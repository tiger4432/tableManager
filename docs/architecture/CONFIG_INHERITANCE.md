# CONFIG 상속 지도 — 무엇이 무엇에서 오고, 무엇이 무엇을 이기는가

> **측정 시각:** 2026-08-16 (이 박스 `assy_manager` 개발 사본, 읽기 전용).
> **측정 방법:** 재구현 없이 **제품의 실제 해석기를 그대로 호출**했다 —
> `bonding_plan.explain_binding_refusal` · `map_overlay.resolve_binding_parts` ·
> `chain_bindings.resolve_column` ·
> `transfer_plan.dry_run` · `config_resolve_report.resolve_report(["binding"])`.
> 재현 절차는 §7.
>
> ⚠️ **`server/config/*`는 gitignore다.** `Grep`을 그 디렉터리에 걸면 라이브 파일이
> **통째로 안 보이고 `.sample`만** 뜬다. 이 문서의 모든 config 사실은 **파일을 이름으로
> 지목해 읽어** 얻었다. 이 함정으로 2026-08-14에 틀린 보고가 한 번 나갔다.
>
> ⚠️ **이 문서의 §5(틀린 선언 전수)는 «이 박스의 config 상태»다.** 규칙(§2~§4)은 코드에서
> 오므로 어느 환경에서나 참이지만, §5는 환경마다 다르다. 다른 박스에서는 §7의 절차를
> **다시 돌려야** 한다.

---

## 0. 이 문서를 만들게 한 질문과, 지시와 어긋난 사실 셋

제품 소유자의 질문은 **「이런 거 상속 안 되나?」**였다. 답은 **「된다. 단, 되는 자리가
정해져 있고, 오늘 고친 자리는 그중에 없다」**이다.

착수 지시에 사실과 어긋나는 것이 셋 있었다. 규칙보다 먼저 놓는다.

### ① `bonding_plan_config.json`의 `"x":"x"`는 «틀린 철자가 아니다»

지시는 이것을 `transfer_plan_config`와 **같은 자리표시자 사고**로 봤다. 아니다.
`core_defect_map`과 `eds_fail_map`은 **실제로 `x`, `y`, `val`이라는 이름의 컬럼을 갖고
있다**(물리 스키마 실측). 철자는 맞다.

그 자리의 진짜 문제는 다르고 **더 크다**: 그 두 테이블과 `wafer_process`가
**`table_config.json`에 아예 선언돼 있지 않다.** 해석기는 컬럼 이름을 보기 **전에**
테이블에서 멈춘다(`bonding_plan.py:644-650`). 그래서 M1 core-summary의 소스 **다섯 개가
전부** 거절된다 — 자세한 것은 §5.1.

### ② 그 `x`/`y`/`val`은 «지워도 상속되지 않는다»

`__bin_map_comment`의 규칙(「지우면 유도가 메운다」)은 **참이지만 조건부**다. 파생은
호출부가 그 역할을 **`required`로 요구할 때만** 일어난다(`bonding_plan.py:568-569`).
그런데 `bonding_plan`의 세 호출부는 전부 `required=("lot","slot")`이다
(`bonding_plan.py:840` · `:939` · `:972`). **x/y/val은 거기 없다.**

즉 그 자리에서 `"x":"x"`를 지우면 좌표는 **상속되는 게 아니라 그냥 사라진다.**

### ③ 오늘 `transfer_plan_config.json`에 한 수리는 «동작을 바꾸지 않았다»

`stages.bonding.source.total_chips`에서 `"x":"x","y":"y"`를 지운 수리를, 실제 해석기에
세 가지 버전을 먹여 대조했다.

| 선언 | 해석 | 그 자리가 보는 것 | 영역·BIN 총계 |
|---|---|---|---|
| **수리 전** `x:"x", y:"y"` | 해석됨 | `cols=[lot,slot]`, `unresolved=[x,y]` | **null** |
| **수리 후**(삭제) | 해석됨 | `cols=[lot,slot]`, `unresolved=[]` | **null** |
| `x:"dt_x", y:"dt_y"` 선언 | 해석됨 | `cols=[lot,slot,x,y]` | **계산됨** |

`transfer_plan.py:2179`의 관문이 `"x" in cols and "y" in cols`라서, 수리 전에도 후에도
`total_pts = None`이다. **바뀐 것은 상태 문자열 하나뿐이고, 그 방향이 나쁘다** —
수리 전에는 `connected(column_unresolved:x,y)`라서 화면이 「뭔가 안 풀렸다」고 말했는데
(`transfer_plan.py:1710`), 수리 후에는 그냥 `connected`다. **아무것도 고쳐지지 않은 채
경고만 사라졌다.**

이 자리에서 좌표를 되살리는 방법은 둘뿐이다.
- **config로:** `"x": "dt_x", "y": "dt_y"`를 **명시 선언**한다(여기선 삭제가 상속을 부르지 않는다).
- **코드로:** 그 호출부의 `required`에 x/y를 넣는다 — 이건 «없으면 count-only»라는
  현재 계약을 바꾸는 것이므로 총괄 판정이 필요하다(§6-D).

