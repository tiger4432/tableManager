# -*- coding: utf-8 -*-
"""S-178. One flow, four declarations — drawn from the declarations and nothing else.

Owner: 「chain 이 너무 거미줄 같아」. The web is not in the code; it is in the fact that ONE
flow is written across FOUR files — `chain_rules.json`, `enrichment_rules.json`,
`virtual_join_rules.json` and `ledger_config.json` — and no screen has ever put them on one
picture. An operator asking 「what happens when this table is written?」 has to hold four
files in their head and join them by hand.

🔴 LOGIC ZERO. Nothing here decides anything. Every node and every edge is read out of a
declaration through the loader the PRODUCT uses, so a rule disabled in a file is disabled
here, and a rule this picture shows is a rule that really exists. The live files are read,
never written.

🔴 AND 「WHO WAKES WHOM」 IS ASKED OF THE WORKER'S OWN FUNCTION. `wakes` does not
re-implement the trigger filter — it calls `_group_triggered_rules` with a synthetic event,
which is the same predicate the running worker applies. A second implementation of that
question is how a picture comes to show a wake that does not happen, which is worse than
showing none.

⚠️ WHAT A REFERENCE VIEW READS IS DECLARED OR IT IS UNKNOWN — never parsed (판정 283).
A reference view is arbitrary SQL, so the tables behind it are knowable only by reading that
SQL, and an arrow guessed from it would be a possibly-wrong arrow on the picture an operator
uses to understand the chain. `reads:` is the cell an operator writes; a view without one is
COUNTED as `reads_unknown` rather than drawn as reading nothing.

⚠️ AND TWO WRITERS ON ONE CELL IS A VALUE, NOT A FAULT. Layering decides which wins, and it
decides correctly; what is not normal is nobody being able to see it. `contested` lists
cells with two NAMED writers; `contested_tables` lists tables two writers share where
neither declares a column. They are separate because the second is a weaker claim — the
mappers may touch disjoint columns, and only their Python knows — and folding them into one
list would let a reader take the weaker for the stronger.
"""
from __future__ import annotations

import time

#: The two node kinds. A table is a catalogue name; the ledger is ONE node, because a
#: ledger source's atoms all land in the same place and drawing fifteen ledger nodes would
#: invent a distinction the declaration does not make.
NODE_TABLE = "table"
NODE_LEDGER = "ledger"
LEDGER_NODE_ID = "(ledger)"


def _chain_rules():
    """Every rule THE WORKER RUNS — synthesized ones included (S-179 ①, 판정 293).

    🔴 THE PRODUCT'S LOADER, NEVER THE FILE. CODE_MAP D-10 ① is the rule — 「모든
    노드·엣지는 «제품이 쓰는 로더»로 읽는다」 — and this seat was the exception that proved
    why: reading `chain_rules.json` directly meant the picture could not see a synthesized
    rule at all, so the dedup projection (`source_table` → `derived_table`) was MISSING
    from the graph entirely while the worker ran it on every event.

    ⚰️ THE OLD REASON WAS 「a merged list would draw every enrichment rule twice」, and it
    was not true of the code it was written beside: `_enrich_edges` drew the derived
    table's SELF-LOOP, never the dedup projection, so the two were different edges and
    neither duplicated the other. A file read and a loader are 「같은 기능 두 경로」, and
    this was the half that was wrong.
    """
    from chain import ingestion_worker as worker

    # ⚰️ [S-284] IT USED TO SWALLOW ITS OWN EXCEPTION AND RETURN []. That made 「the file
    # declares nothing」 and 「the file could not be read」 the same answer, one layer below the
    # place that publishes the number. The catch is now at `_quarter`, which is the seat that
    # can tell the picture WHICH of the two happened.
    return worker.load_chain_rules() or []


