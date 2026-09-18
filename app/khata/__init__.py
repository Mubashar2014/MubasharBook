from flask import Blueprint

khata_bp = Blueprint('khata', __name__)

from app.khata import routes
