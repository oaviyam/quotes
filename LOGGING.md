# Logging Configuration

## Overview

Both `get_quote.py` and `collector.py` now include comprehensive debug logging using Python's built-in `logging` module. The async implementation provides detailed logs for concurrent operations.

## Log Levels

The logging is configured with the following levels:

- **DEBUG**: Detailed diagnostic information
- **INFO**: General informational messages about progress
- **WARNING**: Warning messages (not currently used)
- **ERROR**: Error messages when something fails

## Default Configuration

By default, logs are set to **DEBUG** level, which shows all messages.

## Changing Log Level

To change the log level, modify the `level` parameter in the `logging.basicConfig()` call:

```python
logging.basicConfig(
    level=logging.INFO,  # Change to INFO, WARNING, or ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
```

## What Gets Logged

### collector.py
- ✓ Loading symbols from tickers.yaml
- ✓ Data directory creation
- ✓ Concurrent collection start with all symbols
- ✓ File paths and operations
- ✓ Success/failure status for each symbol
- ✓ Overall completion status with elapsed time
- ✓ Success count summary

### get_quote.py
- ✓ Quote object initialization
- ✓ API request details (URL, status codes)
- ✓ Response size and parsing
- ✓ Quote data (price, volume, market status)
- ✓ Timestamp parsing
- ✓ History updates
- ✓ File write operations
- ✓ Collection iterations and timing
- ✓ Error details (timeouts, HTTP errors, parsing errors)

## Example Output (Async Concurrent Collection)

```
2025-12-20 10:30:15 - __main__ - INFO - ============================================================
2025-12-20 10:30:15 - __main__ - INFO - Starting Async Quote Collector
2025-12-20 10:30:15 - __main__ - INFO - ============================================================
2025-12-20 10:30:15 - __main__ - DEBUG - Loading symbols from /path/to/tickers.yaml
2025-12-20 10:30:15 - __main__ - INFO - Loaded 5 symbols: AAPL, AMZN, GOOGL, MSFT, TSLA
2025-12-20 10:30:15 - __main__ - INFO - Collecting quotes for 5 symbols concurrently: AAPL, AMZN, GOOGL, MSFT, TSLA
2025-12-20 10:30:15 - __main__ - INFO - Starting concurrent collection for 5 symbols
2025-12-20 10:30:15 - __main__ - DEBUG - Initializing GetQuote for AAPL
2025-12-20 10:30:15 - __main__ - DEBUG - Initializing GetQuote for AMZN
2025-12-20 10:30:15 - __main__ - DEBUG - Initializing GetQuote for GOOGL
2025-12-20 10:30:15 - __main__ - INFO - Starting async collection for AAPL: interval=5s, duration=50s
2025-12-20 10:30:15 - __main__ - INFO - Starting async collection for AMZN: interval=5s, duration=50s
2025-12-20 10:30:15 - __main__ - INFO - Starting async collection for GOOGL: interval=5s, duration=50s
2025-12-20 10:30:15 - __main__ - DEBUG - Fetching quote async for AAPL from https://api.nasdaq.com/...
2025-12-20 10:30:15 - __main__ - DEBUG - Fetching quote async for AMZN from https://api.nasdaq.com/...
2025-12-20 10:30:16 - __main__ - DEBUG - API response status code: 200
2025-12-20 10:30:16 - __main__ - INFO - AAPL: $175.50 (up 1.2%), Volume: 52000000, RealTime: True
2025-12-20 10:30:16 - __main__ - INFO - AMZN: $152.30 (down -0.5%), Volume: 35000000, RealTime: True
2025-12-20 10:30:16 - __main__ - DEBUG - Quote written to file for AAPL: price=175.50
2025-12-20 10:30:16 - __main__ - DEBUG - Quote written to file for AMZN: price=152.30
...
2025-12-20 10:31:05 - __main__ - INFO - Completed async collection for AAPL: 10 iterations, 10 quotes collected
2025-12-20 10:31:05 - __main__ - INFO - ✓ Data for AAPL saved to data/AAPL.csv
2025-12-20 10:31:05 - __main__ - INFO - Collection complete: 5/5 symbols succeeded
2025-12-20 10:31:05 - __main__ - INFO - ============================================================
2025-12-20 10:31:05 - __main__ - INFO - Quote collection completed in 50.32 seconds
2025-12-20 10:31:05 - __main__ - INFO - ============================================================
```

**Note**: With async collection, all symbols are fetched **concurrently**, so you'll see interleaved log messages from multiple tickers.

## Logging to File

To save logs to a file instead of console, add a file handler:

```python
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('quote_collector.log'),
        logging.StreamHandler()  # Also print to console
    ]
)
```

## Quiet Mode (INFO only)

For cleaner output, set level to INFO to hide DEBUG messages:

```python
logging.basicConfig(level=logging.INFO, ...)
```

This will show only high-level progress without detailed debugging information.

