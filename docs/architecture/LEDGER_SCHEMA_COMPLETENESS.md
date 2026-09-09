# 원장 선언 스키마 완전성 (S-75) — 축 × 칸

> **Status:** 🟢 Living | **Written:** 2026-09-09 05:4x (응용, 판정 161·162 · 아침 초인종 09-09 05:32) | **Owner:** 응용
> **축의 정본은 [`BASIS.md`](./BASIS.md)** — 이 문서는 그 축에 «칸»을 채운다. 축이 여기서 새로 나오면 BASIS 를 고치고 한 줄 남긴다.
> **문법의 정본은 `server/ledger/setup_bundle.py`** — 아래 모든 줄은 그 파일과 `roleframe.py` · `schema.py` 에 대고 잰 것이다.
> 🔴 **스키마 동결(09-12)의 관문 = «유도»다(판정 167): 「모든 칸 ← 생성자 인자」 ∧ 「모든 생성자 인자 → 칸」. 검사는 맨 아래 §D-1·D-2. ③ 개수는 «작업량»이지 관문이 아니다.**
> 🔴🔴 **동결 문장은 이 문서에서 «네 번» 고쳐졌습니다. 오늘 참인 것은 «§D-9» 하나입니다** — D-4(09:46) · 정정 절(16:0x) · D-6-6(18:0x) · D-7-5(18:2x) 는 «그때의 문장»이고 기록으로 남깁니다. 고칠 때마다 바뀐 것은 «세는 법»이지 술어가 아닙니다(판정 167 → 196).
> 규율: 문서 먼저 → `git grep` 검증 · 라이브 config 수 ⛔(샘플·문법만) · 칸을 «지어내지» 않는다.

## 0. 이 표를 읽는 법 — 칸의 «상태» 넷

```
①   선언 칸이 있다             이름과 자리를 적는다
②   기본값이 덮는다            🔴 「없음」이 아니라 «무엇으로» 덮이는지 «값»을 적는다
③   없다 = 결함               동결 전에 채운다. 「무엇을 적을 자리인가」를 한 줄로
③′  칸은 있는데 «읽는 쪽»이 0    축이 «덮이지» 않는다 — 적어도 아무 일도 안 난다
     🔵 **판정 165: ③′ 도 관문에 «센다».** 근거는 상설 둘 — 「착지는 배선이 아니다」(소비자 0 인 축은
        없는 축) · 「닿을 수 없으면 선언도 닿지 않는다 — 자유도 0 인 선언은 계약이 아니라 사본」(2026-08-20).
        표시는 «유지»한다: ③ 은 «짓는» 일이고 ③′ 는 «은퇴시키는» 일이라 수리가 다르다
```

### 값의 정의역은 «일곱 층» 다 본다 (판정 09-08 22:23)
`문법`(setup_bundle) · `발행`(roleframe/emit) · `걷기`(ledger_subgraph) · `폼`(ledger_skeleton.json) · `값 채움`(bind) · **`DB CHECK`**(schema.py) · `클라 투영`.
**한 층이 좁으면 그 칸은 ③ 이다** — 문법이 문자열을 받아도 발행이 수만 받으면 그 칸은 문자열을 못 든다.

---

## 1. A1 — 노드(엔티티)

| 부축 | 상태 | 칸 · 자리 | 값의 정의역 (좁히는 층) | 읽는 쪽 |
|---|---|---|---|---|
| 타입 | ① | `entities.<type>` — id 는 `^[^@/\s]+@[1-9][0-9]*$` (`setup_bundle.py:90` `_VERSIONED_ID`, 검사 :1096) | 문자열 | 걷기 노드 `type` · 폼 |
| 정체성 `keys` | ① | `entities.<t>.keys` :1123 — 비지 않은 목록 · 중복 ⛔ :1126 | **값 = `_scalar`**(`roleframe.py:1328`): 문자열 · 정수 · 유한 실수 · 불. null 은 `allow_null` 일 때만 :1289 → 🔵 **「keys 가 수여도 되나」 ✅ 된다.** 목록 ❌ | 원자 `subject_keys` JSONB · 노드 id · label |
| `key_types` | 🔴 **③′** | `entities.<t>.key_types` :1129~1145 — 이름이 `keys` 와 «정확히» 일치해야 함 | 값 = trimmed 비지 않은 문자열. **타입 이름의 목록이 닫혀 있지 않다** | 🔴 **없다.** 검증기(:1129) · 폼(`ledger_skeleton.json:183`) · 레지스트리 «보관»(`setup_registry.py:168,:906`) 셋뿐. 시험·문서·아카이브를 뺀 «값을 읽는» 자리 `git grep` **0** |
| `allow_null` | ① | `entities.<t>.allow_null` :1163 | 불 | `roleframe.py:1289` |
| `class` | ① | `entities.<t>.class` ∈ {static, dynamic} :1121. 없으면 dynamic — 🔵 «안 적힌 것»과 «dynamic 이라 적은 것»을 가르려고 기본값을 «안 쓴다»(:1112 주석) | 닫힌 둘 | 걷기 — 정적 노드에 «닿되 나가지 않음» |
| 속성 — 이름 | ① | `entities.<t>.attributes` :1147 — 목록 · 중복 ⛔ · **keys 와 이름 충돌 ⛔** :1160 | 이름 = 문자열 | `predicate_claim` :531~537 이 목적어 없는 술어의 optional qualifier 로 올린다 |
| 속성 — 값 | ① 자리 / 🔴 **③ 정의역** | `sources.<s>.bind.entities.<t>.attributes.<name>` = `column`\|`constant` (:1821~1850). 역할 층 override 는 `…bind.<role>.attributes` :1425 | 🔴 `attribute` 역할 → `_scalar` → **스칼라 «하나»**. 목록 ❌ · 객체 ❌ · 시각 ❌. DB 는 JSONB 라 목록을 «담을 수는» 있는데 발행이 거절한다 — 층이 어긋난 자리 | 원자 `object_payload.qualifiers` · CHECK `ck_ledger_objectless_carries_only_qualifiers`(`schema.py:99`) · 걷기 노드 `attributes` · 클라 |
| 속성 — 복수값 | 🔴 **③** | 위 정의역의 귀결. 「이 웨이퍼의 product 가 «둘»」을 적을 자리가 없다 — 두 값은 «충돌»로 읽힌다(걷기 `attribute_conflicts`) | — | — |
| 존재 — 등록 | ② | 🔴 **술어 이름이 «고정»이다: `register`.** 선언이 못 바꾼다 — `REGISTER_PREDICATE`(`config_authoring.py:101`) · DB CHECK `ck_ledger_register_has_no_object`(`schema.py`) · 부분 인덱스 `WHERE predicate = 'register'`(`store.py:117,:129`) | — | 셋 다 |
| 존재 — 첫 목격 | ① | `sources.<s>.read.registration_probe[]` = `{entity_type, columns, list_separator?}` :1526~ | 목록 · 물리 컬럼 이름 | 드라이버가 페이지마다 store 에 묻고 «중복 register 를 억누른다» |
| 존재 — **은퇴** | 🔴 **③** | `entities.<t>` 의 optional 목록 :1119 = `(key_types, allow_null, references, class, attributes)` — **`status` 가 없다.** 술어에는 있다(A2) | — | — |
| 시간(속성 변경) | ① | 새 등록 원자. 걷기가 최신 `occurred_at` 을 이기고 서로 다른 값의 수를 `attribute_conflicts` 로(`WALK.md` §4) | — | 걷기 · 클라 |
| 표면 `label` | ② | 🔴 선언 칸이 «없다» — `ledger_subgraph.py:384` 가 **`keys` 앞 «둘»을 `" / "` 로 이어** 만든다. 비면 타입 이름 | — | 화면 |
| `references` | ① | `entities.<t>.references` :1165 — 키 하나가 다른 엔티티를 가리키면 걷기가 «엣지를 합성»한다 (:1169) | | 걷기 |

---

## 2. A2 — 엣지(술어)

| 부축 | 상태 | 칸 · 자리 | 값의 정의역 (좁히는 층) | 읽는 쪽 |
|---|---|---|---|---|
| id | ① | `vocabulary.<p>` versioned :1037 | 문자열 | |
| `status` | ① | ∈ {active, retired} :1052 | 닫힌 둘 | 작성 폼이 retired 를 후보에서 뺀다(`config_authoring.py:1253`) |
| `subjects` | ① | :1054 비지 않은 목록 | 엔티티 타입 id | |
| `object.kind` | ① | `OBJECT_KINDS = {none, entity_ref, value, event_ref}` :130, 검사 :1058 | 닫힌 넷 | DB CHECK `ck_ledger_object_kind` 는 «셋» — `none` 이 NULL 로 접힌다 |
| `object.types` | ① | `entity_ref` 일 때만 «필수», 그 밖엔 «금지» :1061~1070 | 목록 | |
| `qualifiers.required`/`optional` | ① 자리 | :1071~1092 — 겹침 ⛔ · `none` 목적어는 payload qualifier ⛔ | 🔴 값 = `attribute` 역할 → `_scalar` → **문자열 ✅ · 수 ✅ · 불 ✅ / 목록 ❌ · 객체 ❌ · 시각 ❌** | 원자 payload · 걷기 엣지 수식어 |
| **값 목적어의 타입** | 🔴 **③** | 🔴 **칸이 없다.** `_OBJECT_VALUE_ROLE_KINDS = {"value": "quantity", "event_ref": "identity"}`(`setup_bundle.py:468`) 가 «코드에서» 정한다 | 🔴 `quantity` → **JSON 수 only · 유한 · 불 ⛔**(`roleframe.py:1302~1309`). **문자열 값 목적어를 «선언할 자리가 없다»** — 소유자가 물은 「수식어에 숫자만 되는 것 아니냐」의 실제 자리다: 수식어는 «되고», 값 목적어가 «안 된다» | |
| `occurred_at` | ① | `sources.<s>.read.occurred_at` = `{timezone 필수, column?, basis?}` :1513~1525 · `basis` ∈ `{"ingested"}` (`_OCCURRED_AT_BASES` :135) | 시각 «순간» 하나 | 원자 `occurred_at` TIMESTAMPTZ · 월 파티션 키 · CHECK `ck_ledger_occurred_at_basis` |
| **유효 구간** | 🔴 **③** | 순간 하나뿐 — 「언제부터 언제까지 참」을 적을 칸이 없다 | — | — |
| **카디널리티** | 🔴 **③** | `vocabulary` 에 칸 없음. ⚠️ `virtual_joins.<r>.join_cardinality` 는 «있다» — 다른 선언 언어에만 | — | BASIS §3 대로 B5 집계의 «중복 셈»을 구조적으로 못 막는다 |
| 방향 | ① | 주어→목적어 «고정». 걷기는 양방향, 같은 술어 반전 ⛔ | | 걷기 |
| **supersede** | 🔴 **③′** (컬럼은 ①) | 컬럼 `supersedes UUID` 있고 검증도 있다(`ledger_frame.py:282`) · CHECK `ck_ledger_no_self_supersede`. 🔴 **쓰는 자리가 `roleframe.py:1520` 의 `"supersedes": None` «하나»** — 비-null 을 쓰는 코드는 `server/_archive/profile_chain_mapper.py:209` 뿐이고 «오늘 트리에서 안 돈다». 즉 「정정」을 선언으로 시킬 자리가 없다 | | 읽는 쪽 넷(subgraph · trace · frame · dry_run) |

---

## 3. A3 — 값

| 부축 | 상태 | 칸 · 자리 | 정의역 |
|---|---|---|---|
| value 목적어 | 🔴 **③** | A2 「값 목적어의 타입」과 «같은 칸» — 수만 | |
| **단위** | ② | 선언 칸이 없다 — 수식어 «이름»(`unit` 같은)으로 «약속»한다. 스칼라라 값과 단위가 «두 칸»이 된다 | 스칼라 |
| null | ① | 엔티티 키는 `allow_null`, 그 밖의 역할 값은 «null 금지»(`roleframe.py:1261`) | |

---

## 4. A4 — 소스

| 부축 | 상태 | 칸 · 자리 | 정의역 |
|---|---|---|---|
| `relation` | ① | `sources.<s>.relation` :1470 — 표 «또는 뷰» | 카탈로그(`table_config.json`)에 있는 이름 |
| 표/뷰 갈래 | ① | 카탈로그의 `kind` ∈ {table, view}, 오타는 «경로 대어» 거절(:250~255) | 닫힌 둘. `view` 면 `row_id` 를 «안 심는다» |
| `read.unit` | ① | {row, group} (`_SOURCE_UNITS` :131) · row 는 `group_by` 빈 목록, group 은 «하나 이상» :1494~1500 | 닫힌 둘 |
| `read.identity` · `order_by` | ① | :1489 비지 않은 목록 · `group_by` ⊆ `identity` :1501 | 컬럼 이름 |
| `read.cursor` | ② | 🔴 **더 «묻지 않는다»** — `order_by` 에서 «파생»된다(`_derived_cursor` :557, :1483 주석). 파일에 남아 있으면 «삼킨다»(`ignored=("cursor",)`) | |
| `prepare` · `map` | ① | :1248~1327 — `implementation_id`/`_version` · `input_columns` · `output_columns` · `unit.kind` ∈ {event, row, group_by} | 닫힘 |
| `bind.mappings.<문장>` | ① | `{predicate, bind:{역할→바인딩}}` :1372~1382 | 바인딩 kind ∈ {column, constant, entity} :1389~1400 |
| `bind.entities.<t>.attributes` | ① | :1821~1850 — 소스당 «한 번»(판정 124) | column\|constant. entity ⛔ (:1846 — 「엔티티 값 속성은 엣지가 옷을 갈아입은 것」) |
| **결정 단위** `decision_key` | 🔴 **③** | 🔴 **원장 선언에도 표 카탈로그에도 없다.** 실측: 카탈로그 항목의 키 = `{business_key, column_types, composite_key_separator, composite_key_source, display_columns, kind, map_key_columns, workspace_name}` (샘플 44 표 전수). ⚠️ **`decision_key` 는 «다른 선언 언어»에 산다** — `enrichment_rules.json` 의 규칙마다(`enrichment_config` · `alignment_view_service.py:53` · `chain_bindings.resolve_decision_column`). 🔵 **판정 165: 이름은 «같게» 둔다** — 뜻이 같고 «범위»만 다르다(규칙의 판단 단위 / 표의 판단 단위). 관계를 적는다: 규칙 칸이 있으면 규칙 · 없으면 표 · 둘 다 없으면 «이름 대어 거절» | 목록(컬럼들) |
| 삭제 겨눔 | ① | `ledger_source_row_ref` (`schema.py:69`, 키 `(relation, row_id, source_who, source_raw_ref)`) · `backfill.sources_without_row_index` :915 · `index_existing_refs` :936 · `withdraw_deleted_rows` :1056 | |
| 삭제 — row_id 없는 뷰 | ② | 🔵 «이름 대어» 남는다 — `sources_without_row_index` 가 그 소스를 «센다». 뷰가 base 의 `row_id` 를 흘려 주면 그 뷰는 겨눌 수 있다(:246 주석, 샘플 뷰 10 중 5) | |
| 🔴 **행 선택·제외** (S-91, 09-09 17:10 **닫힘**) | ✅ **①** | `sources.<s>.prepare.exclude_when: [{column, blank:true}]` — 검증 `setup_bundle.py:1351` `_validate_exclude_when` · 미지 컬럼은 :1903 에서 이름 대어 거절 · `direct-join` 이 아닌 준비기에는 :1913 이 「그 준비기는 이것을 안 읽는다」로 거절 · 레지스트리 `setup_registry.py:310` · 읽는 곳 `source_preparation.py:459` · 스켈레톤 `:576`(폼이 그림) · 출하 샘플 `:1781`. ⚠️ **착지 전 상태를 기록으로 남깁니다** — 기제는 있었으나 «파이썬 준비기»만 냈습니다 — `SOURCE_ROW_EXCLUDED_COLUMN = "__source_row_excluded"` (`source_preparation.py:47`), `setup_bundle.py` 에 «0회». 소유자 실측(09-09 15:59): 신원 키 부품이 빈 행 «하나»가 전부-아니면-전무로 995 행을 막습니다. ⚠️ 출하 카탈로그 주석이 2026-08-23 에 «이미» 이 자리를 적어 뒀습니다(「the only row-exclusion mechanism … is emitted by a preparer implementation」) | 목록(조건) |
| **소스 은퇴** | 🔴 **③′** (09-09 18:2x 정정) | ⚰️ 옛 판정(「`exact` 가 `status` 를 거절한다 — 적을 수 없다」)은 «낡았습니다». 오늘 `setup_bundle.py:1611` 이 `optional=("status",)` 이고 값도 검증됩니다(:1617, `{active, retired}`). 🔴 그러나 «읽는 쪽이 없습니다** — 엔티티·소스 서술자에 `status` 필드가 없어 레지스트리에 안 실립니다(술어는 실리고 `roleframe.py:1381` 이 읽습니다). 적어도 아무 일도 안 일어납니다. 자세히 D-7-6 | |

---

## 5. A5 — 선언 자체

| 부축 | 상태 | 칸 · 자리 |
|---|---|---|
| `setup_version` | ① | 루트 `setup_version`, 오늘 `SETUP_VERSION = 5` (`setup_bundle.py:20`) |
| 지문 | ① | `source_translator_ver = f"ledger-v2:{snapshot_sha256}#{sentence}"` (`roleframe.py:1422,:1517`) — 🔵 «세대 표지»가 원자의 «신원 안»에 이미 있다(`DEDUPE_COLUMNS` `schema.py:71`) |
| 커서 지문 | ① | `f"ledger-v2:{source_cursor_fingerprint(...)}"` (`setup_registry.py:853`) — 한 자리 |
| **세대**(born/retired · 되돌림) | 🔴 **③** (S-57) | 리비전을 «이름 지어» 고르거나 되돌릴 칸이 없다. 지문은 «달라졌음»만 말하고 «어느 세대인가»를 못 말한다 |
| **변경 비용 미리보기** | 🔴 **③** | 「이 선언 diff 로 몇 행이 · 어느 소스가 · 얼마나 다시 도나」를 «바꾸기 전»에 답하는 자리가 없다. 있는 것은 «돌린 뒤» 세는 쪽(`retroactive` 세기 먼저 · `rescope`) |
| 실행 금지 | ① | `_FORBIDDEN_DECLARATION_KEYS`/`_FORBIDDEN_EXECUTABLE_KEYS` :91~100 — 선언에 코드가 못 들어온다 |

---

## 6. A6 — 출처(봉투) · A7 — 변경 동사 · A8 — 이력

