"""`python -m ledger walk-shadow` (lead 11-06): the same walk read two ways - the stored ledger and the declaration read
from its own tables (engine=virtual, `sql_translate.compile_world`) - source by source, on the same seeds, read only.

Each atom one side has and the other has not goes in one bin:
  spelling     the same source row, said differently (a key, a time, a qualifier) - the cells that differ are named
  stale        a row the stored ledger has no atom of yet (translation behind the table), or a second stored copy of an
               atom the virtual read makes once - the same fact of the same row kept from two declaration generations
  stored-only  a stored atom whose row is gone from the table
  real         a stored atom of a row still in the table that the virtual read does not make - the compile is wrong
  time         a difference that shows only with --since / --until
and `tie_split` counts the edges whose newest atoms share their time and whose shown atom (first in
`ledger_subgraph._read_order_key`, lead 11-07) differs between the two reads - 0 when both read the same atoms; it
replaced `tie` (the ties themselves, whichever atom each read drew). Exit 1 when `real` is not 0."""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict

#: «every atom of the seeds» - the read is not cut, so a bin is never a cap
EVERY = 10 ** 7


def _atom_key(atom) -> tuple:
    return (atom.subject_type, json.dumps(atom.subject_keys, sort_keys=True), atom.predicate,
            json.dumps(atom.object_payload, sort_keys=True), atom.occurred_at.isoformat() if atom.occurred_at else None,
            atom.occurred_at_basis, atom.source_raw_ref)


CELLS = ("subject_type", "subject_keys", "predicate", "object_payload", "occurred_at", "basis")


def _edge(key) -> tuple:
    payload = json.loads(key[3])
    return key[0], key[1], key[2], payload.get("type"), json.dumps(payload.get("keys"), sort_keys=True)


def _read(lookup, seeds, follow):
    """(the atoms read, counted; seconds; each edge's atom first in `_read_order_key` - the one it shows)."""
    from ledger_api.ledger_subgraph import _read_order_key

    started = time.perf_counter()
    atoms, cut = lookup.claims_for_entities(seeds, "both", EVERY, follow=follow)
    if cut:
        raise RuntimeError("a read was cut at %d atoms - the bins would count the cap" % EVERY)
    keys, drawn, first = [], {}, {}
    for atom in atoms:
        key, order = _atom_key(atom), _read_order_key(atom)
        keys.append(key)
        if _edge(key) not in first or order > first[_edge(key)]:
            first[_edge(key)], drawn[_edge(key)] = order, key
    return Counter(keys), round(time.perf_counter() - started, 3), drawn


