"""On PostgreSQL a write's lines go in a statement a page (lead 11-12): lines.insert_lines sends execute_values pages
of lines.INSERT_PAGE rows - never one a line, the round trip the overhaul cuts. Counted at the cursor (execute_values
runs below SQLAlchemy's statement events): 1,500 new rows, one line each, are two INSERT statements into t__lines.
The sqlite half of the count is test_set_based_write_path's."""
import pytest

from database import crud, lines, schemas
from tests.support import line_tables

pytestmark = pytest.mark.pg

TABLE = "pgqa_bk_table"
ROWS = 1500


class _Counting:
    """A cursor that counts the statements it sends, by their first words - the rest is the cursor's."""

    def __init__(self, cursor, said):
        self._cursor, self._said = cursor, said

    def execute(self, statement, *args, **kwargs):
        text = statement.decode() if isinstance(statement, bytes) else statement
        self._said.append(" ".join(text.split()[:3]))
        return self._cursor.execute(statement, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def test_a_write_of_new_rows_puts_its_lines_in_a_statement_a_page(pg_session, monkeypatch):
    import psycopg2.extras

    said = []
    real = psycopg2.extras.execute_values
    monkeypatch.setattr(psycopg2.extras, "execute_values",
                        lambda cursor, *a, **k: real(_Counting(cursor, said), *a, **k))
    line_tables.build(pg_session.get_bind(), TABLE)
    try:
        crud.apply_batch_updates(pg_session, TABLE, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(business_key_val="PN-%05d" % i, updates={"part_no": "PN-%05d" % i, "qty": i},
                                      source_name="f1.csv", updated_by="probe") for i in range(ROWS)]))
        pg_session.commit()
        into_lines = [s for s in said if s.startswith('INSERT INTO "%s"' % lines.lines_relation(TABLE))]
        assert len(into_lines) == -(-ROWS // lines.INSERT_PAGE) == 2, said
    finally:
        pg_session.rollback()                                  # its reads' lock goes before the DROP
        line_tables.drop(pg_session.get_bind(), TABLE)