| 부축 | 상태 | 자리 |
|---|---|---|
| 봉투 다섯 칸 | ① | `_outbox_envelope()` (`server/database/database.py:189`) = `(transaction_id, user, source, ts, chain_depth)` — **한 자리**라 접힌 사건과 행별 사건이 «갈라질 수 없다» |
| 파일 신원 → 데이터 행 | ① | `filename_rules` — 🔴 **자리 정정: 표 카탈로그가 «아니다».** 인제스터 선언(`AdvancedIngester(config_path)` 가 읽는 파일)의 세 계열 중 하나다(`advanced_ingester.py:180~186`). 주어는 «인제션 루트 기준 POSIX 상대경로»라 폴더명까지 본다(:267~) · 병합 서열 «경로 < 헤더 < 행». ⚠️ 출하 샘플에 이 계열을 쓰는 선언 **0** — 「관행의 부재」이지 결함이 아니다(판정 159) |
| **봉투 없는 쓰기** | 🔴 **③** (D1) | 표에 직접 쓰는 스크립트는 세션을 안 지나 봉투가 «없고», 그래서 `write⁻¹` 도 없다 |
| CREATE · EDIT · DELETE | ① | `CHAIN_OWNED_EVENT_TYPES = {"CREATE","EDIT","DELETE"}` (`event_constants.py:82`) · 접힘은 `row_ids` 로(:372) · DELETE 는 «접히지 않는다»(:362 — 지워진 행은 다시 못 읽는다) |
| SYSTEM_RELOAD · RETROACTIVE_RUN | ① 사건 / 🔴 **③** 원장 | 사건은 있다(`event_constants.py:28,:43`). 🔴 **원장이 그것을 «사실»로 안 읽는다** — A5 「세대」와 같은 구멍의 다른 끝 |
| **외부 응답** | 🔴 **③** | 싱크로 보낸 명령의 «답»이 봉투 사건으로 돌아오는 동사가 없다 |
| append-only · 월 파티션 | ① | `PARTITION BY RANGE (occurred_at)` (`schema.py` `CREATE_LEDGER` 끝) |
| 표 «전체»의 버전/브랜치 | ② | 🔵 **설계 선택이지 결함이 아니다** — 우리 이력의 단위는 «사실»(원자의 occurred_at)이고 파운드리는 «데이터셋 버전»이다(소유자 정정 09-08 08:3x, `ledger_declaration_by_example.md` §1) |

---

## 7. ③ 목록 — 「무엇을 적을 자리인가」 한 줄씩

```
③  «열하나»
 A1-1 엔티티 은퇴          「이 타입은 더 안 쓴다」 — 술어의 status 와 «같은 모양»이면 족하다
 A1-2 복수값 속성           「이 이름은 값을 «여럿» 든다」 — 오늘은 목록을 넣으면 발행이 거절하고, 두 값은 «충돌»로 읽힌다
 A2-1 값 목적어의 타입       「이 술어의 값은 «문자열»이다」 — 오늘 코드가 quantity 로 못 박아 수만 받는다 (= A3 value 목적어, 한 칸)
 A2-2 유효 구간            「언제부터 언제까지 참」 — 오늘 «순간» 하나뿐
 A2-3 카디널리티           「이 술어는 주어당 «하나»」 — 없으면 집계가 중복을 셀 수 있고 아무도 안 막는다
 A4-1 결정 단위 decision_key 「이 표의 판단 단위는 이 컬럼들」 — 판정 151 이 여는 칸.
                          ⚠️ enrichment 규칙의 «같은 이름»과 뜻이 갈리지 않게
 A4-2 소스 은퇴            「이 소스는 더 안 읽는다」 — 오늘은 «지우는 것»뿐이고 exact 검증이 다른 키를 전부 거절한다
 A5-1 세대 (S-57)          「이 리비전이 어느 세대이고 어디로 되돌리나」
 A5-2 변경 비용 미리보기      「이 diff 는 몇 행이 · 어느 소스가 · 얼마나 다시 도나」 — «바꾸기 전»에
 A6-1 봉투 없는 쓰기 (D1)    「표 직접 쓰기도 봉투를 단다」 — 없으면 그 쓰기에 write⁻¹ 이 없다
 A6-2 외부 응답 동사         「보낸 명령의 답이 사건으로 돌아온다」
 A7-1 선언 사건이 원장 사실 아님  「세대가 바뀌었다」를 원장이 «사실»로 안 읽는다 — A5-1 과 «같은 구멍의 다른 끝»
                          (별도로 세지 않는다 — 위 열하나에 A5-1 로 든다)
```
```
③′ «둘» — 칸은 있는데 «읽는 쪽»이 0
 A1-3 key_types           키의 «타입»을 적게 해 놓고 아무 층도 안 읽는다. 고치는 길이 «둘»이라 판정이 필요하다:
                          ㉠ 읽는 쪽을 만든다(정의역 검사 · 정렬 · 범위 질의)   ㉡ 칸을 은퇴시킨다
 A2-4 supersedes          「정정」의 컬럼 · 검증 · 읽는 쪽 넷이 다 있는데 «비-null 을 쓰는 선언 칸»이 없다:
                          ㉠ 선언이 정정을 시킬 자리를 연다   ㉡ 칸 은퇴 — 정정의 정본은 «철회 후 재작성»(backfill withdraw/remake)
```

## 8. 판정 165 — 관문의 셈법과 이름 (2026-09-09 05:48, 닫힘)

```
㉠ ③′ 도 «센다»                 => 표 A 의 관문 수는 «13» (③ 11 + ③′ 2)
   근거는 상설 둘: 「착지는 배선이 아니다」(소비자 0 인 축은 없는 축) ·
                 「닿을 수 없으면 선언도 닿지 않는다 — 자유도 0 인 선언은 계약이 아니라 사본」(2026-08-20)
   🔴 수리는 둘 다 «은퇴»다:
     A1-3 key_types    칸 «삭제» — 검증기 · 스켈레톤 · 레지스트리를 «같은 커밋»에.
                       (표 B1 의 씨앗 해소도 키 «타입»을 안 쓴다 — 아래 표 B 에서 확인됨)
     A2-4 supersedes   「정정의 정본 = withdraw / remake」로 «선언 은퇴».
                       컬럼 · CHECK 는 마이그레이션 라운드까지 «쓰는 자 0» 으로 유지
㉡ `decision_key` 는 «같은 이름 유지» — 뜻이 같고 «범위»만 다르다(규칙의 판단 단위 / 표의 판단 단위)
   관계를 «적는다»: 규칙 칸이 있으면 규칙 · 없으면 표 · 둘 다 없으면 «이름 대어 거절»
                  (판정 151 「기본값 없음」 그대로)
   🔴 이름을 둘로 «가르는» 것이 오히려 두 뜻을 만든다
```
### 수리 순서 — 소유자 몫 (총괄 권고, 판정 165)
```
동결 «안»(스키마 칸) «일곱»    A2-1 값 목적어 타입 · A4-1 decision_key · A5-1 세대 ·
                           A1-1 엔티티 은퇴 · A4-2 소스 은퇴(둘은 술어 status 와 «같은 모양») ·
                           A2-3 카디널리티 · A1-2 복수값 속성
동결 «밖»(기본값을 «적고» 미룸)  A2-2 유효 구간(기본 = 순간) · A5-2 변경 비용 미리보기(D4 도구) ·
                           A6-1 봉투 없는 쓰기(D1 규율 + 가드) · A6-2 외부 응답(기본 = 없음)
```

## 9. 닫힘 검사 — 지난 열흘의 발견 넷이 어느 칸인가 (BASIS §6 ①)

```
S-52 속성        A1 「속성 — 이름 · 값」        ✅ ① 로 착지. 정의역만 ③(복수값)
S-50 결정 단위    A4 「결정 단위」              ✅ ③ 으로 «자리가 있다». 판정 151 이 그 칸
S-57 세대        A5 「세대」                  ✅ ③
S-65-d 뷰 삭제   A4 「삭제 — row_id 없는 뷰」   ✅ ② («이름 대어» 남는다)
=> 넷 다 칸이 있다. 축이 «빠지지» 않았다
```

## 10. 두 줄이 서나 (BASIS §6 ⑤)

```
✅ 「운영에서는 그 표를 sources 에 한 벌 적고(relation · read · prepare · map · bind),
    엔티티에 keys 와 attributes 이름을, 술어에 subjects 와 object 를 적으면 됩니다」
⚠️ 서지 «않는» 자리 둘 — 둘 다 위 ③ 이다:
   · 값이 «문자열»인 술어를 두 줄로 못 적는다(A2-1) — 수식어로 «돌려» 적어야 한다
   · 표의 판단 단위를 두 줄로 못 적는다(A4-1)
```

---
---

# 표 B — 걷기 스킴 (질의 공간)

> 축의 정본 `BASIS.md` §3. **소비자 정본 `WALK.md` 를 «먼저» 열고 `GET /api/ledger/subgraph` 시그니처로 검증했다** (`server/ledger_trace_router.py:84~163`).
> 제약(상설): 「사용자가 고르는 축은 노드 타입 «하나», 술어는 follow 로만」 — **배관 낱말이 축으로 «새로 생기면» ③ 이 아니라 «위반»이다.**
> 🔴 아래 셋은 BASIS §3 의 「오늘」 칸이 «낡아» 있었다: B2 반전(미확인→착지) · B3 짐(③→①) · B6 대조(③→대부분 ①). BASIS 를 고쳤다.

## B1 시작 · B2 길 · B3 짐

| 축 | 상태 | 인자 · 자리 | 정의역 |
|---|---|---|---|
| B1 마킹 | ① | `id`(별칭, 항상 positive) + `positive[]` + `negative[]` (`ledger_trace_router.py:85,:95,:97`) · 합치는 자리는 `_signed_start` :166 «하나» | 노드 id 문자열 |
| B1 이름 붙은 마킹 «여럿» | ② | 🔴 라우트는 «한 번에 한 질의»다. 「마킹1 · 마킹2」는 «클라의 저장소»가 들고 부품이 각자 걷는다 — 서버는 «부호 두 갈래»만 안다 | |
| B1 씨앗 해소 | ① / ⚠️ | 키 → 노드. ⚠️ `/declaration` 이 `wafer@1` 로 알려 주는데 그 철자로 씨앗을 만들면 «빈 그래프»다 — `wafer` 여야 한다(WALK.md §6 · 큐 C-25). 클라는 `entitySeedId` 가 벗겨서 안 걸린다 | |
| B2 `follow` | ① | `follow[]`, `이름:키1,키2` 로 «목적지 키» 제약까지 :99~103. 없으면 «전부» | 🔴 선언된 술어만 — 아니면 **422 `predicate_not_declared`** + `unknown`/`declared` 집합 :146 |
| B2 `direction` | ① | `outgoing|incoming|both` :88 | 닫힌 셋(FastAPI pattern) |
| B2 `hops` | ① | 1–40, 기본 12 :86 | |
| B2 **인접 반전 규칙** | ① | 🔵 **착지 확인** — `arrivals` 가 노드마다 `(술어, incoming|outgoing)` 을 들고(:917,:1135), 같은 술어로 들어온 뒤 «되짚어 나가는» 걸음을 :1130~1133 에서 거절한다. ⚠️ 정적↔정적은 «예외» — 원인으로 되짚어 다른 결과로 가는 것이 «묻고 있는 차이»라서(:1124~1129, 실측 21 중 2) | |
| B2 정적→동적 정책 | ① | `class == static` 인 노드에 «닿되 나가지 않는다» :1071~1072 | 선언의 `class`(A1) |
| B3 `collect` | ① | `collect[]` :104~109 — 도메인 «노드 타입». 없으면 전부. `@` 버전은 있어도 없어도 됨 | 🔴 선언된 타입만 — 아니면 **422 `node_type_not_declared`** :131 |

## B4 그룹 · B5 집계 — 🔴 둘 다 ③

| 축 | 상태 | 근거 |
|---|---|---|
| B4 `group_by` | 🔴 **③** | 라우트 인자에 없다. `git grep 'group_by'` — `ledger_subgraph.py`·`ledger_trace_router.py` 히트 **0**. 오늘 «클라가» 묶는다 |
| B5 `measure` · `aggregate` · `n` | 🔴 **③** | 같음 — `aggregate`/`measure` 의 히트는 전부 «주석의 낱말»이고 인자가 아니다 |
| B5 «사용자 수식» (BASIS §4.8 의심 ②) | 🔴 **③** | 집계 축 자체가 없으므로 그 정의역도 없다. 「수율식·규격 판정을 사용자가 적는다」를 받을 칸이 «0» — 이것이 `compute : G × D_formula → G` 가 «다섯째 생성자»인지 묻는 자리다 |

🔴 **그리고 이 둘이 ③ 인 것은 «성능»의 문제이기도 하다** (BASIS §3 마지막 줄): 클라가 묶으면 걷기가 «전부»를 실어 와야 하고, 10⁸ 에서는 예산 절단이 «먼저» 온다. 잘린 표로 센 집계는 «기울어진 답»이고 오류를 안 낸다.

## B6 대조 — 🔴 BASIS 가 ③ 이라 적었는데 «대부분 ①» 이다

| 축 | 상태 | 자리 |
|---|---|---|
| 대조군의 정의 | ① | `negative[]` = 「봤는데 안 난 주어」 :97. 🔵 **없으면 `contrast: "unexamined"`** — `_propagation` :666~668 이 「대조군을 안 걸었다」를 «0 으로 보고하지 않는다» |
| 모집단 | ① | «닿은 노드 전부». 소유자 판정 2026-08-28 — 한 타입으로 거르면 «더 좁은 질문»에 답하게 된다(:640~648). `collect` 는 «짐»만 거르고 순위는 전부 본다 |
| 집계(분모) | ① | `reach[i] / reachable[i]` «쌍»으로 나간다 — 분모는 「그 후보의 «타입»에 한 번이라도 닿은 씨앗 수」 :679~697 |
| 동률 | ① | `_rank_layers` — 지배(dominance) 순, **동률은 동률로 남고**, 각자 한 축씩 이기면 `incomparable` 로 «표시»한다 (판정 2026-08-23 「동률은 답이지 실패가 아니다」) |
| 절단이 대조를 «기울이는지» | ① | `propagation.complete` :671~674 — 예산이 걸음을 끊은 후보는 «부재»가 아니라 «미검사». 실측(2026-08-23) 랏 씨앗 넷이 기본 상한에서 잘린다 |
| **두 수를 «접는» 규칙** | 🔴 **③** (의도된 자리) | :649~657 이 «스스로» 적어 둔다 — 「접는 규칙이 아직 없고, 여기서 지어내면 그 발명이 답을 정한다」. 판정이 나면 «그 자리»가 이 함수다 |
| **분모가 «항목» 단위** | 🔴 **③** | :690~695 이 스스로 적어 둔다 — 분모가 «타입»이라, 열여섯 개를 잰 대조군은 «안 잰 항목»에 대해서도 0/2 로 읽혀 «진짜 차이처럼» 보인다 |

## B7 시간 · B8 예산 · B9 출력 · B10 거절

| 축 | 상태 | 자리 |
|---|---|---|
| B7 as-of · 구간 · 세대 선택 | 🔴 **③** | 라우트에 시각 인자가 «없다» — `git grep 'as_of|asof|as-of' -- server/ledger_api/ server/ledger_trace_router.py` 히트 **0**. 항상 «최신» + 속성 충돌 «수». 🔴 그래서 BASIS §4.4 의 「walk 은 멱등」이 **말해지지 않는다** — 「같은 시각」을 적을 칸이 없다 |
| B8 예산 | ① | `node_limit` 10–1000(기본 400) · `edge_limit` 20–MAX(기본 1200) · `backbone_hops` 0–40 «별도 예산» :89~94,:104 |
| B8 절단 «표시» | ① | 응답 `truncated = {depth, nodes, edges, claims, actions, reason}` :1405~1409 — 축 다섯 + «사유» |
| B9 노드 | ① | `{id, type, label, keys, attributes}` — `attributes` 는 선언된 이름만 · 최신 `occurred_at` 승 · «닿지 않은» 이름은 `null` 이 아니라 **키가 없다** · `attribute_conflicts` 는 「서로 다른 값이 둘 이상인 «이름의 수»」(WALK.md §4, 판정 123·124) |
| B9 엣지 | ① | `{source, target, predicate, qualifiers}` |
| B9 그 밖 | ① | `seeds`(부호) · `propagation` · `walk`(모드·방향·씨앗 부호 수·`hops_reached`) · `limits` · `truncated` |
| **B11 근거 동반** (BASIS §3-0) | 🔵 **엣지 ① / 순위 트레일 ⚠️** | **엣지**: 원자에서 온 엣지는 `claim_id`(= `atom.id`)와 `basis`(= `atom.source_raw_ref`)를 «답니다» (`ledger_subgraph.py:996~999`), 그리고 응답은 `ordered_edges = sorted(edges.values(), …)` :1361 로 «투영 없이» 그대로 나갑니다 — 즉 「어느 원자가 이 엣지를 받쳤나」는 **이미 실립니다**. ⚠️ `WALK.md` §4 는 엣지를 `{source,target,predicate,qualifiers}` «넷»으로 적어 두었습니다 — **문서가 코드보다 좁습니다**(고칠 것). 🔴 **순위 트레일은 그것을 «안 씁니다»**: `_evidence` :565~593 의 hop 은 `atom`/`ref` 를 «노드»에서 읽는데(`nodes[item].keys.id` · `source_raw_ref` · `basis`), `_entity_node` :375 는 «셋 다 없습니다» — 엔티티 키는 도메인 키(wafer·x·y)라 `id` 가 없습니다. 그래서 **엔티티 홉의 `atom`·`ref` 는 «전부 null»** 이고, 걷기의 노드는 사실상 전부 엔티티입니다. 즉 순위는 「어느 길로 닿았나」는 말하고 「어느 «사실»이 그 걸음을 받쳤나」는 못 말합니다. 🔵 그런데 그 사실은 «같은 응답 안»에 있습니다 — 트레일이 «노드»가 아니라 «두 홉 사이의 엣지»를 보면 `claim_id`·`basis` 가 거기 있습니다. 잇는 일이지 «짓는» 일이 아닙니다 |
| B11-bis 엣지의 «빈» 근거 칸 | 🔴 **③′** | `_edge()` :388~394 가 매 엣지에 `sources: []` · `witnesses: 1` · `rank: None` 을 답니다. `git grep` 으로 이 셋에 «쓰는» 자리 «0**(시험·다른 뜻의 동명이인 제외) — key_types·supersedes 와 «같은 부류»입니다 |
| B10 거절 | ① 대부분 | «이름 대어» 넷: `predicate_not_declared` · `node_type_not_declared` · `subgraph_request_invalid` · 관계 부재. 범위·열거는 FastAPI 가 422 |
| B10 «조용한 불가» | 🔵 **0 (이 라우트에서는)** | 선언에 없는 술어·타입을 «빈 그래프»로 답하지 않는다 — :117~129,:143~152 가 그 이유를 적어 두었다(「오타와 사실을 부르는 쪽이 못 가른다」) |

## B1-bis — 🔴 마킹 «대수»는 없다 (BASIS §4.8 의심 ① 의 답, 서버 쪽)

```
마킹이 라우트에 닿는 «유일한» 모양   질의 문자열의 «노드 id 목록» — `id` + `positive[]` + `negative[]`
                                 합치는 자리는 `_signed_start`(ledger_trace_router.py:166) 하나
서버가 «마킹»을 아는가             🔴 모른다. `git grep marking -- server/ --include=*.py` 에서
                                 이 뜻의 히트 «0» (나머지는 「~로 표시한다」 같은 다른 낱말이다)
                                 => 마킹을 «이름 지어 저장»할 자리도, 이름으로 부를 자리도 없다
```
| 연산 | 오늘 | 왜 |
|---|---|---|
| ∪ 합집합 | ⚠️ «부르는 쪽»이 목록을 이어 붙이면 된다 | 연산이 «이름을 갖지 않는다» — 그래서 「마킹1 ∪ 마킹2」가 요청에서 «안 보인다» |
| ∩ 교집합 · ∖ 차집합 | 🔴 **③** | 걷기가 못 한다. 부르는 쪽이 «id 를 다 들고» 계산해야 한다 |
| 부호 반전 | 🔴 **③** | `positive`/`negative` 를 바꿔 넣는 것은 «부르는 쪽»의 일이고, 서버에 그 연산이 없다 |
| `negative[]` 가 차집합인가 | ❌ **아니다** | «둘째 부호 집합»(대조군)이다. 차집합으로 읽으면 「한 이름 두 뜻」이다 — `_propagation` 이 «두 도달을 나란히» 내는 것이 그 증거 |

