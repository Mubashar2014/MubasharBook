from datetime import date
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.expenses import expenses_bp
from app.expenses.forms import (
    ExpenseForm, ExpenseCategoryForm, LoanForm, LoanPaymentForm,
)
from app.models.expense import Expense, ExpenseCategory
from app.models.cashbook import CashEntry
from app.models.loan import Loan, LoanPayment
from app.extensions import db
from app.utils import (
    get_user_shop, ensure_opening_cash, recalc_cash_balances, wa_share_link,
)

DEFAULT_CATEGORIES = [
    'Rent',
    'Utilities',
    'Staff Salary',
    'Transport',
    'Tea & Misc',
]


def seed_categories(shop_id):
    existing = ExpenseCategory.query.filter_by(shop_id=shop_id).first()
    if existing:
        return
    for name in DEFAULT_CATEGORIES:
        db.session.add(ExpenseCategory(
            shop_id=shop_id, name=name, is_default=True
        ))
    db.session.commit()


def _kind_for_category(cat_name):
    """Map category name → expense kind. Rent/Salary rows carry a payee."""
    lowered = (cat_name or '').strip().lower()
    if lowered == 'rent':
        return 'rent'
    if lowered in ('staff salary', 'salary'):
        return 'salary'
    return 'general'


def _loan_receipt_text(shop_name, loan, payment):
    amt = f'Rs {float(payment.amount):,.0f}'
    remaining = f'Rs {loan.balance:,.0f}'
    if loan.direction == 'lent':
        return (
            f'{amt} received as loan installment from {loan.party_name}. '
            f'Remaining: {remaining}. — {shop_name}'
        )
    return (
        f'{amt} paid as loan installment to {loan.party_name}. '
        f'Remaining: {remaining}. — {shop_name}'
    )


def _loan_reminder_text(shop_name, loan):
    return (
        f'Assalam-o-Alaikum {loan.party_name}, a gentle reminder from {shop_name}: '
        f'Rs {loan.balance:,.0f} of your Rs {float(loan.principal):,.0f} loan is '
        f'still pending. Thank you!'
    )


def _expense_receipt_text(shop_name, expense):
    amt = f'Rs {float(expense.amount):,.0f}'
    who = f' to {expense.payee_name}' if expense.payee_name else ''
    kind = expense.kind or 'expense'
    label = {'rent': 'rent', 'salary': 'salary'}.get(kind, kind)
    return f'{amt} paid as {label}{who} on {expense.expense_date.strftime("%d %b %Y")}. — {shop_name}'


@expenses_bp.route('/')
@login_required
def list_expenses():
    shop = get_user_shop()
    seed_categories(shop.id)

    tab = request.args.get('tab', 'expenses')
    if tab not in ('expenses', 'rent', 'salary', 'loans'):
        tab = 'expenses'

    category_id = request.args.get('category_id', type=int)
    query = Expense.query.filter_by(shop_id=shop.id)
    if category_id:
        query = query.filter_by(category_id=category_id)

    expenses = query.order_by(Expense.expense_date.desc()).all()
    categories = ExpenseCategory.query.filter_by(shop_id=shop.id).order_by(
        ExpenseCategory.is_default.desc(), ExpenseCategory.name
    ).all()

    rent_rows = [e for e in expenses if e.kind == 'rent']
    salary_rows = [e for e in expenses if e.kind == 'salary']

    loans = Loan.query.filter_by(shop_id=shop.id).order_by(
        Loan.status.asc(), Loan.start_date.desc(), Loan.id.desc()
    ).all()
    loan_form = LoanForm()
    loan_form.start_date.data = loan_form.start_date.data or date.today()

    return render_template(
        'expenses/list.html',
        expenses=expenses,
        categories=categories,
        selected_category=category_id,
        tab=tab,
        today_iso=date.today().isoformat(),
        rent_rows=rent_rows,
        salary_rows=salary_rows,
        loans=loans,
        loan_form=loan_form,
        wa_share_link=wa_share_link,
        expense_receipt_text=_expense_receipt_text,
        loan_receipt_text=_loan_receipt_text,
        loan_reminder_text=_loan_reminder_text,
    )


