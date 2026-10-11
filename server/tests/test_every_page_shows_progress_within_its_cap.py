# -*- coding: utf-8 -*-
"""Every page loop shows progress within the page cap (소유자 10-12 「모든 소급은 5 초에 한 번은 진행 상황이 보이게
배치 크기 조절해」 · 「한 배치에 5 초 이내 무조건」 · 「인벤토리 리플레이는 1 행씩 시작해야지」): on a fixture slowed per
row, the first page is one row, no page and no gap between page lines passes the cap, and the rows read are every row
once in order - what a fixed page size reads. The keyset scan (`iter_pages`); a live proposal's pages stay fixed
(총괄 a02ad0f2b NO-GO ①). Time is scaled: target 0.3 s, cap 0.5 s (3 s · 5 s)."""
import os
import sys
import time

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

