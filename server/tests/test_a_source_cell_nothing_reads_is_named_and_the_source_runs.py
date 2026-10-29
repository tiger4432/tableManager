# -*- coding: utf-8 -*-
"""An external source's cell nothing reads is named, never refused (lead 10-29: `stability_interval_seconds` written at
an entry's top instead of under `options` was dropped without a word, and the table read 0 rows). One sentence for
it and a chain rule's (`validation.unread_said`):

  seat                          what it says
  validate (spec "unread")      top-level · options cells nothing reads; an option at the top: «… is read under options.»
                                «The source runs.» unless switched off; comment cells («__») and a clean entry: nothing
  voids_json                    its own options (max_file_mb, unit) are read; with no parser they are named
  the watcher's registration    one WARNING line each, the source stands
  GET /admin/file-ingestion/tables   each source line's "unread"; raws: []
  check_external_sources.py     the same sentence under the source
  rule_shape                    its four spellings are this one sentence
"""
import logging

import pytest

import directory_watcher
import validation
from chain import rule_shape

TABLES = {"ta": {"business_key": "k", "column_types": {"k": "string"}, "display_columns": ["k"]},
          "void_obs": {"business_key": "k", "column_types": {"k": "string"}, "display_columns": ["k"]}}
TOP = ("external_sources[0]: top-level cell this product does not read \u2014 stability_interval_seconds, zz. "
       "stability_interval_seconds is read under options. The source runs.")


def _entries(tmp_path):
    for name in ("a", "b", "c", "d", "e"):
        (tmp_path / name).mkdir(exist_ok=True)
    return [
        {"path": str(tmp_path / "a"), "table_name": "ta", "stability_interval_seconds": 5, "zz": 1, "__note": "x",
         "options": {"glob": "*.json", "__why": "y"}},
        {"path": str(tmp_path / "b"), "table_name": "ta", "enabled": True, "recursive": True, "max_depth": 2,
         "options": {"filename": "voids.json"}},
        {"path": str(tmp_path / "c"), "table_name": "ta", "enabled": False, "options": {"q": 1}},
        {"path": str(tmp_path / "d"), "table_name": "void_obs", "parser": "voids_json",
         "options": {"max_file_mb": 3, "unit": "um"}},
        {"path": str(tmp_path / "e"), "table_name": "void_obs", "options": {"max_file_mb": 3, "unit": "um"}},
    ]


def test_each_seat_of_an_entry_names_what_nothing_reads_and_the_source_stands(tmp_path):
    (tmp_path / "ws").mkdir()
    specs, errors = directory_watcher.validate_external_source_specs(
        {"external_sources": _entries(tmp_path)}, TABLES, str(tmp_path / "ws"))
    assert errors == [] and len(specs) == 5
    clean = _entries(tmp_path)[1].keys() | _entries(tmp_path)[3].keys()
    assert set(directory_watcher.SOURCE_CELLS) <= clean, "CANARY: every cell an entry is read by, written clean"
    by_root = {spec["root"].rsplit("\\", 1)[-1].rsplit("/", 1)[-1]: spec for spec in specs}
    assert by_root["a"]["unread"] == [TOP]
    assert directory_watcher.STABILITY_INTERVAL_OPTION not in by_root["a"]["options"], "still not read - only named"
    assert "unread" not in by_root["b"] and "unread" not in by_root["d"], "a clean entry: its spec as before"
    assert by_root["c"]["unread"] == ["external_sources[2]: options cell this product does not read \u2014 q."]
    assert by_root["e"]["unread"] == [
        "external_sources[4]: options cell this product does not read \u2014 max_file_mb, unit. The source runs."]


def test_the_watcher_says_it_once_per_registration_and_the_source_stands(tmp_path, monkeypatch, caplog):
    from database import crud

    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", TABLES)
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings",
                        lambda: {"external_sources": _entries(tmp_path)[:1]})
    (tmp_path / "ingestion_workspace").mkdir()
    watcher = directory_watcher.WorkspaceWatcher(str(tmp_path / "ingestion_workspace"))
    with caplog.at_level(logging.WARNING):
        watcher.discover_and_watch()
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("External source config")]
    assert said == ["External source config: " + TOP] and len(watcher.external_targets) == 1


def test_the_file_page_carries_it_on_the_source_line(client, monkeypatch):
    from database import crud
    from ingestion import reread

    spec = {"table_name": next(iter(crud.TABLE_CONFIG)), "root": r"D:\share", "unread": [TOP]}
    monkeypatch.setattr(reread, "validated_sources", lambda: ({}, [spec]))
    for _ in range(50):
        said = client.get("/admin/file-ingestion/tables").json()
        if not said["progress"]["counting"]:
            break
    lines = {(t["table_name"], s["source"]): s["unread"] for t in said["data"] for s in t["sources"]}
    assert lines[(spec["table_name"], r"D:\share")] == [TOP] and lines[(spec["table_name"], "raws")] == []


def test_the_check_script_prints_it_under_the_source(tmp_path, monkeypatch, capsys):
    from parsers import directory_watcher as module
    from scripts import check_external_sources

    monkeypatch.setattr(module, "load_global_table_config", lambda: TABLES)
    monkeypatch.setattr(module, "load_ingestion_settings", lambda: {"external_sources": _entries(tmp_path)[:1]})
    assert check_external_sources.main() == 0
    assert "      ! " + TOP in capsys.readouterr().out.splitlines()


@pytest.mark.parametrize("declaration, sentence", [
    ({"name": "a", "on": {"table": "s"}, "into": {"table": "t"}, "zzz": 1,
      "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}], "take": ["v"], "bogus": 1}}},
     validation.unread_said("a", "derive.join", ["bogus"],
                            " The rule runs; check the spelling if it was meant to do something.")),
    ({"name": "a", "on": {"table": "s"}, "into": {"table": "t"}, "zzz": 1,
      "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}], "take": ["v"]}}},
     validation.unread_said("a", "top-level", ["zzz"], " The rule runs.")),
    ({"name": "r", "on": {"table": "s"}, "into": {"table": "t"}, "layout": "x",
      "derive": {"kind": "report", "report": {}}},
     validation.unread_said("r", "top-level", ["layout"], " layout is read under derive.report.")),
    ({"name": "o", "enabled": False, "on": {"table": "s"}, "into": {"table": "t"},
      "derive": {"kind": "decide", "decide": {"key": ["lot"], "fields": ["w"], "zz": 1}}},
     validation.unread_said("o", "derive.decide", ["zz"])),
    ({"name": "d", "on": {"table": "s"}, "into": {"table": "t"},
      "derive": {"kind": "decide", "decide": {"key": ["lot"], "fields": ["w"], "zz": 1}}},
     validation.unread_said("d", "derive.decide", ["zz"], " The rule runs.")),
])
def test_a_chain_rule_says_the_same_sentence(declaration, sentence):
    _rules, _refusal, notes = rule_shape.expand_declaration(declaration)
    assert sentence in notes, notes
