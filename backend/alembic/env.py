import sys
import os
from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

# Add backend dir to path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.db import Base
from app import models  # noqa: F401 — registers all ORM models with Base.metadata

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False: don't silence app loggers when migrations
    # run in-process (app.migrate, tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Tables that exist in the database but are intentionally not modelled here.
# camera_health belongs to the (now separate) CV app; never autogenerate a drop.
IGNORED_TABLES = {"camera_health"}


def _database_url() -> str:
    # Always the app's DATABASE_URL (env / .env), never a URL hard-coded in
    # alembic.ini. Callers may override via config.attributes["database_url"].
    # (Kept out of config options on purpose: configparser would choke on the
    # '%' in URL-encoded passwords.)
    return config.attributes.get("database_url") or settings.DATABASE_URL


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name in IGNORED_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
