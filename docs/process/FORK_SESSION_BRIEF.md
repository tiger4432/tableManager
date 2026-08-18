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
- production authoring root: `server/config/ontology/` — 🔴 **[2026-08-18] 파일 «하나»**(`ledger_config.json`, `setup_version: 3`). `manifest.json`·`catalog/`·`dataflows/`는 은퇴했고 옮겨진 원본은 `server/config/_ontology_pre_single_file_20260818/`(지원 경로 아님)
- 현재 선언된 source: `lot_event` — 🔴 **선언이 곧 활성화**라 `mode` selector는 없다. 확인은 `conda run -n assy_manager python -m ledger.setup`(`server/`에서, 쓰기 없음)
- UI: `http://127.0.0.1:8080/admin.html#ontology`
- active snapshot 기준: `f6223d6cbd24e2012f8936ecf88447df7b3729039dcd9fc673f96492513c2752`
  (단일 파일 접기 이후 실측. 이전 값 `57d36c07…`은 manifest 시절이다)
- 🔴 **스냅샷 해시는 게이트가 아니다.** 컴파일러를 고치면 뜻이 그대로여도 움직인다
  (2026-08-18 실측: `363c693e`→`fd51baaf`→`f6223d6c`, 세 번 다 원자 디프 0).
  판정은 **원자**로 한다 — 기준선 `task/evidence/ledger_atom_baseline_20260818.json`,
  뜨는 도구 `task/evidence/ledger_atom_baseline.py`, 비교 `task/evidence/ledger_atom_diff.py`.
  변환·이관 때 섹션이 조용히 빠지지 않았는지는 `task/evidence/ledger_config_section_diff.py`.
- 진행 중 프로그램: `task/ledger_simplification_program.md`
  (1라운드 단일 파일·자기 등록 — 대부분 착지 / 2라운드 매퍼 개주 / 3라운드 explorer 작성 모드)
- 🎯 **목적지를 한 번에 보려면** `task/evidence/ledger_config_final_form_example.jsonc`
  — lot_event 부분은 지금 실제로 도는 선언, void 부분은 「시각 없음 선언」 착지 후의 모양.
  명세 일곱 개를 조립하지 않고 최종 형태를 읽을 수 있다.
- 2026-08-18 착지분 요약: 셋업이 **파일 하나·일곱 칸**(`tables`는 은퇴, 물리 스키마는
  `table_config.json`이 정본) · **선언이 곧 활성화**(chains 폐기) · 신뢰 목록을 코드에서
  도출(`ledger/implementations.py`) · 첫 등장 탐침 선언화 · legacy 번역기 5개와 문법
  드라이버 4개 은퇴 · 모듈 개명(`cutover_v2`→`setup`) · `ledger.setup --root`로 초안 검증.
  **열 번의 착지 모두 원자 디프 0.**
- 인제션 쪽 도구(같은 날): `scripts/ledger_deploy_preflight.py`(배포 전 상태 판정) ·
  `scripts/check_external_sources.py`(외부 디렉터리 등록 확인) ·
  `scripts/replay_ingestion.py`(읽기 전용 소스의 파일 하나 재적재) ·
  `scripts/seed_void_sample_tree.py`(폴더 규격 실물 생성). 외부 소스는 이제 `parser`를
  비우면 그 표의 워크스페이스 플러그인으로 들어간다(`401dc72`).
- ⚠️ **이 박스의 표 모양·DB·config를 운영 사실로 인용하지 말 것.** 2026-08-18 하루에 세 번
  틀렸다(빈 DB 접속 / 지워진 config / `void` 표의 스키마). 운영 `void`는 키가
  `x·y·waferid·tkouttime·void_index`이고 정상 가동 중이다 — 이 박스의 `void`와 다른 표다.

승인 구현 커밋:

| 범위 | exact commit |
|---|---|
| Stage 2 Bundle/validator | `ac380e4b26ac19b7e5d96529cfd37478cd5b2f6b` |
| Stage 3 Registry/snapshot | `135a440fa2cbbfba83b8964b0dfc159ca0e1b4f2` |
| Stage 4 RoleFrame/Pack compiler | `1d9bd4aa2f1b0ca5012c959e4647d8feab956ee1` |
| Stage 5 Source Preparer | `4508c12c5acad6b3a48affde61220a5e2e1709a9` |
| Stage 6 runtime/parity | `b98f0c3804f5bdfc6653670da571f8fef0e9e129` |
| Stage 7 config/cutover(당시 manifest 모양) | `f516268eadae5505c586ce5235e76dd729c1e573` |
| 단일 파일 셋업으로 접기 | `141d95e` · 라이브 root 접기 `caba302` |
| 셋업 경계 개명(`cutover_v2`→`setup`) | `b4c5870` · 구 모듈 삭제 `382b78c` |
| Explorer 전체 완료 | `2d1ad863106fc228566cab1a386265957f5c3587` |
| 최종 상태 동기화 | `cbe139e1adae1c808bfb5774f24ae22ede1cf2ea` |

