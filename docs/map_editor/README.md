# 🗺️ Wafer Map Editor Documentation Index

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (`c9bf2c7` — 회사 양식 왕복(COPY HEADER MODE ↔ Ctrl+V)을 빠른 요약에 등재, 문서 목록에 §4-ter·§5.8 반영. 배지는 이번에 신설 — [CONTRIBUTING §3](../process/CONTRIBUTING.md)) | **Owner:** UI/Map | **Source-of-truth:** `client2/src/map_editor.js`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 현행 계약 정본: [spec/MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)

본 디렉토리는 **AssyManager 2세대 웨이퍼 맵 에디터(Wafer Map Editor)**의 전체 설계 사상, 시스템 아키텍처, 수치해석적 알고리즘, API 규격 및 관리 가이드를 수록한 공식 통합 문서 모음입니다.

---

## 📚 문서 목록 (Documentation Directory)

1. **[웨이퍼 맵 관리 및 아키텍처 가이드 (`architecture_and_management.md`)](file:///c:/Users/kk980/Developments/assyManager/docs/map_editor/architecture_and_management.md)**
   * `wafer_map_metadata` 전용 메타데이터 관리 아키텍처
   * 필수 `map_key_columns` 설정 및 테이블 필터링 규칙
   * Clean Map Replacement (`replace_map: true`) 클린 덮어쓰기 파이프라인 (유령 셀 0% 차단)
   * 4-Neighbor BFS Distance Transform 기반 E1/E2 정밀 외곽 셀 자동 추출 알고리즘
   * 4단계 기능별 좌측 사이드바 UI 레이아웃 및 복원 옵션 팝업 처리 로직

2. **[격자 맵 좌표계 설계 철학 (`philosophy.md`)](file:///c:/Users/kk980/Developments/assyManager/docs/map_editor/philosophy.md)**
   * WYSIWYG (What You See Is What You Get) 화면 기준 저장 철학
   * 물리 기판 공간 배치(Physical Alignment)와 화면 시각 눈금(Screen Visual)의 이원화 매핑
   * 회전/대칭 상태에서의 공정 데이터 무결성 보증 수식

3. **[프론트엔드 함수 & API 규격서 — `spec/MAP_EDITOR_SPEC.md`](../spec/MAP_EDITOR_SPEC.md)**
   * 자바스크립트 모듈 ([`client2/src/map_editor.js`](file:///c:/Users/kk980/Developments/assyManager/client2/src/map_editor.js)) 전체 함수 명세
   * 좌표 기하 변환 및 Bounding Box 연산 레퍼런스
   * §4 렌더링 라이프사이클 · **§4-ter 회사 양식 왕복 계약(COPY HEADER MODE ↔ Ctrl+V)** · **§5 범용 맵 오버레이(정렬 계약, §5.8 로드 시 프리셋 라우팅 포함)** · **§6 전사 계획**
   * 🗄️ 이 자리에 있던 `specification.md`(선행판)는 2026-07-27 [_archive](../_archive/map_editor_specification.md)로 이관됐습니다 — 위 문서가 그 내용을 포함한 정본입니다

---

## 🚀 빠른 요약 (Quick Architectural Summary)

* **Physical Geometry vs. Grid Topology**: 실물 웨이퍼 직경/오프셋(Physical)과 화면 격자 회전/반전(Topology)의 명확한 도메인 분리
* **Clean Replacement**: 맵 저장 시 `map_key_columns` 기준 기존 DB 행 SQL Bulk Purge 후 신규 활성 칩만 재적재 — 직렬화가 화면보다 적게 담기면 Push 자체를 거부(적재 대조 게이트)하고, 대상 테이블에 맵 계약(맵 키 + X/Y/값 + 시스템 컬럼) 밖의 데이터 컬럼이 있으면 **로그형 테이블로 판정해 Push를 거부**합니다(로그형 대상 게이트 — 맵으로 조회만 가능. 사이트가 table_config에 `map_push_ok: true`를 선언한 테이블만 소실 확인 confirm 1회로 완화). 응답 `scope: {filters, deleted, inserted}`가 실제 purge 범위를 알리고, 범위를 못 잡으면 400입니다. [MAP_EDITOR_SPEC §6.0-ter](../spec/MAP_EDITOR_SPEC.md)
* **Zero Ghost Cells**: 오리진/규격 변경 시 잔존 데이터 유동 문제를 100% 차단
* **회사 양식 왕복 (COPY HEADER MODE ↔ Ctrl+V, 2026-07-30)**: `📋 Copy to Excel`이 사용자 회사의 본딩맵 양식(TITLE + 열 그룹 띠 + 우측 `VALUE | COUNT | STACK | DESC` 보조표)으로 나가고, **같은 화면에서 Ctrl+V로 되읽힙니다.** 붙여넣기는 이 화면의 **운영자 동작**입니다 — 새 버튼·새 메뉴 없이 **확인창 1회**, 그리고 **서버에는 아무것도 쓰지 않습니다**(저장은 여전히 `⚡ Push` 하나). 격자는 빈 칸까지 복원되고 DOE는 `VALUE`·`STACK`·`DESC`만 복원되며(자재·COLOR는 왕복하지 않고 `COUNT`는 폐기), 열 수·행 수·정체·**회전/면 지문** 중 하나라도 어긋나면 사유를 붙여 **거부**합니다. 계약 전문 [MAP_EDITOR_SPEC §4-ter](../spec/MAP_EDITOR_SPEC.md) · 사용자 안내 [DOE_GUIDE §4.2](../guide/DOE_GUIDE.md)
