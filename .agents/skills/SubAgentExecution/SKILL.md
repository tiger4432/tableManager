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
3. **결과 보고**: 작업이 완료되면 `agent_workspace/reports/` 디렉토리에 작업 내용, 수정한 파일 리스트, 미해결 이슈(있을 경우)를 명시한 `[자신의이름]_report.md` 파일을 `write_to_file`로 생성하십시오.
4. **종료 알림**: 사용자에게 "작업 보고서 작성을 완료했습니다." 라고 대답하고 턴을 종료하십시오.

> 주의: 다른 에이전트의 구역을 침범하지 마시고, 명시된 지시서 내의 스코프(요구사항)만 정확히 수행하는 것을 최우선으로 합니다.

