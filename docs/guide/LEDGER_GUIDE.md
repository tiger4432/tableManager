# 📒 정준 원장 (Canonical Ledger) — 소스 붙이는 법 · 백필 돌리는 법

> **Status:** 🟢 Living | **Last-verified:** 2026-08-14 | **Owner:** Server / Ledger | **Source-of-truth:** `server/ledger/` · `server/ledger_trace.py` · `server/ledger_structure.py`
>
> **이 문서가 소유하는 것: HOW.** 새 소스에 번역기를 붙이는 절차와, 운영자가 백필을 돌리고 숫자를 읽는 절차.
> **WHY는 여기 없다** — 왜 원자가 7필드인지, 왜 어휘가 닫혀 있는지, 왜 해결 서열이 4계급인지는
> [architecture/CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md)이 소유한다. **다시 쓰지 않는다.**
> **EXACTLY-WHAT**(컬럼·인덱스·계약)은 [spec/LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md).
> **판정**은 [process/LEDGER_RULINGS](../process/LEDGER_RULINGS.md) — 🔴 거기 없는 판정은 내려진 적이 없는 것으로 친다.
> **운영에서 무엇을 어느 순서로 돌리는가**는 [process/OPERATOR_RUNBOOK §6·§8](../process/OPERATOR_RUNBOOK.md)이 소유한다 — 이 문서는 **순서를 다시 적지 않고** 명령의 뜻만 적는다.

> ⚠️ **이 문서의 모든 수치는 이 개발 박스(`assy_manager` / `assy_qa`) 실측이고 운영의 증거가 아니다.**
> 측정 시점은 2026-08-13이며, 인용할 때 그 귀속을 떼지 말 것.
>
> **이번 라운드 (2026-08-14 2차 · 구조 뷰 — 읽기 라우트 하나)** — 🔴 **읽는 쪽 모듈이 «둘»이 됐다**(§1.2): `ledger_structure.py`가
> `GET /api/ledger/structure`를 답한다. **유형 수준**이고(`/trace`가 인스턴스 수준이므로 그 보완이다), 🔴 **응답 어디에도 손으로 적은
> 노드·엣지 목록이 없다** — 선언된 절반은 어휘에서, 관측된 절반은 원장 한 번의 `GROUP BY`에서 **생성**된다.
> **번역기를 붙이는 사람이 알아야 할 것 하나**: 술어를 어휘에 더하면 이 라우트를 **한 줄도 안 고치고** 화면에 나타나고,
> 어휘에 없는 모양을 발화하면 **`undeclared`로 화면에 뜬다**(조용히 버려지지 않는다 — §4.6). 어휘에 `label_ko`가 붙었고(§1.1)
> **집행 지점은 단위 테스트 하나**다. 계약은 [spec §3.7-quater · §4.7](../spec/LEDGER_TECHNICAL_SPEC.md), 라우트는 [backend §2](../architecture/backend.md).
>
> **직전 라운드 (2026-08-14 · 어휘 확장 + 생성기 소스)** — 🔴 **어휘가 일곱에서 «아홉»이 됐다**(§1.1 · §3 ①).
> `processed_with`(공정 조건 — **설계가 예약해 둔 낱말이 열린 것**)와 `has_param`(레시피 설정값), 그리고 새 개체 타입 **`Recipe`**(🔴 `rev`가 **키 재료**).
> 🔴 **일곱을 못박던 테스트가 «이름 그대로» 아홉을 못박는다** — 완화가 아니라 판정을 적은 것이고, **열 번째는 지금도 빨갛다.**
> 그리고 **§3-bis 신설**: **생성기 소스**(테이블 번역기가 아닌 것)는 파생·subject 타입을 **`ledger_config.json`이 아니라 자기 안에** 선언한다 —
> 없는 컬럼 일곱을 지어내 운영자 config에 넣는 것이 대안이었다. 계약 절반은 [spec §3.7·§4.1-bis](../spec/LEDGER_TECHNICAL_SPEC.md).
>
> **직전 라운드 (2026-08-14 · `92547c3` · R-2026-08-13-H-bis)** — 🔴 **번역기는 더 이상 «자기 스코프를 열지 않는다»**(§1.1 · §2 · §3 ③).
> `backfill.run`의 분자 루프가 `gate.building_molecule`을 들고, 번역기를 **손으로 모는 호출부(테스트 포함)는 자기가 열어야 한다** — 안 열면 `RuntimeError`.
> 🔴 **다만 오늘 동작은 하나도 안 바뀐다**: 번역기 클래스는 하나이고 `backfill.run`의 호출자는 자기 CLI `main()`뿐이라
> **가치는 미래의 두 번째 번역기 작성자가 맞을 `RuntimeError`**다(「착지 ≠ 배선」). 함께: `screen_molecule`의 **거절만** 예외가 됐고
> **「할 말 없음」의 `[]`는 그대로 반환**이며, `store.write_batch(reasons=…)`는 **필수 키워드 인자**가 됐다.
>
> **직전 라운드 (2026-08-13 5차 · `4f46c25..f313279`)** — 🔴 **마이그레이션이 둘이 됐다**(§4.1) ·
> `subject_types` 복수 allow-list가 **문다**(§3 ② · `eb1ae8b`) · 거절이 **어느 파편에서든** 분자를 세운다(§2.2 · `f313279`) ·
> 커서에 **`refusal_reasons`**와 `/coverage`의 **부호 계약**(§4.4 · §4.6 · `0198e7e`).
> ⚠️ **§4.4·§4.6의 라이브 판독은 그 커밋들 «이전»에 뜬 것**이고 그 자리에 귀속을 달아 두었다 — 재백필하지 않았기 때문이다.

