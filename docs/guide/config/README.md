# 📁 config/ — 운영 서버 config 파일 세팅 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-07-29 (`suggest_config.json` 추가 — F3 입력 제안 노브 + 접두 인덱스 대상 선정. 직전 `effort_metric.json` 추가 — V1 정본 계기 배점. 직전 2026-07-28 신설 — 파일별 세팅 절차. CONFIG_GUIDE §5의 키 상세를 이 폴더로 이관) | **Owner:** Lead / Backend
> 상위: [CONFIG_GUIDE](../CONFIG_GUIDE.md) — **온보딩 지도의 정본.** 시나리오 체크리스트(§3)·리로드 규율(§4)·함정 모음(§6)은 거기서 봅니다. 이 폴더는 **운영 서버에서 각 파일을 실제로 세팅하는 절차**입니다.

## 시작하기 전에 (전 파일 공통)

- `server/config/`의 실파일은 **전부 gitignored·현장 소유**입니다. 처음이면 `.sample`을 확장자 없이 복사해 시작합니다 (`.sample`·`.bak` 편집은 아무 효과 없음).
- **편집 전 스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
- `ASSY_ADMIN_TOKEN`이 설정된 서버는 **모든 `/admin/*` 호출에 `X-Admin-Token` 헤더**가 필요합니다 → [DEPLOY_SETUP §1-4](../DEPLOY_SETUP.md).
- `scheduler_status.json` · `supervisor_status.json` · `worker_heartbeats/*.json`은 **시스템이 쓰는 상태 파일**입니다 — 운영자 config가 아니며 **절대 손편집하지 마십시오**(다음 틱에 덮어써지고, 없는 것이 정상 상태).

## 파일별 가이드

| 파일 (`server/config/`) | 켜는 기능 | 반영 시점 | 반영 확인 | 가이드 |
|---|---|---|---|---|
| `table_config.json` | 모든 동적 테이블 스키마 **SSOT** — 다른 config의 전제 | 신규/컬럼추가 = watcher 핫(**in-place 저장만**) · 삭제/타입변경 = **재기동** | watcher 로그 + `information_schema` | [table_config.md](./table_config.md) |
| `database.json` | DB 접속 정보(이름·비번·호스트) — 환경변수 `DATABASE_URL` 미설정 시 | **재기동**(전 프로세스, 핫리로드 없음) | 기동 로그 `[db] url source=config file` | [database.md](./database.md) |
| `transfer_plan_config.json` | M2 전사 계획 — stage 선언 + 계획 저장소 | 요청마다 재읽기 | `GET /api/transfer-plan/stages` | [transfer_plan_config.md](./transfer_plan_config.md) |
| `bonding_plan_config.json` | M1 본딩 계획 — role→실테이블 바인딩 | 요청마다 재읽기 | `GET /api/bonding-plan/core-summary` | [bonding_plan_config.md](./bonding_plan_config.md) |
| `map_overlay_config.json` | 맵 오버레이 바인딩 + 페인트 잠금 정본 | 요청마다 재읽기 | `GET /api/maps/paint-rules` | [map_overlay_config.md](./map_overlay_config.md) |
| `maps.json` | 웨이퍼 물리 규격 프리셋 (**UI/API로 관리**) | 요청마다 재읽기 | `GET /api/map-presets` | [maps.md](./maps.md) |
| `ontology_mapping.json` | 그래프 노드/엣지 매핑 v2 | `POST /admin/reload-configs` | 서버 로그 + `GET /graph/neighbors` | [ontology_mapping.md](./ontology_mapping.md) |
| `enrichment_rules.json` | 결손 보정 워크리스트 + 파생·승격 | 조회 즉시 / 파생·승격은 `reload-configs` | `GET /enrichment/rules` + 워커 로그 | [enrichment_rules.md](./enrichment_rules.md) |
| `chain_rules.json` | 체인 인제션 룰 | `POST /admin/reload-configs` | `GET /admin/chain/rules` | [chain_rules.md](./chain_rules.md) |
| `auto_update_control.json` | 수집기 on/off (**API로만 쓰기**) | 즉시(매 사이클·매 요청 재계산) | `GET /admin/auto-update/status` | [auto_update_control.md](./auto_update_control.md) |
| `ingestion_settings.json` | 인제션 노브 — heavy 임계·dedup·재개 | 즉시(**다음 파일부터**) | watcher 로그의 heavy 라우팅 줄 | [ingestion_settings.md](./ingestion_settings.md) |
| `effort_metric.json` | V1 계기 — 상호작용 점수 배점 + 컨텍스트 유지 전이 | 즉시(다음 조회부터) | `GET /api/effort/config` | [effort_metric.md](./effort_metric.md) |
| `suggest_config.json` | 입력 제안(고유값 조회) 노브 + **접두 인덱스 대상 선정** | 조회 노브 = 즉시 / `index_*` = **`setup_db_performance.py` 재실행** | `GET /tables/{t}/columns/{c}/values` | [suggest_config.md](./suggest_config.md) |
| `virtual_join_rules.json` | 저장하지 않는 조인 선언 + **팬아웃 가드**(터지는 선언은 로드 안 됨) | 조회 즉시 | `GET /admin/config/resolve?domain=virtual_join` | [virtual_join_rules.md](./virtual_join_rules.md) |

## 잘못됐을 때 (전 파일 공통)

```bash
conda run -n assy_manager python server/scripts/backup_config.py list
conda run -n assy_manager python server/scripts/backup_config.py restore <config>_<yymmdd>.json.bak --yes
```

restore는 **일부러 제자리(in-place) 쓰기**를 합니다 — `table_config.json`이면 config watcher가 발화하고, 현재 파일은 `.prerollback.<ts>`로 보존됩니다. 되돌릴 원본은 날짜가 확장자 **앞**에 붙은 주간 스냅샷뿐입니다(`.bak` 3종 구분 → [CONFIG_GUIDE §1](../CONFIG_GUIDE.md)). 코드까지 얽힌 되돌리기는 [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md) — 순서는 **config → 코드 → 재기동**입니다.
