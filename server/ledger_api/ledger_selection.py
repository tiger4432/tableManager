"""Resolve typed UI markings to ledger-backed final CHIP evidence and comparisons."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from urllib.parse import quote

from ledger_api import finding_kinds
from ledger_api import ledger_siblings
from ledger_api import ledger_identity
from ledger_api import ledger_trends
from ledger_trace import _fetch, relation_exists


def _is_declared(predicate):
    """Whether the DECLARATION emits this predicate. The declaration is the only authority.

    🔴 THIS KEEPS A DISTINCTION, not a lookup: 「declared and nothing was measured」 and
    「nobody declared it」 are different answers, and the caller prints them differently.
    Read from the live declaration rather than a code-held word list -- the list was the
    v1 layer, and it went stale the day a predicate was declared without editing it.
    """
    try:
        from ledger import config as _config
        declared = (_config.load() or {}).get("vocabulary") or {}
    except Exception:      # an unreadable declaration is not a statement that nothing is declared
        return False
    return str(predicate) in {str(key).split("@", 1)[0] for key in declared}

#: The aggregation unit here is the SAME unit the trend grain declares, so its subject
#: type is read from that declaration rather than restated. A literal in this file was
#: exactly what went dark when the ledger's type names became lowercase.
_AGGREGATION_SUBJECT_TYPE = ledger_trends.DEFAULT_GRAIN["subject_type"]


LEDGER_RELATION = "ledger_events"
DEFAULT_WINDOW = "365d"
MAX_WINDOW_DAYS = 730
MAX_SELECTIONS = 200  # request budget, never a domain-cardinality claim
MAP_TABLES = {
    "bonding_log": {"map": ("bond_lot", "bond_slot"), "xy": ("bond_x", "bond_y"),
                    "wafer": "base_id"},
    "dt_map": {"map": ("dt_lot", "dt_slot"), "xy": ("dt_x", "dt_y"),
               "wafer": "core_wafer"},
    "core_wafer_map": {"map": ("core_lot", "core_slot"),
                       "xy": ("core_x", "core_y"), "wafer": "wafer_id"},
}


class SelectionRequestError(ValueError):
    def __init__(self, detail):
        super().__init__(detail.get("message") or detail.get("reason"))
        self.detail = detail


def _window(text, now):
    parsed = ledger_siblings.parse_window(text or DEFAULT_WINDOW, now=now)
    if parsed.start is None or parsed.end is None:
        raise SelectionRequestError({"reason": "selection_window_required",
                                     "message": "selection 해소에는 유계 기간이 필요하다"})
    if (parsed.end - parsed.start).total_seconds() > MAX_WINDOW_DAYS * 86400:
        raise SelectionRequestError({"reason": "selection_window_too_wide",
                                     "maximum_days": MAX_WINDOW_DAYS,
                                     "message": f"selection 기간은 최대 {MAX_WINDOW_DAYS}일이다"})
    return parsed


def _identity_unit(identity):
    identity = identity or {}
    identity_type = identity.get("type")
    keys = identity.get("keys") or {}
    context = identity.get("context") or {}
    wafer, bonding_leg = keys.get("wafer"), context.get("bonding_leg")
    mark = identity.get("mark_key")
    if mark and str(mark).startswith(ledger_identity.MARK_PREFIX):
        try:
            decoded = ledger_identity.decode_mark(mark)
        except ledger_identity.AnalysisIdentityError as exc:
            raise SelectionRequestError({"reason": "bad_analysis_mark",
                                         "message": str(exc)}) from exc
        if wafer and (str(wafer), str(bonding_leg)) != (
                decoded["wafer"], decoded["bonding_leg"]):
            raise SelectionRequestError({"reason": "mark_identity_conflict",
                                         "message": "mark_key와 Wafer 실험 문맥이 서로 다르다"})
        wafer, bonding_leg = decoded["wafer"], decoded["bonding_leg"]
    if identity_type not in (None, "Wafer", "wafer"):
        return None, False
    if wafer and bonding_leg and mark and mark != ledger_identity.encode_mark(
            str(wafer), str(bonding_leg)):
        raise SelectionRequestError({"reason": "mark_identity_conflict",
                                     "message": "mark_key와 Wafer 실험 문맥이 서로 다르다"})
    if wafer and bonding_leg:
        return (str(wafer), str(bonding_leg)), False
    return None, bool(wafer)


def _normalize(payload):
    raw = payload.get("selection", payload.get("marks"))
    if not isinstance(raw, list) or not raw:
        raise SelectionRequestError({"reason": "selection_required",
                                     "message": "selection 배열이 필요하다"})
    if len(raw) > MAX_SELECTIONS:
        raise SelectionRequestError({"reason": "too_many_selections",
                                     "maximum": MAX_SELECTIONS,
                                     "message": "한 요청의 selection 표시 예산을 넘었다"})
    out = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SelectionRequestError({"reason": "bad_selection_item", "index": index,
                                         "message": "selection 항목은 객체여야 한다"})
        kind = item.get("kind")
        selector = item.get("selector") or {}
        identity = item.get("identity") or selector.get("identity")
        subject_type = item.get("subjectType") or item.get("subject_type")
        if subject_type not in (None, "Wafer", "wafer"):
            raise SelectionRequestError({"reason": "unsupported_subject_type",
                                         "index": index, "subject_type": subject_type,
                                         "message": "selection resolver는 Wafer 주어와 본딩 실험 문맥을 받는다"})
        units, legacy = set(), False
        for stable_id in selector.get("ids") or []:
            if isinstance(stable_id, str) and stable_id.startswith(ledger_identity.MARK_PREFIX):
                try:
                    decoded = ledger_identity.decode_mark(stable_id)
                except ledger_identity.AnalysisIdentityError as exc:
                    raise SelectionRequestError({"reason": "bad_analysis_mark",
                                                 "index": index,
                                                 "message": str(exc)}) from exc
                units.add((decoded["wafer"], decoded["bonding_leg"]))
            elif isinstance(stable_id, str) and stable_id.startswith("wafer:"):
                legacy = True
        if kind == "entity_set":
            subjects = selector.get("subjects") or item.get("subjects") or []
            if identity and not subjects:
                subjects = [identity]
            for subject in subjects:
                unit, old = _identity_unit(subject)
                legacy = legacy or old
                if unit:
                    units.add(unit)
            identity = subjects[0] if len(subjects) == 1 else None
        if kind == "map_cells":
            subjects = selector.get("subjects") or []
            identity = identity or (subjects[0] if len(subjects) == 1 else None)
        unit, old = _identity_unit(identity)
        legacy = legacy or old
        if kind in ("map_cells", "map_die"):
            units.clear()  # ids are claims to re-check, never substitutes for map evidence
        elif unit:
            units.add(unit)
        frame = item.get("frame") or selector.get("frame") or {}
        out.append({
            "selection_id": str(item.get("id") or item.get("mark_id") or
                                item.get("selection_id") or
                                f"selection:{index}"),
            "group_id": str(item.get("groupId") or item.get("group_id") or
                            item.get("group") or "ungrouped"),
            "kind": kind, "unit": unit, "units": units, "legacy_wafer": legacy,
            "input": item,
            "map_focus": ({"map_id": item.get("map_id") or selector.get("map_id"),
                           "table": frame.get("table") or selector.get("table"),
                           "stage": frame.get("stage") or item.get("stage") or
                                    selector.get("stage"),
                           "cells": selector.get("cells") or
                                    ([{"x": item.get("x"), "y": item.get("y")}]
                                     if kind == "map_die" else [])}
                          if kind in ("map_die", "map_cells") else None),
        })
    return out


def _map_sql(table):
    spec = MAP_TABLES[table]
    lot, slot = spec["map"]
    x_col, y_col = spec["xy"]
    wafer = spec["wafer"]
    material = {
        "bonding_log": "'DT', t.dt_lot, t.dt_slot",
        "dt_map": "'Wafer', t.core_wafer, NULL::text",
        "core_wafer_map": "'Wafer', t.wafer_id, NULL::text",
    }[table]
    leg_select = "NULL::text"
    leg_join = ""
    if table == "bonding_log":
        leg_select = "NULLIF(bm.leg::text, '')"
        leg_join = ("JOIN bonding_map bm ON bm.base = t.base_id "
                    "AND bm.x = t.bx AND bm.y = t.by")
    # Every identifier is selected from MAP_TABLES above, never request text.
    return f"""
