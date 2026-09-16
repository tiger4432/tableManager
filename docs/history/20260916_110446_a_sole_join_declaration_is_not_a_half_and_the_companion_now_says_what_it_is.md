# 「유일한 조인 선언」이 «반쪽»으로 읽혀 리플레이 목록에서 사라졌다 — 모양을 재던 것이 «칸»으로 바뀌고, 거절이 «범위»를 보게 됐다 (S-270)

> **커밋:** `0c6a70c1` — fix(replay): a sole join declaration is not a half, and a row-scoped replay never needed hiding (S-270)
> **일자:** 2026-09-16 11:04
> **레인:** 구현자 · 지시 `461cc6a3` · 순서 정정 `be1e9f26`(S-272 «앞»으로) · 보고 `37d0d5e8`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** `rule_shape` · `chain_bindings` · `replay` 를 이름으로 드는 모든 시험 **1,015 passed / 46 skipped** · 클라 `replay_rules_harness.mjs` **47 passed**(import, 잘라쓰기 0) · `npm run build` · `pytest tests --collect-only -q` **6,792 · 0 errors**(커밋 본문 · 보고).
> **파일:** `server/chain/replay.py` · `server/chain/rule_shape.py` · `server/chain_bindings.py` · `server/chain_skeleton.json` · `server/main.py` · `server/admin/retroactive.py` · `server/scripts/chain_replay_cli.py` · `client2/src/replayable_rules.js` + 시험 넷 · dist 번들

---

## ① 왜 — 「모양을 재는 술어」가 «둘»을 못 갈랐다

소유자 신고 둘: 「조인 체인이 리플레이 리스트에 안 뜨는데」 · **「조인이 참조하는게 트리거잖아」**. 총괄 보드(`a5f23983`)가 적었듯 **둘 다 맞고, 둘째가 재현 조건이다.**

옛 술어는 «모양»을 물었다:

```python
def is_reference_side(rule: dict) -> bool:
    if (rule or {}).get("mapper") not in builtins.BUILTIN_KINDS:
        return False
    right = ((rule.get("params") or {}).get("right_table")) or ""
    trigger = rule.get("trigger_table") or ""
    return bool(right) and trigger == right and trigger != (rule.get("target_table") or "")
```

`trigger == right_table != target` 은 **두 가지에 대해 참이다**:

```
ⓐ 로더가 «둘째 반쪽»으로 세운 짝(companion)              -> 이것을 겨냥한 술어였다
ⓑ 선언의 `on.table` 이 «참조 표» 인 통합 선언 하나        -> «합법»이고, «유일»하고, 소유자가 쓴 것
```

총괄이 in-process 로 잰 것:

```
on.table = 참조표 인 선언 -> primary trigger=참조표 · companions «[]» (짝이 없다)
                            replay.is_reference_side(primary) = «True»
```

그래서 그리드에 있던 **유일한 조인**이 `replayable_rules_for` 에서 빠지고, `find_rule` 은 그 이름을 거절하면서 **「대상 쪽 규칙을 대신 돌려라」** 고 가리켰다 — **그 규칙은 존재하지 않는다.**

---

## ② 바뀐 것 ⓐ — 짝이 «자기가 짝이라고» 말한다

로더만이 「나는 이 선언의 둘째 반쪽으로 만들어졌다」를 안다. 그래서 그것을 «찍는다»:

```python
companion = dict(primary)
companion["name"] = str(name) + REFERENCE_SUFFIX
companion["trigger_table"] = right_table
# 🔴 [S-270] IT SAYS WHAT IT IS, HERE, WHERE THAT IS KNOWN.
companion[COMPANION_CELL] = str(name)
```

그리고 술어가 **그 칸만** 읽는다:

```python
def is_reference_side(rule: dict) -> bool:
    from chain import rule_shape
    return bool((rule or {}).get(rule_shape.COMPANION_CELL))
```

### 🔴 이름 접미어(`:reference`)를 파싱하는 길은 «일부러» 안 갔다

`rule_shape.py` 의 상수 주석이 사유를 적는다 — 이름은 **운영자가 쓸 수 있는 것**이고, 거기에 **로더만 부여할 수 있는 뜻**을 싣는 것은 같은 실수를 한 층 위에서 하는 것이다. 접미어는 «라벨»로 남는다. 시험 하나가 그것을 못 박는다(`test_the_name_suffix_is_not_what_decides` — 사칭 이름은 반쪽이 아니다).

⚰️ 그리고 이것이 **같은 물음의 세 번째 판독**이다. 그 docstring 이 앞의 둘을 묘비로 남긴다:

