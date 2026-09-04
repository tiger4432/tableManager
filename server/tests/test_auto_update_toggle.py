# -*- coding: utf-8 -*-
"""
auto_update 수집기 active 토글 기능 테스트.

- 제어 파일(auto_update_control.json) IO (부재/손상 fail-open, 원자적 갱신)
- 스케줄러의 disabled 스크립트 핫 스킵 (SKIPPED 상태 + next_run 전진 + 미실행)
- GET /admin/auto-update/status 의 active 필드 부가 (기존 필드 불변)
- POST /admin/auto-update/toggle 의 200/400/404
"""
import os
import json
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import auto_update_control as auc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_TABLE = "autoupd_test_tbl"
TEST_SCRIPT = "collector_a.py"
TEST_KEY = f"{TEST_TABLE}/{TEST_SCRIPT}"


def _make_workspace(base_dir, table=TEST_TABLE, script=TEST_SCRIPT, body='out = "col1,col2\\n1,2\\n"\n'):
    """tmp 서버 디렉토리 하위에 ingestion_workspace/<table>/auto_update/<script> 를 생성."""
    au_dir = os.path.join(str(base_dir), "ingestion_workspace", table, "auto_update")
    os.makedirs(au_dir, exist_ok=True)
    script_path = os.path.join(au_dir, script)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("# schedule: * * * * *\n" + body)
    return script_path


# ---------------------------------------------------------------------------
# 1. 제어 파일 IO
# ---------------------------------------------------------------------------

class TestControlFileIO:
    def test_missing_file_means_all_active(self, tmp_path):
        assert auc.read_disabled_scripts(str(tmp_path)) == set()

    def test_set_inactive_then_active_roundtrip(self, tmp_path):
        base = str(tmp_path)
        auc.set_script_active(TEST_KEY, False, base)
        assert auc.read_disabled_scripts(base) == {TEST_KEY}

        # 파일 내용 규격 확인: {"disabled": [...]}
        with open(auc.get_control_path(base), encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"disabled": [TEST_KEY]}

        auc.set_script_active(TEST_KEY, True, base)
        assert auc.read_disabled_scripts(base) == set()

    def test_set_inactive_is_idempotent(self, tmp_path):
        base = str(tmp_path)
        auc.set_script_active(TEST_KEY, False, base)
        auc.set_script_active(TEST_KEY, False, base)
        assert auc.read_disabled_scripts(base) == {TEST_KEY}

    def test_corrupt_file_fails_open(self, tmp_path):
        base = str(tmp_path)
        path = auc.get_control_path(base)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not-json!!")
        assert auc.read_disabled_scripts(base) == set()

        # 손상 상태에서도 set_script_active 는 정상 복구 기록
        auc.set_script_active(TEST_KEY, False, base)
        assert auc.read_disabled_scripts(base) == {TEST_KEY}

    def test_wrong_shape_fails_open(self, tmp_path):
        base = str(tmp_path)
        path = auc.get_control_path(base)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"disabled": "not-a-list"}, f)
        assert auc.read_disabled_scripts(base) == set()

    def test_validate_script_key(self):
        assert auc.validate_script_key("tbl/script.py") is True
        assert auc.validate_script_key("my_table-1/coll.v2.py") is True
        assert auc.validate_script_key("bonding_map/fetch_data copy.py") is True  # 공백 파일명 실사용 사례
        assert auc.validate_script_key("tbl/한글 수집기.py") is True
        assert auc.validate_script_key("tbl/script.txt") is False
        assert auc.validate_script_key("script.py") is False
        assert auc.validate_script_key("a/b/script.py") is False
        assert auc.validate_script_key("../evil/script.py") is False
        assert auc.validate_script_key("tbl/..py") is False
        assert auc.validate_script_key("tbl\\script.py") is False
        assert auc.validate_script_key(None) is False
        assert auc.validate_script_key(123) is False
        assert auc.validate_script_key("") is False


