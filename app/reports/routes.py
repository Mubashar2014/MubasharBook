from datetime import date, timedelta
from calendar import monthrange
from flask import render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func, extract
from app.reports import reports_bp
from app.extensions import db
from app.utils import get_user_shop
from app.models.cashbook import CashEntry
from app.models.expense import Expense, ExpenseCategory
from app.models.khata import KhataEntry
from app.models.stock import StockItem


def compute_pnl_totals(shop, period_start, period_end):
    """Revenue / cost / expense / profit figures for a period (shared by P&L and monthly statement)."""
    sold_items = StockItem.query.filter(
        StockItem.shop_id == shop.id,
        StockItem.status == 'sold',
        StockItem.sale_date >= period_start,
        StockItem.sale_date <= period_end,
    ).all()

    total_revenue = sum(float(item.sale_price or 0) * item.quantity for item in sold_items)
    total_cost = sum(float(item.cost_price) * item.quantity for item in sold_items)
    total_expenses = float(db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.shop_id == shop.id,
        Expense.expense_date >= period_start,
        Expense.expense_date <= period_end,
    ).scalar() or 0)

    gross_profit = total_revenue - total_cost
    net_profit = gross_profit - total_expenses

    profit_received = 0.0
    profit_pending = 0.0
    for item in sold_items:
        profit_per_unit = float(item.sale_price or 0) - float(item.cost_price)
        item_profit = profit_per_unit * item.quantity
        if item.customer_name and item.sale_price:
            total_sale = float(item.sale_price) * item.quantity
            received_ratio = float(item.sale_received or 0) / total_sale if total_sale > 0 else 0
            profit_received += item_profit * received_ratio
            profit_pending += item_profit * (1 - received_ratio)
        else:
            profit_received += item_profit

    return {
        'sold_items': sold_items,
        'revenue': total_revenue,
        'cost': total_cost,
        'expenses': total_expenses,
        'gross': gross_profit,
        'net': net_profit,
        'received': profit_received,
        'pending': profit_pending,
    }


def _month_bounds(year, month):
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


@reports_bp.route('/pnl')
@login_required
def pnl():
    shop = get_user_shop()
    today = date.today()
    view = request.args.get('view', 'month')
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    day = request.args.get('day', today.day, type=int)

    if view == 'day':
        period_start = date(year, month, day)
        period_end = period_start
    else:
        period_start, period_end = _month_bounds(year, month)

    totals = compute_pnl_totals(shop, period_start, period_end)
    sold_items = totals['sold_items']
    total_revenue = totals['revenue']
    total_cost = totals['cost']
    total_expenses = totals['expenses']
    gross_profit = totals['gross']
    net_profit = totals['net']
    profit_received = totals['received']
    profit_pending = totals['pending']

    # Daily breakdown
    daily_rows = []

    if view == 'day':
        day_sold = [item for item in sold_items if item.sale_date == period_start]
        day_revenue = sum(float(item.sale_price or 0) * item.quantity for item in day_sold)
        day_cost = sum(float(item.cost_price) * item.quantity for item in day_sold)
        day_expenses = float(db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.shop_id == shop.id,
            Expense.expense_date == period_start,
        ).scalar() or 0)
        day_net = day_revenue - day_cost - day_expenses

        daily_rows.append({
            'date': period_start,
            'revenue': day_revenue,
            'cost': day_cost,
            'expenses': day_expenses,
            'net': day_net,
        })
    else:
        # Month view - group by date
        from sqlalchemy import Date
        expense_by_date = db.session.query(
            Expense.expense_date,
            func.sum(Expense.amount),
        ).filter(
            Expense.shop_id == shop.id,
            Expense.expense_date >= period_start,
            Expense.expense_date <= period_end,
        ).group_by(Expense.expense_date).all()

        date_map = {}
        for item in sold_items:
            d = item.sale_date
            if d not in date_map:
                date_map[d] = {'revenue': 0, 'cost': 0, 'expenses': 0}
            date_map[d]['revenue'] += float(item.sale_price or 0) * item.quantity
            date_map[d]['cost'] += float(item.cost_price) * item.quantity

        for edate, amt in expense_by_date:
            if edate not in date_map:
                date_map[edate] = {'revenue': 0, 'cost': 0, 'expenses': 0}
            date_map[edate]['expenses'] += float(amt)

        for d in sorted(date_map.keys(), reverse=True):
            row = date_map[d]
            daily_rows.append({
                'date': d,
                'revenue': row['revenue'],
                'cost': row['cost'],
                'expenses': row['expenses'],
                'net': row['revenue'] - row['cost'] - row['expenses'],
            })

    return render_template('reports/pnl.html',
        total_revenue=total_revenue,
        total_cost=total_cost,
        gross_profit=gross_profit,
        total_expenses=total_expenses,
        net_profit=net_profit,
        profit_received=profit_received,
        profit_pending=profit_pending,
        daily_rows=daily_rows,
        view=view,
        year=year,
        month=month,
        day=day,
        period_start=period_start,
        period_end=period_end,
        today=today,
    )

