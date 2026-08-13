"""[Tier 1] 경로+stat 원장 / 파일을 옮기지 않는 모드 / 실패의 가시성.

무엇을 고정하는가
-----------------
「이 파일을 이미 처리했나?」의 답을 **파일 전체를 읽어야만** 얻을 수 있던 것이,
파일을 옮기지 않기로 하는 순간 스윕마다 트리 전체 해시가 된다. 그래서 tier 1
(`(경로, mtime, size)` 일치 → 해시 없이 스킵)을 넣었고, 이 파일은 그 결정이
**깨질 수 있는 방향들**을 못으로 박는다:

  1. 켜져 있으면 해시가 **0회**여야 한다 (스킵이 진짜 싸야 의미가 있다)
  2. 꺼져 있으면 해시가 **다시 돌아야** 한다 (고장 주입 없이는 ①의 초록이
     「스윕이 아무것도 안 했다」와 구별되지 않는다)
  3. 내용이 바뀌면 **다시 적재돼야** 한다 (tier 1이 삼키면 안 되는 유일한 경우)
  4. 실패한 파일은 `err/` 없이도 **다시 시도되지 않고**, 「무엇이 왜」가 남아야 한다
  5. 강제 재처리 3경로가 새 경로에서도 **여전히 산다**

테이블명은 사용자 config에 실존 불가능한 `tier1_test_*` 접두 사용 (교훈 파일).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import directory_watcher
import ingestion_checkpoint
from directory_watcher import IngestionHandler
from database.database import Base
from database import crud, models

TABLE = "tier1_test_parts"
PARTS_INFO = {
    "business_key": "part_no",
    "column_types": {"part_no": "string", "category": "string", "stock_qty": "number"},
    "display_columns": ["part_no", "category", "stock_qty"],
}


def _csv(n, prefix="P"):
    lines = ["part_no,category,stock_qty"]
    lines += [f"{prefix}-{i},Cap,{i}" for i in range(1, n + 1)]
    return "\n".join(lines) + "\n"


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return str(path)


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    table_config = {TABLE: dict(PARTS_INFO)}
    models.init_dynamic_models(table_config)
    crud.TABLE_CONFIG.update(table_config)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    models.ensure_ingestion_checkpoint_table(engine)

    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: table_config)
    monkeypatch.setattr(directory_watcher, "SessionLocal", TestingSessionLocal)
    settings_path = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings_path))

    ws = tmp_path / "ws"
    (ws / "raws").mkdir(parents=True, exist_ok=True)
    (ws / "archives").mkdir(exist_ok=True)
    (ws / "err").mkdir(exist_ok=True)
    handler = IngestionHandler(workspace_path=str(ws), config_path=None,
                               archives_path=str(ws / "archives"),
                               default_table_name=TABLE)

    # Count the expensive thing directly: a tier-1 hit must not reach this.
    counter = {"hashes": 0, "ingests": 0}
    real_sig = ingestion_checkpoint.compute_file_signature
    real_apply = crud.apply_batch_updates

    def counting_sig(p):
        counter["hashes"] += 1
        return real_sig(p)

    def counting_apply(db, t, b):
        counter["ingests"] += 1
        return real_apply(db, t, b)

    monkeypatch.setattr(directory_watcher, "compute_file_signature", counting_sig)
    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates", counting_apply)

    def settings(**kw):
        settings_path.write_text(json.dumps(kw), encoding="utf-8")

    def process(path):
        counter["hashes"] = counter["ingests"] = 0
        handler.process_with_retry(path, delay=0.01)
        return dict(counter)

    yield {"engine": engine, "SessionLocal": TestingSessionLocal, "ws": ws,
           "handler": handler, "settings": settings, "process": process,
           "raws": ws / "raws"}
    Base.metadata.drop_all(bind=engine)


def _rows(env):
    db = env["SessionLocal"]()
    try:
        return db.query(models.DYNAMIC_TABLES[TABLE]).count()
    finally:
        db.close()


def _ledger(env, status=None):
    db = env["SessionLocal"]()
    try:
        q = db.query(models.FileIngestionCheckpoint)
        if status:
            q = q.filter(models.FileIngestionCheckpoint.status == status)
        return q.all()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# §1 mtime 변환 — tier 1의 `=` 비교가 서 있는 바닥
# ---------------------------------------------------------------------------

def test_mtime_conversion_is_exact_and_reproducible():
    """부동소수 왕복이 아니라 정수 산술 — 같은 입력은 언제나 같은 값.

    이게 깨지면 tier 1은 **조용히** 항상 miss한다(에러 없이 빠른 경로만 사라진다)."""
    ns = 1786580977459357500  # NTFS의 100ns 눈금 (뒤가 00으로 안 끝난다)
    a = ingestion_checkpoint.mtime_ns_to_datetime(ns)
    b = ingestion_checkpoint.mtime_ns_to_datetime(ns)
    assert a == b
    assert a.tzinfo is timezone.utc, "naive datetime 금지 (SCHEMA_CANON R5)"
    assert a.microsecond == 459357, "마이크로초로 «절단»(반올림 아님)"
    # 1ns 차이는 같은 마이크로초로 절단된다 — PG가 저장할 수 있는 해상도가 그것이다.
    assert ingestion_checkpoint.mtime_ns_to_datetime(ns + 1) == a
    # 1us 차이는 반드시 갈라진다.
    assert ingestion_checkpoint.mtime_ns_to_datetime(ns + 1000) == a + timedelta(microseconds=1)


def test_read_file_stat_returns_none_for_a_missing_file(tmp_path):
    """stat 실패는 예외가 아니라 None — tier 1이 miss하고 기존 경로로 떨어진다."""
    assert ingestion_checkpoint.read_file_stat(str(tmp_path / "nope.csv")) is None


# ---------------------------------------------------------------------------
# §2 tier 1 — 켜짐/꺼짐, 그리고 고장 주입
# ---------------------------------------------------------------------------

# 🔴 아래 테스트들은 전부 **같은 경로를 두 번** 처리한다. 그러려면 첫 처리가 파일을
# archives/로 치우지 않아야 한다 — 안 그러면 두 번째 호출은 「파일이 없어서」 0을
# 세고, 그 0이 「tier 1이 잘 돌았다」와 구별되지 않는다(초록 대리지표). 실제로 이
# 파일을 처음 돌렸을 때 그 함정에 걸렸고, 아래 고장 주입 테스트가 그것을 잡아냈다.

def test_tier1_skips_without_reading_the_file(env):
    """같은 경로·같은 stat = 해시 **0회**. 스킵이 싸다는 것이 이 기능의 전부다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a.csv", _csv(3))
    first = env["process"](p)
    assert first["hashes"] == 1 and first["ingests"] == 1

    second = env["process"](p)
    assert os.path.exists(p), "픽스처 전제: 파일이 제자리에 있어야 스킵을 잰 것이 된다"
    assert second["hashes"] == 0, "tier 1 적중인데 파일을 읽었다"
    assert second["ingests"] == 0
    assert _rows(env) == 3


