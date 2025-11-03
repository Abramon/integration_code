import time
import logging
import functools

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def def retry_with_exponential_backoff(
    max_retries=3,
    initial_delay=1,
    backoff_factor=2,
    exceptions=(Exception,)
):
    """
    A decorator to retry a function with exponential backoff.

    This is useful for operations that might fail due to transient issues,
    such as network requests to external services.

    Args:
        max_retries (int): Maximum number of retries.
        initial_delay (float): Initial delay between retries in seconds.
        backoff_factor (float): Multiplier for the delay in each subsequent retry.
        exceptions (tuple): A tuple of exception types to catch and retry on.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            delay = initial_delay

            while attempt <= max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    if attempt > max_retries:
                        logging.error(
                            f"Function '{func.__name__}' failed after {max_retries} retries. Raising last exception."
                        )
                        raise
                    
                    logging.warning(
                        f"Function '{func.__name__}' failed with {type(e).__name__}: {e}. "
                        f"Retrying in {delay:.2f} seconds... (Attempt {attempt}/{max_retries})"
                    )
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator
