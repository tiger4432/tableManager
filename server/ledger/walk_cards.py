"""The agent walk's cards (e38466810, owner 10-20): what a walk shows about where it stands - one function per card
name, each -> {"card", "items", "more"}. The LLM gets them as text (`utils.text_links.walk_context`) and the walk
route's answer carries two as cells (a0ca0428c: `branches` · `missing_edges`) - the same functions on the same
answer, never a second computation.

A card reads `Sight` - the question, where the walk stands, the one-hop walk answer around it (taken once, by the
caller) and the walk so far. It does not walk. Which cards a state carries is the recipe table's (`walk_recipe`), asked
in one place (`text_links.walk_context`); a card name not in `CARDS` is refused by name.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field

OUTGOING, INCOMING = "outgoing", "incoming"
#: A word of the question long enough to search node keys by (`key_candidates`).
WORD = re.compile(r"[\w.\-]{3,}", re.UNICODE)


class UnknownCard(ValueError):
    """A recipe row names a card no function answers."""


@dataclass
class Sight:
    """What the cards read. `at` the nodes a branch card stands on (the walk's position; a marking's nodes),
    `signs` their sign (+1 / -1) where the walk answered a contrast; `answer` the one-hop walk answer around `at`;
    `path` the log rows so far, oldest first ({step, position, chosen, reason, cards}); `db` a session the node
    searches run on."""
    question: str = ""
    at: list = field(default_factory=list)
    signs: dict = field(default_factory=dict)
    answer: dict = None
    declaration: dict = None
    path: list = field(default_factory=list)
    meanings: list = field(default_factory=list)
    hops_left: int = None
    calls_left: int = None
    db: object = None


def _bare(name):
    from declaration_names import bare_name

    return bare_name(str(name or ""))


def _cut(items, limit):
    limit = None if limit is None else max(int(limit), 0)
    if limit is None or len(items) <= limit:
        return items, 0
    return items[:limit], len(items) - limit


def _out(name, items, limit):
    kept, more = _cut(list(items), limit)
    return {"card": name, "items": kept, "more": more}


def _entities(sight):
    return ((sight.declaration or {}).get("entities") or {})


def _nodes(sight):
    return {node["id"]: node for node in ((sight.answer or {}).get("nodes") or ())}


def _node_type(node_id, nodes):
    node = nodes.get(node_id)
    if node is not None:
        return _bare(node.get("type"))
    from ledger_api import ledger_subgraph

    try:
        return _bare(ledger_subgraph.decode_node_id(node_id).get("type"))
    except ValueError:
        return None


def key_values(sight, node_type, limit, starts_with=None):
    """The node search (`GET /api/ledger/key-values`), called in this process on the sight's session."""
    from fastapi import HTTPException

    from ledger import trace_router

    try:
        return trace_router.ledger_key_values(type=node_type, key=None, limit=max(int(limit), 1), world=None,
                                              starts_with=starts_with, db=sight.db)
    except HTTPException:
        return None


# --------------------------------------------------------------------------- not walked yet

def node_types(sight, limit=None, argument=None):
    """The declared node types and each one's keys in their declared order."""
    return _out("node_types", ({"type": _bare(name), "keys": list((spec or {}).get("keys") or [])}
                               for name, spec in _entities(sight).items()), limit)


def key_shapes(sight, limit=None, argument=None):
    """Per declared type, its keys and the first `limit` nodes' key values (the node search's first page)."""
    items = []
    for name, spec in _entities(sight).items():
        found = key_values(sight, _bare(name), limit or 3)
        items.append({"type": _bare(name), "keys": list((spec or {}).get("keys") or []),
                      "sample": [node["keys"] for node in (found or {}).get("nodes") or ()]})
    return _out("key_shapes", items, None)


def node_count(sight, limit=None, argument=None):
    """Per declared type, how many nodes the node search saw - `at_least` when it stopped at its scan budget."""
    from ledger import trace_router

    items = []
    for name in _entities(sight):
        found = key_values(sight, _bare(name), trace_router.KEY_VALUE_MAX_LIMIT) or {}
        items.append({"type": _bare(name), "count": found.get("scanned", 0),
                      "at_least": bool(found.get("scan_truncated") or found.get("values_truncated"))})
    return _out("node_count", items, limit)


