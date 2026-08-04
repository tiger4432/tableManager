# 회전 버튼은 두 집합에 함께 걸린다 ― 그래서 정보를 낼 수 없다

> **커밋:** `f97d0e9` (2026-08-04 22:23) | **일자:** 2026-08-04 밤
> **대상:** `agent_workspace/reports/Map_editor_decomposition_plan.md` (**신규 973줄**) ― **1파일, 코드 0줄**
> **스위트:** 실행하지 않았다. 소스를 한 줄도 안 고쳤다(`client2/src`는 **읽기만**).

## 배경 ― 「느리다」가 아니라 「안 된다」였다

사용자 진술은 **「맵도 좌표계와 같이 돌아가므로 어떤 미지의 회전인지 알 수 없음」**이었다.
이것을 성능/UX 문제로 읽으면 캔버스를 빠르게 하거나 버튼을 좋게 만드는 라운드가 되고,
그 라운드는 **아무것도 못 고친다.** 재개발 착수 판단 전에 그 진술이 무엇의 관측인지
먼저 재기로 했다.

## 무엇이 측정됐나 ― F0

정렬 탐색은 **느린 것이 아니라 정보가 없다.** `renderGridCanvas` 안에서 셀 값 조회와
마스크 판정이 **같은 `getDieIndex` 출력**을 쓴다(이 커밋 시점 `map_editor.js:3363-3369`):

```js
const physical = getDieIndex(c, r, cols, rows, currentRotation, currentSide);
const completelyInside = isValidDieAt(physical.x, physical.y,
  isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height));

const visual = getDbCoords(c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
const coordKey = `${physical.x}_${physical.y}`;
const val = gridData[coordKey] || '';
```

`currentRotation`이 **두 줄에 동시에** 들어간다. 회전은 두 집합에 같이 걸리는 전단사이므로
**둘의 상대 배치는 불변**이다 ― 어떤 UI를 붙여도 「돌려 본다」는 제스처가 맞고 틀림을
가려낼 수 없다. 저장 데이터를 새 프레임으로 다시 해석하는 유일한 프리미티브
(`reseatCellsToStoredCoords`)도 **정확히 그 축들에 대해 null을 돌려주며**, 함수 상단
주석(규칙 ④)이 그것이 의도임을 못박고 있었다 ― 셀이 붙드는 것은 저장 좌표이고 움직이는
것은 캔버스 칸이라는 사용자 확정 때문이다.

## F0-bis ― 소비 쪽은 이미 다 됐다고 가정하고 있었다

`ontology_mapping.json`이 노드를 **원시 저장 x/y**로 다이 단위 키잉하고 테이블 간
**바이트 동일성**으로 병합하는데, 프레임을 읽는 그래프 모듈은 **0개**, `auto_registered`를
보는 곳도 **0개**였다. 같은 파일이 세 줄 위에서 두 좌표계를 **서로 독립인 미지 프레임**이라
적고 있었다.

## 규모 ― 재개발 논의에 들어간 숫자

| | 실측 |
|---|---|
| `map_editor.js` | **10,814줄** / 톱레벨 함수 **252개** |
| 모듈 `let` 변수 | **48** (하네스 천장 48, 여유 **0**) ― 4개는 동작 변화 없이 44로 줄일 수 있음 |
| 하네스·계약 파일의 소스 슬라이스 간선 | **728개 × 32파일** |
| 5단계 분할로 제거되는 간선 | **63%** ― 그런데 **완전히 자유로워지는 파일은 5개뿐**(하네스 34개 중 24개가 변이를 걸어 평범한 `import`로 못 바꾼다) |

## 아키텍처 영향

이 보고서가 뒤에 쓰인 `MAP_ALIGNMENT_SPEC.md` §1(정리)·§6(순수 판정 층)·§7(불변식)의
직접 출처가 됐다. 여기서 **「클라 결함이 아니다」**가 확정되면서, 라운드의 성격이
「에디터 버그 수리」에서 **「정렬을 성립시키는 층을 세우는 일」**로 바뀌었다.

## 그때 남아 있던 것

- 코드는 한 줄도 안 바뀌었다. 이 커밋은 **측정 결과의 보존**이고, 고쳐진 것은 없다.
- 보고서 §14는 재개발을 권하면서 **반대 논거(변경이 국소적이라는 주장)까지 같이** 적어
  두었다 ― 이 시점에 사용자 판정은 아직 없었다.
- 코드 비교로 발견된 문서 결함 1건(`architecture_and_management.md:118`의 바운딩박스
  서술)이 보고서 안에 **doc-keeper 앞으로** 적혀 있었고, 이 커밋에서는 고치지 않았다.
