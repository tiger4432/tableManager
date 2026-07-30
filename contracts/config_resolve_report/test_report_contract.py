"""CONFIG RESOLVE REPORT — the SERVER half, scored against the shared contract vectors.

The file being scored is `contracts/config_resolve_report/vectors.json`, the same file
`client_harness.mjs` reads. Nothing here hardcodes an expectation: every population,
reason and warning comes out of the contract, so deleting a case removes coverage LOUDLY
(`test_every_contract_case_is_consumed`).

    conda run -n assy_manager python -m pytest contracts/config_resolve_report/ -q

HOW IT REACHES THE DEFAULT SUITE
    `server/tests/test_config_resolve_report_contract.py` re-exports every test here, for
    the same reason the map seam does: `testpaths` is ignored whenever paths are given on
    the command line, and every documented command in this repo passes `server/tests/`.

WHY IT LIVES UNDER contracts/
    Two rounds hold this tree open. A contract that costs someone a merge conflict to land
    stops getting landed.

NO DATABASE
    The report reads CONFIG ONLY - that is a property worth pinning, not an accident of the
    test. `test_the_report_issues_no_database_queries` fails if a future edit reaches for a
    session, because the route is a request path and the sweep it deliberately excludes is a
    whole-queue walk.
"""
import copy
import json
import os
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
_SERVER = _ROOT / "server"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

import config_resolve_report as crr          # noqa: E402
import enrichment_candidates                 # noqa: E402
import enrichment_config                     # noqa: E402
from database import crud                    # noqa: E402

VECTORS = json.loads((_HERE / "vectors.json").read_text(encoding="utf-8"))

# Table names that cannot exist in the user's gitignored table_config (server-pm memory:
# the `bonding_log` trap - a collision lets import-time init pin a real schema).
SRC_TABLE = "f9cfg_test_src"
DERIVED_TABLE = "f9cfg_test_derived"

_CONSUMED = set()


# ---------------------------------------------------------------------------
# Translating a contract case into a real config file
# ---------------------------------------------------------------------------

def _table_config(decision_key, target_fields):
    cols = {c: "string" for c in list(decision_key) + list(target_fields)}
    return {
        SRC_TABLE: {"business_key": "src_key",
                    "column_types": dict(cols, src_key="string")},
        DERIVED_TABLE: {"business_key": "drv_key",
                        "composite_key_source": list(decision_key),
                        "composite_key_separator": "_",
                        "column_types": dict(cols, drv_key="string")},
    }


def _rule_json(spec):
    """A contract case declares views by their BINDS; the loader needs real SQL.

    `required_binds` is derived from the query text by the loader itself, so writing the
    SQL here (rather than asserting on a hand-written binds list) means the contract is
    scored against the same derivation production uses.
    """
    decision_key = spec["decision_key"]
    views = []
    for v in spec.get("reference_views", []):
        binds = v["binds"]
        where = " AND ".join(f"{b} = :{b}" for b in binds) or "1 = 1"
        view = {"label": v["label"],
                "query": f"SELECT wafer_id, slot FROM some_reference WHERE {where}"}
        if v.get("candidate_for"):
            view["candidate_for"] = dict(v["candidate_for"])
        views.append(view)
    rule = {
        "source_table": SRC_TABLE,
        "derived_table": DERIVED_TABLE,
        "decision_key": list(decision_key),
        "target_fields": list(spec["target_fields"]),
        "reference_views": views,
    }
    if "auto_confirm" in spec:
        rule["auto_confirm"] = spec["auto_confirm"]
    return rule


