from datetime import datetime
from app.extensions import db


class Notification(db.Model):
    """In-app notifications for users."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Notification content
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False, index=True)  # 'info', 'warning', 'success', 'error', 'payment', 'trial'
    
    # Action link (optional)
    action_url = db.Column(db.String(500), nullable=True)
    action_text = db.Column(db.String(100), nullable=True)
    
    # Status
    is_read = db.Column(db.Boolean, default=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Priority (for sorting)
    priority = db.Column(db.Integer, default=0)  # higher = more important
    
    # Expiry (auto-delete old notifications)
    expires_at = db.Column(db.DateTime, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = db.relationship('User', backref='notifications', lazy=True)

    def mark_read(self):
        """Mark notification as read."""
        self.is_read = True
        self.read_at = datetime.utcnow()

    @property
    def is_expired(self):
        """Check if notification has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def __repr__(self):
        return f'<Notification {self.id}: {self.notification_type} for user {self.user_id}>'
