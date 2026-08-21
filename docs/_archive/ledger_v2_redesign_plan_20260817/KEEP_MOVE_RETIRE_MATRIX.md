# Ledger v2 Keep / Move / Retire

> 상태: `IN_REVIEW` / `NOT_APPROVED`
> `retire` 항목도 stage 7 cutover 승인 전에는 삭제하지 않는다.

## Keep — Kernel

| 대상 | 유지 계약 |
|---|---|
| `ledger_events` schema/envelope/index | append-only Claim, provenance, partition/index |
| molecule gate | 한 source event 전부 승인 또는 전부 거절 |
| `LedgerStore.write_batch` | atoms와 cursor 한 transaction |
| cursor transaction orchestration | 실패 event Atom 0, cursor 미이동 |
| resolver/trace/coverage/structure/read API | 표/그래프 소비 계약 |
| LedgerFrame structure/validator | Pack compiler의 유일 최종 출력 |
| virtual join UNIQUE verifier | right cardinality의 물리 증거 |
| UI virtual join executor | UI absent-only 표시 경로 |

## Move — 선언과 해석

| 현행 | 목표 정본 | 이유 |
|---|---|---|
| Vocabulary builtin 등록값 | `ledger_config.json.entities/vocabulary` | entry 추가에 Python 수정 금지 |
| builtin Pack/Role | `ledger_config.json.packs` | Role과 emission 단일 소유 |
| emitter entity/predicate/payload literal | Pack emission | 의미 정본 단일화 |
| source kind/columns/grouping | Source/Profile + compiled SourcePlan | source별 validator 분기 축소 |
| mapper ID/version builtin | config mappers + trusted implementation class | ID와 code capability 분리 |
| lot event pairing | Base mapper partition/custom hook | 공통/자유 경계 |
| transfer relation read | pandas Source Preparer | compiler DB read 제거 |
| physical table config | `catalog/tables.json` | 물리/의미 분리 |
| virtual join declarations | `catalog/virtual_joins.json` | UI/Ledger 단일 join 계약 |
| chain/enrichment declarations | `dataflows/` | dependency replay/worklist 연결 |

## Retire — parity 뒤 제거

| 대상 | 제거 조건 |
|---|---|
| Position constants/Registry/helper/payload | stage Entity 이동 Pack parity |
| `declared_lookup`/adapter/mapper lookup capability | Source Preparer E2E |
| Python claim emitter registry | generic Pack compiler parity |
| mapper의 Atom/LedgerFrame 직접 생성 | RoleFrame mapper parity |
| source별 legacy translators | source별 shadow parity/rollback 증거 |
| legacy Template/container Profile API | import 격리와 public 비참조 확인 |
| source-kind별 dry-run 변환 중복 | same compiler parity |
| legacy authoring configs | stage 7 cutover/호출부 전수 검사 |

## 새로 만들 것

| 대상 | stage |
|---|---:|
| `LedgerSetupBundle` + strict loader | 2 |
| config-only registries + immutable snapshot/hash | 3 |
| RoleFrame + Base mapper + Pack compiler | 4 |
| Source Preparer + shared join descriptor adapter | 5 |
| right dependency provenance/replay worklist | 5~6 |
| shadow parity/PostgreSQL E2E/scale proof | 6 |

## Cutover NO-GO

- mapper가 Atom/object_payload/Position을 직접 만든다.
- compiler/Profile이 DB를 읽거나 lookup adapter를 호출한다.
- preparer가 virtual join key/expose/folding을 복사한다.
- 성공 뒤 right row 변경을 재평가할 길이 없다.
- incomplete event인데 cursor가 전진한다.
- Registry entry 추가에 compiler core 수정이 필요하다.
- 격리 PostgreSQL에서 atom/cursor 원자성이 미검증이다.
