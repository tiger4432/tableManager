# -*- coding: utf-8 -*-
"""총괄 3d03bc819 · 45410384c ③ — an option a CLI passes to a retroactive operation is a
parameter of that operation, so a run record carries it. The admin form does not offer
it (`form=False`), and an option not given leaves the operation's own default."""
from types import SimpleNamespace

import pytest

from admin import retroactive
from chain import cell_layer, replay
from chain.enrichment import analysis
from chain.enrichment import config as enrichment_config
import chain.enrichment.backfill as enrichment_backfill
import ledger.backfill as ledger_backfill
import ledger.setup as ledger_setup

#: op -> the CLI options widened into it (the census in the 3d03bc819 report).
WIDENED = {
    "ledger_backfill": {"fetch_rows": 50, "max_batches": 0, "ontology_root": "/r"},
    "ledger_rescope": {"ontology_root": "/r"},
    "chain_replay": {"limit": 5, "chunk_size": 7},
    "enrichment_backfill": {"limit": 5, "force_disabled": True, "chunk_size": 7},
    "enrichment_confirm": {"limit": 5, "probe_scan_rows": 11, "probe_distinct_values": 13},
    "resolve": {"limit": 5, "chunk_size": 7},
}
#: What a ledger judgment finds for any source this file names (총괄 8e54a261b ④).
_FOUND = SimpleNamespace(require_source=lambda source: source)

REQUIRED = {
    "resolve": {"table": "t"},
    "ledger_backfill": {"source": "s"},
    "ledger_rescope": {"source": "s", "scope_column": "c", "scope_values": "a"},
    "chain_replay": {"rule": "r"},
    "enrichment_backfill": {"rule": "r"},
    "enrichment_confirm": {"rule": "r"},
}


@pytest.fixture(autouse=True)
def _rule_r_is_found(monkeypatch):
    """`validate` asks each operation's own lookup (총괄 d34247b3d ㉠). This file measures the
    options, so `r` is found and the run would not refuse it - and the box's own rules file is
    never read."""
    monkeypatch.setattr(replay, "find_rule", lambda name, row_scoped=False: {"name": name})
    monkeypatch.setattr(replay, "replay_refusal", lambda rule, force=False: (None, []))
    monkeypatch.setattr(enrichment_backfill, "load_rule", lambda name, *a, **k: {"name": name})
    monkeypatch.setattr(retroactive, "_enrichment_rule", lambda name: {"name": name})
    monkeypatch.setattr(cell_layer, "resolve_target", lambda *a, **k: (None, {}))
    monkeypatch.setattr(ledger_setup, "load_setup", lambda *a, **k: _FOUND)
    monkeypatch.setattr(ledger_backfill, "rescope_scope", lambda *a, **k: (None, None))


def test_the_form_does_not_offer_them_and_the_record_accepts_them():
    shown = {row["op"]: {p["name"] for p in row["params"]}
             for row in retroactive.inventory()}
    for op, options in WIDENED.items():
        assert not set(options) & shown[op], op
        params = retroactive.validate(op, {**REQUIRED[op], **options})
        assert {k: params[k] for k in options} == options, op
    assert {"rule", "business_keys", "row_ids", "pace"} <= shown["chain_replay"]


@pytest.mark.parametrize("raw, want", [("5", 5), (5, 5), (" 12 ", 12)])
def test_a_whole_number_is_read(raw, want):
    assert retroactive.validate("chain_replay", {"rule": "r", "limit": raw})["limit"] == want


@pytest.mark.parametrize("raw, want", [(True, True), ("true", True), ("False", False)])
def test_a_flag_is_read(raw, want):
    params = retroactive.validate("enrichment_backfill", {"rule": "r", "force_disabled": raw})
    assert params["force_disabled"] is want


@pytest.mark.parametrize("op, name, raw", [("chain_replay", "limit", "five"),
                                           ("enrichment_backfill", "force_disabled", "maybe")])
def test_an_unreadable_value_is_refused_by_name(op, name, raw):
    with pytest.raises(retroactive.RetroactiveRefused, match=name):
        retroactive.validate(op, {**REQUIRED[op], name: raw})


class _Db:
    def get_bind(self):
        return "engine"


