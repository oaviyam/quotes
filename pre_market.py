"""Local pre-market board.

Reads every symbol in tickers.yaml, polls the NASDAQ quote API, and serves a
page on localhost. The graph starts when this process starts and grows until
the process stops.

    ./pre-market
    ./pre-market --interval 10 --port 8765
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pre-market")

from get_quote import GetQuote  # noqa: E402


PAGE_PATH = Path(__file__).with_name("pre_market.html")


def load_symbols():
    yaml_path = Path(__file__).with_name("tickers.yaml")
    logger.debug("Loading symbols from %s", yaml_path)
    try:
        import yaml

        with yaml_path.open() as handle:
            config = yaml.safe_load(handle) or {}
        symbols = config.get("symbols") or []
        logger.info("Loaded %s symbols: %s", len(symbols), ", ".join(symbols))
        return symbols
    except FileNotFoundError:
        logger.error("tickers.yaml not found at %s", yaml_path)
        return []
    except Exception as exc:
        logger.error("Error reading tickers.yaml: %s", exc)
        return []


def to_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "N/A", "NA"):
        return None
    try:
        return GetQuote.get_float(text)
    except (TypeError, ValueError):
        return None


def is_premarket(status):
    if not status:
        return False
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    return normalized in {"pre-market", "premarket"}


def parse_payload(payload):
    """Pull pre-market price, prior close, and delta out of a NASDAQ quote."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or "primaryData" not in data:
        status = (payload or {}).get("status") or {}
        messages = status.get("bCodeMessage") or []
        if messages and isinstance(messages[0], dict):
            code = messages[0].get("code")
            message = messages[0].get("errorMessage") or "Unknown API error"
            return None, f"API {code}: {message}"
        return None, "Quote payload did not include primary data"

    primary = data.get("primaryData") or {}
    secondary = data.get("secondaryData") or {}
    price = to_float(primary.get("lastSalePrice"))
    close = to_float(secondary.get("lastSalePrice"))
    delta = None
    delta_pct = None
    if price is not None and close not in (None, 0):
        delta = price - close
        delta_pct = (delta / close) * 100

    return {
        "symbol": data.get("symbol"),
        "company": data.get("companyName"),
        "market_status": data.get("marketStatus") or "",
        "price": price,
        "close": close,
        "delta": delta,
        "delta_pct": delta_pct,
        "as_of": primary.get("lastTradeTimestamp") or "",
        "is_premarket": is_premarket(data.get("marketStatus")),
    }, None


async def fetch_symbol(session, symbol):
    quote = GetQuote(symbol)
    try:
        async with session.get(
            quote.url,
            headers=quote.headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                body = await response.text()
                return symbol, None, f"HTTP {response.status}: {body[:180]}"
            payload = await response.json(content_type=None)
    except asyncio.TimeoutError:
        return symbol, None, "Timeout"
    except aiohttp.ClientError as exc:
        return symbol, None, f"{type(exc).__name__}: {exc}"
    except json.JSONDecodeError as exc:
        return symbol, None, f"JSON decode error: {exc}"

    parsed, error = parse_payload(payload)
    return symbol, parsed, error


def publish(state, payload):
    state.snapshot = payload
    dead = []
    for queue in list(state.subscribers):
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(payload)
        except Exception:
            dead.append(queue)
    for queue in dead:
        state.subscribers.discard(queue)


async def refresh(state, session):
    started = time.perf_counter()
    results = await asyncio.gather(
        *(fetch_symbol(session, symbol) for symbol in state.symbols)
    )
    now = time.time()
    quotes = []
    ok = 0
    for symbol, parsed, error in results:
        history = state.history.setdefault(symbol, [])
        if error:
            logger.warning("%s: %s", symbol, error)
        elif parsed and parsed["price"] is not None:
            state.latest[symbol] = parsed
            if parsed["is_premarket"]:
                history.append({"t": now, "p": parsed["price"]})
                ok += 1
        latest = state.latest.get(symbol) or {}
        source = parsed or latest
        recording = bool(parsed and parsed["is_premarket"] and parsed["price"] is not None)
        quotes.append(
            {
                "symbol": symbol,
                "company": latest.get("company"),
                "market_status": source.get("market_status"),
                "recording": recording,
                "price": latest.get("price"),
                "close": latest.get("close"),
                "delta": latest.get("delta"),
                "delta_pct": latest.get("delta_pct"),
                "as_of": latest.get("as_of"),
                "points": history,
                "error": error,
            }
        )

    payload = json.dumps(
        {
            "interval": state.interval,
            "started_at": state.started_at,
            "server_time": now,
            "quotes": quotes,
        }
    ).encode()
    publish(state, payload)
    elapsed = time.perf_counter() - started
    logger.info("Updated %s/%s symbols in %.1fs", ok, len(state.symbols), elapsed)


async def poll_forever(state):
    async with aiohttp.ClientSession() as session:
        while True:
            started = time.monotonic()
            try:
                await refresh(state, session)
            except Exception:
                logger.exception("Quote refresh failed")
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.0, state.interval - elapsed))


