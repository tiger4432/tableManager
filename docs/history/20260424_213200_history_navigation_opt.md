# 프로젝트 이력: 히스토리 내비게이션 및 동기화 최적화 상세 보고 (2026-04-24)

## 1. 개요
대규모 반도체 공정 데이터셋(백만 행 이상)에서 과거 변경 이력을 추적할 때 발생하는 비동기 응답 유실과 내비게이션 불일치 문제를 해결함. 특히 PySide의 가비지 컬렉션(GC) 특성에 따른 시그널 유실 현상을 상태 기반 구조로 혁신하여 데이터 무결성을 확보함.

## 2. 주요 기술적 변경 사항

### 2.1 상태 기반 내비게이션 컨텍스트 (Navigation Guard & Context)
비동기 콜백(Closure)이 메모리에서 일찍 제거되는 문제를 방지하기 위해, 모든 탐색 상태를 클래스 멤버 변수에 저장하도록 개편함.

```python
# [panel_history.py]
def _on_item_clicked(self, item):
    # 1. 내비게이션 정보 저장 (GC 유실 방지)
    self._current_nav_ctx = {
        "row_id": row_id, "table_name": table_name,
        "source_model": source_model, "table_view": table_view
    }
    # 2. 클래스 메서드 슬롯에 직접 연결 (신뢰성 확보)
    worker.signals.finished.connect(self._handle_discovery_result)
    QThreadPool.globalInstance().start(worker)

def _handle_discovery_result(self, result):
    ctx = getattr(self, "_current_nav_ctx", None)
    if not ctx: return
    # ctx에서 row_id 등을 복원하여 후속 작업 수행
```

### 2.2 가상화 모델의 점프 우선순위 (Model Jump Logic)
기존 `fetchMore` 로직은 배경 페칭(Fetching) 중일 때 새로운 요청을 차단했으나, 히스토리 기반의 "강제 이동(Jump)" 요청은 이를 무시하고 최우선 처리하도록 설계함.

```python
# [table_model.py]
def fetchMore(self, parent=QModelIndex()):
    is_jump = (self._pending_target_skip is not None)
    
    # [Point] 점프 요청 시 기존 로딩 가드를 우회
    if self._fetching and not is_jump: return

    if is_jump:
        # 목적지(Skip)가 노출 범위를 넘어서면 가상 카운트 즉시 확장
        if self._pending_target_skip + self._chunk_size > self._exposed_rows:
            target = self._pending_target_skip + self._chunk_size
            self.beginInsertRows(QModelIndex(), self._exposed_rows, target - 1)
            self._exposed_rows = target
            self.endInsertRows()
```

### 2.3 실시간 이벤트 디바운싱 (Sync Debouncing)
WebSocket을 통한 빈번한 감사 로그 유입 시 네트워크 오버헤드를 줄이기 위해 300ms 디바운싱 타이머 적용.

```python
# [panel_history.py]
def log_event(self, data):
    if hasattr(self, "_refresh_timer"): self._refresh_timer.stop()
    else:
        self._refresh_timer = QTimer(setSingleShot=True)
        self._refresh_timer.timeout.connect(self.refresh_history)
    self._refresh_timer.start(300) # 0.3초 내 중복 요청 통합
```

### 2.4 서버 측 삭제 필터링 (Server-side Filtering)
이미 삭제된 행에 대한 로그가 히스토리에 노출되어 내비게이션 실패를 유도하는 현상을 방지하기 위해 `EXISTS` 서브쿼리 필터 추가.

```sql
-- [server/main.py]
SELECT * FROM audit_logs a 
WHERE EXISTS (
    SELECT 1 FROM inventory_master i WHERE i.row_id = a.row_id
)
ORDER BY timestamp DESC LIMIT 500
```

## 3. 검증 및 결과
- **정밀도**: 100만 행 데이터 중 특정 시점의 변경 행으로 1.0초 이내에 정확히 스크롤 및 포커싱 성공.
- **안정성**: 탭 전환, 탭 닫기, 코드 실시간 반영(Jurigged) 중에도 비정상 종료 없이 내비게이션 가드 정상 작동.
- **사용성**: 모든 비동기 구간에 상태바(Status Bar) 진행 상황을 노출하여 사용자 대기 경험 개선.

---
*AssyManager Enterprise - Core Navigation System Documentation*
