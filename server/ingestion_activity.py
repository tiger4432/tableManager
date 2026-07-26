"""[Heavy Lane P1] 진행 중 파일 인제션 스냅샷 레지스트리 (웹서버 프로세스 인메모리).

진행률 상태의 원천은 watcher 프로세스다. watcher가 기존 `/internal/events/*` 패턴으로
상태를 **밀어(push)** 넣고, 웹서버는 이 레지스트리에 캐시했다가
`GET /admin/file-ingestion/active`로 스냅샷을 서빙한다 (프로세스 간 폴링 신설 없음).

유입 경로 3종 (전부 main.py에서 배선):
  1. POST /internal/events/ingestion-state  → apply_state()   (heavy 레인 QUEUED/PROCESSING/FINISHED)
  2. POST /internal/events/broadcast 의 `file_ingestion_progress` 이벤트 → apply_progress()
     (normal 레인 파일은 이 경로로만 엔트리가 생성된다 — lane 기본값 "normal")
  3. POST /internal/events/file-processed → remove()          (완료/실패 시 제거)

정리 안전망: watcher 프로세스가 처리 도중 죽으면 FINISHED가 영영 오지 않으므로,
snapshot() 시 updated_at 기준 TTL 초과 엔트리를 퇴거한다.

페이로드는 소형 스칼라 필드만 담는다 — 무절단 컬렉션 동봉 금지 교훈(server-pm.md) 준수.
"""

import threading
import time

# 진행 갱신이 이 시간(초) 이상 끊긴 엔트리는 고아로 간주하고 퇴거.
# 대형 파일도 청크(1000행)당 진행 이벤트가 오므로 정상 처리 중 갱신 간격은 수 초 단위다.
# 여유를 크게 두되(느린 파서 고려) 무한 잔류는 막는다.
STALE_ENTRY_TTL_SECONDS = 30 * 60

# [QA F1] QUEUED 엔트리는 "정상적으로 오래 조용"하다 — 다중 heavy 대기열에서 통지 1회
# 이후 수십 분간 갱신 없이 대기하는 것이 정상 동작이며, 재기동 경고의 목적상 바로 그
# 창(장시간 대기열)에서 반드시 보여야 한다. PROCESSING TTL을 그대로 적용하면 최악
# 시나리오에서 경고가 과소 표시되므로 훨씬 긴 별도 TTL을 적용한다.
# watcher 사망 잔재의 자가 치유: watcher 재기동 시 스윕이 같은 파일을 재처리하며 동일
# 키 엔트리를 갱신/제거하고, 웹서버 재기동 시 레지스트리 자체가 비므로 무한 잔류는 없다.
STALE_QUEUED_TTL_SECONDS = 24 * 60 * 60


class IngestionActivityRegistry:
    """(table_name, filename) 키의 진행 중 인제션 엔트리 저장소 (스레드 안전)."""

    def __init__(self, ttl_seconds: int = STALE_ENTRY_TTL_SECONDS,
                 queued_ttl_seconds: int = STALE_QUEUED_TTL_SECONDS):
        self._lock = threading.Lock()
        self._entries: dict = {}
        self._ttl = ttl_seconds
        self._queued_ttl = queued_ttl_seconds

    @staticmethod
    def _key(table_name, filename):
        return (str(table_name), str(filename))

    def _new_entry(self, table_name, filename, lane="normal", status="PROCESSING"):
        now = time.time()
        return {
            "table_name": table_name,
            "filename": filename,
            "lane": lane,
            "status": status,          # QUEUED | PROCESSING
            "progress": 0,             # 0-100
            "processed_rows": 0,
            "total_rows": None,
            "size_bytes": None,
            "queued_at": None,         # watcher가 보낸 로컬 ISO 문자열 (표시용)
            "started_at": None,
            "first_seen": now,         # 웹서버 수신 epoch — elapsed 계산 기준
            "updated_at": now,
        }

    def apply_state(self, state: dict):
        """watcher의 명시적 상태 통지(QUEUED/PROCESSING/FINISHED) 반영. 미지 필드는 무시."""
        if not isinstance(state, dict):
            return
        table_name = state.get("table_name")
        filename = state.get("filename")
        status = state.get("status")
        if not table_name or not filename or not status:
            return
        key = self._key(table_name, filename)
        with self._lock:
            if status == "FINISHED":
                self._entries.pop(key, None)
                return
            if status not in ("QUEUED", "PROCESSING"):
                return
            entry = self._entries.get(key)
            if entry is None:
                entry = self._new_entry(table_name, filename)
                self._entries[key] = entry
            entry["status"] = status
            if state.get("lane"):
                entry["lane"] = state["lane"]
            for field in ("size_bytes", "queued_at", "started_at"):
                if state.get(field) is not None:
                    entry[field] = state[field]
            entry["updated_at"] = time.time()

    def apply_progress(self, table_name, filename, progress=None, processed_rows=None, total_rows=None):
        """`file_ingestion_progress` 브로드캐스트 경유 진행률 반영.
        엔트리가 없으면 normal 레인으로 생성 (normal 파일의 유일한 유입 경로)."""
        if not table_name or not filename:
            return
        key = self._key(table_name, filename)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = self._new_entry(table_name, filename)
                self._entries[key] = entry
            entry["status"] = "PROCESSING"
            if isinstance(progress, (int, float)) and not isinstance(progress, bool):
                entry["progress"] = max(0, min(int(progress), 100))
            if isinstance(processed_rows, int):
                entry["processed_rows"] = processed_rows
            if isinstance(total_rows, int):
                entry["total_rows"] = total_rows
            entry["updated_at"] = time.time()

    def remove(self, table_name, filename):
        """파일 완료/실패(file-processed) 시 제거 — 멱등."""
        if not table_name or not filename:
            return
        with self._lock:
            self._entries.pop(self._key(table_name, filename), None)

    def _ttl_for(self, entry) -> int:
        """[QA F1] 상태별 TTL 차등 — QUEUED는 무갱신 장기 대기가 정상이므로 긴 TTL."""
        return self._queued_ttl if entry.get("status") == "QUEUED" else self._ttl

    def snapshot(self) -> list:
        """진행 중 엔트리 목록 (오래된 것부터). TTL 초과 고아 엔트리는 이 시점에 퇴거
        (TTL은 상태별 차등 — _ttl_for 참조)."""
        now = time.time()
        with self._lock:
            stale = [k for k, e in self._entries.items()
                     if now - e["updated_at"] > self._ttl_for(e)]
            for k in stale:
                self._entries.pop(k, None)
            items = sorted(self._entries.values(), key=lambda e: e["first_seen"])
            result = []
            for e in items:
                out = dict(e)
                out["elapsed_seconds"] = int(now - e["first_seen"])
                result.append(out)
            return result

    def clear(self):
        with self._lock:
            self._entries.clear()


# 웹서버 프로세스 싱글턴
registry = IngestionActivityRegistry()
