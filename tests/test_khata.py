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


def test_khata_type_filter_hides_other_section(logged_in_client):
    resp = logged_in_client.get('/khata/?type=receivable')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Customers with pending payments' in html
    assert 'Suppliers with pending payments' not in html
    assert 'Show all' in html

    resp = logged_in_client.get('/khata/?type=payable')
    html = resp.get_data(as_text=True)
    assert 'Suppliers with pending payments' in html
    assert 'Customers with pending payments' not in html
    assert 'Show all' in html

    resp = logged_in_client.get('/khata/')
    html = resp.get_data(as_text=True)
    assert 'Customers with pending payments' in html
    assert 'Suppliers with pending payments' in html
    assert 'Show all' not in html


# ── Inline settlement flow (custom amount, no confirm, Urdu/space names) ──

from urllib.parse import quote  # noqa: E402
import re  # noqa: E402


def test_party_page_shows_inline_settle_form(logged_in_client):
    _add_stock(logged_in_client, 'Inline Settle Phone', 40000, 20000, 'Inline Supplier')

    resp = logged_in_client.get('/khata/party/Inline Supplier')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="settleAmount"' in html
    assert 'value="20000.00"' in html
    assert 'max="20000.00"' in html
    assert 'validateSettle' in html
    assert 'onclick="return confirm' not in html
    assert 'khata-name' in html
    assert 'dir="auto"' in html


def test_settle_party_partial_amount(logged_in_client, app):
    _add_stock(logged_in_client, 'Partial Phone', 40000, 20000, 'Partial Supplier')

    resp = logged_in_client.post(
        '/khata/party/Partial Supplier/settle',
        data={'amount': '5000'}, follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name='Partial Supplier').first()
        assert entry.status == 'pending'
        assert float(entry.settled_amount or 0) == 5000.0
        cash = CashEntry.query.filter(
            CashEntry.description.like('Khata settled%Partial Supplier%')
        ).first()
        assert cash is not None
        assert cash.entry_type == 'out'
        assert float(cash.amount) == 5000.0

    resp = logged_in_client.get('/khata/party/Partial Supplier')
    html = resp.get_data(as_text=True)
    assert '15000' in html  # remaining pending shown
    assert 'value="15000.00"' in html


def test_settle_party_full_amount_marks_settled(logged_in_client, app):
    _add_stock(logged_in_client, 'Full Party Phone', 40000, 20000, 'Full Party Supplier')

    resp = logged_in_client.post(
        '/khata/party/Full Party Supplier/settle',
        data={'amount': '20000'}, follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name='Full Party Supplier').first()
        assert entry.status == 'settled'
        assert entry.settled_date is not None
        assert float(entry.settled_amount) == 20000.0


def test_settle_party_rejects_invalid_amounts(logged_in_client, app):
    _add_stock(logged_in_client, 'Reject Phone', 40000, 20000, 'Reject Supplier')

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name='Reject Supplier').first()
        entry_id = entry.id

    for bad in ('0', '-100', '20001', 'abc', ''):
        resp = logged_in_client.post(
            '/khata/party/Reject Supplier/settle',
            data={'amount': bad}, follow_redirects=False,
        )
        assert resp.status_code == 302

    with app.app_context():
        entry = KhataEntry.query.get(entry_id)
        assert entry.status == 'pending'
        assert float(entry.settled_amount or 0) == 0.0
        assert CashEntry.query.filter(
            CashEntry.description.like('Khata settled%Reject Supplier%')
        ).count() == 0


def test_settle_party_amount_with_commas_accepted(logged_in_client, app):
    _add_stock(logged_in_client, 'Comma Phone', 40000, 20000, 'Comma Supplier')

    resp = logged_in_client.post(
        '/khata/party/Comma Supplier/settle',
        data={'amount': '5,000'}, follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name='Comma Supplier').first()
        assert float(entry.settled_amount or 0) == 5000.0


