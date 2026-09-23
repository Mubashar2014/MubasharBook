import os
import uuid
from datetime import datetime, date
from decimal import Decimal
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from app.main import main_bp
from app.extensions import db
from app.models.shop import Shop
from app.models.cashbook import CashEntry
from app.models.stock import StockItem
from app.models.expense import Expense
from app.models.khata import KhataEntry
from app.utils import ensure_opening_cash, get_cash_balance, OPENING_CAPITAL_DESC


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


@main_bp.route('/')
def landing():
    return render_template('landing.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    shop = current_user.shop
    if shop is None:
        shop = Shop(user_id=current_user.id, name=current_user.owner_name + "'s Shop")
        db.session.add(shop)
        db.session.commit()
        current_user.shop = shop

    shop_id = shop.id
    today = date.today()

    # ===== CAPITAL BREAKDOWN =====
    # Initial investment (owner's capital)
    initial_investment = float(shop.initial_investment or 0)

    # Cumulative profit from sold phones
    sold_items = StockItem.query.filter_by(shop_id=shop_id, status='sold').all()
    total_revenue = sum(float(item.sale_price or 0) * item.quantity for item in sold_items)
    total_cogs = sum(float(item.cost_price) * item.quantity for item in sold_items)
    cumulative_profit = total_revenue - total_cogs

    # Total expenses (business expenses + withdrawals)
    total_expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.shop_id == shop_id
    ).scalar() or 0)

    # Total Capital = Initial Investment + Cumulative Profit - Expenses
    total_capital = initial_investment + cumulative_profit - total_expenses

    # ===== WHERE THE MONEY IS =====
    # Cash in hand (includes opening capital entry)
    ensure_opening_cash(shop)
    db.session.commit()
    cash_in_hand = get_cash_balance(shop_id)

    # Invested in stock (cost value of in-stock items)
    stock_value = float(db.session.query(func.coalesce(func.sum(StockItem.cost_price * StockItem.quantity), 0)).filter(
        StockItem.shop_id == shop_id, StockItem.status == 'in_stock'
    ).scalar() or 0)

    # Pending from customers (receivables)
    pending_receivable = float(db.session.query(func.coalesce(func.sum(KhataEntry.amount - KhataEntry.settled_amount), 0)).filter(
        KhataEntry.shop_id == shop_id, KhataEntry.entry_type == 'receivable', KhataEntry.status == 'pending'
    ).scalar() or 0)

    # Pending to suppliers (payables)
    pending_payable = float(db.session.query(func.coalesce(func.sum(KhataEntry.amount - KhataEntry.settled_amount), 0)).filter(
        KhataEntry.shop_id == shop_id, KhataEntry.entry_type == 'payable', KhataEntry.status == 'pending'
    ).scalar() or 0)

    # ===== TODAY'S ACTIVITY (exclude opening capital) =====
    today_cash_in = float(db.session.query(func.coalesce(func.sum(CashEntry.amount), 0)).filter(
        CashEntry.shop_id == shop_id, CashEntry.entry_type == 'in', CashEntry.entry_date == today,
        CashEntry.description != OPENING_CAPITAL_DESC,
    ).scalar() or 0)

    today_cash_out = float(db.session.query(func.coalesce(func.sum(CashEntry.amount), 0)).filter(
        CashEntry.shop_id == shop_id, CashEntry.entry_type == 'out', CashEntry.entry_date == today
    ).scalar() or 0)

    today_expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.shop_id == shop_id, Expense.expense_date == today
    ).scalar() or 0)

    today_net = today_cash_in - today_cash_out - today_expenses

    # ===== MONTHLY P&L (based on sold phones this month) =====
    month_start = today.replace(day=1)
    month_sold = StockItem.query.filter(
        StockItem.shop_id == shop_id, StockItem.status == 'sold',
        StockItem.sale_date >= month_start, StockItem.sale_date <= today
    ).all()
    month_revenue = sum(float(item.sale_price or 0) * item.quantity for item in month_sold)
    month_cogs = sum(float(item.cost_price) * item.quantity for item in month_sold)
    month_expenses = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.shop_id == shop_id, Expense.expense_date >= month_start, Expense.expense_date <= today
    ).scalar() or 0)
    monthly_pnl = month_revenue - month_cogs - month_expenses

    # Profit breakdown for this month
    month_profit_received = 0
    month_profit_pending = 0
    for item in month_sold:
        profit_per_unit = float(item.sale_price or 0) - float(item.cost_price)
        total_profit = profit_per_unit * item.quantity
        if item.customer_name:
            received_ratio = float(item.sale_received or 0) / (float(item.sale_price or 0) * item.quantity) if float(item.sale_price or 0) * item.quantity > 0 else 0
            month_profit_received += total_profit * received_ratio
            month_profit_pending += total_profit * (1 - received_ratio)
        else:
            month_profit_received += total_profit

    # Recent cashbook entries
    recent_entries = CashEntry.query.filter_by(shop_id=shop_id).order_by(
        CashEntry.entry_date.desc(), CashEntry.id.desc()
    ).limit(5).all()

    # Trial status
    trial_days_left = None
    if current_user.trial_end:
        delta = current_user.trial_end - datetime.utcnow()
        trial_days_left = max(0, delta.days)
    trial_active = current_user.is_trial_active

    return render_template('dashboard.html',
        # Capital
        initial_investment=initial_investment,
        cumulative_profit=cumulative_profit,
        total_expenses=total_expenses,
        total_capital=total_capital,
        # Where money is
        cash_in_hand=cash_in_hand,
        stock_value=stock_value,
        pending_receivable=pending_receivable,
        pending_payable=pending_payable,
        # Today
        today_net=today_net,
        today_sales=today_cash_in,
        # Monthly P&L
        monthly_pnl=monthly_pnl,
        month_revenue=month_revenue,
        month_cogs=month_cogs,
        month_profit=monthly_pnl + month_expenses,  # gross profit
        month_profit_received=month_profit_received,
        month_profit_pending=month_profit_pending,
        # Recent
        recent_entries=recent_entries,
        today=today,
        trial_days_left=trial_days_left,
        trial_active=trial_active,
    )


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    shop = current_user.shop
    if request.method == 'POST':
        shop.name = request.form.get('shop_name', '').strip()
        shop.initial_investment = Decimal(request.form.get('initial_investment') or 0)
        
        if 'shop_image' in request.files:
            img = request.files['shop_image']
            if img and img.filename:
                img_path = _save_shop_image(img, shop.id)
                if img_path:
                    shop.shop_image = img_path
        
        ensure_opening_cash(shop)
        db.session.commit()
        flash('Shop details updated.', 'success')
        return redirect(url_for('main.settings'))

    return render_template('settings.html', shop=shop)