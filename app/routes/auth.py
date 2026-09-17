import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from urllib.parse import urlparse
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, BooleanField, SubmitField
from wtforms import StringField
from wtforms.validators import DataRequired, Length, ValidationError


def _byte_length(max=72):
    def validate(form, field):
        if len((field.data or '').encode('utf-8')) > max:
            raise ValidationError(f'Password cannot exceed {max} bytes.')
    return validate

import re
from app import bcrypt, limiter
from app.routes.admin import _password_already_used
from app.models.user import User
from app.utils.translations import localize_form

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

_DUMMY_HASH = None

def _dummy_hash():
    """A precomputed bcrypt hash checked when a username lookup misses, so a
    nonexistent username takes the same time to reject as a wrong password —
    otherwise the skipped bcrypt call makes username existence measurable
    via response timing."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = bcrypt.generate_password_hash('constant-time-padding').decode('utf-8')
    return _DUMMY_HASH


class LoginForm(FlaskForm):
    username = StringField('Username')  # optional — speeds up login when set
    password = PasswordField('Password', validators=[DataRequired(), _byte_length(max=72)])
    remember = BooleanField('Remember me')
    submit   = SubmitField('Sign In')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired(), _byte_length(max=72)])
    new_password     = PasswordField('New Password',     validators=[DataRequired(), Length(min=8), _byte_length(max=72)])
    submit           = SubmitField('Save Password')


def _login_username_key():
    """Rate-limit key based on the submitted username (not whether it's a
    real account — using request.form directly, before form validation, so
    the limit applies identically to real and fake usernames alike and adds
    no new way to detect which usernames exist)."""
    uname = (request.form.get('username') or '').strip().lower()
    return uname or 'no-username'


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')                                    # per source IP
@limiter.limit('10 per minute', key_func=_login_username_key)      # per submitted username
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    t    = getattr(g, 't', {})
    form = LoginForm()
    localize_form(form, t, submit_key='login_submit')
    if form.validate_on_submit():
        matched = None
        uname = (form.username.data or '').strip().lower()
        if uname:
            # Fast path: direct index lookup by username
            candidate = User.objects(username=uname).first()
            if candidate:
                if bcrypt.check_password_hash(candidate.password_hash, form.password.data):
                    matched = candidate
            else:
                # No such username — still run a bcrypt check against a dummy
                # hash so this branch takes the same time as a real mismatch.
                bcrypt.check_password_hash(_dummy_hash(), form.password.data)
        else:
            # Fallback: scan all users sorted by last_login (password-only mode)
            for u in User.objects.order_by('-last_login'):
                if bcrypt.check_password_hash(u.password_hash, form.password.data):
                    matched = u
                    break
        if matched:
            from datetime import datetime
            matched.last_login = datetime.utcnow()
            matched.last_seen  = datetime.utcnow()
            matched.save()
            login_user(matched, remember=form.remember.data)
            # Strip control characters browsers ignore when parsing a URL
            # (tab/CR/LF) — otherwise "/\t/evil.com" passes the checks below
            # but a browser reads it as "//evil.com" and redirects off-site.
            next_page = re.sub(r'[\t\r\n]', '', request.args.get('next', ''))
            if (not next_page
                    or not next_page.startswith('/')
                    or next_page.startswith('//')
                    or next_page[1:2] == '\\'):
                next_page = ''
            flash(t.get('flash_welcome', 'Welcome back, {name}!').format(name=matched.name), 'success')
            return redirect(next_page or url_for('main.dashboard'))
        form.password.errors.append(t.get('flash_login_failed', 'Incorrect password.'))
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
