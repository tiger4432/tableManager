# -*- coding: utf-8 -*-
"""The admin setup lane's write gate — ruling R-2026-08-15-M.

WHY THIS FILE EXISTS AND WHY IT IS THIS SIZE
---------------------------------------------
R-2026-08-14-J put a proportionality rule in force: mutation-grade rigour is for risky
places only, and「원장 쓰기 게이트」is named as one of them. Everything checked here is
either a WRITE GATE (what a declaration must satisfy before it is allowed to change what
the ledger will accept) or the DRY RUN'S ZERO-WRITE GUARANTEE. Nothing here checks how a
screen renders a list.

WHAT LEFT ON 2026-08-27, AND WHY IT IS NOT A GAP
--------------------------------------------------
Half this file used to measure the v1 predicate layer: a per-predicate signature checker,
an operator-editable EXTENSION FILE beside the code list, and the save/retire pair that
wrote to it. All three are gone, so the tests that measured them are gone in the same
commit rather than left as tests of nothing. What replaced them is not a smaller version
of the same thing — the declaration is now the only list, its edit unit is the WHOLE
DOCUMENT, and `test_ledger_structure_pg` is where "the picture follows whatever is
declared" is asserted.

What stays here is what still exists: the SQL-identifier refusals, the source surface
(undeclared table, unparsable raw, stale base), the dry-run token, the closed refusal
set, and the guarantee that a preview writes nothing.
"""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import gate                                              # noqa: E402
import ledger_admin                                                  # noqa: E402


# --------------------------------------------------------------------------- fixtures


def codes(violations):
    return [v["code"] for v in violations]


# --------------------------------------------------------- retirement, never deletion
def test_there_is_no_delete_route_anywhere_under_admin_ledger():
    """R-M ③ as a route-table fact, not a promise in a docstring."""
    from main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/admin/ledger"):
            assert "DELETE" not in (getattr(route, "methods", None) or set()), (
                f"{path} offers DELETE; a registered predicate can never be deleted - "
                f"atoms are already lying in the ledger under that word")


# ------------------------------------------------- SQL identifiers (a NEW risk, today)
@pytest.mark.parametrize("bad", [
    "wafer; DROP TABLE ledger_events",
    'wafer" , (SELECT 1) AS "x',
    "Wafer",                    # unquoted identifiers fold to lower case in PostgreSQL
    "wafer id",
    "1_wafer",
    "",
])
def test_an_identifier_that_would_land_in_an_interpolation_is_refused(bad):
    """The fetches build SQL with f-strings, so this is the ONLY place to say no.

    An identifier is not a bind parameter, so the check cannot be moved downstream. Until
    today a human typed these into a file; from today an HTTP request does.
    """
    assert codes(ledger_admin.check_identifier(bad, "columns.wafer")) \
        == ["invalid_identifier"]


def test_a_legal_identifier_passes():
    assert ledger_admin.check_identifier("base_wafer_id", "columns.wafer") == []


# --------------------------- the source surface: declared tables, and raw editing
def test_a_source_on_an_undeclared_table_is_refused_at_SAVE_not_only_hidden(monkeypatch):
    """🔴 The picker rule needs an enforcement point or it is advice.

    Owner, 2026-08-15: the table list is `table_config`'s declared set only. Hiding
    undeclared tables from the picker would leave the rule advisory, because the RAW JSON
    editor is a second door into the same save. The reason is addressing rather than
    permission: a table the rest of the system does not declare has no key columns, no
    ingestion and no chain, so atoms about its rows name something nothing else can point
    at.
    """
    monkeypatch.setattr(ledger_admin, "declared_tables", lambda: ["void_obs"])
    violations = ledger_admin.check_source_declaration(None, "some_other_table", {})
    assert codes(violations) == ["undeclared_table"]
    assert "table_config.json" in violations[0]["detail_ko"]


def test_an_undeclared_table_is_NAMED_rather_than_silently_absent():
    """An operator who types a table they can SEE in the database and gets an empty list
    learns the screen is broken; one who gets a sentence learns what to do next. Same
    refusal ladder as everywhere else — the refusal names the next action."""
    import inspect

    body = inspect.getsource(ledger_admin.relations_view)
    assert "undeclared" in body
    assert "테이블 미등록" in body, (
        "the undeclared-table sentence changed - it is the operator's next action")


