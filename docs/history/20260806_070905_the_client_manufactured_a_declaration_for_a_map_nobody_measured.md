# 클라가 아무도 재지 않은 맵에 대해 선언을 지어냈다 — 「목록 둘에 낱말을 더하라」는 지시가 분기 하나만큼 짧았다

> **커밋:** `7c53581`(2026-08-06 07:09 · 토큰 + 빠진 분기) → `9d26695`(07:22 · 축별 절반 · 빈 표지) | **일자:** 2026-08-06 아침
> **선행:** [`20260806_065114`](./20260806_065114_the_confirmation_reached_the_metadata_because_without_a_marker_the_winner_is_a_row_nobody_touched.md)(`3e96747` — 서버가 일곱째 토큰을 만든 커밋)
> **담당:** map 구현(클라) · 이음매 계약
> **대상:** `client2/src/map2/declaration.js`(+168 / −17) · `decode.js`(+41 / −1) · `main.js`(+38 / −3) · `contracts/map2_seam/vectors.json`(+230) · `client_harness.mjs`(+13 / −1) · `client2/tests/frame_declaration_harness.mjs`(+37 / −4)
> **스위트:** `7c53581` — 벡터군 **6 → 10 케이스**(diff에서 새 케이스 4건 확인), 넷 중 둘이 수리 전 클라에서 빨강(**pass 43 / fail 3**), 되돌림은 sha256으로 복원 확인. `9d26695` — 새 케이스 **5건**, 변이 4종 채점(무분기 5실패 · `!!` 3실패 · 다섯 축 전부 적용 9실패 · 안 읽히는 값에 도장 2실패). ⚠️ **두 커밋 모두 클라 게이트 전체 결과를 메시지에 적지 않았다.**

## 배경 — 지시가 「목록 둘에 토큰을 더하라」였다

그리고 그것이 **더 큰 절반을 빠뜨렸다.**

`confirmed`는 `assumed`와 **한 가지 점에서 다르고, 그 한 가지가 필요한 코드량을
결정한다.** `assumed`는 서버 메모리에만 있어서 클라는 그 표지를 **만날 일이 없었고**
낱말만 알면 됐다. `confirmed`는 **`wafer_map_metadata`에 쓰인다** — 클라는 DB에 든
그 모양을 직접 읽는다.

## ① 빠진 분기가 만든 것은 정보 손실이 아니라 **날조**였다

`geometryDeclaration`에 `phys_confirmed_from` 분기가 없었다. 그러면 그 아래 **phys
여섯 값 — 바닥의 진짜 실측치** — 가 그대로 루프에 걸리고, 함수는 **`declared`**를
답한다.

```js
  if (markerPresent(m[PHYS_ASSUMED_KEY])) return ASSUMED;
  if (markerPresent(m[PHYS_CONFIRMED_KEY])) return CONFIRMED;   // ← 없던 줄
  if (m[AUTO_REGISTERED_KEY] === true) return AUTO_REGISTERED;
```

> **토큰을 흘렸다면 정보를 잃었을 것이다. 이것은 정보를 지어냈다.**
> 클라가 **「누군가 이 맵을 쟀다」**고 말하고 있었다 — 아무도 재지 않았다는 것이
> 존재 이유의 전부인 행에 대해서.

분기는 **서버의 순서 그대로**(assumed → confirmed → auto_registered) 들어갔다.
순서가 서열이기 때문이다.

## ② 거짓 진술은 한 층 아래에 있었다

`attested_maps` 집계는 판정대로 **건드리지 않았다** — `confirmed`는 `declared`로 접히지
않고, 집계는 문자 그대로 참인 채로 있다.

틀린 것은 `adaptPayload`였다. 행을 **`declaredFrameSource === 'declared'`로 게이팅**
해서, **확정된 맵이 `고르지 않음` · basis=unknown으로 렌더됐다** — 미실측 표시조차
안 붙은 채로.

**행이 이미 갖고 있던 그 한 텍스트 슬롯**에 이제 세 답이 들어간다. **새 컨트롤 0 ·
영역 0 · 모드 0 · 모달 0.**

**확정된 프레임은 일부러 `stored_candidate_id`로 승격하지 않았다.** 그 필드는 캔버스가
무엇을 그릴지를 정하고, **확정은 선택이 아니다.**

## ③ 개수 핀이 예고된 대로 터졌다

`7c53581`은 자기 커밋 메시지에 **알려진 빨강**을 적었다:
`frame_declaration_harness.mjs`가 `TOKENS.length === 6`을 **두 군데**에서 박고 있다.
그리고 첫 번째 핀의 **아홉 줄 위 주석**이 바로 그 이유로 길이 핀을 제거했었다고
기록하고 있었다. **그 핀이 자기가 경고한 그 부류의 변경에 대고 발화했다.**