@reports_bp.route('/monthly')
@login_required
def monthly():
    """One printable statement for a month: cash, P&L, stock, khata, expenses."""
    shop = get_user_shop()
    today = date.today()
    year = request.args.get('year', today.year, type=int)
    month = request.args.get('month', today.month, type=int)
    if not 1 <= month <= 12:
        year, month = today.year, today.month
    period_start, period_end = _month_bounds(year, month)
    month_label = period_start.strftime('%B %Y')

    # ── Cashbook ────────────────────────────────────────
    prev_cash = CashEntry.query.filter(
        CashEntry.shop_id == shop.id,
        CashEntry.entry_date < period_start,
    ).order_by(CashEntry.id.desc()).first()
    opening = float(prev_cash.balance_after or 0) if prev_cash else 0.0

    cash_rows = CashEntry.query.filter(
        CashEntry.shop_id == shop.id,
        CashEntry.entry_date >= period_start,
        CashEntry.entry_date <= period_end,
    ).order_by(CashEntry.entry_date.asc(), CashEntry.id.asc()).all()

    cash_in = sum(float(r.amount) for r in cash_rows if r.entry_type == 'in')
    cash_out = sum(float(r.amount) for r in cash_rows if r.entry_type == 'out')
    closing = opening + cash_in - cash_out

    # ── Trading (P&L) ───────────────────────────────────
    pnl_totals = compute_pnl_totals(shop, period_start, period_end)

    # ── Stock movement ──────────────────────────────────
    bought_items = StockItem.query.filter(
        StockItem.shop_id == shop.id,
        StockItem.purchase_date >= period_start,
        StockItem.purchase_date <= period_end,
    ).all()
    bought_qty = sum(i.quantity for i in bought_items)
    bought_value = sum(float(i.cost_price or 0) * i.quantity for i in bought_items)

    sold_qty = sum(i.quantity for i in pnl_totals['sold_items'])
    in_stock_items = StockItem.query.filter(
        StockItem.shop_id == shop.id,
        StockItem.status == 'in_stock',
    ).all()
    in_stock_units = sum(i.quantity for i in in_stock_items)
    stock_value = sum(float(i.cost_price or 0) * i.quantity for i in in_stock_items)

    # ── Expenses by category ────────────────────────────
    expense_rows = db.session.query(
        ExpenseCategory.name,
        func.sum(Expense.amount).label('total'),
    ).join(Expense.category).filter(
        Expense.shop_id == shop.id,
        Expense.expense_date >= period_start,
        Expense.expense_date <= period_end,
    ).group_by(ExpenseCategory.name).order_by(func.sum(Expense.amount).desc()).all()
    expense_breakdown = [{'name': name, 'total': float(total)} for name, total in expense_rows]

    # ── Khata snapshot (current pending) ────────────────
    khata_pending = db.session.query(
        KhataEntry.entry_type,
        func.coalesce(func.sum(KhataEntry.amount - KhataEntry.settled_amount), 0),
    ).filter(
        KhataEntry.shop_id == shop.id,
        KhataEntry.status == 'pending',
    ).group_by(KhataEntry.entry_type).all()
    khata_map = {etype: float(total) for etype, total in khata_pending}
    receivable_pending = khata_map.get('receivable', 0.0)
    payable_pending = khata_map.get('payable', 0.0)

    khata_opened = KhataEntry.query.filter(
        KhataEntry.shop_id == shop.id,
        KhataEntry.entry_date >= period_start,
        KhataEntry.entry_date <= period_end,
    ).all()

    # ── Period navigation ───────────────────────────────
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    return render_template('reports/monthly.html',
        shop=shop,
        year=year,
        month=month,
        month_label=month_label,
        period_start=period_start,
        period_end=period_end,
        today=today,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        opening=opening,
        cash_in=cash_in,
        cash_out=cash_out,
        closing=closing,
        cash_count=len(cash_rows),
        pnl=pnl_totals,
        bought_qty=bought_qty,
        bought_value=bought_value,
        bought_count=len(bought_items),
        sold_qty=sold_qty,
        in_stock_count=len(in_stock_items),
        in_stock_units=in_stock_units,
        stock_value=stock_value,
        expense_breakdown=expense_breakdown,
        receivable_pending=receivable_pending,
        payable_pending=payable_pending,
        khata_opened_count=len(khata_opened),
        khata_opened_amount=sum(float(e.amount) for e in khata_opened),
    )
