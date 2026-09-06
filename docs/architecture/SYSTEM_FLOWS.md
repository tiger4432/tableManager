# 시스템 동작 흐름 — 무엇이 · 어떻게 · 어디로 · 어떤 IO 로 · 무엇을 트리거하나

> **Status:** 뼈대 (칸은 «실측»으로 채운다) · **Owner:** 총괄
> **소유자 지시 (2026-09-06):** 「우선 우리 시스템 «전체의 아키텍처 플로우»를 정의해서 문서로 작성해.
> 그 문서에서 하나하나 «체크리스트» 뽑아서 «취약점 분석»」
> 「무엇이 어떻게 어느 세부시스템으로 어떤 io 로 흘러가서 트리거를 하고 작동하는지 **등등 모두**」

---

## 0. 이 문서가 «왜» 필요한가 — 이틀치 실측

이틀 동안 찾은 결함 여섯이 **전부 한 모양**이었고, **여섯 다 «우연히»** 발견됐다.
```
양끝은 지어져 있고 «가운데»가 끊겨 있다. 그리고 그 끊김이 «자기를 안 알린다»
```
| 발견 | 끊긴 자리 | 어떻게 보였나 |
|---|---|---|
| 체인 가운데 홉 | 맵규격 → 재고 | 규칙이 `enabled:false` — 화면엔 「안 돈다」만 |
| 거절 주소 | refuse → 화면 | 캐리어 «3», 읽는 쪽 «0». 화면은 예외 «클래스 이름»을 표시 |
| 걷기 폼 | 화면 → 서버 | `hops`·`direction`·`node_limit` 가 요청에 «안 실림» |
| 워커 기동 | create_task → 로그 | 죽은 태스크에 「spawned」가 «찍힘» |
| 재적재 시각 | 값 → 운영자 | «로그 문장 속 글자»로만, 그것도 큐가 막힌 뒤에만 |
| 미리보기 | v2 경로 → 화면 | 그것을 부르는 «라우트가 없음» |

🔴 **「이 흐름이 끊겼나」를 묻는 계측기가 없다.** 이 문서가 그 계측기의 «질문지»다.

---

## 1. 칸 정의 — 🔴 이 모양을 지켜야 체크리스트가 «기계적으로» 뽑힌다

흐름마다 **이음매(seam)** 를 줄로 적는다. 이음매 하나 = 표의 한 행.

| 칸 | 무엇을 적나 | ⛔ 하면 안 되는 것 |
|---|---|---|
| **출발** | 어느 세부시스템 (파일·모듈) | — |
| **도착** | 어느 세부시스템 | — |
| **트리거** | 무엇이 이 걸음을 «시작»하나 (사람 클릭·행 쓰기·타이머·부팅·이벤트) | 「자동으로」 금지 — 무엇이 부르는지 적는다 |
| **나르개(IO)** | HTTP 쿼리/바디 · DB 행 · outbox 이벤트 · 함수 인자 · 파일 · 로그 · WebSocket | — |
| **지나가는 것** | 🔴 «실측». 요청이면 «쿼리 문자열», 응답이면 «실제 키», 로그면 «그 줄이 정말 찍히나» | 「~를 넘긴다」로 적지 말 것. **전선에서 잰 값** |
| **받는 쪽** | 🔴 «소비자 수». 그리고 그 자리 | 정의 수 말고 «호출/읽는» 수. 데코레이터·시험·설정문자열 «빼고» 센다 |
| **끊기면** | 🔴 «시끄러운가 조용한가» — 무엇이 울리나 | 「오류가 난다」 금지. **어디에 무엇이 뜨나** |
| **상태** | ✅ 이어짐 / ⚠️ 반쪽 / 🔴 끊김 / ⚰️ 죽은 갈래 | — |

### 🔴 「반쪽」이 이 문서의 «핵심 발견 단위»다
```
❌ 「그 함수가 있나」   <- 반쪽 배선이 여기서 «통과»한다 (useRoute 가 그랬다)
✅ 「무엇이 이 이음매를 «실제로 지나가나»」
   실물: useRoute 가 follow «와» hops 를 둘 다 계산하는데 요청엔 follow «만» 실린다 -> ⚠️ 반쪽
```

---

## 2. 흐름 목록 — 🔴 **`docs/qa/FEATURE_CHECKLIST.md §1` 과 `SYSTEM_OVERVIEW §6` 에서 «뽑았다»**

> ⚠️ **[정정 2026-09-06] 이 자리의 첫 판(흐름 «열»)은 제가 «머리에서» 썼고 절반이 빠져 있었다.**
> 소유자 지적: 「플로우 잘못 썼는데? 왜 «기존 문서 참조» 안 해? **파일 인제션 이런 거 어디 있어?**
> 현재 시스템에 있는 기능 **다 넣으라고**」 — 「추측 금지」가 목적인 문서의 «목차»를 추측으로 쓴 것이다.
> 아래는 **정본 인벤토리 두 곳에서 도출**했다. 새 흐름을 발명하지 않았다.

| # | 흐름 | 인벤토리 출처 | 담당 |
|---|---|---|---|
| ① | **파일 인제션** 파일 도착 → 워처 → 파서 → 표 → 인제션 로그 | FC §1.3 · SSOT §6 인제션 파이프라인 | 서버 |
| ② | **HTML 토폴로지 파서** | FC §1.3 · SSOT §6 | 서버 |
| ③ | **배치 업서트** 그리드 편집 → `apply_batch_updates` → 표 → outbox | SSOT §6 배치 업서트 | 서버+클라 |
| ④ | **변경 이력(타임라인)** 쓰기 → 이력 → 화면 | FC §1.2 | 서버+클라 |
| ⑤ | **가상 조인 컬럼** 조회 시점 결합 → 소스 표시 | FC §1.1 · `virtual_join_executor` | 서버 |
| ⑥ | **값 제안 셀 에디터** 타이핑 → 후보 → 확정 | FC §1.1 | 서버+클라 |
| ⑦ | **체인 인제션** 표 쓰기 → outbox → 규칙 → 맵퍼 → 다른 표 | FC §1.5 · SSOT §6 | 서버 |
| ⑧ | **Auto-Update 스케줄러 · 소급** 크론/수동 → 수집기 → 표 → 큐 | FC §1.4 | 서버 |
| ⑨ | **Enrichment Queue** 결손 탐지 → 워크리스트 → 보정 → 표 | FC §1.6 · SSOT §6 | 서버+클라 |
| ⑩ | **정준 원장 — 적재** 표 → 소스 선언 → 번역기 → 원자 | FC §1.13 · SSOT §6 | 서버 |
| ⑪ | **정준 원장 — walk** 원자 → `GET /api/ledger/subgraph` → 클라 모델 → 좌석 | FC §1.13·§1.15 | 서버+클라 |
| ⑫ | **Ontology Config Explorer(작성)** 폼 → 스켈레톤 → 검증 → 저장 → 발효 | FC §1.14 | 서버+클라 |
| ⑬ | **웨이퍼 맵 에디터** 편집 → 저장 → 정렬/규격 → 확정 이력 | FC §1.7 · SSOT §6 | 클라+서버 |
| ⑭ | **범용 맵 오버레이(맵 인프라)** | SSOT §6 | 서버+클라 |
| ⑮ | **전사 계획(본딩/DT)** | SSOT §6 · MAP_EDITOR_SPEC §6 | 서버+클라 |
| ⑯ | **실시간 동기화** 쓰기 → 브로드캐스트 → WS → 화면 델타 | FC §1.10 · SSOT §6 | 서버+클라 |
| ⑰ | **어드민 대시보드(생애주기 5탭)** | FC §1.8 | 서버+클라 |
| ⑱ | **실패 관리·재시도** 실패 → 로그/아웃박스 → 재시도 → 화면 | SSOT §6 · FAILURE_MANAGEMENT_SPEC | 서버 |
| ⑲ | **거절 → 운영자** 실패 → 사유 → 주소 → 표본 → 화면 | (횡단 · 이틀치 발견) | 서버+클라 |
| ⑳ | **운영 감시** 프로세스 → 심박/명부 → `/health` → 화면 | FC §1.11 | 서버 |
| ㉑ | **접근 통제** 토큰 → 게이트 → 내부 IPC → 정적 서빙 봉쇄 | FC §1.12 | 서버 |
| ㉒ | **데스크톱 래퍼 · 듀얼 테마** | FC §1.10 | 클라 |
| ⚰️ | ~~온톨로지 그래프(승격·뷰어·추적)~~ | FC §1.9 — **은퇴. 흐름 아님** | — |

### 🔴 실측이 «또» 찾았습니다 — 인벤토리에도 없던 흐름 넷 (1차 실측, 2026-09-06)
| # | 흐름 | 왜 «별도» 흐름인가 |
|---|---|---|
| ㉓ | **감독 → 재시작 정책** | 「누가 살아 있나」(운영 감시)와 «다른 물음»이다 — 「죽으면 «무엇을 하나»」를 판정한다. 그 판정 어휘의 소비자가 «0» |
| ㉔ | **자식 stdout → 파일** | 거절·관측·통지의 「끊기면」이 «전부 이 파일로» 떨어진다. 이 흐름이 없으면 「시끄럽다」가 «어디서» 시끄러운지 답할 자리가 없다. 🔴 읽는 화면 «0» |
| ㉕ | **소급 실행 큐** | 스케줄에 접혀 있었으나 «거절 흐름의 청중»이 이것이다. 거절 주소가 버려지는 자리가 «여기»라, 따로 재야 거절이 닫힌다 |
| ㉖ | **인제션 진행 → 화면** | 통지 표에선 한 행이지만 «다른 레지스트리»를 지나고 `table_name` 관문 «앞»에서 소비된다. 인제션에도 통지에도 온전히 안 들어간다 |

🔴 **인벤토리에서 뽑아도 «넷이 빠졌습니다».** 인벤토리는 «기능»의 목록이지 «흐름»의 목록이 아니라서다 —
   한 기능 안에서 «다른 물음에 답하는 경로»는 따로 세어야 흐름이 된다. 2차 조사에 이 판별식을 건다.

### 🔴 첫 판에서 «빠졌던» 것 — 기록으로 남긴다
```
파일 인제션 · HTML 토폴로지 파서 · 배치 업서트 · 변경 이력 · 가상 조인 · 값 제안 ·
Enrichment Queue · 맵 오버레이 · 전사 계획 · 어드민 5탭 · 실패 관리 · 접근 통제 · 데스크톱 래퍼
=> «열셋». 제가 쓴 열 중 실제와 맞은 것은 절반이었다
```
🔴 **교훈은 이 문서의 §0 과 같다** — 목차조차 «문서에서» 뽑아야 한다. 머리에서 쓰면 그 목록이
   빠진 것을 «영원히» 안 보이게 만든다. 흐름이 없으면 그 흐름의 이음매도 없다.

### 진행
```
1차 실측 착수 (2026-09-06)   ⑩⑦⑧ · ⑲⑳⑯ · ⑪⑫⑬  — 아홉
남은 것                      ①②③④⑤⑥⑨⑭⑮⑰⑱㉑㉒ — 열셋. 2차로 돈다
```

## 2-bis. 🟢 **선언 — 「운영 감시」의 청중은 «바깥 모니터»다** (소유자 판정 2026-09-06: 「A」)

```
물음     /health 를 client2 에서 부르는 곳이 «0» 이고, 헬스 스트립 함수도 호출자 «0» 이다
        (스트립은 소유자 지시 「띄 다 빼」로 내려갔고 함수는 일부러 남겨 뒀다)
        -> 이 흐름의 «마지막 홉»이 없다. 화면이 청중인가, 바깥 모니터가 청중인가
소유자 판정  **바깥 모니터가 청중이다**
```
🔴 **그러므로 「화면이 없다」는 «발견이 아니다».** 이 줄이 없으면 매 감사가 그것을 다시 잰다.
   이 문단이 그 재측정을 «끝낸다» — 그것이 이 선언의 목적이다.

### ⚠️ 다만 A 가 «닫는 것»과 «안 닫는 것»이 다르다
```
✅ 닫힘    「화면이 없다」 · 「refreshHealthStrip 호출자 0」 -> 설계다. 더 안 잰다
🔴 열림    「/health 에 «닿지도 않는» 값들」 — 청중이 바깥 모니터여도 그 값들은 여전히 «못 갑니다»
          · heartbeat 의 `note`          (heartbeat.py:290 에서 읽히는데 worker 항목에 «복사 안 됨»)
          · supervisor 의 terminal_verdict (process_supervisor.py:867 이 쓰는데 health 가 «7키만» 복사)
          · backfill.beat(result) 가 «main() 안»에 있어 «어드민이 부른 백필은 심박을 안 냄»
=> 청중이 정해졌으니 이제 그 청중 기준으로 «빠진 것»이 정확히 셋이다
```
📌 **판별식이 이렇게 바뀐다:** 「화면에 뜨나」 ❌  ->  「`/health` 응답에 «들어 있나»」 ✅

## 3. 채우는 규칙

```
① 문서를 «먼저» 읽고(CODE_MAP 해당 절 · architecture/*) 그다음 «코드로 검증»한다
   -> 문서가 낡았으면 «그것이 발견»이다. 표의 「상태」에 적는다
② 소비자를 셀 때 «세 갈래»를 뺀다 — 데코레이터 등록 · 시험 전용 · 설정에 문자열로 든 이름
③ 도달 불가능한 갈래는 ⚰️ 로 «표시»한다. grep 에 살아 보이는 것이 이 저장소의 거짓 신호원이다
④ 못 밝힌 것은 «못 밝혔다»고 적는다. 추측 금지
```

---

## 4. 체크리스트 추출 규칙 — 표가 채워지면 «기계적»으로 나온다

이음매 한 행 = 점검 항목 셋:
```
㉠ 선언된 것이 «실제로» 지나가나        (「지나가는 것」 칸 vs 「나르개」 칸)
㉡ 받는 쪽이 «있나»                   (「받는 쪽」 칸 = 0 이면 그 이음매는 «없는 것»)
㉢ 끊기면 «시끄러운가»                 (「끊기면」 칸 = 조용 이면 취약점)
```
🔴 취약점 분석은 이 셋의 «아니오»를 모은 것이다. 따로 발명하지 않는다.

---

## 5. 흐름 상세 — 1차 실측 (2026-09-06)

> 아래 표는 «실측»이다. 라운드 서사·못 밝힌 것·낡은 문서 목록은 각 실측 파일에 있다:
> [원장적재·체인·스케줄](../../task/SYSTEM_FLOWS_A.md) ·
> [거절·관측·통지·백업](../../task/SYSTEM_FLOWS_B.md) ·
> [원장→화면·작성·맵편집](../../task/SYSTEM_FLOWS_C.md)
> ⚠️ 번호는 «읽기 편의»다. 주소는 «이름»이다 (§2 정정 참조).


---

### 실측 묶음 — 원장 적재 · 체인 · 스케줄

## ⑩ 정준 원장 — 적재 (표 → 소스 선언 → 번역기 → 원자)

> 🔴 **먼저 알아야 할 것 하나: 이 흐름에는 «타이머가 없다».** 부팅 호출도 없다.
> `server/migrations/add_ledger_events.py` 가 자기 주석에 적어 둔 그대로 —
> 「부팅에 `server/ledger` 를 import 하는 프로세스가 없다」. 쓰기 경로의 모든 실행은
> **사람이 누른 admin POST 이거나 CLI** 다. 스케줄러는 «나르기만» 한다(⑧과 만나는 자리).

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| L-1 | 브라우저/curl | `main.py::trigger_retroactive_run` | **`POST /admin/retroactive/{op}/run`** (`op=ledger_backfill`), `Depends(require_admin_token_strict)` | HTTP 바디 | 바디 키 `{"params":{...}}` — `params` 는 `retroactive.validate` 가 검사 | 데코레이터 등록 핸들러 1 (규칙상 제외) → **비라우트 호출자 0** | 🔊 `RetroactiveRefused` → HTTP 4xx (`main.py` 의 `except`) | ✅ |
| L-2 | `retroactive.publish` | `database_outbox` + `retroactive_runs` | L-1 과 «같은 요청», 동기 | DB 행 ×2, **한 커밋** | `DatabaseOutbox(event_uuid, table_name="__retroactive__", event_type="RETROACTIVE_RUN", payload={run_id,op,params,requested_by}, processed_chain=False)` + `RetroactiveRun(run_id,op,params,requested_by,state="queued")` → `NOTIFY outbox_event;` | 1 (`retroactive.publish` 가 유일한 writer) | 행은 🔊(durable). **NOTIFY 실패는 🔇** — `except → logger.debug` | ✅ |
| L-3 | outbox 행 | `run_auto_update.start_retroactive_run` → `retroactive.execute` | **outbox `event_type == EVENT_RETROACTIVE_RUN`** (스케줄러 틱이 줍는다) | outbox 이벤트 | `payload` dict → `spec["run"](db, params, log, control)` | 1 (`run_auto_update.py`) | 🔊 이미 실행 중이면 `logger.warning("[Retroactive] a run is already in flight …")` + **행을 미처리로 남김**(다음 틱 재시도). 실패는 `state=RUN_FAILED` + 로그 | ✅ |
| L-4 | `retroactive._run_ledger_backfill` | `ledger.backfill.run` | `OPERATIONS["ledger_backfill"]["run"]` 디스패치 | 함수 인자 | `backfill.run(db.get_bind(), source=params["source"], checkpoint=_checkpoint(control), pace=params.get("pace"))` — 🔴 **`retranslate` 는 안 넘긴다** | 비시험 호출자 2 (`retroactive.py`, `backfill.main()`) · 설정문자열 1(`"ledger_backfill"`) | 🔊 예외가 `retroactive.execute` 의 `except` 로 → 실행 행 `FAILED` | ✅ |
| L-5 | CLI | `backfill.run` | **`python -m ledger.backfill --source <id>`** | argv | `--source --fetch-rows --max-batches --pace --ontology-root --scope-column --scope-values --apply` (`--reset-cursor`/`--from` 은 `destructive_approval_required` 로 거절) | 1 (`__main__`) | 🔊 traceback + `basicConfig(INFO)` | ✅ |
| L-6 | 소스 릴레이션 (예: `lot_event`) | `backfill._fetch_v2_lineage_page` | `_run_v2_lineage` 의 `walk_group_pages` 루프 | DB SELECT | 컬럼은 `v2_base_select_columns(snapshot, source_id)`, 페이징 `WHERE page_key > cursor` | 1 | 🔊 psycopg 예외 → 실행 `FAILED` | ✅ |
| L-7 | `backfill._run_v2_lineage` | `runtime_v2.execute_cursor_batch` | 페이지마다 | 함수 인자 | `execute_selected_cursor_batch(setup, source, frame, next_cursor, _no_join_reader(), store, known_registrations=known, retranslate_approved=approved)` | 각각 비시험 호출자 **1** | 🔊 `LedgerV2RuntimeError(code, path, message)` | ✅ |
| L-8 | `runtime_v2` | `source_preparation.prepare_source_batch` | `preview_cursor_batch` 안 | 함수 인자 | `SourcePreparationContext(snapshot, source_plan)` + frame + reader + implementations — 선언의 `prepare`/`read`/`map`/`bind` 가 몰고 간다 | 비시험 호출자 1 | 🔊 `SourcePreparationError` | ✅ |
| L-9 | `runtime_v2._screened_atoms` | `gate.screen_compiled_molecule` | `with gate.building_molecule(source_id)` 안에서 호출 | 함수 인자 | `(source_id, atoms, declared_derivations, declared_subject_types, molecule_ref=…, source_rows=…)` → `(kept, _report)`, 🔴 **`_report` 는 «버린다»** | 비시험 호출자 1 | 🔊 **하고 «치명적»**: `gate.refuse` 가 로그 후 `MoleculeRefused` 를 raise 하고, 이 경로엔 잡는 곳이 없어 **배치·실행이 통째로 죽는다** | ⚠️ |
| L-10 | `runtime_v2.execute_cursor_batch` | `LedgerStore.write_batch` | L-7 | 함수 인자 | `write_batch(source_id, translator_version, kept_all, dict(cursor_value), molecule_count, refused=0, incomplete=…, reasons={}, enforce_translator_version=not retranslate_approved)` 🔴 **`refused` 와 `reasons` 는 «리터럴»** | 정당 호출자 **2**(`runtime_v2` 두 자리) · 🔴 **두 번째 문 7**(`server/scripts/seed_syn_*.py`) · 시험 6 | 🔊 kwarg 누락 시 `TypeError` → `LedgerV2RuntimeError("unsupported_store_contract","store.write_batch")` | ✅ |
| L-11 | `LedgerStore.insert_atoms` | **`ledger_events`** | `write_batch` 안 | DB INSERT | `envelope.ROW_COLUMNS` **14칸 전부** — `id, subject_type, subject_keys, predicate, object_kind, object_payload, occurred_at, source_who, source_translator_ver, source_raw_ref, supersedes, source_event_id, source_event_state, occurred_at_basis` · `ON CONFLICT DO NOTHING` · `execute_values(page_size=1000)` · 기본값에 맡기는 칸 **0** | 1 (`write_batch`) | 🔇 **행 유실은 조용하다** — `ON CONFLICT DO NOTHING` 이 무표적이라, 반환값의 `attempted > inserted` 차이(`deduped`)로만 보인다 | ✅ |
| L-12 | `LedgerStore._advance_cursor` | **`ledger_translator_cursor`** | `write_batch` 안, `advance_cursor=True` 일 때 | DB UPSERT, **같은 커넥션·같은 커밋** | `(source, translator_ver, cursor_value, molecules_done, atoms_written, atoms_deduped, molecules_refused, incomplete_molecules, refusal_reasons, updated_at)` + `ON CONFLICT (source) DO UPDATE` + 선택 가드 `WHERE …translator_ver = EXCLUDED.translator_ver RETURNING source` | 1 (`write_batch`) | 🔊 `CursorVersionConflict` (RETURNING 이 빈 행일 때) | ✅ |
| L-13 | `ledger_translator_cursor` | 화면 | **`GET /admin/ledger/sources`** (`require_admin_token`) → `ledger_admin.sources_view` | HTTP 응답 JSON | `_CURSOR_FIELDS = (translator_ver, molecules_done, atoms_written, atoms_deduped, molecules_refused, refusal_reasons, updated_at)` + 파생 `refusals_unaccounted` | 라우트 핸들러 1 = **살아 있는 유일한 독자** | 🔊 컬럼 부재 시 500(코드가 카탈로그를 먼저 프로브) | ✅ |
| L-14 | `store.read_cursor` | `backfill._run_v2_lineage` | 실행 시작 시 | DB read | `{source, translator_ver, cursor_value, molecules_done, atoms_written, atoms_deduped, molecules_refused, incomplete_molecules, source_head, head_probed_at, updated_at, refusal_reasons}` | 비시험 호출자 **3** (`_run_v2_lineage`, `rows_past_cursor`, `scripts/ledger_restamp_cursor.py`) | 🔊 모양 불일치 → `LedgerSetupError("legacy_cursor_reset_required"/"cursor_snapshot_reset_required")` | ✅ |
| L-15 | `server/scripts/seed_syn_*.py` (**7**) | `LedgerStore.write_batch` | **CLI**, 각자 `--apply` | 함수 인자 | 예: `write_batch(SOURCE, TRANSLATOR, accepted, cursor_value={"fixture":"complete"}, molecules=len(groups), refused=0, incomplete=0, reasons={})` — 🔴 **선언이 이 원자를 «본 적이 없다»** | 스크립트 7, 공용 호출자 0 | — (CLAUDE.md 가 이미 판정한 «두 번째 문») | ⚠️ |
| L-16 | `gate` 프로세스 카운터 | `retroactive_runs.result` JSON | `_run_v2_lineage` 끝 | 함수 반환 → DB 행 → HTTP | `result["refused_total"] = sum(gate.refusals().values())`, `result["refused_samples"]`, `result["refused_samples_capped"]` | 비시험 호출자 1 | — | ⚰️ **도달 불가** (근거는 §3-①) |
| L-17 | `ledger_events` + 커서 | `ledger_trace.coverage()` | — | — | `CURSOR_FIELDS`, `refusals_unaccounted` | **운영 호출자 0** (시험 4) | 🔇 아무도 안 부른다 | ⚰️ (라우트가 2026-08-28 은퇴하며 독자를 데려갔다) |

