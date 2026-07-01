"""SMTP email service — config persistita in db.app_settings.

Config schema:
    {
        "_id": "smtp",
        "host": "smtp.example.com",
        "port": 587,
        "username": "noreply@example.com",
        "password": "...",           # stored as-is (encrypt in prod)
        "from_email": "noreply@example.com",
        "from_name": "CleanTec",
        "use_tls": true,             # STARTTLS (port 587)
        "use_ssl": false,            # SSL/TLS (port 465)
        "enabled": true,
        "updated_at": datetime,
        "updated_by": user_email,
    }

Usage:
    from smtp_service import send_email, is_smtp_configured
    ok = await send_email(to, subject, body_text, body_html=None)
"""
from __future__ import annotations
import logging
from email.message import EmailMessage
from typing import Optional, Dict, Any

import aiosmtplib

from core import db, now_utc, new_id

logger = logging.getLogger("cleantec.smtp")


async def get_smtp_config() -> Optional[Dict[str, Any]]:
    doc = await db.app_settings.find_one({"_id": "smtp"})
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


async def is_smtp_configured() -> bool:
    cfg = await get_smtp_config()
    if not cfg:
        return False
    return bool(cfg.get("enabled")) and all(cfg.get(k) for k in ("host", "port", "from_email"))


async def save_smtp_config(data: Dict[str, Any], user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Upsert SMTP config. `data` may include: host, port, username, password,
    from_email, from_name, use_tls, use_ssl, enabled. Password only updated if non-empty."""
    update: Dict[str, Any] = {}
    for k in ("host", "port", "username", "from_email", "from_name"):
        if k in data and data[k] is not None:
            update[k] = data[k]
    for k in ("use_tls", "use_ssl", "enabled"):
        if k in data and data[k] is not None:
            update[k] = bool(data[k])
    if "password" in data and data["password"]:
        update["password"] = data["password"]
    if "port" in update and update["port"]:
        update["port"] = int(update["port"])
    update["updated_at"] = now_utc()
    if user:
        update["updated_by"] = user.get("email")
    await db.app_settings.update_one({"_id": "smtp"}, {"$set": update}, upsert=True)
    return await get_smtp_config()


async def send_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
    attachments: Optional[list] = None,
) -> Dict[str, Any]:
    """Send email via SMTP if configured; otherwise stub (log). Always persists to db.email_events.

    `attachments`: lista di dict {filename, content (bytes), mime (es 'application/pdf')}.
    """
    event: Dict[str, Any] = {
        "id": new_id(),
        "to": to,
        "subject": subject,
        "context": context or {},
        "tenant_id": tenant_id,
        "provider": "stub",
        "status": "logged",
        "error": None,
        "created_at": now_utc(),
    }

    cfg = await get_smtp_config()
    if not cfg or not cfg.get("enabled"):
        logger.info(f"[EMAIL-STUB] to={to} subject={subject!r}")
        await db.email_events.insert_one(event)
        event.pop("_id", None)
        return event

    # Build message
    msg = EmailMessage()
    from_email = cfg.get("from_email")
    from_name = cfg.get("from_name") or "CleanTec"
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    # Allegati
    for att in (attachments or []):
        if not att or not att.get("content"):
            continue
        mime = att.get("mime") or "application/octet-stream"
        maintype, _, subtype = mime.partition("/")
        subtype = subtype or "octet-stream"
        msg.add_attachment(
            att["content"],
            maintype=maintype,
            subtype=subtype,
            filename=att.get("filename") or "attachment.bin",
        )

    try:
        host = cfg["host"]
        port = int(cfg.get("port") or 587)
        use_ssl = bool(cfg.get("use_ssl"))
        use_tls = bool(cfg.get("use_tls")) and not use_ssl  # can't mix
        username = cfg.get("username") or ""
        password = cfg.get("password") or ""

        await aiosmtplib.send(
            msg,
            hostname=host,
            port=port,
            username=username or None,
            password=password or None,
            start_tls=use_tls,
            use_tls=use_ssl,
            timeout=15,
        )
        event["provider"] = "smtp"
        event["status"] = "sent"
        logger.info(f"[EMAIL-SENT] to={to} via={host}:{port}")
    except Exception as e:
        event["provider"] = "smtp"
        event["status"] = "failed"
        event["error"] = str(e)[:500]
        logger.error(f"[EMAIL-FAILED] to={to} err={e}")

    await db.email_events.insert_one(event)
    event.pop("_id", None)
    return event
