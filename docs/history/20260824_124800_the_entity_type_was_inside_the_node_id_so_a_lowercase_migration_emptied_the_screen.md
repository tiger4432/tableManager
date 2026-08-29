# 타입이 «노드 id 안»에 들어 있어서, 소문자 마이그레이션이 화면의 walk 패널 둘을 통째로 비웠다

> **커밋:** `9367adfd` (11:08) · `589148d1` (11:19) · `d9e14b35` (12:33) · `777cedb7` (12:48)
> · `74407096` (16:31) · `1a4f2e62` (16:23)
> | **일자:** 2026-08-24 낮
> **레인:** 서버(마이그레이션) + 클라(씨앗 재철자)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 엔터티 타입 철자를 소문자로 통일한다

`server/scripts/lowercase_entity_types.py`가 두 컬럼을 다시 쓴다:

```
subject_type                                    340,548 행
object_payload->>'type'  (object_kind='entity_ref')  2,189 행
```

**일부러 뺀 것:** `object_kind='value'` 밑의 중첩 `type` **72,964** — 그건 «프레임» 이름
(`dt_slot`·`package_gate`·`wafer_grid`·`dt_job`·`bond_layer`)이지 엔터티 타입이 아니다.
`die`는 이미 소문자여서(subject 1,405 · object 참조 119,067) **지도에서 일부러 빠졌다.**

🔴 지시서가 놓친 위험을 커밋이 스스로 찾아 먼저 셌다: **`uq_ledger_atom`이 다시 쓸 컬럼 «둘 다»를
덮는다.** 그래서 충돌을 먼저 세는 `--check`를 붙였다.

## 🔴 그리고 클라가 통째로 비었다 — 타입이 «id 안»에 있다

보드는 walk 씨앗을 **base64 로 인코딩된 노드 id** 로 선언하는데, 그 안에 엔터티 타입이 들어
있다. 그래서 모든 씨앗이 **은퇴한 철자로 디코드**됐다.

```diff
# client2/src/rnd_board/main.js
-  start: { groupby: 'wafer', value: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0xMDMtMTEifV0' },
+  start: { groupby: 'wafer', value: 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1CVy0xMDMtMTEifV0' },
```

`WyJXYWZlciIs…`는 `["Wafer",…]`, `WyJ3YWZlciIs…`는 `["wafer",…]`로 풀린다 —
**타입이 문자 그대로 id 안에 있다.** 선언 여섯이 다시 철자됐다.

## 서버 쪽 사상자 둘 — 각각 «한 값»이었다

```
server/config/sample/siblings_axes.json.sample   "type": "Wafer" -> "wafer"
   337,389행이 옮겨진 뒤 /siblings?scope= 가 no_atoms_for_subjects 로 떨어졌다
   전: 빈 값 · 후: ready, 후보 20, 주체당 원자 260

server/ledger_api/ledger_identity.py             SUBJECT_TYPE = "Wafer" «삭제»
   관측 원자 115,423 중 «0»과 매치되고 있었다. 삭제 후 11,570이 들어왔다
```

`74407096`이 그 상수를 지운 이유가 기록됐다 — **grain 이 subject type 을 선언해야지 마크
헬퍼가 하면 안 된다.**

## 🔴 어떤 축은 «절대» case 쪽을 못 만든다 — 그것을 선언에 적었다

`777cedb7`. `leg:`와 `scan_recipe:` 축은 원장 주체보다 **더 잘게 자르기 때문에** case 쪽이
영원히 0이다(case 0 · 혼합 36 / 904). 대조 가능한 마킹 축이 무엇인지를 **그것을 정하는
선언에 실측으로 적었다.**

## 🔴 8분 사이에 같은 절을 두고 커밋 둘이 «다른 수»를 말한다

```
1a4f2e62 (16:23)   「원자 열여덟」
74407096 (16:31)   「원장 전체에서 그 키를 나르는 원자는 «12»」
```

**두 커밋 메시지가 서로 모순되고, 어느 diff 도 그 수를 담고 있지 않다.**
그 시점에 트렌드가 여전히 평평했던 이유는 축 2가 `object_payload ? 'bonding_leg'`를 요구하고
그 키가 `subject_keys`에도 실려 있었기 때문이다.

## 아키텍처 영향

- 원장의 엔터티 타입 철자가 **소문자 하나**로 모였다. 다시 쓰인 것은 `subject_type`과
  `entity_ref`의 `type`이고, **`value` 밑의 프레임 이름은 안 건드렸다.**
- **노드 id 가 타입을 담는다**는 성질이 실증됐다 — 타입 철자를 바꾸면 클라가 들고 있는
  «불투명한» 씨앗이 전부 죽는다.
- 마크 헬퍼가 subject type 을 안 들고 있다. grain 이 선언한다.

## 그때 남아 있던 것

- `9367adfd`의 「중복 0」은 **런타임 `--check` 출력**이고, diff 는 검사기만 더한다 —
  **그 수는 diff 로 확인되지 않는다.**
- **`1a4f2e62`와 `74407096`이 같은 대상에 18과 12를 적었다.** 둘 다 근거가 diff 에 없다.
- 트렌드는 이 시점에도 **평평**하다. 셋 중 하나만 막혀도 0이 된다.
