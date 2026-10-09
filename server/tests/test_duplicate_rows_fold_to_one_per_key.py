# -*- coding: utf-8 -*-
"""총괄 d72dc0283 (소유자 10-09 「해당 dtwaferid 중에서 최소 시간으로 접으면 되긴 함」): per key one row
stays - the earliest (or latest) by an order column, a blank one last, a tie the smaller row_id - and
the rest go through the product's delete door, a page at a time. A row with a blank key part ('' or
NULL) is left as it is (총괄 9c8b9f919).
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from admin import retroactive                                          # noqa: E402
from chain import replay                                               # noqa: E402
from database.database import Base                                     # noqa: E402
from database import crud, models, schemas                             # noqa: E402

TABLE = "fold_rows_log"
TABLES = {TABLE: {"business_key": "log_id", "composite_key_source": ["log_id"],
                  "column_types": {"log_id": "string", "wafer": "string", "lot": "string",
                                   "ts": "string", "v": "number", "job": "string", "mark": "string"},
                  "display_columns": ["log_id", "wafer", "lot", "ts", "v", "job", "mark"]}}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop(TABLE, None)


def _seed(db, rows):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name="seed", updated_by="fold")
        for r in rows]))
    db.commit()


def _left(db):
    db.expire_all()
    return sorted(r.log_id for r in db.query(models.DYNAMIC_TABLES[TABLE]).all())


def _row_id(db, log_id):
    return db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(log_id=log_id).one().row_id


def _fold(db, keys=("wafer",), keep="min", **kw):
    return replay.fold_duplicate_rows(db, TABLE, list(keys), "ts", keep=keep, apply=True,
                                      log=lambda m: None, **kw)


def test_the_earliest_of_a_key_stays_and_another_key_is_untouched(db):
    _seed(db, [{"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a3", "wafer": "W1", "ts": "2026-10-01 10:09:00"},
               {"log_id": "b1", "wafer": "W2", "ts": "2026-10-01 11:00:00"}])
    dry = replay.fold_duplicate_rows(db, TABLE, ["wafer"], "ts", log=lambda m: None)
    assert (dry["keys_folded"], dry["rows_to_delete"], dry["rows_kept"], dry["rows_deleted"]) == (1, 2, 2, 0)
    assert _left(db) == ["a1", "a2", "a3", "b1"]                         # the dry run writes nothing
    [one] = dry["sample"]
    assert one["key"] == {"wafer": "W1"} and one["rows"] == 3
    assert one["kept"]["row_id"] == _row_id(db, "a1")
    assert [d["row_id"] for d in one["deleted"]] == [_row_id(db, "a2"), _row_id(db, "a3")]
    done = _fold(db)
    assert done["rows_deleted"] == 2 and _left(db) == ["a1", "b1"]


def test_keep_max_keeps_the_latest(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"}])
    _fold(db, keep="max")
    assert _left(db) == ["a2"]


def test_the_same_time_keeps_the_smaller_row_id(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:00:00"}])
    smaller = min(_row_id(db, "a1"), _row_id(db, "a2"))
    _fold(db)
    db.expire_all()
    assert [r.row_id for r in db.query(models.DYNAMIC_TABLES[TABLE]).all()] == [smaller]


def test_a_blank_order_value_is_last(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"}])
    _fold(db)
    assert _left(db) == ["a2"]


def _blank_stored(db, column, *log_ids):
    """'' in the column - the write door stores a blank as NULL, so only SQL leaves an '' behind."""
    db.execute(text('UPDATE "%s" SET %s = \'\' WHERE log_id IN (%s)'
                    % (TABLE, column, ", ".join("'%s'" % i for i in log_ids))))
    db.commit()


def test_rows_with_one_blank_key_part_are_left_as_they_are(db):
    """총괄 9c8b9f919 (소유자 10-09 「ㅇㅇ 있어」): a blank coordinate is a different row, not one key."""
    _seed(db, [{"log_id": "p1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "p2", "wafer": "W1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "f1", "wafer": "W1", "lot": "L1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "f2", "wafer": "W1", "lot": "L1", "ts": "2026-10-01 10:05:00"}])
    done = _fold(db, keys=("wafer", "lot"))
    assert _left(db) == ["f1", "p1", "p2"] and done["rows_blank_key"] == 2


def test_rows_whose_key_is_all_blank_are_left_as_they_are(db):
    _seed(db, [{"log_id": "b%d" % i, "ts": "2026-10-01 10:0%d:00" % i} for i in range(3)])
    done = _fold(db, keys=("wafer", "lot"))
    assert _left(db) == ["b0", "b1", "b2"] and (done["rows_blank_key"], done["rows_to_delete"]) == (3, 0)


def test_an_empty_string_is_blank_as_null_is(db):
    _seed(db, [{"log_id": "n1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "e1", "wafer": "W1", "lot": "x", "ts": "2026-10-01 10:05:00"},
               {"log_id": "e2", "wafer": "W1", "lot": "x", "ts": "2026-10-01 10:09:00"}])
    _blank_stored(db, "lot", "e1", "e2")
    done = _fold(db, keys=("wafer", "lot"))
    assert _left(db) == ["e1", "e2", "n1"] and done["rows_blank_key"] == 3


def test_the_preview_the_run_and_the_cli_say_the_rows_left_for_a_blank_key(db, monkeypatch, capsys):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "lot": "L1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "lot": "L1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "p1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "p2", "wafer": "W1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "q1", "ts": "2026-10-01 10:00:00"}])
    params = retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer,lot", "order": "ts"})
    said = retroactive.OPERATIONS["fold_duplicate_rows"]["count"](db, params, 1000)
    assert (said["affected"], said["extra"]["rows_blank_key"], said["extra"]["rows_kept"]) == (1, 3, 4)
    assert "3 row(s) with a blank key part are left as they are." in said["detail"], said["detail"]
    if os.path.join(SERVER_DIR, "scripts") not in sys.path:
        sys.path.append(os.path.join(SERVER_DIR, "scripts"))
    import chain_replay_cli
    from database import database
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    assert chain_replay_cli.main(["fold-rows", TABLE, "--keys", "wafer,lot", "--order", "ts"]) == 0
    assert "3 row(s) with a blank key part are left as they are." in capsys.readouterr().out
    ran = retroactive.OPERATIONS["fold_duplicate_rows"]["run"](db, params, lambda m: None)
    assert (ran["rows_deleted"], ran["rows_blank_key"]) == (1, 3)
    assert _left(db) == ["a1", "p1", "p2", "q1"]


def test_a_stop_between_pages_keeps_what_went_and_a_rerun_finds_the_rest(db, monkeypatch):
    _seed(db, [{"log_id": "a%d" % i, "wafer": "W1", "ts": "2026-10-01 10:0%d:00" % i} for i in range(4)])
    monkeypatch.setattr(replay, "FOLD_ROWS_PAGE", 1)
    seen = []

    def checkpoint(done, total):
        seen.append((done, total))
        return done >= 1
    first = _fold(db, checkpoint=checkpoint)
    assert first["stopped"] and first["rows_deleted"] == 1 and seen == [(0, 3), (1, 3)]
    again = _fold(db)
    assert again["rows_to_delete"] == 2 and again["rows_deleted"] == 2 and _left(db) == ["a0"]


def test_a_column_the_table_does_not_declare_is_refused_by_name(db):
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer,wafer_id", "order": "ts"})
    assert "wafer_id" in str(refused.value)
    with pytest.raises(retroactive.RetroactiveRefused):
        retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer", "order": "ts",
                                                     "keep": "first"})


def test_the_cli_previews_and_writes_nothing_without_apply(db, monkeypatch, capsys):
    if os.path.join(SERVER_DIR, "scripts") not in sys.path:
        sys.path.append(os.path.join(SERVER_DIR, "scripts"))
    import chain_replay_cli
    from database import database

    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"}])
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    assert chain_replay_cli.main(["fold-rows", TABLE, "--keys", "wafer", "--order", "ts"]) == 0
    said = capsys.readouterr().out
    assert "1 key(s) of (wafer) in 'fold_rows_log' hold more than one row: 1 row(s) go, 1 stay." in said, said
    assert said.rstrip().endswith("-> add --apply to delete") and _left(db) == ["a1", "a2"]


def test_the_preview_says_keys_rows_and_a_sample(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "b1", "wafer": "W2", "ts": "2026-10-01 11:00:00"}])
    params = retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer", "order": "ts"})
    said = retroactive.OPERATIONS["fold_duplicate_rows"]["count"](db, params, 1000)
    assert (said["affected"], said["scanned"], said["extra"]["keys_folded"], said["extra"]["rows_kept"]) \
        == (1, 3, 1, 2)
    assert said["detail"].startswith("1 key(s) of (wafer) in 'fold_rows_log' hold more than one row: "
                                     "1 row(s) go, 2 stay."), said["detail"]
    assert "wafer=W1: keeps 2026-10-01 10:00:00, deletes 2026-10-01 10:05:00" in said["detail"], said["detail"]


# 총괄 1d2a7e0fd (소유자 10-09 「접기에서 job 에 auto 들어가 있는 거 1순위로 살리기」): a row whose column holds
# the operator's text stays first; the text and the column are the operator's, written here as data.
PREFER = {"prefer_column": "job", "prefer_text": "auto"}


def test_a_preferred_row_stays_though_it_is_later(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00", "job": "manual"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:09:00", "job": "run auto 3"}])
    done = _fold(db, **PREFER)
    assert _left(db) == ["a2"] and done["keys_preferred"] == 1


def test_of_two_preferred_rows_the_earliest_stays(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00", "job": "manual"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:09:00", "job": "auto"},
               {"log_id": "a3", "wafer": "W1", "ts": "2026-10-01 10:05:00", "job": "auto"}])
    _fold(db, **PREFER)
    assert _left(db) == ["a3"]


def test_without_a_preferred_row_the_earliest_stays_as_before(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:05:00", "job": "manual"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:00:00"}])
    done = _fold(db, **PREFER)
    assert _left(db) == ["a2"] and done["keys_preferred"] == 0


def test_the_text_is_matched_in_any_case(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00", "job": "manual"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:09:00", "job": "AUTO_x"}])
    _fold(db, **PREFER)
    assert _left(db) == ["a2"]


@pytest.mark.parametrize("params,said", [
    ({"prefer_column": "job"}, "prefer_column and prefer_text go together"),
    ({"prefer_text": "auto"}, "prefer_column and prefer_text go together"),
    ({"prefer_column": "job_name", "prefer_text": "auto"}, "job_name"),
])
def test_one_of_the_two_or_a_column_the_table_lacks_is_refused_by_name(db, params, said):
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer", "order": "ts", **params})
    assert said in str(refused.value)
    with pytest.raises(replay.ReplayRefused) as refused:
        replay.fold_duplicate_rows(db, TABLE, ["wafer"], "ts", log=lambda m: None, **params)
    assert said in str(refused.value)


def test_a_preferred_fold_leaves_blank_key_rows_and_says_what_it_kept(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "lot": "L1", "ts": "2026-10-01 10:00:00", "job": "manual"},
               {"log_id": "a2", "wafer": "W1", "lot": "L1", "ts": "2026-10-01 10:09:00", "job": "auto"},
               {"log_id": "p1", "wafer": "W1", "ts": "2026-10-01 10:00:00", "job": "manual"},
               {"log_id": "p2", "wafer": "W1", "ts": "2026-10-01 10:05:00", "job": "auto"}])
    params = retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer,lot", "order": "ts", **PREFER})
    said = retroactive.OPERATIONS["fold_duplicate_rows"]["count"](db, params, 1000)
    assert (said["extra"]["keys_preferred"], said["extra"]["rows_blank_key"]) == (1, 2)
    assert "a row whose job holds 'auto' (any case) stays first - 1 key(s) keep one" in said["detail"], said["detail"]
    assert "keeps 2026-10-01 10:09:00 (job=auto), deletes 2026-10-01 10:00:00 (job=manual)" in said["detail"]
    ran = retroactive.OPERATIONS["fold_duplicate_rows"]["run"](db, params, lambda m: None)
    assert (ran["rows_deleted"], ran["keys_preferred"], ran["rows_blank_key"]) == (1, 1, 2)
    assert _left(db) == ["a2", "p1", "p2"]


# 총괄 83c05cfbb (소유자 10-09 「수동 중에 좌표 변환 잘못돼서 겹치는 거는 지워져서 원래 다른 진짜 정보가 날아갈까 봐」): only
# the rows whose column holds the text fold - two events of one chip; a manual row is a different row.
SCOPE = {"only_column": "job", "only_text": "auto"}


def test_only_the_rows_in_scope_fold_and_the_rest_are_left_and_counted(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00", "job": "auto_1"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00", "job": "AUTO_2"},
               {"log_id": "m1", "wafer": "W1", "ts": "2026-10-01 09:00:00", "job": "manual"},
               {"log_id": "a3", "wafer": "W2", "ts": "2026-10-01 11:00:00", "job": "auto"},
               {"log_id": "m2", "wafer": "W2", "ts": "2026-10-01 11:05:00", "job": "manual"}])
    preview = retroactive.count(db, "fold_duplicate_rows",
                                {"table": TABLE, "keys": "wafer", "order": "ts", **SCOPE})
    done = _fold(db, **SCOPE)
    assert (done["rows_to_delete"], done["keys_folded"], done["rows_out_of_scope"]) == (1, 1, 2)
    assert _left(db) == ["a1", "a3", "m1", "m2"], "W1's manual row stays; W2 has one row in scope - none folds"
    assert preview["extra"]["rows_out_of_scope"] == done["rows_out_of_scope"]
    assert "Only rows whose job holds 'auto' (any case) fold - 2 row(s) outside" in preview["detail"]


@pytest.mark.parametrize("half", [{"only_column": "job"}, {"only_text": "auto"}])
def test_a_scope_written_half_is_refused_by_name(db, half):
    with pytest.raises(retroactive.RetroactiveRefused, match="only_column and only_text go together"):
        retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer", "order": "ts", **half})


# 총괄 016a766af (소유자 「접는 거 아예 삭제하지 말고」): the rows that fold are marked, never deleted - what the
# rules that exclude by the mark take back is measured on PostgreSQL
# (`test_a_folded_row_is_marked_and_what_it_fed_taken_back`).
def test_a_mark_deletes_nothing_names_the_row_kept_and_a_marked_row_ranks_no_more(db, monkeypatch):
    monkeypatch.setattr(replay, "load_rules", lambda: [])
    _seed(db, [{"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a3", "wafer": "W1", "ts": "2026-10-01 10:09:00"},
               {"log_id": "b1", "wafer": "W2", "ts": "2026-10-01 11:00:00"}])
    done = _fold(db, mark_column="mark")
    marks = {r.log_id: r.mark for r in db.query(models.DYNAMIC_TABLES[TABLE]).all()}
    kept = replay.FOLD_MARK % _row_id(db, "a1")
    assert (done["rows_to_mark"], done["rows_marked"], done["rules_woken"]) == (2, 2, [])
    assert (_left(db), marks) == (["a1", "a2", "a3", "b1"], {"a1": None, "a2": kept, "a3": kept, "b1": None})
    again = _fold(db, mark_column="mark")
    assert (again["rows_to_mark"], again["rows_already_marked"]) == (0, 2)


def test_a_mark_with_no_recount_paired_says_the_holds_stay(db, monkeypatch):
    copy = {"name": "fr_copy", "trigger_table": TABLE, "target_table": "elsewhere", "exclude": ["mark"]}
    monkeypatch.setattr(replay, "load_rules", lambda: [copy])
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"}])
    said = retroactive.count(db, "fold_duplicate_rows",
                             {"table": TABLE, "keys": "wafer", "order": "ts", "mark_column": "mark"})
    assert (said["extra"]["rules_woken"], said["extra"]["rules_recounting"]) == (["fr_copy"], [])
    assert "the rules that exclude by mark (fr_copy) run on them and take back what they fed; no recount rule " \
           "paired - holds stay as they are." in said["detail"], said["detail"]


def test_a_mark_column_that_is_not_text_is_refused(db):
    with pytest.raises(retroactive.RetroactiveRefused, match="mark_column 'v' is a number column"):
        retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer", "order": "ts",
                                                     "mark_column": "v"})
