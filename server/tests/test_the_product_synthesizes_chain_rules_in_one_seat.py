# -*- coding: utf-8 -*-
"""S-189 ⓒ. One synthesis seat, one table of `builtin:` kinds, and a join that is a chain rule.

🔴 ONE SEAT (판정 304). `load_chain_rules` calls `chain_builtins.synthesize_chain_rules` and
nothing else. Putting the join half inside `load_enrichment_chain_rules` would have satisfied
判정 292's letter while making a function named `enrichment_…` read the virtual-join file, and
a name that lies costs whoever next looks for where a declaration becomes a chain rule.

🔴 ONE TABLE OF KINDS (판정 305), AND IT IS THE FIRST ONE. Measured before building:
`builtin:auto_confirm` appeared exactly twice, both in `enrichment_config`, and NOTHING read
it — S-179 declared the kind for the loader and graph layers and left execution in the sweep.
A rule naming a kind nothing implements sits enabled, looks live, and never runs.

⚠️ THE ENRICHMENT HALF MUST COME OUT BYTE-IDENTICAL. The move is behaviour-zero or it is a
regression wearing a refactor's clothes, and a reordered or dropped rule would be invisible
until a chain stopped firing.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import chain_builtins                                                 # noqa: E402
import enrichment_config                                              # noqa: E402
import virtual_join_config as vjc                                     # noqa: E402


# ---------------------------------------------------------------------------
# 🔴 the seat, and the move that must change nothing
# ---------------------------------------------------------------------------

def test_the_enrichment_half_is_byte_identical_through_the_seat():
    """🔴 THE GATE 판정 304 ASKED FOR. Same rules, same order, same cells — the seat only
    moved the CALL."""
    direct = enrichment_config.load_enrichment_chain_rules()
    through = [r for r in chain_builtins.synthesize_chain_rules()
               if not str(r.get("name") or "").startswith(vjc.JOIN_PREFIX)]
    assert through == direct


def test_the_seat_emits_both_halves():
    names = {r["name"] for r in chain_builtins.synthesize_chain_rules()}
    enrichment = {r["name"] for r in enrichment_config.load_enrichment_chain_rules()}
    joins = {r["name"] for r in vjc.synthesized_join_chain_rules()}
    assert enrichment <= names and joins <= names


def test_the_loader_calls_the_seat_and_not_a_half():
    """⛔ SCORED ON THE SOURCE, because the defect is a SECOND call site that happens to
    agree today — which is exactly what 판정 304 moved."""
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker.load_chain_rules)
    assert "synthesize_chain_rules" in body
    assert "load_enrichment_chain_rules" not in body, "the half is called directly again"


def test_the_boot_line_counts_the_three_kinds_apart():
    """⚠️ 「N synthesized」 OVER THREE KINDS is the shape that once reported 8 of a kind there
    were 4 of, which is why S-179 ① split its own count."""
    rules = chain_builtins.synthesize_chain_rules()
    counts = chain_builtins.synthesized_kind_counts(rules)
    assert set(counts) == {"dedup", "auto_confirm", "join"}
    assert sum(counts.values()) == len(rules)


# ---------------------------------------------------------------------------
# the join half
# ---------------------------------------------------------------------------

KNOWN = {"left_t": {"column_types": {"k": "string", "frame": "string"}},
         "right_t": {"column_types": {"k": "string", "frame": "string"}}}


def _declared(tmp_path, **cells):
    """A virtual-join file we control. ⚠️ NEVER THE LIVE ONE — 「임시로 박스에 설정한
    케이스로 재서 대답 금지」, and the live file is the owner's."""
    import json

    raw = {"_comment": "fixture", "j1": dict(
        {"left_table": "left_t", "right_table": "right_t",
         "join_key": [{"left": "k", "right": "k"}], "expose": ["frame"]}, **cells)}
    path = tmp_path / "virtual_join_rules.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return str(path)


def test_only_a_materializing_rule_becomes_a_chain_rule(tmp_path):
    """🔴 A READ-TIME RULE WRITES NOTHING, so a chain rule for it could never do anything —
    and both of this box's production rules are read-time."""
    read_time = _declared(tmp_path)
    assert vjc.synthesized_join_chain_rules(path=read_time, known_tables=KNOWN) == []


def test_a_materializing_rule_arrives_as_a_paced_builtin(tmp_path):
    path = _declared(tmp_path, materialize=True, max_rewrite_rows=1000)
    rules = vjc.synthesized_join_chain_rules(path=path, known_tables=KNOWN)
    assert len(rules) == 1
    rule = rules[0]
    assert rule["name"] == vjc.synthesized_join_rule_name("j1")
    assert rule["mapper"] == vjc.JOIN_MAPPER
    # 🔴 PACED, for the reason S-151 measured: one reference row can reach 70,800 target
    # rows here, and the standing rule is 「요청/커밋 경로 인라인 금지」.
    assert rule["follow_up"] is True
    assert rule["origin"] == "synthesized:j1"
    # ⚠️ The whole normalized rule rides, as the enrichment half does it — a hand-listed
    # subset goes stale silently.
    assert rule["params"]["max_rewrite_rows"] == 1000
    assert rule["params"]["materialize"] is True