🔴 **그리고 이것이 «규모»의 문제인 이유** — 대조군의 자연스러운 정의가 「전체 ∖ 사례」인데,
그것을 오늘 방식으로 쓰려면 **«전체»를 id 목록으로 실어 보내야 한다.** 원자 10⁸ 규격에서 그 목록은
질의 문자열에 안 들어간다. 즉 «클라에서 하면 된다»가 **규격 안에서 참이 아니다.**
=> BASIS §4.8 의심 ①의 답: **M × M → M 은 오늘 «없고», 부르는 쪽으로 미룰 수도 «없다».**
   합성 규칙 여섯째로 열지 «지을지»는 B4·B5·B6 을 서버로 옮기는 판정과 «같은 자리»다(판정 대기).
📎 클라 쪽 전수(C-46 · 판정 164)도 같은 결론에 닿았다 — 「∩ 기제만 · 선언 비어 · ∪ ∖ 부호 반전 0」.
   **양쪽이 각자 재서 같은 답이 나왔다.**

## B12 — 빈칸 «진위»: 「참인가」를 묻는 연산자 (BASIS §3-0 ⓐ)

| 부축 | 상태 | 근거 |
|---|---|---|
| **진위 검사** | 🔴 **③** | 「이 술어가 이 주어에 대해 참인가」를 묻는 연산자가 «없습니다». 걷기는 하위 그래프를 «주고», 참/거짓은 부르는 쪽이 «보고» 정합니다 |
| ⚠️ 가장 가까운 것 | ② | `state: "ready" \| "empty"` (`ledger_subgraph.py:1380`) — 「이 걷기가 «무언가»를 찾았나」입니다. «이름 붙은 술어»의 검사가 아니라 «걷기 전체»의 존재이고, 둘은 다른 물음입니다 |
| ⚠️ 둘째로 가까운 것 | ② | `propagation.contrast: "contrasted" \| "unexamined"` — 「대조를 «했나»」이지 「그것이 «참인가»」가 아닙니다 |
| 🔴 이것이 무엇을 막나 | | BASIS §4.3 의 가드 `walk ⊳ write` — 「걷기 결과의 술어가 참일 때만 쓴다」가 «서버 연산자»로 없습니다. 그래서 랏 홀드/이송의 가드가 클라 판단이 되고, 그 사이 상태가 바뀌면 «이미 거짓인» 가드로 씁니다 = 표 C 의 C-2(조건부 쓰기)와 «한 몸» |

## B13 — 「빈칸의 종류 → 연산자」 대응 (준동형의 조건, BASIS §3-0 ⓑ)

> 소유자 물음 「근본 기저와 제품 기저가 동형이야?」에 대한 «칸 단위» 답. **동형이 아니라 준동형입니다** — 일곱 중 셋만 연산자가 온전합니다.

| 빈칸의 종류 | 물음 | 오늘의 연산자 | 상태 |
|---|---|---|---|
| **정체** | 「어느 것인가」 | `resolve`(K→M) · `collect`(노드 타입) | ① |
| **값** | 「값이 무엇인가」 | 노드 `attributes` · 엣지 `qualifiers` | ① |
| **차이** | 「무엇이 다른가」 | `propagation`(부호 대조 · 동률 · `complete`) | ① 대부분 (B6 — 접는 규칙·항목 분모만 ③) |
| **수** | 「몇인가」 | ⚠️ «고정 배율»만: 노드마다 `claim_count` · `predicates[{predicate, count}]` (:1285~1293) | ⚠️ 세는 «자리»는 있고 «고를 수» 없음 — 선언 가능한 집계는 ③ (B5) |
| **원인** | 「왜 그런가」 | 엣지의 `claim_id`·`basis` ✅ / 순위 트레일은 «인용 못 함** | ⚠️ (B11 — 한 조인 차이) |
| **시각** | 「그때는 어땠나」 | (없음) | 🔴 ③ (B7) |
| **진위** | 「참인가」 | (없음) | 🔴 ③ (B12 — 새로 나온 것) |

```
🔵 준동형의 «조건»을 이 표로 말하면:
   질문 기저의 «빈칸 종류» 일곱  ->  제품 기저의 «연산자»
   온전히 대응 셋(정체·값·차이) · 부분 둘(수·원인) · 대응 «없음» 둘(시각·진위)
=> 제품 기저는 질문 기저를 «보존하지만 전사(onto)가 아닙니다». 그것이 「동형이 아니라 준동형」의 실물입니다
🔴 그리고 §3-0 ↔ §3 의 빈 자리 «넷» 중 셋(시각 · 마킹 대수 · 순위 근거)은 이미 이 문서에 있고,
   «진위» 하나가 이번에 새로 나왔습니다 — 그래서 표 B 의 ③ 은 «여섯»에서 «일곱»이 됩니다
```

## 표 B 의 ③ — «일곱»

```
 B1-1 마킹 대수 (M × M → M)   「마킹1 ∖ 마킹2 를 걸어라」 — ∪ 는 이름이 없고 ∩ ∖ 부호반전은 «없다».
                            🔴 부르는 쪽으로 미룰 수 없다(위 규모 논거)
 B4-1 group_by              「이 걷기 결과를 «이 타입/속성»으로 묶어라」
 B5-1 measure · aggregate    「무엇을 · 어떻게 세라」(수 · 비율 · 평균 · 분포)
                            정의역에 «사용자 수식»(D_formula)이 들어가야 한다 — BASIS §4.8 의심 ②.
                            🔵 답: 오늘 «없다». 다섯째 생성자 `compute` 인지는 판정
 B6-1 접는 규칙              두 수(사례 reach / 대조 reach)를 한 점수로 — 코드가 «자리를 비워 두고» 기다린다
 B6-2 항목 단위 분모          오늘 분모가 «타입»이라 «안 잰 항목»이 진짜 차이처럼 읽힌다
 B7-1 시간(as-of · 구간 · 세대)  「그때의 사실로 걸어라」 — 없어서 walk 의 «멱등»이 말해지지 않는다
 B12-1 진위 「참인가」          술어를 «검사»하는 연산자 — 가드(walk ⊳ write)가 이것을 쓴다
```
⚠️ **B5-2(사용자 수식)는 B5-1 의 «정의역»이라 같은 칸으로 센다.** 그래서 여섯이다.

## BASIS §3 정정 «셋» (그 문서 자기 규칙대로 고쳤다)

```
B2 반전 규칙   「착지 미확인」        -> 🔵 착지 «확인» (arrivals :917,:1135 · 거절 :1130~1133)
B3 짐 collect  「③ — 축째 지워짐」    -> 🔵 ① (라우트 인자 :104 · 422 :131 · 화면 체크박스)
                                     ⚠️ WALK.md §6 이 «이미» 닫힘으로 적고 있었다 — BASIS 만 낡아 있었다
B6 대조        「③ — 순위표가 클라」  -> 🔵 «대부분 ①» (부호 씨앗 · propagation · 동률 · complete 가 서버에 있다)
                                     남는 ③ 은 «접는 규칙»과 «항목 분모» 둘
그리고 «추가»   B1 에 「마킹 대수」 부축이 없었다 -> BASIS §3 B1 에 한 줄 넣었다
```

## 표 B 의 판정 대기 «하나»

```
㉢ B4 · B5 · B6 을 «서버로» 옮기나 (그리고 B1-1 마킹 대수를 «같이» 여나)
   옮겨야 하는 근거   BASIS §3 이 이미 적었다 — 클라가 묶으면 걷기가 «전부»를 실어 와야 하고
                    10⁸ 에서는 예산 절단이 «먼저» 온다. 잘린 표로 센 대조는 «기울어진 답»이고 오류를 안 낸다
                    그리고 위 B1-bis — 「전체 ∖ 사례」를 id 목록으로 실을 수 없다
   ⚠️ 제 의견을 «내지 않습니다»  이건 라운드 하나가 아니라 «제품의 축»이고,
                    「우선순위」는 소유자 몫이라 총괄이 올릴 자리입니다.
                    다만 재 본 것은 적습니다: 오늘 ③ 여섯 중 «다섯»(B1-1 · B4-1 · B5-1 · B6-1 · B6-2)이
                    이 판정 «하나»에 걸려 있습니다. 남는 하나는 B7(시간)이고 그건 A5 세대와 같은 줄입니다
```

---
---

# 표 C — 행동 기저 (대수)

> 축의 정본 `BASIS.md` §4(대수). 열은 판정 162 대로 「이 행동이 §4.5 꼴로 «어떻게 적히나» · 봉투가 있나 · 안 적히면 «무엇이» 빠졌나(생성자 / 규칙 / 정의역)」다 — «기능 이름»이 아니다.
> 행의 재료: **서버 라우트 전수 117**(`main.py` 97 + `ledger_trace_router` 4 + `ontology_config_explorer_router` 16, `@app.`/`@router.` 실측) + **클라 손짓 전수**(C-46 `a5e6cdc0` — 리스너 260 · 액션 낱말 44).
> 🔴 낱개 117 행을 적지 않는다 — 「부류로 묶되 구성원은 «센다»」(상설). 부류마다 수를 적고, **대수에 안 적히는 것은 이름으로 «전부»** 적는다.

## C-0. 서버 라우트 117 이 §4.5 꼴로 어떻게 갈리나

| # | §4.5 표기 | 수 | 봉투 | 대표 구성원 |
|---|---|---|---|---|
| 1 | «기저 밖» — 표현(§4.8 직교) | **12** | — | `/` · `/admin(.html)` · `/map-editor(2)(.html)` · `/enrichment(.html)` · `/{file_name:path}` · `/api/download/client` · `/api/desktop/download` |
| 2 | `resolve` : K → M | **1** | — | `GET /api/ledger/key-values` |
| 3 | `walk` : M × D_walk → G | **15** | — | `subgraph` · `gaps` · `maps/overlay` · `alignment/{view,worklist,references}` · `transfer-plan/{stages,source-summary}` · `bonding-plan/core-summary` · `maps/{paint-rules,preset-routing}` · `map-presets`×2 · `enrichment/rules`×2 |
| 4 | 🔴 **읽기 — 표 행(R)** | **15** | — | `GET /tables` · `/tables/{t}/data` · `/data/count` 제외 · `/export` · `/schema` · `/columns/{c}/values` · `/{row_id}` · `/rows/{row}/history` · `/cells/{col}/history` · `/{row}/{col}/sources` · `/audit_logs/recent` · `/audit_logs/transaction/{tx}` · `/dashboard/summary` · `/api/effort/config` · **POST 둘**(`cells/sources/query` · `row_ids/target` — 몸통으로 «묻는» 읽기) |
| 5 | 선언 «읽기» | **6** | — | `GET /api/ledger/declaration` + 탐색기 다섯(`view` · `refusals` · `columns` · `authoring/schema` · `authoring/plan`) |
| 6 | 시스템 운영 읽기 (기저 D) | **20** | — | `/health` · `chain/queue` · `outbox/failed` · `file-ingestion/{logs,failed,active,workspaces}` · `mappers/list` · `config/resolve` · `ledger/{sources,relations,config/raw}` · `tables/config/raw` · `chain/rules(/raw)` · `retroactive/{operations,runs}` · `auto-update/status` · `scripts/{list,code}` |
| 7 | 🔴 **미리보기** — `write` 를 «효과 없이» | **10** | — | `admin/ledger/dry-run` · `transfer-plan/dry-run` · `transfer-plan/validate` · `retroactive/{op}/count` · `enrichment/auto-confirm/dry-run` · `config/virtual-join/verify` · `config/notation/preview` · `tables/{t}/data/count` · 탐색기 `deletion-preview` · 탐색기 `test-run` |
| 8 | `write` : (G\|입력) × D_write → E | **14** | ✅ 세션 경유 | `PUT /tables/{t}/data/updates` · `POST /tables/{t}/rows` · `DELETE /tables/{t}/rows/{row}` · `rows/batch_delete` · `upload` · 셀 소스 `DELETE`·`delete/batch` · 우선순위 `PUT`×2 · `map-presets` `POST`×2·`DELETE`×2 · `maps/alignment/confirm` |
| 9 | `declare` : D × ΔD → D' | **12** | 부분 | `POST /admin/{tables/config,chain/rules,scripts/code}/raw` + 탐색기 아홉(`drafts` · `drafts/new` · `PUT drafts/{id}` · `review` · `revise` · `activate` · `DELETE drafts/{id}` · `DELETE declarations/{key}` · `bootstrap`) |
| 10 | 사건 «주입» — E 를 직접 넣음 | **11** | 부분 | `internal/events/{batch-refresh,broadcast,file-processed,ingestion-state}` · `outbox/retry-failed` · `file-ingestion/retry-failed` · `reload-configs`(SYSTEM_RELOAD) · `retroactive/{op}/run`(RETROACTIVE_RUN) · `retroactive/runs/{id}/cancel` · `auto-update/{toggle,run-now}` |
| 11 | `E ↦ write(D_sink)` — 실시간 전파 | **1** | ↑8 을 따름 | `WEBSOCKET /ws` |
| | **합계** | **117** | | |

🔵 **클라 쪽은 C-46 이 같은 표기로 이미 갈라 놓았다** — §4.5 꼴 «여덟»(1 resolve · 2 resolve;walk · 3 walk 인자만 · 4 병렬;diff · 5 write 봉투 보임 · 6 write 봉투 못 봄 · 7 declare;translate · 8 사건 연쇄) + 밖 «셋»(표현 · 폼 상태 · 창 사건). 두 전수가 «따로» 재서 부딪히지 않는다.

## C-1. 🔴 이 표의 핵심 발견 — 「같은 «성질»이 생성자마다 따로 지어졌다」

```
미리보기(효과 없이 결과만)   write 에 «있다»   라우트 10 + `apply=False` 인자 «열하나»
                                          (chain_replay ×4 · enrichment ×3 · backfill ×3 · migrations ×1)
                          declare 에 «없다»  = 표 A 의 A5-2 「변경 비용 미리보기」 ③
조건부 쓰기(내가 본 대로면 써라)  declare 에 «있다»  `expected_revision`
                                          (`config_drafts.py:392,408,446,477,497` · 탐색기 라우트 :235)
                                          커서에도 있다(`backfill.py:383,397` — translator_ver 대조)
                          write 에 «없다»   표 행에 compare-and-set 이 «0». 동시 사용자 10 규격에서
                                          마지막 쓰기가 조용히 이긴다
```
🔴 **둘 다 «생성자의 성질»인데 §4.2 가 그것을 성질로 안 적어서 «한쪽에만» 지어졌다.**
그리고 우리는 그 둘을 «따로» 발견해 왔다 — A5-2 를 「없는 것을 짓는다」로 읽고 있었는데,
실은 **「있는 패턴을 다른 생성자에 붙인다」**이다. 🔵 **변경 비용이 다르다**(상설 D8).

=> 제안(짓지 않음, 한 줄): §4.2 의 각 생성자에 «성질» 둘을 붙인다 —
   `preview(f)` : f 의 효과 없이 E 를 «예상»한다 · `f ⊳ expected(s)` : 본 상태와 같을 때만 f.
   그러면 「어느 생성자에 없나」가 표의 «칸»이 되고, 지금처럼 라운드마다 하나씩 안 나온다.

## C-2. 🔴 대수가 «타입을 안 준» 것 — 표 행 읽기 (15 라우트)

```
오늘 대수    walk : M × D_walk → G       G = 하위 그래프
실제        GET /tables/{t}/data 는 R(표 × 행)을 «페이지»로 돌려준다 — G 가 아니다
           resolve 도 아니다(K → M 은 «마킹»을 낸다)
=> §4.6 (c) 「오늘의 모든 라우트가 4.5 꼴로 적히나」에 «15 개가 안 적힌다»
```
🔴 **그리고 이것이 제품에서 가벼운 자리가 아니다** — 그 15 개가 «교정 표면»(핵심가치 ①)이다.
대수가 그 표면의 «쓰기»는 타입을 주고 «읽기»는 안 준다.
```
가능한 답 둘 (판정 대기 — 제 의견은 ㉡)
 ㉠ walk 의 공역을 넓힌다     G ∪ R.  「표도 그래프의 한 투영」이라는 주장이 필요하다
 ㉡ 다섯째 생성자 read : K × D_read → R
    근거: 이미 «다른 선언 언어»가 그것을 정하고 있다 — table_config 의 column_types ·
    display_columns · business_key · virtual_join_rules. D_read 는 «지어낼 것»이 아니라 «이미 있다»
```

## C-3. 표 C 의 ③

```
 C-1 미리보기가 생성자의 «성질»이 아니다      write 에만 있다. declare 에 붙이는 것이 A5-2
 C-2 조건부 쓰기가 «성질»이 아니다            declare 에만 있다. write 에 없다 — 동시 사용자 10 에서 마지막 쓰기 승
 C-3 표 행 «읽기»에 타입이 없다               15 라우트가 4.5 꼴로 안 적힌다
 C-4 외부 응답 사건                          = 표 A 의 A6-2 «같은 칸». 싱크의 답이 E 로 안 돌아온다
 C-5 마킹 대수 M × M → M                     = 표 B 의 B1-1 «같은 칸». 서버·클라 전수가 «따로» 같은 답
 C-6 write⁻¹ 의 «주어»가 화면에 없다           판정 164 ⓐ — `created_logs[].transaction_id` 가
                                           «응답에 있는데» 그리드가 안 읽는다. 대수의 역원은 «있다»
```
⚠️ **C-4 · C-5 는 표 A · B 와 «같은 칸»이라 관문에 두 번 세지 않는다.** 표 C 가 «새로» 여는 것은 **넷**(C-1 · C-2 · C-3 · C-6).

## C-4. 시험 문제 셋 — 랏 홀드 · 해제 · 이송 (판정 162 추가분)

```
표기   홀드   resolve ; walk ⊳ write(D_transition) ↦ E ↦ write(D_sink)
      해제   같은 표기, 전이가 반대 방향
      이송   resolve ; walk ⊳ write(D_transition) — 가드가 「진행 중 이송 없음」
```
| 필요한 것 | 생성자인가 선언인가 | 오늘 |
|---|---|---|
| 상태 표(랏의 현재 상태) | **선언** — 표 하나 + `attributes` | ① 이 이미 있다(A1 속성). 「상태」는 도메인 낱말이라 코드에 안 들어간다 |
| 허용 전이 표 | **선언** — 표 하나(from · to · 역할) | ① 표를 만들면 된다. 새 문법 ⛔ |
| 가드 술어 | **선언** — 걷기의 `follow`(B2) | ① |
| 가드가 «참일 때만» 쓴다 | 🔴 **생성자의 성질** | §4.3 의 `walk ⊳ write` 는 «대수에 있는데», 그것을 «원자적으로» 하려면 C-2(조건부 쓰기)가 필요하다 — 걷고 나서 쓰는 사이에 남이 바꾸면 가드가 «이미 거짓»이다 |
| 바깥 장비/MES 에 알리고 «답»을 받기 | 🔴 **생성자/규칙** | C-4(외부 응답 사건) |
🔵 **그래서 판정 162 추가분의 답:** 랏 운영 셋은 «선언 셋»으로 분해된다 — 생성자가 늘지 «않는다».
   다만 **가드의 «원자성»과 «외부 답»** 둘은 선언이 아니라 «생성자의 성질»이고, 그 둘이 C-2 · C-4 다.
   즉 소유자 물음(「나중에 랏 운영 액션이 필요해지면」)의 답: **표 셋만 적으면 된다. 단 C-2 가 먼저다.**

