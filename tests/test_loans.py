from datetime import date
from app.models.expense import Expense
from app.models.cashbook import CashEntry
from app.models.loan import Loan, LoanPayment
from app.models.shop import Shop
from app.reports.routes import compute_pnl_totals


def _add_loan(client, direction='borrowed', party='Haji Sahab', principal=200000,
              phone='03001234567', start='2026-01-01', notes=''):
    return client.post('/expenses/loans/add', data={
        'direction': direction,
        'party_name': party,
        'party_phone': phone,
        'principal': principal,
        'start_date': start,
        'notes': notes,
    }, follow_redirects=False)


def _pay(client, loan_id, amount, paid='2026-02-01', notes=''):
    return client.post(f'/expenses/loans/{loan_id}/payments', data={
        'amount': amount,
        'paid_date': paid,
        'notes': notes,
    }, follow_redirects=False)


# ── Loan creation ──────────────────────────────────────────────────────────

def test_add_borrowed_loan(logged_in_client, app):
    resp = _add_loan(logged_in_client)
    assert resp.status_code == 302

    with app.app_context():
        loan = Loan.query.first()
        assert loan is not None
        assert loan.direction == 'borrowed'
        assert loan.party_name == 'Haji Sahab'
        assert float(loan.principal) == 200000.0
        assert loan.status == 'active'


def test_add_lent_loan(logged_in_client, app):
    _add_loan(logged_in_client, direction='lent', party='Rehman', principal=50000)

    with app.app_context():
        loan = Loan.query.first()
        assert loan.direction == 'lent'
        assert loan.balance == 50000.0


def test_loan_rejects_zero_principal(logged_in_client, app):
    _add_loan(logged_in_client, principal=0)
    with app.app_context():
        assert Loan.query.count() == 0


def test_loan_requires_party_name(logged_in_client, app):
    _add_loan(logged_in_client, party='   ')
    with app.app_context():
        assert Loan.query.count() == 0


# ── Installments ───────────────────────────────────────────────────────────

def test_borrowed_installment_creates_cash_out(logged_in_client, app):
    _add_loan(logged_in_client)
    with app.app_context():
        loan_id = Loan.query.first().id

    resp = _pay(logged_in_client, loan_id, 50000)
    assert resp.status_code == 302

    with app.app_context():
        loan = Loan.query.get(loan_id)
        assert loan.balance == 150000.0
        assert loan.status == 'active'
        cash = CashEntry.query.filter(
            CashEntry.description.like('Loan installment paid to%')
        ).first()
        assert cash is not None
        assert cash.entry_type == 'out'
        assert float(cash.amount) == 50000.0
        payment = LoanPayment.query.first()
        assert payment.cash_entry_id == cash.id


def test_lent_installment_creates_cash_in(logged_in_client, app):
    _add_loan(logged_in_client, direction='lent', party='Rehman', principal=50000)
    with app.app_context():
        loan_id = Loan.query.first().id

    _pay(logged_in_client, loan_id, 20000)

    with app.app_context():
        cash = CashEntry.query.filter(
            CashEntry.description.like('Loan installment received from%')
        ).first()
        assert cash.entry_type == 'in'
        assert float(cash.amount) == 20000.0


def test_final_installment_closes_loan(logged_in_client, app):
    _add_loan(logged_in_client, principal=100000)
    with app.app_context():
        loan_id = Loan.query.first().id

    _pay(logged_in_client, loan_id, 100000)

    with app.app_context():
        loan = Loan.query.get(loan_id)
        assert loan.status == 'closed'
        assert loan.balance == 0.0


def test_installment_rejects_overpayment(logged_in_client, app):
    _add_loan(logged_in_client, principal=50000)
    with app.app_context():
        loan_id = Loan.query.first().id

    _pay(logged_in_client, loan_id, 60000)

    with app.app_context():
        loan = Loan.query.get(loan_id)
        assert loan.balance == 50000.0
        assert LoanPayment.query.count() == 0