def test_a_name_claimed_by_both_files_is_refused_by_name(tmp_path):
    path = _declared(tmp_path, materialize=True, max_rewrite_rows=10)
    claimed = vjc.synthesized_join_rule_name("j1")
    assert vjc.join_name_collisions([claimed], path=path, known_tables=KNOWN) == [claimed]
    assert vjc.join_name_collisions(["something_else"], path=path, known_tables=KNOWN) == []


# ---------------------------------------------------------------------------
# 🔴 the `builtin:` table
# ---------------------------------------------------------------------------

def test_an_unknown_kind_is_refused_by_name_not_ignored():
    """⛔ SILENCE IS THE DEFECT. A rule naming a kind nothing implements would sit enabled,
    look live, and never run — the same silence `_report_unwatchable_trigger_columns` breaks
    for a mistyped trigger column."""
    with pytest.raises(chain_builtins.UnknownBuiltinKind) as caught:
        chain_builtins.run_builtin("builtin:no_such_kind", None, {})
    assert "builtin:no_such_kind" in str(caught.value)
    assert "builtin:join" in str(caught.value), "it must say what IS known"


def test_the_join_kind_is_in_the_table():
    assert vjc.JOIN_MAPPER in chain_builtins.BUILTIN_KINDS


def test_the_table_routes_a_target_change_and_a_reference_change_differently(monkeypatch):
    """⚠️ ONE KIND, TWO TRIGGERS. The caller says which by which argument it passes, and they
    cost differently — a reference change counts first and can be refused."""
    import virtual_join_executor as vje

    seen = []
    monkeypatch.setattr(vje, "on_target_rows_changed",
                        lambda db, rule, rows: seen.append(("target", rows)) or {"written": 1})
    monkeypatch.setattr(vje, "on_reference_rows_changed",
                        lambda db, rule, keys: seen.append(("reference", keys)) or {"written": 2})

    rule = {"params": {"name": "j1"}}
    chain_builtins.run_builtin(vjc.JOIN_MAPPER, None, rule, row_ids=["r1"])
    chain_builtins.run_builtin(vjc.JOIN_MAPPER, None, rule, key_values=["k1"])
    assert seen == [("target", ["r1"]), ("reference", ["k1"])]


# ---------------------------------------------------------------------------
# the graph
# ---------------------------------------------------------------------------

def test_a_materialized_rule_is_not_drawn_twice():
    """🔴 IT IS A CHAIN RULE NOW, so `_mapper_edges` draws it from the loader. Drawing it in
    `_vjoin_edges` too would put TWO arrows between one pair of tables for one declaration,
    and a reader counting arrows would see a flow that does not exist."""
    import inspect

    import chain_graph

    body = inspect.getsource(chain_graph._vjoin_edges)
    assert 'rule.get("materialize")' in body and "continue" in body


def test_the_dispatcher_rides_the_paced_lap_beside_its_neighbour():
    """⛔ SCORED ON THE SOURCE: the work must be on the FOLLOW-UP drain, not the commit path.
    S-151 measured the inline version at 0.875 s per group, and that measurement is why the
    seat is here at all."""
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker._drain_ledger_followup_sync)
    assert "_run_builtin_followups(db, done)" in body
    hook = inspect.getsource(worker._run_builtin_followups)
    assert "run_builtin(" in hook
    # 🔴 the group line names the rule — a count nobody can attribute is a count nobody acts on
    assert "rule=%s" in hook
    # ⚠️ a delete follows no values
    assert 'done.get("event_type") == "DELETE"' in hook


# ---------------------------------------------------------------------------
# 🔴 the dispatcher does not re-read the rule file on every drain batch
# ---------------------------------------------------------------------------

def test_the_followup_dispatcher_does_not_load_rules_per_batch():
    """🔴 MEASURED: `load_chain_rules()` COSTS 3.4 ms, and the drain calls its batch function
    in a `while` loop — so reading the file, validating every rule and re-running the
    synthesis on every batch is waste that grows with the rule count.

    ⛔ IT WAS INVISIBLE WHEN S-189 ⓒ LANDED, because no join rule matched and the loop did
    nothing. S-195 puts auto-confirm on this path, where it would have fired on every batch
    forever — the cost would have arrived attributed to S-195 rather than to the commit that
    caused it.
    """
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker._run_builtin_followups)
    assert "_followup_builtin_rules()" in body
    assert "load_chain_rules()" not in body, "the file is read per batch again"


def test_the_cached_rules_are_cleared_where_every_other_worker_cache_is():
    """⚠️ A CACHE WITH NO RESET IS WHY A RELOAD STOPS MEANING ANYTHING, and this process
    already has one seat for that."""
    import inspect

    import chain_ingestion_worker as worker

    worker._followup_builtin_rules()
    assert worker._FOLLOWUP_BUILTIN_RULES is not None
    worker.reload_worker_process_cache()
    assert worker._FOLLOWUP_BUILTIN_RULES is None

    body = inspect.getsource(worker.reload_worker_process_cache)
    assert "_FOLLOWUP_BUILTIN_RULES" in body


def test_the_cache_holds_only_what_the_dispatcher_could_run():
    """⚠️ NARROWED AT THE SOURCE. Holding every rule would make the per-batch loop walk the
    whole list to find the handful that are `follow_up` AND implemented."""
    import chain_ingestion_worker as worker
    import chain_builtins

    worker.reload_worker_process_cache()
    for rule in worker._followup_builtin_rules():
        assert rule.get("follow_up")
        assert rule.get("mapper") in chain_builtins.BUILTIN_KINDS
