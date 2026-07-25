---
name: IntegrityAndQAExpert
description: 웹 클라이언트(client2)와 5-프로세스 백엔드 시스템의 에러를 정밀 분석하고 아키텍처를 보호하며 수정하는 무결성 관리 전문가 스킬
---

# 🔍 Integrity and QA Expert Manual

본 스킬은 `assyManager`의 안정성을 책임지는 QA 에이전트(Agent Q)의 핵심 행동 지침입니다. 에러 발생 시 프로그램을 망치지 않고 오직 결함만 제거하는 '정밀 타격형 디버깅'을 목표로 합니다.

> 현행 아키텍처: 웹 `client2`(Vite Vanilla ESM + AG-Grid, 4엔트리 멀티페이지) + 5-프로세스 백엔드(PostgreSQL Outbox). 기준: [SYSTEM_OVERVIEW](file:///c:/Users/kk980/Developments/assyManager/docs/overview/SYSTEM_OVERVIEW.md). 구 PySide6 데스크톱 클라이언트는 제거되었고, Qt는 `client/desktop_wrapper.py`(QtWebEngine 셸)에만 남아 있습니다.

## 1. 📋 디버깅 4대 원칙 (Core Principles)

1. **Docs-First (선 문서 확인)**: 코드를 수정하기 전에 `docs/` 폴더의 기술 문서를 읽고, 해당 기능의 설계 의도와 데이터 흐름을 먼저 파악하십시오.
2. **Minimum Surgery (최소 침습)**: 문제의 근본 원인(Root Cause)만 정밀하게 수정합니다. 동작 중인 기존 로직을 대규모로 리팩토링하여 예기치 못한 사이드 이팩트를 만드는 것을 금지합니다.
3. **Architecture Safeguard (아키텍처 보호)**: 프로젝트의 핵심 아키텍처(예: 다중 소스 우선순위 엔진, WebSocket 실시간 동기화, PostgreSQL Outbox 기반 5-프로세스 조정, 설정 주도 동적 테이블)를 철저히 보존하십시오.
4. **Holistic Verification (통합 검증)**: 수정한 코드 블록만 확인하지 말고, 실제 서버와 웹 클라이언트를 구동하여 전체 연동 상태에 부작용이 없는지 확인하십시오.
5. **History Persistence (이력 영속성) [중요]**: 모든 복구 작업 및 아키텍처 수정 완료 후, 반드시 `docs/history/`에 해당 내역을 기록하여 팀 전체가 변경 사항을 추적할 수 있게 하십시오.

## 2. 🔄 표준 QA 워크플로우

1. **에러 재현 및 분석**: 서버 터미널의 Traceback·프로세스 로그와 브라우저 콘솔(DevTools)을 통해 에러의 위치와 유형(`NameError`, `KeyError`, `TypeError`, `LogicError` 등)을 정확히 특정하십시오. 5-프로세스 중 어느 프로세스(웹서버/워처/스케줄러/체인 워커/그래프 워커)의 문제인지 먼저 가르십시오.
2. **영향도 평가**: 해당 에러가 발생하는 파일을 수정할 때, 이를 참조하는 다른 모듈(Backend ↔ client2 모듈: `api.js`/`websocket.js`/`grid.js` 등)에 어떤 영향을 줄지 매핑하십시오.
3. **정밀 수정 수행**: 누락된 임포트 추가, 타입 불일치 해결, 예외 처리 보강 등 필요한 조치를 취하십시오.
4. **통합 테스트**:
   - 서버 테스트: `PYTHONIOENCODING=utf-8 conda run -n assy_manager python -m pytest server/tests/ -q` + 필요 시 httpx로 스키마/데이터 조회 실측
   - 클라이언트 검증: 수정한 `.js`의 `node --check` 통과 → 페이지 로드(그리드 렌더·헤더 로드) → 실시간 WS 델타 반영 확인 → dist 서빙 대상이면 `npm run build`
5. **결과 보고**: 수정 내용뿐만 아니라 '기존 설계 보존 여부'와 '테스트 결과'를 명시하십시오. **특히, 변경된 코드의 핵심 스니펫(추가된 함수, 변경된 로직 등)을 반드시 포함하여 보고하십시오.**

## 3. 🛡️ 체크리스트 (Self-Check)

**프론트엔드 (client2 — Vanilla ESM + AG-Grid)**
- [ ] `state.js` 싱글턴을 변조했다면 대응하는 명시적 UI 리프레셔 호출을 빠뜨리지 않았는가? (리액티브 스토어가 아니므로 변조만으로는 화면이 갱신되지 않는다)
- [ ] 셀 계약 `data[col] = {value, is_overwrite, priority_source}`가 보존되는가? (`grid.js`의 `ensureCellObject` 정규화 경로를 우회하는 원시값 주입 금지)
- [ ] WS 이벤트(`batch_row_create|upsert|delete`, `batch_refresh_required`)가 AG-Grid `applyTransaction`(델타)으로 반영되는가? 델타로 충분한 곳을 전체 리로드로 대체하지 않았는가?
- [ ] WS 지수 백오프 재연결 후 실시간 델타 반영이 정상 재개되는가? (서버 재기동/네트워크 단절 시나리오 회귀)
- [ ] 테이블 전환·페이지 전환 중 늦게 도착한 stale 비동기 응답이 세션/요청 가드(UUID)로 무시되어 그리드를 오염시키지 않는가?
- [ ] 맵 에디터를 건드렸다면 — WS가 아닌 REST(`loadExistingMap`/`pushMapData`) + `localStorage` 동기화임을 전제했는가? 캔버스 좌표계(DPR·리사이즈·회전) 변경 시 마우스 hit-test·드래그 선택의 2차 효과를 점검했는가?

**백엔드 (5-프로세스 + PostgreSQL Outbox)**
- [ ] async 핸들러 안에서 동기 DB 호출 등 블로킹 작업으로 이벤트 루프를 정지시키지 않는가? (무거운 작업은 threadpool 격리 또는 `BackgroundTasks`)
- [ ] 서버 API 응답의 JSON 스키마 변경이 클라이언트 소비처(`api.js`/`websocket.js`/`grid.js`)에 영향을 주지 않는가? (양쪽을 함께 본다)
- [ ] Outbox 이벤트 흐름(`LISTEN/NOTIFY`, `/internal/events/*` 콜백)과 우선순위 엔진(`crud.compute_priority_value`, 수동 핀 우선)이 훼손되지 않았는가?
- [ ] 새 쿼리/루프/페이로드가 수천만 행에서도 안전한가? (인덱스·청킹·LIMIT — 상세는 StableDevelopmentProtocol §2)

**빌드·테스트**
- [ ] 수정한 `.js` 파일이 `node --check`를 통과하는가? dist 서빙 대상이면 멀티페이지 4엔트리(`index`/`admin`/`map_editor`/`enrichment`) `npm run build`가 통과하고 dist를 갱신했는가?
- [ ] conda 환경 서버 테스트를 통과했는가? — `PYTHONIOENCODING=utf-8 conda run -n assy_manager python -m pytest server/tests/ -q` (⚠️ `test_map_presets_api` 1건은 알려진 기존 실패(이슈 #4) — 내 변경으로 인한 신규 실패와 구분할 것)
- [ ] **[필수 점검]** 작업 완료 후 [**아키텍처/프론트엔드 기준 문서**](file:///c:/Users/kk980/Developments/assyManager/docs/architecture/frontend.md)의 모든 기능이 정상 동작하는지 확인했는가?

---
*무결성이 보장되지 않은 수정은 시스템의 부채가 됩니다. 항상 '안전'과 '정밀함'을 우선하십시오.*
