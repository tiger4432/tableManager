# 📌 PROJECT STATUS — 진행 상황 & 문제 현황 (Living Board)

> **Status:** 🟢 Living | **Last-updated:** 2026-07-29 (DOE UI VOC 확장 + 신규 3건 등재 — 대기열 1~1e가 한 라운드)
> **목차:** [현재 초점](#-현재-초점-current-focus) · [최근 완료](#-최근-완료-recently-done--2026-07-2526-롤업) · [백로그](#️-다음-단계--백로그-next--backlog) · [열린 문제](#-열린-문제-open-problems) · [코드 체계](#-코드-체계-code-index--약칭이-무슨-뜻이고-어디에-정의돼-있나) · [환경 메모](#-환경-메모-env-notes)
> **작성 규율:** 각 항목은 **목표 / 할 일 / 문제** 세 줄이면 충분하다. 경과·이력·증거는 히스토리와 보고서에 있다 — 여기 쌓지 않는다.
> **역할:** 프로젝트의 **현재 진행 상황·열린 문제·다음 단계**를 담는 단일 상태 보드. **컨텍스트 압축/세션 교체에도 살아남는 영속 상태**다.
> **규칙:** 총괄(및 각 PM)은 작업 **착수 전 이 파일을 읽고**, **완료 후 갱신**한다. 상세 이력은 [history/](../history/README.md), 현재 아키텍처는 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md). 이 보드는 이력 로그가 아니다 — "지금 어디까지 왔고 무엇이 문제인가"만 담는다.

---

> ✅ **재기동 완료 — 라이브는 `269b39e` (2026-07-28 01:00 기동, 커밋 23:35보다 뒤)**. 포트는 **8080**이다(8000 아님 — 진단할 때 여기서 자주 헛짚는다).
>
> 실측 확인: `/health` 200 · `/api/transfer-plan/stages` 200에 roles 전부 `connected` · `/api/transfer-plan/validate`는 **404가 아니라 422**(라우트 존재, 파라미터 누락) · `POST /admin/auto-update/run-now` → **503**.
>
> ✅ **어드민 표면 실제로 잠김 (2026-07-28 01:02, 운영에서 처음)** — 토큰 없음 **401** / 틀린 토큰 **403** / `/health` 200(설계대로 무인증 유지). `/internal/events/*` 4개 라우트도 전부 401.
>
> **워커 토큰 상속도 실측됐다**: 워커 4종 정상 하트비트, 아웃박스 pending 0, 워커 로그에 `401` 없음. 부분 재기동 실패 모드만 아직 미재현([ROLLBACK_PROCEDURE §미실행 표](../guide/ROLLBACK_PROCEDURE.md)).
>
> ⚠️ **PowerShell에서 `set`은 조용히 실패한다.** `set ASSY_ADMIN_TOKEN=…`은 환경변수가 아니라 동명의 PowerShell 변수를 만들고 끝나며 **에러도 안 난다**. `$env:ASSY_ADMIN_TOKEN = "…"`를 써야 하고, 설정한 **그 셸에서** 런처를 띄워야 자식이 물려받는다. 2026-07-28 실제로 여기서 막혔고 [DEPLOY_SETUP §1-4](../guide/DEPLOY_SETUP.md)에 셸별 표로 명문화했다.
>
> 남은 한 가지: **첫 실 `bands` 쓰기**. 라이브 행은 여전히 전부 `bands IS NULL`이라 파싱 경로를 아무도 안 밟았다 — 존 컬럼 설치가 끝나야 처음 밟힌다.

## 📋 개발 대기열 (Queue) — 사용자 지시 2026-07-27

> **규율:** 새 요청은 **즉시 착수하지 않고 이 대기열에 넣는다.** 위에서부터 순차 처리하며, 파일이 겹치지 않을 때만 병렬로 돌린다.
> **이유:** 대기열 항목은 **고쳐도 공짜**지만 이미 던진 항목을 고치면 에이전트-시간이 날아간다. M2.6은 착수 전 5회 수정돼 비용이 0이었고, 좌표 건은 착수 후라 2라운드를 잃었다.
> **예외:** 사용자 작업을 지금 막고 있거나 프로덕션이 깨진 건은 앞으로 당긴다 — 단 **당긴다고 말하고** 당긴다.
> **순서 변경은 사용자 권한.** 총괄은 제안만 한다.

> **포맷 (2026-07-28 통일):** 한 항목 = **제목 한 줄 + 착수에 필요한 핵심 1~3문장**. 경과·근거·수치는 히스토리/보고서에 있다 — 여기 쌓지 않는다. 완료 항목은 표에서 내리고 아래 「종결」 한 줄로 압축한다.
> **열:** 순번(처리 순서) · 항목 · 담당 · 등급([[review-tiers]] T1/T2/T3) · 상태

