# 저장 좌표는 바운딩 박스 상대값이다 — 그리고 catch 하나가 모든 실패를 그럴듯한 웨이퍼로 바꿨다

> **커밋:** `cab8ed9` (2026-08-05 07:40) | **일자:** 2026-08-05 아침 — Map Editor 2가 처음 화면에 닿은 커밋
> **선행:** [`20260805_004700`](./20260805_004700_rebuild_beside_it_and_the_bar_that_was_measuring_the_old_codes_death_rate.md)(`942edb1` — 「옆에 새로 짓는다」 판정)
> **담당:** 제품 소유자(목적 사슬) · map 구현
> **대상:** **48파일 +18,304 / −2.** 신규 41파일(+17,810) — `client2/src/map2/` 14모듈 · `client2/map_editor2.html`·`.css`·엔트리 · 서버 `map_alignment.py`(719) · `frame_confirmation.py`(268) · 마이그레이션(144) · 계약 `contracts/map2_seam/` · 하네스 5종. **기존 7파일 수정**(+494 / −2)
> **스위트:** 커밋 메시지 기준 **서버 2,365 passed**, 게이트된 클라 하네스 전부 초록. (diff 안에 그 결과를 기록한 산출물은 없다.)

## 왜 수술이 아니라 두 번째 에디터인가

낡은 파일에 대고 계획한 수리는 전부 자라났다 — 선언을 빼내려면 조립 층을 갈라야
하고, 그러려면 `physFrameOverride`의 독자 여덟을 한 덩어리로 옮겨야 하고, 그러려면
**소스를 텍스트로 자르는 하네스**를 전환해야 한다. **클라 하네스 41개 중 41개가
텍스트를 자르고, `import`하는 것은 0개다.** 낡은 파일 안에는 「이 함수를 빼내지
마라 — 하네스 넷이 이걸 자른다」는 주석까지 들어 있다.

새 모듈에는 그 값이 없다.

## 목적 사슬 — 정렬은 목표가 아니라 전제다

제품 소유자의 사슬: **좌표계 확정 → 여러 디펙 소스 얼라인 → 다이 맵 확정 →
본딩 계획.** 종결형으로 적으면 — **맵 에디터는 본딩 계획이 가리키는 다이가
실제로 그 다이이게 하려고 존재한다.**

## 이 커밋에서 검토할 값어치가 있는 부분 — 좌표 사슬

```
저장 (x,y) → localIndex → 프레임 셀 (c,r) → seatOf → 공통 좌석
```

빠져 있던 항이 `localIndex`에 들어갔다. **저장 좌표는 격자 상대가 아니라 바운딩
박스 상대다.**

```js
export function localIndex(frame, box, x, y) {
  const c = numOr(x, 0) - numOr(frame.startX, 0) + box.minC;
  const dy = numOr(y, 0) - numOr(frame.startY, 0);
  const known = box !== IDENTITY_BOX;
  const r = (known && frame.invertY === true) ? box.maxR - dy : dy + box.minR;
  return { c, r };
}
```

**y 갈래는 평행이동이 아니라 반사다.** 그래서 채점기가 푸는 start 시프트가
그것을 흡수할 수 없다.

**이 두 항이 없을 때 무슨 일이 벌어졌는지가 이 커밋이 남기는 경고다** —
계약 픽스처 넷의 셀이 **전부 엉뚱한 다이 위에 앉았는데 그림은 여전히 그럴듯한
웨이퍼로 보였다.** 가능한 실패 중 최악이다. **운영자가 어긋난 정렬을 확정하고,
우리가 기록하는 것은 그 확정**이기 때문이다.

박스는 웨이퍼 원에서 나오고, 원의 규격은 **프레임 축**으로 있어야 한다 — 사분회전에
피치가 스왑되고, 뒷면에서는 **면 미러가 회전보다 먼저 적용되므로** x 오프셋의
부호가 뒤집힌다. `_frame_phys_params`의 네 줄짜리 표는 **다시 유도하지 않고 항별로
그대로 옮겨 적었다.** 시스템에서 가장 미묘한 산술이고, **두 번째 유도는 언젠가
불일치한다.** `ROT90_BACK`이 마지막으로 닫힌 픽스처인 이유는 **두 효과가 동시에
발화하는 유일한 경우**여서다.

기하가 없을 때는 항등 박스를 쓰고 **미러도 일부러 건너뛴다** — `maxR = 0`에 대고
미러하면 모든 행이 음수로 가고, 그건 **측정되지 않은 방향의 새로운 틀림**이다.
대신 기록이 `boxKnown: false`를 들고 다녀서 소비자가 거절할 수 있다.

```js
const IDENTITY_BOX = Object.freeze({ minC: 0, maxC: 0, minR: 0, maxR: 0 });
```

**좌석 배정은 절대 거르지 않는다.**

```js
  if (seats.length !== list.length) {
    throw new Error(
      `seating dropped a cell: ${seats.length} seats for ${list.length} cells. `
      + 'Seating registers; it never filters.');
  }
```

충돌은 **해소하지 않고 보고한다.**

## 다른 것들을 가리고 있던 결함 — `.catch(capture)`

**모든 실패가 그럴듯한 웨이퍼로 변환됐다.** 옛 요청 모양은 패킷이 움직이기도 전에
전송 계층에서 거절됐고, 폴백이 그 위에 캡처된 셀을 칠했다 — 그래서 **밤새
「라이브 렌더」라고 보고된 것이 캡처 파일이었다.**

