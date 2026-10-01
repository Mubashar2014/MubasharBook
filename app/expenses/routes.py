from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.expenses import expenses_bp
from app.expenses.forms import ExpenseForm, ExpenseCategoryForm
from app.models.expense import Expense, ExpenseCategory
from app.models.cashbook import CashEntry
from app.extensions import db
from app.utils import get_user_shop, ensure_opening_cash, recalc_cash_balances

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


@expenses_bp.route('/')
@login_required
def list_expenses():
    shop = get_user_shop()
    seed_categories(shop.id)

    category_id = request.args.get('category_id', type=int)
    query = Expense.query.filter_by(shop_id=shop.id)
    if category_id:
        query = query.filter_by(category_id=category_id)

    expenses = query.order_by(Expense.expense_date.desc()).all()
    categories = ExpenseCategory.query.filter_by(shop_id=shop.id).order_by(
        ExpenseCategory.is_default.desc(), ExpenseCategory.name
    ).all()
    return render_template('expenses/list.html', expenses=expenses,
                           categories=categories, selected_category=category_id)


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
        expense = Expense(
            shop_id=shop.id,
            category_id=form.category_id.data,
            amount=form.amount.data,
            description=form.description.data or '',
            expense_date=form.expense_date.data
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
        expense.category_id = form.category_id.data
        expense.amount = form.amount.data
        expense.description = form.description.data or ''
        expense.expense_date = form.expense_date.data

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
