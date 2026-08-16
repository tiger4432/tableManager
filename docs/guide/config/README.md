# 📁 config/ — 운영 서버 config 파일 세팅 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-08-11 (**신규 행 `audit_history_config.json`** — `dab9152`+`2630790`가 이 config를 도입했는데 **문서 행이 아예 없었다**. 행/셀 이력 페이지 상한 + 전역 「최근」 패널 discovery 걸음 상한을 **한 파일**로 묶는다(`audit_cache`가 `audit_history.load_config()`를 재사용, 두 번째 로더 없음). 🔴 **`.sample`이 `recent_*` 넷을 아직 안 적고 있다** — 코드(`RECENT_DEFAULTS`)는 이미 이 파일을 읽으므로 새 가이드가 정본이고 `.sample`이 낡은 쪽이다(총괄 보고). 직전 2026-08-04 🔴 **`notation_rules.json` 행을 다시 썼습니다 — `8d306a5`가 그 모델을 뒤집었습니다.** 파생 컬럼(`<컬럼>_norm`)이 **아무도 소비하기 전에** 철회됐고, 지금은 **한 단계 선언 + 조회 시점 폴드**이며 **저장되는 값이 없습니다.** 종전 이 헤더가 적고 있던 「`table_config.json`이 1단계, 여기가 2단계」는 **거짓**입니다. 이 환경에는 아직 실파일이 없습니다(`.sample`만). 직전 `table_config.json` 행: **새 키 `version_column`**(`092b83f` — 버전 게이트. 「반영 확인」이 이 키만 다릅니다: 물리 스키마를 안 바꾸므로 `information_schema`가 아니라 **다음 적재의 `[VersionGate]` 로그**가 증거입니다). 같은 날 `transfer_plan_config.json` 행: **반영 확인의 1순위가 `GET /admin/transfer-plan/dry-run`으로 바뀌었고**(`8817dde`) 좌표/값 컬럼은 `map_overlay_config`에서 유도된다 — 그 파일 가이드를 **재작성**했다. 🔴 **「반영 확인」 열에 라우트가 생기면 여기부터 고친다** — 운영자가 이 표에서 명령을 고른다. 직전 2026-07-31 `virtual_join_rules.json` 행이 **실행 착지**(`d70a33d`)를 반영 — 선언만 검증하던 기능이 읽기 경로에서 실제로 조인한다. ⚠️ 그 행은 2026-07-31에 추가됐는데 이 헤더는 07-29에 멈춰 있었다 — **행을 더하면 여기도 함께 고친다**. 직전 `suggest_config.json`·`effort_metric.json` 추가, 2026-07-28 신설) | **Owner:** Lead / Backend
> 상위: [CONFIG_GUIDE](../CONFIG_GUIDE.md) — **온보딩 지도의 정본.** 시나리오 체크리스트(§3)·리로드 규율(§4)·함정 모음(§6)은 거기서 봅니다. 이 폴더는 **운영 서버에서 각 파일을 실제로 세팅하는 절차**입니다.

## 시작하기 전에 (전 파일 공통)

- `server/config/`의 실파일은 **전부 gitignored·현장 소유**입니다. 처음이면 `server/config/sample/`의 `.sample`을 상위 폴더에 확장자 없이 복사해 시작합니다. 백업은 `server/config/backup/`에 있으며, `.sample`·`.bak` 편집은 실행 설정에 아무 효과가 없습니다.
- **편집 전 스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
- `ASSY_ADMIN_TOKEN`이 설정된 서버는 **모든 `/admin/*` 호출에 `X-Admin-Token` 헤더**가 필요합니다 → [DEPLOY_SETUP §1-4](../DEPLOY_SETUP.md).
- `scheduler_status.json` · `supervisor_status.json` · `worker_heartbeats/*.json`은 **시스템이 쓰는 상태 파일**입니다 — 운영자 config가 아니며 **절대 손편집하지 마십시오**(다음 틱에 덮어써지고, 없는 것이 정상 상태).

## 파일별 가이드