def meanings(sight, limit=None, argument=None):
    """The meaning table's rows that hold a meaning."""
    from database import crud

    return _out("meanings", ({"kind": row["target_kind"], "name": row["target_name"], "meaning": row["meaning"]}
                             for row in sight.meanings if not crud.is_blank_value(row.get("meaning"))), limit)


def key_candidates(sight, limit=None, argument=None):
    """Nodes whose first key starts with a word of the question - the node search, per type and word."""
    from ledger import explorer

    words = list(dict.fromkeys(WORD.findall(sight.question or "")))
    items, seen = [], set()
    for name in _entities(sight):
        for word in words:
            found = key_values(sight, _bare(name), limit or 5, starts_with=word)
            for node in (found or {}).get("nodes") or ():
                node_id = explorer.entity_id(_bare(name), node["keys"])
                if node_id not in seen:
                    seen.add(node_id)
                    items.append({"id": node_id, "type": _bare(name), "keys": node["keys"], "word": word})
    return _out("key_candidates", items, limit)


# --------------------------------------------------------------------------- on a node

def _branches(sight):
    """{(at node, bare predicate, direction, far type): far node ids} from the answer's edges at `sight.at`, and the
    bundles' undrawn counts on the same keys."""
    nodes, at = _nodes(sight), set(sight.at)
    far = defaultdict(list)
    for edge in (sight.answer or {}).get("edges") or ():
        for here, there, direction in ((edge["source"], edge["target"], OUTGOING),
                                       (edge["target"], edge["source"], INCOMING)):
            if here in at:
                key = (here, _bare(edge.get("predicate")), direction, _node_type(there, nodes))
                if there not in far[key]:
                    far[key].append(there)
    undrawn = defaultdict(int)
    for bundle in (sight.answer or {}).get("bundles") or ():
        if bundle.get("node") in at:
            key = (bundle["node"], _bare(bundle.get("predicate")), bundle.get("direction"),
                   _bare(bundle.get("far_type")))
            undrawn[key] += int(bundle.get("count") or 0) - int(bundle.get("drawn") or 0)
            far.setdefault(key, [])
    return far, undrawn


def edges(sight, limit=None, argument=None):
    """The branches at the nodes it stands on, one per (predicate, direction, far type): how many far nodes, the
    first `limit` of them, and - where the nodes carry a sign - how many came from a positive and a negative one."""
    far, undrawn = _branches(sight)
    grouped = {}
    for (here, predicate, direction, far_type), ids in far.items():
        item = grouped.setdefault((predicate, direction, far_type), {
            "predicate": predicate, "direction": direction, "far_type": far_type, "count": 0, "sample": [],
            "from_positive": 0, "from_negative": 0})
        item["count"] += len(ids) + undrawn.get((here, predicate, direction, far_type), 0)
        item["sample"].extend(i for i in ids if i not in item["sample"])
        sign = sight.signs.get(here)
        if sign is not None:
            item["from_positive" if sign > 0 else "from_negative"] += len(ids)
    items = sorted(grouped.values(), key=lambda i: (i["predicate"], i["direction"], str(i["far_type"])))
    for item in items:
        item["sample"] = item["sample"][:limit] if limit is not None else item["sample"]
        if not sight.signs:
            del item["from_positive"], item["from_negative"]
    return _out("edges", items, None)


def missing_edges(sight, limit=None, argument=None):
    """Per (type, predicate, direction) the declaration gives a node it stands on and that node has no edge of:
    how many such nodes and the first `limit`."""
    from ledger import gaps

    nodes = _nodes(sight)
    far, _undrawn = _branches(sight)
    present = {(here, predicate, direction) for here, predicate, direction, _t in far}
    declared = defaultdict(list)
    for predicate, spec in gaps._vocabulary(sight.declaration).items():
        for subject in gaps._subjects(spec):
            declared[_bare(subject)].append((_bare(predicate), OUTGOING))
        if gaps._object_kind(spec) == "entity_ref":
            for target in gaps._targets(spec):
                declared[_bare(target)].append((_bare(predicate), INCOMING))
    grouped = {}
    for here in sight.at:
        node_type = _node_type(here, nodes)
        for predicate, direction in declared.get(node_type, ()):
            if (here, predicate, direction) not in present:
                item = grouped.setdefault((node_type, predicate, direction), {
                    "type": node_type, "predicate": predicate, "direction": direction, "nodes": 0, "sample": []})
                item["nodes"] += 1
                item["sample"].append(here)
    items = sorted(grouped.values(), key=lambda i: (str(i["type"]), i["predicate"], i["direction"]))
    for item in items:
        item["sample"] = item["sample"][:limit] if limit is not None else item["sample"]
    return _out("missing_edges", items, None)


