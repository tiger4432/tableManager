# 📒 정준 원장 (Canonical Ledger) — 소스 붙이는 법 · 백필 돌리는 법

> **Status:** 🟢 Living | **Last-verified:** 2026-08-13 | **Owner:** Server / Ledger | **Source-of-truth:** `server/ledger/` · `server/ledger_trace.py`
>
> **이 문서가 소유하는 것: HOW.** 새 소스에 번역기를 붙이는 절차와, 운영자가 백필을 돌리고 숫자를 읽는 절차.
> **WHY는 여기 없다** — 왜 원자가 7필드인지, 왜 어휘가 닫혀 있는지, 왜 해결 서열이 4계급인지는
> [architecture/CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md)이 소유한다. **다시 쓰지 않는다.**
> **EXACTLY-WHAT**(컬럼·인덱스·계약)은 [spec/LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md).
> **판정**은 [process/LEDGER_RULINGS](../process/LEDGER_RULINGS.md) — 🔴 거기 없는 판정은 내려진 적이 없는 것으로 친다.
> **운영에서 무엇을 어느 순서로 돌리는가**는 [process/OPERATOR_RUNBOOK §6·§8](../process/OPERATOR_RUNBOOK.md)이 소유한다 — 이 문서는 **순서를 다시 적지 않고** 명령의 뜻만 적는다.

> ⚠️ **이 문서의 모든 수치는 이 개발 박스(`assy_manager` / `assy_qa`) 실측이고 운영의 증거가 아니다.**
> 측정 시점은 2026-08-13이며, 인용할 때 그 귀속을 떼지 말 것.

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
| `vocabulary.py` | 닫힌 어휘 + 항목별 **기계 검증 가능한 서명** | **v0는 일곱이고 그 수는 통제 장치다**(`test_ledger_l1_unit.py`가 집합을 못박는다). `register`만 `object_kind IS NULL`. **투영 상태어**(`resolved`·`contested`·`candidate`·`unresolvable`·`pinned`)는 이름으로 거절된다 — 원장에 절대 안 들어간다 |
| `uuid7.py` | 단조 UUIDv7 — 워터마크이자 기록시각 | **구성상 단조**. 밀리초당 4,096(12비트 카운터), 넘치면 **미래를 당겨 쓰고**, 벽시계가 뒤로 가면 **직전 밀리초를 유지**한다. `assert_monotonic`은 **센 개수를 돌려준다**(빈 순회가 성공을 보고하지 못하게) |
| `gate.py` | 문 앞에서 거절하고 **센다**. 단위는 행이 아니라 **분자** | 설계 §3의 **원자성 검사 넷**이 산문에서 코드가 되는 자리. **전부 아니면 전무** — 원자 하나가 나쁘면 분자 전체가 거절된다. 거절 사유는 **닫힌 집합**이고 호출부가 새 사유를 지어내면 `ValueError` |
| `config.py` | `ledger_config.json`을 **로드 시점에** 검증 | **선언 없는 것은 기본값이 아니라 거절이다** — 시각 컬럼·시간대가 없으면 소스 전체를 거절한다. `translator_version()`이 **선언 전체를 해시**해 원자마다 어떤 규칙이 만들었는지 남긴다. **런당 1회 읽는다**(행마다 아님) |
| `lot_event_translator.py` | 첫 번째 소스, 그리고 다음 번역기가 베낄 **모양** | **한 이벤트 = 두 행 = 한 분자**. 짝은 `(event_type, event_time, parent, child)`로 맞춘다(소스에 이벤트 id가 없다). 🔴 **한 행이 양쪽을 다 채우면 고립시켜 거절**한다 — 「부모 먼저, 없으면 자식」류 순서는 그 행의 웨이퍼를 소스가 주장한 적 없는 계보에 조용히 붙인다 |
| `store.py` | 원자 쓰기 + 커서 전진, **한 트랜잭션** | 커밋 하나 안에 원자와 커서가 같이 들어간다(§2.4). 연결은 **반드시** `engine.raw_connection()` — `psycopg2.connect`는 `db_safety` 가드를 우회한다. `parse_occurred_at`이 **선언 시간대는 naive 텍스트에만** 먹이고 오프셋을 달고 온 문자열은 그대로 존중한다 |
| `backfill.py` | 커서 루프 — **분자를 반으로 자르지 않는다** | 커서는 행 오프셋이 아니라 **`event_time`**이고, 배치는 언제나 **온전한 `event_time` 그룹의 정수 개**다. 페이지가 꽉 찼으면 **꼬리 그룹을 버린다**(잘렸는지 안에서는 알 수 없다) |
| `observability.py` | 거절 요약 + **뒤처짐(lag)** 보고 — 첫날부터 | 티어 2단. **티어 1은 질의 0회**(세계시각 뒤처짐 · 커서 나이) — 이것만으로 「커서가 안 움직인다」가 보인다. **티어 2는 스로틀 걸린 1질의**(소스 head·뒤에 남은 행 수). 🔴 `probe_allowed`를 같이 실어 **「안 뒤처짐」과 「안 물어봄」을 구별**한다 |
| `schema.py` | 물리 DDL **한 철자**. 마이그레이션도 이것을 부른다 | **첫날부터 월 단위 RANGE 파티션**(`ALTER TABLE ... PARTITION BY`가 없으므로 나중은 전면 재작성). 🔴 **모든 인덱스는 이름 붙은 소비자를 갖는다** — 소비자 없이 지어졌다 제거된 셋의 **가격이 주석에 남아 있다** |

