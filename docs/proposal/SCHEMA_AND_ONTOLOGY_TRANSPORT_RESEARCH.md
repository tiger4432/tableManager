# 스키마·온톨로지 이행(transport) 연구 — 구조 변경은 어떻게 환경을 건너가는가

> 상태: **연구·제안** (미확정). 제품 스펙이 아니다. 코드·config·마이그레이션을 하나도 바꾸지 않았다.
> 작성: 2026-08-11 · ontology-pm
> ⚠️ **수치의 출처:** 아래 DB 실측은 전부 **이 개발 박스의 격리 DB `assy_qa`**(읽기 전용 세션)와
> **HEAD 소스**다. 사용자 운영 박스는 다른 기계이고, 이 문서의 어떤 숫자도 운영의 증거가 아니다.
> ⚠️ **동시 작업:** 수리 레인이 지금 `server/config/*.json`을 편집 중이다(전사된 threshold 제거,
> 죽은 컬럼 선언 3건 삭제, `ontology_mapping`의 `CoreCell` 철자 교정). 아래 config 실측은
> 2026-08-11 시점 파일이며, 그 레인이 건드리는 키에 의존하는 대목은 본문에서 따로 표시했다.

---

## 결론

**하나의 메커니즘이 두 문제를 다 덮는다.** 이 문서가 다루는 두 페이로드(테이블 스키마,
온톨로지/config 선언)는 서로 다른 결함이 아니라 **같은 결함의 두 얼굴**이다:
구조 변경이 이동하는데, **그 변경이 무엇을 무효화했는지 말해 주는 것이 같이 이동하지 않는다.**

그 메커니즘은 **"기대 상태를 코드에서 파생해 추적 가능한 산출물로 떨어뜨리고, 배포 대상에서
그것을 실제와 대조한다"**이며, **이 저장소는 이미 그 메커니즘을 세 조각으로 갖고 있다.**
새 발명이 필요한 게 아니라 **일반화가 남았다.**

| 이미 있는 조각 | 무엇을 하는가 | 얼마나 깔렸나 |
|---|---|---|
| `server/schema_drift.py` | 모델이 기대하는 스키마 ↔ DB 카탈로그 대조, 부팅마다 | 26개 테이블 전부. **단, 이름만. 타입은 안 본다** |
| `known_tables=crud.TABLE_CONFIG` 인자 | config 선언의 컬럼 참조를 `table_config`에 대조, **로드 시점에 이름 붙여 거절** | 8개 표면 중 **4개** |
| `server/scripts/install_product_tables.py` | 제품 소유 선언을 사이트의 gitignore된 live config에 **바이트 스플라이스**로 설치 | `table_config.json`의 4개 엔트리만 |

**권고는 하나다: 이 세 조각을 같은 기준까지 완성하고, 하나의 대조 표면에 모은다.**
첫 슬라이스는 `schema_drift`에 **타입 비교**와 **실행 원장(ledger)** 을 더해
`test_system_schema_drift.py`의 **손으로 관리하는 매니페스트를 파생물로 대체**하는 것이다.
이 한 조각이 아래 증상 ①②③을 동시에 닫는다.

**"그냥 config를 커밋하자"는 답은 이 문서 어디에도 없다.** §3의 실측이 그 이유를 바꾼다 —
이 박스에서 gitignore된 live config와 추적되는 `.sample`은 **10개 중 8개가 바이트 동일**하고,
`table_config.json`은 정규화하면 **차이가 0줄**이다. 즉 버전 관리는 이미 사실상 존재하며,
없는 것은 **둘 사이의 방향(누가 상류인가)과 병합 규칙**이다. 그것은 `install_product_tables.py`가
이미 답해 둔 문제다.

---

## 1. 확인된 현상 (1) — 스키마가 실제로 타는 경로 전부

개발자 기계에서 돌아가는 DB까지, 테이블 스키마가 갈 수 있는 길은 다섯 개다. 각각의
**덮는 범위**와 **못 덮는 것**을 소스에서 확인했다.

| # | 경로 | 코드 | 하는 일 | **못 하는 일** |
|---|---|---|---|---|
| ① | `create_all` | `server/main.py:118` | 없는 테이블을 통째로 만든다 | **이미 있는 테이블에는 컬럼도 인덱스도 추가하지 않는다** |
| ② | 동적 테이블 동기화 | `models.sync_dynamic_tables_schema` (`server/database/models.py:772`), 부팅마다 호출 (`main.py:120`) | `table_config`에 있고 DB에 없는 **컬럼을 ADD** | **ALTER TYPE 없음 · DROP 없음 · RENAME 없음.** 실패는 `print` 후 삼킨다(`models.py:801-802`) |
| ③ | 런타임 신규 테이블 | `models.create_missing_dynamic_tables` | config 핫리로드로 생긴 **신규 테이블만** CREATE | 주석이 명시 — *"기존 테이블에 대한 런타임 ALTER는 수행하지 않는다"* |
| ④ | `server/migrations/*` | `.py` 4개 + `.sql` 2개 | 손으로 실행하는 DDL | **순서 없음 · 원장 없음 · 실행 여부를 아무도 모른다** (아래) |
| ⑤ | 부팅 시 드리프트 점검 | `server/schema_drift.py`, `f6406b1` | 모델 ↔ 카탈로그 대조, 배너로 보고 | **읽기 전용.** 그리고 자기 docstring이 선언 — *"It compares NAMES, not types."* (`schema_drift.py:38-39`) |

### 1.1 ④에 원장이 없다는 것은 측정된 사실이다

```
grep -rn "schema_version|migration_history|alembic|applied_migrations|schema_migrations"
  server --include=*.py --include=*.json --include=*.sql   ->  0 hits
```

`server/migrations/`의 파일은 6개이고 이름에 순서가 없다(`add_business_key_unique_index.py`,
`add_frame_confirmation.py`, `migrate_jsonb_numeric.py`, `normalize_schema.py`,
`add_audit_history_keyset_indexes.sql`, `add_dt_log_trigger_indexes.sql`). 멱등성은 파일마다
**개별 선언**이다 — `add_frame_confirmation.py`는 자기 헤더에 *"추가 전용 · 멱등"*을 명시하고
`ADD COLUMN IF NOT EXISTS`만 쓰지만, `add_dt_log_trigger_indexes.sql`은 헤더에 **`NOT RUN`**
이라고 적혀 있다(선행 조건으로만 배포된 파일). **어느 박스가 어느 파일을 돌렸는지 기록하는
자리가 없다.**

