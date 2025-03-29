import os
import time
import json
import logging
from typing import Dict, Any, List, Optional

import requests
from web3 import Web3
from web3.contract import Contract
from web3.types import LogReceipt
from web3.exceptions import BlockNotFound
from dotenv import load_dotenv

# --- Configuration & Setup ---

# Load environment variables from .env file for sensitive data
load_dotenv()

# Configure structured logging for clear, readable output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('BridgeListener')

# --- Configuration Constants ---
# These would typically be managed in a secure configuration service or .env file
# Using public testnet RPCs for this simulation
SOURCE_CHAIN_CONFIG = {
    'name': 'Ethereum_Sepolia',
    'rpc_url': os.getenv('SOURCE_CHAIN_RPC', 'https://rpc.sepolia.org'),
    'contract_address': os.getenv('SOURCE_BRIDGE_CONTRACT', '0x2E64f14a5A8A4B5d5f24248552179659a221295a'), # Example address
    'scan_interval_seconds': 15,
    'block_scan_limit': 500 # Max blocks to scan in one go to avoid RPC timeouts
}

DESTINATION_CHAIN_CONFIG = {
    'name': 'Polygon_Mumbai',
    'rpc_url': os.getenv('DESTINATION_CHAIN_RPC', 'https://rpc-mumbai.maticvigil.com'),
    'contract_address': os.getenv('DESTINATION_BRIDGE_CONTRACT', '0x5bF9e5915d319A5333Ab15093111812a149a842c'), # Example address
}

# The relayer is the entity that submits the 'unlock' transaction on the destination chain
# NOTE: For security, NEVER hardcode a private key. This is for simulation purposes only.
RELAYER_PRIVATE_KEY = os.getenv('RELAYER_PRIVATE_KEY', '0x' + 'a' * 64) # A dummy private key

# --- Contract ABIs (Application Binary Interfaces) ---
# Simplified ABIs for the bridge contracts for demonstration purposes.

SOURCE_BRIDGE_ABI = json.loads('''
[
    {
        "anonymous": false,
        "inputs": [
            {"indexed": true, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": true, "internalType": "address", "name": "token", "type": "address"},
            {"indexed": false, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": false, "internalType": "uint256", "name": "destinationChainId", "type": "uint256"},
            {"indexed": false, "internalType": "bytes32", "name": "transactionId", "type": "bytes32"}
        ],
        "name": "TokensLocked",
        "type": "event"
    }
]
''')

DESTINATION_BRIDGE_ABI = json.loads('''
[
    {
        "inputs": [
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "bytes32", "name": "sourceTransactionId", "type": "bytes32"}
        ],
        "name": "unlockTokens",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
''')


