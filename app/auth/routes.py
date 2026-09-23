import os
import uuid
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.auth.forms import SignupForm, LoginForm, ForgotPasswordForm, ResetPasswordForm, ResendVerificationForm
from app.extensions import db, mail
from app.models.user import User
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.utils.email import send_verification_email, send_password_reset_email, send_welcome_email
from app.utils import ensure_opening_cash


def _save_shop_image(file_storage, shop_id):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    fname = f"shop_{shop_id}_{uuid.uuid4().hex[:8]}.{ext}"
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, fname)
    file_storage.save(path)
    return f'uploads/{fname}'


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = SignupForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(phone=form.phone.data.strip()).first()
        if existing:
            flash('This phone number is already registered. Please log in.', 'warning')
            return redirect(url_for('auth.login'))

        existing_email = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if existing_email:
            flash('This email is already registered. Please log in or use a different email.', 'warning')
            return redirect(url_for('auth.login'))

        user = User(
            owner_name=form.owner_name.data.strip(),
            phone=form.phone.data.strip(),
            email=form.email.data.strip().lower(),
            language=form.language.data,
        )
        user.set_password(form.password.data)
        user.generate_verification_token()
        db.session.add(user)
        db.session.flush()

        shop_name = form.shop_name.data.strip() if form.shop_name.data and form.shop_name.data.strip() else form.owner_name.data.strip() + "'s Shop"
        shop = Shop(
            user_id=user.id,
            name=shop_name,
            initial_investment=form.total_investment.data or 0,
        )
        db.session.add(shop)
        db.session.flush()

        # Handle shop image upload
        if form.shop_image.data:
            img_path = _save_shop_image(form.shop_image.data, shop.id)
            if img_path:
                shop.shop_image = img_path

        user.start_trial(days=7)

        sub = Subscription(
            shop_id=shop.id,
            plan='basic',
            status='trial',
            trial_start=user.trial_start,
            trial_end=user.trial_end,
        )
        db.session.add(sub)
        ensure_opening_cash(shop)
        db.session.commit()

        # Auto-verify for development (remove when email is configured)
        user.is_verified = True
        user.clear_verification_token()
        db.session.commit()

        # Log the user in automatically after signup
        login_user(user)
        
        flash('Your 7-day free trial has started!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('auth/signup.html', form=form)


@auth_bp.route('/verify/<token>')
def verify_email_token(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('auth.verify_email'))

    if user.is_verified:
        flash('Email already verified. Please log in.', 'info')
        return redirect(url_for('auth.login'))

    user.verify_email()
    db.session.commit()

    # Send welcome email
    send_welcome_email(user)

    return render_template('auth/verify_email.html', success=True)


@auth_bp.route('/verify', methods=['GET', 'POST'])
def verify_email():
    email = request.args.get('email', '')
    return render_template('auth/verify_email.html', success=False, email=email)


@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email', '').strip().lower()
    if not email:
        flash('Email is required.', 'warning')
        return redirect(url_for('auth.verify_email'))

    user = User.query.filter_by(email=email).first()
    if not user:
        # Don't reveal if email exists
        flash('If an account exists, a verification email has been sent.', 'info')
        return redirect(url_for('auth.verify_email', email=email))

    if user.is_verified:
        flash('Email already verified. Please log in.', 'info')
        return redirect(url_for('auth.login'))

    user.generate_verification_token()
    db.session.commit()
    send_verification_email(user)

    flash('Verification email sent. Please check your inbox.', 'success')
    return redirect(url_for('auth.verify_email', email=email))


@auth_bp.route('/forgot', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()

        # Always show success to prevent email enumeration
        flash('If an account exists, a password reset link has been sent.', 'info')

        if user:
            user.generate_reset_token(expires_in=3600)  # 1 hour
            db.session.commit()
            send_password_reset_email(user)

        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.clear_reset_token()
        db.session.commit()
        flash('Password updated successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('Your account has been deactivated.', 'warning')
            return redirect(url_for('auth.login'))

        login_user(user)
        user.mark_login()
        db.session.commit()
        
        # Redirect admin users to admin panel
        if user.is_admin:
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('admin.dashboard'))
        
        flash('Welcome back, {}!'.format(user.owner_name), 'success')
        next_page = request.args.get('next')
        return redirect(next_page or url_for('main.dashboard'))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.landing'))