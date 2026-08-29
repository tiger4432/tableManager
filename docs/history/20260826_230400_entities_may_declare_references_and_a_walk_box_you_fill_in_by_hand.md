# 엔터티가 «참조»를 선언할 수 있게 됐고, 손으로 채우는 걷기 상자가 생겼다

> **커밋:** `450779fc` (19:30) · `67157f92` (20:39) · `62aac1c8` (21:58) · `e174a831` (22:58)
> · `b0cebe77` (23:04)
> | **일자:** 2026-08-26 저녁
> **레인:** 서버(선언 · walk) + 클라(보드)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 체인이 «한 홉 모자라» 멈췄고 조용했다

코어 다이에 닿은 체인이 **레시피를 든 웨이퍼 직전에서** 섰다. 조용했다 — 노드 206 / 엣지 259.

BFS «뒤»에 합성하면 엣지 117 · 웨이퍼 17 · 레시피 **0**.
BFS «안»에서 하면 노드 839 · 웨이퍼 601 · 레시피 **5**.

`450779fc`이 그것을 선언 주도로 만들었다. `server/ledger_api/entity_references.py`는
**새 파일(111줄)**이고, 그전에는 그 엣지가 **아예 없었다** — 하드코딩된 컨테이너 규칙이 있었던
것이 아니다. 이제 선언이 정하는 것: **이름 키 · `when` 판별자 · 대상 엔터티 · 그리고 엣지의 «이름»**.

같은 자리에서 실측된 것:

```
mat_type='Wafer' 밑 die mat_id 3,625 중 2,810이 wafer 엔터티로 «존재», 815는 «없음»
'DT' 밑은 358 중 348
```

## 선언은 «검증기가 이름으로 거절»한다

`e174a831`이 `entities.<type>.references`를 열고, `_validate_entities`의
`optional=("key_types", "allow_null", "references")`에 넣었다. 거절문은 이름으로 말한다:

```
binding takes exactly one of 'key' or 'value'
must name one of this entity's identity keys
keys must name the target entity's identity keys
must name a declared entity
condition must name one of this entity's identity keys
edge name must be a non-blank trimmed string
must be a list with at least one item
```

모르는 필드는 `problems.exact(ref, here, required=("edge","to"), optional=("from",))`가 거절한다.

🔴 **그런데 `450779fc`이 자기 docstring 예제에 단수 `"to": {"entity": "wafer@1", "key": "wafer"}`와
`from.key`를 적었고, `67157f92`이 그것을 복수 `keys`로 바꾸면서 `from.key`를 뺐다.**
`e174a831`의 검증기는 복수 모양에 맞고 **단수 모양을 거절한다** — 즉 `450779fc`이 커밋한 그
문서 예제는 나중 검증기에 걸린다.

## 걷기 상자 — 타입 · 키 · follow · collect 를 손으로 고른다

`b0cebe77`이 `client2/src/rnd_board/walk_box_panel.js` **327줄**을 만들었다
(하니스 `rnd_board_walk_box_harness.mjs` 363줄, 단언 36 / 0).

이 시점의 저장소 쓰기 규율: **`goto(id)` 같은 진입점은 아직 «없다».** 패널이 저장소에 쓰는
자리는 **정확히 하나** —
`onRowClick: (id) => { this.mark(id, SIGN.CASE, 'replace'); this.render(); }` — 이고
`Panel.mark`를 지난다. 선택 상태(`nodeType`·`keyValues`·`follow`·`collect`)는
**전부 인스턴스 안**이고 저장소에 안 쓰인다.

## 도달 체인이 «일어난 순서»로 정렬된다

`62aac1c8`. 목적지 목록이 `Set`에서 나와서 **서버 응답 순서**가 곧 화면 순서였다. 이제
술어별로 묶고 시각으로 정렬하며, 시각이 없으면 `span`이 `null`이다.

## 아키텍처 영향

- **엔터티가 참조를 선언한다.** 컨테이너 엣지가 코드가 아니라 선언에서 나오고, 엣지 이름까지
  선언이 정한다. 잘못된 철자는 전부 **이름으로 거절**된다.
- 참조 링크가 **BFS 루프 «안»**에서 만들어진다 — 뒤에 합성하면 레시피에 안 닿는다.
- 걷기 상자가 생겼다. 이 시점엔 선언 라우트가 없어서 **아직 못 답한다.**

## 그때 남아 있던 것

- **`GET /api/ledger/declaration`이 «없다».** 걷기 상자는 `BOARD`에 안 앉았고 dist 는
  바이트 동일하다.
- 🔴 **커밋 본문의 subject 목록과 파일 자기 헤더가 다르다.** 본문은
  `wafer@1 -> bonded_from · inspected · processed_with · register`와 `lot_slot@1 -> has_wafer · slot_map`,
  파일 헤더는 `wafer@1 -> inspected · processed_with · register`(`bonded_from` 없음)와
  `lot@1 -> derived_from · register`(`lot_slot@1` 줄 없음). `die@1`과 `recipe@1 -> NOTHING`만 일치한다.
- `450779fc`의 문서 예제는 **나중 검증기가 거절할 모양**으로 커밋됐다.
