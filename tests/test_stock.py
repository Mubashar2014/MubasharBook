from app.models.stock import StockItem
from app.models.cashbook import CashEntry
from app.models.khata import KhataEntry


def test_stock_list_page_loads(logged_in_client):
    resp = logged_in_client.get('/stock/')
    assert resp.status_code == 200


def test_add_stock_item(logged_in_client, app):
    resp = logged_in_client.post('/stock/in', data={
        'model_name': 'Samsung Galaxy S24',
        'imei': '123456789012345',
        'quantity': 2,
        'cost_price': 85000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 170000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    }, follow_redirects=False)

    assert resp.status_code == 302

    with app.app_context():
        item = StockItem.query.filter_by(model_name='Samsung Galaxy S24').first()
        assert item is not None
        assert item.quantity == 2
        assert item.imei == '123456789012345'
        assert float(item.purchase_paid) == 170000.0


def test_stock_item_appears_in_list(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'iPhone 15',
        'imei': '987654321098765',
        'quantity': 1,
        'cost_price': 120000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 120000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    resp = logged_in_client.get('/stock/')
    assert resp.status_code == 200
    assert b'iPhone 15' in resp.data


def test_delete_stock_item(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'Delete Me',
        'quantity': 1,
        'cost_price': 30000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 30000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    with app.app_context():
        item = StockItem.query.filter_by(model_name='Delete Me').first()
        item_id = item.id

    resp = logged_in_client.post(f'/stock/{item_id}/delete', follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        item = StockItem.query.get(item_id)
        assert item is None


def test_stock_in_auto_creates_cashbook_entry(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'Cash Purchase Phone',
        'quantity': 1,
        'cost_price': 50000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 50000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    with app.app_context():
        cash = CashEntry.query.filter(
            CashEntry.description.like('%Cash Purchase Phone%')
        ).first()
        assert cash is not None
        assert cash.entry_type == 'out'
        assert float(cash.amount) == 50000.0


def test_stock_in_with_supplier_creates_khata(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'Supplier Phone',
        'quantity': 1,
        'cost_price': 60000,
        'purchase_date': '2026-09-14',
        'supplier_name': 'Ahmed Mobiles',
        'purchase_paid': 40000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    }, follow_redirects=False)

    with app.app_context():
        khata = KhataEntry.query.filter_by(party_name='Ahmed Mobiles').first()
        assert khata is not None
        assert khata.entry_type == 'payable'
        assert float(khata.amount) == 20000.0
        assert khata.status == 'pending'


def test_stock_in_with_extra_expense(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'Expense Phone',
        'quantity': 1,
        'cost_price': 30000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 30000,
        'purchase_expense_desc': 'Transport',
        'purchase_expense_amount': 2000,
    })

    with app.app_context():
        cash = CashEntry.query.filter(
            CashEntry.description.like('%Transport%')
        ).first()
        assert cash is not None
        assert cash.entry_type == 'out'
        assert float(cash.amount) == 2000.0


def test_stock_out_creates_cash_in(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'Sell Me Phone',
        'quantity': 1,
        'cost_price': 40000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 40000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    with app.app_context():
        item = StockItem.query.filter_by(model_name='Sell Me Phone').first()
        item_id = item.id

    logged_in_client.post(f'/stock/{item_id}/sell', data={
        'sale_price': 50000,
        'sale_date': '2026-09-15',
        'customer_name': '',
        'sale_received': 50000,
        'sale_expense_desc': '',
        'sale_expense_amount': 0,
    })

    with app.app_context():
        item = StockItem.query.get(item_id)
        assert item.status == 'sold'
        assert float(item.sale_price) == 50000.0

        cash = CashEntry.query.filter(
            CashEntry.description.like('%Sold%Sell Me Phone%')
        ).first()
        assert cash is not None
        assert cash.entry_type == 'in'
        assert float(cash.amount) == 50000.0


def test_stock_out_to_customer_creates_khata(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'Credit Phone',
        'quantity': 1,
        'cost_price': 45000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 45000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    with app.app_context():
        item = StockItem.query.filter_by(model_name='Credit Phone').first()
        item_id = item.id

    logged_in_client.post(f'/stock/{item_id}/sell', data={
        'sale_price': 55000,
        'sale_date': '2026-09-15',
        'customer_name': 'Ali Bhai',
        'sale_received': 30000,
        'sale_expense_desc': '',
        'sale_expense_amount': 0,
    })

    with app.app_context():
        khata = KhataEntry.query.filter_by(party_name='Ali Bhai').first()
        assert khata is not None
        assert khata.entry_type == 'receivable'
        assert float(khata.amount) == 25000.0


def test_stock_filter_by_status(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'In Stock Phone',
        'quantity': 1,
        'cost_price': 50000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 50000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    resp = logged_in_client.get('/stock/?status=in_stock')
    assert resp.status_code == 200
    assert b'In Stock Phone' in resp.data

    resp = logged_in_client.get('/stock/?status=sold')
    assert resp.status_code == 200
    assert b'In Stock Phone' not in resp.data


def test_stock_search(logged_in_client, app):
    logged_in_client.post('/stock/in', data={
        'model_name': 'Samsung Galaxy',
        'imei': '111222333444555',
        'quantity': 1,
        'cost_price': 50000,
        'purchase_date': '2026-09-14',
        'supplier_name': '',
        'purchase_paid': 50000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    resp = logged_in_client.get('/stock/?q=Samsung')
    assert resp.status_code == 200
    assert b'Samsung Galaxy' in resp.data
