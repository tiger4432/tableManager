# 글에서 «원인 -> 현상» 후보 뽑기

> **대상:** `@mapper` 를 쓰는 운영자 | **최종 검증:** 2026-10-01 (코드 대조 — `server/utils/text_links.py` · 시험 `server/tests/test_a_sentence_names_its_cause_and_phenomenon.py`) | **관련:** [MAPPING_GUIDE](../../authoring/MAPPING_GUIDE.md) · [config/chain_rules.md](./config/chain_rules.md)

회의록 · 8D 같은 글에서 «무엇이 무엇의 원인이라고 적혔나»를 후보 행으로 뽑는다. 낱말은 전부 당신이 적은 사전 행에서 온다 — 코드에는 어느 언어의 낱말도 없다.

## 1. 표 넷

| 표 | 칸 | 적는 사람 |
|---|---|---|
| 글 | `<글 id>` · `<글>` — 회의록 한 건이든 8D 한 섹션이든. 나누는 것은 맵퍼 | 사람 · 수집기 |
| 부르는 말 | `node_type` · `node_key` · `phrase` — 한 노드에 말 여럿 | 사람 |
| 연결 말 | `phrase` · `meaning` · `side` | 사람 |
| 후보 | `<글 id>` · `sentence_no` · `sentence` · `cause_type` · `cause_key` · `cause_phrase` · `phenomenon_type` · `phenomenon_key` · `phenomenon_phrase` · `link` · `polarity` · `certainty` · `extractor` · `evidence` | 맵퍼 |

| `meaning` | 뜻 | `side` |
|---|---|---|
| `cause` | 원인을 잇는 말 (「로 인해」 · 「원인」 · 「무관」) | `before` = 원인이 말 앞 · `after` = 말 뒤 |
| `and` | 나열 (「,」 · 「와」 · 「과」) | 비움 |
| `negation` | 부정 — 문장의 후보가 `negated` | 비움 |
| `suspected` · `confirmed` | 추정 · 확인 — 문장에 둘 다 있으면 `suspected` | 비움 |

같은 말을 두 행에 적으면 두 뜻이다 — 「무관」 = `cause`(`before`) 한 행 + `negation` 한 행.
`*_phrase` · `link` 는 글에 «적힌 그대로»다. 후보 표의 키는 `<글 id>` · `sentence_no` · `cause_type` · `cause_key` · `phenomenon_type` · `phenomenon_key` 로 잡는다(LLM 으로 뽑으면 §6 의 키).
`extractor` 는 뽑은 쪽 — `rules` 또는 `llm:<모델>`. `evidence` 는 근거 문장. 후보 표에 이 두 칸이 없으면 쓰기가 그 두 칸만 버리고 경고를 센다.

## 2. 짝짓는 규칙 — 두 줄

1. 원인 말마다, 그 행의 `side` 쪽에서 «가장 가까운» 노드가 원인이다 — 그 노드와 `and` 말(과 공백)로만 이어진 노드도 원인
2. 같은 문장의 나머지 노드가 현상이다 — 원인 × 현상마다 후보 하나

맞추기: 띄어쓰기와 영문 대소문자는 무시한다(「계면 미충진」=「계면미충진」). 두 사전의 말이 겹치면 «긴 말»이 이긴다(「확인 필요」가 「확인」을 이김). 영문 글자 · 숫자로 시작하거나 끝나는 말은 낱말 경계에서만 맞는다(`void` 는 `avoid` 안에서 안 맞음). 문장은 줄바꿈과 `.` `!` `?` `。` 뒤 공백에서 나뉜다.

## 3. 맵퍼와 규칙

```python
import pandas as pd
from mapper_sdk import find_links, mapper, sql

@mapper()
def text_cause_links(df, db):
    names = sql(db, "SELECT <타입 칸> AS node_type, <키 칸> AS node_key, <말 칸> AS phrase "
                    "FROM <부르는 말 표>").to_dict("records")
    links = sql(db, "SELECT <말 칸> AS phrase, <뜻 칸> AS meaning, <쪽 칸> AS side "
                    "FROM <연결 말 표>").to_dict("records")
    rows = [{"<글 id 칸>": text_id, **row}
            for text_id, text in zip(df["<글 id 칸>"], df["<글 칸>"])
            for row in find_links(text, names, links)]
    return pd.DataFrame(rows)
```

