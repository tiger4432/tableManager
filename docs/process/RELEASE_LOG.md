# 📦 RELEASE_LOG — 릴리스 요약

> **Status:** 🟢 Living | **Last-verified:** 2026-08-18 | **Owner:** Lead / PM
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 규율: [CONTRIBUTING](./CONTRIBUTING.md)

불연속 `Phase N.x` 번호 체계를 대체하는 릴리스 요약입니다. 상세 이력은 [history/](../history/README.md)에 있으며, 이 문서는 **큰 흐름의 마일스톤**만 시맨틱하게 기록합니다.

**형식:** `YYYY-MM-DD | 영역 | 요약` (최신순). 상세가 필요하면 history 링크.

---

## 2026-08 — Ledger V2 & Ontology Config Explorer

- **2026-08-18 | Ledger/Ontology** | **Ledger V2 1~7단계와 Ontology Config Explorer 전체 계약 승인 완료.** manifest 단일 진입점, config-only Registry, verified batch join, RoleFrame/Pack compiler, 기존 gate/store/cursor transaction, 비파괴 `lot_event` cutover를 확정했다. Explorer는 compiled 참조 그래프·Used by·단일 context history·draft preview/review/revise/CAS activation과 반응형 3단 UI를 제공한다. 운영 reset/replay·migration·legacy 삭제는 별도 승인 전 금지. [인수인계](./FORK_SESSION_BRIEF.md) · [Ledger V2](../../ledger_v2_redesign_plan_20260817/README.md) · [Explorer 근거](../../ontology_config_explorer_plan/02_IMPLEMENTATION_AND_ACCEPTANCE.md)

## 2026-07 — 웨이퍼 맵 에디터 & 물리 지오메트리

- **2026-07-26 | Map/Overlay** | **범용 맵 오버레이의 좌표 변환을 클라 단일 구현으로 일원화** — 소스 원본 좌표를 소스 자신의 `wafer_map_metadata` 프레임으로 해석해 물리 키로 투영하므로 화면 규격 변경을 오버레이가 따라온다(서버 엔드포인트는 존치, 클라는 보정 선언 관문으로만 사용). 실패 status 6종 명시화 · 테이블 전환 시 오버레이 해제. **도메인 규칙 확정: `wafer_map_metadata`가 정렬의 유일한 기준**(셀 레벨 `grid_metadata`는 폐기 스킴). [상세](../history/20260726_225311_overlay_geometry_unified_into_client.md)
- **2026-07-21 | Map/Ingestion** | 물리 웨이퍼 지오메트리 엔진 도입, 체인 인제션 페이로드 문자열 내성 강화.
- **2026-07-19~20 | Map Editor** | 2세대 격자 맵 에디터 완성 — 회전/면반전 좌표계, E1/E2 외곽 자동 추출, 드래그 페인팅, 엑셀 복사, 메타데이터 전용 테이블(`wafer_map_metadata`), 프리셋.
- **2026-07-17 | Admin** | 브라우저 내 Monaco 코드 에디터 시스템(맵퍼/스크립트 인라인 편집, no-cache 응답).
- **2026-07-15 | Ingestion** | Silent Upsert + 하이브리드 Auto-Update 스케줄러(주석기반 크론).

## 2026-06 — RDB 전환 & 관리자 대시보드

- **2026-06-20 | Data Model** | 복합 비즈니스 키 생성 및 고유성 보장.
- **2026-06-16 | Admin/Perf** | 전용 관리자 대시보드(ingestions/chains/mappers), 배치 업서트·클라이언트 성능 최적화.
- **2026-06-13 | Data Model** | JSONB blob → 정규화 RDB(동적 네이티브 테이블) 마이그레이션.
- **2026-06-09 | Ingestion** | 체인 인제션 Pandas 배치 맵퍼, 공용 맵퍼 유틸 베이스, 폴트 톨러런스·리플레이.

## 2026-05 — 웹 클라이언트 전환

- **2026-05-25 | Frontend** | `client2` AG-Grid 웹 클라이언트 재구축 및 프로덕션 통합. PySide6 데스크톱 → QtWebEngine 셸 + 웹앱 체제로 전환.

## 2026-04 이전 — 기반 플랫폼 (구 Phase 1~80)

- 실시간 WebSocket 동기화, 가상 로딩 그리드, 데이터 계보(AuditLog), 비즈니스 키 업서트, 검색 세션 가드, Float-to-top, 트랜잭션 그룹화 등. 상세: [PROJECT_RECAP(archived)](../_archive/PROJECT_RECAP.md) 및 [history/](../history/README.md).

---

## 앞으로 (백로그)

루트 `task/` 디렉토리의 대기 작업:
- `cursor_based_pagination_pending.md`
- `total_count_sync_pending.md`
- `desktop_hybrid_wrapper_plan.md`

> 새 릴리스는 이 파일 상단(해당 월 섹션)에 한 줄 추가하고 history 상세를 링크하십시오.
