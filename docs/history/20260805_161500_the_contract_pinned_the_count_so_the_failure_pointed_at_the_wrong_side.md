# 계약이 개수를 핀으로 박아서 실패가 엉뚱한 쪽을 가리켰다 — 그리고 이음매는 그것을 애초에 채점하지 않고 있었다

> **커밋:** `aa24bfd` (2026-08-05 16:15) | **일자:** 2026-08-05 오후
> **선행:** [`20260805_155500`](./20260805_155500_requiring_the_spec_first_asks_for_the_answer_before_the_question.md)(`0947972` — 여섯째 토큰 `assumed`를 만든 커밋) · [`20260805_074600`](./20260805_074600_a_ratchet_that_only_turns_one_way_stops_being_trusted.md)(`a099952`)
> **담당:** 계약 레인
> **대상:** `contracts/map2_seam/vectors.json`(1,517 / 1,397) · `client_harness.mjs`(23 / 4) · `test_map2_seam_contract.py`(+21) · `client2/src/map2/declaration.js`(50 / 13) · `client2/tests/frame_declaration_harness.mjs`(13 / 6) · `server/map_overlay.py`(9 / 1) · 스펙 2종
> **스위트:** 커밋 메시지 기준 **변이 13/13 · 서버 2,602 · 클라 하네스 둘 초록 · 이음매 양쪽 초록.**

## ① 개수를 박았더니 서버의 정당한 추가가 클라 결함으로 읽혔다

여섯째 출처 토큰을 더하자, **정확히 다섯 개라고 박아 둔** 하네스와 계약이 빨개졌다.

```js
  eq('B. exactly five tokens', TOKENS.length, 5);
```

> **실패가 엉뚱한 쪽을 가리켰다.** 규칙은 **「빌려라, 발명하지 마라」**였지
> 숫자가 아니었다. **숫자가 박기 쉬운 쪽이었을 뿐이다.**

이제 양쪽이 **토큰마다 이름과 위치로** 박는다.

```js
  eq('B. the four shared with map_overlay.py GEOMETRY_*, in that order',
    TOKENS.slice(0, 4).join(','), 'declared,auto_registered,absent,unparsable');
  eq('B. the fifth is map_overlay.py ORIENTATION_INDETERMINATE', TOKENS[4], 'indeterminate');
  eq('B. the sixth is map_overlay.py GEOMETRY_ASSUMED', TOKENS[5], 'assumed');
  eq('B. and nothing beyond the six the server spells', TOKENS.length, 6);
```

## ② 더 나쁜 것 — 이음매가 이것을 채점하고 있지 않았다

클라의 빌림 가지를 **변이로 삭제해도 모든 방향 케이스가 초록**이었다. 그동안
양쪽은 어긋나 있었다 — **클라는 `auto_registered`, 서버는 `assumed`.** 그것은
**방금 채점된 맵을 화면이 「채점 불가」라고 부르는 것**이다.

기존 케이스들은 **다른 질문에 답하고 있었다.** 새 군
(`geometry_declaration_cases`, 케이스 6건)이 이것을 채점하고 **변이가 죽는다.**

## ③ 새 토큰에 대한 독자 감사 — 하나는 저하가 아니라 죽었다

`geometry_refusal`이 문장 표를 **첨자로 접근**했다. 그래서 모르는 토큰이
**`KeyError` → 요청 전체 500**이었다. 그리고 **어휘가 자랄 때마다, 문장이 같은
편집에 같이 들어가지 않는 한 매 라운드 다시 나타났을** 것이다.

```python
# 이전
    return _GEOMETRY_REFUSAL_TEXT[token]
# 이후
    return _GEOMETRY_REFUSAL_TEXT.get(
        token, "물리 규격의 출처를 읽을 수 없습니다(미상 토큰 '%s')" % token)
```

**일부러 `None`으로 저하시키지 않았다** — 모르는 출처를 아무것도 아닌 것으로
접으면 **그것이 선언 행세를 하게 되고**, 그게 바로 이 어휘가 막으려는 것이다.

나머지 독자들은 이미 저하했고, 감사는 **「괜찮다」가 아니라 각각이 어느 쪽으로
가는지 — 거절인지 무시인지 —** 를 적었다. 물렁한 자리 하나는 **고치지 않고
스펙에 이름으로** 남겼다.

## ⚠️ +1,664 / −1,423이라는 규모는 대부분 들여쓰기다

`vectors.json` 혼자 1,517 / 1,397이고, 그 diff는 **단일 헝크**(`@@ -1,1415 +1,1535 @@`)다 —
**들여쓰기를 1칸에서 2칸으로 바꾼 전면 재직렬화**다.

| | 줄 |
|---|---|
| 변경된 총 줄 | ~2,914 |
| 공백만 다른 부분 | **~2,790** |
| 실질(코드·테스트) | ~147 |
| 실질(새 벡터) | ~120 |
| 실질(스펙) | 31 |

**diff 크기를 작업량으로 읽으면 이 커밋은 20배 과대평가된다.**

## 그때 남아 있던 것

- 스펙에 **고치지 않고 이름만 붙인 물렁한 독자 하나**가 남아 있다.
- 이 커밋 시점 클라의 여섯째 토큰은 **선언 로직에만** 들어갔다. 화면이 그 가정을
  **제안으로 보여 주는 것**은 26분 뒤 `0701968`이다.