```json
{
  "name": "<규칙 이름>",
  "trigger_table": "<글 표>",
  "target_table": "<후보 표>",
  "mapper": "text_cause_links",
  "is_batch": true,
  "allow_retraction": true,
  "trigger_job_column": "<글 id 칸>",
  "target_job_column": "<글 id 칸>"
}
```

- `allow_retraction` 의 출처 = 글 id. 글을 고치면 그 글이 «이번에 안 낸» 옛 후보 행이 지워진다. 다른 글의 후보는 안 건드린다. 사람이 손댄 후보 행도 안 지운다.
- SQL 의 NULL 은 `NaN` 으로 오지만 이 함수가 «빈 말»로 접는다 — 빈 말 행은 아무것도 안 맞는다.
- 두 함수 다 맵퍼가 제품 도우미를 부르는 문(`mapper_sdk`, [MAPPING_GUIDE §5-bis](../../authoring/MAPPING_GUIDE.md))으로 온다.
- `unknown_words(texts, names, links)` 는 사전이 «못 덮은» 낱말과 횟수를 많은 순으로 준다 — 사전을 키우는 자리. 조사 잔여(「는」 · 「의」)도 그대로 센다. 거르는 것은 맵퍼 몫이다.

## 4. 사전을 고친 뒤

사전 표를 고쳐도 규칙은 안 깨어난다 — 규칙은 «글 표»에 깨어난다. 다시 돌린다:

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <규칙 이름>            # 미리 보기
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <규칙 이름> --apply
```

## 5. 남는 것 둘

- **글 행을 지우면 그 글의 후보가 남는다.** 지움은 규칙을 안 깨운다. 그리드에서 후보 표를 그 글 id 로 걸러 지운다.
- **한 글의 후보가 20 행 이상이고 이번에 절반 넘게 사라지면 지우기를 거절한다** — 키를 잘못 적은 것과 모양이 같아서다. 로그 `[DtMapRetraction] … DECLINED` 줄이 그 글 id 와 다음 할 일을 적는다.

## 6. LLM 으로 뽑기

1. 맵퍼가 `find_links` 대신 `ask_links(글, 부르는 말 행)` 을 부르고, 규칙에 `"run_in": "operation"` 을 적는다
2. LLM 은 환경변수 넷으로 고른다 — `ASSY_LLM_BASE_URL` · `ASSY_LLM_MODEL` · `ASSY_LLM_API_KEY` · `ASSY_LLM_TIMEOUT_S`(초, 기본 60). 코드에는 어느 쪽도 없다

```python
import pandas as pd
from mapper_sdk import ask_links, mapper, sql

@mapper()
def text_cause_links_llm(df, db):
    names = sql(db, "SELECT <타입 칸> AS node_type, <키 칸> AS node_key, <말 칸> AS phrase "
                    "FROM <부르는 말 표>").to_dict("records")
    rows = [{"<글 id 칸>": text_id, **row}
            for text_id, text in zip(df["<글 id 칸>"], df["<글 칸>"])
            for row in ask_links(text, names)]
    return pd.DataFrame(rows)
