# 선언된 join 도 «소급»이 된다 — 그리고 나쁜 페이지 하나는 «그 페이지»만 값을 치른다

> **커밋:** `bd0a3db7` — fix(replay): a declared join can be backfilled, and a bad page costs one page (S-242 · 판정 403)
> **일자:** 2026-09-15 13:08
> **레인:** 구현자(서버) — 지시 `da63c477` → 짓기 «전» 블록 `51e0ee32` → 판정 403 `e290c6e8` → 착지 → 보고 `b266126f` → 총괄 닫힘 `dc877746`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **9** · 변이 여섯 «전부» 빨강(builtin 문 다시 닫힘 5 · 페이지 실패 전파 1 · 세션 미롤백 1 · dry-run 이 씀 1 · 참조 쪽을 페이싱으로 판단 1 · 사전 계수가 셀을 읽음 1) · replay·retroactive·체인 계수 모집단 **1,201 passed** · `--collect-only` **6,660** 에러 0 (구현자 보고). 총괄 확인 「267 passed · mapper_call·join_into 무접촉 · 부팅 오류 0 · 체인 17 · 재기동 PID 52904」(`dc877746`).

## ① 왜 — 소유자 「이거 켜려면 어케해 소급」에 답이 «없었다»

```
replay_rule   mapper_module / mapper_function 만 알았다
builtin 규칙  그 둘이 «비어» 있다 -> importlib.import_module(None) 이 던진다
워커          같은 규칙을 builtins.run_builtin 으로 돌린다
=> 라이브와 소급이 «한 규칙에 문 둘»인데, 한쪽 문이 «아예 안 열렸다» — 「같은 기능에 두 경로」의 가장 비싼 판
```
🔴 이관한 join 은 «지금부터 바뀌는 행»만 채웠고, 이미 있던 행(박스 실측 dt_inventory 488,429 행)을 채울 길이 없었다.

## ② 변경 — builtin 갈래가 «워커와 같은 문»으로 페이지마다 돈다

```python
# server/chain/replay.py  replay_rule()
builtin_kind = (rule.get("mapper") if rule.get("mapper") in builtins.BUILTIN_KINDS else None)   # «한 번» 정하고 «보고»한다
stats = {..., "builtin_kind": builtin_kind, "rows_written": 0, "pages_failed": 0, "page_failures": [], ...}
...
if builtin_kind is not None:
    page_ids = [row_id for row_id in (getattr(row, "row_id", None) for row in page) if row_id]
    if not apply:
        stats["mapper_items"] += len(page_ids); continue        # dry-run: «써 봐야» 셀을 알 수 있는 종류라 «행 수»를 답한다
    try:
        outcome = builtins.run_builtin(builtin_kind, db, rule, row_ids=page_ids) or {}
    except Exception as page_error:
        db.rollback()                                           # <- 다음 페이지의 SELECT 가 abort 된 트랜잭션에 말 걸지 않게
        stats["pages_failed"] += 1
        stats["page_failures"].append({"page": ..., "rows": len(page_ids), "error": gist[-1]})   # 열 개까지
        continue                                                # <- 런은 «계속»
    stats["rows_written"] += int(outcome.get("written") or 0)
    if outcome.get("refusal"): stats["pages_failed"] += 1; ...  # 거절은 «답»이다 — 던지지 않고 보고에 싣는다
    db.commit(); continue
# 아래 「The REAL mapper invocation path」는 «바이트 무변»
```
```
rows_written   cells_proposed «옆에» — «접지 않는다». 스스로 쓰는 종류는 셀을 «제안»하지 않으며,
               다른 사실 둘을 한 이름에 담으면 보고가 «틀리게 읽힌다»
격리           «이 갈래에만»(판정 403). 파일 맵퍼 호출은 바이트 무변 — 그쪽 격리는 S-242-b(등급 4)
```

## ③ 첫 가드가 «틀렸고», 자기 판별 시험이 잡았다

