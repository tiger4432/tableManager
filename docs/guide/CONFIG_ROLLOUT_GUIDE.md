# 🧾 CONFIG 전개 런북 (Config Rollout Runbook)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-02 | **Owner:** Lead / Backend | **Source-of-truth:** `server/config/*.json.sample` · 각 로더 소스
>
> **이 문서의 자리** ― [CONFIG_GUIDE](./CONFIG_GUIDE.md)가 「**무엇을** 설정해야 하는가」의 지도이고 [config/](./config/README.md)가 「파일 **하나**의 키 사전」이라면, 이 문서는 **「빈 환경에 선언 한 벌을 어떤 순서로 올리고, 각 단계가 실제로 먹었음을 어떻게 증명하는가」** 하나에만 답합니다.
> 리로드 매트릭스·watcher 발화 조건·물리 반영 검증의 **정본은 [CONFIG_GUIDE §4](./CONFIG_GUIDE.md)**이고 여기서는 링크만 합니다. 키 하나하나의 뜻은 [config/](./config/README.md)입니다.
>
> **범위 (2026-08-02).** §3이 다루는 것은 **샘플이 실 파일과 일치하는 여섯**(`table_config` · `map_overlay_config` · `chain_rules` · `enrichment_rules` · `virtual_join_rules` · `ontology_mapping`)입니다. **`auto_update_control`을 포함한 넷은 샘플이 낡아 아직 못 썼고 §6에 그 목록과 이유가 있습니다** ― 특히 `auto_update_control`이 빠져 있는 동안에는 이 문서만으로 「데이터를 계속 만드는 상태」까지 재현할 수 없습니다.
>
> **왜 목록이 아니라 순서인가.** 파일 목록은 이미 [CONFIG_GUIDE §1](./CONFIG_GUIDE.md)에 있습니다. 운영에서 실제로 깨지는 것은 목록이 아니라 **순서**와 **조용히 안 먹는 방식**입니다 ― 아래 §4의 셋은 전부 2026-08-02에 실제로 밟은 것입니다.

---

## 0. 착수 전 (한 번만)

| # | 할 일 | 확인 |
|---|---|---|
| 1 | `server/config/`의 `*.json.sample`을 **확장자 없이 복사**해 시작. 실 파일은 전부 gitignored이고 git에 올라가는 것은 `.sample`뿐입니다 → [CONFIG_GUIDE §1](./CONFIG_GUIDE.md) | `ls server/config/*.json` |
| 2 | `ASSY_ADMIN_TOKEN`을 **영구 설정**(셸 변수는 셸이 닫히면 사라집니다) → [DEPLOY_SETUP §1-4](./DEPLOY_SETUP.md) | 기동 배너의 `token fingerprint` |
| 3 | 손대기 전 스냅샷 | `conda run -n assy_manager python server/scripts/backup_config.py snapshot` |
| 4 | 아래 명령의 기준 주소를 정합니다. 런처 기본 포트는 **8080**(`ASSY_API_PORT`) | `API=http://127.0.0.1:8080` |

```bash
# 이 문서의 모든 curl 예시가 쓰는 두 변수
API=http://127.0.0.1:8080
AUTH="X-Admin-Token: $ASSY_ADMIN_TOKEN"
```

> ⚠️ **`server/config/*.json`은 어드민 UI에서 편집할 수 없습니다.** Monaco 에디터는 `.py`만 다룹니다(예외: 맵 프리셋·수집기 토글은 전용 API). config는 디스크에서 직접 편집합니다.

---

## 1. 순서 ― 이것이 이 문서의 내용이다

```
① table_config.json        테이블·컬럼 선언            (모든 것의 뿌리)
       │
       ├─② map_overlay_config.json   맵 좌표 컬럼 바인딩
       ├─③ chain_rules.json          쓰기 → 쓰기 투영
       ├─④ enrichment_rules.json     사람이 판정할 워크리스트
       ├─⑤ virtual_join_rules.json   저장하지 않는 조인   (⑤는 오른쪽 테이블의 UNIQUE 인덱스가 먼저)
       └─⑥ ontology_mapping.json     그래프 노드/엣지
```

**②~⑥은 서로 독립이지만 전부 ①을 전제합니다.** ①에 없는 테이블·컬럼을 가리키면 그 선언은 **로드 시점에 거부**되고, 거부는 대개 **그 파일이 통째로 죽는 것이 아니라 그 항목 하나만 빠지는** 형태라 표면에서는 「아직 아무 일도 안 일어난 것」과 구별되지 않습니다.

🔴 **①과 ②~⑥ 사이에 반영을 끼워 넣으십시오.** 한 번에 여섯 파일을 저장하고 리로드를 한 번 누르면, 워커가 ④를 읽는 시점에 자기 `TABLE_CONFIG`가 아직 옛것일 수 있습니다 ― §4.1이 그 이야기입니다.

