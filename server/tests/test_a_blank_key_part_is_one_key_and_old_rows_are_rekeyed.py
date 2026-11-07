"""(a, blank) twice is one key, and a row stored before that is moved onto it by the re-key (소유자 10-24 «a,빈값 a,빈값
같은거로 처리하라고 지금 키충돌나면 접잖아», 총괄 242f4a43a ㄱ / ㄱ2).

  one batch      (a, '') · (a, None) · (b, x) · (b, x) · ('', None) · ('', None)    a_ one row · b_x one row · two keyless
  stored keyless an (a, NULL-key) row from before, re-keyed, then a file's (a, '')   one row, the file's value
  given key      a row stored under ORPHAN_BK with a person's value, re-keyed,      one row under _S1, the person's
                 then a machine write of (blank, S1)                                 value still shown

The re-key is `scripts/rebuild_blank_business_keys.py`'s own plan and apply (`plan_rekeys` · `apply_rekeys`)."""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER)
sys.path.insert(0, os.path.join(SERVER, "scripts"))

from database import crud, models, schemas                            # noqa: E402
from database.database import Base                                    # noqa: E402
import rebuild_blank_business_keys as rekey                           # noqa: E402

SRC, DERIVED = "bkp_src", "bkp_derived"
CONFIG = {
    SRC: {"composite_key_source": ["c1", "c2"], "column_types": {"c1": "string", "c2": "string", "v": "string"},
          "display_columns": ["c1", "c2", "v"]},
    DERIVED: {"business_key": "wafer_key", "composite_key_source": ["lot", "slot"],
              "column_types": {"wafer_key": "string", "lot": "string", "slot": "string", "wafer_id": "string"},
              "display_columns": ["wafer_key", "lot", "slot", "wafer_id"]},
}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _push(db, table, rows, source="f.csv", row_id=None):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates=dict(row), source_name=source, updated_by="t")
        for row in rows]))
    db.commit()
    db.expire_all()


def _rekey(db, table):
    """The script's own plan and apply over the table's rows - what `--apply` does."""
    sources = CONFIG[table]["composite_key_source"]
    model = models.DYNAMIC_TABLES[table]
    rows = [{"row_id": r.row_id, "business_key_val": r.business_key_val, **{c: getattr(r, c) for c in sources}}
            for r in db.query(model)]
    plan = rekey.plan_rekeys(table, rows, sources, "_")
    rekey.apply_rekeys(db, table, plan["pending"])
    db.expire_all()
    return plan


def _stored(db, table, *columns):
    model = models.DYNAMIC_TABLES[table]
    return sorted(tuple("" if getattr(r, c) is None else getattr(r, c) for c in ("business_key_val",) + columns)
                  for r in db.query(model))


def test_a_blank_part_among_filled_ones_is_one_key_and_every_part_blank_is_none(db):
    _push(db, SRC, [{"c1": "a", "c2": "", "v": "1"}, {"c1": "a", "c2": None, "v": "2"},
                    {"c1": "b", "c2": "x", "v": "3"}, {"c1": "b", "c2": "x", "v": "4"},
                    {"c1": "", "c2": None, "v": "5"}, {"c1": "", "c2": None, "v": "6"}])
    assert _stored(db, SRC, "v") == [("", "5"), ("", "6"), ("a_", "2"), ("b_x", "4")]


def test_a_keyless_row_from_before_is_rekeyed_and_the_next_file_lands_on_it(db):
    model = models.DYNAMIC_TABLES[SRC]
    db.add(model(row_id="OLD", c1="a", c2=None, v="0"))          # stored before 242f4a43a: no key
    db.commit()
    plan = _rekey(db, SRC)
    assert plan["pending"] == [("OLD", "a_")] and plan["stat"]["collides"] == 0, plan
    _push(db, SRC, [{"c1": "a", "c2": "", "v": "1"}])
    assert [(r.row_id, r.business_key_val, r.v) for r in db.query(model)] == [("OLD", "a_", "1")]


def test_a_row_stored_under_a_given_key_moves_and_a_persons_value_still_wins(db):
    model = models.DYNAMIC_TABLES[DERIVED]
    db.add(model(row_id="ORPHAN", business_key_val="ORPHAN_BK", wafer_key="ORPHAN_BK", lot=None, slot="S1"))
    db.commit()
    _push(db, DERIVED, [{"wafer_id": "WF_HUMAN"}], source=crud.USER_SOURCE, row_id="ORPHAN")
    plan = _rekey(db, DERIVED)
    assert plan["pending"] == [("ORPHAN", "_S1")], plan
    _push(db, DERIVED, [{"lot": "", "slot": "S1", "wafer_id": "WF_GOOD"}], source="enrichment_auto_confirm")
    assert [(r.row_id, r.business_key_val, r.wafer_key, r.wafer_id) for r in db.query(model)] == [
        ("ORPHAN", "_S1", "_S1", "WF_HUMAN")]