def test_tier1_off_falls_back_to_full_hashing(env):
    """🔴 고장 주입 — 스위치를 끄면 같은 검사가 «빨개져야» 한다.

    위 테스트의 초록은 「스윕이 아무 일도 안 했다」로도 설명된다. 이 테스트가
    그 대안 설명을 지운다: 해시는 돌고(=파일에 도달했고) 적재만 안 한다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a.csv", _csv(3))
    env["process"](p)

    env["settings"](archive_processed_files=False, dedup_by_path_stat=False)
    m = env["process"](p)
    assert m["hashes"] == 1, "tier 1을 껐는데 해시가 안 돌았다 = 다른 이유로 스킵된 것"
    assert m["ingests"] == 0, "tier 2(내용 시그니처)가 여전히 최종 권위여야 한다"
    assert _rows(env) == 3


def test_disabling_dedup_by_signature_disables_tier1_too(env):
    """전역 강제 재처리 스위치가 tier 1에 조용히 무력해지면 안 된다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a.csv", _csv(3))
    env["process"](p)

    env["settings"](archive_processed_files=False, dedup_by_signature=False)
    m = env["process"](p)
    assert m["hashes"] == 1
    assert m["ingests"] == 1, "dedup_by_signature=false인데 재적재되지 않았다"


def test_changed_content_at_the_same_path_is_reingested(env):
    """tier 1이 삼키면 안 되는 유일한 경우 — 경로는 같고 내용이 바뀌었다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a.csv", _csv(3))
    env["process"](p)
    assert _rows(env) == 3

    _write(env["raws"] / "a.csv", _csv(7))
    m = env["process"](p)
    assert m["hashes"] == 1 and m["ingests"] == 1
    assert _rows(env) == 7


def test_tier1_never_matches_a_row_written_before_the_columns_existed(env):
    """NULL 계약 — file_mtime/file_size가 NULL인 행은 tier 1에 **절대** 안 걸린다.

    마이그레이션 이전에 적힌 모든 행이 이 모양이다. 걸리면 「내용을 확인한 적 없는
    파일을 확인했다고 치는」 방향으로 진다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a.csv", _csv(3))
    env["process"](p)
    db = env["SessionLocal"]()
    try:
        row = db.query(models.FileIngestionCheckpoint).one()
        row.file_mtime = None
        row.file_size = None
        db.commit()
    finally:
        db.close()

    m = env["process"](p)
    assert m["hashes"] == 1, "NULL stat 행에 tier 1이 적중했다"
    assert m["ingests"] == 0, "tier 2는 여전히 내용으로 막아야 한다"


