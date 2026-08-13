# 🧪 제안서 — 결함(void·defect) 정준 스키마

> **Status:** 🔵 제안 · 판정 대기 | **작성 2026-08-12** | **소유: 총괄**
> 규칙 준거: [SCHEMA_CANON](SCHEMA_CANON.md) · 어휘 정합: [CANONICAL_LEDGER_DESIGN](CANONICAL_LEDGER_DESIGN.md)
>
> **구현 0.** 이 문서는 판정을 받기 위한 것이고, 승인 전에는 DDL이 나가지 않는다.

---

## 0. 먼저 잰 것 — 이게 그린필드인지부터

| 사실 | 값 |
|---|---|
| 선언된 19개 테이블 중 **defect·void·grade·yield 컬럼** | **0개** |
| `enrichment_rules.json`의 "void" | **오탐** — 산문 속 `avoid` |
| 기존 본딩 셀 기록 | `bonding_log` — `bond_cell_key`(업무키) · `bond_lot/slot/x/y` · **`dt_lot/slot/x/y`** · `b_bn` · `stack_height` · `bond_eqp` · `event_time` |
| 기존 패키지 기하 | `bonding_map` — `pkg_id`(업무키) · `base` · `x` · `y` · `leg` |

**결함 데이터는 완전한 그린필드다.** 그러나 **`bonding_log`가 이미 dt→bond 연결을 셀 단위로
들고 있고**, `stack_height`라는 **계측값 컬럼의 전례**가 이미 있다.

🔴 **그리고 이 저장소가 스스로 적어 둔 도메인 사실이 설계를 지배한다** (`enrichment_rules.json`):

> `bonding_log`의 `(dt_lot, dt_slot)`은 **본딩 시점의 값**이고 `dt_log`의 것은 **DT 시점의
> 값**이다. 그 사이 split/merge가 웨이퍼를 옮겼으므로 **순진한 조인은 에러가 안 나고
> «그럴듯하게 틀린 웨이퍼»를 맞춘다.**

⇒ **결함의 위치는 좌표 튜플이 아니라 «발급된 신원»에 붙어야 한다.**

---

## 1. 설계를 정하는 질문은 하나다 — 「0」을 어떻게 적을 것인가

가장 쉬운 안은 `bonding_log`에 `void_yn`·`void_area`를 붙이는 것이다. **그 안을 기각한다.**

| 상태 | 컬럼 방식 | 관측 테이블 방식 |
|---|---|---|
| 검사했고 **깨끗함** | `void_yn = false` | `inspection_run` 있음 + `defect_obs` 없음 |
| **검사 안 함** | `void_yn = false` 🔴 | `inspection_run` 없음 |
| 검사했고 결함 3개 | `void_area = ?` (3개인데 한 칸) | `defect_obs` 3행 |

🔴 **컬럼 방식은 「검사 안 함」과 「깨끗함」을 구별할 수 없다.** 둘 다 `false`다.
이 프로젝트는 이미 같은 모양에 당했다 — 「없어서 0」을 「무해해서 0」으로 읽고 사용자의
정답 진단을 기각한 적이 있다. **수율은 분모가 있어야 계산된다**: 「보이드 3개」는
「검사한 12자리 중」이 없으면 뜻이 없다.

⇒ **검사 자체를 기록한다.** 그것이 분모다.

---

## 2. 제안 — 테이블 셋 + 어휘 넷

```
inspection_run   검사가 «일어났다»            ← 분모
      │
      └─< defect_obs      그 검사가 «무엇을 어디서» 봤다
                │
                └─< defect_measure   그 결함의 «얼마»  (좁은 행)
```

### 2-1. `inspection_run` — 분모

| 컬럼 | 타입 | 근거 |
|---|---|---|
| `run_uid` | text | 발급 신원 |
| `subject_kind` | text (어휘) | `bond_cell` · `die` · `wafer` · `package` |
| `subject_key` | text | **그 대상의 업무키**(예: `bond_cell_key`) |
| `method` | text (어휘) | `xray` · `sat` · `aoi` · `visual` |
| `recipe_id` | text | 🔴 **임계값이 다르면 같은 물건이 다른 판정을 받는다.** 5% 레시피의 「깨끗함」과 10% 레시피의 「깨끗함」은 다른 사실 |
| `eqp_id` | text | 어느 장비가 봤나 |
| `observed_at` | **timestamptz** | **검사 시각.** 적재 시각 아님 (R5) |
| `source_event_uid` | text | 출처 |

### 2-2. `defect_obs` — 관측

| 컬럼 | 타입 | 근거 |
|---|---|---|
| `defect_uid` | text | 발급 신원 |
| `run_uid` | text | 어느 검사가 봤나 |
| `defect_kind` | text (어휘) | `void` · `crack` · `delamination` · `particle` · `tilt` … |
| `locus` | text | 대상 «안»의 자리(보이드가 다이 어느 구역인지). 없으면 NULL |
| `rank` | int | 같은 검사가 여럿 볼 때의 순번(면적 내림차순 등) |

`subject_*`를 여기 두지 않는 이유: **검사가 대상을 정하고 결함은 검사에 속한다.**
같은 사실을 두 곳에 두면 어긋난다.

### 2-3. `defect_measure` — 좁은 계측

