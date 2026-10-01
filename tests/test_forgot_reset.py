"""Forgot / reset password: discoverable from login, and it really changes the password.

The routes, forms and templates already existed — what was missing was a link
on the login page and any end-to-end coverage of the flow.
"""
from datetime import datetime, timedelta

from app.extensions import db
from app.models.email_log import EmailLog


def test_login_page_links_to_forgot_password(client):
    page = client.get('/auth/login').get_data(as_text=True)
    assert '/auth/forgot' in page
    assert 'Forgot password?' in page


def test_forgot_page_loads(client):
    assert client.get('/auth/forgot').status_code == 200


def test_forgot_unknown_email_uses_the_same_message_and_sends_nothing(client):
    resp = client.post('/auth/forgot', data={'email': 'nobody@example.com'},
                       follow_redirects=True)

    assert resp.status_code == 200
    assert 'If an account exists' in resp.get_data(as_text=True)
    assert EmailLog.query.count() == 0, 'must not reveal whether the address exists'


def test_forgot_known_email_issues_a_token_and_sends(client, test_user):
    resp = client.post('/auth/forgot', data={'email': test_user.email},
                       follow_redirects=True)

    assert resp.status_code == 200
    assert 'If an account exists' in resp.get_data(as_text=True)

    db.session.refresh(test_user)
    assert test_user.reset_token, 'a reset token must be stored'
    assert test_user.reset_token_expiry > datetime.utcnow()

    log = EmailLog.query.order_by(EmailLog.id.desc()).first()
    assert log.email_type == 'password_reset'
    assert log.recipient_email == test_user.email
    assert log.status == 'sent'


def test_reset_page_renders_for_a_valid_token(client, test_user):
    token = test_user.generate_reset_token()
    db.session.commit()

    resp = client.get(f'/auth/reset/{token}')
    assert resp.status_code == 200
    assert 'password' in resp.get_data(as_text=True).lower()


def test_reset_rejects_a_bad_token(client):
    resp = client.get('/auth/reset/not-a-real-token', follow_redirects=False)
    assert resp.status_code == 302
    assert '/auth/forgot' in resp.headers['Location']


def test_reset_rejects_an_expired_token(client, test_user):
    test_user.generate_reset_token()
    test_user.reset_token_expiry = datetime.utcnow() - timedelta(minutes=5)
    db.session.commit()

    resp = client.get(f'/auth/reset/{test_user.reset_token}', follow_redirects=False)
    assert resp.status_code == 302
    assert '/auth/forgot' in resp.headers['Location']


def test_reset_changes_the_password_and_clears_the_token(client, test_user):
    token = test_user.generate_reset_token()
    db.session.commit()

    resp = client.post(f'/auth/reset/{token}', data={
        'password': 'brandnewpass',
        'confirm_password': 'brandnewpass',
    }, follow_redirects=False)

    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']

    db.session.refresh(test_user)
    assert test_user.check_password('brandnewpass')
    assert not test_user.check_password('password123')
    assert test_user.reset_token is None

    # The old link is now dead.
    resp = client.get(f'/auth/reset/{token}', follow_redirects=False)
    assert '/auth/forgot' in resp.headers['Location']


def test_reset_rejects_a_mismatched_confirmation(client, test_user):
    token = test_user.generate_reset_token()
    db.session.commit()

    resp = client.post(f'/auth/reset/{token}', data={
        'password': 'brandnewpass',
        'confirm_password': 'differentpass',
    }, follow_redirects=True)

    assert resp.status_code == 200
    db.session.refresh(test_user)
    assert test_user.check_password('password123'), 'password must be unchanged'
    assert test_user.reset_token is not None
