# Ledger V2 설정 작성 가이드

> **Status:** 🟢 Living
> **Last-verified:** 2026-08-23 — 🔴 **선언에서 «없어진» 낱말 넷을 이 라운드에 지웠다**:
> vocabulary의 `layer`(§7.1 · `ddc93f5b`)와 binding의 `binding_origin`·`approval_status`·
> `suggestion_reason`(§7.6 · `90383987`). 🔴 **`read.cursor`는 이제 «묻지 않고 `order_by`에서
> 파생»된다**(§7.7). 🔴 **범용 매퍼가 드디어 시각 Role을 채운다**(§7.9 · `189193a4`) — 그것이
> 폼만으로 만든 첫 소스 `transfer_event`를 막고 있던 것이다. **작성 화면이 무엇을 채워 주는지는
> §13.3-quater 신설.** 아래 2026-08-21 서술은 그대로 유효하다.
> 🔴 **`setup_version: 5`. 필수 section은 «셋»이다**
> (`entities`·`sources`·`vocabulary`). 2026-08-20~21의 다섯 라운드
> (`087e7d8`·`d64f047e`·`a55f3059`·`e795c706`·`9b6c5da`)로 소스 하나가
> `relation`·`read`·`prepare`·`map`·`bind` 다섯 절을 직접 들게 됐고, 마지막 라운드가
> **`packs`와 그 안의 `claims`를 통째로 지웠다** — 문장이 이제 술어를 «직접» 대고
> (`bind.mappings.<문장> = {predicate, bind}`), Role은 그 술어의 vocabulary 항목에서
> 도출된다(§7.5). 옛 root를 들고 있으면
> `server/scripts/migrate_ledger_config_to_v5.py`가 세대 무관하게 올려 준다(§2.4).
> **Owner:** Server / Ledger
> **정본 구현:** `server/ledger/setup_bundle.py`(파일 문법), `setup_registry.py`(compile), `setup.py`(로드 경계)
> **운영 선언 루트:** `server/config/ontology/` — 파일 **하나**, `ledger_config.json`

이 문서는 새 원천 테이블을 Ledger V2에 연결할 때 **무엇을 어떤 순서로 작성하고,
각 필드가 왜 필요한지** 설명하는 단일 설정 가이드다. 구형
`server/config/ledger_config.json`(flat legacy 선언), translator 종류, `declared_lookup`,
Position/Frame, 마이그레이션·cursor reset 중심의 옛 설정 절차는 이 문서의 대상이 아니다.

> 🔴 **셋업은 파일 하나다.** 소스 하나를 붙이는 사람이 여는 것은 `ledger_config.json`과 —
> 필요하다면 — mapper 함수 하나뿐이고, **단순한 소스는 mapper조차 필요 없다**(§7.4의
> `declarative-role@1`, §7.3의 `direct-join@1`). 예전에는 `manifest.json`이 열거하는
> 다섯 파일을 세 디렉터리에 나눠 썼다. 그 모양은 **은퇴했다** — 옛 내용은 지워지지 않고
> 보존돼 있지만 **로드되지 않으며 지원 경로가 아니다.** 어디에 무엇이 남았는지는 §2.3.

설정은 DB 테이블을 만들지 않고, 데이터를 쓰지 않으며, Python 구현을 config 문자열로
불러오지 않는다. 물리 테이블과 인제션이 먼저 존재해야 한다. 설정은 그 데이터를 어떻게
읽고 의미로 바꿀지를 선언한다.

---

## 1. 먼저 이해할 전체 흐름

```text
server/config/ontology/ledger_config.json
  ├─ setup_version      현재 정확히 5
  ├─ vocabulary         낼 수 있는 술어와 목적어 모양 — Role도 «여기서» 도출된다
  ├─ entities           개체의 정체성과 키
  ├─ sources            소스 하나가 실행 순서대로 다섯 절을 «직접» 든다 — 여기 있으면 «돈다»
  │    ├─ relation      읽는 물리 표
  │    ├─ read          물리 batch를 어떻게 긁나 (unit·identity·group_by·order_by·
  │    │                occurred_at·cursor·registration_probe)
  │    ├─ prepare       물리 행 → EventFrame          (옛 `source_preparers` 본문)
  │    ├─ map           EventFrame → RoleEmission     (옛 `mappers` 본문)
  │    └─ bind          문장 이름 → 술어 + Role binding (옛 `profiles` 본문)
  └─ virtual_joins      (선택) 물리 UNIQUE로 검증할 batch join

strict Bundle validation
  → trusted implementation 대조
  → immutable Registry/Snapshot
  → cursor physical batch
  → Preparer + verified batch join
  → pandas EventFrame
  → Mapper RoleEmission
  → RoleFrame compiler LedgerFrame   (Claim은 선언이 아니라 «술어에서 도출»된다)
  → 기존 gate → LedgerStore → cursor transaction
```

핵심은 세 층을 분리하는 것이다. 파일이 하나가 됐다고 층이 섞이는 것은 아니다 — 다만
**층의 경계가 이제 section이 아니라 «절»이기도 하다.** 재사용되는 의미는 자기 section을
갖고, 소스 하나에만 붙는 배선은 그 소스 안에 산다.

| 층 | 질문 | 사는 곳 |
|---|---|---|
| 물리 | 어느 테이블의 어느 컬럼을 어떤 키로 읽나? | **`table_config.json`**(§5) · `virtual_joins` · `sources.<id>.relation`·`.read` |
| 의미 | 무엇을 개체·관계·시각으로 말하나? | `vocabulary`, `entities` · `sources.<id>.bind` |
| 실행 | 누가 행을 준비하고 Role로 해석하나? | `sources.<id>.prepare`, `.map` |

🔴 **`packs`가 넷째로 사라졌다** (소유자 판정 2026-08-21: 「굳이 claims 도 불필요하지 않나
… 실질적 클레임은 vocab 만 남잖아」, `9b6c5da`). Claim은 Role 목록과 `emit` 절을 선언했는데
**둘 다 그 Claim이 내던 술어가 이미 강제하는 것**이었다. 지우기 전에 실측한 것: 라이브
config의 술어 다섯 중 **서로 다른 Role 집합으로 쓰인 것은 0개**, Claim의 qualifier 이름은
술어의 `object.qualifiers`와 **글자까지 같았고**, `emit` 여섯 중 다섯은
`$subject`/`$occurred_at` 그대로였다. 여섯째만 양끝을 `$child`/`$parent`로 적고 있었고 같은
라운드가 그것을 `subject`/`target`으로 개명했다. 도출의 정본은 함수 **하나**,
`setup_bundle.predicate_claim`이다(§7.5).

🔴 **왜 그 앞의 셋이 section을 잃었나** (소유자 판정 2026-08-20 「소스플랜 준비기 맵퍼」 ·
「근데 그럼 프로필도 소스랑 묶여야 하는거 아니야?」). preparer의 `input_columns`는 **물리
relation의 컬럼**이어야 하는데 `relation`은 소스만 선언한다 — 자기 section에 앉은 preparer는
자기를 검사해 줄 유일한 선언에서 늘 한 홉 떨어져 있었다. profile 쪽은 1:1이 이미 **강제**돼
있었다(profile이 `source`를 선언해야 했고, `_cross_validate`가 자기를 고른 소스의 id 외에는
전부 거절했다). 셋 다 옮기기 전에 소스와 1:1임을 실측했고, **공유되던 것은 하나도 없었다.**
재사용되는 것은 선언이 아니라 **코드**이고, 그 재사용은 여전히
`implementation_id` + `implementation_version`으로 적는다.

`bind`(옛 Profile)는 문법이 아니다. **문법은 `vocabulary`가 소유한다** — 문장이 술어를
가리키면 그 술어가 Role 목록을 정하고, `bind`는 그 소스의 컬럼을 그 Role에 연결하는
배선이다. 그래서 `bind`는 소스 안에 산다.

---

## 2. 실제 파일 위치와 복사 가능한 기준 샘플

### 2.1 운영 root

```text
server/config/ontology/
├─ ledger_config.json   ← 셋업 전부
└─ README.md
```

이 파일은 예시 사본이 아니라 현재 운영 정본이다. 수정 전에는 별도 작업 브랜치에서
전체 Bundle 검증과 preview를 먼저 수행한다.

🔴 **이 문서는 그 파일 안의 «개수»를 적지 않는다.** 소스도 술어도 개체도 늘어난다 —
2026-08-19 기준으로 소스는 이미 하나가 아니다. 아래 §7의 JSON 블록은 전부 **발췌**이고,
지금 무엇이 선언돼 있는지는 §13.2의 쓰기 없는 dry-run이 답한다. 여기에 목록을 베껴 두면
그 목록이 낡는다.

🔴 **root에 다른 `.json`이 있으면 로더가 «거절»한다**(`unlisted_config_file`). 이것은
정돈 취향이 아니라 「이 파일 하나를 열면 전부 본 것」이라는 약속의 집행이다. 남겨 둔
`catalog/tables.json`은 아무도 읽지 않으면서 권위 있어 보이는 자리에 앉아 있게 된다.
검사는 **재귀한다** — 백업 폴더를 root **안에** 두어도 걸린다. 거절 메시지가
「move it outside the config root」로 끝나는 이유가 그것이다.

### 2.2 이종 transfer와 virtual join 샘플

```text
server/config/sample/ontology/transfer_explorer/ledger_config.json
```

같은 단일 파일 모양이고, 운영 root가 쓰지 않는 **선택 section `virtual_joins`**를 실제로
쓰는 유일한 예제다(§6).

⚠️ **이 샘플은 «다른 공장»이다.** 그 배포의 물리 스키마는 그 배포의 `table_config.json`
(`server/tests/support/transfer_explorer_table_config.json`)이 들고 있고, 이름이 같은
운영 테이블과 **같은 표가 아니다**(§5.4).

이 샘플은 다음을 보여준다.

- `dt_log`를 cursor가 읽는다.
- Preparer가 `dt_job_id`를 키로 `dt_inventory`를 batch join한다.
- `CoreDie@1 → DTDie@1 → BondComponent@1 → FinalChip@1` 연속 계보를 선언한다.
- 오른쪽 relation의 `dt_job_id`는 business key와 UNIQUE index로 단일성을 증명한다.

주의: config가 이름으로 부를 수 있는 구현은 **코드에 실재하는 클래스**뿐이다. 파일을
production root에 복사하는 것만으로 trusted implementation이 생기지 않는다. 어떤 이름이
실행 가능한지는 `server/ledger/implementations.py`가 **코드에서 발견해** 답한다(§7.3·§7.4).

### 2.3 옛 다섯 파일을 찾고 있다면

2026-08-18 이전 root는 `manifest.json`이 열거하는 다섯 파일이었다. 찾는 것에 따라 자리가
다르다.

**① 은퇴한 «주변» 파일 넷 + manifest** — 지워지지 않고 옮겨졌다.

```text
server/config/_ontology_pre_single_file_20260818/
├─ manifest.json
├─ catalog/{tables,virtual_joins}.json
└─ dataflows/{chains,enrichments}.json
```

⚠️ **여기에 `ledger_config.json`은 «없다».** 그 파일은 옮겨진 것이 아니라 **제자리에서 새
모양으로 다시 쓰였다** — 지금 `server/config/ontology/ledger_config.json`이 그것이다.

**② 접기 «직전»의 다섯 파일 전부(옛 `ledger_config.json` 포함)** — 변환 근거로 통째 보존돼
있다.

```text
task/evidence/ontology_root_before_20260818/
```

둘 다 **내용을 대조할 때만** 본다. **지원되는 config 경로가 아니다** — 로더는 이 모양을 읽지
않고, 어느 쪽이든 config root 안으로 되돌리면 §2.1의 거절이 난다.

아직 옛 모양의 root를 들고 있다면 일회용 변환기가 있다.

```powershell
conda run -n assy_manager python server/scripts/convert_ontology_to_single_file.py --root <다섯 파일이 다 있는 옛 root> --out <빈 디렉터리>/ledger_config.json
```

원본을 지우지 않고 **새 파일 하나**를 쓴 뒤 무엇이 어디로 갔는지 표로 출력한다. 옮길 자리가
없는 선언(비어 있지 않은 `enrichments`, `v2`가 아닌 selector 항목)은 조용히 버리지 않고
**멈춘다**. 옛 root와 새 파일이 한 디렉터리에 공존하면 로드되지 않으므로 출력은 빈
디렉터리에 쓴다. 🔴 `--root`는 **다섯 파일이 다 있는** root여야 한다 — 위 ①은
`ledger_config.json`이 없어 이 변환기의 입력이 아니다(②는 입력이 된다).

### 2.4 `setup_version` 4 이하를 들고 있다면 — 마이그레이션

2026-08-20~21에 파일 «모양»이 다섯 라운드에 걸쳐 바뀌었고, **스크립트는 둘이며 순서대로
탄다.** 앞의 것이 세대 무관하게 v4까지 올리고, 뒤의 것이 v4를 v5로 올린다.

```powershell
conda run -n assy_manager python -m scripts.migrate_ledger_config_to_v4 <ledger_config.json 경로...> --check
conda run -n assy_manager python -m scripts.migrate_ledger_config_to_v5 <ledger_config.json 경로...> --check
```

(`server/`에서 실행한다. `--check`는 무엇이 바뀔지만 보고하고 **아무것도 쓰지 않는다**;
빼면 제자리에 쓴다.)

| 옛 모양 | → |
|---|---|
| `source_preparers` / `mappers` 절 | 그 본문이 그것을 쓰는 소스 안으로 |
| `profiles` 절 | 그 본문이 그것을 binding하는 소스 안으로 |
| `driver` | `read` · `prepare` · `map` · `bind` 넷으로 갈라짐 |
| `map.emits` · `bind.packs` | 삭제 — 둘 다 `use`의 되풀이였다 |
| `binding_origin` · `approval_status` · `suggestion_reason` | 삭제 — 셋 다 은퇴했다(2026-08-22). 남아 있어도 검증기가 받아서 버린다 |
| `mappings: [ {mapping_id, …} ]` | `mappings: { "<문장 이름>": {…} }` |
| `setup_version` | `4` |
| **`packs` section** | **삭제** — Claim은 술어에서 도출된다(`predicate_claim`) |
| **`mappings.<문장>.use`** (`<pack>@v/<claim>`) | **`mappings.<문장>.predicate`** — 그 Claim이 내던 vocabulary id |
| **`mappings.<문장>.bind.<role>`** | 술어가 강제하는 Role 이름으로 개명 — `subject`·`target`/`value`·`occurred_at`·qualifier는 **선언된 이름 그대로** |
| **`setup_version`** | **`5`** |

모든 단계가 **멱등**이다 — 이미 목표 모양인 파일은 바뀌지 않고 다시 쓰이므로 라이브 config·
샘플·운영자의 묵은 백업이 **같은 명령**을 탄다.

🔴 **v5 변환은 이름을 «추측하지» 않는다.** 개명의 근거는 지워지는 그 `emit` 절이다 —
`lot-lineage@1/lineage`의 `emit.subject`가 `$child`였으므로 `child`가 `subject`가 되고,
`dt-job@1/die_count`의 `emit.object.value`가 `$count`였으므로 `count`가 `value`가 되며,
`emit.object.qualifiers.slot`이 `$slot`이므로 `slot`은 그대로다.

🔴 **그리고 삭제는 «검증»된다.** Claim을 버리기 전에, 개명 후의 Role 목록을 그 술어가
도출하는 Role과 **이름 대 이름·required 대 required**로 대조한다. 어긋나는 파일은
차이를 찍고 **거절한다** — 그 파일에 대해서는 이 라운드의 전제(「Claim이 술어를 되풀이할
뿐」)가 거짓이고, 그러면 section을 지우는 것이 무언가를 잃는 일이 되기 때문이다.

🔴 **별명은 «도출»되지 추측되지 않는다.** mapping의 새 키는 그 소스의 mapper가 어느 문장으로
해석하느냐이고, 그 답의 유일한 정본은 이 라운드 «전에» mapper가 쓰던 규칙이다 — Claim의
구조(목적어 유무·qualifier 이름·양끝 entity type 철자)를 그대로 맞춰 본다. **옛
`mapping_id`를 읽어 이름을 정하는 코드는 한 줄도 없다.** 어느 문장에도 안 걸리거나 이미 다른
mapping이 가져간 문장에 걸리면 **그 id와 사유를 찍고 파일은 손대지 않는다.** 문장 선언이
아예 없는 mapper(`declarative-role@1`)의 mapping은 원래 이름을 그대로 키로 쓴다 — 틀릴 문장이
없다는 관찰이지 추측이 아니다.

