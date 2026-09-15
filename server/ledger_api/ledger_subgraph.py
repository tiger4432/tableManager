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

from ledger import explorer
from utils.wire_format import wire_text
from declaration_names import bare_name as _bare_name
from ledger import trace


DEFAULT_HOPS = 12
MAX_HOPS = 40

# ---------------------------------------------------------------------------
# S-146 — group · aggregate, where the population is whole (판정 331)
# ---------------------------------------------------------------------------
#: 🔴 THE SEVEN THE SCREEN ALREADY OFFERS, spelled ONCE and on the server side.
#: `client2/src/rnd_board/api.js` has held this exact table (`AGGREGATE`) and the operator
#: has been choosing from it; inventing an eighth here, or renaming one, would make the
#: screen and the answer disagree about what 「mean」 means. The names are the client's.
#:
#: 🔴 AND THE AXIS MOVES TO THE SERVER BECAUSE THE POPULATION DOES. Folding on the client
#: needs the walk to carry EVERYTHING back, and at 10⁸ the budget cuts first -- measured:
#: `trendFromWalk` REFUSES to count a truncated walk, so the screen goes blank rather than
#: wrong. Counting here counts over the set the walk actually reached.
AGGREGATE_MEASURES = ("count", "distinct", "sum", "mean", "min", "max", "median")

#: Which of them need numbers. `count` and `distinct` fold anything; the rest are arithmetic
#: and a string in the stream is a refusal rather than a zero.
NUMERIC_MEASURES = frozenset({"sum", "mean", "min", "max", "median"})

#: What `group_by` may name: a node's TYPE, or one of the values it carries.
#: ⚠️ NOT A PREDICATE. 「사용자가 고르는 축은 노드 타입 하나, 술어는 follow 로만」 — a key that
#: named an edge would be a second way to say `follow`.
GROUP_BY_TYPE = "type"


class AggregateRefused(ValueError):
    """A group key or measure this walk cannot honour. Carries the name and the choices.

    ⛔ NAMED, NEVER SILENT. A misspelled measure that fell back to `count` would answer a
    question nobody asked, and the number would look exactly like a right one.
    """

    def __init__(self, code, detail, choices=()):
        self.code = code
        self.detail = detail
        self.choices = tuple(choices)
        super().__init__(detail)


def _numbers(values):
    """The numeric values in a stream, or `None` if any of them is not a number."""
    out = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        out.append(float(value))
    return out


def _fold(measure, values):
    """One measure over one group's values. The seven, and nothing else."""
    if measure == "count":
        return len(values)
    if measure == "distinct":
        return len({_canonical(value) for value in values})
    numbers = _numbers(values)
    if numbers is None:
        raise AggregateRefused(
            "measure_needs_numbers",
            "measure %r folds numbers and this group carries a value that is not one"
            % measure, sorted(NUMERIC_MEASURES))
    if not numbers:
        # 🔴 AN EMPTY GROUP HAS NO SUM TO STATE. `0` would say the values were there and
        # added to nothing, which is a different fact from 「no values were carried」.
        return None
    if measure == "sum":
        return sum(numbers)
    if measure == "mean":
        return sum(numbers) / len(numbers)
    if measure == "min":
        return min(numbers)
    if measure == "max":
        return max(numbers)
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


#: Where a `measure`'s name is looked up, IN THIS ORDER (S-146-c, 판정 336).
#: 🔴 SPELLED ONCE AND CARRIED IN THE ENVELOPE, so the screen learns the order rather than
#: guessing it. A name that resolves in two of these is REFUSED: silently preferring one
#: would let that preference decide the answer, and the two numbers are not the same number.
VALUE_SOURCES = ("attributes", "qualifiers", "predicates")


def _source_values(node, source, name):
    """The values one source of one node offers under `name`. Empty when it offers none."""
    if source == "predicates":
        # 🔴 THE NODE ALREADY CARRIES THIS (`ledger_subgraph` publishes
        # `predicates: [{predicate, count}]` per entity). Counting 「reached by this
        # predicate」 therefore needs no edge walk and no second query - the ratio axis's
        # numerator and denominator are both node-side facts that were already on the wire.
        return [entry.get("count") for entry in (node.get("predicates") or ())
                if entry.get("predicate") == name and entry.get("count") is not None]
    carried = (node.get(source) or {})
    if name not in carried:
        return []
    value = carried[name]
    # ⚠️ A PLURAL ATTRIBUTE IS ALREADY A LIST (S-144), and flattening it is the only reading
    # that does not invent one: each value it holds is a value.
    return list(value) if isinstance(value, list) else [value]


def _values_of(node, name):
    """What one node carries under `name`, always as a list — from ONE source.

    ⛔ A NAME THAT TWO SOURCES ANSWER IS REFUSED. An attribute called `observed@1` and a
    predicate of that id are different numbers, and choosing between them here would make
    this function the author of the answer.
    """
    answering = [source for source in VALUE_SOURCES if _source_values(node, source, name)]
    if len(answering) > 1:
        raise AggregateRefused(
            "ambiguous_value_name",
            "%r is answered by %s on the same node; rename one or ask for the other"
            % (name, " and ".join(answering)), VALUE_SOURCES)
    return _source_values(node, answering[0], name) if answering else []


def _group_keys(node, group_by):
    """Which groups this node belongs to. Several, when the key is a plural attribute.

    🔴 A NODE WITH TWO PRODUCTS IS IN BOTH GROUPS. Picking one would be this seat deciding
    which of two declared-true values counts, and dropping the node would make the groups
    sum to less than the population without saying so.
    """
    if group_by == GROUP_BY_TYPE:
        return [str(node.get("type") or "")]
    return [value for value in _values_of(node, group_by) if value is not None]


def _split_measure(measure):
    """One `measure` argument -> (fold name, the value name it folds). Refuses by name."""
    name, _sep, qualifier = str(measure or "count").partition(":")
    if name not in AGGREGATE_MEASURES:
        raise AggregateRefused(
            "unknown_measure", "no measure named %r" % name, AGGREGATE_MEASURES)
    if name in NUMERIC_MEASURES and not qualifier:
        raise AggregateRefused(
            "measure_needs_a_name",
            "measure %r folds values, so it needs a name: %s:<attribute>" % (name, name),
            AGGREGATE_MEASURES)
    return name, qualifier


def _latest_edge_instant(members, edges_by_node):
    """The newest `occurred_at` among the edges attached to this group's nodes.

    🔴 AN ENTITY HAS NO INSTANT AND SHOULD NOT (S-146-c, 판정 336). Time lives on the atoms,
    so a group's time is the newest time of the facts that reached it -- measured: only
    edges carry `occurred_at`; entity nodes carry none.

    ⚠️ NO EDGES MEANS NO KEY, NOT `null`. 「this group has no fact with a time」 and 「the
    caller did not ask」 are different answers, and a null collapses them.
    """
    instants = [edge.get("occurred_at")
                for node in members
                for edge in edges_by_node.get(node.get("id"), ())
                if edge.get("occurred_at")]
    return max(instants) if instants else None


def group_nodes(nodes, group_by, measure, edges=()):
    """`groups` for one walk: the fold, over the nodes this response carries (판정 331).

    🔴 THE SAME WALK AND THE SAME BUDGET. A second walk for the aggregate would put two
    populations in one answer, and the reader would have no way to know which number came
    from which. Truncation is said by the envelope's own `truncated`/`complete` rather than
    by a second word in here -- one spelling for one fact.

    ⚠️ `edges` IS AN INPUT, NOT A SECOND POPULATION (판정 336). They come from the walk that
    already ran; what changes is what the fold may read, not what was reached.

    🔴 `value` IS ALWAYS A MAP, keyed by the measure string, even for one measure. A cell
    that is a number for one measure and a map for two is one cell with two shapes, and a
    reader would have to guess which it got.
    """
    asked = [measure] if isinstance(measure, (str, bytes)) or measure is None else list(measure)
    if not asked:
        asked = ["count"]
    folds = [(str(item), ) + _split_measure(item) for item in asked]

    edges_by_node = {}
    for edge in edges or ():
        for endpoint in (edge.get("source"), edge.get("target")):
            if endpoint:
                edges_by_node.setdefault(endpoint, []).append(edge)

    grouped = {}
    for node in nodes:
        for key in _group_keys(node, group_by):
            grouped.setdefault(key, []).append(node)

    out = []
    for key in sorted(grouped, key=str):
        members = grouped[key]
        value = {}
        for spelled, name, qualifier in folds:
            if qualifier:
                values = [v for node in members for v in _values_of(node, qualifier)]
            else:
                # `count`/`distinct` with no name count the NODES, which is what the
                # screen's default (`count`) has always meant.
                values = [node.get("id") for node in members]
            value[spelled] = _fold(name, values)
        row = {"key": key, "n": len(members), "value": value}
        at = _latest_edge_instant(members, edges_by_node)
        if at is not None:
            row["at"] = at
        out.append(row)
    return out

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

