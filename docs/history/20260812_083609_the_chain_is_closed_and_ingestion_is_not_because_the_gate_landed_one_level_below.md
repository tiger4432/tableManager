# The chain is closed and ingestion is not, because the gate landed one level below

**Date:** 2026-08-12 08:36 · **Domain:** Server (체인 인제션 / 리플레이 / 레이어링 코어) · **Status:** 착지 — `e9fd8a6`

> 🔴 **정정(2026-08-12 08:59, `c315662`)** — 아래 본문이 여러 번 인용하는 **「~170,000」은
> 술어가 반대인 수다.** 그것은 `duplicate_census`의 `surplus`(`dup_rows − groups`,
> **양쪽 다 `WHERE business_key_val IS NOT NULL`**)이고 곧 **키가 «있는데» 중복된** 행의
> 수다 — 키 «없는» 행의 수가 아니다. 키 없는 행의 운영 수는 추적되는 산출물 어디에도 없어
> 바꿔 넣을 수가 없고, `c315662`가 세 파일에서 그 수를 **빼 버렸다** →
> [항목](./20260812_085940_a_number_travelled_into_three_files_under_the_opposite_predicate.md).
> 게이트의 동작·판정·측정은 그 수와 무관하므로 그대로 선다. **본문은 기록이므로 그대로 둔다.**

> ⚠️ **숫자 출처 구분.** 운영 ~170,000행은 **제품 소유자 보고**다. 아래의 다른 실측은
> 전부 **격리 `assy_qa` 스냅샷과 이 워크스테이션**이며 운영 수치가 아니다. 어떤 접속도
> 시작 전에 `current_database() = 'assy_qa'`를 단언했다.

---

## 배경 — 주소를 못 갖는 행은 다음 배송에서 하나 더 생긴다

맵퍼가 행의 신원을 못 정해도 **행은 그냥 나갔다.** 그다음 쓰기 경로는 **설계대로**
행동했고 그것이 문제였다 — 빈 키 컬럼은 아무것도 안 쓴다(`818c9c0`). 그래서 행은
`business_key_val`이 NULL인 채로 착지했다.

**아무것도 그 행을 지목할 수 없다** — 재푸시도, 업서트도, 운영자도. 그러니 같은 데이터의
다음 배송이 **또 하나를 만든다.** 그 표는 닿을 수 없는 행의 인구를 길렀다(2026-08-11
실측, 한 표에 ~170,000). 그런 행 하나가 나중에
`GET /api/maps/alignment/worklist`를 요청 전체 500으로 만들었다(`c4a3159`).

단위 키를 조립하는 네 자리 중 **셋은 이미 손으로 가드를 갖고 있었다** —
`dt_alignment_metadata_mapper`, `core_alignment_mapper`, `dt_inventory_metadata_mapper`.
넷째만 없었다.

**수리는 그것을 넷으로 만드는 것이 아니다.** `server/mappers/*.py`는 설계상 gitignore라
(`*.py.sample`만 배포된다) 맵퍼에 쓴 가드는 **배포에 닿지 않고**, 다음 달에 새로 쓰는
맵퍼는 가드 없이 시작한다.

## 거절이 겨눈 곳보다 한 층 아래에 도착했다

지시서는 「단일 깔때기를 찾아 거기에 게이트를 놓고, 중앙 게이트가 틀린 것으로 드러나면
멈추고 보고하라」였다. 레인은 **`crud.apply_batch_updates`가 진짜 단일 깔때기이고 바로
그래서 거기 놓으면 안 된다**는 것을 찾았다.

`818c9c0`이 **키 없는 행을 수동 그리드 작업이 만드는 정당한 모양으로, NULL을 그 철자로**
이미 판정해 두었기 때문이다. 거기서 거절하면 **사용자 자신의 타이핑을 거절**하게 된다.

그리고 그것을 **논증이 아니라 측정으로** 세웠다 — 워처 자신의 `_send_to_upsert`에 빈 키를
먹여도 **7행이 그대로 쓰이고 그중 하나는 키가 없으며 게이트 계수기는 비어 있다.**

