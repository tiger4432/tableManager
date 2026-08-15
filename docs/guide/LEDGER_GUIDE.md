# 📒 정준 원장 (Canonical Ledger) — 번역기 쓰는 법 · 숫자 읽는 법

> **Status:** 🟢 Living | **Last-verified:** 2026-08-15 2차 (셋업 통폐합 — 선언·순서 이관, 기전 config 블록 이름 정정) | **Owner:** Server / Ledger | **Source-of-truth:** `server/ledger/` · `server/ledger_trace.py` · `server/ledger_selection.py`
>
> **이 문서가 소유하는 것: HOW(코드).** 번역기를 «쓰는» 절차와, 운영자가 숫자를 읽는 절차.
> 🔴 **[2026-08-15 분할] 「무엇을 선언하는가」는 이 문서가 더 이상 소유하지 않는다** —
> `ledger_config.json`의 키 표(종전 §3 ②·②-bis·②-ter)와 마이그레이션·백필의 **순서·명령**은
> **[guide/ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md)** 하나로 옮겼다.
> 소유자 지시(「온톨로지 원장 셋업 관련 문서 하나로 통폐합」)이고, 근거는 **선언 절차가 두 벌이면 한 벌이 낡는다**는 것이다
> (같은 날 운영자 가이드 셋이 이미 삭제된 것을 돌리라고 말하고 있었다). **선언은 JSON, 번역기는 파이썬 — 이 문서는 뒤엣것만 소유한다.**
> **WHY는 여기 없다** — 왜 원자가 7필드인지, 왜 어휘가 닫혀 있는지, 왜 해결 서열이 4계급인지는
> [architecture/CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md)이 소유한다. **다시 쓰지 않는다.**
> **EXACTLY-WHAT**(컬럼·인덱스·계약)은 [spec/LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md).
> **판정**은 [process/LEDGER_RULINGS](../process/LEDGER_RULINGS.md) — 🔴 거기 없는 판정은 내려진 적이 없는 것으로 친다.
> **운영에서 무엇을 어느 순서로 돌리는가**는 [process/OPERATOR_RUNBOOK §6·§8](../process/OPERATOR_RUNBOOK.md)이 소유한다 — 이 문서는 **순서를 다시 적지 않고** 명령의 뜻만 적는다.

> ⚠️ **이 문서의 모든 수치는 이 개발 박스(`assy_manager` / `assy_qa`) 실측이고 운영의 증거가 아니다.**
> 측정 시점은 2026-08-13이며, 인용할 때 그 귀속을 떼지 말 것.
>
> **이번 라운드 (2026-08-14 밤 · 걷기 대조 + 기전 config — `5ea29b6`·`87374a5` 리빙 동기화)** — 🔴 **§1.2에 `server/ledger_walk_contrast.py` 행 신설**:
> `/siblings`의 `scope=`가 엔진을 바꾸는 자리이고 **항목 목록이 0줄**이다(선언은 필터가 아니라 예산). 같은 커밋으로 **수치 필드가 후보가 됐고**(주어당 한 값으로 접은 뒤 같은 랭킹 사다리 — 둘째 임계 없음), **`wafer` 마킹 축**이 `siblings_axes.json.sample` 선언 한 항목으로 생겼으며(파이썬 0줄 — 「이 두 장 vs 나머지」가 처음으로 표현 가능), **요청된 scope 값의 회계**(`unnest` LEFT JOIN — 못 찾은 값을 흡수하지 않고 이름 대며 탈락시킨다)가 들어왔다. 라우트 계약은 [backend §2](../architecture/backend.md)(**이 라운드에 드디어 행이 생겼다**), 선언은 [CONFIG_GUIDE §1](./CONFIG_GUIDE.md). **§4.6-bis의 기전 층 문단을 현행으로 정정**했다 — `mechanism_models.json`은 실재하고 바인딩은 데이터가 실재하는 날 켠다(`87374a5`).
>
> **직전 라운드 (2026-08-14 3차 · 관측 번역 — R-2026-08-14-D + R-2026-08-14-E ⓐ)** — 🔴 **이 문서의 §3이 이제 «문법 둘»을 가르친다.**
> ① **어휘가 열하나**가 됐다 — `observed`(subject `Wafer`, `value` 목적어, `required` = `finding_kind`·`method`·**`run_uid`**).
> 🔴 **`run_uid`가 required인 것이 분모 규율이 원장 «안»에서도 서는 자리**다(「보이드 3개」는 「몇 개를 봤는데 3개」 없이는 아무 뜻이 없다).
> 짝인 `measured`는 **일부러 등재하지 않았다** — 발화하는 것이 없다.
> ② **소스 선언에 `kind`가 생겼다**(기본 `lineage`, 기존 선언은 한 글자도 안 바뀐다) — 두 번째 문법 **`observation`**은
> 한 행이 곧 한 발화라 분자 조립도 이벤트 짝도 없고, **선언 키와 필수 컬럼 집합이 다르다**(§3 ②-bis).
> 🔴 **세상의 시각이 관측 행에 «없다»** — 선언된 런 조인(`inspection_run.observed_at`)에서 읽고, 런을 못 찾은 발견은 **거절**이다.
> 🔴 **커서가 세계 시각이 아니라 «키셋»**(`updated_at, row_id`)이다(§4.3 · §4.4).
> ③ **걷기 의미론이 코드 목록에서 «선언»으로 올라갔다**(R-2026-08-14-E ⓐ) — 술어마다 `traversable`·`direction`이고
> `ledger_trace.LINEAGE_PREDICATES`는 리터럴이 아니라 **어휘에서 파생**된다. **동작은 불변이고 그 불변이 단언돼 있다.**
> 🔴 **`observed`는 `traversable: None`** — 걷기가 **아예 인출하지 않는다**(R-D 부칙 ①: 웨이퍼 하나가 관측 수만 건을 든다).
> 실측으로 3홉 추적은 여전히 **주장 174건 / 관측 0건 · 5.2–5.8 ms**이고 같은 표에 **102,177 관측 원자**가 손대지 않은 채 앉아 있다.
> 계약은 [spec §3.7·§3.7-quinquies·§4.8](../spec/LEDGER_TECHNICAL_SPEC.md), 판정은 [R-2026-08-14-D·E](../process/LEDGER_RULINGS.md).
>
> **직전 라운드 (2026-08-14 2차 · 구조 뷰 — 읽기 라우트 하나)** — 🔴 **읽는 쪽 모듈이 «둘»이 됐다**(§1.2): `ledger_structure.py`가
> `GET /api/ledger/structure`를 답한다. **유형 수준**이고(`/trace`가 인스턴스 수준이므로 그 보완이다), 🔴 **응답 어디에도 손으로 적은
> 노드·엣지 목록이 없다** — 선언된 절반은 어휘에서, 관측된 절반은 원장 한 번의 `GROUP BY`에서 **생성**된다.
> **번역기를 붙이는 사람이 알아야 할 것 하나**: 술어를 어휘에 더하면 이 라우트를 **한 줄도 안 고치고** 화면에 나타나고,
> 어휘에 없는 모양을 발화하면 **`undeclared`로 화면에 뜬다**(조용히 버려지지 않는다 — §4.6). 어휘에 `label_ko`가 붙었고(§1.1)
> **집행 지점은 단위 테스트 하나**다. 계약은 [spec §3.7-quater · §4.7](../spec/LEDGER_TECHNICAL_SPEC.md), 라우트는 [backend §2](../architecture/backend.md).
>
> **그 앞 라운드 (2026-08-14 · 어휘 확장 + 생성기 소스)** — 🔴 **어휘가 일곱에서 «아홉»이 됐다**(§1.1 · §3 ①).
> `processed_with`(공정 조건 — **설계가 예약해 둔 낱말이 열린 것**)와 `has_param`(레시피 설정값), 그리고 새 개체 타입 **`Recipe`**(🔴 `rev`가 **키 재료**).
> 🔴 **일곱을 못박던 테스트가 «이름 그대로» 아홉을 못박는다** — 완화가 아니라 판정을 적은 것이고, **열 번째는 지금도 빨갛다.**
> 그리고 **§3-bis 신설**: **생성기 소스**(테이블 번역기가 아닌 것)는 파생·subject 타입을 **`ledger_config.json`이 아니라 자기 안에** 선언한다 —
> 없는 컬럼 일곱을 지어내 운영자 config에 넣는 것이 대안이었다. 계약 절반은 [spec §3.7·§4.1-bis](../spec/LEDGER_TECHNICAL_SPEC.md).
>
> **그 앞 라운드 (2026-08-14 · `92547c3` · R-2026-08-13-H-bis)** — 🔴 **번역기는 더 이상 «자기 스코프를 열지 않는다»**(§1.1 · §2 · §3 ③).
> `backfill.run`의 분자 루프가 `gate.building_molecule`을 들고, 번역기를 **손으로 모는 호출부(테스트 포함)는 자기가 열어야 한다** — 안 열면 `RuntimeError`.
> 🔴 **다만 오늘 동작은 하나도 안 바뀐다**: 번역기 클래스는 하나이고 `backfill.run`의 호출자는 자기 CLI `main()`뿐이라
> **가치는 미래의 두 번째 번역기 작성자가 맞을 `RuntimeError`**다(「착지 ≠ 배선」). 함께: `screen_molecule`의 **거절만** 예외가 됐고
> **「할 말 없음」의 `[]`는 그대로 반환**이며, `store.write_batch(reasons=…)`는 **필수 키워드 인자**가 됐다.
>
> ⚠️ **§4.4·§4.6의 `lot_event` 라이브 판독은 `eb1ae8b`·`0198e7e` «이전»에 뜬 것**이고 그 자리에 귀속을 달아 두었다 — 재백필하지 않았기 때문이다.
> **그 이전 라운드 기록은 [`docs/history/`](../history/)에 있다** — 이 헤더에 쌓지 말 것.

---

## 0. 두 독자

| 당신이 | 읽을 곳 |
|---|---|
| **새 소스를 원장에 붙이려는 개발자** | **선언은 [ONTOLOGY_LEDGER_SETUP §3](./ONTOLOGY_LEDGER_SETUP.md) 먼저** → §1 모듈 지도 → §2 쓰기 경로 → **§3 번역기 쓰는 법** |
| **백필을 돌리고 숫자를 읽어야 하는 운영자** | **순서·명령은 [ONTOLOGY_LEDGER_SETUP §2](./ONTOLOGY_LEDGER_SETUP.md)** → §4(숫자 읽는 법) → §2.4(한 트랜잭션이 덮는 것) |

🔴 **안 돌아도 아무것도 안 깨진다.** `server/` 안에서 `server/ledger`를 import하는 부팅 경로가 없다.
원장은 기존 시스템의 **소비자로 태어났다** — `lot_event`를 읽고 **자기 테이블 둘에만** 쓴다.
쓰기 경로·`crud`·체인·그래프·참조뷰·맵은 한 줄도 바뀌지 않았다.

---

## 1. 모듈 지도

### 1.1 `server/ledger/` — 쓰기 쪽

각 모듈의 docstring이 정본이다. 아래는 **찾아가기 위한 색인**이지 요약본이 아니다.