async def on_startup(app):
    app["state"].task = asyncio.create_task(poll_forever(app["state"]))


async def on_cleanup(app):
    task = getattr(app["state"], "task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def index(request):
    return web.Response(
        text=request.app["state"].page,
        content_type="text/html",
        charset="utf-8",
        headers={"Cache-Control": "no-store"},
    )


async def api_quotes(request):
    state = request.app["state"]
    snapshot = state.snapshot
    if snapshot is None:
        snapshot = json.dumps(
            {
                "interval": state.interval,
                "started_at": state.started_at,
                "server_time": time.time(),
                "quotes": [],
            }
        ).encode()
    return web.Response(
        body=snapshot,
        content_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


async def events(request):
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
        },
    )
    await response.prepare(request)
    state = request.app["state"]
    queue = asyncio.Queue(maxsize=1)
    state.subscribers.add(queue)
    try:
        snapshot = state.snapshot
        if snapshot:
            await response.write(b"data: " + snapshot + b"\n\n")
        while True:
            payload = await queue.get()
            await response.write(b"data: " + payload + b"\n\n")
    except asyncio.CancelledError:
        raise
    except (ConnectionResetError, RuntimeError, aiohttp.ClientConnectionError):
        pass
    finally:
        state.subscribers.discard(queue)
    return response


async def favicon(_request):
    return web.Response(status=204)


class BoardState:
    def __init__(self, symbols, interval, page):
        self.symbols = symbols
        self.interval = interval
        self.page = page
        self.history = {symbol: [] for symbol in symbols}
        self.latest = {}
        self.subscribers = set()
        self.snapshot = None
        self.started_at = time.time()
        self.task = None


def build_app(symbols, interval):
    if not PAGE_PATH.is_file():
        raise FileNotFoundError(f"Missing page template: {PAGE_PATH}")
    app = web.Application()
    app["state"] = BoardState(
        symbols,
        interval,
        PAGE_PATH.read_text(encoding="utf-8"),
    )
    app.add_routes(
        [
            web.get("/", index),
            web.get("/api/quotes", api_quotes),
            web.get("/events", events),
            web.get("/favicon.ico", favicon),
        ]
    )
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="pre-market",
        description="Serve a local pre-market board for the symbols in tickers.yaml.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5,
        help="Seconds between quote updates (default: 5)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    args = parser.parse_args(argv)
    if args.interval <= 0:
        parser.error("--interval must be greater than 0")
    if not 0 < args.port < 65536:
        parser.error("--port must be between 1 and 65535")
    return args


def main(argv=None):
    args = parse_args(argv)
    symbols = load_symbols()
    if not symbols:
        logger.error("No symbols to collect. Exiting.")
        return 1
    app = build_app(symbols, args.interval)
    logger.info(
        "Pre-market board at http://%s:%s  (every %ss, %s symbols)",
        args.host,
        args.port,
        args.interval,
        len(symbols),
    )
    web.run_app(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