@pytest.fixture()
def report_env(tmp_path, monkeypatch):
    """Point the loaders at a scratch config pair and hand back a builder."""
    saved = dict(crud.TABLE_CONFIG)

    def build(rules: dict = None, settings=None, settings_file_exists=True,
              rules_file_exists=True, rules_text=None):
        first = next(iter((rules or {}).values()), None)
        cfg = _table_config(first["decision_key"], first["target_fields"]) if first else {}
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(cfg)

        rules_path = tmp_path / "enrichment_rules.json"
        if rules_file_exists:
            if rules_text is not None:
                rules_path.write_text(rules_text, encoding="utf-8")
            else:
                rules_path.write_text(
                    json.dumps({n: _rule_json(s) for n, s in (rules or {}).items()}),
                    encoding="utf-8")
        monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))

        settings_path = tmp_path / "ingestion_settings.json"
        if settings_file_exists:
            settings_path.write_text(json.dumps(settings or {}), encoding="utf-8")
        elif settings_path.exists():
            settings_path.unlink()
        monkeypatch.setattr(enrichment_candidates, "INGESTION_SETTINGS_PATH", str(settings_path))
        enrichment_candidates.reset_warnings()

        return crr.resolve_report()["domains"][0]

    yield build
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(saved)


def _cases():
    return {c["id"]: c for c in VECTORS["cases"]}


def _entries(domain):
    for pop in crr.POPULATIONS:
        for e in domain[pop]:
            yield pop, e


# ---------------------------------------------------------------------------
# The vocabulary itself
# ---------------------------------------------------------------------------

def test_server_vocabulary_is_exactly_the_contract_vocabulary():
    """A fifth reason word is a contract change, not an implementation detail."""
    assert list(crr.REASONS) == VECTORS["vocabulary"]["reasons"]
    assert list(crr.POPULATIONS) == VECTORS["vocabulary"]["populations"]
    assert list(crr.SCOPES) == VECTORS["vocabulary"]["scopes"]


def test_the_vocabulary_is_borrowed_from_the_runtime_not_invented():
    """Every word must already exist in `main`'s chip-trace degradation vocabulary.

    This is the check that keeps 'reuse the runtime vocabulary' from being a comment
    somebody eventually stops honouring: adding `globally_disabled` here fails HERE, at
    the point of invention, rather than three rounds later when a client renders a word
    the rest of the system does not use.
    """
    import main
    runtime = {v for k, v in vars(main).items()
               if k.startswith("CHIP_TRACE_") and isinstance(v, str)}
    borrowed = set(crr.REASONS) - runtime
    assert not borrowed, (
        f"these report reasons do not exist in the runtime vocabulary: {sorted(borrowed)}. "
        "The contract is that config-time degradation reuses the runtime words; a new word "
        "needs the Lead PM, `vectors.json`, and the client harness updated together.")


def test_the_response_advertises_its_own_vocabulary():
    """So a client can build filters/labels without writing the words down."""
    report = crr.resolve_report()
    assert report["vocabulary"]["reasons"] == list(crr.REASONS)
    assert set(VECTORS["envelope"]["top"]) <= set(report)


def test_entry_refuses_a_word_outside_the_vocabulary():
    """Proof the guard can go RED, not merely that today's callers happen to comply."""
    with pytest.raises(ValueError):
        crr.entry(crr.SCOPE_RULE, "r", "d", reason="globally_disabled")
    with pytest.raises(ValueError):
        crr.entry(crr.SCOPE_RULE, "r", "d", warnings=["probably_fine"])
    with pytest.raises(ValueError):
        crr.entry("nonsense_scope", "r", "d")


# ---------------------------------------------------------------------------
# The cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_id", [c["id"] for c in VECTORS["cases"]])
def test_case(case_id, report_env):
    case = _cases()[case_id]
    _CONSUMED.add(case_id)
    domain = report_env(rules=case["rules"], settings=case.get("settings"))

    if "expect_any" in case:
        want = case["expect_any"]
        hits = [e for e in domain[want["population"]]
                if e["reason"] == want["reason"] and e["scope"] == want["scope"]]
        assert hits, (
            f"[{case_id}] expected at least one {want['scope']} entry in "
            f"'{want['population']}' with reason '{want['reason']}'. Got: "
            f"{[(p, e['scope'], e['reason']) for p, e in _entries(domain)]}")
        return

    want = case["expect"]
    rule_name = next(iter(case["rules"]))
    found = [(pop, e) for pop, e in _entries(domain)
             if e["scope"] == crr.SCOPE_RULE and e["subject"] == rule_name]
    assert len(found) == 1, (
        f"[{case_id}] a rule must appear in exactly one population, got {len(found)}: "
        f"{[(p, e['reason']) for p, e in found]}")
    pop, e = found[0]
    assert pop == want["population"], (
        f"[{case_id}] expected population '{want['population']}', got '{pop}' "
        f"(reason={e['reason']!r}, detail={e['detail']!r})")
    assert e["reason"] == want["reason"], f"[{case_id}] detail was: {e['detail']!r}"
    assert e["warnings"] == want["warnings"], f"[{case_id}] detail was: {e['detail']!r}"


