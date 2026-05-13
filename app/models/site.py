from app import db


class Site(db.Model):
    __tablename__ = 'sites'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.Text)
    notes = db.Column(db.Text)

    current_assets = db.relationship('Asset', foreign_keys='Asset.current_site_id',
                                     backref='current_site', lazy='dynamic')
    events_from = db.relationship('AssetEvent', foreign_keys='AssetEvent.from_site_id',
                                  backref='from_site', lazy='dynamic')
    events_to = db.relationship('AssetEvent', foreign_keys='AssetEvent.to_site_id',
                                backref='to_site', lazy='dynamic')

    def __repr__(self):
        return f'<Site {self.name}>'