def test_installment_rejects_zero_and_negative(logged_in_client, app):
    _add_loan(logged_in_client, principal=50000)
    with app.app_context():
        loan_id = Loan.query.first().id

    _pay(logged_in_client, loan_id, 0)
    _pay(logged_in_client, loan_id, -100)

    with app.app_context():
        assert LoanPayment.query.count() == 0


def test_closed_loan_rejects_further_payments(logged_in_client, app):
    _add_loan(logged_in_client, principal=50000)
    with app.app_context():
        loan_id = Loan.query.first().id

    _pay(logged_in_client, loan_id, 50000)
    _pay(logged_in_client, loan_id, 1000)

    with app.app_context():
        assert LoanPayment.query.count() == 1
        loan = Loan.query.get(loan_id)
        assert loan.status == 'closed'


# ── Delete flows ───────────────────────────────────────────────────────────

def test_delete_loan_with_payments_blocked(logged_in_client, app):
    _add_loan(logged_in_client)
    with app.app_context():
        loan_id = Loan.query.first().id
    _pay(logged_in_client, loan_id, 10000)

    resp = logged_in_client.post(f'/expenses/loans/{loan_id}/delete', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert Loan.query.count() == 1


def test_delete_empty_loan_allowed(logged_in_client, app):
    _add_loan(logged_in_client)
    with app.app_context():
        loan_id = Loan.query.first().id

    logged_in_client.post(f'/expenses/loans/{loan_id}/delete', follow_redirects=False)
    with app.app_context():
        assert Loan.query.count() == 0


def test_delete_payment_restores_balance_and_cash(logged_in_client, app):
    _add_loan(logged_in_client, principal=50000)
    with app.app_context():
        loan_id = Loan.query.first().id
    _pay(logged_in_client, loan_id, 20000)
    with app.app_context():
        payment_id = LoanPayment.query.first().id

    logged_in_client.post(f'/expenses/loans/payments/{payment_id}/delete', follow_redirects=False)

    with app.app_context():
        assert LoanPayment.query.count() == 0
        loan = Loan.query.get(loan_id)
        assert loan.balance == 50000.0
        assert CashEntry.query.filter(
            CashEntry.description.like('Loan installment%')
        ).count() == 0


def test_delete_final_payment_reopens_loan(logged_in_client, app):
    _add_loan(logged_in_client, principal=50000)
    with app.app_context():
        loan_id = Loan.query.first().id
    _pay(logged_in_client, loan_id, 50000)
    with app.app_context():
        assert Loan.query.get(loan_id).status == 'closed'
        payment_id = LoanPayment.query.first().id

    logged_in_client.post(f'/expenses/loans/payments/{payment_id}/delete', follow_redirects=False)
    with app.app_context():
        loan = Loan.query.get(loan_id)
        assert loan.status == 'active'
        assert loan.balance == 50000.0


# ── P&L exclusion ──────────────────────────────────────────────────────────

def test_loan_payments_never_touch_expenses_or_pnl(logged_in_client, app):
    _add_loan(logged_in_client, principal=100000)
    with app.app_context():
        loan_id = Loan.query.first().id
    _pay(logged_in_client, loan_id, 60000)

    with app.app_context():
        # No expense rows created by loans
        assert Expense.query.count() == 0
        # P&L expense total is zero despite 60k having left the cashbook
        shop = Shop.query.first()
        totals = compute_pnl_totals(shop, date(2026, 1, 1), date(2026, 12, 31))
        assert totals['expenses'] == 0.0


# ── Rent / salary payee + receipts ─────────────────────────────────────────

def _add_rent_expense(client, cat_id, amount=30000, payee='Landlord Khan', phone='03001234567'):
    return client.post('/expenses/add', data={
        'category_id': cat_id,
        'amount': amount,
        'description': 'Monthly shop rent',
        'expense_date': '2026-03-01',
        'payee_name': payee,
        'payee_phone': phone,
    }, follow_redirects=False)


def test_rent_expense_saves_payee_and_kind(logged_in_client, app):
    logged_in_client.get('/expenses/')
    with app.app_context():
        from app.models.expense import ExpenseCategory
        cat = ExpenseCategory.query.filter_by(name='Rent').first()
        cat_id = cat.id

    resp = _add_rent_expense(logged_in_client, cat_id)
    assert resp.status_code == 302

    with app.app_context():
        e = Expense.query.first()
        assert e.kind == 'rent'
        assert e.payee_name == 'Landlord Khan'
        assert e.payee_phone == '03001234567'


def test_rent_requires_payee_name(logged_in_client, app):
    logged_in_client.get('/expenses/')
    with app.app_context():
        from app.models.expense import ExpenseCategory
        cat_id = ExpenseCategory.query.filter_by(name='Rent').first().id

    _add_rent_expense(logged_in_client, cat_id, payee='')
    with app.app_context():
        assert Expense.query.count() == 0


def test_salary_category_maps_to_salary_kind(logged_in_client, app):
    logged_in_client.get('/expenses/')
    with app.app_context():
        from app.models.expense import ExpenseCategory
        cat_id = ExpenseCategory.query.filter_by(name='Staff Salary').first().id

    _add_rent_expense(logged_in_client, cat_id, amount=25000, payee='Ali Khan')

    with app.app_context():
        e = Expense.query.first()
        assert e.kind == 'salary'
        assert e.payee_name == 'Ali Khan'


def test_general_category_keeps_kind_general(logged_in_client, app):
    logged_in_client.get('/expenses/')
    with app.app_context():
        from app.models.expense import ExpenseCategory
        cat_id = ExpenseCategory.query.filter_by(name='Utilities').first().id

    client_resp = logged_in_client.post('/expenses/add', data={
        'category_id': cat_id,
        'amount': 5000,
        'description': 'Electricity',
        'expense_date': '2026-03-01',
    }, follow_redirects=False)
    assert client_resp.status_code == 302

    with app.app_context():
        assert Expense.query.first().kind == 'general'


# ── Tabs & WhatsApp links on page ──────────────────────────────────────────

def test_expenses_page_has_four_tabs(logged_in_client):
    resp = logged_in_client.get('/expenses/')
    html = resp.get_data(as_text=True)
    for tab in ('Expenses', 'Rent', 'Salary', 'Loans'):
        assert tab in html


def test_loans_tab_shows_add_form_and_reminder_link(logged_in_client, app):
    _add_loan(logged_in_client, direction='lent', party='Rehman', principal=50000,
              phone='03001234567')
    with app.app_context():
        loan_id = Loan.query.first().id
    _pay(logged_in_client, loan_id, 10000)

    resp = logged_in_client.get('/expenses/?tab=loans')
    html = resp.get_data(as_text=True)
    assert 'Rehman' in html
    assert 'wa.me/923001234567' in html
    assert 'loan' in html.lower()


def test_rent_tab_shows_payee_and_receipt_link(logged_in_client, app):
    logged_in_client.get('/expenses/')
    with app.app_context():
        from app.models.expense import ExpenseCategory
        cat_id = ExpenseCategory.query.filter_by(name='Rent').first().id
    _add_rent_expense(logged_in_client, cat_id)

    resp = logged_in_client.get('/expenses/?tab=rent')
    html = resp.get_data(as_text=True)
    assert 'Landlord Khan' in html
    assert 'wa.me/923001234567' in html
    assert 'Send receipt' in html


def test_loans_multitenancy(logged_in_client, second_user, app):
    _add_loan(logged_in_client, party='My Loan Party', principal=99000)

    with app.app_context():
        second_client = app.test_client()
        with second_client.session_transaction() as sess:
            sess['_user_id'] = str(second_user.id)

        resp = second_client.get('/expenses/?tab=loans')
        html = resp.get_data(as_text=True)
        assert 'My Loan Party' not in html