class ChainEventListener:
    """
    Handles connection and event scanning for a single blockchain.

    This class is responsible for connecting to a given blockchain node via its RPC URL,
    instantiating a contract object, and scanning block ranges for specific events.
    It includes retry logic for connections and handles potential RPC errors.
    """
    def __init__(self, name: str, rpc_url: str, contract_address: str, contract_abi: List[Dict[str, Any]]):
        """
        Initializes the event listener for a specific chain.

        Args:
            name (str): A human-readable name for the chain (e.g., 'Ethereum_Mainnet').
            rpc_url (str): The HTTP RPC endpoint URL for the blockchain node.
            contract_address (str): The checksummed address of the smart contract to monitor.
            contract_abi (List[Dict[str, Any]]): The ABI of the smart contract.
        """
        self.name = name
        self.rpc_url = rpc_url
        self.contract_address = contract_address
        self.contract_abi = contract_abi
        self.web3: Optional[Web3] = None
        self.contract: Optional[Contract] = None
        self._connect()

    def _connect(self) -> None:
        """
        Establishes a connection to the blockchain node.
        Includes basic retry logic in case of transient network issues.
        """
        logger.info(f"Connecting to {self.name} at {self.rpc_url}...")
        for attempt in range(3):
            try:
                self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
                if self.web3.is_connected():
                    self.contract = self.web3.eth.contract(
                        address=Web3.to_checksum_address(self.contract_address),
                        abi=self.contract_abi
                    )
                    logger.info(f"Successfully connected to {self.name}. Chain ID: {self.web3.eth.chain_id}")
                    return
            except (requests.exceptions.ConnectionError, Exception) as e:
                logger.warning(f"Connection attempt {attempt + 1} to {self.name} failed: {e}")
                time.sleep(2 ** attempt) # Exponential backoff
        logger.error(f"Failed to connect to {self.name} after several attempts.")
        raise ConnectionError(f"Could not connect to {self.name}.")

    def get_latest_block(self) -> int:
        """
        Fetches the most recent block number from the connected node.

        Returns:
            int: The latest block number.
        
        Raises:
            ConnectionError: If the Web3 provider is not connected.
        """
        if not self.web3 or not self.web3.is_connected():
            logger.warning(f"Not connected to {self.name}. Attempting to reconnect...")
            self._connect()
        
        if not self.web3:
             raise ConnectionError(f"Web3 provider for {self.name} is not available.")

        return self.web3.eth.block_number

    def scan_for_events(self, start_block: int, end_block: int, event_name: str) -> List[LogReceipt]:
        """
        Scans a range of blocks for a specific event.

        Args:
            start_block (int): The starting block number for the scan.
            end_block (int): The ending block number for the scan.
            event_name (str): The name of the event to look for (must be in the ABI).

        Returns:
            List[LogReceipt]: A list of event logs found within the block range.
        """
        if not self.contract or not self.web3:
            logger.error(f"Contract or Web3 provider for {self.name} not initialized.")
            return []
        
        logger.info(f"[{self.name}] Scanning for '{event_name}' events from block {start_block} to {end_block}.")
        try:
            event_filter = self.contract.events[event_name].create_filter(
                fromBlock=start_block,
                toBlock=end_block
            )
            events = event_filter.get_all_entries()
            if events:
                logger.info(f"[{self.name}] Found {len(events)} '{event_name}' event(s) in the specified range.")
            return events
        except BlockNotFound:
             logger.warning(f"[{self.name}] Block range from {start_block} to {end_block} not found. The chain might have re-orged or the range is too fresh.")
             return []
        except Exception as e:
            # This can happen if the RPC node limits the query range or is under load.
            logger.error(f"[{self.name}] An error occurred while scanning for events: {e}")
            return []


class TransactionRelayer:
    """
    Simulates the process of creating and sending a transaction to a destination chain.

    In a real system, this component would securely manage a private key, handle nonces,
    calculate gas prices, and submit signed transactions. For this simulation, it builds
    the transaction and logs the details without actually sending it.
    """
    def __init__(self, name: str, rpc_url: str, contract_address: str, contract_abi: List[Dict[str, Any]], relayer_pk: str):
        self.name = name
        self.rpc_url = rpc_url
        self.relayer_private_key = relayer_pk
        self.web3: Optional[Web3] = None
        self.contract: Optional[Contract] = None
        self.relayer_account = None
        self._connect()

    def _connect(self) -> None:
        """
        Connects to the destination chain and sets up the relayer account.
        """
        logger.info(f"Relayer connecting to {self.name} at {self.rpc_url}...")
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self.web3.is_connected():
                raise ConnectionError("Failed to connect to destination chain RPC.")
            
            self.contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=contract_abi
            )
            self.relayer_account = self.web3.eth.account.from_key(self.relayer_private_key)
            logger.info(f"Successfully connected relayer to {self.name}. Relayer address: {self.relayer_account.address}")
        except Exception as e:
            logger.error(f"Relayer failed to connect or set up account on {self.name}: {e}")
            raise

    def simulate_unlock_transaction(self, event_data: Dict[str, Any]) -> None:
        """
        Builds and simulates the signing and sending of an 'unlockTokens' transaction.

        Args:
            event_data (Dict[str, Any]): The parsed data from the source chain's 'TokensLocked' event.
        """
        if not self.web3 or not self.contract or not self.relayer_account:
            logger.error(f"Relayer for {self.name} is not properly initialized.")
            return

        recipient = event_data['sender']
        token = event_data['token'] # In a real bridge, this address would be mapped to the destination chain equivalent
        amount = event_data['amount']
        source_tx_id = event_data['transactionId']

        logger.info(f"[Relayer] Preparing 'unlockTokens' transaction for recipient {recipient} with amount {amount}.")

        try:
            # 1. Get the latest nonce for the relayer account
            nonce = self.web3.eth.get_transaction_count(self.relayer_account.address)

            # 2. Build the transaction payload
            tx_payload = {
                'from': self.relayer_account.address,
                'nonce': nonce,
                'gasPrice': self.web3.eth.gas_price, # In production, use a more robust gas strategy
                'chainId': self.web3.eth.chain_id
            }

            # 3. Build the contract function call
            unlock_tx = self.contract.functions.unlockTokens(
                recipient,
                token,
                amount,
                source_tx_id
            ).build_transaction(tx_payload)

            # 4. Sign the transaction (simulation)
            # signed_tx = self.web3.eth.account.sign_transaction(unlock_tx, self.relayer_private_key)

            # 5. Send the transaction (simulation)
            # tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

            logger.info(f"--- SIMULATION: Transaction would be sent --- ")
            logger.info(f"    To: {unlock_tx['to']}")
            logger.info(f"    From: {unlock_tx['from']}")
            logger.info(f"    Nonce: {unlock_tx['nonce']}")
            logger.info(f"    Data: {unlock_tx['data']}")
            logger.info(f"--- END SIMULATION --- ")

        except Exception as e:
            logger.error(f"[Relayer] Failed to build or simulate unlock transaction: {e}")


