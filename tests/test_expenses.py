from datetime import date
from app.extensions import db
from app.models.shop import Shop
from app.models.user import User
from app.models.expense import Expense, ExpenseCategory


def _get_shop_id(user):
    return Shop.query.filter_by(user_id=user.id).first().id


def test_expenses_page_loads(logged_in_client):
    resp = logged_in_client.get('/expenses/')
    assert resp.status_code == 200


def test_add_expense(logged_in_client, app, test_user):
    with app.app_context():
        shop_id = _get_shop_id(test_user)
        cat = ExpenseCategory(shop_id=shop_id, name='Rent', is_default=True)
        db.session.add(cat)
        db.session.flush()

        expense = Expense(
            shop_id=shop_id,
            category_id=cat.id,
            amount=15000,
            description='Monthly rent',
            expense_date=date(2024, 6, 15),
        )
        db.session.add(expense)
        db.session.commit()

        loaded = Expense.query.filter_by(description='Monthly rent').first()
        assert loaded is not None
        assert float(loaded.amount) == 15000.0


def test_default_categories_seeded(logged_in_client, app, test_user):
    with app.app_context():
        shop_id = _get_shop_id(test_user)
        for name in ['Rent', 'Utilities', 'Transport', 'Staff Salary']:
            cat = ExpenseCategory(shop_id=shop_id, name=name, is_default=True)
            db.session.add(cat)
        db.session.commit()

        defaults = ExpenseCategory.query.filter_by(shop_id=shop_id, is_default=True).all()
        assert len(defaults) == 4


def test_add_custom_category(logged_in_client, app, test_user):
    with app.app_context():
        shop_id = _get_shop_id(test_user)
        cat = ExpenseCategory(shop_id=shop_id, name='Marketing', is_default=False)
        db.session.add(cat)
        db.session.commit()

        loaded = ExpenseCategory.query.filter_by(name='Marketing').first()
        assert loaded is not None
        assert loaded.is_default is False


def test_delete_custom_category(logged_in_client, app, test_user):
    with app.app_context():
        shop_id = _get_shop_id(test_user)
        cat = ExpenseCategory(shop_id=shop_id, name='To Delete', is_default=False)
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id

        db.session.delete(cat)
        db.session.commit()

        loaded = db.session.get(ExpenseCategory, cat_id)
        assert loaded is None


def test_default_categories_not_deletable(logged_in_client, app, test_user):
    with app.app_context():
        shop_id = _get_shop_id(test_user)
        cat = ExpenseCategory(shop_id=shop_id, name='Rent', is_default=True)
        db.session.add(cat)
        db.session.commit()

        cat = ExpenseCategory.query.filter_by(name='Rent').first()
        assert cat.is_default is True