@pytest.mark.parametrize("case_id", [c["id"] for c in VECTORS["settings_cases"]])
def test_settings_case(case_id, report_env):
    case = {c["id"]: c for c in VECTORS["settings_cases"]}[case_id]
    _CONSUMED.add(case_id)
    domain = report_env(rules={}, settings=case.get("settings"),
                        settings_file_exists=case["settings_file_exists"])
    by_key = {s["key"]: s for s in domain["settings"]}
    for want in case["expect"]:
        got = by_key.get(want["key"])
        assert got is not None, f"[{case_id}] settings list has no '{want['key']}'"
        for field in ("value", "origin", "declared"):
            assert got[field] == want[field], (
                f"[{case_id}] {want['key']}.{field}: expected {want[field]!r}, "
                f"got {got[field]!r}")
        assert got["detail"], f"[{case_id}] {want['key']} has no renderable detail"
    if case.get("expect_rejected_reason"):
        reasons = [e["reason"] for e in domain["rejected"]
                   if e["scope"] == crr.SCOPE_SETTING]
        assert case["expect_rejected_reason"] in reasons, (
            f"[{case_id}] an ignored setting must ALSO appear in `rejected` - the "
            f"in-effect value alone never says the declaration was thrown away. "
            f"Got: {reasons}")


def test_every_contract_case_is_consumed():
    """A vector nobody reads is coverage that silently stopped existing."""
    declared = {c["id"] for c in VECTORS["cases"]} | {c["id"] for c in VECTORS["settings_cases"]}
    assert declared <= _CONSUMED, f"unconsumed contract cases: {sorted(declared - _CONSUMED)}"


# ---------------------------------------------------------------------------
# The invariants (INV-F9-*)
# ---------------------------------------------------------------------------

def test_inv_1_and_2_reason_presence_tracks_population(report_env):
    domain = report_env(rules=_cases()["live_production_state_2026_07_30"]["rules"])
    for e in domain["effective"]:
        assert e["reason"] is None, f"INV-F9-2 violated by {e['subject']}"
    for pop in ("ineffective", "rejected"):
        for e in domain[pop]:
            assert e["reason"] is not None, f"INV-F9-1 violated by {pop}/{e['subject']}"


def test_inv_3_and_4_every_entry_is_renderable_and_in_vocabulary(report_env):
    for case in VECTORS["cases"]:
        domain = report_env(rules=case["rules"], settings=case.get("settings"))
        for pop, e in _entries(domain):
            assert set(VECTORS["envelope"]["entry"]) <= set(e)
            assert e["reason"] is None or e["reason"] in crr.REASONS
            assert all(w in crr.REASONS for w in e["warnings"])
            assert isinstance(e["detail"], str) and e["detail"].strip(), (
                f"INV-F9-4: {case['id']} {pop}/{e['subject']} has no detail string. "
                "The client renders this; an empty one makes it invent its own.")


def test_inv_5_counts_equal_population_lengths(report_env):
    domain = report_env(rules=_cases()["knob_on_and_declared"]["rules"])
    for pop in crr.POPULATIONS:
        assert domain["counts"][pop] == len(domain[pop])