| 컬럼 | 타입 |
|---|---|
| `defect_uid` | text |
| `measure` | text (어휘) — `void_area_ratio` · `void_count` · `max_void_dia` · `crack_len` |
| `value_num` | double precision |
| `unit` | text (어휘) — `%` · `um2` · `um` |
| `value_text` | text — 등급(`A`/`B`) 같은 범주값 전용, 아니면 NULL |

### 2-4. 어휘 넷은 **컬럼이 아니라 행**

`defect_kind` · `method` · `measure` · `unit`. **새 결함 종류가 마이그레이션이 아니라
INSERT다.** 오늘 `dt_map` 키 이주를 막은 것이 정확히 스키마 결합이었다.

---

## 3. 왜 「종류마다 컬럼」이 아닌가 — 세 안 비교

| 안 | 문제 |
|---|---|
| ⓐ 종류별 타입 컬럼 (`void_area`, `crack_len`, …) | **어휘가 자라면 스키마가 자란다.** 컬럼 하나가 config·매퍼·enrichment·참조뷰·그리드로 연쇄한다 — 오늘 실측된 결합 |
| ⓑ JSONB 한 칸 | 타입 없음·질의 불가. 이 저장소가 **이미 두 번 당했다** — `dt_inventory.dt_frame` 타입 모호(체인은 JSON, enrichment는 문자열, 실패 시 조용히 `continue`), `grid_metadata`를 쉼표로 잘라 **없는 컬럼 `grid_rows`를 만들어 냄** |
| **ⓒ 좁은 계측 행** ✅ | 값은 타입이 있고, **단위가 선언되고**, 질의 가능하고, 어휘는 데이터로 자란다 |

ⓒ가 **단위 문제까지 푼다.** 보이드 면적을 `%`로 적는 팀과 `um2`로 적는 장비가 공존하는 것이
팹의 실제 모습이고, 단위 없는 숫자 컬럼은 그걸 **조용히 섞는다**.

---

## 4. 🔴 정직한 비용 셋 — 팔지 않는다

### 4-1. `subject_key`는 **제약 없는 다형 참조**다

FK가 없다. 아무것도 강제하지 않는다. **이것이 `SCHEMA_CANON` R6의 함정 그 자체다** —
표식이 열쇠 노릇을 한다.

**완화**: 쓰기 시점 게이트. 미선언 `subject_kind`, 존재하지 않는 `subject_key`는
**문 앞에서 거절하고 «센다»**. 조용한 건너뛰기 금지 — 오늘 착지한 `chain_key_gate`와
같은 모양이고 같은 이유다.

### 4-2. 좌표로 조인하면 **그럴듯하게 틀린다**

§0의 도메인 사실 때문에 `subject_key`는 **발급된 키**(`bond_cell_key`)여야 하고
`(bond_lot, bond_slot, x, y)` 같은 **좌표 튜플이면 안 된다.** 좌표는 시점에 따라 다른
물건을 가리킨다.

### 4-3. `bonding_log` ↔ `bonding_map`에 **공유 키가 없다**

`bonding_log`는 셀 단위(`bond_cell_key`), `bonding_map`은 패키지 단위(`pkg_id`).
**둘을 잇는 컬럼이 오늘 없다.**

> 🔴 **원장 설계의 「패키지 뷰(12칸 격자)」는 이 링크 없이는 못 만든다.**
> 이건 설계 선택이 아니라 **발견**이다. 셀→패키지 연결을 어떻게 얻는지 판정이 필요하다.

---

## 5. 판정 필요 — 넷

| # | 질문 | 왜 총괄이 못 정하나 |
|---|---|---|
| 1 | **셀 → 패키지 링크를 무엇으로 얻나** | 데이터에 없다. 본딩 장비가 주는지, 규칙으로 유도하는지는 현장 사실 |
| 2 | **보이드 계측의 실제 이름과 단위** | `void_area_ratio`가 `%`인지 `um2`인지, 장비가 무엇을 주는지 |
| 3 | **검사가 셀 단위인가 패키지 단위인가** | X-ray가 패키지 한 장을 찍고 12자리를 한 번에 판정할 수 있다. 그러면 `subject_kind='package'` + `locus`로 자리를 적는다 |
| 4 | **fab/dt 결함도 같은 테이블인가** | 제안은 「예」(대상만 다름). 형제 교집합 질문이 층을 건너므로 나누면 UNION이 된다 |

**2·3은 샘플 파일 한 장이면 답이 나온다.** 실제 검사 출력 한 건을 주시면 어휘를 데이터에서
읽어 채우겠다 — 이름을 지어내지 않는다.

---

## 6. 착수하면 이 순서다 (승인 전 실행 없음)

1. 어휘 넷 + 게이트 (거절을 «세는» 것까지가 1단계)
2. `inspection_run` + `defect_obs` + `defect_measure`, 시간 파티션은 **첫날부터**
   (나중에 붙이면 스키마 재작성인 것이 본 세션에서 실측됨)
3. 샘플 검사 파일 1종 인제션 → 실데이터로 어휘 확정
4. 읽기 하나: **「이 셀의 결함」** — 화면에 붙기 전에는 완료가 아니다

**§5의 1번(셀→패키지)이 안 풀리면 3단계까지만 간다.** 패키지 뷰는 그 링크 위에 선다.
