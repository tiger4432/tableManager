"""Lead 10-31 ① (owner ㄱ): a group source's untranslated rows showed «0, exact» - the census refused rows less the
index as «rows vs groups» (3adf9e797), and the retroactive preview turned that refusal into affected 0. The index
holds every ROW of a molecule (`runtime_v2._row_ref_index`), so the subtraction is rows less rows: measured on the box,
dt_job 535,559 - 467,638 = 67,921 = `rows_missing_from_the_index`.

  the board   a group source (group_by dt_job), three jobs of three rows each, on PostgreSQL
  the cells   none translated · one job translated · all translated
  the seats   rows_missing_from_the_index · rows_not_yet_translated · the census stamp · the ledger_backfill preview
              - one number, and the index counts the translated jobs' rows
"""
import copy

import pytest

from ledger import backfill, followup
from support import hold_world as hw

pytestmark = pytest.mark.pg

JOBS = {"JA": 3, "JB": 3, "JC": 3}


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    source = copy.deepcopy(hw.LEDGER_SOURCE)
    source["read"] = {"unit": "group", "group_by": ["dt_job"], "identity": ["dt_job"],
                      "order_by": ["dt_job", "dt_x", "dt_y"]}
    monkeypatch.setattr(hw, "LEDGER_SOURCE", source)
    for world in hw.build(pg_engine, monkeypatch, tmp_path):
        yield world


def _write(world, jobs):
    import event_constants
    from database import crud, schemas
    from database.context import channel

    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(world["db"], hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"dt_job": job, "dt_x": x, "dt_y": 1, "netdie": 7, "hold": "agreed"},
                                      source_name="user", updated_by="t")
            for job in jobs for x in range(1, JOBS[job] + 1)]))
        world["db"].commit()


def _translate(world):
    hw.run_chain(dict(world, rules=[]))                 # the outbox marked as the chain does; no rule here
    while followup.drain_outbox_once(world["engine"], world["setup"]) is not None:
        pass


def _seats(world, monkeypatch):
    from admin import retroactive

    monkeypatch.setattr(retroactive, "_ledger_setup", lambda params: world["setup"])
    engine, setup = world["engine"], world["setup"]
    missing = len(backfill.rows_missing_from_the_index(engine, setup, hw.SOURCE, 10 ** 6))
    census = backfill.rows_not_yet_translated(engine, setup, hw.SOURCE)
    stamped = backfill.measure_row_census(engine, setup, hw.SOURCE)
    preview = retroactive.OPERATIONS["ledger_backfill"]["count"](world["db"], {"source": hw.SOURCE}, 1000)
    world["db"].rollback()
    return missing, census, stamped, preview


@pytest.mark.parametrize("translated", [(), ("JA",), ("JA", "JB", "JC")], ids=["none", "one job", "all"])
def test_a_group_source_counts_its_rows_left_as_the_index_does(world, monkeypatch, translated):
    _write(world, translated)
    _translate(world)
    _write(world, [job for job in JOBS if job not in translated])
    missing, census, stamped, preview = _seats(world, monkeypatch)

    rows = sum(JOBS.values())
    left = sum(n for job, n in JOBS.items() if job not in translated)
    assert census["relation_rows"] == rows, "CANARY: the board has its rows"
    assert census["indexed_rows"] == rows - left, "the index counts the translated jobs' ROWS"
    assert missing == census["not_yet"] == preview["affected"] == left, (missing, census, preview)
    assert stamped["difference"]["estimate"] == left and "not_comparable" not in stamped
    assert "not_comparable" not in census and "rows vs groups" not in str(preview["detail"])
    assert preview["count_kind"] == "exact" and (preview["absence"] is None) == bool(left), preview