---

## 3. 작성 전 준비 사항

설정을 열기 전에 아래 질문에 답한다.

1. **물리 relation은 이미 존재하고 `table_config.json`에 선언돼 있는가?** 그 선언은
   DDL이 아니다 — 표를 만들어 주지 않는다(§5).
2. **한 source event는 한 행인가, 여러 행의 group인가?**
3. **세계 시각 컬럼은 무엇이며 timezone은 무엇인가?** 묵시적 기본 timezone은 없다.
4. **cursor 동률을 제거할 catalog-declared UNIQUE key는 무엇인가?**
5. **Preparer 출력만으로 신원이 완성되는가?** 아니면 verified virtual join이 필요한가?
6. **기존 trusted Preparer/Mapper를 재사용할 수 있는가?**
7. **기존 Vocabulary/Entity로 말할 수 있는가?** 새 의미가 아니면 중복 선언하지 않는다.
   🔴 술어를 하나 고르면 **Role 목록이 따라온다** — 고를 것은 술어이지 Role이 아니다(§7.5).
8. **이 소스를 지금 돌려도 되는가?** 🔴 `sources`에 적는 순간 **돈다**. 「적어 두고 나중에
   켜기」를 해 주는 별도 스위치는 없다(§8). 준비가 덜 됐다면 `sources`에 아직 적지
   않는다.

### row와 group 선택

| 원천 모양 | `source.read.unit` | `group_by` | 예 |
|---|---|---|---|
| 한 행이 독립된 source event | `row` | 반드시 `[]` | 한 행당 측정 1건 |
| 여러 행이 한 source event를 이룸 | `group` | 1개 이상 | split/merge 한 거래의 여러 wafer 행 |

group일 때 `group_by`는 `identity`의 부분집합이어야 한다. `identity`와 `group_by`에는
Preparer가 만든 EventFrame 컬럼을 쓸 수 있지만, `order_by`, `cursor`, `occurred_at`은 base
physical relation 컬럼이어야 한다.

---

## 4. `ledger_config.json` — 하나뿐인 파일과 그 최상위 모양

최상위는 `setup_version` 하나와 section **셋**, 그리고 선택 section 하나다.

```json
{
  "setup_version": 5,
  "vocabulary": {},
  "entities": {},
  "sources": {}
}
```

| 최상위 키 | 필수 | 용도 |
|---|---:|---|
| `setup_version` | 예 | 문법 세대. 현재 정확히 `5`. 다른 값은 `unsupported_setup_version` |
| `vocabulary` | 예 | 술어의 닫힌 서명 — **Role과 emission도 여기서 도출된다** (§7.1·§7.5) |
| `entities` | 예 | 개체 ID와 key shape (§7.2) |
| `sources` | 예 | 소스 하나 = `relation`+`read`+`prepare`+`map`+`bind` (§7.3·§7.4·§7.6·§7.7) |
| `virtual_joins` | **아니오** | verified read-only batch join (§6) |

정본은 `server/ledger/setup_bundle.py`의 `LOGICAL_SECTIONS`(필수 셋) ·
`OPTIONAL_SECTIONS`(`virtual_joins`) · `SETUP_VERSION`이다. **개수를 외우지 말고 거기서 읽어라.**

🔴 **셋은 비어 있어도 «있어야» 한다.** 키가 없는 것과 `{}`인 것은 읽는 사람에게 다른
뜻이고, 「이 section은 나에게 해당 없음」은 적어 둘 값어치가 있는 결정이다. 키 자체가
빠지면 `missing_field`다.

🔴 **`packs`는 이 표에 없다** (소유자 판정 2026-08-21, `9b6c5da`). 옮겨간 것이 아니라
**도출된다** — 문장이 `predicate`로 술어를 직접 대고, 그 술어의 vocabulary 항목이 Role
목록과 emission을 정한다(§7.5). 다시 적으면 `unknown_field`다.

🔴 **`source_preparers`·`mappers`·`profiles` 셋도 이 표에 없다** (소유자 판정 2026-08-20,
`087e7d8`·`d64f047e`). 없어진 것이 아니라 **본문이 소스 안으로 들어갔다** — §1의 이유와
§7.3·§7.4·§7.6이 그 이야기다. 옛 root는 §2.4의 마이그레이션이 올려 준다. 이 셋을 다시
최상위에 적으면 `unknown_field`로 거절된다.

🔴 **`tables`는 이 표에 없다. 없어진 것이 아니라 «옮겨간» 것이다** (소유자 판정,
2026-08-18: 「ledger json에 tables 왜 또 있어?」). 물리 스키마의 정본은
**`server/config/table_config.json`** 하나이고 §5가 그 이야기다. 이 파일에 `tables`를
다시 적으면 `unknown_field`(`ledger_config.tables`)로 거절된다 — 조용히 무시하지 않는
이유는, 아무도 읽지 않는 물리 선언이 파일 안에 앉아 있는 것이 바로 이 section을 없앤
이유이기 때문이다.

`setup_version` 하나가 예전 다섯 파일의 `schema_version` 다섯 개가 하던 말을 한다. 파일별
버전 필드는 **없다** — `schema_version`을 최상위에 적으면 `unknown_field`로 거절된다.
표 밖의 다른 키도 마찬가지다.

section 셋은 사용 여부와 관계없이 전수 검증된다. 아직 아무 문장도 가리키지 않는 술어도
unknown Entity/column을 숨길 수 없다. 모든 오류는 `code`, 정확한 JSON `path`, `message`로
돌아오며 여러 오류의 순서도 결정적이다.

### 4.1 root에 다른 JSON을 두지 않는다

로더는 config root **아래 어디든** `ledger_config.json`이 아닌 `.json`이 있으면
`unlisted_config_file`로 거절한다. 근거는 §2.1에 있다. 백업·초안·변환 결과는 root 밖에
둔다.

---

## 5. 물리 스키마는 `table_config.json`이 정본이다

🔴 **[2026-08-18 판정] `ledger_config.json`에는 `tables` section이 없다.** 원장이 물리
스키마를 물어야 할 때는 **`server/config/table_config.json`**을 읽는다. 이 절은 그 파일을
다시 설명하지 않는다 — 그 파일의 정본 설명은 [CONFIG_GUIDE](CONFIG_GUIDE.md)에 있다.
여기서는 **원장이 그 선언에서 무엇을 읽어 가는지**만 적는다.

### 5.1 왜 옮겼나

`lot_event`를 양쪽에서 대조한 실측(2026-08-18, 제거 직전):

| | `ledger_config.tables` | `table_config.json` |
|---|---|---|
| 컬럼 | 8 | 8 |
| 한쪽에만 있는 컬럼 | 없음 | |
| 타입이 다른 컬럼 | 없음 (8/8 일치) | |
| 업무 키 | `txn_seq` | `txn_seq` |

**같은 사실의 두 번째 사본이었다.** 그리고 **도는 코드 중 둘을 대조하는 것이 없었다**
(테스트 하나가 `lot_event` 한 relation만 못박고 있었을 뿐이고, 그 핀은 다음 relation에
대해서는 아무 말도 하지 않는다). 실제로 샘플 root 쪽 사본은 이미 **어디에도 없는 컬럼**으로
갈라져 있었고 아무 검사도 그것을 잡지 못했다.

🔴 **옮기면 실물 DB 대조가 공짜로 따라온다.** `server/schema_drift.py`(`_register_dynamic_models`)가
SQLAlchemy에 매핑된 표 전부를 훑는데, 여기에 `table_config.json`에서 만들어진 동적 표가
포함된다. 즉 `table_config.json`에 적힌 컬럼이 DB에 없으면 **이미 잡힌다**. 원장 전용
「선언 대 DB」 검사는 **만들지 않는다** — 검증기가 둘이면 둘이 어긋날 수 있고, 그것이 이
변경으로 없앤 바로 그 모양이다.

### 5.2 원장이 `table_config.json`에서 읽어 가는 것

| `table_config.json` 키 | 원장이 쓰는 곳 |
|---|---|
| `column_types` | preparer `input_columns`·mapper `input_columns`·`order_by`·`cursor.columns`·`occurred_at.column`·registration probe 컬럼이 **실재하는 컬럼인지** |
| `composite_key_source` | 그 컬럼 묶음이 **행의 유일 키**다. cursor 전순서 증거로 인정된다 |
| `business_key` | 그 컬럼이 `column_types`에 실재할 때만 유일 키로 인정된다 |

⚠️ **`map_key_columns`는 유일 키가 아니다.** 한 맵에 여러 행이 들어가는 조회용 접두사이므로
원장은 이것을 cursor 근거로 받지 않는다. 받으면 유일하지 않은 정렬을 커서로 승인하게 되고,
그 방향의 오류는 **이벤트를 잃는다**.

`business_key`, `composite_key_source`, 또는 `unique: true` index의 **전체 컬럼 집합**만
cursor 전순서의 증거가 된다. 컬럼이 존재한다는 사실, `identity`, `group_by`, 비-unique
index는 유일성 증거가 아니다. 예를 들어 `event_at`만으로 정렬하면 같은 시각의 두 행 순서가
불안정하므로 `invalid_cursor`다.

### 5.3 인제션이 쓰지 않는 표 — 그래도 `table_config.json`에 선언한다

**원장만 읽고 인제션은 쓰지 않는 표**(`void`가 그 모양이다)가 `table_config.json`에 없을 수
있다. 그때의 답은 **「`table_config.json`에 선언한다」**이지 「원장에 사본을 만든다」가
아니다. 그 파일이 이 시스템의 물리 스키마 정본이고, **선언하면 드리프트 검사와 그리드가
함께 따라온다.**

선언되지 않은 표를 소스가 가리키면 이름을 대며 거절한다.

```
unknown_relation @ bundle.sources.<id>.relation
  relation 'xxx' is not declared in table_config.json; declare the table there first
  — the ledger reads the physical schema from that file and an undeclared table has
  no columns, no key, and no drift check
```

🔴 이 거절은 **다른 컬럼 오류보다 먼저** 나온다. 표가 선언돼 있지 않으면 그 아래의 컬럼
불평은 전부 파생물이고 **엉뚱한 파일을 고치라고 가리킨다**.

### 5.4 다른 스키마의 배포는 자기 `table_config.json`을 가진다

샘플 root(`server/config/sample/ontology/transfer_explorer/`)는 **다른 공장**의 선언을
보여 준다. 그 배포의 물리 스키마는 그 배포의 `table_config.json`이고, 원장 config 안의
사본이 아니다. 샘플이 쓰는 것은
`server/tests/support/transfer_explorer_table_config.json`이다 — config root 안에 두지
않는 이유는 §4.1의 「root에 다른 JSON을 두지 않는다」가 그대로 적용되기 때문이다.

---

## 6. `virtual_joins` — verified read-only batch join (선택 section)

🔴 **이 section만 선택이다.** 운영 root(`server/config/ontology/ledger_config.json`)는
`virtual_joins`를 **갖고 있지 않다** — 그 자리에 있던 registry가 비어 있었고, enabled rule은
어차피 호출자가 물리 검증된 descriptor를 공급해야 승인되므로 잃은 것이 없다. 그러나
**로더는 이 section을 읽을 줄 안다**: `server/config/sample/ontology/transfer_explorer/`가
실제 descriptor를 공급한다. **파일에서 section을 뺀 것과 로더에서 지원을 뺀 것은 다른
일이고, 일어난 것은 앞의 것뿐이다.**

join이 필요 없으면 이 키를 아예 쓰지 않는다. 빈 `{}`를 두어도 되지만 없는 편이 낫다.

`transfer_explorer` 샘플의 실제 선언은 다음과 같다(파일 안 `virtual_joins` 값).

```json
{
  "dt_job_to_inventory": {
    "left_table": "dt_log",
    "right_table": "dt_inventory",
    "join_key": [
      {"left": "dt_job_id", "right": "dt_job_id"}
    ],
    "expose": [
      "dt_lot",
      "dt_slot",
      "dt_offset_x",
      "dt_offset_y",
      "bond_wafer",
      "bond_offset_x",
      "bond_offset_y",
      "bond_layer",
      "final_chip"
    ],
    "join_cardinality": "one",
    "enabled": true
  }
}
```

| 필드 | 필수 | 설명 |
|---|---:|---|
| rule ID | 예 | 예: `dt_job_to_inventory`. Source가 상속할 이름 |
| `left_table` | 예 | cursor가 읽는 base relation |
| `right_table` | 예 | read-only batch 조회할 relation |
| `join_key` | 예 | 1개 이상의 `{left, right}` 쌍 |
| `expose` | 예 | 오른쪽에서 EventFrame에 노출할 컬럼 목록 |
| `join_cardinality` | 예 | 현재 정확히 `"one"` |
| `enabled` | 예 | `true`인 rule만 상속 가능 |
| `fold` | 아니오 | 제한된 표기 정규화 선언. 임의 식/SQL/Python이 아니다. |

### 6.1 join이 승인되려면

1. 왼쪽·오른쪽 relation과 모든 컬럼이 `table_config.json`에 선언돼 있어야 한다.
2. 오른쪽 `join_key.right` 전체를 정확히 덮는 catalog 유일 키 또는 UNIQUE index가 있어야
   한다.
3. 실제 PostgreSQL의 해당 UNIQUE index를 physical verifier가 확인해야 한다.
4. Preparer의 `input_columns`가 모든 `join_key.left`를 포함해야 한다.
5. Preparer가 `accepts_verified_join_rules: true`여야 한다.
6. Source의 `inherit_virtual_join_rules`에 rule ID를 명시해야 한다.

config의 `unique: true`만으로 `VerifiedJoinDescriptor`를 만들 수 없다. descriptor의 유일한
정상 발급 경로는 physical verifier 성공 결과다. raw mapping이나 임의 index 이름을 직접
주입하는 production API는 봉인돼 있다.

### 6.2 실행 의미

- 키를 모아 기본 1,000개 단위 read-only batch query를 수행한다.
- 0건은 `missing`, 2건 이상은 `ambiguous`로 mapper 전에 거절한다.
- 필요한 expose 값이 비면 `incomplete`로 거절한다.
- EventFrame에 이미 존재하는 이름과 expose가 충돌하면 조용히 덮지 않고 거절한다.
- V2 Source Preparer에서는 기존 일반 UI virtual join의 “빈 값만 채우기” 규칙을 재사용하지
  않는다. V2는 collision 자체를 구성 오류로 본다.
- N+1 query를 허용하지 않는다.

`fold`를 쓸 때는 현재 verifier가 지원하는 닫힌 표기만 사용한다. 현재 구현되지 않은
`zero_pad`나 임의 `sql`, `python`, `expression`을 선언하면 거절된다.

---

## 7. 의미와 실행 section

여기부터는 §4 표의 최상위 section 둘과 **소스가 직접 드는 절 다섯**을 하나씩 본다. 아래의
JSON 블록은 모두 `ledger_config.json` 안 해당 키의 **값**이다.

| 절 | 사는 곳 |
|---|---|
| §7.1 `vocabulary` · §7.2 `entities` | 최상위 section (재사용된다) |
| §7.3 `prepare` · §7.4 `map` · §7.6 `bind` · §7.7 `relation`+`read` | `sources.<id>` 안 |
| §7.5 술어가 강제하는 Role | **선언이 아니다** — `vocabulary` 항목에서 도출된다 |

### 7.1 `vocabulary` — 술어의 닫힌 서명

`lot_event`가 쓰는 술어 넷의 **발췌**다(파일에는 다른 소스가 쓰는 술어도 함께 있다).

```json
{
  "register@1": {
    "status": "active",
    "subjects": ["Lot@1", "Wafer@1"],
    "object": {
      "kind": "none",
      "qualifiers": {"required": [], "optional": []}
    }
  },
  "has_wafer@1": {
    "status": "active",
    "subjects": ["Lot@1"],
    "object": {
      "kind": "entity_ref",
      "types": ["Wafer@1"],
      "qualifiers": {"required": ["slot"], "optional": []}
    }
  },
  "derived_from@1": {
    "status": "active",
    "subjects": ["Lot@1"],
    "object": {
      "kind": "entity_ref",
      "types": ["Lot@1"],
      "qualifiers": {"required": [], "optional": []}
    }
  },
  "slot_map@1": {
    "status": "active",
    "subjects": ["Lot@1"],
    "object": {
      "kind": "entity_ref",
      "types": ["Lot@1"],
      "qualifiers": {
        "required": ["from", "to", "wafer"],
        "optional": []
      }
    }
  }
}
```

