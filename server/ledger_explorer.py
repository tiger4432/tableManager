"""Bounded, read-only graph projection of the canonical ledger lineage.

This module does not invent a second walk.  It consumes the same ``ClaimLookup``
neighbourhood as :mod:`ledger_trace`; the difference is presentation.  ``trace``
resolves one answer per hop, while this projection keeps every live claim so a
branch, disagreement, or missing continuation remains visible in a graph viewer.
"""

from __future__ import annotations

import base64
import json
from collections import Counter, defaultdict, deque
from datetime import datetime

import ledger_trace


MAX_HOPS = ledger_trace.DEFAULT_MAX_DEPTH
DEFAULT_NODE_LIMIT = 400
DEFAULT_EDGE_LIMIT = 1200


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def entity_id(entity_type, keys):
    raw = _canonical([str(entity_type), keys or {}]).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"ledger-entity:v1:{token}"


def decode_entity_id(value):
    """Inverse of :func:`entity_id`, strict enough to reject forged URL state.

    🔴 A READ DOES NOT ASK THE WRITE GATE WHETHER A SUBJECT TYPE IS DECLARED
    (ruling 2026-08-23, round 3 "v1 retirement").

    This used to end by calling `vocabulary.check_subject_keys` - the same function
    `ledger.gate` runs before an atom is WRITTEN - and refusing the id on any violation.
    That made the closed vocabulary a condition of READING, and the two questions are not
    the same one:

        writing   "may this word be spoken?"      a declaration is the whole point
        reading   "what was already said?"        the atoms exist either way

    MEASURED 2026-08-23 on the live ledger, three subject types were refused as seeds
    while holding atoms nobody disputes: `die` (1,405), `DTJob` (792) and `WaferLeg` (42,
    over 12 subjects). `WaferLeg` is the sharp case - it is declared by NEITHER generation,
    v1 having retired it and v5 never carrying it, so no edit to any declaration could have
    reached it. A production ledger keeps atoms written before a declaration changed, so a
    read that gates on the current declaration loses the past the first time someone edits
    one, and reports that loss as `422` rather than as an empty result.

    🔴 ABSENCE IS NOT A FAULT. An undeclared type ANSWERS; it simply answers without the
    extras a declaration would have supplied (`_entity` falls back to insertion order for
    key order, and to the raw type name for a label).

    WHAT STILL REJECTS A FORGED ID, and why that was never the vocabulary's job: the
    canonical-spelling check below re-encodes the decoded pair and compares it to the
    text. An id that is not the exact output of :func:`entity_id` is refused there,
    independently of which words happen to be declared today. Structure - a two-item
    list, a string type, a non-empty mapping of keys - is checked here too. What is gone
    is only the judgement about whether the WORD is in the book.

    ⚠️ THE WRITE PATH IS UNTOUCHED. `ledger.gate` still calls `check_subject_keys` and
    `check_signature` itself; this function was never on the way to a write.
    """
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
