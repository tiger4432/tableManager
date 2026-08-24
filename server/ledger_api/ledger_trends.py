"""Dynamic defect trends for the R&D investigation workbench.

The read model is ledger-backed and grained at whatever unit the caller declares.  A
chart point and a Trend Table row carry the same ``mark_key``; no client-side join is
needed to make marking travel in either direction.

The ``grain`` object in the response used to be an *explanation* of a decision this
module had already made.  It is now the caller's declaration, and the response reflects
back what it was given.  Each axis carries two expressions because the two sides of the
ratio live in different places: the denominator is a column on a scan relation, the
numerator a path into an atom.  A ledger that carries the context in ``subject_keys``
rather than in ``object_payload`` is countable only because the numerator says which --
before it did, this route counted zero findings while reporting a healthy denominator.

Composition is *not* flattened here.  The observation subject is whatever the grain
declares; component composition is a separate, branching question and must never be
inferred from a trend row.

Below the declaration block, no schema word appears: axis names, the subject type and
the payload keys are values that travel in from the request.
"""
from __future__ import annotations

import base64
import json
import re
from collections import defaultdict, namedtuple
from datetime import datetime, timezone

from ledger_api import finding_kinds
from ledger_api import ledger_identity
from ledger_api import ledger_siblings
from ledger_trace import _fetch, relation_exists


LEDGER_RELATION = "ledger_events"
STATE_ABSENT = "absent"
STATE_EMPTY = "empty"
STATE_READY = "ready"
DEFAULT_WINDOW = "90d"
MAX_WINDOW_DAYS = 366
DEFAULT_LIMIT = 100
MAX_LIMIT = 200
DEFAULT_MAX_POINTS = 240
MAX_POINTS = 500

REASON_BAD_CURSOR = "bad_trend_cursor"
REASON_WINDOW_TOO_WIDE = "trend_window_too_wide"
REASON_BAD_LIMIT = "bad_trend_limit"
REASON_BAD_POINTS = "bad_trend_max_points"
REASON_EMPTY_KINDS = "empty_trend_kinds"
REASON_INACTIVE_KIND = "inactive_finding_kind"
REASON_BAD_GRAIN = "bad_trend_grain"

NUMERATOR_SOURCES = ("subject_keys", "object_payload")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

GrainPlan = namedtuple("GrainPlan", "declared names denominators numerators params")

# ---------------------------------------------------------------------------------
# 🔴 THE ONLY BLOCK IN THIS MODULE THAT MAY SPELL A FAB'S OWN WORDS.
#
# Everything below reads these two objects and never a name out of them.  A deployment
# whose ledger and scan relations are spelled differently replaces this block and nothing
# else -- which is also why the block is shaped like the request body: it is the default
# value of an input, not a decision.  Where the default is *read from* (this module today,
# a declaration file later) is a separate item and deliberately not settled here.
# ---------------------------------------------------------------------------------

# The scan side of the ratio.  Its FROM/JOIN is *structure* -- the number of relations is
# fixed here and never by the request -- so a declared axis names a relation this block
# already opens and nothing else.  An axis does NOT restate the ON clause: a caller cannot
# move it, so restating it could only ever agree, and a declaration with no freedom is a
# copy rather than a contract (ruling 2, 2026-08-23).  It comes back with the round that
# lets the FROM itself be declared.
SCAN_SOURCE = {
    "relation": "inspection_run",
    "alias": "r",
    "method_column": "method",
    "observed_at_column": "observed_at",
    "joins": [
        {"relation": "bonding_map", "alias": "b",
         "on": "b.base = r.base_wafer_id AND b.x = r.base_x AND b.y = r.base_y"},
    ],
}