### ⑩ 의 핵심 발견 — 「**거절이 «자기 칸»에 못 닿는다**」

```
쓰는 쪽   ledger_translator_cursor.molecules_refused · refusal_reasons
          + _merge_reasons_sql() 의 FULL JOIN 누적 · {reason:{count,last_at}} 모양
읽는 쪽   GET /admin/ledger/sources 가 «살아서» 그 값을 그리고
          refusals_unaccounted 로 REFUSALS_NONE / _NAMED / _UNKNOWABLE 까지 가른다
가운데    🔴 «비어 있다» — 선언 경로에서 그 값이 0 이 아닐 수 있는 코드 경로가 «없다»
```
실측 근거 셋:
1. `runtime_v2` 의 write_batch 두 자리 **둘 다** `refused=0, reasons={}` 가 **리터럴**이다.
2. 거절은 `gate.refuse` 가 `MoleculeRefused` 를 **raise** 해서 나가고, 운영 코드에서
   그것을 잡는 곳은 **seed 스크립트 셋뿐**(`seed_syn_journey_atoms` · `_process_ledger` ·
   `_split_merge_pressure`). 선언 경로엔 **없다** → 배치가 죽고 `write_batch` 는 **안 불린다**.
3. 그래서 `backfill` 이 루프 «뒤»에서 채우는 `refused_total`·`refused_samples` 는
   **거절이 하나도 없었던 실행에서만** 채워진다 → 항상 0. (⚰️ L-16)

⚠️ 이건 「없어서 0」이 아니라 **「구조적으로 0」**이다. 화면은 정상으로 보인다.
📎 그리고 **⑩ 은 이 저장소의 「반쪽」 중 «드문 방향»이다** — 보통은 쓰는 쪽이 살고 읽는 쪽이
   없는데, 여기는 **읽는 쪽이 살아 있고 쓰는 쪽이 닿지 못한다.**
   `ledger_admin.py` 가 이미 절반은 자백하고 있다: 「이걸 읽던 유일한 코드는
   `ledger_trace.coverage` 에 매달려 있었고 그 라우트가 2026-08-28 에 은퇴하며 읽기를
   데려갔다」 — **라우트는 복구됐는데 «쓰기»는 복구되지 않았다.**

---
## ⑦ 체인 인제션 (표 쓰기 → outbox → 규칙 → 맵퍼 → 다른 표 → 다시 outbox)

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| C-1 | `main.py::startup_event` | `chain_ingestion_worker.start_chain_ingestion_worker` | **부팅** (uvicorn startup, 무조건) | `create_task` + **done 콜백** | `chain_task = main_loop.create_task(...)` → `chain_task.add_done_callback(_log_chain_worker_exit)` → INFO `"Chained Ingestion Worker background task spawned."` | 1 (부팅 1회) | 🔊 **이제 시끄럽다**: 콜백이 ERROR `"Chained Ingestion Worker did NOT start - the line above saying it was spawned is about a task that is already gone. Reason: %s: %s"` + `exc_info`. 취소(정상 종료)는 침묵, 무예외 반환은 WARNING | ✅ **(오늘 `afc7a7ab` 이 고쳤다 — 지시서엔 결함으로 적혀 있었다)** |
| C-2 | `run_decoupled_app.py` | `run_chain_worker.py` (별도 프로세스) | **런처의 `ChildSpec("Chained Ingestion Worker", …, heartbeat="chain")`** | 자식 프로세스 | 같은 `start_chain_ingestion_worker` | 1 | 🔊 `except Exception as e: logger.error(f"Exception occurred: {e}")` → `chain_worker.log` | ⚠️ **둘이 «같은 큐»를 노린다** — C-3 이 가른다 |
| C-3 | 심박 파일 | `another_chain_loop_is_running()` | C-1/C-2 진입 직후 | 파일 read (`utils/heartbeat.read_all`) | 셋이 **모두** 참이어야 「돌고 있다」: 비트가 fresh · pid ≠ 자기 · `psutil.pid_exists(pid)` | 1 | 🔊 WARNING `"[Chain Worker] NOT starting: another chain loop is already running (%s). …"` | ✅ (일부러 관대 — 판정 못 하면 «시작»한다) |
| C-4 | `crud.apply_batch_updates` (사람 편집·인제션·체인 자기 쓰기) | `database_outbox` | **행 쓰기** — `@event.listens_for(Session,"before_flush")` | DB 행 + `NOTIFY` | **per-row**: `payload={row_id, business_key, data{col:{value,is_overwrite,updated_by}}, transaction_id, updated_by, source_name, timestamp}` · **collapsed**: `payload={row_ids[≤1000], row_count, table_name, transaction_id, updated_by, source_name, timestamp}` · 행 칸: `event_uuid, event_type, table_name, payload, status="PENDING"` (나머지는 기본값) | 리스너 등록 1 (전역 Session) | 🔇 **`NOTIFY` 실패는 통째로 삼킨다** (`except: pass`). 대가는 유실이 아니라 «2초 폴백 폴링» | ✅ |
| C-5 | `request_outbox_mode` | `stage_collapsed_event` | 축약 **옵트인** | ContextVar | 켜는 곳 **정확히 둘**: `directory_watcher._upsert_to_local_db`(파일 전체 루프) · `chain_ingestion_worker`(파생 쓰기 «한 호출»만) | 2 | — | ✅ (문서 §2.4 의 「둘뿐」 **여전히 참**) |
| C-6 | `database_outbox` | `OutboxListener` / 폴링 | **`LISTEN outbox_event`** (워커 수명 내내 1회 등록) + 2초 타임아웃 폴링 | 소켓 통지 / SELECT | `processed_chain == False` 를 `id asc LIMIT 200`. `SYSTEM_RELOAD` 는 별도 스로틀 질의(1초) | 1 | 🔊 큐 머리가 `heartbeat.DEFAULT_STALE_AFTER_SEC` 동안 안 움직이면 `QueueHeadWatch` 가 ERROR 한 줄(그 간격당 1회) | ✅ |
| C-7 | `chain_rules.json` | `load_chain_rules()` | **워커 기동 1회** + **`SYSTEM_RELOAD` 이벤트** | 파일 read | `data["rules"]` 원문 + `enrichment_config.load_enrichment_chain_rules()` 파생분 병합 → **끝에 `_validate_chain_cascade_graph(rules)`** | 운영 호출자 **3** (기동 · SYSTEM_RELOAD · `chain_replay`) · 시험 3 | 🔴 §3-② 참조 — **기동과 리로드가 서로 다르게 실패한다** | ⚠️ |
| C-8 | 규칙 집합 | 순환 그래프 검증 | `load_chain_rules` 끝 · **그리고** `ledger_admin.save_chain_rule_raw` | 함수 인자 | 규칙 하나가 **엣지 «둘»**: `trigger_table→target_table`, 그리고 `allow_map_metadata_upsert` 면 `trigger_table→map_meta_registrar.META_TABLE`(=`wafer_map_metadata`) | 2 (`load_chain_rules`, `ledger_admin`) | 🔊 `ValueError("allow_chain_trigger cycle: …")` | ✅ |
| C-9 | 운영자 | `chain_rules.json` | **`POST /admin/chain/rules/raw`** → `ledger_admin.save_chain_rule_raw` | HTTP 바디 | `{name, declaration, base}`; `base` 는 fingerprint(낙관적 잠금) · 신규 규칙은 **`enabled=False` 로 착지** · 저장 «전»에 순환 검증 | 라우트 1 + 클라 `admin.js` | 🔊 `chain_cycle` / `stale_base` / `declaration_rejected` refusal 로 거절 | ✅ |
| C-10 | 이벤트 그룹 | `process_chain_transaction_group` | `transaction_id` 로 묶은 그룹 | 함수 인자 | `valid_events = [e for e in events if e.event_type in ["CREATE","EDIT"] and any(rule.trigger_table == e.table_name and enabled and _rule_accepts_event(r,e))]` — 🔴 `DELETE`·`SYSTEM_RELOAD` 는 여기서 **빠진다**(그리고 no-op 그룹으로 `SUCCESS` 확정된다) | 1 | 🔊 실패 시 rollback + `retry_count += 1`, 3회 후 `FAILED` 격리 | ✅ |
| C-11 | 축약 이벤트 | `outbox_expand.expand_events` | C-10 안, 규칙이 붙은 뒤 | DB 재조회 | 본 테이블을 다시 읽어 per-row 와 **같은 중첩 페이로드** 합성 | **운영 호출자 1** (체인 워커 자신) | 🔊 미해결 `row_id` 를 세어 WARNING (표·tx·표본 동봉) | ⚠️ §3-③ |
| C-12 | 워커 | 사용자 맵퍼 (`server/mappers/*.py`, gitignored) | `execute_custom_mapper(module, function, db, payload, rule)` | 함수 인자 | 반환은 `GeneralUpdateBatch` dict — `updates[].{row_id` 또는 `business_key_val, updates{}, source_name="chain_ingestion", updated_by}` | 활성 규칙 **5** 개가 맵퍼 5종을 지목 | 🔊 예외 → 그룹 실패 → 재시도/격리 | ✅ |
| C-13 | 맵퍼 결과 | `crud.apply_batch_updates` | `write_batches` 루프 | 함수 인자 | 순서 고정: **맵 메타데이터 먼저** → 일반 target → scoped/retract. 각 배치는 `chain_key_gate.screen()` 을 **반드시** 통과 | 1 (유일한 통로) | 🔊 키 없는 행은 `key_gate_report["refused_rows"]` 로 걸러지고 심박 note 로 나간다 · 드롭 셀은 WARNING `"⚠️ [Chain Write Discard] …"` | ✅ |
| C-14 | 파생 쓰기 | `database_outbox` (**다시**) | C-13 의 flush | outbox 이벤트 (축약) | `source_name="chain_ingestion"` 이 실린다 → 하류 `_rule_accepts_event` 가 **옵트인 규칙만** 통과시킨다 | 순환 필터 1 | — | ✅ |
| C-15 | 워커 | 웹서버 | **커밋 «후» 인라인 `await`** (`_dispatch_broadcasts`) | `POST /internal/events/broadcast` (admin 토큰, timeout 3s, `trust_env=False`) | `{"event": "batch_row_upsert" / "batch_row_delete" / "batch_refresh_required", …}` | 1 라우트 → `manager.broadcast` | 🔊 실패는 **삼키되** `broadcast_at` 을 NULL 로 남겨 스윕이 재발사 · `[Latency] tx=… wake=…ms mapper=…ms commit=…ms notify=…ms total=…ms ok=<bool>` INFO 1줄 | ✅ |
| C-16 | 웹서버 | 브라우저 | `manager.broadcast(json.dumps(payload))` | WebSocket | 같은 dict 그대로 (릴레이) | `client2/src/websocket.js` 가 **셋 다** 처리 (`batch_row_upsert` · `batch_row_delete` · `batch_refresh_required`) | 🔇 WS 끊김은 이 층에서 안 울린다 | ✅ |
| C-17 | `broadcast_at IS NULL` | `sweep_undelivered_broadcasts` | 워커 루프 `finally`, **5초 스로틀** | DB read + POST | `refresh_targets = affected_targets ∪ source_tables`, 표당 `batch_refresh_required` 1건 dedup, `LIMIT 500` + grace 5s, 부분 인덱스 `idx_outbox_undelivered` | 1 | 🔊 실패는 `[Chain Worker] maintenance pass failed: …` ERROR | ✅ |
| C-18 | `database_outbox` | 운영자 | **`GET /admin/chain/queue`** (`require_admin_token`) | HTTP 응답 | 대기 깊이·나이를 **소유자별로** 가름(`event_constants.outbox_owner`), 자리표시자 표이름(`__retroactive__`)은 표로 안 셈, tx 로 접은 목록 | 클라 `admin.js` → `chain_queue_panel.js` **1** | 🔊 404 면 화면이 「이 서버 프로세스에 … 없습니다 (404) — 재기동이 필요합니다」 | ✅ |

### ⑦ 의 핵심 발견 — 「**가운데 홉을 켜면 «지금은» 거절당한다. 그리고 거절 방식이 «자리마다 다르다»**」

지시서가 확인을 요청한 건. **확인됐고, 통제군으로 기제까지 갈랐다.**

```
실측 (커밋된 .sample 로 재측정 — 라이브와 규칙 플래그가 «동일»하다)
  현행 그대로               ACCEPTED  (엣지 둘: dt_inventory→dt_map · dt_inventory→wafer_map_metadata)
  dt_metadata_to_dt_inventory 를 enabled=true 로 (메모리 안에서만)
                           REFUSED: allow_chain_trigger cycle:
                                    wafer_map_metadata -> dt_inventory -> wafer_map_metadata
  통제군: 같은 플립 + allow_map_metadata_upsert 를 «전부 제거»
                           ACCEPTED   <- 🔴 즉 «둘째 엣지»가 순환을 만든다
```
🔴 **`trigger_table` 이 엣지이고 `source_table` 은 아니다** — 지시서 문장 그대로 참이다.
`dt_inventory_to_standard_dt_map` 은 `source_table="dt_log"` 인데 그래프는 `dt_inventory` 에서
나간다. 뜻이 겹치는 칸이 둘일 때 **코드가 걷는 쪽**을 고르는 그 자리다.

---
## ⑧ Auto-Update 스케줄러 · 소급 (크론/수동 → 수집기 → 표 → 큐)

