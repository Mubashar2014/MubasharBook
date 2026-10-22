"""Premium / PRO surfaces are disabled for users and labelled 'coming soon'."""
from pathlib import Path

from app.models.payment import Payment
from app.models.shareholder import Partner
from app.utils.premium import premium_enabled

EMAILS_DIR = Path(__file__).resolve().parent.parent / 'app' / 'templates' / 'emails'


def _get(app, client, path):
    with app.app_context():
        return client.get(path)


def _post(app, client, path, data=None):
    with app.app_context():
        return client.post(path, data=data or {})


def test_premium_flag_defaults_to_off(app):
    app.config.pop('PREMIUM_ENABLED', None)
    with app.app_context():
        assert premium_enabled() is False


def test_sidebar_shareholders_disabled_with_soon_chip(logged_in_client, app):
    resp = _get(app, logged_in_client, '/dashboard')
    html = resp.get_data(as_text=True)
    assert 'side-link disabled' in html
    assert 'SOON' in html
    assert 'PRO</span>' not in html
    assert 'href="/shareholders' not in html


def test_shareholders_routes_blocked_when_disabled(logged_in_client, app):
    app.config['PREMIUM_ENABLED'] = False

    resp = _get(app, logged_in_client, '/shareholders/')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/dashboard')

    resp = _post(app, logged_in_client, '/shareholders/add-partner',
                 {'name': 'Sneaky', 'role': 'investor', 'investment_amount': '1000'})
    assert resp.status_code == 302
    with app.app_context():
        assert Partner.query.count() == 0

    resp = _get(app, logged_in_client, '/dashboard')
    assert 'coming soon' in resp.get_data(as_text=True).lower()


def test_premium_payment_instructions_blocked(logged_in_client, app):
    app.config['PREMIUM_ENABLED'] = False

    resp = _get(app, logged_in_client, '/subscription/subscribe/premium/monthly')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/subscription/subscribe')

    resp = _get(app, logged_in_client, '/subscription/subscribe')
    assert 'Premium plan is coming soon' in resp.get_data(as_text=True)


def test_premium_submit_payment_blocked(logged_in_client, app):
    app.config['PREMIUM_ENABLED'] = False

    resp = _post(app, logged_in_client, '/subscription/submit-payment', {
        'plan': 'premium', 'billing_cycle': 'monthly', 'payment_method': 'nayapay',
    })
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/subscription/subscribe')
    with app.app_context():
        assert Payment.query.count() == 0


def test_basic_subscribe_flow_unaffected(logged_in_client, app):
    app.config['PREMIUM_ENABLED'] = False

    resp = _get(app, logged_in_client, '/subscription/subscribe/basic/monthly')
    assert resp.status_code == 200
    assert 'basic' in resp.get_data(as_text=True).lower()


def test_subscribe_page_marks_premium_coming_soon(logged_in_client, app):
    resp = _get(app, logged_in_client, '/subscription/subscribe')
    html = resp.get_data(as_text=True)
    assert 'COMING SOON' in html
    assert 'Subscribe to Premium' not in html
    assert 'Subscribe to Basic' in html


def test_landing_marks_premium_coming_soon(client, app):
    resp = _get(app, client, '/')
    html = resp.get_data(as_text=True)
    assert 'Coming soon — for shops with investors' in html
    assert 'Coming soon — Investor Portal' in html
    assert 'Most popular' not in html
    assert '(Coming soon)' in html


def test_premium_email_templates_mention_coming_soon():
    for name in ('welcome.html', 'trial_reminder_1day.html',
                 'trial_reminder_3days.html', 'trial_expired.html'):
        text = (EMAILS_DIR / name).read_text(encoding='utf-8')
        assert 'coming soon' in text.lower(), name