def mentions(sight, limit=None, argument=None):
    """The far nodes of the predicate `argument` (the recipe row's - a fragment that mentions this node, by
    default `mentions`) at the nodes it stands on, with their labels."""
    if not str(argument or "").strip():
        raise UnknownCard("card 'mentions' needs the predicate it reads in the recipe row's argument")
    nodes, wanted = _nodes(sight), _bare(argument)
    far, _undrawn = _branches(sight)
    items = [{"node": node_id, "label": (nodes.get(node_id) or {}).get("label")}
             for (here, predicate, _d, _t), ids in sorted(far.items(), key=str) if predicate == wanted
             for node_id in ids]
    return _out("mentions", items, limit)


def path(sight, limit=None, argument=None):
    """The hops so far, oldest first."""
    return _out("path", ({key: row.get(key) for key in ("step", "position", "chosen", "reason")}
                         for row in sight.path), None if limit is None else limit)


def budget(sight, limit=None, argument=None):
    return _out("budget", [{"hops_left": sight.hops_left, "calls_left": sight.calls_left}], None)


def question(sight, limit=None, argument=None):
    return _out("question", [{"question": sight.question}], None)


# --------------------------------------------------------------------------- stuck · the end

def dead_end(sight, limit=None, argument=None):
    """The branches earlier hops were shown and did not take, at positions already walked - where to go back to."""
    walked = {row.get("position") for row in sight.path} | set(sight.at)
    items = []
    for row in sight.path:
        for card in row.get("cards") or ():
            if card.get("card") != "edges":
                continue
            for branch in card.get("items") or ():
                left = [i for i in branch.get("sample") or () if i not in walked]
                if left:
                    items.append({"from": row.get("position"), "predicate": branch["predicate"],
                                  "direction": branch["direction"], "far_type": branch["far_type"], "sample": left})
    return _out("dead_end", items, limit)


def full_path(sight, limit=None, argument=None):
    """Every hop - from where, which node it went to, and why - the evidence the answer stands on."""
    items, previous = [], None
    for row in sight.path:
        items.append({"step": row.get("step"), "from": previous, "to": row.get("position"),
                      "reason": row.get("reason")})
        previous = row.get("position")
    return _out("full_path", items, None)


#: 🔴 THE ONE TABLE OF CARD NAMES - a recipe row's `card` is looked up here and nowhere else.
CARDS = {fn.__name__: fn for fn in (node_types, key_shapes, node_count, meanings, key_candidates, edges,
                                    missing_edges, mentions, path, budget, question, dead_end, full_path)}


def card(name, sight, limit=None, argument=None):
    """The card `name` for `sight`, or `UnknownCard` naming it and the names there are."""
    from database import crud

    fn = CARDS.get(str(name or "").strip())
    if fn is None:
        raise UnknownCard("unknown card '%s' - one of %s" % (name, ", ".join(CARDS)))
    # a number cell reads back as a float (5.0)
    return fn(sight, None if crud.is_blank_value(limit) else int(float(limit)), argument)


def answer_cells(answer, at, signs, declaration, limit=None):
    """The walk route answer's two cards (a0ca0428c) - `branches` (the `edges` card) and `missing_edges` - for the
    nodes the walk started from, on that answer; `limit` the far nodes each names."""
    sight = Sight(at=list(at), signs=dict(signs), answer=answer, declaration=declaration)
    return {"branches": edges(sight, limit), "missing_edges": missing_edges(sight, limit)}
