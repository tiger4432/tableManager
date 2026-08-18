# -*- coding: utf-8 -*-
"""Journey contrast — TWO marked subjects, side by side, along the path they walked.

🔴 WHY THIS IS NOT THE RANKING RAIL
------------------------------------
Owner, 2026-08-14, looking at the contrast panel::

    「`processed_with·eqp = SYN-BD-03` 이렇게 나오는데 이게 뭔 공정 뭔 설비인지 어떻게 알아」
    「어느 공정 또는 어느 계측값이 어떤 차이가 있다는 건지 모르겠음」

A ranking table answers 「which factor separates the two groups」. With exactly two
subjects there are no groups, so the question becomes 「where did these two part ways」 and
the answer is a SEQUENCE, not a list. This module rearranges atoms the ledger already
holds into that sequence. It computes no new facts.

🔴 NO GROUP STATISTICS. NOT EVEN AS `null`.
--------------------------------------------
Two subjects cannot support a rate, a ratio, a confidence interval or the 「우연 아님」
(실재) gate, and `ledger_walk_contrast`'s three-gate ranking is therefore NOT reused here.
The two gates that still mean something at n=2 travel: 「시간상 앞섬」 (`upstream`, an
`occurred_at` comparison, which is a fact about two instants and needs no population) and
「물리 경로 있음」 (`mechanism`, a quotation of a declared graph). The third is DROPPED,
not emitted as null — a field that exists gets rendered eventually, and a confidence
interval computed over two wafers is the kind of confident falsehood this project treats
as worse than an error. `gates` in the response has TWO entries; `enrichment`,
`enrichment_ci`, `rate`, `rate_delta` and `std_diff` appear nowhere in this file.

🔴 THE SIX QUESTIONS, ANSWERED FROM THE ENVELOPE AND FROM NOWHERE ELSE
-----------------------------------------------------------------------
Owner (부칙): 「육하원칙에 의거해서 누가, 언제, 어디서, 무엇을, 어떻게, 왜」, then the
correction that settles the layering: 「엄밀히 원장은 누가·언제·어디서·무엇을·어떻게까지」
— the ledger answers FIVE and 「왜」 is not in it. So:

    누가 말했나  source_who                         envelope, always answerable
    누가 (주체)  the predicate's REQUIRED object fields minus the segment paths
                 (for `processed_with`: eqp + recipe) — DERIVED from the vocabulary
                 signature, not from a name typed here
    언제         occurred_at, in the declared display zone
    어디서       the segment — the step annotation this journey is keyed on
    무엇을       predicate + the leaf's path (labelled if the label layer names it)
    어떻게       the two values, each carrying its atom's RESOLUTION CLASS, which is what
                 tells 「둘 다 실측」 from 「한쪽은 레시피 설정값」 with no second spelling
                 of the setpoint/actual distinction anywhere
    왜           `mechanism_gate` — a QUOTATION of a declared model, never a ledger fact,
                 and marked as such (`layer: "declaration"`). An empty 왜 is NOT a missing
                 record: `state` is `not_declared` (nobody was asked) or
                 `declared_no_path` (the model was asked and said no) — never
                 `not_recorded` — and `is_missing_record` is `false`, which is what the
                 screen must render differently from 「기록 없음」.

There is ONE envelope→slot mapping and it runs for every atom of every predicate. A
predicate translated tomorrow renders in the same card. `test`-visible consequence: no
branch in this file reads a predicate name.

🔴 SEGMENTATION, AND THE ONE DECLARATION THE BRIEF DID NOT ANTICIPATE
----------------------------------------------------------------------
A segment is `(step_family, step, ordinal)`. `ordinal` is the rank of the atom's
`occurred_at` among that subject's atoms of that step WITHIN ONE RESOLUTION CLASS, and
that last clause is the whole trick: the equipment log and the recipe book both speak
about the same BONDING run, at different instants and at different classes (observation
vs inference), so ranking within a class pairs run 1 with run 1 and run 2 with run 2
instead of splitting one physical run into two segments. Measured on `assy_manager`:
`SYN-BW-101-06` carries BONDING at 08-10 01:05/01:45 (eqp log) and at 08-12 01:05/01:45
(recipe book) — four atoms, two runs.

WHERE the step name lives inside the payload is declared in `ledger_journey.json`
(`segments`). `server/ledger/vocabulary.py` says `processed_with`'s object requires
`['step','step_family','eqp','recipe']` but nothing says which of the four IS the step,
and reading it off position in that list would be a convention. See that file's `__doc`.

[SCALE] The atom fetch is `subject_keys->>'<key>' = ANY(<2 ids>)` narrowed by predicate —
the same shape `ledger_walk_contrast._atoms_per_subject` uses and with the same seam: a
materialised leaf projection repoints both by changing `LEDGER_TABLE` and one query.
`max_atoms_per_subject` bounds a pathological subject and the response says when it bit.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone

import finding_kinds
import ledger_siblings as sib
import ledger_trace
import mechanism_gate
from ledger_structure import CLASS_LABELS
from ledger_trace import _fetch, relation_exists, rollup_subject_types
from ledger_walk_contrast import (
    LEDGER_TABLE, WalkRequestError, parse_scope, resolve_marking_axis, _subject_of,
    REASON_LEDGER_ABSENT, REASON_MARKING_RELATION_ABSENT, REASON_NO_SCOPE,
    REASON_NO_SUBJECT_DECLARED, REASON_VALUE_UNKNOWN, REASON_NO_VALUE_MATCHED,
    STATE_ABSENT, STATE_EMPTY, STATE_READY, _values_in_axis,
)

logger = logging.getLogger("Ledger.Journey")

CONFIG_FILENAME = "ledger_journey.json"

#: This shape exists for exactly two subjects. Not a default, not a cap — the OWNER's
#: scope decision (brief P0-3 「WF 2장 마킹일 때만」), and groups of three or more keep the
#: ranking rail. Refusing rather than degrading is the point: a journey drawn for five
#: wafers would be a table with five columns, which is the thing being replaced.
ARITY = 2

#: The slot names the two subjects occupy. A/B and never 「the first one」 — the client
#: needs a stable handle for a column header and sorting by id would move the columns
#: when the operator marks the same pair in the other order.
SLOTS = ("A", "B")

#: Structured tokens. A client BRANCHES on these; the Korean beside them is for eyes.
REASON_NOT_A_PAIR = "scope_is_not_a_pair"
REASON_NO_JOURNEY_PREDICATE = "no_journey_predicate_declared"
REASON_NO_ATOMS = "no_journey_atoms_for_subjects"
REASON_CONFIG_UNREADABLE = "journey_config_unreadable"

#: Per-side presence of ONE item at ONE segment. 🔴 FOUR STATES, AND THREE OF THEM LOOK
#: LIKE 「없음」 FROM A DISTANCE. The brief demands they be told apart: an absent reading is
#: a fact about THAT subject at THAT segment, a JSON null is a source that spoke and said
#: nothing, and zero is a measurement.
VALUE_RECORDED = "recorded"          # a value is present (0 and false included)
VALUE_NULL = "recorded_null"         # the source emitted an explicit null
VALUE_ABSENT = "not_recorded"        # this subject has no leaf at this path here
VALUE_NO_SEGMENT = "segment_absent"  # this subject never walked this segment at all

#: Verdicts, for an item and for a segment.
VERDICT_SAME = "same"
VERDICT_DIVERGED = "diverged"
VERDICT_ONE_SIDED = "one_sided"

#: Which of the two gates ranks an item first inside its card. Same order as
#: `ledger_walk_contrast._GATE_ORDER` and deliberately the same shape — `unknown` above
#: `bias_candidate` above `fail`, because an unmodelled real difference is the DOE
#: candidate and burying it under a modelled non-difference is what the ranking is for.
_MECH_ORDER = {mechanism_gate.VERDICT_PASS: 0, mechanism_gate.VERDICT_UNKNOWN: 1,
               mechanism_gate.VERDICT_BIAS: 2, mechanism_gate.VERDICT_FAIL: 3}

_VERDICT_ORDER = {VERDICT_DIVERGED: 0, VERDICT_ONE_SIDED: 1, VERDICT_SAME: 2}

DEFAULTS = {
    "max_atoms_per_subject": 2000,
    "max_segments": 200,
    "sentence_items": 3,
}


# --------------------------------------------------------------- the declaration layer
class JourneyConfig:
    """`ledger_journey.json`, or an honest absence of it.

    🔴 AN ABSENT FILE IS A STATE, NOT AN ERROR — BUT THE TWO HALVES OF THIS FILE FAIL
    DIFFERENTLY, AND AN EARLIER VERSION OF THIS DOCSTRING GOT IT WRONG.

      * The three LABEL blocks (`step_labels`, `family_labels`, `field_labels`) narrow
        nothing. Delete them and every segment, item and value is still produced; only the
        Korean is lost and each name renders as its RAW PATH.
      * The `segments` block is STRUCTURAL. It is the only thing that says which predicate
        carries a journey and where the step name lives inside its payload, so with it gone
        there is no axis to draw and `journey()` answers `state: "absent"`,
        `reason: "no_journey_predicate_declared"`, `segments: []` — a degraded ANSWER, not
        an error, but emphatically not「같은 화면에서 이름만 빠진 것」.

    `state` says which world the screen is in so an operator can tell 「이 필드는 이름이
    없다」 from 「이 파일이 없다」.
    """

    __slots__ = ("segments", "step_labels", "family_labels", "field_labels",
                 "path", "origin", "state", "reason", "message")

    def __init__(self, raw, path, origin, state="declared", reason=None, message=None):
        self.path, self.origin = path, origin
        self.state, self.reason, self.message = state, reason, message
        raw = raw if isinstance(raw, dict) else {}
        self.segments = {}
        for name, spec in (raw.get("segments") or {}).items():
            if name.startswith("__") or not isinstance(spec, dict):
                continue
            name_path = spec.get("name_path")
            if not name_path:
                continue
            self.segments[str(name)] = {
                "name_path": str(name_path),
                "family_path": (str(spec["family_path"])
                                if spec.get("family_path") else None),
            }
        self.step_labels = _strip_doc(raw.get("step_labels"))
        self.family_labels = _strip_doc(raw.get("family_labels"))
        self.field_labels = _strip_doc(raw.get("field_labels"))

    # -- lookups -------------------------------------------------------------------
    def field(self, predicate, path):
        """Label + unit for one leaf. THREE spellings, most specific first.

        `<predicate>:<path>` then `<path>` then the bare leaf name. The bare leaf is what
        lets ONE entry serve `params_actual.pressure_MPa` and `params_setpoint.pressure_MPa`
        — the setpoint/actual distinction is carried by the atom's resolution class and does
        not want a second spelling here. `state` reports which spelling answered, or that
        none did, so an unnamed field is visibly unnamed instead of quietly English.
        """
        leaf = path.rsplit(".", 1)[-1]
        for key in (f"{predicate}:{path}", path, leaf):
            if key in self.field_labels:
                entry = self.field_labels[key]
                if isinstance(entry, dict):
                    return {"label": entry.get("label"), "unit": entry.get("unit"),
                            "state": "declared", "matched_on": key}
                return {"label": str(entry), "unit": None,
                        "state": "declared", "matched_on": key}
        return {"label": None, "unit": None, "state": "undeclared", "matched_on": None}

    def step(self, value):
        got = self.step_labels.get(value)
        return ({"label": str(got), "state": "declared"} if got
                else {"label": None, "state": "undeclared"})

    def family(self, value):
        got = self.family_labels.get(value)
        return ({"label": str(got), "state": "declared"} if got
                else {"label": None, "state": "undeclared"})

    def declaration(self):
        return {"state": self.state, "config": CONFIG_FILENAME, "origin": self.origin,
                "path": self.path, "reason": self.reason, "message": self.message,
                "journey_predicates": sorted(self.segments),
                "step_labels": len(self.step_labels),
                "family_labels": len(self.family_labels),
                "field_labels": len(self.field_labels)}


def _strip_doc(mapping):
    if not isinstance(mapping, dict):
        return {}
    return {str(k): v for k, v in mapping.items() if not str(k).startswith("__")}


_lock = threading.Lock()
_cache = None


def _config_path():
    """Live file, else the shipped sample, else absent — `mechanism_gate`'s rule verbatim.

    `server/config/*.json` is the operator's (gitignored) and `sample/*.json.sample` ships;
    a screen that cannot tell them apart lets an operator believe they configured
    something they did not, so `origin` travels in the response.
    """
    try:
        import paths
        base = paths.CONFIG_DIR
        sample = paths.config_sample_path(CONFIG_FILENAME)
    except Exception:                                            # pragma: no cover
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
        sample = os.path.join(base, "sample", CONFIG_FILENAME + ".sample")
    path = os.path.join(base, CONFIG_FILENAME)
    if os.path.exists(path):
        return path, "live"
    if os.path.exists(sample):
        return sample, "sample"
    return path, "absent"


def load_config(force_reload=False):
    global _cache
    with _lock:
        if _cache is not None and not force_reload:
            return _cache
        path, origin = _config_path()
        if origin == "absent":
            _cache = JourneyConfig({}, path, origin, state="absent",
                                   reason="no_journey_config",
                                   message=f"{CONFIG_FILENAME} 없음 — 이름 선언 층 부재, "
                                           f"구간·항목은 원시 경로로 렌더된다")
            return _cache
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict):
                raise ValueError("최상위가 객체가 아님")
        except Exception as exc:
            logger.error("journey declaration unreadable at %s: %s", path, exc)
            _cache = JourneyConfig({}, path, origin, state="absent",
                                   reason=REASON_CONFIG_UNREADABLE,
                                   message=f"{CONFIG_FILENAME} 읽기 실패: {exc}")
            return _cache
        _cache = JourneyConfig(raw, path, origin)
        return _cache


def set_config(raw):
    """Install a declaration for this process. Tests use it; nothing else should."""
    global _cache
    with _lock:
        _cache = (None if raw is None
                  else JourneyConfig(raw, "<memory>", "memory"))
        return _cache


# ------------------------------------------------------------------------- the answer
def journey(connection, kind=None, scope=None, window=None, now=None, overrides=None):
    """Two marked subjects' journeys, contrasted segment by segment. Read-only."""
    cfg = dict(DEFAULTS)
    cfg.update(overrides or {})
    axes = sib.load_axes_config()
    labels = load_config()

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
            "reason": REASON_NO_SCOPE, "message": "scope 미지정 — 여정 대조는 마킹이 전제"})

    geometry, _attribution = axes.for_kind(kind)
    source, axis = resolve_marking_axis(axes, kind, axis_name)
    observation = finding_kinds.observation_table(kind)
    methods = finding_kinds.methods(kind)
    win = sib.parse_window(window, now=now)
    graph = mechanism_gate.load()
    zone = ledger_trace.resolve_display_zone()

    envelope = {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "engine": "journey",
        "mode": "contrast",
        # 🔴 The arity is a FIELD. A client that has to infer 「this is the two-wafer
        # shape」 from the absence of `candidates` will one day infer it wrongly.
        "arity": ARITY,
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
        # 🔴 TWO GATES. See the module docstring: there is no third one at n=2 and it is
        # absent rather than null.
        "gates": _gate_legend(),
        "statistics": {
            "state": "not_applicable",
            "arity": ARITY,
            "message": ("주어가 둘이라 집단 통계는 성립하지 않는다 — 배수·신뢰구간·"
                        "「우연 아님」 관문은 이 응답에 «없다»(null이 아니라 부재)"),
        },
        "labels": labels.declaration(),
        "mechanism": graph.declaration(),
        "subjects": [], "segments": [], "notes": [],
        "summary": {"segments": 0, "same": 0, "diverged": 0, "one_sided": 0},
    }

    subject, why = _subject_of(geometry)
    if subject is None:
        return _degraded(envelope, REASON_NO_SUBJECT_DECLARED,
                         f"여정 불가 — 원장 주어 선언 없음 ({why})")
    envelope["subject"] = {"type": subject.type, "key": subject.key,
                           "column": subject.column}

    predicates = sorted(labels.segments)
    if not predicates:
        return _degraded(envelope, REASON_NO_JOURNEY_PREDICATE,
                         f"여정을 이루는 술어가 {CONFIG_FILENAME}의 segments에 "
                         f"선언되지 않았다 — 그릴 축이 없다")

    for relation, reason in ((source.relation, REASON_MARKING_RELATION_ABSENT),
                             (LEDGER_TABLE, REASON_LEDGER_ABSENT)):
        if not relation_exists(connection, relation):
            return _degraded(envelope, reason, f"관계 {relation} 없음")

    has_runs = bool(methods) and relation_exists(connection, finding_kinds.RUN_TABLE)
    plan = sib._Plan(geometry, observation, methods, win, has_runs,
                     run_time_as="run_time" if has_runs else None)

    per_value, subjects = _resolve_subjects(connection, plan, source, axis, subject, values)
    accounting, unmatched = _account(connection, source, axis, values, per_value)
    envelope["scope"].update({
        "value_accounting": accounting,
        "values_requested": len(values),
        "values_resolved": len(values) - len(unmatched),
        "values_dropped": len(unmatched),
        "subjects_resolved": len(subjects),
    })
    if unmatched:
        envelope["notes"].append({
            "note": "scope_values_dropped", "values": list(unmatched),
            "message": (f"마킹한 {len(values)}개 중 {len(unmatched)}개가 이 모집단에서 "
                        f"주어로 풀리지 않았다: "
                        + ", ".join(f"{r['value']}({r['message']})"
                                    for r in accounting if r["state"] == "dropped"))})
    if not subjects:
        return _degraded(envelope, REASON_NO_VALUE_MATCHED,
                         "마킹한 값이 주어로 하나도 풀리지 않았다", state=STATE_EMPTY)
    if len(subjects) != ARITY:
        # 🔴 REFUSED, NOT DEGRADED TO A TABLE. The owner scoped this screen to two, and a
        # journey drawn for five subjects is the many-column table it replaced. The refusal
        # NAMES the subjects so the console can offer the ranking rail instead.
        raise WalkRequestError({
            "reason": REASON_NOT_A_PAIR, "arity_required": ARITY,
            "arity_resolved": len(subjects), "subjects": list(subjects),
            "axis": axis.name,
            "message": (f"여정 대조는 주어 {ARITY}개 전용 — 마킹이 {len(subjects)}개로 "
                        f"풀렸다. 3개 이상은 순위 레일(`/siblings?scope=`)이 답한다")})

    envelope["subjects"] = [
        {"slot": slot, "id": sid, "label": sid, "subject_type": subject.type}
        for slot, sid in zip(SLOTS, subjects)
    ]

    obs_at = _observation_times(connection, plan, subject, subjects) if has_runs else {}
    outcomes = _outcomes(connection, plan, subject, subjects)
    for entry in envelope["subjects"]:
        seen = obs_at.get(entry["id"])
        entry["observed_at"] = ledger_trace._iso(seen, zone)
        entry["observed_at_state"] = "recorded" if seen else "not_recorded"
        got = outcomes.get(entry["id"])
        entry["outcome"] = {
            "kind": kind, "label": spec.get("label") or kind,
            "scanned": (got or {}).get("scanned"),
            "found": (got or {}).get("found"),
            "state": "measured" if got else "not_in_population",
            # 🔴 See `_outcomes`: these are the SUBJECT's totals, not this segment's, and
            # nothing declares how to split them across segments.
            "attributed_to_segment": False,
            "message": (None if got else
                        "이 주어가 이 기간·모집단에 없다 — 검사 수 자체가 없음"),
        }

    atoms, truncated = _atoms(connection, subject, subjects, predicates, cfg)
    if not atoms:
        return _degraded(envelope, REASON_NO_ATOMS,
                         "이 주어들에 여정 원자 0건 — 걸을 길이 없다", state=STATE_EMPTY)
    for entry in envelope["subjects"]:
        entry["atoms"] = sum(1 for a in atoms if a["subject"] == entry["id"])
        entry["atoms_truncated"] = entry["id"] in truncated

    if truncated:
        envelope["notes"].append({
            "note": "atoms_truncated", "subjects": sorted(truncated),
            "at": cfg["max_atoms_per_subject"],
            "message": (f"주어당 원자 상한 {cfg['max_atoms_per_subject']}건에 걸려 "
                        f"뒤쪽 구간이 잘렸다 — 아래 여정은 «전부»가 아니다")})

    segments = _segments(atoms, subjects, labels, kind, graph, obs_at, zone, cfg)
    if len(segments) > cfg["max_segments"]:
        envelope["notes"].append({
            "note": "segments_truncated", "at": cfg["max_segments"],
            "total": len(segments),
            "message": (f"구간 {len(segments)}개 중 앞 {cfg['max_segments']}개만 실었다")})
        segments = segments[:cfg["max_segments"]]

    envelope["state"] = STATE_READY
    envelope["segments"] = segments
    envelope["summary"] = _summary(segments)
    envelope["headline"] = (
        f"같은 길 {envelope['summary']['folded']}구간, "
        f"갈라진 곳 {envelope['summary']['opened']}곳")
    _note_inference_positioned(envelope, segments)
    _note_bias_candidates(envelope, segments)
    return envelope


