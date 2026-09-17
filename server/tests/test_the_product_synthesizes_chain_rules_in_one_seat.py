# -*- coding: utf-8 -*-
"""S-189 ⓒ. One synthesis seat, one table of `builtin:` kinds, and a join that is a chain rule.

🔴 ONE SEAT (판정 304). `load_chain_rules` calls `synthesis.synthesize_chain_rules` and
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

from chain import synthesis                                                 # noqa: E402
from chain import enrichment                                              # noqa: E402
from chain import legacy_join_declaration as vjc                                     # noqa: E402


# ---------------------------------------------------------------------------
# 🔴 the seat, and the move that must change nothing
# ---------------------------------------------------------------------------

def _chain_report_with(monkeypatch, dead_half):
    """The report as it is actually BUILT, with one half forced to fail.

    🔴 [판정 454 ④] THE GATE MEASURES 「돌다」, NOT 「간다」. Four tests already
    assert that `synthesize_chain_rules` takes a `failures` list and fills it, and all four
    were green while the SCREEN said nothing at all - the argument had zero product
    consumers. An assertion about the function's signature says nothing about what an
    operator reads, so this builds the report and reads its output.
    """
    import config_resolve_report as rep

    def boom(**k):
        raise RuntimeError("forced: %s" % dead_half)

    if dead_half == "virtual join":
        monkeypatch.setattr(vjc, "synthesized_join_chain_rules", boom)
    else:
        monkeypatch.setattr(enrichment.config, "load_enrichment_chain_rules", boom)
    return rep._resolve_chain()


@pytest.mark.parametrize("dead_half", ["virtual join", "enrichment"])
def test_the_report_names_the_half_that_died(monkeypatch, dead_half):
    """⚠️ BOTH HALVES, BECAUSE AN EMPTY CELL READS AS 「PASSED」. Testing one would leave
    the other's silence covered, and the two are symmetric only if both are wired.
    """
    domain = _chain_report_with(monkeypatch, dead_half)
    said = " ".join(str(r.get("detail") or "") for r in domain.get("rejected") or ())

    assert dead_half in said, "the report does not name the half that died: %r" % said
    assert synthesis.synthesis_half_says(dead_half) in said, (
        "the screen wrote its own sentence instead of the one author's: %r" % said)


def test_the_report_stops_calling_it_normal_while_a_half_is_dead(monkeypatch):
    """🔴 [판정 454 ③] 「정상입니다」 IS A JUDGEMENT AND A DEAD HALF REMOVES ITS
    EVIDENCE. Measured before the repair: thirty-eight tables carried 「파생이 필요 없는
    표라면 이것이 정상입니다」 while the join half was gone. A file-level rejection above
    them does not repair that - 판정 453 ruled on exactly that shape.
    """
    domain = _chain_report_with(monkeypatch, "virtual join")
    normal = [e for e in domain.get("ineffective") or ()
              if "정상입니다" in str(e.get("detail") or "")]

    assert normal == [], (
        "%d tables are called normal while a half of synthesis is dead" % len(normal))
    incomplete = [e for e in domain.get("ineffective") or ()
                  if "불완전" in str(e.get("detail") or "")]
    assert incomplete, "and it does not say the judgement is incomplete either"


def test_a_healthy_report_still_says_normal_and_names_no_half(monkeypatch):
    """🔴 THE BLANK THAT WOULD READ AS 「PASSED」. A report that always warned would be
    noise on every healthy box, and noise is not read - so the two tests above would pass
    while the screen became useless. This is the other side of that cell.
    """
    import config_resolve_report as rep

    domain = rep._resolve_chain()
    said = " ".join(str(r.get("detail") or "") for r in domain.get("rejected") or ())

    assert "반쪽이 실패" not in said, said
    assert not [e for e in domain.get("ineffective") or ()
                if "불완전" in str(e.get("detail") or "")]


def test_one_half_failing_does_not_take_the_other_down(monkeypatch):
    """🔴 [판정 452 ②] THE TWO HALVES WERE ONE EXPRESSION. Anything raising in the
    virtual-join half took the enrichment half with it, the caller logged a single line
    about 「the enrichment and virtual-join files」 and carried on with NO synthesised rule
    at all - dedup and auto-confirm included.

    ⚠️ AND STEP 4 IS EXACTLY THAT FAILURE. Removing the `virtual_join` package makes that
    import raise, so without this the removal would have read as 「this box declares no
    enrichment」 - a silent loss wearing the shape of an empty declaration, which is the
    class this repository keeps closing.
    """
    expected = list(enrichment.config.load_enrichment_chain_rules())
    monkeypatch.setattr(vjc, "synthesized_join_chain_rules",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("package removed")))
    failures = []

    rules = synthesis.synthesize_chain_rules(failures=failures)

    assert rules == expected, "the enrichment half did not survive the join half's failure"
    assert [f["half"] for f in failures] == ["virtual join"]
    assert "NOT running" in failures[0]["stops"], failures
    assert "package removed" in failures[0]["error"]


def test_the_other_direction_too_so_neither_half_is_privileged(monkeypatch):
    """⚠️ THE EMPTY CELL OF THE TABLE, ASSERTED. Testing only the join half would leave
    「enrichment fails」 reading as covered, and the two are symmetric only if both are
    actually wrapped - one `try` around the pair looks identical from the outside until the
    untested half is the one that raises.
    """
    expected = list(vjc.synthesized_join_chain_rules())
    monkeypatch.setattr(enrichment.config, "load_enrichment_chain_rules",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("enrichment gone")))
    failures = []

    rules = synthesis.synthesize_chain_rules(failures=failures)

    assert rules == expected, "the join half did not survive the enrichment half's failure"
    assert [f["half"] for f in failures] == ["enrichment"]
    assert "dedup" in failures[0]["stops"],         "the sentence does not name what stopped running: %r" % failures[0]["stops"]


def test_a_healthy_synthesis_reports_no_failure_at_all(monkeypatch):
    """🔴 THE BLANK THAT WOULD OTHERWISE READ AS 「PASSED」. A collector that always put
    something in the list would make the two tests above pass while telling an operator every
    boot that something is broken - the flood shape, arriving from the other side.
    """
    failures = []

    synthesis.synthesize_chain_rules(failures=failures)

    assert failures == [], failures


def test_the_seat_still_answers_when_the_caller_passes_no_collector():
    """⚠️ `failures` IS OPTIONAL AND A FAILING HALF STILL MUST NOT RAISE. One of the two
    live callers (`config_resolve_report`) passes nothing, and raising there would put the
    package's removal in front of an operator as a broken report rather than a named loss.
    """
    assert synthesis.synthesize_chain_rules() == synthesis.synthesize_chain_rules(failures=[])


def test_the_enrichment_half_is_byte_identical_through_the_seat():
    """🔴 THE GATE 판정 304 ASKED FOR. Same rules, same order, same cells — the seat only
    moved the CALL."""
    direct = enrichment.config.load_enrichment_chain_rules()
    through = [r for r in synthesis.synthesize_chain_rules()
               if not str(r.get("name") or "").startswith(vjc.JOIN_PREFIX)]
    assert through == direct


def test_the_seat_emits_both_halves():
    names = {r["name"] for r in synthesis.synthesize_chain_rules()}
    # 🪦 [S-211 packaging] the local was called `enrichment`, which now shadows the
    #    PACKAGE on the same line. Renamed rather than aliased: the package is the
    #    thing being read here.
    from_enrichment = {r["name"]
                       for r in enrichment.config.load_enrichment_chain_rules()}
    joins = {r["name"] for r in vjc.synthesized_join_chain_rules()}
    assert from_enrichment <= names and joins <= names


def test_the_loader_calls_the_seat_and_not_a_half():
    """⛔ SCORED ON THE SOURCE, because the defect is a SECOND call site that happens to
    agree today — which is exactly what 판정 304 moved."""
    import inspect

    from chain import ingestion_worker as worker

    body = inspect.getsource(worker.load_chain_rules)
    assert "synthesize_chain_rules" in body
    assert "load_enrichment_chain_rules" not in body, "the half is called directly again"


# 🪦 `test_the_boot_line_counts_the_three_kinds_apart` died with `synthesized_kind_counts`
#    (S-234 ③): the 「Synthesized N (a · b · c)」 line folded into the loader's set line, which
#    names every rule with its origin and kind. That line is scored in
#    `test_three_files_declare_one_chain_namespace.py`.


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


def test_a_materializing_rule_arrives_as_a_trigger_path_rule(tmp_path):
    path = _declared(tmp_path, materialize=True, max_rewrite_rows=1000)
    rules = vjc.synthesized_join_chain_rules(path=path, known_tables=KNOWN)
    assert len(rules) == 1
    rule = rules[0]
    assert rule["name"] == vjc.synthesized_join_rule_name("j1")
    assert rule["mapper"] == vjc.JOIN_MAPPER
    # ⚰️ [소유자 정본] THIS ASSERTED `rule["follow_up"] is True`, 「paced, for the reason S-151
    #   measured」. 소유자: 「체인은 … 트랜잭션 - 아웃박스 - 트리거 - 맵퍼 실행 - 페이로드 및
    #   업서트 이거만 하면됨」 — there is no paced lap to be deferred to, so the cell is gone
    #   and its ABSENCE is what this asserts. The 70,800-row measurement still stands; what
    #   changed is that a cost is reported after it happens, not designed around first.
    assert "follow_up" not in rule
    # 🔴 AND THE GROUP-NESS IS DECLARED (판정 506): the retired kind table called every
    #   builtin with the whole row-id list, so this must say so itself now.
    assert rule["is_batch"] is True
    assert rule["origin"] == "synthesized:j1"
    # ⚠️ The whole normalized rule rides, as the enrichment half does it — a hand-listed
    # subset goes stale silently.
    assert rule["params"]["max_rewrite_rows"] == 1000
    assert rule["params"]["materialize"] is True


def test_the_seat_says_which_file_a_synthesised_rule_was_written_in(tmp_path):
    """S-234 ①: the one-namespace refusal names the files to look in, and this is the cell
    that tells the two halves apart. ⚠️ Only for rules out of THIS seat - the loader tags
    `chain_rules.json` by position."""
    path = _declared(tmp_path, materialize=True, max_rewrite_rows=10)
    join = vjc.synthesized_join_chain_rules(path=path, known_tables=KNOWN)[0]
    assert synthesis.written_in(join) == "virtual_join_rules.json"
    # ⚰️ THE FIXTURE IS WHAT THE SEAT NOW EMITS. It spelled `mapper_module`, a cell
    #    the dedup half stopped carrying when it became a registered mapper.
    assert synthesis.written_in(
        {"mapper": enrichment.config.DEDUP_MAPPER}) == "enrichment_rules.json"


# 🪦 `test_a_name_claimed_by_both_files_is_refused_by_name` died with `join_name_collisions`
#    (S-234 ①, 판정 409): the three files are one namespace, judged once at the loader. That
#    refusal is scored in `test_three_files_declare_one_chain_namespace.py`.


# ---------------------------------------------------------------------------
# 🔴 the `builtin:` table
# ---------------------------------------------------------------------------

def test_an_unknown_kind_is_refused_by_name_not_ignored():
    """⛔ SILENCE IS THE DEFECT. A rule naming a kind nothing implements would sit enabled,
    look live, and never run — the same silence `_report_unwatchable_trigger_columns` breaks
    for a mistyped trigger column.

    ⚰️ [판정 498] THE REFUSER MOVED FROM `synthesis.run_builtin` TO THE SEAT, and the SENTENCE
    is what this scores rather than the class. An unregistered `builtin:` name is no longer
    recognised as a builtin at all - it falls through to the arm that resolves a file mapper -
    so the exception type had to change. What must not change is that the operator is told the
    spelling they typed AND the kinds that exist; a refusal naming only the bad spelling leaves
    them guessing at the good one.
    """
    from chain import rule_run

    with pytest.raises(rule_run.UnresolvableRule) as caught:
        rule_run.resolve({"name": "r", "mapper": "builtin:no_such_kind"})
    assert "builtin:no_such_kind" in str(caught.value)
    assert "declared:virtual_join" in str(caught.value), "it must say what IS known"


def test_the_join_mapper_is_registered():
    """⚰️ [판정 562 · 600] THIS ASKED `synthesis.BUILTIN_KINDS`. The kind table is deleted; the
    name resolves through the one registry every mapper uses, under the value 600 gave it."""
    import mapper_sdk

    assert vjc.JOIN_MAPPER == "declared:virtual_join"
    assert vjc.JOIN_MAPPER in mapper_sdk.MAPPER_REGISTRY


def test_the_materialized_join_routes_a_target_change_and_has_no_reference_caller():
    """⚰️ [판정 584 · 소유자 정본] THIS ASSERTED TWO-WAY ROUTING through the kind table:
    `run_join(row_ids=...)` -> target, `run_join(key_values=...)` -> reference.

    🔴 BOTH HALVES OF THAT SUBJECT ARE GONE. The table is deleted, and the reference arm was
    measured at ZERO callers in the product (판정 584) - so the template built from the
    declaration carries the target arm only, and a reference change reaches nothing. That is
    reported here rather than repaired: giving the arm a caller is its own round, and an
    assertion that pretends it is reachable is the kind of green this file exists to refuse.
    """
    import inspect

    from chain import dynamic_mappers
    from chain import legacy_materialized_join as vje

    seen = []
    original = vje.on_target_rows_changed
    try:
        vje.on_target_rows_changed = (
            lambda db, rule, rows: seen.append(("target", list(rows))) or {"written": 1})
        answer = dynamic_mappers.TEMPLATES[vjc.JOIN_MAPPER](
            None, [{"row_id": "r1"}], rule={"params": {"name": "j1"}})
    finally:
        vje.on_target_rows_changed = original

    assert seen == [("target", ["r1"])]
    assert answer["written"] == 1
    assert "on_reference_rows_changed" not in inspect.getsource(
        dynamic_mappers._legacy_materialized_join), (
        "the reference arm got a caller; 584 measured it at zero and this says so")


# ---------------------------------------------------------------------------
# the graph
# ---------------------------------------------------------------------------

def test_a_materialized_rule_is_not_drawn_twice():
    """🔴 IT IS A CHAIN RULE NOW, so `_mapper_edges` draws it from the loader. Drawing it in
    `_vjoin_edges` too would put TWO arrows between one pair of tables for one declaration,
    and a reader counting arrows would see a flow that does not exist."""
    import inspect

    import chain.graph

    body = inspect.getsource(chain.graph._vjoin_edges)
    assert 'rule.get("materialize")' in body and "continue" in body


# ---------------------------------------------------------------------------
# 🔴 the dispatcher does not re-read the rule file on every drain batch
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# S-195 — auto-confirm joins the table, and the named temporary ends
# ---------------------------------------------------------------------------

def test_the_drain_has_no_rule_loop_left():
    """⛔ THE ASSERTION THAT CLOSES 「두 경로 금지」, NOW ONE STEP FURTHER.

    ⚰️ It used to require `_run_the_follow_up_pass(db, done)` to appear EXACTLY ONCE in the
    drain - one route rather than two. 소유자 정본 removed the route itself: the drain follows
    the ledger and nothing else, and chain rules are woken by their trigger.

    🔴 WHAT IS ASSERTED IS THE ABSENCE OF A RULE LOOP, not the absence of a name. A second
    route wearing a different spelling is the defect; a drain that runs no rules cannot have
    one. The DELETE withdrawal stays and is named, because it is not the lap (판정 608).
    ⚠️ SUBJECT (608): this is about the CHAIN. `ledger/followup.py`'s own queue is a different
    subsystem and still stands.
    """
    import inspect

    from chain import ingestion_worker as worker

    assert not hasattr(worker, "_auto_confirm_followed_rows"), "the second route is back"
    assert not hasattr(worker, "_run_the_follow_up_pass"), "the lap is back"
    body = inspect.getsource(worker._drain_ledger_followup_sync)
    assert "auto_confirm" not in body, "the drain names a kind again"
    assert "for rule in" not in body, "the drain is running rules again"
    assert "_retract_what_those_rows_fed" in body, (
        "the DELETE withdrawal left with the lap; it is not the lap")


def test_the_collector_is_handed_its_rule_rather_than_finding_it(monkeypatch):
    """🔴 THE SECOND READER, DELETED. `AutoConfirmCollector` already accepted `rules`; left to
    itself it called `load_enrichment_rules` and re-found what the synthesised rule carries in
    `params`. Two readers of one fact is how they come to disagree — and this one also re-read
    a file on a paced path."""
    from chain import enrichment

    seen = {}

    class _Collector:
        active = False

        def __init__(self, table, rules=None, settings=None):
            seen["table"] = table
            seen["rules"] = rules

    monkeypatch.setattr(enrichment.candidates, "AutoConfirmCollector", _Collector)
    rule = {"name": "enrichment_auto_confirm:x", "target_table": "derived_t",
            "params": {"name": "x", "auto_confirm": True}}
    # ⚰️ [판정 498] THE MAPPER, NOT THE DELETED DOOR. What is under test is which rules the
    #    collector is handed, and routing that through the seat would add a resolution step
    #    this assertion says nothing about.
    # ⚰️ [판정 562 · 소유자 정본] THIS CALLED `synthesis.BUILTIN_KINDS["declared:decide"]` with
    #   `row_ids=` and a `done={"table": ...}` note. The table is gone and so is the note —
    #   the template reads the target off `rule["target_table"]`, which is the cell the
    #   declaration already carries, so the rule above gained it and the note went.
    from chain import dynamic_mappers
    from chain.enrichment import config as enrichment_config

    dynamic_mappers.TEMPLATES[enrichment_config.AUTO_CONFIRM_MAPPER](
        None, [{"row_id": "r1"}], rule=rule)
    assert seen["table"] == "derived_t"
    assert seen["rules"] == [rule["params"]], (
        "the collector was left to load the rules itself")

