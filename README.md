# Risk-Security Diagnostic (RSD) - FastAPI + React

A web application for facility security risk assessment. Users sign in, fill in
a security questionnaire, and get a weighted risk score, ML threat predictions,
plain-language key findings and a downloadable PDF report.

> The camera / computer-vision monitoring features now live in a separate app
> and are no longer part of this repository.

## Project Structure

```
RSD/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI application
│   │   ├── config.py               # Settings (env / .env)
│   │   ├── db.py                   # Engine + session
│   │   ├── migrate.py              # Runs Alembic migrations (python -m app.migrate)
│   │   ├── models.py               # SQLAlchemy ORM models
│   │   ├── schemas.py              # Pydantic request/response schemas
│   │   ├── crud.py                 # Database operations
│   │   ├── dependencies.py         # JWT auth dependency
│   │   ├── routes/
│   │   │   ├── auth.py             # Register / login / me
│   │   │   └── risk.py             # Assessments, anomalies, predictions, PDF report
│   │   └── services/
│   │       ├── risk_service.py     # Scoring, risk velocity
│   │       ├── findings_service.py # Key findings in plain language
│   │       ├── ml_service.py       # Threat prediction model
│   │       └── report_service.py   # PDF report generation
│   ├── alembic/                    # Database migrations
│   ├── tests/                      # pytest suite
│   ├── requirements.txt
│   ├── requirements-dev.txt        # + test dependencies
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── api/apiClient.js        # Axios client (attaches JWT)
│   │   ├── context/                # AuthContext, AssessmentContext
│   │   ├── components/             # RiskForm, RiskResults, AIPredictions, AnomalyReport
│   │   ├── pages/                  # Home, Dashboard, Login, Register
│   │   └── styles/
│   ├── package.json
│   └── vite.config.js
│
├── Dockerfile.backend / Dockerfile.frontend
├── docker-compose.yml
└── render.yaml                     # Render deployment
```

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
python -m app.migrate          # create / update the database schema
python -m uvicorn app.main:app --reload
```

API: `http://localhost:8000` · Swagger docs: `http://localhost:8000/docs`

`.env.example` sets `DEBUG=True`, so a temporary JWT secret is generated if
`JWT_SECRET_KEY` is empty (tokens stop working after a restart). Set a real one
to stay signed in across restarts.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: `http://localhost:5173`

### Docker

```bash
docker-compose up
```

The backend container runs migrations automatically before starting.

## Features

### Risk Assessment
- Questionnaire across five weighted categories: Physical Security (25%),
  Access Control (30%), Personnel (15%), Incident History (20%),
  Emergency Preparedness (10%).
- Every score is risk-oriented: **higher = riskier**. Qualitative answers map
  Poor=90, Fair=60, Good=30, Excellent=10. "Higher is better" numbers
  (CCTV coverage, CCTV functionality, guard adequacy, response time quality)
  are inverted (100 - value) so that a better answer lowers risk.
- Risk levels: Low (≤40), Moderate (≤60), High (≤80), Critical (>80).

### AI Threat Estimates
- Estimated likelihood of unauthorized access, insider threat, emergency
  failure and perimeter breach (scikit-learn RandomForest).
- **There is no real incident data yet.** The model is trained on synthetic
  facilities labelled by expert rules (`THREAT_DRIVERS` in
  `services/ml_service.py`): each threat has a risk index over the category
  scores, mapped to a probability by a logistic curve. Treat the outputs as
  relative indicators, not measured probabilities; the UI and PDF say so.
- **What-If scenarios:** edit any answer of an assessment and see the
  recalculated overall score and threat estimates next to the current ones,
  using the real scoring and model. Nothing is saved.
- Trained on first use and cached to `MODEL_PATH` with a version number, so
  changing the model (`MODEL_VERSION`) retrains automatically.

### Key Findings
- Every answer is placed on the scoring's 0-100 risk scale. **Urgent** = "Poor"
  or ≥ 80, **Needs attention** = "Fair" or 60-79, **Strength** = "Excellent" or
  ≤ 15. Only risk-raising answers are ever flagged; strong answers are strengths.
- Each finding is plain language: headline, why it matters, what to do
  (text in `services/findings_service.py`).
