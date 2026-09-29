# 칸이 다 찬 행만 복사하는 체인

> **대상:** 체인 선언을 쓰는 운영자 | **최종 검증:** 2026-09-29 (코드 대조 — `chain_bindings.REQUIRE_KEY` · `rule_run` 의 넘기기 거름 · `ingestion_worker.wake_columns` · `_rule_accepts_event`) | **관련:** [config/chain_rules.md](./config/chain_rules.md) §5 `require` · `allow_chain_trigger` 행

예: `dt_log` 를 inventory 조인으로 채운 뒤, **정답맵에 필요한 칸이 전부 찬 행만** 정답맵으로 복사한다.
적는 칸은 둘이다 — 복사 규칙의 `require`(무엇이 다 차야 하나)와 `allow_chain_trigger`(조인이 채운 값에 깨어나기).

---

## 1. 선언 둘

**① 키 채우기 — 조인이 `dt_log` 의 빈 칸을 채운다**

```json
{
  "name": "inventory_to_dt_log",
  "on": { "table": "dt_inventory" },
  "derive": {
    "kind": "join",
    "join": {
      "on":   [ { "left": "dt_job", "right": "dt_job" } ],
      "take": [ "<채울 칸>", "..." ]
    }
  },
  "into": { "table": "dt_log" }
}
```

**② 복사 — `dt_log` 에서 정답맵으로, 다 찬 행만**

지금 쓰는 정답맵 맵퍼 규칙에 두 칸을 더한다.

```json
{
  "name": "dt_log_to_answer_map",
  "trigger_table": "dt_log",
  "target_table": "<정답맵 표>",
  "mapper_module": "<정답맵 맵퍼 모듈>",
  "mapper_function": "<함수>",
  "is_batch": true,
  "require": [ "<다 차야 하는 칸>", "..." ],
  "allow_chain_trigger": true
}
```

통합 선언(`on` · `derive` · `into`)으로 쓰면 `require` 는 `on.require` 에 적는다.

| 칸 | 뜻 | 안 적으면 |
|---|---|---|
| `require` | 이 칸이 **모두 찬** `dt_log` 행만 맵퍼에 넘긴다 | 모든 행이 넘어간다 |
| `allow_chain_trigger: true` | 조인이 `dt_log` 에 쓴 값에도 깨어난다 | 사람 · 파일 · 수집기가 바꾼 행에만 깨어난다 — 「왜 안 도나」의 가장 흔한 답 |

---

## 2. 도는 순서

1. `dt_log` 에 행이 들어온다. `require` 칸이 비어 있으면 복사 규칙은 그 행을 **넘기지 않는다**.
2. 조인이 `dt_log` 에 키를 채운다 — 새 `dt_log` 행이 들어올 때(조인의 `:target` 짝), 또는 `dt_inventory` 값이 바뀔 때.
3. 그 쓰기에 복사 규칙이 다시 깨어난다. 이번엔 다 찼으므로 정답맵에 복사된다.

`require` 칸이 나중에 채워지는 것은 그 규칙의 칸이 바뀐 것으로 친다 — `trigger_columns` 를 적었어도 `require` 칸은 자동으로 깨우는 칸에 들어간다.

---

## 3. 로그에서 보는 줄

| 언제 | 줄 |
|---|---|
| 덜 찬 행을 넘기지 않았을 때 | `[Chain] <규칙>: <N> row(s) not handed over - required column(s) empty: <칸>=<건수>, ...` |
| `require` 에 `dt_log` 에 없는 칸을 적었을 때 (로드 거절) | `rule <규칙> requires [<칸>] that 'dt_log' does not have; no row could ever be handed to it. Fix the names or remove the cell.` |
| `require` 가 칸 이름 목록이 아닐 때 (로드 거절) | `require must be a list of column names, got <값>` |

---

## 4. 알아 둘 것

- **「빈 칸」** = 값 없음 · 빈 문자열 · 공백만 있는 문자열. 판정은 한 함수(`crud.is_blank_value`)다.
- **한 묶음이 전부 걸러지면 맵퍼를 부르지 않는다.** 덜 찬 행 때문에 맵퍼가 에러 나는 길이 막힌다.
- **이미 복사된 행은 지우지 않는다.** 나중에 `dt_log` 의 그 칸이 다시 비어도 정답맵 행은 남는다.
- **규칙은 자기가 쓴 것에 깨어나지 않는다**(09-28). 복사 규칙이 정답맵에 쓴 것이 복사 규칙을 다시 부르지 않는다.
- 파일을 어드민 밖에서 직접 고쳤으면 **Reload Configs & Code** 를 눌러야 반영된다(09-29 부터 서버가 규칙을 바뀔 때만 읽는다).

## 5. 켜기 전에

- 운영 체인 워커가 09-29 이후 코드로 재기동돼 있어야 한다 — 자기 쓰기에 안 깨어나기(09-28) · 실패 묶음을 쪼개지 않기(09-29).
- 트리거 표와 타깃 표가 **같은** 규칙에는 `allow_chain_trigger` 를 켜지 않는다.
- 정답맵 맵퍼가 정답맵 키를 `dt_log` 의 어느 칸에서 가져오는지는 **맵퍼 규칙 자신의 칸**이 정한다 — `require` 에는 그 칸들을 빠짐없이 적는다.
