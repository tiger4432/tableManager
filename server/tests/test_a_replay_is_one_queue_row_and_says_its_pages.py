# -*- coding: utf-8 -*-
"""Owner 11-09 «체인 소급은 왜 도는 거 반응이 없어» · «오른쪽 큐도 똑같은 거 잔뜩» · lead ㄷ: a replay's pages as the
chain runs them are ONE answer (`replay.pages_of`) - the admin queue's line, the runs list beside «done», and the grid's
Queue tab, where one replay is one row whatever the page size, however the id cursor cuts the list.

  pages_of   done · staged · rows_done from the run's cursor, waiting · failed from its events; no cursor -> absent
  three      the admin queue line, runs() and the Queue tab row say the same dict
  one row    a replay's waiting pages are one row of the Queue tab; paging one row at a time lists it once
"""
import json
import uuid

import pytest

from admin import retroactive
from chain import replay
from database import models
from database.models import DatabaseOutbox
from test_a_cut_replay_resumes_after_its_last_committed_page import (  # noqa: F401 - the fixture
    RULE, SRC, _pages, _process, _seed, _stage, db)


def _person_edit(db):
    """A person's edit of the trigger table, waiting - its own row on the Queue tab."""
    event = DatabaseOutbox(event_uuid=str(uuid.uuid4()), event_type="EDIT", table_name=SRC, status="PENDING",
                           processed_chain=False, transaction_id="tx-person-%s" % uuid.uuid4().hex[:6],
                           payload={"transaction_id": "tx-person"})
    db.add(event)
    db.commit()
    return event.id


@pytest.mark.anyio
async def test_one_answer_for_a_replays_pages_on_the_queue_the_runs_list_and_the_queue_tab(db, client):
    _seed(db, ["K%02d" % i for i in range(9)])
    _stage(db, "p1")
    db.add(models.RetroactiveRun(run_id="w1", op="withdraw", params="{}", state="done"))
    db.commit()
    pages = _pages(db, "p1")
    await _process(db, pages[1])
    pages[3][0].status = "FAILED"
    pages[3][0].processed_chain = True
    db.commit()

    said = {"done": 1, "staged": 3, "rows_done": 3, "waiting": 1, "rows_waiting": 3, "failed": 1}
    assert replay.pages_of(db, ["p1", "w1", "gone", None]) == {"p1": said}
    assert replay.pages_of(db, []) == {}

    [line] = [l for l in client.get("/admin/chain/queue").json()["waiting_transactions"] if l["run_id"] == "p1"]
    assert line["pages"] == said
    listed = {run["run_id"]: run for run in retroactive.runs(db)}
    assert listed["p1"]["state"] == "done" and listed["p1"]["pages"] == said
    assert listed["w1"]["pages"] is None
    [row] = [r for r in client.get("/outbox/queue/rows").json()["rows"] if r.get("run_id") == "p1"]
    assert row["pages"] == said and row["rule"] == RULE


def test_a_replay_is_one_row_of_the_queue_tab_however_the_cursor_cuts_it(db, client):
    _seed(db, ["K%02d" % i for i in range(9)])
    before = _person_edit(db)
    _stage(db, "p2")
    after = _person_edit(db)
    staged = [e.id for page in _pages(db, "p2").values() for e in page]
    assert len(staged) == 3 and before < min(staged) and max(staged) < after        # the run sits between them

    seen, cursor = [], None
    for _ in range(10):
        body = client.get("/outbox/queue/rows", params={"limit": 1, **({"cursor": cursor} if cursor else {})}).json()
        seen += body["rows"]
        cursor = body["listed"]["next_cursor"]
        if cursor is None:
            break
    assert [(r["outbox_id"], r.get("run_id")) for r in seen] == [(before, None), (min(staged), "p2"), (after, None)]
    assert seen[1]["pages"] == {"done": 0, "staged": 3, "rows_done": 0, "waiting": 3, "rows_waiting": 9, "failed": 0}
    assert "pages" not in seen[0] and "run_id" not in seen[2]


def test_a_run_without_a_cursor_has_no_pages(db):
    db.add(models.RetroactiveRun(run_id="n1", op="chain_replay", params=json.dumps({"rule": RULE}), state="done"))
    db.commit()
    assert replay.pages_of(db, ["n1"]) == {}
    assert {run["run_id"]: run for run in retroactive.runs(db)}["n1"]["pages"] is None
