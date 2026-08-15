# 🧱 온톨로지·원장 셋업 — 무엇을 어느 순서로 «선언»해야 도는가

> **Status:** 🟢 Living | **Last-verified:** 2026-08-15 (선언 표 전수를 코드와 대조) | **Owner:** Server / Ledger + 온톨로지
> **Source-of-truth:** `server/ledger/config.py` · `server/ledger/vocabulary.py` · `server/finding_kinds.py` · `server/mechanism_gate.py` · `server/ledger_siblings.py` · `server/ledger_journey.py` · `server/config/*.json(.sample)`
>
> 🔴 **셋업 «절차»는 이 문서 하나다.** 다른 문서에서 같은 절차를 다시 만나면 그것은 낡은 사본이고, 그 사본을 따르면 실제로 손해가 난다
> (2026-08-15 실측: 운영자 가이드 셋이 이미 «삭제된 것»을 돌리라고 말하고 있었다 — `08e2659`).
> 이 문서는 **WHY를 쓰지 않는다** — 왜 원자가 7필드인지·왜 어휘가 닫혀 있는지는
> [architecture/CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md)이,
> 물리 층의 설계는 [architecture/PHYSICS_ONTOLOGY_SETUP](../architecture/PHYSICS_ONTOLOGY_SETUP.md)이 소유한다.
> **EXACTLY-WHAT**(컬럼·인덱스·응답 계약)은 [spec/LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md),
> **판정**은 [process/LEDGER_RULINGS](../process/LEDGER_RULINGS.md) — 🔴 거기 없는 판정은 내려진 적이 없는 것으로 친다.
>
> ⚠️ **이 문서의 실측 수치·라이브 파일 유무는 전부 개발 박스(`assy_manager`) 기준이고 운영의 증거가 아니다.**
> 코드 대조 기준 리비전은 **`08e2659`(HEAD)**이며, 워킹트리에 미커밋인 것은 그 자리에 표시했다.

---

## 0. 두 독자

| 당신이 | 읽을 곳 |
|---|---|
| **빈 배포에 원장·온톨로지를 올리려는 운영자** | §1 선언 표 → §2 순서 → §10 검증 |
| **새 소스를 원장에 붙이려는 개발자** | §1 → §3 선언 한 장 → 그다음 **코드 쪽 절차는** [LEDGER_GUIDE §3 ③~⑥](./LEDGER_GUIDE.md) |

🔴 **원장은 «소비자»로 태어났다.** 기존 테이블을 읽고 자기 테이블 둘에만 쓴다 —
쓰기 경로·`crud`·체인·맵은 한 줄도 안 바뀐다. **아무것도 안 돌려도 기존 시스템은 그대로 돈다**(§2 각 단계의 「안 하면」 칸).

---

## 1. 선언 표 — 사람이 손으로 쓰는 자리 «전부»

🔴 **`server/config/*.json`은 gitignore다.** `git pull`이 안 실어 오고, 그것이 설계다(배포가 운영자 설정을 덮지 못하게).
배포본은 `*.json.sample`이고 **켜는 방법은 손복사**다.

| 선언 | 무엇을 지배하나 | config인가 코드인가 | 라이브가 없으면 | 이 박스(2026-08-15) |
|---|---|---|---|---|
| **`server/config/ledger_config.json`** | **소스 선언** — 소스마다 한 장. 문법(`kind`)·세상의 시각 컬럼·시간대·컬럼 매핑·허용 subject 타입 | **config** | `.sample`로 폴백 → **둘 다 없으면 번역기가 «거절하고 안 돈다»**(시각 컬럼을 추측하지 않는다) | 라이브 有 · 소스 넷(`lot_event`·`void_obs`·`delam_obs`·`dt_log`) |
| **`server/ledger/vocabulary.py`** | **어휘의 «코드 절반»** — 정준 층 전부 + 코드가 싣는 온톨로지 술어, 그리고 **개체 타입(`ENTITY_TYPES`)은 여기만** | 🔴 **코드**(정준 층은 화면에서 늘릴 수 없다 — 판정 사안) | — | §4 |
| **`server/config/ledger_vocabulary.json`** | **어휘의 «선언 절반»** — ontology 층 술어의 append-only 확장. 서명 완결이 저장 조건 | **config**(2026-08-15 신설 · R-2026-08-15-M) | 🔴 **`.sample` 폴백 «없음»** — 라이브가 없으면 코드가 싣는 낱말만 쓴다. **일부러 그렇다**: 샘플이 로드되면 아무도 선언하지 않은 낱말이 닫힌 어휘에 들어간다 | 라이브 **없음**(`.sample`은 모양 설명용) · §4 |
| **`server/finding_kinds.py`** + `server/config/finding_kinds.json` | **결함 종류** — 종류마다 분모(`observed_by`)·관측 테이블·크기 컬럼·닫힌 class 집합 | 🔴 **코드 기본값 + JSON «덮어쓰기»**(선택) | 기본값 둘(`void`·`delam`)로 돈다 | JSON **없음**(코드 기본값으로 도는 중) · §5 · §9 ② |
| **`server/config/mechanism_models.json`** | **기전 그래프** — 방향만 있는 인과 모델 + `bindings`(필드→물리량). 「**물리 경로 있음**」 관문이 읽는 것 | **config** | `.sample` → 둘 다 없으면 **에러가 아니라 «상태»**(`no_mechanism_config`) | 라이브 有(`.sample`도 有) |
| **`server/config/siblings_axes.json`** | **요인 기하** — 마킹·행·요인 축, 모집단 단위, `rank: false`(식별자 축)·`high_cardinality_at` | **config** | `.sample`로 폴백 → **둘 다 없으면 거절**(축 0개는 500이 아니라 이름 붙은 거절) | 라이브 **없음** — `.sample`로 도는 중 |
| **`server/config/ledger_journey.json`** | **여정** — 어느 술어가 여정을 나르고 step 이름이 payload 어디에 있는지(`segments`) + 한국어 이름 셋 | **config** | `.sample` → 둘 다 없으면 **상태 `absent`**(500 아님) | 라이브 **없음** — `.sample`로 도는 중 |
| ~~`server/config/ontology_mapping.json`~~ | ⚰️ **은퇴** | — | — | 🚫 **새로 쓰지 마라 — §7** |
| `server/config/table_config.json` | **선행 조건** — 관측 소스의 테이블(`inspection_run`·`void_obs`·`delam_obs`)이 «존재»하게 하는 선언 | config | 테이블이 없으면 관측 백필이 **전부 거절** | 켜는 순서는 [OPERATOR_RUNBOOK §4](../process/OPERATOR_RUNBOOK.md) |
| `environment.yml`의 `tzdata` | **배포 의존성** — `Asia/Seoul`은 런타임에 IANA DB에서 해석된다 | 환경 | 🔴 **조용히 UTC로 안 떨어지고 «예외»를 낸다**(일부러) | `conda env update -f environment.yml` |

