import re
from datetime import date as _date

from app.extensions import db
from app.models.stock import StockItem
from app.models.shareholder import Partner
from app.models.shop import Shop
from app.models.user import User


def _get(app, client, path):
    with app.app_context():
        return client.get(path)


def _post(app, client, path, data=None, follow_redirects=False):
    with app.app_context():
        return client.post(path, data=data or {}, follow_redirects=follow_redirects)


def _add_partner(client, app, name, role, amount=300000, email=''):
    _post(app, client, '/shareholders/add-partner', {
        'name': name, 'role': role, 'investment_amount': amount,
        'investor_email': email,
    })
    with app.app_context():
        return Partner.query.filter_by(name=name).first().id


def _stock_payload(**overrides):
    data = {
        'model_name': 'Funded Phone',
        'imei': '',
        'quantity': 1,
        'cost_price': 50000,
        'purchase_date': '2026-09-20',
        'supplier_name': '',
        'purchase_paid': 50000,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
        'funded_by_partner_id': 0,
    }
    data.update(overrides)
    return data


def test_stock_in_assigns_investor_funder(logged_in_client, app):
    pid = _add_partner(logged_in_client, app, 'Bilal Investor', 'investor')
    resp = _post(app, logged_in_client, '/stock/in', _stock_payload(
        model_name='Funder Phone', funded_by_partner_id=pid))
    assert resp.status_code == 302

    with app.app_context():
        item = StockItem.query.filter_by(model_name='Funder Phone').first()
        assert item is not None
        assert item.funded_by_partner_id == pid


def test_stock_in_invalid_funder_becomes_null(logged_in_client, app, second_user):
    owner_pid = _add_partner(logged_in_client, app, 'Owner Partner', 'owner')

    with app.app_context():
        foreign = Partner(
            shop_id=Shop.query.filter_by(user_id=second_user.id).first().id,
            name='Foreign Investor', role='investor', investment_amount=100000,
        )
        db.session.add(foreign)
        db.session.commit()
        foreign_pid = foreign.id

    # Foreign partner id
    _post(app, logged_in_client, '/stock/in', _stock_payload(
        model_name='Foreign Funder', funded_by_partner_id=foreign_pid))
    # Owner-role partner id
    _post(app, logged_in_client, '/stock/in', _stock_payload(
        model_name='Owner Funder', funded_by_partner_id=owner_pid))
    # Bogus id
    _post(app, logged_in_client, '/stock/in', _stock_payload(
        model_name='Bogus Funder', funded_by_partner_id=999999))
    # Field absent entirely
    payload = _stock_payload(model_name='No Funder Field')
    del payload['funded_by_partner_id']
    _post(app, logged_in_client, '/stock/in', payload)

    with app.app_context():
        for name in ('Foreign Funder', 'Owner Funder', 'Bogus Funder', 'No Funder Field'):
            item = StockItem.query.filter_by(model_name=name).first()
            assert item is not None, name
            assert item.funded_by_partner_id is None, name


def test_funder_dropdown_visibility(logged_in_client, app):
    resp = _get(app, logged_in_client, '/stock/in')
    assert b'funded_by_partner_id' not in resp.data

    pid = _add_partner(logged_in_client, app, 'Visible Investor', 'investor')
    resp = _get(app, logged_in_client, '/stock/in')
    assert b'funded_by_partner_id' in resp.data
    assert b'Visible Investor' in resp.data