## 2. 시스템의 본질

R&D 사용자가 보는 기본 계약은 표이고, 온톨로지/그래프는 관계·근거를 보존하는 배경 엔진이다.
목표는 불완전한 소스에서 놀라움을 줄이는 다음 행동을 산출하는 것이다. Ledger V2는 이를 위해
새 소스의 의미를 Python 하드코딩에 흩뜨리지 않고 선언과 제한된 mapper hook으로 분리한다.

```text
server/config/ontology/ledger_config.json   (파일 하나)
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

1. Pack/Profile/Registry/catalog 작성은 `ledger_config.json` **한 파일**에서 함께 본다. config root에 다른 `.json`이 있으면 로더가 `unlisted_config_file`로 거절한다(검사는 재귀한다).
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
| authoring 선언 전부 | `server/config/ontology/ledger_config.json` (파일 하나) |
| Bundle strict validation | `server/ledger/setup_bundle.py` |
| immutable Registry/Snapshot | `server/ledger/setup_registry.py` |
| RoleFrame/Pack compiler | `server/ledger/roleframe.py` |
| verified batch preparation | `server/ledger/source_preparation.py` |
| preview/execute와 기존 transaction 연결 | `server/ledger/runtime_v2.py` |
| legacy↔V2 의미 비교 | `server/ledger/shadow_parity.py` |
| 로드 경계(`load_setup`)와 비파괴 dry-run | `server/ledger/setup.py` |
| 실행 드라이버(하나) | `server/ledger/backfill.py` |
| 실행 가능한 `implementation_id` 발견 | `server/ledger/implementations.py` |

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
- 🔴 준비가 끝나지 않은 source를 `sources`에 적기 — **선언이 곧 활성화**라 그 순간 돈다
- raw mapping이나 임의 index 문자열로 VerifiedJoinDescriptor 발급
- active config 직접 편집, config root 안에 다른 `.json`(백업·초안 포함) 두기
- 기준본과 다른 dashboard/graph 중심 Explorer 재디자인

이 항목은 기능 미완료가 아니라 별도 사용자 승인이 필요한 운영 경계다.

## 7. 알려진 환경 상태

- 2026-08-18 로컬 서버 기동에서 `graph_nodes`, `graph_edges`, `graph_sync_state` 세 구 그래프
  테이블 누락 경고가 보였다. 서버와 Explorer `/health`, `admin.html`은 200으로 기동했다.
  해당 테이블을 만들거나 migration하지 말고, 실제로 구 그래프 기능이 다시 필요할 때 별도
  범위와 승인을 받는다.
- 화면이 비어 있으면 `ASSY_ADMIN_TOKEN` 설정 여부와 응답 상태를 함께 확인한다. token이
  설정된 환경에서 header 누락은 `401`, 설정값과 다른 token은 `403`이다. token 미설정
  환경의 strict route `503`은 쓰기 인증을 구성하지 않은 상태를 안전하게 거절한 것이다.
- task의 HTML은 시각 기준본이지 runtime JavaScript 정본이 아니다.

## 8. 다음 합법적 작업 순서

1. 사용자가 지정한 새 source/Pack을 `ledger_config.json`에 적는다 — **초안 폴더의 사본에
   먼저**(`server/config/ontology/`를 폴더째 복사해 두면 된다). `sources`는 **마지막**에
   적는다 — 그것이 켜는 행위다.
2. **초안을 먼저 검증한다** — 운영 파일을 덮어쓰기 «전»에:
   `conda run -n assy_manager python -m ledger.setup --root <초안폴더>`(`server`에서, 쓰기 없음).
   `--root`는 `ledger_config.json`을 **담은 디렉터리**를 가리키고, 답의 `config_root`가
   초안을 검증했는지 운영을 검증했는지를 말한다. 착지 뒤에는 인자 없이 한 번 더 돌려
   `readiness`와 해당 source 집중 테스트로 확인한다.
3. 지정 Audit task에 단계·상태·exact commit·테스트 범위를 명시해 검수를 요청한다.
4. Audit REJECT면 해당 반례만 최소 수정해 재검수하고, APPROVE면 제품 상태를 동기화한다.

DT/observation cutover, dependency replay worklist, 운영 reset/legacy retirement는 각각 별도 범위다.
사용자 승인 없이 다음 항목으로 묶지 않는다.

## 9. 종료 체크

- 관련 집중 테스트만 실행하고 full suite를 통과했다고 과장하지 않는다.
- `docs/history/YYYYMMDD_HHMMSS_*.md`와 리빙 문서를 함께 갱신한다.
- `python docs/history/gen_index.py`를 실행한다.
- 사용자 파일을 명시 없이 reset/stash/delete하지 않는다.
- commit 후 지정 Audit task에 exact SHA를 보고한다.
