"""Email delivery: the admin context processor must never break a send.

Emails are rendered outside a request (signup side effects, background jobs).
`current_user` is None there, and `inject_admin_badges` used to raise
AttributeError on it — `send_email` caught the error and marked every email
failed, so nothing ever reached the inbox.
"""
from flask import render_template

from app.extensions import db
from app.models.email_log import EmailLog


def test_admin_badge_processor_is_inert_outside_a_request(app):
    from app.admin.routes import inject_admin_badges

    with app.app_context():
        # No request context at all — this must not raise.
        assert inject_admin_badges() == {}


def test_verification_email_sends_with_no_request_context(app, test_user):
    from app.utils.email import send_verification_email

    test_user.generate_verification_token()
    db.session.commit()

    with app.app_context():
        # Exactly the situation a background job runs in: app context only.
        assert send_verification_email(test_user) is True

    log = EmailLog.query.order_by(EmailLog.id.desc()).first()
    assert log.status == 'sent'
    assert log.error_message is None
    assert log.recipient_email == test_user.email
    assert log.email_type == 'verification'


def test_password_reset_email_sends_with_no_request_context(app, test_user):
    from app.utils.email import send_password_reset_email

    test_user.generate_reset_token()
    db.session.commit()

    with app.app_context():
        assert send_password_reset_email(test_user) is True

    log = EmailLog.query.order_by(EmailLog.id.desc()).first()
    assert log.status == 'sent'
    assert log.email_type == 'password_reset'


def test_config_exposes_base_url_for_email_links(app):
    """email.py falls back to localhost when BASE_URL is missing from config."""
    assert app.config.get('BASE_URL'), 'BASE_URL must be configured'


def test_verification_link_uses_configured_base_url(app, test_user):
    test_user.generate_verification_token()
    db.session.commit()

    html = render_template(
        'emails/verify_email.html',
        user=test_user,
        verify_url=f"{app.config['BASE_URL']}/auth/verify/{test_user.verification_token}",
    )
    assert app.config['BASE_URL'] in html


# ── inside a request (the paths a person actually clicks) ──


def test_signup_sends_the_verification_email(client, app):
    resp = client.post('/auth/signup', data={
        'owner_name': 'Mail Recipient',
        'phone': '03001112233',
        'email': 'mailrecipient@example.com',
        'password': 'secure123',
        'confirm_password': 'secure123',
        'language': 'en',
        'shop_name': 'Mail Shop',
        'total_investment': '1000',
    }, follow_redirects=False)
    assert resp.status_code == 302

    log = EmailLog.query.order_by(EmailLog.id.desc()).first()
    assert log is not None, 'signup must log the verification email'
    assert log.email_type == 'verification'
    assert log.recipient_email == 'mailrecipient@example.com'
    assert log.status == 'sent'
    assert log.error_message is None


def test_admin_test_email_reports_success(app, test_user):
    test_user.is_admin = True
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)

    resp = client.post('/admin/test-email', data={
        'user_id': test_user.id,
        'email_type': 'verification',
    }, follow_redirects=True)

    page = resp.get_data(as_text=True)
    assert 'Failed to send email' not in page
    assert f'Test email sent successfully to {test_user.email}' in page

    log = EmailLog.query.order_by(EmailLog.id.desc()).first()
    assert log.status == 'sent'
    assert log.error_message is None
