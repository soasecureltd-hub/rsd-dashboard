"""Alembic migrations: schema parity with the models and adoption of legacy DBs."""
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app import migrate
from app.db import Base

IGNORED_TABLES = {"camera_health"}  # mirrors alembic/env.py


def _url(tmp_path, name="m.db"):
    return f"sqlite:///{(tmp_path / name).as_posix()}"


def _with_engine(url, fn):
    engine = create_engine(url)
    try:
        return fn(engine)
    finally:
        engine.dispose()


def _revision(url):
    def q(engine):
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return _with_engine(url, q)


def _prediction_fks(url):
    return _with_engine(url, lambda e: inspect(e).get_foreign_keys("ai_predictions"))


def _make_legacy_db(url, revision):
    """Simulate a DB built by the old create_all() startup: tables, no Alembic history."""
    command.upgrade(migrate._alembic_config(url), revision)

    def drop_version(engine):
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE alembic_version"))
    _with_engine(url, drop_version)


def test_fresh_database_matches_models(tmp_path):
    url = _url(tmp_path)
    migrate.run(url)
    assert _revision(url) == "003"

    def diff(engine):
        include = lambda obj, name, type_, *a: not (type_ == "table" and name in IGNORED_TABLES)
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"include_object": include})
            return compare_metadata(ctx, Base.metadata)
    assert _with_engine(url, diff) == []


def test_prediction_foreign_key_created(tmp_path):
    url = _url(tmp_path)
    migrate.run(url)
    fks = _prediction_fks(url)
    assert len(fks) == 1
    assert fks[0]["referred_table"] == "assessments"
    assert fks[0]["constrained_columns"] == ["assessment_id"]
    assert fks[0]["options"].get("ondelete") == "CASCADE"


def test_run_is_idempotent(tmp_path):
    url = _url(tmp_path)
    migrate.run(url)
    migrate.run(url)
    assert _revision(url) == "003"


def test_legacy_database_adopted_and_orphans_unlinked(tmp_path):
    url = _url(tmp_path)
    _make_legacy_db(url, "002")

    def seed(engine):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@x.com', 'h')"))
            conn.execute(text("INSERT INTO assessments (id, user_id, input_data) VALUES (1, 1, '{}')"))
            conn.execute(text("INSERT INTO ai_predictions (id, assessment_id, input_features) VALUES (1, 1, '{}')"))
            conn.execute(text("INSERT INTO ai_predictions (id, assessment_id, input_features) VALUES (2, 999, '{}')"))
    _with_engine(url, seed)

    assert migrate.detect_legacy_revision(url) == "002"
    migrate.run(url)
    assert _revision(url) == "003"
    assert len(_prediction_fks(url)) == 1

    def rows(engine):
        with engine.connect() as conn:
            return dict(conn.execute(text("SELECT id, assessment_id FROM ai_predictions")).all())
    # Valid link kept; orphan unlinked (not deleted); user data untouched.
    assert _with_engine(url, rows) == {1: 1, 2: None}


def test_pre_ownership_legacy_database_gets_user_id(tmp_path):
    url = _url(tmp_path)
    _make_legacy_db(url, "001")
    assert migrate.detect_legacy_revision(url) == "001"
    migrate.run(url)
    assert _revision(url) == "003"
    columns = _with_engine(url, lambda e: {c["name"] for c in inspect(e).get_columns("assessments")})
    assert "user_id" in columns


def test_empty_database_not_treated_as_legacy(tmp_path):
    assert migrate.detect_legacy_revision(_url(tmp_path)) is None


def test_downgrade_removes_foreign_key(tmp_path):
    url = _url(tmp_path)
    migrate.run(url)
    command.downgrade(migrate._alembic_config(url), "002")
    assert _prediction_fks(url) == []
