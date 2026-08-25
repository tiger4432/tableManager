"""Unified, bounded evidence subgraph over evidence and physical referents.

This is a projection of ``ledger_events`` rather than a second graph store.  It exposes
the append-only atom as a first-class Claim node and the source utterance that grouped
claims as a first-class Event node:

    Event --asserts--> Claim --subject--> Entity
                              --<predicate>--> Entity | Value

High-cardinality observations stay as individual Claim rows in the ledger, but defects
are not promoted to traversable domain entities.  An Entity walk projects them as a
Finding Collection with aggregate and spatial properties.  Expanding a Collection
adds terminal Finding Point nodes; those points never continue an automatic walk.

A payload leaf the modeller has bound to a physical quantity continues into the declared
mechanism graph, which is synthesized from `mechanism_models.json` rather than read from
the ledger — a Quantity is not an entity anybody asserted:

    Value             --binding--> Quantity
    Finding Collection --finding--> Quantity   the model's own target, by finding_kind
    Quantity        --mechanism--> Quantity    `dir` as declared

Every public node id is opaque, typed, canonical, and can be passed back as the next
seed.  Traversal is undirected for reachability but directed in the returned evidence.
All database probes are exact indexed batches and every response has hard budgets.
"""
from __future__ import annotations

import base64
import bisect
import json
import re
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import ledger_explorer
import ledger_trace
import enrichment_actions
from ledger_api import finding_kinds
from ledger_api import mechanism_gate


DEFAULT_HOPS = 12
MAX_HOPS = 40
DEFAULT_NODE_LIMIT = 400
DEFAULT_EDGE_LIMIT = 6000
MAX_NODE_LIMIT = 1000
#: 🔴 THESE THREE WERE SIZED FOR A GRAPH THAT WAS TWO THIRDS PLUMBING, and on 2026-08-25 the
#: plumbing stopped being nodes and edges of its own. The same numbers then described a much
#: smaller graph, so the walk began truncating a shape it used to fit. Re-measured rather than
#: re-guessed, on the board's own default path (SYN-BW-101-16, no follow, hops=6):
#:
#:      edge_limit 1200   1,248 nodes, cut at edges AND claims
#:      edge_limit 3000   1,741 nodes, still cut at edges
#:      edge_limit 6000   settles at 5,079 edges -- `edges` stops binding
#:      claim scan 5000   still cut at claims;  6000 settles at 1,805 nodes / 720 entities
#:
#: So 6,000 and 6,000: each is the first value at which its own ceiling stops being the thing
#: that ends the walk. What remains is `depth`, which is an honest statement that the graph
#: continues, not a budget hiding it.
#:
#: ⚠️ The node ceiling did NOT need to move: at settle the walk holds ~750 budgeted nodes
#: against 1,000, because measurement nodes do not spend it. Raising a limit that was not
#: binding would have been a number chosen to feel safe.
MAX_EDGE_LIMIT = 6000
MAX_CLAIM_SCAN = 6000
DEFAULT_PROPERTY_LIMIT = 10000
MAX_PROPERTY_LIMIT = 20000
EVENT_STATES = {"source_molecule", "source_record", "legacy_atom"}
#: Every node kind this projection can emit.  `collect` names exactly one of them and an
#: unknown name is REFUSED rather than answered with an empty list: a filter that can never
#: be true is indistinguishable from a true absence, and this walk's whole job is telling
#: those two apart.
NODE_KINDS = ("entity", "event", "claim", "collection", "point", "value",
              "quantity", "action")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _token(value):
    return base64.urlsafe_b64encode(
        _canonical(value).encode("utf-8")).decode("ascii").rstrip("=")


def _untoken(value):
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("node id is not valid canonical UTF-8 JSON") from exc


