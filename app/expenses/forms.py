from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField, SelectField
from wtforms.validators import DataRequired, NumberRange, Optional, Length


class ExpenseForm(FlaskForm):
    category_id = SelectField('Category', coerce=int, validators=[DataRequired()])
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    description = StringField('Description', validators=[Optional(), Length(max=300)])
    expense_date = DateField('Date', validators=[DataRequired()])


class ExpenseCategoryForm(FlaskForm):
    name = StringField('Category name', validators=[DataRequired(), Length(max=100)])
