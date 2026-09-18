from datetime import datetime
from app.extensions import db


class Subscription(db.Model):
    """Tracks subscription status for each shop."""
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, unique=True)
    plan = db.Column(db.String(20), default='basic')  # 'basic' or 'premium'
    status = db.Column(db.String(20), default='trial')  # trial, active, expired
    trial_start = db.Column(db.DateTime)
    trial_end = db.Column(db.DateTime)
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
