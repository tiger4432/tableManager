# 등록이 «두 문 중 하나» 안에 살았다 — 그리고 안 보이던 반쪽이 «도는 쪽»이었다

> **커밋:** `38b5d8e1` — fix(chain): a rule that runs is in the queue view, whichever door ran it (S-246)
> **일자:** 2026-09-15 15:37
> **레인:** 구현자(서버) — 큐 순서 S-249 → S-242 → S-240 → S-245 → **S-246** → S-247 → 착지 → 보고 `7bb0b121` → 총괄 닫힘 `6226bed0`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **12** · 변이 **9 «전부» 빨강** · 등록부·맵퍼 호출·builtin·뒤따르기·재생 모집단 **559 passed** · `--collect-only` **6,701** 에러 0 (구현자 보고). 총괄 확인 「활동·맵퍼 호출 모집단 134 passed · 부팅 오류 0 · 체인 17 · 재기동 PID 39180」(`6226bed0`).

## ① 왜 — 소유자 「체인 대기열에서 안 뜨고 돌고 있었네」

```
activity.registry 의 start · record_outcome · finish   셋 다 mapper_call.execute_custom_mapper «안»에 적혀 있었다 — «파일 맵퍼»가 지나는 문
builtins.run_builtin                                  셋 중 «아무것도» 안 했다 — builtin:join_into · builtin:join · builtin:auto_confirm 의 문
=> builtin 종류는 «도는 목록 없이» 돌았다. GET /admin/chain/queue 를 보던 운영자는 «노는 체인»이 일하는 것을 봤다
```
⛔ **나머지 절반이 «빈 목록보다 나쁘다».** 로더는 선언된 규칙을 전부 `never_evaluated` 로 «씨 뿌린다» — 부재가 「옛 서버」 «하나»만 뜻하게 하려고. 그래서 천 번을 돈 builtin 이 프로세스가 사는 내내 「아직 평가 안 됨」이라 답했다. 틀린 값은 «답처럼» 읽히고, 부재는 적어도 «구멍»으로 읽힌다.

📌 「같은 기능에 두 경로」의 한 판 — 다만 이번엔 «갈라진» 게 아니라 한쪽이 «비어» 있었다.

## ② 변경 — 등록 «하나»가 등록부 «자기 모듈»에 살고, 두 문이 그것을 지난다

```python
# server/chain/activity.py
@contextlib.contextmanager
def running(rule, mapper, target_table, rows_in, no_rows_reason=NO_ROWS_REASON):
    entry = _Run()
    token = registry.start(rule, mapper, target_table, rows_in)
    try:
        yield entry
    except Exception as error:
        registry.record_outcome(rule, RULE_OUTCOME_FAILED, "%s: %s" % (type(error).__name__, error)); raise
    else:
        if entry.rows_out is not None:                     # «보고받았을 때만». 안 셌다 ≠ 0 이었다
            registry.record_outcome(rule, RAN_CHANGED if entry.rows_out else RAN_UNCHANGED,
                                    None if entry.rows_out else no_rows_reason)
    finally:
        registry.finish(token)                             # 던진 런이 «항목을 남기는» 바로 그 경우를 위해 finally
```
```python
# server/chain/builtins.py  run_builtin()
fn = BUILTIN_KINDS.get(kind)   # 모르는 종류의 거절은 등록 «바깥» — 돈 적 없는 규칙의 항목은 거짓 문장
...
with activity.running(name, kind, target_table, _rows_handed(kwargs), no_rows_reason="the rule wrote no rows") as run:
    result = fn(db, rule, **kwargs)
    written = (result or {}).get("written") if isinstance(result, dict) else None
    if written is not None:
        run.produced(int(written))
    return result
```
`mapper_call.execute_custom_mapper` 의 start/outcome/finish 세 손이 «지워지고» 같은 `activity.running(...)` 을 지난다. 어느 문에도 두지 않은 이유: 한쪽에 두면 다른 문이 «그 문을 import» 하게 된다.
```
행 수를 «안 보고하면»   결과를 «안 건드린다» — 「안 셌다」와 「0 이었다」는 다른 사실이고 이 등록부는 그 둘이 뒤섞여서 생겼다
문구                 builtin 쪽은 「the rule wrote no rows」 — 「the mapper produced no rows」가 아니다. builtin: 종류는 맵퍼가 아니다
_rows_handed         트리거 두 팔(row_ids · key_values)이 이름이 다르다 — 둘 다 읽는다
```

## ③ 한 종류는 행 수를 «아예 안 내고» 있었고, 그것은 «이미 보이고» 있었다

```
join_into.run · materialize_rows   written 으로 답한다
_run_auto_confirm                  confirmed «만» — 그래서 S-249 ⓔ 가 넣은 뒤따르기 줄이 «착지한 날부터» auto-confirm 에 written=None 을 찍고 있었다
```
```python
return {"written": confirmed, "confirmed": confirmed, "refused": refused, ...}   # 이름을 «바꾸지» 않고 수를 «더한다»
```

## ④ 시험의 한 판정 — 「항목이 «있었다»」는 안에서 단언한다

「런 «중»에 항목이 있다」는 종류 «안에서» 단언한다 — 「끝난 뒤에 있었다」는 «다른 주장»이고 쓸모가 없다(finally 가 지운 뒤라). 그리고 두 문이 «같은 등록»을 지난다는 것과, 파일 맵퍼 문이 «자기 등록»을 «안 남겼다»는 것(변이 9번째)을 따로 단언한다.

## ⑤ 아키텍처 영향

- 「도는 규칙」의 등록은 «한 자리»(`activity.running`)이고, 문이 둘이든 셋이든 그 자리를 지난다. 새 문이 생기면 «그 자리를 안 지나는 것»이 같은 모양으로 다시 깨질 곳이다.
- 규칙 결과 어휘(`never_evaluated` · `ran:changed` · `ran:unchanged` · `failed`)가 builtin 종류에도 «채워진다».
- builtin 결과 dict 는 `written` 을 «공통 이름»으로 든다.

## ⑥ 그때 남아 있던 것

- **채점한 것은 «등록»이지 «라우트»가 아니다.** `/admin/chain/queue` 가 이 항목을 «그리는지»는 그 라우트의 시험이고, 그 시험이 읽는 것이 여기서 단언한 그 `snapshot()` 이다.
- **항목은 «프로세스마다»다.** 체인 워커를 따로 띄우면 API 프로세스는 «자기 빈 등록부»를 내놓는다 — `attached: false` 가 이미 그것을 말한다. 「다른 프로세스의 같은 판정기는 다른 판정기」 그대로.
- 구현자의 지난 세 라운드가 주석에 `\U0001f534` 를 «글자 그대로» 남겼다 — 이 커밋 범위 안의 넷은 고쳤고, `chain/ingestion_worker.py` 의 «다섯»은 `aa77a2fe`(패키지 재편) 것이라 «안 섞고» 그대로 남아 있었다.
- 총괄 재기동 PID 39180 은 부팅 확인(오류 0 · 체인 17)이다. builtin 종류가 대기열에 «뜨는 것»을 화면에서 본 기록은 이 시점에 없다.
- 이 채널의 미답 «없음». 다음은 S-247 — 오늘 큐의 마지막.

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 S-249 ⓔ 의 뒤따르기 줄(`written=None` 이 찍히던 자리): `20260915_125527_the_follow_up_lap_became_a_hop_and_one_cause_gets_one_helping.md` §③ · 「같은 질문에 문 둘」의 앞선 판: `20260910_162700_two_doors_for_one_question_and_two_accidents_that_came_from_tidying.md`.