| 모듈 | 한 줄 계약 | 이 모듈이 소유하는 불변식 |
|---|---|---|
| `envelope.py` | 설계 §3의 7필드를 파이썬 객체 하나(`Atom`)로. 11컬럼 평탄화는 `ROW_COLUMNS` **한 자리**에서만 | **타입 보존** — payload는 `Json`으로 나가 정수 `0`과 문자열 `"0"`이 갈린다. `freeze_payload`가 못 보존할 모양(이미 문자열로 렌더된 payload · `NaN`/`Inf` · 비문자열 키)을 **고치지 않고 거절**한다. `recorded_at` 컬럼은 **일부러 없다**(uuid7 안에 있다). `molecule_ref`는 메모리에만 있고 **컬럼이 아니다** |
| `vocabulary.py` | 닫힌 어휘 + 항목별 **기계 검증 가능한 서명** + **걷기 의미론** | **현재 열둘**이며 이름 집합은 `test_v0_vocabulary_is_exactly_seven_words`가 통제한다. `processed_with`는 `step/recipe`만 required이고 수치 payload는 후보 계약이 아니다. `measured`(`since:4`)는 `metric/unit/method/state`를 요구하며 `recorded`만 `value/run_uid`, 나머지 상태는 `value` 자체를 금지한다. `measured_as`는 UI category다. 모든 술어의 `traversable/direction`, 모든 항목의 `label_ko`, `value.required` 존재 검증과 투영 상태어 쓰기 거절은 계속 유지된다. 정확한 표는 [spec §3.7](../spec/LEDGER_TECHNICAL_SPEC.md) |
| `uuid7.py` | 단조 UUIDv7 — 워터마크이자 기록시각 | **구성상 단조**. 밀리초당 4,096(12비트 카운터), 넘치면 **미래를 당겨 쓰고**, 벽시계가 뒤로 가면 **직전 밀리초를 유지**한다. `assert_monotonic`은 **센 개수를 돌려준다**(빈 순회가 성공을 보고하지 못하게) |
| `gate.py` | 문 앞에서 거절하고 **센다**. 단위는 행이 아니라 **분자** | 설계 §3의 **원자성 검사 넷** + **다섯째 질문**(`subject_types` — R-2026-08-13-D)이 산문에서 코드가 되는 자리. 🔴 **전부 아니면 전무이고, 그 규칙이 «어느 파편에든» 걸린다**(R-2026-08-13-H): `gate.building_molecule(source)` 스코프 안에서는 **사유를 가리지 않고 모든** `gate.refuse`가 세고 나서 `gate.MoleculeRefused`를 **raise**한다. 내년에 추가되는 헬퍼는 이 규칙이 있는 줄 몰라도 자기 분자를 세운다. 🔴 **`screen_molecule`의 거절도 그 문법이다**(2026-08-14 `92547c3` · R-H-bis 1) — 다만 **거절 팔만** 그렇고, **정당하게 할 말이 없던 분자(원자 0개)는 여전히 `[]`를 «반환»**한다. 거절과 무발화를 같은 문법으로 만들면 거절 카운터가 두 가지 뜻을 갖는다. 🔴 **스코프를 «여는» 것은 이 모듈도 번역기도 아니고 드라이버다**(아래 `backfill.py`). 거절 사유는 **닫힌 집합 열둘**이고 호출부가 새 사유를 지어내면 `ValueError` |
| `config.py` | `ledger_config.json`을 **로드 시점에** 검증 · 🔴 **문법이 «둘»**(2026-08-14 3차) | **선언 없는 것은 기본값이 아니라 거절이다** — 시각 컬럼·시간대가 없으면 소스 전체를 거절한다. `translator_version()`이 **선언 전체를 해시**해 원자마다 어떤 규칙이 만들었는지 남긴다. **런당 1회 읽는다**(행마다 아님). 🔴 **소스는 이제 `kind`를 선언한다**(`lineage` \| `observation` \| **`transfer`**(2026-08-14 4차), **기본 `lineage`** — 그래서 기존 선언 전부가 정확히 옛 뜻을 유지한다). 검증이 그 낱말로 **분기**하고 필수 컬럼 집합이 갈린다 — 관측 소스를 혈통 규칙으로 채점하면 `parent_lot`이 없다는 이유로 거절됐을 것이다(선언 키는 [ONTOLOGY_LEDGER_SETUP §3.2](./ONTOLOGY_LEDGER_SETUP.md)). 🔴 **`transfer`는 `group`(묶는 컬럼 + 행 정렬 타이브레이크)과 `container`(목적지 신원을 «확정하는» 관계)를 «추가로» 요구한다** — 확정 관계를 선언 못 하게 하면 번역기가 읽을 것은 행에 있는 추론 대상뿐이고, 그것을 읽으면 **틀린 조인이 조용히 성공한다**(선언 키는 [ONTOLOGY_LEDGER_SETUP §3.3](./ONTOLOGY_LEDGER_SETUP.md)) |
| **`transfer_translator.py`** (2026-08-14 4차) | 세 번째 번역기 — **잡런 하나 = 분자 하나**, 원자는 **(잡런 × 소스 웨이퍼)당 하나**에 `qty` · 🔴 **이 원장 최초의 «실데이터» 소스** | 🔴 **「잡런당 원자 하나」와 「subject = Wafer」는 실측 하나에서 만난다**: 한 DT 잡을 **여러 코어 웨이퍼가 먹인다**(396잡 중 83잡이 1장, 83잡이 2장, 8잡이 88장). subject이 웨이퍼 여럿인 원자는 **표현 불가**이므로 잡런은 **소스 웨이퍼마다 원자 하나**를 낸다 — 웨이퍼 한 장짜리 잡은 정확히 하나이므로 선언된 모양 그대로다. 🔴 **다이당 원자를 «안» 낸다**(§2-bis의 `die` XOR `qty`) — 34,939행이 4,669원자가 되고, 다이별 좌표는 `source_raw_ref`가 지목하는 소스 행이 계속 말한다. 🔴 **`source_raw_ref`가 «열거»가 아니라 «술어»다** — 그룹이 최대 150행이라 business key를 늘어놓으면 원자마다 6 KB이고 천만 행에서는 출처가 원장보다 커진다. `dt_log:{"core_wafer":…,"dt_job":…}`는 **그 집합을 정의하는 질의**이고 정렬돼 있어 재번역을 유니크 인덱스가 알아본다. ⚠️ **`synthetic` 마커가 «없다»** — 실데이터이고 원장에는 UPDATE가 없어 잘못 찍은 마커는 오타가 아니라 **영구 거짓**이다(소스 «테이블»에 `SYN-*` 잡이 섞여 있는 것은 테이블의 사실이지 번역의 사실이 아니다) |
| **`observation_translator.py`** (2026-08-14 3차) | 두 번째 번역기 — **소스 행 하나 = 분자 하나 = 발화 하나** | 🔴 **조립할 것이 없다.** 짝 맞출 이벤트도, 반으로 잘릴 그룹도 없다 — 그래서 `lot_event_translator`의 「한 이벤트 = 두 행」 기계장치가 여기 없는 것이 **누락이 아니라 문법의 차이**다. 🔴 **그래도 문은 하나다**: `gate.building_molecule` 스코프 안에서 `gate.screen_molecule`을 지나 `store.write_batch`로 간다(§3-bis의 규칙이 생성기뿐 아니라 여기에도 그대로). 🔴 **런을 못 찾은 발견은 «거절»**이지 도착 시각으로 도장 찍히지 않는다 — 세상의 시각이 발견 행에 없기 때문이다 |
| `lot_event_translator.py` | 첫 번째 소스, 그리고 다음 번역기가 베낄 **모양** | **한 이벤트 = 두 행 = 한 분자**. 짝은 `(event_type, event_time, parent, child)`로 맞춘다(소스에 이벤트 id가 없다). 🔴 **한 행이 양쪽을 다 채우면 고립시켜 거절**한다 — 「부모 먼저, 없으면 자식」류 순서는 그 행의 웨이퍼를 소스가 주장한 적 없는 계보에 조용히 붙인다. 🔴 **이 파일은 스코프를 «열지 않고 요구»한다**(2026-08-14 `92547c3` · R-H-bis 3). `translate`는 `gate.building_molecule` **안에서 불려야** 하고, 안 열고 부르면 `_build`의 단언이 **`RuntimeError`**를 내며 그 메시지가 **누가 여는지(`backfill.run`)와 두 줄짜리 철자**를 댄다. 여는 자리가 여기였을 때는 그 규율이 **두 번째 번역기 작성자가 이 파일을 읽고 «알아채야»** 물려받는 구전이었다. 🔴 **번역기 쪽 일방향 문은 여전히 `translate`의 `except MoleculeRefused` 하나**이고 `_build` 안에는 그것을 삼킬 표현식이 없다 — 다만 **게이트 심사의 거절을 받는 두 번째 문이 드라이버에 있다**([spec §3.3-bis 표](../spec/LEDGER_TECHNICAL_SPEC.md)) |
| `store.py` | 원자 쓰기 + 커서 전진, **한 트랜잭션** | 커밋 하나 안에 원자와 커서가 같이 들어간다(§2.4). 연결은 **반드시** `engine.raw_connection()` — `psycopg2.connect`는 `db_safety` 가드를 우회한다. `parse_occurred_at`이 **선언 시간대는 naive 텍스트에만** 먹이고 오프셋을 달고 온 문자열은 그대로 존중한다. 🔴 **`write_batch(…, reasons=…)`는 «필수 키워드» 인자다**(2026-08-14 `92547c3` · R-H-bis 2) — 기본값도 없고 명시적 `None`도 `TypeError`이며, 깨끗한 런의 정당한 값은 **명시적 `{}`** 하나다(§4.4의 부호 계약이 여기 걸려 있다) |
| `backfill.py` | 커서 루프 — **분자를 반으로 자르지 않는다** · 🔴 **분자 스코프를 «여는» 자리** · 🔴 **2026-08-14 3차부터 «디스패처»**(4차부터 **드라이버 셋**) | 🔴 **[2026-08-14 4차 — 실측된 데이터 유실 하나가 여기서 닫혔다]** 페이지 규칙이 **`walk_group_pages` 한 함수**로 모였고, 그 이유는 규칙이 **두 벌이었고 둘 다 같은 곳이 틀렸기** 때문이다: 꽉 찬 페이지의 꼬리 그룹을 버린 뒤 **커서를 «버린 그룹»으로 전진**시켰다. 인출은 `WHERE key > cursor`이므로 **아직 읽어야 해서 버린 바로 그 그룹을 영원히 건너뛴다.** ⚠️ **`lot_event`는 43행이라 `dropped`가 언제나 `None`이었고, 그래서 이 갈래는 «한 번도 실행된 적이 없었다»** — 34,939행짜리 `dt_log`가 같은 루프를 돌자 **396 잡런 중 379만 번역되고 17 그룹·1,862행이 조용히 사라졌다**. 커서는 이제 **온전히 처리된 마지막 그룹**으로 간다. 🔴 **`run()`은 이제 선언된 `kind`를 보고 `_run_lineage` / `_run_observation` / `_run_transfer` 중 하나로 보낸다** — CLI는 한 글자도 안 바뀌었고(`--source <이름>`) 선언이 경로를 정한다. **두 루프의 차이는 커서**다: 혈통은 세계 시각 그룹, 관측은 **키셋**(§4.3). 아래는 혈통 루프의 계약이다 — 커서는 행 오프셋이 아니라 **`event_time`**이고, 배치는 언제나 **온전한 `event_time` 그룹의 정수 개**다. 페이지가 꽉 찼으면 **꼬리 그룹을 버린다**(잘렸는지 안에서는 알 수 없다). 🔴 **분자 루프가 `with gate.building_molecule(source)`를 들고 `translator.translate`와 `gate.screen_molecule`을 «같은» 스코프 안에 감싼다**(2026-08-14 `92547c3` · R-H-bis 3) — 그래서 이 드라이버가 모는 **모든** 번역기는 작성자가 규칙을 몰라도 스코프 안에서 태어난다. ⚠️ **오늘 이 드라이버를 부르는 것은 자기 파일의 CLI `main()`뿐**이다(데몬·라우트·워커 0) |
| `observability.py` | 거절 요약 + **뒤처짐(lag)** 보고 — 첫날부터 | 티어 2단. **티어 1은 질의 0회**(세계시각 뒤처짐 · 커서 나이) — 이것만으로 「커서가 안 움직인다」가 보인다. **티어 2는 스로틀 걸린 1질의**(소스 head·뒤에 남은 행 수). 🔴 `probe_allowed`를 같이 실어 **「안 뒤처짐」과 「안 물어봄」을 구별**한다. 🔴 **[2026-08-14 3차] `lag_basis`가 붙었다**(`world_time` \| `arrival_watermark`) — 키셋 커서(`lag_report_keyset`)는 **세계시각 뒤처짐을 낼 수 없어서** `world_time_lag_seconds`를 `None`으로 두고 **어느 잣대로 쟀는지 이름을 댄다.** 도착 뒤처짐을 세계시각의 이름으로 보고하면 **운영자가 「소스가 조용하다」와 「번역기가 멈췄다」를 구별할 수 없다** |
| `schema.py` | 물리 DDL **한 철자**. 마이그레이션도 이것을 부른다 | **첫날부터 월 단위 RANGE 파티션**(`ALTER TABLE ... PARTITION BY`가 없으므로 나중은 전면 재작성). 🔴 **모든 인덱스는 이름 붙은 소비자를 갖는다** — 소비자 없이 지어졌다 제거된 셋의 **가격이 주석에 남아 있다** |

### 1.2 읽기 쪽 — 추적 화면(인스턴스)과 구조 화면(유형)

🔴 **읽는 쪽은 «두 수준»이고 서로를 복제하지 않는다.** `/trace`는 **인스턴스**(이 랏의 혈통)이고,
`/structure`는 **유형**(어떤 개체가 어떤 관계로 이어지는가)이다 — 구조 응답에는 랏·웨이퍼·보이드가 **한 건도 없다.**

| 파일 | 무엇 | 왜 이 경계인가 |
|---|---|---|
| `server/ledger_structure.py` (2026-08-14) | `GET /api/ledger/structure` — **유형 수준 온톨로지 그림 + 선언 지도**. 노드=개체 타입, 엣지=(subject 타입, 술어, 목적어) 삼중항 | 🔴 **손으로 적은 노드·엣지 목록이 이 파일에 «없다»**(제품 소유자 실패 조건: 「하드코딩된 목록이 응답 어디에든 보이면 실패」). **선언된 절반**은 `vocabulary.ENTITY_TYPES` × `PREDICATES`에서, **관측된 절반**은 원장 한 번의 `GROUP BY`에서 생성하고 **둘을 병합**한다 — 병합이 설계 전부다. 선언에만 있는 모양(`declared_only`)과 데이터에만 있는 모양(`undeclared`)은 **손으로 그린 그림이 영원히 못 내는 답 둘**이다. 🔴 **어휘는 «지연» import한다**(호출 «안»에서) — §0의 「`server/`에서 `server/ledger`를 import하는 부팅 경로가 없다」를 *거의* 참이 아니라 **글자 그대로** 참으로 두려고. 🔴 **등급 분포를 SQL이 «분류하지 않는다»** — 그룹 키만 만들고 `ledger_trace.claim_class`/`claim_basis`를 **그대로 부른다**(철자가 둘이면 갈라진다). 🔴 **등록 엣지는 이름이 아니라 «모양»(`object_kind IS NULL`)으로 식별**한다 — `predicate == "register"` 리터럴이 먼저 쓰였고 어휘를 갈아끼우는 테스트가 잡았다 |
| `server/ledger_trace.py` | **셋이 살고 둘은 서로를 몰라야 한다**: **해결기**(`claim_class`/`claim_rank_key`/`resolve` — 순수 파이썬, SQL·테이블명·커넥션 0) · **조회기**(`ClaimLookup` 계열 — 가져오기만 하고 등급을 모른다) · **보행**(`trace` — 조회기에 한 번 묻고 홉마다 해결기에 한 번 묻는다) | 스타일이 아니라 **구조 요구**다. 슬라이스 1은 **랏 단위**라 질의 시점 해결로 가지만 **슬롯 단위 혈통은 질의 시점에서 죽는다**(인라인 452 ms 대 물질화 0.58 ms — 합성·이 박스). 조회기가 **교체 가능한 객체**라 물질화된 클로저 테이블로 옮기는 것이 **생성자 인자 하나**이고 해결기는 한 줄도 안 바뀐다. `InMemoryClaimLookup`은 그 교체 가능성을 **주장이 아니라 검사된 성질**로 만든다. 🔴 **[2026-08-14 3차] 「무엇을 걷는가」가 이 파일에 더 이상 «적혀» 있지 않다** — `LINEAGE_PREDICATES`는 리터럴 목록이었고 지금은 `vocabulary.walk_predicates()`에서 **파생**되며, 재귀가 따르는 낱말도 `traversal_predicate()`가 대어 **두 CTE 모두 SQL 파라미터로 바인드**한다(`'derived_from'` 리터럴이 없어졌다). 어휘는 **호출 안에서 지연 import**하므로 §0의 부팅 경로 보증은 그대로다. 🔴 **동작 불변이 단언돼 있다**(`test_ledger_observed_unit.py::test_the_walk_vocabulary_is_derived_and_still_says_what_it_said`) — 파생으로 옮기면서 걷기가 **한 낱말도 더 얻거나 잃지 않았다**는 것이 이 이관의 유일한 합격 조건이었다 |
| `server/ledger_trace_router.py` | `APIRouter(prefix="/api/ledger")` **하나에 라우트 열** — `/trace` · `/coverage` · `/siblings` · `/kinds` · `/structure` · `/lots` · `/lot_map` · `/journey` · **`/trends`** · **`/composition`**. 전부 **읽기 전용**. 🔴 **라우트 계약의 정본은 [backend §2](../architecture/backend.md)이고 이 칸은 색인이다** | 🔴 **SPA catch-all «위»에 등록해야 한다.** FastAPI는 등록 순서로 매칭하므로 catch-all 뒤에 등록된 라우트는 **200으로 `index.html`을 받는다** — 감시자가 죽은 엔드포인트를 살아 있다고 부르게 되는 실패다(`/health`가 실제로 그랬다). 현재 `server/main.py`에서 catch-all 훨씬 위에 등록돼 있다. 🔴 **빈 `hops`는 가능한 답이 아니다** — 어느 홉에서 왜 끊겼는지가 이 화면의 존재 이유다 |
| `server/ledger_siblings.py` + `server/ledger_walk_contrast.py` (2026-08-14 밤 등재) | `/siblings`의 **엔진 둘** — 축 엔진(선언된 요인 기하 위 케이스-컨트롤, `mode=intersection\|contrast`)과 **걷기 대조**(`scope=` 마킹 시 — 「이 랏/웨이퍼들과 나머지는 뭐가 다른가」). 응답 `engine` 필드가 어느 쪽이 답했는지 말한다. 요인 기하는 전부 `server/config/siblings_axes.json`(.sample 폴백) 선언 | 🔴 **걷기 대조에는 항목 목록이 «한 줄도» 없다** — 후보는 마킹된 주어들의 걷기가 닿는 모든 술어×필드×값이고, 선언(`defaults.walk`)은 필터가 아니라 **예산**이다(CASE는 절대 안 깎고 control만 결정적 표본 · `walk.gate`가 그랬다고 말한다). 🔴 **수치는 주어당 «한 값»으로 접은 뒤 같은 랭킹 사다리를 탄다**(원자 141개 웨이퍼 = 관측 1 — 둘째 임계를 발명하지 않는다. 배율 밴드의 단위 의존성은 화면에 이름이 불린다). 🔴 **요청된 scope 값은 전수 회계된다** — `unnest` LEFT JOIN으로 해소/탈락이 이름 불리고, 전부 탈락이면 `empty`이지 남은 값에 대한 잘 지어진 답이 아니다. 🔴 **기전 관문은 `server/mechanism_gate.py` + `mechanism_models.json`** — 바인딩 안 된 후보는 좁혀지지 않고 `unknown`을 단다. 세부·수치는 [backend §2 `/siblings`](../architecture/backend.md)가 정본 |
| **`server/ledger_journey.py`** (2026-08-14 밤) | `/journey`의 **주어 «둘» 전용** 읽기 — 두 주어의 원자를 **공정 구간의 순서**로 재배치한다. 새 사실을 계산하지 않는다. 이름 층은 `server/config/ledger_journey.json`(.sample). 읽는 법 §4.6-quater · 계약 [spec §4.9](../spec/LEDGER_TECHNICAL_SPEC.md) | 🔴 **`/siblings`의 «모드»가 아니라 별도 라우트인 것이 설계 전부다** — 저쪽 계약에는 배수·신뢰구간이 들어 있고 **주어 둘은 그 무엇도 지탱하지 못하므로**, 여기서는 그 키들이 `null`이 아니라 **아예 없다**(관문도 셋이 아니라 둘). 🔴 **주어가 둘로 안 풀리면 강등이 아니라 «거절»**(422)이고 해결된 주어를 이름 댄다. 🔴 **술어 이름으로 분기하는 갈래가 0개** — 육하원칙 여섯 슬롯은 봉투→슬롯 매핑 하나라 **내일 번역된 술어도 같은 카드로** 렌더된다. 🔴 **세그먼트 서수는 «해결 등급 안에서»** 매기고 묶을 때 등급을 뺀다 — 그래야 장비 로그와 레시피 책이 한 물리적 런을 둘로 안 쪼갠다. 🔴 **`claim_rank_key`를 재구현하지 않고 «부른다»** — 한 구간의 두 원자가 한 잎을 다투면 혈통 해결기와 **같은 전순서**가 승자를 정하고 패자는 실려 나간다 |
| `client2/src/ledger_trace_core.js` | **순수**. DOM·네트워크·import 0. 서버 답을 낱말과 톤에 매핑만 한다 | 🔴 **이 모듈은 원장에 대해 아무것도 판정하지 않는다.** 어느 주장이 이기는지는 서버가 이미 정했다. **여기에 승패 규칙이 나타나면 그건 두 번째 해결기이고 틀린 것이다** |
| `client2/src/ledger_trace_view.js` | 답을 DOM으로. `document`가 **전역이 아니라 인자** | 그래서 `client2/tests/ledger_trace_harness.mjs`가 **진짜 렌더러를** bare node로 몰아 「화면에 실제로 도달한 것」을 단언한다 — 함수가 존재한다는 단언이 아니라. `innerHTML` 0(원장에서 나온 랏 id가 마크업이 될 수 없다) |
| `client2/src/ledger_trace.js` | 페이지 진입점(`ledger.html`). 질문 읽기 → fetch → 뷰에 넘기기 | 🔴 **읽기 전용 화면.** GET 하나를 쏘고 아무 데도 안 쓴다. `window`를 만지는 유일한 파일이라 나머지 둘이 bare node에서 채점된다 |

