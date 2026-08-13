"""[P2] 오프셋 체크포인트 재개 + 파일 시그니처 dedup + 감사 결함 2건 검증.

결함 배경
---------
P1(heavy 레인)까지는 1,000행 청크로 적재하되 **진행 오프셋을 어디에도 남기지 않아**
재기동 시 99,999행(≈7분) 작업이 통째로 소실되고 파일을 처음부터 재처리했다.
동일 파일 재투입 방어도 없었다.

검증 범위
---------
- A. 시그니처(sha256) 산출 / 청크 커밋과 원자적인 오프셋 기록 / 중간 오프셋 재개
     / 재개 불가(총행수 불일치·파서 불일치·오프셋 손상) 시 0부터 재처리 + **명시 기록**
     / **멱등성**(강제 중간 재개 후 행 수·bk 중복 0) / 스윕·heavy 레인 경로 동일 동작
- B. 동일 시그니처 SUCCESS 파일 skip(명시 기록·통지) + 강제 재처리 3경로 + 테이블별 격리
- C. audit_cache total_count 누적 의미론(#10) / 감사 값 길이 상한·절단 표기

테이블명은 사용자 config에 실존 불가능한 `p2_test_*` 접두 사용 (교훈 파일).
"""

import json
import os
import sys
import threading

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
from directory_watcher import IngestionHandler, WorkspaceWatcher
from database.database import Base
from database import crud, models

PARTS_INFO = {
    "business_key": "part_no",
    "column_types": {"part_no": "string", "category": "string", "stock_qty": "number"},
    "display_columns": ["part_no", "category", "stock_qty"],
}

TABLE = "p2_test_parts"
ALT_TABLE = "p2_test_alt"


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return str(path)


def _csv(n, prefix="P"):
    lines = ["part_no,category,stock_qty"]
    for i in range(1, n + 1):
        lines.append(f"{prefix}-{i},Cap,{i}")
    return "\n".join(lines) + "\n"


