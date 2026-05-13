from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required

from app import db
from app.models.asset import Asset

scan_bp = Blueprint('scan', __name__, url_prefix='/scan')


@scan_bp.route('/')
@login_required
def index():
    return render_template('scan/index.html')


@scan_bp.route('/api/lookup')
@login_required
def lookup():
    q = request.args.get('q', '').strip().upper()
    if not q:
        return jsonify({'error': 'No query provided'}), 400

    asset = Asset.query.filter(
        db.or_(Asset.serial_number == q, Asset.barcode == q)
    ).first()

    if asset:
        return jsonify({
            'found': True,
            'asset': {
                'id': asset.id,
                'serial_number': asset.serial_number,
                'barcode': asset.barcode,
                'status': asset.status,
                'status_label': asset.status_label,
                'status_color': asset.status_color,
                'type': asset.asset_type.name if asset.asset_type else None,
                'model': asset.model or '',
                'manufacturer': asset.manufacturer or '',
                'site': asset.current_site.name if asset.current_site else None,
                'assignee': asset.assignee.name if asset.assignee else None,
                'detail_url': url_for('assets.detail', id=asset.id),
            }
        })

    return jsonify({
        'found': False,
        'query': q,
        'register_url': url_for('assets.new_asset', serial=q),
    })