🔴 **`.sample` 폴백이 있다고 「선언이 끝났다」가 아니다.** 폴백은 **새 체크아웃이 500 대신 답하게 하는 장치**이고,
`.sample`은 **이 박스의 스키마를 말한다.** 다른 스키마의 운영 배포에서 폴백이 도는 것은 **남의 컬럼 이름으로 도는 것**이다.

---

## 2. 순서 — 빈 배포에서 「화면이 답한다」까지

| # | 무엇 | 선행 | 안 하면 |
|---|---|---|---|
| **①** | **시간대 확정 + `tzdata`** — 선언은 `Asia/Seoul`, 형식은 `T`가 낀 ISO 8601(제품 소유자 판정, [RUNBOOK §8](../process/OPERATOR_RUNBOOK.md)) | — | 🔴 **모든 원자가 어긋나고 «아무것도 항의하지 않는다»** — 어긋난 시각도 well-formed하다. 정정은 재백필이지 제자리 `UPDATE`가 아니다 |
| **②** | **소스 테이블이 실재하게 한다** — 관측을 쓸 것이면 `inspection_run`(**분모**)·관측 테이블. 순서(선언 손복사 → 리로드 → 인덱스 → 파서 → 파일)는 [OPERATOR_RUNBOOK §4](../process/OPERATOR_RUNBOOK.md)가 정본이고 **여기 다시 적지 않는다** | ① | 분모가 없으면 「발견 0」과 「스캔 안 함」이 **같은 부재**가 되고 둘 다 깨끗하게 읽힌다 |
| **③** | **마이그레이션 둘** (아래 명령) | ①·② | 표가 없다 → `GET /api/ledger/trace`가 **503 + 관계 이름**, `/coverage`가 `state: "absent"`. **그 밖에는 아무것도 안 깨진다** |
| **④** | **`ledger_config.json`에 소스 선언** — §3 | ③ | `--source`가 `undeclared_source`로 거절하고 **한 행도 안 읽는다** |
| **⑤** | **어휘 확인** — 새 술어·개체 타입이 필요한가(대개 아니다). §4 | ④ | `subject_types`에 미선언 타입을 적으면 **로드 시점 거절** |
| **⑥** | **백필** (아래 명령) | ③④⑤ | `/coverage`가 `state: "empty"` — 표는 있고 원자 0 |
| **⑦** | **화면 층 선언** — `finding_kinds`(§5) · `siblings_axes` · `mechanism_models` · `ledger_journey`(§6) | ⑥(원자가 있어야 «보인다») | 각각 자기 부재를 **이름 대어 말한다**(500이 아니다). 잃는 것은 답이 아니라 **답의 해상도** |
| **⑧** | **검증** — §10 | ⑦ | — |

**③ 마이그레이션 — 표 둘과 컬럼 하나**

```bash
# ① 표 둘을 만든다 (ledger_events · ledger_translator_cursor)
conda run -n assy_manager python server/migrations/add_ledger_events.py
conda run -n assy_manager python server/migrations/add_ledger_events.py --report   # 아무것도 안 바꾸고 상태만
conda run -n assy_manager python server/migrations/add_ledger_events.py --months 3 # 파티션을 3개월치 미리

# ② 커서 표에 거절 «내역» 컬럼 하나 (열둘 → 열셋)
conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py
conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py --report
conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py --reverse
```

- **둘 다 추가 전용·멱등이다.** DROP 없음, 기존 것의 ALTER 없음, 기존 표의 행을 읽거나 쓰는 문장 없음.
- **파티션은 만들지 않는다** — 번역기가 **자기가 쓸 달을 쓰기 직전에** 만든다. 존재할 달을 정하는 것은 배포일이 아니라 **데이터**다.
- 🔴 **②를 건너뛰어도 서버는 500이 아니다.** 쓰는 쪽(`ensure_schema`)이 백필 첫 단계에 같은 문장을 스스로 적용하고,
  읽는 쪽(`/coverage`)은 **카탈로그에 컬럼 존재를 먼저 묻는다.** 잃는 것은 **거절 사유를 이름으로 보는 능력**뿐이다.
  성질·되돌리기의 자세한 근거는 [LEDGER_GUIDE §4.1](./LEDGER_GUIDE.md).

**⑥ 백필 — 명령은 하나이고 «선언»이 경로를 정한다**

```bash
# server/ 에서 실행 (-m 이라 패키지 경로가 잡힌다)
conda run -n assy_manager python -m ledger.backfill --source lot_event   # lineage
conda run -n assy_manager python -m ledger.backfill --source void_obs    # observation
conda run -n assy_manager python -m ledger.backfill --source delam_obs   # observation
conda run -n assy_manager python -m ledger.backfill --source dt_log      # transfer
```

🔴 **드라이버를 고르는 것은 명령줄이 아니라 선언의 `kind`다**(`backfill.run`이 분기). 운영자가 외울 것은 **소스 이름뿐**이다.
소스끼리는 **서로 독립이라 순서가 없다** — ③ 뒤이기만 하면 된다.