그래서 `schema_drift.py`가 만들어 내는 문장은 *"run server/migrations/add_frame_confirmation.py"*
까지이고, **"그거 이미 돌렸나?"에는 아무도 답할 수 없다.** `a14a098`이 그 마이그레이션 파일에
검증 루프를 손으로 넣은 이유가 정확히 이것이다(`add_frame_confirmation.py:169-181` —
컬럼별 `information_schema` 조회를 **이름으로** 출력하며, 주석이 이유를 적어 놓았다:
*"'the migration ran' is not the same claim as 'the column is there'"*).

### 1.2 ⑤가 타입을 안 본다는 것이 증상 ②의 정확한 구멍이다

`schema_drift.py:38-39`가 자기 한계를 선언한다: *"A column that exists with the wrong type is
real drift and this will call it healthy."* `dt_inventory.dt_frame`이 `double precision`인 채로
있어도 이 점검은 초록이다. §2 ②에서 다시 다룬다.

### 1.3 어느 경로도 덮지 않는 것 — 이름을 붙인다

1. **타입 변경.** ①②③⑤ 어느 것도 `ALTER ... TYPE`을 발행하지 않고, ⑤는 보지도 않는다.
   ④만이 할 수 있고, ④는 원장이 없다.
2. **컬럼 삭제·개명.** 어느 경로에도 없다. `schema_drift`는 DB에만 있는 컬럼을 `INFO`로
   *"harmless"*라고 부른다(`schema_drift.py:248-254`) — 의도된 판단이지만, 개명은 "새 컬럼 +
   무해한 잉여 컬럼"으로 보이며 **개명이었다는 사실은 아무 데도 안 남는다.**
3. **동적 테이블의 ALTER 실패.** ②는 실패를 `print` 후 삼킨다. 실패한 박스는 조용히
   컬럼 없는 상태로 계속 돈다.
4. **"선언은 있는데 물리 테이블이 없다"** — 이 박스에서 지금 그 상태다:

   ```
   assy_qa: 물리 테이블 49개 / table_config 선언 19개
   선언은 있으나 물리 테이블 부재:  core_usage_map, dt_core_view, dt_inventory
   ```

   `dt_inventory`는 2026-08-09 사용자 결정으로 **DT frame의 통합 정본**이 된 테이블이다.
   그 테이블이 이 박스에 없다. `create_all`/③이 만들어 줄 수 있었지만 이 스냅샷 DB는
   `snapshot_db.py`가 만들고 그 뒤로 부팅되지 않았다(`snapshot_db.py:154-171`은 서버 자신의
   부트 경로 — `create_all` + `sync_dynamic_tables_schema` — 를 호출한다. 즉 스냅샷은
   **스키마도 함께 옮기려 시도하지만, 그 시점의 config가 만든 스키마다**).

5. **선언 없이 존재하는 물리 테이블.** 33개, 그중 데이터가 있는 것:

   ```
   core_defect_map   5,152 rows      eds_fail_map   2,576 rows
   wafer_process        22 rows      wafer_slot_history  0 rows
   ```

   이들은 `table_config`에 없으므로 `models.DYNAMIC_TABLES`에도 없고, 따라서
   **`schema_drift`의 시야 밖이다** — 점검은 "코드가 매핑한 테이블"을 순회하기 때문이다.
   **선언에서 빠지면 오류가 아니라 투명해진다**(증상 ⑤, 확인됨).

---

## 2. 여섯 증상 재검증 — 넷은 그대로, **둘은 고쳐야 한다**

### ① 두 컬럼 때문에 테이블이 통째로 내려갔다 — **맞다. 단, 커밋 귀속을 정정한다**

기제는 확인된다. `test_system_schema_drift.py`가 그 기제 자체를 테스트로 고정해 두었고
(`test_missing_column_appears_in_sql_that_never_asked_for_it:67`,
`test_full_entity_read_dies_without_the_column:79`), `schema_drift.py` 헤더가 같은 문장을 쓴다.

**정정:** 두 컬럼이 `models.py`에 도달한 커밋은 **`9cf17ee`**이고, `a14a098`은
*docs(board)* 커밋으로 **마이그레이션 파일에 `ALTER` 두 줄과 검증 루프를 추가하고
드리프트 매니페스트에 컬럼을 기록한** 커밋이다. `a14a098`의 커밋 메시지 자체가
*"The migration already exists ... and has simply not been run; production may be in the same
state"*라고 적고 있다. 즉 **손으로 수리된 것은 DB가 아니라 마이그레이션 파일과 매니페스트**이며,
운영 박스가 그때 어떤 상태였는지는 이 저장소가 알지 못한다. 이 구분이 §1.1의 원장 부재와
정확히 같은 지점이다.

### ② 타입 변경이 산문에만 있다 — **맞다. 그리고 예상보다 나쁘다**

`docs/history/20260809_160000_syn_dt_alignment_samples.md:41`:
*"the pre-existing `dt_inventory.dt_frame` physical column from `double precision` to `text`"*.

추적되는 마이그레이션에서 이 변경을 찾으면:

```
grep -rn "dt_frame" server/migrations/   ->  add_frame_confirmation.py:34 (`dt_frame TEXT`, CREATE TABLE 안)
```

**`dt_inventory`에 대한 `ALTER ... TYPE`은 저장소 어디에도 없다.** 저장소를 처음부터 재생하면
이 변경은 재현되지 않는다. 그리고 §1.2대로 **`schema_drift`가 이 종류를 구조적으로 못 본다** —
그래서 "산문에만 있다"에 더해 **"검출기도 없다"**가 붙는다. 이 박스의 타입 대조 실측은
`declared ∩ physical` 범위에서 불일치 0건이지만, `dt_inventory` 자체가 물리적으로 없어서
이 케이스는 **측정 범위 밖**이다. 즉 초록이 아니라 **미측정**이다.

### ③ 드리프트 탐지가 테스트 파일 안의 손 목록이다 — **맞다. 단, 절반은 이미 자동화됐다**

`server/tests/test_system_schema_drift.py:186`의 `SYSTEM_TABLE_COLUMNS`는 테이블당 컬럼명
튜플을 손으로 적은 dict가 맞다. 실패 메시지가 순서를 규정하는 것도 맞다
(`:249-254`): *"Ship a migration that adds it to an existing database, confirm it has run,
then record the column here naming that migration."*

**정정 두 가지 — 둘 다 설계 근거로 중요하다.**

1. **이 게이트는 모델↔DB를 대조하지 않는다. 모델↔손목록을 대조한다.** 그래서
   개발자가 `models.py`에 컬럼을 더할 때만 빨개지고, **어느 박스에서 마이그레이션이
   돌았는지는 볼 수 없다.** 손목록이라는 게 문제의 절반이고, **대조 상대가 DB가 아니라는 게
   나머지 절반**이다.