DEFAULT_GRAIN = {
    # 🔴 DECLARED HERE, because the grain is what knows which subject it aggregates.
    # It used to be read off `ledger_identity`, which inverted the dependency: a mark
    # helper decided what the query would match.
    "subject_type": "wafer",
    "identity_fields": ["wafer"],
    "aggregation_unit": "void_by_experiment_unit",
    "context_fields": ["bonding_leg"],
    "context_role": ledger_identity.CONTEXT_ROLE,
    "marking": "identity.mark_key",
    "axes": [
        {"name": "wafer",
         "denominator": {"relation": "inspection_run", "column": "base_wafer_id"},
         "numerator": {"from": "subject_keys", "key": "wafer"}},
        {"name": "bonding_leg",
         "denominator": {"relation": "bonding_map", "column": "leg"},
         "numerator": {"from": "object_payload", "key": "bonding_leg"}},
    ],
}

# relation -> the alias the scans FROM binds it to.  A declared denominator is resolved
# against this, which is the whole of what a caller may choose about the scan side.
SCAN_RELATIONS = dict(
    [(SCAN_SOURCE["relation"], SCAN_SOURCE["alias"])]
    + [(join["relation"], join["alias"]) for join in SCAN_SOURCE["joins"]])

# Members the caller may state but may not yet move.  Not taste: `ledger_identity` spells
# the axis names into every mark_key, `/selection/resolve` and the client read that same
# mark, and the keyset cursor carries exactly that tuple.  Freeing them is the node-id
# marking step of the design, which comes after the finer subject is declared.
FENCED_GRAIN_MEMBERS = ("identity_fields", "context_fields", "aggregation_unit",
                        "context_role", "marking")

TRACE_DIMENSIONS = [
    {"id": "dt_trace", "label": "DT Trace",
     "ontology_path": ["Wafer", "FinalChip", "Component", "DT"],
     "states": ["ready", "partial", "absent"]},
    {"id": "core_trace", "label": "Core Trace",
     "ontology_path": ["Wafer", "FinalChip", "Component", "Core"],
     "states": ["ready", "partial", "absent"]},
]


class TrendRequestError(ValueError):
    def __init__(self, detail):
        super().__init__(detail.get("message") or detail.get("reason"))
        self.detail = detail


def mark_key(*unit) -> str:
    return ledger_identity.encode_mark(*(str(value) for value in unit))