| 플래그 | 뜻 |
|---|---|
| `--source <이름>` | 기본 `lot_event`. 선언이 없으면 **`undeclared_source`로 거절하고 아무것도 안 읽는다** |
| `--reset-cursor` | 커서를 무시하고 끝난 일감을 다시 읽는다. 유니크 인덱스(둘째 그물)를 실제로 태우는 방법이자 **재번역**의 방법 |
| `--from <위치>` | 커서 대신 이 위치 «다음»부터. 🔴 **철자가 문법마다 다르다** — lineage는 `event_time` 하나, observation은 **선언된 키셋을 `\|`로 이은 것**, transfer는 그룹 컬럼 값 |
| `--fetch-rows N` | 소스 페이지 크기(기본 2000). **배치 크기가 아니다** — 트랜잭션 크기는 `batch.molecules_per_transaction` |
| `--max-batches N` | N 배치 후 정지. 첫 시험 주행용 |
| `--config <경로>` | 다른 선언 파일로 |

⚠️ **재실행의 «뜻»은 선언을 바꿨는지에 달렸다** — 그냥 재실행은 0행, `--reset-cursor`는 dedupe,
**선언을 고친 뒤의 `--reset-cursor`는 「같은 주장, 새 provenance」를 새로 쓴다**(선언 전체가 `source_translator_ver`에 해시되므로).
근거와 읽는 법은 [LEDGER_GUIDE §4.3](./LEDGER_GUIDE.md).

---

## 3. `ledger_config.json` — 소스 선언 한 장

> 🔴 **이 절이 이 문서로 «옮겨 온» 자리다**(2026-08-15). 종전에는 [LEDGER_GUIDE §3 ②·②-bis·②-ter](./LEDGER_GUIDE.md)와
> [CONFIG_GUIDE §1](./CONFIG_GUIDE.md)에 **두 벌**로 있었다. 저쪽 둘은 이제 이 절을 가리킨다.

### 3.0 먼저 «어느 문법인지»부터 정한다

`kind` 한 낱말이 **필수 키 집합과 검증 갈래**를 통째로 가른다. 잘못 고르면 「없는 컬럼이 없다」는 이유로 거절된다.

| `kind` | 소스가 말하는 것 | 실물 | 베낄 번역기 | 키 표 |
|---|---|---|---|---|
| **`lineage`** (기본) | **여러 행이 모여** 한 사건(랏이 갈라졌다·합쳐졌다) | `lot_event` | `lot_event_translator.py` | §3.1 |
| **`observation`** | **한 행이 곧 한 발화**(이 웨이퍼에서 이런 발견을 봤다) | `void_obs`·`delam_obs` | `observation_translator.py` | §3.2 |
| **`transfer`** | **한 행이 다이 하나**이고 원자 단위는 **잡런** — 행을 선언된 컬럼으로 «묶는다» | `dt_log` | `transfer_translator.py` | §3.3 |
| (테이블이 아님) | 생성기·계산된 사실·외부 API | `seed_syn_process_ledger.py` | — | 🔴 **`ledger_config.json`에 넣지 마라 → [LEDGER_GUIDE §3-bis](./LEDGER_GUIDE.md)** |
| ⏳ ~~`derivation`~~ | 규칙이 조건을 평가해 만드는 주장(태그·스킴 분류) | — | — | 🔴 **판정됨 · «미구현»**([R-2026-08-15-M](../process/LEDGER_RULINGS.md) 5) — `SOURCE_KINDS`에 없으므로 오늘 선언하면 **로드 거절**이다. 판정을 기능으로 읽지 말 것 |

⚠️ **`kind`를 안 적으면 `lineage`다.** 기본이 그쪽인 것은 **이 파일이 원래 알던 유일한 모양**이기 때문이지 혈통이 더 근본이어서가 아니다.

### 3.1 `lineage` 키

| 키 | 필수 | 뜻 · 함정 |
|---|---|---|
| `occurred_at_column` | ✅ | **세상의 시각을 담은 소스 컬럼**. 없으면 **소스 전체 거절** — 기본값 없음(도착 시각이 대신 서지 못한다) |
| `occurred_at_timezone` | ✅ | 소스의 **naive 텍스트**가 무슨 시각인지. 🔴 `Asia/Seoul`. **오프셋을 달고 온 문자열에는 다시 먹이지 않는다** |
| `occurred_at_format` | ⬜ | 기본 `%Y-%m-%dT%H:%M:%S`. 구분자 계열만 넓힌다 |
| **`subject_types`** | ✅ | 🔴 **복수 allow-list이고 «문다»** — 밖에 있는 원자는 `undeclared_subject_type`으로 이름 대고 거절·계수된다. 멤버는 전부 `vocabulary.ENTITY_TYPES`의 선언된 타입(**여기 타입을 더하는 것은 config 결정이 아니라 어휘 결정** — §4). ⚠️ **단수 `subject_type`은 «로드 에러»다**(무시도 승계도 아니다) |
| `register_entity_types` | ⬜ | `register` 원자를 낼 **발급형** 타입들. `Die`는 **구성형**이라 일부러 없다 |
| `list_separator` | ⬜ | 기본 `":"` — 위치 대응 리스트의 구분자 |
| `columns.*` | ✅ | **일곱 전부**: `row_identity` · `lot` · `event_type` · `parent_lot` · `child_lot` · `slots` · `wafers`. 논리 이름 → 물리 컬럼이고 **번역기는 물리 이름을 절대 안 본다**. ⚠️ **혈통이 없는 소스도 일곱을 다 적어야 통과한다** |
| `vocabulary.<event_type>` | ✅ | 이 소스가 알아듣는 이벤트 타입들. **여기 없는 event_type은 «건너뛰는» 것이 아니라 거절되고 세어진다** |
| `vocabulary.*.lineage` | ⬜ | `parent_child` \| `none` |
| `vocabulary.*.slot_pairing` | ⬜ | `shared_wafer`(추론 0) \| `slot_preserving`(**운영자의 관례 선언**) \| `none`. 🔴 **오타는 로드 시점 에러다** — 조용히 `none`으로 떨어지면 슬롯 체인 없는 원장이 항의 없이 생긴다 |
| `vocabulary.*.emit_has_wafer` / `emit_register` | ⬜ | 기본 `true` |
| `batch.molecules_per_transaction` | ⬜ | 기본 200. **온전한 소스 이벤트 개수**이고 절대 분수가 아니다 |
| `lag.probe_interval_seconds` | ⬜ | 기본 60 |

