"""Portfolio analysis and add-suggestions based on trend scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from data.acquisition import DEFAULT_WATCHLIST, FULL_WATCHLIST, fetch_market_data
from logic.indicators import atr, rsi
from logic.scanner import _extract_symbol_frame

# Default book from the user's Prime Account snapshot (USD market values).
DEFAULT_HOLDINGS = {
    "SOXL": 8936.95,
    "INTC": 1560.50,
    "AUR": 613.00,
    "SKHHY": 955.50,
    "SLS": 107.68,
    "MRVL": 2272.50,
    "SOXS": 422.50,
    "CRE": 158.50,
    "NASA": 1017.60,
    "SPCX": 2064.60,
}

THEME_MAP = {
    "semiconductor": {
        "SOXL", "SOXS", "INTC", "MRVL", "SKHHY", "NVDA", "AMD", "AVGO",
        "QCOM", "AMAT", "MU", "LRCX", "TXN", "ARM", "TSM", "ASML", "SMCI",
    },
    "space": {"NASA", "SPCX", "RKLB", "BA", "LMT", "RTX", "GE", "ASTS", "LUNR"},
    "ev_auto": {"TSLA", "RIVN", "NIO", "AUR"},
    "biotech": {"SLS", "LLY", "JNJ", "PFE", "UNH"},
    "fintech": {"COIN", "HOOD", "SOFI", "PYPL", "JPM", "BAC", "GS"},
    "mega_tech": {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX", "CRM", "ORCL"},
    "crypto_proxy": {"COIN", "MSTR", "MARA", "RIOT"},
    "cyber": {"CRWD", "PANW", "NET", "ZS", "FTNT", "SNOW", "DDOG"},
    "travel": {"AAL", "UAL", "DAL", "CCL", "RCL", "ABNB", "LYFT", "UBER"},
}

LEVERAGED = {"SOXL", "SOXS", "TQQQ", "SQQQ", "UPRO", "SPXU", "TECL", "TECS"}

CANDIDATE_UNIVERSE = sorted(
    set(DEFAULT_WATCHLIST + FULL_WATCHLIST + ["TSM", "ASML", "ASTS", "LUNR", "SMH", "XLK", "SPY", "QQQ"])
)


@dataclass
class HoldingScore:
    symbol: str
    market_value: float
    weight_pct: float
    price: float
    ret_1m: float
    ret_3m: float
    rsi: float
    atr_pct: float
    trend_score: float
    theme: str
    note: str


@dataclass
class AddSuggestion:
    symbol: str
    price: float
    ret_1m: float
    ret_3m: float
    rsi: float
    atr_pct: float
    trend_score: float
    add_score: float
    theme: str
    rationale: str


def _theme_for(symbol: str) -> str:
    for theme, members in THEME_MAP.items():
        if symbol in members:
            return theme
    return "other"


def _trend_score(closes: pd.Series, lookback: int = 20) -> float:
    recent = closes.dropna().tail(lookback)
    if len(recent) < 5:
        return 50.0
    x = np.arange(len(recent)).reshape(-1, 1)
    y = recent.values.reshape(-1, 1)
    model = LinearRegression().fit(x, y)
    avg = float(recent.mean())
    if avg <= 0:
        return 50.0
    slope_pct = (model.coef_[0][0] / avg) * 100
    return float(np.clip(50 + slope_pct * 30, 0, 100))


def _period_return(closes: pd.Series, bars: int) -> float:
    if len(closes) < bars + 1:
        return float("nan")
    start = float(closes.iloc[-(bars + 1)])
    end = float(closes.iloc[-1])
    if start <= 0:
        return float("nan")
    return ((end - start) / start) * 100


def _score_frame(frame: pd.DataFrame) -> dict | None:
    if frame is None or len(frame) < 21:
        return None
    close = frame["Close"]
    high = frame["High"]
    low = frame["Low"]
    latest = float(close.iloc[-1])
    if latest <= 0:
        return None
    atr_val = float(atr(high, low, close).iloc[-1])
    rsi_val = float(rsi(close).iloc[-1])
    return {
        "price": round(latest, 2),
        "ret_1m": round(_period_return(close, 21), 2),
        "ret_3m": round(_period_return(close, min(63, len(close) - 1)), 2),
        "rsi": round(rsi_val, 1),
        "atr_pct": round((atr_val / latest) * 100, 2),
        "trend_score": round(_trend_score(close), 1),
    }


def _holding_note(symbol: str, metrics: dict, weight_pct: float) -> str:
    notes: list[str] = []
    if symbol in LEVERAGED:
        notes.append("3x leveraged — decay risk if held long")
    if weight_pct >= 25:
        notes.append(f"concentrated ({weight_pct:.0f}% of book)")
    if metrics["rsi"] >= 70:
        notes.append("overbought RSI")
    elif metrics["rsi"] <= 30:
        notes.append("oversold RSI")
    if metrics["trend_score"] < 40:
        notes.append("weak short-term trend")
    elif metrics["trend_score"] > 65:
        notes.append("strong short-term trend")
    return "; ".join(notes) if notes else "neutral"


def analyze_holdings(holdings: dict[str, float] | None = None) -> dict:
    book = holdings or DEFAULT_HOLDINGS
    total = sum(book.values()) or 1.0
    symbols = list(book.keys())
    data = fetch_market_data(symbols, period="6mo")

    scored: list[HoldingScore] = []
    theme_weights: dict[str, float] = {}
    for symbol, value in book.items():
        weight = (value / total) * 100
        frame = _extract_symbol_frame(data, symbol)
        metrics = _score_frame(frame) if frame is not None else None
        theme = _theme_for(symbol)
        theme_weights[theme] = theme_weights.get(theme, 0.0) + weight
        if metrics is None:
            scored.append(
                HoldingScore(
                    symbol=symbol,
                    market_value=round(value, 2),
                    weight_pct=round(weight, 2),
                    price=0.0,
                    ret_1m=float("nan"),
                    ret_3m=float("nan"),
                    rsi=50.0,
                    atr_pct=0.0,
                    trend_score=50.0,
                    theme=theme,
                    note="insufficient data",
                )
            )
            continue
        scored.append(
            HoldingScore(
                symbol=symbol,
                market_value=round(value, 2),
                weight_pct=round(weight, 2),
                price=metrics["price"],
                ret_1m=metrics["ret_1m"],
                ret_3m=metrics["ret_3m"],
                rsi=metrics["rsi"],
                atr_pct=metrics["atr_pct"],
                trend_score=metrics["trend_score"],
                theme=theme,
                note=_holding_note(symbol, metrics, weight),
            )
        )

    scored.sort(key=lambda h: h.weight_pct, reverse=True)
    risks: list[str] = []
    semi_w = theme_weights.get("semiconductor", 0.0)
    space_w = theme_weights.get("space", 0.0)
    if semi_w >= 50:
        risks.append(f"Semiconductor exposure is {semi_w:.0f}% — too concentrated.")
    if "SOXL" in book and "SOXS" in book:
        risks.append("Both SOXL and SOXS held — net bullish but paying double decay.")
    if space_w >= 15:
        risks.append(f"Space names are {space_w:.0f}% and recently deep red — review cutoffs.")
    leveraged_w = sum(h.weight_pct for h in scored if h.symbol in LEVERAGED)
    if leveraged_w >= 30:
        risks.append(f"Leveraged ETFs are {leveraged_w:.0f}% of book — volatility drag risk.")

    return {
        "total_value": round(total, 2),
        "holdings": [asdict(h) for h in scored],
        "theme_weights": {k: round(v, 2) for k, v in sorted(theme_weights.items(), key=lambda x: -x[1])},
        "risks": risks,
    }


def suggest_additions(
    holdings: dict[str, float] | None = None,
    limit: int = 5,
) -> dict:
    book = holdings or DEFAULT_HOLDINGS
    analysis = analyze_holdings(book)
    held = set(book.keys())
    theme_weights = analysis["theme_weights"]
    dominant = max(theme_weights, key=theme_weights.get) if theme_weights else "other"

    candidates = [s for s in CANDIDATE_UNIVERSE if s not in held and s not in LEVERAGED]
    data = fetch_market_data(candidates, period="6mo")

    suggestions: list[AddSuggestion] = []
    for symbol in candidates:
        frame = _extract_symbol_frame(data, symbol)
        metrics = _score_frame(frame)
        if metrics is None:
            continue
        if np.isnan(metrics["ret_1m"]) or np.isnan(metrics["ret_3m"]):
            continue
        # Prefer constructive trend, not extreme overbought, and reasonable vol
        if metrics["trend_score"] < 52 or metrics["rsi"] > 75 or metrics["rsi"] < 25:
            continue

        theme = _theme_for(symbol)
        diversify_bonus = 18.0 if theme != dominant and theme_weights.get(theme, 0) < 15 else 0.0
        quality_bonus = 10.0 if theme in {"mega_tech", "cyber", "semiconductor"} else 0.0
        momentum = (
            np.clip(metrics["ret_1m"], -20, 40) * 0.8
            + np.clip(metrics["ret_3m"], -30, 60) * 0.4
            + metrics["trend_score"] * 0.5
            + (70 - abs(metrics["rsi"] - 55)) * 0.3
        )
        vol_penalty = max(0.0, metrics["atr_pct"] - 4.0) * 2.5
        add_score = float(momentum + diversify_bonus + quality_bonus - vol_penalty)

        if theme == dominant and theme_weights.get(theme, 0) > 45:
            rationale = f"Strong {theme} momentum, but keep size small — theme already heavy."
            add_score -= 8.0
        elif diversify_bonus > 0:
            rationale = f"Diversifies away from {dominant} into {theme} with constructive trend."
        else:
            rationale = f"Constructive trend in {theme}; fits existing book without leverage."

        suggestions.append(
            AddSuggestion(
                symbol=symbol,
                price=metrics["price"],
                ret_1m=metrics["ret_1m"],
                ret_3m=metrics["ret_3m"],
                rsi=metrics["rsi"],
                atr_pct=metrics["atr_pct"],
                trend_score=metrics["trend_score"],
                add_score=round(add_score, 1),
                theme=theme,
                rationale=rationale,
            )
        )

    suggestions.sort(key=lambda s: s.add_score, reverse=True)

    # Prefer theme diversity in the top list (max 2 per theme).
    top: list[AddSuggestion] = []
    theme_counts: dict[str, int] = {}
    for item in suggestions:
        if theme_counts.get(item.theme, 0) >= 2:
            continue
        top.append(item)
        theme_counts[item.theme] = theme_counts.get(item.theme, 0) + 1
        if len(top) >= limit:
            break
    if len(top) < limit:
        for item in suggestions:
            if item in top:
                continue
            top.append(item)
            if len(top) >= limit:
                break

    actions = [
        "Avoid adding more leveraged semiconductor exposure (SOXL already dominates).",
        "Prefer 1–2 unlevered liquid names for diversification or cleaner theme expression.",
    ]
    if top:
        actions.append(
            f"Top add candidates: {', '.join(s.symbol for s in top)}."
        )

    def _clean(obj):
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        return obj

    return _clean(
        {
            **analysis,
            "suggestions": [asdict(s) for s in top],
            "actions": actions,
        }
    )