---

## 2. 쓰기 경로 — 소스 행 하나가 원자가 되기까지

```
소스 행들                (backfill.fetch_page — event_time 순, 그룹 경계에서만 자른다)
   ↓ group_molecules     한 소스 이벤트 = 한 분자 (lot_event은 두 행)
분자
   │  ┌─ with gate.building_molecule(source):   ← 🔴 드라이버가 «여기서» 연다 (backfill.run)
   │  │     ↓ translator.translate   원자를 «만든다». 아직 아무것도 안 검사됐다
   │  │  Atom[]
   │  │     ↓ gate.screen_molecule   원자성 검사 넷 + 다섯째 질문. 전부 아니면 전무
   │  └─ except gate.MoleculeRefused: refused = True   ← 거절은 «풀려서» 여기로 온다
kept[]  (거절이면 아무것도 안 실린다 · 「할 말 없음」이면 [])
   ↓ store.write_batch(…, reasons={사유: 분자수})   원자 INSERT + 커서 UPDATE = 커밋 하나
ledger_events + ledger_translator_cursor
```

🔴 **스코프를 여는 것은 번역기가 아니라 이 루프다**(2026-08-14 `92547c3` · R-H-bis 3).
번역기를 **손으로 모는 호출부**(테스트·일회성 스크립트)는 **자기가 열어야 한다** — §3 ③.

⚠️ **관측 소스는 이 그림에서 «`group_molecules` 한 칸»만 다르다**(2026-08-14 3차) — 한 행이 곧 한 분자라 묶을 것이 없다.
🔴 **나머지 칸은 전부 같고, 그것이 요점이다**: 문법이 셋이어도 **게이트도 저장 경로도 하나**다([ONTOLOGY_LEDGER_SETUP §3](./ONTOLOGY_LEDGER_SETUP.md) · §3-bis).

### 2.1 실제 예 하나 — `assy_manager`, 2026-08-13 실측

소스 `lot_event`의 두 행(같은 `event_time`, 한 쪽만 `child_lot`, 다른 쪽만 `parent_lot`):

```
business_key_val                        lot              event_type parent_lot     child_lot        slot_numbers  wafer_ids
CL-2601-006|split|2026-05-03 02:17:00   CL-2601-006      split      (없음)         CL-2601-006-A1   01:02:03:…:25 WF.010601:…  (19개)
CL-2601-006-A1|split|2026-05-03 02:17:00 CL-2601-006-A1  split      CL-2601-006    (없음)           04:05:11:20:21:22  WF.010604:… (6개)
```

두 행이 한 분자다. 이 분자가 낸 원자 **59개**(실측):

| 술어 | 개수 | 파생(`#`) | 어디서 나왔나 |
|---|---|---|---|
| `register` | 27 | `first_sight` | 랏 2 + 웨이퍼 25. **첫 등장에만.** `Die`는 구성형이라 등록하지 않는다 |
| `has_wafer` | 25 | `positional_row` | 각 행의 `(slot[i], wafer[i])`. 🔴 **길이가 다르면 분자 전체 거절** — 어긋난 위치 짝짓기는 조용히 웨이퍼를 엉뚱한 슬롯에 붙이고 **여전히 well-formed하게 보인다** |
| `derived_from` | 1 | `pair_field` | 행이 자기 `parent_lot`/`child_lot` 컬럼에 **적어 놓은 것** |
| `slot_map` | 6 | **`slot_preserving`** | 🔴 **소스에 없다.** 이 split의 두 행은 **둘 다 이동 «후»** 스냅숏이라 **겹치는 웨이퍼가 0개**다. 슬롯 체인은 「split은 슬롯 번호를 보존한다」는 **선언된 관례** 아래에서만 성립한다 |

`slot_map` 원자 하나의 실제 모양:

```json
{"type": "Lot", "keys": {"lot": "CL-2601-006-A1"},
 "qualifiers": {"from": "04", "to": "04", "wafer": "WF.010604"}}
source_translator_ver = "lot_event/1/rules:d8d1c9e0#slot_preserving"
source_raw_ref        = "lot_event:[\"CL-2601-006-A1|split|…\",\"CL-2601-006|split|…\"]"
```

🔴 **`#slot_preserving` 접미가 이 전체 설계의 핵심 장치다.**
`WHERE source_translator_ver LIKE '%#slot_preserving'`로 **관례에 기댄 원자와 소스가 실제로 발화한 원자가 갈린다.**
`assy_manager` 909개 중 **127개**가 여기 걸린다(실측). 해결기는 그것들을 **3류(추론)**로 매기고, 나중에 진짜 관측이
다른 슬롯 대응을 주장하면 **사람이 아무것도 풀지 않아도 관측이 자동으로 이긴다** — [R-2026-08-13-A / 기결 판정](../process/LEDGER_RULINGS.md).

> `merge`는 관례가 필요 없다. 소스 행이 이동 **전** 스냅숏이고 목적 행이 **후**라 옮겨진 웨이퍼가 양쪽에 다 나타난다
> → `shared_wafer`로 `from`/`to` 둘 다 **소스에서 그대로 읽는다**(실측 26개).

### 2.2 거절은 어디서 세어지는가

전부 `gate.py`이고, **`(소스, 사유)`별로 프로세스 수명 내내 누적**된다.

| 사유 상수 | 언제 |
|---|---|
| `undeclared_source` | `ledger_config.json`에 그 소스 선언이 없다 |
| `undeclared_vocabulary` | 소스의 `event_type`이 `vocabulary` 맵에 없다 · 또는 어휘에 없는 술어를 emit했다 |
| `no_occurred_at_declaration` / `missing_occurred_at` | 시각 컬럼 미선언 / 선언된 형식으로 안 읽힌다. 🔴 **도착 시각으로 대체하지 않는다** |
| `no_identity` | 분자의 어느 행에도 랏 값이 없다 · subject 신원이 비었거나 구조화되지 않았다 |
| `not_true_alone` | 서명 위반(subject 타입·object kind·필수 qualifier) |
| `atomicity_violation` | 슬롯/웨이퍼 길이 불일치 · 남의 분자 원자가 이 트랜잭션 단위에 섞였다 |
| `undeclared_derivation` | 원자가 config가 선언하지 않은 규칙 이름을 달고 있다 |
| `no_raw_ref` | 원문으로 돌아갈 길이 없다 |
| `payload_not_preservable` | `NaN`/비문자열 키/왕복 못 하는 타입 |
| `ambiguous_pair` | 🔴 한 행이 `parent_lot`과 `child_lot`을 **둘 다** 채웠다 — 두 계보를 동시에 단언하고 있고 어느 쪽인지 행이 말하지 않는다 |
| **`undeclared_subject_type`** | 🔴 원자의 개체 타입이 소스 선언의 **`subject_types` 밖**이다(2026-08-13 `eb1ae8b`). 원자 자체는 **참일 수 있다** — 항의하는 것은 「이 번역기가 아무도 검토 안 한 타입을 발화하기 시작했다」이고, 그 드리프트는 **자기 이름이 있어야 세어진다.** ⚠️ 실데이터에서는 **0건**이다(탐지기이지 오늘의 문제가 아니다) |

🔴 **거절은 «어느 파편에서든» 분자 전체를 세운다** (2026-08-13 `f313279` · R-2026-08-13-H).
게이트의 심사(`screen_molecule`)만 전부-아니면-전무이던 것이 결함이었다 — 번역기가 **원자를 만드는 도중** 거절하는
자리는 그 보장 «밖»이었고, `_slot_map`이 `None`으로 신호하던 것을 한 호출부가 `... or []`로 삼켰다.
**실측: 게이트는 `atomicity_violation`을 셌고 로그는 「1행이 아무것도 못 냈다」고 말했는데 원자 셋이 착지했다.**
지금은 `gate.refuse`가 스코프 안에서 **예외**(`MoleculeRefused`)를 던진다 —
🔴 **`[]`를 돌려주는 수리는 «그 측정만» 초록으로 만들고 모양을 그대로 남긴다.**
**어떤 병합 표현식도 예외를 삼킬 수 없다.** 파편 단위 생존은 **`incomplete`의 몫**이지 `refuse`의 뜻이 아니다.

🔴 **게이트의 심사도 같은 문법이 됐고, 스코프는 드라이버가 연다** (2026-08-14 `92547c3` · R-2026-08-13-H-bis).
`screen_molecule`의 **거절 팔**은 이제 `gate.refuse`를 지나 `MoleculeRefused`로 풀리고, `backfill.run`이 **심사를 스코프 «안»에서**
부르기 때문에 그 풀림이 실제로 발화한다. ⚠️ **「이제 언제나 raise한다」로 읽지 말 것** —
**정당하게 할 말이 없던 분자**(원자 0개: 빈 wafer 컬럼의 `track_in`)는 **여전히 `[]`를 반환**하고 **거절로 세어지지 않는다.**
그 둘을 같은 문법으로 만들면 위의 거절 카운터가 두 가지 뜻을 갖는다.
🔴 **이것이 단위 테스트만으로는 못 정착되는 자리다**: 옛 반환형을 주입하면 단위는 빨개지지만,
같은 주입을 실 PostgreSQL에 걸었을 때 나오는 것은 **게이트 2 대 드라이버 0**(`refused_molecules`)이고 —
**세지 않고 잃는** 그 경로가 §4.4의 `refusals_unaccounted`를 **음수**로 민다.

🔴 **거절된 분자는 자기 «부작용»도 되돌린다.** `register` 원자는 실행 스코프 메모에 거절 검사보다 **먼저** 들어가므로,
아무것도 안 쓰이면 그 랏은 **아무것도 안 쓴 분자에 의해 등록됨으로 표시되고 이후 누구도 등록하지 않는다.**
`_forget_this_molecules_registers`가 **분자별 목록**으로 되돌린다(수명 메모의 스냅숏은 천만 행 백필을 2차식으로 만든다).

**세 숫자를 구별해야 한다** — 이 자리가 이 모듈 자신의 첫 결함이었다:

- `molecules` — 거절된 **분자** 수
- `source_rows` — 그래서 아무것도 못 낸 **소스 행** 수
- `built_atoms_discarded` — 만들어졌다가 분자와 함께 버려진 **원자** 수.
  🔴 **이것이 「얼마나 잃었나」가 아니다.** 원자가 되기 «전»에 거절된 분자(미선언 event_type, 안 읽히는 시각, 모호한 짝)는
  여기에 **0을 기여하고도 그 행이 냈을 전부를 잃는다.** 첫 실전에서 실제로 「1행 거절, 26원자 미기입, `atoms_lost=0`」이 나왔다.

**거절이 아닌 것 하나** — `incomplete`. 소스 이벤트의 행이 다 안 온 분자다. 온 행들은 **참인 주장을 하고 있어서**
버리면 증거가 사라진다. 번역은 하되 **구멍의 이유가 세어진다.** (`assy_manager` 실측 2건 — 누가 그리드에서
`child_lot`을 손으로 고쳐 한 merge의 두 행이 더 이상 같은 짝을 가리키지 않는다.)

