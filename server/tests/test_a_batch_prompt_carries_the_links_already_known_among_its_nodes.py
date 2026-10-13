# -*- coding: utf-8 -*-
"""총괄 d7a27a758 · 423599fe9 (소유자 「모델링이 서로 연결이 되어야 온톨로지 쓰는데 다 단발성 모델링만 나옴」 ·
「좀 더 스마트하게 샘플링해서 넣을 수 있을까? 프롬프트 너무 커지니까」): with `known` from the mapper, a request's
prompt carries the links already known among its nodes - the seeds are the nodes the texts name
(`phrase_bag.held_nodes`), the walk is the screen's own walk called directly (replaced here by the same
`ledger_subgraph.subgraph` over an in-memory ledger, except in the PostgreSQL proof), and the dictionary
lists only the seeds and the chosen links' nodes. A fake model (`llm.ask_json` replaced).

  the prompt                         the dictionary of the seeds and the chosen links' nodes, the known lines
                                     grouped by cause, the three asks - written out below
  the order                          bridges between seeds, then step 1 by confirmed · records · id, then step 2
  known_per_seed                     at most k non-bridge links per seed, the seeds taking turns
  known_chars                        seeds first, then links in order; the cut said in `known`
  the same batch twice               the same prompt, byte for byte
  no seed                            no known-links heading, an empty dictionary, no walk
  no `known`                         no walk, nothing added
  a chain A -> B -> C                two rows sharing B (the answer shape is the pairs, as before)
  a seed whose type has 2 keys       not walked, one line
  PostgreSQL                         the real walk (`trace_router._evidence_graph`) on a scratch ledger
"""
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from ledger import explorer                                                # noqa: E402
from ledger_api import ledger_subgraph                                     # noqa: E402
from utils import llm, text_links                                          # noqa: E402
from test_a_text_is_read_by_a_language_model import (                      # noqa: E402,F401 - the fixtures are used
    CELLS, _declare, fixture_root)
from test_many_texts_are_asked_in_one_request_under_a_per_minute_limit import Model   # noqa: E402
from tests.test_ledger_trace_pg import ledger_engine   # noqa: E402,F401 - the shipped ledger schema, for the pg proof

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
FOLLOW = {"follow": ["leads_to"], "hops": 2, "certainty": "certainty"}
WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india"]
NAMES = ([{"node_type": "thing", "node_key": "N%d" % n, "phrase": word} for n, word in enumerate(WORDS, 1)]
         + [{"node_type": "other", "node_key": "O1", "phrase": "kilo"}])
TEXT = "Alpha rose and charlie fell."
#: (cause, effect, records, confirmed). The seeds of TEXT are N1 and N3.
LINKS = [("N1", "N2", 1, False), ("N2", "N3", 1, False),          # the way between the seeds - bridges
         ("N1", "N4", 1, True), ("N1", "N5", 3, False), ("N1", "N6", 1, False),   # one step from N1
         ("N3", "N7", 2, False),                                   # one step from N3
         ("N4", "N8", 1, False)]                                   # two steps from N1
ELSEWHERE = [("N1", "N9", "has_part")]                             # not followed


def _atoms(links=LINKS, elsewhere=ELSEWHERE):
    atoms, number = [], 0
    for cause, effect, records, confirmed in links:
        for _n in range(records):
            number += 1
            atoms.append(_atom(number, cause, "leads_to", effect, {"certainty": "confirmed" if confirmed else "suspected"}))
    for cause, effect, predicate in elsewhere:
        number += 1
        atoms.append(_atom(number, cause, predicate, effect, {}))
    return atoms


def _atom(number, cause, predicate, effect, qualifiers):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="thing", subject_keys={"key": cause}, predicate=predicate,
        object_kind="entity_ref", object_payload={"type": "thing", "keys": {"key": effect}, "qualifiers": qualifiers},
        occurred_at=NOW, source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=10_000 + number)), source_event_state="source_molecule")


