"""Bounded, read-only graph projection of the canonical ledger lineage.

This module does not invent a second walk.  It consumes the same ``ClaimLookup``
neighbourhood as :mod:`ledger_trace`; the difference is presentation.  ``trace``
resolves one answer per hop, while this projection keeps every live claim so a
branch, disagreement, or missing continuation remains visible in a graph viewer.
"""

from __future__ import annotations

import base64
import json
import re
from collections import Counter, defaultdict, deque
from datetime import datetime

import ledger_trace


MAX_HOPS = ledger_trace.DEFAULT_MAX_DEPTH
DEFAULT_NODE_LIMIT = 400
DEFAULT_EDGE_LIMIT = 1200
MAX_CLAIM_SCAN = 5000
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def entity_id(entity_type, keys):
    raw = _canonical([str(entity_type), keys or {}]).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"ledger-entity:v1:{token}"


def decode_entity_id(value):
    """Inverse of :func:`entity_id`, strict enough to reject forged URL state."""
    text = str(value or "").strip()
    prefix = "ledger-entity:v1:"
    if not text.startswith(prefix):
        raise ValueError("entity id must use ledger-entity:v1")
    token = text[len(prefix):]
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("entity id is not valid canonical UTF-8 JSON") from exc
    if (not isinstance(decoded, list) or len(decoded) != 2
            or not isinstance(decoded[0], str)
            or not isinstance(decoded[1], dict) or not decoded[1]):
        raise ValueError("entity id must contain [type, structured keys]")
    if entity_id(decoded[0], decoded[1]) != text:
        raise ValueError("entity id is not in canonical spelling")
    try:
        from ledger import vocabulary
        violations = vocabulary.check_subject_keys(decoded[0], decoded[1])
    except Exception as exc:  # pragma: no cover - deployment failure, not user input
        raise ValueError(f"entity vocabulary unavailable: {exc}") from exc
    if violations:
        raise ValueError("; ".join(violations))
    return decoded[0], decoded[1]


def _entity(entity_type, keys):
    keys = dict(keys or {})
    try:
        from ledger import vocabulary
        key_order = vocabulary.ENTITY_TYPES.get(str(entity_type), {}).get("keys") or keys.keys()
    except Exception:  # pragma: no cover - deployment failure is reported by the route
        key_order = keys.keys()
    values = [str(keys.get(name)) for name in key_order
              if keys.get(name) is not None and str(keys.get(name)) != ""]
    label = " / ".join(values[:2]) or str(entity_type)
    return {
        "id": entity_id(entity_type, keys),
        "type": str(entity_type),
        "keys": keys,
        "label": label,
        "depth": None,
        "claim_count": 0,
        "predicates": [],
    }


def _target_of(claim):
    if claim.object_kind != "entity_ref":
        return None
    payload = claim.object_payload or {}
    entity_type = payload.get("type")
    keys = payload.get("keys")
    if not entity_type or not isinstance(keys, dict) or not keys:
        return None
    return str(entity_type), keys


def _instant(value, zone):
    if not isinstance(value, datetime):
        return str(value) if value is not None else None
    return value.astimezone(zone).isoformat()


def _edge_rows(claims, config, zone):
    """Aggregate duplicate witnesses without merging distinct targets."""
    groups = {}
    for claim in claims:
        target = _target_of(claim)
        if target is None:
            continue
        source_id = entity_id(claim.subject_type, claim.subject_keys)
        target_id = entity_id(target[0], target[1])
        key = (source_id, str(claim.predicate), target_id)
        row = groups.get(key)
        rank = ledger_trace.claim_class(claim, config)
        basis = ledger_trace.hop_basis(claim, config)
        instant = _instant(claim.occurred_at, zone)
        if row is None:
            row = {
                "id": "ledger-edge:v1:" + base64.urlsafe_b64encode(
                    _canonical(key).encode("utf-8")).decode("ascii").rstrip("="),
                "source": source_id,
                "target": target_id,
                "predicate": str(claim.predicate),
                "witnesses": 0,
                "rank": rank,
                "basis": basis,
                "first_at": instant,
                "last_at": instant,
                "sources": [],
                "event_ids": [],
                "qualifiers": dict((claim.object_payload or {}).get("qualifiers") or {}),
            }
            groups[key] = row
        row["witnesses"] += 1
        row["rank"] = min(row["rank"], rank)
        if row["basis"] is None and basis is not None:
            row["basis"] = basis
        if instant is not None:
            row["first_at"] = min(row["first_at"], instant) if row["first_at"] else instant
            row["last_at"] = max(row["last_at"], instant) if row["last_at"] else instant
        source = str(claim.source_who or "")
        if source and source not in row["sources"]:
            row["sources"].append(source)
        if len(row["event_ids"]) < 20:
            row["event_ids"].append(str(claim.id))
    return list(groups.values())


