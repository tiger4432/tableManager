# `.sample` config v1 잔재 정정 + 스위트의 사용자 자산 오염 차단

> 커밋 `9a8ede8` (+ 보드 `eefec81`) · 2026-07-26 21:51 · 도메인 Server / 설정·테스트
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 설정 지도: [CONFIG_GUIDE](../guide/CONFIG_GUIDE.md)

## 배경

두 가지가 동시에 드러났다.

1. **신규 환경이 깨진 채로 시작한다.** `transfer_plan_config.json.sample`의 `plan_store`가 아직 v1 형태(`plan_id`/`layer_from`/`layer_to` × `transfer_plan_doe`)였는데, 코드는 `(ref_table, map_key, doe_value, band_seq)`를 요구한다. **필수 키가 하나도 없었으므로** `.sample`을 복사해 출발한 환경은 `plan_store.doe = missing`, 즉 계획 저장이 아예 동작하지 않는다.
2. **테스트가 라이브 사용자 자산에 쓴다.** `test_map_presets_api`는 사용자 `server/config/maps.json`을 읽고 **`POST`로 써넣었으며**, 단언 대상은 `maps.json.sample`에만 있는 키였다 — 즉 **구조적으로 통과할 수 없는** 테스트였고, 그래서 세션 내내 "상시 허용 실패"로 취급돼 왔다. 항상 실패하는 테스트 하나가 스위트 전체의 신호를 죽인다. `test_file_ingestion_callback_direct`는 워크스페이스 루트를 `dirname(__file__)/..`로 계산해 라이브 `ingestion_workspace/inventory_master/config/config.json`을 매 실행 덮어썼다.

## 변경 내용

### 1. `transfer_plan_config.json.sample` — v1 잔재 제거

`plan_store`가 코드가 실제로 읽는 튜플로 교체됐다.

| 역할 | before | after |
|---|---|---|
| `doe` | `transfer_plan_doe` / `plan_id, doe_value, source_lot, …` — **필수 4개 전부 부재** | `map_doe` / `ref_table, map_key, doe_value, band_seq` + `stack_band, qty_total, knobs, note` |
| `doe_source` | **키 없음** | `map_doe_source` / 위 4개 + `source_lot, source_slot` + `qty, note` |
| `plan` · `map` · `doe_layer` | v1 바인딩 | **제거**(계획 헤더·계획 맵 사본·"층마다 소스 1개" 차원 소멸) |
| `source_region` | 키 없음 | **키 없음 유지** — 휴면 바인딩이 `missing`을 보고하면 잡음이 된다. 활성화 절차만 `__comment`로 남김 |

### 2. `table_config.json.sample` — **선언 여부가 곧 소유권 표명**이다

이 배치에서 가장 중요한 판단. 샘플에 무엇을 넣을지는 **"이 스키마를 누가 정하는가"**로 가른다.

- **제품 소유**(assyManager 자신의 저장소 — 이름·컬럼을 제품이 정한다) → **선언한다**: `map_doe`, `map_doe_source`, `map_split_registry`.
- **현장 소유**(사이트마다 이름이 다르다) → **선언하지 않는다**: `bonding_log`, `eds_fail_map`, `wafer_process`, stage가 가리키는 맵 테이블 등. 예시 스키마를 박으면 **표준이 존재하는 것처럼 오해**된다.

세 정의 모두 `__comment`로 소유권과 bk 설계 이유를 명시했다. 특히 복합 키 구분자는 반드시 `|`다:

```json
"map_doe": {
  "__comment": "[제품 소유 저장소 — 이름·컬럼을 바꾸지 마라] … band_seq(정수 서수)가 정체를 지고 stack_band(자유 텍스트 라벨)는 비키 컬럼이다 — 라벨을 키에 넣으면 라벨 수정이 곧 re-key가 되어 하위 자재 행이 고아가 된다.",
  "business_key": "doe_key",
  "composite_key_source": ["ref_table", "map_key", "doe_value", "band_seq"],
  "composite_key_separator": "|"
}
```

`map_key` 자체가 `_` 조인 문자열이고 테이블명에도 `_`가 흔해, `_`를 쓰면 키가 모호해진다(클라 `map_editor.js`의 `SPLIT_KEY_SEP`와 일치해야 한다).

`__comment` 키는 경계 계약에 무해함이 확인됐다 — `GET /tables/{t}/schema`는 원본 dict를 그대로 내보내지 않고 `display_columns`·`column_types`·`business_key`만 조립하며(`server/main.py:1530-1556`), `init_dynamic_models`는 `column_types`만 읽는다.

### 3. `map_overlay_config.json.sample` · `bonding_plan_config.json.sample`