---

## 1. 이 문서의 자리 — 왜 `docs/architecture/`인가

- `docs/guide/config/<파일>.md`는 **파일 한 장당 한 페이지**로, 「이 파일을 어떻게 세팅하나」를
  다룬다. 파일 **사이의** 우선순위를 거기 쓰면 같은 문장을 열네 번 복제해야 하고, 복제된
  규칙은 갈라진다(이 프로젝트가 반복해서 지불한 비용이다).
- `docs/guide/CONFIG_GUIDE.md`는 **어느 페이지를 열지 알려주는 색인**이다. 규칙의 집이 아니다.
- `docs/architecture/`에는 이미 **여러 파일을 가로지르는 규칙 문서**가 산다 —
  `SCHEMA_CANON.md`(스키마 여덟 규칙 + 탐지기), `INDEX_POLICY.md`, `PRIMITIVES.md`,
  `DUPLICATION_LEDGER.md`. 이 문서는 정확히 같은 장르다: **규칙 + 탐지기 제안**.

그래서 `docs/architecture/CONFIG_INHERITANCE.md`.

---

## 2. config 전수 — 무엇을 선언하고, 누가 읽고, 언제 읽는가

### 2.1 라이브 파일 (실제로 도는 것)

| 파일 | 무엇을 선언하는가 | 대표 읽는 자리 | 언제 읽히는가 |
|---|---|---|---|
| **`table_config.json`** | 동적 테이블의 **정본** — 테이블 목록, `column_types`, `business_key`, `composite_key_source`, `display_columns`, `map_key_columns` | `crud.py` 로더 · `main.py` · `run_watcher.py` · `run_chain_worker.py` | **기동 시 싱글턴** + 파일 감시 리로드(1초 디바운스). ⚠️ **감시되는 파일은 이것 하나뿐** |
| **`map_overlay_config.json`** | 맵 좌표·값·정체성 바인딩의 **예외 선언**(`table_bindings`), 기본 legend, 값컬럼 후보, paint_lock, 정렬 임계값 | `map_overlay.py:89` 로더 · `main.py:4701,5005,5056,5081,5113` · `bonding_plan.py:506` | **호출마다 디스크 재읽기**. 단 `bonding_plan`만 **(mtime_ns, size) 메모**(`bonding_plan.py:518-524`) |
| **`transfer_plan_config.json`** | M2 전사 단계(stage) 선언 — 소스/타깃 종류, `source_config_ref`, `bin_map`, `target_map.preset`, `plan_store` | `transfer_plan.py:282` 로더 · `main.py:5141,5166,5206,5249` | 호출마다 재읽기, **요청당 1스냅샷** |
| **`bonding_plan_config.json`** | M1 코어 요약 소스 — `defect`/`eds_fail`/`total_chips`/`used_chips`/`process_history`, `map_metadata`, `core_identity` | `bonding_plan.py:79` 로더 · `main.py:4659` · `transfer_plan.py:419,2271,3547` | 호출마다 재읽기 |
| **`chain_rules.json`** | 체인 인제션 규칙 — `trigger_table`→`target_table`, 매퍼 모듈/함수, 컬럼 바인딩 키 | `chain_ingestion_worker.py:307` 로더 · `:1294`(기동) · `:1381`(SYSTEM_RELOAD) | **워커 기동 시 고정**. `POST /admin/reload-configs`가 발행하는 `SYSTEM_RELOAD` outbox 행으로만 갱신 |
| **`enrichment_rules.json`** | 파생/확정 규칙 — `source_table`→`derived_table`, `decision_key`, `target_fields`, `aggregations`, `reference_views` | `enrichment_config.py:550,573` · `main.py`(6곳) · `retroactive.py:428` | **호출마다 재읽기**(모듈 캐시 없음) |
| **`virtual_join_rules.json`** | 가상 조인 — `left_table`/`right_table`/`join_key`/`expose`. **`_`로 시작하는 키는 무시**(`virtual_join_config.py:411`) | `virtual_join_config.py:424,606` · `virtual_join_executor.py:128` | **TTL 5초 캐시**(`virtual_join_executor.py:86`). `/admin/reload-configs`가 즉시 무효화 |
| **`ingestion_settings.json`** | 인제션 스위치 — `archive_processed_files`, `dedup_by_path_stat`, heavy 임계값, 읽기 상한 | **로더가 넷, 각자 독립**: `directory_watcher.py:248` · `enrichment_config.py:133` · `enrichment_candidates.py:239` · `map_meta_registrar.py:96` | 호출마다 재읽기 — 「다음 파일부터」 적용 |
| **`maps.json`** | 웨이퍼 프리셋 기하 — `phys_wafer_dia`, `phys_chip_x/y`, `rotation`, `side` | `main.py:4545` 로더/기록기 · `map_preset_routing.py:261,318` | **API가 읽고 쓴다**(손으로 편집하는 파일이 아니다) |
| **`auto_update_control.json`** | 자동 갱신 스크립트 **비활성 목록** | `utils/auto_update_control.py:55` · `run_auto_update.py:530,606` · `main.py:5898` | 양쪽 다 호출마다 재읽기 — **재기동 없는 토글이 설계 의도** |
| **`ledger_config.json`** | 정준 원장 번역기 — `occurred_at_column`, `subject_types`, `vocabulary`, `slot_pairing` | `ledger/config.py:96` 로더 → **`ledger/backfill.py:408`이 유일한 호출자** | 실행(run)당 1회. ⚠️ **다섯 프로세스 중 아무도 읽지 않는다** — CLI 전용 |
| **`scheduler_status.json`** | (설정 아님) 자동 갱신 스케줄러의 **런타임 상태** | 기록 `run_auto_update.py:525` / 읽기 `main.py:5887` | 서버가 **쓰는** 파일. `config_backup.py:114-117`이 스냅샷에서 제외 |
| **`supervisor_status.json`** | (설정 아님) 프로세스 수퍼바이저 **런타임 상태** | 기록 `process_supervisor.py:1100` / 읽기 `health.py:141` | 5초마다 갱신, 스냅샷 제외 |

