# 뒤따르기 랩이 «홉»이 됐고 한 원인은 «한 번»만 받는다 — 그리고 랩이 이벤트를 접고 «왜 돌았나»를 말한다

> **커밋:** `b1e89e36` — fix(chain): the follow-up lap is a hop, and one cause gets one helping (S-249 ⓒ) · `6edf4db4` — fix(chain): the follow-up lap collapses its events, and one line says what woke it (S-249 ⓔ)
> **일자:** 2026-09-15 12:44 · 12:55
> **레인:** 구현자(서버) — 총괄 원인 확정 `e1b6bb0b`(12:3x) → ⓒ 착지 → 보고 `76b10db9` → 판정 403·404 `e290c6e8` → ㉮㉯ 픽스처 + ⓔ 착지 → 보고 `d9fcd70f` → 총괄 닫힘 `58cd1c9c`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** ⓒ 신설 **11** · 변이 여섯 «전부» 빨강 · 모집단 **1,277 passed** · collect 6,646 / ⓔ 신설 **5**(ⓒ 위에) · 변이 «열» 전부 빨강 · 모집단 **546 passed** · collect 6,651 (구현자 보고). 총괄 확인 「267 passed」(ⓒ, `e290c6e8`) · 「196 passed · 부팅 오류 0 · 체인 17 · 재기동 PID 36612」(ⓔ, `58cd1c9c`).

## ① 왜 — 소유자 「조인 체인 무한 실행되는데 뭐 땜에 실행되는지 모르겠음」 · 「한 행당 로그가 하나씩 뜨는 듯」

지시가 «먼저 재라» 했고, 구현자가 잰 것이 이 라운드의 «전부»다:
```
request_chain_depth 를 «세우는» 자리   git grep -> «한 곳»뿐 (그룹 단계 _process_chain_transaction_group_sync)
뒤따르기 드레인                      _drain_ledger_followup_sync 는 «자기 스레드·자기 세션» — 그 스코프 밖
=> 이 랩(_run_builtin_followups: 조인 오른쪽·auto_confirm)이 쓴 것은 chain_depth 키가 «아예 없고», chain_depth_of 가 None
=> 뒤따르기 랩을 지나는 고리는 «무한», 같은 고리가 그룹 단계 안이면 «유한» — 상한 «하나»에 답 «둘»
그리고                              그룹 경로는 outbox_mode(COLLAPSED) 안에서 쓴다(OUTBOX-4). 랩은 «안 접었다»
                                    -> 뒤따르기 쓰기 1,000 행 = 이벤트 1,000 = 큐 1,000 = 랩 1,000 = 줄 1,000
```
🔴 소유자의 «무한»과 «행당 로그» 둘 다 «이 한 자리»였다. 그리고 판정 402 의 정정대로 상한은 «새 칸이 아니라» `max_chain_depth` 다 — 없던 것은 «랩이 그 상한에 닿는 것»이었다.

## ② ⓒ 변경 — 원인과 홉이 큐를 «타고», 랩이 «한 홉 위»에서 돈다

```python
# server/ledger/followup.py
def enqueue(table_name, row_ids, event_type, transaction_id=None, chain_depth=None):
    _queue.append((str(table_name), ids, str(event_type), time.time(),
                   str(transaction_id) if transaction_id else None, chain_depth))   # <- 큐 튜플에 한 칸

def drain_once(engine, setup):
    table, row_ids, event_type, queued_at, transaction_id, chain_depth = item
    done = {..., "transaction_id": transaction_id, "chain_depth": chain_depth, ...}   # <- 원인이 caller 에게 «도착»
```
```python
# server/chain/ingestion_worker.py  _run_builtin_followups()
incoming_depth = done.get("chain_depth")
token_depth = request_chain_depth.set((incoming_depth or 0) + 1)      # <- 랩은 «한 걸음»이다
try:
    for rule in _followup_builtin_rules():
        fresh = followup_already_served(done.get("transaction_id"), table, rule.get("name"), row_ids)
        if not fresh:
            logger.info("[ChainBuiltin] rule=%s kind=%s table=%s — 이 원인(tx %s)의 행은 이미 한 번 받았습니다. 건너뜁니다.", ...)
            continue
        ...
finally:
    request_chain_depth.reset(token_depth)
```
```python
_FOLLOWUP_SERVED = OrderedDict()     # (원인 tx) -> {(표, 규칙): frozenset(이미 건넨 행)}. 유계
MAX_REMEMBERED_CAUSES = 512

def followup_already_served(transaction_id, table, rule_name, row_ids) -> list:
    if not transaction_id or not rows: return rows        # 원인 없는 배치(백필)는 «기억하지 않는다»
    ...
    fresh = [r for r in rows if r not in already]         # 나중에 «합류한» 행은 그대로 건넨다
```
```
「없음」은 «없는 채로»   체인이 아닌 편집은 홉이 없다 — 0 을 지어내면 «평범한 편집»이 캐스케이드 첫 걸음으로 보인다
그러나 랩의 쓰기는 «1»   들어온 홉이 없어도 (None or 0)+1 — 그 쓰기 «자체»가 한 걸음이고, 0 이라 부르면 첫 체인 쓰기가 «공짜 홉»을 얻는다
키는 (원인, 표, 규칙)     다른 규칙은 자기 몫을 받고, 같은 행이 «새 원인» 아래면 새 질문이다 — 옵트인의 «예외»는 예외로 남는다
메모는 유계             「영원히 도는 페이싱 경로의 무한 메모는 이름이 예쁜 누수다」
```
🔵 그룹 단계의 원칙 「체인이 쓴 행은 체인을 다시 깨우지 않는다 — 선언으로 켠 것만 예외」가 뒤따르기 랩에 «짝»을 얻었다. 같은 날 `1aa50d3d` 가 닫은 것은 «그룹 경로의 필터를 지나치던 라벨»(문 ③)이고, 이것은 «필터가 아예 없던 문»(문 ②)이다.

