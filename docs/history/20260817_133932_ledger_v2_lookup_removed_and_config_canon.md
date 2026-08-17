# Ledger v2 lookup 제거·virtual join 상속·Config 정본 확정

## 요청

- v2 온톨로지에서 lookup을 제거한다.
- Ledger cursor가 virtual join column을 직접 읽을 수 있는지 실제 코드로 확인한다.
- DT source가 `dt_inventory`를 이용해 die 신원을 완성하는 경계를 정한다.
- 모든 설정을 유기적인 config root에 모으고 Registry 등록값도 config로 관리한다.
- Pack과 Profile은 종전처럼 `ledger_config.json` 한 파일 아래에서 함께 작성한다.

## 확인한 현행 사실

- `server/ledger/backfill.py`의 cursor는 base relation을 직접 `SELECT`한다.
- virtual join은 `main.fetch_and_merge_metadata` 뒤
  `virtual_join_executor.attach()`가 웹 조회 payload에 붙이며 저장 column이 아니다.
- collide column은 왼쪽 값이 있으면 유지하고, 비었을 때만 오른쪽 값으로 채운다.
- 현재 production `server/config/virtual_join_rules.json`은 없고 sample의 과거 DT 선언은 retired다.
- 현행 `dt_inventory`는 `dt_job_id` business key와 `dt_lot/dt_slot/frame` 정보를 가진다.

## 확정한 목표 구조

```text
dt_log physical cursor
→ pandas source batch
→ Source Preparer
   → verified virtual-join rule ID 상속
   → dt_inventory batch join
   → frame/coordinate 계산
→ complete EventFrame
→ RoleFrame
→ Pack compiler
→ existing gate/store/cursor transaction
```

- Profile/Bundle/Registry/compiler의 `lookup`, `declared_lookup`, `LookupRegistry` 제거.
- cursor는 base physical column/watermark만 읽는다.
- join relation/key/expose/folding/cardinality/UNIQUE 근거는 virtual join config가 단독 소유한다.
- UI executor와 Ledger preparer는 같은 immutable `VerifiedJoinDescriptor`를 소비한다.
- UI absent-only/`미상`/셀 표시 계약은 Ledger identity에 사용하지 않고 raw/joined evidence를
  분리 보존한다.
- join 0/다건/frame 결측은 event 전체 거절, Atom 0, cursor 미이동이다.
- right row 사후 수정은 dependency replay/worklist 없이는 cutover `NO-GO`다.

## Config 정본

```text
server/config/ontology/
├─ manifest.json
├─ ledger_config.json
├─ catalog/
│  ├─ tables.json
│  └─ virtual_joins.json
└─ dataflows/
   ├─ chains.json
   └─ enrichments.json
```

`ledger_config.json`은 `vocabulary`, `entities`, `source_preparers`, `packs`, `profiles`,
`sources` section을 함께 가진다. Registry는 각 section의 immutable compiled view이며 도메인
등록값을 Python builtin과 병합하지 않는다. catalog/dataflow만 역할상 별도 파일로 둔다.

## 변경 문서

- `ledger_v2_redesign_plan_20260817/CONFIG_CANON.md` — 파일별 역할·소유·금지 내용·legacy 이동표.
- `ledger_v2_redesign_plan_20260817/TARGET_ARCHITECTURE_AND_SSOT.md` — 목표 흐름·DT 예시·정본 목록.
- 같은 폴더의 단계별 계획 전반 — lookup 제거, pandas preparation, virtual join 상속,
  config-root/Registry-as-config 수락 기준.
- `docs/overview/SYSTEM_OVERVIEW.md` 등 Ledger 리빙 문서와 virtual join 가이드 — 현행 동결
  구현과 v2 목표 경계 동기화.

## 사이드 이펙트와 방어

- right relation 변경이 base cursor에 잡히지 않는 위험을 dependency replay/worklist 필수로 명시.
- 기존 잘못된 left 값이 absent-only로 confirmed right 값을 가리는 위험을 evidence 분리로 방어.
- Registry 파일 과분할로 작성성이 나빠진 초안을 사용자 피드백에 따라 폐기하고
  `ledger_config.json` 단일 authoring surface로 복구.
- 현재 runtime code, DB schema/data, cursor에는 변경 없음.
- 기존 dirty/deletion/untracked 파일은 reset·stash·overwrite하지 않음.

## 검증

- 계획 폴더의 폐기된 lookup/옛 분할 경로 검색.
- `git diff --check` 통과(기존 line-ending 경고만 존재).
- 문서 전용 변경이므로 runtime pytest/PostgreSQL E2E는 실행하지 않음.

## 다음 단계

계획 1단계 승인 전 구현하지 않는다. 첫 구현 단계는 현행 hardcoding/config loader/cursor/
virtual join descriptor 호출부와 baseline을 읽기 전용으로 확정하는 작업이다.
