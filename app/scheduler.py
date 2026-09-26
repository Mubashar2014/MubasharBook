"""
Background scheduler for automated tasks.

Handles:
- Trial reminder emails (3 days, 1 day before expiry)
- Trial expiry notifications
- Subscription renewal checks
"""

from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from sqlalchemy import func
from app.extensions import db
from app.models.user import User
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.utils.email import (
    send_trial_reminder_email,
    send_trial_expired_email
)


def check_trial_reminders():
    """
    Check for trials ending soon and send reminder emails.
    Runs daily at 9:00 AM.
    """
    with current_app.app_context():
        today = datetime.utcnow().date()
        sent_count = 0
        
        current_app.logger.info('Running trial reminder check...')
        
        # Find users with trials ending in 3 days
        three_days_from_now = today + timedelta(days=3)
        users_3days = User.query.join(Shop).join(Subscription).filter(
            User.is_admin == False,
            User.email_verified_at.isnot(None),  # Only verified users
            Subscription.status == 'trial',
            func.date(Subscription.trial_end) == three_days_from_now
        ).all()
        
        for user in users_3days:
            try:
                if send_trial_reminder_email(user, 3):
                    sent_count += 1
                    current_app.logger.info(f'Sent 3-day reminder to {user.email}')
            except Exception as e:
                current_app.logger.error(f'Failed to send 3-day reminder to {user.email}: {e}')
        
        # Find users with trials ending in 1 day
        one_day_from_now = today + timedelta(days=1)
        users_1day = User.query.join(Shop).join(Subscription).filter(
            User.is_admin == False,
            User.email_verified_at.isnot(None),
            Subscription.status == 'trial',
            func.date(Subscription.trial_end) == one_day_from_now
        ).all()
        
        for user in users_1day:
            try:
                if send_trial_reminder_email(user, 1):
                    sent_count += 1
                    current_app.logger.info(f'Sent 1-day reminder to {user.email}')
            except Exception as e:
                current_app.logger.error(f'Failed to send 1-day reminder to {user.email}: {e}')
        
        current_app.logger.info(f'Trial reminders check complete. Sent {sent_count} emails.')


def check_trial_expiry():
    """
    Check for expired trials and send expiry notifications.
    Also marks subscriptions as expired.
    Runs daily at 12:00 AM (midnight).
    """
    with current_app.app_context():
        today = datetime.utcnow().date()
        expired_count = 0
        
        current_app.logger.info('Running trial expiry check...')
        
        # Find users whose trial ended today or before (but subscription still shows 'trial')
        users_expired = User.query.join(Shop).join(Subscription).filter(
            User.is_admin == False,
            User.email_verified_at.isnot(None),
            Subscription.status == 'trial',
            func.date(Subscription.trial_end) <= today
        ).all()
        
        for user in users_expired:
            try:
                # Mark subscription as expired
                subscription = user.shop.subscription
                subscription.expire()
                
                # Send expiry notification
                if send_trial_expired_email(user):
                    expired_count += 1
                    current_app.logger.info(f'Sent expiry email to {user.email}')
                
            except Exception as e:
                current_app.logger.error(f'Failed to process expiry for {user.email}: {e}')
        
        if expired_count > 0:
            db.session.commit()
        
        current_app.logger.info(f'Trial expiry check complete. Processed {expired_count} expirations.')


def check_subscription_renewals():
    """
    Check for subscriptions due for renewal.
    Runs daily at 3:00 AM.
    
    Future: Will integrate with payment gateway for auto-charging.
    """
    with current_app.app_context():
        today = datetime.utcnow().date()
        
        current_app.logger.info('Running subscription renewal check...')
        
        # Find subscriptions expiring in 3 days
        three_days_from_now = today + timedelta(days=3)
        subscriptions_due = Subscription.query.filter(
            Subscription.status == 'active',
            func.date(Subscription.current_period_end) == three_days_from_now
        ).all()
        
        # TODO: Send renewal reminder emails
        # TODO: Attempt auto-charge if payment method on file
        
        current_app.logger.info(f'Renewal check complete. Found {len(subscriptions_due)} subscriptions due soon.')


def init_scheduler(app):
    """
    Initialize the background scheduler with all jobs.
    
    Jobs:
    - check_trial_reminders: Daily at 9:00 AM
    - check_trial_expiry: Daily at 12:00 AM (midnight)
    - check_subscription_renewals: Daily at 3:00 AM
    """
    if not app.config.get('SCHEDULER_ENABLED', True):
        app.logger.info('Scheduler disabled by config')
        return None
    
    scheduler = BackgroundScheduler()
    
    # Add jobs with app context
    scheduler.add_job(
        func=check_trial_reminders,
        trigger='cron',
        hour=9,
        minute=0,
        id='trial_reminders',
        name='Check trial reminders',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=check_trial_expiry,
        trigger='cron',
        hour=0,
        minute=0,
        id='trial_expiry',
        name='Check trial expiry',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=check_subscription_renewals,
        trigger='cron',
        hour=3,
        minute=0,
        id='subscription_renewals',
        name='Check subscription renewals',
        replace_existing=True
    )
    
    scheduler.start()
    app.logger.info('Background scheduler started with 3 jobs')
    
    return scheduler