⚠️ **`columns.equipment`는 `.sample`에 있고 `server/ledger/` 안에서 «아무도 읽지 않는다».** 베낄 때 딸려 오지 않게 할 것.

### 3.2 `observation` 키

**§3.1의 키 목록은 여기 적용되지 않는다** — 검증이 `kind`로 분기하고, 혈통 키를 쓰면 **이름을 대며 거절**한다.

| 키 | 필수 | 뜻 · 함정 |
|---|---|---|
| **`kind`** | ✅ | `"observation"`. 없으면 lineage로 채점돼 **`parent_lot`이 없다는 이유로** 거절된다 |
| **`finding_kind`** | ✅ | 이 소스가 번역하는 결함 **종류 하나**. 🔴 **종류의 «정의»는 여기가 아니라 `server/finding_kinds.py`**(§5) — 이 선언이 소유하는 것은 **어느 소스가 그것을 생산하는가** 하나뿐 |
| **`run`** | ✅ | `{relation, key_column, method_column}`. 🔴 **세상의 시각과 분모가 «둘 다» 여기서 나온다** — `occurred_at`은 발견 행이 아니라 **이 관계**에서 읽는다. **런을 못 푸는 발견은 원자 0개**(도착 시각으로 대체하지 않는다) |
| **`watermark.columns`** | ✅ | 커서의 **키셋**(예: `["updated_at", "row_id"]`). 🔴 **세계 시각 커서를 쓸 수 없다** — 대량 적재가 `updated_at` 하나를 수만 행에 찍으므로 한 적재가 **쪼갤 수 없는 한 그룹**이 된다. 선언한 키셋은 **유니크 + 인덱스 뒷받침**이어야 하고, ✅ **그 인덱스는 이미 공짜다**(`models.py`가 모든 동적 테이블에 `idx_<table>_updated (updated_at, row_id)`를 만든다) |
| **`columns`** | ✅ | **필수 셋**: `row_identity` · `wafer` · `run_key`. **선택**: `die_x`·`die_y`·`die_gate`·`inchip_x`·`inchip_y`·`extent_x`·`extent_y`·`unit`·`class`. 🔴 **목록 밖 이름은 «로드 시점 거절»** — 안 읽히는 매핑은 대개 읽히는 이름의 오타다 |
| `synthetic` | ⬜ | 참이면 **모든 원자 payload에 `"synthetic": true`**. 🔴 **실물 피드가 오는 날 이 줄을 «지우고» 재백필하는 것**이 그 사실의 철회다(원장에 UPDATE는 없다) |
| `subject_types` / `register_entity_types` | ✅ / ⬜ | `["Wafer"]`. 🔴 **`Die`가 아니다** — 다이는 구성형이라 등록이 없고, 발견을 웨이퍼 아래 접어야 「이 웨이퍼의 보이드」가 질의 하나가 된다 |
| `occurred_at_*` · `batch.*` · `lag.*` | ✅ / ⬜ | §3.1과 같다. 다만 `occurred_at_column`이 가리키는 것은 **런 관계의 컬럼**이다 |
| ~~`vocabulary`~~ | ❌ | 🔴 **있으면 로드 에러다** — 관측 소스에는 이벤트 타입이 없다(한 행이 한 발화) |

### 3.3 `transfer` 키

| 키 | 필수 | 뜻 · 함정 |
|---|---|---|
| **`kind`** | ✅ | `"transfer"` |
| **`group`** | ✅ | `{column, row_order_column}` — 행을 한 사건으로 묶는 컬럼과, 페이지를 결정적으로 만드는 타이브레이크. ⚠️ **business key로 정렬하지 마라**(`<group>_<x>_<y>` 꼴이라 **어떤 그룹 이름도 다른 것의 접두가 아닐 때만** 연속한다 — 오늘 데이터의 우연이다) |
| **`container`** | ✅ | `{relation, key_column, lot_column, slot_column}` **또는 `{"relation": null}`**(확정 관계가 아예 없다는 «선언»). 🔴 **목적지의 신원을 누가 확정하는가.** 선택이 아닌 이유: 못 선언하게 하면 번역기가 읽을 것은 **행에 적힌 값**뿐인데, `dt_log`에서 그 컬럼은 `table_config.json`이 스스로 **「추론 대상 — 40% 부재, 10%는 있는데 틀림」**이라 적어 둔 바로 그것이다 |
| **`columns`** | ✅ | **필수 셋**: `row_identity` · `group_key` · `wafer`. **선택 둘**: `recorded_lot` · `recorded_slot`(신원이 아니라 **보존된 발화**). 목록 밖 이름은 로드 시점 거절. ⚠️ **`columns.group_key`와 `group.column`이 다르면 거절** — 분자 키와 배치 경계가 어긋나기 때문 |
| `subject_types` / `register_entity_types` | ✅ / ⬜ | `["Wafer"]`. 🔴 **DT 테이프는 subject이 아니라 «장소»다** |
| ~~`vocabulary`~~ | ❌ | 있으면 로드 에러(잡런 하나가 한 이동이라 이벤트 타입이 없다) |

🔴 **확정됐는지는 파생 이름이 말한다** — `#job_run_to_confirmed_container` 대 `#job_run_to_job`.
새 컬럼도 새 플래그도 없고 **질의 가능**하다: `WHERE source_translator_ver LIKE '%#job_run_to_job'`이 「목적지가 확정된 적 없는 이동」의 전량이다.

### 3.4 선언을 다 썼으면

**번역기 «코드»를 쓰는 절차는 여기 없다.** 클래스 모양·게이트 스코프·`#<derivation>` 접미와 그때 빨개지는 테스트·픽스처 규율·검증 기대치는
[LEDGER_GUIDE §3 ③~⑥](./LEDGER_GUIDE.md)이 소유한다. **선언은 JSON이고 번역기는 파이썬이라, 이 문서는 앞엣것만 소유한다.**

---

## 4. 어휘 — 🔴 **층에 따라 갈린다**(2026-08-15부터)

**두 층이고 성질이 다르며, 이제 «어디서 늘리는가»도 다르다.**

