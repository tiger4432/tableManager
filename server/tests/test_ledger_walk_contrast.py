# -*- coding: utf-8 -*-
"""Walk-based contrast — asserted on the RULES, without PostgreSQL.

The SQL is exercised against a live database by the driver in the round's report; what
these defend are the properties that survive any query plan, and none of them needs a
server, so a green line here is green rather than a grey skip.

WHAT EACH TEST DEFENDS
-----------------------
1. `test_a_field_no_config_has_ever_heard_of_becomes_a_candidate` — 🔴 THE ROUND'S
   ACCEPTANCE ASSERTION (owner, 2026-08-14: 「새 술어가 번역되면 선언 0줄로 대조에
   나타난다」). Driven, not asserted about the source text: the payload leaf below appears
   in no config in this repository.
2. `test_the_attributed_denominator_is_what_the_ratio_is_built_on` — the defect the client
   lane measured (44,399 of 46,899 attributed, every factor divided by 46,899). The
   fixture is built so the TWO CANDIDATE RULES DISAGREE: over the side size the row looks
   depleted, over the attributed size it is flat. A fixture where both agree would decide
   nothing.
3. `test_zero_coverage_is_undeterminable_and_never_a_zero_rate` — measured on this box:
   the excursion lots carry no `observed` atoms at all, so `observed·finding_kind=void`
   reaches 0 of 75 case subjects. Read against the side size that is 「이 랏엔 보이드가
   없다」, the exact inversion of the truth.
4. `test_found_and_clean_are_null_under_the_walk_not_reused` — the two names keep meaning
   the found/clean split; the walk compares scope-versus-control and says so in `case`
   and `control` instead of quietly putting different numbers under the old names.
5. `test_upstream_tells_apart_all_before_all_after_mixed_and_unmeasured` — four states,
   and the fourth must not be folded into the second.
6. `test_the_ranking_is_lexicographic_over_the_gates` — 「관문 통과 사전식, 동률은 효과
   크기」, including that `unknown` outranks `fail`.
7. `test_an_identifier_like_field_keeps_its_row_and_loses_only_its_values` — a field that
   vanished silently is indistinguishable from one that was never translated.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_walk_contrast as walk                                 # noqa: E402
import mechanism_gate                                               # noqa: E402


CONTRAST_CFG = {"enriched_at": 1.5, "depleted_at": 0.6667}
WALK_CFG = dict(walk.WALK_DEFAULTS)


def row(predicate, field, value, case_n, control_n, *, is_field=False,
        leaves=None, numeric=0, nulls=0, vtype="string",
        before=0, after=0, no_obs=0, refs=("a1",)):
    """One grouping-sets row in `_COLS` order — the shape `_walk` returns."""
    leaves = case_n + control_n if leaves is None else leaves
    return (predicate, field, 1 if is_field else 0, None if is_field else value,
            case_n, control_n, leaves, numeric, nulls, vtype, vtype,
            before, after, no_obs, None, None, None, None, list(refs))


def shape(rows, case_of, control_of):
    return walk._shape(rows, case_of, control_of, WALK_CFG)


def score_all(rows, case_of, control_of, min_support=2):
    _fields, candidates = shape(rows, case_of, control_of)
    return [c for c in (walk._score(c, CONTRAST_CFG, min_support) for c in candidates)
            if c is not None]


# ------------------------------------------------------ 1. the acceptance assertion
def test_a_field_no_config_has_ever_heard_of_becomes_a_candidate():
    """🔴 `sputter_shield_lot` is in no `siblings_axes.json`, no `finding_kinds`, no
    mechanism binding and no line of Python. It is a candidate because the walk touched
    it, which is the whole redirection of this round."""
    rows = [
        row("cleaned_with", "sputter_shield_lot", None, 40, 100, is_field=True),
        row("cleaned_with", "sputter_shield_lot", "SHIELD-99", 40, 5),
    ]
    scored = score_all(rows, case_of=40, control_of=200)
    assert [c["candidate_key"] for c in scored] == ["cleaned_with:sputter_shield_lot"]
    assert scored[0]["value"] == "SHIELD-99"
    assert scored[0]["enrichment_state"] == walk.ENRICHED

    # ...and its mechanism verdict is `unknown`, never `fail` — nobody has said what the
    # field measures, and that must not read as「기전이 없다」.
    graph = mechanism_gate.MechanismGraph({}, "<test>", "memory")
    walk._attach_gates(scored[0], "void", graph, CONTRAST_CFG)
    assert scored[0]["gates"]["mechanism"]["verdict"] == mechanism_gate.VERDICT_UNKNOWN


# ------------------------------------------------------- 2 & 3. the denominators
def test_the_attributed_denominator_is_what_the_ratio_is_built_on():
    """A fixture the two rules DISAGREE about.

    The field reaches 50 of 100 case subjects and 200 of 200 control subjects. The value
    is carried by 25 case and 100 control.

        over the SIDE:        25/100 = 0.25  vs  100/200 = 0.50   -> 0.5x, "depleted"
        over the ATTRIBUTED:  25/50  = 0.50  vs  100/200 = 0.50   -> 1.0x, flat

    The first is a data gap wearing the clothes of a measured absence.
    """
    rows = [
        row("processed_with", "chamber", None, 50, 200, is_field=True),
        row("processed_with", "chamber", "CH-B", 25, 100),
    ]
    scored = score_all(rows, case_of=100, control_of=200)
    hit = scored[0]
    assert hit["enrichment"] == 1.0
    assert hit["enrichment_state"] == walk.FLAT
    assert hit["enrichment_basis"] == "attributed"
    # Both denominators travel, and the naive one is still visible so an operator can see
    # the coverage gap rather than having to trust that somebody handled it.
    assert hit["case"] == {"n": 25, "of": 100, "rate": 0.25,
                           "attributed_of": 50, "rate_attributed": 0.5,
                           "coverage": 0.5}
    assert hit["control"]["coverage"] == 1.0


def test_zero_coverage_is_undeterminable_and_never_a_zero_rate():
    rows = [
        row("observed", "finding_kind", None, 0, 200, is_field=True),
        row("observed", "finding_kind", "void", 0, 200),
    ]
    scored = score_all(rows, case_of=75, control_of=200, min_support=0)
    hit = scored[0]
    assert hit["enrichment_state"] == walk.UNDETERMINABLE
    assert hit["reason"] == walk.REASON_NO_ATTRIBUTED
    # 🔴 `null`, not `0`. A zero here is the claim「이 랏엔 하나도 없다」.
    assert hit["case"]["rate_attributed"] is None
    assert hit["enrichment"] is None
    assert hit["enrichment_ci"] is None
    assert hit["case"]["attributed_of"] == 0


def test_found_and_clean_are_null_under_the_walk_not_reused():
    rows = [row("processed_with", "step", None, 10, 10, is_field=True),
            row("processed_with", "step", "BONDING", 10, 10)]
    hit = score_all(rows, case_of=10, control_of=10)[0]
    assert hit["found"] is None and hit["clean_scanned"] is None
    assert hit["case"]["n"] == 10 and hit["control"]["n"] == 10
    assert hit["unit"] == "subject"


def test_a_value_absent_from_every_control_subject_gets_no_infinite_ratio():
    rows = [row("processed_with", "recipe.rev", None, 75, 1250, is_field=True),
            row("processed_with", "recipe.rev", "6", 75, 0)]
    hit = score_all(rows, case_of=75, control_of=1250)[0]
    assert hit["enrichment"] is None
    assert hit["reason"] == walk.REASON_ABSENT_FROM_CONTROL
    # The interval still has a finite lower bound, and THAT is what ranks it.
    assert hit["enrichment_ci"][0] > 1.5
    assert hit["enrichment_state"] == walk.ENRICHED


# --------------------------------------------------------------- 5. upstream gate
@pytest.mark.parametrize("before,after,no_obs,expected,reason", [
    (12, 0, 0, walk.GATE_PASS, "all_before"),
    (0, 12, 0, walk.GATE_FAIL, "all_after"),
    (7, 5, 0, walk.GATE_FAIL, "mixed_order"),
    (0, 0, 9, walk.GATE_UNKNOWN, "no_comparable_time"),
])
def test_upstream_tells_apart_all_before_all_after_mixed_and_unmeasured(
        before, after, no_obs, expected, reason):
    out = walk._gate_upstream({"_timing": {"before": before, "after": after,
                                           "no_obs_time": no_obs}})
    assert out["verdict"] == expected
    assert out["reason"] == reason
    assert out["detail"]["atoms_compared"] == before + after


def test_an_unmeasured_order_is_not_a_failed_one():
    """The pair that must never render the same: nothing to compare is not a refutation."""
    unmeasured = walk._gate_upstream({"_timing": {"before": 0, "after": 0,
                                                  "no_obs_time": 9}})
    refuted = walk._gate_upstream({"_timing": {"before": 0, "after": 9,
                                               "no_obs_time": 0}})
    assert unmeasured["verdict"] != refuted["verdict"]
    assert unmeasured["verdict"] == walk.GATE_UNKNOWN


# ------------------------------------------------------------------- 6. the ranking
def _with_gates(real, upstream, mechanism, ci_low, case_n=10):
    return {"gates": {"real": {"verdict": real}, "upstream": {"verdict": upstream},
                      "mechanism": {"verdict": mechanism}},
            "enrichment_ci": [ci_low, ci_low * 2], "case": {"n": case_n}}


def test_the_ranking_is_lexicographic_over_the_gates():
    P, U, F = walk.GATE_PASS, walk.GATE_UNKNOWN, walk.GATE_FAIL
    B = mechanism_gate.VERDICT_BIAS
    rows = [
        _with_gates(P, U, U, 2.0),      # 실재✓ 상류— 기전—
        _with_gates(P, P, U, 1.6),      # 실재✓ 상류✓ 기전—  <- the DOE candidate
        _with_gates(P, P, P, 1.55),     # fully explained
        _with_gates(F, P, P, 99.0),     # huge, but not real: must sink despite the size
        _with_gates(P, P, B, 1.7),      # bias candidate
        _with_gates(P, P, F, 1.9),      # modelled and refuted
    ]
    order = sorted(rows, key=walk._rank_key)
    verdicts = [(r["gates"]["real"]["verdict"], r["gates"]["upstream"]["verdict"],
                 r["gates"]["mechanism"]["verdict"]) for r in order]
    assert verdicts == [(P, P, P), (P, P, U), (P, P, B), (P, P, F),
                        (P, U, U), (F, P, P)]
    # 🔴 `unknown` outranks both `bias_candidate` and `fail` in the mechanism column:
    # the strongest thing nobody has modelled is the DOE candidate, not a leftover.
    assert verdicts.index((P, P, U)) < verdicts.index((P, P, F))


def test_effect_size_breaks_a_tie_and_only_a_tie():
    P = walk.GATE_PASS
    small, large = _with_gates(P, P, P, 1.6), _with_gates(P, P, P, 12.0)
    assert sorted([small, large], key=walk._rank_key) == [large, small]


# ------------------------------------------------------- 7. identifier-like fields
def test_an_identifier_like_field_keeps_its_row_and_loses_only_its_values():
    cap = int(WALK_CFG["high_cardinality_at"])
    rows = [row("observed", "run_uid", None, 100, 100, is_field=True)]
    rows += [row("observed", "run_uid", f"uid-{i}", 1, 1) for i in range(cap + 5)]
    rows += [row("processed_with", "chamber", None, 100, 100, is_field=True),
             row("processed_with", "chamber", "CH-A", 90, 10)]
    fields, candidates = shape(rows, 100, 100)
    by_key = {f["candidate_key"]: f for f in fields}
    assert by_key["observed:run_uid"]["high_cardinality"] is True
    assert by_key["observed:run_uid"]["distinct_values"] == cap + 5
    assert [c["row"]["field"] for c in candidates] == ["chamber"]


def test_the_json_type_decides_the_comparison_and_nothing_else():
    """The owner's 「필드 유형이 비교 방식을 자동 결정」 — no field-name list anywhere."""
    rows = [
        row("processed_with", "params_actual.temp_C", None, 10, 10,
            is_field=True, leaves=20, numeric=20, vtype="number"),
        row("processed_with", "chamber", None, 10, 10, is_field=True, leaves=20),
        row("transferred", "to.position", None, 10, 10,
            is_field=True, leaves=20, nulls=20, vtype="null"),
    ]
    fields, _c = shape(rows, 10, 10)
    kinds = {f["field"]: f["compare"] for f in fields}
    assert kinds == {"params_actual.temp_C": walk.COMPARE_DISTRIBUTION,
                     "chamber": walk.COMPARE_CATEGORICAL,
                     "to.position": walk.COMPARE_NULL}
    numeric = next(f for f in fields if f["compare"] == walk.COMPARE_DISTRIBUTION)
    assert numeric["numeric"]["state"] == "summary_only"


