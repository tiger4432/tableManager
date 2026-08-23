"""Dynamic defect trends for the R&D investigation workbench.

The read model is deliberately wafer-grained and ledger-backed.  A chart point and a
Trend Table row therefore carry the same ``mark_key``; no client-side join is needed to
make marking travel in either direction.

This module does *not* flatten product composition.  ``Wafer`` is the observation
subject declared by the active ``observed`` vocabulary.  Core/DT/Bonding composition is
a separate, branching question and must not be inferred from a trend row.
"""
from __future__ import annotations

import base64
import json
from collections import defaultdict
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


def mark_key(wafer: str, bonding_leg: str) -> str:
    return ledger_identity.encode_mark(str(wafer), str(bonding_leg))


def _encode_cursor(occurred_at: datetime, wafer: str, bonding_leg: str) -> str:
    raw = json.dumps({"v": 2, "t": occurred_at.isoformat(), "w": wafer,
                      "l": bonding_leg},
                     separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(text):
    if not text:
        return None
    try:
        padded = str(text) + "=" * (-len(str(text)) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if body.get("v") != 2 or not body.get("t") or not body.get("w") or not body.get("l"):
            raise ValueError("missing cursor member")
        instant = datetime.fromisoformat(str(body["t"]).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("cursor timestamp has no offset")
        return instant, str(body["w"]), str(body["l"])
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


def _definitions(selected):
    definitions = []
    for kind in selected:
        spec = finding_kinds.spec(kind)
        subtypes = [str(v) for v in (spec.get("classes") or ())]
        definitions.append({
            "id": kind,
            "label": spec.get("label") or kind,
            "active": bool(spec.get("active", True)),
            "selectable": bool(spec.get("active", True)),
            "subject_type": "Wafer",
            "aggregation_context": "bonding_experiment_unit",
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


def _series_sql():
    return """
WITH declared AS MATERIALIZED (
    SELECT * FROM jsonb_to_recordset(%(kind_methods)s::jsonb)
      AS d(kind text, method text)
), scans AS MATERIALIZED (
    SELECT r.base_wafer_id AS wafer, b.leg::text AS bonding_leg, d.kind,
           max(r.observed_at) AS scan_at, count(*) AS scan_denominator
    FROM inspection_run r JOIN declared d ON d.method = r.method
    JOIN bonding_map b ON b.base = r.base_wafer_id AND b.x = r.base_x AND b.y = r.base_y
    WHERE r.observed_at >= %(from)s AND r.observed_at < %(to)s
      AND r.base_wafer_id IS NOT NULL AND NULLIF(b.leg::text, '') IS NOT NULL
    GROUP BY r.base_wafer_id, b.leg::text, d.kind
), observed AS MATERIALIZED (
    SELECT subject_keys->>'wafer' AS wafer,
           object_payload->>'bonding_leg' AS bonding_leg,
           object_payload->>'finding_kind' AS kind,
           NULLIF(object_payload->>'class', '') AS subtype,
           occurred_at,
           COALESCE(object_payload->'die', object_payload->'position') AS die
    FROM ledger_events
    WHERE predicate = 'observed'
      AND occurred_at >= %(from)s AND occurred_at < %(to)s
      AND object_payload->>'finding_kind' = ANY(%(kinds)s)
      AND subject_type = 'Wafer'
      AND subject_keys ? 'wafer' AND object_payload ? 'bonding_leg'
), observed_wafer AS (
    SELECT wafer, bonding_leg, kind, NULL::text AS subtype, max(occurred_at) AS observed_at,
           count(*) AS events,
           count(DISTINCT die) FILTER (WHERE die IS NOT NULL) AS found_chips
    FROM observed GROUP BY wafer, bonding_leg, kind
    UNION ALL
    SELECT wafer, bonding_leg, kind, subtype, max(occurred_at) AS observed_at,
           count(*) AS events,
           count(DISTINCT die) FILTER (WHERE die IS NOT NULL) AS found_chips
    FROM observed WHERE subtype IS NOT NULL GROUP BY wafer, bonding_leg, kind, subtype
), per_wafer AS (
    SELECT s.wafer, s.bonding_leg, s.kind, NULL::text AS subtype,
           GREATEST(s.scan_at, o.observed_at) AS last_at,
           coalesce(o.events, 0) AS events, coalesce(o.found_chips, 0) AS found_chips,
           s.scan_denominator,
           CASE WHEN coalesce(o.events, 0) = 0 THEN 'scanned_clean' ELSE 'found' END AS metric_state
    FROM scans s LEFT JOIN observed_wafer o
      ON o.wafer = s.wafer AND o.bonding_leg = s.bonding_leg
     AND o.kind = s.kind AND o.subtype IS NULL
    UNION ALL
    SELECT o.wafer, o.bonding_leg, o.kind, o.subtype, o.observed_at, o.events, o.found_chips,
           coalesce(s.scan_denominator, 0),
           CASE WHEN s.wafer IS NULL THEN 'no_denominator' ELSE 'found' END
    FROM observed_wafer o LEFT JOIN scans s
      ON s.wafer = o.wafer AND s.bonding_leg = o.bonding_leg AND s.kind = o.kind
    WHERE o.subtype IS NOT NULL OR s.wafer IS NULL
), numbered AS (
    SELECT *, row_number() OVER
        (PARTITION BY kind, subtype ORDER BY last_at, wafer, bonding_leg) AS rn,
        count(*) OVER (PARTITION BY kind, subtype) AS n
    FROM per_wafer
)
SELECT wafer, bonding_leg, kind, subtype, last_at, events, found_chips, scan_denominator,
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


def _table_sql(has_cursor):
    cursor_clause = ""
    if has_cursor:
        cursor_clause = ("HAVING (max(occurred_at), wafer, bonding_leg) < "
                         "(%(cursor_at)s, %(cursor_wafer)s, %(cursor_leg)s)")
    return f"""
WITH declared AS MATERIALIZED (
    SELECT * FROM jsonb_to_recordset(%(kind_methods)s::jsonb)
      AS d(kind text, method text)
), scans AS MATERIALIZED (
    SELECT r.base_wafer_id AS wafer, b.leg::text AS bonding_leg, d.kind,
           max(r.observed_at) AS scan_at, count(*) AS scan_denominator
    FROM inspection_run r JOIN declared d ON d.method = r.method
    JOIN bonding_map b ON b.base = r.base_wafer_id AND b.x = r.base_x AND b.y = r.base_y
    WHERE r.observed_at >= %(from)s AND r.observed_at < %(to)s
      AND r.base_wafer_id IS NOT NULL AND NULLIF(b.leg::text, '') IS NOT NULL
    GROUP BY r.base_wafer_id, b.leg::text, d.kind
), observed AS MATERIALIZED (
    SELECT subject_keys->>'wafer' AS wafer,
           object_payload->>'bonding_leg' AS bonding_leg,
           object_payload->>'finding_kind' AS kind,
           NULLIF(object_payload->>'class', '') AS subtype,
           occurred_at,
           COALESCE(object_payload->'die', object_payload->'position') AS die
    FROM ledger_events
    WHERE predicate = 'observed'
      AND occurred_at >= %(from)s AND occurred_at < %(to)s
      AND object_payload->>'finding_kind' = ANY(%(kinds)s)
      AND subject_type = 'Wafer'
      AND subject_keys ? 'wafer' AND object_payload ? 'bonding_leg'
), population AS MATERIALIZED (
    SELECT wafer, bonding_leg, kind, scan_at AS occurred_at, scan_denominator FROM scans
    UNION ALL
    SELECT o.wafer, o.bonding_leg, o.kind, max(o.occurred_at), 0
    FROM observed o LEFT JOIN scans s
      ON s.wafer=o.wafer AND s.bonding_leg=o.bonding_leg AND s.kind=o.kind
    WHERE s.wafer IS NULL GROUP BY o.wafer, o.bonding_leg, o.kind
), page AS (
    SELECT wafer, bonding_leg, max(occurred_at) AS last_at
    FROM population
    GROUP BY wafer, bonding_leg
    {cursor_clause}
    ORDER BY last_at DESC, wafer DESC, bonding_leg DESC
    LIMIT %(page_size)s
)
SELECT p.wafer, p.bonding_leg, p.last_at, pop.kind, NULL::text AS subtype,
       count(o.wafer) AS events,
       count(DISTINCT o.die) FILTER (WHERE o.die IS NOT NULL) AS found_chips,
       max(pop.scan_denominator) AS scan_denominator,
       CASE WHEN max(pop.scan_denominator) > 0 AND count(o.wafer) = 0
            THEN 'scanned_clean'
            WHEN max(pop.scan_denominator) = 0 THEN 'no_denominator'
            ELSE 'found' END AS metric_state
FROM page p JOIN population pop
  ON pop.wafer = p.wafer AND pop.bonding_leg = p.bonding_leg
LEFT JOIN observed o
  ON o.wafer = p.wafer AND o.bonding_leg = p.bonding_leg AND o.kind = pop.kind
GROUP BY p.wafer, p.bonding_leg, p.last_at, pop.kind
ORDER BY p.last_at DESC, p.wafer DESC, p.bonding_leg DESC, pop.kind
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


def _identity(wafer, bonding_leg):
    return ledger_identity.identity(str(wafer), str(bonding_leg))


def _make_series(rows):
    grouped = defaultdict(list)
    totals = {}
    for raw in rows:
        (wafer, bonding_leg, kind, subtype, last_at, events, found_chips,
         scan_denominator, metric_state, rn, n) = raw
        series_id = f"{kind}:{subtype or 'all'}"
        grouped[series_id].append({
            "identity": _identity(str(wafer), str(bonding_leg)),
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


def _make_table(rows, limit):
    by_wafer = {}
    order = []
    for raw in rows:
        (wafer, bonding_leg, last_at, kind, subtype, events, found_chips,
         scan_denominator, metric_state) = raw
        wafer, bonding_leg = str(wafer), str(bonding_leg)
        unit = (wafer, bonding_leg)
        if unit not in by_wafer:
            by_wafer[unit] = {"identity": _identity(wafer, bonding_leg),
                               "occurred_at": last_at.isoformat(), "metrics": []}
            order.append(unit)
        by_wafer[unit]["metrics"].append({
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
    page_rows = [by_wafer[unit] for unit in visible]
    next_cursor = None
    if truncated and page_rows:
        tail = page_rows[-1]
        next_cursor = _encode_cursor(
            datetime.fromisoformat(tail["occurred_at"]),
            tail["identity"]["keys"]["wafer"],
            tail["identity"]["context"]["bonding_leg"])
    return {"rows": page_rows, "returned": len(page_rows), "limit": limit,
            "truncated": truncated, "next_cursor": next_cursor}


def _trace_state(count, total):
    if not count:
        return "absent"
    return "ready" if count == total else "partial"


def _attach_traceability(table, rows):
    by_wafer = {}
    for wafer, bonding_leg, total, core_count, dt_count, core_evidence, dt_evidence in rows:
        total, core_count, dt_count = int(total or 0), int(core_count or 0), int(dt_count or 0)
        by_wafer[(str(wafer), str(bonding_leg))] = {
            "dt": {"state": _trace_state(dt_count, total), "count": dt_count,
                   "component_denominator": total,
                   "evidence_ids": sorted(f"evidence:{value}" for value in (dt_evidence or []))},
            "core": {"state": _trace_state(core_count, total), "count": core_count,
                     "component_denominator": total,
                     "evidence_ids": sorted(f"evidence:{value}" for value in (core_evidence or []))},
        }
    for row in table["rows"]:
        identity = row["identity"]
        row["traceability"] = by_wafer.get((identity["keys"]["wafer"],
                                             identity["context"]["bonding_leg"]), {
            "dt": {"state": "absent", "count": 0, "component_denominator": 0,
                   "evidence_ids": [], "reason": "final_component_transfer_absent"},
            "core": {"state": "absent", "count": 0, "component_denominator": 0,
                     "evidence_ids": [], "reason": "final_component_transfer_absent"},
        })
    return table


def trends(connection, kinds=None, window=None, cursor=None, limit=None,
           max_points=None, now=None, relation=LEDGER_RELATION):
    """Return chart series and a cursor-paged Trend Table in one marking contract."""
    now = now or datetime.now(timezone.utc)
    declared = finding_kinds.kinds()
    definitions = _definitions(declared)
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
        "grain": {"subject_type": "Wafer",
                  "identity_fields": ["wafer"],
                  "aggregation_unit": "void_by_experiment_unit",
                  "context_fields": ["bonding_leg"],
                  "context_role": "planned_bonding_experiment_unit",
                  "marking": "identity.mark_key"},
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
            "denominator": {"source": "inspection_run",
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
              "max_points": point_limit, "page_size": page_limit + 1}
    if decoded:
        params.update(cursor_at=decoded[0], cursor_wafer=decoded[1], cursor_leg=decoded[2])
    series_rows = _fetch(connection, _series_sql(), params)
    table_rows = _fetch(connection, _table_sql(bool(decoded)), params)
    table = _make_table(table_rows, page_limit)
    page_units = [row["identity"]["keys"] for row in table["rows"]]
    trace_rows = (_fetch(connection, _traceability_sql(), {
        "from": applied.start, "to": applied.end,
        "page_units": json.dumps(page_units, separators=(",", ":"))})
                  if page_units else [])
    _attach_traceability(table, trace_rows)
    state = STATE_READY if series_rows or table["rows"] else STATE_EMPTY
    return dict(base, state=state, series=_make_series(series_rows), table=table)