class CrossChainBridgeListener:
    """
    Orchestrates the entire cross-chain listening and relaying process.

    This main class initializes listeners for the source chain and a relayer for the
    destination chain. It runs a continuous loop to poll for new blocks on the source
    chain, scan for 'TokensLocked' events, and trigger the relayer to process them.
    """
    def __init__(self):
        logger.info("Initializing Cross-Chain Bridge Listener...")
        self.source_chain = ChainEventListener(
            name=SOURCE_CHAIN_CONFIG['name'],
            rpc_url=SOURCE_CHAIN_CONFIG['rpc_url'],
            contract_address=SOURCE_CHAIN_CONFIG['contract_address'],
            contract_abi=SOURCE_BRIDGE_ABI
        )
        self.relayer = TransactionRelayer(
            name=DESTINATION_CHAIN_CONFIG['name'],
            rpc_url=DESTINATION_CHAIN_CONFIG['rpc_url'],
            contract_address=DESTINATION_CHAIN_CONFIG['contract_address'],
            contract_abi=DESTINATION_BRIDGE_ABI,
            relayer_pk=RELAYER_PRIVATE_KEY
        )
        self.last_processed_block = None
        self.scan_limit = SOURCE_CHAIN_CONFIG['block_scan_limit']

    def _process_event(self, event: LogReceipt) -> None:
        """
        Handles a single 'TokensLocked' event log.

        It parses the event data and passes it to the transaction relayer.
        A real system would include robust checks here, e.g., verifying the
        destination chain ID and ensuring the transaction hasn't been processed before.

        Args:
            event (LogReceipt): The raw event log from web3.py.
        """
        event_args = event['args']
        tx_hash = event['transactionHash'].hex()
        logger.info(f"Processing 'TokensLocked' event from transaction {tx_hash}...")

        # In a real bridge, you would check if event_args['destinationChainId'] matches
        # the chain ID of your destination network.

        self.relayer.simulate_unlock_transaction(event_args)

    def run(self) -> None:
        """
        Starts the main event loop for the bridge listener.
        """
        logger.info("Starting main event loop. Press Ctrl+C to stop.")
        while True:
            try:
                # Determine the range of blocks to scan
                latest_block = self.source_chain.get_latest_block()
                
                if self.last_processed_block is None:
                    # On first run, start from the latest block to avoid scanning the whole chain history.
                    # In a production system, this would be loaded from a persistent state store.
                    self.last_processed_block = latest_block - 1 
                    logger.info(f"Initial run. Setting start block to {self.last_processed_block}.")

                from_block = self.last_processed_block + 1
                to_block = min(latest_block, from_block + self.scan_limit - 1)

                if from_block > to_block:
                    logger.debug(f"No new blocks to scan. Current head is {latest_block}.")
                    time.sleep(SOURCE_CHAIN_CONFIG['scan_interval_seconds'])
                    continue

                # Scan for events
                events = self.source_chain.scan_for_events(
                    start_block=from_block,
                    end_block=to_block,
                    event_name='TokensLocked'
                )

                # Process any found events
                for event in events:
                    self._process_event(event)

                # Update state for the next iteration
                self.last_processed_block = to_block
                
                # Wait before the next scan
                time.sleep(SOURCE_CHAIN_CONFIG['scan_interval_seconds'])

            except ConnectionError as e:
                logger.error(f"A connection error occurred: {e}. Retrying in 60 seconds...")
                time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Shutdown signal received. Exiting gracefully.")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
                time.sleep(30) # Wait longer after unexpected errors


if __name__ == '__main__':
    listener = CrossChainBridgeListener()
    listener.run()
