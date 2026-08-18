# 🏭 운영에서 돌릴 것 — 기록 시간 · 목적 · 방법

> **Status:** 🟢 Living | **Last-verified:** 2026-08-18 | **Owner:** Lead / PM

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

1. `server/config/sample/table_config.json.sample`의 **`void_obs`·`inspection_run` 두 선언**을 `server/config/table_config.json`으로 **손복사**.
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
| **방법 — 마이그레이션(이 문서가 소유)** | ① `conda run -n assy_manager python server/migrations/add_ledger_events.py`<br>② `conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py`<br>실행 없이 상태만 보려면 각각 `--report` |
| **방법 — 번역(백필)** | 🔴 **명령은 여기 다시 적지 않습니다.** 정본은 [LEDGER_GUIDE §4.1~§4.3](../guide/LEDGER_GUIDE.md)이고, 새 소스를 «선언»하는 절차는 [ONTOLOGY_LEDGER_SETUP §10·§13](../guide/ONTOLOGY_LEDGER_SETUP.md)입니다. 운영자가 알아야 할 것 한 줄: **백필 명령은 하나**이고(`python -m ledger.backfill --source <소스>`, **`server/`에서**), `--source`는 **이름만** 고릅니다 — 🔴 **[2026-08-18] 드라이버도 하나뿐이라** 운영자가 고를 것이 없습니다 |
| **🔴 이 문서는 소스 «문법»의 개수를 적지 않습니다** | 이 자리엔 오래 「셋」이라 적혀 있었고 틀렸습니다 — 같은 문장이 `LEDGER_GUIDE`·`CONFIG_GUIDE`·`README`에도 복사돼 **넷이 함께 틀렸습니다.** 그래서 개수 대신 **정본과 세는 법**만 둡니다: 레거시 경로의 문법 목록은 `server/ledger/config.py`의 `SOURCE_KINDS`이고, 다시 세는 한 줄은<br>`conda run -n assy_manager python -c "import sys; sys.path.insert(0,'server'); from ledger import config; print(sorted(config.SOURCE_KINDS))"`<br>⚠️ **Ledger v2 선언에는 `kind`가 «아예 없습니다»** — v2 소스는 `driver`·`preparer_id`·`mapper_id`·`profile_id`로 조립되므로 **v2에서는 「문법 개수」라는 것이 세어지지 않습니다.** 🔴 **[2026-08-18] 백필이 타는 경로에 `kind`는 이제 관여하지 않습니다** — `SOURCE_KINDS`가 남아 있는 곳은 레거시 선언을 읽는 어드민 dry-run 쪽이고, 백필 드라이버는 하나입니다 |
| **🔴 이 박스의 셋업 상태는 이 한 줄이 답합니다** | (`server/`에서) `conda run -n assy_manager python -m ledger.setup` → `config_root`·`setup_version`·`readiness`·선언된 `sources`를 JSON 한 줄로 답합니다. **쓰기 없는 dry-run입니다.**<br>🔴 **[2026-08-18] 실행 경로가 «하나»가 됐습니다.** 문법별 드라이버 넷과 그것을 고르던 `mode`/`parity_status` selector(`dataflows/chains.json`)가 함께 은퇴했습니다. 종전 여기 있던 「어느 세계인가」 판별 두 줄은 그와 함께 사라졌습니다 — **가를 세계가 하나뿐입니다.**<br>🔴 **선언이 곧 활성화입니다** — `sources`에 있으면 돕니다. 따로 켜는 스위치는 없습니다 |
| **결함 관측(`void_obs`·`delam_obs`) 백필 (2026-08-14 3차 · `0a86651`)** | 판정 R-2026-08-14-D. 마이그레이션은 **추가로 없습니다** — 표도 컬럼도 안 늘고 **행만** 늘어납니다. 서로 독립이라 **순서는 상관없고** 위 ①·② 뒤이기만 하면 됩니다. 🔴 **선행 조건은 4번 항목**입니다 — `inspection_run`·`void_obs`·`delam_obs`가 있어야 하고, **분모(`inspection_run`)가 없으면 발견이 전부 거절**됩니다(원자 0). 개발 박스 실측: **91,756 + 10,421 = 102,177 원자, 거절 0 · 불완전 0**(20.8 s / 2.9 s). 되돌리기는 [LEDGER_GUIDE §4.7](../guide/LEDGER_GUIDE.md)의 술어 둘 |
| **🔴 돌리기 전에 그 소스가 «선언»돼 있는지 보십시오** | 선언 없는 소스는 백필이 `REFUSE_UNDECLARED_SOURCE`로 **거절**합니다(원자 0 · 커서 미이동 — 조용히 0건 성공하는 것이 아니라 거절입니다). 🔴 **어느 소스가 선언돼 있는지는 이 문서가 «세지 않습니다»** — `server/config/ontology/ledger_config.json`의 `sources` 키가 정본입니다. 🔴 **[2026-08-18] 그 root는 파일 «하나»입니다** — `manifest.json`과 `catalog/`·`dataflows/`는 은퇴했고, 옮겨진 원본은 `server/config/_ontology_pre_single_file_20260818/`에 있으나 **로드되지 않습니다**. **돌리기 전에 그 환경의 `sources`를 직접 여십시오**(또는 위 dry-run 한 줄) — 여기 숫자를 적어 두면 그 숫자가 낡습니다 |
| **⚠️ 이 박스의 소스는 «합성»입니다** | `void_obs`·`delam_obs`가 생성기 산물이라 번역된 원자 payload에 **`"synthetic": true`**가 붙습니다(선언의 `synthetic` 한 줄). 🔴 **운영에 실물 피드가 들어오는 날 그 줄을 «지우고» 백필해야 합니다** — 안 지우면 진짜 관측이 합성으로 표시된 채 영구히 남습니다(원장은 UPDATE가 없어 정정이 재번역입니다) |
| **🔴 스크립트가 «둘»이다 (2026-08-13 추가 · `0198e7e`)** | ②는 커서 표에 **`refusal_reasons`** 컬럼 하나를 붙인다(열둘 → 열셋). 거절 «사유»가 그전까지 백필 프로세스의 **메모리에만** 있어서 **DB를 어떻게 읽어도 사유 하나를 낼 수 없었다.** `ADD COLUMN <nullable, DEFAULT 없음>` 한 문장이라 PG 11+에서 **카탈로그만** 바꾸고 표 크기와 무관하며, 게이트가 `pg_attribute`라 **재실행은 DDL도 잠금도 0**이다. 되돌리기는 `--reverse`(내역만 잃고 원자·커서·집계는 안 잃는다) |
| **Source Event 전환 (2026-08-15)** | 새로 만드는 원장과 새로 재적재하는 원자는 writer가 `source_event_id`·`source_event_state`를 처음부터 기록하므로 **별도 작업이 없다. 이것이 권장 경로다.** 기존 원장을 잠시 유지해야 할 때만 `conda run -n assy_manager python server/migrations/add_ledger_source_events.py --apply`를 실행한다(`--report`는 읽기 전용). 과거 원자를 억지로 묶지 않고 **원자 1개 = `legacy_atom` 사건 1개**로만 보존한다. 곧 재적재할 환경에서는 이 호환 백필에 시간을 쓰지 않는다 |
| **Evidence Graph 확인** | 배포 게이트는 두 컬럼과 `idx_ledger_source_event`·`idx_ledger_object_entity`를 모두 확인한다. 빠지면 `/api/ledger/subgraph`가 빈 200이 아니라 `503 source_event_projection_not_deployed`와 `missing[]`을 답한다. 재적재 후 `GET /api/ledger/subgraph?id=<opaque-id>&hops=3`에서 `raw_claims:true`, `resolver_applied:false`를 확인한다 |
| **⚠️ 건너뛰어도 500은 안 난다** | ②를 안 돌려도 **웹서버는 죽지 않는다** — 읽는 쪽(`/coverage`)이 카탈로그에 컬럼 존재를 먼저 묻고, 쓰는 쪽(`ensure_schema`)이 백필 첫 단계에 같은 문장을 스스로 적용한다. 잃는 것은 **화면이 거절 사유를 이름으로 보여 주는 능력**이다. 1번 항목처럼 「안 돌리면 라우트가 죽는」 계급이 **아니다** |
| **성질** | **추가 전용·멱등.** DROP 없음, 기존 것의 ALTER 없음, 기존 테이블의 행을 건드리는 문장 없음. ①은 **새 테이블 둘만**, ②는 **컬럼 하나만** 만든다 |
| **급하지 않은 이유** | 안 돌아도 **아무것도 안 깨진다.** 2번과 달리 큰 기존 테이블에 컬럼을 붙이지 않아 **잠금 위험도 없다**. ⚠️ **[2026-08-18 정정] 종전 이 자리의 근거였던 「부팅 시 `server/ledger`를 import하는 프로세스가 없다」는 «거짓»이 됐습니다** — 웹서버가 `main.py` → `ledger_trace_router` → `ledger_selection` → `from ledger import vocabulary`로 **모듈 로드 시점에** import합니다. 🔴 **그래도 결론은 그대로입니다**: import되는 것은 «선언 모듈»이지 표가 아니라서, 마이그레이션이 안 돌았다고 부팅이 실패하지 않습니다. **근거가 바뀐 것이지 위험이 생긴 것이 아닙니다** |
| **~~⏸ 대기~~** | ~~시간대 수정 착지 후에 돌리는 것을 권합니다 — 아래 8번 참조~~ → **해제됨.** 8번이 `bee1aeb`로 착지 |
| **✅ 개발 박스 완료 (2026-08-13)** | 이 박스의 `assy_manager`에 마이그레이션 + 백필 실행. **909 원자 / 추적 가능 랏 25** (`has_wafer` 491 · `register` 245 · `slot_map` 153 · `derived_from` 20), `occurred_at` `2026-05-03T02:17+09:00` ~ `2026-05-21T20:33+09:00`. 원본 44행 전수 처리, 재실행 시 0행 읽음(커서 멱등) |
| **🔴 운영은 «아직»** | 위 완료는 **개발 DB 하나**의 이야기다. 이 파일의 첫 규칙대로 **운영에서는 대표님이 직접 돌려야 하고, 그 전까지 이 항목은 열려 있다.** 운영에서 돌린 뒤 그 줄을 여기에 추가해 주십시오 |
| **운영에서 돌린 뒤 확인** | `GET /api/ledger/coverage`가 `state`를 돌려준다 — `absent`(마이그레이션 미실행) · `empty`(백필 미실행) · `ready`. 화면이 비어 보일 때 **어느 쪽인지 이 한 줄로 갈린다** |
| **⚠️ 그 응답의 `refusals_unaccounted`를 「결함」으로 읽지 마십시오** | **부호가 뜻이다**: `0` 정상 · **`> 0`은 배포 이력**(컬럼이 생기기 «전»에 세어진 거절 — 그 이름은 이미 끝난 프로세스와 함께 사라졌다) · `< 0`만 진짜 장부 결함이다. **개발 두 DB는 지금 `1`을 읽고 그것이 정상이다** |
| **선행 확인** | `tzdata` 필요 (8번 참조). 없으면 조용히 UTC로 안 떨어지고 **예외를 낸다** |

