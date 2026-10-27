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

## 동작

```
호출 수     그룹 수 (한 그룹은 늘 통째로 한 글. 자르지 않습니다)
묶음        llm_config.json 의 batch_chars 까지 그룹 여럿을 한 요청에. 넘는 그룹은 혼자 한 요청
거절        그 그룹만. 체인 거절 줄에 «["P1"] (4699 chars): <사유>» — 어느 그룹이 몇 글자였나
다시 돌 때   사람이 고친 칸은 그대로(user 층). 답에 없어진 행은 그 규칙의 칸만 거둡니다(사람 행은 남음)
로그        chain_worker.log «[ChainRule] <규칙>: asked N group(s) in M call(s) - R row(s), K refused»
```