@pytest.fixture
def p2_env(tmp_path, monkeypatch):
    """실 DB(SQLite in-memory) + 워처 핸들러 환경.

    SessionLocal은 **팩토리**로 주입한다 — 체크포인트/청크가 각자 세션을 열고 닫는
    실제 동작(세션 경계 = 트랜잭션 경계)을 그대로 재현하기 위함. StaticPool로 커넥션은
    하나를 공유하므로 in-memory DB 내용은 세션 간 유지된다.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    table_config = {TABLE: dict(PARTS_INFO), ALT_TABLE: dict(PARTS_INFO)}
    models.init_dynamic_models(table_config)
    crud.TABLE_CONFIG.update(table_config)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    models.ensure_ingestion_checkpoint_table(engine)

    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: table_config)
    monkeypatch.setattr(directory_watcher, "SessionLocal", TestingSessionLocal)
    # ingestion_settings.json 부재 상태(전 항목 기본값)에서 출발 — 개별 테스트가 필요 시 덮어쓴다.
    settings_path = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings_path))

    def make_handler(table_name=TABLE, name=None):
        ws = tmp_path / (name or f"ws_{table_name}")
        (ws / "raws").mkdir(parents=True, exist_ok=True)
        (ws / "archives").mkdir(exist_ok=True)
        (ws / "err").mkdir(exist_ok=True)
        handler = IngestionHandler(
            workspace_path=str(ws),
            config_path=None,
            archives_path=str(ws / "archives"),
            default_table_name=table_name,
        )
        return ws, handler

    env = {
        "engine": engine,
        "SessionLocal": TestingSessionLocal,
        "make_handler": make_handler,
        "settings_path": settings_path,
        "table_config": table_config,
        "tmp_path": tmp_path,
    }
    yield env

    Base.metadata.drop_all(bind=engine)


def _rows(env, table=TABLE):
    db = env["SessionLocal"]()
    try:
        model = models.DYNAMIC_TABLES[table]
        return db.query(model).all()
    finally:
        db.close()


def _checkpoint(env, table=TABLE, signature=None):
    db = env["SessionLocal"]()
    try:
        q = db.query(models.FileIngestionCheckpoint).filter(
            models.FileIngestionCheckpoint.table_name == table
        )
        if signature:
            q = q.filter(models.FileIngestionCheckpoint.file_signature == signature)
        return q.one_or_none()
    finally:
        db.close()


def _ingestion_logs(env):
    db = env["SessionLocal"]()
    try:
        return db.query(models.FileIngestionLog).order_by(models.FileIngestionLog.id).all()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# §B-1 파일 시그니처
# ---------------------------------------------------------------------------

def test_signature_is_content_addressed_and_stable(tmp_path):
    a = _write(tmp_path / "a.csv", _csv(5))
    b = _write(tmp_path / "b.csv", _csv(5))   # 다른 이름, 같은 내용
    c = _write(tmp_path / "c.csv", _csv(6))   # 다른 내용

    sig_a = ingestion_checkpoint.compute_file_signature(a)
    assert sig_a == ingestion_checkpoint.compute_file_signature(a)  # 결정적
    assert sig_a == ingestion_checkpoint.compute_file_signature(b)  # 이름 무관·내용 기준
    assert sig_a != ingestion_checkpoint.compute_file_signature(c)

    algo, size, digest = sig_a.split(":")
    assert algo == "sha256"
    assert int(size) == os.path.getsize(a)
    assert len(digest) == 64


def test_signature_returns_none_when_unreadable(tmp_path):
    """읽기 불가 파일은 None → 호출자는 체크포인트/dedup을 끄고 기존 동작으로 처리."""
    assert ingestion_checkpoint.compute_file_signature(str(tmp_path / "nope.csv")) is None


# ---------------------------------------------------------------------------
# §A 체크포인트 기록 · 재개
# ---------------------------------------------------------------------------

def test_checkpoint_recorded_and_marked_done_after_success(p2_env):
    ws, handler = p2_env["make_handler"]()
    p = _write(ws / "raws" / "d1.csv", _csv(3))
    sig = ingestion_checkpoint.compute_file_signature(p)

    handler.process_with_retry(p, delay=0.01)

    ck = _checkpoint(p2_env, signature=sig)
    assert ck is not None
    assert ck.status == ingestion_checkpoint.STATUS_DONE
    assert ck.processed_rows == 3
    assert ck.total_rows == 3
    assert ck.source_kind == "std"
    assert len(_rows(p2_env)) == 3


def test_crash_mid_file_keeps_committed_offset_then_resumes(p2_env, monkeypatch):
    """[핵심] 청크 커밋과 오프셋 기록의 원자성 + 크래시 후 이어받기.

    청크 크기(1,000)를 넘는 1,500행 파일로 2개 청크를 만든 뒤 두 번째 청크에서
    크래시를 시뮬레이션한다. 기대:
      1) 1청크(1,000행)는 커밋되고 오프셋도 정확히 1,000으로 남는다(원자성).
      2) 실패한 2청크의 행은 적재되지 않는다(오프셋이 앞서 나가지 않음).
      3) 같은 파일을 다시 처리하면 1,000행부터 재개해 나머지 500행만 업서트한다.
    """
    ws, handler = p2_env["make_handler"]()
    content = _csv(1500)
    p = _write(ws / "raws" / "big.csv", content)
    sig = ingestion_checkpoint.compute_file_signature(p)

    real_apply = crud.apply_batch_updates
    state = {"calls": 0}

    def exploding_apply(db, table_name, batch_obj):
        state["calls"] += 1
        if state["calls"] == 2:
            raise RuntimeError("simulated crash mid-file")
        return real_apply(db, table_name, batch_obj)

    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates", exploding_apply)
    handler.process_with_retry(p, delay=0.01)

    ck = _checkpoint(p2_env, signature=sig)
    assert ck is not None
    # 상태는 FAILED다 (2026-08-13 이전에는 IN_PROGRESS였다). 이 예외 핸들러가 돌았다는
    # 것은 종전 기준으로 「파일이 err/로 갔다」 = 자동 재시도 안 함이라는 뜻이고, 파일을
    # 옮기지 않는 모드에서는 그 사실을 폴더가 아니라 원장이 들어야 한다. 프로세스가
    # 통째로 죽어 이 핸들러가 못 돈 경우에만 IN_PROGRESS로 남고, 그때는 다음 스윕이
    # 자동으로 이어받는다 — P2 재개의 원래 대상이 그쪽이다.
    assert ck.status == ingestion_checkpoint.STATUS_FAILED
    # 🔴 종결 표시가 재개 오프셋을 지우지 않는다 — 아래 재개가 그것을 그대로 쓴다.
    assert ck.processed_rows == 1000, "커밋된 행 수와 기록된 오프셋이 일치해야 한다"
    assert len(_rows(p2_env)) == 1000

    # 실패 파일은 err/로 이동했으므로 같은 내용을 다시 투입해 재개를 검증한다.
    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates", real_apply)
    applied = []
    original = directory_watcher.crud.apply_batch_updates

    def spy(db_, t, b):
        applied.append(len(b.updates))
        return original(db_, t, b)

    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates", spy)
    p2 = _write(ws / "raws" / "big_again.csv", content)
    handler.process_with_retry(p2, delay=0.01)

    assert applied == [500], f"재개 후 남은 500행만 적재되어야 한다 (실제: {applied})"
    rows = _rows(p2_env)
    bks = [r.business_key_val for r in rows]
    assert len(rows) == 1500
    assert len(set(bks)) == 1500, "bk 중복 0"
    ck2 = _checkpoint(p2_env, signature=sig)
    assert ck2.status == ingestion_checkpoint.STATUS_DONE


def test_resume_skips_already_committed_rows(p2_env):
    """중간 오프셋에서 강제 재개 → 이미 커밋된 선두 행은 업서트 대상에서 제외된다."""
    ws, handler = p2_env["make_handler"]()
    content = _csv(6)
    p = _write(ws / "raws" / "resume.csv", content)
    sig = ingestion_checkpoint.compute_file_signature(p)

    # 앞 2행만 적재된 상태를 인위적으로 만든다 (프로세스가 2행 커밋 직후 죽은 상황)
    db = p2_env["SessionLocal"]()
    try:
        db.add(models.FileIngestionCheckpoint(
            table_name=TABLE, file_signature=sig, filename="resume.csv",
            filepath=p, source_kind="std", total_rows=6, processed_rows=2,
            chunk_index=1, status=ingestion_checkpoint.STATUS_IN_PROGRESS,
        ))
        db.commit()
    finally:
        db.close()

    applied = []
    real_apply = crud.apply_batch_updates

    def spy(db_, table_name, batch_obj):
        applied.extend([u.business_key_val for u in batch_obj.updates])
        return real_apply(db_, table_name, batch_obj)

    import unittest.mock as _mock
    with _mock.patch.object(directory_watcher.crud, "apply_batch_updates", spy):
        handler.process_with_retry(p, delay=0.01)

    # 선두 2행(P-1, P-2)은 재적재되지 않고 나머지 4행만 업서트된다.
    assert applied == ["P-3", "P-4", "P-5", "P-6"]
    ck = _checkpoint(p2_env, signature=sig)
    assert ck.status == ingestion_checkpoint.STATUS_DONE


def test_resume_note_is_recorded_in_log_and_notification(p2_env):
    """재개 사실이 로그·FileIngestionLog·완료 통지 detail 세 곳에 명시된다(조용한 재개 금지)."""
    ws, handler = p2_env["make_handler"]()
    notified = []
    handler.on_file_processed_callback = lambda t, f, s, d: notified.append((t, f, s, d))
    p = _write(ws / "raws" / "resume2.csv", _csv(4))
    sig = ingestion_checkpoint.compute_file_signature(p)

    db = p2_env["SessionLocal"]()
    try:
        db.add(models.FileIngestionCheckpoint(
            table_name=TABLE, file_signature=sig, filename="resume2.csv", filepath=p,
            source_kind="std", total_rows=4, processed_rows=1, chunk_index=1,
            status=ingestion_checkpoint.STATUS_IN_PROGRESS,
        ))
        db.commit()
    finally:
        db.close()

    handler.process_with_retry(p, delay=0.01)

    assert notified and notified[0][2] == "SUCCESS"
    assert "[resume]" in (notified[0][3] or "")
    logs = _ingestion_logs(p2_env)
    assert logs[-1].status == "SUCCESS"
    assert "[resume]" in (logs[-1].error_message or "")


@pytest.mark.parametrize("mutate,expected_reason", [
    ({"total_rows": 99}, "총 행 수 불일치"),
    ({"source_kind": "pipeline:other.py::Other"}, "파서 정체성 불일치"),
    ({"processed_rows": 9999}, "오프셋 손상"),
    ({"processed_rows": -5}, "오프셋 손상"),
])
def test_unusable_checkpoint_restarts_from_zero_with_explicit_reason(p2_env, mutate, expected_reason):
    """재개 불가 조건은 **조용히** 처음부터 돌지 않는다 — 사유가 detail/이력에 남는다."""
    ws, handler = p2_env["make_handler"]()
    notified = []
    handler.on_file_processed_callback = lambda t, f, s, d: notified.append(d)
    p = _write(ws / "raws" / "bad.csv", _csv(4))
    sig = ingestion_checkpoint.compute_file_signature(p)

    base = dict(
        table_name=TABLE, file_signature=sig, filename="bad.csv", filepath=p,
        source_kind="std", total_rows=4, processed_rows=2, chunk_index=1,
        status=ingestion_checkpoint.STATUS_IN_PROGRESS,
    )
    base.update(mutate)
    db = p2_env["SessionLocal"]()
    try:
        db.add(models.FileIngestionCheckpoint(**base))
        db.commit()
    finally:
        db.close()

    handler.process_with_retry(p, delay=0.01)

    detail = notified[0] or ""
    assert "[resume-abort]" in detail
    assert expected_reason in detail
    # 처음부터 재처리했으므로 전 행이 적재된다
    assert len(_rows(p2_env)) == 4
    logs = _ingestion_logs(p2_env)
    assert "[resume-abort]" in (logs[-1].error_message or "")


def test_resume_is_idempotent_no_duplicate_rows(p2_env):
    """[핵심] 재개 지점이 어긋나도 bk 업서트라 중복 행이 생기지 않는다.

    같은 파일을 (1) 전량 적재 → (2) 오프셋을 인위적으로 되돌려 중간 재개 →
    (3) 오프셋 0으로 되돌려 전량 재적재. 세 번 모두 후 행 수는 원본 행 수와 같아야 하고
    business key 중복이 0이어야 한다.
    """
    ws, handler = p2_env["make_handler"]()
    n = 7
    content = _csv(n)

    def drop_and_process(fname):
        p = _write(ws / "raws" / fname, content)
        handler.process_with_retry(p, delay=0.01)
        return ingestion_checkpoint.compute_file_signature(str(ws / "archives" / fname))

    sig = drop_and_process("idem1.csv")
    assert len(_rows(p2_env)) == n

    for forced_offset in (3, 0):
        db = p2_env["SessionLocal"]()
        try:
            db.query(models.FileIngestionCheckpoint).filter(
                models.FileIngestionCheckpoint.file_signature == sig
            ).update({"processed_rows": forced_offset,
                      "status": ingestion_checkpoint.STATUS_IN_PROGRESS},
                     synchronize_session=False)
            db.commit()
        finally:
            db.close()

        p = _write(ws / "raws" / f"idem_{forced_offset}.csv", content)
        handler.process_with_retry(p, delay=0.01)

        rows = _rows(p2_env)
        bks = [r.business_key_val for r in rows]
        assert len(rows) == n, f"offset={forced_offset}: 행 수 {len(rows)} != {n}"
        assert len(set(bks)) == len(bks), f"offset={forced_offset}: bk 중복 발생 {bks}"


def test_checkpoint_applies_on_sweep_path(p2_env):
    """스윕(재기동 캐치업) 경로도 같은 라우팅을 타므로 체크포인트가 동일하게 동작한다."""
    ws, handler = p2_env["make_handler"]()
    p = _write(ws / "raws" / "sweep.csv", _csv(3))
    sig = ingestion_checkpoint.compute_file_signature(p)

    watcher = WorkspaceWatcher(str(p2_env["tmp_path"]))
    raw_abs = os.path.abspath(str(ws / "raws"))
    watcher.handlers_by_raw_path[raw_abs] = handler
    processed = watcher.sweep_existing_files([raw_abs])

    assert processed == 1
    ck = _checkpoint(p2_env, signature=sig)
    assert ck is not None and ck.status == ingestion_checkpoint.STATUS_DONE
    assert len(_rows(p2_env)) == 3


def test_checkpoint_applies_on_heavy_lane_path(p2_env):
    """heavy 레인(별도 워커 스레드)도 process_with_retry를 그대로 호출 → 동일 동작."""
    ws, handler = p2_env["make_handler"]()
    lane = directory_watcher.HeavyIngestionLane()
    handler.heavy_lane = lane
    # 임계를 0.000001MB로 낮춰 모든 파일을 heavy로 라우팅
    p2_env["settings_path"].write_text(json.dumps({"heavy_file_mb": 0.000001}), encoding="utf-8")

    p = _write(ws / "raws" / "heavy.csv", _csv(4))
    sig = ingestion_checkpoint.compute_file_signature(p)

    done = threading.Event()
    handler.on_file_processed_callback = lambda *a: done.set()
    handler._handle_event(p)
    assert done.wait(timeout=15), "heavy 레인 작업이 완료되지 않음"
    lane.stop()

    ck = _checkpoint(p2_env, signature=sig)
    assert ck is not None and ck.status == ingestion_checkpoint.STATUS_DONE
    assert ck.processed_rows == 4


def test_resume_disabled_by_setting_restarts_from_zero(p2_env):
    ws, handler = p2_env["make_handler"]()
    p2_env["settings_path"].write_text(json.dumps({"resume_from_checkpoint": False}), encoding="utf-8")
    p = _write(ws / "raws" / "noresume.csv", _csv(4))
    sig = ingestion_checkpoint.compute_file_signature(p)

    db = p2_env["SessionLocal"]()
    try:
        db.add(models.FileIngestionCheckpoint(
            table_name=TABLE, file_signature=sig, filename="noresume.csv", filepath=p,
            source_kind="std", total_rows=4, processed_rows=3, chunk_index=1,
            status=ingestion_checkpoint.STATUS_IN_PROGRESS,
        ))
        db.commit()
    finally:
        db.close()

    notified = []
    handler.on_file_processed_callback = lambda t, f, s, d: notified.append(d)
    handler.process_with_retry(p, delay=0.01)

    assert "[resume-abort]" in (notified[0] or "")
    assert len(_rows(p2_env)) == 4


# ---------------------------------------------------------------------------
# §B dedup
# ---------------------------------------------------------------------------

def test_duplicate_signature_is_skipped_with_explicit_record(p2_env):
    ws, handler = p2_env["make_handler"]()
    notified = []
    handler.on_file_processed_callback = lambda t, f, s, d: notified.append((f, s, d))

    content = _csv(3)
    p1 = _write(ws / "raws" / "first.csv", content)
    handler.process_with_retry(p1, delay=0.01)

    applied = []
    import unittest.mock as _mock
    real_apply = crud.apply_batch_updates

    def spy(db_, t, b):
        applied.append(t)
        return real_apply(db_, t, b)

    p2 = _write(ws / "raws" / "second.csv", content)   # 다른 이름, 같은 내용
    with _mock.patch.object(directory_watcher.crud, "apply_batch_updates", spy):
        handler.process_with_retry(p2, delay=0.01)

    # 1) 적재 자체가 일어나지 않았다
    assert applied == []
    # 2) 무음이 아니다 — 통지 detail + FileIngestionLog(status=SKIPPED)
    assert notified[-1][1] == "SUCCESS"           # 실패가 아님을 수신부에 정확히 전달
    assert "[dedup-skip]" in (notified[-1][2] or "")
    logs = _ingestion_logs(p2_env)
    assert logs[-1].status == "SKIPPED"
    assert "[dedup-skip]" in (logs[-1].error_message or "")
    # 3) 파일은 raws/에 남지 않는다 (스윕 무한 재시도 방지)
    assert not os.path.exists(p2)
    assert os.path.exists(str(ws / "archives" / "second.csv"))


def test_dedup_is_scoped_per_table(p2_env):
    """같은 내용이라도 다른 테이블 대상이면 스킵하지 않는다."""
    ws_a, handler_a = p2_env["make_handler"](TABLE, name="ws_a")
    ws_b, handler_b = p2_env["make_handler"](ALT_TABLE, name="ws_b")
    content = _csv(2)

    handler_a.process_with_retry(_write(ws_a / "raws" / "x.csv", content), delay=0.01)
    handler_b.process_with_retry(_write(ws_b / "raws" / "x.csv", content), delay=0.01)

    assert len(_rows(p2_env, TABLE)) == 2
    assert len(_rows(p2_env, ALT_TABLE)) == 2


def test_different_content_is_not_skipped(p2_env):
    ws, handler = p2_env["make_handler"]()
    handler.process_with_retry(_write(ws / "raws" / "a.csv", _csv(2)), delay=0.01)
    handler.process_with_retry(_write(ws / "raws" / "b.csv", _csv(4)), delay=0.01)
    assert len(_rows(p2_env)) == 4


def test_force_token_in_filename_bypasses_dedup(p2_env):
    ws, handler = p2_env["make_handler"]()
    content = _csv(3)
    handler.process_with_retry(_write(ws / "raws" / "f1.csv", content), delay=0.01)

    applied = []
    import unittest.mock as _mock
    real_apply = crud.apply_batch_updates

    def spy(db_, t, b):
        applied.append(len(b.updates))
        return real_apply(db_, t, b)

    with _mock.patch.object(directory_watcher.crud, "apply_batch_updates", spy):
        handler.process_with_retry(_write(ws / "raws" / "f1__force__.csv", content), delay=0.01)

    assert applied == [3], "강제 재처리 파일은 dedup을 우회해 전량 재적재되어야 한다"


def test_dedup_can_be_disabled_globally(p2_env):
    ws, handler = p2_env["make_handler"]()
    content = _csv(3)
    handler.process_with_retry(_write(ws / "raws" / "g1.csv", content), delay=0.01)

    p2_env["settings_path"].write_text(json.dumps({"dedup_by_signature": False}), encoding="utf-8")

    applied = []
    import unittest.mock as _mock
    real_apply = crud.apply_batch_updates

    def spy(db_, t, b):
        applied.append(len(b.updates))
        return real_apply(db_, t, b)

    with _mock.patch.object(directory_watcher.crud, "apply_batch_updates", spy):
        handler.process_with_retry(_write(ws / "raws" / "g2.csv", content), delay=0.01)

    assert applied == [3]


def test_admin_retry_path_bypasses_dedup_and_reingests(p2_env):
    """관리자 재시도(process_archived_file_sync)는 명시적 재처리 — dedup skip을 타지 않는다."""
    ws, handler = p2_env["make_handler"]()
    content = _csv(3)
    p = _write(ws / "raws" / "retry.csv", content)
    handler.process_with_retry(p, delay=0.01)
    archived = str(ws / "archives" / "retry.csv")
    assert os.path.exists(archived)

    applied = []
    import unittest.mock as _mock
    real_apply = crud.apply_batch_updates

    def spy(db_, t, b):
        applied.append(len(b.updates))
        return real_apply(db_, t, b)

    db = p2_env["SessionLocal"]()
    try:
        log_entry = models.FileIngestionLog(
            filename="retry.csv", filepath=archived, table_name=TABLE,
            status="PENDING", error_message=None, retry_count=0,
        )
        db.add(log_entry)
        db.commit()
        with _mock.patch.object(directory_watcher.crud, "apply_batch_updates", spy):
            ok = handler.process_archived_file_sync(log_entry, db)
        assert ok is True
    finally:
        db.close()

    # 이미 DONE 상태였으므로 0부터 전량 재적재 (사용자가 굳이 다시 눌렀다는 의미)
    assert applied == [3]
    assert len(_rows(p2_env)) == 3   # 업서트라 행 수는 그대로


# ---------------------------------------------------------------------------
# §C-1 audit_cache total_count 누적 의미론 (보드 이슈 #10 / QA D-1)
# ---------------------------------------------------------------------------

def _log(tx, i):
    from datetime import datetime, timezone
    return {
        "id": 0, "table_name": "t", "row_id": f"r{i}", "column_name": "c",
        "old_value": None, "new_value": str(i), "source_name": "s",
        "updated_by": "u", "transaction_id": tx, "business_key": f"bk{i}",
        "timestamp": datetime.now(timezone.utc),
    }


@pytest.fixture
def cache():
    from audit_cache import AuditLogCache
    c = AuditLogCache()
    c.is_loaded = True
    return c


def test_multi_message_same_tx_accumulates_total_count(cache):
    """[#10] 같은 tx가 여러 target-table 메시지로 나뉘어 도착해도 총계가 덮어써지지 않는다."""
    cache.add_logs_batch([_log("chain_1", i) for i in range(3)], 600)
    cache.add_logs_batch([_log("chain_1", i) for i in range(100, 102)], 50)

    group = next(g for g in cache.groups if g["transaction_id"] == "chain_1")
    assert group["total_count"] == 650   # 종전 SET 의미론이면 50 (과소 표기)


def test_single_message_total_count_is_used_as_is(cache):
    """절단된 메시지(로그 3건, 실제 500건)의 총계는 실건수를 따른다."""
    cache.add_logs_batch([_log("tx_a", i) for i in range(3)], 500)
    group = next(g for g in cache.groups if g["transaction_id"] == "tx_a")
    assert group["total_count"] == 500
    assert len(group["logs"]) == 3


def test_without_total_count_falls_back_to_len(cache):
    """override 미전달(crud 내부 호출) 경로는 종전과 동일하게 len(logs) 누적."""
    cache.add_logs_batch([_log("tx_b", i) for i in range(4)])
    cache.add_logs_batch([_log("tx_b", i) for i in range(10, 13)])
    group = next(g for g in cache.groups if g["transaction_id"] == "tx_b")
    assert group["total_count"] == 7


def test_multi_tx_batch_ignores_message_total_count(cache):
    """한 메시지에 여러 tx가 섞이면 기여분을 귀속시킬 수 없으므로 len(logs)로 폴백한다."""
    cache.add_logs_batch([_log("tx_x", 1), _log("tx_y", 2), _log("tx_y", 3)], 999)
    gx = next(g for g in cache.groups if g["transaction_id"] == "tx_x")
    gy = next(g for g in cache.groups if g["transaction_id"] == "tx_y")
    assert gx["total_count"] == 1
    assert gy["total_count"] == 2


def test_cache_log_list_still_capped_at_500(cache):
    cache.add_logs_batch([_log("tx_cap", i) for i in range(600)], 600)
    group = next(g for g in cache.groups if g["transaction_id"] == "tx_cap")
    assert len(group["logs"]) == 500
    assert group["total_count"] == 600


# ---------------------------------------------------------------------------
# §C-2 감사 값 길이 상한 (crud.py old_value/new_value)
# ---------------------------------------------------------------------------

def test_truncate_audit_value_marks_truncation():
    from event_constants import MAX_AUDIT_VALUE_CHARS, truncate_audit_value

    small, cut = truncate_audit_value("x" * 10)
    assert cut is False and small == "x" * 10

    big, cut = truncate_audit_value("y" * (MAX_AUDIT_VALUE_CHARS + 500))
    assert cut is True
    assert big.startswith("y" * 100)
    assert "truncated" in big
    assert str(MAX_AUDIT_VALUE_CHARS + 500) in big     # 원래 길이가 보존된다
    assert len(big) < MAX_AUDIT_VALUE_CHARS + 100      # 상한 + 마커 수준으로 고정

    # 숫자/불리언/None은 그대로
    for v in (1, 3.5, True, None):
        out, cut = truncate_audit_value(v)
        assert out == v and cut is False


def test_truncate_audit_value_handles_containers():
    from event_constants import MAX_AUDIT_VALUE_CHARS, truncate_audit_value

    small, cut = truncate_audit_value({"a": 1})
    assert cut is False and small == {"a": 1}

    big, cut = truncate_audit_value(["z" * 200] * 100)
    assert cut is True
    assert isinstance(big, str) and "truncated" in big


def test_create_audit_log_caps_both_values(p2_env):
    from event_constants import MAX_AUDIT_VALUE_CHARS

    db = p2_env["SessionLocal"]()
    try:
        log_dict = crud.create_audit_log(
            db, TABLE, "row-1", "map_string",
            old_val="o" * 50000, new_val="n" * 50000,
            source="parser", user="tester", add_to_cache=False,
        )
        assert len(log_dict["old_value"]) < MAX_AUDIT_VALUE_CHARS + 100
        assert len(log_dict["new_value"]) < MAX_AUDIT_VALUE_CHARS + 100
        assert "truncated" in log_dict["old_value"]
        assert "truncated" in log_dict["new_value"]
    finally:
        db.close()


def test_ingestion_payload_stays_bounded_with_huge_cells(p2_env):
    """대형 텍스트 셀이 적재돼도 통지에 실리는 created_logs 총 크기가 상한 안에 든다."""
    from event_constants import MAX_AUDIT_VALUE_CHARS, MAX_NOTIFY_CREATED_LOGS

    ws, handler = p2_env["make_handler"]()
    captured = {}
    handler.on_refresh_callback = lambda t, c, logs, total: captured.update(
        {"logs": logs, "total": total}
    )
    huge = "M" * 60000
    lines = ["part_no,category,stock_qty"]
    for i in range(1, 4):
        lines.append(f"P-{i},{huge},{i}")
    p = _write(ws / "raws" / "huge.csv", "\n".join(lines) + "\n")

    handler.process_with_retry(p, delay=0.01)

    logs = captured.get("logs") or []
    assert logs, "created_logs가 통지되어야 한다"
    assert len(logs) <= MAX_NOTIFY_CREATED_LOGS
    for l in logs:
        for key in ("old_value", "new_value"):
            v = l.get(key)
            if isinstance(v, str):
                assert len(v) < MAX_AUDIT_VALUE_CHARS + 100
