# server/scripts 사용법

**작성 2026-08-19.** 여기 있는 것들이 무엇이고 언제 쓰는지. 지운 것도 옮긴 것도 없다.

## 돌리는 법

`server/`에서 돈다. 인터프리터는 **conda 환경 `assy_manager`** 하나뿐이다 — 맨 `python`으로
돌리면 임포트가 어긋난다.

```text
conda run -n assy_manager python scripts/<이름>.py
```

`.sql`은 스크립트가 아니라 **읽고 붙여 넣는 질의문**이다. 그대로 실행하지 말고 안에 적힌
전제를 먼저 읽을 것.

## 🔴 쓰기 여부부터 본다

이 목록에서 가장 중요한 칸이다. **읽기 전용**은 운영에 그대로 돌려도 되고, **드라이런**은
기본이 「무엇을 할지 말하기」이며 `--apply`를 붙여야 실제로 쓴다. **쓰기**는 처음부터 쓴다.

---

## 진단 — 느리다·안 뜬다·막혔다 (전부 읽기 전용)

| 스크립트 | 언제 |
|---|---|
| `diagnose_db_health.py` | DB가 이상하다 — 긴 트랜잭션·블로트·블로킹 |
| `diagnose_slow_after_ingest.py` | **대량 인제션 직후** 느려졌다 |
| `diagnose_wal_headroom.py` | WAL 여유가 얼마나 남았나 |
| `diagnose_socket.py` | 서버가 안 뜬다 / 소켓·기동 문제 |
| `probe_core_occupancy_alignment.py` | 코어 프레임 정렬이 맞나 (퍼지 점유 탐침) |

## 점검 — 선언과 실물이 맞나 (전부 읽기 전용)

| 스크립트 | 언제 |
|---|---|
| `check_schema_drift.py` | 코드가 요구하는 스키마와 실제 DB가 어긋났나 |
| `check_external_sources.py` | **외부 디렉터리 인제션**이 등록됐나, 거절이면 왜 |
| `check_source_ordering.py` | 백필 **전에** 소스 정렬이 실제 표와 맞나 |
| `check_missing_business_key.py` | 업무키가 빈 행 — 그리고 채울 수 있는지 |
| `list_undeclared_tables.py` | `table_config.json`이 더는 선언 안 하는 물리 표 |
| `audit_schema_canon.py` | `SCHEMA_CANON.md`의 여덟 규칙을 세어 본다 |
| `ledger_deploy_preflight.py` | v2 원장이 착지하면 **이 박스에** 무슨 일이 생기나 |
| `wf_spelling_census.sql` | WF·lot·slot 표기 흔들림 실측 (정규화 규칙 정하기 전) |
| `find_confirmations_with_origin_gap.sql` | 소스 맵과 기준 바닥이 원점을 **다르게** 선언한 확정 |

## 수리 — 데이터를 고친다

| 스크립트 | 쓰기 | 언제 |
|---|---|---|
| `replay_ingestion.py` | **드라이런** | 읽기 전용 소스의 **파일 하나**를 다시 먹인다. 파일은 안 건드리고 인제션 기록만 잊는다 |
| `dedupe_business_key_rows.py` | **드라이런** | 한 업무키에 여러 행 → 한 행으로 접는다 |
| `backfill_enrichment.py` | **보고 후 선택** | 소급 enrichment 백필 |
| `rebuild_blank_business_keys.py` | 쓴다 | 빈 컴포넌트가 든 업무키를 원본 컬럼에서 다시 조립 |
| `purge_outbox_backlog.py` | 쓴다 | `database_outbox` 백로그 수동 정리 |
| `backup_config.py` | 쓴다 | `server/config/` 스냅샷·목록·검사·복원 |

## 셋업 — 멱등, 다시 돌려도 된다

여기 다섯은 **처음 세울 때와 새 환경에서** 쓴다. 전부 「이미 있으면 안 만든다」.

| 스크립트 | 무엇 |
|---|---|
| `setup_db_performance.py` | 성능용 인덱스 + `ANALYZE` |
| `setup_transfer_plan_indexes.py` | Universal Transfer Plan(M2) 엔진용 인덱스 |
| `setup_bonding_plan_indexes.py` | 본딩 실험계획(M1) 집계 API용 인덱스 |
| `setup_ingestion_checkpoint.py` | 파일 인제션 체크포인트 표 |
| `install_product_tables.py` | 제품이 소유한 표 선언을 그 사이트의 `table_config.json`에 설치 |

## 원장·온톨로지

