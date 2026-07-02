# Market Rocket Scanner

Scan the market for stocks making sharp moves — with **automated Pre-Market, Intraday, and Post-Market alerts** to support daily trading.

## Features

### Scanner
- **Session-aware scanning** — different logic for pre-market, intraday, and post-market
- **S&P 500 universe** (falls back to a curated 100-ticker watchlist)
- **Rocket scoring** combining % change, volume surge, trend strength, and RSI
- **Standard indicators**: RSI (Wilder), ATR (Wilder)

### Alerts (new)
- **Pre-Market** (4:00–9:30 ET) — scans every 5 min for extended-hours movers
- **Intraday** (9:30–16:00 ET) — scans every 2 min using 5-minute bars
- **Post-Market** (16:00–20:00 ET) — scans every 5 min for after-hours moves
- **Browser push notifications** + optional sound alerts
- **Live SSE stream** for real-time alert delivery
- **Discord / Telegram webhooks** for phone alerts (via `.env`)

## Project Structure

```
data/           # Market data acquisition (yfinance)
logic/          # Indicators, scanner, sessions, alerts
config/         # Session-specific alert thresholds
api/            # FastAPI backend + background scheduler
ui/             # Web dashboard
run.py          # Server entry point
```

## Quick Start

```bash
pip install -r requirements.txt
python3 run.py
```

Open [http://localhost:8000](http://localhost:8000) → click **Enable Push** for browser notifications.

### Phone alerts (optional)

Copy `.env.example` to `.env` and add:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
# or
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Session Alert Thresholds

| Session | Scan Interval | Min % Change | Min Vol Ratio | Min Score |
|---------|---------------|--------------|---------------|-----------|
| Pre-Market | 5 min | 2.0% | 0.3x | 45 |
| Intraday | 2 min | 1.5% | 1.5x | 50 |
| Post-Market | 5 min | 2.0% | 0.3x | 45 |

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/session` | Current market session + thresholds |
| `GET /api/rockets` | Run a scan (session-aware) |
| `GET /api/alerts` | Alert history |
| `POST /api/alerts/scan` | Manually trigger scan + fire alerts |
| `GET /api/alerts/stream` | SSE real-time alert stream |
| `GET /api/scheduler/status` | Background scheduler status |

## Rocket Score

| Factor | Weight |
|--------|--------|
| % Change | 40% |
| Volume Ratio | 30% |
| Trend Score | 20% |
| RSI | 10% |

## Data Source

Market data via [yfinance](https://github.com/ranaroussi/yfinance). No API key required.

## Legacy Demo

The original single-symbol Alpha Vantage demo is at `ai-trading-demo.html`.

## iPhone Only (No Mac)

See **[PHONE_SETUP.md](PHONE_SETUP.md)** for cloud deploy + Telegram alerts + Add to Home Screen.