의존 관계의 전체 그림은 [CONFIG_GUIDE §2](./CONFIG_GUIDE.md), 각 시나리오의 체크리스트는 [CONFIG_GUIDE §3](./CONFIG_GUIDE.md)입니다.

---

## 2. 주석은 파일마다 다르다 (먼저 알아야 손이 안 묶인다)

선언 옆에 「왜 이렇게 했는지」를 남기고 싶은 것이 정상인데, **채널이 파일마다 다르고 한 파일에는 아예 없습니다.**

| 파일 | 최상위 주석 키 | 선언 **안**의 주석 키 |
|---|---|---|
| `table_config.json` | ❌ 두지 마십시오 (최상위 항목은 테이블 선언으로 읽힙니다) | ✅ `__comment` (읽히지 않는 키는 무시됩니다) |
| `chain_rules.json` | ✅ `__comment` (로더는 `rules`만 읽습니다) | ✅ `__comment` |
| `enrichment_rules.json` | 🔴 **없습니다.** 최상위 `__comment`는 `rule must be an object`로 **거부**됩니다 | ✅ `__comment` |
| `virtual_join_rules.json` | ✅ **`_`로 시작하는 이름**은 선언이 아니라 주석으로 건너뜁니다 | ― |
| `ontology_mapping.json` | ✅ **`__`(밑줄 둘)로 시작하는 이름**만 건너뜁니다 | 🔴 **불가.** 매핑 안의 허용 키는 `description`/`event_time_column`/`node`/`edges` 넷뿐이고 그 밖의 키는 **거부**입니다 |
| `map_overlay_config.json` | ✅ 읽지 않는 키는 무시됩니다 | ✅ `table_bindings` 조회는 테이블 이름으로만 하므로 `__derived_note` 같은 키가 섞여도 무해합니다 |

> `ontology_mapping.json`은 `description`이 **필수**입니다(노드·엣지 양쪽). 그것이 사실상 그 파일의 주석 채널입니다 ― 장식이 아니라 검증되는 필드라 비면 그 매핑이 거부됩니다.

---

## 3. 단계별 ― 최소 선언 · 먹었는지 확인 · 안 먹었을 때의 모양

각 절의 JSON은 **`.sample`에 실재하는 키만** 씁니다. 키의 의미·전체 사전은 각 절 끝의 링크입니다.

### ① `table_config.json` ― 테이블과 컬럼

**무엇을 선언하나:** 동적 테이블 하나의 이름·컬럼·타입·비즈니스 키. 물리 `CREATE TABLE`이 여기서 나옵니다.

**최소 선언 (단일 키)**

```json
"dt_job_attribution": {
  "business_key": "dt_job",
  "column_types": {
    "dt_job": "string",
    "dt_lot_confirmed": "string",
    "dt_slot_confirmed": "string",
    "cell_count": "number"
  },
  "display_columns": ["dt_job", "dt_lot_confirmed", "dt_slot_confirmed", "cell_count"]
}
```

**복합 키를 쓸 때는 두 줄이 더 붙습니다** ― 키 컬럼을 조합해 `business_key`를 만듭니다.

```json
"core_wafer_map": {
  "business_key": "core_cell_key",
  "composite_key_source": ["core_lot", "core_slot", "core_x", "core_y"],
  "composite_key_separator": "_",
  "column_types": { "core_cell_key": "string", "core_lot": "string", "core_slot": "string",
                    "core_x": "number", "core_y": "number", "c_bn": "string" },
  "display_columns": ["core_cell_key", "core_lot", "core_slot", "core_x", "core_y", "c_bn"],
  "map_key_columns": ["core_lot", "core_slot"]
}
```

- `map_key_columns`는 **맵 한 장의 범위**를 정합니다. 행 하나의 키(`composite_key_source`)와 다른 것이며, 둘을 혼동하면 「키 하나에 수백 행」처럼 보입니다.
- 🔴 **자릿수가 의미 있는 값은 `string`으로 선언하십시오.** `number`로 선언한 `"07"`은 `7`로 저장되고 앞의 0이 사라집니다.

**먹었는지 확인 (순서대로)**

```sql
-- 유일하게 신뢰할 수 있는 물리 증거
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'dt_job_attribution' ORDER BY ordinal_position;
```

```bash
curl -s "$API/tables/dt_job_attribution/data?limit=1"   # 200 = ORM이 실물 테이블을 잡았다
```

**안 먹었을 때의 모양**