## C-5. 판별식 ⓐ ⓑ 의 답 (BASIS §4.6)

```
ⓐ 「모든 행동이 넷으로 분해되나」
   🔴 아니오 — 117 중 «15»(표 행 읽기)가 안 적힌다(C-3). 그 밖의 102 는 적힌다.
   ⚠️ 「기저 밖」 12(표현)와 시스템 운영 20 은 §4.8 · 기저 D 가 «이미» 밖이라 적어 둔 것이라 위반이 아니다
ⓑ 「임의 조합이 허용되거나 «이름 대어» 거절되나 — 조용한 불가 0」
   🔵 걷기(표 B10)에서는 «0» — 선언에 없는 술어·타입을 빈 그래프로 답하지 않는다
   🔴 쓰기에서는 «아니다» — 조건부 쓰기가 없어서(C-2) 「내가 본 상태가 바뀌었다」가
      «거절»이 아니라 «덮어쓰기»로 끝난다. 조용한 불가가 아니라 «조용한 허용»이고, 더 나쁘다
```

## C-6. 동결 관문 — 🔴 «수»가 아니라 «유도»다 (판정 167, BASIS §2.6 말미)

판정 167 이 관문의 술어를 바꿨다: 「③ 이 0」이 아니라
**「문법의 모든 칸이 어느 생성자의 인자로 «유도»되고, 모든 생성자의 인자가 «칸»을 갖는다」.**
그래서 아래 수는 «관문»이 아니라 «작업량»이다.

```
표 A  ③ 11 + ③′ 2   = 13   (판정 165)   -> BASIS §2.6 이 이것을 성격별로 다시 갈랐다:
                                          문법 수리 «다섯»(①②③④⑤, ③④는 패턴 하나) ·
                                          읽기 규칙 «셋» · 술어 한 줄 · 사건 둘 · 도구 하나 · 삭제 둘
표 B  ③ 6                                -> §3.5: «진짜 구멍»은 시각(as-of·세대)과 M 대수 둘.
                                          group·aggregate·diff 는 «자리»의 문제(생성자는 있다)
표 C  ③ 6 중 둘(C-4·C-5)은 A·B 와 같은 칸  -> 새로 여는 것 «넷»(C-1·C-2·C-3·C-6)
```
🔴 **그리고 이 표가 관문의 술어에 대해 말하는 것:**
```
「모든 생성자의 인자가 칸을 갖는다」 쪽    C-3 이 그 반대다 — 15 라우트가 «어느 생성자의 상(image)도 아니다».
                                    read : K × D_read → R 을 인정하든 walk 공역을 넓히든, 그 전에는
                                    이 관문이 «참일 수 없다». 수를 0 으로 만들어도 참이 안 된다
「모든 칸이 인자로 유도된다」 쪽          C-1 · C-2 는 «칸»이 아니라 «성질»이다. 성질로 적으면
                                    A5-2 가 «따라온다» — 낱개로 세면 그것이 안 보인다
```
⚠️ **표 A 를 §2.6 의 열로 «다시 적는 일»이 남았다**(그 절이 응용에게 맡긴 것). 이번 라운드에는 «안 했다» —
다음 라운드의 첫 줄이고, 그때 표 B 도 §3.5 열로 같이 맞춘다.

## C-7. 표 C 의 판정 대기 «둘»

```
㉣ C-3 표 행 읽기의 타입 — ㉠ walk 공역 확장 vs ㉡ 다섯째 생성자 `read`
   제 의견 ㉡ — D_read 를 «지어낼» 필요가 없다(table_config 가 이미 그 선언이다)
㉤ C-1 · C-2 를 §4.2 의 «생성자 성질»로 올리나 (`preview(f)` · `f ⊳ expected(s)`)
   올리면 A5-2 가 「짓기」에서 「붙이기」로 바뀐다 — 변경 비용 상설(D8)에 걸리는 판정이다
```

---
---

# 유도 검사 — 판정 167 의 관문 (2026-09-09 06:0x)

> 판정 167 이 관문의 술어를 바꿨다. **「③ 이 0」이 아니라**
> **「모든 «칸»이 어느 생성자의 인자로 «유도»된다」 ∧ 「모든 «생성자 인자»가 칸을 갖는다」.**
> 그래서 이 절은 표 A · B 를 그 «두 방향»으로 다시 읽는다. 위의 표 A · B 는 «재고»로 그대로 두고 — 그것이 이 절의 `git grep` 증거다.
> 기저의 정본은 `BASIS.md` §2(표기 대수) · §3(질의 대수).

## D-0. 🔴 §2.6 의 대응에서 «틀린 자리» 둘 (판정 167 ① 이 물은 것)

### ㉠ ⑨ 「노드 은퇴 = retire 술어 한 줄 → 선언 한 줄, 문법 무변」 — **오늘 거짓이다**

```
문법     OBJECT_KINDS 에 "none" 이 있다 -> `retire@1` 을 목적어 없는 술어로 «선언할 수 있다»  ✅
발행     predicate_claim 이 목적어 없는 문장을 만든다                                        ✅
🔴 DB    CONSTRAINT ck_ledger_register_has_no_object CHECK (
             (predicate = 'register') = (object_kind IS NULL))          schema.py:140~141
         «동치»다. predicate='retire' 이고 object_kind IS NULL 이면  거짓 = 참  ->  거절
         그리고 저장되는 predicate 는 «맨이름»이다(`_runtime_id` roleframe.py:1242~1250 이 @1 을 벗긴다)
근거     그 파일이 스스로 적어 두었다 — 「makes that legal for `register` and for nothing else,
         in BOTH directions - a register with an object and a non-register without one are equally refused」
         (schema.py:20~24)
```
🔵 **그래서 ⑨ 는 「선언 한 줄」이 아니라 «마이그레이션 하나»다.** 일곱 층 중 «여섯»이 통과하고 DB 가 거절한다 —
정의역 열이 잡으라고 만들어진 바로 그 모양이다.
🔴 **그리고 이것은 표 A 의 A1 ② 를 «더 강한 문장»으로 바꾼다:**
```
전에 적은 것   「등록 술어의 «이름»을 선언이 못 바꾼다」(register 로 고정)
실제로 참인 것  「목적어 없는 술어가 «하나»여야 한다」 — 둘째를 선언하면 DB 가 그 원자를 거절한다
```
⚠️ 수리의 «모양»은 제 판정 밖이다(총괄). 다만 갈래는 둘이고, 하나는 막다른 길이다:
```
㉠ CHECK 의 목록에 이름을 «더한다»       -> 저장 층에 도메인/선언 낱말이 는다. 다음 술어에 또 마이그레이션
㉡ CHECK 를 «성질»로 바꾼다              -> 「목적어 없음은 선언이 정한다」. CHECK 는 선언을 못 읽으므로
                                        DB 는 `object_kind IS NULL` 을 «일반 허용»하고, 「선언이 none 이라 했나」는
                                        발행이 «이미» 보장한다(predicate_claim). 즉 검사가 «층을 옮긴다»
```

### ㉡ 「표 A 의 「엔티티 은퇴」가 ③ 타입 status 와 ⑨ 를 «섞었다»」 — **섞은 게 아니라 «빠뜨렸다»**

```
표 A 가 잰 것   `entities.<t>` 의 optional 목록에 `status` 가 «없다» (setup_bundle.py:1119)  = «타입» 수명
표 A 의 ③ 줄    「A1-1 엔티티 은퇴 — 이 «타입»은 더 안 쓴다」  <- 타입이라고 «적혀» 있다
=> 인스턴스 은퇴(⑨)는 표 A 에 «한 줄도 없다». 섞인 게 아니라 «빠진» 것이다
```
🔵 **수리가 다르다** — 「한 행을 둘로 «가른다»」가 아니라 「행을 «더한다»」이고, 그 더한 행이 위 ㉠ 이라 «문법 무변이 아니다».

## D-1. 방향 ① — 「이 칸은 어느 생성자의 인자인가」 (없으면 «하드코딩»)

| 문법의 칸 | 유도되는 인자 | |
|---|---|---|
| `entities.<t>` · `keys` | `node : T × K → N` 의 T 와 K | ✅ |
| `attributes`(이름) · `bind.entities…attributes`(값) | `fact(n, register, ∅, Q, τ, π)` 의 **Q** | ✅ |
| `class` | 걷기 D_walk 의 «길» 제약(정적에서 안 나감) | ✅ B 쪽 인자 |
| `allow_null` | K 의 정의역 | ✅ |
| `references` | fact 의 목적어 N (합성 엣지) | ✅ |
| `vocabulary.<p>` · `subjects` · `object.kind` · `object.types` | `fact` 의 **P** 와 목적어 종류 | ✅ |
| `qualifiers.required/optional` | `fact` 의 **Q** | ✅ |
| `status`(술어) | D_P 의 «수명» | ✅ |
| `sources.<s>` 의 `relation`·`read`·`prepare`·`map`·`bind` | **Π** 로 가는 번역 | ✅ |
| `registration_probe` | Π 의 「첫 목격」 — fact(register) 를 «한 번만» | ✅ |
| `occurred_at`(+ `basis`) | **τ** | ✅ |
| `setup_version` · 지문 | **Π** 의 리비전 | ✅ |
| 🔴 `key_types` | **없다** — 어느 생성자의 인자도 아니고 «읽는 쪽»도 0 | ③′ → 삭제(판정 165) |
| 🔴 `supersedes` | 원장은 append-only 라 `fact⁻¹` 이 «없다»(§2.5). 이 칸은 그 없는 역을 «가리키고» 있었다 | ③′ → 삭제(판정 165) |
| 🔴 CHECK 의 `'register'` 리터럴 | 선언이 아니라 «저장 층»이 정한다 — 유도 안 됨 | **하드코딩**(D-0 ㉠) |
| 🔴 `_OBJECT_VALUE_ROLE_KINDS` 의 `quantity` | V 의 «타입»이 선언이 아니라 «코드»에 있다 | **하드코딩**(표 A A2-1) |
| 🔴 `label` 의 「keys 앞 둘」 | 표면 규칙이 코드에 있다 | 하드코딩(경미 — ②로 «적었다») |

## D-2. 방향 ② — 「이 생성자 인자에 칸이 있나」 (없으면 «구멍»)

| 생성자 · 인자 | 칸 | |
|---|---|---|
| `fact` 의 V «타입» | 🔴 **없다** — 값 목적어가 `quantity` 고정 | **구멍 ①** |
| `fact` 의 제약(카디널리티 · 필수) | 🔴 **없다**(필수는 qualifiers.required 로 있고, «카디널리티»가 없다) | **구멍 ②** |
| D_T 의 `status`(타입 수명) | 🔴 **없다** | **구멍 ③** |
| D_Π 의 `status`(소스 수명) | 🔴 **없다** | **구멍 ④** — ③④는 「모든 선언 항목은 status 를 가진다」 «한 패턴» |
| D_Π 의 `decision_key` | 🔴 **없다** | **구멍 ⑤** (판정 151·165) |
| «목적어 없는 술어»를 둘 이상 | 🔴 DB 가 거절 | **구멍 ⑥ (신규)** — §2.6 이 ⑨ 를 「무변」이라 본 자리 |
| D_walk 의 «시각»(as-of · 세대) | 🔴 **없다** — 라우트에 시각 인자 0 | **구멍 ⑦** (표 B B7 · §2.4 읽기 규칙과 한 몸) |
| D_walk 의 «짐» 읽기 규칙(최신 / 집합) | 🔴 **없다** — 항상 «최신», 집합 읽기를 «고를» 칸이 없다 | **구멍 ⑧** — 복수값 속성이 여기로 «환원»된다(칸이 아니라 규칙) |
| `aggregate` 의 measure 정의역이 «수식» | 🔴 **없다** | **구멍 ⑨** (§4.8 ②) |
| `M` 대수 (∪ ∩ ∖ ¬) | 🔴 **없다** | **구멍 ⑩** (§4.8 ①) |
| `read : K × D_read → R` (표 행 읽기) | ⚠️ 생성자가 «인정되면» 칸은 이미 있다(table_config) | 표 C C-3 — 판정 대기 ㉣ |
| `preview(f)` · `f ⊳ expected(s)` | 생성자의 «성질» — write 와 declare 에 «각각 반쪽» | 표 C C-1·C-2 — 판정 대기 ㉤ |

## D-3. 「대응이 바꾼 것」 — 한 줄 (판정 167 산출물)

```
표 A 의 «열셋» -> 「문법을 고칠 것」은 «여섯»(①값타입 ②카디널리티 ③④status 패턴 하나 ⑤decision_key ⑥목적어없는술어 둘째)
                 나머지는 읽기 규칙 «둘»(집합 · as-of/세대) · 사건 «둘»(봉투 없는 쓰기 · 외부 응답) ·
                 도구 «하나»(변경 비용 미리보기 = 표 C 의 preview 성질) · 삭제 «둘»(key_types · supersedes)
🔴 §2.6 은 문법 수리를 «다섯»으로 셌다. ⑥ 이 빠져 있었고, 그것이 §2.6 이 「문법 무변」이라 부른 바로 그 항목이다
🔴 그리고 관문의 두 방향에서 «아직 참이 아닌» 것:
   방향 ①(칸 → 인자)   하드코딩 «셋» — CHECK 의 register 리터럴 · 값 타입의 quantity · label 규칙
                     (③′ 둘은 판정 165 로 «삭제»가 답이라 유도 실패가 아니라 «제거» 대상)
   방향 ②(인자 → 칸)   구멍 «열» — 위 표. 그중 ⑦⑧ 은 걷기(B)와 «한 몸»이고 ⑩ 은 지을지 판정 대기
```

---
---

# 최종 목록 — 동결까지 무엇을 · 얼마에 (판정 168 ①)

> 표 A · B · C 를 판정 167 의 술어 «둘»(칸 ← 인자 · 인자 → 칸)과 판정 168 의 «성질» 축으로 다시 묶은 «하나의 목록».
> 각 줄의 «변경 비용» = 선언 몇 줄 · 코드 어느 층 · **소급 여부**. 🔴 소유자가 «순서»를 정할 재료이고, 순서는 제 몫이 아니다.

## F-0. 🔵 먼저 — 비용 모델을 «쟀다». 「선언 한 줄 고치면 다 다시 도나」의 답은 **아니오**다

```
커서 재설정 판단   «소스별» 지문 `source_cursor_fingerprint`(setup_registry.py:748~)
                 닫힘 = 그 소스의 plan(relation·read·prepare·map·bind, input_columns 만 제외)
                      + 그 소스가 «이름 부른» 술어 전부 + 거기 닿는 엔티티 전부
                      + compiler_contract_version + setup_version
                 🔵 「lot_event 를 고쳤더니 dt_job 백필이 거절되던」 결함을 «이미 고친» 자리다(그 함수 주석)
컴파일러 버전      `SNAPSHOT_COMPILER_VERSION = 4` — 「같은 행에서 «다른 원자»가 나올 때만» 올린다
                 (4 로 올린 사유가 정확히 그것: varchar occurred_at 을 읽게 되어 같은 행이 «다른 시각»을 냈다)
=> 🔵 **새 «선택» 칸을 문법에 더해도, 그 칸을 «안 적은» 소스는 지문이 안 움직인다 — 재번역 0.**
   그래서 아래 Ⓐ 의 문법 수리는 대부분 «소급 0» 이다. 이것이 소유자 상설(변경 비용)에 대한 오늘의 답이다
🔴 남는 비대칭 «하나» — 비용이 아니라 «표지»
   원자의 세대 표지 `source_translator_ver` 는 «스냅샷 전체» sha 를 쓴다(roleframe.py:1422).
   남의 소스를 고쳐도 내 «다음» 원자의 표지가 바뀐다. 재번역을 «부르지는 않는다»(그건 커서가 정한다) —
   다만 표지가 「누가 바뀌었나」를 못 말한다. 🔵 그것이 정확히 S-57(세대)이 메울 자리다
```

## Ⓐ 문법 수리 — 선언에 «칸»을 연다 (인자 → 칸 방향의 구멍)

| # | 무엇 | 선언 | 코드 층 | 소급 |
|---|---|---|---|---|
| 1 | **값 목적어의 «타입»** (구멍 ①) | `vocabulary.<p>.object.value_type` 한 칸 | 문법(setup_bundle) + 발행(`_OBJECT_VALUE_ROLE_KINDS` 를 «선언에서» 읽게) + 스켈레톤 한 줄 | 🔵 **0** — 기존 value 술어는 수인 채로 그대로. 새로 적는 술어만 |
| 2 | **카디널리티** (구멍 ②) | `object.cardinality` 한 칸 | 문법(검증)만. 읽는 쪽은 집계(B5)가 «생길 때» | 🔵 **0** — 제약은 새 원자에만 |
| 3 | **status 패턴** (구멍 ③④) | `entities.<t>.status` · `sources.<s>.status` — 술어의 것을 «일반화» | 문법 + 걷기가 retired 타입을 뺄지(한 줄) | 🔵 **0** |
| 4 | **decision_key** (구멍 ⑤) | 표 카탈로그에 `decision_key: [컬럼들]` (판정 151·165, 이름 «하나») | 문법 + 판정 120/122 의 뷰 결정 자리 | 🔵 **0** |
| 5 | 🔴 **목적어 없는 술어 «둘째»** (구멍 ⑥ — 오늘 발견) | 선언은 «이미 된다». 막는 것은 DB 다 | 🔴 **마이그레이션** — `ck_ledger_register_has_no_object` 를 이름 동치에서 «성질»로 (D-0 ㉠) | 🔵 원자 **0** — 다만 «마이그레이션 라운드»라 배포 절차(D7)가 붙는다 |

🔵 **1~4 는 «같은 모양»이다** — 선택 칸 하나 + 검증 몇 줄 + 스켈레톤 한 줄, 소급 0. 넷을 «한 라운드»로 묶을 수 있다.
🔴 **5 만 다르다** — 유일하게 DB 를 건드리고, 유일하게 「선언 한 줄」이 «거짓»이던 항목이다.

## Ⓑ 성질 붙이기 (판정 168 — dry · expected · 역을 «모든 생성자»에)

| # | 무엇 | 이미 있는 것 | 붙일 곳 | 소급 |
|---|---|---|---|---|
| 6 | `dry(declare)` = **변경 비용 미리보기** (A5-2) | `apply=False` 가 «열한 함수» · 미리보기 라우트 «열» · `preview_rescope` · `retroactive count` | declare 경로에 그 셋을 «부르는» 자리 하나 | 🔵 **0** — 읽기만 |
| 7 | `write ⊳ expected` = **조건부 쓰기** (C-2) | `expected_revision`(`config_drafts.py:392·408·446·477·497` · 라우트 :235) · 커서의 translator_ver 대조(`backfill.py:383,397`) | 표 행 쓰기(crud) + 라우트 인자 + 클라가 «본 값»을 실어 보내기 | 🔵 **0** |
| 8 | `write⁻¹` 의 «주어» (C-6, 판정 164 ⓐ) | 🔵 봉투가 **응답에 이미 있다** — `created_logs[].transaction_id` | 🔵 **클라 한 층** — 그리드가 그것을 «읽기만» 하면 된다 | 🔵 **0** |

