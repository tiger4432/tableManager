"""[Heavy Lane P1] 대형 파일 인제션 heavy 레인 분리 + 진행 스냅샷 검증.

결함 배경: 단일 observer 디스패치/스윕 스레드가 파일을 인라인 처리해 대형 파일 1개
(99,999행 ≈ 7분)가 인제션 전체를 HOL 차단했다.

- 임계 라우팅: ingestion_settings.json `heavy_file_mb`(기본 10MB) 크기 경계 + 핫리로드
- 순서 보존(경계 계약): 같은 워크스페이스 파일은 heavy 처리 중 후속 파일이 큐 후미로
  대기 — 두 레인이 같은 테이블을 동시에 업서트하지 않는다
- 교차 워크스페이스 격리: A 테이블 heavy 진행 중 B 테이블 소형 파일은 즉시 완료
- 스윕 경로도 동일 라우팅 (재기동 캐치업이 heavy 파일 주 발원지)
- active 스냅샷 레지스트리 + GET /admin/file-ingestion/active 형태

테이블명은 사용자 config에 실존 불가능한 `hvy_test_*` 접두 사용 (교훈 파일).
동시성 검증은 sleep 경합이 아닌 Event/락 기반 결정적 구성.
"""

import os
import sys
import json
import time
import threading

# Ensure server/parsers is in python path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import pytest

import directory_watcher
from directory_watcher import HeavyIngestionLane, IngestionHandler, WorkspaceWatcher
import ingestion_activity
from ingestion_activity import IngestionActivityRegistry


HVY_INFO = {
    "business_key": "part_no",
    "column_types": {"part_no": "string", "category": "string"},
    "display_columns": ["part_no", "category"],
}