> **타이머는 «있다» — 다만 OS 크론이 아니라 «프로세스 안의 5초 틱»이다.**
> `MultiDiscoveryScheduler(check_interval=5)` → `time.sleep(self.check_interval)`.
> 크론식은 config 가 아니라 **수집기 스크립트의 첫 20줄 주석**(`# schedule:`)에서 파싱한다.
> 프로세스는 `process_supervisor.py` 가 아니라 **`run_decoupled_app.py`** 의
> `ChildSpec("Auto Update Scheduler", ["run_auto_update.py"], heartbeat="scheduler")` 다.

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| A-1 | `MultiDiscoveryScheduler.run()` | `check_and_run_schedules` → `start_collector` → 데몬 스레드 → `execute_collector` | **`time.sleep(5)` 틱**; 수집기별 만기는 `croniter(cron_expression).get_next()` | 함수 인자 → `threading.Thread` | 크론식은 스크립트 주석에서 파싱(`parse_script_comments`) | 프로세스 내 호출자 1 · 라우트 0 · 시험 4 | 🔊 `logger.error("Collector Execution Failed for table '…'")` **와** `scheduler_status.json` 의 `last_status="FAIL"`+`last_error` → 화면 traceback 뷰어 | ✅ |
| A-2 | `GenericScriptRunnerCollector.execute()` | `<DATA_ROOT>/ingestion_workspace/<table>/raws/` | A-1 수집기 본문 완료 | **파일** (`.tmp` 쓰기 + `os.replace` 원자 rename) | `f"{prefix}_{YYYYmmdd_HHMMSS}.csv"` | 1 (디렉터리 워처 — 흐름 ① 소속) | 🔊 `"Successfully transferred '…' to ingestion queue."` / 실패 시 ERROR 후 re-raise | ✅ |
| A-3 | 사람 클릭 (`admin.js` `.btn-run-now`) | `main.py::trigger_auto_update_run_now` | **`POST /admin/auto-update/run-now`** (STRICT 토큰; 토큰 미설정이면 503) | HTTP 바디 → DB 행 + NOTIFY | 바디 `{table_name, script_name}` (둘 다 `Body(..., embed=True)`) · 행: `event_uuid`, `table_name`=**진짜 표 이름**, `event_type="SCHEDULER_RUN_NOW"` (🔴 **리터럴** — 상수 참조 아님), `payload={table_name,script_name}`, `processed_chain=False` | 라우트 1 + UI 1 | 🔊 200 + INFO. ⚠️ 다만 ack 는 «발행»만 증명한다 — 스케줄러가 사는지 확인하지 않는다 | ✅ |
| A-4 | outbox (`SCHEDULER_RUN_NOW`) | `run_collector_on_demand` → `start_collector` | **5초 폴링** (🔴 `LISTEN` 없음 — A-6) | outbox 이벤트 | `event_type == EVENT_SCHEDULER_RUN_NOW AND processed_chain == False ORDER BY id ASC LIMIT 1`; 읽는 것 `payload.table_name/script_name`; 쓰는 것 `processed_chain=True` | 1 | 🔴 **조용하고, 큐를 막는다** — §3-③ 참조 | 🔴 |
| A-5 | 사람 클릭 (`admin.js` · **그리고** `main.js::runRetroactive` 의 그리드 RedoBanner) | `retroactive.publish` | **`POST /admin/retroactive/{op}/run`** (STRICT 토큰) | HTTP 바디 → **DB 행 둘, 한 커밋** | `database_outbox`: `table_name="__retroactive__"`, `event_type="RETROACTIVE_RUN"`, `payload={run_id(12-hex),op,params,requested_by}` · `retroactive_runs`: `run_id, op, params, requested_by(없으면 NULL 유지 — 지어내지 않는다), state="queued"` · `db.commit()` 하나 | 라우트 1 · **UI 2** · `publish` 비시험 호출자 1 | 🔊 `RetroactiveRefused`→400, 그 외 500 + ERROR; 성공은 INFO + 토스트 | ✅ |
| A-6 | `NOTIFY outbox_event;` (`retroactive.publish` · `trigger_auto_update_run_now`) | *(의도: 스케줄러)* | A-3/A-5 와 같은 커밋 | PostgreSQL NOTIFY | 채널 `outbox_event`, 페이로드 없음 | 🔴 **이 흐름의 소비자 0** — `grep -c LISTEN server/run_auto_update.py` = **0**. 트리에서 `LISTEN outbox_event` 하는 곳은 체인 워커뿐이고 그것은 두 이벤트를 `CONTROL_EVENT_TYPES` 로 **즉시 건너뛴다** | 🔇 무해(5초 폴링이 덮는다). 다만 **주석 둘이 거짓** | ⚰️ |
| A-7 | outbox (`RETROACTIVE_RUN`) | `handle_retroactive_trigger` | 5초 폴링, `if not self.retroactive_busy():` 로 감쌈 | outbox 이벤트 | 같은 필터 모양; `processed_chain=True` 를 **실행 시작 «전»에** 찍는다(at-most-once); 핸들러 실패 시 `status="FAILED"` **와** `processed_chain=True` 를 함께 | 1 | 🔊 ERROR 로 outbox#·run_id·op 를 이름 붙여 남긴다. 2차 실패도 별도 ERROR(「큐가 아직 이 행 뒤에 막혀 있다」) | ✅ |
| A-8 | `handle_retroactive_trigger` | `retroactive.execute` | `threading.Thread(name="retroactive-run", daemon=True)` | 함수 인자 → 스레드 | payload 그대로 + `log=logger.info`(**`Scheduler`** 로거) | `retroactive.execute` 비시험 호출자 **1** · 시험 7 | 🔊 `logger.error("[Retroactive] runner thread raised: …", exc_info=True)` | ✅ |
| A-9 | `retroactive.execute` | `retroactive_runs` (`_mark_run`, **자기 세션**) | 연산 시작/종료 | DB 행 | 시작: `state="running"`, `started_at`, `last_progress_at`, `runner=name/host/pid` · 종료: `finished_at`, `state∈{done,cancelled,failed}`, `result=json(...)`, `error=str(e)[:2000]` | 모듈 내 독자 5 (`runs`·`in_flight`·`queue_view`·`request_cancel`·`RunControl`) | 🔊 실패해도 죽지 않고, **값으로도** 나간다 — `record_failures()` → `/admin/chain/queue` | ✅ |
| A-10 | 연산의 checkpoint 훅 | `retroactive_runs.last_progress_at/processed_rows/total_rows` | 배치 경계 | DB 행 (자기 세션) | `last_progress_at` 은 항상; `processed_rows`/`total_rows` 는 값이 있을 때만(**NULL=모름, 0 으로 안 적는다**) | 등록된 연산 6 중 **4** 만 `_checkpoint(control)` 를 넘긴다(`chain_replay`·`withdraw`·`enrichment_backfill`·`ledger_backfill`) | 🔇 `except → logger.debug` 인데 **루트가 INFO** (`utils/logger.py:251 root_logger.setLevel(logging.INFO)`) → **그 줄은 안 찍힌다.** 보이는 것은 `in_flight()` 의 `moving="unreported"` 뿐 | ⚠️ |
| A-11 | `retroactive_runs` | 화면 | **`GET /admin/retroactive/runs?limit=50`** → `admin.js::refreshRunning` → `retroactive_view.buildRunsView` | HTTP JSON | 서버는 **13칸**을 보낸다: `run_id, op, label, params, requested_by, state, processed_rows, total_rows, result, error, queued_at, started_at, last_progress_at, finished_at` — **클라는 9칸만 읽는다** | 라우트 1 · UI 1 | 🔊 비정상 응답은 화면의 `failedSources` 에 「실행 목록」으로 남긴다(빈 목록으로 접지 않는다) | ⚠️ §3-④ |
| A-12 | `retroactive_runs` | **`GET /admin/chain/queue`** → `chain_queue_panel.js` + `pickup_state.js` | 어드민 「체인」 탭 갱신 | HTTP JSON, `owners["scheduler"]` 밑 | `blocked_by{run_id,op,params,requested_by,queued_at,state,moving∈{progressing,stalled,unreported},runner,gate_blocked,no_progress_seconds,stall_after_seconds=300.0,processed_rows,total_rows,cancel_reaches∈{at_next_batch,unknown,never},recovery}` · `queue{last_pickup_at,last_pickup_age_seconds,picker_interval_seconds=5,stall_after_seconds=60.0,waiting_count,waiting[]+ahead,orphaned[],record_failures[]}` | 라우트 1 · **UI 2** | ⚠️ **실패 경로가 조용하다**: `except → logger.debug(...)` (안 찍힘) → `blocked_by=null` + `queue` 키 «부재» → 패널이 「막는 것 없음」으로 그린다. 404 는 반대로 시끄럽다 | ✅ / 실패 경로 ⚠️ |
| A-13 | 사람 클릭 | `retroactive_runs.state="cancel_requested"` → `RunControl.stop_requested` (**교차 프로세스**) | **`POST /admin/retroactive/runs/{run_id}/cancel`** | HTTP → DB 행 → 폴링 | `state` 만 쓰고, 연산의 checkpoint 훅이 되읽는다. 한 번 True 면 sticky | 라우트 1 · UI 1 (`cancellable !== true` 면 × 를 감춘다) | 🔊 이미 끝난 실행/모르는 id 는 400 + 이름 붙은 거절 | ✅ |
| A-14 | `heartbeat.beat("scheduler")` | `run_decoupled_app.py` 명부 → `server/health.py` | 매 틱(5초) | 심박 파일 | `note` 없음; `DEFAULT_STALE_AFTER_SEC=60.0` | 1 writer · 1 명부 · 1 reader | 🔊 `/health` 가 stale/wedged 로 보고. ⚠️ 다만 §3-⑤ | ⚠️ |
| A-15 | `_write_status_file` | `<DATA_ROOT>/config/scheduler_status.json` → **`GET /admin/auto-update/status`** | 로드 시 · 수집기 시작/종료마다 · SKIP 마다 | 파일 → HTTP JSON | 수집기별 `table_name, script_name, script_path, cron_expression(또는 "Manual-only"), next_run, last_run, last_status, last_error, active` — `active` 는 라우트가 `auto_update_control.json` 에서 **라이브로 재계산**(토글이 즉시 보이도록) | 라우트 1 · UI 1 | 🔊 화면 traceback 뷰어. ⚠️ 읽기 실패는 `{"status":"error","data":[]}` **HTTP 200** → 화면이 「수집기 없음」으로 그린다 | ✅ |
| A-16 | outbox (`SYSTEM_RELOAD`) | `discover_and_load_collectors()` | 5초 폴링 | outbox 이벤트 | `event_type == "SYSTEM_RELOAD"` (🔴 **리터럴**), `ORDER BY id DESC LIMIT 1`, **`processed_chain` 필터 없음** — 진도는 **메모리 안** `last_reload_event_id` | 1 | 🔊 INFO 두 줄(감지·재스캔 완료) | ✅ / ⚠️ 커서가 프로세스 로컬이라 **스케줄러가 죽어 있던 동안의 리로드는 조용히 삼켜진다** |
| A-17 | `run()` | `config_backup.run_scheduled` | 벽시계 게이트 `CHECK_INTERVAL_SEC = 1800.0` | 함수 인자 → 파일 | `server/config/` 스냅샷 | 1 | 🔊 `[ConfigBackup] maintenance cycle raised: …` ERROR, 수집기를 안 죽인다 | ✅ |

### 「큐」라는 낱말이 이 흐름에서 «넷»을 가리킨다 — 둘만 큐다
```
✅ 진짜 픽업 큐   database_outbox 의 processed_chain=false + event_type ∈ SCHEDULER_OWNED_EVENT_TYPES
                 체인 워커도 같은 행을 보지만 CONTROL_EVENT_TYPES 로 «표시 없이» 건너뛴다
                 -> 이 행을 비우는 것은 스케줄러 «하나»다
✅ 보이는 큐      retroactive_runs 의 state='queued'  — (1) 과 «같은 커밋»에 쓰이는 거울
                 ⚠️ 둘은 어긋날 수 있다: _mark_run 이 실패하면 outbox 행은 소비되는데
                    실행 행은 영원히 queued 로 남는다. 그래서 record_failures() 가
                    로그가 아니라 «큐 옆의 값»으로 나간다
❌ 큐 아님        _collectors_running(set) · _retroactive_thread — 둘 다 «거절»하지 «적재»하지 않는다
❌ 큐 아님        "…to ingestion queue." 로그의 그 큐 = raws/ «디렉터리»
```

---

---

### 실측 묶음 — 거절 · 관측 · 통지 · 백업

## ⑤ 거절 → 운영자 — 실패 → 사유 → 주소 → 표본 → 화면

**한 줄:** 주소는 이제 «만들어지고 실려서 백필 결과까지» 간다. 그런데 **그 결과를 화면으로 나르는 유일한 호출자가 세 칸을 버린다.** 그리고 작성 화면 쪽은 «완전히 배선돼 있는데», 그 화면이 받기로 돼 있는 예외가 그 경로에서는 **발생할 수 없다.**

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `ledger/envelope.py:317 check_envelope` | `ledger/gate.py:602 screen_compiled_molecule` | 분자 1건마다 — `runtime_v2.py:303` 의 `for result, atoms in zip(...)` 루프 | 함수 반환값 (list[dict]) | `[{code, path, message}]` — 코드 4종 매핑은 `gate.py:387 _ENVELOPE_REASONS`, 미매핑 코드는 `REFUSE_NOT_TRUE_ALONE` 로 폴백(`gate.py:403`) | **1** — `gate.py:610` 이 `report["violation_details"]` 로 적재 | 조용 — 위반이 없으면 빈 리스트라 구분 불가. 다만 뒤 칸이 곧 시끄러워진다 | ✅ 이어짐 |
| `gate.py:610` `report["violation_details"]` | `gate.py:630-634 refuse(addresses=)` | 같은 루프, `report["refused"]` 가 참일 때 | 함수 인자 | `report.get("violation_details") or ()` — dict 리스트 그대로 | **1** — `gate.py:406 refuse` | 조용 — `or ()` 라 빈 튜플이 되고 거절 자체는 그대로 발생 | ✅ 이어짐 |
| `gate.py:427 _record(addresses=)` | `gate.py:232 _samples` (프로세스 전역 list) | 매 거절 | 모듈 전역 상태 | `{source, reason, atoms, rows, detail, addresses:[{code,path}]}` — **`code`·`path` 만 추림**(`gate.py:365`), 상한 `MAX_REFUSAL_SAMPLES=20`(`gate.py:210`) | **1** — `gate.py:255 samples()` | 조용 — 21번째부터 «말없이» 안 담긴다. 다만 잘림 여부는 다음 칸이 수로 낸다 | ✅ 이어짐 |
| `gate.py:255 samples()` · `gate.py:235 refusals()` | `ledger/backfill.py:544-547` 실행 결과 dict | `backfill.run()` 종료 직전 (매 실행 1회) | 함수 반환값 (dict) | `refused_total`(int) · `refused_samples`(list) · `refused_samples_capped`(bool) — 잘림을 «수 두 개»로 말한다 | **0 (운영)** — `server/` 전건 grep 에서 이 셋을 읽는 코드가 없다. 히트는 `backfill.py` 자신과 `tests/test_a_refusal_says_which_field_to_fix.py:117`(소스 텍스트 단언) 뿐 | 🔴 **완전 무음** — 값이 만들어지고 아무도 안 읽고 사라진다. 오류도 로그도 없다 | 🔴 끊김 |
| `backfill.run()` 결과 dict | `retroactive.py:387-390 _run_ledger_backfill` 반환 dict | 운영자가 어드민에서 `POST /admin/retroactive/ledger_backfill/run` | 함수 반환값 | **7칸만 통과**: `rows_read`·`batches`·`inserted`·`deduped`·`molecules`·`stopped`·`cursor_after`. 🔴 `refused_total`·`refused_samples`·`refused_samples_capped` 는 **여기서 버려진다** | 1 (`retroactive.py:1477` → `RetroactiveRun.result` JSON) | 🔴 **무음** — 화면은 「분자 N개 만들었다」만 보고, 몇 건이 왜 거절됐는지는 «응답에 아예 없다» | 🔴 끊김 |
| `RetroactiveRun.result` | `client2/src/admin.js:2551` → 소급 실행 화면 | 어드민 소급 탭 열기 / 폴링 | HTTP `GET /admin/retroactive/runs?limit=50` (`retroactive.py:1127 runs()`) | `{run_id, op, label, params, state, processed_rows, total_rows, result, error, …}` — `result` 는 위 7칸 | 1 | 화면이 조용히 「성공」으로 읽는다 — 거절된 행이 있어도 `state` 는 성공이다 | ⚠️ 반쪽 |
| `gate.py:371-380 logger.warning/info` | 스케줄러 프로세스 stdout | 매 거절 (1·10·100·… 번째는 WARNING, 나머지 INFO — `gate.py:211 _ANNOUNCE_AT`) | 로그 | `[LedgerGate] source=%s REFUSED a source event at the door \| reason=%s \| …` | 파일 1 — 🔴 **uvicorn 이 아니다.** 소급 백필은 `run_auto_update.py:758 start_retroactive_run` 이 «스케줄러 프로세스의 별도 스레드»에서 돌린다 → `run_decoupled_app.py:330-331` 의 `log_file=paths.log_path("auto_update_stdout.log")` 로 tee 된다 | ⚠️ 조용 — 아무 화면도 그 파일을 읽지 않는다. 「로그에 찍힌다」는 참이지만 «운영자가 보는 자리»는 아니다 | ⚠️ 반쪽 |
| `gate.py:525` `report["violation_details"]` (v1 팔 `screen_molecule`) | — | — | — | 같은 dict 리스트를 «쓰기는 쓴다» | **0** — `gate.py:554 refuse(...)` 가 `addresses=` 를 **안 넘긴다**. 그리고 `screen_molecule` 자체의 운영 호출자가 **0**(히트 전부 `server/scripts/seed_syn_*.py` 6종 + 시험) | 조용 | ⚰️ 죽은 갈래 |
| `gate.py:528-530` · `gate.py:613-616` | — | — | — | `break` **뒤에** 놓인 `report.update(...)` 3~4줄 | 0 — 도달 불가 | 조용 | ⚰️ 죽은 갈래 (양쪽 팔에 같은 모양이 하나씩) |
| `backfill.py:1298` `result["gate_note"]` | CLI stderr | `python server/ledger/backfill.py --source …` | 로그 | — | **읽는 쪽 1 · 쓰는 쪽 0.** `gate_note` 는 `server/` 전건에서 이 두 줄(1298·1299)에만 있고 **어디서도 설정되지 않는다** → 이 `if` 는 항상 거짓 | 조용 | ⚰️ 죽은 갈래 |
| `gate.py:310 note()` → `observability.py:44 note()` | `heartbeat.beat("ledger", note=…)` | `backfill.py:1294 beat(result)` | 하트비트 파일 `worker_heartbeats/ledger.json` | 거절 digest 문자열 (`molecules=` / `source_rows=` / `built_atoms_discarded=` + 상위 5) | **CLI 전용.** `beat(result)` 는 `backfill.py:1223 main()` 안(1294행)에 있다 → 어드민에서 돌린 백필은 **비트를 아예 안 찍는다** | 🔴 조용 — 화면에서 돌린 백필의 거절 digest 는 «어디에도 안 실린다» | 🔴 끊김 |
| `worker_heartbeats/ledger.json` 의 `note` | `/health` 응답 | `GET /health` | HTTP JSON | `heartbeat.py:290` 이 `note` 를 읽어 entry 에 담는다 | **0** — `health.py` 의 워커 루프(`:226~:352`)가 만드는 entry 칸은 `heartbeat·supervisor_state·pid·restarts·status·detail·age_seconds·beats·error·work·stale_after_seconds·beat_pid·detail_beat`. **`note` 가 없다** | 🔴 무음 — 읽혀서 dict 에 담기고 그다음 칸에서 «조용히 떨어진다» | 🔴 끊김 |
| `POST /admin/ontology-explorer/test-run` (`ontology_config_explorer_router.py:121`) | `config_explorer_service.py:673 _test_run_refusal` | 운영자가 「시험 실행」 버튼 (`ontology_explorer.js:1110`) | HTTP body `{source_id}` → 응답 dict | `{code, path, message, form_path}` + 조건부 `rows_read`·`rows_missing`·`column`·`partial_apply` | **1** — `ontology_explorer_view.js:745 renderTestRunRefusal` | 시끄럽다 — 500 을 안 낸다(`config_explorer_service.py:618 except Exception`). 거절이 «답»으로 나간다 | ✅ 이어짐 |
| 위 응답 | 화면 픽셀 | 같은 클릭 | DOM | `form_path` 있으면 폼으로 가는 **버튼**(`map-goto`), 없으면 `path` 를 `<code>` 로. `rows_read/rows_missing/column` 셋이 다 있을 때만 「N행 중 M행 · 컬럼」. `partial_apply === false` 일 때만 「좋은 행도 안 들어갑니다」 | **1** — 그리고 «출하본에 들어 있다»: `client2/dist/assets/admin-eErqdtgQ.js` 에 `oe-testrun-refusal` · `form_path`(2) · `rows_missing`(1) · `partial_apply`(1) 존재 | 시끄럽다 | ✅ 이어짐 |
| `gate.py:122-123 MoleculeRefused.code/.path` | `_test_run_refusal` 의 `getattr(exc,"code")` | — | 예외 속성 | 첫 주소의 `code`·`path` | **0 (이 경로에서 도달 불가)** — 아래 ⚰️ 근거 참조 | — | ⚰️ 죽은 갈래 |
| `gate.py:275 captured()` | — | — | contextmanager | 프로세스 카운터를 격리해 미리보기가 라이브 거절 총계를 오염시키지 않게 함 | **0 (운영)** — 히트는 `tests/test_ledger_admin_setup.py:240·254` 뿐. `ledger/dry_run.py:190 preview()` 는 «첫 실행 문장에서 `DryRunUnavailable` 을 raise» 하므로 그것을 부를 자리 자체가 없다 | — | ⚰️ 죽은 갈래 |

### ⚰️ 근거 — 「게이트 거절은 시험 실행 화면에 도달할 수 없다」

`MoleculeRefused` 는 `gate.py:428 molecule_is_open()` 이 참일 때만 raise 된다. 그 스코프를 여는 자리는 **`server/ledger/runtime_v2.py:306` 하나**(`server/ledger/` 전건 grep).

```
시험 실행   test_run → backfill.preview_first_batch(:904)
           → setup.preview_selected_cursor_batch(:191)
           → runtime_v2.preview_cursor_batch(:72)      <- `_screened_atoms` 를 «안 부른다»
백필 실행   backfill.run → execute_selected_cursor_batch(:208)
           → runtime_v2.execute_cursor_batch(:115) -> `_screened_atoms`(:146) -> building_molecule(:306)
```
`_screened_atoms`(`runtime_v2.py:293`)의 호출자는 `:146`·`:226` 둘뿐이고 **둘 다 execute 계열**이다. 즉 미리보기는 게이트를 통과하지 않으므로 `MoleculeRefused` 가 나올 수 없고, `gate.py:109-114` 가 이 리더를 위해 붙인 `code`/`path` 는 이 경로에서 한 번도 쓰이지 않는다. (백필 경로에서는 raise 되지만 그쪽 리더는 `_test_run_refusal` 이 아니다.)

### ⚠️ 낡은 서술 (「상태」에 기록해야 할 발견)

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| `gate.py:256` docstring | 「…for the report and for **`/health`**」 | `/health` 는 게이트를 **안 읽는다**. `health.py:432-443` payload 의 `checks` 는 `database·workers·outbox·supervisor·config_backup` 다섯뿐 |
| `gate.py:146` docstring | 「With **`backfill.run`** holding the `with`」 | 실제 스코프 보유자는 `runtime_v2.py:306`. 같은 드라이버 밑이라 결론은 유효하지만 **이름이 낡았다** |
| `SYSTEM_FLOWS.md` §0 표 「거절 주소 — 캐리어 3, 읽는 쪽 0」 | 고쳐진 것으로 읽히기 쉽다 | 절반만 고쳐졌다: 작성 화면 팔은 ✅, 백필 팔은 캐리어가 «하나 더 늘고» 읽는 쪽은 **여전히 0** |

---
## ⑥ 관측 — 프로세스 → 심박/명부 → `/health` → 화면

