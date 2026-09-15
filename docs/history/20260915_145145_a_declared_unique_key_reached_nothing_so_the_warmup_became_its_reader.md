# 선언한 유일 키가 «아무 데도 닿지 않았다» — 그래서 웜업이 그 칸의 독자가 됐고, `key.columns` 는 «검사 칸»이 됐다

> **커밋:** `8cab58da` — feat(chain): a unified join's declared unique key is made by the product (S-240) · `07a568ad` — feat(chain): `key.columns` is read as a check, and RUN.md stops calling the cell dead (S-240 후반)
> **일자:** 2026-09-15 14:46 · 14:51
> **레인:** 구현자(서버) — 지시 `474f1aa9`(10:36) → 구현자 컴팩트로 트리 정지 13:11~14:3x → 초인종 `85baed87` → 재개 브리프 `44604384` → 착지 둘 → 보고 `7d1f77ee` → 총괄 닫힘 `dbecac4b` · RUN.md 절은 `d0c72ebe`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **16 + 2 = 18** · 변이 **11 «전부» 빨강**(첫 커밋에서 «둘이 빠져나가» 픽스처를 고친 뒤의 수) · rule_shape·join_into·builtins·unique_key·웜업·가상 조인 로더 모집단 **624 passed** · `--collect-only` **6,676** 에러 0 (구현자 보고). 총괄 확인 「70 passed · virtual_join 변경은 합집합 한 자리 · 부팅 오류 0 · 체인 17 · 재기동 PID 48808」(`dbecac4b`).

## ① 왜 — 「제품이 인덱스를 세웁니다」가 통합 join 에 대해 «거짓»이었다

```
계획          「선언이 key.unique 라고 말하면 제품이 성립시킨다」
RUN.md        「제품이 인덱스를 세웁니다」 — 그리고 같은 파일이 통합 join 의 그 칸을 「오늘은 읽히지 않습니다」라고 적고 있었다
실측          rule_shape.from_declaration 이 on · derive · into · limits «만» 싣는 고정 dict 를 만들었다
              -> key 는 «번역에서 떨어졌다». 운영자가 적을 수 있고 폼이 그릴 수 있는데 아래로 «아무것도» 안 갔다
```
빌더(S-235 의 `unique_key.ensure_once`)는 있었다. 없던 것은 **칸이 빌더에 닿는 길**이다 — 「폼이 그리는데 읽는 쪽이 없다」의 한 판 더.

## ② 변경 — 칸이 «규칙과 함께» 여행하고, 웜업이 «유일한 자리»로 잰 뒤 골라졌다

```python
# server/chain/rule_shape.py
def from_declaration(raw, origin="declared"):
    return {..., "into": dict(raw.get("into") or {}),
            "key": dict(raw.get("key") or {}),          # <- 떨어뜨리던 칸
            "limits": ..., "grammar": "unified"}
def as_chain_rule(internal):
    ...
    if internal.get("key"):
        out["key"] = dict(internal["key"])               # params «옆». 맵퍼 인자가 아니다 — join_into 는 이 칸을 못 본다
```
```python
# server/chain/join_into.py  — 이 모듈은 여전히 virtual_join 을 «모른다»(자기 경계 시험)
def right_key(rule) -> tuple:
    """(오른쪽 표, 그 조인 컬럼들, fold 들) — 유일 인덱스가 «덮어야 할 것». fold 가 «여기서» 정해지므로 «여기서» 묻는다(판정 397·S-181)."""
```
```python
# server/chain/builtins.py  — «껍데기»가 짓는다. 두 반쪽을 이미 아는 자리다
def ensure_declared_unique_keys(db, rules) -> dict:
    for name, table, columns, folds, skip in declared_unique_targets(rules):
        ...
        index_name = vjc.required_index_name(table, columns, folds)
        if index_name in seen: continue                  # 선언 하나 = 규칙 둘(대상 + :reference) = 인덱스 «하나»
        report["ensured"].append((name, unique_key.ensure_once(db, name, table, columns, folds)))
```
```python
# server/chain/ingestion_worker.py  warmup_worker()  — 0-bis
if db_session_factory is not None:
    try:
        _report = _chain_builtins.ensure_declared_unique_keys(_index_db, rules)
    except Exception as _key_error:
        logger.error("[Warmup] 선언된 유일 키를 세우지 못했습니다(체인은 계속): %s", _key_error)   # 워커가 «안 뜨는» 일은 없다
```
```
자리가 웜업인 이유   load_chain_rules() 는 세션이 없고, 읽기 경로는 §0-ter ① 이 새 SQL 을 금지하는 «바로 그» 자리
                  「규칙을 방금 (다시) 읽었다」와 「DB 가 있다」가 만나는 곳이 웜업 «하나»다. 기동 «그리고» 리로드마다 돈다
enabled:false     호출 «0» (판정 399 ③′) — 「OFF 가 DB 를 만지던」 09-14 의 결함 그 부류
```

