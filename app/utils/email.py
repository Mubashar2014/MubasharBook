from flask import current_app, render_template
from flask_mail import Message
from app.extensions import mail


def send_email(to, subject, template, **kwargs):
    """Send an email using Flask-Mail."""
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.warning('Email not configured, skipping send')
        return False

    try:
        msg = Message(
            subject=subject,
            recipients=[to],
            html=render_template(f'emails/{template}.html', **kwargs),
            sender=current_app.config.get('MAIL_DEFAULT_SENDER')
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send email to {to}: {e}')
        return False


def send_verification_email(user):
    """Send email verification link to user."""
    return send_email(
        to=user.email,
        subject='Verify your email — Mubashar\'s Book',
        template='verify_email',
        user=user,
        verify_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/auth/verify/{user.verification_token}"
    )


def send_password_reset_email(user):
    """Send password reset link to user."""
    return send_email(
        to=user.email,
        subject='Reset your password — Mubashar\'s Book',
        template='reset_password',
        user=user,
        reset_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/auth/reset/{user.reset_token}"
    )


def send_welcome_email(user):
    """Send welcome email after verification."""
    return send_email(
        to=user.email,
        subject='Welcome to Mubashar\'s Book!',
        template='welcome',
        user=user,
        dashboard_url=f"{current_app.config.get('BASE_URL', 'http://localhost:5050')}/dashboard"
    )