@pytest.fixture(name="ledger")
def fixture_ledger(root, monkeypatch):
    """The walk over these atoms: `ledger.walks` are the (seeds, follow, hops) it was asked; `ledger.reverse`
    hands its edges back in the other order - a database may read them in any."""
    state = {"atoms": _atoms(), "walks": [], "reverse": False}

    def walked(seeds, follow, hops):
        state["walks"].append((list(seeds), list(follow), hops))
        ids = [explorer.entity_id(node_type, {"key": key}) for node_type, key in seeds]
        walk = ledger_subgraph.subgraph({"positive": ids, "negative": []},
                                        ledger_subgraph.InMemoryEvidenceLookup(state["atoms"]),
                                        hops=hops, follow=list(follow), direction="both")
        if state["reverse"]:
            walk["edges"] = list(reversed(walk["edges"]))
        return walk
    monkeypatch.setattr(text_links, "_walked", walked)
    return state


@pytest.fixture(name="model")
def fixture_model(root, monkeypatch):
    def install(cells=None, **kwargs):
        _declare(root, **CELLS, **(cells or {}))
        fake = Model(**kwargs)
        monkeypatch.setattr(llm, "ask_json", fake)
        return fake
    return install


def _between(prompt, start, end):
    return prompt.split(start, 1)[1].split(end, 1)[0]


DICTIONARY_HEADING = "Dictionary, one node per line - identifier (node type): the phrases that name it\n"
#: What the request of TEXT carries between the dictionary heading and the texts - written out, not built.
BLOCK = """N1 (thing): alpha
N2 (thing): bravo
N3 (thing): charlie
N4 (thing): delta
N5 (thing): echo
N6 (thing): foxtrot
N7 (thing): golf
N8 (thing): hotel
Known links, one per line: <cause id> -> <effect id>, <effect id> (<predicate>)
N1 -> N2, N4, N5, N6 (leads_to)
N2 -> N3 (leads_to)
N3 -> N7 (leads_to)
N4 -> N8 (leads_to)
Where a node of the dictionary or of the known links is what a text names, link to that node - a new node only when none fits.
When a text names a step between the two ends of a known link, link that step: one link into it and one out of it.
When A causes B and B causes C, answer A -> B and B -> C as two links, and give one thing the same identifier or the same words in every text of this request.

Texts, each after its [id] line:
"""


def test_the_prompt_carries_the_known_links_and_only_their_nodes(model, ledger):
    fake = model()
    found = text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known=FOLLOW)
    assert fake.prompts[0].split(DICTIONARY_HEADING, 1)[1].split("[t1]", 1)[0] == BLOCK
    assert ledger["walks"] == [([("thing", "N1"), ("thing", "N3")], ["leads_to"], 2)]
    assert found.known == [{"texts": ["t1"], "seeds": 2, "links": 7, "kept": 7, "nodes": 10, "listed": 8, "certainty": "certainty"}]


def test_the_dictionary_lists_no_node_but_the_seeds_and_the_chosen_links_ends(model, ledger):
    fake = model(cells={"known_per_seed": 1})
    text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known=FOLLOW)
    listed = re.findall(r"^(\S+) \((?:thing|other)\):", _between(fake.prompts[0], DICTIONARY_HEADING, "Known links"), re.M)
    known = _between(fake.prompts[0], "(<predicate>)\n", "\nWhere a node")
    ends = set(re.findall(r"N\d", known))
    assert listed == ["N1", "N2", "N3", "N4", "N7"] and set(listed) == ends | {"N1", "N3"}
    assert "kilo" not in fake.prompts[0] and "india" not in fake.prompts[0]