위 블록은 `ledger_config.json`의 `vocabulary` 값만 발췌한 **section fragment**다.

| 필드 | 허용값/용도 |
|---|---|
| Vocabulary ID | 반드시 versioned ID, 예: `has_wafer@1` |
| `status` | `active` 또는 `retired` |
| `subjects` | 허용되는 versioned Entity ID 목록 |
| `object.kind` | `none`, `entity_ref`, `value`, `event_ref` |
| `object.types` | `entity_ref`일 때 허용되는 Entity ID 목록 |
| `object.qualifiers.required` | 문장이 반드시 공급해야 하는 qualifier 이름. 🔴 **각 이름이 그대로 필수 Role이 된다**(§7.5) |
| `object.qualifiers.optional` | 선택적으로 공급할 수 있는 qualifier 이름. 각 이름이 그대로 «선택» Role이 된다 |

required와 optional은 겹칠 수 없다. `object.kind: "none"`에는 qualifier나 type을 붙일 수
없다. `slot_map@1`을 내는 문장이 `from`, `to`, `wafer` 중 하나를 빠뜨리면
`missing_required_payload`, 선언하지 않은 이름(`depth` 같은 것)을 추가하면
`unknown_payload_field`로 거절한다.

🔴 **[2026-08-22 `ddc93f5b`] `layer`는 항목에서 «없어졌다» — 지금 적으면 `unknown_field`로
거절된다.** 문법이 아무 비어 있지 않은 문자열이나 받았지만 **작성자가 쓸 수 있는 값은
하나뿐**이었다: 시스템이 아는 층은 둘이고 `canonical`은 코드 소유라 `ontology`가 선언 가능한
집합의 전부였다. 자유도 0인 칸은 계약이 아니라 상수의 사본이다([PRIMITIVES §3](../architecture/PRIMITIVES.md)).
읽는 쪽은 **손대지 않았다** — config explorer가 술어 노드 설명을 `raw.get('layer', 'ontology')`로
만드는데 그 기본값이 바로 그 유일 합법값이라, 필드가 사라져도 설명이 **바이트까지 같다.**
옛 파일은 `server/scripts/migrate_ledger_config_drop_vocabulary_layer.py`가 올린다 —
`ontology` 아닌 값을 들고 있으면 **아무것도 쓰지 않고 그 값을 대며 거절**하고, 두 번 돌리면
「변화 없음」이라 답한다. `setup_version`은 **일부러 안 올렸다**(두 자리 모두 등가 비교라
버전으로 분기하는 코드가 없고, 안 올린 파일은 이미 이름 대어 거절된다 — 올리면 같은 말을
하는 거절이 하나 더 생기고 번호만 틀린 백업이 전부 무효가 된다).

Vocabulary는 “어떤 문장이 문법적으로 가능한가”를 정한다. 실제 source 컬럼은 여기에 쓰지
않는다.

### 7.2 `entities` — 개체 ID와 key shape

`lot_event`가 쓰는 두 개체의 실제 선언이다.

```json
{
  "Lot@1": {"keys": ["lot"]},
  "Wafer@1": {"keys": ["wafer"]}
}
```

이 역시 `entities` section fragment다 — 파일에는 다른 소스의 개체도 함께 선언돼 있다.

| 필드 | 필수 | 설명 |
|---|---:|---|
| Entity ID | 예 | versioned ID, 예: `Lot@1` |
| `keys` | 예 | 개체를 식별하는 논리 key 이름. 비어 있거나 중복될 수 없다. |
| `key_types` | 아니오 | key 이름 → trimmed nonblank type 문자열. 키 집합은 `keys`와 정확히 같아야 한다. |
| `allow_null` | 아니오 | 명시적 boolean. 생략 시 null key를 허용하는 것으로 추측하지 않는다. |

여기서 `lot`은 논리 key 이름이지 반드시 물리 컬럼명일 필요는 없다. 소스 A의 `bind`는
`lot_id`를, 소스 B의 `bind`는 `batch_name`을 같은 `Lot@1.keys.lot`에 binding할 수 있다.
이것이 source 이름과 column 이름이 바뀌어도 같은 술어를 재사용할 수 있는 이유다.

복합 개체 예시는 다음과 같다.

```json
{
  "Die@1": {
    "keys": ["wafer", "x", "y"],
    "key_types": {
      "wafer": "string",
      "x": "number",
      "y": "number"
    },
    "allow_null": false
  }
}
```

`key_types.x`에 객체, 배열, null, bool, 숫자 자체, blank 문자열을 넣으면 구조화된 오류로
거절한다. 닫힌 type enum은 현재 계약에 없으므로 임의 enum을 발명하지 않는다.

### 7.3 `sources.<id>.prepare` — 물리 batch를 EventFrame으로 준비

`lot_event`의 preparer 절이다. **이름이 없다** — 이 본문이 곧 그 소스의 준비 단계이지,
어딘가에서 참조되는 별도 선언이 아니다.

```json
"prepare": {
  "implementation_id": "lot-event-live-frame",
  "implementation_version": 1,
  "input_columns": [
    "lot_id",
    "event_type",
    "slotnumbers",
    "waferids",
    "parent_lot",
    "child_lot",
    "txn_seq",
    "event_time"
  ],
  "output_columns": {
    "lot": "string",
    "slots": "string",
    "wafers": "string",
    "row_identity": "string",
    "event_group_key": "string",
    "__source_event_incomplete": "boolean",
    "__source_row_excluded": "boolean"
  },
  "accepts_verified_join_rules": false,
  "inherit_virtual_join_rules": []
}
```

| 필드 | 설명 |
|---|---|
| `implementation_id` | trusted code catalog에서 찾을 구현 이름 |
| `implementation_version` | 구현 계약 버전. **재사용되는 것은 이 «코드»이지 선언이 아니다.** |
| `input_columns` | base physical SELECT와 join left key로 필요한 컬럼 전수 |
| `output_columns` | Mapper가 받을 EventFrame 컬럼명 → 타입 문자열 |
| `accepts_verified_join_rules` | physical verification을 통과한 join descriptor 수용 여부 |
| `inherit_virtual_join_rules` | 상속할 `virtual_joins` 규칙 이름 목록(§6). 안 쓰면 `[]` |

여섯 필드 **전부 필수**다(빈 목록이라도 적는다). 정본은
`setup_bundle._validate_preparation`.

🔴 **이 절에 «id»는 없다** (소유자 판정 2026-08-20 「소스플랜 준비기 맵퍼」, `087e7d8`).
preparer의 `input_columns`는 물리 relation의 컬럼이어야 하는데 `relation`을 선언하는 것은
소스뿐이라, 자기 section에 앉은 preparer는 자기를 검사해 줄 유일한 선언에서 한 홉 떨어져
있었다. 옮긴 뒤 실측된 것이 그 대가다 — mapper가 받을 수 있는 입력 후보가 `lot_event`에서
**8개(물리 표)에서 14개(8 + preparer가 만드는 6)로** 늘었다. 그 여섯은 정확히 위
`output_columns`이고, 옮기기 전에는 mapper에게 **존재를 알릴 방법이 없었다.**

Preparer는 source별 정규화·그룹 조립·virtual join 적용·결측 판정을 담당한다. Claim이나
LedgerFrame을 만들지 않는다.

#### 두 예약 컬럼 — 준비기가 말할 수 있는 두 문장 (`8bb0f5f1`)

`output_columns`에 **선언했을 때만** 뜻이 생기는 이름 둘이 있다. 둘 다 base 행마다 하나씩
나오는 boolean이고, 선언하지 않은 소스는 이 경로를 **구별할 수 없다.**

| 예약 컬럼 | 준비기가 하는 말 | 엔진이 하는 일 |
|---|---|---|
| `__source_event_incomplete` | 「이 source event의 행이 다 오지 않았다」 | 착지시키되 `incomplete_molecules`로 센다 — 거절이 아니다 |
| `__source_row_excluded` | 「이 행은 **내 것이 아니다**」 | 신원 루프 **전에** 그 행들만 뺀다 |

🔴 **`__source_row_excluded`는 가드를 «낮추는» 것이 아니라 «좁히는» 것이다.**
`lot_event`에는 같은 사실을 다르게 철자하는 세대가 둘 섞여 있고(한쪽은 `lot_id`,
다른 쪽은 `lot`) 준비기가 읽는 것은 첫 철자뿐이라, 둘째 세대의 행은 신원 루프에 **빈 채로**
도착해 **배치를 통째로 거절시켰다.** 살아남은 행은 여전히 전부 신원을 요구받고 거절문도
그대로다 — 「빈 `lot`은 우리 것이 아니다」라는 지식이 **그 소스의 준비기 안에** 남는 것이
이 모양의 값어치다.

- 준비기의 다른 두 계약(**base 행당 정확히 하나** · **base 값을 바꾸지 않음**)은 **먼저
  채점된 뒤에** 제거가 일어나므로 손상되지 않는다.
- boolean이 아닌 값이 하나라도 있으면 `invalid_source_preparer_output`으로 거절한다.
- **페이지 전체가 배제돼도 거절이 아니다** — 빈 EventFrame과 원자 0으로 지나간다. 페이지를
  자르는 것은 cursor이지 세대가 아니라서 옛 행만 든 페이지는 정상이고, 거절하면 백필이
  거기서 영영 선다. cursor는 **base 페이지**에서 전진하므로 배제된 행을 다시 읽지 않는다.

입력과 출력 이름은 충돌할 수 없다. 출력은 base physical catalog 컬럼과도 충돌할 수 없다.
join을 상속하면서 left key가 `input_columns`에 없거나 `accepts_verified_join_rules`가 false면
실행 불가능한 sealed plan이 되지 않도록 compile 전에 거절한다.

Config는 Python module/function/path를 지정할 수 없다. 다음은 금지다.

```json
{
  "implementation_id": "my.module:prepare",
  "python": "lambda row: row",
  "sql": "SELECT * FROM secret"
}
```

🔴 **먼저 `direct-join@1`을 본다 — 대개 Preparer 코드는 필요 없다.**
`ledger.source_preparation.DirectJoinSourcePreparer`는 계산을 하지 않는 범용 Preparer로,
선언한 출력 컬럼 각각이 상속한 verified join 정확히 하나에 의해 expose되면 그대로 쓴다.
`transfer_explorer` 샘플이 이것을 쓴다. 정규화·그룹 조립처럼 **계산이 필요할 때만** 새
구현을 만든다.

새로운 실행 모양이 필요하면 `BaseSourcePreparer` 하위 클래스를 코드에 추가한다. 클래스가
자기 `implementation_id`/`implementation_version`을 스스로 선언하고
`server/ledger/implementations.py`가 그것을 **코드에서 발견해** 신뢰 집합을 만든다. 별도
목록에 이름을 다시 적을 곳은 없다.

### 7.4 `sources.<id>.map` — EventFrame에서 Role만 해석

`lot_event`의 mapper 절이다. §7.3과 같이 **이름이 없다.**

```json
"map": {
  "implementation_id": "lot-event-role",
  "implementation_version": 1,
  "unit": {"kind": "event"},
  "input_columns": [
    "lot",
    "event_type",
    "slots",
    "wafers",
    "parent_lot",
    "child_lot",
    "row_identity",
    "event_time",
    "event_group_key",
    "__source_event_incomplete"
  ]
}
```

| 필드 | 설명 |
|---|---|
| `implementation_id/version` | trusted mapper 코드 선택 |
| `unit.kind` | `event`, `row`, `group_by` 중 하나 |
| `unit.columns` | `group_by` mapper에서만 필요한 grouping columns |
| `input_columns` | Preparer가 만든 EventFrame에서 mapper가 읽을 컬럼 전수 |

Mapper는 Atom, predicate payload, Ledger 7컬럼을 직접 만들지 않는다. 공통
`BaseLedgerMapper.map()` 경계를 통해 `RoleEmission`만 반환한다. subject/object/time/qualifier
shape는 RoleFrame compiler가 소유한다.

🔴 **`emits`는 없다. 없는 것이 요점이다** (소유자 판정 2026-08-21: 「클레임과 맵퍼 함수는
완전 별개인데 왜 맵퍼에서 쓸 클레임을 정의함?」 → 「닿을 수 없다면 선언도 닿으면 안됨」,
`a55f3059`). mapper 구현이 아는 것은 `SentenceShape`이지 **claim이 아니다** — 「이 mapper가 낼
수 있는 claim」은 그 코드가 답할 방법이 없는 질문이었다. 답을 아는 유일한 선언은
`bind.mappings.<문장>`이므로, 필드는 옮겨간 것이 아니라 **사라졌다**:
`MapperDescriptor.emits`는 이제 그 문장들이 대는 술어에서 **compile 시점에 도출된다.**
그래서 둘이 어긋날 수 없고, 어긋남을 보던 규칙도 함께 없어졌다.

이것이 이 파일의 일반 규칙이다 — **코드가 닿을 수 없는 것은 선언도 닿지 않는다.** 자유도
0인 선언은 계약이 아니라 사본이고, 사본은 조용히 갈라진다.

🔴 **단순한 소스는 mapper 코드를 쓰지 않는다.** `ledger.roleframe.DeclarativeRoleMapper`
(`implementation_id: "declarative-role"`, version 1)는 Profile이 선언한 column/constant/entity
binding을 그대로 평가하는 범용 mapper다. 어느 특정 source도 알지 못하고 DB에 접근하지
않는다. **업무적 읽기가 binding만으로 표현되는 소스는 이 이름을 적으면 끝이다** —
`transfer_explorer` 샘플이 그렇게 한다. 위 `lot-event-role@1`처럼 전용 mapper가 필요한 것은
행을 쪼개거나 도메인 규칙으로 해석해야 할 때뿐이다.

전용 mapper를 새로 만든다면 **파일 하나**다: `server/mappers/ledger_v2_*.py`에
`BaseLedgerMapper` 하위 클래스를 쓰고 클래스가 자기 `implementation_id`와
`implementation_version`을 선언한다. `server/ledger/implementations.py`는 편집하지 않는다 —
그 모듈이 발견해 간다.

### 7.5 Role은 «선언하지 않는다» — 술어가 강제한다 (`9b6c5da`)

🔴 **`packs` section은 없다.** 2026-08-20까지 이 자리에는 Pack이 있었고, Pack 안의 Claim이
Role 목록과 `emit` 절을 선언했다. 둘 다 **그 Claim이 내던 술어가 이미 강제하던 것**이라
지웠다(§1의 실측). 지금 문장이 적는 것은 술어 이름 하나뿐이고, 그 술어의 §7.1 항목이
**어떤 Role이 있어야 하는지**를 정한다.

도출의 정본은 함수 하나, `setup_bundle.predicate_claim`이다. 컴파일러·검증기·작성 화면이
**같은 함수 하나**를 읽는다 — 서로 동의하는 선언 셋이 아니라.

| 술어의 `object.kind` | 도출되는 Role |
|---|---|
| 언제나 | `subject` (`entity`, 필수) · `occurred_at` (`time`, 필수) |
| `none` | 그 둘뿐 |
| `entity_ref` | + `target` (`entity`, 필수) |
| `value` | + `value` (`quantity`, 필수) |
| `event_ref` | + `value` (`identity`, 필수) |
| `object.qualifiers.required[]` | 각 이름이 **그 이름 그대로** Role(`attribute`, 필수) |
| `object.qualifiers.optional[]` | 각 이름이 **그 이름 그대로** Role(`attribute`, 선택) |

그래서 `register@1`(`object.kind: "none"`)은 `subject`·`occurred_at` 둘을 요구하고,
`has_wafer@1`(`entity_ref` + required qualifier `slot`)은
`subject`·`target`·`occurred_at`·`slot` 넷을 요구한다. 🔴 **양끝의 이름은 상수다** —
`subject`/`target`이지 `$child`/`$parent`가 아니다. vocabulary가 `subjects`로 말하는 것은
그 자리에 올 수 있는 **entity 타입**이지 자리의 «이름»이 아니어서, 술어마다 철자를 정하게
두면 대조할 것이 없는 자유 선택이 된다.

**작성자가 할 일은 Role을 «고르는» 것이 아니라 술어를 고르는 것이다.** 화면도 그렇게
동작한다 — 술어를 고르면 그 술어가 강제하는 칸이 **선언된 이름 그대로** 깔린다. 그것이
section을 지운 것이 작성자에게 부담을 넘기는 일이 아니라 단순화가 되는 절반이다.

