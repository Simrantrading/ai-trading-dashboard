"""FastAPI backend for the Market Rocket Scanner."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from logic.scanner import scan_rockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

app = FastAPI(
    title="Market Rocket Scanner",
    description="Scan for stocks with sharp price moves, volume surges, and momentum.",
    version="1.0.0",
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
    return {"status": "ok"}


@app.get("/api/rockets")
async def get_rockets(
    min_change: float = Query(0.0, description="Minimum daily % change"),
    min_volume_ratio: float = Query(1.0, description="Minimum volume vs 20-day avg"),
    limit: int = Query(25, ge=1, le=100, description="Max results"),
):
    logger.info(
        "Scan requested: min_change=%.1f min_vol=%.1f limit=%d",
        min_change,
        min_volume_ratio,
        limit,
    )
    rockets = scan_rockets(
        min_pct_change=min_change,
        min_volume_ratio=min_volume_ratio,
        limit=limit,
    )
    return {
        "count": len(rockets),
        "filters": {
            "min_change": min_change,
            "min_volume_ratio": min_volume_ratio,
            "limit": limit,
        },
        "rockets": rockets,
    }