2. **손으로 관리하던 매니페스트가 이미 한 번 파생으로 대체된 전례가 있다.** `f6406b1`이
   `schema_drift.MIGRATION_OWNER`를 손 지도에서 **디렉터리 스캔 파생**으로 바꿨고
   (`schema_drift.py:89-104`), 그 이유를 코드 주석이 적어 놓았다: *"A check whose whole value
   is naming the fix cannot depend on somebody remembering to describe the fix here."*
   **같은 판단을 `SYSTEM_TABLE_COLUMNS`에 적용하는 것이 §7의 권고다** — 새 원칙이 아니라
   이미 한 번 내려진 판단의 확장이다.

또한 이 매니페스트는 **동적 테이블을 일부러 제외**한다(`:177-180`) — 그것들은 운영자의
`table_config.json`에서 오고 git 밖이며, ② 경로라는 부팅 시 ALTER 통로가 **있기** 때문이다.
시스템 테이블에는 그 통로가 없다. **이 비대칭이 이 저장소의 실제 규칙이고, 어떤 설계도
이걸 지워선 안 된다.**

### ④ 정의가 일부러 버전 관리 밖에 있다 — **맞다. 그러나 실측이 문제의 성격을 바꾼다**

규칙은 실재한다. `.gitignore`: `server/config/*` 아래에서 `server/config/sample/*.sample`만 추적한다.
`LEAD_PM_HANDOFF.md` §2: *"`server/config/`·`ingestion_workspace/`는 **일부러** git 밖 —
운영 패치 시 오염 방지. `.sample`은 git 안이다."* `ontology_mapping.json`이 그중 하나인 것도 맞다.

**그런데 §3의 실측이 "정의가 버전 관리 밖에 있다"는 문장을 약화시킨다.** 요약하면:
이 박스에서 live config 10개 중 **8개가 추적되는 `.sample`과 바이트 동일**하고,
`table_config.json`은 정규화 비교에서 **차이 0줄**, `map_overlay_config.json`은
**바인딩 1개 차이**다. 즉 정의는 사실상 버전 관리되고 있다 — **다만 우연히, 그리고
그것을 보장하는 것이 아무것도 없이.**

### ⑤ `table_config`에서 빠진 테이블은 오류가 아니라 투명해진다 — **맞다. 실측 재확인**

§1.3-5 참조. `core_defect_map`(5,152행), `eds_fail_map`(2,576행), `wafer_process`(22행)가
물리적으로 존재하고 `table_config`에 없다. 이 박스 수치이며, 서베이 보고서
(`agent_workspace/reports/Config_map_duplication_survey.md` §0)의 결론과 일치한다.

### ⑥ 같은 모양이 8개 표면에 선언되어 있고 **어느 것도 다른 것의 상류가 아니다** — **후반부가 틀렸다**

전반부는 맞다(8개 표면: `table_config`, `ontology_mapping`, `map_overlay_config`,
`enrichment_rules`, `chain_rules`, `virtual_join_rules`, `transfer_plan_config`,
`bonding_plan_config`).

**후반부는 소스가 반박한다. `table_config`는 이미 상류다. 그것도 코드로.**
`known_tables=crud.TABLE_CONFIG`라는 인자가 그 방향을 나른다 — **8개 중 4개가 로드 시점에
자기 컬럼 참조를 `table_config`에 대조하고, 어긋나면 이름을 붙여 거절한다.** §4에서 전수한다.

---

## 3. 확인된 현상 (2) — "구조"와 "운영자의 값"은 이 파일들에서 분리되는가

브리핑이 요구한 핵심 질문이다. **정직한 답: 파일마다 다르고, 한 파일(`ontology_mapping.json`)
안에서는 분리되지 않는다.**

### 3.1 실측 — live config ↔ 추적되는 `.sample`

`server/config/*.json` 과 `*.json.sample`을 leaf 단위로 비교한 결과(이 박스, 2026-08-11):

| 파일 | 바이트 | 정규화 비교(키 순서·들여쓰기 무시) |
|---|---|---|
| `auto_update_control.json` | **동일** | 차이 없음 |
| `bonding_plan_config.json` | **동일** | 차이 없음 |
| `chain_rules.json` | **동일** | 차이 없음 |
| `enrichment_rules.json` | **동일** | 차이 없음 |
| `maps.json` | **동일** | 차이 없음 |
| **`ontology_mapping.json`** | **동일** | 차이 없음 |
| `transfer_plan_config.json` | **동일** | 차이 없음 |
| `virtual_join_rules.json` | **동일** | 차이 없음 |
| `table_config.json` | 다름(29,768 / 29,906 B) | **차이 0줄** — 키 순서·서식만 |
| `map_overlay_config.json` | 다름(9,953 / 9,757 B) | **바인딩 1개**: live에만 `core_usage_map` |

leaf 총계: 동일 570 · 값 상이 **0** · live 전용 **4** · sample 전용 **0**.

**해석.** 이 박스에서 `.sample`은 "템플릿"이 아니라 **live의 사실상 전량 사본**이다.
그래서 "정의가 git 밖이라 옮길 수 없다"는 진단은 이 박스에 대해서는 성립하지 않는다.
성립하지 않는 것은 다른 것이다:

- **방향이 없다.** live가 `.sample`에서 왔는지, `.sample`이 live에서 왔는지 파일이 말하지 않는다.
- **병합 규칙이 없다.** `.sample`에 새 키가 생겼을 때 운영자의 live 파일에 그걸 넣는
  절차가 `table_config.json`의 4개 엔트리를 제외하면 없다.
- **초과·미달을 검사하는 것이 없다.** live가 `.sample`의 구조적 상위집합인지 아무도 안 본다.
- 곁가지: `audit_history_config.json.sample`은 디스크에 있으나 **git 추적 대상이 아니다**
  (`git ls-files server/config/` 15건에 없음). `.sample`이면 추적된다는 규칙에도 예외가 있다.

**⚠️ 운영 박스에 대해서는 이 표가 아무것도 말하지 않는다.** 운영에서는 divergence가 클 수 있고,
그것이 gitignore 규칙의 존재 이유다. 이 표가 말하는 것은 **개발 박스에서 그 divergence가
관리되지 않은 채 0에 가깝다**는 것뿐이다.

### 3.2 분리가 깨끗한 파일 — `table_config.json`

이 저장소는 **이 경계를 이미 명시적으로 그어 놓았다.** `server/product_tables.py:1-27`:

- **product-owned** — assyManager 자신의 저장소. 제품이 테이블명과 컬럼을 정하고, 사이트가
  바꿀 이유가 없다. → **코드에 선언**(`PRODUCT_TABLES`, 5개 엔트리)
