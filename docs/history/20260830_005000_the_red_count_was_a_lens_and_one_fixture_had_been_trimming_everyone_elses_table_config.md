# 빨강 «9» 는 측정이 아니라 «렌즈»였다 — 그리고 픽스처 하나가 남의 테이블 설정을 잘라 놓고 있었다

> **커밋:** `c1229106` (00:07) · `1d17c34a` (00:13) · `db9bb6bb` (00:14) · `a6317960` (00:16)
> · `6eab7ef4` (00:50)
> | **일자:** 2026-08-30 새벽
> **레인:** 서버(시험 수리 · 검증기) + 보드 기록
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 🔴 배경 — 「빨강 아홉」을 여러 번 보고했는데, 그건 «선택자가 정한 답»이었다

`a6317960`. `pytest -k ledger` 로 재서 아홉이라고 여러 번 적었다. **전수는 49다.**

```
-k ledger      «이름»에 ledger 가 들어간 시험만 고른다
test_syn_complex_composite.py   빨강 11 개 중 그 이름을 가진 것은 «정확히 1»
```

**렌즈를 넓히기 «전»에 그 아홉 위에 계획을 세웠다.** 몇 시간 전 문서 감사가 잡아낸 것과
**같은 실수의 grep 판**이다.

> ⚠️ 이 커밋 메시지는 **다시 쓰였다.** 처음 것은 `git commit -m` 안에 백틱을 썼고 셸이 그 안을
> 실행해 **pytest 실행 결과가 커밋 본문에 박혔다.** 그 규칙은 이미 메모리에 있었고, **이번이 두 번째**다.

## 픽스처 하나가 «모듈 전역»을 갈아 끼우고 돌려놓지 않았다

`db9bb6bb`. `db_session` 은 함수 스코프인데 쓰는 대상이 **모듈 전역** `crud.TABLE_CONFIG` 였다.
그래서 **한 세션에서 이 픽스처를 처음 부른 시험이 그 뒤 «전부»의 테이블 설정을 바꿔 놓았다.**

```python
# server/tests/conftest.py — db_session
saved_table_config = dict(crud.TABLE_CONFIG)
models.init_dynamic_models(test_table_config)
crud.TABLE_CONFIG.clear()
crud.TABLE_CONFIG.update(test_table_config)
...
crud.TABLE_CONFIG.clear()
crud.TABLE_CONFIG.update(saved_table_config)
```

```
test_syn_complex_composite.py   단독 26/26 통과 · 스위트 안에서 «11» 실패
왜                             씨앗이 crud.assemble_composite_business_key 로 inspection_run
                              업무키를 조립하는데, 그 표가 시험 설정에 «없다» -> None
증상이 뜬 자리                   «세 파일 건너»에서 「inspection_run key unavailable for
                              SYN-CX-BW-001@1,4」 — 픽스처도 누수도 이름에 안 나온다
```

🔴 **이미 저장·복원을 하던 픽스처 «둘»이 있었는데, 그것들은 «이 픽스처가 이미 갈아 끼운» 설정을
스냅샷하고 있었다** — 그래서 **성실하게 누수를 복원했다.**

`-k "ledger or syn_complex"` 가 빨강 14 → 2 로 갔고, 남은 둘은 뒤에 나오는 `in_slot` 결함이다.

## 네 갈래를 «가족으로 묶지 않고» 하나씩 쟀다

`1d17c34a`.

```
source_preparation   "server/ledger/source_preparation.py" 를 열고 있었다 -> 레포 루트에서만 풀린다
                     스위트는 server/ 에서 돈다 -> FileNotFoundError. 자기 파일 기준 경로로 (자리 «둘»)
admin_setup          은퇴한 ledger_api/ledger_selection 의 SQL 문자열 «넷»을 비교하고 있었다
                     네 함수 다 트리에 «없다» -> 묘비를 달고 은퇴. 불변식은 묘비가 들고 있다
transfer_unit        운영자 선언이 dt_log 를 transfer 종류로 싣는다고 단언 -> 이 박스의 «어느» 선언도 아니다
                     라이브+샘플 소스 14 개 전부 kind: null. R-2026-08-29-T 의 «반대 절반»이었다
skeleton             검증기 자리 «셋»(_validate_references 와 from/to)에 스켈레톤이 놓인 적이 없다
                     -> 스켈레톤에 references 노드가 «아예» 없었고, 그래서 admin 폼이
                        운영자가 쓸 수 있는 칸을 «내놓지 못했다»
```

묘비는 **왜 은퇴했나만 적지 않고 무엇이 되살리나를 같이 적었다.**

```python
# server/tests/test_ledger_transfer_unit.py
# 🗄️ RETIRED 2026-08-30 — ... WHAT BRINGS IT BACK: declaring a transfer source turns
# `test_every_declared_derivation_is_explicitly_classified` red until the derivation is
# classified, and that is the moment to restore this assertion with it. The GRAMMAR is
# still covered by the fixture-config tests below, which do not read the live file.
```

