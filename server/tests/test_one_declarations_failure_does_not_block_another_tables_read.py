"""한 선언의 실패가 «무관한 표»의 읽기를 막지 않는다 (2026-09-15 운영 장애 다섯째).

소유자: 「이 가상조인 오류가 내가 건드리던 테이블과 완전 다른 건데 왜 뚱딴지같이 튀어나와서
막았던 거야?」 · 「그냥 모든 선언 무조건 다 돌면서 다 막아버렸네」.
둘 다 맞았다. 읽기 미스마다 «읽는 사람의 세션»으로 «모든» 선언을 검사했고, 검사 SQL 이 try 밖이라
표 B 의 선언 하나가 던지면 표 A 를 읽던 트랜잭션이 abort 된 채 남았다.

⚰️ [판정 652 3걸음] 그 좌석(`legacy_materialized_join` 의 TTL 캐시 + 읽기 시점 검증)은
문법과 같이 걷혔다. **증상을 재는 이 파일은 «걷히지 않는다»** — 은퇴 상설이 「아팠던 증상을
대조군으로 남긴다」이고, 같은 실수를 다시 할 수 있는 자리가 «지금도» 있기 때문이다:
`chain.synthesis.right_keys_for` 가 선언을 읽고 `pg_index` 를 판다. 그래서 좌석만 옮겨 단다.

⚠️ 옛 파일이 재던 것 «둘» 중 하나는 모양이 바뀌었고, 그것을 여기 적는다.
   ① 「B 하나만 거절되고 A 는 남는다」 — 그 자리는 읽기 경로의 «검증 목록»이었다. 오늘
      쓰기 게이트는 선언을 못 읽으면 「조인이 없다」로 기울어 «아무 행도 거절하지 않는다»
      (`test_the_write_gate_learns_its_keys_once_per_load` 의 마지막 줄이 그것을 잰다).
      설정 문제를 장애로 바꾸지 않는다는 자세는 같고, 단위가 규칙에서 «게이트 전체»로 바뀌었다.
   ② 「읽는 사람의 세션은 한 문장도 안 실린다」 — 소유자가 실제로 맞은 증상이고, 아래가 그것이다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chain import synthesis  # noqa: E402
from database import crud    # noqa: E402


def test_the_readers_session_is_never_touched_by_verification(db_session, monkeypatch):
    """🔴 「내가 건드리던 테이블과 완전 다른 건데 왜 막았던 거야」의 부정. 승인 검사는 «자기
    세션»에서 돌므로, 그것이 던지든 말든 읽는 사람의 트랜잭션에는 한 문장도 안 실린다.

    🔴 그리고 이 줄은 «세션 동일성»을 직접 잰다 — 옛 판이 `SELECT 1/0` 으로 그 세션을
    abort 시켜 「그래도 살아 있나」를 물었는데, 이 픽스처는 **SQLite** 이고 거기서 `1/0` 은
    예외가 아니라 NULL 이다. 그래서 그 줄은 이 박스에서 «아무것도 단언하지 않았다** —
    PostgreSQL 전용 고장 모양을 PostgreSQL 아닌 데서 채점한 것이다. 성질(「누구의 세션인가」)을
    바로 물으면 방언과 무관하고, 좌석이 호출자 세션을 쓰는 순간 빨개진다.

    ⚠️ 던지는 자리를 `unique_index_covering` 으로 잡은 것은 그것이 세션을 «실제로 받는»
    호출이기 때문이다. 그 위를 패치하면 세션이 전달되지도 않아 이 줄이 공허해진다.
    """
    synthesis.reset_right_key_cache()
    seen = []

    def explode(session, table, columns, folds=None):
        seen.append(session)
        raise RuntimeError("index probe exploded")

    from chain import ingestion_worker, join_key_index
    monkeypatch.setattr(join_key_index, "unique_index_covering", explode)
    monkeypatch.setattr(synthesis, "declared_unique_targets",
                        lambda rules: [("b_join", "right_b", ["k"], [None], None, None)])
    monkeypatch.setattr(ingestion_worker, "load_chain_rules", lambda: [{"name": "b_join"}])

    # 🔴 「조인 없음」으로 안전하게 기운다 — 거절이 아니라 무동작이다.
    assert crud._virtual_join_right_keys(db_session, "table_a") == []
    assert seen, "승인 검사에 닿지도 않았습니다 — 이 시험이 아무것도 안 잽니다"
    assert seen[0] is not db_session, (
        "승인 검사가 «읽는 사람의 세션»을 썼습니다 — 2026-09-15 장애 다섯째의 모양입니다")
    assert db_session.is_active, "읽는 사람의 트랜잭션이 이 호출로 망가졌습니다"

    synthesis.reset_right_key_cache()