**한 줄:** 서버 쪽은 이 저장소에서 가장 촘촘하게 지어진 흐름이다 — 그리고 **마지막 칸이 없다.** `/health` 를 읽는 화면이 «하나도» 없다.

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| 워커 루프 | `utils/heartbeat.py:157 beat(name)` | 루프 반복마다 (워처 3.0s · 체인 2.0s · 스케줄러 5.0s) | 파일 `<config>/worker_heartbeats/<name>.json`, `os.replace` 원자적 | `{ts, pid, beats, note, work{…}}`, 200B, 초당 1회 상한(`:83`) | 1 (`read_all`) | 🔴 **아무것도 안 울린다 — 의도다.** 디스크 오류를 전부 삼키고 카운트만 한다(`:157` docstring): 모니터링이 새 장애 모드가 되면 안 되므로. 부재는 다음 칸이 판정 | ✅ 이어짐 |
| 런처 `run_decoupled_app.py:351` | `heartbeat.py:327 write_roster` → `_roster.json` | 부팅 1회 (`Supervisor` 생성 직전) | 파일 | `{"written_at": t, "processes": {name: t}}` — 실측 이름 **셋**: `watcher`·`chain`·`scheduler`. 🔴 **웹서버는 `heartbeat=` 가 없어 명부에 «없다»**(`:310-314`), 데스크톱도 없다 | **1** — `health.py:219 _hb.read_roster()` | 시끄럽다 — 실패 시 WARNING 한 줄(`run_decoupled_app.py:355`) 후 «디스크 폴백». 명부가 비면 「존재하는 비트 전부」로 떨어진다(`health.py:220-221`) | ✅ 이어짐 |
| `process_supervisor.Supervisor.write_status` | `<config>/supervisor_status.json` | 1초 폴 / 5초 강제 갱신 (`STATUS_REFRESH_SEC`) | 파일 | `{supervisor_pid, updated_at, children{…state, restarts, pid, last_exit_code, failure_reason, correlated_with, correlated_retries, **terminal_verdict**}, failed_children, correlated_children}` | 1 (`main.py:262 _supervisor_mod.read_status()`) | 시끄럽다 — `updated_at` 이 감독자 자신의 생존 신호. 낡으면 `health.py:174-181` 이 UNHEALTHY + 문장 | ✅ 이어짐 |
| `supervisor_status.json` 의 `terminal_verdict` | `/health` 응답 | — | — | `broken_child` / `port_conflict` (`process_supervisor.py:867`, 스냅샷 `:1069`) | **0** — `health.py:158-167` 의 `sup_check["children"]` 이 복사하는 칸 7개에 **없다.** `server/*.py`·`client2/src/*.js` 전건에서 이 값으로 분기하는 코드 0 | 🔴 무음 — 「포트를 누가 점유했다」는 판정이 파일에만 앉는다 | 🔴 끊김 |
| `heartbeat.read_all` + `read_status` + `read_roster` + DB/outbox 프로브 | `health.py:107 compute_health` | `GET /health` 요청마다 | 함수 인자 | 워커 판정 = 감독자 뷰 × 비트 뷰 조인. `expected` 결정 순서 **감독자 → 명부 → 디스크**(`:213-221`), `uptime` 없으면 명부 시작시각에서 채움(`:229`) — 이 한 줄이 재기동 503 이었다 | 1 | — | ✅ 이어짐 |
| `compute_health` | HTTP 응답 | `GET /health` (`main.py:238`, 게이트 **없음** — 의도) | HTTP JSON + 상태코드 | **실측 페이로드**(`health.py:432-443`): `{status, checked_at, problems[], checks:{database, workers, outbox, supervisor, config_backup}}`. `workers.<n>` = `heartbeat·supervisor_state·pid·restarts·status·detail·age_seconds·beats·work·stale_after_seconds`(+상황별 `error`·`beat_pid`·`detail_beat`). `status ∈ ok\|degraded\|unhealthy`, unhealthy 만 503(`:444`) | 아래 두 행 | 라우트가 catch-all 아래로 밀리면 `index.html` 을 200 으로 답한다 — `tests/test_health_endpoint.py` 가 그것을 막는다 | ✅ 이어짐 |
| `GET /health` | **화면** | — | — | — | 🔴 **0** — `client2/src` · `client2/*.html` 전건에서 `/health` 를 부르는 코드가 **없다.** `api.js:38 checkServerHealth()` 는 이름과 달리 **`${API_BASE}/tables` 를 친다**(`api.js:39`) | 🔴 **완전 무음.** 워커 wedged · 감독자 사망 · outbox 백로그 · 미전달 브로드캐스트 — 이 판정 전부가 «운영자 화면에 도달하는 경로가 없다» | 🔴 끊김 |
| `GET /health` | 데몬 기동 배너 | 데몬 부팅 **1회** — `chain_ingestion_worker.py:1629` · `run_watcher.py:317` 의 `startup_lines(...)` → `internal_event_client.py:241 check_api_reachable` | 로그 | 판별자는 상태코드가 아니라 **BODY**(`own_health_payload`, `:218`): `status` 키 + dict 인 `checks` 가 있으면 WARNING(앱이 살아 있고 스스로 unhealthy), 없으면 ERROR(앞단) | 파일 (`*_stdout.log`) | ⚠️ 조용 — 기동 시 1회뿐이라 «떠 있는 동안» 나빠지는 것은 이쪽으로 안 나온다 | ⚠️ 반쪽 |
| 어드민 「파이프라인 헬스 스트립」 | 화면 | **없다 — `admin.js:4555 refreshHealthStrip` 의 호출자가 0** (히트는 정의 1줄과 `:538` 주석뿐) | HTTP | 🔴 `/health` 와 **무관**. `admin.js:4650` 주석이 자기 입으로 적었다 — 「기존 API만 조합: `/admin/file-ingestion/failed` · `/admin/outbox/failed` · `/admin/auto-update/status` · `/enrichment/rules`」 | 0 | 실패 경로가 카드를 `'loading'`+`'상태 조회 실패'` 로 두지만, 그 함수가 안 불린다 | ⚰️ 죽은 갈래 |
| 같은 스트립 | 픽셀 | — | DOM | — | 0 | `admin.js:539` — `healthStripEl.style.display = 'none';` ⚠️ **결함이 아니라 소유자 판정이다** — `:536-538` 「소유자: 「띄 다 빼」(2026-09-05). 카드 넷이 하던 일 둘 중 «이동»은 탭 바가 이미 하고, «수»는 각 탭의 절이 다시 말합니다. 마크업과 `refreshHealthStrip` 은 남깁니다 — 되돌리는 것이 한 줄이어야 하기 때문입니다」 | ⚰️ 의도된 죽은 갈래 |
| `heartbeat.work_claim` | `/health` `checks.workers.<n>.work` | 파일 인제션 1건을 `with` 로 감쌈 (`directory_watcher` 2곳) | 하트비트 파일의 `work` 블록 | `{open, what, no_progress_seconds, held_seconds, stalled, stall_after_seconds}` — 나이가 아니라 **절대 타임스탬프**를 publish 해서 독자가 «지금»에서 잰다 | 1 (`health.py:337-352`) | 시끄럽다 — `stalled` 면 UNHEALTHY + 문장. 「루프는 도는데 일이 안 간다」를 잡는 유일한 축 | ✅ 이어짐 (단 마지막 칸은 위와 같이 화면 0) |

### 이 흐름에서 「끊기면 시끄러운가」의 진짜 답

```
서버 안쪽   촘촘하다 — 판정 하나하나에 문장이 붙고, 모르면 「모른다」로 답한다
경계        /health 는 JSON 도 상태코드도 정직하다
화면        «없다». 이 제품의 어떤 화면도 /health 를 부르지 않는다
=> 이 흐름의 청중은 «외부 모니터»뿐이고, 저장소 안에 그 모니터를 세우는 것은 없다
```

---
## ⑦ 통지 — 쓰기 → 브로드캐스트 → WebSocket → 화면 델타

**한 줄:** 이름은 양쪽이 «정확히» 맞는다(집합 차 0). 어긋나는 것은 **페이로드 칸**이다 — 같은 이벤트가 발신 자리마다 다른 칸 수로 나가고, 잘림을 알리려고 만든 칸들은 읽는 쪽이 0 이다.

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `database/database.py:128 auto_stage_database_outbox` | `database_outbox` 행 | ORM `before_flush` — 동적 행의 new/dirty/deleted | DB 행 (같은 트랜잭션) | `stage_event`(`:263`) 또는 `stage_collapsed_event`(`:205`). 축약은 명시 opt-in(`request_outbox_mode`), 켜는 곳 둘 | 2 (체인 워커 · 스케줄러) | 리스너가 이중 등록되면 **×2 중복**(과거 실측 중복 그룹 126만). 그물 `tests/test_contention_fixes.py` | ✅ 이어짐 |
| `database.py:311 _notify_outbox_once` | PostgreSQL 채널 | 같은 flush, 트랜잭션당 1회 | `NOTIFY` | 실측 SQL: `text("NOTIFY outbox_event;")` (`:337`). 래치 `_OUTBOX_NOTIFY_SENT`(`:90`), 해제는 `after_transaction_end`(`:93`)이되 **`SUBTRANSACTION` 제외**(`:122-123`) | 1 (`OutboxListener`) | 🔴 **완전 무음** — `:331`·`:339-341` 이 `except Exception: pass`. NOTIFY 유실의 증상은 데이터 유실이 아니라 «2초 폴백 폴링» | ⚠️ 반쪽 |
| `chain_ingestion_worker.py:286 _dispatch_broadcasts` | `POST /internal/events/broadcast` | 배치의 모든 그룹 커밋 «직후» 인라인 `await`(`:1353`) | HTTP | `post_event_async`(`:176`) → `.post(...)`(`:191-193`). 세션은 `internal_event_client.internal_event_session()`(`trust_env=False`, `:90`). ⚠️ **타임아웃은 상수가 아니라 인라인 리터럴 `timeout=3`**(`:192`) — 워처 쪽은 `timeout=5`(`run_watcher.py:91`)로 «다르다» | 1 | 시끄럽다 — `logger.error` 2종(`:203-205` 상태코드 + `admin_auth.internal_event_failure_note` 로 «누가 거절했는지», `:209` 전송예외), 그리고 **아무것도 raise 안 한다**(`:206`·`:210` 이 `False` 반환) | ✅ 이어짐 |
| 통지 실패 | `broadcast_at` 이 NULL 로 «남음» | 위 실패 | DB 행 (부재) | `_stamp_broadcast_at_sync` 가 `if all_ok and event_ids:` 로 가드(`:314`) → 안 찍는다 | 1 (`sweep_undelivered_broadcasts:1357`) | 🔴 **체인 워커는 `record_undelivered_notification` 을 «부르지 않는다»**(그 파일 히트 0). durable 신호가 «부재»(`broadcast_at IS NULL`)라는 것이 설계다 — 그래서 스윕이 멎으면 아무것도 안 말한다 | ✅ 이어짐 (⑥의 `undelivered_oldest_age_seconds` 가 그 사각을 메운다) |
| `run_watcher.py:78 post_event` 실패 | `database_outbox` 마커 행 | 워처 통지 실패 | DB 행 | `internal_event_client.py:135-147`: `event_type="BROADCAST_RECOVERY"` · `status="SUCCESS"` · `processed_chain=True` · `broadcast_at=NULL` · payload `{endpoint, reason[:500], marker}` — **실패한 통지의 페이로드는 «복사하지 않는다»** | 1 (같은 스윕) | 시끄럽다 — 못 쓰면 ERROR 한 줄 + `False`, 절대 raise 안 함(`:150-161`). ⚠️ 단 `table_name` 이 없으면 **말없이 bail**(`run_watcher.py:70-72`) | ✅ 이어짐 |
| `event_constants.py:300-302` 미전달 마커 3종 | 쓰는 쪽 / 줍는 쪽 | — | 상수 | `UNDELIVERED_MARKER_STATUS="SUCCESS"` · `_PROCESSED_CHAIN=True` · `_TAG="undelivered_notification"` | STATUS **2**(`internal_event_client.py:145` 쓰기 / `chain_ingestion_worker.py:1383` 줍기) · PROCESSED_CHAIN **2**(`:146` / `:1382`) · **TAG 1 — 쓰기뿐**(`:144`). 스윕 필터(`:1381-1386`)는 `payload["marker"]` 를 «안 본다» | — | ⚠️ 반쪽 — 철자를 묶은 것은 옳고, `TAG` 만 여전히 「쓰고 아무도 안 읽는」 칸이다 |
| `broadcast_at` | — | — | — | 상수 묶음에 **일부러 없다**(`event_constants.py:298-299`) — 쓰는 값이 아니라 «줍는 쪽이 찾는 부재» | — | — | ✅ 의도된 부재 (이름을 주면 누군가 «쓰게» 된다) |
| `main.py:5839 POST /internal/events/broadcast` | `ConnectionManager.broadcast` | 위 POST | HTTP → WS | 🔴 **`payload: dict = Body(...)` — 모델 없음.** 캐시 무효화 → 인제션 진행 반영 → `created_logs` 를 **제자리에서 `[:MAX_NOTIFY_CREATED_LOGS]` 로 절단**(`:5870-5871`) → `json.dumps` → 팬아웃. `event` 키를 **검증도 재작성도 안 하는 순수 릴레이** | 1 (`main.py:566 manager`) | 게이트 있음(`Depends(require_admin_token)`). 실패는 HTTP 오류로 발신자에게 돌아간다 | ✅ 이어짐 |
| `main.py:540 ConnectionManager.broadcast` | 브라우저 | 메시지 1건 | WebSocket `/ws`(`main.py:3140`) | `send_text` 순회, 실패한 소켓은 `failed_connections` 로 모아 루프 뒤 정리(`:556-564`) | N (접속 클라) | ⚠️ `/ws` 에는 **`dependencies=` 도 인증도 없다** — `/internal/events/*` 넷은 전부 게이트인데 나가는 쪽만 열려 있다 | ⚠️ 반쪽 |
| 서버 이벤트 이름 6종 | `client2/src/websocket.js:305 handleWebSocketMessage` | WS `onmessage`(`:294`) | WS JSON | `batch_refresh_required` · `batch_row_upsert` · `batch_row_delete` · `batch_row_create` · `file_ingestion_completed` · `file_ingestion_progress` | **6 / 6 — 집합 차 «양쪽 다 0»**(`:306·317·366·382·464·479`). 출하본도 일치(`dist/assets/main-M6juM_wA.js` 에 6종 전부) | 시끄럽다 | ✅ 이어짐 |
| 같은 메시지 | 그리드 델타 | — | — | 🔴 **뒤 네 갈래는 `msg.table_name === state.currentTable` 이 아니면 도달 불가**(`websocket.js:361`), `state.gridApi` 없으면도(`:362`). `created_logs` 만 그 관문 «앞»에서 소비(`:342-358`) | — | 조용 — 다른 표를 보고 있으면 통지가 «정상적으로» 버려진다(설계) | ✅ 이어짐 |
| `main.py:3018 deleted_row_ids_omitted` | 화면 | `PUT /data/updates` 의 삭제 id 가 `BROADCAST_ITEM_LIMIT` 초과 | WS `batch_refresh_required` | 잘린 개수(int). 발신 자리 **1곳뿐**(`:3001` 분기 안) | 🔴 **0** — `client2/` 전건(`src`+`dist`) 히트 0. 그리고 `batch_refresh_required` 핸들러(`websocket.js:479-485`)는 **`event` 말고 아무 칸도 안 읽는다**(캐시 클리어 + 이력 리로드만) | 🔴 무음 — 「잘렸다는 사실을 같이 보낸다」가 발신까지만 참이다 | 🔴 끊김 |
| `total_log_count` | 화면 | 대량 tx | WS | 발신: `chain_ingestion_worker.py:1092·1102` · `main.py:5828`. **`main.py` 의 `batch_row_upsert` 5곳 전부에 없다** | 🔴 **0** (`client2/src` 히트 0) | 🔴 무음 | 🔴 끊김 |
| `change_count` | 화면 | 모든 refresh | WS | 발신 자리마다 있음(스윕은 하드코딩 `0`, `:1437`) | 🔴 **0** — 위와 같은 이유(핸들러가 안 읽는다) | 조용 | 🔴 끊김 |

### 같은 이름, 다른 칸 — 실측

```
batch_row_upsert        발신 6곳 · 칸 집합 «셋»    7칸(체인) / 7칸(main 3044, total_log_count 없음) / 4칸 / 5칸
batch_row_delete        발신 6곳 · 칸 집합 «셋»    4칸(체인) / 3칸 / 5칸
batch_refresh_required  발신 9곳 · 칸 집합 «넷»    4칸(omitted 팔) / 3~4칸(created_logs 조건부) / 6칸(체인) / 3칸(스윕)
```
🔴 **그리고 `created_logs` 를 «통째로 버리는» 가드가 넷 있는데(`main.py:436·3035·3467·3534·5609`, `<= 5000`) 버렸다는 수를 아무도 안 싣는다.** `deleted_row_ids_omitted` 가 없애려던 침묵과 «같은 모양»이 한 층 위에 그대로 있다.

⚠️ `event_constants.py:125` 의 주석이 `MAX_AUDIT_VALUE_TRUNCATION_SUFFIX` 를 상수처럼 부르는데 **그 이름은 파일에 없다**(`truncate_audit_value` 가 f-string 으로 인라인, `:268`·`:277-279`).
⚠️ WS 이벤트 이름 6종은 `event_constants.py` 에 **하나도 없다** — 발신 자리마다 맨 문자열이다. 자체 재측정(`"event": "<이름>"` 전건, 시험·`_archive` 제외): `batch_refresh_required` **9** · `batch_row_upsert` **6** · `batch_row_delete` **6** · `batch_row_create` **1** · `file_ingestion_completed` **3** · `file_ingestion_progress` **1** = **26곳**. ⑦의 「경계 계약」이 공유 심볼로 묶여 있지 않다 — 미전달 마커 3종이 `event_constants` 로 모인 것과 «정반대»의 상태이고, 그 마커를 모은 사유(「한쪽이 바뀌면 오류 없이 안 주워진다」)가 여기 26곳에 그대로 적용된다.

---
## ⑩ 백업·복원 — «있는지부터»

