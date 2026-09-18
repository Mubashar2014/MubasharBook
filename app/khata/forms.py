from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField, SelectField
from wtforms.validators import DataRequired, NumberRange, Optional


class KhataEntryForm(FlaskForm):
    entry_type = SelectField('Type', choices=[('receivable', 'Money Receivable'), ('payable', 'Money Payable')])
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    description = StringField('Description', validators=[DataRequired()])
    entry_date = DateField('Date', validators=[DataRequired()])
    linked_stock_id = SelectField('Linked stock item', coerce=int, validators=[Optional()])


class SettleKhataForm(FlaskForm):
    """Form to settle (mark as paid/received) a khata entry."""
    settle_date = DateField('Settlement date', validators=[DataRequired()])
