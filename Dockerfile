FROM python:3.11-slim

WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .

EXPOSE 8000

# Apply database migrations, then start the API.
# --proxy-headers: trust X-Forwarded-For from the hosts in FORWARDED_ALLOW_IPS
# (set by the platform, e.g. render.yaml) so login rate limiting sees the real
# client IP rather than the load balancer's.
CMD ["sh", "-c", "python -m app.migrate && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