#### Role kind와 binding 종류

| 항목 | 지금 값 |
|---|---|
| `kind` | 도출된다: `entity` · `time` · `quantity` · `identity` · `attribute` |
| `required` | 도출된다: qualifier의 `optional[]`만 `false`, 나머지는 전부 `true` |
| 허용 binding | entity Role은 `entity`, 나머지는 `column`과 `constant`(`role_binding_kinds`의 기본값) |

⚠️ **`allowed_binding_kinds`·`allowed_values`를 적을 자리는 이제 «없다».** 읽는 코드는
남아 있지만(`setup_registry.RoleDescriptor`·`roleframe`의 symbolic 검사·
`setup_bundle`의 `invalid_symbolic_constant`) **그것을 채워 줄 유일한 생산자였던 Claim이
사라졌으므로** `predicate_claim`이 내는 Role에는 두 키가 붙지 않는다. 같은 이유로 Role
kind `symbolic`과 `order`도 **도출될 수 없다.** 좁힌 binding이나 닫힌 상수 목록이 실제로
필요해지면 그것은 config 수정이 아니라 **코드 라운드**다 — 총괄에 가져간다.

### 7.6 `sources.<id>.bind` — 그 Source 컬럼을 술어의 Role에 binding

아래는 `lot_event`의 `first_sight_holder` mapping 전체다.

```json
"bind": {
  "mappings": {
    "first_sight_holder": {
      "predicate": "register@1",
      "bind": {
        "subject": {
          "kind": "entity",
          "entity_type": "Lot@1",
          "keys": {
            "lot": {
              "kind": "column",
              "column": "lot"
            }
          }
        },
        "occurred_at": {
          "kind": "column",
          "column": "event_time"
        }
      }
    }
  }
}
```

이 블록은 문법 설명을 위한 **발췌**다. 실제 `lot_event.bind`에는 여섯 mapping이 있고,
정본은 `server/config/ontology/ledger_config.json`이다.

| `bind` 필드 | 설명 |
|---|---|
| `mappings` | **문장 이름 → mapping**인 객체. 비어 있을 수 없다 |
| `mappings.<문장>` | 그 키가 곧 이 mapping이 실현하는 **문장의 이름**이다 (아래) |
| `mappings.<문장>.predicate` | 이 문장이 내는 **vocabulary id**. 예: `register@1` |
| `mappings.<문장>.bind` | **그 술어가 강제하는** Role 이름 → binding (§7.5) |

`bind`의 필드는 지금 `mappings` 하나뿐이지만 **record로 남는다**(소유자 판정: 「ㅇㅇ 남겨」)
— `bind: [...]`로 접으면 `mappings` 말고 다른 것이 들어오는 날 마이그레이션을 하며 다시
펼쳐야 한다.

🔴 **`source`도 `packs`도, `use`도 없다.** `source`는 한 단계 위 키의 되풀이였고
`_cross_validate`가 그 키 외의 값을 전부 거절했으므로 **작성자가 할 수 있는 일이 「틀리게
쓰기」뿐이었다**(`d64f047e`). `packs`는 그 mapping들이 부르는 pack 집합을
`sorted(set(...))` 한 것을 양방향으로 대조하던 값이라 역시 자유도가 0이었다(`a55f3059`).
`use`(`<pack>@v/<claim>`)는 **`predicate`가 됐다**(`9b6c5da`) — Claim이 하던 말이 술어에서
도출되고 나니 Pack 이름과 Claim 이름은 술어 이름에 딸린 **두 번째 주소**였다.

#### mapping의 키가 곧 문장 별명이다 (`e795c706`)

옛 모양은 `mappings`가 **배열**이고 각 항목이 `mapping_id`와 (선택) `sentence`를 들었다.
어느 mapping이 어느 문장을 실현하는지는 **탐색**이었다 — 목적어 유무를 비교하고, qualifier
집합을 비교하고, subject type으로 떨어지고, object type으로 떨어지고, **마지막에야** 이름을
봤다. 그런데 이름은 양쪽이 이미 합의하고 있던 유일한 것이었다: mapper는 그것을
`SentenceShape` 속성으로 선언하고 config는 그것을 가리킨다.

그래서 mapping은 이제 **그 별명으로 키가 매겨지고 해석은 dict 조회 한 번**이다.
`mapping_id`와 `sentence`는 이름 둘을 쓰고 있던 같은 문자열이었고, 살아남은 쪽은 **mapper가
실제로 선언하는 쪽**이다.

```text
bind.mappings.counted.predicate       has_netdie@1
bind.mappings.first_sight_holder      lot_event의 FIRST_SIGHT, 「가진 쪽」에 대해
bind.mappings.first_sight_item        그리고 「담긴 쪽」에 대해
```

구조 탐색이 **실제로** 실패하고 있던 자리가 바로 저 둘이다. `lot_event`는 `FIRST_SIGHT`를 두
번 내는데 구조만으로는 구별이 안 돼 `subject_type`을 넘겨야 했다. 별명 밑에서는 그냥 이름이
둘이고, selector 인자는 할 일이 없어졌다. 문장 일곱이 mapping 여덟을 섬기던 것이 여덟 이름이
됐다.

`mappings`는 비어 있을 수 없고(`invalid_profile`) 각 mapping은 `predicate`와 `bind` **정확히
둘**을 든다. 어느 술어를 쓰는지는 **각 mapping의 `predicate`가 말한다** — 그것을 다시 모아
적는 자리는 없다.

#### binding 종류

V2 canonical binding은 다음 세 가지뿐이다.

**column** — EventFrame의 컬럼 값을 쓴다.

```json
{
  "kind": "column",
  "column": "event_time"
}
```

**constant** — config에 명시한 결정적 JSON 값을 쓴다.

```json
{
  "kind": "constant",
  "value": "track_in"
}
```

constant는 임의 문자열을 무조건 통과시키지 않는다. null 허용 여부는 Role 계약(`required`)을
따른다. ⚠️ symbolic Role의 `allowed_values` 검사는 코드에 남아 있지만 **그 목록을 선언할
자리가 없다** — 사유는 §7.5.

**entity** — Entity type과 그 논리 key 각각을 nested column/constant로 조립한다.

```json
{
  "kind": "entity",
  "entity_type": "Die@1",
  "keys": {
    "wafer": {
      "kind": "column",
      "column": "core_wafer"
    },
    "x": {
      "kind": "column",
      "column": "core_x"
    },
    "y": {
      "kind": "column",
      "column": "core_y"
    }
  }
}
```

Entity key 집합은 Entity descriptor의 `keys`와 정확히 같아야 한다. nested key binding도
각자 승인 metadata를 가져야 한다.

`declared_lookup`, Position, Frame, SQL/Python/JavaScript expression은 canonical V2 binding이
아니다. 외부 값을 붙여야 하면 Source Preparer의 verified batch join으로 EventFrame column을
만든 뒤 `column` binding을 쓴다.

#### binding 승인 metadata — **은퇴했다 (2026-08-22)**

> 🔴 **`binding_origin` · `approval_status` · `suggestion_reason` 셋은 선언에서 «없어졌다».**
> binding은 이제 **종류와 그 payload만** 말한다 — `kind` + (`column` | `value` | `entity_type`·`keys`).
>
> **왜:** 소유자가 화면에서 그 셋을 보고 「바인딩이 이렇게 복잡하게 할 일이야? 그냥 주어, 목적어
> 등 당 타입, 키만 입력하게 해」라고 판정했다. 실측이 뒷받침했다 — 라이브 40개 binding에서
> `approval_status`는 **40번 다 `approved`**(자유도 0), `binding_origin`과 `suggestion_reason`은
> **0번** 선언됐고 `binding_origin`을 읽는 유일한 분기(`system_suggested`)를 **만드는 코드가 없었다**.
> 실행을 막던 `_binding_readiness_issues`의 승인 게이트도 필드와 «같이» 나갔다.
>
> **옛 파일은 그대로 열린다.** 검증기는 이 «세 이름만» 받아서 버린다(`_Problems.exact(..., ignored=)`,
> 호출부 둘). 일반화가 아니라 세 낱말짜리 목록이라, `approval_statuss` 같은 오타는 여전히
> `unknown_field`로 자기 경로에서 잡힌다. 마이그레이션은 급하지 않다 — 있어도 없어도 돌아간다.
>
> ✅ **이 문서의 JSON 예시에서도 그 줄은 걷어냈다** (9곳). 복사해서 쓰면 그대로 맞는다.

<details><summary>은퇴 전 판정 (읽을 필요 없다 — 왜 «둘 중 하나만» 접혔는지의 기록)</summary>

둘은 대칭으로 «보이고» 대칭이 아니었다 (`a55f3059`). `user_declared`는 가장 밋밋한 저작권
주장이라 적어도 아무것도 더 허락하지 않고, 이 필드를 읽는 유일한 규칙(`suggestion_reason` 요구)은
`system_suggested`에서만 발화했다. 그래서 안 적은 것과 `user_declared`라 적은 것이 같은 주장이었고
상수 40번이 운영자 파일에서 빠졌다. `approval_status`는 그럴 수 없어서 필수로 남았다 —
`roleframe._evaluate_binding`이 `approved`라 말하지 않은 binding을 실행하지 않고, 레거시 v1
리더가 같은 부재를 `pending`으로 읽었기 때문이다. **침묵은 아무것도 허락하지 않는 값에만 기본값을
줄 수 있다** — 그 문장은 지금도 참이고, 다만 그 필드가 «없어져서» 물을 일이 없어졌다.

</details>

🔴 **「받아서 버린다」는 «지운다»가 아니다.** 옛 파일에 남아 있는 세 이름은 canonical bundle에
**그대로 실려 간다** — 떼어 내면 소스마다 cursor fingerprint가 움직여, 이제 아무 뜻도 없는
낱말 하나 때문에 **돌던 커서가 선다.** 바뀐 것은 그 이름이 **어떤 결정에도 도달하지 않는다**는
것뿐이다(실측: 이 변경 전후로 bundle 해시·snapshot 해시·소스 지문 둘이 전부 동일).

🔴 **그래서 「binding 승인」이라는 실행 관문은 더 이상 없다.** 종전에 여기 있던
「`pending`/`rejected` binding은 실행 진입점마다 readiness gate가 차단한다」는 **거짓이 됐다** —
그 게이트가 필드와 함께 나갔다(`roleframe`·`source_profile` 양쪽). 준비 안 된 소스를 붙드는
자리는 §8 하나뿐이다: **`sources`에 적지 않는 것.**

#### mapper는 여전히 선언의 낱말을 모른다

전용 mapper는 **선언의 이름을 모른다.** predicate 철자도, entity type 철자도 mapper 코드에
없다 — 그것들은 배포마다 바뀌는 운영자의 낱말이기 때문이다. mapper가 아는 것은
**문장**(`ledger.roleframe.SentenceShape`)이고, 그 문장에 붙은 **별명**이 곧
`bind.mappings`의 키다. 그래서 술어를 다른 것으로 바꿔 달아도 mapper는 그대로다.

바뀐 것은 **찾는 방법**이다(§7.6). 옛 `ProfileSentences`는 목적어 유무 · qualifier 집합 ·
subject/object entity type으로 모양을 계산해 후보를 골랐고, 그래도 갈라지지 않으면
`ambiguous_sentence`로 거절했다. 지금은 별명이 키라서 조회 한 번이고, `_sentence_signature`·
`_ambiguous_sentences`·`has_object`와 `say()`가 받던 `subject_type`/`object_type` selector가
**표현할 수 없는 상태가 돼서** 함께 없어졌다.

`qualifiers`는 남는다. `say()` 안에서 **두 번째 용도**로 읽히기 때문이다 — 내보내는 키가
그 문장이 선언한 키인지 자기 검사한다. 그건 mapping을 고르는 일과 무관하고, 두 용도를 한
덩이로 접었다면 「matcher를 지웠다」면서 자기 검사를 지운 것이 됐을 것이다.

### 7.7 `sources` — 한 source 실행 계약으로 조립

`lot_event` source 선언 전체다(`bind` 본문은 §7.6). `sources`에는 다른 소스도 함께 있다 —
지금 무엇이 선언돼 있는지는 §13.2의 dry-run이 답한다.

```json
{
  "lot_event": {
    "relation": "lot_event",
    "read": {
      "unit": "group",
      "identity": ["event_group_key"],
      "group_by": ["event_group_key"],
      "order_by": ["event_time", "row_id"],
      "occurred_at": {
        "column": "event_time",
        "timezone": "Asia/Seoul"
      },
      "cursor": {
        "columns": ["event_time", "row_id"]
      }
    },
    "prepare": { },
    "map":     { },
    "bind":    { "mappings": { } }
  }
}
```

🔴 **`driver`는 한 키로 두 일을 부르고 있어서 없어졌다** (소유자 판정 2026-08-21: 「애초에
지금 컨피그 스키마가 잘못돼 있는건데」, `a55f3059`). 물리 batch를 읽는 것과 그것을 문장으로
바꾸는 것은 **다른 컬럼 우주 위의 다른 단계**인데 한 키가 둘을 다 이름 붙이고 있었다 —
전날 「preparer를 어디 둘 것인가」에 한 라운드를 통째로 쓰게 만든 것이 그것이다.

다섯 절은 `relation`의 **형제**로 서고, 문서가 읽히는 순서는 **실행이 일어나는 순서**다.
파일은 `sort_keys=True`로 쓰이므로 디스크에서는 `bind · map · prepare · read` 순으로 앉는데,
그건 정규 해시 재료라서 고치지 않는다 — **읽는 순서는 스켈레톤이 만든다**(화면 라벨
읽기 · 준비 · 매핑 · 연결. 키는 영어 그대로).

| 필드 | 설명 |
|---|---|
| source ID | **여기 있으면 이 소스는 돈다**(§8) |
| `relation` | `table_config.json`이 선언한 base physical relation. **안 옮겼다** — `prepared_columns`가 여기서 출발한다 |
| `read.unit` | `row` 또는 `group`. 🔴 **작성 화면이 «채워 주지 않는» 칸이다** — 채우면 드롭다운이 사라져 새 소스에서 고를 수가 없어진다(2026-08-22 판정) |
| `read.identity` | 결정적인 source event identity 컬럼 |
| `read.group_by` | group event 조립 컬럼. row이면 빈 배열. 화면은 **파일이 아무 말도 안 할 때만** `identity`로 채운다 — 검증기가 「`identity`의 부분집합」만 요구하므로 진부분집합이 합법이고, 무조건 채우면 그런 선언을 빨갛게 칠한다 |
| `read.order_by` | physical read order. catalog UNIQUE key 전체를 포함해야 함. 화면은 `table_config.json`이 선언한 **가장 짧은 유일 키**를 기본값으로 낸다 |
| `read.occurred_at.column` | 세계 시각을 담은 physical column |
| `read.occurred_at.basis` | 표에 세계 시각이 **없을 때** `column` 대신. 현재 `"ingested"` 하나 |
| `read.occurred_at.timezone` | 명시적 IANA timezone. 묵시 기본값 없음 |
| `read.cursor.columns` | physical keyset cursor 컬럼. 🔴 **[2026-08-22 `90383987`] 더 이상 «묻지 않는다»** — `read.order_by`에서 파생돼 번들에 쓰인다(아래) |
| `read.registration_probe` | 이미 등록된 개체를 가려내는 probe. **`bind`가 `register@1`을 내는 소스에는 필수** |
| `prepare` | 이 소스의 preparer 본문 (§7.3) |
| `map` | 이 소스의 mapper 본문 (§7.4) |
| `bind` | 이 소스의 문장 별명 → Role binding (§7.6) |

`read`의 여섯(`unit`·`identity`·`group_by`·`order_by`·`occurred_at`·`cursor`)은 번들에 전부
있어야 하고 `registration_probe`만 문법상 선택이다. **다만 사람이 적는 것은 다섯이다** —
`cursor`는 아래대로 파생된다. `occurred_at`의 `column`과 `basis`는 **정확히 하나**여야 한다 —
둘 다 적거나 둘 다 없으면 거절된다. 자세한 것은 §7.9.

