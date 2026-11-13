"""The migration pre-check reports declared-vs-stored type differences (lead 11-10): a column declared datetime but
stored as text is listed and migrates as text."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import line_migration


@pytest.fixture()
def db():
    session = sessionmaker(bind=create_engine("sqlite://"))()
    session.execute(text("CREATE TABLE ev (row_id VARCHAR PRIMARY KEY, business_key_val VARCHAR, created_at TIMESTAMP, "
                         "updated_at TIMESTAMP, event_time VARCHAR, qty FLOAT, seen TIMESTAMP, lot VARCHAR)"))
    yield session
    session.close()


def test_a_datetime_declared_text_stored_column_is_reported(db):
    cfg = {"ev": {"column_types": {"event_time": "datetime", "qty": "number", "seen": "datetime", "lot": "string"}}}
    found = line_migration.declared_vs_stored(db, cfg)
    assert found == [("ev", "event_time", "datetime", "string")]
    line = line_migration.report_line(found)
    assert "ev.event_time (declared datetime, stored string)" in line and "separate step" in line


def test_nothing_to_report_says_nothing(db):
    cfg = {"ev": {"column_types": {"qty": "number", "lot": "string"}}}
    assert line_migration.report_line(line_migration.declared_vs_stored(db, cfg)) is None