| 증상 | 원인 |
|---|---|
| 서버가 아예 안 뜨고 로그에 `table_config.json is not valid JSON` | JSON 문법 오류. 부팅 경로는 **일부러 죽습니다**(테이블 0개로 조용히 뜨는 것보다 낫습니다) |
| 로그에 `Config reload ABORTED: ... produced an empty table config` | 실행 중 리로드였고 **아무것도 바뀌지 않았습니다.** 기존 상태가 유지됩니다 |
| `/tables/<t>/schema`는 200인데 `information_schema`에 컬럼이 없음 | **컬럼 추가는 watcher 경로에서만 ALTER됩니다.** `/admin/reload-configs`는 ALTER를 하지 않습니다 → §4.2 |
| 컬럼 삭제·타입 변경이 반영되지 않음 | 어떤 리로드 경로도 하지 않습니다. **재기동**(+ 필요 시 수동 마이그레이션) |

→ 키 사전: [config/table_config](./config/table_config.md) · 반영 규율: [CONFIG_GUIDE §4.1 / §4.3 / §4.4](./CONFIG_GUIDE.md)

---

### ② `map_overlay_config.json` ― 맵 좌표 컬럼

**무엇을 선언하나:** 맵 테이블의 x/y/값 컬럼이 `x`/`y`/`val` 관례와 **다를 때만** 그 이름을 알려 줍니다.

```json
{
  "table_bindings": {
    "dt_log": {
      "columns": { "x": "dt_x", "y": "dt_y", "val": "c_bn", "key_columns": ["dt_job"] }
    }
  }
}
```

- 🔴 **관례와 같은 테이블은 선언하지 마십시오.** 바인딩은 `table_config`에서 자동 유도되고, 같은 값을 중복 선언하면 **유도 경로가 아직 살아 있는지를 가려 버립니다.**
- 같은 파일이 담는 나머지(전부 `.sample`에 있습니다): `default_legend`(레지스트리 행이 없는 맵의 시작 legend) · `value_column_candidates`(값 컬럼 탐지 순서 ― 선언하면 **부분 적용 없이 통째로 대체**) · `paint_lock`(페인팅 잠금의 정본).
- ⚠️ `preset_routing`(로드 시 프리셋 라우팅)은 **`.sample`에 없습니다.** 형태는 [config/map_overlay_config §2-bis](./config/map_overlay_config.md)에 있고, 여기서는 샘플에 보이지 않는 모양을 옮겨 적지 않습니다.

**먹었는지 확인**

```bash
curl -s "$API/api/maps/paint-rules"
```

해석된 바인딩이 `source` 필드를 달고 돌아옵니다 ― `declared`(내가 선언했다) / `derived`(table_config에서 유도됐다) / **`fallback_guess`(추측이다 ― 신뢰하지 말 것)**. 리로드는 필요 없습니다. 이 파일은 **요청마다 디스크를 다시 읽습니다.**

**안 먹었을 때:** 오버레이가 「이 테이블은 맵으로 해석할 수 없다」로 명시 실패합니다. 조용히 0건을 정상처럼 내보내지 않습니다.

→ [config/map_overlay_config](./config/map_overlay_config.md) · [CONFIG_GUIDE §5.8-bis](./CONFIG_GUIDE.md)

---

### ③ `chain_rules.json` ― 쓰기가 쓰기를 부른다

**무엇을 선언하나:** `trigger_table`에 커밋된 쓰기를 맵퍼로 변환해 `target_table`에 투영합니다.

```json
{
  "rules": [
    {
      "name": "dt_log_to_dt_map",
      "trigger_table": "dt_log",
      "target_table": "dt_map",
      "mapper_module": "mappers.dt_map_mapper",
      "mapper_function": "build_dt_map_batch_df",
      "is_batch": true,
      "enabled": false
    }
  ]
}
```

- 맵퍼 파일은 `server/mappers/<module>.py`이고 **`server/mappers/*`도 gitignored**입니다(`.sample`만 올라갑니다).
- **`enabled`는 생략하면 `true`입니다.** 끄려면 명시적으로 `false`.
- 🔴 **체인은 맵 셀을 올릴(upsert) 수는 있어도 지우지(purge) 못합니다.** `replace_map`은 배치 단위 필드인데 체인 워커가 배치를 직접 조립하면서 그것을 설정하지 않기 때문입니다. 한 작업의 셀 집합이 **줄어들 수 있다면** 체인이 아니라 맵 경로(`PUT /tables/<t>/data/updates` + `replace_map: true`)로 몰아야 합니다. `dt_log_to_dt_map`이 `enabled: false`로 나가는 이유가 이것입니다.
- 🔴 **맵퍼에서 `business_key_val`을 직접 만들지 마십시오.** 복합 키 테이블에서는 `crud.apply_batch_updates`가 `composite_key_source` 컬럼들로 키를 **대신 조합**합니다 ― 조건은 항목이 `business_key_val`을 **생략**하고 소스 컬럼을 **전부** 실어 보내는 것입니다. 직접 넣으면 한 작업의 모든 셀이 행 하나로 붕괴합니다(`dt_map_mapper.py.sample`이 고치기 전에 그랬습니다).

