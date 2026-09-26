from flask import current_app, render_template
from flask_mail import Message
from app.extensions import mail, db
from datetime import datetime


def send_email(to, subject, template, email_type='general', user_id=None, **kwargs):
    """Send an email using Flask-Mail with logging."""
    from app.models.email_log import EmailLog
    
    # Create email log entry
    email_log = EmailLog(
        user_id=user_id,
        recipient_email=to,
        subject=subject,
        email_type=email_type,
        status='pending',
        provider='smtp'
    )
    db.session.add(email_log)
    db.session.commit()
    
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.warning('Email not configured, skipping send')
        email_log.mark_failed('Email not configured (MAIL_USERNAME missing)')
        db.session.commit()
        return False

    try:
        html_content = render_template(f'emails/{template}.html', **kwargs)
        
        # Store preview of content
        email_log.body_preview = html_content[:500] if len(html_content) > 500 else html_content
        
        msg = Message(
            subject=subject,
            recipients=[to],
            html=html_content,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER')
        )
        mail.send(msg)
        
        # Mark as sent
        email_log.mark_sent()
        db.session.commit()
        
        current_app.logger.info(f'Email sent successfully to {to}: {subject}')
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send email to {to}: {e}')
        email_log.mark_failed(str(e))
        db.session.commit()
        return False


def send_verification_email(user):
    """Send email verification link to user."""
    return send_email(
        to=user.email,
        subject='Verify your email — Mubashar\'s Book',
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
        subject='Reset your password — Mubashar\'s Book',
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
        subject='Welcome to Mubashar\'s Book!',
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
        subject=f'Your trial ends in {days_left} day{"s" if days_left > 1 else ""} — Mubashar\'s Book',
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
        subject='Your trial has expired — Mubashar\'s Book',
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
