# 인덱스는 «그것을 요구하는 조인»만큼만 산다 — 제품이 자기 인덱스를 걷어내고, 실패 줄이 «원인»을 싣는다

> **커밋:** `90d971ba` — fix(virtual-join): an index lives exactly as long as the join that requires it (S-248)
> **일자:** 2026-09-15 11:56
> **레인:** 구현자(서버) — 지시 `e0e0a25d`(S-249 «보다 먼저, 지금») → 착지 → 보고 `15347139` → 총괄 닫힘 `dc5f1310`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **8** · 변이 다섯 «전부» 빨강(메모 망각 1 · 스위치 무시 1 · 요구되는 것까지 DROP 2 · probe 실패를 던짐 1 · 원인을 첫 줄로 1) · `unique_key`·`virtual_join`·실패 줄 모집단 **977 passed** · `--collect-only` **6,634** 에러 0 (구현자 보고). 총괄 확인 「855 passed · 박스 부팅에서 남은 제품 인덱스 «둘» 걷어냄 줄 실증 · 체인 17 그대로 · 재기동 PID 22964」(`dc5f1310`).

## ① 왜 — 운영 장애를 «질문지»로 산정했다 (운영 로그는 밖으로 못 나온다)

```
소유자 답안   main 재기동 뒤에도 enrichment_dedup: 규칙이 «매번 다른 행»에서 「Transaction … permanently failed」
             그 줄 밑 traceback 은 잘려 원인이 «안 보임» · 앞서 「중복 키」 낱말은 uq_vjoin
             소유자 선택: 「제품이 되돌리게 기다림」(손으로 DROP 안 함) · 「너가 직접 하지 말고 세션 맡겨」
총괄 산정     09-14 S-235 가 dt_inventory 에 uq_vjoin_dt_inventory_… 를 «그 순간의 데이터»(중복 0)로 세웠다.
             그 조인이 이튿날 거절·이관·꺼진 뒤에도 «인덱스는 남았다».
             dedup 이 넣는 새 inventory 행이 그 키에 부딪혀 23505 -> 그룹 영구 실패 -> 재시도마다 «다른 행»에서 같은 실패
🔴 쓰기 관문   crud.refuse_virtual_join_duplicates 는 «검증된 규칙»의 키만 안다
             -> 규칙이 사라진 인덱스는 관문 «밖»에서 문다. 「규칙 없는 인덱스」가 병이다
```
📌 「인덱스를 세운 날」(`d3a92648`, 09-14)에는 없던 물음이 「인덱스를 «누가 거두나»」였다. 세우는 손만 있고 거두는 손이 없었다.

## ② 변경 — 층 «둘», 저자 «하나»

```python
# server/virtual_join/unique_key.py
def product_indexes(db) -> list:
    from virtual_join.config import INDEX_PREFIX          # <- 접두를 «다시 적지 않는다»
    rows = db.execute(text(
        "SELECT t.relname, i.relname FROM pg_index x "
        "JOIN pg_class i ON i.oid = x.indexrelid JOIN pg_class t ON t.oid = x.indrelid "
        "WHERE x.indisunique AND i.relname LIKE :prefix"), {"prefix": INDEX_PREFIX + "%"}).fetchall()

def retract_unrequired_once(db, required) -> dict:
    key = frozenset(required or ())
    if key in _RETRACTED: return _RETRACTED[key]           # 요구 집합마다 «한 번»
    if switch in ("0", "false", "off", "no"): ... return   # OFF = DB 무접촉
    if dialect != "postgresql": ... return                 # 이름 대고 skip
    try: present = product_indexes(db)
    except Exception: db.rollback(); ... return            # probe 실패 = 롤백 + 사유, 던지지 않음
    for table, index_name in present:
        if index_name in key: kept.append(index_name); continue
        statement = 'DROP INDEX CONCURRENTLY IF EXISTS "%s"' % index_name
        with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(statement))            # 하나 실패해도 나머지 계속
```
```python
# server/virtual_join/config.py  load_verified_rules() 끝
if path is None:                                           # 부분 목록으로 «실물»을 지우지 않게
    try:
        unique_key.retract_unrequired_once(db, {r["unique_index"] for r in verified if r.get("unique_index")})
    except Exception as retract_error:                     # 로딩은 «절대» 안 깨진다
        logger.warning("[VirtualJoin] 제품 인덱스 회수를 건너뜁니다(로딩은 계속): %s", retract_error)
```
🔴 **접두가 안전장치의 «전부»다.** 운영자가 자기 이름으로 세운 유일 인덱스는 `uq_vjoin_` 로 시작하지 않으므로 이 함수의 «모집단 밖»이다. 접두 문자열은 `config.INDEX_PREFIX` «하나»에서 읽는다 — 「어느 것이 우리 것인가」에 답이 둘이면 안 된다.
🔵 §0-ter 의 문장이 «태어날 때부터» 걸렸다: 읽기 경로에 더한 것은 memo 뒤의 probe «하나»(요구 집합당 프로세스에 한 번) · OFF 는 DB 무접촉(같은 날 아침 `1497ea3e` 가 「OFF 인데 probe 하던 스위치」로 읽기 경로를 죽인 그 문장) · 못 지우는 인덱스 하나는 «그 하나»다.

