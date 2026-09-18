import pytest
from app import create_app
from app.extensions import db as _db
from app.models.user import User
from app.models.shop import Shop


@pytest.fixture(scope='function')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()


@pytest.fixture(scope='function')
def db_session(app):
    with app.app_context():
        _db.session.begin_nested()
        yield _db.session
        if _db.session.is_active:
            _db.session.rollback()


def _create_user(app, owner_name, phone, password='password123', is_premium=False):
    user = User(
        owner_name=owner_name,
        phone=phone,
        email=f'{owner_name.lower().replace(" ", "")}@test.com',
        language='en',
        is_premium=is_premium,
        is_verified=True,
    )
    user.set_password(password)
    _db.session.add(user)
    _db.session.flush()

    shop = Shop(user_id=user.id, name=f"{owner_name}'s Shop", initial_investment=100000)
    _db.session.add(shop)
    _db.session.flush()

    if not is_premium:
        user.start_trial(days=7)

    _db.session.commit()
    return user


@pytest.fixture
def test_user(app):
    return _create_user(app, 'Test User', '03001234567')


@pytest.fixture
def logged_in_client(client, test_user):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)
    return client


@pytest.fixture
def premium_user(app):
    return _create_user(app, 'Premium User', '03009876543', is_premium=True)


@pytest.fixture
def second_user(app):
    return _create_user(app, 'Second User', '03005551234')
