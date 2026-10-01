from datetime import date

from app.extensions import db
from app.models.stock import StockItem
from app.models.khata import KhataEntry
from app.utils import wa_me_link, validate_whatsapp, normalise_whatsapp, wa_share_link


def _add_stock(client, model, cost, paid, supplier='', whatsapp=''):
    return client.post('/stock/in', data={
        'model_name': model,
        'quantity': 1,
        'cost_price': cost,
        'purchase_date': '2026-09-14',
        'supplier_name': supplier,
        'purchase_whatsapp': whatsapp,
        'purchase_paid': paid,
        'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    }, follow_redirects=False)


def _sell(client, item_id, price, received, customer='', whatsapp=''):
    return client.post(f'/stock/{item_id}/sell', data={
        'sale_price': price,
        'sale_date': '2026-09-15',
        'customer_name': customer,
        'sale_whatsapp': whatsapp,
        'sale_received': received,
        'sale_expense_desc': '',
        'sale_expense_amount': 0,
    }, follow_redirects=False)


def _item_id(app, model):
    with app.app_context():
        return StockItem.query.filter_by(model_name=model).first().id


# ── helpers ─────────────────────────────────────────────

def test_wa_me_link_normalises_numbers():
    assert wa_me_link('0300 1234567') == 'https://wa.me/923001234567'
    assert wa_me_link('923001234567', 'hello') == 'https://wa.me/923001234567?text=hello'
    assert wa_me_link('+92-300-1234567') == 'https://wa.me/923001234567'
    assert wa_me_link('') is None
    assert wa_me_link(None) is None
    assert wa_share_link('', 'reminder') == 'https://wa.me/?text=reminder'


def test_validate_whatsapp_accepts_blank_and_rejects_junk():
    assert validate_whatsapp('') is None
    assert validate_whatsapp(None) is None
    assert validate_whatsapp('0300 1234567') is None
    assert validate_whatsapp('abc') is not None
    assert validate_whatsapp('12345') is not None  # too short
    assert normalise_whatsapp('0300 123-4567') == '03001234567'


# ── stock in / out ──────────────────────────────────────

def test_stock_in_saves_whatsapp_and_redirects_to_receipt(logged_in_client, app):
    resp = _add_stock(logged_in_client, 'Receipt Phone', 85000, 85000,
                      supplier='Sialkot Traders', whatsapp='0300 1234567')
    assert resp.status_code == 302
    assert '/receipt' in resp.headers['Location']

    with app.app_context():
        item = StockItem.query.filter_by(model_name='Receipt Phone').first()
        assert item.purchase_whatsapp == '03001234567'


def test_stock_in_form_shows_whatsapp_field(logged_in_client):
    resp = logged_in_client.get('/stock/in')
    assert resp.status_code == 200
    assert b'purchase_whatsapp' in resp.data
    assert b'data-parties' in resp.data
    assert b'data-wa-field' in resp.data


def test_invalid_whatsapp_is_rejected(logged_in_client, app):
    resp = _add_stock(logged_in_client, 'Bad Number Phone', 50000, 50000, whatsapp='not-a-number')
    assert resp.status_code == 200  # re-rendered the form
    assert b'valid WhatsApp number' in resp.data

    with app.app_context():
        assert StockItem.query.filter_by(model_name='Bad Number Phone').first() is None


def test_stock_out_saves_customer_whatsapp(logged_in_client, app):
    _add_stock(logged_in_client, 'Sold Phone', 40000, 40000)
    item_id = _item_id(app, 'Sold Phone')

    resp = _sell(logged_in_client, item_id, 50000, 50000,
                 customer='Bilal', whatsapp='0345 7654321')
    assert resp.status_code == 302
    assert '/receipt' in resp.headers['Location']
    assert 'type=sale' in resp.headers['Location']

    with app.app_context():
        item = StockItem.query.get(item_id)
        assert item.sale_whatsapp == '03457654321'


# ── receipt page ────────────────────────────────────────

def test_purchase_receipt_renders_with_share_link(logged_in_client, app, test_user):
    _add_stock(logged_in_client, 'Receipt Show', 85000, 60000,
               supplier='Sialkot Traders', whatsapp='03001234567')
    item_id = _item_id(app, 'Receipt Show')

    resp = logged_in_client.get(f'/stock/{item_id}/receipt?type=purchase')
    assert resp.status_code == 200
    assert b'Purchase Receipt' in resp.data
    assert b'Receipt Show' in resp.data
    assert b'https://wa.me/923001234567?text=' in resp.data
    assert b'Sialkot Traders' in resp.data
    assert b'html2canvas' in resp.data
    assert b'id="receipt-card"' in resp.data


def test_receipt_without_number_has_no_wa_link(logged_in_client, app):
    _add_stock(logged_in_client, 'No Number Phone', 30000, 30000)
    item_id = _item_id(app, 'No Number Phone')

    resp = logged_in_client.get(f'/stock/{item_id}/receipt')
    assert resp.status_code == 200
    assert b'wa.me' not in resp.data
    assert b'Receipt No:' in resp.data


def test_sale_receipt_shows_received_in_full(logged_in_client, app):
    _add_stock(logged_in_client, 'Full Sale Phone', 40000, 40000)
    item_id = _item_id(app, 'Full Sale Phone')
    _sell(logged_in_client, item_id, 50000, 50000, customer='Bilal', whatsapp='03457654321')

    resp = logged_in_client.get(f'/stock/{item_id}/receipt?type=sale')
    assert resp.status_code == 200
    assert b'Sale Receipt' in resp.data
    assert b'Received in full' in resp.data
    assert b'https://wa.me/923457654321?text=' in resp.data


def test_receipt_is_scoped_to_own_shop(logged_in_client, app, second_user):
    _add_stock(logged_in_client, 'Private Phone', 40000, 40000)
    item_id = _item_id(app, 'Private Phone')

    other = app.test_client()
    with other.session_transaction() as sess:
        sess['_user_id'] = str(second_user.id)

    resp = other.get(f'/stock/{item_id}/receipt')
    assert resp.status_code == 404


# ── settle → receipt ────────────────────────────────────

def test_settle_redirects_to_linked_receipt(logged_in_client, app):
    _add_stock(logged_in_client, 'Pending Phone', 60000, 40000, supplier='Ahmed Mobiles')
    item_id = _item_id(app, 'Pending Phone')

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name='Ahmed Mobiles').first()
        entry_id = entry.id

    resp = logged_in_client.post(f'/khata/{entry_id}/settle', follow_redirects=False)
    assert resp.status_code == 302
    assert f'/stock/{item_id}/receipt' in resp.headers['Location']
    assert 'settled=1' in resp.headers['Location']

    receipt = logged_in_client.get(resp.headers['Location'].replace('http://localhost', ''))
    assert receipt.status_code == 200
    assert b'Paid in full' in receipt.data
    assert b'Settled on:' in receipt.data


# ── khata reminders ─────────────────────────────────────

def test_khata_list_shows_whatsapp_reminder(logged_in_client, app):
    _add_stock(logged_in_client, 'Reminder Phone', 60000, 40000, supplier='Ahmed Mobiles')

    resp = logged_in_client.get('/khata/')
    assert resp.status_code == 200
    assert b'wa.me' in resp.data
    assert b'Remind' in resp.data or b'Message' in resp.data


def test_khata_party_page_shows_reminder_button(logged_in_client, app):
    _add_stock(logged_in_client, 'Party Phone', 60000, 40000, supplier='Ahmed Mobiles')

    resp = logged_in_client.get('/khata/party/Ahmed%20Mobiles')
    assert resp.status_code == 200
    assert b'Send reminder' in resp.data
    assert b'https://wa.me/' in resp.data


def test_receipt_pending_survives_without_khata_entry(logged_in_client, app):
    """Pending still shows when no khata row is linked (legacy/manual data)."""
    from datetime import date as _date

    with app.app_context():
        from app.models.shop import Shop

        shop = Shop.query.first()
        item = StockItem(
            shop_id=shop.id, model_name='Orphan Pending Phone', quantity=1,
            cost_price=60000, purchase_date=_date(2026, 9, 5), purchase_paid=40000,
            purchase_pending=20000, supplier_name='No Khata Supplier',
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    resp = logged_in_client.get(f'/stock/{item_id}/receipt?type=purchase')
    assert resp.status_code == 200
    assert b'Pending to supplier' in resp.data
    assert b'Rs 20,000' in resp.data
    assert b'Paid in full' not in resp.data