def test_edit_stock_reassign_and_clear(logged_in_client, app, second_user):
    with app.app_context():
        resp = _post(app, logged_in_client, '/stock/in', _stock_payload(model_name='Editable Phone'))
        assert resp.status_code == 302
        item = StockItem.query.filter_by(model_name='Editable Phone').first()
        item_id = item.id
        assert item.funded_by_partner_id is None

    pid_a = _add_partner(logged_in_client, app, 'Investor A', 'investor')
    pid_b = _add_partner(logged_in_client, app, 'Investor B', 'investor')

    with app.app_context():
        foreign = Partner(
            shop_id=Shop.query.filter_by(user_id=second_user.id).first().id,
            name='Other Shop Investor', role='investor', investment_amount=50000,
        )
        db.session.add(foreign)
        db.session.commit()
        foreign_pid = foreign.id

    # Assign A
    _post(app, logged_in_client, f'/stock/{item_id}/edit', _stock_payload(
        model_name='Editable Phone', funded_by_partner_id=pid_a))
    with app.app_context():
        assert db.session.get(StockItem, item_id).funded_by_partner_id == pid_a

    # Reassign B
    _post(app, logged_in_client, f'/stock/{item_id}/edit', _stock_payload(
        model_name='Editable Phone', funded_by_partner_id=pid_b))
    with app.app_context():
        assert db.session.get(StockItem, item_id).funded_by_partner_id == pid_b

    # Foreign partner -> NULL
    _post(app, logged_in_client, f'/stock/{item_id}/edit', _stock_payload(
        model_name='Editable Phone', funded_by_partner_id=foreign_pid))
    with app.app_context():
        assert db.session.get(StockItem, item_id).funded_by_partner_id is None

    # Clear with 0
    _post(app, logged_in_client, f'/stock/{item_id}/edit', _stock_payload(
        model_name='Editable Phone', funded_by_partner_id=pid_a))
    _post(app, logged_in_client, f'/stock/{item_id}/edit', _stock_payload(
        model_name='Editable Phone', funded_by_partner_id=0))
    with app.app_context():
        assert db.session.get(StockItem, item_id).funded_by_partner_id is None


def test_delete_partner_nullifies_funded_phones(logged_in_client, app):
    pid = _add_partner(logged_in_client, app, 'Gone Investor', 'investor')
    for name in ('Phone One', 'Phone Two'):
        _post(app, logged_in_client, '/stock/in', _stock_payload(
            model_name=name, funded_by_partner_id=pid))

    with app.app_context():
        assert StockItem.query.filter_by(funded_by_partner_id=pid).count() == 2

    resp = _post(app, logged_in_client, f'/shareholders/partner/{pid}/delete',
                 follow_redirects=True)
    assert b'returned to unassigned stock' in resp.data

    with app.app_context():
        assert db.session.get(Partner, pid) is None
        assert StockItem.query.filter_by(model_name='Phone One').first().funded_by_partner_id is None
        assert StockItem.query.filter_by(model_name='Phone Two').first().funded_by_partner_id is None
        assert StockItem.query.filter_by(funded_by_partner_id=pid).count() == 0


def _add_stock(client, app, model, **extra):
    payload = _stock_payload(model_name=model)
    payload.update(extra)
    resp = _post(app, client, '/stock/in', payload)
    assert resp.status_code == 302
    with app.app_context():
        return StockItem.query.filter_by(model_name=model).first().id


def test_stock_list_shows_funder_chip(logged_in_client, app):
    pid = _add_partner(logged_in_client, app, 'Chip Investor', 'investor')
    item_id = _add_stock(logged_in_client, app, 'Chip Phone', funded_by_partner_id=pid)

    resp = _get(app, logged_in_client, '/stock/')
    assert resp.status_code == 200
    assert b'badge-funded' in resp.data
    assert b'Chip Investor' in resp.data
    assert b'action="/stock/assign-funder"' in resp.data


def test_stock_list_hides_funder_ui_without_investors(logged_in_client, app):
    _add_stock(logged_in_client, app, 'Plain Phone')
    resp = _get(app, logged_in_client, '/stock/')
    assert b'badge-funded' not in resp.data
    assert b'action="/stock/assign-funder"' not in resp.data
    assert b'class="row-select"' not in resp.data


def test_bulk_assign_mixed_ids(logged_in_client, app, second_user):
    pid = _add_partner(logged_in_client, app, 'Bulk Investor', 'investor')
    own_a = _add_stock(logged_in_client, app, 'Bulk Phone A')
    own_b = _add_stock(logged_in_client, app, 'Bulk Phone B')

    with app.app_context():
        other_shop = Shop.query.filter_by(user_id=second_user.id).first()
        foreign_item = StockItem(shop_id=other_shop.id, model_name='Foreign Phone',
                                 quantity=1, cost_price=10000, purchase_date=_date(2026, 9, 20),
                                 status='in_stock')
        db.session.add(foreign_item)
        db.session.commit()
        foreign_id = foreign_item.id

    resp = _post(app, logged_in_client, '/stock/assign-funder', {
        'item_ids': [str(own_a), str(own_b), str(foreign_id)],
        'partner_id': str(pid),
    }, follow_redirects=True)
    assert b'2 phone(s) assigned to Bulk Investor' in resp.data

    with app.app_context():
        assert db.session.get(StockItem, own_a).funded_by_partner_id == pid
        assert db.session.get(StockItem, own_b).funded_by_partner_id == pid
        assert db.session.get(StockItem, foreign_id).funded_by_partner_id is None


