# 커서가 «파일 전체»의 해시와 자기를 견주고 있었다

> **커밋:** `b100fb2a` (11:26) · `d6df6449` (12:38) | **일자:** 2026-08-21 오전
> **레인:** 서버(원장 · 셋업 레지스트리 / 커서)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **검증:** `d6df6449` 스위트 **48 passed** · 라이브 설정의 **사본**에서만 편집 실측
> **앞 항목:** [커서를 쓰는 키와 읽는 키가 달랐다](20260819_074500_the_cursor_was_written_with_one_key_and_read_with_another.md)

## 배경 — `lot_event` 를 고치면 `dt_job` 의 백필이 거절됐다

모든 소스의 커서가 **하나의 전역 `snapshot_sha256`**에 대고 비교됐다. 그 해시는 모든
레지스트리를 한꺼번에 덮는다. 그래서 `lot_event`의 바인딩을 편집하면 `dt_job`의 백필이
`cursor_snapshot_reset_required`로 거절됐다 — **`dt_job` 원자 하나도 바꿀 수 없는 변경에
대해서.**

`compile_setup_snapshot`은 원칙을 이미 적어 두고 있었다 — **「해시는 원자를 바꿀 수 있는
것만 덮는다」**. 이 라운드는 그것을 **소스별로** 지켰을 뿐이다.

## `source_cursor_fingerprint` — 한 소스에 실제로 «닿는» 재료의 이행 폐포

```
소스 계획      relation · read · prepare · map · bind  전부
팩             그 소스의 `use` 가 이름 붙인 팩, «통째로»
술어           그 팩들의 claim 이 내는 `emit.predicate` 전부
엔터티         위 어디에든 «나타나는» 엔터티 id 전부
+ compiler_contract_version · setup_version
```

🔴 **`bundle_sha256`이 커서 비교에서 빠졌고, 그 부재가 수리다.** 그것은 파일 전체의
해시라서, 남겨 두면 **지우려던 전역성이 그대로 복원된다.** 그것은 `snapshot_sha256`에 남고,
원자의 `setup_snapshot_hash`가 여전히 기록한다 — **「어느 «전체» 셋업이 이 행을
만들었나」와 「이 커서가 계속 가도 되나」는 다른 질문**이고, 오늘 움직인 것은 둘 중 하나다.

**폐포는 일부러 «크게» 틀린다.** `register@1`은 오늘 두 팩이 다 이름 붙이므로 그것을
편집하면 두 소스가 다 움직인다. 「내 선언만」으로 좁힌 폐포는 **밑에서 바뀐 술어에 대고
소스가 계속 도는 것을 허용**하고, 그것은 조용하며 커서 하나를 과하게 막는 것보다 나쁘다.

엔터티도 **네 가지 도착 모양을 열거하지 않고 재료를 훑어서** 모은다.

```python
def _reachable_entity_ids(value, known, found):
    """🔴 SCANNED, NOT ENUMERATED, AND DELIBERATELY SO.  An entity id reaches a source
    through at least four unrelated shapes ... Enumerating those four would be a list that
    goes silently WRONG the day a fifth is declared, and a closure that is too SMALL fails
    by not blocking a cursor that should have been blocked."""
```

키까지 대조하는 이유는 엔터티 id 가 **버전 붙은 이름**(`Lot@1`)이라, 우연히 맞으려면
그 문자열 그대로여야 하기 때문이다.

`backfill`(읽는 쪽)과 `runtime_v2`(쓰는 쪽)가 이제 **둘 다 `cursor_translator_version`을
묻는다** — 가드가 비교하는 값의 **철자가 하나**가 됐다.

## 저장된 커서를 다시 찍는 것은 «되감기가 아니다»

`LedgerStore.restamp_cursor`는 저장된 커서의 지문만 옮기고 **다른 것은 아무것도 안 건드린다.**
`source_translator_ver`가 `uq_ledger_atom`의 일부라서, 되감기거나 새로 만든 커서는
**이미 원장에 있는 행을 다시 읽고 새 지문 아래 «또» 착지시킨다** — dedup 되지 않는다.

이 박스에서 `dt_job` 재각인 실측:

```
translator_ver   39ebb419 -> 925655da
position         {dt_job: TWO, dt_cell_key: TWO_3_10}   불변
counters · updated_at                                    불변
원자              221,563 전후 동일
저장된 792 원자는 여전히 39ebb419 를 달고 있다     <- 원장은 «덧붙인다»
뒤이은 백필        거절 없음 · 0행 읽음 · 0원자 씀
```

## 실측이 보고서로 갔던 것을, 다음 커밋이 스위트로 옮겼다

🔴 `b100fb2a`는 소스별 지문을 **임시 사본 위의 편집 세 번**으로 증명했고, **그 측정은
보고서로 갔지 스위트로 가지 않았다.** 나중에 좁혀지는 폐포는 **조용한 방향으로** 실패한다 —
거절됐어야 할 소스가 밑에서 바뀐 계약 아래 계속 읽는다.

`d6df6449`가 셋을 못 박았고, **핵심은 셋 중 어느 하나도 충분하지 않다는 것**이다:

```
한 소스의 바인딩 편집이 다른 소스의 지문을 안 건드린다   목표. 그러나 «모든 소스를 무시하는»
                                                        지문도 이걸 통과한다
자기 편집이 자기 지문을 움직인다                        🔴 «판별식» — 「격리」와 「불활성」이
                                                        서로 다른 답을 내는 표본
두 소스가 «공유»하는 술어를 편집하면 둘 다 움직인다      좁힌 폐포가 드러나는 자리.
                                                        좁은 쪽이 위험한 방향이다
```

테스트가 실제로 무는지 **믿지 않고 주입해서** 확인했다:

```
지문 := 전역 스냅샷 해시     1·2 실패, 3 통과
폐포에서 술어를 뺌           3 실패, 1·2 통과
원복                         48 passed
```

픽스처에 **두 번째 소스**가 필요했다 — 소스 하나짜리 화단은 그 불일치를 **표현할 수 없다.**

## 아키텍처 영향

- 커서 진행 판정의 축이 **「전체 셋업」에서 「이 소스에 닿는 재료」로** 바뀌었다.
  `snapshot_sha256`은 계보 기록용으로 남았고, 커서는 `source_cursor_fingerprint`를 묻는다.
- 옛 규칙을 못 박고 있던 런타임 단언은 **지우지 않고 다시 썼고**, 등식 옆에 **부등식**을
  같이 박았다 — 「이 두 문자열은 더 이상 같지 않다」가 소스별 커서가 기대는 성질이다.

## 그때 남아 있던 것

- 🔴 **`lot_event`는 여전히 거절됐다** — `legacy_cursor_reset_required`, 즉 스냅샷 게이트가
  아니라 **커서 «모양» 게이트**다. 저장된 `cursor_value`는 `{event_time}`을 들고 있는데
  계획은 `{event_time, txn_seq}`를 선언하고, 그 `translator_ver`는
  `lot_event/1/rules:34311f15`다. **이 변경보다 오래된 것**이고 별도 판정 사안이라,
  재각인 스크립트는 그것을 **이름을 대고 거절한다** — v1 모양의 위치 위에 v2 처럼 생긴
  문자열을 바르지 않는다.
