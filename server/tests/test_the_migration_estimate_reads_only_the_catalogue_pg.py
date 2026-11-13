"""copy_layers_to_lines --estimate (lead 11-12 (가)): a table's layers come from the database's own statistics -
pg_class.reltuples and pg_stats' common values of cell_sources.table_name - and no statement reads cell_sources."""
import re

import pytest
from sqlalchemy import event, text

from database.models import CellSource
from scripts import copy_layers_to_lines as script

pytestmark = pytest.mark.pg


@pytest.fixture()
def layers(pg_engine):
    CellSource.__table__.create(pg_engine, checkfirst=True)
    with pg_engine.begin() as c:
        c.execute(text("DELETE FROM cell_sources"))
        for table, n in (("est_a", 3000), ("est_b", 1000)):
            c.execute(text("INSERT INTO cell_sources (table_name, row_id, column_name, source_name, value) "
                           "SELECT :t, 'r' || g, 'c', 'f.csv', to_json(g) FROM generate_series(1, :n) g"),
                      {"t": table, "n": n})
        c.execute(text("ANALYZE cell_sources"))
    yield
    with pg_engine.begin() as c:
        c.execute(text("DELETE FROM cell_sources"))


def test_the_estimate_counts_each_tables_layers_from_the_statistics_alone(pg_engine, layers):
    seen = []
    listen = lambda conn, cursor, statement, *a: seen.append(statement)        # noqa: E731
    event.listen(pg_engine, "before_cursor_execute", listen)
    try:
        per, rest, total = script.estimate(pg_engine)
    finally:
        event.remove(pg_engine, "before_cursor_execute", listen)
    assert (per, rest, total) == ({"est_a": 3000, "est_b": 1000}, 0, 4000)
    assert seen and all("pg_class" in s or "pg_stats" in s for s in seen), seen
    assert not [s for s in seen if re.search(r'(?i)\b(from|join)\s+"?cell_sources\b', s)], seen