### 1.2 읽기 쪽 — 추적 화면

| 파일 | 무엇 | 왜 이 경계인가 |
|---|---|---|
| `server/ledger_trace.py` | **셋이 살고 둘은 서로를 몰라야 한다**: **해결기**(`claim_class`/`claim_rank_key`/`resolve` — 순수 파이썬, SQL·테이블명·커넥션 0) · **조회기**(`ClaimLookup` 계열 — 가져오기만 하고 등급을 모른다) · **보행**(`trace` — 조회기에 한 번 묻고 홉마다 해결기에 한 번 묻는다) | 스타일이 아니라 **구조 요구**다. 슬라이스 1은 **랏 단위**라 질의 시점 해결로 가지만 **슬롯 단위 혈통은 질의 시점에서 죽는다**(인라인 452 ms 대 물질화 0.58 ms — 합성·이 박스). 조회기가 **교체 가능한 객체**라 물질화된 클로저 테이블로 옮기는 것이 **생성자 인자 하나**이고 해결기는 한 줄도 안 바뀐다. `InMemoryClaimLookup`은 그 교체 가능성을 **주장이 아니라 검사된 성질**로 만든다 |
| `server/ledger_trace_router.py` | `GET /api/ledger/trace` (+ 커버리지 — §4.6 주의) | 🔴 **SPA catch-all «위»에 등록해야 한다.** FastAPI는 등록 순서로 매칭하므로 catch-all 뒤에 등록된 라우트는 **200으로 `index.html`을 받는다** — 감시자가 죽은 엔드포인트를 살아 있다고 부르게 되는 실패다(`/health`가 실제로 그랬다). 현재 `server/main.py`에서 catch-all 훨씬 위에 등록돼 있다. 🔴 **빈 `hops`는 가능한 답이 아니다** — 어느 홉에서 왜 끊겼는지가 이 화면의 존재 이유다 |
| `client2/src/ledger_trace_core.js` | **순수**. DOM·네트워크·import 0. 서버 답을 낱말과 톤에 매핑만 한다 | 🔴 **이 모듈은 원장에 대해 아무것도 판정하지 않는다.** 어느 주장이 이기는지는 서버가 이미 정했다. **여기에 승패 규칙이 나타나면 그건 두 번째 해결기이고 틀린 것이다** |
| `client2/src/ledger_trace_view.js` | 답을 DOM으로. `document`가 **전역이 아니라 인자** | 그래서 `client2/tests/ledger_trace_harness.mjs`가 **진짜 렌더러를** bare node로 몰아 「화면에 실제로 도달한 것」을 단언한다 — 함수가 존재한다는 단언이 아니라. `innerHTML` 0(원장에서 나온 랏 id가 마크업이 될 수 없다) |
| `client2/src/ledger_trace.js` | 페이지 진입점(`ledger.html`). 질문 읽기 → fetch → 뷰에 넘기기 | 🔴 **읽기 전용 화면.** GET 하나를 쏘고 아무 데도 안 쓴다. `window`를 만지는 유일한 파일이라 나머지 둘이 bare node에서 채점된다 |

---

## 2. 쓰기 경로 — 소스 행 하나가 원자가 되기까지

```
소스 행들                (backfill.fetch_page — event_time 순, 그룹 경계에서만 자른다)
   ↓ group_molecules     한 소스 이벤트 = 한 분자 (lot_event은 두 행)
분자
   ↓ translator.translate   원자를 «만든다». 아직 아무것도 안 검사됐다
Atom[]
   ↓ gate.screen_molecule   원자성 검사 넷. 전부 아니면 전무
kept[]  (또는 [])
   ↓ store.write_batch      원자 INSERT + 커서 UPDATE = 커밋 하나
ledger_events + ledger_translator_cursor
```

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
그리고 **v0 일곱이라는 수는 통제 장치**다 — `test_ledger_l1_unit.py`가 `PREDICATES` 집합을 못박고 있으므로
여덟 번째를 더하면 **테스트가 빨개진다. 그 빨강이 「판정을 적으라」는 자리다.**
등재는 [LEDGER_RULINGS](../process/LEDGER_RULINGS.md)에 남는다 — **거기 없으면 내려진 적이 없는 판정이다.**

