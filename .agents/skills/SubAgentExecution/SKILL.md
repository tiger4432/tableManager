---
name: SubAgentExecution
description: PM 에이전트와 하위 개발 에이전트 간의 표준 작업 명령 및 결과 보고 체계 매뉴얼
---

# PM Command Protocol (Sub-Agent 워크플로우 매뉴얼)

본 스킬 문서는 PM 에이전트(리드)와 하위 개발 에이전트들이 코드 베이스 안에서 텍스트 파일로 서로 충돌 없이 소통하고 작업을 인계하기 위한 **표준 명령/보고 프로토콜**입니다. 여러분(하위 에이전트)은 유저로부터 호출되면 가장 먼저 이 구조에 따라 행동해야 합니다.

## 1. 📂 통신 디렉토리 구조 (`agent_workspace/`)
모든 작업 지시와 보고는 프로젝트 루트의 `agent_workspace/` 폴더를 통해 이루어집니다. 더 이상 `report` 폴더를 사용하지 마십시오.

* `agent_workspace/tasks/`: PM이 당신에게 할당한 **작업 지시서(Prompt)**가 보관됩니다. (형식: `[Agent_이름]_task.md`)
* `agent_workspace/reports/`: 당신이 작업을 마친 후 PM에게 제출할 **결과 보고서**를 작성하는 곳입니다. (형식: `[Agent_이름]_report.md`)
* `agent_workspace/archive/`: 완료되어 효력을 다한 과거의 문서들이 보관되는 곳입니다.

## 2. 🐍 프로젝트 실행 환경 (환경 미준수 시 DLL 오류 발생)

**모든 하위 에이전트는 아래 `assy_manager` Conda 환경을 반드시 사용**해야 합니다.
`venv` 폴더가 존재하더라도 절대 사용하지 마십시오. 과거에 Windows Anaconda 환경과의 DLL 충돌로 `venv` 방식이 폐기되었습니다.

| 구분 | 명령어 |
|---|---|
| 환경 활성화 | `conda activate assy_manager` |
| 서버 실행 | `cd server && uvicorn main:app --reload` |
| 클라이언트 실행 | `cd client && python main.py` |
| 패키지 설치 시 | `conda run -n assy_manager pip install <패키지명>` |

> ⚠️ 터미널 프롬프트가 `(assy_manager)`로 표시되어 있는지 반드시 확인하십시오.

## 3. 🤖 하위 에이전트 행동 지침 (Action Guide)
당신이 특정 하위 에이전트(예: Agent D)로 임명받아 세션을 시작했다면 다음 순서로 임무를 수행하십시오.

1. **지시 수신**: `find_by_name` 혹은 `list_dir` 도구를 이용해 `agent_workspace/tasks/` 디렉토리를 열고, 자신에게 할당된 작업 지시서(`.md`)를 `view_file`로 정독하십시오.
2. **작업 수행**: 지시서에 포함된 코딩, 디버깅, 리팩토링 임무를 실제로 프로젝트 파일에 수행하십시오.
3. **기능 검증**: 보고서 작성 전, [**클라이언트 전수 기능 점검표**](file:///c:/Users/kk980/Developments/assyManager/docs/CLIENT_FEATURE_CHECKLIST.md)를 참조하여 기존/신규 기능에 이상이 없는지 확인하십시오.
4. **결과 보고**: 작업이 완료되면 `agent_workspace/reports/` 디렉토리에 작업 내용, 수정한 파일 리스트, 미해결 이슈(있을 경우)를 명시한 `[자신의이름]_report.md` 파일을 `write_to_file`로 생성하십시오.
5. **종료 알림**: 사용자에게 "작업 보고서 작성을 완료했습니다." 라고 대답하고 턴을 종료하십시오.

## 4. 📝 영구 기술 이력 기록 (`docs/history/`)

보고서 제출과 별개로, 모든 주요 로직 변경이나 버그 수정 사항은 프로젝트의 영구 기술 자산으로 남겨야 합니다.

* **저장 위치**: `docs/history/`
* **파일명 규칙**: `YYYYMMDD_HHMMSS_summary.md` (예: `20260412_221000_fix_ws_deadlock.md`)
* **내용**: 
  - 문제 현상 (Phenomenon)
  - 기술적 원인 분석 (Root Cause)
  - 해결 방안 및 코드 변경 핵심 요약 (Solution & Code Changes)
  - 검증 결과 (Validation)

## 5. 🤖 프로젝트 전문 에이전트 구성 (R&R)

본 프로젝트는 각 분야의 전문성을 가진 에이전트들이 협업하여 구축되었습니다. 작업 시 자신의 역할에 맞는 전문 스킬을 소환하여 사용하십시오.

| 에이전트 명칭 | 전문 분야 | 주요 담당 컴포넌트 |
|---|---|---|
| **Lead Agent (PM)** | 아키텍처 설계 & 작업 조율 | `task.md`, `technical_manual.md`, `docs/history/` |
| **Agent Excel (UI)** | 고성능 테이블 & 클립보드 | `table_model.py` (Edit/Batch), `ExcelTableView` |
| **Agent D (Sync)** | 실시간 동기화 & WebSocket | `SharedWS`, `WsListenerThread`, `broadcast_engine` |
| **Agent I (Pipeline)** | 인제션 & 아카이빙 | `advanced_ingester.py`, `directory_watcher.py` |
| **Agent Stability** | 무결성 & 예외 처리 | GC 관리, Race Condition 해결, 로깅 표준화 |

---

## 6. 🤝 협업 규약 (Collaboration Convention)
1. **영역 보존**: 각 에이전트는 자신의 담당 컴포넌트를 수정할 때 다른 에이전트가 구축한 인터페이스를 파괴하지 않도록 주의해야 합니다.
2. **이력 연동**: 모든 에이전트의 결과물은 `docs/history/`에 남겨져 Lead Agent가 전체 프로젝트의 진행 상태를 파악할 수 있게 해야 합니다.
3. **환경 공유**: 반드시 동일한 Conda 환경(`assy_manager`)에서 검증을 마친 후 보고서를 작성해야 합니다.
4. **로컬 람다/클로저 금지 (Anti-Pattern)**: 백그라운드 스레드 시그널 연결 시 PyQt/PySide6 가비지 컬렉터(GC)에 의해 연결이 소거되는 현상을 막기 위해 로컬 람다(`lambda`)나 클로저 콜백을 절대로 사용하지 마십시오. 오직 클래스의 **Bound Method**에만 연결해야 합니다.

