# -*- coding: utf-8 -*-
"""총괄 402f1ab2e — the fold mapper: per wafer one job's log rows stay, the others are marked «folded into <job>»
(소유자 「AUTO 잡 먼저, 그 안에서 시간 빠른 거」 · 「매뉴얼끼리도 같은 규칙」 · 「replace map 느낌으로」).

The application lane's seed (rh_world_inv): CW1 AUTO_J1 · AUTO_J5 -> the earlier AUTO_J1 · CW3 MAN_J3 · AUTO_J4 -> AUTO_J4
· CW2 AUTO_J2 alone -> nothing; and two manual jobs on CW4 -> the earlier. Then what happens live.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import rule_run                                          # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402
from mappers import fold_unit                                       # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

INV, LOG = "fu_inventory", "fu_log"
TABLES = {INV: {"business_key": "dt_job", "composite_key_source": ["dt_job"],
                "column_types": {c: "string" for c in ("dt_job", "dt_job_id", "core_wafer", "wafer_out_time")},
                "display_columns": ["dt_job", "dt_job_id", "core_wafer", "wafer_out_time"]},
          LOG: {"business_key": "record_id", "composite_key_source": ["record_id"],
                "column_types": {c: "string" for c in ("record_id", "dt_job_id", "core_wafer", "fold_mark")},
                "display_columns": ["record_id", "dt_job_id", "core_wafer", "fold_mark"]}}
PARAMS = {"unit_table": INV, "group": "core_wafer", "unit": "dt_job_id", "order": "wafer_out_time",
          "prefer_column": "dt_job_id", "prefer_text": "AUTO", "mark_column": "fold_mark",
          "match": [{"left": "dt_job_id", "right": "dt_job_id"}, {"left": "core_wafer", "right": "core_wafer"}]}
RULES = [{"name": "fu_by_unit", "trigger_table": INV, "target_table": LOG, "mapper": fold_unit.NAME,
          "is_batch": True, "allow_chain_trigger": True, "params": PARAMS},
         {"name": "fu_by_log", "trigger_table": LOG, "target_table": LOG, "mapper": fold_unit.NAME,
          "is_batch": True, "trigger_columns": ["dt_job_id", "core_wafer"], "params": PARAMS}]
JOBS = [("AUTO_J1", "CW1", "2026-10-01 11:00:00"), ("AUTO_J5", "CW1", "2026-10-02 09:00:00"),
        ("AUTO_J2", "CW2", "2026-10-01 12:00:00"),
        ("MAN_J3", "CW3", "2026-10-03 11:00:00"), ("AUTO_J4", "CW3", "2026-10-03 12:00:00"),
        ("MAN_J6", "CW4", "2026-10-04 09:00:00"), ("MAN_J7", "CW4", "2026-10-04 10:00:00")]


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    fold_unit._register()
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _write(db, table, rows, source="seed"):
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            updates=dict(r), source_name=source, updated_by="fu") for r in rows]))
    db.commit()


def _drain(db):
    for _ in range(6):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        groups = {}
        for e in pending:
            groups.setdefault(get_payload_dict(e).get("transaction_id"), []).append(e)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, [dict(r) for r in RULES])
            assert ok, error
            for e in events:
                event_constants.mark_processed(e, "SUCCESS")
            db.commit()
    raise AssertionError("the chain did not settle")


def _logs(job, wafer, n=3):
    return [{"record_id": "%s-%d" % (job, i), "dt_job_id": job, "core_wafer": wafer} for i in range(n)]


def _seed(db, jobs=JOBS):
    _write(db, LOG, [r for job, wafer, _t in jobs for r in _logs(job, wafer)])
    _drain(db)
    _write(db, INV, [{"dt_job": job, "dt_job_id": job, "core_wafer": wafer, "wafer_out_time": t} for job, wafer, t in jobs])
    _drain(db)


def _marks(db):
    """{job: the set of marks its log rows show}."""
    db.expire_all()
    out = {}
    for row in db.query(models.DYNAMIC_TABLES[LOG]).all():
        out.setdefault(row.dt_job_id, set()).add("" if crud.is_blank_value(row.fold_mark) else row.fold_mark)
    return out


SEEDED = {"AUTO_J1": {""}, "AUTO_J5": {"folded into AUTO_J1"}, "AUTO_J2": {""},         # the winners' rows: never written
          "MAN_J3": {"folded into AUTO_J4"}, "AUTO_J4": {""}, "MAN_J6": {""}, "MAN_J7": {"folded into MAN_J6"}}


def test_per_wafer_the_auto_job_first_then_the_earliest_keeps_its_rows(db):
    _seed(db)
    assert _marks(db) == SEEDED


def test_running_it_again_writes_nothing(db):
    _seed(db)
    count = lambda: (db.query(models.AuditLog).count(), db.query(models.CellSource).count())   # noqa: E731
    before = count()
    rows = db.query(models.DYNAMIC_TABLES[INV]).all()
    out = fold_unit.fold_by_unit(db, [{"row_id": r.row_id, "data": {}} for r in rows], dict(RULES[0]))
    crud.apply_batch_updates(db, LOG, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        **item, source_name=rule_run.layer_of_a_rules_write(None, item["origin_row_id"]),   # the worker's seat
        updated_by=fold_unit.NAME) for item in out["updates"]]))
    db.commit()
    # 총괄 406d7c102: every losing row is handed again - one left out is a mark the edit's withdrawal takes back
    assert len(out["updates"]) == 9 and count() == before, "the losing jobs' 3 + 3 + 3 rows, written again as they are"


@pytest.mark.parametrize("times", [2, 3])
def test_replaying_the_inventory_rule_keeps_every_mark(db, times):
    """응용 진짜 프로세스 (총괄 406d7c102): the second replay withdrew all 321,315 marks - the chain takes back what a
    rule's edited source rows fed and this run did not hand, and the mapper had left the marked rows out."""
    from chain import replay

    _seed(db)
    for _ in range(times):
        replay.replay_rule(db, dict(RULES[0]), apply=True, log=lambda *a, **k: None)
        _drain(db)
        assert _marks(db) == SEEDED


