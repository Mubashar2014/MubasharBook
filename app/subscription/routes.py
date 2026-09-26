"""
Subscription and payment routes.
Handles manual payment submission and verification.
"""

import os
import uuid
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.subscription import subscription_bp
from app.extensions import db
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.utils.pricing import get_plan_price, PLANS


def allowed_file(filename):
    """Check if file extension is allowed for payment proof."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@subscription_bp.route('/subscribe')
@login_required
def subscribe():
    """Subscription page - choose plan and billing cycle."""
    if current_user.is_admin:
        flash('Admin accounts do not need subscriptions.', 'info')
        return redirect(url_for('admin.dashboard'))
    
    subscription = current_user.shop.subscription if current_user.shop else None
    
    return render_template('subscription/subscribe.html',
        subscription=subscription,
        plans=PLANS
    )


@subscription_bp.route('/subscribe/<plan>/<billing_cycle>')
@login_required
def payment_instructions(plan, billing_cycle):
    """Show payment instructions for selected plan."""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    
    if plan not in ['basic', 'premium']:
        flash('Invalid plan selected.', 'danger')
        return redirect(url_for('subscription.subscribe'))
    
    if billing_cycle not in ['monthly', 'annual']:
        flash('Invalid billing cycle.', 'danger')
        return redirect(url_for('subscription.subscribe'))
    
    amount = get_plan_price(plan, billing_cycle)
    plan_info = PLANS[plan]
    
    return render_template('subscription/payment_instructions.html',
        plan=plan,
        plan_info=plan_info,
        billing_cycle=billing_cycle,
        amount=amount
    )


@subscription_bp.route('/submit-payment', methods=['POST'])
@login_required
def submit_payment():
    """Submit payment proof for verification."""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    
    plan = request.form.get('plan')
    billing_cycle = request.form.get('billing_cycle')
    payment_method = request.form.get('payment_method')
    transaction_id = request.form.get('transaction_id', '').strip()
    notes = request.form.get('notes', '').strip()
    
    # Validate inputs
    if plan not in ['basic', 'premium']:
        flash('Invalid plan.', 'danger')
        return redirect(url_for('subscription.subscribe'))
    
    if billing_cycle not in ['monthly', 'annual']:
        flash('Invalid billing cycle.', 'danger')
        return redirect(url_for('subscription.subscribe'))
    
    if payment_method not in ['nayapay', 'bank_transfer', 'easypaisa', 'jazzcash']:
        flash('Invalid payment method.', 'danger')
        return redirect(url_for('subscription.subscribe'))
    
    # Handle file upload
    if 'payment_proof' not in request.files:
        flash('Please upload payment screenshot.', 'danger')
        return redirect(url_for('subscription.payment_instructions', 
            plan=plan, billing_cycle=billing_cycle))
    
    file = request.files['payment_proof']
    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('subscription.payment_instructions', 
            plan=plan, billing_cycle=billing_cycle))
    
    if not allowed_file(file.filename):
        flash('Invalid file type. Please upload PNG, JPG, or PDF.', 'danger')
        return redirect(url_for('subscription.payment_instructions', 
            plan=plan, billing_cycle=billing_cycle))
    
    # Save file
    try:
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"payment_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
        
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, unique_filename)
        file.save(filepath)
        
    except Exception as e:
        current_app.logger.error(f'Failed to save payment proof: {e}')
        flash('Failed to upload file. Please try again.', 'danger')
        return redirect(url_for('subscription.payment_instructions', 
            plan=plan, billing_cycle=billing_cycle))
    
    # Get subscription
    subscription = current_user.shop.subscription if current_user.shop else None
    if not subscription:
        flash('No subscription found.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Calculate amount
    amount = get_plan_price(plan, billing_cycle)
    
    # Create payment record
    payment = Payment(
        subscription_id=subscription.id,
        user_id=current_user.id,
        amount=amount,
        payment_method=payment_method,
        status='pending',
        gateway='manual',
        gateway_transaction_id=transaction_id or None,
        description=f'{plan.title()} Plan - {billing_cycle.title()} billing',
        notes=notes,
        payment_proof=unique_filename
    )
    db.session.add(payment)
    db.session.commit()
    
    # Send confirmation email
    from app.utils.email import send_payment_received_email
    send_payment_received_email(current_user, payment)
    
    flash('Payment submitted successfully! We will verify and activate your subscription within 24 hours.', 'success')
    return redirect(url_for('subscription.payment_status', payment_id=payment.id))


@subscription_bp.route('/payment/<int:payment_id>')
@login_required
def payment_status(payment_id):
    """Show payment verification status."""
    payment = Payment.query.get_or_404(payment_id)
    
    # Check ownership
    if payment.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    return render_template('subscription/payment_status.html', payment=payment)


@subscription_bp.route('/my-subscription')
@login_required
def my_subscription():
    """View current subscription details."""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    
    subscription = current_user.shop.subscription if current_user.shop else None
    if not subscription:
        flash('No subscription found.', 'info')
        return redirect(url_for('subscription.subscribe'))
    
    # Get payment history
    payments = Payment.query.filter_by(
        subscription_id=subscription.id
    ).order_by(Payment.created_at.desc()).all()
    
    return render_template('subscription/my_subscription.html',
        subscription=subscription,
        payments=payments
    )