## ③ S-248 이 이 트리 «위»에 착지했고, 이 인덱스를 «도로 걷어 갈» 참이었다

```
S-248         인덱스는 그것을 요구하는 조인만큼 산다 — retract_unrequired_once 가 «읽기 시점 선언»에서 required 를 계산해 나머지를 걷는다
이 라운드 뒤   요구하는 조인이 «두 종류»가 됐고 둘 다 uq_vjoin_ 접두다
              -> 웜업이 세운 인덱스를 다음 읽기가 걷고, 다음 재기동이 다시 세우고, 또 걷는다: «혼자 깜빡이는 스위치»
```
```python
# server/virtual_join/config.py  load_verified_rules()
required = {r["unique_index"] for r in verified if r.get("unique_index")}
required |= chain_builtins.declared_unique_index_names(known_tables=known_tables)   # «둘 다» 아니면 «아무것도»
unique_key.retract_unrequired_once(db, required)
```
`declared_unique_index_names` 는 로더와 «같은 판정기»(`rule_shape.expand_declaration`, S-244)로 선언을 편다 — 파일을 두 번 읽으면 「이 선언이 무엇을 세우나」에 답이 둘이 된다. 그 절반을 «못 읽으면» 회수는 아예 안 돈다: 반쪽 required 집합은 «덜» 걷는 게 아니라 «틀린 것»을 걷는다. 이 거절은 `retract_unrequired_once` 가 `path` 를 받는 호출자에게 이미 적어 둔 계약과 같다.
📌 이 조건은 지시 원문에 «없었다» — 컴팩트 뒤 재개 브리프(`44604384`)가 게이트 ⑥으로 «덧붙였다». 컴팩트 «전»에는 S-248 이 없었기 때문이다.

## ④ 픽스처 «둘»이 자기 가설을 못 담았고 변이 «둘»이 빠져나갔다

```
다른 종류 규칙   params 가 «없어서» 종류 검사를 빼도 한 줄 뒤 「오른쪽 키 없음」으로 떨어졌다 — 검사가 «없어도» 초록
               -> 지금은 맵퍼 이름 «하나만» 다른 규칙
fold           양쪽 다 표기 선언이 없으면 fold 가 None — «계산하는» right_key 와 «전부 None 을 돌려주는» right_key 가 구별 불가
               -> 픽스처가 표기를 «선언»하고, 접힌 키는 «다른 이름»(_nf)을 요구한다고 단언한다
```
📌 부류: **「범례가 단언을 공허하게 만든다」** — 두 픽스처 모두 「주장하는 그 한 가지»만 다르게 고쳐진 뒤에 변이가 잡혔다.

## ⑤ 후반 `07a568ad` — 첫 커밋이 «읽는 쪽 없는 칸»을 «하나 더» 남긴 채 닫힐 뻔했다

