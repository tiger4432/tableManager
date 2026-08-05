# 제안에 독자가 없었다 — 서버가 두 커밋 동안 답하고 있었는데 아무도 듣지 않았다

> **커밋:** `0701968` (2026-08-05 16:41) | **일자:** 2026-08-05 오후
> **선행:** [`20260805_155500`](./20260805_155500_requiring_the_spec_first_asks_for_the_answer_before_the_question.md)(`0947972` — 제안을 만든 커밋) · [`20260805_161500`](./20260805_161500_the_contract_pinned_the_count_so_the_failure_pointed_at_the_wrong_side.md)(`aa24bfd`)
> **담당:** map 구현
> **대상:** **신규 하네스** `client2/tests/map2_geometry_assumption_harness.mjs`(**+524**) · `client2/src/map2/main.js`(109 / 1) · `decode.js`(+107) · `view_model.js`(70 / 3) · `session.js`(45 / 1) · `api.js`(18 / 2) · `check_harnesses.mjs`(+13)
> **스위트:** 커밋 메시지 기준 **단언 74, 바닥 등록.** `check_harnesses.mjs`의 바닥이 `['map2_geometry_assumption_harness.mjs', 74]`로 확인된다.

## 배경 — 서버가 두 커밋 동안 답하고 있었다

서버는 **「바닥의 웨이퍼를 공유한다고 가정하면 이 맵들은 채점될 수 있다」**를
`0947972` 이후 계속 답하고 있었고, **아무도 그것을 읽지 않았다.** 제안에 독자가
없으니 **화면은 막다른 길을 그렸고, 운영자는 그런 길이 있다는 것을 알 방법이
없었다.**

> **이 라운드에서 서버 능력이 나가고 클라가 배선하지 않은 것이 세 번째다** —
> 참조 카탈로그, 컬럼 파라미터, 그리고 이것.

## 제안은 한 줄이고, 마지막 토큰이 서버의 문장 그대로다

```js
    if (vm.assumption.line) parts.push(vm.assumption.line);
```

`view_model`은 페이로드에서만 그 문장을 세운다(`line: a && a.text ? String(a.text) : ''`).
**바닥의 이름을 대는 것은 서버의 문장이 그것을 대기 때문**이고, **클라는 그
옆에 한국어를 짓지 않는다** — 클라가 짓는 것은 확정 슬롯의 한 단어 라벨
`기하 가정`뿐이다.

## 수락은 정확히 그것 하나만 보낸다

```js
      if (r.assumeReferenceGeometry === true) q.assume_reference_geometry = 'true';
```

**`=== true`에서만 방출되고 그 외에는 생략된다.** 그래서 truthy한 쓰레기 값은
조용히 가정되는 게 아니라 **거절로 채점된다.**

## 절대 걸쇠가 걸리지 않는다

플래그는 **질문 위에** 산다. 클릭 한 번이 기존 시퀀스 가드를 통과하는 **재질문
한 번**이고, **다음 행에서, 테이블이나 참조가 바뀌면 떨어진다.**

```js
    question: Object.freeze({ ...session.question, assumeReferenceGeometry: false }),
```

```js
  if (patch && patch.assumeReferenceGeometry === undefined
      && (patch.mapTable !== undefined || patch.reference !== undefined)) {
    merged.assumeReferenceGeometry = false;
  }
```

> **자기가 대상으로 삼은 것보다 오래 사는 가정이, 빌린 기하가 눈치채지 못한
> 기본값이 되는 경로다.**

`decode.js`는 모르는 상태를 **거절하고**, 모르는 값은 `unavailable`로 접으며,
`offered = state === 'available' && !!basis`로만 제안을 연다.

## 가정된 결과는 모든 층에서 다르게 읽힌다

주석의 어조가 뒤집히고, 워크벤치가 상태를 싣고, 행마다 자기 기하와 근거를
공개하고, 확정 슬롯이 **정렬이 기하를 빌렸다**고 말한다.
**쓰기는 차단이 아니라 공개된다** — 가정 아래에서 확정하는 것은 운영자의 판단이고,
**기록이 그가 그렇게 했다고 말한다.**

## 하네스가 헛돌지 않는다는 것을 네 가지로 보였다

전송을 빼면 B2/B3 사망, 리셋을 빼면 D1 사망, 제안 줄을 빼면 G2 사망, 행 표시를
빼면 G12 사망. **매번 바이트 스냅샷에서 복원**했다.

## 덮지 않고 이름 붙인 구멍 둘

- **질문을 요청으로 매핑하는 리터럴이 커버되지 않는다** — 그 파일이 import 시점에
  자기 시동을 걸기 때문이다(양쪽은 따로 채점된다).
- **이 박스는 정렬 규칙을 선언하지 않는다.** 그래서 라이브 경로는 서버가 아니라
  **로더를 바꿔 끼운 진짜 모듈과 DOM**으로 굴렸다.

## 그때 남아 있던 것

- **누를 컨트롤이 없다.** 배선이 `me2-assume-accept`를 이름으로 바인딩하는데
  **마크업이 그 노드를 노출하지 않는다.** 페이지가 그것을 로그로 남긴다 —
  17분 뒤 `6f0a328`이 버튼을 붙인다
  ([`20260805_165800`](./20260805_165800_the_offer_had_no_control_to_accept_it.md)).
