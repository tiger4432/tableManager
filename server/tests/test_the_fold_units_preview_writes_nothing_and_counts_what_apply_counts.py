"""fold-units' preview is read-only (lead 11-12, after the R2 preview ruling: «a preview must not contend with live
writes; the judgement is read-only, and only apply writes»). On one seed, `replay.fold_units` dry run then apply:
every count of the answer the same, and the dry run issues no write statement (INSERT / UPDATE / DELETE / REPLACE,
sqlite's BEGIN IMMEDIATE, a FOR UPDATE) - the canary: apply issues some. The seed fills every bucket: marked so
already, to mark, a person's layer above, a pin on another source, a pin whose source has no line, a file layer that
shows the mark already (left out - neither bucket), a unit that now wins (old marks withdrawn). The gated case: the
log table versioned, every mark refused by the gate in both."""
import pytest
from sqlalchemy import event

from chain import replay, rule_run
from database import crud, models, schemas
from mappers import fold_unit
from support import line_tables

INV, LOG, MARK = "fpv_inv", "fpv_log", "fold_mark"
PARAMS = {"unit_table": INV, "group": "core_wafer", "unit": "dt_job_id", "order": "wafer_out_time",
          "prefer_column": "dt_job_id", "prefer_text": "AUTO", "mark_column": MARK,
          "match": [{"left": "dt_job_id", "right": "dt_job_id"}, {"left": "core_wafer", "right": "core_wafer"}]}
RULE = {"name": "fpv_by_unit", "trigger_table": INV, "target_table": LOG, "mapper": fold_unit.NAME,
        "is_batch": True, "allow_chain_trigger": True, "params": PARAMS}
JOBS = [("AUTO_J1", "CW1", "2026-10-01 11:00:00"), ("AUTO_J5", "CW1", "2026-10-02 09:00:00"),
        ("AUTO_J2", "CW2", "2026-10-01 12:00:00"),
        ("MAN_J3", "CW3", "2026-10-03 11:00:00"), ("AUTO_J4", "CW3", "2026-10-03 12:00:00"),
        ("MAN_J6", "CW4", "2026-10-04 11:00:00"), ("MAN_J7", "CW4", "2026-10-04 10:00:00")]
#: the chain's marks from before, named as the fold names its own (its rule and group) - AUTO_J5-0 marked so already,
#: MAN_J7 lost and now wins (its marks go)
OLD_MARKS = [("AUTO_J5-0", "AUTO_J5", "CW1", "folded into AUTO_J1"),
             ("MAN_J7-0", "MAN_J7", "CW4", "folded into MAN_J6"), ("MAN_J7-1", "MAN_J7", "CW4", "folded into MAN_J6")]
#: a file's layer on the mark: AUTO_J5-1 shows the mark already (no line), MAN_J3-1 / MAN_J3-2 the pins' cells
FILE_MARKS = [("AUTO_J5-1", "folded into AUTO_J1"), ("MAN_J3-1", "kept by file")]
BY_HAND = ("MAN_J3-0", "kept by hand")
WRITES = ("INSERT", "UPDATE", "DELETE", "REPLACE")
COUNTS = ("units", "groups", "units_losing", "rows_proposed", "rows_to_mark", "rows_higher_layer",
          "rows_already_marked", "rows_gone", "rows_refused", "version_gate", "marks_withdrawn", "pages")


def _tables(gated):
    log = {"business_key": "record_id", "column_types": {c: "string" for c in ("record_id", "dt_job_id", "core_wafer",
                                                                               MARK)}}
    if gated:
        log["column_types"]["rev"] = "number"
        log["version_column"] = "rev"
    return {INV: {"business_key": "dt_job",
                  "column_types": {c: "string" for c in ("dt_job", "dt_job_id", "core_wafer", "wafer_out_time")}},
            LOG: log}


@pytest.fixture(params=[False, True], ids=["plain", "version-gated"])
def db(db_session, monkeypatch, request):
    tables = _tables(request.param)
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    fold_unit._register()
    for table in tables:
        line_tables.build(db_session.get_bind(), table)
    monkeypatch.setattr(replay, "load_rules", lambda: [dict(RULE)])
    monkeypatch.setattr(replay, "FOLD_UNITS_PAGE", 4)                 # several pages
    _seed(db_session, request.param)
    yield db_session
    db_session.rollback()
    from conftest import retire_dynamic_model
    for table in tables:
        line_tables.drop(db_session.get_bind(), table)
        models.DYNAMIC_TABLES[table].__table__.drop(bind=db_session.get_bind(), checkfirst=True)   # «rev» or not
        retire_dynamic_model(table)
        crud.TABLE_CONFIG.pop(table, None)


def _write(db, table, items):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=items, silent=True))
    db.commit()