def _depths(seed_id, edges):
    adjacency = defaultdict(list)
    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])
    depths = {seed_id: 0}
    queue = deque([seed_id])
    while queue:
        current = queue.popleft()
        for target in adjacency.get(current, ()):
            if target in depths:
                continue
            depths[target] = depths[current] + 1
            queue.append(target)
    return depths


def _claim_label(claim):
    payload = claim.object_payload or {}
    predicate = str(claim.predicate)
    if claim.object_kind is None:
        return "등록"
    if predicate == "processed_with":
        return " · ".join(str(v) for v in (payload.get("step"), payload.get("recipe"))
                          if v not in (None, "")) or predicate
    if predicate == "measured":
        metric = payload.get("metric") or "계측"
        value = payload.get("value", payload.get("state"))
        unit = payload.get("unit") or ""
        return f"{metric} = {value} {unit}".strip()
    if predicate == "observed":
        return " · ".join(str(v) for v in (payload.get("finding_kind"),
                                             payload.get("method"))
                          if v not in (None, "")) or predicate
    if predicate == "has_param":
        return f"{payload.get('param', '설정값')} = {payload.get('value', '—')} {payload.get('unit', '')}".strip()
    if predicate == "transferred":
        return f"{payload.get('from', '출발')} → {payload.get('to', '도착')}"
    parts = []
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) and value not in (None, ""):
            parts.append(f"{key}={value}")
        if len(parts) == 2:
            break
    return " · ".join(parts) or predicate


def _claims_for_entities(connection, entities, relation, limit):
    if not entities or limit <= 0:
        return [], False
    if not _IDENTIFIER.match(relation or ""):
        raise ValueError("relation must be a bare identifier")
    frontier = [{"type": item[0], "keys": item[1]} for item in entities]
    rows = ledger_trace._fetch(connection, f"""
        WITH frontier AS (
            SELECT type, keys
            FROM jsonb_to_recordset(CAST(%(frontier)s AS jsonb))
                 AS item(type text, keys jsonb)
        )
        SELECT e.id, e.subject_type, e.subject_keys, e.predicate, e.object_kind,
               e.object_payload, e.occurred_at, e.source_who,
               e.source_translator_ver, e.source_raw_ref, e.supersedes
        FROM frontier f
        JOIN {relation} e
          ON e.subject_type = f.type AND e.subject_keys = f.keys
        ORDER BY e.subject_type, e.subject_keys, e.predicate,
                 e.occurred_at DESC, e.id DESC
        LIMIT %(fetch)s
    """, {"frontier": _canonical(frontier), "fetch": int(limit) + 1})
    truncated = len(rows) > limit
    return [ledger_trace._claim_from_row(row) for row in rows[:limit]], truncated


