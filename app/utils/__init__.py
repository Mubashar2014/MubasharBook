from datetime import date
from flask_login import current_user
from sqlalchemy import case, func
from app.models.shop import Shop
from app.models.cashbook import CashEntry
from app.extensions import db

OPENING_CAPITAL_DESC = 'Opening capital'


def get_user_shop():
    """Get or create shop for current user."""
    shop = Shop.query.filter_by(user_id=current_user.id).first()
    if not shop:
        shop = Shop(user_id=current_user.id, name=current_user.owner_name + "'s Shop")
        db.session.add(shop)
        db.session.commit()
    return shop


def recalc_cash_balances(shop_id):
    """Recompute running balance_after for all cash entries, including opening capital."""
    entries = CashEntry.query.filter_by(shop_id=shop_id).order_by(
        CashEntry.created_at.asc(), CashEntry.id.asc()
    ).all()
    # Opening capital must always be the first row in the running balance
    opening = [e for e in entries if e.description == OPENING_CAPITAL_DESC]
    others = [e for e in entries if e.description != OPENING_CAPITAL_DESC]
    ordered = opening + others
    balance = 0.0
    for e in ordered:
        amt = float(e.amount)
        balance = balance + amt if e.entry_type == 'in' else balance - amt
        e.balance_after = balance
    db.session.flush()
    return balance


def ensure_opening_cash(shop):
    """Create or sync the opening-capital cash entry so cash-in-hand starts at investment."""
    if shop is None:
        return 0.0

    amount = float(shop.initial_investment or 0)
    openings = CashEntry.query.filter_by(
        shop_id=shop.id, description=OPENING_CAPITAL_DESC
    ).order_by(CashEntry.id.asc()).all()

    # Merge accidental duplicates into a single opening row
    if len(openings) > 1:
        keep = openings[0]
        for dup in openings[1:]:
            db.session.delete(dup)
        openings = [keep]
        db.session.flush()

    if amount <= 0 and not openings:
        return 0.0

    if not openings:
        opening = CashEntry(
            shop_id=shop.id,
            entry_type='in',
            amount=amount,
            description=OPENING_CAPITAL_DESC,
            entry_date=shop.created_at.date() if shop.created_at else date.today(),
            balance_after=amount,
        )
        db.session.add(opening)
        db.session.flush()
    elif float(openings[0].amount) != amount:
        openings[0].amount = amount

    return recalc_cash_balances(shop.id)


def get_cash_balance(shop_id):
    """Current cash in hand = sum of all cash entries (opening capital is an entry)."""
    net = db.session.query(
        func.coalesce(
            func.sum(
                case(
                    (CashEntry.entry_type == 'in', CashEntry.amount),
                    else_=-CashEntry.amount,
                )
            ),
            0,
        )
    ).filter(CashEntry.shop_id == shop_id).scalar()
    return float(net or 0)


def format_currency(amount):
    """Format a number as Rs with comma separators."""
    if amount is None:
        return 'Rs 0'
    try:
        val = float(amount)
        return 'Rs {:,.0f}'.format(val)
    except (ValueError, TypeError):
        return 'Rs 0'