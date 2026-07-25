# 보고서: 맵 에디터 value description 강화 — split 서술의 관리 테이블 승격

발신: Client PM / 수신: 총괄 PM
브랜치: `worktree-agent-aec38ea300e456414` (worktree — main 병합·빌드 금지 준수, `node --check`까지만 수행)
지시서: `agent_workspace/tasks/Client_map_split_registry_task.md`

## 1. 결론 요약

| 항목 | 상태 |
|---|---|
| ① `map_split_registry` 테이블 config 설계 | 완료 — **전문 §2에 수록 (gitignored — 총괄이 본체 적용 필요)** |
| ② 온톨로지 매핑(SplitCondition) | 완료 — **전문 §3에 수록 (gitignored — 총괄 적용 필요)**. 엣지는 노드-온리로 보류, §7 에스컬레이션 |
| ③ map_editor.js legend 서버 승격 | 완료 — 서버 registry 우선 로드 / localStorage 캐시 강등 / 1회 마이그레이션 제안 |
| ④ UX 강화 3종 | 완료 — 여러 줄 textarea + push 시 서술 누락 confirm + 수정자·시각 표시 |
| 검증 | `node --check` PASS, mock 하니스 **38/38 PASS** (`client2/tests/split_registry_harness.mjs`) |
| 경계 계약 | 불변 — 신규 서버 API 0건, 기존 제네릭 `GET /tables/{t}/data` + `PUT /tables/{t}/data/updates`만 사용 |
| 좌표 변환·그리기 로직 | 무접촉 (legend/IO/push 확인 관문만 수정) |

## 2. [총괄 적용 필요] `server/config/table_config.json` 추가 전문

최상위 객체에 아래 키를 추가:

```json
"map_split_registry": {
  "business_key": "split_key",
  "composite_key_source": ["ref_table", "map_key", "value"],
  "composite_key_separator": "|",
  "column_types": {
    "split_key": "string",
    "ref_table": "string",
    "map_key": "string",
    "value": "string",
    "split_desc": "string",
    "color": "string",
    "eventtime": "string"
  },
  "display_columns": ["split_key", "ref_table", "map_key", "value", "split_desc", "color", "eventtime"]
}
```

설계 근거:
- **separator `"|"` (기존 관례 `"_"`와 다름 — 의도적)**: `map_key` 자체가 `getMapIdFromMeta`의 `"_"` 조인 산물이고 테이블명에도 `_`가 흔해, `"_"` 분리자는 bk 충돌·역파싱 모호를 만든다. 클라이언트 `SPLIT_KEY_SEP = '|'`(map_editor.js)와 **반드시 일치**해야 한다.
- `split_desc`는 `"string"` → 동적 모델에서 무제한 VARCHAR(`models.py init_dynamic_models`의 `String`) — 여러 줄 자연어 저장에 제약 없음(개행 포함 JSON 문자열로 왕복 확인).
- display_columns ⊇ column_types + bk 소스 (F5 교훈 준수). `map_key_columns` 없음 — 맵 에디터 테이블 셀렉터(맵 테이블만 노출)에 등장하지 않게 하는 의도된 부재.
- `std_parse` 기본 유지(별도 플래그 없음).

## 3. [총괄 적용 필요] `server/config/ontology_mapping.json` 추가 전문

```json
"map_split_registry": {
  "description": "웨이퍼 맵 value별 실험 split 조건의 자연어 기록 (맵 에디터 legend의 서버 영속화 — value가 어떤 실험 조건 분기인지 사람이 서술)",
  "node": {
    "label": "SplitCondition",
    "identity": "split_key",
    "props": ["split_desc", "color", "value"]
  },
  "edges": []
}
```

- description 필수 규칙 준수(테이블 서술 포함).
- **엣지 보류 사유는 §7-1 에스컬레이션** 참조.

## 4. 클라이언트 변경 상세 (`client2/src/map_editor.js` +318/-20, `client2/map_editor.html`)

### 4-1. 신규 코어 (legend의 서버 영속화 계층)
- 상수 `SPLIT_REGISTRY_TABLE`/`SPLIT_KEY_SEP`, 상태 `legendMeta`(value→{updated_by, updated_at}).
- **순수 함수(하니스 검증 대상)**: `buildSplitKey`, `buildLegendRegistryUpdates`(PUT 페이로드 빌더 — business_key_val 명시 + composite 소스 3컬럼 동봉 + `source_name:"user"` + `updated_by:CURRENT_USER` + `eventtime`), `parseLegendRegistryRows`(**셀 계약 `{value,...}` 객체로 읽기**, 테이블 단위 조회 시 value 중복은 updated_at 최신 승리), `getMissingDescValues`, `formatLegendMetaText`.
- IO: `fetchLegendFromServer`(GET + ref_table/map_key equals 필터), `loadLegend`(서버 → localStorage 캐시 → DEFAULT 폴백 오케스트레이터, 서버 성공 시 캐시 역동기화), `saveLegendToServer`(PUT 업서트, map_key 미확정 시 조용히 스킵→push 때 일괄 저장), `scheduleLegendServerSave`(800ms 디바운스 — 입력 중 포커스 보존), `persistLegend`(캐시 즉시 + 서버 디바운스의 단일 관문), `renderLegendMetaOnly`(DOM 유지 메타 갱신), `maybeOfferLegendMigration`(1회 제안, `map_split_migrated_<table>|<map>` 플래그).

