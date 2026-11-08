# -*- coding: utf-8 -*-
"""Every page loop shows progress within the page cap (소유자 10-12 「모든 소급은 5 초에 한 번은 진행 상황이 보이게
배치 크기 조절해」 · 「한 배치에 5 초 이내 무조건」 · 「인벤토리 리플레이는 1 행씩 시작해야지」): on a fixture slowed per
row, the first page is one row, no page and no gap between page lines passes the cap, and the rows read are every row
once in order - what a fixed page size reads. The keyset scan (`iter_pages`); a live proposal's pages stay fixed
(총괄 a02ad0f2b NO-GO ①). Time is scaled: target 0.3 s, cap 0.5 s (3 s · 5 s)."""
import os
import sys
import time

import pytest

from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from admin import retroactive                                               # noqa: E402
from chain import keyset_scan                                               # noqa: E402

TARGET, CAP, PER_ROW, ROWS = 0.3, 0.5, 0.01, 300
Base = declarative_base()


class Row(Base):
    __tablename__ = "paged"
    row_id = Column(String, primary_key=True)


def _walk(pages_of):
    """Each page slowed PER_ROW a row, a page line at its end -> (rows read, page sizes, page seconds, line times)."""
    lines, said = [], []
    control = retroactive.RunControl(None, op="probe", log=lambda line: (lines.append(line), said.append(time.monotonic())))
    started, read, sizes, seconds = time.monotonic(), [], [], []
    for page in pages_of():
        began = time.monotonic()
        time.sleep(PER_ROW * len(page))
        read += page
        sizes.append(len(page))
        seconds.append(time.monotonic() - began)
        control.progress(len(read))
    return read, sizes, seconds, [started] + said, lines


def _assert_within_the_cap(read, sizes, seconds, times, lines, every):
    assert read == every, "a row read twice or missed"
    assert sizes[0] == 1 and lines[0].startswith("[probe] page 1: 1 rows · "), lines[:2]
    assert max(sizes) > 1, "the size never grew"
    assert max(seconds) <= CAP, (sizes, seconds)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert max(gaps) <= CAP, (sizes, gaps)


def test_a_page_over_the_page_time_cuts_the_next_by_its_overshoot(monkeypatch):
    """A slow page (5 s against 3 s, on a fake clock) cuts the next page to size x 3 / 5, rounded down - neither kept
    nor grown by the rate rule's ceiling (총괄 2ea5ee2a7 ④, the surviving «shrink off» mutant)."""
    ticks = iter([0.0, 0.1, 0.2, 5.2])
    monkeypatch.setattr(keyset_scan.time, "monotonic", lambda: next(ticks))
    size = keyset_scan.PageSize(keyset_scan.DEFAULT_CHUNK_SIZE, seconds=3)
    assert [size.next() for _ in range(4)] == [1, 2, 4, 2]


def test_a_page_grows_by_the_slower_of_its_own_and_the_page_befores_rate(monkeypatch):
    """A slow page (1 row in 1 s) then a fast one (2 rows in 0.1 s): the next fills 3 s at the slower rate - 3, not the
    fast page's 4 (총괄 2ea5ee2a7, 응용: a page sized by a fast page before it took 5.2 s)."""
    ticks = iter([0.0, 1.0, 1.1])
    monkeypatch.setattr(keyset_scan.time, "monotonic", lambda: next(ticks))
    size = keyset_scan.PageSize(keyset_scan.DEFAULT_CHUNK_SIZE, seconds=3)
    assert [size.next() for _ in range(3)] == [1, 2, 3]


def test_the_keyset_scan_starts_at_one_row_and_keeps_every_page_under_the_cap():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    every = ["r%04d" % n for n in range(ROWS)]
    db.add_all([Row(row_id=r) for r in every])
    db.commit()
    size = keyset_scan.PageSize(keyset_scan.DEFAULT_CHUNK_SIZE, seconds=TARGET)
    read, sizes, seconds, times, lines = _walk(lambda: (
        [r[0] for r in page] for page in keyset_scan.iter_pages(db, Row, columns=[], size=size)))
    _assert_within_the_cap(read, sizes, seconds, times, lines, every)


