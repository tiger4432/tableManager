# -*- coding: utf-8 -*-
"""총괄 26a5ef836 (소유자 「ㄱ으로」) — 문법이 모르는 `derive` 종류는 이름 대어 거절한다.

🔴 THE DEFECT, FOUND WHILE WIDENING THE KIND SEAT (a42f8779a). `derive.kind: "banana"` was not
   refused: `expand_declaration` stood it as an EMPTY rule - no refusal, no mapper, and no `derive`
   left for any seat to read - so the rules list called it 「mapper」.

🔴 ONE JUDGE, TWO CALLERS (S-244). The loader and the save gate both ask `expand_declaration`, so
   the save is refused at the moment of saving and a line already in the file stands on the list
   as declared-only with the sentence. The allowed words are read from `DECLARED_KINDS`.

⚠️ A declaration that writes NO kind but names its `derive` cell (`{"join": {...}}`) is read by
   `from_declaration` and passes - that normalisation is untouched.
"""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import rule_shape                                        # noqa: E402
from database import crud                                           # noqa: E402
from ledger import admin                                            # noqa: E402

SRC, DST = "k26a5_src", "k26a5_derived"
BANANA = {"name": "k26a5_banana", "on": {"table": SRC}, "into": {"table": DST},
          "derive": {"kind": "banana"}}
NO_KIND = {"name": "k26a5_nokind", "on": {"table": SRC}, "into": {"table": DST}, "derive": {}}
#: names no kind, names its cell - `from_declaration` reads 「decide」 and it stands
NAMED_CELL = {"name": "k26a5_named", "on": {"table": SRC}, "into": {"table": DST},
              "derive": {"decide": {"key": ["job"], "fields": ["grade"]}}}
TABLES = {
    SRC: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string"}, "display_columns": ["job"]},
    DST: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "grade": "string"},
          "display_columns": ["job", "grade"]},
}


@pytest.fixture(name="tables")
def fixture_tables():
    crud.TABLE_CONFIG.update(TABLES)
    try:
        yield
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def test_an_unknown_kind_is_refused_and_the_sentence_names_the_allowed_words(tables):
    stood, refusal, _notes = rule_shape.expand_declaration(BANANA, crud.TABLE_CONFIG)
    assert stood == [], "an unknown kind must not stand an empty rule"
    assert "unknown derive kind 'banana'" in refusal
    assert all(kind in refusal for kind in rule_shape.DECLARED_KINDS)


def test_a_derive_that_names_no_kind_and_no_cell_is_refused_too(tables):
    stood, refusal, _notes = rule_shape.expand_declaration(NO_KIND, crud.TABLE_CONFIG)
    assert stood == [] and "derive names no kind" in refusal


def test_a_kind_read_off_its_cell_still_passes(tables):
    """⚠️ 음성 대조 — `from_declaration` 의 정규화가 거절에 걸리면 이 줄이 빨개집니다."""
    stood, refusal, _notes = rule_shape.expand_declaration(NAMED_CELL, crud.TABLE_CONFIG)
    assert refusal is None and stood, (refusal, stood)


def test_the_three_kinds_stand_as_they_did(tables):
    decide = dict(NAMED_CELL, name="k26a5_decide", derive={"kind": "decide", **NAMED_CELL["derive"]})
    mapper = {"name": "k26a5_mapper", "on": {"table": SRC}, "into": {"table": DST},
              "derive": {"kind": "mapper", "mapper": {"mapper_module": "m", "mapper_function": "f"}}}
    join = {"name": "k26a5_join", "on": {"table": SRC}, "into": {"table": DST},
            "derive": {"kind": "join", "join": {"on": {"job": "job"}}}}
    for declaration in (decide, mapper, join):
        stood, refusal, _notes = rule_shape.expand_declaration(declaration, crud.TABLE_CONFIG)
        assert refusal is None and stood, (declaration["name"], refusal)


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch, tables):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [BANANA]}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "backup"))
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    import paths
    real_config_path = paths.config_path
    monkeypatch.setattr(paths, "config_path",
                        lambda name: str(path) if name == "chain_rules.json" else real_config_path(name))
    return path


def test_the_save_gate_refuses_it_by_name(rules_file):
    with pytest.raises(Exception) as raised:
        admin.save_chain_rule_raw("k26a5_new", dict(BANANA, name="k26a5_new"),
                                  admin.file_fingerprint(str(rules_file)))
    detail = raised.value.detail
    assert detail["code"] == "declaration_refused", detail
    assert "unknown derive kind 'banana'" in json.dumps(detail, ensure_ascii=False)


def test_a_line_already_in_the_file_stands_on_the_list_with_its_reason(rules_file):
    import main

    rows = {row["name"]: row for row in main.get_chain_rules()["data"]}
    row = rows["k26a5_banana"]
    assert row["rule_state"] == event_constants.RULE_STATE_DECLARED_ONLY
    assert "unknown derive kind 'banana'" in (row.get("rule_state_detail") or "")
    assert row["kind"] == rule_shape.UNKNOWN_KIND
