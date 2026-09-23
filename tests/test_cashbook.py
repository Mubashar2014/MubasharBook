from app.models.cashbook import CashEntry


def test_cashbook_page_loads(logged_in_client):
    resp = logged_in_client.get('/cashbook/')
    assert resp.status_code == 200


def test_add_cash_in_entry(logged_in_client, app):
    resp = logged_in_client.post('/cashbook/add', data={
        'entry_type': 'in',
        'amount': 50000,
        'description': 'Sale of phone',
        'entry_date': '2024-06-15',
        'linked_stock_id': 0,
    }, follow_redirects=False)

    assert resp.status_code == 302

    with app.app_context():
        entry = CashEntry.query.filter_by(description='Sale of phone').first()
        assert entry is not None
        assert entry.entry_type == 'in'
        assert float(entry.amount) == 50000.0


def test_add_cash_out_entry(logged_in_client, app):
    resp = logged_in_client.post('/cashbook/add', data={
        'entry_type': 'out',
        'amount': 10000,
        'description': 'Paid supplier',
        'entry_date': '2024-06-16',
        'linked_stock_id': 0,
    }, follow_redirects=False)

    assert resp.status_code == 302

    with app.app_context():
        entry = CashEntry.query.filter_by(description='Paid supplier').first()
        assert entry is not None
        assert entry.entry_type == 'out'
        assert float(entry.amount) == 10000.0


def test_balance_calculates_correctly(logged_in_client, app):
    # Fixture shop has initial_investment=100000, which seeds opening cash
    logged_in_client.post('/cashbook/add', data={
        'entry_type': 'in',
        'amount': 50000,
        'description': 'First sale',
        'entry_date': '2024-06-15',
        'linked_stock_id': 0,
    })

    with app.app_context():
        entry = CashEntry.query.filter_by(description='First sale').first()
        assert float(entry.balance_after) == 150000.0


def test_opening_capital_seeds_balance(logged_in_client, app):
    logged_in_client.get('/dashboard')

    with app.app_context():
        opening = CashEntry.query.filter_by(description='Opening capital').first()
        assert opening is not None
        assert opening.entry_type == 'in'
        assert float(opening.amount) == 100000.0
        assert float(opening.balance_after) == 100000.0


def test_purchase_after_capital_keeps_positive_cash(logged_in_client, app):
    logged_in_client.get('/dashboard')
    logged_in_client.post('/stock/in', data={
        'model_name': 'Capital Phone',
        'quantity': 1,
        'cost_price': 35000,
        'purchase_date': '2026-09-23',
        'supplier_name': '',
        'purchase_paid': 35000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })

    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.first()
        opening = CashEntry.query.filter_by(shop_id=shop.id, description='Opening capital').first()
        assert opening is not None
        last = CashEntry.query.filter_by(shop_id=shop.id).order_by(CashEntry.id.desc()).first()
        assert float(last.balance_after) == 65000.0


def test_multiple_entries_running_balance(logged_in_client, app):
    # Opening capital = 100000 from fixture
    logged_in_client.post('/cashbook/add', data={
        'entry_type': 'in',
        'amount': 100000,
        'description': 'Cash in 1',
        'entry_date': '2024-06-15',
        'linked_stock_id': 0,
    })
    logged_in_client.post('/cashbook/add', data={
        'entry_type': 'out',
        'amount': 30000,
        'description': 'Cash out 1',
        'entry_date': '2024-06-16',
        'linked_stock_id': 0,
    })
    logged_in_client.post('/cashbook/add', data={
        'entry_type': 'in',
        'amount': 25000,
        'description': 'Cash in 2',
        'entry_date': '2024-06-17',
        'linked_stock_id': 0,
    })

    with app.app_context():
        e1 = CashEntry.query.filter_by(description='Cash in 1').first()
        e2 = CashEntry.query.filter_by(description='Cash out 1').first()
        e3 = CashEntry.query.filter_by(description='Cash in 2').first()

        assert float(e1.balance_after) == 200000.0
        assert float(e2.balance_after) == 170000.0
        assert float(e3.balance_after) == 195000.0


def test_cashbook_list_page_shows_entries(logged_in_client, app):
    logged_in_client.post('/cashbook/add', data={
        'entry_type': 'in',
        'amount': 20000,
        'description': 'Visible Entry',
        'entry_date': '2024-06-15',
        'linked_stock_id': 0,
    })

    resp = logged_in_client.get('/cashbook/')
    assert resp.status_code == 200
    assert b'Visible Entry' in resp.data
