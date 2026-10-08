# Stock Quote Collector

A Python application to collect real-time stock quotes from NASDAQ API concurrently.

## Features

- ✅ **Concurrent Collection**: Fetches quotes for multiple tickers simultaneously using async/await
- ✅ **Real-time Data**: Gets live stock prices, volume, bid/ask spreads from NASDAQ
- ✅ **Configurable**: Easy YAML configuration for tickers and collection parameters
- ✅ **Comprehensive Logging**: Detailed debug logs for monitoring and troubleshooting
- ✅ **CSV Output**: Individual CSV files for each ticker with timestamped data

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

Edit `tickers.yaml` to configure which stocks to track:

```yaml
symbols:
  - AAPL
  - AMZN
  - GOOGL
  - MSFT
  - TSLA
```

## Usage

Run the collector:

```bash
python collector.py
```

This will:
1. Load symbols from `tickers.yaml`
2. Create a `data/` directory
3. Collect quotes **concurrently** for all symbols
4. Save each ticker's data to `data/{SYMBOL}.csv`

### Output Format

Each CSV file contains:
- `symbol`: Stock ticker symbol
- `time`: Timestamp of the quote
- `epoch`: Unix timestamp
- `price`: Last sale price
- `isup`: True if price is up, False if down
- `volume`: Trading volume
- `isRealTime`: Whether the quote is real-time
- `bidPrice`: Current bid price
- `askPrice`: Current ask price
- `bidSize`: Bid size
- `askSize`: Ask size

## Performance

The async implementation collects quotes for **all tickers concurrently**, dramatically reducing total collection time:

- **Sequential**: 5 tickers × 50 seconds = 250 seconds total
- **Concurrent**: All 5 tickers in ~50 seconds (parallelized)

## Customization

### Collection Parameters

Modify in `collector.py`:

```python
asyncio.run(collect_all_symbols_async(
    my_symbols, 
    interval=5,   # Seconds between fetches
    duration=50   # Total duration per ticker
))
```

### Logging Level

Change in `collector.py` or `get_quote.py`:

```python
logging.basicConfig(
    level=logging.INFO,  # Change to INFO, WARNING, or ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

See `LOGGING.md` for more details.

## Architecture

- **`get_quote.py`**: Core `GetQuote` class with both sync and async methods
- **`collector.py`**: Main script that orchestrates concurrent collection
- **`tickers.yaml`**: Configuration file for stock symbols
- **`data/`**: Output directory for CSV files

## License

See LICENSE file for details.
