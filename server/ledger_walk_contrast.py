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

import finding_kinds
import ledger_siblings as sib
import mechanism_gate
from ledger_trace import _fetch, relation_exists

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
REASON_NO_ATTRIBUTED = "no_attributed_denominator"

#: Comparison kinds, decided by the JSON type of the leaf and by nothing else — the owner's
#: rule 「필드 유형이 비교 방식을 자동 결정」. `categorical` gets a share contrast;
#: `distribution` gets per-side summary statistics and is ranked by R7, not here.
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

    sides = _sides(connection, plan, source, axis, subject, values, has_runs)
    envelope["scope"].update(_scope_block(sides, has_runs))
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
        f"marked AS (SELECT p.unit_id, p.is_found, p.{subject.column} AS subject,\n"
        f"                  (a.{axis.column}::text = ANY(%(scope_values)s)) AS in_scope\n"
        f"           FROM pop p JOIN {source.relation} a "
        f"ON {sib._join_on('p', 'a', source.join)}{narrow})\n"
        f"SELECT subject,\n"
        f"       CASE WHEN bool_and(in_scope) THEN 'case'\n"
        f"            WHEN bool_or(in_scope) THEN 'mixed'\n"
        f"            ELSE 'control' END AS side,\n"
        f"       count(*) AS units, {found_expr} AS found_units\n"
        f"FROM marked GROUP BY subject")
    out = {s: {"subjects": [], "units": 0, "found_units": 0}
           for s in (SIDE_CASE, SIDE_CONTROL, SIDE_MIXED)}
    for subject_id, side, units_n, found_n in _fetch(connection, sql, params):
        bucket = out[side]
        bucket["subjects"].append(subject_id)
        bucket["units"] += int(units_n)
        bucket["found_units"] += int(found_n or 0)
    for bucket in out.values():
        bucket["subjects"].sort()
    return out


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
    sql = (f"SELECT count(*) FROM {LEDGER_TABLE} "
           f"WHERE subject_type = %(stype)s "
           f"AND subject_keys->>%(skey)s = ANY(%(ids)s)")
    total = int(_fetch(connection, sql, {"stype": subject.type, "skey": subject.key,
                                         "ids": list(sample_ids)})[0][0])
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
        "stype": subject.type, "skey": subject.key,
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
    FROM sides s
    JOIN {LEDGER_TABLE} e
      ON e.subject_type = %(stype)s
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
       (array_agg(f.id::text) FILTER (WHERE f.side = 'case'))[1:%(sample_n)s] AS refs
FROM flat f
WHERE f.vtype <> 'object'
GROUP BY GROUPING SETS ((f.predicate, f.path,
                         CASE WHEN f.vtype IN ('string','boolean')
                              THEN f.val #>> '{{}}' END),
                        (f.predicate, f.path))
"""
    return _fetch(connection, sql, params)


_COLS = ("predicate", "field", "is_field_row", "value", "case_n", "control_n",
         "leaves", "numeric_leaves", "null_leaves", "vtype_min", "vtype_max",
         "n_before", "n_after", "n_no_obs_time", "case_avg", "control_avg",
         "num_min", "num_max", "refs")


def _shape(rows, case_of, control_of, walk_cfg):
    """Raw grouping-sets rows into `(fields[], candidates[])`.

    The field rows carry 「귀속 N/M」 — how many subjects on each side the field reaches at
    all — and every candidate row is handed its own field's coverage, because a rate whose
    denominator has not been checked is the thing this console refuses to print.
    """
    fields, values = {}, []
    for raw in rows:
        row = dict(zip(_COLS, raw))
        key = (row["predicate"], row["field"])
        if int(row["is_field_row"]) == 1:
            fields[key] = row
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
            "numeric": (None if compare != COMPARE_DISTRIBUTION else {
                "case_mean": _round(row["case_avg"]),
                "control_mean": _round(row["control_avg"]),
                "min": _round(row["num_min"]), "max": _round(row["num_max"]),
                "state": "summary_only",
                "message": "수치 분포 대조는 R7 — 지금은 양쪽 요약만",
            }),
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
                           "control_of": control_of})
    return out_fields, candidates


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


def _gate_real(row, contrast_cfg):
    """실재 — is the difference bigger than its own noise? The Katz lower bound decides.

    Ranking by the point estimate puts the smallest samples on top; this project measured
    that on `finding=delam` and the interval is the standing answer.
    """
    ci = row.get("enrichment_ci")
    if not ci or ci[0] is None:
        return {"verdict": GATE_UNKNOWN, "basis": "katz_lower_bound",
                "reason": row.get("reason") or "no_interval",
                "message": "구간을 낼 분모가 없음", "detail": None}
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


def _round(value, places=6):
    return None if value is None else round(float(value), places)
