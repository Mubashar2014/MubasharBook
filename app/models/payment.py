from datetime import datetime
from app.extensions import db


class Payment(db.Model):
    """Track all payment transactions."""
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Payment details
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='PKR')
    payment_method = db.Column(db.String(50), nullable=False)  # 'card', 'jazzcash', 'easypaisa', 'bank_transfer', 'stripe'
    
    # Status: pending, completed, failed, refunded
    status = db.Column(db.String(20), default='pending', index=True)
    
    # Gateway integration
    gateway = db.Column(db.String(50), nullable=True)  # 'stripe', 'jazzcash', 'manual'
    gateway_transaction_id = db.Column(db.String(255), nullable=True, unique=True, index=True)
    gateway_response = db.Column(db.Text, nullable=True)  # JSON response from gateway
    
    # Receipt & verification
    receipt_url = db.Column(db.String(500), nullable=True)
    verified_by_admin = db.Column(db.Boolean, default=False)  # For manual payments
    verified_at = db.Column(db.DateTime, nullable=True)
    
    # Refund tracking
    refunded_at = db.Column(db.DateTime, nullable=True)
    refund_reason = db.Column(db.Text, nullable=True)
    refund_amount = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Metadata
    description = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)  # Admin notes
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscription = db.relationship('Subscription', backref='payments', lazy=True)
    user = db.relationship('User', backref='payments', lazy=True)

    def mark_completed(self):
        """Mark payment as completed."""
        self.status = 'completed'
        self.updated_at = datetime.utcnow()

    def mark_failed(self, reason=None):
        """Mark payment as failed."""
        self.status = 'failed'
        if reason:
            self.notes = reason
        self.updated_at = datetime.utcnow()

    def refund(self, amount=None, reason=None):
        """Mark payment as refunded."""
        self.status = 'refunded'
        self.refunded_at = datetime.utcnow()
        self.refund_amount = amount or self.amount
        self.refund_reason = reason
        self.updated_at = datetime.utcnow()

    def verify_manual_payment(self, admin_id):
        """Admin verifies manual payment (bank transfer)."""
        self.verified_by_admin = True
        self.verified_at = datetime.utcnow()
        self.status = 'completed'
        if not self.notes:
            self.notes = f'Verified by admin ID: {admin_id}'

    def __repr__(self):
        return f'<Payment {self.id}: {self.amount} {self.currency} - {self.status}>'