def _degraded(envelope, reason, message, state=STATE_ABSENT):
    envelope.update({"state": state, "reason": reason, "message": message,
                     "segments": [],
                     "summary": {"segments": 0, "same": 0, "diverged": 0,
                                 "one_sided": 0}})
    return envelope


# ---------------------------------------------------------------- scope -> subjects
def _resolve_subjects(connection, plan, source, axis, subject, values):
    """Every requested marking value -> the ledger subjects it resolves to.

    The two hops are BOTH declared: `attribution[].join` maps the population's unit columns
    onto the marking relation, and `geometry.ledger_subject.column` says which unit column
    IS the subject. Neither is assumed here — the same pair `ledger_walk_contrast._sides`
    walks, narrowed to the requested values because two subjects do not need a census.
    """
    params = dict(plan.params)
    params["scope_values"] = [str(v) for v in values]
    narrow = source.filter_clause("a", [], params)
    sql = (
        f"{plan.prelude},\n"
        f"marked AS (SELECT DISTINCT p.{subject.column}::text AS subject,\n"
        f"                  a.{axis.column}::text AS mark_val\n"
        f"           FROM pop p JOIN {source.relation} a "
        f"ON {sib._join_on('p', 'a', source.join)}{narrow}\n"
        f"           WHERE a.{axis.column}::text = ANY(%(scope_values)s))\n"
        # One row per REQUESTED value whether or not it matched — the difference between
        # 「빠졌다」 and silence, and the same `unnest ... LEFT JOIN` the contrast uses.
        f"SELECT v.val, m.subject\n"
        f"FROM unnest(%(scope_values)s::text[]) AS v(val)\n"
        f"LEFT JOIN marked m ON m.mark_val = v.val")
    per_value, subjects = {}, []
    for value, sid in _fetch(connection, sql, params):
        bucket = per_value.setdefault(value, [])
        if sid is None:
            continue
        if sid not in bucket:
            bucket.append(sid)
        if sid not in subjects:
            subjects.append(sid)
    for bucket in per_value.values():
        bucket.sort()
    subjects.sort()
    return per_value, subjects


