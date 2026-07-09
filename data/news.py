"""Fetch and parse financial news from RSS feeds."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from config.news import NEWS_SOURCES

logger = logging.getLogger(__name__)

USER_AGENT = "MarketRocketScanner/2.0 (+https://github.com/Simrantrading/ai-trading-dashboard)"


@dataclass
class NewsArticle:
    id: str
    title: str
    summary: str
    url: str
    source_id: str
    source_name: str
    published: str


def _parse_published(entry: dict) -> str:
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def _article_id(url: str, title: str) -> str:
    return url.strip() or title.strip().lower()[:120]


def fetch_source(source: dict) -> list[NewsArticle]:
    """Fetch articles from a single RSS source."""
    articles: list[NewsArticle] = []
    try:
        response = httpx.get(
            source["url"],
            headers={"User-Agent": USER_AGENT},
            timeout=15,
            follow_redirects=True,
        )
        response.raise_for_status()
        feed = feedparser.parse(response.text)
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", source["name"], exc)
        return articles

    for entry in feed.entries[:20]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        url = (entry.get("link") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        # Strip basic HTML tags from summaries
        if "<" in summary:
            summary = re.sub(r"<[^>]+>", "", summary)
            summary = summary.strip()

        articles.append(
            NewsArticle(
                id=_article_id(url, title),
                title=title,
                summary=summary[:500],
                url=url,
                source_id=source["id"],
                source_name=source["name"],
                published=_parse_published(entry),
            )
        )
    return articles


def fetch_all_news() -> list[NewsArticle]:
    """Fetch articles from all configured news sources."""
    seen: set[str] = set()
    all_articles: list[NewsArticle] = []

    for source in NEWS_SOURCES:
        for article in fetch_source(source):
            if article.id in seen:
                continue
            seen.add(article.id)
            all_articles.append(article)

    all_articles.sort(key=lambda a: a.published, reverse=True)
    return all_articles
