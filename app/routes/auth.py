from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length

from app import db, bcrypt
from app.models.user import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


class LoginForm(FlaskForm):
    email = StringField('אימייל', validators=[DataRequired(), Email(check_deliverability=False)])
    password = PasswordField('סיסמה', validators=[DataRequired()])
    remember = BooleanField('זכור אותי')
    submit = SubmitField('כניסה')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('סיסמה נוכחית', validators=[DataRequired()])
    new_password = PasswordField('סיסמה חדשה', validators=[DataRequired(), Length(min=8)])
    submit = SubmitField('שמור סיסמה')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash(f'ברוך שובך, {user.name}!', 'success')
            return redirect(next_page or url_for('main.dashboard'))
        flash('אימייל או סיסמה שגויים.', 'danger')
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('התנתקת בהצלחה.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not bcrypt.check_password_hash(current_user.password_hash, form.current_password.data):
            flash('הסיסמה הנוכחית שגויה.', 'danger')
        else:
            current_user.password_hash = bcrypt.generate_password_hash(
                form.new_password.data
            ).decode('utf-8')
            db.session.commit()
            flash('הסיסמה שונתה בהצלחה.', 'success')
            return redirect(url_for('main.dashboard'))
    return render_template('auth/change_password.html', form=form)
