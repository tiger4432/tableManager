# -*- coding: utf-8 -*-
"""Owner 11-08 1ㄱ 2ㄱ 3ㄱ 4ㄱ: the grid's own colours are colour rules every table has - the look table's declaration
(`grid_look.DECLARED`: a person's cell a warn line, a merge's a danger fill, a model's an accent line), under rows of
look_table «*» (an administrator's) and each table's own rows, folded in one place (`grid_look.fold`).

  layer    declared < «*» < the table; the same look_key: a higher layer's written cells cover, its blank role turns
           the rule off there (kept, `under` the role it turned off); a table's key alone needs its role
  writers  every cell's from the page read's priority_source - the line its current line names (cell-source overhaul;
           test_a_cells_winner_is_the_line_its_current_line_names)
  access   a «*» row is an administrator's - the refusal says so; a table's row of a default is its editors'
"""
import pytest

import grid_look
from admin import access
from database import models
from test_a_cell_looks_by_its_colour_rules_and_hand_paint import LOOKS, TABLE, _look, _read, grid  # noqa: F401
from test_a_deny_on_an_edit_by_table_wins_before_the_table_it_names import signed  # noqa: F401 - the fixture


def _c(position, role, written_by=None, shape=None, when=None):
    return grid_look._cells(position, role, when, None, written_by, shape)


def test_the_fold_matrix():
    declared = {"p": _c("0", "warn", "person", "line"), "m": _c("01", "danger", "merge")}
    every = {"p": _c("5", "ok"), "x": _c("02", "accent", "ai", "line")}
    table = {"p": _c("9", "", when="[value] > 1"), "m": _c("9", "accent"), "t": _c("8", "warn", "chain"),
             "gone": _c("7", "")}
    got = {r["id"]: (r["position"], r["role"], r["written_by"], r["shape"], r["when"], r["every"], r["under"])
           for r in grid_look.fold(declared, every, table)}
    assert got == {
        "p": ("0", None, "person", "line", "[value] > 1", True, "ok"),    # «*» covered warn with ok, the table turns it off
        "m": ("01", "accent", "merge", None, None, True, "danger"),       # the table's role covers; its place is the rule's
        "x": ("02", "accent", "ai", "line", None, True, None),            # a «*» rule of its own: every table's
        "t": ("8", "warn", "chain", None, None, False, None),             # the table's own
    }, got                                                               # «gone»: the table's alone, no role - no rule
    assert [r["id"] for r in grid_look.fold(declared, every, table)] == ["p", "m", "x", "t"], "by position"


def test_every_table_reads_them_and_a_table_covers_or_turns_one_off(grid, db_session):
    client, _ids = grid
    looks = models.DYNAMIC_TABLES[LOOKS]
    try:
        rules = {r["id"]: r for r in _read(client)["looks"]["rules"]}
        assert {k: (r["role"], r["written_by"], r["shape"], r["every"]) for k, r in rules.items()} == {
            "written-by-person": ("warn", "person", "line", True), "written-by-merge": ("danger", "merge", "fill", True),
            "written-by-ai": ("accent", "ai", "line", True)}
        answer = client.put("/tables/%s/data/updates" % LOOKS, json={"updates": [{"updates": {
            "look_table": grid_look.EVERY, "look_axis": "rule", "look_key": "written-by-merge", "role": "ok"},
            "updated_by": "probe"}]})
        assert answer.status_code == 200, answer.text
        _look(client, "rule", "written-by-person", role="")
        rules = {r["id"]: r for r in _read(client)["looks"]["rules"]}
        assert (rules["written-by-merge"]["role"], rules["written-by-merge"]["written_by"]) == ("ok", "merge"), \
            "an administrator's «*» row covers the declaration on every table"
        assert (rules["written-by-person"]["role"], rules["written-by-person"]["under"]) == (None, "warn"), \
            "the table's blank role: off here, «On here» gives warn back"
    finally:
        db_session.rollback()
        db_session.query(looks).filter(looks.look_table == grid_look.EVERY).delete()
        db_session.commit()


def test_a_rule_of_every_table_is_an_administrators(signed, db_session):
    client, who = signed
    looks = models.DYNAMIC_TABLES[LOOKS]

    def put(table, role):
        return client.put("/tables/%s/data/updates" % LOOKS, json={"updates": [{"updates": {
            "look_table": table, "look_axis": "rule", "look_key": "written-by-person", "role": role},
            "updated_by": "web_client"}]})
    try:
        who["name"] = "kim"
        refused = put(grid_look.EVERY, "ok")
        assert (refused.status_code, refused.json().get("detail")) == (403, access.ADMINS_ONLY % ("kim", grid_look.EVERY))
        assert put(TABLE, "").status_code == 200, "off on a table kim may edit"
        who["name"] = "boss"
        assert put(grid_look.EVERY, "ok").status_code == 200
    finally:
        db_session.rollback()
        db_session.query(looks).filter(looks.look_table == grid_look.EVERY).delete()
        db_session.commit()
