from datetime import datetime
from app.extensions import db


class EmailLog(db.Model):
    """Track all email sends for debugging and compliance."""
    __tablename__ = 'email_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    
    # Email details
    recipient_email = db.Column(db.String(120), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=False)
    email_type = db.Column(db.String(50), nullable=False, index=True)  # 'verification', 'welcome', 'password_reset', 'payment_receipt', etc.
    
    # Delivery tracking
    status = db.Column(db.String(20), default='pending', index=True)  # pending, sent, failed, bounced
    sent_at = db.Column(db.DateTime, nullable=True)
    failed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Content (optional, for debugging)
    body_preview = db.Column(db.Text, nullable=True)  # First 500 chars
    
    # Gateway tracking
    provider = db.Column(db.String(50), nullable=True)  # 'sendgrid', 'mailgun', 'smtp'
    provider_message_id = db.Column(db.String(255), nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = db.relationship('User', backref='email_logs', lazy=True)

    def mark_sent(self, provider_message_id=None):
        """Mark email as successfully sent."""
        self.status = 'sent'
        self.sent_at = datetime.utcnow()
        if provider_message_id:
            self.provider_message_id = provider_message_id

    def mark_failed(self, error_message):
        """Mark email as failed."""
        self.status = 'failed'
        self.failed_at = datetime.utcnow()
        self.error_message = error_message

    def mark_bounced(self):
        """Mark email as bounced."""
        self.status = 'bounced'

    def __repr__(self):
        return f'<EmailLog {self.id}: {self.email_type} to {self.recipient_email} - {self.status}>'
