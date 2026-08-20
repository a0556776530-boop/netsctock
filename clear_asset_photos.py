"""Clear all asset photos from MongoDB."""
import os
from mongoengine import connect
from dotenv import load_dotenv

load_dotenv()
connect(host=os.environ['MONGO_URI'], db='netstock')

from app.models.asset import Asset

result = Asset.objects(__raw__={'photo': {'$exists': True, '$ne': None, '$ne': ''}}).update(unset__photo=1)
print(f'Cleared photos from {result} assets.')
