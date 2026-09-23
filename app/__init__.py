import os
import logging
from flask import Flask, flash, redirect, url_for, request, render_template, jsonify
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from app.config import config
from app.extensions import db, login_manager, csrf, migrate, mail

logger = logging.getLogger(__name__)


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

    if app.config['SECRET_KEY'] == 'dev-fallback-change-me':
        logger.warning('SECRET_KEY is using the insecure development fallback — set SECRET_KEY in .env')

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # Don't cache authenticated HTML (stale pages = stale CSRF tokens = 400)
    @app.after_request
    def add_no_cache_headers(response):
        if request.endpoint and request.endpoint != 'static':
            if request.path.startswith('/static'):
                return response
            response.headers.setdefault('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            response.headers.setdefault('Pragma', 'no-cache')
            response.headers.setdefault('Expires', '0')
        return response

    # Friendly CSRF failure instead of bare white 400
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        logger.warning('CSRF failure on %s %s: %s', request.method, request.path, e.description)
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error='CSRF token missing or invalid'), 400
        flash('Your session expired. Please try again.', 'warning')
        # Safe landing: never re-POST — send them to a fresh GET
        if request.method == 'POST':
            return redirect(request.referrer or url_for('main.dashboard'))
        return render_template('errors/400.html', message='Invalid security token. Please refresh and try again.'), 400

    @app.errorhandler(400)
    def bad_request(e):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error=str(e.description)), 400
        return render_template('errors/400.html', message=getattr(e, 'description', 'Bad request')), 400

    @app.errorhandler(403)
    def forbidden(e):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error=str(e.description)), 403
        return render_template('errors/403.html', message=getattr(e, 'description', 'Forbidden')), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error='Not found'), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.exception('Unhandled 500 on %s %s', request.method, request.path)
        db.session.rollback()
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error='Internal server error'), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        if isinstance(e, HTTPException):
            return e
        logger.exception('Unhandled exception on %s %s', request.method, request.path)
        db.session.rollback()
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error='Internal server error'), 500
        return render_template('errors/500.html'), 500

    # Read-only enforcement: block POST/state-changing requests for expired accounts
    @app.before_request
    def enforce_read_only():
        if not current_user.is_authenticated:
            return None
        
        # Redirect admin users away from non-admin pages
        if current_user.is_admin and request.endpoint and not request.endpoint.startswith('admin.') and not request.endpoint.startswith('auth.') and not request.endpoint.startswith('static'):
            return redirect(url_for('admin.dashboard'))
        
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

    from app.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Import models so SQLAlchemy knows about all tables
    from app.models import user, shop, stock, cashbook, khata, expense, shareholder, subscription

    # Register CLI commands
    from app.cli import register_commands
    register_commands(app)

    # Make format_currency available in all templates
    from app.utils import format_currency
    app.jinja_env.globals['format_currency'] = format_currency

    return app