### 4-2. 흐름 재배선
- `switchTable`: `loadLegendFromStorage()` → `await loadLegend(table, null)` (메타 미입력 시점이라 테이블 단위 registry, value별 최신 dedupe).
- `loadExistingMap`: `mapIdStr`을 `loadedMapKey`로 함수 스코프 승격 → 데이터 기반 legend 자동 구성 **후** registry를 최우선 override(서술·색), registry 전용 값은 브러시로 추가 노출. registry가 비어 있으면 마이그레이션 1회 제안. registry 실패는 `console.warn`으로 격리(맵 로드 자체는 진행).
- 모든 legend 변조 지점(값 rename/desc/색/추가/삭제/autoPaintE1E2)의 `saveLegendToStorage()` → `persistLegend()`. 단, loadExistingMap의 **자동 생성 legend는 캐시만** 저장(placeholder 서술로 registry 오염 방지).
- `pushMapData`: ① Clean-Replace confirm **앞에** 서술 누락 관문 — push 대상 고유 값 중 desc 빈 값 N개를 `confirm("split 서술이 없는 값 N개 — 그래도 저장?")` ② 셀 push 성공 시 `saveLegendToServer(mapIdStr)` 일괄 저장(맵-서술 원자적 동행) + 성공/실패 토스트.
- `addNewLegendRow`의 기본 desc를 `VALUE n` → **빈 문자열**로 변경(placeholder 서술이 "작성됨"으로 위장하는 것 방지 — push 관문이 실누락을 정확히 잡도록).

### 4-3. UX
- desc 입력: 한 줄 input → **자동 확장 textarea**(max 120px, `resize:none`, placeholder "실험 split 조건 서술…").
- 각 legend 행 desc 아래 **`updated_by · updated_at` 메타 라인**(서버 registry 기준, 미저장 시 "서버 미저장").
- 행 클릭 브러시 선택 가드에 `TEXTAREA` 추가(서술 편집 클릭이 브러시 전환으로 오작동하는 회귀 방지).
- HTML: legend 헤더 "Description"→"Split Description", 안내 문구에 서버 공유 명시, 컬럼 폭 미세 조정(desc 확대). tokens.css 무수정.

## 5. 검증

### 5-1. 정적 + 하니스 (worktree에서 실행 완료)
- `node --check client2/src/map_editor.js` → PASS.
- `node client2/tests/split_registry_harness.mjs` → **38/38 PASS** (node_modules 불필요 — vm 샌드박스가 소스에서 함수를 추출해 fetch/localStorage/confirm 스텁으로 구동):
  - T1 페이로드 빌더(bk `ref|map|value` 조립, trim, 빈 value 필터, source_name/updated_by/eventtime)
  - T2 응답 파서(셀 계약 읽기, dedupe 최신 승리, color 폴백, 빈 응답 안전)
  - T3 서술 누락 관문(공백 desc·legend 부재 검출)
  - T5 로드 우선순위 4폴백(server → local(빈 서버) → offline(캐시) → DEFAULT)
  - T6 저장(PUT 경로/바디, legendMeta 즉시 갱신, 실패 시 예외 전파 없이 false)
  - T7 마이그레이션 1회 제안(플래그, 재제안 없음, mapKey 없으면 무동작)