### 2.2 라이브 파일이 없는 것들 — «없을 때 어떻게 되는가»

**파일 부재 자체가 상속의 한 형태**이고, 네 갈래로 갈린다 —
①내장 기본값 ②기능이 조용히 꺼짐 ③다음 우선순위로 폴백 ④에러.
**어느 갈래인지 모르고 파일을 지우면 ②를 ①로 착각한다.**

| 파일 | 부재 시 | 근거 |
|---|---|---|
| `audit_history_config.json` | **내장 기본값**으로 완전 동작(`default_limit` 200, `max_limit` 1000) | `audit_history.py:76,109-110` |
| `effort_metric.json` | **내장 기본 가중치**로 동작 | `effort_metric.py:60` |
| `suggest_config.json` | **내장 기본값**으로 동작 | `value_suggest.py:120` |
| `notation_rules.json` | **기능이 조용히 꺼진다** — 정규화 0건, 조인이 원시 값 비교(기능 도입 전과 동일) | `notation_norm.py:613-614,640-646` |
| `database.json` | **다음 우선순위로 떨어진다**: `env DATABASE_URL` > 이 파일 > `DEFAULT_PG_URL`. ⚠️ **env가 파일을 이겨야 한다** — 격리 스택이 config 트리를 통째로 복사하기 때문 | `paths.py:146-165` |
| `siblings_axes.json` | **`.sample`로 폴백**한다. 둘 다 없으면 **에러**(조용한 0이 아니다) | `ledger_siblings.py:318-322` |
| `finding_kinds.json` | **`.sample`조차 없고 「없는 것이 정상」인 유일한 파일.** 정본은 코드의 `DEFAULT_FINDING_KINDS`이고, 파일이 있으면 **종류 단위 얕은 병합으로 덮어쓴다**. 깨졌으면 조용히 기본값으로 안 떨어지고 `FindingKindError`로 **거절**한다 | `finding_kinds.py:78,99,118-151` |

`ledger_config.json`도 같은 `.sample` 폴백을 갖는다(`ledger/config.py:105-108`) — 이 박스엔
라이브 파일이 있어 폴백이 안 걸린다.

> 🔴 **`/admin/reload-configs`는 이름보다 좁다.** 갱신 대상은 동적 모델
> (table_config), `virtual_join_executor` 캐시, `notation_norm` 캐시,
> 그리고 `mappers.*` 모듈 축출(`main.py:4441-4492`). **`ledger_siblings._axes_cache`는
> 무효화 훅이 아예 없다** — `siblings_axes.json`을 고치면 웹서버 재기동이 필요하다.

---

## 3. 연결 관계 — 방향과 우선순위

### 3.1 그림

```
                       ┌──────────────────────────────────────┐
                       │        table_config.json             │
                       │  (테이블·컬럼·map_key_columns의 정본) │
                       └──────────────────────────────────────┘
                          ▲            │ 유도(derive)
             검증(validate)│            │ 항상 «밑바탕», 절대 «덮어쓰지» 않음
                          │            ▼
   ┌───────────────────────┴───┐   ┌──────────────────────────────────┐
   │  chain_rules.json         │   │  map_overlay_config.json         │
   │  enrichment_rules.json    │   │  .table_bindings.<표>.columns    │
   │  virtual_join_rules.json  │   │  키별로: 선언 > 유도 > 부재       │
   │                           │   └──────────────────────────────────┘
   └───────────────────────────┘        │              ▲
              │                          │ 상속(inherit)│ @map_key_columns
              │ 「@map_key_columns」      ▼              │ (명시 토큰)
              └────────────────►  bonding_plan.DERIVED_ROLE_OF
                                  {x→x, y→y, val→val, bin→val}
                                         │  «required에 든 역할이 «없을 때»만»
                                         ▼
              ┌──────────────────────────────────────────────────┐
              │  bonding_plan_config.json                        │
              │        ▲                                         │
              │        │ source_config_ref: "bonding_plan"       │
              │  transfer_plan_config.json  (stage 전체 위임)     │
              └──────────────────────────────────────────────────┘
```