**답: config 는 «있다»(단 복원은 CLI 전용) · 데이터베이스는 «없다».**

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `run_auto_update.py:995 maybe_backup_configs` | `config_backup.py:411 run_scheduled` | 스케줄러 루프 5초 틱 → 1800초 게이트(`run_auto_update.py:714`) → 디스크 기준 7일 기한(`config_backup.py:357 due`) | 함수 호출 | 「신선도를 cron 슬롯이 아니라 디스크 최신 스냅샷 나이로 판정」 — 놓친 주가 다음 틱에 자가 치유 | 1 | 예외를 삼킨다(`run_auto_update.py:719-722`) — 백업 실패가 수집기를 죽이지 않게. 부재는 `/health` 가 판정 | ✅ 이어짐 |
| `config_backup.py:285 take_snapshot` | `<DATA_ROOT>/config/backup/<stem>_<yymmdd>[a-z].json.bak` | 위 | 파일 (`shutil.copy` → `os.replace`, `:338-339`) | 바이트 동일하면 «안 쓴다»(`_same_bytes:253`). FIFO 31일 + 최신 4개 바닥(`RETENTION_MIN_KEEP=4`) | 3 (`run_scheduled` · `probe` · CLI) | 조용 | ✅ 이어짐 |
| `config_backup.py:366 probe` | `health.py:80 probe_config_backups` | `GET /health` (60초 캐시, `health.py:70`) | 함수 반환값 | `ok\|missing\|stale\|unknown` + detail. import 실패·예외는 **`unknown`** — 확인 불가를 이상 없음으로 내지 않는다 | 1 (`health.py:419`) | 시끄럽다 | ✅ 이어짐 |
| `health.py:420-430` | `/health` `checks.config_backup` | 위 | HTTP JSON | `missing`/`stale`/`unknown` → `escalate(STATUS_DEGRADED)`(`:426`) + `problems[]` 문장. 🔴 **절대 503 이 아니다**(`:444`) — 백업 부재는 「다음 인시던트가 어려워진다」이지 「지금 장애」가 아니고, 503 이면 모니터가 멀쩡한 스택을 재시작한다 | 위 ⑥ 참조 | 🔴 **무음** — 상태코드로는 안 보이고 200 안의 문자열이다. 그리고 그 문자열을 읽는 화면이 **0** | 🔴 끊김 (마지막 칸) |
| `/health` `checks.config_backup` | 화면 | — | — | — | **0** — `client2/` 전건에서 `config_backup` 도 `/health` 도 히트 0 | 🔴 무음 | 🔴 끊김 |
| `scripts/backup_config.py:92 cmd_restore` | 라이브 `config/<stem>.json` | **사람이 CLI 를 친다.** 그것뿐 | 파일 | ① 스냅샷 이름 검증(`_parse`, 아니면 exit 2) ② 되돌리기 전 사본 `<name>.prerollback.<ts>` ③ **기본이 dry-run** — `--yes` 없으면 아무것도 안 쓴다(`:123-125`) ④ 🔴 **in-place `open(dest,"wb")`, `os.replace` 를 «일부러» 안 쓴다**(`:127-132`) — 원자적 rename 은 config watcher 의 `on_modified` 를 «안 깨우기» 때문 | 1 (사람) | 시끄럽다 (종료코드 + 문장) | ✅ 이어짐 (단 트리거가 사람뿐) |
| 복원 | HTTP 라우트 | — | — | — | **0 — 없다.** `server/` 에서 `(backup\|restore\|rollback\|snapshot)` 경로를 등록하는 라우트 데코레이터 **0건** | — | 🔴 **없음** |
| 복원 | UI 컨트롤 | — | — | — | **0 — 없다.** `client2/` 히트는 낙관적 UI 상태 되돌리기(`admin.js:2458·3191`) 와 시험 헬퍼뿐 | — | 🔴 **없음** |
| 복원 절차 | 운영자 | 사람이 문서를 편다 | 문서 | `docs/guide/ROLLBACK_PROCEDURE.md` §3.1-bis(`:115~`), 실행 줄 `:205-206`. 「깨진 파일은 자동으로 `.prerollback.<ts>` 로 남으므로 증거를 잃지 않는다」(`:203`) | 1 (문서) | — | ✅ 이어짐 (수동) |
| **DB 백업** | — | — | — | — | **없다.** `pg_dump\|pg_restore` 저장소 전건 히트 **2** — 하나는 문서의 수동 한 줄(`docs/guide/POSTGRES_OPERATIONS_GUIDE.md:267`), 하나는 마이그레이션 **주석**(`drop_redundant_layering_indexes.py:215`). 스크립트·스케줄러 잡·헬스체크 **0** | — | 🔴 무음 — `/health` 에 DB 백업 축이 «아예 없다» | 🔴 **없음** |
| **`ingestion_workspace/` 백업** | — | — | — | — | **없다.** `run_auto_update.py:125` 의 `shutil.copy2` 는 `raws/` 로의 인제션 «이동»이지 스냅샷이 아니다 | — | 조용 | 🔴 **없음** |

### ⑩ 의 나머지 `.bak` 쓰는 자리 — 전부 config 파일 한 겹

| 쓰는 곳 | 지키는 것 | 트리거 |
|---|---|---|
| `config_backup.py:338` | `config/*.json` 전부 | 스케줄러 7일 |
| `scripts/backup_config.py:117` | 덮어써질 라이브 config (증거) | CLI restore |
| `ledger_admin.py:738-744` | 어드민 화면으로 저장되는 config·mapper — 「이것이 유일한 undo 기제」라고 자기 주석이 선언(`:734-736`) | 어드민 저장 |
| `ledger/config_drafts.py:775-780` | 초안 적용 전의 원장/온톨로지 config | 초안 적용 |
| `scripts/install_product_tables.py:510-521` | `--apply` 전의 `table_config.json` | 설치기 CLI |

🔴 **맵퍼·수집기 스크립트·원장·맵 데이터에는 백업 쓰는 자리가 없다.**
⚠️ 이 저장소의 문서가 이미 같은 말을 하고 있다 — `docs/process/PRODUCTION_READINESS.md:194` 「**PostgreSQL 정기 백업**: 없다.」 즉 ⑩은 «몰라서 빈 칸»이 아니라 **알고 비워 둔 칸**이다. 이 표가 더하는 것은 그 부재가 **`/health` 에도 축이 없다**는 사실 하나다.

---

---

### 실측 묶음 — 원장→화면 · 작성 · 맵 편집

## ② 원장 → 화면 (원자 → walk → 클라 모델 → 좌석/부품)

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `ledger_events` 테이블 | `ledger_api/ledger_subgraph.py::SqlEvidenceLookup.claims_for_entities` (~205) | `subgraph()` 의 홉 루프가 프론티어마다 호출 | SQL (psycopg, `jsonb_to_recordset` 프론티어) | `frontier`(=`[{type,keys}]` JSONB) · `fetch`=limit+1 · **`follow` 가 있으면 `e.predicate = ANY(%(follow)s)` 로 WHERE 절에 들어간다**(~236). direction 이 `outgoing`/`incoming`/`both` 에 따라 UNION 팔 1~2개 | 1 — `ledger_subgraph.subgraph()` (~774) | 🔊 **시끄럽다.** 관계 부재는 `_relation_absent()` → **503 + `{reason:"ledger_relation_absent", state:"absent", relation, message:"원장 테이블 … 마이그레이션 미실행"}`. 컬럼/인덱스 넷 중 하나라도 없으면 `_subgraph_contract_state` → **503 + `missing:[…]` + 실행할 명령 문자열** | ✅ |
| `ledger_trace_router.py::evidence_subgraph` (`GET /api/ledger/subgraph`, 84) | `ledger_subgraph.subgraph()` (774) | 브라우저 HTTP GET | 함수 인자 | 받는 쿼리 **아홉**: `id`(필수) · `hops`(기본 **12**, 1–40) · `direction`(기본 **both**) · `node_limit`(기본 **400**) · `edge_limit`(기본 **1200**) · `positive[]` · `negative[]` · `follow[]` · `backbone_hops`. `follow` 는 `_split_follow` 로 `이름:키` 를 갈라 `follow_keys` 로 따로 나른다 | 1 | 🔊 선언에 없는 술어는 **422 `{reason:"predicate_not_declared", unknown:[…], declared:[…]}`** — 빈 그래프로 답하지 않는다. 씨앗이 못 지니는 키는 **422 `subgraph_request_invalid`** | ✅ |
| `ledger_subgraph.subgraph()` | HTTP 응답 | 같은 요청 | JSON 바디 | 최상위 키 **열셋**: `schema_version:3` · `state` · `generated_at` · `seed` · `nodes[]` · `edges[]` · `seeds[]` · `propagation` · `walk{mode,direction,start{positive,negative},hops_requested,hops_reached,claims_scanned,actions_scanned,enrich_actions,raw_claims,resolver_applied}` · `limits{nodes,edges,claims,actions,max_hops}` · `truncated{depth,nodes,edges,claims,actions,reason}` · `message` (1217) | 2 클라 경로 — `api.js::subgraphModel`(499) · `api.js::createWalkBoxWalk`(1712) | 🔊 `state:"empty"` + `message` 문장. 예산 절단은 `truncated` 로 «별도» 표기 | ✅ |
| `rnd_board/main.js` 좌석 선언(`BOARD`) | `rnd_board/main.js::bindLoaders` (~649) | 부팅 시 `boot()` 1회 | 함수 인자 | 좌석의 다섯 칸만 «질문»으로 올라간다(676–687): `follow` · `direction` · `hops` · `node_limit` · `backbone_hops`. 적힌 것만 실린다 — 빈 선언이면 `walkHere === walk` | 1 (`createWalk` 로 감싼 `walkHere`) | 🔇 **조용.** 좌석이 칸을 빠뜨리면 서버 기본값이 먹는다. 오류도 로그도 없다 | ✅ |
| `api.js::createWalk`(1516) / `COLLECTS`(1434) | `api.js::fetchSubgraph`(337) | 부품의 `this.walk(spec)` 또는 `bound.load()` | 함수 인자 | `{start, collect, ...rest}` 로 갈라 `collect` 가 없으면 `WALK`(=`fetchSubgraph`). 같은 key 는 `inflight` Map 으로 합류. **선언 안 된 `collect` 는 빈 답이 아니라 `Promise.reject`** | 7 좌석 경로 | 🔊 `walk: 선언되지 않은 collect — {name}` 로 reject → 부품이 `refused` 로 그린다 | ✅ |
| `api.js::fetchSubgraph` | `GET /api/ledger/subgraph` | 위와 같음 | HTTP 쿼리스트링 | 실제로 조립되는 것(340–398): `id` · `positive[]` · `negative[]` · `node_limit`(있을 때) · `hops`(있을 때) · `backbone_hops`(있을 때) · `follow[]` · `direction`(있을 때). **`edge_limit` 은 «한 글자도» 안 실린다** | 서버 1 | 🔊 씨앗 없음/스탬프 id 는 요청 «전»에 막고 `{ok:false, reason:'no_seed_chosen'\|'seed_is_not_a_server_node'}` 로 되돌린다 | ✅ |
| 응답 `truncated.edges` | 어떤 클라 코드도 | — | — | 🔴 **`edge_limit` 은 `client2/src/` 전량 grep «0 히트»다.** 서버 기본 1200 이 언제나 적용된다. api.js:369–372 주석이 「이 경계가 둘(nodes·hops)을 «떨어뜨렸다» — 부품이 절단을 «부를 수는» 있는데 «더 달라고 할 수는» 없었다」고 그 결함을 적고 고쳤는데, **`edge_limit` 은 그 수리에서 빠졌다** | 0 (요청 쪽) · 배너는 `truncated.edges` 를 «이름으로» 찍는다 | 🔇 **조용한 반쪽.** 배너가 「edges 에서 잘림」을 말하지만 운영자가 올릴 손잡이가 없다 | ⚠️ |
| 응답 `truncated{}` | `api.js::truncationNames`(494) → `subgraphModel.truncated` | 응답 도착 | 함수 반환 | `Object.keys(raw).filter(k => raw[k] === true)` → 배열. **`null` 이면 `null` 을 돌려준다** (「안 왔다」 ≠ 「안 잘렸다」) | **7** — 부품 배너 2(`candidate_list_panel.js:127` · `rank_list_panel.js:121`) + api.js 재해석 5(`mapModel:1045` · `compositionFromWalk:1126` · `waferFactsFromWalk:1165` · `peerCountFromWalk:1208` · `trendFromWalk:1330`) | 🔊 `{names} 에서 잘림 — 더 있을 수 있습니다` (후보·순위표) · `이 걷기는 예산에서 끊겼습니다` (트렌드 `state:'truncated'`) | ✅ |
| `subgraphModel.truncationReason`(580) | — | — | 모델 필드 | `body.truncated.reason` 을 그대로 올린다 | **0** — 전량 grep 결과 정의 줄 «하나»뿐(`client2/src/`·`client2/tests/`) | 🔇 **조용.** 만들어 놓고 아무도 안 읽는다. 서버가 이 문자열을 바꿔도 화면이 아무 말도 안 한다 | ⚠️ |
| `walk_box_panel.js::run()`(211) | `api.js::createWalkBoxWalk`(1712) | 「걷기」 버튼 클릭 | 함수 인자 | 부품이 **네 칸**을 실어 보낸다: `{type, keys, follow?, hops?}` — `spec.hops = this.hops`(230) 는 «명시적으로» 세워지고, 소스 주석이 「hops 는 고른 경로가 «요구하는» 값」이라 그 이유까지 적는다 | 1 | — | 🔴 (다음 행) |
| `createWalkBoxWalk` 내부 | `GET /api/ledger/subgraph` | 같은 클릭 | HTTP 쿼리스트링 | 🔴 **구조분해가 «셋»이다: `const { type, keys, follow } = spec` (1716).** 조립되는 쿼리는 `id=entitySeedId(type,keys)` + `follow[]` **둘뿐**(1717–1720). **`hops` 가 여기서 «증발한다».** 화면은 `경로 A · 3홉 · wafer → …` 라고 «찍고»(`walk_box_panel.js:366`), `useRoute()`(387)가 `this.hops = route.hops` 로 «세우고», `run()` 이 «싣는데», 경계가 «버린다** → 서버가 자기 기본 `hops=12` 로 답한다. `direction`·`node_limit`·`edge_limit`·`backbone_hops`·`positive`/`negative` 도 마찬가지로 안 실린다(부품이 계산조차 안 함) | 서버 1 | 🔴 **완전히 조용.** 200 이 오고 결과가 «더 많이» 나온다. 3홉을 물었다고 화면이 말하는데 12홉 답을 그린다. 오류·로그·배너 «0» | 🔴 |
| `/api/ledger/subgraph` 응답 | `createWalkBoxWalk` 반환 | 응답 도착 | 함수 반환 | 🔴 **응답 열셋 중 «둘»만 살아남는다**: `nodes` 를 `{id, type, label}` 로 «세 칸으로 깎아» 담고 `truncated` 를 원본 객체 그대로 담는다(1732–1734). **`edges` 가 버려진다** — 걷기 검색창은 「무엇이 나왔나」는 보여 주고 「어떻게 이어졌나」는 «구조적으로» 못 보여 준다. `seed`·`seeds`·`walk`(hops_reached 포함)·`limits`·`propagation`·`state`·`message` 도 버려진다 | 1 (`walk_box_panel.this.result`) | 🔇 **조용.** 「몇 홉까지 실제로 갔나」(`walk.hops_reached`)가 응답에 «있는데» 화면이 못 받아, 위 행의 hops 유실을 화면에서 검출할 방법도 같이 사라진다 | 🔴 |
| `GET /api/ledger/declaration`(400) | `api.js::fetchDeclaration`(1687) | `WalkBoxPanel.mount()` → `loadDecl()`(159) · `ControlBarPanel` | HTTP GET(무인자) | 서버가 내는 것: `state` · `entities[{type,keys}]` · `predicates[{name,subjects,object,origin}]` · `sources[{source,relation,emits,scope_columns}]`. 클라가 읽는 것: `entities` · `predicates` · **`collect`(1698) — 서버가 «안 보내는» 키**. `sources` 는 이 경로에서 «안 읽는다**(그리드 쪽 `grid_source_label.js` 가 따로 읽는다) | 3 — `rnd_board/main.js:701`(walkBox) · `:706`(controlBar) · `walk/main.js:36` | 🔊 `{ok:false, message}` 한 모양 → 「서버가 아직 선언을 못 줍니다 — 걷기 상자는 그 답 위에 섭니다」(walk_box_panel:352). 실패는 «캐시 안 한다** | ⚠️ `collect` 는 서버에 없는 키를 읽는 잔재 — 언제나 `[]` |
| `fetchDeclaration` 결과 | `api.js::typeGraph`(1586) → `pathsBetween`(1611) → `useRoute`(387) | 도착지 드롭다운 `change` | 함수 인자 | 원장을 «한 줄도» 안 읽는다 — 선언의 `predicates[].subjects × object.types` 로 무방향 그래프를 만들고 단순경로를 «follow 집합»으로 접는다. `useRoute` 가 `this.follow = new Set(route.follow)` · `this.hops = route.hops` 를 «둘 다» 세운다 | 1 | 🔊 이어지지 않으면 「{A} 과 {B} 은 «선언상» 안 이어집니다」(351) — 「없다」와 「못 봤다」를 가른다 | ⚠️ **`follow` 만 전선을 건넌다.** 같은 함수가 낳은 `hops` 는 위 행에서 버려진다 — 「그 함수가 있나」로는 통과하고 「무엇이 지나가나」로는 반쪽 |
| `walk_box_panel::_resultBox` 행 클릭(526) | `MarkingStore`(`marking:2`) → 좌석 재걷기 | 사람 클릭 | 함수 호출 → 구독 emit | `this.mark(id, SIGN.CASE, 'replace')` → `Panel.mark`(panel.js:139)가 `markings.clear(writes)` 후 `set(...)`. 그 emit 을 `walk_box_panel.mount()`(144)의 구독이 받아 `push(outside)` 로 이력 칸을 «자식으로» 붙인다. `marking:2` 를 읽는 좌석(후보·순위·트렌드2·맵2)이 각자 `startFor()` 로 다시 걷는다 | 4 좌석(`reads:'marking:2'`) + 이력 구독 1 | 🔇 조용(정상 경로) | ✅ |
| `walk_box_panel.js::collect(nodeId, sign)`(120) | — | — | — | 저장소 전량 grep: **호출부 0** (`client2/src/`·`client2/tests/` 에서 `collect(` 히트는 «정의 줄 하나»뿐). 찍기-재걷기 고리는 위 행의 `mark()` 가 «다른 철자»로 담당한다 | **0** | — | ⚰️ 죽은 메서드 |
| `WalkBoxPanel` 이 그리는 CSS 클래스 | `rnd_board/board.css` | 렌더 | 클래스명 | 🔴 **부품이 `rb-walkbox*` 클래스 «15개»를 찍는데**(`rb-walkbox` · `-history` · `-history-head` · `-step` · `-select` · `-route` · `-note` · `-field` · `-label` · `-key` · `-follow` · `-run` · `-go` · `-result` · `rb-part-title`) **`board.css` 의 `rb-walkbox` 규칙은 «0»이다**(`grep -c` = 0). 저장소 전량에서 그 문자열을 든 파일은 `walk_box_panel.js` «하나». `dist/assets/*.css` 에도 «없다**(빌드본 확인) — 반면 `rb-part-title` 은 board.css:289 에 있다 | **0** | 🔇 **완전히 조용.** 브라우저 기본 스타일로 그려진다. `walk.html` 의 주석이 「부품의 스타일은 `board.css` 에 삽니다 — 사본을 만들면 두 화면이 달라집니다」라고 «단언하는데 그 문장이 거짓»이다. 휴대폰 타깃인데 스타일 없는 `<button>`/`<select>` 는 44px 터치 타깃에 못 미친다 | 🔴 |
| `walk.html` → `src/walk/main.js::boot` | `WalkBoxPanel` | 페이지 로드 | 생성자 인자 | `reads:'marking:1'` · `writes:'marking:1'` · `loadDeclaration` · `walk: createWalkBoxWalk(...)`. vite 엔트리 `walk` 존재, **`dist/walk.html` 빌드본도 존재** | 1 | 🔊 `#wk-host` 없으면 부팅 안 함(무해) | ⚠️ 위 CSS 행 때문에 «페이지는 서는데 모양이 없다» |
| R&D 보드 walkBox 좌석(`main.js:635`) | `WalkBoxPanel` | 부팅 | 좌석 선언 | `reads: null` · `writes:'marking:2'`. 🔴 그래서 `TablePart` 에 넘어가는 `reads`(516) 도 `null` → `Panel.signOf()` 가 «언제나 ABSENT» → **결과 표가 「어느 행이 마킹됐는지」를 보드에서는 못 그린다**. `walk.html` 은 `reads === writes` 라 그려진다 — 같은 부품, 두 화면, 다른 동작 | 1 | 🔇 조용 | ⚠️ |
| R&D 보드 walkBox 좌석 제목 | 화면 | 렌더 | 문자열 | 좌석 제목이 `'걷기 -- 타입 · 키 · 따라갈 술어 · **모을 것**'`(main.js:637). 부품이 그리는 줄은 `_typeRow`·`_keyRow`·`_destinationRow`·`_followRow`·`_runRow` 다섯 — **COLLECT 칸은 «없다»**. `frontend.md` §4 가 「COLLECT 는 2026-08-28 에 라우트에서 빠졌다 — 화면에 그 칸이 남아 있으면 결함이다」라고 적어 뒀는데, 칸은 갔고 «제목만» 남았다 | — | 🔇 조용 | ⚠️ |
| `COLLECTS.trend_y` → `fetchTrends` → `GET /api/ledger/trends` | 서버 | — | — | 🔴 **그 라우트가 없다.** `ledger_trace_router.py` 의 `@router` 는 «셋»뿐: `/subgraph`(84) · `/gaps`(353) · `/declaration`(400). 그리고 `collect:'trend_y'` 를 대는 좌석이 **0** — `main.js:218` 이 그 줄이 떠난 자리를 적고 있고, `main_trend_panel.js:85` 는 폴백을 `options.collect \|\| null` 로 «닫아 놨다** | **0** | 🔇 조용 | ⚰️ |
| `COLLECTS.map` → `fetchLotMap` · `COLLECTS.basis` → `fetchComposition` · `COLLECTS.peer` → `fetchSiblings` · `COLLECTS.wafer_process` → `fetchComposition` | 서버 | — | — | 넷 다 없는 라우트(`/lot_map`·`/composition`·`/siblings`). 도달성 실측: **`collect:'map'` 은 `if (!options.question)` 의 «else» 안에만 있고(main.js:872·877·881) — `question:` 을 선언하는 좌석이 «0»이다**(rnd_board 전량 grep, 주석 제외 0 히트) · **`decl.part==='map' && decl.collect`(811) 도 map 좌석 셋 중 `collect` 를 대는 것이 0** · **`collect:'basis'`(805) 는 `options.basisChipId` 가드 아래인데 그 옵션을 대는 좌석이 0** · `wafer_process` 는 세 부품의 «생성자 기본값»으로만 살아 있고 좌석이 `follow` 를 대는 한 `bound.load` 가 먼저 이긴다 · `peer` 는 호출부 0 | **0** (넷 다) | 🔇 조용 — grep 에는 «살아 보인다**. `slotPagesFromLotMap` 은 grep 히트 2라 살아 보이지만 그 한 호출이 죽은 갈래(881) 안이다 | ⚰️ |
| `api.js::fetchMapGrid` → `GET /tables/wafer_map_metadata/data` | `main.py:1793 @app.get("/tables/{table_name}/data")` | `map_panel` 의 `loadGrid` | HTTP 쿼리 | 원장 라우트가 «아니다** — 선언된 관계의 범용 리더. 라우트 실재 확인 | 1 (`map_panel.js:231` → `mapModel`) | 🔊 표준 표 라우트의 거절 | ✅ |