**로그 시끄러움**은 1·10·100·1,000… 번째에만 `WARNING`으로 올라간다 — 고쳐진 배포와 망가진 배포가
같은 로그를 내지 않게. `/health`가 다른 프로세스에서 읽는 **박동 노트**는 **깨끗하면 `None`**이다
(줄이 «나타나는» 것 자체가 신호).

### 2.3 한 트랜잭션이 덮는 것

🔴 **원자 INSERT + 커서 UPDATE = 커밋 하나.** (`store.write_batch`)

- 커밋 **전**에 커서를 쓰면 크래시 때 일감을 **건너뛴다**.
- 커밋 **후**에 쓰면 **다시 한다**.
- 한 트랜잭션에 넣어야 「쓰인 원자 == 커서 위치」가 **원자적 사실**이 된다.
  (파일 인제션의 `record_chunk_progress`가 이미 같은 논증을 했다 — 그것을 그대로 물려받았다.)

**분자는 절대 트랜잭션을 걸쳐 쪼개지지 않는다.** 한 트랜잭션이 담는 것은 **온전한 소스 이벤트 N개**이고
(`batch.molecules_per_transaction`, 기본 200) **하나의 일부는 아니다.** 자르는 것은 `backfill.py`가 하고,
자르는 자리는 **소스 자신이 주는 경계**(`event_time` 그룹)다.

**파티션 생성은 «자기» 트랜잭션에서 돈다.** 원자 트랜잭션 안에서 돌다 실패하면 분자까지 롤백되고
운영자는 **DDL 문제를 원자성 거절로 본다.** 둘을 갈라 놔서 두 실패가 구별된다.

---

## 3. 🔴 새 소스 붙이는 법 — **코드 쪽**

> 이 절이 이 문서가 존재하는 이유다. `lot_event_translator.py`가 **베낄 모양**이다.
> 🔴 **선언(JSON) 쪽은 [ONTOLOGY_LEDGER_SETUP §3](./ONTOLOGY_LEDGER_SETUP.md)이고 «거기부터» 한다** — 선언 없이 쓴 번역기는 돌려 볼 수 없다.

🔴 **먼저 «어느 문법인지»부터 정한다** (R-2026-08-14-D). 소스 선언의 `kind` 한 낱말이 절차를 가른다 —
**문법 셋(`lineage`·`observation`·`transfer`)과 각각의 선언 키 표는
[ONTOLOGY_LEDGER_SETUP §3](./ONTOLOGY_LEDGER_SETUP.md)이 소유한다.** 아래 ①·③·④·⑤·⑥은 **문법을 가리지 않고** 적용된다.

🔴 **세 번째 문법이 «필요했던» 이유는 컬럼이 아니라 «단위»다** (`dt_log`). 혈통은 이벤트 키가 정확히 두 행을 짝짓고,
관측은 아예 안 묶는다. `dt_log`는 **한 잡이 최대 150행**이고 그 전부가 한 사건이므로 **묶어야** 한다 —
`group.column` 한 낱말이 그것을 선언하고, 배치 경계는 언제나 **온전한 그룹의 정수 개**다(혈통의 그룹 절단을
`event_time` 대신 **선언된 컬럼**으로 하는 것이고, `backfill.walk_group_pages` **한 함수**를 둘이 공유한다).

⚠️ **실측이 `container` 선언의 값을 증명했다 (2026-08-14, `assy_manager`)**: `dt_inventory` 401행 중 `dt_lot`이 비지 않은 것은 **하나**,
그 값이 문자열 **`'DT_LOT'`**(스프레드시트 **헤더가 데이터로 샌 것**)이다. `dt_job` → `dt_inventory` **행 존재**는 396/396으로
**100%**인데 **확정은 0건**이다 — 🔴 **존재는 확정이 아니다.** 그래서 4,669 원자 중 4,640이 `#job_run_to_job`으로 앉았고,
원장은 없는 연결을 지어내는 대신 **「이 목적지는 확정된 적 없다」**를 말한다.

### ① 어휘 검사 — 먼저, 그리고 코드보다 먼저

새 술어나 새 개체 타입이 필요한가? **대개는 아니다.** 필요하다면 [설계 §4.3의 **3문 검사**](../architecture/CANONICAL_LEDGER_DESIGN.md)를 통과한 **판정**으로만 등재한다:

1. **기존 어휘로 정말 못 쓰나** (재사용 검사)
2. **SEMI 대응이 있나** — 있으면 차용하고 `semi_ref`에 적는다, 없으면 `"local"`이라고 **명시**한다
3. **클래스별 검사** — 개체 후보면 재식별 검사 / 좌표류면 subject 금지 검사 / 값이면 **단위 선언**

🔴 **어휘 자체가 append-only다.** 원자가 술어를 영원히 참조하므로 **삭제·재정의는 불가**하고 `deprecate`(신규 기입 금지)만 된다.
그리고 **그 수는 통제 장치**다 — `test_ledger_l1_unit.py`가 `PREDICATES` 집합을 못박고 있으므로
낱말을 더하면 **테스트가 빨개진다. 그 빨강이 「판정을 적으라」는 자리다.**
등재는 [LEDGER_RULINGS](../process/LEDGER_RULINGS.md)에 남는다 — **거기 없으면 내려진 적이 없는 판정이다.**

✅ **실제로 한 번 일어났다 (2026-08-14, 일곱 → 아홉).** 그 빨강을 어떻게 갚았는지가 다음 사람의 본보기다:

- **테스트 «이름»을 안 바꿨다**(`test_v0_vocabulary_is_exactly_seven_words`). 🔴 **일곱을 지키던 테스트가 왜 아홉인지를 적는 자리**여야 한다 —
  조용히 완화된 옛 테스트 옆에 새 테스트가 서면, 다음 사람은 **판정이 있었다는 사실 자체**를 못 본다. 판정 본문은 그 docstring에 있다.
- **`since`를 다시 매기지 않았다.** 원래 일곱은 `since: 1`, 새 둘은 `since: 2`이고 **그것도 단언된다** — 낱말이 들어온 슬라이스는
  「이 시스템이 언제 이 말을 배웠나」에 대한 증거다. 산수를 깔끔하게 만들려고 개번호하지 마라.
- **재사용 검사를 통과했다**: `processed_with`는 **설계 §4.2가 처음부터 예약**해 둔 낱말이고(첫 사용이다), `has_param`은
  「레시피 개정을 지목하는데 그 설정값을 아무도 못 읽는 공정 원자는 아무것도 설명하지 않는다」가 근거다.
- **개체 타입을 더하는 것은 config 결정이 아니라 어휘 결정이다** — `Recipe`가 `ENTITY_TYPES`에 들어가면서 `register`·`pin`·`same_as`의
  subject 목록 **셋 다** 손봐야 했다. 🔴 **`rev`는 키 재료이지 속성이 아니다**(개정은 편집이 아니라 새 등록 — [spec §3.7-ter](../spec/LEDGER_TECHNICAL_SPEC.md)).

✅ **두 번째로 일어났다 (2026-08-14 3차, 아홉 → 열하나 — `observed` 하나만 등재).** 이번 빨강이 가르치는 것 셋:

- 🔴 **필요가 실증된 낱말만 들어간다.** [MI 통일안 §6-bis](../architecture/MI_LEDGER_SCHEMA_PROPOSAL.md)는 `measured`와 `observed`를 **짝으로** 그렸지만
  등재된 것은 하나다 — **오늘 `measured`를 발화하는 것이 없다.** 짝이 예뻐서 낱말을 미리 만들면 그것이 미끼 선언이다.
  (그래서 「열하나」는 「열둘의 절반이 왔다」가 아니다. `since: 3`이 그 사실을 나른다.)
- 🔴 **`value` 목적어의 `required`가 설계 규율의 «집행 지점»이다.** `observed`의 `required`에 `run_uid`가 든 것은 문서화가 아니라
  **강제**다 — 분모 없는 관측은 게이트가 거절한다. 산문으로만 적혀 있었으면 다음 소스가 조용히 그것 없이 쓸 수 있었다.
- 🔴 **서명 필드를 더하는 것도 어휘 변경이다**(⑦ 트리거). 이번엔 `traversable`·`direction`이 **모든** 술어에 붙었다 —
  낱말은 하나 늘었는데 **선언의 «모양»은 열한 항목 전부가 바뀌었고**, DDL은 여전히 0줄이다.

### ② 선언 한 장 → 🔴 **[ONTOLOGY_LEDGER_SETUP §3](./ONTOLOGY_LEDGER_SETUP.md)이 소유한다**

**`server/config/ledger_config.json`의 키 표 셋(문법별 `lineage` · `observation` · `transfer`)은 2026-08-15에 그쪽으로 옮겼다.**
여기 사본을 두지 않는 이유는 이 문서가 이미 한 번 겪은 것이다 — **선언 절차가 두 벌이면 한 벌이 낡고,
낡은 쪽을 따른 사람이 손해를 본다.** 저쪽이 답하는 것: 필수/선택 키, 각 키가 없을 때의 거절 이름,
`kind`가 검증을 어떻게 가르는지, 그리고 **관측·이동 문법에서 `vocabulary` 키가 왜 로드 에러인지**.

번역기를 «쓰는» 쪽에서 알아야 할 것 둘만 여기 남긴다:

- 🔴 **선언을 바꾸면 `translator_version` 해시가 움직인다.** `source_translator_ver`가 dedupe 열쇠 일곱 중 하나이므로,
  **`--reset-cursor` 재실행은 dedupe가 아니라 «옛 원자 옆에 새 원자»를 쓴다**(실제로 `eb1ae8b`에서 `d8d1c9e0` → `34311f15`,
  878행 → 878 «신규»행). 「다시 돌려서 안 변한 걸 확인하자」가 기대하게 만드는 것과 **다르다** — 상세는 §4.3.
- **상설 규칙**: 🔴 **선언 필드는 «집행 지점»을 갖거나, 존재하지 않는다**(R-2026-08-13-D).
  단수 `subject_type`이 검사만 되고 **어느 원자에도 도달하지 않던** 것이 그 판정의 발단이고,
  지금은 복수 `subject_types`가 게이트에서 실제로 문다.

### ③ 번역기 작성 — `lot_event_translator`의 모양을 그대로

```python
class <Source>Translator:
    def __init__(self, source_cfg, translator_ver, declared_derivations, who=SOURCE): ...
    # 🔴 `gate.building_molecule` 안에서 «불린다». 이 안에서 스코프를 열지 «않는다» — 첫 항목 참조
    def translate(self, molecule) -> tuple[list[Atom] | None, dict]: ...
```

지켜야 하는 것:

- 🔴 **분자 스코프를 «열지 마라». 그것은 드라이버의 일이다** (2026-08-14 `92547c3` · R-H-bis 3).
  `lot_event_translator`는 한때 `translate` 안에서 `with gate.building_molecule(SOURCE):`를 들고 있었고,
  **베낄 모양으로서 그것이 틀렸다** — 그러면 규율이 「이 파일을 읽고 그 `with`를 «알아챈» 두 번째 작성자」에게만 전해진다.
  지금은 `backfill.run`의 분자 루프가 들고 있으므로 **이 드라이버가 모는 번역기는 전부 스코프 안에서 태어난다.**
  ⚠️ **번역기를 손으로 모는 호출부(테스트·일회성 스크립트)는 자기가 열어야 한다** — 안 열면 `_build`의 단언이 `RuntimeError`를 낸다:
  ```python
  with gate.building_molecule(source):
      atoms, report = tr.translate(molecule)
  ```
  🔴 **이 문장 하나가 오늘 이 항목의 «전부»다.** 번역기 클래스는 아직 하나이고 `backfill.run`을 부르는 것은
  자기 파일의 CLI `main()`뿐이라 **오늘 동작은 하나도 안 바뀌었다.** 이 구조의 값어치는 전부
  **당신이 두 번째 번역기 작성자일 때 맞을 그 `RuntimeError`**이고 — 그것이 이 절이 존재하는 이유다.
- **`(atoms, report)`를 돌려준다.** 원자가 되기 전에 거절했으면 **`(None, report)`** — 그때는 이미 `gate.refuse()`가 세었고
  호출자는 아무것도 안 쓰기만 하면 된다.
- **게이트 심사(`gate.screen_molecule`)는 호출자가 «같은 스코프 안에서» 부른다.** 그 거절은 값이 아니라
  `MoleculeRefused`로 풀려 나오므로 **번역기가 검사할 반환값이 아니다.** (「할 말 없음」의 `[]`만 값으로 온다.)
- **모든 원자는 `envelope.entity_ref`로 object payload를 만든다.** 손으로 dict를 조립하지 말 것(⑤ 참조).
- **`source_raw_ref`는 재번역의 유일한 경로다.** `lot_event`는 `raw_ref()`에서 **JSON 배열**로 쓴다 —
  행 신원(`business_key_val`)이 이미 `|`를 품고 있어서 구분자로 또 이으면 **다시 쪼갤 수 없는 문자열**이 된다.
  🔴 **정렬해서** 만든다 — 매 실행 같은 값이어야 유니크 인덱스가 재번역을 알아본다.
- **분자 안의 중복은 번역기가 억눌러도 된다**(`Atom.identity()` — DB에 거절시키는 것보다 싸다). 다만
  `identity()`는 `schema.DEDUPE_COLUMNS`의 **파이썬 쪽 거울**이지 열쇠 자체가 아니다.
- **등록 메모는 런 스코프**다. 호출자가 페이지마다 `store.existing_registrations()`로 **한 질의에 통째로** 씨를 뿌린다 —
  개체마다 조회하면 천만 행 백필이 **2차식**이 된다.
- 🔴 **거절된 분자는 자기 register를 메모에 남기면 안 된다**(`_forget_registers`). 아무것도 안 쓰였으니
  같은 랏을 말하는 다음 분자가 등록할 수 있어야 한다.

### ④ 🔴 `#<derivation>` 접미 — 그리고 **예상된 빨강**

**config가 선언한 가정에 원자의 «내용»이 의존하면**(소스 행에 없는 것) 그 원자는
`source_translator_ver` 끝에 `#<derivation>`을 달고 **3류(추론)로 해소된다.** 상설 규칙이다 —
[R-2026-08-13-A / §12-8](../process/LEDGER_RULINGS.md).

파생 이름 집합은 **선언에서 조립된다**(`config.declared_derivations`) — 옆에 나열하는 것이 아니라:

| 파생 | 언제 legal이 되나 |
|---|---|
| `positional_row` | 항상 |
| `first_sight` | 어느 이벤트든 `emit_register`가 참일 때 |
| `pair_field` | 어느 이벤트든 `lineage: "parent_child"`일 때 |
| `shared_wafer` / `slot_preserving` | 그 이름의 `slot_pairing`이 선언됐을 때 |

**그러므로 config에 규칙을 켜는 것이 그 파생을 합법으로 만드는 유일한 행위다.** 게이트는
선언 밖 파생을 단 원자를 **다른 게 다 완벽해도 거절**한다.

🔴 **새 파생을 추가하면 다음이 «반드시» 빨개진다. 그것은 고장이 아니라 기능이다:**

```
server/tests/test_ledger_trace_contract.py::test_every_declared_derivation_is_explicitly_classified
```

