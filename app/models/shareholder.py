from datetime import datetime
from app.extensions import db


class Partner(db.Model):
    """A partner in a shop — can be managing owner or silent investor."""
    __tablename__ = 'partners'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'owner' or 'investor'
    investment_amount = db.Column(db.Numeric(14, 2), nullable=False)
    investment_ratio = db.Column(db.Float)  # auto-calculated percentage
    investor_user_id = db.Column(db.Integer, db.ForeignKey('investors.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SplitRule(db.Model):
    """Profit split rule for a shop — one active rule per shop."""
    __tablename__ = 'split_rules'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, unique=True)
    management_base_pct = db.Column(db.Float, default=30.0)  # % off top for managing owners
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Period(db.Model):
    """A 30-day accounting period for a shop."""
    __tablename__ = 'periods'

    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), default='open')  # open or locked
    locked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PeriodSnapshot(db.Model):
    """Snapshot of a partner's split for a locked period. Never recalculated."""
    __tablename__ = 'period_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=False, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False, index=True)

    # Snapshot of ratios at time of lock
    investment_ratio_at_lock = db.Column(db.Float, nullable=False)
    management_base_pct_at_lock = db.Column(db.Float, nullable=False)

    # Calculated amounts (never recalculated)
    net_profit = db.Column(db.Numeric(14, 2), nullable=False)
    loss_amount = db.Column(db.Numeric(14, 2), default=0)
    share_amount = db.Column(db.Numeric(14, 2), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
