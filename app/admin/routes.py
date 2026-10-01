from datetime import datetime, date, timedelta
import calendar
import json
import os
from flask import (render_template, request, redirect, url_for, flash,
                   current_app, has_request_context)
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from app.admin import admin_bp
from app.admin.middleware import admin_required
from app.extensions import db
from app.models.user import User, Investor
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.admin_log import AdminLog
from app.models.stock import StockItem
from app.models.cashbook import CashEntry
from app.models.expense import Expense, ExpenseCategory
from app.models.khata import KhataEntry
from app.models.notification import Notification
from app.models.email_log import EmailLog
from app.models.shareholder import Partner, SplitRule, Period, PeriodSnapshot


@admin_bp.app_context_processor
def inject_admin_badges():
    """Sidebar badge for the admin panel.

    This is registered app-wide, so it runs for every template — including
    emails, which are often rendered with no request context at all (signup
    side effects, background jobs). There `current_user` is None, and
    touching it raised AttributeError, which aborted the render and made
    every email fail. Stay strictly inert outside an admin page.
    """
    if not has_request_context() or request.blueprint != 'admin':
        return {}
    if not (current_user.is_authenticated and getattr(current_user, 'is_admin', False)):
        return {}
    return {'pending_payments_count': Payment.query.filter_by(status='pending').count()}


@admin_bp.route('/')
@admin_required
def dashboard():
    """Overview: headline stats plus anything that needs attention right now.

    The searchable user list lives on its own page (admin.users) so this one
    stays a single-purpose screen.
    """
    total_users = User.query.filter_by(is_admin=False).count()

    def _status_count(status):
        # Distinct non-admin users whose shop is in this status. The admin's
        # own shop is excluded so the breakdown adds up to total_users.
        return db.session.query(func.count(func.distinct(User.id))).join(
            Shop, Shop.user_id == User.id
        ).join(
            Subscription, Subscription.shop_id == Shop.id
        ).filter(
            User.is_admin == False,
            Subscription.status == status,
        ).scalar() or 0

    trial_users = _status_count('trial')
    active_users = _status_count('active')
    expired_users = _status_count('expired')
    suspended_users = _status_count('suspended')

    week_ago = datetime.utcnow() - timedelta(days=7)
    new_signups = User.query.filter(
        User.is_admin == False,
        User.created_at >= week_ago
    ).count()

    total_revenue = db.session.query(func.sum(Payment.amount)).filter(
        Payment.status == 'completed'
    ).scalar() or 0

    pending_payments_count = Payment.query.filter_by(status='pending').count()

    # Trials ending within 3 days (including already-overdue)
    soon = datetime.utcnow() + timedelta(days=3)
    expiring_trials = (
        db.session.query(User, Subscription)
        .join(Shop, Shop.user_id == User.id)
        .join(Subscription, Subscription.shop_id == Shop.id)
        .filter(
            User.is_admin == False,
            Subscription.status == 'trial',
            Subscription.trial_end <= soon,
        )
        .order_by(Subscription.trial_end.asc())
        .limit(5)
        .all()
    )

    recent_signups = User.query.filter_by(is_admin=False).order_by(
        User.created_at.desc()
    ).limit(5).all()

    recent_activity = AdminLog.query.order_by(
        AdminLog.created_at.desc()
    ).limit(6).all()

    return render_template('admin/dashboard.html',
        total_users=total_users,
        trial_users=trial_users,
        active_users=active_users,
        expired_users=expired_users,
        suspended_users=suspended_users,
        new_signups=new_signups,
        total_revenue=float(total_revenue),
        pending_payments_count=pending_payments_count,
        expiring_trials=expiring_trials,
        recent_signups=recent_signups,
        recent_activity=recent_activity,
        today=date.today(),
    )


