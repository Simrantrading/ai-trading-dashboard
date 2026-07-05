"""Alert engine: session-aware rocket alerts with dedup and webhook delivery."""

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

import httpx

from config.alerts import ALERT_CONFIG, get_session_config
from config.opportunities import get_opportunity_config
from logic.sessions import MarketSession, get_market_session

logger = logging.getLogger(__name__)

ALERTS_FILE = Path(__file__).resolve().parent.parent / "data" / "alerts_history.json"


@dataclass
class Alert:
    id: str
    symbol: str
    session: str
    alert_type: str
    severity: str
    message: str
    price: float
    pct_change: float
    volume_ratio: float
    rocket_score: float
    timestamp: str
    meta: dict[str, Any] = field(default_factory=dict)


class AlertStore:
    """Thread-safe in-memory alert store with optional persistence."""

    def __init__(self, max_history: int = 200) -> None:
        self._alerts: list[Alert] = []
        self._seen: dict[str, float] = {}  # dedup key -> last alert unix time
        self._lock = Lock()
        self._max_history = max_history
        self._load()

    def _load(self) -> None:
        if not ALERTS_FILE.exists():
            return
        try:
            raw = json.loads(ALERTS_FILE.read_text())
            for item in raw[-self._max_history :]:
                self._alerts.append(Alert(**item))
        except Exception as exc:
            logger.warning("Could not load alert history: %s", exc)

    def _persist(self) -> None:
        try:
            ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = [asdict(a) for a in self._alerts[-self._max_history :]]
            ALERTS_FILE.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            logger.warning("Could not persist alerts: %s", exc)

    def list_alerts(self, limit: int = 50, session: str | None = None) -> list[dict]:
        with self._lock:
            alerts = self._alerts
            if session:
                alerts = [a for a in alerts if a.session == session]
            return [asdict(a) for a in reversed(alerts[-limit:])]

    def get_since(self, since_id: str | None) -> list[dict]:
        with self._lock:
            if not since_id:
                return []
            found = False
            result = []
            for alert in self._alerts:
                if found:
                    result.append(asdict(alert))
                elif alert.id == since_id:
                    found = True
            return result

    def _dedup_key(self, symbol: str, session: str, alert_type: str) -> str:
        return f"{session}:{symbol}:{alert_type}"

    def _is_duplicate(self, key: str, cooldown_seconds: int) -> bool:
        last = self._seen.get(key)
        if last is None:
            return False
        return (datetime.now(timezone.utc).timestamp() - last) < cooldown_seconds

    def add_alert(self, alert: Alert, cooldown_seconds: int) -> bool:
        key = self._dedup_key(alert.symbol, alert.session, alert.alert_type)
        with self._lock:
            if self._is_duplicate(key, cooldown_seconds):
                return False
            self._seen[key] = datetime.now(timezone.utc).timestamp()
            self._alerts.append(alert)
            if len(self._alerts) > self._max_history:
                self._alerts = self._alerts[-self._max_history :]
            self._persist()
        return True


alert_store = AlertStore(max_history=ALERT_CONFIG["max_history"])


def _severity(pct_change: float, rocket_score: float) -> str:
    thresholds = ALERT_CONFIG["severity_thresholds"]
    if (
        pct_change >= thresholds["high"]["min_pct_change"]
        or rocket_score >= thresholds["high"]["min_rocket_score"]
    ):
        return "high"
    if (
        pct_change >= thresholds["medium"]["min_pct_change"]
        or rocket_score >= thresholds["medium"]["min_rocket_score"]
    ):
        return "medium"
    return "low"


def _alert_type(pct_change: float, volume_ratio: float, session: str) -> str:
    if volume_ratio >= 3.0:
        return "volume_spike"
    if session in (MarketSession.PREMARKET.value, MarketSession.POSTMARKET.value):
        return "extended_hours_move"
    if pct_change >= 3.0:
        return "momentum_breakout"
    return "rocket"


def build_alert(rocket: dict, session: str) -> Alert:
    pct = rocket["pct_change"]
    score = rocket["rocket_score"]
    atype = _alert_type(pct, rocket["volume_ratio"], session)
    sev = _severity(pct, score)

    session_label = {
        "premarket": "Pre-Market",
        "intraday": "Intraday",
        "postmarket": "Post-Market",
        "closed": "After-Hours",
    }.get(session, session.title())

    direction = "up" if pct >= 0 else "down"
    message = (
        f"{session_label} {rocket['symbol']} {direction} {pct:+.2f}% "
        f"@ ${rocket['price']:.2f} | Vol {rocket['volume_ratio']:.1f}x | "
        f"Score {score:.0f}"
    )

    return Alert(
        id=str(uuid.uuid4())[:8],
        symbol=rocket["symbol"],
        session=session,
        alert_type=atype,
        severity=sev,
        message=message,
        price=rocket["price"],
        pct_change=pct,
        volume_ratio=rocket["volume_ratio"],
        rocket_score=score,
        timestamp=datetime.now(timezone.utc).isoformat(),
        meta={"rsi": rocket.get("rsi"), "trend_score": rocket.get("trend_score")},
    )


