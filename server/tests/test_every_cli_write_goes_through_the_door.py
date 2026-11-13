# -*- coding: utf-8 -*-
"""총괄 8a1f32f99 ① · 3d03bc819 — the five CLIs (eight operation calls) write through
`retroactive.run_here`: with --apply the door is called with the operation and the CLI's
options; a dry run does not enter it (45410384c ①); and no CLI calls an operation with
`apply=True` itself. One table: CLI invocation x (door call, direct call)."""
import pytest

from admin import retroactive
from chain import replay
from chain.enrichment import analysis
import chain.enrichment.backfill as enrichment_backfill
import ledger.backfill as ledger_backfill
import ledger.setup as ledger_setup
from tests.test_retroactive_admin import retro_env  # noqa: F401  - session + registered tables

REPLAY_STATS = {"mode": "apply", "rule": "r", "trigger_table": "a", "target_table": "b",
                "self_triggering": False, "rows_scanned": 0, "pages": 0, "rows_staged": 0,
                "events_staged": 0, "pages_failed": 0, "page_failures": []}
WITHDRAW_STATS = {"mode": "apply", "source": "s", "table": "t", "cells_matched": 0,
                  "cells_withdrawn": 0, "revealed": 0, "emptied": 0, "value_unchanged": 0,
                  "pinned_skipped": 0, "samples": []}
RESOLVE_STATS = {"mode": "apply", "table": "t", "rows_scanned": 0, "pages": 0,
                 "cells_examined": 0, "pinned_examined": 0, "cells_changed": 0,
                 "changed_by_tiebreak": 0, "changed_by_stale_materialisation": 0,
                 "pinned_changed": 0, "changes": []}
STATS = {"withdraw": WITHDRAW_STATS, "resolve": RESOLVE_STATS}
REAL_SWEEP = analysis.run_auto_confirm_sweep


@pytest.fixture()
def seen(retro_env, monkeypatch):
    """The door records (op, params); every operation function refuses a write the CLI
    makes itself, and records the dry runs."""
    calls = {"door": [], "direct": []}

    def door(op, params, log=print):
        calls["door"].append((op, {k: v for k, v in params.items() if v is not None}))
        return {"stats": STATS.get(op, REPLAY_STATS)}

    def direct(name, answer):
        def fn(*args, **kwargs):
            assert kwargs.get("apply") is False, f"{name} was asked to write outside the door"
            calls["direct"].append(name)
            return answer
        return fn

    monkeypatch.setattr(retroactive, "run_here", door)
    monkeypatch.setattr(replay, "replay_rule", direct("replay_rule", REPLAY_STATS))
    monkeypatch.setattr(replay, "withdraw_source", direct("withdraw_source", WITHDRAW_STATS))
    monkeypatch.setattr(replay, "recompute_display_values",
                        direct("recompute_display_values", RESOLVE_STATS))
    monkeypatch.setattr(replay, "find_rule", lambda name, row_scoped=False: {"name": name})
    monkeypatch.setattr(replay, "load_rules", lambda: [
        {"name": "r1", "trigger_table": "triage_tbl"},
        {"name": "r2", "trigger_table": "triage_tbl"}])
    monkeypatch.setattr(replay, "order_rules", lambda rules: list(rules))
    monkeypatch.setattr(replay, "_refuse_unless_idempotent", lambda rule, force: None)
    monkeypatch.setattr(enrichment_backfill, "load_rule", lambda *a, **k: {"name": "e"})
    monkeypatch.setattr(enrichment_backfill, "run_backfill", direct("run_backfill", {}))
    monkeypatch.setattr(analysis, "run_auto_confirm_sweep", direct("sweep", {}))
    monkeypatch.setattr(ledger_backfill, "run", lambda *a, **k: pytest.fail(
        "the ledger forward scan always writes - only the door may run it"))
    monkeypatch.setattr(ledger_backfill, "rescope", direct("rescope", {}))
    monkeypatch.setattr(ledger_setup, "load_setup", lambda *a: None)
    monkeypatch.setattr(ledger_backfill, "beat", lambda result: None)
    return calls


def _chain_replay_cli(argv):
    from scripts import chain_replay_cli
    return chain_replay_cli.main(argv)


def _backfill_enrichment(argv, monkeypatch):
    from scripts import backfill_enrichment
    monkeypatch.setattr(backfill_enrichment, "format_report", lambda s, limit=None: "report")
    return backfill_enrichment.main(argv)


def _enrichment_insights(argv, monkeypatch):
    from scripts import enrichment_insights
    monkeypatch.setattr(enrichment_insights, "_rules", lambda name: [{"name": "e"}])
    monkeypatch.setattr(enrichment_insights, "_report_confirm", lambda s: "report")
    return enrichment_insights.main(argv)


def _ledger(argv, monkeypatch):
    import database.database as database_module
    from test_ledger_setup_boundary import _SatisfiedEngine
    monkeypatch.setattr(database_module, "engine", _SatisfiedEngine())
    return ledger_backfill.main(argv)