def test_a_losing_jobs_inventory_row_edited_keeps_its_marks(db):
    _seed(db)
    inv = models.DYNAMIC_TABLES[INV]
    row = db.query(inv).filter(inv.dt_job_id == "AUTO_J5").one()
    crud.apply_batch_updates(db, INV, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=row.row_id, updates={"wafer_out_time": "2026-10-02 10:00:00"}, source_name="user",
        updated_by="fu")]))
    db.commit()
    _drain(db)
    assert _marks(db) == SEEDED, "AUTO_J5 still loses to the earlier AUTO_J1 - its rows keep their mark"


def _inventory_group(db, monkeypatch, fail_on_write=None):
    """The inventory's own group through the chain's seat - its log writes counted, its page lines kept."""
    from chain import keyset_scan  # noqa: F401 - the page size the caller set
    from maps import alignment_batch_counts

    writes, lines, real = [], [], crud.apply_batch_updates

    def counting(session, table, batch, *a, **k):
        if table == LOG:
            writes.append(len(batch.updates))
            if fail_on_write and len(writes) == fail_on_write:
                raise RuntimeError("the write of page %d failed" % fail_on_write)
        return real(session, table, batch, *a, **k)

    monkeypatch.setattr(crud, "apply_batch_updates", counting)
    monkeypatch.setattr(alignment_batch_counts.heartbeat, "progress", lines.append)
    events = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.table_name == INV,
                                                     models.DatabaseOutbox.processed_chain.is_(False)).all())
    assert events, "CANARY: the inventory's event waits"
    with alignment_batch_counts.counting_group():
        ok, _error, _ = worker._process_chain_transaction_group_sync("tx-fold", events, db, [dict(r) for r in RULES])
    monkeypatch.setattr(crud, "apply_batch_updates", real)
    if not ok:
        db.rollback()
    return ok, writes, [line for line in lines if line.startswith("mapper · fu_by_unit")]


def _logs_then_inventory(db):
    _write(db, LOG, [r for job, wafer, _t in JOBS for r in _logs(job, wafer)])
    _drain(db)
    _write(db, INV, [{"dt_job": j, "dt_job_id": j, "core_wafer": w, "wafer_out_time": t} for j, w, t in JOBS])


def test_the_marks_are_written_a_page_at_a_time_and_end_as_one_write_would(db, monkeypatch):
    """총괄 634c06fc3 (소유자 「배치로」 · 「쓰는 진척률이라도 보이면」): nine marks in pages of two - five writes, each
    committed before the next page is asked, and the same marks; every page says its line, the first too."""
    from chain import keyset_scan

    monkeypatch.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", 2)
    _logs_then_inventory(db)
    ok, writes, lines = _inventory_group(db, monkeypatch)
    assert ok and writes == [2, 2, 2, 2, 1], writes
    assert _marks(db) == SEEDED
    assert lines == ["mapper · fu_by_unit -> fu_log · page %d/5 · %d / 9 rows" % (k, n)
                     for k, n in ((1, 2), (2, 4), (3, 6), (4, 8), (5, 9))], lines


def test_a_stop_between_pages_keeps_the_pages_written_and_a_rerun_ends_as_one_write_would(db, monkeypatch):
    """A page that fails stops the group and its pages go with it - one commit (총괄 09f58844f); the re-run hands
    every losing row again (총괄 406d7c102 - one left out is a mark withdrawn) and ends where one write ends."""
    from chain import keyset_scan

    monkeypatch.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", 2)
    _logs_then_inventory(db)
    ok, writes, _lines = _inventory_group(db, monkeypatch, fail_on_write=3)
    assert not ok and writes == [2, 2, 2]
    rows = db.query(models.DYNAMIC_TABLES[LOG]).filter(models.DYNAMIC_TABLES[LOG].fold_mark.isnot(None)).count()
    assert rows == 0, "pages one and two went with the group"
    ok, writes, lines = _inventory_group(db, monkeypatch)
    assert ok and writes == [2, 2, 2, 2, 1], "every losing row handed again"
    assert lines[0] == "mapper · fu_by_unit -> fu_log · page 1/5 · 2 / 9 rows", lines
    assert _marks(db) == SEEDED