def _account(connection, source, axis, requested, per_value):
    """Every requested value, resolved or dropped, NAMED and with its reason."""
    rows, unmatched = [], []
    for value in requested:
        got = per_value.get(str(value)) or []
        if got:
            rows.append({"value": value, "state": "resolved", "subjects": list(got),
                         "reason": None, "message": None})
        else:
            rows.append({"value": value, "state": "dropped", "subjects": [],
                         "reason": None, "message": None})
            unmatched.append(value)
    if not unmatched:
        return rows, unmatched
    known = _values_in_axis(connection, source, axis, unmatched)
    for row in rows:
        if row["state"] != "dropped":
            continue
        if row["value"] in known:
            row["reason"] = "value_outside_population"
            row["message"] = "축에는 있으나 이 기간·모집단에 유닛 0건"
        else:
            row["reason"] = REASON_VALUE_UNKNOWN
            row["message"] = f"{axis.label or axis.name}에 없는 값 — 오타 가능"
    return rows, unmatched


def _observation_times(connection, plan, subject, subjects):
    """Each subject's FIRST run of this kind's methods — the 「시간상 앞섬」 reference.

    Reads the `runs` CTE the shared plan already built, so the method and window filters
    have ONE spelling. `ledger_walk_contrast._walk` reads the same CTE the same way.
    """
    params = dict(plan.params)
    params["ids"] = list(subjects)
    sql = (f"{plan.prelude}\n"
           f"SELECT {subject.column}::text, min(run_time) FROM runs "
           f"WHERE {subject.column}::text = ANY(%(ids)s) GROUP BY 1")
    return {sid: seen for sid, seen in _fetch(connection, sql, params)}


def _outcomes(connection, plan, subject, subjects):
    """WHY these two were marked — each subject's scanned and found counts.

    🔴 PER SUBJECT, NOT PER SEGMENT, AND THE DIFFERENCE IS A REFUSAL. The brief asks for
    「그 구간의 관련 결과(보이드/칩 등)」 beside each divergence, and attributing a void to
    BONDING#2 rather than BONDING#1 would need a rule nobody has declared — a time window,
    or a step-to-finding binding that does not exist. So the outcome is reported at the
    level the declarations actually reach, and `attributed_to_segment: false` says that in
    a field rather than leaving a reader to assume the counts are segment-local.

    Both denominators travel: `found` alone is unreadable without `scanned`, and this
    project has measured that only 20.6% of a lot is inspected.
    """
    params = dict(plan.params)
    params["ids"] = list(subjects)
    sql = (f"{plan.prelude}\n"
           f"SELECT p.{subject.column}::text, count(*), "
           f"count(*) FILTER (WHERE p.is_found) FROM pop p "
           f"WHERE p.{subject.column}::text = ANY(%(ids)s) GROUP BY 1")
    return {sid: {"scanned": int(scanned), "found": int(found or 0)}
            for sid, scanned, found in _fetch(connection, sql, params)}


# --------------------------------------------------------------------- atoms -> segments
# `occurred_at_basis` rides along so a reader can tell an observation time from a world
# time WITHOUT re-reading the config that produced the atom. NULL - which is every atom
# written before the column existed - means world time.
_ATOM_COLS = ("id", "subject", "predicate", "payload", "occurred_at", "occurred_at_basis",
              "source_who", "source_translator_ver", "source_raw_ref", "supersedes")


