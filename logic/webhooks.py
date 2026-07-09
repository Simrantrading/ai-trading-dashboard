"""Send alert notifications to Telegram and Discord."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def send_phone_alert(title: str, message: str, severity: str = "medium", url: str | None = None) -> None:
    """Deliver an alert to configured Telegram/Discord webhooks."""
    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    emoji = {"high": "🚨", "medium": "⚡", "low": "📢"}.get(severity, "📢")
    body = f"{emoji} *{title}*\n{message}"
    if url:
        body += f"\n\n[Read more]({url})"

    try:
        if discord_url:
            content = f"{emoji} **{title}** — {message}"
            if url:
                content += f"\n{url}"
            httpx.post(
                discord_url,
                json={"content": content, "username": "Market Rocket Scanner"},
                timeout=10,
            )

        if telegram_token and telegram_chat:
            tg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            httpx.post(
                tg_url,
                json={
                    "chat_id": telegram_chat,
                    "text": body,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
                timeout=10,
            )
    except Exception as exc:
        logger.warning("Phone alert delivery failed: %s", exc)
