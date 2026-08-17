# Ledger V2 · Ontology Config Explorer 인수인계

> **상태:** `COMPLETE / APPROVED`
> **작성 기준:** 2026-08-18 main `cbe139e1`
> **독립 Audit:** `01a00f3f-4249-7bf0-ab96-6d32c27273fe`
> **운영 파괴 작업:** 별도 사용자 승인 전 금지

이 문서는 2026-08-14의 구 포크/구현자/Data Manager 세션 운영 지시를 대체한다. 현재는 별도
구현 세션 이름이나 휘발성 메시지 큐가 정본이 아니다. 설계·구현·검수의 정본은 아래 파일과
Git commit이며, 개발 완료 뒤 지정 Audit task에 exact commit을 제출한다.

## 1. 지금 어디까지 왔나

- Ledger V2 1~7단계: `COMPLETE / APPROVED`
- Ontology Config Explorer 전체 계약: `COMPLETE / APPROVED`
- production authoring root: `server/config/ontology/`
- 현재 V2 cutover source: `lot_event`
- UI: `http://127.0.0.1:8080/admin.html#ontology`
- active snapshot 기준: `57d36c07271a019242722cc4627f1c0a9c6b477e632f29f32034e331928b0da0`

승인 구현 커밋:

| 범위 | exact commit |
|---|---|
| Stage 2 Bundle/validator | `ac380e4b26ac19b7e5d96529cfd37478cd5b2f6b` |
| Stage 3 Registry/snapshot | `135a440fa2cbbfba83b8964b0dfc159ca0e1b4f2` |
| Stage 4 RoleFrame/Pack compiler | `1d9bd4aa2f1b0ca5012c959e4647d8feab956ee1` |
| Stage 5 Source Preparer | `4508c12c5acad6b3a48affde61220a5e2e1709a9` |
| Stage 6 runtime/parity | `b98f0c3804f5bdfc6653670da571f8fef0e9e129` |
| Stage 7 manifest cutover | `f516268eadae5505c586ce5235e76dd729c1e573` |
| Explorer 전체 완료 | `2d1ad863106fc228566cab1a386265957f5c3587` |
| 최종 상태 동기화 | `cbe139e1adae1c808bfb5774f24ae22ede1cf2ea` |

## 2. 시스템의 본질

R&D 사용자가 보는 기본 계약은 표이고, 온톨로지/그래프는 관계·근거를 보존하는 배경 엔진이다.
목표는 불완전한 소스에서 놀라움을 줄이는 다음 행동을 산출하는 것이다. Ledger V2는 이를 위해
새 소스의 의미를 Python 하드코딩에 흩뜨리지 않고 선언과 제한된 mapper hook으로 분리한다.

```text
manifest.json
  → ledger_config + catalog + dataflows
  → strict LedgerSetupBundle
  → immutable Registry/Snapshot
  → 기존 cursor의 bounded physical batch
  → Source Preparer의 verified batch join
  → pandas EventFrame
  → BaseLedgerMapper / RoleEmission / RoleFrame
  → Pack-owned LedgerFrame
  → 기존 gate → LedgerStore → cursor transaction
```

핵심 불변식:

1. Pack/Profile/Registry 작성은 `ledger_config.json`에서 함께 본다.
2. cursor는 base physical column만 읽는다.
3. join은 physical UNIQUE 검증을 통과한 descriptor만 사용한다.
4. mapper는 Atom이나 object payload를 직접 만들지 않고 Role만 해석한다.
5. dry-run과 execute는 같은 snapshot/compiler를 사용한다.
6. 한 source event의 Claim은 전부 통과하거나 Atom 0·cursor 미이동이다.
7. Position/lookup을 V2 의미 계층에 다시 만들지 않는다.

## 3. 먼저 읽을 정본

1. `docs/overview/SYSTEM_OVERVIEW.md`
2. `docs/process/PROJECT_STATUS.md` 최상단
3. `docs/guide/ONTOLOGY_LEDGER_SETUP.md` — V2 설정 파일·필드·샘플·검증 절차
4. `ledger_v2_redesign_plan_20260817/README.md`
5. `ledger_v2_redesign_plan_20260817/00_MASTER_PLAN.md`
6. `ledger_v2_redesign_plan_20260817/CONFIG_CANON.md`
7. 해당 단계의 `STAGE_*_ACCEPTANCE_EVIDENCE.md`
8. `ontology_config_explorer_plan/01_DISCOVERY_AND_STATE_CONTRACT.md`
9. `ontology_config_explorer_plan/02_IMPLEMENTATION_AND_ACCEPTANCE.md`
10. `task/ontology_config_explorer_pending.md` — 완료된 원 요구사항
11. `task/ontology_config_explorer_reference.html` — CSS·3단 배치 시각 기준본

## 4. 파일 소유권

### Ledger V2

| 책임 | 파일 |
|---|---|
| manifest와 authoring 선언 | `server/config/ontology/` |
| Bundle strict validation | `server/ledger/setup_bundle.py` |
| immutable Registry/Snapshot | `server/ledger/setup_registry.py` |
| RoleFrame/Pack compiler | `server/ledger/roleframe.py` |
| verified batch preparation | `server/ledger/source_preparation.py` |
| preview/execute와 기존 transaction 연결 | `server/ledger/runtime_v2.py` |
| legacy↔V2 의미 비교 | `server/ledger/shadow_parity.py` |
| selector와 비파괴 cutover | `server/ledger/cutover_v2.py`, `server/ledger/backfill.py` |