---

## 0. 두 독자

| 당신이 | 읽을 곳 |
|---|---|
| **새 소스를 원장에 붙이려는 개발자** | §1 모듈 지도 → §2 쓰기 경로 → **§3 새 소스 붙이는 법**(이 문서가 존재하는 이유) |
| **백필을 돌리고 숫자를 읽어야 하는 운영자** | §4 운영자 절 → §2.4(한 트랜잭션이 덮는 것) → [OPERATOR_RUNBOOK](../process/OPERATOR_RUNBOOK.md) |

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
| `vocabulary.py` | 닫힌 어휘 + 항목별 **기계 검증 가능한 서명** | **지금 아홉이고 그 수는 여전히 통제 장치다**(2026-08-14 — v0 일곱 + `processed_with`·`has_param`, 둘 다 `since: 2`. `test_ledger_l1_unit.py`가 **이름을 안 바꾼 채** 집합을 못박고, **원래 일곱이 여전히 `since: 1`인 것까지** 단언한다 — 열 번째는 지금도 빨갛다). 개체 타입에 **`Recipe`**가 들어왔고 🔴 **`rev`가 subject 키 재료**다(개정은 편집이 아니라 **새 등록**). `register`만 `object_kind IS NULL`. 🔴 **`value` 목적어는 이제 «검사된다»** — 술어가 `required` 필드를 선언하면 payload가 그것을 **존재로** 만족해야 한다(⚠️ **진리값이 아니다** — `0`·`False`는 정당한 설정값이고 빈 문자열만 거절). 계약은 [spec §3.7](../spec/LEDGER_TECHNICAL_SPEC.md). **투영 상태어**(`resolved`·`contested`·`candidate`·`unresolvable`·`pinned`)는 이름으로 거절된다 — 원장에 절대 안 들어간다. 🔴 **[2026-08-14 2차] 모든 항목에 `label_ko`가 붙었다 — 장식이 아니라 «선언의 일부»다**: 구조 뷰(§4.6)가 어휘를 그림으로 그리면서 라벨을 여기서 읽는다. 렌더러 옆에 라벨 지도를 두면 **어휘의 두 번째 목록**이 되고, 그때 낱말을 더한 사람은 다른 테스트가 전부 초록인 채 화면에서만 맨 식별자를 본다. ⚠️ **읽는 쪽은 라벨이 없으면 원시 이름으로 «폴백»하고 raise하지 않는다** — 그래서 빨개지는 것은 `test_ledger_l1_unit.py::test_every_declared_word_carries_a_label` **하나뿐**이다(라벨 누락은 화면을 영어로 강등시켜야지 비워서는 안 된다) |
| `uuid7.py` | 단조 UUIDv7 — 워터마크이자 기록시각 | **구성상 단조**. 밀리초당 4,096(12비트 카운터), 넘치면 **미래를 당겨 쓰고**, 벽시계가 뒤로 가면 **직전 밀리초를 유지**한다. `assert_monotonic`은 **센 개수를 돌려준다**(빈 순회가 성공을 보고하지 못하게) |
| `gate.py` | 문 앞에서 거절하고 **센다**. 단위는 행이 아니라 **분자** | 설계 §3의 **원자성 검사 넷** + **다섯째 질문**(`subject_types` — R-2026-08-13-D)이 산문에서 코드가 되는 자리. 🔴 **전부 아니면 전무이고, 그 규칙이 «어느 파편에든» 걸린다**(R-2026-08-13-H): `gate.building_molecule(source)` 스코프 안에서는 **사유를 가리지 않고 모든** `gate.refuse`가 세고 나서 `gate.MoleculeRefused`를 **raise**한다. 내년에 추가되는 헬퍼는 이 규칙이 있는 줄 몰라도 자기 분자를 세운다. 🔴 **`screen_molecule`의 거절도 그 문법이다**(2026-08-14 `92547c3` · R-H-bis 1) — 다만 **거절 팔만** 그렇고, **정당하게 할 말이 없던 분자(원자 0개)는 여전히 `[]`를 «반환»**한다. 거절과 무발화를 같은 문법으로 만들면 거절 카운터가 두 가지 뜻을 갖는다. 🔴 **스코프를 «여는» 것은 이 모듈도 번역기도 아니고 드라이버다**(아래 `backfill.py`). 거절 사유는 **닫힌 집합 열둘**이고 호출부가 새 사유를 지어내면 `ValueError` |
| `config.py` | `ledger_config.json`을 **로드 시점에** 검증 | **선언 없는 것은 기본값이 아니라 거절이다** — 시각 컬럼·시간대가 없으면 소스 전체를 거절한다. `translator_version()`이 **선언 전체를 해시**해 원자마다 어떤 규칙이 만들었는지 남긴다. **런당 1회 읽는다**(행마다 아님) |
| `lot_event_translator.py` | 첫 번째 소스, 그리고 다음 번역기가 베낄 **모양** | **한 이벤트 = 두 행 = 한 분자**. 짝은 `(event_type, event_time, parent, child)`로 맞춘다(소스에 이벤트 id가 없다). 🔴 **한 행이 양쪽을 다 채우면 고립시켜 거절**한다 — 「부모 먼저, 없으면 자식」류 순서는 그 행의 웨이퍼를 소스가 주장한 적 없는 계보에 조용히 붙인다. 🔴 **이 파일은 스코프를 «열지 않고 요구»한다**(2026-08-14 `92547c3` · R-H-bis 3). `translate`는 `gate.building_molecule` **안에서 불려야** 하고, 안 열고 부르면 `_build`의 단언이 **`RuntimeError`**를 내며 그 메시지가 **누가 여는지(`backfill.run`)와 두 줄짜리 철자**를 댄다. 여는 자리가 여기였을 때는 그 규율이 **두 번째 번역기 작성자가 이 파일을 읽고 «알아채야»** 물려받는 구전이었다. 🔴 **번역기 쪽 일방향 문은 여전히 `translate`의 `except MoleculeRefused` 하나**이고 `_build` 안에는 그것을 삼킬 표현식이 없다 — 다만 **게이트 심사의 거절을 받는 두 번째 문이 드라이버에 있다**([spec §3.3-bis 표](../spec/LEDGER_TECHNICAL_SPEC.md)) |
| `store.py` | 원자 쓰기 + 커서 전진, **한 트랜잭션** | 커밋 하나 안에 원자와 커서가 같이 들어간다(§2.4). 연결은 **반드시** `engine.raw_connection()` — `psycopg2.connect`는 `db_safety` 가드를 우회한다. `parse_occurred_at`이 **선언 시간대는 naive 텍스트에만** 먹이고 오프셋을 달고 온 문자열은 그대로 존중한다. 🔴 **`write_batch(…, reasons=…)`는 «필수 키워드» 인자다**(2026-08-14 `92547c3` · R-H-bis 2) — 기본값도 없고 명시적 `None`도 `TypeError`이며, 깨끗한 런의 정당한 값은 **명시적 `{}`** 하나다(§4.4의 부호 계약이 여기 걸려 있다) |
| `backfill.py` | 커서 루프 — **분자를 반으로 자르지 않는다** · 🔴 **분자 스코프를 «여는» 자리** | 커서는 행 오프셋이 아니라 **`event_time`**이고, 배치는 언제나 **온전한 `event_time` 그룹의 정수 개**다. 페이지가 꽉 찼으면 **꼬리 그룹을 버린다**(잘렸는지 안에서는 알 수 없다). 🔴 **분자 루프가 `with gate.building_molecule(source)`를 들고 `translator.translate`와 `gate.screen_molecule`을 «같은» 스코프 안에 감싼다**(2026-08-14 `92547c3` · R-H-bis 3) — 그래서 이 드라이버가 모는 **모든** 번역기는 작성자가 규칙을 몰라도 스코프 안에서 태어난다. ⚠️ **오늘 이 드라이버를 부르는 것은 자기 파일의 CLI `main()`뿐**이다(데몬·라우트·워커 0) |
| `observability.py` | 거절 요약 + **뒤처짐(lag)** 보고 — 첫날부터 | 티어 2단. **티어 1은 질의 0회**(세계시각 뒤처짐 · 커서 나이) — 이것만으로 「커서가 안 움직인다」가 보인다. **티어 2는 스로틀 걸린 1질의**(소스 head·뒤에 남은 행 수). 🔴 `probe_allowed`를 같이 실어 **「안 뒤처짐」과 「안 물어봄」을 구별**한다 |
| `schema.py` | 물리 DDL **한 철자**. 마이그레이션도 이것을 부른다 | **첫날부터 월 단위 RANGE 파티션**(`ALTER TABLE ... PARTITION BY`가 없으므로 나중은 전면 재작성). 🔴 **모든 인덱스는 이름 붙은 소비자를 갖는다** — 소비자 없이 지어졌다 제거된 셋의 **가격이 주석에 남아 있다** |