```
첫 판   「is it `follow_up`」   -> «양쪽 반쪽 모두» paced 라, 운영자가 돌려야 할 그 규칙을 거절했다
둘째    「trigger == right != target」 -> 위 ⓑ 가 그것도 만족한다
셋째    로더가 찍은 «칸»          -> 「세 번 읽는 물음을 칸 하나가 끝낸다」
```

---

## ③ 바뀐 것 ⓑ — 거절이 «범위»를 본다. 그리고 술어가 «하나»다

S-242 가 짝을 거절한 사유는 **비용 논증**이었다: 짝을 돌리면 참조 행마다 그 대상들을 다시 찾는데, 대상 쪽 규칙이 그것을 이미 «모든 행에» 해 준다. 그건 **「표 전체를 돌릴 때」의 논증**이다.

그리드 배너는 payload 에 `row_ids` **뿐**을 싣고, `replay_rule` 이 그것으로 스캔을 좁힌다. 행을 고른 순간:

```
· 그 행들의 대상을 다시 유도하는 것은 «라이브 체인이 그 행이 움직일 때 하는 바로 그 일»이다
· 대상 쪽 규칙은 «그리드가 고를 수 없는 표»를 트리거로 한다
  -> 운영자에게는 「그걸 대신 돌려라」가 «없다»
```

그래서 술어가 «하나»로 접혔고, 거절·목록·라우트가 **같이** 그것을 지난다:

```python
def replay_is_refused(rule: dict, row_scoped: bool = False) -> bool:
    """May this rule NOT be replayed? The ONE predicate the refusal, the list and the
    route all pass through (S-270)."""
    return is_reference_side(rule) and not row_scoped
```

⛔ 두 번째 철자였다면 그것이 **S-250 의 결함**이다 — 화면이 내미는 이름을 소급이 거절하거나, 소급이 받을 이름을 화면이 숨긴다.

### 범위와 허가가 «한 값»에서 나온다 — 네 자리

```python
# server/admin/retroactive.py, 세는 쪽과 도는 쪽 «둘 다»
rule = replay.find_rule(params["rule"], row_scoped=bool(params.get("row_ids")))
```
```python
# server/scripts/chain_replay_cli.py — 조회 «전»에 파싱한다
rows = ([r.strip() for r in args.row_ids.split(",") if r.strip()]
        if args.row_ids is not None else None)
# ⚠️ [S-270] PARSED BEFORE THE LOOKUP ... Asking first and narrowing after is how
# a CLI comes to refuse what the button accepts (S-254 was that shape).
rule = replay.find_rule(args.rule_name, row_scoped=bool(rows))
```
```js
// client2/src/replayable_rules.js — 배너는 «항상» 행을 보내므로 항상 켜서 묻는다
`${API_BASE}/admin/chain/rules/replayable?table=${encodeURIComponent(table)}`
+ '&row_scoped=true',
```
라우트(`main.py`)는 `row_scoped: bool = False` 를 받아 그대로 넘긴다. 클라 주석이 **빼면 무슨 일이 나는지**를 적는다 — 「이 인자를 빼면 화면은 다시 그 규칙을 안 보여 주고, 운영자는 조인 체인만 없는 목록을 보게 됩니다」.

---

## ④ 지시가 물은 것 — 「새 칸이 로더 검증에 걸리나」. **걸렸다.**

이것이 이 라운드가 «재서 산» 것이다. 문법이 모르는 최상위 칸은 `flat_param_cells` 가 «맵퍼 인자»로 읽는다. 그래서 로더가 **자기가 찍은 스탬프에 대고** 「a mapper argument still written at the top level - move it under 'params'」를 **조인마다 · 매 부팅** 찍었다(실측 2026-09-16).

> 「영구 경고 한 줄은 진짜 경고 하나를 안 읽히게 만든다.」

수리는 이름을 **문법이 아는 자리에** 등록하는 것이고, 저자를 «하나»로 둔 것이다:

```python
# server/chain_bindings.py — 여기가 «저자»다
COMPANION_CELL_NAME = "companion_of"
...
RULE_ROUTING_OPTIONAL = tuple(... "idempotent", "origin",
    COMPANION_CELL_NAME,        # `origin` 과 «같은 부류» — 문법은 받고, 쓰는 것은 로더다
    ...)
```
```python
# server/chain/rule_shape.py — «가져다» 쓴다. 두 벌로 적지 않는다
COMPANION_CELL = chain_bindings.COMPANION_CELL_NAME
```
`chain_skeleton.json` 은 `routing_keys()` 에서 생성되므로 재생성됐다(`companion_of` 가 `required: false` 잎으로 들어감).

시험 하나가 그 관측을 고정한다 — `test_the_new_cell_is_a_cell_the_grammar_KNOWS`.

---

## ⑤ 시험 — 일곱 신규 + 둘 확장, 그리고 한 픽스처로 «두 답»

