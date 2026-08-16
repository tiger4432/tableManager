"""Reverse composition trace for a final composite CHIP.

Unlike the lot lineage walk, this projection preserves one ordered movement path per
component and then returns the collection of paths as a many-to-many DAG.  It never picks
one representative DT and never folds several components into one wafer journey.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from urllib.parse import quote

import ledger_siblings
from ledger_trace import _fetch, relation_exists


LEDGER_RELATION = "ledger_events"
DEFAULT_WINDOW = "365d"
MAX_WINDOW_DAYS = 730


class CompositionRequestError(ValueError):
    def __init__(self, detail):
        super().__init__(detail.get("message") or detail.get("reason"))
        self.detail = detail


def _stable(prefix, value):
    return f"{prefix}:" + quote(str(value), safe="")


def _window(text, now):
    parsed = ledger_siblings.parse_window(text or DEFAULT_WINDOW, now=now)
    if parsed.start is None or parsed.end is None:
        raise CompositionRequestError({"reason": "composition_window_required",
                                       "message": "구성 추적은 유계 기간이 필요하다"})
    if (parsed.end - parsed.start).total_seconds() > MAX_WINDOW_DAYS * 86400:
        raise CompositionRequestError({
            "reason": "composition_window_too_wide", "maximum_days": MAX_WINDOW_DAYS,
            "message": f"구성 추적 기간은 최대 {MAX_WINDOW_DAYS}일이다"})
    return parsed


def _movement_sql():
    return """
SELECT id, subject_keys, object_payload, occurred_at, source_raw_ref
FROM ledger_events
WHERE predicate = 'transferred'
  AND occurred_at >= %(from)s AND occurred_at < %(to)s
  AND object_payload->'component'->>'final_chip_id' = %(final_chip_id)s
ORDER BY object_payload->'component'->>'component_id',
         (object_payload->>'sequence')::integer, occurred_at, id
"""


def _process_sql():
    return """