def _seed(db, gated):
    _write(db, INV, [schemas.GeneralUpdateItem(business_key_val=job, updates={"dt_job": job, "dt_job_id": job,
                     "core_wafer": wafer, "wafer_out_time": at}, source_name="seed.csv", updated_by="seed")
                     for job, wafer, at in JOBS])
    _write(db, LOG, [schemas.GeneralUpdateItem(business_key_val="%s-%d" % (job, i), updates=dict(
        {"record_id": "%s-%d" % (job, i), "dt_job_id": job, "core_wafer": wafer}, **({"rev": 1} if gated else {})),
        source_name="seed.csv", updated_by="seed") for job, wafer, _at in JOBS for i in range(3)])
    units = {r.dt_job: r.row_id for r in db.query(models.DYNAMIC_TABLES[INV])}
    rows = {r.record_id: r.row_id for r in db.query(models.DYNAMIC_TABLES[LOG])}
    rev = {"rev": 1} if gated else {}
    # named as the page names the rule's answer (replay._fold_units_page: the owner read off the answer's item)
    old = [{"row_id": rows[rec], "origin_row_id": units[job], "owner_key": group, "updates": {MARK: said, **rev},
            "source_name": crud.CHAIN_SOURCE, "updated_by": RULE["name"]} for rec, job, group, said in OLD_MARKS]
    _write(db, LOG, [schemas.GeneralUpdateItem(**dict(item, source_name=rule_run.layer_of_a_rules_write(
        item["source_name"], item["origin_row_id"], rule_run.owner_of(item)))) for item in old]
           + [schemas.GeneralUpdateItem(row_id=rows[rec], updates={MARK: said, **rev}, source_name="file.csv",
                                        updated_by="file") for rec, said in FILE_MARKS]
           + [schemas.GeneralUpdateItem(row_id=rows[BY_HAND[0]], updates={MARK: BY_HAND[1]}, source_name="user",
                                        updated_by="op")])
    crud.set_cell_manual_priority_batch(db, LOG, [{"row_id": rows["MAN_J3-1"], "column_name": MARK}], "file.csv")
    # a pin whose source has no line on the cell - t keeps its value (lines.merge); the door cannot make one
    db.add(models.CellOverwrite(table_name=LOG, row_id=rows["MAN_J3-2"], column_name=MARK, is_overwrite=False,
                                updated_by="op", manual_priority_source="gone.csv"))
    db.query(models.DatabaseOutbox).update({"processed_chain": True})
    db.commit()


def _shown(db):
    db.expire_all()
    return sorted((r.record_id, getattr(r, MARK)) for r in db.query(models.DYNAMIC_TABLES[LOG]))


def _run(db, apply):
    said = []

    def count(conn, cursor, statement, parameters, context, executemany):
        words = statement.lstrip().upper()
        if words.split(None, 1)[0] in WRITES or words.startswith("BEGIN IMMEDIATE") or " FOR UPDATE" in words:
            said.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        stats = replay.fold_units(db, RULE["name"], apply=apply, log=lambda m: None)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return stats, said


def test_the_fold_units_preview_writes_nothing_and_counts_what_apply_counts(db):
    gated = bool(crud.TABLE_CONFIG[LOG].get("version_column"))
    seeded = _shown(db)

    preview, preview_writes = _run(db, apply=False)
    assert _shown(db) == seeded
    applied, apply_writes = _run(db, apply=True)

    assert preview_writes == [], preview_writes[:5]
    assert len(apply_writes) > 0, "canary: the counter sees apply's writes"
    assert {k: preview[k] for k in COUNTS} == {k: applied[k] for k in COUNTS}
    # the buckets the comparison stands on - equal zeros would say nothing
    assert applied["rows_proposed"] == 9 and applied["marks_withdrawn"] == 2, applied
    if gated:
        assert applied["version_gate"] and applied["rows_to_mark"] == 0, applied
    else:
        assert (applied["rows_already_marked"], applied["rows_to_mark"], applied["rows_higher_layer"]) == (1, 7, 3), \
            applied
        assert applied["rows_marked"] == applied["rows_to_mark"] and preview["rows_marked"] == 0


def test_a_page_counts_a_gone_row_alike_in_its_preview_and_its_run(db):
    """A row the answer names that is gone (the full run above has none): one page, preview then run."""
    rows = {r.record_id: r.row_id for r in db.query(models.DYNAMIC_TABLES[LOG])}
    proposed = lambda: [{"row_id": row_id, "updates": {MARK: "folded into MAN_J7"}, "owner_key": "CW4",  # noqa: E731
                         "source_name": crud.CHAIN_SOURCE, "updated_by": RULE["name"]}
                        for row_id in (rows["MAN_J6-0"], rows["MAN_J6-1"], "gone-row")]
    model = models.DYNAMIC_TABLES[LOG]

    preview = replay._fold_units_page(db, LOG, model, MARK, proposed(), "tx-fpv", False)[0]
    applied = replay._fold_units_page(db, LOG, model, MARK, proposed(), "tx-fpv", True)[0]

    assert applied["rows_gone"] == 1, applied
    assert {k: v for k, v in preview.items() if k != "rows_marked"} == \
        {k: v for k, v in applied.items() if k != "rows_marked"}
