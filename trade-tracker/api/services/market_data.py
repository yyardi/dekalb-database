"""
Market data service.

Current implementation: yfinance (free, no auth required).
IBKR path is wired in but gated behind IBKR_GATEWAY_ENABLED=true.

When IBKR gateway is ready:
1. Set IBKR_GATEWAY_ENABLED=true in env
2. Set IBKR_GATEWAY_URL to your gateway address (default https://localhost:5000)
3. The gateway must be running and authenticated via 2FA
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import yfinance as yf

import config
from models.schemas import HistoricalBar, PriceQuote

logger = logging.getLogger(__name__)

# Simple in-process TTL cache to avoid hammering yfinance
_price_cache: dict[str, tuple[float, PriceQuote]] = {}  # symbol -> (expires_at, quote)


def _cached_quote(symbol: str) -> Optional[PriceQuote]:
    entry = _price_cache.get(symbol)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def _store_quote(symbol: str, quote: PriceQuote) -> None:
    expires_at = time.time() + config.PRICE_CACHE_TTL_SECONDS
    _price_cache[symbol] = (expires_at, quote)


# ---------------------------------------------------------------------------
# yfinance implementation
# ---------------------------------------------------------------------------

def _fetch_quote_yfinance(symbol: str) -> Optional[PriceQuote]:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info  # lighter call than .info
        price = info.last_price
        prev_close = info.previous_close

        if price is None:
            logger.warning("yfinance returned no price for %s", symbol)
            return None

        change = Decimal(str(price)) - Decimal(str(prev_close)) if prev_close else None
        change_pct = (change / Decimal(str(prev_close)) * 100) if (change and prev_close) else None

        quote = PriceQuote(
            symbol=symbol,
            price=Decimal(str(round(price, 4))),
            change=round(change, 4) if change else None,
            change_pct=round(change_pct, 4) if change_pct else None,
            previous_close=Decimal(str(round(prev_close, 4))) if prev_close else None,
            source="yfinance",
            as_of=datetime.utcnow(),
        )
        _store_quote(symbol, quote)
        logger.debug("yfinance price for %s: %s", symbol, price)
        return quote

    except Exception as exc:
        logger.error("yfinance error for %s: %s", symbol, exc)
        return None


def get_historical_bars(
    symbol: str,
    start: date,
    end: date,
    interval: str = "1d",
) -> list[HistoricalBar]:
    """
    Fetch OHLCV bars via yfinance.
    interval: '1d', '1wk', '1mo'  (daily is most useful for portfolio metrics)
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
            interval=interval,
            auto_adjust=True,
        )
        if df.empty:
            logger.warning("No historical data for %s %s-%s", symbol, start, end)
            return []

        bars: list[HistoricalBar] = []
        for ts, row in df.iterrows():
            bars.append(
                HistoricalBar(
                    date=ts.date(),
                    open=Decimal(str(round(row["Open"], 4))),
                    high=Decimal(str(round(row["High"], 4))),
                    low=Decimal(str(round(row["Low"], 4))),
                    close=Decimal(str(round(row["Close"], 4))),
                    volume=int(row["Volume"]),
                )
            )
        logger.info("Fetched %d bars for %s via yfinance", len(bars), symbol)
        return bars

    except Exception as exc:
        logger.error("yfinance historical error for %s: %s", symbol, exc)
        return []


# ---------------------------------------------------------------------------
# IBKR implementation (placeholder - requires gateway running)
# ---------------------------------------------------------------------------

def _fetch_quote_ibkr(symbol: str) -> Optional[PriceQuote]:
    """
    TODO: Implement IBKR Client Portal Gateway market data lookup.

    Steps to implement:
    1. Look up the contract ID:
       GET {IBKR_GATEWAY_URL}/v1/api/trsrv/stocks?symbols={symbol}
    2. Subscribe to market data snapshot:
       GET {IBKR_GATEWAY_URL}/v1/api/iserver/marketdata/snapshot?conids={conid}&fields=31,84,86
       Field 31 = last price, 84 = bid, 86 = ask
    3. Parse response and return PriceQuote

    Auth: The gateway handles all auth. Requests go to localhost:5000.
    The gateway must be running and authenticated (2FA).
    See: https://www.interactivebrokers.com/campus/ibkr-api-page/web-api

    Rate limit: 10 requests/second global. Cache aggressively.
    """
    logger.warning(
        "IBKR gateway not enabled. Set IBKR_GATEWAY_ENABLED=true and run the gateway."
    )
    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_quote(symbol: str) -> Optional[PriceQuote]:
    """
    Get current price for a symbol.
    Uses IBKR if gateway is enabled, otherwise falls back to yfinance.
    Results are cached for PRICE_CACHE_TTL_SECONDS.
    """
    cached = _cached_quote(symbol)
    if cached:
        logger.debug("Cache hit for %s", symbol)
        return cached

    if config.IBKR_GATEWAY_ENABLED:
        quote = _fetch_quote_ibkr(symbol)
        if quote:
            return quote
        logger.warning("IBKR quote failed for %s, falling back to yfinance", symbol)

    return _fetch_quote_yfinance(symbol)


def get_spy_history(start: date, end: date) -> list[HistoricalBar]:
    """Convenience wrapper for SPY benchmark data."""
    return get_historical_bars(config.BENCHMARK_SYMBOL, start, end)
