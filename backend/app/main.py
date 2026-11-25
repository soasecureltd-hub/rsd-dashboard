"""FastAPI main application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes import risk
from app.routes import auth as auth_routes

# Sentry (only if DSN is configured)
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.2,
        environment="development" if settings.DEBUG else "production",
    )

# Schema is managed by Alembic: run `python -m app.migrate` before starting.

app = FastAPI(title=settings.API_TITLE, version=settings.API_VERSION, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Lets the cross-origin frontend read the PDF filename on report downloads.
    expose_headers=["Content-Disposition"],
)

app.include_router(auth_routes.router)
app.include_router(risk.router)


@app.get("/")
def read_root():
    return {
        "message": "Risk-Security Diagnostic API",
        "version": settings.API_VERSION,
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
