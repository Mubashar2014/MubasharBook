from datetime import datetime
from app.extensions import db


class CashEntry(db.Model):
    """Cashbook entry — cash in or cash out."""
    __tablename__ = 'cash_entries'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    entry_type = db.Column(db.String(10), nullable=False)  # 'in' or 'out'
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    linked_stock_id = db.Column(db.Integer, nullable=True)  # plain ID, no FK to avoid cycles
    balance_after = db.Column(db.Numeric(12, 2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
