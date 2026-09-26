"""Stock lifecycle: Un-sell (revert sale) and Delete (full cascade)."""
from datetime import date, datetime

import pytest

from app.extensions import db
from app.models.stock import StockItem
from app.models.cashbook import CashEntry
from app.models.khata import KhataEntry
from app.models.shareholder import Period
from app.utils import get_cash_balance


def db_get(model, item_id):
    return db.session.get(model, item_id)


@pytest.fixture
def other_client(app, second_user):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(second_user.id)
    return c


def add_stock(client, model, cost=40000, paid=None, expense=0, supplier='', pdate='2026-09-10'):
    paid = cost if paid is None else paid
    resp = client.post('/stock/in', data={
        'model_name': model,
        'quantity': 1,
        'cost_price': cost,
        'purchase_date': pdate,
        'supplier_name': supplier,
        'purchase_paid': paid,
        'purchase_expense_desc': 'Freight' if expense else '',
        'purchase_expense_amount': expense,
    }, follow_redirects=False)
    assert resp.status_code == 302, resp.data[:500]
    return get_id(model)


def get_id(model):
    item = StockItem.query.filter_by(model_name=model).first()
    assert item is not None, f'no item {model}'
    return item.id


def sell(client, item_id, price, received, customer='', sdate='2026-09-15', expense=0):
    resp = client.post(f'/stock/{item_id}/sell', data={
        'sale_price': price,
        'sale_date': sdate,
        'customer_name': customer,
        'sale_received': received,
        'sale_expense_desc': 'Delivery' if expense else '',
        'sale_expense_amount': expense,
    }, follow_redirects=False)
    assert resp.status_code == 302, resp.data[:500]


# ── UN-SELL ──────────────────────────────────────────────