### 3.2 우선순위 표 — 「A가 B를 이긴다」

| 자리 | 이기는 쪽 | 지는 쪽 | 틀린 선언을 쓰면? | 구현 |
|---|---|---|---|---|
| 맵 바인딩 (키별) | `map_overlay_config` 선언 | `table_config` 유도 | 🟢 **이름으로 거절** — 바인딩 전체가 `None`이 되고 로그가 「고치지 말고 **지워라**」라고 말한다 | `map_overlay.py:1778-1791, 1815-1821` |
| 체인 규칙 컬럼 | 규칙의 선언 | `table_config` 유도(단일 `map_key_columns` → `business_key`) | 🟢 **예외 발생** `ColumnBindingRefused` | `chain_bindings.py:159-197` |
| **계획 config 역할** | **선언** | **맵 바인딩 유도** | 🔴 **조용히 이긴다 — 검증이 없다.** 나중에 `missing` 한 단어로만 나타난다 | `bonding_plan.py:565-586` |
| stage 소스 위임 | `bonding_plan_config.json` | stage 자기 `source.*`(**전혀 안 읽힘**) | 🟡 `not_reached`로 **이름 붙여** 알려줌 | `transfer_plan.py:417-427, 693-715` |
| DB 접속 | `env DATABASE_URL` | `database.json` > 기본값 | — | `paths.py:159-165` |
| 값컬럼 후보 | `map_overlay_config.value_column_candidates` | 내장 기본 목록 | **부분 병합 없음 — 통째로 교체** | `map_overlay.py:1548-1562` |
| enrichment→chain | 둘 다 산다 | — | **병합이 아니라 «이어붙이기»** — 이름이 겹쳐도 규칙 둘이 각각 존재 | `chain_ingestion_worker.py:322-330` |

> 🔴 **표에서 빨간 줄이 하나다.** 「틀린 선언이 조용히 이기는」 해석기는 **계획 config
> (`bonding_plan`/`transfer_plan`) 하나뿐**이다. 나머지 넷은 전부 `table_config`에 대고
> 검증해서 **이름으로 거절**한다. 오늘의 사고도, 2026-08-04의 사고도, 그 하나에서 났다.
>
> ⚠️ **초록 넷에도 공통의 구멍이 하나 있다.** 검증은 `table_config`가 **그 표를 선언했을
> 때만** 돈다 — 미선언 표에 대해서는 「판단할 수 없다」로 **그냥 통과**시킨다
> (`chain_bindings.declared_columns`가 `None`을 돌려주는 설계, `map_overlay`의 `known is None`
> 분기도 같다). 미선언 표를 쓰는 규칙이 계속 돌게 하려는 의도지만, **결과적으로 §5.1과 §5.4의
> 상태 — 「표가 통째로 빠졌는데 아무도 거절하지 않는다」 — 를 만든다.**

---

## 4. 역할별 상속 가능 여부 — 이 문서의 핵심

### 4.1 계획 config(`bonding_plan_config` / `transfer_plan_config`)의 역할

파생 대상은 `DERIVED_ROLE_OF = {x→x, y→y, val→val, bin→val}` 넷뿐이고
(`bonding_plan.py:494`), 실제로 메워지려면 **세 조건이 동시에** 참이어야 한다.

1. 그 역할이 `DERIVED_ROLE_OF`에 있고,
2. **호출부가 그 역할을 `required`로 요구하고**,
3. `columns`에 **그 역할이 없어야** 한다.

