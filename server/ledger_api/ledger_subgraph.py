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
from collections import defaultdict, deque
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
#: repeating forever is bounded by `hops + backbone_hops` rather than unbounded; what
#: the second budget buys is that following one wafer's own history does not spend the
#: allowance meant for LEAVING it.
#: 🔴 NAMED AFTER THE POLICY, NOT AFTER THE RETIRED FLAG. It was `continues_hops` while a
#: per-predicate `continues` decided which steps were free; that flag retired 2026-08-29
#: once the entity class covered it, and `ONTOLOGY_GRAPH_SPEC` §7.5c calls this walk
#: 「메인 스트림(backbone) 추적」. No alias is accepted for the old spelling: both
#: consumers are ours, and a compatibility layer with no one left to remove it stays.
DEFAULT_BACKBONE_HOPS = 0
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


def _reach(nodes, edges, seed_signs, static_types=()):
    """Signed reach of every walked node from the signed seeds.  Pure — no query.

    ONE RULE: A SEED THAT REACHES A NODE COUNTS 1.  Reach is therefore how many marked
    subjects reach it and how many controls do, and nothing else — an integer pair.

    🔴 IT DOES NOT DIVIDE, AND THAT IS THE OWNER'S RULING (2026-08-29): 「그냥 많이 재면
    신호 약해지겠구나」.  Splitting a node's carry among the nodes it forwards to punishes
    the subject that was MEASURED MORE.  MEASURED: a die carrying 3 findings gave each of
    them 0.333 and a die carrying 12 gave each 0.083 — four times weaker for the die that
    was looked at harder, which is backwards for defect analysis.

    The argument was already accepted for the first hop, where dividing would have let a
    factor common to both sides score non-zero purely because a marked subject happens to
    carry a different number of claims than a control does.  That argument is just as true
    at the second hop and every hop after it; it was only ever applied at the first.

    🔴 AND THE FRACTIONS WERE DECIDING THE ANSWER.  MEASURED on the live ledger with four
    seeds: dividing produced 41 distinct reach values across 996 candidates, 981 of them
    fractional, and the top layer held `thickness_um` at [2.0, 0.0123] TOGETHER WITH core
    dies at [0.503, 0.0063] — neither dominates the other, because 2.0 beats 0.503 on the
    marked side while 0.0123 loses to 0.0063 on the control side.  Undivided, the same
    seeds produce five distinct values, all integers, and the top layer is one node.
    Integers also make a tie EXACT, so dominance never breaks on rounding and no tolerance
    has to be invented.

    Distance is not counted either, for the reason a damping constant is refused: decay
    would rank a 3-hop process history below a 1-hop one for its distance alone, which is
    the opposite of what an R&D screen is for.  One hop or five, reaching is reaching.

    What used to justify dividing was hub flooding.  The walk now refuses the two steps
    that made hubs flood — it does not expand a static node into the world, and it does not
    walk back down the predicate it just climbed — so the forks that remain are honest ones
    and there is nothing to split.

    Returns `(reach, parents, kinds)`.  `reach` is `node -> [from_positive, from_negative]`,
    `parents` is `seed -> {node: predecessor}` so an evidence path is rebuilt on demand
    instead of keeping one path per node per seed alive for the whole walk, and `kinds` is
    `seed -> {declared type it reached}` — the DENOMINATOR the ranking needs and the one
    thing a reach of zero cannot supply about itself.
    """
    # 🔴 THIS WALKS UNDER THE SAME TWO RULES THE FETCH DOES, and it has to.  It used to
    # build a plain undirected adjacency and let every seed flood it, which was invisible
    # only because dividing turned the flood into different-looking fractions.  MEASURED the
    # moment dividing stopped: every one of 996 candidates came back [2, 2] -- all four
    # seeds reaching everything -- because a seed could climb out of a name, or climb a
    # container and come back down into another seed's dies, exactly the two steps the
    # fetch refuses.
    #
    # ⚠️ THE RULES ARE STATED TWICE, HERE AND IN `_expand_atom`, AND THAT IS A COST.  The
    # alternative is one fetch PER SEED so that reaching is simply membership; that is the
    # honest shape and it is four times the queries.  Kept as one merged graph plus these
    # two guards until the query cost is measured. If a third rule ever appears, this is the
    # duplication to remove first.
    adjacency = {}
    for edge in edges:
        predicate = edge.get("predicate")
        adjacency.setdefault(edge["source"], []).append((edge["target"], predicate, "outgoing"))
        adjacency.setdefault(edge["target"], []).append((edge["source"], predicate, "incoming"))
    static = {str(name).split("@", 1)[0] for name in (static_types or ())}

    def _kind(node_id):
        return str((nodes.get(node_id) or {}).get("type") or "").split("@", 1)[0]

    reach, parents, kinds = {}, {}, {}
    for seed, sign in seed_signs.items():
        if seed not in nodes:
            continue
        slot = 0 if sign > 0 else 1
        trail = parents.setdefault(seed, {})
        reached_kinds = kinds.setdefault(seed, set())
        seen = {seed}
        queue = deque([(seed, None, None)])
        while queue:
            node, came_by, came_how = queue.popleft()
            here_is_name = _kind(node) in static
            for nxt, predicate, direction in adjacency.get(node) or ():
                if nxt in seen:
                    continue
                there_is_name = _kind(nxt) in static
                # a name may lead to another name and never back out into the world
                if here_is_name and not there_is_name:
                    continue
                # and no step goes back down the predicate it just climbed -- between two
                # names there is no container and so no siblings, so that pair is exempt
                if (direction == "outgoing" and came_how == "incoming"
                        and predicate == came_by
                        and not (here_is_name and there_is_name)):
                    continue
                seen.add(nxt)
                trail[nxt] = node
                reached_kinds.add(_kind(nxt))
                reach.setdefault(nxt, [0, 0])[slot] += 1
                queue.append((nxt, predicate, direction))
    return reach, parents, kinds


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