def test_a_page_with_no_total_is_said_without_one():
    assert worker._page_said("r", "t", 2, None, 5, None, 7) == "r -> t · page 2 · 5 rows"


def test_the_queue_reads_each_pages_line_while_that_page_is_written(db, monkeypatch):
    """총괄 59f2ab3f4 ①: on the real process the write stage replaced the page line on every page (157 running samples,
    0 page lines) while the cell above counted the progress call. This reads what a queue line reads - the chain's
    beat, written during each page's write, through the running seat - with the group claimed as the loop claims it."""
    import threading

    from chain import keyset_scan
    from maps import alignment_batch_counts
    from runtime import running
    from utils import heartbeat

    monkeypatch.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", 2)
    _logs_then_inventory(db)
    seen, real = [], crud.apply_batch_updates

    def reading(session, table, batch, *a, **k):
        if table == LOG:
            # from another thread, as the loop beats for its group - a beat on the claim's thread is its progress
            beater = threading.Thread(target=heartbeat.beat, args=(worker.GROUP_BEAT,), kwargs={"force": True})
            beater.start()
            beater.join()
            seen.append(sorted({facts["stage"] for facts in running.chain_lines_running().values()}))
        return real(session, table, batch, *a, **k)

    monkeypatch.setattr(crud, "apply_batch_updates", reading)
    events = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.table_name == INV,
                                                     models.DatabaseOutbox.processed_chain.is_(False)).all())
    token = worker._GROUP_LINE_KEYS.set(("tx-fold",))
    try:
        with alignment_batch_counts.counting_group():
            ok, _error, _ = worker._claimed_group_sync("tx-fold", events, db, [dict(r) for r in RULES])
    finally:
        worker._GROUP_LINE_KEYS.reset(token)
    assert ok
    assert seen == [["write:fu_log · fu_by_unit -> fu_log · page %d/5 · %d / 9 rows" % (k, n)]
                    for k, n in ((1, 2), (2, 4), (3, 6), (4, 8), (5, 9))], seen


def test_the_winners_log_rows_are_not_read(db):
    """총괄 3ec26c632 ① (소유자 「인벤토리 1,000 · 매칭 로그 수십만 행」): the log read names the losing units' keys only -
    a winner's rows are never written, and reading them was most of the work."""
    from sqlalchemy import event

    _seed(db)
    asked = []

    def seen(conn, cursor, statement, parameters, context, executemany):
        if ("FROM %s" % LOG) in statement:
            asked.extend(parameters)

    event.listen(db.get_bind(), "before_cursor_execute", seen)
    try:
        rows = db.query(models.DYNAMIC_TABLES[INV]).all()
        fold_unit.fold_by_unit(db, [{"row_id": r.row_id, "data": {}} for r in rows], dict(RULES[0]))
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", seen)
    losing, winning = {"AUTO_J5", "MAN_J3", "MAN_J7"}, {"AUTO_J1", "AUTO_J2", "AUTO_J4", "MAN_J6"}
    assert losing <= set(asked), "CANARY: the read names the losing jobs"
    assert not winning & set(asked), sorted(winning & set(asked))


def test_a_new_log_row_of_a_losing_job_is_marked(db):
    _seed(db)
    _write(db, LOG, [{"record_id": "AUTO_J5-9", "dt_job_id": "AUTO_J5", "core_wafer": "CW1"}])
    _drain(db)
    assert _marks(db) == SEEDED


def test_a_later_auto_job_takes_the_wafer_from_the_manual_ones(db):
    _seed(db)
    _write(db, LOG, _logs("AUTO_J8", "CW4"))
    _write(db, INV, [{"dt_job": "AUTO_J8", "dt_job_id": "AUTO_J8", "core_wafer": "CW4",
                      "wafer_out_time": "2026-10-05 09:00:00"}])
    _drain(db)
    assert _marks(db) == dict(SEEDED, MAN_J6={"folded into AUTO_J8"}, MAN_J7={"folded into AUTO_J8"},
                              AUTO_J8={""})


def test_a_unit_that_now_wins_keeps_its_old_mark_until_withdrawn(db):
    """총괄 10-11: the winner's rows are not written, so MAN_J7 - now earlier than MAN_J6 - keeps «folded into MAN_J6»
    until the mark is withdrawn (RUN.md: withdraw the log table's chain_ingestion on fold_mark, then replay)."""
    _seed(db)
    _write(db, INV, [{"dt_job": "MAN_J6", "wafer_out_time": "2026-10-04 11:00:00"}], source="user")
    _drain(db)
    assert _marks(db) == dict(SEEDED, MAN_J6={"folded into MAN_J7"}, MAN_J7={"folded into MAN_J6"})