def _atoms(connection, subject, subjects, predicates, cfg):
    """Every journey atom of the two subjects, oldest first.

    [SCALE] `subject_keys->>'<key>' = ANY(<2 ids>)` narrowed by predicate. Same shape and
    same seam as the contrast's probe; the cap is per subject so one pathological subject
    cannot decide the response size, and truncation is REPORTED rather than silent.
    """
    sql = (f"SELECT e.id::text, e.subject_keys->>%(skey)s, e.predicate, "
           f"e.object_payload, e.occurred_at, e.occurred_at_basis, e.source_who, "
           f"e.source_translator_ver, e.source_raw_ref, e.supersedes::text "
           f"FROM {LEDGER_TABLE} e "
           f"WHERE e.subject_type = ANY(%(stypes)s) "
           f"AND e.subject_keys->>%(skey)s = ANY(%(ids)s) "
           f"AND e.predicate = ANY(%(preds)s) "
           f"AND e.object_payload IS NOT NULL "
           f"ORDER BY e.occurred_at, e.id")
    # 🔴 ROOT-KEY ROLLUP, NOT A SINGLE TYPE (ruling R-2026-08-15-O). A journey asks what
    # happened to a WAFER. Derived subject rollup remains generic for future declared
    # types, but bonding ``leg`` is now a value in a Wafer experiment-assignment claim,
    # not a derived subject. The join key is unchanged: derived types declare the root key
    # they carry, so `subject_keys->>'wafer'` finds them exactly as it finds the wafer.
    rows = _fetch(connection, sql,
                  {"stypes": list(rollup_subject_types(subject.type)), "skey": subject.key,
                   "ids": list(subjects), "preds": list(predicates)})
    out, seen, truncated = [], {}, set()
    cap = int(cfg["max_atoms_per_subject"])
    for raw in rows:
        atom = dict(zip(_ATOM_COLS, raw))
        count = seen.get(atom["subject"], 0)
        if count >= cap:
            truncated.add(atom["subject"])
            continue
        seen[atom["subject"]] = count + 1
        out.append(atom)
    return out, truncated


def _claim(atom):
    """A `ledger_trace.Claim` over one fetched row, so `claim_class` is not re-implemented.

    `subject_type`/`subject_keys` are left empty ON PURPOSE and it is safe for exactly one
    reason worth writing down: `claim_class` and `claim_rank_key` read `predicate`,
    `object_payload`, `source_who`, `source_translator_ver`, `occurred_at` and `id`, and
    nothing else. If either ever starts reading the subject, this call is the site that
    breaks — and it should break loudly rather than rank on an empty dict.
    """
    return ledger_trace.Claim(
        id=atom["id"], subject_type=None, subject_keys={}, predicate=atom["predicate"],
        object_kind="value", object_payload=atom["payload"] or {},
        occurred_at=atom["occurred_at"], source_who=atom["source_who"],
        source_translator_ver=atom["source_translator_ver"],
        source_raw_ref=atom["source_raw_ref"], supersedes=atom["supersedes"])


def _leaves(payload, prefix=()):
    """Every scalar leaf of a payload as `(dotted path, value)`. Objects recurse; a list is
    a LEAF (its members have no names, so a path into one would be positional and would
    move when the source reorders)."""
    for key, value in (payload or {}).items():
        path = prefix + (str(key),)
        if isinstance(value, dict):
            for item in _leaves(value, path):
                yield item
        else:
            yield ".".join(path), value


def _segments(atoms, subjects, labels, kind, graph, obs_at, zone, cfg):
    """Atoms -> the ordered journey axis. One pass, no predicate ever named."""
    # ① annotate each atom with its step, family and resolution class
    annotated = []
    for atom in atoms:
        spec = labels.segments.get(atom["predicate"])
        if not spec:
            continue
        payload = atom["payload"] or {}
        name = _dig(payload, spec["name_path"])
        if name is None:
            # 🔴 An atom of a journey predicate that carries no step is NOT dropped: it
            # would vanish from a screen whose whole job is showing what happened. It gets
            # its own segment named for the absence.
            name, name_state = "(step 기록 없음)", "not_recorded"
        else:
            name, name_state = str(name), "recorded"
        family = _dig(payload, spec["family_path"]) if spec["family_path"] else None
        klass = ledger_trace.claim_class(_claim(atom))
        annotated.append({**atom, "step": name, "step_state": name_state,
                          "family": None if family is None else str(family),
                          "class": klass,
                          "class_name": ledger_trace.CLASS_NAMES.get(klass, str(klass)),
                          "name_path": spec["name_path"],
                          "family_path": spec["family_path"]})

    # ② ordinal WITHIN (subject, family, step, class) — the pairing rule, see the docstring
    ranks = {}
    for atom in sorted(annotated, key=lambda a: (a["occurred_at"], a["id"])):
        key = (atom["subject"], atom["family"], atom["step"], atom["class"])
        ranks[key] = ranks.get(key, 0) + 1
        atom["ordinal"] = ranks[key]

    # ③ group into segments keyed on (family, step, ordinal) — class-free, so the eqp log
    #    and the recipe book land in ONE segment and their disagreement becomes readable
    buckets = {}
    for atom in annotated:
        buckets.setdefault((atom["family"], atom["step"], atom["ordinal"]),
                           []).append(atom)

    resolver = ledger_trace.load_resolver_config()
    out = []
    for key, members in buckets.items():
        out.append(_segment(key, members, subjects, labels, kind, graph, obs_at, zone,
                            cfg, resolver))
    # Ordered by the earliest instant anybody recorded for it. `position_basis` says when
    # that instant came from an inference-class atom, because a recipe book's date is not
    # the day the wafer was in the furnace and a reader must be able to see that.
    out.sort(key=lambda s: (s["_sort_at"], s["step"]["family"] or "",
                            s["step"]["name"], s["ordinal"]))
    for index, segment in enumerate(out, start=1):
        segment["position"] = index
        segment.pop("_sort_at", None)
    return out


def _dig(payload, dotted):
    node = payload or {}
    for part in (dotted or "").split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return None if isinstance(node, (dict, list)) else node


def _segment(key, members, subjects, labels, kind, graph, obs_at, zone, cfg, resolver):
    family, step, ordinal = key
    by_subject = {sid: [a for a in members if a["subject"] == sid] for sid in subjects}
    present = {sid: bool(rows) for sid, rows in by_subject.items()}

    step_label = labels.step(step)
    family_label = labels.family(family) if family else {"label": None,
                                                         "state": "not_recorded"}
    predicate = members[0]["predicate"]
    vocab = _predicate_declaration(predicate)

    items = _items(members, subjects, by_subject, labels, kind, graph, predicate, vocab,
                   obs_at, zone, resolver)
    if all(present.values()):
        verdict = (VERDICT_SAME if all(i["verdict"] == VERDICT_SAME for i in items)
                   else VERDICT_DIVERGED)
    else:
        verdict = VERDICT_ONE_SIDED

    instants = sorted(a["occurred_at"] for a in members)
    observed_class = [a for a in members
                      if a["class"] == ledger_trace.CLASS_OBSERVATION]
    when, firsts = {}, {}
    for slot, sid in zip(SLOTS, subjects):
        rows = by_subject[sid]
        first = min((a["occurred_at"] for a in rows), default=None)
        firsts[slot] = first
        when[slot] = {
            "at": ledger_trace._iso(first, zone),
            "state": "recorded" if first else VALUE_NO_SEGMENT,
            "atoms": len(rows),
            "classes": sorted({a["class_name"] for a in rows}),
        }
    when["gap_seconds"] = (
        None if firsts["A"] is None or firsts["B"] is None
        else int(abs((firsts["A"] - firsts["B"]).total_seconds())))

    segment = {
        "key": f"{family or '-'}/{step}#{ordinal}",
        "ordinal": ordinal,
        "predicate": predicate,
        "predicate_label": vocab["label"],
        "step": {
            "name": step, "label": step_label["label"],
            "label_state": step_label["state"],
            "name_state": members[0]["step_state"],
            "family": family, "family_label": family_label["label"],
            "family_label_state": family_label["state"],
            "declared_by": {"config": CONFIG_FILENAME,
                            "name_path": members[0]["name_path"],
                            "family_path": members[0]["family_path"]},
        },
        "display": _display_step(step, step_label, family, family_label),
        "verdict": verdict,
        "presence": {slot: ("present" if present[sid] else VALUE_NO_SEGMENT)
                     for slot, sid in zip(SLOTS, subjects)},
        "when": when,
        "position_basis": ("observation" if observed_class else "inference"),
        "items": items,
        "item_counts": {
            "total": len(items),
            VERDICT_SAME: sum(1 for i in items if i["verdict"] == VERDICT_SAME),
            VERDICT_DIVERGED: sum(1 for i in items if i["verdict"] == VERDICT_DIVERGED),
            VERDICT_ONE_SIDED: sum(1 for i in items if i["verdict"] == VERDICT_ONE_SIDED),
        },
        "_sort_at": instants[0],
    }
    segment["agreement"] = _agreement(items, cfg)
    # 🔴 THE GREY LINE, ASSEMBLED SERVER-SIDE. The ruling's own form —
    # 「본딩 — 같음: 장비 SYN-BD-EXC · 레시피 rev 6 · 수치 3건 차이」 — so the client
    # concatenates nothing and two consoles cannot punctuate it two ways. `null` when the
    # segment is not foldable, which is the same signal as `agreement.foldable` in the
    # shape the renderer actually consumes.
    segment["fold_line"] = (
        f"{segment['display']} — {segment['agreement']['sentence']}"
        if segment["agreement"]["foldable"] and segment["agreement"]["sentence"]
        else None)
    segment["sentence"] = _sentence(segment, subjects, cfg)
    # 🔴 THE SIX ARE ATTACHED HERE AND NOWHERE ELSE — one mapping, after the segment knows
    # its own 어디서 and 언제. A card is complete when all six answer OR say they cannot,
    # and `completeness` is what a reviewer reads instead of counting slots by eye.
    for item in segment["items"]:
        item["six"] = six_questions(segment, item, subjects)
        answered = [q for q, slot in item["six"].items()
                    if slot["state"] == "answered"]
        # 🔴 `complete` IS MEASURED, NOT ASSERTED. The 부칙's completion criterion is 「여섯
        # 물음에 답하거나, 답이 없으면 없다고 말해야」, so completeness is「every slot
        # carries a sentence」 — a hardcoded True would have made this field decoration and
        # a slot that silently returned null would have passed it.
        item["six_completeness"] = {
            "answered": sorted(answered),
            "unanswered": sorted(q for q in item["six"] if q not in answered),
            "complete": all(slot.get("text") for slot in item["six"].values()),
        }
    return segment


