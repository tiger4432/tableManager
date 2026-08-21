# Ledger v2 1단계 Baseline

> 실행일: 2026-08-17 · env `assy_manager` · `main@3b640b8`
> 상태: `IN_REVIEW` / `NOT_APPROVED`

## 변경 경계

- 시작 HEAD와 `origin/main`은 모두 `3b640b8`이다.
- 시작 전 worktree는 이미 dirty였다. 문서 개편, 구 계획 폴더 삭제, v2 계획, 로컬
  설정/로그/임시물, 이전 Profile 3단계 파일이 포함돼 있었다.
- reset/checkout/stash/삭제를 하지 않았다.
- stage 1 변경은 조사 문서, 상태/SSOT 링크, 새 history뿐이다.
- 런타임 Python, DB migration, 운영 config, DB data는 변경하지 않았다.

## 핵심 Ledger

실행 범위는 Profile, Chain mapper/LedgerFrame, Source contract, L1 unit, trace contract/read,
composition 7개 파일이다.

```text
247 passed, 7 warnings in 1.94s
```

warnings는 Pydantic/FastAPI deprecation과 `.pytest_cache` 권한이다.

## PostgreSQL Ledger

격리 DB 환경변수 없이 PostgreSQL 전용 Ledger 7개 파일을 실행했다.

```text
8 passed, 131 skipped, 7 warnings in 0.86s
```

- 129 skip: `ASSY_PG_TEST_DATABASE_URL` 미설정. 운영 DB 오접속 방지용 safety gate.
- 2 skip: `ASSY_LEDGER_COST_PROBE=1`이 필요한 대용량 cost probe.
- PostgreSQL write/E2E를 통과했다고 표현할 수 없다.

## 전체 server baseline

```text
3923 passed, 142 failed, 203 skipped, 1 xfailed, 23 errors,
98 warnings in 869.93s (14:29)
```

23 errors는 모두 `test_void_base_join_fixture.py` setup의 `KeyError: 'void_obs'`다. 현재
`table_config.json`에 그 table이 없다.

| failure 그룹 | 근거 | stage 1 관련성 |
|---|---|---|
| 현재 config와 구 fixture 불일치 | API/ingestion/config resolve/DT/void schema | 기존 dirty/config 상태 |
| map alignment/synthetic fixture | 정렬·복합 샘플 기대값 | Ledger v2 무관 |
| 구 온톨로지 기대 | `WaferLeg` 요구 5개 | 사용자가 폐기한 개념의 구 테스트 |
| live Ledger source 누락 | `void_obs`, `dt_log` 요구 2개 | 현재 최소 live config |

전체 실패의 clean baseline은 이 worktree에서 확보할 수 없다. 전체 repo “회귀 없음”은
주장하지 않는다.

## Ledger 관련 기존 7 failures

```text
102 passed, 7 failed, 8 warnings in 0.98s
```

| test | 원인 |
|---|---|
| `test_waferleg_rolls_up_into_wafer` | 현 Vocabulary에는 없지만 구 테스트가 WaferLeg rollup 요구 |
| `test_chained_rollups_are_refused_rather_than_silently_truncated` | 폐기된 rollup 전제 |
| `test_the_two_grain_arms_each_pin_their_own_subject_type` | SQL의 `subject_type='WaferLeg'` 요구 |
| `test_the_rollup_helper_has_one_spelling_for_every_reader` | trace helper의 WaferLeg rollup 요구 |
| `test_catalog_is_generated_for_every_registered_entity_type` | catalog 기대 집합에 WaferLeg 잔존 |
| `test_the_lineage_declaration_still_validates_unchanged` | live `void_obs` 부재로 기본 `lineage` 관측 |
| `test_the_live_declaration_validates_and_declares_this_source` | live `dt_log` source 부재 |

stage 1 문서 변경의 신규 실패가 아니다. 새 Bundle fixture에서 기대 계약을 다시 세운다.

## 전체 skip 분류

원래 203 skip 중 202개는 해당 파일 묶음을 `-rs`로 재실행해 이유를 확인했다.

| 사유 | 수 | 판정 |
|---|---:|---|
| 격리 PG URL 없음: Ledger PG | 129 | 환경 의존 safety gate |
| 격리 PG URL 없음: readonly guard | 23 | 환경 의존 safety gate |
| 격리 PG URL 없음: multirow upsert | 36 | 환경 의존 safety gate |
| Ledger cost probe opt-in 없음 | 2 | 의도된 marker |
| live virtual join config 없음 | 1 | 현재 config 상태 |
| retired map-alignment cases | 3 | 명시적 retired marker |
| contract PostgreSQL axes | 5 | `ASSY_CONTRACT_PG_URL` 필요 |
| map2 artifact/oracle/client 축 | 3 | 명시적 UNSCORED marker |
| 원 전체 로그에 reason 미보존 | 1 | 원인 미확정, 녹색 간주 안 함 |

선택 dependency 또는 플랫폼 조건으로 확정된 skip은 이 호스트에서 0건이다.

보조 실행은 skip 가능 21파일 `556 passed, 58 failed, 158 skipped`, PG multirow
`36 skipped`, contract shim `188 passed, 2 failed, 8 skipped`였다.

## 신규 실패 판정

- stage 1 핵심 Ledger 247개 기준 신규 실패: **0**
- 전체 suite 신규 실패: clean baseline 부재로 **미검증**
- PostgreSQL E2E: 격리 URL 제공 전까지 **미검증**
