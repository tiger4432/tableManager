# -*- coding: utf-8 -*-
"""e38466810 (lead 10-21 ㄱ): the agent walk ping-pongs - `agent_walk` on a walk_request row writes the next
walk_log row (the LLM picks), and on log rows writes the request's position back, which wakes it again. Driven here
the way the chain drives the two sample rules, with a fake LLM and a fake one-hop walk: the hops stop at
`hop_cap` (max_chain_depth // 2, or the request's hop_budget), the last hop and the end row come in one call so no
row is past the depth limit, log hop rows = LLM calls - 1, and a refused answer is asked once more, then ends the
walk saying why."""
import json
import os
import re
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

import product_tables  # noqa: E402
from chain import ingestion_worker  # noqa: E402
from database import crud, models, schemas  # noqa: E402
from database.database import Base  # noqa: E402
from ledger import explorer, trace_router, walk_cards  # noqa: E402
from mappers import agent_walk  # noqa: E402
from utils import llm  # noqa: E402

TABLES = (product_tables.MEANING_TABLE, product_tables.WALK_REQUEST_TABLE, product_tables.WALK_LOG_TABLE,
          product_tables.WALK_RECIPE_TABLE)
HOP_RULE = {"name": "agent_walk_hop", "trigger_table": product_tables.WALK_REQUEST_TABLE}
FOLLOW_RULE = {"name": "agent_walk_follow", "trigger_table": product_tables.WALK_LOG_TABLE}
DECLARATION = {"entities": {"step@1": {"keys": ["n"]}},
               "vocabulary": {"next@1": {"subjects": ["step@1"], "object": {"kind": "entity_ref",
                                                                            "types": ["step@1"]}}}}
RECIPE = [("unwalked", 1, "key_candidates"), ("unwalked", 2, "question"), ("on_node", 1, "edges"),
          ("on_node", 2, "path"), ("on_node", 3, "budget"), ("stuck", 1, "dead_end"), ("end", 1, "full_path")]


def node(n):
    return explorer.entity_id("step", {"n": str(n)})


def one_hop(db, position, limit):
    """A line of steps: n - next -> n+1."""
    n = int(explorer.decode_entity_id(position)[1]["n"])
    ids = [node(n), node(n + 1)]
    return {"nodes": [{"id": i, "type": "step", "label": str(k)} for i, k in zip(ids, (n, n + 1))],
            "edges": [{"source": node(n), "target": node(n + 1), "predicate": "next"}]}


@pytest.fixture
def box(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "walk.db"))
    cfg = {t: product_tables.effective_declaration(product_tables.PRODUCT_TABLES[t]) for t in TABLES}
    models.init_dynamic_models(cfg)
    for table, spec in cfg.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, table, spec)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    monkeypatch.setattr(trace_router, "_declaration", lambda world=None: DECLARATION)
    monkeypatch.setattr(ingestion_worker, "_RULES_DOCUMENT", {"max_chain_depth": 8})
    monkeypatch.setattr(agent_walk, "_one_hop", one_hop)
    monkeypatch.setattr(walk_cards, "key_values", lambda sight, t, limit, starts_with=None: {
        "nodes": [{"keys": {"n": "0"}, "count": 1}] if starts_with == "start" else [], "scanned": 1})
    calls = []

    def ask_json(prompt, system=None):
        calls.append(prompt)
        return box_state["answer"](prompt)

    box_state = {"answer": go_forward, "calls": calls}
    monkeypatch.setattr(llm, "ask_json", ask_json)
    with Session(bind=engine) as db:
        write(db, product_tables.WALK_RECIPE_TABLE,
              [{"recipe": "r", "state": s, "card_order": o, "card": c, "card_limit": 5} for s, o, c in RECIPE])
        box_state["db"] = db
        yield box_state
    engine.dispose()


def go_forward(prompt):
    """Go to the highest-numbered step listed, answer at the end."""
    if "rule_draft" in prompt and '{"go"' not in prompt:
        return {"answer": "the line ends nowhere", "evidence": ["N1"], "rule_draft": ""}
    listed = re.findall(r"^(N\d+): step (?:n=)?(\d+)", prompt, re.M)
    assert listed, prompt
    return {"go": max(listed, key=lambda pair: int(pair[1]))[0], "reason": "further along"}


def write(db, table, rows, source="user"):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=row, source_name=source, updated_by="t") for row in rows]))
    db.commit()


def rows(db, table, **where):
    model = models.DYNAMIC_TABLES[table]
    query = db.query(model)
    for column, value in where.items():
        query = query.filter(getattr(model, column) == value)
    return query.all()