🔵 **셋 다 «붙이기»다 — 짓는 것이 하나도 없다.** 특히 8 은 이 목록에서 «가장 싼» 줄이고, 제품에서 «가장 자주 눌리는 쓰기»(셀 편집)를 되돌릴 수 있게 만든다.

## Ⓒ 읽기 규칙 — 원자의 «칸»이 아니라 걷기의 인자 (D_walk)

| # | 무엇 | 비용 |
|---|---|---|
| 9 | **집합 읽기**(복수값 속성, 구멍 ⑧) | 걷기에 「최신 / 집합」 인자 하나. 🔵 원자 무변 — «읽는 규칙»이라 소급 0 |
| 10 | **as-of · 세대**(구멍 ⑦ + S-57) | 걷기에 시각 인자 + 세대 선택. 🔴 세대는 F-0 의 «표지 입도»를 같이 고쳐야 뜻이 선다 |
| 11 | **M 대수** ∪ ∩ ∖ ¬ (구멍 ⑩) | 🔴 «지을지»가 먼저 — 대조를 서버로 옮기는 판정과 «한 자리»(판정 대기 ㉢) |
| 12 | **measure 의 «수식» 정의역** (구멍 ⑨) | 11 과 같은 판정. 집계 축이 서야 그 정의역이 생긴다 |

## Ⓓ 하드코딩 삭제 (칸 → 인자 방향의 실패)

| # | 무엇 | 비용 |
|---|---|---|
| 13 | `key_types` 칸 삭제 (③′, 판정 165) | 문법 + 스켈레톤 + 레지스트리 «한 커밋». 🔵 소급 0 |
| 14 | `supersedes` 선언 은퇴 (③′, 판정 165) | 컬럼·CHECK 는 «그대로 두고» 쓰는 자 0 유지. 🔵 소급 0 |
| 15 | CHECK 의 `'register'` 리터럴 | = Ⓐ5 «같은 줄». 🔵 **판정 169: ㉡(성질화) 채택 — S-77** 로 열렸고, 저장 층은 «구조 불변식»만 지킨다. 따로 세지 않는다 |
| 15-bis | 🔴 `bind.occurred_at.column` — basis 가 `ingested` 인 소스에서 «죽은 칸** | ③′ 부류(판정 172). `read.occurred_at.basis: ingested` 면 원자의 시각은 «적재 순간»이고, 문장의 `bind.occurred_at.column` 은 «항상 무시»된다(`roleframe.py:339~347`, 판정 2026-08-23). 실측 2026-09-09: `dt_job` 의 두 문장이 `column: event_time` 을 적어 두고 있고 아무도 안 읽는다. 🔵 수리는 «검증기가 거절»하거나 «폼이 안 묻는» 쪽 — 라이브 선언은 안 고친다 |
| 16 | `label` 의 「keys 앞 둘」 | 경미 — ② 로 «적었다». 필요해지면 그때 선언 칸 |

## Ⓔ 사건 · 정의

| # | 무엇 | 비용 |
|---|---|---|
| 17 | **봉투 없는 쓰기** (D1) | 표 직접 쓰기 스크립트에 세션 경유 강제 + 가드. 🔵 원자 소급 0, 규율의 일 |
| 18 | **외부 응답 사건** | 싱크가 «생길 때». 오늘 필요가 없다 — 기본값 「없음」을 적고 미룬다 |
| 19 | 🔴 **`read = fold(E)` 를 «맞는지» 재기** (판정 168 ㉣) | 다음 라운드. 오늘 `GET /tables/{t}/data` 가 «표를 직접» 읽는데, 그것이 「사건의 접힘」과 «같은 답»인지는 **안 쟀다** — 봉투 없는 쓰기(17)가 있는 한 «같지 않을» 수 있다. 둘은 한 줄이다 |

## F-1. 이 목록이 말하는 «한 문장»

```
🔵 동결까지 남은 일 중 «소급이 붙는 것»이 «하나도 없다».
   Ⓐ1~4 는 선택 칸이라 안 쓰는 소스의 지문이 안 움직이고, Ⓑ 셋은 이미 있는 기제를 «붙이는» 일이며,
   Ⓒ 는 원자가 아니라 «읽는 규칙»이고, Ⓓ 는 삭제다.
   유일하게 다른 것이 Ⓐ5(DB 마이그레이션) 하나이고, 그것도 원자는 안 건드린다
🔴 그러므로 순서를 정하는 축은 «비용»이 아니라 «무엇을 먼저 할 수 있게 되느냐»다:
   · Ⓑ7(조건부 쓰기)이 없으면 랏 운영 셋의 가드가 «원자적이지 않다»(표 C C-4)
   · Ⓒ10(시각)이 없으면 걷기의 «멱등»이 말해지지 않고 이력·전후 비교가 질문될 수 없다
   · Ⓐ5 가 없으면 「노드 은퇴」가 «선언 한 줄»이 아니다
⚠️ 그리고 이 목록에 «없는» 것: 순서. 그것은 소유자 몫이고 총괄이 올릴 자리다
```

## F-2. `read = fold(E)` 는 오늘 «참인가» — 판정 168 ㉣ 의 정의를 잰다

> 판정 168 이 다섯째 생성자를 «정의»로 못 박았다: `read = fold(E)`, `D_read` = 표 카탈로그.
> 정의가 «오늘 참»이 아니면 read 를 더하는 순간 둘이 갈라진다. 그래서 잰다.

```
사건이 서는 자리   `auto_stage_database_outbox`(database.py:128~) — session.new / dirty / deleted 중
                 `DYNAMIC_TABLES` 의 인스턴스에만 CREATE · EDIT · DELETE 를 «단다»
🔴 첫 의심        층 표(`cell_sources` · `cell_overwrites`)는 «정적 Base 모델»이다(models.py:449,:467) —
                 DYNAMIC_TABLES 에 «없다». 그러면 우선순위를 바꾸는 라우트 «넷»이
                 화면 값을 바꾸면서 사건을 «안 남기는» 것처럼 보인다
```
### 🔵 그런데 «틀렸다» — 층 쓰기가 «바탕 행에 값을 굽는다»
```
set_cell_manual_priority_batch  crud.py:4565 -> ... `setattr(row, col_name, new_val)`
delete_cell_source_batch        crud.py:4402 -> `compute_priority_value(...)` 뒤 같은 `setattr`
그 `row` 는 `models.DYNAMIC_TABLES.get(table_name)` 로 꺼낸 인스턴스다(:4571, :4408)
=> session.dirty 에 들어가고 before_flush 가 EDIT 를 «단다»
⚠️ 값이 «안 바뀌면» dirty 가 아니라 사건도 없다 — 그리고 그때는 화면 값도 «안 바뀐다». 어긋나지 않는다
```
🔵 **그러므로 우선순위·소스 삭제 넷은 정의를 «지킨다».** 층은 사건을 안 내지만 «효력 있는 값»이 바탕 행에 구워지고, 그 쓰기가 사건이다.
⚠️ 하마터면 여기서 결함을 «지어낼» 뻔했다 — 층 표의 모델 선언만 보고 라우트가 부르는 함수를 «안 열었으면» 그랬다(상설 「축소판 재현은 동작이 아니다」).

### 그래서 정의가 깨지는 자리는 «둘»뿐이고, 둘 다 이미 목록에 있다
```
① 벌크 질의        session.query(...).update()/.delete() 는 new/dirty/deleted 에 «안 들어간다» -> 사건 0
② 표 직접 쓰기      세션을 안 지나는 스크립트 -> 사건 0
=> 둘 다 D1 «봉투 없는 쓰기»(Ⓔ17)다. 새 항목이 «아니다»
```
🔵 **결론: `read = fold(E)` 는 Ⓔ17 을 닫으면 «참이 된다». 다섯째 생성자를 위해 «새로 지을 것이 없다».**
   그리고 이것이 Ⓔ17 의 값을 올린다 — 봉투 없는 쓰기는 「되돌릴 수 없다」에 더해 **「읽기의 정의를 깬다」**이다.

## D-3. 재실행 — 문법 네 칸 착지 뒤 (2026-09-09 09:0x, `cf858ff5` + 판정 178)

> 판정 167 의 술어로 다시 읽습니다. 🔴 **0/0 «아닙니다» — 그리고 그것이 «맞습니다»**: 소유자가 「기저는 자리만」이라 하셨으므로 오늘은 «자리»가 정답입니다.

| 표 A 의 ③ | 착지 뒤 | 자리 | 정의역 | 읽는 쪽 |
|---|---|---|---|---|
| A2-1 값 목적어의 타입 | `vocabulary.<p>.object.value_type` | ① | 🔴 **③** — `number` «만» 통과(판정 178). string·boolean·timestamp 는 «이름 대어» 거절, 여는 것은 **S-84** | 발행 «0» (`roleframe.py` 에 `value_type` 0회 · `_OBJECT_VALUE_ROLE_KINDS` :493 이 여전히 `quantity`) |
| A2-3 카디널리티 | `vocabulary.<p>.cardinality` ∈ {one, many}, 기본 `many` | ① | ① | «0» — 무해(검사하는 쪽이 없을 뿐) |
| A1-1 엔티티 은퇴 | `entities.<t>.status` ∈ {active, retired}, 기본 `active` | ① | ① | «0» — 무해 |
| A4-2 소스 은퇴 | `sources.<s>.status` 같음 | ① | ① | 🔴 «0» — ⚠️ **무해하지 않음**: retired 로 적어도 «계속 번역»합니다 |
| A4-1 결정 단위 | 🔵 **표 카탈로그**의 `decision_key` (`setup_bundle.py:304~315`) — 소스에서 «옮겨졌습니다**(판정 e578eabc) | ① | ① (기본값 «없음» — 판정 151) | 미검 |

```
🔵 판정 178 의 요점: `value_type` 은 「덫」에서 「좁힌 자리」가 됐습니다.
   덫 = 폼이 권하고 검증이 받는데 «발행»이 거절 -> 운영자가 자기 잘못을 못 봄
   좁힌 자리 = 「아직 number 만」이라고 «문법이 먼저» 말함 -> S-84 가 열 때 그 거절만 빼면 됨
🔵 그리고 이 넷은 「안 적음 = 기본값을 적음」입니다(`class` 와 다릅니다) — 그래서 출하 샘플에
   기본값을 «그대로 쓴» 예시를 한 벌 넣을 수 있었습니다(`has_netdie@1` · `defect@1` · `bonded_from`)
```

### 방향 ①(칸 → 인자) — 🔴 «넷이 늘었습니다», 그리고 그것이 오늘의 정상입니다
```
새로 「칸은 있는데 아직 어느 생성자의 인자도 아님」  value_type · cardinality · entity.status · source.status
기존 ③′(삭제 예정)                                key_types · supersedes
=> 「자리만」 단계에서는 이 수가 «늘어야» 맞습니다. 줄어드는 것은 «읽는 쪽»이 생기는 라운드(S-84 등)입니다
🔴 다만 `source.status` 는 «읽는 쪽 0» 이 조용한 «불이행»이라, 나머지 셋과 같은 칸에 세지 않습니다
```

### 방향 ②(인자 → 칸) — 다섯이 닫히고 여섯이 남았습니다
```
닫힘 ①②③④⑤   값 타입(자리) · 카디널리티 · 타입 status · 소스 status · decision_key
남음           ⑥ 목적어 없는 술어 둘째(S-77) · ⑦ 시각 · ⑧ 집합 읽기 · ⑨ 수식 · ⑩ M 대수 · ⑪ 진위(B12)
=> 동결 문장은 아직 «못 씁니다». 다음 관문은 S-84(값 타입의 정의역)와 S-77(목적어 없는 술어)입니다
```

### D-3-bis. S-77 착지 — 구멍 ⑥ 닫힘, 하드코딩 하나 사라짐 (2026-09-09, `4f49fdff`)

```
전    CONSTRAINT ck_ledger_register_has_no_object CHECK ((predicate = 'register') = (object_kind IS NULL))
      -> «동치»라 목적어 없는 술어가 `register` «하나»여야 했습니다(D-0 ㉠ 에서 잰 것)
후    그 제약이 «사라졌습니다»(schema.py:20 묘비 · :128 사유 · :140 이름만 남겨 마이그레이션이 떨굴 수 있게)
      저장 층은 이제 «구조 불변식»만 지킵니다 — 목적어 없으면 payload 는 수식어뿐(ck_ledger_objectless_carries_only_qualifiers)
```
**일곱 층으로 확인했습니다** — DB 만 본 것이 아닙니다:
```
문법     목적어 없는 술어를 여럿 «선언 가능»(전부터)                                  ✅
발행     predicate_claim 이 목적어 없는 문장을 만듭니다                                ✅
엔진     runtime_v2 :499~531 의 register 분기는 «등록 중복 제거» 전용이고,
         `if atom.predicate != "register": continue` 라 «다른 술어는 그냥 지나갑니다»   ✅ 막지 않음
DB       제약 없음                                                                  ✅
=> 구멍 ⑥ «닫힘». 방향 ①의 하드코딩 「CHECK 의 register 리터럴」도 «사라졌습니다»(셋 -> 둘)
```
⚠️ **다만 대칭은 아닙니다 — 기록해 둡니다**: `register` 는 «중복 억제»를 갖습니다(`known_registrations` ·
`store.py:117` 의 부분 인덱스 `WHERE predicate = 'register'`). 둘째 목적어 없는 술어는 그것을 «안 씁니다» —
같은 사실을 두 시각에 내면 원자 «둘»입니다(`DEDUPE_COLUMNS` 에 occurred_at 이 있어 접히지 않음).
🔵 결함이 아니라 «성질»입니다. 「은퇴를 두 번 적으면 두 사실」이 맞는 답인지는 그 술어를 쓸 때 판정할 일입니다.

### 남은 구멍 (방향 ②)
```
닫힘   ①②③④⑤(자리) · ⑥(S-77)
남음   ⑦ 시각 · ⑧ 집합 읽기 · ⑨ 수식 · ⑩ M 대수 · ⑪ 진위
       + 정의역 하나: 값 타입이 아직 number 만(S-84)
=> 문법 관문(09-12)에 남은 것은 «S-84 하나»입니다. 나머지 다섯은 걷기·행동 인자라 09-16 관문 쪽입니다
```

---

## D-4. 문법 동결 — 재실행 (2026-09-09 09:4x, 판정 167 ① 의 술어로)

> 술어: 「모든 «문법 칸»이 어느 생성자의 인자로 «유도»되고 · 모든 «표기 기저의 인자»가 칸을 갖는다」. 판정 167 ① 대로 **자리는 기본값으로 유도**됩니다.

### 방향 ②(인자 → 칸) — 표기 기저 A
| 인자 | 칸 | |
|---|---|---|
| `fact` 의 V 타입 | `object.value_type`, 기본 `number` | ✅ |
| `fact` 의 카디널리티 | `vocabulary.<p>.cardinality`, 기본 `many` | ✅ |
| D_T 의 수명 | `entities.<t>.status`, 기본 `active` | ✅ |
| D_Π 의 수명 | `sources.<s>.status`, 기본 `active` | ✅ |
| D_Π 의 판단 단위 | 표 카탈로그의 `decision_key`, 기본 «없음» | ✅ |
| 목적어 없는 술어 «여럿** | 저장 층이 술어 이름을 «안 댐**(S-77) | ✅ |
| 🔴 행 선택·제외 | `sources.<s>.prepare.exclude_when` (S-91 착지 09-09 17:10) | ✅ |
| | **문법 구멍** | 🔴 **아래 D-6 에서 다시 셈** — 이 표의 인자 목록이 «내 산문»이었습니다 |

### 방향 ①(칸 → 인자) — 문법 칸이 «전부» 인자로 유도되나
```
key_types      ⚰️ «삭제»됨(판정 165 A1-3) — 묘비만 남음
supersedes     선언 칸이 «없음»(컬럼은 원장의 것이지 선언의 칸이 아니었음)
CHECK 의 register  ⚰️ «사라짐»(S-77)
value 의 quantity  🔵 하드코딩이 «아니게» 됐습니다 — `DEFAULT_VALUE_TYPE = "number"` 로 «적혔고»,
                  그 밖의 값은 `EMITTABLE_VALUE_TYPES` 로 «이름 대어» 거절되며 그 거절문이 «S-84 를 댑니다».
                  「선언됐지만 발행이 아직 안 읽는다」와 「그런 낱말이 없다」를 «가르는» 거절입니다(:142~154)
label 「keys 앞 둘」  ② 로 적힌 «표면 규칙» — 판정 169 로 동결 «밖»
                  문법 칸 = «0**
```

## 🔴 정정 — 동결 문장이 «과장»이었습니다 (S-91, 2026-09-09 16:0x)

```
제가 쓴 것   「문법의 ③ 은 «0» 이다」 (D-4)
반증        소유자 실측이 «축 하나»를 찾았습니다 — 「이 행이 이 소스의 행인가」(행 선택·제외).
           제외 기제는 «있는데»(`__source_row_excluded`) 파이썬 준비기만 내고 문법에 «0회»입니다
🔴 왜 못 봤나  제 표 A 의 A4 부축 목록을 «BASIS 의 축 목록»에서 받아 왔는데, 그 문서에도 이 축이 «없었습니다».
           그래서 「칸이 없다」가 아니라 «축이 없다»였고, 축이 없으면 제 표는 그 자리를 «묻지도» 않습니다
           => 「모든 생성자 인자가 칸을 갖는다」는 «인자 목록이 완전할 때만» 검사입니다. 목록이 짧으면 통과는 «공허»합니다
🔵 그리고 «단서가 있었습니다** — 출하 카탈로그 주석이 2026-08-23 에 이미 적어 뒀습니다:
           「the only row-exclusion mechanism (`__source_row_excluded`) is emitted by a preparer
             implementation -- the live config declares zero `source_preparers`」
           제가 그 파일을 여러 번 읽고도 그 문장을 «축»으로 읽지 않았습니다
조치        BASIS §2.3 의 D_Π 에 「행 선택」을 넣고, 표 A 에 행을 넣고, 아래 문장을 고칩니다
✅ 닫힘(09-09 17:10)  S-91 이 착지해 그 축에 칸이 생겼습니다 — `prepare.exclude_when`.
           표 A · D-4 의 그 행은 ① 이고, 이 절의 「③ 은 1」은 «그 축에 대해서는» 0 입니다
🔴 그러나 «이 절이 가르친 것»은 남습니다 — 칸 하나가 아니라 «검사 방법»이 빠져 있었습니다.
           그 방법을 D-6-1 에 적었고, 그것으로 다시 세니 ③ 이 «넷»입니다(D-6-4).
           즉 이 정정은 「1 → 0」이 아니라 「1 → 4」로 끝납니다 — 목록이 길어졌기 때문입니다
```

## 🔵 그래서 — 문법 동결 문장