# ---------------------------------------------------------------------------
# §3 파일을 옮기지 않는 모드
# ---------------------------------------------------------------------------

def test_success_leaves_the_file_in_place(env):
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a.csv", _csv(3))
    env["process"](p)
    assert os.path.exists(p), "성공한 파일이 옮겨졌다"
    assert os.listdir(env["ws"] / "archives") == []
    assert _rows(env) == 3


def test_failure_leaves_the_file_in_place_and_the_reason_in_the_ledger(env):
    """🔴 `err/` 폴더가 들고 있던 사실이 어디로 갔는지 — 원장이다.

    운영자가 「무엇이 왜 실패했나」를 여전히 답할 수 있어야 한다:
    원장 행이 **어느 파일**인지(filepath)와 **왜**(note)를, FileIngestionLog가
    트레이스를 든다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "bad.csv", "nothing,here\n1,2\n")
    env["process"](p)

    assert os.path.exists(p), "실패한 파일이 옮겨졌다"
    assert os.listdir(env["ws"] / "err") == []

    failed = _ledger(env, "FAILED")
    assert len(failed) == 1, "실패 사실이 원장에 없다 — err/ 폴더도 없는데 아무 데도 없다"
    assert os.path.normcase(failed[0].filepath) == os.path.normcase(os.path.abspath(p))
    assert failed[0].note and "[failed]" in failed[0].note
    assert failed[0].file_size is not None and failed[0].file_mtime is not None

    db = env["SessionLocal"]()
    try:
        logs = db.query(models.FileIngestionLog).filter_by(status="FAILED").all()
        assert len(logs) == 1 and logs[0].error_message, "트레이스는 종전 자리에 그대로"
    finally:
        db.close()


def test_a_sealed_failure_is_not_retried_forever(env):
    """옮기지 않으면 스윕이 매번 다시 집어 온다 — 원장이 그 무한 재시도를 끊는다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "bad.csv", "nothing,here\n1,2\n")
    env["process"](p)

    again = env["process"](p)
    assert again["hashes"] == 0, "종결된 실패를 다시 읽었다"
    assert len(_ledger(env, "FAILED")) == 1, "실패 행이 늘었다(멱등성 위반)"