- **site-owned** — 고객 공장 데이터. 배포마다 이름이 다르다. → **여기 절대 선언하지 않고
  설치기가 건드리지도 않는다**

그리고 이행기까지 있다 — `server/scripts/install_product_tables.py`. 그 규율은
**정확히 브리핑이 묻는 "구조는 가고 운영자의 선택은 남는" 계약**이다:

- site 엔트리는 **재직렬화하지 않는다.** 바이트 단위 스플라이스 — 키 순서·들여쓰기·줄바꿈까지 보존
- 없으면 추가 · 같으면 **쓰기 자체를 안 함** · **다르면 drift로 보고하고 그대로 둔다**
  (`--overwrite-drift` 없이는 안 덮음)
- dry run이 기본, `--apply`가 있어야 씀 · 쓰기 전 타임스탬프 백업 · **쓴 뒤 재스캔해
  건드리지 않은 멤버를 바이트 대조하고 어긋나면 백업 복원**
- 추적되는 `.sample`의 제품 섹션은 **같은 모듈에서 생성**되고
  `test_install_product_tables.py`가 둘의 일치를 단언한다

**분리 단위는 "최상위 엔트리(테이블 1개)"다.** 그 입도에서 `table_config.json`은 깨끗하다.

### 3.3 분리가 깨끗하지 **않은** 파일 — `ontology_mapping.json`

여기서 답이 갈린다. 온톨로지 매핑의 최상위 키는 **source 테이블명**이고, 한 엔트리 안에서
product-owned와 site-owned가 **leaf 단위로 뒤섞인다**:

| 키 | 누구 것인가 |
|---|---|
| `node.label` (`CoreCell`, `Wafer`, `DtCell`) | **제품.** 온톨로지 어휘 |
| `node.node_class` (`static`/`dynamic`) | **제품.** 탐색 규칙의 축(스펙 §7.5c) |
| `edges[].type` (`ON_CORE_SLOT`, `FROM_CORE_CELL`) | **제품.** 관계 어휘 |
| `edges[].target_label` | **제품** |
| `node.identity` (`["core_lot","core_slot","core_x","core_y"]`) | **둘 다** |
| `edges[].target_identity_from` | **둘 다** |
| `node.props[].col` · `event_time_column` | **사이트.** 컬럼명 |
| 최상위 키 자체(`core_wafer_map`) | **사이트.** 테이블명 |

**`identity`가 진짜로 양쪽인 키다.** "이 개체의 정체는 무엇으로 구성되는가"는 **제품의 결정**이고,
"그 정체를 나르는 컬럼의 이름"은 **사이트의 사실**이다. 한 리스트가 둘을 동시에 표현한다.
그래서 `table_config`가 쓰는 "엔트리 단위 소유권"을 그대로 가져오면 **온톨로지는 통째로
site-owned가 되고, 제품이 정한 어휘가 사이트마다 갈릴 수 있게 된다.**

**이것이 온톨로지 페이로드의 고유한 설계 과제다.** §6에서 답한다.

---

## 4. `table_config` 변경을 배포 전에 검사 가능하게

사용자의 문장: 「지금 table config 하나에서 map overlay 등등 다 꺼내쓰면서 호환 안되서
하나 바꾸면 줄줄이 에러나잖아」. 소스는 이 진단이 맞다고 말한다 — 그리고
**부분적으로는 이미 고쳐져 있다.**

### 4.1 소비자별 전수 — 무엇을 `table_config`에서 필요로 하고, 바뀌면 얼마나 시끄러운가

`known_tables` 인자를 받는 로더 = 로드 시점 대조가 있는 표면.

| 소비자 | `table_config`에서 필요한 사실 | 검사 시점 | **얼마나 시끄러운가** | 근거 |
|---|---|---|---|---|
| `enrichment_rules.json` | source·derived 테이블 등록 여부 + 참조 컬럼 존재 | **로드** | 🟢 **큼.** 규칙 1건 거절 + 사유 + `/admin/config/resolve` 표면 | `enrichment_config.py:441-445` |
| **`ontology_mapping.json`** | 테이블 등록 여부 + `identity`/`props`/`event_time_column`/`target_identity_from` 컬럼 존재 | **로드** | 🟢 **큼.** 테이블 매핑 **통째 거절** + `/graph/mapping-summary`의 `rejected[]` | `ontology_config.py:256-271` |
| `virtual_join_rules.json` | 양쪽 테이블 등록 + join_key/expose 컬럼 존재 | **로드** | 🟢 **큼.** 규칙 거절 + 코드 붙은 사유 | `virtual_join_config.py:330-344` |
| `notation_rules.json` | 컬럼 존재 | **로드** | 🟢 큼 | `notation_norm.load_notation_rules(known_tables=)` |
| `map_overlay_config.json` | 바인딩이 지목한 x/y/val/key 컬럼이 모델에 존재 | **질의 시** | 🟡 **중간.** 이름 붙은 거절(`binding_unresolved`)이지만 **그 맵을 읽을 때에야** | 로더 `map_overlay.load_overlay_config(path)` — **`known_tables` 인자 없음** |
| `chain_rules.json` | `source_table`/`map_table`/`x_col`/`y_col`/`index_col`/`primary_selector.group_columns` | **없음** | 🔴 **조용.** 로더는 cascade 그래프만 검증 | `chain_ingestion_worker.load_chain_rules():297` — 인자 없음 |
| `bonding_plan_config.json` | `sources.*.table` + `columns.*` 역할별 컬럼 | **질의 시** | 🔴 **조용.** `DYNAMIC_TABLES.get()` → `None` → 역할이 `missing`으로 열화. 사유는 dry-run 화면을 열어야 보임 | `bonding_plan.load_bonding_plan_config(path)` — 인자 없음 |
| `transfer_plan_config.json` | 동일 | **질의 시** | 🔴 **조용** | `transfer_plan.load_transfer_plan_config(path)` — 인자 없음 |

**4 대 4.** 패턴은 실재하고, 절반에 깔려 있다.

### 4.2 **정정 — 참조 구현은 `map_overlay`가 아니라 우리(온톨로지)다**

브리핑이 준 대비표는 `map_overlay`를 "자기 기대를 검증하고 말하는" 쪽,
`ontology_mapping`을 "조용한" 쪽에 놓았다. **측정은 반대에 가깝다.**

- **로드 시점 대조의 참조 구현은 `ontology_config.py:256-271`이다.** 컬럼이 사라지면
  그 테이블의 온톨로지가 **통째로** 거절되고, 그 거절이 `/graph/mapping-summary`에
  `{scope, table, reason}`으로 **숫자와 함께** 나온다. `map_overlay`에는 그런 로드 시점
  검사가 없다.
