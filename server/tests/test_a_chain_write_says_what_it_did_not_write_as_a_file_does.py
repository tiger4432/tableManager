# -*- coding: utf-8 -*-
"""A column a chain write offers and the target does not declare is dropped, counted and said - in the words a file
and a grid save say it (`crud.not_written_sentence`, lead 11-04: one event, one sentence). The rest of the row goes in."""
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import mapper_sdk  # noqa: E402
from chain import ingestion_worker as worker  # noqa: E402
from database import crud  # noqa: E402

TABLE = "inventory_master"


class Lines(logging.Handler):
    """On the worker's own logger - caplog does not see every logger of this stack (C 11-04)."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def test_an_undeclared_column_is_said_in_the_files_sentence_and_the_row_goes_in(db_session):
    items = mapper_sdk.df_to_updates(
        pd.DataFrame([{"part_no": "P%d" % i, "category": "c", "zz": "v"} for i in range(2)]), TABLE,
        source_name=crud.CHAIN_SOURCE, updated_by="r_said")["updates"]
    seen = Lines()
    worker.logger.addHandler(seen)
    try:
        ok = worker.apply_chain_writes(db_session, "tx-said", {"name": "r_said", "target_table": TABLE}, 0,
                                       {TABLE: {"r_said"}}, {TABLE: items}, [], [], {TABLE: ["r_said"]}, [])
        db_session.commit()
    finally:
        worker.logger.removeHandler(seen)

    assert ok == (True, None)
    said = crud.not_written_sentence({crud.DROP_UNDECLARED_COLUMN: {"zz": 2}}, "Not written", {}, 2)
    assert said == ("Next: declare the undeclared columns in table_config.json. "
                    "Not written: undeclared_column zz=2 over 2 row(s).")
    [line] = [line for line in seen.lines if "[Chain Write Discard]" in line]
    assert line.endswith(" " + said), line
    from sqlalchemy import text
    written = db_session.execute(text("SELECT part_no, category FROM inventory_master")).fetchall()
    assert sorted(map(tuple, written)) == [("P0", "c"), ("P1", "c")]          # the rest of each row went in