### ② `ledger_config.json`에 선언 한 장

`server/config/ledger_config.json`(gitignore. 배포본은 `.json.sample`이고 실 파일이 없으면 **샘플로 폴백**한다).
`sources.<이름>` 아래 한 장:

| 키 | 필수 | 뜻 · 함정 |
|---|---|---|
| `occurred_at_column` | ✅ | **세상의 시각을 담은 소스 컬럼 이름.** 없으면 소스 전체 거절 — 기본값 없음 |
| `occurred_at_timezone` | ✅ | 소스의 **naive 텍스트**가 무슨 시각인지. 🔴 **`Asia/Seoul`(제품 소유자 판정)**. 오프셋을 달고 온 문자열에는 **다시 먹이지 않는다** |
| `occurred_at_format` | ⬜ | 기본 `%Y-%m-%dT%H:%M:%S`. 🔴 **구분자만 넓힌다** — 선언된 형식에서 시(hour) 직전 구분자 하나를 바꾼 사본과, 각각에 `%z`를 단 사본까지 **총 4후보**. 문법을 넓히는 것이 아니라 **전송 형태**를 넓히는 것이고, 어떤 문자열도 두 가지로 읽히지 않는다 |
| `subject_type` | ✅ | 로드 시점에 검증되지만 **⚠️ 어느 원자에도 도달하지 않는다** — subject 타입은 번역기 안의 리터럴에서 온다. 아래 「함정」 참조 |
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

- ⚠️ 🔴 **subject 타입은 «전부 번역기 안의 리터럴»에서 오고 선언에서 오지 않는다.**
  `self.subject_type = source_cfg.get("subject_type", "Lot")`은 `lot_event_translator.py:190`에서 대입되고
  **어디서도 읽히지 않는다.** 호출부가 리터럴을 넘긴다 — `"Lot"`(:308 · :334 · :341 · :392 · :415)과
  **`"Wafer"`(:329)**. 그러므로 `config.validate()`는 **어느 원자에도 도달하지 않는 필드를 검사한다.**
  **⚠️ 「모든 원자가 `Lot`」이 아니다** — `assy_manager` 실측 **`Lot` 689 · `Wafer` 220**이고,
  웨이퍼 `register` 220개가 전부 subject 타입 `Wafer`를 정확히 달고 있다. 그 경로는 **이미 있고 잘 돈다.**
  🔴 **그리고 이것이 이 필드가 배선되지 않은 «이유»다: 소스당 `subject_type` 하나는 애초에 틀린 모양이다.**
  `lot_event` **한 소스가 개체 타입 «둘»에 대한 원자를 만든다**(랏에 대한 주장과 웨이퍼에 대한 주장).
  선언이 번역기가 실제로 하는 일을 **표현하지 못하는 것**이지 코드가 읽기를 잊은 것이 아니다.
  ⏳ **이 필드 자체는 총괄이 별도로 판정 중이다.** 그때까지 새 번역기는 **자기 호출부에서 subject 타입을 명시**하라.
- ⚠️ **`columns`의 일곱은 lineage가 없는 소스도 전부 선언해야 한다.** 로드 검증이 무조건 요구한다 —
  `parent_lot`/`child_lot`/`slots`/`wafers`를 안 쓰는 소스도 컬럼 이름을 적어야 통과한다.
- ⚠️ **`columns.equipment`는 선언돼 있고 `server/ledger/` 안에서 아무도 읽지 않는다.** 베낄 때 딸려 오지 않게 할 것.

### ③ 번역기 작성 — `lot_event_translator`의 모양을 그대로

```python
class <Source>Translator:
    def __init__(self, source_cfg, translator_ver, declared_derivations, who=SOURCE): ...
    def translate(self, molecule) -> tuple[list[Atom] | None, dict]: ...
```

지켜야 하는 것:

- **`(atoms, report)`를 돌려준다.** 원자가 되기 전에 거절했으면 **`(None, report)`** — 그때는 이미 `gate.refuse()`가 세었고
  호출자는 아무것도 안 쓰기만 하면 된다.
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
| **어휘 집합** | `PREDICATES`가 정확히 일곱 · `REFUSAL_REASONS`가 닫혀 있음 |