### 1.2 읽기 쪽 — 추적 화면(인스턴스)과 구조 화면(유형)

🔴 **읽는 쪽은 «두 수준»이고 서로를 복제하지 않는다.** `/trace`는 **인스턴스**(이 랏의 혈통)이고,
`/structure`는 **유형**(어떤 개체가 어떤 관계로 이어지는가)이다 — 구조 응답에는 랏·웨이퍼·보이드가 **한 건도 없다.**

| 파일 | 무엇 | 왜 이 경계인가 |
|---|---|---|
| `server/ledger_structure.py` (2026-08-14) | `GET /api/ledger/structure` — **유형 수준 온톨로지 그림 + 선언 지도**. 노드=개체 타입, 엣지=(subject 타입, 술어, 목적어) 삼중항 | 🔴 **손으로 적은 노드·엣지 목록이 이 파일에 «없다»**(제품 소유자 실패 조건: 「하드코딩된 목록이 응답 어디에든 보이면 실패」). **선언된 절반**은 `vocabulary.ENTITY_TYPES` × `PREDICATES`에서, **관측된 절반**은 원장 한 번의 `GROUP BY`에서 생성하고 **둘을 병합**한다 — 병합이 설계 전부다. 선언에만 있는 모양(`declared_only`)과 데이터에만 있는 모양(`undeclared`)은 **손으로 그린 그림이 영원히 못 내는 답 둘**이다. 🔴 **어휘는 «지연» import한다**(호출 «안»에서) — §0의 「`server/`에서 `server/ledger`를 import하는 부팅 경로가 없다」를 *거의* 참이 아니라 **글자 그대로** 참으로 두려고. 🔴 **등급 분포를 SQL이 «분류하지 않는다»** — 그룹 키만 만들고 `ledger_trace.claim_class`/`claim_basis`를 **그대로 부른다**(철자가 둘이면 갈라진다). 🔴 **등록 엣지는 이름이 아니라 «모양»(`object_kind IS NULL`)으로 식별**한다 — `predicate == "register"` 리터럴이 먼저 쓰였고 어휘를 갈아끼우는 테스트가 잡았다 |
| `server/ledger_trace.py` | **셋이 살고 둘은 서로를 몰라야 한다**: **해결기**(`claim_class`/`claim_rank_key`/`resolve` — 순수 파이썬, SQL·테이블명·커넥션 0) · **조회기**(`ClaimLookup` 계열 — 가져오기만 하고 등급을 모른다) · **보행**(`trace` — 조회기에 한 번 묻고 홉마다 해결기에 한 번 묻는다) | 스타일이 아니라 **구조 요구**다. 슬라이스 1은 **랏 단위**라 질의 시점 해결로 가지만 **슬롯 단위 혈통은 질의 시점에서 죽는다**(인라인 452 ms 대 물질화 0.58 ms — 합성·이 박스). 조회기가 **교체 가능한 객체**라 물질화된 클로저 테이블로 옮기는 것이 **생성자 인자 하나**이고 해결기는 한 줄도 안 바뀐다. `InMemoryClaimLookup`은 그 교체 가능성을 **주장이 아니라 검사된 성질**로 만든다 |
| `server/ledger_trace_router.py` | `APIRouter(prefix="/api/ledger")` **하나에 라우트 다섯** — `/trace` · `/coverage` · `/siblings` · `/kinds` · **`/structure`**(2026-08-14). 전부 **읽기 전용** | 🔴 **SPA catch-all «위»에 등록해야 한다.** FastAPI는 등록 순서로 매칭하므로 catch-all 뒤에 등록된 라우트는 **200으로 `index.html`을 받는다** — 감시자가 죽은 엔드포인트를 살아 있다고 부르게 되는 실패다(`/health`가 실제로 그랬다). 현재 `server/main.py`에서 catch-all 훨씬 위에 등록돼 있다. 🔴 **빈 `hops`는 가능한 답이 아니다** — 어느 홉에서 왜 끊겼는지가 이 화면의 존재 이유다 |
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

