# 🚀 운영 배포 — 직접 세팅해야 하는 것들 (요약)

> **Status:** 🟢 Living | **대상:** 새 환경에 assyManager를 올리는 사람
> **상세:** 각 항목의 키·함정·검증 절차는 [CONFIG_GUIDE](CONFIG_GUIDE.md)에 있다. 이 문서는 **"내가 무엇을 채워야 하는가"** 만 담는다.

---

## 0. 한 줄 원칙 — 무엇이 내 몫인가

**"이 테이블의 스키마를 누가 정하는가"** 로 갈린다.

| 구분 | 뜻 | 세팅 |
|---|---|---|
| **제품 소유** | assyManager 자신의 저장소. 이름·컬럼을 제품이 정한다 | `.sample`에 이미 선언돼 있다 — **건드리지 마라** |
| **현장 소유** | 우리 공장 데이터. 테이블명·컬럼이 사이트마다 다르다 | **전부 내가 채운다** |

`server/config/`는 통째로 gitignored다(`.sample`만 git에 올라간다). 즉 **`.sample`을 복사해서 시작하고, 그 사본이 내 자산**이다.

```bash
cd server/config
for f in *.sample; do cp "$f" "${f%.sample}"; done
```

---

## 1. 반드시 해야 하는 것 (없으면 안 뜬다)

### 1-1. 데이터베이스

`server/database/database.py`의 기본값은 `postgresql://postgres:admin@localhost:5432/assy_manager`다.
운영에서는 **환경변수로 덮는다** — 소스를 고치지 마라.

```bash
DATABASE_URL=postgresql://<user>:<pw>@<host>:5432/<db>
```