def test_bulk_assign_empty_selection_warns(logged_in_client, app):
    pid = _add_partner(logged_in_client, app, 'Empty Sel Investor', 'investor')
    item_id = _add_stock(logged_in_client, app, 'Untouched Phone')

    resp = _post(app, logged_in_client, '/stock/assign-funder', {
        'partner_id': str(pid),
    }, follow_redirects=True)
    assert b'No phones selected' in resp.data
    with app.app_context():
        assert db.session.get(StockItem, item_id).funded_by_partner_id is None


def test_bulk_assign_foreign_partner_rejected(logged_in_client, app, second_user):
    with app.app_context():
        other_shop = Shop.query.filter_by(user_id=second_user.id).first()
        foreign = Partner(shop_id=other_shop.id, name='Not Mine', role='investor',
                          investment_amount=100000)
        db.session.add(foreign)
        db.session.commit()
        foreign_pid = foreign.id

    item_id = _add_stock(logged_in_client, app, 'Safe Phone')
    resp = _post(app, logged_in_client, '/stock/assign-funder', {
        'item_ids': [str(item_id)],
        'partner_id': str(foreign_pid),
    }, follow_redirects=True)
    assert b'Invalid funder selected' in resp.data
    with app.app_context():
        assert db.session.get(StockItem, item_id).funded_by_partner_id is None


def test_bulk_assign_clear(logged_in_client, app):
    pid = _add_partner(logged_in_client, app, 'Clear Investor', 'investor')
    item_id = _add_stock(logged_in_client, app, 'Clearable Phone', funded_by_partner_id=pid)

    resp = _post(app, logged_in_client, '/stock/assign-funder', {
        'item_ids': [str(item_id)],
        'partner_id': '0',
    }, follow_redirects=True)
    assert b'1 phone(s) unassigned' in resp.data
    with app.app_context():
        assert db.session.get(StockItem, item_id).funded_by_partner_id is None


def test_bulk_assign_other_tenant_items_untouched(logged_in_client, app, second_user):
    pid = _add_partner(logged_in_client, app, 'Tenant Investor', 'investor')
    with app.app_context():
        other_shop = Shop.query.filter_by(user_id=second_user.id).first()
        foreign_item = StockItem(shop_id=other_shop.id, model_name='Victim Phone',
                                 quantity=1, cost_price=10000, purchase_date=_date(2026, 9, 20),
                                 status='in_stock')
        db.session.add(foreign_item)
        db.session.commit()
        foreign_id = foreign_item.id

    resp = _post(app, logged_in_client, '/stock/assign-funder', {
        'item_ids': [str(foreign_id)],
        'partner_id': str(pid),
    }, follow_redirects=True)
    assert b'No matching phones found' in resp.data
    with app.app_context():
        assert db.session.get(StockItem, foreign_id).funded_by_partner_id is None


