# AI 가 표를 채우는 규칙 — `derive: {kind: "ask"}`

> **Status:** 🟢 Living | **Last-verified:** 2026-10-28 (A-1 구조 인식)

한 그룹(예: 제품)의 행을 통째로 AI 에 묻고, 답을 다른 표의 행으로 쓰는 체인 규칙입니다.
모델링 구조 인식 · 스텝 맵핑 · 아이템 글 해석이 모두 이 «선언 하나»의 다른 값입니다.
코드에는 표 · 칸 · 낱말 이름이 없습니다. 아래 칸이 전부입니다.

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
| `common` | `cell` 의 값은 공용 표 칸 값 중 하나, 아니면 `none` 낱말 |
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

리포트 선언(`derive.report`)도 같은 `memory` · `prompts.memory` 칸을 읽습니다. 상황은 리포트의 웨이퍼 키 값입니다. 리포트 표의 사람 교정을 메모리로 «쓰는» 쪽은 아직 없습니다.

```
쓰는 것     memory 를 적으면 같은 선언에서 반쪽 규칙 하나가 섭니다(출력 표가 트리거, 메모리 표가 타깃)
           출력 표의 칸을 사람이 AI 값과 «다르게» 고치면 메모리 행 하나. 같은 자리면 덮어씁니다
           사람 값이 AI 값과 같으면 교정이 아닙니다
되돌리면    사람이 AI 값으로 되돌리거나 사람 층이 거둬지면 그 상황의 메모리 행은 지워집니다(gone)
남는 것     AI 가 나중에 사람 값과 같은 답을 내게 돼도 교정 줄은 남습니다 — 지우려면 메모리 행을 지웁니다
```

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
