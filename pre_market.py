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
import re
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
YAML_PATH = Path(__file__).with_name("tickers.yaml")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def normalize_symbol(value):
    if not isinstance(value, str):
        return None
    symbol = value.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        return None
    return symbol


def load_board():
    """Read tickers.yaml. Symbols stay a string list so the collector still works."""
    logger.debug("Loading symbols from %s", YAML_PATH)
    try:
        import yaml

        with YAML_PATH.open() as handle:
            config = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        logger.error("tickers.yaml not found at %s", YAML_PATH)
        return [], {}
    except Exception as exc:
        logger.error("Error reading tickers.yaml: %s", exc)
        return [], {}

    symbols = []
    for item in config.get("symbols") or []:
        if isinstance(item, str):
            symbol = normalize_symbol(item)
        elif isinstance(item, dict):
            symbol = normalize_symbol(str(item.get("symbol") or ""))
        else:
            symbol = None
        if symbol and symbol not in symbols:
            symbols.append(symbol)

    buys = {}
    raw_buys = config.get("buys") or {}
    if isinstance(raw_buys, dict):
        for key, value in raw_buys.items():
            symbol = normalize_symbol(str(key))
            position = parse_position(value)
            if symbol and position:
                buys[symbol] = position
    logger.info("Loaded %s symbols: %s", len(symbols), ", ".join(symbols))
    return symbols, buys


def parse_position(value):
    """A buy is a price, plus an optional share count. A bare number is price only."""
    if isinstance(value, dict):
        price = to_float(value.get("price"))
        shares = to_float(value.get("shares"))
    else:
        price = to_float(value)
        shares = None
    if price is None or price <= 0:
        return None
    if shares is not None and shares <= 0:
        shares = None
    return {"price": price, "shares": shares}


def format_buy(price):
    text = f"{price:.4f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def save_board(symbols, buys):
    lines = ["# Stock symbols to track", "symbols:"]
    for symbol in symbols:
        lines.append(f"  - {symbol}")
    priced = [(symbol, buys[symbol]) for symbol in symbols if symbol in buys]
    if priced:
        lines.append("")
        lines.append("# Price paid per share, and how many shares")
        lines.append("buys:")
        for symbol, position in priced:
            lines.append(f"  {symbol}:")
            lines.append(f"    price: {format_buy(position['price'])}")
            if position.get("shares") is not None:
                lines.append(f"    shares: {format_buy(position['shares'])}")
    text = "\n".join(lines) + "\n"
    tmp = YAML_PATH.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(YAML_PATH)


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


def session_kind(status):
    """Which quote the feed is printing: pre-market, the open session, or after hours."""
    if not status:
        return "closed"
    normalized = status.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in {"pre-market", "premarket"}:
        return "pre"
    if normalized in {"open", "market-open"}:
        return "regular"
    if normalized in {"after-hours", "afterhours", "post-market", "postmarket"}:
        return "post"
    return "closed"


def is_premarket(status):
    return session_kind(status) == "pre"


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
    close_as_of = secondary.get("lastTradeTimestamp") or ""
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
        "close_as_of": close_as_of,
        "close_official": "closed" in close_as_of.lower(),
        "delta": delta,
        "delta_pct": delta_pct,
        "as_of": primary.get("lastTradeTimestamp") or "",
        "is_premarket": is_premarket(data.get("marketStatus")),
        "session": session_kind(data.get("marketStatus")),
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


def remember_close(state, symbol, parsed):
    """Keep the closing price from when the board starts.

    Prefer the official prior close ("Closed at ...") over a secondary quote
    that is still moving. Later polls do not shift the start of the graph.
    """
    close = parsed.get("close")
    official = bool(parsed.get("close_official"))
    locked = state.close_at_start.get(symbol)
    if close is None:
        return None if locked is None else locked["price"]
    if locked is None:
        state.close_at_start[symbol] = {"price": close, "official": official}
        return close
    if official and not locked["official"]:
        locked["price"] = close
        locked["official"] = True
    return locked["price"]