WITH requested AS (
    SELECT * FROM jsonb_to_recordset(%(requests)s::jsonb)
      AS r(selection_id text, map_id text, x numeric, y numeric)
)
SELECT r.selection_id, NULLIF(t.{wafer}, ''), {leg_select},
       r.map_id, r.x, r.y, {material}
FROM requested r
JOIN wafer_map_metadata m
  ON m.target_table = %(table)s AND m.map_id = r.map_id
JOIN {table} t
  ON concat_ws('_', t.{lot}, t.{slot}) = r.map_id
 AND t.{x_col} = r.x AND t.{y_col} = r.y
{leg_join}
ORDER BY r.selection_id, t.{wafer} NULLS LAST
"""


def _resolve_map_wafers(connection, selections):
    requests_by_table = defaultdict(list)
    invalid = {}
    for selection in selections:
        if selection["kind"] not in ("map_die", "map_cells"):
            continue
        focus = selection["map_focus"] or {}
        table, map_id = focus.get("table"), focus.get("map_id")
        cells = focus.get("cells") or []
        if table not in MAP_TABLES:
            invalid[selection["selection_id"]] = "map_frame_table_absent_or_unknown"
            continue
        if not map_id or not cells:
            invalid[selection["selection_id"]] = "map_address_incomplete"
            continue
        for cell in cells:
            if cell.get("x") is None or cell.get("y") is None:
                invalid[selection["selection_id"]] = "map_address_incomplete"
                continue
            requests_by_table[table].append({"selection_id": selection["selection_id"],
                                             "map_id": map_id, "x": cell["x"],
                                             "y": cell["y"]})
    resolved = defaultdict(lambda: {"units": set(), "evidence": set(),
                                    "materials": set()})
    for table, requests in requests_by_table.items():
        rows = _fetch(connection, _map_sql(table),
                      {"requests": json.dumps(requests, separators=(",", ":")),
                       "table": table})
        for (selection_id, wafer, bonding_leg, map_id, x, y, material_type, material_a,
             material_b) in rows:
            evidence_id = f"source:{table}:{map_id}:{x}:{y}"
            resolved[str(selection_id)]["evidence"].add(evidence_id)
            if wafer and bonding_leg:
                resolved[str(selection_id)]["units"].add((str(wafer), str(bonding_leg)))
            if material_a:
                material_id = (f"material:{material_type}:{quote(str(material_a), safe='')}" +
                               (f":{quote(str(material_b), safe='')}"
                                if material_b is not None else ""))
                resolved[str(selection_id)]["materials"].add(material_id)
    return resolved, invalid


def _candidate_sql():
    return """
WITH marks AS (
  SELECT * FROM jsonb_to_recordset(%(units)s::jsonb)
    AS m(wafer text, bonding_leg text)
), assignments AS (
  SELECT m.wafer, m.bonding_leg, a.id AS assignment_claim_id
  FROM marks m
  JOIN ledger_events a
    ON a.subject_type = 'Wafer'
   AND a.subject_keys->>'wafer' = m.wafer
   AND a.predicate = 'assigned_to_experiment'
   AND a.object_payload->>'experiment_type' = 'bonding_leg'
   AND a.object_payload->>'unit_id' = m.bonding_leg
   AND a.occurred_at >= %(from)s AND a.occurred_at < %(to)s
)
SELECT m.wafer, m.bonding_leg, e.id, e.subject_keys->>'wafer',
       e.object_payload->'component'->>'final_chip_id',
       e.object_payload->'component'->>'component_id', m.assignment_claim_id
FROM assignments m
JOIN ledger_events e
  ON e.predicate = 'transferred'
 AND e.occurred_at >= %(from)s AND e.occurred_at < %(to)s
 AND e.object_payload->'to'->>'type' = 'bond_layer'
 AND e.object_payload->'to'->'keys'->>'base_wafer_id' = m.wafer
 AND e.object_payload->'to'->'keys'->>'bonding_leg' = m.bonding_leg
WHERE NULLIF(e.object_payload->'component'->>'final_chip_id', '') IS NOT NULL
ORDER BY m.wafer, m.bonding_leg, e.occurred_at, e.id
"""


def _paths_sql():
    return """
SELECT id, subject_keys->>'wafer', object_payload, occurred_at, source_raw_ref
FROM ledger_events
WHERE predicate = 'transferred'
  AND occurred_at >= %(from)s AND occurred_at < %(to)s
  AND object_payload->'component'->>'final_chip_id' = ANY(%(chips)s)
ORDER BY object_payload->'component'->>'final_chip_id',
         object_payload->'component'->>'component_id',
         (object_payload->>'sequence')::integer, occurred_at, id
"""


def _process_sql():
    """Component-grain process evidence on Core Wafer subjects.

    Base-Wafer bonding claims use the same ontology subject type but carry an explicit
    ``bonding_leg`` experiment context in the value payload.  Excluding that context here
    prevents a component population from double-counting experiment-unit evidence.
    """
    return """
SELECT id, subject_keys->>'wafer', object_payload, occurred_at, source_raw_ref
FROM ledger_events
WHERE predicate = 'processed_with'
  AND subject_type = 'Wafer'
  AND NOT (object_payload ? 'bonding_leg')
  AND occurred_at >= %(from)s AND occurred_at < %(to)s
  AND subject_keys->>'wafer' = ANY(%(wafers)s)
ORDER BY subject_keys->>'wafer', occurred_at, id
"""


def _analysis_process_sql():
    return """
WITH units AS (
  SELECT * FROM jsonb_to_recordset(%(units)s::jsonb)
    AS u(wafer text, bonding_leg text)
)
SELECT e.id, e.subject_keys->>'wafer', e.object_payload->>'bonding_leg',
       e.object_payload, e.occurred_at, e.source_raw_ref
FROM units u JOIN ledger_events e
  ON e.subject_type = 'Wafer' AND e.predicate = 'processed_with'
 AND e.subject_keys->>'wafer' = u.wafer
 AND e.object_payload->>'bonding_leg' = u.bonding_leg
 AND e.occurred_at >= %(from)s AND e.occurred_at < %(to)s
ORDER BY e.subject_keys->>'wafer', e.object_payload->>'bonding_leg', e.occurred_at, e.id
"""


def _measurement_sql():
    return """
SELECT id, subject_keys->>'wafer', object_payload, occurred_at, source_raw_ref
FROM ledger_events
WHERE predicate = 'measured'
  AND subject_type = 'Wafer'
  AND NOT (object_payload ? 'bonding_leg')
  AND occurred_at >= %(from)s AND occurred_at < %(to)s
  AND subject_keys->>'wafer' = ANY(%(wafers)s)
ORDER BY subject_keys->>'wafer', occurred_at, id
"""


def _analysis_measurement_sql():
    return """
WITH units AS (
  SELECT * FROM jsonb_to_recordset(%(units)s::jsonb)
    AS u(wafer text, bonding_leg text)
)
SELECT e.id, e.subject_keys->>'wafer', e.object_payload->>'bonding_leg',
       e.object_payload, e.occurred_at, e.source_raw_ref
FROM units u JOIN ledger_events e
  ON e.subject_type = 'Wafer' AND e.predicate = 'measured'
 AND e.subject_keys->>'wafer' = u.wafer
 AND e.object_payload->>'bonding_leg' = u.bonding_leg
 AND e.occurred_at >= %(from)s AND e.occurred_at < %(to)s
ORDER BY e.subject_keys->>'wafer', e.object_payload->>'bonding_leg',
         e.occurred_at, e.id
"""


def _bond_maps_sql():
    return """
WITH units AS (
  SELECT * FROM jsonb_to_recordset(%(units)s::jsonb)
    AS u(wafer text, bonding_leg text)
)
SELECT DISTINCT b.base_id, bm.leg::text, concat_ws('_', b.bond_lot, b.bond_slot),
       CASE WHEN dt_lot IS NOT NULL AND dt_slot IS NOT NULL
            THEN concat_ws('_', dt_lot, dt_slot) END,
       CASE WHEN core_lot IS NOT NULL AND core_slot IS NOT NULL
            THEN concat_ws('_', core_lot, core_slot) END
FROM units u
JOIN bonding_log b ON b.base_id = u.wafer
JOIN bonding_map bm ON bm.base = b.base_id AND bm.x = b.bx AND bm.y = b.by
                   AND bm.leg::text = u.bonding_leg