def _encode_cursor(occurred_at: datetime, unit) -> str:
    # The keyset is (time, *unit values) at whatever arity the grain has; the token spells
    # no axis name so a renamed schema does not rename the cursor.
    raw = json.dumps({"v": 3, "t": occurred_at.isoformat(),
                      "k": [str(value) for value in unit]},
                     separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(text):
    if not text:
        return None
    try:
        padded = str(text) + "=" * (-len(str(text)) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        keys = body.get("k")
        if (body.get("v") != 3 or not body.get("t") or not isinstance(keys, list)
                or not keys or not all(keys)):
            raise ValueError("missing cursor member")
        instant = datetime.fromisoformat(str(body["t"]).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("cursor timestamp has no offset")
        return instant, [str(value) for value in keys]
    except Exception as exc:
        raise TrendRequestError({
            "reason": REASON_BAD_CURSOR,
            "message": f"Trend cursor를 해석할 수 없다: {exc}",
        }) from exc


def _bounded_int(value, default, maximum, reason, name):
    try:
        parsed = default if value is None else int(value)
    except (TypeError, ValueError) as exc:
        raise TrendRequestError({"reason": reason,
                                 "message": f"{name}은 정수여야 한다"}) from exc
    if parsed < 1 or parsed > maximum:
        raise TrendRequestError({
            "reason": reason, "minimum": 1, "maximum": maximum, "value": parsed,
            "message": f"{name}은 1..{maximum} 범위여야 한다",
        })
    return parsed


def _window(text, now):
    # An undeclared all-time scan is not a useful default on a fact table that is allowed
    # to grow to tens of millions of atoms.  The applied default is returned explicitly.
    parsed = ledger_siblings.parse_window(text or DEFAULT_WINDOW, now=now)
    if parsed.start is None or parsed.end is None:
        raise TrendRequestError({
            "reason": REASON_WINDOW_TOO_WIDE,
            "message": "Trend는 유계 기간이 필요하다",
        })
    span = parsed.end - parsed.start
    if span.total_seconds() > MAX_WINDOW_DAYS * 86400:
        raise TrendRequestError({
            "reason": REASON_WINDOW_TOO_WIDE,
            "maximum_days": MAX_WINDOW_DAYS,
            "message": f"Trend 기간은 최대 {MAX_WINDOW_DAYS}일이다",
        })
    return parsed


def _definitions(selected, grain):
    definitions = []
    for kind in selected:
        spec = finding_kinds.spec(kind)
        subtypes = [str(v) for v in (spec.get("classes") or ())]
        definitions.append({
            "id": kind,
            "label": spec.get("label") or kind,
            "active": bool(spec.get("active", True)),
            "selectable": bool(spec.get("active", True)),
            "subject_type": grain.declared["subject_type"],
            "aggregation_context": ledger_identity.UNIT_KIND,
            "subtypes": [{"id": value, "label": value} for value in subtypes],
            "series": ([{"id": f"{kind}:all", "subtype": None, "label": "전체"}]
                       + [{"id": f"{kind}:{value}", "subtype": value,
                           "label": value} for value in subtypes]),
            "metrics": [
                {"id": "event_count", "label": "관측 건수", "state": "ready"},
                {"id": "found_chip_count", "label": "발견 칩 수", "state": "ready"},
                {"id": "found_rate", "label": "발생 칩비",
                 "state": "ready" if finding_kinds.has_denominator(kind) else "absent",
                 "numerator": "found_chip_count",
                 "denominator": "scan_denominator",
                 **({"reason": "inspection_method_not_declared"}
                    if not finding_kinds.has_denominator(kind) else {})},
            ],
        })
    return definitions


def _refuse_grain(message, **named):
    raise TrendRequestError(dict({"reason": REASON_BAD_GRAIN, "message": message},
                                 **named))


def _fenced(declared, member):
    """A member the caller may state but may not yet move, and is told so by name."""
    expected = DEFAULT_GRAIN[member]
    stated = declared.get(member, expected)
    if stated != expected:
        _refuse_grain(f"grain.{member}은 아직 고정이다 (마킹 계약)",
                      field=member, declared=stated, fenced_to=expected)
    return list(expected) if isinstance(expected, list) else expected


def _axis_denominator(index, axis):
    stated = axis.get("denominator")
    if not isinstance(stated, dict):
        _refuse_grain(f"grain.axes[{index}].denominator는 객체여야 한다")
    relation = stated.get("relation")
    if relation not in SCAN_RELATIONS:
        _refuse_grain(f"grain.axes[{index}].denominator.relation이 scans가 여는 관계가 아니다",
                      declared=relation, allowed=sorted(SCAN_RELATIONS))
    alias = SCAN_RELATIONS[relation]
    column = stated.get("column")
    if not isinstance(column, str) or not _IDENTIFIER.match(column):
        _refuse_grain(f"grain.axes[{index}].denominator.column은 식별자여야 한다",
                      declared=column)
    # `::text` on every axis so the denominator meets the numerator's `->>` as the same
    # type no matter what a declared column happens to be underneath.
    return f"{alias}.{column}::text", {"relation": relation, "column": column}


def _axis_numerator(index, axis):
    stated = axis.get("numerator")
    if not isinstance(stated, dict):
        _refuse_grain(f"grain.axes[{index}].numerator는 객체여야 한다")
    source = stated.get("from")
    if source not in NUMERATOR_SOURCES:
        _refuse_grain(f"grain.axes[{index}].numerator.from은 원자의 어느 자리를 읽는지 말해야 한다",
                      declared=source, allowed=list(NUMERATOR_SOURCES))
    key = stated.get("key")
    if not isinstance(key, str) or not key:
        _refuse_grain(f"grain.axes[{index}].numerator.key는 비어 있지 않은 문자열이어야 한다",
                      declared=key)
    # The key is bound, never spelled into the SQL: it is a value, not an identifier.
    return (source, f"grain_key_{index}"), {"from": source, "key": key}


def _grain(stated):
    """Resolve the caller's grain into the column lists and bindings the SQL takes.

    Refuses before any SQL is built, like every other malformed question on this route.
    """
    if stated is None:
        stated = DEFAULT_GRAIN
    if isinstance(stated, str):
        try:
            stated = json.loads(stated)
        except ValueError as exc:
            _refuse_grain(f"grain을 JSON으로 해석할 수 없다: {exc}")
    if not isinstance(stated, dict):
        _refuse_grain("grain은 객체여야 한다")

    subject_type = stated.get("subject_type", DEFAULT_GRAIN["subject_type"])
    if not isinstance(subject_type, str) or not subject_type.strip():
        _refuse_grain("grain.subject_type은 비어 있지 않은 문자열이어야 한다",
                      declared=subject_type)
    fenced = {member: _fenced(stated, member) for member in FENCED_GRAIN_MEMBERS}

    names = fenced["identity_fields"] + fenced["context_fields"]
    axes = stated.get("axes", DEFAULT_GRAIN["axes"])
    if (not isinstance(axes, list)
            or [axis.get("name") if isinstance(axis, dict) else None
                for axis in axes] != names):
        _refuse_grain("grain.axes는 identity_fields + context_fields와 이름·순서가 같아야 한다",
                      expected=names)

    denominators, numerators, params, echo = [], [], {}, []
    for index, axis in enumerate(axes):
        expression, denominator = _axis_denominator(index, axis)
        binding, numerator = _axis_numerator(index, axis)
        denominators.append(expression)
        numerators.append(binding)
        params[binding[1]] = numerator["key"]
        echo.append({"name": names[index], "denominator": denominator,
                     "numerator": numerator})
    params["grain_subject_type"] = subject_type
    # Echoed in the key order the response has always used, so a reader diffing the two
    # eras sees the added `axes` and nothing else moved.
    reflected = {member: DEFAULT_GRAIN[member] for member in DEFAULT_GRAIN}
    reflected.update(fenced, subject_type=subject_type, axes=echo)
    return GrainPlan(declared=reflected, names=names, denominators=denominators,
                     numerators=numerators, params=params)


def _join_on(grain, left, right):
    return " AND ".join(f"{left}.{name} = {right}.{name}" for name in grain.names)


def _qualified(grain, alias, suffix=""):
    return ", ".join(f"{alias}.{name}{suffix}" for name in grain.names)


def _base_ctes(grain):
    """`declared` + `scans` + `observed`, shared verbatim by the series and table reads.

    Only the column *lists* and the two per-axis expressions come from the grain.  The
    FROM/JOIN shape is untouched, which is why an axis names a relation and a column and
    says nothing about how the relation is joined.
    """
    alias = SCAN_SOURCE["alias"]
    scan = f"{alias}.{SCAN_SOURCE['observed_at_column']}"
    source = "\n".join(
        [f"    FROM {SCAN_SOURCE['relation']} {alias} JOIN declared d "
         f"ON d.method = {alias}.{SCAN_SOURCE['method_column']}"]
        + [f"    JOIN {join['relation']} {join['alias']} ON {join['on']}"
           for join in SCAN_SOURCE["joins"]])
    projection = (",\n" + " " * 11).join(
        f"{path}->>%({param})s AS {name}"
        for (path, param), name in zip(grain.numerators, grain.names))
    return f"""
WITH declared AS MATERIALIZED (
    SELECT * FROM jsonb_to_recordset(%(kind_methods)s::jsonb)
      AS d(kind text, method text)
), scans AS MATERIALIZED (
    SELECT {", ".join(f"{expr} AS {name}" for expr, name
                      in zip(grain.denominators, grain.names))}, d.kind,
           max({scan}) AS scan_at, count(*) AS scan_denominator
{source}
    WHERE {scan} >= %(from)s AND {scan} < %(to)s
      AND {" AND ".join(f"NULLIF({expr}, '') IS NOT NULL"
                        for expr in grain.denominators)}
    GROUP BY {", ".join(grain.denominators)}, d.kind
), observed AS MATERIALIZED (
    SELECT {projection},
           {finding_kinds.payload_field_sql('object_payload', 'finding_kind')} AS kind,
           NULLIF(object_payload->>'class', '') AS subtype,
           occurred_at,
           COALESCE(object_payload->'die', object_payload->'position') AS die
    FROM ledger_events
    WHERE predicate = 'observed'
      AND occurred_at >= %(from)s AND occurred_at < %(to)s
      AND {finding_kinds.payload_field_sql('object_payload', 'finding_kind')} = ANY(%(kinds)s)
      AND subject_type = %(grain_subject_type)s
      AND {" AND ".join(f"{path} ? %({param})s"
                        for path, param in grain.numerators)}
)"""


def _series_sql(grain):
    columns = ", ".join(grain.names)
    first = grain.names[0]
    return _base_ctes(grain) + f""", observed_unit AS (
    SELECT {columns}, kind, NULL::text AS subtype, max(occurred_at) AS observed_at,
           count(*) AS events,
           count(DISTINCT die) FILTER (WHERE die IS NOT NULL) AS found_chips
    FROM observed GROUP BY {columns}, kind
    UNION ALL
    SELECT {columns}, kind, subtype, max(occurred_at) AS observed_at,
           count(*) AS events,
           count(DISTINCT die) FILTER (WHERE die IS NOT NULL) AS found_chips
    FROM observed WHERE subtype IS NOT NULL GROUP BY {columns}, kind, subtype
), per_unit AS (
    SELECT {_qualified(grain, "s")}, s.kind, NULL::text AS subtype,
           GREATEST(s.scan_at, o.observed_at) AS last_at,
           coalesce(o.events, 0) AS events, coalesce(o.found_chips, 0) AS found_chips,
           s.scan_denominator,
           CASE WHEN coalesce(o.events, 0) = 0 THEN 'scanned_clean' ELSE 'found' END AS metric_state
    FROM scans s LEFT JOIN observed_unit o
      ON {_join_on(grain, "o", "s")}
     AND o.kind = s.kind AND o.subtype IS NULL
    UNION ALL
    SELECT {_qualified(grain, "o")}, o.kind, o.subtype, o.observed_at, o.events, o.found_chips,
           coalesce(s.scan_denominator, 0),
           CASE WHEN s.{first} IS NULL THEN 'no_denominator' ELSE 'found' END
    FROM observed_unit o LEFT JOIN scans s
      ON {_join_on(grain, "s", "o")} AND s.kind = o.kind
    WHERE o.subtype IS NOT NULL OR s.{first} IS NULL
), numbered AS (
    SELECT *, row_number() OVER
        (PARTITION BY kind, subtype ORDER BY last_at, {columns}) AS rn,
        count(*) OVER (PARTITION BY kind, subtype) AS n
    FROM per_unit
)
SELECT {columns}, kind, subtype, last_at, events, found_chips, scan_denominator,
       metric_state, rn, n
FROM numbered
WHERE rn = 1
   OR (%(max_points)s > 1 AND (
          rn = n OR mod(
              rn - 1,
              GREATEST(1, ceil((n - 1)::numeric / (%(max_points)s - 1))::bigint)
          ) = 0
      ))
ORDER BY kind, subtype NULLS FIRST, rn
"""


def _table_sql(has_cursor, grain):
    columns = ", ".join(grain.names)
    first = grain.names[0]
    cursor_clause = ""
    if has_cursor:
        bindings = ", ".join(f"%(cursor_key_{index})s"
                             for index in range(len(grain.names)))
        cursor_clause = (f"HAVING (max(occurred_at), {columns}) < "
                         f"(%(cursor_at)s, {bindings})")
    return _base_ctes(grain) + f""", population AS MATERIALIZED (
    SELECT {columns}, kind, scan_at AS occurred_at, scan_denominator FROM scans
    UNION ALL
    SELECT {_qualified(grain, "o")}, o.kind, max(o.occurred_at), 0
    FROM observed o LEFT JOIN scans s
      ON {_join_on(grain, "s", "o")} AND s.kind = o.kind
    WHERE s.{first} IS NULL GROUP BY {_qualified(grain, "o")}, o.kind
), page AS (
    SELECT {columns}, max(occurred_at) AS last_at
    FROM population
    GROUP BY {columns}
    {cursor_clause}
    ORDER BY last_at DESC, {", ".join(f"{name} DESC" for name in grain.names)}
    LIMIT %(page_size)s
)
SELECT {_qualified(grain, "p")}, p.last_at, pop.kind, NULL::text AS subtype,
       count(o.{first}) AS events,
       count(DISTINCT o.die) FILTER (WHERE o.die IS NOT NULL) AS found_chips,
       max(pop.scan_denominator) AS scan_denominator,
       CASE WHEN max(pop.scan_denominator) > 0 AND count(o.{first}) = 0
            THEN 'scanned_clean'
            WHEN max(pop.scan_denominator) = 0 THEN 'no_denominator'
            ELSE 'found' END AS metric_state
FROM page p JOIN population pop
  ON {_join_on(grain, "pop", "p")}
LEFT JOIN observed o
  ON {_join_on(grain, "o", "p")} AND o.kind = pop.kind
GROUP BY {_qualified(grain, "p")}, p.last_at, pop.kind
ORDER BY p.last_at DESC, {_qualified(grain, "p", " DESC")}, pop.kind
"""
def _traceability_sql():
    """Trace only final-component evidence for the already bounded table page."""
    return """
WITH final_components AS MATERIALIZED (
    SELECT object_payload->'to'->'keys'->>'base_wafer_id' AS wafer,
           object_payload->'to'->'keys'->>'bonding_leg' AS bonding_leg,
           object_payload->'component'->>'final_chip_id' AS final_chip_id,
           object_payload->'component'->>'component_id' AS component_id,
           NULLIF(subject_keys->>'wafer', '') AS core_wafer,
           id
    FROM ledger_events e
    JOIN jsonb_to_recordset(%(page_units)s::jsonb)
      AS u(wafer text, bonding_leg text)
      ON u.wafer = e.object_payload->'to'->'keys'->>'base_wafer_id'
     AND u.bonding_leg = e.object_payload->'to'->'keys'->>'bonding_leg'
    WHERE predicate = 'transferred'
      AND occurred_at >= %(from)s AND occurred_at < %(to)s
      AND object_payload->'to'->>'type' = 'bond_layer'
      AND NULLIF(object_payload->'component'->>'component_id', '') IS NOT NULL
), component_events AS MATERIALIZED (
    SELECT f.wafer, f.bonding_leg, f.component_id, f.core_wafer,
           e.id,
           CASE WHEN e.object_payload->'from'->>'type' = 'dt_slot'
                  OR e.object_payload->'to'->>'type' = 'dt_slot'
                  OR e.object_payload->'from'->'keys' ? 'dt_lot'
                  OR e.object_payload->'to'->'keys' ? 'dt_lot'
                THEN true ELSE false END AS has_dt
    FROM final_components f
    JOIN ledger_events e
      ON e.predicate = 'transferred'
     AND e.occurred_at >= %(from)s AND e.occurred_at < %(to)s
     AND e.object_payload->'component'->>'component_id' = f.component_id
     AND e.object_payload->'component'->>'final_chip_id' = f.final_chip_id
), dt_components AS MATERIALIZED (
    SELECT wafer, bonding_leg, component_id, min(id::text) AS evidence_id
    FROM component_events WHERE has_dt
    GROUP BY wafer, bonding_leg, component_id
)
SELECT f.wafer, f.bonding_leg,
       count(DISTINCT f.component_id) AS components,
       count(DISTINCT f.component_id) FILTER (WHERE f.core_wafer IS NOT NULL) AS core_components,
       count(DISTINCT d.component_id) AS dt_components,
       array_agg(DISTINCT f.id::text) FILTER (WHERE f.core_wafer IS NOT NULL) AS core_evidence,
       array_agg(DISTINCT d.evidence_id) FILTER (WHERE d.component_id IS NOT NULL) AS dt_evidence
FROM final_components f
LEFT JOIN dt_components d
  ON d.wafer = f.wafer AND d.bonding_leg = f.bonding_leg
 AND d.component_id = f.component_id
GROUP BY f.wafer, f.bonding_leg
ORDER BY f.wafer, f.bonding_leg
"""


def _identity(unit, subject_type):
    # The mark layer still takes the axis values positionally; that positional contract
    # is what fences the axis names, and it is the node-id step that retires it.
    return ledger_identity.identity(*(str(value) for value in unit),
                                    subject_type=subject_type)


def _split(raw, arity):
    """Peel the grain's leading columns off a result row, whatever they are named."""
    return tuple(str(value) for value in raw[:arity]), raw[arity:]


def _make_series(rows, grain):
    grouped = defaultdict(list)
    totals = {}
    arity = len(grain.names)
    for raw in rows:
        unit, rest = _split(raw, arity)
        (kind, subtype, last_at, events, found_chips,
         scan_denominator, metric_state, rn, n) = rest
        series_id = f"{kind}:{subtype or 'all'}"
        grouped[series_id].append({
            "identity": _identity(unit, grain.declared["subject_type"]),
            "occurred_at": last_at.isoformat(),
            "value": {"event_count": int(events or 0),
                      "found_chip_count": int(found_chips or 0),
                      "scan_denominator": int(scan_denominator or 0),
                      "found_rate": (round(int(found_chips or 0) /
                                           int(scan_denominator), 6)
                                     if scan_denominator else None),
                      "state": metric_state},
            "source_order": int(rn),
        })
        totals[series_id] = int(n)
    return [{
        "id": series_id,
        "points": points,
        "downsampling": {"strategy": "deterministic_stride",
                         "input_wafer_count": totals[series_id],
                         "returned_points": len(points)},
    } for series_id, points in sorted(grouped.items())]


def _make_table(rows, limit, grain):
    by_unit = {}
    order = []
    arity = len(grain.names)
    for raw in rows:
        unit, rest = _split(raw, arity)
        (last_at, kind, subtype, events, found_chips,
         scan_denominator, metric_state) = rest
        if unit not in by_unit:
            by_unit[unit] = {"identity": _identity(
                unit, grain.declared["subject_type"]),
                             "occurred_at": last_at.isoformat(), "metrics": []}
            order.append(unit)
        by_unit[unit]["metrics"].append({
            "kind": str(kind), "subtype": subtype,
            "series_id": f"{kind}:{subtype or 'all'}",
            "event_count": int(events or 0),
            "found_chip_count": int(found_chips or 0),
            "scan_denominator": int(scan_denominator or 0),
            "found_rate": (round(int(found_chips or 0) / int(scan_denominator), 6)
                           if scan_denominator else None),
            "state": metric_state,
        })
    truncated = len(order) > limit
    visible = order[:limit]
    page_rows = [by_unit[unit] for unit in visible]
    next_cursor = None
    if truncated and visible:
        # From the unit tuple the SQL returned, not by reading the axis names back out of
        # the identity object -- that lookup is the one that goes wrong on a rename.
        next_cursor = _encode_cursor(
            datetime.fromisoformat(page_rows[-1]["occurred_at"]), visible[-1])
    return {"rows": page_rows, "returned": len(page_rows), "limit": limit,
            "truncated": truncated, "next_cursor": next_cursor}, visible


def _trace_state(count, total):
    if not count:
        return "absent"
    return "ready" if count == total else "partial"


def _attach_traceability(table, units, rows, arity):
    by_unit = {}
    for raw in rows:
        unit, rest = _split(raw, arity)
        total, core_count, dt_count, core_evidence, dt_evidence = rest
        total, core_count, dt_count = int(total or 0), int(core_count or 0), int(dt_count or 0)
        by_unit[unit] = {
            "dt": {"state": _trace_state(dt_count, total), "count": dt_count,
                   "component_denominator": total,
                   "evidence_ids": sorted(f"evidence:{value}" for value in (dt_evidence or []))},
            "core": {"state": _trace_state(core_count, total), "count": core_count,
                     "component_denominator": total,
                     "evidence_ids": sorted(f"evidence:{value}" for value in (core_evidence or []))},
        }
    for row, unit in zip(table["rows"], units):
        row["traceability"] = by_unit.get(unit, {
            "dt": {"state": "absent", "count": 0, "component_denominator": 0,
                   "evidence_ids": [], "reason": "final_component_transfer_absent"},
            "core": {"state": "absent", "count": 0, "component_denominator": 0,
                     "evidence_ids": [], "reason": "final_component_transfer_absent"},
        })
    return table


def trends(connection, kinds=None, window=None, cursor=None, limit=None,
           max_points=None, now=None, relation=LEDGER_RELATION, grain=None):
    """Return chart series and a cursor-paged Trend Table in one marking contract."""
    now = now or datetime.now(timezone.utc)
    plan = _grain(grain)
    declared = finding_kinds.kinds()
    definitions = _definitions(declared, plan)
    if kinds is None:
        selected = [row["id"] for row in definitions if row["active"]]
    else:
        selected = [item.strip() for item in str(kinds).split(",") if item.strip()]
        if not selected:
            raise TrendRequestError({"reason": REASON_EMPTY_KINDS,
                                     "message": "Trend 종류를 하나 이상 선택해야 한다"})
    # Resolve every name before touching the database.  Unknown means refusal, never drop.
    for kind in selected:
        spec = finding_kinds.spec(kind)
        if not spec.get("active", True):
            raise TrendRequestError({"reason": REASON_INACTIVE_KIND,
                                     "kind": kind,
                                     "message": f"비활성 Trend 종류는 선택할 수 없다: {kind}"})
    selected = list(dict.fromkeys(selected))

    page_limit = _bounded_int(limit, DEFAULT_LIMIT, MAX_LIMIT,
                              REASON_BAD_LIMIT, "limit")
    point_limit = _bounded_int(max_points, DEFAULT_MAX_POINTS, MAX_POINTS,
                               REASON_BAD_POINTS, "max_points")
    applied = _window(window, now)
    decoded = _decode_cursor(cursor)
    base = {
        "generated_at": now.isoformat(),
        "grain": plan.declared,
        "finding_kinds": definitions,
        "selectable_finding_kinds": definitions,
        "applied_kinds": selected,
        "trace_dimensions": TRACE_DIMENSIONS,
        "window": {"requested": window, "applied": applied.as_dict(),
                   "defaulted": not bool(window)},
        "composition": {"included": False,
                        "reason": "trend_grain_is_observation_subject_not_chip_composition"},
        "provenance": {
            "numerator": {"source": relation, "ledger_backed": True,
                          "predicate": "observed"},
            "denominator": {"source": SCAN_SOURCE["relation"],
                            "declared_by": "finding_kinds.methods",
                            "absence_is_zero": False},
        },
    }
    if not relation_exists(connection, relation):
        return dict(base, state=STATE_ABSENT, series=[],
                    table={"rows": [], "returned": 0, "limit": page_limit,
                           "truncated": False, "next_cursor": None})

    kind_methods = [{"kind": kind, "method": method}
                    for kind in selected for method in finding_kinds.methods(kind)]
    params = {"from": applied.start, "to": applied.end, "kinds": selected,
              "kind_methods": json.dumps(kind_methods, separators=(",", ":")),
              "max_points": point_limit, "page_size": page_limit + 1,
              **plan.params}
    if decoded:
        params["cursor_at"] = decoded[0]
        params.update({f"cursor_key_{index}": value
                       for index, value in enumerate(decoded[1])})
    series_rows = _fetch(connection, _series_sql(plan), params)
    table_rows = _fetch(connection, _table_sql(bool(decoded), plan), params)
    table, units = _make_table(table_rows, page_limit, plan)
    page_units = [dict(zip(plan.names, unit)) for unit in units]
    trace_rows = (_fetch(connection, _traceability_sql(), {
        "from": applied.start, "to": applied.end,
        "page_units": json.dumps(page_units, separators=(",", ":"))})
                  if page_units else [])
    _attach_traceability(table, units, trace_rows, len(plan.names))
    state = STATE_READY if series_rows or table["rows"] else STATE_EMPTY
    return dict(base, state=state, series=_make_series(series_rows, plan), table=table)
