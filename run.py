#!/usr/bin/env python3
"""Run the Market Rocket Scanner server."""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("ENV", "development") == "development"
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=reload)
