# -*- coding: utf-8 -*-
"""소유자 2026-09-23, 운영 장애: 「돌기는 하는데 행추가가 안되는 케이스」 ·
「파샬 디시전 키 낫 드라이브드」 · 「그냥 컴포짓키로해 그게 테이블에서 정의한 정체니까 /
근데 none, w1을 조합한건 none w1 이지 그게 왜 lot w1 에 접히지?」

THE OWNER'S LAST SENTENCE IS THE RULING, AND THE PRODUCT ALREADY AGREES WITH IT:
`compose_business_key` joins without judging blankness, so `("", "W1")` is `"_W1"` and
`("LOT", "W1")` is `"LOT_W1"` - a blank component KEEPS ITS SLOT. Nothing folds them.

So a partial decision key owns an identity exactly when the derived table's
`composite_key_source` HAS A SLOT for the column that went blank. The seat used to ask a
coarser question - 「is the composite the WHOLE decision key」 - and that refused tables
which carry the blank column in a narrower composite. That refusal is the outage.

🔴 EVERY GATE HERE IS A ROW COUNT, AND ㉢ ASSERTS A VALUE, NOT A COUNT. The defect that
started this round kept ONE row and erased a column on it, so a count alone stayed
plausible while data was gone.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                     # noqa: E402
from chain import enrichment, rule_shape                              # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

SRC = "pk_src"
#: The operational contract: a PROPER SUBSET of the decision key that still carries the
#: column which goes blank. This is the one the old question refused.
CARRIES = "pk_carries"
#: The same rule against a table whose composite has no slot for that column. Those rows
#: are one identity by the table's own declaration, so the refusal stays.
NARROW = "pk_narrow"
#: ㉤: composite IS the decision key, declared in ITS OWN order. Nothing here may be
#: respelled by this round - that is what bounds the change to zero migration.
WIDE = "pk_wide"

DECISION_KEY = ["core_lot", "dt_wafer_id", "step"]
DERIVED_COLS = {"job_id": "string", "core_lot": "string",
                "dt_wafer_id": "string", "step": "string", "grade": "string"}

TABLES = {
    SRC: {"business_key": "log_key", "composite_key_source": ["log_key"],
          "column_types": {"log_key": "string", "core_lot": "string",
                           "dt_wafer_id": "string", "step": "string",
                           "grade": "string"},
          "display_columns": ["log_key", "core_lot", "dt_wafer_id", "step", "grade"]},
    CARRIES: {"business_key": "job_id",
              "composite_key_source": ["core_lot", "dt_wafer_id"],
              "column_types": dict(DERIVED_COLS),
              "display_columns": list(DERIVED_COLS)},
    NARROW: {"business_key": "job_id",
             "composite_key_source": ["dt_wafer_id"],
             "column_types": dict(DERIVED_COLS),
             "display_columns": list(DERIVED_COLS)},
    WIDE: {"business_key": "job_id",
           "composite_key_source": ["step", "dt_wafer_id", "core_lot"],
           "column_types": dict(DERIVED_COLS),
           "display_columns": list(DERIVED_COLS)},
}


@pytest.fixture(name="db")
def fixture_db():
    mapper_sdk.discover()
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
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
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _seed(db, rows):
    crud.apply_batch_updates(db, SRC, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=r, source_name="seed", updated_by="outage")
        for r in rows]))
    db.commit()


def _derived(db, table):
    model = models.DYNAMIC_TABLES[table]
    return [(r.business_key_val, r.core_lot, r.dt_wafer_id)
            for r in db.query(model).all()]


def _dedup_rule(into):
    stood = rule_shape.expand_declaration(
        {"name": "outage_%s" % into, "on": {"table": SRC}, "into": {"table": into},
         "derive": {"kind": "decide",
                    "decide": {"key": DECISION_KEY, "fields": ["grade"]}}},
        crud.TABLE_CONFIG)
    return [r for r in (stood[0] or []) if r["name"].startswith("enrichment_dedup:")][0]


def _run(db, into):
    events = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == SRC).all()
    assert events, "the trigger table produced no outbox event - the fixture is broken"
    worker._process_chain_transaction_group_sync(
        "tx-%s" % into, events, db, [_dedup_rule(into)])
    db.commit()
    db.expire_all()


# ---------------------------------------------------------------------------

def test_the_rule_stands_on_the_operational_contract(db):
    """㉠ The rule STOOD and the chain RAN - the owner said so, and the loader has to
    agree or every row count below is about a shape the product never sees."""
    normalized, why = enrichment.config._validate_rule(
        "outage_rule", {"source_table": SRC, "derived_table": CARRIES,
                        "decision_key": DECISION_KEY, "target_fields": ["grade"]},
        crud.TABLE_CONFIG)

    assert normalized is not None, f"the loader refused the operational contract: {why}"
    assert set(TABLES[CARRIES]["composite_key_source"]) < set(DECISION_KEY), (
        "the fixture stopped being a PROPER subset, so it no longer stands the outage")


def test_a_row_whose_key_is_partly_blank_gets_a_derived_row(db):
    """㉡ 「돌기는 하는데 행추가가 안되는 케이스」 — before N, after N+k."""
    _seed(db, [{"log_key": "L1", "core_lot": "LOT", "dt_wafer_id": "W1",
                "step": "S1", "grade": "A"},
               {"log_key": "L2", "core_lot": "", "dt_wafer_id": "W2",
                "step": "S1", "grade": "B"}])

    before = _derived(db, CARRIES)
    assert len(before) == 0, "the derived table is not empty before the rule runs"

    _run(db, CARRIES)

    after = _derived(db, CARRIES)
    assert len(after) == 2, (
        f"a partly blank decision key derived no row: before 0, after {len(after)} "
        f"({after})")


def test_the_partial_row_stands_beside_the_complete_one_and_erases_nothing(db):
    """㉢ 총괄: 「여기가 제일 중요합니다」 — 삭제 0 · 병합 0, and the VALUE survives.

    Both rows carry `dt_wafer_id = W1` and `step = S1`; only `core_lot` differs, and on
    one of them it is blank. The composite has a slot for `core_lot`, so the identities
    are 「LOT_W1」 and 「_W1」 - two rows. Counting rows is not enough: the way this broke
    was one row surviving with the other's blank written over its value.
    """
    _seed(db, [{"log_key": "L1", "core_lot": "LOT", "dt_wafer_id": "W1",
                "step": "S1", "grade": "A"},
               {"log_key": "L2", "core_lot": "", "dt_wafer_id": "W1",
                "step": "S1", "grade": "B"}])

    _run(db, CARRIES)

    rows = _derived(db, CARRIES)
    keys = sorted(k for k, _lot, _w in rows)
    assert len(rows) == 2, f"the partial key landed on the complete key's row: {rows}"
    assert len(set(keys)) == 2, f"two rows share one identity: {keys}"
    assert all(k for k in keys), f"a derived row carries an EMPTY identity: {keys}"
    assert [r for r in rows if r[1] == "LOT"], (
        f"the complete key's core_lot was erased by the partial row: {rows}")


def test_a_narrow_composite_updates_its_one_row_and_erases_no_value(db):
    """㉣ `NARROW` declares its identity as `dt_wafer_id` alone, so two rows differing
    only in `core_lot` are ONE row BY THE DECLARATION - blank or not. The product may not
    invent a difference the table does not declare, so the partial key lands on that row
    rather than being skipped.

    🔴 AND IT MAY NOT ARRIVE CARRYING AN ERASER. The blank component builds the key; it
    is not a claim that the cell is empty. 「비었다고 말하는」 blank is the join's matched
    NULL (판정 f3c04dee) and that one still writes - both halves of the chain share one
    `source_name`, so this has to be told apart HERE and not at the write door.
    """
    _seed(db, [{"log_key": "L1", "core_lot": "LOT", "dt_wafer_id": "W1",
                "step": "S1", "grade": "A"},
               {"log_key": "L2", "core_lot": "", "dt_wafer_id": "W1",
                "step": "S1", "grade": "B"}])

    _run(db, NARROW)

    rows = _derived(db, NARROW)
    assert len(rows) == 1, (
        f"the table declares one identity for these two keys, so one row: {rows}")
    assert rows[0][1] == "LOT", (
        f"the partial key's blank core_lot erased the value that was there: {rows}")


#: ⚰️ 「정체성 컬럼이 전부 빈 행은 안 만든다」(판정 13e2894f1)의 게이트가 여기 있었다 —
#: 이 파일의 좌석에서는 «공허»했다. 변이로 그 가드를 죽여도 초록이었고, 이유는 체인 쓰기
#: 경로에 키 게이트가 «따로» 있기 때문이다 (`ingestion_worker` 의 `unkeyed_refused`).
#: 그 가드가 «혼자» 답하는 자리는 소급 스윕이고, 그쪽은 변이로 빨개지는 시험이 이미 있다:
#: test_backfill_enrichment.py::test_a_partial_key_is_refused_when_the_blank_column_IS_the_business_key


def test_the_mapper_answers_an_empty_batch_and_a_ruleless_call(db):
    """🔴 총괄 실측 2026-09-23: 착지 직후 `map_enrichment_dedup(None, [], None)` 이
    `TypeError: _result() takes 3 positional arguments but 4 were given` 로 터졌다.

    두 갈래 다 «정상 경로»다 — 빈 배치는 운영에서 늘 오고, `params` 없는 규칙은
    잘못 선언된 규칙이 지나는 자리다. 그런데 이 파일의 다른 시험 넷은 전부 «행이 있는»
    배치를 넘기므로 넷 다 초록인 채로 그 갈래가 터져 있었다. 조건이 드물어서가 아니라
    시험이 «늘 도는 조건»을 안 지나고 있었다.
    """
    from chain.enrichment import mapper

    empty = mapper.map_enrichment_dedup(None, [], None)
    assert empty["updates"] == []
    assert empty["skipped_no_key"] == 0

    ruleless = mapper.map_enrichment_dedup(None, [{"data": {}}], {})
    assert ruleless["updates"] == []


def test_the_two_skips_reach_the_caller_under_their_own_names(db):
    """🔴 계기가 조용히 죽는 자리. The identity-blank guard counted and logged, and the
    count went nowhere - a backfill preview could not show it, which is the same shape as
    the defect that opened this round. The two skips never fold: one is fixed in the
    source data, the other in the derived table's identity declaration.
    """
    from chain.enrichment import mapper

    shape = mapper.map_enrichment_dedup(None, [], None)
    assert "skipped_no_key" in shape and "skipped_blank_identity" in shape, (
        f"a skip count the seat keeps is not in its answer: {sorted(shape)}")

    _seed(db, [{"log_key": "B1", "core_lot": "", "dt_wafer_id": "",
                "step": "S1", "grade": "A"}])
    payloads = [{"data": {c: {"value": getattr(r, c)}
                          for c in ("log_key", "core_lot", "dt_wafer_id", "step", "grade")}}
                for r in db.query(models.DYNAMIC_TABLES[SRC]).all()]

    out = mapper.map_enrichment_dedup(db, payloads, rule=_dedup_rule(CARRIES))

    assert out["skipped_blank_identity"] == 1, (
        f"the guard ran but its count did not reach the caller: {out}")
    assert out["skipped_no_key"] == 0, (
        "these rows HAVE a decision key (step is present) - do not fold the two facts")
    assert out["updates"] == []
