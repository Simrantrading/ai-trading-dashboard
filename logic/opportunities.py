"""Buy opportunity scanner: detect actionable long setups with reasons and expectations."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from config.opportunities import SETUP_LABELS, get_opportunity_config
from data.acquisition import (
    fetch_daily_reference,
    fetch_extended_hours_data,
    fetch_intraday_data,
    fetch_market_data,
    get_scan_universe,
    get_sp500_symbols,
)
from logic.scanner import (
    RocketResult,
    _extract_symbol_frame,
    _score_daily_frame,
    _score_extended_hours,
    _score_intraday_frame,
)
from logic.sessions import MarketSession, get_market_session

logger = logging.getLogger(__name__)


@dataclass
class BuyOpportunity:
    symbol: str
    price: float
    setup_type: str
    setup_label: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    expectations: dict = field(default_factory=dict)
    rsi: float = 0.0
    atr: float = 0.0
    trend_score: float = 0.0
    volume_ratio: float = 0.0
    pct_change: float = 0.0
    session: str = "intraday"


def _compute_expectations(price: float, atr: float, setup_type: str, session: str) -> dict:
    """ATR-based entry, stop, and target levels for a long setup."""
    if atr <= 0:
        atr = price * 0.02

    stop_mult = {"oversold_bounce": 1.5, "pullback_uptrend": 1.2, "breakout_retest": 1.0}.get(
        setup_type, 1.3
    )
    target_mult = {"oversold_bounce": 2.5, "pullback_uptrend": 2.0, "breakout_retest": 3.0}.get(
        setup_type, 2.5
    )
    if setup_type == "momentum_continuation":
        stop_mult, target_mult = 1.0, 2.0
    if setup_type == "gap_recovery":
        stop_mult, target_mult = 1.5, 3.0

    entry = round(price, 2)
    stop = round(price - stop_mult * atr, 2)
    target = round(price + target_mult * atr, 2)
    risk = entry - stop
    reward = target - entry
    rr = round(reward / risk, 1) if risk > 0 else 0.0

    timeframe = {
        MarketSession.INTRADAY.value: "Intraday (same session)",
        MarketSession.PREMARKET.value: "Pre-market → regular open",
        MarketSession.POSTMARKET.value: "Next regular session",
        MarketSession.CLOSED.value: "Swing (1–3 trading days)",
    }.get(session, "1–2 sessions")

    return {
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_reward": rr,
        "timeframe": timeframe,
        "atr": round(atr, 2),
    }


def _evaluate_buy_setup(result: RocketResult) -> BuyOpportunity | None:
    """Score a symbol for buy-side setups. Returns None if no valid setup."""
    rsi = result.rsi
    trend = result.trend_score
    pct = result.pct_change
    vol = result.volume_ratio
    price = result.price
    atr = result.atr
    change_open = result.change_from_open

    candidates: list[tuple[str, float, list[str]]] = []

    # Oversold bounce: RSI low but trend not broken
    if rsi <= 35 and trend >= 38:
        score = 28.0
        reasons = [f"RSI oversold at {rsi:.0f} — historically a reversal zone"]
        if pct >= -1.5:
            score += 12
            reasons.append(f"Price stabilizing ({pct:+.1f}% move, not falling knife)")
        if vol >= 1.2:
            score += 10
            reasons.append(f"Volume {vol:.1f}x average — buyers stepping in")
        if trend >= 50:
            score += 8
            reasons.append(f"Broader trend still intact (score {trend:.0f})")
        candidates.append(("oversold_bounce", score, reasons))

    # Pullback in uptrend: dip to buy
    if trend >= 58 and -3.5 <= pct <= 0.8:
        score = 30.0
        reasons = [
            f"Strong uptrend (trend score {trend:.0f})",
            f"Pullback of {pct:+.1f}% — potential buy-the-dip zone",
        ]
        if 35 <= rsi <= 55:
            score += 12
            reasons.append(f"RSI cooled to {rsi:.0f} — not overbought")
        if vol >= 1.0:
            score += 8
            reasons.append(f"Volume {vol:.1f}x — participation on the dip")
        candidates.append(("pullback_uptrend", score, reasons))

    # Breakout retest: moved up, pulled back to support
    if trend >= 55 and 0.5 <= change_open <= 4.0 and -2.0 <= pct <= 1.0:
        score = 26.0
        reasons = [
            f"Up {change_open:+.1f}% from open — breakout in progress",
            f"Retesting after {pct:+.1f}% pullback — classic entry zone",
        ]
        if vol >= 1.3:
            score += 12
            reasons.append(f"Elevated volume ({vol:.1f}x) confirms interest")
        if 45 <= rsi <= 65:
            score += 8
            reasons.append(f"RSI {rsi:.0f} — momentum without extreme overbought")
        candidates.append(("breakout_retest", score, reasons))

    # Momentum continuation: riding the trend
    if trend >= 65 and 1.5 <= pct <= 8.0 and 50 <= rsi <= 72:
        score = 25.0
        reasons = [
            f"Strong momentum (trend {trend:.0f}, +{pct:.1f}% today)",
            f"RSI {rsi:.0f} — bullish but not exhausted",
        ]
        if vol >= 1.5:
            score += 15
            reasons.append(f"Volume surge {vol:.1f}x — institutional participation likely")
        candidates.append(("momentum_continuation", score, reasons))

    # Gap recovery (pre/post market): gap down recovering
    if result.session in (MarketSession.PREMARKET.value, MarketSession.POSTMARKET.value):
        if -6.0 <= pct <= -1.5 and rsi <= 42:
            score = 24.0
            reasons = [
                f"Extended-hours gap down {pct:+.1f}%",
                f"RSI {rsi:.0f} — selling may be overdone",
            ]
            if trend >= 45:
                score += 10
                reasons.append("Daily trend still supportive")
            candidates.append(("gap_recovery", score, reasons))

    if not candidates:
        return None

    best_type, best_score, reasons = max(candidates, key=lambda x: x[1])

    if vol >= 1.5 and not any("Volume" in r for r in reasons):
        best_score += 8
        reasons.append(f"Volume {vol:.1f}x average — above-normal interest")

    confidence = min(round(best_score, 1), 95.0)
    if confidence < 45 or len(reasons) < 2:
        return None

    expectations = _compute_expectations(price, atr, best_type, result.session)

    return BuyOpportunity(
        symbol=result.symbol,
        price=price,
        setup_type=best_type,
        setup_label=SETUP_LABELS.get(best_type, best_type.replace("_", " ").title()),
        confidence=confidence,
        reasons=reasons[:5],
        expectations=expectations,
        rsi=result.rsi,
        atr=result.atr,
        trend_score=result.trend_score,
        volume_ratio=result.volume_ratio,
        pct_change=result.pct_change,
        session=result.session,
    )


def _scan_all_scored(session: str | None = None) -> list[RocketResult]:
    """Score every symbol in the universe — not limited to top rocket movers."""
    active = session or get_market_session().value
    results: list[RocketResult] = []

    if active in (MarketSession.PREMARKET.value, MarketSession.POSTMARKET.value):
        universe = get_scan_universe()
        ext_data = fetch_extended_hours_data(universe)
        daily_data = fetch_daily_reference(universe)
        for symbol in universe:
            e_frame = _extract_symbol_frame(ext_data, symbol)
            d_frame = _extract_symbol_frame(daily_data, symbol)
            if e_frame is None or d_frame is None:
                continue
            scored = _score_extended_hours(e_frame, d_frame, symbol, active)
            if scored:
                results.append(scored)
    elif active == MarketSession.INTRADAY.value:
        universe = get_scan_universe()
        intraday = fetch_intraday_data(universe)
        daily = fetch_daily_reference(universe)
        for symbol in universe:
            i_frame = _extract_symbol_frame(intraday, symbol)
            d_frame = _extract_symbol_frame(daily, symbol)
            if i_frame is None or d_frame is None:
                continue
            scored = _score_intraday_frame(i_frame, d_frame, symbol)
            if scored:
                results.append(scored)
    else:
        universe = get_sp500_symbols()
        data = fetch_market_data(universe)
        for symbol in universe:
            frame = _extract_symbol_frame(data, symbol)
            if frame is None:
                continue
            scored = _score_daily_frame(frame, symbol, MarketSession.CLOSED.value)
            if scored:
                results.append(scored)

    return results


def scan_buy_opportunities(
    session: str | None = None,
    min_confidence: float | None = None,
    min_volume_ratio: float | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    Scan the universe for actionable buy setups.
    Returns ranked opportunities with reasons and price expectations.
    """
    active = session or get_market_session().value
    cfg = get_opportunity_config(active)
    min_conf = min_confidence if min_confidence is not None else cfg.min_confidence
    min_vol = min_volume_ratio if min_volume_ratio is not None else cfg.min_volume_ratio
    max_results = limit if limit is not None else cfg.limit

    try:
        scored = _scan_all_scored(active)
    except Exception as exc:
        logger.exception("Buy opportunity scan failed: %s", exc)
        return []

    opportunities: list[BuyOpportunity] = []
    for result in scored:
        if result.volume_ratio < min_vol:
            continue
        opp = _evaluate_buy_setup(result)
        if opp is None or opp.confidence < min_conf:
            continue
        opportunities.append(opp)

    opportunities.sort(key=lambda o: o.confidence, reverse=True)
    return [asdict(o) for o in opportunities[:max_results]]