### Ontology Config Explorer

| 책임 | 파일 |
|---|---|
| compiled graph/read model | `server/ledger/config_explorer.py` |
| active/draft context service | `server/ledger/config_explorer_service.py` |
| draft/review/revise/CAS activation | `server/ledger/config_drafts.py` |
| strict Admin API | `server/ontology_config_explorer_router.py` |
| 단일 client state/history | `client2/src/ontology_explorer_store.js` |
| 화면·interaction | `client2/src/ontology_explorer.js`, `ontology_explorer_view.js`, `ontology_explorer.css` |
| file-backed 이종 계보 예제 | `server/config/sample/ontology/transfer_explorer/` |

## 5. Explorer 사용·검증

서버 실행:

```powershell
conda activate assy_manager
python run_decoupled_app.py --server-only
```

`--server-only`는 데스크톱 셸을 띄우지 않는다는 뜻이며 백엔드 보조 프로세스는 launcher가 함께
감독한다. Explorer는 `admin.html#ontology`에서 연다. 인증은 두 상태다.

- `ASSY_ADMIN_TOKEN`이 설정돼 있으면 모든 Admin 요청에 정확한 `X-Admin-Token`이 필요하다.
- token이 설정되지 않으면 ordinary read route(예: active `/view`)는 열릴 수 있지만,
  draft/write 같은 strict route는 `503`으로 fail-closed한다.

승인된 집중 검증:

- backend 직접군: `165 passed`
- client Explorer harness: `35 assertions / 0 failed`
- client contracts: `7 passed`
- production build: Vite `107 modules`
- 브라우저: 1920×1080, 700×900, 320×800
- 10,000-node fixture: `<2s`, 응답 `<=213 nodes`, payload `<1.5MB`
- dirty save→reedit→keep→back→forward→back에서 editor bytes/cursor 보존
- file-backed 계보: `CoreDie → DTDie → BondComponent → FinalChip`

현재 HEAD에서 마지막 집중 재검증은 Explorer backend `21 passed`, client state `35/0`이다.
full server suite와 Explorer PostgreSQL E2E는 사용자 지시에 따라 생략했으며 통과로 표현하지
않는다.

## 6. 절대 자동으로 하지 말 것

- 운영 Ledger/cursor reset 또는 source replay
- 운영 DB migration/write
- legacy config/translator/template 이동·삭제
- DT/observation source를 parity 승인 없이 V2로 전환
- raw mapping이나 임의 index 문자열로 VerifiedJoinDescriptor 발급
- active config 직접 편집 또는 manifest 밖 경로 쓰기
- 기준본과 다른 dashboard/graph 중심 Explorer 재디자인

이 항목은 기능 미완료가 아니라 별도 사용자 승인이 필요한 운영 경계다.

## 7. 알려진 환경 상태

- 2026-08-18 로컬 서버 기동에서 `graph_nodes`, `graph_edges`, `graph_sync_state` 세 구 그래프
  테이블 누락 경고가 보였다. 서버와 Explorer `/health`, `admin.html`은 200으로 기동했다.
  해당 테이블을 만들거나 migration하지 말고, 실제로 구 그래프 기능이 다시 필요할 때 별도
  범위와 승인을 받는다.
- 화면이 비어 있으면 `ASSY_ADMIN_TOKEN` 설정 여부와 응답 상태를 함께 확인한다. token이
  설정된 환경의 `401`은 header 누락/불일치이고, token 미설정 환경의 strict route `503`은
  쓰기 인증을 구성하지 않은 상태를 안전하게 거절한 것이다.
- task의 HTML은 시각 기준본이지 runtime JavaScript 정본이 아니다.

## 8. 다음 합법적 작업 순서

1. 사용자가 지정한 새 source/Pack을 `server/config/ontology/` 선언으로 추가한다.
2. manifest dry-run과 해당 source 집중 테스트로 readiness를 확인한다.
3. legacy↔V2 shadow parity에서 설명 없는 차이 0을 증명한다.
4. 지정 Audit task에 단계·상태·exact commit·테스트 범위를 명시해 검수를 요청한다.
5. Audit REJECT면 해당 반례만 최소 수정해 재검수하고, APPROVE면 제품 상태를 동기화한다.

DT/observation cutover, dependency replay worklist, 운영 reset/legacy retirement는 각각 별도 범위다.
사용자 승인 없이 다음 항목으로 묶지 않는다.

## 9. 종료 체크

- 관련 집중 테스트만 실행하고 full suite를 통과했다고 과장하지 않는다.
- `docs/history/YYYYMMDD_HHMMSS_*.md`와 리빙 문서를 함께 갱신한다.
- `python docs/history/gen_index.py`를 실행한다.
- 사용자 파일을 명시 없이 reset/stash/delete하지 않는다.
- commit 후 지정 Audit task에 exact SHA를 보고한다.