def test_a_repaired_file_is_picked_up_again(env):
    """봉인이 «영구»면 그것도 결함이다 — 파일을 고치면 stat이 바뀌어 다시 걸린다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "bad.csv", "nothing,here\n1,2\n")
    env["process"](p)
    assert len(_ledger(env, "FAILED")) == 1

    _write(env["raws"] / "bad.csv", _csv(4))
    m = env["process"](p)
    assert m["ingests"] == 1, "고친 파일이 다시 적재되지 않았다"
    assert _rows(env) == 4


def test_move_mode_is_untouched_by_default(env):
    """`.sample` 기본값 = 종전 동작. 설정 파일이 없어도 그대로여야 한다."""
    p = _write(env["raws"] / "a.csv", _csv(3))
    env["process"](p)
    assert not os.path.exists(p)
    assert os.listdir(env["ws"] / "archives") == ["a.csv"]


def test_tier1_hit_still_retries_a_move_that_failed_before(env):
    """🔴 tier 1 적중이 「아무것도 안 함」이 되면, 이동에 실패한 파일은 raws/에 영원히
    남는다(중첩 인제션이면 그 폴더째로). 적중해도 이동은 다시 시도한다."""
    p = _write(env["raws"] / "a.csv", _csv(3))
    moves = {"n": 0}
    real_move = directory_watcher.shutil.move

    def failing_move(src, dst):
        moves["n"] += 1
        if moves["n"] == 1:
            raise OSError("simulated locked file")
        return real_move(src, dst)

    directory_watcher.shutil.move = failing_move
    try:
        env["process"](p)
        assert os.path.exists(p), "픽스처 전제: 첫 이동이 실패해 파일이 남아야 한다"
        m = env["process"](p)
    finally:
        directory_watcher.shutil.move = real_move

    assert m["hashes"] == 0, "tier 1이 적중해야 한다(해시는 다시 돌 필요 없다)"
    assert not os.path.exists(p), "적중 뒤에도 이동이 재시도되지 않았다"


# ---------------------------------------------------------------------------
# §4 강제 재처리 3경로가 새 경로에서도 산다
# ---------------------------------------------------------------------------

def test_force_token_bypasses_tier1(env):
    """`__force__`는 tier 1보다 «앞»에서 빠져나가야 한다 — 뒤였다면 해시조차 안 돈다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a__force__.csv", _csv(3))
    env["process"](p)
    m = env["process"](p)
    assert m["hashes"] == 1, "__force__ 파일이 tier 1에 삼켜졌다"
    assert m["ingests"] == 1


def test_admin_retry_records_the_tier1_key(env):
    """관리자 재시도도 원장의 tier-1 열쇠를 갱신한다 — 안 그러면 다음 스윕이 또 해시한다."""
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a.csv", _csv(3))
    env["process"](p)

    db = env["SessionLocal"]()
    try:
        log = models.FileIngestionLog(filename="a.csv", filepath=os.path.abspath(p),
                                      table_name=TABLE, status="FAILED", retry_count=0)
        db.add(log)
        db.commit()
        assert env["handler"].process_archived_file_sync(log, db) is True
    finally:
        db.close()

    row = _ledger(env, "DONE")[0]
    st = ingestion_checkpoint.read_file_stat(os.path.abspath(p))
    assert row.file_size == st[1]
    # 저장된 값을 «시각으로» 비교한다. SQLite의 DateTime은 tzinfo를 떼고 돌려주고
    # PostgreSQL은 KST로 붙여 돌려준다 — 두 백엔드에서 다른 객체가 같은 순간을
    # 뜻하므로, 객체 동일성으로 재면 한쪽에서만 빨개진다.
    stored = row.file_mtime
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    assert stored == st[0]
    # 무엇보다 «행동»으로 확인한다: 이 열쇠로 tier 1이 실제로 적중하는가.
    db = env["SessionLocal"]()
    try:
        assert ingestion_checkpoint.find_terminal_by_path_stat(
            db, TABLE, os.path.abspath(p), st) is not None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# §5 같은 내용이 다른 경로에 — 원장이 새 위치를 「기억」하는가
# ---------------------------------------------------------------------------

def test_duplicate_content_at_a_new_path_is_skipped_and_recorded(env):
    """내용 시그니처가 최종 권위 — 적재는 안 하되 새 위치는 남긴다."""
    env["settings"](archive_processed_files=False)
    content = _csv(3)
    a = _write(env["raws"] / "a.csv", content)
    env["process"](a)
    assert _rows(env) == 3

    b = _write(env["raws"] / "b.csv", content)
    m = env["process"](b)
    assert m["hashes"] == 1, "새 경로는 tier 1을 miss하고 해시로 판정해야 한다"
    assert m["ingests"] == 0, "내용이 같은데 재적재됐다"
    row = _ledger(env, "DONE")[0]
    assert "b.csv" in (row.note or ""), "사본의 위치가 아무 데도 안 남았다"


def test_the_ledger_adopts_the_survivor_when_the_original_is_gone(env):
    """원본이 사라지면 새 위치를 «채택»한다 — 그래야 반복 해시가 멈춘다."""
    env["settings"](archive_processed_files=False)
    content = _csv(3)
    a = _write(env["raws"] / "a.csv", content)
    env["process"](a)
    os.remove(a)

    b = _write(env["raws"] / "b.csv", content)
    first = env["process"](b)
    assert first["hashes"] == 1 and first["ingests"] == 0
    second = env["process"](b)
    assert second["hashes"] == 0, "채택이 안 돼서 사본이 매 스윕 다시 해시된다"
