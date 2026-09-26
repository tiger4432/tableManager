# `chain_rules.json` 세팅 — 체인 인제션 룰

> **Status:** 🟢 Living | **Last-verified:** 2026-09-16 «은퇴 1» (통합 선언의 `into.read` 가 «이름으로» 거절된다 — 두 좌석이 `rule_shape.READ_TIME_RETIRED` «한 상수»를 읽고, `read` 는 문법에 남고, 구 선언 파일의 읽기 시점 조인은 그대로 돈다 — `6580c30f`) · 직전 2026-09-16 «후속» (§5-B-bis `enabled` 행 — `ASSY_CHAIN_SYNTHESIZE` 은퇴, 세 파일이 한 이름공간이라 두 번 선언된 이름은 거절, S-234) · 직전 2026-09-16 (§5-B-bis — `into` 는 «택1»: `table` 은 쓰는 조인, `read: true` 는 읽기 시점 조인이라 «체인 규칙이 아니고» 가상 조인 목록에 선다, S-251 · 스켈레톤이 두 문법을 다 들고 raw 응답이 `grammar` 를 말한다, S-241) · 직전 2026-09-15 «후속 2» (`key.unique` 는 워커 웜업이 읽어 «제품이» 세운다 · `key.columns` 는 검사뿐 · 키 식의 저자는 `notation_norm` 하나 — S-240 · S-245) · 직전 2026-09-15 «후속» (고리는 거절 사유가 아니다 — `max_chain_depth` 가 유일한 상한 · 저장 관문과 로더가 «확장기 하나» · join 의 키 접기·층·소급) · 직전 2026-09-15 (§5-B-bis 통합 선언 키 신설 — join · decide · `enabled` 의 두 뜻) · 직전 2026-09-08 00:5x (§5 를 «코드가 읽는 키» 전수로 다시 씀 — 파일 수준·프레임워크·맵퍼 사설 «세 층», `reads`·`slow_warn_ms`·`max_chain_depth`·표 역할 키 추가, «없는 것» 절) · 직전 2026-09-05 (§5 키 표에 `source_table`·`allow_chain_trigger`·`allow_map_metadata_upsert` 세 행 추가 — 그중 마지막이 «둘째 엣지»다) · 직전 2026-08-13 (§5 키 표에 **제거 전략 옵트인 둘**(`allow_replace_map`·`allow_retraction`)과 **`*_job_column` 명시 선언** 행 추가 — `4d5198c`. 셋 다 표에 없어서, `dt_map`처럼 맵 키가 둘인 타깃에서 왜 체인이 이름을 대며 거절하는지 이 문서만으로는 알 수 없었다) | **Owner:** Ingester
> 상위: [폴더 인덱스](./README.md) · 동작 원리 정본은 [chain_ingestion_guide](../chain_ingestion_guide.md) · 절차 요약은 [CONFIG_GUIDE §3-S8](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  worker load: server/chain/ingestion_worker.py:278 load_chain_rules (RULES_PATH :111; missing file -> warning + empty)
    called at startup :787 and re-called on SYSTEM_RELOAD :862; enrichment-derived rules merged :296
  web view: GET /admin/chain/rules (admin-gated) answers BOTH states since 644 - the loader's
    standing rules with rule_state=running, plus the file's declarations that stood nothing
    with rule_state=declared_only. It is no longer 「the file, handed back」.
  mapper cache purge on reload: main.py reload-configs (mappers.* module cache)
-->

## 0. 한눈에 보기 — 규칙 «맨 위»에 적는 칸 (2026-09-26)

전부 규칙 dict 의 «맨 위»에 적습니다. 적지 않으면 아래 「안 적으면」 칸이 답입니다. 자세한 것은 §5-B · §5-B-bis.

⚠️ `allow_replace_map` · `allow_retraction` · `key` 는 `params` 밑으로 옮기지 마십시오 — 옮기면 제품이 못 읽어 허락이 꺼지고 유일 인덱스가 안 섭니다. 로그 `[ChainRules] <규칙>: N cell(s) still written flat — move them under 'params'` 가 이 칸들을 가리키는 것은 경고 쪽 결함이고, 고치는 중입니다(2026-09-26).

**허락 칸** — 켜야 되는 일

| 칸 | 켜면 | 안 적으면 |
|---|---|---|
| `allow_chain_trigger: true` | 다른 체인 규칙(조인 포함)이 쓴 행에도 깨어난다 — 체인 뒤에 체인 | 사람·파일·수집기가 바꾼 행에만 깨어난다. 체인이 쓴 행은 지나간다 |
| `allow_replace_map: true` | 맵퍼가 맵 하나를 «통째로 갈아끼우는» 결과를 낼 수 있다 | 그런 결과는 이름 대어 거절 |
| `allow_retraction: true` | 맵퍼가 «한 출처(출처 칸의 값 하나)가 전에 낸 행만» 거둬들이는 결과를 낼 수 있다 | 거절 |
| `allow_map_metadata_upsert: true` | 맵퍼가 맵 메타데이터(`wafer_map_metadata`)도 고친다. 그 쓰기가 다시 체인을 깨운다 | 메타는 안 고친다 |

- 둘 중 무엇을 쓸지는 «그 맵에 값을 내는 출처가 몇인가»가 정합니다. 하나면 `replace_map`(맵 단위로 지운다), 여럿이면 `retraction`(출처 단위로 지워 남의 값을 안 건드린다). 한 배치에 둘을 같이 내면 거절됩니다.
- 체인이 체인을 깨우는 깊이는 파일 맨 위 `max_chain_depth`(기본 8)가 막습니다.

**그 밖에 자주 쓰는 칸**

| 칸 | 뜻 | 안 적으면 |
|---|---|---|
| `enabled: false` | 규칙을 끈다 | 켜짐 |
| `is_batch: true` | 한 묶음의 행을 표(DataFrame) 하나로 맵퍼에 넘긴다. 맵퍼는 dict «하나»를 돌려준다 | 행마다 한 번 |
| `trigger_columns: [칸, …]` | 이 칸들이 바뀐 변경에만 깨어난다 | 표의 어떤 변경에도 깨어난다 |
| `group_by: [칸, …]` | 한 배치 안에서 이 칸 값이 같은 행끼리 맵퍼 한 번 | 쓴 쪽의 트랜잭션 하나가 한 묶음 |
| `max_group_rows: N` | 같은 규칙의 묶음 여럿을 N 행까지 합쳐 맵퍼 한 번 | 안 합친다 |
| `max_group_attempts: N` | 실패한 묶음을 N 번까지 다시 시도한 뒤 격리 | 파일 맨 위 값, 없으면 기본값 |
| `idempotent: false` | 두 번 돌면 안 되는 맵퍼 — 한 번 실패하면 바로 격리, 리플레이도 `force` 없이는 안 돈다 | 다시 시도한다 |
| `key: {unique: true}` (조인) | 원천 표(`on.table`)의 조인 키에 제품이 유일 인덱스를 세운다. 중복 값이 있으면 안 세우고 값·건수를 로그에 낸다 | 인덱스 없이 돈다. 답이 둘인 행만 건너뛴다 |

### 0-1. 예시 — 어떨 때 무엇을 적나

아래 규칙 이름·표 이름은 출하 샘플(`server/config/sample/chain_rules.json.sample`)의 것입니다.

⚠️ `@mapper` 로 쓴 맵퍼는 DataFrame 을 돌려주고 «덮어쓰기(upsert)만» 합니다. ②·③ 의 지우는 봉투는 못 냅니다 — dict 를 돌려주면 `MapperContractError` 로 거절됩니다. 지워야 하는 맵퍼는 `(db, payloads, rule)` 모양으로 손으로 씁니다. 허락 칸은 어느 쪽이든 «규칙에» 적습니다 — 맵퍼가 대신 켜 주지 않습니다.

**① 체인이 쓴 값에 이어서 돌게 하고 싶다 → `allow_chain_trigger`**

조인이 `dt_inventory` 에 확정 lot·slot 을 쓰고, 그 값이 들어오면 `dt_map` 을 다시 만들고 싶을 때. «이어서 도는 쪽» 규칙에 적습니다.

```json
{
  "name": "dt_inventory_to_standard_dt_map",
  "trigger_table": "dt_inventory",
  "target_table": "dt_map",
  "allow_chain_trigger": true
}
```

- 안 적으면 사람이 `dt_inventory` 를 고칠 때만 돌고, 조인이 쓴 값에는 안 돕니다. 「이 규칙이 왜 안 도나」의 가장 흔한 답입니다.
- 트리거 표와 타깃 표가 같은 규칙에는 켜지 않습니다 — 자기가 쓴 행에 다시 깨어납니다.
- A → B → A 처럼 돌아오는 고리는 오류가 아니고, `max_chain_depth` 에서 끊깁니다.
- ⚠️ 자동 확정(auto-confirm)이 쓴 행은 지금 이 칸 없이도 규칙을 깨웁니다 — 알려진 결함입니다(2026-09-26).

**② 맵 하나를 이 규칙 «혼자» 채우고, 매번 통째로 다시 계산한다 → `allow_replace_map`**

`core_usage_map` 처럼 한 맵을 이 규칙만 쓰고, 입력이 바뀌면 맵 전체를 다시 계산해 «이번에 안 나온 셀은 지워야» 할 때.

```json
{ "name": "dt_log_to_core_usage_map", "target_table": "core_usage_map", "allow_replace_map": true }
```

맵퍼는 맵 하나를 «범위»와 함께 돌려줍니다:

```python
return {"batches": [{"target_table": "core_usage_map", "replace_map": True,
                     "scope": {"core_wafer": wafer}, "updates": cells}]}
```

- 봉투 없이 행만 돌려주면 덮어쓰기(upsert)만 됩니다 — 지난번에만 있던 셀이 남습니다.
- 칸 없이 이 봉투를 내면 `rule '<이름>' returned scoped batches without allow_replace_map or allow_retraction` 으로 거절됩니다.

**③ 맵 하나를 «여러 출처»가 채우고, 한 출처만 다시 계산한다 → `allow_retraction`**

`dt_map` 한 장(lot, slot)을 잡(`dt_job`) 여럿이 채울 때. 잡 하나를 다시 계산하면 «그 잡이 전에 냈는데 이번에 안 나온 셀»만 지워야 합니다.

```json
{ "name": "dt_inventory_to_standard_dt_map", "target_table": "dt_map", "target_job_column": "dt_job", "allow_retraction": true }
```

```python
return {"batches": [{"target_table": "dt_map",
                     "retract": {"source_column": "dt_job", "source_value": job_id},
                     "updates": cells}]}
```

- 여기서 ②(`replace_map`)를 쓰면 둘째 잡이 첫째 잡의 셀을 지웁니다(2026-08-13 실측: 첫 파생에서 3 행 전부).
- 사람이 고친 셀은 지우지 않습니다. 한 출처가 가진 행의 절반 넘게 지우게 되면 거절하고 그 사실을 로그에 남깁니다.

**④ 맵 셀과 함께 그 맵의 메타데이터도 고친다 → `allow_map_metadata_upsert`**

맵퍼가 맵의 프레임·좌표식 같은 메타데이터(`wafer_map_metadata`)도 같이 내야 할 때. 맵퍼는 `map_metadata_updates` 를 함께 돌려줍니다.

```json
{ "name": "dt_inventory_to_standard_dt_map", "allow_map_metadata_upsert": true }
```

- 이미 등록된 맵의 메타만 고칩니다. 없는 메타를 새로 만들지는 않습니다.
- 그 쓰기도 체인이 쓴 것이라, `wafer_map_metadata` 를 트리거로 하는 규칙은 ①의 `allow_chain_trigger` 가 있어야 이어서 돕니다.

**⑤ 조인 원천이 키마다 값 하나여야 한다 → `key.unique`**

`on.table` 의 조인 키(`join.on` 의 `right`)가 한 값에 한 행이어야 할 때. 유일 인덱스는 제품이 세웁니다 — 운영자는 DB 를 만지지 않습니다.

```json
{
  "name": "sample_unified_join",
  "on": { "table": "dt_job_attribution" },
  "derive": { "kind": "join", "join": { "on": [{ "left": "dt_job", "right": "dt_job" }], "take": ["dt_lot_confirmed"] } },
  "into": { "table": "dt_inventory" },
  "key": { "unique": true }
}
```

- 원천에 이미 중복이 있으면 인덱스를 안 세우고 그 값과 건수를 로그에 냅니다. 중복을 치운 뒤에는 앱을 다시 띄워야 다시 시도합니다 — 리로드만으로는 같은 프로세스가 지난 답을 기억합니다(`chain/unique_key.ensure_once`).

## 1. 언제 이 파일을 만지는가

- **테이블 A의 변경이 테이블 B를 자동 갱신하게 만들 때** (trigger→target→mapper 체인)
- 기존 룰을 끄거나(`enabled: false`) 배치/단건 모드를 바꿀 때
- 인리치(결손 보정) 규칙도 **여기에** `derive: {kind: "decide"}` 로 씁니다 — §5-B-bis. ⚰️ 2026-09-24 `enrichment_rules.json` 은퇴(소유자 「enrich.json 아예 삭제」)

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **맵퍼 함수 먼저**: `server/mappers/<module>.py`에 함수를 배치합니다(어드민 Monaco 에디터로 `.py` 편집 가능 — `POST /admin/scripts/code`는 `ASSY_ADMIN_TOKEN` 미설정 시 503).
3. **전제 확인**: `trigger_table`·`target_table`이 `table_config.json`에 선언돼 있어야 합니다.
   🔴 **`allow_map_metadata_upsert`를 쓸 룰이면 표가 «셋»입니다** — 그 룰은 맵 메타데이터 표
   (`wafer_map_metadata`)에도 쓰고, 그 쓰기가 **자기 체인 이벤트를 냅니다.** 즉 그 표를
   `trigger_table`로 삼는 룰이 깨어나므로 **순환 검사의 꼭짓점**이기도 합니다(§5 표 참조).
4. 파일이 없으면 `chain_rules.json.sample` 복사. `rules[]` 배열에 항목 추가:

   ```json
   {
     "name": "production_to_inventory_reservation_batch",
     "trigger_table": "production_plan",
     "target_table": "inventory_master",
     "mapper_module": "mappers.production_mapper",
     "mapper_function": "reserve_materials_batch_df",
     "is_batch": true,
     "enabled": true
   }
   ```
5. 저장 후 **리로드가 필수**입니다 — 워커는 기동 시 + SYSTEM_RELOAD 시에만 룰을 다시 읽습니다:

   ```bash
   curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"
   ```

   (`mappers.*` 모듈 캐시도 함께 퍼지되므로 맵퍼 코드 수정도 이걸로 반영됩니다.)

## 3. 반영 확인

1. `GET /admin/chain/rules` (`X-Admin-Token` 필요) — 룰이 보이는지. ⚠️ 이 뷰는 **「도는 규칙」과 「적혀 있지만 안 선 선언」을 «둘 다»** 답합니다(판정 644·656) — 칸은 `rule_state`(`running` / `declared_only`)입니다. 「없다」와 「꺼짐」이 같은 픽셀이 아닌 것이 이 라운드의 핵심입니다. 워커가 «실제로 실은 것»은 여전히 체인 워커 로그로 확인하십시오.
2. **워커 반영의 증거는 체인 워커 로그**: 리로드 후 룰 재로드/enrichment 병합 로그(`[Enrichment] Synthesized ...` 등)가 새로 찍히는지.
3. `GET /admin/mappers/list` — 맵퍼 모듈·함수가 열거되는지.
4. 왕복 검증: trigger 테이블에 행을 넣어 target 테이블이 갱신되는지 + `GET /admin/outbox/failed`에 실패가 쌓이지 않는지.

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore chain_rules_<yymmdd>.json.bak --yes
```

복원 후 **다시 `reload-configs`** (워커가 옛 룰로 돌아가야 하므로). 이미 잘못 전파된 target 데이터는 룰 복원으로 돌아오지 않습니다 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조 — «코드가 읽는 키» 전수 (2026-09-08 00:5x 실측, `git grep` 추적 파일 기준)

> 🔴 **옵션은 «두 층»이다.** 프레임워크가 읽는 키(아래 표, 닫힌 집합)와 «맵퍼가 스스로 읽는» 키(§5-bis, 맵퍼마다 다름).
> 워커는 규칙 dict «통째로» 맵퍼에 넘기고(`run(db, payloads, rule)`), 맵퍼 사설 키는 **검증하지 않는다** — 오타는 조용하다.
> 컬럼 이름 키만 `chain_bindings.resolve_column` 이 «이름 대어» 거절한다.

### 5-A. 파일 수준 (`chain_rules.json` 최상위)

| 키 | 읽는 곳 | 의미 · 기본값 |
|---|---|---|
| `max_chain_depth` | `event_constants.max_chain_depth` | 체인이 체인을 깨우는 «홉 상한». 양의 정수 아니면 **기본 8**. 깊이 초과 행은 `[Chain Depth]` 로 이름 대어 거절되고 «끝난 것»으로 표시된다(2026-09-06). 🔴 **[2026-09-15 판정 402] 고리의 «유일한» 상한이다** — 규칙 고리(`dt_log → dt_inventory` 맵퍼 · 되돌아오는 join)는 «모양»이지 오류가 아니라 로드·저장 어디서도 거절되지 않고, 순서는 «선언 순»이며, 로그는 프로세스당 trail 당 한 번(`[ChainRules] 고리: … 다음: 없음`). 뒤따르기 랩도 이 상한을 만난다(S-249 — 종전엔 홉을 안 실어 그 길은 «무한»이었다) |
| `rules[]` | 워커 로더 | 규칙 목록. 아래 5-B |
| `__comment` · `_*_comment` | 아무도 안 읽음 | 주석 자리 |

### 5-B. 규칙 수준 — 프레임워크 키 (`rules[]` 항목)

| 키 | 읽는 곳 | 의미 · 기본값 |
|---|---|---|
| `name` | 워커 · 리플레이 · bindings · 큐 패널 | 규칙 식별자. 로그·화면·소급 실행의 «인자»가 이 이름이다 |
| `enabled` | 워커 | `false` 면 비활성. **생략 = 켜짐**. 꺼진 규칙은 순환 검사 그래프에 안 들어가고, 순서 유도(`chain/rule_order`)도 꺼진 규칙·`follow_up` 규칙을 엣지로 안 센다(2026-09-15) |
| `trigger_table` | 워커 · 리플레이 · bindings(역할 read) | 이 표의 변경이 발화. 순환 검사의 «엣지 출발점». 🔴 **정확히 한 트리거** |
| `target_table` | 워커 · 리플레이 · SDK · bindings(역할 write) | 맵퍼 행이 가는 표. «엣지 도착점». `@mapper` 는 «이 선언»에서 비즈니스 키 층을 정한다 — 규칙이 안 주면 데코레이터 인자로 |
| `source_table` | bindings(역할 read) · 맵퍼 | 맵퍼가 «읽는» 표. 엣지가 «아니다» — `trigger_table` 과 뜻이 겹쳐 보여 바꿔 읽기 쉽다 |
| `mapper_module` / `mapper_function` | 워커 · 리플레이 | `server/mappers/<module>.py` 의 함수. 🔴 맵퍼 파일은 gitignore(`.sample` 만 출하) |
| `is_batch` | 워커 · 리플레이 | `true` = DataFrame 배치 모드(트랜잭션 그룹 하나를 한 번에). 🔴 배치 맵퍼는 dict «하나»를 돌려준다 — 목록을 주면 오류 없이 `mapper_items: 0` |
| `allow_chain_trigger` | 워커 | 체인이 만든 이벤트(`source_name: "chain_ingestion"`)를 «받겠다»는 옵트인. 없으면 지나감. 순환 검사가 보는 엣지는 «이 옵트인이 걸린 것»뿐. 깊이 상한은 5-A |
| `allow_map_metadata_upsert` | 워커 · 리플레이 | 맵퍼가 «맵 메타 봉투»(`map_metadata_updates`)를 낼 수 있게. 🔴 그 쓰기는 `wafer_map_metadata` 에 착지하며 «자기 체인 이벤트를 낸다» = 둘째 엣지(2026-09-04). 2026-09-07 부터 «자동 등록»은 은퇴(S-38) — 등록된 메타만 갱신 |
| `allow_replace_map` | 워커 · `dt_map_derivation` | 맵 단위 «전량 교체» 봉투 옵트인. 없이 내면 거부 |
| `allow_retraction` | 워커 · `dt_map_derivation` | 출처 단위 «철회» 봉투 옵트인. 🔴 한 배치에 `replace_map` 과 `retract` 을 같이 실으면 거부(2026-08-13). 둘 중 무엇은 «그 맵의 생산자가 하나인가 여럿인가»가 정한다 |
| `slow_warn_ms` | 워커 · 리플레이 (`event_constants.slow_warn_ms`) | 이 규칙의 맵퍼 실행·철회가 «느리다»고 경고할 문턱(ms). 양의 정수 아니면 경고 한 줄 뒤 기본값. 「느리다」는 이 선언이 정한다 — 캡 맞음 ≠ 느림 |
| `reads` | `chain_bindings.READS_KEY` (순서 가드, C-3) | 위 표 키로 «표현 못 하는» 읽기 표 목록(예: `load_map_meta` 가 여는 `wafer_map_metadata`). 🔴 **목적마다 새 키를 만들지 않는다** — 새 읽기는 여기 «값»으로. 순서는 이 선언에서 «도출»된다(의존을 적지 않고 «읽는 표»를 적는다, 판정 61) |
| `map_table` · `inventory_table` · `derivation_source_table` · `metadata_target_table` | bindings `RULE_TABLE_KEYS`(역할 read) · 각 맵퍼 | 맵퍼가 «여는» 표 이름들. 순서 가드가 «읽기»로 센다. ⚠️ `metadata_target_table` 은 이름과 달리 «소스»(read)다 — 개명 가부는 S-29(소유자) |
| `reference` `{table, …}` | bindings `REFERENCE_BLOCK` · `core_alignment_mapper` | 실행 시점에 map_id 가 정해지되 «표 집합»은 선언인 참조. 순서 가드는 «표»만 본다 |
| `*_job_column` (`trigger_`·`source_`·`target_`·`inventory_`·`reference_`) · `job_column` | `chain_bindings.resolve_column` | 잡 컬럼 이름의 «명시 선언». 미선언이면 `table_config`(`map_key_columns` 단일 컬럼 → `business_key`)에서 유도, 그래도 없으면 «이름 대어 거절». 🔴 `map_key_columns` 가 둘 이상인 타깃은 «반드시» 선언 |

### 5-B-bis. 통합 선언 키 — `derive` 가 있는 규칙 (S-237 join · S-239 decide, 2026-09-15)

`derive` «한 칸»이 새 문법의 판별이다. 있으면 `chain/rule_shape` 가 오늘의 규칙 dict 로 번역하고, 없으면 위 5-B 그대로다. 모양·절차는 `RUN.md` §5(쓰는 조인) · §5-bis(읽기 조인), 왜는 [BASIS §0-bis](../../architecture/BASIS.md).
🔵 **[2026-09-16 S-241 `0dda6f08` · S-241-b `7c81c6d5`] chain 탭의 폼이 이 문법을 «그린다».** 스켈레톤(`chain_bindings.skeleton()`)이 `root`(5-B 평면)와 `unified_root`(`on`/`derive`/`into`/`key`/`limits`) «둘»을 들고, `GET /admin/chain/rules/raw?name=` 이 그 규칙이 어느 쪽인지 **`grammar: flat|unified`** 로 말한다(판별은 여기서도 `derive` 가 dict 인가). `derive`(join·decide·mapper) 와 `into`(table·read) 는 «택1» 노드(`oneOf`)이고 칸 이름은 이 파일이 아니라 `rule_shape`·`join_into` 의 상수에서 «생성»된다 — 문법에 칸이 늘면 폼도 «같이» 는다. 가지의 칸은 «가지 키 밑»에 산다(`derive: {kind:'join', join:{…}}` · `into: {table: 'dt_x'}` — 판정 411).
🔴 **번역기는 `rule_shape.expand_declaration` «하나»이고 로더와 어드민 raw 저장 라우트(`POST /admin/chain/rules/raw`)가 같이 부른다**(S-244 `00da7e91`) — 저장 버튼은 «로더가 세울 규칙»을 판정하지 날것을 판정하지 않는다(종전엔 `trigger_table` 없음·`derive` 모름으로 저장에서 거절되고 같은 파일로 부팅은 됐다). 파일에는 운영자가 적은 그대로 남고 번역본은 «판정에만» 쓴다. 소급은 [BACKFILL_GUIDE §0](../BACKFILL_GUIDE.md) — 선언된 join 은 왼쪽 규칙에 R1.

| 키 | 읽는 곳 | 의미 |
|---|---|---|
| `derive.kind` | `rule_shape` | 낱말은 `rule_shape.DECLARED_KINDS` 셋(`join` · `decide` · `mapper`)이다. 그 밖은 저장과 로드에서 «이름 대어» 거절된다 — 「unknown derive kind 'banana' - one of join · decide · mapper」(종류를 안 적고 칸도 없으면 「derive names no kind - …」, 09-25 `ac2f73381`). 종류를 안 적어도 `derive.join` 처럼 칸 이름으로 정해지면 통과한다. Chain 탭 규칙 목록의 첫 칸 Kind 가 이 낱말이고 목록은 이 순서로 선다(09-25 `a42f8779a`). `join` = `declared:join` 가 원천(`on.table`)의 값을 «into 표에 쓴다»(선언 하나 → 규칙 둘: 선언 이름은 원천이 바뀔 때 · `<이름>:target` 은 into 표에 행이 들어오거나 키가 바뀔 때. `on` 과 `into` 가 같은 표면 하나만 — 09-25 `244d825dc`, 전엔 짝이 `:reference` 로 원천 쪽에 섰다. ⚰️ [09-16 S-278 `c41f9c6d`] 둘 다 «트리거 경로»이고 `follow_up` 칸은 «사라졌다»). 쓰기의 층은 `chain_ingestion`·`updated_by` 가 규칙 이름(`1aa50d3d` — 규칙 이름을 층에 두면 깨우기 필터가 사람 편집으로 읽어 핑퐁) · 키 식(cast · 접기 · coalesce)은 `notation_norm.key_expression_sql` «하나» — 텍스트가 아닌 키는 `::text` 로 접는다(S-245 `ddd5b3ba`) · `decide` = enrich(`enrichment.config.chain_rules_for` — 옛 `enrichment_rules.json` 과 «같은 확장기») | ⚰️ **[판정 600] 이름이 바뀌었습니다** — 옛 `builtin:join_into`·`builtin:auto_confirm`·`builtin:join` 은 오늘 `declared:join`·`declared:decide`·`declared:virtual_join` 입니다. 접두 `declared:` 는 「선언에서 «제품이 만든» 맵퍼」를 뜻하고, 뒤는 선언이 쓰는 낱말입니다. 옛 접두로 로그를 찾으면 «안 나옵니다»(RUN.md 의 환산표).
| `derive.join` / `derive.decide` | `rule_shape` | 종류별 칸. 모르는 칸은 «이름 대고» 규칙은 돈다(`unknown_join_cells`·`unknown_decide_cells`). `join` 의 칸은 `on`(짝 목록 — `left` 는 into 표의 칸, `right` 는 원천의 칸) · `take`(원천에서 가져올 칸)다. ⚰ **`join.right_table` 은 은퇴 — «이름 대어» 거절**(09-25 `244d825dc`, 소유자 「붙일 값을 고쳐야 트리거 시켜서 그걸 붙이지」): 「derive.join.right_table is retired - on names the table whose value changes. Set on.table to "<값>" and delete right_table …」. 원천은 `on.table` 이 말하고, 번역기가 엔진의 `right_table` 을 거기서 채운다. 옛 모양을 새 모양으로 바꾸는 것은 `rule_shape.modernize_join`(변환 문 `admin.convert_chain_rule_grammar` 가 부른다). `decide.auto_confirm` 은 칸이다(판정 400); «적었나»는 칸이 아니라 키 존재에서 유도(판정 401) |
| `on.table` · `into.table` | `rule_shape` | 트리거 표(값이 바뀌는 표) · 쓰는 표 — `mapper`·`decide`·`join` 이 같은 문장이다. `join` 에서 `on.table` 은 «원천»이고 없으면 거절된다(「a join needs on.table - the table whose value changes」). `on.columns` 는 join 에서 적지 않는다 — 원천 쪽 키(`join.on` 의 `right`)에서 유도(판정 398). `into` 는 «택1»이다(`rule_shape.INTO_KINDS` = `table` · `read`). 폼이 «내놓는» 가지는 그중 `rule_shape.RETIRED_INTO_KINDS` 를 뺀 것 — 오늘 `table` 하나(09-25 `65f3590c2` — 전엔 드롭다운이 `read` 를 내놓고, 고르면 로더가 거절했다). ⚰ `read` 는 «은퇴»했고, 문법에서는 «빼지 않고» 이름으로 거절한다(아래 행) |
| `into.read` | `rule_shape.expand_declaration` «하나»(로더와 어드민 저장 라우트가 같이 부른다) — `rule_shape.RETIRED_INTO_KINDS` 에 든 가지를 `READ_TIME_RETIRED` «한 문장»으로 거절한다. 같은 목록을 스켈레톤(`chain_bindings._unified_root`)이 «안 내놓을 것»으로 읽는다 | ⚰ **[2026-09-16 은퇴 1단계 `6580c30f`, 판정 440 ④ — 소유자 「운영은 조인 값을 표에 써서 쓴다」]** 통합 선언의 `derive.kind: join` + `into: {read: true}` 는 «이름 대고 거절»된다: 「읽기 시점 조인(into.read)은 은퇴했습니다 — 조인 값을 «표에 써서» 씁니다. → 다음: 이 선언의 `into` 를 `{"table": "<대상 표>"}` 로 바꾸십시오」. 거절은 «규칙 하나»만 떨어뜨리고 파일은 선다(같은 파일의 쓰는 조인은 규칙 둘로 선다 — `test_a_writing_join_still_stands_two_chain_rules`), 어드민 저장 라우트도 «같은 문장»을 `declaration_refused` 로 낸다. `read` 는 `INTO_KINDS` 에 «남는다» — 빼면 「모르는 칸」이 되어 운영자가 «안 낸 오타»를 찾는다(S-251 이 닫은 구멍을 은퇴가 다시 열지 않는다). `enabled: false` 는 여전히 «조용하다»(판정 399 ③′). ⚰ `virtual_join_rules.json` 쪽도 끝났다 — 09-17 `306419fd5` 가 엔진을 지웠고, 09-22 `fd546ccb1`(판정 652)이 그 문법을 지웠다 — 서버·클라 소스에서 그 파일 이름은 주석에만 남았다(09-25 `git grep`). 조인 쪽 옛 규율은 [config/virtual_join_rules](./virtual_join_rules.md) |
| `key.unique` · `key.columns` | 워커 웜업(`chain/synthesis.ensure_declared_unique_keys` — 부팅 + 리로드마다. 읽기 경로가 «아니다») | `unique: true` 면 «제품이» 원천 표(`on.table`)에 유일 인덱스를 세운다 — 읽기 시점 가상 조인과 같은 `unique_key.ensure_once`, 같은 `uq_vjoin_*` 이름(S-240 `8cab58da`). 중복이 있으면 안 세우고 값·건수를 줄로 낸다(→ `RUN.md` §2 로 가른다). `columns` 는 «선택»이고 «검사»만 — 조인의 원천 쪽 키(`right`)와 같으면 무변, 다르면 두 목록을 이름 대고 안 세운다(`07a568ad` — 다른 컬럼 위의 인덱스는 이 조인이 안 쓴다). `enabled: false` 면 호출 0. 쓰기 시점 «행 단위 그물»은 그대로다 — 답이 둘인 into 행만 `[join_into:<규칙>] … → 다음:` 한 줄로 건너뛰고 나머지는 써진다 |
| `enabled` | 로더(`rule_shape.is_switched_off`) | `false` 면 규칙이 «안 선다» — DB 도 안 만진다(판정 399, ③′). 5-B 의 `enabled` 가 로드 «뒤» 걸러지는 것과 다르다. ⚰️ `ASSY_CHAIN_SYNTHESIZE` 은퇴(S-234 `5c845e67`, 판정 408) — 어느 문법이든 규칙 하나는 «적은 파일»의 `enabled`, 전부는 `ASSY_CHAIN_WORKER=0`. 🆕 이 파일·`enrichment_rules.json`·`virtual_join_rules.json` 의 규칙 이름은 «한 집합»(판정 409): 같은 이름이 두 번이면 로더가 «어느 쪽도 안 세우고» 한 번 거절한다 — `[ChainRules] <이름>: 같은 규칙 이름이 N 번 선언돼 있습니다 (<파일> · <파일>) — 어느 쪽도 돌지 않습니다 → 다음: 두 파일 중 하나에서 이름을 바꾸십시오` |

### 5-bis. 맵퍼 «사설» 키 — 프레임워크가 «안 읽고 안 검증한다» (출하 샘플 기준)

| 맵퍼 | 사설 키 |
|---|---|
| `dt_alignment_metadata_mapper` · `core_alignment_mapper` | `alignment_rule` · `alignment_thresholds` · `reference` · `reference_by_job_pattern` · `geometry_bootstrap` · `primary_selector` · `assume_reference_geometry` · `allow_assumed_geometry` · `accepted_metrics` |
| `dt_map_mapper` · `dt_standard_map_mapper` | `x_col` · `y_col` · `value_col` · `index_col` · `target_field` (+ 가상 조인 규칙의 `right_table`·`join_key`·`expose` 는 `virtual_join_config` 쪽 파일) |
| `lot_slot_wafer_mapper` | `list_delimiter` · `slot_list_column` · `wafer_list_column` · `lot_column` · `time_column` · `event_type_column` |

🔴 **이 층의 규율**: 사설 키의 오타는 «조용»하다(프레임워크가 모른다). 컬럼 이름은 `resolve_column` 을 «지나게» 써서 거절이 이름을 대게 하고, 새 사설 키를 만들기 전에 5-B 의 «같은 역할» 키(`reads` · `*_job_column`)로 표현되는지 먼저 본다.

### 5-ter. «없는» 것 — 적을 자리가 없어서 코드가 정하는 것 (2026-09-08 실측)
```
· 트리거가 «둘 이상»인 규칙          — 없다. 같은 맵퍼를 규칙 둘로 쓴다(core_usage 가 그 예)
· 규칙 «의존 순서»의 명시            — 없다(의도). `reads` 에서 «도출»한다
· 재생(replay) 페이스               — 규칙 키가 아니라 실행 인자(`--pace`, `pacing.json`)
· 「이 규칙을 바꾸면 무엇이 다시 도나」 — 없다. 내일 방향 논의(변경 비용)
```