def _agreement(items, cfg):
    """WHAT AGREED AND WHAT STILL DIFFERS — the grey line, and the account it must give.

    🔴 THE FOLD RULE IS RUN IDENTITY. Lead PM ruling, 2026-08-14, decided by measurement:
    on real data NO segment is byte-identical (every one of the owner's eight carries at
    least one differing measured number), so a fold on strict equality fires 0 times in 8
    and a collapse rule that never collapses makes the design vacuous — the owner would get
    the eight open cards they were trying to escape. Run identity DOES agree in five of the
    eight (BONDING#1 is `eqp SYN-BD-EXC · recipe rev 6` on both sides while `temp_C` reads
    155.712 against 154.152), and that is the grey line they drew.

    🔴 AND FOLDED IS NOT HIDDEN — THE LINE ACCOUNTS FOR EVERYTHING UNDER IT. Folding on
    identity while a number moved and calling it 「같음」 with nothing else said would be a
    small lie about sameness, which is the one thing this console exists to stop. So the
    sentence carries a differs-clause (「… · 수치 4건 차이」) and `differing` carries the
    counts and the paths behind it, pre-computed: the client renders and expands the line
    without ever walking raw leaves. Same rule the truncation notice and the multi-lot map
    summary follow, and the same reason both are allowed to show less.

    ⚠️ `mechanism_bound` IS REPORTED IN THE TAIL, and that is a deliberate loudness. The
    fold does not consult it (the ruling is identity, full stop), but a divergence with a
    DECLARED path to the finding is the DOE candidate, and one disappearing silently behind
    a grey line is precisely the failure this screen guards against. Counting it in the
    sentence lets the reader — and the owner — see what the fold costs without changing
    what the fold is.
    """
    actors = [i for i in items if i["role"] in ("actor", "segment")]
    content = [i for i in items if i["role"] == "content"]
    named = [i for i in actors
             if i["verdict"] == VERDICT_SAME and i["role"] == "actor"]
    named.sort(key=_item_rank)
    head = " · ".join(f"{i['display']} {i['A']['text']}"
                      for i in named[:cfg["sentence_items"]])

    # 🔴 TWO ROLES ARE NOT COUNTED AS DIFFERENCES, FOR TWO DIFFERENT REASONS.
    # `epistemic` (`inferred`/`confirmed`) are the resolver's own flags, already surfaced as
    # each side's resolution class — a reader told 「수치 5건 차이」 where one of the five is
    # `inferred: true` goes looking for a process difference that is not there.
    # `segment` (the step annotation) is the segment's own IDENTITY: it can never differ
    # inside a folded segment by construction, and in a one-sided one 「step이 다르다」 is
    # not a fact about the process, it is the absence restated.
    differing = [i for i in items
                 if i["verdict"] != VERDICT_SAME
                 and i["role"] not in ("epistemic", "segment")]
    differing.sort(key=_item_rank)
    numeric = [i for i in differing if _is_numeric_item(i)]
    formation = [i for i in differing
                 if i["gates"]["mechanism"]["verdict"] == mechanism_gate.VERDICT_PASS]
    bias = [i for i in differing
            if i["gates"]["mechanism"]["verdict"] == mechanism_gate.VERDICT_BIAS]
    bound = formation + bias
    actors_verdict = _roll(actors)
    # 🔴 THE FOLD DECISION, SO THE CLIENT NEVER INVENTS IT — AND ITS SECOND CLAUSE IS THE
    # WHOLE REVISION. Lead PM, 2026-08-14, revising the identity-only rule after it was
    # measured: `SYN-BW-101-01 / -06` folded 7 of 7 with `bond_pressure` and `bond_temp`
    # — each with a DECLARED path to `void` — behind the grey lines. A fold exists to
    # collapse NOISE, and a difference with a declared physical path to the outcome is by
    # construction not noise; folding it inverts the purpose of the screen at exactly the
    # comparison an engineer runs when they already suspect the process.
    #
    # ⚠️ THE COUNT IS SPLIT because `bias_candidate` is a live question, not a settled one.
    # `formation_bound` reaches a FORMATION model's target; `bias_bound` reaches only an
    # observation-bias target — 「발생 아님」, which the brief says must not appear at the
    # rank of a cause, and opening a card IS a rank. The shipped rule is the ruling as
    # written (`mechanism_bound == 0`, both kinds block); switching to formation-only is
    # this one predicate. Measured cost of the difference is in the round's report.
    foldable = actors_verdict == VERDICT_SAME and not bound
    return {
        "actors": actors_verdict,
        "content": _roll(content),
        # A `one_sided` segment can never be foldable — one subject was not there, and
        # there is no shared road to collapse.
        "foldable": foldable,
        "fold_basis": "run_identity_and_no_mechanism_path",
        "fold_basis_label": "장비·레시피·rev 일치 · 기전 경로 있는 차이 없음",
        # 🔴 WHY A SEGMENT OPENED DESPITE THE IDENTITY MATCHING. Without this the reader
        # sees an open card whose first line says 「같음」 and has no way to learn that the
        # opening was itself a judgement.
        "fold_blocked_by": ("mechanism_path"
                            if actors_verdict == VERDICT_SAME and bound else None),
        "agreeing_actors": [{"path": i["path"], "display": i["display"],
                             "text": i["A"]["text"]} for i in named],
        # 🔴 PRE-COMPUTED, because the ruling says the client must not recompute it from
        # raw leaves. `paths` is a direct lookup key into `segment.items` for the expand.
        "differing": {
            "total": len(differing),
            "numeric": len(numeric),
            "other": len(differing) - len(numeric),
            "mechanism_bound": len(bound),
            # 🔴 SPLIT, because the two do not mean the same thing and the fold rule may
            # yet want only one of them. `formation_bound` reaches a formation model's
            # target (a cause); `bias_bound` reaches only an observation-bias target
            # (「발생 아님」 — why it was SEEN, not why it formed).
            "formation_bound": len(formation),
            "bias_bound": len(bias),
            "paths": [i["path"] for i in differing],
            "items": [{"path": i["path"], "display": i["display"], "role": i["role"],
                       "verdict": i["verdict"], "numeric": _is_numeric_item(i),
                       "mechanism": i["gates"]["mechanism"]["verdict"],
                       "A": i["A"]["text"], "B": i["B"]["text"]}
                      for i in differing],
        },
        "mechanism_bound_diverged": len(bound),
        # 🔴 ALWAYS RENDERABLE, even in a segment that also diverged. The owner's grey line
        # is this string; withholding it until nothing at all differs is how 「같음」 stops
        # being information.
        "sentence": (f"같음: {head}{_differs_clause(len(numeric), len(differing) - len(numeric), len(bound))}"
                     if head else None),
    }


def _is_numeric_item(item):
    """Is this leaf a QUANTITY? Judged on the JSON type of whichever side recorded a value
    — the same rule `ledger_walk_contrast._compare_kind` uses, and not on the field's name.
    `bool` is checked first because it is an `int` subclass in Python."""
    for side in (item["A"], item["B"]):
        if side["state"] != VALUE_RECORDED:
            continue
        value = side["value"]
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float))
    return False


def _differs_clause(numeric, other, bound):
    """The tail that stops a fold from being a claim of sameness. 🔴 Nouns and counts, no
    sentence — UI copy rule (기호·명사형 우선); the one full sentence per card is the fact
    line above it."""
    if not (numeric or other):
        return ""
    parts = []
    if numeric:
        parts.append(f"수치 {numeric}건")
    if other:
        parts.append(f"그 외 {other}건")
    tail = f" · {' · '.join(parts)} 차이"
    if bound:
        # The DOE candidates, counted where the fold would otherwise bury them.
        tail += f" (기전 {bound}건)"
    return tail


def _roll(items):
    if not items:
        return VERDICT_SAME
    if any(i["verdict"] == VERDICT_ONE_SIDED for i in items):
        return VERDICT_ONE_SIDED
    return (VERDICT_SAME if all(i["verdict"] == VERDICT_SAME for i in items)
            else VERDICT_DIVERGED)


def _predicate_declaration(predicate):
    """The vocabulary's word for this predicate — label and REQUIRED object fields.

    The required list is what makes 「누가(주체)」 answerable without a second declaration:
    the fields a predicate's signature demands, minus the ones the journey config points at
    for the step, are exactly the run's identifying actors (`eqp`, `recipe` for
    `processed_with`). Imported LAZILY — `LEDGER_GUIDE` §0 promises nothing on the web
    server's boot path imports `server/ledger`, and this module is reached from the router.
    """
    try:
        from ledger import vocabulary
        # The MERGED set (R-2026-08-15-M ④): a word registered from admin has a
        # `label_ko` of its own, and reading only the code-loaded set would render it as
        # a bare English identifier while every test stayed green.
        sig = (vocabulary.all_predicates() or {}).get(predicate) or {}
    except Exception:                                            # pragma: no cover
        sig = {}
    return {"label": sig.get("label_ko") or predicate,
            "required": list((sig.get("object") or {}).get("required") or []),
            "declared": bool(sig)}


