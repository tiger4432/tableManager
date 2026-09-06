# 반환을 «안 받은» 호출 하나가, 병합 이력을 «가끔»이 아니라 «항상» 잃게 하고 있었다

> **커밋:** `ce7dd982` (18:28)
> | **일자:** 2026-09-06
> **레인:** 구현자(서버)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 무엇이 일어났나

`crud.py` 의 `create_audit_log` 호출 «열» 중 «하나»가 반환을 «안 받는 맨 문장»으로 쓰여 있었다.
그 하나가 `apply_row_update_internal` 안의 **충돌 병합(collision_merge)** 자리다.

```
`create_audit_log` 의 «자기 독스트링»이 규칙을 적는다:
   `add_to_cache=False` 면 메모리 캐시를 건너뛰고 «`db.add` 도 건너뛴다» —
   반환된 dict 를 «모으는 것»은 «호출자» 책임이다
호출자 아홉은 정확히 그렇게 한다. 이 하나가 dict 를 «버렸다»
=> 그 감사 행은 데이터베이스에도, 캐시에도 «안 갔다»
```

## 🔴 문장이 「가끔」이 아니라 «항상»인 이유 — 호출자를 «세서» 나온다

```
`apply_row_update_internal` 의 «산» 호출자는 «정확히 하나» (`_apply_batch_updates_once`)
그 호출자는 `logs_to_cache = []` 를 «무조건» 할당해 넘긴다
=> 이 갈래에서 `add_to_cache` 는 «매번» False 였다
=> 그 행이 «스스로» 살아남는 갈래가 «없다». 조용한 손실은 «전부»였다
```
🔵 이것이 「없어서 0」과 「가끔 0」을 가르는 자리다 — 호출자를 세지 않았으면
「간헐적」으로 적혔을 것이고, 그러면 «재현 안 되는» 결함이 된다.

## 확인한 것 (diff 실측)
```
-  create_audit_log(              <- 맨 문장
+  log_dict = create_audit_log(   <- 반환을 받고
+  if logs_to_cache is not None: logs_to_cache.append(log_dict)
+  주석이 「`add_to_cache` 는 False 이고 `create_audit_log` 는 «`db.add` 도» 건너뛴다」를 적는다
시험 `test_a_collision_merge_leaves_history.py` (183줄)
```
📎 큐 등급 0 «L-3».
