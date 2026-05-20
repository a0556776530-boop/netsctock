from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, Email

from app.models.contact import Contact
from app.utils.mongo_helpers import get_or_404

contacts_bp = Blueprint('contacts', __name__, url_prefix='/contacts')


class ContactForm(FlaskForm):
    name   = StringField('Full Name',      validators=[DataRequired(), Length(max=150)])
    email  = StringField('Personal Email', validators=[Optional(), Email(), Length(max=200)])
    phone  = StringField('Phone Number',   validators=[Optional(), Length(max=30)])
    notes  = TextAreaField('Notes',        validators=[Optional()])
    submit = SubmitField('Save Contact')


@contacts_bp.route('/')
@login_required
def list_contacts():
    contacts = list(Contact.objects.order_by('name'))
    return render_template('contacts/list.html', contacts=contacts)


@contacts_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_contact():
    form = ContactForm()
    if form.validate_on_submit():
        Contact(
            name  = form.name.data.strip(),
            email = (form.email.data or '').strip() or None,
            phone = (form.phone.data or '').strip() or None,
            notes = (form.notes.data or '').strip() or None,
        ).save()
        flash(f'Contact "{form.name.data.strip()}" added.', 'success')
        return redirect(url_for('contacts.list_contacts'))
    return render_template('contacts/form.html', form=form, title='New Contact', contact=None)


@contacts_bp.route('/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit_contact(id):
    contact = get_or_404(Contact, id)
    form = ContactForm(obj=contact)
    if form.validate_on_submit():
        contact.name  = form.name.data.strip()
        contact.email = (form.email.data or '').strip() or None
        contact.phone = (form.phone.data or '').strip() or None
        contact.notes = (form.notes.data or '').strip() or None
        contact.save()
        flash(f'Contact "{contact.name}" updated.', 'success')
        return redirect(url_for('contacts.list_contacts'))
    return render_template('contacts/form.html', form=form, title='Edit Contact', contact=contact)


@contacts_bp.route('/<id>/send-email', methods=['POST'])
@login_required
def send_email(id):
    contact = get_or_404(Contact, id)
    subject = (request.form.get('subject') or '').strip() or 'Message from NetStock'
    body    = (request.form.get('body')    or '').strip()

    if not contact.email:
        flash(f'{contact.name} has no email address.', 'warning')
        return redirect(url_for('contacts.list_contacts'))

    if not body:
        flash('Message body cannot be empty.', 'warning')
        return redirect(url_for('contacts.list_contacts'))

    import os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host     = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port     = int(os.environ.get('SMTP_PORT', '587'))
    smtp_email    = os.environ.get('SMTP_EMAIL', '')
    smtp_password = os.environ.get('SMTP_PASSWORD', '')

    if not smtp_email or not smtp_password:
        flash(
            'SMTP is not configured. Create a <strong>.env</strong> file next to '
            'Inventory.exe with SMTP_EMAIL and SMTP_PASSWORD.',
            'warning',
        )
        return redirect(url_for('contacts.list_contacts'))

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = smtp_email
    msg['To']      = contact.email

    html = f"""\
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;color:#333;padding:24px;">
  <h2 style="color:#1a5fa8;">NetStock</h2>
  <p>{body.replace(chr(10), '<br>')}</p>
  <p style="color:#aaa;font-size:12px;margin-top:32px;">— NetStock Inventory System</p>
</body></html>"""

    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html',  'utf-8'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        flash(f'Email sent to {contact.email}.', 'success')
    except Exception as exc:
        flash(f'Failed to send email: {exc}', 'danger')

    return redirect(url_for('contacts.list_contacts'))


@contacts_bp.route('/<id>/delete', methods=['POST'])
@login_required
def delete_contact(id):
    if not current_user.is_admin:
        abort(403)
    contact = get_or_404(Contact, id)
    name = contact.name
    contact.delete()
    flash(f'Contact "{name}" deleted.', 'info')
    return redirect(url_for('contacts.list_contacts'))