| 스크립트 | 언제 |
|---|---|
| `convert_ontology_to_single_file.py` | 옛 다섯 파일 루트를 `ledger_config.json` 하나로 접는다. **원본을 안 지우고** 새 파일을 쓴다 |
| `table_config_from_schema.py` | 스키마 시트(Table·Column·Type) → `table_config.json` **초안** |

## 합성 데이터 — 빈 박스에서 화면을 돌려 보려면

전부 **쓴다**. 이름이 `SYN-*`인 것만 만들고 실데이터는 안 건드리는 게 원칙이다.

| 스크립트 | 무엇을 세우나 |
|---|---|
| `seed_syn_world.py` | **여기서 시작.** 코어 웨이퍼·DT 이송·랏·공정 이력 |
| `seed_syn_process_ledger.py` | 공정 조건·레시피·두 번째 발견 종류 + **정답지** |
| `syn_world_prove.py` | 위 둘의 **정답지 검산** — 양방향, 축마다 |
| `seed_syn_journey_atoms.py` | 콘솔이 묻는 여정 축 세 개 |
| `seed_syn_k1_lot.py` | 본딩→DT 홉이 k=1인 랏 (세 축이 다 그려지게) |
| `seed_syn_lot_excursion.py` | 랏 단위 이탈 — 추세 격자가 찾으려는 그 이상치 |
| `seed_syn_valid_die_floors.py` | 모든 SYN 프레임에 유효다이 기준 (맵 마스크 경로 발화용) |
| `seed_syn_void_base_join.py` | 베이스 좌표 본딩 웨이퍼 + SAT 스캔 + 조인 |
| `seed_syn_core_defect_jobs.py` | 뭉친 CORE_DT 결함 맵을 DT 잡으로 쪼갬 |
| `seed_syn_dt_alignment_samples.py` | PRD 유효다이 맵에서 DT 정렬 표본 둘 |
| `seed_syn_composite_chip.py` | 복합 CHIP 이송 픽스처 |
| `seed_syn_complex_composite.py` | 복합 CHIP R&D 픽스처 (`SYN-CX-*`) |
| `seed_syn_split_merge_pressure.py` | 갈렸다 다시 합쳐지는 랏, 가지마다 다른 압력 |
| `generate_syn_lot_split_merge_sources.py` | 위 분기/병합 소스 파일 생성 (**스테이징 파일만**, DB·`raws` 안 건드림) |

## 실데이터에서 뽑는 시드

| 스크립트 | 무엇 |
|---|---|
| `seed_root_lot_valid_die_refs.py` | 현재 `lot_event` 루트 랏마다 유효다이 기준 하나 |
| `seed_dt_log_from_root_refs.py` | 위 기준으로 `dt_log` 행 생성 |
| `seed_valid_die_ref_floor.py` | `valid_die_ref`에 기준 바닥 (+ 메타 행) |
| `seed_dt_index_walk.py` | `dt_map`에 dt_index 워크 (인덱스 축 발화용) |
| `seed_void_sample_tree.py` | void 폴더 트리 실물 생성 → **진짜 파서로 되읽기** |

## 트레이스·enrichment CLI

| 스크립트 | 무엇 |
|---|---|
| `chain_replay_cli.py` | 체인 리플레이 — R1(규칙 재적용) · R2(낡은 소스 철회) |
| `enrichment_insights.py` | 갭 분류 → 규칙 제안 → 확정 |
| `generate_trace_fixture.py` | 트레이스 픽스처 생성 |
| `score_trace_fixture.py` | 기준 트레이서를 돌려 정답지 다섯 개에 채점 |
| `confirmed_origin_box_delta.py` | 유효다이 원점 상자가 확정 맵을 얼마나 움직이나 (읽기 전용) |

## 지난 일회성 — 남겨는 뒀다

끝난 작업이고 다시 돌릴 일이 없다. 지우지 않은 이유는 그때 무엇을 했는지가 여기 적혀 있어서다.

| 스크립트 | 언제 것 |
|---|---|
| `migrate_to_postgres.py` | SQLite → PostgreSQL 이관 (2026-04) |
| `migrate_assets.py` | 다른 서버의 옛 `config`·`ingestion_workspace` 이관 (2026-04) |
| `migrate_jsonb_to_rdb.py` | JSONB → RDB (2026-06) |
| `drop_legacy_tables_20260725.sql` | 레거시 표 정리 **준비본** — ⚠️ 실행 전 안의 전제·절차를 반드시 읽을 것 |

`archive/`에는 더 오래된 일회성 15개가 들어 있다.
