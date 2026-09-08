# 원장 선언 스키마 완전성 (S-75) — 축 × 칸

> **Status:** 🟢 Living | **Written:** 2026-09-09 05:4x (응용, 판정 161·162 · 아침 초인종 09-09 05:32) | **Owner:** 응용
> **축의 정본은 [`BASIS.md`](./BASIS.md)** — 이 문서는 그 축에 «칸»을 채운다. 축이 여기서 새로 나오면 BASIS 를 고치고 한 줄 남긴다.
> **문법의 정본은 `server/ledger/setup_bundle.py`** — 아래 모든 줄은 그 파일과 `roleframe.py` · `schema.py` 에 대고 잰 것이다.
> 🔴 **스키마 동결(09-12)의 관문 = 이 문서 표 셋의 ③ 이 0.**
> 규율: 문서 먼저 → `git grep` 검증 · 라이브 config 수 ⛔(샘플·문법만) · 칸을 «지어내지» 않는다.

## 0. 이 표를 읽는 법 — 칸의 «상태» 넷

```
①   선언 칸이 있다             이름과 자리를 적는다
②   기본값이 덮는다            🔴 「없음」이 아니라 «무엇으로» 덮이는지 «값»을 적는다
③   없다 = 결함               동결 전에 채운다. 「무엇을 적을 자리인가」를 한 줄로
③′  칸은 있는데 «읽는 쪽»이 0    축이 «덮이지» 않는다 — 적어도 아무 일도 안 난다
     ⚠️ ③′ 를 관문의 ③ 에 «세는지»는 총괄 판정 대기(§8). 아래 표에서는 «따로» 표시한다
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
| **결정 단위** `decision_key` | 🔴 **③** | 🔴 **원장 선언에도 표 카탈로그에도 없다.** 실측: 카탈로그 항목의 키 = `{business_key, column_types, composite_key_separator, composite_key_source, display_columns, kind, map_key_columns, workspace_name}` (샘플 44 표 전수). ⚠️ **`decision_key` 는 «다른 선언 언어»에 산다** — `enrichment_rules.json` 의 규칙마다(`enrichment_config` · `alignment_view_service.py:53` · `chain_bindings.resolve_decision_column`). 판정 151 이 여는 칸이 «그것과 이름이 같다» → 「한 이름 두 뜻」 위험을 판정에 붙일 것 | 목록(컬럼들) |
| 삭제 겨눔 | ① | `ledger_source_row_ref` (`schema.py:69`, 키 `(relation, row_id, source_who, source_raw_ref)`) · `backfill.sources_without_row_index` :915 · `index_existing_refs` :936 · `withdraw_deleted_rows` :1056 | |
| 삭제 — row_id 없는 뷰 | ② | 🔵 «이름 대어» 남는다 — `sources_without_row_index` 가 그 소스를 «센다». 뷰가 base 의 `row_id` 를 흘려 주면 그 뷰는 겨눌 수 있다(:246 주석, 샘플 뷰 10 중 5) | |
| **소스 은퇴** | 🔴 **③** | `_validate_sources` 는 `required=("relation","read","prepare","map","bind")` 를 `exact` 로 잰다 — **그 밖의 키는 전부 거절**(:1466). `status`/`enabled` 를 «적을 수 없다». 소스를 끄는 길은 «지우는 것»뿐 | |

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

## 8. 판정 대기 — 관문의 셈법

```
㉠ ③′ 둘을 동결 관문의 ③ «에 세나»
   세는 쪽 근거   축이 «덮이지» 않는다 — 적어도 아무 일도 안 나므로 「칸이 없다」와 결과가 같다
   안 세는 쪽 근거 고치는 일이 «다르다» — ③ 은 «짓는» 일, ③′ 는 «읽는 쪽을 만들거나 은퇴시키는» 일
   🔴 제 의견: «센다». 다만 ③′ 로 표시해 수리 종류를 가른다
㉡ A4-1 `decision_key` 의 «이름» — enrichment 규칙에 이미 같은 이름이 있다(뜻: 규칙의 판단 단위).
   표 카탈로그에 같은 이름을 놓으면 「한 이름 두 뜻」(은퇴 상설 ㉣). 판정 151 을 «이름째» 다시 볼 자리
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
