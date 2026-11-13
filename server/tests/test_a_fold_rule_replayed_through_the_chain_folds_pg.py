# -*- coding: utf-8 -*-
"""A fold rule replayed through the chain folds: the unit rule replayed and drained through the worker's group step
(setup ⑤ - the write door, then the edited unit rows' withdrawal). Owner 11-12: folds run through the chain's replay -
`fold-units` (10-11, 「접는 거 일단 스크립트로 빨리 하는 거 줘」) is retired; this file compared it with this copy, and
PINNED is what the two left alike on main 0062fc8b7 (ids and times left out); on the overhaul its
history is the LOG table's lines after the seed, measured on ovh-trial (B 11-13), the rest unchanged. The seed holds each case a fold has to
get right: a log row marked so already, a hand-written layer above the chain's, a unit that lost and now wins (its old
marks go), a log row whose job moved (its old mark goes), a winner with no out time, AUTO before MANUAL."""
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
from database import crud, lines, models, schemas                   # noqa: E402
from tests.support import line_tables                              # noqa: E402
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
#: what the chain's copy and fold-units both left on main 0062fc8b7 (A == B, 13 passed) - b74_fill_pins.py
PINNED = {'history': [('AUTO_J5-0', 'fold_mark', 'folded into AUTO_J1', 'chain_ingestion (pgqa_fu_by_unit CW1)', 'pgqa_fu_by_unit'),
                       ('AUTO_J5-0', 'fold_mark', None, 'chain_ingestion (AUTO_J5)', 'chain_replay_withdraw'),
                       ('AUTO_J5-1', 'fold_mark', 'folded into AUTO_J1', 'chain_ingestion (pgqa_fu_by_unit CW1)', 'pgqa_fu_by_unit'),
                       ('AUTO_J5-2', 'fold_mark', 'folded into AUTO_J1', 'chain_ingestion (pgqa_fu_by_unit CW1)', 'pgqa_fu_by_unit'),
                       ('MAN_J10-0', 'fold_mark', 'folded into AUTO_J9', 'chain_ingestion (pgqa_fu_by_unit CW5)', 'pgqa_fu_by_unit'),
                       ('MAN_J10-1', 'fold_mark', 'folded into AUTO_J9', 'chain_ingestion (pgqa_fu_by_unit CW5)', 'pgqa_fu_by_unit'),
                       ('MAN_J10-2', 'fold_mark', 'folded into AUTO_J9', 'chain_ingestion (pgqa_fu_by_unit CW5)', 'pgqa_fu_by_unit'),
                       ('MAN_J3-0', 'fold_mark', 'folded into AUTO_J4', 'chain_ingestion (pgqa_fu_by_unit CW3)', 'pgqa_fu_by_unit'),
                       ('MAN_J3-1', 'fold_mark', 'folded into AUTO_J4', 'chain_ingestion (pgqa_fu_by_unit CW3)', 'pgqa_fu_by_unit'),
                       ('MAN_J3-2', 'fold_mark', 'folded into AUTO_J4', 'chain_ingestion (pgqa_fu_by_unit CW3)', 'pgqa_fu_by_unit'),
                       ('MAN_J6-0', 'fold_mark', 'folded into MAN_J7', 'chain_ingestion (pgqa_fu_by_unit CW4)', 'pgqa_fu_by_unit'),
                       ('MAN_J6-1', 'fold_mark', 'folded into MAN_J7', 'chain_ingestion (pgqa_fu_by_unit CW4)', 'pgqa_fu_by_unit'),
                       ('MAN_J6-2', 'fold_mark', 'folded into MAN_J7', 'chain_ingestion (pgqa_fu_by_unit CW4)', 'pgqa_fu_by_unit'),
                       ('MAN_J7-0', 'fold_mark', None, 'chain_ingestion (MAN_J7)', 'chain_replay_withdraw'),
                       ('MAN_J7-1', 'fold_mark', None, 'chain_ingestion (MAN_J7)', 'chain_replay_withdraw'),
                       ('MAN_J7-2', 'fold_mark', None, 'chain_ingestion (MAN_J7)', 'chain_replay_withdraw'),
                       ('MOVED-0', 'fold_mark', None, 'chain_ingestion (MAN_J3)', 'chain_replay_withdraw')],
          'layers': [('AUTO_J5-0',
                      'chain_ingestion (pgqa_fu_by_unit CW1)',
                      'folded into AUTO_J1',
                      'AUTO_J5',
                      'pgqa_fu_by_unit'),
                     ('AUTO_J5-1',
                      'chain_ingestion (pgqa_fu_by_unit CW1)',
                      'folded into AUTO_J1',
                      'AUTO_J5',
                      'pgqa_fu_by_unit'),
                     ('AUTO_J5-2',
                      'chain_ingestion (pgqa_fu_by_unit CW1)',
                      'folded into AUTO_J1',
                      'AUTO_J5',
                      'pgqa_fu_by_unit'),
                     ('MAN_J10-0',
                      'chain_ingestion (pgqa_fu_by_unit CW5)',
                      'folded into AUTO_J9',
                      'MAN_J10',
                      'pgqa_fu_by_unit'),
                     ('MAN_J10-1',
                      'chain_ingestion (pgqa_fu_by_unit CW5)',
                      'folded into AUTO_J9',
                      'MAN_J10',
                      'pgqa_fu_by_unit'),
                     ('MAN_J10-2',
                      'chain_ingestion (pgqa_fu_by_unit CW5)',
                      'folded into AUTO_J9',
                      'MAN_J10',
                      'pgqa_fu_by_unit'),
                     ('MAN_J3-0',
                      'chain_ingestion (pgqa_fu_by_unit CW3)',
                      'folded into AUTO_J4',
                      'MAN_J3',
                      'pgqa_fu_by_unit'),
                     ('MAN_J3-0', 'user', 'kept by hand', None, 'op'),
                     ('MAN_J3-1',
                      'chain_ingestion (pgqa_fu_by_unit CW3)',
                      'folded into AUTO_J4',
                      'MAN_J3',
                      'pgqa_fu_by_unit'),
                     ('MAN_J3-2',
                      'chain_ingestion (pgqa_fu_by_unit CW3)',
                      'folded into AUTO_J4',
                      'MAN_J3',
                      'pgqa_fu_by_unit'),
                     ('MAN_J6-0',
                      'chain_ingestion (pgqa_fu_by_unit CW4)',
                      'folded into MAN_J7',
                      'MAN_J6',
                      'pgqa_fu_by_unit'),
                     ('MAN_J6-1',
                      'chain_ingestion (pgqa_fu_by_unit CW4)',
                      'folded into MAN_J7',
                      'MAN_J6',
                      'pgqa_fu_by_unit'),
                     ('MAN_J6-2',
                      'chain_ingestion (pgqa_fu_by_unit CW4)',
                      'folded into MAN_J7',
                      'MAN_J6',
                      'pgqa_fu_by_unit')],
          'overwrites': [('MAN_J3-0', True, 'pgqa_fu_by_unit', None)],
          'shown': [('AUTO_J1-0', 'AUTO_J1-0', None),
                    ('AUTO_J1-1', 'AUTO_J1-1', None),
                    ('AUTO_J1-2', 'AUTO_J1-2', None),
                    ('AUTO_J2-0', 'AUTO_J2-0', None),
                    ('AUTO_J2-1', 'AUTO_J2-1', None),
                    ('AUTO_J2-2', 'AUTO_J2-2', None),
                    ('AUTO_J4-0', 'AUTO_J4-0', None),
                    ('AUTO_J4-1', 'AUTO_J4-1', None),
                    ('AUTO_J4-2', 'AUTO_J4-2', None),
                    ('AUTO_J5-0', 'AUTO_J5-0', 'folded into AUTO_J1'),
                    ('AUTO_J5-1', 'AUTO_J5-1', 'folded into AUTO_J1'),
                    ('AUTO_J5-2', 'AUTO_J5-2', 'folded into AUTO_J1'),
                    ('AUTO_J9-0', 'AUTO_J9-0', None),
                    ('AUTO_J9-1', 'AUTO_J9-1', None),
                    ('AUTO_J9-2', 'AUTO_J9-2', None),
                    ('MAN_J10-0', 'MAN_J10-0', 'folded into AUTO_J9'),
                    ('MAN_J10-1', 'MAN_J10-1', 'folded into AUTO_J9'),
                    ('MAN_J10-2', 'MAN_J10-2', 'folded into AUTO_J9'),
                    ('MAN_J3-0', 'MAN_J3-0', 'kept by hand'),
                    ('MAN_J3-1', 'MAN_J3-1', 'folded into AUTO_J4'),
                    ('MAN_J3-2', 'MAN_J3-2', 'folded into AUTO_J4'),
                    ('MAN_J6-0', 'MAN_J6-0', 'folded into MAN_J7'),
                    ('MAN_J6-1', 'MAN_J6-1', 'folded into MAN_J7'),
                    ('MAN_J6-2', 'MAN_J6-2', 'folded into MAN_J7'),
                    ('MAN_J7-0', 'MAN_J7-0', None),
                    ('MAN_J7-1', 'MAN_J7-1', None),
                    ('MAN_J7-2', 'MAN_J7-2', None),
                    ('MOVED-0', 'MOVED-0', None)]}


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
    return _last_line(db)