🔴 **[2026-08-22 `90383987`] `read.cursor`는 «질문»에서 빠졌지 «문서»에서 빠지지 않았다.**
`setup_bundle._derived_cursor`가 번들을 만들 때 소스마다 `read.cursor.columns`를
`read.order_by`로 **덮어쓴다.** 아래 전부가 그 값을 계속 읽으므로 한 줄도 안 바뀐다 —
`setup_registry`가 compile하고, `backfill`이 페이지를 그것으로 정렬해 watermark를 만들고,
`runtime_v2`가 커서 튜플을 그것에 대조하고, `source_preparation`이 그 컬럼들의 생존을 요구한다.
- **왜 「빈 자리만 채우기」가 아니라 «덮어쓰기»인가.** watermark는 **읽기가 실제로 돈 순서로만**
  표현될 수 있다. `order_by`와 다른 커서는 두 번째 의견이 아니라 **읽는 쪽이 지킬 수 없는
  페이지 경계**다. 부재한 것만 채우면 어긋난 선언들이 살아남고, 검증기는 이제 그 키를 아예
  안 보므로 **살아 있으면서 검사도 안 받는** 상태가 된다.
- **어긋난 것이 실제로 있었다.** 트리의 선언 다섯이 자기 `order_by`가 한 번도 언급하지 않는
  컬럼으로 페이징하고 있었다 — 두 칸을 한 계약으로 채점하던 탓에 결함 하나가 둘로 보고됐고
  작성자는 같은 답을 두 번 붙여넣고 있었다(소유자: 「커서 어차피 복붙할건데 왜 적으라 그래?」).

🔴 **`registration_probe`의 「선택」은 문법의 말이지 소스의 말이 아니다.** `bind`의 문장
가운데 하나라도 `register@1`을 내면 이 절은 **필수**다 — `runtime_v2._filtered_event_atoms`가
`registration_context_required`로 **런을 통째로 거절**한다(`backfill._probe_subjects`가
probe 없는 소스에 `None`을 돌려주기 때문이고, 빈 집합을 돌려주면 첫 등록이 매 batch 중복
발화한다). `lot_event`가 오래 돌지 못한 이유가 이것이었다. 화면은 이 조건을 소스마다
따져서 묻는다 — `config_authoring._registering_sentences`가 `bind`의 문장에서 `register`를
찾고, 찾으면 `bundle.sources.<id>.read.registration_probe` 칸을 **`missing`으로 세운다.**
`entity_type` 후보는 전체 개체가 아니라 **그 문장들이 실제로 등록하는 것들로 좁혀지고**,
어느 소스·컬럼·이름 패턴에도 키를 걸지 않는다 — 문장이 「등록한다」인지는 그 술어가
`vocabulary.PREDICATES`의 정준 `register`로 풀리느냐로 판정하며, 이는 `runtime_v2`와
`backfill`이 원자를 대조할 때 쓰는 **같은 철자**다.

🔴 **`registration_probe.columns`는 «물리» 컬럼이다 — 준비기가 만든 이름이 아니다.**
`bind`가 쓰는 철자를 기억으로 옮겨 적으면 `'lot_event' has no column 'lot'`으로 거절된다.
`lot_event`의 실제 선언이 그 차이를 보여 준다 — probe는 `lot_id`·`waferids`(물리)를 읽는데
같은 소스의 binding은 `lot`·`wafers`(준비기 출력)를 쓴다. 화면은 그래서 **relation의 물리
카탈로그 컬럼**을 후보로 내놓는다: probe가 진짜로 읽는 우주가 그것이다.

`order_by`는 catalog가 선언한 유일 키를 완전히 포함해야 하고, `cursor.columns`는 그것과
**같은 값**이 되므로 같은 성질을 물려받는다. 위 `lot_event`는 `row_id`가 유일 키라
`order_by: ["event_time", "row_id"]`가 전순서를 만든다. **둘을 다르게 적어 볼 자리는 이제
없다** — 다르게 적어도 번들이 `order_by` 쪽으로 맞춰 쓴다.

Timezone은 “DB session timezone을 쓰겠지”라고 추측하지 않는다. `event_time`이 이미 offset을
갖는지, 현장 local time인지 확인하고 실제 의미를 적는다. 없거나 잘못된 timezone은 validation
단계에서 거절한다.

🔴 **`occurred_at.timezone`은 offset 없는 컬럼을 «읽는다»** (소유자 판정 2026-08-21,
`9aa147b9`). 자기 offset을 적는 값은 그것을 그대로 지키고, **이 선언은 offset이 없는 값에
대해서만 답한다.** 원장에 실리는 셀은 그렇게 해석된 instant이고, **event id를 만드는 것과
같은 값**이다.

그전까지 이 두 반쪽이 어긋나 있었다: id는 이미 해석된 instant에서 나오는데 실리는 셀은
읽은 문자열 그대로였고, Role 검증기가 그것을 `time Role must be a timezone-aware datetime`
으로 **거절**했다. 정체를 정하기엔 믿을 만하고 값을 정하기엔 아닌 가정 하나는 조심이
아니라 **원자를 하나도 못 내는 소스**였다 — `lot_event`가 그 모습이었다.

⚠️ **대가는 이름 불러 적는다:** offset 없는 시각 컬럼을 가진 **모든** 소스가 이제 자기
선언 timezone으로 읽힌다. 그래서 §3의 질문 3(「timezone은 무엇인가」)은 취향이 아니라
**값을 정하는 선언**이다.

---

### 7.9 시각 컬럼이 없는 표

세상에는 **언제인지 말하지 않는 표**가 있다. 어디에 얼마만 한 것이 있는지만 적고 시각은
적지 않는 관측 표가 그렇다. 원장 봉투의 `occurred_at`은 없앨 수 없으므로(`ledger_events`가
시간 분할이고 PK가 `(id, occurred_at)`이다) 종전에는 그런 표를 붙이려면 **거짓을 선언**해야
했다 — 시각이 아닌 컬럼을 시각으로 지목하거나, 프로필에 `1970-01-01` 같은 상수를 박거나.

둘 다 **읽는 쪽에서 구분할 수 없다.** 「그때 생겼다」로 읽히고 여정·대조가 그 값을 세계
시각으로 취급한다. §15의 「가짜 값 생성 금지」와 정면으로 어긋난다.

그래서 시각을 없애는 대신 **시각의 출처를 선언**한다.

```jsonc
"occurred_at": { "column": "event_time", "timezone": "Asia/Seoul" }  // 세계 시각
"occurred_at": { "basis": "ingested",    "timezone": "Asia/Seoul" }  // 적재 시각
```

- `basis: "ingested"`는 그 행의 **적재 시각**(`created_at`)을 읽는다. 모든 적재 표가 갖는
  시스템 컬럼이라 어디서든 성립하고, **저장된 값**이라 백필을 다시 돌려도 같은 원자가 나온다.
  `created_at`을 `column`에 직접 적을 필요는 없다 — 적으면 그건 「이 표의 세계 시각이
  적재 시각이다」라는 **다른 주장**이 된다.
- 허용값은 `"ingested"` 하나다. 닫힌 목록이라 오타는 이름을 대며 거절된다.
- `timezone`은 두 형태 모두 필수다.

**여러 행이 한 사건인 소스에서 그 시각은 `min`이다**(소유자 판정 2026-08-19). 한 사건의
행들이 한 인제션 배치에 다 들어온다는 보장이 없어서 `created_at`이 그룹 안에서 하나가
아닐 수 있고, 그때 사건의 시각은 **가장 이른 적재 시각** — 「우리가 이걸 처음 본 때」다.
늦은 쪽을 고르면 조각이 하나 더 오는 날 **같은 사건의 시각이 움직이고**, 사건 id가 그
시각에서 만들어지므로 다음 백필이 같은 사건을 새 id로 다시 쓴다. `min`에는 그 성질이 없다.

🔴 **`column`은 접지 않는다.** 세계 시각이 한 사건 안에서 둘이면 그것은 **그룹이 틀렸다**는
뜻이라 어떤 집계도 고칠 수 없다 — `one source event must have exactly one occurred_at
instant`로 거절된다. 접는 것은 `basis` 경로뿐이고, 두 갈래를 갈라 두는 것이 이 규칙의 전부다
(가드: `task/evidence/ledger_atom_baseline.py`의 `dtjob_group_*`·`refuse_two_world_times_in_one_group`).

**페이지는 커서의 첫 컬럼으로 자른다**(같은 날 판정, `backfill._page_key`). 위 규칙은 한
배치가 그룹을 통째로 들고 있을 때만 효력이 있는데, 페이지를 `occurred_at` 컬럼으로 자르던
동안에는 그렇지 않았다 — 커서는 `cursor.columns`로 **쓰면서** 읽기는 시각 컬럼으로 했다.
`dt_log` 실측(2026-08-19): 걸치는 job 26개 중 **24개가 배치 경계에 쪼개졌고**, 그것이 원장에
들어갔던 12건의 정체다. `lot_event`는 두 키가 같은 컬럼이라 **동작이 한 글자도 안 바뀐다.**

🔴 **그런데 「페이지 키가 그룹 안에서 상수」임을 컴파일러는 검사할 수 없다.** `lot_event`에서
그것이 참인 이유는 매퍼가 `event_time`을 그룹 키에 **품고 있기** 때문이고, 그건 선언에
안 보인다. 그래서 원인 대신 **증상**을 지키는 가드가 런에 붙어 있다 — 이미 통째로 처리한
그룹이 뒤 페이지에 다시 나오면 **이름을 대며 거절**한다. 어제 코드로 재현하면 배치 #1에서
거절되고, 지금 코드로는 396그룹이 전부 깨끗하다. 그룹 키가 파생 컬럼이라 base 행에서 읽을 수
없는 소스에서는 **가드가 꺼져 있다고 런이 말한다**(조용히 건너뛰지 않는다).

**원자가 스스로 말한다.** 이렇게 선언된 소스의 원자는 `occurred_at_basis` 컬럼에 그 값을
싣는다. 종전 원자는 이 값이 비어 있고, **비어 있음이 곧 「세계 시각」**이다. config를 다시
읽지 않아도 구분되는 것이 요점이다 — 원자는 선언보다 오래 살고, 그때의 선언은 이미 바뀌어
있다.

물리 컬럼 추가는 `server/migrations/add_ledger_occurred_at_basis.py`가 한다(널 허용,
행 재작성 없음, 백필 없음).

**팩·프로필은 안 바뀐다.** `occurred_at` 역할은 여전히 필수이고 `$role` 참조여야 한다.
바뀌는 것은 그 역할에 **무엇이 들어오느냐**뿐이라, 프로필에 시각 리터럴이 등장할 이유가
사라진다.

**매퍼도 안 바뀐다.** `column`이든 `basis`든 매퍼는 시각을 **`__occurred_at` 한 이름으로**
읽는다 — 물리 컬럼 이름은 준비 경계가 이미 풀었고, 그 이름을 매퍼가 되물을 자리는 없다.

🔴 **[2026-08-23 `189193a4`] 그 문장이 «범용 매퍼에 대해서는» 오늘부터 참이 됐다.**
`declarative-role@1`은 모든 binding을 프레임 셀 그대로 읽었으므로, varchar 시각 컬럼을 문자열로
집어 들고 `invalid_time_role`(`time Role must be a timezone-aware datetime`)로 거절했다.
**전용 매퍼 둘이 각자 값을 변환하고 있어서 그 칸을 가리고 있었고**, 전용 매퍼가 없는 소스가
처음 생긴 날 드러났다 — 소유자가 폼만으로 만든 `transfer_event`가 그것이다. 지금은 범용
매퍼도 **Role kind가 `time`이면** binding을 평가하지 않고 `__occurred_at`을 읽는다. 범위는
정확히 그 kind 하나다(claim 컴파일러는 `time`을 `occurred_at`에만 준다). 다시 파싱하지 않는
것이 요점이다 — **`source_event_identity`가 사건 id를 바로 그 값에서 만들기 때문에**, 다른
철자로 읽은 시각은 자기가 속한 사건의 id와 어긋난다.

⚠️ **그래서 `bind.<문장>.occurred_at`의 `column`은 시각 Role에 대해 «아무 일도 하지 않는다».**
`dt_job`이 그 상태다 — `read.occurred_at.basis: ingested`인데 모든 `bind.occurred_at`은
`event_time`을 가리키고, 전용 매퍼도 그것을 무시한다. **자유도 0인 칸이므로 지울 후보이지만
아직 판정 전이다**(열린 항목). 이 칸을 「시각을 바꾸는 손잡이」로 읽지 말 것.

```python
sentences = ProfileSentences(context, profile,
                             occurred_at=unit.iloc[0][SOURCE_OCCURRED_AT_COLUMN])
```

`__source_row_ref`와 같은 부류다 — **엔진이 얹는 컬럼이라 선언하지 않는다.** `input_columns`에
적으면 `column '__occurred_at' is not in EventFrame schema`로 거절된다(EventFrame 스키마는
물리 컬럼 ∪ preparer `output_columns`이고 이 컬럼은 어느 쪽도 아니다).

## 8. 선언이 곧 활성화다 — 실행 스위치는 없다

🔴 **`sources`에 있는 source는 «돈다».** 「돈다」고 다시 말해 주는 두 번째 자리는 없다.

예전에는 `dataflows/chains.json`의 `ledger_v2_execution` selector가 source마다 `mode`,
`parity_status`, `approval_ref`를 들고 있었다. 셋 다 은퇴했다. 그 파일도, 그 문법도 없다.

**왜 느슨해진 것이 아닌가.** selector는 애초에 「선언은 됐지만 돌 준비는 안 됨」을 붙들고
있지 않았다. 절반만 쓴 소스는 스위치가 무슨 말을 하든 **bundle validation과 snapshot compile을
통과하지 못해** 돌 수 없다(⚠️ **그 자리를 붙들던 것이 binding 승인 게이트라고 적혀 있었는데,
그 게이트는 2026-08-22에 필드째 없어졌다** — 붙드는 것은 검증기이지 승인이 아니었다). 그리고 스위치의 다른
쪽 위치(`legacy`)는 이제 **아무것도 연결되지 않은 config**를 가리켰다. 남겨 두면 새 소스를
**두 번** 적어야 하고, 그중 하나는 Explorer가 보여 주지도 않는 파일이었다 — 실제로 그렇게
한 소스를 적는 것을 잊은 적이 있다.

따라서 준비의 표현은 이렇게 한다.

- **아직 돌리면 안 되는 소스** → `sources`에 아직 적지 않는다. 나머지 section(`vocabulary`,
  `entities`)은 먼저 적어도 되고, 전수 검증도 받는다.
- **다 됐는데 잠시 꺼 두고 싶다** → 그런 요구가 실제로 생기면 그 소스 **자기 선언 안**
  (`sources.<id>.enabled`)에 들어갈 자리다. 드리프트하는 별도 파일이 아니다. 🔴 **현재
  그런 필드는 구현돼 있지 않다** — 지금 필요하면 총괄에 가져간다.

`sources` 안에 `sql`, `python`, `exec` 같은 실행 키를 중첩 배열 깊숙이 숨겨도 완전 재귀
검사에서 `unsafe_declaration`으로 거절한다. 이 검사는 파일 전체에 걸린다.

---

## 9. enrichment는 이 셋업에 없다

`dataflows/enrichments.json`은 은퇴했고 대체 section도 없다. 그 파일은 항상 비어 있었고
읽는 코드가 없었다.

결측 Claim 후보, dependency replay, enrich action/worklist가 필요하면 **별도 승인된 계약**을
통해 구현한다. 특히 다음은 하지 않는다.

- `ledger_config.json`에 임의 SQL/Python/expression을 넣어 실행될 것으로 기대
- 미완성 값을 자동 confirmed Claim으로 승격
- cursor 재실행이나 삭제를 부작용으로 숨김

---

## 10. 새 Source를 추가하는 실제 순서

의미 선언은 전부 `server/config/ontology/ledger_config.json` **한 파일 안**에서 일어난다.
🔴 **그 앞에 파일이 하나 더 있다 — Step 2의 `server/config/table_config.json`이다.** 물리
스키마는 그 파일이 정본이고(§5), 표가 거기 선언되기 전에는 원장이 그 표에 대해 아무 말도
할 수 없다. 아래 순서를 바꾸면 뒤 단계의 오류가 앞 단계 결함을 가린다.

🔴 **`sources`(Step 9)를 마지막에 적는다.** 그것이 「켠다」이기 때문이다(§8). 앞의 여덟
단계는 아직 아무것도 돌리지 않는다.

### Step 1. 물리 표와 인제션을 먼저 확정

