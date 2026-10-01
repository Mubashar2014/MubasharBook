import re
from datetime import date
from urllib.parse import quote
from flask_login import current_user
from sqlalchemy import case, func
from app.models.shop import Shop
from app.models.cashbook import CashEntry
from app.models.user import User
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


def apply_profile_update(user, owner_name, phone, language):
    """Validate and save profile edits.

    Shared by /settings/profile and the admin account page.
    Returns an error message to flash, or None on success.
    """
    owner_name = (owner_name or '').strip()
    if not owner_name:
        return 'Owner name cannot be empty.'

    phone = (phone or '').strip()
    if len(phone) > 20:
        return 'Phone number is too long (max 20 characters).'
    if phone and User.query.filter(User.phone == phone, User.id != user.id).first():
        return 'This phone number is already registered to another account.'
    if not phone and user.phone:
        return 'Phone number cannot be empty.'

    user.owner_name = owner_name
    user.phone = phone
    user.language = language if language in ('en', 'ur') else (user.language or 'en')
    db.session.commit()
    return None


def apply_password_change(user, current_password, new_password):
    """Verify the current password then set the new one.

    Shared by /settings/password and the admin account page.
    Returns an error message to flash, or None on success.
    """
    if not user.check_password(current_password or ''):
        return 'Current password is incorrect.'

    new_password = new_password or ''
    if len(new_password) < 8:
        return 'New password must be at least 8 characters.'

    user.set_password(new_password)
    user.clear_reset_token()
    db.session.commit()
    return None


def format_currency(amount):
    """Format a number as Rs with comma separators."""
    if amount is None:
        return 'Rs 0'
    try:
        val = float(amount)
        return 'Rs {:,.0f}'.format(val)
    except (ValueError, TypeError):
        return 'Rs 0'

def normalise_whatsapp(raw):
    """Digits-only form of a phone/WhatsApp number ('' when blank)."""
    return re.sub(r'\D', '', raw or '')


def validate_whatsapp(raw):
    """Error message for a bad WhatsApp number, or None when blank/valid."""
    if not (raw or '').strip():
        return None
    if not 7 <= len(normalise_whatsapp(raw)) <= 15:
        return 'Enter a valid WhatsApp number (7-15 digits), e.g. 0300 1234567.'
    return None


def wa_me_link(number, text=''):
    """Build a wa.me deep link, turning a local PK number into international."""
    digits = normalise_whatsapp(number)
    if not digits:
        return None
    if digits.startswith('92') and len(digits) >= 11:
        intl = digits
    elif digits.startswith('0'):
        intl = '92' + digits[1:]
    elif len(digits) <= 9:
        intl = '92' + digits
    else:
        intl = digits
    link = f'https://wa.me/{intl}'
    if text:
        link += '?text=' + quote(text)
    return link


def party_whatsapp_map(shop_id):
    """{party_name: last WhatsApp number used} for prefilling stock forms."""
    from app.models.stock import StockItem

    rows = StockItem.query.filter(StockItem.shop_id == shop_id).order_by(StockItem.id.desc()).all()
    known = {}
    for row in rows:
        if row.supplier_name and row.purchase_whatsapp and row.supplier_name not in known:
            known[row.supplier_name] = row.purchase_whatsapp
        if row.customer_name and row.sale_whatsapp and row.customer_name not in known:
            known[row.customer_name] = row.sale_whatsapp
    return known


def wa_share_link(number, text=''):
    """wa.me link; falls back to WhatsApp's contact picker when number unknown."""
    link = wa_me_link(number, text)
    if link:
        return link
    return 'https://wa.me/?text=' + quote(text)


def reminder_text(shop_name, party_name, amount, direction):
    """Message used by the 'send reminder' WhatsApp button on khata pages."""
    amt = f'Rs {float(amount):,.0f}'
    if direction == 'receivable':
        return (
            f'Assalam-o-Alaikum {party_name}, a gentle reminder from {shop_name}: '
            f'{amt} is pending on your account. Thank you!'
        )
    return (
        f'Assalam-o-Alaikum {party_name}, from {shop_name}: '
        f'{amt} is pending on our side and will be cleared soon. JazakAllah.'
    )