def walk(box, request):
    """The two rules in turn, as the chain runs them, until the request ends. -> the depth each write came at."""
    db = box["db"]
    write(db, product_tables.WALK_REQUEST_TABLE, [dict({"request_id": "q1", "recipe": "r"}, **request)])
    depths, depth = [], 0                      # an operator's row: no depth; each rule's write is one deeper
    for _ in range(12):
        req = rows(db, product_tables.WALK_REQUEST_TABLE, request_id="q1")[0]
        out = agent_walk.agent_walk(db, [{"row_id": req.row_id}], HOP_RULE)
        if not out["updates"]:
            return depths
        depth += 1
        depths.append(depth)
        steps = [item.updates["step"] for item in out["updates"]]
        write(db, product_tables.WALK_LOG_TABLE, [item.updates for item in out["updates"]], crud.CHAIN_SOURCE)
        written = [r for r in rows(db, product_tables.WALK_LOG_TABLE, request_id="q1") if r.step in steps]
        back = agent_walk.agent_walk(db, [{"row_id": r.row_id} for r in written], FOLLOW_RULE)
        depth += 1
        depths.append(depth)
        write(db, product_tables.WALK_REQUEST_TABLE, [item.updates for item in back["updates"]], crud.CHAIN_SOURCE)
    raise AssertionError("the walk did not end")


def log(box):
    return sorted(rows(box["db"], product_tables.WALK_LOG_TABLE, request_id="q1"), key=lambda r: r.step)


def test_the_hops_stop_at_half_the_chain_depth_and_the_end_comes_with_the_last(box):
    depths = walk(box, {"question": "Where does start lead?"})
    written = log(box)
    assert [(r.step, r.kind) for r in written] == [(1, "hop"), (2, "hop"), (3, "hop"), (4, "hop"), (5, "end")]
    assert [explorer.decode_entity_id(r.position)[1]["n"] for r in written[:4]] == ["0", "1", "2", "3"]
    assert max(depths) == 8                                       # nothing past max_chain_depth
    end = written[-1]
    assert end.reason == "chain depth 8 → 4 hops" and end.answer == "the line ends nowhere"
    assert json.loads(end.evidence) == [written[0].position] and end.recipe_print == written[0].recipe_print
    assert sum(r.kind == "hop" for r in written) == len(box["calls"]) - 1
    request = rows(box["db"], product_tables.WALK_REQUEST_TABLE, request_id="q1")[0]
    assert (request.state, request.step, request.position) == ("end", 5, written[3].position)
    assert "## key_candidates" in box["calls"][0] and "## edges" in box["calls"][1]


def test_a_hop_budget_below_the_depth_stops_the_walk_sooner(box):
    walk(box, {"question": "Where does start lead?", "hop_budget": 2})
    written = log(box)
    assert [r.kind for r in written] == ["hop", "hop", "end"] and written[-1].reason == "hop budget 2"


def test_the_model_answering_ends_the_walk_with_its_evidence(box):
    def answer_at_two(prompt):
        if "step 2" in prompt:
            return {"answer": "step 2 is it", "evidence": ["N1"], "rule_draft": "next twice"}
        return go_forward(prompt)

    box["answer"] = answer_at_two
    walk(box, {"question": "Where does start lead?"})
    written = log(box)
    assert [r.kind for r in written] == ["hop", "hop", "end"]
    assert (written[-1].answer, written[-1].rule_draft) == ("step 2 is it", "next twice")
    assert sum(r.kind == "hop" for r in written) == len(box["calls"]) - 1


def test_a_refused_answer_is_asked_once_more(box):
    said = {"n": 0}

    def wrong_once(prompt):
        said["n"] += 1
        return {"go": "N99"} if said["n"] == 1 else go_forward(prompt)

    box["answer"] = wrong_once
    walk(box, {"question": "Where does start lead?", "hop_budget": 1})
    assert "Your last answer was refused: 'N99' is not one of the listed node identifiers" in box["calls"][1]
    assert [r.kind for r in log(box)] == ["hop", "end"]


def test_two_refused_answers_end_the_walk_saying_why(box):
    box["answer"] = lambda prompt: {"go": "N99"}
    walk(box, {"question": "Where does start lead?"})
    (end,) = log(box)
    assert end.kind == "end" and end.reason == ("the answer was refused twice: 'N99' is not one of the listed node "
                                                "identifiers")
    assert len(box["calls"]) == 2


def test_a_recipe_with_no_rows_ends_the_walk_naming_where_to_write_them(box):
    walk(box, {"question": "Where does start lead?", "recipe": "nobody"})
    (end,) = log(box)
    assert end.reason == "recipe 'nobody' has no rows - write its rows in walk_recipe" and box["calls"] == []
