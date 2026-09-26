from datetime import datetime
from app.extensions import db


class StockItem(db.Model):
    """Phone stock item — tracks purchase AND sale with payment + expenses."""
    __tablename__ = 'stock_items'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)

    # Phone details
    model_name = db.Column(db.String(200), nullable=False)
    imei = db.Column(db.String(20), nullable=True)
    quantity = db.Column(db.Integer, default=1)

    # Purchase (stock in)
    cost_price = db.Column(db.Numeric(12, 2), nullable=False)
    supplier_name = db.Column(db.String(200), nullable=True)
    purchase_date = db.Column(db.Date, nullable=False)
    purchase_paid = db.Column(db.Numeric(12, 2), default=0)
    purchase_pending = db.Column(db.Numeric(12, 2), default=0)
    purchase_expense_desc = db.Column(db.String(300), nullable=True)
    purchase_expense_amount = db.Column(db.Numeric(12, 2), default=0)

    # Sale (stock out)
    status = db.Column(db.String(10), default='in_stock')
    sale_price = db.Column(db.Numeric(12, 2), nullable=True)
    customer_name = db.Column(db.String(200), nullable=True)
    sale_date = db.Column(db.Date, nullable=True)
    sale_received = db.Column(db.Numeric(12, 2), default=0)
    sale_pending = db.Column(db.Numeric(12, 2), default=0)
    sale_expense_desc = db.Column(db.String(300), nullable=True)
    sale_expense_amount = db.Column(db.Numeric(12, 2), default=0)

    # Links (plain IDs — no FK to avoid circular dependency)
    purchase_cash_entry_id = db.Column(db.Integer, nullable=True)
    purchase_expense_cash_entry_id = db.Column(db.Integer, nullable=True)
    purchase_khata_entry_id = db.Column(db.Integer, nullable=True)
    sale_cash_entry_id = db.Column(db.Integer, nullable=True)
    sale_expense_cash_entry_id = db.Column(db.Integer, nullable=True)
    sale_khata_entry_id = db.Column(db.Integer, nullable=True)
    funded_by_partner_id = db.Column(db.Integer, nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
