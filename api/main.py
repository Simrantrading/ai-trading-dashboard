"""FastAPI backend for the Market Rocket Scanner."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api.scheduler import get_last_scan, start_scheduler, stop_scheduler
from config.alerts import get_session_config
from config.opportunities import get_opportunity_config
from logic.alerts import alert_store, process_buy_opportunities, process_scan_results
from logic.opportunities import scan_buy_opportunities
from logic.scanner import scan_rockets
from logic.sessions import get_market_session, get_session_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Market Rocket Scanner",
    description="Scan for stocks with sharp price moves, volume surges, and momentum.",
    version="2.0.0",
    lifespan=lifespan,
)

if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


@app.get("/")
async def root():
    index = UI_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Market Rocket Scanner API", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "ready": True}


@app.get("/api/ping")
async def ping():
    """Instant response — use to wake free-tier server before scanning."""
    return {"status": "ok"}


@app.get("/api/wake")
async def wake():
    """
    Lightweight endpoint for external cron (free-tier hosting).
    Wakes the server, runs a scan, and fires alerts to Telegram/Discord.
    """
    session = get_market_session().value
    cfg = get_session_config(session)
    rockets = await asyncio.to_thread(
        scan_rockets,
        min_pct_change=cfg.min_pct_change,
        min_volume_ratio=cfg.min_volume_ratio,
        limit=cfg.limit,
        session=session,
    )
    new_alerts = await asyncio.to_thread(process_scan_results, rockets, session)
    buy_opps = await asyncio.to_thread(scan_buy_opportunities, session)
    buy_alerts = await asyncio.to_thread(process_buy_opportunities, buy_opps, session)
    return {
        "status": "ok",
        "session": session,
        "rockets_found": len(rockets),
        "alerts_fired": len(new_alerts),
        "buy_opportunities": len(buy_opps),
        "buy_alerts_fired": len(buy_alerts),
    }


@app.get("/api/session")
async def session():
    info = get_session_info()
    cfg = get_session_config(info["session"])
    opp_cfg = get_opportunity_config(info["session"])
    return {
        **info,
        "alert_thresholds": {
            "min_pct_change": cfg.min_pct_change,
            "min_volume_ratio": cfg.min_volume_ratio,
            "min_rocket_score": cfg.min_rocket_score,
            "scan_interval_seconds": cfg.scan_interval_seconds,
        },
        "buy_thresholds": {
            "min_confidence": opp_cfg.min_confidence,
            "min_volume_ratio": opp_cfg.min_volume_ratio,
        },
    }


@app.get("/api/rockets")
async def get_rockets(
    min_change: float | None = Query(None, description="Minimum daily % change"),
    min_volume_ratio: float | None = Query(None, description="Minimum volume vs avg"),
    limit: int = Query(25, ge=1, le=100, description="Max results"),
    session: str | None = Query(None, description="Force session: premarket/intraday/postmarket"),
):
    active = session or get_market_session().value
    cfg = get_session_config(active)

    rockets = await asyncio.to_thread(
        scan_rockets,
        min_pct_change=min_change if min_change is not None else cfg.min_pct_change,
        min_volume_ratio=min_volume_ratio if min_volume_ratio is not None else cfg.min_volume_ratio,
        limit=limit,
        session=active,
    )
    return {
        "count": len(rockets),
        "session": active,
        "filters": {
            "min_change": min_change if min_change is not None else cfg.min_pct_change,
            "min_volume_ratio": min_volume_ratio if min_volume_ratio is not None else cfg.min_volume_ratio,
            "limit": limit,
        },
        "rockets": rockets,
    }


@app.get("/api/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=200),
    session: str | None = Query(None),
):
    return {
        "count": len(alert_store.list_alerts(limit=limit, session=session)),
        "alerts": alert_store.list_alerts(limit=limit, session=session),
    }


@app.post("/api/alerts/scan")
async def trigger_scan():
    """Manually trigger a scan and fire alerts."""
    session = get_market_session().value
    cfg = get_session_config(session)
    rockets = await asyncio.to_thread(
        scan_rockets,
        min_pct_change=cfg.min_pct_change,
        min_volume_ratio=cfg.min_volume_ratio,
        limit=cfg.limit,
        session=session,
    )
    new_alerts = await asyncio.to_thread(process_scan_results, rockets, session)
    buy_opps = await asyncio.to_thread(scan_buy_opportunities, session)
    buy_alerts = await asyncio.to_thread(process_buy_opportunities, buy_opps, session)
    return {
        "session": session,
        "rockets_found": len(rockets),
        "alerts_fired": len(new_alerts),
        "new_alerts": new_alerts,
        "buy_opportunities": len(buy_opps),
        "buy_alerts_fired": len(buy_alerts),
        "new_buy_alerts": buy_alerts,
        "rockets": rockets[:10],
        "opportunities": buy_opps[:10],
    }


@app.get("/api/opportunities")
async def get_opportunities(
    min_confidence: float | None = Query(None, description="Minimum confidence score"),
    min_volume_ratio: float | None = Query(None, description="Minimum volume vs avg"),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
    session: str | None = Query(None, description="Force session"),
):
    active = session or get_market_session().value
    cfg = get_opportunity_config(active)

    opportunities = await asyncio.to_thread(
        scan_buy_opportunities,
        session=active,
        min_confidence=min_confidence if min_confidence is not None else cfg.min_confidence,
        min_volume_ratio=min_volume_ratio if min_volume_ratio is not None else cfg.min_volume_ratio,
        limit=limit,
    )
    return {
        "count": len(opportunities),
        "session": active,
        "filters": {
            "min_confidence": min_confidence if min_confidence is not None else cfg.min_confidence,
            "min_volume_ratio": min_volume_ratio if min_volume_ratio is not None else cfg.min_volume_ratio,
            "limit": limit,
        },
        "opportunities": opportunities,
    }


@app.post("/api/opportunities/scan")
async def trigger_opportunity_scan():
    """Scan for buy opportunities and fire alerts."""
    session = get_market_session().value
    opportunities = await asyncio.to_thread(scan_buy_opportunities, session)
    buy_alerts = await asyncio.to_thread(process_buy_opportunities, opportunities, session)
    return {
        "session": session,
        "opportunities_found": len(opportunities),
        "buy_alerts_fired": len(buy_alerts),
        "new_buy_alerts": buy_alerts,
        "opportunities": opportunities,
    }


@app.get("/api/alerts/stream")
async def alert_stream():
    """Server-Sent Events stream for real-time alert delivery."""

    async def event_generator():
        last_id: str | None = None
        while True:
            new_alerts = alert_store.get_since(last_id)
            for alert in new_alerts:
                last_id = alert["id"]
                yield f"data: {json.dumps(alert)}\n\n"
            session_info = get_session_info()
            yield f"event: heartbeat\ndata: {json.dumps(session_info)}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/scheduler/status")
async def scheduler_status():
    return {
        "session": get_session_info(),
        "last_scan": get_last_scan(),
    }
