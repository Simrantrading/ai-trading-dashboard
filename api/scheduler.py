"""Background scheduler for session-aware market scans and alerts."""

from __future__ import annotations

import logging

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.alerts import get_session_config
from logic.alerts import process_buy_opportunities, process_scan_results
from logic.opportunities import scan_buy_opportunities
from logic.scanner import scan_rockets
from logic.sessions import MarketSession, get_market_session, get_session_info

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_last_scan: dict | None = None


def _run_scheduled_scan() -> None:
    global _last_scan
    session = get_market_session()
    cfg = get_session_config(session)

    logger.info("Running scheduled scan for session=%s", session.value)
    try:
        rockets = scan_rockets(
            min_pct_change=cfg.min_pct_change,
            min_volume_ratio=cfg.min_volume_ratio,
            limit=cfg.limit,
            session=session.value,
        )
        new_alerts = process_scan_results(rockets, session.value)
        buy_opps = scan_buy_opportunities(session.value)
        buy_alerts = process_buy_opportunities(buy_opps, session.value)
        _last_scan = {
            "session": session.value,
            "rockets_found": len(rockets),
            "alerts_fired": len(new_alerts),
            "buy_opportunities": len(buy_opps),
            "buy_alerts_fired": len(buy_alerts),
            "top_symbol": rockets[0]["symbol"] if rockets else None,
            "top_buy": buy_opps[0]["symbol"] if buy_opps else None,
        }
        logger.info(
            "Scan complete: %d rockets, %d alerts, %d buy opps, %d buy alerts",
            len(rockets),
            len(new_alerts),
            len(buy_opps),
            len(buy_alerts),
        )
    except Exception as exc:
        logger.exception("Scheduled scan failed: %s", exc)


def _reschedule_for_session() -> None:
    """Adjust scan interval when market session changes."""
    global _scheduler
    if _scheduler is None:
        return

    info = get_session_info()
    interval = info["scan_interval_seconds"]

    _scheduler.reschedule_job(
        "market_scan",
        trigger=IntervalTrigger(seconds=interval),
    )
    logger.info(
        "Rescheduled scan to every %ds for session=%s",
        interval,
        info["session"],
    )


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    info = get_session_info()
    _scheduler = BackgroundScheduler(timezone="America/New_York")

    _scheduler.add_job(
        _run_scheduled_scan,
        trigger=IntervalTrigger(seconds=info["scan_interval_seconds"]),
        id="market_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Re-check session boundaries every minute
    _scheduler.add_job(
        _reschedule_for_session,
        trigger=IntervalTrigger(seconds=60),
        id="session_watch",
        replace_existing=True,
    )

    # Defer first scan so the server responds to UI requests immediately
    _scheduler.add_job(
        _run_scheduled_scan,
        id="startup_scan",
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(seconds=60),
    )

    _scheduler.start()
    logger.info("Alert scheduler started (session=%s)", info["session"])
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def get_last_scan() -> dict | None:
    return _last_scan
