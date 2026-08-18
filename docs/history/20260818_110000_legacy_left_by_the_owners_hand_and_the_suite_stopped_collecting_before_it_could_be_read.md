# legacy는 소유자 손으로 먼저 나갔고, 스위트는 읽히기 전에 수집에서 멈췄다

**날짜:** 2026-08-18 07:48~11:06 · **커밋:** `0ff91a7` `ea832c0` `855f831` `aad42fb`
`459946b` `e1a7a6f` `f3a6915` `d7bfcd0` `d752bce` `cac3aca` `e47d325`
**레인:** 서버(원장 단순화 1라운드 · legacy 은퇴) · **측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경 — 계획이 아니라 사고로 시작됐다

`task/ledger_simplification_program.md`는 「legacy 은퇴는 별건」이라고 적고 있었다.
그 서술이 그날 아침 **폐기됐다**(`855f831`). 이유는 판단이 바뀐 것이 아니라 사실이 바뀐
것이다 — **소유자가 번역기 6개를 작업 트리에서 직접 지웠다.**

`declared_translator.py` · `lot_event_translator.py` · `observation_translator.py` ·
`transfer_translator.py` · `translator_pattern.py` · `mappers/ledger_lot_event_mapper.py`.

실측한 여파가 둘로 갈렸다.

- **v2 실행 경로는 무사했다.** 지운 모듈은 전부 함수 안에서 늦게 import되고 있었다.
- **스위트는 통째로 멈췄다.** 수집 단계에서 8개 파일이 오류를 내고 pytest가 전체 실행을
  중단했다 — **4,335개가 한 개도 돌지 않았다.**

즉 초록도 빨강도 아니고 **아무 답도 없는 상태**였다. 지운 것을 부르는 자리는 문서에 파일과
줄로 적혔고, `source_contract.py`가 지운 모듈 경로를 **문자열로** 가리키고 있어 import 오류는
안 나는데 내용이 거짓인 자리도 함께 적혔다.

## 🔴 8과 10은 서로 다른 것을 센 것이다

구현 레인이 수집 오류를 10건이라 보고했고 재측정했다(`aad42fb`). **둘 다 맞았다.**

- `server/`에서 `pytest tests` → **8건.** 전부 삭제된 번역기 import가 원인이다.
- 저장소 루트에서 `pytest` → server/tests 기준 **10건.** 늘어난 둘
  (`test_map2_seam_contract`·`test_notation_fold_contract`)은 **직접 지목해 돌리면 정상
  수집된다.** 삭제 여파가 아니라 rootdir/conftest 수집 경로 문제다.

문서가 그 판정을 이렇게 닫았다 — 「10건을 다 고쳤다」로 보고하면 **두 종류의 문제를 한
덩어리로 만든다.** 이 라운드가 고쳐야 할 것은 8건이다.

## 「지웠더니 초록」을 구별하는 계측기를 먼저 만들었다

`459946b`. 은퇴 라운드는 커버리지가 **옮겨졌는지 잃어버렸는지**로 판정되는데, 초록 스위트
쪽에서 보면 **둘이 똑같이 보인다.** 그래서 지워질 8개 파일이 유일한 집이었던 불변식마다,
그 불변식을 단언하는 테스트만 가질 법한 **문자열 마커**를 붙여 세는 도구를 만들었다.

```python
"v2: mapper import boundary":
    ("ledger_v2_lot_event_role_mapper",
     "the mapper file must not import database/gate/store/envelope/ledger_frame"),
"backfill: group page boundary":
    ("walk_group_pages",
     "a group dropped at a page boundary is read on the next page"),
```

> Run before and after the round. A marker that goes to zero files is coverage that left
> and did not arrive.

## 🔴 산문이 세는 숫자는 조용히 낡는다 — 셋이 아니라 넷이었다

`f3a6915`가 legacy 진입점을 막으면서 `backfill.py` 헤더에 이렇게 적었다.

```
🔴 The count in this header used to be maintained by hand and went stale silently: it said
THREE until 2026-08-18, having missed `_run_declared`, and the wrong count propagated into
four documents before anyone re-read `run()`. Prose that COUNTS something the code also
counts will go stale, because nothing executes the prose.
```

**세 문법이라 적힌 것이 실제로는 네 문법이었고, 그 틀린 수가 문서 넷으로 번졌다.**
그리고 네 드라이버는 전부 소유자가 지운 번역기를 지연 import하고 있었으므로 **어차피
`ImportError`밖에 못 냈다** — 거절이 있어야 할 자리에 트레이스백이 있었다.

`run()`은 이제 선언된 `kind`로 분기하지 않는다. **v2로 선택되지 않은 소스는 여기서 이름을
대고 거절되고, 사유는 「없는 파일」이 아니라 「선언」이다.**