## 3. 🔴 새 소스 붙이는 법

> 이 절이 이 문서가 존재하는 이유다. `lot_event_translator.py`가 **베낄 모양**이다.

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

### ② `ledger_config.json`에 선언 한 장

`server/config/ledger_config.json`(gitignore. 배포본은 `.json.sample`이고 실 파일이 없으면 **샘플로 폴백**한다).
`sources.<이름>` 아래 한 장:

| 키 | 필수 | 뜻 · 함정 |
|---|---|---|
| `occurred_at_column` | ✅ | **세상의 시각을 담은 소스 컬럼 이름.** 없으면 소스 전체 거절 — 기본값 없음 |
| `occurred_at_timezone` | ✅ | 소스의 **naive 텍스트**가 무슨 시각인지. 🔴 **`Asia/Seoul`(제품 소유자 판정)**. 오프셋을 달고 온 문자열에는 **다시 먹이지 않는다** |
| `occurred_at_format` | ⬜ | 기본 `%Y-%m-%dT%H:%M:%S`. 🔴 **구분자만 넓힌다** — 선언된 형식에서 시(hour) 직전 구분자 하나를 바꾼 사본과, 각각에 `%z`를 단 사본까지 **총 4후보**. 문법을 넓히는 것이 아니라 **전송 형태**를 넓히는 것이고, 어떤 문자열도 두 가지로 읽히지 않는다 |
| **`subject_types`** | ✅ | 🔴 **복수 allow-list이고 «문다».** 이 소스의 번역기가 **말해도 되는 개체 타입들**(예: `["Lot", "Wafer"]`) — 밖에 있는 원자는 `undeclared_subject_type`으로 **이름 대고 거절되고 세어진다.** 멤버는 전부 `vocabulary.ENTITY_TYPES`의 선언된 타입이어야 한다(여기 타입을 더하는 것은 config 결정이 아니라 **어휘 결정**이다). ⚠️ **단수 `subject_type`은 은퇴했고 «에러»다** — 아래 「함정」 |
| `register_entity_types` | ⬜ | `register` 원자를 낼 **발급형** 타입들. `Die`는 **구성형**이라 일부러 없다(다이당 원자 1개가 된다) |
| `list_separator` | ⬜ | 기본 `":"`. 위치 대응 리스트의 구분자 |
| `columns.*` | ✅ | **일곱 개 전부 필수**: `row_identity` · `lot` · `event_type` · `parent_lot` · `child_lot` · `slots` · `wafers`. 논리 이름 → 물리 컬럼. 번역기는 물리 이름을 **절대 안 본다** |
| `vocabulary.<event_type>` | ✅ | 이 소스가 알아듣는 이벤트 타입들. **여기 없는 event_type은 «건너뛰는» 것이 아니라 거절되고 세어진다** |
| `vocabulary.*.lineage` | ⬜ | `parent_child` \| `none` |
| `vocabulary.*.slot_pairing` | ⬜ | `shared_wafer`(추론 0 — 같은 웨이퍼가 양쪽에 발화됐을 때만) \| `slot_preserving`(**운영자의 관례 선언**) \| `none`. 오타는 **로드 시점 에러**다(조용히 `none`으로 떨어지면 슬롯 체인 없는 원장이 항의 없이 생긴다) |
| `vocabulary.*.emit_has_wafer` / `emit_register` | ⬜ | 기본 `true` |
| `batch.molecules_per_transaction` | ⬜ | 기본 200. **온전한 소스 이벤트 개수**다 |
| `lag.probe_interval_seconds` | ⬜ | 기본 60. 티어 2 프로브가 소스에 진짜 `COUNT`를 돌려도 되는 최소 간격 |