- 실제 relation 이름과 대소문자를 확인한다.
- 모든 물리 column과 타입을 확인한다.
- source event의 business/composite key를 정한다.
- DB에 그 유일성을 강제하는 constraint/index가 실제로 있는지 확인한다.
- 세계 시각 column과 timezone을 확정한다.
- null, 늦게 도착한 행, re-delivery의 의미를 정한다.

이 단계는 Ledger config 작업이 아니라 Source 소유 작업이다. Ledger config가 relation을
생성하거나 데이터 품질을 고쳐 주지 않는다.

### Step 2. `table_config.json`에 표를 «먼저» 선언한다

🔴 **원장 파일을 열기 전에 하는 일이고, 건너뛸 수 없다.** 표가
`server/config/table_config.json`에 없으면 Step 9에서 `unknown_relation`으로 거절되며,
그때 나오는 문장이 다시 여기로 보낸다(§5.3).

- `column_types`에 모든 물리 컬럼과 타입을 적는다.
- 행의 유일 키를 선언한다 — 여러 컬럼을 합쳐 만든다면 `composite_key_source`,
  한 컬럼이 그대로 신원이면 `business_key`.
- **인제션이 그 표에 쓰지 않더라도 선언한다.** 원장만 읽는 표도 마찬가지다(`void`가 그
  모양이다). 선언해야 드리프트 검사와 그리드가 따라온다.

검토 질문:

- 식별자를 `number`로 잘못 선언하지 않았는가?
- 유일 키의 일부만 적어 두고 전체라고 오인하지 않았는가?
- `map_key_columns`를 유일 키로 착각하지 않았는가? (아니다 — §5.2)
- 선언한 컬럼이 실제 DB에 있는가? — 여기서만큼은 **직접 대조하지 않아도 된다.**
  `schema_drift`가 이 파일을 실물 DB와 대조한다. 그것이 원장이 이 파일을 읽는 이유다.

### Step 3. 필요한 경우 `virtual_joins` section 추가

신원이나 목적지 정보가 다른 inventory relation에 있을 때만 사용한다. join 없이 Preparer가
EventFrame을 완성할 수 있으면 이 선택 section을 아예 쓰지 않는다.

join을 추가할 때:

1. 오른쪽 relation도 `table_config.json`에 선언한다.
2. 오른쪽 key 전체의 catalog UNIQUE 근거를 선언한다.
3. `join_key`, `expose`, `join_cardinality: "one"`을 작성한다.
4. physical verifier가 실제 index를 찾을 수 있는 테스트 환경을 준비한다.

### Step 4. 기존 의미 재사용 여부 확인

새 Vocabulary/Entity를 만들기 전에 현재 registry를 검색한다.

- 같은 개체인데 source column 이름만 다르다 → 기존 Entity 재사용
- 같은 관계인데 source 표현만 다르다 → 기존 Vocabulary 술어 재사용
- 같은 술어인데 source별 컬럼이 다르다 → 새 소스의 `bind.mappings`만 작성
- EventFrame 조립 방식도 같다 → 같은 `implementation_id`를 그 소스의 `prepare`/`map`에 적는다
  (선언을 «공유»하는 것이 아니라 **같은 코드를 부르는 것**이다 — §7.3)
- 그룹 조립이나 도메인 해석이 다르다 → 새 trusted 구현 검토

**의미 층은 물리 테이블 이름을 알아서는 안 된다.** 공통 validator와 registry에 `dt_log`,
`bonding_log`, `CORE_WAFER` 같은 source 문자열 분기를 추가하지 않는다.

### Step 5. Vocabulary와 Entity 작성

먼저 “무슨 문장을 말할지”를 닫는다.

- subject Entity type
- object kind와 Entity type
- required/optional qualifier
- 개체 logical key shape

단순히 source에 컬럼이 있다는 이유로 새 qualifier를 만들지 않는다. R&D 질문에서 보존해야 할
의미인지 먼저 판단한다.

### Step 6. ~~Pack 작성~~ — **이 단계는 없어졌다** (`9b6c5da`)

🔴 **적을 것이 없다.** Step 5에서 술어를 닫는 순간 Role 목록과 emission이 **함께 정해진다**
(§7.5). 예전에는 여기서 Claim마다 Role을 열거하고 `emit`으로 Vocabulary 위치에 연결했는데,
그 둘은 Step 5가 이미 적은 것의 사본이었다.

Step 5에서 적은 것이 곧 다음이 된다.

| §7.1에 적은 것 | 도출되는 것 |
|---|---|
| `object.kind` | `subject`·`occurred_at`(항상) + `target`/`value`(있으면) |
| `object.qualifiers.required[]` | 같은 이름의 필수 Role |
| `object.qualifiers.optional[]` | 같은 이름의 선택 Role |

Mapper는 여전히 Role 값만 반환한다. `object_payload` dict를 Mapper가 조립하는 일은 없고,
어떤 Role이 subject·object·qualifier인지는 **술어가** 정한다.

### Step 7. `prepare`·`map` 절 작성

🔴 **먼저 범용 구현으로 끝나는지 본다.** 다음 둘이면 Python을 한 줄도 쓰지 않는다.

- Preparer `direct-join@1` — 출력 컬럼이 상속한 verified join에서 그대로 오는 경우
- Mapper `declarative-role@1` — 업무적 읽기가 `bind` binding만으로 표현되는 경우

이 둘은 `prepare.implementation_id`/`map.implementation_id`에 이름만 적으면 된다. **절
자체는 언제나 소스가 직접 든다** — 이름 붙은 descriptor를 어딘가에 만들고 참조하는 모양은
없어졌다(§7.3·§7.4).

전용 구현이 정말 필요하면 다음 코드 경계를 따른다.

- Preparer: `BaseSourcePreparer.prepare_batch()` 최종 경계(하위 클래스는
  `prepare_outputs()`를 구현한다)
- Mapper: `BaseLedgerMapper.map()` 최종 경계(하위 클래스는 `interpret_unit()`을 구현한다)
- 위치: mapper는 `server/mappers/ledger_v2_*.py`, preparer는 `server/ledger/`
- 신뢰 등록: **없다.** 클래스가 `implementation_id`/`implementation_version`을 자기 자신에
  선언하면 `server/ledger/implementations.py`가 발견한다. 손으로 유지하는 목록은 없다.

설정에 module path를 넣어 우회하지 않는다. `implementation_id`가 발견되지 않으면
`untrusted_implementation` 또는 unknown implementation 오류가 정상이다.

### Step 8. `bind` 절 작성

1. mapper가 말하는 **문장 이름**마다 `mappings.<문장>` 항목을 만든다. 전용 mapper면 그
   목록의 정본은 mapper 파일의 `SentenceShape` 속성들이고, `declarative-role@1`이면 이름은
   그냥 이 mapping을 부를 이름이다.
2. 각 항목에 `predicate`(정확한 vocabulary id, 예 `has_wafer@1`)를 적는다. **어느 술어를
   쓰는지 따로 모아 적는 자리는 없다** — `predicate`가 그 답이다.
3. 그 술어가 강제하는 required Role을 모두 binding한다. **목록은 §7.5가 도출한다** —
   고를 것은 없고, 빠뜨리면 `missing_required_role`, 없는 이름을 적으면 `unknown_role`이다.
4. Entity logical key를 exact set으로 채운다.
5. **더 적을 것이 없다.** binding은 **종류와 그 payload**만 말한다 — `binding_origin`·
   `approval_status`·`suggestion_reason` 셋은 2026-08-22에 선언에서 없어졌다(§7.6). 옛 파일에
   남아 있어도 검증기가 **받아서 버리므로**(reaches no decision) 마이그레이션을 기다릴 수 있다.

🔴 **「승인」이라는 별도 단계는 이제 없다.** 종전의 `approval_status: "pending"` → `approved`
왕복이 실행 허가를 붙들고 있는 것처럼 보였지만, 라이브 40개 binding이 전부 `approved`였고
그 관문을 **실패시킬 수 있는 파일이 없었다.** 준비의 표현은 §8 하나다 — **아직 돌리면 안 되는
소스는 `sources`에 적지 않는다.**

### Step 9. `relation`·`read` 조립 — 이것이 「켠다」이다

🔴 **`sources`에 항목을 적는 순간 그 소스는 실행 대상이다.** 앞의 여덟 단계를 끝내고 아래
증거를 만든 뒤에 적는다.

- Bundle validation 성공
- immutable snapshot compile 성공
- preview candidate/refusal/incomplete 결과
- failure 시 Atom 0/cursor 미이동
- 필요한 경우 안전한 격리 PostgreSQL E2E

적을 때 확인할 것:

- relation과 row/group 단위를 정한다.
- identity/group_by를 EventFrame schema에 맞춘다.
- order/cursor가 catalog UNIQUE key 전체를 포함하게 한다.
- occurred_at physical column과 timezone을 명시한다.

🔴 **연결할 ID가 없다.** 소스 하나를 만드는 것은 이제 **한 번의 행위**다 — `prepare`·`map`·
`bind`가 같은 항목 안에 있으므로 서로를 이름으로 부르지 않고, 서로를 되가리키는 선언을
따로 만들 필요도 없다. 그것이 profile을 옮긴 이유이기도 하다: 종전에는 새 소스가 저장되려면
**자기를 이름으로 되부르는 새 profile**이 먼저 있어야 했다.

---

## 11. `lot_event` 선언의 end-to-end 연결 읽기

현재 production 선언을 한 줄로 읽으면 다음과 같다.

```text
table_config.json / lot_event
  physical: lot_id/event_time/txn_seq/...
  unique proof: txn_seq business_key

sources.lot_event
  relation  lot_event

  read      group by prepared event_group_key
            order by txn_seq
            cursor (event_time, txn_seq)
            occurred_at event_time in Asia/Seoul

  prepare   lot-event-live-frame v1
            physical lot_id/slotnumbers/waferids/...
            → EventFrame lot/slots/wafers/event_group_key/...

  map       lot-event-role v1, unit event
            EventFrame event
            → 문장 6개의 RoleEmission

  bind      mappings keyed by sentence, each naming its predicate:
              in_slot → has_wafer@1 · descent → derived_from@1
              split_slot_carry · merge_slot_join → slot_map@1
              first_sight_holder · first_sight_item → register@1
            EventFrame lot/wafers/slots/event_time
            → 그 술어가 강제하는 subject/target/slot/occurred_at Role

vocabulary (술어가 Role을 강제한다 — 선언 없음)
  Role
  → register@1 / has_wafer@1 / derived_from@1 / slot_map@1 LedgerFrame
```

`sources.lot_event`가 존재한다는 것이 곧 「이 소스는 돈다」이다. 그 위에 얹힌 selector는
없다.

예를 들어 mapper가 말하는 문장 `in_slot`은 다음 연결로 완성된다.

```text
bind.mappings.in_slot.predicate = has_wafer@1
EventFrame.lot
  → bind subject = Entity Lot@1 {lot}
EventFrame.wafers
  → bind target = Entity Wafer@1 {wafer}
EventFrame.slots
  → bind slot Role
EventFrame.event_time
  → bind occurred_at Role
Vocabulary has_wafer@1
  → object.kind entity_ref  ⇒ Role subject/target/occurred_at
  → object.qualifiers.required ["slot"]  ⇒ Role slot
  → Lot subject, Wafer object, required slot 검증
```

어느 한 층도 다른 층의 일을 대신하지 않는다. Mapper에 `{"slot": ...}` payload를
하드코딩하지 않고, `bind`가 술어의 서명을 재정의하지 않으며, 의미 층이 source column을
읽지 않는다. **mapper는 `in_slot`이라는 자기 낱말만 알고, 그것이 어느 술어가 되는지는
`bind.mappings.in_slot.predicate` 한 칸 옆에 적혀 있다.** 그리고 그 술어가 정해지면
채워야 할 칸도 정해진다 — 중간에서 그 둘을 이어 주던 Claim은 없다.

---

## 12. transfer sample에서 virtual join과 계보 읽기

샘플 위치:

```text
server/config/sample/ontology/transfer_explorer/ledger_config.json
```

물리 흐름은 다음과 같다.

```text
dt_log
  record_id, event_at, dt_job_id, core_wafer, core_x, core_y
       │
       │ dt_job_id = dt_job_id
       ▼
dt_inventory
  dt_lot, dt_slot, offsets, bond_wafer, bond_layer, final_chip
```

Source cursor는 `dt_log`만 읽는다. Preparer가 한 batch의 `dt_job_id`를 모아
`dt_inventory`를 read-only batch join하고 EventFrame에 목적지 identity를 붙인다. 따라서
Profile에는 `declared_lookup`이 필요 없고, 완성된 EventFrame column을 binding하면 된다.

이 예제가 보여 주는 의미 계보는 다음과 같다.

```text
CoreDie@1
  → DTDie@1
    → BondComponent@1
      → FinalChip@1
```

중요한 점:

- CoreDie를 FinalChip에 직접 우회 연결하지 않는다.
- 실제 이동 단계를 나타내는 중간 Entity를 보존한다.
- 좌표/lot/slot은 Entity key 또는 qualifier 계약에 따라 표현한다.
- Position이라는 별도 만능 객체를 만들지 않는다.
- join 0건·다건은 불완전 계보를 꾸며 내지 않고 mapper 전 거절한다.
- dependency가 늦게 도착하면 replay 후보로 남길 수 있지만 cursor reset을 자동 실행하지
  않는다.

샘플의 `ledger_config.json` 하나가 `virtual_joins`·각 Entity·술어·소스의 `bind.mappings`를 함께
보여 주고 그 배포의 물리 스키마는 자기 `table_config.json`이 든다(§5.4). 그러므로 새 transfer source를 설계할 때 복사 가능한 출발점이다. 🔴 이 샘플은
Preparer `direct-join@1`과 Mapper `declarative-role@1`을 쓴다 — **전용 Python이 0줄인 소스가
실제로 어떤 모양인지**가 여기 있다.

---

## 13. 검증, preview, 실행의 차이

### 13.1 JSON/Bundle validation

검증은 다음을 모두 전수 대조한다.

- 최상위 exact shape(필수 section **셋** + `setup_version`, 여분 키 금지)와 config root에 다른
  JSON이 없음
- 모든 catalog relation/column/key/index
- 모든 Vocabulary/Entity, 그리고 모든 source의 `read`·`prepare`·`map`·`bind`
- Vocabulary subject/object/qualifier의 닫힌 서명
- **술어가 도출하는 Role** ↔ `bind` binding kind (§7.5)
- `bind.mappings.<문장>.predicate` ↔ `vocabulary` registry
- `prepare` physical input/output collision와 inherited join
- cursor total order의 catalog UNIQUE 근거
- unsafe executable key의 임의 깊이 재귀 검사
- ⚰️ **[2026-08-23] 「모든 binding readiness metadata」는 검사 목록에서 뺐다** — 그 metadata(`binding_origin`·`approval_status`·`suggestion_reason`)가 2026-08-22에 은퇴했고, readiness 단계는 **규칙이 0개라 언제나 빈 결과**를 낸다(§7.6). 검증기가 오늘 binding에 대해 보는 것은 **kind와 그 payload뿐**이다

malformed JSON도 raw traceback 대신 구조화된 `code/path/message`로 거절된다. **path는
소스에서 출발한다** — 그것이 절이 소스 안으로 들어온 부수 효과다. 대표 예시는 다음과 같다.

```json
{
  "code": "unknown_entity_type",
  "path": "bundle.sources.my_source.bind.mappings.my_sentence.bind.subject.entity_type",
  "message": "unknown entity type 'Missing@1'"
}
```

```json
{
  "code": "invalid_cursor",
  "path": "bundle.sources.my_source.read.order_by",
  "message": "ordering must include every column of a catalog-declared business_key, composite_key, or UNIQUE index"
}
```

🔴 **거절은 「무엇이 허용되는지」까지 말한다** (2026-08-19). 세 가지가 메시지에 붙는다.

- `unknown_field`는 그 자리에 **허용되는 키 목록**을 뒤에 붙인다(필수 표시 포함).
- `unknown_*`(predicate·entity type·relation …)은 철자가 가까우면 **`did you mean '...'?`**,
  가깝지 않으면 **선언된 것들의 목록**, 아무것도 선언돼 있지 않으면 **「아직 없다」**를 붙인다.
  이 셋은 다음에 할 일이 서로 다르고, 종전 메시지는 그것을 한 문장으로 뭉개고 있었다.
- 참조 목록의 `invalid_type`은 **항목의 철자 형식**(`<이름>@<version>`)을 이름으로 댄다.