**먹었는지 확인**

```bash
curl -s -H "$AUTH" "$API/admin/chain/rules"
curl -s -H "$AUTH" "$API/admin/mappers/list"
```

반영은 `POST /admin/reload-configs`입니다(워커가 `SYSTEM_RELOAD`를 받아 룰을 다시 읽습니다).

→ [config/chain_rules](./config/chain_rules.md) · [chain_ingestion_guide](./chain_ingestion_guide.md)

---

### ④ `enrichment_rules.json` ― 사람이 판정할 워크리스트

**무엇을 선언하나:** 「`source_table`을 `decision_key`로 묶어 `derived_table`에 한 행씩 만들고, 그 행의 `target_fields`가 빌 동안 큐에 둔다」.

**최소 선언**

```json
{
  "dt_job_lot_slot_attribution": {
    "source_table": "dt_log",
    "derived_table": "dt_job_attribution",
    "decision_key": ["dt_job"],
    "target_fields": ["dt_lot_confirmed", "dt_slot_confirmed"],
    "list_columns": ["cell_count"],
    "aggregations": { "cell_count": "count" },
    "enabled": true,
    "auto_confirm": true,
    "reference_views": [
      {
        "label": "설비 track-in이 말하는 DT 랏",
        "query": "SELECT DISTINCT le.lot AS dt_lot FROM lot_event le WHERE le.event_type = 'track_in' AND le.equipment = :dt_job",
        "limit": 50,
        "candidate_for": { "dt_lot_confirmed": "dt_lot" }
      }
    ]
  }
}
```

**여기서 조용히 죽는 자리 넷** ― 넷 다 에러가 아니라 **아무 일도 안 일어남**으로 나타납니다.

1. `source_table`·`derived_table`이 `table_config`에 없으면 **그 규칙 하나가 통째로 빠집니다.** → §4.1
2. **바인드 파라미터는 `decision_key` 컬럼만** 허용됩니다. 다른 것을 바인딩한 뷰는 그 뷰만 떨어져 나갑니다.
3. **`candidate_for`가 없는 뷰는 표시 전용입니다.** 컬럼명 유추는 하지 않습니다. 어떤 타깃도 선언 뷰를 갖지 못하면 자동 확정 프로브가 **SQL을 한 줄도 돌리지 않고** 종료하며 **로그도 남지 않습니다** ― 「기능이 꺼진 것」과 구별되지 않는 상태이고, 이 선언이 존재하는 이유가 바로 그 침묵을 없애는 것입니다.
4. **`decision_key`의 일부만 바인딩하는 뷰는 문법상 합법이지만 `scope_unresolved`로 표시됩니다** ― 확정 하나가 더 넓은 범위 전체에 찍히기 때문입니다.

> **`auto_confirm`은 기본 OFF입니다.** 켜기 전에 반드시 측정하십시오 ― 드라이런은 노브를 무시하므로 **꺼 둔 채로도 전부 측정됩니다.**
> ```bash
> curl -s -H "$AUTH" "$API/admin/enrichment/auto-confirm/dry-run?rule=<규칙>&limit=500"
> ```
> `refused_reason`이 `not_declared`면 위 3번입니다. 정상이면 `null`이고 `refused`에 **이름이 붙은 거절**(`no_candidate` 등)이 들어옵니다.

**먹었는지 확인**

```bash
curl -s -H "$AUTH" "$API/admin/config/resolve?domain=enrichment"   # effective / ineffective / rejected
curl -s "$API/enrichment/rules"                                    # 공개 메타
grep "Synthesized\|rule skipped" server/chain_worker.log | tail    # 워커가 실제로 받았는가
```

🔴 **마지막 줄이 이 단계의 핵심입니다.** 웹 서버가 규칙을 받아들이는 것과 **체인 워커가** 받아들이는 것은 별개입니다 → §4.1.

→ [config/enrichment_rules](./config/enrichment_rules.md)(§7이 자동 확정 정본) · [ENRICHMENT_QUEUE_SPEC](../spec/ENRICHMENT_QUEUE_SPEC.md)

---

### ⑤ `virtual_join_rules.json` ― 저장하지 않는 조인

**무엇을 선언하나:** 오른쪽 테이블의 컬럼을 **복사하지 않고** 왼쪽 테이블 위에 조회 시점에 얹습니다.

```json
{
  "dt_log_confirmed_attribution": {
    "left_table": "dt_log",
    "right_table": "dt_job_attribution",
    "join_key": [{ "left": "dt_job", "right": "dt_job" }],
    "expose": ["dt_lot_confirmed", "dt_slot_confirmed"],
    "unresolved_label": "미상",
    "join_cardinality": "one",
    "enabled": true
  }
}
```

