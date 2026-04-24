# AssyManager 에이전트 Starting Prompt (Master Guideline)

이 문서는 `AssyManager` 프로젝트의 에이전트가 준수해야 할 핵심 지침과 기술 표준을 정의합니다. 모든 에이전트는 작업을 시작하기 전 이 가이드를 숙지해야 합니다.

## ⚖️ 1. 핵심 철학 (Core Philosophy)
- **무결성 우선 (Integrity First)**: 데이터 정합성과 앱의 안정성은 모든 기능 구현의 최우선 가치다.
- **예외 없는 방어 (Defensive Programming)**: 네트워크 지연, 리소스 소멸, 연타 클릭 등 모든 예외 상황을 설계 단계에서 차단한다.
- **기록으로의 자산화 (Documentation as Asset)**: 단순 코딩이 아닌, 시스템의 설계 의도와 변화 과정을 정교하게 기록한다.

## 🛠️ 2. 기술 개발 표준 (Technical Standards)

### A. 비동기 처리 및 안전성
- **Thread Safety**: 모든 백그라운드 작업은 `QRunnable`을 사용하며, 워커의 시그널 발생부는 반드시 `RuntimeError` 방어 래퍼를 씌운다.
- **GC 보호 (Callback Persistence)**: 비동기 응답 핸들러(Slot)는 지역 클로저가 아닌 클래스 멤버 메서드에 연결하고, 필요한 컨텍스트는 멤버 변수에 저장하여 가비지 컬렉션에 의한 신호 유실을 원천 차단한다.
- **Status Feedback**: 모든 비동기 구간은 좌하단 상태바(`set_status`)를 통해 사용자에게 소요 시간과 성공 여부를 즉시 보고한다.

### B. 내비게이션 및 데이터 엔지니어링
- **Data Jump Logic**: 서버 측에서의 인덱스 탐색(`Discovery`) -> 모델 점프 우선순위 반영 -> 가상 테이블 확장 순으로 진행한다.
- **Server-side Integrity**: 히스토리 추적 시 서버에서 대상 행의 실제 존재 여부(`EXISTS`)를 검증하여 유효하지 않은 이동 시도를 사전에 차단한다.
- **Sync Debouncing**: WebSocket 이벤트는 300ms 디바운싱을 거쳐 화면을 갱신함으로써 UI 스래싱을 방지한다.

## 📝 3. 형상 관리 및 기록 표준 (Documentation)

### A. 히스토리 기록 (docs/history/) - [전 필수 단계]
- **명칭**: `docs/history/YYYYMMDD_HHMMSS_설명이름.md`
- **필수 포함 사항**:
    - **Context**: 작업의 기술적 배경과 해결하고자 한 문제.
    - **Architecture**: 데이터 흐름 및 클래스 관계의 변화.
    - **Code Snippets**: 핵심 로직의 원형을 포함하여 향후 유지보수를 돕는다.
    - **Impact**: 해당 변경이 시스템 전체에 미치는 영향 및 검증 결과.

### B. 작업 워크플로우
- **Planning Phase**: 복잡한 작업은 연구 -> 계획서 작성 -> 사용자 승인 단계를 거친다.
- **Execution Tracking**: `task.md`를 통해 실행 과정을 실시간 추적한다.
- **Final Report**: `walkthrough.md`를 통해 시각적 피드백과 최종 요약을 제공한다.

## 🎨 4. 디자인 및 미학 (Aesthetics)
- **Premium Design**: 브라우저 기본 색상을 지양하고 최적화된 HSL 배색, 구글 폰트 적용, 부드러운 애니메이션(Micro-interaction)을 적용하여 고품질의 UX를 제공한다.
- **Glassmorphism**: 현대적인 레이아웃과 블러 효과를 적재적소에 활용한다.

---
*AssyManager Enterprise - System Governance v2.1*