그 밖에 자주 보는 code:

| code | 뜻 | 먼저 볼 곳 |
|---|---|---|
| `unlisted_config_file` | config root에 `ledger_config.json` 말고 다른 `.json`이 있음(재귀) | root 밖으로 옮긴다 |
| `unsupported_setup_version` | `setup_version`이 `5`가 아님 | 파일 최상위 — 옛 세대면 §2.4의 마이그레이션 |
| `unknown_relation` | `sources.<id>.relation`이 `table_config.json`에 없음 | 🔴 **다른 컬럼 오류보다 먼저 본다**(§5.3) |
| `unknown_source` | join이 없는 source를 참조 | source ID 철자 |
| `unknown_predicate` | `bind.mappings.<문장>.predicate`가 `vocabulary`에 없음 | 술어 ID와 version (§7.1) |
| `missing_required_role` | 술어가 강제하는 Role의 binding 누락 | `bind.mappings.<문장>.bind` (§7.5) |
| `unknown_role` | 그 술어가 강제하지 «않는» Role을 binding | Role 철자 — 이름은 §7.5의 표에서 도출된다 |
| `invalid_profile` | `mappings`나 `bind`가 비었거나 mapping이 `predicate`+`bind` 둘이 아님 | 그 mapping |
| `invalid_binding` | kind/column/constant/entity shape 오류 | 해당 binding leaf |
| `duplicate_id` | JSON 키 중복, 목록 값 중복, catalog index ID 중복 | 그 path |
| `missing_required_payload` | Vocabulary required qualifier 누락 | 그 qualifier의 binding |
| `unknown_payload_field` | Vocabulary에 없는 qualifier | `vocabulary.<술어>.object.qualifiers` |
| `unsafe_declaration` | SQL/Python/eval/exec 등 금지 키 | 정확한 nested path |
| `untrusted_implementation` | `prepare`/`map`의 `implementation_id`가 코드 trusted catalog 밖 | 클래스가 자기 id를 선언하는지 |
| `unsupported_implementation_version` | id는 있는데 `implementation_version`이 코드와 다름 | 클래스의 `implementation_version` |
| `destructive_approval_required` | reset/from replay 시도 | 별도 사용자 승인 필요 |

### 13.2 write-free dry-run

`server` 디렉터리에서 실행한다.

```powershell
conda run -n assy_manager python -m ledger.setup                 # 운영 config root
conda run -n assy_manager python -m ledger.setup --root <초안폴더>  # 초안 검증
```

운영 config root를 로드하고 결정적인 JSON 한 줄을 낸다 — `config_root`, `setup_version`,
`snapshot_sha256`, `readiness`, 선언된 `sources`(각 `source_id`/`relation`), 그리고
`destructive_actions`가 전부 false임. 정상 dry-run은 DB write, cursor advance, reset,
migration을 수행하지 않는다.

🔴 **`--root`는 「고치기 전에 확인하라」를 실제로 지킬 수 있게 하는 인자다** (2026-08-18
신설). 이전에는 이 명령이 운영 root에 고정돼 있어서, 초안을 확인하는 **유일한** 방법이
운영 파일을 먼저 덮어쓰는 것이었다 — 이 문서가 금지하는 바로 그 순서다. `--root <폴더>`는
같은 읽기 전용 검증을 아무 config root에나 겨눈다. 생략하면 종전과 똑같이 운영 root를 본다.

- `--root`는 **`ledger_config.json`을 «담은 폴더»**를 가리킨다. 파일 자체를 가리키면
  그렇게 말해 주고 멈춘다(종료코드 2). 없는 경로·config 없는 폴더도 각각 한 줄로 거절한다.
- 답의 `config_root`가 **어느 파일을 검증했는지**를 말한다. 초안을 확인했는지 운영을
  확인했는지는 이 값으로 가른다 — `readiness: "ready"`만 보고 넘어가지 말 것.
- 초안 검증은 운영 `ledger_config.json`을 **바이트 하나 건드리지 않는다**(테스트로 고정).

🔴 **이 명령은 문제를 «전부» 보고한다** (2026-08-19 신설). 거절이 있으면 stderr에
`code<TAB>path<TAB>message` 한 줄씩과 마지막에 `N problem(s) in <root>`를 내고 종료코드 1로
끝난다. 순서는 **세 단계**다 — ① 파일 문법(Bundle) ② binding readiness ③ snapshot compile.
뒤 단계는 앞 단계가 통과해야 판정할 수 있으므로 섞지 않는다. 한 단계 «안에서는» 전부 나온다.

- 🔴 **런타임 경로는 바뀌지 않았고 여전히 첫 거절에서 멈춘다.** 원자를 쓰기 직전인 소스에게
  결함 목록은 쓸모가 없다. 「전부 보고」는 **작성 경로**의 성질이고, 그것이 이 명령이
  「고치기 전에 확인하라」를 실제로 지킬 수 있게 하는 두 번째 이유다.
- 종료코드: `0` 통과 · `1` config 문제 · `2` `--root` 인자 자체가 틀림.
- 🔴 **`--root`는 «의미» root만 바꾼다 — 물리 카탈로그는 언제나 라이브 `table_config.json`이다.**
  그래서 **다른 공장의 root를 이 명령에 겨누면 컬럼 거절이 쏟아진다.** 2026-08-19 실측:
  `--root ./config/sample/ontology/transfer_explorer`는 문제 22건을 낸다 — 그 배포의 물리
  스키마는 `server/tests/support/transfer_explorer_table_config.json`이고 이 박스의
  `table_config.json`이 아니기 때문이다(§5.4). **이것은 그 샘플의 결함이 아니다.**
  초안 검증에 이 명령을 쓸 때는 초안이 **이 배포의** 물리 스키마를 겨누고 있어야 한다.

🔴 **`mode`도 `parity_status`도 이 출력에 없다.** 그런 필드는 은퇴했다(§8). 「이 소스가
도는가」의 답은 `sources` 목록에 있느냐다.

주의: `virtual_joins`를 가진 source는 physical verifier가 발급한 descriptor가 필요하다.
선언 JSON만 맞는다고 physical proof를 생략해 ready라고 주장하지 않는다.

### 13.3 Explorer draft preview

서버를 기동한 뒤 다음 화면에서 active 선언을 읽고 working draft를 만든다.

```text
http://127.0.0.1:8080/admin.html#ontology
```

Admin 인증은 두 상태다.

- `ASSY_ADMIN_TOKEN`이 설정돼 있으면 모든 Admin 요청에 정확한 `X-Admin-Token`이 필요하다.
  header가 없으면 `401`, 값이 설정된 token과 다르면 `403`이다.
- token이 설정되지 않으면 ordinary read route(예: active `/view`)는 열릴 수 있지만,
  draft/write 같은 strict route는 `503`으로 fail-closed한다.

draft 저장은 runtime activation이 아니다. draft preview도 같은 compiler를 사용하며 검토·승인,
CAS activation 전까지 active snapshot을 바꾸지 않는다.

#### 13.3-bis 화면 밖에서도 부르는 작성 도구 둘 (2026-08-19)

라우터 `/admin/ontology-explorer` 아래에 **읽기 전용** 엔드포인트 둘이 있다.
`/deletion-preview`는 2026-08-21에 화면 배선이 붙었고(확정 전 casualty 목록),
**`/columns`는 아직 부르는 화면이 없다** — 지금 쓰려면 HTTP로 직접 부른다.

| 엔드포인트 | 무엇을 답하나 |
|---|---|
| `GET /deletion-preview?targets=<key>&…` | 이 선언들을 지우면 **무엇이 함께 가는지**를, 남는 것을 걸어서 이름으로 나열한다. 지우지 않고 초안도 만들지 않는다 |
| `GET /columns?relation=<표>[&combination=<컬럼>…]` | 그 표의 후보 컬럼 각각에 **실제로 값이 든 행 수**를, `combination`을 주면 그 정렬의 **실측 유일성**을 함께 답한다 |

🔴 **`/columns`의 값어치는 목록이 아니라 «숫자»다.** 2026-08-18에 실측된 두 결함은 둘 다
컴파일 검사를 **통과했다** — 개체를 `dt_job_id`로 키잉했는데 그 컬럼은 `dt_log`에서
34,939행 중 **0행**만 값을 갖고(값은 `dt_job`에 있다), `order_by: [dt_job, dt_index]`는
중복이 8,580행이라 정렬 계약이 **백필 도중에** 깨진다. 앞의 것은 거절이 **아예 나오지
않고**, 뒤의 것은 몇 시간 뒤에야 난다. 숫자를 후보 옆에 보여 주면 둘 다 고르는 순간
사라진다 — 이것은 오타 방지 기능이 **아니다**. (위 두 수의 출처는
`server/ledger/column_stats.py` 모듈 docstring의 2026-08-18 실측이고, 다시 재는 방법은 같은
표를 `/columns`로 부르는 것이다. 이 문서는 그 수를 스스로 주장하지 않는다.)

⚠️ **`/columns`는 비싼 읽기다.** population은 추정이 아니라 정확한 수고 표 스캔 한 번이
든다. 응답의 `estimated_rows`는 무엇에 대해 물었는지 되돌려 주는 값이다. 표가
`table_config.json`에 선언돼 있지 않으면 조용히 후보를 내놓지 않고 `undeclared_relation`으로
이름을 대며 거절한다.

🔴 **거절과 삭제는 다른 자리다.** in-degree(참조 개수)는 삭제를 **막는** 기준이 아니다 —
같이 죽을 것들만 가리키는 참조는 막을 이유가 없기 때문이다. `deletion_plan`이 「남는 것」을
걸어 판정하고, `require_no_referrers`는 그것이 없을 때의 fallback이다. 참조를 다른 곳으로
**옮겨 주는 일은 이 화면이 하지 않는다**(남의 선언을 대신 고쳐 쓰는 일이다).

### 13.3-ter 시험 실행 — 진짜를 «한 배치» 돌린다 (`fd3dda05`, 2026-08-21)

작성 화면의 소스 선언에는 **「시험 실행」 버튼**이 있고, 그것이 부르는 것은
`POST /admin/ontology-explorer/test-run`(`{"source_id": "<id>"}`)이다.

| 하는 것 | 하지 않는 것 |
|---|---|
| 첫 페이지(`PREVIEW_FETCH_ROWS`=200행)를 **실제로 읽는다** | 원자를 **하나도 쓰지 않는다** |
| snapshot이 이미 지목한 trusted 구현을 **실제로 실행한다** | `ledger_cursor`를 **움직이지 않는다** |
| 읽은 행 수 · molecule · incomplete · **문장별 원자 수**를 답한다 | 게이트 한 걸음 앞에서 멈춘다 |
| 거절이 나면 **그대로** 돌려준다 | 거절을 자기 낱말로 다시 쓰지 않는다 |

🔴 **이것이 「두 번째 판정자」의 대안이다.** 런타임은 85가지로 거절할 수 있고 작성 화면은
57가지인데 **둘은 코드 이름을 하나도 공유하지 않는다.** 그래서 선언이 폼을 통과하고
백필에서 죽는 일이 생겼다 — `lot_event`가 하루에 **다섯 번** 그렇게 했고 매번 화면은
초록이었다. 런타임 거절을 폼 검증으로 «옮겨 적는» 것은 판정자를 하나 더 짓는 일이라
(`main.py`가 이미 금지한다) **진짜를 한 번 돌리는** 쪽을 골랐다.

- 거절의 path가 폼의 칸을 가리키면 **그 칸으로 가는 버튼**이 되고, 가리키지 않으면
  **원문 그대로 찍는다** — 지어낸 칸보다 자리 없는 문장이 낫다.
- POST인 이유는 바꾸는 것이 있어서가 아니라 **페이지 읽기 한 번 + 컴파일 한 번**이 드는
  비싼 읽기이기 때문이다. 인증은 `/columns`와 같은 일반 admin token이다.
- **0행을 읽은 것도 결과다** — 통과는 아니다(`status: "empty"`). 컴파일된 적 없는 선언이
  도는 것을 보인 적은 없기 때문이다.
- 선언이 **아예 안 읽힌** 경우(compiled snapshot 밖)에는 「그런 소스 없음」이 아니라
  **읽히지 못한 사유**를 답한다.

### 13.3-quater 작성 화면이 «채우는» 것 — 저장이 문서를 늘린다 (2026-08-22~23)

🔴 **소유자가 폼만으로 소스 하나를 처음부터 만들어 원자를 얻은 것이 셋업 완주의 수락
사건이다**(`transfer_event`, 2026-08-23). 그 라운드가 바꾼 것은 문법이 아니라 **작성 경험**이고,
그래서 **손으로 쓴 파일과 화면이 쓴 파일이 다르게 생길 수 있다.** 아래가 화면이 채우는 전부다.

**① 저장이 「파생」 행을 문서에 쓴다** (`config_authoring.filled_declaration`, `3c6a854d`).
계획이 `derived`라 부르고, 모양(shape) 행이 아니며, 값이 있는 행은 **저장 시점에 문서로
내려간다.** 종전에는 「id를 고르면 버전이 따라온다」가 **빈 칸 옆의 문장**으로만 있었고 칸은
빨간 채였다. 특수 케이스 셋이 아니라 계획의 어휘를 한 번 훑는 한 패스라, 나중에 추가되는
파생도 아무도 이 코드를 안 고치고 파일에 도착한다.
- 🔴 **빈 자리만 채우고 «절대» 덮어쓰지 않는다** — 바로 옆 커서 파생(§7.7)과 갈리는 유일한
  지점이다. 덮어쓰면 사람이 바꿔 달라 한 적 없는 값 위에서 **지문이 움직여 돌던 커서가 선다.**
- ⚠️ **id를 안 고른 소스에서는 버전도 안 생긴다** — 파생할 것이 없는 것이지 지어내지 않는다.

**② 후보는 «칸을 완성»해야 후보다** (`88c0c76d`). `occurred_at` 후보를 누르면 컬럼만 들어가고
timezone이 빈 채로 남아, 화면은 빨강 0인데 소스는 컴파일을 거절했다. 지금 후보는 **객체를
통째로** 낸다. timezone 값은 이 모듈이 아니라 **파일에서** 온다 — 그 소스의 선언 → 없으면 같은
파일의 다른 소스가 쓰는 값 → 없으면 이름 붙은 폴백. 강제하지도 목록을 내지도 않으므로
서울 밖 공장은 **첫 소스에서 한 번 타이핑하면** 이후 소스가 그 답을 제안받는다(코드 0줄).
timezone은 **자기 행을 유지한다** — 채워지는 것과 바꿀 수 있는 것은 다르다.

**③ `input_columns` 둘은 「전부 켜짐 + 잠긴 칩」으로 도착한다**
(`a13eeed4`+`e21e990f`+`4a42f393`). 소유자 판정: 「그러면 그냥 디폴트 전체 입력해도 되지?」
- **기본값** = 그 칸의 후보 전부에서 **읽기가 어차피 데려오는 컬럼을 뺀 나머지**.
  준비기의 후보 우주는 `relation`의 **물리** 컬럼이고, 매퍼의 후보 우주는 준비된 컬럼이다.
- **잠긴 칩** = `identity`·`group_by`·`order_by`·`cursor.columns`·`occurred_at`이 이미 SELECT에
  넣는 컬럼(`source_preparation.locked_select_columns` — **런타임 자신의 식**을 선언에서 먹여
  계산한다. 컴파일 안 된 소스도 답을 받는다). 눌린 채로 그려지고 **버튼이 아니다** —
  `data-action`이 없어 마우스·키보드·합성 클릭 어느 쪽으로도 닿지 않는다. `disabled` 속성을
  안 쓴 것이 판정이다(회색이지만 선택처럼 보이는 컨트롤을 소유자가 기각했다).
- 🔴 **화면은 잠긴 컬럼을 문서에 «넣지도 빼지도» 않는다.** `input_columns`는 여전히
  「읽기 위에 더하는 것」이라 이미 오는 이름을 적으면 파일이 이미 한 말을 다시 해서 **지문만
  움직인다.** 반대로 지우는 쪽도 안 한다 — 검증기가 binding이 부르는 컬럼을 `map.input_columns`가
  전부 이름 대기를 요구하고, 라이브 선언 둘이 오늘 실제로 잠긴 컬럼을 적고 있다.
