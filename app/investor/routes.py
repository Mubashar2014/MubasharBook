from functools import wraps
from datetime import date, timedelta
from decimal import Decimal
from flask import (
    render_template, redirect, url_for, flash, request, session, abort
)
from app.investor import investor_bp
from app.extensions import db
from app.models.user import Investor
from app.models.shareholder import Partner, Period, PeriodSnapshot
from app.models.stock import StockItem
from app.shareholders.engine import calculate_split


def investor_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'investor_id' not in session:
            flash('Please log in to access the investor portal.', 'warning')
            return redirect(url_for('investor.login'))
        return f(*args, **kwargs)
    return decorated


def get_current_investor():
    investor_id = session.get('investor_id')
    if not investor_id:
        return None
    return db.session.get(Investor, investor_id)


@investor_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'investor_id' in session:
        return redirect(url_for('investor.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return redirect(url_for('investor.login'))

        investor = Investor.query.filter_by(email=email).first()
        if investor is None or not investor.check_password(password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('investor.login'))

        if not investor.is_active:
            flash('Your account has been deactivated. Contact the shop owner.', 'warning')
            return redirect(url_for('investor.login'))

        session['investor_id'] = investor.id
        flash(f'Welcome back, {investor.name}!', 'success')
        return redirect(url_for('investor.dashboard'))

    return render_template('investor/login.html')


@investor_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('investor_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('investor.login'))


@investor_bp.route('/')
@investor_bp.route('/dashboard')
@investor_login_required
def dashboard():
    investor = get_current_investor()
    partner = Partner.query.filter_by(investor_user_id=investor.id).first()
    if not partner:
        flash('No partner record found for your account.', 'warning')
        return redirect(url_for('investor.login'))

    total_investment = db.session.query(
        db.func.coalesce(db.func.sum(Partner.investment_amount), 0)
    ).filter_by(shop_id=partner.shop_id).scalar()
    partner.investment_ratio = float(partner.investment_amount / total_investment * 100) if total_investment > 0 else 0

    today = date.today()
    current_period = Period.query.filter_by(shop_id=partner.shop_id).filter(
        Period.period_start <= today,
        Period.period_end >= today,
    ).first()

    current_estimate = Decimal('0')
    last_final = Decimal('0')
    last_period_label = None
    current_period_label = None

    if current_period:
        current_period_label = f"{current_period.period_start.strftime('%b %Y')} — {current_period.period_end.strftime('%b %Y')}"
        if current_period.status == 'open':
            from app.models.cashbook import CashEntry
            from app.models.expense import Expense

            cash_in = db.session.query(
                db.func.coalesce(db.func.sum(CashEntry.amount), 0)
            ).filter(
                CashEntry.shop_id == partner.shop_id,
                CashEntry.entry_type == 'in',
                CashEntry.entry_date >= current_period.period_start,
                CashEntry.entry_date <= current_period.period_end,
            ).scalar()

            cash_out = db.session.query(
                db.func.coalesce(db.func.sum(CashEntry.amount), 0)
            ).filter(
                CashEntry.shop_id == partner.shop_id,
                CashEntry.entry_type == 'out',
                CashEntry.entry_date >= current_period.period_start,
                CashEntry.entry_date <= current_period.period_end,
            ).scalar()

            expenses = db.session.query(
                db.func.coalesce(db.func.sum(Expense.amount), 0)
            ).filter(
                Expense.shop_id == partner.shop_id,
                Expense.expense_date >= current_period.period_start,
                Expense.expense_date <= current_period.period_end,
            ).scalar()

            net_profit = Decimal(str(cash_in)) - Decimal(str(cash_out)) - Decimal(str(expenses))
            split_result = calculate_split(partner.shop_id, net_profit)
            for s in split_result['splits']:
                if s['partner_id'] == partner.id:
                    current_estimate = s['share_amount']
                    break
        else:
            snapshot = PeriodSnapshot.query.filter_by(
                period_id=current_period.id,
                partner_id=partner.id,
            ).first()
            if snapshot:
                current_estimate = snapshot.share_amount

    last_locked = Period.query.filter_by(
        shop_id=partner.shop_id, status='locked'
    ).order_by(Period.period_end.desc()).first()

    if last_locked:
        last_period_label = last_locked.period_start.strftime('%b %Y')
        snapshot = PeriodSnapshot.query.filter_by(
            period_id=last_locked.id,
            partner_id=partner.id,
        ).first()
        if snapshot:
            last_final = snapshot.share_amount

    my_phones_count = StockItem.query.filter_by(
        shop_id=partner.shop_id,
        funded_by_partner_id=partner.id,
    ).count()

    return render_template(
        'investor/dashboard.html',
        investor=investor,
        partner=partner,
        current_estimate=current_estimate,
        last_final=last_final,
        current_period_label=current_period_label,
        last_period_label=last_period_label,
        my_phones_count=my_phones_count,
    )


@investor_bp.route('/profit-share')
@investor_login_required
def profit_share():
    investor = get_current_investor()
    partner = Partner.query.filter_by(investor_user_id=investor.id).first()
    if not partner:
        flash('No partner record found for your account.', 'warning')
        return redirect(url_for('investor.login'))

    month_filter = request.args.get('month', 'all')
    today = date.today()
    current_month_start = date(today.year, today.month, 1)

    periods = Period.query.filter_by(shop_id=partner.shop_id).order_by(Period.period_end.desc()).all()

    period_data = []
    for period in periods:
        month_key = period.period_start.strftime('%Y-%m')
        if month_filter != 'all' and month_key != month_filter:
            continue

        if period.status == 'locked':
            snapshot = PeriodSnapshot.query.filter_by(
                period_id=period.id,
                partner_id=partner.id,
            ).first()
            share = snapshot.share_amount if snapshot else Decimal('0')
            net_profit = snapshot.net_profit if snapshot else Decimal('0')
            status = 'locked'
            label = f"{period.period_start.strftime('%b %d')} — {period.period_end.strftime('%b %d, %Y')}"
        else:
            from app.models.cashbook import CashEntry
            from app.models.expense import Expense

            cash_in = db.session.query(
                db.func.coalesce(db.func.sum(CashEntry.amount), 0)
            ).filter(
                CashEntry.shop_id == partner.shop_id,
                CashEntry.entry_type == 'in',
                CashEntry.entry_date >= period.period_start,
                CashEntry.entry_date <= period.period_end,
            ).scalar()

            cash_out = db.session.query(
                db.func.coalesce(db.func.sum(CashEntry.amount), 0)
            ).filter(
                CashEntry.shop_id == partner.shop_id,
                CashEntry.entry_type == 'out',
                CashEntry.entry_date >= period.period_start,
                CashEntry.entry_date <= period.period_end,
            ).scalar()

            expenses = db.session.query(
                db.func.coalesce(db.func.sum(Expense.amount), 0)
            ).filter(
                Expense.shop_id == partner.shop_id,
                Expense.expense_date >= period.period_start,
                Expense.expense_date <= period.period_end,
            ).scalar()

            net_profit = Decimal(str(cash_in)) - Decimal(str(cash_out)) - Decimal(str(expenses))
            split_result = calculate_split(partner.shop_id, net_profit)
            share = Decimal('0')
            for s in split_result['splits']:
                if s['partner_id'] == partner.id:
                    share = s['share_amount']
                    break
            status = 'open'
            label = f"{period.period_start.strftime('%b %d')} — {period.period_end.strftime('%b %d, %Y')}"

        period_data.append({
            'period': period,
            'label': label,
            'net_profit': net_profit,
            'share': share,
            'status': status,
        })

    available_months = []
    seen = set()
    for period in periods:
        mk = period.period_start.strftime('%Y-%m')
        if mk not in seen:
            seen.add(mk)
            available_months.append({
                'key': mk,
                'label': period.period_start.strftime('%B %Y'),
            })

    total_investment = db.session.query(
        db.func.coalesce(db.func.sum(Partner.investment_amount), 0)
    ).filter_by(shop_id=partner.shop_id).scalar()
    investment_ratio = float(partner.investment_amount / total_investment * 100) if total_investment > 0 else 0

    return render_template(
        'investor/profit_share.html',
        investor=investor,
        partner=partner,
        periods=period_data,
        available_months=available_months,
        month_filter=month_filter,
        investment_ratio=investment_ratio,
    )


@investor_bp.route('/my-phones')
@investor_login_required
def my_phones():
    investor = get_current_investor()
    partner = Partner.query.filter_by(investor_user_id=investor.id).first()
    if not partner:
        flash('No partner record found for your account.', 'warning')
        return redirect(url_for('investor.login'))

    phones = StockItem.query.filter_by(
        shop_id=partner.shop_id,
        funded_by_partner_id=partner.id,
    ).order_by(StockItem.created_at.desc()).all()

    return render_template(
        'investor/my_phones.html',
        investor=investor,
        partner=partner,
        phones=phones,
    )
