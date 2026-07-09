"""Market news alert engine: RSS monitoring with impact scoring and phone delivery."""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from config.news import CATEGORY_WEIGHTS, IMPACT_KEYWORDS, NEWS_CONFIG
from data.news import NewsArticle, fetch_all_news
from logic.webhooks import send_phone_alert

logger = logging.getLogger(__name__)

NEWS_ALERTS_FILE = Path(__file__).resolve().parent.parent / "data" / "news_alerts_history.json"


@dataclass
class NewsAlert:
    id: str
    title: str
    summary: str
    url: str
    source: str
    severity: str
    impact_score: int
    matched_categories: list[str]
    matched_keywords: list[str]
    timestamp: str
    meta: dict[str, Any] = field(default_factory=dict)


class NewsAlertStore:
    """Thread-safe store for news alerts with deduplication."""

    def __init__(self, max_history: int = 100) -> None:
        self._alerts: list[NewsAlert] = []
        self._seen: dict[str, float] = {}
        self._lock = Lock()
        self._max_history = max_history
        self._load()

    def _load(self) -> None:
        if not NEWS_ALERTS_FILE.exists():
            return
        try:
            raw = json.loads(NEWS_ALERTS_FILE.read_text())
            for item in raw[-self._max_history :]:
                self._alerts.append(NewsAlert(**item))
                self._seen[item["url"] or item["title"]] = datetime.now(timezone.utc).timestamp()
        except Exception as exc:
            logger.warning("Could not load news alert history: %s", exc)

    def _persist(self) -> None:
        try:
            NEWS_ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = [asdict(a) for a in self._alerts[-self._max_history :]]
            NEWS_ALERTS_FILE.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            logger.warning("Could not persist news alerts: %s", exc)

    def list_alerts(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [asdict(a) for a in reversed(self._alerts[-limit:])]

    def _is_duplicate(self, article_id: str, cooldown_seconds: int) -> bool:
        last = self._seen.get(article_id)
        if last is None:
            return False
        return (datetime.now(timezone.utc).timestamp() - last) < cooldown_seconds

    def add_alert(self, alert: NewsAlert, article_id: str, cooldown_seconds: int) -> bool:
        with self._lock:
            if self._is_duplicate(article_id, cooldown_seconds):
                return False
            self._seen[article_id] = datetime.now(timezone.utc).timestamp()
            self._alerts.append(alert)
            if len(self._alerts) > self._max_history:
                self._alerts = self._alerts[-self._max_history :]
            self._persist()
        return True


news_alert_store = NewsAlertStore(max_history=NEWS_CONFIG["max_history"])


def _score_article(title: str, summary: str) -> tuple[int, list[str], list[str]]:
    """Score article impact based on keyword categories."""
    text = f"{title} {summary}".lower()
    score = 0
    matched_categories: list[str] = []
    matched_keywords: list[str] = []

    for category, keywords in IMPACT_KEYWORDS.items():
        weight = CATEGORY_WEIGHTS.get(category, 1)
        hits = [kw for kw in keywords if kw in text]
        if hits:
            matched_categories.append(category)
            matched_keywords.extend(hits)
            score += weight * min(len(hits), 2)  # cap per category to reduce noise

    return score, matched_categories, matched_keywords


def _severity(score: int) -> str:
    if score >= NEWS_CONFIG["high_impact_score"]:
        return "high"
    return "medium"


def _build_alert(article: NewsArticle, score: int, categories: list[str], keywords: list[str]) -> NewsAlert:
    sev = _severity(score)
    return NewsAlert(
        id=str(uuid.uuid4())[:8],
        title=article.title,
        summary=article.summary[:280] if article.summary else "",
        url=article.url,
        source=article.source_name,
        severity=sev,
        impact_score=score,
        matched_categories=categories,
        matched_keywords=sorted(set(keywords))[:8],
        timestamp=datetime.now(timezone.utc).isoformat(),
        meta={"published": article.published, "source_id": article.source_id},
    )


def _is_enabled() -> bool:
    if os.getenv("NEWS_ALERTS_ENABLED", "true").lower() in ("0", "false", "no"):
        return False
    return NEWS_CONFIG.get("enabled", True)


def process_news_feeds() -> list[dict]:
    """Fetch news, filter for market impact, and fire phone alerts."""
    if not _is_enabled():
        return []

    articles = fetch_all_news()
    fired: list[dict] = []
    min_score = NEWS_CONFIG["min_impact_score"]
    cooldown = NEWS_CONFIG["alert_cooldown_seconds"]
    max_per_poll = NEWS_CONFIG["max_alerts_per_poll"]

    for article in articles:
        if len(fired) >= max_per_poll:
            break

        score, categories, keywords = _score_article(article.title, article.summary)
        if score < min_score:
            continue

        alert = _build_alert(article, score, categories, keywords)
        if news_alert_store.add_alert(alert, article.id, cooldown):
            fired.append(asdict(alert))
            message = (
                f"📰 *{article.source_name}*\n"
                f"Impact score: {score}\n"
                f"Categories: {', '.join(categories)}"
            )
            if alert.summary:
                message += f"\n\n{alert.summary[:200]}"
            send_phone_alert(alert.title, message, alert.severity, alert.url)

    if fired:
        logger.info("Fired %d news alerts", len(fired))
    return fired


def get_last_news_poll() -> dict | None:
    return _last_poll


_last_poll: dict | None = None


def run_news_poll() -> dict:
    """Run news poll and record status."""
    global _last_poll
    try:
        fired = process_news_feeds()
        _last_poll = {
            "alerts_fired": len(fired),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
        }
    except Exception as exc:
        logger.exception("News poll failed: %s", exc)
        _last_poll = {
            "alerts_fired": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "error": str(exc),
        }
    return _last_poll