def _mapper_edges(rules):
    """① `chain_rules`: the trigger table writes the target table."""
    import map_meta_registrar

    edges = []
    for rule in rules:
        source = rule.get("trigger_table")
        if not source:
            continue
        common = {
            "kind": "mapper",
            "rule": rule.get("name"),
            "enabled": bool(rule.get("enabled", True)),
            "allow_chain_trigger": bool(rule.get("allow_chain_trigger")),
            "max_group_attempts": rule.get("max_group_attempts"),
            # 🔴 WHICH FILE THIS CAME FROM, AS A CELL (판정 293-b). The graph used to keep a
            # SECOND reader — the raw file — so it could tell a written rule from a
            # synthesized one; that reader is the 「같은 기능 두 경로」 this round removes, and
            # per-file counts come from here instead. `mapper` is the only kind where the
            # question is ambiguous: `vjoin` and `ledger` name their own file by kind.
            "origin": rule.get("origin") or "file",
        }
        if rule.get("trigger_columns"):
            common["trigger_columns"] = list(rule["trigger_columns"])
        # 🔴 WHAT THE ENRICH SELF-LOOP USED TO CARRY, on the rule that replaced it (S-179 ①).
        # Dropping the old edge without moving these would have made the fold a LOSS of
        # information rather than a change of label — `decision_key` and the reference-view
        # detail are what an operator reads this arrow for.
        params = rule.get("params") or {}
        if params.get("decision_key"):
            common["decision_key"] = list(params["decision_key"])
        views = params.get("reference_views") or ()
        if views:
            common["reference_views"] = [
                {"label": view.get("label"),
                 "required_binds": list(view.get("required_binds") or ()),
                 "reads": list(view["reads"]) if view.get("reads") else None}
                for view in views
            ]
            unknown = [v for v in views if not v.get("reads")]
            if unknown:
                common["reads_unknown"] = len(unknown)
        if rule.get("target_table"):
            edges.append(dict(common, **{"from": source, "to": rule["target_table"]}))
        # 🔴 A RULE CAN WRITE TWO TABLES, AND A PICTURE THAT SHOWS ONE IS THE HALF-GRAPH
        # THAT ALREADY COST A ROUND. `allow_map_metadata_upsert` writes map metadata as
        # well, that write raises its own chain event, and `_validate_chain_cascade_graph`
        # was repaired in 2026-09 precisely because it could not see that edge — a live
        # cycle passed the validator. The metadata table comes from the REGISTRAR, never
        # from the rule: `metadata_target_table` names the mapper's SOURCE in one shipped
        # rule, so borrowing it would draw the arrow backwards.
        if rule.get("allow_map_metadata_upsert"):
            edges.append(dict(common, **{
                "from": source, "to": map_meta_registrar.META_TABLE,
                "via": "allow_map_metadata_upsert"}))
    return edges


def _enrich_edges(rules):
    """② `enrichment_rules`: the derived table feeds itself, and reads reference views."""
    edges = []
    for rule in rules:
        derived = rule.get("derived_table")
        if not derived:
            continue
        # ⚰️ THE SELF-LOOP IS NOT DRAWN HERE ANY MORE (S-179 ①, 판정 292·293). The
        # auto-confirm rule IS a chain rule now, so `_mapper_edges` draws that same
        # `derived → derived` arrow with `kind: "mapper"` and carries this rule's own cells
        # on it from `params`. Drawing it in both places would be the 「같은 기능 두 경로」
        # this round exists to remove; the endpoints do not move, only the label.
        #
        # ⚠️ THE `reads` EDGES BELOW STAY EXACTLY AS THEY ARE, and they keep `kind:
        # "enrich"`. They are a 「이 표를 읽는다」 relation that NO chain rule expresses —
        # folding them too would mean inventing a rule that does not exist. So `enrich`
        # does not reach zero, contrary to what 판정 292 assumed when it queued C-78: the
        # count after this round is the reference-view edges, and the report carries it.
        views = rule.get("reference_views") or ()
        if views:
            # ⚠️ THE TABLES A VIEW READS ARE DECLARED OR THEY ARE UNKNOWN — never parsed
            # (판정 283). A reference view is arbitrary SQL, and an arrow guessed from it
            # would be a possibly-wrong arrow on the picture an operator is using to
            # understand the chain. `reads` is the cell an operator writes; a view without
            # one is COUNTED as unknown rather than drawn as reading nothing.
            pass
        # The declared half, as real edges: a table a view reads feeds the derived table.
        for view in views:
            for table in view.get("reads") or ():
                edges.append({
                    "kind": "enrich", "from": table, "to": derived,
                    "rule": rule.get("name"),
                    "enabled": bool(rule.get("enabled", True)),
                    "via_reference_view": view.get("label"),
                    # These come from enrichment_rules.json itself, not from a synthesized
                    # chain rule — the reads relation has no chain rule to be synthesized
                    # from (판정 293-b).
                    "origin": "file",
                })
    return edges