```python
def is_reference_side(rule: dict) -> bool:
    """참조 쪽 = «읽는 표»를 트리거로 하는 쪽 — 그 표는 자기가 «쓰는» 표가 아니다"""
    right = ((rule.get("params") or {}).get("right_table")) or ""
    trigger = rule.get("trigger_table") or ""
    return bool(right) and trigger == right and trigger != (rule.get("target_table") or "")
```
```
첫 판    「follow_up 인가」로 걸렀다
실측     S-237 이 통합 join 의 «양쪽»을 페이싱으로 만들었다 -> 둘 다 follow_up=True
결과     운영자가 «돌려야 할» 왼쪽 규칙까지 거절했다 — 판별 시험이 빨개졌다
고침     «칸»이 아니라 «성질»: 트리거가 «읽는 표»에 앉아 있는가
```
📌 부류: 판정 387→388(「예외를 이름에서 성질로, 그리고 «어느» 성질인지」)과 같은 교훈을 «한 라운드 먼저» 잡았다. 시험이 `rules[0].follow_up == rules[1].follow_up is True` 를 «같이» 단언해 「둘은 페이싱이 아니라 트리거로 갈린다」를 못 박았다.
🔵 참조 쪽 규칙(`…:reference`)은 «이름 대고 거절»된다 — 그것을 돌리면 참조 행마다 «같은 답을 두 번» 치르기 때문이고, 거절문이 「Replay that one instead」로 «나갈 길»을 든다(S-247 자세).

## ④ 사전 계수가 「0 셀」이라 답할 뻔했다

```python
# server/admin/retroactive.py  _count_chain_replay()
is_builtin = bool(s.get("builtin_kind"))                   # <- replay 가 «보고하는» 것에서. 「items 는 있는데 cells 가 0」 추론이 아니다
affected = s["mapper_items"] if is_builtin else s["cells_proposed"]
"affected_label": "다시 계산할 행" if is_builtin else "덮어쓸 셀",
```
지시가 「`_count_chain_replay` 의 세기가 맞는지 재라」 했고, 재 보니 `cells_proposed` 를 읽는데 builtin 은 그 칸이 0 이다 — **488k 행을 다시 쓰는 소급 앞에서 운영자가 동의하는 화면이 「0 셀을 다시 씁니다」**가 됐을 것이다. 「아무것도 안 한다」고 말하는 사전 계수는 사전 계수가 없는 것보다 나쁘다.
📌 «추론»이 아니라 «보고»에서 판단한 이유: 「items 는 있는데 cells 가 0」은 셀을 0 개 «정당하게» 제안하는 첫 파일 맵퍼에서 틀린다.

## ⑤ 단언 하나가 «공허»했고 변이가 잡았다

```
단언     「SELECT 1 이 된다」 — 롤백을 «빼도» 초록
이유     SQLite 에서 실패 문장은 세션을 «안 죽인다». §0-ter ② 가 말하는 것은 PostgreSQL 의 abort 다
고침     이 경로가 «지는 빚»은 롤백 «그 자체» — `rolled == [True]` 를 잰다
```
📌 부류: **「범례가 단언을 공허하게 만든다」**의 방언 판 — 단언의 주어가 «이 DB 에서 일어나지 않는 것»이면 초록은 아무것도 재지 않는다.

## ⑥ 그때 남아 있던 것

- **파일 맵퍼 페이지 루프에는 여전히 try 가 없다** — 한 페이지가 던지면 «런 전체»가 죽는다. 판정 403 이 그것을 «별 줄»(S-242-b, 등급 4)로 두었다: 소급은 운영자가 부르고 체크포인트로 재시작되므로 오늘 «막지 않는다». `test_the_file_mapper_call_is_unchanged` 가 «try 가 «안» 생겼음»을 단언한다 — 즉 이 시점의 게이트는 그 구멍을 «지키는» 쪽이다.
- RUN.md §5 에 소급 절차가 실렸다: 어드민 소급 탭 → `chain_replay` → 규칙 이름은 «왼쪽 규칙» → pace `slow`/`trickle` → «세기»(「다시 계산할 행」) → 실행. 「왼쪽 표 전체 행이 대상(박스 실측 488,429 행)」은 «박스 수»다.
- 첫 실행 «없음». 이 박스에 통합 join 선언이 없어 소급을 «돌린» 기록은 없다 — 총괄 재기동 PID 52904 는 부팅 확인이다.
- 이 채널의 미답 «없음». 다음은 S-240(로더가 통합 join 의 `key.unique` 를 읽지 않음) → S-245 → S-246 → S-247.

---
📎 수는 구현자 보고·총괄 확인·RUN.md 의 «박스 수»다. 「운영」이라 적은 줄은 소유자 원문뿐이다.
📎 통합 join 의 두 규칙(왼쪽·`:reference`)이 태어난 자리: `20260915_093113_the_day_strictness_invalidated_what_was_already_running.md` §②.
