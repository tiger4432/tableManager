# -*- coding: utf-8 -*-
"""R2's preview (`replay.count_withdrawable`) counts the cells the run (`withdraw_source`) withdraws, and the run's dry
run counts the rows its apply deletes - same fixture, thirteen scenarios, a 4-column table and one whose columns sit in
chunk 1, on sqlite and PostgreSQL (lead 11-11; rows left to the run, lead ㄷ 11-14). A count of lines, bits read from
chunk 0 only, or lines of a deleted row answered another number than the run; a row count judged apart from
`cell_layer.shells` answered another in (a) a chain that only attached a value (s8), (b) a pin keeping a row (s4, s5)
and a value no layer carries (s9). The run's line and the CLI report say the rows it deleted.
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


def _drop(db):
    """PostgreSQL keeps the table between tests and a slot per column name (`line_columns`): small and wide reuse
    one name, so both go before and after."""
    from sqlalchemy import inspect

    db.rollback()
    lines.drop_line_table(db, TABLE)
    conn = db.connection()
    if inspect(conn).has_table(TABLE):
        conn.exec_driver_sql(f'DROP TABLE "{TABLE}"')
    db.query(lines.LineColumn).filter(lines.LineColumn.table_name == TABLE).delete()
    db.commit()


@pytest.fixture(name="env", params=[("small", "sqlite"), ("wide", "sqlite"),
                                    pytest.param(("small", "pg"), marks=pytest.mark.pg),
                                    pytest.param(("wide", "pg"), marks=pytest.mark.pg)],
                ids=lambda p: "-".join(p))
def fixture_env(request, db_session, monkeypatch):
    width, dialect = request.param
    db = db_session if dialect == "sqlite" else request.getfixturevalue("pg_session")
    if dialect == "pg":
        _drop(db)
    types = {**(PAD if width == "wide" else {}), "k": "string", "a": "string", "b": "string", "c": "string"}
    cfg = {"composite_key_source": ["k"], "column_types": types}
    models.init_dynamic_models({TABLE: cfg})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, cfg)
    Base.metadata.create_all(bind=db.get_bind())
    if dialect == "pg":    # the key index lines stand on - the runtime builds it, as conftest's pg_engine does
        import migrations.add_business_key_unique_index as bk
        db.connection().exec_driver_sql(f'CREATE UNIQUE INDEX "{bk.unique_index_name(TABLE)}" ON "{TABLE}" '
                                        '(business_key_val)')
    bits = lines.ensure_line_table(db, TABLE, cfg)["bits"]
    assert (min(bits[c] for c in "kabc") >= 64) == (width == "wide"), "canary: the columns' chunk"
    db.commit()
    ticking_clock(monkeypatch)

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
    yield env
    if dialect == "pg":
        _drop(db)


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


def _s10(env):
    crud.delete_rows_batch(env.db, TABLE, [env.rows()["K2"]], "kim")   # its lines stay - the run never pages it
    env.db.commit()


def _s10b(env):
    model = models.DYNAMIC_TABLES[TABLE]
    env.db.query(model).filter(model.row_id == env.rows()["K2"]).delete()
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
    "s10_a_row_the_grid_deleted": (_s10, SOURCE, {}, (5, 1, 1)),
    "s10b_a_row_deleted_raw": (_s10b, SOURCE, {}, (5, 1, 1)),
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
    assert (out["count_kind"], out["affected_label"], out["absence"]) == (
        retroactive.COUNT_EXACT, "cells to withdraw", None), "the run's cells, exact (lead ㄱ)"
    assert "at most" not in out["detail"].lower(), out["detail"]
    assert "why_upper_bound" not in out["extra"] and "deleted" not in str(out["extra"]), out["extra"]
    assert "counted when it runs" in out["detail"], out["detail"]
    assert not re.search(r"\d+ rows?\b|\d+ row\(s\)", out["detail"]), out["detail"]
    assert not [key for key in out["extra"] if "row" in key], out["extra"]


def test_the_runs_line_says_the_rows_it_deleted_in_words(env):
    result = retroactive._run_withdraw(env.db, {"table": TABLE, "source": SOURCE}, log=lambda m: None)
    said = retroactive.run_result_sentence(result)

    assert (result["rows_deleted"], result["cells_withdrawn"]) == (1, 7), "canary: the fixture"
    assert "rows deleted 1" in said, said
    assert "cells withdrawn 7" in said and "pinned, skipped 1" in said, said


def test_the_cli_report_says_what_the_run_did_dry_and_applied(env):
    from scripts import chain_replay_cli as cli

    dry = _run(env, SOURCE, {}, apply=False)
    said_dry = cli._report_withdraw(dry)
    run = _run(env, SOURCE, {}, apply=True)
    said_run = cli._report_withdraw(run)   # the dict `--apply` reads: run_here's stats are withdraw_source's

    assert (run["cells_withdrawn"], run["rows_deleted"]) == (7, 1), "canary: the fixture"
    for said in (said_dry, said_run):
        assert "rows nothing keeps      : %d" % run["rows_deleted"] in said, said
        assert "None" not in said, said
        assert "'%s' withdrawn" % SOURCE in said, "canary: a withdrawn cell's sample line"
