from datetime import datetime
from app.extensions import db


class AdminLog(db.Model):
    """Audit trail for admin actions."""
    __tablename__ = 'admin_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Action details
    action = db.Column(db.String(100), nullable=False, index=True)  # 'user_suspended', 'payment_verified', 'subscription_extended', etc.
    target_type = db.Column(db.String(50), nullable=True)  # 'user', 'subscription', 'payment'
    target_id = db.Column(db.Integer, nullable=True)
    
    # Details
    description = db.Column(db.Text, nullable=False)
    changes = db.Column(db.Text, nullable=True)  # JSON of before/after values
    
    # Context
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    admin_user = db.relationship('User', backref='admin_actions', lazy=True)

    @staticmethod
    def log_action(admin_user_id, action, description, target_type=None, target_id=None, changes=None, ip_address=None, user_agent=None):
        """Helper to create admin log entry."""
        log = AdminLog(
            admin_user_id=admin_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            description=description,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(log)
        return log

    def __repr__(self):
        return f'<AdminLog {self.id}: {self.action} by admin {self.admin_user_id}>'
