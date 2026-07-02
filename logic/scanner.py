"""Rocket scanner: rank stocks by momentum, volume surge, and trend."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from data.acquisition import (
    fetch_daily_reference,
    fetch_extended_hours_data,
    fetch_intraday_data,
    fetch_market_data,
    get_scan_universe,
    get_sp500_symbols,
)
from logic.indicators import atr, rsi
from logic.sessions import MarketSession, get_market_session

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
    session: str = "intraday"
    change_from_open: float = 0.0


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

    return frame.dropna(subset=["Close"])


def _trend_score(closes: pd.Series, lookback: int = 10) -> float:
    """Linear-regression slope on recent closes, normalized to 0–100."""
    recent = closes.dropna().tail(lookback)
    if len(recent) < 3:
        return 50.0

    x = np.arange(len(recent)).reshape(-1, 1)
    y = recent.values.reshape(-1, 1)
    model = LinearRegression()
    model.fit(x, y)

    avg_price = recent.mean()
    if avg_price <= 0:
        return 50.0

    slope_pct = (model.coef_[0][0] / avg_price) * 100
    return float(np.clip(50 + slope_pct * 25, 0, 100))


def _norm(value: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return float(np.clip((value - low) / (high - low) * 100, 0, 100))


def _compute_rocket_score(
    pct_change: float,
    volume_ratio: float,
    trend: float,
    rsi_val: float,
) -> float:
    return (
        _norm(pct_change, -5, 20) * 0.40
        + _norm(volume_ratio, 0.5, 5) * 0.30
        + trend * 0.20
        + rsi_val * 0.10
    )


def _score_daily_frame(
    frame: pd.DataFrame,
    symbol: str,
    session: str,
    reference_close: float | None = None,
) -> RocketResult | None:
    if len(frame) < 21:
        return None

    close = frame["Close"]
    high = frame["High"]
    low = frame["Low"]
    volume = frame["Volume"]

    latest_close = float(close.iloc[-1])
    prev_close = reference_close if reference_close else float(close.iloc[-2])
    if prev_close <= 0 or latest_close <= 0:
        return None

    pct_change = ((latest_close - prev_close) / prev_close) * 100
    latest_volume = float(volume.iloc[-1]) if not volume.iloc[-1:].isna().all() else 0.0
    avg_volume = float(volume.iloc[-21:-1].mean())
    volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 0.0

    rsi_val = float(rsi(close).iloc[-1])
    atr_val = float(atr(high, low, close).iloc[-1])
    trend = _trend_score(close)
    rocket_score = _compute_rocket_score(pct_change, volume_ratio, trend, rsi_val)

    today_open = float(frame["Open"].iloc[-1]) if "Open" in frame.columns else latest_close
    change_from_open = ((latest_close - today_open) / today_open * 100) if today_open > 0 else 0.0

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
        session=session,
        change_from_open=round(change_from_open, 2),
    )


def _score_intraday_frame(
    intraday: pd.DataFrame,
    daily: pd.DataFrame,
    symbol: str,
) -> RocketResult | None:
    """Score using 5m bars for intraday momentum."""
    if len(intraday) < 10:
        return None

    close = intraday["Close"]
    high = intraday["High"]
    low = intraday["Low"]
    volume = intraday["Volume"]

    latest_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    if prev_close <= 0:
        return None

    # Change over last 5m bar
    pct_change = ((latest_close - prev_close) / prev_close) * 100

    # Also track change from today's open
    today_bars = intraday[intraday.index.date == intraday.index[-1].date()]
    today_open = float(today_bars["Open"].iloc[0]) if len(today_bars) > 0 else latest_close
    change_from_open = ((latest_close - today_open) / today_open * 100) if today_open > 0 else 0.0

    # Use broader intraday % move from open as primary signal
    pct_change = change_from_open

    # Volume: today's total vs daily average
    today_volume = float(today_bars["Volume"].sum()) if len(today_bars) > 0 else 0.0
    avg_daily_vol = 0.0
    if len(daily) >= 21:
        avg_daily_vol = float(daily["Volume"].iloc[-21:-1].mean())
    volume_ratio = today_volume / avg_daily_vol if avg_daily_vol > 0 else 0.0

    rsi_val = float(rsi(close).iloc[-1])
    atr_val = float(atr(high, low, close).iloc[-1]) if len(intraday) >= 14 else 0.0
    trend = _trend_score(close, lookback=min(20, len(close)))
    rocket_score = _compute_rocket_score(pct_change, volume_ratio, trend, rsi_val)

    return RocketResult(
        symbol=symbol,
        price=round(latest_close, 2),
        pct_change=round(pct_change, 2),
        volume=today_volume,
        volume_ratio=round(volume_ratio, 2),
        rsi=round(rsi_val, 1),
        atr=round(atr_val, 2),
        trend_score=round(trend, 1),
        rocket_score=round(rocket_score, 1),
        session=MarketSession.INTRADAY.value,
        change_from_open=round(change_from_open, 2),
    )


def _score_extended_hours(
    ext_frame: pd.DataFrame,
    daily_frame: pd.DataFrame,
    symbol: str,
    session: str,
) -> RocketResult | None:
    """Score pre/post market moves vs prior regular close."""
    if ext_frame.empty or daily_frame.empty:
        return None

    latest_close = float(ext_frame["Close"].dropna().iloc[-1])
    prev_regular_close = float(daily_frame["Close"].iloc[-1])
    if prev_regular_close <= 0 or latest_close <= 0:
        return None

    pct_change = ((latest_close - prev_regular_close) / prev_regular_close) * 100
    ext_volume = float(ext_frame["Volume"].sum())
    avg_volume = float(daily_frame["Volume"].iloc[-21:-1].mean()) if len(daily_frame) >= 21 else 0.0
    if ext_volume > 0 and avg_volume > 0:
        volume_ratio = ext_volume / avg_volume
    else:
        # yfinance often reports 0 volume for extended-hours 1m bars
        volume_ratio = 1.0

    close_series = pd.concat([daily_frame["Close"], ext_frame["Close"]])
    high_series = pd.concat([daily_frame["High"], ext_frame["High"]])
    low_series = pd.concat([daily_frame["Low"], ext_frame["Low"]])

    rsi_val = float(rsi(close_series).iloc[-1])
    atr_val = float(atr(high_series, low_series, close_series).iloc[-1])
    trend = _trend_score(close_series)
    rocket_score = _compute_rocket_score(pct_change, volume_ratio, trend, rsi_val)

    return RocketResult(
        symbol=symbol,
        price=round(latest_close, 2),
        pct_change=round(pct_change, 2),
        volume=ext_volume,
        volume_ratio=round(volume_ratio, 2),
        rsi=round(rsi_val, 1),
        atr=round(atr_val, 2),
        trend_score=round(trend, 1),
        rocket_score=round(rocket_score, 1),
        session=session,
        change_from_open=round(pct_change, 2),
    )


def scan_rockets(
    symbols: list[str] | None = None,
    min_pct_change: float = 0.0,
    min_volume_ratio: float = 1.0,
    limit: int = 25,
    session: str | None = None,
) -> list[dict]:
    """
    Scan a symbol universe and return ranked rocket candidates.
    Automatically uses session-appropriate data when session is not specified.
    """
    active_session = session or get_market_session().value
    if active_session in (MarketSession.PREMARKET.value, MarketSession.POSTMARKET.value):
        return scan_extended_hours(
            symbols=symbols,
            session=active_session,
            min_pct_change=min_pct_change,
            min_volume_ratio=min_volume_ratio,
            limit=limit,
        )
    if active_session == MarketSession.INTRADAY.value:
        return scan_intraday(
            symbols=symbols,
            min_pct_change=min_pct_change,
            min_volume_ratio=min_volume_ratio,
            limit=limit,
        )
    return scan_daily(
        symbols=symbols,
        min_pct_change=min_pct_change,
        min_volume_ratio=min_volume_ratio,
        limit=limit,
    )


def scan_daily(
    symbols: list[str] | None = None,
    min_pct_change: float = 0.0,
    min_volume_ratio: float = 1.0,
    limit: int = 25,
) -> list[dict]:
    universe = symbols or get_sp500_symbols()
    data = fetch_market_data(universe)
    if data.empty:
        return []

    results: list[RocketResult] = []
    for symbol in universe:
        frame = _extract_symbol_frame(data, symbol)
        if frame is None:
            continue
        scored = _score_daily_frame(frame, symbol, MarketSession.CLOSED.value)
        if scored is None:
            continue
        if scored.pct_change < min_pct_change or scored.volume_ratio < min_volume_ratio:
            continue
        results.append(scored)

    results.sort(key=lambda r: r.rocket_score, reverse=True)
    return [asdict(r) for r in results[:limit]]


def scan_intraday(
    symbols: list[str] | None = None,
    min_pct_change: float = 0.0,
    min_volume_ratio: float = 1.0,
    limit: int = 25,
) -> list[dict]:
    universe = symbols or get_scan_universe()
    intraday = fetch_intraday_data(universe)
    daily = fetch_daily_reference(universe)
    if intraday.empty:
        logger.warning("No intraday data; falling back to daily scan")
        return scan_daily(universe, min_pct_change, min_volume_ratio, limit)

    results: list[RocketResult] = []
    for symbol in universe:
        i_frame = _extract_symbol_frame(intraday, symbol)
        d_frame = _extract_symbol_frame(daily, symbol)
        if i_frame is None or d_frame is None:
            continue
        scored = _score_intraday_frame(i_frame, d_frame, symbol)
        if scored is None:
            continue
        if scored.pct_change < min_pct_change or scored.volume_ratio < min_volume_ratio:
            continue
        results.append(scored)

    results.sort(key=lambda r: r.rocket_score, reverse=True)
    return [asdict(r) for r in results[:limit]]


def scan_extended_hours(
    symbols: list[str] | None = None,
    session: str = MarketSession.PREMARKET.value,
    min_pct_change: float = 0.0,
    min_volume_ratio: float = 0.0,
    limit: int = 25,
) -> list[dict]:
    universe = symbols or get_scan_universe()
    ext_data = fetch_extended_hours_data(universe)
    daily_data = fetch_daily_reference(universe)
    if ext_data.empty:
        logger.warning("No extended-hours data; falling back to daily scan")
        return scan_daily(universe, min_pct_change, min_volume_ratio, limit)

    results: list[RocketResult] = []
    for symbol in universe:
        e_frame = _extract_symbol_frame(ext_data, symbol)
        d_frame = _extract_symbol_frame(daily_data, symbol)
        if e_frame is None or d_frame is None:
            continue
        scored = _score_extended_hours(e_frame, d_frame, symbol, session)
        if scored is None:
            continue
        if scored.pct_change < min_pct_change or scored.volume_ratio < min_volume_ratio:
            continue
        results.append(scored)

    results.sort(key=lambda r: r.rocket_score, reverse=True)
    return [asdict(r) for r in results[:limit]]
