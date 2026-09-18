import os
from flask import Flask, flash, redirect, url_for, request
from flask_login import current_user
from app.config import config
from app.extensions import db, login_manager, csrf, migrate, mail


def get_shop_id():
    """Get current user's shop_id, or None if not logged in."""
    if current_user.is_authenticated and hasattr(current_user, 'shop') and current_user.shop:
        return current_user.shop.id
    return None


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__, static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'), template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # Read-only enforcement: block POST/state-changing requests for expired accounts
    @app.before_request
    def enforce_read_only():
        if not current_user.is_authenticated:
            return None
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None
        if current_user.is_read_only:
            flash('Your trial has expired. Subscribe to continue making changes.', 'warning')
            return redirect(url_for('main.dashboard'))

    # Register blueprints
    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.main import main_bp
    app.register_blueprint(main_bp)

    from app.stock import stock_bp
    app.register_blueprint(stock_bp, url_prefix='/stock')

    from app.cashbook import cashbook_bp
    app.register_blueprint(cashbook_bp, url_prefix='/cashbook')

    from app.khata import khata_bp
    app.register_blueprint(khata_bp, url_prefix='/khata')

    from app.expenses import expenses_bp
    app.register_blueprint(expenses_bp, url_prefix='/expenses')

    from app.reports import reports_bp
    app.register_blueprint(reports_bp, url_prefix='/reports')

    from app.shareholders import shareholders_bp
    app.register_blueprint(shareholders_bp, url_prefix='/shareholders')

    from app.investor import investor_bp
    app.register_blueprint(investor_bp, url_prefix='/investor')

    # Import models so SQLAlchemy knows about all tables
    from app.models import user, shop, stock, cashbook, khata, expense, shareholder, subscription

    # Make format_currency available in all templates
    from app.utils import format_currency
    app.jinja_env.globals['format_currency'] = format_currency

    return app