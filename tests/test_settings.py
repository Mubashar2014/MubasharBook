"""Settings: shop card (existing), profile card, security card — plus the
admin's own account page and the signup duplicate-phone guard."""
import pytest

from app.extensions import db
from app.models.shop import Shop
from app.models.user import User


def _make_user(owner_name, phone, email, is_admin=False):
    user = User(owner_name=owner_name, phone=phone, email=email,
                language='en', is_admin=is_admin)
    user.set_password('password123')
    user.start_trial(days=7)
    db.session.add(user)
    db.session.flush()
    db.session.add(Shop(user_id=user.id, name=f'{owner_name}s Shop',
                        initial_investment=50000))
    db.session.commit()
    return user


@pytest.fixture
def admin_user(app):
    return _make_user('Admin Person', '03001110000', 'adminperson@test.com',
                      is_admin=True)


@pytest.fixture
def admin_client(client, admin_user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
    return client


# ── Settings page ──


def test_settings_requires_login(client):
    resp = client.get('/settings', follow_redirects=False)
    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_settings_renders_all_three_sections(logged_in_client):
    resp = logged_in_client.get('/settings')
    assert resp.status_code == 200

    page = resp.get_data(as_text=True)
    assert 'Shop Settings' in page
    assert 'Profile' in page
    assert 'Security' in page
    assert '/settings/profile' in page
    assert '/settings/password' in page
    assert '/auth/forgot' in page, 'users locked out of their password need the link'
    assert 'href="/settings"' in page, 'Settings must be reachable from the sidebar'


def test_profile_update_saves_the_fields(logged_in_client, test_user):
    resp = logged_in_client.post('/settings/profile', data={
        'owner_name': 'Renamed Owner',
        'phone': '03009998887',
        'language': 'ur',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '#profile' in resp.headers['Location']

    db.session.refresh(test_user)
    assert test_user.owner_name == 'Renamed Owner'
    assert test_user.phone == '03009998887'
    assert test_user.language == 'ur'


def test_profile_rejects_a_phone_owned_by_someone_else(logged_in_client, test_user, second_user):
    resp = logged_in_client.post('/settings/profile', data={
        'owner_name': test_user.owner_name,
        'phone': second_user.phone,
        'language': 'en',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert 'already registered' in resp.get_data(as_text=True)

    db.session.refresh(test_user)
    assert test_user.phone == '03001234567', 'phone must not change'


def test_profile_rejects_a_blank_owner_name(logged_in_client, test_user):
    resp = logged_in_client.post('/settings/profile', data={
        'owner_name': '',
        'phone': test_user.phone,
        'language': 'en',
    }, follow_redirects=False)

    assert resp.status_code == 200, 'validation failure must re-render, not redirect'
    db.session.refresh(test_user)
    assert test_user.owner_name == 'Test User'


def test_profile_keeps_your_own_phone(logged_in_client, test_user):
    resp = logged_in_client.post('/settings/profile', data={
        'owner_name': 'Same Phone',
        'phone': test_user.phone,
        'language': 'en',
    }, follow_redirects=False)

    assert resp.status_code == 302
    db.session.refresh(test_user)
    assert test_user.phone == '03001234567'
    assert test_user.owner_name == 'Same Phone'


# ── Change password ──


def test_password_change_rejects_the_wrong_current_password(logged_in_client, test_user):
    resp = logged_in_client.post('/settings/password', data={
        'current_password': 'not-my-password',
        'password': 'brandnewpass',
        'confirm_password': 'brandnewpass',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert 'Current password is incorrect' in resp.get_data(as_text=True)
    db.session.refresh(test_user)
    assert test_user.check_password('password123')


def test_password_change_rejects_a_short_new_password(logged_in_client, test_user):
    resp = logged_in_client.post('/settings/password', data={
        'current_password': 'password123',
        'password': 'short',
        'confirm_password': 'short',
    }, follow_redirects=False)

    assert resp.status_code == 200
    db.session.refresh(test_user)
    assert test_user.check_password('password123')


def test_password_change_with_the_right_password_works(logged_in_client, test_user):
    resp = logged_in_client.post('/settings/password', data={
        'current_password': 'password123',
        'password': 'brandnewpass',
        'confirm_password': 'brandnewpass',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '#password' in resp.headers['Location']

    db.session.refresh(test_user)
    assert test_user.check_password('brandnewpass')
    assert not test_user.check_password('password123')


def test_shop_investment_edit_still_works(logged_in_client, test_user):
    resp = logged_in_client.post('/settings', data={
        'shop_name': 'Renamed Shop',
        'initial_investment': '75000',
    }, follow_redirects=False)

    assert resp.status_code == 302
    db.session.refresh(test_user)
    assert test_user.shop.name == 'Renamed Shop'
    assert float(test_user.shop.initial_investment) == 75000


# ── Admin's own account page ──


def test_admin_account_page_renders(admin_client):
    resp = admin_client.get('/admin/account')
    assert resp.status_code == 200

    page = resp.get_data(as_text=True)
    assert 'My Account' in page
    assert '/settings/profile' not in page, 'profile posts back to the admin route'


def test_admin_account_is_forbidden_for_normal_users(logged_in_client):
    resp = logged_in_client.get('/admin/account')
    assert resp.status_code == 403


def test_admin_can_update_their_profile(admin_client, admin_user):
    resp = admin_client.post('/admin/account', data={
        'form': 'profile',
        'owner_name': 'Admin Renamed',
        'phone': '03001110000',
        'language': 'en',
    }, follow_redirects=False)

    assert resp.status_code == 302
    db.session.refresh(admin_user)
    assert admin_user.owner_name == 'Admin Renamed'


def test_admin_can_change_their_password(admin_client, admin_user):
    resp = admin_client.post('/admin/account', data={
        'form': 'password',
        'current_password': 'password123',
        'password': 'brandnewpass',
        'confirm_password': 'brandnewpass',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '#password' in resp.headers['Location']

    db.session.refresh(admin_user)
    assert admin_user.check_password('brandnewpass')
    assert not admin_user.check_password('password123')


def test_admin_password_change_rejects_the_wrong_current_password(admin_client, admin_user):
    resp = admin_client.post('/admin/account', data={
        'form': 'password',
        'current_password': 'wrong-password',
        'password': 'brandnewpass',
        'confirm_password': 'brandnewpass',
    }, follow_redirects=True)

    assert 'Current password is incorrect' in resp.get_data(as_text=True)
    db.session.refresh(admin_user)
    assert admin_user.check_password('password123')


def test_admin_is_never_read_only(app, admin_user):
    """A expired trial must not stop the admin changing their own password."""
    from datetime import datetime, timedelta

    admin_user.trial_start = datetime.utcnow() - timedelta(days=30)
    admin_user.trial_end = datetime.utcnow() - timedelta(days=1)
    admin_user.is_premium = False
    db.session.commit()

    assert admin_user.is_trial_active is False
    assert admin_user.is_read_only is False


# ── Signup: the live duplicate-phone 500 ──


def test_signup_duplicate_phone_is_caught_instead_of_500ing(client, test_user, monkeypatch):
    """The pre-check can miss (races, MySQL trailing-space comparison); the
    unique index is the real gate and must produce a friendly flash, not a 500."""
    from app.auth import routes as auth_routes

    monkeypatch.setattr(auth_routes, '_existing_account', lambda phone, email: None)

    resp = client.post('/auth/signup', data={
        'owner_name': 'Duplicate',
        'phone': '03001234567',          # already taken by test_user
        'email': 'duplicate@example.com',
        'password': 'secure123',
        'confirm_password': 'secure123',
        'language': 'en',
        'shop_name': 'Duplicate Shop',
        'total_investment': '50000',
    }, follow_redirects=True)

    assert resp.status_code == 200, 'must not raise'
    page = resp.get_data(as_text=True)
    assert 'This phone number is already registered' in page
    assert User.query.filter_by(phone='03001234567').count() == 1
    assert User.query.filter_by(email='duplicate@example.com').first() is None
