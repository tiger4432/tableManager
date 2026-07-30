# Enrichment ①②④ + Chain Replay R1·R2 — 판단을 없애고, 되돌릴 길을 만들다

> **일자:** 2026-07-30 | **담당:** Server PM | **검수 등급:** T2
> **관련:** [ENRICHMENT_QUEUE_SPEC §5.2~§5.4](../spec/ENRICHMENT_QUEUE_SPEC.md) · [chain_ingestion_guide §4.4·§5](../guide/chain_ingestion_guide.md) · [data_model §2.2-bis](../architecture/data_model.md) · [config/enrichment_rules §7](../guide/config/enrichment_rules.md)

## 현상 / 배경

보드 2026-07-29 분석이 Enrichment 강화 3안과 Chain Replay를 같은 방향으로 지목했다.

- **①** 참조뷰 결과가 유일값 하나일 때, 사람은 판단이 아니라 **확인**을 하고 있었다. V1 상호작용 계기(2026-07-29 착지)로 `키n + 마우스3`.
- **②** 같은 패턴을 N번 풀었으면 그건 규칙이다. ①③이 건당 공수를 낮추는 반면 **②만 큐 자체를 줄인다.**
- **④** 큐가 **"소스에 원래 없다"(진짜 일감)** 와 **"소스엔 있는데 매핑이 떨궜다"(버그)** 를 섞어 사람에게 청구하고 있었다.
- **R1/R2** 룰을 바꿔도 과거 데이터는 옛 룰이 남긴 상태였고(R1), 옛 룰이 쓴 **틀린 값을 되돌릴 경로가 없었다**(R2). ②를 자동 적용할 수 없었던 이유가 정확히 R2의 부재였다.

## 근본 원인 / 설계 판단

**① 왜 "선언"인가.** 후보 컬럼을 컬럼명으로 유추하면 안 된다는 근거가 사용자 실 config에 있었다: `core_wafer_attribution`의 뷰 #0(lot+slot 조회 → 후보 1개)과 뷰 #1(lot만 조회 → 후보 N개)이 **둘 다 `wafer_id` 컬럼을 가진다.** 맵 오버레이 `derive_table_binding`이 첫 데이터 컬럼을 추측해 DECOY를 붙인 사건의 행(row) 버전이다. → `reference_views[].candidate_for = {target: 뷰_컬럼}` **선언만** 인정, 선언 없는 뷰는 표시 전용.

**① 왜 기본 OFF인가 (M3와 유일하게 다른 점).** 형태는 M3 `auto_register_map_meta`와 같다 — 부재 시에만, 최하위 우선순위, 작업 단위 경계 노브, 비-boolean 경고 1회. 기본값만 다르고 근거는 둘이다: ⓐ 이 필드의 blank가 **큐 소속을 정의**하므로(`queue_filters`) 오확정은 항목을 워크리스트에서 빼 재검토를 막는다 ⓑ 철회가 부분적이다(R2로 레이어는 되돌리지만 그 셀은 provenance가 남아 재확정되지 않는다).

**② 왜 선행부가 `decision_key`의 진부분집합인가.** 임의 선택이 아니라 기존 계약의 결과다. 승격물은 참조뷰로 표현되고 `_validate_view_sql`이 바인드를 decision_key 컬럼으로 제한한다 → 실행 가능한 형태는 "판단키의 일부가 target을 결정한다"뿐이다. 그리고 승격물이 **참조뷰 + `candidate_for`** 이므로 **①이 그것을 실행한다** — 새 맵퍼도 새 실행기도 없고, 선행부가 나중에 두 값에 대응하면 ①이 `ambiguous`로 **거절**해 화석화 대신 사람의 판단으로 되돌아간다.

**R1이 빈 값을 쓰지 않는 이유 = R2가 필요한 이유.** "이 셀에 룰이 더는 값을 만들지 않는다"는 **빈 값과 다른 진술**이고, 그 진술을 할 수 있는 것은 레이어 철회뿐이다. 그래서 R1은 그런 셀을 **철회 후보로 보고만** 한다.

