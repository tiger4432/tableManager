# 소스→원장 변환 셋업 러너북 (as-is, 2026-08-17 실측)

> 지금 이 순간 코드가 실제로 읽는 것 기준. 이상형이 아니라 **현재 걸어야 하는
> 길**이며, 각 단계의 함정을 같이 적는다. 1단계(전환 목록)의 입력이기도 하다.

## 0. 한눈에 — 절차 7걸음

| # | 하는 일 | 편집/실행 대상 | 확인 방법 |
|---|---|---|---|
| 1 | 테이블 실재 + 표 선언 | DB(인제션) + `table_config.json` | 그리드에 표가 뜸 |
| 2 | 소스 선언 | `ledger_config.json` → `sources.<이름>` | 서버 기동/리로드 시 검증 통과 |
| 3 | 변환기 선택 | 같은 블록의 `chain_mapper` | 아래 «두 갈래» 참조 |
| 4 | (필요시) 새 낱말 | 어휘 config (R-M, ontology층만) | `/admin/ledger/vocabulary`에 origin:config로 |
| 5 | 드라이런 | `POST /admin/ledger/dry-run` (strict 토큰) | 나올 원자 봉투 + 거절 사유, 쓰기 0 |
| 6 | 백필 | `python -m ledger.backfill --source <이름>` | 분자/원자/거절 수 출력 |
| 7 | 확인 | `/api/ledger/structure` | 새 엣지에 원자 수·출처 |

읽기측(트렌드·대조에 «보이게»)은 별도 8~9걸음: `siblings_axes.json`(geometry·
ledger_subject·attribution) + 온톨로지(`mechanism_models.json` bindings ·
`ledger_journey.json` labels). — 소스→원장 자체는 1~7로 끝난다.

## 1. 변환기 선택 — 두 갈래 (3걸음의 본론)

### 갈래 A — 신뢰 Python mapper (지금 유일하게 «걸어 본» 길)
```jsonc
"sources": { "lot_event": {
    "kind": "lineage",
    "chain_mapper": { "mapper_id": "lot-event", "version": 1 },
    ...columns/occurred_at/watermark...
}}
```
- mapper_id는 `server/mappers/ledger_lot_event_mapper.py`처럼 **코드가 등록**돼
  있어야 한다. 새 모양 = 새 파이썬 파일. 리스트 짝짓기·두 줄 문법 같은 구조
  변환은 이 갈래만 가능.
- 라이브 실증: `lot_event` 1건 (현재 라이브 선언의 전부).

### 갈래 B — canonical Profile (계약은 완비, **실전 0회** — 첫 사용자가 됨)
```jsonc
"sources": { "<이름>": {
    "chain_mapper": { "mapper_id": "canonical-profile", "profile_id": "<프로파일ID>" }, ... },
"profiles": { "<프로파일ID>": {
    "profile_version": 1,
    "packs": ["transfer@1"],
    "mappings": [{ "use": "transfer/movement",
                   "bind": { "subject": "column:ITEM_ID", "from": "column:SRC",
                             "to": "column:DEST", "occurred_at": "column:EVENT_TIME" },
                   "status": "human_approved" }] }}
```
- 스키마 정본은 문서가 아니라 **`server/ledger/source_profile.py`** — binding은
  `column:` / `constant:` / `lookup:` 셋, 매핑마다 status(human_approved/
  inferred)·origin(user_declared/system_suggested/imported)·승인 상태가 계약에
  이미 있다(마법사 대비 설계).
- 로드 시 profiles 섹션 통째 검증 — 틀린 profile_id·미등록 Pack은 기동/리로드에서
  이름 붙은 거절.
- ⚠️ 등록된 Pack 목록은 `source_profile_builtins.py`가 정본 — **여기 없는 claim은
  못 쓴다**(2단계 Pack 라이브러리가 채울 자리).

## 2. 문서·파일 리스트 (역할별)

### 읽는 것 (셋업 전 필독 순서)
1. `ontology_codex_plan_v2/02_CLAIM_MAPPING_PROFILE.md` — Profile/Pack 계약의 뜻
2. `server/ledger/source_profile.py` — Profile 스키마 **정본** (모듈 docstring)
3. `server/mappers/ledger_lot_event_mapper.py` — 갈래 A의 실물 예제
4. `server/config/ledger_config.json` 현행 — 살아 있는 선언 예
5. `docs/process/LEDGER_RULINGS.md` R-M(어휘)·R-N(대장)·R-O(뿌리 키)
6. `docs/guide/LEDGER_GUIDE.md` §1(모듈 지도)·§4(게이트)

### 편집하는 것
- `server/config/table_config.json` — 표 선언 (초안 스크립트:
  `server/scripts/table_config_from_schema.py`)
- `server/config/ledger_config.json` — `sources` + (갈래 B) `profiles`
- (낱말 필요시) 어휘 config — admin 라우트(`/admin/ledger/save`, target=predicate)
  경유가 정석 (직접 편집 말고)
- (읽기측까지 가면) `siblings_axes.json` · `mechanism_models.json` ·
  `ledger_journey.json`

### 실행하는 것
- `POST /admin/reload-configs` — 편집 후 핫리로드 (DB 경로만 예외: 재기동)
- `POST /admin/ledger/dry-run` — 저장 전 의무 (3단 저장 규율)
- `conda run -n assy_manager python -m ledger.backfill --source <이름>`
  (+`--reset-cursor` 재주행, `--fetch-rows`, `--config`) — ⚠️ bare python 금지,
  `PYTHONIOENCODING=utf-8`