🔴 **선언보다 먼저 인덱스입니다.** 승인 조건은 **조인 키를 덮는 유효한 UNIQUE 인덱스** 하나뿐이고, 없으면 선언은 `no_unique_index`로 **거부**됩니다. 거부는 만들어야 할 DDL을 그대로 돌려줍니다:

```sql
CREATE UNIQUE INDEX CONCURRENTLY uq_vjoin_dt_job_attribution_dt_job
  ON "dt_job_attribution" ("dt_job");
```

- 인덱스는 config가 아니라 **DB에 살기 때문에** 이후의 어떤 쓰기도 그 성질을 깰 수 없습니다. 그래서 등급도 예산도 없습니다 ― 있으면 통과, 없으면 거부.
- **인정되지 않는 인덱스 셋**: 무효(`indisvalid=false` ― 취소된 `CREATE INDEX CONCURRENTLY`의 잔해) · 부분(`indpred`) · 표현식(`indexprs`). `CONCURRENTLY`를 중간에 끊었다면 **지우고 다시 만들어야** 판정이 인정합니다.
- **인덱스 생성 자체가 실패한다면 그것이 답입니다.** PostgreSQL이 `Key (lot, slot)=(...) is duplicated`로 중복 키 값까지 지목합니다 ― 그 중복이 곧 「이 조인은 그 배수만큼 불어난다」의 증거입니다.
- `join_cardinality`는 **`"one"`만** 지원됩니다. 다른 값은 `fanout_declared`로 이름 붙은 거부입니다(집계 형태는 아직 구현이 없습니다).
- `expose` 이름이 왼쪽에 이미 있어도 **거부가 아닙니다.** 규칙은 **부재일 때만 채운다**입니다: 왼쪽 값 있음 → 그대로, 비었음 → 조인 값, 둘 다 없음 → `unresolved_label`.
- 🔴 **그래서 이름을 겹치게 만들지 마십시오.** 겹치면 왼쪽의 값이 **틀렸을 때조차** 이깁니다. 확정값을 기록값 **옆에** 세우는 것이 목적이라면 `_confirmed` 같은 접미로 갈라야 어긋남이 화면에 보입니다.
- 이름이 `_`로 시작하는 항목은 선언이 아니라 주석입니다 ― `.sample`의 `_example_rejected_no_unique_index`가 그 형태이며, 밑줄을 떼면 실제로 거부 목록에 뜹니다.

**먹었는지 확인**

```bash
curl -s -H "$AUTH" "$API/admin/config/virtual-join/verify"
```

선언마다 `accepted` · `unique_index`(잡힌 인덱스 이름) · `required_index_ddl`(거부일 때 만들어야 할 DDL) · `detail`(사람이 읽을 한국어 문장)이 돌아옵니다.

> ⚠️ **`/admin/config/resolve`만으로는 이 절반을 볼 수 없습니다.** 그 라우트는 「DB 질의 0건」이 계약이라 인덱스의 존재를 모릅니다. 라우트가 둘인 것이 그 때문입니다.

**반영:** 승인 선언은 짧은 TTL 캐시를 탑니다. 웹 서버는 `POST /admin/reload-configs`가 즉시 무효화하고, 그 훅이 없는 워커 프로세스는 TTL이 지나야 바뀝니다.

**남아 있는 한계 3건**(CSV 추출에 안 실림 · `미상` 행을 검색할 방법 없음 · 사람이 일부러 비운 셀에도 조인 값이 뜸)은 [config/virtual_join_rules §9](./config/virtual_join_rules.md)가 단독으로 관리합니다 ― 여기에 사본을 만들지 않습니다.

→ [config/virtual_join_rules](./config/virtual_join_rules.md)

---

### ⑥ `ontology_mapping.json` ― 그래프 노드와 엣지

**무엇을 선언하나:** 테이블 한 행이 어떤 노드가 되고 어떤 엣지를 뻗는지.

```json
{
  "dt_job_attribution": {
    "description": "추론 ①의 판정 결과. 확정 전에는 타깃이 비어 있다",
    "node": {
      "label": "DtJob",
      "identity": ["dt_job"],
      "node_class": "static",
      "props": ["cell_count"]
    },
    "edges": [
      {
        "type": "RESOLVED_TO_LOT",
        "target_label": "Lot",
        "target_identity_from": ["dt_lot_confirmed"],
        "description": "확정된 DT 랏. 미확정이면 엣지 없음"
      }
    ]
  }
}
```

