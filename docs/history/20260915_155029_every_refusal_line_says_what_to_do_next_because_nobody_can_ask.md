# 거절 줄마다 «다음에 무엇을 하나»를 싣는다 — 물어볼 데가 없기 때문에, 그리고 같은 낱말에 수리가 «정반대»인 자리가 있기 때문에

> **커밋:** `3aab7173` — fix(logs): every refusal line says what to do next, because nobody can ask (S-247)
> **일자:** 2026-09-15 15:50
> **레인:** 구현자(서버) — 큐 순서 S-249 → S-242 → S-240 → S-245 → S-246 → **S-247**(마지막) → 착지 → 보고 `b5587884` → 총괄 닫힘 `b1db471a`(「오늘 라운드 S-237~S-249 · 판정 396~404 닫힘」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **15** · 기존 **2 변경**(지우지 않고 «저자에게 묻게») · 변이 **9 «전부» 빨강** · 네 자리 모집단 **222 passed** · `--collect-only` **6,716** 에러 0 (구현자 보고). 총괄 확인 「112 passed · 부팅 오류 0 · 체인 17 · 재기동 PID 45380」(`b1db471a`).

## ① 왜 — 소유자의 두 문장이 «하나의 요구»였다

> 「난 이 에러를 이해할 수가 없다, 조치를 뭘 해야 하는지 안 알려줌」 · 같은 날 「운영은 보안 땜에 못 붙여」

운영 로그는 밖으로 못 나온다 → 붙여 넣고 물어볼 수 없다 → **무엇이 일어났는지만 말하는 줄은 미완성이다.** 뒤에 더 물을 수 있는 독자가 있을 때만 완성인 줄인데, 여기엔 그 독자가 없다.

⛔ 그리고 조치 없는 줄은 이 제품에서 «중립이 아니다». 「중복 키」로 읽히는 줄이 «넷»인데 그중 둘의 수리가 «정반대»다:
```
조인 키가 «신원보다 좁다»   -> 고칠 것은 «선언»  (데이터를 접으면 사실이 사라진다)
진짜 중복이다               -> 고칠 것은 «데이터» (선언을 넓히면 중복이 남는다)
```
조치 없는 줄은 운영자를 «반반의 확률로» 틀린 수리로 보내고, 지난주에 통한 수리가 이번 주에 정확히 틀린 쪽이다. RUN.md §2-bis 는 «바로 이 넷»의 해독표였다 — 줄이 스스로 못 답해서 둔 것.

## ② 변경 — 저자 «하나» `server/operator_line.py`: 모양과 «닫힌 행동 어휘»

```python
# server/operator_line.py  — stdlib 만 import. 네 자리가 세 패키지(chain · database · virtual_join)에 살고 어느 쪽도 남을 읽으면 안 된다
MAX_SAMPLES = 3                                  # 넷째부터는 «세는 것»이 답이다. 수천 건 나열은 진단이 아니라 덤프

def fold_the_data(table, columns) -> str:        # 진짜 중복 — 그 표의 행을 «합쳐라»
def widen_the_key(where_declared, what_to_add):  # 키가 신원보다 좁다 — 선언을 넓혀라. 「데이터를 합치면 사실이 사라집니다」를 «같이» 말한다
def fill_or_declare_null(table, columns):        # 비어 있다 — 중복이 아니라 «부재»
def restart_to_apply():                          # 제품이 «스스로» 세운다. 손 DDL 없음
def nothing_to_do():                             # 「없음」도 행동이다 — 모르면 운영자는 «무엇이든» 한다

def line(where, subject, what, action, samples=()) -> str:
    """「다음:」 절이 «없는» 줄은 이 함수가 만들 수 없다."""
    body = "[%s:%s] %s" % (where, subject, what)
    shown = samples_of(samples)                  # ≤3 + 「외 N」 — 셋만 보이고 수를 안 말하면 「셋뿐」으로 읽힌다
    if shown: body += " (표본: %s)" % shown
    return "%s → 다음: %s" % (body, action)
```
```
행동이 «함수»인 이유   행동마다 «채워야 할 이름»이 다르다. 문자열 상수로 두면 부르는 자리가 포맷을 짜고, 그 순간 저자가 넷이 된다
접두 대괄호           «검색어»다. 운영자가 로그에서 이 줄을 찾는 «유일한» 방법이고, 자리마다 다르면 못 찾는다
_names               ['slot'] 같은 repr 이 운영자에게 가지 않는다 — 대괄호부터 해독해야 하는 문장은 문장이 아니다
```

## ③ 네 자리 — 부르는 자리는 행동을 «고르기만» 한다

```
[join_into:<규칙>]           왼쪽 행이 오른쪽 «둘 이상»과 맞음 -> fold_the_data(오른쪽 표, 오른쪽 키)        데이터
[VirtualJoinUnique:<규칙>]   같은 오른쪽 키가 «한 배치 안»에 / «이미 저장된» 행과 -> fold_the_data           데이터 (두 반쪽)
[BKConflict:<표>]            업무키가 다시 읽어도 충돌 -> widen_the_key("table_config 의 '<표>' 의 composite_key_source", "두 행을 가르는 컬럼")   선언 — «정반대»
[VirtualJoinIndex:<표>]      인덱스 없음 / INVALID -> restart_to_apply · 키 비어 있음 -> fill_or_declare_null · 진짜 중복 목록 -> 마지막 줄에 fold_the_data
```
```python
# server/database/crud.py  — BK 충돌. 위 두 줄과 «같은 낱말»로 읽히는데 수리가 반대라, 코드 주석이 그것을 «먼저» 적는다
logger.error("%s", operator_line.line("BKConflict", table_name,
    "업무키가 다시 읽은 뒤에도 계속 충돌해 이 배치(%s 행, tx %s)를 «거절»했습니다 — 경합이 아니라 «같은 신원»이 둘입니다" % (...),
    operator_line.widen_the_key("table_config 의 '%s' 의 `composite_key_source`" % table_name, "두 행을 가르는 컬럼")))
```
마지막 자리(유일 인덱스 보고 네 상태)는 «이미 산문으로» 조치를 말하고 있었다 — 이제 «같은 모양»이라 운영자가 검색어 하나로 넷을 찾는다.

📎 **`virtual_join/refusal.py` 와 «다른 것»이고 그 차이가 발견이다.** 그 모듈은 «화면»이 읽는 문장(설정 보고서 · verify 라우트)의 정본이다. 화면에는 저자가 있었고 «로그에는 없었다» — 그런데 운영에 실제로 있는 채널은 로그 쪽이다.

## ④ 기존 시험 «둘»이 옛 문구를 박고 있었고, 지우지 않고 «저자에게 묻게» 고쳤다

```
test_business_key_conflict_retry              태그 「BK Conflict Unresolved」 «만» 단언 -> 이제 [BKConflict:dt_log] 줄 «하나»에 「→ 다음: 」 과 widen_the_key(...) 그대로가 들어 있는지
test_the_product_sets_up_its_own_unique_key   「제품이 만듭니다」를 «베껴» 둠 -> 이제 startswith("[VirtualJoinIndex:dt_log] ") 와 endswith(restart_to_apply())
```
📌 부류: **「하니스가 문구를 베끼면 그 문구의 둘째 저자가 된다」** — 운영자가 행동하는 것이 하나도 안 바뀐 재작성에 빨개진다.

## ⑤ RUN.md §2-bis — 해독표가 «모양과 앞머리 넷»으로 갈렸다

지시대로 표를 지우고 줄의 모양 `[<자리>:<규칙 또는 표>] 무엇이 일어났나 (표본: ≤3) → 다음: <무엇을 하나>` 와 앞머리 넷의 표로 바꿨다. 「`double precision` 은 `ddd5b3ba` 부터 안 난다」 행(S-245)은 🪦 로 남았다.

⚠️ **그 과정에서 RUN.md 가 «0 바이트»가 됐다.** 패치 스크립트가 `open(p, "w")` 로 연 «뒤»에 인코딩 예외가 났고, 그 순간 파일은 이미 잘려 있었다. `git checkout HEAD -- RUN.md` 로 복구하고 «임시 파일에 통째로 만든 뒤 옮기는» 방식으로 다시 했다. 커밋 «전»에 잡혔고, 공유 트리에 0 바이트로 있던 시간은 한 자리 분이다.
📌 부류: **「쓰기 모드로 여는 순간 파일은 이미 사라졌다」**(2026-08-23) — 같은 함정에 같은 날 한 번 더.

## ⑥ 아키텍처 영향

- 로그의 거절·경고 줄에 «저자»가 생겼다(`operator_line`) — 화면 쪽 저자(`virtual_join/refusal.py`)와 «나란히», 서로 import 하지 않는다.
- 행동 어휘가 «닫혀» 있다(다섯). 새 행동은 이 모듈에 «함수 하나»를 더하는 것이고, 그러면 그 행동이 «무엇을 말해야 하는지»가 한 자리에서 정해진다.
- 운영자가 로그에서 이 줄을 찾는 방법은 `[자리:` 접두 «하나»다.

## ⑦ 그때 남아 있던 것

- **채점한 것은 «렌더된 줄»이다.** 「진짜 PostgreSQL 이 진짜 데이터에서 이 줄을 낸다」는 이 커밋이 증명하지 않는다. 총괄 재기동(PID 45380)이 확인한 것은 「부팅 오류 0 · 체인 17」이다.
- **순서 의존 하나가 «이미 있었다».** `test_chain_key_gate.py::test_the_refusal_count_reaches_another_process_through_the_heartbeat` 가 이 모집단 «뒤»에 돌면 빨갛다 — 구현자가 «자기 변경을 빼고도» 빨간 것을 확인했다(부수 피해가 아니라 기존 순서 의존). 이 시점에 그대로 남아 있다.
- 지시받은 큐(S-249 → S-242 → S-240 → S-245 → S-246 → S-247)를 «끝까지» 돌았고, 구현자는 «정지»(다음 지시 없음). 총괄이 「오늘 라운드(S-237~S-249, 판정 396~404) 닫힘」을 적었다.
- 이 채널의 미답 «없음».

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 소유자 원문(「운영은 보안 땜에 못 붙여」)뿐이다.
📎 「거절이 원인을 안 대면 운영자를 사람에게 보낸다」의 앞선 판: `20260805_120400_a_refusal_that_names_no_cause_sends_the_operator_to_a_person.md` · 화면 쪽 거절 저자의 자리 셋: `20260905_184900_three_carriers_had_no_reader_so_a_refusal_had_a_sentence_and_no_address.md` · 「좁은 키」 게이트와 신원(`composite_key_source`)이 같은 날 아침 먼저 다뤄진 자리: `20260915_100554_a_left_row_with_two_right_answers_is_written_by_neither.md`.