- 코드가 이 경로의 위험까지 스스로 적어 놓았다 — `ontology_config._record:289-297`:
  *"rename a column and that table's ontology disappears **wholesale**, with one WARNING and
  no number anywhere"*. 수집기(`rejections`)와 `/graph/mapping-summary`가 바로 그 문장에
  대한 대응이다.

**그러면 왜 `core_wafer_map` identity 이동이 온톨로지에서 조용했는가.**
**그 변경이 컬럼을 없애지 않았기 때문이다.** identity가 `core_lot/core_slot` → `wafer_id`로
옮겼을 때 `core_lot`과 `core_slot`은 **여전히 `core_wafer_map`에 존재한다.** 존재 검사는
통과한다. 바뀐 것은 **"어느 컬럼이 정체를 구성하는가"**이고, **그 사실을 비교 가능한 형태로
선언하는 표면이 하나도 없다.**

같은 이유로 `map_overlay` 쪽의 거절도 **선언 대조의 결과가 아니었다.** 서베이의 추적
(`Config_map_duplication_survey.md` §5)대로, 낡은 key_columns로 필터가 **성공적으로 만들어지고
0행을 돌려준** 것이 실질이었다. 즉 **한쪽은 값이 안 맞아서 시끄러웠고, 한쪽은 값이 우연히
1:1이라 조용했다.** 이 박스 실측이 그 우연을 보여 준다:

```
core_wafer_map:  distinct wafer_id = 200,  distinct core_lot|core_slot = 200
graph_nodes(Wafer) 중 live wafer_id와 일치 : 200 / 200
graph_nodes(Wafer) 중 core_lot|core_slot와 일치 : 0 / 200
graph_nodes(CoreCell) identity 예: 'BLKCORE0000|1|-1|-30'  (= core_lot|core_slot|core_x|core_y)
graph_nodes 206,987 · graph_edges 413,011 (assy_qa, 2026-08-11)
```

> ⚰️ **[2026-08-14 `2ec78b9` · R-2026-08-14-H] 위 박스의 `graph_nodes`·`graph_edges`는 그 뒤 **DROP**됐습니다** — 이 수치는 **2026-08-11 시점의 기록**이고 다시 재목할 수 없습니다. 본문이 이 측정에서 도출하는 **`ontology_mapping.json`에 대한 권고(§3.3 · §말미)는 소비자가 없어진 선언에 대한 것**이므로 그대로 실행하지 마십시오. 그러나 이 문서의 **중심 판정**(「어휘는 코드, 결합은 현장 선언」)은 저장소 중립이라 **원장 어휘에 그대로 다시 물을 수 있습니다**([CANONICAL_LEDGER_DESIGN §4.2](../architecture/CANONICAL_LEDGER_DESIGN.md)). — doc-keeper


**결론: 두 소비자 다 검사가 있었고, 두 검사 다 이 변경을 볼 수 없는 종류였다.**
필요한 검사는 "컬럼이 있나"가 아니라 **"identity 선언이 서로 같은 것을 가리키나"**다.
그건 §6·§8의 대상이다.

### 4.3 검사가 있어야 할 자리 — 하나가 아니다

| 자리 | 무엇을 잡나 | 비용 | 못 잡는 것 |
|---|---|---|---|
| **config 로드 시점** (`known_tables=`) | 컬럼·테이블 참조 파탄. 즉시, 이름으로 | 이미 4곳에 있음. 나머지 4곳은 로더 시그니처 + 호출자 수정 | 컬럼이 살아 있는 의미 변경(§4.2) |
| **부팅** (`schema_drift` 옆) | 배포된 박스의 실제 상태 | `f6406b1`이 이미 14ms로 측정 | 부팅 후 config 핫리로드 |
| **테스트 스위트** | 개발자 기계에서 선제적으로 | 이미 있음(`test_system_schema_drift.py`) | **배포 대상 DB를 못 봄**(§2 ③) |
| **배포 전 단계** | 옮기기 전에 옮겨질 것을 검사 | **부분적으로 있다** — `server/scripts/check_schema_drift.py`는 종료 코드를 내고 자기 docstring이 *"Suitable for a deploy gate: run it after migrating and before letting traffic in"*이라고 적는다. **아무 배포 절차에도 걸려 있지 않을 뿐** | config 축은 없음 |

**`f6406b1`의 부팅 점검은 올바른 집이되 층이 하나 아래다.** 그것은
"모델 ↔ DB"를 묻는다. 필요한 건 같은 자리에서 **"config ↔ 그 소비자들"**도 묻는 것이다.
두 질문은 같은 모양이고 같은 배너 어휘를 쓸 수 있다. **`config_resolve_report.py`가 이미
그 어휘를 갖고 있다** — `effective` / `ineffective` / `rejected`, 사유는 닫힌 4개 단어
(`not_declared` · `mapping_unavailable` · `scope_unresolved` · `not_reached`),
확장은 `_RESOLVERS`에 등록기 하나. **오늘 등록된 도메인은 10개 중 3개**
(enrichment · virtual_join · notation, `config_resolve_report.py:696-700`).

### 4.4 의존 선언은 손으로 쓰면 안 된다 — 파생 가능한가

**대체로 가능하다. 그리고 4개 표면은 이미 파생이다** — `known_tables=`를 받는 로더는
**자기 선언을 읽어 참조 컬럼 목록을 계산한다**(예: `ontology_config.py:262-268`은
`identity + props + event_time_column + target_identity_from + edge props`를 모아
`referenced` 리스트를 만든다). 손으로 적는 목록이 아니다.

나머지 4개도 같은 방식이 가능하다 — 각 config의 스키마가 "이 키의 값은 컬럼명"임을
알고 있기 때문이다(`bin_map.columns.x`, `chain_rules.*.x_col`, `sources.*.table` …).
**손 목록이 되는 순간 §2 ③과 같은 실패로 돌아간다는 것을 명시해 둔다.**

한 곳은 예외로 남는다: `crud.py:3931`의 `validate_ontology_mapping(raw, known_tables=None)` —
`check_needs_rollback`용 캐시가 **일부러 컬럼 검증을 끈다.** 같은 파일에 두 독자가 있고
**서로 다른 엄격도로 읽는다**는 뜻이다. 어느 설계든 이 갈래를 알고 있어야 한다.

---

## 5. 선택지와 절충 — 이 코드베이스의 제약에 대고 판정한다

제약: config 주도 동적 테이블 · gitignore된 config · 단일 박스 운영자 · DBA 없음 ·
Windows + PostgreSQL · 무인 재기동이 정상 상황.

### A. 순서 있는 버전 마이그레이션 + 실행 원장

`0001_x.sql`, `0002_y.sql` … + `schema_migrations` 테이블.

