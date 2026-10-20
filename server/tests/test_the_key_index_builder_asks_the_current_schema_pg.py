# -*- coding: utf-8 -*-
"""총괄 10-20 ③: the business-key index migration asks the connection's current schema, not 'public' (production's
current schema is public). Section 1 (count, census, build) is gated end to end by
test_a_row_keyed_in_an_old_number_spelling_is_rekeyed_and_merged; this is section 2 - an index that repeats its
table's primary key is found in the scratch schema, and nothing of public's is."""
import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA                                            # noqa: E402
from migrations import add_business_key_unique_index as uq                     # noqa: E402

pytestmark = pytest.mark.pg
TABLE, INDEX = "uqs_pk_twice", "ix_uqs_pk_twice_row_id"


def test_an_index_repeating_the_primary_key_is_found_in_the_current_schema(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        conn.execute(text('CREATE TABLE "%s"."%s" (row_id text PRIMARY KEY, business_key_val text)'
                          % (PG_TEST_SCHEMA, TABLE)))
        conn.execute(text('CREATE INDEX "%s" ON "%s"."%s" (row_id)' % (INDEX, PG_TEST_SCHEMA, TABLE)))
    try:
        with pg_engine.connect() as conn:
            assert conn.execute(text("SELECT current_schema()")).scalar() == PG_TEST_SCHEMA
            found = uq.redundant_pk_indexes(conn)
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
    mine = [(r["table"], r["index"], r["droppable"]) for r in found if r["table"] == TABLE]
    assert mine == [(TABLE, INDEX, True)], found