| 역할 | 상속되나 | 무엇에서 | 적으면 상속이 막히나 | 왜 그런가 / 어떻게 해야 하나 |
|---|---|---|---|---|
| `x`, `y` | **조건부 예** | 해당 테이블의 맵 바인딩(`map_overlay_config.table_bindings` → 없으면 `table_config` 유도) | 🔴 **예 — 조용히 막힌다** | 파생이 도는 자리: `bin_map`(BIN_AXIS_ROLES) · `origin_log` · `origin_area_map` · `source_region`. **안 도는 자리**: `required=("lot","slot")`인 모든 자리(대부분) |
| `val` | **조건부 예** | 맵 바인딩의 값 컬럼. ⚠️ `fallback_guess`로 나온 값은 **거부**된다(`bonding_plan.py:547-548`) | 🔴 **예** | 추측한 값 컬럼으로 집계를 내면 「아무도 선언하지 않은 숫자」가 나온다 |
| `bin` | **조건부 예** | 맵 바인딩의 **`val`**(`bin→val`) | 🔴 **예** | `bin_map`에서만 required |
| `lot`, `slot` | **아니오 — 그리고 그게 옳다** | — | (해당 없음) | **키 역할은 절대 파생하지 않는다.** 오버레이는 `dt_log`를 `dt_job`으로 키잉하는데 계획은 `dt_lot`/`dt_slot`으로 키잉한다. 그 차이는 **관례가 아니라 목적에 대한 정보**다(`bonding_plan.py:481-483`) |
| `origin_x`, `origin_y` | **아니오 — 그리고 그게 옳다** | — | (해당 없음) | 같은 표 위의 **두 번째 좌표쌍**이다. 맵 바인딩은 좌표쌍 하나만 서술하므로 **어느 쪽인지 말할 수 없다**(`bonding_plan.py:484-485`) |
| `value`(plan_store) | **아니오** | — | — | 철자가 `val`이 아니라 `value`다. `DERIVED_ROLE_OF`의 키가 아니므로 파생 대상이 아니다 |
| `target_table`·`map_id`·`grid_metadata` | **아니오** | — | — | 메타데이터 표의 컬럼이고 관례가 없다 |
| 선택(optional) 역할 전부 | **아니오 — 그리고 그게 «가장» 옳다** | — | — | 🔴 **여기가 하중을 받는 자리다.** 선택 역할의 부재는 이미 **모든 소비자가 행동으로 옮기는 정보**다 — 좌표 없는 transfer_log는 `connected(count_only)`로 읽히고, 좌표 없는 소스는 영역 교차를 0으로 낸다. 이걸 자동으로 메우면 **count-only 자리가 조용히 집합 뺄셈으로 바뀌어 숫자가 달라진다**(`bonding_plan.py:486-493`) |

**호출부별 `required` — 어느 역할이 그 자리에서 상속되는가**

| 호출부 | `required` | 실제로 상속 가능한 역할 |
|---|---|---|
| `bonding_plan.py:840` (defect/eds_fail/total_chips) | `(lot, slot)` | **없음** |
| `bonding_plan.py:939` (used_chips) | `(lot, slot)` | **없음** |
| `bonding_plan.py:972` (process_history) | `(lot, slot)` | **없음** |
| `transfer_plan.py:1098` `bin_map` | `BIN_AXIS_ROLES (lot,slot,x,y,bin)` | **x, y, bin** |
| `transfer_plan.py:1784` `origin_log` | `ORIGIN_LOG_ROLES` | **x, y**만(`origin_x/y`는 제외) |
| `transfer_plan.py:2031` `origin_area_map` | `(lot,slot,x,y,val)` | **x, y, val** |
| `transfer_plan.py:475,921,2418` `source_region` | `SOURCE_REGION_ROLES` | **x, y** |
| `transfer_plan.py:469,3336` `registry` | `REGISTRY_ROLES` | **없음** |
| 그 밖의 `total_chips`/`lot_membership`/보조 역할 | `(lot, slot)` | **없음** |

### 4.2 맵 바인딩(`map_overlay_config`)의 키

| 키 | 상속되나 | 무엇에서 | 적으면? |
|---|---|---|---|
| `x`, `y` | **예** | `table_config`에 **문자 그대로** `x`/`y` 컬럼이 있으면 둘 다. 한쪽만 있으면 **둘 다 안 준다** | 🟢 검증 후 거절 |
| `val` | **조건부** | 값컬럼 후보 목록에서 첫 매치. ⚠️ **그 표에 `table_bindings` 블록이 하나라도 있으면 `val` 생략은 상속이 아니라 「값 없음(점유만)」** | 🟢 검증 후 거절 |
| `key_columns` | **예** | `table_config.<표>.map_key_columns` → 없으면 표가 `lot`·`slot`을 **둘 다** 선언할 때만 `["lot","slot"]` | 🟢 검증 후 거절 |
| `index` | **아니오 — 명시적 거부** | — | 유도 자체가 없다(`map_overlay.py:1734-1737`) |

### 4.3 그 밖

| 자리 | 상속되나 | 비고 |
|---|---|---|
| 체인 규칙의 job 컬럼 | **예** | 규칙 선언 > `map_key_columns`가 **정확히 하나**일 때 그것 > `composite_key_source`가 없을 때 `business_key` > **거절**. 「`dt_job`이겠지」라는 추측 폴백은 **일부러 없다**(`chain_bindings.py:186-192`) |
| stage 소스 블록 | **예 — 블록 통째로** | `source_config_ref: "bonding_plan"`이면 그 stage의 `source.*`는 **한 줄도 읽히지 않는다**. `bin_map`과 `target_map`만 stage에 남는다 |
| enrichment 규칙 컬럼 | **아니오** | 전부 문자 그대로 적어야 하고, `table_config`에 대고 **검증만** 한다(위반 시 규칙 스킵) |
| 가상 조인 컬럼 | **아니오** | 문자 그대로. 승인에는 우측 표의 UNIQUE 인덱스까지 필요 |
| `ledger_config` | **아니오 — 연결 자체가 없다** | `table_config`·`column_types`·`map_key_columns`를 한 번도 참조하지 않는다 |
| `target_map.preset` | **아니오, 그리고 «집행 지점이 없다»** | 서버는 이 값을 그대로 통과시킬 뿐 아무도 해석하지 않는다. 해석은 클라(`client2/src/transfer_plan.js`)에서 일어난다 → **오타가 나도 서버는 거절하지 않는다**(§5.5) |

