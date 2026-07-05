"""Session-specific thresholds for buy opportunity detection."""

from __future__ import annotations

from dataclasses import dataclass

from logic.sessions import MarketSession


@dataclass(frozen=True)
class SessionOpportunityConfig:
    min_confidence: float
    min_volume_ratio: float
    alert_cooldown_seconds: int
    limit: int


SESSION_OPPORTUNITY_CONFIG: dict[MarketSession, SessionOpportunityConfig] = {
    MarketSession.PREMARKET: SessionOpportunityConfig(
        min_confidence=52.0,
        min_volume_ratio=0.0,
        alert_cooldown_seconds=1200,
        limit=15,
    ),
    MarketSession.INTRADAY: SessionOpportunityConfig(
        min_confidence=55.0,
        min_volume_ratio=1.0,
        alert_cooldown_seconds=900,
        limit=20,
    ),
    MarketSession.POSTMARKET: SessionOpportunityConfig(
        min_confidence=52.0,
        min_volume_ratio=0.0,
        alert_cooldown_seconds=1200,
        limit=15,
    ),
    MarketSession.CLOSED: SessionOpportunityConfig(
        min_confidence=58.0,
        min_volume_ratio=0.8,
        alert_cooldown_seconds=3600,
        limit=10,
    ),
}

SETUP_LABELS = {
    "oversold_bounce": "Oversold Bounce",
    "pullback_uptrend": "Pullback in Uptrend",
    "breakout_retest": "Breakout Retest",
    "momentum_continuation": "Momentum Continuation",
    "gap_recovery": "Gap Recovery",
}


def get_opportunity_config(session: MarketSession | str) -> SessionOpportunityConfig:
    if isinstance(session, str):
        session = MarketSession(session)
    return SESSION_OPPORTUNITY_CONFIG[session]