def _rows_present(fetch, relation, order_by, refs) -> set:
    """Of `refs` (row refs `<relation>:{order_by}`), those whose row is in the table now."""
    wanted = sorted({ref.split(":", 1)[1] for ref in refs if ref.startswith(relation + ":")})
    if not wanted:
        return set()
    built = "jsonb_build_object(%s)" % ", ".join(
        "'%s', w.\"%s\"" % (column.replace("'", "''"), column.replace('"', '""')) for column in order_by)
    found = fetch(f"SELECT {built}::text FROM {relation} w WHERE {built} = ANY(CAST(%(rows)s AS jsonb[]))",
                  {"rows": wanted})
    return {relation + ":" + json.dumps(json.loads(text), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for (text,) in found}


def _tie_split(stored, drawn) -> int:
    """Edges whose newest atoms tie in time and whose drawn atom differs between the two reads (lead 11-07)."""
    newest = defaultdict(list)
    for key in stored:
        newest[_edge(key)].append(key[4])
    tied = {edge for edge, times in newest.items() if times.count(max(times, key=str)) > 1}
    return sum(1 for edge in tied if edge in drawn[0] and edge in drawn[1] and drawn[0][edge] != drawn[1][edge])


def shadow(fetch, ledger, plan, stored, virtual, seeds, follow, show=3, window=None) -> dict:
    """One source, one seed set: the two reads, their seconds and the bins. `stored` / `virtual`: the two lookups,
    `window` (stored, virtual) the same two asked with --since / --until."""
    from .roleframe import claim_source_row_refs

    have, stored_s, have_drawn = _read(stored, seeds, follow)
    made, virtual_s, made_drawn = _read(virtual, seeds, follow)
    only = {"stored": have - made, "virtual": made - have}
    by_ref = {side: defaultdict(list) for side in only}
    for side, atoms in only.items():
        for key, count in atoms.items():
            by_ref[side][key[-1]].extend([key] * count)
    both = set(by_ref["stored"]) & set(by_ref["virtual"])
    differ = Counter(cell for ref in both for a, b in zip(by_ref["stored"][ref], by_ref["virtual"][ref])
                     for cell, x, y in zip(CELLS, a, b) if x != y)
    # a stored copy of an atom the virtual read makes too: the same row's fact kept from another generation
    kept_twice = {key: count for key, count in only["stored"].items() if key in made}
    gone_refs = [ref for ref in by_ref["stored"] if ref not in both
                 and any(key not in kept_twice for key in by_ref["stored"][ref])]
    rows = {ref: claim_source_row_refs(ref) for ref in gone_refs}
    present = _rows_present(fetch, plan.relation, plan.driver.order_by, [r for refs in rows.values() for r in refs])
    real = [ref for ref in gone_refs if any(row in present for row in rows[ref])]
    virtual_refs = [ref for ref in by_ref["virtual"] if ref not in both]
    said = {ref for (ref,) in fetch(f"SELECT DISTINCT source_raw_ref FROM {ledger} WHERE source_who = %(s)s "
                                    f"AND source_raw_ref = ANY(%(refs)s)", {"s": plan.source_id, "refs": virtual_refs})
            } if virtual_refs else set()
    bins = {"spelling": sum(len(by_ref["stored"][ref]) for ref in both) + sum(
                len(by_ref["virtual"][ref]) for ref in virtual_refs if ref in said),
            "stale": sum(len(by_ref["virtual"][ref]) for ref in virtual_refs if ref not in said) + sum(
                kept_twice.values()),
            "stored-only": sum(len(by_ref["stored"][ref]) for ref in gone_refs if ref not in real),
            "real": sum(len(by_ref["stored"][ref]) for ref in real),
            "tie_split": _tie_split(have, (have_drawn, made_drawn))}
    out = {"source": plan.source_id, "seeds": len(seeds), "atoms": {"stored": sum(have.values()),
                                                                     "virtual": sum(made.values())},
           "seconds": {"stored": stored_s, "virtual": virtual_s}, "bins": bins,
           "spelling_cells": dict(differ),
           "e.g.": {"spelling": [[dict(zip(CELLS, by_ref["stored"][r][0])), dict(zip(CELLS, by_ref["virtual"][r][0]))]
                                 for r in sorted(both)[:show]],
                    "real": [dict(zip(CELLS, by_ref["stored"][r][0])) for r in real[:show]],
                    "stale": [dict(zip(CELLS, by_ref["virtual"][r][0])) for r in virtual_refs if r not in said][:show]}}
    if window is not None:
        whole = set(only["stored"]) | set(only["virtual"])
        have_w, _, _ = _read(window[0], seeds, follow)
        made_w, _, _ = _read(window[1], seeds, follow)
        bins["time"] = len((set(have_w - made_w) | set(made_w - have_w)) - whole)
    return out


def main(argv=None) -> int:
    import argparse

    from sqlalchemy import create_engine

    parser = argparse.ArgumentParser(
        prog="python -m ledger walk-shadow",
        description="Walk the same seeds through the stored ledger and the virtual read, source by source, and bin "
                    "every difference (writes nothing; exit 1 when a «real» difference is found)")
    parser.add_argument("--world", default=None, help="this world; the operating one when absent")
    parser.add_argument("--source", action="append", default=None, help="this source (repeatable); every compiled one")
    parser.add_argument("--seeds", default="1,100,1000", help="seed counts, comma separated (default 1,100,1000)")
    parser.add_argument("--since", default=None, help="also walk from this time (ISO 8601) - the «time» bin")
    parser.add_argument("--until", default=None, help="also walk before this time (ISO 8601) - the «time» bin")
    parser.add_argument("--show", type=int, default=3, help="examples per bin")
    args = parser.parse_args(argv)

    from database.database import engine as live
    from ledger_api import ledger_subgraph

    from . import schema, sql_translate, trace, trace_router
    from .setup import load_setup

    names = schema.require_world(args.world)
    snapshot = load_setup(names.declaration_root).snapshot
    engine = create_engine(live.url, connect_args={"options": "-c default_transaction_read_only=on"})
    raw = engine.raw_connection()

    def fetch(sql, params=None):
        return trace._fetch(raw, sql, params)

    window = {name: trace_router._instant_arg(value) for name, value in (("since", args.since), ("until", args.until))
              if value}
    try:
        legs, left_out = sql_translate.compile_world(snapshot, fetch, names.name)
        atoms = dict(fetch(f"SELECT source_who, count(*) FROM {names.ledger} GROUP BY source_who"))
        for item in left_out:
            print(json.dumps({"left_out": item["source"], "stored_atoms": atoms.get(item["source"], 0),
                              "why": item["why"]}, ensure_ascii=False), flush=True)
        one = ledger_subgraph.one_predicates(trace_router._predicate_cardinalities(args.world))
        sources = sorted({leg.source for leg in legs})
        real = 0
        for source in args.source or sources:
            if source not in sources:
                print(json.dumps({"source": source, "skipped": "not compiled"}, ensure_ascii=False))
                continue
            mine = [leg for leg in legs if leg.source == source]
            others = {names.name: [other for other in snapshot.source_plans if other != source]}

            def lookups(**bounds):
                return (ledger_subgraph.SqlEvidenceLookup(raw, worlds=(names,), leave_out=others, one=one, **bounds),
                        ledger_subgraph.VirtualEvidenceLookup(raw, mine, worlds=(names,), one=one, **bounds))

            for count in [int(n) for n in args.seeds.split(",") if n.strip()]:
                seeds = [(kind, json.loads(keys)) for kind, keys in fetch(
                    f"SELECT t, k FROM (SELECT DISTINCT subject_type AS t, subject_keys::text AS k FROM {names.ledger} "
                    f"WHERE source_who = %(s)s) d ORDER BY md5(t || k) LIMIT %(n)s", {"s": source, "n": count})]
                said = shadow(fetch, names.ledger, snapshot.source_plans[source], *lookups(), seeds,
                              sorted({leg.predicate for leg in mine}), args.show,
                              window=lookups(**window) if window else None)
                real += said["bins"]["real"]
                print(json.dumps(said, ensure_ascii=False, default=str), flush=True)
    finally:
        raw.rollback()
        raw.close()
    return 1 if real else 0