def _wait_until(cond, timeout=5.0, interval=0.01):
    """조건 폴링 대기 (이벤트 후속 정리 등 짧은 창 검증용 — 결과는 결정적)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(interval)
    return cond()


def _make_workspace(base, name, files=None):
    """워크스페이스 구조 생성. files: {파일명: 크기(bytes)}. 반환: workspace 절대경로."""
    ws = base / name
    for sub in ("raws", "archives", "err"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    for fname, size in (files or {}).items():
        (ws / "raws" / fname).write_bytes(b"x" * size)
    return str(ws)


class FakeLane:
    """submit만 기록하는 레인 스텁 — 라우팅 결정 검증용 (실행은 테스트가 수동 호출)."""

    def __init__(self):
        self.jobs = []

    def submit(self, job):
        self.jobs.append(job)

    def run_all(self):
        while self.jobs:
            self.jobs.pop(0)()


@pytest.fixture
def inline_calls(monkeypatch):
    """process_with_retry를 no-op 기록기로 대체 — (스레드명, 파일명) 기록."""
    calls = []

    def fake_process(self, file_path, uploader="system", retries=3, delay=1.0):
        calls.append((threading.current_thread().name, os.path.basename(file_path)))

    monkeypatch.setattr(IngestionHandler, "process_with_retry", fake_process)
    return calls


# ---------------------------------------------------------------------------
# 1) 임계값 설정: 기본값 / 유효값 / 불량값 폴백 / 파일 변경 핫리로드
# ---------------------------------------------------------------------------

def test_heavy_threshold_default_when_settings_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        directory_watcher, "INGESTION_SETTINGS_PATH", str(tmp_path / "nope.json")
    )
    assert directory_watcher.get_heavy_threshold_bytes() == 10 * 1024 * 1024


def test_heavy_threshold_reads_and_hot_reloads_settings_file(tmp_path, monkeypatch):
    settings = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings))

    settings.write_text(json.dumps({"heavy_file_mb": 1}), encoding="utf-8")
    assert directory_watcher.get_heavy_threshold_bytes() == 1 * 1024 * 1024

    # 파일 재기록 → 다음 호출(=다음 파일 이벤트)부터 반영 (파일 경계 핫리로드)
    settings.write_text(json.dumps({"heavy_file_mb": 2.5}), encoding="utf-8")
    assert directory_watcher.get_heavy_threshold_bytes() == int(2.5 * 1024 * 1024)


@pytest.mark.parametrize("bad", ["ten", True, -5, 0, None, [10]])
def test_heavy_threshold_invalid_values_fall_back_to_default(tmp_path, monkeypatch, bad):
    settings = tmp_path / "ingestion_settings.json"
    settings.write_text(json.dumps({"heavy_file_mb": bad}), encoding="utf-8")
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings))
    assert directory_watcher.get_heavy_threshold_bytes() == 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# 2) 크기 경계 라우팅: threshold 이상 → heavy 큐, 미만 → 인라인
# ---------------------------------------------------------------------------

def test_size_boundary_routes_heavy_vs_inline(tmp_path, monkeypatch, inline_calls):
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)
    ws = _make_workspace(tmp_path, "hvy_test_route", {"big.csv": 100, "small.csv": 99})
    lane = FakeLane()
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_route", heavy_lane=lane,
    )

    big = os.path.join(ws, "raws", "big.csv")
    small = os.path.join(ws, "raws", "small.csv")

    # 임계 미만 → 인라인 즉시 처리, 큐 미사용
    handler._handle_event(small)
    assert [c[1] for c in inline_calls] == ["small.csv"]
    assert lane.jobs == []
    assert not handler.processing_files

    # 임계 이상(경계 포함) → heavy 큐 제출, processing_files 유지(이중 진입 가드)
    handler._handle_event(big)
    assert len(lane.jobs) == 1
    assert [c[1] for c in inline_calls] == ["small.csv"]  # 아직 실행 안 됨
    assert big in handler.processing_files
    assert handler._heavy_backlog == 1

    # 워커 실행 시뮬레이션 → 처리 + 정리
    lane.run_all()
    assert [c[1] for c in inline_calls] == ["small.csv", "big.csv"]
    assert not handler.processing_files
    assert handler._heavy_backlog == 0


def test_threshold_config_change_reflected_on_next_file(tmp_path, monkeypatch, inline_calls):
    """config 변경(임계 하향)이 다음 파일 이벤트부터 라우팅에 반영된다."""
    settings = tmp_path / "ingestion_settings.json"
    settings.write_text(json.dumps({"heavy_file_mb": 1}), encoding="utf-8")
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings))

    ws = _make_workspace(tmp_path, "hvy_test_cfg", {"f1.csv": 2048, "f2.csv": 2048})
    lane = FakeLane()
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_cfg", heavy_lane=lane,
    )

    handler._handle_event(os.path.join(ws, "raws", "f1.csv"))  # 2KB < 1MB → 인라인
    assert lane.jobs == [] and [c[1] for c in inline_calls] == ["f1.csv"]

    # 임계를 ~1KB로 하향 → 같은 크기 파일이 heavy로 라우팅
    settings.write_text(json.dumps({"heavy_file_mb": 0.001}), encoding="utf-8")
    handler._handle_event(os.path.join(ws, "raws", "f2.csv"))
    assert len(lane.jobs) == 1
    lane.run_all()
    assert [c[1] for c in inline_calls] == ["f1.csv", "f2.csv"]


def test_handler_without_lane_processes_inline_regardless_of_size(tmp_path, monkeypatch, inline_calls):
    """레인 미배선(재시도 임시 핸들러 등)은 크기와 무관하게 기존 인라인 경로 그대로."""
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 1)
    ws = _make_workspace(tmp_path, "hvy_test_legacy", {"big.csv": 4096})
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"), default_table_name="hvy_test_legacy",
    )
    handler._handle_event(os.path.join(ws, "raws", "big.csv"))
    assert [c[1] for c in inline_calls] == ["big.csv"]
    assert not handler.processing_files


# ---------------------------------------------------------------------------
# 3) 같은 워크스페이스 순서 보존: heavy 처리 중 후속 소형 파일은 큐 후미 대기
# ---------------------------------------------------------------------------

def test_same_workspace_order_preserved_behind_heavy(tmp_path, monkeypatch):
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)
    ws = _make_workspace(
        tmp_path, "hvy_test_order", {"heavy.csv": 200, "small.csv": 10}
    )

    order = []
    heavy_started = threading.Event()
    gate = threading.Event()          # heavy 처리 완료를 테스트가 제어
    small_done = threading.Event()

    def fake_process(self, file_path, uploader="system", retries=3, delay=1.0):
        name = os.path.basename(file_path)
        order.append(("start", name))
        if name == "heavy.csv":
            heavy_started.set()
            assert gate.wait(5), "테스트 게이트 대기 실패"
        order.append(("end", name))
        if name == "small.csv":
            small_done.set()

    monkeypatch.setattr(IngestionHandler, "process_with_retry", fake_process)

    lane = HeavyIngestionLane()
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_order", heavy_lane=lane,
    )
    try:
        # heavy 파일 → 큐 제출 후 즉시 반환 (라우팅 스레드 비블로킹)
        handler._handle_event(os.path.join(ws, "raws", "heavy.csv"))
        assert heavy_started.wait(5), "heavy 워커가 처리를 시작해야 한다"

        # heavy 진행 중 도착한 같은 워크스페이스 소형 파일 → 인라인이 아니라 큐 후미로
        handler._handle_event(os.path.join(ws, "raws", "small.csv"))
        assert ("start", "small.csv") not in order, \
            "heavy 완료 전에 같은 워크스페이스 후속 파일이 처리되면 순서 보존 위반"
        assert handler._heavy_backlog == 2

        gate.set()
        assert small_done.wait(5), "heavy 완료 후 후속 파일이 처리되어야 한다"
        assert order == [
            ("start", "heavy.csv"), ("end", "heavy.csv"),
            ("start", "small.csv"), ("end", "small.csv"),
        ]
        assert _wait_until(lambda: not handler.processing_files)
        assert _wait_until(lambda: handler._heavy_backlog == 0)
    finally:
        gate.set()
        lane.stop()


def test_inline_falls_back_to_queue_when_workspace_busy(tmp_path, monkeypatch, inline_calls):
    """직렬화 락이 점유된 워크스페이스의 소형 파일은 블로킹 대기 대신 큐 후미로 간다
    (observer 디스패치 스레드 HOL 방지 + 순서 보존)."""
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 10**9)
    ws = _make_workspace(tmp_path, "hvy_test_busy", {"s.csv": 10})
    lane = FakeLane()
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_busy", heavy_lane=lane,
    )

    assert handler._serial_lock.acquire(blocking=False)  # 처리 중 상황 시뮬레이션
    try:
        handler._handle_event(os.path.join(ws, "raws", "s.csv"))
        assert inline_calls == [], "락 점유 중 인라인 처리는 순서 보존 위반"
        assert len(lane.jobs) == 1
    finally:
        handler._serial_lock.release()

    lane.run_all()
    assert [c[1] for c in inline_calls] == ["s.csv"]
    assert not handler.processing_files and handler._heavy_backlog == 0


# ---------------------------------------------------------------------------
# 4) 교차 워크스페이스 격리: A 테이블 heavy 진행 중 B 테이블 소형 파일은 즉시 완료
# ---------------------------------------------------------------------------

def test_cross_workspace_small_file_not_blocked_by_heavy(tmp_path, monkeypatch):
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)
    ws_a = _make_workspace(tmp_path, "hvy_test_iso_a", {"heavy.csv": 200})
    ws_b = _make_workspace(tmp_path, "hvy_test_iso_b", {"tiny.csv": 10})

    order = []
    heavy_started = threading.Event()
    gate = threading.Event()

    def fake_process(self, file_path, uploader="system", retries=3, delay=1.0):
        name = os.path.basename(file_path)
        order.append(("start", name))
        if name == "heavy.csv":
            heavy_started.set()
            assert gate.wait(5)
        order.append(("end", name))

    monkeypatch.setattr(IngestionHandler, "process_with_retry", fake_process)

    lane = HeavyIngestionLane()  # 두 워크스페이스가 공유 (WorkspaceWatcher와 동일 구성)
    handler_a = IngestionHandler(
        ws_a, None, os.path.join(ws_a, "archives"),
        default_table_name="hvy_test_iso_a", heavy_lane=lane,
    )
    handler_b = IngestionHandler(
        ws_b, None, os.path.join(ws_b, "archives"),
        default_table_name="hvy_test_iso_b", heavy_lane=lane,
    )
    try:
        handler_a._handle_event(os.path.join(ws_a, "raws", "heavy.csv"))
        assert heavy_started.wait(5)

        # A의 heavy가 가로막지 않는다 — B는 인라인으로 즉시 완료 (게이트 해제 전에)
        handler_b._handle_event(os.path.join(ws_b, "raws", "tiny.csv"))
        assert ("end", "tiny.csv") in order, \
            "다른 워크스페이스 소형 파일은 heavy 완료를 기다리면 안 된다"
        assert ("end", "heavy.csv") not in order

        gate.set()
        assert _wait_until(lambda: ("end", "heavy.csv") in order)
    finally:
        gate.set()
        lane.stop()


# ---------------------------------------------------------------------------
# 5) 스윕 경로의 heavy 라우팅 (재기동 캐치업이 대형 파일 주 발원지)
# ---------------------------------------------------------------------------

def test_sweep_routes_big_files_to_heavy_lane(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    config = {"hvy_test_sweep": dict(HVY_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: config)
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)

    _make_workspace(base, "hvy_test_sweep", {"big.csv": 500, "small.csv": 10})
    # WorkspaceWatcher 등록 경로에는 scripts 폴더 또는 config 해석이 필요 — config 해석 사용
    processed = []
    done = threading.Event()

    def fake_process(self, file_path, uploader="system", retries=3, delay=1.0):
        processed.append((threading.current_thread().name, os.path.basename(file_path)))
        if len(processed) >= 2:
            done.set()

    monkeypatch.setattr(IngestionHandler, "process_with_retry", fake_process)

    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()
    assert watcher.watch_count == 1
    try:
        assert watcher.sweep_existing_files() == 2
        assert done.wait(5), "스윕 대상 파일이 모두 처리되어야 한다"
        by_name = {name: thread for thread, name in processed}
        assert by_name["big.csv"] == HeavyIngestionLane.WORKER_THREAD_NAME, \
            "스윕 경로의 대형 파일도 heavy 레인에서 처리되어야 한다"
        assert by_name["small.csv"] != HeavyIngestionLane.WORKER_THREAD_NAME
    finally:
        watcher._stop_event.set()
        watcher.heavy_lane.stop()


# ---------------------------------------------------------------------------
# 6) 상태 통지 라이프사이클: QUEUED → PROCESSING → FINISHED
# ---------------------------------------------------------------------------

def test_heavy_lane_emits_state_lifecycle(tmp_path, monkeypatch, inline_calls):
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)
    ws = _make_workspace(tmp_path, "hvy_test_state", {"big.csv": 300})
    lane = FakeLane()
    states = []
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_state", heavy_lane=lane,
        on_ingestion_state_callback=states.append,
    )

    handler._handle_event(os.path.join(ws, "raws", "big.csv"))
    lane.run_all()

    assert [s["status"] for s in states] == ["QUEUED", "PROCESSING", "FINISHED"]
    queued, processing, finished = states
    assert queued["lane"] == "heavy" and queued["size_bytes"] == 300
    assert queued["filename"] == "big.csv" and queued["table_name"] == "hvy_test_state"
    assert queued.get("queued_at")
    assert processing["lane"] == "heavy" and processing.get("started_at")
    assert finished["filename"] == "big.csv"


# ---------------------------------------------------------------------------
# 7) 진행 스냅샷 레지스트리 (웹서버측)
# ---------------------------------------------------------------------------

def test_activity_registry_state_progress_and_remove():
    reg = IngestionActivityRegistry()
    reg.apply_state({
        "table_name": "hvy_test_reg", "filename": "big.csv", "lane": "heavy",
        "status": "QUEUED", "size_bytes": 123, "queued_at": "2026-07-26T10:00:00",
    })
    snap = reg.snapshot()
    assert len(snap) == 1
    e = snap[0]
    assert e["status"] == "QUEUED" and e["lane"] == "heavy" and e["size_bytes"] == 123
    assert e["progress"] == 0 and "elapsed_seconds" in e

    reg.apply_state({
        "table_name": "hvy_test_reg", "filename": "big.csv", "lane": "heavy",
        "status": "PROCESSING", "started_at": "2026-07-26T10:00:05",
    })
    # 진행 이벤트는 lane을 덮어쓰지 않는다 (normal 기본값으로의 오염 방지)
    reg.apply_progress("hvy_test_reg", "big.csv", progress=42,
                       processed_rows=42000, total_rows=100000)
    e = reg.snapshot()[0]
    assert e["status"] == "PROCESSING" and e["lane"] == "heavy"
    assert e["progress"] == 42 and e["processed_rows"] == 42000 and e["total_rows"] == 100000
    assert e["queued_at"] == "2026-07-26T10:00:00" and e["started_at"] == "2026-07-26T10:00:05"

    # normal 파일은 진행 이벤트만으로 엔트리 생성 (lane 기본 normal)
    reg.apply_progress("hvy_test_reg2", "s.csv", progress=10,
                       processed_rows=100, total_rows=1000)
    assert {x["lane"] for x in reg.snapshot()} == {"heavy", "normal"}

    # FINISHED / remove 는 멱등 제거
    reg.apply_state({"table_name": "hvy_test_reg", "filename": "big.csv", "status": "FINISHED"})
    reg.remove("hvy_test_reg2", "s.csv")
    reg.remove("hvy_test_reg2", "s.csv")
    assert reg.snapshot() == []


def test_activity_registry_evicts_stale_entries():
    reg = IngestionActivityRegistry(ttl_seconds=0)  # 즉시 만료
    reg.apply_progress("hvy_test_ttl", "orphan.csv", progress=5)
    # updated_at을 과거로 밀어 고아 상황 재현
    with reg._lock:
        for e in reg._entries.values():
            e["updated_at"] -= 1
    assert reg.snapshot() == [], "watcher 사망 등으로 FINISHED가 없는 고아 엔트리는 TTL 퇴거"


def test_activity_registry_ignores_malformed_payloads():
    reg = IngestionActivityRegistry()
    reg.apply_state(None)
    reg.apply_state({"status": "PROCESSING"})                    # 키 결측
    reg.apply_state({"table_name": "t", "filename": "f", "status": "???"})  # 미지 상태
    reg.apply_progress(None, None)
    assert reg.snapshot() == []


# ---------------------------------------------------------------------------
# 8) active API: 내부 이벤트 push → 스냅샷 서빙 (엔드포인트 계약)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 9) QA 픽스 회귀 (QA_large_file_p1_review.md F1/F3/F4)
# ---------------------------------------------------------------------------

def test_activity_registry_keeps_long_queued_entries():
    """[QA F1] QUEUED 엔트리는 무갱신 장기 대기가 정상 — PROCESSING TTL로 퇴거되면
    재기동 경고가 최악 시나리오(다중 heavy 대기열)에서 과소 표시된다."""
    reg = IngestionActivityRegistry(ttl_seconds=1, queued_ttl_seconds=3600)
    reg.apply_state({
        "table_name": "hvy_test_f1", "filename": "queued.csv", "lane": "heavy",
        "status": "QUEUED",
    })
    reg.apply_progress("hvy_test_f1", "processing.csv", progress=50)  # status PROCESSING
    # 두 엔트리 모두 PROCESSING TTL(1s)을 초과하도록 backdate
    with reg._lock:
        for e in reg._entries.values():
            e["updated_at"] -= 10
    snap = reg.snapshot()
    assert [e["filename"] for e in snap] == ["queued.csv"], \
        "QUEUED 엔트리는 PROCESSING TTL 초과에도 생존해야 한다 (별도 장기 TTL)"
    assert snap[0]["status"] == "QUEUED"

    # QUEUED 전용 TTL(3600s)마저 초과하면 고아로 간주하고 퇴거 (무한 잔류 방지)
    with reg._lock:
        for e in reg._entries.values():
            e["updated_at"] -= 3700
    assert reg.snapshot() == []


def test_rerouted_small_file_reports_normal_lane(tmp_path, monkeypatch, inline_calls):
    """[QA F4] 순서 보존 때문에 큐 후미로 재라우팅된 '소형' 파일의 상태 통지는
    lane="normal"이어야 한다 — HEAVY 배지 오표기/heavy 카운트 부풀림 방지."""
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 10**9)
    ws = _make_workspace(tmp_path, "hvy_test_f4", {"s.csv": 10})
    lane = FakeLane()
    states = []
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_f4", heavy_lane=lane,
        on_ingestion_state_callback=states.append,
    )

    # 워크스페이스 처리 중 상황(직렬화 락 점유) → 소형 파일이 큐 후미로 재라우팅
    assert handler._serial_lock.acquire(blocking=False)
    try:
        handler._handle_event(os.path.join(ws, "raws", "s.csv"))
        assert len(lane.jobs) == 1
    finally:
        handler._serial_lock.release()
    lane.run_all()

    assert [s["status"] for s in states] == ["QUEUED", "PROCESSING", "FINISHED"]
    assert states[0]["lane"] == "normal", "재라우팅 소형 파일의 QUEUED lane은 normal"
    assert states[1]["lane"] == "normal", "재라우팅 소형 파일의 PROCESSING lane은 normal"


def test_backlog_rerouted_small_file_reports_normal_lane(tmp_path, monkeypatch, inline_calls):
    """[QA F4] heavy backlog 뒤에 줄 선 소형 파일도 lane="normal"로 통지된다."""
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)
    ws = _make_workspace(tmp_path, "hvy_test_f4b", {"big.csv": 200, "s.csv": 10})
    lane = FakeLane()
    states = []
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_f4b", heavy_lane=lane,
        on_ingestion_state_callback=states.append,
    )

    handler._handle_event(os.path.join(ws, "raws", "big.csv"))  # heavy → 큐 (backlog 1)
    handler._handle_event(os.path.join(ws, "raws", "s.csv"))    # backlog>0 → 큐 후미
    queued = [s for s in states if s["status"] == "QUEUED"]
    assert [(s["filename"], s["lane"]) for s in queued] == [
        ("big.csv", "heavy"), ("s.csv", "normal"),
    ]
    lane.run_all()
    assert handler._heavy_backlog == 0 and not handler.processing_files


def test_retry_pattern_waits_for_heavy_via_workspace_serial_lock(tmp_path, monkeypatch):
    """[QA F3] run_watcher 재처리 폴러가 사용하는 패턴(get_workspace_serial_lock 획득 후
    process_archived_file_sync)이 heavy 처리와 상호 배제됨을 검증 — 같은 워크스페이스
    경로면 핸들러 인스턴스가 달라도 동일 락 객체를 공유한다."""
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)
    ws = _make_workspace(tmp_path, "hvy_test_f3", {"heavy.csv": 200})

    # 모듈 레지스트리: 표기가 달라도(normcase/절대경로) 같은 경로면 같은 락
    lock_a = directory_watcher.get_workspace_serial_lock(ws)
    lock_b = directory_watcher.get_workspace_serial_lock(ws.upper() if os.name == "nt" else ws)
    assert lock_a is lock_b

    order = []
    heavy_started = threading.Event()
    gate = threading.Event()
    retry_done = threading.Event()

    def fake_process(self, file_path, uploader="system", retries=3, delay=1.0):
        order.append(("start", os.path.basename(file_path)))
        heavy_started.set()
        assert gate.wait(5)
        order.append(("end", os.path.basename(file_path)))

    monkeypatch.setattr(IngestionHandler, "process_with_retry", fake_process)

    lane = HeavyIngestionLane()
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_f3", heavy_lane=lane,
    )
    try:
        handler._handle_event(os.path.join(ws, "raws", "heavy.csv"))
        assert heavy_started.wait(5)

        # run_watcher poll_pending_retries와 동일 패턴: 별도 핸들러 인스턴스 + 공용 락
        def retry_worker():
            with directory_watcher.get_workspace_serial_lock(ws):
                order.append(("retry", "archived.csv"))
            retry_done.set()

        t = threading.Thread(target=retry_worker, daemon=True)
        t.start()
        # heavy가 락 보유 중 — 재처리는 진입하지 못해야 한다
        assert not retry_done.wait(0.2), "재처리가 heavy 처리와 동시 진행되면 순서 계약 위반"
        assert ("retry", "archived.csv") not in order

        gate.set()
        assert retry_done.wait(5), "heavy 완료 후 재처리가 진행되어야 한다"
        assert order == [
            ("start", "heavy.csv"), ("end", "heavy.csv"), ("retry", "archived.csv"),
        ]
    finally:
        gate.set()
        lane.stop()


# ---------------------------------------------------------------------------
# 10) 라이브 드릴 후속 수정 회귀 (QA_p1_live_drill_report.md 결함1 + 관찰)
# ---------------------------------------------------------------------------

def test_queued_notification_precedes_instant_worker_pickup(tmp_path, monkeypatch, inline_calls):
    """[드릴 결함1] 큐가 비어 워커가 제출 '즉시' 잡을 집는 최악 타이밍에서도
    QUEUED 통지가 PROCESSING보다 먼저 발신되어야 한다 (역행 덮어쓰기 오표시 방지)."""

    class InstantLane:
        """submit 즉시 잡을 동기 실행 — 빈 큐 + 즉시 픽업 경합의 결정적 재현."""
        def submit(self, job):
            job()

    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)
    ws = _make_workspace(tmp_path, "hvy_test_drill1", {"big.csv": 300})
    states = []
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_drill1", heavy_lane=InstantLane(),
        on_ingestion_state_callback=states.append,
    )
    handler._handle_event(os.path.join(ws, "raws", "big.csv"))

    assert [s["status"] for s in states] == ["QUEUED", "PROCESSING", "FINISHED"], \
        "즉시 픽업에서도 QUEUED가 선행해야 한다 (submit 이전 발신)"
    assert not handler.processing_files and handler._heavy_backlog == 0


def test_submit_failure_cleans_up_preemptive_queued_state(tmp_path, monkeypatch, inline_calls):
    """[드릴 결함1 후속] QUEUED 선발신으로 바뀌면서 submit 실패 시 고아 QUEUED 엔트리
    (장기 TTL — F1)가 남지 않도록 FINISHED 정리를 발신하고 인라인 폴백해야 한다."""

    class BrokenLane:
        def submit(self, job):
            raise RuntimeError("lane stopped")

    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 100)
    ws = _make_workspace(tmp_path, "hvy_test_drill1b", {"big.csv": 300})
    states = []
    handler = IngestionHandler(
        ws, None, os.path.join(ws, "archives"),
        default_table_name="hvy_test_drill1b", heavy_lane=BrokenLane(),
        on_ingestion_state_callback=states.append,
    )
    handler._handle_event(os.path.join(ws, "raws", "big.csv"))

    assert [s["status"] for s in states] == ["QUEUED", "FINISHED"], \
        "submit 실패 시 선발신 QUEUED는 FINISHED로 정리되어야 한다"
    assert [c[1] for c in inline_calls] == ["big.csv"], "submit 실패는 인라인 폴백 처리"
    assert not handler.processing_files and handler._heavy_backlog == 0


def test_batch_refresh_ws_payload_includes_total_log_count(client, monkeypatch):
    """[드릴 관찰] watcher-직행 경로(/internal/events/batch-refresh)의 WS 페이로드도
    체인 경로(passthrough)와 대칭으로 total_log_count를 동봉해야 한다 (C-5 계약 정합 —
    클라이언트가 절단 여부를 양 경로에서 동일하게 판별 가능)."""
    import main as main_module

    sent = []

    async def capture_broadcast(text):
        sent.append(text)

    monkeypatch.setattr(main_module.manager, "broadcast", capture_broadcast)

    logs = [{"row_id": f"r{i}", "table_name": "hvy_test_ws"} for i in range(3)]
    res = client.post("/internal/events/batch-refresh", json={
        "table_name": "hvy_test_ws", "change_count": 1200,
        "created_logs": logs, "total_log_count": 1200,
    })
    assert res.status_code == 200
    assert len(sent) == 1
    msg = json.loads(sent[0])
    assert msg["event"] == "batch_refresh_required"
    assert msg["total_log_count"] == 1200, "실제 총 건수(절단 전)가 WS 페이로드에 실려야 한다"
    assert len(msg["created_logs"]) == 3

    # 구버전 워처 호환: total_log_count 미전송 시 len(created_logs)로 폴백
    sent.clear()
    res = client.post("/internal/events/batch-refresh", json={
        "table_name": "hvy_test_ws", "change_count": 3, "created_logs": logs,
    })
    assert res.status_code == 200
    assert json.loads(sent[0])["total_log_count"] == 3


def test_active_api_snapshot_shape(client):
    ingestion_activity.registry.clear()
    try:
        res = client.post("/internal/events/ingestion-state", json={
            "table_name": "hvy_test_api", "filename": "big.csv", "lane": "heavy",
            "status": "PROCESSING", "size_bytes": 555, "started_at": "2026-07-26T11:00:00",
        })
        assert res.status_code == 200

        res = client.get("/admin/file-ingestion/active")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success" and body["total"] == 1
        entry = body["data"][0]
        for field in ("table_name", "filename", "lane", "status", "progress",
                      "processed_rows", "total_rows", "size_bytes", "elapsed_seconds"):
            assert field in entry
        assert entry["lane"] == "heavy" and entry["status"] == "PROCESSING"

        # FINISHED push → 목록에서 제거
        res = client.post("/internal/events/ingestion-state", json={
            "table_name": "hvy_test_api", "filename": "big.csv", "status": "FINISHED",
        })
        assert res.status_code == 200
        body = client.get("/admin/file-ingestion/active").json()
        assert body["total"] == 0 and body["data"] == []
    finally:
        ingestion_activity.registry.clear()
