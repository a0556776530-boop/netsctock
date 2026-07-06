web: gunicorn --worker-class=gthread --workers=2 --threads=8 --timeout=60 --max-requests=1000 --max-requests-jitter=100 wsgi:app
