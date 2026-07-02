"""US market session detection (Eastern Time)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# US equity extended hours (NYSE/NASDAQ)
PREMARKET_OPEN = time(4, 0)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
POSTMARKET_CLOSE = time(20, 0)


class MarketSession(str, Enum):
    CLOSED = "closed"
    PREMARKET = "premarket"
    INTRADAY = "intraday"
    POSTMARKET = "postmarket"


@dataclass
class SessionInfo:
    session: str
    label: str
    is_trading: bool
    scan_interval_seconds: int
    et_time: str
    next_session: str
    next_session_at: str


def get_market_session(now: datetime | None = None) -> MarketSession:
    """Return the current US equity session."""
    now = now or datetime.now(ET)
    if now.weekday() >= 5:  # Saturday / Sunday
        return MarketSession.CLOSED

    t = now.time()
    if PREMARKET_OPEN <= t < REGULAR_OPEN:
        return MarketSession.PREMARKET
    if REGULAR_OPEN <= t < REGULAR_CLOSE:
        return MarketSession.INTRADAY
    if REGULAR_CLOSE <= t < POSTMARKET_CLOSE:
        return MarketSession.POSTMARKET
    return MarketSession.CLOSED


def _next_boundary(now: datetime) -> tuple[str, datetime]:
    """Return the next session name and its start time."""
    t = now.time()
    today = now.date()

    boundaries = [
        (PREMARKET_OPEN, MarketSession.PREMARKET.value),
        (REGULAR_OPEN, MarketSession.INTRADAY.value),
        (REGULAR_CLOSE, MarketSession.POSTMARKET.value),
    ]

    for boundary_time, session_name in boundaries:
        boundary_dt = datetime.combine(today, boundary_time, tzinfo=ET)
        if now < boundary_dt:
            return session_name, boundary_dt

    # Next trading day premarket
    days_ahead = 1
    while True:
        candidate = now + timedelta(days=days_ahead)
        if candidate.weekday() < 5:
            next_dt = datetime.combine(candidate.date(), PREMARKET_OPEN, tzinfo=ET)
            return MarketSession.PREMARKET.value, next_dt
        days_ahead += 1


def get_session_info(now: datetime | None = None) -> dict:
    """Full session metadata for API / UI."""
    now = now or datetime.now(ET)
    session = get_market_session(now)
    next_name, next_at = _next_boundary(now)

    intervals = {
        MarketSession.PREMARKET: 300,
        MarketSession.INTRADAY: 120,
        MarketSession.POSTMARKET: 300,
        MarketSession.CLOSED: 600,
    }

    labels = {
        MarketSession.PREMARKET: "Pre-Market (4:00–9:30 ET)",
        MarketSession.INTRADAY: "Intraday (9:30–16:00 ET)",
        MarketSession.POSTMARKET: "Post-Market (16:00–20:00 ET)",
        MarketSession.CLOSED: "Market Closed",
    }

    info = SessionInfo(
        session=session.value,
        label=labels[session],
        is_trading=session != MarketSession.CLOSED,
        scan_interval_seconds=intervals[session],
        et_time=now.strftime("%Y-%m-%d %H:%M:%S ET"),
        next_session=next_name,
        next_session_at=next_at.strftime("%Y-%m-%d %H:%M ET"),
    )
    return asdict(info)