---

## 5. 지금 틀린 선언 전수 (2026-08-14 이 박스 실측)

방법: 모든 라이브 config의 `{table, columns}` 선언을 훑고, `map_overlay`
바인딩, chain 규칙, enrichment 규칙을 각각 그
**해석기 자신에게** 물었다.

### 5.1 🔴 M1 코어 요약이 «통째로» 죽어 있다 — 소스 다섯 전부 거절

| 표 | 역할 | 선언된 이름 | 실제 | 무엇이 안 되나 |
|---|---|---|---|---|
| `core_defect_map` | `defect` (lot/slot/x/y/val) | 이름은 **맞음** | **표가 `table_config.json`에 없음** | defect 카운트 |
| `eds_fail_map` | `eds_fail` | 이름은 **맞음** | **표가 `table_config.json`에 없음** | eds_fail 카운트 |
| `core_defect_map` | `total_chips` | 이름은 **맞음** | **표가 `table_config.json`에 없음** | **분모** — 코어 가용 계산 자체 |
| `bonding_log` | `used_chips` (lot→`core_lot`, slot→`core_slot`, x→`cx`, y→`cy`) | `core_lot`/`core_slot`/`cx`/`cy` | **DB엔 있으나 `table_config`가 선언하지 않음** | 기전사 칩 수 |
| `wafer_process` | `process_history` | 이름은 **맞음** | **표가 `table_config.json`에 없음** | 공정 이력·경고 |

**해석기의 실제 판정**(요약): 앞의 셋과 다섯째는 `mapping_unavailable`
(「테이블이 table_config.json에 선언돼 있지 않습니다」), `used_chips`는
`candidate_column_missing`(「필수 역할이 가리키는 컬럼이 테이블에 없습니다: lot → `core_lot`, slot → `core_slot`」).

**언제부터인가.** 디스크의 `table_config` 스냅샷을 시간순으로 훑었다. `2026-07-28 07:24`
스냅샷까지는 세 표가 **전부 선언돼 있었고** `bonding_log`도 `core_lot`/`core_slot`/`cx`/`cy`를
선언했다. `2026-08-04 05:19` 스냅샷부터 **전부 사라졌다.** `bonding_plan_config.json`은
`2026-07-27 00:46` 이후 손대지 않았다 — **config가 움직인 게 아니라 그 밑의 표 선언이
빠져나갔다.**

물리 표와 데이터는 남아 있다(이 개발 사본 기준: `core_defect_map` 5,152행 ·
`eds_fail_map` 2,576행 · `wafer_process` 22행, 마지막 기록 2026-08-01).
⚠️ 이 박스는 **개발 사본이고 운영의 증거가 아니다.** 사용자가 명시한 대형 합성 픽스처
목록(`void_obs`·`inspection_run`·`delam_obs` 100%, `bonding_log` 98.5%)에 이 셋은 없다.

**판정이 필요하다:** M1 코어 요약을 되살릴 것인가(→ 세 표를 `table_config.json`에 다시
선언 + `bonding_log`에 네 컬럼 추가), 아니면 **의도적으로 폐기된 축인가**(→
`bonding_plan_config.json`의 그 선언들을 지우고, DT stage의 `source_config_ref`를 다시 볼 것).

### 5.2 🔴 라이브 `table_config.json`이 자기 `.sample`보다 «모자란다» — 켜져 있는 체인 규칙 하나가 거절된다

두 파일의 차이는 딱 셋이다.

| 차이 | 라이브 | `.sample` |
|---|---|---|
| `dt_map.column_types` | `dt_index`·**`dt_job` 없음** | 둘 다 있음 |
| `dt_job_attribution` | 없음 | 있음 |
| `eqp_frame_attribution` | 없음 | 있음 |

결과: 체인 규칙 **`dt_inventory_to_standard_dt_map`(enabled=true)**가 배치를 만들지 못한다.
그 규칙은 `target_job_column: "dt_job"`을 `target_table: "dt_map"`에 대고 선언하는데,
라이브 `table_config`의 `dt_map`은 `dt_job`을 선언하지 않는다 →
`chain_bindings.resolve_column`이 `ColumnBindingRefused`를 던진다
(`mappers/dt_standard_map_mapper.py:116`).

⚠️ **이건 진행 중인 이관과 얽혀 있다.** `dt_map`의 정체성을 `dt_job`에서 `(dt_lot, dt_slot)`로
옮기는 레인이 2026-08-13에 `assy_qa`에서 착지했다. 매퍼 주석이 명시하듯 그 이관 후에도
`target_job_column`은 **선언돼야 하고**(맵 키 둘 중 어느 것도 job이 아니므로), 그러려면
`dt_map`이 `dt_job`을 **컬럼으로는 계속 갖고 있어야** 한다. `.sample`은 그렇게 돼 있다.
**라이브만 빠졌다.** 의도인지 누락인지는 그 레인 소유자의 판정이 필요하다.

