# -*- coding: utf-8 -*-
"""R2's preview (`replay.count_withdrawable`) counts the cells the run (`withdraw_source`) withdraws, and the run's dry
run counts the rows its apply deletes - same fixture, eleven scenarios, a 4-column table and one whose columns sit in
chunk 1 (lead 11-11; rows left to the run, lead ㄷ 11-14). A count of lines, or bits read from chunk 0 only, answered
another number than the run; a row count judged apart from `cell_layer.shells` answered another in (a) a chain that
only attached a value (s8), (b) a pin keeping a row (s4, s5) and a value no layer carries (s9).
"""
import re

import pytest

from admin import retroactive
from chain import replay
from database import crud, lines, models, schemas
from database.database import Base
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE, SOURCE, OTHER = "wd_preview", "s.csv", "f.csv"
PAD = {f"p{i:02d}": "string" for i in range(64)}     # first, so k · a · b · c take bits 64.. (chunk 1)


@pytest.fixture(name="env", params=["small", "wide"])
def fixture_env(request, db_session, monkeypatch):
    types = {**(PAD if request.param == "wide" else {}), "k": "string", "a": "string", "b": "string", "c": "string"}
    cfg = {"composite_key_source": ["k"], "column_types": types}
    models.init_dynamic_models({TABLE: cfg})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, cfg)
    Base.metadata.create_all(bind=db_session.get_bind())
    bits = lines.ensure_line_table(db_session, TABLE, cfg)["bits"]
    assert (min(bits[c] for c in "kabc") >= 64) == (request.param == "wide"), "canary: the columns' chunk"
    db_session.commit()
    ticking_clock(monkeypatch)
    db = db_session

    class Env:
        def put(self, source, key, by="loader", with_key=True, **values):
            crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
                business_key_val=key, updates={**({"k": key} if with_key else {}), **values}, source_name=source,
                updated_by=by)]))

        def rows(self):
            return {r.business_key_val: r.row_id for r in db.query(models.DYNAMIC_TABLES[TABLE])}

        def pin(self, key, col, src):
            db.add(models.CellOverwrite(table_name=TABLE, row_id=self.rows()[key], column_name=col, is_overwrite=False,
                                        updated_by="kim", manual_priority_source=src))
            db.commit()

    env = Env()
    env.db = db
    env.put(SOURCE, "K1", a="1", b="1")                 # only the source - a shell after
    env.put(SOURCE, "K2", a="2", b="2")
    env.put(OTHER, "K2", a="x", c="x")
    env.put(SOURCE, "K3", a="3")
    env.put(OTHER, "K3", a="y")
    env.put(OTHER, "K4", a="z")
    env.pin("K3", "a", SOURCE)                          # a pin on a claimed cell
    env.pin("K2", "c", SOURCE)                          # a pin on a cell the source never said
    return env


def _chain(origin):
    return crud.merged_layer_name(crud.CHAIN_SOURCE, origin)


def _s3(env):
    env.put(SOURCE, "K6", by="ruleX", b="6")            # the same source, another writer
    env.put(SOURCE, "K1", by="ruleX", c="9")            # beside a loader line on K1


def _s4(env):
    env.put(SOURCE, "K5", a="5")
    env.pin("K5", "a", SOURCE)                          # (b) its pinned cell keeps the row


def _s5(env):
    env.put(SOURCE, "K7", a="7")
    env.pin("K7", "c", OTHER)                           # (b) another source's pin keeps the row


def _s6(env):
    replay.withdraw_source(env.db, TABLE, SOURCE, columns=["b"], apply=True, log=lambda m: None)


def _s7(env):
    env.put(_chain("r1"), "K8", a="c1")
    env.put(_chain("r2"), "K8", a="c2")


def _s8(env):
    env.put(SOURCE, "K9", a="9")
    env.put(_chain("r9"), "K9", with_key=False, b="att")   # (a) a value only, no key cell - keeps nothing


def _s9(env):
    model = models.DYNAMIC_TABLES[TABLE]
    env.db.query(model).filter(model.row_id == env.rows()["K1"]).update({"c": "handwritten"})   # (b) no layer
    env.db.commit()


# name: (more of the fixture, source, the run's scope, the run's (cells_matched, pinned_skipped, rows_deleted))
SCENARIOS = {
    "s0_base": (None, SOURCE, {}, (8, 1, 1)),
    "s1_columns_a": (None, SOURCE, {"columns": ["a"]}, (3, 1, 0)),
    "s2_columns_b_c": (None, SOURCE, {"columns": ["b", "c"]}, (2, 0, 0)),
    "s3_written_by": (_s3, SOURCE, {"written_by": ["ruleX"]}, (4, 0, 1)),
    "s3b_written_by_column_c": (_s3, SOURCE, {"written_by": ["ruleX"], "columns": ["c"]}, (1, 0, 0)),
    "s4_a_pinned_cell_keeps_the_row": (_s4, SOURCE, {}, (10, 2, 1)),
    "s5_another_sources_pin_keeps_the_row": (_s5, SOURCE, {}, (10, 1, 1)),
    "s6_partly_withdrawn": (_s6, SOURCE, {}, (6, 1, 1)),
    "s7_two_chain_layers": (_s7, crud.CHAIN_SOURCE, {}, (4, 0, 1)),
    "s8_a_chain_that_only_attached_keeps_nothing": (_s8, SOURCE, {}, (10, 1, 2)),
    "s9_a_value_no_layer_carries_keeps_the_row": (_s9, SOURCE, {}, (8, 1, 0)),
}


def _scenario(env, name):
    more, source, scope, want = SCENARIOS[name]
    if more:
        more(env)
    return source, scope, want


def _run(env, source, scope, apply):
    out = replay.withdraw_source(env.db, TABLE, source, apply=apply, log=lambda m: None, **scope)
    env.db.rollback()
    return out


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_preview_counts_the_cells_the_run_withdraws(env, name):
    source, scope, want = _scenario(env, name)
    preview = replay.count_withdrawable(env.db, TABLE, source, **scope)
    run = _run(env, source, scope, apply=True)

    assert (run["cells_matched"], run["pinned_skipped"], run["rows_deleted"]) == want, "canary: the fixture"
    assert (preview["cells_claimed"], preview["pinned"], preview["cells_claimed"] - preview["pinned"]) == (
        run["cells_matched"], run["pinned_skipped"], run["cells_withdrawn"]), (preview, run)
    assert set(preview) == {"cells_claimed", "pinned"}, "rows are the run's to count (lead ㄷ)"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_a_dry_run_deletes_no_row_and_counts_the_rows_the_run_deletes(env, name):
    source, scope, want = _scenario(env, name)
    before = sorted(env.rows())
    dry = _run(env, source, scope, apply=False)
    assert sorted(env.rows()) == before, "the dry run deleted a row"
    run = _run(env, source, scope, apply=True)

    assert run["rows_deleted"] == want[2], "canary: the fixture"
    assert dry["rows_deleted"] == run["rows_deleted"], (dry, run)


def test_the_screen_draws_no_row_number_and_says_rows_are_counted_when_it_runs(env):
    out = retroactive.count(env.db, "withdraw", {"table": TABLE, "source": SOURCE})

    assert out["affected"] == 7, "canary: 8 cells claimed, 1 pinned"
    assert "counted when it runs" in out["detail"], out["detail"]
    assert not re.search(r"\d+ rows?\b|\d+ row\(s\)", out["detail"]), out["detail"]
    assert not [key for key in out["extra"] if "row" in key], out["extra"]
