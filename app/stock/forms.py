from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, IntegerField, DateField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length, NumberRange


class StockInForm(FlaskForm):
    """Form for adding new stock (buying from supplier)."""
    model_name = StringField('Phone model', validators=[DataRequired(), Length(max=200)])
    imei = StringField('IMEI', validators=[Optional(), Length(max=20)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)], default=1)
    cost_price = DecimalField('Cost price per unit (Rs)', validators=[DataRequired(), NumberRange(min=0)])
    purchase_date = DateField('Purchase date', validators=[DataRequired()])
    supplier_name = StringField('Supplier name', validators=[Optional(), Length(max=200)])
    purchase_paid = DecimalField('Paid now (Rs)', validators=[Optional(), NumberRange(min=0)], default=0)
    purchase_expense_desc = StringField('Extra expense description', validators=[Optional(), Length(max=300)])
    purchase_expense_amount = DecimalField('Extra expense amount (Rs)', validators=[Optional(), NumberRange(min=0)], default=0)


class StockOutForm(FlaskForm):
    """Form for selling a stock item."""
    sale_price = DecimalField('Selling price per unit (Rs)', validators=[DataRequired(), NumberRange(min=0)])
    sale_date = DateField('Sale date', validators=[DataRequired()])
    customer_name = StringField('Customer name', validators=[Optional(), Length(max=200)])
    sale_received = DecimalField('Received now (Rs)', validators=[Optional(), NumberRange(min=0)], default=0)
    sale_expense_desc = StringField('Extra expense description', validators=[Optional(), Length(max=300)])
    sale_expense_amount = DecimalField('Extra expense amount (Rs)', validators=[Optional(), NumberRange(min=0)], default=0)