## 진입점 먼저, 사체는 그다음 — 두 커밋으로

소유자 판정(`aad42fb`)이 순서를 정했다: **「진입점을 먼저 막고 사체는 그다음이다. 한 커밋에
다 넣지 말라.」** 그대로 착지했다.

- `f3a6915` — 진입점 차단(`backfill.py` +84/-115)
- `d7bfcd0` — 네 드라이버 본체 삭제(`backfill.py` −848줄)
- `e47d325` — 번역기 다섯과 **그것을 재던 테스트들**을 같이 은퇴(−3,531줄)
- `cac3aca` — 매퍼 레지스트리에서 은퇴한 lot-event 등록 제거(−435줄)

`e47d325`가 테스트를 **같은 커밋에서** 지운 것이 요점이다. 먼저 지우면 그 사이가 무방비고,
늦으면 수집이 계속 막힌다.

## 손으로 관리하던 목록 넷이 코드에서 유도되는 하나가 됐다

`e1a7a6f`. `implementation_id`는 **이름**이고 모듈도 경로도 표현식도 아니다 — 그래서 무엇이
실행 가능한 이름인지 누군가는 말해야 한다. **그 경계는 옳고 이 커밋도 지킨다.** 틀렸던 것은
경계가 아니라 장부였다.

```
the same fact was written down in FOUR places -- a trusted catalog, a preparer registry, a
mapper registry, and a fourth literal inside the transfer sample's test support ... MEASURED
2026-08-18: two generic implementations (DeclarativeRoleMapper, DirectJoinSourcePreparer)
were already written, already correct, and unreachable from any config because nobody had
added them to the lists.
```

이제 클래스가 자기 정체를 선언하고 이 모듈이 그것을 읽는다. **import 집합은 저장소 레이아웃의
성질**이지 config의 성질이 아니고(그래야 선언이 무엇을 import할지 고르지 못한다), 상속만으로
정체를 물려받는 것은 인정하지 않는다. 「매퍼를 추가한다」는 `server/mappers/`에
`ledger_v2_*.py` 파일 하나를 놓는 일이 됐고, 이 모듈은 편집하지 않는다.

## 소스가 하나뿐이었던 진짜 이유

`d752bce`. 드라이버는 페이지마다 스토어에 「이 배치의 주체 중 이미 있는 것」을 물어 **첫
관측에만** `register` 원자를 낸다. 그 질문은 **준비 «전»에 물리 컬럼 이름으로** 던져지는데
프로필은 **준비 «후»의 논리 이름**을 묶는다 — 그래서 답을 바인딩에서 읽어 낼 수 없다.
그 선언이 없던 동안 드라이버는 **한 소스의 컬럼 이름을 하드코딩**하고 있었고, 그것이
**소스 하나만 돌 수 있었던 이유**였다.

오차의 방향이 대칭이 아닌 것이 안전 논증 전부다:

```
Naming a column that contributes no subject is therefore free ... MISSING a column is not
free: a subject that is already registered goes unsuppressed and the batch emits a duplicate
`register`. So the declaration must be a SUPERSET ...
```

`list_separator`가 함께 돌아왔다 — 한 문자열에 위치 목록이 든 컬럼을 안 쪼개고 물으면
**하나도 못 찾는다**(과소 근사, 위험한 방향). 은퇴한 문법에는 그 선언이 있었고 현재 문법은
그것을 **하드코딩된 구분자로 잃어버린 상태**였다.

## 검증

- 커밋 본문 주장: 원자 기준선 CASE DIFF 0, 불변식 로케이터 10/10.
  ⚠️ 기록자는 재실행하지 않았다 — **커밋의 주장**으로 남긴다.
- 기록자가 직접 확인한 것: 위 인용문이 각 커밋 diff에 실재한다는 것, 삭제 규모
  (−3,531 / −848 / −435)를 `--stat`으로 각각 셌다.

## 그때 남아 있던 것

- `--legacy` CLI 플래그와 `ledger/config.py`(63KB)는 소유자 판정으로 **전면 제거 대상이
  됐지만**, 이 라운드의 커밋들은 진입점 차단과 드라이버 삭제까지다.
- `ledger/dry_run.py`는 이 은퇴 목록에 없었는데도 같은 삭제로 **네 문법 전부 500**이 됐다.
  그 이야기는 `ab8657f`의 항목에 있다.
- `task/evidence/ledger_invariant_locator.py`는 라운드 «전후»에 돌리라고 쓰인 도구다.
  이 항목은 그 도구가 존재하고 10개 마커를 선언한다는 사실만 기록한다.