WHERE b.bond_lot IS NOT NULL AND b.bond_slot IS NOT NULL
ORDER BY b.base_id, bm.leg::text, concat_ws('_', b.bond_lot, b.bond_slot), 4, 5
"""


def _map_metadata_sql():
    return """
WITH requested AS (
    SELECT * FROM jsonb_to_recordset(%(requests)s::jsonb)
      AS r(stage text, table_name text, map_id text, component_id text,
           subject_wafer text, subject_leg text, selection_id text)
)
SELECT r.stage, r.table_name, r.map_id, r.component_id, r.subject_wafer,
       r.subject_leg,
       r.selection_id, m.grid_metadata
FROM requested r
JOIN wafer_map_metadata m ON m.target_table = r.table_name AND m.map_id = r.map_id
ORDER BY r.stage, r.map_id, r.component_id
"""


def _map_cells_sql(table):
    spec = MAP_TABLES[table]
    lot, slot = spec["map"]
    x_col, y_col = spec["xy"]
    bin_col = "b_bn" if table == "bonding_log" else "c_bn"
    material = {
        "bonding_log": "'DT', t.dt_lot, t.dt_slot",
        "dt_map": "'Wafer', t.core_wafer, NULL::text",
        "core_wafer_map": "'Wafer', t.wafer_id, NULL::text",
    }[table]
    return f"""
WITH requested AS (SELECT unnest(%(map_ids)s::text[]) AS map_id)
SELECT r.map_id, t.{x_col}, t.{y_col}, t.{bin_col}, {material}
FROM requested r JOIN {table} t
  ON concat_ws('_', t.{lot}, t.{slot}) = r.map_id
ORDER BY r.map_id, t.{x_col}, t.{y_col}
"""


def _valid_die_sql():
    return """
WITH requested AS (SELECT unnest(%(map_ids)s::text[]) AS map_id)
SELECT r.map_id, v.x, v.y
FROM requested r JOIN valid_die_ref v
  ON concat_ws('_', v.product, v.type) = r.map_id
WHERE v.val IS DISTINCT FROM '0'
ORDER BY r.map_id, v.x, v.y
"""


def _void_map_cells_sql():
    return """
WITH units AS (
  SELECT * FROM jsonb_to_recordset(%(units)s::jsonb)
    AS u(wafer text, bonding_leg text)
), hits AS (
  SELECT DISTINCT b.base_id, bm.leg::text AS bonding_leg,
         b.bond_lot, b.bond_slot, b.bond_x, b.bond_y,
         b.dt_lot, b.dt_slot, b.dt_x, b.dt_y,
         b.core_lot, b.core_slot, b.cx, b.cy, v.run_uid
  FROM units u
  JOIN bonding_log b ON b.base_id = u.wafer
  JOIN bonding_map bm ON bm.base = b.base_id AND bm.x = b.bx AND bm.y = b.by
                     AND bm.leg::text = u.bonding_leg
  JOIN inspection_run r ON r.base_wafer_id = b.base_id
                       AND r.base_x = b.bx AND r.base_y = b.by
  JOIN void_obs v ON v.run_uid = r.run_uid
)
SELECT 'bonding_log', base_id, bonding_leg,
       concat_ws('_', bond_lot, bond_slot), bond_x, bond_y, run_uid
FROM hits
UNION ALL
SELECT 'dt_map', base_id, bonding_leg,
       concat_ws('_', dt_lot, dt_slot), dt_x, dt_y, run_uid
FROM hits WHERE dt_lot IS NOT NULL AND dt_slot IS NOT NULL
UNION ALL
SELECT 'core_wafer_map', base_id, bonding_leg,
       concat_ws('_', core_lot, core_slot), cx, cy, run_uid
