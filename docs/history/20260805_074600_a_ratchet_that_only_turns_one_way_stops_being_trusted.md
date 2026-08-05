# 한쪽으로만 도는 래칫은 처음 우회당하는 순간 신뢰를 잃는다 — 그리고 우회는 언제나 「발산을 다시 선언한다」다

> **커밋:** `a099952` (2026-08-05 07:46) | **일자:** 2026-08-05 아침
> **선행:** [`20260805_074000`](./20260805_074000_a_stored_coordinate_is_bounding_box_relative_and_a_catch_turned_every_failure_into_a_plausible_wafer.md)(`cab8ed9`, **6분 전** — 이 발산을 닫은 코드가 들어간 커밋이자, 계약 군을 의도된 FAIL로 남긴 커밋)
> **담당:** 계약 레인
> **대상:** `contracts/map2_seam/client_harness.mjs`(**+21 / −1**) · `contracts/map2_seam/vectors.json`(**+26 / −2**)
> **스위트:** 커밋 메시지에 결과 없음.

## 배경 — 선언된 발산이 닫혔고, 하네스가 그것을 말할 수 없었다

`frame_basis` 군은 **핀으로 박은 좌석 14개 중 14개가 틀림**으로 선언된 발산이었다.
`seating.js`가 바운딩 박스 항과 y 미러를 갖게 되면서 **14개 중 0개**가 됐다.

그러면 선언이 빠져야 한다. 그리고 **하네스가 일부러 FAIL로 그것을 강요했다** —
그게 기제가 작동한 것이다.

## 그런데 선언을 빼자 하네스가 죽었다

```js
const declared = group.client_expected_failure;   // client_harness.mjs:289
```

이 줄은 이 커밋에서 **안 바뀐다.** 키가 `client_divergence_closed`로 이름이 바뀌자
`declared`가 `undefined`가 되고, `diverged === 0`인 상태에서 제어가 기존 가지로
떨어졌는데 그 가지의 첫 식이 이것이다:

```js
`${declared.name} -- THE DECLARED DIVERGENCE HAS DISAPPEARED`
```

→ `TypeError`.

**하네스는 「결함이 여기 있다」와 「결함이 사라졌는데 네가 말을 안 했다」는 말할 수
있었고, 「결함이 없어졌다」는 말할 수 없었다.**

> 한쪽으로만 도는 래칫은 누군가 처음 우회해야 하는 순간 신뢰를 잃고,
> **그 우회는 언제나 「발산을 다시 선언한다」**이다.

해소 가지가 추가됐다:

```js
  if (!declared) {
    if (diverged === 0) {
      ok(`frame_basis: all ${agreed} pinned seats agree`, ...);
    } else {
      bad(`frame_basis: ${diverged} of ${agreed + diverged} pinned seats diverge`, ...);
    }
  } else if (diverged > 0 && agreed === 0) {
```

## 무엇이 틀렸었는지는 지우지 않고 옮겨 놓았다

`client_divergence_closed`에 `$resolved`, `$what_closed_it`(18줄),
`$the_reclassification_was_forced_and_that_worked`가 붙고, `name`·`symbol`·`owner`·
`measured_mismatch`·`$two_omissions`·`$turns_red_when_fixed`는 **그대로 유지된다.**

이유가 기록할 가치가 있다 — **저장 좌표가 바운딩 박스 상대라는 것과, 그 항을
빼면 엉뚱한 다이 위에 그럴듯한 웨이퍼가 그려진다는 것을 말하는 유일한 자리**가
여기이기 때문이다.

## 숫자 둘이 같은 군 안에서 서로 다른 것을 센다

- **14**는 `frame_basis_cases.cases[*].expect_seats` 길이의 합이다
  (`SPEC_FIXTURE` 4 + `SPEC_FIXTURE_YINV` 4 + `CORE_YINV_LIKE` 3 + `ROT90_BACK` 3).
  **핀으로 박은 좌석 수**다.
- 유지된 `measured_mismatch`는 **픽스처 전체 셀 수**로 `3,405 / 3,430`이다.

같은 블록 안에 살지만 **다른 모집단**이다.

## 그때 남아 있던 것

- **기하가 없는 경우는 여전히 선언된 발산이고, 그대로 남는다** —
  `$what_closed_it`이 그렇게 적는다. 닫힌 것은 박스가 알려진 경로다.
- `declared`를 읽는 줄(`:289`)은 이 커밋에서 안 바뀌었다. 새 가지가 그 앞에
  들어가 `undefined` 경로를 먼저 잡는 형태다.
