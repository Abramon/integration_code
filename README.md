# integration_code: Cross-Chain Bridge Event Listener Simulation

This repository contains a Python script that simulates a critical component of a cross-chain bridge: the event listener and transaction relayer. It is designed to demonstrate a robust, architecturally sound approach to monitoring events on a source blockchain and simulating corresponding actions on a destination blockchain.

## Concept

A cross-chain bridge allows users to transfer assets or data from one blockchain (e.g., Ethereum) to another (e.g., Polygon). A common mechanism for this is a "lock-and-mint" or "lock-and-unlock" system.

1.  **Lock**: A user sends tokens to a bridge smart contract on the source chain. The contract locks these tokens and emits an event (e.g., `TokensLocked`) containing details of the transaction (sender, amount, destination chain, etc.).
2.  **Listen**: Off-chain services, known as listeners or relayers, constantly monitor the source chain for these `TokensLocked` events.
3.  **Relay & Unlock**: Upon detecting a valid event, the relayer submits a transaction to a corresponding bridge contract on the destination chain. This transaction proves that tokens were locked on the source chain and authorizes the destination contract to issue (mint or unlock) an equivalent amount of tokens to the user's address on the new chain.

This script simulates steps 2 and 3 of this process.

## Code Architecture

The script is designed with a modular, class-based architecture to separate concerns and improve maintainability.

-   **`script.py`**: The main entry point of the application.

-   **`CrossChainBridgeListener`**: The main orchestrator class. It initializes and manages the components for both chains and contains the primary execution loop. It is responsible for determining which blocks to scan and passing found events to the processing logic.

-   **`ChainEventListener`**: A reusable class responsible for all interactions with a single blockchain. It handles:
    -   Connecting to a blockchain node via an RPC URL.
    -   Instantiating a `web3.py` contract object.
    -   Fetching the latest block number.
    -   Scanning a given range of blocks for specific smart contract events.
    -   Basic connection error handling and retries.

-   **`TransactionRelayer`**: A class that simulates the action on the destination chain. It:
    -   Connects to the destination blockchain.
    -   Uses a (dummy) private key to create a relayer account object.
    -   Takes the parsed event data from the source chain.
    -   Builds a corresponding `unlockTokens` transaction, including fetching the correct nonce and estimating gas.
    -   **Simulates** the signing and sending of the transaction by logging the transaction payload to the console instead of broadcasting it to the network.

-   **Configuration**: All key parameters (RPC URLs, contract addresses, etc.) are managed via environment variables using the `python-dotenv` library, which is a best practice for separating configuration from code.

## How it Works

The listener operates in a continuous loop with the following steps:

1.  **Initialization**: The `CrossChainBridgeListener` is instantiated. It creates a `ChainEventListener` instance for the source chain (e.g., Ethereum Sepolia) and a `TransactionRelayer` instance for the destination chain (e.g., Polygon Mumbai).

2.  **State Check**: In its main `run()` loop, the listener first determines the range of blocks it needs to scan. On its first run, it starts from the current latest block. On subsequent runs, it starts from the last block it successfully processed (`last_processed_block + 1`).

3.  **Block Scanning**: It calls the `scan_for_events` method of the `ChainEventListener`, passing the calculated block range. This method queries the source chain's RPC node for any `TokensLocked` events that occurred within those blocks.

4.  **Event Processing**: If any events are found, the listener iterates through them.
    -   For each event, it calls its internal `_process_event` method.
    -   This method parses the event data (like `sender`, `amount`, and `transactionId`).

5.  **Transaction Relaying (Simulation)**: The parsed event data is passed to the `TransactionRelayer`'s `simulate_unlock_transaction` method.
    -   The relayer builds a raw transaction that would call the `unlockTokens` function on the destination bridge contract.
    -   It logs the contents of this transaction (the `to` address, `from` address, `nonce`, and encoded function `data`) to the console.

6.  **State Update**: After scanning the block range, the listener updates its `last_processed_block` state to the last block it scanned. This ensures that it doesn't re-scan the same blocks in the next iteration.

