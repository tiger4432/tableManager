"""유일 키를 «기계가» 세우는 자리 — 조율 부분 (S-235).

⚠️ 이 파일이 재는 범위를 «먼저» 적는다. 인덱스 카탈로그 질의와 DDL 은 PostgreSQL 전용이라
SQLite 스위트가 못 태운다. 그래서 여기서 채점하는 것은 «언제 시도하나 · 몇 번 시도하나 ·
못 세웠을 때 무엇을 말하나»이고, SQL 자체는 박스의 진짜 PG 에서 확인한다.
🔴 범위를 안 적으면 이 파일은 「유일 키 자동 설치가 시험됐다」로 읽힌다 — 그것이 이 저장소가
   여러 번 맞은 「대리를 성질로 읽는」 병이다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from virtual_join import unique_key  # noqa: E402


def setup_function(_):
    unique_key.forget()


def test_it_is_attempted_once_per_rule_per_process(monkeypatch):
    """🔴 이 단언이 없으면 데이터베이스가 위험하다. 이 판정이 사는 자리는 읽기 경로의 5초
    TTL 캐시라, 미스마다 DDL 을 던지면 로그가 아니라 «데이터베이스»를 채운다."""
    calls = []
    monkeypatch.setattr(unique_key, "ensure",
                        lambda *a, **k: calls.append(a) or {"state": "ok", "created": "DDL"})

    for _ in range(50):
        unique_key.ensure_once(None, "slot_trace", "dt_log", ["lot", "slot"])

    assert len(calls) == 1, "5초마다 도는 자리에서 %d 번 시도했다" % len(calls)


def test_a_changed_declaration_may_be_asked_again(monkeypatch):
    """⚠️ 기억은 «이 선언에 대한» 것이지 영구 판정이 아니다 — 선언이 바뀌면 다시 묻는다."""
    calls = []
    monkeypatch.setattr(unique_key, "ensure",
                        lambda *a, **k: calls.append(a) or {"state": "ok", "created": "DDL"})

    unique_key.ensure_once(None, "r", "t", ["k"])
    unique_key.forget("r")
    unique_key.ensure_once(None, "r", "t", ["k"])
    assert len(calls) == 2


def test_the_switch_stops_the_product_from_touching_the_database(monkeypatch):
    """운영자가 «자동 설치»를 끌 수 있어야 한다 — DDL 은 언제나 누군가의 결정이다."""
    monkeypatch.setenv("ASSY_VJOIN_AUTO_INDEX", "0")
    monkeypatch.setattr(unique_key, "ensure",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("만지면 안 된다")))
    monkeypatch.setattr(unique_key, "inspect",
                        lambda *a, **k: {"state": "missing", "invalid": [], "duplicates": []})

    report = unique_key.ensure_once(None, "r", "t", ["k"])
    assert report["skipped"].startswith("ASSY_VJOIN_AUTO_INDEX")
    assert report["created"] is None


def test_duplicates_are_reported_as_values_and_counts_not_as_ddl():
    """🔴 이 모듈의 요점. 운영자가 읽어야 하는 것은 「이 키가 몇 행 겹쳤다」이지
    「이 DDL 을 실행하세요」가 아니다 — 후자는 2026-09-14 에 조인을 전부 끄게 만들었다."""
    report = {"state": "duplicates", "invalid": [],
              "duplicates": [{"key": ["LOT-A", "01"], "rows": 3},
                             {"key": ["LOT-B", "02"], "rows": 2}]}
    sentence = unique_key.describe("dt_log", ["lot", "slot"], report)

    assert "LOT-A" in sentence and "3 행" in sentence
    assert "LOT-B" in sentence and "2 행" in sentence
    assert "CREATE" not in sentence.upper(), "DDL 을 다시 내밀고 있다"


def test_an_invalid_leftover_is_named_as_the_cause_and_not_as_duplicates():
    """🔴 중복이 «하나도 없어도» 조인이 거절될 수 있다 — 취소된 빌드의 잔해가 이름을
    붙잡고 있으면 `IF NOT EXISTS` 가 「이미 있다」로 답한다. 두 원인을 같은 문장으로
    말하면 운영자가 없는 중복을 찾으러 간다."""
    report = {"state": "invalid", "invalid": ["uq_vjoin_slot_trace"], "duplicates": []}
    sentence = unique_key.describe("dt_log", ["lot", "slot"], report)

    assert "INVALID" in sentence
    assert "uq_vjoin_slot_trace" in sentence
    assert "행" not in sentence, "중복 얘기가 섞여 있다"


def test_when_there_is_nothing_in_the_way_it_says_it_will_build_it():
    sentence = unique_key.describe(
        "dt_log", ["lot"], {"state": "missing", "invalid": [], "duplicates": []})
    assert "제품이 만듭니다" in sentence


def test_an_empty_key_is_absence_and_gets_its_own_sentence():
    """🔴 박스 실측에서 바로 나온 것: 한 컬럼의 «빈 문자열»이 수십만 행이었다. 그것을
    「중복」이라 부르면 운영자가 «없는 중복»을 찾으러 가고, 접기로 고치려 들면 키 없는 행
    전부가 한 행이 된다. 상설이 이미 답을 정해 뒀다 — 길이 0 인 문자열은 «부재»다."""
    report = {"state": "blank_keys", "invalid": [], "duplicates": [],
              "blank_keys": [{"key": [""], "rows": 523015}]}
    sentence = unique_key.describe("dt_log", ["dt_job_id"], report)

    assert "비어 있습니다" in sentence and "523015" in sentence
    assert "부재" in sentence
    assert "중복이 아니라" in sentence


def test_a_blank_bucket_is_noted_but_does_not_hide_the_real_duplicates():
    """⚠️ 둘이 같이 있을 수 있다. 그때는 «진짜 중복»이 본문이고 빈 키는 꼬리표다."""
    report = {"state": "duplicates", "invalid": [],
              "duplicates": [{"key": ["LOT-A"], "rows": 2}],
              "blank_keys": [{"key": [""], "rows": 900}]}
    sentence = unique_key.describe("dt_log", ["lot"], report)

    assert "LOT-A" in sentence
    assert "900" in sentence and "부재" in sentence