```
🔴 이 문장은 «두 번» 고쳐졌습니다. ① S-91 이 「③ 은 0」을 무효로 만들었고, ② S-91 착지 뒤
   인자 목록을 BASIS §2-0 에서 다시 받으니 «다른 넷»이 나왔습니다. 오늘의 문장은 D-6-6 이 정본이고,
   여기 남기는 것은 «그때의 문장»입니다(기록):
2026-09-09 09:46 기준, 원장 «문법»의 모든 칸은 어느 생성자의 인자로 유도된다(방향 ① 참).
그러나 «모든 인자가 칸을 갖는다»는 «거짓»이다 — 「행 선택」에 칸이 없다(S-91).
문법의 ③ 은 «0 이 아니라 1» 이다.
⚠️ 남은 정의역 빚 «하나»는 «이름이 붙어» 있다 — 값 타입이 오늘 `number` 만 발행되고,
   그 밖은 「S-84」를 대며 거절된다. 침묵이 아니라 «번호 붙은 빚»이다
```
🔴 **걷기·행동 관문(09-16)은 «따로»입니다** — 거기 남은 ③: 시각 · 집합 읽기 · 수식 · M 대수 · 진위(B12) · 대조의 둘(B6) · 행동의 넷(C).

## D-5. 🔴 지문 폐쇄 — 그리고 §F-0 의 제 문장을 정정합니다 (S-87)

| 부축 | 상태 | 근거 |
|---|---|---|
| 지문이 «무엇을» 닫나 | ⚠️ **서술자의 «모양»** | `source_cursor_fingerprint` 는 `_semantic_plain(...)` 의 «정규 JSON»을 해시합니다(`setup_registry.py:838~`). `_semantic_plain` 은 «빈 필드도 남깁니다** — 그래서 **키를 하나 더하거나 빼면 값이 안 바뀐 소스의 해시도 움직입니다** |
| 실물 | | 그 파일이 스스로 적어 뒀습니다(:812~816): 「REMOVING THESE MOVED EVERY FINGERPRINT ONCE … dropping the key changed the hash even where the value had not」. 2026-09-09 문법 삭제에서 «15 소스» 전부 움직였습니다 |
| 비용의 «크기» | 🔵 커서 «정지» 한 번 | 해소는 `scripts/ledger_restamp_cursor.py` — **저장된 문자열만 옮기고 커서 «위치»는 안 옮깁니다** → 원자를 «다시 읽지도 다시 쓰지도» 않습니다 |
| 고칠 것 | **S-87** | 지문이 «서술자 모양»이 아니라 «선언된 내용»을 닫게 |

### 🔴 정정 — §F-0 에서 제가 쓴 문장
```
제가 쓴 것   「새 «선택» 칸을 문법에 더해도, 그 칸을 «안 적은» 소스는 지문이 «안 움직인다» — 재번역 0」
실제        지문은 «움직입니다». 서술자에 키가 하나 늘거나 줄면 정규 JSON 이 바뀌기 때문입니다
살아남는 것  «결론»은 그대로입니다 — 원자를 다시 읽거나 다시 쓰지 «않습니다»(재도장은 위치를 안 건드림)
죽는 것     «기제»가 틀렸습니다. 그리고 그 틀린 기제가 «운영 절차 하나»를 감췄습니다:
           🔴 문법이 바뀌는 «모든» 배포에 「소스 전부 재도장」이 붙습니다. 안 하면 커서가 «전부» 멈춥니다
=> 「소급 0」은 맞고 「비용 0」은 «틀렸습니다». 그 차이가 S-87 이 지우려는 것입니다
```

---

# D-6. 🔴 A4 부축 목록을 «기저에서» 다시 받음 — BASIS §2-0 (2026-09-09 18:0x)

> 지시(09-09 17:49): 「표 A 의 A4 부축 목록을 «그 절에서» 다시 받아 ③ 을 다시 셈. 후보 여섯은 «검사 대상»이지 답이 아님 — 각각 ①②③ 판정(문서 → grep)」

## D-6-0. 왜 목록을 «다시» 받나 — S-91 이 가르쳐 준 것
```
09:46 의 검사   방향 ①(칸 → 인자)은 «문법 키»를 걸어서 닫힌다 — 목록이 코드에서 나온다
                방향 ②(인자 → 칸)는 «내 산문 목록»을 걸었다 — 목록이 «내가 지어 놓은 것»에서 나온다
=> 그래서 ② 의 통과는 «목록이 완전할 때만» 뜻이 있고, 하루에 축 둘(S-91 · S-99)이 그 목록 밖에 있었다
🔵 이제 목록은 §2-0 의 «구조 정리»에서 온다: T = ⋃ emit_s({m ∈ unit(filter(read(R))) : select_s(m)})
   그 정리가 「이것이 전부」를 증명하므로, 인자 목록이 «닫혀» 있다 — 산문이 아니라 분해다
```

## D-6-1. 🔴 축 목록 완전성의 «검사 방법» — 한 줄로 돌릴 수 있는 것
```
검사   「런타임이 «엔진이 지어낸 컬럼»으로 읽는 것 중, 문법이 이름을 «안 대는» 것을 센다」
       그런 컬럼은 «선언이 못 말하는 축»의 흔적이다 — S-91 이 정확히 그 모양이었다
       (`__source_row_excluded` 가 `source_preparation.py` 에 있고 `setup_bundle.py` 에 «0회»)
오늘   `git grep -o '"__[a-z_]*"' -- server/ledger` = 다섯. 판정:
       __source_row_excluded     ✅ 문법 칸 있음 — `prepare.exclude_when` (S-91 착지)
       __source_event_incomplete ✅ 선언이 «준비기 출력»으로 이름 댐 (샘플 :927 · :949)
       __occurred_at · __source_row_ref   엔진의 «산출»이지 인자가 아님 (π · 시각의 자리)
       __physical_catalog__      탐색기의 내부 키 — 번역 인자 아님
=> 이 검사로는 «0». 🔴 다만 이 검사는 «컬럼으로 새는 축»만 잡는다.
   아래 D-6-3 이 잡은 셋은 «파이썬 매퍼 안»에 있어서 이 검사를 «통과»한다 — 그래서 검사가 «둘»이다
```
```
검사 둘   「출하 샘플의 소스 중 «범용 구현»을 안 쓰는 것을 세고, 그 구현이 «무엇을» 하는지 읽는다」
         범용을 벗어난 이유가 곧 «칸이 없는 축»이다. 이건 grep 한 줄이고 답이 이름으로 나온다
```

## D-6-2. 🔴 그 검사가 §2-0 의 전제 하나를 «반증»합니다 — 「무계산」
```
§2-0 전제   「원자의 값·수식어는 분자의 컬럼 값 «그대로»이거나 상수다. 변환·집계·조인은 없다」
           => 그래서 값 변환 · 그룹 집계 · 선언 조인은 «체인 기저»의 항목이고 이 기저의 구멍이 아니다
실측       출하 샘플 15 소스의 구현 이름 (grep, `.sample` — 저장소 파일이라 운영에도 참인 «모양»):
             prepare  direct-join 14 · lot-event-live-frame 1
             map      declarative-role 13 · lot-event-role 1 · dt-job-role 1
🔴 즉 «셋»이 범용을 벗어나 파이썬으로 갑니다. 그 셋이 하는 일이 파일에 적혀 있습니다:
   dt-job-role      「A dt_job is not one row: the count only exists once the rows are grouped,
                    which is why this needs a mapper at all rather than the generic declarative one」
                    -> «그룹 집계»가 원장 번역 «안»에서 일어납니다. 체인이 표에 써 준 것이 아닙니다
   lot-event-role   「the domain interpretation that cannot be expressed as independent column
                    bindings: split/merge pairing, positional slot lists, and first-sight
                    registration candidates」
                    -> «분자 안의 짝짓기» · «두 목록의 위치 대응» · «처음 본 주어인가»
=> 「무계산」은 «출하 샘플에서 거짓»입니다. 그러므로 이 셋은 「밖의 일」이 아니라 «이 기저의 구멍»입니다.
   전제가 참인 소스가 12~13 이고, 나머지가 파이썬으로 «새는» 것입니다
```
🔵 **그리고 새는 자리가 «이름 대어 거절»됩니다** — `roleframe.py:906` `ambiguous_binding_value`:
「column {c!r} has multiple values in one mapper unit」. 즉 범용 매퍼는 여러 값을 «조용히 첫 행으로»
접지 않고 «거절»합니다. 그래서 이 구멍은 «침묵이 아니라 번호 붙일 수 있는 빚»입니다.

## D-6-3. 후보 여섯 — 각각 ①②③ (문서 → grep)

| 후보 | 판정 | 근거(실측) |
|---|---|---|
| **값 변환** | 🔴 **③** | 바인딩 kind ∈ {column, constant, entity} «뿐»(`setup_bundle.py:495` `binding_kinds`). 값에 «함수»를 먹일 칸이 없습니다. 있는 변환은 «이름 붙은 하나» — `read.occurred_at.timezone`(샘플 :326). 🔴 그것이 이 축의 증거입니다: 변환이 필요할 때마다 «칸을 하나씩» 더해 왔고, 그 밖은 매퍼로 나갑니다 |
| **조건부 값** | 🔴 **③ = S-99** | `mappings.<s>` 에 `when` 이 «없습니다». 문법의 `when` 은 «둘 다 다른 것»입니다 — 스켈레톤의 `when` 은 «폼 표시 조건»(`{field, is}`), `setup_bundle.py:1304` 의 `when` 은 «엔티티 참조의 from 조건»입니다. 🔵 그러므로 S-99 는 «없던 것을 짓는 것»이 아니라 «이미 있는 조건 어휘를 문장 자리에 두는 것»입니다 |
| **그룹 집계** | 🔴 **③** | `map.unit.kind: group_by` 는 «분할»을 선언하고 «집계»는 선언하지 않습니다. 샘플에서 group_by 는 «1»이고 그 소스가 곧 `dt-job-role`(파이썬)입니다. 범용 매퍼는 여러 값을 만나면 `ambiguous_binding_value` 로 «거절»합니다 |
| **선언 조인** | ✅ **①** (단서 있음) | 칸이 있습니다 — `prepare.accepts_verified_join_rules` · `inherit_virtual_join_rules`, 그리고 `direct-join` 준비기를 15 중 «14»가 씁니다. ⚠️ 단서 둘: ⓐ 조인 «규칙»은 «다른 선언 언어»(`virtual_join_rules.json`)에 삽니다 — `decision_key` 와 «같은 부류»이므로 판정 165 와 같이 «관계를 적는» 처리 ⓑ 샘플 15 전부가 `false` / `[]` 입니다(소비자 0) → ③′ 의 성격을 «함께» 가집니다 |
| **다중 목적어 타입** | ✅ **①** | `object.types` 가 «목록»입니다(`setup_bundle.py:1149` `_nonblank_list`, 검사 :1993 · :2133). 한 술어의 목적어가 여러 엔티티 타입일 수 있습니다 |
| **부재의 뜻** | ✅ **②** | `entities.*.allow_null` 이 칸으로 있고(`ledger_skeleton.json:183`) 읽는 쪽이 있습니다(`roleframe.py:1289~1293`). 기본은 «원자 없음», 적으면 «null 목적어». 🔴 「없음 vs 모름」을 «구별»하려면 값의 정의역이 필요하고 그것은 S-84 의 자리입니다 — 번역 인자가 아닙니다 |

### 그리고 후보 여섯 «밖»에서 나온 것 — 매퍼가 이름 댄 셋 중 둘
| 축 | 판정 | 근거 |
|---|---|---|
| **분자 안의 «짝짓기»** | 🔴 **③** | split/merge 는 한 사건의 두 행이 «서로»를 가리킵니다. 바인딩은 «컬럼 하나 → 역할 하나»라 「같은 분자의 «다른 행»의 컬럼」을 적을 수 없습니다 |
| **두 목록의 «위치 대응»** | 🔴 **③** | `list_separator` 는 한 셀을 n 개로 «폅니다». 두 셀(`slots` · `wafers`)을 «위치로 짝지어» n 개를 내는 자리는 없습니다 |
| **「처음 본 주어인가」** | ⚠️ **§2-0 의 «국소성» 전제 밖** | first-sight registration 은 «원장이 이미 무엇을 아는가»에 답이 달려 있습니다 — 분자만으로 안 정해집니다(`execute_selected_scoped_batch(known_registrations=…)`). 🔴 이건 칸의 문제가 아니라 «전제의 문제»라 판정을 올립니다: 국소성을 좁힐지, 이 축을 기저에 들일지 |

## D-6-4. 그래서 — 인자 × 칸 (다시 셈)
```
read    ①  relation · columns · order/cursor · page          filter  ①  prepare.exclude_when          (S-91 착지)
unit    ①  map.unit.kind(row|event|group_by)                 select  ③  «없음»                        -> S-99
emit    ①  키 조립 · entity_ref · value · 수식어 · 상수        emit 안의 계산  ③ ③ ③               -> 값 변환 · 그룹 집계 · 짝짓기/위치
time    ①  occurred_at.column | basis (+ timezone)            multi   ①  list_separator (한 셀만)
π       ②  엔진의 것(row_id · 그룹 키) — 칸 없음이 «맞다»       σ       —  인자 아님(문의 삭제 사건)
정의역   ②  value_type = number 만 발행, 그 밖은 «S-84 를 대며» 거절
=> 🔴 번역 기저의 ③ = «넷» (문장 선택 S-99 · 값 변환 · 그룹 집계 · 짝짓기/위치)   + 전제 재검토 «하나»(국소성)
```
🔴 **09:46 에 제가 「문법의 ③ 은 0」이라고 쓴 자리에, 목록을 기저에서 받으니 «넷»이 있습니다.**
그중 «둘»(S-91 · S-99)은 오늘 소유자와 총괄이 찾았고, «둘»(집계 · 짝짓기)은 이 재계산이 찾았습니다.

## D-6-5. ③ 마다 큐 행 초안 (두 줄 문장 포함)

```
S-99  «문장 선택» — 한 분자가 «어느 문장»을 말하는지 선언한다
      두 줄:  「운영에서는 소스의 `bind.mappings.<문장>` 에 `when: {컬럼: 값}` 을 적으면 됩니다.
              그 조건이 맞는 행만 그 문장을 말하고, 안 맞으면 그 문장은 안 나옵니다」
      왜   조건부 값 · 다중 목적어 타입이 «둘 다» 이 하나로 닫힌다(§2-0 닫힘 절)
      단서  어휘가 이미 있다 — `references[].from.when` 이 «엔티티 신원 키»에 대해 같은 일을 한다.
           같은 철자를 쓰면 «두 번째 조건 언어»가 생기지 않는다

Q-집계  «그룹 값» — group_by 분자에서 «세거나 모은» 값을 선언한다
      두 줄:  「운영에서는 소스의 `bind` 에 `value: {from: 'group', op: 'count'}` 처럼 적으면 됩니다.
              그러면 묶인 행 수(또는 합·최소·최대)가 그 술어의 목적어가 됩니다」
      왜   샘플의 `dt-job-role` 이 «이것 하나 때문에» 파이썬입니다(파일이 자기 첫 줄에 그렇게 적어 뒀습니다)
      크기  op 목록을 «열거»로 두고 그 밖은 이름 대어 거절 — S-84 와 같은 모양

Q-변환  «값 변환» — 컬럼 값을 «이름 붙은 변환»에 통과시켜 목적어로 삼는다
      두 줄:  「운영에서는 바인딩에 `transform: <이름>` 을 적으면 됩니다.
              이름은 선언된 목록에서 고르고, 없는 이름은 «이름을 대며» 거절됩니다」
      ⚠️ 이건 «자유 수식»이 아닙니다 — 자유 수식은 국소성·무계산 전제를 깨고 체인의 일이 됩니다.
         오늘 이미 그런 변환이 «하나» 선언돼 있습니다(`occurred_at.timezone`) — 그 자리를 «일반화»하는 것

Q-짝짓기  «분자 안의 위치» — 같은 분자의 «다른 행/다른 목록 자리»를 가리킨다
      두 줄:  「운영에서는 바인딩에 `from_row: {match: <컬럼>}` 또는 두 목록에 `zip: [slots, wafers]`
              를 적으면 됩니다. 그러면 짝지어진 자리마다 원자가 하나씩 나옵니다」
      ⚠️ 두 축이 한 줄에 있습니다(행 짝짓기 · 목록 위치). 짓기 전에 «가르는» 판정이 필요합니다 —
         샘플의 근거는 `lot-event-role` «하나»뿐이라, 이 초안은 「하나의 사례에서 뽑은 규칙」의 위험이 있습니다
```

## D-6-6. 🔴 그래서 문법 동결 문장 — «다시 유도»
```
술어(판정 167 ①, 09-03 총괄 갈래 ①):
   「모든 «문법 칸»이 어느 생성자의 인자로 유도된다」 ∧ 「모든 «생성자 인자»가 칸을 갖는다」
방향 ①  ✅ 참 (D-4 그대로 — 문법 칸 중 인자로 안 가는 것 «0»)
방향 ②  🔴 «거짓» — 인자 목록을 BASIS §2-0 의 분해에서 받으면 칸 없는 인자가 «넷»이다
        (문장 선택 · 값 변환 · 그룹 집계 · 짝짓기/위치)
🔴 그러므로 2026-09-09 18:0x 기준 «문법 동결은 성립하지 않는다». ③ 은 0 이 아니라 «4» 다
```
```
🔵 그리고 이 수는 09:46 의 「0」보다 «나쁜 소식이 아니라 다른 종류의 수»다:
   09:46 의 0   내 산문 목록에 대한 0 — 목록이 짧으면 «공허하게» 참이다
   18:0x 의 4   구조 정리에 대한 4 — 정리가 「이것이 전부」를 증명하므로 «셀 수 있는» 4 다
   => 넷을 채우면 그때의 0 은 공허하지 않다. 그것이 이 재계산이 산 것이다
⚠️ 09-12 라는 날짜에 대해서는 아무 말도 하지 않는다 — 넷의 «크기»는 총괄이 판정할 자리다
```

---

# D-7. 판정 196 뒤 — 두 전제가 «규칙»이 되면 셈이 바뀝니다. 그리고 제 판정 하나가 틀렸고 닫힘 하나가 깨집니다 (09-09 18:2x)

> 판정 196: 「§2-0 의 두 전제는 «규칙»이다. ③ 넷 중 «문장 선택(S-99)»만 문법 구멍이고, 값 변환·그룹 집계·짝짓기는 문법에 «만들지 않는다» — S-100 부채(파이썬 셋을 「체인 규칙 + 표」로)」

## D-7-1. 🔴 정정 — 「다중 목적어 타입 = ①」은 제가 «틀렸습니다». 총괄 닫힘 주장이 맞습니다
```
제가 잰 것   `object.types` 가 «목록»이다 (`setup_bundle.py:1149` `_nonblank_list`)     <- 참
제가 답한 것  「그러므로 한 술어의 목적어가 여러 타입일 수 있다」 = ①                     <- «다른 질문의 답»
🔴 물음은 «소스»의 것이었습니다   「행마다 목적어 «타입»이 달라질 수 있나」
   실측: 엔티티 바인딩의 `entity_type` 은 «상수»입니다 — `_versioned_id(value.get("entity_type"))`
        (`setup_bundle.py:1554`, 허용 키 `("kind","entity_type","keys","attributes")` :1540).
        컬럼일 수 «없습니다». 그래서 한 문장은 «한 타입»만 냅니다
=> `types` 목록은 «술어가 허용하는 것»이고, «소스가 고르는 것»이 아닙니다.
   행마다 다르려면 문장 둘 + 선택 ⇒ **S-99**. 판정 196 의 닫힘이 맞고 제 ① 이 틀렸습니다
🔴 부류: 「뜻이 겹치는 칸이 둘이면 «코드가 걷는» 쪽을 고른다」의 판 — 저는 «술어 선언»을 재고
        «소스 선언»에 대해 답했습니다. 같은 낱말(타입)이 두 자리에 있었습니다
```

