# -*- coding: utf-8 -*-
"""총괄 10-11 (소유자 「접는 거 일단 스크립트로 빨리 하는 거 줘, 맵퍼 말고」) — `fold-units` leaves what the chain leaves.

Two copies of one seed in the scratch schema. A: the unit rule replayed and drained through the worker's group
step (setup ⑤ - the write door, then the edited unit rows' withdrawal). B: `replay.fold_units(apply=True)`.
Compared with ids and times left out: every log row's mark, every layer and overwrite on the mark column, the
history lines. The seed holds each case the script has to get right: a log row marked so already, a hand-written
layer above the chain's, a unit that lost and now wins (its old marks go), a log row whose job moved (its old
mark goes), a winner with no out time, AUTO before MANUAL."""
import json
import os
import sys

import pytest
from sqlalchemy import MetaData, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import keyset_scan, replay, rule_run                     # noqa: E402
from conftest import PG_TEST_SCHEMA, _declared_as_test_database, _resolve_pg_test_url   # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from mappers import fold_unit                                       # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

pytestmark = pytest.mark.pg

INV, LOG, MARK = "pgqa_fu_inv", "pgqa_fu_log", "fold_mark"
TABLES = {INV: {"business_key": "dt_job", "composite_key_source": ["dt_job"],
                "column_types": {c: "string" for c in ("dt_job", "dt_job_id", "core_wafer", "wafer_out_time")}},
          LOG: {"business_key": "record_id", "composite_key_source": ["record_id"],
                "column_types": {c: "string" for c in ("record_id", "dt_job_id", "core_wafer", MARK)}}}
PARAMS = {"unit_table": INV, "group": "core_wafer", "unit": "dt_job_id", "order": "wafer_out_time",
          "prefer_column": "dt_job_id", "prefer_text": "AUTO", "mark_column": MARK,
          "match": [{"left": "dt_job_id", "right": "dt_job_id"}, {"left": "core_wafer", "right": "core_wafer"}]}
RULES = [{"name": "pgqa_fu_by_unit", "trigger_table": INV, "target_table": LOG, "mapper": fold_unit.NAME,
          "is_batch": True, "allow_chain_trigger": True, "params": PARAMS},
         {"name": "pgqa_fu_by_log", "trigger_table": LOG, "target_table": LOG, "mapper": fold_unit.NAME,
          "is_batch": True, "trigger_columns": ["dt_job_id", "core_wafer"], "params": PARAMS}]
JOBS = [("AUTO_J1", "CW1", "2026-10-01 11:00:00"), ("AUTO_J5", "CW1", "2026-10-02 09:00:00"),
        ("AUTO_J2", "CW2", "2026-10-01 12:00:00"),
        ("MAN_J3", "CW3", "2026-10-03 11:00:00"), ("AUTO_J4", "CW3", "2026-10-03 12:00:00"),
        ("MAN_J6", "CW4", "2026-10-04 11:00:00"), ("MAN_J7", "CW4", "2026-10-04 10:00:00"),
        ("AUTO_J9", "CW5", None), ("MAN_J10", "CW5", "2026-10-05 09:00:00")]
#: (log row, origin job, what its chain layer said before) - written through the door before the fold
OLD_MARKS = [("AUTO_J5-0", "AUTO_J5", "folded into AUTO_J1"),                   # marked so already
             ("MAN_J7-0", "MAN_J7", "folded into MAN_J6"), ("MAN_J7-1", "MAN_J7", "folded into MAN_J6"),
             ("MAN_J7-2", "MAN_J7", "folded into MAN_J6"),                       # MAN_J7 lost, now wins
             ("MOVED-0", "MAN_J3", "folded into AUTO_J4")]                       # was MAN_J3's row, now AUTO_J4's
