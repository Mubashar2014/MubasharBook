from flask import Blueprint

shareholders_bp = Blueprint('shareholders', __name__)

from app.shareholders import routes
