# -*- coding: utf-8 -*-
"""A yes/no cell holds true or false (총괄 de64fb0f9 · 872f6cb6b · 36b465139).

`"false"` is truthy and `0` is not, so every reader that guessed read one of them wrong - a
chain rule's `allow_retraction: "false"` turned removal ON. One judge
(`validation.flag_refusal`) and one sentence; what a seat does with it is the seat's own:

  declaration   chain rules (flat · unified), collectors, ledger bundle  -> does not stand
  setting       auto-confirm switches, map_push_ok, notation write        -> default + the sentence
  entry         map preset routing, paint lock                            -> not used + the sentence

Absent is never judged: each seat keeps what absence meant before.
"""
import json
import logging
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                               # noqa: E402
import map_overlay                                                  # noqa: E402
import notation_norm                                                # noqa: E402
import validation                                                   # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import rule_shape                                        # noqa: E402
from chain.enrichment import candidates                             # noqa: E402
from database import crud                                           # noqa: E402
from ledger import admin                                            # noqa: E402
from ledger.setup_bundle import LedgerSetupBundle                   # noqa: E402
from maps import preset_routing                                     # noqa: E402
from parsers import directory_watcher                               # noqa: E402
from test_external_source_watcher import TABLES as VOID_TABLES      # noqa: E402
from test_external_source_watcher import _specs                     # noqa: E402
from test_ledger_setup_bundle import logical_bundle                 # noqa: E402
from test_ledger_setup_registry import (                            # noqa: E402
    snapshot_compile_errors, trusted_implementations)

NOT_FLAGS = [0, 1, None, "false", "true"]
SRC, DST = "yn_src", "yn_dst"
TABLES = {
    SRC: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string"}, "display_columns": ["job"]},
    DST: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "grade": "string"},
          "display_columns": ["job", "grade"]},
}
FLAT = {"name": "yn_flat", "trigger_table": SRC, "target_table": DST,
        "mapper_module": "mappers.x", "mapper_function": "build"}
UNIFIED = {"name": "yn_unified", "on": {"table": SRC}, "into": {"table": DST},
           "derive": {"kind": "decide", "decide": {"key": ["job"], "fields": ["grade"]}}}


def _said(value):
    return json.dumps(value)


@pytest.fixture(name="tables")
def fixture_tables():
    crud.TABLE_CONFIG.update(TABLES)
    try:
        yield
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch, tables):
    """The chain rules file every chain seat reads, pointed at this test's own."""
    path = tmp_path / "chain_rules.json"

    def write(rules):
        path.write_text(json.dumps({"rules": rules}), encoding="utf-8")
        return path

    write([])
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "bk"))
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    import paths
    real = paths.config_path
    monkeypatch.setattr(paths, "config_path",
                        lambda name: str(path) if name == "chain_rules.json" else real(name))
    return write


# ------------------------------------------------------------------------------ the judge

@pytest.mark.parametrize("value", [True, False])
def test_true_and_false_pass(value):
    assert validation.flag_refusal("enabled", value) is None


@pytest.mark.parametrize("value", NOT_FLAGS)
def test_anything_else_gets_the_one_sentence_naming_the_value(value):
    assert validation.flag_refusal("enabled", value) == (
        "enabled must be true or false, got %s - write true or false" % _said(value))


# ------------------------------------------------------------------------- chain declarations

CHAIN_CELLS = [
    (FLAT, ("enabled",)), (FLAT, ("allow_retraction",)), (FLAT, ("key", "unique")),
    (UNIFIED, ("enabled",)), (UNIFIED, ("derive", "decide", "auto_confirm")),
    (UNIFIED, ("limits", "idempotent")), (UNIFIED, ("is_batch",)),
]


def _with(declaration, cells, value):
    out = json.loads(json.dumps(declaration))
    node = out
    for cell in cells[:-1]:
        node = node.setdefault(cell, {})
    node[cells[-1]] = value
    return out