def test_raw_json_that_does_not_parse_is_refused_WITH_A_POSITION():
    """The three-step save is not relaxed for the raw path: no parse, no dry run, no save.
    A raw editor's most common failure is a stray comma, and 「JSON이 잘못됐다」 with no
    position sends the operator hunting through a 200-line blob."""
    parsed, refusal = ledger_admin.parse_raw_declaration(
        '{\n  "kind": "observation",\n  "oops": ,\n}')
    assert parsed is None
    assert refusal["code"] == "declaration_rejected"
    assert "3행" in refusal["detail_ko"], refusal["detail_ko"]

    parsed, refusal = ledger_admin.parse_raw_declaration('["not", "an", "object"]')
    assert parsed is None and refusal["code"] == "declaration_rejected"

    parsed, refusal = ledger_admin.parse_raw_declaration('{"kind": "observation"}')
    assert parsed == {"kind": "observation"} and refusal is None


def test_a_stale_base_is_refused_so_one_save_cannot_clobber_another(tmp_path):
    """🔴 CONCURRENCY IS ITS OWN PROBLEM AND HAS ITS OWN ANSWER.

    The strict admin token is AUTHENTICATION - it answers「are you allowed to write」and
    says nothing about「is the thing you edited still the thing on disk」. The dry-run
    token is a freshness check on the operator's OWN preview: two operators can each
    dry-run their own edit and both tokens are valid. Config files are gitignored by
    design, so a clobbered edit has no history to recover from.
    """
    path = str(tmp_path / "ledger_config.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "sources": {}}, handle)
    base = ledger_admin.file_fingerprint(path)

    assert ledger_admin.check_base(path, base) is None
    assert ledger_admin.check_base(path, None) is None      # the form sends none

    with open(path, "w", encoding="utf-8") as handle:       # somebody else saved
        json.dump({"version": 1, "sources": {"theirs": {}}}, handle)
    stale = ledger_admin.check_base(path, base)
    assert stale is not None and stale["code"] == "stale_base"

    # An absent file has a fingerprint of its own, so "created since you looked" is caught
    # rather than reading as unchanged.
    os.remove(path)
    assert ledger_admin.file_fingerprint(path) == "sha256:absent"
    assert ledger_admin.check_base(path, base)["code"] == "stale_base"


# ------------------------- the declaration map as an edit surface (owner, 08-15)


# ------------------------------------------------- ⑥ the save cannot skip the dry run
def test_the_token_binds_a_save_to_the_EXACT_declaration_that_was_previewed():
    """🔴 What makes「드라이런 없는 저장 버튼은 만들지 않는다」a server rule.

    Not "the client is expected to call dry-run first" - a client that skips it, or that
    edits one character afterwards, produces a token the server does not accept.

    ⚠️ Scope, stated so nobody reads more into this test than it proves: the fingerprint
    is a pure function of the declaration, so a caller who reimplements the hash can
    produce a valid token without ever previewing. That is deliberate circumvention by a
    caller who already holds the strict admin token, not the accidental skip this gate
    exists to prevent - and a server-issued nonce, the only thing that would close it,
    would intermittently refuse legitimate saves the moment there is more than one worker
    process.
    """
    declaration = {"kind": "observation", "relation": "void_obs",
                   "occurred_at_column": "t", "columns": {"wafer": "wafer_id"}}
    token = ledger_admin.declaration_token("source", "void_obs", declaration)

    assert ledger_admin.declaration_token("source", "void_obs", declaration) == token
    edited = dict(declaration, columns={"wafer": "base_wafer_id"})
    assert ledger_admin.declaration_token("source", "void_obs", edited) != token, (
        "one edited character must invalidate the preview it was issued against")
    assert ledger_admin.declaration_token("source", "other", declaration) != token
    assert ledger_admin.declaration_token("predicate", "void_obs", declaration) != token


def test_key_order_does_not_change_the_token():
    """A screen that serialises its form in a different order must not be refused."""
    a = {"kind": "observation", "relation": "r", "occurred_at_column": "t"}
    b = {"occurred_at_column": "t", "relation": "r", "kind": "observation"}
    assert (ledger_admin.declaration_token("source", "n", a)
            == ledger_admin.declaration_token("source", "n", b))


def test_the_refusal_codes_are_closed():
    """A code invented at a call site is a refusal the screen cannot render."""
    with pytest.raises(ValueError):
        ledger_admin.violation("something_went_wrong", None, "…")
    # The control: a code that IS in the closed set builds, so the assertion above is
    # about the CODE and not about `violation` raising for everything.
    assert ledger_admin.violation("invalid_identifier", "columns.wafer", "…")


# ---------------------------------------------------------------- the dry run's config
def test_the_candidate_config_carries_only_the_source_under_preview():
    """A broken NEIGHBOUR must not be able to refuse this preview - and vice versa."""
    declaration = {"occurred_at_column": "t", "occurred_at_timezone": "Asia/Seoul",
                   "subject_types": ["wafer"]}
    cfg = ledger_admin.candidate_config("my_table", declaration)
    assert list(cfg["sources"]) == ["my_table"]


# ---------------------------- the hand-built read queries (R-…-08-15-O)
def test_the_read_paths_ask_for_the_rolled_up_set_not_a_single_type():
    """🔴 THE POINT OF THE RULING, asserted where it can actually regress: a
    wafer-scope reader must bind a LIST. Pinning one `subject_type` is what made 42
    `WaferLeg` atoms invisible and the screen say「본딩 조건 차이 없음」falsely.

    `ledger_journey` was the second source checked here and was deleted with the /journey
    route on 2026-08-25; its half of this guard goes with it rather than lingering as a
    test of nothing. `ledger_walk_contrast` still carries the same query shape, so the
    invariant is still asserted where it still exists.

    Asserted on the SQL text because these are hand-built query strings — there is no
    object to interrogate, and a future edit back to `= %(stype)s` is exactly the
    regression this guards."""
    from ledger_api import ledger_walk_contrast

    sources = [
        ("ledger_walk_contrast",
         open(ledger_walk_contrast.__file__, encoding="utf-8").read()),
    ]
    for name, text in sources:
        assert "subject_type = %(stype)s" not in text, (
            f"{name} still pins a single subject_type — WaferLeg atoms are invisible again")
        assert "subject_type = ANY(%(stypes)s)" in text, (
            f"{name} no longer asks for the rolled-up set")


def test_the_two_grain_arms_are_held_apart_by_the_leg_qualifier():
    """🔴 NOT a rollup site — the opposite, and the distinction is the whole defect.

    `_process_sql` and `_analysis_process_sql` fill ONE dict at TWO grains (component,
    keyed by wafer; analysis_unit, keyed by (wafer, bonding_leg)). If both arms accepted
    the same atom it would land in both buckets and be counted twice - no error, every
    downstream number confidently wrong.

    ⚠️ THE SEPARATOR MOVED, THE REQUIREMENT DID NOT. The two grains used to be two
    subject TYPES; the bonding leg is now a value carried in the claim payload, so all
    four arms legitimately pin the same `subject_type = 'Wafer'` and the split is made by
    the payload qualifier instead: the component arm must EXCLUDE legged evidence, the
    analysis arm must REQUIRE it. Asserting the retired type name here is what made this
    test die on a rename; asserting the exclusion/requirement pair is what actually
    guards against the double count.

    Guarded on the SQL text because these are hand-built strings: a future edit that
    "helpfully" widens either arm is exactly the regression to catch.
    """
    from ledger_api import ledger_selection

    pairs = [("process", ledger_selection._process_sql(),
              ledger_selection._analysis_process_sql()),
             ("measurement", ledger_selection._measurement_sql(),
              ledger_selection._analysis_measurement_sql())]

    for grain, component_arm, unit_arm in pairs:
        assert "NOT (object_payload ? 'bonding_leg')" in component_arm, (
            f"the {grain} component arm no longer excludes legged evidence - the same "
            f"atom now lands in both buckets and is counted twice")
        assert "object_payload->>'bonding_leg' = u.bonding_leg" in unit_arm, (
            f"the {grain} analysis arm no longer requires a bonding leg - it has stopped "
            f"being the other half of the split and reads component evidence too")
        for arm in (component_arm, unit_arm):
            assert "subject_type = 'Wafer'" in arm
            assert "ANY(%(stypes)s)" not in arm, (
                f"a {grain} two-grain arm was widened to the rollup set, merging what "
                f"these two queries exist to hold apart")


# ------------------------------------------------ the gate's counters survive a preview
def test_a_preview_does_not_move_the_processs_refusal_counters():
    """🔴 Otherwise「거절이 쌓이나」answers yes because somebody LOOKED at a declaration.

    The counters are what `/health` and the heartbeat report, and they are process
    aggregates on purpose.
    """
    gate.reset_counters()
    gate.refuse("live_source", gate.REFUSE_NO_IDENTITY, "a real refusal")
    before = gate.refusals()

    with gate.captured() as captured:
        gate.refuse("preview_source", gate.REFUSE_NOT_TRUE_ALONE, "a previewed refusal")

    assert gate.refusals() == before, "the preview's refusal leaked into the process"
    assert captured["refusals"] == {("preview_source", "not_true_alone"): 1}
    assert ("preview_source", "not_true_alone") not in gate.refusals()
    gate.reset_counters()


def test_a_capture_that_raises_still_reports_what_it_counted():
    """A refusal is a fact whether or not the caller caught the exception."""
    gate.reset_counters()
    handle = {}
    with pytest.raises(gate.MoleculeRefused):
        with gate.captured() as handle:
            with gate.building_molecule("preview_source"):
                gate.refuse("preview_source", gate.REFUSE_ATOMICITY, "boom")
    assert handle["refusals"] == {("preview_source", "atomicity_violation"): 1}
    assert gate.refusals() == {}