---

## 7. 🔴 지금 대기열 «맨 위» — 업무키 UNIQUE 인덱스 28개 표 전부

| | |
|---|---|
| **기록** | 2026-08-13 등재 · **2026-08-14 실측으로 전면 개정** |
| **⚠️ 이 항목의 두 문장이 틀렸었다** | ① 「아직 마이그레이션 파일이 없다」 — **있다**: `server/migrations/add_business_key_unique_index.py`. 기본이 읽기 전용이고 `--apply`로만 쓴다. ② 「`wafer_map_metadata` 건」 — **범위가 그 한 표가 아니다.** 스크립트는 `tables_with_business_key()`로 대상을 «발견»한다 |
| **🔑 실측 (2026-08-14, `assy_manager`, 읽기 전용)** | **`business_key_val`을 가진 표 28개 · 그중 UNIQUE 인덱스 보유 «0개» · 중복 업무키 «0건»** — 28개 표 전부에서 `count(*) == count(DISTINCT business_key_val)`. **즉 오늘 돌리면 전부 성공한다.** 이 항목이 오래 막혀 있던 이유(「중복이 있으면 어느 행을 남길지가 먼저 판정할 문제」)가 **실측으로 해소됐다** — 판정할 것이 없다 |
| **🔴 왜 대기열 맨 위인가** | `models.py:806-813`이 **자기 주석에서** 「새로 만든 DB는 이 마이그레이션 전까진 무방비」라고 경고한다. 그리고 안 돌았다. 이건 성능이 아니라 **동일성 무결성**이고, 쓰기 경로가 「업무키는 유일하다」를 «가정»하는데 물리가 그걸 보장하지 않는 상태다. 유일성은 지금까지 **쓰기 경로가 우연히 그렇게 보였기 때문에만** 유지됐다 |
| **한 줄** | `conda run -n assy_manager python server/migrations/add_business_key_unique_index.py --apply` <br>(먼저 인자 없이 돌리면 읽기 전용 리포트만 나온다) |
| **목적(원 항목)** | `business_key_val`에 **UNIQUE 인덱스**(SCHEMA_CANON **R2** — 「`business_key`를 선언했으면 UNIQUE 인덱스가 있어야 한다」) |
| **⚠️ 정정** | 이 항목은 처음에 **R6**이라 적었다. R6은 「표식은 열쇠가 아니다」로 다른 규칙이다. 그리고 인덱스 대상도 원시 컬럼 쌍이 아니라 **`business_key_val`**이다 — 이 프로젝트의 기존 패턴(`uq_bk_<table>`)이고, `composite_key_source = [target_table, map_id]`이므로 **같은 제약이다.** 총괄 실측 2026-08-13 |
| **왜** | 🔴 **선언과 물리가 어긋난 R2 위반이다.** `product_tables.py`가 `business_key: "map_pk"`, `composite_key_source: [target_table, map_id]`를 **선언**해 놓았는데, 물리 UNIQUE는 `wafer_map_metadata_pkey`(= `row_id`) **하나뿐**이다. 그래서 `map_overlay._meta_select`의 `.first()`(`LIMIT 1`)가 중복 한 쌍을 만나면 같은 맵이 새로고침마다 **다른 «기하»**를 읽는다 |
| **지금 상태** | `c36368c`가 읽기에 총순서를 박아 **리더는 결정적**으로 만들었다. 🔴 **그런데 그 대가로 이제 중복을 «조용히 가린다»** — 예전엔 값이 흔들려서 티가 났다 |
| **~~방법 (2026-08-13 원문)~~** | ~~**아직 마이그레이션 파일이 없다.** 만들기 전에 운영에 중복이 있는지부터 세야 한다 … 0이면 `CREATE UNIQUE INDEX uq_bk_wafer_map_metadata …`를 붙이면 되고, 0이 아니면 **어느 행을 남길지가 먼저 판정할 문제**다~~ → **위 「한 줄」 행으로 대체.** 이 문장은 바로 위 ⚠️ 행이 반박한 그 문장인데 같은 절 안에 남아 있었다(2026-08-14 정정). 파일은 있고, 중복은 28개 표 전부 0이며, 대상은 이 한 표가 아니다 |

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

