"""Notifications service: SMS / WhatsApp via Twilio, with safe stub fallback.

Usage:
    from notifications import send_notification
    await send_notification(db, kind="sms", to="+393331234567", body="Test", context={...})

Providers:
- Twilio (enabled when TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN are set)
- Stub (always on; persists to DB with status="logged", used in dev/no-keys)
"""
import logging
import os
from typing import Optional, Dict, Any

from core import db, new_id, now_utc

logger = logging.getLogger("cleantec.notifications")

# --- Twilio client lazy init -------------------------------------------------
_twilio_client = None
_twilio_checked = False


def _get_twilio():
    global _twilio_client, _twilio_checked
    if _twilio_checked:
        return _twilio_client
    _twilio_checked = True
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        logger.info("Twilio not configured — using stub provider")
        return None
    try:
        from twilio.rest import Client
        _twilio_client = Client(sid, token)
        logger.info("Twilio initialized")
    except Exception as e:
        logger.error(f"Twilio init failed: {e}")
        _twilio_client = None
    return _twilio_client


def is_twilio_enabled() -> bool:
    return _get_twilio() is not None


# --- Core send ---------------------------------------------------------------
async def send_notification(
    kind: str,
    to: str,
    body: str,
    context: Optional[Dict[str, Any]] = None,
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send SMS or WhatsApp. Always persists a record to db.notifications.

    Returns the stored notification record.
    """
    kind = kind.lower().strip()
    if kind not in ("sms", "whatsapp"):
        raise ValueError(f"kind must be sms|whatsapp, got {kind}")
    if not to or not body:
        raise ValueError("to and body are required")

    record: Dict[str, Any] = {
        "id": new_id(),
        "kind": kind,
        "to": to,
        "body": body,
        "context": context or {},
        "status": "pending",
        "provider": "stub",
        "provider_sid": None,
        "error": None,
        "sent_by": (user or {}).get("id"),
        "sent_by_name": (user or {}).get("name"),
        "created_at": now_utc(),
    }

    client = _get_twilio()
    if client is None:
        record["status"] = "logged"
        record["provider"] = "stub"
        logger.info(f"[STUB-{kind.upper()}] to={to} body={body[:80]!r}")
    else:
        try:
            if kind == "sms":
                sender = os.environ.get("TWILIO_PHONE_NUMBER")
                if not sender:
                    raise RuntimeError("TWILIO_PHONE_NUMBER missing")
                msg = client.messages.create(from_=sender, to=to, body=body)
            else:  # whatsapp
                sender = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
                sender_norm = sender if sender.startswith("whatsapp:") else f"whatsapp:{sender}"
                to_norm = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
                msg = client.messages.create(from_=sender_norm, to=to_norm, body=body)
            record["status"] = "sent"
            record["provider"] = "twilio"
            record["provider_sid"] = msg.sid
        except Exception as e:
            logger.error(f"Twilio send failed: {e}")
            record["status"] = "failed"
            record["provider"] = "twilio"
            record["error"] = str(e)[:500]

    await db.notifications.insert_one(record)
    record.pop("_id", None)
    return record