### ② 에서 나온 문서 정정 (상태 칸에 못 담은 것)

| 문서/주석 | 적힌 것 | 실측 |
|---|---|---|
| `server/ledger_trace_router.py` **모듈 docstring 1~5행** | 「The ledger read routes — **ten of them** … `subgraph`, `subgraph/table`, `siblings`, `trends`, `composition`, `selection/resolve`, `kinds`, `declaration`, `structure`, `lot_map`」 | 🔴 **`@router` 는 셋뿐**(84·353·400). 열 중 «일곱»이 없는 이름이다. CODE_MAP §5-H 는 「라우트는 «셋»이다」로 맞게 적혀 있다 — **틀린 것은 소스 주석 쪽**이고, 이 파일을 여는 사람이 제일 먼저 읽는 줄이다 |
| `CODE_MAP.md` §7-B `api.js` 표 마지막 행 | 「`main.js` 의 죽은 import — **다섯**(`fetchLotMap`·`fetchComposition`·`fetchTrends`·`fetchSiblings`·`fetchSubgraph`)」 | 🔴 **열이다.** import 문 외 히트 0인 것 실측: 위 다섯 + `trendsModel` · `subgraphModel` · `basisCountsFromComposition` · `peerCountFromSiblings` · `waferFactsFromLotMap`. 모델 변환기 다섯이 목록에서 빠져 있었다 |
| `CODE_MAP.md` §7-B 머리 | 「`api.js` **1,567줄**」(⑬) / 「1,733줄」(⑭ 정정) | `api.js` **1,739줄**(워킹트리). `walk_box_panel.js` 는 §7-B 가 **544**, `frontend.md` §4 표가 **352** 로 «서로 다르고» 실측은 **544** — frontend.md 쪽이 낡았다. `main.js` 는 §7-B 812 / frontend.md 686 / 실측 **921** — 둘 다 낡았다 |
| `walk_box_panel.js` 클래스 주석(70행) | 「쓰는 곳은 `goto` «하나»입니다. **다른 어떤 경로도 저장소에 안 씁니다**」 | ⚠️ 거짓. `_resultBox` 의 `onRowClick`(526)이 `Panel.mark()` 를 부르고 그것이 `markings.clear/set` 으로 «직접 쓴다**. 기제 자체는 성립한다(그 쓰기의 emit 을 구독이 받아 `push`→`goto` 로 되돌아온다) — 틀린 것은 «주장»이지 동작이 아니다. 다만 이 주석을 근거로 「저장소 쓰기는 한 줄」이라 진단하면 틀린다 |
| `frontend.md` §4 `api.js` 행 | 「`COLLECTS` … 일곱 중 다섯이 은퇴한 라우트를 부르는 fetch 함수로 간다」 | ✅ 참이고, **더 정확히는 그 다섯 중 «넷»이 오늘 호출부 0 이라 요청 자체가 안 나간다.** 「404 하나가 남는다」(main.js:218 주석)는 «이제 거짓»이다 — `trend_y` 도 호출부 0 이다 |

### ② 좌석 인구조사 — 「라우트가 여럿일 이유가 없다」는 **실제로 지켜지고 있다**

```
좌석 16   그중 걷기에 닿는 것 «13»  ->  전부 «같은 라우트» GET /api/ledger/subgraph
          표시 전용 «3»          markingStatus · declaration ×2 (질의를 안 낸다)
          부품 종류 «11»          같은 부품이 좌석 둘·셋으로 서는 것이 map(3)·mainTrend(2)·declaration(2)
```
✅ 늘어난 것이 «선언»이지 갈래가 아니다 — 부품 13이 한 라우트를 나눠 쓴다.
🔴 예외가 «하나**: `walkBox` 만 `createWalkBoxWalk` 라는 «두 번째 경계 함수**를 통과하고, 그 함수가 위 표의 두 🔴 를 낳는다.
   같은 라우트인데 «경계가 둘»이라, 한쪽에서 고친 것이 다른 쪽에 안 온다 — `hops` 가 정확히 그 자리다
   (좌석 `map`(main.js:481)은 `hops: 8` 을 «전선까지 보낸다**. 같은 파일, 같은 라우트, 다른 결과).

### ② 절단(truncation) 배선 — 「끝까지 이어졌나」 판정: **이어졌다. 다만 «한 경계에 모양이 셋»이다**

```
서버       truncated {depth, nodes, edges, claims, actions, reason}      한 모양
클라 ①     subgraphModel.truncated    = 배열  (truncationNames)          후보·순위·트렌드 → 배너
클라 ②     reachModel.cut             = 배열  («cut» 이라는 다른 이름)    reach_panel:165 「잘림 …」
클라 ③     createWalkBoxWalk.truncated = 원본 객체 (`.reason` 을 읽는다)   walk_box_panel:505
```
✅ **화면에 절단을 «말하는» 부품은 다섯**(candidate_list · rank_list · main_trend · reach · walk_box) — 지시서의 「다섯 소비자」는 **참**이다.
⚠️ 다만 셋이 «다른 모양»이라, 서버가 `truncated` 의 모양을 바꾸면 **셋 중 하나만 조용히 죽는다**.
   `reachModel` 이 `depth` 를 «일부러» 뺀 것은 옳다(hops=1 이 질문 자체) — 그건 이름이 다른 «이유»이지 우연이 아니다.
   그래도 세 철자가 한 경계에 서 있다는 사실은 남는다.

### ② 의 «왜 안 잡혔나» — 채점기가 그 이음매를 안 본다

```
rnd_board_walk_box_harness.mjs (464줄)   `hops` 히트 «0»
rnd_board_walk_harness.mjs     (329줄)   `hops` 히트 2 — 둘 다 픽스처 행(`evidence[].hops`)이고 쿼리 단언이 아니다
```
🔴 **부품이 `spec.hops` 를 세우는 것도, 경계가 그것을 버리는 것도 «아무도 안 잰다».** 하니스가 재는 것은
씨앗 id 의 base64url(S3 절)이지 쿼리 «전체»가 아니다. 그래서 이 결함은 「코드가 있나」로도, 「하니스가 초록인가」로도
안 보이고 **「무엇이 전선을 건너나」로만** 보인다 — 이 문서가 그 질문지인 이유 그대로다.

### ② 에서 목록이 놓친 흐름

- **선언 → 화면의 «어휘»** (`GET /api/ledger/declaration`). ②는 「원자 → 화면」인데 이 라우트는 **원장을 한 줄도 안 읽는다.** 드롭다운·타입그래프·경로 목록·그리드의 원장 라벨이 전부 여기서 나오고, 끊기면 걷기 화면 «전체»가 안 선다. ②와 ④ 사이의 «셋째» 흐름으로 세는 편이 맞다.
- **`/api/ledger/gaps`**(353) — 「선언이 있어야 한다고 말한 자리 중 원장이 비어 있는 곳」. 인자 없으면 선언만(즉시), `name=` 이면 그 하나를 «센다»(~1초). 클라 소비자 **2**: `client2/src/admin.js:2115` · `client2/src/gap_catalogue.js`. R&D 보드 쪽 소비자는 «0** — 「무엇이 비어 있나」는 어드민에만 있고 걷는 화면엔 없다.
- **선언 라우트의 «두 청중»** — `GET /api/ledger/declaration` 을 부르는 자리가 클라에 **둘**이고 서로를 모른다: `client2/src/main.js:178`(그리드의 원장 소스 라벨 — `sources[]` 를 읽는다) · `rnd_board/api.js:1691`(걷기 — `entities`/`predicates` 를 읽는다). **`sources` 와 `entities` 는 «다른 반쪽»이라 한쪽이 비어도 다른 쪽은 정상으로 보인다** — 서버가 `sources` 키를 «빼서» 답하는 갈래(setup 이 컴파일 안 될 때)가 실제로 있고, 그러면 걷기는 멀쩡한데 그리드 라벨만 「못 읽음」이 된다.
- **마킹 체인 자체**(마킹1 → walk → 찍기 → 마킹2 → walk). 부품 간 이음매가 아니라 «저장소 하나»를 통과하는데, 열 흐름 목록에는 그 축이 없다. `marking_intersection.js::intersectMarkings` 는 `boot()`(main.js:908)에서 좌석 «뒤에» 설치된다.

---
## ④ 작성(선언) — 폼 → 스켈레톤 → 검증 → 저장 → 발효

> 표면: `/admin/ontology-explorer/*` **라우트 15**(비-strict 6 · strict 9) · 클라 `ontology_explorer{,_store,_view}.js` + `ontology_skeleton.js` · `closed_list.js` · `uniqueness.js`.

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `admin.js::switchTab`(580) | `ontology_explorer.js::refreshOntologyExplorer` | 운영자가 어드민 「온톨로지」 탭 클릭 | 함수 호출(무인자) | `controller?.refresh()` → `load({allowContextSwitch:true, editorCheckpoint: state.dirty ? checkpoint() : null})`. `initOntologyExplorer`(admin.js:368)는 컨트롤러만 만들고 **적재하지 않는다** | 1 (`ontology_explorer.js:1350`) | 🔇 `controller` 가 null 이면 `?.` 가 삼킨다 — 빈 `#ontology-explorer-root`(admin.html:2148) | ✅ |
| `ontology_explorer.js::load` | `GET /admin/ontology-explorer/view` | 위 refresh · 모든 성공한 쓰기 뒤 `readMirror` | HTTP 쿼리 | `new URLSearchParams({q, page, limit:'100', view_mode})` + 조건부 `selection`·`context_token`·`draft_id`·`revision`. `mode = draft?.draft_id ? viewMode : 'active'` — 초안 없이 `draft_preview` 가 못 나가게 한 곳에서 접는다. ⚠️ 라우터가 받는 **`reference_limit` 을 클라가 한 번도 안 싣는다**(항상 서버 기본 200) | 1 (`:704`) | 🔊 throw → `REQUEST_FAILED` + 패널의 `errorSentence(error)`(토스트 아님) | ⚠️ |
| `config_explorer_service.view` | `ontology_explorer_store.js::reduceExplorerState` | `/view` 200 | HTTP JSON | 응답 12키: `items`·`nodes`·`outbound`·`used_by`·`integrity`·`changes`·`edge_changes`·`selection`·`view_context`·`draft`·`total`·`verification`. `verification` 은 `test_runs.json` 을 `definition_hash` 로 대조해 만든 `{target_key,status,ran_at,rows_read,molecules,atoms,stale}` | 2 (`store.js:178` 저장 · `view.js:742` `verificationOf`) | 🔇 키가 없으면 `p.verification \|\| {}` → 배지가 「모름」 | ✅ |
| `ontology_explorer.js::loadAuthoring` | `GET /authoring/plan?selection=` | `load` 성공 직후 `void loadAuthoring(...)` (await 안 함) | HTTP 쿼리 | `params.set('selection', selection)` 하나. 인자는 `payload.draft?.target_key ?? payload.selection?.key ?? selection ?? null` — 🔴 초안이 선택보다 이긴다 | 1 (`:768`) | 🔊 `console.warn('[ontology] authoring plan unavailable')` + `AUTHORING_FAILED` → 패널이 사유를 그린다(비우지 않는다) | ✅ |
| `config_authoring.authoring_plan` | `ontology_explorer_view.js` | 위 응답 | HTTP JSON | 반환 8키 + 서비스가 `config_source` 추가 | **6/9.** 읽힘: `steps`·`sections`·`fields`·`force_summary.grammar_requires_it`·`unattached_refusals`·`physical_schema_file`·`config_source`. 🔴 **`counts` 소비자 0**(view 가 `plan.steps` 로 재계산) · 🔴 **최상위 `refusals` 소비자 0**(행별 `row.refusals` 로 나뉘어 소비) | 🔇 조용 — 안 읽는 키라 부재가 안 보인다 | ⚠️ |
| `config_authoring.closed_lists(sources)` | `ontology_explorer_view.js` | `GET /authoring/schema` (세션 1회, `state.authoringSchema===null` 일 때만) | HTTP JSON | 🔴 **발행 키 «23»** = `setup_bundle.public_bundle_schema()` **8** + 본문 **15**. CODE_MAP 의 23 은 **맞다** | 🔴 **이름으로 읽히는 것 «11/23»** — 스켈레톤 `list:` 이름 9개가 `view.js:1822 context.schema[node.list]` 로 간접 소비 + 명시 2(`skeleton`·`authorable_kinds`). **나머지 12는 이름으로 읽는 곳 0**; 그중 7(`setup_version`·`config_file`·`physical_schema_file`·`column_universes`·`steps`·`implementations`·`tiers`)은 **어느 경로로도 도달 불가** | 🔇 조용 — 발행만 되고 화면에 안 뜬다 | ⚠️ |
| `closed_lists["tiers"]` (한국어 라벨) | 화면 | — | HTTP JSON | 서버가 `{"id":"TIER_STRUCTURAL","label":"구조적 제거"}` 꼴로 낸다 | **0** — `view.js:1203/1662/1777` 은 `row.tier` 의 **영문 id 원문**을 그대로 찍는다 | 🔇 조용 — 운영자가 `TIER_STRUCTURAL` 이라는 «배관 낱말»을 본다 | ⚰️ |
| `closed_lists["column_universes"]` | 화면 | — | HTTP JSON | `[{id, note}]` | **0** — `view.js:1271` 은 `row.universe`/`row.universe_note` 를 읽는다(`Field.to_mapping` 이 `_UNIVERSE_NOTE` 로 이미 실어 보냄, `config_authoring.py:278`). 같은 값의 두 번째 사본 | 🔇 조용 | ⚰️ |
| `closed_lists["implementations"]`(`options`·`counts`·`default`) | 화면 | — | HTTP JSON | 「기본값이 «무엇을 세어서» 나왔나」를 `counts` 로 같이 낸다 | **0** — 클라 전량 grep 히트는 무관한 주석 1건. 드롭다운은 문자열 목록인 `prepare_implementation`/`map_implementation` 만 쓴다 | 🔇 조용 — 「무엇을 세어서 나온 default 인가」가 화면에 없다 | ⚠️ |
| `config_authoring.skeleton()`(`lru_cache`) → `ledger_skeleton.json` | `ontology_skeleton.js` | `closed_lists` 가 `"skeleton": skeleton()` 으로 실어 보냄 | 파일 → HTTP JSON | **761줄** 실측. `hint` 분포: `free` 27 · **`choice` 9** · `ref` 6 · `flag` 4 · `number` 3. `list:` 이름도 정확히 **9** — `choice` 수와 일치 | 다수 (`shapeAt`/`declarationShape`/`emptyOf`; `view.js:295,446,2049` · `ontology_explorer.js:310,969`) | 🔊 안 오면 `shapeForPath` 가 null → **폼이 안 그려진다**. `closed_list.js` 의 `loaded` 판정이 「모름」과 「없음」을 가른다 | ✅ |
| 스켈레톤 `hint:"choice"` 잎 | `closed_list.js::closedListChoice` | 폼 렌더 | 함수 인자 | `closedListChoice(context.schema[node.list], text, {loaded, name: node.list})` — **이름 문자열로 인덱싱**. 클라가 목록 이름을 «하나도» 안 갖는다 | 2 (`view.js:1339` 플랜 행 `candidates` · `view.js:1822` 스켈레톤 잎). `oe-field-select` 잔존 **0** | 🔊 미도착 시 `loaded=false` → `LIST_UNREAD` 픽셀(「없음」과 다른 글자) | ✅ |
| `ontology_explorer.js::loadAuthoring` | `GET /columns?relation=` | 플랜에 `\.relation$` 로 끝나고 값이 문자열인 행이 있을 때, relation 당 1회 | HTTP 쿼리 | 🔴 **`/columns?relation=${enc(relation)}` 뿐이다.** 라우터가 받는 `combination: list[str]` 을 **클라가 한 번도 안 싣는다** → 서버의 `payload["combination"]` 이 UI 요청에서는 **항상 None** | 1 (`:800`) | 🔊 `COLUMNS_FAILED` → `stats.failed` 문장이 행 옆에 | ⚠️ |
| `column_stats` population | `ontology_explorer_view.js::renderUniqueness` | `/columns` 200 | HTTP JSON | 응답 6키: `relation`·`total_rows`·`columns`·`estimated_rows`·`ordering`·`combination` | 🔴 **1/6.** `view.js:1163` 의 `orderingVerdicts(stats?.ordering, …)` 뿐. 게다가 `renderUniqueness` 는 `row.ground.rule !== 'ordering_default_from_catalog_key'` 면 즉시 `null` — 그려지는 행이 사실상 하나 | 🔇 조용. 🔴 **라우터 docstring 이 「EXPENSIVE by design · the population counts are exact and cost one table scan」이라 선언한 그 전수 스캔의 결과가 화면에 한 자도 안 나온다** | ⚠️ |
| `column_stats.combination_uniqueness` | 화면 | 사람이 조합 지정 | — | 서버 경로는 살아 있다(`config_explorer_service.py:537`) | **0/0 — 양끝 다 없다.** 보내는 쪽 0 · 읽는 쪽 0(`stats.combination` grep 0). `uniqueness.js::uniquenessVerdict` 는 export 되지만 **외부 호출자 0** | 🔇 조용 | ⚰️ |
| 폼 입력(`edit-shape`·`edit-field`·`edit-shape-flag`·`add/remove-field-item`) | `state.editorText` | 운영자 타이핑/클릭/선택 | DOM 이벤트 → 문자열 | `JSON.parse(state.editorText)` → `setAtPath`/`deleteAtPath` → `dispatch({type:'EDITOR_CHANGED', text: JSON.stringify(next,null,2)})`. 🔴 **두 번째 저장소가 없다** — 모든 폼 조작이 저장 버튼이 보낼 «그 버퍼»를 고친다 | 1 (리듀서 `EDITOR_CHANGED`) | 🔇 `editorText` 가 falsy 면 writer 들이 조기 return — **버튼이 눌리는데 아무 일도 안 남는다** | ✅ |
| 「Save」(`view.js:672`) | `PUT /drafts/{id}` | 운영자 클릭 | HTTP 본문 | `{expected_revision: state.draft.revision, raw: state.editorText}` — 🔴 **`raw` 가 «문자열»**(서버가 `json.loads`). 폼이 계산한 값 중 `editorText` 에 안 들어간 것은 **한 개도 안 건넌다** | 1 (`:1175`, + 생성 경로 `:431`) | 🔊 `showToast(errorMessage(error),'error')` — 코드+경로+문장 | ✅ |
| `config_drafts.save`(`:426`) | `config_authoring.filled_declaration` | 위 PUT | 함수 인자 | 🔴 **저장 시점에 «유도된 값»을 문서에 실제로 앉힌다.** 규칙: `prefix = "bundle." + ".".join(steps) + "."`(끝의 점이 `user_test`/`user_test_2` 를 가른다) · `state=="derived"` 이고 `disposition!="shape"` 인 행만 · `value is None` 이면 건너뜀 · `_fill_leaf` 가 **빈 칸만 채우고 덮어쓰지 않는다**(`false`·`0` 은 답이라 안 덮음). 🔴 **채움이 프리뷰 «앞»에 있다** — 프리뷰가 채점하는 것이 파일이 들 것과 같아야 하므로 | 1 (`config_drafts.py:426`). 되읽는 쪽: `activate` 가 `record["raw"]` 를 **그대로** 파일에 쓴다(`:619`) | 🔊 안 채워지면 `missing_field` 거절문이 「채움」이라 그린 칸에 뜬다 (`validation_errors`) | ✅ |
| Save 두 번째 호출 | `POST /drafts/{id}/activate` | 같은 클릭(PUT 성공 직후, 같은 try) | HTTP 본문 | `{expected_revision: record.revision}` — 🔴 PUT 응답이 돌려준 **새 revision** 을 쓴다(`state.draft.revision` 아님) | 1 (`:1183`) | 🔊 실패해도 **PUT 은 이미 착지** — 초안은 저장됨, 파일은 안 바뀜 | ✅ |
| `config_drafts.activate` | `server/config/ontology/ledger_config.json` | 위 POST | 파일 쓰기 | `_activate_file(config_path, [(node.bundle_path, record["raw"])])` + 백업. 🔴 컴파일 실패가 쓰기를 막지 않는다 — `preview` 는 계산만 하고 판정하지 않는다 | 1 (`:619`) | ⚠️ 아래가 실패해도 **쓰기는 남는다**(주석 명시: 「THE WRITE STAYS, EVEN IF WHAT FOLLOWS FAILS」). 백업은 취하지만 자동 되돌림 아님 | ✅ |
| `config_drafts.activate` | `system_reload.reload_system_configs(db)` | 파일 쓰기 직후 | 콜백 | 🔴 **라우터가 실제로 배선한다**: `ontology_config_explorer_router.py:261` `reload_callback=lambda: system_reload.reload_system_configs(db)`(삭제 경로도 `:243`) → `ledger_authoring.skeleton.cache_clear()`·`ledger_trace.reset_walk_cache()`·`load_resolver_config(force_reload=True)`·`virtual_join_executor.reset_cache()`·`notation_norm.reset_cache()`·`models.refresh_dynamic_models(engine)`·`sys.modules` 의 `mappers.*` 제거 | 2 비시험 (`:243`·`:261`) | ⚠️ 던지면 `_refusal` 이 안 잡아 **FastAPI 500** → 클라 `요청 실패 (500)`. 파일은 이미 쓰였고 프로세스 캐시만 낡음 — **소리는 나지만 사유를 이름 대지 않는다** | ✅ |
| `system_reload` | outbox 행 + `NOTIFY outbox_event` | 위 | DB 행 + PG NOTIFY | `DatabaseOutbox(event_type="SYSTEM_RELOAD")` commit 후 `NOTIFY`. 🔴 **NOTIFY 는 bare `except:` 로 통째로 삼킨다** — 실패해도 폴러가 나중에 잡는다 | `chain_ingestion_worker.py:1698`(`SYSTEM_RELOAD` 를 `id desc` 로, 스로틀) · `run_watcher.py` 폴러. ⚠️ **원장 v2 소비자는 이 이벤트를 안 읽는다** | 🔇 NOTIFY 실패는 완전 조용(폴링이 커버) | ✅ |
| `activate` → `convergence_probe(actual_hash)` | `convergence_unproven`/`convergence_mismatch` 거절 | reload 직후 | 함수 반환 | 🔴 **운영 주입 «0».** 기본값이 `convergence_probe or (lambda expected: {"ontology-explorer-api": expected})`(`config_explorer_service.py:89`) — **자기가 받은 값을 그대로 돌려준다**. 라우터는 `OntologyExplorerService(config_root=DEFAULT_ONTOLOGY_ROOT)` 로만 만든다(`router:18`) → `consumer_hashes` 는 절대 안 비고 `mismatched` 는 절대 안 찬다 | 비시험 주입 **0** (`convergence_probe=` 를 넘기는 자리는 `server/tests/test_ontology_config_explorer.py:722,778` 둘뿐 — 규칙대로 «시험 전용»을 빼면 0) | 🔇 응답의 `runtime_convergence.status:"confirmed"` 가 **자기 입력을 «측정»으로 보고한다**. 두 거절문은 409 목록에 등재돼 있으나 운영에서 도달 불가 | ⚰️ |
| 「시험 실행」(`view.js:855`) | `POST /test-run` | 운영자 클릭 | HTTP 본문 | `{source_id: state.selection.canonical_id}` | 🔴 **호출자 1 — 있다.** `ontology_explorer.js:1120` 발신 · `view.js:855` 렌더. **CODE_MAP 이 의심하도록 지시한 「폼이 그리는데 읽는 쪽이 없다」 부류가 «아니다»** | 🔊 `TEST_RUN_FAILED` + `error.detail.code` 가 `oe-tree-why-code` 에 자기 칸으로 | ✅ |
| `test_run` 응답 | `state.testRun` | 위 | HTTP JSON | 15키 | **13/15.** 🔴 `ran_at` 소비자 0 · 🔴 `fetch_rows`(=`PREVIEW_FETCH_ROWS` 200) 소비자 0 — 「200행 중 몇」의 **분모가 화면에 없다** | 🔇 조용 | ⚠️ |
| `test_run status=="passed"` | `draft_store.root/test_runs.json` | 통과했을 때만 | 파일 쓰기 | `definition_hash` 를 키로 9키. 🔴 원장 아님 · `ledger_config.json` 안도 아님 — **선언 파일 옆의 두 번째 저장소** | 1 (`_test_runs()` → `_verification_view` → `/view.verification`) | 🔇 읽기 실패는 `except (OSError, ValueError): return {}` → 전부 `unverified` | ✅ |
| 삭제 (`deleteDeclaration`) | `GET /deletion-preview?targets=` → `DELETE /declarations/{key}` | 「삭제」 클릭 | HTTP 쿼리 ×2 | 🔴 **`context_token` 을 안 싣는다**(라우터가 받고 `stale_context` 로 거절할 수 있는 축인데 클라가 안 쓴다) | 🔴 **응답 14키 중 «1»** — `plan.unread_after` 만(`:499`). `released`·`blocked`·`retained`·`is_reset`·`sources_before/after`·`*_total` 등 13 소비자 0 | 🔴 **위험하게 조용.** `is_reset`(「소스가 하나도 안 남는다」)이 **안 읽혀서** 번들을 통째로 비우는 삭제가 `window.confirm` 에 「영향 없음」으로 뜰 수 있다 | ⚠️ |
| 컨트롤러 `review-draft`·`revise-draft`·`activate-draft`·`discard-draft` 분기 | `POST /drafts/{id}/review`·`/revise`·`/activate`, `DELETE /drafts/{id}` | (없음) | — | 네 분기가 `ontology_explorer.js:1212·1218·1227·1242` 에 살아 있다 | 🔴 **생산자 0.** 그 넷을 «만드는» 자리가 `client2/src/` 어디에도 없다(전량 grep: 소비 분기 4줄 + `client2/tests/dom_patch_harness.mjs:223` 시험 전용 1 — 규칙대로 빼면 **0**). `view.js` 의 `button(...)` 이 내는 액션은 `save-draft`(672)·`test-run`(855)·`create-draft`(870) 셋 | 🔇 조용 — 서버 라우트 넷이 서 있고 **누를 버튼이 없다**. `POST /review`·`/revise` 는 클라 호출자 0 | ⚰️ |

