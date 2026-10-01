from flask import current_app, render_template
from flask_mail import Message
from app.extensions import mail, db
from datetime import datetime


def _record_log_result(email_log_id, sent, error=None):
    """Write the final status of a send onto its log row.

    Deliberately avoids touching an ORM instance: the instance is expired by the
    previous commit, so reading it back would issue a SELECT on whatever
    connection is checked out. MySQL frequently drops that connection while a
    slow SMTP send is in progress ("server has gone away"), and letting the
    write fail would turn a successfully delivered email into a 500 page.

    Never raises — a logging failure must not break the caller.
    """
    from app.models.email_log import EmailLog

    now = datetime.utcnow()
    payload = {
        'status': 'sent' if sent else 'failed',
        'error_message': None if sent else (error or 'Unknown error'),
        'sent_at': now if sent else None,
        'failed_at': None if sent else now,
    }
    try:
        db.session.rollback()
        EmailLog.query.filter_by(id=email_log_id).update(payload, synchronize_session=False)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f'Could not record email log {email_log_id}: {exc}')


def send_email(to, subject, template, email_type='general', user_id=None, **kwargs):
    """Send an email using Flask-Mail with logging."""
    from app.models.email_log import EmailLog

    html_content = None
    error = None

    try:
        # Absolute URL so remote mail clients can fetch the brand logo.
        kwargs.setdefault(
            'logo_url',
            f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}"
            f"/static/img/logo-light.png",
        )
        html_content = render_template(f'emails/{template}.html', **kwargs)
    except Exception as e:
        error = f'Failed to render emails/{template}.html: {e}'
        current_app.logger.error(f'Email template error for {to}: {e}')

    if error is None and not current_app.config.get('MAIL_USERNAME'):
        error = 'Email not configured (MAIL_USERNAME missing)'
        current_app.logger.warning('Email not configured, skipping send')

    # Create email log entry — all ORM work happens BEFORE the send, so no
    # transaction is held open across the (potentially long) SMTP call.
    email_log = EmailLog(
        user_id=user_id,
        recipient_email=to,
        subject=subject,
        email_type=email_type,
        status='pending',
        provider='smtp',
        body_preview=(html_content or '')[:500] or None,
    )
    db.session.add(email_log)
    db.session.flush()
    log_id = email_log.id
    db.session.commit()

    sent = False
    if error is None:
        try:
            msg = Message(
                subject=subject,
                recipients=[to],
                html=html_content,
                sender=current_app.config.get('MAIL_DEFAULT_SENDER')
            )
            mail.send(msg)
            sent = True
            current_app.logger.info(f'Email sent successfully to {to}: {subject}')
        except Exception as e:
            error = str(e)
            current_app.logger.error(f'Failed to send email to {to}: {e}')

    _record_log_result(log_id, sent, error)
    return sent


def send_verification_email(user):
    """Send email verification link to user."""
    return send_email(
        to=user.email,
        subject='Verify your email — Mubashar Khata',
        template='verify_email',
        email_type='verification',
        user_id=user.id,
        user=user,
        verify_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/auth/verify/{user.verification_token}"
    )


def send_password_reset_email(user):
    """Send password reset link to user."""
    return send_email(
        to=user.email,
        subject='Reset your password — Mubashar Khata',
        template='reset_password',
        email_type='password_reset',
        user_id=user.id,
        user=user,
        reset_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/auth/reset/{user.reset_token}"
    )


def send_welcome_email(user):
    """Send welcome email after verification."""
    return send_email(
        to=user.email,
        subject='Welcome to Mubashar Khata!',
        template='welcome',
        email_type='welcome',
        user_id=user.id,
        user=user,
        dashboard_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/dashboard"
    )


def send_trial_reminder_email(user, days_left):
    """Send trial reminder email."""
    template = 'trial_reminder_3days' if days_left == 3 else 'trial_reminder_1day'
    return send_email(
        to=user.email,
        subject=f'Your trial ends in {days_left} day{"s" if days_left > 1 else ""} — Mubashar Khata',
        template=template,
        email_type='trial_reminder',
        user_id=user.id,
        user=user,
        days_left=days_left,
        dashboard_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/dashboard"
    )


def send_trial_expired_email(user):
    """Send trial expired notification."""
    return send_email(
        to=user.email,
        subject='Your trial has expired — Mubashar Khata',
        template='trial_expired',
        email_type='trial_expired',
        user_id=user.id,
        user=user,
        dashboard_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/dashboard"
    )



def send_payment_received_email(user, payment):
    """Send payment received confirmation to user."""
    return send_email(
        to=user.email,
        subject='Payment received — Awaiting verification',
        template='payment_received',
        email_type='payment_received',
        user_id=user.id,
        user=user,
        payment=payment,
        status_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/subscription/payment/{payment.id}"
    )


def send_payment_verified_email(user, payment, subscription):
    """Send payment verified and subscription activated email."""
    return send_email(
        to=user.email,
        subject='🎉 Payment verified — Subscription activated!',
        template='payment_verified',
        email_type='payment_verified',
        user_id=user.id,
        user=user,
        payment=payment,
        subscription=subscription,
        dashboard_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/dashboard"
    )


def send_payment_rejected_email(user, payment, reason):
    """Send payment rejection notification."""
    return send_email(
        to=user.email,
        subject='Payment verification issue — Action required',
        template='payment_rejected',
        email_type='payment_rejected',
        user_id=user.id,
        user=user,
        payment=payment,
        reason=reason,
        subscribe_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/subscription/subscribe"
    )
