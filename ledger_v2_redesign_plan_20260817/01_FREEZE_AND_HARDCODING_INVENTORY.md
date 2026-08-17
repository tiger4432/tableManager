# 1단계 — 동결 경계와 하드코딩 전수 조사

> 실행 상태: `COMPLETE` · 승인: `APPROVED` · 2026-08-17

## 목표

코드를 고치기 전에 무엇을 유지하고 무엇을 재작성할지 symbol 단위로 확정한다. 현재
3단계는 `AWAITING_REVIEW/NOT_APPROVED`로 동결하고 신규 기능을 얹지 않는다.

## 작업

### 1. 현재 변경 경계

- git status, branch, HEAD, staged/unstaged/untracked 전수 기록
- 이번 Profile/mapper 작업 파일과 기존 사용자 dirty 파일 분리
- current Phase 3가 실제로 어느 driver kind에만 연결됐는지 호출 그래프로 확인
- 현재 PostgreSQL baseline과 skip/failure 이유 기록
- 기존 `_archive` 계획은 참고자료로만 표시

사용자 파일을 reset/checkout/stash/overwrite하지 않는다.

### 2. 하드코딩 inventory

최소 다음 항목을 `HARDCODING_INVENTORY.md`로 산출한다.

| 범주 | 조사 대상 | 분류 |
|---|---|---|
| predicate signature | `vocabulary.py`, config 확장 | Kernel 유지 / declaration 이동 |
| entity identity | `ENTITY_TYPES`, emitter의 `Lot/lot`, `Wafer/wafer` | Registry 이동 |
| Position | `PLACE_*`, Container TypeRegistry, `_position`, translators | v2 제거·stage Entity로 치환 |
| Pack | built-in Pack/Role | declaration 이동 |
| emission | `_emit_*`, translator payload literal | generic compiler 이동 |
| source event | `row_identity`, grouping, order, timezone, cursor | Source plan 이동 |
| runtime lookup | table/column SQL, select, cardinality | v2에서 제거·source preparation으로 이동 |
| execution | driver, dry-run, gate, store, cursor | 기존 Kernel 유지 |
| legacy | translator/config/templates/import | parity 후 은퇴 |

각 항목은 다음 열을 가진다.

```text
file / symbol / literal / current owner / duplicate owners /
runtime caller / tests / v2 destination / keep|move|retire
```

### 3. 계약 중복·불일치 실측

최소 다음 대조를 자동화하거나 읽기 전용 보고로 남긴다.

- Pack required Roles ↔ emitter가 읽는 Roles
- Pack emission 후보 ↔ Vocabulary required payload
- 기존 Position Registry keys ↔ 실제 translator/emitter keys(삭제 migration 근거)
- source preparer join key/output ↔ 실제 relation columns/index
- Ledger cursor SELECT ↔ virtual-only column 비참조
- source preparer join literal ↔ virtual_join rule 중복 여부
- virtual join UI executor ↔ source preparer의 compiled join descriptor 동일성
- right relation 수정 뒤 이미 처리한 source event의 재평가 경로
- source Profile column ↔ table_config column
- source event identity ↔ cursor uniqueness/index
- mapper derivation ↔ gate declaration

### 4. baseline

- Profile schema/registry unit
- Chain mapper/LedgerFrame unit
- source별 translator/mapper parity 가능 범위
- PostgreSQL Ledger L1
- trace/coverage/structure read API
- 현재 실패와 skip을 그룹별 분류

baseline을 확보할 수 없으면 `신규 실패 0`을 주장하지 않고 `미검증`으로 표기한다.

## 산출물

1. `HARDCODING_INVENTORY.md`
2. `CURRENT_CALL_GRAPH.md`
3. `BASELINE_RESULTS.md`
4. `KEEP_MOVE_RETIRE_MATRIX.md`
5. `OPEN_DECISIONS.md` D1~D5의 조사 근거

## 수락 기준

- live source → cursor → mapper/translator → gate → store 호출점이 source kind별로 표시됨
- Position 의존 호출부와 stage-local Entity 치환 대상이 전수 기록됨
- 재작성 대상과 유지 Kernel에 겹치는 symbol이 없음
- 삭제·migration·DB write 0
- 설명되지 않은 dirty 변경 0

완료 후 멈추고 1단계 승인을 기다린다.

## 실행 결과

- [하드코딩 전수표](./HARDCODING_INVENTORY.md)
- [현행 호출 그래프](./CURRENT_CALL_GRAPH.md)
- [baseline](./BASELINE_RESULTS.md)
- [Keep/Move/Retire](./KEEP_MOVE_RETIRE_MATRIX.md)

런타임 코드·DB·운영 config 변경 없이 조사 문서만 작성했다. 2단계는 시작하지 않았다.