def test_settle_party_fifo_across_multiple_entries(logged_in_client, app):
    _add_stock(logged_in_client, 'Fifo Phone A', 60000, 40000, 'Fifo Supplier')
    _add_stock(logged_in_client, 'Fifo Phone B', 50000, 30000, 'Fifo Supplier')

    resp = logged_in_client.post(
        '/khata/party/Fifo Supplier/settle',
        data={'amount': '25000'}, follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        entries = KhataEntry.query.filter_by(party_name='Fifo Supplier').order_by(
            KhataEntry.id.asc()
        ).all()
        assert len(entries) == 2
        # Oldest entry fully settled first
        assert entries[0].status == 'settled'
        assert float(entries[0].settled_amount) == 20000.0
        # Remainder applied to second entry (partial)
        assert entries[1].status == 'pending'
        assert float(entries[1].settled_amount or 0) == 5000.0

        cash_total = sum(
            float(c.amount) for c in CashEntry.query.filter(
                CashEntry.description.like('Khata settled%Fifo Supplier%')
            )
        )
        assert cash_total == 25000.0


def test_party_detail_roundtrip_with_spaces_and_urdu_name(logged_in_client, app):
    urdu_name = 'کاشف عباس احمد'
    _add_stock(logged_in_client, 'Urdu Phone', 40000, 20000, urdu_name)

    # Link on list page opens the party despite spaces + Urdu characters
    list_resp = logged_in_client.get('/khata/')
    list_html = list_resp.get_data(as_text=True)
    m = re.search(r'href="([^"]*)" class="party-open"', list_html)
    assert m, 'party-open link missing on khata list'
    page = logged_in_client.get(m.group(1))
    assert page.status_code == 200
    page_html = page.get_data(as_text=True)
    assert urdu_name in page_html
    assert 'dir="auto"' in page_html
    assert 'id="settleAmount"' in page_html

    # Settle with a custom amount via the URL-encoded party route
    resp = logged_in_client.post(
        f'/khata/party/{quote(urdu_name)}/settle',
        data={'amount': '7500'}, follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name=urdu_name).first()
        assert entry is not None
        assert entry.status == 'pending'
        assert float(entry.settled_amount or 0) == 7500.0


def test_party_detail_handles_raw_percent_encoded_path(logged_in_client, app):
    """LiteSpeed passes PATH_INFO still percent-encoded — the route must decode
    it, otherwise names with spaces never match their khata entries."""
    _add_stock(logged_in_client, 'Raw Path Phone', 40000, 20000, 'Raw Path Supplier')

    resp = logged_in_client.get(
        '/khata/party/Raw%20Path%20Supplier',
        environ_overrides={'PATH_INFO': '/khata/party/Raw%20Path%20Supplier'},
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Raw Path Supplier' in html
    assert 'id="settleAmount"' in html
    assert 'value="20000.00"' in html

    resp = logged_in_client.post(
        '/khata/party/Raw%20Path%20Supplier/settle',
        data={'amount': '9000'},
        environ_overrides={'PATH_INFO': '/khata/party/Raw%20Path%20Supplier/settle'},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        entry = KhataEntry.query.filter_by(party_name='Raw Path Supplier').first()
        assert entry.status == 'pending'
        assert float(entry.settled_amount or 0) == 9000.0


# ── Editable per-row settle (custom amount on each pending row) ─────────────

def test_row_settle_with_custom_amount(logged_in_client, app):
    _add_stock(logged_in_client, 'Row Edit Phone', 40000, 20000, 'Row Edit Supplier')
    with app.app_context():
        khata = KhataEntry.query.filter_by(party_name='Row Edit Supplier').first()
        khata_id = khata.id

    resp = logged_in_client.post(
        f'/khata/{khata_id}/settle',
        data={'amount': '7000'}, follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        entry = KhataEntry.query.get(khata_id)
        assert entry.status == 'pending'
        assert float(entry.settled_amount or 0) == 7000.0
        cash = CashEntry.query.filter(
            CashEntry.description.like('Khata settled%Row Edit Supplier%')
        ).first()
        assert float(cash.amount) == 7000.0


def test_row_settle_without_amount_settles_full(logged_in_client, app):
    """Old callers (no amount field) still settle the whole remainder."""
    _add_stock(logged_in_client, 'Row Full Phone', 40000, 20000, 'Row Full Supplier')
    with app.app_context():
        khata_id = KhataEntry.query.filter_by(party_name='Row Full Supplier').first().id

    logged_in_client.post(f'/khata/{khata_id}/settle', follow_redirects=False)

    with app.app_context():
        entry = KhataEntry.query.get(khata_id)
        assert entry.status == 'settled'
        assert float(entry.settled_amount) == 20000.0


def test_row_settle_rejects_over_amount(logged_in_client, app):
    _add_stock(logged_in_client, 'Row Over Phone', 40000, 20000, 'Row Over Supplier')
    with app.app_context():
        khata_id = KhataEntry.query.filter_by(party_name='Row Over Supplier').first().id

    resp = logged_in_client.post(
        f'/khata/{khata_id}/settle',
        data={'amount': '25000'}, follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        entry = KhataEntry.query.get(khata_id)
        assert entry.status == 'pending'
        assert float(entry.settled_amount or 0) == 0.0
        assert CashEntry.query.filter(
            CashEntry.description.like('Khata settled%Row Over Supplier%')
        ).count() == 0


def test_row_settle_rejects_zero_and_garbage(logged_in_client, app):
    _add_stock(logged_in_client, 'Row Zero Phone', 40000, 20000, 'Row Zero Supplier')
    with app.app_context():
        khata_id = KhataEntry.query.filter_by(party_name='Row Zero Supplier').first().id

    for bad in ('0', '-5', 'abc'):
        logged_in_client.post(
            f'/khata/{khata_id}/settle', data={'amount': bad},
            follow_redirects=False,
        )

    with app.app_context():
        entry = KhataEntry.query.get(khata_id)
        assert entry.status == 'pending'
        assert float(entry.settled_amount or 0) == 0.0


def test_row_settle_repeated_partials_reach_settled(logged_in_client, app):
    _add_stock(logged_in_client, 'Row Steps Phone', 40000, 20000, 'Row Steps Supplier')
    with app.app_context():
        khata_id = KhataEntry.query.filter_by(party_name='Row Steps Supplier').first().id

    logged_in_client.post(f'/khata/{khata_id}/settle', data={'amount': '8000'},
                          follow_redirects=False)
    logged_in_client.post(f'/khata/{khata_id}/settle', data={'amount': '12000'},
                          follow_redirects=False)

    with app.app_context():
        entry = KhataEntry.query.get(khata_id)
        assert entry.status == 'settled'
        assert float(entry.settled_amount) == 20000.0
        assert entry.settled_date is not None
        total_cash = sum(
            float(c.amount) for c in CashEntry.query.filter(
                CashEntry.description.like('Khata settled%Row Steps Supplier%')
            )
        )
        assert total_cash == 20000.0


def test_pending_row_has_editable_amount_input(logged_in_client):
    _add_stock(logged_in_client, 'Row Input Phone', 40000, 20000, 'Row Input Supplier')
    resp = logged_in_client.get('/khata/party/Row Input Supplier')
    html = resp.get_data(as_text=True)
    assert 'class="row-settle-amount"' in html
    assert 'value="20000.00"' in html
    assert 'max="20000.00"' in html
    assert 'validateRowSettle' in html
