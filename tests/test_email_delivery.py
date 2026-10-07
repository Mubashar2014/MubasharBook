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


# ── failure paths: the log write must never take the request down ──


def test_smtp_failure_marks_log_failed(app, test_user, monkeypatch):
    from app.extensions import mail
    from app.utils.email import send_verification_email

    def _boom(msg):
        raise ConnectionResetError(104, 'Connection reset by peer')

    monkeypatch.setattr(mail, 'send', _boom)

    with app.app_context():
        assert send_verification_email(test_user) is False

    log = EmailLog.query.order_by(EmailLog.id.desc()).first()
    assert log.status == 'failed'
    assert 'Connection reset' in log.error_message
    assert log.failed_at is not None


def test_stale_connection_on_log_write_does_not_break_send(app, test_user, monkeypatch):
    """Live bug: MySQL dropped the pooled connection during the SMTP send, then
    the 'mark as sent' SELECT raised 2006 and the error handler raised again —
    so a delivered email produced a 500 page."""
    from sqlalchemy.exc import OperationalError

    from app.utils.email import send_verification_email

    class _DeadConnection:
        def filter_by(self, **kwargs):
            raise OperationalError('SELECT', {}, Exception('MySQL server has gone away'))

    monkeypatch.setattr(EmailLog, 'query', _DeadConnection())

    with app.app_context():
        # Must not raise, and the send itself still counts as delivered.
        assert send_verification_email(test_user) is True


def test_missing_template_marks_log_failed(app, test_user):
    from app.utils.email import send_email

    with app.app_context():
        assert send_email(
            to=test_user.email,
            subject='Broken',
            template='does_not_exist',
            email_type='verification',
        ) is False

    log = EmailLog.query.order_by(EmailLog.id.desc()).first()
    assert log.status == 'failed'
    assert 'does_not_exist' in log.error_message


# ── admin-triggered notifications: trial extended / package allotted ──


def test_trial_extended_email_renders_days_and_new_end(app, test_user):
    from datetime import datetime, timedelta

    end = datetime.utcnow() + timedelta(days=14)
    html = render_template(
        'emails/trial_extended.html',
        user=test_user,
        days=7,
        trial_end=end,
        dashboard_url=f"{app.config['BASE_URL']}/dashboard",
        logo_url=f"{app.config['BASE_URL']}/static/img/logo-light.png",
    )
    assert 'Trial extended!' in html
    assert '7 days' in html
    assert end.strftime('%d %B %Y') in html
    assert test_user.owner_name in html


def test_package_allotted_email_renders_details_and_optional_rows(app, test_user):
    from datetime import datetime, timedelta

    end = datetime.utcnow() + timedelta(days=30)
    base = dict(
        user=test_user,
        plan='premium',
        duration_text='1 month',
        period_end=end,
        dashboard_url=f"{app.config['BASE_URL']}/dashboard",
        logo_url=f"{app.config['BASE_URL']}/static/img/logo-light.png",
    )

    html = render_template('emails/package_allotted.html', amount=1500,
                           notes='bank slip received', **base)
    assert 'Premium plan activated!' in html
    assert '1 month' in html
    assert end.strftime('%d %B %Y') in html
    assert 'Rs 1,500' in html
    assert 'bank slip received' in html

    html = render_template('emails/package_allotted.html', **base)  # quick-activate: no amount
    assert 'Rs 1,500' not in html
    assert 'bank slip received' not in html
    assert 'Amount' not in html


def test_send_trial_extended_email_logs_user_and_admin_copy(app, test_user):
    from datetime import datetime, timedelta

    from app.models.user import User
    from app.utils.email import send_trial_extended_email

    admin = User(
        owner_name='Copy Admin', phone='03009990001',
        email='copyadmin@test.com', language='en',
        is_admin=True, is_verified=True,
    )
    admin.set_password('password123')
    db.session.add(admin)
    db.session.commit()

    with app.app_context():
        assert send_trial_extended_email(
            test_user, 3, datetime.utcnow() + timedelta(days=3),
        ) is True

    logs = EmailLog.query.filter_by(email_type='trial_extended') \
        .order_by(EmailLog.id).all()
    assert [log.recipient_email for log in logs] == [test_user.email, 'copyadmin@test.com']
    assert all(log.status == 'sent' for log in logs)
    assert logs[1].user_id == admin.id


def test_admin_copy_skips_primary_when_primary_is_admin(app, test_user):
    from datetime import datetime, timedelta

    from app.utils.email import send_package_allotted_email

    test_user.is_admin = True
    db.session.commit()

    with app.app_context():
        assert send_package_allotted_email(
            test_user,
            plan='basic',
            duration_text='1 month',
            period_end=datetime.utcnow() + timedelta(days=30),
        ) is True

    logs = EmailLog.query.filter_by(email_type='package_allotted').all()
    assert len(logs) == 1                      # no self-copy
    assert logs[0].recipient_email == test_user.email


def test_test_email_panel_sends_new_notification_types(app, test_user):
    test_user.is_admin = True
    db.session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)

    # Both new dropdown options must render and send
    page = client.get('/admin/test-email').get_data(as_text=True)
    assert 'value="trial_extended"' in page
    assert 'value="package_allotted"' in page

    for email_type in ('trial_extended', 'package_allotted'):
        resp = client.post('/admin/test-email', data={
            'user_id': test_user.id,
            'email_type': email_type,
        }, follow_redirects=True)
        page = resp.get_data(as_text=True)
        assert 'Failed to send email' not in page
        assert f'Test email sent successfully to {test_user.email}' in page

    assert EmailLog.query.filter_by(email_type='trial_extended').count() == 1
    assert EmailLog.query.filter_by(email_type='package_allotted').count() == 1


def test_verification_email_copies_admin_without_cascade(client, app):
    """Every email now copies admins (send_email-level); copies must not
    cascade to other admins' copies."""
    from app.models.user import User

    admin = User(
        owner_name='All Mail Admin', phone='03009990002',
        email='alldomainadmin@test.com', language='en',
        is_admin=True, is_verified=True,
    )
    admin.set_password('password123')
    db.session.add(admin)
    db.session.commit()

    resp = client.post('/auth/signup', data={
        'owner_name': 'Copy Target',
        'phone': '03009990003',
        'email': 'copytarget@test.com',
        'password': 'secure123',
        'confirm_password': 'secure123',
        'language': 'en',
        'shop_name': 'Copy Shop',
        'total_investment': '1000',
    }, follow_redirects=True)
    assert 'Account created' in resp.get_data(as_text=True)

    logs = EmailLog.query.filter_by(email_type='verification') \
        .order_by(EmailLog.id).all()
    recipients = sorted(log.recipient_email for log in logs)
    assert recipients == ['alldomainadmin@test.com', 'copytarget@test.com']
    assert all(log.status == 'sent' for log in logs)
