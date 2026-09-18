from datetime import datetime
from app.extensions import db


class KhataEntry(db.Model):
    """Khata — pending amounts with parties (supplier/customer)."""
    __tablename__ = 'khata_entries'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)

    party_name = db.Column(db.String(200), nullable=False)
    entry_type = db.Column(db.String(10), nullable=False)  # 'receivable' or 'payable'
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    entry_date = db.Column(db.Date, nullable=False)

    linked_stock_id = db.Column(db.Integer, nullable=True)  # plain ID, no FK

    status = db.Column(db.String(10), default='pending')
    settled_amount = db.Column(db.Numeric(12, 2), default=0)
    settled_date = db.Column(db.Date, nullable=True)
    settled_cash_entry_id = db.Column(db.Integer, nullable=True)  # plain ID, no FK

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