- **`description`은 노드에도 엣지에도 필수**입니다(LLM 그라운딩). 없으면 그 매핑이 거부됩니다.
- 매핑 안에 쓸 수 있는 키는 **`description` · `event_time_column` · `node` · `edges` 넷뿐**이고, 그 밖의 키는 오타를 조용히 넘기지 않기 위해 **거부**됩니다.
- 🔴 **빈 값은 엣지를 만들지 않습니다.** `target_identity_from`의 컬럼이 하나라도 비면 그 엣지는 생기지 않습니다. 이것이 설계입니다 ― 「아직 모른다」가 「없다」로 둔갑하지 않고, 사람의 확정은 **값이 조용히 바뀌는 것이 아니라 엣지가 나타나는 것**으로 보입니다.
- 🔴 **없는 쪽을 `-` 같은 리터럴로 채우지 마십시오.** 그것은 완벽하게 유효한 식별자라 노드 하나가 만들어지고, 그 노드에 **모든** 관계가 매달려 무관한 두 개체가 두 홉 거리로 보이게 됩니다.

**먹었는지 확인**

```bash
curl -s "$API/graph/mapping-summary"
```

성공 목록과 **같은 응답**에 `rejected`가 실려 옵니다 ― 성공 개수만 보면 「안 늘었다」와 「죽었다」가 구별되지 않기 때문입니다. 컬럼 하나를 개명한 순간 그 테이블의 온톨로지가 통째로 사라질 수 있고, 그때 표면에 남는 것이 이 배열입니다.

**반영:** `POST /admin/reload-configs`.

→ [config/ontology_mapping](./config/ontology_mapping.md) · [ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md)

---

## 4. 조용히 실패하는 세 가지 (전부 실측)

### 4.1 🔴 규칙은 **디스크에서 유효하면서 워커 안에서는 죽어 있을 수** 있다

2026-08-02에 실제로 일어난 일입니다. 체인 워커 로그:

```
23:48  [Enrichment:dt_job_lot_slot_attribution] rule skipped:
       source_table 'dt_log' is not registered in table_config.json
00:23  [Chain.enrichment_dedup] [Enrichment:core_wafer_attribution]
       1000 row(s) skipped: blank decision_key value(s)      <- 옛 규칙이 그대로 돌고 있었다
00:26  Process stopped. ... restarted ...
00:26  [Enrichment] Synthesized 2 dedup chain rule(s) from enrichment_rules.json
```

**무슨 일이 있었나.** 워커는 새 `enrichment_rules.json`을 자기 `TABLE_CONFIG`가 아직 옛것인 상태에서 읽었고, `dt_log`가 등록돼 있지 않다며 **두 규칙을 모두 버렸습니다.** 그리고 **스스로 다시 시도하지 않았습니다** ― 인제션 내내 옛 규칙이 돌면서 모든 행을 건너뛰었습니다.

**그래서 규율은 셋입니다.**

1. **테이블을 먼저 선언하고 반영시킨 뒤에 규칙을 선언하십시오.** 한 번에 저장하고 리로드를 한 번 누르는 것이 이 사고의 모양입니다.
2. **한 번의 리로드로 됐다고 가정하지 마십시오.** 규칙 재합성은 리로드마다 다시 일어나므로 **두 번째 `/admin/reload-configs`도 회복 경로**입니다 ― 다만 재기동이 확실합니다(부팅 경로가 `TABLE_CONFIG`부터 다시 읽습니다). **어느 쪽이든 로그를 읽고 확인하기 전까지는 반영된 것이 아닙니다.**
3. **확인은 응답이 아니라 로그로 하십시오.**
   ```bash
   grep "Synthesized\|rule skipped" server/chain_worker.log | tail
   ```
   `Synthesized N dedup chain rule(s)`의 N이 여러분이 선언한 수와 같아야 합니다. `rule skipped:`가 보이면 그 규칙은 **없는 것과 같습니다.**

> 웹 서버가 `/admin/config/resolve`에서 `effective`라고 답하는 것은 **웹 서버 프로세스의 판정**입니다. 워커는 별개의 프로세스이고 별개의 캐시를 갖습니다.

### 4.2 🔴 스키마 라우트의 **200은 아무것도 증명하지 않는다**

`GET /tables/<t>/schema`는 **메모리의 config 싱글턴을 읽습니다.** config에만 있고 데이터베이스에는 없는 컬럼도 그대로 200으로 보입니다.

**대신 볼 것 둘:**

```bash
curl -s "$API/tables/<t>/data?limit=1"     # 실제 ORM 모델과 실물 테이블을 지난다
```
```sql
SELECT column_name FROM information_schema.columns WHERE table_name = '<t>';
```

선언을 **지웠는지** 확인할 때도 같습니다 ― 지운 테이블은 `/tables/<t>/data`에서 **404**가 되어야 하고, 남아 있으면 그 프로세스는 아직 옛 config를 들고 있는 것입니다.

