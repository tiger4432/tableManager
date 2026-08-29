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


DEFAULT_HOPS = 12
MAX_HOPS = 40
#: 🔴 A STEP THAT STAYS ON THE SAME MATERIAL SPENDS A DIFFERENT BUDGET, and this is how
#: many of those a walk may take on top of `hops`.  DEFAULT ZERO, deliberately: the day
#: this landed the declaration already marked six predicates `continues`, so any other
#: default would have changed every existing screen's answer in the same commit that
#: introduced the axis.  Turning it on is the caller's sentence, not this file's.
#:
#: ⚠️ NOT free.  A material step still costs a level of `depths`, so split/transfer
#: repeating forever is bounded by `hops + continues_hops` rather than unbounded; what
#: the second budget buys is that following one wafer's own history does not spend the
#: allowance meant for LEAVING it.
DEFAULT_CONTINUES_HOPS = 0
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
#: 🔴 `NODE_KINDS`, `RETIRED_NODE_KINDS` and `FOLDED_KINDS` left on 2026-08-28.
#: A projection that emits ONE kind needs no roster of kinds, and the two retired
#: names existed only so `collect` could refuse them by name. `collect` went too.

#: A SQL identifier, so a caller-named relation cannot smuggle anything else in.
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


def decode_node_id(value):
    """Decode and canonical-reencode any public evidence-graph node id."""
    text = str(value or "").strip()
    if text.startswith("ledger-entity:v1:"):
        entity_type, keys = ledger_explorer.decode_entity_id(text)
        return {"kind": "entity", "type": entity_type, "keys": keys, "id": text}
    #: 🔴 A CLAIM ID IS NO LONGER A PLACE. Claims became edges on 2026-08-25, so a claim seed
    #: names something the graph has no node for. Refusing says that; answering with a graph
    #: built around a node that does not exist would be a fiction, and answering empty would be
    #: indistinguishable from "this claim has nothing attached". Marking was checked first:
    #: nothing marks a claim.
    # 🔴 ONE PREFIX. Everything a caller may seed is an ENTITY, because everything that is
    # not a predicate is a node and every node the walk returns is a declared entity. The
    # branches for event / claim-atom / finding-point / value ids retired 2026-08-28 with
    # the builders that minted them; a seed in one of those spellings is now refused by the
    # line above rather than decoded into a node kind that no longer exists.
    raise ValueError("node id must be ledger-entity:v1:")


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
    def event_identity(self):
        # Pre-migration rows remain readable and honest.  They are not grouped by a
        # heuristic: one historical atom becomes one explicitly labelled legacy event.
        if self.source_event_id and self.source_event_state in EVENT_STATES:
            return str(self.source_event_id), self.source_event_state
        return str(self.id), "legacy_atom"


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

    def claims_for_entities(self, entities, direction, limit, *,
                            follow=None):
        """`follow` narrows which predicates the walk fetches at all.

        🔴 IT BELONGS IN THE SQL, NOT IN A PROJECTION, because a predicate filtered here is
        never fetched and therefore never spends the budget. Filtering after the fetch would
        leave the walk stopping at the same wall and merely hiding what it collected.
        Observations are always fetched; `follow` is the only thing that narrows this. The
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
                {_where(
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

    def claims_for_entities(self, entities, direction, limit, *,
                            follow=None):
        wanted = {(item[0], _canonical(item[1])) for item in entities}
        rows = []
        for atom in self.atoms:
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


def _rank_layers(items):
    """Layer candidates by DOMINANCE, never by one number.

    A dominates B when A was reached at least as much from the marked subjects and at most
    as much from the controls, strictly better on one of the two.  Two candidates that each
    beat the other on one axis are not ranked against each other at all — they differ in
    KIND, not in degree — and both stay in the top set.  The answer is a set, and 「1등」 is
    a question this function refuses to answer when the evidence does not.

    🔴 RESTORED 2026-08-28, NOT REINVENTED.  It left with `collect` earlier the same day on
    the premise that a walk emitting one node kind has nothing to rank between; the owner
    ruled that afternoon that the candidates are every node, so the premise expired and the
    rule it deleted is the measured one rather than a fresh guess at an ordering.

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


