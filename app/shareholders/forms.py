from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SelectField
from wtforms.validators import DataRequired, NumberRange, Email, Optional, Length


class PartnerForm(FlaskForm):
    name = StringField('Partner name', validators=[DataRequired()])
    role = SelectField('Role', choices=[('owner', 'Managing Owner'), ('investor', 'Investor')])
    investment_amount = FloatField('Investment amount (Rs)', validators=[DataRequired(), NumberRange(min=1)])
    investor_email = StringField('Investor email', validators=[Optional(), Email()])
    investor_phone = StringField('Investor phone', validators=[Optional(), Length(max=20)])


class SplitRuleForm(FlaskForm):
    management_base_pct = FloatField('Management base %', validators=[DataRequired(), NumberRange(min=0, max=60)])
