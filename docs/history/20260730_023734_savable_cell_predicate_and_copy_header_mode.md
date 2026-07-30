# 저장 가능한 셀의 술어 하나 + COPY HEADER MODE — Fill All 한 번이 맵을 영구 거절로 만들던 자리

> **일자:** 2026-07-30 02:37 | **커밋:** `064550f` | **담당:** Map PM | **소급 기록:** 2026-07-30 (배치 밖에 남아 있던 항목)
> **대상:** `client2/src/map_editor.js`(+313) · `client2/src/doe_bands.js` · `client2/map_editor.html` · `client2/tests/copy_header_count_harness.mjs`(신규 585줄)
> **관련:** [VALID_DIE_MAP_GUIDE §8](../guide/VALID_DIE_MAP_GUIDE.md) — 이 결함을 11분 전에 문서에 적어 둔 자리 · 후속 `5a14e77`(폭 병합·로스터 집합 채점)

## 현상 — 하나가 아니라 증상 셋이었다

사용자 회사 실 본딩맵 양식(상단 헤더 + 우측 `VALUE | COUNT | STACK | DESC` 보조표)을 내보내는 것이 요청이었는데, **COUNT를 세려고 하니 화면의 수량이 저장되는 수량과 달랐다.** 파고들면 증상이 셋이고 서로 다른 함수에 있었다.

1. `🎨 Fill All`이 **사각 격자 전체**를 칠했다 — 원 기반 맵에서 약 21%가 원 밖.
2. `computeLegendCounts`가 `gridData`(물리 키 평면 맵, `inside`를 모른다)를 순회해 **그 셀까지 셌다.**
3. 그리고 — 아무도 눈치채지 못한 부분 — `pushMapData`의 대비 관문이 **화면 수량과 페이로드를 비교해 Push 전체를 거절했다.**

그 셀들은 캔버스에 색이 나오지도 않았다(`cellFillColor`가 `!inside`면 `outBg`). 즉 **보이지도 않고 저장되지도 않는 셀이 DOE 산술의 입력이자 거절의 근거**였다.

결과: **원 기반 맵에서 Fill All 한 번이 그 맵의 Push를 영구 거절 상태로 만들었다.** 그리고 거절 문구는 "격자 크기·회전·물리 규격을 맞추십시오"였다 — **그 조언으로는 절대 풀리지 않는다.** 셀이 격자 밖이 아니라 원 밖이기 때문이다.

## 근본 원인 / 설계 판단

**수량을 고치는 것만으로는 안 됐다.** 세는 쪽만 맞추면 숫자는 일치하는데 **저장은 여전히 아무것도 안 되는** 상태가 된다(거절은 그대로다). 그래서 세 증상을 하나의 술어로 수렴시켰다.

**`pushMapData`가 `updates`를 만드는 그 순회를 함수로 들어내고, 화면 쪽이 같은 함수를 지나게 했다.** 두 곳에서 각자 세면 이 저장소가 이미 값을 치른 계급이 되돌아온다(저장 `ceil` / 표시 `round`로 DB 34 · 화면 33).

```js
// 정의역이 `gridCells2D`인 것이 규칙의 일부다 — 렌더가 만들지 않은 셀은 Push도 직렬화하지 않는다.
function eachSavableCell(fn) {
  if (!gridCells2D) return;
  Object.keys(gridCells2D).forEach(rStr => {
    const r = parseInt(rStr, 10);
    if (!gridCells2D[r]) return;
    Object.keys(gridCells2D[r]).forEach(cStr => {
      const cellObj = gridCells2D[r][parseInt(cStr, 10)];
      if (!cellObj || !cellObj.inside) return;   // 원/유효다이 밖은 저장되지 않는다
      const val = gridData[cellObj.key] || '';
      if (val === '') return;                    // replace_map이 맵을 청소한다 — 빈 값은 아무것도 옮기지 않는다
      fn(cellObj, val);
    });
  });
}
```

`computeLegendCounts`·DOE 패널·COPY HEADER MODE의 COUNT·`pushMapData`의 직렬화가 **모두 이 함수를 통과한다.** 빈 값 판정은 Push가 쓰던 식(`(v || '') !== ''`)을 **글자 그대로** 옮겼다 — 여기서 표현을 "개선"하면 그 개선분만큼 화면과 저장이 갈린다.