**두 라우트가 덮지 못하는 자리:** 기존 테이블에 **컬럼을 추가**하는 ALTER는 **config watcher 경로에서만** 일어납니다. `/admin/reload-configs`는 신규 테이블 CREATE는 해도 **ALTER는 하지 않습니다**(락 컨보이 방지 ― 의도된 설계). watcher가 발화하지 않았다면 파일을 **제자리로 다시 저장**하거나 웹 서버를 재기동하십시오.

> ⚠️ **watcher가 감시하는 파일은 `table_config.json` 하나뿐입니다.** 나머지 config 파일은 저장해도 아무것도 트리거하지 않습니다 ― 그 파일들의 반영 경로는 `/admin/reload-configs`이거나 「요청마다 재읽기」입니다([CONFIG_GUIDE §4.1](./CONFIG_GUIDE.md)).
>
> ℹ️ 저장 방식(제자리 쓰기 / temp+rename)은 **2026-07-29부터 문제가 되지 않습니다** ― watcher가 `on_modified`·`on_moved`·`on_created` 셋을 모두 처리하고 트레일링 엣지로 디바운스합니다([CONFIG_GUIDE §4.4](./CONFIG_GUIDE.md)). 그래도 **발화했다는 것과 DDL이 성공했다는 것은 다릅니다** ― 증거는 여전히 `information_schema`입니다.

### 4.3 🔴 선언을 **지우면**, 그것을 가리키던 다른 선언이 조용히 반쯤 돈다

테이블 선언을 제거할 때 **다섯 곳을 먼저 훑으십시오.**

| 훑을 곳 | 남아 있으면 |
|---|---|
| `map_overlay_config.json` | 해당 맵이 「해석할 수 없음」으로 명시 실패 |
| `ontology_mapping.json` | 매핑이 거부됩니다 ― `/graph/mapping-summary`의 `rejected`에 뜹니다 |
| `virtual_join_rules.json` | 선언이 거부됩니다 ― `/admin/config/virtual-join/verify`에 뜹니다 |
| `enrichment_rules.json` · `chain_rules.json` | 규칙이 빠집니다(§4.1의 모양) |
| 🔴 `bonding_plan_config.json` · `transfer_plan_config.json` | **아무 데도 안 뜹니다.** 이 둘의 테이블 참조를 **검증하는 코드가 없습니다** ― `load_config`가 실패 시 빈 dict를 돌려주고 그것이 「부분 가동, 에러 아님」으로 문서화돼 있습니다. 매달린 참조는 **에러가 아니라 반쯤 작동하는 화면**을 만듭니다 |

**그래서 순서는 「지우기 전에 감사」입니다.** 앞의 넷은 라우트가 말해 주지만, **마지막 줄은 사람이 열어 보는 것 말고 방법이 없습니다.**

```bash
grep -n "<지울테이블>" server/config/*.json
```

> 삭제해도 **물리 테이블과 행은 남습니다.** 선언 제거는 config 작업이고 `DROP`은 별개의 결정입니다. 잔여 테이블 검출은 `server/scripts/list_undeclared_tables.py`(읽기 전용)입니다.

---

## 5. 안 되면 이 셋부터

1. **워커 로그를 보십시오 ― 응답이 아니라.**
   ```bash
   grep "rule skipped\|Synthesized\|ABORTED\|rejected" server/chain_worker.log server/server.log | tail -30
   ```
   `/admin/reload-configs`는 `{"status":"success"}` 하나만 돌려줍니다. 그것은 **캐시를 갱신했다**는 뜻이지 여러분의 선언이 효과를 냈다는 뜻이 **아닙니다.**

2. **선언 순서를 되짚으십시오.** `table_config`가 먼저 반영됐습니까? `information_schema`로 확인한 뒤에 규칙 파일을 저장했습니까? 아니라면 리로드를 한 번 더 누르고 §4.1의 `Synthesized` 줄을 다시 읽으십시오.

3. **서버에게 물어보십시오.** 세 라우트가 각자 다른 절반에 답합니다.
   ```bash
   curl -s -H "$AUTH" "$API/admin/config/resolve"                  # 선언의 해석 (DB 질의 0건)
   curl -s -H "$AUTH" "$API/admin/config/virtual-join/verify"      # 인덱스 승인 여부 + 필요한 DDL
   curl -s          "$API/graph/mapping-summary"                   # 온톨로지 성공 + 거부
   ```
   ⚠️ **읽기에 실패했다면 그것은 「설정이 멀쩡하다」가 아닙니다.** 특히 「관리자 게이트가 아닌 응답」이 보이면 토큰 문제가 아니라 **그 포트 앞에 무엇이 답하고 있는가**의 문제입니다(사내 프록시 전례 → [DEPLOY_SETUP §1-5](./DEPLOY_SETUP.md)).

---

