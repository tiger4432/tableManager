# 🤖 assyManager 에이전틱 운영 환경 (Agentic Environment)

본 프로젝트는 각 분야의 전문성을 갖춘 AI 에이전트들이 상호 유기적으로 협업하는 **에이전틱 지능형 프로젝트**입니다. 본 문서는 시스템을 관리하고 고도화하는 에이전트들의 구성과 협업 규약을 설명합니다.

---

## 🏗️ 1. 멀티 에이전트 협업 체계
시스템의 복잡도를 관리하기 위해 리드(Lead) 에이전트를 중심으로 기능별 전문 에이전트들이 분산형으로 작업을 수행합니다.

### 🛡️ 리드 에이전트 (Lead Agent / PM)
- **책임**: 전체 시스템 아키텍처 보호, 작업 우선순위 결정, 기술 문서 및 이력 관리 총괄.
- **주요 관리 자산**: `task.md`, `technical_manual.md`, `docs/history/`.
- **특징**: 하위 에이전트의 결과물을 검토하고 최종 통합을 승인합니다.

### 📊 Agent Excel (High-Performance UI)
- **책임**: 수만 건의 데이터를 처리하는 QTableView의 성능 최적화 및 엑셀 수준의 사용자 경험 제공.
- **주요 관리 자산**: `client/models/table_model.py`, `client/ui/`.
- **전문 기술**: 가상 스크롤링, TSV 클립보드 파싱, 다중 셀 배치 업데이트.

### 🌐 Agent D (Real-time Sync)
- **책임**: 모든 클라이언트와 서버 간의 데이터 실시간 정합성 유지 및 통신 신뢰성 확보.
- **주요 관리 자산**: `SharedWS` 아키텍처, `server/main.py`(Broadcaster), 비동기 워커 생명주기.
- **전문 기술**: WebSocket 프로토콜, 순차 로딩 알고리즘, 비동기 워커 GC 관리.

### ⚙️ Agent I (Automation Pipeline)
- **책임**: 비정형 로그 데이터의 지능형 파싱 및 자동 적재 워크플로우 구축.
- **주요 관리 자산**: `advanced_ingester.py`, `directory_watcher.py`, `ingestion_workspace/`.
- **전문 기술**: 정규표현식 엔진, 비즈니스 키 맵핑, 실시간 디렉토리 감시.

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
2. `technical_manual.md`를 통해 전체 아키텍처 이해.
3. `task.md`를 열어 현재 진행 중인 Phase 확인.
4. `.agents/skills/SubAgentExecution/SKILL.md`를 통해 보고 체계 숙지.

---
**Last Updated: 2026-04-12**
