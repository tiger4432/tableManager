# -*- coding: utf-8 -*-
"""Walk-based contrast — 「이 랏들과 정상 양산은 뭐가 다른가」, WITHOUT an item list.

🔴 THE ONE RULE THIS MODULE EXISTS TO OBEY
--------------------------------------------
Owner, 2026-08-14, redirecting this round after it had already started::

    「대조할 랏 선택은 괜찮은데 그 안에서 여러 항목 비교하는 게 별로 — 항목에 가정이
     들어가잖아. 다 걷기로 처리하면 양쪽 그룹별로 챔버 차이·레시피 차이 이런 게
     알아서 드러날 텐데」

So the human still MARKS the lots — that is a judgement and it stays a judgement — and
after that nothing is chosen. The candidate space is **everything the walk touches**:
every atom of every marked subject, exploded into `(predicate, field path, value)`. The
chamber difference and the recipe-revision difference are not axes somebody declared; they
are two leaves of `processed_with`'s payload and they arrive because they are there.

**The acceptance assertion**: a newly translated predicate shows up in this contrast with
**zero declaration lines**. If any item list survives anywhere in this file, that assertion
is broken. `siblings_axes.json` still exists and is still read — for the POPULATION
geometry and for the marking axis and for pretty labels — but nothing in it decides what
gets compared, and `test_ledger_walk_contrast.py` asserts exactly that by walking a payload
whose field names appear in no config at all.

WHAT IS COMPARED, AND OVER WHICH DENOMINATOR
---------------------------------------------
    case      subjects whose in-population units are ALL inside the marked scope
    control   subjects with NONE of their units inside it, minus declared exclusions
    mixed     subjects with some of each — their OWN bucket, never folded into either

A leaf's JSON type picks the comparison and nothing else does: a string or boolean gets a
share contrast per VALUE, a number gets a mean-ratio contrast per FIELD. Both land in ONE
ranking under the same declared band and the same three gates, because a cause that lives
in a number is a cause and a screen that can only show categories cannot be read alone.

🔴 The unit of comparison is the **subject the atoms hang off** (a wafer), not the
package. A `processed_with` atom is asserted about a wafer; counting its 141 packages as
141 independent observations would shrink every confidence interval by an order of
magnitude and put noise on top of the ranking. Package counts are still reported — they
are why the operator marked these lots — but they are context, and they are labelled as
context.

🔴 EVERY RATE CARRIES BOTH ITS DENOMINATORS, AND «귀속 N/M» IS ONE OF THEM
---------------------------------------------------------------------------
A field does not reach every subject. Measured on this box: `processed_with` reaches
2,575 of 2,575 base wafers but `params_setpoint.pressure_MPa` reaches only the ones whose
step declared a setpoint. Dividing every candidate by the full side size reports a factor
that is present in EVERY subject it could possibly be present in as though it were present
in 60% of them — a data gap wearing the clothes of a measured absence, which is the exact
defect the client lane measured on the bonding axis (44,399 of 46,899) the morning this
was written.

So each row carries:

    case.n / case.of                  carriers over the whole case side
    case.attributed_of                subjects on that side the FIELD reaches at all
    case.rate_attributed              n / attributed_of  <- what `enrichment` is built on

and `enrichment_basis: "attributed"` says which pair the ratio came from. A field with
50% coverage on one side and 100% on the other no longer manufactures a depletion.

THE THREE GATES (R3)
--------------------
    실재    the Katz lower bound clears the enrichment band — noise cannot rank
    상류    the atom happened BEFORE the observation it is supposed to explain
    기전    `mechanism_gate` — a declared path from this quantity to this finding

`unknown` is a first-class verdict and it is NEVER folded into `fail`. The ranking is
lexicographic over the three, effect size breaking ties, so 「실재✓ · 상류✓ · 기전 —」
sorts where it belongs: the strongest thing nobody has modelled yet, which the brief calls
the DOE candidate.

[SCALE] — MEASURED, AND IT DOES NOT REACH 10M
-----------------------------------------------
The flatten costs ~73 us per atom (measured, `assy_manager`, 2026-08-14: 187,234 Wafer
atoms in 19.6 s; 5,600 atoms in 100 ms — linear). At 10M atoms that is ~12 minutes, so
this walk is bounded by a DECLARED gate rather than by hope: the case side is never
sampled (it is the question), and the control side is deterministically thinned until the
atom estimate fits `walk.max_atoms`. The thinning is by sorted position so the same URL
gives the same answer to two people, and `walk.gate` reports it — a sampled control that
does not say it was sampled is a lie with a confidence interval attached.
The structural fix (a materialised leaf projection) is NOT built here on purpose: the
`observed` translation lane is still changing what the atoms are.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from ledger_api import finding_kinds
from ledger_api import ledger_siblings as sib
from ledger_api import mechanism_gate
from ledger_trace import _fetch, relation_exists, rollup_subject_types

#: The relation the walk reads. 🔴 A literal rather than `from ledger.schema import
#: LEDGER_TABLE`, and deliberately: `ledger_trace_router` states the rule — nothing on the
#: READ side imports the `server/ledger` package, so that including this in the web server
#: does not drag the translator (and its writer-side dependencies) into boot. Same spelling
#: as `ledger_trace_router.LEDGER_RELATION` and the same seam: pointing the walk at a
#: materialised leaf projection is this one string plus a query.
LEDGER_TABLE = "ledger_events"

logger = logging.getLogger("Ledger.WalkContrast")

STATE_READY = "ready"
STATE_EMPTY = "empty"
STATE_ABSENT = "absent"

SIDE_CASE = "case"
SIDE_CONTROL = "control"
SIDE_MIXED = "mixed"

#: Structured refusal/degradation tokens. A client branches on these.
REASON_NO_SUBJECT_DECLARED = "no_ledger_subject_declared"
REASON_LEDGER_ABSENT = "ledger_relation_absent"
REASON_MARKING_RELATION_ABSENT = "marking_relation_absent"
REASON_NO_SCOPE = "no_scope_declared"
REASON_EMPTY_CASE = "empty_case_side"
REASON_EMPTY_CONTROL = "empty_control_side"
REASON_NO_ATOMS = "no_atoms_for_subjects"
REASON_UNKNOWN_AXIS = "unknown_marking_axis"
REASON_BAD_SCOPE = "bad_scope"
REASON_ABSENT_FROM_CONTROL = "absent_from_control_population"
#: Scope-value accounting. 🔴 A requested value that matches nothing used to vanish in
#: silence — the contrast then answered about a NARROWER case set than the caller asked
#: for, and every number downstream (case n, the ratio, the interval, the gates) inherited
#: it while looking perfectly healthy. Measured 2026-08-14 on the live stack:
#: `scope=bond_lot:SYN-VOID-101,NOPE-999` returned `state: "ready"`, echoed both values and
#: computed 25 case subjects — byte-identical to asking for the one lot alone.
REASON_VALUE_UNKNOWN = "value_not_in_axis"
REASON_VALUE_OUT_OF_POPULATION = "value_outside_population"
REASON_NO_VALUE_MATCHED = "no_scope_value_matched"
REASON_NO_ATTRIBUTED = "no_attributed_denominator"
#: Numeric-only outcomes. 🔴 All three keep the candidate IN the list. A quantity that
#: cannot be put on a ratio scale (a mean of 0, a signed quantity) is a fact about the
#: data, and dropping it is how a screen looks more complete than it is.
REASON_NOT_COMPARABLE_SCALE = "not_comparable_scale"
REASON_NO_DISPERSION = "no_dispersion_measured"
REASON_ZERO_DISPERSION = "zero_dispersion"

#: Comparison kinds, decided by the JSON type of the leaf and by nothing else — the owner's
#: rule 「필드 유형이 비교 방식을 자동 결정」. `categorical` gets a share contrast;
#: `distribution` gets a MEAN-RATIO contrast and enters the SAME ranking, with the same
#: three gates and the same enrichment band (2026-08-14 — before that a numeric field was
#: walked, attributed and then never scored, so 33 of 49 fields on the live fixture, every
#: process condition among them, could not reach the screen at all: 「수치에 사는 원인은
#: 보이지 않았다」).
COMPARE_CATEGORICAL = "categorical"
COMPARE_DISTRIBUTION = "distribution"
COMPARE_NULL = "always_null"

CATEGORICAL_TYPES = ("string", "boolean")

ENRICHED, FLAT, DEPLETED, UNDETERMINABLE = (
    "enriched", "flat", "depleted", "undeterminable")

GATE_PASS = "pass"
GATE_FAIL = "fail"
GATE_UNKNOWN = "unknown"

#: 🔴 Rank order WITHIN a gate. `unknown` sits between `pass` and `fail` because it is the
#: absence of a judgement: burying an unmodelled-but-real difference under a modelled
#: non-difference would hide the DOE candidates, which are the point of the screen.
#: `bias_candidate` is a definite 「not a formation cause」 and so sorts below `unknown`,
#: but above `fail` — it is still a real finding, about the inspector rather than the part.
_GATE_ORDER = {GATE_PASS: 0, GATE_UNKNOWN: 1,
               mechanism_gate.VERDICT_BIAS: 2, GATE_FAIL: 3}

#: Defaults, all overridable from `siblings_axes.json`'s `defaults.walk`.
WALK_DEFAULTS = {
    "max_atoms": 60000,
    "max_depth": 6,
    "control_min_subjects": 30,
    "evidence_ref_sample": 5,
    "high_cardinality_at": 200,
    #: 🔴 A NOTE THRESHOLD, NOT A RANKING ONE. The enrichment band is a MULTIPLE, and a
    #: multiple is unit-dependent for a physical quantity: bond temperature 150 vs 145 is
    #: 1.03x in °C and 1.016x in K, so a band declared at 1.5x demotes a declared,
    #: mechanistically-modelled cause for reasons that live in the thermometer. Rather than
    #: invent a second promotion rule tonight, the fields the band demoted while their
    #: SPREAD says they are far apart get named on screen.
    "std_diff_note_at": 1.0,
}

_Z95 = 1.959963985


class WalkRequestError(ValueError):
    """A malformed request, refused with the structured body the route returns as 422."""

    def __init__(self, detail):
        super().__init__(detail.get("message") or detail.get("reason"))
        self.detail = detail


# ------------------------------------------------------------------ scope parsing
def parse_scope(spec):
    """`bond_lot:SYN-VOID-101,SYN-VOID-102` -> `(axis_name, [values])`.

    The axis NAME is a declared marking axis; the VALUES are data and are bound as
    parameters, never interpolated. An empty spec is not an error — it means「전체」and the
    caller falls back to the axes contrast.
    """
    text = (spec or "").strip()
    if not text:
        return None, []
    if ":" not in text:
        raise WalkRequestError({
            "reason": REASON_BAD_SCOPE, "scope": spec,
            "message": "scope 형식: <축이름>:<값>[,<값>...]"})
    axis, _, rest = text.partition(":")
    values = [v.strip() for v in rest.split(",") if v.strip()]
    if not axis.strip() or not values:
        raise WalkRequestError({
            "reason": REASON_BAD_SCOPE, "scope": spec,
            "message": "scope 형식: <축이름>:<값>[,<값>...]"})
    return axis.strip(), values


def resolve_marking_axis(config, kind, name):
    """The axis the human MARKED with. Declared in `siblings_axes.json`, never here.

    This is the one place a declaration still decides something, and it decides only the
    MARKING — which lots the operator pointed at. It has no say over what is compared.
    """
    _geometry, attribution = config.for_kind(kind)
    available = [(s, a) for s in attribution for a in s.axes]
    for source, axis in available:
        if axis.name == name:
            return source, axis
    raise WalkRequestError({
        "reason": REASON_UNKNOWN_AXIS, "axis": name,
        "declared": [a.name for _s, a in available],
        "message": (f"마킹 축 {name!r} 미선언 "
                    f"(선언된 것: {', '.join(a.name for _s, a in available) or '없음'})")})


class LedgerSubject:
    """How a population unit becomes a ledger subject. DECLARED, not conventional.

    `unit_columns[0] is the wafer` happens to be true of the declared package geometry and
    is exactly the kind of convention that turns into a wrong join the day a kind counts
    something else. So the geometry declares it, and a geometry that does not gets an
    honest 「걷기 불가」 instead of a guess.
    """

    __slots__ = ("type", "key", "column")

    def __init__(self, raw, unit_columns):
        self.type = raw.get("type")
        self.key = raw.get("key")
        self.column = raw.get("column")
        if not (self.type and self.key and self.column):
            raise ValueError("geometry.ledger_subject needs type, key and column")
        if self.column not in unit_columns:
            raise ValueError(
                f"geometry.ledger_subject.column {self.column!r} is not one of "
                f"unit_columns {unit_columns!r}")


def _subject_of(geometry):
    raw = getattr(geometry, "ledger_subject", None)
    if not raw:
        return None, "geometry.ledger_subject 미선언"
    try:
        return LedgerSubject(raw, list(geometry.unit_columns)), None
    except Exception as exc:
        return None, str(exc)


# --------------------------------------------------------------------- the answer
def contrast(connection, kind=None, scope=None, window=None, limit=None,
             min_support=None, now=None, walk_overrides=None):
    """The walk contrast, in the pinned envelope. Read-only: never writes, never DDLs."""
    config = sib.load_axes_config()
    defaults = config.defaults
    walk_cfg = dict(WALK_DEFAULTS)
    walk_cfg.update(defaults.get("walk") or {})
    walk_cfg.update(walk_overrides or {})

    kind = (kind or finding_kinds.DEFAULT_KIND).strip()
    try:
        spec = finding_kinds.spec(kind)
    except finding_kinds.FindingKindError as exc:
        raise WalkRequestError({
            "reason": sib.REASON_UNKNOWN_KIND, "kind": kind,
            "declared_kinds": finding_kinds.kinds(),
            "message": f"선언되지 않은 관측 종류: {kind}", "detail": str(exc)})

    axis_name, values = parse_scope(scope)
    if not axis_name:
        raise WalkRequestError({
            "reason": REASON_NO_SCOPE, "message": "scope 미지정 — 걷기 대조는 마킹이 전제"})

    geometry, _attribution = config.for_kind(kind)
    source, axis = resolve_marking_axis(config, kind, axis_name)
    observation = finding_kinds.observation_table(kind)
    methods = finding_kinds.methods(kind)
    win = sib.parse_window(window, now=now)
    limit = sib._bounded(limit, defaults["limit"], 1, 200)
    min_support = sib._bounded(min_support, defaults["min_support"], 0, 10 ** 9)
    graph = mechanism_gate.load()

    envelope = {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "engine": "walk",
        "mode": "contrast",
        "finding": {
            "kind": kind, "label": spec.get("label") or kind, "declared": True,
            "observed_by": list(methods),
            "population_unit": geometry.unit,
            "population_unit_label": geometry.unit_label,
            "source": {"relation": observation},
        },
        "window": win.as_dict(),
        "scope": {"declared": True, "axis": axis.name, "axis_label": axis.label,
                  "values": list(values), "relation": source.relation,
                  "column": axis.column},
        "mechanism": graph.declaration(),
        "notes": [],
        "candidates": [], "candidates_considered": 0, "candidates_truncated": False,
        "fields": [],
    }

    subject, why = _subject_of(geometry)
    if subject is None:
        return _degraded(envelope, REASON_NO_SUBJECT_DECLARED,
                         f"걷기 불가 — 원장 주어 선언 없음 ({why})")
    envelope["subject"] = {"type": subject.type, "key": subject.key,
                           "column": subject.column,
                           "unit_label": f"{subject.type} (원장 주어)"}

    for relation, reason in ((observation, sib.REASON_FINDING_RELATION_ABSENT),
                             (source.relation, REASON_MARKING_RELATION_ABSENT),
                             (LEDGER_TABLE, REASON_LEDGER_ABSENT)):
        if not relation_exists(connection, relation):
            return _degraded(envelope, reason, f"관계 {relation} 없음")

    has_runs = bool(methods) and relation_exists(connection, finding_kinds.RUN_TABLE)
    plan = sib._Plan(geometry, observation, methods, win, has_runs,
                     run_time_as="run_time" if has_runs else None)

    sides, per_value = _sides(connection, plan, source, axis, subject, values, has_runs)
    envelope["scope"].update(_scope_block(sides, has_runs))

    # 🔴 EVERY REQUESTED VALUE IS ACCOUNTED FOR BEFORE ANY NUMBER IS REPORTED. A contrast
    # that silently narrows its own case set gives a confident answer about a population
    # nobody asked about, and it looks healthy the whole way down — which is worse than an
    # error, because an error would stop somebody.
    accounting, unmatched = _account_values(connection, source, axis, values, per_value)
    envelope["scope"].update({
        "value_accounting": accounting,
        "values_requested": len(values),
        "values_resolved": len(values) - len(unmatched),
        "values_dropped": len(unmatched),
    })
    if unmatched:
        # `notes` because the console prints a note's sentence VERBATIM and unconditionally
        # — the one channel that reaches the screen with no client change.
        envelope["notes"].append({
            "note": "scope_values_dropped",
            "values": list(unmatched),
            "message": (f"마킹한 {len(values)}개 중 {len(unmatched)}개가 대조에서 빠졌다 — "
                        f"{_dropped_sentence(accounting)}"
                        + (f". 아래 모든 수치는 남은 {len(values) - len(unmatched)}개 "
                           f"기준이다" if len(unmatched) < len(values) else ""))})
    if len(unmatched) == len(values):
        # 🔴 NOT an empty contrast — a scope that matched NOBODY. A well-formed answer here
        # would be an answer about a population that does not exist.
        return _degraded(envelope, REASON_NO_VALUE_MATCHED,
                         f"마킹한 값 {len(values)}개가 전부 매칭 0 — "
                         f"대조할 케이스가 없다 ({_dropped_sentence(accounting)})",
                         state=STATE_EMPTY)
    if not sides["case"]["subjects"]:
        return _degraded(envelope, REASON_EMPTY_CASE,
                         "케이스 쪽 주어 0 — 마킹한 값이 이 모집단에 없음",
                         state=STATE_EMPTY)
    if not sides["control"]["subjects"]:
        return _degraded(envelope, REASON_EMPTY_CONTROL,
                         "대조군 주어 0 — 같은 기간 정상 양산이 없음", state=STATE_EMPTY)

    case_ids = sides["case"]["subjects"]
    control_ids, gate = _apply_walk_gate(
        connection, subject, case_ids, sides["control"]["subjects"], walk_cfg)
    envelope["walk"] = gate
    if gate.get("case_over_budget"):
        envelope["notes"].append({
            "note": "case_side_over_budget",
            "message": ("케이스 쪽만으로 원자 예산 초과 — 케이스는 «표본하지 않는다»"
                        "(질문 그 자체라서). 응답은 전량 기준이고 느릴 수 있다")})

    rows = _walk(connection, plan, subject, case_ids, control_ids, walk_cfg)
    if not rows:
        return _degraded(envelope, REASON_NO_ATOMS,
                         "이 주어들에 붙은 원자 0건 — 걸을 것이 없음", state=STATE_EMPTY)

    fields, candidates = _shape(rows, len(case_ids), len(control_ids), walk_cfg)
    scored = [_score(c, defaults["contrast"], min_support) for c in candidates]
    scored = [c for c in scored if c is not None]
    for row in scored:
        _attach_gates(row, kind, graph, defaults["contrast"])
    scored.sort(key=_rank_key)

    envelope.update({
        "state": STATE_READY,
        "fields": fields,
        # Three counts, because they answer three different questions and a screen that
        # shows one of them as「후보 수」would be wrong on the other two: how many
        # value-level candidates the walk produced, how many survived `min_support`, and
        # how many fit on the page.
        "candidates_considered": len(candidates),
        "candidates_scored": len(scored),
        "candidates_truncated": len(scored) > limit,
        "candidates": scored[:limit],
        "gates": _gate_legend(),
    })
    _note_high_cardinality(envelope, fields, walk_cfg)
    _note_flat_but_separated(envelope, scored, walk_cfg)
    return envelope


def _degraded(envelope, reason, message, state=STATE_ABSENT):
    envelope.update({"state": state, "reason": reason, "message": message,
                     "candidates": [], "fields": [], "candidates_considered": 0,
                     "candidates_truncated": False})
    envelope.setdefault("walk", {"state": state})
    return envelope


# ----------------------------------------------------------------- the two sides
def _sides(connection, plan, source, axis, subject, values, has_runs):
    """Split the population's SUBJECTS into case / control / mixed, in one query.

    🔴 `mixed` is its own bucket. A subject whose units straddle the marking (a wafer
    bonded into a marked lot and an unmarked one) belongs to neither side, and quietly
    assigning it to one would put the same atoms on both sides of the comparison it is
    supposed to decide.
    """
    units = plan.units
    found_expr = ("count(*) FILTER (WHERE is_found)" if has_runs else "count(*)")
    params = dict(plan.params)
    params["scope_values"] = [str(v) for v in values]
    narrow = source.filter_clause("a", [], params)
    sql = (
        f"{plan.prelude},\n"
        f"marked AS (SELECT p.unit_id, p.is_found, p.{subject.column}::text AS subject,\n"
        f"                  a.{axis.column}::text AS mark_val\n"
        f"           FROM pop p JOIN {source.relation} a "
        f"ON {sib._join_on('p', 'a', source.join)}{narrow})\n"
        f"SELECT 'subject'::text AS kind, subject AS name,\n"
        f"       CASE WHEN bool_and(mark_val = ANY(%(scope_values)s)) THEN 'case'\n"
        f"            WHEN bool_or(mark_val = ANY(%(scope_values)s)) THEN 'mixed'\n"
        f"            ELSE 'control' END AS side,\n"
        f"       count(*) AS units, {found_expr} AS found_units\n"
        f"FROM marked GROUP BY subject\n"
        f"UNION ALL\n"
        # 🔴 THE ACCOUNTING IS DRIVEN BY THE REQUEST, NOT BY WHAT THE DATA CONTAINED.
        # `unnest(...) LEFT JOIN marked` emits one row PER REQUESTED VALUE whether or not
        # it matched, which is the whole difference between「빠졌다」and silence: a
        # GROUP BY over the joined rows can only ever report the values that survived.
        f"SELECT 'value'::text, v.val, NULL::text,\n"
        f"       count(m.unit_id), count(DISTINCT m.subject)\n"
        f"FROM unnest(%(scope_values)s::text[]) AS v(val)\n"
        f"LEFT JOIN marked m ON m.mark_val = v.val\n"
        f"GROUP BY v.val")
    out = {s: {"subjects": [], "units": 0, "found_units": 0}
           for s in (SIDE_CASE, SIDE_CONTROL, SIDE_MIXED)}
    per_value = {}
    for kind, name, side, units_n, found_n in _fetch(connection, sql, params):
        if kind == "value":
            per_value[name] = {"units": int(units_n or 0),
                               "subjects": int(found_n or 0)}
            continue
        bucket = out[side]
        bucket["subjects"].append(name)
        bucket["units"] += int(units_n)
        bucket["found_units"] += int(found_n or 0)
    for bucket in out.values():
        bucket["subjects"].sort()
    return out, per_value


def _account_values(connection, source, axis, requested, per_value):
    """Every requested scope value, resolved or dropped, NAMED and with its reason.

    🔴 DROPPING A VALUE THAT MATCHED NOTHING IS FINE; DOING IT IN SILENCE IS THE DEFECT.
    「빠졌다」 alone is not enough either — a reader told only that much goes hunting for a
    typo when the window may be the cause, so the two are told apart.
    """
    rows, unmatched = [], []
    for value in requested:
        got = per_value.get(str(value)) or {"units": 0, "subjects": 0}
        if got["units"]:
            rows.append({"value": value, "state": "resolved",
                         "units": got["units"], "subjects": got["subjects"],
                         "reason": None, "message": None})
        else:
            rows.append({"value": value, "state": "dropped", "units": 0, "subjects": 0,
                         "reason": None, "message": None})
            unmatched.append(value)
    if not unmatched:
        return rows, unmatched

    # [SCALE] Only on the drop path, and ONE scan of the axis relation no matter how many
    # values dropped — the alternative (an EXISTS per value) is N scans of a table this
    # project sizes at 10M rows, on exactly the path that is already going wrong.
    known = _values_in_axis(connection, source, axis, unmatched)
    for row in rows:
        if row["state"] != "dropped":
            continue
        if row["value"] in known:
            row["reason"] = REASON_VALUE_OUT_OF_POPULATION
            row["message"] = "축에는 있으나 이 기간·모집단에 유닛 0건"
        else:
            row["reason"] = REASON_VALUE_UNKNOWN
            row["message"] = f"{axis.label or axis.name}에 없는 값 — 오타 가능"
    return rows, unmatched


def _values_in_axis(connection, source, axis, values):
    """Which of these values exist on the axis at all, ignoring window and population."""
    sql = (f"SELECT DISTINCT a.{axis.column}::text FROM {source.relation} a "
           f"WHERE a.{axis.column}::text = ANY(%(vals)s)")
    return {r[0] for r in _fetch(connection, sql, {"vals": [str(v) for v in values]})}


def _dropped_sentence(rows):
    """The dropped values, named with their reasons — never a bare count."""
    return ", ".join(
        f"{r['value']}({r['message']})" for r in rows if r["state"] == "dropped")


def _scope_block(sides, has_runs):
    """Both sides' context numbers — WHY these lots were marked — with denominators."""
    def side(bucket):
        units = bucket["units"]
        return {
            "subjects": len(bucket["subjects"]),
            "units": units,
            "found_units": bucket["found_units"] if has_runs else None,
            "found_rate": (round(bucket["found_units"] / units, 6)
                           if has_runs and units else None),
            "found_rate_of": units if has_runs else None,
        }
    return {
        "case": side(sides[SIDE_CASE]),
        "control": side(sides[SIDE_CONTROL]),
        "excluded": [
            {"bucket": SIDE_MIXED, "label": "양쪽에 걸친 주어",
             "subjects": len(sides[SIDE_MIXED]["subjects"]),
             "state": "measured",
             "message": "마킹 안팎에 유닛이 걸쳐 있어 어느 쪽도 아님"},
            # 🔴 `null`, not `0`. The owner has not named the real special-evaluation
            # discriminator yet (`ledger_lots.BUCKET_UNKNOWN` says the same thing about
            # the same gap), so this project has not MEASURED zero special-evaluation
            # subjects — it has not measured at all, and a 0 here would be read as「없음」.
            {"bucket": "special_eval", "label": "특수평가",
             "subjects": None, "state": "discriminator_pending",
             "message": "실데이터 특수평가 구분자 소유자 입력 대기 — 제외 미적용"},
            {"bucket": "unknown", "label": "미상",
             "subjects": None, "state": "discriminator_pending",
             "message": "구분자가 서기 전엔 전 주어가 미상이라 제외하면 대조군이 사라진다"},
        ],
    }


