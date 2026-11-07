"""[Startup Sweep] 워처 기동/런타임 등록 시 raws/ 기존 파일 스윕 검증.

결함 배경: directory_watcher는 watchdog 이벤트 전용이라 워처 다운타임 중 raws/에
도착한 파일이 영영 미처리(FileIngestionLog 기록조차 없음)로 방치됐다.

- 기동 스윕: start() 후 raws/ 직속 기존 파일을 mtime 오름차순으로 기존 이벤트
  경로(_handle_event)와 동일하게 처리
- 런타임 등록 스윕: sync_new_workspaces가 '신규 등록된 raws/만' 스윕
- err//archives//raws 하위 디렉토리 제외 (observer recursive=False와 동일 범위)
- (mtime, size) 시그니처 가드: 잔류 파일의 무한 재시도 루프 방지
- 이중 처리 가드: 스윕 스레드 vs watchdog 이벤트 스레드 동시 진입 시 1회만 처리
- 주기 안전망: _ensure_periodic_sweep_running 반복 스윕 + stop()으로 종료
"""

import os
import sys
import threading
import time

# Ensure server/parsers is in python path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import directory_watcher
from directory_watcher import IngestionHandler, WorkspaceWatcher


# 사용자 config(gitignored)와 절대 겹치지 않는 고유 접두 테이블명 사용 (교훈 파일)
SWEEP_INFO = {
    "business_key": "part_no",
    "column_types": {"part_no": "string", "category": "string"},
    "display_columns": ["part_no", "category"],
}


