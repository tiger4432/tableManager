# 화면이 선언을 되무를 수 있게 됐고, 소스가 「내 표엔 세계 시각이 없다」고 말할 수 있게 됐다

**날짜:** 2026-08-18 22:18~22:59 · **커밋:** `ca7a6f0` `4d100c3` `1541e1a` `018a3d0`
`ee5960e` `ec9f1c2` (지시서 `64c52ba`) · **레인:** 서버(온톨로지 작성 모드 3라운드 착수)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

Ontology Config 화면은 그때까지 **교체만** 할 수 있었다. 선언을 새로 만들거나 없애는 것은
파일을 직접 여는 일이었고, 그것이 「파일 하나를 열고 닫으면 끝난다」는 오전의 목표와
어긋나는 마지막 자리였다.

같은 저녁 두 번째 소스(`dt_job`)를 세우려는 시도가 **선언 문법 자체의 구멍** 하나를 드러냈다.

## 삭제 표시는 `None`이 아니어야 한다

`ca7a6f0`.

```python
class _Remove:
    """Sentinel: this operation removes the leaf rather than writing one.

    A distinct object rather than `None`, because `None` is a legal JSON value and a
    declaration whose body is `null` must stay distinguishable from one that is gone.
    """
```

그리고 없는 것을 지우는 것은 **성공이 아니라 오류**다.

```python
    """Remove the leaf at `path`. Absent is an ERROR, not a silent success.

    A delete that shrugs at a missing target turns "someone already removed this" and
    "I removed the wrong thing and the real one is still there" into the same green.
    """
```

## 거절은 «행동할 수 있는 행»을 데리고 다녀야 한다

`018a3d0`이 `ConfigExplorerError`에 `details`를 붙였다.

> A refusal that only states a fault ("this is referenced") leaves the operator with no
> next move; the rows that made the refusal true have to travel with it.

`referrers()`는 개수를 세지 않는다 — **운영자는 화면이 이름을 대지 않는 것을 다시 가리킬 수
없기 때문**이다. 각 행이 참조하는 선언의 id와 **참조가 선언된 정확한 json 포인터**를 나른다.

그리고 `resolved` 엣지만 센다. 미해결 인바운드 엣지는 **이미 끊어져 있는 것**이라, 그것을
referrer로 치면 **다른 것이 망가졌다는 이유로** 이 선언이 삭제 불가가 된다.

**참조자를 대신 고쳐 주지는 않는다** — 남의 선언을 삭제의 부수 효과로 다시 쓰는 것은 한 번의
활성화에 올라탄 **두 번째 미검수 편집**이기 때문이다.

## 🔴 그리고 같은 밤, 그 가드가 «게이트가 아니다»라고 자기 자리에 적혔다

`ec9f1c2`. `require_no_referrers`라는 이름은 「이건 최후 수단이다」를 나를 수 없다.

```
🔴 READ THIS BEFORE WIRING IT TO THE DELETE BUTTON.  This function is the FALLBACK, not the
decision procedure, and its name does not say so ... measured on the live root, the number of
declarations with no referrer is ZERO, and a source and its profile name each OTHER, so
neither ever reaches an in-degree of zero.  A screen guarded this way refuses every delete
and reads to the author as "this screen cannot delete anything".
```

**기능을 만든 커밋과, 그 기능을 오해하는 배선을 막는 주석이 40분 사이에 갈라져 있다.**
올바른 질문(남는 root에서의 도달성)은 다음 커밋(`943cc64`)의 항목에 있다. 여기서는 그 판정이
**구현보다 먼저 코드 옆에 적혔다**는 사실을 남긴다 — 다음 사람이 이 함수를 삭제 버튼에 잇는
것을 막는 것이 그 주석의 일이다.

## 시각이 없는 표를 «정직하게» 선언한다

`4d100c3`. 그때까지 모든 소스는 시각 컬럼을 이름해야 했다.

```python
    """A source says WHERE its time came from - a world column, or an admitted basis.

    Before this, every source had to name a column. A table with no time column could only
    be declared by pointing at something that is not a time, or by pinning a constant into
    the profile - both of which produce atoms that READ as world time and cannot be told
    apart afterwards. ...
    """
```

**둘 중 정확히 하나**만 있어야 한다 — 둘 다 적으면 독자가 어느 쪽이 이겼는지 추측하게 된다.
`_OCCURRED_AT_BASES`는 `{"ingested"}` 하나로 **닫혀 있다**. 열린 문자열이면 오타가
**시각에 대한 조용한 주장**이 된다.

그리고 그 사실이 **원자에 실려 독자에게까지 간다**(`1541e1a`).

```python
# `occurred_at_basis` rides along so a reader can tell an observation time from a world
# time WITHOUT re-reading the config that produced the atom. NULL - which is every atom
# written before the column existed - means world time.
```

**NULL의 뜻을 코드 옆에 못 박은 것**이 이 세 줄의 값어치다. 컬럼이 생기기 전의 모든 원자가
NULL이므로, 그 해석이 정해지지 않으면 마이그레이션이 과거를 「미상」으로 바꾼다.

## 은퇴한 어휘 멤버를 이름하던 테스트 넷 — 블록째 지우지 않았다

`ee5960e`. `WaferLeg`가 `244312a`에서 어휘를 떠났고 그 이름을 대던 테스트들이 그 뒤로
빨간 상태였다. 넷을 **각각 자기 근거로** 처리했다.

- 주제 자체가 은퇴 멤버였던 하나는 **삭제.** 다만 그것이 유일한 독자였던
  `vocabulary.root_key`가 이제 **독자 0**이 된다는 사실을 **보고했고 고치지는 않았다.**
- 연쇄 롤업은 규칙이 **모양**에 대한 것이므로 합성 선언 타입 둘로 사슬을 만들었다.
  실재 멤버에 두 번째 홉을 걸어 둔 것이, 연쇄와 무관한 이유로 연쇄 규칙을 깨지게 만들었다.
- 두 결 갈래는 **구분자가 옮겨 갔을 뿐 요구사항은 그대로**라, 이제 네 갈래가 같은
  `subject_type`을 못 박고 payload qualifier 유무로 갈린다.

## 아키텍처 영향

작성 화면의 쓰기 경로가 **교체 / 생성 / 제거** 셋이 됐고, 제거는 참조 검사를 통과해야 한다.
원장 원자 스키마에 `occurred_at_basis`가 생겨(마이그레이션 포함) 시각의 출처가 원자 자체에
실린다.

## 검증

- 기록자가 직접 확인한 것: 인용한 docstring·주석이 각 커밋 diff에 실재한다는 것,
  `4d100c3`이 마이그레이션 파일(`add_ledger_occurred_at_basis.py`, 111줄)을 함께 실었다는 것.
- ⚠️ 「라이브 루트에서 referrer 0인 선언은 0건」은 `ec9f1c2` 주석이 인용한 실측이다.
  같은 숫자의 근거는 `943cc64` 항목에 있고, 기록자가 별도로 재측정하지 않았다.

## 그때 남아 있던 것

- `vocabulary.root_key`는 **독자가 없다.** 은퇴한 테스트가 유일한 독자였고, 그 사실은
  보고됐을 뿐 이 라운드에서 처리되지 않았다.
- 삭제 «컴포넌트» 판정은 아직 없다. 이 시점의 화면은 참조가 하나라도 있으면 거절하며,
  라이브 루트에서 그 조건을 만족하는 선언은 0개다.
- `64c52ba`가 「시각 없는 소스」 지시서를 남겼고, 그 판정이 이 커밋으로 착지했다.