def _display_step(step, step_label, family, family_label):
    """The screen's name for this segment. 🔴 The raw value when nothing declares a name —
    「정직 우선」: a missing declaration must LOOK missing rather than be papered over."""
    head = step_label["label"] or step
    tail = family_label["label"] or family
    return f"{tail} · {head}" if tail else head


# ------------------------------------------------------------------------------ items
def _items(members, subjects, by_subject, labels, kind, graph, predicate, vocab,
           obs_at, zone, resolver):
    """One row per leaf path that either subject recorded in this segment."""
    values = {sid: {} for sid in subjects}
    ordered = []
    for atom in members:
        claim = _claim(atom)
        for path, value in _leaves(atom["payload"]):
            if path not in ordered:
                ordered.append(path)
            record = {"value": value, "atom": atom, "claim": claim}
            prior = values[atom["subject"]].get(path)
            if prior is None:
                values[atom["subject"]][path] = {"win": record, "lost": []}
                continue
            # 🔴 TWO ATOMS OF ONE SEGMENT DISAGREE ABOUT ONE LEAF. The winner is decided by
            # `claim_rank_key` — the SAME total order the lineage resolver uses — so
            # 「실측이 설정값을 이긴다」 has one spelling in this system and not two. The
            # loser is CARRIED, never dropped: a contested value the screen hides is how a
            # setpoint quietly becomes a measurement.
            contenders = [prior["win"]] + prior["lost"] + [record]
            contenders.sort(key=lambda r: ledger_trace.claim_rank_key(r["claim"], resolver))
            values[atom["subject"]][path] = {"win": contenders[0],
                                             "lost": contenders[1:]}

    segment_paths = {members[0]["name_path"]}
    if members[0]["family_path"]:
        segment_paths.add(members[0]["family_path"])
    actor_paths = _actor_paths(vocab["required"], segment_paths)

    out = []
    for path in ordered:
        out.append(_item(path, subjects, values, labels, kind, graph, predicate,
                         by_subject, segment_paths, actor_paths, obs_at, zone, resolver))
    out.sort(key=_item_rank)
    return out


def _actor_paths(required, segment_paths):
    """The predicate's required object fields that are NOT the step — 「누가(주체)」.

    DERIVED, not declared twice: `vocabulary` says what a `processed_with` object must
    carry and `ledger_journey.json` says which of those is the step. What is left over is
    the run's identity — the equipment and the recipe — and it costs no name typed here.
    """
    return tuple(r for r in required if r not in segment_paths)


def _item(path, subjects, values, labels, kind, graph, predicate, by_subject,
          segment_paths, actor_paths, obs_at, zone, resolver):
    field = labels.field(predicate, path)
    candidate_key = f"{predicate}:{path}"
    sides = {}
    # 🔴 THE RAW INSTANT NEVER ENTERS THE RESPONSE, AND THE RENDERED ONE NEVER ENTERS A
    # COMPARISON. Keeping one field for both is how the upstream gate started comparing a
    # string to a datetime the moment the response was corrected to render its zone.
    raw_at = {}
    for slot, sid in zip(SLOTS, subjects):
        entry = (values.get(sid) or {}).get(path)
        raw_at[slot] = None if entry is None else entry["win"]["atom"]["occurred_at"]
        if entry is None:
            state = (VALUE_NO_SEGMENT if not by_subject[sid] else VALUE_ABSENT)
            sides[slot] = {
                "state": state, "value": None, "text": None,
                "claim_class": None, "claim_class_label": None,
                "occurred_at": None, "source_who": None, "source_raw_ref": None,
                "atom_id": None, "contested": False, "superseded_by_here": [],
                # 🔴 THE SENTENCE THAT MUST NOT COLLAPSE INTO A BLANK. 「측정 없음」 is a
                # FACT about this subject at this segment, and it is a different fact from
                # 「이 구간을 걷지 않았다」.
                "message": ("이 구간 자체를 걷지 않았다" if state == VALUE_NO_SEGMENT
                            else "이 구간은 걸었으나 이 항목의 기록이 없다"),
            }
            continue
        win, lost = entry["win"], entry["lost"]
        value, atom, claim = win["value"], win["atom"], win["claim"]
        state = VALUE_NULL if value is None else VALUE_RECORDED
        sides[slot] = {
            "state": state,
            "value": value,
            "text": _fmt(value, field.get("unit")),
            "claim_class": atom["class_name"],
            "claim_class_label": CLASS_LABELS.get(atom["class_name"], atom["class_name"]),
            # 🔴 THROUGH `_iso`, LIKE EVERY OTHER INSTANT IN THIS SUBSYSTEM. A first cut
            # put the raw `datetime` here and it serialised with whatever offset the
            # PostgreSQL session's TimeZone happened to give — the exact accident
            # `DISPLAY_TIMEZONE_RULING` was written to end, and it renders identically to
            # a correct value on a box whose zone happens to match.
            "occurred_at": ledger_trace._iso(atom["occurred_at"], zone),
            "source_who": atom["source_who"],
            "source_raw_ref": atom["source_raw_ref"],
            "atom_id": atom["id"],
            "contested": bool(lost),
            "superseded_by_here": [
                {"value": r["value"], "claim_class": r["atom"]["class_name"],
                 "source_who": r["atom"]["source_who"], "atom_id": r["atom"]["id"]}
                for r in lost],
            "message": ("소스가 명시적으로 null을 발화했다" if state == VALUE_NULL
                        else None),
        }

    a, b = sides["A"], sides["B"]
    if a["state"] in (VALUE_ABSENT, VALUE_NO_SEGMENT) or \
            b["state"] in (VALUE_ABSENT, VALUE_NO_SEGMENT):
        verdict = (VERDICT_SAME
                   if a["state"] == b["state"] == VALUE_NO_SEGMENT
                   else VERDICT_ONE_SIDED)
    elif a["value"] == b["value"] and type(a["value"]) is type(b["value"]):
        verdict = VERDICT_SAME
    else:
        verdict = VERDICT_DIVERGED

    mech = mechanism_gate.verdict(kind, candidate_key, graph)
    item = {
        "path": path,
        "candidate_key": candidate_key,
        "label": field["label"],
        "label_state": field["state"],
        "label_matched_on": field["matched_on"],
        "unit": field.get("unit"),
        # 🔴 THE RAW PATH WHEN NOTHING NAMES IT. `display` is what the screen prints and it
        # is never blank — the brief bans `predicate·field` notation for DECLARED things
        # and demands honesty for undeclared ones, and those are the same rule.
        "display": field["label"] or path,
        "role": _role(path, segment_paths, actor_paths, resolver),
        "verdict": verdict,
        "A": sides["A"], "B": sides["B"],
        "gates": {"upstream": _gate_upstream(raw_at, subjects, obs_at, zone),
                  "mechanism": mech},
        "bias_candidate": mech["verdict"] == mechanism_gate.VERDICT_BIAS,
    }
    return item


def _gate_upstream(raw_at, subjects, obs_at, zone):
    """시간상 앞섬 — did this claim happen BEFORE the observation it might explain?

    🔴 A COMPARISON OF TWO INSTANTS, WHICH IS WHY IT SURVIVES n=2. Nothing here is a
    population statistic: each side is judged against ITS OWN subject's first run of this
    kind's methods, and a subject with no run gives `unknown` rather than `fail` — a
    missing timestamp is not a refuted causal order. Same rule and same three verdicts as
    `ledger_walk_contrast._gate_upstream`, measured per side instead of per atom count,
    because with two subjects there is nothing to count.
    """
    per_side, verdicts = {}, []
    for slot, sid in zip(SLOTS, subjects):
        at = raw_at.get(slot)
        seen = obs_at.get(sid)
        if at is None or seen is None:
            per_side[slot] = {"verdict": "unknown", "reason": "no_comparable_time",
                              "atom_at": ledger_trace._iso(at, zone),
                              "observed_at": ledger_trace._iso(seen, zone)}
        else:
            before = at < seen
            per_side[slot] = {
                "verdict": "pass" if before else "fail",
                "reason": "before_observation" if before else "at_or_after_observation",
                "atom_at": ledger_trace._iso(at, zone),
                "observed_at": ledger_trace._iso(seen, zone)}
        verdicts.append(per_side[slot]["verdict"])
    if "fail" in verdicts:
        verdict, message = "fail", "관측과 같거나 뒤 — 결과이지 원인일 수 없음"
    elif all(v == "pass" for v in verdicts):
        verdict, message = "pass", "두 기록 모두 관측보다 앞섬"
    else:
        verdict, message = "unknown", "비교할 관측 시각이 없음"
    return {"verdict": verdict, "basis": "occurred_at", "message": message,
            "per_side": per_side}