이 테스트는 번역기 config가 낼 수 있는 파생을 **전수 열거해** 해결기가 아직 분류하지 않은 것에서 실패한다.
빨강을 만나면 **둘 중 하나를 판정해서 적어라**:

- 원자의 내용이 **소스 행에 없는 config 선언 가정**에 의존한다 → `ledger_trace.DEFAULT_RESOLVER_CONFIG["inference_derivations"]`에 추가(**3류**)
- 소스가 발화한 것을 모양만 바꿨다 → 그 테스트 파일의 `UTTERED_DERIVATIONS`에 추가(**2류**)

**아무것도 안 하면 관측으로 기본 해소되고, 그것이 이 규칙이 막으려는 바로 그 역전이다**
(config 가정이 실측을 이긴다). 빨강이 그 자리를 막고 있다.

### ⑤ 🔴 픽스처는 **실물을 불러** 만든다 — `01452d5`를 경고 라벨로

> **이 레인의 모든 테스트가 초록인 동안 통합이 끝에서 끝까지 깨져 있었다.**
> 픽스처가 평평했고(`{"lot": ...}`) 실제 payload는 `entity_ref`(`{type, keys, qualifiers}`)여서,
> 모든 리더가 `None`을 돌려주고 **첫 실제 질의에서 모든 홉이 `[unusable_payload]`로 왔을** 상태였다.
> **자기 레인이 쓴 픽스처는 자기 레인에 동의한다. 초록이 아무리 많아도 그 사실을 뒤집지 못한다.**

그래서 규칙은 하나다:

- **object payload는 `envelope.entity_ref()`를 «불러서» 만든다.** dict 리터럴 금지.
- **가능하면 진짜 번역기를 몰아서** 픽스처를 만든다(`test_ledger_trace_contract.py`가 지금 그렇게 한다).
- **DDL을 손으로 베끼지 않는다.** 테스트도 `ledger.schema.ensure_schema`를 부른다 —
  손으로 베낀 사본이 **연 단위 파티션 + nullable provenance**로 어긋나 있었고,
  **아무도 안 가진 테이블을 시험하고 있었다.**

### ⑥ 검증 기대치

| 무엇 | 어떻게 |
|---|---|
| **멱등성 — 그물 «둘»을 각각** | ① **커서**: 2회차가 0행을 읽으니 0원자를 쓴다. ② **`uq_ledger_atom`**: 커서를 리셋하고 다시 돌리면 행은 읽히고 원자는 만들어지는데 **DB가 하나도 안 받는다.** 🔴 **①만으로 통과하면서 ②가 깨져 있을 수 있다(그 반대도).** 이 프로젝트는 이미 **문 둘 중 하나만 닫고 성공을 보고한 수리**의 값을 치렀다 |
| **`occurred_at`은 소스 시각** | 도착 시각이 대체될 수 있는 갈래가 **하나도 없어야** 한다. 안 읽히는 시각은 **거절**이 정답. 결함 주입으로 확인할 것 — 🔴 **주입은 `ledger.store`와 번역기 모듈 «양쪽»에 걸어야 한다**(번역기가 `parse_occurred_at`을 자기 이름으로 import해서 들고 있다. 한쪽만 패치하면 **성공해 보이는 주입 아래서 진짜 코드가 돈다**) |
| **오프셋 왕복** | 단언은 **instant «와» offset을 둘 다** 검사한다. `astimezone` 철자의 결함은 instant를 보존하므로 **instant만 보는 테스트에는 아예 안 보인다** |
| **반쪽 착지 불가** | 페이지 중간 청크가 이미 INSERT된 뒤 raise하면 **원자 0개가 살아남아야** 한다. 경계를 걷어냈을 때 원자가 남는 것이 **그 테스트가 빨개질 수 있음의 증명**이다 |
| 🔴 **번역기를 손으로 몰 때 스코프를 «연다»** | (2026-08-14 `92547c3`) 테스트가 `translate`를 직접 부르면 `with gate.building_molecule(source):`로 감싼다 — 안 감싸면 `RuntimeError`이고 **그 빨강은 고장이 아니라 ③의 가드가 도는 증거**다. 🔴 **양팔을 다 태워라**: 스코프 «밖»에서는 `RuntimeError`, 스코프 «안»에서는 **원자가 나와야** 한다(거절 팔만 보면 「전부 거절하는 가드」와 구별이 안 된다) |
| ⚠️ **「예외가 던져진다」는 주입 하네스 «안에서» 못 주장한다** | 이 저장소의 공유 주입 하네스 둘이 `AssertionError`를 **성공으로 친다** — **틀린 예외가 던져져도 초록**이다. 그러니 `pytest.raises(<정확한 타입>)`으로 쓰고, 예외에 대한 단언은 **전부 블록 «밖»에서 `caught.value`에** 대고 한다(블록 안, 호출 뒤에 쓴 단언은 **한 번도 실행되지 않는다**). 증명은 **옛 모양을 실제로 주입해 빨강을 실측**하는 것 |
| **어휘 집합** | `PREDICATES`가 정확히 **열하나**(2026-08-14 3차 — 일곱 → 아홉 → 열하나) · **원래 일곱이 여전히 `since: 1`** · `REFUSAL_REASONS`가 닫혀 있음 |
| 🔴 **걷기 선언은 «양방향»으로 검사한다** | (2026-08-14 3차) 술어마다 `traversable`이 **있어야** 하고(없으면 로드 시점 거절), `True`인데 `direction`이 없으면 거절, **`traversable`이 아닌데 `direction`이 있어도** 거절이다 — 아무도 안 걷는 엣지의 방향 선언은 미끼다. 🔴 **그리고 파생이 «같은 답»을 내는지 따로 단언한다**: 목록을 선언에서 뽑도록 바꾼 뒤 걷기가 낱말을 하나라도 더 얻거나 잃으면 그것은 이관이 아니라 **동작 변경**이다 |
| 🔴 **관측 소스는 「거절 0」이 아니라 «양팔»로** | (2026-08-14 3차) 온전한 행은 원자가 되고, **런을 못 푸는 행은 원자 0개 + 이름 붙은 거절**이어야 한다. 🔴 **`class`도 양팔**이다 — 선언된 값은 payload에 실리고, 밖의 값은 **종류 이름과 선언 집합을 대며** 거절된다(초록 한쪽만 보면 「class를 아예 안 읽는 번역기」와 구별이 안 된다) |
| 🔴 **`value` 목적어의 `required`는 «양팔»로** | (2026-08-14) 온전한 payload는 **위반 0**, 필드 하나 뺀 payload는 **그 필드 이름을 대며 거절**. 🔴 **`0`과 `False`를 «따로»** 태워라 — 진리값 검사로 잘못 쓰면 그 둘만 거절되고 나머지는 전부 통과해서, 온전한 payload 하나로는 **두 철자가 구별되지 않는다** |

**실행:**
```bash
conda run -n assy_manager python -m pytest server/tests/test_ledger_l1_unit.py server/tests/test_ledger_l1_pg.py server/tests/test_ledger_observed_unit.py server/tests/test_ledger_trace.py server/tests/test_ledger_trace_contract.py server/tests/test_ledger_trace_pg.py
```
🔴 **PostgreSQL 절반은 기본 실행에서 «건너뛰어진다»** — 초록 개수가 통과처럼 보이지만
실제 DB에 대고 안 돌면 스키마·인덱스·CHECK는 하나도 채점되지 않는다. skip 수를 반드시 읽을 것.
파이썬은 **전부 conda `assy_manager`**로(시스템 python은 `psycopg2` 부재로 **거짓 실패**한다).

---

## 3-bis. 🔴 소스가 «테이블»이 아닐 때 — 생성기 소스 (2026-08-14)

§3은 **RDB 테이블을 읽는 번역기**의 절차다. 원장에 쓰고 싶은 것이 테이블이 아니라 **생성기**(합성 데이터·계산된 사실·외부 API)일 때
`ledger_config.json`에 항목을 만들려고 하면 **막힌다** — `config.validate()`가 `columns` 일곱(`row_identity`·`lot`·`event_type`·
`parent_lot`·`child_lot`·`slots`·`wafers`)을 **무조건** 요구하고, 생성기에는 그 컬럼이 하나도 없다.

🔴 **빈 문자열로 채워 통과시키지 마라.** 그러면 **아무것도 서술하지 않는 선언**이 운영자의 config에 영구히 남고,
그것이 R-2026-08-13-D가 끝낸 「검사되지만 아무 데도 도달하지 않는 필드」의 재발이다.

**대신 생성기가 자기 선언을 «자기 안에» 든다.** 실물: `server/scripts/seed_syn_process_ledger.py`.

| 무엇 | 생성기는 어디에 두나 | 왜 여전히 계약인가 |
|---|---|---|
| 허용 파생(`#<derivation>`) | 모듈 상수 `DECLARED_DERIVATIONS` | `gate.screen_molecule`에 **그대로 넘긴다** — 목록 밖 파생은 config 소스와 **똑같이** 거절된다 |
| 허용 subject 타입 | 모듈 상수 `DECLARED_SUBJECT_TYPES` | 같은 인자 자리(§3.5-bis의 다섯째 질문)로 들어간다 |
| provenance 경계 | `source_translator_ver`의 **접두**(`<소스>/<버전>/rules:<규칙>`) | 롤백이 목록이 아니라 **술어**가 된다(§4.7) |

🔴 **바뀌지 않는 것이 핵심이다 — 문은 하나뿐이다.** 생성기도 `gate.building_molecule` 스코프 «안»에서 `gate.screen_molecule`을 지나
`store.LedgerStore.write_batch`로 쓴다. **원장에 쓰는 두 번째 경로를 만들지 마라** — 픽스처가 게이트를 우회하면
「게이트가 진짜 데이터를 거절하는가」를 그 픽스처로는 영원히 증명할 수 없다.

⚠️ **`source_who`를 롤백 표식으로 쓰지 마라.** 생성기는 `source_who`를 **일부러 여러 개** 쓴다(장비 로그와 레시피 대장은
서로 다른 발화자이고, 계급 판정이 그 차이에 걸려 있다) — 그래서 그 컬럼은 픽스처의 경계가 될 수 없다.

---

## 4. 운영자 절

> 🔴 **무엇을 어느 순서로 돌리는가는 [ONTOLOGY_LEDGER_SETUP §2](./ONTOLOGY_LEDGER_SETUP.md)가 소유한다**(2026-08-15 통폐합).
> 운영에서 **실제로 돌린 기록**은 [OPERATOR_RUNBOOK §6·§8](../process/OPERATOR_RUNBOOK.md).
> 이 절은 **명령이 무엇을 하는지·숫자를 어떻게 읽는지**만 적는다.

### 4.1 설치·백필의 «명령과 순서» → 🔴 **[ONTOLOGY_LEDGER_SETUP §2](./ONTOLOGY_LEDGER_SETUP.md)이 소유한다**

**마이그레이션 둘·백필 명령·플래그 표는 2026-08-15에 그쪽으로 옮겼다.** 여기 남는 것은 **그 명령들이 무엇을 하는지**뿐이다.

②(`add_ledger_refusal_reasons.py`)에 대해:

- **`ALTER TABLE … ADD COLUMN <nullable, DEFAULT 없음>` 하나뿐이다.** PG 11+에서 **카탈로그만** 바꾸므로
  힙을 안 건드리고 표 크기와 무관하다. 게이트가 `pg_attribute`라 **재실행은 DDL도 잠금도 0**이다.
  **어떤 표의 행도 읽거나 쓰지 않는다** — 기존 커서 행은 값을 전부 유지하고 NULL 하나를 얻는다.
- 🔴 **안 돌려도 «서버가 500을 내지 않는다».** 양방향으로 방어돼 있다 — 쓰기 쪽은 `ensure_schema`가 같은 문장을
  모든 백필 첫 단계에 적용하고(번역기는 자기가 못 쓰는 표를 만날 수 없다), 읽기 쪽 `/coverage`는
  **어느 컬럼이 있는지 카탈로그에 먼저 묻고** 있는 것만 SELECT한다. 이 스크립트는 **운영자의 진입점이자 감사 기록**이다.
- 🔴 **NULL은 `{}`가 아니다.** NULL = 「이 행은 컬럼보다 오래됐다 — 그 집계는 영원히 분해 못 한다」,
  `{}` = 「현재 쓰기가 이 행을 소유했고 거절 0건」. **개발 두 DB 모두 정확히 그 NULL 행을 갖고 있었다**
  (`molecules_refused = 1`). 읽는 법은 §4.4.
- **되돌리기(`--reverse`)는 진짜 역방향이다** — 원자도, 커서 위치도, 집계도 잃지 않고 **내역만** 잃는다.

①(`add_ledger_events.py`)에 대해:

- **추가 전용·멱등.** DROP 없음, 기존 것의 ALTER 없음, 기존 테이블의 행을 건드리는 문장 없음. **새 테이블 둘만.**
- **큰 기존 테이블에 컬럼을 붙이지 않으므로 잠금 위험이 없다.** 안 돌아도 아무것도 안 깨진다.
- **DDL은 그 파일에 없다** — `server/ledger/schema.py`가 유일한 철자이고 마이그레이션은 그것을 부른다.
  (테스트가 스크래치 스키마에 **같은** 테이블을 짓게 하려면 사본이 있으면 안 된다.)
- **파티션은 만들지 않는다.** 번역기가 **자기가 쓸 달을 쓰기 직전에** 만든다 — 존재할 달은 배포일이 아니라 **데이터**가 정한다.

### 4.2 백필이 «무엇을 고르는가»

🔴 **명령은 하나이고 «선언»이 경로를 정한다** — `run()`이 선언된 `kind`로 혈통/관측/이동 루프를 고른다(§1.1 `backfill.py`).
운영자가 외울 것은 소스 이름뿐이고, **명령줄과 플래그는 [ONTOLOGY_LEDGER_SETUP §2](./ONTOLOGY_LEDGER_SETUP.md)**.

### 4.3 재실행 의미론 — **왜 재실행이 0을 쓰는가**

- **그냥 다시 돌리면**: 커서가 이미 소스 head에 있으므로 **0행을 읽고 0원자를 쓴다.** 정상이다.
- **`--reset-cursor`로 다시 돌리면**: 행은 다 읽히고 원자도 다 만들어지는데
  `uq_ledger_atom`이 **전부 걸러낸다** → 보고가 `attempted=N inserted=0 deduped=N`.
  🔴 **두 수를 절대 합치지 마라.** `attempted > inserted`는 「커서가 이미 끝난 일감을 통과시켰고 인덱스가 알아봤다」는 뜻이고,
  운영자가 그것을 **볼 수 있어야** 한다.