## 10. 🔴 실행이 아니라 «주의» — 같은 파일을 다시 넣으면 거절되는 표가 있다

> 총괄 지시로 doc-keeper가 등재(2026-08-14 · `50a21c7`). **돌릴 것이 없는 항목**이고, 신고를 받았을 때 **어디를 보는지**가 내용이다.

| | |
|---|---|
| **기록** | 2026-08-14 (픽스처 레인 재현, 이 박스) |
| **증상** | 어떤 표에 **파일을 처음 넣으면 성공**하고, **같은 키를 담은 파일을 다시 넣으면 배치가 통째로 거절**된다. 로그에 `[BK Conflict Unresolved]`가 남고 그 앞에 회복 시도 3회(`[BK Conflict Recovered]` 아님)가 있다. **새 키만 담긴 파일은 그대로 잘 들어간다** |
| **어느 표인가** | `table_config.json`에서 **`composite_key_source`를 «선언하지 않은»** 표. `business_key`만 있으면 해당된다. 확인: 그 표의 선언에 `composite_key_source` 키가 있는지 본다 |
| **왜** | 신원 해석기가 **`row_id`와 `business_key_val` 둘만** 보고 기존 행을 찾는데, 그 `business_key_val`을 payload에서 만들어 주는 코드가 **복합 키 선언이 있을 때만** 돈다. 그래서 업무 키를 **값으로** 실어 보낸 행은 신원 없이 도착해 **매번 새 행**이 되고, `uq_bk_<표>` 유니크 인덱스가 그것을 실패로 바꾼다. **기전과 판별 케이스**: [architecture/data_model §3.1-quater](../architecture/data_model.md) |
| **🔴 인덱스를 걷지 마십시오** | 유니크 인덱스가 원인이 아니다. 인덱스가 없으면 같은 사건이 **같은 업무 키를 가진 행이 조용히 둘 생기는** 형태로 나타날 뿐이고, 그쪽이 더 나쁘다 |
| **오늘의 회피** | ① 그 표에 **`composite_key_source`를 선언**한다(신원을 구성하는 컬럼들로). ⚠️ **기존 행이 있으면 업무 키 값이 재계산되므로 재키잉이다** — 운영 표에서는 총괄 판정을 거칠 것. ② 또는 재인제션 전에 **그 파일이 덮을 범위의 행을 먼저 지운다**(범위를 좁혀서). 픽스처가 쓴 것이 ②이고 **코드에 「우회」라고 명시**돼 있다 |
| **⏳ 수리** | 없다. 고치는 자리는 신원 해석기가 **선언된 업무 키 컬럼의 값으로도** 조회하게 하는 것으로 보이지만, 그 변경은 **모든 표의 신원 해석**을 건드리므로 총괄 판정 대상이다 |
| **오늘 이 상태인 표(이 박스)** | `wafer_process`(2026-08-14 재등재). 다른 표는 선언을 직접 확인할 것 |

---

## 부록 — 이 박스에서만 하면 되는 것 (운영 아님)

- **`bonding_log`의 base 조인 인덱스** (2026-08-14 등재, **차단 아님**)
  ```bash
  psql "postgresql://postgres:admin@localhost:5432/assy_manager" -f server/migrations/add_bonding_base_join_index.sql
  ```
  마이그레이션 파일은 **저장소에 이미 있고 이 박스에만 미적용**이다. 없어도 돌지만
  놀라움 장치의 칩→랏 브리지가 매 요청 **352,500행 전수 스캔 398 ms**(HashAggregate가
  디스크로 20 MB 스필). 오늘 `core_wafer_map` 건과 **같은 모양** — 인덱스가 없어서가
  아니라 **인덱스가 «이 박스에» 없어서**다. ⚠️ 건 뒤엔 `ANALYZE`도 같이 — 오늘 통계 없는
  표에 인덱스만 걸어 「효과 없음」으로 읽은 적이 있다.
- **`:8081` 격리 스택 재기동** — 셀 이력 기능이 착지하기 «전»에 뜬 프로세스라 그 기능이 안 보인다.