#: How many SUBJECTS a described seed set may name (S-148-a, 판정 337). 🔴 THE NUMBER IS
#: MINE AND UNVERIFIED AT OPERATING SHAPE. It sits in `node_limit`'s class -- an argument,
#: a ceiling and a default -- and is deliberately generous rather than tuned: a seed is one
#: id, but every seed EXPANDS, so the real cost is seeds x hops and `node_limit` cuts that
#: second. Whether 200 is right belongs in a production-shaped box (S-146-b's seat), and
#: guessing it here would let the guess decide the answer.
DEFAULT_SEED_LIMIT = 200
MAX_SEED_LIMIT = 2000
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


def _json_key(value):
    """One spelling for a key value, so `1` and `1.0` do not miss each other.

    The same die was measured arriving as `x: 1` from one source and `x: 1.0` from another
    on 2026-08-28; comparing raw would silently drop the edge that matters, which is the
    failure this constraint exists to prevent rather than cause.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)


#: How many registration atoms the follow-independent sweep fetches PER NODE. A node's
#: attributes come from its newest registration, and a new one is written only when a value
#: CHANGES, so this is a history depth rather than a row count.
REGISTRATIONS_FETCHED_PER_NODE = 8


def decode_node_id(value):
    """Decode and canonical-reencode any public evidence-graph node id."""
    text = str(value or "").strip()
    if text.startswith("ledger-entity:v1:"):
        entity_type, keys = explorer.decode_entity_id(text)
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

    def __init__(self, connection, relation="ledger_events", since=None, until=None):
        if not _IDENTIFIER.match(relation or ""):
            raise ValueError("relation must be a bare identifier")
        self.connection = connection
        self.relation = relation
        # 🔴 S-98. THE INTERVAL LIVES ON THE LOOKUP, not on each method. The walk asks
        # three different queries, and an argument threaded through each would let them hold
        # three different intervals for one request.
        self.since = since
        self.until = until
        #: How many claims this walk did NOT fetch because they fall outside the interval,
        #: summed over hops (ruling 208).
        #:
        #: ⚠️ A CUT IS NOT AN ABSENCE. Without this number a narrowed walk and an
        #: empty one render identically - the failure this repository has already had to name
        #: in five other shapes. `None` while no interval was asked for, so the response
        #: leaves the key OUT rather than publishing a zero that reads as "nothing was
        #: excluded" when nothing was excluded because nothing was asked.
        self.interval_excluded = None if (since is None and until is None) else 0

    def _interval_clause(self, params):
        """The rows the interval KEEPS. Empty string when no interval was asked for.

        🔴 IT BELONGS IN THE SQL for `follow`'s reason, stated in its docstring below: a
        claim filtered here is never fetched and therefore never spends the budget.
        """
        kept = []
        if self.since is not None:
            params["since"] = self.since
            kept.append("e.occurred_at >= %(since)s")
        if self.until is not None:
            params["until"] = self.until
            kept.append("e.occurred_at < %(until)s")
        return " AND ".join(kept)

    def _outside_clause(self, params):
        """The rows the interval EXCLUDES - the complement of `_interval_clause`, and it has
        to be built from the same two bounds or the count would answer a third question."""
        kept = []
        if self.since is not None:
            params["since"] = self.since
            kept.append("e.occurred_at < %(since)s")
        if self.until is not None:
            params["until"] = self.until
            kept.append("e.occurred_at >= %(until)s")
        if not kept:
            return ""
        return "(" + " OR ".join(kept) + ")"

    def _execute(self, sql, params):
        return trace._fetch(self.connection, sql, params)

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

        # 🔴 ONE ARM BUILDER, TWO QUESTIONS (ruling 208). The fetch asks for the claims
        # INSIDE the interval and the census asks how many fall OUTSIDE it; they must differ
        # in nothing but that clause, or the number reported is about a different set of rows
        # than the walk actually skipped.
        def _arms(extra_clause):
            built = []
            if direction in ("outgoing", "both"):
                built.append(f"""
                    SELECT {EVIDENCE_COLUMNS} FROM frontier f
                    JOIN {self.relation} e
                      ON e.subject_type = f.type AND e.subject_keys = f.keys
                    {_where(follow_clause, extra_clause)}
                """)
            if direction in ("incoming", "both"):
                built.append(f"""
                    SELECT {EVIDENCE_COLUMNS} FROM frontier f
                    JOIN {self.relation} e
                      ON e.object_kind = 'entity_ref'
                     AND e.object_payload->>'type' = f.type
                     AND e.object_payload->'keys' = f.keys
                    {_where(follow_clause, extra_clause)}
                """)
            return " UNION ".join(built)

        frontier_cte = """
            WITH frontier AS (
                SELECT type, keys FROM jsonb_to_recordset(CAST(%(frontier)s AS jsonb))
                     AS item(type text, keys jsonb)
            )
        """
        rows = self._execute(f"""
            {frontier_cte}
            SELECT * FROM ({_arms(self._interval_clause(params))}) claims
            ORDER BY occurred_at DESC, id DESC
            LIMIT %(fetch)s
        """, params)
        self._count_excluded(frontier_cte, _arms, params)
        return self._bounded(rows, limit)

    def _count_excluded(self, frontier_cte, arms, params):
        """One aggregate per hop, and ONLY when an interval was asked for (ruling 208).

        ⚠️ THE COST IS VISIBLE AND BOUNDED: `MAX_HOPS` caps the walk, so this is at most
        that many extra queries, and it runs not at all for a request that named no interval.
        A boolean would have been free and would not answer the question an operator asks -
        「how many did I not see」.
        """
        if self.interval_excluded is None:
            return
        outside = self._outside_clause(params)
        if not outside:
            return
        rows = self._execute(f"""
            {frontier_cte}
            SELECT count(*) FROM ({arms(outside)}) claims
        """, params)
        self.interval_excluded += int(rows[0][0]) if rows else 0

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


    def subjects_of_type(self, entity_type, limit):
        """Every REGISTERED subject of one declared type — a described seed set (S-148-a).

        🔴 THROUGH THIS CLASS'S OWN RUNNER, `self._execute`, and that is not a style choice.
        Measured: every sibling method here goes through it (`ledger_trace._fetch`), and the
        first landing of this method reached for `self.connection.cursor()` instead — a
        DBAPI call. The connection this class actually holds in the product is a SQLAlchemy
        `Connection`, which has no `cursor`, so the route answered 500. One class, one way
        of emitting SQL.

        🔴 THE INDEX IS THE ONE THE SCHEMA ALREADY KEEPS:
        `idx_ledger_register (subject_type, subject_keys) WHERE predicate = 'register'`.
        PARTIAL, so it is O(entities) rather than O(atoms) -- the schema's own note says so.

        🔴 EVERY ENTITY HAS A REGISTER ATOM. That is A1's existence axis and the predicate
        name is fixed (`config_authoring.REGISTER_PREDICATE`), so 「this type's subjects」
        reads the seat that already records existence rather than inventing one.

        ⚠️ ONE ROW PAST THE BUDGET, so 「there were more」 is a fact rather than an inference
        from a full page.
        """
        from ledger import schema
        from ledger.config_authoring import REGISTER_PREDICATE

        bare = str(entity_type or "").split("@", 1)[0]
        rows = self._execute(
            f"SELECT DISTINCT subject_type, subject_keys "
            f"FROM {schema.LEDGER_TABLE} "
            f"WHERE predicate = %(predicate)s AND subject_type = %(subject_type)s "
            f"ORDER BY subject_type, subject_keys "
            f"LIMIT %(fetch)s",
            {"predicate": REGISTER_PREDICATE, "subject_type": bare,
             "fetch": int(limit) + 1})
        cut = max(0, len(rows) - int(limit))
        # ⚠️ ROWS ARE POSITIONAL, as `_atom_from_row` beside this reads them, and
        # `subject_keys` arrives as text on one driver and as a mapping on the other --
        # the same two-shaped handling that function already does.
        out = []
        for row in rows[:int(limit)]:
            keys = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            out.append(explorer.entity_id(str(row[0]), dict(keys or {})))
        return _DescribedSeeds(out, cut)


class _DescribedSeeds:
    """What a described seed set resolved to, and whether the description outran its budget.

    ⚠️ A PAIR, because 「these are the subjects」 and 「there were more」 are two facts and a
    truncated list cannot carry the second one about itself.
    """

    __slots__ = ("ids", "cut")

    def __init__(self, ids, cut):
        self.ids = list(ids)
        self.cut = int(cut)


class InMemoryEvidenceLookup:
    """Contract double used to prove traversal independently of PostgreSQL."""

    def __init__(self, atoms, since=None, until=None):
        self.atoms = list(atoms)
        # 🔴 THE SAME TWO ARGUMENTS AND THE SAME ACCUMULATOR AS THE SQL LOOKUP. A double
        # thinner than the thing it stands in for is more permissive than production, and a
        # test suite driving this one would then score only the SQL side of the interval.
        self.since = since
        self.until = until
        self.interval_excluded = None if (since is None and until is None) else 0

    def _outside(self, atom):
        if self.since is not None and atom.occurred_at < self.since:
            return True
        return self.until is not None and atom.occurred_at >= self.until

    @staticmethod
    def _result(rows, limit):
        ordered = sorted(rows, key=lambda atom: (atom.occurred_at, atom.id), reverse=True)
        return ordered[:limit], len(ordered) > limit

    def subjects_of_type(self, entity_type, limit):
        """The same question over the atoms held in memory. ⚠️ THE SAME RULE, not a looser
        one: only REGISTERED subjects count, so a fixture cannot accidentally seed from a
        type nothing registered."""
        from ledger.config_authoring import REGISTER_PREDICATE

        bare = str(entity_type or "").split("@", 1)[0]
        seen, ids = set(), []
        for atom in sorted(self.atoms, key=lambda a: (a.subject_type, str(a.subject_keys))):
            if atom.predicate != REGISTER_PREDICATE:
                continue
            if str(atom.subject_type).split("@", 1)[0] != bare:
                continue
            node_id = explorer.entity_id(atom.subject_type, atom.subject_keys)
            if node_id in seen:
                continue
            seen.add(node_id)
            ids.append(node_id)
        return _DescribedSeeds(ids[:int(limit)], max(0, len(ids) - int(limit)))

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
                # Counted where it is skipped, so the census and the filter cannot come to
                # disagree about which claims the interval left out.
                if self._outside(atom):
                    if self.interval_excluded is not None:
                        self.interval_excluded += 1
                    continue
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

#: Which attribute names hold SEVERAL values, per bare entity type (S-144). Filled by the
#: same read as the line above, so the two can never come from different revisions.
_entity_plural_attributes = {}

#: 🔴 「이 술어가 안 보이는 것이 무슨 뜻인가」 — bare finding predicate -> (bare examination
#: predicate, whether that examination is itself declared). Filled by the same read as the two
#: above (S-149). The population of `node["absence"]` is THIS MAP, not the data: a predicate
#: that did not appear has no row in `predicates[]`, and that is exactly where a `false`
#: verdict has to live.
_absence_confirmers = {}


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
    _read_entity_declaration()
    return _entity_key_order.get(str(entity_type))


def _read_entity_declaration():
    """Read the entity declaration ONCE, filling everything this module takes from it.

    🔴 ONE READ, TWO FACTS (S-144). Key order and attribute cardinality come from the same
    file, and two cached reads could answer from two different revisions of it - a node
    labelled by one version of a declaration and valued by another. They are two caches
    because they are two questions, but there is only one sentinel and one open().

    Never raises: an absent or unreadable declaration leaves labels and attributes exactly
    as they are today rather than taking the walk down with it. The `@version` suffix is
    stripped the way `ledger/roleframe.py` strips it.
    """
    global _entity_key_order, _entity_plural_attributes, _absence_confirmers
    if _entity_key_order is not None:
        return
    from ledger.setup_bundle import ATTRIBUTE_CARDINALITY_MANY

    order, plural_by_type, confirmers = {}, {}, {}
    try:
        import paths
        with open(paths.config_path("ontology", "ledger_config.json"),
                  "r", encoding="utf-8") as handle:
            document = json.load(handle) or {}
        declared = document.get("entities") or {}
        # 🔴 THE THIRD FACT, ON THE SAME READ AND THE SAME SENTINEL (S-149). A separate
        # cached read would be a second thing to forget on reload -- which is exactly the
        # hole S-206 closed -- and could answer from a different revision of one file.
        vocabulary = document.get("vocabulary") or {}
        for predicate, spec in vocabulary.items():
            confirmer = (spec or {}).get("absence_confirmed_by")
            if isinstance(confirmer, str) and confirmer.strip():
                confirmers[str(predicate).rsplit("@", 1)[0]] = (
                    confirmer.rsplit("@", 1)[0], confirmer in vocabulary)
        for name, spec in declared.items():
            spec = spec or {}
            bare = str(name).rsplit("@", 1)[0]
            keys = [str(key) for key in (spec.get("keys") or [])]
            if keys:
                order[bare] = keys
            cardinality = spec.get("attribute_cardinality")
            if isinstance(cardinality, dict):
                plural = frozenset(
                    str(attribute) for attribute, how in cardinality.items()
                    if how == ATTRIBUTE_CARDINALITY_MANY)
                if plural:
                    plural_by_type[bare] = plural
    except Exception:
        order, plural_by_type, confirmers = {}, {}, {}
    _entity_key_order, _entity_plural_attributes = order, plural_by_type
    _absence_confirmers = confirmers


def reset_declaration_cache():
    """Forget the entity declaration so the next walk reads it again (S-206, 판정 330).

    🔴 THE SENTINEL ABOVE IS PROCESS-LIFETIME, and that is a reload hole rather than a
    design: an operator who declares `attribute_cardinality: many` and activates it gets
    `one` from the walk until somebody RESTARTS the server. 「빌드했다고 로드된 건 아니다」.

    ⚠️ THE HOLE PREDATES THE PLURAL CELL - key order was already cached this way - but the
    same cache now carries a fact the operator wrote MINUTES ago, which is what makes the
    staleness visible instead of theoretical.

    🔴 BOTH GLOBALS GO TOGETHER, because one read fills them both. Clearing only the
    sentinel would leave the plural map from the previous revision standing while the key
    order came from the new one - the split this module's 「one read」 note exists to stop.
    """
    global _entity_key_order, _entity_plural_attributes, _absence_confirmers
    _entity_key_order, _entity_plural_attributes = None, {}
    _absence_confirmers = {}


def _declared_entity_facts_names():
    """The bare names the declaration gives entity types. Empty when it cannot be read.

    ⚠️ EMPTY MEANS 「cannot say」, NOT 「none are declared」 — the caller must not turn an
    unreadable declaration into a refusal of every type.
    """
    _read_entity_declaration()
    return frozenset(_entity_key_order or ())


def _declared_plural_attributes(entity_type):
    """Which of this type's attribute names hold SEVERAL values (S-144, 판정 327)."""
    _read_entity_declaration()
    return _entity_plural_attributes.get(_bare(str(entity_type))) or frozenset()