def _propagation(nodes, edges, seed_signs, complete):
    """Rank every node this walk REACHED, by the contrast between the two signed reaches.

    🔴 THE POPULATION IS EVERY REACHED NODE, and that is an owner ruling
    (2026-08-28: 「노드 전부지 rcp 같은거 차이도 있잖아 값 밀고, 그리고 이런 차이가 더
    빈번함」).  Filtering the candidates to one type would answer a narrower question than
    the one being asked: which recipe a marked set ran through is a categorical difference
    like any other, and the owner's measurement is that this KIND of difference is the
    frequent one.  So there is no type filter here, and `collect` — the argument that used
    to name one — is gone with the vocabulary it was spelled in.

    🔴 BOTH NUMBERS LEAVE, and that reverses what this docstring said this morning.  The
    old rule was that reach decides the rank and stays inside, because one magnitude reads
    like a probability and is not one.  What changed is that there is no agreed way to FOLD
    the two reaches into one score yet, and inventing one here would make that invention the
    thing that decides the answer.  Two numbers side by side are a contrast a reader can
    see; one number is a verdict the machine did not earn.  When the folding rule is ruled,
    this is where it goes.

    The ordering itself is `_rank_layers` — dominance, ties kept as ties, and candidates
    that each win on one axis marked `incomparable` rather than separated.
    """
    negatives = sum(1 for sign in seed_signs.values() if sign < 0)
    block = {
        # 🔴 With no control seed the second axis was never examined.  That is NOT
        # 「controls were walked and the factor was absent from them」, and reporting it as
        # a zero would turn 미검사 into a finding.
        "contrast": "contrasted" if negatives else "unexamined",
        # 🔴 A candidate the budget stopped the walk short of is UNEXAMINED, not absent.
        # Measured 2026-08-23: four lot seeds at the default node cap truncate, so this is
        # reachable today rather than a someday case, and a rank read off a truncated graph
        # is provisional.
        "complete": complete,
        "state": "empty",
        "ranked": [],
        "top_set": [],
        "message": None,
    }
    reach, parents = _reach(nodes, edges, seed_signs)
    collected = [{
        "id": node["id"],
        # 🔴 THE DECLARED ENTITY TYPE, not `node_kind`.  `node_kind` is this projection's
        # own plumbing word and every node carries the same value of it now; what tells a
        # recipe from a die is the type the declaration gives them.
        "type": node.get("type"), "label": node.get("label"),
        "reach": reach.get(node["id"], [0.0, 0.0]),
    } for node in nodes.values()
        if node["id"] not in seed_signs and node["id"] in reach]
    if not collected:
        block["message"] = "이 걷기가 씨앗 밖의 노드에 닿지 않았습니다"
        return block
    layers = _rank_layers(collected)
    block["state"] = "ranked"
    block["ranked"] = [{
        "id": item["id"], "type": item["type"], "label": item["label"],
        "reach": item["reach"],
        "rank": item["rank"], "top": item["rank"] == 1,
        "tied": item["tied"], "incomparable": item["incomparable"],
        # 🔴 The trails go on EVERY rank, not only the top set.  「reached from the marked
        # subjects and never from a control」 is a different answer from 「not first」, and
        # what carries that distinction is `evidence[].sign` — one `+`/`−` per seed that
        # reached this candidate.
        #
        # Measured 2026-08-23 before deciding whether to cut: at the node cap (929 nodes,
        # 5 seeds, 90 ranked items, 653 hop entries) the block was 285 KB inside a 2,991 KB
        # response, and trails stay 5 hops long because a BFS trail is bounded by the
        # graph's DIAMETER rather than by `hops`.  ⚠️ That measurement was taken when the
        # population was ONE collected kind; it is now every reached node, so the item
        # count is the node budget rather than a fraction of it.
        "evidence": _evidence(nodes, parents, seed_signs, item["id"]),
    } for layer in layers for item in layer]
    block["top_set"] = [item["id"] for item in layers[0]]
    return block


def _seed_node(seed_id, seed_ref, action_lookup):
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
def _bare_predicate(name):
    """`bonded_from@1` -> `bonded_from`.  The declaration versions ids; atoms do not."""
    return str(name or "").split("@", 1)[0]