@admin_bp.route('/users')
@admin_required
def users():
    """Searchable, filterable user list."""
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 50

    # LEFT JOIN so users without shops still show
    query = User.query.outerjoin(Shop).outerjoin(Subscription, Shop.id == Subscription.shop_id)

    if search:
        query = query.filter(
            or_(
                User.owner_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.phone.ilike(f'%{search}%'),
                Shop.name.ilike(f'%{search}%')
            )
        )

    if status_filter == 'trial':
        query = query.filter(Subscription.status == 'trial')
    elif status_filter == 'active':
        query = query.filter(Subscription.status == 'active')
    elif status_filter == 'expired':
        query = query.filter(Subscription.status == 'expired')
    elif status_filter == 'suspended':
        query = query.filter(Subscription.status == 'suspended')

    query = query.filter(User.is_admin == False)

    users_pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('admin/users.html',
        users=users_pagination.items,
        pagination=users_pagination,
        search=search,
        status_filter=status_filter,
    )


def _count_user_data(user, shop):
    """Row counts shown in the delete-confirmation modal (and kept in the audit log)."""
    counts = {'User accounts': 1}
    if shop:
        sid = shop.id
        sub_ids = [r[0] for r in db.session.query(Subscription.id).filter(Subscription.shop_id == sid)]

        counts['Shop'] = 1
        counts['Subscription'] = len(sub_ids)
        counts['Investors'] = Investor.query.filter_by(shop_id=sid).count()
        counts['Shareholders'] = Partner.query.filter_by(shop_id=sid).count()
        counts['Split rules'] = SplitRule.query.filter_by(shop_id=sid).count()
        counts['Periods'] = Period.query.filter_by(shop_id=sid).count()
        counts['Period snapshots'] = PeriodSnapshot.query.filter_by(shop_id=sid).count()
        counts['Stock items'] = StockItem.query.filter_by(shop_id=sid).count()
        counts['Cashbook entries'] = CashEntry.query.filter_by(shop_id=sid).count()
        counts['Expenses'] = Expense.query.filter_by(shop_id=sid).count()
        counts['Expense categories'] = ExpenseCategory.query.filter_by(shop_id=sid).count()
        counts['Khata entries'] = KhataEntry.query.filter_by(shop_id=sid).count()
        counts['Payments'] = Payment.query.filter(
            or_(Payment.user_id == user.id, Payment.subscription_id.in_(sub_ids))
        ).count()

    counts['Notifications'] = Notification.query.filter_by(user_id=user.id).count()
    counts['Email logs'] = EmailLog.query.filter_by(user_id=user.id).count()
    return counts


def _revenue_for(user):
    """Completed payments that would disappear if this user were deleted."""
    return float(db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.user_id == user.id, Payment.status == 'completed'
    ).scalar() or 0)


@admin_bp.route('/user/<int:user_id>')
@admin_required
def user_detail(user_id):
    """View detailed information about a specific user."""
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash('Cannot view admin user details.', 'warning')
        return redirect(url_for('admin.dashboard'))
    
    shop = user.shop
    subscription = shop.subscription if shop else None
    
    # Get payment history
    payments = []
    if subscription:
        payments = Payment.query.filter_by(subscription_id=subscription.id).order_by(
            Payment.created_at.desc()
        ).all()
    
    # Get admin actions on this user
    admin_logs = AdminLog.query.filter(
        AdminLog.target_type == 'user',
        AdminLog.target_id == user_id
    ).order_by(AdminLog.created_at.desc()).limit(20).all()

    # Where "Back" should land, so a search is never thrown away
    back_args = {
        'search': request.args.get('search', '').strip(),
        'status': request.args.get('status', 'all'),
        'page': request.args.get('page', 1, type=int),
    }

    # Delete confirmation: email, or phone when the account has no email
    confirm_label = user.email or user.phone or ''
    confirm_hint = 'email' if user.email else 'phone number'

    return render_template('admin/user_detail.html',
        user=user,
        shop=shop,
        subscription=subscription,
        payments=payments,
        admin_logs=admin_logs,
        back_args=back_args,
        data_counts=_count_user_data(user, shop),
        revenue_impact=_revenue_for(user),
        confirm_label=confirm_label,
        confirm_hint=confirm_hint,
    )


