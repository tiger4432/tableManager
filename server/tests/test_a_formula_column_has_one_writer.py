# -*- coding: utf-8 -*-
"""A formula column has one writer (lead 10-28 ㄴ): a rule that writes a column a formula computes is refused by name,
the formula's own rule aside - two writers of one cell, one losing in silence, is what this stops. One judge
(`formula.second_writers`, what a rule writes is `rule_run.columns_a_rule_writes`'), four readers:

    reader                     gate
    the loader                 the other rule is refused and said; the formula runs
    the rule save door         saving either side is refused with the sentence; an unrelated save is not
    the formula preview        a column a loaded rule writes is refused
    the rules list             the refused rule is declared_only with the sentence
"""
import json

import pytest

from chain import formula
from chain import ingestion_worker as worker
from database import crud
from ledger import admin

TABLES = {"fx": {"business_key": "k", "composite_key_source": ["k"],
                 "column_types": {"k": "string", "a": "number", "c": "number"}},
          "src": {"business_key": "k", "composite_key_source": ["k"],
                  "column_types": {"k": "string", "v": "number", "w": "number"}}}
SENTENCE = "copy v writes fx.c, which formula fx.c computes - a formula column has one writer"


def _copy(into="c", name="copy v"):
    return {"name": name, "enabled": True, "on": {"table": "src"}, "into": {"table": "fx"},
            "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}],
                                                "take": [{"into": into, "from": "v"}]}}}


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch, caplog):
    import mapper_sdk

    for name, config in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, config)
    mapper_sdk.discover()
    path = tmp_path / "chain_rules.json"
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "bk"))
    worker.forget_loaded_chain_rules()
    yield path
    worker.forget_loaded_chain_rules()


def _write(path, *declarations):
    path.write_text(json.dumps({"rules": list(declarations)}), encoding="utf-8")
    worker.forget_loaded_chain_rules()


def test_the_loader_refuses_the_second_writer_by_name_and_runs_the_formula(rules_file, caplog):
    _write(rules_file, formula.to_declaration("fx", "c", "=[a]*2"), _copy(), _copy(into="a", name="copy a"))
    names = [rule.get("name") for rule in worker.load_chain_rules()]
    assert "formula fx.c" in names and "copy a" in names and "copy v" not in names
    assert "copy v refused: formula_column - " + SENTENCE in caplog.text


def test_saving_either_writer_is_refused_with_the_sentence_and_an_unrelated_save_is_not(rules_file):
    _write(rules_file, formula.to_declaration("fx", "c", "=[a]*2"))
    with pytest.raises(Exception) as refused:
        admin.save_chain_rule_raw("copy v", _copy(), admin.file_fingerprint(str(rules_file)))
    assert SENTENCE in str(getattr(refused.value, "detail", refused.value))
    _write(rules_file, _copy())
    with pytest.raises(Exception) as refused:
        admin.save_chain_rule_raw("formula fx.c", formula.to_declaration("fx", "c", "=[a]*2"),
                                  admin.file_fingerprint(str(rules_file)))
    assert SENTENCE in str(getattr(refused.value, "detail", refused.value))
    _write(rules_file, formula.to_declaration("fx", "c", "=[a]*2"), _copy())
    assert admin.save_chain_rule_raw("copy a", _copy(into="a", name="copy a"),
                                     admin.file_fingerprint(str(rules_file)))["ok"], "not about this rule"


def test_a_preview_refuses_a_column_a_loaded_rule_writes(rules_file):
    _write(rules_file, _copy())
    with pytest.raises(formula.FormulaRefused) as refused:
        formula.preview(None, "fx", "c", "=[a]*2")
    assert str(refused.value) == SENTENCE


def test_the_rules_list_says_the_refused_rule_with_the_sentence(rules_file, monkeypatch):
    import main
    from chain import control

    monkeypatch.setattr("paths.config_path", lambda name: str(rules_file))
    monkeypatch.setattr(control, "rules_off", lambda: {})
    _write(rules_file, formula.to_declaration("fx", "c", "=[a]*2"), _copy())
    listed = {row["name"]: row for row in main.get_chain_rules(db=None)["data"]}
    assert listed["copy v"]["rule_state"] == "declared_only" and listed["copy v"]["rule_state_detail"] == "formula_column - " + SENTENCE
    assert listed["formula fx.c"]["rule_state"] == "running"
