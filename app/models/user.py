import secrets
from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db, login_manager


class User(UserMixin, db.Model):
    """Shop owner account."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    owner_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    language = db.Column(db.String(5), default='ur')  # 'en' or 'ur'
    is_premium = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)  # Product owner/admin flag
    trial_start = db.Column(db.DateTime, default=datetime.utcnow)
    trial_end = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)  # email verified (deprecated, use email_verified_at)
    email_verified_at = db.Column(db.DateTime, nullable=True)  # When email was verified
    last_login_at = db.Column(db.DateTime, nullable=True)  # Last successful login
    verification_token = db.Column(db.String(64), nullable=True, index=True)
    verification_sent_at = db.Column(db.DateTime, nullable=True)
    reset_token = db.Column(db.String(64), nullable=True, index=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    shop = db.relationship('Shop', backref='owner', uselist=False, lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_trial_active(self):
        if self.trial_end is None:
            return True
        return datetime.utcnow() < self.trial_end

    @property
    def is_read_only(self):
        """Account is read-only when trial expired and not premium."""
        return not self.is_trial_active and not self.is_premium

    def start_trial(self, days=7):
        self.trial_start = datetime.utcnow()
        self.trial_end = datetime.utcnow() + timedelta(days=days)

    def generate_verification_token(self):
        """Generate a new email verification token."""
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_sent_at = datetime.utcnow()
        return self.verification_token

    def generate_reset_token(self, expires_in=3600):
        """Generate a new password reset token (default 1 hour)."""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        return self.reset_token

    def verify_reset_token(self, token):
        """Check if reset token is valid and not expired."""
        return (self.reset_token == token and
                self.reset_token_expiry and
                datetime.utcnow() < self.reset_token_expiry)

    def clear_verification_token(self):
        self.verification_token = None
        self.verification_sent_at = None

    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_expiry = None

    def mark_login(self):
        """Update last login timestamp."""
        self.last_login_at = datetime.utcnow()

    def verify_email(self):
        """Mark email as verified."""
        self.is_verified = True
        self.email_verified_at = datetime.utcnow()
        self.clear_verification_token()


class Investor(UserMixin, db.Model):
    """Investor account (separate from shop owner)."""
    __tablename__ = 'investors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(64), nullable=True, index=True)
    verification_sent_at = db.Column(db.DateTime, nullable=True)
    reset_token = db.Column(db.String(64), nullable=True, index=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_verification_token(self):
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_sent_at = datetime.utcnow()
        return self.verification_token

    def generate_reset_token(self, expires_in=3600):
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        return self.reset_token

    def verify_reset_token(self, token):
        return (self.reset_token == token and
                self.reset_token_expiry and
                datetime.utcnow() < self.reset_token_expiry)

    def clear_verification_token(self):
        self.verification_token = None
        self.verification_sent_at = None

    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_expiry = None


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))