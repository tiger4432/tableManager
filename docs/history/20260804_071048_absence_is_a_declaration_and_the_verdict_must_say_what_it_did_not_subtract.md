# 부재는 선언이다 — 그리고 판정은 「무엇을 빼지 않았는지」 말해야 한다

> **일자:** 2026-08-04 | **관련 커밋:** `2c2a777`(완화) + 이 항목과 같은 커밋(QA B1 후속)
> **담당:** 사용자(현장 피드백 — 부속 테이블을 두지 않고 불량 맵을 겹쳐 맵 위에서 차감한다) · 총괄 판정 · server-pm 구현 · qa-reviewer 검수(T2, GO-WITH-FIXES)
> **대상:** `server/bonding_plan.py`(`STATUS_NOT_DECLARED`·`role_is_declared`) · `server/transfer_plan.py`(`_aux_role_status`·요약·로트 합산·**`validate_plan`**) · `server/tests/test_availability_relaxation.py` · `docs/spec/MAP_EDITOR_SPEC.md §6.2-ter` · `docs/guide/CONFIG_GUIDE.md §3-S6/§5.8/§5.8-ter/§6-I`
> **선행 항목:** 7c `ab6ac02`(2026-07-29 — `transfer_log: "none"`. 「바인딩이 깨진 것과 사이트가 없다고 말한 것은 다르다」를 처음 분리한 라운드)

## 결함 — 이 엔진은 「없다」를 「깨졌다」로만 읽을 수 있었다

`transfer_log`·`origin_log`·`fail_sources`·`process_history`가 config에 **키조차 없으면**
엔진은 그것을 깨진 바인딩과 똑같이 `missing`으로 접었다 → `source_degraded` → 신뢰 표기
3층 방어가 발동해 `remaining: null`. 실 현장은 그 부속 테이블을 **아예 두지 않고** 불량 맵을
겹쳐 그려 맵 위에서 차감한다. 그래서 그런 사이트에서는 **모든 자재의 가용이 `미상`**이었다 —
방어가 지켜 줄 값 자체가 없는 상태이고, 이것은 보호가 아니라 기능 부재다.

## 수정 ① — config 경계에 상태가 셋이 된다

술어는 **하나**이고 `bonding_plan`에 한 번만 정의된다(`role_is_declared` = 키 존재 검사,
`transfer_log_is_declared_none`과 같은 규율). M2 인라인 엔진 · `/stages` 역할 뷰 · M1
`core-summary`가 그 하나를 함께 쓴다.

| 선언 | status | `remaining` | 강등인가 |
|---|---|---|---|
| 키 자체가 없음 | **`not_declared`** | **숫자**(그 감산항 없이) | 아니오 |
| 키는 있는데 깨짐(`null`·오타·테이블 부재) | `missing` 등 종전 그대로 | `null` | 예 |
| `transfer_log: "none"` | `connected(untracked)` | `null` + 상한 | 아니오(7c) |

`total_chips`는 분모라 예외로 남는다 — 없으면 가용이 성립하지 않는다.
`transferred`/`used`는 로그가 없으면 `null`이다(가짜 `0` 금지). `remaining`만 숫자인 이유는
**감산항이 존재하지 않는다고 사이트가 선언했기 때문**이다 — 미지수가 아니다.

## 수정 ② — 총량이 순량 행세를 하는 침묵은 필드 하나가 막는다

`inactive_subtractions`(빠진 감산 종류의 이름 목록). 비어 있으면 **필드 자체가 없으므로**
전 역할을 선언한 환경의 응답은 완화 전과 **바이트 단위로 동일**하다.

## QA가 잡은 것 — 판정을 내는 라우트만 그 필드를 모르고 있었다

