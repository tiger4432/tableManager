# -*- coding: utf-8 -*-
"""총괄 2f2a2f570 — a failure summary line unfolds to EXACTLY the rows it counted.

The summary groups by (table · kind · day); the list pages by transaction. Without a filter
an unfold showed one page (10) of a 33-row line, and the gate 「펼침 Retry 하나」 was measured
on rows that were not drawn. The filter goes through the SAME failure clause and the SAME day
expression the summary groups by - one definition, so the line and its unfold cannot disagree.

And the loops table's on-demand row says running · orphaned and what to do through the one
function `/health` calls (`runtime.health.on_demand_state`) - one line's state, one author.
"""
import datetime
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402
import runtime.health                                            # noqa: E402
import runtime.loops                                             # noqa: E402
from database import models                                      # noqa: E402


def _seed(db):
    def at(day, hour, table, kind, status="FAILED"):
        db.add(models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()), event_type=kind, table_name=table, payload={},
            status=status, retry_count=1, processed_chain=True,
            created_at=datetime.datetime(2026, 9, day, hour, 0)))
    for hour in (0, 1, 2):
        at(23, hour, "dt_inventory", "EDIT")
    at(24, 5, "dt_inventory", "EDIT")
    at(23, 3, "wafer", "CREATE")
    at(23, 4, "dt_inventory", "EDIT", status="SUCCESS")   # not a failure: never unfolds
    db.flush()


def _rows(out):
    return [event for group in out["data"] for event in group["events"]]


def test_every_summary_line_unfolds_to_the_rows_it_counted(db_session):
    _seed(db_session)
    lines = main.get_failed_outbox_events(page=1, limit=1, db=db_session)["summary"]
    assert len(lines) == 3, lines
    for line in lines:
        out = main.get_failed_outbox_events(
            page=1, limit=100, table=line["table_name"], event_type=line["event_type"],
            day=line["day"], db=db_session)
        rows = _rows(out)
        assert len(rows) == line["count"], (line, len(rows))
        assert {(r["table_name"], r["event_type"]) for r in rows} \
            == {(line["table_name"], line["event_type"])}
        assert all(r["status"] == "FAILED" for r in rows)


def test_the_summary_stays_the_whole_section_when_the_list_is_one_line(db_session):
    _seed(db_session)
    out = main.get_failed_outbox_events(page=1, limit=100, table="wafer", event_type="CREATE",
                                        day="2026-09-23", db=db_session)
    assert len(out["summary"]) == 3
    assert out["total"] == 1


def test_a_blank_filter_is_no_filter(db_session):
    """길이 0 인 문자열은 NULL 이다 — `?table=` 은 「표 이름이 빈 것」이 아니라 «안 거름»."""
    _seed(db_session)
    everything = main.get_failed_outbox_events(page=1, limit=100, db=db_session)
    blank = main.get_failed_outbox_events(page=1, limit=100, table="", event_type="", day="",
                                          db=db_session)
    assert len(_rows(blank)) == len(_rows(everything)) == 5


def _row(beats):
    payload = runtime.loops.runtime_loops(_NoDb(), heartbeats=beats)
    return [i for i in payload["loops"] if i.get("when") == runtime.loops.ON_DEMAND]


class _NoDb:
    """The two questions the loops route asks a database (the loops test's own fake, same shape)."""

    def get_bind(self):
        return type("B", (), {"dialect": type("D", (), {"name": "postgresql"})()})()

    def query(self, *a, **kw):
        return self

    def select_from(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def scalar(self):
        return 0

    def execute(self, *a, **kw):
        return type("R", (), {"fetchone": lambda _s: None})()


def test_the_on_demand_row_says_what_health_says():
    process = next(iter(runtime.loops.on_demand_processes()))
    for stale in (False, True):
        beat = {"stale": stale, "age_seconds": 3, "beats": 4}
        (row,) = _row({process: beat})
        assert {row["status"], row["detail"]} == set(runtime.health.on_demand_state(beat).values())
    assert {r["status"] for r in _row({process: {"stale": True}})} == {"orphaned"}


def test_an_idle_on_demand_row_carries_no_state_word():
    """No beat is idle; the loops answer says so by carrying no beat - the screen names it."""
    (row,) = _row({})
    assert "status" not in row and "alive" not in row
