import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from urllib.parse import urlparse
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length

from app import bcrypt, limiter
from app.routes.admin import _password_already_used
from app.models.user import User
from app.utils.translations import localize_form
from app.utils.login_recorder import record_login, get_ip

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


class LoginForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired(), Length(max=72)])
    remember = BooleanField('Remember me')
    submit   = SubmitField('Sign In')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired(), Length(max=72)])
    new_password     = PasswordField('New Password',     validators=[DataRequired(), Length(min=8, max=72)])
    submit           = SubmitField('Save Password')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    t    = getattr(g, 't', {})
    form = LoginForm()
    localize_form(form, t, submit_key='login_submit')
    if form.validate_on_submit():
        matched = None
        # Sort by last_login so most-recently-active user is checked first,
        # minimising bcrypt iterations on average without changing the UX.
        for u in User.objects.order_by('-last_login'):
            if bcrypt.check_password_hash(u.password_hash, form.password.data):
                matched = u
                break
        if matched:
            from datetime import datetime
            prev_login = matched.last_login
            matched.last_login = datetime.utcnow()
            matched.last_seen  = datetime.utcnow()
            matched.save()
            login_user(matched, remember=form.remember.data)
            record_login(
                user_name=matched.name, user_role=matched.role,
                user_id=str(matched.id), ip=get_ip(request),
                ua=request.headers.get('User-Agent', ''), success=True,
            )
            next_page = request.args.get('next', '')
            # Allow only safe relative paths.
            # Block: empty, non-slash-prefixed, protocol-relative (//), and backslash-relative (/\)
            # because Chrome/Edge/Safari normalise /\ to // enabling open-redirect.
            if (not next_page
                    or not next_page.startswith('/')
                    or next_page.startswith('//')
                    or next_page[1:2] == '\\'):
                next_page = ''
            flash(t.get('flash_welcome', 'Welcome back, {name}!').format(name=matched.name), 'success')
            if prev_login:
                fmt = prev_login.strftime('%d %b %Y, %H:%M')
                flash(t.get('flash_last_login', 'Last login: {date}').format(date=fmt), 'info')
            return redirect(next_page or url_for('main.dashboard'))
        record_login(
            user_name='—', user_role='—',
            ip=get_ip(request),
            ua=request.headers.get('User-Agent', ''), success=False,
        )
        flash(t.get('flash_login_failed', 'Incorrect password.'), 'danger')
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    t = getattr(g, 't', {})
    logout_user()
    flash(t.get('flash_logged_out', 'You have been logged out.'), 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@limiter.limit('5 per minute')
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
            current_user.session_version = (current_user.session_version or 0) + 1
            current_user.save()
            from flask_login import logout_user
            logout_user()
            flash(t.get('flash_password_changed', 'Password changed successfully. Please log in again.'), 'success')
            return redirect(url_for('auth.login'), 303)
        return redirect(url_for('auth.change_password'), 303)
    return render_template('auth/change_password.html', form=form)