BY_HAND = ("MAN_J3-0", "kept by hand")
FOLDED = {**{"%s-%d" % (job, i): "" for job, _w, _t in JOBS for i in range(3)},
          **{"AUTO_J5-%d" % i: "folded into AUTO_J1" for i in range(3)},
          **{"MAN_J3-%d" % i: "folded into AUTO_J4" for i in range(3)}, BY_HAND[0]: BY_HAND[1],
          **{"MAN_J6-%d" % i: "folded into MAN_J7" for i in range(3)},
          **{"MAN_J10-%d" % i: "folded into AUTO_J9" for i in range(3)}, "MOVED-0": ""}
PARTS = ("shown", "layers", "overwrites", "history")


def _write(db, table, items):
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=items))
    db.commit()


def _seed(db):
    _write(db, INV, [schemas.GeneralUpdateItem(updates={k: v for k, v in (("dt_job", job), ("dt_job_id", job),
                     ("core_wafer", wafer), ("wafer_out_time", t)) if v}, source_name="seed.csv", updated_by="seed")
                     for job, wafer, t in JOBS])
    _write(db, LOG, [schemas.GeneralUpdateItem(updates={"record_id": "%s-%d" % (job, i), "dt_job_id": job,
                     "core_wafer": wafer}, source_name="seed.csv", updated_by="seed")
                     for job, wafer, _t in JOBS for i in range(3)]
           + [schemas.GeneralUpdateItem(updates={"record_id": "MOVED-0", "dt_job_id": "AUTO_J4", "core_wafer": "CW3"},
                                        source_name="seed.csv", updated_by="seed")])
    units = {r.dt_job: r.row_id for r in db.query(models.DYNAMIC_TABLES[INV])}
    rows = {r.record_id: r.row_id for r in db.query(models.DYNAMIC_TABLES[LOG])}
    # the marks the chain wrote before: its layer, signed by the rule that wrote them (rule_run.signed)
    _write(db, LOG, [schemas.GeneralUpdateItem(row_id=rows[rec], origin_row_id=units[job], updates={MARK: said},
                                               source_name=rule_run.layer_of_a_rules_write(None, units[job]),
                                               updated_by=RULES[0]["name"])
                     for rec, job, said in OLD_MARKS]
           + [schemas.GeneralUpdateItem(row_id=rows[BY_HAND[0]], updates={MARK: BY_HAND[1]}, source_name="user",
                                        updated_by="op")])
    db.query(models.DatabaseOutbox).update({"processed_chain": True})     # the seed feeds no rule
    db.commit()
    return db.query(models.AuditLog.id).order_by(models.AuditLog.id.desc()).limit(1).scalar() or 0


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


def _state(db, after_id):
    """What a copy holds, every row id put back to its job or record and ids · times · transaction left out."""
    db.expire_all()
    names = {r.row_id: r.dt_job for r in db.query(models.DYNAMIC_TABLES[INV])}
    names.update({r.row_id: r.record_id for r in db.query(models.DYNAMIC_TABLES[LOG])})

    def said(value):
        text_ = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
        for row_id, name in names.items():
            text_ = text_.replace(row_id, name)
        return text_

    cs, co, al = models.CellSource, models.CellOverwrite, models.AuditLog
    return {
        "shown": sorted((names[r.row_id], r.business_key_val, r.fold_mark)
                        for r in db.query(models.DYNAMIC_TABLES[LOG])),
        "layers": sorted((names[c.row_id], said(c.source_name), said(c.value), names.get(c.origin_row_id),
                          c.updated_by) for c in db.query(cs).filter(cs.table_name == LOG, cs.column_name == MARK)),
        "overwrites": sorted((names[o.row_id], o.is_overwrite, o.updated_by, o.manual_priority_source)
                             for o in db.query(co).filter(co.table_name == LOG, co.column_name == MARK)),
        "history": sorted((names.get(a.row_id), a.column_name, said(a.old_value), said(a.new_value),
                           said(a.source_name), said(a.updated_by), a.business_key)
                          for a in db.query(al).filter(al.table_name == LOG, al.id > after_id)),
    }


def _marks(state):
    return {name: mark or "" for name, _key, mark in state["shown"]}