def _propagation(nodes, edges, seed_signs, complete, static_types=()):
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
    reach, parents, kinds = _reach(nodes, edges, seed_signs, static_types)
    # 🔴 THE DENOMINATOR. A reach of zero says nothing about itself: the control may have
    # HAD the path and not carried this factor, or it may have had no path to that kind at
    # all, and those two read identically as 0. So each side is reported as a pair --
    # `reach[i]` over `reachable[i]`, where the second counts the seeds that reached the
    # candidate's TYPE at least once.
    #
    # MEASURED 2026-08-29 on three seeded fixtures. With a sound control, `SYN-R-CMP-01`
    # reads 2/2 against 0/2 -- the control could reach recipes and ran a different one, so
    # the difference is real. With a control whose bridge to its core wafers is missing,
    # the same recipe reads 0/0 and every candidate in the top layer does too, so the false
    # answer is visible instead of confident. And `void` reads 0/0 against ANY of these
    # controls, because a group defined as void-free cannot reach `defect_kind` -- the
    # tautological axis excludes itself here rather than needing a rule of its own.
    #
    # ⚠️ WHAT THIS DOES NOT CATCH, said plainly: the denominator is the TYPE. A control
    # that measured sixteen quantities reaches `quantity`, so an item it never measured
    # still reads 0/2 and looks like a real difference. That is a different denominator --
    # the item, not the kind -- and it stays a separate question.
    def _reachable(node_type):
        bare = str(node_type or "").split("@", 1)[0]
        pair = [0, 0]
        for seed, sign in seed_signs.items():
            if bare and bare in kinds.get(seed, ()):
                pair[0 if sign > 0 else 1] += 1
        return pair
    collected = [{
        "id": node["id"],
        # 🔴 THE DECLARED ENTITY TYPE, not `node_kind`.  `node_kind` is this projection's
        # own plumbing word and every node carries the same value of it now; what tells a
        # recipe from a die is the type the declaration gives them.
        "type": node.get("type"), "label": node.get("label"),
        "reach": reach.get(node["id"], [0, 0]),
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
        "reachable": _reachable(item["type"]),
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
def _bare(name):
    """The same trim for an ENTITY type: `defect_kind@1` -> `defect_kind`."""
    return str(name or "").split("@", 1)[0]


def subgraph(seed_id, lookup, *, hops=DEFAULT_HOPS, direction="both",
             node_limit=DEFAULT_NODE_LIMIT, edge_limit=DEFAULT_EDGE_LIMIT,
             action_lookup=None, follow=None,
             backbone_hops=DEFAULT_BACKBONE_HOPS, static_types=None,
             static_follow=None):
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
    # 🔴 THE CLASSES COME FROM THE CALLER, WHICH READ THEM FROM THE DECLARATION.
    # No type is spelled in this file: an entity becomes a name rather than a happening by
    # being declared `class: "static"`, and nothing here has to be edited for that.  Bare
    # names because the declaration versions its ids (`defect_kind@1`) and a projected node
    # carries the bare one.
    backbone_hops = max(0, min(int(backbone_hops), MAX_HOPS))
    budget_hops = hops + backbone_hops
    static_types = {str(name).split("@", 1)[0] for name in (static_types or ())}
    # 🔴 AND THE STEPS A NAME MAY TAKE, from the same caller and the same declaration.
    # Empty means a static node is not expanded at all, which is what an unreadable
    # declaration should do: refuse the step rather than guess which hub is safe.
    static_follow = {str(name).split("@", 1)[0] for name in (static_follow or ())}
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
    #: node -> the set of (predicate, "incoming"|"outgoing") steps that REACHED it.
    #: Seeds keep an empty set, which is why they need no exemption below.
    arrivals = defaultdict(set)
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
        # 🔴 THE FAR SIDE PAYS, AND WHAT IT PAYS DEPENDS ON THE TWO ENDS. A step between two
        # happenings stays inside the world -- one wafer's own split,
        # transfer and inspection history -- so it costs a level of `depths` but no
        # DEPARTURE. `depths` is untouched by this: every reader of it (the truncation
        # test, `hops_reached`, the evidence trails, the client) keeps the meaning it had.
        # 🔴 A NAME MAY BE REACHED, AND MAY LEAD TO ANOTHER NAME, BUT NOT BACK INTO THE
        # WORLD. The owner's rule is about the STEP and not about the node: `s -> s` is
        # allowed, `s -> d` is not. Written as "do not expand a static node" instead, it
        # also cuts `s -> s`, and MEASURED that costs the whole causal chain - seeded at
        # quantity{bond_pressure} with follow=leads_to the graph fell from 18 nodes and 4
        # hops to 1 node and 0 edges, because every link in that chain is quantity to
        # quantity. What the rule is for is the other direction: `defect_kind` carries
        # 103,841 atoms against ONE distinct object, so one step from that name back out
        # to wafers drags in 747 of them and the answer drowns.
        near_kind = far_kind = None
        if subject_near and not target_near:
            near_kind, far_kind = _bare(atom.subject_type), _bare(payload.get("type"))
        elif target_near and not subject_near:
            near_kind, far_kind = _bare(payload.get("type")), _bare(atom.subject_type)
        if near_kind in static_types and far_kind and far_kind not in static_types:
            return
        # 🔴 A STEP DOES NOT GO BACK DOWN THE PREDICATE IT JUST CLIMBED. Reaching a
        # container by walking one predicate BACKWARDS and then walking the same predicate
        # FORWARDS lands on the container's other children -- the seed's own siblings,
        # which are one-sided by construction and say nothing.
        #
        # MEASURED 2026-08-29, one defect seeded with `direction=both` and hops=4: the walk
        # returned 199 defects, of which 189 arrived as
        # `die -[inspected backwards]-> wafer -[inspected forwards]-> die'`. The ten that
        # remain are the ones the transfer and bond chain carries, and those are the answer.
        #
        # 🔴 THE TEST IS ON THE ADJACENT PAIR, AND ON THAT DIRECTION ONLY.
        # `outgoing(P) -> incoming(P)` is the OPPOSITE shape -- "everything that points at
        # what I point at", which is how one asks for the wafers that ran the same recipe --
        # and it stays. So does `P -> Q -> P`: the owner's own path climbs `inspected` and
        # `has_wafer`, travels a `slot_map` chain, and descends into a DIFFERENT wafer.
        # MEASURED on the declaration: that path is one of 23 lot_slot routes this rule
        # keeps, out of 95 it is offered.
        #
        # 🔴 `==` AND NOT `in`: a node reached some other way as well was not used purely as
        # a container, so expanding it is not the sibling step this refuses.
        near_id = far_id = step_dir = None
        if subject_near and not target_near:
            near_id, step_dir = subject_id, "outgoing"
            far_id = target["id"] if target is not None else None
        elif target_near and not subject_near:
            near_id, far_id, step_dir = target["id"], subject_id, "incoming"
        # 🔴 AND IT IS A RULE ABOUT THE WORLD, NOT ABOUT THE NAMES. Between two static
        # types there is no container and so no siblings: `leads_to` walked back to a cause
        # and then forward again reaches THE OTHER EFFECTS OF THAT CAUSE, which is the
        # differential a person is asking for. MEASURED: seeded at `defect_kind{void}` with
        # follow=leads_to, refusing the step costs 2 of 21 nodes -- one of them another
        # defect kind the same cause produces.
        if (step_dir == "outgoing"
                and not (near_kind in static_types and far_kind in static_types)
                and arrivals.get(near_id) == {(atom.predicate, "incoming")}):
            return
        if far_id is not None and step_dir is not None:
            arrivals[far_id].add((atom.predicate, step_dir))
        # 🔴 A STEP BETWEEN TWO HAPPENINGS IS NOT A DEPARTURE - policy 1 of
        # `ONTOLOGY_GRAPH_SPEC` §7.5c, and the same machine `continues` was, keyed on the
        # ENTITY CLASS instead of on a per-predicate flag. Following one wafer through its
        # own split, transfer and inspection history stays inside the world, so it spends
        # the material budget rather than the allowance meant for LEAVING.
        #
        # ⚠️ MEASURED BEFORE THE FLAG WAS REMOVED: on the same seed the class rule reaches
        # everything the flag reached (157 nodes either way), and reaches MORE once
        # `observed` is followed (246), which is the one predicate D->D holds that
        # `continues` did not.
        _charge = 0 if (near_kind and far_kind
                        and near_kind not in static_types
                        and far_kind not in static_types) else 1
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
        # did.  With `backbone_hops=0` this reads `dep_cost < hops` on a range of `hops`,
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
        # 🔴 A NAME IS FETCHED WITH A NARROWER `follow`, NOT FILTERED AFTER THE FETCH.
        # `_expand_atom` already refuses the `s -> d` step, and refusing it there is too
        # late: the atom has been read out of the ledger and charged to `claims_scanned`
        # before anything looks at its two ends. MEASURED 2026-08-29 from one defect at
        # hops=4 -- following `of_kind` scanned 6,000 claims (the ceiling) to return 13
        # nodes and stopped at hop 2, while dropping it scanned 371 and returned 315 at
        # hop 4. One name was buying 6,000 atoms so that the projection could throw them
        # away, and the walk ran out of budget two hops from its seed.
        #
        # The two groups differ ONLY in the `follow` they are fetched with, so `s -> s`
        # survives: `leads_to` is in `static_follow` and the mechanism chain still walks.
        dynamic_refs = [item for item in full_entity_refs
                        if _bare(item["type"]) not in static_types]
        static_refs = [item for item in full_entity_refs
                       if _bare(item["type"]) in static_types]
        # 🔴 AN EMPTY LIST IS NOT `None` HERE. `claims_for_entities` reads a falsy `follow`
        # as "every predicate", so narrowing to an empty intersection and passing it would
        # fetch MORE than narrowing to one name. The group is skipped instead.
        static_step_follow = sorted(static_follow & set(follow)) if follow else sorted(static_follow)
        for group, group_follow, group_is_static in (
                (dynamic_refs, follow, False), (static_refs, static_step_follow, True)):
            if not group or remaining <= 0:
                continue
            if group_is_static and not group_follow:
                continue
            batch, cut = lookup.claims_for_entities(
                [(item["type"], item["keys"]) for item in group],
                direction, remaining,
                follow=group_follow)
            claims_scanned += len(batch); remaining -= len(batch); claim_cut |= cut
            fetched.extend(batch)
            frontier_entities = {item["id"] for item in group}
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
            not (depth_cut or node_cut or edge_cut or claim_cut or action_cut),
            static_types),
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