#: The three answers a walk may give about 「is this predicate true of this subject」
#: (S-149, 판정 338·339). 🔴 `unknown` IS A VALUE, NOT A GAP -- a guard must be able to refuse
#: on it, which it cannot do if 「cannot say」 renders as `false`.
VERDICT_TRUE = "true"
VERDICT_FALSE = "false"
VERDICT_UNKNOWN = "unknown"

#: Why a verdict is `unknown`, in words that already exist. `not_declared` = the examination
#: predicate this one names is not itself declared; a truncation key (`nodes`, `claims`, …)
#: = the walk was cut, so an absence here may be the budget rather than the world.
#:
#: ⚠️ `not_examined` IS A THIRD WORD AND I ADDED IT. The ruling named two, and measuring the
#: cases turned up one they do not cover: the confirmer IS declared, the walk IS complete,
#: and the examination simply did not happen for this subject. Calling that `not_declared`
#: would be false (it is declared) and calling it a truncation would be false (nothing was
#: cut), so mislabelling it would put a wrong reason where an operator reads one.
WHY_NOT_DECLARED = "not_declared"
WHY_NOT_EXAMINED = "not_examined"


def _absence_verdicts(nodes, complete, cut_reason):
    """What each node can say about the predicates whose absence is confirmable (S-149).

    🔴 THE POPULATION IS THE DECLARATION, NOT THE DATA. `predicates[]` is built from claims
    that were ATTACHED, so a predicate with no claims has no row there -- and a `false`
    verdict is by definition about a predicate with no claims. The set of predicates that
    declared `absence_confirmed_by` is the only population in which 「it did not happen」 can
    be stated at all.

    🔴 `false` IS EARNED, NEVER ASSUMED. It needs three things at once: the examination this
    predicate names happened to THIS subject, this predicate did not, and the walk was
    COMPLETE. Drop any one and a zero is one of the five zeros again -- and a guard built on
    it writes on an absence that was really a budget.

    ⚠️ EMPTY IS THE HONEST ANSWER TODAY. Nothing in the shipped declaration names a
    confirmer yet, so this map is `{}` until an operator writes one. That is the cell
    filling up, not the cell failing.
    """
    _read_entity_declaration()
    confirmers = _absence_confirmers
    if not confirmers:
        return
    for node in nodes.values():
        if node.get("node_kind") not in {"entity", "event"}:
            continue
        counts = {_bare(str(row.get("predicate"))): row.get("count") or 0
                  for row in (node.get("predicates") or ())}
        verdicts = {}
        for finding, (examination, examination_declared) in sorted(confirmers.items()):
            if counts.get(finding):
                verdicts[finding] = {"verdict": VERDICT_TRUE, "why": None}
            elif not examination_declared:
                verdicts[finding] = {"verdict": VERDICT_UNKNOWN,
                                     "why": WHY_NOT_DECLARED}
            elif not counts.get(examination):
                verdicts[finding] = {
                    "verdict": VERDICT_UNKNOWN,
                    # A cut walk may simply not have REACHED the examination, so the budget
                    # is the honest reason when there was one.
                    "why": cut_reason or WHY_NOT_EXAMINED}
            elif not complete:
                verdicts[finding] = {"verdict": VERDICT_UNKNOWN, "why": cut_reason}
            else:
                verdicts[finding] = {"verdict": VERDICT_FALSE, "why": None}
        node["absence"] = verdicts