지시는 「`key: {columns, unique: true}` 를 로더가 읽어」였는데 첫 커밋은 `unique` 만 읽었다 — 이 라운드의 «이름»이 된 결함을 그대로 남긴 것이다.
```python
# server/chain/builtins.py  declared_unique_targets()
declared = [str(c) for c in ((rule.get("key") or {}).get("columns") or ()) if c]
if declared and declared != list(columns):
    yield (name, table, columns, folds,
           "key.columns %s is not this join's right key %s — the index covers the right key" % (declared, list(columns)))
    continue
```
```
key.columns 는 «고를 수 없다»   인덱스는 조인의 «자기» 오른쪽 키 위에 서야 PG 가 쓴다(S-181). 다른 컬럼에 세우면 pg_index 에 «있는데» 이 조인이 «안 쓰고», 쓰기는 «거절»한다
그래서 «검사 칸»              맞으면 아무 변화 없음 · 다르면 «두 목록을 이름 대고» 안 세운다 · 안 적어도 된다
```

## ⑥ 아키텍처 영향

- 통합 join 의 `key` 가 선언 → 내부형 → 체인 규칙 «왕복»을 살아남는다. 체인 규칙 안에서는 `params` «옆»에 앉는다(맵퍼 인자가 아니다).
- `uq_vjoin_` 인덱스의 «생산자»가 둘(읽기 시점 가상 조인 · 통합 join 웜업)이고, «요구 집합»은 한 자리(`load_verified_rules`)에서 둘의 합집합이다. 「무엇을 세우나」와 「무엇을 요구하나」가 `declared_unique_targets` «한 걷기»에서 나온다 — 둘이 어긋나는 날 인덱스가 «영원히» 세워지고 걷힌다.
- `join_into` ↔ `virtual_join` 경계는 그대로다. `join_into` 는 `right_key` 로 «무엇이 필요한가»만 답한다.

## ⑦ 그때 남아 있던 것

- **게이트는 전부 «가짜 세션»이다.** 이 박스에서 PostgreSQL 이 실제로 인덱스를 세웠는지는 «안 쟀다». 총괄 재기동(PID 48808)이 확인한 것은 「부팅 오류 0 · 체인 17」이지 `[VirtualJoin:이름] 유일 인덱스를 «제품이» 세웠습니다` 줄의 «관측»이 아니다 — 이 박스에 통합 join 선언이 없어 그 줄이 «나올 자리»가 없었다.
- 회수와의 정합은 「required 집합에 이름이 든다」까지다. 운영의 `pg_index` 에 대고 잰 것이 아니다.
- **해시 하나가 제목과 어긋난다.** `07a568ad` 의 제목이 RUN.md 를 말하지만 그 커밋에 RUN.md 는 «없다» — 구현자가 트리에 남긴 RUN.md 편집을 총괄이 공유 트리에서 주워 `d0c72ebe` 로 «먼저» 올렸다(내용은 그대로 main 에 있다 — `key.unique` 예시 · 재기동 때 일어나는 일 · 오른쪽 표에 중복이 있으면 «안 세우고» 값·건수를 로그에 냄 · `ASSY_VJOIN_AUTO_INDEX=0` · `key.columns` 는 검사 칸).
- 구현자 세션이 컴팩트로 13:11~14:3x «정지»했고, 미커밋 96줄(+96/−2)이 공유 트리에 그 시간 동안 노출돼 있었다. 초인종 커밋 + 재개 브리프 + 소유자 창 두드림으로 깨어났다.
- 이 채널의 미답 «없음». 다음은 S-245 → S-246 → S-247.

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 S-248(인덱스 수명 = 조인 수명): `20260915_115619_an_index_lives_exactly_as_long_as_the_join_that_requires_it.md` · 「OFF 가 DB 를 만지던」 부류: `20260915_094114_off_still_touched_the_database_and_a_probe_poisoned_the_read.md` · S-181(한 축 한 함수): `20260911_203000_two_blind_spots_got_screens_and_one_axis_got_one_function.md` §③.