폐기 테이블 `transfer_plan_map`의 `table_bindings`·`paint_lock` 항목 제거(계획 맵 사본이 없어졌으므로 계획 캔버스의 잠금은 그 stage의 `target_map` 테이블에 직접 선언한다). 두 파일에 "전제 테이블" 주석 1줄 추가 — 절 번호가 아니라 **제목**을 참조하게 해 번호 재정렬에 깨지지 않게 했다.

`enrichment_rules.json.sample`에는 **의도적으로** `__comment`를 넣지 않았다 — 이 파일의 루트는 `{rule_name: rule}`이라 주석 키가 규칙으로 파싱돼 매 로드마다 경고가 찍힌다(`server/enrichment_config.py:237-244`).

### 4. 테스트 격리 2건

`test_map_presets_api` — 저장소가 DB가 아니라 파일이므로 경로 상수를 갈아끼운다:

```python
maps_path = tmp_path / "maps.json"
maps_path.write_text(json.dumps(seeded), encoding="utf-8")
monkeypatch.setattr(main, "MAPS_CONFIG_PATH", str(maps_path))
assert str(tmp_path) in main.MAPS_CONFIG_PATH              # 격리 가드
...
assert set(res_data["presets"]) == {"pytest_seed_std"}     # 심은 것 '만' 보여야 한다
```

단언을 "심은 키가 있다"가 아니라 **"심은 키만 있다"**로 쓴 것이 핵심이다 — 몽키패치가 풀리면 라이브 프리셋이 섞여 들어와 즉시 깨진다.

`test_file_ingestion_callback_direct` — 몽키패치가 필요 없었다. `IngestionHandler.__init__`이 경로를 전부 생성자 인자로 받으므로(`server/parsers/directory_watcher.py:441`) `tmp_path`를 넘기면 끝난다. **폐기된 `config.json` 생성은 아예 제거**했고(`5fac5f0`에서 폐기된 개념 — `config_path=None`이 허용되고 `columns` 키는 아무도 읽지 않으며 테이블명은 `default_table_name`으로 동일 해석된다), 다시 세워지면 깨지도록 부정 단언을 넣었다.

## 아키텍처 영향

- **경계 계약 무변경.** API 시그니처·응답 형태·DB 스키마 모두 그대로다. `server/transfer_plan.py`는 무수정이며 `test_transfer_plan.py` 53 passed로 계약 불변을 확인했다.
- **`.sample` 정합성은 자기 파일만으로 판정할 수 없다** — 바인딩 샘플은 참조 테이블이 `table_config.json`에 등록돼야 해석된다. 신규 환경 시뮬레이션(`.sample` 3종만 임시 디렉터리에 복사해 로드, 엔진은 `sqlite:///:memory:`)에서 `plan_store: {"doe": "connected", "doe_source": "connected"}` 확인. 네거티브 대조군으로 **컬럼 축뿐 아니라 테이블 미선언 축**도 흔들었다 — 이번 사건의 실제 원인 축이 후자였기 때문이다.
- 스위트 **414 passed / 0 failed**(허용 실패 0). 격리 증명은 통과가 아니라 **바이트 동일성**으로 했다: 라이브 `maps.json`의 sha256·크기·**mtime까지 동일**(= 파일이 열리지도 않았다), `ingestion_workspace` 9,230파일 트리 `changed=0`. 스위트 실행 중 새로 생긴 3파일이 **수집기의 산물**임은 추측이 아니라 **pytest를 돌리지 않은 같은 길이의 창**을 관측해 대조군으로 증명했다.

## 남은 것 (해소되지 않음 — 축소해 적지 않는다)

- **이미 발생한 오염은 복구 불가.** `server/ingestion_workspace/inventory_master/config/config.json`의 원본 내용은 **미상이며 되돌릴 수 없다**(gitignored). 현재 내용은 테스트 페이로드 그대로다. **"무해"라고 단정할 수 없다** — 하위호환 읽기 경로가 살아 있고 그중 `std_parse`는 실제 파싱 규칙을 주입하므로, 사용자가 거기에 `std_parse`를 두었다면 그 설정은 소실됐다. 사용자 자산이라 지우지도 되돌리지도 않았다.
- 라이브 `maps.json`의 `custom_1784890104442`(테스트 산물)도 사용자 자산이라 미삭제 — 정리 후보로만 남긴다.
- 이슈 #16ⓐ(**pytest가 운영 PostgreSQL에 DDL 발행** — `main.py` import 시 모듈 레벨 `Base.metadata.create_all`)는 **미해소**다. 이번 배치는 config·워크스페이스 축만 닫았다.
- `ontology_mapping.json.sample`은 테이블 참조 스캔만 했고 전수 정합 감사는 하지 않았다.

## 다음 단계

- 개발 환경 격리(별도 DB·config 경로·수집기 정지)가 근본 해법 — 보드 최우선 트랙.
- `table_config.json.sample`의 `large_table_100`(성능 테스트용으로 보이는 엔트리)을 템플릿에서 뺄지 판단.
