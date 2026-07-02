# Market Rocket Scanner

Scan the market for stocks making sharp moves — high % gains, volume surges, and strong momentum trends.

## Features

- **S&P 500 universe** (falls back to a curated watchlist if unavailable)
- **Rocket scoring** combining:
  - Daily % price change
  - Volume vs 20-day average
  - Linear-regression trend strength (scikit-learn)
  - RSI momentum
- **Standard indicators**: RSI (Wilder), ATR (Wilder)
- **Web dashboard** with filters and 60-second auto-refresh
- **REST API** via FastAPI

## Project Structure

```
data/           # Market data acquisition (yfinance)
logic/          # Indicators + rocket scanner engine
api/            # FastAPI backend
ui/             # Web dashboard
run.py          # Server entry point
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python run.py
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## API

### `GET /api/rockets`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_change` | `0` | Minimum daily % change |
| `min_volume_ratio` | `1.0` | Minimum volume vs 20-day average |
| `limit` | `25` | Max results (1–100) |

Example:

```bash
curl "http://localhost:8000/api/rockets?min_change=3&min_volume_ratio=1.5&limit=10"
```

### `GET /api/health`

Health check endpoint.

## Rocket Score

Each stock is scored 0–100 using weighted factors:

| Factor | Weight |
|--------|--------|
| % Change | 40% |
| Volume Ratio | 30% |
| Trend Score | 20% |
| RSI | 10% |

## Data Source

Market data is fetched via [yfinance](https://github.com/ranaroussi/yfinance). No API key required.

## Legacy Demo

The original single-symbol Alpha Vantage demo is still available at `ai-trading-demo.html`.