# ---------------------------------------------------------------------------
# 2. 스케줄러 핫 스킵
# ---------------------------------------------------------------------------

def _await_collector(collector, timeout=5.0):
    """Wait for a collector started off the tick thread.

    🔴 2026-09-04: `check_and_run_schedules` used to run the collector INLINE, so these
    cases could assert the moment it returned. That inline call is exactly what stopped
    `heartbeat.beat("scheduler")` for the length of a user script and made /health report
    the daemon as making no progress. The work now runs on a thread and the scheduling
    pass returns immediately - so the wait is the change, not the assertion.
    """
    import time as _time
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if collector.last_status not in (None, "RUNNING"):
            return collector.last_status
        _time.sleep(0.02)
    return collector.last_status


class TestSchedulerSkip:
    def _build_scheduler(self, tmp_path):
        from run_auto_update import MultiDiscoveryScheduler
        _make_workspace(tmp_path)
        scheduler = MultiDiscoveryScheduler(check_interval=1, server_dir=str(tmp_path))
        scheduler.discover_and_load_collectors()
        assert len(scheduler.collectors) == 1
        return scheduler

    def test_disabled_script_is_skipped(self, tmp_path):
        base = str(tmp_path)
        scheduler = self._build_scheduler(tmp_path)
        collector = scheduler.collectors[0]

        auc.set_script_active(TEST_KEY, False, base)

        now = datetime.now()
        collector.next_run = now - timedelta(seconds=1)
        scheduler.check_and_run_schedules(now=now)

        assert collector.last_status == "SKIPPED"
        assert collector.next_run > now  # 스킵해도 다음 스케줄로 전진
        # 실제 실행이 없었으므로 raws 산출물 없음
        assert os.listdir(collector.target_dir) == []

        # 스킵도 status 파일에 반영 (active: false 포함)
        with open(scheduler.status_file_path, encoding="utf-8") as f:
            status = json.load(f)
        entry = status["collectors"][0]
        assert entry["last_status"] == "SKIPPED"
        assert entry["active"] is False

    def test_enabled_script_runs(self, tmp_path):
        base = str(tmp_path)
        scheduler = self._build_scheduler(tmp_path)
        collector = scheduler.collectors[0]

        # 제어 파일에 등록 후 다시 활성화 (핫 반영: 재발견 불필요)
        auc.set_script_active(TEST_KEY, False, base)
        auc.set_script_active(TEST_KEY, True, base)

        now = datetime.now()
        collector.next_run = now - timedelta(seconds=1)
        scheduler.check_and_run_schedules(now=now)
        _await_collector(collector)

        assert collector.last_status == "SUCCESS"
        outputs = os.listdir(collector.target_dir)
        assert len(outputs) == 1 and outputs[0].endswith(".csv")

        with open(scheduler.status_file_path, encoding="utf-8") as f:
            status = json.load(f)
        assert status["collectors"][0]["active"] is True

    def test_run_now_ignores_disabled(self, tmp_path):
        """run-now(수동 실행)는 active 무관 실행 — 계약 #5."""
        import time
        base = str(tmp_path)
        scheduler = self._build_scheduler(tmp_path)
        collector = scheduler.collectors[0]

        auc.set_script_active(TEST_KEY, False, base)
        assert scheduler.run_collector_on_demand(TEST_TABLE, TEST_SCRIPT) is True

        # run_collector_on_demand 는 데몬 스레드로 실행 — 완료 대기
        deadline = time.time() + 10
        while time.time() < deadline and collector.last_status in ("PENDING", "RUNNING"):
            time.sleep(0.05)
        assert collector.last_status == "SUCCESS"
        assert len(os.listdir(collector.target_dir)) == 1


# ---------------------------------------------------------------------------
# 3. /admin/auto-update/status 의 active 필드
# ---------------------------------------------------------------------------

