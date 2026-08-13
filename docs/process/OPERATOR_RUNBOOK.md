# 🏭 운영에서 돌릴 것 — 기록 시간 · 목적 · 방법

> **이 파일의 규칙**
>
> - 총괄이 쓰고, **대표님이 운영에서 직접 돌린다.** 에이전트는 운영 DB에 닿지 않는다.
> - 항목은 **끝나면 지우지 않고 「✅ 완료 (날짜)」로 표시**한다 — 안 돈 것과 돈 것을 구별할 수 있어야 한다.
> - 🔴 **이 박스의 실측은 운영의 증거가 아니다.** 여기서 「0행」이어도 운영은 아닐 수 있다. 그래서 아래 마이그레이션들은 **스스로 거절**하도록 만들었다.
> - ⚠️ **`.sql` 파일은 잘못된 «서버»를 거절하지 못한다.** 내용만 지킨다. 돌리기 전에 반드시:
>   ```sql
>   SELECT current_database(), current_user, inet_server_addr();
>   ```
> - 순서가 걸린 항목은 **「선행」**에 적었다. 선행을 건너뛰면 조용히 틀린다.

---

## 1. 🔴 정렬기 작업목록이 500을 내면 이것부터

| | |
|---|---|
| **기록** | 2026-08-06 (미완, 오늘 재확인) |
| **목적** | `frame_confirmation`에 `reference_cell_count`·`thresholds_defaulted` 두 컬럼을 붙인다. **모델엔 있고 표엔 없으면 정렬기 작업목록 라우트가 HTTP 500으로 죽는다.** 이 박스에서 실제로 그렇게 죽었고 마이그레이션 실행으로 살아났다 |
| **방법** | `conda run -n assy_manager python server/migrations/add_frame_confirmation.py` |
| **성질** | 멱등 — 2회 실행해도 바이트 동일, 행 수 불변 |
| **⚠️** | **큰 기존 테이블에 컬럼을 붙이는 것**이라 잠금 시간을 본다. 스크립트 자신이 그 위험을 문서화해 두었다 |
| **확인** | 작업목록 라우트가 500이 아니라 **422**(파라미터 누락)로 답하면 성공 — 검증 단계까지 도달했다는 뜻 |

---

## 2. 🔴 `dt_inventory`의 lot/slot이 수치형이라 값을 잃는다

| | |
|---|---|
| **기록** | 2026-08-13 |
| **목적** | `dt_inventory.dt_lot` / `dt_slot`을 `double precision` → `character varying`. SCHEMA_CANON R1 — **식별자는 절대 수치형이 아니다.** 이 시스템의 lot은 `DT-2601-001` 같은 «문자열」이고 슬롯은 `01`처럼 선행 0을 갖는다. 수치형은 **문자열 lot을 아예 못 받고, 슬롯 `01`을 `1`로 조용히 바꾼다** |
| **방법** | `psql "<운영URL>" -f server/migrations/alter_dt_inventory_lot_slot_to_text.sql` |
| **선행** | 없음. 단, **돌리기 전에 소수점 값 사전 점검**을 하라 — 쿼리는 파일 주석 안에 있다 |
| **되돌리기** | `alter_dt_inventory_lot_slot_to_text_reverse.sql`. 🔴 **되돌리기는 수치로 변환 불가능한 값이 하나라도 있으면 거절한다** — 버리는 사본에서 실제로 터뜨려 확인했다 |
| **⚠️ 왜 config로는 안 되나** | `models.sync_dynamic_tables_schema`는 컬럼을 **ADD만** 한다. **타입은 절대 안 건드린다.** 그래서 `table_config.json`의 `"number"→"string"` 수정은 **선언만 바꾸고 물리 컬럼은 그대로 둔다** — 언제나 «반쪽» 수리다 |

---

## 3. 파일을 안 지우고 장부로만 대조하려면 — 인제션 원장

| | |
|---|---|
| **기록** | 2026-08-13 |
| **목적** | `file_ingestion_checkpoints`에 `file_mtime`·`file_size`와 `idx_fic_path_stat`를 붙인다. 처리한 파일을 **원래 자리에 그대로 두고** 장부와 대조해 재처리를 막는 모드의 토대 |
| **방법** | `psql "<운영URL>" -f server/migrations/add_ingestion_ledger_path_stat.sql` |
| **선행** | 없음 |
| **🔴 순서 위험** | **`archive_processed_files: false`를 채택하기 «전에» 이걸 먼저 돌려야 한다.** 컬럼이 없으면 티어1 조회가 매번 예외를 내고 **availability-first 예외 처리에 먹혀서 조용히 무력화된다** — 로그에 경고만 남고 기능은 「없는 것처럼」 돈다. 이 박스에서 한 레인이 실제로 그 상태로 벤치마크를 돌려 그럴듯한 숫자를 냈다 |
| **되돌리기** | `add_ingestion_ledger_path_stat_reverse.sql` |
| **효과** | 이게 있어야 `831ab68`의 스윕 티어1이 산다 — 재시작 후 재스윕이 **26.4초 → 0.60초**(이 박스 2,001파일 실측) |