- **얻는 것:** "돌았나?"에 답이 생긴다. 저장소를 처음부터 재생하면 같은 스키마가 나온다.
  증상 ①②를 구조적으로 닫는다.
- **잃는 것/비용:** 기존 6개 파일을 순서 안으로 넣어야 하고, `add_dt_log_trigger_indexes.sql`
  처럼 **일부러 안 돌리는 파일**의 자리를 정해야 한다. `CONCURRENTLY`는 트랜잭션 밖에서
  돌아야 해서 러너가 그걸 알아야 한다.
- **이 코드베이스에서:** **동적 테이블에는 못 쓴다.** 동적 테이블의 스키마는 운영자의
  `table_config.json`에서 오고 배포마다 다르다. 버전 마이그레이션이 덮을 수 있는 것은
  **시스템 테이블뿐**이고, 그건 이미 `SYSTEM_TABLE_COLUMNS`가 그은 경계와 같다.
  → **부분 해답. 절반만 덮는다.**

### B. 선언적 목표 상태 + 차이 계산기(differ)

기대 스키마를 선언하고 러너가 차이를 계산해 적용.

- **이 코드베이스에서:** **차이 계산기는 이미 있다** — `schema_drift.check()`가
  정확히 그것이고, 결과에 `ALTER TABLE ... ADD COLUMN` 문장까지 만든다
  (`_add_column_ddl:197`). 없는 것은 (a) 타입 비교 (b) 적용. **적용을 자동화하지 않은 것은
  의도된 판단이다**(모듈 헤더: *"Remedies are REPORTED for a human to run, deliberately"*).
- **절충:** 자동 적용은 무인 재기동에서 위험하고, 이 저장소는 그 위험을 이미 한 번
  판정했다(`f6406b1`: 드리프트로 부팅을 막지 않는다). **차이 계산은 확장하되 적용은
  사람에게 남기는 것이 이 저장소의 기존 판정과 일관된다.**
- **동적 테이블에는 이쪽이 맞는다** — ② 경로가 이미 "선언 대비 없는 컬럼을 ADD"라는
  선언적 differ다. **타입과 실패 보고만 없다.**

### C. 버전 있는 스키마 패키지

스키마를 배포 산출물로 패키징.

- **이 코드베이스에서:** `product_tables.py`가 이미 그 형태다 — 추적되는 코드 모듈이
  제품 소유 선언을 나르고, 설치기가 사이트에 심고, `.sample`은 같은 모듈에서 **생성**된다.
- **한계:** 5개 엔트리, 한 파일에만. **확장 비용이 낮다는 것이 이 옵션의 최대 장점**이고,
  브리핑의 「이미 있는지 먼저 본다」 규율이 가리키는 곳이다.

### D. 온톨로지를 데이터로 vs 코드로

- **데이터로**(오늘): `ontology_mapping.json`. 운영자가 고칠 수 있고 핫리로드된다. 대신
  git 밖.
- **코드로**: `product_tables.py`처럼 모듈에. 추적되고 이행되지만 **사이트가 테이블명을
  바꿀 수 없게 된다** — 그런데 §3.3대로 온톨로지 엔트리의 최상위 키가 **사이트 테이블명**이다.
  통째로 코드에 넣는 것은 성립하지 않는다.
- **판정: 섞어야 한다.** 어휘(label · edge type · node_class)는 코드, 결합(어느 테이블의
  어느 컬럼)은 데이터. §6.

---

## 6. 온톨로지 페이로드 — 스키마와 **함께** 가는가, 따로 가되 호환 검사를 붙이는가

**논거를 세우고 답한다: 따로 가되, 호환 검사가 아니라 `table_config`에 대한 로드 시점
대조로 묶는다. 그리고 그 대조에 `identity` 축을 하나 더한다.**

### 6.1 함께 갈 수 없는 이유

온톨로지 매핑은 스키마의 **투영**이 아니라 **소비자**다. 최상위 키가 source 테이블명이고,
identity 성분이 전부 raw 컬럼명이다(`Ontology_domain_context_review.md` §4의 3개 근거).
그리고 그 source 테이블은 **사이트 소유**다. 스키마 페이로드에 온톨로지를 담으면
**사이트가 못 바꾸는 것을 사이트 데이터에 붙이게 된다.**

### 6.2 따로 갈 때 이미 있는 안전장치, 그리고 없는 축

**있는 것 —** 로드 시점 컬럼 존재 대조(`ontology_config.py:256-271`), 닫힌 키 집합
(`_ALLOWED_TABLE_KEYS` / `_ALLOWED_NODE_KEYS` / `_ALLOWED_EDGE_KEYS`) — 미지의 키는
**그 테이블 매핑 전체를 거절**하고, 거절이 `/graph/mapping-summary`에 숫자와 함께 나온다.
**이건 나머지 4개 표면에 없는 수준의 방어다.**

**없는 것 —** identity 축. 오늘 살아 있는 사례:

```
ontology_mapping.core_wafer_map.node.identity = ["core_lot","core_slot","core_x","core_y"]
table_config.core_wafer_map.map_key_columns   = ["wafer_id"]          <- 이동함
map_overlay_config...key_columns              = ["wafer_id"]          <- 이동함
```

네 컬럼이 전부 존재하므로 **존재 검사는 초록**이다. 그래프는 `CoreCell(core_lot|...)`을
계속 찍어 내고 화면은 멀쩡해 보인다.

**다만 이것이 자동으로 결함인 것은 아니다** — `wafer_id`는 *웨이퍼*를 식별하고
`core_lot|core_slot`은 *위치*를 식별한다. 두 입도가 진짜로 다를 수 있고, 그 판정은
이름으로 결정되지 않는다(`Ontology_domain_context_review.md` §9-8이 그 질문을 열어 둔 상태다).
**⚠️ 그리고 수리 레인이 지금 이 철자를 교정 중이다. 이 문서는 그 값이 무엇이 되든
"교차 대조가 없다"는 사실만을 근거로 삼는다.**

### 6.3 그래서 필요한 것 — `identity_of(table)` 단일 질문

지금 "이 테이블 하나를 무엇이 식별하는가"는 **다섯 곳**에 따로 적혀 있다
(서베이 §5: `chain_rules.reference.map_id_template` · 저장된 `wafer_map_metadata.map_id` 행 ·
`map_overlay_config...key_columns` · `table_config.map_key_columns` ·
`ontology_mapping.node.identity`). **어느 둘도 서로를 대조하지 않는다.**

필요한 건 새 파일이 아니라 **파생 가능한 질문 하나**: 각 표면이 자기 선언에서
`identity_of(table)`을 계산해 내놓고, 대조는 그 결과들 사이에서 한다. 4개 표면은 이미
`referenced`를 계산하고 있으므로 **같은 자리에 함수 하나가 더 붙는 모양**이다.

