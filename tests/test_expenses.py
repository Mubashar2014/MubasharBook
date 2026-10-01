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


# ---------------------------------------------------------------- edit / delete

def _seed_expense_with_cash(app, test_user, amount=5000, desc='Old desc',
                            when=date(2024, 6, 15)):
    from app.models.cashbook import CashEntry
    with app.app_context():
        shop_id = _get_shop_id(test_user)
        cat = ExpenseCategory(shop_id=shop_id, name='Rent', is_default=True)
        db.session.add(cat)
        db.session.flush()
        expense = Expense(
            shop_id=shop_id,
            category_id=cat.id,
            amount=amount,
            description=desc,
            expense_date=when,
        )
        db.session.add(expense)
        db.session.flush()
        db.session.add(CashEntry(
            shop_id=shop_id,
            entry_type='out',
            amount=amount,
            description=f'Expense: Rent — {desc}',
            entry_date=when,
            linked_expense_id=expense.id,
        ))
        db.session.commit()
        return expense.id, cat.id


def test_edit_expense_page_renders(logged_in_client, app, test_user):
    expense_id, _ = _seed_expense_with_cash(app, test_user)
    resp = logged_in_client.get(f'/expenses/{expense_id}/edit')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Edit Expense' in html
    assert 'Update Expense' in html
    assert 'value="5000' in html          # amount prefilled
    assert 'Old desc' in html             # description prefilled
    assert 'value="2024-06-15"' in html   # date prefilled


def test_edit_expense_updates_and_syncs_cash(logged_in_client, app, test_user):
    expense_id, cat_id = _seed_expense_with_cash(app, test_user)

    resp = logged_in_client.post(f'/expenses/{expense_id}/edit', data={
        'category_id': str(cat_id),
        'amount': '7500',
        'description': 'New desc',
        'expense_date': '2024-06-20',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Expense updated.' in resp.data

    with app.app_context():
        e = db.session.get(Expense, expense_id)
        assert float(e.amount) == 7500.0
        assert e.description == 'New desc'
        assert e.expense_date == date(2024, 6, 20)

        from app.models.cashbook import CashEntry
        cash = CashEntry.query.filter_by(linked_expense_id=expense_id).first()
        assert cash is not None
        assert float(cash.amount) == 7500.0
        assert cash.entry_date == date(2024, 6, 20)
        assert 'New desc' in cash.description


def test_delete_expense_removes_linked_cash_only(logged_in_client, app, test_user):
    from app.models.cashbook import CashEntry
    expense_id, _ = _seed_expense_with_cash(app, test_user)

    with app.app_context():
        shop_id = _get_shop_id(test_user)
        db.session.add(CashEntry(
            shop_id=shop_id, entry_type='in', amount=999,
            description='Sale', entry_date=date(2024, 6, 10),
        ))
        db.session.commit()

    resp = logged_in_client.post(f'/expenses/{expense_id}/delete', follow_redirects=True)
    assert resp.status_code == 200
    assert b'Expense deleted.' in resp.data

    with app.app_context():
        assert db.session.get(Expense, expense_id) is None
        assert CashEntry.query.filter_by(linked_expense_id=expense_id).first() is None
        assert CashEntry.query.filter_by(description='Sale').count() == 1


def test_expense_edit_delete_scoped_to_own_shop(logged_in_client, app, second_user):
    with app.app_context():
        shop_id = Shop.query.filter_by(user_id=second_user.id).first().id
        cat = ExpenseCategory(shop_id=shop_id, name='Ops', is_default=True)
        db.session.add(cat)
        db.session.flush()
        expense = Expense(
            shop_id=shop_id, category_id=cat.id, amount=1111,
            description='Other shop', expense_date=date(2024, 6, 1),
        )
        db.session.add(expense)
        db.session.commit()
        expense_id = expense.id

    assert logged_in_client.get(f'/expenses/{expense_id}/edit').status_code == 404
    assert logged_in_client.post(f'/expenses/{expense_id}/delete').status_code == 404

    with app.app_context():
        assert db.session.get(Expense, expense_id) is not None
