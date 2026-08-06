# 🤖 assyManager 에이전틱 운영 환경 (Agentic Environment)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-06 | 🔴 **[2026-08-06 정정] 이 문서는 「총괄 + 도메인 PM 2인」 조직을 설명하면서 `.claude/agents/`에 정의가 훨씬 많은 상태로 **넉 달 가까이** 굴렀습니다.** §1의 명단과 §3의 온보딩 순서를 현행으로 맞췄습니다. ⚠️ **그리고 이 문서는 자기 날짜를 *두 개* 갖고 있었습니다** — 헤더 `Last-verified: 2026-07-26`과 꼬리 `Last Updated: 2026-04-12`. **자기 날짜가 둘인 문서는 어느 쪽도 증거가 아니므로** 꼬리를 없애고 헤더 하나로 통일했습니다. 개발·문서 갱신 규율은 [CONTRIBUTING.md](./CONTRIBUTING.md), 각 PM 헌장은 [server_pm](../prompts/server_pm.md)·[client_pm](../prompts/client_pm.md). 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md).

본 프로젝트는 각 분야의 전문성을 갖춘 AI 에이전트들이 상호 유기적으로 협업하는 **에이전틱 지능형 프로젝트**입니다. 본 문서는 시스템을 관리하고 고도화하는 에이전트들의 구성과 협업 규약을 설명합니다.

---

## 🏗️ 1. 멀티 에이전트 협업 체계

시스템의 복잡도를 관리하기 위해 **총괄 PM(Lead)** 아래 도메인·역할별 에이전트를 두고, 각자 자기 소관 파일만 건드린다.

> 🔴 **정본은 `.claude/agents/*.md`이고 이 절은 그 지도다. 명단 옆에 수를 적지 않는다** — 종전 이 자리는 「총괄 + 2 도메인 PM」이었고 그 사이에 아홉이 더 생겼다. **역할이 늘어날 때 이 문단을 고치는 사람은 없다**는 것이 지난 넉 달의 실측이므로, 세지 말고 `ls .claude/agents/`를 보라.

```
총괄 PM (lead-pm)  — 아키텍처 무결성 · 경계 계약 수호 · 작업 분배 · 문서 총괄
│
├─ 구현 도메인
│   ├── server-pm       →  server/ 전 영역                 [헌장: docs/prompts/server_pm.md]
│   ├── client-pm       →  client2/ + desktop_wrapper.py   [헌장: docs/prompts/client_pm.md]
│   ├── map-pm          →  맵 에디터·좌표·오버레이·DOE (client-pm이 아니라 이쪽)
│   └── ontology-pm     →  그래프 머티리얼라이저·온톨로지 매핑·graph/trace 뷰어
│
├─ 문서 (🔴 파일이 안 겹쳐서 **동시에** 돈다 — 그것이 분할의 목적이다)
│   ├── doc-keeper      →  리빙 문서 동기화 · PRIMITIVES
│   ├── doc-historian   →  docs/history/** + 인덱스 재생성
│   ├── code-mapper     →  docs/architecture/CODE_MAP.md
│   └── doc-auditor     →  검수 전담 (**쓰지 않는다** — 쓴 사람은 자기 것을 검수할 수 없다)
│
└─ 검수·이음매·표현
    ├── qa-reviewer     →  적대적 코드 검수 (GO / GO-WITH-FIXES / NO-GO)
    ├── contract-keeper →  contracts/<name>/ — 두 구현이 같은 답을 내야 하는 자리
    └── ui-designer     →  로직 안 건드리는 시각·인터랙션 작업
```

🔴 **보드(`docs/process/PROJECT_STATUS.md`)는 총괄 전담이다** — 다른 에이전트는 제안만 남기고 직접 고치지 않는다.

### 🛡️ 총괄 PM (Lead)
- **책임**: 전체 아키텍처 보호, 작업 분배, **서버-클라이언트 경계 계약(REST·WS·셀 형태·스키마) 수호**, 기술 문서·이력 총괄.
- **주요 관리 자산**: `docs/overview/SYSTEM_OVERVIEW.md`(SSOT), `docs/process/`, `docs/history/`.
- **헌장**: [`docs/prompts/starting_prompt.md`](../prompts/starting_prompt.md) §0.