- 🔴 **이 두 키에서는 `[]`가 «미응답»이다**(소유자 판정: 「그냥 다 갈아버린다」). `[]`는 문법상
  합법인 선언이지만 **읽는 쪽이 그것을 부재로 보고 기본값을 씌운다.** 대가를 알고 고른 것이다 —
  `dt_job.prepare.input_columns`가 빈 목록이었으므로 22컬럼이 되고 그 소스의 지문이 움직인다.
  ⚠️ **이 규칙은 그 두 키에만 있다** — 한 층 위에 두면 `read.group_by`까지 잡는데 거기서는
  `unit: row`일 때 `[]`가 **정답**이다. 그래서 판정이 클래스 분기가 아니라 생산자 자리에 있다.
- ⚠️ **대가는 이름 대어 적는다**: 저장된 목록이 이 소스가 읽지도 않는 컬럼을 이름 대므로,
  그중 하나를 표에서 지우면 이 소스도 선다. 완화책이 바로 그 컨트롤이다 — **사람이 칩을 끈다.**

**④ 기본값이 「이미 답한 칸」과 싸우지 않는다** (`0a44069c`). `default_overridable` 행이 선언을
들고 있으면 그 행은 **답한 것**으로 선다(기본값은 주석에 남고 논쟁을 그만둔다). 종전에는
소유자의 `order_by`가 **자기 1,323개 원자가 실제로 나온 정렬을 선언했다는 이유로** 빨갛게
칠해졌다 — 카탈로그 기본값과 다르고 둘 다 합법인데. 같은 라운드에서 함께: 검증기가 **비었다고
거절하는** 값은 결정으로 치지 않고(그 자리는 기본값이 이긴다), **입력이 아직 안 채워진 파생**은
할 일로 세지 않으며(고를 id가 없으면 파생할 것이 없다), **지운 mapping이 진짜로 사라진다**
(계획이 강제하는 멤버는 계속 합집합에 남고, 사람이 이름 붙인 멤버는 이제 문서를 따른다).

**⑤ 「어떤 키가 있는지 보여 주는 행」은 문서에 쓸 값이 아니다** (`08991990`). entity 참조 행은
키 **이름**의 정렬 목록을 화면에 보여 주는 모양 행인데, 저장 채움이 그것을 값으로 파일에 썼다.
문법은 거기서 「키 → binding」 맵을 원하므로 `invalid_entity_ref`가 났고, 더 나쁘게는
`setAtPath`가 문자열을 배열로 파고들지 못해 **키별 피커가 그려진 채 눌러도 아무것도 안 쓰는**
상태가 됐다. 수리는 그 행에 **모양 표지**를 다는 것 하나다 — 옆의 bind 행이 이미 같은 이유로
그 표지를 달고 있다.

⚠️ **알려진 구멍 — 「+ New」 직후 첫 저장 전에는 계획 행이 0개다.** 초안의 본문은 config 파일에
없고 계획 엔드포인트는 그 파일만 읽으므로, **만들어지는 중인 소스는 잠긴 칩도 전체선택도 못
본다** — 스켈레톤의 `+ 컬럼` 버튼만 보인다. 위 ①~⑤는 전부 **첫 저장 이후**의 이야기다.

### 13.4 실제 execute — 쓰기 경계

다음은 기존 LedgerStore와 cursor transaction을 실제로 사용한다.

```powershell
conda run -n assy_manager python -m ledger.backfill --source lot_event --max-batches 1
```

이 명령은 **운영 DB 쓰기 권한을 뜻하지 않는다**. 대상 DB, source, 승인 상태를 확인하고 별도
사용자 승인을 받은 경우에만 실행한다. 한 source event의 문장은 전부 통과하거나 전부
거절되며, 실패 시 Atom 0·cursor 미이동이어야 한다.

공개 CLI의 `--reset-cursor`와 `--from` replay는 `destructive_approval_required`로 선행
차단된다. 이 가이드만 보고 우회하거나 lower-level helper를 직접 호출하지 않는다.

CLI가 받는 나머지 플래그는 `--source`, `--fetch-rows`, `--max-batches`, 그리고 config root를
가리키는 `--ontology-root`(기본값 `server/config/ontology`)뿐이다. **실행 경로는 하나이고
`--legacy`나 `--config` 같은 갈래는 없다.**

---

## 14. 테스트 전략

새 Source가 건드린 직접 범위만 우선 실행한다. 긴 full server suite와 PostgreSQL E2E는
사용자 지시에 따라 생략할 수 있지만, 실행하지 않은 테스트를 통과했다고 기록하지 않는다.

🔴 **파일명 목록을 여기 박아 두지 않는다.** 이 문서가 들고 있던 목록은 테스트가 개명되는
날 조용히 낡고, 없는 파일을 지목한 명령은 「돌렸다」는 근거로 재사용된다. 아래 첫 명령은
**패턴**이라 실행 시점에 실재하는 파일로 풀린다.

⚠️ **경로가 `server/tests/`이므로 이 절의 명령은 «저장소 루트»에서 실행한다** — §13의
dry-run/backfill 명령이 `server/`에서 도는 것과 다르다.

```powershell
conda run -n assy_manager python -m pytest server/tests/test_ledger_setup_*.py -q --basetemp .test_tmp/ledger_setup
```

범용 구현으로 Python 0줄 소스를 붙였다면 다음 둘이 그 경로의 직접 범위다.

```powershell
conda run -n assy_manager python -m pytest server/tests/test_ledger_zero_python_source.py server/tests/test_ledger_implementations.py -q --basetemp .test_tmp/ledger_zero_python
```

변경 범위가 더 넓으면 **먼저 수집만 해서** 무엇이 걸리는지 본다. 수집 오류가 섞여 나오면
그 자체가 정보다 — 없는 것을 돌린 셈 치지 말고 원인을 본다.

```powershell
conda run -n assy_manager python -m pytest server/tests/ -q --collect-only -k ledger
```

존재하지 않는 명령을 복사해 통과 근거로 쓰지 않는다.

PostgreSQL E2E는 `ASSY_PG_TEST_DATABASE_URL`이 안전한 격리 DB를 가리키고 safety guard를
통과할 때만 실행한다. URL이 없으면 skip 수와 이유를 그대로 보고한다.

최소 수락 항목:

- 같은 config의 canonical serialization/snapshot hash 결정성
- source/column 이름이 달라도 같은 술어 재사용
- ⚰️ **[2026-08-23] 「pending/rejected/nested pending 실행 차단」은 수락 항목에서 뺐다** — `approval_status` 은퇴(2026-08-22)로 **일으킬 수 없는 상태**라 이 항목을 통과시킬 수도 실패시킬 수도 없다(§7.6)
- virtual join 0건/다건/incomplete/collision fail-closed
- batch join N+1 방지
- preview/execute 후보 parity
- source event all-or-nothing
- failure에서 Atom 0/cursor 미이동
- config root에 다른 JSON을 두면 `unlisted_config_file`로 거절
- 운영 config/DB migration/reset 0

---

## 15. 흔한 실패와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `invalid_mapper` (`column ... is missing`) | physical/EventFrame 층 혼동 | 🔴 **`bind`가 binding할 수 있는 컬럼 집합은 정확히 `map.input_columns`다.** `table_config.json`에만 있고 mapper input에 없는 컬럼은 binding할 수 없고, `prepare.output_columns`에 있어도 mapper input에 없으면 거절된다 |
| `invalid_cursor` | order/cursor가 UNIQUE key 전체를 안 포함 | business/composite/UNIQUE index 전체 컬럼 추가 |
| join은 선언됐는데 compile 실패 | left key가 `prepare.input_columns`에 없거나 physical proof 없음 | input_columns와 실제 UNIQUE index 확인 |
| `untrusted_implementation` | sample ID를 production에 복사 | 코드에 그 클래스가 있는지 확인 또는 기존 구현 재사용 |
| `missing_required_role` | 술어가 강제하는 Role과 `bind` 불일치 | §7.5의 도출 표를 기준으로 binding 추가 |
| `unknown_predicate` | `mappings.<문장>.predicate`가 `vocabulary` 밖 | 술어 ID와 version 철자 |
| `unknown_payload_field` | binding한 qualifier가 Vocabulary 밖 | Vocabulary를 무작정 넓히지 말고 의미 확인 후 술어 서명 수정 |
| draft validation은 되는데 execute 불가 | ⚰️ **[2026-08-23] 「pending/rejected binding 존재」는 원인이 «될 수 없다»** — `approval_status`는 2026-08-22에 은퇴했고 binding 승인 관문 자체가 없다(§7.6). 이 칸을 보고 승인 상태를 찾으러 가면 **없는 필드를 찾는다** | 그 소스가 `sources`에 적혀 있는지부터 본다(§8) — 준비 안 된 소스를 붙드는 자리는 그것 하나다. 실행 거절문은 코드·경로와 함께 오므로 **거절문의 `code`를 이 표에서 찾아라**(`undeclared_source`·`invalid_cursor`·`invalid_mapper` 등) |
| mapper가 문장을 못 찾는다 | `bind.mappings`의 **키**가 mapper의 문장 별명과 다름 | mapper 파일의 `SentenceShape` 속성명이 정본이다(§7.6) |
| join 결과 0건 | inventory 늦은 도착/키 불일치 | 원천·표기·dependency replay 후보 확인; 가짜 값 생성 금지 |
| join 결과 다건 | 오른쪽 유일성 위반 | 물리 중복 해소와 exact UNIQUE proof; 첫 행 임의 선택 금지 |
| 화면이 비어 있음 | Admin auth 상태 오해 | token 설정 시 header 누락 `401`·값 불일치 `403`, token 미설정 strict route `503`을 구분 |
| `unlisted_config_file` | config root 안에 다른 `.json`이 있음(백업 폴더 포함 — 검사는 재귀한다) | root **밖**으로 옮긴다. 옛 다섯 파일은 §2.3 |
| `unsupported_setup_version` | 파일에 `setup_version: 5`가 없거나 옛 세대(`4` 이하·`schema_version`)를 씀 | §2.4의 마이그레이션 → §4의 최상위 모양 |
| `unknown_field` (`packs`/`source_preparers`/`mappers`/`profiles`) | 넷이 최상위 section이던 세대의 파일 | §2.4의 마이그레이션 |
| `unknown_field` (`bind.mappings.<문장>.use`) | `use`가 `predicate`가 되기 전 세대 | §2.4의 v5 마이그레이션 |
| 안 켠 소스가 돌았다 | `sources`에 적는 것이 곧 켜는 것 | §8. 준비 전이면 `sources`에서 뺀다 |
| `--legacy`/`--config`가 없다 | 실행 경로가 하나가 됨 | `--ontology-root`로 config root를 지정한다(§13.4) |
| reset/from이 거절됨 | 파괴적 replay 선행 gate | 우회하지 말고 별도 사용자 승인과 작업 범위 확정 |

---

## 16. 작성 완료 체크리스트

### 물리/카탈로그 (`table_config.json` — §5)

- [ ] 표가 `server/config/table_config.json`에 선언돼 있다. **원장 파일에 `tables`를 적지
      않았다**(적으면 `unknown_field`).
- [ ] relation과 physical columns가 실제 DB와 일치한다. — 이 대조는 `schema_drift`가 한다.
- [ ] 식별자와 수치 타입을 구분했다.
- [ ] order/cursor가 catalog-declared UNIQUE key 전체를 포함한다.
- [ ] join 오른쪽 key는 catalog와 실제 DB 모두에서 UNIQUE다.
- [ ] virtual join left key가 Preparer input에 포함된다.

### 의미

- [ ] 기존 Vocabulary/Entity를 먼저 재사용 검토했다.
- [ ] Vocabulary subject/object/qualifier가 닫혀 있다.
- [ ] Entity logical key가 source 물리 이름과 분리돼 있다.
- [ ] 각 문장의 `predicate`가 `vocabulary`에 있고, **그 술어가 강제하는 Role을 전부**
      binding했다(§7.5 — 목록은 고르는 것이 아니라 도출된다).

### 실행

- [ ] config에 module/path/SQL/Python/expression을 넣지 않았다.
- [ ] `prepare`의 input/output과 `map.input_columns`가 exact하게 맞는다.
- [ ] `implementation_id`/version을 가진 클래스가 코드에 실제 있다(범용 `direct-join@1`·
      `declarative-role@1`으로 끝나는지 먼저 확인했다).
- [ ] `bind.mappings`의 **키가 mapper의 문장 별명**이다. 전용 mapper면 그 목록의 정본은
      mapper 파일의 `SentenceShape` 속성들이다(§7.6).
- [ ] 다섯 절(`relation`·`read`·`prepare`·`map`·`bind`)을 **한 소스 항목 안에** 적었다 —
      최상위 `source_preparers`/`mappers`/`profiles`는 없다(§4).
- [ ] 이 소스를 **지금 돌려도 되는 상태**에서만 `sources`에 적었다.

### 승인/검증

- [ ] binding에 `approval_status`·`binding_origin`·`suggestion_reason`을 **적지 않았다**
      (2026-08-22 은퇴 — 남아 있어도 검증기가 받아서 버린다. §7.6).
- [ ] vocabulary 항목에 `layer`를 **적지 않았다**(2026-08-22 은퇴 — 지금은 `unknown_field`. §7.1).
- [ ] `read.cursor`를 손으로 적지 않았다 — `order_by`에서 파생돼 문서에 쓰인다(§7.7).
- [ ] `python -m ledger.setup` dry-run이 `readiness: "ready"`이고 write 0이다. **초안이면
      `--root <초안폴더>`로 먼저 돌리고, 답의 `config_root`가 그 초안을 가리키는지 본다**(§13.2).
- [ ] config root에 `ledger_config.json` 말고 다른 `.json`이 없다.
- [ ] preview/execute parity와 all-or-nothing을 검증했다.
- [ ] 미실행 full/PG 테스트를 통과로 표현하지 않았다.
- [ ] reset/replay/migration을 수행하지 않았다.

---

## 17. 정본과 참고 문서

| 목적 | 문서/코드 |
|---|---|
| 현재 시스템 상태와 인수인계 | [FORK_SESSION_BRIEF](../process/FORK_SESSION_BRIEF.md) |
| 최상위 section 목록과 필수/선택 구분 | `server/ledger/setup_bundle.py`의 `LOGICAL_SECTIONS`·`OPTIONAL_SECTIONS`·`SETUP_VERSION` |
| Bundle exact validation | `server/ledger/setup_bundle.py` |
| Registry/Snapshot compile | `server/ledger/setup_registry.py` |
| RoleFrame compile · 범용 mapper · 문장 이름(`SentenceShape`/`ProfileSentences`) | `server/ledger/roleframe.py` |
| **술어 → Role/emission 도출(옛 `packs`)** | `server/ledger/setup_bundle.py`의 `predicate_claim` |
| **시험 실행(한 배치, 무쓰기)** | `server/ledger/config_explorer_service.py`의 `test_run` + `backfill.preview_first_batch` |
| **작성 폼과 계획의 불일치 감사(읽기 전용)** | `server/scripts/audit_authoring_form.py` |
| 컬럼 실측(작성 화면) | `server/ledger/column_stats.py` |
| 삭제가 데려가는 것 | `server/ledger/config_explorer.py`(`deletion_plan`·`referrers`) |
| Source preparation · 범용 preparer | `server/ledger/source_preparation.py` |
| 어떤 `implementation_id`가 실행 가능한가 | `server/ledger/implementations.py` |
| preview/execute | `server/ledger/runtime_v2.py` |
| 로드 경계와 dry-run 보고 | `server/ledger/setup.py` |
| 옛 다섯 파일 → 한 파일 변환 | `server/scripts/convert_ontology_to_single_file.py` |
| 옛 세대 → `setup_version: 4` 마이그레이션(§2.4) | `server/scripts/migrate_ledger_config_to_v4.py` |
| v4 → `setup_version: 5` 마이그레이션(§2.4) | `server/scripts/migrate_ledger_config_to_v5.py` |
| 현재 production 선언 | `server/config/ontology/ledger_config.json` |
| transfer file-backed sample | `server/config/sample/ontology/transfer_explorer/ledger_config.json` |
| Explorer 전체 계약 | `ontology_config_explorer_plan/02_IMPLEMENTATION_AND_ACCEPTANCE.md` |

정확한 필드가 이 문서와 validator에서 충돌하면 코드와 승인된 V2 acceptance evidence를 먼저
대조한다. 문서를 조용히 추측으로 고치지 말고, 실제 contract 변경이면 validator·테스트·정본
문서를 한 커밋에서 함께 갱신한다.