def test_inv_6_a_missing_rules_file_is_absence_not_rejection(report_env):
    domain = report_env(rules={}, rules_file_exists=False)
    src = {s["key"]: s for s in domain["sources"]}["rules"]
    assert src["exists"] is False
    assert src["status"] == "ok", (
        "INV-F9-6: an absent declaration file is not a degraded one. Conflating them "
        "makes `rejected` non-empty in a healthy system, and a list that cries wolf "
        "gets ignored (the /graph/mapping-summary precedent).")
    assert domain["rejected"] == []
    assert src["detail"], "absence still has to say something the client can render"


def test_an_unreadable_rules_file_IS_a_rejection(report_env):
    """The other side of INV-F9-6, and the one that must go red if absence swallows it."""
    domain = report_env(rules={}, rules_text="{ not json")
    src = {s["key"]: s for s in domain["sources"]}["rules"]
    assert src["exists"] is True and src["status"] == "degraded"
    assert [e["reason"] for e in domain["rejected"]] == [crr.REASON_MAPPING_UNAVAILABLE]


# ---------------------------------------------------------------------------
# Properties of the report itself
# ---------------------------------------------------------------------------

def test_the_report_issues_no_database_queries(report_env, monkeypatch):
    """It sits on a request path, so it must not become a queue walk.

    Injected defect check: this fails if anything in the report path opens a session.
    The expensive question (the dry-run count) is a SEPARATE route on purpose.
    """
    import database.database as dbmod

    def explode(*a, **k):
        raise AssertionError(
            "the config resolve report opened a database session. It is a request-path "
            "route and must read config only - the whole-queue measurement belongs to "
            "GET /admin/enrichment/auto-confirm/dry-run.")

    monkeypatch.setattr(dbmod, "SessionLocal", explode)
    report_env(rules=_cases()["knob_on_and_declared"]["rules"])


def test_one_domain_failing_does_not_swallow_the_others(monkeypatch):
    """A resolver raising must degrade to a named rejection, not a 500 for everything."""
    def boom():
        raise RuntimeError("synthetic")

    monkeypatch.setitem(crr._RESOLVERS, "synthetic_domain", boom)
    report = crr.resolve_report()
    bad = next(d for d in report["domains"] if d["domain"] == "synthetic_domain")
    assert [e["reason"] for e in bad["rejected"]] == [crr.REASON_MAPPING_UNAVAILABLE]
    assert bad["rejected"][0]["detail"]
    assert any(d["domain"] == crr.DOMAIN_ENRICHMENT for d in report["domains"]), (
        "the healthy domain disappeared when a sibling failed")


def test_the_trap_view_is_visible_before_the_knob_is_turned_on(report_env):
    """The measured live trap, stated as a requirement rather than a comment.

    `같은 lot 전체 슬롯` keys on lot alone. Declaring `candidate_for` on it produces
    `single` (not `ambiguous`) and writes one wafer_id onto every slot of the lot. The
    runtime cannot warn about it - it is not lying when it says `single`. Only the
    DECLARATION shows it, so the report has to.
    """
    case = _cases()["declared_on_a_view_that_cannot_see_the_whole_key"]
    domain = report_env(rules=case["rules"])
    e = domain["effective"][0]
    assert crr.REASON_SCOPE_UNRESOLVED in e["warnings"]
    view = e["fields"]["reference_views"][0]
    assert crr.REASON_SCOPE_UNRESOLVED in view["warnings"]
    assert "slot" in view["detail"], (
        "the warning must name the key the view cannot see - 'this view is narrow' is "
        "not actionable, 'it cannot distinguish slot' is")


def test_the_trap_is_named_BEFORE_anyone_declares_on_it(report_env):
    """'Before they enable the knob' means before the declaration, not after it.

    The dangerous edit declares `candidate_for` on the broad view and flips
    `auto_confirm` in one pass; by the time the report says `scope_unresolved` the
    collector is live. So a narrow-scope view states the fact whether or not it is
    declared - the operator choosing WHICH view to declare is the reader who can
    still act on it.

    `warnings` stays empty for an undeclared view on purpose: a display-only view does
    nothing, and a rule that carries a warning about something inert trains people to
    ignore the warning that matters.
    """
    case = _cases()["live_production_state_2026_07_30"]
    domain = report_env(rules=case["rules"])
    views = domain["ineffective"][0]["fields"]["reference_views"]
    narrow = [v for v in views if v["scope_narrow"]]
    assert narrow, "the lot-only view must be identified as narrow even undeclared"
    for v in narrow:
        assert v["warnings"] == [], "an inert view must not raise the rule's warning"
        assert "candidate_for" in v["detail"] and "core_slot" in v["detail"], (
            "an undeclared narrow view must say what would happen IF it were "
            f"declared, and name the key it cannot see. Got: {v['detail']!r}")


