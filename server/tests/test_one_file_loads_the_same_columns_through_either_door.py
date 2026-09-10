# -*- coding: utf-8 -*-
"""같은 표에 «적재 가능 컬럼» 필터가 하나다 (S-119, 판정 09-10 12:20).

🔴 WHAT WAS MEASURED. The file watcher filtered incoming columns by `display_columns` and
dropped what was not there BEFORE `crud` ever saw the row; `crud` filtered by
`column_types`. A column declared in one and not the other therefore LANDED through the
API and was silently DISCARDED through the watcher - measured on `dt_log`, whose `dt_job`
the row generator writes through the API and the watcher drops. Same table, same fact, two
answers depending on which door it came through (깔끔 ④).

🔴 THE RULING: LOADING ASKS "DOES THIS EXIST", WHICH IS `column_types`. A column can exist
and be written without being on a screen; a screen cannot show a column that does not
exist. `display_columns` keeps the showing axis - `GET /tables/{t}/schema` and the grid -
and no longer decides what may be written.

⛔ AND THE GUARANTEE IS STRUCTURAL, NOT A PROMISE. The standard parser's F5 note already
said the validator's set must equal the loader's; what it could not do was keep two files
reading two different keys in agreement. One function is what makes the two equal.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                              # noqa: E402
from parsers import directory_watcher, std_parser                      # noqa: E402


#: A declaration whose two axes DISAGREE - the shape the defect lived in. `dt_extra` is
#: declared to exist and is deliberately not on a screen.
DIVERGENT = {
    "business_key": "k",
    "display_columns": ["k", "shown"],
    "column_types": {"k": "string", "shown": "string", "dt_extra": "string"},
}


def test_the_loadable_set_is_the_columns_declared_to_exist():
    assert crud.loadable_columns(DIVERGENT) == ("k", "shown", "dt_extra")


def test_a_column_that_is_not_on_a_screen_is_still_loadable():
    """🔴 THE WHOLE RULING IN ONE CASE. `dt_extra` exists and is not displayed; before
    this it was writable through one door and dropped at the other."""
    assert "dt_extra" in crud.loadable_columns(DIVERGENT)
    assert "dt_extra" not in DIVERGENT["display_columns"]


def test_an_undeclared_column_is_still_not_loadable():
    """⚠️ THE AXIS MOVED, IT DID NOT OPEN. A column nothing declares is dropped exactly as
    it was - widening the filter to "anything the file carries" would let a typo create a
    column-shaped hole that no declaration knows about."""
    assert "typo" not in crud.loadable_columns(DIVERGENT)


def test_an_empty_declaration_still_loads_nothing():
    """Unchanged on both sides, and now said about the same declaration."""
    assert crud.loadable_columns({}) == ()
    assert crud.loadable_columns({"display_columns": ["k"]}) == ()
    assert crud.loadable_columns(None) == ()


def test_both_doors_ask_the_one_function():
    """🔴 착지는 배선이 아니다 — a canonical answer nobody calls is not a canonical answer.

    Asserted on the source of the two filter seats, because what can go wrong here is one
    of them being edited back to reading a config key directly, and that is what the text
    sees. The behavioural halves are the two cases below.
    """
    import inspect

    upsert = inspect.getsource(directory_watcher.IngestionHandler._send_to_upsert)
    assert "crud.loadable_columns(table_info)" in upsert, upsert[:400]
    assert 'table_info.get("display_columns"' not in upsert

    header = inspect.getsource(std_parser._build_header_map)
    assert "crud.loadable_columns(table_info)" in header, header[:400]
    assert 'table_info.get("display_columns"' not in header


def test_the_write_path_accepts_exactly_that_set():
    """The `crud` half, read off the seat that decides it rather than off a config key."""
    import inspect

    body = inspect.getsource(crud.apply_row_update_internal)
    assert "loadable_columns(config)" in body, body[:400]


def test_the_parser_and_the_loader_agree_on_a_divergent_declaration():
    """🔴 THE GATE THE RULING NAMED: one file, either door, the SAME column set.

    The standard parser decides which of a file's headers it will map; the loader decides
    which of a mapped row's keys it will write. Before this they answered from different
    keys, so a file carrying `dt_extra` mapped it and then lost it. Now both answers come
    from one call, and this case pins that they are the same SET rather than merely both
    non-empty - a divergent declaration is the only input that can tell the two apart.
    """
    header_map = std_parser._build_header_map(
        ["k", "shown", "dt_extra", "typo"], DIVERGENT, "t", "some_file.csv")

    mapped = {name for name in header_map if name is not None}

    assert mapped == set(crud.loadable_columns(DIVERGENT))
    assert "dt_extra" in mapped, "the parser dropped a column the loader would have taken"
    assert "typo" not in mapped