def _role(path, segment_paths, actor_paths, resolver):
    """What this leaf IS, structurally — never what it MEANS. Three roles, all derived.

    `segment` — the step annotation this journey is keyed on (declared in the journey
    config). `actor` — a required object field that is not the step, i.e. the run's
    identity (derived from the vocabulary signature). `epistemic` — the resolver's own
    declared flags, which say how much to believe an atom and are already surfaced as the
    resolution class, so a screen that renders them twice is repeating itself.
    Everything else is `content`.
    """
    if path in segment_paths:
        return "segment"
    head = path.split(".", 1)[0]
    if head in actor_paths or path in actor_paths:
        return "actor"
    if path in (resolver.get("inference_payload_flag"),
                resolver.get("confirmed_payload_flag")):
        return "epistemic"
    return "content"


_ROLE_ORDER = {"actor": 0, "content": 1, "segment": 2, "epistemic": 3}


def _item_rank(item):
    """Diverged first, then by how much the mechanism graph has to say about it."""
    mech = _MECH_ORDER.get(item["gates"]["mechanism"]["verdict"], 9)
    return (_VERDICT_ORDER.get(item["verdict"], 9), mech,
            _ROLE_ORDER.get(item["role"], 9), item["path"])


# ------------------------------------------------------------- the six questions
def six_questions(segment, item, subjects):
    """ONE envelope→slot mapping, run for every atom of every predicate.

    🔴 EVERY SLOT ANSWERS OR SAYS IT CANNOT. `state` is `answered` | `not_recorded` |
    `not_in_ledger`, and the third is reserved for 「왜」 alone: an empty 왜 is the absence
    of a DECLARATION in another layer, not a missing record, and the brief requires the two
    to render in different words and different colours.
    """
    a, b = item["A"], item["B"]
    mech = item["gates"]["mechanism"]
    who_said = sorted({s["source_who"] for s in (a, b) if s["source_who"]})
    return {
        # 🔴 THE ACTORS ARE THE SEGMENT'S, NOT THIS ITEM'S. A card about 「압력」 must still
        # answer 「누가」 with 「장비 SYN-BD-02 · 레시피 rev 5」 — the run's identity is a
        # property of the segment and reading it off the item would leave every numeric
        # card answering 「기록 없음」 to a question the ledger answers perfectly well.
        # `who` has TWO readings in the 부칙 (the table says 장비·레시피, the canonical line
        # says `source=누가 말했나`) and BOTH are carried rather than one being chosen.
        "who": _slot("누가", "이 실행의 주체 (장비·레시피)",
                     _actor_text(segment),
                     extra={"said_by": who_said,
                            "said_by_state": "answered" if who_said else "not_recorded"}),
        "when": _slot("언제", "기록된 시각",
                      _when_text(segment, subjects),
                      extra={"A": segment["when"]["A"], "B": segment["when"]["B"],
                             "gap_seconds": segment["when"]["gap_seconds"]}),
        "where": _slot("어디서", "공정 구간 (step 주석)", segment["display"]),
        "what": _slot("무엇을", "항목", item["display"],
                      extra={"raw_path": item["path"],
                             "label_state": item["label_state"]}),
        "how": _slot("어떻게", "값의 차이 (실측/설정 구분 포함)",
                     _how_text(item, subjects),
                     extra={"A_class": a["claim_class_label"],
                            "B_class": b["claim_class_label"]}),
        # 🔴 A DIFFERENT LAYER, AND IT SAYS SO. Never rendered as a ledger fact.
        # 🔴 `is_missing_record: False` IS THE LOAD-BEARING FIELD. The 부칙: an empty 왜 is
        # the absence of a DECLARATION, not a missing record, and the two must render in
        # different words and different colours. This boolean is how a client can be sure
        # it never paints 「기록 없음」 here — the other five slots carry it as True when
        # they are empty, so ONE rule covers all six.
        "why": {
            "question": "왜",
            "about": "선언된 물리 (기전 그래프)",
            "layer": "declaration",
            "state": _WHY_STATE.get(mech["verdict"], "not_declared"),
            "text": _why_text(mech),
            "is_missing_record": False,
            "verdict": mech["verdict"],
            "model": mech["model"],
            "role": mech["role"],
            "path": mech["path"],
            "quantity": mech["quantity"],
            "message": mech["message"],
            # 🔴 The 왜 slot is a QUOTATION and carries its citation. `model_version` is
            # READ from the declaration, never printed as a literal 「v0」 — a version
            # nobody declared is a number this screen would be inventing, so an
            # unversioned model reports `null` + `model_version_state: "undeclared"`.
            # (Measured 2026-08-14: `void_formation` DOES declare `version: "v0"`, which
            # is why this must be read rather than assumed either way.)
            "citation": {"config": mechanism_gate.CONFIG_FILENAME,
                         "model": mech["model"],
                         "model_version": _model_version(mech["model"]),
                         "model_version_state": (
                             "declared" if _model_version(mech["model"]) else "undeclared")},
        },
    }


#: 왜's three outcomes. 🔴 `declared_no_path` is the model ANSWERING no, `not_declared` is
#: nobody having been asked, and folding them together is the defect `mechanism_gate`'s own
#: docstring spends four paragraphs refusing.
_WHY_STATE = {
    mechanism_gate.VERDICT_PASS: "answered",
    mechanism_gate.VERDICT_BIAS: "answered",
    mechanism_gate.VERDICT_FAIL: "declared_no_path",
    mechanism_gate.VERDICT_UNKNOWN: "not_declared",
}


def _model_version(name):
    if not name:
        return None
    for model in mechanism_gate.load().models:
        if model.name == name:
            return model.version
    return None


def _slot(question, about, text, extra=None):
    """One of the FIVE the ledger answers. An empty one says 「기록 없음」 and admits it —
    the 부칙: 「결측은 여섯 어느 자리든 「기록 없음」으로 표기(빈칸·생략 금지)」."""
    out = {"question": question, "about": about,
           "state": "answered" if text else "not_recorded",
           "text": text if text else "기록 없음",
           "is_missing_record": not text}
    if extra:
        out.update(extra)
    return out


def _actor_text(segment):
    """「장비 SYN-BD-02 · 레시피 rev 5」 — and when the two sides ran on different ones,
    both, because that difference IS the answer to 「누가」."""
    parts = []
    for item in segment["items"]:
        if item["role"] != "actor":
            continue
        left, right = item["A"], item["B"]
        if item["verdict"] == VERDICT_SAME and left["text"]:
            parts.append(f"{item['display']} {left['text']}")
        else:
            parts.append(f"{item['display']} "
                         f"{left['text'] or '기록 없음'} ↔ {right['text'] or '기록 없음'}")
    return " · ".join(parts) or None


def _when_text(segment, subjects):
    when = segment["when"]
    if when["A"]["at"] and when["B"]["at"]:
        gap = when["gap_seconds"]
        if not gap:
            return f"{when['A']['at']} — 동시"
        hours = gap / 3600.0
        unit = f"{hours:.1f}h" if hours >= 1 else f"{int(gap // 60)}m"
        return f"{when['A']['at']} · {when['B']['at']} ({unit} 차이)"
    for slot, sid in zip(SLOTS, subjects):
        if when[slot]["at"]:
            return f"{sid} {when[slot]['at']} · 반대쪽 기록 없음"
    return None


def _how_text(item, subjects):
    """🔴 THE SETPOINT/ACTUAL TAIL IS ONLY SPOKEN WHEN BOTH SIDES SPOKE.

    A first cut said 「둘 다 실측」 on the one-sided MI_THICKNESS card, where exactly one
    side recorded anything — a sentence that is false about the very absence the card
    exists to show, and it read perfectly well. The classes are collected from the sides
    that RECORDED, and the tail only claims 「둘 다」 when there are two of them.
    """
    a, b = item["A"], item["B"]
    recorded = [s for s in (a, b) if s["state"] in (VALUE_RECORDED, VALUE_NULL)]
    left = a["text"] if a["state"] in (VALUE_RECORDED, VALUE_NULL) else "기록 없음"
    right = b["text"] if b["state"] in (VALUE_RECORDED, VALUE_NULL) else "기록 없음"
    classes = sorted({s["claim_class_label"] for s in recorded if s["claim_class_label"]})
    if len(recorded) < 2:
        tail = f" ({'·'.join(classes)} — 한쪽만 기록)" if classes else ""
    elif classes == ["관측"]:
        tail = " (둘 다 실측)"
    elif classes:
        tail = f" ({'·'.join(classes)})"
    else:
        tail = ""
    return f"{subjects[0]} {left}, {subjects[1]} {right}{tail}"


def _why_text(mech):
    """🔴 NEVER NULL, AND NEVER 「기록 없음」.

    The 부칙's ruling: an empty 왜 is the absence of a DECLARATION in another layer, not a
    missing record, and the two must render in different words. So this always returns a
    sentence and the sentence never uses the ledger's word for absence. A first cut
    returned `None` for the unmodelled case, which would have left the client to invent the
    wording — and the wording is the whole distinction.
    """
    if mech["verdict"] == mechanism_gate.VERDICT_PASS and mech["path"]:
        chain = " → ".join(node["node"] for node in mech["path"])
        return f"{chain} (모델 {mech['model']})"
    if mech["verdict"] == mechanism_gate.VERDICT_BIAS and mech["path"]:
        chain = " → ".join(node["node"] for node in mech["path"])
        # 🔴 「발생 아님」 — the marker the brief demands so a bias candidate cannot sit at
        # the rank of a cause. It is a real finding about the INSPECTOR, not about the part.
        return f"발생 아님 — 관측 편향: {chain} (모델 {mech['model']})"
    if mech["verdict"] == mechanism_gate.VERDICT_FAIL:
        return f"이 불량까지 가는 경로가 모델에 없다 — 모델이 «아니오»라 답했다 " \
               f"({mech['quantity']})"
    return "물리 모델에 아직 없음 — 원장의 결측이 아니라 선언의 부재"


