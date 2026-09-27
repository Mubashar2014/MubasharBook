"""Admin quick-activation: form handling, access gating, and expiry."""
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models.user import User
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.admin_log import AdminLog
from app.models.stock import StockItem
from app.scheduler import check_subscription_expiry


@pytest.fixture
def admin_client(app, test_user):
    test_user.is_admin = True
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)
    return c


def client_for(app, user):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
    return c


def make_user(name, phone, trial_days_left=-5, sub_status='trial',
              plan='basic', period_days_left=None, is_admin=False, is_premium=False):
    """User + shop + subscription. trial_days_left=-5 → trial already over."""
    user = User(
        owner_name=name, phone=phone, email=f'{phone}@activate.test',
        language='en', is_verified=True, email_verified_at=datetime.utcnow(),
        is_admin=is_admin, is_premium=is_premium,
    )
    user.set_password('password123')
    trial_end = datetime.utcnow() + timedelta(days=trial_days_left)
    user.trial_start = trial_end - timedelta(days=7)
    user.trial_end = trial_end
    db.session.add(user)
    db.session.flush()

    shop = Shop(user_id=user.id, name=f"{name}'s Shop", initial_investment=100000)
    db.session.add(shop)
    db.session.flush()

    sub = Subscription(
        shop_id=shop.id, plan=plan, status=sub_status,
        trial_start=user.trial_start, trial_end=user.trial_end,
    )
    if period_days_left is not None:
        sub.current_period_start = datetime.utcnow() - timedelta(days=2)
        sub.current_period_end = datetime.utcnow() + timedelta(days=period_days_left)
    db.session.add(sub)
    db.session.commit()
    return user, shop, sub


def activate(admin_client, user_id, **data):
    payload = {'plan': 'basic', 'duration': '1'}
    payload.update(data)
    return admin_client.post(f'/admin/user/{user_id}/quick-activate', data=payload,
                             follow_redirects=False)


def days_between(a, b):
    return (b - a).total_seconds() / 86400.0


# ── ACTIVATION ───────────────────────────────────────────


def test_quick_activate_premium_sets_flag_and_window(admin_client, app):
    user, shop, sub = make_user('Premium Target', '03001110001')
    assert user.is_read_only is True  # expired trial

    resp = activate(admin_client, user.id, plan='premium', duration='1')
    assert resp.status_code == 302

    db.session.refresh(sub)
    db.session.refresh(user)
    assert sub.status == 'active'
    assert sub.plan == 'premium'
    assert user.is_premium is True
    assert user.is_read_only is False
    assert 27 <= days_between(sub.current_period_start, sub.current_period_end) <= 32


def test_quick_activate_basic_unlocks_expired_trial(admin_client, app):
    """Core gap fix: Basic plan grants writes without the premium flag."""
    user, shop, sub = make_user('Basic Target', '03001110002')
    assert user.is_read_only is True

    activate(admin_client, user.id, plan='basic', duration='3')

    db.session.refresh(sub)
    db.session.refresh(user)
    assert sub.status == 'active'
    assert sub.plan == 'basic'
    assert user.is_premium is False
    assert user.is_read_only is False  # unlocked by active window


def test_quick_activate_one_year_uses_calendar_year(admin_client, app):
    user, shop, sub = make_user('Year Target', '03001110003')
    activate(admin_client, user.id, plan='premium', duration='12')

    db.session.refresh(sub)
    span = days_between(sub.current_period_start, sub.current_period_end)
    assert 360 <= span <= 370  # calendar year, not 12*30=360-ish only


def test_quick_activate_custom_days(admin_client, app):
    user, shop, sub = make_user('Custom Target', '03001110004')
    activate(admin_client, user.id, plan='basic', duration='custom', custom_days='45')

    db.session.refresh(sub)
    span = days_between(sub.current_period_start, sub.current_period_end)
    assert 44 <= span <= 46


def test_quick_activate_invalid_inputs_flash_not_crash(admin_client, app):
    user, shop, sub = make_user('Invalid Target', '03001110005')
    original_status = sub.status

    for payload in (
        {'plan': 'basic', 'duration': 'bogus'},
        {'plan': 'gold', 'duration': '1'},       # bad plan
        {'plan': 'basic', 'duration': 'custom'}, # custom without days
        {'plan': 'basic', 'duration': ''},       # blank duration
    ):
        resp = activate(admin_client, user.id, **payload)
        assert resp.status_code == 302  # redirect with flash, never a 500

    # Duration key missing entirely (not just blank)
    resp = admin_client.post(f'/admin/user/{user.id}/quick-activate',
                             data={'plan': 'basic'}, follow_redirects=False)
    assert resp.status_code == 302

    db.session.refresh(sub)
    assert sub.status == original_status  # nothing was activated