| 순번 | 항목 | 담당 | 등급 | 상태 |
|---|---|---|---|---|
| — | ~~H1·H2~~ ✅ **완료** (`6db517d`, 퀵 QA FIXED×2) — H1: 로드 경로가 초안을 덮기 전에 읽도록 + "복구=화면 변화"로 정정. H2: 대조 가드(화면 비어있지 않은 셀 − 직렬화 셀, 0 오탐)가 파괴 방지 게이트 3호로. **잔여 소형 3건 대기열 편입** ↓ | — | — | ✅ |
| 5b | **맵 에디터 소형 묶음** (라운드 인접 발견, 전부 기존 결함): ⓐ 지문 불일치 토스트 문구 vs 직후 persist 모순 ⓑ `legendDirty` 맵 전환 시 미리셋 ⓒ **메타 없는 맵 프레임 사상 근본 수리** — 기본 프레임 전 선택지가 원형 마스크로 373/1293만 담아 가드 발화로 Push 불가 + 로드 후 격자 입력 readOnly라 UI 조정 불가 ⓓ 후보 목록 매칭 대소문자 분기(`map_editor.js:1285` 무시 vs `:5097`·서버 정확일치) ⓔ 안 고친 자재 프레임에서 뒤로가기 confirm 발화(`framePushed` 초기 false) ⓕ **~1540px 미만 창에서 계획 사이드바 도달 불가**(`overflow-x: hidden` + 최소폭 — 1366/1440 화면 사용자는 계획 패널을 못 씀) ⓖ 메타 모달 취소 시 조용한 롤백 | map-pm(ⓐⓑⓓⓔⓖⓒ)·ui-designer(ⓕ) | T2/T3 | ✅ **전건 완료** (`0052d76`, 퀵 QA 6/6 FIXED + ⓕ 실측 3폭). ⓒ는 기본 프레임 = 데이터 bbox·마스크 무효 기하로 — Push 불가였던 QA 재현 맵이 정상 확인창(1293건) 도달. **신규 발견 1건 백그라운드 분리**: depth-0 로드 취소가 모달 전에 gridData를 지움(기존 결함) |
| — | ~~U8·U9~~ ✅ **완료** (`2baf9ff`, QA GO) — 마커 값·V6 양측, 가용 사유 노출, bin_map 선언 경로 E2E 증명. 잔여 LOW 2건: JSON 숫자 `0.5`→marker 승격(양측 일치라 비긴급, 다음 계약 라운드에 동승) · M1 위임 stage에서 bin_map 무효(라이브 dt 점등 시 inline 전환 필요 — 현장 결정) | — | — | ✅ |
| — | ~~U6~~ ✅ **완료** (`95bf072`, QA 2레인 GO — 분할 구조 첫 실전) — `default_legend`·`value_column_candidates` 선언 신설(paint-rules 서빙 단일 소스), 클라 하드코딩 6종 삭제(후보 목록 2사본·builtin stage·팔레트 3사본·E1/E2 색). 라운드 내 High 1건(같은 테이블 연속 로드 legend 유출) 발견·수리 완료. 브라우저 레인이 낡은 결함 2건 추가 검출 → 5b 편입 | — | — | ✅ |
| — | ~~U7·U1·U3~~ ✅ **완료** (`a98dc72`, CSS-only) — U7 원인은 `b35bc9f` CSS 재작성의 3·4번째 희생(`.map-breadcrumb`·`.plock-chip` 무스타일) → 복원+보강. U1은 규칙이 이미 반반이었고 **주석이 거짓말** → 주석 정정+죽은 `.tp-scroll` 삭제. U3 하단 중앙 배너 + `--toast-inset-right` 참조 0 증명 삭제. 부수 관찰: 메타 모달 취소 시 `openMapFrame`이 조용히 롤백(토스트 없음) → 5b-ⓖ | — | — | ✅ |
| — | ~~5c~~ ✅ **완료** (`1fefd12`) — 트리아지 REAL(+101 유령 실측) → `connected(count_only)` 강등(remaining null+진짜 상한, per-core 양 경로 null — 퀵 QA가 log 경로 맨 숫자 잔재를 잡아 마감) + 선언 컬럼 오타 `column_unresolved` 강등 + val 오타 fail 카운트 거부(상한 불변식). 테스트 21, 뮤테이션 전멸. **형제 결함 제안 중**: self-frame fail 소스 x/y 미바인딩 — 같은 유령 계급, 승인 대기 | — | — | ✅ |
| — | ~~소급 백필 + 빈 키 큐 필터~~ ✅ **완료** (`1fefd12`) — `backfill_enrichment.py`(dry-run 기본·기존 행 불가침·멱등·실 mapper 경로·루프 가드 라이브 검증) + 큐 판정식 서버 단일화(`queue_filters` — 클라 3사본 소멸, 빈 키 제외). 빈 키 출처 = 그리드 빈 행 추가·부분 편집(레거시 mapper 무죄) | — | — | ✅ |
| — | ~~raws 폴더 평탄화~~ ✅ **완료** (`0c6ac1a`, 퀵 QA 5/5) — 중첩 폴더 투하 → 정온 대기 → 파일 승격 → `rmdir`-only 폐기. 충돌 `~` 접두(`__force__` 위조 차단), 핫 토글 | — | — | ✅ |
| — | ~~오버레이 F1~F5~~ ✅ **완료** (`17f65bd`, 원 진단 QA 재판정 5/5 FIXED — 결함 번들이 미끼 4칩을 그리는 것까지 실측한 판별 검증). paint-rules `binding` 단일 소스, 클라 유도 사본 ~40줄 삭제, 추측은 데이터 경로 거부·Load 사전선택만 경고. **table_bindings 선언만으로 tx/ty·대문자 테이블이 로드·겹치기 동작** | — | — | ✅ |
| — | ~~게이트 4호 + map_push_ok~~ ✅ **완료** (`deed6d2`, QA 4/4 + 하네스 15/15) — 판별자 = "payload/서버가 그 컬럼을 재구성할 수 있는가"(조합키 pkg_id 생존, 행 고유 dt_id 차단, config 불필요). R&D 수동 계측용 `map_push_ok: true` 선언 시 차단→소실 인지 1회 확인(JSON boolean만, `is True` 엄격) | — | — | ✅ |
| — | ~~self-frame fail count_only~~ ✅ **완료** (`deed6d2`) — 유령 계급 소탕 종결: 좌표 없는 fail 소스가 전 칩을 fail로 세며 remaining reliable:true 서빙하던 것 → count_only 강등+진짜 상한. fallback 경로는 의도적 무변경(개수 감산이 옳은 곳). 잔여 엣지 1건(fallback+region 부분집합 신뢰도) 트리아지 대기 | — | — | ✅ |
| — | ~~#6 replace_map scope~~ ✅ **완료** (`deed6d2`) — 무동작 200 → 400 사유, 응답 `scope:{filters,deleted,inserted}` 단일 해석기, 명시 scope로 의도적 전체 삭제 표현 가능. **후속 등재**: 교체 삭제 행 WS 미방송(유령 행) — 경계 계약 건 | server-pm | — | 후속 대기 |
| — | ~~D1 헌장 공백~~ ✅ **완료** (`deed6d2`) — 4문서를 server/client PM 헌장에 도메인별 의무와 함께 등재 | — | — | ✅ |
| — | ~~DB 쓰기 2건~~ ✅ **완료** (로컬 라이브 적용 — 인덱스 6종+정리 4종+재교정 인덱스, CONCURRENTLY 무중단. 운영 실행 가이드 전달) | — | — | ✅ |
| 4 | **D1 — 에이전트 헌장 공백**: `CONFIG_GUIDE`·`DEPLOY_SETUP`·`PRODUCTION_READINESS`·`FEATURE_CHECKLIST`가 어느 헌장에도 없음(감사 발견). 문서 아닌 헌장 문제 | 총괄 | — | 대기 |
| 5 | **DB 쓰기 2건** — ⓐ 재교정 집계 부분 인덱스(`setup_db_performance.py` 준비됨, 현재 512ms 순차 스캔을 60초 캐시로 방어 중) ⓑ 낡은 outbox 인덱스 정리 | 총괄+사용자 | — | DB 쓰기 필요 |
| **0** | 🔴 **V1 계기 계측 — 완료까지의 상호작용 점수** (사용자 2026-07-29 사양 확정). **단위 = 한 tx 묶음 교정 완료**(서버가 이미 긋는 경계 — `PUT /tables/{t}/data/updates` + `AuditLog.tx_id` 재사용, 새 개념 신설 없음). **배점: 키입력 1 · 마우스 3 · 화면이동 5, 낮을수록 좋음.** ⚠️ **컨텍스트를 유지한 자연스러운 리다이렉트는 0점**(예: DOE → dt map 라우팅) — 판정은 **config 선언형**, 기본은 "상실(5점)"이고 유지 전이만 선언한다(낙관 편향 방지). 집계 = **세션별 평균**. 계약: `effort:{session_id,key,mouse,nav}`는 **선택 필드** — 워커·인제션 경로는 미계측이 정상이며 **0이 아니라 없음**이어야 평균이 조용히 희석되지 않는다. 원시 카운트를 저장하고 합산은 조회 시점(배점 변경 시 과거 데이터 재해석). **R1보다 먼저 머지** — 소급 산출 불가라 UI를 먼저 고치면 "before"를 영영 못 얻는다 | client-pm+map-pm+server-pm | T2 | **승인됨 — 투입 대기** |
| **0b** | 🟡 **공수 절감 기능군** (계기에서 파생, 사용자 방향 제시 2026-07-29). 배점이 마우스 3·이동 5이므로 **손을 줄이는 기능이 곧 지표 개선**이다: ⓐ **드롭다운·입력 추천** 적극 활용 ⓑ **최대한 미리 값이 채워지게**(prefill) ⓒ **범위 묶어 Ctrl+Enter 일괄 채우기**. ⚠️ 착수 전 필수 확인: 그리드에 **이미 있는 범위·클립보드 프리미티브**(`clipboard.js`)와 겹치는지 — 없는 것만 만든다([[check-existing-primitives-first]]) | client-pm | T2 | 대기 (0번 계측 후 — 효과를 숫자로 증명) |
| **1** | 🔴 **DOE UI 개편 — 사용자 VOC 8건 (2026-07-29 스크린샷 첨부)**. **핵심 가치 선언: "작은 글씨는 없느니만 못하다"** — 이 라운드의 판정 기준. ⓐ **상단 헤더 삭제** → 전부 placeholder로(`VALUE·STACK·DESC·1H·MID·TOP`) ⓑ **빨간 테두리 제거**(V5 등 검수 표시가 거슬림) ⓒ **DOE 영역 아무 데나 클릭 → ACTIVE BRUSH**(현재는 인풋 포커스를 하이라이트해서, 브러시 선택하려면 인풋을 클릭해야 함) ⓓ 「비움」 글씨는 가운데인데 **커서가 위로 붙는** 부자연 — placeholder와 실제 입력 **정렬 일치화** ⓔ 층수 입력칸 placeholder가 **보이지도 않음** ⓕ **인풋이 너무 작아** 클릭해서 입력하기 어려움 ⓖ `LOT_*` 입력 시 **하단 자재 리스트 펼치기 미반영** ⓗ **우측 DOE 패널 슬라이더로 크기 조절** ⓘ **[2026-07-29 추가] 패널이 조잡하고 인풋 크기가 제각각** — 핵심 내용만 남기고 **UI 그리드 통일**(인풋 규격 1종, 열 정렬 한 축). 감사 P1(크기 섬 20×13px·10.9px)과 같은 뿌리 — 병합 처리 | ui-designer(시각)+map-pm(ⓒⓖ 로직) | T2 | 대기 (**7b/7c 다음** — 같은 파일권이라 직렬) |
| **1b** | 🔴 **P0 입력 연속성** (야간 감사, 어제 mousedown 결함의 blur 경로 생존 친척): 필드 편집 후 **다음 클릭이 먹지 않고 이후 타이핑이 조용히 소실**. blur 커밋이 표①을 재생성 → mousedown은 옛 노드·mouseup은 새 노드 → click 미성립, 포커스 BODY로. **Tab도 동일 → 키보드만으로 행 채우기 불가**. 실증 로그 있음 | map-pm | T2 | 대기 (1과 동반 — 같은 파일) |
| **1c** | 🔴 **Copy to Excel 미작동 — 서식 보존 복사 재건** (사용자 발견 2026-07-29, **중요**). 버튼·핸들러·HTML 표 생성 코드는 **존재**한다(`map_editor.js:4598` `copyGridToExcel`, `map_editor.html:258`) — 즉 "기능 없음"이 아니라 **어딘가에서 죽는다**. 착수 = **원인 규명 먼저**(비보안 컨텍스트에서 `navigator.clipboard` 미정의 → else 분기가 그대로 `writeText` 호출해 TypeError, `gridCells2D` 가드가 `{}`라 항상 truthy 등 후보 있음). 요구사항은 **"맵이 보이는 대로"** — 범례색·테두리·노치·유효/무효 구분이 엑셀에서 유지 | map-pm | T2 | 대기 (원인 규명 후 계획 제시) |
| **1d** | 🟠 **우클릭 드래그 삭제 프리뷰가 주간 테마에서 맵을 다 가림** — **원인 실측 완료**: 라이트 `tokens.css:41` `--danger-weak: #fdecec`가 **불투명**, 다크 `:95`는 `rgba(248,126,126,.14)` 반투명. 소비처 `map_editor.js:2245`(erase 프리뷰)·`:2148`(원점 하이라이트)가 캔버스에 그대로 칠해 흰 박스가 됨. 다크에서만 정상이라 여태 안 잡힘. 수리 = 캔버스 오버레이용 **반투명 토큰**을 라이트에도 주기(범용 `--danger-weak`는 CSS 배경 12곳이 쓰므로 건드리지 말 것) | ui-designer | T3 | 대기 |
| **1e** | 🟡 **디버그성 토스트 과다 — console 이관** (사용자 2026-07-29). 맵 도메인만 `showToast` **48회**(map_editor 36 + transfer_plan 12). 기준: 사용자가 **행동을 바꿀 수 있는 것만 토스트**, 개발 흔적·중간 상태·성공 확인은 `console.debug`. 파괴 방지 게이트·거부 사유·저장 실패는 **토스트 유지**(정직한 실패 고지는 핵심 계약) | map-pm | T2 | 대기 |
| 7b | 🔴 **맵 키 값 정규화 일원화** (운영 실증 2026-07-28 밤): slot이 number 선언이면 저장은 `1`인데 자재 토큰 `LOT_01`이 map_id를 `LOT_01`로 조합 → 메타 `LOT_1` 미스. **데이터는 열리고 메타만 없는 것처럼** 보임(셀은 캐스팅 필터, 메타는 문자열 map_id). 수리: map_id 조합·메타 조회·토큰 분해가 **선언 타입 기준 canonical화 공유 함수 하나**를 타게(R4 함정 계급, "같은 정수 판정기" 규율의 확장). 우회 안내됨(토큰을 저장 형식으로). **M3와 같은 메타 영역 — 한 라운드로 묶기**. **서버 절반은 이미 라이브**(`ab6ac02` `canonical_key_value`) — 남은 건 클라의 map_id 조합·토큰 분해 사이트 | map-pm | T2 | 🔴 **다음 라운드 1순위** (사용자 지시 2026-07-29). 현 계측 라운드가 같은 파일을 잡고 있어 **머지 직후 착수** |
| 7c | **`transfer_log: "none"` 선언 — 소비 기록 없는 현장 지원** (사용자 요청 2026-07-28 밤 "기록 없이도 되게"): 선언 시 `connected(untracked)` 상태로 잔량을 **상한 표시(`≤N` = 총량−fail)** + 툴팁 "기전사 미차감". 사고성 missing은 미상 유지 — 선언=인지 패턴(map_push_ok와 동형). 서버 upper_bound 배관 기존재, 선언 파싱+클라 표시만. 가용 풀 바인딩 canonical화(7b)와 같은 파일권 — 동반 가능 | map-pm | T2 | 🔴 **1순위 (7b와 한 라운드)** |
| 7 | **M3 맵 메타 자동 등록** (ingestion 체인) — `bonding_map` 맵 키 39만 vs 메타 9건 해소 경로 | server-pm | — | 대기 |
| 8 | **P3 대형 파일** (backpressure·COPY·상한) | server-pm | — | 대기 |
| 8.5 | **M4 — 유효 다이 맵 기반 전환 트랙** (사용자 승인 2026-07-28 밤, **mm 정렬 미사용 확인** — 손실 0 확정). 원 기하를 판정자에서 **생성기로 강등**: ①`valid_die_ref`(템플릿 맵 참조) 소비 — 가산적 공존 ②프리셋=템플릿 생성기 + E1/E2 침식(이웃) 기반 ③inside에서 원 은퇴 + 기존 메타 188건 이관 스크립트. 결함 계급 #11·#18·#20·마스크 트릭의 근원 제거. "유효 다이도 맵이다 — 마스크 편집이 곧 페인팅" | map-pm+server-pm | ①T2 ②③T1 | ①은 7b·7c·M3 묶음과 동반 |
| 9 | 🔵 **온톨로지 슬라이스 1호 — 자재 knob tag 추적** (사용자 로드맵 모델 2026-07-29). "자재의 knob tag를 잡으면 **공정 이력과 DT 이력이 엣지 트레이스만으로** 따라 나온다". 기계는 이미 있다(G1 materializer·`POST /graph/trace` 멀티시드 BFS·`trace.html`) — **비어 있는 건 매핑과 label 정합**이다. 슬라이스 범위: ⓐ knob tag 노드 승격 선언 ⓑ **테이프 label 분리**(lot=테이프 확정으로 지금 가능, #15 해소) ⓒ 슬라이스 테이블 `event_time` 교정 ⓓ dt_log 매핑 ⓔ trace 결과 검수. **전면 §7.5c·정책 엔진·M3 39만은 이 슬라이스에 불필요** — 다음 use case가 요구할 때 당긴다 | ontology-pm | T2 | 대기 (범위 확정 후) |
| 9b | **온톨로지 잔여 기반** (슬라이스가 요구할 때 당김): §7.5c node_class 전면 · 4대 탐색 정책 엔진(G2.5 전제) · DELETE 시 그래프 정리 정책(stale 엣지) · M3 맵 메타 39만 · G3 불량추론(PPR·heat propagation) | ontology-pm | — | 대기 |

**종결 (2026-07-25~28)**: 운영 강화 2차 `d56e7e2` · M2.6 DOE 통합 `cdcddee` · 문서 4분할 `52a668b` · 수집기 exec 스코프+`out=None` FAIL · 그리드 Ctrl+C 중복 분기 삭제 · C1 접근 통제(+경로 탈출·낡은 번들) `90e284f` · 재교정률 계기 `ec75d4c` · B4 롤백 드릴(30초 실측) · C3 백업(복원 드릴 2회) `b35bc9f` · U2 없는 키 라우팅 `280ebf0` · 문서 감사 후속(아카이브 7건·헬스 어휘) — 상세는 [히스토리](../history/README.md).

**✅ 사용자 결정 (2026-07-29) — 대기 4건 전부 해소**:
- **V1 계기 교체** — 재교정률이 아니라 **완료까지의 상호작용 횟수**(클릭·화면 이동)가 정본. 재교정률은 보조로 강등. SSOT §1 갱신 완료. **미구현이고 소급 불가** → 계측이 R1 UI 라운드보다 **먼저** 머지돼야 전/후 비교가 성립
- **`bonding_log` lot/slot = 테이프** — 코어 아님. 스펙 §7.5b DT/Tape 계층 확정. 파생: `Wafer` label에 섞인 `core_lot|core_slot`은 **테이프 위치**이므로 별도 label로 분리(#15), 해당 엣지는 DT 계층으로 retarget
- **재교정 인덱스 승인** — `python server/scripts/setup_db_performance.py` (CONCURRENTLY·멱등·무중단). 절차는 [POSTGRES_OPERATIONS §3.1](../guide/POSTGRES_OPERATIONS_GUIDE.md)
- **선언 없는 테이블 처분 허용** — 총괄은 **선언 제거만**(워처 부활 차단) 수행하고 물리 `DROP`은 사용자가 직접 실행(기존 규율 유지)

**🔁 로드맵 모델 (사용자 2026-07-29) — 얇은 수직 슬라이스 루프**:
> 온톨로지를 **작게 활성화** → 작은 use case 완성 → 그 use case로 온톨로지 **강화** → use case 추가 → 반복.
> **1호 use case = 자재 knob tag 추적** (공정 이력·DT 이력을 온톨로지 **엣지 트레이스만으로** 소환).
> 이 모델의 값: 기반 공사(§7.5c 전면·정책 엔진·M3 39만)를 **뒤로 미룰 수 있다**. 단 **두 가지는 슬라이스 안으로 딸려 들어온다** — ⓐ 테이프 label 분리(안 하면 trace가 엉뚱한 개체를 지목) ⓑ **슬라이스에 포함된 테이블의 `event_time`**(공정 이력의 *순서*가 틀리면 use case가 능동적으로 오도한다). 전면 교정은 불필요.

> 🧭 **핵심 가치 추가 (사용자 2026-07-29)**: **"작은 글씨는 없느니만 못하다."** 읽히지 않는 정보는 정보가 아니라 잡음이다 — 크기·대비·정렬이 안 맞으면 그 요소는 있으나 마나이므로, UI 판정에서 **가독성은 기능과 동급**으로 다룬다. 야간 감사가 측정한 10.9px 메시지·20×13px 버튼·placeholder 정렬 불일치가 모두 이 기준 위반이다.

## 🎯 현재 초점 (Current Focus)

> 완료된 트랙은 여기서 내리고 §최근 완료로 옮긴다. **지금 손이 가 있는 것과 바로 다음 관문만** 남긴다.
> 항목 형식은 **목표 / 할 일 / 문제** 세 줄. 경과는 히스토리와 보고서에 있다.

1. **🟢 DOE 존 모델(M3) — 양측 착지, 라이브 동작 중** (`b35bc9f`+`280ebf0`, 2026-07-28)
   - **모델**: 표① 값 정의(`COLOR·VALUE·STACK·DESC·1H·MID·TOP`) + 표② 자재 롤업(`MAT·MAP·KNOB·가용·사용·잔여`). `STACK` 숫자 하나가 층 구조 전부, 세 구역이 `1..STACK`을 구조적으로 채움. `dt_map`은 `STACK=1`·MID만. 자재 토큰 `lot[_slot][:BIN]`. 엑셀 6칼럼 TSV 계약(`tsv.js`).
   - **저장**: `pushMapData` 유일 기록자(참조 정의 1 + 호출 1). 검수는 보고만. 존 컬럼 4종 **물리 설치 완료**(`stack`은 **string** — number였으면 `'7.5'→7` 조용한 절단). 실 `replace_map` 저장 E2E 통과, `'0x10'` 원문 왕복 확인. 스위트 815.
   - **새로고침 생존**: 초안(DOE+셀) 10개 편집 경로 전부 + **마지막 맵 자동 재열기**(`map_editor_last_open`, 부팅 시 기존 LOAD 경로 재사용).
   - **할 일**: ⓐ 사용자 DOE 실입력(이관 없음 — 확정) ⓑ **U8** 가용 버튼(대기열, `bin_map` 선언 대기) ⓒ `map_doe`·`map_doe_source` 처분(승인 대기 — 부활 사건 포함).
   - **파생 계약**: `contracts/` 3종(304/71/82)을 pytest + node 하네스 양쪽이 읽는다. 계약 변경 = 두 구현 동시 이동.

2. **🟢 프로덕션 게이트 — 차단 4건 전부 해소** (2026-07-28)
   - **해소**: B1 프로세스 감시 · B2 헬스 라우트 · B3 워커 로그 배선 · **B4 롤백 절차(드릴 실측 30초)**.
   - **조건부도 착지**: C1 접근 통제(운영에서 401/403 발효, 워커 토큰 상속 실측) · **C3 백업(복원 드릴 2회 실행)** · C2는 M2.6 재읽기·거부로 완화(재등급 대기).
   - **남은 것**: `check` §의 config 트리 외 대상 — **PostgreSQL 덤프·`ingestion_workspace/`**(실제 복구불능 손실이 났던 곳)가 다음 백업 대상으로 명명됨.

3. **🔑 도메인 규칙 — `wafer_map_metadata`가 정렬의 유일한 기준**
   - 맵을 담는 모든 테이블은 **메타 등록이 전제**. 미등록은 정상이 아니라 **누락**. 정렬은 소스·타깃 메타 델타에서 유도하고 계측 결과도 메타에 기록한다. 셀 레벨 `grid_metadata`는 **폐기 스킴**.
   - **문제**: `bonding_map` 맵 키 **약 39만 vs 메타 9건** — 정렬이 사실상 9개 맵에서만 일한다. 나머지는 `화면기준` 칩으로 노출된다. → 대기열 7번(M3)에서 해소.

4. **⚪ 대기 트랙** — ⓐ **G2.5** §7.5c 탐색 정책 엔진 → LLM 도구 API ⓑ **enrichment 실전 규칙**(사용자 실 스키마 확보가 조건) ⓒ **Chain Replay R1**.

## ✅ 최근 완료 (Recently Done) — 2026-07-25~27 롤업

| 영역 | 요약 | 근거 |
|---|---|---|
| 문서 | **문서 관리 4분할 첫 실행** — historian(히스토리)·mapper(CODE_MAP)·keeper(리빙 문서) 동시 실행 후 auditor 적대 검수. 분리가 첫 회부터 값을 했다: mapper가 "해제 지점 3곳"(실제 2)·`WARN_*` 12(실제 14) 같은 **개수 주장의 오류**를, auditor가 `PRIMITIVES.md`가 **폐기된 재시작 설계를 가르치던 것**(매 착수 로드 문서라 심각)을 잡았다. 읽기 트리거 측정으로 49개 중 18개만 실제로 읽힌다는 사실도 확인 | `d411386`·`87cbf35`·`e6a0f44`·`52a668b` |
| 서버+클라/맵 | **오버레이 변환 일원화** — 정렬을 서버에서 받지 않고 클라가 `소스 메타 프레임 → 물리 → 타깃 현재 컨트롤`로 배치. 오버레이 전용 변환 코드 0줄(메인 로드와 같은 함수). 화면에서 변환을 바꾸면 오버레이가 따라온다. 검수 A(기하) 15개 공격 전패, 검수 B가 잡은 fail-open 2종 수정. UI 순증 0. 이슈 #18 종결 | `7d931dc`+`251dbfd` · [검수 A](../../agent_workspace/reports/QA_overlay_unify_geometry.md) · [검수 B](../../agent_workspace/reports/QA_overlay_unify_behavior.md) |
| 서버+클라/계획 | **M2-v2 「계획 = 그 맵 자체」** — `bonding_map` 열면 본딩 계획, stage는 열린 테이블에서 유도. `plan_id`·별도 계획 테이블 폐기, 정체성은 `(ref_table, map_key)`. 병렬 QA 첫 적용(A·B 동시) → 양쪽 NO-GO → A1(프레임 규격 좌표)·C1(DOE 전량 삭제) 수정 후 병합 | `da65a87` · [히스토리](../history/20260726_204344_m2_v2_plan_as_map_redesign.md) |
| 인프라/테스트 | **스위트에서 허용 실패 제거 — 414 passed / 0 failed** — 라이브 사용자 자산에 쓰던 테스트 2종 격리(`maps.json`, 워크스페이스 `config.json`). `.sample` config가 v1 잔재라 신규 환경이 안 뜨던 문제 수정 | `9a8ede8` |
| 서버/인제션 | **대형 파일 P1 — heavy 레인 분리 + 진행 가시화 + 재기동 경고, 라이브 드릴 PASS** — 크기 임계(기본 10MB, `ingestion_settings.json` 핫리로드) 라우팅·워크스페이스 FIFO 3중 보존·스윕 경로 포함, push 진행 스냅샷(`/admin/file-ingestion/active`)+admin File 탭 HEAVY 배지/경고 배너. 드릴 실측: **비차단 180배(2.3s vs 415s)·10만 행 유실 0·bk 중복 0·created_logs 정확 500건 절단·이벤트 루프 p50 3.5ms**. QUEUED 통지 역전·total_log_count 비대칭 후속 수정 완료. 테스트 278 passed(+27) | `4fd8ac9`+`8b0fd03` · [히스토리](../history/20260726_093100_large_file_p1_heavy_lane_and_live_drill.md) · [드릴 보고서](../../agent_workspace/reports/QA_p1_live_drill_report.md) |
| 서버+클라/맵 | **본딩 실험계획 M1(조회 전용)** — 역할 바인딩 config + `GET /api/bonding-plan/core-summary`(`server/bonding_plan.py` — align은 cell_to_physical 순수 인덱스 변환만, QA F1/F2 결함 지점 무참여) + map editor Info 패널(`bonding_plan.js` — 층 배정·수량/FAIL/조건 이탈 경고 3종·knob 비교·localStorage 초안) + fake 원천 2종(eds 180° align 실증). **rect 영역 선택 모드는 개발 중 폐기**(M2 값 페인팅 정본). 테스트 275 passed(+18) | `e6eabe4`+`24753d3` · [히스토리](../history/20260726_093200_bonding_plan_m1_info_panel_and_core_summary.md) |
| 설계/온톨로지 | **DT/Tape 계층 편입(스펙 §7.5b) + Universal Transfer Plan/DOE 관리 단위 확정** — bonding의 core lot/slot=실제 DT lot/slot, 전사 프리미티브 일반화, value=DOE 조건군 | `63ac0c3`·`437d6d5` · [히스토리](../history/20260726_093300_dt_tape_layer_universal_transfer_plan_design.md) |
| 클라/그래프 | **뷰어 stats 라벨 카드 클릭 → 노드 리스트**(빈 q+label 서버 리스팅 캡 200, 행 클릭 explore 연동) | `df63f3a` · [히스토리](../history/20260726_093400_graph_viewer_label_node_list.md) |
| 클라/그래프 | **뷰어 Connections 테이블 + 검색 시드 연동** — 노드 클릭=선택+관계 테이블(비중심은 depth-1 보강, 80행 페이지), 행 클릭 → 중심 재조회+URL push/popstate+검색바 반영, 패널 접기. ⚠️ 중심 이동이 클릭→**더블클릭**으로 변경(사용자 공지 권장) | `18218da` · [히스토리](../history/20260725_222215_graph_viewer_connections_table.md) |
| 스펙/그래프 | **§7.5c 정적/동적 노드 분류 + 4대 탐색 정책** 수렴(S→D 기본 금지·2단계 백본→ROI·EqpState 허브앤스포크) — 정책 엔진이 **G2.5 전제 조건**으로 승격 | `99c4cb6` · [히스토리](../history/20260725_222347_ontology_spec_static_dynamic_traversal_policy.md) |
| 서버/인제션 | **워크스페이스 config.json 폐지** — `table_name`/`std_parse`를 글로벌 table_config의 `workspace_name`/`std_parse`로 흡수(옵트아웃 핫리로드화 → F4 자연 해소), 신규 생성 중단+하위호환 읽기, QA 6건 반영(파일당 config 스냅샷·별칭 섀도잉/경로탈출 방어)·테스트 21건(스위트 229 passed) | `5fac5f0`+`20d6898` · [히스토리](../history/20260725_220619_workspace_config_deprecation.md) |
| 서버/그래프 | **온톨로지 G1** — graph_nodes/edges/graph_sync_state + 매핑 v2(description 필수, enrichment `RESOLVED_AS` 자동 승격) + materializer(증분 소비·QA H1/H2 provenance·retarget) | `6da2276`→`7c40a33`→`d130c65` |
| 서버/그래프 | **조회 API 5종** — stats/neighbors/search(뷰어) + trace/mapping-summary(G2, 공용 BFS 추출) | `c63b881`, `d8d109d` |
| 클라/그래프 | **그래프 뷰어 + 추적 리포트** — graph.html(BFS 동심원 캔버스)·trace.html(그룹+타임라인) + index 「🕸️ 추적」 진입점, 양방향 크로스링크 | `eea929d`/`f41ca3e`, `6c0a722`/`83507aa` |
| 클라/admin | **파이프라인 생애주기 5탭 IA 재편**(Overview/File/Chain/AutoUpdate/Enrichment, Code Editor 딥링크 공용 뷰, 구 해시 별칭 호환) — 라이브 검증 통과 | `7d02989`(소안), `3e599d2`/`387d987`(중안) |
| 서버/인제션 | **온보딩 완결** — std parser 폴백 + 워크스페이스 자동생성(`f90717f`) + 런타임 테이블 CREATE(#7, `6c447ee`) → "config 추가→리로드→즉시 사용" | [20260725_113212](../history/20260725_113212_std_parser_fallback_and_workspace_autoprovision.md), [20260725_170000](../history/20260725_170000_issue7_runtime_table_create.md) |
| 클라/테마 | **듀얼 테마(기본 라이트)** tokens.css SSOT + 다크 심화, 헤더 드롭다운 z-order 수정 | `765c7e5`~`cd3f90c`, `4229d9f`, `d48f25b` |
| 서버/체인 | 이슈 #0 종결 — outbox 지연·신뢰성(F1~F5·인라인 발사·웜업), 정상 31ms(SLO 100ms) | [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) |
| 서버 | 경합 수정 배치 1(C-1/C-2/C-3/C-5) + 감사 로그 미저장 수정(#6) | `4329c29`, `5fd8d24` |
| 전체 | **Enrichment Queue v1**(서버 dedup mapper + 컨베이어 + 참조뷰 + 결손 배지) — 스펙 Living 승격 | [20260725_130000](../history/20260725_130000_enrichment_queue_v1_complete.md) |
| 프로세스 | 코드맵+교훈 파일 체계(유지보수 doc-keeper 전담) · 기능 체크리스트 초판 · 에이전트 로스터 확장(qa-reviewer/doc-keeper/ui-designer) | `de79c50`, `d0c14a5`, `cbdc1e2` |
| 서버/체인 | **인시던트(21:29) 수정** — 체인 워커 created_logs 무절단(~50MB/6.5만 건) 전송 → :8080 이벤트 루프 GIL 동결 → 알림 타임아웃 연쇄. 발신측 500건 절단+`total_log_count`(C-5 계약 확장, `event_constants.py` 공용 상수). QA GO-WITH-FIXES(D-2 편승 적용) | [히스토리](../history/20260725_215500_chain_created_logs_truncation_incident.md) · [QA 리뷰](../../agent_workspace/reports/QA_chain_created_logs_truncation_review.md) |
| 서버/온톨로지 | **wafer_process lot/slot 확장**(사용자 config·핫리로드) — 수집기 lot_id/slot_no 기록, ProcessEvent props, enrichment 공정 이력 뷰 노출. 라이브 검증 통과(LOT-E\|25 분기 발화) | [보고서](../../agent_workspace/reports/Server_wafer_process_lot_slot_report.md) |

2026-07-24 이전 완료분은 [history/README.md](../history/README.md)와 [RELEASE_LOG](./RELEASE_LOG.md) 참조.

## ⏭️ 다음 단계 / 백로그 (Next / Backlog)

> 가동 중 트랙은 §현재 초점에 있다. 여기는 **대기열**이다.

**우선 순위 높음 (현재 초점 연동)**
- **대형 파일 인제션 — P1·P2 완료, P2 드릴 미실행, P3 미착수**
  - **P1** heavy 레인 ✅ 병합·드릴 PASS(비차단 180배, 유실 0). **P2** 체크포인트 재개 + sha256 dedup + #10 ✅ 병합·라이브 가동(`file_ingestion_checkpoints` 643행 실적재 확인).
  - **✅ P2 드릴 3종 PASS** (격리 환경 첫 사용, 2026-07-27). **D1 재개**: 30,000/100,000 지점에서 `taskkill /F` — 커밋 오프셋과 실제 행수가 정확히 일치(주입 예외가 아닌 실제 강제 종료에서 원자성 관측), 재개 후 10만 행·10만 고유키·**기대 키 누락 0**(`generate_series` 안티조인으로 "10만 행인데 다른 10만"까지 차단), 건너뛰기 **275ms** vs 재적재 ~219초. **D2 dedup**: 동일 재투입 1.22초 `SKIPPED` vs `__force__` 1,687초 `SUCCESS` — **1,383배** 분리. **D3 #10**: 비대칭 5+2로 총계 7(구 SET 의미론이면 2), 단일 타깃 대조군 1. **회귀 없음**: 이벤트 루프 11,371 샘플 p50 5.1ms·250ms 초과 0건, 체크포인트 UPDATE는 청크의 **0.0097%**. 보고서 `agent_workspace/reports/QA_p2_drills_isolated.md`.
  - **P3(미착수)**: 후단 backpressure(outbox 파일 단위 집계, 경합 배치 2·C-4와 통합) · PG COPY 벌크 경로(프로파일링 선행) · `batch_row_upsert` items 행 데이터 상한 · audit `old/new_value` 길이 상한(`crud.py:224-236` — 대형 텍스트 셀이면 500건 절단으로도 수십 MB 재발) · heavy 워커 수 설정화(heavy 간 직렬 해소, outbox 파도 증폭 주의).
  - 잔여 QA 후속: F2 라우팅 원자화 · F4 공유 큐 대기 · F5~F7. 운영 수칙: AUTO_UPDATE_GUIDE에 증분(delta) 산출 가이드.
- G2.5 서브그래프 직렬화 → G3(그래프 시각화 고도화, Neo4j 병행 타깃). 시간 범위 스캔용 엣지 인덱스(event_time)는 G2.5 쿼리 설계와 함께.
- **[신규 2026-07-26] Chain Replay(룰 재적용)** — 룰 변경 시 기존 데이터 재적용. 설계: 원천 keyset 재계산(그래프 resync 패턴) + 레이어링의 user 보호 + stale 소스 철회(H2-b 패턴 셀 버전) + dry-run 우선. 단계 R1(dry-run+적용)→R2(stale 철회)→R3(admin 위저드). 착수 전 확정: 매퍼 파일 컨텍스트 의존성·다중 룰 의존·enrichment dedup 별도 취급. P1 병합 후 R1 권장.
- map_split_registry(현재 초점 #2) — client-pm 착수.
- **[본딩 실험계획 — ✅ M1 완료(2026-07-26), 다음은 M2 = Universal Transfer Plan]** M1 산출물(Info 패널·역할 바인딩 config·core-summary·align 서버 단독 변환·rect 모드 폐기)은 [히스토리](../history/20260726_093200_bonding_plan_m1_info_panel_and_core_summary.md), 설계 확정(DT/Tape·전사 프리미티브·DOE)은 [히스토리](../history/20260726_093300_dt_tape_layer_universal_transfer_plan_design.md) 참조. **M2 골자 — Universal Transfer Plan 프레임워크**(사용자 확정): 모든 단계=전사 프리미티브 `(stage, target 맵 페인팅, assignments[소스, 소스 영역, 타깃 값(층/코어), 수량])`, 가용=총−fail류(역할 바인딩)−기전사(단계 전사 로그), 테이프 가용은 코어 fail의 DT-조인 투영으로 제외, 신규 단계=config stage 선언만(코드 불변). **영역 지정 정본 = 값 페인팅**(base 맵 값=층 번호, 코어 맵=사용 영역 — rect 모드는 폐기됨, 서버 region 계약은 M2 cells 모드용 존치). **관리 단위 = value(DOE)**: value ↦ {소스, knob/조건, 수량, 자연어 설명} — map_split_registry 직계 확장, SplitCondition=DOE로 온톨로지 정합(G3 "어느 DOE에서 불량 군집" 질의). M2 작업 항목: 역할 바인딩에 dt_log/dt_map 추가 + 잔여 계산 2단계(코어 잔여 vs 테이프 위 가용) + 계획 페인팅은 DT 테이프 맵 위 + 관리 테이블 2종(`bonding_experiment_plan`/`bonding_plan_layer` — localStorage 초안 승격) + 온톨로지 ExperimentPlan·PlanLayer·TransferEvent 일반화 + **by_eqp 장비별 align 적용·align 보정 모드**(시험 align 서버 변환 오버레이 + 확정 시 config 원자 저장 — `make_align_transform` 주입형이라 재사용 가능) → M3(실적 대조·중복 배정 감지·EDS 연동). M1 이월 잔재: total_chips는 실 운영에서 칩 레벨 total 테이블로 재바인딩 필요(현 config는 core_defect_map 풀맵 겸용 — escalation 승인분), 기존 bonding fake의 마스크 밖 (cx,cy) 미세 왜곡(미접촉). 착수 전 사용자 확인(잔여 2건): ①defect/EDS 원천 위치 ②실로그의 knob 형태.
- enrichment 실전 규칙(현재 초점 #3).

**그래프 트랙 미결 정책**
- 행 DELETE 시 그래프 정리 정책(스펙 §8 — materializer는 DELETE 스킵, stale 엣지 잔존). `idx_graph_edges_row_ref`가 구현 기반.
- 운영 수칙: outbox 7일 purge보다 materializer 장기 정지 시 증분 유실 → `/api/graph/sync {"table_name":"all"}` 복구(문서화됨 — [event_driven_backend §4.3](../architecture/event_driven_backend.md)).
- search ILIKE 프리픽스 인덱스 한계(pg_trgm/text_pattern_ops 검토) · stats GROUP BY 캐시 — 그래프 대형화 시.

**admin 이관 목록** ([중안 보고서 §E](../../agent_workspace/reports/Client_admin_ux_mid_report.md))
- Enrichment 규칙 CRUD API · Chain rule CRUD API · 워크스페이스 생성/검증 API · 파이프라인별 "신규 추가" 위저드 UI · 헬스 시간창 집계 API(+파일 로그 서버 검색/정렬).

**관찰/저순위**
- [드릴 2026-07-26] :8080 이벤트 루프 지터 0.68%(100~846ms 단발, 동결 아님) 발생원 미규명 — 장기 프로파일링은 별도 태스크(qa-reviewer 위임 후보).
- [드릴 2026-07-26] 드릴 생성물 정리 대기(총괄 수행) — config 항목·물리 테이블 `hvy_drill_big`(100,008행)/`hvy_drill_small`·워크스페이스 2식·FileIngestionLog 5행: [드릴 보고서 §7](../../agent_workspace/reports/QA_p1_live_drill_report.md) 목록 참조.
- 워크스페이스 레거시 config.json **읽기 경로의 최종 제거 시점** — 총괄 결정 대기(현재는 하위호환 읽기 + deprecation 경고 가동, 실 워크스페이스 14곳 전수 무영향 확인).
- 레이어링 표시 정합 의심 1건: `priority_source: chain_ingestion`인데 표시 값은 system 소스 값(38320 vs 3832) — chain_ingestion 서열 등재(#5 배치에 동승 가능) 후 재확인.
- 재생성 소스 삭제 시 경고 표시 UX(파이프라인이 소스를 재생성하는 것은 레이어링 설계상 정상 — 비이슈 종결됨).
- main.py 셀 히스토리 라우트 이중 정의(~2020 사장) · `client2/src/counter.js` 템플릿 잔재 — 소규모 정리 후보.
- 재기동 첫 체인 579ms(수용) — 잔여 mapper 첫 쿼리 웜업.
- [라이브 검증 PASS 관찰 3건, 다음 서버 배치 동승 후보] ① pytest가 라이브 로그 파일 오염 → 테스트 로거 분리 ② created_logs 절단 발동 시 무음 → `truncated N→500` 1줄 로그 ③ wafer_process lot_id UndefinedColumn 1회(21:48, 컬럼 핫추가 과도기 — #9와 같은 뿌리 추정).
- wafer_process에 `lot`/`slot`(기존)과 `lot_id`/`slot_no`(신규)가 중복 공존 — 데모 테이블이라 수용, 실전화 시 하나로 통일 필요. Lot 노드 label 신설 여부도 미결(현재 props까지만).
- 루트 `task/` 대기: `cursor_based_pagination_pending.md`, `total_count_sync_pending.md`, `desktop_hybrid_wrapper_plan.md`.

## 🐞 열린 문제 (Open Problems)

| # | 심각도 | 문제 | 도메인 | 상태 |
|---|---|---|---|---|
| 4 | 낮음 | `test_map_presets_api` 기존 실패(맵 프리셋 도메인, #0 이전부터) — **잔여는 이것 1건뿐**(enrichment 테스트 격리 버그는 2026-07-25 해소, 현재 스위트 177 passed / 1 failed) | Client·Server | 대기 |
| 5 | 중간 | **경합 점검 잔여 리스크(수정 배치 2 후보)** — C-4(체인 큐 독점·HOL, 매퍼 의미론 협의 필요)·C-6(동시 upsert 행 락 순서)·C-8(런타임 ALTER 락 컨보이)·C-9(커넥션 풀 합계>max_connections)·C-10(워처 .tmp 필터 부재)·C-11(WS 직렬 전송) + created_logs 무상한 전송 잔여. 상세: [점검 보고서](../../agent_workspace/reports/Server_contention_audit.md) (C-7은 그래프 키셋 청킹으로 해소됨) | Server | 대기 |
| 2 | 낮음 | 맵 이월 시 A/B의 x·y·val 컬럼명이 크게 다르면 자동 정합 안 됨(저장 전 Advanced Column Mapping 수동 확인 필요) | Client | 대기(관찰) |
| 3 | 정보 | 미리보기 브라우저 pane이 비-compositing → rAF/ResizeObserver 자동발화·CSS transition 프리즈로 라이브 UI 자동검증 제약(실제 브라우저 무관) | 검증환경 | 알려짐 |
| 9 | 중간 | **config_watcher가 원자적 쓰기(temp+rename)를 감지 못함** — on_modified만 처리해 에이전트 Edit류 저장 시 기존 테이블 ALTER가 조용히 누락(on_moved 미처리). 스키마 API는 config 싱글턴이라 200이어도 물리 반영 증거 아님 | Server | 대기(수정 소형 — on_moved 보강) |
| 10 | 낮음 | audit_cache total_count 과소 표기(QA D-1) — 멀티 target-table tx에서 테이블별 total_log_count가 SET 덮어쓰기. 기존 결함(회귀 아님), production_plan 체인+enrichment 동시 트리거로 도달 가능 | Server | 대기(P2 동승) |
| 20 | 중간 | **변환 구현이 아직 둘이다 — `bonding_plan.py`가 자기 사본을 갖고 있다**(구 A2의 정체). doc-keeper 4차가 총괄의 오인을 잡았다: `bonding_plan.py`는 `map_overlay`를 **참조 0건**이고 자체 `normalize_align`/`make_align_transform`(`:74`,`:140`)을 쓴다. `transfer_plan.py`도 `resolve_binding`/`build_key_filters`/`load_overlay_config`만 쓰고 **정렬 함수는 안 쓴다**. 즉 A1 수정이 `bonding_plan`에 전파되지 않은 이유가 이것이고, 오버레이에서 방금 없앤 "두 구현" 문제가 **가용량 산출에는 그대로 살아 있다**(`bonding_plan.py:199-204` bbox 항 없는 구 산술 — 라이브 오버라이드 없어 휴면). 부수 발견: 클라가 서버 정렬 좌표 소비를 멈춘 뒤로 `map_overlay`의 정렬 함수군(`resolve_align`/`make_frame_transform`/`_frame_transformer`/`_frame_phys_params`) **운영 소비자가 0**이다 — 호출처는 엔드포인트 자신과 자기 테스트뿐. 폐기 여부 판단 필요 | Server | 대기 |
| 11 | 중간(격하) | **좌표 변환 서버-클라 드리프트** ([감사](../../agent_workspace/reports/QA_map_transform_logic_audit.md)) — F1: rot=90/270 비등방 칩에서 transformer가 회전 치수·비회전 chip 혼용 · F2: 엔진 미장착 fallback 타원 ±1 어긋남 · F3[중]: 클라 getPhysicalCoords의 mm 오프셋 반올림 혼입(서버 정의가 정론 — 경계 계약 명문화 필요). **M1 align이 결함 지점을 구조적으로 우회 완료**(`bonding_plan.make_align_transform` — cell_to_physical 순수 인덱스 변환만, 엔진 fallback 무참여 + 90/270 치수 스왑 규약 + 규격 불명 시 `align_unavailable` 명시 실패). transformer 자체의 F1/F2 수정과 F3 계약 명문화는 잔여(현 소비자는 안전 경로만 사용) | Server·Client | M1 우회 완료 — 근본 수정 대기 |
| 16 | **높음(격상)** | **테스트 스위트가 라이브 환경으로 샌다 — 2계통 실증** ⓐ **운영 PostgreSQL에 DDL 발행**: `main.py` import 시 모듈 레벨 `Base.metadata.create_all`(main.py:44)이 실 DB에 대해 실행되어, 테스트만 돌려도 신규 테이블이 라이브에 생성된다(P2에서 실제 발생 — 빈 테이블이라 무해했으나 경로가 위험). ⓑ **사용자 config에 써넣는다**: `test_map_presets_api`가 `POST /api/map-presets`로 라이브 `server/config/maps.json`을 수정한다. 실증 — 현재 프리셋 키가 `['custom_1784890104442', 'core_std', 'base_std', 'tape_std']`이고 첫 항목이 테스트 산물(총괄 직접 확인). 같은 테스트가 `maps.json.sample`에만 있는 키를 라이브에서 찾아 단언하므로 **세션 내내 "상시 허용 실패"로 취급돼 왔다 — 항상 실패하는 테스트는 스위트 전체의 신호를 죽인다.** **✅ ⓑ 해소(`9a8ede8`)** — 두 오염 테스트 격리. `test_map_presets_api`는 `tmp_path` + `MAPS_CONFIG_PATH` 패치, 단언을 `set(presets) == {심은 키}`로 써서 **격리가 풀리면 즉시 깨지게** 했다. `test_file_ingestion_callback_direct`는 핸들러가 이미 경로를 생성자 인자로 받으므로 패치 없이 `tmp_path` 주입으로 끝났고, `config.json` 쓰기는 **제거**(폐기 개념 + `columns` 키 무소비 + 테이블명이 `default_table_name`으로 동일 해석) 후 재생성 시 깨지는 네거티브 단언을 넣었다. **증명은 바이트 동일성** — `maps.json`의 sha256·크기·**mtime**까지 불변, `ingestion_workspace` 9,230파일 `changed=0`. 생긴 3파일이 수집기 산물임은 **pytest를 안 돌린 동일 길이 창 대조군**으로 실증. **스위트 414 passed / 0 failed — 허용 실패 소멸.** ⓐ(운영 DB DDL)는 잔존하나 테스트 엔진은 전부 sqlite 메모리/tmp로 확인됨. 라이브 잔재 2건(`maps.json`의 `custom_…`, `inventory_master/config/config.json`)은 **사용자 자산이라 미삭제 — 원본 미상·복구 불가로 고지함** | Server | ⓑ 해소 / ⓐ 대기 |
| 15 | 중간 | **`Wafer` label에 이질적 정체 혼입**(2026-07-26 온톨로지 리뷰 발견) — `wafer_slot_history.wafer_id`(예 `A123`)와 `core_wafer_map.core_lot\|core_slot`(예 `LOT-A\|05`)이 같은 label에 공존해 서로 조인 불가. 더 근본적으로 **후자는 DT 계층 판명으로 실은 테이프 위치**(스펙 §7.5b)라 "테이프 91개를 Wafer라 부르는" 상태. 방치 시 불량 역추적이 엉뚱한 개체를 지목. **M2에서 dt_map/dt_log 올릴 때 정리 필수**. 파생 결정: 층 배정 온톨로지 매핑(§14-4)도 같은 패턴이라 보류, 별도 label(`PlanLayer`)로 §7.5c node_class 작업 시 처리 | Server·온톨로지 | M2에서 처리 |
| 14 | 중간 | **맵 push 경로 기존 결함 3종**([QA M2 리뷰](../../agent_workspace/reports/QA_transfer_plan_m2_review.md) 부수 발견, **M2 회귀 아님 — 전 맵 공통**) — ⓐ `limit=2000` + `replace_map` 조합에서 2000셀 초과 맵의 데이터 소실 가능(현행 프리셋 최대 1600셀이라 미발화) ⓑ `GET /tables/{t}/schema`가 미존재 테이블에도 200 반환(존재 확인 불가) ⓒ 클라 `CURRENT_USER`가 빌드 시점 값으로 박힘(번들 확인) | Server·Client | 대기 |
| 13 | 중간 | **`crud.load_table_config()`가 JSON 파싱 실패 시 로그 없이 `{}` 반환** — 가동 중에는 `refresh_dynamic_models`의 빈-config 가드가 막지만, **손상된 config로 재기동하면 전 테이블이 조용히 사라진다**. 최소 `logger.error` + 기동 시 명시 실패(fail-fast) 검토. CONFIG_GUIDE 함정 A로 문서화됨 | Server | 대기(소형) |
| 17 | 중간 | **계획 자재 500행 초과 시 영구 저장 불가** (QA-B의 C3) — 클라가 `limit=500`으로 조회하고(`client2/src/transfer_plan.js:1068/1104`) `total > rows`면 로드 실패로 강등하는데, 그 강등이 쓰기 보류로 이어지므로 **자재 500행을 넘긴 계획은 저장 경로가 영구히 닫힌다**. 강등 자체는 옳다(절단된 상태로 prune하면 전량 삭제) — 페이징이나 상한 상향이 필요 | Client·Server | 대기 |
| 18 | 중간 | **오버레이 기하 시그니처에 물리 파라미터 누락** (QA-B의 C7) — `currentGeomSignature()`(`client2/src/map_editor.js`)가 cols/rows/start/invertY/rot/side만 보고 `phys_*`(칩 피치·오프셋·직경·edge margin)를 빼먹어, 물리 규격을 바꾸면 오버레이가 **조용히 안 따라온다**. 기존 결함이나 신규 `importOverlayToGrid`가 어긋난 좌표를 `gridData`에 써 넣어 **표시 오류에서 데이터 오염으로 승격**됐다. **오버레이 변환 일원화 작업의 수용 기준에 포함시켰다** | Client | 일원화 작업에 동승 |
| 19 | 낮음 | **페인트 잠금 콜드 스타트 fail-open** (QA-B의 C4) — `degrade()`가 유지하는 "직전 값"이 로드 직후에는 기본값 `{enabled:false}`(`client2/src/map_editor.js:37`)라, **첫 조회가 실패하면 8개 강제 지점이 열린 채 시작**한다. 칩으로 표시는 되므로 *조용한* fail-open은 해소된 상태 — "fail-open 제거"라는 서술만 과장이었다 | Client | 대기 |
| 12 | 낮음 | **임베디드 모드 `trigger_ws_refresh` 레거시 경로 C-5 미적용** — main.py 임베디드(비-DECOUPLED) 콜백은 created_logs 절단 계약(C-5) 밖(레거시 5000 게이트). 분리 모드 운영에서는 무영향 — 드릴 관찰로 등재 | Server | 대기(저순위) |

**종결(2026-07-25):** #0 체인 outbox 지연·신뢰성(31ms) · #1 IntegrityAndQAExpert 스킬 웹 전환 · #6 감사 로그 DB 미저장 · #7 런타임 테이블 물리 CREATE · **#8 graph 워커 신규 테이블 미인지(G1 materializer의 SYSTEM_RELOAD 구독으로 해소)**.

## 🔤 코드 체계 (Code Index) — 약칭이 무슨 뜻이고 어디에 정의돼 있나

**트랙 단계 코드** (전역 유효 — 여기가 정의처)

| 코드 | 뜻 | 정의 위치 |
|---|---|---|
| `G1`~`G4` | 온톨로지 그래프 트랙 단계 (G1 materializer → G2 추적 → **G2.5 LLM 액세스** → G3 불량추론 → G3.5 상태물화 → G4 Neo4j) | [ONTOLOGY_GRAPH_SPEC §8 단계표](../spec/ONTOLOGY_GRAPH_SPEC.md) |
| `P1`~`P3` | 대형 파일 인제션 대응 단계 (P1 heavy 레인 **완료** → P2 체크포인트 → P3 backpressure·COPY) | 이 보드 백로그 |
| `M1`~`M3` | 본딩/전사 계획 단계 (M1 조회 **완료** → M2 Universal Transfer Plan **진행중** → M3 실적 대조) | 이 보드 백로그 |
| `R1`~`R3` | Chain Replay(룰 재적용) 단계 | 이 보드 백로그 |
| `C-1`~`C-11` | 경합 점검 항목 (하이픈 있음 — 아래 QA 코드와 구별) | [Server_contention_audit.md](../../agent_workspace/reports/Server_contention_audit.md) |
| `F1`~`F5` | 체인 outbox 신뢰성 수정 (이슈 #0) | [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) |
| `S1`~`S8` | config 온보딩 시나리오 체크리스트 | [CONFIG_GUIDE](../guide/CONFIG_GUIDE.md) |
| `#0`~`#14` | 열린 문제 번호 | 이 보드 §열린 문제 |

**⚠️ QA 리뷰 결함 코드는 문서 로컬이다** — 리뷰마다 `F1`/`D1`/`C1`이 새로 시작하므로 **반드시 문서명과 함께** 인용할 것(예: "M2 QA의 F1", "P1 QA의 F1"은 서로 다름).

| 리뷰 문서 | 쓰는 코드 | 대표 사례 |
|---|---|---|
| [QA_transfer_plan_m2_review](../../agent_workspace/reports/QA_transfer_plan_m2_review.md) | `F1`~`F7`(서버) · `C1`~`C11`(클라) | F1=degraded 시 remaining 과대, C5=plan_id 미잠금 데이터 소실 |
| [QA_large_file_p1_review](../../agent_workspace/reports/QA_large_file_p1_review.md) | `F1`~`F7` | F1=QUEUED TTL 과소 표시 |
| [QA_workspace_config_deprecation_review](../../agent_workspace/reports/QA_workspace_config_deprecation_review.md) | `D1`~`D6` | D1=파일 처리 중 config 리로드 정합 |
| [QA_chain_created_logs_truncation_review](../../agent_workspace/reports/QA_chain_created_logs_truncation_review.md) | `D-1`,`D-2` | D-1=total_count 과소(이슈 #10) |
| [QA_map_transform_logic_audit](../../agent_workspace/reports/QA_map_transform_logic_audit.md) | `F1`~`F5` | F1/F2=변환 드리프트(이슈 #11) |
| G1 그래프 QA(이력) | `H1`,`H2`,`H2-b` | H1=provenance 위조, H2-b=빈 산출 정리 |

**규율**: 리뷰 결함이 배치를 넘어 살아남으면(미조치 이월) **이 보드의 `#번호` 열린 문제로 승격**해 추적한다 — QA 코드로만 남기지 않는다.

## 🧭 환경 메모 (Env Notes)
- 로컬 테스트 테이블 `sample_map`은 `server/config/table_config.json`(gitignored)에만 존재 — 운영 무영향.
- 서버 기동: `python run_decoupled_app.py` (웹 :8080 + 워커 4종). 프론트 개발: `cd client2 && npm run dev`. dist는 추적·서빙 대상 → 소스 변경 시 `npm run build` 후 dist 커밋.
- 운영 서버는 `git pull` 후 이슈 #0 절차(재기동→인덱스→purge→VACUUM, `scripts/setup_db_performance.py`) 필요.

---
*갱신 규율: 이 보드는 상태의 단일 원천이다. 새 작업/문제/해결이 생기면 즉시 이 파일을 고친다. 이력 상세는 history, 이 파일은 "지금 어디까지 왔고 무엇이 문제인가"의 요약.*
