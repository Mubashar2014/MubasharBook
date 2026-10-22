from datetime import datetime
from app.extensions import db


class WhatsAppMessage(db.Model):
    """Outbox row for automatic user WhatsApp notifications (welcome,
    package activated, trial expired). Sent via Evolution API when
    configured, otherwise from the admin panel with one click."""
    __tablename__ = 'whatsapp_messages'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(30), nullable=False)  # welcome | package_active | trial_expired
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(15), nullable=False, default='pending')  # pending | sent | failed | dismissed
    error = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref=db.backref('whatsapp_messages', lazy='selectin'))