@pytest.mark.parametrize("declaration,cells", CHAIN_CELLS)
@pytest.mark.parametrize("value", NOT_FLAGS)
def test_a_chain_declaration_stands_nothing_and_names_the_cell(tables, declaration, cells,
                                                                value):
    stood, refusal, _notes = rule_shape.expand_declaration(
        _with(declaration, cells, value), crud.TABLE_CONFIG)
    assert stood == []
    assert refusal == "%s: %s" % (declaration["name"], validation.flag_refusal(
        ".".join(cells), value))


@pytest.mark.parametrize("declaration,cells", CHAIN_CELLS)
def test_the_same_declaration_with_true_stands(tables, declaration, cells):
    """The control: the cell itself is not what refuses."""
    stood, refusal, _notes = rule_shape.expand_declaration(
        _with(declaration, cells, True), crud.TABLE_CONFIG)
    assert refusal is None and stood


def test_absent_enabled_is_on_as_before(tables):
    assert rule_shape.expand_declaration(FLAT, crud.TABLE_CONFIG) == ([FLAT], None, [])
    assert not rule_shape.is_switched_off(FLAT)


def test_the_loader_drops_it_and_says_why(rules_file, caplog):
    rules_file([dict(FLAT, name="yn_on"), dict(FLAT, name="yn_off", enabled="false")])
    with caplog.at_level(logging.ERROR):
        names = {rule.get("name") for rule in worker.load_chain_rules()}
    assert "yn_on" in names and "yn_off" not in names
    assert any('yn_off: enabled must be true or false, got "false"' in r.getMessage()
               for r in caplog.records)


def test_the_save_gate_refuses_the_switch_before_it_overwrites_it(rules_file):
    path = rules_file([])
    with pytest.raises(Exception) as raised:
        admin.save_chain_rule_raw("yn_new", dict(UNIFIED, name="yn_new", enabled="false"),
                                  admin.file_fingerprint(str(path)))
    detail = raised.value.detail
    assert detail["code"] == "declaration_refused"
    assert 'enabled must be true or false, got \\"false\\"' in json.dumps(detail)


def test_the_rule_list_says_why_a_declaration_did_not_stand(rules_file):
    import main

    rules_file([dict(UNIFIED, enabled=0)])
    rows = {row["name"]: row for row in main.get_chain_rules()["data"]}
    assert "enabled must be true or false, got 0" in (
        rows["yn_unified"].get("rule_state_detail") or "")


def test_the_report_carries_the_sentence(rules_file):
    import config_resolve_report

    rules_file([_with(UNIFIED, ("derive", "decide", "auto_confirm"), "true")])
    report = config_resolve_report._resolve_enrichment()
    assert any("derive.decide.auto_confirm must be true or false" in json.dumps(row)
               for row in report["rejected"])


def test_rule_refusals_keeps_its_code_and_says_the_one_sentence():
    issues = chain_bindings.rule_refusals(
        dict(FLAT, idempotent="false"), "rules[0]", mapper_resolvable=lambda name: True,
        derived_tables=set())
    [issue] = [i for i in issues if i.code == "bad_idempotent"]
    assert issue.message == validation.flag_refusal("idempotent", "false")


# ------------------------------------------------------------------------------- collectors

@pytest.mark.parametrize("cell", ["enabled", "recursive"])
def test_a_collector_entry_is_refused_by_name(tmp_path, monkeypatch, cell):
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: VOID_TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", VOID_TABLES)
    settings = _specs(tmp_path / "outside")
    settings["external_sources"][0][cell] = "false"
    specs, errors = directory_watcher.validate_external_source_specs(
        settings, VOID_TABLES, str(tmp_path / "workspace"))
    assert [s["table_name"] for s in specs] == ["inspection_run"]
    assert errors == ["external_sources[0]: " + validation.flag_refusal(cell, "false")]


# ----------------------------------------------------------------------------- ledger bundle