@expenses_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    shop = get_user_shop()
    seed_categories(shop.id)

    form = ExpenseForm()
    categories = ExpenseCategory.query.filter_by(shop_id=shop.id).order_by(
        ExpenseCategory.is_default.desc(), ExpenseCategory.name
    ).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]

    if form.validate_on_submit():
        category = next((c for c in categories if c.id == form.category_id.data), None)
        kind = _kind_for_category(category.name if category else '')
        payee_name = (form.payee_name.data or '').strip()
        payee_phone = (form.payee_phone.data or '').strip()

        # Rent/salary rows exist to track a payee — require the name.
        if kind in ('rent', 'salary') and not payee_name:
            flash(f'Enter the payee name for {kind}.', 'danger')
            return render_template('expenses/form.html', form=form)

        expense = Expense(
            shop_id=shop.id,
            category_id=form.category_id.data,
            amount=form.amount.data,
            description=form.description.data or '',
            expense_date=form.expense_date.data,
            payee_name=payee_name or None,
            payee_phone=payee_phone or None,
            kind=kind,
        )
        db.session.add(expense)
        db.session.flush()

        # Mirror the expense into the cashbook so cash-in-hand reflects money spent.
        # Cash-basis formulas (dashboard/partners/investors) read cash_out only — no
        # separate "- expenses" subtraction there anymore, so this never double-counts.
        ensure_opening_cash(shop)
        category = next((c.name for c in categories if c.id == form.category_id.data), 'Expense')
        desc = f"Expense: {category}"
        if expense.description:
            desc = f"{desc} — {expense.description}"
        db.session.add(CashEntry(
            shop_id=shop.id,
            entry_type='out',
            amount=expense.amount,
            description=desc[:300],
            entry_date=expense.expense_date,
            linked_expense_id=expense.id,
        ))
        recalc_cash_balances(shop.id)
        db.session.commit()
        flash('Expense added.', 'success')
        return redirect(url_for('expenses.list_expenses'))

    return render_template('expenses/form.html', form=form)


@expenses_bp.route('/<int:expense_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    shop = get_user_shop()
    expense = Expense.query.filter_by(id=expense_id, shop_id=shop.id).first_or_404()
    seed_categories(shop.id)

    form = ExpenseForm(obj=expense)
    categories = ExpenseCategory.query.filter_by(shop_id=shop.id).order_by(
        ExpenseCategory.is_default.desc(), ExpenseCategory.name
    ).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]

    if form.validate_on_submit():
        category = next((c for c in categories if c.id == form.category_id.data), None)
        kind = _kind_for_category(category.name if category else '')
        payee_name = (form.payee_name.data or '').strip()
        payee_phone = (form.payee_phone.data or '').strip()
        if kind in ('rent', 'salary') and not payee_name:
            flash(f'Enter the payee name for {kind}.', 'danger')
            return render_template('expenses/form.html', form=form, expense=expense)

        expense.category_id = form.category_id.data
        expense.amount = form.amount.data
        expense.description = form.description.data or ''
        expense.expense_date = form.expense_date.data
        expense.payee_name = payee_name or None
        expense.payee_phone = payee_phone or None
        expense.kind = kind

        # Keep the mirrored cashbook entry in sync (same recipe as add_expense).
        cash = CashEntry.query.filter_by(linked_expense_id=expense.id).first()
        if cash:
            category = next((c.name for c in categories if c.id == form.category_id.data), 'Expense')
            desc = f"Expense: {category}"
            if expense.description:
                desc = f"{desc} — {expense.description}"
            cash.amount = expense.amount
            cash.entry_date = expense.expense_date
            cash.description = desc[:300]
            recalc_cash_balances(shop.id)
        db.session.commit()
        flash('Expense updated.', 'success')
        return redirect(url_for('expenses.list_expenses'))

    return render_template('expenses/form.html', form=form, expense=expense)


@expenses_bp.route('/<int:expense_id>/delete', methods=['POST'])
@login_required
def delete_expense(expense_id):
    shop = get_user_shop()
    expense = Expense.query.filter_by(id=expense_id, shop_id=shop.id).first_or_404()

    # Remove the mirrored cashbook entry first so cash-in-hand recalculates.
    cash = CashEntry.query.filter_by(linked_expense_id=expense.id).first()
    if cash:
        db.session.delete(cash)
    db.session.delete(expense)
    db.session.flush()
    recalc_cash_balances(shop.id)
    db.session.commit()
    flash('Expense deleted.', 'success')
    return redirect(url_for('expenses.list_expenses'))


@expenses_bp.route('/categories')
@login_required
def list_categories():
    shop = get_user_shop()
    seed_categories(shop.id)

    categories = ExpenseCategory.query.filter_by(shop_id=shop.id).order_by(
        ExpenseCategory.is_default.desc(), ExpenseCategory.name
    ).all()
    form = ExpenseCategoryForm()
    return render_template('expenses/categories.html', categories=categories, form=form)


@expenses_bp.route('/categories/add', methods=['POST'])
@login_required
def add_category():
    shop = get_user_shop()
    form = ExpenseCategoryForm()

    if form.validate_on_submit():
        existing = ExpenseCategory.query.filter_by(
            shop_id=shop.id, name=form.name.data.strip()
        ).first()
        if existing:
            flash('Category already exists.', 'warning')
        else:
            cat = ExpenseCategory(
                shop_id=shop.id,
                name=form.name.data.strip(),
                is_default=False
            )
            db.session.add(cat)
            db.session.commit()
            flash('Category added.', 'success')

    return redirect(url_for('expenses.list_categories'))


@expenses_bp.route('/categories/<int:cat_id>/delete', methods=['POST'])
@login_required
def delete_category(cat_id):
    shop = get_user_shop()
    cat = ExpenseCategory.query.filter_by(id=cat_id, shop_id=shop.id).first_or_404()

    if cat.is_default:
        flash('Cannot delete default categories.', 'warning')
        return redirect(url_for('expenses.list_categories'))

    has_expenses = Expense.query.filter_by(category_id=cat.id).first()
    if has_expenses:
        flash('Cannot delete category — it has expense records.', 'warning')
        return redirect(url_for('expenses.list_categories'))

    db.session.delete(cat)
    db.session.commit()
    flash('Category deleted.', 'success')
    return redirect(url_for('expenses.list_categories'))


