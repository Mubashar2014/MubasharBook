"""User WhatsApp notifications: an outbox of queued messages.

Every event (welcome / package activated / trial extended / trial expired)
is recorded in whatsapp_messages as 'pending'. The admin panel
(WhatsApp → Send Messages) shows each row with a button that opens
WhatsApp with the number and text prefilled — one click, then the admin
taps send; the row is recorded as 'sent'. Nothing here may ever break the
surrounding request (signup, activation...).
"""
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.whatsapp import WhatsAppMessage
from app.utils import normalise_whatsapp


def build_whatsapp_text(kind, user):
    """Message texts, personalized.
    kind: welcome | package_active | trial_extended | trial_expired"""
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
    if kind == 'trial_extended':
        until = ''
        if user.trial_end:
            end = user.trial_end
            until = end.strftime('%d %b %Y') if hasattr(end, 'strftime') else str(end)
        extended = (
            f'Your Mubashar Khata trial has been extended — now valid until {until}.'
            if until else
            'Your Mubashar Khata trial has been extended.'
        )
        return (
            f'Assalam-o-Alaikum {name}! {extended} '
            'Keep recording your sales and khata. '
            'Need help? Just reply to this message.'
        )
    if kind == 'trial_expired':
        return (
            f'Assalam-o-Alaikum {name}, your free trial of Mubashar Khata has ended. '
            'Your data is safe — subscribe to a package to keep recording sales, '
            'stock and khata. Reply to this message if you need help choosing a plan.'
        )
    raise ValueError(f'Unknown WhatsApp message kind: {kind!r}')


def queue_whatsapp(user, kind):
    """Record a WhatsApp message for the admin to send. Deduplicates
    welcome/trial_expired to one row per user. Never raises."""
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
        db.session.commit()
        return msg
    except Exception:  # noqa: BLE001 — notifications must never break signup etc.
        current_app.logger.exception(
            'queue_whatsapp(%s) failed for user %s', kind, getattr(user, 'id', '?')
        )
        db.session.rollback()
        return None