## ③ 그리고 이 장애가 «하루 동안 안 보였던» 이유를 같이 고쳤다

```python
# server/chain/ingestion_worker.py
def failure_cause(error_reason) -> str:
    lines = [line.strip() for line in str(error_reason or "").splitlines() if line.strip()]
    return lines[-1] if lines else "(no reason recorded)"     # <- «마지막» 줄. 첫 줄은 「Traceback (most recent call last):」다
...
logger.error("Transaction %s permanently failed: %d event(s) -> FAILED. 원인: %s",
             tx_id, failed_permanently_count, failure_cause(error_reason))
```
종전은 `_why[0]` — traceback 의 «첫 줄»이었다. 운영자가 받은 한 줄이 아무 말도 안 했고, 원인을 적은 문장은 잘린 아래에 있었다.
📌 «함수로 빼서» 직접 채점했다 — 모듈 텍스트를 읽는 단언은 줄이 재배치되면 빨개지고 주석에 낱말이 들어가면 초록이 된다(같은 날 판정 402 커밋이 «정확히 그 병»을 옆 시험에서 잡는다).

## ④ 아키텍처 영향

- 「인덱스 수명 = 규칙 수명」이 «코드로» 강제된다 — 검증 로더의 끝에서, 기본 선언 파일일 때만. 이 자리 밖에서 세운 `uq_vjoin_*` 는 없으므로(세우는 손이 `ensure_once` 하나) 회수도 그 짝에서 산다.
- 쓰기 관문이 «검증된 규칙의 키»만 안다는 사실은 그대로다 — 이 커밋은 관문을 넓힌 것이 아니라 «관문 밖의 것»을 없앤 것이다.

## ⑤ 그때 남아 있던 것

- 구현자가 «안 잰 것»을 스스로 적었다: 이 박스의 라이브 `uq_vjoin_dt_inventory_…` 가 다음 로드에서 실제로 걷히는지 — 재기동은 총괄 몫. 총괄이 재기동(PID 22964)하고 «부팅에서 남은 제품 인덱스 둘을 걷어내는 줄»을 실증했다(`dc5f1310`). 그러나 **운영에서 dedup 영구 실패가 멎었는지는 이 시점에 아무도 모른다** — 소유자가 pull + 재기동 뒤 `[VirtualJoin] 인덱스 … 걷어냈습니다` 줄을 보는 것이 남은 확인이었고, RUN.md 에 그 줄과 뜻이 실렸다.
- 조인을 «다시 켜면» 제품이 인덱스를 «다시 세운다»(`ensure_once`) — 회수 줄의 「다음: 없음」이 그 뜻이다.
- 이 채널의 미답이 «둘» 열려 있었다: S-242 ②의 격리 범위 · S-249 의 ㉠/㉡/㉢.

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 소유자 질문지 답안뿐이다.
📎 `ensure_once` 가 세운 날: `20260915_093113_the_day_strictness_invalidated_what_was_already_running.md` §② · OFF 가 DB 를 만지던 아침: `20260915_094114_off_still_touched_the_database_and_a_probe_poisoned_the_read.md`.
