from flask import Blueprint

subscription_bp = Blueprint('subscription', __name__)

from app.subscription import routes