**그래서 체인은 닫혔고 인제션은 안 닫혔다.** 운영의 잉여 ~170,000행이 체인이 아니라
**인제션**으로 들어온 것이라면 이 변경은 그 증식을 막지 못한다. 그것이 열린 항목이고,
**이 커밋이 닫은 것보다 크다.**

## 깔때기는 두 자리, 게이트는 하나

```python
kept, key_gate_report = chain_key_gate.screen(
    target_table, batch_data.updates,
    rule_names=rules_by_target.get(target_table, ()),
    transaction_id=chain_tx_id)
```

`chain_ingestion_worker.process_chain_transaction_group`의 `write_batches` 루프 —
행별 맵퍼 반환, 배치 맵퍼 반환, `map_metadata_updates`, `replace_map` 스코프 배치가
전부 여기로 모인다. 그리고 `chain_replay._apply_replay_batch`.

**리플레이가 일부러 들어갔다.** 리플레이는 같은 맵퍼를 표 전체에 다시 돌리는 경로이고,
인시던트의 행을 **대량으로 만들어 낼 수 있는 유일한 길**이다. 발화만 막고 리플레이를 열어
두면 문을 닫고 창문을 남기는 것이 된다.

## 같아야 했던 두 술어

`crud.unfilled_key_columns`는 「키가 만들어질 것인가」를 묻고
`assemble_composite_business_key`는 「내가 키를 만들어도 되는가」를 묻는다. **이 둘이 같은
질문이 아니면 게이트가 쓰기 경로라면 키를 붙였을 행을 거절한다.**

```python
def _unfilled_composite_parts(composite_src, updates) -> list:
    """Which `composite_key_source` columns this payload does not supply a value for.

    Extracted so that the assembler above and `unfilled_key_columns` below cannot drift
    apart: one asks "may I build a key?" and the other asks "will a key be buildable?",
    and those must be THE SAME QUESTION ...
    """
    updates = updates or {}
    return [col for col in composite_src
            if col not in updates or is_blank_value(updates.get(col))]
```

조합기가 갖고 있던 **열려 있는 all-filled 검사 둘**이 사라지고 이 하나로 접혔다.
공백 판정은 `is_blank_value`이고, 그것이 대체한 `clean_str_value(x) == ""`와 동치라는
것은 `contracts/blank_predicate`가 고정한다.

그리고 술어는 **읽기 전용이어야 한다.**

```python
🔴 READ-ONLY. It must never call `assemble_composite_business_key`, whose two side
effects include writing the key back into `updates[key_col]` - and doing that before
`derive_replace_map_scope` runs would narrow a whole-map purge down to a single die
```

빈 리스트가 **「받아들인다」**를 뜻하고, 그 결론에 이르는 이유가 셋인데 **셋 다 받아들여야
한다** — 항목이 이미 신원을 갖고 있거나, 표가 업무키를 아예 선언하지 않았거나, 표가 단순
키를 선언했고 페이로드가 그 값을 실었거나. 비어 있지 않은 결과는 **컬럼 이름을 댄다.**
운영자가 받는 문장이 「어떤 키가 없다」가 아니라 「이 컬럼들이 비어 있었다」인 것이 요점이다.

## 게이트가 배치를 비우면 배치는 안 쓴다

```python
if not kept:
    # 🔴 EVERY row was refused. Writing the batch anyway would be
    # actively destructive on a `replace_map`: the purge (or the
    # scope diff) removes the map's rows and nothing replaces them.
    # A DECLARED empty replace - `scope` with an empty payload - is
    # still honoured, because this arm is only reached when the gate
    # is what emptied the list.
```

**선언된 빈 replace는 여전히 존중된다.** 이 갈래는 **게이트가 비운 경우에만** 타므로
둘이 구별된다.

## 거절은 시끄럽다

조용한 스킵은 나쁜 쓰기와 같은 결함이다 — 하루가 통째로 든 인시던트가 그 문장이다.
모든 거절이 `(table, column)`으로 프로세스 수명 동안 세어지고, 체인 워커의 하트비트
note로 요약된다. `/health`가 `crud.undeclared_column_drops()`를 위해 **이미 읽고 있는
같은 크로스프로세스 채널**이라 새 채널을 만들지 않았다.

