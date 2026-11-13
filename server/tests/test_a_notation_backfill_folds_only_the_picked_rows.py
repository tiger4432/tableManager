# -*- coding: utf-8 -*-
"""The notation backfill folds only the rows a screen picked - `row_ids`, the cell chain_replay takes (lead 11-10,
owner «노테이션 소급 ㄱ»). Without it the whole table, as before; an id the table does not hold is named, not
counted as «0 rows»; an empty pick is refused, not read as «everything»."""
import pytest

from admin import retroactive
from chain import replay
from test_a_written_column_is_stored_folded import DECLARED, PLAIN, _declare, _rows, _write, env  # noqa: F401


def _stored(db, tmp_path, monkeypatch):
    _declare(tmp_path, monkeypatch, {})
    _write(db, PLAIN, [{"k": "K-01", "v": "wafer.1"}, {"k": "K-02", "v": "wafer.2"}])
    _declare(tmp_path, monkeypatch, DECLARED)
    return {row.k: row.row_id for row in _rows(db, PLAIN)}


def _shown(db):
    db.expire_all()
    return sorted((row.k, row.v) for row in _rows(db, PLAIN))


def test_only_the_picked_row_is_folded_and_an_id_the_table_does_not_hold_is_named(env, tmp_path, monkeypatch):
    ids = _stored(env, tmp_path, monkeypatch)
    count = retroactive.count(env, "fold_written_notation", {"table": PLAIN, "row_ids": [ids["K-01"], "no-such-row"]})
    assert (count["affected"], count["scanned"]) == (1, 1)
    assert "'%s' holds no row no-such-row. " % PLAIN in count["detail"], count["detail"]
    stats = replay.fold_written_notation(env, PLAIN, apply=True, row_ids=[ids["K-01"], "no-such-row"])
    assert stats["row_ids_not_found"] == ["no-such-row"]
    assert _shown(env) == [("K-01", "wafer-01"), ("K-02", "wafer.2")]
    replay.fold_written_notation(env, PLAIN, apply=True)                # no pick: the whole table, as before
    assert _shown(env) == [("K-01", "wafer-01"), ("K-02", "wafer-02")]


def test_a_pick_of_rows_the_table_does_not_hold_is_not_none(env, tmp_path, monkeypatch):
    _stored(env, tmp_path, monkeypatch)
    count = retroactive.count(env, "fold_written_notation", {"table": PLAIN, "row_ids": ["gone-1", "gone-2"]})
    assert (count["affected"], count["absence"]) == (0, retroactive.ABSENCE_CANNOT_POINT)
    assert "holds no row gone-1, gone-2" in count["detail"]


def test_an_empty_pick_is_refused_not_read_as_the_whole_table(env, tmp_path, monkeypatch):
    _stored(env, tmp_path, monkeypatch)
    with pytest.raises(replay.ReplayRefused, match="row_ids was given but empty; an empty selection would fold the "
                                                   "whole table instead of nothing"):
        replay.fold_written_notation(env, PLAIN, apply=True, row_ids=[" "])
    assert _shown(env) == [("K-01", "wafer.1"), ("K-02", "wafer.2")]


@pytest.mark.parametrize("op, params", [("fold_written_notation", {"table": PLAIN}), ("chain_replay", {"rule": "r"})])
@pytest.mark.parametrize("sent", [[], "", " , "])
def test_a_pick_sent_empty_is_refused_where_the_route_reads_it(env, op, params, sent):
    """Lead 11-10, a data guard: the route dropped an empty csv, so a screen that sent no rows ran on everything."""
    with pytest.raises(retroactive.RetroactiveRefused, match="row_ids was given but empty; an empty selection would "
                                                             "run %s on everything instead of nothing" % op):
        retroactive.validate(op, dict(params, row_ids=sent))


def test_a_pick_not_sent_is_the_whole_table_and_a_draft_keeps_a_blank_field(env):
    assert retroactive.validate("fold_written_notation", {"table": PLAIN}) == {"table": PLAIN}
    # a draft (the admin help) keeps the blank field for the operator to fill
    assert retroactive.validate("fold_written_notation", {"table": PLAIN, "row_ids": ""}, partial=True) ==         {"table": PLAIN}