def test_unsell_reverts_sale_and_cash(logged_in_client, app, test_user):
    item_id = add_stock(logged_in_client, 'Return Me', cost=40000)   # out 40000
    sell(logged_in_client, item_id, price=50000, received=50000)     # in 50000
    sid = test_user.shop.id

    with app.app_context():
        assert float(get_cash_balance(sid)) == 110000.0  # 100k - 40k + 50k

    resp = logged_in_client.post(f'/stock/{item_id}/unsell', follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        item = db_get(StockItem, item_id)
        assert item.status == 'in_stock'
        assert item.sale_price is None
        assert item.sale_date is None
        assert item.sale_received is None
        assert item.sale_cash_entry_id is None
        assert item.sale_khata_entry_id is None

        # Sale cash entry gone; purchase entry + opening remain
        assert CashEntry.query.count() == 2
        # P&L source query: no sold phones in the period anymore
        sold = StockItem.query.filter(
            StockItem.status == 'sold',
            StockItem.sale_date >= date(2026, 9, 1),
            StockItem.sale_date <= date(2026, 9, 30),
        ).count()
        assert sold == 0
        assert float(get_cash_balance(sid)) == 60000.0  # 100k - 40k
        # Running balances were recalculated and consistent
        last = CashEntry.query.order_by(CashEntry.id.desc()).first()
        assert float(last.balance_after) == 60000.0


def test_unsell_keeps_purchase_side(logged_in_client, app, test_user):
    item_id = add_stock(logged_in_client, 'Keep Buy', cost=40000, paid=30000, supplier='Ali Traders')
    with app.app_context():
        assert CashEntry.query.count() == 2          # opening + purchase paid
        assert KhataEntry.query.count() == 1         # payable 10000
        khata_id = KhataEntry.query.first().id

    sell(logged_in_client, item_id, price=50000, received=50000)
    logged_in_client.post(f'/stock/{item_id}/unsell', follow_redirects=False)

    with app.app_context():
        item = db_get(StockItem, item_id)
        assert item.status == 'in_stock'
        assert item.supplier_name == 'Ali Traders'
        assert CashEntry.query.count() == 2          # purchase cash untouched
        k = db_get(KhataEntry, khata_id)
        assert k is not None and k.status == 'pending'


def test_unsell_removes_pending_receivable(logged_in_client, app, test_user):
    item_id = add_stock(logged_in_client, 'Credit Sale', cost=45000)
    sell(logged_in_client, item_id, price=55000, received=30000, customer='Ali Bhai')
    with app.app_context():
        assert KhataEntry.query.filter_by(entry_type='receivable').count() == 1

    logged_in_client.post(f'/stock/{item_id}/unsell', follow_redirects=False)

    with app.app_context():
        assert KhataEntry.query.filter_by(entry_type='receivable').count() == 0


def test_unsell_settled_receivable_removes_settle_cash(logged_in_client, app, test_user):
    sid = test_user.shop.id
    item_id = add_stock(logged_in_client, 'Settled Sale', cost=45000)
    sell(logged_in_client, item_id, price=55000, received=30000, customer='Ali Bhai')
    with app.app_context():
        khata = KhataEntry.query.filter_by(entry_type='receivable').first()
        khata_id = khata.id
    assert float(get_cash_balance(sid)) == 85000.0  # 100k - 45k + 30k

    resp = logged_in_client.post(f'/khata/{khata_id}/settle', follow_redirects=False)
    assert resp.status_code == 302
    assert float(get_cash_balance(sid)) == 110000.0  # +25k settled

    logged_in_client.post(f'/stock/{item_id}/unsell', follow_redirects=False)

    with app.app_context():
        item = db_get(StockItem, item_id)
        assert item.status == 'in_stock'
        assert db_get(KhataEntry, khata_id) is None
        # opening + purchase only — both sale-side cash entries removed
        assert CashEntry.query.count() == 2
        assert float(get_cash_balance(sid)) == 55000.0


# ── DELETE ───────────────────────────────────────────────


def test_delete_in_stock_removes_everything_and_recalculates(logged_in_client, app, test_user):
    sid = test_user.shop.id
    item_id = add_stock(
        logged_in_client, 'Delete Full', cost=40000, paid=30000,
        expense=2000, supplier='Ali Traders',
    )
    with app.app_context():
        assert CashEntry.query.count() == 3   # opening + paid + expense
        assert KhataEntry.query.count() == 1  # payable 10000
        assert float(get_cash_balance(sid)) == 68000.0  # 100k - 30k - 2k

    resp = logged_in_client.post(f'/stock/{item_id}/delete', follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        assert db_get(StockItem, item_id) is None
        # Everything linked is gone — only the opening-capital entry remains
        assert CashEntry.query.count() == 1
        assert KhataEntry.query.count() == 0
        assert CashEntry.query.filter_by(linked_stock_id=item_id).count() == 0
        assert float(get_cash_balance(sid)) == 100000.0
        last = CashEntry.query.order_by(CashEntry.id.desc()).first()
        assert float(last.balance_after) == 100000.0


def test_delete_sold_item_cascades_sale_side(logged_in_client, app, test_user):
    sid = test_user.shop.id
    item_id = add_stock(logged_in_client, 'Delete Sold', cost=40000)
    sell(logged_in_client, item_id, price=50000, received=50000, expense=1000)
    with app.app_context():
        assert CashEntry.query.count() == 4  # opening + buy + sale in + sale expense
        assert float(get_cash_balance(sid)) == 109000.0  # 100k - 40k + 50k - 1k

    logged_in_client.post(f'/stock/{item_id}/delete', follow_redirects=False)

    with app.app_context():
        assert db_get(StockItem, item_id) is None
        assert CashEntry.query.count() == 1
        assert float(get_cash_balance(sid)) == 100000.0


def test_unsell_requires_sold_status(logged_in_client, app):
    item_id = add_stock(logged_in_client, 'Still In Stock', cost=30000)
    resp = logged_in_client.post(f'/stock/{item_id}/unsell', follow_redirects=False)
    assert resp.status_code == 404
    with app.app_context():
        item = db_get(StockItem, item_id)
        assert item.status == 'in_stock'


def test_tenant_cannot_delete_or_unsell_other_shops_items(logged_in_client, other_client, app, second_user):
    item_id = add_stock(logged_in_client, 'Private Phone', cost=40000)
    sell(logged_in_client, item_id, price=50000, received=50000)

    # Nested app context: ambient test context shares `g` across clients,
    # which would leak the first client's identity into this request.
    with app.app_context():
        resp = other_client.post(f'/stock/{item_id}/delete', follow_redirects=False)
    assert resp.status_code == 404
    with app.app_context():
        resp = other_client.post(f'/stock/{item_id}/unsell', follow_redirects=False)
    assert resp.status_code == 404

    with app.app_context():
        item = db_get(StockItem, item_id)
        assert item is not None and item.status == 'sold'


def test_unsell_allowed_inside_locked_period(logged_in_client, app, test_user):
    item_id = add_stock(logged_in_client, 'Locked Sell', cost=40000, pdate='2026-09-10')
    sell(logged_in_client, item_id, price=50000, received=50000, sdate='2026-09-15')
    _lock_september(app, test_user.shop.id)

    resp = logged_in_client.post(f'/stock/{item_id}/unsell', follow_redirects=False)
    assert resp.status_code == 302  # allowed, not blocked
    with app.app_context():
        item = db_get(StockItem, item_id)
        assert item.status == 'in_stock'


def test_delete_allowed_inside_locked_period(logged_in_client, app, test_user):
    item_id = add_stock(logged_in_client, 'Locked Buy', cost=40000, pdate='2026-09-10')
    _lock_september(app, test_user.shop.id)

    resp = logged_in_client.post(f'/stock/{item_id}/delete', follow_redirects=False)
    assert resp.status_code == 302  # allowed, not blocked
    with app.app_context():
        assert db_get(StockItem, item_id) is None
        assert CashEntry.query.filter_by(linked_stock_id=item_id).count() == 0


def _lock_september(app, shop_id):
    with app.app_context():
        db.session.add(Period(
            shop_id=shop_id,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            status='locked',
            locked_at=datetime(2026, 9, 30, 12, 0, 0),
        ))
        db.session.commit()