def _public(engine):
    """Rows about these tables in `public` - must not move. None where public has no such table."""
    out = {}
    with engine.connect() as conn:
        for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": "public.%s" % table}).scalar():
                out[table] = conn.execute(text("SELECT count(*) FROM public.%s WHERE table_name IN (:a, :b)" % table),
                                          {"a": INV, "b": LOG}).scalar()
        out["tables"] = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = "
                                          "'public' AND table_name IN (:a, :b)"), {"a": INV, "b": LOG}).scalar()
    return out


@pytest.fixture(scope="module")
def copies(pg_engine):
    from sqlalchemy.orm import sessionmaker

    url, _ = _resolve_pg_test_url()
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    fold_unit._register()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    made = [models.DYNAMIC_TABLES[t].__table__.to_metadata(scratch, schema=None) for t in TABLES]
    emptied = ", ".join('"%s"."%s"' % (PG_TEST_SCHEMA, t) for t in
                        ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox", *TABLES))
    Session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    out = {"public_before": _public(pg_engine)}
    with _declared_as_test_database(url), pytest.MonkeyPatch.context() as mp:
        mp.setattr(replay, "load_rules", lambda: [dict(r) for r in RULES])
        # the 12 rows the fold names come in mapper pages of 5 (both copies) and are written in pages of 4
        mp.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", 5)
        mp.setattr(replay, "FOLD_UNITS_PAGE", 4)
        real_run, out["answers"] = rule_run.run_rule, []

        def run_rule(*args, **kwargs):
            answer = real_run(*args, **kwargs)
            out["answers"].append((len(answer["updates"]), [m["rows_total"] for m in answer["next_page"]]))
            return answer
        mp.setattr(rule_run, "run_rule", run_rule)
        scratch.create_all(pg_engine)
        try:
            db = Session()
            out["schema"] = db.execute(text("SELECT current_schema()")).scalar()
            seeded = _seed(db)
            out["seed"] = _state(db, seeded)
            replay.replay_rule(db, dict(RULES[0]), apply=True, log=lambda *a, **k: None)     # A: setup ⑤
            _drain(db)
            out["A"] = _state(db, seeded)
            replay.withdraw_source(db, LOG, "chain_ingestion", columns=[MARK], apply=True, log=lambda *a: None)
            out["A_reset"] = _state(db, seeded)
            db.close()
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            db = Session()
            seeded = _seed(db)
            lines = out["B_dry_lines"] = []

            def hook(_processed, _total):
                return False
            hook.step = lambda name, page, pages, rows: lines.append((name, page, rows))
            out["B_dry"] = replay.fold_units(db, RULES[0]["name"], log=lambda m: None, checkpoint=hook)
            out["B_after_dry"] = _state(db, seeded)
            out["B_stats"] = replay.fold_units(db, RULES[0]["name"], apply=True, log=lambda m: None)   # B
            out["B"] = _state(db, seeded)
            out["B_again"] = replay.fold_units(db, RULES[0]["name"], apply=True, log=lambda m: None)
            out["B_after_again"] = _state(db, seeded)
            replay.withdraw_source(db, LOG, "chain_ingestion", columns=[MARK], apply=True, log=lambda *a: None)
            out["B_reset"] = _state(db, seeded)
            db.close()
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            db = Session()
            seeded = _seed(db)
            with pytest.MonkeyPatch.context() as door_only:                      # every cell through the door
                door_only.setattr(replay, "_fold_units_forced", lambda *a, **k: None)
                out["B_door_stats"] = replay.fold_units(db, RULES[0]["name"], apply=True, log=lambda m: None)
            out["B_door"] = _state(db, seeded)
            db.close()
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            scratch.drop_all(pg_engine)
            for t in TABLES:
                crud.TABLE_CONFIG.pop(t, None)
    out["public_after"] = _public(pg_engine)
    return out


def test_the_writes_land_in_the_scratch_schema_and_public_does_not_move(copies):
    assert copies["schema"] == PG_TEST_SCHEMA
    assert copies["public_after"] == copies["public_before"], (copies["public_before"], copies["public_after"])


def test_the_chain_copy_folds_the_seed(copies):
    """The reference itself, so a comparison of two empty answers cannot pass."""
    assert _marks(copies["seed"])["MAN_J7-0"] == "folded into MAN_J6", "CANARY: the old marks are there"
    assert _marks(copies["A"]) == FOLDED


@pytest.mark.parametrize("part", PARTS)
def test_fold_units_leaves_what_the_chain_leaves(copies, part):
    assert copies["A"][part], "CANARY: the chain copy holds %s" % part
    assert copies["B"][part] == copies["A"][part]


def test_the_higher_layer_keeps_its_value_and_takes_the_chains_under_it(copies):
    for copy in ("A", "B"):
        assert _marks(copies[copy])[BY_HAND[0]] == BY_HAND[1], copy
        assert ("MAN_J3-0", "chain_ingestion (MAN_J3)", "folded into AUTO_J4", "MAN_J3", RULES[0]["name"]) in \
            copies[copy]["layers"], copy
    assert copies["B_stats"]["rows_higher_layer"] == 1


def test_the_dry_run_counts_what_the_run_does_and_writes_nothing(copies):
    said = ("units", "groups", "units_losing", "rows_proposed", "rows_to_mark", "rows_already_marked",
            "rows_higher_layer", "marks_withdrawn")
    assert {k: copies["B_dry"][k] for k in said} == {k: copies["B_stats"][k] for k in said}
    assert (copies["B_dry"]["units"], copies["B_dry"]["groups"], copies["B_dry"]["units_losing"],
            copies["B_dry"]["marks_withdrawn"]) == (9, 5, 4, 4)
    assert copies["B_after_dry"] == copies["seed"]


def test_a_rerun_writes_nothing(copies):
    again = copies["B_again"]
    assert copies["B_stats"]["rows_marked"] == 11, "CANARY: the first run wrote"
    assert copies["answers"][0] == (5, [12]), "CANARY: the mapper answers in pages (A, the chain's copy)"
    # fold-units asks the rule seat whole groups at a time - 1, then 2, then 2 of the 5 - in each of its 4 runs, so its
    # first page does not wait on every group's answer (총괄 2ea5ee2a7)
    assert len(copies["answers"]) == 1 + 4 * 3, copies["answers"]
    assert (copies["B_stats"]["rows_proposed"], copies["B_stats"]["pages"] >= 3) == (12, True), "every mapper page followed"  # pages of at most 5, from one row
    assert (again["rows_marked"], again["marks_withdrawn"], again["rows_already_marked"]) == (0, 0, 12)
    assert copies["B_after_again"] == copies["B"]


def test_the_reset_line_clears_both_alike(copies):
    assert any(source.startswith("chain_ingestion") for _r, source, *_ in copies["A"]["layers"]), "CANARY"
    assert copies["B_reset"] == copies["A_reset"]
    assert [one for one in copies["B_reset"]["layers"] if one[1].startswith("chain_ingestion")] == []


def test_the_decided_cells_take_the_doors_answer(copies):
    """`_fold_units_forced` off - every cell judged by `crud.apply_row_update_internal` - leaves the same."""
    assert copies["B_door"] == copies["B"]
    assert {k: copies["B_door_stats"][k] for k in ("rows_to_mark", "rows_already_marked", "rows_higher_layer")} ==         {k: copies["B_stats"][k] for k in ("rows_to_mark", "rows_already_marked", "rows_higher_layer")}


def test_the_first_line_comes_once_one_group_is_asked(copies):
    """총괄 10-12 (응용: «fold_units 가 그룹을 한 번에 다 물음» 변이가 살아남음): the first line is the rule seat's
    answer for the first group alone - not the whole answer before anything is said."""
    first = min(w for _job, w, _t in JOBS if w)
    assert copies["B_dry_lines"][0] == ("rule", 1, sum(1 for _job, w, _t in JOBS if w == first)), (
        copies["B_dry_lines"][:3])
