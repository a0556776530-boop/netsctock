from flask import abort
from bson import ObjectId
from bson.errors import InvalidId


def get_or_404(model, id):
    try:
        obj = model.objects(id=ObjectId(id)).first()
    except (InvalidId, Exception):
        abort(404)
    if obj is None:
        abort(404)
    return obj