def _apply_registrations(nodes, registrations):
    """Fold every registration this walk reached onto its node, by the DECLARED rule.

    🔴 LATEST WINS, AND A DISAGREEMENT IS COUNTED RATHER THAN HIDDEN (S-52 ③, ruling 124).
    "Latest" is the reading rule: a changed attribute wrote a NEW registration and the old
    one stays, so this picks the newest instant and says out loud how many names had more
    than one distinct value. Same value at two instants is NOT a conflict - that is one
    fact stated twice.

    🔴 A NAME THE DECLARATION CALLS `many` IS NOT A DISAGREEMENT (S-144 / A1-2, 판정 327).
    A column holds one value per ROW, so a wafer with two products is two rows and two
    registrations - which this read as one name with two values, counted a conflict, and
    then DROPPED one of them by keeping only the latest. Both were true, and until the
    declaration gained a cell there was no way to say so.

    🔴 THE SHAPE IS FIXED PER NAME, NOT PER ANSWER. A `many` name is a list even when it
    holds one value: 「a list only when there are two」 puts two shapes in one cell, and the
    reader would have to guess which it got.

    A node this walk reached no registration for gets NO KEY, not an empty object: "this
    entity carries no values" and "this walk did not reach its registration" are different
    answers.
    """
    for node_id, by_name in registrations.items():
        node = nodes.get(node_id)
        if node is None:
            continue
        plural = _declared_plural_attributes(str(node.get("type") or ""))
        values, conflicts = {}, 0
        for name, seen in by_name.items():
            if name in plural:
                # Ordered by instant, and the same value at two instants is ONE value -
                # exactly the rule the conflict count already used: that is one fact
                # stated twice, not two facts.
                distinct = {}
                for _at, value in sorted(seen, key=lambda item: item[0]):
                    distinct.setdefault(_canonical(value), value)
                values[name] = list(distinct.values())
                continue
            values[name] = max(seen, key=lambda item: item[0])[1]
            if len({_canonical(value) for _at, value in seen}) > 1:
                conflicts += 1
        node["attributes"] = values
        node["attribute_conflicts"] = conflicts

def _entity_node(entity_type, keys):
    node = explorer._entity(entity_type, keys)
    node.update({"node_kind": "entity", "schema_kind": "entity_instance"})
    order = _declared_key_order(entity_type)
    if order:
        # Same shape as the label `_entity` builds, on the declared order instead of the
        # insertion order.  Types the declaration does not name keep the label they have.
        values = [str(keys.get(name)) for name in order
                  if keys.get(name) is not None and str(keys.get(name)) != ""]
        node["label"] = " / ".join(values[:2]) or str(entity_type)
    return node


def _split_superseded(atoms):
    """`(live, superseded_by)` — 대체된 원자를 «하나뿐인 필터»로 가른다 (S-141).

    🔴 THE FILTER IS `ledger_trace.live_claims` AND THE WALK DOES NOT BUILD ITS OWN.
    Two places deciding 「which claim is current」 is the class this repository keeps
    meeting: they do not error when they disagree, one of them just starts drawing a
    fact that was replaced.

    ⚰️ AND UNTIL NOW THE WALK CALLED NOTHING. `live_claims` had zero product callers, so
    a superseded edge and the edge that replaced it were BOTH drawn. S-133 ④ asserted the
    function directly from a test rather than through this response, which proved the
    filter and not the wiring - 착지는 배선이 아니다.

    ⚠️ SCOPE IS THE FETCHED SET, which is what `live_claims` documents: a correction is
    about the same subject, so the superseding atom rides in the same neighbourhood.
    """
    from ledger import trace

    atoms = list(atoms)
    live = trace.live_claims(atoms)
    if len(live) == len(atoms):
        return atoms, {}
    kept = {str(a.id) for a in live}
    replaced_by = {}
    for atom in atoms:
        if atom.supersedes:
            replaced_by[str(atom.supersedes)] = str(atom.id)
    return live, {k: v for k, v in replaced_by.items() if k not in kept}


def _edge(edge_type, source, target, *, original_predicate=None,
          cardinality=None):
    """One edge. `cardinality` is what the DECLARATION says about this
    predicate (S-133 ④): `one` means the subject carries at most one object
    right now, so a screen can say so instead of guessing from what it drew.

    ⚠️ `None` MEANS 「the declaration did not say」, which is not the same as
    `many`. A synthesised edge and an undeclared predicate both land here, and
    telling a reader `many` about either would be inventing an answer.
    """
    # ⚰️ `witnesses: 1` · `rank: None` · `sources: []` RETIRED 2026-09-13 (S-150, 판정 340).
    # Three constants on every edge with nothing reading them — the `key_types` class
    # (판정 165): a declaration slot with no reader is not a contract, it is a copy. Measured
    # before removing: no client reads an edge's `sources`, `witnesses` or `rank`
    # (`ledger_sources_panel` reads an INGESTION's `sources`, and `rank` on a node is the
    # propagation layer, a different key on a different object).
    #
    # 🔴 `basis` AND `qualifiers` STAY, and that is the same measurement rather than a
    # different opinion: both are FILLED further down from the atom, so they are initialised
    # here rather than constant. Filling the three instead of removing them is the work of
    # the round that gains a caller for them.
    edge_id = f"ledger-evidence-edge:v1:{_token([edge_type, source, target])}"
    return {
        "id": edge_id, "source": source, "target": target,
        "predicate": edge_type, "predicate_label": edge_type,
        "original_predicate": original_predicate,
        "basis": None, "qualifiers": {},
        "cardinality": cardinality,
    }


def _canonical_seed(item):
    """The seed id the ledger can actually be ASKED about.

    🔴 `/declaration` publishes `wafer@1` and the ledger writes `wafer`, so an id
    minted from the spelling the catalogue PRINTS names a `subject_type` that has no rows.
    The walk answered that with an EMPTY graph, and an empty graph reads as
    「여기 아무것도 없다」 rather than
    「버전을 붙여 물으셨습니다」.
    This is NOT leniency being added - it is an ABSENCE being closed: `collect` already
    trims the version on both sides (`_bare` below) and the seed did not, so the two axes
    disagreed about one declaration.

    🔴 THE VERSION BELONGS TO THE DECLARATION, NOT TO THE NAME. `ledger.gaps._bare`
    says exactly that in its own docstring, and this is the same trim.

    🔴 RE-MINTED, NOT ONLY TRIMMED, because the id IS the node's identity. Atoms
    mint their subject id from the BARE type (`entity_id(atom.subject_type, ...)`), so a
    seed keyed on the versioned token and its own evidence keyed on the bare one are TWO
    nodes - the graph would come back with the seed sitting alone beside the very atoms it
    asked for, which is a wrong answer wearing the face of a shy one.

    Anything that is not an entity id comes back UNCHANGED, so `decode_node_id` stays the
    one place that refuses a seed and the refusal keeps its wording.
    """
    text = str(item)
    try:
        entity_type, keys = explorer.decode_entity_id(text)
    except ValueError:
        return text
    bare = _bare(entity_type)
    if bare == entity_type:
        return text
    return explorer.entity_id(bare, keys)


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
        for raw_seed in group:
            # 🔴 ONE PLACE. Canonicalising HERE rather than in the two lists above
            # means the conflict check below compares the same subject to itself: `wafer@1`
            # positive and `wafer` negative are ONE subject asked two ways, and before this
            # they were two keys that both got through.
            item = _canonical_seed(raw_seed)
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
    `parents` is `seed -> {node: (predecessor, predicate)}` so an evidence path is rebuilt
    on demand — the PREDICATE rides with the predecessor (S-183) because a path that says
    only which nodes were visited cannot say how, and the two were being read from
    different places
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
                trail[nxt] = (node, predicate)
                reached_kinds.add(_kind(nxt))
                reach.setdefault(nxt, [0, 0])[slot] += 1
                queue.append((nxt, predicate, direction))
    return reach, parents, kinds


