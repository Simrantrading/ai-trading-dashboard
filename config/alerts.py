"""Session-specific alert thresholds for daily trading."""

from __future__ import annotations

from dataclasses import dataclass

from logic.sessions import MarketSession


@dataclass(frozen=True)
class SessionAlertConfig:
    min_pct_change: float
    min_volume_ratio: float
    min_rocket_score: float
    scan_interval_seconds: int
    alert_cooldown_seconds: int
    limit: int


# Tuned for practical day-trading alerts
SESSION_CONFIG: dict[MarketSession, SessionAlertConfig] = {
    MarketSession.PREMARKET: SessionAlertConfig(
        min_pct_change=1.0,
        min_volume_ratio=0.0,
        min_rocket_score=28.0,
        scan_interval_seconds=300,
        alert_cooldown_seconds=900,
        limit=20,
    ),
    MarketSession.INTRADAY: SessionAlertConfig(
        min_pct_change=1.5,
        min_volume_ratio=1.5,
        min_rocket_score=50.0,
        scan_interval_seconds=120,
        alert_cooldown_seconds=600,
        limit=25,
    ),
    MarketSession.POSTMARKET: SessionAlertConfig(
        min_pct_change=1.0,
        min_volume_ratio=0.0,
        min_rocket_score=28.0,
        scan_interval_seconds=300,
        alert_cooldown_seconds=900,
        limit=20,
    ),
    MarketSession.CLOSED: SessionAlertConfig(
        min_pct_change=3.0,
        min_volume_ratio=1.0,
        min_rocket_score=55.0,
        scan_interval_seconds=600,
        alert_cooldown_seconds=1800,
        limit=10,
    ),
}

ALERT_CONFIG = {
    "webhook_enabled": True,
    "max_history": 200,
    "severity_thresholds": {
        "high": {"min_pct_change": 5.0, "min_rocket_score": 70.0},
        "medium": {"min_pct_change": 3.0, "min_rocket_score": 55.0},
    },
}


def get_session_config(session: MarketSession | str) -> SessionAlertConfig:
    if isinstance(session, str):
        session = MarketSession(session)
    return SESSION_CONFIG[session]