@admin_bp.route('/user/<int:user_id>/extend-trial', methods=['POST'])
@admin_required
def extend_trial(user_id):
    """Extend a user's trial period."""
    user = User.query.get_or_404(user_id)
    days = request.form.get('days', 7, type=int)
    
    if not user.shop:
        flash('User has no shop.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    subscription = user.shop.subscription
    if not subscription:
        flash('User has no subscription.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    # Extend trial
    if subscription.status == 'trial':
        subscription.trial_end = subscription.trial_end + timedelta(days=days)
        subscription.current_period_end = subscription.trial_end
        user.trial_end = subscription.trial_end
    else:
        # Reactivate trial
        subscription.activate_trial(days=days)
        user.trial_start = subscription.trial_start
        user.trial_end = subscription.trial_end
    
    # Log admin action
    AdminLog.log_action(
        admin_user_id=current_user.id,
        action='trial_extended',
        description=f'Extended trial by {days} days for {user.owner_name}',
        target_type='user',
        target_id=user_id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    db.session.commit()
    flash(f'Trial extended by {days} days.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/user/<int:user_id>/activate-subscription', methods=['POST'])
@admin_required
def activate_subscription(user_id):
    """Manually activate a user's paid subscription (for bank transfers)."""
    user = User.query.get_or_404(user_id)
    
    if not user.shop:
        flash('User has no shop.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    subscription = user.shop.subscription
    if not subscription:
        flash('User has no subscription.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    amount = request.form.get('amount', type=float)
    payment_method = request.form.get('payment_method', 'bank_transfer')
    notes = request.form.get('notes', '').strip()
    
    if not amount or amount <= 0:
        flash('Please enter a valid amount.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    # Activate subscription
    subscription.activate_subscription(payment_method=payment_method, billing_cycle='monthly')
    user.is_premium = True
    
    # Create payment record
    payment = Payment(
        subscription_id=subscription.id,
        user_id=user_id,
        amount=amount,
        payment_method=payment_method,
        status='completed',
        gateway='manual',
        description=f'Manual activation by admin',
        notes=notes,
        verified_by_admin=True,
        verified_at=datetime.utcnow()
    )
    db.session.add(payment)
    
    # Log admin action
    AdminLog.log_action(
        admin_user_id=current_user.id,
        action='subscription_activated',
        description=f'Manually activated subscription for {user.owner_name} - Rs {amount}',
        target_type='subscription',
        target_id=subscription.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    db.session.commit()
    flash(f'Subscription activated successfully. Rs {amount:,.0f} payment recorded.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


def _add_months(dt, months):
    """Calendar-accurate month addition (clamps day to month length)."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


@admin_bp.route('/user/<int:user_id>/quick-activate', methods=['POST'])
@admin_required
def quick_activate_subscription(user_id):
    """Quick activate subscription with plan and duration (no payment record)."""
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash('Cannot activate admin user subscription.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    if not user.shop:
        flash('User has no shop.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    subscription = user.shop.subscription
    if not subscription:
        flash('User has no subscription.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    plan = request.form.get('plan', '').strip()
    duration = request.form.get('duration', '').strip()
    custom_days = request.form.get('custom_days', type=int)
    notes = request.form.get('notes', '').strip()

    if plan not in ('basic', 'premium'):
        flash('Please select a valid plan.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    # Calculate duration (calendar-accurate, not months * 30)
    if duration == 'custom':
        if not custom_days or custom_days <= 0:
            flash('Please enter valid custom days.', 'danger')
            return redirect(url_for('admin.user_detail', user_id=user_id))
        now = datetime.utcnow()
        period_end = now + timedelta(days=custom_days)
        duration_text = f'{custom_days} days'
    elif duration in ('1', '2', '3', '6', '12'):
        months = int(duration)
        now = datetime.utcnow()
        period_end = _add_months(now, months)
        duration_text = '1 year' if months == 12 else f'{months} month(s)'
    else:
        flash('Please select a valid duration.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    # Activate subscription
    subscription.status = 'active'
    subscription.plan = plan
    subscription.current_period_start = now
    subscription.current_period_end = period_end
    subscription.next_billing_date = period_end
    subscription.payment_method = 'manual_admin'
    
    # Set premium flag
    user.is_premium = (plan == 'premium')
    
    # Log admin action
    AdminLog.log_action(
        admin_user_id=current_user.id,
        action='quick_activation',
        description=f'Quick activated {plan.title()} plan for {user.owner_name} - Duration: {duration_text}. Notes: {notes or "None"}',
        target_type='subscription',
        target_id=subscription.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    db.session.commit()
    
    flash(f'✅ Subscription activated! {plan.title()} plan for {duration_text}. Expires: {subscription.current_period_end.strftime("%Y-%m-%d")}', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/user/<int:user_id>/suspend', methods=['POST'])
@admin_required
def suspend_user(user_id):
    """Suspend a user's account."""
    user = User.query.get_or_404(user_id)
    reason = request.form.get('reason', '').strip()
    
    if not user.shop or not user.shop.subscription:
        flash('User has no subscription.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    subscription = user.shop.subscription
    subscription.suspend(reason=reason)
    user.is_active = False
    
    # Log admin action
    AdminLog.log_action(
        admin_user_id=current_user.id,
        action='user_suspended',
        description=f'Suspended {user.owner_name}. Reason: {reason}',
        target_type='user',
        target_id=user_id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    db.session.commit()
    flash('User suspended.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/user/<int:user_id>/unsuspend', methods=['POST'])
@admin_required
def unsuspend_user(user_id):
    """Reactivate a suspended user."""
    user = User.query.get_or_404(user_id)
    
    if not user.shop or not user.shop.subscription:
        flash('User has no subscription.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    subscription = user.shop.subscription
    subscription.unsuspend()
    user.is_active = True
    
    # Log admin action
    AdminLog.log_action(
        admin_user_id=current_user.id,
        action='user_unsuspended',
        description=f'Unsuspended {user.owner_name}',
        target_type='user',
        target_id=user_id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    db.session.commit()
    flash('User reactivated.', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


# ====== EMAIL TESTING & MANAGEMENT ======

@admin_bp.route('/test-email', methods=['GET', 'POST'])
@admin_required
def test_email():
    """Test email sending functionality."""
    from app.utils.email import (
        send_verification_email, 
        send_welcome_email, 
        send_trial_reminder_email,
        send_trial_expired_email
    )
    
    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        email_type = request.form.get('email_type')
        
        if not user_id:
            flash('Please select a user.', 'danger')
            return redirect(url_for('admin.test_email'))
        
        user = User.query.get(user_id)
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('admin.test_email'))
        
        # Send email based on type
        success = False
        if email_type == 'verification':
            user.generate_verification_token()
            db.session.commit()
            success = send_verification_email(user)
        elif email_type == 'welcome':
            success = send_welcome_email(user)
        elif email_type == 'trial_3days':
            success = send_trial_reminder_email(user, 3)
        elif email_type == 'trial_1day':
            success = send_trial_reminder_email(user, 1)
        elif email_type == 'trial_expired':
            success = send_trial_expired_email(user)
        else:
            flash('Invalid email type.', 'danger')
            return redirect(url_for('admin.test_email'))
        
        if success:
            flash(f'Test email sent successfully to {user.email}!', 'success')
        else:
            flash(f'Failed to send email. Check email configuration.', 'danger')
        
        return redirect(url_for('admin.test_email'))
    
    # GET request - show form
    users = User.query.filter_by(is_admin=False).order_by(User.owner_name).all()
    return render_template('admin/test_email.html', users=users)


@admin_bp.route('/send-trial-reminders', methods=['POST'])
@admin_required
def send_trial_reminders_manually():
    """Manually trigger trial reminder emails."""
    from app.utils.email import send_trial_reminder_email, send_trial_expired_email
    
    today = datetime.utcnow().date()
    sent_count = 0
    
    # Find users with trials ending in 3 days
    three_days = today + timedelta(days=3)
    users_3days = User.query.join(Shop).join(Subscription).filter(
        User.is_admin == False,
        Subscription.status == 'trial',
        func.date(Subscription.trial_end) == three_days
    ).all()
    
    for user in users_3days:
        if send_trial_reminder_email(user, 3):
            sent_count += 1
    
    # Find users with trials ending in 1 day
    one_day = today + timedelta(days=1)
    users_1day = User.query.join(Shop).join(Subscription).filter(
        User.is_admin == False,
        Subscription.status == 'trial',
        func.date(Subscription.trial_end) == one_day
    ).all()
    
    for user in users_1day:
        if send_trial_reminder_email(user, 1):
            sent_count += 1
    
    # Find users with trials expired today
    users_expired = User.query.join(Shop).join(Subscription).filter(
        User.is_admin == False,
        Subscription.status == 'trial',
        func.date(Subscription.trial_end) == today
    ).all()
    
    for user in users_expired:
        if send_trial_expired_email(user):
            sent_count += 1
            # Mark subscription as expired
            if user.shop and user.shop.subscription:
                user.shop.subscription.expire()
    
    db.session.commit()
    
    flash(f'Sent {sent_count} trial reminder emails.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/email-logs')
@admin_required
def email_logs():
    """View email send history."""
    from app.models.email_log import EmailLog
    
    page = request.args.get('page', 1, type=int)
    email_type = request.args.get('type', '')
    status = request.args.get('status', '')
    
    query = EmailLog.query
    
    if email_type:
        query = query.filter_by(email_type=email_type)
    
    if status:
        query = query.filter_by(status=status)
    
    logs_pagination = query.order_by(EmailLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    # Get stats
    total_sent = EmailLog.query.filter_by(status='sent').count()
    total_failed = EmailLog.query.filter_by(status='failed').count()
    total_pending = EmailLog.query.filter_by(status='pending').count()
    
    return render_template('admin/email_logs.html',
        logs=logs_pagination.items,
        pagination=logs_pagination,
        total_sent=total_sent,
        total_failed=total_failed,
        total_pending=total_pending,
        email_type_filter=email_type,
        status_filter=status,
    )


# ====== PAYMENT VERIFICATION ======

@admin_bp.route('/pending-payments')
@admin_required
def pending_payments():
    """View pending payment verifications."""
    page = request.args.get('page', 1, type=int)
    
    payments_pagination = Payment.query.filter_by(status='pending').order_by(
        Payment.created_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    
    return render_template('admin/pending_payments.html',
        payments=payments_pagination.items,
        pagination=payments_pagination
    )


@admin_bp.route('/payment/<int:payment_id>/verify', methods=['POST'])
@admin_required
def verify_payment(payment_id):
    """Verify and approve a payment."""
    payment = Payment.query.get_or_404(payment_id)
    
    if payment.status != 'pending':
        flash('Payment already processed.', 'warning')
        return redirect(url_for('admin.pending_payments'))
    
    # Mark payment as completed
    payment.status = 'completed'
    payment.verified_by_admin = True
    payment.verified_at = datetime.utcnow()
    
    # Get user and subscription
    user = payment.user
    subscription = payment.subscription
    
    # Determine plan from payment description
    plan = 'basic'
    if 'premium' in payment.description.lower():
        plan = 'premium'
    
    billing_cycle = 'monthly'
    if 'annual' in payment.description.lower():
        billing_cycle = 'annual'
    
    # Activate subscription
    subscription.activate_subscription(
        payment_method=payment.payment_method,
        billing_cycle=billing_cycle
    )
    subscription.plan = plan
    user.is_premium = (plan == 'premium')
    
    # Log admin action
    AdminLog.log_action(
        admin_user_id=current_user.id,
        action='payment_verified',
        description=f'Verified payment of Rs {payment.amount} for {user.owner_name}',
        target_type='payment',
        target_id=payment.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    db.session.commit()
    
    # Send confirmation email to user
    from app.utils.email import send_payment_verified_email
    send_payment_verified_email(user, payment, subscription)
    
    flash(f'Payment verified! Subscription activated for {user.owner_name}.', 'success')
    return redirect(url_for('admin.pending_payments'))


@admin_bp.route('/payment/<int:payment_id>/reject', methods=['POST'])
@admin_required
def reject_payment(payment_id):
    """Reject a payment."""
    payment = Payment.query.get_or_404(payment_id)
    
    if payment.status != 'pending':
        flash('Payment already processed.', 'warning')
        return redirect(url_for('admin.pending_payments'))
    
    reason = request.form.get('reason', '').strip()
    
    payment.status = 'failed'
    payment.notes = f"Rejected by admin: {reason}" if reason else "Rejected by admin"
    
    # Log admin action
    AdminLog.log_action(
        admin_user_id=current_user.id,
        action='payment_rejected',
        description=f'Rejected payment of Rs {payment.amount} for {payment.user.owner_name}. Reason: {reason}',
        target_type='payment',
        target_id=payment.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent')
    )
    
    db.session.commit()
    
    # TODO: Send rejection email to user
    
    flash(f'Payment rejected.', 'success')
    return redirect(url_for('admin.pending_payments'))


# ====== AUDIT LOG ======

@admin_bp.route('/activity')
@admin_required
def activity_log():
    """Every admin action, across all targets (the per-user page only shows 20)."""
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '').strip()
    admin_filter = request.args.get('admin', type=int)

    query = AdminLog.query
    if action_filter:
        query = query.filter(AdminLog.action == action_filter)
    if admin_filter:
        query = query.filter(AdminLog.admin_user_id == admin_filter)

    logs_pagination = query.order_by(AdminLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    actions = [r[0] for r in db.session.query(AdminLog.action).distinct().all()]
    admins = db.session.query(AdminLog.admin_user_id, User.owner_name).join(
        User, User.id == AdminLog.admin_user_id
    ).distinct().all()

    return render_template('admin/activity.html',
        logs=logs_pagination.items,
        pagination=logs_pagination,
        actions=sorted(actions),
        admins=admins,
        action_filter=action_filter,
        admin_filter=admin_filter,
    )


# ====== COMPLETE USER DELETION ======

def _payment_proof_files(user, shop):
    """Filenames of uploaded proof screenshots that belong to this user."""
    criteria = [Payment.user_id == user.id]
    if shop:
        sub_ids = [r[0] for r in db.session.query(Subscription.id).filter(Subscription.shop_id == shop.id)]
        if sub_ids:
            criteria = [or_(Payment.user_id == user.id, Payment.subscription_id.in_(sub_ids))]
    return [p.payment_proof for p in Payment.query.filter(*criteria).all() if p.payment_proof]


def _delete_user_rows(user, shop):
    """Hard-delete every row this user owns.

    All 17 foreign keys into users/shops are NO ACTION, so children must go
    first. Returns a {label: rows_deleted} dict for the audit log.
    """
    deleted = {}
    uid = user.id

    def _purge(label, query, *criteria):
        n = query.filter(*criteria).delete(synchronize_session=False)
        if n:
            deleted[label] = deleted.get(label, 0) + n

    if shop:
        sid = shop.id
        sub_ids = [r[0] for r in db.session.query(Subscription.id).filter(Subscription.shop_id == sid)]

        _purge('period snapshots', PeriodSnapshot.query, PeriodSnapshot.shop_id == sid)
        _purge('shareholders', Partner.query, Partner.shop_id == sid)
        _purge('investors', Investor.query, Investor.shop_id == sid)
        _purge('periods', Period.query, Period.shop_id == sid)
        _purge('split rules', SplitRule.query, SplitRule.shop_id == sid)
        _purge('khata entries', KhataEntry.query, KhataEntry.shop_id == sid)
        _purge('expenses', Expense.query, Expense.shop_id == sid)
        _purge('expense categories', ExpenseCategory.query, ExpenseCategory.shop_id == sid)
        _purge('cashbook entries', CashEntry.query, CashEntry.shop_id == sid)
        _purge('stock items', StockItem.query, StockItem.shop_id == sid)

        # payments reference both users and subscriptions -> before either
        _purge('payments', Payment.query,
               or_(Payment.user_id == uid, Payment.subscription_id.in_(sub_ids)))

        _purge('subscriptions', Subscription.query, Subscription.shop_id == sid)
    else:
        _purge('payments', Payment.query, Payment.user_id == uid)

    _purge('notifications', Notification.query, Notification.user_id == uid)
    _purge('email logs', EmailLog.query, EmailLog.user_id == uid)

    if shop:
        _purge('shop', Shop.query, Shop.user_id == uid)

    db.session.expunge(user)
    _purge('user account', User.query, User.id == uid)

    return deleted


@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Permanently delete a user and every row they own. Irreversible."""
    user = User.query.get_or_404(user_id)
    owner_name = user.owner_name

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    if user.is_admin:
        flash('Admin accounts cannot be deleted.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    # Type-to-confirm. Accounts may have no email, so fall back to the phone.
    confirm_label = user.email or user.phone or ''
    supplied = (request.form.get('confirm_text') or '').strip()

    if not confirm_label or supplied.lower() != confirm_label.lower():
        flash('Confirmation did not match — nothing was deleted.', 'danger')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    shop = user.shop
    counts = _count_user_data(user, shop)
    revenue = _revenue_for(user)
    proofs = _payment_proof_files(user, shop)
    summary = ', '.join(f'{v} {k.lower()}' for k, v in counts.items() if v)

    # Audit row first — its FK points at the admin, so it survives the purge
    AdminLog.log_action(
        admin_user_id=current_user.id,
        action='user_deleted',
        description=(
            f'Permanently deleted {owner_name} ({confirm_label}). '
            f'Removed: {summary}. Completed revenue removed: Rs {revenue:,.0f}.'
        ),
        target_type='user',
        target_id=user_id,
        changes=json.dumps({'counts': counts, 'revenue_removed': revenue}),
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
    )

    _delete_user_rows(user, shop)
    db.session.commit()

    # Proof screenshots only — after the commit so a failure here loses nothing.
    # static_folder is overridden in create_app(), so use it, not root_path.
    proof_dir = os.path.join(current_app.static_folder, 'payment_proofs')
    for fname in proofs:
        path = os.path.join(proof_dir, os.path.basename(fname))
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass

    flash(f'{owner_name} and all of their data were permanently deleted.', 'success')
    return redirect(url_for('admin.users'))


# ====== ADMIN'S OWN ACCOUNT ======

@admin_bp.route('/account', methods=['GET', 'POST'])
@admin_required
def account():
    """Profile + change password for the signed-in admin.

    Admins are redirected away from /settings by enforce_read_only(), so they
    need their own copy of those forms. Reuses the shared helpers and partials.
    """
    from app.auth.forms import ProfileForm, ChangePasswordForm
    from app.utils import apply_profile_update, apply_password_change

    which = request.form.get('form') if request.method == 'POST' else None
    profile_form = ProfileForm(obj=current_user)
    password_form = ChangePasswordForm()

    if which == 'password' and password_form.validate_on_submit():
        error = apply_password_change(
            current_user, password_form.current_password.data, password_form.password.data
        )
        if error:
            flash(error, 'warning')
        else:
            flash('Password changed. Use your new password the next time you log in.', 'success')
            return redirect(url_for('admin.account') + '#password')

    if which == 'profile' and profile_form.validate_on_submit():
        error = apply_profile_update(
            current_user, profile_form.owner_name.data, profile_form.phone.data,
            profile_form.language.data
        )
        if error:
            flash(error, 'warning')
        else:
            flash('Profile updated.', 'success')
            return redirect(url_for('admin.account') + '#profile')

    return render_template('admin/account.html',
                           profile_form=profile_form,
                           password_form=password_form)
