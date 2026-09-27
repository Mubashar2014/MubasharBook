from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models.shop import Shop
from app.models.cashbook import CashEntry
from app.models.expense import Expense, ExpenseCategory
from app.models.shareholder import Period
from app.utils import get_cash_balance, OPENING_CAPITAL_DESC
from app.shareholders.engine import _calculate_period_net_profit
from backfill_expense_cash import backfill


def _shop_id(user):
    return Shop.query.filter_by(user_id=user.id).first().id


def _add_expense_via_route(client, app, user, amount='5000', desc='Bijli bill',
                           when=None, category='Tea & Misc'):
    """Walk the real form flow: GET the form (seeds + returns category choices),
    then POST it. Returns (status_code, location)."""
    when = when or date.today().isoformat()
    with app.app_context():
        resp = client.get('/expenses/add')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        import re
        from html import unescape
        cid = None
        for m in re.finditer(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)</option>', html):
            if unescape(m.group(2)).strip() == category:
                cid = m.group(1)
                break
        assert cid, f'category {category!r} not in form choices'

    with app.app_context():
        resp = client.post('/expenses/add', data={
            'category_id': cid,
            'amount': amount,
            'description': desc,
            'expense_date': when,
        }, follow_redirects=False)
    return resp.status_code, resp.headers.get('Location')


# ---------------------------------------------------------------- 500 regression

def test_expense_list_renders_with_data(logged_in_client, app, test_user):
    """Regression: list.html used expense.category with no relationship → 500."""
    code, loc = _add_expense_via_route(logged_in_client, app, test_user)
    assert code == 302
    assert loc == '/expenses/'

    resp = logged_in_client.get('/expenses/')
    assert resp.status_code == 200
    assert b'Bijli bill' in resp.data
    assert b'Tea &amp; Misc' in resp.data  # Jinja HTML-escapes '&'


def test_expense_list_survives_orphan_category(logged_in_client, app, test_user):
    """A row whose category row is missing must not 500 the page."""
    with app.app_context():
        shop_id = _shop_id(test_user)
        # point at a category id that doesn't exist (raw SQL bypasses the ORM's
        # attempt to null the FK, which NOT NULL would reject)
        db.session.execute(db.text(
            "INSERT INTO expenses (shop_id, category_id, amount, description, expense_date) "
            "VALUES (:s, 999999, 500, 'orphan row', :d)"
        ), {'s': shop_id, 'd': date.today().isoformat()})
        db.session.commit()

    resp = logged_in_client.get('/expenses/')
    assert resp.status_code == 200
    assert b'orphan row' in resp.data


def test_expense_filter_by_category_renders(logged_in_client, app, test_user):
    _add_expense_via_route(logged_in_client, app, test_user)
    with app.app_context():
        cat_id = ExpenseCategory.query.filter_by(name='Tea & Misc').first().id

    resp = logged_in_client.get(f'/expenses/?category_id={cat_id}')
    assert resp.status_code == 200
    assert b'Bijli bill' in resp.data


# ---------------------------------------------------------------- cashbook pairing

def test_add_expense_creates_cash_out_row(logged_in_client, app, test_user):
    _add_expense_via_route(logged_in_client, app, test_user, amount='5000')

    with app.app_context():
        expense = Expense.query.filter_by(description='Bijli bill').first()
        assert expense is not None

        cash = CashEntry.query.filter_by(linked_expense_id=expense.id).first()
        assert cash is not None
        assert cash.entry_type == 'out'
        assert float(cash.amount) == 5000.0
        assert cash.entry_date == expense.expense_date
        assert cash.description.startswith('Expense: ')
        assert 'Bijli bill' in cash.description
        # exactly one cash row per expense
        assert CashEntry.query.filter_by(linked_expense_id=expense.id).count() == 1


def test_add_expense_reduces_cash_in_hand(logged_in_client, app, test_user):
    logged_in_client.get('/dashboard')  # seeds opening capital
    with app.app_context():
        shop_id = _shop_id(test_user)
        before = get_cash_balance(shop_id)  # opening capital 100000
    assert float(before) == 100000.0

    _add_expense_via_route(logged_in_client, app, test_user, amount='5000')

    with app.app_context():
        after = get_cash_balance(shop_id)
    assert float(after) == float(before) - 5000.0


