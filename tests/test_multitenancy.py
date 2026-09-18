from datetime import date
from app.extensions import db
from app.models.shop import Shop
from app.models.stock import StockItem
from app.models.cashbook import CashEntry


def test_user_cannot_see_other_users_stock(logged_in_client, second_user, app):
    with app.app_context():
        second_shop = Shop.query.filter_by(user_id=second_user.id).first()

        item = StockItem(
            shop_id=second_shop.id, model_name='Secret Phone',
            quantity=1, cost_price=50000, purchase_date=date(2026, 9, 14),
            status='in_stock', purchase_paid=50000,
        )
        db.session.add(item)
        db.session.commit()

    resp = logged_in_client.get('/stock/')
    assert resp.status_code == 200
    assert b'Secret Phone' not in resp.data


def test_user_cannot_see_other_users_cashbook(logged_in_client, second_user, app):
    with app.app_context():
        second_shop = Shop.query.filter_by(user_id=second_user.id).first()

        entry = CashEntry(
            shop_id=second_shop.id, entry_type='in', amount=99999,
            description='Secret cash entry', entry_date=date(2026, 9, 15),
        )
        db.session.add(entry)
        db.session.commit()

    resp = logged_in_client.get('/cashbook/')
    assert resp.status_code == 200
    assert b'Secret cash entry' not in resp.data


def test_user_stock_isolation_add_and_view(logged_in_client, second_user, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'My Phone',
        'quantity': 1,
        'cost_price': 40000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 40000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    resp = logged_in_client.get('/stock/')
    assert b'My Phone' in resp.data

    with app.app_context():
        second_client = app.test_client()
        with second_client.session_transaction() as sess:
            sess['_user_id'] = str(second_user.id)

        resp2 = second_client.get('/stock/')
        assert b'My Phone' not in resp2.data