def test_candidate_for_reaches_the_public_rule_shape():
    """The lead-approved additive field. Without it the client must DERIVE which view is
    a candidate source, and derivation is what put a live DECOY on the map overlay."""
    rule = {"name": "r", "source_table": "s", "derived_table": "d",
            "decision_key": ["lot"], "target_fields": ["wafer_id"], "list_columns": [],
            "reference_views": [{"label": "narrow", "candidate_for": {"wafer_id": "wf"}},
                                {"label": "display only", "candidate_for": {}}]}
    public = enrichment_config.to_public_rule(rule)
    assert public["reference_views"] == [
        {"label": "narrow", "candidate_for": {"wafer_id": "wf"}},
        {"label": "display only", "candidate_for": {}},
    ]
    blob = json.dumps(public)
    assert "query" not in blob and "limit" not in blob, (
        "to_public_rule must still withhold the query body and the limit")


def test_reference_view_execution_has_exactly_one_definition():
    """Replaces the drift guard that `main.py` being held open used to require.

    The route now calls `execute_reference_view`; this fails if a second inline copy of
    the wrap reappears in main.py.
    """
    import main
    src = pathlib.Path(os.path.abspath(main.__file__.replace(".pyc", ".py"))).read_text(
        encoding="utf-8")
    assert "execute_reference_view" in src
    for token in ("__enrichment_ref", "__enrichment_cand"):
        assert token not in src, (
            f"main.py contains {token!r} again - reference-view execution has grown a "
            f"second definition. It belongs to enrichment_config, which the candidate "
            f"probe shares.")


def test_live_config_is_still_the_state_this_round_measured():
    """A canary on the user's real (gitignored) config, skipped when absent.

    F9's premise is a MEASUREMENT: no live view declares `candidate_for`, so the knob
    would read as ON and do nothing. When somebody finally declares one, this skips-or-
    fails loudly and the `live_production_state_2026_07_30` vector gets revisited
    deliberately instead of quietly describing a state that no longer exists.
    """
    path = enrichment_config.ENRICHMENT_RULES_PATH
    if not os.path.exists(path):
        pytest.skip(f"no live enrichment_rules.json at {path}")
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    declared = [
        (name, v.get("label"))
        for name, rule in raw.items() if isinstance(rule, dict)
        for v in (rule.get("reference_views") or []) if isinstance(v, dict)
        if v.get("candidate_for")
    ]
    if declared:
        pytest.skip(
            f"the live config now declares candidate_for on {declared} - F9's measured "
            f"premise has changed. Revisit the `live_production_state_2026_07_30` vector.")
    assert not declared


def test_vectors_and_report_agree_on_the_envelope(report_env):
    domain = report_env(rules=_cases()["knob_on_and_declared"]["rules"])
    assert set(VECTORS["envelope"]["domain"]) <= set(domain)
    for s in domain["sources"]:
        assert set(VECTORS["envelope"]["source"]) <= set(s)
    for s in domain["settings"]:
        assert set(VECTORS["envelope"]["setting"]) <= set(s)


def test_contract_case_data_is_not_mutated_by_the_run():
    """Cheap guard: the parametrised tests share `VECTORS`, so an in-place edit in one
    case would silently rewrite another's expectation."""
    fresh = json.loads((_HERE / "vectors.json").read_text(encoding="utf-8"))
    assert fresh == VECTORS or copy.deepcopy(fresh) == VECTORS