def test_expense_cash_row_gets_running_balance(logged_in_client, app, test_user):
    _add_expense_via_route(logged_in_client, app, test_user, amount='5000')

    with app.app_context():
        cash = CashEntry.query.filter(
            CashEntry.linked_expense_id.isnot(None)
        ).first()
        assert cash is not None
        # opening 100000 - 5000
        assert float(cash.balance_after) == 95000.0
        assert cash.description.startswith('Expense: ')


def test_expense_shows_in_cashbook_list(logged_in_client, app, test_user):
    _add_expense_via_route(logged_in_client, app, test_user, amount='5000')

    resp = logged_in_client.get('/cashbook/')
    assert resp.status_code == 200
    assert b'Bijli bill' in resp.data
    assert b'Expense: Tea &amp; Misc' in resp.data  # Jinja HTML-escapes '&'


def test_manual_cash_entry_delete_does_not_touch_expense_pair(logged_in_client, app, test_user):
    """Deleting an unrelated manual entry must leave the expense pairing intact."""
    _add_expense_via_route(logged_in_client, app, test_user, amount='5000')

    with app.app_context():
        manual = CashEntry(
            shop_id=_shop_id(test_user), entry_type='in', amount=20000,
            description='Manual unrelated', entry_date=date.today(),
        )
        db.session.add(manual)
        db.session.commit()
        manual_id = manual.id

    logged_in_client.post(f'/cashbook/{manual_id}/delete')

    with app.app_context():
        assert db.session.get(CashEntry, manual_id) is None
        assert CashEntry.query.filter(
            CashEntry.linked_expense_id.isnot(None)
        ).count() == 1


