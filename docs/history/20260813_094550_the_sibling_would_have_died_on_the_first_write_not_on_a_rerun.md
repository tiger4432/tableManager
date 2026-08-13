# The sibling would have died on the first write, not on a re-run

**Date:** 2026-08-13 09:45 · **Domain:** Server (체인 / dt_map 키 이동) · **Status:** 착지 — `4d5198c`

> ⚠️ **이 항목의 모든 수치는 격리 `assy_qa` 실측이다. 개발 사본이고 운영의 증거가 아니다.**

---

## 배경 — 한 형제만 다른 단위로 키를 잡고 있었다

`dt_map`은 **취득 단위**(`dt_job`)로 키를 잡고 있었고, `core_usage_map`은 이미 **물리
단위**로 잡고 있었다. 맵 하나는 웨이퍼 하나인데, **웨이퍼 하나에 여러 `dt_job`이 먹인다.**
두 잡이 같은 물리 다이를 쓰면 그것은 **한 행**이어야 한다 — 아니면 레이어링 불변식도,
사람 교정 규칙도 그 다이에 적용될 수가 없다.

그래서 키를 `(dt_lot, dt_slot)`으로 옮겼다. 그리고 **그 이동을 그냥 하면 데이터가
날아간다는 것**이 이 항목의 중심이다.

## 지시서가 말한 것보다 나빴다

지시서: 「한 잡이 재실행되면 형제 잡들이 그 공유 맵에 넣은 기여를 지운다.」
**주입해 보니 재실행 문제가 아예 아니었다.**

`replace_map`이 `(dt_lot, dt_slot)`로 스코프되면 형제는 **첫 파생에서, 한 트랜잭션 그룹
안에서** 죽는다:

```
In Scope: 3 | Claimed: 2 | Removed: 3
```

**「언젠가」가 아니라 「첫 쓰기에」다.** 회수(retraction) 없이 키 이동만 착지시켰으면 첫
쓰기에 데이터가 파괴됐다. 그래서 회수가 **먼저** 들어가야 했다.

## `plan_retraction`은 미완성이 아니라 «호출자가 없었다»

여기서 진단의 방향이 한 번 바뀌었다. 그 함수의 판단은 **온전했고 테스트도 있었다.**
`grep`이 찾은 것은 **운영 호출자 0개**였다.

빠져 있던 것은 로직이 아니라 **통합**이었고, 그래서 셋을 닫았다 — ① 원장 정합(행만 지우고
`cell_sources`·`cell_overwrites`를 고아로 남겼다, `crud` 자기 삭제 경로와 달리),
② 없는 호출자, ③ 삭제 이벤트 전파.

`replace_map`과 `retract`가 **같이 도는 것**은 워커가 거절한다 — 순서가 뒤집히면 회수가
형제를 살려 주기 «전에» purge가 먼저 지워 버리기 때문이다:

```python
if retract is not None and requested.get("replace_map"):
    raise ValueError(
        f"rule '{rule.get('name')}' set both replace_map and retract on "
        ...
        f"and retract removes by SOURCE; running both would purge the "
        f"sibling sources' cells before the retraction could spare them.")
```

## 키가 움직이면 복합 소스도 같이 움직여야 했다

```json
"composite_key_source": ["dt_lot", "dt_slot", "dt_x", "dt_y"],
...
"map_key_columns": ["dt_lot", "dt_slot"]
```

셋이 이것을 강제했다 — 행 키가 **물리 다이마다 유일**해야 하고, `derive_cells`가 2-튜플만
변환하므로 `dt_job`을 키에 남기면 **모든 행이 걸려서 못 넘어가고**, `dt_job`이 키에 있으면
**수렴 자체가 안 일어난다**(수렴이 이 이동의 목적이다). config·체인 규칙 바인딩·매퍼를
**한 착지로** 옮겼다 — 반만 착지한 키 이동이 바로 purge를 넓히는 모양이기 때문이다.

`dt_job`은 키 재료가 아니라 **셀과 함께 다니는 출처**가 된다. 그것이 셀을 추적 가능하게
만들고, 체인이 **정확히 한 잡의 기여만** 회수할 수 있게 하는 것이다.

## 새 코드 없이 지켜진 규칙

「메타데이터가 채워졌을 때만 맵을 만든다」는 **새 코드가 필요 없었다.** `chain_key_gate`가
이미 선언된 키 컬럼이 안 채워진 행을 거절하고 있었고, 복합 소스가 `dt_lot`·`dt_slot`을
이름 부르는 순간 **공짜로** 덮인다.