**함정 셋 (실측 2026-08-13):**

- ✅ 🔴 **[닫혔다 — `eb1ae8b` · R-2026-08-13-D] 「검사되지만 어느 원자에도 도달하지 않던 필드」가 이제 «문다».**
  옛 상태는 이랬다: `subject_type`이 단수였고, 번역기 안에서 **한 번 대입되고 아무 데서도 읽히지 않았으며**,
  호출부가 `"Lot"`/`"Wafer"` 리터럴을 넘겼다 — 즉 `config.validate()`가 **아무 결과도 없는 값**을 검사했다.
  🔴 **그리고 단수가 애초에 틀린 모양이었다**: `lot_event` **한 소스**가 개체 타입 **둘**에 대한 원자를 만든다
  (실측 `Lot` 689 · `Wafer` 220 — 웨이퍼 register 경로는 이미 있고 잘 돈다).
  지금은 **복수 `subject_types`**이고 게이트가 밖에 있는 원자를 `undeclared_subject_type`으로 거절한다.
  **리터럴은 그대로 있다** — 코드가 각 원자의 **사실**을 소유하고 선언이 그 사실의 **허용 범위**를 소유한다.
  - 🔴 **옛 키를 쓰면 «에러»이고 메시지가 새 이름과 예시를 댄다.** 무시하지도, 받아들여 다른 일을 하지도 않는다 —
    조용히 아무 뜻도 없는 config가 이 판정이 끝내려는 결함 그 자체다.
  - 🔴 **`screen_molecule`의 인자는 필수이고 기본값이 없다.** 기본값이 있으면 호출부가 **아무 말도 안 함으로써** 옛 동작을
    유지할 수 있다. **빈 리스트는 전부 거절**하고 그것이 옳은 방향이다.
  - 🔴 **선언을 바꾸면 `translator_version` 해시가 움직인다** — 이 라운드에 `d8d1c9e0` → `34311f15`.
    `source_translator_ver`가 dedupe 열쇠 일곱 중 하나이므로, **`--reset-cursor` 재실행은 dedupe가 아니라
    «옛 원자 옆에 새 원자»를 쓴다**(878행 → 878 «신규»행). 그것이 선언 변경의 설계된 뜻이고,
    「다시 돌려서 안 변한 걸 확인하자」가 기대하게 만드는 것과 **다르다.** 상세는 §4.3.
  - **상설 규칙**: 🔴 **선언 필드는 «집행 지점»을 갖거나, 존재하지 않는다.**
