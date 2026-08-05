# 클라는 자기 거절에 이름을 붙일 수 있지, 서버의 거절을 개명할 수는 없다 — 그리고 면제는 파일 편의가 아니라 출처로 갈린다

> **커밋:** `cab77e7` (2026-08-05 07:56) | **일자:** 2026-08-05 아침
> **선행:** [`20260805_074000`](./20260805_074000_a_stored_coordinate_is_bounding_box_relative_and_a_catch_turned_every_failure_into_a_plausible_wafer.md)(`cab8ed9` — 새 모듈들이 들어온 커밋)
> **담당:** 제품 소유자(판정: 어휘는 공유, 문장은 서버 것) · map 구현
> **대상:** **소스는 `client2/src/map2/verdict.js`(+24 / −2) 하나** · `contracts/config_resolve_report/vectors.json`(+35 / −2) · 나머지 24경로는 전부 `client2/dist/`(번들 재빌드)
> **스위트:** 커밋 메시지에 결과 없음. 빌드 게이트가 **결과로** 풀렸다(목표가 아니라).

## 배경 — 계약 불변식이 새 모듈에서 22곳을 잡았다

`config_resolve_report` 계약의 **INV-F9-7**이 Map Editor 2 모듈들이 **서버의 사유
단어를 리터럴로 적는 것**을 잡았다. 금지 집합은 넷이다:

```
not_declared · mapping_unavailable · scope_unresolved · not_reached
```

**진짜 결함 하나와 오탐 하나**가 나왔고, 평균 내지 않고 **둘 다 기록됐다.**

## 진짜 — `verdict.js`가 서버의 거절을 자기 단어로 매핑했다

지워진 줄:

```js
  [REASON.SERVER_REFUSED]: 'mapping_unavailable',
  [REASON.SOURCE_REFUSED]: 'mapping_unavailable',
```

**이것이 이 불변식이 존재하는 실패 계급이다** — 클라가 **서버가 무슨 뜻이었는지에
대해 두 번째 의견을 획득**하는 것. 그리고 그동안 **서버 테스트는 전부 초록으로
남는다.**

대체:

```js
  if (verdict.reason === REASON.SERVER_REFUSED || verdict.reason === REASON.SOURCE_REFUSED) {
    return verdict.serverDegradation || null;
  }
```

## 오탐 — `excel_io.js`에는 서버가 없다

`excel_io.js`는 **붙여넣어진 산출물**을 거절한다. 그 경로에 서버가 없다 —
순회할 응답도, 렌더할 detail도, 반박할 남의 의견도 없다. 거기서 어휘를 가져오라고
강제하면 **닿을 수 없는 어휘를 대신할 사적인 단어를 지어내게 되고**, 그게 바로 이
불변식이 막는 것이다.

## 판정 — 면제는 **출처**로 갈리지 파일 편의로 갈리지 않는다

> **어휘는 공유고, 문장은 서버 것이다.**

시험은 **「이 모듈이 서버 응답을 소비한 적이 있는가」**다. `decode.js`와 `api.js`는
소비하므로 **금지 아래 남는다**(둘 다 네 리터럴에 대해 0건임이 확인됐다).

```json
    "allow_paths": [
      "client2/src/map2/excel_io.js",
      "client2/src/map2/artifact_gateway.js",
      "client2/src/map2/verdict.js"
    ]
```

`$allow_paths_why` 24줄이 그 시험과, `decode.js`·`api.js`를 **일부러 안 넣었다**는
것을 적는다.

**`verdict.js`는 자기 진짜 결함이 수리된 **뒤에야** 목록에 올라갔다** — 검사를
건너뛰는 수단으로 오른 적이 없다.

## ⚠️ diff가 커밋 메시지와 어긋난 자리 — 옮겨 오는 경로가 아직 없다

커밋 메시지는 「서버의 단어가 그대로 실려 오고, 서버가 아무 말도 안 했으면 null이
반환된다」고 적는다. **이 커밋 시점 `verdict.serverDegradation`에는 생산자가
없다.** 그 식별자는 트리 전체에서 **읽는 자리 한 곳(`verdict.js:142`)에만**
나타난다. `frozen()`이 만드는 판정 레코드는 `kind, reason, winnerId, rankedIds,
marginDies, discriminating, minMargin, minDiscriminating, tiedCount, refusalDetail…`을
세우고 **`serverDegradation`은 세우지 않으며**, `decode.js`도 `view_model.js`도
세우지 않는다.

> 즉 `degradationFor()`는 `SERVER_REFUSED`/`SOURCE_REFUSED`에 대해 **무조건 null**을
> 돌려준다. **「null인 쪽」만 도달 가능하다.**

**서버의 문장 자체는 살아 있다** — 다만 이 이름이 아니라 `refusalDetail`로
실려 온다.

## 빌드 게이트

`dist`가 이 커밋에서 재빌드됐다 — `map_editor2` 번들이 처음 들어가고, 기존
페이지들의 자산 엔트리도 함께 다시 해시된다. **게이트가 풀린 것은 목표가 아니라
결과다.**

## 그때 남아 있던 것

- **`serverDegradation`에 생산자가 없다.** 옮겨 오기는 계약상 선언됐고 배선은
  아직 반쪽이다.
- `artifact_gateway.js`는 함수들이 `NOT_IMPLEMENTED`를 던지는 **이름 붙은
  이음매**로 남아 있다.
- 페이지를 서빙하는 라우트는 여전히 없다 — 7분 뒤 `39b43ab`.