def _instant(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("node occurrence must be a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat()


def _parse_instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("node occurrence is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("node occurrence has no timezone")
    return parsed.astimezone(timezone.utc)


def event_node_id(source_event_id, occurred_at, state):
    event_uuid = str(uuid.UUID(str(source_event_id)))
    if state not in EVENT_STATES:
        raise ValueError(f"unknown source event state: {state}")
    return f"ledger-event:v1:{_token([event_uuid, _instant(occurred_at), state])}"


def claim_node_id(claim_id, occurred_at):
    claim_uuid = str(uuid.UUID(str(claim_id)))
    return f"ledger-claim-atom:v1:{_token([claim_uuid, _instant(occurred_at)])}"


def value_node_id(claim_id, occurred_at):
    claim_uuid = str(uuid.UUID(str(claim_id)))
    return f"ledger-value:v1:{_token([claim_uuid, _instant(occurred_at)])}"


def finding_point_node_id(claim_id, occurred_at):
    """Address one terminal spatial point without making it a traversable Entity."""
    claim_uuid = str(uuid.UUID(str(claim_id)))
    return f"ledger-finding-point:v1:{_token([claim_uuid, _instant(occurred_at)])}"


def finding_collection_node_id(entity_type, keys, finding_kind, method, map_id):
    """Address one exact display collection without turning it into a domain entity."""
    return "ledger-finding-collection:v1:" + _token([
        str(entity_type), dict(keys or {}), str(finding_kind or "unknown"),
        str(method) if method not in (None, "") else None,
        str(map_id) if map_id not in (None, "") else None,
    ])


def quantity_node_id(model, quantity):
    """Address one declared physical quantity INSIDE one mechanism model.

    The model name is part of the identity on purpose.  `bond_pressure` is a node of both
    `void_formation` and `delam_formation`, and one shared node would splice two
    modellers' assertions into a third one nobody made — the rule
    `mechanism_gate.Model.reach` already states for its own BFS.
    """
    return "ledger-quantity:v1:" + _token([str(model), str(quantity)])


def decode_node_id(value):
    """Decode and canonical-reencode any public evidence-graph node id."""
    text = str(value or "").strip()
    if text.startswith("ledger-entity:v1:"):
        entity_type, keys = ledger_explorer.decode_entity_id(text)
        return {"kind": "entity", "type": entity_type, "keys": keys, "id": text}
    if text.startswith(enrichment_actions.ACTION_PREFIX):
        return enrichment_actions.decode_enrich_action_id(text)
    collection_prefix = "ledger-finding-collection:v1:"
    if text.startswith(collection_prefix):
        payload = _untoken(text[len(collection_prefix):])
        if (not isinstance(payload, list) or len(payload) != 5
                or not isinstance(payload[1], dict)):
            raise ValueError("finding collection node id has the wrong shape")
        entity_type, keys, finding_kind, method, map_id = payload
        canonical = finding_collection_node_id(
            entity_type, keys, finding_kind, method, map_id)
        if canonical != text:
            raise ValueError("node id is not in canonical spelling")
        return {
            "kind": "collection", "type": str(entity_type), "keys": keys,
            "finding_kind": str(finding_kind), "method": method,
            "map_id": map_id, "id": text, "expandable": True,
        }
    quantity_prefix = "ledger-quantity:v1:"
    if text.startswith(quantity_prefix):
        payload = _untoken(text[len(quantity_prefix):])
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError("quantity node id has the wrong shape")
        model, quantity = str(payload[0]), str(payload[1])
        if quantity_node_id(model, quantity) != text:
            raise ValueError("node id is not in canonical spelling")
        return {"kind": "quantity", "model": model, "quantity": quantity, "id": text}
    #: 🔴 A CLAIM ID IS NO LONGER A PLACE. Claims became edges on 2026-08-25, so a claim seed
    #: names something the graph has no node for. Refusing says that; answering with a graph
    #: built around a node that does not exist would be a fiction, and answering empty would be
    #: indistinguishable from "this claim has nothing attached". Marking was checked first:
    #: nothing marks a claim.
    if text.startswith("ledger-claim-atom:v1:"):
        raise ValueError(
            "claim ids are no longer seeds -- a claim is an edge, seed its subject instead")
    prefixes = {
        "ledger-event:v1:": "event",
        "ledger-claim-atom:v1:": "claim",
        "ledger-finding-point:v1:": "point",
        "ledger-value:v1:": "value",
    }
    prefix = next((item for item in prefixes if text.startswith(item)), None)
    if prefix is None:
        raise ValueError(
            "node id must be ledger-entity/event/claim-atom/"
            "finding-collection/finding-point/value/quantity/enrich-action v1")
    payload = _untoken(text[len(prefix):])
    kind = prefixes[prefix]
    expected = 3 if kind == "event" else 2
    if not isinstance(payload, list) or len(payload) != expected:
        raise ValueError(f"{kind} node id has the wrong shape")
    node_uuid = str(uuid.UUID(str(payload[0])))
    occurred_at = _parse_instant(payload[1])
    if kind == "event":
        state = str(payload[2])
        canonical = event_node_id(node_uuid, occurred_at, state)
        decoded = {"kind": kind, "event_id": node_uuid,
                   "occurred_at": occurred_at, "event_state": state, "id": text}
    elif kind == "claim":
        canonical = claim_node_id(node_uuid, occurred_at)
        decoded = {"kind": kind, "claim_id": node_uuid,
                   "occurred_at": occurred_at, "id": text}
    elif kind == "point":
        canonical = finding_point_node_id(node_uuid, occurred_at)
        decoded = {"kind": kind, "claim_id": node_uuid,
                   "occurred_at": occurred_at, "id": text, "expandable": True}
    else:
        canonical = value_node_id(node_uuid, occurred_at)
        decoded = {"kind": kind, "claim_id": node_uuid,
                   "occurred_at": occurred_at, "id": text}
    if canonical != text:
        raise ValueError("node id is not in canonical spelling")
    return decoded


@dataclass(frozen=True)
class EvidenceAtom:
    id: str
    subject_type: str
    subject_keys: dict
    predicate: str
    object_kind: str | None
    object_payload: dict
    occurred_at: datetime
    source_who: str | None
    source_translator_ver: str | None
    source_raw_ref: str | None
    supersedes: str | None
    source_event_id: str | None
    source_event_state: str | None

    @property
    def claim_node_id(self):
        return claim_node_id(self.id, self.occurred_at)

    @property
    def event_identity(self):
        # Pre-migration rows remain readable and honest.  They are not grouped by a
        # heuristic: one historical atom becomes one explicitly labelled legacy event.
        if self.source_event_id and self.source_event_state in EVENT_STATES:
            return str(self.source_event_id), self.source_event_state
        return str(self.id), "legacy_atom"

    @property
    def event_node_id(self):
        event_id, state = self.event_identity
        return event_node_id(event_id, self.occurred_at, state)

    @property
    def finding_point_node_id(self):
        return finding_point_node_id(self.id, self.occurred_at)

ATOM_COLUMNS = (
    "id, subject_type, subject_keys, predicate, object_kind, object_payload, "
    "occurred_at, source_who, source_translator_ver, source_raw_ref, supersedes, "
    "source_event_id, source_event_state"
)
EVIDENCE_COLUMNS = ", ".join(f"e.{name.strip()}" for name in ATOM_COLUMNS.split(","))


def _atom_from_row(row):
    keys = json.loads(row[2]) if isinstance(row[2], str) else row[2]
    payload = json.loads(row[5]) if isinstance(row[5], str) else row[5]
    return EvidenceAtom(
        id=str(row[0]), subject_type=str(row[1]), subject_keys=dict(keys or {}),
        predicate=str(row[3]), object_kind=row[4], object_payload=dict(payload or {}),
        occurred_at=row[6], source_who=row[7], source_translator_ver=row[8],
        source_raw_ref=row[9], supersedes=str(row[10]) if row[10] else None,
        source_event_id=str(row[11]) if row[11] else None,
        source_event_state=str(row[12]) if row[12] else None)


class SqlEvidenceLookup:
    """Exact, batched reads against the ledger; no ranking or inference."""

    def __init__(self, connection, relation="ledger_events"):
        if not _IDENTIFIER.match(relation or ""):
            raise ValueError("relation must be a bare identifier")
        self.connection = connection
        self.relation = relation

    def _execute(self, sql, params):
        return ledger_trace._fetch(self.connection, sql, params)

    @staticmethod
    def _bounded(rows, limit):
        cut = len(rows) > limit
        return [_atom_from_row(row) for row in rows[:limit]], cut

    def claims_for_entities(self, entities, direction, limit, *, include_observed=True,
                            follow=None):
        """`follow` narrows which predicates the walk fetches at all.

        🔴 IT BELONGS IN THE SQL, NOT IN A PROJECTION, because a predicate filtered here is
        never fetched and therefore never spends the budget. Filtering after the fetch would
        leave the walk stopping at the same wall and merely hiding what it collected.
        `include_observed` was already a predicate condition in this same clause; this is the
        general form of it, and the two combine with AND.

        `None` means follow everything, which is what every caller did before this existed.
        """
        if not entities or limit <= 0:
            return [], False
        frontier = [{"type": item[0], "keys": item[1]} for item in entities]
        params = {"frontier": _canonical(frontier), "fetch": int(limit) + 1}
        follow_clause = ""
        if follow:
            params["follow"] = list(follow)
            follow_clause = "e.predicate = ANY(%(follow)s)"

        def _where(*conditions):
            kept = [item for item in conditions if item]
            return ("WHERE " + " AND ".join(kept)) if kept else ""

        arms = []
        if direction in ("outgoing", "both"):
            arms.append(f"""
                SELECT {EVIDENCE_COLUMNS} FROM frontier f
                JOIN {self.relation} e
                  ON e.subject_type = f.type AND e.subject_keys = f.keys
                {_where(None if include_observed else "e.predicate <> 'observed'",
                        follow_clause)}
            """)
        if direction in ("incoming", "both"):
            arms.append(f"""
                SELECT {EVIDENCE_COLUMNS} FROM frontier f
                JOIN {self.relation} e
                  ON e.object_kind = 'entity_ref'
                 AND e.object_payload->>'type' = f.type
                 AND e.object_payload->'keys' = f.keys
                {_where(follow_clause)}
            """)
        union = " UNION ".join(arms)
        rows = self._execute(f"""
            WITH frontier AS (
                SELECT type, keys FROM jsonb_to_recordset(CAST(%(frontier)s AS jsonb))
                     AS item(type text, keys jsonb)
            )
            SELECT * FROM ({union}) claims
            ORDER BY occurred_at DESC, id DESC
            LIMIT %(fetch)s
        """, params)
        return self._bounded(rows, limit)

    def finding_summaries_for_entities(self, entities, direction, limit):
        """Group observed claims only after an exact subject-key lookup."""
        if not entities or limit <= 0 or direction == "incoming":
            return [], False
        frontier = [{"type": item[0], "keys": item[1]} for item in entities]
        rows = self._execute(f"""
            WITH frontier AS (
                SELECT type, keys FROM jsonb_to_recordset(CAST(%(frontier)s AS jsonb))
                     AS item(type text, keys jsonb)
            )
            SELECT e.subject_type, e.subject_keys,
                   COALESCE({finding_kinds.payload_field_sql('e.object_payload', 'finding_kind')}, 'unknown'),
                   NULLIF(e.object_payload->>'method', ''),
                   NULLIF(e.object_payload->>'map_id', ''),
                   count(*)::bigint,
                   count(DISTINCT {finding_kinds.payload_field_sql('e.object_payload', 'run_uid')})::bigint,
                   min(e.occurred_at), max(e.occurred_at),
                   count(*) FILTER (WHERE e.object_payload->>'value'
                     ~ '^-?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$')::bigint,
                   avg(CASE WHEN e.object_payload->>'value'
                     ~ '^-?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$'
                     THEN (e.object_payload->>'value')::double precision END),
                   min(CASE WHEN e.object_payload->>'value'
                     ~ '^-?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$'
                     THEN (e.object_payload->>'value')::double precision END),
                   max(CASE WHEN e.object_payload->>'value'
                     ~ '^-?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$'
                     THEN (e.object_payload->>'value')::double precision END),
                   min(CASE WHEN e.object_payload#>>'{{position,x}}' ~ '^-?[0-9]+([.][0-9]+)?$'
                     THEN (e.object_payload#>>'{{position,x}}')::double precision END),
                   max(CASE WHEN e.object_payload#>>'{{position,x}}' ~ '^-?[0-9]+([.][0-9]+)?$'
                     THEN (e.object_payload#>>'{{position,x}}')::double precision END),
                   min(CASE WHEN e.object_payload#>>'{{position,y}}' ~ '^-?[0-9]+([.][0-9]+)?$'
                     THEN (e.object_payload#>>'{{position,y}}')::double precision END),
                   max(CASE WHEN e.object_payload#>>'{{position,y}}' ~ '^-?[0-9]+([.][0-9]+)?$'
                     THEN (e.object_payload#>>'{{position,y}}')::double precision END)
            FROM frontier f
            JOIN {self.relation} e
              ON e.subject_type = f.type AND e.subject_keys = f.keys
            WHERE e.predicate = 'observed'
            GROUP BY e.subject_type, e.subject_keys,
                     COALESCE({finding_kinds.payload_field_sql('e.object_payload', 'finding_kind')}, 'unknown'),
                     NULLIF(e.object_payload->>'method', ''),
                     NULLIF(e.object_payload->>'map_id', '')
            ORDER BY count(*) DESC, e.subject_type, e.subject_keys
            LIMIT %(fetch)s
        """, {"frontier": _canonical(frontier), "fetch": int(limit) + 1})
        summaries = [{
            "subject_type": str(row[0]),
            "subject_keys": json.loads(row[1]) if isinstance(row[1], str) else dict(row[1]),
            "finding_kind": str(row[2]), "method": row[3], "map_id": row[4],
            "occurrence_count": int(row[5]), "run_count": int(row[6]),
            "first_at": _instant(row[7]), "last_at": _instant(row[8]),
            "value_count": int(row[9]), "value_mean": row[10],
            "value_min": row[11], "value_max": row[12],
            "min_x": row[13], "max_x": row[14],
            "min_y": row[15], "max_y": row[16],
        } for row in rows[:limit]]
        return summaries, len(rows) > limit

    def claims_for_collections(self, collections, limit):
        """Unfold only collections explicitly supplied as the traversal frontier."""
        if not collections or limit <= 0:
            return [], False
        frontier = [{
            "type": item[0], "keys": item[1], "finding_kind": item[2],
            "method": item[3], "map_id": item[4],
        } for item in collections]
        rows = self._execute(f"""
            WITH frontier AS (
                SELECT type, keys, finding_kind, method, map_id
                FROM jsonb_to_recordset(CAST(%(frontier)s AS jsonb))
                     AS item(type text, keys jsonb, finding_kind text,
                             method text, map_id text)
            )
            SELECT {EVIDENCE_COLUMNS} FROM frontier f
            JOIN {self.relation} e
              ON e.subject_type = f.type AND e.subject_keys = f.keys
             AND e.predicate = 'observed'
             AND COALESCE({finding_kinds.payload_field_sql('e.object_payload', 'finding_kind')}, 'unknown')
                 = f.finding_kind
             AND NULLIF(e.object_payload->>'method', '') IS NOT DISTINCT FROM f.method
             AND NULLIF(e.object_payload->>'map_id', '') IS NOT DISTINCT FROM f.map_id
            ORDER BY e.occurred_at DESC, e.id DESC
            LIMIT %(fetch)s
        """, {"frontier": _canonical(frontier), "fetch": int(limit) + 1})
        return self._bounded(rows, limit)

    def claims_for_events(self, events, limit):
        if not events or limit <= 0:
            return [], False
        source_events = [
            {"id": item[0], "occurred_at": _instant(item[1])}
            for item in events if item[2] != "legacy_atom"
        ]
        legacy = [(item[0], item[1]) for item in events if item[2] == "legacy_atom"]
        rows = []
        if source_events:
            rows.extend(self._execute(f"""
                WITH frontier AS (
                    SELECT id::uuid AS id, occurred_at
                    FROM jsonb_to_recordset(CAST(%(frontier)s AS jsonb))
                         AS item(id text, occurred_at timestamptz)
                )
                SELECT {EVIDENCE_COLUMNS} FROM frontier f
                JOIN {self.relation} e
                  ON e.source_event_id = f.id AND e.occurred_at = f.occurred_at
                ORDER BY e.occurred_at DESC, e.id DESC
                LIMIT %(fetch)s
            """, {"frontier": _canonical(source_events), "fetch": int(limit) + 1}))
        if legacy and len(rows) <= limit:
            extra, _ = self.claims_by_ids(legacy, limit + 1 - len(rows))
            rows.extend([
                (atom.id, atom.subject_type, atom.subject_keys, atom.predicate,
                 atom.object_kind, atom.object_payload, atom.occurred_at,
                 atom.source_who, atom.source_translator_ver, atom.source_raw_ref,
                 atom.supersedes, atom.source_event_id, atom.source_event_state)
                for atom in extra
            ])
        return self._bounded(rows, limit)

    def claims_by_ids(self, claims, limit):
        if not claims or limit <= 0:
            return [], False
        frontier = [{"id": item[0], "occurred_at": _instant(item[1])}
                    for item in claims]
        rows = self._execute(f"""
            WITH frontier AS (
                SELECT id::uuid AS id, occurred_at
                FROM jsonb_to_recordset(CAST(%(frontier)s AS jsonb))
                     AS item(id text, occurred_at timestamptz)
            )
            SELECT {EVIDENCE_COLUMNS} FROM frontier f
            JOIN {self.relation} e ON e.id = f.id AND e.occurred_at = f.occurred_at
            ORDER BY e.occurred_at DESC, e.id DESC
            LIMIT %(fetch)s
        """, {"frontier": _canonical(frontier), "fetch": int(limit) + 1})
        return self._bounded(rows, limit)


class InMemoryEvidenceLookup:
    """Contract double used to prove traversal independently of PostgreSQL."""

    def __init__(self, atoms):
        self.atoms = list(atoms)

    @staticmethod
    def _result(rows, limit):
        ordered = sorted(rows, key=lambda atom: (atom.occurred_at, atom.id), reverse=True)
        return ordered[:limit], len(ordered) > limit

    def claims_for_entities(self, entities, direction, limit, *, include_observed=True,
                            follow=None):
        wanted = {(item[0], _canonical(item[1])) for item in entities}
        rows = []
        for atom in self.atoms:
            if not include_observed and atom.predicate == "observed":
                continue
            if follow and atom.predicate not in follow:
                continue
            subject = (atom.subject_type, _canonical(atom.subject_keys))
            payload = atom.object_payload or {}
            target = (str(payload.get("type")), _canonical(payload.get("keys") or {}))
            if ((direction in ("outgoing", "both") and subject in wanted)
                    or (direction in ("incoming", "both")
                        and atom.object_kind == "entity_ref" and target in wanted)):
                rows.append(atom)
        return self._result(rows, limit)

    def finding_summaries_for_entities(self, entities, direction, limit):
        if not entities or limit <= 0 or direction == "incoming":
            return [], False
        wanted = {(item[0], _canonical(item[1])) for item in entities}
        grouped = {}
        for atom in self.atoms:
            subject = (atom.subject_type, _canonical(atom.subject_keys))
            if subject not in wanted or atom.predicate != "observed":
                continue
            payload = atom.object_payload or {}
            key = (atom.subject_type, _canonical(atom.subject_keys),
                   str(_payload_field(payload, "finding_kind") or "unknown"),
                   payload.get("method") or None, payload.get("map_id") or None)
            bucket = grouped.setdefault(key, {"atoms": [], "runs": set()})
            bucket["atoms"].append(atom)
            run_uid = _payload_field(payload, "run_uid")
            if run_uid not in (None, ""):
                bucket["runs"].add(str(run_uid))
        summaries = []
        for key, bucket in grouped.items():
            atoms = bucket["atoms"]
            values = []
            xs = []
            ys = []
            for atom in atoms:
                payload = atom.object_payload or {}
                for target, value in (
                    (values, payload.get("value")),
                    (xs, (payload.get("position") or {}).get("x")),
                    (ys, (payload.get("position") or {}).get("y")),
                ):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        target.append(float(value))
            summaries.append({
                "subject_type": key[0], "subject_keys": json.loads(key[1]),
                "finding_kind": key[2], "method": key[3], "map_id": key[4],
                "occurrence_count": len(atoms), "run_count": len(bucket["runs"]),
                "first_at": _instant(min(atom.occurred_at for atom in atoms)),
                "last_at": _instant(max(atom.occurred_at for atom in atoms)),
                "value_count": len(values),
                "value_mean": sum(values) / len(values) if values else None,
                "value_min": min(values) if values else None,
                "value_max": max(values) if values else None,
                "min_x": min(xs) if xs else None, "max_x": max(xs) if xs else None,
                "min_y": min(ys) if ys else None, "max_y": max(ys) if ys else None,
            })
        summaries.sort(key=lambda row: (
            -row["occurrence_count"], row["subject_type"],
            _canonical(row["subject_keys"]), row["finding_kind"],
            row["method"] or "", row["map_id"] or ""))
        return summaries[:limit], len(summaries) > limit

    def claims_for_collections(self, collections, limit):
        wanted = {(item[0], _canonical(item[1]), str(item[2]),
                   item[3] or None, item[4] or None) for item in collections}
        rows = []
        for atom in self.atoms:
            payload = atom.object_payload or {}
            key = (atom.subject_type, _canonical(atom.subject_keys),
                   str(_payload_field(payload, "finding_kind") or "unknown"),
                   payload.get("method") or None, payload.get("map_id") or None)
            if atom.predicate == "observed" and key in wanted:
                rows.append(atom)
        return self._result(rows, limit)

    def claims_for_events(self, events, limit):
        wanted = {(str(item[0]), _instant(item[1]), item[2]) for item in events}
        return self._result([
            atom for atom in self.atoms
            if (atom.event_identity[0], _instant(atom.occurred_at),
                atom.event_identity[1]) in wanted
        ], limit)

    def claims_by_ids(self, claims, limit):
        wanted = {(str(item[0]), _instant(item[1])) for item in claims}
        return self._result([
            atom for atom in self.atoms
            if (atom.id, _instant(atom.occurred_at)) in wanted
        ], limit)


#: Key order per entity type, read once from the live ontology declaration.  `None`
#: until the first entity node asks for it.
_entity_key_order = None


def _declared_key_order(entity_type):
    """The key order one entity type declares, from the LIVE ontology declaration.

    `ledger_explorer._entity` takes its order from the v1 `ENTITY_TYPES` in
    `ledger/vocabulary.py`, and a type the operator declared later is simply ABSENT there.
    The label then falls back to whatever order the payload's JSON happened to use, which
    for `die` puts `x` and `y` first and pushes `mat_id` — the only key that names the
    material — off the front of a two-value label entirely.

    The declaration already answers this: `entities` lists the keys in order, and `die@1`
    lists `mat_id` first.  Read once, cached, and NEVER raised: an absent or unreadable
    declaration leaves every label exactly as it is today rather than taking the walk down
    with it.  The `@version` suffix is stripped the way `ledger/roleframe.py` strips it.
    """
    global _entity_key_order
    if _entity_key_order is None:
        order = {}
        try:
            import paths
            with open(paths.config_path("ontology", "ledger_config.json"),
                      "r", encoding="utf-8") as handle:
                declared = (json.load(handle) or {}).get("entities") or {}
            for name, spec in declared.items():
                keys = [str(key) for key in ((spec or {}).get("keys") or [])]
                if keys:
                    order[str(name).rsplit("@", 1)[0]] = keys
        except Exception:
            order = {}
        _entity_key_order = order
    return _entity_key_order.get(str(entity_type))


def _entity_node(entity_type, keys):
    node = ledger_explorer._entity(entity_type, keys)
    node.update({"node_kind": "entity", "schema_kind": "entity_instance"})
    order = _declared_key_order(entity_type)
    if order:
        # Same shape as the label `_entity` builds, on the declared order instead of the
        # insertion order.  Types the declaration does not name keep the label they have.
        values = [str(keys.get(name)) for name in order
                  if keys.get(name) is not None and str(keys.get(name)) != ""]
        node["label"] = " / ".join(values[:2]) or str(entity_type)
    return node


def _claim_label(atom):
    payload = atom.object_payload or {}
    if atom.predicate == "processed_with":
        detail = " · ".join(str(payload.get(key)) for key in ("step", "recipe")
                            if payload.get(key) not in (None, ""))
        return detail or atom.predicate
    if atom.predicate == "measured":
        metric = payload.get("metric") or "계측"
        value = payload.get("value", payload.get("state", "—"))
        return f"{metric} = {value} {payload.get('unit') or ''}".strip()
    if atom.predicate == "observed":
        return " · ".join(str(payload.get(key)) for key in ("finding_kind", "method")
                          if payload.get(key) not in (None, "")) or atom.predicate
    return atom.predicate


def _claim_node(atom):
    return {
        "id": atom.claim_node_id, "type": "Claim", "node_kind": "claim",
        "schema_kind": "claim_atom", "label": _claim_label(atom),
        "keys": {"id": atom.id}, "predicate": atom.predicate,
        "object_kind": atom.object_kind, "object_payload": atom.object_payload,
        "occurred_at": _instant(atom.occurred_at), "source_who": atom.source_who,
        "source_translator_ver": atom.source_translator_ver,
        "source_raw_ref": atom.source_raw_ref, "supersedes": atom.supersedes,
        "claim_count": 1,
        "predicates": [{"predicate": atom.predicate, "count": 1}],
    }


def _event_node(atom):
    event_id, state = atom.event_identity
    return {
        "id": atom.event_node_id, "type": "Source Event", "node_kind": "event",
        "schema_kind": "source_event", "label": f"{atom.source_who or 'unknown'} · {_instant(atom.occurred_at)}",
        "keys": {"source_event_id": event_id}, "occurred_at": _instant(atom.occurred_at),
        "source_who": atom.source_who, "source_event_state": state,
        "claim_count": 0, "predicates": [],
    }


def _value_label(atom):
    payload = atom.object_payload or {}
    scalar = payload.get("value") if isinstance(payload, dict) else None
    if scalar is not None:
        return str(scalar)
    compact = _canonical(payload)
    return compact if len(compact) <= 72 else compact[:69] + "…"


#: 🔴 THE SAME NAME, ONE LEVEL DOWN -- NOT A TRANSLATION TABLE.
#: v1 translators wrote these at the payload's top level. The v5 runtime cannot: it builds a
#: value payload as exactly `{"value": ...}` plus `{"qualifiers": {...}}`
#: (`ledger/roleframe.py:1172-1183`, hardcoded), so everything a declaration names lands one
#: level down. MEASURED 2026-08-24: 103,729 re-translated void atoms projected as
#: `finding_kind = "defect"` with a null `run_uid`, because the reader looked only on top --
#: the same fact, with the writer and the reader looking in different places.
#:
#: ⚠️ THIS LOOKS UP THE IDENTICAL NAME AND NOTHING ELSE. `position` is deliberately absent:
#: the declaration spells those `inchip_x`/`inchip_y`, and teaching the reader that
#: `inchip_x` means `position.x` would put a coordinate-naming rule in the READ layer -- the
#: shape that breaks "a different vocabulary costs zero lines of code". Empty `position` is a
#: separate, older item (v1's delam atoms are empty there too) and is not this round's.
_QUALIFIED_FIELDS = ("finding_kind", "run_uid", "map_id")


def _payload_field(payload, name):
    """Delegate: the rule lives in `finding_kinds.payload_field`, stated once."""
    return finding_kinds.payload_field(payload, name)


def _finding_point_node(atom):
    payload = atom.object_payload or {}
    position = payload.get("position") or {}
    coordinate = ",".join(str(position[key]) for key in ("x", "y")
                          if position.get(key) is not None)
    qualified = {name: _payload_field(payload, name) for name in _QUALIFIED_FIELDS}
    finding_kind = str(qualified["finding_kind"] or "defect")
    return {
        "id": atom.finding_point_node_id,
        "type": "Finding Point",
        "node_kind": "point",
        "schema_kind": "terminal_finding_point_projection",
        "label": f"{finding_kind}{f' @ {coordinate}' if coordinate else ''}",
        "keys": {
            "finding_kind": finding_kind,
            "run_uid": qualified["run_uid"],
            "map_id": qualified["map_id"],
            "position": position,
        },
        "finding_kind": finding_kind,
        "occurred_at": _instant(atom.occurred_at),
        "value": payload.get("value"),
        "evidence_claim_id": atom.claim_node_id,
        "source_raw_ref": atom.source_raw_ref,
        "expansion": "explicit_seed_to_wafer_only",
        "claim_count": 1,
        "predicates": [{"predicate": "observed", "count": 1}],
    }


def _finding_collection_node(summary):
    node_id = finding_collection_node_id(
        summary["subject_type"], summary["subject_keys"],
        summary["finding_kind"], summary.get("method"), summary.get("map_id"))
    qualifiers = [summary["finding_kind"]]
    qualifiers.extend(str(value) for value in (
        summary.get("method"), summary.get("map_id")) if value not in (None, ""))
    return {
        "id": node_id, "type": "Finding Collection", "node_kind": "collection",
        "schema_kind": "finding_collection_projection",
        "label": f"{' · '.join(qualifiers)} ({summary['occurrence_count']:,})",
        "keys": {
            "subject_type": summary["subject_type"],
            "subject_keys": summary["subject_keys"],
            "finding_kind": summary["finding_kind"],
            "method": summary.get("method"), "map_id": summary.get("map_id"),
        },
        "finding_kind": summary["finding_kind"],
        "method": summary.get("method"), "map_id": summary.get("map_id"),
        "occurrence_count": summary["occurrence_count"],
        "run_count": summary["run_count"],
        "aggregates": {
            "count": summary["occurrence_count"],
            "run_count": summary["run_count"],
            "value_count": summary.get("value_count", 0),
            "value_mean": summary.get("value_mean"),
            "value_min": summary.get("value_min"),
            "value_max": summary.get("value_max"),
        },
        "spatial": {
            "map_id": summary.get("map_id"),
            "bbox": {
                "min_x": summary.get("min_x"), "max_x": summary.get("max_x"),
                "min_y": summary.get("min_y"), "max_y": summary.get("max_y"),
            },
        },
        "first_at": summary["first_at"], "last_at": summary["last_at"],
        "claim_count": summary["occurrence_count"],
        "predicates": [{"predicate": "observed",
                        "count": summary["occurrence_count"]}],
    }


def _quantity_node(model_name, quantity, model=None):
    """A physical quantity, SYNTHESIZED from `mechanism_models.json`.

    It is not an entity sitting in the ledger and it costs no query: the declaration is a
    config file of tens of nodes that `mechanism_gate` loads once and caches.  `model` is
    the loaded `mechanism_gate.Model` when the declaration still carries it — a node id
    bookmarked before the modeller deleted a model still decodes and still names itself.
    """
    node = {
        "id": quantity_node_id(model_name, quantity),
        "type": "Quantity", "node_kind": "quantity",
        "schema_kind": "mechanism_quantity_projection",
        "label": f"{quantity} · {model_name}",
        "keys": {"model": model_name, "quantity": quantity},
        "quantity": quantity, "model": model_name,
        "basis": mechanism_gate.CONFIG_FILENAME,
        "claim_count": 0, "predicates": [],
    }
    if model is not None:
        node.update({"model_role": model.role, "finding_kind": model.finding_kind,
                     "is_target": quantity == model.target})
    return node


def _payload_paths(payload, prefix=""):
    """Dotted leaf paths of one claim payload — the spelling bindings are keyed by."""
    if isinstance(payload, dict):
        for key in payload:
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _payload_paths(payload[key], child)
    elif prefix:
        yield prefix


def _bound_quantities(mechanism, atom):
    """The declared `(model, quantity, binding key)` triples one claim's payload binds to.

    The lookup is `mechanism_gate`'s own `nodes_for`, including its two accepted binding
    spellings and their precedence, so this projection never re-decides what a binding
    means.  A quantity is emitted once per usable model that declares it, which is how
    `bond_pressure` reaches both the void and the delam model without the two becoming
    one node.
    """
    out, seen = [], set()
    for path in _payload_paths(atom.object_payload or {}):
        quantities, binding_key = mechanism.nodes_for(f"{atom.predicate}:{path}")
        for quantity in quantities:
            for model in mechanism.models:
                if not model.usable or quantity not in model.nodes:
                    continue
                if (model.name, quantity) in seen:
                    continue
                seen.add((model.name, quantity))
                out.append((model, quantity, binding_key))
    return out


def _enrich_action_node(action):
    return enrichment_actions.action_node(action)


def _edge(edge_type, source, target, *, original_predicate=None):
    edge_id = f"ledger-evidence-edge:v1:{_token([edge_type, source, target])}"
    return {
        "id": edge_id, "source": source, "target": target,
        "predicate": edge_type, "predicate_label": edge_type,
        "original_predicate": original_predicate, "witnesses": 1,
        "rank": None, "basis": None, "sources": [], "qualifiers": {},
    }


def _signed_seeds(start):
    """`start` widens from one id to a signed SET without leaving its argument slot.

    🔴 THREE STATES, AND THEY ARE THREE.
        +        observed
        −        looked for and NOT found — a control
        unlisted never examined, which is NOT the same fact as −

    Nothing here promotes an unlisted subject to a control.  「미검사」 and 「봤는데 안
    났다」 answer different questions and only the second can rule a factor out, so an
    empty `negative` means the contrast was never run rather than that every control came
    back clean.  A single id keeps working and is one positive seed.
    """
    if isinstance(start, dict):
        positive = [str(item) for item in (start.get("positive") or [])]
        negative = [str(item) for item in (start.get("negative") or [])]
    else:
        positive, negative = [str(start)], []
    signs = {}
    for sign, group in ((1, positive), (-1, negative)):
        for item in group:
            if signs.get(item, sign) != sign:
                raise ValueError(
                    "a seed cannot be both observed and a control: " + item)
            signs[item] = sign
    if not signs:
        raise ValueError("start must name at least one seed")
    return signs


def _reach(nodes, edges, seed_signs):
    """Signed reach of every walked node from the signed seeds.  Pure — no query.

    TWO RULES AND NO THIRD.
      * The FIRST hop does not divide by degree.  Dividing there makes a factor that is
        equally common on both sides come out non-zero purely because a marked subject
        happens to carry a different number of claims than a control does.
      * Every hop after that divides by the number of nodes it FORWARDS TO, so a hub splits
        its reach instead of flooding the ranking.
      * There is NO damping constant, as a default or otherwise.  A decay factor is an
        artefact and it would end up being the thing that decides the answer.

    🔴 IT USED TO DIVIDE BY THE FULL DEGREE, WHICH IS A LENGTH DECAY WEARING ANOTHER NAME.
    A node's undirected degree counts the neighbour it was REACHED FROM, so a node in a pure
    chain has degree 2 and halved its carry at a place where nothing forks.  MEASURED on the
    chain S-B-C-D: 1.0, 0.5, 0.25 - the exact geometric decay the third rule above forbids,
    arrived at without a constant.  A 3-hop process-history factor was therefore ranked below
    a 1-hop one for its distance alone, which is the opposite of what an R&D screen is for.

    Forward degree is `degree - 1` and not the count of not-yet-seen neighbours, deliberately:
    the unseen count depends on the order the BFS happens to mark siblings, so the same graph
    would score differently between runs.  Degree is a property of the graph.

    Returns `(reach, parents)` where reach is `node -> [from_positive, from_negative]` and
    parents is `seed -> {node: predecessor}`, so an evidence path is rebuilt on demand
    instead of keeping one path per node per seed alive for the whole walk.
    """
    adjacency = {}
    for edge in edges:
        adjacency.setdefault(edge["source"], set()).add(edge["target"])
        adjacency.setdefault(edge["target"], set()).add(edge["source"])
    reach, parents = {}, {}
    for seed, sign in seed_signs.items():
        if seed not in nodes:
            continue
        slot = 0 if sign > 0 else 1
        trail = parents.setdefault(seed, {})
        seen = {seed}
        queue = deque([(seed, 1.0)])
        while queue:
            node, carried = queue.popleft()
            neighbours = adjacency.get(node)
            if not neighbours:
                continue
            forward = max(1, len(neighbours) - 1)     # exclude the way it came in
            share = carried if node == seed else carried / forward
            for nxt in neighbours:
                if nxt in seen:
                    continue
                seen.add(nxt)
                trail[nxt] = node
                reach.setdefault(nxt, [0.0, 0.0])[slot] += share
                queue.append((nxt, share))
    return reach, parents


def _rank_layers(items):
    """Layer candidates by DOMINANCE, never by one number.

    A dominates B when A was reached at least as much from the marked subjects and at most
    as much from the controls, strictly better on one of the two.  Two candidates that each
    beat the other on one axis are not ranked against each other at all — they differ in
    KIND, not in degree — and both stay in the top set.  The answer is a set, and 「1등」 is
    a question this function refuses to answer when the evidence does not.

    [SCALE] Layering is O(n log n) over the two axes rather than the pairwise sweep: a
    lineage answer can collect the whole node budget, where the pairwise form is n³.
    """
    ordered = sorted(items, key=lambda item: (-item["reach"][0], item["reach"][1]))
    floors, layers, index = [], [], 0
    while index < len(ordered):
        stop, coordinate = index, ordered[index]["reach"]
        while stop < len(ordered) and ordered[stop]["reach"] == coordinate:
            stop += 1
        # Everything already placed has at least this observed-reach, so this group is
        # dominated by exactly those layers already holding a smaller control-reach.
        layer = bisect.bisect_right(floors, coordinate[1])
        if layer == len(floors):
            floors.append(coordinate[1])
            layers.append([])
        else:
            floors[layer] = coordinate[1]
        for item in ordered[index:stop]:
            item["rank"] = layer + 1
            item["tied"] = stop - index > 1
            layers[layer].append(item)
        index = stop
    for layer in layers:
        distinct = {tuple(item["reach"]) for item in layer}
        for item in layer:
            item["incomparable"] = len(distinct) > 1
    return layers


def _evidence(nodes, parents, seed_signs, node_id):
    """The hop-by-hop path from every seed that reached this candidate.

    Each hop carries the ref the projection already holds — the claim atom's raw source for
    a ledger hop, the declaration file for a synthesized mechanism hop — rather than a
    second provenance vocabulary invented for the ranking.
    """
    trails = []
    for seed, trail in parents.items():
        if node_id not in trail:
            continue
        path, cursor = [], node_id
        while cursor is not None:
            path.append(cursor)
            cursor = trail.get(cursor)
        path.reverse()
        trails.append({
            "seed": seed,
            "sign": "+" if seed_signs[seed] > 0 else "-",
            "hops": [{
                "id": item,
                "node_kind": nodes[item].get("node_kind"),
                "label": nodes[item].get("label"),
                "atom": (nodes[item].get("keys") or {}).get("id"),
                "ref": (nodes[item].get("source_raw_ref")
                        or nodes[item].get("basis")),
            } for item in path],
        })
    return trails


def _propagation(nodes, edges, seed_signs, collect, complete):
    """Rank the collected node kind by signed reach.  ONE mechanism, two configurations.

    🔴 `collect` chooses the POPULATION and nothing else.  The walk, the propagation and
    the domination are identical whether the answer wanted is a cause candidate
    (`quantity`) or a common ancestor in lineage (`entity`); there is deliberately no
    branch on which one was asked for, because a fork here would mean the two applications
    are not the same question after all.  A new application is a new value of this
    argument, not new code.

    🔴 NO NUMBERS LEAVE.  Reach decides the rank and the top set and then stays inside:
    the ranking is the machine's judgement, and reading it is the owner's.  What answers
    「이 후보는 대조군에서 한 번도 안 닿았다」 is the SIGN on each evidence trail, which
    every rank now carries — not the magnitude, which reads like a probability and is not
    one.
    """
    negatives = sum(1 for sign in seed_signs.values() if sign < 0)
    block = {
        "collect": collect,
        "state": "not_requested",
        # 🔴 With no control seed the second axis was never examined.  That is NOT
        # 「controls were walked and the factor was absent from them」, and reporting it as
        # a zero would turn 미검사 into a finding.
        "contrast": "contrasted" if negatives else "unexamined",
        # 🔴 A candidate the budget stopped the walk short of is UNEXAMINED, not absent.
        # Measured 2026-08-23: four lot seeds at the default node cap truncate, so this is
        # reachable today rather than a someday case, and a rank read off a truncated graph
        # is provisional.
        "complete": complete,
        "ranked": [],
        "top_set": [],
        "message": None,
    }
    if collect is None:
        return block
    reach, parents = _reach(nodes, edges, seed_signs)
    collected = [{
        "id": node["id"], "type": node.get("type"), "label": node.get("label"),
        "reach": reach.get(node["id"], [0.0, 0.0]),
    } for node in nodes.values() if node.get("node_kind") == collect]
    if not collected:
        block["state"] = "empty"
        block["message"] = "이 걷기가 %s 노드에 닿지 않았습니다" % collect
        return block
    layers = _rank_layers(collected)
    block["state"] = "ranked"
    block["ranked"] = [{
        "id": item["id"], "type": item["type"], "label": item["label"],
        "rank": item["rank"], "top": item["rank"] == 1,
        "tied": item["tied"], "incomparable": item["incomparable"],
        # 🔴 The trails go on EVERY rank, not only the top set.  「reached from the marked
        # subjects and never from a control」 is a different answer from 「not first」, and
        # what carries that distinction is `evidence[].sign` — one `+`/`−` per seed that
        # reached this candidate.  The magnitude does NOT travel: a reader who sees 0.0625
        # reads it as 6% and hands the judgement back to the machine, and it is not a
        # probability.  The sign is the finding; the size is an artefact of the walk.
        #
        # Measured 2026-08-23 before deciding whether to cut: at the node cap (929 nodes,
        # 5 seeds, 90 ranked items, 653 hop entries) the block is 285 KB inside a 2,991 KB
        # response — 10% of what the caller already receives — and trails stay 5 hops long
        # because a BFS trail is bounded by the graph's DIAMETER rather than by `hops`.
        # So nothing is truncated here and there is no cap to name.
        "evidence": _evidence(nodes, parents, seed_signs, item["id"]),
    } for layer in layers for item in layer]
    block["top_set"] = [item["id"] for item in layers[0]]
    return block


def _seed_node(seed_id, seed_ref, models_by_name, action_lookup):
    """Build the depth-0 node for ONE seed.

    Extracted verbatim so a signed seed SET runs the same construction per member;
    the branches and their spellings are unchanged.
    """
    if seed_ref["kind"] == "entity":
        seed_node = _entity_node(seed_ref["type"], seed_ref["keys"])
    elif seed_ref["kind"] == "event":
        seed_node = {
            "id": seed_id, "type": "Source Event", "node_kind": "event",
            "schema_kind": "source_event", "label": f"Event {seed_ref['event_id'][:8]}",
            "keys": {"source_event_id": seed_ref["event_id"]},
            "occurred_at": _instant(seed_ref["occurred_at"]),
            "source_event_state": seed_ref["event_state"], "claim_count": 0,
            "predicates": [],
        }
    elif seed_ref["kind"] == "claim":
        seed_node = {
            "id": seed_id, "type": "Claim", "node_kind": "claim",
            "schema_kind": "claim_atom", "label": f"Claim {seed_ref['claim_id'][:8]}",
            "keys": {"id": seed_ref["claim_id"]}, "claim_count": 0, "predicates": [],
        }
    elif seed_ref["kind"] == "point":
        seed_node = {
            "id": seed_id, "type": "Finding Point",
            "node_kind": "point", "schema_kind": "terminal_finding_point_projection",
            "label": f"Finding point {seed_ref['claim_id'][:8]}",
            "keys": {"claim_id": seed_ref["claim_id"]},
            "occurred_at": _instant(seed_ref["occurred_at"]),
            "expansion": "explicit_seed_to_wafer_only",
            "claim_count": 0, "predicates": [],
        }
    elif seed_ref["kind"] == "collection":
        seed_node = {
            "id": seed_id, "type": "Finding Collection", "node_kind": "collection",
            "schema_kind": "finding_collection_projection",
            "label": " · ".join(filter(None, [
                seed_ref["finding_kind"], seed_ref.get("method"),
                seed_ref.get("map_id")])),
            "keys": {
                "subject_type": seed_ref["type"], "subject_keys": seed_ref["keys"],
                "finding_kind": seed_ref["finding_kind"],
                "method": seed_ref.get("method"), "map_id": seed_ref.get("map_id"),
            },
            "finding_kind": seed_ref["finding_kind"],
            "method": seed_ref.get("method"), "map_id": seed_ref.get("map_id"),
            "claim_count": 0, "predicates": [],
        }
    elif seed_ref["kind"] == "quantity":
        seed_node = _quantity_node(seed_ref["model"], seed_ref["quantity"],
                                   models_by_name.get(seed_ref["model"]))
    elif seed_ref["kind"] == "action":
        action = action_lookup.action_for_ref(seed_ref) if action_lookup else None
        if action is not None:
            seed_node = _enrich_action_node(action)
        else:
            seed_node = {
                "id": seed_id, "type": "Enrich Action", "node_kind": "action",
                "schema_kind": "enrich_action_projection",
                "label": f"{seed_ref['rule_name']} · 현재 상태 확인 불가",
                "keys": {
                    "rule": seed_ref["rule_name"],
                    "contract_version": seed_ref["version"],
                    "scope": seed_ref["scope"],
                    "decision_key": seed_ref.get("decision_key"),
                },
                "state": "projection_unavailable", "projection": True,
                "terminal_in_automatic_walk": True,
                "claim_count": 0, "predicates": [],
            }
    else:
        seed_node = {
            "id": seed_id, "type": "Value", "node_kind": "value",
            "schema_kind": "claim_value", "label": "Value",
            "keys": {"claim_id": seed_ref["claim_id"]}, "claim_count": 0,
            "predicates": [],
        }
    return seed_node


#: The node kinds that summary mode folds away. Asking to collect one of these is asking
#: for the inside of the fold, so the walk unfolds rather than answering an empty set.
#: MEASURED 2026-08-24: with the fold on these two rank 0 and 1; with it off, 30 and 31.
#: `claim` left this set on 2026-08-25: there is no claim node to unfold to any more.
FOLDED_KINDS = frozenset({"point"})

#: Kinds that stopped existing when one fact became one edge. Collecting one of these
#: would return an empty ranking that reads exactly like "nothing was found", which is
#: the confusion this module refuses everywhere else.
RETIRED_NODE_KINDS = frozenset({"claim", "event"})




def subgraph(seed_id, lookup, *, hops=DEFAULT_HOPS, direction="both",
             include_values=True, node_limit=DEFAULT_NODE_LIMIT,
             edge_limit=DEFAULT_EDGE_LIMIT, observation_mode="summary",
             action_lookup=None, collect=None, follow=None):
    """Return a typed evidence subgraph from any public node id, or from a signed SET.

    `seed_id` is one opaque id as before, or `{"positive": [ids], "negative": [ids]}`.
    `collect` names one node kind and turns the walk into a ranked answer over it.  Both
    are optional and neither changes what a single-seed caller already receives.
    """
    seed_signs = _signed_seeds(seed_id)
    seed_refs = {item: decode_node_id(item) for item in seed_signs}
    primary = next(iter(seed_signs))
    if collect is not None:
        collect = str(collect).strip().lower()
        if collect not in NODE_KINDS:
            raise ValueError("collect must be one of " + ", ".join(NODE_KINDS))
    hops = max(1, min(int(hops), MAX_HOPS))
    node_limit = max(10, min(int(node_limit), MAX_NODE_LIMIT))
    edge_limit = max(20, min(int(edge_limit), MAX_EDGE_LIMIT))
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError("direction must be outgoing, incoming, or both")
    if observation_mode not in {"summary", "claims"}:
        raise ValueError("observation_mode must be summary or claims")
    if collect in RETIRED_NODE_KINDS:
        raise ValueError(
            f"{collect!r} is no longer a node kind -- a claim is an edge and its source event "
            "is an edge attribute, so this can never rank anything")
    # 🔴 `collect` NAMES WHAT THE CALLER WANTS, AND THE FOLD IS AN INTERNAL ECONOMY.
    # Summary mode replaces a wafer's observations with ONE collection node, so the point
    # and claim nodes are never emitted at all -- not filtered late, not walked past:
    # never made. MEASURED 2026-08-24 on `SYN-BW-K1-201-01`: `collect=point` ranked 0 with
    # the fold on and 30 with it off, and `collect=claim` 1 against 31. A caller asking for
    # a kind that only exists behind the fold was answered "none", which is a false
    # statement about the data rather than a limit of the request.
    #
    # So the fold yields to the request. It stays on for every other call -- thirty
    # observations collapsing to one node is why a wafer's graph is readable at all -- and
    # unfolds only when the collected kind lives inside it. This is not a second route and
    # not a flag the client passes: the client declares what it collects, which is the
    # contract the marking rule asks for.
    #
    # ⚠️ THE NODE BUDGET IS REAL AND IS ANSWERED WITH `truncated`, NOT WITH SILENCE. A wafer
    # with thousands of observations will hit the cap once unfolded; the response says so.
    # Answering 0 because the fold was cheaper is the behaviour this replaces.
    if collect in FOLDED_KINDS and observation_mode == "summary":
        observation_mode = "claims"
    claim_limit = min(MAX_CLAIM_SCAN, max(200, edge_limit * 2))
    # Declared, not queried.  An absent or broken declaration yields no models and no
    # bindings, so the projection simply carries no Quantity nodes — the same «state, not
    # exception» rule `mechanism_gate.load` follows for every other consumer.
    mechanism = mechanism_gate.load()
    models_by_name = {model.name: model for model in mechanism.models if model.usable}

    nodes = {}
    refs = {}
    depths = {}
    edges = {}
    atom_cache = {}
    action_claims_seen = set()
    node_cut = edge_cut = claim_cut = action_cut = depth_cut = False
    #: nodes that have spent the node budget -- see `_spends_budget` below
    budgeted = 0
    budgeted_edges = 0
    claims_scanned = 0
    actions_scanned = 0

    #: 🔴 THE EXEMPTION IS GONE, BECAUSE THE PLUMBING IS NO LONGER MADE OF NODES.
    #: Claims, events and values-as-connectors used to crowd out the answer, so they
    #: were excluded from the budget. Now a claim IS an edge and an event IS an edge
    #: attribute, so everything still in `nodes` is a thing in the world and the
    #: budget can go back to counting all of it. Keeping the carve-out would have let
    #: measurement nodes grow without limit while the cap claimed to hold.
    def add_node(node, ref, depth):
        nonlocal node_cut, budgeted
        node_id = node["id"]
        if node_id in nodes:
            if depth < depths[node_id]:
                depths[node_id] = depth
            nodes[node_id].update({k: v for k, v in node.items() if v is not None})
            return True
        # 🔴 THE MEASUREMENT NODE STILL RIDES FREE, and the reason changed. It is no longer
        # plumbing -- it is the fact itself -- but there are 847 of them on this one seed
        # against 149 entities, so counting them saturates the cap and the answer falls out:
        # MEASURED, quantity ranked drops 9 -> 4 and the recipe's trail disappears entirely.
        # Whether a measurement should share the entity budget is a ruling, not a default.
        if node.get("node_kind") != "value":
            if budgeted >= node_limit:
                node_cut = True
                return False
            budgeted += 1
        nodes[node_id] = node
        refs[node_id] = ref
        depths[node_id] = depth
        return True

    def add_edge(row):
        nonlocal edge_cut, budgeted_edges
        if row["source"] not in nodes or row["target"] not in nodes:
            return False
        if row["id"] in edges:
            return True
        if budgeted_edges >= edge_limit:
            edge_cut = True
            return False
        budgeted_edges += 1
        edges[row["id"]] = row
        return True

    #: 🔴 ONE ATOM BECOMES ONE EDGE, IN THE SAME BFS LEVEL IT WAS FETCHED IN.
    #: Until 2026-08-25 a fetched atom was parked as a claim NODE at depth+1 and only expanded
    #: on the next iteration, so its subject and object landed at depth+2 -- one assertion cost
    #: two levels of the walk. MEASURED: a recipe sat 5 hops away as
    #: [entity, claim, entity, claim, entity], and two of those five were claims. Not building
    #: the node is not enough on its own; the STAGING is what spends the hop, so the expansion
    #: happens here, where the atom arrives.
    #:
    #: The claim itself is not lost, it stops being a place you walk THROUGH: its id, time,
    #: source and qualifiers ride on the edge, which is where "who said this and when" belongs
    #: in a graph whose nodes are things in the world.
    def _claim_edge(atom, source_id, target_id, edge_type):
        edge = _edge(edge_type, source_id, target_id,
                     original_predicate=atom.predicate)
        edge["claim_id"] = atom.id
        edge["occurred_at"] = _instant(atom.occurred_at)
        edge["source_who"] = atom.source_who
        edge["basis"] = atom.source_raw_ref
        edge["qualifiers"] = dict((atom.object_payload or {}).get("qualifiers") or {})
        return edge

    def _expand_atom(atom, depth, frontier_entities):
        """Materialise one atom's far side and the single edge that carries it."""
        subject_id = ledger_explorer.entity_id(atom.subject_type, atom.subject_keys)
        if subject_id not in nodes:
            subject = _entity_node(atom.subject_type, atom.subject_keys)
            if not add_node(subject, decode_node_id(subject["id"]), depth):
                return
        payload = atom.object_payload or {}
        if atom.object_kind == "entity_ref" and payload.get("type") and payload.get("keys"):
            target = _entity_node(payload["type"], payload["keys"])
            if add_node(target, decode_node_id(target["id"]), depth + 1):
                add_edge(_claim_edge(atom, subject_id, target["id"], atom.predicate))
            return
        if atom.predicate == "observed" and atom.object_kind == "value":
            point = _finding_point_node(atom)
            point_ref = decode_node_id(point["id"])
            point_ref["expandable"] = False
            if add_node(point, point_ref, depth + 1):
                add_edge(_claim_edge(atom, subject_id, point["id"], "observed"))
            return
        if atom.object_kind is not None and include_values:
            # 🔴 THE MEASUREMENT NODE: claim, value and event collapsed into the one thing the
            # question is about -- "this subject measured this". It keeps its own node because
            # a reader marks a measurement and because the mechanism bindings hang off it.
            value_id = value_node_id(atom.id, atom.occurred_at)
            value = {
                "id": value_id, "type": "Value", "node_kind": "value",
                "schema_kind": "claim_value", "label": _value_label(atom),
                "keys": payload, "claim_count": 1, "predicates": [],
                "occurred_at": _instant(atom.occurred_at), "source_who": atom.source_who,
                # the measurement node absorbed the claim, so it carries the claim's fields
                # too -- `tabular_projection` types payload leaves under this exact scope, and
                # the export's three sheets are a contract with Spotfire and Excel.
                "predicate": atom.predicate, "object_kind": atom.object_kind,
                "object_payload": payload, "source_raw_ref": atom.source_raw_ref,
            }
            if add_node(value, decode_node_id(value_id), depth + 1):
                add_edge(_claim_edge(atom, subject_id, value_id, atom.predicate))
                for model, quantity, binding_key in _bound_quantities(mechanism, atom):
                    node = _quantity_node(model.name, quantity, model)
                    if not add_node(node, decode_node_id(node["id"]), depth + 2):
                        continue
                    edge = _edge("binding", value_id, node["id"],
                                 original_predicate=atom.predicate)
                    edge["basis"] = mechanism_gate.CONFIG_FILENAME
                    edge["qualifiers"] = {"binding_key": binding_key}
                    add_edge(edge)

    for item, ref in seed_refs.items():
        add_node(_seed_node(item, ref, models_by_name, action_lookup), ref, 0)

    for depth in range(hops):
        frontier_ids = [node_id for node_id, seen_depth in depths.items()
                        if seen_depth == depth]
        if not frontier_ids:
            break
        remaining = claim_limit - claims_scanned
        if remaining <= 0:
            claim_cut = True
            break
        entity_refs = [refs[item] for item in frontier_ids
                       if refs[item]["kind"] == "entity"]
        point_refs = [refs[item] for item in frontier_ids
                      if refs[item]["kind"] == "point"
                      and refs[item].get("expandable", False)]
        event_refs = [refs[item] for item in frontier_ids
                      if refs[item]["kind"] == "event"]
        collection_refs = [refs[item] for item in frontier_ids
                           if refs[item]["kind"] == "collection"
                           and refs[item].get("expandable", False)]
        quantity_refs = [refs[item] for item in frontier_ids
                         if refs[item]["kind"] == "quantity"]
        finding_refs = [refs[item] for item in frontier_ids
                        if refs[item]["kind"] == "collection"]
        fetched = []

        full_entity_refs = [item for item in entity_refs
                            if not item.get("observation_only", False)]
        if full_entity_refs and remaining > 0:
            batch, cut = lookup.claims_for_entities(
                [(item["type"], item["keys"]) for item in full_entity_refs],
                direction, remaining,
                include_observed=observation_mode == "claims", follow=follow)
            claims_scanned += len(batch); remaining -= len(batch); claim_cut |= cut
            fetched.extend(batch)
            frontier_entities = {item["id"] for item in full_entity_refs}
            for atom in batch:
                atom_cache[atom.claim_node_id] = atom
                _expand_atom(atom, depth, frontier_entities)

        if entity_refs and observation_mode == "summary" and remaining > 0:
                summaries, cut = lookup.finding_summaries_for_entities(
                    [(item["type"], item["keys"]) for item in entity_refs],
                    direction, min(remaining, max(1, node_limit - budgeted + 1)))
                claim_cut |= cut
                frontier_entities = {item["id"] for item in entity_refs}
                for summary in summaries:
                    collection = _finding_collection_node(summary)
                    ref = decode_node_id(collection["id"])
                    # A collection reached from an Entity is deliberately folded.
                    # Passing its opaque id back as a new seed is the explicit unfold.
                    ref["expandable"] = False
                    if not add_node(collection, ref, depth + 1):
                        continue
                    subject_id = ledger_explorer.entity_id(
                        summary["subject_type"], summary["subject_keys"])
                    if subject_id in frontier_entities:
                        edge = _edge("has_findings", subject_id, collection["id"],
                                     original_predicate="observed")
                        edge["witnesses"] = summary["occurrence_count"]
                        add_edge(edge)

        if point_refs and remaining > 0:
            batch, cut = lookup.claims_by_ids([
                (item["claim_id"], item["occurred_at"]) for item in point_refs
            ], remaining)
            claims_scanned += len(batch); remaining -= len(batch); claim_cut |= cut
            frontier_points = {item["id"] for item in point_refs}
            for atom in batch:
                point = _finding_point_node(atom)
                point_ref = decode_node_id(point["id"])
                point_ref["expandable"] = False
                add_node(point, point_ref, depth)
                if point["id"] not in frontier_points:
                    continue
                wafer = _entity_node(atom.subject_type, atom.subject_keys)
                wafer_ref = decode_node_id(wafer["id"])
                wafer_ref["observation_only"] = True
                if add_node(wafer, wafer_ref, depth + 1):
                    add_edge(_edge("on_subject", point["id"], wafer["id"],
                                   original_predicate="observed"))

        if collection_refs and remaining > 0:
            summaries, _ = lookup.finding_summaries_for_entities(
                [(item["type"], item["keys"]) for item in collection_refs],
                "outgoing", MAX_NODE_LIMIT)
            frontier_collections = {item["id"] for item in collection_refs}
            for summary in summaries:
                collection = _finding_collection_node(summary)
                if collection["id"] in frontier_collections:
                    add_node(collection, refs[collection["id"]], depth)
            batch, cut = lookup.claims_for_collections([(
                item["type"], item["keys"], item["finding_kind"],
                item.get("method"), item.get("map_id"))
                for item in collection_refs], remaining)
            claims_scanned += len(batch); remaining -= len(batch); claim_cut |= cut
            fetched.extend(batch)
            for atom in batch:
                payload = atom.object_payload or {}
                collection_id = finding_collection_node_id(
                    atom.subject_type, atom.subject_keys,
                    _payload_field(payload, "finding_kind"),
                    payload.get("method"), payload.get("map_id"))
                if collection_id in frontier_collections:
                    point = _finding_point_node(atom)
                    point_ref = decode_node_id(point["id"])
                    point_ref["expandable"] = False
                    if add_node(point, point_ref, depth + 1):
                        add_edge(_edge("contains", collection_id, point["id"],
                                       original_predicate="observed"))

        # 🔴 Drawing what is already written.  Every model declares the `finding_kind`
        # it is a model OF and the `target` it terminates in, so the link from an observed
        # finding to that target is a READING of the declaration rather than a new
        # assertion — the same class of edge as `binding`, keyed on `finding_kind` where
        # that one is keyed on `bindings`.  No extra atom is read: the kind is already on
        # the collection.
        #
        # 🔴 One finding reaching TWO models is the point, not a collision.  A void
        # attaches to `void_formation.void` AND to `void_observation_bias.void_observed`,
        # and keeping them apart is how a real formation path stays distinguishable from
        # something that only looks like one — the split `mechanism_gate` is built around.
        for item in finding_refs:
            for model in models_by_name.values():
                if model.finding_kind != item["finding_kind"]:
                    continue
                node = _quantity_node(model.name, model.target, model)
                if not add_node(node, decode_node_id(node["id"]), depth + 1):
                    continue
                edge = _edge("finding", item["id"], node["id"],
                             original_predicate="observed")
                edge["basis"] = mechanism_gate.CONFIG_FILENAME
                edge["qualifiers"] = {"finding_kind": item["finding_kind"],
                                      "model": model.name, "role": model.role}
                add_edge(edge)

        # Mechanism edges are DECLARED structure rather than ledger evidence, so they cost
        # no claim budget and ignore `direction` the way the other structural edges do.
        # Reachability is undirected; the emitted edge keeps the declaration's own `dir`.
        # Traversal never leaves the model the frontier quantity belongs to.
        for item in quantity_refs:
            model = models_by_name.get(item["model"])
            if model is None:
                continue
            for head, outgoing in model.adjacency.items():
                for spec in outgoing:
                    tail = spec["to"]
                    if item["quantity"] not in (head, tail):
                        continue
                    endpoints = {}
                    for name in (head, tail):
                        node = _quantity_node(model.name, name, model)
                        if add_node(node, decode_node_id(node["id"]),
                                    depth if name == item["quantity"] else depth + 1):
                            endpoints[name] = node["id"]
                    if len(endpoints) != 2:
                        continue
                    edge = _edge("mechanism", endpoints[head], endpoints[tail])
                    edge["basis"] = mechanism_gate.CONFIG_FILENAME
                    edge["qualifiers"] = {"dir": spec.get("dir"), "model": model.name}
                    add_edge(edge)

        # 🔴 THE SOURCE EVENT IS NO LONGER A NODE EITHER. It was provenance for a claim, and
        # a claim is now an edge, so "which run asserted this" is an edge attribute
        # (`source_who`, `occurred_at`, `basis`) rather than a place in the graph. An event
        # seed therefore expands nothing -- there is no claim node left for it to point at.
        if event_refs and remaining > 0:
            batch, cut = lookup.claims_for_events([
                (item["event_id"], item["occurred_at"], item["event_state"])
                for item in event_refs], remaining)
            claims_scanned += len(batch); remaining -= len(batch); claim_cut |= cut
            fetched.extend(batch)
            for atom in batch:
                atom_cache[atom.claim_node_id] = atom
                _expand_atom(atom, depth, set())

        # 🔴 THE CLAIM FRONTIER STAGE IS GONE. It used to sit here: park a fetched atom as a
        # claim node, wait for the next BFS level, then unfold its subject and object. That
        # staging is what made one assertion cost two hops. Atoms are now expanded where they
        # are fetched (`_expand_atom`), so there is nothing left to revisit and no claim node
        # to revisit it as.
        # Enrich Actions are reached FROM evidence Claims, never injected beside the
        # graph as an unrelated list.  The lookup reuses validated Enrichment rules and
        # materialized derived rows; it does not execute reference SQL here.  Action
        # nodes are terminal during this automatic walk, but their opaque id is a valid
        # next seed for explicit inspection.
        if action_lookup is not None and fetched:
            action_atoms = []
            for atom in fetched:
                if atom.claim_node_id in action_claims_seen:
                    continue
                action_claims_seen.add(atom.claim_node_id)
                action_atoms.append(atom)
            action_budget = min(node_limit - budgeted, edge_limit - budgeted_edges)
            if not action_atoms:
                pass
            elif action_budget <= 0:
                action_cut = True
            else:
                action_rows, cut = action_lookup.actions_for_claims(
                    action_atoms, action_budget)
                actions_scanned += len(action_rows)
                action_cut |= cut
                for action, anchor_claim_id in action_rows:
                    anchor_depth = depths.get(anchor_claim_id)
                    if anchor_depth is None or anchor_depth >= hops:
                        depth_cut = True
                        continue
                    action_node = _enrich_action_node(action)
                    action_ref = decode_node_id(action_node["id"])
                    # A reached action is deliberately folded/terminal.  Re-seeding its
                    # id is the explicit expansion act, just like a Finding Collection.
                    action_ref["expandable"] = False
                    if not add_node(action_node, action_ref, anchor_depth + 1):
                        continue
                    edge = _edge(
                        "needs_enrichment", anchor_claim_id, action_node["id"],
                        original_predicate=nodes[anchor_claim_id].get("predicate"))
                    edge["qualifiers"] = {
                        "rule": action.rule_name,
                        "state": action.state,
                        "action_kind": action.action_kind,
                    }
                    add_edge(edge)

        if any(depth_value > hops for depth_value in depths.values()):
            depth_cut = True
        if claim_cut or (node_cut and edge_cut):
            break

    if any(depth == hops for depth in depths.values()):
        depth_cut = True
    # 🔴 ONE EDGE IS ONE CLAIM, so the predicate is read off the edge rather than off a node
    # that no longer exists.  This used to walk edge -> claim NODE -> its predicate; claims
    # stopped being nodes when a fact became an edge, so `claim_id` was ALWAYS None here and
    # the loop skipped every edge -- `claim_count` 0 and `predicates` [] on every entity.
    #
    # 🔴 WHAT IS COUNTED: an edge that carries `claim_id`, i.e. an edge that IS one ledger
    # atom.  What is NOT: the plumbing this graph draws around those atoms -- `binding`,
    # `has_findings`, `on_subject`, `contains`, `finding`, `mechanism`, `needs_enrichment`.
    # Those carry a BORROWED `original_predicate` (mostly "observed"), so counting them would
    # report observations nobody recorded.  `claim_id` is the discriminant because it is the
    # atom's own id: no name matching, and nothing to keep in step with a rename.
    attached_claims = {node_id: {} for node_id in nodes}
    for edge in edges.values():
        claim_id = edge.get("claim_id")
        if not claim_id:
            continue
        for endpoint in (edge["source"], edge["target"]):
            attached_claims[endpoint][claim_id] = edge["predicate"]
    for node_id, node in nodes.items():
        node["depth"] = depths[node_id]
        if node.get("node_kind") in {"entity", "event"}:
            node["claim_count"] = len(attached_claims[node_id])
            counts = {}
            for predicate in attached_claims[node_id].values():
                if predicate:
                    counts[predicate] = counts.get(predicate, 0) + 1
            node["predicates"] = [
                {"predicate": predicate, "count": count}
                for predicate, count in sorted(counts.items())]
    ordered_nodes = sorted(nodes.values(), key=lambda item: (
        item["depth"], item["node_kind"], item["label"], item["id"]))
    ordered_edges = sorted(edges.values(), key=lambda item: (
        min(depths[item["source"]], depths[item["target"]]),
        item["predicate"], item["id"]))
    seed = nodes[primary]
    found = (len(nodes) > len(seed_refs) or bool(edges)
             or any(ref["kind"] == "action" for ref in seed_refs.values()))
    reasons = []
    if depth_cut: reasons.append("depth")
    if node_cut: reasons.append("nodes")
    if edge_cut: reasons.append("edges")
    if claim_cut: reasons.append("claims")
    if action_cut: reasons.append("actions")
    return {
        "schema_version": 3,
        "state": "ready" if found else "empty",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed, "nodes": ordered_nodes, "edges": ordered_edges,
        "seeds": [{"id": item, "sign": "+" if seed_signs[item] > 0 else "-",
                   "node_kind": seed_refs[item]["kind"]} for item in seed_signs],
        "propagation": _propagation(
            nodes, ordered_edges, seed_signs, collect,
            not (depth_cut or node_cut or edge_cut or claim_cut or action_cut)),
        "walk": {
            "mode": "evidence_graph", "direction": direction,
            "observation_mode": observation_mode,
            "collect": collect,
            "start": {
                "positive": sum(1 for s in seed_signs.values() if s > 0),
                "negative": sum(1 for s in seed_signs.values() if s < 0),
            },
            "hops_requested": hops,
            "hops_reached": max(depths.values(), default=0),
            "claims_scanned": claims_scanned,
            "actions_scanned": actions_scanned,
            "enrich_actions": action_lookup is not None,
            "raw_claims": True, "resolver_applied": False,
        },
        "limits": {"nodes": node_limit, "edges": edge_limit,
                   "claims": claim_limit, "actions": edge_limit,
                   "max_hops": MAX_HOPS},
        "truncated": {
            "depth": depth_cut, "nodes": node_cut, "edges": edge_cut,
            "claims": claim_cut, "actions": action_cut,
            "reason": ", ".join(reasons) if reasons else None,
        },
        "message": None if found else "선택한 노드에 연결된 원장 증거가 없습니다",
    }


NODE_TABLE_COLUMNS = (
    "node_id", "node_kind", "node_type", "label", "depth", "claim_count",
    "predicate", "object_kind", "occurred_at", "source_who",
    "source_event_state", "keys_json", "object_payload_json",
)
EDGE_TABLE_COLUMNS = (
    "edge_id", "source_id", "target_id", "predicate", "original_predicate",
    "witnesses", "qualifiers_json",
)
PROPERTY_TABLE_COLUMNS = (
    "node_id", "node_kind", "property_scope", "property_path", "ordinal",
    "value_type", "value_text", "value_number", "value_boolean", "is_null",
)


def _json_cell(value):
    return _canonical(value) if value not in (None, {}) else None


def _property_scalar(node, scope, path, ordinal, value):
    value_type = "null"
    text = number = boolean = None
    if isinstance(value, bool):
        value_type, boolean = "boolean", value
    elif isinstance(value, int) and not isinstance(value, bool):
        value_type, number = "integer", value
    elif isinstance(value, float):
        value_type, number = "number", value
    elif isinstance(value, str):
        value_type, text = "string", value
    elif value is not None:
        value_type, text = "json", _canonical(value)
    return {
        "node_id": node["id"], "node_kind": node.get("node_kind"),
        "property_scope": scope, "property_path": path or "$",
        "ordinal": ordinal, "value_type": value_type, "value_text": text,
        "value_number": number, "value_boolean": boolean,
        "is_null": value is None,
    }


def _flatten_properties(node, scope, value, *, path="", rows=None, limit=10000):
    rows = rows if rows is not None else []
    if len(rows) >= limit:
        return rows, True
    if isinstance(value, dict):
        if not value:
            rows.append(_property_scalar(node, scope, path, None, value))
        for key in sorted(value):
            child = f"{path}.{key}" if path else str(key)
            rows, cut = _flatten_properties(
                node, scope, value[key], path=child, rows=rows, limit=limit)
            if cut:
                return rows, True
        return rows, False
    if isinstance(value, (list, tuple)):
        if not value:
            rows.append(_property_scalar(node, scope, path, None, list(value)))
        for index, item in enumerate(value):
            child = f"{path}[{index}]" if path else f"[{index}]"
            before = len(rows)
            rows, cut = _flatten_properties(
                node, scope, item, path=child, rows=rows, limit=limit)
            for row in rows[before:]:
                row["ordinal"] = index
            if cut:
                return rows, True
        return rows, False
    rows.append(_property_scalar(node, scope, path, None, value))
    return rows, len(rows) >= limit


def tabular_projection(graph, property_limit=DEFAULT_PROPERTY_LIMIT):
    """Project one evidence graph into stable long-form tables.

    Dynamic ontology fields never become dynamic SQL/CSV columns.  They land in the
    typed property long table, which is what lets Spotfire/Excel pivot a newly declared
    metric without this function learning its name.
    """
    property_limit = max(100, min(int(property_limit), MAX_PROPERTY_LIMIT))
    node_rows = []
    edge_rows = []
    property_rows = []
    property_cut = False
    reserved = {
        "id", "node_kind", "type", "label", "depth", "claim_count",
        "predicate", "object_kind", "occurred_at", "source_who",
        "source_event_state", "keys", "object_payload", "predicates",
    }
    for node in graph.get("nodes") or []:
        node_rows.append({
            "node_id": node.get("id"), "node_kind": node.get("node_kind"),
            "node_type": node.get("type"), "label": node.get("label"),
            "depth": node.get("depth"), "claim_count": node.get("claim_count", 0),
            "predicate": node.get("predicate"), "object_kind": node.get("object_kind"),
            "occurred_at": node.get("occurred_at"), "source_who": node.get("source_who"),
            "source_event_state": node.get("source_event_state"),
            "keys_json": _json_cell(node.get("keys")),
            "object_payload_json": _json_cell(node.get("object_payload")),
        })
        # The property table has its own cap.  Reaching it must never shorten
        # Nodes: edges join against the complete node projection even when a
        # very wide payload makes Properties explicitly partial.
        if property_cut:
            continue
        scopes = [
            ("keys", node.get("keys") or {}),
            ("object_payload", node.get("object_payload") or {}),
            ("metadata", {key: value for key, value in node.items()
                          if key not in reserved}),
        ]
        for scope, value in scopes:
            property_rows, cut = _flatten_properties(
                node, scope, value, rows=property_rows, limit=property_limit)
            property_cut |= cut
            if property_cut:
                break
    for edge in graph.get("edges") or []:
        edge_rows.append({
            "edge_id": edge.get("id"), "source_id": edge.get("source"),
            "target_id": edge.get("target"), "predicate": edge.get("predicate"),
            "original_predicate": edge.get("original_predicate"),
            "witnesses": edge.get("witnesses", 0),
            "qualifiers_json": _json_cell(edge.get("qualifiers")),
        })
    tables = {
        "nodes": {"columns": list(NODE_TABLE_COLUMNS), "rows": node_rows},
        "edges": {"columns": list(EDGE_TABLE_COLUMNS), "rows": edge_rows},
        "properties": {"columns": list(PROPERTY_TABLE_COLUMNS),
                       "rows": property_rows},
    }
    truncated = dict(graph.get("truncated") or {})
    truncated["properties"] = property_cut
    if property_cut:
        parts = [part for part in (truncated.get("reason") or "").split(", ") if part]
        if "properties" not in parts:
            parts.append("properties")
        truncated["reason"] = ", ".join(parts)
    provenance = {"source": "ledger_events", "projection": "evidence_graph"}
    if (graph.get("walk") or {}).get("enrich_actions"):
        provenance["additive_sources"] = ["enrichment_action_projection"]
    return {
        "schema_version": 1, "state": graph.get("state"),
        "generated_at": graph.get("generated_at"),
        "seed_id": (graph.get("seed") or {}).get("id"),
        "tables": tables, "walk": graph.get("walk") or {},
        "limits": {**(graph.get("limits") or {}), "properties": property_limit},
        "truncated": truncated,
        "provenance": provenance,
    }
