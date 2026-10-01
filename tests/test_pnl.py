from datetime import date
from decimal import Decimal
from app.extensions import db
from app.models.shop import Shop
from app.models.user import User
from app.models.cashbook import CashEntry
from app.models.expense import Expense


def _get_shop_id(user):
    return Shop.query.filter_by(user_id=user.id).first().id


def test_pnl_page_loads(logged_in_client):
    resp = logged_in_client.get('/reports/pnl')
    assert resp.status_code == 200


def test_pnl_calculation_basic(logged_in_client, app, test_user):
    with app.app_context():
        shop_id = _get_shop_id(test_user)

        db.session.add_all([
            CashEntry(shop_id=shop_id, entry_type='in', amount=100000,
                      description='Revenue', entry_date=date(2024, 6, 15)),
            CashEntry(shop_id=shop_id, entry_type='out', amount=40000,
                      description='Cost of goods', entry_date=date(2024, 6, 15)),
            Expense(shop_id=shop_id, category_id=1, amount=10000,
                    description='Rent', expense_date=date(2024, 6, 15)),
        ])
        db.session.commit()

        total_in = db.session.query(
            db.func.coalesce(db.func.sum(CashEntry.amount), 0)
        ).filter(
            CashEntry.shop_id == shop_id,
            CashEntry.entry_type == 'in',
        ).scalar()

        total_out = db.session.query(
            db.func.coalesce(db.func.sum(CashEntry.amount), 0)
        ).filter(
            CashEntry.shop_id == shop_id,
            CashEntry.entry_type == 'out',
        ).scalar()

        total_exp = db.session.query(
            db.func.coalesce(db.func.sum(Expense.amount), 0)
        ).filter(
            Expense.shop_id == shop_id,
        ).scalar()

        net_profit = Decimal(str(total_in)) - Decimal(str(total_out)) - Decimal(str(total_exp))
        assert net_profit == Decimal('50000')


def test_pnl_daily_breakdown(logged_in_client, app, test_user):
    with app.app_context():
        shop_id = _get_shop_id(test_user)

        db.session.add_all([
            CashEntry(shop_id=shop_id, entry_type='in', amount=60000,
                      description='Day 1 sale', entry_date=date(2024, 6, 15)),
            CashEntry(shop_id=shop_id, entry_type='in', amount=40000,
                      description='Day 2 sale', entry_date=date(2024, 6, 16)),
            CashEntry(shop_id=shop_id, entry_type='out', amount=10000,
                      description='Day 1 cost', entry_date=date(2024, 6, 15)),
        ])
        db.session.commit()

        day1_in = db.session.query(
            db.func.coalesce(db.func.sum(CashEntry.amount), 0)
        ).filter(
            CashEntry.shop_id == shop_id,
            CashEntry.entry_type == 'in',
            CashEntry.entry_date == date(2024, 6, 15),
        ).scalar()

        day2_in = db.session.query(
            db.func.coalesce(db.func.sum(CashEntry.amount), 0)
        ).filter(
            CashEntry.shop_id == shop_id,
            CashEntry.entry_type == 'in',
            CashEntry.entry_date == date(2024, 6, 16),
        ).scalar()

        assert Decimal(str(day1_in)) == Decimal('60000')
        assert Decimal(str(day2_in)) == Decimal('40000')


# ── Monthly statement ───────────────────────────────────

def test_monthly_statement_page_loads(logged_in_client, test_user):
    resp = logged_in_client.get('/reports/monthly')
    assert resp.status_code == 200
    assert b'Monthly Statement' in resp.data
    assert b'Cash Position' in resp.data
    assert b'Net Profit' in resp.data
    assert b'Phones Sold' in resp.data


def test_monthly_statement_navigation_months(logged_in_client):
    assert logged_in_client.get('/reports/monthly?year=2026&month=3').status_code == 200
    assert logged_in_client.get('/reports/monthly?year=2025&month=12').status_code == 200
    # garbage month falls back to the current month
    resp = logged_in_client.get('/reports/monthly?month=99')
    assert resp.status_code == 200


