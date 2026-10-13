from datetime import datetime
from app.extensions import db


class Loan(db.Model):
    """Loan book — money borrowed by the shop or lent out.

    direction='borrowed' → shop received money, pays installments out (cash out)
    direction='lent'     → shop gave money, receives installments (cash in)

    Principal only, no interest. Payments never create Expense rows, so
    P&L is untouched — cashbook-only, as a liability/asset movement.
    """
    __tablename__ = 'loans'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)  # 'borrowed' | 'lent'
    party_name = db.Column(db.String(100), nullable=False)
    party_phone = db.Column(db.String(20), nullable=True)
    principal = db.Column(db.Numeric(12, 2), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(10), nullable=False, default='active')  # 'active' | 'closed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payments = db.relationship(
        'LoanPayment', backref=db.backref('loan', lazy=True),
        lazy=True, order_by='LoanPayment.paid_date.asc(), LoanPayment.id.asc()',
        cascade='all, delete-orphan',
    )

    @property
    def paid_amount(self):
        return sum(float(p.amount) for p in self.payments)

    @property
    def balance(self):
        return float(self.principal) - self.paid_amount


class LoanPayment(db.Model):
    """One installment against a loan. Mirrors into the cashbook only."""
    __tablename__ = 'loan_payments'

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    paid_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.String(300), nullable=True)
    cash_entry_id = db.Column(db.Integer, nullable=True)  # plain ID, no FK (app convention)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