def _contested(chain_rules, enrichment_rules, vjoin_rules):
    """Cells more than one declaration writes — a VALUE, not an error (소유자 「이 둘이
    충돌 안 나?」).

    🔴 IT IS NOT A FAULT AND MUST NOT BE DRAWN AS ONE. Layering is what decides which
    writer wins, and it decides correctly; two rules feeding one cell is a normal and
    sometimes intended shape. What is NOT normal is nobody being able to see it — an
    operator debugging a value has to know that a second declaration also writes there,
    and today that fact is spread across three files.

    ⚠️ THE THREE WRITERS ARE THE THREE THAT REALLY WRITE, and a virtual join is included
    deliberately even though it writes nothing to disk: it PRESENTS a column on the left
    table, so a reader of that cell sees the join's value where a mapper's value may also
    be. For a `collide` column those are the same cell with two sources, which is exactly
    the question being asked.
    """
    writers = {}

    def _claim(table, column, who):
        if table and column:
            writers.setdefault((table, column), set()).add(who)

    for rule in chain_rules:
        # ⚠️ `target_field` IS THE ONLY COLUMN A CHAIN RULE DECLARES, and most rules declare
        # none — a mapper returns whatever columns it returns, and that is Python, not a
        # declaration. So this list is COMPLETE FOR DECLARED CELLS and silent about the
        # rest; `contested_tables` below says where two rules share a TABLE without either
        # naming a column, which is the most that can be read without running a mapper.
        declared = rule.get("target_field")
        for column in ([declared] if isinstance(declared, str) else (declared or ())):
            _claim(rule.get("target_table"), column, rule.get("name"))
    for rule in enrichment_rules:
        for column in rule.get("target_fields") or ():
            _claim(rule.get("derived_table"), column, rule.get("name"))
    for rule in vjoin_rules:
        for column in rule.get("expose") or ():
            _claim(rule.get("left_table"), column, rule.get("name"))

    return [
        {"table": table, "column": column, "writers": sorted(who)}
        for (table, column), who in sorted(writers.items())
        if len(who) > 1
    ]


def _contested_tables(chain_rules, enrichment_rules):
    """Tables two writers share where neither DECLARES a column (S-178 ②).

    ⚠️ SEPARATE FROM `contested`, AND DELIBERATELY WEAKER. A cell with two named writers is
    a fact; a table with two writers is a question — they may touch disjoint columns, and
    only the mapper's Python knows. Publishing them in one list would let a reader take the
    weaker claim for the stronger one, which is the whole shape this graph exists to stop.
    """
    writers = {}
    for rule in chain_rules:
        if not rule.get("target_field") and rule.get("target_table"):
            writers.setdefault(rule["target_table"], set()).add(rule.get("name"))
    for rule in enrichment_rules:
        if rule.get("derived_table") in writers:
            writers[rule["derived_table"]].add(rule.get("name"))
    return [{"table": table, "writers": sorted(who)}
            for table, who in sorted(writers.items()) if len(who) > 1]


def _vjoin_edges(db, rules):
    """③ `virtual_join_rules`: the right table feeds the left one, at read time.

    🔴 A MATERIALISED RULE IS NOT DRAWN HERE (S-189 ⓒ). It is a chain rule now — synthesised
    as `builtin:join` — so `_mapper_edges` above already draws it from the loader, carrying
    its `origin: synthesized:<name>`. Drawing it in both places would put TWO arrows between
    the same pair of tables for one declaration, and a reader counting arrows would see a
    flow that does not exist.

⚰️ THIS SAID 「THE READ-TIME RULES STAY, and on this box that is both of them」 AND
    BOTH HALVES OF THAT ARE NOW WRONG. It was not an aside - it was the PREMISE of the
    arrows drawn below, so a reader took them for a flow that still runs everywhere.

    🔴 THEY DO NOT ALL STAY. A read-time join written in the UNIFIED file is refused by
    name (`rule_shape.READ_TIME_RETIRED`, 판정 440 ①), so those never reach this loop. What
    still reaches it is a declaration in the legacy `virtual_join_rules.json`; 판정 446
    retires that doorway too, and when it lands this loop is handed an empty list.

    ⛔ AND THE SECOND HALF WAS A COUNT OF THIS BOX, IN A COMMENT. 「both of them」 described
    a gitignored file, so it said nothing about any other installation and went stale the
    moment that file changed - which is the thing this repository forbids in answers and had
    written into a docstring.

    🔴 THE LOOP IS KEPT, AND THE ARROW IT DRAWS IS WHY. A read-time arrow means the right
    table feeds the left WITHOUT writing - the distinction a materialised rule stops making -
    so while any rule still reaches here the picture tells the operator which kind it is.
    What it must never do is draw an arrow for a declaration the product refused, and it
    cannot: every refusal happens in the loader, above this.
    """
    from chain import legacy_join_declaration as vjc

    edges = []
    for rule in rules:
        if rule.get("materialize"):
            continue
        left, right = rule.get("left_table"), rule.get("right_table")
        if not (left and right):
            continue
        # ⛔ THE INDEX IS ASKED OF THE DATABASE, NOT ASSUMED FROM THE DECLARATION. A join
        # is only in effect when a UNIQUE index really covers its right key, so a picture
        # that drew every declared rule as live would show joins that are not happening.
        try:
            index = vjc.unique_index_covering(
                db, right, rule.get("right_columns") or [],
                rule.get("right_folds") or [])
        except Exception:
            index = None
        edges.append({
            "kind": "vjoin", "from": right, "to": left,
            "rule": rule.get("name"),
            "enabled": bool(rule.get("enabled", True)),
            "unique_index": index,
            "expose": list(rule.get("expose") or ()),
        })
    return edges