### 6.4 저장된 값 — `map_contracts` 제안이 못 닫는 것(G1)

`PROJECT_STATUS.md` 2026-08-10의 `map_contracts` 제안(surface 단위 단일 선언,
`dt_log:dt` / `dt_log:core` 분리, `map_id_template`·중복 `key_columns` 제거)은
**선언 중복에 대해서는 옳다** — 특히 한 테이블의 두 좌표계를 surface로 쪼개는 부분은
`dt_core_view`라는 물리 테이블이 존재하는 이유 자체를 재고 가능하게 만든다.

**그러나 실제로 깨진 것은 선언이 아니라 저장된 행이었다.** 서베이 실측:
`core_wafer_map` 메타데이터 200행 중 **200행이 낡은 철자**, **0행이 현재 `wafer_id`와 일치**.
그리고 `[D5]` 이후 메타 행 부재는 **정상 상태**라 시스템은 거절하지 않고
**빌린 geometry로 채점한다.** 즉 선언을 하나로 합치는 설계는 **시끄러운 실패를 없애고
조용한 실패를 남긴다.**

**따라서 어떤 identity 단일화 설계든 "옛 철자로 저장된 행은 어떻게 되는가"에 대한 답
(마이그레이션이든, 저장된 distinct 값 ↔ 현재 identity가 합성할 값의 대조기든)을
같이 갖고 와야 한다.** 이것이 §8 권고가 "검출"에서 멈추지 않는 이유다.

### 6.5 8개 표면의 미래 — 정준 계층이 생기면

**붕괴하지 않는다. `table_config`만 raw 형태로 남고 나머지가 그 위로 올라간다.**
`table_config`는 source→canonical 매핑 그 자체이고, 나머지 7개는 canonical 위의 바인딩/규칙이다
(`Ontology_domain_context_review.md` §10). 그러므로:

- `map_contracts`는 **자기만의 메커니즘이 아니라 정준 seam의 첫 인스턴스로** 만드는 것이 맞다.
  surface = canonical 개체의 좌표 표현.
- 나머지 7개는 **삭제도 파생도 아니고, 선언된 우선순위를 가진 override로** 남는다 —
  이미 그렇게 동작하고 있고(서베이 §1의 "resolution order, first listed wins"),
  없는 것은 **그 우선순위가 선언되어 있고 응답에 표시되는 것**이다. 오늘은 체인이
  enrichment 규칙의 `source_table`을 조용히 덮고, chain의 threshold가 config의 것을
  조용히 덮는다(서베이 §2-④⑥).

---

## 7. 드리프트 매니페스트를 손 목록이 아닌 것으로

**계산 가능하다. 그리고 계산하는 코드가 이미 있다.**

`schema_drift._declared()`(`schema_drift.py:107-144`)가 정확히 그 일을 한다 —
`database.models`를 import하고 `init_dynamic_models`로 동적 테이블까지 등록한 뒤
`Base.metadata.tables`에서 **테이블별 컬럼 전체**를 뽑는다. `test_system_schema_drift.py`의
`_live_system_tables()`도 같은 것의 축소판이다.

즉 `SYSTEM_TABLE_COLUMNS`는 **이미 계산 가능한 값을 손으로 옮겨 적은 것**이다.

**바꿀 때 지켜야 할 것 세 가지:**

1. **게이트의 의미가 "새 컬럼이 생겼다"에서 "새 컬럼이 마이그레이션 없이 생겼다"로 옮겨야 한다.**
   단순히 파생물끼리 비교하면 게이트는 항상 초록이 되어 **아무것도 아닌 것**이 된다.
   비교 상대는 **`server/migrations/`가 실제로 추가하는 컬럼 집합**이어야 한다 —
   그리고 그 집합을 스캔하는 코드도 이미 있다(`schema_drift._owner_from_sources:89-104`,
   `f6406b1`이 손 지도를 대체할 때 만든 것).
2. **비용:** 새 파일 없음. `_owner_from_sources`의 얕은 매칭(문자열 3개 포함)은
   **오탐이 싸다**는 자기 주석의 판단을 그대로 물려받는다. 게이트로 쓰면 오탐이 비싸지므로
   판정 강도(경고 vs 실패)를 정해야 한다 — **이것이 이 슬라이스의 유일한 실질 설계 결정이다.**
3. **동적 테이블 제외는 유지한다.** ② 경로가 있으므로 위험 계급이 다르다(§2 ③).

**타입을 더하는 비용은 별개이며 작다.** `_actual()`이 쓰는 `inspect().get_multi_columns()`는
이미 `data_type`을 돌려주고, `_declared()`의 `Column` 객체는 `col.type`을 갖고 있다.
필요한 건 **dialect별 동치 집합**(`string` ↔ `text`/`varchar` 등)이고, 그건 이 문서를 위해
쓴 임시 스크립트에서 이미 동작했다. 어려운 부분은 **동치 판정의 정책**이지 배관이 아니다.

---

## 8. 권고 — 하나

> **`schema_drift.py`를 "보고서"에서 "이 저장소의 기대 상태를 계산하는 단일 자리"로 승격하고,
> 그 자리를 (a) 타입 (b) 마이그레이션 실행 원장 (c) config 소비자 계약, 세 축으로 넓힌다.
> 나머지는 전부 그 한 자리의 소비자가 된다.**

새 메커니즘이 아니다. `f6406b1`이 이미 세운 자리에, 그 커밋이 이미 한 번 내린 판단
(손 지도 → 파생)을 두 번 더 적용하는 것이다.

### 8.1 첫 슬라이스 — 무엇을 만들고 무엇을 증명하는가

**만드는 것:** `schema_drift`에
① **타입 비교**(dialect 동치 집합과 함께),
② **실행 원장**(`schema_migrations` 시스템 테이블 1개 + `server/migrations/` 러너가 기록),
그리고 ③ **`test_system_schema_drift.SYSTEM_TABLE_COLUMNS`를 파생물로 교체**
(비교 상대는 `server/migrations/`가 추가하는 컬럼 집합).

**증명하는 것:**
- 매니페스트는 **기억하는 것이 아니라 계산되는 것**이라는 점.
- 모델 쪽 결함과 DB 쪽 결함이 **같은 자리에서 같은 어휘로** 이름 붙는다는 점.
- `dt_frame` 계열(타입만 바뀐 드리프트)이 **검출된다**는 점 — 오늘은 구조적으로 불가능하다.

