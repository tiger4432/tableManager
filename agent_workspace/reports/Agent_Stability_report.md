# 📝 하위 에이전트 작업 보고서 (Agent Stability)

* **작업 대상**: `client/ui/history_logic.py`
* **작업 내용**: HistoryNavigator의 3가지 핵심 취약점 보완

## 1. 🔍 필터(검색) 충돌 시 자동 해제 및 재추적 (Task 1)
* **현상**: 서버 검색에 의해 필터링되거나, 클라이언트 ProxyModel에 의해 데이터가 숨겨져 있을 때 점프가 침묵하는 현상
* **조치**: 
  - `_step4_final_hop` (서버 필터) 및 `_final_scroll` (로컬 필터) 양쪽 모두에 방어 로직 추가.
  - 타겟을 찾지 못했을 때 검색 쿼리가 켜져 있다면, 상태바에 `⚠️ 검색 필터 해제 후 재탐색...` 메시지를 띄움.
  - `_filter_bar._search_box.clear()`를 호출하여 강제로 필터를 초기화함.
  - 600ms 뒤(API 페치 대기시간 고려), 기존 컨텍스트 정보(`self._ctx["data_obj"]`)를 이용해 `navigate_to_log`를 재귀적으로 재호출하여 완벽하게 타겟을 추적해 내도록 고도화 완료.

## 2. ⚡ 레이아웃 안정화 타이머 개선 (Task 2)
* **조치**: `QTimer.singleShot(10, ...)` 을 `QTimer.singleShot(0, ...)` 으로 교체하여, 시스템 성능과 무관하게 항상 안전하게 Qt 이벤트 큐(Paint 이벤트 등) 처리를 보장.

## 3. 🛡️ 좀비 콜백 방지 (Task 3)
* **조치**: `source_model.fetch_finished.connect` 사용 시 `Qt.ConnectionType.UniqueConnection` 속성을 명시하여 다중 연결로 인한 중복 호출(메모리 누수 및 오작동)을 원천 차단.

---

> **미해결 이슈 및 다음 단계**:
> 클라이언트 측 1, 2, 3번 태스크 완료. 서버 쪽 트랜잭션 그룹화(Task 4)는 PM 판단에 따라 진행 가능합니다.
