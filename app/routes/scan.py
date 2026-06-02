from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required
from mongoengine import Q

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

    asset = Asset.objects(Q(serial_number=q) | Q(barcode=q)).first()

    if asset:
        try:
            asset_type_name = asset.asset_type.name if asset.asset_type else None
        except Exception:
            asset_type_name = None
        try:
            assignee_name = asset.assignee.name if asset.assignee else None
        except Exception:
            assignee_name = None

        return jsonify({
            'found': True,
            'asset': {
                'id':           str(asset.id),
                'serial_number': asset.serial_number,
                'barcode':      asset.barcode or '',
                'status':       asset.status,
                'status_label': asset.status_label,
                'status_color': asset.status_color,
                'type':         asset_type_name,
                'model':        asset.model or '',
                'manufacturer': asset.manufacturer or '',
                'assignee':     assignee_name,
                'detail_url':   url_for('assets.detail', id=str(asset.id)),
            }
        })

    return jsonify({
        'found': False,
        'query': q,
        'register_url': url_for('assets.new_asset', serial=q),
    })