def _make_workspace(base, table_name, files=None):
    """표준 워크스페이스 구조 생성 + raws/ 직속 파일 배치. 반환: raws 절대경로."""
    ws = base / table_name
    for sub in ("raws", "archives", "err", "config"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    (ws / "config" / "config.json").write_text(
        '{"table_name": "%s"}' % table_name, encoding="utf-8"
    )
    for name in (files or []):
        (ws / "raws" / name).write_text("part_no,category\np1,c1\n", encoding="utf-8")
    return os.path.abspath(str(ws / "raws"))


def _set_mtime(path, epoch):
    os.utime(str(path), (epoch, epoch))


# ---------------------------------------------------------------------------
# 1) 기동 스윕: 기존 파일을 mtime 오름차순 처리, err/·하위 디렉토리 제외
# ---------------------------------------------------------------------------

def test_sweep_processes_preexisting_files_mtime_order_excluding_err(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    config = {"sweeptest_a": dict(SWEEP_INFO), "sweeptest_b": dict(SWEEP_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: config)

    raws_a = _make_workspace(base, "sweeptest_a", ["a_new.csv", "a_old.csv"])
    raws_b = _make_workspace(base, "sweeptest_b", ["b_mid.csv"])

    now = time.time()
    _set_mtime(os.path.join(raws_a, "a_old.csv"), now - 300)
    _set_mtime(os.path.join(raws_b, "b_mid.csv"), now - 200)
    _set_mtime(os.path.join(raws_a, "a_new.csv"), now - 100)

    # 스윕 제외 대상: err/ 파일, raws/ 하위 디렉토리 내 파일, archives/ 파일
    ws_a = base / "sweeptest_a"
    (ws_a / "err" / "failed.csv").write_text("x", encoding="utf-8")
    (ws_a / "archives" / "done.csv").write_text("x", encoding="utf-8")
    nested = ws_a / "raws" / "nested_dir"
    nested.mkdir()
    (nested / "deep.csv").write_text("x", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        IngestionHandler, "_handle_event",
        lambda self, fp: calls.append(os.path.abspath(fp)),
    )

    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()
    assert watcher.watch_count == 2

    processed = watcher.sweep_existing_files()
    assert processed == 3
    # 전역 mtime 오름차순 (워크스페이스 교차 정렬)
    assert [os.path.basename(p) for p in calls] == ["a_old.csv", "b_mid.csv", "a_new.csv"]
    # err//archives//하위 디렉토리 파일은 미포함
    assert all("failed.csv" not in p and "done.csv" not in p and "deep.csv" not in p for p in calls)

    # 시그니처 가드: 파일이 그대로 잔류(핸들러 no-op)해도 동일 시그니처는 재시도 안 함
    assert watcher.sweep_existing_files() == 0
    assert len(calls) == 3


# ---------------------------------------------------------------------------
# 2) start()가 observer 기동 후 기동 스윕을 비동기로 킥한다 (전체 raws 대상)
# ---------------------------------------------------------------------------

def test_start_kicks_async_startup_sweep(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    config = {"sweeptest_boot": dict(SWEEP_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: config)
    _make_workspace(base, "sweeptest_boot", ["pending.csv"])

    swept = {}
    done = threading.Event()

    def fake_sweep(self, raw_paths=None):
        swept["raw_paths"] = raw_paths
        swept["observer_alive"] = self.observer.is_alive()
        done.set()
        return 0

    monkeypatch.setattr(WorkspaceWatcher, "sweep_existing_files", fake_sweep)

    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()
    try:
        watcher.start(blocking=False)
        assert done.wait(5), "start()가 기동 스윕을 킥해야 한다"
        assert swept["raw_paths"] is None  # 전체 등록 raws 대상
        assert swept["observer_alive"], "스윕은 observer 기동 이후여야 한다(이벤트 유실 방지)"
    finally:
        if watcher.observer.is_alive():
            watcher.stop()


# ---------------------------------------------------------------------------
# 3) 런타임 등록 스윕: sync_new_workspaces는 '신규 등록 raws/만' 스윕한다
# ---------------------------------------------------------------------------

def test_sync_new_workspaces_sweeps_only_new_raws(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    config = {"sweeptest_old": dict(SWEEP_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: config)

    _make_workspace(base, "sweeptest_old", ["old_pending.csv"])
    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()

    swept = {}
    done = threading.Event()

    def fake_sweep(self, raw_paths=None):
        swept["raw_paths"] = raw_paths
        done.set()
        return 0

    monkeypatch.setattr(WorkspaceWatcher, "sweep_existing_files", fake_sweep)

    try:
        config["sweeptest_new"] = dict(SWEEP_INFO)
        new_raws = _make_workspace(base, "sweeptest_new", ["arrived_while_down.csv"])
        assert watcher.sync_new_workspaces() == 1
        assert done.wait(5), "런타임 등록 시 신규 raws 스윕이 킥되어야 한다"
        assert swept["raw_paths"] == [new_raws]  # 기존 sweeptest_old raws는 재스윕하지 않음
    finally:
        if watcher.observer.is_alive():
            watcher.stop()
        else:
            watcher._stop_event.set()


# ---------------------------------------------------------------------------
# 4) 이중 처리 가드: 스윕/이벤트 스레드가 같은 파일에 동시 진입해도 1회만 처리
# ---------------------------------------------------------------------------

def test_concurrent_handle_event_processes_once(tmp_path, monkeypatch):
    ws = tmp_path / "sweeptest_dup"
    (ws / "raws").mkdir(parents=True)
    (ws / "archives").mkdir()
    fp = ws / "raws" / "same_file.csv"
    fp.write_text("part_no\np1\n", encoding="utf-8")

    handler = IngestionHandler(
        workspace_path=str(ws), config_path=None,
        archives_path=str(ws / "archives"), default_table_name="sweeptest_dup",
    )

    started = threading.Barrier(2)
    processed = []

    def slow_process(self, file_path, uploader="system", retries=3, delay=1.0):
        processed.append(file_path)
        time.sleep(0.2)  # 처리 중 윈도를 벌려 두 번째 진입 시도를 보장

    monkeypatch.setattr(IngestionHandler, "process_with_retry", slow_process)

    def enter():
        started.wait()
        handler._handle_event(str(fp))

    threads = [threading.Thread(target=enter) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(processed) == 1, "동일 파일 동시 진입은 정확히 1회만 처리되어야 한다"
    assert not handler.processing_files, "처리 종료 후 processing_files는 비워져야 한다"


# ---------------------------------------------------------------------------
# 5) 시그니처 가드: 파일 갱신(mtime 변경) 시에만 재시도
# ---------------------------------------------------------------------------

def test_sweep_signature_guard_allows_retry_on_file_change(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    config = {"sweeptest_sig": dict(SWEEP_INFO)}
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: config)
    raws = _make_workspace(base, "sweeptest_sig", ["stuck.csv"])
    stuck = os.path.join(raws, "stuck.csv")

    # 핸들러 no-op → 처리 실패로 파일이 raws/에 잔류하는 상황 시뮬레이션
    monkeypatch.setattr(IngestionHandler, "_handle_event", lambda self, fp: None)

    watcher = WorkspaceWatcher(str(base))
    watcher.discover_and_watch()

    assert watcher.sweep_existing_files() == 1
    assert watcher.sweep_existing_files() == 0  # 동일 시그니처 → 무한 재시도 방지
    _set_mtime(stuck, time.time() + 10)         # 파일 갱신 → 시그니처 변경
    assert watcher.sweep_existing_files() == 1  # 재시도 허용


# ---------------------------------------------------------------------------
# 6) 주기 안전망: 반복 스윕 + stop() 신호로 종료
# ---------------------------------------------------------------------------

def test_periodic_sweep_repeats_and_stops(tmp_path, monkeypatch):
    base = tmp_path / "ingestion_workspace"
    base.mkdir()
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {})
    monkeypatch.setattr(directory_watcher, "PERIODIC_SWEEP_INTERVAL_SECONDS", 0.02)

    watcher = WorkspaceWatcher(str(base))
    sweeps = []
    hit_twice = threading.Event()

    def counting_sweep(self, raw_paths=None):
        sweeps.append(raw_paths)
        if len(sweeps) >= 2:
            hit_twice.set()
        return 0

    monkeypatch.setattr(WorkspaceWatcher, "sweep_existing_files", counting_sweep)

    watcher._ensure_periodic_sweep_running()
    assert hit_twice.wait(5), "주기 스윕이 반복 실행되어야 한다"
    # 멱등: 이미 살아있는 스레드는 재기동하지 않는다
    t = watcher._periodic_sweep_thread
    watcher._ensure_periodic_sweep_running()
    assert watcher._periodic_sweep_thread is t

    watcher._stop_event.set()
    t.join(5)
    assert not t.is_alive(), "stop 신호로 주기 스윕 스레드가 종료되어야 한다"
