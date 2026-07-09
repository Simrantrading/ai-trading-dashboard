"""Configuration for market news monitoring and phone alerts."""

from __future__ import annotations

# RSS feeds from top financial news platforms.
# CNN/Reuters feeds are often blocked from cloud hosts; CNBC, Bloomberg, WSJ, etc. work reliably.
NEWS_SOURCES: list[dict[str, str]] = [
    {"id": "cnbc_top", "name": "CNBC", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"id": "cnbc_markets", "name": "CNBC Markets", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html"},
    {"id": "cnbc_economy", "name": "CNBC Economy", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html"},
    {"id": "cnbc_earnings", "name": "CNBC Earnings", "url": "https://www.cnbc.com/id/15839135/device/rss/rss.html"},
    {"id": "bloomberg", "name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss"},
    {"id": "yahoo_finance", "name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    {"id": "marketwatch", "name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories/"},
    {"id": "wsj_markets", "name": "WSJ", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"},
    {"id": "seeking_alpha", "name": "Seeking Alpha", "url": "https://seekingalpha.com/market_currents.xml"},
]

# Keyword categories with scoring weights for impact filtering.
IMPACT_KEYWORDS: dict[str, list[str]] = {
    "market_macro": [
        "fed", "federal reserve", "fomc", "interest rate", "rate cut", "rate hike",
        "inflation", "cpi", "ppi", "jobs report", "nonfarm", "unemployment",
        "recession", "gdp", "treasury", "yield", "tariff", "trade war",
        "government shutdown", "debt ceiling", "stimulus", "quantitative",
    ],
    "company_event": [
        "earnings", "revenue", "profit", "guidance", "merger", "acquisition",
        "buyout", "takeover", "bankruptcy", "chapter 11", "layoff", "layoffs",
        "restructuring", "ipo", "stock split", "dividend", "buyback",
        "beats estimates", "misses estimates", "warns", "forecast",
    ],
    "regulatory": [
        "sec ", "antitrust", "doj", "fda", "subpoena", "investigation",
        "lawsuit", "settlement", "fine", "ban", "sanction",
    ],
    "sector": [
        "oil price", "crude oil", "opec", "banking crisis", "semiconductor",
        "ai chip", "pharmaceutical", "biotech", "real estate", "housing market",
        "auto industry", "airline", "defense", "energy sector", "tech sector",
        "financial sector", "health care sector",
    ],
    "market_move": [
        "s&p 500", "s&p500", "dow jones", "nasdaq", "stock market",
        "wall street", "rally", "sell-off", "selloff", "plunge", "surge",
        "crash", "record high", "record low", "circuit breaker", "halt trading",
        "trading halt", "market turmoil", "volatility", "vix",
    ],
    "breaking": [
        "breaking", "just in", "alert", "urgent", "developing",
    ],
}

CATEGORY_WEIGHTS: dict[str, int] = {
    "market_macro": 3,
    "company_event": 3,
    "regulatory": 3,
    "sector": 2,
    "market_move": 2,
    "breaking": 2,
}

NEWS_CONFIG = {
    "enabled": True,
    "min_impact_score": 3,          # minimum score to fire an alert
    "high_impact_score": 6,         # severity = high above this
    "alert_cooldown_seconds": 14400,  # 4h dedup per headline
    "max_history": 100,
    "poll_interval_market_seconds": 180,   # 3 min during market hours
    "poll_interval_closed_seconds": 900,   # 15 min when market closed
    "max_alerts_per_poll": 5,
}