- ⚠️ **`columns`의 일곱은 lineage가 없는 소스도 전부 선언해야 한다.** 로드 검증이 무조건 요구한다 —
  `parent_lot`/`child_lot`/`slots`/`wafers`를 안 쓰는 소스도 컬럼 이름을 적어야 통과한다.
- ⚠️ **`columns.equipment`는 선언돼 있고 `server/ledger/` 안에서 아무도 읽지 않는다.** 베낄 때 딸려 오지 않게 할 것.

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
| **어휘 집합** | `PREDICATES`가 정확히 **아홉**(2026-08-14 — 그전엔 일곱) · **원래 일곱이 여전히 `since: 1`** · `REFUSAL_REASONS`가 닫혀 있음 |
| 🔴 **`value` 목적어의 `required`는 «양팔»로** | (2026-08-14) 온전한 payload는 **위반 0**, 필드 하나 뺀 payload는 **그 필드 이름을 대며 거절**. 🔴 **`0`과 `False`를 «따로»** 태워라 — 진리값 검사로 잘못 쓰면 그 둘만 거절되고 나머지는 전부 통과해서, 온전한 payload 하나로는 **두 철자가 구별되지 않는다** |

**실행:**
```bash
conda run -n assy_manager python -m pytest server/tests/test_ledger_l1_unit.py server/tests/test_ledger_l1_pg.py server/tests/test_ledger_trace.py server/tests/test_ledger_trace_contract.py server/tests/test_ledger_trace_pg.py
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

> 🔴 **운영에서 무엇을 어느 순서로 돌리는가는 [OPERATOR_RUNBOOK §6·§8](../process/OPERATOR_RUNBOOK.md)이 소유한다.**
> 이 절은 **명령이 무엇을 하는지·숫자를 어떻게 읽는지**만 적는다. 순서는 저쪽을 보라.

### 4.1 설치 — 마이그레이션

🔴 **마이그레이션은 «둘»이다** (2026-08-13 `0198e7e`부터). 순서는 [OPERATOR_RUNBOOK §6](../process/OPERATOR_RUNBOOK.md).

```bash
# ① 표 둘을 만든다
conda run -n assy_manager python server/migrations/add_ledger_events.py            # 만든다
conda run -n assy_manager python server/migrations/add_ledger_events.py --report   # 아무것도 안 바꾸고 상태만
conda run -n assy_manager python server/migrations/add_ledger_events.py --months 3 # 파티션 미리 3개월치