def subgraph(seed_id, lookup, *, hops=DEFAULT_HOPS, direction="both",
             node_limit=DEFAULT_NODE_LIMIT, edge_limit=DEFAULT_EDGE_LIMIT,
             action_lookup=None, follow=None, continuing=None,
             continues_hops=DEFAULT_CONTINUES_HOPS):
    """Return a typed evidence subgraph from any public node id, or from a signed SET.

    `seed_id` is one opaque id as before, or `{"positive": [ids], "negative": [ids]}`.

    🔴 `collect`, `observation_mode` and `include_values` left on 2026-08-28 with their
    last caller. They chose among node KINDS, and there is one kind now: a declared entity.
    What narrows a walk is `follow`, and nothing else.
    """
    seed_signs = _signed_seeds(seed_id)
    seed_refs = {item: decode_node_id(item) for item in seed_signs}
    primary = next(iter(seed_signs))
    hops = max(1, min(int(hops), MAX_HOPS))
    # 🔴 THE PREDICATES COME FROM THE CALLER, WHICH READ THEM FROM THE DECLARATION.
    # No word is spelled in this file: a predicate joins the material budget by being
    # declared `continues: true`, and nothing here has to be edited for that.  Bare
    # names on both sides because the declaration versions its ids (`bonded_from@1`)
    # and an atom carries the bare one.
    continuing = {str(name).split("@", 1)[0] for name in (continuing or ())}
    continues_hops = max(0, min(int(continues_hops), MAX_HOPS))
    budget_hops = hops + continues_hops
    node_limit = max(10, min(int(node_limit), MAX_NODE_LIMIT))
    edge_limit = max(20, min(int(edge_limit), MAX_EDGE_LIMIT))
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError("direction must be outgoing, incoming, or both")
    claim_limit = min(MAX_CLAIM_SCAN, max(200, edge_limit * 2))
    # Declared, not queried.  An absent or broken declaration yields no models and no
    # bindings, so the projection simply carries no Quantity nodes — the same «state, not
    # 🔴 THE MECHANISM LOAD LEFT 2026-08-28. It ran on EVERY request to
    # build `models_by_name`, and the only thing that read it was a quantity seed
    # branch that `decode_node_id` cannot produce - it returns `{"kind": "entity"}`
    # or raises. What left here was the walk loading it for nobody; the file itself
    # moved to `_archive/ledger_api/` on 2026-08-28 once the consumer count reached zero.

    nodes = {}
    refs = {}
    depths = {}
    #: node -> how many DEPARTURES were spent reaching it.  A second budget,
    #: not a second depth: `depths` still counts every step.
    dep_cost = {}
    edges = {}
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

    def _spend(near_id, far_id, charge):
        """Carry the departure count from the near side to the far one.

        Keeps the MINIMUM, for the same reason `add_node` keeps the minimum depth: a
        node reached twice is as close as its closest route, and a later expensive
        route must not retire a node the cheap one already paid for.
        """
        cost = dep_cost.get(near_id, 0) + charge
        if far_id not in dep_cost or cost < dep_cost[far_id]:
            dep_cost[far_id] = cost

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
        payload = atom.object_payload or {}
        target = None
        if atom.object_kind == "entity_ref" and payload.get("type") and payload.get("keys"):
            target = _entity_node(payload["type"], payload["keys"])
        # 🔴 THE FAR SIDE ADVANCES, AND WHICH SIDE IS FAR DEPENDS ON THE ARM THAT FETCHED
        # THE ATOM. `claims_for_entities` has two of them, and on the incoming arm the
        # frontier entity is the OBJECT, so the far side is the SUBJECT. Handing the
        # subject `depth` unconditionally -- written as if the walk only ever moved
        # forward -- landed it on a level already walked, where it never joined the next
        # frontier. The walk then stopped after one hop with every budget flag false, and
        # a silent stop is indistinguishable from "there is nothing there".
        # MEASURED 2026-08-28: seeded at defect_kind{void} with follow=leads_to and hops=6
        # the cause chain returned 8 nodes ALL at depth 0 and hops_reached 0, while the
        # same graph seeded one node further in showed bond_pressure -> interface_unfill
        # -> void. `frontier_entities` is what tells the two arms apart; it was already
        # passed in here and read nowhere in the body until now.
        subject_near = subject_id in frontier_entities
        target_near = target is not None and target["id"] in frontier_entities
        if subject_near and target_near:
            subject_depth = target_depth = depth
        elif subject_near:
            subject_depth, target_depth = depth, depth + 1
        else:
            subject_depth, target_depth = depth + 1, depth
        # 🔴 THE FAR SIDE PAYS, AND WHAT IT PAYS DEPENDS ON THE PREDICATE. A step over a
        # `continues` predicate stays on the same material -- one wafer's own split,
        # transfer and inspection history -- so it costs a level of `depths` but no
        # DEPARTURE. `depths` is untouched by this: every reader of it (the truncation
        # test, `hops_reached`, the evidence trails, the client) keeps the meaning it had.
        _charge = 0 if _bare_predicate(atom.predicate) in continuing else 1
        if subject_near and not target_near and target is not None:
            _spend(subject_id, target["id"], _charge)
        elif target_near and not subject_near:
            _spend(target["id"], subject_id, _charge)
        if subject_id not in nodes:
            subject = _entity_node(atom.subject_type, atom.subject_keys)
            if not add_node(subject, decode_node_id(subject["id"]), subject_depth):
                return
        if target is not None:
            if add_node(target, decode_node_id(target["id"]), target_depth):
                add_edge(_claim_edge(atom, subject_id, target["id"], atom.predicate))
            return
        # 🔴 EVERYTHING ELSE IS NOT A NODE. An atom whose object is a VALUE says
        # something about its subject; it is not a second place to stand. The finding-point
        # and measurement-value branches that used to mint nodes here retired 2026-08-28,
        # with the id builders behind them.
        #
        # ⚠️ SAID PLAINLY: findings therefore do not appear in the walk. Making a
        # finding a place again means declaring `defect@1` and re-emitting `observed@1` with
        # an entity_ref object - a reload of 103,841 atoms, and the owner's call. The day that
        # lands, this function needs no branch: the entity_ref arm above already draws it.

    # 🔴 `_link_containers` REMOVED 2026-08-28. It composed the declared
    # reference edges (a die -> its wafer / its dt-job). The declaration stopped
    # declaring them the same night - `entities.die@1.references` was deleted and
    # those 128 edges vanished with NO code change, which is the cleanest proof this
    # projection draws only what is declared.
    # Nothing moves out of reach: `inspected` (128 atoms) already crosses wafer to
    # die forwards, so the material set is unchanged. What left is a drawing.

    for item, ref in seed_refs.items():
        add_node(_seed_node(item, ref, action_lookup), ref, 0)
        dep_cost[item] = 0

    for depth in range(budget_hops):
        # 🔴 A NODE THAT HAS SPENT ITS DEPARTURES IS NOT EXPANDED, however shallow it is.
        # That is the whole of the second budget: the walk keeps going while it stays on
        # the material, and stops going FURTHER AFIELD at exactly the same `hops` it always
        # did.  With `continues_hops=0` this reads `dep_cost < hops` on a range of `hops`,
        # which is what the loop did before this existed.
        frontier_ids = [node_id for node_id, seen in depths.items()
                        if seen == depth and dep_cost.get(node_id, 0) < hops]
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
        finding_refs = [refs[item] for item in frontier_ids
                        if refs[item]["kind"] == "collection"]
        fetched = []

        full_entity_refs = [item for item in entity_refs
                            if not item.get("observation_only", False)]
        if full_entity_refs and remaining > 0:
            batch, cut = lookup.claims_for_entities(
                [(item["type"], item["keys"]) for item in full_entity_refs],
                direction, remaining,
                follow=follow)
            claims_scanned += len(batch); remaining -= len(batch); claim_cut |= cut
            fetched.extend(batch)
            frontier_entities = {item["id"] for item in full_entity_refs}
            for atom in batch:
                _expand_atom(atom, depth, frontier_entities)

        # 🔴 FOUR BRANCHES LEFT HERE ON 2026-08-28: finding summaries, finding
        # points, quantities and source events, plus the enrich-action tail. Each expanded a
        # node kind that is no longer a node -- the walk returns declared ENTITIES and the
        # edges between them, and nothing else. What used to be a place is now either an
        # edge (a claim, a source event) or an attribute of one.
        #
        # ⚠️ The budget flags they wrote (`claim_cut`, `node_cut`, `edge_cut`) are set
        # by `add_node`/`add_edge` and by the entity fetch above, so `truncated` still tells
        # the truth about a walk that ran out of room.

        if any(depth_value > budget_hops for depth_value in depths.values()):
            depth_cut = True
        if claim_cut or (node_cut and edge_cut):
            break

    if any(depth == budget_hops for depth in depths.values()):
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
            nodes, ordered_edges, seed_signs,
            not (depth_cut or node_cut or edge_cut or claim_cut or action_cut)),
        "walk": {
            "mode": "evidence_graph", "direction": direction,
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