| 층 | 무엇 | 어디서 늘리나 | 왜 |
|---|---|---|---|
| **정준**(§4.1) | 기록의 문법 — `register`·`pin`·예약 `same_as` | 🔴 **코드 + 판정만.** 화면에 문이 **없다** | 기록의 문법이 조용히 자라면 원장이 원장이 아니게 된다 |
| **온톨로지**(§4.2) | 세계의 언어 — `derived_from`·`observed`·… | ✅ **admin 화면에서 선언으로**(코드 0줄·재기동 0회) 또는 코드로 | 설계가 이미 「append-only로 성장」이라 적어 둔 층이다 |
| **개체 타입**(`ENTITY_TYPES`) | `Lot`·`Wafer`·`Recipe`·… | 🔴 **코드 + 판정만** | 주어의 «신원 키»가 바뀌는 일이라 술어 하나 늘리는 것과 급이 다르다 |

- **선언 확장의 자리**: `server/config/ledger_vocabulary.json`. 화면 경로는 `POST /admin/ledger/dry-run` → `POST /admin/ledger/save`이고,
  **저장은 언제나 3단**이다(문법 검증 → 쓰기 0 드라이런 → 저장+리로드+「먹었는가」). 드라이런 없는 저장은 만들지 않은 게 아니라 **불가능**하다 —
  저장이 «그 선언의» 드라이런 지문을 요구한다.
- 🔴 **서명이 완결돼야 저장된다.** `label_ko`·`subject`·`object{kind, required}`·**`traversable` 삼상태 «명시»**·`direction`·`layer`·`status`·`since`.
  하나라도 없으면 이름 붙은 거절이다. ⚠️ **`traversable`은 «키의 존재»까지 본다** — 없으면 「생각 안 했다」와 「걷기가 절대 안 가져온다(null)」가 같은 선언이 된다.
- 🔴 **`traversable: true`는 오늘 «선택할 수 없다»** — 걷기의 재귀 질의는 통과 술어를 정확히 하나만 실행하고 그 자리엔 `derived_from`이 있다.
  둘째를 저장하면 추적 화면이 다음 요청에 죽으므로, **읽는 날이 아니라 저장하는 날** 이름 붙여 거절한다.
- 🔴 **삭제 경로가 «없다».** 원자가 이미 그 낱말로 누워 있으므로 `status: retired` + `superseded_by`만 있고, **은퇴는 읽기를 막지 않는다**(발화만 막는다).
- 🔴 **이 문서는 낱말 목록도 그 «개수»도 옮겨 적지 않는다.** 옮겨 적는 순간 두 번째 목록이 되고, 그 둘은 갈라진다.
  정본은 코드의 `PREDICATES` + 선언 파일이고, 합쳐진 뷰는 `vocabulary.all_predicates()` 하나다.
  화면에 그려지는 것도 그 선언에서 **생성**된다(`GET /api/ledger/structure` — 손으로 적은 노드 목록이 응답 어디에도 없고, 항목마다 `origin: code|config`가 붙는다).
- **셋업에서 실제로 걸리는 지점은 하나다**: `ledger_config.json`의 `subject_types` 멤버는 **`ENTITY_TYPES`에 있는 이름이어야 한다.**
  없는 이름을 적으면 **로드 시점에 거절**되고, 그 해결은 config 편집이 아니라 **코드의 어휘 등재**다(개체 타입은 여전히 코드다).
- **코드로 낱말·개체 타입을 더하는 절차**(3문 검사 → 판정 기록 → 예상된 빨강을 갚는 법)는 [LEDGER_GUIDE §3 ①](./LEDGER_GUIDE.md),
  기준은 [CANONICAL_LEDGER_DESIGN §4.3](../architecture/CANONICAL_LEDGER_DESIGN.md), 판정은 [LEDGER_RULINGS R-2026-08-15-M](../process/LEDGER_RULINGS.md).
- ⚠️ **낱말을 더해도 DDL은 0줄이다** — 그래서 **스키마 감시로는 영원히 안 잡힌다.** 집행 지점은 단위 테스트(`test_ledger_admin_setup.py`)다.
- ⚠️ **선언 파일이 깨지면 «통째로» 무시하고 코드 집합으로 내려간다** — 절반만 실린 어휘는 프로세스마다 다른 낱말을 인정하기 때문이다.
  그 강등은 조용하지 않다: `GET /admin/config/resolve?domain=ledger`가 사유와 함께 말한다.

---

## 5. 결함 종류 — 코드 기본값 + JSON 덮어쓰기

`server/finding_kinds.py`가 레지스트리다. **종류는 코드의 분기가 아니라 «조회»**이고, 그것이 이 파일이 존재하는 이유다
(숨은 `WHERE finding_kind='void'`는 **두 번째 종류가 도착하는 날에만** 드러난다).

**한 종류가 선언하는 것 — 넷 다 집행된다:**

| 필드 | 무엇 | 없으면 |
|---|---|---|
| `observed_by` | 🔴 **분모의 정의** — 이 종류를 «찾는» `inspection_run.method` 값들 | 🔴 **부재 ≠ 빈 목록.** 빈 것은 「분모 없음 — 대조 불가」라는 **결정**이고, 부재는 **로드 시점 거절**이다 |
| `observation_table` | 이 종류의 관측이 사는 곳 | 로드 시점 거절 |
| `extent_columns` | **얼마나 큰가**의 컬럼들 | 로드 시점 거절 |
| `classes` | 종류별 **닫힌 class 집합**(add-only). 관측 번역기가 **이 집합 밖의 값을 거절**한다 | 없으면 class 축이 없는 것(정상). 형식이 틀리면 거절 |
| `label` | 화면 이름 | 로드 시점 거절 |

**덮어쓰기 — `server/config/finding_kinds.json`(선택)**

- 있으면 **종류 «단위»로 코드 기본값 위에 병합**된다(`dict.update`) — 없는 종류를 **더할 수도 있다.**
- ⚠️ **이 저장소에는 `.sample`이 없다.** 이 박스에는 라이브 파일도 없어서 **오늘 레지스트리는 코드 기본값 둘(`void`·`delam`)로 돈다.**
- 🔴 **등급(합불)은 저장하지 않는다.** class는 「무엇인가」이고 등급은 「합격인가」이며, 임계는 레시피 파라미터다 — 굳혀 두면 이력을 다시 판정할 수 없다.
- 🔴 **종류를 더할 때 `observed_by`의 method는 기존 종류와 «달라야» 한다.** 공유하면 종류를 바꿔도 같은 런을 세게 되어
  **분모가 안 움직이고**, 종류 파라미터가 실제로 도는지 그 데이터로는 판별할 수 없다.