def explore_entity(entity_type, keys, connection, hops=MAX_HOPS,
                   node_limit=DEFAULT_NODE_LIMIT, edge_limit=DEFAULT_EDGE_LIMIT,
                   relation="ledger_events", config=None):
    """Project every claim reachable forward from any registered entity.

    Entity references continue the breadth-first walk. Value/event/objectless claims
    become inspectable claim nodes, so a Wafer or Recipe does not render as an
    isolated dot merely because its ontology edges carry values instead of entity refs.
    """
    seed_id = entity_id(entity_type, keys)
    # Reuse the vocabulary's exact structured-identity judgement.
    decode_entity_id(seed_id)
    hops = max(1, min(int(hops), MAX_HOPS))
    node_limit = max(10, min(int(node_limit), 1000))
    edge_limit = max(20, min(int(edge_limit), 3000))
    cfg = config or ledger_trace.load_resolver_config()
    zone = ledger_trace.resolve_display_zone(cfg)

    nodes = {seed_id: _entity(entity_type, keys)}
    depths = {seed_id: 0}
    frontier = [(entity_type, dict(keys))]
    all_claims = []
    scanned = 0
    claim_cap = min(MAX_CLAIM_SCAN, max(200, edge_limit * 4))
    depth_truncated = False
    claims_truncated = False

    for depth in range(hops + 1):
        remaining = claim_cap - scanned
        if not frontier or remaining <= 0:
            claims_truncated = claims_truncated or remaining <= 0
            break
        batch, cut = _claims_for_entities(connection, frontier, relation, remaining)
        scanned += len(batch)
        claims_truncated = claims_truncated or cut
        live = ledger_trace.live_claims(batch)
        all_claims.extend(live)
        next_frontier = []
        for claim in live:
            target = _target_of(claim)
            if target is None:
                continue
            target_node = _entity(target[0], target[1])
            if target_node["id"] not in nodes:
                if len(nodes) >= node_limit:
                    claims_truncated = True
                    continue
                nodes[target_node["id"]] = target_node
                depths[target_node["id"]] = depth + 1
                if depth < hops:
                    next_frontier.append((target[0], dict(target[1])))
                else:
                    depth_truncated = True
        frontier = next_frontier
        if cut:
            break

    predicate_counts = defaultdict(Counter)
    for claim in all_claims:
        source_id = entity_id(claim.subject_type, claim.subject_keys)
        predicate_counts[source_id][str(claim.predicate)] += 1

    edges = _edge_rows(all_claims, cfg, zone)
    claim_groups = {}
    for claim in all_claims:
        if _target_of(claim) is not None:
            continue
        source_id = entity_id(claim.subject_type, claim.subject_keys)
        token = (source_id, str(claim.predicate), str(claim.object_kind or "none"),
                 _canonical(claim.object_payload or {}))
        row = claim_groups.get(token)
        instant = _instant(claim.occurred_at, zone)
        if row is None:
            encoded = base64.urlsafe_b64encode(_canonical(token).encode("utf-8")).decode("ascii").rstrip("=")
            node_id = f"ledger-claim:v1:{encoded}"
            node_type = ("Value" if claim.object_kind == "value" else
                         "Event" if claim.object_kind == "event_ref" else "Empty")
            nodes[node_id] = {
                "id": node_id, "type": node_type, "keys": dict(claim.object_payload or {}),
                "label": _claim_label(claim), "depth": depths.get(source_id, 0) + 1,
                "claim_count": 0, "predicates": [], "schema_kind": "claim_instance",
            }
            row = {
                "id": "ledger-edge:v1:" + encoded,
                "source": source_id, "target": node_id,
                "predicate": str(claim.predicate), "witnesses": 0,
                "rank": ledger_trace.claim_class(claim, cfg),
                "basis": ledger_trace.hop_basis(claim, cfg),
                "first_at": instant, "last_at": instant,
                "sources": [], "event_ids": [], "qualifiers": {},
            }
            claim_groups[token] = row
        row["witnesses"] += 1
        nodes[row["target"]]["claim_count"] += 1
        if instant is not None:
            row["first_at"] = min(row["first_at"], instant) if row["first_at"] else instant
            row["last_at"] = max(row["last_at"], instant) if row["last_at"] else instant
        source = str(claim.source_who or "")
        if source and source not in row["sources"]:
            row["sources"].append(source)
        if len(row["event_ids"]) < 20:
            row["event_ids"].append(str(claim.id))
    edges.extend(claim_groups.values())

    for node in nodes.values():
        if node.get("schema_kind") == "claim_instance":
            continue
        node["depth"] = depths.get(node["id"])
        counts = predicate_counts.get(node["id"], {})
        node["claim_count"] = sum(counts.values())
        node["predicates"] = [{"predicate": name, "count": count}
                              for name, count in sorted(counts.items())]

    ordered_nodes = sorted(nodes.values(), key=lambda n: (
        n.get("depth") is None, n.get("depth") if n.get("depth") is not None else 10 ** 9,
        n["type"], n["label"], n["id"]))
    node_cut = len(ordered_nodes) > node_limit
    ordered_nodes = ordered_nodes[:node_limit]
    kept = {node["id"] for node in ordered_nodes}
    graph_edges = [edge for edge in edges
                   if edge["source"] in kept and edge["target"] in kept]
    graph_edges.sort(key=lambda edge: (
        depths.get(edge["source"], 10 ** 9), edge["predicate"], edge["target"], edge["id"]))
    edge_cut = len(graph_edges) > edge_limit
    graph_edges = graph_edges[:edge_limit]
    return {
        "state": "ready" if all_claims else "empty",
        "generated_at": datetime.now(zone).isoformat(),
        "seed": nodes[seed_id],
        "nodes": ordered_nodes,
        "edges": graph_edges,
        "walk": {
            "hops_requested": hops,
            "hops_reached": max((node.get("depth") or 0 for node in ordered_nodes), default=0),
            "direction": "subject_to_object",
            "mode": "entity_claims",
            "claims_scanned": scanned,
        },
        "limits": {"nodes": node_limit, "edges": edge_limit, "claims": claim_cap},
        "truncated": {
            "depth": depth_truncated,
            "nodes": node_cut,
            "edges": edge_cut,
            "claims": claims_truncated,
            "reason": "bounded entity claim projection" if any((depth_truncated, node_cut, edge_cut, claims_truncated)) else None,
        },
        "message": None if all_claims else "선택한 개체에 원장 주장이 없습니다",
    }