def test_monthly_statement_shows_cash_and_pnl_figures(logged_in_client, app, test_user):
    from app.models.expense import ExpenseCategory
    from app.models.stock import StockItem

    with app.app_context():
        shop_id = _get_shop_id(test_user)
        category = ExpenseCategory(shop_id=shop_id, name='Shop Rent')
        db.session.add(category)
        db.session.flush()

        db.session.add_all([
            CashEntry(shop_id=shop_id, entry_type='in', amount=50000,
                      description='Sale payment', entry_date=date(2026, 9, 5)),
            CashEntry(shop_id=shop_id, entry_type='out', amount=20000,
                      description='Stock purchase', entry_date=date(2026, 9, 10)),
            Expense(shop_id=shop_id, category_id=category.id, amount=10000,
                    description='Rent', expense_date=date(2026, 9, 12)),
            StockItem(shop_id=shop_id, model_name='Statement Phone', quantity=1,
                      cost_price=40000, purchase_date=date(2026, 9, 1),
                      status='sold', sale_price=60000, sale_date=date(2026, 9, 15),
                      sale_received=60000, sale_pending=0, purchase_paid=40000),
        ])
        db.session.commit()

    resp = logged_in_client.get('/reports/monthly?year=2026&month=9')
    assert resp.status_code == 200
    assert b'Rs 50,000' in resp.data   # cash in
    assert b'Rs 20,000' in resp.data   # cash out
    assert b'Rs 30,000' in resp.data   # closing = 0 + 50k - 20k
    assert b'Rs 60,000' in resp.data   # revenue
    assert b'Rs 40,000' in resp.data   # COGS / opening stock value
    assert b'Rs 20,000' in resp.data   # gross profit
    assert b'Shop Rent' in resp.data   # expense breakdown
    assert b'Statement Phone' in resp.data  # sold list


def test_monthly_statement_empty_period(logged_in_client):
    resp = logged_in_client.get('/reports/monthly?year=2024&month=2')
    assert resp.status_code == 200
    assert b'No expenses recorded in this period.' in resp.data
    assert b'No phones sold in this period.' in resp.data


def test_monthly_statement_is_shop_scoped(logged_in_client, second_user, app):
    from app.models.stock import StockItem

    with app.app_context():
        second_shop = Shop.query.filter_by(user_id=second_user.id).first()
        db.session.add(StockItem(
            shop_id=second_shop.id, model_name='Other Shops Phone', quantity=1,
            cost_price=70000, purchase_date=date(2026, 9, 3),
            status='sold', sale_price=90000, sale_date=date(2026, 9, 6),
            sale_received=90000, purchase_paid=70000,
        ))
        db.session.commit()

    resp = logged_in_client.get('/reports/monthly?year=2026&month=9')
    assert resp.status_code == 200
    assert b'Other Shops Phone' not in resp.data


def test_monthly_statement_counts_in_stock_units(logged_in_client, app, test_user):
    import re
    from app.models.stock import StockItem

    with app.app_context():
        shop_id = _get_shop_id(test_user)
        db.session.add_all([
            StockItem(shop_id=shop_id, model_name='Unit A', quantity=3,
                      cost_price=30000, purchase_date=date(2026, 8, 5), purchase_paid=90000),
            StockItem(shop_id=shop_id, model_name='Unit B', quantity=5,
                      cost_price=20000, purchase_date=date(2026, 7, 5), purchase_paid=100000),
        ])
        db.session.commit()

    resp = logged_in_client.get('/reports/monthly?year=2026&month=9')
    assert resp.status_code == 200
    row = re.search(rb'In stock today.*?</tr>', resp.data, re.S)
    assert row, 'in-stock row missing'
    assert b'>2<' in row.group(0)   # 2 items
    assert b'>8<' in row.group(0)   # 8 units
    assert b'Rs 190,000' in row.group(0)  # 3x30k + 5x20k