적대 검수(B1)의 지적은 정확했다. `validate_plan`은 `remaining_reliable` **하나로만**
게이트하는데(`transfer_plan.py:3290`), 완화가 그 플래그를 감산 없는 숫자에 대해 `true`로
만든다. 그리고 반환 dict에는 `inactive_subtractions`도, 어떤 경고도 없었다 —
**운영자에게 가·부를 건네는 유일한 표면이 감산 없는 숫자를 조건 없는 `ok`로 제시**했다.
새 안전 필드를 「요약 응답」에만 달면 판정 라우트는 그 필드를 모른 채 숫자만 읽는다.

**총괄 판정(2026-08-04): 게이트가 아니라 마커다.** 되돌리지 않는다 — 미선언은 시스템이
적용하지 못한 숨은 데이터가 아니라 **그 사이트가 가진 최선의 지식을 적은 선언**이고,
`availability_unreliable`로 다시 강등하는 것은 사용자가 없애 달라고 한 바로 그 가혹함을
복원하는 일이다. 그래서:

- `validate` 응답이 **슬롯/로트/M1과 같은 이름·같은 모양**으로 `inactive_subtractions`를 싣는다(한 어휘, 한 철자).
- 판정 문자열은 `ok` 그대로. `remaining_reliable`도 그대로 — **신뢰 축을 하나 더 만들지 않았다.**
- 전 역할 선언 환경의 응답은 바이트 동일(목록이 비면 필드 없음).

수집 지점은 **신뢰도 게이트를 통과한 뒤**다. 판정 불가로 건너뛴 소스의 수치는 아무 판정에도
쓰이지 않았으므로, 이 목록은 「지금 내가 내는 판정이 딛고 선 수치」만 서술한다.

## 왜 아무도 못 잡았나 — validate 표면을 완화된 config로 태운 테스트가 없었다

완화 라운드의 새 테스트 10건은 요약·`/stages`·BIN·로트·M1을 덮었지만 **`validate`를 한 번도
완화 config로 호출하지 않았다.** 축이 없으면 술어는 채점되지 않는다(2026-08-04 N7 라운드의
교훈과 같은 모양). 이번 라운드는 결함 주입으로 그 축이 실제로 살아 있는지 먼저 확인했다 —
필드 방출을 끄면 새 테스트가 **빨강**, 되살리면 초록.

- `test_validate_names_the_inactive_subtractions_behind_its_verdict` — 완화 경로: 필요 5 ≤ **총량 8**로 `status: "ok"`가 나오고, 그 `ok`가 무엇 없이 나온 것인지 필드가 말한다.
- `test_validate_verdict_on_a_declared_config_is_byte_identical` — 같은 계획·전 역할 선언: 필요 5 > **순량 2**로 종전 `qty_shortage` 그대로, 응답 키 집합이 완화 전과 동일(새 필드 없음).
- `test_validate_omits_the_marker_when_the_gross_number_never_judged` — 판정 불가로 건너뛴 소스의 비활성 감산은 판정의 근거로 주장되지 않는다.

## 문서 — 완화가 거짓으로 만든 문장을 술어로 찾아 고쳤다

구현자의 목록을 믿지 않고 술어(`missing` = 선언 부재)로 검색했다. `CONFIG_GUIDE`
§3-S6(상태 사전) · §5.8-ter(「미선언 테이블을 가리키는 바인딩」) · §6-I(「role이 빠지거나」),
`MAP_EDITOR_SPEC` §6.2-bis(「키 삭제도 `missing`」)가 전부 이번 완화로 거짓이 됐다.

⚠️ **이름 충돌을 남긴다(총괄 확인 사항).** `CONFIG_GUIDE` §4.2-bis의 `config_resolve_report`
사유 어휘에 `not_declared`가 **이미 있다**. 판정: **술어는 같고**(필요한 선언이 없다 → 그 효과가
비활성) **축이 다르다**(한쪽은 `reasons[]`의 사유, 다른 쪽은 `sources.<role>`의 역할 status).
같은 뜻이므로 개명하지 않고, 두 절에 「서로 대체할 수 없다」는 상호 참조를 넣었다.
