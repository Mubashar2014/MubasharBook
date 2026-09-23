from datetime import datetime, timedelta
from app.extensions import db


class Subscription(db.Model):
    """Tracks subscription status for each shop."""
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, unique=True)
    plan = db.Column(db.String(20), default='basic')  # 'basic' or 'premium'
    billing_cycle = db.Column(db.String(20), default='monthly')  # 'monthly' or 'annual'
    
    # Status: pending, trial, active, expired, cancelled, suspended
    status = db.Column(db.String(20), default='pending', index=True)
    
    # Trial tracking
    trial_start = db.Column(db.DateTime)
    trial_end = db.Column(db.DateTime)
    
    # Subscription period tracking
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    
    # Payment & renewal
    payment_method = db.Column(db.String(50), nullable=True)  # 'card', 'jazzcash', 'easypaisa', 'bank_transfer'
    auto_renew = db.Column(db.Boolean, default=True)
    next_billing_date = db.Column(db.DateTime, nullable=True)
    
    # Cancellation & suspension
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.Text, nullable=True)
    suspended_at = db.Column(db.DateTime, nullable=True)
    suspension_reason = db.Column(db.Text, nullable=True)
    
    # Grace period (3 days after expiry for payment)
    grace_period_end = db.Column(db.DateTime, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    shop = db.relationship('Shop', backref=db.backref('subscription', uselist=False), lazy=True)

    @property
    def is_active(self):
        """Check if subscription is currently active (not expired/cancelled/suspended)."""
        return self.status in ('trial', 'active')

    @property
    def is_in_grace_period(self):
        """Check if subscription is in grace period after expiry."""
        if not self.grace_period_end:
            return False
        return datetime.utcnow() < self.grace_period_end

    @property
    def days_until_expiry(self):
        """Calculate days until subscription expires."""
        if self.status == 'trial' and self.trial_end:
            delta = self.trial_end - datetime.utcnow()
            return max(0, delta.days)
        elif self.status == 'active' and self.current_period_end:
            delta = self.current_period_end - datetime.utcnow()
            return max(0, delta.days)
        return 0

    def activate_trial(self, days=7):
        """Start trial period."""
        now = datetime.utcnow()
        self.status = 'trial'
        self.trial_start = now
        self.trial_end = now + timedelta(days=days)
        self.current_period_start = now
        self.current_period_end = self.trial_end

    def activate_subscription(self, payment_method, billing_cycle='monthly'):
        """Activate paid subscription."""
        now = datetime.utcnow()
        self.status = 'active'
        self.payment_method = payment_method
        self.billing_cycle = billing_cycle
        self.current_period_start = now
        
        # Set period end based on billing cycle
        if billing_cycle == 'annual':
            self.current_period_end = now + timedelta(days=365)
        else:
            self.current_period_end = now + timedelta(days=30)
        
        self.next_billing_date = self.current_period_end

    def expire(self):
        """Mark subscription as expired and start grace period."""
        self.status = 'expired'
        self.grace_period_end = datetime.utcnow() + timedelta(days=3)

    def cancel(self, reason=None):
        """Cancel subscription."""
        self.status = 'cancelled'
        self.cancelled_at = datetime.utcnow()
        self.cancellation_reason = reason
        self.auto_renew = False

    def suspend(self, reason=None):
        """Suspend subscription (admin action)."""
        self.status = 'suspended'
        self.suspended_at = datetime.utcnow()
        self.suspension_reason = reason

    def unsuspend(self):
        """Reactivate suspended subscription."""
        if self.status == 'suspended':
            self.status = 'active'
            self.suspended_at = None
            self.suspension_reason = None

    def renew(self):
        """Renew subscription for another billing cycle."""
        if self.billing_cycle == 'annual':
            self.current_period_end = self.current_period_end + timedelta(days=365)
        else:
            self.current_period_end = self.current_period_end + timedelta(days=30)
        
        self.current_period_start = datetime.utcnow()
        self.next_billing_date = self.current_period_end
        self.status = 'active'
        
        # Clear grace period if it was set
        self.grace_period_end = None
