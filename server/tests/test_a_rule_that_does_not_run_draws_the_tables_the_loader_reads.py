# -*- coding: utf-8 -*-
"""A declaration on the rules list that does not run - off, or refused - carries the tables the loader reads in it,
through the grammar's own translation, as a running row does (lead 11-10). Before, it was the raw declaration: a
unified one wrote only on/into, so the screen's Data Flow drew «- → -», and a flat target_table written beside into.table
(box «aaa») showed a table the loader never reads."""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import crud                                           # noqa: E402

SRC, DST, OTHER = "q11_src", "q11_dst", "q11_other"

#: off, and it would stand were it on
OFF = {"name": "q11_off", "enabled": False, "on": {"table": SRC}, "into": {"table": DST},
       "derive": {"kind": "decide", "decide": {"key": ["job"], "fields": ["grade"]}}}
#: off, flat trigger_table/target_table written beside into.table - two answers to «which table it writes»
TWO = {"name": "q11_two", "enabled": False, "trigger_table": OTHER, "target_table": OTHER,
       "into": {"table": DST}, "derive": {"join": {"right_table": SRC}}}
#: on, and refused by the grammar
REFUSED = {"name": "q11_refused", "on": {"table": SRC}, "into": {"table": DST}, "derive": {"kind": "nonsense"}}

TABLES = {name: {"business_key": "job", "composite_key_source": ["job"],
                 "column_types": {"job": "string", "grade": "string"}, "display_columns": ["job"]}
          for name in (SRC, DST, OTHER)}


@pytest.fixture(name="rows")
def fixture_rows(tmp_path, monkeypatch):
    chain_file = tmp_path / "chain_rules.json"
    chain_file.write_text(json.dumps({"rules": [OFF, TWO, REFUSED]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))
    for name, cfg in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, cfg)
    import paths
    real_config_path = paths.config_path
    monkeypatch.setattr(paths, "config_path",
                        lambda name: str(chain_file) if name == "chain_rules.json" else real_config_path(name))
    import main

    answer = main.get_chain_rules()
    assert answer["status"] == "success", answer
    return {row["name"]: row for row in answer["data"]}


@pytest.mark.parametrize("name", ["q11_off", "q11_refused"])
def test_a_unified_rule_that_does_not_run_says_its_source_and_its_target(rows, name):
    row = rows[name]
    assert row["rule_state"] == event_constants.RULE_STATE_DECLARED_ONLY
    assert (row.get("trigger_table"), row.get("target_table")) == (SRC, DST), row


def test_a_flat_table_beside_into_is_not_drawn_the_loader_reads_into(rows):
    row = rows["q11_two"]
    assert row.get("target_table") == DST, row
    assert row.get("trigger_table") != OTHER, "the loader does not read a flat trigger_table in a unified declaration"


def test_the_row_keeps_its_name_its_state_and_its_kind(rows):
    assert rows["q11_off"]["enabled"] is False and rows["q11_off"]["kind"] == "decide"
    assert rows["q11_refused"]["kind"] != "mapper", rows["q11_refused"]["kind"]