# --------------------------------------------------------------------------- sentences
def _sentence(segment, subjects, cfg):
    """The card's first line — a FACT sentence, composed from the six slots and nothing
    invented. 🔴 It never says more than the segment holds: with a one-sided segment it
    says the absence, and with an agreement it says the agreement, because 「같음」 is
    information (brief P0-3 §2)."""
    a_id, b_id = subjects
    step = segment["display"]
    top = [i for i in segment["items"] if i["verdict"] != VERDICT_SAME
           and i["role"] != "epistemic"]
    if segment["verdict"] == VERDICT_ONE_SIDED:
        walked = [slot for slot in SLOTS
                  if segment["presence"][slot] == "present"]
        if len(walked) == 1:
            here, sid = walked[0], subjects[SLOTS.index(walked[0])]
            other = subjects[1 - SLOTS.index(walked[0])]
            named = [i for i in segment["items"]
                     if i[here]["state"] == VALUE_RECORDED and i["role"] == "content"]
            named.sort(key=_item_rank)
            detail = " · ".join(f"{i['display']} {i[here]['text']}"
                                for i in named[:cfg["sentence_items"]])
            return (f"{step} — {other} 기록 없음 · {sid} "
                    f"{detail or '기록 있음'}")
    if not top:
        named = [i for i in segment["items"]
                 if i["role"] in ("actor", "content") and i["A"]["text"]]
        named.sort(key=_item_rank)
        detail = " · ".join(f"{i['display']} {i['A']['text']}"
                            for i in named[:cfg["sentence_items"]])
        return f"{step} — 같음: {detail}" if detail else f"{step} — 같음"

    # 🔴 THE CARD THAT OPENED DESPITE THE IDENTITY MATCHING LEADS WITH BOTH HALVES.
    # Lead PM, 2026-08-14: 「same equipment, different pressure」 is a sharper finding than
    # either half alone, so the fact line names what agreed AND what a declared physical
    # model can reach — 「장비·레시피 같음 · 압력·온도 다름」 — rather than opening with a
    # bare divergence that hides the fact that the run was the same run.
    if segment["agreement"].get("fold_blocked_by") == "mechanism_path":
        agreed = _short_names(a["display"] for a in
                              segment["agreement"]["agreeing_actors"])
        bound = [i for i in top
                 if i["gates"]["mechanism"]["verdict"] in (
                     mechanism_gate.VERDICT_PASS, mechanism_gate.VERDICT_BIAS)]
        moved = _short_names(i["display"] for i in bound)
        rest = len(top) - len(bound)
        tail = f" 외 {rest}건" if rest > 0 else ""
        left = f"{'·'.join(agreed)} 같음 · " if agreed else ""
        # 🔴 A CARD OPENED ONLY BY A BIAS CANDIDATE CARRIES 「발생 아님」 ON ITS FIRST LINE.
        # The brief is explicit that an observation-bias factor must not read at the rank of
        # a cause, and OPENING a card IS a rank — so if the fold was blocked by nothing but
        # bias, the fact line says what kind of finding this is before it says anything
        # else. Without this the revised fold rule would promote a scanner artefact to a
        # process card, which is the exact confusion `mechanism_gate` was split to prevent.
        if not segment["agreement"]["differing"]["formation_bound"]:
            return f"{step} — 발생 아님(관측 편향) · {left}{'·'.join(moved)} 다름{tail}"
        return f"{step} — {left}{'·'.join(moved)} 다름{tail}"
    head = top[0]
    left = (head["A"]["text"] if head["A"]["state"] == VALUE_RECORDED else "기록 없음")
    right = (head["B"]["text"] if head["B"]["state"] == VALUE_RECORDED else "기록 없음")
    rest = len(top) - 1
    tail = f" 외 {rest}건" if rest else ""
    return (f"{step} — {head['display']}: {a_id} {left}, {b_id} {right}{tail}")


def _short_names(displays):
    """Display names for a summary line — PREFIX-deduped, never truncated.

    「레시피」 and 「레시피 rev」 both agreeing would otherwise read 「장비·레시피·레시피
    rev 같음」 on a line meant to be scanned, so the longer one is dropped when the shorter
    is its prefix. Nothing is LOST: every agreeing actor is in `agreement.agreeing_actors`
    and every item is in `items`.

    🔴 A FIRST CUT TOOK THE FIRST WHITESPACE TOKEN AND THAT WAS A DEFECT, not a style
    choice. It rendered 「본딩 후 대기」 as 「본딩」, so a POST_BOND_QUEUE card read
    「본딩 다름」 — naming the wrong process step, on the summary line, in a screen whose
    entire purpose is to say which step differed. Shortening a label may drop a word; it
    may never change which thing the label denotes.
    """
    out = []
    for display in displays:
        text = str(display)
        if any(text.startswith(kept) for kept in out):
            continue
        out = [kept for kept in out if not kept.startswith(text)]
        out.append(text)
    return out


def _fmt(value, unit):
    if value is None:
        return "null"
    if isinstance(value, bool):
        text = "예" if value else "아니오"
    elif isinstance(value, float):
        text = ("%.4f" % value).rstrip("0").rstrip(".")
    elif isinstance(value, list):
        # `_leaves` treats a list as a LEAF, so one can reach here. JSON rather than
        # `str()`, which would put a Python repr (single quotes, `True`) on the screen.
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    return f"{text} {unit}" if unit else text


def _summary(segments):
    """🔴 TWO COUNTS OF 「같음」, AND THEY MEAN DIFFERENT THINGS.

    `folded` follows the RULING (run identity agreed → one grey line) and is what the
    headline counts, because a headline that disagrees with the screen below it is worse
    than no headline. `same` is the STRICT count (nothing at all moved) and stays because
    it is the measurement the ruling was decided on — on the owner's pair it is 0 of 8
    while `folded` is 5, and a reader who cannot see both cannot see why the rule is what
    it is.
    """
    folded = sum(1 for s in segments if s["agreement"]["foldable"])
    return {
        "segments": len(segments),
        "folded": folded,
        "opened": len(segments) - folded,
        "fold_basis": "run_identity",
        VERDICT_SAME: sum(1 for s in segments if s["verdict"] == VERDICT_SAME),
        VERDICT_DIVERGED: sum(1 for s in segments if s["verdict"] == VERDICT_DIVERGED),
        VERDICT_ONE_SIDED: sum(1 for s in segments
                               if s["verdict"] == VERDICT_ONE_SIDED),
    }


def _gate_legend():
    """TWO gates. 🔴 The third (실재 / 「우연 아님」) is ABSENT, and this legend is where a
    reader can see that it is absent on purpose rather than broken."""
    return [
        {"id": "upstream", "label": "시간상 앞섬", "basis": "occurred_at",
         "doc": "그 사건이 관측보다 앞섰는가 — 두 시각의 비교이므로 n=2에서도 성립"},
        {"id": "mechanism", "label": "물리 경로 있음", "basis": mechanism_gate.CONFIG_FILENAME,
         "doc": "그 항목에서 이 불량으로 가는 경로가 «선언»돼 있는가 — 사실이 아니라 인용"},
    ]


def _note_inference_positioned(envelope, segments):
    """Segments whose place on the axis rests on a recipe book's date, not a run's.

    🔴 THE ORDER IS THE SCREEN'S MAIN CLAIM, so the one way it can lie gets named. Measured
    on `assy_manager`: `SYN-BW-101-06`'s DIFFUSION exists only as a `recipe_setpoint` atom
    dated after its BONDING atoms, so a fab step sorts below a packaging step. That is what
    the ledger says and the response does not silently reorder it.
    """
    hits = [s for s in segments if s["position_basis"] == "inference"]
    if not hits:
        return
    envelope["notes"].append({
        "note": "position_from_inference_only",
        "segments": [s["key"] for s in hits],
        "message": ("이 구간들은 «실측 시각»이 없어 추론 원자(레시피 설정값)의 날짜로 "
                    "자리를 잡았다 — 순서를 물리 순서로 읽지 말 것: "
                    + ", ".join(s["display"] for s in hits))})


def _note_bias_candidates(envelope, segments):
    """Every 「발생 아님」 on the journey, gathered — the brief's 편향 후보 requirement."""
    hits = []
    for segment in segments:
        for item in segment["items"]:
            if item["bias_candidate"] and item["verdict"] != VERDICT_SAME:
                hits.append((segment, item))
    if not hits:
        return
    envelope["notes"].append({
        "note": "bias_candidates",
        "items": [{"segment": s["key"], "candidate_key": i["candidate_key"],
                   "model": i["gates"]["mechanism"]["model"]} for s, i in hits],
        "message": ("발생 아님 — 관측 편향 후보: "
                    + ", ".join(f"{s['display']} · {i['display']}" for s, i in hits)
                    + ". 원인 카드와 같은 급으로 읽지 말 것")})