CASES = [
    # (label, runner, argv, door calls, direct dry-run calls)
    ("replay --apply", "chain", ["replay", "r", "--limit", "5", "--apply"],
     [("chain_replay", {"rule": "r", "limit": 5, "chunk_size": 1000})], []),
    ("replay dry", "chain", ["replay", "r"], [], ["replay_rule"]),
    ("replay-all --apply", "chain", ["replay-all", "--apply"],
     [("chain_replay", {"rule": "r1", "chunk_size": 1000}),
      ("chain_replay", {"rule": "r2", "chunk_size": 1000})], []),
    ("replay-all dry", "chain", ["replay-all"], [], ["replay_rule", "replay_rule"]),
    ("withdraw --apply", "chain", ["withdraw", "t", "s", "--columns", "a", "--apply"],
     [("withdraw", {"table": "t", "source": "s", "columns": ["a"]})], []),
    ("withdraw dry", "chain", ["withdraw", "t", "s"], [], ["withdraw_source"]),
    ("resolve --apply", "chain", ["resolve", "t", "--limit", "5", "--apply"],
     [("resolve", {"table": "t", "limit": 5, "chunk_size": 1000})], []),
    ("resolve dry", "chain", ["resolve", "t"], [], ["recompute_display_values"]),
    ("enrichment --apply", "enrich", ["e", "--force-disabled", "--apply"],
     [("enrichment_backfill", {"rule": "e", "chunk_size": 1000, "force_disabled": True})], []),
    ("enrichment dry", "enrich", ["e"], [], ["run_backfill"]),
    ("confirm --apply", "insights", ["confirm", "e", "--probe-scan-rows", "9", "--apply"],
     [("enrichment_confirm", {"rule": "e", "probe_scan_rows": 9})], []),
    ("confirm dry", "insights", ["confirm", "e"], [], ["sweep"]),
    ("ledger forward", "ledger", ["--source", "s", "--max-batches", "0"],
     [("ledger_backfill", {"source": "s", "fetch_rows": ledger_backfill.DEFAULT_FETCH_ROWS,
                           "max_batches": 0, "world": "default"})], []),
    ("ledger rescope --apply", "ledger",
     ["--source", "s", "--scope-column", "c", "--scope-values", "a,b", "--apply"],
     [("ledger_rescope", {"source": "s", "scope_column": "c", "scope_values": ["a", "b"],
                          "world": "default"})],
     []),
    ("ledger rescope dry", "ledger",
     ["--source", "s", "--scope-column", "c", "--scope-values", "a,b"], [], ["rescope"]),
]


@pytest.mark.parametrize("label, runner, argv, door, direct", CASES,
                         ids=[c[0] for c in CASES])
def test_the_cli_writes_through_the_door_and_dry_runs_do_not(seen, monkeypatch, label,
                                                             runner, argv, door, direct):
    run = {"chain": lambda: _chain_replay_cli(argv),
           "enrich": lambda: _backfill_enrichment(argv, monkeypatch),
           "insights": lambda: _enrichment_insights(argv, monkeypatch),
           "ledger": lambda: _ledger(argv, monkeypatch)}[runner]
    assert run() == 0
    got = [(op, {k: v for k, v in p.items() if k != "ontology_root"}) for op, p in seen["door"]]
    want = [(op, {k: v for k, v in p.items() if k != "ontology_root"}) for op, p in door]
    assert got == want
    assert seen["direct"] == direct


def test_a_script_replay_cannot_ask_for_a_cascade(seen):
    """소유자 09-26 · 09-27: a replay from a script cascades nothing. The grid's click is the one
    seat that asks - its cell is the cascade parameter in
    test_a_chain_write_reads_as_the_chain_whatever_its_layer (총괄 5057d030b)."""
    with pytest.raises(SystemExit) as refused:
        _chain_replay_cli(["replay", "r", "--cascade", "--apply"])
    assert refused.value.code == 2 and seen["door"] == []


def test_replay_all_does_not_replay_a_companion_whole(seen, monkeypatch):
    """S-270's one predicate: the door refuses a join's companion half replayed whole, so
    replay-all must not list it - or it would stop midway, after the rules before it ran."""
    from chain import rule_shape

    monkeypatch.setattr(replay, "load_rules", lambda: [
        {"name": "r1"}, {"name": "half", rule_shape.COMPANION_CELL: "r1"}])
    assert _chain_replay_cli(["replay-all", "--apply"]) == 0
    assert [p["rule"] for _, p in seen["door"]] == ["r1"]
    assert _chain_replay_cli(["replay-all"]) == 0
    assert seen["direct"] == ["replay_rule"], "the dry run lists the same set"


def test_the_ledger_cli_hands_its_world_to_the_run(seen, monkeypatch):
    """총괄 3b6dacd2f: the operator names a declaration by world only. Isolated by the seat's
    own list - `w1` is declared for this test and nothing on disk is read for it."""
    import ledger.schema as ledger_schema

    monkeypatch.setattr(ledger_schema, "worlds", lambda: ["w1"])
    assert _ledger(["--source", "s", "--world", "w1"], monkeypatch) == 0
    assert seen["door"][-1][1]["world"] == "w1"
    assert "ontology_root" not in seen["door"][-1][1]


def test_ignore_knob_with_apply_is_still_refused_and_nothing_enters_the_door(seen,
                                                                            monkeypatch):
    """The sweep is where that refusal lives (the knob is a human's consent); the door
    never sees the combination."""
    monkeypatch.setattr(analysis, "run_auto_confirm_sweep", REAL_SWEEP)
    assert _enrichment_insights(["confirm", "e", "--ignore-knob", "--apply"],
                                monkeypatch) == 2
    assert seen["door"] == []


def test_triage_replays_the_cancelled_rows_through_the_door_by_row_id(seen, flooded):
    from scripts import outbox_triage

    outbox_triage.cancel(flooded, "triage_tbl", apply=True)
    assert outbox_triage.replay_cancelled(flooded, "triage_tbl", apply=True) == 5
    # One door: the registry's `rerun_set_aside`, which replays each rule by row id, once and
    # without cascade (소유자 09-27) - its own gate measures the rules and the rows.
    assert seen["door"] == [("rerun_set_aside", {"tables": "triage_tbl"})]
    assert seen["direct"] == []


@pytest.fixture()
def flooded(retro_env):
    from tests.test_outbox_triage import _per_row_event
    for i in range(5):
        _per_row_event(retro_env, "triage_tbl", i)
    retro_env.commit()
    return retro_env