### ④ 에서 목록이 놓친 흐름

- **`GET /authoring/plan` 이 «두 번» 나간다.** `loadAuthoring` 이 `Promise.all` 로 필터된 플랜(`?selection=`)과 **필터 없는 전량 플랜**을 같이 부른다(`:768-773`). 뒤엣것은 「이 파일이 여기서 이미 무엇을 쓰나」 전용이고 `state.authoringAll` 에 한 번만 캐시된다. **라우트는 하나인데 질문이 둘**이라 라우트를 세면 안 보인다.
- **`filled_declaration` 은 «저장할 때 문서를 바꾸는» 유일한 자리**인데, 흐름도상 「검증」과 「저장」 사이가 아니라 **프리뷰보다 앞**에 있다(`config_drafts.py:426` → `:427`). 순서가 계약이다.
- **`test_runs.json` 이라는 두 번째 저장소.** ④의 산출물이 `ledger_config.json` «하나»가 아니다. `definition_hash` 로 걸려 있어 편집과 함께 죽는다(`stale`).
- **`system_reload` 가 스켈레톤 캐시를 비운다**(`skeleton.cache_clear()`). 즉 `ledger_skeleton.json` 을 고치면 «재기동 없이» **폼 자신의 모양**이 바뀐다 — 발효가 운영자 데이터뿐 아니라 폼에도 걸려 있다.
- **어드민 토큰이 두 갈래.** 라우트 15 중 읽기 6은 `require_admin_token`, 쓰기 9는 `require_admin_token_strict`. 클라는 `adminFetch` 하나로 둘 다 태우고 503(토큰 미설정)만 별도 토스트로 가른다(`admin.js:180`) — **strict 거부와 일반 거부를 화면이 구분하지 않는다**.

### ④ 양끝이 다 있는데 아무것도 잇지 않는 이음매 (일곱)

| # | 이음매 | 양끝 | 가운데 |
|---|---|---|---|
| 1 | `/columns` 의 `combination` 축 | 서버 인자·`combination_uniqueness` 구현·클라 판정기 `uniquenessVerdict` | 쿼리에 안 싣고 응답에서 안 읽는다. `uniquenessVerdict` **외부 호출자 0** |
| 2 | `/columns` 의 population 절반 | docstring 이 「THE NUMBERS ARE THE FEATURE」라 선언하고 전수 스캔 비용을 감수 | `columns`·`total_rows`·`estimated_rows` 를 읽는 클라 코드 **0** |
| 3 | `convergence_probe` | 검사 코드 · 거절문 둘 · 409 매핑 | 운영 주입 0 → **자기 입력을 되돌려받는다** |
| 4 | `closed_lists["tiers"]` 한국어 라벨 | 서버가 「구조적 제거」 등을 낸다 | 화면은 `row.tier` 의 영문 id 를 찍는다 |
| 5 | `POST /drafts/{id}/review` · `/revise` | 라우트 · 서비스 메서드 · 컨트롤러 분기 | **누를 버튼이 없다** |
| 6 | `deletion_preview` 의 `is_reset`·`blocked`·`released` | 계산되고 발행된다 | 클라가 `unread_after` 하나만 읽는다 |
| 7 | `/view` 의 `reference_limit` | 라우터가 쿼리로 받는다 | 클라가 안 싣는다(항상 기본 200) |

### ④ 에서 나온 문서 정정

| 문서 | 적힌 것 | 실측 |
|---|---|---|
| `CODE_MAP.md` §5-H-bis `ledger_skeleton.json` 항목의 **🆕⑮ [2026-08-30] 블록** | 「`references` … 작성 폼 그림(**여기, 신설**)」 | 🔴 **거짓이 됐다.** `git show HEAD:server/ledger/ledger_skeleton.json \| grep -c references` = **0**(`5a73021a` 에서는 1). `b143e162`(「the form stops offering `references`, and the grammar keeps accepting it」)가 그 노드를 들어냈다. 그 블록이 센 다섯 층 중 **넷이 0**이다. 🔴 같은 절의 «헤더»는 줄 수를 761로 갱신했는데(`328a5c20`) 이 문단은 안 따라와서 **한 절이 서로 모순되는 두 상태를 들고 있다.** 정정 문장: 「`references` 는 검증기 문법만 남았다(`setup_bundle._validate_references`). 폼은 `b143e162` 이후 «묻지 않는다» — 다섯 층 중 하나만 살아 있다」 |
| `CODE_MAP.md` §5-H-bis 클라 표 줄 수 넷 | `8d1e6c4c` 기준 | 드리프트(표가 기준을 밝히므로 «틀림»은 아님): `ontology_explorer.js` 1,323→**1,367** · `_store.js` 465→**485** · `_view.js` 2,277→**2,415** · `config_explorer_service.py` 989→**1,004** |
| `server/scripts/audit_authoring_form.py` `_skeleton_leaves` docstring | 「`ontology_explorer_view.js:1062`」(후보 목록) · 「`:975`」(한 멤버 접기) | ⚠️ **줄 번호가 죽었다** — 실제 그 줄은 `renderGround(row)` 와 `const list = h('span','oe-value')`. 규칙 자체는 `closed_list.js` 로 옮겨가 살아 있으니 **위치가 아니라 술어로 다시 적어야** 한다 |

### ④ 에서 CODE_MAP 이 맞았던 것

라우트 **15**·비-strict **6** ✅ · `closed_lists` 발행 키 **23** ✅ · `implementation_choices` 가 클라 무변경으로 배선된다 ✅ · `oe-field-select` 잔존 **0**, `closed_list.js` 호출처 **2** ✅ · `preparer_output_columns` 의 `value` 가 «매핑»이고 런타임이 안 읽는다 ✅.

### ④ 못 밝힌 것

- `/columns` 응답의 `columns` 배열이 **구조분해나 다른 이름으로** 넘겨받는 경로로 렌더될 가능성은 전수로 배제하지 못했다(`stats.` 접근 두 건만 확인).
- 워커 쪽에서 `SYSTEM_RELOAD` 를 받아 **원장 v2 선언**을 다시 읽는 소비자가 있는지 — 「백필이 run boundary 마다 컴파일한다」는 것은 `activate` 응답의 `note` 문자열이 하는 «주장»이고, 백필 코드로 직접 재지 않았다.

---
## ⑨ 맵 편집·확정 — 화면 편집 → 저장 → 정렬/규격 → 확정 이력

