from datetime import datetime

from app.models.user import User
from app.models.shop import Shop
from app.extensions import db


def test_signup_page_loads(client):
    resp = client.get('/auth/signup')
    assert resp.status_code == 200


def test_signup_creates_user_and_shop(client, app):
    resp = client.post('/auth/signup', data={
        'owner_name': 'New Owner',
        'phone': '03009998877',
        'email': 'newowner@example.com',
        'password': 'secure123',
        'confirm_password': 'secure123',
        'language': 'en',
        'shop_name': 'Test Shop',
        'total_investment': '100000',
    }, follow_redirects=False)

    with app.app_context():
        user = User.query.filter_by(phone='03009998877').first()
        assert user is not None
        assert user.owner_name == 'New Owner'
        assert user.check_password('secure123')
        shop = Shop.query.filter_by(user_id=user.id).first()
        assert shop is not None
        assert shop.name == 'Test Shop'
        assert float(shop.initial_investment) == 100000.0


def test_signup_logs_in_and_redirects_to_dashboard(client, app):
    resp = client.post('/auth/signup', data={
        'owner_name': 'Redirect User',
        'phone': '03007776655',
        'email': 'redirect@example.com',
        'password': 'secure123',
        'confirm_password': 'secure123',
        'language': 'ur',
        'shop_name': 'Redirect Shop',
        'total_investment': '50000',
    }, follow_redirects=False)

    assert resp.status_code == 302
    # Soft verification: signup logs the user straight into the app
    assert '/dashboard' in resp.headers['Location']
    with client.session_transaction() as sess:
        assert '_user_id' in sess

    with app.app_context():
        user = User.query.filter_by(email='redirect@example.com').first()
        assert user is not None
        assert user.email_verified_at is None  # NOT auto-verified
        assert user.is_verified is False


def test_signup_duplicate_phone_redirects_to_login(client, test_user):
    resp = client.post('/auth/signup', data={
        'owner_name': 'Duplicate',
        'phone': '03001234567',
        'email': 'duplicate@example.com',
        'password': 'secure123',
        'confirm_password': 'secure123',
        'language': 'en',
        'shop_name': 'Duplicate Shop',
        'total_investment': '50000',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_login_page_loads(client):
    resp = client.get('/auth/login')
    assert resp.status_code == 200


def test_login_with_valid_credentials(client, test_user):
    # Login now requires a verified email
    test_user.email_verified_at = datetime.utcnow()
    db.session.commit()

    resp = client.post('/auth/login', data={
        'email': 'testuser@test.com',
        'password': 'password123',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


def test_login_unverified_email_allowed(client, test_user):
    """Soft verification: unverified users log in normally — the dashboard
    banner nags them instead of a wall."""
    assert test_user.email_verified_at is None

    resp = client.post('/auth/login', data={
        'email': 'testuser@test.com',
        'password': 'password123',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


def test_admin_login_skips_email_verification(client, test_user):
    # Admins must never be gated on email verification
    test_user.email_verified_at = None
    test_user.is_verified = False
    test_user.is_admin = True
    db.session.commit()

    resp = client.post('/auth/login', data={
        'email': 'testuser@test.com',
        'password': 'password123',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/admin' in resp.headers['Location']

    db.session.refresh(test_user)
    assert test_user.email_verified_at is not None
    assert test_user.is_verified is True


def test_login_with_invalid_credentials(client, test_user):
    resp = client.post('/auth/login', data={
        'email': 'testuser@test.com',
        'password': 'wrongpassword',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_login_with_nonexistent_user(client):
    resp = client.post('/auth/login', data={
        'email': 'nonexistent@example.com',
        'password': 'whatever',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_logout_clears_session(logged_in_client):
    resp = logged_in_client.get('/auth/logout', follow_redirects=False)
    assert resp.status_code == 302

    with logged_in_client.session_transaction() as sess:
        assert '_user_id' not in sess


def test_protected_route_requires_login(client):
    resp = client.get('/dashboard', follow_redirects=False)
    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_protected_route_accessible_when_logged_in(logged_in_client):
    resp = logged_in_client.get('/dashboard', follow_redirects=False)
    assert resp.status_code == 200

def test_signup_blank_phone_can_be_used_twice(client, app):
    """Regression: phone is Optional in the form but the column used to be
    NOT NULL UNIQUE — the first blank phone took the single '' slot, so every
    later blank-phone signup died with the generic 'Could not create' error."""
    for i in (1, 2):
        # Signup now auto-logs-in — log out so the next POST reaches signup
        # instead of the already-authenticated redirect.
        client.get('/auth/logout', follow_redirects=False)
        resp = client.post('/auth/signup', data={
            'owner_name': f'No Phone {i}',
            'phone': '',
            'email': f'nophone{i}@example.com',
            'password': 'secure123',
            'confirm_password': 'secure123',
            'language': 'en',
            'shop_name': f'NoPhone Shop {i}',
            'total_investment': '1000',
        }, follow_redirects=True)
        html = resp.get_data(as_text=True)
        assert 'Could not create your account' not in html, f'attempt {i} failed'
        assert 'Account created' in html, f'attempt {i}: {html[:200]}'

    with app.app_context():
        users = User.query.filter(
            User.email.in_(['nophone1@example.com', 'nophone2@example.com'])
        ).all()
        assert len(users) == 2
        assert all(u.phone is None for u in users)


def test_verify_banner_shows_for_unverified_user(logged_in_client):
    resp = logged_in_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Verify your email' in html
    assert '/auth/resend-verification' in html


def test_verify_banner_hidden_for_verified_user(client, test_user):
    test_user.email_verified_at = datetime.utcnow()
    db.session.commit()

    client.post('/auth/login', data={
        'email': 'testuser@test.com',
        'password': 'password123',
    }, follow_redirects=False)
    html = client.get('/dashboard').get_data(as_text=True)
    assert 'Verify your email' not in html


def test_verify_banner_session_dismiss(logged_in_client):
    resp = logged_in_client.get('/auth/dismiss-verify-banner', follow_redirects=False)
    assert resp.status_code == 302

    html = logged_in_client.get('/dashboard').get_data(as_text=True)
    assert 'Verify your email' not in html


def test_verify_link_while_logged_in_returns_to_dashboard(client, app):
    client.post('/auth/signup', data={
        'owner_name': 'Token User',
        'phone': '',
        'email': 'tokenuser@example.com',
        'password': 'secure123',
        'confirm_password': 'secure123',
        'language': 'en',
        'shop_name': 'Token Shop',
        'total_investment': '1000',
    }, follow_redirects=False)

    with app.app_context():
        user = User.query.filter_by(email='tokenuser@example.com').first()
        assert user is not None and user.email_verified_at is None
        token = user.verification_token
        assert token

    resp = client.get(f'/auth/verify/{token}', follow_redirects=False)
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']

    with app.app_context():
        user = User.query.filter_by(email='tokenuser@example.com').first()
        assert user.email_verified_at is not None

    html = client.get('/dashboard').get_data(as_text=True)
    assert 'Verify your email' not in html


def test_banner_resend_returns_to_next(logged_in_client):
    resp = logged_in_client.post('/auth/resend-verification', data={
        'email': 'testuser@test.com',
        'next': '/dashboard',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


def test_banner_resend_rejects_external_next(client):
    resp = client.post('/auth/resend-verification', data={
        'email': 'anyone@example.com',
        'next': 'https://evil.example.com/phish',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert 'evil.example.com' not in resp.headers['Location']
