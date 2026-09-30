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

#: the next action comes first - a file's status field keeps 500 characters (d4a949a8c ③)
NEXT = "Next: declare the undeclared columns in table_config.json. "

EXPECTED = {
    "all": ("FAILED", str(crud.NothingWritten(TABLE, {crud.DROP_UNDECLARED_COLUMN: ["lot", "qty"]}))),
    "part": ("SUCCESS", "%sNot written: undeclared_column extra=1 over 1 row(s)." % NEXT),
    "none": ("SUCCESS", None),
    "undeclared_only": ("SUCCESS", "%sNot written: undeclared_column extra=0 over 1 row(s)." % NEXT),
    "spaces": ("SUCCESS", "%sNot written: undeclared_column extra=0 over 2 row(s)." % NEXT),
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
    said = str(crud.NothingWritten("t_probe", {crud.DROP_UNDECLARED_COLUMN: ["qty", "lot"]}))
    assert said == (NEXT + "Nothing was written to 't_probe' - dropped: undeclared_column lot, qty.")
    # both reasons: both next actions first, in one sentence (d4a949a8c ③)
    said = str(crud.NothingWritten("t_probe", {crud.DROP_UNDECLARED_COLUMN: ["x"],
                                               crud.DROP_UNMAPPED_COLUMN: ["y"]}))
    assert said == ("Next: declare the undeclared columns in table_config.json; reload or restart "
                    "so this process holds the unmapped columns, then Retry the file. Nothing was "
                    "written to 't_probe' - dropped: undeclared_column x; unmapped_column y.")