FROM hits WHERE core_lot IS NOT NULL AND core_slot IS NOT NULL
ORDER BY 1, 2, 3, 4
"""


def _build_maps(connection, components, final_units, selected_focuses, finding_kind=None):
    refs = []
    seen = set()
    def add(stage, table, map_id, component_id=None, subject_wafer=None,
            subject_leg=None,
            selection_id=None):
        key = (stage, table, map_id, component_id, subject_wafer, subject_leg,
               selection_id)
        if table in MAP_TABLES and map_id and key not in seen:
            seen.add(key)
            refs.append({"stage": stage, "table_name": table, "map_id": map_id,
                         "component_id": component_id,
                         "subject_wafer": subject_wafer,
                         "subject_leg": subject_leg,
                         "selection_id": selection_id})

    for focus in selected_focuses:
        add(focus.get("stage") or "selected", focus.get("table"),
            focus.get("map_id"), selection_id=focus.get("selection_id"))
    if final_units:
        unit_rows = [{"wafer": wafer, "bonding_leg": leg}
                     for wafer, leg in sorted(final_units)]
        for _wafer, _leg, bond_map, dt_map, core_map in _fetch(
                connection, _bond_maps_sql(),
                {"units": json.dumps(unit_rows, separators=(",", ":"))}):
            add("bond", "bonding_log", bond_map, subject_wafer=_wafer,
                subject_leg=_leg)
            add("dt", "dt_map", dt_map, subject_wafer=_wafer,
                subject_leg=_leg)
            add("core", "core_wafer_map", core_map, subject_wafer=_wafer,
                subject_leg=_leg)
    for row in components.values():
        for dt in row["dt_collections"]:
            keys = dt.get("keys") or {}
            if keys.get("dt_lot") and keys.get("dt_slot"):
                add("dt", "dt_map", f"{keys['dt_lot']}_{keys['dt_slot']}",
                    row["component_id"])
        core = row["core"]
        if core.get("lot") and core.get("slot"):
            add("core", "core_wafer_map", f"{core['lot']}_{core['slot']}",
                row["component_id"])
    if not refs:
        return []
    meta_rows = _fetch(connection, _map_metadata_sql(),
                       {"requests": json.dumps(refs, separators=(",", ":"))})
    maps = []
    valid_refs = set()
    for (stage, table, map_id, component_id, subject_wafer, subject_leg, selection_id,
         raw_meta) in meta_rows:
        meta = raw_meta if isinstance(raw_meta, dict) else json.loads(raw_meta or "{}")
        valid_ref = meta.get("valid_die_ref") or {}
        if valid_ref.get("map_id"):
            valid_refs.add(valid_ref["map_id"])
        subject_identity = (ledger_identity.identity(
            subject_wafer, subject_leg, _AGGREGATION_SUBJECT_TYPE)
                            if subject_wafer and subject_leg else None)
        scope_id = (subject_identity["mark_key"] if subject_identity else
                    component_id or selection_id)
        maps.append({"id": f"map:{table}:{map_id}" +
                           (f":{quote(scope_id, safe='')}" if scope_id else ""),
                     "label": map_id,
                     "stage": stage, "component_id": component_id,
                     "subject_wafer": subject_wafer,
                     "subject_leg": subject_leg,
                     "subject_identity": subject_identity,
                     "wafer_mark_key": (subject_identity["mark_key"]
                                        if subject_identity else None),
                     "selection_id": selection_id,
                     "frame": {"table": table, "mapId": map_id,
                               "coordinate_system": {
                                   "unit": "cells_from_origin",
                                   "start_x": meta.get("grid_start_x"),
                                   "start_y": meta.get("grid_start_y"),
                                   "y_invert": meta.get("grid_y_invert"),
                                   "rotation": meta.get("rotation"),
                                   "side": meta.get("side")}},
                     "meta": meta,
                     "layers": {"valid_die": {"state": "absent", "cells": []},
                                "process_area": {"state": "ready", "cells": []},
                                "used_area": {"state": "ready", "cells": []},
                                "supply_material": {"state": "ready", "cells": []},
                                "defect": {"state": "absent",
                                           "reason": "finding_to_map_layer_not_declared",
                                           "cells": []}}})
    cells_by_map = defaultdict(list)
    by_table = defaultdict(set)
    for row in maps:
        by_table[row["frame"]["table"]].add(row["frame"]["mapId"])
    for table, map_ids in by_table.items():
        for map_id, x, y, value, material_type, material_a, material_b in _fetch(
                connection, _map_cells_sql(table), {"map_ids": sorted(map_ids)}):
            material_id = None
            if material_a:
                material_id = (f"material:{material_type}:{quote(str(material_a), safe='')}" +
                               (f":{quote(str(material_b), safe='')}"
                                if material_b is not None else ""))
            cells_by_map[(table, map_id)].append({"x": x, "y": y, "value": value,
                                                  "material_id": material_id})
    valid_cells = defaultdict(list)
    if valid_refs:
        for map_id, x, y in _fetch(connection, _valid_die_sql(),
                                   {"map_ids": sorted(valid_refs)}):
            valid_cells[map_id].append({"x": x, "y": y})
    defect_cells = defaultdict(list)
    if finding_kind == "void" and final_units:
        unit_rows = [{"wafer": wafer, "bonding_leg": leg}
                     for wafer, leg in sorted(final_units)]
        for table, wafer, leg, map_id, x, y, run_uid in _fetch(
                connection, _void_map_cells_sql(),
                {"units": json.dumps(unit_rows, separators=(",", ":"))}):
            defect_cells[(table, map_id, wafer, leg)].append({
                "x": x, "y": y, "evidence_id": f"source:void_obs:{run_uid}"})
    for row in maps:
        cells = cells_by_map[(row["frame"]["table"], row["frame"]["mapId"])]
        row["layers"]["process_area"]["cells"] = cells
        row["layers"]["used_area"]["cells"] = [{"x": c["x"], "y": c["y"]}
                                                   for c in cells]
        supply = [{"x": c["x"], "y": c["y"], "material_id": c["material_id"]}
                  for c in cells if c["material_id"]]
        row["layers"]["supply_material"] = {
            "state": "ready" if supply else "absent", "cells": supply,
            **({"reason": "material_identity_absent"} if not supply else {})}
        ref = row["meta"].get("valid_die_ref") or {}
        if ref.get("map_id") in valid_cells:
            row["layers"]["valid_die"] = {"state": "ready",
                                            "cells": valid_cells[ref["map_id"]],
                                            "ref": ref}
        defects = defect_cells[(row["frame"]["table"], row["frame"]["mapId"],
                                row.get("subject_wafer"), row.get("subject_leg"))]
        if defects:
            row["layers"]["defect"] = {"state": "ready", "cells": defects,
                                         "finding_kind": finding_kind}
    return maps


def _json_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _traceability(paths):
    total = len(paths)
    core = [row for row in paths if row.get("core", {}).get("wafer")]
    dt = [row for row in paths if row.get("dt_collections")]
    def item(rows):
        count = len(rows)
        return {"state": "absent" if not count else "ready" if count == total else "partial",
                "count": count, "component_denominator": total,
                "evidence_ids": sorted({e for row in rows
                                         for e in row.get("evidence_ids") or []})}
    return {"dt": item(dt), "core": item(core)}


def _entropy(parts):
    total = sum(parts)
    if not total:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in parts if n)


def _information_gain(a_hit, a_total, b_hit, b_total):
    total = a_total + b_total
    if not total:
        return None
    before = _entropy((a_total, b_total))
    hit = a_hit + b_hit
    miss = total - hit
    after = 0.0
    if hit:
        after += hit / total * _entropy((a_hit, b_hit))
    if miss:
        after += miss / total * _entropy((a_total - a_hit, b_total - b_hit))
    return round(before - after, 6)


def resolve(connection, payload, now=None, relation=LEDGER_RELATION):
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, dict):
        raise SelectionRequestError({"reason": "bad_selection_body",
                                     "message": "JSON 객체가 필요하다"})
    selections = _normalize(payload)
    window = _window(payload.get("window"), now)
    for selection in selections:
        if selection["kind"] != "time_range":
            continue
        source = selection["input"].get("interval") or \
                 (selection["input"].get("selector") or {}).get("interval") or \
                 selection["input"].get("selector") or {}
        start, end = source.get("from"), source.get("to")
        if not start or not end:
            raise SelectionRequestError({"reason": "bad_time_range",
                                         "selection_id": selection["selection_id"],
                                         "message": "time_range는 from/to가 필요하다"})
        narrowed = ledger_siblings.parse_window(f"{start}..{end}", now=now)
        if narrowed.start is None or narrowed.end is None:
            raise SelectionRequestError({"reason": "bad_time_range",
                                         "selection_id": selection["selection_id"],
                                         "message": "time_range를 해석할 수 없다"})
        window.start, window.end = max(window.start, narrowed.start), min(window.end,
                                                                    narrowed.end)
    if window.start >= window.end:
        raise SelectionRequestError({"reason": "empty_time_intersection",
                                     "message": "time_range 교집합이 비었다"})
    base = {"schema_version": 5, "generated_at": now.isoformat(),
            "window": {"requested": payload.get("window"), "applied": window.as_dict()},
            "cardinality": {"selections": "variable", "final_chips": "variable",
                            "paths": "variable", "facets": "variable"}}
    if not relation_exists(connection, relation):
        return {**base, "state": "absent", "selections": [],
                "resolved_final_chip_ids": [], "comparison": _empty_comparison("ledger_absent")}

    map_resolution, invalid_maps = _resolve_map_wafers(connection, selections)
    units_by_selection = {s["selection_id"]: set(s["units"])
                          for s in selections}
    for selection_id, resolution in map_resolution.items():
        units_by_selection[selection_id].update(resolution["units"])
    units = sorted({unit for values in units_by_selection.values() for unit in values})
    params = {"from": window.start, "to": window.end,
              "units": json.dumps([{"wafer": wafer, "bonding_leg": leg}
                                    for wafer, leg in units], separators=(",", ":"))}
    candidate_rows = _fetch(connection, _candidate_sql(), params) if units else []
    direct = defaultdict(lambda: {"chips": set(), "evidence": set()})
    for (mark_wafer, mark_leg, atom_id, _core_wafer, chip, _component,
         assignment_claim_id) in candidate_rows:
        direct[(str(mark_wafer), str(mark_leg))]["chips"].add(str(chip))
        direct[(str(mark_wafer), str(mark_leg))]["evidence"].add(f"evidence:{atom_id}")
        direct[(str(mark_wafer), str(mark_leg))]["evidence"].add(
            f"evidence:{assignment_claim_id}")
    chips = sorted({chip for answer in direct.values() for chip in answer["chips"]})
    path_rows = _fetch(connection, _paths_sql(), {**params, "chips": chips}) if chips else []

    components = {}
    for atom_id, core_wafer, body, occurred_at, raw_ref in path_rows:
        body, meta = body or {}, (body or {}).get("component") or {}
        chip, component_id = meta.get("final_chip_id"), meta.get("component_id")
        if not chip or not component_id:
            continue
        key = (str(chip), str(component_id))
        row = components.setdefault(key, {
            "path_id": f"component:{component_id}", "final_chip_id": str(chip),
            "component_id": str(component_id),
            "core": {"wafer": core_wafer, "lot": meta.get("core_lot"),
                     "slot": meta.get("core_slot"), "type": meta.get("core_type"),
                     "branch": meta.get("core_branch"), "role": meta.get("role")},
            "bond": {"layer": meta.get("bond_layer"),
                     "position": meta.get("bond_position"), "final_wafer": None,
                     "bonding_leg": meta.get("bonding_leg")},
            "dt_collections": [], "evidence_ids": [], "transfer_steps": 0,
            "sequence": {"first": None, "last": None},
        })
        evidence_id = f"evidence:{atom_id}"
        row["evidence_ids"].append(evidence_id)
        row["transfer_steps"] += 1
        sequence = body.get("sequence")
        if sequence is not None:
            row["sequence"]["first"] = sequence if row["sequence"]["first"] is None else min(row["sequence"]["first"], sequence)
            row["sequence"]["last"] = sequence if row["sequence"]["last"] is None else max(row["sequence"]["last"], sequence)
        for place in (body.get("from") or {}, body.get("to") or {}):
            if place.get("type") == "dt_slot":
                dt = {"keys": place.get("keys") or {}, "position": place.get("position")}
                if dt not in row["dt_collections"]:
                    row["dt_collections"].append(dt)
            if place.get("type") == "bond_layer":
                keys = place.get("keys") or {}
                row["bond"]["final_wafer"] = keys.get("base_wafer_id")
                row["bond"]["bonding_leg"] = keys.get("bonding_leg")

    core_wafers = sorted({row["core"]["wafer"] for row in components.values()
                          if row["core"]["wafer"]})
    process_rows = (_fetch(connection, _process_sql(), {**params, "wafers": core_wafers})
                    if core_wafers else [])
    process_by_wafer = defaultdict(list)
    for atom_id, wafer, body, occurred_at, raw_ref in process_rows:
        process_by_wafer[str(wafer)].append({"evidence_id": f"evidence:{atom_id}",
                                             "subject_grain": "component",
                                             "payload": body or {},
                                             "occurred_at": occurred_at.isoformat(),
                                             "source_raw_ref": raw_ref})
    analysis_process_rows = (_fetch(connection, _analysis_process_sql(), params)
                             if units else [])
    for atom_id, wafer, bonding_leg, body, occurred_at, raw_ref in analysis_process_rows:
        process_by_wafer[(str(wafer), str(bonding_leg))].append({
            "evidence_id": f"evidence:{atom_id}",
            "subject_grain": "bonding_experiment_unit",
            "subject_key": {"wafer": str(wafer), "bonding_leg": str(bonding_leg)},
            "payload": body or {},
            "occurred_at": occurred_at.isoformat(), "source_raw_ref": raw_ref})

    measurement_by_subject = defaultdict(list)
    measurement_rows = (_fetch(connection, _measurement_sql(),
                               {**params, "wafers": core_wafers})
                        if core_wafers else [])
    for atom_id, wafer, body, occurred_at, raw_ref in measurement_rows:
        measurement_by_subject[str(wafer)].append({
            "evidence_id": f"evidence:{atom_id}", "payload": body or {},
            "occurred_at": occurred_at.isoformat(), "source_raw_ref": raw_ref})
    analysis_measurement_rows = (_fetch(connection, _analysis_measurement_sql(), params)
                                 if units else [])
    for atom_id, wafer, bonding_leg, body, occurred_at, raw_ref in analysis_measurement_rows:
        measurement_by_subject[(str(wafer), str(bonding_leg))].append({
            "evidence_id": f"evidence:{atom_id}", "payload": body or {},
            "occurred_at": occurred_at.isoformat(), "source_raw_ref": raw_ref})

    final_units = {(row["bond"]["final_wafer"], row["bond"]["bonding_leg"])
                   for row in components.values()
                   if row["bond"].get("final_wafer") and
                   row["bond"].get("bonding_leg")}
    selected_focuses = [{**s["map_focus"], "selection_id": s["selection_id"]}
                        for s in selections if s["map_focus"]]
    maps = _build_maps(connection, components, final_units, selected_focuses,
                       finding_kinds.payload_field(payload, "finding_kind"))

    answers = []
    for selection in selections:
        selected_units = units_by_selection[selection["selection_id"]]
        final_chip_set, direct_evidence = set(), set()
        for unit in selected_units:
            final_chip_set.update(direct[unit]["chips"])
            direct_evidence.update(direct[unit]["evidence"])
        map_evidence = map_resolution[selection["selection_id"]]["evidence"]
        final_chips = sorted(final_chip_set)
        if selection["kind"] in ("time_range",):
            state, reason = "resolved", None
        elif selection["kind"] in ("map_die", "map_cells"):
            reason = invalid_maps.get(selection["selection_id"])
            if reason:
                state, final_chips = "unresolvable", []
            elif not map_evidence:
                state, reason = "unresolvable", "map_cell_not_found"
            elif not selected_units:
                state, reason = "unresolvable", "map_cell_experiment_unit_absent"
            else:
                state = ("resolved" if len(final_chips) == 1 else
                         "candidate" if final_chips else "unresolvable")
                reason = None if final_chips else "no_transfer_evidence"
        elif not selected_units:
            state, reason = "unresolvable", (
                "wafer_mark_requires_experiment_unit" if selection["legacy_wafer"] else
                "map_die_bridge_absent" if selection["map_focus"] else
                "bonding_experiment_context_absent")
        else:
            state = "resolved" if len(final_chips) == 1 else "candidate" if final_chips else "unresolvable"
            reason = None if final_chips else "no_transfer_evidence"
        paths = [row for (chip, _component), row in components.items() if chip in final_chips]
        answers.append({"selection_id": selection["selection_id"],
                        "mark_id": selection["selection_id"],
                        "markId": selection["selection_id"],
                        "group_id": selection["group_id"], "input": selection["input"],
                        "groupId": selection["group_id"],
                        "state": state, "reason": reason,
                        "resolved_subjects": [{"type": "FinalChip",
                                               "keys": {"final_chip_id": chip}}
                                              for chip in final_chips],
                        "subjects": [{"type": "FinalChip", "id": chip}
                                     for chip in final_chips],
                        "aggregation_units": [
                            ledger_identity.identity(wafer, leg,
                                                     _AGGREGATION_SUBJECT_TYPE)
                            for wafer, leg in sorted(selected_units)],
                        "final_chip_ids": final_chips,
                        "wafer_mark_keys": sorted(ledger_identity.encode_mark(wafer, leg)
                                                  for wafer, leg in selected_units),
                        "evidence_ids": sorted(direct_evidence | map_evidence),
                        "evidenceIds": sorted(direct_evidence | map_evidence),
                        "path": (["Wafer", "ExperimentAssignmentClaim", "Bond",
                                  "DT", "Core", "FinalChip"]
                                 if final_chips else []),
                        "material_ids": sorted(
                            map_resolution[selection["selection_id"]]["materials"]),
                        "paths": paths,
                        "traceability": _traceability(paths),
                        "maps": [row for row in maps
                                 if (row.get("selection_id") == selection["selection_id"] or
                                     any(row.get("subject_wafer") == wafer and
                                         row.get("subject_leg") == leg
                                         for wafer, leg in selected_units) or
                                     any(p["component_id"] == row["component_id"]
                                         for p in paths))],
                        **({"map_focus": selection["map_focus"]}
                           if selection["map_focus"] else {})})

    comparison = _comparison(answers, components, process_by_wafer,
                             finding_kinds.payload_field(payload, "finding_kind"),
                             measurement_by_subject=measurement_by_subject)
    top_maps = {}
    for answer in answers:
        for row in answer["maps"]:
            current = top_maps.setdefault(row["id"], {**row, "component_ids": []})
            if row.get("component_id") and row["component_id"] not in current["component_ids"]:
                current["component_ids"].append(row["component_id"])
    return {**base, "schemaVersion": 5,
            "state": "ready" if answers else "empty", "selections": answers,
            "resolved_final_chip_ids": chips,
            "maps": list(top_maps.values()), "comparison": comparison}


def _empty_comparison(reason):
    return {"state": "absent", "reason": reason, "groups": [],
            "facets": {"process": [], "measurement": [], "context": []},
            "actions": []}


def _events_for_path(row, process_by_wafer):
    """Component-grain process only; experiment-context claims never cross-join."""
    core_events = process_by_wafer.get(row.get("core", {}).get("wafer"), [])
    return sorted(core_events,
                  key=lambda event: (event["occurred_at"], event["evidence_id"]))


def _unit_events(row, process_by_wafer):
    bond = row.get("bond") or {}
    return sorted(process_by_wafer.get((bond.get("final_wafer"),
                                        bond.get("bonding_leg")), []),
                  key=lambda event: (event["occurred_at"], event["evidence_id"]))


def _measurements_for_path(row, measurement_by_subject):
    """Component-grain metrology follows the exact Core Wafer subject."""
    return sorted(measurement_by_subject.get(row.get("core", {}).get("wafer"), []),
                  key=lambda event: (event["occurred_at"], event["evidence_id"]))


def _unit_measurements(row, measurement_by_subject):
    bond = row.get("bond") or {}
    return sorted(measurement_by_subject.get((bond.get("final_wafer"),
                                               bond.get("bonding_leg")), []),
                  key=lambda event: (event["occurred_at"], event["evidence_id"]))


def _comparison(answers, components, process_by_wafer, finding_kind,
                measurement_by_subject=None):
    measurement_by_subject = measurement_by_subject or {}
    group_components = defaultdict(dict)
    for answer in answers:
        for path in answer["paths"]:
            group_components[answer["group_id"]][(path["final_chip_id"],
                                                   path["component_id"])] = path
    group_ids = sorted(group_components)
    group_units = defaultdict(dict)
    for group_id, keyed in group_components.items():
        for row in keyed.values():
            bond = row.get("bond") or {}
            unit = (bond.get("final_wafer"), bond.get("bonding_leg"))
            if all(unit):
                group_units[group_id].setdefault(unit, row)

    groups = []
    for group_id in group_ids:
        rows = list(group_components[group_id].values())
        with_process = sum(bool(_events_for_path(r, process_by_wafer)) for r in rows)
        unit_rows = list(group_units[group_id].values())
        units_with_process = sum(bool(_unit_events(r, process_by_wafer)) for r in unit_rows)
        with_measurement = sum(bool(_measurements_for_path(r, measurement_by_subject))
                               for r in rows)
        units_with_measurement = sum(bool(_unit_measurements(r, measurement_by_subject))
                                     for r in unit_rows)
        measurement_total = len(rows) + len(unit_rows)
        measurement_evidence = with_measurement + units_with_measurement
        groups.append({"group_id": group_id, "component_count": len(rows),
                       "aggregation_unit_count": len(unit_rows),
                       "process_evidence": {"state": "complete" if rows and with_process == len(rows)
                                            else "partial" if with_process else "absent",
                                            "with_evidence": with_process,
                                            "missing": len(rows) - with_process},
                       "aggregation_unit_process_evidence": {
                           "state": "complete" if unit_rows and units_with_process == len(unit_rows)
                                    else "partial" if units_with_process else "absent",
                           "with_evidence": units_with_process,
                           "missing": len(unit_rows) - units_with_process},
                       "measurement": {
                           "state": ("complete" if measurement_total and
                                     measurement_evidence == measurement_total else
                                     "partial" if measurement_evidence else "absent"),
                           "with_evidence": measurement_evidence,
                           "missing": measurement_total - measurement_evidence}})

    context_counts = defaultdict(lambda: defaultdict(set))
    process_counts = defaultdict(lambda: defaultdict(set))
    unit_process_counts = defaultdict(lambda: defaultdict(set))
    context_evidence = defaultdict(lambda: defaultdict(set))
    process_facet_evidence = defaultdict(lambda: defaultdict(set))
    unit_process_facet_evidence = defaultdict(lambda: defaultdict(set))
    process_evidence = defaultdict(set)
    for group_id, keyed in group_components.items():
        for component_key, row in keyed.items():
            dimensions = {"core.type": row["core"].get("type"),
                          "core.branch": row["core"].get("branch"),
                          "core.lot": row["core"].get("lot"),
                          "bond.layer": row["bond"].get("layer"),
                          "transfer.steps": row.get("transfer_steps")}
            for field, value in dimensions.items():
                signature = _json_value({"field": field, "value": value})
                context_counts[group_id][signature].add(component_key)
                context_evidence[group_id][signature].update(row.get("evidence_ids") or [])
            occurrences = defaultdict(int)
            for event in _events_for_path(row, process_by_wafer):
                process_evidence[group_id].add(event["evidence_id"])
                payload = event["payload"]
                occurrence_key = _json_value({"step": payload.get("step"),
                                              "recipe": payload.get("recipe")})
                occurrences[occurrence_key] += 1
                signature = {"core_type": row["core"].get("type"),
                             "core_branch": row["core"].get("branch"),
                             "step": payload.get("step"),
                             "recipe": payload.get("recipe"),
                             "occurrence": occurrences[occurrence_key]}
                encoded = _json_value(signature)
                process_counts[group_id][encoded].add(component_key)
                process_facet_evidence[group_id][encoded].add(event["evidence_id"])

        for unit_key, row in group_units[group_id].items():
            unit_events = _unit_events(row, process_by_wafer)
            occurrences = defaultdict(int)
            for event in unit_events:
                process_evidence[group_id].add(event["evidence_id"])
                payload = event["payload"]
                occurrence_key = _json_value({"step": payload.get("step"),
                                              "recipe": payload.get("recipe")})
                occurrences[occurrence_key] += 1
                signature = {"subject_grain": "bonding_experiment_unit",
                             "step": payload.get("step"),
                             "recipe": payload.get("recipe"),
                             "occurrence": occurrences[occurrence_key]}
                encoded = _json_value(signature)
                unit_process_counts[group_id][encoded].add(unit_key)
                unit_process_facet_evidence[group_id][encoded].add(event["evidence_id"])

    process_coverage = {
        group["group_id"]: (group["process_evidence"]["with_evidence"] /
                            group["component_count"] if group["component_count"] else 0)
        for group in groups}
    unit_process_coverage = {
        group["group_id"]: (group["aggregation_unit_process_evidence"]["with_evidence"] /
                            group["aggregation_unit_count"] if group["aggregation_unit_count"] else 0)
        for group in groups}
    context = _facet_rows(context_counts, group_components, "context", finding_kind,
                          evidence_by_group=context_evidence)
    process = _facet_rows(process_counts, group_components, "process", finding_kind,
                          coverage_by_group=process_coverage,
                          evidence_by_group=process_facet_evidence,
                          population_kind="component")
    process += _facet_rows(unit_process_counts, group_units, "process", finding_kind,
                           coverage_by_group=unit_process_coverage,
                           evidence_by_group=unit_process_facet_evidence,
                           population_kind="bonding_experiment_unit")
    measurement = _measurement_facet_rows(
        group_components, measurement_by_subject, _measurements_for_path,
        population_kind="component")
    measurement += _measurement_facet_rows(
        group_units, measurement_by_subject, _unit_measurements,
        population_kind="bonding_experiment_unit")
    if not measurement:
        reason = ("measured_evidence_absent" if _is_declared("measured")
                  else "measured_predicate_not_declared")
        measurement = [{"state": "absent", "reason": reason,
                        "predicate": "measured", "wafer_mark_keys": [],
                        "evidence_ids": []}]
    actions = _actions(process, groups, finding_kind)
    physics_backed = [row for row in process
                      if row["surprise"]["binding_state"] in ("pass", "bias_candidate")
                      and row["surprise"]["score"] is not None]
    physics_backed.sort(key=lambda row: (-row["surprise"]["score"], row["facet_id"]))
    surprise = ({"state": "ready", "facet_id": physics_backed[0]["facet_id"],
                 "signature": physics_backed[0]["signature"],
                 **physics_backed[0]["surprise"]}
                if physics_backed else
                {"state": "unknown", "reason": "no_physics_backed_facet",
                 "score": None, "mechanism_model_id": None})
    return {"state": "ready" if group_ids else "absent", "groups": groups,
            "facets": {"process": process,
                       "measurement": measurement,
                       "context": context},
            "process": process, "measurement": measurement, "context": context,
            "surprise": surprise,
            "sequence": _sequence_comparison(group_components, process_by_wafer),
            "aggregation_unit_sequence": _experiment_unit_sequence(group_units,
                                                                     process_by_wafer),
            "evidence_ids": sorted({e for values in process_evidence.values() for e in values}),
            "actions": actions}


_MEASUREMENT_SIGNATURE_FIELDS = (
    "metric", "unit", "method", "step", "step_family", "eqp", "recipe", "stat",
    "frame", "die_x", "die_y", "inchip_x", "inchip_y", "structure", "conditions",
)
_MEASUREMENT_STATES = frozenset({"recorded", "missing", "not_performed", "unknown"})


def _measurement_signature(payload):
    """Identity of one comparable quantity; result/state/run evidence stay outside it."""
    return {field: payload[field] for field in _MEASUREMENT_SIGNATURE_FIELDS
            if field in payload and payload[field] is not None
            and not (isinstance(payload[field], str) and not payload[field].strip())}


def _measurement_state(events):
    if not events:
        return "missing"
    states = set()
    for event in events:
        payload = event["payload"]
        state = payload.get("state")
        if state not in _MEASUREMENT_STATES:
            state = "unknown"
        elif state == "recorded" and (
                "value" not in payload or payload.get("value") is None
                or not str(finding_kinds.payload_field(payload, "run_uid")
                           or "").strip()):
            state = "unknown"
        elif state != "recorded" and "value" in payload:
            state = "unknown"
        states.add(state)
    if len(states) != 1:
        return "contradiction"
    state = next(iter(states))
    if state == "recorded":
        values = {_json_value(event["payload"].get("value")) for event in events}
        if len(values) != 1:
            return "contradiction"
    return state


def _measurement_rollup(states):
    """Expose every non-recorded population state; exact counts remain in state_counts."""
    states = list(states)
    if states and all(state == "recorded" for state in states):
        return "recorded"
    for state in ("contradiction", "unknown", "not_performed", "missing"):
        if state in states:
            return state
    return "unknown"


def _measurement_facet_rows(group_populations, measurement_by_subject, event_selector,
                            population_kind):
    """Build value-preserving metrology comparisons without means, sentinels, or guesses."""
    records = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    signatures = {}
    for group_id, population in group_populations.items():
        for member_key, row in population.items():
            for event in event_selector(row, measurement_by_subject):
                signature = _measurement_signature(event["payload"])
                encoded = _json_value(signature)
                signatures[encoded] = signature
                records[group_id][encoded][member_key].append(event)
    if not signatures:
        return []

    rows = []
    for encoded in sorted(signatures):
        signature = signatures[encoded]
        observations = []
        for group_id in sorted(group_populations):
            population = group_populations[group_id]
            state_counts = defaultdict(int)
            evidence_ids = set()
            marks = set()
            values = {}
            recorded_members = set()
            member_states = []
            for member_key, row in population.items():
                events = records[group_id][encoded].get(member_key, [])
                member_state = _measurement_state(events)
                member_states.append(member_state)
                state_counts[member_state] += 1
                bond = row.get("bond") or {}
                if bond.get("final_wafer") and bond.get("bonding_leg"):
                    marks.add(ledger_identity.encode_mark(
                        str(bond["final_wafer"]), str(bond["bonding_leg"])))
                for event in events:
                    evidence_ids.add(event["evidence_id"])
                    payload = event["payload"]
                    if payload.get("state") != "recorded" or "value" not in payload:
                        continue
                    recorded_members.add(member_key)
                    value_key = _json_value(payload["value"])
                    entry = values.setdefault(value_key, {
                        "value": payload["value"], "members": set(), "evidence_ids": set()})
                    entry["members"].add(member_key)
                    entry["evidence_ids"].add(event["evidence_id"])
            rendered_values = [
                {"value": entry["value"], "count": len(entry["members"]),
                 "evidence_ids": sorted(entry["evidence_ids"])}
                for _key, entry in sorted(values.items())]
            observation = {
                "group_id": group_id,
                "state": _measurement_rollup(member_states),
                "state_counts": dict(sorted(state_counts.items())),
                "count": len(recorded_members), "total": len(population),
                "denominator": len(population), "denominator_kind": population_kind,
                "values": rendered_values,
                "wafer_mark_keys": sorted(marks), "evidence_ids": sorted(evidence_ids),
            }
            if population_kind == "component":
                observation["of_components"] = len(population)
            else:
                observation["of_aggregation_units"] = len(population)
            if len(rendered_values) == 1:
                observation["value"] = rendered_values[0]["value"]
            observations.append(observation)

        digest = hashlib.sha256(f"{population_kind}:{encoded}".encode("utf-8")).hexdigest()[:16]
        metric = str(signature.get("metric") or "measurement")
        unit = str(signature.get("unit") or "").strip()
        rows.append({
            "facet_id": f"measurement:{population_kind}:{digest}",
            "kind": "measurement", "predicate": "measured",
            "subject_grain": population_kind,
            "label": f"{metric} ({unit})" if unit else metric,
            "state": _measurement_rollup(row["state"] for row in observations),
            "signature": signature, "groups": observations,
            "wafer_mark_keys": sorted({mark for item in observations
                                        for mark in item["wafer_mark_keys"]}),
            "evidence_ids": sorted({evidence for item in observations
                                     for evidence in item["evidence_ids"]}),
            "evidence": {"basis": f"{population_kind}_measured_atoms",
                         "denominators_included": True,
                         "values_aggregated": False},
            "surprise": {"score": None, "binding_state": "unknown",
                         "reason": "measurement_scoring_not_declared",
                         "mechanism_model_id": None},
        })
    return rows


def _sequence_comparison(group_components, process_by_wafer):
    clusters = {}
    missing = defaultdict(int)
    for group_id, keyed in group_components.items():
        for component_key, row in keyed.items():
            events = _events_for_path(row, process_by_wafer)
            if not events:
                missing[group_id] += 1
                continue
            occurrences = defaultdict(int)
            tokens, evidence, ambiguous = [], [], False
            previous_at, previous_token = None, None
            for event in events:
                payload = event["payload"]
                token = (payload.get("step"), _json_value(payload.get("recipe")))
                occurrences[token] += 1
                tokens.append({"step": payload.get("step"),
                               "recipe": payload.get("recipe"),
                               "occurrence": occurrences[token]})
                evidence.append(event["evidence_id"])
                if previous_at == event["occurred_at"] and previous_token != token:
                    ambiguous = True
                previous_at, previous_token = event["occurred_at"], token
            encoded = _json_value(tokens)
            cluster_id = "schema:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
            cluster = clusters.setdefault(cluster_id, {
                "id": cluster_id, "tokens": tokens, "subjects": 0,
                "groups": defaultdict(int), "evidence_ids": set(),
                "wafer_mark_keys": set(), "group_wafer_mark_keys": defaultdict(set),
                "ambiguous_order": False})
            cluster["subjects"] += 1
            cluster["groups"][group_id] += 1
            cluster["evidence_ids"].update(evidence)
            final_wafer = row.get("bond", {}).get("final_wafer")
            bonding_leg = row.get("bond", {}).get("bonding_leg")
            if final_wafer and bonding_leg:
                mark_key = ledger_identity.encode_mark(str(final_wafer), str(bonding_leg))
                cluster["wafer_mark_keys"].add(mark_key)
                cluster["group_wafer_mark_keys"][group_id].add(mark_key)
            cluster["ambiguous_order"] = cluster["ambiguous_order"] or ambiguous
    ordered = sorted(clusters.values(), key=lambda row: (
        row["ambiguous_order"], -row["subjects"], row["id"]))
    rendered = [{key: value for key, value in row.items()
                 if key not in ("groups", "wafer_mark_keys", "group_wafer_mark_keys",
                                "evidence_ids")} | {"groups": dict(sorted(row["groups"].items())),
                 "group_wafer_marks": [{"group_id": group_id,
                                          "wafer_mark_keys": sorted(marks)}
                                         for group_id, marks in sorted(
                                             row["group_wafer_mark_keys"].items())],
                 "wafer_mark_keys": sorted(row["wafer_mark_keys"]),
                 "evidence_ids": sorted(row["evidence_ids"])} for row in ordered]
    if not ordered:
        return {"state": "absent", "reason": "process_events_absent",
                "coverage": {"resolved": 0,
                             "total": sum(len(v) for v in group_components.values())},
                "clusters": [], "common_spans": [], "differences": []}

    sequences = [[(t["step"], _json_value(t.get("recipe"))) for t in row["tokens"]]
                 for row in ordered]
    prefix = 0
    while all(len(seq) > prefix and seq[prefix] == sequences[0][prefix]
              for seq in sequences):
        prefix += 1
    suffix = 0
    while (all(len(seq) - suffix > prefix and seq[-1 - suffix] == sequences[0][-1 - suffix]
               for seq in sequences)):
        suffix += 1
    common_spans = []
    if prefix:
        common_spans.append({"position": "prefix", "tokens": ordered[0]["tokens"][:prefix],
                             "count": sum(row["subjects"] for row in ordered)})
    if suffix:
        common_spans.append({"position": "suffix", "tokens": ordered[0]["tokens"][-suffix:],
                             "count": sum(row["subjects"] for row in ordered)})

    differences = []
    reference = ordered[0]
    ref_tokens = [(t["step"], _json_value(t.get("recipe")))
                  for t in reference["tokens"]]
    for branch in ordered[1:]:
        tokens = [(t["step"], _json_value(t.get("recipe")))
                  for t in branch["tokens"]]
        ref_counts = {token: ref_tokens.count(token) for token in set(ref_tokens)}
        counts = {token: tokens.count(token) for token in set(tokens)}
        if branch["ambiguous_order"] or reference["ambiguous_order"]:
            kind = "ambiguous_order"
        elif set(ref_tokens) == set(tokens) and ref_counts != counts:
            kind = "repeat_change"
        elif len(set(ref_tokens)) == len(ref_tokens) and sorted(ref_tokens) == sorted(tokens):
            kind = "order_change"
        elif all(token in tokens for token in ref_tokens) and len(tokens) > len(ref_tokens):
            kind = "insert"
        elif all(token in ref_tokens for token in tokens) and len(tokens) < len(ref_tokens):
            kind = "delete"
        elif len(tokens) == len(ref_tokens):
            kind = "substitution"
        else:
            kind = "schema_branch"
        differences.append({"kind": kind, "left_cluster": reference["id"],
                            "right_cluster": branch["id"],
                            "left": reference["tokens"][prefix:len(ref_tokens)-suffix or None],
                            "right": branch["tokens"][prefix:len(tokens)-suffix or None],
                            "support": {"left": dict(reference["groups"]),
                                        "right": dict(branch["groups"])},
                            "wafer_mark_keys": sorted(reference["wafer_mark_keys"] |
                                                       branch["wafer_mark_keys"]),
                            "evidence_ids": sorted(reference["evidence_ids"] |
                                                   branch["evidence_ids"])})
    if missing:
        differences.append({"kind": "record_absent", "support": dict(sorted(missing.items())),
                            "evidence_ids": [], "state": "missing"})
    return {"state": "ready", "coverage": {
                "resolved": sum(row["subjects"] for row in ordered),
                "total": sum(len(v) for v in group_components.values())},
            "clusters": rendered, "common_spans": common_spans,
            "differences": differences}


def _experiment_unit_sequence(group_units, process_by_wafer):
    """Summarize bonding experiment order once per aggregate, never per component."""
    clusters = {}
    total = sum(len(rows) for rows in group_units.values())
    missing = 0
    for group_id, keyed in group_units.items():
        for unit_key, row in keyed.items():
            events = _unit_events(row, process_by_wafer)
            if not events:
                missing += 1
                continue
            occurrences = defaultdict(int)
            tokens = []
            for event in events:
                payload = event["payload"]
                occurrence_key = (payload.get("step"), _json_value(payload.get("recipe")))
                occurrences[occurrence_key] += 1
                tokens.append({"step": payload.get("step"),
                               "recipe": payload.get("recipe"),
                               "occurrence": occurrences[occurrence_key]})
            encoded = _json_value(tokens)
            cluster_id = "unit-schema:" + hashlib.sha256(
                encoded.encode("utf-8")).hexdigest()[:16]
            cluster = clusters.setdefault(cluster_id, {
                "id": cluster_id, "subject_grain": "bonding_experiment_unit",
                "tokens": tokens,
                "subjects": 0, "groups": defaultdict(int), "wafer_mark_keys": set(),
                "evidence_ids": set()})
            cluster["subjects"] += 1
            cluster["groups"][group_id] += 1
            cluster["wafer_mark_keys"].add(ledger_identity.encode_mark(*unit_key))
            cluster["evidence_ids"].update(event["evidence_id"] for event in events)
    rendered = [{**row, "groups": dict(sorted(row["groups"].items())),
                 "wafer_mark_keys": sorted(row["wafer_mark_keys"]),
                 "evidence_ids": sorted(row["evidence_ids"])}
                for row in sorted(clusters.values(), key=lambda item: item["id"])]
    return {"state": "ready" if rendered else "absent",
            **({"reason": "bonding_experiment_process_events_absent"}
               if not rendered else {}),
            "coverage": {"resolved": total - missing, "total": total},
            "clusters": rendered}


def _facet_rows(counts, group_components, facet_kind, finding_kind,
                coverage_by_group=None, evidence_by_group=None,
                population_kind="component"):
    signatures = sorted({signature for by_signature in counts.values() for signature in by_signature})
    group_ids = sorted(group_components)
    rows = []
    for signature in signatures:
        values = json.loads(signature)
        observations = []
        for group_id in group_ids:
            component_keys = counts[group_id].get(signature, set())
            count = len(component_keys)
            total = len(group_components[group_id])
            marks = sorted({ledger_identity.encode_mark(
                                str(group_components[group_id][key]["bond"]["final_wafer"]),
                                str(group_components[group_id][key]["bond"]["bonding_leg"]))
                            for key in component_keys
                            if group_components[group_id][key].get("bond", {}).get("final_wafer")
                            and group_components[group_id][key].get("bond", {}).get("bonding_leg")})
            group_evidence = sorted((evidence_by_group or {}).get(group_id, {}).get(
                signature, set()))
            observations.append({"group_id": group_id, "count": count,
                                 "of_components": total,
                                 "denominator": total,
                                 "denominator_kind": population_kind,
                                 **({"of_aggregation_units": total}
                                    if population_kind == "bonding_experiment_unit" else {}),
                                 "frequency": round(count / total, 6) if total else None,
                                 "wafer_mark_keys": marks,
                                 "evidence_ids": group_evidence})
        verdict = {"verdict": "unknown",
                   "reason": ("categorical_process_has_no_numeric_binding"
                              if facet_kind == "process" else "finding_kind_absent"),
                   "model": None, "binding_key": None, "path": None}
        expected = observations[1]["frequency"] if len(observations) == 2 else None
        observed = observations[0]["frequency"] if len(observations) == 2 else None
        raw_effect = score = coverage = reliability = None
        if len(observations) == 2 and all(row["of_components"] for row in observations):
            a, b = observations
            a_miss = a["of_components"] - a["count"]
            b_miss = b["of_components"] - b["count"]
            raw_effect = (math.log((a["count"] + 0.5) / (a_miss + 0.5)) -
                          math.log((b["count"] + 0.5) / (b_miss + 0.5)))
            coverage = min((coverage_by_group or {}).get(a["group_id"], 1.0),
                           (coverage_by_group or {}).get(b["group_id"], 1.0))
            reliability = (a["of_components"] / (a["of_components"] + 1.0) *
                           b["of_components"] / (b["of_components"] + 1.0))
            score = round(abs(raw_effect) * coverage * reliability, 6)
        rows.append({"facet_id": f"{facet_kind}:{population_kind}:{len(rows)}",
                     "kind": facet_kind, "subject_grain": population_kind,
                     "signature": values,
                     "groups": observations,
                     "wafer_mark_keys": sorted({mark for item in observations
                                                  for mark in item["wafer_mark_keys"]}),
                     "evidence_ids": sorted({evidence for item in observations
                                              for evidence in item["evidence_ids"]}),
                     "evidence": {"basis": f"{population_kind}_frequency",
                                  "denominators_included": True},
                     "surprise": {"score": score, "expected": expected,
                                  "observed": observed,
                                  "raw_effect": (round(raw_effect, 6)
                                                 if raw_effect is not None else None),
                                  "effect_kind": "smoothed_log_odds_difference",
                                  "smoothing": 0.5, "coverage": coverage,
                                  "reliability": (round(reliability, 6)
                                                  if reliability is not None else None),
                                  "denominators": [{"group_id": item["group_id"],
                                                    "n": item["of_components"]}
                                                   for item in observations],
                                  "mechanism_model_id": verdict.get("model"),
                                  "binding_state": verdict.get("verdict", "unknown"),
                                  "binding_key": verdict.get("binding_key"),
                                  "mechanism_path": verdict.get("path"),
                                  "reason": verdict.get("reason")}})
    return rows


def _actions(process_rows, groups, finding_kind):
    group_ids = sorted(g["group_id"] for g in groups)
    actions = []
    if len(group_ids) == 2:
        for row in process_rows:
            by_group = {g["group_id"]: g for g in row["groups"]}
            a, b = group_ids
            total_a, total_b = by_group[a]["denominator"], by_group[b]["denominator"]
            gain = _information_gain(by_group[a]["count"], total_a,
                                     by_group[b]["count"], total_b)
            if row["surprise"]["binding_state"] in ("pass", "bias_candidate") and gain:
                actions.append({"kind": "doe", "information_gain": gain,
                                "hypotheses_split": 1, "missing_resolved": 0,
                                "target_count": total_a + total_b,
                                "mechanism_model_id": row["surprise"]["mechanism_model_id"],
                                "parameters": row["signature"],
                                "evidence_basis": "empirical_binary_mutual_information"})
    missing = sum(g["process_evidence"]["missing"] +
                  g.get("aggregation_unit_process_evidence", {}).get("missing", 0)
                  for g in groups)
    if missing:
        actions.append({"kind": "collect_missing", "information_gain": None,
                        "information_gain_state": "unknown_until_values_exist",
                        "hypotheses_split": 0, "missing_resolved": missing,
                        "target_count": missing, "mechanism_model_id": None,
                        "parameters": {"predicate": "processed_with"}})
    return actions
