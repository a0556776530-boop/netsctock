"""
One-time migration: move file_data from chat_messages to chat_files collection.
Run once: python cleanup_file_data.py
"""
import os
os.environ.setdefault('DATABASE_URL', 'sqlite:///inventory.db')

from app import create_app
app = create_app()

with app.app_context():
    from mongoengine.connection import get_db
    db = get_db('default')

    msgs     = db['chat_messages']
    files    = db['chat_files']
    migrated = 0
    cleaned  = 0

    for doc in msgs.find({'file_data': {'$exists': True, '$ne': None}}):
        file_data = doc.get('file_data')
        if not file_data:
            continue

        # Save to chat_files
        result = files.insert_one({
            'data':        file_data,
            'name':        doc.get('file_name', ''),
            'file_type':   doc.get('file_type', 'file'),
            'size':        doc.get('file_size', 0),
            'uploaded_at': doc.get('timestamp'),
        })

        # Update message with file_id, remove file_data
        msgs.update_one(
            {'_id': doc['_id']},
            {
                '$set':   {'file_id': str(result.inserted_id)},
                '$unset': {'file_data': ''},
            }
        )
        migrated += 1

    # Clean any remaining file_data fields (nulls / empty strings)
    result = msgs.update_many(
        {'file_data': {'$exists': True}},
        {'$unset': {'file_data': ''}}
    )
    cleaned = result.modified_count

    print(f'Migrated: {migrated} files to chat_files collection')
    print(f'Cleaned:  {cleaned} leftover file_data fields')
    print('Done.')