def build_buy_alert(opportunity: dict, session: str) -> Alert:
    """Build an alert for a buy opportunity with reasons and expectations."""
    confidence = opportunity["confidence"]
    exp = opportunity["expectations"]
    setup_label = opportunity["setup_label"]

    if confidence >= 75:
        sev = "high"
    elif confidence >= 60:
        sev = "medium"
    else:
        sev = "low"

    session_label = {
        "premarket": "Pre-Market",
        "intraday": "Intraday",
        "postmarket": "Post-Market",
        "closed": "After-Hours",
    }.get(session, session.title())

    message = (
        f"BUY {opportunity['symbol']} — {setup_label} "
        f"@ ${opportunity['price']:.2f} | Confidence {confidence:.0f}% | "
        f"Target ${exp['target']:.2f} · Stop ${exp['stop']:.2f} · R:R {exp['risk_reward']:.1f}"
    )

    return Alert(
        id=str(uuid.uuid4())[:8],
        symbol=opportunity["symbol"],
        session=session,
        alert_type=f"buy_{opportunity['setup_type']}",
        severity=sev,
        message=message,
        price=opportunity["price"],
        pct_change=opportunity["pct_change"],
        volume_ratio=opportunity["volume_ratio"],
        rocket_score=confidence,
        timestamp=datetime.now(timezone.utc).isoformat(),
        meta={
            "direction": "buy",
            "setup_type": opportunity["setup_type"],
            "setup_label": setup_label,
            "confidence": confidence,
            "reasons": opportunity["reasons"],
            "expectations": exp,
            "rsi": opportunity.get("rsi"),
            "trend_score": opportunity.get("trend_score"),
            "atr": opportunity.get("atr"),
        },
    )


def process_buy_opportunities(
    opportunities: list[dict], session: str | None = None
) -> list[dict]:
    """Evaluate buy opportunities and fire alerts."""
    session = session or get_market_session().value
    cfg = get_opportunity_config(session)
    fired: list[dict] = []

    for opp in opportunities:
        if opp["confidence"] < cfg.min_confidence:
            continue
        if opp["volume_ratio"] < cfg.min_volume_ratio:
            continue

        alert = build_buy_alert(opp, session)
        if alert_store.add_alert(alert, cfg.alert_cooldown_seconds):
            fired.append(asdict(alert))
            _dispatch_webhooks(alert)

    if fired:
        logger.info("Fired %d buy opportunity alerts for session=%s", len(fired), session)
    return fired


def process_scan_results(rockets: list[dict], session: str | None = None) -> list[dict]:
    """Evaluate scan results and fire new alerts."""
    session = session or get_market_session().value
    cfg = get_session_config(session)
    fired: list[dict] = []

    for rocket in rockets:
        if rocket["rocket_score"] < cfg.min_rocket_score:
            continue
        if rocket["pct_change"] < cfg.min_pct_change:
            continue
        if rocket["volume_ratio"] < cfg.min_volume_ratio:
            continue

        alert = build_alert(rocket, session)
        if alert_store.add_alert(alert, cfg.alert_cooldown_seconds):
            fired.append(asdict(alert))
            _dispatch_webhooks(alert)

    if fired:
        logger.info("Fired %d new alerts for session=%s", len(fired), session)
    return fired


def _format_webhook_message(alert: Alert) -> str:
    """Format alert for Discord/Telegram, with extra detail for buy opportunities."""
    emoji = {"high": "🚨", "medium": "⚡", "low": "📢"}.get(alert.severity, "📢")
    meta = alert.meta or {}

    if meta.get("direction") == "buy":
        reasons = meta.get("reasons", [])
        exp = meta.get("expectations", {})
        lines = [
            f"{emoji} **BUY {alert.symbol}** — {meta.get('setup_label', 'Buy Setup')}",
            f"Confidence: {meta.get('confidence', alert.rocket_score):.0f}%",
            "",
            "**Why:**",
        ]
        for reason in reasons:
            lines.append(f"• {reason}")
        lines.extend([
            "",
            "**Expectations:**",
            f"Entry: ${exp.get('entry', alert.price):.2f}",
            f"Target: ${exp.get('target', 0):.2f}",
            f"Stop: ${exp.get('stop', 0):.2f}",
            f"R:R {exp.get('risk_reward', 0):.1f} · {exp.get('timeframe', '')}",
        ])
        return "\n".join(lines)

    return f"{emoji} **{alert.symbol}** — {alert.message}"


def _dispatch_webhooks(alert: Alert) -> None:
    if not ALERT_CONFIG.get("webhook_enabled"):
        return

    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    body = _format_webhook_message(alert)

    try:
        if discord_url:
            payload = {
                "content": body,
                "username": "Rocket Scanner",
            }
            httpx.post(discord_url, json=payload, timeout=10)

        if telegram_token and telegram_chat:
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            httpx.post(
                url,
                json={"chat_id": telegram_chat, "text": body, "parse_mode": "Markdown"},
                timeout=10,
            )
    except Exception as exc:
        logger.warning("Webhook delivery failed: %s", exc)