def _apply_walk_gate(connection, subject, case_ids, control_ids, walk_cfg):
    """The declared size gate — kin to `ledger_lots.apply_size_gate`, same shape of answer.

    🔴 The CASE side is never thinned. It is the question; sampling it would answer a
    different one. Only the control side gives ground, deterministically (every k-th of the
    sorted ids) so that the same URL yields the same answer for two people reading it.
    """
    max_atoms = int(walk_cfg["max_atoms"])
    # 🔴 EACH SIDE IS MEASURED ON ITS OWN SAMPLE. A first cut estimated atoms-per-subject
    # from the case side alone and under-counted by 8x on this fixture — the excursion
    # wafers carry 9 atoms each while a normal wafer carries 75, because the `observed`
    # translation had not been re-run over the newer lots. The gate then did not fire and
    # the request took 18.5 s. Two sides that differ IS the situation this tool exists for,
    # so a budget that assumes they are alike is wrong exactly when it matters.
    case_rate = _atoms_per_subject(connection, subject, case_ids[:200])
    control_rate = _atoms_per_subject(connection, subject, control_ids[:200])
    gate = {"state": "ready", "max_atoms": max_atoms,
            "atoms_per_case_subject": case_rate,
            "atoms_per_control_subject": control_rate,
            "applied": False,
            "control_subjects": len(control_ids),
            "control_subjects_available": len(control_ids),
            "control_sampled": False, "sample_step": 1,
            "atoms_estimated": None, "case_over_budget": False}
    if not control_rate:
        gate["atoms_estimated"] = len(case_ids) * case_rate
        return control_ids, gate

    case_atoms = len(case_ids) * case_rate
    gate["case_over_budget"] = case_atoms >= max_atoms
    room = max(max_atoms - case_atoms, 0)
    affordable = int(room // control_rate)
    floor = int(walk_cfg["control_min_subjects"])
    if affordable < len(control_ids):
        keep = max(affordable, min(floor, len(control_ids)))
        step = max(1, math.ceil(len(control_ids) / keep)) if keep else 1
        control_ids = control_ids[::step]
        gate.update({"applied": True, "control_sampled": True, "sample_step": step,
                     "control_subjects": len(control_ids),
                     "sampling": "정렬된 주어의 매 k번째 (URL 재현 가능)",
                     "message": ("대조군을 표본했다 — 비율은 그대로지만 «분모가 "
                                 "표본 크기»다. 케이스는 표본하지 않는다")})
    gate["atoms_estimated"] = case_atoms + len(control_ids) * control_rate
    return control_ids, gate


def _atoms_per_subject(connection, subject, sample_ids):
    """Atoms per subject, measured on a sample of the case side rather than assumed."""
    if not sample_ids:
        return 0
    # Rolled up like the walk it sizes (R-2026-08-15-O). If this probe counted a narrower
    # population than `_walk` actually reads, the sampling step derived from it would be
    # wrong in the direction that matters - it would under-sample the very subjects whose
    # extra atoms it failed to count.
    sql = (f"SELECT count(*) FROM {LEDGER_TABLE} "
           f"WHERE subject_type = ANY(%(stypes)s) "
           f"AND subject_keys->>%(skey)s = ANY(%(ids)s)")
    total = int(_fetch(connection, sql,
                       {"stypes": list(rollup_subject_types(subject.type)),
                        "skey": subject.key, "ids": list(sample_ids)})[0][0])
    return max(1, int(math.ceil(total / float(len(sample_ids)))))


# ------------------------------------------------------------------------ the walk
def _walk(connection, plan, subject, case_ids, control_ids, walk_cfg):
    """ONE pass: flatten every payload of every marked subject, aggregate both sides.

    `GROUPING SETS` gives the value-level rows and the field-level coverage row from the
    same scan, which is what makes 「귀속 N/M」 free rather than a second query — the same
    trick `ledger_siblings._factors` uses, for the same reason.
    """
    params = dict(plan.params)
    params.update({
        "stypes": list(rollup_subject_types(subject.type)), "skey": subject.key,
        "case_ids": list(case_ids), "control_ids": list(control_ids),
        "max_depth": int(walk_cfg["max_depth"]),
        "sample_n": int(walk_cfg["evidence_ref_sample"]),
    })
    # `plan.prelude` already opens with `WITH `; the walk needs `WITH RECURSIVE`, so the
    # shared prelude is spliced in as CTE text rather than re-spelled here. One spelling of
    # runs/scanned/found/pop, which is what keeps the three-way population split identical
    # to the one `/siblings` and the lot grid report.
    prelude_body = plan.prelude[len("WITH "):]
    obs_cte = (f"subj_obs AS (SELECT {subject.column} AS subject, "
               f"min(run_time) AS obs_at FROM runs GROUP BY 1)"
               if plan.has_runs else
               "subj_obs AS (SELECT NULL::text AS subject, "
               "NULL::timestamptz AS obs_at WHERE false)")
    sql = f"""
WITH RECURSIVE {prelude_body},
{obs_cte},
sides AS (
    -- 🔴 `sid` is a DENSE INTEGER name for one subject, and it is here for the measured
    -- reason `ledger_siblings._Plan` gives for its own `unit_id`: the aggregate below has
    -- to count SUBJECTS, and `count(DISTINCT <text id>)` over hundreds of thousands of
    -- leaves is the difference between a screen and a timeout.
    SELECT row_number() OVER () AS sid, subject, side FROM (
        SELECT unnest(%(case_ids)s::text[]) AS subject, 'case'::text AS side
        UNION ALL
        SELECT unnest(%(control_ids)s::text[]), 'control'::text) t
),
atoms AS (
    -- 🔴 The upstream comparison is resolved ONCE PER ATOM, not once per leaf. An atom
    -- with ten leaves would otherwise repeat the same timestamp join ten times, and the
    -- answer would be identical — so the ordering collapses to a small code here and the
    -- recursion carries three bytes instead of a timestamp and a join.
    --   0 = no observation time to compare against   1 = before   2 = at or after
    SELECT e.id, e.predicate, e.object_payload AS payload, s.sid, s.side,
           CASE WHEN o.obs_at IS NULL THEN 0
                WHEN e.occurred_at < o.obs_at THEN 1
                ELSE 2 END AS ord_code
    -- 🔴 ROOT-KEY ROLLUP (R-2026-08-15-O). The contrast asks what differs between two
    -- populations of WAFERS; a bonding leg is a wafer at a finer grain, and pinning one
    -- `subject_type` here made every FINAL_BOND condition invisible to the very screen
    -- built to find condition differences. The join key does not change - a derived type
    -- declares the root key its atoms carry.
    FROM sides s
    JOIN {LEDGER_TABLE} e
      ON e.subject_type = ANY(%(stypes)s)
     AND e.subject_keys->>%(skey)s = s.subject
    LEFT JOIN subj_obs o ON o.subject = s.subject
    WHERE e.object_payload IS NOT NULL
),
flat(id, sid, side, predicate, ord_code, path, val, vtype) AS (
    SELECT a.id, a.sid, a.side, a.predicate, a.ord_code,
           ARRAY[t.k], t.v, jsonb_typeof(t.v)
    FROM atoms a, jsonb_each(a.payload) AS t(k, v)
  UNION ALL
    SELECT f.id, f.sid, f.side, f.predicate, f.ord_code,
           f.path || t2.k, t2.v, jsonb_typeof(t2.v)
    FROM flat f, jsonb_each(f.val) AS t2(k, v)
    WHERE f.vtype = 'object' AND array_length(f.path, 1) < %(max_depth)s
),
-- 🔴 THE NUMERIC SIDE COLLAPSES TO THE SUBJECT FIRST, AND THAT IS THE WHOLE DESIGN.
-- A wafer carrying 141 `processed_with` atoms would otherwise contribute 141 readings of
-- its own bond temperature, shrinking every interval by an order of magnitude and putting
-- noise on top of the ranking — the same mistake this module's header refuses for the
-- categorical side, stated there about packages. So one subject gives ONE reading (its own
-- mean), and the contrast is then between two sets of subject readings. `flat` is a
-- recursive CTE and is therefore materialised once, so this second aggregation re-reads it
-- rather than re-walking the payloads.
subj_num AS (
    SELECT f.predicate, f.path, f.sid, f.side,
           avg((f.val #>> '{{}}')::numeric)               AS sval,
           count(*)                                       AS leaves,
           count(*) FILTER (WHERE f.ord_code = 1)         AS n_before,
           count(*) FILTER (WHERE f.ord_code = 2)         AS n_after,
           count(*) FILTER (WHERE f.ord_code = 0)         AS n_no_obs,
           (array_agg(f.id::text))[1]                     AS a_ref
    FROM flat f
    WHERE f.vtype = 'number'
    GROUP BY 1, 2, 3, 4
)
SELECT f.predicate,
       array_to_string(f.path, '.') AS field,
       GROUPING(CASE WHEN f.vtype IN ('string','boolean')
                     THEN f.val #>> '{{}}' END) AS is_field_row,
       CASE WHEN f.vtype IN ('string','boolean') THEN f.val #>> '{{}}' END AS value,
       count(DISTINCT f.sid) FILTER (WHERE f.side = 'case')           AS case_n,
       count(DISTINCT f.sid) FILTER (WHERE f.side = 'control')        AS control_n,
       count(*)                                                       AS leaves,
       count(*) FILTER (WHERE f.vtype = 'number')                     AS numeric_leaves,
       count(*) FILTER (WHERE f.vtype = 'null')                       AS null_leaves,
       min(f.vtype)                                                   AS vtype_min,
       max(f.vtype)                                                   AS vtype_max,
       count(*) FILTER (WHERE f.ord_code = 1)                         AS n_before,
       count(*) FILTER (WHERE f.ord_code = 2)                         AS n_after,
       count(*) FILTER (WHERE f.ord_code = 0)                         AS n_no_obs_time,
       avg(CASE WHEN f.vtype = 'number' AND f.side = 'case'
                THEN (f.val #>> '{{}}')::numeric END)                 AS case_avg,
       avg(CASE WHEN f.vtype = 'number' AND f.side = 'control'
                THEN (f.val #>> '{{}}')::numeric END)                 AS control_avg,
       min(CASE WHEN f.vtype = 'number'
                THEN (f.val #>> '{{}}')::numeric END)                 AS num_min,
       max(CASE WHEN f.vtype = 'number'
                THEN (f.val #>> '{{}}')::numeric END)                 AS num_max,
       (array_agg(f.id::text) FILTER (WHERE f.side = 'case'))[1:%(sample_n)s] AS refs,
       NULL::numeric                                                  AS case_sd,
       NULL::numeric                                                  AS control_sd
FROM flat f
WHERE f.vtype <> 'object'
GROUP BY GROUPING SETS ((f.predicate, f.path,
                         CASE WHEN f.vtype IN ('string','boolean')
                              THEN f.val #>> '{{}}' END),
                        (f.predicate, f.path))
UNION ALL
-- `is_field_row = 2` — a THIRD row kind beside the value rows (0) and the field coverage
-- row (1): one per numeric field, carrying both sides' subject-level moments.
SELECT n.predicate,
       array_to_string(n.path, '.'),
       2,
       NULL::text,
       count(*) FILTER (WHERE n.side = 'case'),
       count(*) FILTER (WHERE n.side = 'control'),
       sum(n.leaves)::bigint,
       sum(n.leaves)::bigint,
       0::bigint,
       'number'::text, 'number'::text,
       sum(n.n_before)::bigint, sum(n.n_after)::bigint, sum(n.n_no_obs)::bigint,
       avg(n.sval) FILTER (WHERE n.side = 'case'),
       avg(n.sval) FILTER (WHERE n.side = 'control'),
       min(n.sval), max(n.sval),
       (array_agg(n.a_ref) FILTER (WHERE n.side = 'case'))[1:%(sample_n)s],
       stddev_samp(n.sval) FILTER (WHERE n.side = 'case'),
       stddev_samp(n.sval) FILTER (WHERE n.side = 'control')
FROM subj_num n
GROUP BY 1, 2
"""
    return _fetch(connection, sql, params)


_COLS = ("predicate", "field", "is_field_row", "value", "case_n", "control_n",
         "leaves", "numeric_leaves", "null_leaves", "vtype_min", "vtype_max",
         "n_before", "n_after", "n_no_obs_time", "case_avg", "control_avg",
         "num_min", "num_max", "refs", "case_sd", "control_sd")

#: `is_field_row` discriminates three row kinds out of one scan.
ROW_VALUE, ROW_FIELD, ROW_NUMERIC = 0, 1, 2


def _shape(rows, case_of, control_of, walk_cfg):
    """Raw grouping-sets rows into `(fields[], candidates[])`.

    The field rows carry 「귀속 N/M」 — how many subjects on each side the field reaches at
    all — and every candidate row is handed its own field's coverage, because a rate whose
    denominator has not been checked is the thing this console refuses to print.
    """
    fields, values, nums = {}, [], {}
    for raw in rows:
        row = dict(zip(_COLS, raw))
        key = (row["predicate"], row["field"])
        kind = int(row["is_field_row"])
        if kind == ROW_FIELD:
            fields[key] = row
        elif kind == ROW_NUMERIC:
            nums[key] = row
        else:
            values.append(row)

    out_fields = []
    for key, row in sorted(fields.items()):
        compare = _compare_kind(row)
        out_fields.append({
            "predicate": row["predicate"], "field": row["field"],
            "candidate_key": f"{row['predicate']}:{row['field']}",
            "compare": compare,
            "value_type": row["vtype_min"] if row["vtype_min"] == row["vtype_max"]
                          else f"mixed({row['vtype_min']}/{row['vtype_max']})",
            "leaves": int(row["leaves"]),
            # 🔴 「귀속 N/M」, both sides, on every field. Not decoration: a field that
            # reaches 60% of one side and 100% of the other will otherwise report a
            # data gap as a measured difference.
            "attributed": {
                "case": {"n": int(row["case_n"]), "of": case_of},
                "control": {"n": int(row["control_n"]), "of": control_of},
            },
            "distinct_values": None,
            "high_cardinality": False,
            "numeric": (None if compare != COMPARE_DISTRIBUTION
                        else _field_numeric(nums.get(key), row)),
        })
    by_key = {(f["predicate"], f["field"]): f for f in out_fields}

    counts = {}
    for row in values:
        if row["value"] is None:
            continue                      # numeric / null leaves: the field row speaks
        key = (row["predicate"], row["field"])
        counts[key] = counts.get(key, 0) + 1
    cap = int(walk_cfg["high_cardinality_at"])
    for key, n in counts.items():
        if key in by_key:
            by_key[key]["distinct_values"] = n
            by_key[key]["high_cardinality"] = n > cap

    candidates = []
    for row in values:
        if row["value"] is None:
            continue
        key = (row["predicate"], row["field"])
        field = by_key.get(key)
        # An identifier-like field is not a factor: 55,419 distinct `observed.run_uid`
        # values, one carrier each. Its VALUE rows are dropped here rather than scored and
        # then buried — but the FIELD row stays with its count and `notes` names it, so a
        # field that is merely noisy never becomes indistinguishable from one that was
        # never translated.
        if field is not None and field.get("high_cardinality"):
            continue
        candidates.append({"row": row, "field": field, "case_of": case_of,
                           "control_of": control_of, "kind": COMPARE_CATEGORICAL})

    # 🔴 ONE NUMERIC CANDIDATE PER NUMERIC FIELD — bounded by the field count rather than
    # by a value explosion, which is why the numeric side needs no high-cardinality rule.
    # It is emitted whether or not it turns out to be comparable: 「비교 불가」 is an
    # answer and it belongs on the same list as the answers that ARE ratios.
    for field in out_fields:
        if field["compare"] != COMPARE_DISTRIBUTION:
            continue
        nrow = nums.get((field["predicate"], field["field"]))
        if nrow is None:
            continue
        candidates.append({"row": nrow, "field": field, "case_of": case_of,
                           "control_of": control_of, "kind": COMPARE_DISTRIBUTION})
    return out_fields, candidates


def _field_numeric(nrow, field_row):
    """The `fields[]` summary for a numeric field — SUBJECT-level once the walk measured it.

    The fallback keeps the older leaf-level pair rather than reporting nothing, and says so:
    a field whose summary silently changed unit would be worse than one that admits which
    unit it is in.
    """
    if nrow is None:
        return {"case_mean": _round(field_row["case_avg"]),
                "control_mean": _round(field_row["control_avg"]),
                "min": _round(field_row["num_min"]), "max": _round(field_row["num_max"]),
                "unit_of_summary": "leaf",
                "state": "summary_only",
                "message": "주어 단위 요약 미측정 — 잎 단위 평균만"}
    return {"case_mean": _round(nrow["case_avg"]),
            "control_mean": _round(nrow["control_avg"]),
            "case_sd": _round(nrow["case_sd"]), "control_sd": _round(nrow["control_sd"]),
            "case_subjects": int(nrow["case_n"]), "control_subjects": int(nrow["control_n"]),
            "min": _round(nrow["num_min"]), "max": _round(nrow["num_max"]),
            "unit_of_summary": "subject",
            "state": "compared",
            "message": "주어별 평균끼리 평균비로 대조 — 같은 순위에 참여"}


def _compare_kind(field_row):
    """The JSON type decides — the owner's 「필드 유형이 비교 방식을 자동 결정」."""
    if int(field_row["null_leaves"]) == int(field_row["leaves"]):
        return COMPARE_NULL
    if int(field_row["numeric_leaves"]) == int(field_row["leaves"]):
        return COMPARE_DISTRIBUTION
    return COMPARE_CATEGORICAL


# ------------------------------------------------------------------------ scoring
def _score(item, contrast_cfg, min_support):
    """One candidate into the pinned row. Both denominators, twice: side and attributed."""
    if item.get("kind") == COMPARE_DISTRIBUTION:
        return _score_numeric(item, contrast_cfg, min_support)
    row, field = item["row"], item["field"]
    case_n, control_n = int(row["case_n"]), int(row["control_n"])
    if case_n < min_support and control_n < min_support:
        return None

    case_of, control_of = item["case_of"], item["control_of"]
    att = (field or {}).get("attributed") or {}
    case_att = int((att.get("case") or {}).get("n") or 0)
    control_att = int((att.get("control") or {}).get("n") or 0)
    predicate, fname = row["predicate"], row["field"]

    out = {
        "candidate_key": f"{predicate}:{fname}",
        "predicate": predicate,
        "field": fname,
        "value": row["value"],
        # `axis`/`label` keep the axes-engine spelling so one renderer serves both, but
        # the label is DECORATION here and never a qualification to be compared.
        "axis": f"{predicate}·{fname}",
        "label": f"{predicate}·{fname} = {row['value']}",
        "about": "walk",
        "compare": COMPARE_CATEGORICAL,
        "unit": "subject",
        "case": _side(case_n, case_of, case_att),
        "control": _side(control_n, control_of, control_att),
        # 🔴 Never repurposed: under the walk the comparison is scope-vs-control, so the
        # found/clean split the axes engine fills is `null` here rather than quietly
        # holding different numbers under the same two names.
        "found": None, "clean_scanned": None,
        "enrichment": None, "enrichment_ci": None, "rate_delta": None,
        "enrichment_state": UNDETERMINABLE,
        "enrichment_basis": "attributed",
        "reason": None,
        "evidence_refs": [{"relation": LEDGER_TABLE, "key_column": "id", "key": r,
                           "population": "case"}
                          for r in (row["refs"] or []) if r],
        "evidence_ref_count": case_n,
        "_timing": {"before": int(row["n_before"]), "after": int(row["n_after"]),
                    "no_obs_time": int(row["n_no_obs_time"])},
    }

    if not case_att or not control_att:
        # 🔴 「귀속 0/75」 IS AN ANSWER, AND IT IS NOT ZERO. Measured on this box: the
        # excursion lots carry no `observed` atoms at all (that translation predates
        # them), so `observed·finding_kind = void` reaches 0 of 75 case subjects and
        # 2,500 of 2,500 control subjects. Scored against the SIDE size that reads as
        # 「이 랏들엔 보이드가 없다」 — the exact inversion of the truth. Against the
        # ATTRIBUTED denominator there is no ratio to compute, the verdict stays
        # `undeterminable`, and the coverage field says why.
        out["reason"] = REASON_NO_ATTRIBUTED
        return out
    rate_case = case_n / case_att
    rate_control = control_n / control_att
    out["rate_delta"] = _round(rate_case - rate_control)
    if rate_control == 0:
        # Present in the case side and in NO control subject. NOT「무한대로 농축」: an
        # unbounded point estimate would sort above every measured one, so `enrichment`
        # stays null and the Katz interval's finite lower bound does the ranking.
        out["reason"] = REASON_ABSENT_FROM_CONTROL
    else:
        out["enrichment"] = _round(rate_case / rate_control)
    low, high = _ratio_interval(case_n, case_att, control_n, control_att)
    out["enrichment_ci"] = [_round(low), _round(high)]
    if low >= contrast_cfg["enriched_at"]:
        out["enrichment_state"] = ENRICHED
    elif high <= contrast_cfg["depleted_at"]:
        out["enrichment_state"] = DEPLETED
    else:
        out["enrichment_state"] = FLAT
    return out


def _score_numeric(item, contrast_cfg, min_support):
    """One NUMERIC field into the SAME pinned row — same gates, same band, same columns.

    🔴 THE EFFECT IS A MEAN RATIO, ON PURPOSE, AND IT IS THE SAME SCALE THE CATEGORICAL
    SIDE ALREADY USES. `enrichment` is 「몇 배」 either way, so `defaults.contrast`'s
    declared band (`enriched_at` / `depleted_at`) bands both, `_gate_real` reads the same
    95% lower bound, and `_rank_key` compares like with like. That is also the answer to
    multiplicity: 33 numeric fields entering the ranking are held to the SAME rule that
    keeps 51 categorical candidates from promoting noise — an interval bound clearing an
    operator-declared band, not a p-value, and `min_support` on the same subject counts.

    🔴 AND THE INTERVAL IS BETWEEN-SUBJECT. `sd` here is the spread of the SUBJECTS' own
    means (the SQL collapsed each subject first), so the delta-method interval on the log
    ratio is measured against the noise between wafers, not between the leaves of one wafer.

    Not comparable is a VERDICT, not a removal — see `REASON_NOT_COMPARABLE_SCALE`.
    """
    row, field = item["row"], item["field"]
    case_n, control_n = int(row["case_n"]), int(row["control_n"])
    if case_n < min_support and control_n < min_support:
        return None

    case_of, control_of = item["case_of"], item["control_of"]
    predicate, fname = row["predicate"], row["field"]
    case_mean, control_mean = _num(row["case_avg"]), _num(row["control_avg"])
    case_sd, control_sd = _num(row["case_sd"]), _num(row["control_sd"])

    numeric = {
        "effect": "mean_ratio",
        "unit_of_observation": "subject",
        "case": {"mean": _round(case_mean), "sd": _round(case_sd), "subjects": case_n},
        "control": {"mean": _round(control_mean), "sd": _round(control_sd),
                    "subjects": control_n},
        "range": {"min": _round(row["num_min"]), "max": _round(row["num_max"])},
        "mean_delta": (None if case_mean is None or control_mean is None
                       else _round(case_mean - control_mean)),
        # 🔴 REPORTED, NEVER RANKED ON. The band is a RATIO band, so a quantity that moves
        # 3% against a spread of 0.1% reads 「차이 없음」 while being wildly separated.
        # `std_diff` is that separation, carried so the gap is visible instead of silently
        # deciding nothing — a second promotion rule is a design decision, not tonight's.
        "std_diff": _std_diff(case_mean, case_sd, case_n,
                              control_mean, control_sd, control_n),
        "state": "compared", "message": None,
    }

    out = {
        "candidate_key": f"{predicate}:{fname}",
        "predicate": predicate,
        "field": fname,
        # No `value`: the candidate IS the field. A numeric row that invented a value
        # would collide with the categorical row contract the console renders.
        "value": None,
        "axis": f"{predicate}·{fname}",
        "label": _numeric_label(predicate, fname, case_mean, control_mean),
        "about": "walk",
        "compare": COMPARE_DISTRIBUTION,
        "unit": "subject",
        # 🔴 「귀속 51/75」 SURVIVES INTO THE ROW. For a quantity every attributed subject
        # carries a reading, so `n` and `attributed_of` coincide — and `coverage` is then
        # exactly the gap the owner named (`clamp_kN`: 51 of 75 case, 587 of 834 control).
        # Averaging over the missing would be the one thing this console refuses to print.
        "case": _side(case_n, case_of, case_n),
        "control": _side(control_n, control_of, control_n),
        "found": None, "clean_scanned": None,
        "enrichment": None, "enrichment_ci": None,
        # `rate_delta` stays null: a difference of means is not a difference of rates, and
        # putting one under the other's name is the reuse this module refuses elsewhere.
        # It travels as `numeric.mean_delta` instead.
        "rate_delta": None,
        "enrichment_state": UNDETERMINABLE,
        "enrichment_basis": "attributed",
        "reason": None,
        "numeric": numeric,
        "evidence_refs": [{"relation": LEDGER_TABLE, "key_column": "id", "key": r,
                           "population": "case"}
                          for r in (row["refs"] or []) if r],
        "evidence_ref_count": case_n,
        "_timing": {"before": int(row["n_before"]), "after": int(row["n_after"]),
                    "no_obs_time": int(row["n_no_obs_time"])},
    }

    if not case_n or not control_n or case_mean is None or control_mean is None:
        out["reason"] = REASON_NO_ATTRIBUTED
        numeric.update({"state": "not_comparable",
                        "message": "한쪽 귀속 0 — 대조할 값이 없음"})
        return out
    if case_mean <= 0 or control_mean <= 0:
        # 🔴 「비교 불가」 AND IT STAYS ON THE LIST. A quantity centred on zero (or signed)
        # has no ratio; measured on this box `params_actual.purge_delay_s` is 0.0 on both
        # sides. Dropping it would leave a reader thinking the walk never saw it.
        out["reason"] = REASON_NOT_COMPARABLE_SCALE
        numeric.update({"state": "not_comparable",
                        "message": "평균이 0 이하 — 비율 척도 불가 (차이만 보고)"})
        return out

    ratio = case_mean / control_mean
    out["enrichment"] = _round(ratio)
    se = _log_ratio_se(case_mean, case_sd, case_n, control_mean, control_sd, control_n)
    if se is None:
        # One side has fewer than two subjects, so it has no spread of its own. The point
        # estimate stands and `real` reports `unknown` — never `fail`.
        out["reason"] = REASON_NO_DISPERSION
        numeric.update({"state": "point_only",
                        "message": "주어 2개 미만 — 산포 없음, 구간 불가"})
        return out
    half = _Z95 * se
    low, high = ratio * math.exp(-half), ratio * math.exp(half)
    out["enrichment_ci"] = [_round(low), _round(high)]
    if se == 0.0:
        # Both sides are constant. The interval is a point, which is TRUE of this sample and
        # overconfident about the next one, so the row says which it is.
        out["reason"] = REASON_ZERO_DISPERSION
        numeric["message"] = "양쪽 모두 상수 — 구간 폭 0 (이 표본에 한해)"
    if low >= contrast_cfg["enriched_at"]:
        out["enrichment_state"] = ENRICHED
    elif high <= contrast_cfg["depleted_at"]:
        out["enrichment_state"] = DEPLETED
    else:
        out["enrichment_state"] = FLAT
    return out


def _log_ratio_se(m1, s1, n1, m2, s2, n2):
    """Delta-method standard error of `log(m1/m2)`. `None` when a side has no spread."""
    if s1 is None or s2 is None or n1 < 1 or n2 < 1:
        return None
    return math.sqrt(s1 * s1 / (n1 * m1 * m1) + s2 * s2 / (n2 * m2 * m2))


def _std_diff(m1, s1, n1, m2, s2, n2):
    """Standardised mean difference (pooled). Reported beside the ratio, never ranked on."""
    if None in (m1, m2, s1, s2) or (n1 + n2) < 3:
        return None
    var = ((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / float(n1 + n2 - 2)
    if var <= 0:
        return None
    return _round((m1 - m2) / math.sqrt(var))


def _numeric_label(predicate, fname, case_mean, control_mean):
    """🔴 THE NUMBERS RIDE IN THE LABEL. The console's 마킹/나머지 columns hold counts, so
    for a quantity the two means would otherwise be nowhere on the row and the reader would
    see 「2.73×」 with nothing to read it against."""
    return (f"{predicate}·{fname} 평균 "
            f"{_fmt_num(case_mean)} ↔ {_fmt_num(control_mean)}")


def _fmt_num(value):
    if value is None:
        return "—"
    size = abs(value)
    if size >= 10000:
        return "%.0f" % value
    if size >= 1:
        return "%.2f" % value
    return "%.4g" % value


def _num(value):
    return None if value is None else float(value)


def _side(n, of, attributed_of):
    """One side of one row. Two denominators and never a bare ratio: `of` is the side,
    `attributed_of` is how much of that side the FIELD reaches, and `coverage` is the
    「귀속 N/M」 the client prints beside the number."""
    return {
        "n": n, "of": of,
        "rate": _round(n / of) if of else None,
        "attributed_of": attributed_of,
        "rate_attributed": _round(n / attributed_of) if attributed_of else None,
        "coverage": _round(attributed_of / of) if of else None,
    }


def _ratio_interval(a, n1, b, n2):
    """95% Katz interval for the rate ratio, Haldane-corrected. One spelling, reused."""
    return sib._ratio_interval(a, n1, b, n2)


# -------------------------------------------------------------------------- gates
def _attach_gates(row, kind, graph, contrast_cfg):
    """The three gates, each with its own basis and its own `unknown`."""
    row["gates"] = {
        "real": _gate_real(row, contrast_cfg),
        "upstream": _gate_upstream(row),
        "mechanism": mechanism_gate.verdict(kind, row["candidate_key"], graph),
    }
    row.pop("_timing", None)
    verdicts = [row["gates"][g]["verdict"] for g in ("real", "upstream", "mechanism")]
    row["gate_summary"] = {
        "code": "".join(_GATE_CODE[v] for v in verdicts),
        "passed": sum(1 for v in verdicts if v == GATE_PASS),
        "unknown": sum(1 for v in verdicts if v == GATE_UNKNOWN),
        "failed": sum(1 for v in verdicts if v == GATE_FAIL),
        "bias_candidate": row["gates"]["mechanism"]["verdict"]
                          == mechanism_gate.VERDICT_BIAS,
    }


#: One character per gate for a compact, unambiguous badge: `✓` pass, `—` unknown,
#: `✗` fail, `~` bias candidate. The client may render its own; this is the token.
_GATE_CODE = {GATE_PASS: "P", GATE_UNKNOWN: "-", GATE_FAIL: "X",
              mechanism_gate.VERDICT_BIAS: "B"}


#: Why an interval could not be formed, in that case's own words.
_NO_INTERVAL_MESSAGE = {
    REASON_NOT_COMPARABLE_SCALE: "비교 불가 — 비율 척도에 올릴 수 없는 값",
    REASON_NO_DISPERSION: "산포를 낼 주어가 부족",
}


def _gate_real(row, contrast_cfg):
    """실재 — is the difference bigger than its own noise? The Katz lower bound decides.

    Ranking by the point estimate puts the smallest samples on top; this project measured
    that on `finding=delam` and the interval is the standing answer.
    """
    ci = row.get("enrichment_ci")
    if not ci or ci[0] is None:
        reason = row.get("reason") or "no_interval"
        return {"verdict": GATE_UNKNOWN, "basis": "katz_lower_bound",
                "reason": reason,
                # 🔴 The sentence names the ACTUAL obstacle. A numeric field refused for
                # its scale is not「분모가 없다」, and one sentence covering both would
                # send a reader looking for a missing denominator that is right there.
                "message": _NO_INTERVAL_MESSAGE.get(reason, "구간을 낼 분모가 없음"),
                "detail": None}
    low, high = ci
    state = row["enrichment_state"]
    verdict = GATE_PASS if state in (ENRICHED, DEPLETED) else GATE_FAIL
    return {
        "verdict": verdict, "basis": "katz_lower_bound",
        "reason": state,
        "message": ("표본 대비 실재" if verdict == GATE_PASS
                    else "구간이 기준 밴드를 넘지 못함 — 미끼일 수 있음"),
        "detail": {"ci_low": low, "ci_high": high,
                   "enriched_at": contrast_cfg["enriched_at"],
                   "depleted_at": contrast_cfg["depleted_at"]},
    }


def _gate_upstream(row):
    """상류 — did the atom happen BEFORE the observation it is meant to explain?

    Measured per atom against that subject's FIRST run of the kind's methods, so an
    `observed` leaf (which is the finding itself) correctly fails, and a `processed_with`
    leaf asserted weeks earlier correctly passes.

    🔴 `unknown` when nothing was comparable, and it is NOT `fail`. A subject with no run
    time gives no evidence either way, and folding that into a failure would let a missing
    timestamp look like a refuted causal order.
    """
    timing = row.get("_timing") or {}
    before, after = int(timing.get("before", 0)), int(timing.get("after", 0))
    compared = before + after
    detail = {"atoms_before": before, "atoms_after": after,
              "atoms_compared": compared,
              "atoms_without_observation_time": int(timing.get("no_obs_time", 0))}
    if not compared:
        return {"verdict": GATE_UNKNOWN, "basis": "occurred_at",
                "reason": "no_comparable_time",
                "message": "비교할 관측 시각이 없음", "detail": detail}
    if after == 0:
        return {"verdict": GATE_PASS, "basis": "occurred_at", "reason": "all_before",
                "message": "모든 원자가 관측보다 앞섬", "detail": detail}
    if before == 0:
        return {"verdict": GATE_FAIL, "basis": "occurred_at", "reason": "all_after",
                "message": "관측과 같거나 뒤 — 결과이지 원인일 수 없음", "detail": detail}
    # Mixed IS a judgement, not an absence of one: some carriers were asserted after their
    # own observation, so the ordering claim does not hold for this candidate as stated.
    return {"verdict": GATE_FAIL, "basis": "occurred_at", "reason": "mixed_order",
            "message": "일부 원자가 관측 뒤 — 상류라고 단언 불가", "detail": detail}


def _rank_key(row):
    """관문 통과 사전식, 동률은 효과 크기 — the brief's ranking, literally."""
    gates = row.get("gates") or {}
    order = tuple(_GATE_ORDER.get((gates.get(g) or {}).get("verdict"), 9)
                  for g in ("real", "upstream", "mechanism"))
    ci_low = (row.get("enrichment_ci") or [0])[0] or 0
    return order + (-float(ci_low), -int(row["case"]["n"]))


def _gate_legend():
    """What the three columns mean, served so the client never hardcodes the vocabulary."""
    return [
        {"id": "real", "label": "실재", "basis": "katz_lower_bound",
         "doc": "표본 크기 대비 우연이 아닌가 — 신뢰구간 하한"},
        {"id": "upstream", "label": "상류", "basis": "occurred_at",
         "doc": "그 요인이 관측보다 앞선 사건인가"},
        {"id": "mechanism", "label": "기전", "basis": mechanism_gate.CONFIG_FILENAME,
         "doc": "그 요인에서 이 불량으로 가는 경로가 선언돼 있는가"},
    ]


def _note_high_cardinality(envelope, fields, walk_cfg):
    """Identifier-like fields, named rather than dropped.

    A field with 55,000 distinct values (`observed.run_uid`, measured) is not a factor —
    every value has one carrier and the ranking would fill with noise the interval already
    demotes. It stays in `fields` with its count, and this note says why its values are not
    worth reading, because a field that vanished silently is indistinguishable from a field
    that was never translated.
    """
    cap = int(walk_cfg["high_cardinality_at"])
    noisy = [f for f in fields if f.get("high_cardinality")]
    if noisy:
        envelope["notes"].append({
            "note": "high_cardinality_fields", "at": cap,
            "fields": [{"candidate_key": f["candidate_key"],
                        "distinct_values": f["distinct_values"]} for f in noisy],
            "message": ("값이 너무 많아 사실상 식별자인 필드 — 필드 행은 남고 값 단위 "
                        "비교만 생략했다 (숨긴 것이 아니라 뜻이 없어서)")})


def _note_flat_but_separated(envelope, scored, walk_cfg):
    """🔴 THE DOUBT, ON SCREEN RATHER THAN ONLY IN A REPORT.

    A numeric candidate the ratio band called 「차이 없음」 while the two sides are far
    apart relative to their own spread is the one place this scoring can quietly lose a
    real cause. Measured on the demo fixture: `params_actual.temp_C` is 150.0 vs 145.3 —
    a declared cause with a mechanism edge to `void` — and lands at 1.03x, flat, because
    the band counts multiples. Naming it costs a sentence; promoting it would be a second
    ranking rule invented at the console, which is a design decision and not this round's.
    """
    at = float(walk_cfg["std_diff_note_at"])
    hits = []
    for row in scored:
        if row.get("compare") != COMPARE_DISTRIBUTION:
            continue
        if row.get("enrichment_state") != FLAT:
            continue
        spread = (row.get("numeric") or {}).get("std_diff")
        if spread is None or abs(spread) < at:
            continue
        hits.append(row)
    if not hits:
        return
    hits.sort(key=lambda r: -abs(r["numeric"]["std_diff"]))
    named = ", ".join(f"{r['candidate_key']}({r['enrichment']}배, 산포대비 "
                      f"{r['numeric']['std_diff']})" for r in hits)
    envelope["notes"].append({
        "note": "flat_ratio_but_separated", "at": at,
        "fields": [{"candidate_key": r["candidate_key"],
                    "enrichment": r["enrichment"],
                    "std_diff": r["numeric"]["std_diff"]} for r in hits],
        "message": (f"배수로는 「차이 없음」이나 산포 대비로는 크게 갈린 수치 — {named}. "
                    f"밴드가 «배수» 기준이라 단위에 좌우된다(°C↔K). 순위에는 미반영")})


def _round(value, places=6):
    return None if value is None else round(float(value), places)
