# 초안을 죽인 것은 리로드가 아니라 **로드 경로의 첫 저장**이었다 — 그리고 잘라먹는 push를 거절하는 세 번째 관문

> 커밋 `6db517d` · 2026-07-28 11:07 · 도메인 Client(맵 에디터, map-pm 라운드)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)
> 발견 경위: [U9 클라 라운드의 T2 QA](./20260728_101201_u9_client_half_marker_contract_u8_refresh_feedback_qa.md) (`2baf9ff`) — 그 라운드 diff는 GO였고, 이 두 건은 **이전 커밋의 코드**에서 나온 HIGH 티켓이다.
> H1의 원인 커밋: [첫 클릭이 죽던 이유](./20260728_074941_map_editor_five_fixes_lag_overlay_reopen.md) (`280ebf0` — 새로고침 생존 기능 자체가 회귀를 실었다)

## H1 — 초안 우선순위 판정이 읽기 **전에**, 로드 경로가 초안을 덮어썼다

### 왜 이런 모양의 결함이었나

`280ebf0`이 "새로고침해도 마지막 맵으로 돌아온다"를 넣으면서 리로드가 일상 동작이 됐는데, 바로 그 리로드가 초안을 지우고 있었다. 순서 결함이다: `loadExistingMap`의 legend 자동 감지 블록이 서버에서 막 받은 상태를 `saveLegendToStorage()`로 저장했고, 그 저장이 초안 레코드까지 **방금 받은 서버 상태로** 덮어썼다 — 초안 우선순위 블록이 초안을 읽는 것은 그 **뒤**였다. 읽을 시점엔 이미 초안이 서버 사본이 되어 있었으므로, 값이 있는 맵에서는 칠한 셀 초안이 리로드를 한 번도 살아남지 못했다. 파괴자는 별도의 삭제 코드가 아니라 **로드 경로 자신의 첫 저장**이었다.

```js
// map_editor.js — loadExistingMap, 이 커밋 시점
-      // Update legend array, save to localStorage and rebuild legend table
+      // Update legend array and rebuild the legend table. Deliberately NOT persisted here:
+      // saveLegendToStorage() -> saveDoeDraft() at this point would overwrite this map's
+      // draft with the just-loaded SERVER state ... BEFORE the draft-precedence block
+      // below has read it - that destroyed every painted-cell draft on reload (H1).
       legend = newLegend;
-      saveLegendToStorage();
```

수정 원리는 하나다: **로드 경로는 정확히 한 번, 초안 우선순위가 끝난 뒤에만 저장한다.**

### "복구했다"는 "바꿨다"여야 한다

부수 수정 둘이 같은 원리에서 나왔다. 초안은 registry 저장 성공 직후에도 다시 써지므로, Push 후 리로드에서는 초안 == 서버 상태다. 종전 `applied` 판정은 "초안에 내용이 있는가"였기에 이 경우에도 참이 되어 **모든 리로드가 유령 복구 토스트**를 띄울 참이었다. 판정을 적용 전/후 투영 비교로 바꿨다:

```js
// applyDoeDraftRecord — "applied"는 "화면을 바꿨다"는 뜻이어야 한다
const before = JSON.stringify([l.knobs, l.stack, l.mat_1h, l.mat_mid, l.mat_top]);
// ... 초안 적용 ...
if (JSON.stringify([l.knobs, l.stack, l.mat_1h, l.mat_mid, l.mat_top]) !== before) applied = true;
```

그리고 진짜 복구는 `legendDirty = true`를 세운다 — 복구된 편집은 여전히 **저장 안 된** 편집인데, 세우지 않으면 초안이 막 살아남은 그 새로고침 직후에 칩이 "저장됨"으로 읽힌다.

## H2 — 잘라먹는 push의 거절: 화면 − 페이로드

메타데이터 없는 맵을 기본(추측) 프레임으로 열어 push하면, 직렬화 루프가 원 밖·격자 밖 셀을 건너뛴 페이로드가 `replace_map`(전체 삭제 후 삽입)으로 나가 **덮지 못한 셀이 서버에서 삭제**됐다 — QA 실측 1293행 → 379행. 사용자에게는 정상 push로 보였다.

세 번째 데이터 보호 관문(기존: zone 컬럼 부재 / legacy 판독 불가 — 셋 다 "직렬화하지 않은 데이터를 지우는 쓰기를 막는다"는 같은 가족)을 confirm·쓰기 **이전에** 세웠다. 셈법이 요점이다:

```js
// pushMapData — 화면의 비어있지 않은 셀 수 − 페이로드 셀 수
const nonEmptyOnGrid = Object.keys(gridData).filter(k => (gridData[k] || '') !== '').length;
const droppedNonEmpty = nonEmptyOnGrid - updates.length;
if (droppedNonEmpty > 0) { /* 삭제될 셀 수를 명시하고 거절 */ }
```

- **차집합이라서** 현재 격자가 아예 순회하지 않는 좌표(축소된 격자 밖)도 잡힌다 — "루프가 건너뛴 것"만 세면 루프가 방문조차 안 한 셀은 못 센다.
- 루프와 **같은 공백 술어**(`(v || '') !== ''`)를 쓰므로 사용자가 일부러 지운 셀은 양변에서 함께 빠진다 — 지우고 push하는 정상 작업은 마찰 없이 통과한다.

## 검증

- 격리 스택에서 **기준 번들로 재현 → 수정 번들로 통과** 순서로 양건 확인, 이어서 독립 quick-QA 재실행 FIXED/FIXED — 거절 시 PUT 0건, DB 1293행 무손상.
- 하네스 82/71/331 green · `node --check` clean · vite 재빌드.

## 그때 남아 있던 것

- **관문은 거절하지 못한 것을 push 가능하게 만들어 주지 않는다.** QA 재확인 결과, 재시딩된 메타데이터 없는 맵은 어떤 기본 프레임 아래서도 push 불가였다 — 원 마스크가 실제로 1293셀 중 373셀을 덮지 못했다. 즉 관문은 정확히 발화하는 것이고, 기본 프레임이 그 맵을 제대로 담게 하는 **프레임 매핑 결함 자체는 별도 티켓으로 남아 있었다.**
- H1 수정으로 로드 경로의 저장은 한 번이 됐지만, 이는 `280ebf0`이 만든 리로드 빈도 위에서의 수정이다 — 자재 프레임 안 새로고침이 루트 맵으로 돌아가는 설계 선택(레코드는 depth-0 정체성만)은 그대로였다.
