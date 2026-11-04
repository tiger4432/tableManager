# -*- coding: utf-8 -*-
"""A column a chain write offers and the target does not declare is dropped, counted and said - in the words a file
and a grid save say it (`crud.not_written_sentence`, lead 11-04: one event, one sentence). The rest of the row goes in.

ONE cell count per reason on the line (lead 11-04 ㄱ): a reason the sentence names is counted there - cells that
held a value, a blank lost nothing (총괄 629c678a8) - and the head says rows and reasons only; a reason the
sentence does not name (a system column) is counted in the head, its cells as dropped."""
import logging
import os
import sys

import pandas as pd
from sqlalchemy import text

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


def _discard_line(db, frame):
    items = mapper_sdk.df_to_updates(frame, TABLE, source_name=crud.CHAIN_SOURCE, updated_by="r_said")["updates"]
    seen = Lines()
    worker.logger.addHandler(seen)
    try:
        ok = worker.apply_chain_writes(db, "tx-said", {"name": "r_said", "target_table": TABLE}, 0,
                                       {TABLE: {"r_said"}}, {TABLE: items}, [], [], {TABLE: ["r_said"]}, [])
        db.commit()
    finally:
        worker.logger.removeHandler(seen)
    assert ok == (True, None)
    [line] = [line for line in seen.lines if "[Chain Write Discard]" in line]
    return line


def test_an_undeclared_column_is_said_in_the_files_sentence_and_the_row_goes_in(db_session):
    # two rows offer zz, one of them blank: two cells dropped, one of them held a value
    line = _discard_line(db_session, pd.DataFrame([{"part_no": "P0", "category": "c", "zz": "v"},
                                                   {"part_no": "P1", "category": "c", "zz": None}]))

    said = crud.not_written_sentence({crud.DROP_UNDECLARED_COLUMN: {"zz": 1}}, "Not written", {}, 2)
    assert said == ("Next: declare the undeclared columns in table_config.json. "
                    "Not written: undeclared_column zz=1 over 2 row(s).")
    assert line.endswith(" " + said), line
    assert "| 2 row(s) had cells dropped (undeclared_column, columns ['zz']); 0 row(s) were not created" in line, line
    assert "cell(s)" not in line.split(" Next: ")[0], line                  # the one cell count is the sentence's
    written = db_session.execute(text("SELECT part_no, category FROM inventory_master")).fetchall()
    assert sorted(map(tuple, written)) == [("P0", "c"), ("P1", "c")]       # the rest of each row went in


def test_a_reason_the_sentence_does_not_name_is_counted_in_the_head(db_session):
    """A system column the write path owns: no sentence names it, so the head counts its cells - blanks included,
    as dropped."""
    line = _discard_line(db_session, pd.DataFrame([{"part_no": "P0", "category": "c", "updated_by": "x"},
                                                   {"part_no": "P1", "category": "c", "updated_by": None}]))

    assert "| 2 row(s) had cells dropped (system_column, columns ['updated_by']; system_column 2 cell(s)); " in line, \
        line
    assert "Next:" not in line, line
