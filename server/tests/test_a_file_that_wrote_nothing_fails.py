# -*- coding: utf-8 -*-
"""총괄 8e54a261b ② · f0578f20a — a file whose every value was dropped for undeclared columns FAILS
with one sentence; a file that dropped PART of itself stays a success and its record names the
drop. Three files x the two parser paths (standard · a custom script in the workspace), and the
two paths answer with the same status and the same string."""
import pytest

from database import crud
from tests.test_ingestion_checkpoint import TABLE, _ingestion_logs, _write, p2_env  # noqa: F401

CUSTOM = """from pipeline_base import BasePipelineParser


class PassThroughParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path):
        return file_path.lower().endswith('.csv')

    def process_dataframe(self, df):
        return df
"""

FILES = {
    "all": "lot,qty\nL1,5\n",
    "part": "part_no,category,stock_qty,extra\nP-1,Cap,1,x\n",
    "none": "part_no,category,stock_qty\nP-1,Cap,1\n",
    # 총괄 69aad666e C: a row blank in its declared cells is skipped on both paths before its
    # undeclared value is counted, and a cell of spaces is blank on both.
    "undeclared_only": "part_no,category,stock_qty,extra\nP-1,Cap,1,\n,,,x\n",
    "spaces": "part_no,category,stock_qty,extra\nP-1,Cap,1,  \nP-2,Cap,2,  \n",
}

EXPECTED = {
    "all": ("FAILED", str(crud.NothingWritten(TABLE, ["lot", "qty"]))),
    "part": ("SUCCESS", "Dropped 1 undeclared column(s) over 1 row(s): extra=1 "
                        "(name=non-blank values discarded)."),
    "none": ("SUCCESS", None),
    "undeclared_only": ("SUCCESS", "Dropped 1 undeclared column(s) over 1 row(s): extra=0 "
                                   "(name=non-blank values discarded)."),
    "spaces": ("SUCCESS", "Dropped 1 undeclared column(s) over 2 row(s): extra=0 "
                          "(name=non-blank values discarded)."),
}


@pytest.mark.parametrize("path", ["standard", "custom"])
@pytest.mark.parametrize("kind", ["all", "part", "none", "undeclared_only", "spaces"])
def test_status_and_sentence(p2_env, path, kind):
    ws, handler = p2_env["make_handler"]()
    if path == "custom":
        (ws / "scripts").mkdir()
        _write(ws / "scripts" / "pass_through.py", CUSTOM)
    handler.process_with_retry(_write(ws / "raws" / ("%s.csv" % kind), FILES[kind]), delay=0.01)

    [log] = _ingestion_logs(p2_env)
    assert (log.status, log.error_message) == EXPECTED[kind]


def test_the_sentence_names_the_columns_and_the_next_step():
    said = str(crud.NothingWritten("t_probe", ["qty", "lot"]))
    assert said == ("No column of this file is declared on 't_probe', so nothing was written - "
                    "dropped lot, qty. Declare the columns on the table, or send the file to the "
                    "table that declares them.")