def _ledger_edges(db, setup):
    """④ `ledger_config`: a source's relation feeds the ledger. A view feeds it through
    its base tables, which `followup.base_tables_of` already knows how to find."""
    from ledger import followup

    engine = db.get_bind()
    edges = []
    for source_id, plan in sorted(getattr(setup.snapshot, "source_plans", {}).items()):
        relation = plan.relation
        if not relation:
            continue
        try:
            bases = followup.base_tables_of(engine, relation) or (relation,)
        except Exception:
            bases = (relation,)
        for base in bases:
            edge = {
                "kind": "ledger", "from": base, "to": LEDGER_NODE_ID,
                "source": source_id,
                "status": plan.status,
                "planned": bool(getattr(plan, "planned", True)),
            }
            if base != relation:
                # The source reads a VIEW; the arrow starts at what the view really reads,
                # because that is the table whose event wakes the follow-up.
                edge["via_view"] = relation
            if not getattr(plan, "planned", True) and getattr(plan, "refusal", None):
                edge["refusal"] = dict(plan.refusal)
            edges.append(edge)
    return edges


def _wakes(worker, rules, table):
    """Which rules an event on `table` wakes — asked of the WORKER'S OWN function.

    Two answers, because the declaration draws the distinction: an ordinary write wakes
    every enabled rule on that table, and a CHAIN-produced write wakes only the rules that
    opted in with `allow_chain_trigger`. That opt-in is most of what makes the web a web,
    so it is a value here rather than something a reader infers from the edges.
    """
    def _ask(source_name):
        event = type("Event", (), {
            "table_name": table, "event_type": "CREATE",
            "payload": {"source_name": source_name}})()
        return sorted(
            r.get("name") for r in worker._group_triggered_rules([event], rules)
            if r.get("name"))

    return {"user": _ask("user"), "chain": _ask("chain_ingestion")}


#: 🔴 [S-284] ONE SEAT ASKS 「WHICH KIND OF ANSWER WAS THAT」, FOR EVERY QUARTER.
#: Three states reach this picture and they used to arrive as the same pixel:
#:     read it, nothing declared   -> the number IS 0, and that 0 is an answer
#:     could not read it           -> there is NO number. Publishing 0 says 「none declared」
#:     read it, product refused it -> the opposite of 「none declared」: the file has one
#: The operator's action differs in all three - do nothing / fix a breakage / fix a
#: declaration - so folding them reads two of the three as the first.
#:
#: ⚠️ 「말 안 함」 IS AN ABSENT KEY, NOT A ZERO (판정 445 ④). `countLine` on the screen draws
#: whatever keys the response carries, in the order it carries them, so dropping the key is
#: literally how the number stops being drawn - and the client needs no change to obey it.
#: The refused count is omitted when it is zero for the same reason `contested` is: a line
#: that is always on says nothing and only makes the head longer.
def _quarter(name, load, counts, unread, catalogue):
    """Load one declaration and record WHICH of the three answers came back.

    `load` takes the rejections list, because a loader that can refuse must be ASKED to
    report it - `chain_graph` passed none, so 「declared but refused」 arrived here as 「none
    declared」 with nothing to distinguish them (S-284, the 450 ① shape).
    """
    rejections = []
    try:
        rules = load(rejections) or []
    except Exception as exc:                                        # noqa: BLE001
        unread[name] = "%s: %s" % (type(exc).__name__, exc)
        return []
    counts[name] = len(rules)
    if rejections:
        counts["%s_refused" % name] = len(rejections)
    return rules


