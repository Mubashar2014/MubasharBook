from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField, SelectField, IntegerField
from wtforms.validators import DataRequired, NumberRange, Optional


class CashEntryForm(FlaskForm):
    entry_type = SelectField('Type', choices=[('in', 'Cash In'), ('out', 'Cash Out')])
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    description = StringField('Description', validators=[DataRequired()])
    entry_date = DateField('Date', validators=[DataRequired()])
    linked_stock_id = SelectField('Linked stock item', coerce=int, validators=[Optional()])
