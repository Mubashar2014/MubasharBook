from app.models.khata import KhataEntry
from app.models.cashbook import CashEntry
from app.models.stock import StockItem
from datetime import date


def _add_stock(logged_in_client, model, cost, paid, supplier=''):
    logged_in_client.post('/stock/in', data={
        'model_name': model,
        'quantity': 1,
        'cost_price': cost,
        'purchase_date': '2026-09-14',
        'supplier_name': supplier,
        'purchase_paid': paid,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })


def _sell_stock(logged_in_client, item_id, sale_price, received, customer=''):
    logged_in_client.post(f'/stock/{item_id}/sell', data={
        'sale_price': sale_price,
        'sale_date': '2026-09-15',
        'customer_name': customer,
        'sale_received': received,
        'sale_expense_desc': '',
        'sale_expense_amount': 0,
    })


def test_khata_page_loads(logged_in_client):
    resp = logged_in_client.get('/khata/')
    assert resp.status_code == 200


def test_supplier_pending_creates_payable_khata(logged_in_client, app):
    _add_stock(logged_in_client, 'Supplier Phone', 60000, 40000, 'Ahmed Mobiles')

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name='Ahmed Mobiles').first()
        assert entry is not None
        assert entry.entry_type == 'payable'
        assert float(entry.amount) == 20000.0
        assert entry.status == 'pending'


def test_customer_pending_creates_receivable_khata(logged_in_client, app):
    _add_stock(logged_in_client, 'Credit Phone', 40000, 40000)

    with app.app_context():
        item = StockItem.query.filter_by(model_name='Credit Phone').first()
        item_id = item.id

    _sell_stock(logged_in_client, item_id, 50000, 30000, 'Ali Bhai')

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name='Ali Bhai').first()
        assert entry is not None
        assert entry.entry_type == 'receivable'
        assert float(entry.amount) == 20000.0
        assert entry.status == 'pending'


def test_settle_receivable_creates_cash_in(logged_in_client, app):
    _add_stock(logged_in_client, 'Settle Test', 40000, 40000)
    with app.app_context():
        item = StockItem.query.filter_by(model_name='Settle Test').first()
        _sell_stock(logged_in_client, item.id, 50000, 25000, 'Receivable Person')

    with app.app_context():
        khata = KhataEntry.query.filter_by(party_name='Receivable Person').first()
        khata_id = khata.id

    resp = logged_in_client.post(f'/khata/{khata_id}/settle', follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        cash = CashEntry.query.filter(
            CashEntry.description.like('%Receivable Person%')
        ).first()
        assert cash is not None
        assert cash.entry_type == 'in'
        assert float(cash.amount) == 25000.0


def test_settle_payable_creates_cash_out(logged_in_client, app):
    _add_stock(logged_in_client, 'Payable Test', 60000, 30000, 'Payable Supplier')

    with app.app_context():
        khata = KhataEntry.query.filter_by(party_name='Payable Supplier').first()
        khata_id = khata.id

    resp = logged_in_client.post(f'/khata/{khata_id}/settle', follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        cash = CashEntry.query.filter(
            CashEntry.description.like('%Payable Supplier%')
        ).first()
        assert cash is not None
        assert cash.entry_type == 'out'
        assert float(cash.amount) == 30000.0


def test_khata_entry_status_changes_to_settled(logged_in_client, app):
    _add_stock(logged_in_client, 'Status Check', 50000, 30000, 'Status Supplier')

    with app.app_context():
        khata = KhataEntry.query.filter_by(party_name='Status Supplier').first()
        khata_id = khata.id
        assert khata.status == 'pending'

    logged_in_client.post(f'/khata/{khata_id}/settle', follow_redirects=False)

    with app.app_context():
        khata = KhataEntry.query.get(khata_id)
        assert khata.status == 'settled'
        assert khata.settled_date is not None
        assert khata.settled_cash_entry_id is not None


def test_already_settled_entry_shows_warning(logged_in_client, app):
    _add_stock(logged_in_client, 'Double Settle', 50000, 30000, 'Double Supplier')

    with app.app_context():
        khata = KhataEntry.query.filter_by(party_name='Double Supplier').first()
        khata_id = khata.id

    logged_in_client.post(f'/khata/{khata_id}/settle', follow_redirects=False)
    resp = logged_in_client.post(f'/khata/{khata_id}/settle', follow_redirects=False)
    assert resp.status_code == 302