def test_bridges_come_before_the_first_steps(model, ledger):
    """Two links fit: the two on the way between the seeds, not the confirmed step from N1."""
    size = len("\n".join(["N1 (thing): alpha", "N2 (thing): bravo", "N3 (thing): charlie",
                          text_links.KNOWN_HEADING, "N1 -> N2 (leads_to)", "N2 -> N3 (leads_to)"]))
    fake = model(cells={"known_chars": size})
    found = text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known=FOLLOW)
    assert _between(fake.prompts[0], "(<predicate>)\n", "\nWhere a node") == "N1 -> N2 (leads_to)\nN2 -> N3 (leads_to)"
    assert found.known[0] == {"texts": ["t1"], "seeds": 2, "links": 7, "kept": 2, "nodes": 10, "listed": 3, "certainty": "certainty"}


def test_the_whole_order(ledger):
    """`_chosen` over the walk: bridges · step 1 by confirmed, records, id, seeds taking turns · step 2."""
    by_id, _lines = text_links._node_lines(NAMES)
    node_of = {node: ident for ident, node in by_id.items()}
    seeds = [("thing", "N1"), ("thing", "N3")]
    links = text_links._known_links(text_links._walked(seeds, ["leads_to"], 2), node_of, ["leads_to"], "certainty")
    order = [(node_of[link["cause"]], node_of[link["effect"]]) for link in text_links._chosen(seeds, links, 5, node_of)]
    assert order == [("N1", "N2"), ("N2", "N3"), ("N1", "N4"), ("N3", "N7"), ("N1", "N5"), ("N1", "N6"), ("N4", "N8")]
    supports = {(node_of[link["cause"]], node_of[link["effect"]]): (link["support"], link["confirmed"]) for link in links}
    assert supports[("N1", "N5")] == (3, False) and supports[("N1", "N4")] == (1, True)


def test_at_most_k_links_a_seed_besides_the_bridges(model, ledger):
    fake = model(cells={"known_per_seed": 1})
    found = text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known=FOLLOW)
    assert _between(fake.prompts[0], "(<predicate>)\n", "\nWhere a node") == (
        "N1 -> N2, N4 (leads_to)\nN2 -> N3 (leads_to)\nN3 -> N7 (leads_to)")
    assert found.known[0]["kept"] == 4


def test_the_same_batch_twice_is_the_same_prompt(model, ledger):
    fake = model()
    batch = [{"id": "t1", "text": TEXT}, {"id": "t2", "text": "Golf and india moved."}]
    text_links.ask_links(batch, NAMES, known=FOLLOW)
    ledger["reverse"] = True                                    # the ledger reads in another order
    text_links.ask_links(batch, NAMES, known=FOLLOW)
    assert len(fake.prompts) == 2 and fake.prompts[0] == fake.prompts[1]


def test_no_seed_no_known_links_and_no_walk(model, ledger):
    fake = model()
    found = text_links.ask_links([{"id": "t1", "text": "Nothing named here."}], NAMES, known=FOLLOW)
    assert "Known links" not in fake.prompts[0] and ledger["walks"] == []
    assert fake.prompts[0].split(DICTIONARY_HEADING, 1)[1].startswith("\nWhere a node of the dictionary")
    assert found.known[0] == {"texts": ["t1"], "seeds": 0, "links": 0, "kept": 0, "nodes": 10, "listed": 0, "certainty": "certainty"}


def test_without_known_nothing_is_walked_or_added(model, ledger):
    fake = model()
    found = text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES)
    assert ledger["walks"] == [] and found.known == []
    assert "Known links" not in fake.prompts[0] and "Where a node" not in fake.prompts[0]
    assert "india" in fake.prompts[0], "the whole dictionary"


def test_each_request_carries_its_own_texts_known_links(model, ledger):
    fake = model(cells={"batch_chars": 30})
    text_links.ask_links([{"id": "t1", "text": TEXT}, {"id": "t2", "text": "Golf and india moved."}], NAMES,
                         known=FOLLOW)
    assert [walk[0] for walk in ledger["walks"]] == [[("thing", "N1"), ("thing", "N3")],
                                                     [("thing", "N7"), ("thing", "N9")]]
    assert "N3 -> N7 (leads_to)" in fake.prompts[1] and "N1 -> N2" not in fake.prompts[1]


