# NetStock — Flask + MongoDB inventory app
# Build: docker build -t netstock:<tag> .
# Run:   docker run -p 8080:8080 -e MONGO_URI=... -e SECRET_KEY=... netstock:<tag>

FROM python:3.11-slim AS base

# Runtime OS deps: none required — bcrypt/pymongo ship manylinux wheels.
# tini gives the app process proper signal handling (SIGTERM on pod termination)
# instead of gunicorn running as PID 1 directly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY wsgi.py .

# Local-disk upload path used by the purchases BOM feature (app/routes/purchases.py).
# Mount a volume here in Kubernetes if uploads must survive pod restarts/rescheduling.
RUN mkdir -p /app/app/uploads/bom

# Run as non-root
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

ENTRYPOINT ["tini", "--"]
CMD ["gunicorn", \
     "--bind=0.0.0.0:8080", \
     "--worker-class=gthread", \
     "--workers=2", \
     "--threads=8", \
     "--timeout=60", \
     "--max-requests=1000", \
     "--max-requests-jitter=100", \
     "wsgi:app"]