### 5.3 🟡 유도와 «똑같은 말을 다시 적은» 선언 다섯

`map_overlay_config.table_bindings`의 `key_columns` 다섯 개가 `table_config`가 이미 유도하는
값과 **글자 그대로 같다**. 해석 결과는 안 바뀌지만, **같은 진실의 사본이 둘이 되어** 다음에
갈라질 자리가 된다(그리고 유도 경로가 아직 도는지를 가린다).

| 표 | `key_columns` 선언 | `table_config`가 유도할 값 |
|---|---|---|
| `dt_map` | `["dt_lot","dt_slot"]` | 같음 |
| `dt_log` | `["dt_job"]` | 같음 |
| `dt_core_view` | `["dt_job"]` | 같음 |
| `core_usage_map` | `["core_wafer"]` | 같음 |
| `bonding_log` | `["bond_lot","bond_slot"]` | 같음 |

`GET /admin/config/resolve?domain=binding`이 이 다섯을 `restates_derivation: true`로 이미
표시하고 「지우십시오」라고 말한다. **그 밖의 맵 바인딩 33개는 전부 정상**이고 거절 0건이다.

### 5.4 🟡 `enrichment_rules`의 `dt_job_lot_slot_attribution` — 판정 불가 상태

`derived_table: "dt_job_attribution"`이 라이브 `table_config`에 없다. 이 경우 검증기는
**거절하지 않고 「판단할 수 없다」로 통과시킨다**(`chain_bindings.declared_columns`가
`None`을 돌려주는 설계 — 미선언 표를 쓰는 규칙이 계속 돌게 하려는 의도).
이 상태는 §5.2의 `.sample` 차이와 **같은 뿌리**다.

### 5.5 🟡 집행 지점이 없는 선언 둘

- `transfer_plan_config.stages.*.target_map.preset`(`"TAPE"`, `"BASE"`) — 서버에 해석기가
  없다. 오타가 나도 서버는 200을 준다.
- `maps.json`에 **`name: "BASE_OFFSET"`인 프리셋이 둘**이다(`custom_1785446789091`,
  `custom_1785446867113`, `rotation` 0/270으로 서로 다름). 프리셋을 **이름으로** 참조하면
  어느 쪽이 잡힐지는 순서에 달린다.

### 5.6 🟢 깨끗한 것들 (반증 가능하게 적는다)

- `table_config` 자기 정합성: `business_key`·`composite_key_source`·`display_columns`·
  `map_key_columns`가 자기 `column_types`를 벗어난 곳 **0건**.
- 맵 바인딩: 유효 33건 · **거절 0건** · 그중 **9건이 유도로** 채워졌다
  (`bonding_map`의 x/y/val/key_columns, `core_wafer_map`의 key_columns,
  `valid_die_ref`의 x/y/val/key_columns). 미해결 7건은 전부 `index` 미선언 — 정상이다
  (`index`는 유도 대상이 아니고 부재는 부재를 뜻한다).
- `chain_rules` 8개 규칙의 `trigger_table`/`target_table` — **전부 선언된 표**.
- `transfer_plan_config.plan_store.registry` 7역할 + `bin_map` 5역할 — 전부 해석됨
  (`bin_map`의 x/y는 **유도로** `dt_x`/`dt_y`를 받았다. 상속이 실제로 도는 것을 확인한 자리다).
- `virtual_join_rules.json`: **활성 규칙 0개**(모든 키가 `_` 접두라 로더가 무시). 의도된 상태.

---

## 6. 제안 — 이 계급의 사고를 다시 안 내려면

전제: **이미 있는 것을 먼저 쓴다.** 이 프로젝트에는 계기가 이미 넷 있다 —
`GET /admin/config/resolve?domain=binding`, `GET /admin/transfer-plan/dry-run`,
`server/scripts/list_undeclared_tables.py`, `server/scripts/audit_schema_canon.py`.
**오늘 사고의 절반은 도구 부재가 아니라 「도구에 물어보지 않은 것」이다** —
dry-run은 `total_chips`의 x/y를 `derivable: false`로 표시하고 그 결과까지
(「없으면 그쪽 total/remaining이 null이 되고 BIN 항목은 unknown으로 내려갑니다」)
문장으로 말하고 있었다.

### A. 로드 시점 거절 — 「선언은 그 표에 실재하는 컬럼이어야 한다」 (권장)

계획 config(`bonding_plan`/`transfer_plan`)의 `{table, columns}` 선언을 로드할 때
`table_config`에 대고 검증하고, 어긋나면 **이름으로 거절**한다 — 나머지 네 해석기가
이미 하는 그대로.