## 해결

### 신규 모듈

| 파일 | 역할 |
|---|---|
| `server/enrichment_candidates.py` | ① 술어(`resolve_target_candidate`) + 노브 + `AutoConfirmCollector`(체인 경로, 부재 시에만·배치·상한) |
| `server/enrichment_analysis.py` | ② `analyze_promotions` · ④ `classify_queue` · ① 소급 `run_auto_confirm_sweep`(dry-run이 곧 계기) |
| `server/chain_replay.py` | R1 `replay_rule`/`replay_all`/`order_rules` · R2 `withdraw_source` |
| `server/keyset_scan.py` | **공용** 키셋 페이지 순회 — `backfill_enrichment`·`enrichment_analysis`·R1이 공유 |
| `server/scripts/enrichment_insights.py` | `classify` / `propose` / `confirm` CLI (dry-run 기본) |
| `server/scripts/chain_replay_cli.py` | `list` / `replay` / `replay-all` / `withdraw` CLI (dry-run 기본) |

### 기존 파일 변경

- `server/enrichment_config.py` — `candidate_for` 정규화(비-target 키·비문자열 **거절**), `required_binds`, 규칙별 `auto_confirm` 통과, **참조뷰 실행의 정본** `execute_reference_view`(+`REFERENCE_LIMIT_WRAP_SQL`·`ReferenceViewError`).
- `server/chain_ingestion_worker.py` — M3 훅 **직후**에 ① 자동 확정 훅(격리: 실패해도 체인 적재 정상 완료).
- `server/scripts/backfill_enrichment.py` — 손으로 쓴 키셋 루프 2곳을 `keyset_scan.iter_pages`로 수렴.

### R2 — 레이어 철회의 핵심

```python
survivors = {s: d for s, d in (remaining.get(cell) or {}).items() if s != source_name}
new_val, top_src = crud.compute_priority_value(survivors, pins.get(cell), table_name)
```

`cell_sources` 행 **하나**만 지우고 남은 소스로 표시값을 재계산한다 → **아래 레이어가 드러나고 구멍이 남지 않는다**(H2-b의 셀 버전). 행 삭제·컬럼 NULL은 다른 소스의 기여까지 파괴하므로 하지 않는다.

**사람 값을 지울 경로가 없음을 보장하는 두 거절**: `user` 소스 철회는 **거부**, 사람이 핀한 셀(`manual_priority_source`)은 **건너뛰고 이유를 남긴다**.

**무음 금지**: 표시값이 바뀐 셀마다 `AuditLog`에 소스 `chain_replay_withdraw` · `updated_by="withdraw:<소스명>"` · old/new. 클라의 **기존** 셀 이력 타임라인이 이를 읽는다(신규 이벤트·신규 화면 0).

### R1 — 세 겹의 루프 가드

현 `chain_rules.json`에 `inventory_master → inventory_master`(트리거 = 타깃)가 실재하므로 가드는 선택이 아니다.

| 겹 | 무엇 |
|---|---|
| ① | **시작 시점 스냅샷 경계** — `keyset_scan.iter_pages(max_row_id=...)`로 자기 산출물을 다시 만나지 않는다 |
| ② | **룰당 정확히 1회** — `replay_all`은 캐스케이드 재발화 없음 |
| ③ | **라이브 워커의 기존 필터 재사용** — 재적용 쓰기는 `source_name="chain_ingestion"`이고 워커가 이미 그 이벤트를 버린다 |

재적용 **순서**는 계약이다(생산자 → 소비자). 자기 간선은 순서에서 제외하고 ①로 다루며, **서로 다른 테이블 사이의 순환은 경로를 이름으로 밝히며 거부**한다.

## 검증

**`pytest server/tests/` — 1361 passed** (기준선 1361 = 착수 시 1301 + 신규 60). 전부 `conda run -n assy_manager`.

신규 테스트 60건: `test_enrichment_candidates.py`(23) · `test_enrichment_analysis.py`(16) · `test_chain_replay.py`(21).