7.  **Wait**: The listener then pauses for a configured interval (`scan_interval_seconds`) before starting the loop again from step 2. This prevents spamming the RPC node with requests.

## Usage Example

### 1. Prerequisites

-   Python 3.8+
-   `pip` and `virtualenv`

### 2. Setup

Clone the repository and set up a virtual environment.

```bash
# Clone the repo (or create the files)
git clone https://github.com/your-username/integration_code.git
cd integration_code

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# Install the required libraries
pip install -r requirements.txt
```

### 3. Configuration

The script uses a `.env` file to manage configuration. Create a file named `.env` in the root of the project and add the following content. You can use the provided public RPC URLs or replace them with your own (e.g., from Infura or Alchemy).

```ini
# .env file

# RPC URL for the source chain (e.g., Ethereum Sepolia Testnet)
SOURCE_CHAIN_RPC="https://rpc.sepolia.org"

# Address of the bridge contract on the source chain
SOURCE_BRIDGE_CONTRACT="0x2E64f14a5A8A4B5d5f24248552179659a221295a"

# RPC URL for the destination chain (e.g., Polygon Mumbai Testnet)
DESTINATION_CHAIN_RPC="https://rpc-mumbai.maticvigil.com"

# Address of the bridge contract on the destination chain
DESTINATION_BRIDGE_CONTRACT="0x5bF9e5915d319A5333Ab15093111812a149a842c"

# IMPORTANT: This is a dummy private key for simulation only.
# In a real application, this must be kept secret and managed securely.
RELAYER_PRIVATE_KEY="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
```

### 4. Running the Script

Execute the script from your terminal:

```bash
python script.py
```

### 5. Expected Output

The script will start, connect to the chains, and begin scanning for new blocks. The output will look similar to this:

```
2023-10-27 14:30:00 - INFO - [BridgeListener] - Initializing Cross-Chain Bridge Listener...
2023-10-27 14:30:01 - INFO - [BridgeListener] - Connecting to Ethereum_Sepolia at https://rpc.sepolia.org...
2023-10-27 14:30:02 - INFO - [BridgeListener] - Successfully connected to Ethereum_Sepolia. Chain ID: 11155111
2023-10-27 14:30:02 - INFO - [BridgeListener] - Relayer connecting to Polygon_Mumbai at https://rpc-mumbai.maticvigil.com...
2023-10-27 14:30:04 - INFO - [BridgeListener] - Successfully connected relayer to Polygon_Mumbai. Relayer address: 0x... 
2023-10-27 14:30:04 - INFO - [BridgeListener] - Starting main event loop. Press Ctrl+C to stop.
2023-10-27 14:30:05 - INFO - [BridgeListener] - Initial run. Setting start block to 4567890.
2023-10-27 14:30:05 - INFO - [Ethereum_Sepolia] - Scanning for 'TokensLocked' events from block 4567891 to 4567895.
...
# If an event is found, you will see:
2023-10-27 14:30:25 - INFO - [Ethereum_Sepolia] - Found 1 'TokensLocked' event(s) in the specified range.
2023-10-27 14:30:25 - INFO - [BridgeListener] - Processing 'TokensLocked' event from transaction 0x... 
2023-10-27 14:30:25 - INFO - [Relayer] - Preparing 'unlockTokens' transaction for recipient 0x... with amount 100000000.
2023-10-27 14:30:26 - INFO - [BridgeListener] - --- SIMULATION: Transaction would be sent --- 
2023-10-27 14:30:26 - INFO - [BridgeListener] -     To: 0x5bF9e5915d319A5333Ab15093111812a149a842c
2023-10-27 14:30:26 - INFO - [BridgeListener] -     From: 0x... (Relayer Address)
2023-10-27 14:30:26 - INFO - [BridgeListener] -     Nonce: 42
2023-10-27 14:30:26 - INFO - [BridgeListener] -     Data: 0x... (Hex-encoded function call)
2023-10-27 14:30:26 - INFO - [BridgeListener] - --- END SIMULATION --- 
```
