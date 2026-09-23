from datetime import date, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.cashbook import cashbook_bp
from app.cashbook.forms import CashEntryForm
from app.models.cashbook import CashEntry
from app.models.stock import StockItem
from app.extensions import db
from app.utils import get_user_shop, ensure_opening_cash, recalc_cash_balances, OPENING_CAPITAL_DESC


@cashbook_bp.route('/')
@login_required
def list_entries():
    shop = get_user_shop()
    period = request.args.get('period', 'all')
    today = date.today()

    query = CashEntry.query.filter(
        CashEntry.shop_id == shop.id, CashEntry.description != OPENING_CAPITAL_DESC
    )

    if period == 'today':
        query = query.filter_by(entry_date=today)
    elif period == 'week':
        week_start = today - timedelta(days=today.weekday())
        query = query.filter(CashEntry.entry_date >= week_start)
    elif period == 'month':
        month_start = today.replace(day=1)
        query = query.filter(CashEntry.entry_date >= month_start)

    entries = query.order_by(CashEntry.entry_date.asc(), CashEntry.created_at.asc()).all()

    subtotal_in = sum(float(e.amount) for e in entries if e.entry_type == 'in')
    subtotal_out = sum(float(e.amount) for e in entries if e.entry_type == 'out')

    return render_template(
        'cashbook/list.html',
        entries=entries,
        period=period,
        subtotal_in=subtotal_in,
        subtotal_out=subtotal_out,
    )


@cashbook_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_entry():
    shop = get_user_shop()
    form = CashEntryForm()

    stock_items = StockItem.query.filter_by(shop_id=shop.id).filter(
        StockItem.status.in_(['in_stock', 'reserved'])
    ).order_by(StockItem.model_name).all()
    form.linked_stock_id.choices = [(0, '-- None --')] + [(s.id, f'{s.model_name} ({s.imei or "no IMEI"})') for s in stock_items]

    if form.validate_on_submit():
        ensure_opening_cash(shop)
        last_entry = CashEntry.query.filter_by(shop_id=shop.id).order_by(
            CashEntry.id.desc()
        ).first()
        prev_balance = float(last_entry.balance_after) if last_entry and last_entry.balance_after else float(shop.initial_investment or 0)

        amt = float(form.amount.data)
        if form.entry_type.data == 'in':
            new_balance = prev_balance + amt
        else:
            new_balance = prev_balance - amt

        entry = CashEntry(
            shop_id=shop.id,
            entry_type=form.entry_type.data,
            amount=form.amount.data,
            description=form.description.data,
            entry_date=form.entry_date.data,
            linked_stock_id=form.linked_stock_id.data if form.linked_stock_id.data else None,
            balance_after=new_balance,
        )
        db.session.add(entry)
        db.session.commit()
        flash('Cash entry added.', 'success')
        return redirect(url_for('cashbook.list_entries'))

    form.entry_date.data = date.today()
    form.linked_stock_id.data = 0

    return render_template('cashbook/form.html', form=form)
