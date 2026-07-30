# `virtual_join_rules.json` 세팅 — 저장하지 않는 조인(virtual join) 선언

> **Status:** 🟢 Living | **Last-verified:** 2026-07-31 (**신설** — 팬아웃 가드 착지. 선언 스키마 + 로드 시점 거부 + `GET /admin/config/resolve?domain=virtual_join`. ⏳ **조인 실행 코드는 아직 없다** — 이 파일은 선언과 그 검증만 다루며, 유효한 선언도 보고서에서 `ineffective`로 나온다) | **Owner:** Backend / 총괄
> 상위: [폴더 인덱스](./README.md) · 절차 요약은 [CONFIG_GUIDE §1](../CONFIG_GUIDE.md) · 검증기 정본은 `server/virtual_join_config.py`

<!-- Loader evidence (2026-07-31):
  load/validate: server/virtual_join_config.py load_virtual_join_rules (missing -> [], no rejection),
    validate_virtual_join_rules (root must be object), _validate_join (per-declaration),
    static fan-out guard: key_is_covered + declared_key_columns,
    live half: unique_index_covering / probe_duplicate / verify_uniqueness / load_verified_rules
  report: server/config_resolve_report.py _resolve_virtual_join (DOMAIN_VIRTUAL_JOIN), zero DB queries
  tests: server/tests/test_virtual_join_guard.py (38)
  measurements behind every number here: read-only against the live DB, 2026-07-31
-->

## 1. 무엇인가

두 테이블을 **저장하지 않고 조회 시점에** 잇는다. `/api/maps/overlay`가 좌표로 하는 일의
행(row) 버전이고, 잇는 기준은 좌표가 아니라 선언된 조인 키다.

분석가는 REST API로 두 테이블을 Spotfire에 끌어와 거기서 잇는다. DB 뷰를 만들지 않는
이유가 그것이다 — 서빙 계층은 API다.

## 2. 가장 중요한 규칙 — 터지는 선언은 로드되지 않는다

조인 키가 **오른쪽 테이블의 행 하나를 지목**해야 한다. 지목하지 못하는 선언은 유효 규칙
목록에 들어가지 않는다. 문법도 맞고 컬럼도 존재하는 선언이라 이 검사가 없으면 거부할
자리가 없다 — 실행해 봐야 드러난다.

실측 (2026-07-31, 운영 DB read-only):

| 선언 | 왼쪽 행 | 조인 결과 | 배율 |
|---|---:|---:|---:|
| `core_defect_map ⋈ eds_fail_map (lot,slot,x,y)` | 103,040 | 103,040 | x1 |
| `core_defect_map ⋈ eds_fail_map (lot,slot)` | 103,040 | **132,715,520** | **x1288** |
| `bonding_log ⋈ wafer_process (lot,slot)` | 14,436 | **2,552,624** | **x177** |
| `bonding_log ⋈ core_wafer_map (core_lot,core_slot)` | 14,436 | 14,436 | x1 |

**맵 정체성(lot/slot)으로 이으면 맵의 셀 수만큼 곱해지고, 칩 정체성(lot/slot/x/y)으로
이으면 곱해지지 않는다.** 두 선언은 컬럼 두 개 차이인데 결과는 10만 행과 1억 3천만 행이다.

판정 기준: 오른쪽 테이블이 `table_config`에 선언한 행 정체성
(`composite_key_source`, 없으면 `business_key`)이 **조인 키의 부분집합**인가.

## 3. 「미상」의 정의 — 경계 계약

조인 결과에서 `unresolved_label`(기본 `미상`)은 **두 경우를 모두 덮는다**:

1. 오른쪽에 맞는 행이 **아예 없다**.
2. 맞는 행은 **있는데 그 값이 비어 있다**(NULL 또는 빈 문자열).

②를 빼면 안 되는 이유는 실측이다. `bonding_log → core_wafer_map.wafer_id`는
**14,436행 전부가 오른쪽 행을 찾는다** — 그런데 3,792행(26.27%)의 `wafer_id`가 비어 있다.
`core_defect_map → core_wafer_map.wafer_id`는 103,040행 전부가 행을 찾고 88,872행(86.25%)이
비어 있다. LEFT 조인만으로는 이 26%와 86%가 「값이 있다」로 읽힌다.

INNER 조인은 ①을 조용히 지우므로 쓰지 않는다.

## 4. 키 사전

| 키 | 필수 | 뜻 |
|---|---|---|
| `left_table` | ✅ | 왼쪽(구동) 테이블. `table_config`에 등록돼 있어야 한다 |
| `right_table` | ✅ | 오른쪽(참조) 테이블. 등록 + 행 정체성 선언 필요 |
| `join_key` | ✅ | `{left, right}` 쌍의 목록. 같은 `right` 컬럼을 두 번 묶을 수 없다(키가 넓어 보이지만 고정하는 성분은 하나라 덮임 판정이 거짓 통과한다) |
| `expose` | ✅ | 왼쪽에 붙여 보여줄 오른쪽 컬럼들. 왼쪽에 **같은 이름이 있으면 거부** — 어느 쪽 값인지 알 수 없는 표가 된다. 상한 32개 |
| `unresolved_label` | | 기본 `미상`. §3의 두 경우를 모두 덮는다 |
| `enabled` | | 기본 `true`. `false`는 오류가 아니라 조용한 제외 |
| `join_cardinality` | | `"one"`만 지원. 집계 형태는 **구현이 없어** 선언하면 거부된다(§6) |

