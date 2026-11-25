# RSD Development Guide

## Prerequisites
- Python 3.11 (matches the Docker image)
- Node.js 18+
- npm

## Initial Setup

**Backend:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
python -m app.migrate
```

**Frontend:**
```bash
cd frontend
npm install
```

## Running in Development

**Backend** (terminal 1):
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
API on `http://localhost:8000`, Swagger docs on `http://localhost:8000/docs`.

**Frontend** (terminal 2):
```bash
cd frontend
npm run dev
```
App on `http://localhost:5173`.

**Or with Docker:** `docker-compose up` (runs migrations, then both services).

## Project Structure Overview

### Backend (`/backend`)
- **app/main.py** - FastAPI entry point (CORS, Sentry, routers)
- **app/routes/** - `auth.py` and `risk.py` endpoint handlers
- **app/services/** - Scoring, key findings, ML threat estimates, PDF reports
- **app/models.py** - Database models
- **app/schemas.py** - Request/response validation
- **app/crud.py** - Database operations
- **app/db.py** - Engine and session
- **app/migrate.py** - Applies Alembic migrations
- **alembic/** - Migration scripts
- **tests/** - pytest suite

### Frontend (`/frontend`)
- **src/pages/** - Home, Dashboard, Login, Register
- **src/components/** - RiskForm, RiskResults, AIPredictions, AnomalyReport
- **src/context/** - Auth and assessment state
- **src/api/apiClient.js** - Axios client; attaches the JWT and signs out on 401
- **src/styles/** - Component stylesheets
- **src/App.jsx** - Root component and page switching

## Making Changes

### Adding a Backend Endpoint
1. Add the handler to a route file in `app/routes/`.
2. Define request/response schemas in `schemas.py`.
3. Protect it with `current_user=Depends(get_current_user)` and scope database
   queries to `current_user.id`.
4. Add tests in `backend/tests/`.
5. Try it at `http://localhost:8000/docs`.

Auth tokens must travel in the `Authorization` header. Never accept them as URL
query parameters: URLs end up in browser history and server logs.

### Adding a Frontend Component
1. Create the component in `src/components/` or `src/pages/`.
2. Add its CSS in `src/styles/`.
3. Call the backend through `riskAPI` / `authAPI` in `src/api/apiClient.js`.

### Database Schema Changes
Alembic is the only thing that creates or alters tables.

1. Update models in `app/models.py`.
2. Generate a migration:
   ```bash
   cd backend
   alembic revision --autogenerate -m "describe the change"
   ```
3. Review the generated file in `alembic/versions/` (autogenerate is not
   perfect; on SQLite use `op.batch_alter_table` for constraint changes).
4. Apply it: `python -m app.migrate`.
5. `pytest` - `test_migrations.py` fails if migrations and models disagree.

Migrations always use the app's `DATABASE_URL` (from the environment / `.env`),
for both `python -m app.migrate` and the `alembic` CLI. Double-check which
database it points at before running against production.

`camera_health` (left over from the old CV feature) is ignored by autogenerate
so a migration never drops it.

## API Communication

```javascript
import { riskAPI } from '../api/apiClient';

const { data: assessment } = await riskAPI.createAssessment(formData);
const { data: anomalies } = await riskAPI.detectAnomalies(assessment.id);
const { data: predictions } = await riskAPI.predict(assessment.id);
const pdf = await riskAPI.downloadReport(assessment.id); // blob response
```

## Testing

### Backend Testing
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Tests live in `backend/tests/` and run against a throwaway SQLite database and
ML model in a temp directory (set up in `tests/conftest.py`), so they never
touch `rsd.db` or your `.env`. The first run takes ~20s because the ML model is
trained once per session.

- `test_scoring.py` – scoring direction, weights, risk levels, risk velocity
- `test_findings.py` – key findings: no false alarms, severity bands, plain language, same-facility comparison
- `test_crud.py` – newest-first ordering and latest-prediction lookups
- `test_auth.py` – register / login / `/me`
- `test_risk_api.py` – endpoints end to end: ownership, anomalies, predictions, PDF report auth
- `test_migrations.py` – migrations match the models, legacy databases are adopted, FK behaviour
- `test_validation.py` – input validation and pagination bounds
- `test_ml.py` – threat estimates are graded, follow the documented rules, retrain when outdated
- `test_simulation.py` – What-If scenarios use real scoring and save nothing
- `test_security.py` – password/JWT compatibility and tampering, inactive accounts, login rate limiting

### Frontend
There is no frontend test setup yet. Check changes with `npm run build` and in
the browser.

## Deployment

See [README.md](README.md#deployment). In short: Render builds
`Dockerfile.backend` and `Dockerfile.frontend`; the backend container runs
`python -m app.migrate` before starting uvicorn.

## Troubleshooting

### Backend won't start
- `JWT_SECRET_KEY must be set...` - set it in `.env`, or use `DEBUG=True` locally.
- Port 8000 already in use.
- Re-run `pip install -r requirements.txt`.

### "no such table" errors
- Run `python -m app.migrate`.
- To reset a local SQLite database: delete `backend/rsd.db`, then run
  `python -m app.migrate`.

### API calls failing from the frontend
- Check the backend is running on port 8000.
- Check `ALLOWED_ORIGINS` in `.env` is comma-separated with no brackets or
  quotes, and includes the frontend's origin.
- Check the browser console / network tab.

### Frontend won't start
- Reinstall: `rm -rf node_modules && npm install`
- Check Node version (18+) and that port 5173 is free.

## Resources
- FastAPI: https://fastapi.tiangolo.com
- React: https://react.dev
- SQLAlchemy: https://docs.sqlalchemy.org
- Alembic: https://alembic.sqlalchemy.org
