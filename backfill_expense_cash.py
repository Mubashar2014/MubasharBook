#!/usr/bin/env python
"""
Create the missing cashbook cash-out row for expenses added before expenses
were mirrored into the cashbook. Idempotent — safe to re-run; already-paired
expenses are skipped.

Run:  bahi/venv/bin/python backfill_expense_cash.py
"""
from app import create_app
from app.extensions import db
from app.models.expense import Expense
from app.models.cashbook import CashEntry
from app.models.shop import Shop
from app.utils import ensure_opening_cash, recalc_cash_balances


def backfill():
    """Pair every unpaired expense with a cash-out row. Returns count created."""
    paired_ids = {r[0] for r in db.session.query(CashEntry.linked_expense_id).filter(
        CashEntry.linked_expense_id.isnot(None)
    ).all()}
    missing = [e for e in Expense.query.all() if e.id not in paired_ids]

    shops_touched = set()
    for expense in missing:
        category_name = expense.category.name if expense.category else 'Expense'
        desc = f"Expense: {category_name}"
        if expense.description:
            desc = f"{desc} — {expense.description}"
        db.session.add(CashEntry(
            shop_id=expense.shop_id,
            entry_type='out',
            amount=expense.amount,
            description=desc[:300],
            entry_date=expense.expense_date,
            linked_expense_id=expense.id,
        ))
        shops_touched.add(expense.shop_id)

    db.session.flush()

    for shop_id in shops_touched:
        shop = db.session.get(Shop, shop_id)
        if shop is None:
            continue
        ensure_opening_cash(shop)
        recalc_cash_balances(shop_id)

    db.session.commit()
    return len(missing)


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        total = Expense.query.count()
        created = backfill()
        print(f"Expenses: {total} | backfilled: {created}")
        print("✓ Nothing to do — all expenses already paired" if not created
              else f"✓ Created {created} expense cash entries")
