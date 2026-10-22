"""WhatsApp user notifications: signup/activation/expiry hooks, outbox, Evolution API."""
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


def test_quick_activate_queues_package_active(admin_client, app):
    target = app.test_client()
    _signup(target, owner='Pack User', phone='03001112223')
    with app.app_context():
        user = User.query.filter_by(email='packuser@example.com').first()
        user_id = user.id

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


# ── Admin outbox ─────────────────────────────────────────────────────────────

def test_outbox_page_admin_only(admin_client, client, app):
    _signup(app.test_client(), owner='Outbox User', phone='03005554443')

    resp = admin_client.get('/admin/whatsapp')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'WhatsApp Outbox' in html
    assert 'Welcome to Mubashar Khata' in html
    assert 'Open in WhatsApp' in html

    outsider = client.get('/admin/whatsapp', follow_redirects=False)
    assert outsider.status_code == 302


def test_outbox_sent_filter_empty(admin_client, app):
    resp = admin_client.get('/admin/whatsapp?status=sent')
    assert resp.status_code == 200
    assert 'No sent messages.' in resp.get_data(as_text=True)


def test_mark_sent_records_and_opens_wa(admin_client, app):
    _signup(app.test_client(), owner='Mark User', phone='03006665554')
    with app.app_context():
        msg = WhatsAppMessage.query.filter_by(kind='welcome').first()
        msg_id = msg.id

    resp = admin_client.post(f'/admin/whatsapp/{msg_id}/mark-sent',
                             follow_redirects=False)
    assert resp.status_code == 302
    assert 'wa.me/923006665554' in resp.headers['Location']
    assert 'Welcome%20to%20Mubashar' in resp.headers['Location']

    with app.app_context():
        saved = db.session.get(WhatsAppMessage, msg_id)
        assert saved.status == 'sent'
        assert saved.sent_at is not None


def test_dismiss_marks_dismissed(admin_client, app):
    _signup(app.test_client(), owner='Dismiss User', phone='03004443332')
    with app.app_context():
        msg_id = WhatsAppMessage.query.filter_by(kind='welcome').first().id

    resp = admin_client.post(f'/admin/whatsapp/{msg_id}/dismiss',
                             follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(WhatsAppMessage, msg_id).status == 'dismissed'


# ── Evolution API auto-send ──────────────────────────────────────────────────

def _enable_evolution(app, monkeypatch, responder):
    monkeypatch.setattr('app.utils.whatsapp._post_json', responder)
    app.config['EVOLUTION_API_URL'] = 'http://evo.test:8080'
    app.config['EVOLUTION_API_KEY'] = 'secret-key'
    app.config['EVOLUTION_INSTANCE'] = 'shop1'


def test_evolution_auto_send_success(client, app, monkeypatch):
    captured = {}

    def fake_post(url, payload, headers, timeout=15):
        captured.update(url=url, payload=payload, headers=headers)
        return 200, '{}'

    _enable_evolution(app, monkeypatch, fake_post)
    _signup(client, owner='Evo User', phone='03001234567')

    with app.app_context():
        msg = WhatsAppMessage.query.filter_by(kind='welcome').one()
        assert msg.status == 'sent'
        assert msg.sent_at is not None
        assert msg.error is None

    assert captured['url'] == 'http://evo.test:8080/message/sendText/shop1'
    assert captured['headers'] == {'apikey': 'secret-key'}
    assert captured['payload']['number'] == '923001234567'
    assert 'Welcome to Mubashar Khata' in captured['payload']['text']


def test_evolution_failure_marks_failed_and_signup_survives(client, app, monkeypatch):
    def boom(url, payload, headers, timeout=15):
        raise OSError('connection refused')

    _enable_evolution(app, monkeypatch, boom)
    resp = _signup(client, owner='Evo Down', phone='03001234567')
    assert resp.status_code == 302  # signup never breaks

    with app.app_context():
        msg = WhatsAppMessage.query.filter_by(kind='welcome').one()
        assert msg.status == 'failed'
        assert 'connection refused' in (msg.error or '')


def test_send_api_route_retries(admin_client, app, monkeypatch):
    _signup(app.test_client(), owner='Retry User', phone='03002221110')
    with app.app_context():
        msg_id = WhatsAppMessage.query.filter_by(kind='welcome').first().id

    def fake_post(url, payload, headers, timeout=15):
        return 200, '{}'

    _enable_evolution(app, monkeypatch, fake_post)
    resp = admin_client.post(f'/admin/whatsapp/{msg_id}/send-api',
                             follow_redirects=True)
    assert resp.status_code == 200
    assert 'sent via Evolution API' in resp.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(WhatsAppMessage, msg_id).status == 'sent'


def test_send_api_route_without_config_warns(admin_client, app):
    _signup(app.test_client(), owner='No Evo', phone='03003332221')
    with app.app_context():
        msg_id = WhatsAppMessage.query.filter_by(kind='welcome').first().id

    resp = admin_client.post(f'/admin/whatsapp/{msg_id}/send-api',
                             follow_redirects=True)
    assert resp.status_code == 200
    assert 'not configured' in resp.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(WhatsAppMessage, msg_id).status == 'pending'