def _last_line(db):
    """The LOG table's newest line id - the history read after the seed starts past it."""
    return db.execute(text('SELECT max(line_id) FROM "%s"' % lines.lines_relation(LOG))).scalar() or 0


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

    co = models.CellOverwrite
    row_ids = sorted(names)
    layers = lines.layers(db, LOG, row_ids, columns=[MARK])
    by_bit = {bit: col for col, bit in lines.bit_map(db, LOG).items()}
    chunks = 1 + max(by_bit) // lines.BITS_PER_CHUNK
    written = lines.bit_columns("written", chunks)
    history = db.execute(text('SELECT row_id, source_name, written_by, %s, %s FROM "%s" WHERE line_id > :after' % (
        ", ".join(written), lines.value_column(MARK), lines.lines_relation(LOG))), {"after": after_id}).all()
    return {
        "shown": sorted((names[r.row_id], r.business_key_val, r.fold_mark)
                        for r in db.query(models.DYNAMIC_TABLES[LOG])),
        "layers": sorted(((names[row], said(source), said(one["value"]), names.get(one.get("origin_row_id")),
                          one["updated_by"])
                         for (row, _col), by_source in layers.items() for source, one in by_source.items()), key=repr),
        "overwrites": sorted((names[o.row_id], o.is_overwrite, o.updated_by, o.manual_priority_source)
                             for o in db.query(co).filter(co.table_name == LOG, co.column_name == MARK)),
        "history": sorted(((names.get(h[0]), ",".join(sorted(lines._columns_of(list(h[3:3 + chunks]), by_bit))),
                           said(h[-1]) if h[-1] is not None else None, said(h[1]), said(h[2]))
                          for h in history), key=repr),
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
        # the 12 rows the fold names come in mapper pages of 5
        mp.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", 5)
        real_run, out["answers"] = rule_run.run_rule, []

        def run_rule(*args, **kwargs):
            answer = real_run(*args, **kwargs)
            # rows written - what the page also covers (its groups, owner 11-06 step 2) is not one
            out["answers"].append((rule_run.rows_written(answer["updates"]), [m["rows_total"] for m in answer["next_page"]]))
            return answer
        mp.setattr(rule_run, "run_rule", run_rule)
        scratch.create_all(pg_engine)
        for table in TABLES:                # the overhaul's line tables (old-shape recipe, owner 11-11)
            line_tables.build(pg_engine, table)
        try:
            db = Session()
            out["schema"] = db.execute(text("SELECT current_schema()")).scalar()
            seeded = _seed(db)
            out["seed"] = _state(db, seeded)
            replay.replay_rule(db, dict(RULES[0]), apply=True, log=lambda *a, **k: None)     # setup ⑤
            _drain(db)
            out["A"] = _state(db, seeded)
            out["answers_first"] = len(out["answers"])
            replay.replay_rule(db, dict(RULES[0]), apply=True, log=lambda *a, **k: None)     # again
            _drain(db)
            out["A_again"] = _state(db, seeded)
            replay.withdraw_source(db, LOG, "chain_ingestion", columns=[MARK], apply=True, log=lambda *a: None)
            out["A_reset"] = _state(db, seeded)
            db.close()
        finally:
            db.close()                      # a failed run's session holds locks the TRUNCATE below would wait on
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            for table in TABLES:
                line_tables.drop(pg_engine, table)
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
def test_the_chain_leaves_what_the_two_copies_agreed_on(copies, part):
    assert copies["A"][part], "CANARY: the chain copy holds %s" % part
    assert copies["A"][part] == PINNED[part]


def test_a_unit_that_now_wins_takes_its_old_marks_back_and_a_moved_row_loses_its_own(copies):
    before, after = _marks(copies["seed"]), _marks(copies["A"])
    assert [before["MAN_J7-%d" % i] for i in range(3)] == ["folded into MAN_J6"] * 3, "CANARY: MAN_J7 lost before"
    assert [after["MAN_J7-%d" % i] for i in range(3)] == [""] * 3
    assert [after["MAN_J6-%d" % i] for i in range(3)] == ["folded into MAN_J7"] * 3
    assert (before["MOVED-0"], after["MOVED-0"]) == ("folded into AUTO_J4", "")


def test_the_higher_layer_keeps_its_value_and_takes_the_chains_under_it(copies):
    assert _marks(copies["A"])[BY_HAND[0]] == BY_HAND[1]
    # the rule's layer of the unit's group (owner 11-06 step 2 - `owner_key`, the fold's group)
    assert ("MAN_J3-0", crud.owned_layer_name(RULES[0]["name"], "CW3"), "folded into AUTO_J4", "MAN_J3",
            RULES[0]["name"]) in copies["A"]["layers"]


def test_the_rule_answers_in_pages_and_a_rerun_writes_nothing(copies):
    assert copies["answers"][0] == (5, [12]), "the mapper answers the 12 rows it names in pages of 5"
    assert copies["answers_first"] >= 1, "CANARY: the rule ran"
    assert copies["A_again"] == copies["A"]


def test_the_reset_line_takes_the_chains_marks_back(copies):
    assert any(source.startswith("chain_ingestion") for _r, source, *_ in copies["A"]["layers"]), "CANARY"
    assert [one for one in copies["A_reset"]["layers"] if one[1].startswith("chain_ingestion")] == []
    assert _marks(copies["A_reset"])[BY_HAND[0]] == BY_HAND[1]
