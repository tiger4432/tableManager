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

⚠️ ONE EDGE IN THE ORDER CANNOT BE DRAWN FROM DECLARATIONS, AND IT SAYS SO RATHER THAN
GUESSING. A reference view is arbitrary SQL (inline or a `query_ref` file); the normalised
view carries `label`, `query`, `limit`, `candidate_for`, `required_binds` — and NO table
name. Which tables it reads is knowable only by parsing that SQL, which is an inference,
not a declaration. So those views are listed on the rule's own entry with what IS declared,
and the absence is named. See `reference_views` below.
"""
from __future__ import annotations

import time

#: The two node kinds. A table is a catalogue name; the ledger is ONE node, because a
#: ledger source's atoms all land in the same place and drawing fifteen ledger nodes would
#: invent a distinction the declaration does not make.
NODE_TABLE = "table"
NODE_LEDGER = "ledger"
LEDGER_NODE_ID = "(ledger)"


def _chain_rule_file():
    """`chain_rules.json`'s OWN rules, without the enrichment-derived ones.

    ⚠️ `load_chain_rules()` MERGES SYNTHESIZED RULES INTO ITS RETURN, and that is right for
    the worker and wrong for a count. `enrichment_config.load_enrichment_chain_rules`
    derives a dedup chain rule per enrichment rule, so a graph built off the merged list
    would draw every enrichment rule twice and the per-file counts would not add up. The
    synthesized rules are still VISIBLE here — they are in `wakes`, because the worker
    really is woken by them — and that is the honest split: the file says what an operator
    wrote, `wakes` says what runs.
    """
    import json
    import os

    import chain_ingestion_worker as worker

    if not os.path.exists(worker.RULES_PATH):
        return []
    try:
        with open(worker.RULES_PATH, "r", encoding="utf-8") as handle:
            return (json.load(handle) or {}).get("rules") or []
    except Exception:
        return []


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
        }
        if rule.get("trigger_columns"):
            common["trigger_columns"] = list(rule["trigger_columns"])
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
        edge = {
            "kind": "enrich", "from": derived, "to": derived,
            "rule": rule.get("name"),
            "enabled": bool(rule.get("enabled", True)),
            "decision_key": list(rule.get("decision_key") or ()),
        }
        views = rule.get("reference_views") or ()
        if views:
            # ⚠️ THE TABLES THESE READ ARE NOT DECLARED ANYWHERE. What is declared is the
            # label and which binds the view needs; the rest is inside the SQL. Naming the
            # absence beats parsing the SQL and drawing an edge that may be wrong — a
            # wrong arrow on the picture an operator is using to understand the web is
            # worse than a missing one.
            edge["reference_views"] = [
                {"label": view.get("label"),
                 "required_binds": list(view.get("required_binds") or ()),
                 "reads": None}
                for view in views
            ]
            edge["reads_not_declared"] = len(views)
        edges.append(edge)
    return edges


def _vjoin_edges(db, rules):
    """③ `virtual_join_rules`: the right table feeds the left one, at read time."""
    import virtual_join_config as vjc

    edges = []
    for rule in rules:
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


def chain_graph(db):
    """The four declarations on one picture. Reads only; decides nothing."""
    import chain_ingestion_worker as worker
    import enrichment_config
    import virtual_join_config as vjc
    from database import crud

    catalogue = crud.TABLE_CONFIG or {}
    chain_rules = _chain_rule_file()
    try:
        enrichment_rules = enrichment_config.load_enrichment_rules(
            known_tables=catalogue) or []
    except Exception:
        enrichment_rules = []
    try:
        vjoin_rules = vjc.load_virtual_join_rules(known_tables=catalogue) or []
    except Exception:
        vjoin_rules = []

    setup, ledger_error = None, None
    try:
        from ledger.setup import load_setup
        setup = load_setup()
    except Exception as exc:                                    # noqa: BLE001
        ledger_error = f"{type(exc).__name__}: {exc}"

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
    cycles = []
    try:
        worker._validate_chain_cascade_graph(chain_rules)
    except Exception as exc:                                    # noqa: BLE001
        cycles.append(str(exc))

    out = {
        "generated_at": round(time.time(), 3),
        "nodes": nodes,
        "edges": edges,
        "cycles": cycles,
        # The gate's number: what each file declared, so the picture can be checked
        # against the files rather than believed.
        "counts": {
            "chain_rules": len(chain_rules),
            "enrichment_rules": len(enrichment_rules),
            "virtual_joins": len(vjoin_rules),
            "ledger_sources": (0 if setup is None
                               else len(setup.snapshot.source_plans)),
            "edges": len(edges),
            "nodes": len(nodes),
        },
    }
    if ledger_error:
        # Omitted when the ledger loaded: an absent key means 「nothing to say」, and a
        # present one means 「this quarter of the picture is missing, and here is why」.
        out["ledger_error"] = ledger_error
    return out
