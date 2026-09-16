"""한 선언의 실패가 «무관한 표»의 읽기를 막지 않는다 (2026-09-15 운영 장애 다섯째).

소유자: 「이 가상조인 오류가 내가 건드리던 테이블과 완전 다른 건데 왜 뚱딴지같이 튀어나와서
막았던 거야?」 · 「그냥 모든 선언 무조건 다 돌면서 다 막아버렸네」.
둘 다 맞았다. 읽기 미스마다 «읽는 사람의 세션»으로 «모든» 선언을 검사했고, 검사 SQL 이 try 밖이라
표 B 의 선언 하나가 던지면 표 A 를 읽던 트랜잭션이 abort 된 채 남았다.
"""
import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chain import legacy_join_declaration as vjc  # noqa: E402
from chain import legacy_materialized_join as vje  # noqa: E402


def _rule(name, left, right):
    return {"name": name, "left_table": left, "right_table": right,
            "left_columns": ["k"], "right_columns": ["k"], "join_key": [{"left": "k", "right": "k"}],
            "expose": ["v"], "right_folds": [], "unresolved_label": "미상",
            "required_index_ddl": "CREATE UNIQUE INDEX ...", "join_cardinality": "one"}


def test_one_rule_that_cannot_be_verified_refuses_only_itself(db_session, monkeypatch):
    """🔴 「모든 선언 다 돌면서 다 막아버렸네」의 부정. B 의 검사가 던져도 A 는 «검증된 목록»에
    남고, B 만 이름 대어 거절되며, 그 세션은 다음 문장에 «답한다»(abort 아님)."""
    good, bad = _rule("a_join", "table_a", "right_a"), _rule("b_join", "table_b", "right_b")
    monkeypatch.setattr(vjc, "load_virtual_join_rules", lambda **k: [good, bad])

    def verify(session, rule):
        if rule["name"] == "b_join":
            raise RuntimeError('invalid input syntax for type double precision: "미상"')
        return {"unique_index": "uq_ok", "refused": False, "code": None}
    monkeypatch.setattr(vjc, "verify_uniqueness", verify)

    rejections = []
    verified = vjc.load_verified_rules(db_session, known_tables={}, rejections=rejections)

    assert [r["name"] for r in verified] == ["a_join"], "무관한 A 가 같이 죽었다"
    assert [r["subject"] for r in rejections] == ["b_join"], rejections
    assert db_session.execute(text("SELECT 1")).scalar() == 1, "세션이 abort 된 채 남았다"


def test_the_readers_session_is_never_touched_by_verification(db_session, monkeypatch):
    """🔴 「내가 건드리던 테이블과 완전 다른 건데 왜 막았던 거야」의 부정. 검증 «전체»가 던져도
    읽는 사람의 세션은 한 문장도 안 실렸으므로 그대로 산다 — 검증은 자기 세션이다."""
    def explode(session, **k):
        session.execute(text("SELECT 1/0"))  # 그 세션을 «일부러» abort 시킨다
        raise RuntimeError("declaration verification exploded")
    monkeypatch.setattr(vjc, "load_verified_rules", explode)
    vje.reset_cache()

    assert vje.rules_for(db_session, "table_a") == []          # 조인 없음으로 안전하게 기운다
    assert db_session.execute(text("SELECT 1")).scalar() == 1, "읽는 사람의 세션이 죽었다 — 검증이 그 세션을 썼다"