def test_a_chain_comes_back_as_two_pairs_sharing_the_middle(model, ledger):
    text = "Alpha raised bravo, and bravo raised charlie."
    model(links={text: [
        {"cause": "alpha", "cause_key": "N1", "effect": "bravo", "effect_key": "N2", "evidence": text},
        {"cause": "bravo", "cause_key": "N2", "effect": "charlie", "effect_key": "N3", "evidence": text}]})
    rows = text_links.ask_links([{"id": "t1", "text": text}], NAMES, known=FOLLOW)
    assert [(row["cause_key"], row["phenomenon_key"]) for row in rows] == [("N1", "N2"), ("N2", "N3")]


@pytest.mark.parametrize("known", [{"follow": ["leads_to"]}, {"follow": [], "hops": 2}, {"follow": "leads_to", "hops": 2},
                                   {"follow": ["leads_to"], "hops": 0}, {"follow": ["leads_to"], "hops": True}, ["leads_to"]])
def test_a_known_of_another_shape_is_refused_before_any_request(model, ledger, known):
    fake = model()
    with pytest.raises(ValueError, match="known is"):
        text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known=known)
    assert fake.prompts == []


def test_a_seed_whose_type_declares_two_keys_is_not_walked(monkeypatch, caplog):
    monkeypatch.setattr(ledger_subgraph, "_declared_key_order", lambda entity_type: ["a", "b"])
    caplog.set_level(logging.WARNING)
    assert text_links._walked([("thing", "N1")], ["leads_to"], 2) == {"nodes": [], "edges": []}
    assert [r.getMessage() for r in caplog.records if r.name == "utils.text_links"] == [
        "[LLM] known links: 1 seed(s) not walked - type(s) thing do not declare exactly one key"]


# ---------------------------------------------------------------------------- 총괄 검수 10-13: 6


def test_a_paused_chain_stops_the_batch_before_its_next_request(model, ledger, monkeypatch):
    """Each request is a stage boundary of the chain group it runs in: paused, nothing more is asked or walked
    - the group is rewound as at any boundary. Outside a group the pause is not this call's."""
    from chain import control
    from database.context import chain_group

    fake = model()
    monkeypatch.setattr(control, "paused", lambda: {"by": "t", "at": "now", "reason": "test"})
    with chain_group(), pytest.raises(control.ChainPaused):
        text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known=FOLLOW)
    assert fake.prompts == [] and ledger["walks"] == []
    text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known=FOLLOW)
    assert len(fake.prompts) == 1


def _bridges_by_pairs(seeds, links):
    """The definition, pair by pair - a link on a shortest way between two seeds, read both ways."""
    from collections import deque

    near = {}
    for link in links:
        near.setdefault(link["cause"], set()).add(link["effect"])
        near.setdefault(link["effect"], set()).add(link["cause"])
    far = {}
    for seed in seeds:
        far[seed], queue = {seed: 0}, deque([seed])
        while queue:
            at = queue.popleft()
            for step in near.get(at, ()):
                if step not in far[seed]:
                    far[seed][step] = far[seed][at] + 1
                    queue.append(step)
    return {(link["cause"], link["effect"]) for link in links
            if any(s != t and t in far[s] and any(
                a in far[s] and b in far[t] and far[s][a] + 1 + far[t][b] == far[s][t]
                for a, b in ((link["cause"], link["effect"]), (link["effect"], link["cause"])))
                for s in seeds for t in seeds)}


@pytest.mark.parametrize("seed", range(6))
def test_the_bridges_are_the_ones_the_pairwise_definition_gives(seed):
    """One pass per seed (links x seeds) picks exactly the links the pairwise reading (links x seeds²) does."""
    import random

    rng = random.Random(seed)
    nodes = [("t", "n%02d" % n) for n in range(40)]
    node_of = {node: node[1] for node in nodes}
    pairs = set()
    while len(pairs) < 70:
        a, b = rng.sample(nodes, 2)
        pairs.add((a, b))
    links = [{"cause": a, "effect": b, "predicate": "p", "confirmed": False, "support": 1} for a, b in sorted(pairs)]
    seeds = sorted(rng.sample(nodes, 6), key=node_of.__getitem__)
    want = _bridges_by_pairs(seeds, links)
    chosen = text_links._chosen(seeds, links, 0, node_of)        # k 0: the bridges and nothing else
    assert {(link["cause"], link["effect"]) for link in chosen} == want and want


