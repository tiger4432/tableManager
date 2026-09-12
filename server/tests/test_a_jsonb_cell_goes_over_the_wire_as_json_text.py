# -*- coding: utf-8 -*-
"""S-190. A cell declared `string` reaches the client as text, whatever it is underneath.

🔴 MEASURED ON THE OWNER'S GRID: `ledger_events` showed 「[object Object]」 in `subject_keys`
and `object_payload`. Those columns are physically JSONB, psycopg2 returns a `dict`, the
route passed it through, and the grid -- which renders every cell as text -- called
`String(...)` on an object. The catalogue declares both columns `string`, so the wire was
disagreeing with the declaration.

⚠️ THE ROWS TSV WAS WORSE THAN WRONG, IT WAS UNPARSEABLE. `_row_cell` did `str(value)`,
which for a dict is Python's repr: single quotes, `True`, `None`. A reader pasting that into
anything expecting JSON gets a syntax error, and a reader who does not parse it sees a
value that merely LOOKS like JSON.

🔴 SO THE POINT OF THIS FILE IS THAT THE DOORS AGREE. The grid, the CSV export and the TSV
are three doors onto one value; the gate below feeds one dict to all three and asserts the
SAME string comes out. Three spellings of 「this value as text」 is how a cell copied from
one door stops matching the same cell copied from another.
"""
import json
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from utils.wire_format import wire_text                              # noqa: E402

#: The shape the owner actually saw rendered as 「[object Object]」 -- a ledger subject key.
#: Deliberately unsorted and non-ASCII, because both are what the spelling has to pin.
PAYLOAD = {"wafer": "W7", "lot": "SYN-001", "\ud55c\uae00": "\uac12"}


# ---------------------------------------------------------------------------
# The one function
# ---------------------------------------------------------------------------

def test_an_object_becomes_json_text_not_a_python_repr():
    text = wire_text(PAYLOAD)
    assert isinstance(text, str)
    assert json.loads(text) == PAYLOAD, "it must survive a round trip as JSON"
    assert "'" not in text, "a python repr quotes with apostrophes"


def test_the_spelling_is_fixed_so_two_doors_can_be_compared():
    """🔴 `sort_keys`, so the same object is the same TEXT however the dict was built --
    otherwise two doors could both be 「correct JSON」 and still not match."""
    other_order = {"\ud55c\uae00": "\uac12", "lot": "SYN-001", "wafer": "W7"}
    assert wire_text(PAYLOAD) == wire_text(other_order)
    assert wire_text(PAYLOAD) == (
        '{"lot":"SYN-001","wafer":"W7","\ud55c\uae00":"\uac12"}'), (
        "sorted keys, no spaces, and Korean stays readable rather than a numeric escape")


def test_a_list_is_json_too():
    assert wire_text([2, 1, {"a": 1}]) == '[2,1,{"a":1}]'


def test_everything_else_passes_through_byte_identical():
    """⚠️ THE REGRESSION LINE. This function may not be the reason a cell changes: numbers
    must stay numbers for the grid to sort them, and `None` must stay absent rather than
    become the string `"null"`."""
    for value in ("plain", "", 0, 1, 3.5, True, False, None, "{\"already\":\"text\"}"):
        assert wire_text(value) is value or wire_text(value) == value, value
        assert not isinstance(wire_text(value), str) or isinstance(value, str), value


# ---------------------------------------------------------------------------
# 🔴 The three doors agree
# ---------------------------------------------------------------------------

def test_the_rows_tsv_emits_the_same_string_as_the_grid():
    """The TSV additionally flattens tabs and newlines -- which JSON text has none of, so
    the two strings are equal rather than merely similar."""
    from ledger_api import ledger_subgraph as ls

    assert ls._row_cell(PAYLOAD) == wire_text(PAYLOAD)


def test_the_tsv_still_refuses_to_invent_a_column_or_a_row():
    """⚠️ The fold that was already there has to survive the new one."""
    from ledger_api import ledger_subgraph as ls

    assert "\t" not in ls._row_cell("a\tb")
    assert "\n" not in ls._row_cell("a\nb")
    assert ls._row_cell(None) == "" and ls._row_cell(True) == "true"


def test_the_csv_export_and_the_grid_read_one_function():
    """⛔ SCORED ON THE SOURCE, because the export is a streaming generator and the sample
    sizer beside it is a THIRD copy of the same expression -- this file's own history is
    that the sizer diverged from the stream and the progress bar ran past 100%."""
    import inspect

    import main

    body = inspect.getsource(main.export_table_csv)
    assert body.count("wire_text(r)") == 2, (
        "both the sample sizer and the streamed rows must fold the same way")
    merge = inspect.getsource(main.fetch_and_merge_metadata)
    assert merge.count("wire_text(") == 2, "the view arm and the ordinary arm"


# ---------------------------------------------------------------------------
# Through the route
# ---------------------------------------------------------------------------

# ⚠️ `client` COMES FROM `conftest`, and that matters: its `db_session` SEEDS
# `raw_table_1`, so the route below has rows to read. A bare `TestClient(main.app)` reaches
# an empty database, every relation answers with no data, and the gate passes while checking
# NOTHING -- which is how it read `checked == 0` when first written.


def test_a_declared_string_cell_never_reaches_the_client_as_an_object(client):
    """🔴 THE GATE AT THE DOOR THE OWNER USED. Every cell of every declared-`string` column
    must be a scalar on the wire -- an object there is what the grid renders as
    「[object Object]」, and it cannot tell that from a value."""
    from database import crud

    checked = 0
    for name, entry in crud.TABLE_CONFIG.items():
        types = (entry or {}).get("column_types") or {}
        strings = [c for c, t in types.items() if t == "string"]
        if not strings:
            continue
        response = client.get("/tables/%s/data?limit=3" % name)
        # ⚠️ A RELATION THIS ENVIRONMENT CANNOT READ IS SKIPPED, NOT FAILED. The test
        # database is SQLite and the ledger relations are PostgreSQL objects, so `/data`
        # answers 500 for them here -- which says nothing about the fold. `checked` below
        # is what stops that skip from turning the whole gate vacuous, and the view arm is
        # scored on its source by `test_the_csv_export_and_the_grid_read_one_function`.
        if response.status_code != 200:
            continue
        body = response.json()
        if not isinstance(body, dict) or not body.get("data"):
            continue
        for row in body["data"]:
            for col in strings:
                cell = (row.get("data") or {}).get(col)
                if cell is None:
                    continue
                value = cell.get("value") if isinstance(cell, dict) else cell
                assert not isinstance(value, (dict, list)), (name, col, type(value))
                checked += 1
    assert checked, "no declared string cell was reached - this gate proved nothing"