| 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|
| `map_editor.js::loadExistingMap` | `main.py` 제네릭 표 라우트 | `#btnLoadMap` 클릭(`:664`) · 부팅 복원(`:4109`) · 프레임 진입(`:8423`) | HTTP GET 쿼리 | `` `/tables/${selectedTable}/data?limit=2000&filters=${enc(JSON.stringify(filterModel))}` `` — `defer_total` 을 **일부러 안 붙인다**(응답 `total` 로 셀 절단을 판정하므로) | 호출처 3 | 🔊 `alert('맵 로드 실패 · 테이블·맵 키 확인')` / quiet 모드면 같은 문구 토스트. 행은 왔는데 셀 0이면 별도로 `'${selectedTable}: ${fetchedRows}행 중 좌표로 읽힌 셀 0개 — X/Y 컬럼을 확인하십시오.'` | ✅ |
| `map_editor.js::fetchGridMetaFor` | `wafer_map_metadata` | `resolveDeclaredGridMeta:5617` · `diagnoseDesignationAlignment:9506` · `saveMapSpecOnly:9789` · 오버레이 쌍 `:10464-65` | HTTP GET 쿼리 | `` `/tables/wafer_map_metadata/data?limit=2&defer_total=true&filters=…` `` — **`limit=2` 로 「둘 이상인가」를 행 수로 판정** | 5 | 🔊 404/405 → `null`(「선언 없음」) · 그 외 `throw new Error('맵 규격 조회 실패 (HTTP N)')` — 호출자가 결정 | ✅ |
| `map_editor.js::pushMapData` (1/2) | `PUT /tables/wafer_map_metadata/data/updates` | `#btnPushMap` 클릭(`:707` 유일 리스너) | HTTP PUT 본문 | `{updates:[{business_key_val:`${selectedTable}_${mapIdStr}`, updates:{map_pk, target_table, map_id, grid_metadata}, source_name:'user', updated_by}]}` — 🔴 `effort` **없음**(주석이 사유 명시: 같은 배치 엔드포인트라 두 번 청구됨) | 1 (`crud.apply_batch_updates`) | 🔊 실패 시 `metaPushFailed` 를 물고 가 `:6352` 에서 `'셀 N건 적재 · 맵 규격 저장 실패 (HTTP N) — 다시 Push하십시오.'` | ✅ |
| `map_editor.js::pushMapData` (2/2) | `PUT /tables/{selectedTable}/data/updates` (`main.py:2863`) | 같은 클릭, 1/2 직후 | HTTP PUT 본문 | `{updates, silent:false, replace_map:true, effort: effortSnapshot()}` — **이 화면에서 `effort` 가 실리는 유일한 요청** | `_validate_effort` → `crud.record_interaction_effort` (1) | 🔊 `'적재 완료 — N건'` / `console.error('❌ [API Response 2/2] …')`. `effortCommitIfRecorded(result)` 가 `res.ok` 가 아니라 **서버가 기록했다고 답할 때만** 카운터를 비운다 | ✅ |
| `map_editor.js::saveMapSpecOnly` | `PUT /tables/wafer_map_metadata/data/updates` | `#btnSaveMapSpec` 클릭(`:708` 유일) | HTTP PUT 본문 + `AbortController` | `{updates:[{business_key_val, updates:{target_table, map_id, grid_metadata}, source_name:'user', updated_by}]}` — 🔴 `effort` **없음**, 셀 0건 | 1 | 🔊 **세 갈래로 가른다** — `!res.ok`: `'…아무것도 기록되지 않았습니다.'` / 타임아웃: `'…N초 안에 응답이 오지 않았습니다. 저장됐는지 확인이 필요합니다…'` / 예외: `'응답을 받지 못했습니다'` | ✅ |
| `map_editor.js::saveLegendToServer` | `PUT /tables/map_split_registry/data/updates` | `pushMapData:6333` 의 `await` — **호출처 1** | HTTP PUT 본문 | `{updates, replace_map:true}` — 🔴 `effort` 없음(같은 사람 동작의 후반부). 쓰기 전 관문 넷: `probeZoneColumns()` · `legacyBands` 미판독 행 · `readRegistryScope` · 지문 대조 | 1 | ⚠️ 저장 실패는 🔊 `'DOE·split 서술 registry 저장 실패 · 오프라인 캐시에만 보관됨'`. 그러나 **관문 거절 넷은 🔇 조용** — `{ok:false, reason:'zone-columns-missing'\|'adopted'\|'conflict'\|'empty'}` 를 «반환만» 하고 화면에 안 뜬다 | ⚠️ |
| `map_editor.js::saveDoeDraft` | `localStorage` | 범례 편집 | localStorage 키 | `doeDraftKey(selectedTable, mapKey)` + 별도 `LAST_OPEN_KEY`(`:4078`) | 1 (`restoreDoeDraftWithPrecedence:5927`) | 🔇 `try/catch` 로 삼킨다(`/* 무해 */`) | ✅ |
| `map_editor.js::resolveValidDie` | `GET /tables/{ref.table}/data` | 유효 다이 참조 해석 | HTTP GET 쿼리 | `` `?limit=${OVERLAY_CELL_LIMIT+1}&defer_total=true&filters=…` `` — 절단을 `rows.length > 2000` 으로 판정하고 `total` 은 안 쓴다 | 1 | 🔊 `refuse(ref, '${ref.table}: 참조 맵 셀 조회 실패 (HTTP N).')` · 절단은 **실패로 강등**해 이름을 댄다 | ✅ |
| `map_editor2.js::start` → `map2/api.js::loadWorklist` | `GET /api/maps/alignment/worklist` (`main.py:4503`) | 페이지 부팅(`map_editor2.html:877`) · 검색어 입력 | HTTP GET 쿼리 | `?rule&map_table&q&sort&order&limit&offset` — 🔴 **`q`·정렬·페이징이 전부 서버**(클라에 「전량 로드」 함수가 없다 — 확장성 상설 준수) | 1 (abort 신호까지 통과) | 🔊 `withWorklistError` → 목록 영역 사유 문구. 라우트 미배선이면 `RouteNotServedError('worklist')` 로 **이름을 대고** 거절 | ✅ |
| `map2/api.js::loadReferenceView` | `GET /api/maps/alignment/view`(`main.py:4292`) → `alignment_view_service.resolve_alignment_view` → `map_alignment.build_alignment_view` | 목록 행 선택 | HTTP GET 쿼리 | `{rule, map_table, params: JSON.stringify(r.params)}` + 조건부 `reference`·`x_col`·`y_col`·`value_col`·`include_cells='false'`. 🔴 **`assume_reference_geometry` 를 어느 방향으로도 안 보낸다** → 서버 기본 `True` 가 항상 성립 | 1 (`decode.js::decodeReferenceView`) | 🔊 400/404 는 서버 문장 그대로. `params` 없으면 **요청 전에** reject | ⚠️ |
| `map2/api.js::loadAlignConfig` | (없음) | 임계값이 필요할 때 | — | `ROUTES.config = null` 이 **의도된 부재** → `Promise.reject(new RouteNotServedError('config'))` | 0 (서버 라우트 0) | 🔊 `"no server route exists for 'config'…"` 를 던진다. 판정층은 임계값이 없으면 **순위를 안 매긴다** | ⚰️ (의도적·명명됨) |
| `map2/main.js::onConfirm`(`:1830`) | `POST /api/maps/alignment/confirm`(`main.py:4403`) | `#me2-confirm-btn` 클릭 또는 Enter — **무장 단계 없음**(제품 소유자 2026-08-06) | HTTP POST 본문 | `{rule, decision_key, frames: r.frames \|\| {}, map_table, columns:{x,y,val}, frame, sources, ruling, state, reference, confirmed_by}`. 🔴 `frames` 를 **일부러 `{}`** 로 · 🔴 `shift_dx/dy` 삭제됨(상수 0을 배치로 실어 보내던 결함) · `enrichment_row_id` 안 보냄 | 1 (`map_editor2.js:104` 이 `live.confirmFrame` 위임) | 🔊 서버 문장을 `#me2-confirm-note` 에 그대로 + `#me2-confirmbar[data-me2-confirm-state="failed"]`. 결정키 미충족은 **요청 전에** 같은 슬롯으로 거절 | ✅ — 🔴 **map2 는 확정할 수 있다**(vite 주석의 전제는 이미 충족) |
| `main.py::confirm_map_alignment` | `frame_confirmation.record_confirmation` → `FrameConfirmation` + `FrameConfirmationSource` 행 | 위 POST | 함수 인자 → DB 행 | `models.FrameConfirmation(… frames=dict(frames), core_frame=frames.get('core_frame'), dt_frame=frames.get('dt_frame') …)` | **1 운영 호출처**(`main.py:4441`. 나머지 12건은 `server/tests/*` — 규칙대로 뺀다) | 🔊 `ConfirmationRefused` → 400 + 한국어 문장. `_resolve_frames` 가 **`frames` 도 `frame` 도 비면 거절**(「확정된 프레임이 없습니다」) | ✅ |
| `frame_confirmation._write_confirmed_meta` | `wafer_map_metadata.grid_metadata` | `record_confirmation` 내부 | DB 배치 upsert | `map_alignment.confirmed_meta_for` 가 만든 `meta` 에 `base[FRAME_CONFIRMED_KEY]=dict(mark)` + `apply_valid_die_ref` 를 찍는다. `transaction_id=confirmation_uid`, `silent=True` | 1 | 🔴 **사용자에게는 조용.** 메타 표가 미선언이면 `logger.warning("[frame_confirm] '%s' is not a declared table — the confirmed coordinate system was not stored")` 만 남고 **확정은 200 으로 성공**. `valid_die_ref` 미도장도 `logger.info` 뿐 | ⚠️ 사슬이 끊겨도 화면은 「확정됨」 |
| `frame_confirmation.as_payload`(`main.py:4448` 응답) | `map2/main.js::onConfirm` 의 `.then()` | 응답 도착 | HTTP 응답 본문 | 서버가 **전부** 실어 보낸다: `{confirmation_uid, version, unit, frames, confirmed{frame,map_table,columns}, reference, ruling, weakest, confirmed_by, confirmed_at, supersedes, sources[]}` | 🔴 **0** — `.then(() => { confirmInFlight=false; setSession(withConfirmed(session)); })` 가 **인자를 안 받는다**. `map2/api.js:358` 이 「Returns the WHOLE created record… **Render that.** NEVER re-fetch after a write.」라고 «자기 파일에» 적어 뒀다 | 🔇 조용 — 화면은 `#me2-confirm-hint` 가 `'확정됨'` 이 될 뿐. `confirmation_uid`·`version`·`supersedes` 가 **브라우저에 도착했다가 버려진다** | ⚠️ |
| `FrameConfirmation.superseded_by` / `supersedes_uid` 사슬 | (없음) | `record_confirmation:622` 이 `prev.superseded_by = uid; header.supersedes_uid = prev.confirmation_uid` | DB 컬럼 | 마이그레이션 `add_frame_confirmation.py` 가 append-only 로 깔고, 재확정마다 version+1 로 사슬을 **쓴다** | 🔴 **0** — 읽는 곳은 `.is_(None)` 필터 «셋»(`frame_confirmation.py:141,174` · `map_alignment.py:6649`)뿐이고 전부 「현행만 고르려고」 읽는다. **이력을 내는 GET 라우트 0건**(`main.py` 의 `/api/maps/*` 전건 열거로 확인) | 🔇 조용 — 아무 화면도 「이 단위가 세 번 확정됐고 두 번 뒤집혔다」를 말하지 못한다 | 🔴 **흐름 ⑨ 의 「확정 이력」 절반이 쓰기만 있고 읽기가 없다** |
| `map_alignment._live_confirmations`(`:6641`) | 워크리스트 행 `confirmation` | 워크리스트 요청(`:6812`) | DB 조회 → HTTP 응답 | `filter(rule_name, unit_key.in_(part), superseded_by.is_(None)).order_by(version.desc())` → 행에 `{version, confirmed_by, confirmed_at}` **셋만** | 1 (`map2/view_model.js:1313` `confirmed: !!row.confirmation`) | 🔇 확정이 없으면 `pending`(정상 상태) | ✅ — 다만 **현행 1건만이고 이력이 아니다** |
| `map2/view_model.js` 「이 세션 확정」 배지 | `#me2-badge-session` | 확정 성공 | 클라 메모리 | `confirmedThisSession: session.confirmedCount` ← `session.js:491` 의 `+1` | 1 | 🔇 새로고침하면 0. **서버가 세어 준 수가 아니다** | ⚠️ 「확정 이력」으로 읽히지만 세션 카운터 |
| `frame_confirmation.derived_cell_scope` | `models.CellSource` 질의 | (없음) | — | `filter(CellSource.confirmation_uid == confirmation_uid)` | **0 운영 호출처** — 히트 2건은 `server/tests/test_frame_confirmation.py:209`(시험) 과 `bonding_plan.py:276`(**주석**) | 🔇 조용 | ⚰️ |
| `bonding_plan.py:283` | `frame_confirmation.live_confirmation_for_maps` → `warrant_of` | 본딩/전사 계획 조회 | 함수 인자 → DB 행 | `basis = {"kind": BASIS_CONFIRMATION, "confirmation_uid", "version", "reference", "warrant": warrant_of(header), "weakest"}` | 1 (`bonding_plan`·`transfer_plan` 두 경로가 같은 함수) | 🔊 `logger.warning("[BondingPlan] frame confirmation lookup failed: %s")` + 이름 붙은 상태(`not_declared`/`mapping_unavailable`)로 물러난다 | ✅ **확정을 실제로 읽는 유일한 운영 소비자** |
| 확정 → `map_editor.js::parseValidDieRef` | 레거시 에디터 | 확정 뒤 사람이 레거시에서 맵 로드 | DB 행(`grid_metadata`) | 확정이 `apply_valid_die_ref` 로 `grid_metadata.valid_die_ref` 를 찍고(`map_alignment.py:799`) 레거시가 같은 키를 읽는다(`map_editor.js:2489`). 유도가 하나이고 `contracts/map_seam` 이 양쪽을 채점 | 1 | 🔇 도장을 못 찍으면 `logger.info("[MapAlignment] valid_die_ref NOT stamped…")` 뿐 | ⚠️ 🔴 **레거시는 `frame_confirmed_from` 을 읽지 않는다**(`map_editor.js` grep 0) — 확정된 회전·면은 «값»으로만 들어가고 「확정됨」 표지는 레거시에 없다 |
| `chain_ingestion_worker` → `mappers/dt_alignment_metadata_mapper` | `wafer_map_metadata` | 체인 규칙(`alignment_rule`·`map_table`·`metadata_target_table`)이 걸린 표에 행이 적재될 때 | 함수 인자 → DB 배치 | `resolve_alignment_view(...)` → 게이트 통과 시 `confirmed_meta_for(..., mark={source:UPDATED_BY, rule, decision_key, winner, input_fingerprint})` → `grid_metadata` upsert | 1 | 🔴 시끄러움이 **엉뚱한 방식으로** — `print('------------------- AUTO ALIGNMENT IS RUNNING------------------')` + `print(rule)` 이 raw stdout 으로 나간다(`logger` 아님). 게이트 미통과는 `continue` 로 🔇 | ⚠️ **`FrameConfirmation` 행을 안 만든다.** `mark` 에 `confirmation_uid` 가 없어 사람 확정과 «같은 표지 자리»를 쓰면서 재검 가능성이 없다 |
| `chain_ingestion_worker` → `mappers/core_alignment_mapper` | `dt_inventory.core_frame` | 같은 체인 | 함수 인자 → DB 배치 | `resolve_alignment_view(..., alignment_thresholds, source_filters, source_table, ignore_source_metadata=True)` — **HTTP 라우트가 안 보내는 인자 넷을 이쪽만 쓴다** | 1 | 🔇 게이트 미통과·`placement is None` 은 `continue`. 미선언 컬럼은 배치가 경고 남기고 200 | ⚠️ |
| `mappers/dt_map_mapper` → `dt_map_derivation.join_rule` | 가상 조인 선언 | 체인 적재 | 함수 인자 | `join_rule(db, "dt_log_confirmed_attribution")` / `join_rule(db, "dt_log_frame_attribution")`(`dt_map_derivation.py:103-104`, 호출 `:561-562`) | 1 | 🔊 `DerivationRefused(REFUSE_JOIN_RULE_MISSING, "virtual join rule '%s' is absent or was not verified…")` | 🔴 **끊김** — 커밋된 `virtual_join_rules.json.sample` 에서 그 두 이름은 **`_retired_` 접두**다(`:5`·`:22` 실측). 로더가 선언이 아니라 주석으로 건너뛰므로 **출하 샘플 기준 이 두 조회는 항상 거절** |
| `POST /confirm` 의 `frames` | `dt_map_derivation.FRAME_COLUMN`(`"dt_frame"`) | — | — | 화면이 `frames:{}` 를 보냄 → `header.dt_frame = frames.get('dt_frame')` = **NULL**. 그리고 `dt_map_derivation` 은 `dt_frame` 을 «가상 조인»에서 읽지 `FrameConfirmation` 에서 읽지 않는다(`grep frame_confirmation server/dt_map_derivation.py` = **0**) | **0** | 🔇 조용 | 🔴 양쪽 다 존재하는데 잇는 것이 없다 |
| `GET /api/maps/overlay`(`main.py:4254`) | (없음) | — | HTTP GET | `map_overlay.get_overlay(...)` · `parse_sources` · `MAX_OVERLAY_CELLS` | 🔴 **0 소스 소비자** — `client2/` 전량에서 `api/maps/overlay` 히트 0(재확인). 유일 히트는 `server/auto_update.log` 의 **과거 시험 실행 로그** | 🔇 조용 | ⚰️ (HTTP 표면만. `map_overlay` **모듈**은 `bonding_plan`·`transfer_plan`·`map_alignment` 가 활발히 쓴다) |

### ⑨ 에서 목록이 놓친 흐름

- **자동 정렬이 «두 갈래 더» 있다.** 사람 확정(`POST /confirm`) 말고 체인 매퍼 둘이 같은 채점기를 태워 좌표계를 쓴다 — `dt_alignment_metadata_mapper`(→`wafer_map_metadata`) · `core_alignment_mapper`(→`dt_inventory.core_frame`). 🔴 **둘 다 `FrameConfirmation` 행을 안 만든다** → 「확정 이력」에도, `bonding_plan` 의 warrant 조회에도 안 잡힌다.
- **자동 메타 등록**(`map_meta_registrar.py`, `MapMetaCollector`) — `directory_watcher:2635` · `chain_ingestion_worker:993` 이 트리거. **`DEFAULT_ENABLED = False`**(2026-08-30 이후)라 선언으로 켜야 돈다. 켜지면 `source='auto_map_meta'`(우선순위 99)로 합성 프레임을 만들고, 그 행을 `map_alignment.make_frame_transform` 이 거절한다 — **워크리스트 `unscorable` 의 큰 원천**.
- 🔴 **`wafer_map_metadata` 에 기록자가 «다섯»이다**: 레거시 Push(1/2) · 레거시 규격 저장 · 확정(`_write_confirmed_meta`) · 체인 자동 정렬 · 자동 등록. **다섯이 같은 `grid_metadata` 한 칸을 쓴다.**
- **범례/DOE 계획**은 별도 표(`map_split_registry`)에 `replace_map:true` 로 간다. `transfer_plan.js` 는 서버에 **쓰지 않는다** — fetch 3건 전부 GET(`/api/transfer-plan/stages`·`/source-summary`·`/validate`). `frontend.md` §5.1 의 「쓰기 소유권」 문장 ✅ 정확.
- ⚠️ **`map2/main.js` 에 리터럴 NUL 바이트가 있다**(오프셋 28521, `join('\x00')`). 그래서 ripgrep·Grep 도구가 이 파일을 **binary 로 보고 건너뛴다** — **grep 기반 감사가 map2 의 합성 루트 2,610줄을 통째로 못 본다.** 이번 측정도 `grep -a`/`sed` 로만 읽혔다. 🔴 이건 「도구가 이 파일에서 눈이 먼다」는 뜻이라, 이 저장소의 감사 전반에 걸리는 사각이다.

### ⑨ 양끝이 다 있는데 아무것도 잇지 않는 이음매 (다섯)

| # | 이음매 | 양끝 | 가운데 |
|---|---|---|---|
| 1 | **확정 이력 ↔ 아무 화면** | `superseded_by`/`supersedes_uid` 를 `record_confirmation:622` 가 쓰고 append-only 스키마가 받친다 | **이력을 내는 GET 라우트 0건.** 읽는 곳은 「현행만 고르는」 `.is_(None)` 셋뿐 |
| 2 | `as_payload` 응답 ↔ `onConfirm().then()` | 서버가 `confirmation_uid`·`version`·`supersedes`·소스 행 전부를 보낸다 | 클라가 `.then(() => …)` 로 **인자 없이** 받는다 (`api.js:358` 이 「Render that」이라 적어 두고) |
| 3 | `POST /confirm` 의 `frames` ↔ `dt_map_derivation.FRAME_COLUMN` | 화면이 `frames:{}` 를 «일부러» 비워 보내고, 파생기는 `dt_frame` 을 가상 조인에서 읽는다 | 두 이름이 만나는 자리가 코드에 없다 |
| 4 | `derived_cell_scope` ↔ 회수 경로 | 함수·질의 존재 | 운영 호출처 0 |
| 5 | `GET /api/maps/overlay` ↔ 클라 | 라우트·엔진 존재 | 소스 소비자 0 |

### ⑨ 에서 나온 문서·주석 정정

| 자리 | 적힌 것 | 실측 |
|---|---|---|
| 🔴 `client2/src/map2/api.js:277-283` | 「THE COLUMNS ARE SENT AND ARE NOT YET HONOURED … the route takes no column parameter at all (`server/main.py:4160-4168`)」 | **거짓이다.** `main.py:4292 get_map_alignment_view` 가 `x_col`·`y_col`·`value_col` 을 받아 `resolve_alignment_view` → `build_alignment_view(:5609-13)` 까지 넘긴다. 응답도 `unit.columns.{x,y,value}.{column, origin}` 으로 에코하고, 클라 `main.js:2345-50` 의 `answeredColumns` 가 `a.origin === 'chosen'` 으로 **이미 읽고 있다** |
| 🔴 `client2/src/map2/main.js:1402-04` | 콘솔 진단 「the fix is `unit.x_col` / `unit.y_col` on the wire」 | 같은 이유로 낡았다. 서버는 `unit.x_col` 을 «낸 적이 없고** `unit.columns` 를 낸다 |
| ⚠️ `client2/map_editor2.html:36-38` | 「모듈 엔트리는 아직 붙이지 않았다 … 배선 레인이 `</body>` 직전에 한 줄을 넣고」 | `:877` 에 **이미 있고** `vite.config.js:22` 에도 등재돼 있다. 같은 파일 `:876` 이 스스로 반박한다 |
| ⚠️ `CODE_MAP.md` §7-A 줄 수 3건 | (다른 15개 모듈은 정확) | `main.js` 2,489 → **2,610** · `view_model.js` 1,395 → **1,548** · `session.js` 485 → **535** |
| 🔴 `CODE_MAP.md` §7-A 「모듈 의존」 | `authoring` → `brush`·`legend` 가 살아 있는 갈래처럼 적혀 있다 | `authoring.js`(394)를 `src/` 안에서 import 하는 곳 **0건**(유일 히트는 `client2/tests/map2_authoring_harness.mjs` — 시험 전용이라 뺀다). `brush.js`(316)·`legend.js`(161)의 유일한 importer 가 그 `authoring.js` 다 → **871줄이 화면에서 도달 불가** |
| ✅ `frontend.md` §5 | 「맵 에디터는 WebSocket 을 쓰지 않는다. REST pull/push + localStorage」 | **정확하다.** `map_editor.js` fetch 27자리 전건 확인 · WebSocket 0건 · `localStorage` 는 `copyHeader`·사이드바 폭·DOE 초안·최근 열람 넷 |
| ⚠️ `docs/spec/MAP_EDITOR_SPEC.md` §5.2 | 「맵 에디터 클라는 이 엔드포인트를 더 이상 호출하지 않는다」는 **정확**하다 | 다만 절 제목 「엔드포인트는 살아 있다」와 소비자 표가 오해를 부른다: 표의 `bonding_plan.py`·`transfer_plan.py` 는 `map_overlay` **모듈**의 소비자이지 **라우트**의 소비자가 아니다. 라우트의 소스 소비자는 시험 하나(`server/tests/test_map_overlay.py`)뿐 |
| ✅ `vite.config.js:20-21` | 「until the new screen can actually confirm a frame」 | **그 전제는 이미 충족됐다** — map2 는 확정 호출처를 가진다(`map2/main.js:1830`). 「왜 아직 병렬인가」의 진짜 사유는 `CODE_MAP` §7-A 가 밝힌 `artifact_gateway.isImplemented()` 하드코딩 `return false` + 엑셀 in/out 미구현이고, 그 서술은 ✅ 정확 |

---

---

## 6. 체크리스트 — 1차 실측 아홉 흐름에서 «뽑은» 것 (발명 없음 · §4 규칙 그대로)

> 각 항목은 §4 의 세 물음 중 하나에 「아니오」가 나온 자리다. 2차 실측이 끝나면 여기에 «더해진다».

### ㉠ 선언된 것이 «실제로» 지나가나 — 아니오
```
🔄 화면이 계산·표시한 hops 가 요청에 «안 실림» (서버 기본 12). 응답의 hops_reached 도 같이 버려짐
🔴 map2 의 기준 기하 플래그가 «안 실림» -> 서버 기본값이 «항상» 적용
🔴 조회 상한 · 조합 · 컨텍스트 토큰이 «안 실림»
🔴 원장 번역기의 거절 수·사유가 «리터럴 0» 으로 넘어감 (읽는 쪽은 살아 있음)
```
### ㉡ 받는 쪽이 «있나» — 아니오
```
🔴 소급 실행 결과가 거절 셋을 «7키 복사»에서 떨어뜨림 — 화면은 「N 분자」만 말함  ← 한 줄
🔴 심박의 note · 감독의 terminal_verdict 가 /health 복사 목록에 «없음»
🔴 확정 이력(supersede 사슬)을 «쓰는데» 꺼내는 라우트가 «없음» — 흐름 이름의 절반이 write-only
🔴 자식 stdout 파일들을 «읽는 화면 0»
🔴 걷기 응답 13키 중 «2»만 남김 · 작성 화면의 여러 키가 안 읽힘
⚠️ 다만 「소비자 0」은 «두 뜻»이다 — 아무도 안 쓴다(빼기) vs 한 곳에서만 쓴다(퍼뜨리기)
   가르는 물음: 「이 키가 «없으면» 무엇을 말할 수 없게 되나」
```
### ㉢ 끊기면 «시끄러운가» — 아니오(조용함)
```
✅ 닫힘  독 든 요청이 큐를 영원히 막던 것 · 죽은 태스크에 「spawned」
🔴 열림  설정 순환 거절 -> 워커가 «옛 규칙»으로 계속 돎 (로그 한 줄뿐)
🔴 열림  debug 침묵 -> 체인 큐가 「막는 것 없음」으로 그려짐
🔴 열림  읽기 실패가 HTTP 200 + 빈 배열 -> 「수집기 없음」으로 읽힘
🔴 열림  잘림 가드 다섯이 목록을 «세지 않고» 버림
🔴 열림  죽은 백업 잡이 200 응답 «문자열»로만 — 읽는 화면 없음
🔴 열림  원장 적재의 ON CONFLICT DO NOTHING 이 «무표적» 유실
```
### ⚰️ 그리고 «도달 불가» — 죽은 갈래
```
1차 실측 합계: 「반쪽」 19건 · 그중 «죽은 갈래 11»
   씨앗 노드의 여섯 갈래 중 다섯 · 영원히 빈 지역변수 넷 · 걷기 종류 축 일곱 중 다섯 ·
   작성의 수렴 프로브·검토 라우트(누를 버튼 없음) · 브러시/범례 871줄 ·
   그리고 «검색이 못 보는» 2,610줄 (NUL 바이트 — 세기 전)
```

### 🔴 우선순위 — 「운영을 멈추는 것」 > 「거짓을 말하는 것」 > 「안 들리는 것」
```
✅ 멈춤     둘 다 닫힘 (독행 · spawned)
🔴 거짓     화면이 12홉을 3홉이라 함 · 「막는 것 없음」 · 「수집기 없음」  <- 지금 여기
🔴 안 들림  자식 로그·백업·확정 이력 — 값은 있는데 «볼 자리»가 없음
```
