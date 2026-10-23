# -*- coding: utf-8 -*-
"""총괄 8b487d2e6 · 6c6d76924 — the declaration form draws `decide.aggregations` as records, says the cells it does not
read, and draws no Korean (소유자 「체인 선언창에 aggregation 이 안 뜨는데」 -> 「ㄱ 으로 폼 그려」).

  ① each aggregation reaches the form as its record - "count" too, through the reader's one fold - and the reader
    reads the record as it read what the file holds (a form save round-trips to the same normal form)
  ② a cell at the top or under `derive` the product does not read is named, on a rule that is off too - a rule saved
    off is not said to run, a refused declaration and a flat rule name theirs too, the loader says a flat one once
  ③ the form's ADVANCED line about a role-frame mapper is English
"""
import json
import re

import pytest

import mapper_sdk
from chain import rule_shape
from chain.enrichment import config as enrichment_config

AGGREGATIONS = {"n": "count", "hi": {"fn": "max", "column": "t"},
                "names": {"fn": "unique_concat", "column": "w", "separator": "/"}}
TABLES = {"src_t": {"column_types": {c: "string" for c in ("lot", "wafer", "t", "w")}},
          "derived_t": {"business_key": "lot", "composite_key_source": ["lot"],
                        "column_types": {c: "string" for c in ("lot", "wafer", *AGGREGATIONS)}}}
DECIDE = {"name": "agg_form", "enabled": True, "on": {"table": "src_t"}, "into": {"table": "derived_t"},
          "derive": {"kind": "decide", "decide": {"key": ["lot"], "fields": ["wafer"],
                                                   "aggregations": AGGREGATIONS}}}


def test_the_route_hands_each_aggregation_as_its_record_and_the_reader_reads_it_the_same(tmp_path, monkeypatch):
    from ledger import admin

    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [DECIDE]}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))

    out = admin.chain_rule_raw_view("agg_form")
    drawn = out["declaration"]["derive"]["decide"]["aggregations"]

    # lead 5667ea0fe: "count" is drawn as its expression; max over a text column and another separator stay records
    assert drawn == {"n": "Count()", "hi": AGGREGATIONS["hi"], "names": AGGREGATIONS["names"]}
    assert json.loads(out["raw"]) == out["declaration"], "the form is drawn from raw (raw_registry_panel)"
    for name, spec in AGGREGATIONS.items():
        assert enrichment_config._parse_aggregation(name, drawn[name]) == \
            enrichment_config._parse_aggregation(name, spec), name


@pytest.mark.parametrize("enabled", [True, False])
def test_a_cell_the_product_does_not_read_is_named_at_the_top_and_under_derive(enabled):
    declaration = dict(DECIDE, enabled=enabled, aggregations={"x": "count"}, zzz_cell=1, __comment="prose",
                       derive=dict(DECIDE["derive"], aggregations={"y": "count"}))
    _rules, refusal, notes = rule_shape.expand_declaration(declaration, TABLES)
    tail = " The rule runs." if enabled else ""
    assert refusal is None
    assert "agg_form: top-level cell this product does not read — aggregations, zzz_cell.%s" % tail in notes, notes
    assert "agg_form: derive cell this product does not read — aggregations.%s" % tail in notes, notes


def _save(tmp_path, monkeypatch, entry):
    """The chain rule save door (`POST /admin/chain/rules/raw`'s function) into an empty rules file."""
    from database import crud
    from ledger import admin

    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    for table, table_entry in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, table, table_entry)
    return admin.save_chain_rule_raw(entry["name"], entry, admin.file_fingerprint(str(path)))


def test_the_save_answer_names_a_cell_the_product_does_not_read(tmp_path, monkeypatch):
    """The application lane measured it on 18766: the load line said it, the save answer did not."""
    out = _save(tmp_path, monkeypatch, dict(DECIDE, zzz_cell=1))

    assert "agg_form: top-level cell this product does not read — zzz_cell. The rule runs." in out["notes"], out


def test_a_rule_saved_off_is_not_said_to_run(tmp_path, monkeypatch):
    """총괄 10-11 ②: the save judged a copy switched on and answered that copy's notes."""
    out = _save(tmp_path, monkeypatch, dict(DECIDE, enabled=False, zzz_cell=1))

    assert out["notes"] == ["agg_form: enabled=false — nothing wakes it; a replay that names it runs it.",
                            "agg_form: top-level cell this product does not read — zzz_cell."], out


def test_a_refused_declaration_names_the_cells_it_does_not_read_too(tmp_path, monkeypatch):
    """총괄 10-11 ③: a refusal came back with no notes - the loader's line and the save's refusal say them too."""
    from fastapi import HTTPException

    declaration = dict(DECIDE, zzz_cell=1, derive={"kind": "no_such_kind"})
    _rules, refusal, notes = rule_shape.expand_declaration(declaration, TABLES)
    assert refusal and notes == ["agg_form: top-level cell this product does not read — zzz_cell."], (refusal, notes)
    with pytest.raises(HTTPException) as refused:
        _save(tmp_path, monkeypatch, declaration)
    assert refused.value.detail["message"] == refusal + " | " + notes[0], refused.value.detail


FLAT = {"name": "flat_r", "trigger_table": "src_t", "target_table": "derived_t", "mapper": "no_such_mapper",
        "zzz_arg": 1}


def test_a_flat_rule_names_its_flat_cells_and_the_loader_says_them_once(tmp_path, monkeypatch, caplog):
    """총괄 10-11 ③: a flat rule's notes were empty; the loader said its flat cells on a line of its own."""
    import logging

    from chain import ingestion_worker as worker

    said = "flat_r: 1 cell(s) still written flat — move them under 'params': zzz_arg"
    assert rule_shape.expand_declaration(dict(FLAT), TABLES) == ([FLAT], None, [said])
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [FLAT]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    with caplog.at_level(logging.WARNING):
        worker.load_chain_rules()
    assert [r.getMessage() for r in caplog.records].count("[ChainRules] " + said) == 1, caplog.text
    assert "still written flat" not in caplog.text.replace("[ChainRules] " + said, ""), caplog.text


def test_the_role_frame_mappers_line_is_english():
    other = mapper_sdk.mapper_candidates()["other"]
    said = [o["why"] for o in other if o.get("kind") == "ledger_roleframe"]
    assert said and not any(re.search("[가-힣]", why) for why in said), said