## D-7-2. ✅ 「처음 본 주어인가」 — 칸이 «있습니다». 제 「전제 밖」도 틀렸습니다
```
실측   `read.registration_probe` 가 문법 칸입니다(`required: false`) — 검증 `_validate_registration_probe`,
      읽는 곳 `backfill.py:1573` (`plan.driver.registration_probe`), 폼·작성기 `config_authoring.py:1751~1772`
      («미지의 모양»은 `unsupported_registration_probe` 로 이름 대어 거절)
🔵 그리고 «누가 쓰나»가 이 축의 증거입니다 — 출하 샘플에서 이 칸을 쓰는 소스는 «둘»(:734 dt_job · :980 lot_event),
   즉 파이썬 매퍼를 쓰는 «바로 그 둘»입니다. 비국소성이 칸으로 «이미 표현»돼 있었습니다
=> 판정 196 대로 «규칙의 명시된 예외»입니다. 제가 「국소성 전제 밖」이라 올린 것은 «칸을 못 찾은 것»이었습니다
```

## D-7-3. 🔴 반증 «성공» — 닫힘 넷 중 「철회」가 깨집니다 (filter 가 바뀌면 옛 원자가 남습니다)
```
닫힘 주장(§2-0)   「행 삭제 → 철회: σ 는 행이 아니라 «사건»(문의 delete)이 정한다 — 번역 인자 아님」
반증             σ 는 «filter»(번역 인자!)에도 달려 있습니다. 제외가 «나중에» 참이 되면 옛 원자가 «남습니다»
경로 (코드 읽기)
  ① 제외는 «프레임에서 떨굽니다» — `source_preparation.py:860` `out = out.loc[[not v for v in excluded]]`.
     그 자리 주석이 스스로 적어 뒀습니다: 「the base page is read off `rows_missing_from_the_index`,
     never off what survives here, so the excluded rows are passed over once and not re-read」
  ② 철회는 «사라진 행»만 겨눕니다 — `withdraw_deleted_rows(…, row_ids)` 는 표에서 «없어진» row_id 로 돕니다.
     제외된 행은 «표에 그대로 있으므로» 이 경로에 들어오지 않습니다
  ③ 범위 재번역도 못 걷습니다 — 그 범위의 행이 전부 제외되면 프레임이 비고 `backfill.py:727` 이
     `scope_empty` 로 «먼저 반환»합니다. `withdraw_refs` 는 계산됐지만 «적용 전»입니다
=> 선언에 `exclude_when` 을 «더하는» 배포는, 그 조건에 걸리는 행들의 «이미 쓴 원자»를 그대로 둡니다.
   원장은 「이 소스의 행이 아니다」라고 선언하면서 그 행의 사실을 «계속 들고 있습니다»
```
```
⚠️ 제가 «안 한 것**: 재현. 라이브 선언은 ⛔(기록자는 총괄 하나)이고, 재현하려면 선언을 바꿔야 합니다.
   그래서 이것은 «코드 경로 읽기»이고, 확정 실험은 한 줄로 말할 수 있습니다 —
   「제외 안 된 상태로 한 번 번역 → 선언에 `exclude_when` 추가 → 재도장 → 그 행의 원자 수를 센다.
     안 줄면 확정」. 격리 DB 에서면 제가 돌릴 수 있습니다(지시 주시면)
🔵 크기는 «작을» 수 있습니다 — 새 소스는 처음부터 제외되므로 이 자리는 «기존 소스에 조건을 더할 때»만 열립니다.
   그러나 S-91 이 «바로 그 용도»로 들어왔습니다(신원 키 부품이 빈 옛 행 995). 즉 첫 사용자가 이 경로입니다
```

## D-7-4. 표 A 의 A4 부축 → §2-0 다섯 인자로 «재매김» (지시 ①)
| 표 A 의 칸 | §2-0 인자 | |
|---|---|---|
| `relation` · `read.columns` · `order_by`/커서 · 페이지 | **read** | ① |
| `prepare.exclude_when` | **filter** | ① (S-91) |
| `map.unit.kind` (row·event·group_by) · `unit.columns` | **unit** | ① |
| `bind.mappings.<s>.when` (S-99, 09-09 18:33 **닫힘**) | **select** | ✅ ① — 검증 `setup_bundle.py:1521` `_validate_when` (교차 :2008) · 레지스트리 `setup_registry.py:272` · 읽는 곳 `roleframe.py:325` (`if mapping.when and not _unit_says(...)` → 그 문장을 «안 냄») · 폼 스켈레톤 · 출하 샘플 |
| `bind.mappings.<s>.bind` (키 조립 · entity_ref · value · 수식어 · 상수) | **emit** | ① |
| `read.occurred_at.column` \| `basis` (+`timezone`) | **emit** 의 t | ① |
| `list_separator` | **emit** 의 다중 | ① |
| `object.value_type` | **emit** 의 정의역 | ② (number 만 · 그 밖은 S-84 를 대며 거절) |
| `entities.*.allow_null` | **emit** 의 부재 | ② |
| `read.registration_probe` | **규칙의 «명시된 예외»**(비국소) | ① |
| `decision_key` | 번역 인자 «아님** — 표의 판단 단위(판정 165) | ① |
| `prepare.accepts_verified_join_rules` · `inherit_virtual_join_rules` | **규칙 «밖»**(조인) | 칸 있음 · 샘플 소비 0 → S-100 |
| `status` (술어) | 번역 인자 «아님** — 선언의 수명 | ✅ ① — «읽힙니다**(`roleframe.py:1381` `predicate.status != "active"` 면 발행 안 함) |
| `status` (엔티티·소스) | 번역 인자 «아님** | 🔴 **③′** — 적을 수 «있고»(:1611 `optional=("status",)`) 검증도 되는데 **레지스트리에 안 실립니다** (D-7-6) |
```
🔴 다섯 인자에 대해서는 ③ 이 «하나»(select = S-99).
   다만 표 A 의 ③ 이 그것 «하나»는 아닙니다 — 「소스 은퇴」는 번역 인자가 «아니라서» 이 셈 밖에 남아 있습니다.
   문법 동결 술어는 «문법 칸 전체»를 말하므로 그 행도 동결의 대상입니다
```

## D-7-5. 🔵 그래서 문법 동결 문장 — 판정 196 판 (D-6-6 을 대체)
```
술어   「모든 «문법 칸»이 어느 생성자의 인자로 유도된다」 ∧ 「모든 «규칙 안의 인자»가 칸을 갖는다」
방향 ①  ✅ 참 — 문법 칸 중 인자로 안 가는 것 «0» (D-4)
방향 ②  🔴 «하나» 남음 — select(문장 선택) = S-99.
        값 변환 · 그룹 집계 · 짝짓기는 «규칙 밖»이므로 동결 대상이 아니라 S-100 «부채»다
        「처음 본 주어」는 규칙의 명시된 예외이고 칸이 있다(`read.registration_probe`)
🔴 그리고 이 셈 «밖»에 둘이 더 있다 — 「엔티티·소스의 수명」(③′, D-7-6) ·
   그리고 D-7-3 이 연 「제외된 행의 옛 원자」(칸의 문제가 아니라 «기제»의 문제)
=> 2026-09-09 18:2x 기준: 번역 인자의 ③ = «1»(S-99). 문법 칸 전체로는 ③′ 이 «하나» 더(수명).
   S-99 가 닫히고 수명이 읽히면 그때의 0 은 «분해에 대한 0» 이라 공허하지 않다
```

## D-7-6. 🔴 표 A 의 「소스 은퇴 ③」이 «낡았습니다» — 그리고 실제 상태는 더 조용한 종류입니다
```
표 A 가 적은 것   「`_validate_sources` 는 다섯 키를 `exact` 로 재고 그 밖을 전부 거절 —
                 `status`/`enabled` 를 «적을 수 없다». 소스를 끄는 길은 «지우는 것»뿐」
오늘             `setup_bundle.py:1611` `optional=("status",)` — **적을 수 있습니다**.
                 값도 검증됩니다(:1617, `LIFECYCLE_STATES = {"active","retired"}`, 없으면 `active`)
⚠️ 그 위 두 줄 주석(:1614~1616)이 «자기 코드보다 낡았습니다** — 「the exact check then refuses
   every other key -- so a source that has stopped being read cannot be left on record saying so」.
   제 표 A 행이 그 주석에서 왔습니다(상설: 「주석은 «의도»의 증거이지 «동작»의 증거가 아니다」)
```
```
🔴 그런데 «고쳐진 것도 아닙니다» — 상태는 ③ 이 아니라 ③′ 입니다:
   술어      ✅ 읽힙니다 — `roleframe.py:1381` 「`predicate.status != "active"` 면 그 문장을 안 냅니다」
   엔티티·소스  🔴 «레지스트리에 안 실립니다** — `PredicateDescriptor` 에는 `status` 가 있는데
              (`setup_registry.py:154` · `:888`) 엔티티·소스 쪽 서술자에는 «필드가 없습니다».
              훑은 범위(server/ledger 의 `.status` 소비자 전부)에서 읽는 곳 «0»
=> 「은퇴」라고 적을 수는 있고, 적어도 «아무 일도 일어나지 않습니다». 소스는 여전히 읽히고 엔티티는 여전히 씁니다.
   이건 「칸이 없다」보다 조용한 고장입니다 — 폼이 그리고, 검증이 통과시키고, 운영자는 «껐다고 믿습니다»
```
> 큐 행 초안 — **Q-수명**: 「운영에서는 소스나 엔티티에 `status: "retired"` 를 적으면 됩니다.
> 그러면 그 소스는 «더 읽지 않고», 이미 쓴 원자는 «그대로 남습니다»(참인 역사).」
> 술어가 이미 그렇게 돕니다(`roleframe.py:1381`) — 같은 술어를 나머지 둘에 «잇는» 일이지 새 기제가 아닙니다.

---

# D-8. 체인 기저 — 「규칙 밖 셋」이 «저쪽에» 칸을 갖는가 (지시 ③, 09-09 18:4x)

> 판정 196 이 값 변환·집계·짝짓기를 «문법 밖 · S-100 부채»로 보냈습니다. 그러면 물음이 하나 남습니다 —
> **옮겨갈 저쪽에 «칸»이 있는가.** 없으면 S-100 은 파이썬을 «이사»시키는 것이지 선언으로 만드는 것이 아닙니다.

## D-8-1. 체인의 선언 «둘»과 그 칸 (출하 샘플, 저장소 파일)
```
chain_rules.json.sample      규칙 9. 키 = {name, trigger_table, derivation_source_table, target_table,
                             mapper_module, mapper_function, is_batch, enabled}
                             => 「어느 파이썬을 부르나」는 «선언». 「무엇을 계산하나」는 «코드»
enrichment_rules.json.sample 규칙 4. 키 = {source_table, derived_table, decision_key, target_fields,
                             list_columns, aggregations, alignment, reference_views, auto_confirm, enabled}
                             => 여기가 체인의 «선언적인 절반»입니다
```

## D-8-2. 셋을 그 칸에 대 봅니다
| 규칙 밖 축 | 체인의 칸 | 판정 |
|---|---|---|
| **그룹 집계** | ✅ 있음 — `aggregations: {컬럼: fn}` (샘플: `{"cell_count": "count"}`) | ⚠️ **②** — 정의역이 `count` «하나»입니다. 🔴 그리고 그 밖은 **「경고 후 조용히 드롭」**입니다(`enrichment_config.py:585` 「aggregation '…' dropped (v1 supports 'count' only)」). 원장 쪽 같은 상황은 «이름 대어 거절»하고 S-84 를 댑니다 — **같은 상황, 두 처리** |
| **선언 조인** | ⚠️ 있음 — `reference_views[].query` | ⚠️ **②** — 칸은 있으나 내용이 «생 SQL»(샘플: `SELECT … FROM dt_log WHERE dt_job = :dt_job ORDER BY …`). 완성 정의가 지목한 자리 그대로입니다 — 「뷰는 두 줄로 안 말해진다」 |
| **값 변환** | 🔴 **없음** | **③** — 변환은 `mapper_module`/`mapper_function` 이 가리키는 파이썬 «안»에 있습니다 |
| **짝짓기 / 위치** | 🔴 **없음** | **③** — 같은 자리 |

## D-8-3. 🔴 그래서 S-100 은 «셋이 아니라 하나»만 선언으로 갑니다
```
dt-job-role (집계)       ✅ 갈 곳이 있습니다 — 체인이 `aggregations: {cell_count: "count"}` 로 «세어» 표에 쓰고,
                        원장 소스는 그 컬럼을 `declarative-role` 로 «그대로» 읽습니다. 국소·무계산 규칙을 지킵니다
lot-event-role (짝짓기·위치)  🔴 갈 곳이 «없습니다» — 체인에도 칸이 없습니다. 오늘 옮기면 파이썬이 원장에서
                        체인으로 «자리만» 옮깁니다. 규칙은 지켜지지만(원장 선언이 깨끗해짐) 부채는 «그대로»입니다
lot-event-live-frame (준비기)  같은 부류
=> S-100 은 «두 종류»입니다: ⓐ 옮기면 선언이 되는 것(집계 하나) ⓑ 옮겨도 코드인 것(짝짓기·위치).
   ⓑ 를 ⓐ 와 같은 등급으로 큐에 넣으면 「했는데 아무것도 선언이 안 됐다」로 끝납니다
```

## D-8-4. ⛔ 그리고 «못 세는» 것 하나 — 이건 박스가 답할 수 없습니다
```
물음        「맵퍼 SDK(`server/mapper_sdk.py`, `@mapper` 데코레이터)를 «누가» 쓰나」
판별식      `git check-ignore` — `server/mappers/production_mapper.py` = **BOX** (`.py.sample` 만 추적)
            반면 원장 역할 매퍼 둘(`ledger_v2_dt_job_mapper.py` · `ledger_v2_lot_event_role_mapper.py`)은 **REPO**
=> 그래서 D-6 의 「15 중 셋」은 «유효»하고(추적 파일만 봤습니다), 체인 매퍼의 소비자 수는 «무효»입니다.
🔴 그리고 소유자가 이미 답하셨습니다 — 「내가 운영에서 @mapper 로 했다니까? 박스 재지 마」(2026-09-07).
   추적본 중 SDK 를 쓰는 것은 `production_mapper.py.sample` «하나»이고, 그 수는 «출하 견본의 수»이지
   운영의 수가 아닙니다. 여기서 「소비자 0/1」을 말하지 않습니다
```

## D-8-5. 🔵 그러므로 「맵퍼 SDK 가 코드라는 것이 답인가」 — 답: **부분적으로만**
```
답이 되는 쪽   판정 196 의 규칙이 「계산은 체인의 것」이라 했으므로, 체인의 계산이 «코드»인 것은
              규칙 위반이 아니라 규칙의 «다른 쪽»입니다. `mapper_module`/`mapper_function` 이 그 코드를 «이름 댑니다»
답이 안 되는 쪽 그러면 체인은 「무엇을 계산하나」를 아무 데도 «적지 않습니다». 그래서 변경 비용이
              원장 쪽과 다릅니다 — 원장은 선언 diff 로 「무엇이 다시 도는가」를 물을 수 있고, 체인은 «코드 diff» 입니다
              (상설 「소급이 비싸서 선언·스키마 변경이 싸야 한다」의 반대편)
🔵 다만 체인에는 «선언적 절반»이 이미 있고(enrichment_rules), 그 절반이 집계 하나를 이미 답합니다.
   그래서 물음은 「SDK 를 없앨까」가 아니라 **「그 선언적 절반을 어디까지 넓힐까」**입니다 — 그건 판정 자리입니다
```

---

# D-9. 🔵 문법 동결 문장 — **정본** (2026-09-09 18:33, S-99 착지 뒤 · 판정 196·197·198·199)

> 앞선 넷을 대체합니다. 술어는 판정 167 그대로이고, 바뀐 것은 «인자 목록을 어디서 받나»입니다:
> 09:46 에는 제 산문에서, 지금은 BASIS §2-0 의 «구조 정리»에서 받습니다.

```
술어   ① 모든 «문법 칸»이 어느 생성자의 인자로 «유도»된다        (판정 167 ①: 자리는 기본값으로 유도)
      ② 모든 «규칙 안의 인자»가 «칸»을 갖는다                  (판정 196: §2-0 의 두 전제는 «규칙»이다)

방향 ①  ✅ 참   문법 칸 중 인자로 안 가는 것 «0» (D-4 방향 ①, 오늘도 그대로)
방향 ②  ✅ 참   여섯 인자가 «전부» 칸을 갖는다
               read ① · filter ①(S-91) · unit ① · **select ①(S-99, 18:33 닫힘)** ·
               emit ①(t ① · 다중 ① · 정의역 ② · 부재 ②)
               규칙의 «명시된 예외» registration_probe ① (비국소성이 칸으로 이미 표현돼 있다)

=> **2026-09-09 18:33 기준: 번역 인자의 ③ = «0». 그리고 이 0 은 공허하지 않다**
   (분해가 「이것이 전부」를 증명하므로 — 09:46 의 0 이 공허했던 이유가 정확히 그것이 없어서였다)
🔵 오늘 «두 번» 0 이 나왔고 두 0 은 «다른 문장»이다:
   09:46 의 0   내 산문 목록에 대한 0. 목록이 짧아서 참이었고, 같은 날 축 둘이 그 밖에서 나왔다
   18:33 의 0   BASIS §2-0 의 구조 정리에 대한 0. 목록이 «닫혀» 있으므로 밖이 없다
   => 하루에 축 넷을 찾고(S-91 · S-99 · 집계 · 짝짓기) 그중 «규칙 안의 둘»을 채워서 닫힌 0 이다
```

## 동결 술어 «밖»에 남는 셋 — 관문이 아니라 «같이 읽어야 하는 것»
```
S-100  값 변환 · 그룹 집계 · 짝짓기   «규칙 밖»이라 문법에 만들지 않는다(196). 등급 2, ⓐ 하나만(197)
                                => 동결의 대상이 «아니다». 「문법에 없다」가 결함이 아니라 «규칙»이다
S-103  엔티티·소스의 «수명»          칸은 있고(③′) 읽는 쪽이 없다(198). 등급 2
                                => 「모든 칸이 인자로 유도된다」는 참이다 — 유도된 칸이 «안 읽힐» 뿐이다.
                                   그래서 동결 술어를 안 깬다. 🔴 그러나 운영자에겐 «껐는데 안 꺼진» 칸이다
S-101  제외된 행의 옛 원자           «칸의 문제가 아니라 기제»다(199, 등급 1 · 구현자).
                                => 술어를 안 깨지만, 깨는 것은 더 센 것이다 —
                                   「선언이 말하는 것」과 「원장이 든 것」이 어긋난다
S-105  없는 컬럼을 적어도 통과      «칸의 문제가 아니라 정의역»이다(총괄 18:37 · 구현자).
                                => 아래 「셋째 방향」. 술어가 그것을 «묻지 않으므로» 0 과 공존한다
```
## 🔴 그리고 «셋째 방향»이 있습니다 — 술어가 «묻지 않는» 것 (S-105, 총괄 실측 18:37)
```
동결 술어가 묻는 것   ① 칸 -> 인자   ② 인자 -> 칸        둘 다 «칸의 존재»에 대한 물음이다
묻지 «않는» 것        ③ 「그 칸에 적힌 «값»이 검사되나」   = 정의역
```
```
오늘의 사례   출하 샘플의 lot_event `split`·`merge` 문장이 주어와 목적어를 «둘 다» 컬럼 `lot` 에 묶는데
             (자기를 가리키는 엣지) 그 이름이 read 가 싣는 컬럼에 «없고», 셋업이 그것을 «받습니다» → S-105
같은 부류    S-86(로더의 조용한 수용) · S-102(체인 집계의 count 밖 함수를 «경고 후 드롭»)
🔴 그래서 ③ 이 0 이어도 「선언이 검사된다」는 «따라오지 않습니다». 칸은 다 있고, 그 칸에
   «관계에 없는 이름»을 적어도 통과할 수 있습니다 — 그리고 그때 실패는 «런타임»으로 미뤄집니다
```
🔵 **다만 이 방향은 «칸마다» 이미 표에 있습니다** — 표 A 의 마지막 열(정의역)이 그것이고,
`value_type`(② number 만 · 그 밖은 S-84 를 대며 거절) 같은 줄이 그 자리입니다.
없는 것은 «칸마다의 답»이 아니라 **「모든 칸이 정의역 검사를 갖는가」라는 술어**입니다.
그것을 세려면 표 A 의 그 열을 ①②③ 로 «다시 한 번» 훑어야 하고, 그건 별도 라운드입니다.
⚠️ 제가 잰 것이 아닙니다 — S-105 는 총괄이 제품 로더로 샘플을 읽어 잡은 것입니다. 여기엔 «부류»로만 적습니다.

