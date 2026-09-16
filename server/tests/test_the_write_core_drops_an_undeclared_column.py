# -*- coding: utf-8 -*-
"""쓰기 코어는 «선언되지 않은 컬럼»을 떨어뜨린다 — 그리고 그 앞에 문이 «하나»뿐이다.

🪦 [S-283] THESE TWO ASSERTIONS CAME OUT OF `test_virtual_join_executor.py`, WHICH DIED
WITH THE READ-TIME JOIN. That file measured a mechanism that no longer exists, but these
two do not: they are about the write core, and the write core is untouched.

🔴 WHY THEY WERE NOT DELETED WITH THEIR FILE. The rule is 「테스트는 자기가 재던 코드와
같은 커밋에서 죽는다」 — and its other half is that the unit is the TEST, not the file. The
old file's premise was 「이 컬럼은 가상 조인 컬럼이다」; the premise that actually carried
these two is 「이 컬럼은 선언에 없다」, which survives the retirement word for word. Deleting
them with the file would have taken a live gate down for a dead reason.

⚠️ WHAT THE SECOND ONE IS REALLY FOR. `apply_row_update_internal` having ONE caller is the
whole argument that a guard placed in front of that caller cannot be bypassed. It used to
back `refuse_virtual_join_columns`; that guard is gone with its subject, but the property it
depended on is load-bearing for every OTHER gate standing on the same funnel (the replace_map
scope refusal, the duplicate refusal). A second caller appearing is exactly as significant
today as it was then, and nothing else in the suite counts them.
"""
import pytest

from database import crud, models, schemas

TABLES = {
    "wcore_test_log": {
        "business_key": "log_id",
        "column_types": {"log_id": "string", "core_lot": "string"},
    },
}

#: Not in `column_types` above, and that is the whole fixture. It used to be a name a join
#: exposed; today it is simply a name the declaration does not carry - and the write core
#: cannot tell those apart, which is the point.
UNDECLARED = "fab_site"


@pytest.fixture()
def write_env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    return db_session


def test_the_write_core_drops_a_column_the_declaration_does_not_carry(write_env):
    """관문 뒤의 «두 번째 층» — 코어 자신도 선언에 없는 컬럼을 저장하지 않는다.

    이것이 중요한 이유는 파급 때문이다: `delete_cell_source_batch` 와
    `set_cell_manual_priority_batch` 는 컬럼에 «직접 setattr» 하는 유일한 다른 두 곳인데,
    둘 다 «이미 존재하는 CellSource 층»에만 작동한다. 선언에 없는 컬럼으로는 그 층이
    만들어질 수 없으므로 두 경로가 «구조적으로» 도달 불가능해진다 — 그 논거 전체가 이
    테스트 한 줄 위에 서 있다.
    """
    db = write_env
    crud.apply_row_update_internal(db, "wcore_test_log", schemas.GeneralUpdateItem(
        business_key_val="L1", updates={"log_id": "L1", UNDECLARED: "sneaked-in"},
        source_name="user", updated_by="test"))
    db.flush()

    assert db.query(models.CellSource).filter(
        models.CellSource.table_name == "wcore_test_log",
        models.CellSource.column_name == UNDECLARED).count() == 0, (
        "선언에 없는 컬럼에 소스 층이 생기면 Pin/철회 경로가 그것에 도달할 수 있게 된다")


def test_the_funnel_still_has_exactly_one_caller():
    """거부가 «구조적»이라는 주장의 근거: 쓰기 코어의 호출부가 하나다.

    `apply_row_update_internal` 을 부르는 곳이 `apply_batch_updates` 하나뿐이라, 그 함수
    앞에 선 관문을 우회해 컬럼에 도달할 쓰기 경로가 «존재하지 않는다». 호출부가 늘어나면
    이 테스트가 그것을 알린다.
    """
    import inspect
    src = inspect.getsource(crud)
    calls = [ln for ln in src.splitlines()
             if "apply_row_update_internal(" in ln and not ln.strip().startswith("def ")]
    assert len(calls) == 1, (
        f"쓰기 코어의 호출부가 {len(calls)}개다 — 관문을 우회하는 경로가 생겼는지 확인하고, "
        f"정당하면 그 호출부도 같은 관문 뒤로 보낼 것")
