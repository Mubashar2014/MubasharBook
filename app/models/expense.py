from datetime import datetime
from app.extensions import db


class ExpenseCategory(db.Model):
    """Expense categories — predefined + user-created custom categories."""
    __tablename__ = 'expense_categories'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)  # True for predefined categories
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Expense(db.Model):
    """Business expense entry."""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.String(300))
    expense_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
