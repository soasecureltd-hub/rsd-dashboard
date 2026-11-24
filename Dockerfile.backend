FROM python:3.11-slim

WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .

EXPOSE 8000

# Apply database migrations, then start the API.
CMD ["sh", "-c", "python -m app.migrate && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