class TestStatusEndpoint:
    def _seed_status_file(self, base):
        status = {
            "last_updated": "2026-07-25 10:00:00",
            "collectors": [
                {
                    "table_name": TEST_TABLE,
                    "script_name": TEST_SCRIPT,
                    "script_path": f"/x/{TEST_SCRIPT}",
                    "cron_expression": "* * * * *",
                    "next_run": "2026-07-25 10:01:00",
                    "last_run": None,
                    "last_status": "PENDING",
                    "last_error": None
                },
                {
                    "table_name": "other_tbl",
                    "script_name": "other.py",
                    "script_path": "/x/other.py",
                    "cron_expression": "0 * * * *",
                    "next_run": None,
                    "last_run": None,
                    "last_status": "PENDING",
                    "last_error": None
                }
            ]
        }
        os.makedirs(os.path.join(base, "config"), exist_ok=True)
        with open(os.path.join(base, "config", "scheduler_status.json"), "w", encoding="utf-8") as f:
            json.dump(status, f)
        return status

    def test_status_annotates_active(self, client, tmp_path, monkeypatch):
        base = str(tmp_path)
        monkeypatch.setattr(auc, "SERVER_DIR", base)
        original = self._seed_status_file(base)
        auc.set_script_active(TEST_KEY, False, base)

        res = client.get("/admin/auto-update/status")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        assert body["last_updated"] == "2026-07-25 10:00:00"

        by_name = {c["script_name"]: c for c in body["data"]}
        assert by_name[TEST_SCRIPT]["active"] is False
        assert by_name["other.py"]["active"] is True

        # 기존 필드 불변(순수 추가) 검증
        for orig_entry in original["collectors"]:
            got = by_name[orig_entry["script_name"]]
            for k, v in orig_entry.items():
                assert got[k] == v

    def test_status_all_active_without_control_file(self, client, tmp_path, monkeypatch):
        base = str(tmp_path)
        monkeypatch.setattr(auc, "SERVER_DIR", base)
        self._seed_status_file(base)

        res = client.get("/admin/auto-update/status")
        assert res.status_code == 200
        assert all(c["active"] is True for c in res.json()["data"])


# ---------------------------------------------------------------------------
# 4. /admin/auto-update/toggle
# ---------------------------------------------------------------------------

class TestToggleEndpoint:
    def test_toggle_success_roundtrip(self, client, tmp_path, monkeypatch):
        base = str(tmp_path)
        monkeypatch.setattr(auc, "SERVER_DIR", base)
        _make_workspace(tmp_path)

        # 비활성화
        res = client.post("/admin/auto-update/toggle", json={"script": TEST_KEY, "active": False})
        assert res.status_code == 200
        assert res.json() == {"status": "success", "script": TEST_KEY, "active": False}
        assert auc.read_disabled_scripts(base) == {TEST_KEY}

        # 재활성화
        res = client.post("/admin/auto-update/toggle", json={"script": TEST_KEY, "active": True})
        assert res.status_code == 200
        assert res.json() == {"status": "success", "script": TEST_KEY, "active": True}
        assert auc.read_disabled_scripts(base) == set()

    def test_toggle_nonexistent_script_404(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(auc, "SERVER_DIR", str(tmp_path))
        res = client.post("/admin/auto-update/toggle", json={"script": "ghost_tbl/ghost.py", "active": False})
        assert res.status_code == 404

    @pytest.mark.parametrize("payload", [
        {"script": "no_slash.py", "active": False},          # 형식 위반
        {"script": "../evil/x.py", "active": False},          # 경로 탈출
        {"script": "tbl/script.txt", "active": False},        # .py 아님
        {"script": 123, "active": False},                     # 타입 위반
        {"active": False},                                    # script 누락
        {"script": "tbl/script.py"},                          # active 누락
        {"script": "tbl/script.py", "active": "yes"},         # active 타입 위반
    ])
    def test_toggle_validation_400(self, client, tmp_path, monkeypatch, payload):
        monkeypatch.setattr(auc, "SERVER_DIR", str(tmp_path))
        res = client.post("/admin/auto-update/toggle", json=payload)
        assert res.status_code == 400