def _sizes(monkeypatch, fixed, per_row, pages=40):
    """The sizes `PageSize` gives (3 s a page, cap 1000) on a fake clock where a page takes `fixed` + `per_row` a row,
    the first 2.9 s more (its one-off reload and progress on B's board 11-08) -> (sizes, the PageSize)."""
    now = [0.0]
    monkeypatch.setattr(keyset_scan.time, "monotonic", lambda: now[0])
    size = keyset_scan.PageSize(keyset_scan.DEFAULT_CHUNK_SIZE, seconds=3)
    sizes = []
    for n in range(pages):
        sizes.append(size.next())
        now[0] += fixed + per_row * sizes[-1] + (2.9 if n == 0 else 0)
    return sizes, size


def test_a_fixed_cost_a_page_is_read_apart_and_the_pages_still_grow_to_the_cap(monkeypatch):
    """B's board 11-08 on a fake clock (소유자 11-08): 2.5 s a page held pages at ~190 rows; read apart, the rows fill
    what F leaves of the page time - the whole page, F with it, within it (QA 11-08: past F it took F + 3 s). c 60 ms
    a row stays at ~49 - c is not F's to take off; no fixed cost stays at the cap. The fit leaves the first page's
    one-off out."""
    sizes, size = _sizes(monkeypatch, 2.5, 0.002)
    assert sizes[-1] == 250, sizes
    assert size.fit.value() == (pytest.approx(2.5), pytest.approx(0.002))
    sizes = _sizes(monkeypatch, 2.5, 0.003, pages=200)[0]
    assert max(2.5 + 0.003 * n for n in sizes[1:]) <= 3 + 0.003, sizes
    assert 45 <= _sizes(monkeypatch, 0.0, 0.06)[0][-1] <= 51
    assert _sizes(monkeypatch, 0.0, 0.002)[0][-1] == 1000
    # 총괄 11-08: the rows' share under the noise (c read <= 0) doubles - on the board it grew 1.2x, 30 pages to 1000
    sizes = _sizes(monkeypatch, 2.5, 0.0)[0]
    assert 1000 in sizes[:14], sizes


def test_a_fixed_cost_at_the_page_time_is_said_once_and_pages_stay_at_one_row(monkeypatch):
    """QA 11-08: F 3.1 s against a 3 s page - no size fits, so pages stay at one row and the run says so once, with F."""
    said = []
    monkeypatch.setattr(keyset_scan, "say", lambda line: said.append(line) or True)
    sizes = _sizes(monkeypatch, 3.1, 0.0, pages=10)[0]
    assert sizes == [1] * 10, sizes
    assert len(said) == 1 and "fixed cost is 3.1 s" in said[0] and "cannot fit" in said[0], said


def test_a_retroactive_chain_lines_batch_reads_the_fit_a_page_reads(monkeypatch):
    """QA 11-08: the same F and c size a chain line's batch (`slots.next_row_budget`) as `PageSize` sizes a page - the
    line's fit crosses to the slot and back as its sums."""
    from chain import slots

    sizes, size = _sizes(monkeypatch, 2.5, 0.002)
    fit, rows = None, 1
    for n in range(40):
        took = 2.5 + 0.002 * rows + (2.9 if n == 0 else 0)
        line = keyset_scan.Fit(fit)
        rows = slots.next_row_budget(rows, took, target=3, fit=line)
        fit = line.sums
    assert rows == sizes[-1] == 250, (rows, sizes)


@pytest.mark.pg
def test_a_ledger_backfill_page_says_its_read_and_its_translation(pg_engine, monkeypatch, tmp_path, doubling_pages):
    """총괄 10-12 (응용: a ledger backfill page took 7.7 s with its one line at its end): inside each page a line after
    the read and one after the translation and write - the steps a slow page passes, each stamping the progress time."""
    import uuid

    from database import models
    from ledger import backfill
    from support import hold_world as hw

    built = hw.build(pg_engine, monkeypatch, tmp_path, batch=True)
    world = next(built)
    try:
        with world["engine"].begin() as conn:
            conn.execute(models.DYNAMIC_TABLES[hw.OFFICIAL].__table__.insert(), [
                {"row_id": str(uuid.uuid4()), "dt_job": "J%d" % i, "dt_x": i, "dt_y": i, "netdie": 1.0 + i,
                 "hold": "agreed"} for i in range(3)])
        lines = []

        def hook(_rows, _total):
            return False
        hook.step = lambda name, page, pages, rows: lines.append((name, page, rows))
        backfill._run_via_events(world["engine"], world["setup"], hw.SOURCE, checkpoint=hook)
        assert lines == [("read", 1, 1), ("translated", 1, 1), ("read", 2, 2), ("translated", 2, 2)], lines
    finally:
        next(built, None)