def _trail_back(trail, node_id):
    """`(ids, predicates)` from the seed down to `node_id`, seed first.

    🔴 ONE SEAT (S-183). The ranking's `_evidence` and the row projection's `path` must be
    the same answer — a walk that ranks a node by one path and reports another is two
    walks wearing one name. Both call this.

    ⚠️ THE FIRST PATH THAT REACHED IT, NOT EVERY PATH. `_reach` is breadth-first and writes
    `trail[node]` once, so this is the SHORTEST path from that seed and the only one the
    walk ever knew. Reporting all paths would be a different (and much larger) question;
    it is not answered here and the row projection documents that.
    """
    ids, predicates, cursor = [], [], node_id
    while cursor is not None:
        ids.append(cursor)
        step = trail.get(cursor)
        if step is None:
            break
        cursor, predicate = step
        predicates.append(predicate)
    ids.reverse()
    predicates.reverse()
    return ids, predicates


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
        path, _predicates = _trail_back(trail, node_id)
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
    # 🔴 AND WHERE THE DECLARATION SAYS SO, THE DENOMINATOR IS THE ITEM (S-147-b, 판정 342).
    # The type denominator counted a control that reached `quantity` at all, so an item it
    # never measured still read 0/2 and looked like a real difference. What tells those
    # apart is whether the question was DECIDABLE for that control -- which is exactly the
    # verdict S-149 already folded onto every node.
    #
    # 🔴 `unknown` LEAVES THE DENOMINATOR. That is the whole of the fix: a control that could
    # not be asked becomes 0/0 rather than 0/2, and 0/0 does not read as a difference.
    #
    # ⚠️ AND IT IS NOT A SECOND COMPUTATION. The verdict is already on the node, so this
    # READS rather than re-derives -- counting one fact two ways is a place for the two to
    # disagree.
    #
    # ⚠️ `parents` WAS THE FIRST PLAN AND IT CANNOT ANSWER THIS. Measured: it keeps ONE path
    # per seed, so the predicate it records is whichever arrived first in that seed's walk --
    # `observed` was simply missing from it. That incompleteness is invisible: the lookup just
    # quietly falls through to the type question and the number looks reasonable.
    #
    # ⚠️ A PREDICATE THAT DECLARED NO CONFIRMER FALLS BACK TO THE TYPE, unchanged. Dropping
    # such a candidate from the ranking instead would be a folding rule, and folding is the
    # owner's (판정 332 ①).
    # ⚠️ A CANDIDATE IS CONNECTED BY A SET OF PREDICATES, NOT ONE — the cases reach a defect
    # by `observed` while a control reaches the SAME defect by something else entirely.
    #
    # 🔴 AND IT IS READ FROM THE EDGES, NOT FROM `parents`. Measured while gating this:
    # `parents` keeps ONE path per seed (it exists to rebuild an evidence trail), so the
    # predicate it records is whichever arrived first in that seed's walk -- `observed` was
    # simply absent from it. A set built there is incomplete by construction, and the
    # incompleteness is invisible: it just quietly answers the type question instead.
    arrived_by = {}
    for edge in edges or ():
        predicate = _bare(str(edge.get("predicate") or ""))
        if not predicate:
            continue
        for endpoint in (edge.get("source"), edge.get("target")):
            if endpoint:
                arrived_by.setdefault(endpoint, set()).add(predicate)

    def _reachable(node_type, node_id=None):
        # 🔴 THE ITEM DENOMINATOR NEEDS ONE PREDICATE WHOSE ABSENCE IS CONFIRMABLE. Two would
        # be two different questions about one candidate, and picking between them here would
        # make this function the author of the answer -- so that falls back to the type,
        # which is the answer that shipped.
        confirmable = sorted((arrived_by.get(node_id) or set()) & set(_absence_confirmers))
        if len(confirmable) == 1:
            predicate = confirmable[0]
            pair = [0, 0]
            for seed, sign in seed_signs.items():
                verdict = (((nodes.get(seed) or {}).get("absence") or {})
                           .get(predicate) or {}).get("verdict")
                if verdict in (VERDICT_TRUE, VERDICT_FALSE):
                    pair[0 if sign > 0 else 1] += 1
            return pair
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
        "reachable": _reachable(item["type"], item["id"]),
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
#: The same trim for an ENTITY type: `defect_kind@1` -> `defect_kind`.
#: 🔴 본체는 `declaration_names.bare_name` 하나다 — 이 이름을 쓰던 네 모듈이 «다른 답»을
#: 낼 수 있었다. 앞뒤 공백을 이제 턴다(종전 이 판은 안 텄다).
_bare = _bare_name


#: The columns every row carries whatever it is — asked of the walk, not of a declaration.
#: `depth` first because the first question about a returned node is how far it is from the
#: seed, and `id` is long, so it sits where the eye is not.
ROW_FIXED_COLUMNS = ("type", "depth", "id", "parent_id", "via", "seed",
                     "path", "path_ids")

#: What separates the hops of `path` / `path_ids`. Not a comma: a predicate name cannot
#: contain this, and a reader can see direction in it.
PATH_SEPARATOR = "\u2192"


#: 🔴 EDGE QUALIFIERS RIDE UNDER A PREFIX (S-183-b, 판정 294). The row's subject stays
#: the NODE; `via` is already the one edge fact on it, so that edge's qualifiers are the
#: same fact carried further. The prefix is not decoration - without it an edge qualifier
#: named `gate` and a node qualifier named `gate` are ONE column, and the edge's value
#: would silently overwrite the node's in a table where both are real.
VIA_PREFIX = "via."


def _edge_qualifiers(edges):
    """`(source, target, predicate) -> qualifiers`, indexed BOTH ways.

    ⚠️ Both directions because `_reach` walks an adjacency built from these edges without
    caring which way each was declared - the hop it recorded may be the reverse of the
    edge's own `source`/`target`, and a one-way index would quietly find nothing for half
    the rows.
    """
    index = {}
    for edge in edges or ():
        quals = edge.get("qualifiers")
        if not quals:
            continue
        predicate = edge.get("predicate")
        index[(edge.get("source"), edge.get("target"), predicate)] = quals
        index[(edge.get("target"), edge.get("source"), predicate)] = quals
    return index


def _declared_columns(nodes, entities):
    """The declared column names across the types this walk reached, first-seen order.

    🔴 THE SAME RULE THE CLIENT'S `tableColumns` USES, and the contract vector scores the
    two against each other. For one type it is: the declaration's `keys`, then the
    qualifier names the RESPONSE actually carried, then the declaration's `attributes` —
    names exactly as declared, never written here.

    ⚠️ THE CLIENT RENDERS PER-TYPE SECTIONS AND THIS IS ONE TABLE, so the union is this
    projection's own decision and the vector cannot pin it: a TSV has one header. The rule
    the vector DOES pin is the per-type list; the union is that list, merged in the order
    the types were reached, which is why a node of a type that never declared a column
    leaves it blank rather than shifting its row.
    """
    # 🔴 THE DECLARATION SIDE IS FOLDED TO BARE, NOT THE NODE SIDE (measured live: every
    # declared column came back empty). A node's `type` is ALREADY bare (`wafer`) and the
    # declaration is keyed with its version (`wafer@1`), so looking the node up in the
    # declaration as-is can never match — and folding the node would be folding the half
    # that is already folded. The client does exactly this, in this direction:
    # `bareName(e.type) === bare`.
    declared_by_bare = {}
    for name, spec in (entities or {}).items():
        declared_by_bare.setdefault(_bare(name), spec)
    by_type = {}
    for node in nodes:
        by_type.setdefault(str(node.get("type") or ""), []).append(node)
    columns = []
    for node_type, members in by_type.items():
        spec = declared_by_bare.get(_bare(node_type)) or {}
        names = list(spec.get("keys") or ())
        seen_qualifiers = []
        for node in members:
            for name in (node.get("qualifiers") or {}):
                if name not in seen_qualifiers:
                    seen_qualifiers.append(name)
        names += seen_qualifiers
        names += list(spec.get("attributes") or ())
        for name in names:
            if name not in columns and name not in ROW_FIXED_COLUMNS:
                columns.append(name)
    return columns


