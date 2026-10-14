"""총괄 e2f112f02 (소유자 «ㅇㅇ»): a whole-source re-translate died on one group_by molecule whose row list made a row-index
key over the btree limit - its slice, then the run, failed, and again at the same molecule. Now its page goes again a key
value at a time through the follow-up's call, the one over the limit refused by the follow-up's judgment, one line, its
count in the run's `refused`; every other key value written, the run to its end.

  the run    ends, one «refused <source> <key> = <value>: … row-index key too long (<the database's sentence>)» line,
             refused {"row_index_key_too_long": 1} (a key value), the page's other key values re-translated
  the atoms  by ref, as before the run - the refused molecule keeps its atoms (its withdrawal rolled back with it)
"""
import json
import secrets

import pytest
from sqlalchemy import text

from admin import retroactive
from chain import keyset_scan
from ledger import backfill, gate, roleframe
from support import hold_world as hw

pytestmark = pytest.mark.pg


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    for w in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        hw.push(w, [{"log_id": "L%03d" % i, "dt_job": "J%d" % (i % 10), "dt_x": i, "dt_y": 1, "netdie": i}
                    for i in range(40)])
        hw.settle(w)
        yield w


def _run(world):
    lines = []
    control = retroactive.RunControl(None, op="ledger_rescope", log=lines.append, report=lambda processed: None)
    token = keyset_scan.RUN_CONTROL.set(control)
    try:
        out = backfill.rescope(world["engine"], world["setup"], hw.SOURCE, None, [], apply=True,
                               page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True)
    finally:
        keyset_scan.RUN_CONTROL.reset(token)
    return out, lines


def _atoms_by_ref(world):
    with world["engine"].connect() as conn:
        return dict(conn.execute(text("SELECT source_raw_ref, count(*) FROM ledger_events WHERE source_who = :s "
                                      "GROUP BY 1"), {"s": hw.SOURCE}).fetchall())


def test_a_molecule_over_the_row_index_key_is_refused_and_the_run_goes_on(world, monkeypatch):
    real, made = roleframe._claim_source_raw_ref, []
    monkeypatch.setattr(roleframe, "_claim_source_raw_ref",
                        lambda event_ref, row_refs: made.append(event_ref) or real(event_ref, row_refs))
    first, _lines = _run(world)
    assert first["pages"] >= 3 and not first["refused"], first
    victim = made[-1]                                   # translated last: on the last page, beside other key values
    before = _atoms_by_ref(world)

    # the ref a molecule of thousands of rows makes - too long for the index's key; the real write says so
    rows = [secrets.token_urlsafe(48) for _ in range(120)]
    monkeypatch.setattr(roleframe, "_claim_source_raw_ref", lambda event_ref, row_refs: json.dumps(
        {"event": event_ref, "rows": sorted(set(row_refs)) + rows}, sort_keys=True, separators=(",", ":"))
        if event_ref == victim else real(event_ref, row_refs))
    one_by_one = []
    real_rescope = backfill.rescope

    def rescope(*args, **kwargs):
        if kwargs.get("key_range") == (None, None) and len(args) > 4 and len(args[4]) == 1:
            one_by_one.append(args[4][0])
        return real_rescope(*args, **kwargs)
    monkeypatch.setattr(backfill, "rescope", rescope)
    second, lines = _run(world)

    assert second["refused"] == {gate.REFUSE_ROW_INDEX_KEY_TOO_LONG: 1}, second
    said = [line for line in lines if " refused %s " % hw.SOURCE in line]
    assert len(said) == 1 and "row-index key too long (" in said[0], lines
    assert len(one_by_one) >= 2, one_by_one             # the page held other key values - they went on their own
    assert 0 < second["inserted"] < first["inserted"], (first["inserted"], second["inserted"])
    assert _atoms_by_ref(world) == before