WITH RECURSIVE membership AS (
    SELECT id, object_payload->'keys'->>'wafer' AS wafer,
           subject_keys->>'lot' AS lot, subject_keys, object_payload,
           occurred_at, source_raw_ref
    FROM ledger_events
    WHERE predicate = 'has_wafer'
      AND occurred_at >= %(from)s AND occurred_at < %(to)s
      AND object_payload->'keys'->>'wafer' = ANY(%(wafers)s)
), lineage AS (
    SELECT wafer, lot, 0 AS depth, ARRAY[lot]::text[] AS path,
           id, 'has_wafer'::text AS predicate, subject_keys, object_payload,
           occurred_at, source_raw_ref
    FROM membership
    UNION ALL
    SELECT w.wafer, e.object_payload->'keys'->>'lot', w.depth + 1,
           w.path || (e.object_payload->'keys'->>'lot'),
           e.id, e.predicate, e.subject_keys, e.object_payload,
           e.occurred_at, e.source_raw_ref
    FROM lineage w
    JOIN ledger_events e
      ON e.subject_keys->>'lot' = w.lot AND e.predicate = 'derived_from'
     AND e.occurred_at >= %(from)s AND e.occurred_at < %(to)s
    WHERE w.depth < 20
      AND NOT (e.object_payload->'keys'->>'lot' = ANY(w.path))
), records AS (
    SELECT id, subject_keys->>'wafer' AS wafer, object_payload,
           occurred_at, source_raw_ref
    FROM ledger_events
    WHERE predicate = 'processed_with'
      AND occurred_at >= %(from)s AND occurred_at < %(to)s
      AND subject_keys->>'wafer' = ANY(%(wafers)s)
    UNION ALL
    SELECT id, wafer,
           jsonb_build_object(
               '__record_kind', 'lineage', 'predicate', predicate,
               'subject_keys', subject_keys, 'object_payload', object_payload,
               'depth', depth, 'path', path),
           occurred_at, source_raw_ref
    FROM lineage
)
SELECT id, wafer, object_payload, occurred_at, source_raw_ref
FROM records ORDER BY wafer, occurred_at, id
"""


def _place_id(place):
    place = place or {}
    keys = place.get("keys") or {}
    rendered = ",".join(f"{k}={keys[k]}" for k in sorted(keys))
    pos = place.get("position")
    if pos is not None:
        rendered += "@" + json.dumps(pos, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False)
    return _stable(place.get("type") or "place", rendered)


def composition(connection, final_chip_id, window=None, now=None,
                relation=LEDGER_RELATION):
    now = now or datetime.now(timezone.utc)
    final_chip_id = str(final_chip_id or "").strip()
    if not final_chip_id:
        raise CompositionRequestError({"reason": "final_chip_required",
                                       "message": "final_chip_id가 필요하다"})
    applied = _window(window, now)
    base = {
        "generated_at": now.isoformat(),
        "final_chip": {"entity_id": _stable("final_chip", final_chip_id),
                       "keys": {"final_chip_id": final_chip_id}},
        "window": {"requested": window, "applied": applied.as_dict(),
                   "defaulted": not bool(window)},
        "cardinality": {"components": "variable", "transfer_events": "variable",
                        "dt_collections": "variable"},
        "provenance": {"source": relation, "predicate": "transferred",
                       "ledger_backed": True},
        "final_subject_resolution": {
            "state": "absent",
            "basis": "transferred.to.bond_layer.keys.bond_wafer",
            "final_chip_id": final_chip_id,
            "candidates": [],
        },
    }
    if not relation_exists(connection, relation):
        return dict(base, state="absent", components=[], graph={"nodes": [], "edges": []})

    params = {"from": applied.start, "to": applied.end,
              "final_chip_id": final_chip_id}
    movement_rows = _fetch(connection, _movement_sql(), params)
    if not movement_rows:
        return dict(base, state="empty", components=[], graph={"nodes": [], "edges": []})

    components = {}
    nodes, edges = {}, []
    core_wafers = set()
    for atom_id, subject_keys, payload, occurred_at, raw_ref in movement_rows:
        payload = payload or {}
        meta = payload.get("component") or {}
        component_id = str(meta.get("component_id") or "").strip()
        if not component_id:
            # Missing identity cannot be grouped honestly.  Preserve it as its own
            # unresolvable component, keyed by evidence rather than merging absences.
            component_id = f"unresolved@{atom_id}"
        entity_id = _stable("component", component_id)
        core_wafer = str((subject_keys or {}).get("wafer") or "")
        if core_wafer:
            core_wafers.add(core_wafer)
        component = components.setdefault(entity_id, {
            "entity_id": entity_id, "component_id": component_id,
            "core": {"wafer": core_wafer or None,
                     "lot": meta.get("core_lot"), "slot": meta.get("core_slot"),
                     "type": meta.get("core_type"), "role": meta.get("role"),
                     "branch": meta.get("core_branch"),
                     "lineage": {"state": "absent", "events": []}},
            "bonding": {"layer": meta.get("bond_layer"),
                        "position": meta.get("bond_position")},
            "resolution_state": meta.get("state") or "unresolvable",
            "transfer_events": [], "dt_collections": [],
            "upstream_process": {"subject": {"type": "Wafer",
                                               "keys": {"wafer": core_wafer}},
                                 "evidence_ids": [], "events": []},
        })
        source, target = payload.get("from") or {}, payload.get("to") or {}
        source_id, target_id = _place_id(source), _place_id(target)
        nodes.setdefault(source_id, {"entity_id": source_id, **source})
        nodes.setdefault(target_id, {"entity_id": target_id, **target})
        evidence_id = _stable("evidence", atom_id)
        event = {"evidence_id": evidence_id, "sequence": payload.get("sequence"),
                 "occurred_at": occurred_at.isoformat(), "from": source,
                 "to": target, "qty": payload.get("qty"), "source_raw_ref": raw_ref}
        component["transfer_events"].append(event)
        edges.append({"edge_id": evidence_id, "component_id": entity_id,
                      "from": source_id, "to": target_id,
                      "sequence": payload.get("sequence")})
        for place in (source, target):
            if place.get("type") == "dt_slot":
                dt = {"entity_id": _place_id(place), "keys": place.get("keys") or {},
                      "position": place.get("position")}
                if dt not in component["dt_collections"]:
                    component["dt_collections"].append(dt)

    process_rows = (_fetch(connection, _process_sql(),
                           {**params, "wafers": sorted(core_wafers)})
                    if core_wafers else [])
    process_by_wafer = defaultdict(list)
    lineage_by_wafer = defaultdict(list)
    for atom_id, wafer, payload, occurred_at, raw_ref in process_rows:
        payload = payload or {}
        evidence_id = _stable("evidence", atom_id)
        if payload.get("__record_kind") == "lineage":
            lineage_by_wafer[str(wafer)].append({
                "evidence_id": evidence_id,
                "predicate": payload.get("predicate"),
                "subject_keys": payload.get("subject_keys") or {},
                "object_payload": payload.get("object_payload") or {},
                "depth": payload.get("depth"),
                "path": payload.get("path") or [],
                "occurred_at": occurred_at.isoformat(),
                "source_raw_ref": raw_ref,
            })
            continue

        # Keep the ledger value intact.  Normalized aliases make common R&D
        # comparisons convenient, while explicit key checks distinguish an absent
        # claim from a present null/zero/false value.
        knobs = {}
        parameters = []
        if "params_actual" in payload:
            knobs["actual"] = payload.get("params_actual")
            parameters.append({"source": "actual",
                               "values": payload.get("params_actual")})
        if "params_setpoint" in payload:
            knobs["setpoint"] = payload.get("params_setpoint")
            parameters.append({"source": "setpoint",
                               "values": payload.get("params_setpoint")})
        event = {
            "evidence_id": evidence_id,
            "step": payload.get("step"),
            "step_family": payload.get("step_family"),
            "equipment": payload.get("eqp"),
            "claims_present": [key for key in ("step", "step_family", "eqp",
                                                 "recipe", "params_actual",
                                                 "params_setpoint")
                               if key in payload],
            "parameters": parameters,
            "knobs": knobs,
            "payload": payload,
            "occurred_at": occurred_at.isoformat(),
            "source_raw_ref": raw_ref,
        }
        if "recipe" in payload:
            event["recipe"] = payload.get("recipe")
        process_by_wafer[str(wafer)].append(event)
    for component in components.values():
        wafer = component["core"]["wafer"]
        events = process_by_wafer.get(wafer, [])
        # Backward-compatible legacy alias.  It historically contained event
        # summaries despite its name, so retain that shape and add the clear field.
        component["upstream_process"]["evidence_ids"] = [
            {"evidence_id": event["evidence_id"], "step": event["step"],
             "occurred_at": event["occurred_at"],
             "source_raw_ref": event["source_raw_ref"]}
            for event in events
        ]
        component["upstream_process"]["events"] = events
        lineage = lineage_by_wafer.get(wafer, [])
        component["core"]["lineage"] = {
            "state": "resolved" if lineage else "absent", "events": lineage}

    final_candidates = {}
    for atom_id, _subject_keys, payload, occurred_at, raw_ref in movement_rows:
        target = (payload or {}).get("to") or {}
        target_keys = target.get("keys") or {}
        final_wafer = (target_keys.get("bond_wafer")
                       if target.get("type") == "bond_layer" else None)
        if not final_wafer:
            continue
        candidate = final_candidates.setdefault(str(final_wafer), {
            "wafer": str(final_wafer), "entity_id": _stable("wafer", final_wafer),
            "evidence_ids": []})
        candidate["evidence_ids"].append(_stable("evidence", atom_id))
    candidates = sorted(final_candidates.values(), key=lambda row: row["entity_id"])
    resolution_state = ("resolved" if len(candidates) == 1 else
                        "contested" if candidates else "absent")
    final_subject_resolution = {
        "state": resolution_state,
        "basis": "transferred.to.bond_layer.keys.bond_wafer",
        "final_chip_id": final_chip_id,
        "candidates": candidates,
    }
    if resolution_state == "resolved":
        final_subject_resolution["wafer"] = candidates[0]

    ordered = sorted(components.values(), key=lambda c: (
        c["bonding"].get("layer") is None, c["bonding"].get("layer") or 0,
        c["entity_id"]))
    dt_ids = sorted({dt["entity_id"] for c in ordered for dt in c["dt_collections"]})
    return dict(base, state="ready", components=ordered,
                graph={"nodes": list(nodes.values()), "edges": edges},
                final_subject_resolution=final_subject_resolution,
                summary={"component_count": len(ordered),
                         "dt_collection_count": len(dt_ids),
                         "dt_collection_ids": dt_ids,
                         "core_types": sorted({c["core"]["type"] for c in ordered
                                               if c["core"]["type"]})})