def _row_cell(value):
    """One TSV cell. A tab or a newline inside a value would invent a column or a row."""
    if value is None or value is False:
        return ""
    if value is True:
        return "true"
    # 🔴 S-190: THE SAME FUNCTION THE GRID AND THE CSV EXPORT USE. `str()` on a dict is
    # Python's repr -- single quotes, `True`, `None` -- which is not JSON and which nothing
    # downstream can parse. Two spellings of 「this value as text」 is how one cell
    # arrives differently depending on which door the reader came through.
    text = str(wire_text(value))
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def rows_projection(payload, nodes, edges, seed_signs, entities,
                    static_types=()):
    """The walk's answer as TSV — one row per reached node.

    🔴 THE TRUNCATION MARKER IS THE FIRST LINE, ALWAYS. 「끊김 ≠ 없음」: a reader who
    pastes this into a spreadsheet has no other way to learn the walk ran out of budget,
    and a table that is silently short is worse than no table — it answers the question
    wrongly rather than refusing it.

    🔴 `depth` COMES FROM THE PAYLOAD AND `path` FROM THE TRAIL — two different
    traversals ON PURPOSE. `subgraph`'s own BFS stamps `node["depth"]` under the
    follow/hops/backbone budgets; `_reach` re-walks the RESULT graph under further rules.
    Recomputing depth from the trail would make 「`path` 의 술어 수 = `depth`」 true by
    construction and measure nothing. Taking each from its own place makes that gate assert
    the two AGREE, so if it ever goes red it is a finding about the walk.

    ⚠️ ONE PATH — the first that reached the node. `_trail_back` says why.
    """
    reach, parents, _kinds = _reach(nodes, edges, seed_signs, static_types)
    visible = payload.get("nodes") or []
    limits = payload.get("limits") or {}
    truncation = payload.get("truncated") or {}
    # 🔴 THE REASON, NOT A BOOLEAN (measured live: `truncated=true` while the payload said
    # `nodes: False, reason: depth` — the walk simply stopped at the hop count it was ASKED
    # for). A budget it ran out of and a depth it was told to stop at are different facts,
    # and one word for both tells a reader their table is short when it is complete.
    # The response already carries `reason`; this repeats it rather than re-deriving it.
    cut = truncation.get("reason") or "none"

    declared = _declared_columns(visible, entities)
    edge_quals = _edge_qualifiers(edges)
    # First-seen order, and AFTER the declared columns: a row is read identity-first.
    via_columns = []
    for quals in edge_quals.values():
        for name in quals:
            if VIA_PREFIX + str(name) not in via_columns:
                via_columns.append(VIA_PREFIX + str(name))
    header = list(ROW_FIXED_COLUMNS) + declared + via_columns
    lines = ["# truncated=%s nodes=%d limit=%s" % (
        cut, len(visible), limits.get("nodes")),
        "\t".join(header)]

    for node in visible:
        node_id = node.get("id")
        # A node may have been reached from more than one seed; the row belongs to the
        # seed whose trail holds it, and a node on two trails gets a row per seed — 「씨앗
        # 여럿이면 씨앗마다 행」.
        trails = [(seed, trail) for seed, trail in parents.items() if node_id in trail]
        if not trails:
            trails = [(None, {})]
        for seed, trail in trails:
            ids, predicates = _trail_back(trail, node_id) if trail else ([node_id], [])
            values = {
                "type": node.get("type"),
                "depth": node.get("depth"),
                "id": node_id,
                "parent_id": ids[-2] if len(ids) > 1 else None,
                "via": predicates[-1] if predicates else None,
                # A seed row is its OWN seed — it has no trail, and a blank here read as
                # 「this row belongs to no walk」 (measured live on the depth-0 row).
                "seed": seed or (node_id if node.get("depth") in (0, "0") else None),
                "path": PATH_SEPARATOR.join(str(item) for item in predicates),
                "path_ids": PATH_SEPARATOR.join(str(item) for item in ids),
            }
            carried = dict(node.get("keys") or {})
            carried.update(node.get("qualifiers") or {})
            carried.update(node.get("attributes") or {})
            row = [_row_cell(values.get(name)) for name in ROW_FIXED_COLUMNS]
            row += [_row_cell(carried.get(name)) for name in declared]
            # ⚠️ THE SEED ROW HAS NO REACHING EDGE, so its `via.` cells are blank - the
            # honest answer rather than a gap, because nothing walked to it.
            reached_by = (edge_quals.get((ids[-2], node_id, values["via"]))
                          if len(ids) > 1 else None) or {}
            row += [_row_cell(reached_by.get(name[len(VIA_PREFIX):]))
                    for name in via_columns]
            lines.append("\t".join(row))
    return "\n".join(lines) + "\n"