@pytest.mark.pg
def test_the_walk_runs_under_the_chains_statement_limit_in_a_group(pg_engine, monkeypatch):
    """The walk's connection is a session's, so in a chain group it carries `chain_statement_timeout_seconds`
    (default 120 s) like the group's own reads; outside one, none."""
    from ledger import trace_router
    from database import database
    from database.context import chain_group
    from sqlalchemy import text

    seen = []

    def walk(connection, **_kwargs):
        seen.append(connection.execute(text("SHOW statement_timeout")).scalar())
        return {"nodes": [], "edges": []}
    monkeypatch.setattr(database, "engine", pg_engine)
    monkeypatch.setattr(trace_router, "_evidence_graph", walk)
    monkeypatch.setattr(ledger_subgraph, "_declared_key_order", lambda entity_type: ["key"])
    with chain_group():
        text_links._walked([("thing", "N1")], ["leads_to"], 2)
    text_links._walked([("thing", "N1")], ["leads_to"], 2)
    assert seen[0] == "2min" and seen[1] != "2min", seen


# ---------------------------------------------------------------------------- PostgreSQL: the real walk


def _ledger_rows(atoms):
    """`EvidenceAtom`s as `test_ledger_trace_pg.insert` takes them."""
    return [{"id": atom.id, "st": atom.subject_type, "sk": json.dumps(atom.subject_keys), "p": atom.predicate,
             "ok": atom.object_kind, "op": json.dumps(atom.object_payload), "oa": atom.occurred_at,
             "who": atom.source_who, "ver": atom.source_translator_ver, "raw": atom.source_raw_ref, "sup": None}
            for atom in atoms]


@pytest.mark.pg
def test_the_real_walk_reaches_the_known_links(model, ledger_engine, monkeypatch):
    """`_walked` as shipped - `trace_router._evidence_graph` on a connection of its own - over a scratch ledger:
    the same prompt as the in-memory walk gives. public is not read: the engine is the scratch one."""
    from sqlalchemy import text

    from database import database
    from tests.test_ledger_trace_pg import insert

    with ledger_engine.begin() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() != "public"
        conn.execute(text("TRUNCATE ledger_events"))
        insert(conn, _ledger_rows(_atoms()))
    monkeypatch.setattr(database, "engine", ledger_engine)
    monkeypatch.setattr(ledger_subgraph, "_declared_key_order", lambda entity_type: ["key"])
    fake = model()
    try:
        found = text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known=FOLLOW)
    finally:
        with ledger_engine.begin() as conn:
            conn.execute(text("TRUNCATE ledger_events"))
    assert fake.prompts[0].split(DICTIONARY_HEADING, 1)[1].split("[t1]", 1)[0] == BLOCK
    assert found.known == [{"texts": ["t1"], "seeds": 2, "links": 7, "kept": 7, "nodes": 10, "listed": 8, "certainty": "certainty"}]


def test_without_the_certainty_cell_no_link_is_read_as_confirmed(model, ledger):
    """총괄 10-13 ⑪: the qualifier that says confirmed is the mapper's to name - unnamed, step 1 goes by records
    alone (N5 - three records - before the confirmed N4), and the result says none was named."""
    fake = model()
    found = text_links.ask_links([{"id": "t1", "text": TEXT}], NAMES, known={"follow": ["leads_to"], "hops": 2})
    assert _between(fake.prompts[0], "(<predicate>)\n", "\nWhere a node").splitlines()[0] == "N1 -> N2, N5, N4, N6 (leads_to)"
    assert found.known[0]["certainty"] is None
