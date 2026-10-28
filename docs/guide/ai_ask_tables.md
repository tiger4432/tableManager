# AI 가 표를 채우는 규칙 — `derive: {kind: "ask"}`

> **Status:** 🟢 Living | **Last-verified:** 2026-10-28 (A-1 구조 인식)

한 그룹(예: 제품)의 행을 통째로 AI 에 묻고, 답을 다른 표의 행으로 쓰는 체인 규칙입니다.
모델링 구조 인식 · 스텝 맵핑 · 아이템 글 해석이 모두 이 «선언 하나»의 다른 값입니다.
코드에는 표 · 칸 · 낱말 이름이 없습니다. 아래 칸이 전부입니다.

운영에서는 `server/config/sample/chain_rules.json.sample` 의 견본 규칙(`ai_structure_of_product` · `ai_step_mapping` · `ai_split_item_quantity` · `split_fill` · `wafer_report_rows` · `wafer_report`, 모두 `enabled: false`)을 켜고 표 이름을 자기 표로 고치면 됩니다. 견본 표는 `table_config.json.sample` 에 같은 이름으로 있습니다(스텝 표 `step_master` 의 `step_seq` · `step_desc`, 아이템 표 `item_master` 의 `item_id` 등).
리포트 · fn walk 규칙은 꺼져 있어도 표와 세계를 읽어 판정하므로, 표 이름을 고치기 전에는 «규칙이 안 섬» — 체인 로드 줄 «<규칙>: enabled=false — no rule stands for it.» 와 그 위의 거절 문장이 고칠 표 · 세계를 이름 댑니다.

## 선언

```json
{"name": "structure_of_product",
 "on":   {"table": "<스텝 표>"},
 "into": {"table": "<구조 표>"},
 "derive": {"kind": "ask", "ask": {
   "input":   {"group_by": ["<제품 칸>"], "order_by": "<순서 칸>", "text": ["<설명 칸>"]},
   "output":  {"carry": {"<출력 칸>": "<입력 칸>"}, "cells": ["<답 칸>", "..."]},
   "common":  {"cell": "<답 칸>", "table": "<공용 표>", "column": "<칸>", "none": "<목록 밖일 때 낱말>"},
   "prompts": {"common": "<모든 그룹에 붙는 설명>",
               "memo": {"table": "<메모 표>", "key": "<그룹 칸>", "text": "<메모 칸>"}}}}}
```

| 칸 | 뜻 |
|---|---|
| `input.group_by` | 이 값이 같은 행이 한 글 — 행 하나가 바뀌어도 그 그룹 «전체»를 `order_by` 순으로 읽습니다 |
| `input.text` | 한 줄에 실을 칸 (`order_by` 값이 줄 머리) |
| `output.carry` | 그룹 값을 출력 행에 옮겨 적을 칸 |
| `output.cells` | AI 가 채우는 칸 — 답 행의 키 |
| `common` | `cell` 의 값은 공용 표 칸 값 중 하나, 아니면 `none` 낱말. `about` 을 적으면 같은 표의 그 칸이 값 옆에 실립니다 |
| `prompts.memo` | 그 그룹에 붙는 사람 메모(표의 행) |

### 스텝 맵핑에 더하는 칸 (A-2)

| 칸 | 뜻 |
|---|---|
| `input.window` · `input.overlap` | 그룹을 `window` 줄씩 잘라 묻고, 앞뒤 `overlap` 줄은 «맥락 줄»로만 싣습니다(답하지 않음) |
| `output.line` · `output.item` | 답 행이 «어느 줄 · 어느 아이템»인지 적을 출력 칸 |
| `items` | `{table, step: {column}, item}` — 아이템 표 step 값을 줄의 `order_by` 값과 «그대로» 견주어 그 줄 아래에 아이템을 싣습니다. 접두가 제품이라 제품까지 같이 맞습니다 |
| `reuse.key` | `[{column, drop_leading}, ...]` — 이 값이 같은 기존 답이 있으면 묻지 않고 그 답을 씁니다(다른 그룹 포함). `drop_leading` 은 앞 접두(제품)를 떼어 «같은 자리의 공정»으로 견줄 때. 이 줄의 아이템 중 기존 답에 없는 것이 있으면 그 줄은 묻습니다 |
| `reuse.within` | `{cell, table, column, carry}` — 재사용할 답의 `cell` 값이 이 그룹의 목록에 없으면 재사용하지 않고 묻습니다 |

### 사람 교정을 기억하는 칸 (A-3)

| 칸 | 뜻 |
|---|---|
| `memory.table` | 교정을 적을 표. 키는 보통 `purpose` · `key` · `cell` 칸 셋 |
| `memory.columns` | 역할마다 그 표의 칸 이름: `purpose`(규칙 이름) · `key`(상황 — 출력 행의 키 칸 값 json) · `cell` · `ai`(AI 가 낸 값) · `right`(사람이 고친 값) · `memo`(사람이 적는 메모, 규칙은 안 씀) · `who` · `when` |
| `prompts.memory` | `{scope, limit}` — 상황의 `scope` 칸 값이 같은 교정만, 최근 `limit` 개(기본 5)를 프롬프트에 «Past corrections» 줄로 싣습니다 |

리포트 선언(`derive.report`)도 같은 `memory` · `prompts.memory` 칸을 읽고 씁니다. 사람이 리포트 표의 글 칸(`results` 가 이름 댄 text 칸)을 고치면 그 교정이 메모리 행이 됩니다. 상황은 리포트 표의 키 칸 값이라, `scope` 칸이 리포트 표의 키에 있어야 다음 리포트에 실립니다.