**어떻게 검증하는가(이 도메인의 규율대로):**
- **결함 주입.** `dt_frame`을 `double precision`으로 되돌린 격리 DB에 대고 돌려 **빨개지는지**
  확인한다. 빨개지지 않으면 그 축은 아무것도 증명하지 못한다.
- **개수가 아니라 개체 단위 대조.** "N건 발견"이 아니라 "어느 테이블의 어느 컬럼"까지.
- **원장은 두 방향으로.** 안 돌린 마이그레이션이 안 돌았다고 나오는 것과,
  돌린 마이그레이션이 다시 안 돌아가는 것(멱등) 둘 다 별도 케이스로.
- **격리 환경에서만.** `server/scripts/dev_env/devenv.py`. 착수 시 `:8081` 점유를
  먼저 확인한다(오늘 다른 레인이 stale 프로세스를 발견했다).

### 8.2 두 번째 슬라이스 — config 소비자 계약

`known_tables=`를 나머지 4개 로더(`map_overlay`, `chain_rules`, `bonding_plan`,
`transfer_plan`)에 넣고, 그 결과를 `config_resolve_report._RESOLVERS`에 도메인으로 등록한다.
어휘는 이미 닫혀 있고 계약 벡터(`contracts/config_resolve_report/vectors.json`)가 있다.
**여기에 §6.3의 `identity_of(table)` 축을 같이 얹는다** — 그게 §4.2가 밝힌 진짜 사각지대다.

### 8.3 세 번째 슬라이스 — 온톨로지의 이행

`product_tables.py` / `install_product_tables.py`의 소유권 모델을 온톨로지로 확장하되,
**입도를 엔트리가 아니라 키로 낮춘다**(§3.3): 어휘(`label`·`edge type`·`node_class`)는
product-owned로 코드에 올리고, 결합(`identity`·`props`·테이블명)은 site-owned로 남긴다.
`.sample` 생성과 일치 단언은 `test_install_product_tables.py`의 형태를 그대로 쓴다.

### 8.4 **이 권고가 틀리려면 무엇이 참이어야 하는가**

세 가지. 하나라도 참이면 이 권고는 돈을 잘못 쓰는 것이다.

1. **진짜 병목이 탐지가 아니라 적용이라면.** 사용자가 이미 "드리프트가 났다"는 것은 알고
   있고, 못 하는 것이 **운영 박스에서 안전하게 DDL을 거는 일**이라면, 더 나은 검출기는
   아무것도 사 주지 않는다. 그때 돈은 **순서 있고 원장 있고 멱등인 러너**(§5-A)에 가야 하고,
   그건 다른 작업이다. **이 문서는 그 답을 갖고 있지 않다** — 운영 박스에서 무엇이 실제로
   막히는지에 대한 측정이 여기 없기 때문이다.
2. **`.sample`↔live 동일성이 이 박스만의 사실이라면.** §3.1의 8/10 바이트 동일이 운영에서
   깨져 있고 divergence가 크다면, "방향과 병합 규칙"이 아니라 **재조정(reconciliation) 자체**가
   문제이고 규모가 다르다. **운영 박스에서 같은 비교를 한 번 돌리는 것이 이 문서 다음의
   첫 사실 수집이다.**
3. **정준 계층 결정이 임박했다면.** `ontology_mapping`이 source 테이블 키를 버리고
   canonical 개체 키로 옮기기로 확정되면, §8.2·§8.3이 붙는 표면 자체가 바뀐다.
   그때는 `map_contracts`를 정준 seam의 첫 인스턴스로 먼저 짓고 검사 축을 그 위에 얹는 편이
   싸다(§6.5). **§8.1은 이 결정과 무관하므로 어느 쪽이든 먼저 지을 수 있다.**

---

## 9. 실행 순서

1. **사실 수집 먼저.** 운영 박스에서 (a) `python server/scripts/check_schema_drift.py`
   (읽기 전용) (b) `server/config/*.json` ↔ `*.json.sample` 비교, 두 가지를 돌려 §3.1과
   §2 ①의 실제 상태를 기록한다. **이 문서의 숫자는 개발 박스 것이므로 이 단계 없이는
   규모를 못 정한다.**
2. **§8.1 슬라이스** — 타입 축 + 원장 + 파생 매니페스트. 격리 환경, 결함 주입 검증.
3. **`server/migrations/` 정리** — 순서 부여, `NOT RUN` 파일의 지위 명시, 러너가 원장에 기록.
4. **§8.2 슬라이스** — 나머지 4개 로더에 `known_tables=`, `config_resolve_report` 도메인 등록,
   `identity_of(table)` 축.
5. **저장된 값 대조기**(§6.4 G1) — 저장된 distinct `map_id` ↔ 현재 identity가 합성할 값.
   이게 있어야 identity 단일화가 조용한 실패를 남기지 않는다.
6. **§8.3 슬라이스** — 온톨로지 소유권 분리와 설치기.

---

## 이번에 하지 않는 것

- **`server/config/`를 git에 넣는 것.** 규칙(`LEAD_PM_HANDOFF.md` §2)에는 실제 이유가 있고,
  §3의 실측은 그 규칙이 아니라 **방향과 병합 규칙의 부재**가 문제라고 말한다.
- **드리프트로 부팅을 막는 것.** `f6406b1`이 측정과 함께 반대로 판정했다.
  무인 재기동에서 한 컬럼이 전체 스택을 죽일 수 있다.
- **동적 테이블에 버전 마이그레이션을 적용하는 것.** 그 스키마는 운영자 config에서 오고
  배포마다 다르다. `SYSTEM_TABLE_COLUMNS`가 그은 경계는 옳다.
- **드리프트의 자동 적용(auto-ALTER).** 검출과 적용은 다른 결정이고, 이 저장소는
  "사람이 실행하도록 보고한다"를 이미 명시적으로 골랐다.
- **`ontology_mapping`의 `CoreCell` identity 판정.** 입도가 진짜 다를 수 있고
  (`wafer_id` = 웨이퍼, `core_lot|core_slot` = 위치), 수리 레인이 지금 그 파일을 편집 중이다.
  이 문서는 **교차 대조가 없다는 사실**만 근거로 쓴다.
- **`map_contracts`의 채택/기각 판정.** 선언 중복에 대해서는 옳고 저장된 값에 대해서는
  답이 없다는 것까지가 이 문서의 범위다. 채택은 정준 계층 결정과 함께 내려야 한다.
- **`Wafer` label의 정체 혼재(이슈 #15) 처리.** 이 박스의 `assy_qa`에서는 `Wafer` 1,292개가
  전부 단일 성분 identity이고 `core_lot|core_slot` 형태는 0개다 — **이 스냅샷에서는
  재현되지 않는다.** 별도 확인이 필요하며 이 문서의 주제가 아니다.