- **규칙을 바꾸고 `--reset-cursor`로 다시 돌리면**: `source_translator_ver`가 바뀌었으므로 **새 원자가 들어간다.**
  그것이 맞다 — **다른 규칙이 만든 다른 주장**이다. (옛 원자는 남는다. 옛것을 없애야 하는 상황은 §4.5.)
  - 🔴 **「규칙을 바꿨다」의 범위가 생각보다 넓다.** `translator_version()`은 **소스 선언 전체를 해시**하므로
    `subject_types` 한 줄을 더한 것 같은 변경도 해시를 움직인다 — 실제로 `eb1ae8b`에서 `d8d1c9e0` → `34311f15`.
    ⚠️ **「다시 돌려서 안 변한 걸 확인하자」가 위험한 자리가 여기다**: 커서 전진 재실행은 **0행을 읽어 아무것도 증명 못 하고**,
    `--reset-cursor` 재실행은 **878행을 dedupe하는 것이 아니라 «같은 주장, 새 provenance»로 878행을 새로 쓴다.**
    그래서 `assy_manager`는 **일부러 재백필하지 않았다.** 착지가 안 변했다는 것은 커서와 무관하게 따로 증명됐다
    (43 소스행 전수 재번역 후 저장된 878원자와 **주장 단위 대조** — 878/878, 한쪽에만 있는 주장 0건).
- 🔴 **혈통 소스의 커서는 세계 시각(`event_time`)이다.** 늦게 도착한 오래된 타임스탬프 행은 **커서 뒤에 앉고 이 백필은 못 본다.**
  일회성 백필에는 받아들일 만하고(이미 있는 것을 쓸어 담는 것이 목적) **라이브 구독에는 아니다** —
  그쪽은 아웃박스가 몰아야 한다. `--from`으로 어느 창이든 다시 돌릴 수 있고 재실행은 유니크 인덱스 덕에 공짜다.
- 🔴 **관측 소스의 커서는 «키셋»이고 그것은 세계 시각이 아니다**(2026-08-14 3차). `(updated_at, row_id)`는 **도착·수정의 워터마크**이고,
  세상의 시각(`inspection_run.observed_at`)은 원자의 `occurred_at`으로만 간다. **두 시간을 한 필드에 섞지 않는 것이 요점**이다.
  - **왜 시각 커서가 아닌가**: 대량 적재가 `updated_at` 하나를 수만 행에 찍는다(실측 91,756행 / 서로 다른 값 92개) —
    시각 커서였으면 **한 번의 적재가 쪼갤 수 없는 한 그룹**이 되어 배치 경계가 사라진다.
  - **되레 얻는 것**: 운영자가 소스 행을 고치면 `updated_at`이 올라가고 **그 행이 다시 방문된다** —
    재발화가 원장에 도달하는 경로가 커서 자체에 들어 있다(같은 내용이면 유니크 인덱스가 걸러낸다).
  - ⚠️ **그래서 이 커서로는 「세계시각 기준 뒤처짐」을 낼 수 없고, 보고가 그렇게 «말한다»** — `lag_basis`(§4.4).

### 4.4 커서·박동 숫자 읽는 법

```sql
SELECT * FROM ledger_translator_cursor;
```

`assy_manager` 2026-08-13 실측 (⚠️ `eb1ae8b`·`0198e7e` **이전** 판독 — 아래 두 주석을 함께 읽을 것):

```
source=lot_event  translator_ver=lot_event/1/rules:d8d1c9e0
cursor_value={"event_time": "2026-05-21 20:33:00"}
molecules_done=26  atoms_written=909  atoms_deduped=0
molecules_refused=1  incomplete_molecules=2
refusal_reasons=NULL                       ← 이 행은 컬럼보다 «오래됐다»
source_head={"event_time": "2026-05-21 20:33:00", "rows_behind": 0}
```

⚠️ **`translator_ver`의 해시는 `eb1ae8b`으로 `34311f15`가 됐다.** 위 판독의 `d8d1c9e0`은
**저장된 원자들의 provenance이지 지금 번역기의 버전이 아니다** — `assy_manager`는 **일부러 재백필하지 않았다**
(커서 전진 재실행은 0행을 읽어 아무것도 증명 못 하고, 리셋은 원장을 두 배로 만든다. §4.3).
**이 박스에서 새로 백필하면 새 해시가 찍힌다.**

| 필드 | 읽는 법 |
|---|---|
| `cursor_value` | **온전히 처리한 마지막 `event_time` 그룹.** 크래시하면 그 그룹의 «다음»부터 다시 읽는다 |
| `molecules_done` | 이 소스에 대해 **본** 분자 총계. 🔴 **거절된 것도 포함**한다 — `molecules_refused`는 그 부분집합이다 |
| `atoms_written` / `atoms_deduped` | 실제 INSERT된 수 / 유니크 인덱스가 걸러낸 수. **누적**이다(SET이 아니라 `+=`) |
| `molecules_refused` | 문 앞에서 통째로 거절된 분자. **왜인지는 이제 옆 칸에 있다** — `refusal_reasons` |
| **`refusal_reasons`** | **그 집계의 내역.** `{사유: {"count": N, "last_at": "<시각>"}}`. 🔴 **NULL과 `{}`는 다른 뜻**이고, 🔴 **누적이다**(§아래) |
| `incomplete_molecules` | 착지했지만 소스 이벤트의 행이 다 안 온 분자. **거절이 아니다.** 혈통 사슬에 구멍이 있는 이유 |
| `source_head` / `head_probed_at` | 티어 2 프로브가 마지막으로 본 소스 끝과 그 시각 |

🔴 **관측 소스의 행은 «다른 잣대»로 읽는다** (2026-08-14 3차). 같은 표, 같은 컬럼인데 두 필드의 뜻이 다르다:

| 필드 | 혈통 소스 | 관측 소스 |
|---|---|---|
| `cursor_value` | 온전히 처리한 마지막 **`event_time` 그룹** | 마지막으로 처리한 **키셋**(`updated_at`+`row_id`) — **세상의 시각이 아니라 도착·수정 워터마크**다 |
| `lag_basis` | `world_time` | **`arrival_watermark`** |
| `world_time_lag_seconds` | 「세상이 이만큼 앞서 있다」 | 🔴 **언제나 `null`이다 — 「안 뒤처짐」이 아니라 「이 잣대로는 잴 수 없음」**이다 |

⚠️ **도착 뒤처짐을 세계시각의 이름으로 보고하지 않는 것이 판정이다.** 그렇게 하면 운영자가
「소스가 조용하다」와 「번역기가 멈췄다」를 **구별할 수 없고**, 그것이 이 프로젝트가 `absent-zero-is-not-inert-zero`로 이미 값을 치른 모양이다.

🔴 **이 수들은 전부 «이 커서 행이 사는 동안»의 누적이지 «이번 런»이 아니다.** `_advance_cursor`는 처음부터
`컬럼 + EXCLUDED.컬럼`을 써 왔다 — **런 스코프 수를 이 표에서 읽어낼 방법은 없다.**
최근성은 `updated_at`과 각 사유의 `last_at`이 나른다: **조용해진 사유는 옛 타임스탬프를 유지하고,
깨끗한 런은 기존 항목을 다시 찍지 않는다.** 화면·보고는 「누적」이라고 말해야 하고 「지난 런의」라고 말하면 안 된다.

🔴 **`refusal_reasons`가 이 DB에서 사유를 읽을 수 있는 «유일한» 자리다.** 게이트의 카운터는 백필 프로세스의
메모리에만 있고, 웹서버는 `server/ledger`를 일부러 import하지 않으며, 박동 노트는 서빙되지 않는다.
그래서 이 컬럼이 생기기 전에는 **어떤 읽기도 사유 하나를 낼 수 없었다.**

**NULL vs `{}` — 실제로 부딪히는 자리다.** 두 개발 DB 모두 `molecules_refused = 1`인 채로 이 컬럼을 맞았다.

| 판독 | 뜻 | 할 일 |
|---|---|---|
| `NULL` | 컬럼보다 오래된 행. **그 1건의 이름은 이미 끝난 프로세스와 함께 사라졌다** | **없다 — 배포 이력이다** |
| `{}` | 현재 쓰기가 이 행을 처음부터 소유했고 거절 0건 | 없다 |
| `{"undeclared_vocabulary": {"count": 1, …}}` | 그 사유로 분자 1개가 거절됨 | 소스 데이터를 본다(§4.4 말미의 실측 예) |

`GET /api/ledger/coverage`가 이 차이를 **`refusals_unaccounted`**로 계산해 준다 — 부호 읽는 법은 §4.6.

**박동(heartbeat)** — `/health`가 다른 프로세스에서 읽는다.

```
ledger gate refusals: molecules=1 source_rows=1 built_atoms_discarded=0 | lot_event:undeclared_vocabulary=1
 || incomplete source molecules: lot_event=2
ledger lag[cursor=2026-05-21 20:33:00, world_lag=…, cursor_age=…, rows_behind=0, head=2026-05-21 20:33:00]
```

- **거절 노트는 깨끗하면 `None`**이다 — 줄이 «나타나는» 것이 신호다.
- **lag 노트는 언제나 나온다** — 「0만큼 뒤처졌다」는 운영자가 봐야 하는 정보이고, **그 부재**가 그래프 워커의 결함 모양이었다.
- `rows_behind=?`는 「안 뒤처졌다」가 **아니라** 「안 물어봤다」(스로틀)다. `head_probe_age`가 같이 나온다.
- 🔴 **커서가 안 움직이는 것은 `world_lag`·`cursor_age` 둘만으로 보인다** — 질의 0회. 그것이 티어 1의 존재 이유다.

**실측 예의 거절 하나**(`assy_manager`): `lot_event`에 `event_type='123'`인 행이 하나 있다
(`DT-2601-004|123|2026-05-21 20:33:00`). 선언에 없는 event_type이라 `undeclared_vocabulary`로 거절되고
**1 소스행 / 0 원자**로 세어졌다. ⚠️ **커서는 그 위를 지나 전진한다** — 거절은 커서를 세우지 않는다.
구멍은 커서가 아니라 **거절 카운터와 로그**가 말한다.

### 4.5 정정은 «재백필»이지 제자리 UPDATE가 아니다

`occurred_at_timezone`이 틀렸다는 식의 정정에서:

🔴 **버전 붙여 공존시키면 안 된다.** 해결기는 계급과 `source_who`가 같으면 **`occurred_at` 내림차순**으로 이긴다.
낡은 원자와 정정본은 `source_who='lot_event'`를 공유하고, **틀린 시각이 9시간 «더 늦다»** —
그래서 공존시키면 **틀린 원자가 구성상 정정본을 이긴다.**
`bee1aeb`이 실제로 택한 길: **비우고 다시 백필**(`assy_qa` 878 → 878, `inserted=878 deduped=0` —
`occurred_at`과 `source_translator_ver`가 둘 다 dedupe 열쇠에 있고 둘 다 바뀌었다).
🔴 **제자리 UPDATE는 없다.** 원장에 UPDATE 경로는 구성상 존재하지 않는다(§5).

### 4.6 화면과 `/api/ledger/*`

추적 화면은 `client2/ledger.html`이고 `GET /api/ledger/trace?lot=&slot=` 하나를 쏜다.
**응답 형태는 pin됐다 — 바꾸는 것은 편집이 아니라 에스컬레이션이다.** 라우트 계약의 정본은
[architecture/backend §2](../architecture/backend.md), 세부 의미는 [spec/LEDGER_TECHNICAL_SPEC §4](../spec/LEDGER_TECHNICAL_SPEC.md).

**`GET /api/ledger/coverage`** — 화면이 로드할 때 **한 번** 묻는다(착지 `d78e1ec`). 🔴 **부재·공백에도 에러가 아니라 200과 `state`를 낸다**:

| `state` | 뜻 | 운영자가 할 일 |
|---|---|---|
| `absent` | 테이블이 없다 | **마이그레이션 미실행** — §4.1 |
| `empty` | 테이블은 있고 원자 0 | **백필 미실행** — §4.2 |
| `ready` | 추적 가능 | — |

이 라우트가 없으면 **네 가지 서로 다른 「없음」이 같은 빈 화면**이 된다: 마이그레이션 미실행 · 백필 미실행 ·
없는 랏 · 혈통 주장 없는 랏. 원자가 0이면 보행은 **모든** 랏에 `[unknown_subject]`를 주므로
빈 원장과 진짜 없는 랏이 화면에서 구별되지 않는다. `coverage`가 **어느 세계인지**를 말해 주면
같은 홉이 `empty`에서는 「백필 미실행」으로, `ready`에서는 「없는 랏」으로 읽힌다.

**이 박스 실측 (2026-08-13, `:8080` — ⚠️ `0198e7e` «이전» 판독이라 아래 확장 필드가 안 보인다)**:
```
GET /api/ledger/coverage  ->  200
{"state":"ready","lots":25,"sources":["lot_event"],
 "occurred_at":{"from":"2026-05-03T02:17:00+09:00","to":"2026-05-21T20:33:00+09:00"},"sample":[…]}
```

**`0198e7e`로 더해진 것 — 상태 표시줄과 어드민 탭이 «이 한 요청»을 나눠 쓴다:**

| 필드 | 운영자가 읽는 법 |
|---|---|
| `atoms` | `{estimate, exact, method, unanalyzed_partitions}`. ⚠️ **`exact`는 «언제나» `false`다** — 이 라우트에 행을 세는 갈래가 없다. `pg_class.reltuples`이므로 대량 쓰기와 다음 autovacuum 사이에는 **그냥 낡은 수**이고, `unanalyzed_partitions > 0`이면 **그만큼의 파티션을 못 보고 낸 수**라는 뜻이다(0으로 세지 않는다). 「원장이 행을 잃었다」로 읽지 말 것 |
| `partitions` | `{count, list:[{name, bound}]}`. `bound`는 **PostgreSQL이 렌더한 문자열 그대로**다 |
| `cursors[]` | §4.4의 커서 행 전체 + `refusal_reasons` + **`refusals_unaccounted`** |
| `last_atom` | `{occurred_at, recorded_at}`. `recorded_at`은 **uuid7 `id`에서 디코드**한 것이라 추가 컬럼도 비용도 없다(v7이 아닌 id면 NULL — 난수에서 그럴듯한 시각을 만들지 않는다) |

🔴 **`refusals_unaccounted`는 «부호»로 읽는다** — 수가 아니라 부호가 계약이다.

| 부호 | 뜻 | 할 일 |
|---|---|---|
| `0` | 내역이 집계를 전부 설명한다 | 없다 (보통의 답) |
| `> 0` | 컬럼이 생기기 «전»에 세어진 거절 — 그 이름은 이미 사라졌다 | 🔴 **없다. 배포 이력이지 결함이 아니다** |
| `< 0` | 내역이 집계를 **초과**한다 = **진짜 장부 결함** | 보고할 것 — 「세면서 분자를 거절하지는 않는」 새 경로가 열렸다는 뜻 |

⚠️ **이 박스의 두 라이브 커서 행은 지금 `1`을 읽는다** — 컬럼이 생기기 전 `undeclared_vocabulary` 1건이다.
**화면은 이것을 이력으로 렌더해야 하고 「1건 거절, 사유 없음」으로 렌더하면 안 된다.**
🔴 음수는 이론이 아니었다 — 2026-08-13에 실제로 `-1`이 측정됐고(`_slot_map`의 삼킴) `f313279`가 닫았다.
**갈래는 남겨 뒀다: 그것이 탐지기다.**