## ③ ⓔ 변경 — 랩이 이벤트를 접고, 줄이 «왜 돌았나»를 단다

```python
with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):          # <- 그룹 경로와 «같은» 컨텍스트 매니저, 같은 이유
    result = builtins.run_builtin(kind, db, rule, row_ids=list(fresh), done=done)
log_followup_folded(logger, rule.get("name"), table, len(fresh), (result or {}).get("written"),
                    "%s#%s" % (table, done.get("transaction_id") or "?"),         # woke_by
                    (incoming_depth or 0) + 1, event_constants.max_chain_depth(_RULES_DOCUMENT),   # hop=h/max
                    (result or {}).get("refusal"))
```
```
줄 모양       [ChainBuiltin] rule=… table=… rows_in=N written=M ← woke_by=<표>#<tx> hop=h/max
쓴 것이 0     DEBUG — 매 랩의 «평범한 경우»라 INFO 면 «일한 랩»을 가린다
거절         «언제나» 말한다 — 거절은 「아무 일 없음」이 아니다
접기         log_failure_folded 의 손: 첫 줄 + 500 마다, 유계 맵(2,000 키에서 비운다)
```

## ④ 판정 404 의 가설 «둘» — 픽스처로 돌렸고 «둘 다 수렴»했다

```
㉮ dedup 의 리스트 컬럼이 그룹의 log 행 «셋»에서 (순서가 매번 달라 no-op 이 안 잡히나)   랩 4, 3, 0 -> 수렴
㉯ join 의 take 컬럼이 dedup 의 decision_key 에 들어감 (변환이 «한 글자» 다르게 만드나)      랩 3, 1, 0 -> 수렴
㉯ + 한쪽에 fold 선언                                                                      랩 3, 1, 0 -> 수렴
```
⚠️ **㉯ 의 첫 판은 가설을 «못 담고» 있었다.** 지시는 「take 컬럼을 decision_key 에 넣고」인데 구현자가 `decision_key: ["job"]` 으로 두어 초록이 «다른 것에 대한 초록»이었다. `lot_confirmed` 를 키에(그리고 그 키를 덮어야 하는 파생 신원에) 넣자 «랩 수가 바뀌었고» — 그 변화가 이 픽스처가 주장하는 것을 «실제로 돌린다»는 증거다. 그러고도 수렴했다.
📌 부류: **「두 규칙이 같은 답을 내는 표본은 판별식이 아니다」** — 픽스처가 가설을 «담았는지»는 가설을 «켰을 때 수가 움직이는지»로만 안다.

## ⑤ 아키텍처 영향

- 홉 상한(`max_chain_depth`)이 «두 경로 모두»에 걸린다 — 그룹 단계와 뒤따르기 랩. 상한은 «한 자리»(드레인)에서 강제되고, 두 경로는 «같은 컨텍스트 변수»를 세운다. 새 경로가 생기면 «그 둘을 세우지 않는 것»이 «같은 모양»으로 다시 깨질 자리다.
- 아웃박스 접기(OUTBOX-4)도 «두 경로 모두». 접는 손은 `outbox_mode` 하나.
- 뒤따르기 큐 튜플이 «여섯 칸»이 됐다(표·행·종류·시각·원인 tx·홉). `_take()` 를 푸는 시험 둘이 같은 커밋에서 따라 움직였다.

## ⑥ 그때 남아 있던 것 — «유한함»이지 «원인»이 아니다

- 구현자가 «두 번» 적었고 총괄이 보드에 «다시» 적었다: **이 라운드가 주는 것은 «유한»(홉 상한이 랩에 닿음 + 한 원인 한 번 + 이벤트 접기)이지 «원인 소멸»이 아니다.** 구현자의 재현은 «랩 3 에 수렴»해 소유자가 맞고 있던 원인을 «못 봤다». ⓑ(근본 저자)는 판정 404 대로 「**운영 선언 없이는 못 본다**」로 닫혔다 — 운영 로그는 보안상 밖으로 못 나온다. 「나중 요약에서 조용히 「고쳤다」가 되기 쉬운 자리라 한 번 더 적는다」(구현자 원문).
- 게이트 Ⅰ(수렴)은 ⓒ «전»에도 초록이었다 — 즉 이 박스에서 「핑퐁이 멎었다」를 이 커밋으로 «증명한» 것은 없다.
- 총괄 재기동 PID 36612 · RUN.md 에 부팅 줄 넷(`[ChainBuiltin] … woke_by` · `[Chain Depth] … refusing` · `[ChainRules] 고리:` · S-248 의 회수 줄)이 «뜻»과 함께 실렸다.
- 이 채널의 미답 «없음». 다음은 판정 403 의 S-242.

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 소유자 원문과 판정 404 의 「운영 선언 없이는」뿐이다.
📎 문 ③(join 의 층 라벨): `20260915_113722_the_joins_writes_carry_the_chains_layer_so_they_cannot_wake_the_enrich_that_feeds_them.md` · 판정 402: `20260915_121153_a_cycle_is_a_shape_not_an_error_said_once_refused_nowhere.md`.
