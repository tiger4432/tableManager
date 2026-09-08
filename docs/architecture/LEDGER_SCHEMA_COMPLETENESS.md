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

## 표 B 의 ③ — «여섯»

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