def explore(lot, lookup, hops=MAX_HOPS, node_limit=DEFAULT_NODE_LIMIT,
            edge_limit=DEFAULT_EDGE_LIMIT, config=None):
    """Return every live lineage claim reachable from ``lot`` as a bounded graph."""
    lot = str(lot or "").strip()
    if not lot:
        raise ValueError("lot 필요")
    hops = max(1, min(int(hops), MAX_HOPS))
    node_limit = max(10, min(int(node_limit), 1000))
    edge_limit = max(20, min(int(edge_limit), 3000))
    cfg = config or ledger_trace.load_resolver_config()
    zone = ledger_trace.resolve_display_zone(cfg)

    neighbourhood = lookup.neighbourhood(lot, max_depth=hops)
    claims = ledger_trace.live_claims(neighbourhood.claims)
    seed = _entity("Lot", {"lot": lot})
    nodes = {seed["id"]: seed}
    predicate_counts = defaultdict(Counter)

    for claim in claims:
        subject = _entity(claim.subject_type, claim.subject_keys)
        nodes.setdefault(subject["id"], subject)
        predicate_counts[subject["id"]][str(claim.predicate)] += 1
        target = _target_of(claim)
        if target is not None:
            target_node = _entity(target[0], target[1])
            nodes.setdefault(target_node["id"], target_node)

    edges = _edge_rows(claims, cfg, zone)
    depths = _depths(seed["id"], edges)
    for node in nodes.values():
        node["depth"] = depths.get(node["id"])
        counts = predicate_counts.get(node["id"], {})
        node["claim_count"] = sum(counts.values())
        node["predicates"] = [
            {"predicate": name, "count": count}
            for name, count in sorted(counts.items())
        ]

    ordered_nodes = sorted(nodes.values(), key=lambda n: (
        n["depth"] is None, n["depth"] if n["depth"] is not None else 10 ** 9,
        n["type"], n["label"], n["id"]))
    nodes_truncated = len(ordered_nodes) > node_limit
    ordered_nodes = ordered_nodes[:node_limit]
    kept = {node["id"] for node in ordered_nodes}
    graph_edges = [edge for edge in edges
                   if edge["source"] in kept and edge["target"] in kept]
    graph_edges.sort(key=lambda e: (
        depths.get(e["source"], 10 ** 9), e["predicate"], e["target"], e["id"]))
    edges_truncated = len(graph_edges) > edge_limit
    graph_edges = graph_edges[:edge_limit]

    return {
        "state": "ready" if claims else "empty",
        "generated_at": datetime.now(zone).isoformat(),
        "seed": seed,
        "nodes": ordered_nodes,
        "edges": graph_edges,
        "walk": {
            "hops_requested": hops,
            "hops_reached": max((n["depth"] or 0 for n in ordered_nodes), default=0),
            "traversal_predicate": ledger_trace.traversal_predicate(),
            "fetched_predicates": list(ledger_trace.lineage_predicates()),
            "direction": "subject_to_object",
        },
        "limits": {"nodes": node_limit, "edges": edge_limit},
        "truncated": {
            "depth": bool(neighbourhood.truncated),
            "nodes": nodes_truncated,
            "edges": edges_truncated,
            "reason": neighbourhood.truncation_reason,
        },
        "message": (None if claims else
                    f"lot={lot}에 걷기 가능한 원장 주장이 없습니다"),
    }
