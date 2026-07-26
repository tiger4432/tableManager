# 테이블 전환 시 오버레이 해제 + `wafer_map_metadata`를 정렬의 유일한 기준으로 확정

> 커밋 `251dbfd` · 2026-07-26 22:58 · 도메인 Client / 맵 에디터 + 도메인 규칙
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md) · 선행: [오버레이 클라 일원화](./20260726_225311_overlay_geometry_unified_into_client.md)

## 1. 코드 변경 — `switchTable`이 오버레이를 해제한다

### 배경

`switchTable`은 `gridData`를 비웠지만 **오버레이 레이어는 그대로 세워 뒀다.** 서 있는 오버레이는 `가져오기` 버튼이 살아 있으므로, 테이블을 바꾼 뒤 그 버튼을 누르면 **이전 테이블의 값이 새 테이블의 `gridData`에 써졌다.** 세 줄 위의 주석이 이미 셀에 대해 정확히 그 위험을 경고하고 있었는데, 오버레이가 규칙에서 빠져 있었다.

맵 로드(`loadExistingMap`)는 이미 같은 상황에서 해제 + 토스트를 하고 있었다. 즉 신설이 아니라 **누락 지점을 규칙에 편입**한 것이다.

### 변경

```js
// client2/src/map_editor.js — switchTable
gridData = {};
loadedFCells.clear();
// Overlays belong to the previous table's frame, so ⓑ above applies to them
// verbatim: an overlay left behind stays importable, and importing it writes
// the old table's values into this one. Clearing gridData alone did not close
// that path. Matches what a map load already does.
if (overlayLayers.length > 0) {
  clearOverlayLayers();
  showToast('테이블이 바뀌어 오버레이를 해제했습니다.', 'info');
}
```

대안(가져오기 버튼만 비활성화)이 아니라 **해제**를 택한 것은 사용자 판단이다 — 전환은 어느 쪽으로든 깨끗한 전환이어야 한다.

이로써 오버레이 해제 지점은 **3곳**이 됐다: 맵 로드(토스트) · **테이블 전환(토스트)** · 프레임 진입(무음).

> ⚠️ **문서 정정**: 이전 CODE_MAP은 "테이블 전환 시 전체 제거"라고 적고 있었으나 **사실이 아니었다** — 그 앵커 2개는 실제로 `loadExistingMap`(맵 로드)과 `openMapFrame`(프레임 진입)이었다. 이번 커밋으로 **문서가 주장하던 동작이 비로소 실제가 됐다.**

## 2. 도메인 규칙 확정 — `wafer_map_metadata`가 정렬의 유일한 기준이다

사용자 확정. 원문:

> "모든 맵 기반 데이터(DEFECT 계측 결과든 EDS든 뭐든)는 map_metadata를 넣을거야. 모든 얼라인 정보는 이걸 기준으로해."

### 규칙의 귀결

1. **맵 데이터를 담는 모든 테이블은 메타 등록이 전제다.** defect·EDS·DT·bonding·core 구분 없다. **미등록은 정상 상태가 아니라 누락**이며, "메타가 없으면 identity"는 규칙이 아니라 폴백이다.
2. **정렬은 소스·타깃 메타의 델타에서 유도한다.** 그 외의 정렬 근거는 두지 않는다.
3. **계측 결과(DEFECT WF로 측정한 어긋남)도 메타에 기록한다** — 별도 오버라이드 레이어를 두지 않는다.
4. **셀 레벨 `grid_metadata` 컬럼은 폐기 스킴이다.** 정렬 소스로 문서화하지도, 새로 구현하지도 않는다.
   > 이름이 겹치므로 주의: 폐기 대상은 **맵 데이터 행마다 붙던 컬럼**이고, `wafer_map_metadata` **테이블의 동명 payload 컬럼은 정본**이다.

### 이 규칙이 정리한 열린 검수 항목 2건

- **F3 폐기** — "셀 `grid_metadata`를 스키마에 노출해 미등록 169개 맵을 정확히 해석하자"는 제안은 **방향이 반대다.** 해법은 해석 경로를 하나 더 만드는 것이 아니라 메타를 등록하는 것이다.
- **B3는 수리가 아니라 제거 대상** — `align_overrides.by_eqp` 분기는 규칙상 존재할 이유가 없다. 그 분기가 사라지면 "`by_eqp`로만 스코프된 선언이 관문에 안 보인다"는 격차도 함께 사라진다. (폐기 범위는 착수 시 사용자 확인.)

### 규칙이 드러낸 진짜 격차 (해소되지 않음)

`bonding_map`의 distinct 맵 키는 **약 39만 개**인데 `wafer_map_metadata` 등록은 **9행**이다. 즉 실사용의 거의 전부가 "규격 미등록 → 현재 화면 규격으로 해석"으로 **조용히** 떨어지고, **오버레이 정렬은 사실상 9개 맵에서만 실제로 일한다.** 규칙상 이것은 누락이므로, **그 조용함 자체가 규칙과 충돌한다.**

이 격차는 보드의 **M3**(맵 원천 데이터 인제션 체인에 메타 자동 등록 부착)에서 추적한다 — 계획·우선순위·워크플로는 [PROJECT_STATUS](../process/PROJECT_STATUS.md)가 정본이며 여기서 되풀이하지 않는다.

## 아키텍처 영향

- 경계 계약 무변경(API·스키마·응답 형태 그대로). 클라 동작만 바뀐다.
- 도메인 규칙은 [MAP_EDITOR_SPEC §5.0](../spec/MAP_EDITOR_SPEC.md)에 계약으로 편입됐다 — 보드는 상태를, 스펙은 규칙을 담는다.
- `map_overlay_config.json`의 `align_overrides` 운용 지침이 바뀐다: **정렬을 켜는 올바른 방법은 오버라이드 선언이 아니라 소스·타깃 맵의 메타 등록**이다([CONFIG_GUIDE §5.8-bis](../guide/CONFIG_GUIDE.md)).

## 다음 단계

- M3 착수 시 **검증할 전제 1건**: 값 소스 우선순위가 실제로 USER > 체인으로 동작하는지 쿼리로 증명할 것(보드 기록). 단순화 설계 전체가 그 위에 서 있다.
- 기존 39만 맵의 소급 등록 여부는 별개 결정(미정).
