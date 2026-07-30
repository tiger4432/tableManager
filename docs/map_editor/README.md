# 🗺️ Wafer Map Editor Documentation Index

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (**§2.3 요약줄 정정** — 「치수 변경이 저장 좌표를 옮긴다 → 그것이 **프레임 채택 거절 규율**의 근거」에서 뒷부분이 가리킬 대상을 잃었다(**프레임 채택은 `61440e6`+`94b9baa`에서 폐기**, 소스에 심볼 0건). 근거는 이제 「셀은 칸이 아니라 **번호**를 붙들고 칸은 파생이다」이고, **유효 다이 근거 변경도** 저장 좌표를 옮긴다(`da8f390` — `box`가 마스크를 근거로 삼는다). 좌표 규약 정본은 [MAP_EDITOR_SPEC §1의 0)](../spec/MAP_EDITOR_SPEC.md). 함께: **`architecture_and_management.md`에 Status 배지 신설**(정본으로 지목되는 문서인데 신선도를 말하는 줄이 없었다). 직전 `ae2811c` — ① 문서 목록의 `philosophy.md` 항목에 **§2.3**(고정되는 것은 방향이고 원점은 아니다 · 원점 마커는 다이가 아니라 화면 자리) 반영 ② 빠른 요약의 왕복 항목에 **거부 5갈래**와 **179개 중 27개만 지문 보유**를 명기 — 왕복을 일반 기능으로 읽으면 안 됩니다. 직전 `c9bf2c7`) | **Owner:** UI/Map | **Source-of-truth:** `client2/src/map_editor.js`
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
   * **§2.3 시각 좌표계가 화면에 고정하는 것과 하지 않는 것** (2026-07-30 정정) — 고정되는 것은 **축의 방향**이고 **원점(anchor)은 아니다**(`box.minC`가 회전·면의 함수). 라이브 모집단은 179개 중 회전 의존 원점 0개이지만 **코드가 그것을 보장하지는 않는다**. 그리고 **원점 마커는 다이가 아니라 화면 자리를 표시한다**(등방 맵에서도 네 회전에서 네 개의 다른 다이 위에 앉는다). 🔴 여기서 **치수 변경(그리고 유효 다이 근거 변경)이 저장 좌표를 옮긴다**는 성질이 나오고, 그것이 「셀은 칸이 아니라 **번호**를 붙들고 칸은 파생이다」([MAP_EDITOR_SPEC §5.7-bis](../spec/MAP_EDITOR_SPEC.md), 좌표 규약은 같은 문서 **§1의 0)**)의 근거다. ⚠️ 종전 이 줄은 *"프레임 채택 거절 규율의 근거"*라고 적었는데, **프레임 채택은 2026-07-30에 폐기됐다**(`61440e6`+`94b9baa` — 소스에 심볼 0건)

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
* **회사 양식 왕복 (COPY HEADER MODE ↔ Ctrl+V, 2026-07-30)**: `📋 Copy to Excel`이 사용자 회사의 본딩맵 양식(TITLE + 열 그룹 띠 + 우측 `VALUE | COUNT | STACK | DESC` 보조표)으로 나가고, **같은 화면에서 Ctrl+V로 되읽힙니다.** 붙여넣기는 이 화면의 **운영자 동작**입니다 — 새 버튼·새 메뉴 없이 **확인창 1회**, 그리고 **서버에는 아무것도 쓰지 않습니다**(저장은 여전히 `⚡ Push` 하나). 격자는 빈 칸까지 복원되고 DOE는 `VALUE`·`STACK`·`DESC`만 복원되며(자재·COLOR는 왕복하지 않고 `COUNT`는 폐기), 열 수·행 수·정체·**회전/면 지문 불일치**·**지문 부재** 다섯 중 하나라도 걸리면 사유를 붙여 **거부**합니다. ⚠️ **2026-07-30 `ae2811c`부터 지문이 없는 프레임에서는 붙여넣기가 거부됩니다 — 선언 맵 179개 중 노치가 격자 안에 들어오는 것은 27개이므로 나머지 152개에서 왕복이 성립하지 않습니다**(안전에서는 옳고 능력에서는 비쌉니다. 양식 후속은 대기열·미구현). 계약 전문 [MAP_EDITOR_SPEC §4-ter](../spec/MAP_EDITOR_SPEC.md) · 사용자 안내 [DOE_GUIDE §4.2](../guide/DOE_GUIDE.md)