`9d26695`이 핀을 지웠다. **그런데 그냥 지우면 진짜 커버리지가 줄었다** — 인위적으로
`'provisional'`을 인덱스 7에 덧붙인 변이가 이 하네스를 **4079/0**(전부 초록)으로
통과했다.

**어휘를 이 라운드에서 다시 소유하는 대신 소유자를 실측했다**: 그 변이는
`contracts/map2_seam/client_harness.mjs`에서 죽는다. 여기 남긴 것은 **어떤 길이 핀도
표현할 수 없는 단언** — 마지막 위치 핀을 넘어서 반복된 토큰이다.

```js
    new Set(TOKENS).size, TOKENS.length);
```

## ④ 이미 살아 있던 발산 — 파이썬 진리성과 자바스크립트 진리성

**`bool({})`은 파이썬에서 거짓이고 `!!{}`은 자바스크립트에서 참이다.** 그리고 빈 표지는
**쓰는 쪽이 실제로 만들어 내는 모양**이다 — `confirmed_meta_for`가
`base[FRAME_CONFIRMED_KEY] = dict(mark or {})`로 끝난다.

서버는 그때 **자기 표지를 무시한다**(실측: `phys_confirmed_from: {}`인 메타에
`geometry_declaration`은 `declared`를 답한다). 이것은 「`confirmation_uid` 없는 값은
표지를 달 자격이 없다」는 서버 자기 규칙과 일관된다.

`!!`로 썼다면 클라는 **서버가 표지 없다고 취급하는 바로 그 행들에서**
`assumed`/`confirmed`를 답했을 것이다 — **발산에 대한 수리 안에서 만들어진 두 번째
발산.** 이 발산은 `phys_assumed_from`에 대해 **이미 살아 있었다.**

```js
function markerPresent(raw) {
  if (raw === undefined || raw === null || raw === false || raw === 0 || raw === '') return false;
  if (Array.isArray(raw)) return raw.length > 0;
  if (typeof raw === 'object') return Object.keys(raw).length > 0;   // Python: bool({}) is False
  return !!raw;
}
```

⚠️ **`markerPresent`는 적격성을 다시 검사하지 않는다.** `confirmation_uid`가 있는지는
서버의 규칙이고 서버의 집행 지점이다 — 여기서 다시 물으면 **그것의 두 번째 구현**이
되고 둘은 갈린다. 서버의 `if`가 묻는 그 질문만 묻는다.

## ⑤ 이식은 이식이지 개선이 아니다

`frameFromDeclaration`이 **오염 규칙보다 먼저** 확정 표지를 읽는다.
`orientation_declaration`의 **곧은 이식**이다 — 그 `continue`까지, **회전과 면 두 축만.**
기댓값은 이식본이 아니라 **서버 함수를 직접 돌려서** 얻었다.

서버 동작 **둘**을 고치지 않고 **그대로 비추고 제자리에 표시**했다.

- **안 읽히는 값은 승격되지 않는다.** `side: "Back"`을 확정된 선언으로 바꾸는
  확정은 이 어휘가 막으려는 사칭이다.
- **확정 아래에서 키가 없으면 `absent`가 아니라 `unparsable`을 답한다.** 이것은 서버
  분기의 실제 기벽이고, **같은 어휘 안의 `absent_key_is_not_unparsable`과 나란히
  놓으면 어색하다.**

> **이식하는 대상을 「고치는」 이식은 버그 수정의 옷을 입은 두 번째 구현이다.**
> 그래서 보고했고 고치지 않았다.

## 그때 남아 있던 것

- **`grid_assumed_from`은 클라에 철자가 아예 없다** — `client2/src`와
  `contracts/map2_seam` 통틀어 히트 0. 실측 2026-08-06: `grid_assumed_from`과
  `grid_start_x: 4`를 든 메타가 **서버에서 `{4, assumed}`, 여기서 `{4, declared}`**를
  답한다. **같은 부류, 다른 표지.** 보드에 올렸고 이 라운드에서는 고치지 않았다 —
  다른 표지에 다른 소유자이고, 확정 작업 옆에서 조용히 같이 닫으면 **두 변경이 하나의
  검수 불가능한 변경**이 된다.
- 이 커밋 시점 **`FRAME_CONFIRMED_KEY`와 `PHYS_CONFIRMED_KEY`는 읽는 자리가 다르다** —
  전자는 `frameFromDeclaration`(회전·면 **한정**), 후자는 `geometryDeclaration`(메타
  전체 판정). `grid_y_invert`와 `grid_start_*`는 **양쪽 어느 표지도 덮지 않는다.**
- 이 시점 클라 변경은 **소스에만** 있다. 화면에 닿는 것은 07:51의 빌드이고,
  그 빌드는 하루 종일 다른 것에 막혀 있었다 —
  [`20260806_074904`](./20260806_074904_the_contract_was_red_for_a_day_because_arguments_shifted_one_place_left.md) 참조.