🔴 **완성 조건 미달 — §9 ②.**

---

## 6. 화면 층 선언 셋 — 없어도 답하고, 있으면 해상도가 올라간다

세 파일 전부 **부재를 «상태»로 답한다.** 500이 아니고, 부재를 빈 결과로 위장하지도 않는다.

### 6.1 `mechanism_models.json` — 「물리 경로 있음」 관문

- **최상위는 `__doc` · `bindings` · «그 밖 전부가 모델 하나»다.**
  ⚠️ **`models`라는 블록은 «없다»** — 문서 셋이 그렇게 적고 있었고 그것은 코드와 어긋난다(2026-08-15 정정).
  `signatures`는 **모델 «안»의 키**이고 **로더가 읽지 않는다**(사람용 문서).
- 모델 하나가 드는 것: `role`(`formation` \| `observation_bias`) · `finding_kind` · `target` · `nodes` · `edges`(**방향만** — `dir: '+'/'-'/'u'`. 🔴 **방정식은 일부러 없다**) · `version` · `validity`.
- **`bindings`** — `<술어>:<점 경로>` 또는 맨 경로 → 물리량. 🔴 **항목 목록이 아니다**: 바인딩 없는 후보도 대조에서 안 좁혀지고
  기전 칸에 **`unknown`을 달고 나온다**(갓 번역된 술어가 선언 0줄로 화면에 닿는다).
- 🔴 **바인딩은 «데이터가 실재하는 날» 켠다.** 화면을 완성돼 보이게 하려고 공백에 바인딩을 지어내지 마라.
- ⚠️ **`.sample`과 라이브를 «동일하게» 편집한다** — 추적되는 것은 `.sample`뿐이다.

### 6.2 `siblings_axes.json` — 요인 기하

- **블록**: `defaults` · `geometry` · `attribution[]` · `kinds`(종류별 덮어쓰기).
- `geometry` — 모집단 한 명이 무엇인지(`unit`·`unit_columns`)와 런 컬럼들, `ledger_subject`(모집단 ↔ 원장 주어의 다리), `universe`.
- `attribution[]` — 관계 하나마다 `{relation, about, label, key_column, join, axes[]}`이고, `axes[]` 한 항목이 축 하나다.
  🔴 **축을 더하는 것은 항목 하나이고 파이썬 0줄이다.**
- 🔴 **고카디널리티 방어는 «두 반쪽»이고 둘 다 필요하다**:
  - **선언된 반쪽 `rank: false`** — 그 축은 **SQL 전에** 요인 랭킹에서 빠진다(GROUPING SETS에 아예 안 들어간다).
    **식별자 축**(웨이퍼처럼 값마다 담지자 하나)에 붙인다. ⚠️ **마킹은 손대지 않는다** — `rank: false` 축으로도 계속 마킹할 수 있다.
  - **측정된 반쪽 `defaults.factors.high_cardinality_at`**(기본 200) — **SQL 뒤에** 걸리고, **아무도 표시할 생각을 못 한 축**을 잡는다.
    축을 지우지 않고 `ranked: false` + 사유로 남긴다.
- 모든 이름이 **SQL 식별자로 보간**되므로 **로드 시점에 식별자 검사**를 받는다(주입 가능한 선언은 요청이 닿기 전에 거절).
- ⚠️ **`siblings_axes.json.sample`의 `defaults.walk.__comment` 산문 하나가 코드와 어긋난다**(§11 보고 대상).

### 6.3 `ledger_journey.json` — 여정

- **블록 넷이고 «지웠을 때의 결과가 정반대»다**:
  - **`segments`** — 🔴 **구조적**이다. 어느 술어가 여정을 나르고 step 이름이 payload 어디에 있는지를 말하는 **유일한 것**.
    비면 응답은 `state: "absent"` · `reason: "no_journey_predicate_declared"` · **구간 0개**다.
  - **`step_labels` · `family_labels` · `field_labels`** — **아무것도 안 좁힌다.** 지워도 구간·항목·값은 그대로 나오고 **한국어만 잃는다**(원시 경로로 렌더).

**이름을 붙이는 법** (선언만이고 파이썬 0줄):

1. `server/config/ledger_journey.json`을 연다(라이브가 없으면 `.json.sample`을 복사해 만든다 — 응답의 `labels.origin`이 `live`\|`sample`\|`absent`로 **지금 어느 쪽을 읽고 있는지** 말한다).
2. 구간 이름은 `step_labels`에 `<step 값>: "본딩"`, 계열은 `family_labels`.
3. 항목 이름은 `field_labels`에 `<잎 이름>: "압력"` 또는 `{"label": "압력", "unit": "MPa"}`.
   **조회 철자가 셋이고 구체적인 것부터**다 — `<술어>:<점 경로>` → `<점 경로>` → **맨 잎 이름**.
   맨 잎이 기본값인 이유는 그 한 항목이 `params_actual.pressure_MPa`와 `params_setpoint.pressure_MPa`를 **동시에** 이름 짓기 때문이다
   (설정/실측 구분은 라벨이 아니라 **원자의 해결 등급**이 나른다). 같은 이름의 잎 둘이 **다른 물리량**일 때만 긴 철자를 쓴다.
4. **새 여정 술어를 붙이는 것은 `segments`의 항목 하나**다 — payload 안 어디에 step 이름과 계열이 있는지를 점 경로로 적는다.
   **거기에 선언이 없는 술어는 여정 축에 안 나타난다.**
5. 저장하고 **다시 요청한다** — 프로세스 수명 캐시라 서버 재기동 또는 `ledger_journey.load_config(force_reload=True)`가 필요하다.

- 응답을 읽는 법(빈칸 세 종류 등)은 [LEDGER_GUIDE §4.6-quater](./LEDGER_GUIDE.md).

---