| 파일 (`server/config/`) | 켜는 기능 | 반영 시점 | 반영 확인 | 가이드 |
|---|---|---|---|---|
| `table_config.json` | 모든 동적 테이블 스키마 **SSOT** — 다른 config의 전제. **+ `version_column`**(2026-08-04 `092b83f` — 버전이 권위이고 도착 순서가 아니다. 🔴 **선언 전 파생 타깃 확인 필수** → [§7.2](./table_config.md)) | 신규/컬럼추가 = watcher 핫(**in-place 저장만**) · 삭제/타입변경 = **재기동** · `version_column`은 **스키마를 안 바꿔 watcher 반영만으로 즉시** | watcher 로그 + `information_schema` · `version_column`은 다음 적재의 **`[VersionGate]` 로그 줄** | [table_config.md](./table_config.md) |
| **`audit_history_config.json`** (2026-08-11 신설) | 행/셀 감사 이력 조회의 페이지 상한(`default_limit`/`max_limit`) + **전역 「최근」 패널 discovery 걸음의 상한**(`recent_*` 넷 — `server/audit_cache.py`가 같은 파일을 재사용, 두 번째 로더 없음) | 요청마다 재읽기(요청당 1회 스냅샷) | 전용 조회 라우트 없음 — `limit`을 크게 요청해 clamp+`truncated`로 확인, 오타는 서버 로그 `[AuditCache] '<key>' must be a positive integer` | [audit_history_config.md](./audit_history_config.md) |
| `database.json` | DB 접속 정보(이름·비번·호스트) — 환경변수 `DATABASE_URL` 미설정 시 | **재기동**(전 프로세스, 핫리로드 없음) | 기동 로그 `[db] url source=config file` | [database.md](./database.md) |
| `transfer_plan_config.json` | M2 전사 계획 — stage 선언 + 계획 저장소. **좌표/값 컬럼은 `map_overlay_config`에서 유도**되므로 대부분 안 써도 된다(`8817dde`) | 요청마다 재읽기 | 🔴 **`GET /admin/transfer-plan/dry-run`**(역할별 수용/거절 + 어느 철자가 이겼는지 — 1순위) · 그다음 `GET /api/transfer-plan/stages` | [transfer_plan_config.md](./transfer_plan_config.md) |
| `bonding_plan_config.json` | M1 본딩 계획 — role→실테이블 바인딩 | 요청마다 재읽기 | `GET /api/bonding-plan/core-summary` | [bonding_plan_config.md](./bonding_plan_config.md) |
| `map_overlay_config.json` | 맵 오버레이 바인딩 + 페인트 잠금 정본 | 요청마다 재읽기 | `GET /api/maps/paint-rules` | [map_overlay_config.md](./map_overlay_config.md) |
| `maps.json` | 웨이퍼 물리 규격 프리셋 (**UI/API로 관리**) | 요청마다 재읽기 | `GET /api/map-presets` | [maps.md](./maps.md) |
| 🗄️ `ontology_mapping.json` | ⚰️ **[2026-08-14 `2ec78b9`] 소비자 0 — 고쳐도 아무 일도 안 일어납니다.** ~~그래프 노드/엣지 매핑 v2~~ | `POST /admin/reload-configs` | 서버 로그 + `GET /graph/neighbors` | [ontology_mapping.md](./ontology_mapping.md) |
| `enrichment_rules.json` | 결손 보정 워크리스트 + 파생·승격 | 조회 즉시 / 파생·승격은 `reload-configs` | `GET /enrichment/rules` + 워커 로그 | [enrichment_rules.md](./enrichment_rules.md) |
| `chain_rules.json` | 체인 인제션 룰 | `POST /admin/reload-configs` | `GET /admin/chain/rules` | [chain_rules.md](./chain_rules.md) |
| `auto_update_control.json` | 수집기 on/off (**API로만 쓰기**) | 즉시(매 사이클·매 요청 재계산) | `GET /admin/auto-update/status` | [auto_update_control.md](./auto_update_control.md) |
| `ingestion_settings.json` | 인제션 노브 — heavy 임계·dedup·재개 | 즉시(**다음 파일부터**) | watcher 로그의 heavy 라우팅 줄 | [ingestion_settings.md](./ingestion_settings.md) |
| `effort_metric.json` | V1 계기 — 상호작용 점수 배점 + 컨텍스트 유지 전이 | 즉시(다음 조회부터) | `GET /api/effort/config` | [effort_metric.md](./effort_metric.md) |
| `suggest_config.json` | 입력 제안(고유값 조회) 노브 + **접두 인덱스 대상 선정** | 조회 노브 = 즉시 / `index_*` = **`setup_db_performance.py` 재실행** | `GET /tables/{t}/columns/{c}/values` | [suggest_config.md](./suggest_config.md) |
| `notation_rules.json` | **표기 정규화** — 「이 컬럼의 표기가 정규화됐다」 선언 한 줄(`{"dt_log": {"core_lot": true}}`). 🔴 **아무것도 저장하지 않습니다** — 소비자가 **조회 시점에 SQL에서 비교의 양쪽을** 접습니다. 켜는 것은 **한 단계**(전제: 그 컬럼이 `table_config`에 `"string"`). 🔴 **[2026-08-04 `8d306a5`] 파생 컬럼 `<컬럼>_norm` 모델은 철회됐습니다** — 「층 셋」·재파생 스크립트·쓰기 거부는 전부 소멸. 🔴 **접힌 키를 쓰는 가상 조인은 함수 인덱스가 필요합니다**(평범한 UNIQUE는 접힌 키의 유일성을 증명 못 함) | 저장 후 **TTL 5초** 또는 `POST /admin/reload-configs` | `GET /admin/config/resolve?domain=notation` · 무엇이 합쳐지는지는 **`GET /admin/config/notation/preview`**(병합군) | [notation_rules_config.md](./notation_rules_config.md) |
| `virtual_join_rules.json` | 저장하지 않는 조인 선언 + **팬아웃 가드**(승인 조건 = 조인 키를 덮는 UNIQUE 인덱스). **읽기 경로가 실제로 실행**해 `expose` 컬럼을 붙인다(`d70a33d`) — 왼쪽과 이름이 겹치면 **부재일 때만 채운다** | 조회 즉시 | 모양은 `GET /admin/config/resolve?domain=virtual_join` · 승인 여부는 `GET /admin/config/virtual-join/verify` | [virtual_join_rules.md](./virtual_join_rules.md) |

## 잘못됐을 때 (전 파일 공통)

```bash
conda run -n assy_manager python server/scripts/backup_config.py list
conda run -n assy_manager python server/scripts/backup_config.py restore <config>_<yymmdd>.json.bak --yes
```

restore는 **일부러 제자리(in-place) 쓰기**를 합니다 — `table_config.json`이면 config watcher가 발화하고, 현재 파일은 `.prerollback.<ts>`로 보존됩니다. 되돌릴 원본은 날짜가 확장자 **앞**에 붙은 주간 스냅샷뿐입니다(`.bak` 3종 구분 → [CONFIG_GUIDE §1](../CONFIG_GUIDE.md)). 코드까지 얽힌 되돌리기는 [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md) — 순서는 **config → 코드 → 재기동**입니다.