---

## 4. void(보이드) 스키마 켜기 — 5단계, 순서가 있다

| | |
|---|---|
| **기록** | 2026-08-13 |
| **목적** | SAT 보이드 관측을 받는다. 테이블 둘 — `inspection_run`(**분모**: 스캔이 있었다)과 `void_obs`(관측). 분모가 없으면 「보이드 0」과 「스캔 안 함」이 **같은 부재**고 둘 다 깨끗하게 읽힌다 |

**방법 — 이 순서대로:**

1. `server/config/table_config.json.sample`의 **`void_obs`·`inspection_run` 두 선언**을 `server/config/table_config.json`으로 **손복사**.
   🔴 **config는 gitignore라 `git pull`이 안 실어온다** — 이건 설계다(배포가 운영자 설정을 덮어쓰지 못하게).
2. 재기동 또는 `POST /admin/reload-configs` → **물리 테이블 생성 + 워크스페이스 자동 프로비저닝**(`scripts/` 포함).
3. `psql "<운영URL>" -f server/migrations/add_void_schema_indexes.sql` — **반드시 2번 «다음»**(테이블이 있어야 인덱스가 붙는다).
4. `server/parsers/void_obs_parser.py.sample` → `ingestion_workspace/void_obs/scripts/void_obs_parser.py`,
   `server/parsers/inspection_run_parser.py.sample` → `ingestion_workspace/inspection_run/scripts/inspection_run_parser.py`.
   재기동 불필요 — 폴더는 파일 이벤트마다 다시 읽힌다.
5. **SAT 파일을 두 `raws/` 양쪽에 넣는다.** 파일 하나가 사실 둘을 말하는데 워처는 테이블당 핸들러 1개다.
   🔴 **체인으로 대신할 수 없다** — 깨끗한 스캔은 파생할 행이 0개다.

| | |
|---|---|
| **되돌리기** | `add_void_schema_indexes_reverse.sql` |
| **⚠️ 아직 검증 안 된 것** | **진짜 SAT 파일을 한 번도 못 봤다.** 헤더 철자는 대소문자·구분자 접힘 별칭이라 `base wafer id`/`BASE_WAFER_ID`/`base-wafer-id`가 다 먹지만, **런 메타 헤더 블록(`# key: value`)은 지어낸 것**이다 — 여덟 컬럼에 시각·레시피·설비가 없어서. 실제 파일이 다르면 수정은 `_ALIASES`/`_RUN_ALIASES`에 한정된다 |
| **⚠️ 단위** | 단위 없는 파일은 **추측하지 않고 거절**한다(`DEFAULT_UNIT`이 `None`) |

---

## 5. 폐기 테이블 삭제 — `map_doe` / `map_doe_source`

| | |
|---|---|
| **기록** | 2026-08-13 |
| **목적** | 2026-07-27에 폐기(M2.6)된 두 테이블의 물리 삭제. 자재는 `map_split_registry.bands[].materials`로 옮겨 갔고 **코드는 더 이상 읽지 않는다.** 코드 주석이 「DROP은 운영자 승인 필요」라고 적고 기다리고 있었다 |
| **방법** | `psql "<운영URL>" -f server/migrations/drop_map_doe_tables.sql` |
| **성질** | 🔴 **비어 있지 않으면 거절한다.** 이 박스는 양쪽 0행이지만 **운영은 아닐 수 있어서** 그렇게 만들었다. 거절 메시지에 행 수가 들어 있다. 이미 없으면 `ABSENT (nothing to drop)`로 조용히 통과(멱등) |
| **되돌리기** | `drop_map_doe_tables_reverse.sql` — 컬럼 집합을 **선언이 아니라 라이브 DB의 `information_schema`에서** 떠서 만들었다(물리 테이블엔 선언에 없는 일반 컬럼 7개가 있고 `band_seq`/`qty_total`/`qty`가 정수가 아니라 `double precision`이다) |
| **참고** | 이 박스에선 **본체 0행인데 딸린 행이 남아 있었다** — `cell_sources` 210 · `cell_overwrites` 210 · `audit_logs` 517. 마이그레이션은 **세어서 보고만 하고 지우지 않는다**(이력은 대상보다 오래 남아야 하고, 사용자가 고정한 셀 삭제는 별개 승인) |
| **완료** | 개발 두 DB(`assy_qa`·`assy_manager`)는 2026-08-13 실행 완료 |

---

## 6. 원장(ledger) 테이블 — 온톨로지 1순위의 토대