```
쓰는 것     memory 를 적으면 같은 선언에서 반쪽 규칙 하나가 섭니다(출력 표가 트리거, 메모리 표가 타깃)
           출력 표의 칸을 사람이 AI 값과 «다르게» 고치면 메모리 행 하나. 같은 자리면 덮어씁니다
           사람 값이 AI 값과 같으면 교정이 아닙니다
되돌리면    사람이 AI 값으로 되돌리거나 사람 층이 거둬지면 그 상황의 메모리 행은 지워집니다(gone)
남는 것     AI 가 나중에 사람 값과 같은 답을 내게 돼도 교정 줄은 남습니다 — 지우려면 메모리 행을 지웁니다
```

### split 아이템 글 -> quantity (split 템플릿 2 단계)

펼친 split 표의 아이템 글(자연어)마다 «어느 quantity 인가»를 한 번 묻습니다. 같은 선언, 다른 값:

```json
{"name": "split_item_quantity", "on": {"table": "<펼친 split 표>"}, "into": {"table": "<아이템 글 맵핑 표>"},
 "derive": {"kind": "ask", "ask": {
   "input":  {"group_by": ["<아이템 글 칸>"], "order_by": "<split 종류 칸>", "text": ["<split 종류 칸>", "<레이어 칸>"]},
   "output": {"carry": {"<아이템 글 칸>": "<아이템 글 칸>"}, "cells": ["<quantity 칸>"]},
   "common": {"cell": "<quantity 칸>", "table": "<quantity 목록 표>", "column": "<quantity 키 칸>",
              "about": "<설명 칸>", "none": "not found"},
   "prompts": {"common": "<약어 풀이 · 레이어 이름>"}}}}
```
```
호출      서로 다른 아이템 글 수(행 수 아님). 로그 «asked N text(s)» 의 N
선택지    common.about 을 적으면 «값 (설명)» 으로 실립니다. 답은 값만. 목록 밖의 답은 none 낱말
크기      선택지 하나에 약 36 자(박스: 설명 «quantity number N» 꼴) — 50 개 2,155 자, 500 개 18,305 자. 요청마다 한 번
```

## AI 표를 원장에 — ai_model 세계 (A-4)

운영에서는 `server/config/sample/ai_model_world.ledger_config.json.sample` 을 `config/ontology_worlds/ai_model/ledger_config.json` 으로 복사하고, 소스 둘의 `relation` 을 구조 표 · 맵핑 표 이름으로 고치면 됩니다.

| 문장 | 읽는 칸 |
|---|---|
| 구조 `part_of` 부모 구조 | 구조 표의 제품 · 구조 · 부모 |
| 구조 `is_a` physical_object | 구조 표의 종류 칸 |
| 스텝 `acts_on` 구조 | 맵핑 표의 제품 · 스텝 · 작용 구조 |
| 스텝 `is_a` physical_process | 맵핑 표의 공정 종류 칸 |
| 계측 항목 `describes` 구조 | 맵핑 표의 아이템 · 작용 구조 |

```
imports    process_step · quantity · physical_object/process/quantity 는 기본 세계 것을 가리킵니다 — 키가 한 곳, 노드가 하나
           product_structure 와 술어 넷(part_of · acts_on · describes · is_a)은 이 세계 것입니다
공용 없음   is_a 문장의 "when": {"<종류 칸>": {"not": "<common.none 낱말>"}} — 그 문장만 안 하고, 같은 행의 다른 문장은 섭니다
           화면(출력 표)에는 «공용 없음» 낱말이 그대로 남습니다
of_kind    기본 세계의 결함 → 결함 종류만입니다. 모델링의 «무엇의 한 종류»는 is_a 입니다
```
계측값은 기본 세계가 읽습니다(견본 `ledger_config.json.sample` 의 소스 `metro` · `process_event`): 웨이퍼 `measures` quantity(값 · 스텝) · quantity `measured_at` 스텝 — 실측 행에서, 웨이퍼 `processed_at` 스텝(수식어 `tx_id`). 맵핑 표의 아이템 행은 `describes` 만 냅니다.
스텝 노드의 키는 (제품, step_seq) 입니다. 운영 표에 제품 칸이 없고 step 값이 제품 접두를 품으면, 원장 bind 는 무계산이라 접두를 뗄 수 없습니다 — 표에 제품 칸을 두거나 체인이 채웁니다.
리포트의 모델 걷기는 `causes.worlds` 에 두 세계(`["default", "ai_model"]`)를 적고 `causes.values.follow` 에 `is_a` 를 적습니다(docs/guide/ai_report_tables.md).

## 동작

```
호출 수     물을 글 수. window 없으면 그룹마다 하나(자르지 않음), 있으면 «바뀐 줄이 든 창»마다 하나
           재사용으로 다 채워진 창은 묻지 않습니다
묶음        llm_config.json 의 batch_chars 까지 글 여럿을 한 요청에. 넘는 글은 혼자 한 요청
거절        그 글만. 체인 거절 줄에 «["P1"] (4699 chars): <사유>» — 어느 그룹이 몇 글자였나
다시 돌 때   사람이 고친 칸은 그대로(user 층). 답에 없어진 행은 그 규칙의 칸만 거둡니다(사람 행은 남음)
           창 하나만 물었으면 그 창의 줄 범위만 거둡니다
로그        chain_worker.log «[ChainRule] <규칙>: asked N text(s) in M call(s), W window(s) reused whole - R row(s), K refused»
```