**실행:**
```bash
conda run -n assy_manager python -m pytest server/tests/test_ledger_l1_unit.py server/tests/test_ledger_l1_pg.py server/tests/test_ledger_trace.py server/tests/test_ledger_trace_contract.py server/tests/test_ledger_trace_pg.py
```
🔴 **PostgreSQL 절반은 기본 실행에서 «건너뛰어진다»** — 초록 개수가 통과처럼 보이지만
실제 DB에 대고 안 돌면 스키마·인덱스·CHECK는 하나도 채점되지 않는다. skip 수를 반드시 읽을 것.
파이썬은 **전부 conda `assy_manager`**로(시스템 python은 `psycopg2` 부재로 **거짓 실패**한다).

---

## 4. 운영자 절

> 🔴 **운영에서 무엇을 어느 순서로 돌리는가는 [OPERATOR_RUNBOOK §6·§8](../process/OPERATOR_RUNBOOK.md)이 소유한다.**
> 이 절은 **명령이 무엇을 하는지·숫자를 어떻게 읽는지**만 적는다. 순서는 저쪽을 보라.

### 4.1 설치 — 마이그레이션

```bash
conda run -n assy_manager python server/migrations/add_ledger_events.py            # 만든다
conda run -n assy_manager python server/migrations/add_ledger_events.py --report   # 아무것도 안 바꾸고 상태만
conda run -n assy_manager python server/migrations/add_ledger_events.py --months 3 # 파티션 미리 3개월치
```

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
- 🔴 **커서는 세계 시각(`event_time`)이다.** 늦게 도착한 오래된 타임스탬프 행은 **커서 뒤에 앉고 이 백필은 못 본다.**
  일회성 백필에는 받아들일 만하고(이미 있는 것을 쓸어 담는 것이 목적) **라이브 구독에는 아니다** —
  그쪽은 아웃박스가 몰아야 한다. `--from`으로 어느 창이든 다시 돌릴 수 있고 재실행은 유니크 인덱스 덕에 공짜다.

### 4.4 커서·박동 숫자 읽는 법

```sql
SELECT * FROM ledger_translator_cursor;
```

`assy_manager` 2026-08-13 실측:

```
source=lot_event  translator_ver=lot_event/1/rules:d8d1c9e0
cursor_value={"event_time": "2026-05-21 20:33:00"}
molecules_done=26  atoms_written=909  atoms_deduped=0
molecules_refused=1  incomplete_molecules=2
source_head={"event_time": "2026-05-21 20:33:00", "rows_behind": 0}
```

| 필드 | 읽는 법 |
|---|---|
| `cursor_value` | **온전히 처리한 마지막 `event_time` 그룹.** 크래시하면 그 그룹의 «다음»부터 다시 읽는다 |
| `molecules_done` | 이 소스에 대해 **본** 분자 총계. 🔴 **거절된 것도 포함**한다 — `molecules_refused`는 그 부분집합이다 |
| `atoms_written` / `atoms_deduped` | 실제 INSERT된 수 / 유니크 인덱스가 걸러낸 수. **누적**이다(SET이 아니라 `+=`) |
| `molecules_refused` | 문 앞에서 통째로 거절된 분자. **왜인지는 여기 없다** — 로그와 박동 노트에 있다 |
| `incomplete_molecules` | 착지했지만 소스 이벤트의 행이 다 안 온 분자. **거절이 아니다.** 혈통 사슬에 구멍이 있는 이유 |
| `source_head` / `head_probed_at` | 티어 2 프로브가 마지막으로 본 소스 끝과 그 시각 |

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

**이 박스 실측 (2026-08-13, `:8080`)**:
```
GET /api/ledger/coverage  ->  200
{"state":"ready","lots":25,"sources":["lot_event"],
 "occurred_at":{"from":"2026-05-03T02:17:00+09:00","to":"2026-05-21T20:33:00+09:00"},"sample":[…]}
```

🔴 **테이블이 없을 때 `/trace`는 «카탈로그와 SQLSTATE»로 판정한다 — 에러 문자열이 아니다.**
`to_regclass` 선조회가 먼저이고(그 자체가 요청 트랜잭션을 깨끗하게 유지한다),
경합 대비 백스톱은 SQLSTATE **`42P01`**이다. 503의 본문은 **산문이 아니라 구조**다 —
클라는 `detail.reason`·`detail.state`로 분기하고 운영자는 `detail.message`를 읽는다.
`state`는 `/coverage`의 어휘를 **일부러 그대로 쓴다**(한 낱말이 두 라우트에서 한 뜻).

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