## 7. 🚫 `ontology_mapping.json` — **새로 쓰지 마라**

- ⚰️ **R-2026-08-14-H로 옛 그래프 갈래가 은퇴했다.** 이 파일을 읽던 라우트들은 **410**으로 답하고(404가 아니다 — 「있었고 의도적으로 뺐다」),
  머티리얼라이저 워커는 프로세스 목록에서 빠졌으며 저장소는 DROP됐다.
- 🔴 **오늘 이 선언에 남은 유일한 살아 있는 독자는 쓰기 경로가 세우는 `needs_graph_rollback` 표지 하나이고, «그 표지를 읽는 것이 은퇴했다».**
  즉 **지금 이 파일을 쓰면 아무도 안 보는 불리언 컬럼을 흔드는 일만 한다.**
- ⚠️ **이 파일을 «authoring»하라고 아직 말하는 문서가 셋 있다** — [guide/config/ontology_mapping.md](./config/ontology_mapping.md) ·
  [CONFIG_GUIDE §3 S4](./CONFIG_GUIDE.md) · [CONFIG_ROLLOUT_GUIDE §3 ⑥](./CONFIG_ROLLOUT_GUIDE.md). **전부 은퇴 배너가 붙었다. 절차를 실행하지 마라.**
- **「그럼 온톨로지는 어디에 있나」** — 여기다. 오늘의 온톨로지는 **그래프 테이블이 아니라 원장의 어휘**(§4)이고,
  그림은 그 어휘에서 **생성**된다(`GET /api/ledger/structure`).

---

## 8. 🔴 무엇이 실물이고 무엇이 «제안»인가

[PHYSICS_ONTOLOGY_SETUP](../architecture/PHYSICS_ONTOLOGY_SETUP.md)은 **설계 문서이고 절마다 상태가 다르다.**
셋업 문서가 제안을 단계로 적으면 없는 문서보다 나쁘므로, **오늘 선언할 수 있는 것만** 여기 적는다.
(아래는 **2026-08-15 코드 실측**이고, 그 문서 헤더의 착지표보다 이 표가 새롭다.)

| 물리 층 | 오늘 | 셋업에서 뜻하는 것 |
|---|---|---|
| **WF 공정 원장**(`processed_with`) | ✅ **실물** | 어휘에 있다. 선언 없이 발화 가능 |
| **RCP 원장**(`Recipe` + `has_param`) | ✅ **실물** | 🔴 `rev`가 **키 재료**다 — 개정은 편집이 아니라 **새 등록** |
| **칩 이동**(`transferred`) | ✅ **실물** | `kind: "transfer"` 소스로 선언한다(§3.3). ⚠️ **PHYSICS §2-bis는 아직 「제안」이라 적고 있고 그것이 낡았다** |
| **메커니즘 그래프**(M4) | ✅ **실물** | `mechanism_models.json`이 실재하고 소비자가 둘이다(§6.1). ⚠️ **PHYSICS §4의 「제안」 표기도 낡았다** |
| **가상 소스 결선** | ✅ **실물** | `seed_syn_process_ledger.py` |
| **M1 구조(`BondLine`)** | 🟡 **제안** | **선언할 자리가 없다.** 구성형 개체는 여전히 `Die` 하나 |
| **M2 물리량 사전** | 🟡 **제안** | 물리량↔구조 종류의 타입 시스템은 코드에 없다 |
| **시나리오 S1~S3** | 🟡 **제안** | 재료(공정 원자·개정 diff·분모)는 있지만 **폴드·액션 산출이 없다** |
| **액션 노드**(`Action`·`applies_to`·…) | 🟡 **제안** | 어휘에 없다 |

🔴 **제안 행을 「아직 안 켠 단계」로 읽지 마라.** 켤 스위치가 없다 — **어휘 등재라는 판정**이 먼저다(§4).

---

## 9. 🔴 완성 조건에 «아직 못 미치는» 자리

> 완성 조건(소유자 상설): **다른 스키마의 운영 환경에서 코드 0줄, 선언 교체만으로 발화한다.**
> 아래 셋은 오늘 그 조건을 못 만족한다. 이 문서가 그것을 숨기지 않는 것이 이 절의 전부다.

**① ✅ [2026-08-15 — 절반이 닫혔다] 어휘의 «온톨로지 층»은 이제 선언이다. 남은 절반은 개체 타입과 넷째 문법.**
🔴 **[R-2026-08-15-M · 소유자 판정] 답은 「전부 연다」가 아니라 «층으로 가른다»였고, 그대로 착지했다:**

| 층 | 판정 | 오늘 |
|---|---|---|
| **정준**(`register`·`pin`·`same_as`) | 🔴 **코드 + 판정. admin은 읽기 전용이고 화면에서 늘릴 수 없다** — 기록의 문법이 조용히 자라면 원장이 원장이 아니게 된다 | ✅ 코드(화면에 문 없음이 테스트로 고정) |
| **온톨로지**(세계의 언어) | ✅ **선언으로 append-only 확장 허용** — 단 **서명이 완결돼야 저장된다** | ✅ **착지**(`ledger_vocabulary.json` · §4) |
| **개체 타입**(`ENTITY_TYPES`) | (판정 대상 아님) | 🔴 **여전히 코드** — 아래 ①-bis |

- 🔴 **삭제는 판정에서도 금지다** — `status: retired` + `superseded_by`만 가능하다(원자가 이미 그 낱말로 누워 있다). 라우트에 DELETE가 0개임을 테스트가 단언한다.
- 🔴 **v0 고정 집합 테스트는 유지된다** — 못 박는 것은 «코드가 싣는 집합»(`PREDICATES`)이고, 선언 확장분은 합쳐진 뷰(`all_predicates()`)로 합류하며
  응답과 구조 뷰가 **출처(`origin: code|config`)를 구분해 표시**한다. **「선언으로 늘었다」가 눈에 보인다.**

**①-bis 남은 간극 둘.**
- **개체 타입은 여전히 코드다.** 다른 스키마의 배포가 새 «주어»를 필요로 하면(예: `Cassette`) 파이썬을 고쳐야 한다.
  술어와 달리 개체 타입은 **신원 키의 정의**라 서명 완결 검사로 안전해지지 않는다 — 열려면 자기 판정이 필요하다.
