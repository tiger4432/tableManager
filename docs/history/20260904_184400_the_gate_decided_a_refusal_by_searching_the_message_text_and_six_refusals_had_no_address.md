# 게이트가 «메시지 «글자»를 뒤져서» 거절 사유를 정하고 있었다 — 그리고 거절 여섯에 «주소가 없었다»

> **커밋:** `93ee913d` (18:15) · `1c316668` (18:30) · `a1814dc6` (18:44) · `c12dade5` (19:03) · `d917117b` (19:44) · `1936c356` (21:01) · `18ec604b` (18:51)
> | **일자:** 2026-09-04 저녁
> **레인:** 구현자(서버) + 클라
> **측정 상자:** 이 워크스테이션. **다만 신고 셋은 운영에서 왔다.**

## 배경 — 운영 신고 둘

```
「원장이 운영에서 «한 달째» 안 돌았다」
「시간 컬럼이 «채워진» 소스인데 시험 실행이 「시간 컬럼이 비었다」로 거절한다」
```

## 🔴 ① 활성화를 막는 것을 «말하지 않았다» — 그리고 빨간 시험 실행은 그것이 아니다 (`93ee913d`)

`activate` 는 **정확히 하나**에서 거절한다 — 스냅숏 compare-and-swap. 실패한 **시험
실행**은 그것이 아니다.

```
🔴 그런데 «빨간 패널 옆에서 activate 를 누르는 사람은 없다»
   -> 내내 활성화 가능했던 선언들이 «한 번도» 활성화되지 않았다
   「화면이 틀린 게 아니다. 서버가 «무엇이 막는지»를 말한 적이 없다」
```

**값 둘, 산문 없음.** 시험 실행의 결과가 `blocks_activation: false` 를 나르고,
초안 뷰가 `activation_blockers` 를 나른다 — **`activate` 자기가 «던지는 코드»**라
둘이 갈라질 수 없다. 그리고 **빈 목록**이 말할 방법이 없던 답이다: 「지금 아무것도
안 막는다」.

```python
@classmethod
def activation_blockers(cls, record, active_index) -> list[str]:
    if record.get("base_snapshot_hash") != active_index.snapshot_hash:
        return [f"{cls.stale_status(record, active_index)}_draft"]
    return []
```
⚠️ **`activation_blockers` 는 «읽기»다.** `activate` 는 자기가 발견한 상태를 «기록»하지만
이것은 그러면 안 된다 — **그러면 폴링하는 화면이 «초안 이력을 다시 쓴다».**
시험이 기록이 안 바뀌는 것을 붙들고 있다.

⚠️ **쓰고 «지운» 시험 하나** — 메서드의 «소스 텍스트»에 대고 결과가 그 플래그를
나르는지 단언했다. **글자를 재지 동작을 재지 않아서** 지워졌고, 구멍은 파일에 «적혔다».
그리고 `test_ontology_config_explorer` 의 실패 «둘»은 **선행 결함**이라고 정직하게
표시됐다 — 「이 변경을 stash 해도 같은 둘이 실패한다」.

## 🔴 ② 두 문장이 «둘 다 참»이었다 (`1c316668`)

```
소유자: 시간 컬럼이 «채워져» 있는데 거절이 「비었다」고 한다
컴파일: «못 쓰는 첫 행»에서 «멈춘다»
=> 199 부분이 멀쩡한 페이지가 「실패한 «선언»」으로 보고됐다
```

🔴 **「‘비었다’는 두 행동 중 «어느 쪽»도 못 받친다. ‘이백 중 한 행, 컬럼 t 에서’는
«둘 다» 받친다 — 선언을 고치거나, 그 행을 고치거나.」**

`server/ledger/backfill.py` 의 `count_rows_missing()`. 제약 «둘»이 일한다:

```
«같은 페이지»   preview_first_batch 와 같은 fetch · 같은 순서 · 같은 크기
                -> 그 수가 «거절이 나온 그 행들»을 서술하지 «관계를 다시 읽은 것»이 아니다
«같은 술어»     from .source_preparation import _is_missing
                -> 던진 «준비기»에서 import 한다. «다시 철자하지 않는다»
```