```python
def _worker_note():
    """Everything this process needs to say through the heartbeat, or `None`. ...
    They are different questions with different fixes (declare a column / fix the mapper
    or its source), so they are never summed into one number - they are joined and both
    named."""
    parts = [p for p in (_undeclared_drop_note(), chain_key_gate.note()) if p]
    return " | ".join(parts) or None
```

건강한 워커에서 `None`인 것이 하중을 진다 — **깨끗한 배포의 하트비트가 바이트 단위로
지금과 같게 유지된다.** 로그도 1·10·100…번째에서만 알린다.

같은 커밋에서 워커가 `94954cb`가 만든 `drop_report`를 **받기 시작했다.** 게이트가 무엇을
거절하는가와 **쓰기가 무엇을 버리는가**는 다른 질문이고, 후자에는 이미 채널이 있었다.

## 살아남은 변이 M9

변이 10개, 10개 사망. 그러나 **M9(거절에서 규칙 귀속을 제거)가 1차에서 살아남았다.**

이유가 기록할 값어치다 — **모든 테스트가 게이트의 «리포트»를 읽었고 «운영자의 채널»을
아무도 읽지 않았다.** 아무것도 지목하지 않는 거절이 그대로 통과했다. 워커를 실제로 돌려
로그가 규칙 이름을 대는지 단언하는 테스트를 추가해 잡았다.

규칙 이름은 **규칙이 자기 대상에 묶이는 그 한 자리**에서 수집된다. `table_updates`가 여러
규칙을 한 대상에 합치므로 **나중에는 귀속을 복원할 수 없다.**

```python
# [ChainKeyGate] target_table -> the rule names that contributed to it. Collected
# here, at the ONE place a rule is bound to its target ... `table_updates` aggregates
# several rules onto one target, so this cannot be recovered after the fact.
rules_by_target = defaultdict(set)
```

⚠️ **변이 하나는 테스트가 아니라 변이 쪽 잘못이었다.** 초기 M3b가 항상 빈 반환을
`return [] or [...]`로 적었는데 파이썬에서 이것은 no-op이라 **아무 일도 안 해서
「살아남았다」.** 고쳐서 다시 채점했다. **부실한 변이와 견고한 테스트는 밖에서 똑같이
보인다.**

## 실부하에서 거절 0건

운영 `chain_rules.json`의 활성 규칙 전부를 `assy_qa` 스냅샷 위에서 `chain_replay`로
돌리되 `apply_batch_updates`를 계수기로 바꿔서 **실제 게이트가 실제 맵퍼 출력을 실제
규모로 보되 아무것도 안 쓰게** 했다.

| | 값 |
|---|---|
| 스캔 | `dt_log` 116,134행 등 |
| 맵퍼 항목 | **560** |
| 쓰기에 도달 | **560** |
| **거절** | **0** |

**도는 인제션을 거절 소음으로 바꾸지 않았다**는 증거다.

## 검증 — 이름으로 보고된 실패

15개 파일 이웃(243 테스트, crud 쓰기 경로·복합키·체인 워커·리플레이·맵메타·드롭 공시).

| | 결과 |
|---|---|
| 이전(HEAD 바이트) | **1 failed / 218 passed** — `test_inserting_new_rows_still_probes_once_per_row` |
| 이후 | **1 failed / 242 passed** — **같은 테스트**, 연속 3회 |
| 새 실패 | **없음** |

진짜 파손을 하나 찾아 고쳤다 — `test_chain_created_logs_truncation.py`의
`apply_batch_updates` 더블이 `drop_report`를 안 받았다. 더블에 진짜 시그니처를 주는
것으로 고쳤다. **시그니처를 속이는 더블은 전달 버그를 감춘다**는 `94954cb`의 판정 그대로다.