- **넷째 문법 `derivation`(R-M ⑤)은 번역기가 없다.** 판정만 났고, `GET /admin/ledger/sources`가 그것을
  `unsupported_kinds`에 **사유와 함께** 실어 화면이 「못 한다」가 아니라 「아직 안 왔다」로 읽히게 한다.
  결과적으로 **오늘 선언으로 등재한 술어를 발화할 번역기가 없다** — `/admin/config/resolve?domain=ledger`가 그 낱말을
  「효과없음: 발화하는 번역기 없음」으로 이름 대어 보고한다.

**② 결함 종류는 절반만 열려 있다.** 종류의 **정의**는 `finding_kinds.json`으로 덮어쓸 수 있지만,
**모집단·런의 «주소»는 코드 상수**다 — `PACKAGE_TABLE = "bonding_log"` · `PACKAGE_COLUMNS = ("base_id","bx","by")` · `RUN_TABLE = "inspection_run"`.
🔴 **패키지를 다르게 주소 지정하는 fab은 이 세 상수를 고쳐야 한다.** 같은 사실을 `siblings_axes.json.geometry`는 **선언으로** 들고 있어
(같은 모집단을 config가 말하는 자리가 이미 있다), 여기는 **선언 채널이 있는데 안 쓰는 자리**다.

**③ 선행 테이블 이름 몇 개가 선언 밖에 있다.** 관측 문법의 `run.relation`은 선언이지만(✅),
분모 규율의 다른 소비자들은 `finding_kinds.RUN_TABLE`을 통해 **같은 상수**를 본다.

⚠️ **그리고 규칙 하나가 «두 벌로 철자돼» 있다** — 「스캔됨 MINUS 발견됨」(3분할)이
`finding_kinds.population_ctes`와 `ledger_siblings.py`에 각각 조립돼 있다. **둘은 오늘 동의하고, 갈라지는 날을 탐지하는 것이 없다.**
(분리에는 이유가 있다 — 화면 쪽은 런을 시간 창으로 좁히고 `found ⊆ scanned`를 유지해야 한다.)

---

## 10. 검증 — 무엇을 보고 「됐다」고 하는가

| 묻는 것 | 어떻게 | 답의 뜻 |
|---|---|---|
| **표가 생겼나** | `GET /api/ledger/coverage`의 `state` | `absent` = 마이그레이션 미실행 · `empty` = 백필 미실행 · `ready` = 추적 가능 |
| **거절이 있었나** | 같은 응답의 거절 집계 | ⚠️ **`refusals_unaccounted`는 «부호»가 계약이다** — `0` 정상 · **`> 0`은 배포 이력이지 결함이 아니다**(컬럼이 생기기 전에 세어진 거절) · `< 0`만 진짜 장부 결함 |
| **원자가 말이 되나** | `GET /api/ledger/trace?...` | 🔴 **빈 `hops`는 가능한 답이 아니다** — 끊긴 홉과 그 이유가 답이다 |
| **선언이 화면에 닿았나** | `GET /api/ledger/structure` | 어휘에 없는 모양은 **버려지지 않고 `undeclared`로 뜬다**. `atoms: 0` ≠ `atoms: null` |
| **종류가 원장에 있나** | `GET /api/ledger/kinds` | 분모(`observed_by`) 유무까지 답한다 |
| **테스트** | [LEDGER_GUIDE §3 ⑥](./LEDGER_GUIDE.md)의 명령 | 🔴 **PostgreSQL 절반은 기본 실행에서 «건너뛰어진다»** — skip 수를 반드시 읽을 것. 파이썬은 전부 conda `assy_manager` |

🔴 **재실행으로 「안 변한 것」을 확인하려 하지 마라.** 커서 전진 재실행은 **0행을 읽어 아무것도 증명 못 하고**,
`--reset-cursor` 재실행은 선언이 바뀌었으면 **중복이 아니라 새 원자**를 쓴다(§2 ⑥ 각주 · [LEDGER_GUIDE §4.3](./LEDGER_GUIDE.md)).

---

## 11. ⚠️ 이 문서가 알면서 남겨 둔 것

- **`OPERATOR_RUNBOOK §6`이 마이그레이션·백필 명령을 한 벌 더 들고 있다.** 그 파일은 **총괄 전담**이라 손대지 않았다.
  🔴 **그 §6은 번역 소스를 «셋»이라 적고 `dt_log`가 빠져 있다** — 총괄 정정 대상.
- **`siblings_axes.json.sample`의 `defaults.walk.__comment`가 「행을 지우지 않고 주석만 단다」고 적는데,
  코드는 VALUE 행을 후보에서 «뺀다».** config 파일이라 손대지 않았다 — 총괄 정정 대상.

---

## 관련 문서

| 문서 | 무엇 |
|---|---|
| [architecture/CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md) | **WHY** — 원자 7필드, 두 어휘, 해결 서열, 확장 순서 |
| [architecture/PHYSICS_ONTOLOGY_SETUP](../architecture/PHYSICS_ONTOLOGY_SETUP.md) | **WHY(물리)** — 4계층·기전 그래프·시나리오·액션 노드. 🔴 **제안이 섞여 있다 — §8을 먼저 읽을 것** |
| [guide/LEDGER_GUIDE](./LEDGER_GUIDE.md) | **HOW(코드)** — 모듈 지도·쓰기 경로·번역기 작성·백필 숫자 읽는 법·롤백 |
| [spec/LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md) | **EXACTLY-WHAT** — 컬럼·CHECK·인덱스·응답 계약·실패 모드 |
| [process/LEDGER_RULINGS](../process/LEDGER_RULINGS.md) | **판정** — 여기 없는 판정은 내려진 적이 없다 |
| [process/OPERATOR_RUNBOOK](../process/OPERATOR_RUNBOOK.md) | **운영 실행 기록** — 무엇을 운영에서 실제로 돌렸는가(§4 관측 테이블 켜기가 이 문서 §2 ②의 정본) |
| [guide/CONFIG_GUIDE](./CONFIG_GUIDE.md) | **config 전수 지도** — 이 문서 밖의 선언들 |
