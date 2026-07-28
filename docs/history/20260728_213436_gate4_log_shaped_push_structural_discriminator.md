# 관문 4 — 컬럼을 지킬지 버릴지는 config가 아니라 **구조가 답한다**

> 커밋 `deed6d2` · 2026-07-28 21:34 · 도메인 Client(맵 에디터 push 관문) + Server(`/schema` 선언 서빙)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) · 선언: [table_config](../guide/config/table_config.md)
> **동반 항목** (같은 커밋의 다른 세 단락): [self-frame 유령 형제](./20260728_213700_self_frame_fail_count_only_sibling.md) · [replace_map 정직한 범위](./20260728_213900_replace_map_honest_scope_400_over_noop.md) · [PM 헌장 등재](./20260728_214100_pm_charters_gain_ops_docs.md)

## 배경 — dt_log의 256행은 OK 한 번 거리에 있었다

로그형 테이블(`dt_log`)을 맵으로 **열어 보는 것**은 정상 흐름이다 — 좌표와 값이 있으니
오버레이 소스로 잘 동작한다. 문제는 그 화면에서 ⚡ Push를 누르는 순간이다. Push는
`replace_map`(범위 내 전량 삭제 후 재기록)이고, 페이로드는 (맵 키, x, y, val)만 실어
나르므로, 맵 계약 밖의 실데이터 컬럼 — `dt_id`, `eventtime`, 코어 lot/slot, 장비 컬럼 —
은 교체된 모든 행에서 NULL이 된다. 2026-07-28 실측에서 dt_log의 실로그 256행이
확인창 하나 뒤에 있었다. 기존 세 관문(zone 컬럼 부재 / legacy 판독 불가 / 잘라먹는
push의 화면−페이로드 차집합)과 같은 가족 — "직렬화하지 않은 데이터를 지우는 쓰기를
막는다" — 의 네 번째 구성원이 필요했다.

## 판별자 — "페이로드나 서버가 그 컬럼을 재구성할 수 있는가"

이 커밋의 핵심 통찰은 분류에 **config가 필요 없다**는 것이다. 어떤 컬럼이 push를
살아남는지는 이름 목록이 아니라 구조가 답한다: **페이로드가 싣거나 서버가 재구성하는
컬럼만 살아남는다.**

```js
// map_editor.js — getUnprotectedPushColumns, 이 커밋 시점
const covered = new Set([
  ...(schema.map_key_columns || []),   // push가 상수로 다시 쓰는 맵 범위
  xCol, yCol, valCol,                  // 페이로드가 싣는 좌표·값
  ...PUSH_SYSTEM_COLUMNS               // 서버가 스스로 관리
]);
const bk = schema && schema.business_key;
const src = Array.isArray(schema && schema.composite_key_source) ? schema.composite_key_source : [];
if (bk && src.length > 0 && src.every(c => covered.has(c))) covered.add(bk);
return cols.filter(c => !covered.has(c));
```

같은 business_key라도 운명이 갈린다: `bonding_map`의 `pkg_id`는
`composite_key_source`(base_x_y)에서 **쓰기마다 서버가 재계산**하므로 페이로드에 없어도
살아남고, `dt_log`의 `dt_id`는 합성 원천이 비어 있어 행별 정체성 그 자체 — 재구성 불가,
따라서 보호 대상이다. 명목(이름) 분류였다면 테이블마다 선언을 관리해야 했을 것을,
구조 판별이 이미 있는 스키마 필드 두 개로 끝냈다.

부수 정리: 종전 메타데이터 입력 폴백이 갖고 있던 별도의 시스템 컬럼 목록을
`PUSH_SYSTEM_COLUMNS` 하나로 합쳤다 — 같은 질문("이 컬럼은 시스템 것인가")에 목록이
둘이면 언젠가 서로 다른 답을 낸다.

## 거절이 기본, 완화는 사이트 선언으로

관문은 **모든 다이얼로그보다 앞**에서 발화한다 — 허용될 수 없는 push에서 사용자가
질문에 하나라도 답하게 하지 않는다. 거절문은 파괴될 컬럼명을 명시한다.

단 하나의 예외 경로가 있다: R&D 수동 계측 덮어쓰기처럼 로그형 테이블로의 에디터 push가
**알려진 흐름**인 사이트는 table_config에 `map_push_ok: true`를 선언한다. 선언 시 차단이
소실 컬럼명을 명시한 확인창 1회로 완화되고, 양산 전환 시 선언을 제거하면 다시 잠긴다.

```python
# main.py — /schema, 이 커밋 시점. std_parse와 같은 규율:
# 문자열 "true"/"false" 오타가 파괴를 해제하지 못하도록 JSON boolean만 유효.
"map_push_ok": config.get("map_push_ok") is True
```

클라이언트도 `=== true`로 대칭 — 선언 오타는 양쪽 어디서도 잠금을 풀지 못한다.
깨끗한(맵 계약과 일치하는) 테이블에 선언이 있어도 아무 일도 일어나지 않는다
(`extras`가 비면 관문 자체가 무마찰).

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 관문 판정 | `push_gate_harness.mjs` — vm으로 소스에서 **pushMapData가 실행하는 바로 그 판정 함수**를 추출해 실서빙 스키마 픽스처로 실행 | 15/15 |
| 퀵 QA | 격리 스택에서 4 시나리오 + SQL로 dt_log **0건 쓰기** 증명 | 4/4 |
| 전체 스위트 | conda `assy_manager` | 893 passed |

## 그때 남아 있던 것

- 관문은 **클라이언트에만** 있었다 — 서버의 `replace_map` 자체는 어떤 호출자가 보내든
  로그형 테이블을 여전히 교체했다. 서버가 이 판별을 스스로 하지는 않는 상태였다.
- `map_push_ok`를 실제로 선언한 테이블은 이 커밋 시점 없었다 — 선언은 R&D 사이트
  전환 시점의 도구로 준비된 상태였다.