⚠️ **`atoms.estimate`가 `count(*)`보다 낫다는 것은 이 박스에서 «시연할 수 없다»** — 909 원자에서 정확한 카운트는
**0.194 ms**다. 카탈로그를 고른 근거는 **구조**(O(1) 대 O(원자))이지 측정된 승리가 아니다. 그렇게 인용하지 말 것.

**측정된 비용**(`assy_manager` 웜, 이 박스): 호출 전체 **4.3–4.7 ms**. 별도 프로브 DB(280,000원자 / 100,000랏 /
12파티션) 전체 **31 ms**이고 그중 `count(register)`가 24.06 ms — 🔴 **커지는 필드는 `lots` 하나이고
원자가 아니라 «랏»을 따라간다.** **캐시하지 않는다**: 이 라우트는 「방금 돌린 마이그레이션·백필이 먹혔나」를 묻는
자리라, 캐시는 답이 가장 중요한 순간에 5초간 옛 세계를 답한다. 폴링하는 소비자가 생기면 **그쪽에서** 캐시할 것.

🔴 **테이블이 없을 때 `/trace`는 «카탈로그와 SQLSTATE»로 판정한다 — 에러 문자열이 아니다.**
`to_regclass` 선조회가 먼저이고(그 자체가 요청 트랜잭션을 깨끗하게 유지한다),
경합 대비 백스톱은 SQLSTATE **`42P01`**이다. 503의 본문은 **산문이 아니라 구조**다 —
클라는 `detail.reason`·`detail.state`로 분기하고 운영자는 `detail.message`를 읽는다.
`state`는 `/coverage`의 어휘를 **일부러 그대로 쓴다**(한 낱말이 두 라우트에서 한 뜻).

#### 4.6-bis `GET /api/ledger/structure?window=` — **구조를 «보는» 자리** (2026-08-14)

`/coverage`가 「원장이 **무엇을 덮고 있나**」라면 이쪽은 「**무엇이 무엇과 이어져 있고, 데이터가 어디에 얼마나 있나**」다.
🔴 **유형 수준이다** — 랏·웨이퍼·보이드는 한 건도 안 나온다. 그건 `/trace`의 화면이고 이건 그 **보완**이다.
응답 계약의 정본은 [backend §2](../architecture/backend.md)이고 의미론은 [spec §4.7](../spec/LEDGER_TECHNICAL_SPEC.md) — 여기는 **읽는 법**만 적는다.

**엣지·노드마다 «한 낱말»이 온다. 클라는 세어서 판정하지 않고 그 필드로 분기한다**([spec §4.7](../spec/LEDGER_TECHNICAL_SPEC.md)):

| 낱말 | 뜻 | 운영자가 읽는 법 |
|---|---|---|
| `flowing` | 선언돼 있고 원자가 흐른다 | 정상 |
| `declared_only` | 선언돼 있고 **세었는데 0** | 🔴 **정직한 빈 축.** 「어휘엔 있는데 아무도 안 쓴다」 — **숨기지 않는 것이 이 화면 존재 이유의 절반**이다 |
| `undeclared` | **원자는 있는데 어휘가 그 모양을 선언하지 않았다** | **드리프트.** 게이트가 막아야 할 일이라 보이면 조사 대상 |
| `unmeasured` | **아무도 안 셌다**(`ledger_events` 부재) | 마이그레이션 미실행 — §4.1. **`0`이 아니다** |
| `declared_unconsumed` | 선언은 있고 **읽는 것이 하나도 없다** | 기전 층. 셀 수가 «없는» 것이지 0인 것이 아니다 |

- 🔴 **`atoms: 0`과 `atoms: null`은 다른 답이다**(`/kinds`와 같은 규칙) — `0`은 「세었고 없다」, `null`은 「안 셌다」.
  같게 렌더하면 이 프로젝트가 이미 한 번 값을 치른 `absent-zero-is-not-inert-zero`를 다시 밟는다.
- 🔴 **관계가 아예 없어도 200이고 «선언된 절반은 그대로 나간다»** — 원장 없는 박스에도 온톨로지는 있고,
  빈 화면을 보고 있는 사람이 바로 그것을 봐야 할 사람이다. 200 아닌 결말은 **셋뿐**([spec §4.7](../spec/LEDGER_TECHNICAL_SPEC.md)).
- 🔴 **`window`는 «건수»만 좁히고 구조는 절대 안 좁힌다.** 창을 걸어도 선언된 엣지는 전부 화면에 남고 `atoms: 0`이 된다 —
  안 그러면 아래의 크기 방어가 위 표의 `declared_only` 규칙을 무력화한다.
- ✅ **[2026-08-14 3차 — 닫혔다] 결함 관측이 이 그래프에 «들어왔다».** 종전 판독은 「`observed` 술어가 선언된 적이 없고
  모든 종류가 `in_ledger: false`이며 `ledger_edge_ids`가 빈 배열」이었다 — **R-2026-08-14-D의 번역이 그것을 뒤집었다.**
  지금 실측: 엣지 **`Wafer|observed|value`**가 `edge_state: "flowing"`, 원자 **102,177**(보이드 91,756 + 박리 10,421),
  **전량 등급 `observation`(2류)**, `source_who`로 소스가 갈려 보인다. `/kinds`는 두 종류 다 **`in_ledger: true` · `ledger_state: "flowing"`**.
  🔴 **그때의 빈 배열이 「연결 실패」가 아니라 「그런 연결은 없다」였던 것처럼, 지금의 수도 «선언 + 측정»의 합이다** — 낱말이 생겼고 데이터가 흘렀다.
  ⚠️ **여전히 참인 것 하나**: 요인 축 8개는 아직 원장이 번역하지 않는 소스로 **옆조인**한다(R-D 원칙 ④가 **과도기**로 선언한 그것) —
  「모든 것이 이미 걷기로 닿는다」를 전제로 화면을 설계하면 안 된다.
- ⚠️ **선언된 엣지 대부분이 `declared_only`인 것은 정상이다** — 실측 **엣지 54 중 흐르는 것 9 · `declared_only` 45**(2026-08-14 2차 판독. 3차의 관측 번역으로 흐르는 엣지가 하나 늘었다).
  「45개가 고장났다」가 아니라 **「선언된 문법의 대부분이 아직 안 쓰인다」**는 사실이 처음 보인 것이고, 그것이 이 화면의 값이다.
  `Equipment`·`Product`가 고립 노드인 이유는 [spec §4.7 ⑨](../spec/LEDGER_TECHNICAL_SPEC.md).
- **[확장성] 유형 센서스는 본질상 O(원자)**이고 그 컬럼 조합을 서비스하는 인덱스는 없다(있던 후보는 **소비자 부재로 제거**됐다 —
  [spec §2.2](../spec/LEDGER_TECHNICAL_SPEC.md)). 방어는 **캐시가 아니라 선언된 크기 게이트**다: 파티션 합계가 `FULL_CENSUS_MAX_BYTES`를 넘으면
  `LARGE_LEDGER_WINDOW`가 **강제**되고 응답이 `window.forced`·`forced_reason`으로 **그렇게 말한다**.
  ⚠️ **화면이 한 달치 수를 「전체」라고 부르는 일이 없어야** 하므로 그 두 필드를 렌더에서 빼지 말 것.
  **캐시하지 않는 이유는 `/coverage`와 같다** — 백필 직후가 이 화면을 여는 자리이고, 캐시는 답이 가장 중요한 순간에 **옛 구조**를 답한다.
- ⚠️ **기전 층(M4)은 오늘 `state: "absent"`다** — [PHYSICS_ONTOLOGY_SETUP §4](../architecture/PHYSICS_ONTOLOGY_SETUP.md)가 완성된 모양을 **제안**하지만
  코드가 읽을 수 있는 선언이 0이다(config·dict·로더·라우트·`Model` 개체 타입·소비자 전부 없음). 응답은 그것을
  `reason: "no_declaration_file"` + `spec_ref`로 **말하고, 문서의 제안을 데이터로 옮겨 채우지 않는다.**
  🔴 **씨앗은 `server/config/mechanism_models.json`이고 `.sample`은 «일부러» 안 실었다** — 이 프로젝트에서 `.sample`은 「출하된 선언」이라
  제안을 그 자리에 두면 **착지한 선언으로 오독된다.** 파일이 놓이는 날 코드 변경 없이 렌더된다.
  - ✅ **[2026-08-14 · `f52628f` — 그날이 왔다] 위 두 줄은 낡았다.** `server/config/mechanism_models.json.sample`이 착지했고(**모델 셋 · 방향만 있는 엣지 22개**),
    구조 뷰는 **코드 0줄 변경으로** 그 층을 답한다.
  - **[2026-08-14 밤 — 현행 확정]** 라이브 `mechanism_models.json`도 실재하고 소비자는 **둘**이다: 이 라우트의 기전 층 + **3관문 랭킹의 기전 관문**(`server/mechanism_gate.py` — 요인→결함 도달 가능성).
    🔴 **[2026-08-15 정정] 파일에 `models`라는 블록은 «없다»** — 최상위 예약 키는 `__doc`와 `bindings`뿐이고 **나머지 키 하나하나가 모델**이다(`mechanism_gate`의 `KEY_DOC`/`KEY_BINDINGS`). `signatures`는 **모델 «안»의 키**이고
    (방향만 있는 인과 엣지 `dir: '+'/'-'/'u'`. **방정식은 일부러 없다**) 사람용 공간 패턴 문서라 **로더가 무시한다**. · **`bindings`**(필드→물리량. 🔴 **항목 목록이 아니다** —
    바인딩 안 된 후보도 대조에서 안 좁혀지고 기전 칸에 `unknown`을 달고 나온다). 🔴 **바인딩은 «데이터가 실재하는 날» 켠다**(`87374a5`) — `post_bond_queue_h`는 측정 필드가 없는 동안 「정직한 공백」으로
    문서화돼 있다가 증강 레인이 필드를 실재로 만든 저녁에 바인딩이 켜졌다(코드 0줄). **화면을 완성돼 보이게 하려고 공백에 바인딩을 지어내지 말 것** — 남은 공백 다섯(`stage_particle`·`humidity` 등)이 그 규율의 현재형이다.
    ⚠️ **`.sample`과 라이브를 «동일하게» 편집한다** — 추적되는 것은 `.sample`뿐이다.

**이 박스 실측 (2026-08-14 2차, `assy_manager`, 84,747원자 · 두 파티션)**: census **182 ms** · 호출 전체 **285 ms** · 페이로드 **59 KB**.
⚠️ **이 수를 다른 문서의 「285 ms」와 섞지 말 것** — 버려진 SQL 사다리 철자의 비교값에도 같은 수가 있다([spec §5.7](../spec/LEDGER_TECHNICAL_SPEC.md)).

🔴 **같은 화면, 관측 번역 이후 (2026-08-14 3차)**: 원장 **186,924원자 · 101,326,848 바이트 · 파티션 다섯**
(`2026_09`~`2026_11`이 **번역기 손에** 새로 생겼다 — §4.1 ①의 「파티션은 데이터가 정한다」가 다시 발화한 것).
**census 85 ms → 438 ms**(그룹 14개 · **같은 라운드에 잰 전·후 쌍**이다. ⚠️ **바로 위 182 ms와 같은 측정이 아니니 한 줄에 세우지 말 것** — [spec §5.7](../spec/LEDGER_TECHNICAL_SPEC.md)의 라벨 주의).
🔴 **여전히 `FULL_CENSUS_MAX_BYTES`(256 MB) 아래라 창은 강제되지 않았다** —
즉 오늘 이 화면은 아직 **전 기간**을 답하고 있고, 그 사실이 `window.forced`로 나간다. 원자당 비용은 §5.7의 외삽 그대로다.
⚠️ **합성·이 박스이고 운영 증거가 아니다.**

#### 4.6-ter `GET /api/ledger/kinds` — **「이 종류가 원장에 있나」를 묻는 자리** (2026-08-14 3차)

이 라우트는 원래 **콘솔의 종류 선택기**를 짓는 자리였다(소스 테이블의 관측 수·런 수). 관측 번역이 착지하면서
**원장 쪽 위치를 말하는 필드 다섯**이 붙었다 — 계약은 [backend §2](../architecture/backend.md), 의미론은 [spec §4.8](../spec/LEDGER_TECHNICAL_SPEC.md).

| 필드 | 운영자가 읽는 법 |
|---|---|
| `in_ledger` | **선언 사실**이다 — `ledger_config.json`의 어떤 소스가 이 종류를 번역한다고 «말했나». 질의 0회. **데이터가 있다는 뜻이 아니다** |
| `ledger_source` / `ledger_predicate` | 그 소스 이름과 술어(`observed`). 롤백 술어를 짜는 재료다(§4.7) |
| `ledger_state` | **측정된 절반**, `/structure`의 낱말을 그대로 쓴다 — `absent`(아무도 선언 안 함) · `declared_only`(선언은 됐고 **세었더니 0** = **백필 미실행**) · `flowing`(원자가 있다) · `unmeasured`(원장 관계가 없거나 세기에 너무 큼) |
| `ledger_atoms` | 그 수. 🔴 **`null`은 `0`이 아니다** — `null` = 「아무도 안 셌다」, `0` = 「세었고 없다」. 256 MB 규칙에 걸리면 `null`이 정답이다 |

🔴 **불리언 하나로는 부족해서 둘로 나눈 것이다.** 번역 전에는 「보이드 91,756건이 소스 테이블에 있는데 `in_ledger: false`」였고,
그 한 낱말은 **「선언이 없다」와 「백필을 아직 안 돌렸다」를 구별하지 못했다** — 운영자가 할 일이 정반대인 두 상태다.

**이 박스 실측 (2026-08-14 3차)**: `void` · `delam` 둘 다 `in_ledger: true` · `ledger_state: "flowing"` ·
`ledger_atoms` **91,756 / 10,421** — 즉 **소스 행 수와 정확히 같고 거절 0 · 불완전 0**이다.

#### 4.6-quater `GET /api/ledger/journey` — **두 장이 «어디서» 갈라졌나** (2026-08-14 밤)

⚠️ **오늘은 REST로만 있다 — 이 응답을 그리는 화면은 «아직 없다».** 계약은 [backend §2](../architecture/backend.md), 의미론은 [spec §4.9](../spec/LEDGER_TECHNICAL_SPEC.md).

```
GET /api/ledger/journey?scope=wafer:SYN-BW-101-06,SYN-BW-101-15&finding=void&window=30d
```

- 🔴 **주어가 «둘»이어야 한다.** 아니면 **422**이고 본문이 `reason: "scope_is_not_a_pair"` · `arity_resolved` · **풀린 주어 이름**을 든다.
  운영자가 읽는 법은 하나다 — **에러가 아니라 「그 질문은 순위 레일(`/siblings?scope=`)의 것」이라는 안내**다(실측: 웨이퍼 셋 → 3, 실재 하나 + 오타 하나 → 1).
- **읽는 순서**: `headline`(「같은 길 N구간, 갈라진 곳 M곳」) → `segments[]`를 위에서 아래로 → 갈라진 구간의 `sentence`(**첫 줄이 항상 사실 문장**) → `items[]`.
- **구간마다 무엇을 보는가**:

| 필드 | 읽는 법 |
|---|---|
| `display` | 화면에 찍는 구간 이름(「후공정 · 본딩」). **선언이 없으면 원시 값이 그대로 보인다 — 그것이 의도다**(빠진 선언은 빠져 보여야 한다) |
| `verdict` | `same`(둘 다 걸었고 전 항목 동일) · `diverged` · `one_sided`(**한쪽만 걸었다**) |
| `agreement` | 🔴 **「같음」도 정보다.** `actors`(런의 신원이 같았나)와 `content`(값이 같았나)를 **따로** 답한다 — 실측 소유자 쌍에서 여덟 구간 전부가 수치 하나쯤은 다르지만 **런 신원은 다섯에서 일치**한다. 회색 한 줄(「본딩 — 같음: 장비 … · 레시피 rev …」)은 `agreement.sentence`다 |
| `position_basis` | `inference`면 **그 구간의 자리가 레시피 책의 날짜에서 왔다** — 물리적 순서로 읽지 말 것. 같은 사실이 `notes[]`에도 모여 나온다 |
| `when.gap_seconds` | 두 주어의 그 구간 사이 시간차. `null`이면 한쪽에 시각이 없다 |

- **항목(`items[]`)마다 A/B 두 칸**이고, 🔴 **빈칸으로 보이는 것이 세 종류다** — `not_recorded`(구간은 걸었는데 이 항목 기록 없음) · `segment_absent`(구간 자체를 안 걸음) · `recorded_null`(소스가 명시적 null을 말함). **`0`은 빈칸이 아니라 측정값이다**([spec §4.9 ⓑ](../spec/LEDGER_TECHNICAL_SPEC.md)).
- **`six`(육하원칙)**: 여섯 슬롯 전부가 답하거나 **「기록 없음」이라 말한다**(빈칸·생략 없음). 🔴 **「왜」만 다른 층이다** — 「물리 모델에 아직 없음」은 **원장의 결측이 아니라 선언의 부재**이고, 그래서 그 슬롯의 `is_missing_record`는 언제나 `false`다. 화면은 그 둘을 **다른 문구·다른 색**으로 그려야 한다.
- **`notes[]`에 잘림이 실린다** — 주어당 원자 상한(`atoms_truncated`)·구간 상한(`segments_truncated`). **조용히 잘리는 것이 없다.**

🔴 **`server/config/ledger_journey.json`을 «쓰는» 절차는 [ONTOLOGY_LEDGER_SETUP §6.3](./ONTOLOGY_LEDGER_SETUP.md)이 소유한다**(2026-08-15 이관).
여기 남는 것은 그 선언이 응답에 대해 뜻하는 것이다:

🔴 **이름 블록 셋은 «항목 목록»이 아니다.** 이름을 안 붙인 잎도 **똑같이 비교되고** 원시 경로로 화면에 나온다 — 이름 선언을 지워서 사라지는 것은 **한국어뿐**이고 구간·항목·값은 하나도 안 준다. 「화면에서 빼려고」 거기서 지우는 것은 **아무 효과가 없다.**
🔴 **새 여정 술어를 붙이는 것은 `segments` 블록의 항목 하나**다 — payload 안 어디에 step 이름과 계열이 있는지를 점 경로로 적으면 되고 파이썬은 0줄이다. **거기에 선언이 없는 술어는 여정 축에 안 나타난다.**
⚠️ **그래서 `segments`만은 「지워도 이름만 없어지는」 블록이 아니다** — 그 블록이(또는 라이브·`.sample` 둘 다) 없으면 응답은 500이 아니라 200이되 `state: "absent"` · `reason: "no_journey_predicate_declared"` · **`segments: []`**로 «그렇게 말한다».
✅ **[2026-08-15 실측] 종전 이 자리의 「코드와 `.sample`의 산문이 거짓이다」는 낡았다** — `ledger_journey.JourneyConfig`의 docstring이 스스로 그 옛 문장을 지목해 정정했고(「AN EARLIER VERSION OF THIS DOCSTRING GOT IT WRONG」), 지금은 코드도 `.sample`도 **두 반쪽이 다르게 실패한다**고 적는다.

#### 4.6-quinquies R&D Trend와 Composite CHIP 읽는 법

- `/api/ledger/trends`의 차트와 표는 `identity.mark_key`가 같으면 같은 웨이퍼다.
  종류·subtype·차트 수는 배열 길이로 읽고, `max_points`를 전체 개수로 읽지 않는다.
  표의 다음 페이지는 `table.next_cursor`가 있을 때만 요청한다.
- `found_rate.state=absent`는 0%가 아니다. 관측 원자 투영에 clean scan 분모가 없다는
  뜻이다. `event_count`·`found_chip_count`만 현재 수치다.
- `/api/ledger/composition`은 `components[]`를 먼저 읽는다. `summary.dt_collection_ids`는
  참여한 DT 전부의 합집합이고 대표값이 아니다. component의 `transfer_events[]`는
  sequence 순서, component들 사이 관계는 `graph` DAG다. 공정 비교는
  `upstream_process.events[]`의 step/recipe occurrence만 읽고, Core lot 분기는
  `core.branch`와 `core.lineage.events[]`를 읽는다. 이 값들은 근거 원자를 보존할 뿐
  원인을 판정하지 않는다. 최종 wafer 연결은 `final_subject_resolution`의 state와 후보를
  함께 읽으며 `absent`를 추정값으로 채우지 않는다.

**Selection 비교에서 Process와 Measurement를 읽는 법**

- `comparison.facets.process[]`는 `processed_with`의 STEP+RCP occurrence만 비교한다.
  signature에 `equipment`·`step_family`·actual/setpoint·parameter/value가 보이면 계약 위반이다.
- `comparison.facets.measurement[]`의 원장 술어는 `measured`다. `measured_as`는 클라이언트의
  category 이름일 뿐 적재할 술어가 아니다.
- 공통 payload는 `metric/unit/method/state`; `recorded`만 `value/run_uid`가 필수다.
  `missing/not_performed/unknown`에는 `value`를 `null`로도 쓰지 않는다.
- 그룹은 `state_counts`와 원값 `values[]`를 함께 읽는다. `value`는 원값이 하나일 때만 있고,
  서버는 평균이나 0 sentinel을 만들지 않는다. `wafer_mark_keys`는 역마킹 대상,
  `evidence_ids`는 실제 원자 근거다.
- 선택 범위의 계측 원자가 0개인 경우에만 `state=absent`와
  `reason=measured_evidence_absent`가 나온다. 이것은 `missing`이나 `not_performed`가 아니다.
- 개발 SYN 데이터: `conda run -n assy_manager python
  server/scripts/seed_syn_composite_chip.py`는 dry-run, `--apply`는 추가 전용 적재다.
  재실행은 unique atom index에서 전량 dedupe된다.

### 4.7 🔴 합성·픽스처 적재를 걷어내는 법 — **목록이 아니라 술어** (2026-08-14)

원장에 **append-only 규율이 있다는 것과, 실험용 적재를 되돌릴 수 없다는 것은 다른 말이다.**
합성 적재는 정정(`supersedes`)의 대상이 아니라 **애초에 있어서는 안 되는 행**이므로 `DELETE`이고,
그래서 **처음 쓸 때부터 「무엇이 내 것인가」가 한 문장으로 대답 가능해야** 한다.

`seed_syn_process_ledger.py`(2026-08-14 · 가상 공정·레시피 소스)의 경계는 넷이고 **전부 술어**다:

| 무엇 | 술어 |
|---|---|
| 원장 원자 | `ledger_events WHERE source_translator_ver LIKE 'syn_process_ledger/%'` |
| 커서 행 | `ledger_translator_cursor WHERE source = 'syn_process_ledger'` |
| RDB 관측 | `inspection_run WHERE method = 'scat'` · `delam_obs` **전량** |
| 셀 레이어 | `cell_sources` · `cell_overwrites`의 `updated_by = 'seed_syn_process_ledger'` |

- 🔴 **원장만 지우면 절반만 지워진다.** 이 생성기는 원장 원자 **와** RDB 행(관측 테이블 둘)을 **같이** 만들었고,
  RDB 쪽은 인제션 경로를 지나므로 **셀 레이어 행까지** 남긴다. 세 층을 다 적어 두지 않으면 다음 사람이 원장만 비우고
  「깨끗해졌다」고 보고한다.
- ⚠️ **`source_who`로 스코프하지 마라** — 생성기가 그것을 **일부러 여러 개** 쓴다(§3-bis).
- ⚠️ **파티션은 지워지지 않는다.** 이 적재로 `ledger_events_2026_08`이 생겼고, 행을 다 지워도 **빈 파티션은 남는다**(정상이다).

**관측 번역(`void_obs`·`delam_obs`, 2026-08-14 3차)의 경계는 «둘»이다 — 층이 적은 이유는 번역이 «읽기만» 했기 때문이다:**

```sql
DELETE FROM ledger_events            WHERE source_who IN ('void_obs','delam_obs');
DELETE FROM ledger_translator_cursor WHERE source     IN ('void_obs','delam_obs');
```

- 🔴 **소스 테이블과 `inspection_run`은 손대지 않는다.** 번역기는 그것을 읽었을 뿐이라 지울 것이 없다 —
  🔴 **그 테이블들 «자체»를 걷어내는 것은 위의 생성기 술어이지 이것이 아니다. 두 작업을 섞으면 남의 데이터를 지운다.**
- **같은 행을 다르게 짚는 철자 둘 더** — `source_translator_ver LIKE 'void_obs/%'` · `LIKE 'delam_obs/%'`
  (현행 값 `void_obs/1/rules:fadf97f0` · `delam_obs/1/rules:a4212d3f`), 그리고 🔴 **`object_payload->>'synthetic' = 'true'`** —
  이것은 **다른 질문**이다(「합성 표식이 붙은 원자 전부」). 원자가 스스로 답하므로 소스 이름을 기억할 필요가 없다.
- ⚠️ **여기서는 `source_who`로 스코프하는 것이 «맞다»** — 관측 번역기는 소스당 이름 하나만 쓴다.
  🔴 **바로 위 생성기와 규칙이 반대이므로 옮겨 적지 말 것.**
- ⚠️ **파티션 `ledger_events_2026_09`~`2026_11`이 이 번역으로 생겼다** — 행을 지워도 남는다. 위와 같은 이유로 정상이고, 필요하면 따로 DROP한다.

---

## 5. 원장이 **일부러 안 하는 것**

**① UPDATE 경로가 없다.** 정정도 철회도 **새 원자**다(`supersedes`). 그래서 「누가 언제 무엇을 바꿨나」가
감사 로그가 아니라 **데이터 자체**이고, 낡음이 **결정 가능**해진다. 정정 절차는 §4.5.
근거: [설계 §3 · §14 「박제」](../architecture/CANONICAL_LEDGER_DESIGN.md).

**② status·processed 플래그 컬럼이 없다.** 🔴 **가변 필드 0.** 소비자는 **자기 커서**를 든다
(`ledger_translator_cursor`가 정확히 그것이다). 원장에 `processed` 컬럼을 다는 순간 소비자가 둘이 되면
그 컬럼이 누구의 것인지 답이 없어지고, 그것이 이 프로젝트가 「박제」라고 부르는 뿌리다.
같은 이유로 **투영 상태어**(`resolved`·`contested`·`candidate`·`unresolvable`·`pinned`)는
`vocabulary.PROJECTION_ONLY_WORDS`가 **이름으로 거절**한다 — 캐시가 자기 상태를 말하는 낱말이지 원장의 낱말이 아니다.
근거: [설계 §3 「일부러 뺀 것」 · §4.2](../architecture/CANONICAL_LEDGER_DESIGN.md).

**③ 텔레메트리는 자기 저장소에 남는다.** 원장은 **주장의 기록**이지 측정치 저장소가 아니다.
트레이스·파형·원시 계측은 제 저장소에 있고, 원장에는 그로부터 **파생된 주장**만 `raw_ref`를 달고 들어온다.
근거: [설계 §5 규칙 5](../architecture/CANONICAL_LEDGER_DESIGN.md).

**④ 배치/트랜잭션 신원은 «비의미» 표지다.** `molecule_ref`는 메모리에만 있고 **컬럼이 아니다** —
게이트가 전부 아니면 전무를 결정하는 데만 쓰고 버린다. 🔴 **해석기가 그것을 읽으면 계약 위반**이고,
이 구현에서는 **새어 나갈 곳이 아예 없다.** 근거: [설계 §3 「일부러 뺀 것」 · §14 「표식이 열쇠로」](../architecture/CANONICAL_LEDGER_DESIGN.md).

**⑤ 보존(retention) 정책은 아직 «판정 대기»다.** [설계 §12-4](../architecture/CANONICAL_LEDGER_DESIGN.md) —
운영 증가율 숫자가 필요하다. ⚠️ **파티션 키가 `occurred_at`(세상 시각)이지 기록 시각이 아니라는 점을 놓고 결정할 것.**
늦게 도착한 오래된 주장은 **오래된 파티션에 들어간다** — 「N개월 지난 파티션을 떼어낸다」를 순진하게 걸면
**어제 도착한 원자를 떼어낼 수 있다.**

---

## 관련 문서

- 🔴 **무엇을 선언하나 · 어느 순서로** — [guide/ONTOLOGY_LEDGER_SETUP.md](./ONTOLOGY_LEDGER_SETUP.md) **정본**(2026-08-15 통폐합)
- **왜** — [architecture/CANONICAL_LEDGER_DESIGN.md](../architecture/CANONICAL_LEDGER_DESIGN.md) (설계 문서. 현행 서술 아님)
- **정확히 무엇** — [spec/LEDGER_TECHNICAL_SPEC.md](../spec/LEDGER_TECHNICAL_SPEC.md) (스키마·인덱스·계약)
- **판정** — [process/LEDGER_RULINGS.md](../process/LEDGER_RULINGS.md) 🔴 정본
- **착수 지시** — [process/LEDGER_SLICE_1_BRIEF.md](../process/LEDGER_SLICE_1_BRIEF.md)
- **운영에서 «실제로 돌린» 기록** — [process/OPERATOR_RUNBOOK.md](../process/OPERATOR_RUNBOOK.md) §6 · §8
- **저장·시각 선언** — [architecture/data_model.md §1.1-ter](../architecture/data_model.md)
- **라우트** — [architecture/backend.md §2](../architecture/backend.md) · **화면** — [architecture/frontend.md §6.1](../architecture/frontend.md)
- **재사용 관점** — [architecture/PRIMITIVES.md](../architecture/PRIMITIVES.md) §1 · §3 · §6 · §7
- **회귀 점검** — [qa/FEATURE_CHECKLIST.md §1.13](../qa/FEATURE_CHECKLIST.md)
- 형제 가이드 — [INGESTION_GUIDE](./INGESTION_GUIDE.md) · [chain_ingestion_guide](./chain_ingestion_guide.md) · [BACKFILL_GUIDE](./BACKFILL_GUIDE.md)(**다른 백필이다** — 저쪽은 레이어링 규칙의 소급 적용)
