from app.models.user import User
from app.models.shop import Shop


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


def test_signup_redirects_to_dashboard(client, app):
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
    assert '/dashboard' in resp.headers['Location']


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
    resp = client.post('/auth/login', data={
        'phone': '03001234567',
        'password': 'password123',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


def test_login_with_invalid_credentials(client, test_user):
    resp = client.post('/auth/login', data={
        'phone': '03001234567',
        'password': 'wrongpassword',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_login_with_nonexistent_user(client):
    resp = client.post('/auth/login', data={
        'phone': '00000000000',
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