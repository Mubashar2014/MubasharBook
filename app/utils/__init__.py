from flask_login import current_user
from app.models.shop import Shop
from app.extensions import db


def get_user_shop():
    """Get or create shop for current user."""
    shop = Shop.query.filter_by(user_id=current_user.id).first()
    if not shop:
        shop = Shop(user_id=current_user.id, name=current_user.owner_name + "'s Shop")
        db.session.add(shop)
        db.session.commit()
    return shop


def format_currency(amount):
    """Format a number as Rs with comma separators."""
    if amount is None:
        return 'Rs 0'
    try:
        val = float(amount)
        return 'Rs {:,.0f}'.format(val)
    except (ValueError, TypeError):
        return 'Rs 0'