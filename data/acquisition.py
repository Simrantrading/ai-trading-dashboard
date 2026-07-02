"""Market data acquisition via yfinance."""

from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Fallback watchlist when Wikipedia / network is unavailable
DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "NFLX",
    "CRM", "AVGO", "ORCL", "ADBE", "INTC", "QCOM", "TXN", "AMAT", "MU", "LRCX",
    "COIN", "MARA", "RIOT", "PLTR", "SOFI", "HOOD", "RIVN", "LCID", "NIO", "XPEV",
    "SMCI", "ARM", "IONQ", "RKLB", "GME", "AMC", "BBBY", "MSTR", "PYPL",
    "UBER", "LYFT", "ABNB", "SNAP", "PINS", "ROKU", "SHOP", "CRWD", "NET", "DDOG",
    "SNOW", "ZS", "PANW", "FTNT", "DKNG", "PENN", "WYNN", "MGM", "LVS", "CCL",
    "RCL", "DAL", "UAL", "AAL", "BA", "LMT", "RTX", "GE", "CAT", "DE",
    "JPM", "BAC", "GS", "MS", "WFC", "C", "V", "MA", "AXP", "BLK",
    "XOM", "CVX", "COP", "SLB", "OXY", "EOG", "MPC", "VLO", "PSX", "HAL",
    "LLY", "UNH", "JNJ", "PFE", "MRK", "ABBV", "BMY", "AMGN", "GILD", "REGN",
]


@lru_cache(maxsize=1)
def get_sp500_symbols() -> list[str]:
    """Return S&P 500 tickers; falls back to a curated watchlist on failure."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        symbols = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
        if symbols:
            logger.info("Loaded %d S&P 500 symbols", len(symbols))
            return symbols
    except Exception as exc:
        logger.warning("Could not load S&P 500 list: %s", exc)

    logger.info("Using default watchlist (%d symbols)", len(DEFAULT_WATCHLIST))
    return DEFAULT_WATCHLIST.copy()


def fetch_market_data(
    symbols: list[str] | None = None,
    period: str = "1mo",
) -> pd.DataFrame:
    """
    Download OHLCV history for the given symbols.

    Returns a MultiIndex DataFrame: (symbol, field) columns when multiple
    symbols are requested, or a flat OHLCV frame for a single symbol.
    """
    tickers = symbols or get_sp500_symbols()
    if not tickers:
        return pd.DataFrame()

    logger.info("Fetching market data for %d symbols (period=%s)", len(tickers), period)
    raw = yf.download(
        tickers,
        period=period,
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    if raw.empty:
        return pd.DataFrame()

    return raw
