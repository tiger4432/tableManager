# -*- coding: utf-8 -*-
"""How connected the causal links in the ledger are - read only (총괄 d7a27a758, 소유자 「모델링이 서로 연결이
되어야 온톨로지 쓰는데 다 단발성 모델링만 나옴 · 그래프가 아니라 그냥 쌍의 집합」). Run it before and after a change
to the modelling extraction and compare.

    python server/scripts/causal_graph_connectivity.py --predicate <name> [--predicate <name> ...] [--world <name> ...]

No --world reads the operating world. The links are the distinct (cause, effect, predicate) atoms of those
predicates whose object is a node; read both ways for what follows.

    nodes          the nodes any of those links touches
    links          the distinct links
    pieces         groups of nodes joined by links (connected components)
    largest piece  its nodes - and the share of all nodes
    lone pairs     links neither end of which touches another node - and the share of the links

A graph of separate pairs has pieces = links and every link a lone pair; a connected one has few pieces,
a largest piece near 100 % and few lone pairs. The connection is read-only (`db_safety`), checked by PostgreSQL.
"""
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def connectivity(links):
    """`links` [(cause, effect)] - nodes hashable, one per distinct link -> {nodes, links, pieces, largest,
    lone}. Directions are not read: a piece is nodes joined either way."""
    links = list(links)
    near, parent = {}, {}

    def root(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for cause, effect in links:
        for node in (cause, effect):
            parent.setdefault(node, node)
            near.setdefault(node, set())
        if cause != effect:
            near[cause].add(effect)
            near[effect].add(cause)
        parent[root(cause)] = root(effect)
    sizes = {}
    for node in parent:
        sizes[root(node)] = sizes.get(root(node), 0) + 1
    lone = sum(1 for cause, effect in links if cause != effect and near[cause] == {effect} and near[effect] == {cause})
    return {"nodes": len(parent), "links": len(links), "pieces": len(sizes),
            "largest": max(sizes.values(), default=0), "lone": lone}


def read_links(connection, relation, predicates):
    """The distinct (cause, effect) node pairs of `predicates` in ledger `relation`, a link per predicate."""
    from sqlalchemy import text

    rows = connection.execute(text(
        "SELECT DISTINCT subject_type, subject_keys::text, object_payload->>'type', (object_payload->'keys')::text,"
        " predicate FROM %s WHERE predicate = ANY(:predicates) AND object_kind = 'entity_ref'" % relation),
        {"predicates": list(predicates)})
    return [((cause_type, cause_keys), (effect_type, effect_keys))
            for cause_type, cause_keys, effect_type, effect_keys, _predicate in rows]


def said(numbers):
    """The answer as the lines the command prints."""
    def share(part, whole):
        return "%.1f %%" % (100.0 * part / whole) if whole else "-"
    return ["nodes          %d" % numbers["nodes"],
            "links          %d" % numbers["links"],
            "pieces         %d" % numbers["pieces"],
            "largest piece  %d nodes - %s of the nodes" % (numbers["largest"], share(numbers["largest"], numbers["nodes"])),
            "lone pairs     %d - %s of the links" % (numbers["lone"], share(numbers["lone"], numbers["links"]))]


def main(argv=None):
    import db_safety
    from ledger import schema

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--predicate", action="append", required=True, help="a predicate, repeated for several")
    parser.add_argument("--world", action="append", default=[], help="a ledger world, repeated; none: the operating world")
    args = parser.parse_args(argv)
    worlds = [schema.require_world(name) for name in args.world] or [schema.require_world(None)]
    engine = db_safety.open_readonly_engine(application_name="causal_graph_connectivity")
    links = []
    with engine.connect() as connection:
        db_safety.assert_readonly(connection)
        for names in worlds:
            links += [((names.world, cause), (names.world, effect))
                      for cause, effect in read_links(connection, names.ledger, args.predicate)]
    print("predicates     %s" % ", ".join(args.predicate))
    print("worlds         %s" % ", ".join(names.world or "(operating)" for names in worlds))
    for line in said(connectivity(links)):
        print(line)


if __name__ == "__main__":
    main()