# ② 커서 행에 거절 «내역» 컬럼을 붙인다 (열둘 → 열셋)
conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py
conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py --report
conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py --reverse
```

②에 대해:

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

①에 대해:

- **추가 전용·멱등.** DROP 없음, 기존 것의 ALTER 없음, 기존 테이블의 행을 건드리는 문장 없음. **새 테이블 둘만.**
- **큰 기존 테이블에 컬럼을 붙이지 않으므로 잠금 위험이 없다.** 안 돌아도 아무것도 안 깨진다.
- **DDL은 이 파일에 없다** — `server/ledger/schema.py`가 유일한 철자이고 마이그레이션은 그것을 부른다.
  (테스트가 스크래치 스키마에 **같은** 테이블을 짓게 하려면 사본이 있으면 안 된다.)
- **파티션은 만들지 않는다.** 번역기가 **자기가 쓸 달을 쓰기 직전에** 만든다 — 존재할 달은 배포일이 아니라 **데이터**가 정한다.
  `--months`는 창을 미리 열어 두고 싶은 운영자를 위한 것.

### 4.2 백필

```bash
conda run -n assy_manager python -m ledger.backfill --source lot_event
```
(`server/`에서 실행. `-m`이므로 패키지 경로가 잡힌다.)

| 플래그 | 뜻 |
|---|---|
| `--source <이름>` | 기본 `lot_event`. `ledger_config.json`에 선언이 없으면 **`undeclared_source`로 거절하고 아무것도 안 읽는다** |
| `--reset-cursor` | 커서를 무시하고 **이미 끝난 일감을 다시 읽는다.** 유니크 인덱스(그물 ②)를 실제로 태우는 방법이고, 규칙을 바꾼 뒤 **재번역**하는 방법이다 |
| `--from <event_time>` | 커서 대신 이 시각 «다음»부터. 특정 창만 다시 돌릴 때 |
| `--fetch-rows N` | 소스 페이지 크기(기본 2000). **배치 크기가 아니다** — 트랜잭션 크기는 config의 `batch.molecules_per_transaction` |
| `--max-batches N` | N 배치 후 멈춘다. 첫 시험 주행용 |
| `--config <경로>` | 다른 선언 파일로 |

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
- 🔴 **커서는 세계 시각(`event_time`)이다.** 늦게 도착한 오래된 타임스탬프 행은 **커서 뒤에 앉고 이 백필은 못 본다.**
  일회성 백필에는 받아들일 만하고(이미 있는 것을 쓸어 담는 것이 목적) **라이브 구독에는 아니다** —
  그쪽은 아웃박스가 몰아야 한다. `--from`으로 어느 창이든 다시 돌릴 수 있고 재실행은 유니크 인덱스 덕에 공짜다.

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
- ⚠️ **결함 관측은 이 그래프에 «노드가 없다» — 원장에 안 들어 있기 때문이다.** `measured`·`observed` 같은 술어는 선언된 적이 없고,
  보이드·딜램은 `void_obs`·`delam_obs`에 살며 `finding_kinds` 등록부를 통해서만 도달한다. 그래서 응답의 모든 종류가 **`in_ledger: false`**이고
  `ledger_edge_ids`가 **빈 배열**이다 — 🔴 **그 빈 배열이 「연결 실패」가 아니라 「그런 연결은 없다」는 답**이다.
  🔴 **「한 렌더러 · 통합 어휘」를 전제로 화면을 설계하지 말 것** — 오늘 참이 아니다(2026-08-14 실측).
- ⚠️ **선언된 엣지 대부분이 `declared_only`인 것은 정상이다** — 이 박스 실측 **엣지 54 중 흐르는 것 9 · `declared_only` 45**.
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

**이 박스 실측 (2026-08-14, `assy_manager`, 84,747원자 · 두 파티션)**: census **182 ms** · 호출 전체 **285 ms** · 페이로드 **59 KB**.
⚠️ **이 수를 다른 문서의 「285 ms」와 섞지 말 것** — 버려진 SQL 사다리 철자의 비교값에도 같은 수가 있다([spec §5.7](../spec/LEDGER_TECHNICAL_SPEC.md)).

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

- **왜** — [architecture/CANONICAL_LEDGER_DESIGN.md](../architecture/CANONICAL_LEDGER_DESIGN.md) (설계 문서. 현행 서술 아님)
- **정확히 무엇** — [spec/LEDGER_TECHNICAL_SPEC.md](../spec/LEDGER_TECHNICAL_SPEC.md) (스키마·인덱스·계약)
- **판정** — [process/LEDGER_RULINGS.md](../process/LEDGER_RULINGS.md) 🔴 정본
- **착수 지시** — [process/LEDGER_SLICE_1_BRIEF.md](../process/LEDGER_SLICE_1_BRIEF.md)
- **운영 실행 순서** — [process/OPERATOR_RUNBOOK.md](../process/OPERATOR_RUNBOOK.md) §6 · §8
- **저장·시각 선언** — [architecture/data_model.md §1.1-ter](../architecture/data_model.md)
- **라우트** — [architecture/backend.md §2](../architecture/backend.md) · **화면** — [architecture/frontend.md §6.1](../architecture/frontend.md)
- **재사용 관점** — [architecture/PRIMITIVES.md](../architecture/PRIMITIVES.md) §1 · §3 · §6 · §7
- **회귀 점검** — [qa/FEATURE_CHECKLIST.md §1.13](../qa/FEATURE_CHECKLIST.md)
- 형제 가이드 — [INGESTION_GUIDE](./INGESTION_GUIDE.md) · [chain_ingestion_guide](./chain_ingestion_guide.md) · [BACKFILL_GUIDE](./BACKFILL_GUIDE.md)(**다른 백필이다** — 저쪽은 레이어링 규칙의 소급 적용)
