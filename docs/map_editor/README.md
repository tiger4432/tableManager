# 🗺️ Wafer Map Editor Documentation Index

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
   * §4 렌더링 라이프사이클 · **§5 범용 맵 오버레이(정렬 계약)** · **§6 전사 계획**
   * 🗄️ 이 자리에 있던 `specification.md`(선행판)는 2026-07-27 [_archive](../_archive/map_editor_specification.md)로 이관됐습니다 — 위 문서가 그 내용을 포함한 정본입니다

---

## 🚀 빠른 요약 (Quick Architectural Summary)

* **Physical Geometry vs. Grid Topology**: 실물 웨이퍼 직경/오프셋(Physical)과 화면 격자 회전/반전(Topology)의 명확한 도메인 분리
* **Clean Replacement**: 맵 저장 시 `map_key_columns` 기준 기존 DB 행 SQL Bulk Purge 후 신규 활성 칩만 재적재 — 직렬화가 화면보다 적게 담기면 Push 자체를 거부(적재 대조 게이트, [MAP_EDITOR_SPEC §6.0-ter](../spec/MAP_EDITOR_SPEC.md))
* **Zero Ghost Cells**: 오리진/규격 변경 시 잔존 데이터 유동 문제를 100% 차단
