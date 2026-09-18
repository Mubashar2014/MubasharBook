from flask import Blueprint

investor_bp = Blueprint('investor', __name__)

from app.investor import routes