```

```json
{
  "name": "<규칙 이름>",
  "trigger_table": "<글 표>",
  "target_table": "<후보 표>",
  "mapper": "text_cause_links_llm",
  "is_batch": true,
  "allow_retraction": true,
  "trigger_job_column": "<글 id 칸>",
  "target_job_column": "<글 id 칸>",
  "run_in": "operation",
  "rows_per_run": 1
}
```

- `run_in: operation` — 글을 넣은 묶음은 LLM 을 안 부르고 작업(`rule_rows`)으로 줄 세운 뒤 다음 묶음으로 간다. LLM 이 다른 표의 체인을 안 막는다([chain_rules](./config/chain_rules.md)).
- `rows_per_run: 1` — 작업 하나 = 글 하나. 틀린 답은 그 글의 작업만 실패시키고, 다른 글은 다른 작업이라 계속 돈다.
- 노드 키는 «부르는 말» 사전의 말에서만 온다. 사전에 없는 말이 원인·현상이면 `*_type` · `*_key` 가 비고 `*_phrase` 만 찬다.
- 체인은 키 칸이 빈 행을 버린다. 그래서 이 후보 표의 키는 `<글 id>` · `sentence_no` · `cause_phrase` · `phenomenon_phrase` 로 잡는다 — 구절은 늘 찬다.
- `certainty` 는 글이 «확인»이라 하면 `confirmed`, 그 밖에는 `suspected` — 사람이 확정하기 전에 사실로 올리지 않는다.
- 운영자 지시는 셋째 인자 — `ask_links(text, names, instruction="<지시>")`. 프롬프트에 들어가는 낱말은 사전 행 · 지시 · 글뿐이다.
- 틀린 답(JSON 아님 · `links` 없음 · 원인/현상/근거 빔 · 근거 문장이 글에 없음)은 `LlmRefused` 로 이름 대어 거절된다. 그 글의 작업이 실패하고, 작업의 error 에 체인 격리와 같은 기록(`error_log` 모양)이 남는다. 관리 화면에서 다시 돌린다.
- LLM 을 한 번 더 부르는 다른 쓰임새는 `ask_json(프롬프트)` — 답한 JSON 객체를 준다.

## 7. 원장으로 — 확정한 후보만 `leads_to`

1. 후보 표에 사람이 채우는 확정 칸을 두고, 원장 소스의 `read.exclude_when` 에 그 칸을 적는다 — 빈 행은 원장이 안 읽는다
2. 원인 · 현상의 타입은 `entity_type: {"kind": "column", "column": "<타입 칸>"}` 으로 행에서 읽고, `keys` 에는 그 자리가 받는 타입들의 키를 다 적는다

```json
"leads_to": {
  "subjects": ["<원인 타입>"],
  "object": { "kind": "entity_ref", "types": ["<현상 타입>", "<다른 현상 타입>"],
              "qualifiers": { "required": [], "optional": ["certainty"] } }
}
```

```json
"<후보 소스>": {
  "relation": "<후보 표>",
  "read": { "unit": "row", "identity": ["<후보 id 칸>"], "order_by": ["<후보 id 칸>"],
            "occurred_at": { "basis": "ingested", "timezone": "Asia/Seoul" },
            "exclude_when": [{ "column": "<확정 칸>", "blank": true }] },
  "map": { "implementation_id": "declarative-role", "implementation_version": 1, "unit": { "kind": "row" } },
  "bind": { "mappings": { "leads": { "predicate": "leads_to", "bind": {
    "subject": { "kind": "entity", "entity_type": { "kind": "column", "column": "cause_type" },
                 "keys": { "<원인 타입의 키>": { "kind": "column", "column": "cause_key" } } },
    "target": { "kind": "entity", "entity_type": { "kind": "column", "column": "phenomenon_type" },
                "keys": { "<현상 타입의 키>": { "kind": "column", "column": "phenomenon_key" },
                          "<다른 현상 타입의 키>": { "kind": "column", "column": "phenomenon_key" } } },
    "certainty": { "kind": "column", "column": "certainty" } } } } }
}
```

- 타입 칸의 값은 선언된 타입 이름 그대로다(옛 철자 `x@1` 도 접힌다). 행마다 그 타입의 키만 쓴다.
- 그 자리가 받지 않는 타입의 행은 그 행만 `type_not_admitted` 로 거절되고 다른 행은 들어간다 — 받는 타입은 술어 목록(`subjects` · `object.types`)이 정한다.
- 타입 칸이 비거나 그 타입의 키 칸이 빈 행은 `no_identity`.
- 적재에서 거절: 받는 타입의 키를 안 적음 · 어느 타입에도 없는 키 · 칸 타입에 속성 · 받는 타입에 소스 속성(`bind.entities`) · 코드 맵퍼 · `register` 문장인데 `read.registration_probe` 없음.
- 선언 화면은 이 모양(이름 또는 칸)을 아직 읽기 전용으로만 보인다.
