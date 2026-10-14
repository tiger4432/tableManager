"""총괄 10-14, 소유자 «ㅇㅇ ㄱ»: a molecule two of whose rows the source's `order_by` spells alike raised for the whole
page - a re-translate died on it, and the follow-up's event failed on it every time. Now it is that molecule's refusal
(`order_not_unique`), named and counted where an unreadable time is; the other molecules land.

  the follow-up   the event is done, not failed; the job whose rows repeat its order has no atom, the other job has
  the re-translate  ends, `refused` {"order_not_unique": 1}
"""
import copy
import json

import pytest
from sqlalchemy import text

from ledger import backfill, followup, gate
from support import hold_world as hw

pytestmark = pytest.mark.pg


def _grouped():
    source = copy.deepcopy(hw.LEDGER_SOURCE)
    source["read"].update({"unit": "group", "group_by": ["dt_job"], "identity": ["dt_job"],
                           "order_by": ["dt_job", "netdie"]})
    return source


def _catalog_claiming_netdie_is_a_key(load):
    """The ledger's catalog claiming `netdie` unique - a declared key is a claim, not a measurement (the box's dt_log
    declares dt_cell_key; one job holds 12,000 rows of one value). The chain keeps its own key."""
    def loaded(path):
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc[hw.OFFICIAL]["business_key"] = "netdie"
        claimed = path.with_name("table_config_claimed.json")
        claimed.write_text(json.dumps(doc), encoding="utf-8")
        return load(claimed)
    return loaded


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    monkeypatch.setattr(hw, "LEDGER_SOURCE", _grouped())
    monkeypatch.setattr(hw, "load_physical_catalog", _catalog_claiming_netdie_is_a_key(hw.load_physical_catalog))
    for world in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        yield world


def test_the_follow_up_refuses_the_molecule_and_the_event_is_done(world):
    hw.push(world, [{"log_id": "L1", "dt_job": "JA", "dt_x": 1, "dt_y": 1, "netdie": 5},
                    {"log_id": "L2", "dt_job": "JA", "dt_x": 2, "dt_y": 1, "netdie": 5},     # JA's order repeats
                    {"log_id": "L3", "dt_job": "JB", "dt_x": 1, "dt_y": 1, "netdie": 7}])
    hw.run_chain(world)
    said = []
    while True:
        done = followup.drain_outbox_once(world["engine"], world["setup"], rows=1000)
        if not done:
            break
        said.append((done.get("table"), done.get("sources"), done["outbox_id"]))
    last = said[-1][2]
    with world["engine"].connect() as conn:
        states = {r[0] for r in conn.execute(text("SELECT ledger_state FROM database_outbox WHERE id <= :i AND "
                                                  "ledger_state IS NOT NULL"), {"i": last})}
        jobs = {r[0] for r in conn.execute(text("SELECT subject_keys->>'dt_job' FROM ledger_events WHERE "
                                                "source_who = :s"), {"s": hw.SOURCE})}
    assert states and not any(s.startswith(followup.LEDGER_FAILED) for s in states), states
    assert jobs == {"JB"}, repr((jobs, said))

    # the re-translate: the same molecule, the same count - by its reason
    out = backfill.rescope(world["engine"], world["setup"], hw.SOURCE, None, [], apply=True,
                           page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True)
    assert out["refused"] == {gate.REFUSE_ORDER_NOT_UNIQUE: 1}, out