def chain_graph(db):
    """The four declarations on one picture. Reads only; decides nothing."""
    from chain import ingestion_worker as worker
    from chain import enrichment
    from chain import legacy_join_declaration as vjc
    from database import crud

    catalogue = crud.TABLE_CONFIG or {}
    counts, unread = {}, {}

    chain_rules = _quarter(
        "chain_rules", lambda rej: _chain_rules(), counts, unread, catalogue)
    enrichment_rules = _quarter(
        "enrichment_rules",
        lambda rej: enrichment.config.load_enrichment_rules(
            known_tables=catalogue, rejections=rej),
        counts, unread, catalogue)
    vjoin_rules = _quarter(
        "virtual_joins",
        lambda rej: vjc.load_virtual_join_rules(known_tables=catalogue, rejections=rej),
        counts, unread, catalogue)

    setup = None

    def _load_ledger(_rej):
        nonlocal setup
        from ledger.setup import load_setup
        setup = load_setup()
        return list(setup.snapshot.source_plans)

    _quarter("ledger_sources", _load_ledger, counts, unread, catalogue)

    edges = (_mapper_edges(chain_rules)
             + _enrich_edges(enrichment_rules)
             + _vjoin_edges(db, vjoin_rules))
    if setup is not None:
        edges += _ledger_edges(db, setup)

    # ⚠️ `wakes` USES THE MERGED RULE LIST, because that is what the worker filters. The
    # enrichment-derived rules are part of what really wakes, and a picture that showed
    # only the hand-written file would answer 「nothing wakes」 for a table the chain
    # demonstrably picks up.
    try:
        live_rules = worker.load_chain_rules() or []
    except Exception:
        live_rules = chain_rules

    names = {edge["from"] for edge in edges} | {edge["to"] for edge in edges}
    names.discard(LEDGER_NODE_ID)
    names |= set(catalogue)
    nodes = [{"id": name, "kind": NODE_TABLE, "declared": name in catalogue,
              "wakes": _wakes(worker, live_rules, name)}
             for name in sorted(names)]
    nodes.append({"id": LEDGER_NODE_ID, "kind": NODE_LEDGER})

    # 🔴 A CYCLE THE LOADER REFUSED IS PART OF THE PICTURE. It is the one thing an
    # operator cannot see anywhere else: the rule is in the file, looks live, and the
    # worker refused the whole document over it.
    # ⚰️ IT USED TO CATCH AN EXCEPTION HERE. 판정 402 made the cycle a reported SHAPE rather
    # than a refusal, so the validator returns what it found and this reads it - the screen
    # shows exactly what it showed before, from a value instead of a raise.
    cycles = list(worker._validate_chain_cascade_graph(chain_rules) or ())

    out = {
        "generated_at": round(time.time(), 3),
        "nodes": nodes,
        "edges": edges,
        "cycles": cycles,
        "contested": _contested(chain_rules, enrichment_rules, vjoin_rules),
        "contested_tables": _contested_tables(chain_rules, enrichment_rules),
        # The gate's number: what each file declared, so the picture can be checked
        # against the files rather than believed.
        #
        # 🔴 [S-284] THE FOUR DECLARATION COUNTS ARE PUT THERE BY `_quarter`, NOT HERE, and a
        # quarter that could not be read has NO KEY. These two are computed rather than
        # loaded, so they are always answerable and always present.
        "counts": dict(counts, edges=len(edges), nodes=len(nodes)),
    }
    out["counts"]["contested"] = len(out["contested"])
    out["counts"]["contested_tables"] = len(out["contested_tables"])
    if unread:
        # 🔴 [S-284] WHICH QUARTER COULD NOT BE READ, AND WHY. Absent when everything loaded:
        # an absent key means 「nothing to say」, a present one means 「this part of the
        # picture is missing, and here is the reason」 - and its count is absent beside it,
        # so the screen draws no number rather than a zero.
        out["unread"] = dict(unread)
    if "ledger_sources" in unread:
        # ⚠️ [S-284] THE SAME FACT, UNDER THE NAME THE CLIENT ALREADY READS. `chain_graph.js`
        # renders `ledger_error` and knows nothing about `unread` yet, so dropping this key
        # would turn a repair into a blank line. It is DERIVED from the one seat rather than
        # computed a second time - two authors of one sentence is how they come to disagree -
        # and it retires the day the client reads `unread`. That is a joint round.
        out["ledger_error"] = unread["ledger_sources"]
    return out
