# -*- coding: utf-8 -*-
"""`key.columns` and `group_by` (flat) / `limits.group_by` (unified) hold LISTS of column names (총괄 77793123e, 소유자
10-20 「1 ㅇㅇ」). Drawn as one value, the form saved «lot» as text: `chain.synthesis` read it letter by letter
(['l', 'o', 't']), matched no join key and built no unique index - without an error; and `group_by` as text is
refused by the loader (bad_group_by), so the form could not save one at all.

  the skeleton the declaration window gets draws the three cells as rows (list nodes)
  key.columns written as text is refused by name, in either grammar - by the judge the save gate, the loader and
     synthesis share (`rule_shape.expand_declaration`)
  key.columns as a list over the join's right key -> the unique index is named over that real key
  a group key as a list passes the save gate's judgement in either grammar
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                # noqa: E402
from chain import join_key_index, rule_shape, synthesis              # noqa: E402
from database import crud                                            # noqa: E402

COLS = {"lot": "string", "slot": "string", "dt_job": "string", "dt_lot": "string", "dt_slot": "string"}
TABLES = {"k77_log": {"business_key": "k", "composite_key_source": ["lot", "slot"], "column_types": dict(COLS)},
          "k77_inventory": {"business_key": "k", "composite_key_source": ["dt_job"], "column_types": dict(COLS)}}
LIST = {"kind": "map", "keyed_by": "index", "member": "column", "of": {"kind": "leaf", "hint": "free"}}


def _join(columns):
    return {"name": "k77_join", "enabled": True,
            "on": {"table": "k77_inventory"},
            "derive": {"kind": "join", "join": {"on": [{"left": "dt_job", "right": "dt_job"}],
                                                "take": ["dt_lot", "dt_slot"]}},
            "into": {"table": "k77_log"},
            "key": {"unique": True, "columns": columns}}


def _field(record, key):
    return next(f["node"] for f in record["fields"] if f["key"] == key)


@pytest.fixture(autouse=True)
def _fresh():
    synthesis.reset_right_key_cache()
    yield
    synthesis.reset_right_key_cache()


def _live(monkeypatch, declarations):
    from chain import ingestion_worker

    monkeypatch.setattr(ingestion_worker, "read_rules_document",
                        lambda *a, **kw: {"exists": True, "error": None, "rules": list(declarations)})


def test_the_window_draws_the_three_cells_as_rows():
    from ledger import admin

    skeleton = admin.chain_rule_raw_view()["skeleton"]           # what the declaration window is handed
    flat, unified = skeleton["root"], skeleton["unified_root"]
    assert _field(_field(flat, "key"), "columns") == LIST
    assert _field(_field(unified, "key"), "columns") == LIST
    assert _field(flat, "group_by") == LIST
    assert _field(_field(unified, "limits"), "group_by") == LIST


@pytest.mark.parametrize("grammar", ["unified", "flat"])
def test_key_columns_written_as_text_is_refused_by_name(grammar):
    declaration = _join("dt_job") if grammar == "unified" else {
        "name": "k77_flat", "trigger_table": "k77_log", "target_table": "k77_log", "mapper": "m",
        "key": {"unique": True, "columns": "dt_job"}}

    stood, refusal, _notes = rule_shape.expand_declaration(declaration, TABLES)

    assert stood == [] and refusal == '%s: key.columns must be a list, e.g. ["dt_job"]' % declaration["name"], refusal


def test_text_key_columns_names_no_index_and_a_list_names_it_over_the_real_key(monkeypatch):
    _live(monkeypatch, [_join("dt_job")])
    assert synthesis.declared_unique_index_names(known_tables=TABLES) == set()   # refused, never read as letters

    _live(monkeypatch, [_join(["dt_job"])])
    assert synthesis.declared_unique_index_names(known_tables=TABLES) == {
        join_key_index.required_index_name("k77_inventory", ["dt_job"], [None])}


@pytest.mark.parametrize("grammar", ["unified", "flat"])
def test_a_group_key_as_a_list_passes_the_save_gates_judgement(grammar, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, "k77_log", TABLES["k77_log"])
    declaration = ({"name": "k77_grouped", "on": {"table": "k77_log", "columns": ["lot"]},
                    "derive": {"kind": "mapper", "mapper": {"mapper": "m"}}, "into": {"table": "k77_log"},
                    "limits": {"group_by": ["lot", "slot"]}} if grammar == "unified" else
                   {"name": "k77_grouped", "trigger_table": "k77_log", "target_table": "k77_log", "mapper": "m",
                    "group_by": ["lot", "slot"]})

    stood, refusal, _notes = rule_shape.expand_declaration(declaration, TABLES)
    assert refusal is None and len(stood) == 1
    assert stood[0]["group_by"] == ["lot", "slot"]
    assert chain_bindings.rule_refusals(stood[0], "rule", mapper_resolvable=lambda name: True,
                                        derived_tables=()) == []
