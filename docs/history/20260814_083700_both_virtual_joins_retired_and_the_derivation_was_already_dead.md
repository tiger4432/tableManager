# Both virtual joins retired, and the derivation was already dead

**Date:** 2026-08-14 08:37 · **Domain:** Server (config) · **Status:** 착지 — `e327163`

---

## 배경 — 소유자 판정: 두 선언을 내린다

`dt_log_confirmed_attribution`·`dt_log_frame_attribution` — 둘 다 `enabled: true`,
둘 다 `table_config.json`에 없는 right_table을 가리켜 **매 로드마다 거절**되고
있었고, 그 거절은 인제션 배치당 로그 두 줄로만 표면화됐다.

## 은퇴는 이 파일 자신의 관용구로

밑줄 접두가 로더에게 키를 주석으로 읽히고, 파일엔 이미 같은 방식의 2026-08-02 은퇴
기록이 있다. 한 글자로 되돌릴 수 있고 모양과 이유가 읽히는 채 남는다.

남길 가치가 있는 부분: `dt_map_derivation`이 정확히 이 두 이름(`CONFIRMED_JOIN_RULE`,
`FRAME_JOIN_RULE`)에 대고 해소하므로 **귀속·프레임 경로는 이 커밋 전에 이미 죽어
있었다.** 선언 은퇴는 그것을 부수지도 고치지도 않는다 — 바뀌는 것은 실패가 말하는
자리다: `join_rule()`이 `REFUSE_JOIN_RULE_MISSING`을 raise하며 호출자에게 자기를
이름 댄다. 더 조용해진 게 아니라 **맞는 자리에서 들리게** 됐다.

테이블들은 실재하고 데이터를 든다(dt_job_attribution 252행, eqp_frame_attribution 5)
— 전날 미사용 판정에도 드롭 안 된 이유. 부활에는 접두 제거 이상이 필요하다: 두
테이블의 `table_config.json` 등록이 먼저, 아니면 선언은 정확히 종전처럼 거절로
돌아간다 — 그 문장이 시도할 사람이 실제로 서 있을 config 주석 안에 있다.

## 그때 남아 있던 것

- 두 파일(라이브·`.sample`) 모두 눈이 아니라 **파스로** 검증 — 이 config는 매 호출
  재읽기라 트레일링 콤마가 라이브 장애다. 파스가 함께 보여준 것: 이 둘이 빠지면
  활성 가상 조인 선언 수 **0.**