@pytest.fixture()
def calls(monkeypatch):
    """Every operation function the adapters call, recording its keyword arguments."""
    seen = {}

    def record(name, answer):
        def fake(*args, **kwargs):
            seen.setdefault(name, []).append(kwargs)
            return answer
        return fake

    monkeypatch.setattr(ledger_backfill, "run", record("run", {}))
    monkeypatch.setattr(ledger_backfill, "rescope", record("rescope", {
        "source": "s", "scope_column": "c", "rows_in_scope": 0, "withdrawn": 0,
        "inserted": 0, "attempted": 0, "deduped": 0, "applied": True}))
    monkeypatch.setattr(ledger_setup, "load_setup",
                        lambda *args: seen.setdefault("load_setup", []).append(args) or _FOUND)
    monkeypatch.setattr(replay, "find_rule", lambda name, row_scoped=False: {"name": name})
    monkeypatch.setattr(replay, "replay_rule", record("replay_rule", {
        "rows_staged": 0, "events_staged": 0, "rows_scanned": 0}))
    monkeypatch.setattr(enrichment_backfill, "load_rule", record("load_rule", {"name": "r"}))
    monkeypatch.setattr(enrichment_backfill, "run_backfill", record("run_backfill", {
        "created_rows": 0, "updated_rows": 0, "rows_scanned": 0, "skipped_no_key": 0,
        "skipped_blank_identity": 0}))
    monkeypatch.setattr(retroactive, "_enrichment_rule", lambda name: {"name": name})
    monkeypatch.setattr(analysis, "run_auto_confirm_sweep", record("sweep", {}))
    monkeypatch.setattr(replay, "recompute_display_values", record("recompute", {
        "cells_changed": 0, "cells_examined": 0, "rows_scanned": 0}))
    return seen


def _run(op, params):
    spec = retroactive.operation(op)
    spec["run"](_Db(), retroactive.validate(op, params), lambda *_: None, None)


#: op -> (operation function, the options it receives as keywords)
RECEIVES = {
    "ledger_backfill": ("run", ["fetch_rows", "max_batches", "ontology_root"]),
    "chain_replay": ("replay_rule", ["limit", "chunk_size"]),
    "enrichment_backfill": ("run_backfill", ["limit", "chunk_size"]),
    "enrichment_confirm": ("sweep", ["limit"]),
    "resolve": ("recompute", ["limit", "chunk_size"]),
}


@pytest.mark.parametrize("op", sorted(RECEIVES))
def test_a_given_option_reaches_the_operation(calls, op):
    fn, names = RECEIVES[op]
    _run(op, {**REQUIRED[op], **WIDENED[op]})
    got = calls[fn][-1]
    assert {n: got[n] for n in names} == {n: WIDENED[op][n] for n in names}


@pytest.mark.parametrize("op", sorted(RECEIVES))
def test_an_option_not_given_leaves_the_operations_default(calls, op):
    fn, names = RECEIVES[op]
    _run(op, REQUIRED[op])
    assert not set(names) & set(calls[fn][-1]), calls[fn][-1]


def test_the_rest_reach_their_seats(calls):
    _run("enrichment_backfill", {**REQUIRED["enrichment_backfill"],
                                 **WIDENED["enrichment_backfill"]})
    assert calls["load_rule"][-1] == {"force_disabled": True}
    _run("enrichment_backfill", REQUIRED["enrichment_backfill"])
    assert calls["load_rule"][-1] == {}

    _run("ledger_rescope", {**REQUIRED["ledger_rescope"], **WIDENED["ledger_rescope"]})
    _run("ledger_rescope", REQUIRED["ledger_rescope"])
    # Each run twice - its params judgment and the run read the SAME root (총괄 06bb8f474).
    assert calls["load_setup"] == [("/r",), ("/r",), (), ()]

    _run("enrichment_confirm", {**REQUIRED["enrichment_confirm"],
                                **WIDENED["enrichment_confirm"]})
    caps = calls["sweep"][-1]["caps"]
    assert (caps["probe_scan_rows"], caps["probe_distinct_values"]) == (
        {"value": 11, "declared": True}, {"value": 13, "declared": True})
    assert calls["sweep"][-1]["ignore_knob"] is False


def test_a_cap_given_for_one_run_reads_as_declared_and_the_rest_stay_shipped():
    caps = enrichment_config.load_read_caps(settings={}, overrides={
        enrichment_config.CAP_PROBE_SCAN_ROWS: 7,
        enrichment_config.CAP_PROBE_DISTINCT_VALUES: None})
    assert caps[enrichment_config.CAP_PROBE_SCAN_ROWS] == {"value": 7, "declared": True}
    assert caps[enrichment_config.CAP_PROBE_DISTINCT_VALUES]["declared"] is False
    assert caps == {**enrichment_config.load_read_caps(settings={}),
                    enrichment_config.CAP_PROBE_SCAN_ROWS: {"value": 7, "declared": True}}
