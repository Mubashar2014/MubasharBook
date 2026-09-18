from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.expenses import expenses_bp
from app.expenses.forms import ExpenseForm, ExpenseCategoryForm
from app.models.expense import Expense, ExpenseCategory
from app.extensions import db
from app.utils import get_user_shop

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
        db.session.commit()
        flash('Expense added.', 'success')
        return redirect(url_for('expenses.list_expenses'))

    return render_template('expenses/form.html', form=form)


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