**결함 주입으로 각 기제가 실제로 red가 되는지 확인** (교훈 파일: "새 코드 경로를 한 번도 실행하지 않는 검증으로 해소를 선언" 금지):

| 주입 | 기대 | 결과 |
|---|---|---|
| DECOY 뷰(lot만 조회)를 후보로 **선언** | `ambiguous` 거절 | PASS — 선언이 load-bearing임이 증명됨 |
| 선언된 뷰 하나를 실행 불가로 | **살아남은 뷰가 값 1개를 내도 거절** | PASS (`view_error`) |
| 자기 트리거 감지를 끔 | 스캔이 자기 산출물을 먹는다 | PASS (`rows_scanned > 3`) |
| 같은 선행부 → 서로 다른 target 값 | ②가 제안하지 않고 이유 보고 | PASS |
| 사람이 자동 확정값을 비움 | 재확정 안 함 | PASS (`cell_has_provenance`) |
| 사람이 그 소스를 핀 | R2가 건너뜀 | PASS (`pinned_skipped`) |

**라이브 읽기 전용 측정(서빙 DB, 쓰기 0)** — ④ 분류 실측:

`core_wafer_attribution` 큐 **69건**. 선언 없는 현 config에서는 전부 `not_declared`. 명백한 선언(판단키 전체로 조회하는 뷰 2개)을 **스크래치 사본에** 넣어 재측정:

| 분류 | 건수 |
|---|---|
| `resolvable_from_reference` (①이 처리) | **68** |
| `ambiguous_reference` (진짜 사람의 판단) | **1** |
| `mapping_gap_same_name` (**파이프라인 버그**) | **0** |
| `no_source_rows` · `no_evidence` · `unprobed` | 0 |

① sweep dry-run: **67건 자동 확정 가능**(69 중), 거절 `cell_has_provenance` 1 + `ambiguous` 1. ② 제안: 사람이 채운 11셀에서 `core_lot`·`core_slot` 두 선행부 **모두 충돌로 거절**(둘 다 `wafer_id`를 결정하지 못함 — 이 데이터에선 올바른 답).

**부수 발견 — 보드의 미결 위험 ⓐ("표기가 섞여 있는지 측정할 것")에 대한 실측 답:**

| 테이블 | `wafer_id` 표기 | 행수 |
|---|---|---|
| `wafer_slot_history` | `WF-C-21` (단축형) | 7 |
| `wafer_process` | `WF-LOT-C-21` (전체형) | 10,372 |
| `core_wafer_map`(사람이 채운 것) | 전체형 8 · 단축형 1 · 기타 2 | 11 |

**같은 (lot, slot)에 두 표기가 공존한다.** `ambiguous_reference` 1건이 정확히 이 케이스였다(`WF-C-21` vs `WF-LOT-C-21`) — ①이 거절한 것이 옳다. 표기 통일 없이 ①을 켜면 자동 확정이 **데이터가 있는 쪽 표기로 조용히 표준화**한다.

## 남은 것 / 승인 대기

- **① 1클릭 확정(클라 절반) 미착지** — `GET /enrichment/rules` **가산 필드** + "후보 1개인가" 엔드포인트가 필요하고 둘 다 `server/main.py`(동시 라운드 점유) + **경계 계약**. 술어는 서버에 완성돼 있어 클라 재구현은 불필요.
- **② 자동 적용 가부** — R2 착지로 철회 경로가 생겼으나 셀 레벨 재확정 억제(`cell_has_provenance`)가 남아 완전 가역은 아니다. 판단은 총괄.
- `main.py`의 참조뷰 LIMIT 래핑 인라인 사본 → `execute_reference_view` 호출로 통합(파일 점유 해제 후). 그때까지 이음새 가드 테스트가 드리프트를 감시.
- `graph_materializer.resync_table`의 키셋 순회는 그래프 작업에 용접돼 있고 파일이 타 라운드 소유라 이번에 통합하지 못했다(`keyset_scan`으로 수렴 대상).