🔴 **그러므로 「동결했다」와 「원장 선언이 옳다」는 «다른 문장»입니다.** 동결은 «칸이 다 있다»는 말이고,
S-101·S-103 은 «있는 칸이 말한 대로 되지 않는» 자리입니다. 09-12 에 ① 이 참이 되어도 이 둘은 열려 있습니다 —
동결 문장을 그 둘의 «부재 증명»으로 읽지 않도록 여기 같이 적습니다.

## 그리고 「이 문장이 또 낡을 때」를 위한 검사 둘 (D-6-1 정본, 한 줄씩)
```
① 「엔진이 지어낸 컬럼(`"__*"`) 중 문법이 이름을 «안 대는» 것을 센다」        오늘 0
② 「출하 샘플에서 «범용 구현»을 안 쓰는 소스를 세고, 그 «이유»를 읽는다」      오늘 3 (전부 S-100)
🔴 ① 만 돌리면 파이썬 안에 있는 축을 «전부» 놓칩니다. 그래서 둘입니다 — 하나는 컬럼으로 새는 축,
   하나는 «구현 이름»으로 새는 축을 잡습니다
```

---

# D-10. 정의역 열 훑기 — 「그 칸의 «값»이 검사되나 · 무엇으로 · 안 되면 실패가 «어디로» 미뤄지나」 (지시 09-09 18:40)

> D-9 의 «셋째 방향»을 별도 라운드로. 세는 대상은 «칸의 존재»가 아니라 «칸에 적힌 값의 검사»입니다.

## D-10-0. 어떻게 쟀나 — 목록 «둘 다» 코드에서 받았습니다
```
칸의 목록    `ledger_skeleton.json` 을 «걸어서» 폼이 쓸 수 있는 잎 칸을 뽑았습니다 = «38»
            (제가 타이핑한 목록이 아닙니다 — S-91 이 가르쳐 준 「목록을 내 산문에서 받지 말 것」)
거절의 목록  커밋된 `setup_bundle.py` 를 `ast` 로 읽어 `problems.add(코드, 경로, …)` 를 전부 = «123 자리 · 코드 35 종»
            🔴 «커밋된» 것입니다 — 훑는 중에 다른 레인이 그 파일을 편집하고 있어서(18:43 mtime,
            제 프로브가 반쪽 편집에 걸려 `TypeError` 를 봤습니다) HEAD blob 으로 다시 돌렸습니다.
            그 편집은 «건드리지 않았습니다»
교차        칸의 잎 이름 × 거절 경로의 잎 이름. 안 맞는 것은 «후보»로 두고 «손으로» 확인했습니다
            (경로가 변수인 거절은 이 교차가 못 봅니다 — 실제로 일곱이 그렇게 떨어졌고 전부 ① 이었습니다)
```

## D-10-1. 🔵 «존재»로는 ③ 이 «0» 입니다 — 38 칸 전부에 이름 대는 거절이 있습니다
| 갈래 | 수 | 예 |
|---|---|---|
| 번들 검증이 «이름 대어» 거절 | **31** | `object.value_type` → `unsupported_value_type` · `read.occurred_at.timezone` → `invalid_timezone` · `exclude_when[].column` → `unknown_column` · `bind.mappings.<s>.when.<컬럼>` → `unknown_column`(S-99 도 «검사와 함께» 들어왔습니다) |
| 교차가 못 본 것 → 손으로 확인, 전부 ① | **5** | `relation` → `unknown_relation`(:2349) · `virtual_joins.{left,right}_table`·`join_key.{left,right}` → `_relation_columns`(:1843~1850). 경로가 «변수»라 이름으로 안 잡혔을 뿐입니다 |
| ⚠️ «다른 단계»에서 거절 | **2** | `prepare.implementation_id` · `map.implementation_id` — 번들 검증엔 없고 **스냅샷 컴파일**이 거절합니다(`setup_registry.py:638` 「version … is not trusted」). 거절은 «있고» 자리가 한 단계 뒤입니다 |
```
=> 「칸에 아무 값이나 적어도 조용하다」는 «거짓»입니다. 38 칸 전부가 이름 대어 거절합니다
```

## D-10-2. 🔴 그런데 «충분성»으로는 다릅니다 — 거절이 «틀린 집합»에 대고 잽니다
```
발견   바인딩의 컬럼은 «관계의 컬럼 ∪ 준비기 산출»에 대고 검사됩니다:
         `setup_bundle.py:1919`  available = set(physical)
         `setup_bundle.py:1931`  available.update(prep["output_columns"])
      그런데 원자를 만들 때 «프레임에 실려 오는» 컬럼은 그 집합이 «아닙니다»:
         `source_preparation.base_select_columns` = identity · group_by · order_by · cursor ·
         occurred_at · 준비기 입출력 · exclude_when · **when(S-99)** · **map.input_columns** · row_id
      🔴 이 목록에 «바인딩의 컬럼»이 «없습니다». 바인딩 컬럼은 `map.input_columns` 에 «따로 적어야»
         프레임에 옵니다
결과   관계엔 있고 read 가 «안 싣는» 컬럼을 바인딩에 적으면 → 검증 «통과» → 실행에서 터집니다:
         `roleframe.py:895` `missing_binding_column` 「column X is absent from the EventFrame unit」
=> 「검사가 없다」가 아니라 **「검사가 다른 것을 잰다」**입니다. 그리고 그 차이가 실패를 «런타임으로» 미룹니다
```
🔵 **그리고 S-99·S-91 은 이 함정을 «피했습니다»** — `when` 과 `exclude_when` 의 컬럼은
`locked_select_columns` 의 인자로 들어가 «읽기에 강제»됩니다(`condition_columns` · `exclude_when_columns`).
즉 같은 파일이 그 두 칸에 대해서는 「선언한 컬럼이 프레임에 오게」 만들어 두었습니다.
**바인딩만 그 대우를 못 받고 있습니다.**

## D-10-3. 칸 × {검사 있음 · 조용히 받음 · 런타임에서 터짐}
| | 몇 칸 | 실패가 어디서 나나 |
|---|---|---|
| ✅ 번들 검증이 이름 대어 거절 | 36 | «작성 시점» — 폼이 그 경로를 짚어 줍니다 |
| ⚠️ 스냅샷 컴파일이 거절 | 2 | «로드 시점» — 폼이 아니라 기동/재로드에서 |
| 🔴 검증은 통과하고 «실행»에서 터짐 | 바인딩 컬럼 «전부»가 이 위험을 가짐 | `roleframe.py:895` — 이름은 대지만 «운영 중»입니다 |
| 🔴 조용히 받고 «아무 말 없음» | 알려진 셋 → 각각 큐 | S-105 · S-86 · S-102 |
```
⚠️ 마지막 두 줄은 «칸 수»로 못 셉니다 — 「이 칸이 검사되나」가 아니라 「그 검사가 옳은 것을 재나」라서
   칸마다 «그 검사의 정의»를 읽어야 합니다. 오늘 읽은 것은 «컬럼을 받는 칸» 갈래이고, 거기서 하나 나왔습니다
```

## D-10-4. ③ 의 큐 행 초안
```
Q-바인딩-읽기   «바인딩이 이름 댄 컬럼은 읽기가 싣는다»
   두 줄:  「운영에서는 바인딩에 컬럼 이름만 적으면 됩니다. 그 컬럼은 자동으로 읽혀 옵니다 —
           `map.input_columns` 에 «또» 적지 않아도 됩니다」
   기제   `base_select_columns` 에 «프로파일 바인딩 컬럼»을 한 항 더한다. `when`·`exclude_when` 이
          이미 그렇게 들어가 있으므로 «새 기제가 아니라 한 줄»이다
   대안   더하지 않겠다면 «검증에서» 잡는다 — 바인딩 컬럼이 `base_select_columns` 에 없으면
          이름 대어 거절. 둘 중 하나는 해야 실패가 런타임에서 «작성 시점»으로 옮겨온다
   ⚠️ 이 초안은 «둘 중 어느 쪽인지»를 정하지 않습니다 — 「자동으로 싣는다」와 「거절한다」는
      운영자에게 다른 약속이고, 그건 판정 자리입니다
```
```
Q-정의역-충분성  «검사가 무엇을 재는지»를 칸마다 한 줄로 적는다
   오늘 이 표는 「거절이 있나」까지 왔습니다. 「그 거절이 «옳은 집합»을 재나」는 칸마다 다르고,
   오늘 «컬럼 갈래»에서만 하나를 찾았습니다. 나머지 갈래(열거 · 참조 · 수 · 시각)는 «안 읽었습니다»
   -> 이건 큐 행이라기보다 «이 표의 다음 열»입니다. 지시 주시면 이어서 합니다
```

## D-10-5. 그래서 D-9 에 무엇을 되먹이나
```
바뀌는 것   D-9 의 「셋째 방향」이 «부재»가 아니라 «불충분»으로 정확해집니다 —
           38 칸에 거절이 다 있고, 그중 «컬럼을 받는 칸»의 거절이 프레임이 아니라 관계를 잽니다
안 바뀌는 것 동결 술어의 ③ = 0 (판정 167 은 두 방향이고 이 열은 그 밖입니다)
🔴 다만 D-9 의 경고가 «더» 맞습니다 — 「③ 이 0 이어도 «선언이 검사된다»는 따라오지 않는다」에
   이제 «기제»가 붙었습니다: 검사는 있는데 프레임이 아니라 관계를 잽니다
```

---

# D-11. 정의역 훑기 «나머지 갈래» — 열거 · 참조 · 수 · 시각 (지시 09-09 18:47, 판정 201 뒤)

> 물음은 D-10 과 같습니다: 「그 거절이 «옳은 집합»을 재나」. 답을 먼저 적으면 —
> **이 네 갈래에 «이름 없는» 구멍은 없습니다.** 대신 «상태가 넷»이라는 것이 나왔고, 그 넷을 가르는 규칙이 하나 나왔습니다.

## D-11-0. 🔵 이 훑기가 찾아낸 «규칙» — 이것이 D-10 의 결함을 일반화합니다
```
「받는 집합」과 「지키는 집합」이 다를 수 있다.  다르면 — 거절이 «둘 다»를 이름 대야 한다.
   ✅ 잘 된 예   value_type: 문법이 받는 넷 ≠ 발행이 지키는 하나. 거절이 «두 문장»으로 갈린다
                「그런 낱말이 아니다」 vs 「선언은 되는데 발행이 아직 안 읽는다 — S-84」
   🔴 안 된 예   바인딩 컬럼(D-10): 받는 집합 = «관계», 지키는 집합 = «프레임». 거절은 앞것만 안다
                -> 뒷것은 운영 중에 `missing_binding_column` 으로 나온다
```

## D-11-1. 열거(choice) — 11 개, «드리프트가 구조적으로 불가능»합니다
```
실측   폼의 목록 이름 11 (`ledger_skeleton.json` 의 `"list"`)
      그중 «아홉»이 `config_authoring.py:565~576` 에서 «검증기의 frozenset 그대로» 만들어집니다:
        LIFECYCLE_STATUSES · EMITTABLE_VALUE_TYPES · CARDINALITIES · OBJECT_KINDS ·
        _SOURCE_UNITS · _MAPPER_UNITS · _OCCURRED_AT_BASES  (전부 `setup_bundle.py:130~174`)
      => 폼이 내놓는 값과 검증기가 받는 값이 «같은 객체»입니다. 두 철자가 아니라 하나입니다
예외 둘 (그리고 둘 다 «의도된» 것)
  ⓐ binding_kinds · identity_binding_kinds   `declaration_contract()` 의 «리터럴»(:496 · :504)
     -> 두 철자입니다. 다만 «시험이 못 박습니다» — `test_identity_keys_are_not_offered_an_entity.py`
        가 「모든 kind 를 검증기에 먹여」 비교합니다(리터럴을 믿지 않고 «동작»을 잽니다).
        그 파일의 주석이 그 이유를 스스로 적어 뒀습니다
  ⓑ prepare_implementation · map_implementation   «신뢰 레지스트리»의 옵션에서 만듭니다
     -> 폼이 내놓는 것이 곧 «컴파일되는 것»입니다. 그래서 「고를 수 있는데 거절되는 값」이 없습니다
```
✅ **열거 갈래의 ③ = 0.**

## D-11-2. 참조(ref) — 「받는 집합」이 아니라 「지키는 집합」을 잽니다
```
predicate     `unknown_predicate`(선언에 없음) + **`inactive_predicate`**(있는데 은퇴)
              🔵 둘째가 요점입니다 — 런타임(`roleframe.py:1381`)이 «active 아니면 안 냅니다».
                 즉 거절이 «발행이 지키는 집합»을 재고 있습니다. D-11-0 의 규칙대로입니다
entity_type   `unknown_entity_type` · `keys` 는 「등록된 신원 키와 «정확히» 일치」 · 속성 이름은 «타입이 소유»
⚠️ 그림자 하나  엔티티의 `status` 는 «아무도 안 읽습니다»(S-103). 그래서 「은퇴한 엔티티를 내는 문장」이
              거절되지 않는 것은 «거절이 틀린 집합을 재서»가 아니라 «지키는 집합이 곧 전부»여서입니다.
              고칠 자리는 여기가 아니라 S-103 입니다 — 술어처럼 «읽히게» 되는 날 이 칸도 같이 맞습니다
```
✅ **참조 갈래의 ③ = 0** (S-103 은 «다른 축»입니다 — 정의역이 아니라 수명).

## D-11-3. 수(number) — 거절은 있는데 «한 단계 뒤»입니다
```
setup_version              `unsupported_setup_version` — 번들 검증에서
implementation_version     `invalid_version` — 「모양이 버전인가」까지. **«신뢰되는가»는 여기서 안 봅니다**
                           -> `setup_registry.py:638` 「version … is not trusted」 = «스냅샷 컴파일»
=> 받는 집합(모양이 맞는 버전) ⊋ 지키는 집합(신뢰 목록). 그 차이는 «이름 대어» 거절됩니다 —
   다만 자리가 «작성 시점»이 아니라 «로드 시점»입니다
```
🟡 **③ 는 아니고, 「실패가 어디로」의 답이 다릅니다** — 폼에서는 못 잡고 기동/재로드에서 잡습니다.
   ⓑ(폼이 신뢰 레지스트리에서 목록을 만든다, D-11-1)가 이미 그 창을 «좁혀» 둡니다 —
   목록에서 «고르면» 신뢰된 것이고, 손으로 «타이핑하면» 로드에서 만납니다.

## D-11-4. 시각(instant) — 실물 tz 데이터베이스를 잽니다. 그리고 «넷째 상태»가 여기 있습니다
```
timezone   `ZoneInfo(timezone)` 를 «실제로 만들어» 보고 `ZoneInfoNotFoundError` 면 `invalid_timezone`
           (:1766~1769) -> 받는 집합 = 지키는 집합. 문자열 목록을 따로 들고 있지 «않습니다» ✅
basis      `_OCCURRED_AT_BASES = {"ingested"}` — 한 값짜리 열거
🔴 그리고 여기가 «넷째 상태»입니다 — `bind.<역할>.occurred_at` 이 컬럼을 대는데 소스가 `basis` 를
   선언한 경우: 컴파일러가 그 컬럼을 «안 읽습니다». 검증은 «거절하지 않고», 로더가 «이름 대어 알립니다»
     `setup.py:133` `_dead_time_cells` · `:191` `_announce_dead_cells` (정보 한 줄, 프로세스당 한 번, 경로 전부)
   ⚠️ 그리고 그 파일이 «왜 거절이 아닌지»를 적어 뒀습니다 — 거절하면 그 두 소스의 선언을 고쳐야 하고,
      선언을 고치면 «재번역»이 따라옵니다(동결 라운드가 안 하기로 한 바로 그것). 그래서 «말하고» 미룹니다
```
🔵 제가 오늘 서버 로그에서 그 줄을 실제로 봤습니다: 「dead cell: sources.dt_job.bind.mappings.counted.
bind.occurred_at=event_time (basis ingested) ignored」. **기제가 아니라 «동작»으로 확인됩니다.**

## D-11-5. 그래서 — 상태는 «셋»이 아니라 «넷»입니다 (D-10-3 을 넓힘)
| 상태 | 뜻 | 예 |
|---|---|---|
| ✅ 작성 시점 거절 | 폼이 그 경로를 짚어 준다 | 36 칸 (D-10) · 열거 11 · timezone |
| ⚠️ 로드 시점 거절 | 기동/재로드에서 이름 대어 | `implementation_id`·`_version`(신뢰) |
| 🔵 **받되 «알리고» 무시** | 거절이 «비용 때문에» 미뤄진 자리. 사유와 «없앨 라운드»가 같이 적혀 있다 | 죽은 시각 칸(판정 179 ⓑ) |
| 🔴 실행 시점에 터짐 | 검증이 «다른 집합»을 쟀다 | 바인딩 컬럼 → 판정 201 로 닫힘 |
```
🔴 셋째 상태는 «결함이 아닙니다» — 「고칠 수 있는데 지금 안 고치는 이유」가 값으로 적혀 있고,
   운영자가 그것을 «봅니다». 그것이 없으면 넷째와 구별이 안 됩니다(둘 다 「거절 안 함」이므로).
   그래서 이 표에 상태를 하나 더 두는 것이 이 훑기의 결론입니다
```

## D-11-6. ③ 초안 — «없습니다». 대신 남긴 것 둘
```
③ 0        네 갈래에서 「이름 없이 조용히 받는 칸」을 «못 찾았습니다»
남긴 것 ①   D-11-0 의 규칙을 «다음 칸이 생길 때»의 판별식으로 씁니다 —
           「이 칸의 받는 집합과 지키는 집합이 같은가. 다르면 거절이 둘 다 이름 대는가」
남긴 것 ②   ⚠️ 이 훑기는 «칸» 단위입니다. 「칸 둘 사이의 관계」는 안 봤습니다 —
           S-105 가 잡은 「한 문장의 주어와 목적어가 «같은 값»에 묶임」이 정확히 그 부류이고,
           칸마다로는 «둘 다 옳습니다». 그 축을 세려면 «문장 단위» 훑기가 따로 필요합니다
```
