from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from sqlalchemy import func, or_
from app.admin import admin_bp
from app.admin.middleware import admin_required
from app.extensions import db
from app.models.user import User
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.admin_log import AdminLog


@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin dashboard with overview stats and user list."""
    
    # Get filter parameters
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Base query - get all users with LEFT JOIN (so users without shops still show)
    query = User.query.outerjoin(Shop).outerjoin(Subscription, Shop.id == Subscription.shop_id)
    
    # Apply search filter
    if search:
        query = query.filter(
            or_(
                User.owner_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.phone.ilike(f'%{search}%'),
                Shop.name.ilike(f'%{search}%')
            )
        )
    
    # Apply status filter
    if status_filter == 'trial':
        query = query.filter(Subscription.status == 'trial')
    elif status_filter == 'active':
        query = query.filter(Subscription.status == 'active')
    elif status_filter == 'expired':
        query = query.filter(Subscription.status == 'expired')
    elif status_filter == 'suspended':
        query = query.filter(Subscription.status == 'suspended')
    
    # Exclude admin users from the list
    query = query.filter(User.is_admin == False)
    
    # Paginate
    users_pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Calculate stats - simple counts without joins
    total_users = User.query.filter_by(is_admin=False).count()
    
    # Users by subscription status - only count those WITH subscriptions
    trial_users = db.session.query(func.count(Subscription.id)).join(
        Shop, Subscription.shop_id == Shop.id
    ).filter(
        Subscription.status == 'trial'
    ).scalar() or 0
    
    active_users = db.session.query(func.count(Subscription.id)).join(
        Shop, Subscription.shop_id == Shop.id
    ).filter(
        Subscription.status == 'active'
    ).scalar() or 0
    
    expired_users = db.session.query(func.count(Subscription.id)).join(
        Shop, Subscription.shop_id == Shop.id
    ).filter(
        Subscription.status == 'expired'
    ).scalar() or 0
    
    suspended_users = db.session.query(func.count(Subscription.id)).join(
        Shop, Subscription.shop_id == Shop.id
    ).filter(
        Subscription.status == 'suspended'
    ).scalar() or 0
    
    # New signups (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_signups = User.query.filter(
        User.is_admin == False,
        User.created_at >= week_ago
    ).count()
    
    # Total revenue (completed payments)
    total_revenue = db.session.query(func.sum(Payment.amount)).filter(
        Payment.status == 'completed'
    ).scalar() or 0
    
    # Pending payments count
    pending_payments_count = Payment.query.filter_by(status='pending').count()
    
    return render_template('admin/dashboard.html',
        users=users_pagination.items,
        pagination=users_pagination,
        total_users=total_users,
        trial_users=trial_users,
        active_users=active_users,
        expired_users=expired_users,
        suspended_users=suspended_users,
        new_signups=new_signups,
        total_revenue=float(total_revenue),
        pending_payments_count=pending_payments_count,
        search=search,
        status_filter=status_filter,
    )


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
    
    return render_template('admin/user_detail.html',
        user=user,
        shop=shop,
        subscription=subscription,
        payments=payments,
        admin_logs=admin_logs,
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