```python
from .source_preparation import _is_missing
...
for row in rows:
    value = row.get(column) if isinstance(row, dict) else None
    if _is_missing(value) or (isinstance(value, str) and not value.strip()):
        missing += 1
return missing, len(rows)
```
⚠️ 「그것을 「None 인가」로 다시 철자하는 변이는 **`NaT` 가 세어질 때까지 모든 케이스에서
살아남는다** — 그리고 그게 정확히 소스에 시간이 없을 때 datetime 컬럼이 드는 것이다.」
(같은 날 오전 NaN 라운드와 «같은 결손 표지 가족»이다.)

⚠️ **세는 쪽이 거절 하나를 둘로 만들 수 없다** — 그것이 던지면 거절은 «수 없이»
전처럼 보고된다.

## 🔴 ③ 첫 셋만 «한 문장으로 이어 붙이고» 있었다 (`a1814dc6`)

v5 검증 이슈는 **이미 각자 `(code, path, message)` 를 들고 있었고**,
「path 는 운영자가 «열어야 하는 작성 박스»」다. 그런데 `_validate_for_version` 이
**처음 «셋»을 한 문장으로 join** 했다.

```
=> 화면이 받는 것: «코드도 주소도 없는 산문», 그리고 «무언가 잘렸다는 표시도 없음»
🔴 그날 다른 데서 «네 번» 고친 것과 «같은 조용한 절단» 부류이고,
   이것은 «운영자 자기 경로»에 있다 — 어드민 화면이 선언을 «이 함수를 통해» 읽는다
```

이제 **전부, 구조로, 그리고 «몇 개인지»를 말한다.** `LedgerConfigError` 가
**선택 `errors`** 를 받아서 **다른 모든 raise 자리가 그대로 돈다.**

🔴 **둘째 반쪽이 정직한 쪽이다** — 시험 실행의 거절이 **`partial_apply: false`** 를 나른다.
미리보기와 실행이 `_event_frames` 를 «공유»하므로, 실행도 미리보기와 «똑같이»
전부-아니면-전무다 — **멀쩡한 행들이 «안 들어간다».**

```
「‘199행이 써질 것’이라고 말하면 백필이 «그다음 깨는 약속»이고,
 그건 고치려던 거짓말보다 «더 나쁜» 거짓말이다」
=> 문장이 아니라 «값». 낱말은 화면이 쓴다
```

## ④ 화면 반쪽 (`c12dade5`) — 「이 줄이 중요한 줄이다」

```
개수는 «셋 다 아니면 아무것도» — rows_read · rows_missing · «컬럼»
   「컬럼 없는 개수는 아무도 행동할 수 없는 수다.
    「이 컬럼이 비었다」 하나로는 ‘내 선언이 틀렸다’와 ‘내 소스의 한 행이 비었다’를 못 가르고,
    둘은 «반대 행동»을 원한다」
🔴 「그리고 «실행이 무엇을 할지»를 말한다. 이 줄이 중요한 줄이다」
   없으면 운영자가 「나머지는 들어가겠지」로 읽고,
   그건 «서버가 하기를 금지당한 바로 그 약속»이다 —
   그러니 그것을 «빠뜨린 화면»이 «서버 대신» 그 약속을 한다
거절된 선언은 «자기 코드»를 지킨다 — 서버가 이슈마다 (code, path, message) 를 보내는데
   트리가 «셋 중 둘»만 찍고 있었다.  코드가 «서버 어휘에 대고 찾아보는 것»이고
   메시지만으로는 찾을 수 없다.  목록은 «전부» 그려지지 «잘라서» 안 그려진다
partial_apply 의 «true» 는 «아무것도 안 그린다» — 이 빌드는 서버가 그렇게 답하는 것을
   «한 번도 본 적이 없고», 약속은 «추론할 것»이 아니다
```

## 🔴 ⑤ 봉투의 거절 «여섯»이 이 시스템에서 «코드도 주소도 없는 유일한» 거절이었다 (`1936c356`)

`server/ledger/envelope.py`, **원자마다** 검사된다:

| 상수 | code | 주소(`path`) |
|---|---|---|
| `ENVELOPE_OCCURRED_AT_MISSING` | `occurred_at_missing` | `atom.occurred_at` |
| `ENVELOPE_OCCURRED_AT_NAIVE` | `occurred_at_naive` | `atom.occurred_at` |
| `ENVELOPE_SOURCE_WHO_EMPTY` | `source_who_empty` | `atom.source.who` |
| `ENVELOPE_TRANSLATOR_VER_EMPTY` | `source_translator_ver_empty` | `atom.source.translator_ver` |
| `ENVELOPE_RAW_REF_EMPTY` | `source_raw_ref_empty` | `atom.source.raw_ref` |
| `ENVELOPE_PAYLOAD_NOT_PRESERVABLE` | `payload_not_preservable` | `atom.object_payload` |

**전에는 목록 안의 «맨 문자열»이었다:**

```python
violations.append(
    "occurred_at is missing or is not a datetime - the world time must come "
    "from the source's declared time column, never from arrival")
```
「주위 검증기 «셋»이 전부 `(code, path, message)` 로 답하는데 이 여섯만 그랬다.
화면은 «문장만» 그릴 수 있어서 ‘어느 필드를 고치나’에 답이 없었다.」
그리고 **원자마다** 검사되므로 **운영자가 이 시스템에서 가장 자주 만나는 거절**이다.
**문장은 안 바뀌었다. 새로운 것은 «각 문장이 어디를 가리키는가»다.**

### 🔴 하중은 봉투가 아니라 «게이트»에 있었다

`server/ledger/gate.py` 가 거절 사유를 **메시지 텍스트를 뒤져서** 정하고 있었다:

```python
# BEFORE
for violation in envelope_violations:
    if "raw_ref" in violation:
        reason = REFUSE_NO_RAW_REF
    elif "occurred_at" in violation:
        reason = REFUSE_MISSING_OCCURRED_AT
    elif "NaN" in violation or "no JSON spelling" in violation \
            or "non-string key" in violation:
        reason = REFUSE_PAYLOAD_NOT_PRESERVABLE
    break
```
🔴 그 문구 셋은 **다른 모듈의 «예외 텍스트»에서 들어 온 것**이고, 그것을 낸 모듈과
보조를 맞추는 것이 «아무것도 없었다» — **문구를 다듬으면 원자가 받는 거절이 «조용히»
바뀐다.**

```python
_ENVELOPE_REASONS = {
    envelope.ENVELOPE_RAW_REF_EMPTY: REFUSE_NO_RAW_REF,
    envelope.ENVELOPE_OCCURRED_AT_MISSING: REFUSE_MISSING_OCCURRED_AT,
    envelope.ENVELOPE_OCCURRED_AT_NAIVE: REFUSE_MISSING_OCCURRED_AT,
    envelope.ENVELOPE_PAYLOAD_NOT_PRESERVABLE: REFUSE_PAYLOAD_NOT_PRESERVABLE,
}
```
부분 문자열 사슬과 **같은 폴백** — 모르는 코드는 `KeyError` 가 아니라 `NOT_TRUE_ALONE`
이라, **새 봉투 검사가 «정직한 거절»을 받는다.**

⚠️ **사고가 결정으로 승격된 것 하나** — naive 타임스탬프와 결손 타임스탬프가 여전히
사유를 «공유»한다. 「그건 두 문장에 다 'occurred_at' 이 들어 있어서 생긴 «사고»였고,
이제는 매핑에 «적힌 결정»이다.」 그리고 보고서는 **문자열 목록을 그대로 두고**
`violation_details` 를 «더한다» — 오늘 읽는 것이 아무것도 안 바뀌어도 화면이 각 거절을
필드에 얹을 수 있다.

## ⑥ 소스 상태가 «왜»를 «세 상태»로 나른다 (`d917117b`)