def test_quick_activate_creates_no_payment_record(admin_client, app):
    user, shop, sub = make_user('No Payment Target', '03001110006')
    before = Payment.query.count()
    activate(admin_client, user.id, plan='premium', duration='6')
    assert Payment.query.count() == before


def test_quick_activate_writes_admin_log(admin_client, app):
    user, shop, sub = make_user('Logged Target', '03001110007')
    activate(admin_client, user.id, plan='premium', duration='2', notes='Gift for demo')

    log = AdminLog.query.filter_by(action='quick_activation', target_id=sub.id).first()
    assert log is not None
    assert 'Gift for demo' in log.description


def test_quick_activate_rejects_admin_target(admin_client, app):
    user, shop, sub = make_user('Admin Target', '03001110008', is_admin=True,
                                sub_status='expired')
    activate(admin_client, user.id, plan='premium', duration='12')
    db.session.refresh(sub)
    assert sub.status == 'expired'  # unchanged


# ── ACCESS GATING / EXPIRY ───────────────────────────────


def test_access_denied_once_period_has_ended(app):
    """Stale premium flag must not outlive the paid window (lazy expiry)."""
    user, shop, sub = make_user('Lazy Expiry', '03001110009',
                                sub_status='active', is_premium=True,
                                period_days_left=-1)
    assert user.is_read_only is True


def test_access_denied_for_expired_status_even_with_premium(app):
    user, shop, sub = make_user('Expired Status', '03001110010',
                                sub_status='expired', is_premium=True)
    assert user.is_read_only is True


def test_active_basic_window_grants_access(app):
    user, shop, sub = make_user('Window Access', '03001110011',
                                sub_status='active', period_days_left=15)
    assert user.is_read_only is False


def test_subscription_expiry_job_expires_and_clears_premium(app):
    user, shop, sub = make_user('Job Expiry', '03001110012',
                                sub_status='active', is_premium=True,
                                period_days_left=-1)

    check_subscription_expiry()

    db.session.refresh(sub)
    db.session.refresh(user)
    assert sub.status == 'expired'
    assert sub.grace_period_end is not None
    assert user.is_premium is False
    assert user.is_read_only is True


def test_subscription_expiry_job_skips_still_active(app):
    user, shop, sub = make_user('Still Active', '03001110013',
                                sub_status='active', is_premium=True,
                                period_days_left=10)

    check_subscription_expiry()

    db.session.refresh(sub)
    db.session.refresh(user)
    assert sub.status == 'active'
    assert user.is_premium is True


# ── END-TO-END: read-only block → activate → writes work ─


STOCK_DATA = {
    'model_name': 'Activation Test Phone',
    'quantity': 1,
    'cost_price': 40000,
    'purchase_date': '2026-09-20',
    'supplier_name': '',
    'purchase_paid': 40000,
    'purchase_expense_desc': '',
    'purchase_expense_amount': 0,
}


def test_expired_user_blocked_then_basic_quick_activate_unlocks_writes(admin_client, app):
    user, shop, sub = make_user('E2E Target', '03001110014')
    target_client = client_for(app, user)

    # Expired trial, no paid window → POSTs are redirected as read-only
    with app.app_context():
        resp = target_client.post('/stock/in', data=STOCK_DATA, follow_redirects=False)
    assert resp.status_code == 302
    assert 'dashboard' in resp.headers.get('Location', '')
    assert StockItem.query.count() == 0

    # Admin quick-activates Basic for 1 month
    resp = activate(admin_client, user.id, plan='basic', duration='1')
    assert resp.status_code == 302

    # Same POST now goes through and creates the item
    with app.app_context():
        resp = target_client.post('/stock/in', data=STOCK_DATA, follow_redirects=False)
    assert resp.status_code == 302
    assert 'dashboard' not in resp.headers.get('Location', '')
    assert StockItem.query.count() == 1


# ── PAYMENT PAGE ─────────────────────────────────────────


def test_payment_instructions_uses_config_and_local_qr(logged_in_client, app):
    app.config['PAYMENT_NAYAPAY_NUMBER'] = '03129347067'
    app.config['PAYMENT_NAYAPAY_NAME'] = 'Malik Muhammad Mubashar Waheed'
    app.config['PAYMENT_EASYPAISA_NUMBER'] = '03490111739'

    resp = logged_in_client.get('/subscription/subscribe/basic/monthly')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'static/img/nayapay-qr.png' in html
    assert 'static/img/easypaisa-qr.png' in html
    assert 'qrserver.com' not in html          # no third-party QR service
    assert '03129347067' in html               # config number rendered
    assert 'Malik Muhammad Mubashar Waheed' in html
    assert '03490111739' in html