`fillGrid`에는 세 번째 기하식을 만들지 않았다. 렌더가 만든 셀 객체가 있으면 그 `inside`를 읽고, 없으면 `getGridCellObject`가 쓰는 **같은 두 함수**(`isValidDieAt` · `isCellInsideWafer`)를 같은 순서로 부른다.

저작 캔버스(`basis === 'template'`)에서는 마스크가 격자 전체이므로 이 필터가 아무것도 걸러내지 않는다 — M4② 저작 동선은 무변경.

## 해결 — COPY HEADER MODE

끄면 페이로드가 **종전과 바이트 동일**하다(하네스가 HEAD 출력과 바이트 비교). 켜면 두 블록이 더 실린다.

**보조표의 출처가 둘이라는 것이 이 설계의 핵심**이다: `COUNT`는 격자 **집계**(=`computeLegendCounts`, 위 술어를 지난 것)이고 `STACK`·`DESC`는 표①(DOE)의 **선언**이다. 여기서 따로 세면 한 화면에 두 개의 수량이 생긴다 — 방금 고친 그 결함이다.

열 그룹 이름은 하드코딩하지 않고 DOE 선언(`ZONE_LABEL`·`DOE_COLUMNS`)에서 나온다. 화면이 "MID"라 쓰는데 내보내기가 "MIDDLE"이면 **공장이 읽는 파일이 화면과 갈린다.**

`legend`에 없는데 **칠해진** 값은 보조표 뒤에 붙인다 — 화면에 색이 있는데 표에 없는 값은 "보이는 대로"를 깨고, 그 셀들은 실제로 저장된다.

체크박스 영속화는 새 기계장치를 만들지 않고 그리드 화면의 `Copy Header` 토글이 이미 쓰는 `localStorage` 패턴 사본이다. **초안(`saveDoeDraft`)에는 얹지 않았다** — 초안은 지문이 어긋나면 적용되지 않고 Push 성공 시 `clearDoeDraft`가 지운다. 사용자 설정이 저장 한 번에 조용히 꺼지는 동작이 된다.

`doe_bands.js`의 `IGNORED_HEADERS`에 `COUNT` 한 단어를 더했다 — **알아보되 버린다.** 칠한 셀 수는 격자에서 세는 것이지 붙여넣기로 정하는 것이 아니다.

## 검증

- `client2/tests/copy_header_count_harness.mjs` 신규(585줄).
- **라이브 실측 — 사용자가 보게 되는 변화**: Fill All을 쓴 맵에서 화면 수량이 내려간다. 프리셋별 CORE **35%** · BASE **41%** · TAPE **51%** · 프리셋 없음 **7%**(격자가 웨이퍼보다 작게 잘려 원 밖 셀이 애초에 적었다).
- **서버에서 로드한 맵은 변화 0** — 21/56/14가 전후 동일. Push가 원 밖 셀을 저장한 적이 없기 때문이다. **사라지는 숫자는 원래 저장될 수 없던 셀이고, 그것이 저장이 거절되던 이유였다.**
- 격리 스택 표준 시나리오가 **세 라운드 만에 처음** 완주했다(본딩맵+DOE → dt 맵 편집·Push → 롤업 반영). 화면 315 · DB 315행.

## 그때 남아 있던 것

- `VALID_DIE_MAP_GUIDE §8`이 이 결함을 11분 전에 문서화하며 **"수량이 30~40% 내려간다"고 예측**했는데, 실측은 7~51%였다. TAPE에서 예측을 넘었다.
- `IGNORED_HEADERS`는 이 커밋에서 4개였다. 후속 `5a14e77`이 13개로 늘리며 롤업 8단어를 실었고, **그 확장이 붙여넣기 스캔의 종료 조건을 깨뜨린 것은 `ae2811c`에서 드러났다** — 이 커밋 시점에는 알려지지 않았다.
- `dist` 번들이 함께 커밋됐다(빌드 산출물이 저장소에 들어오는 그때의 관행).