## 6. ⏳ 아직 못 쓴 네 절 (샘플이 실 파일보다 낡아 있다)

> 🔴 **이 문서가 인용하는 모양의 출처는 `server/config/*.json.sample` 하나입니다.** 실 config는 gitignored이므로, 샘플에 없는 모양을 적으면 **독자가 대조할 수 없는 가이드**가 됩니다. 2026-08-02 실측 결과 아래 넷은 **샘플이 실 파일보다 낡아** 그 상태로는 옮겨 적을 수 없습니다.
>
> ✅ **다만 선언 자체는 이제 저장소 안에서 읽을 수 있습니다** ― [`guide/config_reference/`](./config_reference/README.md)가 이 환경의 실 config를 **있는 그대로 복사**해 두었습니다(자격증명·호스트·절대경로는 복사 전에 걸러졌습니다). **넷 중 무엇이 어떻게 선언돼 있는지 지금 당장 보고 싶다면 그쪽입니다.** 이 §3 형식의 절(최소 선언 · 반영 확인 · 실패 모양)이 아직 없을 뿐입니다.
>
> 🔴 **그리고 그 폴더는 배포물이 아닙니다** ― 현장마다 테이블·컬럼·설비 이름이 다릅니다. **복사해 덮으면 그쪽 선언이 사라집니다.**

| 파일 | 이 문서에 왜 필요한가 | 상태 |
|---|---|---|
| 🔴 **`auto_update_control.json`** | **넷 중 이것이 핵심입니다.** 수집기(생성기)의 활성/비활성 목록이 여기 있습니다 ― 「데이터를 계속 만들려면 무엇을 켜고, 옛 데모 생성기 중 무엇을 꺼야 하는가」에 답하는 유일한 파일이고, **이것 없이는 운영이 같은 상태를 재현할 수 없습니다.** 실 파일에는 이번 라운드에 등록된 생성기와 **꺼 놓은 옛 데모 생성기들**이 들어 있는데 샘플이 그 이전입니다 | ⏳ 샘플 갱신 대기 |
| `maps.json` | 웨이퍼 물리 규격·오프셋 프리셋 | ⏳ 샘플 갱신 대기 |
| `bonding_plan_config.json` | M1 본딩 실험계획의 역할→테이블 바인딩. ⚠️ **§4.3의 마지막 줄에 해당하는 파일**입니다(참조를 검증하는 코드가 없습니다) | ⏳ 샘플 갱신 대기 |
| `transfer_plan_config.json` | M2 전사 계획의 stage 선언. ⚠️ 위와 같습니다 | ⏳ 샘플 갱신 대기 |

**그동안 볼 곳**(정본이며, 낡은 것은 샘플이지 이 문서들이 아닙니다): [config/auto_update_control](./config/auto_update_control.md) · [config/maps](./config/maps.md) · [config/bonding_plan_config](./config/bonding_plan_config.md) · [config/transfer_plan_config](./config/transfer_plan_config.md) · 수집기 자체의 동작은 [AUTO_UPDATE_GUIDE](./AUTO_UPDATE_GUIDE.md).

> ⚠️ **이 환경에는 `.sample`만 있고 실 파일이 없는 config가 넷 있습니다** ― `database.json` · `effort_metric.json` · `ingestion_settings.json` · `suggest_config.json`. **이번 설정 한 벌의 일부가 아니므로 §3에 절이 없습니다.** 각자 기본값으로 동작하고 있으며, 실제로 세팅해야 할 때의 절차는 [config/](./config/README.md)의 해당 파일 가이드입니다.

---

## 7. 이 문서가 다루지 않는 것 (일부러)

| 질문 | 자리 |
|---|---|
| 어떤 config 파일이 있고 각각 누가 소비하나 | [CONFIG_GUIDE §1](./CONFIG_GUIDE.md) |
| 리로드 매트릭스 · watcher 발화 조건 · 물리 검증 | [CONFIG_GUIDE §4](./CONFIG_GUIDE.md) |
| 파일 하나의 키 전수 사전 | [config/](./config/README.md) |
| 이미 쌓인 데이터에 규칙을 소급 적용 | [BACKFILL_GUIDE](./BACKFILL_GUIDE.md) |
| 되돌리기(config → 코드 → 재기동) | [ROLLBACK_PROCEDURE](./ROLLBACK_PROCEDURE.md) |
| 새 환경 배포 전반 | [DEPLOY_SETUP](./DEPLOY_SETUP.md) |
| **이 환경이 실제로 무엇을 선언했나**(실 config 사본) | [guide/config_reference/](./config_reference/README.md) |
| 이 선언 한 벌이 **무엇을 위한 것인가** | [spec/TRACE_FIXTURE_SPEC](../spec/TRACE_FIXTURE_SPEC.md) |
