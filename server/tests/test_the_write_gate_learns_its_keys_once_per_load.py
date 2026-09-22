# -*- coding: utf-8 -*-
"""판정 652 · 667 — 쓰기 경로의 중복 그물이 «적재당 한 번» 배운다.

🔴 THE GATE SIX PROPERTY, WRITTEN AS A PROPERTY. The ruling's letter said
`apply_batch_updates` reads neither the file nor `pg_index`; taken literally that is false on
the first batch and always will be, because 「approved」 MEANS an index exists and something
has to look. What is true, and what this file measures, is: batches 2..N read nothing, a box
with no declared unique key probes `pg_index` never, and the write path does not open a
session per batch.

⚰️ AND THE CLOCK IT REPLACED IS THE POINT. The answer used to live behind a 5-second TTL,
and the comment on that TTL said why - the reload hook belongs to the WEB server and worker
processes never reach it, so the clock was standing in for an invalidation those processes
do not get. Keyed to loading instead, each process invalidates where it re-reads.

⚰️ [판정 652 3걸음] 이 파일의 머리글은 「두 생산자를 다 든다」였습니다. 생산자가 «하나»가
됐습니다 — 읽기 시점 문법이 삭제돼 `_legacy_right_keys` 가 없어졌고, 그것을 중립화하려고
모든 시험이 달고 있던 `monkeypatch.setattr(synthesis, "_legacy_right_keys", …)` 여섯 줄도
같이 갔습니다. 🔴 **그 여섯 줄이 이 삭제에서 제일 조용했던 자리입니다** — `setattr` 는 없는
이름에 AttributeError 를 내므로 «전부» 빨개졌고, 그래서 들켰습니다. 제 전수 조사가 import
와 문자열만 보고 `setattr` 를 못 봐서 목록에 이 파일이 아예 없었습니다.

⚠️ 창이 길어지고 모양은 안 바뀝니다: 낡은 「있다」는 `operator_line` 경고로, 낡은 「없다」는
DB 의 23505 로 나옵니다. 둘 다 시끄럽습니다.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import synthesis                                          # noqa: E402
from database import crud                                            # noqa: E402

TABLE = "w652_right"
KEY = ["job"]


@pytest.fixture(autouse=True)
def _fresh():
    synthesis.reset_right_key_cache()
    yield
    synthesis.reset_right_key_cache()


def _declared(monkeypatch, rules, covering=True, probes=None):
    """선언을 세우고, 인덱스 실재 여부를 «대답»으로 고정한다."""
    from chain import ingestion_worker, join_key_index

    monkeypatch.setattr(ingestion_worker, "load_chain_rules", lambda: list(rules))

    def fake_covering(db, table, columns, folds=None):
        if probes is not None:
            probes.append((table, tuple(columns)))
        return "uq_w652" if covering else None

    monkeypatch.setattr(join_key_index, "unique_index_covering", fake_covering)


def _target(name, table=TABLE, columns=None):
    # ⚠️ 여섯째 칸은 «부류»다 (판정 685). 서는 행은 건너뛸 것이 없으므로 None.
    return (name, table, list(columns or KEY), [None], None, None)


# ---------------------------------------------------------------------------
# ⓐ 「적재당 한 번」 — 배치 2..N 은 아무것도 안 읽는다
# ---------------------------------------------------------------------------

def test_the_second_batch_asks_nothing(monkeypatch):
    probes = []
    monkeypatch.setattr(synthesis, "declared_unique_targets",
                        lambda rules: [_target("w652_join")])
    _declared(monkeypatch, [{"name": "w652_join"}], probes=probes)

    first = synthesis.right_keys_for(None, TABLE)
    after_first = len(probes)
    second = synthesis.right_keys_for(None, TABLE)

    assert first == second
    assert after_first >= 1, "첫 배치는 물어야 합니다 — 안 물으면 답을 지어낸 것입니다"
    assert len(probes) == after_first, "둘째 배치가 pg_index 를 다시 물었습니다"


def test_a_box_with_no_declared_key_never_probes(monkeypatch):
    """🔴 게이트 ⑥ 의 성질이 «문자 그대로» 서는 자리. 선언이 0 이면 물을 것이 없습니다."""
    probes = []
    monkeypatch.setattr(synthesis, "declared_unique_targets", lambda rules: [])
    _declared(monkeypatch, [], probes=probes)

    assert synthesis.right_keys_for(None, TABLE) == []
    assert probes == [], "선언이 없는데 pg_index 를 물었습니다"


def test_loading_again_expires_the_answer(monkeypatch):
    """⚰️ 시간이 아니라 «적재»가 만료입니다 — 이 줄이 5초 TTL 을 대신합니다."""
    probes = []
    monkeypatch.setattr(synthesis, "declared_unique_targets",
                        lambda rules: [_target("w652_join")])
    _declared(monkeypatch, [{"name": "w652_join"}], probes=probes)

    synthesis.right_keys_for(None, TABLE)
    before = len(probes)
    synthesis.reset_right_key_cache()
    synthesis.right_keys_for(None, TABLE)

    assert len(probes) > before, "다시 실었는데 옛 답을 그대로 냈습니다"


def test_the_write_path_does_not_open_a_session_per_batch(monkeypatch):
    """🔴 [판정 677 ③] 이 파일의 독스트링이 «처음부터» 단언하던 문장인데, 그것을 재는 줄이
    없었습니다 — 그리고 그동안 거짓이었습니다. `legacy_probe = SessionLocal()` 이 적재
    블록 «밖»에 있어 배치마다 하나씩 열었고, 그 세션은 `rules_for_right` 에 넘겨졌다가
    한 번도 쓰이지 않았습니다(`_verified_by_left_table` 이 자기 것을 엽니다).

    ⚰️ [652 3걸음] 여기 있던 ⚠️ 는 「레거시 좌석이 «자기» 세션을 자기 시계로 여는 것은
    여기서 안 센다 — 그 문법과 같이 죽을 것이고, 그것을 여기서 재려 하면 죽는 모듈의
    수명이 이 시험의 전제가 된다」였습니다. 그 문법이 죽었으므로 세는 좌석이 «하나»이고,
    이 줄은 이제 전제 없이 참입니다.
    """
    opened = []

    import database.database as dbmod
    real = dbmod.SessionLocal

    def counted(*a, **kw):
        opened.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(dbmod, "SessionLocal", counted)
    monkeypatch.setattr(synthesis, "declared_unique_targets",
                        lambda rules: [_target("w652_join")])
    _declared(monkeypatch, [{"name": "w652_join"}])

    synthesis.right_keys_for(None, TABLE)
    synthesis.right_keys_for(None, TABLE)

    assert len(opened) == 1, (
        "적재당 한 번이어야 합니다. 연 수: %d — 배치마다 열면 쓰기 경로가 "
        "배치마다 연결을 냅니다" % len(opened))


# ---------------------------------------------------------------------------
# ⓑ 한 유일성은 한 항목
#
# ⚰️ [판정 652 3걸음] 이 절의 이름은 「두 생산자 — Q-192 를 같은 라운드에 두 번 하지 않기
#    위해」였고, 그 아래 `test_a_live_read_time_join_still_has_its_uniqueness_protected`
#    가 있었습니다. 그 줄은 자기 독스트링에 「그 문법이 죽는 커밋에서 이 줄과 그 반쪽이
#    «같이» 죽습니다」라고 적어 두었고, 이 커밋이 그 커밋입니다. 재던 것은 「아직 살아
#    있는 읽기 시점 조인의 유일성」이었는데 «살아 있는 것이 없습니다».
#    🔴 Q-192 의 부류(그물을 옮기다 한쪽 생산자를 놓치는 것)는 이제 생산자가 하나라서
#    «생길 수가» 없습니다 — 가드가 아니라 모집단이 답을 바꿨습니다.
# ---------------------------------------------------------------------------

def test_one_uniqueness_is_one_entry_even_when_two_rules_declare_it(monkeypatch):
    """⚠️ 조인과 그 `:reference` 짝이 «같은 키»를 선언합니다. 둘로 두면 한 중복이 두 이름으로
    보고돼 운영자가 한 사실을 두 문장으로 읽습니다."""
    monkeypatch.setattr(
        synthesis, "declared_unique_targets",
        lambda rules: [_target("w652_join"), _target("w652_join:reference")])
    _declared(monkeypatch, [{"name": "w652_join"}])

    answer = synthesis.right_keys_for(None, TABLE)

    assert len(answer) == 1, answer


def test_a_declaration_without_a_real_index_is_not_approved(monkeypatch):
    """⛔ 승인은 「인덱스가 «실제로» 있다」입니다. 없으면 깨질 제약도 없고, 그때 거절하면
    데이터베이스가 받아 줬을 행을 가드가 버립니다."""
    monkeypatch.setattr(synthesis, "declared_unique_targets",
                        lambda rules: [_target("w652_join")])
    _declared(monkeypatch, [{"name": "w652_join"}], covering=False)

    assert synthesis.right_keys_for(None, TABLE) == []


# ---------------------------------------------------------------------------
# ⓒ 쓰기 경로가 그 좌석을 «지난다»
# ---------------------------------------------------------------------------

def test_the_write_gate_reads_that_seat_and_not_a_second_one(monkeypatch):
    """🔴 「돈다」로 잽니다 — crud 가 그 함수를 실제로 부르는지."""
    asked = []
    monkeypatch.setattr(synthesis, "right_keys_for",
                        lambda db, table: asked.append(table) or [])

    assert crud._virtual_join_right_keys(None, TABLE) == []
    assert asked == [TABLE]


def test_an_unreadable_declaration_refuses_no_row(monkeypatch):
    """⚠️ 자세는 그대로입니다 — 선언을 못 읽으면 「조인이 없다」이지 「쓰기를 막는다」가
    아닙니다. 설정 문제를 장애로 바꾸지 않습니다."""
    def boom(db, table):
        raise RuntimeError("declaration unreadable")

    monkeypatch.setattr(synthesis, "right_keys_for", boom)

    assert crud._virtual_join_right_keys(None, TABLE) == []
