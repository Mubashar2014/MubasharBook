"""WhatsApp user notifications: signup/activation/extension/expiry hooks,
admin Send Messages menu, one-click wa.me send."""
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models.user import User
from app.models.whatsapp import WhatsAppMessage
from app.utils.whatsapp import queue_whatsapp


def _signup(client, owner='WA Tester', phone='03001234567'):
    return client.post('/auth/signup', data={
        'owner_name': owner,
        'phone': phone,
        'email': f'{owner.lower().replace(" ", "")}@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
        'language': 'ur',
        'shop_name': f'{owner} Shop',
        'total_investment': 50000,
    }, follow_redirects=False)


@pytest.fixture
def admin_client(app, test_user):
    test_user.is_admin = True
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)
    return c


# ── Hooks ────────────────────────────────────────────────────────────────────

def test_signup_queues_welcome(client, app):
    resp = _signup(client)
    assert resp.status_code == 302

    with app.app_context():
        msg = WhatsAppMessage.query.filter_by(kind='welcome').one()
        assert msg.status == 'pending'
        assert msg.phone == '03001234567'
        assert 'Welcome to Mubashar Khata' in msg.message
        assert 'WA Tester' in msg.message
        assert '7-day free trial' in msg.message
        assert msg.user_id is not None


def test_signup_without_phone_skips_welcome(client, app):
    resp = _signup(client, owner='No Phone', phone='')
    assert resp.status_code == 302

    with app.app_context():
        assert WhatsAppMessage.query.count() == 0


def test_welcome_queued_only_once(app, client):
    _signup(client, owner='Once Only')
    with app.app_context():
        user = User.query.filter_by(email='onceonly@example.com').first()
        assert user is not None

    queue_whatsapp(user, 'welcome')
    queue_whatsapp(user, 'welcome')

    with app.app_context():
        assert WhatsAppMessage.query.filter_by(kind='welcome').count() == 1