def test_expense_cash_row_cannot_be_deleted_from_cashbook(logged_in_client, app, test_user):
    """Auto-created expense rows are protected, same as stock-linked rows."""
    _add_expense_via_route(logged_in_client, app, test_user, amount='5000')

    with app.app_context():
        cash = CashEntry.query.filter(
            CashEntry.linked_expense_id.isnot(None)
        ).first()
        assert cash is not None
        cash_id = cash.id

    resp = logged_in_client.post(f'/cashbook/{cash_id}/delete', follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(CashEntry, cash_id) is not None


# ------------------------------------------------- no double-subtract (the point)

def test_dashboard_today_net_not_double_subtracted(logged_in_client, app, test_user):
    """today_net must be In − Out only; the expense lives inside Out.

    Wrong (old) result would be -10,000; correct is -5,000.
    """
    _add_expense_via_route(logged_in_client, app, test_user, amount='5000')

    resp = logged_in_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    import re
    m = re.search(r'Today.s Net.*?class="v[^"]* num">Rs ([^<]+)</div>', html, re.S)
    assert m, 'Today\'s Net stat not found on dashboard'
    assert m.group(1).strip() == '-5,000', f'got {m.group(1)!r} — double subtracted'


def test_dashboard_today_net_counts_non_expense_cash_too(logged_in_client, app, test_user):
    """A real cash-out (stock purchase) plus an expense both land in Out."""
    logged_in_client.post('/stock/in', data={
        'model_name': 'X Phone', 'quantity': 1, 'cost_price': 30000,
        'purchase_date': date.today().isoformat(), 'supplier_name': '',
        'purchase_paid': 30000, 'purchase_expense_desc': '',
        'purchase_expense_amount': 0,
    })
    _add_expense_via_route(logged_in_client, app, test_user, amount='5000')

    resp = logged_in_client.get('/dashboard')
    html = resp.get_data(as_text=True)
    import re
    m = re.search(r'Today.s Net.*?class="v[^"]* num">Rs ([^<]+)</div>', html, re.S)
    assert m
    # no cash in today: -(30000 stock + 5000 expense) = -35,000
    assert m.group(1).strip() == '-35,000', f'got {m.group(1)!r}'


def test_period_net_profit_is_cash_basis_only(app, test_user):
    """engine: cash_in − cash_out, where cash_out already includes the expense."""
    with app.app_context():
        shop_id = _shop_id(test_user)
        today = date.today()
        period = Period(shop_id=shop_id, period_start=today - timedelta(days=1),
                        period_end=today + timedelta(days=1), status='open')
        db.session.add(period)
        db.session.add_all([
            CashEntry(shop_id=shop_id, entry_type='in', amount=100000,
                      description='Sales', entry_date=today),
            CashEntry(shop_id=shop_id, entry_type='out', amount=35000,
                      description='Stock purchase', entry_date=today),
            CashEntry(shop_id=shop_id, entry_type='out', amount=5000,
                      description='Expense: Tea & Misc', entry_date=today),
        ])
        db.session.add(Expense(shop_id=shop_id, category_id=1, amount=5000,
                               description='Bijli bill', expense_date=today))
        db.session.commit()

        net = _calculate_period_net_profit(period)
        # 100000 in − 40000 out = 60000 (NOT 55000, which would double-subtract)
        assert Decimal(str(net)) == Decimal('60000'), f'got {net} — double subtracted'


def test_accrual_pnl_still_subtracts_expenses(logged_in_client, app, test_user):
    """P&L reads the Expense table only (no cash involved) — must be unchanged."""
    with app.app_context():
        shop_id = _shop_id(test_user)
        cat = ExpenseCategory(shop_id=shop_id, name='Accrual Rent', is_default=False)
        db.session.add(cat)
        db.session.flush()
        db.session.add(Expense(shop_id=shop_id, category_id=cat.id, amount=12345,
                               description='accrual only', expense_date=date.today()))
        db.session.commit()

    resp = logged_in_client.get('/reports/pnl')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '12,345' in html, 'expense missing from P&L'


# ---------------------------------------------------------------- backfill

def test_backfill_pairs_unpaired_expenses_and_is_idempotent(app, test_user):
    with app.app_context():
        shop_id = _shop_id(test_user)
        cat = ExpenseCategory(shop_id=shop_id, name='Legacy', is_default=False)
        db.session.add(cat)
        db.session.flush()
        legacy = Expense(shop_id=shop_id, category_id=cat.id, amount=7500,
                         description='old expense', expense_date=date(2026, 9, 20))
        db.session.add(legacy)
        db.session.commit()
        legacy_id = legacy.id

        # unpaired at this point
        assert CashEntry.query.filter_by(linked_expense_id=legacy_id).count() == 0

        created = backfill()
        assert created == 1
        assert CashEntry.query.filter_by(linked_expense_id=legacy_id).count() == 1

        cash = CashEntry.query.filter_by(linked_expense_id=legacy_id).first()
        assert cash.entry_type == 'out'
        assert float(cash.amount) == 7500.0
        assert cash.entry_date == date(2026, 9, 20)
        assert 'Legacy' in cash.description and 'old expense' in cash.description

        # idempotent: re-run adds nothing
        assert backfill() == 0
        assert CashEntry.query.filter_by(linked_expense_id=legacy_id).count() == 1


def test_backfill_recalculates_running_balance(app, test_user):
    with app.app_context():
        shop_id = _shop_id(test_user)
        cat = ExpenseCategory(shop_id=shop_id, name='Legacy2', is_default=False)
        db.session.add(cat)
        db.session.flush()
        db.session.add(Expense(shop_id=shop_id, category_id=cat.id, amount=1000,
                               description='legacy2', expense_date=date(2026, 9, 21)))
        db.session.commit()

        backfill()

        cash = CashEntry.query.filter(
            CashEntry.linked_expense_id.isnot(None)
        ).first()
        assert cash is not None
        # opening capital 100000 − 1000 (opening must sort first in recalc)
        assert float(cash.balance_after) == 99000.0
        opening = CashEntry.query.filter_by(description=OPENING_CAPITAL_DESC).first()
        assert opening is not None
        assert float(opening.balance_after) == 100000.0
