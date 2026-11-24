"""Bring the database schema up to date with Alembic.

    python -m app.migrate

Run this before starting the API (the Docker images do it automatically).
Alembic is the only thing that creates or changes tables; the app itself no
longer calls create_all().

Databases created by the old create_all() startup have tables but no
alembic_version row. Running `upgrade head` on them would try to re-create
existing tables, so they are first stamped at the revision their schema
already matches, then upgraded normally.
"""
import logging
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import settings

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = database_url
    return cfg


def detect_legacy_revision(database_url: str) -> Optional[str]:
    """Return the revision an untracked create_all() database matches, else None."""
    engine = create_engine(database_url)
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        if "alembic_version" in tables or "users" not in tables:
            return None  # already tracked, or empty → normal upgrade
        columns = {c["name"] for c in insp.get_columns("assessments")} if "assessments" in tables else set()
        return "002" if "user_id" in columns else "001"
    finally:
        engine.dispose()


def run(database_url: Optional[str] = None) -> None:
    url = database_url or settings.DATABASE_URL
    cfg = _alembic_config(url)

    legacy = detect_legacy_revision(url)
    if legacy:
        logger.warning(
            "Existing schema without Alembic history detected; stamping revision %s", legacy
        )
        command.stamp(cfg, legacy)

    command.upgrade(cfg, "head")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run()