def _login_investor(app, investor_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['investor_id'] = investor_id
    return client


def test_investor_sees_only_own_funded_phones(logged_in_client, app, second_user):
    pid_a = _add_partner(logged_in_client, app, 'Alice Funded', 'investor',
                         email='alice@inv.com')
    pid_b = _add_partner(logged_in_client, app, 'Bob Funded', 'investor')
    _add_stock(logged_in_client, app, 'Own One', funded_by_partner_id=pid_a)
    _add_stock(logged_in_client, app, 'Own Two', funded_by_partner_id=pid_a)
    _add_stock(logged_in_client, app, 'Bobs Phone', funded_by_partner_id=pid_b)
    _add_stock(logged_in_client, app, 'Unfunded Phone')

    with app.app_context():
        other_shop = Shop.query.filter_by(user_id=second_user.id).first()
        foreign_partner = Partner(shop_id=other_shop.id, name='Foreign Investor',
                                  role='investor', investment_amount=100000,
                                  investment_ratio=100.0)
        db.session.add(foreign_partner)
        db.session.flush()
        db.session.add(StockItem(shop_id=other_shop.id, model_name='Foreign Tenant Phone',
                                 quantity=1, cost_price=20000, purchase_date=_date(2026, 9, 20),
                                 status='in_stock', funded_by_partner_id=foreign_partner.id))
        db.session.commit()
        inv_id = db.session.get(Partner, pid_a).investor_user_id
        assert inv_id is not None

    inv_client = _login_investor(app, inv_id)
    resp = _get(app, inv_client, '/investor/my-phones')
    assert resp.status_code == 200
    assert b'Own One' in resp.data
    assert b'Own Two' in resp.data
    assert b'Bobs Phone' not in resp.data
    assert b'Unfunded Phone' not in resp.data
    assert b'Foreign Tenant Phone' not in resp.data


def test_investor_dashboard_count_matches_list(logged_in_client, app):
    pid = _add_partner(logged_in_client, app, 'Count Investor', 'investor',
                       email='count@inv.com')
    _add_stock(logged_in_client, app, 'Count One', funded_by_partner_id=pid)
    _add_stock(logged_in_client, app, 'Count Two', funded_by_partner_id=pid)
    _add_stock(logged_in_client, app, 'Count Unfunded')

    with app.app_context():
        inv_id = db.session.get(Partner, pid).investor_user_id

    inv_client = _login_investor(app, inv_id)

    dash = _get(app, inv_client, '/investor/dashboard')
    assert dash.status_code == 200
    m = re.search(rb'margin-top:8px;">(\d+)<', dash.data)
    assert m, 'dashboard count element not found'
    assert int(m.group(1)) == 2

    phones = _get(app, inv_client, '/investor/my-phones')
    assert phones.status_code == 200
    assert phones.data.count(b'data-label="Model"') == 2


def test_investor_my_phones_handles_unsold_and_empty(logged_in_client, app):
    # Unfunded-balance phone: sale_price is NULL -> must render (was a 500)
    pid = _add_partner(logged_in_client, app, 'Null Price Investor', 'investor',
                       email='nullprice@inv.com')
    _add_stock(logged_in_client, app, 'Unsold Funded Phone', funded_by_partner_id=pid)

    with app.app_context():
        inv_id = db.session.get(Partner, pid).investor_user_id

    inv_client = _login_investor(app, inv_id)
    resp = _get(app, inv_client, '/investor/my-phones')
    assert resp.status_code == 200
    assert b'Unsold Funded Phone' in resp.data
    assert b'No phones funded by your investment yet.' not in resp.data

    # Investor with zero funded phones -> empty state
    pid2 = _add_partner(logged_in_client, app, 'Empty Investor', 'investor',
                        email='empty@inv.com')
    with app.app_context():
        inv_id2 = db.session.get(Partner, pid2).investor_user_id
    inv_client2 = _login_investor(app, inv_id2)
    resp = _get(app, inv_client2, '/investor/my-phones')
    assert resp.status_code == 200
    assert b'No phones funded by your investment yet.' in resp.data


def test_funding_does_not_affect_split_engine(test_user, app):
    from app.models.shareholder import SplitRule
    from app.shareholders.engine import calculate_split

    with app.app_context():
        shop = Shop.query.filter_by(user_id=test_user.id).first()
        owner = Partner(shop_id=shop.id, name='Eng Owner', role='owner',
                        investment_amount=200000)
        inv = Partner(shop_id=shop.id, name='Eng Investor', role='investor',
                      investment_amount=100000)
        db.session.add_all([owner, inv])
        db.session.flush()
        db.session.add(SplitRule(shop_id=shop.id, management_base_pct=20.0))
        db.session.commit()

        before = calculate_split(shop.id, 80000)
        assert len(before['splits']) == 2

        db.session.add(StockItem(
            shop_id=shop.id, model_name='Eng Phone A', quantity=2, cost_price=50000,
            purchase_date=_date(2026, 9, 20), status='in_stock',
            funded_by_partner_id=inv.id))
        db.session.add(StockItem(
            shop_id=shop.id, model_name='Eng Phone B', quantity=1, cost_price=30000,
            purchase_date=_date(2026, 9, 20), status='in_stock',
            funded_by_partner_id=owner.id))
        db.session.commit()

        after = calculate_split(shop.id, 80000)
        assert before == after


def test_edit_form_preselects_current_funder(logged_in_client, app):
    pid = _add_partner(logged_in_client, app, 'Preselect Investor', 'investor')
    item_id = _add_stock(logged_in_client, app, 'Preselect Phone', funded_by_partner_id=pid)

    resp = _get(app, logged_in_client, f'/stock/{item_id}/edit')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    opt = f'<option value="{pid}" selected>'
    assert opt in html