def place_close_anchor(history, close, started_at):
    if close is None:
        return
    for point in history:
        if point.get("anchor"):
            point["p"] = close
            return
    history.insert(0, {"t": started_at, "p": close, "anchor": True})


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
    active = set(state.symbols)
    for symbol, parsed, error in results:
        if symbol not in active:
            continue
        history = state.history.setdefault(symbol, [])
        if error:
            logger.warning("%s: %s", symbol, error)
        elif parsed and parsed["price"] is not None:
            state.latest[symbol] = parsed
            # Keep the same prior close as the baseline, and keep recording.
            # Pre-market uses the pre-market print. Once the market is open the
            # print is the regular session, then after-hours when that session starts.
            close = remember_close(state, symbol, parsed)
            place_close_anchor(history, close, state.started_at)
            history.append({"t": now, "p": parsed["price"]})
            ok += 1
        latest = state.latest.get(symbol) or {}
        source = parsed or latest
        if parsed and parsed.get("close") is not None:
            remember_close(state, symbol, parsed)
        locked = state.close_at_start.get(symbol) or {}
        display_close = locked.get("price", latest.get("close"))
        price = latest.get("price")
        delta = latest.get("delta")
        delta_pct = latest.get("delta_pct")
        if price is not None and display_close not in (None, 0):
            delta = price - display_close
            delta_pct = (delta / display_close) * 100
        recording = bool(parsed and parsed["price"] is not None)
        quotes.append(
            {
                "symbol": symbol,
                "company": latest.get("company"),
                "market_status": source.get("market_status"),
                "session": source.get("session") or "closed",
                "recording": recording,
                "price": price,
                "close": display_close,
                "delta": delta,
                "delta_pct": delta_pct,
                "as_of": latest.get("as_of"),
                "buy": (state.buys.get(symbol) or {}).get("price"),
                "shares": (state.buys.get(symbol) or {}).get("shares"),
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


def json_error(message, status):
    return web.json_response({"error": message}, status=status)


async def read_body(request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return None
    return body if isinstance(body, dict) else None


async def add_ticker(request):
    body = await read_body(request)
    if body is None:
        return json_error("Send a ticker symbol", 400)
    symbol = normalize_symbol(body.get("symbol") or "")
    if not symbol:
        return json_error("Enter a ticker like AAPL", 400)
    state = request.app["state"]
    if symbol in state.symbols:
        return json_error(f"{symbol} is already on the board", 409)
    state.symbols.append(symbol)
    save_board(state.symbols, state.buys)
    logger.info("Added %s", symbol)
    return web.json_response({"symbol": symbol, "symbols": state.symbols})


async def delete_ticker(request):
    symbol = normalize_symbol(request.match_info["symbol"])
    if not symbol:
        return json_error("Unknown ticker", 400)
    state = request.app["state"]
    if symbol not in state.symbols:
        return json_error(f"{symbol} is not on the board", 404)
    state.symbols = [item for item in state.symbols if item != symbol]
    state.buys.pop(symbol, None)
    state.history.pop(symbol, None)
    state.latest.pop(symbol, None)
    state.close_at_start.pop(symbol, None)
    save_board(state.symbols, state.buys)
    logger.info("Removed %s", symbol)
    return web.json_response({"symbol": symbol, "symbols": state.symbols})


async def set_buy(request):
    symbol = normalize_symbol(request.match_info["symbol"])
    if not symbol:
        return json_error("Unknown ticker", 400)
    state = request.app["state"]
    if symbol not in state.symbols:
        return json_error(f"{symbol} is not on the board", 404)
    body = await read_body(request)
    if body is None or "price" not in body:
        return json_error("Send a buy price", 400)
    raw = body.get("price")
    raw_shares = body.get("shares")
    price_blank = raw is None or raw == ""
    shares_blank = raw_shares is None or raw_shares == ""
    if price_blank and shares_blank:
        state.buys.pop(symbol, None)
        price = None
        shares = None
    elif price_blank:
        return json_error("Enter the price you paid, or leave both fields blank to follow only", 400)
    else:
        price = to_float(raw)
        if price is None or price <= 0:
            return json_error("Buy price must be above 0", 400)
        shares = None
        if not shares_blank:
            shares = to_float(raw_shares)
            if shares is None or shares <= 0:
                return json_error("Share count must be above 0", 400)
        state.buys[symbol] = {"price": price, "shares": shares}
    save_board(state.symbols, state.buys)
    logger.info("Buy for %s set to price %s, shares %s", symbol, price, shares)
    return web.json_response({"symbol": symbol, "buy": price, "shares": shares})


class BoardState:
    def __init__(self, symbols, buys, interval, page):
        self.symbols = list(symbols)
        self.buys = dict(buys)
        self.interval = interval
        self.page = page
        self.history = {symbol: [] for symbol in symbols}
        self.latest = {}
        self.close_at_start = {}
        self.subscribers = set()
        self.snapshot = None
        self.started_at = time.time()
        self.task = None


def build_app(symbols, buys, interval):
    if not PAGE_PATH.is_file():
        raise FileNotFoundError(f"Missing page template: {PAGE_PATH}")
    app = web.Application()
    app["state"] = BoardState(
        symbols,
        buys,
        interval,
        PAGE_PATH.read_text(encoding="utf-8"),
    )
    app.add_routes(
        [
            web.get("/", index),
            web.get("/api/quotes", api_quotes),
            web.post("/api/tickers", add_ticker),
            web.delete("/api/tickers/{symbol}", delete_ticker),
            web.put("/api/tickers/{symbol}/buy", set_buy),
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
    symbols, buys = load_board()
    if not symbols:
        logger.error("No symbols to collect. Exiting.")
        return 1
    app = build_app(symbols, buys, args.interval)
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