## 5. 유일성의 근거는 두 겹이고, 한 겹은 공짜가 아니다

**① 정적 구조 검사** — 항상 · DB 접근 0회. §2의 부분집합 판정.
**필요조건이지 충분조건이 아니다.**

**② 라이브 유일성 검증** — 세션이 있을 때만(`load_verified_rules`).

①만으로 부족하다는 것은 실측이 증명한다. `business_key_val`에는 **UNIQUE 제약이 없고**
(평범한 btree 2개뿐) dedup 업서트는 규약일 뿐 DB가 강제하지 않는다. 운영 DB의 실제 상태:

| 테이블 | 선언 키 | 중복 그룹 | 중복 행 | 최대 행/키 |
|---|---|---:|---:|---:|
| `bonding_map` | `base+x+y` | 2,312 | 4,645 | 10 |
| `inventory_master` | `part_no` | 164 | 427 | 101 |
| `bonding_log` | `log_id` | 117 | 234 | 2 |
| `wafer_process` | `proc_id` | 43 | 86 | 2 |

`bonding_map`은 ①을 **통과**하지만 실제로는 10배 팬아웃한다. 그래서 ②가 별도로 있다.

### 증거 등급

| 등급 | 뜻 | 보장 범위 |
|---|---|---|
| `unique_index` | UNIQUE 인덱스가 조인 키를 덮는다 | **영구** — 이후 어떤 쓰기도 깨지 못한다 |
| `probe_clean` | 프로브가 완주했고 중복이 없었다 | **그 시점의 스냅샷** — 나중에 들어온 행이 깨뜨릴 수 있다 |
| `unverified` | 정적 검사만 통과 | 없음 |

### 프로브에 예산이 붙는 이유

중복을 **찾는** 방향은 첫 중복에서 멈춰 싸다(실측 1.0ms / 2.5ms / 351ms).
중복이 **없음을 증명하는** 방향은 전수 스캔이다 — 실측 103,040행에 약 120ms(859행/ms).
같은 속도로 **1,000만 행이면 약 11.6초**이고 정렬이 디스크로 넘친다(337k행에서 이미
temp write 881블록 관측).

그래서 프로브는 `statement_timeout` 예산(기본 2,000ms) 안에서만 돌고, 예산이 다하면
「깨끗하다」가 아니라 **「증명하지 못했다」**로 답하며 그것은 거부다.

> 🔴 **큰 테이블에서 영구히 통과시키는 방법은 예산을 올리는 것이 아니라 조인 키에
> UNIQUE 인덱스를 만드는 것이다.** 예산을 올려도 `probe_clean`은 스냅샷일 뿐이다.
> 인덱스 생성은 **운영자의 DDL**이며 이 로더의 권한 밖이다.

## 6. 왜 「집계 형태」 스위치가 열려 있지 않은가

x1288 조인이 언제나 틀린 것은 아니다 — **행 조인으로서** 틀렸다. 집계 형태
(오른쪽을 먼저 접고 잇기)는 정당할 수 있다.

그래도 `join_cardinality: "many"`는 지금 **거부**된다. 유일성 검사를 끄는 스위치는 그것이
향할 안전한 경로가 생긴 뒤에 열려야 하기 때문이다. 지금 열어 두면 처음 거부를 만난
운영자가 그 스위치를 켜고 1억 3천만 행 조인을 얻는다. 스위치가 조용히 허용이 아니라
**이름 있는 거부**인 것은 그래서다.

## 7. 확인하는 법

```bash
curl -H "X-Admin-Token: <토큰>" "http://localhost:8080/admin/config/resolve?domain=virtual_join"
```

- `rejected` — 거부된 선언 + 사유. 팬아웃 3종은 `scope_unresolved`(조인 키가 행 하나를
  고르지 못함), 문법·미구현 형태는 `mapping_unavailable`.
- `ineffective` — ①을 통과한 선언. ⏳ **조인 실행 코드가 아직 없어 전부 여기 있다**
  (`not_reached`). 통과를 `effective`로 표기하면 운영자가 조인이 동작한다고 읽는다.
- `settings` — 프로브 예산과 `미상` 표시의 실효값.

> 사유 어휘는 **닫혀 있다**(4단어). 새 단어를 만드는 것은 계약 변경이며
> `contracts/config_resolve_report/vectors.json` + node 하네스를 함께 고쳐야 한다.

## 8. 함정

- **선언 키가 없는 테이블은 어떤 조인 키로도 통과하지 못한다.** `composite_key_source`도
  `business_key`도 없으면 그 테이블은 행 하나를 지목한다고 **주장할 근거**가 없다.
- **`expose`가 왼쪽 컬럼을 가리면 거부된다.** 이름이 겹치면 표에서 어느 쪽 값을 보고 있는지
  알 수 없다.
- **밑줄로 시작하는 키는 선언이 아니라 주석이다**(`_comment` 등) — 조용히 건너뛴다.
- **파일 부재는 거부가 아니다.** 선언이 없을 뿐이며 `sources[].exists: false`로 나온다.
