# 소급이 좌석을 지나게 됐고, 접힘은 «두 문 중 하나»만 덮었다

> **커밋:** `edecf1a0`(S-279 ㉡-2ⓐ · 판정 421) — 구현자
> **일자:** 2026-09-16 (밤 19:57)
> **레인:** 구현자. 반증은 응용(Q-5, `2b8f3904`) · 판정 424 는 총괄(`cfa50299`, 20:4x)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 🔴 먼저 — 커밋 제목이 «절반만» 참이다

커밋 제목: 「retroactive runs a rule through the seat, **and its writes collapse like the other
two doors**」. 뒷절은 **빌트인 문에 대해서만 참이다.**

```
실측 (이 항목을 쓰며 blob 에서 직접 잼, 2026-09-16)
   git grep -n outbox_mode -- server/chain/replay.py
     -> 히트 «하나». 그리고 그것은 :497 의 «주석»이다. 호출이 아니다
   접힘이 사는 자리   server/chain/rule_run.py:110  `with outbox_mode(COLLAPSED):`
                    -> :90 `if kind is not None:` «안»이다. 빌트인 갈래 «전용»
   파일 맵퍼가 쓰는 길 replay.py:535 `rule_run.run_rule(db, rule, payloads=payloads)`  (제안만 받음)
                    -> :609 · :613 · :616 `_apply_replay_batch(...)`
                    -> :707 `def _apply_replay_batch(...)`   ← 감싸는 def
                    -> :737 `crud.apply_batch_updates(db, table_name, batch)`   ← 실제 쓰기
                    이 경로 어디에도 outbox_mode 범위가 «없다»
```
🔴 **그래서 파일 맵퍼 규칙을 소급으로 돌리면 오늘도 «행마다 아웃박스 이벤트 하나»가 나간다.**
판정 424(채널 `task/IMPLEMENTER_ORDERS.md`, 20:4x)가 이것을 기록한다.

📌 이 항목이 커밋 제목을 그대로 옮기지 않는 이유가 이것이다 — 옮겼으면 **거짓을 다시 발행**한다.

## 그리고 «좌석 자신»이 그 반대를 적어 두었다

`rule_run.py:101-103` 의 주석:

```
# 🔴 COLLAPSED, BECAUSE A BUILTIN WRITES FOR ITSELF. A file mapper's rows go out
# through the caller's `apply_batch_updates`, which is already inside an
# `outbox_mode(COLLAPSED)` scope; …
```
🔴 **그 문장은 방금 배선한 호출자(replay)에 대해 «거짓»이다.** 그룹 경로와 후속 랩에 대해서는
참이고, 그래서 이 주석이 두 호출자에서 참이고 셋째에서 거짓이 됐다 — 그리고 «오류가 안 난다».

📌 **부류: 「주석은 «의도»의 증거이지 «동작»의 증거가 아니다」**, 그리고 그 위에 한 겹 더 —
   **한 문장이 세 호출자를 «한꺼번에» 주장하면, 그중 하나가 어긋나도 그 문장은 그대로 서 있다.**

## 그래서 «실제로» 착지한 것

```
✅ 문의 이름이 replay 에서 사라졌다
   :375  builtin_kind = rule_run.builtin_kind(rule)     <- `BUILTIN_KINDS` 비교가 여기서 «없어졌다»
   :504  outcome = rule_run.run_rule(db, rule, row_ids=page_ids)        (빌트인 페이지)
   :535  results = [rule_run.run_rule(db, rule, payloads=payloads)]     (맵퍼 페이지)
   삭제된 것: `from chain.mapper_call import execute_custom_mapper` · `is_batch` 지역변수 ·
             `module_name`/`func_name` 의 지역 읽기 · `builtins` 의 지역 import
✅ 빌트인 소급의 이벤트가 접혔다
   페이지 하나가 N 행을 써도 아웃박스 이벤트 «하나». 게이트가 5행 배필로 5 == 1 을 빨갛게 보였다
✅ is_batch 팬아웃이 문과 «같이» 좌석으로 갔다
   「이 규칙을 이 페이지에 돌려라」의 두 철자(여기 · 워커의 그룹 단계)가 이제 한 호출이라 갈릴 수 없다
```
🔵 부수 효과 하나가 «좋은» 쪽이다: 규칙이 맵퍼 이름을 «데코레이터 레지스트리»에만 든 경우
(`mapper` 한 칸, S-188 ⓓ) 종전에는 문 앞에 `(None, None)` 쌍으로 도착했다. 좌석이 규칙에서
직접 읽으므로 그 길이 닫혔다.

