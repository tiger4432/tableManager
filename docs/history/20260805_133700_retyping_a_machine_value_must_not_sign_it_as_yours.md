# 기계가 쓴 값을 다시 타이핑한 것에 사람 서명이 붙으면 안 된다 — 폼이 이미 아는 것을 안 보여 줘서 생긴 일이다

> **커밋:** `a565db1` (2026-08-05 13:37) | **일자:** 2026-08-05 오후
> **선행:** [`20260805_131200`](./20260805_131200_a_predicate_shipped_as_data_is_defined_by_whoever_applies_it.md)(`7f0a717`, **25분 전** — **이 결함을 도달 가능하게 만든 변경**)
> **담당:** enrichment 클라 레인(자기 변경이 만든 결과를 같은 라운드에서 닫음)
> **대상:** `client2/src/enrichment.js`(168) · `client2/enrichment.html`(37) · **신규 하네스** `enrichment_provenance_harness.mjs`(**+488**) · `check_harnesses.mjs`(+14) + dist
> **스위트:** **43 하네스 · 게이트 39 전부 초록 · 기지의 빨강 4 불변.** 파일 수와 `FLOORS` 항목 수로 확인된다(이 커밋이 하네스 하나를 추가하고 바닥 59로 등록한다).

## 배경 — 앞 커밋이 큐를 고치자 다음 결함이 손에 닿았다

반쯤 채운 행을 큐에 남기기로 하자, 컨베이어가 운영자에게 **모든 칸이 빈 행**을
건네고 **전부를 요구했다.** 그래서 운영자는 **이미 거기 있던 값을 다시 타이핑했고,
그 사본이 user 우선순위로 착지해 기계의 판단을 손으로 친 자기 복제본으로 덮었다.**

> **폼이 자기가 이미 아는 것을 보여 주지 않아서 기계 판단이 사람 판단이 됐다.**

## 칸이 저장된 값을 그 필자와 함께 싣는다

```js
    const stored = String(cellVal(row, field)).trim();
    input.dataset.baseline = stored;
    input.dataset.source = cellSource(row, field);
    input.value = stored;
    input.placeholder = stored === '' ? `${field} 입력 후 Enter` : '';
```

표시는 **맵 화면이 제안에 쓰는 것과 같은 파선·흐림 모양**이다 —
**여기 있는 것은 당신이 넣은 것이 아니다.**

표시는 **텍스트가 달라지는 즉시 사라지고, 저장된 문자열을 그대로 다시 치면
돌아온다.**

```js
function isTargetUntouched(input) {
  const baseline = input.dataset.baseline || '';
  return baseline !== '' && input.value.trim() === baseline;
}
```

**포커스는 첫 번째 빈 칸에 떨어진다** — 덮어쓰기가 절대 기본 동작이 되지 않게.
`Esc`는 비우지 않고 **되돌린다**(안내 문구도 `Esc 입력 지우기` → `Esc 저장된
값으로 되돌리기`).

## 저장은 텍스트가 다른 필드만 쓴다

```js
    after[field] = val;
    if (val === baseline) {
      record.withheld[field] = { value: baseline, priority_source: input.dataset.source || null };
      continue;
    }
```

손대지 않은 컬럼은 **페이로드에 아예 없다.** 그래서 값도 출처도 유지된다.
**글자 그대로 다시 타이핑하면 아무것도 안 쓴다.** 일부러 덮어쓰는 것은 새 컨트롤
없이 그대로 된다 — **필드를 편집하는 행위가 곧 그 행위**다.

## 빈 저장은 no-op이 아니라 거절이다

```js
  if (Object.keys(updates).length === 0) {
    showToast('바뀐 값이 없습니다. 고칠 칸을 수정한 뒤 저장해 주세요.', 'warning');
    console.log('[enrichment] save refused: nothing edited', record);
```

> **아무것도 안 쓰면서 성공했다고 보고하는 버튼은 운영자에게 그 버튼이 거짓말을
> 한다고 가르친다. 그러면 다음 진짜 실패가 같은 거짓말로 읽힌다.**

칸을 비운 채 저장하는 것도 별도 갈래로 거절되고, 포커스가 그 칸으로 간다.

## 레인이 자기 변경이 만든 결과를 같은 커밋에서 닫았다

저장이 이제 **대상을 공백으로 남길 수 있으므로**, 행은 **모든 대상이 비공백일 때만**
회수된다.

```js
    const stillBlank = (S.rule.target_fields || []).some(f => (after[f] || '') === '');
```

그리고 로컬에 반영되는 값은 **필자를 달지 않는다** — 옛 필자를 붙이는 것은
**같은 사칭**이기 때문이다.

```js
    rowData.data[col] = (cell && typeof cell === 'object')
      ? { ...cell, value: written[col], priority_source: null }
      : { value: written[col], is_overwrite: false, priority_source: null };
```

## 표시 폭도 같은 규율에 걸렸다

표시가 60% 폭에서 **`enrichment_auto_co…`**로 잘려 렌더되는 것을 발견하고 넓혔다.
`.target-field-head` 플렉스 래퍼가 **자르지 말고 줄바꿈하게** 하려고 들어갔다.

> **잘린 출처는 누가 썼는지 말하지 않으면서 말한 척한다.**

## 그때 남아 있던 것

- 이 커밋의 스위트 수치는 **파일 수와 `FLOORS`로 검증된다** — 이 라운드에서
  그렇게 대조 가능한 몇 안 되는 경우다.
- 덮어쓰기를 막는 새 컨트롤은 **없다.** 막힌 것은 **덮어쓰기가 기본이 되는
  경로**다.