그리고 그 거절은 **가정한 것이 아니라 운영자 로그에서 읽어 냈다** — 로그가 빈 컬럼 «둘 다»
이름을 부른다.

**150잡 중 141이 맵을 안 만들었다. 그것이 규칙이 도는 모습이지 실패가 아니다** — 확정
lot·slot이 없는 잡은 아직 맵이 없을 뿐이다.

오늘 같은 DB를 읽기 전용으로 다시 재 봐도 그 모양 그대로다:

| `assy_qa` 실측 (2026-08-13) | |
|---|---|
| `dt_inventory` 행 | 150 |
| `dt_lot`·`dt_slot` 둘 다 채워진 행 | **11** |
| `dt_map` 셀 | 481 |
| `dt_map`의 서로 다른 `(dt_lot, dt_slot)` = 맵 | **6** |
| `dt_map`의 서로 다른 `dt_job` = 출처 | **9** |

**출처 9개가 맵 6개로 수렴해 있다.** 이 이동이 사려던 것이 그 수렴이다. (150 − 9 = 141이
「맵을 안 만든 잡」이다.)

실증은 진짜 `process_chain_transaction_group`을 통과해 나왔다 — 재실행이
`owns=3 stale=1 would_delete=1`로 회수했고, **형제는 두 셀을 값 그대로 지켰고**, 안 바뀐
재실행은 `stale=0`을 보고했고, 운영자가 손댄 셀은 살아남았다(`protected=1`).

## 이 이동이 «만든» 성질과 «드러낸» 사실

- 🔴 **수렴한 셀의 `dt_job`은 last-writer-wins다.** 그래서 형제에게 덮인 잡은 자기 낡은
  기여를 **영영 회수할 수 없다.** 방향은 보수적이지만(**덜** 지운다) 이 성질은 **이
  이동과 함께 새로 생긴 것**이다.
- **픽스처의 100% 겹침은 퇴화 케이스다.** 운영 비율로 읽으면 안 된다.
- 🔴 **이 시스템은 컬럼 타입을 ALTER하는 곳이 없다.** `sync_dynamic_tables_schema`는
  ADD만 한다. 그래서 `dt_inventory.dt_lot`의 `number → string` 수리는 **선언만 바꾸고
  물리 컬럼을 `double precision`으로 영원히 남긴다.** 이 사실이 이 커밋에서 처음 이름을
  얻었고, 두 시간 뒤
  [마이그레이션](./20260813_114522_the_half_of_the_repair_a_config_file_can_never_do.md)이
  나머지 절반을 처리한다.

## 되돌린 시도 하나 — `git checkout --`이 91줄을 지웠다

기록해 둘 값이 있는 실패다. 되돌리려던 **주입이 CRLF/LF 불일치로 조용히 적용에
실패**했고, 그래서 파일이 **안 바뀐 것처럼 보였다.** 그 상태에서 `git checkout --`을
걸어 레인의 작업 91줄이 날아갔다.

**「수정 안 됨」으로 보이는 것이 「주입이 안 붙었다」일 수 있다.** 몇 초 전 사본에서
복구했고 diff·테스트·증명 재실행으로 다시 확인했다.

## 검증

**테스트 119 passed / 1 failed.** 실패한 `test_all_three_declared_rules_ship_disabled`는
**이 변경 «전»에도 똑같이 실패한다** — `.sample`이 애초에 세 규칙 중 둘만 선언했기
때문이다. 이 변경이 만든 빨강이 아니다.

## 그때 남아 있던 것

- **수렴 셀의 `dt_job` last-writer-wins는 열려 있다.** 이 커밋이 만들었고 안 고쳤다.
- **`assy_manager`에는 이 키 이동이 적용되지 않았다** — `assy_qa`에만 적용됐다. 그래서
  이후 감사가 `assy_manager`에서 `dt_map.dt_lot`/`dt_slot`을 「선언됐는데 안 지어짐」으로
  본다.
- `server/config/*`·`server/mappers/*.py`는 **`git pull`로 가지 않는다.** `.sample`에만
  반영돼 있고 **손복사 단계가 남아 있었다.**
- 픽스처 실측 481셀·6맵·충돌 0은 **`assy_qa` 하나의 수**다. 스코프된 `replace_map`이
  정확히 한 맵만 가져갔고(121행 → 1) 나머지 다섯은 안 건드렸다.