def subgraph(seed_id, lookup, *, hops=DEFAULT_HOPS, direction="both",
             node_limit=DEFAULT_NODE_LIMIT, edge_limit=DEFAULT_EDGE_LIMIT,
             action_lookup=None, follow=None,
             backbone_hops=DEFAULT_BACKBONE_HOPS, static_types=None,
             static_follow=None, follow_keys=None, collect=None,
             cardinalities=None, include_superseded=False, rows=False,
             entities=None, group_by=None, measure=None,
             seed_type=None, seed_limit=DEFAULT_SEED_LIMIT,
             registration_follow=None):
    """Return a typed evidence subgraph from any public node id, or from a signed SET.

    `seed_id` is one opaque id as before, or `{"positive": [ids], "negative": [ids]}`.

    🔴 `collect` IS THE LOAD, `follow` IS THE ROAD, and they are not the same axis.
    Reaching a defect from a wafer means walking THROUGH the dies, so narrowing the walk
    cannot be how a caller says which nodes it wants carried back. `collect` names
    DECLARED ENTITY TYPES to keep in the response's `nodes`; absent, everything comes
    back exactly as before.

    ⚠️ IT CHANGES NOTHING BUT THAT LIST. The walk still follows every step `follow`
    allows - it has to, or the wanted nodes are unreachable - and `propagation` still
    ranks over EVERY node reached, on the owner's 2026-08-28 ruling that the population
    is all of them. Filtering the population here would put two axes into one argument.

    ⚠️ EDGES ARE NOT FILTERED THIS ROUND. Dropping edges whose endpoints were collected
    away would hide the path that explains why a node is in the answer, and deciding that
    is a separate ruling.

    🔴 `observation_mode` and `include_values` left on 2026-08-28 and did NOT come back:
    they chose among node KINDS, and there is one kind now, a declared entity. `collect`
    returned because it chooses among DOMAIN TYPES, which is a different question.
    """
    # 🔴 A DESCRIBED SEED SET (S-148-a, 판정 337). 「전체 ∖ 사례」 could not be asked because
    # 「전체」 had to be SHIPPED as ids, and at 10⁸ that list does not fit a query string. The
    # description is re-evaluated per request, so it is not a stored derivation -- the
    # 2026-08-24 ruling forbids keeping one, and the truth's owner stays the ledger.
    #
    # ⚠️ WITH `negative[]` THIS IS THE WHOLE OF `∖`. No set operator is built: 「everything of
    # this type」 plus 「except these」 are two arguments the walk already knows how to read.
    # ⚠️ A DESCRIPTION IS A NON-EMPTY STRING, AND NOTHING ELSE. A direct call to the route
    # handler leaves FastAPI's `Query` sentinel in this argument and a sentinel is truthy —
    # measured: a bare truthiness test sent a walk that asked for no description off to
    # enumerate subjects, against a connection the caller never opened.
    seed_type = seed_type if isinstance(seed_type, str) and seed_type.strip() else None
    seed_cut = 0
    if seed_type:
        # ⛔ AN UNDECLARED TYPE IS REFUSED BEFORE THE QUERY RUNS, and by name. Asking the
        # ledger for a type the declaration never named returns zero rows, which would read
        # as 「that type has no subjects」 -- a fact about the data rather than about the
        # request. The walk already refuses an undeclared `collect` this way.
        declared = _declared_entity_facts_names()
        if declared and _bare(str(seed_type)) not in declared:
            raise AggregateRefused(
                "seed_type_not_declared",
                "no declared entity type named %r" % (seed_type,), sorted(declared))
        described = lookup.subjects_of_type(seed_type, seed_limit)
        seed_cut = described.cut
        if not described.ids:
            raise ValueError(
                "no registered subject of type %r; nothing to walk from" % (seed_type,))
        negatives = list((seed_id or {}).get("negative") or ()) if isinstance(
            seed_id, dict) else []
        # 🔴 THE EXCEPTED SUBJECTS LEAVE THE DESCRIBED SIDE — this subtraction IS the set
        # difference, and it is why no operator had to be built. Measured while writing the
        # gate: leaving them in both sides trips `_signed_seeds`'s own refusal 「a seed
        # cannot be both observed and a control」, which is that guard correctly saying the
        # request contradicted itself.
        excepted = set(negatives)
        seed_id = {"positive": [item for item in described.ids if item not in excepted],
                   "negative": negatives}
        if not seed_id["positive"]:
            raise ValueError(
                "every registered subject of type %r is named as a control; nothing is "
                "left to walk from" % (seed_type,))
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
    # 🔴 THE CONTEXT IS TAKEN FROM THE SEEDS, ONCE, AND NEVER CHANGES. The owner's sentence
    # is "an edge carrying those keys walks only to nodes whose keys match THE SEED", so the
    # comparison has a fixed right-hand side. Deriving it from the previous node instead
    # would make it path-dependent - the same node reachable two ways would answer two
    # different questions, and the walk would need per-path state it deliberately does not
    # have (`nodes`, `depths` and `arrivals` are all keyed by node id alone).
    #
    # 🔴 AND A SEED THAT CANNOT CARRY THE KEY IS REFUSED, NOT ANSWERED WITH ZERO. Asking a
    # wafer seed for `inspected:x,y` is asking something unsatisfiable; zero would render
    # exactly like "there is nothing there" and the caller could not tell the two apart.
    seed_key_sets = {}
    for predicate, key_names in (follow_keys or {}).items():
        if not key_names:
            continue
        wanted = []
        for ref in seed_refs.values():
            keys = (ref or {}).get("keys") or {}
            missing = [name for name in key_names if name not in keys]
            if missing:
                raise ValueError(
                    f"follow={predicate}:{','.join(key_names)} cannot be satisfied: the "
                    f"seed {ref.get('type')} has no {', '.join(missing)}. A seed that "
                    f"cannot carry the key would match nothing, and an empty graph reads "
                    f"as 'there is nothing here'.")
            wanted.append(tuple(_json_key(keys[name]) for name in key_names))
        seed_key_sets[str(predicate).split("@", 1)[0]] = (tuple(key_names), set(wanted))
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
    # moved to `_archive/ledger_api/` on 2026-08-28 once the consumer count reached zero,
    # 🪦 and that archive directory was deleted on 2026-09-13 (S-210, 판정 353) - the file
    # is in this repository's history and nowhere in its tree.

    nodes = {}
    #: node id -> {attribute name: [(occurred_at, value)]}. Filled by ONE sweep after the
    #: walk finishes -- not by the expansion, because what the expansion sees is whatever
    #: `follow` fetched and a node's own columns must not depend on which roads were asked
    #: for. Spent once just before the nodes are ordered, so "latest wins" is decided in one
    #: place with the whole set in hand rather than per atom as they arrive.
    registrations: dict = {}
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
    #: [S-141] 대체돼서 «안 그린» 원자 수. 절단처럼 «숨기지 않고 센다».
    superseded_dropped = 0
    #: 대체된 원자 id -> 그것을 대체한 원자 id (include_superseded 일 때 표지로 쓴다).
    superseded_by = {}
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
                     original_predicate=atom.predicate,
                     cardinality=(cardinalities or {}).get(
                         str(atom.predicate).split("@", 1)[0]))
        edge["claim_id"] = atom.id
        edge["occurred_at"] = _instant(atom.occurred_at)
        edge["source_who"] = atom.source_who
        edge["basis"] = atom.source_raw_ref
        edge["qualifiers"] = dict((atom.object_payload or {}).get("qualifiers") or {})
        # ⚠️ include_superseded 로 «일부러» 그린 엣지에만 붙는 표지 (S-141). 기본 걷기는
        # 이 원자를 애초에 안 그리므로 이 키가 없고, 있으면 「이건 대체된 것」이다.
        replaced = superseded_by.get(str(atom.id))
        if replaced:
            edge["superseded_by"] = replaced
        return edge

    def _record_registration(atom):
        """File one registration's qualifiers under its SUBJECT. The only recorder.

        🔴 A REGISTRATION SAYS WHAT ITS SUBJECT IS -- the entity's own values ride in the
        qualifiers -- so this is where a node's columns come from.

        ⛔ AND IT IS ONE CALLER, DELIBERATELY. The expansion used to record these too, from
        whatever `follow` happened to fetch; that is exactly the dependence S-52-i removes,
        and once the sweep below asks for EVERY node the second call could only ever record
        a subset of what the first already had. Which atoms these are is stated once, by the
        sweep's `registration_follow`, rather than restated as a predicate check here.
        """
        subject_id = explorer.entity_id(atom.subject_type, atom.subject_keys)
        for name, value in ((atom.object_payload or {}).get("qualifiers") or {}).items():
            registrations.setdefault(subject_id, {}).setdefault(name, []).append(
                (atom.occurred_at, value))

    def _expand_atom(atom, depth, frontier_entities):
        """Materialise one atom's far side and the single edge that carries it."""
        subject_id = explorer.entity_id(atom.subject_type, atom.subject_keys)
        # 🔴 EVERY REGISTRATION THIS WALK TOUCHED, RECORDED BEFORE ANY BRANCH (S-52 ③).
        # A registration says what its SUBJECT is - the entity's own values ride in the
        # qualifiers - so this is where a node's columns come from. Taken at the top
        # because the branches below return early on several paths, and a registration
        # dropped there would look exactly like an attribute nobody declared.
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
        # 🔴 THE KEY CONSTRAINT, ON THE FAR NODE ONLY. An edge whose predicate was named
        # with keys may only land on a node matching the SEED on those keys - so a hop out
        # to a container and back does not hand over the container's OTHER children.
        # The adjacent-reversal guard cannot do this: it fires only when the two steps use
        # the SAME predicate, and the path this exists for never repeats one.
        #
        # 🔴 NO DOMAIN WORD DECIDES ANYTHING HERE. Which keys are a seat and which are a
        # vessel is not knowledge this file has or needs - the request names the keys and
        # the entity's own key names are what it names them by.
        constraint = seed_key_sets.get(_bare(atom.predicate))
        if constraint is not None:
            key_names, allowed = constraint
            far_keys = None
            if subject_near and not target_near:
                far_keys = (payload.get("keys") or {}) if target is not None else None
            elif target_near and not subject_near:
                far_keys = atom.subject_keys or {}
            # Both ends already on the frontier means this step advances nobody, so there is
            # no far node to constrain - dropping it would remove an edge between two nodes
            # the walk already holds.
            if far_keys is not None:
                if any(name not in far_keys for name in key_names):
                    return
                if tuple(_json_key(far_keys[name]) for name in key_names) not in allowed:
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
            # 🔴 대체된 원자를 «여기서» 거른다 (S-141). 필터는 `live_claims` 하나이고
            # 걷기는 자기 필터를 짓지 않는다. 뺀 수는 아래 응답이 «이름 대어» 말한다.
            live, replaced_by = _split_superseded(batch)
            superseded_by.update(replaced_by)
            if not include_superseded:
                superseded_dropped += len(batch) - len(live)
                batch = live
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
    # 🔴 A NODE'S OWN COLUMNS DO NOT COME THROUGH `follow` (S-52-i). A registration is the
    # entity DESCRIBING ITSELF, not a predicate anybody walks -- 「술어가 아닌 것은 노드」 --
    # and every screen seat declares `follow` as the predicates that seat cares about. So a
    # walk with `follow=['has_netdie']` returned its `dtjob` node with the attribute column
    # permanently empty, which reads as "this entity carries no values" and means "this walk
    # never asked".
    #
    # 🔴 ONE QUERY FOR THE WHOLE RESULT. Every entity node is asked at once, through the same
    # `claims_for_entities` the walk uses; a query per node would be a walk-sized fan-out on
    # the request path. The atoms land through `_record_registration`, the same recorder the
    # expansion uses, so a walk that DID follow `register` and one that did not cannot come
    # back with different values.
    #
    # ⚠️ A TRUNCATED SWEEP IS SAID OUT LOUD rather than left to look like an absence: the cut
    # rides the flag `truncated` already carries for a walk that ran out of claims.
    # {red} WHICH PREDICATE THAT IS COMES FROM THE DECLARATION, NOT FROM HERE (S-263).
    # This read `follow=["register"]` - a domain word in the code, so an installation that
    # calls its registration anything else got every attribute column permanently empty and
    # nothing said so. `trace_router._self_describing_predicates()` answers it: a sentence
    # the declaration gives NO OBJECT is a sentence about its subject. Empty means this
    # walk carries no columns, and the seat that can explain why - the declaration - is the
    # caller's, not this module's: `ledger_subgraph` reads no declaration at all.
    registration_refs = []
    if registration_follow:
        for node in nodes.values():
            try:
                ref = decode_node_id(node["id"])
            except ValueError:
                continue
            registration_refs.append((ref["type"], ref["keys"]))
    if registration_refs:
        # Generous on purpose (owner, 2026-09-08: 「성능 마진 넉넉하게」). An entity registers
        # once per distinct attribute STATE, so a node with eight generations of one name is
        # already extraordinary; the multiplier is what stops a long-lived entity's history
        # from crowding out a short-lived one's current values.
        found, registration_cut = lookup.claims_for_entities(
            registration_refs, "outgoing",
            len(registration_refs) * REGISTRATIONS_FETCHED_PER_NODE,
            follow=sorted(registration_follow))
        claim_cut |= registration_cut
        for atom in found:
            _record_registration(atom)

    # 🔴 LATEST WINS, AND A DISAGREEMENT IS COUNTED RATHER THAN HIDDEN (S-52 ③, ruling
    # 124). "Latest" is the reading rule: a changed attribute wrote a NEW registration and
    # the old one stays, so the walk picks the newest instant and says out loud how many
    # names had more than one distinct value. Same value at two instants is NOT a
    # conflict - that is one fact stated twice.
    #
    # A node the walk reached no registration for gets NO KEY, not an empty object: "this
    # entity carries no values" and "this walk did not reach its registration" are
    # different answers.
    from ledger.setup_bundle import ATTRIBUTE_CARDINALITY_MANY

    _apply_registrations(nodes, registrations)
    ordered_nodes = sorted(nodes.values(), key=lambda item: (
        item["depth"], item["node_kind"], item["label"], item["id"]))
    # 🔴 THE LAST STEP, AND ONLY ON THIS LIST. `nodes` (the dict) still holds everything
    # reached, so `seed` and `propagation` below read the full population - which is the
    # ruling. Versions are stripped on both sides: a caller writes `defect`, the
    # declaration may spell it `defect@1`, and neither should have to know the other's
    # form to ask a question.
    visible_nodes = ordered_nodes
    if collect:
        wanted = {str(name).split("@", 1)[0] for name in collect if str(name).strip()}
        visible_nodes = [item for item in ordered_nodes
                         if str(item.get("type") or "").split("@", 1)[0] in wanted]
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
    # 🔴 SEEDS CUT IS A TRUNCATION LIKE THE OTHERS. A walk that started from 200 of 5,000
    # subjects answered a NARROWER question than the one asked, and `complete` has to say so
    # -- a contrast computed over a fifth of the controls is the skew `propagation.complete`
    # exists to name.
    if seed_cut: reasons.append("seeds")
    # 🔴 THE VERDICTS NEED THE CUTS, so they are folded once the budget is known — the same
    # walk, no second pass over the store.
    _absence_verdicts(nodes, not reasons, reasons[0] if reasons else None)
    payload = {
        # 🪦 [S-13 ③] `schema_version: 3` 이 여기 있었다. 독자가 «0» 이었고(클라 소스·
        #    하니스·계약·서버 시험 전수), 「다를 때 무엇을 하나」가 «어디에도» 안 적혀 있었으며,
        #    3 과 2 의 «뜻 차이»도 기록이 없었다. 형제(파일별 schema_version)는 이미 은퇴했고
        #    문서 세대는 `setup_version` «하나»가 말한다 — 이것은 그 사본이었다.
        # ⛔ `setup_version` 을 여기 «넣지» 않는다. 세대가 필요해지는 날 먼저 적을 것은
        #    「다를 때의 «행동»」이고, 그것은 계약 라운드다.
        "state": "ready" if found else "empty",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed, "nodes": visible_nodes, "edges": ordered_edges,
        # 🔴 WHICH ATTRIBUTE NAMES HOLD SEVERAL VALUES, BY NODE TYPE (S-144, 판정 327).
        # `attributes[name]` is a list for these names and a scalar for every other, so a
        # reader has to know which - and the DECLARATION is where that is written. The
        # server is the declaration's only reader, so it says so here rather than leaving
        # the screen to fetch and parse the ontology for itself.
        #
        # ⚠️ THE DECLARATION'S OWN WORD, AND ITS OWN DEFAULT. Only `many` names appear;
        # absent means `one`, exactly as an absent cell means `one` in the declaration. A
        # second vocabulary for the same idea is how the two start disagreeing.
        # ⚠️ OVER THE TYPES THE RESPONSE CARRIES, not over the ones that happened to reach a
        # registration. It is a fact about the DECLARATION, so a type whose nodes carry no
        # values yet must still say that `product` is a list when it does - otherwise the
        # header a screen draws changes shape as data arrives.
        # 🔴 THE FOLD, OVER THE SET THIS WALK REACHED (S-146, 판정 331). The key is ABSENT
        # when nobody asked - not `null` and not `[]`. 「안 물었다」·「물었는데 아무 무리도
        #없다」·「무리가 있다」 are three answers and a null collapses the first two.
        #
        # ⚠️ IT IS THE SAME WALK AND THE SAME BUDGET. A second walk for the aggregate would
        # put two populations in one answer. Whether this number stands on a whole
        # population is said by `truncated`/`complete` in this same envelope -- one
        # spelling for one fact, rather than a second absence word in here.
        **({} if group_by is None
           else {"groups": group_nodes(visible_nodes, str(group_by),
                                       measure or "count", ordered_edges)}),
        # ⚠️ WHERE A MEASURE NAME IS LOOKED UP, IN ORDER (판정 336). Carried so the screen
        # learns the order rather than guessing it, and so a name answered by two sources
        # is a refusal both sides can explain.
        **({} if group_by is None else {"value_sources": list(VALUE_SOURCES)}),
        "attribute_cardinality": {
            node_type: {name: ATTRIBUTE_CARDINALITY_MANY for name in sorted(plural)}
            for node_type, plural in sorted(
                (str(item.get("type") or ""),
                 _declared_plural_attributes(str(item.get("type") or "")))
                for item in visible_nodes) if plural
        },
        "seeds": [{"id": item, "sign": "+" if seed_signs[item] > 0 else "-",
                   "node_kind": seed_refs[item]["kind"]} for item in seed_signs],
        "propagation": _propagation(
            nodes, ordered_edges, seed_signs,
            not (depth_cut or node_cut or edge_cut or claim_cut or action_cut
                 or seed_cut),
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
            # ⚠️ 이름 대어 «뺀 수»를 말한다 — truncation 과 같은 규율. 0 이면 이 걷기가
            # 대체된 것을 하나도 안 만났다는 뜻이고, 그것도 사실이라 늘 싣는다.
            "superseded_dropped": superseded_dropped,
            "actions_scanned": actions_scanned,
            "enrich_actions": action_lookup is not None,
            "raw_claims": True, "resolver_applied": False,
        },
        "limits": {"nodes": node_limit, "edges": edge_limit,
                   "claims": claim_limit, "actions": edge_limit,
                   "max_hops": MAX_HOPS,
                   # ⚠️ Present only when a DESCRIPTION was asked for: an enumerated seed
                   # list has no ceiling of its own, and a number here would state one.
                   **({"seeds": seed_limit} if seed_type else {})},
        "truncated": {
            "depth": depth_cut, "nodes": node_cut, "edges": edge_cut,
            "claims": claim_cut, "actions": action_cut,
            "reason": ", ".join(reasons) if reasons else None,
            # 🔴 HOW MANY SUBJECTS THE DESCRIPTION NAMED AND THIS WALK DID NOT TAKE
            # (S-148-a). A COUNT rather than a flag, as `interval_excluded` beside it is:
            # 「how much was left out」 is what tells an operator whether to narrow the
            # question. Present only when a description was asked for.
            **({"seeds": seed_cut} if seed_type else {}),
            # 🔴 S-98 / ruling 208. Present ONLY when an interval was asked for - a key
            # that is absent says 「this question was not put」, and a 0 would say 「it was put
            # and nothing was excluded」. Those are different answers and a reader cannot
            # recover the difference from a zero.
            **({} if getattr(lookup, "interval_excluded", None) is None
               else {"interval_excluded": lookup.interval_excluded}),
        },
        "message": None if found else "선택한 노드에 연결된 원장 증거가 없습니다",
    }
    if rows:
        # Folded at the END, from this walk's own structures (S-183). No second route, no
        # second traversal of the source data - the rows ARE this answer, read sideways.
        payload["rows"] = rows_projection(
            payload, nodes, ordered_edges, seed_signs, entities, static_types or ())
    return payload



