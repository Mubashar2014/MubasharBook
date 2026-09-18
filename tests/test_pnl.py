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