def test_quick_activate_queues_plan_allotted(admin_client, app):
    target = app.test_client()
    _signup(target, owner='Pack User', phone='03001112223')
    with app.app_context():
        user_id = User.query.filter_by(email='packuser@example.com').first().id

    resp = admin_client.post(f'/admin/user/{user_id}/quick-activate', data={
        'plan': 'basic', 'duration': '1', 'notes': '',
    }, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        msg = WhatsAppMessage.query.filter_by(
            user_id=user_id, kind='package_active'
        ).one()
        assert msg.status == 'pending'
        assert 'package has been activated' in msg.message
        user = User.query.get(user_id)
        expected_until = user.shop.subscription.current_period_end.strftime('%d %b %Y')
        assert expected_until in msg.message
        assert 'Pack User' in msg.message


def test_extend_trial_queues_message(admin_client, app):
    target = app.test_client()
    _signup(target, owner='Extend User', phone='03008887776')
    with app.app_context():
        user_id = User.query.filter_by(email='extenduser@example.com').first().id

    resp = admin_client.post(f'/admin/user/{user_id}/extend-trial',
                             data={'days': 7}, follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        msg = WhatsAppMessage.query.filter_by(
            user_id=user_id, kind='trial_extended'
        ).one()
        assert msg.status == 'pending'
        assert 'trial has been extended' in msg.message
        user = User.query.get(user_id)
        assert user.trial_end.strftime('%d %b %Y') in msg.message
        assert 'Extend User' in msg.message


def test_trial_expired_queued_once_via_requests(client, app):
    _signup(client, owner='Old Trial', phone='03009998887')
    with app.app_context():
        user = User.query.filter_by(email='oldtrial@example.com').first()
        user.trial_end = datetime.utcnow() - timedelta(days=1)
        user.shop.subscription.trial_end = datetime.utcnow() - timedelta(days=1)
        db.session.commit()
        user_id = user.id

    client.get('/dashboard')
    client.get('/dashboard')

    with app.app_context():
        rows = WhatsAppMessage.query.filter_by(
            user_id=user_id, kind='trial_expired'
        ).all()
        assert len(rows) == 1
        assert 'free trial of Mubashar Khata has ended' in rows[0].message
        assert rows[0].phone == '03009998887'


def test_no_trial_expired_while_trial_active(client, app):
    _signup(client, owner='Fresh Trial', phone='03007776665')
    client.get('/dashboard')

    with app.app_context():
        user = User.query.filter_by(email='freshtrial@example.com').first()
        assert WhatsAppMessage.query.filter_by(
            user_id=user.id, kind='trial_expired'
        ).count() == 0
        assert WhatsAppMessage.query.filter_by(
            user_id=user.id, kind='welcome'
        ).count() == 1


# ── Admin Send Messages menu ─────────────────────────────────────────────────

def test_send_messages_page_admin_only(admin_client, client, app):
    _signup(app.test_client(), owner='Outbox User', phone='03005554443')

    resp = admin_client.get('/admin/whatsapp')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'WhatsApp Messages' in html
    assert 'Welcome to Mubashar Khata' in html
    assert 'Send on WhatsApp' in html
    assert 'Evolution' not in html  # manual-only build
    assert 'send-api' not in html

    outsider = client.get('/admin/whatsapp', follow_redirects=False)
    assert outsider.status_code == 302


def test_sent_filter_empty(admin_client, app):
    resp = admin_client.get('/admin/whatsapp?status=sent')
    assert resp.status_code == 200
    assert 'No sent messages.' in resp.get_data(as_text=True)


def test_click_send_records_and_opens_wa(admin_client, app):
    _signup(app.test_client(), owner='Mark User', phone='03006665554')
    with app.app_context():
        msg_id = WhatsAppMessage.query.filter_by(kind='welcome').first().id

    resp = admin_client.post(f'/admin/whatsapp/{msg_id}/mark-sent',
                             follow_redirects=False)
    assert resp.status_code == 302
    assert 'wa.me/923006665554' in resp.headers['Location']
    assert 'Welcome%20to%20Mubashar' in resp.headers['Location']

    with app.app_context():
        saved = db.session.get(WhatsAppMessage, msg_id)
        assert saved.status == 'sent'
        assert saved.sent_at is not None


def test_sent_row_has_no_send_button(admin_client, app):
    _signup(app.test_client(), owner='Sent Row', phone='03009191918')
    with app.app_context():
        msg_id = WhatsAppMessage.query.filter_by(kind='welcome').first().id
    admin_client.post(f'/admin/whatsapp/{msg_id}/mark-sent', follow_redirects=False)

    resp = admin_client.get('/admin/whatsapp?status=sent')
    html = resp.get_data(as_text=True)
    assert 'Sent Row' in html
    assert '/mark-sent' not in html  # only pending rows offer the send form


def test_dismiss_marks_dismissed(admin_client, app):
    _signup(app.test_client(), owner='Dismiss User', phone='03004443332')
    with app.app_context():
        msg_id = WhatsAppMessage.query.filter_by(kind='welcome').first().id

    resp = admin_client.post(f'/admin/whatsapp/{msg_id}/dismiss',
                             follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(WhatsAppMessage, msg_id).status == 'dismissed'


# ── Custom (ad-hoc) message ──────────────────────────────────────────────────

def test_custom_message_sends_and_records(admin_client, app):
    _signup(app.test_client(), owner='Custom Target', phone='03001717171')
    with app.app_context():
        uid = User.query.filter_by(email='customtarget@example.com').first().id

    resp = admin_client.post('/admin/whatsapp/send-custom', data={
        'user_id': uid, 'message': 'Hello from admin',
    }, follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.headers['Location']
    assert 'wa.me/923001717171' in loc
    assert 'Hello%20from%20admin' in loc

    with app.app_context():
        msg = WhatsAppMessage.query.filter_by(kind='custom').one()
        assert msg.status == 'sent'
        assert msg.sent_at is not None
        assert msg.message == 'Hello from admin'
        assert msg.phone == '03001717171'


def test_custom_message_empty_rejected(admin_client, app):
    _signup(app.test_client(), owner='Custom Empty', phone='03001818182')
    with app.app_context():
        uid = User.query.filter_by(email='customempty@example.com').first().id

    resp = admin_client.post('/admin/whatsapp/send-custom', data={
        'user_id': uid, 'message': '   ',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'Message cannot be empty' in resp.get_data(as_text=True)

    with app.app_context():
        assert WhatsAppMessage.query.filter_by(kind='custom').count() == 0


def test_custom_message_rejects_user_without_phone(admin_client, app):
    _signup(app.test_client(), owner='No Phone Two', phone='')
    with app.app_context():
        uid = User.query.filter_by(email='nophonetwo@example.com').first().id

    resp = admin_client.post('/admin/whatsapp/send-custom', data={
        'user_id': uid, 'message': 'Should not send',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'no WhatsApp number' in resp.get_data(as_text=True)

    with app.app_context():
        assert WhatsAppMessage.query.filter_by(kind='custom').count() == 0


def test_compose_form_lists_only_phone_users(admin_client, app):
    _signup(app.test_client(), owner='Listed User', phone='03001919198')
    _signup(app.test_client(), owner='Unlisted User', phone='')

    resp = admin_client.get('/admin/whatsapp')
    html = resp.get_data(as_text=True)
    assert 'New message' in html
    assert 'Listed User — 03001919198' in html
    assert 'Unlisted User —' not in html


def test_custom_message_admin_only(client, app):
    resp = client.post('/admin/whatsapp/send-custom', data={
        'user_id': 1, 'message': 'x',
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert 'login' in resp.headers.get('Location', '').lower()
