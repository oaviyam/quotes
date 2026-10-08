from get_quote import GetQuote
import multiprocessing
import atexit
import time
import yaml
import os
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Data directory for storing ticker files
data_dir = "./data"

# Load symbols from tickers.yaml
def load_symbols():
    yaml_path = os.path.join(os.path.dirname(__file__), 'tickers.yaml')
    logger.debug(f"Loading symbols from {yaml_path}")
    
    try:
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)
        symbols = config.get('symbols', [])
        logger.info(f"Loaded {len(symbols)} symbols: {', '.join(symbols)}")
        return symbols
    except FileNotFoundError:
        logger.error(f"tickers.yaml not found at {yaml_path}")
        return []
    except yaml.YAMLError as e:
        logger.error(f"Error parsing tickers.yaml: {e}")
        return []

my_symbols = load_symbols()


async def collect_symbol_async(symbol, interval=5, duration=50):
    """
    Collect quotes for a single symbol asynchronously
    
    Args:
        symbol: Stock symbol to collect
        interval: Time in seconds between quote fetches
        duration: Total duration in seconds to collect quotes
    """
    ticker_file = os.path.join(data_dir, f"{symbol}.csv")
    logger.debug(f"Output file for {symbol}: {os.path.abspath(ticker_file)}")
    
    try:
        with open(ticker_file, 'w') as f:
            # Write header
            f.write("symbol,time,epoch,price,isup,volume,isRealTime,bidPrice,askPrice,bidSize,askSize\n")
            logger.debug(f"Header written to {symbol}.csv")
            
            # Collect quotes asynchronously
            quote = GetQuote(symbol)
            await quote.collect_quotes_async(f, interval=interval, duration=duration)
        
        logger.info(f"✓ Data for {symbol} saved to {ticker_file}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to collect data for {symbol}: {type(e).__name__}: {e}")
        return False


async def collect_all_symbols_async(symbols, interval=5, duration=50):
    """
    Collect quotes for all symbols concurrently
    
    Args:
        symbols: List of stock symbols to collect
        interval: Time in seconds between quote fetches
        duration: Total duration in seconds to collect quotes
    """
    logger.info(f"Starting concurrent collection for {len(symbols)} symbols")
    
    # Create tasks for all symbols
    tasks = [
        collect_symbol_async(symbol, interval, duration)
        for symbol in symbols
    ]
    
    # Run all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Count successes
    success_count = sum(1 for r in results if r is True)
    logger.info(f"Collection complete: {success_count}/{len(symbols)} symbols succeeded")
    
    return results


# Main execution
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("Starting Async Quote Collector")
    logger.info("=" * 60)
    
    # Create data directory if it doesn't exist
    logger.debug(f"Ensuring data directory exists: {data_dir}")
    os.makedirs(data_dir, exist_ok=True)
    logger.info(f"Data directory ready: {os.path.abspath(data_dir)}")
    
    if not my_symbols:
        logger.error("No symbols to collect. Exiting.")
        exit(1)
    
    logger.info(f"Collecting quotes for {len(my_symbols)} symbols concurrently: {', '.join(my_symbols)}")
    
    # Run async collection
    start_time = time.time()
    asyncio.run(collect_all_symbols_async(my_symbols, interval=5, duration=50))
    elapsed_time = time.time() - start_time
    
    logger.info("=" * 60)
    logger.info(f"Quote collection completed in {elapsed_time:.2f} seconds")
    logger.info("=" * 60)
