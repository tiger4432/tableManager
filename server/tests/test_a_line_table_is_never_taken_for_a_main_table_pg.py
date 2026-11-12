"""A line table carries t's columns; the seats that listed tables by catalogue or column took it for a main table
(lead 11-12). They ask lines.base_tables now: the ledger source picker does not offer t__lines to declare, the
missing-key report does not count it. A declared name ending in the lines suffix is refused. (The schema audit and
the manifest read 'public' by name, so a scratch schema cannot show them - the census test holds their seat.)"""
import contextlib
import io

import pytest
from sqlalchemy import MetaData, Table, text

from database import lines
from database.models import sql_type_of

pytestmark = pytest.mark.pg

CFG = {"column_types": {"lot": "string"}}
T = "ltm_t"


@pytest.fixture()
def built(pg_engine):
    with pg_engine.begin() as c:
        Table(T, MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(c)
        c.execute(text('CREATE TABLE "%s" (line_id bigint PRIMARY KEY, row_id text, business_key_val text)'
                       % lines.lines_relation(T)))
        c.execute(text('INSERT INTO "%s" VALUES (1, \'r1\', NULL)' % lines.lines_relation(T)))
    yield
    with pg_engine.begin() as c:
        c.execute(text('DROP TABLE IF EXISTS "%s"' % lines.lines_relation(T)))
        c.execute(text('DROP TABLE IF EXISTS "%s"' % T))


def test_base_tables_leaves_line_tables_out_unless_asked(pg_engine, built):
    with pg_engine.connect() as c:
        assert T in lines.base_tables(c) and lines.lines_relation(T) not in lines.base_tables(c)
        assert lines.lines_relation(T) in lines.base_tables(c, lines=True)


def test_the_ledger_source_picker_offers_no_line_table_to_declare(pg_engine, built):
    from sqlalchemy.orm import Session

    from ledger.admin import relations_view

    with Session(bind=pg_engine) as db:
        offered = [u["name"] for u in relations_view(db, query="ltm_")["undeclared"]]
    assert offered == [T]


def test_the_missing_key_report_does_not_count_a_line_table(pg_engine, built):
    from scripts import check_missing_business_key as report

    said = io.StringIO()
    with pg_engine.connect() as c, contextlib.redirect_stdout(said):
        report._report(c, {}, None)
    assert lines.lines_relation(T) not in said.getvalue()      # it holds a line of no key: before, «== ltm_t__lines»


def test_a_declared_name_ending_in_the_lines_suffix_is_refused_naming_it():
    said = lines.table_name_refusal("lot" + lines.LINES_SUFFIX)
    assert said and ("lot" + lines.LINES_SUFFIX) in said and "rename" in said
    assert lines.table_name_refusal("lot") is None and not lines.is_line_table(lines.LINES_SUFFIX)