# ---------------------------------------------------------------- scope + buckets
@pytest.mark.parametrize("bad", ["", "bond_lot", "bond_lot:", ":X", "   "])
def test_a_malformed_scope_is_refused_by_name(bad):
    if not bad.strip():
        assert walk.parse_scope(bad) == (None, [])
        return
    with pytest.raises(walk.WalkRequestError) as exc:
        walk.parse_scope(bad)
    assert exc.value.detail["reason"] == walk.REASON_BAD_SCOPE


def test_scope_parses_an_axis_and_its_values():
    assert walk.parse_scope("bond_lot:A,B , C") == ("bond_lot", ["A", "B", "C"])


def test_the_pending_exclusion_buckets_report_null_and_never_zero():
    """🔴 The owner has not named the special-evaluation discriminator. Reporting `0`
    excluded would be the claim「특수평가 랏은 하나도 없다」, which nobody measured."""
    sides = {s: {"subjects": [], "units": 0, "found_units": 0}
             for s in (walk.SIDE_CASE, walk.SIDE_CONTROL, walk.SIDE_MIXED)}
    block = walk._scope_block(sides, has_runs=True)
    pending = {b["bucket"]: b for b in block["excluded"]}
    assert pending["special_eval"]["subjects"] is None
    assert pending["unknown"]["subjects"] is None
    assert pending["special_eval"]["state"] == "discriminator_pending"
    # `mixed` IS measured, so it is a number — the contrast between the two is the point.
    assert pending["mixed"]["subjects"] == 0
    assert pending["mixed"]["state"] == "measured"