LEDGER_CELLS = [
    (("virtual_joins", "input_to_reference", "enabled"), "enabled"),
    (("virtual_joins", "input_to_reference", "materialize"), "materialize"),
    (("virtual_joins", "input_to_reference", "fold", "case"), "case"),
    # ⚰️ prepare.accepts_verified_join_rules left with the prepare clause (setup_version 6).
]


@pytest.mark.parametrize("cells,name", LEDGER_CELLS)
def test_a_ledger_flag_refuses_the_bundle_with_the_sentence(cells, name):
    raw = _with(logical_bundle(), cells, "true")
    errors = snapshot_compile_errors(LedgerSetupBundle(raw), trusted_implementations())
    wanted = "bundle." + ".".join(cells)
    assert [(e.path, e.message) for e in errors if e.path == wanted] == [
        (wanted, validation.flag_refusal(name, "true"))]


def test_blank_and_allow_null_say_the_sentence_too():
    raw = logical_bundle()
    raw["sources"]["input_rows"]["read"]["exclude_when"] = [
        {"column": "join_id", "blank": 1}]
    raw["entities"]["InputEntity@1"]["allow_null"] = "false"
    messages = {e.message for e in snapshot_compile_errors(
        LedgerSetupBundle(raw), trusted_implementations())}
    assert validation.flag_refusal("blank", 1) in messages
    assert validation.flag_refusal("allow_null", "false") in messages


# -------------------------------------------------------------------------------- notation

def test_a_notation_rule_toggle_keeps_the_default_and_write_stays_off():
    rejections = []
    out = notation_norm.validate_notation_rules(
        {"columns": {"t": {"rules": {"case": "true"}, "c": {"write": 1}}}},
        rejections=rejections)
    details = [r["detail"] for r in rejections]
    assert validation.flag_refusal("case", "true") + "; the default is kept" in details
    assert (validation.flag_refusal("write", 1)
            + "; the column is folded for comparison only") in details
    assert out["t"]["c"]["write"] is False


# ---------------------------------------------------------------------------- maps: entries

def _routing(**cells):
    entry = {"product_presets": {"P1": "preset_a"}}
    entry.update(cells)
    return {"preset_routing": {"t": entry}}


def test_routing_whose_switch_is_not_a_yes_no_is_not_used(caplog):
    assert preset_routing.resolve_routing_config(_routing(enabled=True), "t") is not None
    with caplog.at_level(logging.WARNING):
        assert preset_routing.resolve_routing_config(_routing(enabled="false"), "t") is None
    assert any(validation.flag_refusal("enabled", "false") in r.getMessage()
               for r in caplog.records)


def test_a_routing_rule_or_lookup_whose_switch_is_not_a_yes_no_is_dropped(caplog):
    rule = {"name": "r", "match": "prefix", "value": "A", "preset": "preset_a"}
    lookup = {"table": "lt", "key_column": "k", "value_column": "v"}
    kept = preset_routing.resolve_routing_config(
        _routing(rules=[rule], product_lookup=lookup), "t")
    assert kept["rules"] and kept["product_lookup"]
    with caplog.at_level(logging.WARNING):
        out = preset_routing.resolve_routing_config(
            _routing(rules=[dict(rule, enabled=1)], product_lookup=dict(lookup, enabled=0)), "t")
    assert out["rules"] == [] and out["product_lookup"] is None
    said = [r.getMessage() for r in caplog.records]
    assert any(validation.flag_refusal("enabled", 1) in m for m in said)
    assert any(validation.flag_refusal("enabled", 0) in m for m in said)


@pytest.mark.parametrize("written,locked", [(True, True), (False, False), ("false", False),
                                            (1, False)])
def test_paint_lock_takes_only_true(caplog, written, locked):
    with caplog.at_level(logging.WARNING):
        rules = map_overlay.get_paint_rules({"paint_lock": {"t": {"enabled": written}}}, "t")
    assert rules["enabled"] is locked
    why = validation.flag_refusal("enabled", written)
    assert any(bool(why) and why in r.getMessage() for r in caplog.records) is bool(why)


def test_paint_lock_absent_is_off_as_before():
    assert map_overlay.get_paint_rules({}, "t")["enabled"] is False


