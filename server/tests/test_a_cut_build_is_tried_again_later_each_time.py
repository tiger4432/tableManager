# -*- coding: utf-8 -*-
"""Lead 11-08 (QA ④a): a build cut past its lock wait was thrown away and built again every poll. Each cut now puts
its next try off - doubling, at most a day - in one sentence «cut N time(s) - next try after <time>», and the cuts are
kept where each path keeps its asks: an ask's on its INDEX_WANTED row, the declared work's beside `_LEFT`.
"""
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                               # noqa: E402
from database import models                                          # noqa: E402


def test_each_cut_doubles_the_wait_up_to_a_day():
    now = 1000.0
    assert [models.next_try_after(cuts, now) - now for cuts in (1, 2, 3)] == [
        models.INDEX_CUT_AGAIN_SECONDS, 2 * models.INDEX_CUT_AGAIN_SECONDS, 4 * models.INDEX_CUT_AGAIN_SECONDS]
    assert models.next_try_after(40, now) - now == models.INDEX_CUT_AGAIN_MOST


def test_a_name_still_held_off_is_not_tried_and_stays_left():
    lines = []
    with models.built_tables(cuts={"ix_held": (2, time.time() + 600)}):
        word = models._ensure_one_index(None, "ix_held", "CREATE INDEX CONCURRENTLY ix_held ON t (c)", "automatic",
                                         say=lines.append)
        left, sentence = models.left_in_round(), models.cut_sentence("ix_held")
    assert word == models.INDEX_DEFERRED and left == 1, (word, left)
    assert lines == ["[Indexes] automatic index 'ix_held' not tried - " + sentence], lines
    assert sentence.startswith("cut 2 time(s) - next try after "), sentence


def test_a_cut_on_the_round_is_one_more_and_said_once_the_same_way():
    with models.built_tables(cuts={"ix_a": (1, 0.0)}):
        models._count_cut("ix_a")
        models._count_cut("ix_b")
        cuts = models.cuts_in_round()
        assert models.held_off("ix_a") and models.held_off("ix_b")
    assert cuts["ix_a"][0] == 2 and cuts["ix_b"][0] == 1, cuts
    assert models.cut_sentence("ix_a") == models._comes_back(), "outside the line's round nothing keeps cuts"


def test_an_open_ask_keeps_its_cuts_on_its_row_and_the_next_poll_reads_them(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from database.database import Base
    from runtime import index_wants, maintenance_line

    Base.metadata.create_all(bind=db_session.get_bind())
    asked = ("zz_t", ["s"], models.AUTO_SLOW_SORT)
    name = index_wants.index_name(*asked)
    row = models.DatabaseOutbox(event_uuid=str(uuid.uuid4()), table_name="zz_t",
                                event_type=event_constants.EVENT_INDEX_WANTED, processed_chain=False,
                                payload=json.dumps({"table": "zz_t", "columns": ["s"], "why": asked[2]}))
    db_session.add(row)
    db_session.commit()

    def cut_it(*_args):
        models._count_cut(name)
        models._noted(name, models.INDEX_DEFERRED)

    monkeypatch.setattr(maintenance_line, "_ask_works", lambda factory, each: [(cut_it,)])
    factory = sessionmaker(bind=db_session.get_bind())
    maintenance_line._take_asks(factory, [(row.id, asked)])
    db_session.expire_all()
    kept = db_session.get(models.DatabaseOutbox, row.id)
    assert kept.processed_chain is False and json.loads(kept.payload)["cut"][0] == 1, kept.payload
    seen = {}
    monkeypatch.setattr(maintenance_line, "_take_asks", lambda factory, asks, cuts=None: seen.update(cuts or {}))
    monkeypatch.setattr(maintenance_line, "_declared_work", lambda factory: None)
    maintenance_line.poll_once(factory, 0)
    assert seen.get(name, (0,))[0] == 1, ("the next poll reads the row's cuts", seen)