# ── Loans (installments — cashbook only, never in P&L) ──────────────────────

@expenses_bp.route('/loans/add', methods=['POST'])
@login_required
def add_loan():
    shop = get_user_shop()
    form = LoanForm()

    if form.validate_on_submit():
        loan = Loan(
            shop_id=shop.id,
            direction=form.direction.data,
            party_name=form.party_name.data.strip(),
            party_phone=(form.party_phone.data or '').strip() or None,
            principal=form.principal.data,
            start_date=form.start_date.data,
            notes=(form.notes.data or '').strip() or None,
        )
        db.session.add(loan)
        db.session.commit()
        flash(f'Loan added — Rs {float(loan.principal):,.0f} {loan.direction} {loan.party_name}.', 'success')
    else:
        flash('Could not add loan — check the form fields.', 'danger')

    return redirect(url_for('expenses.list_expenses', tab='loans'))


@expenses_bp.route('/loans/<int:loan_id>/payments', methods=['POST'])
@login_required
def record_loan_payment(loan_id):
    shop = get_user_shop()
    loan = Loan.query.filter_by(id=loan_id, shop_id=shop.id).first_or_404()

    if loan.status == 'closed':
        flash('This loan is already fully paid.', 'warning')
        return redirect(url_for('expenses.list_expenses', tab='loans'))

    form = LoanPaymentForm()
    if not form.validate_on_submit():
        flash('Enter a valid installment amount and date.', 'danger')
        return redirect(url_for('expenses.list_expenses', tab='loans'))

    amount = round(float(form.amount.data), 2)
    if amount <= 0:
        flash('Enter an amount greater than 0.', 'danger')
        return redirect(url_for('expenses.list_expenses', tab='loans'))
    if amount > loan.balance + 0.005:
        flash(f'Amount cannot exceed the remaining Rs {loan.balance:,.0f}.', 'danger')
        return redirect(url_for('expenses.list_expenses', tab='loans'))

    payment = LoanPayment(
        loan_id=loan.id,
        amount=amount,
        paid_date=form.paid_date.data,
        notes=(form.notes.data or '').strip() or None,
    )
    db.session.add(payment)
    db.session.flush()

    # Cashbook mirror only — loans are liability/asset movements, not P&L costs.
    ensure_opening_cash(shop)
    if loan.direction == 'borrowed':
        cash_type = 'out'
        desc = f"Loan installment paid to {loan.party_name}"
    else:
        cash_type = 'in'
        desc = f"Loan installment received from {loan.party_name}"
    cash = CashEntry(
        shop_id=shop.id,
        entry_type=cash_type,
        amount=amount,
        description=desc[:300],
        entry_date=form.paid_date.data,
    )
    db.session.add(cash)
    db.session.flush()
    payment.cash_entry_id = cash.id
    recalc_cash_balances(shop.id)

    # Refresh so the loan.payments collection reflects the row we just added.
    db.session.refresh(loan)
    if loan.balance <= 0.005:
        loan.status = 'closed'
        flash(f'Final installment recorded — loan with {loan.party_name} is fully paid.', 'success')
    else:
        flash(f'Installment of Rs {amount:,.0f} recorded — Rs {loan.balance:,.0f} remaining.', 'success')

    db.session.commit()
    return redirect(url_for('expenses.list_expenses', tab='loans'))


@expenses_bp.route('/loans/<int:loan_id>/delete', methods=['POST'])
@login_required
def delete_loan(loan_id):
    shop = get_user_shop()
    loan = Loan.query.filter_by(id=loan_id, shop_id=shop.id).first_or_404()

    if loan.payments:
        flash('Cannot delete — this loan has installment records. Delete them first.', 'warning')
        return redirect(url_for('expenses.list_expenses', tab='loans'))

    db.session.delete(loan)
    db.session.commit()
    flash('Loan deleted.', 'success')
    return redirect(url_for('expenses.list_expenses', tab='loans'))


@expenses_bp.route('/loans/payments/<int:payment_id>/delete', methods=['POST'])
@login_required
def delete_loan_payment(payment_id):
    shop = get_user_shop()
    payment = LoanPayment.query.join(Loan).filter(
        LoanPayment.id == payment_id, Loan.shop_id == shop.id
    ).first_or_404()
    loan = payment.loan

    cash = db.session.get(CashEntry, payment.cash_entry_id) if payment.cash_entry_id else None
    if cash:
        db.session.delete(cash)
    db.session.delete(payment)

    if loan.balance > 0.005 and loan.status == 'closed':
        loan.status = 'active'
    db.session.flush()
    recalc_cash_balances(shop.id)
    db.session.commit()
    flash('Installment deleted — loan balance restored.', 'success')
    return redirect(url_for('expenses.list_expenses', tab='loans'))