- `GET /admin/config/resolve` — 「내 config가 먹었는가」 문장

## 3. 함정 목록 (실측·실사고 기반)

1. **갈래 B는 아무도 안 걸어 봤다** — profiles 라이브 0건. 첫 프로파일은 반드시
   드라이런→소량 백필→structure 확인 순서로, 등가 하니스(1단계) 나오기 전엔
   기존 소스 전환에 쓰지 말 것(신규 소스 전용).
2. **occurred_at 포맷·타임존** — `%Y-%m-%dT%H:%M:%S` + `Asia/Seoul` 철자를
   현행 `lot_event` 선언에서 복사할 것. 틀리면 번역 시점 거절.
3. **business_key가 시각을 포함하면** 같은 순간의 두 사건이 한 행으로 붕괴
   (축 7 실사고 — `txn_seq`가 있으면 키에 넣어라).
4. **워터마크 없는 표** — 단조 증가 컬럼(updated_at·txn_seq)이 없으면 재주행
   전략을 먼저 정할 것(`--reset-cursor` 전량 재주행뿐).
5. **admin 라우트는 토큰** — 없으면 401인데 일부 화면이 조용히 빈 목록으로
   보임(반려 상태). curl로 칠 때는 `X-Admin-Token`.
6. **원자가 안 생기는 «정상»** — 저장·리로드까지 해도 6걸음(백필)을 돌리기
   전엔 원자 0이 맞다. structure의 0은 결함이 아니라 미실행.
7. **읽기측 미선언** — 원자가 있어도 `siblings_axes`에 축·기하가 없으면 트렌드·
   대조에 안 보인다(등재 ≠ 소비). 소스→원장 완료의 정의를 7걸음까지로 좁혀서
   혼동을 피할 것.

## 4. TO-BE — 전환 계획 완주 후 이 길이 어떻게 짧아지는가

같은 일곱 걸음이 어디로 가는지, 단계 번호(01~07)와 함께.

| as-is 걸음 | to-be | 만드는 단계 |
|---|---|---|
| 1 표 선언 (JSON 손편집) | 그대로 두되 마법사가 감지·초안 (스크립트 흡수) | 04 |
| 2 소스 선언 (sources 블록 손편집) | **인터뷰 4~5문** → 시스템이 초안 (원장 용어 0개) | 04 |
| 3 변환기 두 갈래 중 선택 | 선택 소멸 — **Profile이 기본**, Python mapper는 구조 변환(계보 등) 소수 전용, legacy 번역기는 은퇴 | 01·02·07 |
| 4 낱말 등재 (라우트 직접 호출) | 마법사 안에서 「이걸 말할 낱말이 없습니다 → 만들까요?」로만 등장 | 03·04 |
| 5 드라이런 (별도 호출) | 마법사에 내장 — **작성하는 동안** 문장·원자 실시간 갱신 | 04 |
| 6 백필 (CLI, conda 함정 포함) | 현황판의 **[실행] 버튼** — 결과 수치·거절 사유 화면에 | 05 |
| 7 확인 (structure 수동 조회) | **현황판이 사슬 전체를 자동 표시** — 「N중 M 충족, 다음: ○○」 | 05 |
| 8~9 읽기측·온톨로지 (존재 자체를 알아야 함) | 현황판이 **결핍을 이름으로** 안내 (「축 미선언」「바인딩 0」) — Pack의 전제 선언이 근거 | 02·05 |

### 함정 사망 명부 (§3의 일곱이 어느 단계에서 죽는가)

| 함정 | 죽이는 것 | 단계 |
|---|---|---|
| 1 Profile 실전 0회 | 등가 하니스 실측 + Pack 라이브러리 | 01·02 |
| 2 occurred_at 포맷 손복사 | 마법사가 시각 컬럼·포맷을 감지해 후보 제시 | 04 |
| 3 business_key 붕괴 | 인터뷰의 「같은 행이 다시 오면?」 + 드라이런 중복 경고 | 04 |
| 4 워터마크 부재 | 마법사가 단조 컬럼 후보 제시, 없으면 재주행 전략을 묻기 | 04 |
| 5 401이 조용한 빈 목록 | 셋업 4금칙 A-3 (결핍은 이름·행동은 버튼) | 03~05 전반 |
| 6 백필 전 원자 0 혼동 | 현황판 「원자 0 — 백필 미실행 [실행]」 | 05 |
| 7 등재≠소비 (읽기측 미선언) | Pack 전제 선언 → 현황판 결핍 표시 | 02·05 |

+ §7-② «영원히 조용»(바인딩·라벨 유령 경로)은 06 합의 검사기가 죽인다 — as-is
함정 목록엔 없지만 to-be가 반드시 덮어야 할 여덟째 함정이다.

### 최종 상태의 정의 (00_MASTER_PLAN 최종 목표의 러너북판)

새 테이블 하나를 잇는 사람의 여정: **인터뷰 → 문장 판정 → 저장 → [백필] →
현황판 완충.** 문서 0회 · JSON 손편집 0회(고급 뒷문 제외) · 자유 기입 열거형 0 ·
행동 없는 거절문 0 · legacy 경로 0. 이 러너북의 §0~3은 그날 «역사 문서»가 된다 —
그때까지는 이 문서가 걷는 길이다.