### 🖥️ Server PM (Backend Domain)
- **책임**: `server/` 전 영역 — API/CRUD, 레이어링 엔진, 인제션 파이프라인, 체인 워커, 그래프 동기화, Auto-Update, DB.
- **스킬**: `DataIngester`, `WebSocketExpert`(서버측), `IntegrityAndQAExpert`.
- **헌장**: [`docs/prompts/server_pm.md`](../prompts/server_pm.md).

### 🖼️ Client PM (Frontend Domain)
- **책임**: 웹 `client2`(AG-Grid 그리드, 클립보드, 이력 타임라인, 어드민, 맵 에디터) + QtWebEngine 데스크톱 셸.
- **스킬**: `ExcelInteractionExpert`, `PanelUIExpert`, `WebSocketExpert`(클라측).
- **헌장**: [`docs/prompts/client_pm.md`](../prompts/client_pm.md).

> 경계 계약(양측 공유 규약)은 어느 PM도 단독 변경 불가 — 총괄이 양측을 동시 조율한다.

---

## 🤝 2. 에이전트 협업 규약 (Protocol)

### A. 기술 이력 강제 기록 (`docs/history/`)
모든 에이전트는 주요 코드 변경이나 버그 수정 시 반드시 `YYYYMMDD_HHMMSS_summary.md` 형식의 이력을 남겨야 합니다. 이는 다른 에이전트가 문맥을 파악하는 유일한 영구 레퍼런스입니다.

### B. 전문 분야 존중 (Domain Respect)
자신의 전문 영역 밖의 파일을 수정할 때는 반드시 해당 영역 담당 에이전트(혹은 리드)가 구축한 인터페이스와 주석 규칙을 준수해야 합니다.

### C. 환경 무결성 (Environment Integrity)
Conda 환경(`assy_manager`)에서 검증되지 않은 코드는 절대 커밋하거나 보고하지 않습니다. 윈도우 DLL 충돌 및 패키지 정합성을 에이전트 선에서 항시 체크합니다.

### D. 산출 언어 규약 (사용자 지시 2026-07-26 · `6ac2ac9`)
**에이전트가 산출하는 텍스트는 영어로 씁니다.** 기준은 "누가 읽는가"입니다 — 에이전트가 읽는 것은 영어, 사람이 읽는 것은 한국어.

| 영어 | 한국어 유지 |
|---|---|
| `agent_workspace/reports/**` 보고서 | 사용자에게 직접 보이는 **UI 문자열·토스트·에러 문구** |
| 코드에 **새로 쓰거나 수정하는 주석** | **`docs/**` 프로젝트 문서**(사용자가 읽는 산출물) |
| 서브에이전트 지시서·메시지 | 기존 주석의 일괄 번역은 하지 않음(**건드리는 줄만** 영어로) |
| 커밋 메시지 | |

각 에이전트의 교훈 파일(`agent_workspace/memory/*.md`) 공통 절에 같은 규약이 실려 있으며, 착수 시 Pre-Flight로 로드합니다.

---

## 🚀 3. 신규 에이전트 온보딩 가이드
본 프로젝트에 새롭게 참여하는 에이전트는 다음 순서로 프로젝트를 파악하십시오.
1. `docs/history/`의 최신 이력 3개 읽기.
2. `docs/overview/SYSTEM_OVERVIEW.md`(SSOT)를 통해 전체 아키텍처 이해.
3. 루트 `task/` 디렉토리와 `docs/process/RELEASE_LOG.md`로 진행/백로그 확인.
4. `.agents/skills/SubAgentExecution/SKILL.md`를 통해 보고 체계 숙지.
5. **자기 역할 파일** `.claude/agents/<역할>.md`와 **자기 교훈 파일** `agent_workspace/memory/<역할>.md`를 읽기 — 후자는 **반복 함정 목록**이고, 신규 교훈은 보고서에 *제안*하지 직접 추가하지 않는다.
6. 문서 규율은 [CONTRIBUTING](./CONTRIBUTING.md), 소유 매핑은 [DOC_OWNERSHIP](./DOC_OWNERSHIP.md).

---
> ⚠️ **이 문서에 두 번째 날짜를 만들지 마십시오.** 여기 `**Last Updated: 2026-04-12**`가 있었고 헤더는 `2026-07-26`이었습니다 — **3개월 반 어긋난 두 날짜를 한 문서가 동시에 주장**하면 독자는 어느 쪽도 못 믿습니다. 날짜는 헤더의 `Last-verified` **하나**입니다.