- Change since the previous assessment **of the same facility**.
- A statistical "unusual combination" check (IsolationForest over category
  scores; the facility's own history once it has 5+ earlier assessments) is
  shown only as a detail under "How this was calculated".

### History & Trends
- History page listing all your assessments (newest first) with a risk-score
  trend chart: one line per facility, with a facility filter.
- "Change since previous" compares against the previous assessment of the
  same facility. Any past assessment can be reopened in the dashboard.

### PDF Report
- Downloadable report with scores, weaknesses, recommendations and the latest
  AI prediction.

### Accounts & Security
- Email + password hashed with argon2id (`argon2-cffi`), HS256 JWT bearer
  tokens (`PyJWT`). Each user only sees their own assessments; deactivated
  accounts (`is_active = false`) lose access immediately.
- Failed logins are rate limited (`app/rate_limit.py`): 5 per account per IP,
  30 per IP, 50 per account, in a 15-minute window, answered with `429` and
  `Retry-After`. Counters are in memory, per process.
- Behind a proxy, uvicorn runs with `--proxy-headers`; set `FORWARDED_ALLOW_IPS`
  to the proxy's address (`render.yaml` uses `*`) so limits apply to real
  client IPs.
- CI runs `pip-audit` on the backend requirements.

## API Endpoints

All `/api/risk/*` endpoints require `Authorization: Bearer <token>`.

### Auth
- `POST /api/auth/register` - Create an account
- `POST /api/auth/login` - OAuth2 form login (used by Swagger)
- `POST /api/auth/login/json` - JSON login (used by the frontend)
- `GET /api/auth/me` - Current user

### Risk
- `POST /api/risk/assess` - Create and score an assessment
- `GET /api/risk/assess/{id}` - Get an assessment
- `GET /api/risk/assessments?skip=&limit=` - List your assessments, newest first (`limit` 1–100)
- `POST /api/risk/assess/{id}/simulate` - What-If: score an edited copy of the answers against the saved ones (nothing is saved)
- `GET /api/risk/assess/{id}/findings` - Key findings, strengths, change since the last assessment of the facility
- `POST /api/risk/predict/{id}` - Run ML threat predictions (stores a new prediction)
- `GET /api/risk/predict/{id}` - Latest stored prediction, without re-running the model (404 if none)
- `GET /api/risk/assess/{id}/report` - Download the PDF report

## Configuration

### Backend (`backend/.env`)
See `backend/.env.example` for the full list.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite locally; Postgres (Supabase) in production. URL-encode special characters in the password. |
| `DEBUG` | `True` only for local development. |
| `JWT_SECRET_KEY` | Required (32+ chars) when `DEBUG=False`. |
| `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` | Token settings. |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins, no brackets or quotes. |
| `MODEL_PATH` | Where the trained ML model is cached. |
| `SENTRY_DSN` | Optional error monitoring. |

### Frontend
| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Backend API base URL (default `http://localhost:8000/api`). Baked in at build time. |

## Database

Alembic owns the schema; the app never creates tables itself.

- Apply migrations: `cd backend && python -m app.migrate`
- After changing `app/models.py`: `alembic revision --autogenerate -m "describe change"`,
  review the generated file, then run the migrations.

`python -m app.migrate` also adopts databases created by older versions of the
app (which used `create_all()` and have no Alembic history) by stamping them at
the matching revision before upgrading.

### Models
- **User** - `email`, `hashed_password`, `full_name`, `is_active`, `created_at`
- **Assessment** - owner `user_id`, `facility_name`, raw `input_data` (JSON),
  `category_scores`, `contributions`, `overall_score`, `risk_level`, timestamps
- **AIPrediction** - `assessment_id` (foreign key, cascades on delete),
  `input_features`, the four threat probabilities, `shap_values`, `created_at`

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

See [DEVELOPMENT.md](DEVELOPMENT.md#testing) for what is covered.

## Deployment

Frontend on **Vercel** (`frontend/vercel.json`), backend on **Render**
(`render.yaml`, Docker), database on **Supabase**. Step-by-step guide:
[DEPLOY.md](DEPLOY.md). Migrations run on every backend container start.

`Dockerfile.frontend` (nginx) remains for running the frontend as a container
(e.g. `docker-compose up`).

## Dependencies

- **Backend:** FastAPI, SQLAlchemy, Alembic, Pydantic, scikit-learn, NumPy,
  joblib, fpdf, PyJWT, argon2-cffi, Sentry SDK
- **Frontend:** React 18, Vite, Axios, Recharts, Lucide React, Sentry