# ------------------------------------------------------------------------ settings: default

def test_the_global_auto_confirm_switch_falls_back_to_true_and_says_why(caplog):
    candidates.reset_warnings()
    key = candidates.GLOBAL_KILL_SWITCH_KEY
    with caplog.at_level(logging.WARNING):
        assert candidates.global_auto_confirm_enabled({key: "false"}) is True
    assert any(validation.flag_refusal(key, "false") in r.getMessage() for r in caplog.records)
    assert candidates.global_auto_confirm_enabled({key: False}) is False
    assert candidates.global_auto_confirm_enabled({}) is True


@pytest.mark.parametrize("written,unlocked", [(True, True), ("true", False), (1, False)])
def test_map_push_ok_unlocks_only_on_true_and_says_why_otherwise(caplog, written, unlocked):
    import main

    with caplog.at_level(logging.WARNING):
        assert main._map_push_ok("t", {"map_push_ok": written}) is unlocked
    why = validation.flag_refusal("map_push_ok", written)
    assert any(bool(why) and why in r.getMessage() for r in caplog.records) is bool(why)
    assert main._map_push_ok("t", {}) is False


def test_an_ingestion_setting_falls_back_to_its_default_and_says_why(monkeypatch, caplog):
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings",
                        lambda: {"dedup_by_signature": "false"})
    monkeypatch.setattr(directory_watcher, "_invalid_field_warned", set())
    with caplog.at_level(logging.WARNING):
        on = directory_watcher.dedup_by_signature_enabled()
    assert on is directory_watcher.DEFAULT_DEDUP_BY_SIGNATURE
    assert any(validation.flag_refusal("dedup_by_signature", "false") in r.getMessage()
               for r in caplog.records)


def test_std_parse_says_the_one_sentence(monkeypatch, caplog):
    monkeypatch.setattr(directory_watcher, "_invalid_field_warned", set())
    with caplog.at_level(logging.WARNING):
        directory_watcher.warn_invalid_std_parse_once("table_config.json entry 't'", "false")
    assert any(validation.flag_refusal("std_parse", "false") in r.getMessage()
               for r in caplog.records)


# ------------------------------------------- found after the landing (총괄 5057d030b B)

def test_a_filename_rule_whose_required_is_not_a_yes_no_does_not_stand():
    from parsers import advanced_ingester

    rules, errors = advanced_ingester._validate_rules(
        [{"column": "lot", "regex": "(L\\d+)", "required": "false"}], "rules")
    assert rules == []
    assert errors == ["rules[0]: " + validation.flag_refusal("required", "false")]


def test_a_finding_kind_whose_active_is_not_a_yes_no_is_refused(tmp_path, monkeypatch):
    from scripts.support import finding_kinds

    path = tmp_path / "finding_kinds.json"
    path.write_text(json.dumps({"yn_kind": {"active": "true"}}), encoding="utf-8")
    monkeypatch.setattr(finding_kinds, "_config_path", lambda: str(path))
    with pytest.raises(finding_kinds.FindingKindError) as refused:
        finding_kinds.load(force_reload=True)
    assert str(refused.value) == "finding kind 'yn_kind': " + validation.flag_refusal(
        "active", "true")


def test_bypass_proxy_that_is_not_a_yes_no_falls_back_to_true_and_says_why(
        tmp_path, monkeypatch, caplog):
    import run_auto_update
    from utils import auto_update_control

    path = tmp_path / "auto_update_control.json"
    path.write_text(json.dumps({"bypass_proxy": "false"}), encoding="utf-8")
    monkeypatch.setattr(auto_update_control, "get_control_path", lambda: str(path))
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:1")
    with caplog.at_level(logging.WARNING):
        run_auto_update._apply_proxy_policy()
    assert "HTTP_PROXY" not in os.environ, "the fallback is true: the proxy is bypassed"
    assert any(validation.flag_refusal("bypass_proxy", "false") in r.getMessage()
               for r in caplog.records)
