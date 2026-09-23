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