### 5-2. E2E 절차 (라이브 — 총괄 수행, config 적용 후)
1. §2·§3 전문을 본체 `server/config/`에 적용 → 어드민 "설정 리로드"(POST `/admin/reload-configs`). **재기동 없이** `map_split_registry` 물리 테이블 생성 확인(`reload_local_process_cache` → `models.refresh_dynamic_models`가 런타임 CREATE 수행 — 이슈 #7 해소 경로 검증 겸. main.py:2396-2410).
2. 본체에서 `cd client2 && npm run build` + dist 커밋(worktree 제약으로 빌드 미수행).
3. 맵 에디터: 테이블 선택 → 메타 입력 → legend desc를 여러 줄로 작성 → Push. (a) desc 빈 값이 있으면 경고 confirm 노출 (b) push 후 "Split 서술 registry 저장 완료" 토스트 (c) legend 행에 `사용자 · 시각` 표시.
4. index 그리드에서 `map_split_registry` 조회 → `split_key = <table>|<map>|<value>` 행들과 `split_desc` 개행 보존 확인.
5. Load Existing Map 재수행 → 서버 서술·색이 legend에 복원되는지 + 다른 브라우저(localStorage 없는)에서도 동일 legend가 보이는지(팀 공유).
6. localStorage에만 legend가 있는 기존 브라우저로 Load → 마이그레이션 confirm 1회 노출 → 수락 시 registry 업로드.
7. graph_nodes에 `SplitCondition` 노드 등장 확인(materializer 자동 승격).
8. 오프라인 열화: 서버 정지 상태에서 맵 에디터 진입 → legend가 localStorage 캐시/DEFAULT로 정상 폴백(콘솔 warn만).

## 6. 경계 계약 준수 확인
- 소비 API: 기존 `GET /tables/{t}/data`(filters equals) + `PUT /tables/{t}/data/updates`만 — 신규 엔드포인트 0.
- 셀 형태: 읽기는 전부 `d.col?.value`/`updated_by` 객체 접근, 쓰기는 기존 wafer_map_metadata push와 동일한 updates 원시값 + `business_key_val` 명시 패턴.
- WS 미사용(맵 에디터 관례 유지), `/schema` 무접촉.

## 7. 에스컬레이션 (총괄 판단 요청)
1. **SplitCondition 엣지 설계 보류**: 현행 온톨로지에 맵을 표상하는 노드 라벨이 없다(bonding_map·wafer_map_metadata 모두 미매핑, MapRecord 라벨 부재). 제안: `wafer_map_metadata`를 `Map` 노드(identity `map_pk`)로 승격하고 SplitCondition→`SPLIT_OF`→Map 엣지(`target_identity_from: ["ref_table","map_key"]`)를 거는 안 — 단, graph 워커의 composite identity 조인 분리자(`_`)와 registry bk 분리자(`|`)의 정합을 server-pm과 합의해야 안전. 그 전까지 노드-온리.
2. **registry 행 삭제/rename 정책**: legend 삭제·값 rename 시 서버 registry의 구 행은 **이력으로 잔존**시킨다(제네릭 batch_delete는 row_id 필요 + 실험 서술은 삭제보다 보존이 가치). 화면상 노이즈가 되면 후속으로 "비활성" 컬럼 또는 map_key 단위 정리 UI 검토.
3. `wafer_map_metadata`의 map_id는 `default_map` 폴백이 있어 registry도 `map_key="default_map"`가 생길 수 있다(push 시 동일 관례로 저장). 현행 유지가 일관적이라 판단.

## 8. 히스토리 초안 (통합 시 총괄 기록용)
> feat(client/map): 맵 legend의 value description을 `map_split_registry` 관리 테이블로 승격 — 실험 split 조건의 자연어 기록을 서버 영속·팀 공유·온톨로지(SplitCondition) 대상화. localStorage는 오프라인 캐시로 강등(1회 마이그레이션 제안), push 시 서술 누락 경고 confirm, desc 여러 줄 textarea + 수정자·시각 표시. 기존 제네릭 테이블 API만 사용(신규 API 0). 하니스 38/38.

## 9. 리빙 문서 갱신 초안 (worktree 제약으로 미수정 — 총괄/doc-keeper 반영)
- `docs/architecture/CODE_MAP.md` map_editor.js 항목: "레전드/브러시" 줄에 `loadLegend/saveLegendToServer(서버 registry 우선, localStorage 캐시 강등)` 추가, 라인 수 ~2,771 → ~3,070.
- `docs/map_editor/architecture_and_management.md`: legend 저장소 절 신설(map_split_registry, bk `ref_table|map_key|value`, 분리자 `|`).
- `docs/overview/SYSTEM_OVERVIEW.md` 테이블 목록에 map_split_registry 1줄.

## 10. 교훈 제안 (client-pm 교훈 파일 반영 후보)
- **함정**: composite bk의 분리자를 관례(`_`)로 따라가면 소스 값 자체에 `_` 조인이 있는 경우(map_key, 테이블명) bk가 모호해진다. **올바른 방법**: 소스 값의 문자 구성을 먼저 확인하고 충돌 없는 분리자를 config `composite_key_separator`에 명시 + 클라이언트 상수와 쌍으로 일치시킨다.
- **함정**: export 없는 단일 페이지 스크립트(map_editor.js)는 빌드 없이 검증이 막힌다고 착각하기 쉽다. **올바른 방법**: 신규 로직을 순수 함수로 승격해 두면 `node:vm` 추출 하니스(`client2/tests/split_registry_harness.mjs` 패턴)로 worktree에서도 회귀 검증이 된다.

## 11. 부수 발견 (무수정 — 참고)
- `client2/src/utils.js:7` `getLocalTimeString`의 시(hh)가 `pad()` 미적용 — `2026-07-25 9:05:03`처럼 나온다. eventtime 문자열 정렬에 경미한 영향 가능(본 기능의 최신 승리 판정은 서버 `updated_at` 기준이라 무해). 별도 소소한 수정 후보.
