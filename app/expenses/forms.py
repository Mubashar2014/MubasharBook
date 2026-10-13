from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField, SelectField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Optional, Length


class ExpenseForm(FlaskForm):
    category_id = SelectField('Category', coerce=int, validators=[DataRequired()])
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    description = StringField('Description', validators=[Optional(), Length(max=300)])
    expense_date = DateField('Date', validators=[DataRequired()])
    payee_name = StringField('Payee name', validators=[Optional(), Length(max=100)])
    payee_phone = StringField('Payee phone (WhatsApp)', validators=[Optional(), Length(max=20)])


class ExpenseCategoryForm(FlaskForm):
    name = StringField('Category name', validators=[DataRequired(), Length(max=100)])


class LoanForm(FlaskForm):
    direction = SelectField(
        'Direction', choices=[('borrowed', 'We borrowed (we pay installments)'),
                              ('lent', 'We lent out (they pay us back)')],
        validators=[DataRequired()],
    )
    party_name = StringField('Party name', validators=[DataRequired(), Length(max=100)])
    party_phone = StringField('Phone (optional, for WhatsApp)', validators=[Optional(), Length(max=20)])
    principal = FloatField('Principal amount', validators=[DataRequired(), NumberRange(min=0.01)])
    start_date = DateField('Start date', validators=[DataRequired()])
    notes = StringField('Notes', validators=[Optional(), Length(max=300)])


class LoanPaymentForm(FlaskForm):
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    paid_date = DateField('Date', validators=[DataRequired()])
    notes = StringField('Notes', validators=[Optional(), Length(max=300)])
