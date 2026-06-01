from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from urllib.parse import urlparse
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired

from app import bcrypt
from app.routes.admin import _password_already_used
from app.models.user import User
from app.utils.translations import localize_form

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


class LoginForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember me')
    submit   = SubmitField('Sign In')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password     = PasswordField('New Password',     validators=[DataRequired()])
    submit           = SubmitField('Save Password')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    t    = getattr(g, 't', {})
    form = LoginForm()
    localize_form(form, t, submit_key='login_submit')
    if form.validate_on_submit():
        matched = None
        for u in User.objects.all():
            if bcrypt.check_password_hash(u.password_hash, form.password.data):
                matched = u
                break
        if matched:
            from datetime import datetime
            matched.last_login = datetime.utcnow()
            matched.last_seen  = datetime.utcnow()
            matched.save()
            login_user(matched, remember=form.remember.data)
            next_page = request.args.get('next', '')
            parsed = urlparse(next_page)
            if parsed.scheme or parsed.netloc:
                next_page = ''
            flash(t.get('flash_welcome', 'Welcome back, {name}!').format(name=matched.name), 'success')
            return redirect(next_page or url_for('main.dashboard'))
        flash(t.get('flash_login_failed', 'Incorrect password.'), 'danger')
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    t = getattr(g, 't', {})
    logout_user()
    flash(t.get('flash_logged_out', 'You have been logged out.'), 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    t    = getattr(g, 't', {})
    form = ChangePasswordForm()
    localize_form(form, t, submit_key='form_save_password')
    if form.validate_on_submit():
        if not bcrypt.check_password_hash(current_user.password_hash, form.current_password.data):
            flash(t.get('flash_wrong_password', 'Current password is incorrect.'), 'danger')
        elif bcrypt.check_password_hash(current_user.password_hash, form.new_password.data):
            flash(t.get('flash_same_password', 'New password must be different from your current password.'), 'danger')
        elif _password_already_used(form.new_password.data, exclude_id=current_user.id):
            flash(t.get('flash_password_taken', 'הסיסמה קיימת במערכת — בחר סיסמה אחרת.'), 'danger')
        else:
            current_user.password_hash = bcrypt.generate_password_hash(
                form.new_password.data
            ).decode('utf-8')
            current_user.save()
            flash(t.get('flash_password_changed', 'Password changed successfully.'), 'success')
            return redirect(url_for('main.dashboard'), 303)
        return redirect(url_for('auth.change_password'), 303)
    return render_template('auth/change_password.html', form=form)
