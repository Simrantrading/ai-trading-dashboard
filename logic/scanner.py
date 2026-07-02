"""Rocket scanner: rank stocks by momentum, volume surge, and trend."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from data.acquisition import fetch_market_data, get_sp500_symbols
from logic.indicators import atr, rsi

logger = logging.getLogger(__name__)


@dataclass
class RocketResult:
    symbol: str
    price: float
    pct_change: float
    volume: float
    volume_ratio: float
    rsi: float
    atr: float
    trend_score: float
    rocket_score: float


def _extract_symbol_frame(data: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    """Normalize yfinance output into a single-symbol OHLCV frame."""
    if data.empty:
        return None

    if isinstance(data.columns, pd.MultiIndex):
        if symbol not in data.columns.get_level_values(0):
            return None
        frame = data[symbol].copy()
    else:
        frame = data.copy()

    frame = frame.dropna(how="all")
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(frame.columns):
        return None

    return frame.dropna(subset=["Close", "Volume"])


def _trend_score(closes: pd.Series, lookback: int = 10) -> float:
    """Linear-regression slope on recent closes, normalized to 0–100."""
    recent = closes.dropna().tail(lookback)
    if len(recent) < 3:
        return 50.0

    x = np.arange(len(recent)).reshape(-1, 1)
    y = recent.values.reshape(-1, 1)
    model = LinearRegression()
    model.fit(x, y)

    # Slope as % of average price per bar
    avg_price = recent.mean()
    if avg_price <= 0:
        return 50.0

    slope_pct = (model.coef_[0][0] / avg_price) * 100
    # Map roughly -2%..+2% per bar → 0..100
    return float(np.clip(50 + slope_pct * 25, 0, 100))


def _score_symbol(frame: pd.DataFrame, symbol: str) -> RocketResult | None:
    if len(frame) < 21:
        return None

    close = frame["Close"]
    high = frame["High"]
    low = frame["Low"]
    volume = frame["Volume"]

    latest_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    if prev_close <= 0 or latest_close <= 0:
        return None

    pct_change = ((latest_close - prev_close) / prev_close) * 100
    latest_volume = float(volume.iloc[-1])
    avg_volume = float(volume.iloc[-21:-1].mean())
    volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0.0

    rsi_val = float(rsi(close).iloc[-1])
    atr_val = float(atr(high, low, close).iloc[-1])
    trend = _trend_score(close)

    def _norm(value: float, low: float, high: float) -> float:
        if high <= low:
            return 50.0
        return float(np.clip((value - low) / (high - low) * 100, 0, 100))

    # Weighted rocket score (0–100) with fixed normalization ranges
    rocket_score = (
        _norm(pct_change, -5, 20) * 0.40
        + _norm(volume_ratio, 0.5, 5) * 0.30
        + trend * 0.20
        + rsi_val * 0.10
    )

    return RocketResult(
        symbol=symbol,
        price=round(latest_close, 2),
        pct_change=round(pct_change, 2),
        volume=latest_volume,
        volume_ratio=round(volume_ratio, 2),
        rsi=round(rsi_val, 1),
        atr=round(atr_val, 2),
        trend_score=round(trend, 1),
        rocket_score=round(rocket_score, 1),
    )


def scan_rockets(
    symbols: list[str] | None = None,
    min_pct_change: float = 0.0,
    min_volume_ratio: float = 1.0,
    limit: int = 25,
) -> list[dict]:
    """
    Scan a symbol universe and return ranked rocket candidates.

    Filters:
      - min_pct_change: minimum daily % change (default 0 = show all ranked)
      - min_volume_ratio: minimum volume vs 20-day average
      - limit: max results returned
    """
    universe = symbols or get_sp500_symbols()
    data = fetch_market_data(universe)

    if data.empty:
        logger.warning("No market data returned")
        return []

    results: list[RocketResult] = []
    for symbol in universe:
        frame = _extract_symbol_frame(data, symbol)
        if frame is None:
            continue
        scored = _score_symbol(frame, symbol)
        if scored is None:
            continue
        if scored.pct_change < min_pct_change:
            continue
        if scored.volume_ratio < min_volume_ratio:
            continue
        results.append(scored)

    results.sort(key=lambda r: r.rocket_score, reverse=True)
    return [asdict(r) for r in results[:limit]]