그리고 **검증기가 `continues` 를 다시 거절한다.** 그 관용의 주석이 스스로 「선언이 청소되는 날까지」라고
시한을 적어 두었고, `36802e42` 가 청소했다 — 잰 뒤로 라이브와 샘플이 «0» 이고 백업 스냅샷만 그 낱말을 갖는다.

```python
# server/ledger/setup_bundle.py — _validate_vocabulary
if not problems.exact(
        item, path, required=("status", "subjects", "object")):
```

`pytest -k ledger` 9 → 3.

## 커서가 움직였는데 픽스처가 옛 짝을 그대로 말하고 있었다 — 그리고 그것이 «진짜 결함»을 가리고 있었다

`c1229106`. `lot_event` 의 키셋이 `(event_time, row_id)` 로 옮겼는데 픽스처는
`(event_time, txn_seq)` 를 계속 말했다. 빨강 셋이 그 표류였다.

```
프레임에 row_id 가 없었다 · cursor_for 가 옛 짝을 «철자»하고 있었다
거절 시험의 가짜 커서는 «모양»이 틀려서 앞선 가드가 먼저 답했고
   -> 그 시험이 겨냥한 «버전 가드»는 한 번도 발화하지 않았다
```

`cursor_for` 는 이제 컬럼을 철자하지 않고 **계획에서 읽는다** — 그것이 애초에 보조를 맞춰 줬을 것이다.

**넷 중 둘이 «더 안쪽»에서 실패하기 시작했다** — 커서 불일치가 가리고 있던 것이다.

```
RoleFrameError: bundle.sources.lot_event.bind.mappings.in_slot.bind.subject.keys:
a mapper-supplied Entity reference carries one identity key
```

```
lot_event 의 매퍼   lot-event-role · unit: event  -> 문장을 내고 «역할당 스칼라 하나»를 준다
in_slot 의 주어     lot_slot@1                    -> 식별키가 «둘»이다
다중키 자체는 문제가 아니다   die@1 은 키 «넷»으로 declarative-role 아래 다섯 소스에서 돌고,
                        lot_slot_move 는 «같은 두 키 엔티티» 위에 slot_map 을 이미 낸다
원장이 동의한다        has_wafer 원자 «0» · slot_map 135 · register 396
```

🔴 **보드는 그 «0» 을 「소스가 선언되지 않았다, 선언하라」 밑에 넣어 두고 있었다.**
소스는 **선언돼 있고 문장 넷 중 셋이 돈다.** 그래서 **시험을 고치지 않고 빨간 채로 두고 결함을 이름 붙였다** —
고치는 것은 선언 판정이지 시험 편집이 아니다.

## 렌즈를 넓혀 다시 셌다

`6eab7ef4`. 전수 **31 failed · 4,062 passed**.

```
통과가 «18» 이 아니라 «16» 늘었다 — 수리 둘이 «은퇴»였기 때문이다.
주어가 없어진 시험은 통과하기 시작하는 게 아니라 «세어지지 않게» 된다
```

```
13   엔티티 id 부류. 선언이 08-28 에 소문자로 내린 것을 픽스처가 Lot·Wafer 로 부른다
      (한 파일은 선언에 없는 lot_event 매핑도 기대한다)
      기록된 놓침: 4b6f3f90 이 그 부류를 «시험 아홉»이라 불렀다 — 부류가 그때 센 구성원보다 «멀리» 간다
 2   in_slot 롤프레임 결함
16   «일부러» 미분류. 그중 열네 파일은 «열어 보지도 않았다» —
      읽기 전에 부류라고 부르는 것이 이 보드가 계속 기록하는 실수다
```

## 스위트

```
db9bb6bb 시점   -k "ledger or syn_complex"  14 red -> 2
1d17c34a 시점   -k ledger                   9 red -> 3
6eab7ef4 시점   전수                        31 failed · 4,062 passed
```

## 아키텍처 영향

- `db_session` 이 자기가 갈아 끼운 모듈 전역을 **복원한다.** 시험 순서가 답을 정하는 경로 하나가 닫혔다.
- 검증기가 `continues` 를 **거절**한다 — 은퇴한 낱말이 살아 있는 규칙으로 조용히 읽힐 자리가 없다.
- `ledger_skeleton.json` 에 `references` 노드가 있어 admin 폼이 그 칸을 내놓는다.
- 시험 둘이 **`in_slot` 이 emit 하지 못한다는 사실을 빨강으로 들고 있다.**

## 그때 남아 있던 것

- **`in_slot` 은 emit 하지 못한다.** 결과로 `has_wafer` 는 원자 «0» 이고, 이 시점에 보드의 분류가
  그 0 을 「소스 미선언」으로 읽고 있다 — 커밋 본문이 그 분류가 틀렸다고 적었다.
- 전수 빨강 31 중 **16 이 미분류**이고 그중 열네 파일은 이 시점에 열린 적이 없다.
- `-k ledger` 로 잰 수는 이 시점 이후로도 **부분집합**이다. 보드에 그렇게 적혔다.
