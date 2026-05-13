from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, Length

from app import db
from app.models.site import Site
from app.models.asset import Asset

sites_bp = Blueprint('sites', __name__, url_prefix='/sites')


class SiteForm(FlaskForm):
    name = StringField('שם האתר', validators=[DataRequired(), Length(max=150)])
    address = TextAreaField('כתובת', validators=[Optional()])
    notes = TextAreaField('הערות', validators=[Optional()])
    submit = SubmitField('שמור אתר')


@sites_bp.route('/')
@login_required
def list_sites():
    sites = Site.query.order_by(Site.name).all()
    counts = {
        s.id: Asset.query.filter_by(current_site_id=s.id).count()
        for s in sites
    }
    return render_template('sites/list.html', sites=sites, counts=counts)


@sites_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_site():
    if not current_user.is_admin:
        abort(403)
    form = SiteForm()
    if form.validate_on_submit():
        site = Site(
            name=form.name.data.strip(),
            address=form.address.data.strip() or None,
            notes=form.notes.data.strip() or None,
        )
        db.session.add(site)
        db.session.commit()
        flash(f'האתר "{site.name}" נוצר בהצלחה.', 'success')
        return redirect(url_for('sites.detail', id=site.id))
    return render_template('sites/form.html', form=form, site=None, title='הוספת אתר חדש')


@sites_bp.route('/<int:id>')
@login_required
def detail(id):
    site = Site.query.get_or_404(id)
    assets = Asset.query.filter_by(current_site_id=id).order_by(Asset.serial_number).all()
    status_counts = {}
    for a in assets:
        status_counts[a.status] = status_counts.get(a.status, 0) + 1
    return render_template('sites/detail.html', site=site, assets=assets, status_counts=status_counts)


@sites_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    if not current_user.is_admin:
        abort(403)
    site = Site.query.get_or_404(id)
    form = SiteForm(obj=site)
    if form.validate_on_submit():
        site.name = form.name.data.strip()
        site.address = form.address.data.strip() or None
        site.notes = form.notes.data.strip() or None
        db.session.commit()
        flash('האתר עודכן בהצלחה.', 'success')
        return redirect(url_for('sites.detail', id=site.id))
    return render_template('sites/form.html', form=form, site=site, title='עריכת אתר')
