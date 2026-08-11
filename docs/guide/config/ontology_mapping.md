# `ontology_mapping.json` 세팅 — 그래프 노드/엣지 매핑 (v2)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-11 (**`node.identity`가 맵 정체성을 상속할 수 있다** — `68db020` 신설 `@map_key_columns` 토큰 + 「생략하면 전체 상속」, §5 참조) | **Owner:** Sync / 총괄
> 상위: [폴더 인덱스](./README.md) · 트랙 스펙은 [ONTOLOGY_GRAPH_SPEC §3](../../spec/ONTOLOGY_GRAPH_SPEC.md) · 온보딩 절차는 [CONFIG_GUIDE §3-S4](../CONFIG_GUIDE.md) · 상속 메커니즘은 [data_model §5.0-bis](../../architecture/data_model.md) · [PRIMITIVES §3](../../architecture/PRIMITIVES.md#-키를-지우면-상속한다--관례-폴백이-아니라-파생-리졸버로-2026-08-11-등록--68db020)가 정본

<!-- Loader evidence (2026-07-28):
  validate: server/ontology_config.py:99 _validate_table_mapping (description required :104-106,
    node.label/identity :108-116, edges type/target_label/target_identity_from/description :125-139,
    props + spatial {coord_system, axis} :63-96, column existence vs table_config :156-169)
  load: ontology_config.py:280 load_ontology_mappings (+ enrichment RESOLVED_AS promotion :218)
  web cache: server/database/crud.py:1966 get_ontology_mapping (_ontology_cache; invalidated by /admin/reload-configs)
  worker: server/graph_sync_worker.py:489 (reload on SYSTEM_RELOAD)
  reload route: server/main.py:2947 POST /admin/reload-configs (require_admin_token)
-->

## 1. 언제 이 파일을 만지는가

- **테이블을 그래프에 올릴 때** — 여기 선언한 테이블만 graph_sync_worker가 materialize하고 그래프 뷰어·trace에서 탐색됩니다
- 노드/엣지 구조·`description`(LLM 그라운딩 계약)을 수정할 때
- enrichment로 해석 관계를 만들 때는 **여기가 아닙니다** — `RESOLVED_AS` 엣지는 `enrichment_rules.json`에서 자동 승격되므로 중복 선언 금지

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **전제 확인**: 참조할 테이블·컬럼이 전부 `table_config.json`에 실존해야 합니다 — 미등록 참조가 하나라도 있으면 **그 테이블 매핑이 통째로 스킵**됩니다.
3. 파일이 없으면 `ontology_mapping.json.sample` 복사. 루트는 반드시 `{테이블명: 매핑}` 객체(배열 거부). 항목 추가:

   ```json
   "wafer_slot_history": {
     "description": "wafer가 공정 step을 통과한 이력 (wafer_id 기준 실개체 노드의 소스)",
     "node": { "label": "Wafer", "identity": "wafer_id", "props": ["lot", "slot"] },
     "edges": [
       {
         "type": "WENT_THROUGH",
         "target_label": "Step",
         "target_identity_from": ["step"],
         "props": ["event_time", "lot", "slot"],
         "description": "wafer가 이 공정 step을 통과한 이벤트"
       }
     ]
   }
   ```

   **`description`은 노드·엣지 모두 필수**입니다 — 비면 거부.
4. 저장 후 **리로드가 필수**입니다(파일만 고치면 반영 안 됨):

   ```bash
   curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"
   ```

   (`ASSY_ADMIN_TOKEN` 설정 서버는 헤더 필수 — 미설정이면 헤더 없이 호출 가능.) 웹서버 `_ontology_cache` 무효화 + outbox `SYSTEM_RELOAD`로 워커까지 전파됩니다.

## 3. 반영 확인

1. reload 응답이 `{"status": "success", ...}` 인지.
2. **서버/워커 로그에 검증 에러가 없는지** — 거부는 테이블 단위 + 조용해서(스킵된 테이블만 빠지고 200) 로그가 유일한 증거입니다.
3. 매핑 반영 후 재동기화 → 그래프 조회:
   ```
   GET /graph/neighbors?label=<Label>&identity=<id>
   ```
   ⚠️ `node_id` 파라미터는 없습니다(422). 매핑 변경만으로 **기존 노드가 소급 변경되지는 않습니다** — 재동기화 절차는 [CONFIG_GUIDE §3-S4](../CONFIG_GUIDE.md).

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore ontology_mapping_<yymmdd>.json.bak --yes
```

복원 후 **다시 `POST /admin/reload-configs`** — 이 파일은 캐시되므로 복원만으로는 옛 매핑이 살아나지 않습니다 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조 (`{테이블명: 매핑}`)

| 키 | 의미 |
|---|---|
| `description` | **필수** — 테이블 의미 서술(LLM 그라운딩). 엣지에도 각각 필수 |
| `node.label` / `node.identity` | 라벨(식별자 규칙) · 단일 컬럼명 또는 복합 리스트. **생략하면 그 테이블의 맵 정체성을 그대로 상속**(아래 §5-bis) |
| `node.props` | 컬럼명 문자열 또는 `{"col": "bx", "spatial": {"coord_system": "...", "axis": "x"}}` |
| `edges[].type` / `target_label` / `target_identity_from` | 엣지 타입 · 타깃 라벨 · 타깃 정체성 컬럼(들). **`target_identity_from`는 부재가 계속 오류다** — 다른 테이블의 노드를 가리키므로 "그" 정체성이 하나로 정해지지 않는다 |
| `edges[].props` / `description` | 엣지 속성(형식은 node.props와 동일) · **필수** 서술 |
| `edges[].source_override` | provenance 고정(enrichment 승격 엣지가 씀 — 사용자 파일에서도 가능) |

- 구 v1 형식(`default`/`tables` 래퍼)은 v2 로더가 무시.
- `RESOLVED_AS`는 자동 승격 — 중복 선언 금지.

### 5-bis. 맵 정체성 상속 — `@map_key_columns`와 「생략하면 전체 상속」 (2026-08-11 `68db020`)

이 그래프는 "무엇이 웨이퍼 하나를 정하는가"를 말하는 **다섯 번째 자리**였다(`table_config.map_key_columns`가 정본이고 나머지 넷이 이미 그것을 따르는데, 그래프만 따로 철자하고 있었다). 지금은 두 형태로 상속을 표현한다:

- **`node.identity`를 통째로 생략** → "이 테이블의 맵 정체성을 그대로 쓴다"는 뜻. 노드가 곧 맵과 1:1이면 이 형태를 쓴다.
- **`node.identity` 리스트 안에 `"@map_key_columns"` 토큰을 끼워 넣는다** → 그 자리에 맵 정체성 컬럼들이 스플라이스된다. 노드 정체성이 "맵 정체성 + 무언가"(예: 셀 = 맵 + 좌표)일 때 쓴다 — 생략만으로는 이 합성을 표현할 수 없어서 토큰이 명시적이다.

```json
"core_wafer_map": {
  "description": "...",
  "node": { "label": "CoreWafer" }
}
```
```json
"core_wafer_map": {
  "description": "...",
  "node": { "label": "CoreCell", "identity": ["@map_key_columns", "cx", "cy"] }
}
```

- **소비자는 `map_overlay.derive_binding_parts`이지 두 번째 리더가 아니다** — 그래프가 자기 유도 로직을 갖지 않으므로 맵과 그래프가 "구조적으로" 같은 답을 낸다(우연히 일치하는 것이 아니라 같은 함수를 부른다).
- **상속할 것이 없으면 거절이다.** `table_config`에 그 테이블의 `map_key_columns` 선언이 없으면(그리고 `lot`/`slot`이 둘 다 있는 것도 아니면) `@map_key_columns`는 풀리지 않고 **이름을 대며 거절**한다 — 조용히 빈 리스트로 접히지 않는다.
- ⚠️ **`CoreCell`은 `wafer_id`로 키잉되지 않는다** — `assy_qa` 실측 `core_wafer_map`의 24,200행 중 9,674행(40.0%)이 `wafer_id`가 비어 있고 200개 lot/slot 그룹 전부가 그런 행을 최소 하나씩 갖는다. `compose_identity`는 컴포넌트가 null이면 `None`을 반환하므로, `wafer_id`로 키잉했다면 9,674개 다이가 **조용히 그래프에서 빠졌을 것**이다(반증됨, 실행 전 되돌려짐). `RECORDED_AS_WAFER`가 이미 "이 엣지는 의도적으로 성기다(결손이 곧 보정 워크리스트)"고 선언하므로, 성긴 것은 결함이 아니다.