| 단언 | 무엇을 막나 |
| --- | --- |
| 유일 선언은 규칙 «하나»를 세우고 참조 쪽이 «아니다» | 소유자의 모양 자체 |
| 짝은 칸을 들고, primary 는 «안» 든다 | 칸이 아무 데나 찍히는 것 |
| 이름 접미어가 «결정자가 아니다»(사칭 이름은 반쪽이 아님) | 한 층 위의 같은 실수 |
| 짝은 통째로 거절 · 행을 주면 수락 · 거절문이 «나가는 길»을 댄다 | 범위를 안 보는 거절 |
| 유일 규칙은 «행이 없어도» 거절되지 않는다 | 범위를 과잉 적용하는 수리 |
| 새 칸에 flat-param 경고 «0», 저자 «하나» | 매 부팅 영구 경고 |
| 공유 술어의 «네 조합 전부» | 두 좌석 중 하나만 시험되는 것 |
| 목록: **픽스처 하나, 두 답** — `row_scoped=True` 면 짝이 서고, 없으면 통째 답이 «안 움직인다» | 초록이 「본 적 없다」인 것 |
| 라우트: 문을 «양쪽으로» 통과 | 「받고 무시하는 인자」 = 폼이 그리는데 읽는 쪽이 없는 것의 쿼리스트링 판 |

클라는 하니스가 모듈을 **import** 해서 요청 URL 에 `row_scoped=true` 가 실리는지 단언한다(`A1-bis`). 같은 커밋에서 기존 단언 `url.endsWith(...)` 가 `url.includes(...)` 로 바뀌었다 — 인자가 «뒤에» 붙었기 때문이다.

---

## ⑥ 아키텍처 영향

- **「대리를 성질로 읽는다」가 한 자리 줄었다.** 「로더가 이걸 둘째 반쪽으로 만들었나」는 로더가 «가진» 사실이고, 이제 그것이 칸으로 적힌다. 다른 칸 셋에서 재유도하지 않는다.
- 소급의 «허가»가 «범위»의 함수가 됐다. 같은 규칙이 통째로는 거절되고 행 범위로는 수락된다 — S-242 의 논증이 «자기 범위 안에서만» 참으로 남았다.
- 화면·라우트·CLI·소급 실행기 **넷이 한 술어**를 지난다. 「같은 기능에 두 경로가 없다」(구성 기준 ④)의 실물이다.
- `chain_bindings` 에 「문법은 받고 쓰는 것은 로더」인 칸이 `origin` 에 이어 **둘**이 됐다.

---

## ⑦ 그때 남아 있던 것

- **운영은 아직 이 커밋을 안 받았다.** 구현자 보고(`37d0d5e8`)가 「재기동 부탁드립니다」로 끝난다. 소유자가 신고한 화면이 실제로 조인을 다시 보여 주는 것은 «이 시점에 아무도 안 봤다».
- 총괄이 이 라운드의 «형태»는 확인했지만 게이트에 도장을 안 찍었다 — 채널에 그렇게 적혀 있다: 「게이트는 당신 몫이니 제가 통과 도장을 찍지는 않습니다」. 재기동 뒤 총괄이 «실경로»로 확인했다고 적은 것은 그 «다음» 보고(`17f60b97`)다.
- **이미 운영자 박스에 있던 라이브 선언은 못 세었다.** 이 칸은 로더가 «부팅 때» 찍으므로 파일에는 없고, 그래서 「이 표가 몇 개나 이 모양인가」는 라이브 선언을 붙여야 나오는 수다.
- `flat_param_cells` 경고가 «매 부팅» 찍혔다는 것은 **이 칸을 등록하기 전 며칠의 로그에 그 줄이 조인마다 있었다**는 뜻이다. 그 로그를 본 사람은 없다(운영 로그는 못 붙인다).
- 커밋에 `client2/dist/` 번들이 같이 들어갔다(빌드 산출물). 번들 파일명은 다음 빌드에 바뀐다.
- 순서가 «정정»된 라운드다 — 원래 S-272(운영에서 도는 25P01)가 급했는데, 총괄이 `be1e9f26` 에서 「끝난 미커밋 작업을 끊는 비용이 S-272 가 기다리는 비용보다 크다」로 S-270 을 먼저 착지시켰다. 그 사이 소유자께는 즉효 스위치(`analyze_after_rows: 0`)가 안내돼 있었다.

---
📎 이 항목의 수(1,015 / 46 · 47 · 6,792)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 사유 코드: S-242(짝의 거절 사유 — 이제 «범위 안에서» 참) · S-250(목록과 실행이 갈리면 결함) · S-254(CLI 가 버튼이 받는 것을 거절하던 모양) · S-188 ⓓ(`mapper`/`params` 칸 규율).