## 🔴 게이트의 «대리»가 빨개졌는데 그 «성질»은 안 깨졌다

```
S-214 / 판정 370  「공용 프리미티브는 한 호출자의 집에 살지 않는다」
대리였던 것       replay 안에 리터럴 `from chain.mapper_call import execute_custom_mapper` 가 «있다»
오늘             replay 는 실행자에 «어느 문으로도» 닿지 않는다 -> 대리가 빨개진다.
                 성질은 «더 강하게» 만족된다 — 대리가 표현할 수 없던 방식으로
수리             단언 둘을 «성질»로 다시 썼다: 실행자를 부르는 «모든» 모듈을 AST 로 계산하고,
                 각자 «자기 집»에서 import 하며 다른 호출자를 거치지 않는지 잰다
                 그 모집단은 오늘 `chain/ingestion_worker.py` · `chain/rule_run.py` 둘이고,
                 ㉡-2ⓑ 에서 «시험을 고치지 않고» 하나 더 준다
```
📌 **부류: 「대리가 빨개졌을 때 고칠 것은 대리이지 코드가 아닐 수 있다」.** 판별식은 「성질이
   깨졌나, 철자가 바뀌었나」이고, 이 자리에서는 성질이 «더 좋아졌다».

## ⚠️ PG 스위트가 12 failed / 13 errors 를 냈고, 그것은 이 변경이 «아니었다»

커밋이 그것을 스스로 적었다: 배경 실행이 전경 실행과 겹쳤고, `PG_TEST_SCHEMA` 는 xdist 아래서만
접미사를 받으므로 **두 동시 실행이 서로의 스크래치 스키마를 지운다**(`InvalidSchemaName`, 그리고
수가 실행마다 «움직였다»). 혼자 돌리면 91 / 0.

🔴 기록해 둘 값어치가 있는 이유: 그 실패는 **평범한 스위트가 «볼 수 없는 바로 그 절반»에서 회귀처럼
보였다.** 수가 실행마다 움직이는 것이 「내 실행 환경」과 「코드」를 가른 유일한 신호였다.

## 그때 남아 있던 것

```
파일 맵퍼 소급    행마다 이벤트 하나. 접힘이 «안 덮었다» (판정 424)
좌석의 주석      :101-103 이 replay 에 대해 거짓인 채로 서 있다
㉡-2ⓑ           그룹 경로의 호출 자리 «둘». 파트 1 이 총괄 워크트리에서 같은 파일을 들고 있어 대기
                ⚠️ 그리고 그 파트 1 은 «취소됐다» — 전제가 거짓이었다 (`e85aa29d`, 19:56)
제품의 소급 경로  이 상자에서 «안 돌렸다». 총괄이 재기동한 상자에서 그 확인을 예약했다
스위트          지목 모집단 902 passed / 9 skipped / 0 failed · run_pg_tests.py 91 / 0 ·
                collect-only 6,834, 0 errors — 커밋이 적은 수이고, 이 항목은 다시 안 돌렸다
```
📎 오늘 밤의 판정 420·421·424 는 한 실이다. 총괄의 한 화면 정리는 `6bea68bd`(20:07) 에 있다.