> 같은 변수로 검증 환경을 분리한다 → [개발 환경 격리](#5-검증개발-환경-선택)

### 1-2. `table_config.json` — 동적 테이블 선언 (**핵심**)

이 시스템의 스키마 SSOT다. 여기 선언된 테이블만 존재한다.

- **이미 들어 있는 것(제품 소유 — 그대로 두기)**: `wafer_map_metadata`, `map_split_registry`, `map_doe`, `map_doe_source`
- **내가 추가할 것(현장 소유)**: 우리 공장 로그·맵 테이블 전부. 아래 §2의 기능별 표 참조.

각 테이블에 필요한 것: 컬럼 정의(`column_types`), **비즈니스 키**(`business_key`), 복합키면 `composite_key_source` + `composite_key_separator`.

> ⚠️ **구분자 함정**: 맵 키는 `_`가 흔하고 테이블명에도 `_`가 있다. 복합키 구분자로 `_`를 쓰면 파싱이 깨진다. 제품 소유 3종은 `|`를 쓴다 — 새로 만들 때도 `|` 권장.

### 1-3. 인제션 워크스페이스

`server/ingestion_workspace/<테이블명>/` 아래에 `raws/ archives/ err/ config/ auto_update/ scripts/`가 필요하다. 파일을 `raws/`에 떨구면 워처가 집어간다.

> 워크스페이스별 `config/config.json`은 **폐기된 개념**이다(하위호환 읽기만 남아 있음). 테이블명·파싱 규칙은 전역 `table_config.json`이 이긴다. 새로 만들지 마라.

---

## 2. 기능을 켤 때만 필요한 것

각 기능은 **현장 테이블이 `table_config.json`에 선언돼 있어야** 동작한다. 아래 이름은 **예시일 뿐 표준이 아니다** — 우리 이름으로 선언하고, config의 `table`/`columns`를 그 이름에 맞추면 된다.

| 기능 | config 파일 | 필요한 현장 테이블(예시) |
|---|---|---|
| **전사 계획 / DOE** (M2) | `transfer_plan_config.json` | stage 참조 테이블 — `dt_map`, `dt_log`, `bonding_log`, `eds_fail_map` 등 |
| **본딩 가용량** (M1) | `bonding_plan_config.json` | `bonding_log`, `core_defect_map`, `eds_fail_map`, `wafer_process` |
| **맵 오버레이** | `map_overlay_config.json` | 겹칠 맵 테이블들 (x/y 컬럼 + 맵 키 컬럼 선언 필요) |
| **체인 인제션** | `chain_rules.json` | 트리거/타깃 테이블 + `server/mappers/`의 매퍼 모듈 |
| **결손 보완** | `enrichment_rules.json` | 규칙이 참조하는 테이블 |
| **온톨로지 그래프** | `ontology_mapping.json` | 노드/엣지로 승격할 테이블 |

**상태 확인**: 바인딩이 제대로 붙었는지는 API가 알려준다. `missing`이 뜨면 그 테이블이 `table_config.json`에 없거나 컬럼명이 어긋난 것이다.

```bash
curl http://localhost:8080/api/transfer-plan/stages
```

---

## 3. 맵을 쓴다면 — 정렬의 전제

**`wafer_map_metadata` 등록이 전제다.** 맵을 담는 모든 테이블(defect·EDS·DT·bonding·core)이 대상이고, **미등록은 정상 상태가 아니라 누락**이다.

- 정렬은 소스·타깃 메타의 **델타에서 유도**된다. 별도 보정 레이어는 없다.
- 계측 결과(DEFECT WF 돌려서 잰 값)도 **메타에 기록**한다.
- 메타가 없으면 화면에 `화면기준` 칩이 뜬다 — "지금 화면 규격으로 가정해서 그렸다"는 뜻이다. 이 칩이 보이면 그 맵은 메타를 등록해야 한다.

`maps.json`에 **제품 규격별 프리셋**을 만들어 두면 등록이 쉬워진다. 프리셋 한 세트가 곧 메타 JSON이다:

```json
{"grid_cols":40,"grid_rows":40,"grid_start_x":1,"grid_start_y":1,"grid_y_invert":false,
 "rotation":180,"side":"front","phys_wafer_dia":300.0,"phys_chip_x":7.0,"phys_chip_y":7.0,
 "phys_offset_x":0,"phys_offset_y":0,"phys_edge_margin":3.0}
```

> 격자 크기(`grid_cols/rows/start`)는 **방향·물리 규격에서 파생**된다. 데이터 좌표 범위에서 역산하지 마라.

---

## 4. 선택 — 기본값으로 둬도 되는 것

| 파일 | 안 만들면 | 언제 손대나 |
|---|---|---|
| `ingestion_settings.json` | 전부 기본값 동작 | heavy 임계(기본 10MB) 조정, dedup·재개 끄기 |
| `auto_update_control.json` | 수집기 전부 활성 | 특정 수집기만 끄고 싶을 때 |
| `maps.json` | 프리셋 없음 | 맵 프리셋 등록 시 (§3) |

---

## 5. 검증/개발 환경 (선택)

운영 데이터 위에서 테스트하지 않으려면 격리 환경을 쓴다.

```bash
python server/scripts/dev_env/devenv.py snapshot   # 운영에서 읽기 전용 스냅샷
python server/scripts/dev_env/devenv.py up         # :8081, 워처·스케줄러 없음
python server/scripts/dev_env/devenv.py down
```

`ASSY_DATA_ROOT`가 `config/`·`ingestion_workspace/`를 통째로 옮기는 단일 지점이다(`server/paths.py`). 안 걸면 기존 경로 그대로다.

---

## 6. 순서 요약

1. PostgreSQL 준비 → `DATABASE_URL` 설정
2. `server/config/*.sample` → 확장자 떼고 복사
3. **`table_config.json`에 우리 현장 테이블 선언** (여기가 대부분의 작업)
4. `server/ingestion_workspace/<테이블>/` 디렉터리 생성
5. 켤 기능의 config에서 `table`/`columns`를 우리 이름으로 맞춤 (§2)
6. 맵을 쓴다면 `wafer_map_metadata` 등록 (§3)
7. 기동 → `/api/transfer-plan/stages` 등으로 바인딩 상태 확인

---

## 7. 함정 (실제로 물린 것들)

- **`.sample`을 복사만 하고 테이블 선언을 안 하면** 바인딩이 전부 `missing`이 된다. `.sample`은 *기능 템플릿*이지 완성된 설정이 아니다.
- **`/tables/{t}/schema`가 200이라고 물리 반영의 증거가 아니다** — config 싱글턴을 읽는다. 실제 컬럼은 `information_schema`로 확인하라.
- **기존 테이블에 컬럼을 추가하면** 런타임 ALTER는 `config_watcher`만 하는데, 원자적 쓰기(temp+rename)는 감지되지 않는다. `/admin/reload-configs`는 **신규 CREATE 전용**이다.
- **존재하지 않는 API 경로는 정적 catch-all이 HTML을 200으로 반환한다.** 헬스체크 근거로 쓰지 마라 — 응답이 JSON인지 확인할 것.
- **`server/config/`와 `server/ingestion_workspace/`는 백업 대상이다.** git에 없다.
