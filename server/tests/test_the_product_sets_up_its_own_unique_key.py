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


# ---------------------------------------------------------------------------
# 접기 계획 — 「접어도 되는 것」과 「접으면 안 되는 것」을 가르는 것이 요점이다
# ---------------------------------------------------------------------------

def test_rows_that_differ_are_never_offered_as_foldable():
    """🔴 이 도구의 존재 이유. 같은 키의 행들이 «실제로 다르면» 그것은 사본이 아니라
    「신원이 이 컬럼이 아니다」는 증거다 — S-226 이 가르쳐 준 것. 접으면 데이터가 사라진다."""
    plan = {"table": "dt_log", "columns": ["dt_job_id"], "safe": [],
            "blank_keys": [],
            "unsafe": [{"key": ["JOB-1"], "rows": 400,
                        "differing_columns": ["b_wx", "b_wy", "dt_cell_key"]}]}
    sentence = unique_key.describe_fold_plan(plan)

    assert "데이터가 사라지는" in sentence
    assert "b_wx" in sentence
    assert "키를 넓히십시오" in sentence
    assert "접어도 되는" not in sentence


def test_true_copies_are_offered_and_counted():
    plan = {"table": "t", "columns": ["k"], "unsafe": [], "blank_keys": [],
            "safe": [{"key": ["A"], "rows": 3, "keep": "r1", "drop": ["r2", "r3"],
                      "differing_columns": []}]}
    sentence = unique_key.describe_fold_plan(plan)

    assert "접어도 되는 키 1" in sentence
    assert "3 행 중 1 남김" in sentence


def test_the_two_kinds_are_never_merged_into_one_count():
    """⚠️ 「중복 N」 하나로 합치면 운영자가 «접어도 되는지»를 못 고른다 — 그 판단이
    이 화면의 전부다."""
    plan = {"table": "t", "columns": ["k"], "blank_keys": [],
            "safe": [{"key": ["A"], "rows": 2, "differing_columns": []}],
            "unsafe": [{"key": ["B"], "rows": 5, "differing_columns": ["x"]}]}
    sentence = unique_key.describe_fold_plan(plan)

    assert "접어도 되는 키 1" in sentence
    assert "데이터가 사라지는» 키 1" in sentence


def test_a_json_cell_can_be_compared_without_blowing_up():
    """dict·list 는 해시가 안 된다. 비교하다 던지면 계획 자체가 «안 나온다»."""
    assert unique_key._comparable({"b": 1, "a": 2}) == unique_key._comparable({"a": 2, "b": 1})
    assert unique_key._comparable([1, 2]) != unique_key._comparable([2, 1])
    assert unique_key._comparable(None) is None


# ---------------------------------------------------------------------------
# 「행 하나는 사실 하나」 — 선언만으로 잡히는 위반 (소유자 2026-09-15)
# ---------------------------------------------------------------------------

_KNOWN = {"dt_log": {"composite_key_source": ["dt_job_id", "b_wx", "b_wy"]},
          "plainly_keyed": {"business_key": "k"}}


def test_a_key_narrower_than_the_identity_is_known_without_reading_a_row():
    """🔴 이것이 2026-09-14 에 없어서 운영자가 조인을 전부 껐다. 카탈로그가 그 표의 신원을
    «이미» 적어 두므로, 조인 키가 그 부분집합이면 유일 인덱스는 영원히 설 수 없다 —
    중복을 세지 않고도, 데이터를 한 행도 안 읽고도 안다."""
    assert unique_key.narrower_than_identity(
        "dt_log", ["dt_job_id"], _KNOWN) == ["dt_job_id", "b_wx", "b_wy"]


def test_the_right_key_is_not_flagged():
    assert unique_key.narrower_than_identity(
        "dt_log", ["dt_job_id", "b_wx", "b_wy"], _KNOWN) is None


def test_a_table_that_declares_no_composite_identity_is_not_judged():
    """⚠️ 신원을 «안 적은» 표에 대해서는 이 검사가 할 말이 없다. 없는 선언을 근거로
    거절하면 그것은 「내가 기대한 모양」을 강요하는 것이다."""
    assert unique_key.narrower_than_identity("plainly_keyed", ["k"], _KNOWN) is None
    assert unique_key.narrower_than_identity("unknown_table", ["k"], _KNOWN) is None


def test_a_key_wider_than_the_identity_is_not_flagged():
    """⚠️ 넓은 키는 «유일하다». 좁은 것만 불가능하다 — 방향을 뒤집으면 멀쩡한 선언을 막는다."""
    assert unique_key.narrower_than_identity(
        "dt_log", ["dt_job_id", "b_wx", "b_wy", "c_wx"], _KNOWN) is None