산 경로 셋도 탔다 — 체인 유발(게이트 켜기 전 `dt_map` +3행 중 **키 없는 행 1개**,
켠 뒤 +2행 **키 없음 0**, 거절 1건이 `dt_map.dt_job`과 규칙 이름을 댐) · 인제션 유발
(**변화 없음**, 위 참조) · 그리드 셀 편집(`PUT /tables/dt_map/data/updates`, 200,
`ROW_UPDATE` 감사 1건, 업무키 보존).

⚠️ **한 라운드가 오염된 측정을 냈고 그것은 이 변경에 대한 사실이 아니다.** 레인의
before/after 하네스가 파일 바이트를 스냅샷·교체·복원하는 방식인데, 실행 도중 옆 레인이
`crud.py`를 썼다. 그 실행이 `NameError: name 'audit_changeset' is not defined`로
**80건 넘게 빨개졌다.** 트리는 그 뒤 수렴했고(양쪽 hunk가 다 있고 파일이 컴파일되며
이웃이 3회 연속 초록) 잃은 것은 없어 보이지만, **그 80건 실행을 이 변경의 사실로 읽으면
안 된다.** 레인은 그 뒤 공유 파일에 하네스를 쓰지 않았다.

## 아키텍처 영향

- **가드가 추적되는 자리로 옮겨 왔다.** 배포되지 않는 파일(gitignore된 맵퍼)에 규칙을
  두는 것과 배포되는 모듈에 두는 것은 다른 물건이다. 이 커밋은 후자를 골랐고
  **맵퍼는 한 줄도 안 건드렸다.**
- **게이트가 `chain_bindings`에 있지 않은 이유**도 파일에 적혀 있다 — 그쪽은 선언에서
  컬럼 **이름**을 푸는 순수 모듈이고, 이쪽은 **행**을 판정하며 프로세스 수명 계수기를
  갖는다. 같은 계열, 다른 수명.
- 리플레이 통계에 `unkeyed_rows_refused`·`unkeyed_key_columns`가 붙었고
  `skipped_blank_cells`와 **합쳐지지 않는다** — 스킵된 «셀»은 자기 행을 쓰고, 거절된
  «행»은 아무것도 안 쓴다.
- `crud.py`가 마감 시점에 **저자를 둘 갖고 있었다.** hunk를 옛 파일 줄 범위로 갈라
  이 커밋은 키 게이트의 둘만 실었고, 감사 레인의 넷은 HEAD로 되돌려 패치로 보관했다 —
  그 레인이 반쯤 병합된 베이스가 아니라 깨끗한 베이스에서 다시 시작하도록. 게이트의
  테스트 29개는 **분리된 트리에서 다시 돌렸고**, 레인이 측정했던 트리에서 돌린 것을
  그대로 쓰지 않았다.

## 그때 남아 있던 것

- 🔴 **인제션은 열려 있다.** 이 게이트는 체인 발화와 리플레이에만 앉았다. 인제션 경로는
  `818c9c0`의 판정 아래 **변경 전과 동일하게** 키 없는 행을 쓴다(측정으로 확인).
- **격리 스택은 재기동하지 않았다.** `:8081`의 프로세스들이 옛 코드로 계속 돌고 있었다.
- **브라우저 그리드 클릭은 안 태웠다.** 그리드 편집은 HTTP로 몰았고, 요청·엔드포인트·
  쓰기 경로·감사 기록은 클릭이 만드는 것과 같지만 **AG-Grid 렌더링과 WS 델타는 관측되지
  않았다.** 동시 레인들이 브라우저 탭 상한을 다 쓰고 있었고 남의 탭을 닫지 않았다.
- **체인 규칙 넷은 이 스냅샷에서 잴 수 없었다** — 소스/타깃 표가 스냅샷에 없다.
  조용히 빠뜨리지 않고 이름으로 적었다. `dt_log_to_dt_map`은 비활성으로 배포된다.
- 같은 커밋이 `docs/architecture/data_model.md`와 `docs/guide/chain_ingestion_guide.md`를
  같이 옮겼다 — 리빙 문서 쪽 반영은 그 두 파일까지다.
