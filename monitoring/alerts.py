import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import httpx

logger = logging.getLogger("automlops.alerts")

SEVERITY_COLORS = {
    "info": 0x3498DB,     # Blue
    "success": 0x2ECC71,  # Green
    "warning": 0xF1C40F,  # Yellow
    "critical": 0xE74C3C  # Red
}

SEVERITY_EMOJIS = {
    "info": "ℹ️",
    "success": "✅",
    "warning": "⚠️",
    "critical": "🚨"
}


def send_alert(
    message: str,
    severity: str = "warning",
    title: Optional[str] = None,
    fields: Optional[List[Dict[str, Any]]] = None
) -> bool:
    """
    Sends an actionable, rich embed notification via Discord Webhook.
    
    Args:
        message: Detailed explanation of the alert event
        severity: One of 'info', 'success', 'warning', 'critical'
        title: Optional title for the alert embed
        fields: Optional list of {'name': str, 'value': str, 'inline': bool}
        
    Returns:
        bool indicating whether delivery succeeded
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    sev = severity.lower()
    color = SEVERITY_COLORS.get(sev, 0x95A5A6)
    emoji = SEVERITY_EMOJIS.get(sev, "📢")

    alert_title = title or f"{emoji} AutoMLOps Alert [{sev.upper()}]"

    embed = {
        "title": alert_title,
        "description": message,
        "color": color,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {
            "text": "AutoMLOps Self-Hosted Platform"
        }
    }

    if fields:
        embed["fields"] = fields

    payload = {
        "username": "AutoMLOps Bot",
        "embeds": [embed]
    }

    # If critical severity, mention @everyone if configured
    if sev == "critical" and os.getenv("DISCORD_MENTION_CRITICAL", "false").lower() == "true":
        payload["content"] = "@everyone 🚨 Critical Platform Event!"

    if not webhook_url:
        logger.warning(f"[Discord Webhook Not Configured] {alert_title}: {message}")
        print(f"[ALERT - {sev.upper()}] {alert_title}\n{message}\n".encode("ascii", "replace").decode("ascii"))
        return False

    try:
        response = httpx.post(webhook_url, json=payload, timeout=5.0)
        if response.status_code in (200, 204):
            return True
        logger.error(f"Failed to post Discord alert: HTTP {response.status_code} - {response.text}")
        return False
    except Exception as e:
        logger.error(f"Exception posting Discord alert: {str(e)}")
        return False
