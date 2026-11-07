# -*- coding: utf-8 -*-
"""Owner 10-26 «버전 리플레이 버전이 같아도 들어온 새 걸로 업데이트되게» (lead ㄱ): the same version is taken - a map at
the stored map's version is written when its content differs and left as it is when it is the same, so a map file read
again purges and rewrites nothing (a 20x20 map was 400 rows deleted and made again, its chain run on them).

  file        a 20x20 map, one cell changed at the same version     -> that cell written (the map replaced)
              the same 20x20 map read again                          -> cells · layers · history · outbox as they were
              the same version, a cell fewer                         -> the map replaced: the cell gone
  pushes      the purge form and the diff form, the same map again   -> nothing written, said «unchanged»
  older       a lower version                                        -> refused, as before
"""
import os

import pytest

from database import crud, models
from test_an_older_map_is_refused_whole import DIFF, PURGE, _map, _push, _results, env, fixture_watcher  # noqa: F401

SIDES = (("cells", None), ("layers", models.CellSource), ("overwrites", models.CellOverwrite),
         ("history", models.AuditLog), ("outbox", models.DatabaseOutbox))
GRID = ["c%02d_%02d" % (x, y) for x in range(20) for y in range(20)]


def _snap(db, table):
    db.expire_all()
    out = {}
    for name, model in SIDES:
        model = model or models.DYNAMIC_TABLES[table]
        q = db.query(model)
        if model is not models.DYNAMIC_TABLES[table]:
            q = q.filter(model.table_name == table)
        cols = [c.name for c in model.__table__.columns]
        out[name] = sorted(tuple(str(getattr(r, c)) for c in cols) for r in q.all())
    return out


def _csv(rev, changed=None, cells=GRID):
    return "job,cell,v,rev\n" + "".join("J,%s,%s,%s\n" % (c, "other" if c == changed else "v", rev) for c in cells)


def _read(watcher, text, bump):
    handler, workspace, factory = watcher
    path = os.path.join(workspace, "raws", "a.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    stat = os.stat(path)
    os.utime(path, (stat.st_atime, stat.st_mtime + bump))
    handler._handle_event(path)
    handler.heavy_lane.run_all()
    db = factory()
    try:
        return _snap(db, DIFF), _map(db, DIFF)
    finally:
        db.close()


def test_a_same_version_map_with_one_cell_changed_is_written(watcher):
    _read(watcher, _csv(2), 0)
    _snap_after, drawn = _read(watcher, _csv(2, changed=GRID[7]), 100)
    assert len(drawn) == 400 and (GRID[7], "other", 2.0) in drawn and (GRID[8], "v", 2.0) in drawn


def test_the_same_20x20_map_read_again_writes_nothing(watcher):
    before, drawn = _read(watcher, _csv(2), 0)
    assert len(drawn) == 400 and len(before["outbox"]) >= 1
    after, _drawn = _read(watcher, _csv(2), 100)
    for name, _model in SIDES:
        assert after[name] == before[name], name
    assert _results(watcher[2])["a.csv"] == ("SUCCESS", 400, 0, 0, None), "400 rows unchanged, none refused"


def test_the_same_version_with_a_cell_fewer_replaces_the_map(watcher):
    _read(watcher, _csv(2), 0)
    _after, drawn = _read(watcher, _csv(2, cells=GRID[1:]), 100)
    assert len(drawn) == 399 and GRID[0] not in {cell for cell, _v, _r in drawn}


@pytest.mark.parametrize("table", [PURGE, DIFF])
def test_a_pushed_map_the_same_as_stored_writes_nothing(env, table):
    _push(env, table, ("c1", "c2"), 2, "new")
    before = _snap(env, table)
    said = _push(env, table, ("c1", "c2"), 2, "new")
    assert (said["mode"], said["reason"], said["deleted"]) == ("unchanged", crud.NOTE_MAP_UNCHANGED, 0)
    assert _snap(env, table) == before


@pytest.mark.parametrize("table", [PURGE, DIFF])
def test_an_older_map_is_still_refused(env, table):
    _push(env, table, ("c1", "c2"), 2, "new")
    said = _push(env, table, ("c1", "c2"), 1, "new")
    assert (said["mode"], said["reason"]) == ("refused", crud.REASON_VERSION_OLDER)
