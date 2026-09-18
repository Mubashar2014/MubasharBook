from datetime import date, timedelta
from calendar import monthrange
from flask import render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func, extract
from app.reports import reports_bp
from app.extensions import db
from app.utils import get_user_shop
from app.models.cashbook import CashEntry
from app.models.expense import Expense
from app.models.stock import StockItem


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
        last_day = monthrange(year, month)[1]
        period_start = date(year, month, 1)
        period_end = date(year, month, last_day)

    # Sold phones in period
    sold_items = StockItem.query.filter(
        StockItem.shop_id == shop.id,
        StockItem.status == 'sold',
        StockItem.sale_date >= period_start,
        StockItem.sale_date <= period_end,
    ).all()

    # Revenue = sum of (sale_price * quantity) for sold phones
    total_revenue = sum(float(item.sale_price or 0) * item.quantity for item in sold_items)

    # Cost of goods sold = sum of (cost_price * quantity) for sold phones
    total_cost = sum(float(item.cost_price) * item.quantity for item in sold_items)

    # Total expenses in period
    total_expenses = float(db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.shop_id == shop.id,
        Expense.expense_date >= period_start,
        Expense.expense_date <= period_end,
    ).scalar() or 0)

    # Gross profit
    gross_profit = total_revenue - total_cost
    # Net profit
    net_profit = gross_profit - total_expenses

    # Profit breakdown: received vs pending
    profit_received = 0
    profit_pending = 0
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