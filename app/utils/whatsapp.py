"""User WhatsApp notifications: outbox + optional Evolution API auto-send.

Every event (welcome / package activated / trial expired) is recorded in
whatsapp_messages. If EVOLUTION_API_URL is configured the message is sent
immediately through the Evolution API gateway; otherwise it waits in the
admin outbox, where one click opens WhatsApp with the text prefilled.
Nothing here may ever break the surrounding request (signup, activation...).
"""
import json
import urllib.request
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.whatsapp import WhatsAppMessage
from app.utils import normalise_whatsapp, intl_digits


def build_whatsapp_text(kind, user):
    """Approved message texts, personalized. kind: welcome | package_active | trial_expired."""
    name = user.owner_name or 'there'
    if kind == 'welcome':
        days = current_app.config.get('TRIAL_DAYS', 7)
        return (
            f'Assalam-o-Alaikum {name}! Welcome to Mubashar Khata. '
            f'Your account is ready and your {days}-day free trial has started. '
            'Start by adding your stock and recording your first sale. '
            'Need help? Just reply to this message.'
        )
    if kind == 'package_active':
        until = ''
        sub = user.shop.subscription if user.shop else None
        if sub is not None and sub.current_period_end:
            end = sub.current_period_end
            until = end.strftime('%d %b %Y') if hasattr(end, 'strftime') else str(end)
        activated = (
            f'Your Mubashar Khata package has been activated — full access until {until}.'
            if until else
            'Your Mubashar Khata package has been activated.'
        )
        return (
            f'Assalam-o-Alaikum {name}! {activated} '
            'Thank you for subscribing. Happy accounting!'
        )
    if kind == 'trial_expired':
        return (
            f'Assalam-o-Alaikum {name}, your free trial of Mubashar Khata has ended. '
            'Your data is safe — subscribe to a package to keep recording sales, '
            'stock and khata. Reply to this message if you need help choosing a plan.'
        )
    raise ValueError(f'Unknown WhatsApp message kind: {kind!r}')


def evolution_configured():
    return bool((current_app.config.get('EVOLUTION_API_URL') or '').strip()
                and (current_app.config.get('EVOLUTION_INSTANCE') or '').strip())


def _post_json(url, payload, headers, timeout=15):
    """HTTP POST seam (tests monkeypatch this). Returns (status_code, body)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
    )
    req.add_header('Content-Type', 'application/json')
    for key, value in headers.items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode('utf-8', errors='replace')


def send_via_evolution(msg):
    """Try sending one outbox row through the Evolution API. Updates msg in
    place (sent/failed). Returns True on success. Never raises."""
    base = (current_app.config.get('EVOLUTION_API_URL') or '').rstrip('/')
    instance = current_app.config.get('EVOLUTION_INSTANCE') or ''
    api_key = current_app.config.get('EVOLUTION_API_KEY') or ''
    if not base or not instance:
        msg.status = 'failed'
        msg.error = 'Evolution API not configured'
        return False

    number = intl_digits(msg.phone)
    if not number:
        msg.status = 'failed'
        msg.error = 'No usable phone number'
        return False

    try:
        status, body = _post_json(
            f'{base}/message/sendText/{instance}',
            {'number': number, 'text': msg.message},
            {'apikey': api_key} if api_key else {},
        )
        if 200 <= int(status) < 300:
            msg.status = 'sent'
            msg.error = None
            msg.sent_at = datetime.utcnow()
            return True
        msg.status = 'failed'
        msg.error = f'HTTP {status}: {body[:200]}'
        return False
    except Exception as exc:  # noqa: BLE001 — never break the calling request
        current_app.logger.warning('Evolution API send failed: %s', exc)
        msg.status = 'failed'
        msg.error = str(exc)[:300]
        return False


def queue_whatsapp(user, kind):
    """Record a WhatsApp message for a user and try to auto-send it.
    Deduplicates welcome/trial_expired to one row per user. Never raises."""
    try:
        phone = (user.phone or '').strip()
        if not normalise_whatsapp(phone):
            return None

        if kind in ('welcome', 'trial_expired'):
            existing = WhatsAppMessage.query.filter_by(
                user_id=user.id, kind=kind
            ).first()
            if existing is not None:
                return existing

        msg = WhatsAppMessage(
            user_id=user.id,
            phone=phone,
            kind=kind,
            message=build_whatsapp_text(kind, user),
            status='pending',
        )
        db.session.add(msg)
        db.session.flush()

        if evolution_configured():
            send_via_evolution(msg)

        db.session.commit()
        return msg
    except Exception:  # noqa: BLE001 — notifications must never break signup etc.
        current_app.logger.exception(
            'queue_whatsapp(%s) failed for user %s', kind, getattr(user, 'id', '?')
        )
        db.session.rollback()
        return None
