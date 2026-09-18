from datetime import datetime
from app.extensions import db


class Shop(db.Model):
    """Each shop is a tenant — all data scoped to shop_id."""
    __tablename__ = 'shops'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    
    # Capital tracking
    initial_investment = db.Column(db.Numeric(14, 2), default=0)  # owner's initial capital
    shop_image = db.Column(db.String(300), nullable=True)  # path to uploaded image
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)