그리고 그것이 네 번째 버그도 가렸다: **셀이 `{x,y}`가 아니라 `[x,y]` 쌍으로
도착해서** 모든 `.x` 읽기가 `undefined`였고 `NaN`에 좌석 배정됐다 — 결과는 빈
그림이고, 그건 **「이 맵에 다이가 없다」로 읽히지 버그로 읽히지 않는다.**

이제 실패가 분류된다. 라우트/모양 실패는 **다시 던져지고 화면에 이름이 뜬다.**
**상태 코드가 없는 fetch 오류만** 폴백할 수 있다.

```js
function isOutage(err) {
  if (!err) return false;
  if (err instanceof RouteNotServedError) return false;
  if (Number.isFinite(err.status)) return false;
  if (err.name === 'AbortError') return false;
  return err instanceof TypeError
    || /fetch|network|ECONN|Failed to fetch/i.test(String(err && err.message));
}
```

캡처 마커는 **폴백 안에서** 쓰인다. 그래서 라이브 렌더가 캡처라고 주장할 수 없고,
캡처가 조용히 있을 수도 없다.

## 판정을 지키던 가드 안에 그 가드가 막으려는 결함이 살고 있었다

교체된 플레이스홀더는 **부재한 임계값을 `Number(null)`로 0으로 읽었다.** 즉
**I4를 막는 가드 안에 I4가 들어 있었다.** 지금은:

```js
  const minMargin = finiteOrNull(thresholds && thresholds.min_margin_dies);
  const minDiscriminating = finiteOrNull(thresholds && thresholds.min_discriminating_dies);
  if (minMargin === null || minDiscriminating === null) {
    return frozen(VERDICT.NOT_SCORABLE, REASON.NO_THRESHOLDS, {});
  }
```

`verdict_placeholder.js`는 **원래 철자를 증거로 남겨 둔 채** 트리에 남아 있다.

## 화면에 닿았고, 화면이 「못 한다」고 말한다

`GET /api/maps/alignment/view`가 200을 돌려주고, 한 `(dt_eqp, product)` 단위에
대해 맵 40개에 걸친 **실제 셀 2,892개**를 243 ms에, **동작 1회 · fetch 1회**로
그린다. 서버 판정은 `not_scorable`이고 **화면이 그렇게 말한다** — 헤드라인
`채점 불가`, 서버 자신의 거절 문장 그대로, 모든 카운트 `미상`, 후보 8개 전부 불활성,
바닥 미표시.

> 「이 다이들이 어디 있는지는 안다. 그것들이 무엇과 어떻게 관계되는지는 모른다」의
> 정직한 그림이다.

모든 카운트가 **CSS 형제 셋** 안에 있다. 그래서 계산 중·채점 불가 상태에서 숫자가
뜨는 것이 **배선이 기억해야 하는 규율이 아니라 구조적으로 불가능**하다.

## ⚠️ diff가 커밋 메시지와 어긋난 자리

- **「여기 있는 건 전부 새것이다」는 문자 그대로는 아니다.** 기존 7파일이 수정됐고
  그중 `server/map_overlay.py`(+188)와 `server/database/models.py`(+165)는 작지
  않다. **커밋 전체에서 삭제가 있는 파일은 `setup_db_performance.py` 하나**다
  (부분 인덱스 `idx_sources_confirmation` 추가). 다만 「`map_editor.js`·
  `map_editor.html`·`dist/`는 안 건드렸다」는 **파일 목록으로 확인된다** — 셋 다
  없다.
- **「서버 모듈 셋」은 부정확하다.** 새로 생긴 톱레벨 서버 모듈은 둘
  (`map_alignment.py`, `frame_confirmation.py`)이고, 셋째는 마이그레이션
  스크립트이거나 **수정된** `map_overlay.py`다.
- **「3,430셀 전부가 엉뚱한 다이에 앉았다」는 계약이 핀으로 박은 수와 다르다.**
  `contracts/map2_seam/vectors.json`의 `frame_basis_cases.client_expected_failure`가
  기록한 `measured_mismatch`는 `SPEC_FIXTURE 475/475 · SPEC_FIXTURE_YINV **450/475** ·
  CORE_YINV_LIKE 1755/1755 · ROT90_BACK 725/725` = **3,405 / 3,430**이다.

## 일부러 빨강으로 둔 계약 군

`client_expected_failure`가 **의도된 FAIL**이다. 재분류를 기다리는데, 그것이
핀으로 박은 발산이 이미 닫혔기 때문이다. **익명으로 상시 빨간 것을 금지**하는
규율이 이 군에 적혀 있다.

## 안 한 것을 이름으로 적었다

- **저작(유효 다이 편집·legend·DOE)은 레거시 에디터에 남는다.**
- `bonding_plan.CANONICAL_FRAME_ROLES`는 여전히 **config 순서로** 정준 프레임을
  고른다 — 운영 계획 코드를 하룻밤에 고치지 않는다.
- **bbox 근거 정합은 오늘 발화할 수 없다** — `valid_die_ref`를 선언한 행이 8인데
  **해소되는 것이 0**이다.

## 그때 남아 있던 것

- **API 라우트가 등록되지 않은 채로 이 커밋이 나갔다.** 새 checkout에서는
  엔드포인트가 존재하지 않는다 — 1분 뒤 `580387c`가 닫는다.
- **페이지를 서빙하는 라우트도 없다.** 23분 뒤 `39b43ab`가 닫는다.
- 계약 군 하나가 **의도적으로 빨갛다.**
- 채점은 서버에만 있다. 후보 8개는 각각 **메타 전체로 다시 조립된다** — 박스
  하나에 변환 8개를 얹으면 `CORE_YINV`가 (2,−1)만큼 어긋나기 때문이다.
