from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, DecimalField, FileField, EmailField
from wtforms.validators import DataRequired, Length, Optional, Email, EqualTo
from flask_wtf.file import FileAllowed


class SignupForm(FlaskForm):
    owner_name = StringField('Owner name', validators=[DataRequired(), Length(max=120)])
    phone = StringField('Phone number', validators=[DataRequired(), Length(max=20)])
    email = EmailField('Email address', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password')])
    language = SelectField('Preferred language',
                          choices=[('en', 'English'), ('ur', 'Roman Urdu')],
                          default='ur')
    shop_name = StringField('Shop name', validators=[Optional(), Length(max=120)])
    total_investment = DecimalField('Total investment (Rs)', validators=[DataRequired()])
    shop_image = FileField('Shop photo (optional)', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Images only')])


class LoginForm(FlaskForm):
    phone = StringField('Phone number', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class ShopSettingsForm(FlaskForm):
    shop_name = StringField('Shop name', validators=[DataRequired(), Length(max=120)])
    initial_investment = DecimalField('Total investment (Rs)', validators=[DataRequired()])
    shop_image = FileField('Shop photo (optional)', validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png'], 'Images only')])


class ForgotPasswordForm(FlaskForm):
    email = EmailField('Email address', validators=[DataRequired(), Email(), Length(max=120)])


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password')])


class ResendVerificationForm(FlaskForm):
    email = EmailField('Email address', validators=[DataRequired(), Email(), Length(max=120)])