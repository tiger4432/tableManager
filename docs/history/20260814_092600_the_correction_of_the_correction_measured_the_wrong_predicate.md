# The correction of the correction measured the wrong predicate

**Date:** 2026-08-14 09:22~09:26 · **Domain:** Server (references 라운드 F1~F4 구현) · **Status:** 착지 — `614a2ab`, `9f4fc3b`, 기록 `9913a83`

---

## F1·F3 (`614a2ab`)

- **F1**: `migrate_map_meta_to_wafer_id.py` 삭제 + `.RETIRED.md` 마커. 은퇴 규율은
  가정이 아니라 측정 — `map_doe`는 커밋 메시지를 마커 삼아 지워지지 않았고
  `server/migrations/`에 승인·이유·불가역·부활 경로를 헤더에 든 명명 산출물을 남겼다.
  그것을 맞췄다. 소비자 0은 `--no-ignore`로 확인(gitignore된 config·mappers 포함).
- **F3**: `core_wafer_map.key_columns` 오버라이드 삭제. 사용자 0을 두 방법으로 측정 —
  키 유무에 해소가 바이트 동일(출처만 `declared` → `inherited`), 두 상태에 걸친 교차
  라이브 요청 36회가 응답 다이제스트 정확히 1개.
- `__reason` 요구가 config만이 아니라 **코드에** 들어갔다 — config만이면 집행 지점
  없는 또 하나의 선언이다. `GET /admin/config/resolve`의 운영자 검증기가 질문을
  «내던» 자리(「같은 답이면 지워도 된다」 — 중복이 드리프트할 만큼 살아남은 메커니즘)
  에서 이제 질문에 «답한다».
- 레인의 교정 둘: 총괄 지시서가 라이브 config를 「갈라진 사본」이라 불렀는데 레인
  시작 시점엔 이미 복합키였다 — F3는 갈라짐이 아니라 **재서술**을 지웠다. `~0.64 s`는
  레인 넷이 도는 박스에서 회귀 신호가 아니다 — 타이밍 여섯 표본이 못 정한 것을 응답
  다이제스트 한 번이 정했다.
- 판정 필요로 올라간 것: `dt_map`의 오버레이는 리더를 `dt_job`으로, `table_config`는
  라이터를 `(dt_lot, dt_slot)`으로 키잉 — **F3의 라이터/리더 분열이 다른 이름으로
  라이브**이고 파일의 유일한 진짜 오버라이드. 레인은 정당화를 발명하지 않았다.

## F2·F4 (`9f4fc3b`) — 그리고 총괄의 «교정»이 같은 죽음을 맞았다

포크의 수를 교정한 총괄의 259/273이 스스로 죽었다. 세 가지가 틀렸다:
`_count_cells_bulk`의 유일한 호출자는 `floor_tables()`(= `valid_die_ref`·
`core_wafer_map`)를 돌므로 **`dt_map`은 그 함수에 전달되지 않는다**; 함수는
`table_config.map_key_columns`가 아니라 **해소된 바인딩의 `key_columns`**를 읽고
dt_map의 오버레이 arity는 1이라 도달해도 규칙에 안 걸린다; 술어는 「정확 arity가
아님」이 아니라 「부분이 너무 «적음»」 — `map_map_key_parts`는 마지막 컬럼이 나머지를
흡수한다. 교정된 사실: **라이브 위반은 셋, `SYN-CORE-WAFER-01/02/03`, 정확히 F2가
이미 사형선고한 그 세 행.** 실데이터 위반은 당일 0. 수리는 판정의 이유(다음 나쁜
등록의 재발 방지)로 여전히 옳되, 실행 속도 향상은 아무도 기대하면 안 되는 상태였다.

```python
# b510df2의 기존 모양을 따름: (counts, servable) 반환,
# 갈라지지 않는 id는 servable에서 빠지고 이웃은 단일 GROUP BY 유지
```

주입으로 증명: all-or-nothing 복원 시 울려야 할 두 테스트만 울림; arity 안 읽고
구분자만 세면 단일 키 테스트가 울림(1컬럼 키는 구분자 0이 정당 — 그것을 플래그하는
구현이 틀린 것). **F4**: 커플링은 키 하나(`archive_processed_files`) — 격리는 파일별
autouse, 손으로 쓴 모듈 목록 대신 `sys.modules` 스윕(스테일 목록은 운영자 파일을
«조용히» 다시 읽는 쪽으로 실패한다), 파일마다 「운영자 config를 읽을 수 없다」 단언
추가. 60 passed 격리, 격리 제거 시 8 fail.

## 교정의 교정 기록 (`9913a83`)

두 매장과 생존 사실이 판정 파일에 적혔다: 「dt_map이 지배적 케이스」 문장은 어디서든
삭제. 함께 온 의뢰(dt_map의 job/lot·slot 라이터-리더 분열)는 판정하지 않고 대기열로
— 결정할 두 측정이 항목에 적혔고 당일 착수는 금지됐다(콘솔 기한일).

## 그때 남아 있던 것

- `614a2ab`: 4 빨강(`test_map_alignment_columns.py`)은 옆 레인 것 — mtime 상관이
  아니라 이 레인 파일을 HEAD로 복원·재실행·동일 4실패로 무죄 증명. 그 외 224 passed,
  2 skipped. 오버라이드 재서술 4건(`bonding_log`·`core_usage_map`·`dt_core_view`·
  `dt_log`)이 남았고 새 검증기가 운영자에게 삭제를 말하는 상태.
- `9f4fc3b`: `test_map_alignment.py` 단독 55 / 병행 15 실패의 순서 의존 공유 상태가
  남았다(HEAD 모듈 주입으로 이 레인 것 아님 확인). 그룹 읽기는 필터·캡 없이 층 표
  전체 스캔(24,749행에 5.0 ms, 선형) — `b510df2`의 설계 그대로, 먼저 부러질 축.
