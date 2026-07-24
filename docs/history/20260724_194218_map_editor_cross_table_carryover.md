# 맵 에디터: 테이블 전환 시 편집 맵 이월(Carry-Over) 지원

## 현상 (Phenomenon)
맵 에디터에서 A 테이블의 맵을 불러와 편집한 뒤 다른 테이블(B)로 전환하면 `switchTable()`이 무조건 `gridData`를 초기화하여, 편집한 맵을 B로 옮겨 저장할 수 없었다. (요구: A 로드 → 편집 → B 전환 → 바로 B 저장)

## 근본 원인 (Root Cause)
`client2/src/map_editor.js`의 `switchTable(tableName)`이 전환 시 `loadLegendFromStorage()`로 대상 테이블 레전드를 덮어쓰고 `gridData = {}`로 격자를 무조건 리셋했다. 저장 함수 `pushMapData()`는 이미 `selectedTable`을 대상으로 저장하므로, 초기화만 막으면 B 저장이 가능한 구조였다.

## 해결 (Solution)
`switchTable`을 수정하여, 편집 중인 맵이 있으면 유지/초기화를 선택하는 확인창을 띄우고 유지 시 `gridData`+레전드를 보존한다. (기존 `clearGrid`/`pushMapData`와 동일한 `confirm` 스타일)

```js
const hasWorkingMap = gridData && Object.keys(gridData).length > 0;
const keepMap = hasWorkingMap && confirm(
  `현재 편집 중인 맵을 유지한 채 '${tableName}' 테이블로 전환하시겠습니까?\n\n` +
  `[확인] 맵 유지 — 저장 시 '${tableName}'에 적재됩니다. ...\n[취소] 맵 초기화`
);
if (keepMap) {
  renderLegendTable();               // 현재 grid + 레전드/색상 보존
} else {
  loadLegendFromStorage();           // 대상 테이블 레전드 로드
  renderLegendTable();
  gridData = {};                     // 기존(초기화) 동작
}
renderGridCanvas();
```

## 검증 (Validation)
- `node --check` 구문 통과.
- `npm run build`(vite) 성공 — `dist/assets/map_editor-*.js` 정상 번들.
- `switchTable`은 `map_editor.js` 전용 로컬 함수로, 메인 그리드용 `api.js#switchTable`과 별개임을 확인(상호 영향 없음).
- 경계 계약(REST/WS/셀 형태/스키마) 무변경 — 서버 수정 불필요.

## 영향 (Impact)
- 워크플로우: A 로드 → 편집 → B 전환(맵 유지 선택) → B 메타데이터 입력 → Push → B에 적재.
- 초기화/타 맵 로드는 기존 `Clear Grid`/`Load Existing Map` 버튼으로 처리(회귀 없음).
- 도메인: Client PM. 리빙 문서 `docs/map_editor/architecture_and_management.md` §3.3 추가.