```
「‘몇 개가 거절됐나’는 화면에 닿았고 ‘왜’는 안 닿았다 —
 그래서 운영자가 «수»까지 가고 ‘무엇을 고치나’에서 멈췄고, 그게 이 단계 완료 정의의 «절반»이다」
```
**사유는 한 번도 «잃은» 적이 없다.** 소스마다 총계와 «한 문장으로» 써지니 내역이 총계와
갈라질 수도 없다. 「무슨 일이 있었냐면, 그것을 읽던 «유일한 코드»가 `ledger_trace.coverage`
에 걸려 있었고 **그 라우트가 2026-08-28 에 은퇴하면서 그 읽기를 데려갔다.**」
살아 있는 소스 상태 뷰가 이미 그 표를 읽으므로 — **컬럼 «둘»이지, 새 라우트도 쓰기도
감사 단위 변경도 아니다.**

```
NULL   이 행은 컬럼보다 «앞선» 것이라 내역을 낼 수 없다
{}     쓰는 쪽이 그 행을 «소유»했고 «아무것도 거절되지 않았다»
값     내역이 «있다»
=> 앞의 둘을 접으면 「모름」과 「없음」이 «같은 픽셀»이 된다 —
   바로 옆의 소스 상태들에 대해 이 뷰가 «이미 피하고 있는» 결함이다
```
🔴 **이날 가장 선명한 이 상자 표시** — 「**이 상자의 모든 행이 `{}` 인데도 빈 상태를
유지한다. 이 상자는 운영이 아니기 때문이다.**」

⚠️ `refusals_unaccounted` 는 **다시 계산하지 않고 `ledger_trace` 에서 import** 한다 —
**그 «부호»가 뜻을 나르기 때문**이다(0 평범, >0 배치 이력, <0 진짜 장부 결함).
철자가 둘이면 언젠가 «결함에 대해» 서로 다른 말을 한다.

## 아키텍처 영향

- 봉투의 거절 여섯이 **`(code, path, message)`** 를 나른다 — 원자마다.
  보고서는 **문자열 목록을 그대로 두고** `violation_details` 를 더한다.
- 게이트가 거절 사유를 **매핑 하나**로 정한다. **메시지 텍스트를 안 뒤진다.**
  모르는 코드의 폴백은 전과 «같다».
- 활성화를 막는 것이 **`activate` 자기가 던지는 코드**로 게시된다. **빈 목록**이 답이다.
- 시험 실행의 거절이 **몇 행 중 몇 행 · 어느 컬럼 · 실행이 «무엇을 할지»** 를 나른다.
  세는 술어와 페이지가 **거절을 낸 것과 «같다»**.
- 소스 상태가 사유 내역을 **세 상태**로 나른다.

## 스위트 (전부 이 상자)

```
1936c356  11건 · 변이 5 잡힘
93ee913d  (시험 하나는 «쓰고 지웠다» — 소스 텍스트를 재고 있었다)
1c316668  5건 · 변이 5 잡힘
a1814dc6  4건 · 변이 4 잡힘 (조용한 절단 복원 · 개수 제거 · 구조 이슈 제거 ·
          «errors 를 필수로» — 그러면 «기존 raise 자리 전부»가 깨진다)
c12dade5  68 -> 79 단언, 바닥 올림
d917117b  4건 추가 · 변이 3 잡힘
```
⚠️ 「199 / 이백 중 한 행」은 **소유자의 운영 사례**이지 이 상자의 측정이 아니다.

## 그때 남아 있던 것

- 🔴 **R2 의 «구조적» 반쪽은 «안 됐다»** — 배치가 부분 성공을 보고하는 대신 «통째로»
  죽는 것. `_event_frames` 가 실행 경로와 «공유»되고, 거기서 못 만드는 이벤트를 건너뛰면
  **원자가 조용히 떨어진다.** 세 층을 지나는 «미리보기 전용 경로»가 필요하고,
  **시도하지 않고 보고됐다.**
- `test_ontology_config_explorer` 의 실패 **둘은 선행 결함**이다 — 이 변경을 stash 해도
  같은 둘이 실패한다고 확인됐다.
- **이 상자에서는 사유 내역이 전부 `{}` 다.** 빈 상태와 NULL 을 가르는 설계는
  이 상자에서 «검증되지 않았다» — 일부러 그렇게 남겼다.