- **비용:** `bonding_plan.py`에 검증 호출 한 줄 + 기존 `explain_binding_refusal` 재사용
  (문장 생성기는 **이미 있다**). 테스트 2~3개.
- **위험:** 지금 「조용히 미해석」인 선언이 **에러로 승격**된다 → §5.1의 다섯이 즉시
  시끄러워진다. 그게 목적이지만 **§5.1의 판정이 먼저** 나와야 한다.
- **한계:** 「선언이 없어서 상속도 안 되는」 §0-② 모양은 **못 잡는다**(선언이 없으니
  검증할 게 없다).

### B. 기동 시 «전수 대조» 배너 (권장, A와 짝)

기동 시 모든 config 선언 × `table_config`를 훑어 어긋난 행을 **로그 한 덩어리**로 낸다.
`schema_drift.py`가 이미 하는 것과 같은 자세.

- **비용:** 이 조사에 쓴 감사 스크립트를 `server/scripts/audit_config_declarations.py`로
  승격(≈120줄, 읽기 전용, DDL 없음).
- **효과:** §5.1·§5.2 같은 「표 선언이 밑에서 빠져나간」 사고를 **다음 기동에 즉시** 드러낸다.
  이번 사고는 열흘 동안 조용했다.

### C. `dry-run`을 M1까지 넓힌다 (권장)

`GET /admin/transfer-plan/dry-run`은 M2만 설명한다. 위임된 stage의 역할은
`not_reached`라고만 말하고 **위임 «받은» `bonding_plan_config`의 다섯 소스가 왜 거절됐는지는
말하지 않는다.** 그 다섯이 지금 죽어 있는데 계기가 침묵한다.

- **비용:** `dry_run`에서 위임 시 M1 config를 열어 같은 `explain_binding_refusal`을
  다섯 역할에 돌린다(≈25줄). 새 어휘 없음.

### D. 「선택 역할도 유도한다」는 **추천하지 않는다**

`required`가 아닌 역할까지 자동으로 메우면 §0-③이 「고쳐진 것처럼」 보이지만,
`count_only` 자리가 조용히 집합 뺄셈으로 바뀌어 **숫자가 달라진다**
(`bonding_plan.py:486-493`이 정확히 이걸 경고한다). 필요한 건 「x/y가 없으면 그 결과가
이렇게 된다」를 **화면이 말해 주는 것**이고, 그건 이미 dry-run에 있다.
정말로 그 자리에서 좌표가 필요하다면 **그 호출부의 `required`에 x/y를 넣는** 국소 결정이
맞고, 그건 총괄 판정 사항이다.

### E. 자리표시자 금지 규칙 — **추천하지 않는다**

`"x": "x"`는 `core_defect_map`에서 **정답**이다(§0-①). 「자리표시자처럼 생긴 값 금지」는
정당한 선언을 오차단한다. **문자 검사 말고 결과 검사** — 그게 A다.

**우선순위 제안: A + B를 한 라운드로, C를 그다음.** 단, §5.1과 §5.2의 판정이
**A보다 먼저** 나와야 한다(거절을 켜면 그 둘이 즉시 에러가 된다).

---

## 7. 재현 절차

**지금 있는 계기 셋** (전부 읽기 전용, DDL 없음):

```
# 1) 맵 바인딩 「무엇이 이겼나」 — 선언/유도/부재/거절 + 「지우십시오」 안내 (§5.3)
GET /admin/config/resolve?domain=binding

# 2) 계획 config 역할별 판정 + 어느 철자가 이겼나 + 지우면 무엇이 유도되나 (§0-③, §4.1)
GET /admin/transfer-plan/dry-run

# 3) 선언과 물리 스키마의 어긋남 (미선언 표/컬럼, 선언됐으나 없는 표)
conda run -n assy_manager python server/scripts/list_undeclared_tables.py
```

⚠️ **§5.1의 전수 대조를 한 번에 내는 계기는 «아직 없다».** 이번 조사는 임시 스크립트로
했고, 그것을 `server/scripts/audit_config_declarations.py`로 승격하자는 것이 **§6-B의
제안**이다(아직 만들지 않았다 — 승인 대기).

> ⚠️ 2·3번은 `require_admin_token`이 걸린 읽기 전용 경로다. 1·4번은 DDL을 하지 않는다.
> 그리고 **`Grep`을 `server/config/`에 걸지 말 것** — gitignore 때문에 라이브 파일이 통째로
> 안 보이고 `.sample`만 뜬다.

---

## 8. 관련 문서

- [guide/CONFIG_GUIDE.md](../guide/CONFIG_GUIDE.md) — 어느 파일을 열지(색인)
- [guide/config/](../guide/config/README.md) — 파일 한 장당 세팅 절차
- [architecture/SCHEMA_CANON.md](SCHEMA_CANON.md) — 스키마 규칙 + 탐지기(같은 장르, 다른 축)
- [architecture/data_model.md](data_model.md) · [architecture/backend.md](backend.md)
- [guide/data_preservation_and_signature_change.md](../guide/data_preservation_and_signature_change.md)