| | |
|---|---|
| **기록** | 2026-08-13 |
| **목적** | `ledger_events`(월 단위 파티션)와 커서 테이블 생성 |
| **방법** | `conda run -n assy_manager python server/migrations/add_ledger_events.py`<br>실행 없이 상태만 보려면 `--report` |
| **성질** | **추가 전용·멱등.** DROP 없음, 기존 것의 ALTER 없음, 기존 테이블의 행을 건드리는 문장 없음. **새 테이블 둘만 만든다** |
| **급하지 않은 이유** | 안 돌아도 **아무것도 안 깨진다** — 부팅 시 `server/ledger`를 import하는 프로세스가 없다. 2번과 달리 큰 기존 테이블에 컬럼을 붙이지 않아 **잠금 위험도 없다** |
| **⏸ 대기** | 시간대 수정 착지 후에 돌리는 것을 권합니다 — 아래 8번 참조 |

---

## 7. ⏳ 파일 없음 — 만들어야 하는 것

| | |
|---|---|
| **기록** | 2026-08-13 |
| **목적** | `wafer_map_metadata.business_key_val`에 **UNIQUE 인덱스**(SCHEMA_CANON **R2** — 「`business_key`를 선언했으면 UNIQUE 인덱스가 있어야 한다」) |
| **⚠️ 정정** | 이 항목은 처음에 **R6**이라 적었다. R6은 「표식은 열쇠가 아니다」로 다른 규칙이다. 그리고 인덱스 대상도 원시 컬럼 쌍이 아니라 **`business_key_val`**이다 — 이 프로젝트의 기존 패턴(`uq_bk_<table>`)이고, `composite_key_source = [target_table, map_id]`이므로 **같은 제약이다.** 총괄 실측 2026-08-13 |
| **왜** | 🔴 **선언과 물리가 어긋난 R2 위반이다.** `product_tables.py`가 `business_key: "map_pk"`, `composite_key_source: [target_table, map_id]`를 **선언**해 놓았는데, 물리 UNIQUE는 `wafer_map_metadata_pkey`(= `row_id`) **하나뿐**이다. 그래서 `map_overlay._meta_select`의 `.first()`(`LIMIT 1`)가 중복 한 쌍을 만나면 같은 맵이 새로고침마다 **다른 «기하»**를 읽는다 |
| **지금 상태** | `c36368c`가 읽기에 총순서를 박아 **리더는 결정적**으로 만들었다. 🔴 **그런데 그 대가로 이제 중복을 «조용히 가린다»** — 예전엔 값이 흔들려서 티가 났다 |
| **방법** | **아직 마이그레이션 파일이 없다.** 만들기 전에 운영에 중복이 있는지부터 세야 한다: <br>`SELECT business_key_val, count(*) FROM wafer_map_metadata WHERE business_key_val IS NOT NULL GROUP BY 1 HAVING count(*) > 1;` <br>0이면 `CREATE UNIQUE INDEX uq_bk_wafer_map_metadata ON wafer_map_metadata (business_key_val);`를 붙이면 되고, 0이 아니면 **어느 행을 남길지가 먼저 판정할 문제**다 |

---

## 8. ✅ 완료 — 원장 시각대 (2026-08-13, `bee1aeb`)

| | |
|---|---|
| **기록** | 2026-08-13 |
| **판정** | **현지시간 `Asia/Seoul`**, 형식은 가운데 `T`가 낀 ISO 8601(`2026-08-13T13:45:00`) — 제품 소유자 |
| **상태** | ✅ **착지 `bee1aeb`.** 6번(원장 테이블)을 이제 운영에 돌려도 된다 — 이 항목이 걸어 둔 대기가 풀렸다 |
| **위험** | 틀리면 **모든 원자가 9시간 어긋나고 아무것도 항의하지 않는다.** 그래서 못 읽는 시각은 추측 대신 거절하고, 오프셋을 달고 온 문자열엔 선언 시간대를 다시 먹이지 않는다 |
| **🔴 배포 의존성이 «생겼다»** | `Asia/Seoul`은 IANA tzdata를 런타임에 찾는다 — `UTC`는 안 찾았다. **`environment.yml`에 `tzdata`를 넣었으니 운영 환경도 재생성해야 한다.** 없으면 조용히 UTC로 떨어지지 않고 **예외를 낸다**(일부러 그렇게 뒀다 — 조용한 폴백은 방금 고친 결함을 그대로 재현한다) |

---

## 9. 📋 실행이 아니라 «질문» — 운영에서 한 줄 떠 주실 것

| 목적 | 쿼리 |
|---|---|
| 원장 주 1의 전제 확인 — 운영 `lot_event`에 진짜 SPLIT/MERGE가 있나. **이 박스 픽스처로는 답이 안 나온다** | `SELECT event_type, count(*) FROM lot_event GROUP BY 1;` |
| 7번의 선행 — `wafer_map_metadata`에 중복이 있나 | `SELECT target_table, map_id, count(*) FROM wafer_map_metadata GROUP BY 1,2 HAVING count(*) > 1;` |

---

## 부록 — 이 박스에서만 하면 되는 것 (운영 아님)

- **`:8081` 격리 스택 재기동** — 셀 이력 기능이 착지하기 «전»에 뜬 프로세스라 그 기능이 안 보인다.