def test_a_persons_line_the_backfill_re_spells_stays_theirs_and_is_no_new_act(env, tmp_path, monkeypatch):
    """Lead 11-11: the re-spelled line keeps its value's author (the person); the backfill's audit row names the
    backfill as the write's actor - so the re-correction figure is what it was before the fold."""
    import sqlalchemy as sa

    from database import crud, lines

    _declare(tmp_path, monkeypatch, {})
    _write(env, PLAIN, [{"k": "K-01", "v": "wafer.1"}], source=crud.USER_SOURCE)
    _declare(tmp_path, monkeypatch, DECLARED)
    before = crud.get_recorrection_stats(env, window_days=100000)
    assert before["measured_cells"], "canary: the person's write is measured"
    replay.fold_written_notation(env, PLAIN, apply=True)
    assert _shown(env) == [("K-01", "wafer-01")], "canary: the fold re-spelled the person's value"
    ab = lines.AuditBatch
    folded = sa.literal(replay.NOTATION_BACKFILL_SOURCE + "%")
    assert {who for (who,) in env.execute(sa.select(ab.written_by).where(
        ab.table_name == PLAIN, ab.transaction_id.like(folded)))} == {replay.NOTATION_BACKFILL_SOURCE}
    said = env.execute(sa.text('SELECT written_by FROM "%s" WHERE batch LIKE :b AND source_name = :s'
                               % lines.lines_relation(PLAIN)),
                       {"b": replay.NOTATION_BACKFILL_SOURCE + "%", "s": crud.USER_SOURCE}).scalars().all()
    assert said and set(said) == {"t"}, "the re-spelled line keeps its value's author"
    assert crud.get_recorrection_stats(env, window_days=100000) == before


def test_a_key_the_backfill_folds_onto_a_persons_row_merges_as_the_backfills_act(env, tmp_path, monkeypatch):
    """A (9b01e1d72 review): a re-spelled key that lands on another row merges the two - the merge is the backfill's
    act (its audit row and its lines' batch), the person's values stay theirs; the re-correction figure is unchanged."""
    from database import crud

    _declare(tmp_path, monkeypatch, {})
    _write(env, PLAIN, [{"k": "K-01", "v": "wafer-01"}, {"k": "K.1", "v": "wafer-02"}], source=crud.USER_SOURCE)
    _declare(tmp_path, monkeypatch, DECLARED)
    before = crud.get_recorrection_stats(env, window_days=100000)
    assert (before["measured_cells"], before["recorrected_cells"]) == (4, 0), before
    replay.fold_written_notation(env, PLAIN, apply=True)
    env.expire_all()
    assert [row.k for row in _rows(env, PLAIN)] == ["K-01"], "canary: the folded key merged the two rows"
    after = crud.get_recorrection_stats(env, window_days=100000)
    # one row now (its moved lines keep their own batch, one act): its two cells, and no new act on them
    assert (after["measured_cells"], after["recorrected_cells"]) == (2, before["recorrected_cells"] == 0 and 0), after


def test_a_value_no_line_said_that_a_backfill_merge_keeps_is_the_backfills_not_a_persons(env, tmp_path, monkeypatch):
    """A (11-11, after 4b5f7ac67): the merged-away row's value no line said becomes a line of the merge's writer -
    named after the merge's actor, the backfill, not «user (<tag>)»: a person's layer name with the backfill as its
    author and actor would count as a person's act."""
    import sqlalchemy as sa

    from database import crud, lines

    _declare(tmp_path, monkeypatch, {})
    _write(env, PLAIN, [{"k": "K-01", "v": "wafer-01"}, {"k": "K.1", "v": "wafer-02"}], source=crud.USER_SOURCE)
    env.execute(sa.text("UPDATE \"%s\" SET note = 'n' WHERE k = 'K.1'" % PLAIN))   # a value no line said
    env.commit()
    _declare(tmp_path, monkeypatch, DECLARED)
    before = crud.get_recorrection_stats(env, window_days=100000)
    replay.fold_written_notation(env, PLAIN, apply=True)
    env.expire_all()
    assert [(row.k, row.note) for row in _rows(env, PLAIN)] == [("K-01", "n")], "canary: merged, the value kept"
    said = env.execute(sa.text('SELECT source_name, written_by, batch FROM "%s" WHERE batch LIKE :b ORDER BY line_id'
                               % lines.lines_relation(PLAIN)), {"b": replay.NOTATION_BACKFILL_SOURCE + "%"}).all()
    by_backfill = [source for source, who, _batch in said if who == replay.NOTATION_BACKFILL_SOURCE
                   and source != crud.COLLISION_SOURCE]
    assert by_backfill and all(source.startswith(replay.NOTATION_BACKFILL_SOURCE + " (") for source in by_backfill), said
    # one row now: its key and value cells the person's (moved lines, one act each), the note no person's act
    after = crud.get_recorrection_stats(env, window_days=100000)
    assert (before["measured_cells"], after["measured_cells"], after["recorrected_cells"]) == (4, 2, 0), after

