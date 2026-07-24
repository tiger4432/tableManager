# 🤖 assyManager 에이전틱 운영 환경 (Agentic Environment)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-24 | 조직 구조(총괄 + 2 PM) 반영. 개발·문서 갱신 규율은 [CONTRIBUTING.md](./CONTRIBUTING.md), 각 PM 헌장은 [server_pm](../prompts/server_pm.md)·[client_pm](../prompts/client_pm.md). 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md).

본 프로젝트는 각 분야의 전문성을 갖춘 AI 에이전트들이 상호 유기적으로 협업하는 **에이전틱 지능형 프로젝트**입니다. 본 문서는 시스템을 관리하고 고도화하는 에이전트들의 구성과 협업 규약을 설명합니다.

---

## 🏗️ 1. 멀티 에이전트 협업 체계 (총괄 + 2 도메인 PM)

시스템의 복잡도를 관리하기 위해 **총괄 PM(Lead)** 아래 **서버·클라이언트 도메인 PM 2인**을 두고, 각 PM이 필요 시 전문 스킬을 소환하여 작업한다.

```
총괄 PM (Lead)  — 아키텍처 무결성 · 경계 계약 수호 · 작업 분배 · 문서 총괄
├── Server PM   →  server/ 전 영역          [헌장: docs/prompts/server_pm.md]
└── Client PM   →  client2/ + desktop_wrapper.py   [헌장: docs/prompts/client_pm.md]
```

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

---

## 🚀 3. 신규 에이전트 온보딩 가이드
본 프로젝트에 새롭게 참여하는 에이전트는 다음 순서로 프로젝트를 파악하십시오.
1. `docs/history/`의 최신 이력 3개 읽기.
2. `docs/overview/SYSTEM_OVERVIEW.md`(SSOT)를 통해 전체 아키텍처 이해.
3. 루트 `task/` 디렉토리와 `docs/process/RELEASE_LOG.md`로 진행/백로그 확인.
4. `.agents/skills/SubAgentExecution/SKILL.md`를 통해 보고 체계 숙지.

---
**Last Updated: 2026-04-12**
