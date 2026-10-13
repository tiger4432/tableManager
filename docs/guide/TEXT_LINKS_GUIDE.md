# 글에서 «원인 -> 현상» 후보 뽑기

> **대상:** `@mapper` 를 쓰는 운영자 | **최종 검증:** 2026-10-13 (코드 대조 — `server/utils/text_links.py` · `llm.py` · `phrase_bag.py` · `dictionary_suggest.py` · `server/scripts/causal_graph_connectivity.py` · 시험 `server/tests/test_a_sentence_names_its_cause_and_phenomenon.py` · `test_a_phrase_with_modifiers_finds_its_node_by_its_bag.py` · `test_many_texts_are_asked_in_one_request_under_a_per_minute_limit.py` · `test_a_batch_prompt_carries_the_links_already_known_among_its_nodes.py` · `test_the_causal_graph_connectivity_command_counts_pieces_and_lone_pairs.py`) | **관련:** [MAPPING_GUIDE](../../authoring/MAPPING_GUIDE.md) · [config/chain_rules.md](./config/chain_rules.md)

회의록 · 8D 같은 글에서 «무엇이 무엇의 원인이라고 적혔나»를 후보 행으로 뽑는다. 낱말은 전부 당신이 적은 사전 행에서 온다 — 코드에는 어느 언어의 낱말도 없다.

## 1. 표 넷

| 표 | 칸 | 적는 사람 |
|---|---|---|
| 글 | `<글 id>` · `<글>` — 회의록 한 건이든 8D 한 섹션이든. 나누는 것은 맵퍼 | 사람 · 수집기 |
| 부르는 말 | `node_type` · `node_key` · `phrase` — 한 노드에 말 여럿 | 사람 |
| 연결 말 | `phrase` · `meaning` · `side` | 사람 |
| 후보 | `<글 id>` · `sentence_no` · `sentence` · `cause_type` · `cause_key` · `cause_phrase` · `cause_direction` · `phenomenon_type` · `phenomenon_key` · `phenomenon_phrase` · `phenomenon_direction` · `dir` · `link` · `polarity` · `certainty` · `extractor` · `evidence` | 맵퍼 |

| `meaning` | 뜻 | `side` |
|---|---|---|
| `cause` | 원인을 잇는 말 (「로 인해」 · 「원인」 · 「무관」) | `before` = 원인이 말 앞 · `after` = 말 뒤 |
| `and` | 나열 (「,」 · 「와」 · 「과」) | 비움 |
| `negation` | 부정 — 문장의 후보가 `negated` | 비움 |
| `suspected` · `confirmed` | 추정 · 확인 — 문장에 둘 다 있으면 `suspected` | 비움 |

샘플: `server/config/sample/table_config.json.sample` 의 `text_doc`(글) · `text_name`(부르는 말) · `text_link_word`(연결 말) · `text_cause_candidate`(후보) — 표 설정에 옮겨 이름만 바꿔 쓴다.

같은 말을 두 행에 적으면 두 뜻이다 — 「무관」 = `cause`(`before`) 한 행 + `negation` 한 행.
규칙으로 뽑은 행의 `*_phrase` · `link` 는 글에 «적힌 그대로»다(LLM 행은 §6). 후보 표의 키는 `<글 id>` · `sentence_no` · `cause_type` · `cause_key` · `phenomenon_type` · `phenomenon_key` 로 잡는다(LLM 으로 뽑으면 §6 의 키).
`*_direction` 은 LLM 이 채운다(§6) — 규칙이 뽑은 행은 비어 있다. `dir` 은 그 둘의 부호 — 둘 다 차고 같으면(up/up · down/down) `+`, 다르면(up/down · down/up) `-`, 한쪽이라도 비면 빈다. 후보 표에 이 세 칸이 없으면 쓰기가 없는 칸만 버리고 경고를 센다.
`extractor` 는 뽑은 쪽 — `rules` 또는 `llm:<모델>`. `evidence` 는 근거 — 규칙이 뽑은 행은 그 문장, LLM 행은 모델이 쓴 인용 그대로(두 문장에 걸칠 수 있고 따옴표 · 말줄임이 글과 다를 수 있음 — 그때 문장 칸은 인용이 시작한 문장부터 끝난 문장까지, 문장 번호는 시작한 문장). 후보 표에 이 두 칸이 없으면 쓰기가 그 두 칸만 버리고 경고를 센다.

## 2. 짝짓는 규칙 — 두 줄

1. 원인 말마다, 그 행의 `side` 쪽에서 «가장 가까운» 노드가 원인이다 — 그 노드와 `and` 말(과 공백)로만 이어진 노드도 원인
2. 같은 문장의 나머지 노드가 현상이다 — 원인 × 현상마다 후보 하나

맞추기: 띄어쓰기와 영문 대소문자는 무시한다(「계면 미충진」=「계면미충진」). 두 사전의 말이 겹치면 «긴 말»이 이긴다(「확인 필요」가 「확인」을 이김). 영문 글자 · 숫자로 시작하거나 끝나는 말은 낱말 경계에서만 맞는다(`void` 는 `avoid` 안에서 안 맞음). 문장은 `.` `!` `?` `。` 뒤 공백(줄바꿈 포함)과 빈 줄에서 나뉜다 — 줄바꿈 하나는 문장을 나누지 않는다(PPT · 엑셀에서 붙인 글은 한 문장이 여러 줄). 문장 칸은 글 그대로라 그 줄바꿈을 품는다. `1.5` 는 안 나뉜다.

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

사전 표를 고쳐도 규칙은 안 깨어난다 — 규칙은 «글 표»에 깨어난다. LLM 후보의 빈 키만 채우려면 §8-2(LLM 을 안 부른다). 글을 다시 읽히려면 다시 돌린다:

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <규칙 이름>            # 미리 보기
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <규칙 이름> --apply
```

## 5. 남는 것 둘

- **글 행을 지우면 그 글의 후보가 남는다.** 지움은 규칙을 안 깨운다. 그리드에서 후보 표를 그 글 id 로 걸러 지운다.
- **한 글의 후보가 20 행 이상이고 이번에 절반 넘게 사라지면 지우기를 거절한다** — 키를 잘못 적은 것과 모양이 같아서다. 로그 `[DtMapRetraction] … DECLINED` 줄이 그 글 id 와 다음 할 일을 적는다.

## 6. LLM 으로 뽑기

1. 맵퍼가 `find_links` 대신 `ask_links(글들, 부르는 말 행)` 을 부른다 — 체인이 넘긴 묶음의 글을 «한 번에» 넘긴다. 규칙에 `"rows_per_run": 20` 처럼 묶음 크기를 적는다
2. LLM 은 선언 파일 하나로 고른다 — `server/config/llm_config.json`(모양: `server/config/sample/llm_config.json.sample`): `base_url` · `model` · `api_key` · `timeout_s`(초, 기본 60) · `headers`(덧붙일 요청 머리) · `proxy`(없거나 null 이면 시스템 프록시를 안 읽고 바로 간다) · `requests_per_minute`(기본 20) · `batch_chars`(기본 4000) · `known_chars`(기본 4000) · `known_per_seed`(기본 5) — 뒤의 둘은 §6-2. 부를 때마다 읽으므로 고친 값은 다음 부름부터 쓰인다. 코드에는 어느 값도 없다. ⚰️ 환경변수 `ASSY_LLM_*` 는 은퇴했다 — 파일 없이 환경변수만 있으면 옮기라는 거절 문장이 난다
3. 부를 때마다 `server/llm_requests.log` 에 JSON 두 줄 — 보낸 것(시각 · id · URL · 모델 · 머리 · 페이로드 · 프록시)과 받은 것(같은 id · 상태 · ms · 답 또는 오류). 키는 `***` 로 가린다
4. `devenv bootstrap` 이 이 파일도 복사한다 — 격리 스택도 같은 모델을 부른다

```python
import pandas as pd
from mapper_sdk import UNREAD_JOBS, ask_links, mapper, sql

@mapper()
def text_cause_links_llm(df, db):
    names = sql(db, "SELECT <타입 칸> AS node_type, <키 칸> AS node_key, <말 칸> AS phrase "
                    "FROM <부르는 말 표>").to_dict("records")
    texts = [{"id": text_id, "text": text} for text_id, text in zip(df["<글 id 칸>"], df["<글 칸>"])]
    found = ask_links(texts, names)
    out = pd.DataFrame(found).rename(columns={"text_id": "<글 id 칸>"})
    out.attrs[UNREAD_JOBS] = [item["id"] for item in found.refused]     # 못 읽은 글 - 옛 후보를 지우지 않는다
    return out
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
  "rows_per_run": 20
}
```

- 글 여럿은 `[{"id": <글 id>, "text": <글>}, …]` — id 는 묶음 안에서 겹치면 안 된다(겹치면 묻기 전에 `ValueError`). 결과 행마다 맨 앞에 `text_id`(넘긴 id 그대로). 글 하나(문자열)로 불러도 된다 — 그때 결과는 전과 같다(`text_id` 없음).
- 요청 하나 = 사전 한 번 + 지시 한 번 + 글들(글마다 `[<글 id>]` 줄 뒤에, 빈 줄로 띄워). 글 길이 합이 `batch_chars` 를 넘으면 다음 요청으로 — 묶음 하나 = 요청 «글자 합 / batch_chars» 번(올림, 한 글이 상한보다 길면 그 글 혼자). 모델은 글 id 마다 링크를 답하고, 근거 · 방향 · 키는 «그 글 안에서만» 읽는다 — 다른 글의 문장을 근거로 댄 링크는 그 글에서 버려진다(아래 근거 줄).
- 답에 빠진 글 · 모양이 틀린 글(링크 목록 없음 · 원인/현상/근거 빔 · 모든 링크의 근거가 그 글에 없음 · 답 전체가 JSON 아님)은 «그 글만 혼자» 한 번 더 묻는다 — 로그 한 줄 `[LLM] a request of N texts left K unread - each asked alone: <id>: <사유>; …`. 혼자 물은 요청에서도 안 되면 그 글만 거절 — 후보 0 행, 경고 한 줄 `[LLM] text <id> refused - no rows (llm:<모델>): <사유>`, 결과의 `refused` 에 `{id, reason}`. 처음부터 혼자였던 글(묶음에 글 하나, 또는 상한보다 긴 글)은 다시 묻지 않는다. 모든 글이 거절되면 `LlmRefused` 로 묶음이 실패한다(`max_group_attempts` 만큼 다시 시도한 뒤 FAILED — 전과 같다).
- 호출 «자체»가 실패하면(연결 · 시한 · 5xx · 세 번 넘은 429 — 답이 아예 안 옴) 글마다 다시 묻지 않고 곧바로 `LlmCallFailed`(`LlmRefused` 의 하위)로 묶음이 실패한다 — 게이트웨이가 죽어도 요청은 한 번이고, 체인이 그 묶음을 나중에 다시 한다. 글마다 다시 묻는 것은 모양이 틀린 답 · 빠진 글뿐이다.
- 거절된 글은 «이번에 낸 것이 없음»이 아니라 «모름»이다 — 예시처럼 `found.refused` 의 id 를 결과의 `attrs[UNREAD_JOBS]` 에 실으면, `allow_retraction` 규칙이 그 글의 회수 배치를 만들지 않아 옛 후보가 그대로 남는다. 로그 한 줄 `[Chain] <규칙 이름>: kept old cells of N job(s) the mapper could not read - <글 id>, …`. ⚠️ 싣지 않으면 그 글은 «아무것도 안 낸» 글로 읽혀 사람이 손대지 않은 옛 후보가 지워진다(20 행 이상 · 절반 넘게면 §5 처럼 거절). 그 글을 다시 읽히려면 §4 의 replay.
- 결과는 행 목록이고, 덧붙여 `requests`(부른 수 — 혼자 다시 물은 것 포함) · `texts`(넘긴 글 수) · `refused` 를 든다. 같은 수가 로그 한 줄 `[LLM] ask_links: N text(s) in K request(s) - R row(s), M text(s) refused`.
- 분당 상한 — LLM 을 부르는 자리(`ask_json`) 하나가 지난 60 초의 부름이 `requests_per_minute` 이면 가장 오래된 것이 60 초를 넘길 때까지 기다린다. 기다리는 동안 `[LLM] per-minute limit - waiting N s (20 requests a minute)` 한 줄(체인이면 `chain_worker.log`). PostgreSQL 이면 상한을 체인 슬롯 · 소급 실행 · 서버(맵퍼 벤치 · 소급 미리 보기)가 «같이» 쓴다 — 표 `llm_calls`(최근 부른 시각, 상한만큼의 행) 를 잠금 하나 아래에서 읽고 쓴다. 이 표는 웹 서버 기동이 만든다 — 표를 못 쓰면 `the per-minute limit could not use table llm_calls (<예외>: <DB 문장 첫 줄>) - a missing table is made by the web server's boot (create_all): start it once on this code` 로 거절(그 부름이 실패 — 체인이면 묶음이 다시 시도).
- 게이트웨이가 429 를 주면 그 답의 `Retry-After` 초(없으면 60 초) 기다렸다 다시 — 세 번까지, 매번 분당 상한을 지난다. 줄 `[LLM] the gateway answered 429 (too many requests) - waiting N s, then try 2 of 4`. 네 번째도 429 면 거절. ⚠️ openai 클라이언트 자체의 다시 시도(기본 2 번 — 429 · 연결 실패 · 5xx)는 그대로이고, 그 다시 시도는 이 상한을 안 지난다.
- 묶음 하나가 슬롯을 쥐는 시간 — 요청 수 × (모델 답 시간), 분당 상한에 걸리면 그 위에 기다림. `rows_per_run` 을 크게 하면 요청은 줄지만(사전을 덜 보냄) 한 묶음이 오래 걸린다. 다른 표의 줄은 다른 슬롯에서 돌아 LLM 이 막지 않는다([chain_rules](./config/chain_rules.md)). ⚰️ `run_in: operation`(작업 `rule_rows` 로 줄 세우기)은 은퇴했다 — 적혀 있어도 체인에서 돈다.
- 모델은 사전을 노드마다 한 줄로 본다 — `<키> (<타입>): <구절> / <구절> / …`. 같은 키가 두 타입에 있으면 그 노드들의 식별자는 `<타입>:<키>`. 모델은 원인 · 현상마다 그 식별자(맞는 노드가 없으면 null)와 글의 가장 짧은 명사구를 답한다.
- 노드 키는 사전에서만 온다 — 목록의 식별자면 그 노드의 `*_type` · `*_key`(말이 구절과 달라도). 빈 값(키 없음 · null · 빈 글자)이면 말이 어느 노드의 구절을 통째로 품을 때 그 노드(낱말 주머니, §8-1), 아니면 `*_type` · `*_key` 가 빈다. 목록에 없는 식별자는 키를 비우고 로그에 한 줄 `[LLM] link N of M answers cause_key '<식별자>', which the dictionary does not list - kept with its words only (llm:<모델>): '<말>'`. `*_phrase` 는 모델이 답한 말 그대로다 — 글과 견주는 것은 `evidence` 뿐(「글에서 베껴라」는 프롬프트의 부탁).
- 프롬프트는 요청마다 사전 전체를 담는다(나눠 보내지 않는다) — 고정 1,550 자(`ASK_LINKS_PROMPT` 에서 자리표시를 뺀 길이, 10-13 잼 · 묶음 전 1,404 자) + 노드마다 한 줄 + 글마다 `[<id>]` 줄. 노드마다 구절 셋이면 100 노드 약 7 천 자 · 1,000 노드 약 6.6 만 자 · 5,000 노드 약 34 만 자(지어낸 사전으로 잰 수). 보낸 그대로는 `llm_requests.log` 보낸 줄의 payload.
- 한 문장이 원인 · 현상을 여럿 말하면 모델은 짝마다 링크 하나를 답한다(같은 근거). 한 문장에서 후보가 여럿 나오므로 후보 표의 키에 `cause_phrase` · `phenomenon_phrase` 가 들어 있어야 한다 — 아니면 같은 키의 행이 서로 덮어쓴다.
- 체인은 키 칸이 빈 행을 버린다. 그래서 이 후보 표의 키는 `<글 id>` · `sentence_no` · `cause_phrase` · `phenomenon_phrase` 로 잡는다 — 구절은 늘 찬다.
- `certainty` 는 글이 «확인»이라 하면 `confirmed`, 그 밖에는 `suspected` — 사람이 확정하기 전에 사실로 올리지 않는다. 모델 답은 앞뒤 공백만 무시하고 견주며, 빈 답은 말없이 `suspected`, 그 밖의 답은 `suspected` 로 두고 로그에 한 줄 `[LLM] link N of M answers certainty '<답>', which is not confirmed or suspected - kept as suspected (llm:<모델>): '<근거>'`.
- `cause_direction` · `phenomenon_direction` 은 글이 그것이 «늘었다 · 올랐다»고 하면 `up`, «줄었다 · 떨어졌다»고 하면 `down`, 둘 다 아니면 빈다. 모델 답이 `up` · `down` 그대로(앞뒤 공백만 무시, 대소문자는 그대로)일 때만 쓰고, 그 밖의 답은 비우고 로그에 한 줄 `[LLM] link N of M answers cause_direction '<답>', which is not up or down - kept without it (llm:<모델>): '<말>'`.
- 운영자 지시는 셋째 인자 — `ask_links(texts, names, instruction="<지시>")`. 프롬프트에 들어가는 낱말은 사전 행 · 지시 · 글뿐이다.
- 근거(evidence)는 글 전체에서 찾는다 — 두 문장에 걸쳐도 찾고(문장 칸은 시작한 문장부터 끝난 문장까지, 문장 번호는 시작한 문장), 따옴표 12 자(`"'“”‘’«»「」『』`)와 말줄임(… ...)은 양쪽 다 견주지 않는다(`text_links.EVIDENCE_MARKS` — 목록 밖 따옴표는 견줌). 근거를 못 찾은 링크는 버리고 로그에 한 줄 `[LLM] link N of M quotes evidence the text does not hold - dropped (llm:<모델>): '<근거>'` — 나머지 링크는 그대로 후보가 된다.
- 묶음의 모든 글이 거절되면(위) `LlmRefused` 로 이름 대어 거절된다 — 글 하나면 그 글의 사유 그대로, 여럿이면 `every text (N) was refused - text <id>: <사유>`. 그 묶음이 실패하고(`max_group_attempts` 만큼 다시 시도한 뒤 FAILED), 사건의 `error_log` 에 체인 격리 기록이 남는다. 관리 화면에서 실패한 사건을 다시 돌린다.
- LLM 을 한 번 더 부르는 다른 쓰임새는 `ask_json(프롬프트)` — 답한 JSON 객체를 준다. 분당 상한 · 429 다시 묻기는 여기서도 같다.

### 6-2. 이미 아는 인과를 프롬프트에 — `known`

맵퍼가 `known={"follow": [<술어>, …], "hops": <걸음 수>}` 를 넘기면, 요청마다 프롬프트가 «그 요청의 글이 부르는 노드 사이에 이미 아는 링크»를 싣고 사전은 그 노드들만 싣는다 — 모델이 쌍을 따로따로 내지 않고 아는 그래프에 이어 붙이게(소유자 「그래프가 아니라 그냥 쌍의 집합」). 안 넘기면 프롬프트는 §6 그대로다.

```python
import pandas as pd
from mapper_sdk import UNREAD_JOBS, ask_links, mapper, sql

@mapper()
def text_cause_links_llm(df, db):
    names = sql(db, "SELECT <타입 칸> AS node_type, <키 칸> AS node_key, <말 칸> AS phrase "
                    "FROM <부르는 말 표>").to_dict("records")
    texts = [{"id": text_id, "text": text} for text_id, text in zip(df["<글 id 칸>"], df["<글 칸>"])]
    found = ask_links(texts, names, known={"follow": ["<인과 술어>"], "hops": 2})
    out = pd.DataFrame(found).rename(columns={"text_id": "<글 id 칸>"})
    out.attrs[UNREAD_JOBS] = [item["id"] for item in found.refused]
    return out
```

1. 씨앗 — 요청의 글이 구절을 품은 사전 노드(낱말 주머니 §8-1, `match_at` 같음). 식별자 순
2. 걷기 — 씨앗에서 운영 세상의 원장을 `follow` 술어로 `hops` 걸음. 화면의 걷기를 그대로 부른다(HTTP 없이 · 묶음 없이). 양 끝이 다 사전 노드인 링크만 쓴다 — 사전에 없는 노드는 모델이 식별자로 답할 수 없다. 씨앗의 타입이 키를 정확히 하나 선언해야 그 씨앗에서 걷는다(아니면 그 씨앗은 빼고 한 줄 `[LLM] known links: N seed(s) not walked - type(s) <타입> do not declare exactly one key`)
3. 고르는 차례 — ① 다리: 두 씨앗을 잇는 가장 짧은 길 위의 링크 ② 씨앗에서 1 걸음 ③ 2 걸음 … 같은 차례 안에서는 확인된 것(한정자 `certainty` 가 `confirmed`, §7) · 근거 원자가 많은 것 · 식별자 순. 걸음 링크는 씨앗을 돌아가며 씨앗마다 `known_per_seed`(기본 5) 개까지 — 다리는 안 센다. 무작위가 없어 같은 묶음은 같은 프롬프트다
4. 상한 — 사전 줄과 아는 링크 줄의 글자 합 `known_chars`(기본 4,000) 안에서 씨앗 먼저, 그다음 링크를 차례대로(그 링크 양 끝의 사전 줄과 함께), 안 들어가는 첫 링크에서 멈춘다
5. 적는 모양 — 사전 아래에 원인 하나에 결과를 모아:
   ```
   Known links, one per line: <cause id> -> <effect id>, <effect id> (<predicate>)
   N1 -> N2, N4 (leads_to)
   ```
   그 아래 지시 셋 — 새 링크의 양 끝은 있는 노드로 · 아는 링크 두 끝 사이의 단계를 글이 말하면 그 단계를 잇는 링크 둘로 · A 가 B 를, B 가 C 를 일으키면 A -> B 와 B -> C 를 따로, 같은 것은 같은 식별자나 같은 말로(요청 안 글 사이에서도). 답 모양은 그대로(쌍 목록) — 사슬은 «가운데 노드를 같이 쓰는 쌍들»로 온다
6. 씨앗이 없는 요청 — 아는 링크 절이 없고 사전이 빈다(지시 셋은 남음). 걷지 않는다
7. 결과의 `known` — 요청마다 `{texts, seeds, links, kept, nodes, listed}`: 닿은 링크 `links` 중 실은 `kept` · 사전 노드 `nodes` 중 실은 `listed`. 같은 수를 로그 한 줄 `[LLM] known links for N text(s): S seed(s), K of L link(s), dictionary J of M node(s)`
8. 대가 — 사전을 줄이므로 글에 구절이 그대로 안 나오는 동의어 노드는 빠진다 — 모델은 null 을 답하고 낱말 주머니가 받는다
9. `known` 의 모양이 틀리면(`follow` 가 비거나 글자 하나 · `hops` 가 1 이상 정수가 아님) 묻기 전에 `ValueError`

연결성 재기 — 바꾸기 전과 후에 같은 명령을 돌려 견준다(읽기만):

```bash
conda run -n assy_manager python server/scripts/causal_graph_connectivity.py --predicate <인과 술어>
```

`nodes` · `links`(서로 다른 원인 · 결과 · 술어) · `pieces`(이어진 덩어리 수) · `largest piece`(가장 큰 덩어리의 노드와 그 몫) · `lone pairs`(양 끝이 다른 노드에 안 닿는 링크와 그 몫). 쌍만 쌓이면 `pieces` 가 `links` 와 같고 `lone pairs` 가 100 % 에 가깝다 — 이어지면 `pieces` 가 줄고 `largest piece` 가 커진다. `--predicate` 여럿 · `--world <세상>` 여럿(없으면 운영 세상). PostgreSQL 이 읽기 전용임을 확인한 연결로 읽고, 그 술어의 원자를 원장에서 한 번 훑는다(술어 색인이 없어 원장 전체를 지난다 — 이 박스 원장 약 275만 행(통계 추정)에서 1.6 초).

## 7. 원장으로 — 확정한 후보만 `leads_to`

1. 후보 표에 사람이 채우는 확정 칸을 두고, 원장 소스의 `read.exclude_when` 에 그 칸을 적는다 — 빈 행은 원장이 안 읽는다
2. 원인 · 현상의 타입은 `entity_type: {"kind": "column", "column": "<타입 칸>"}` 으로 행에서 읽고, `keys` 에는 그 자리가 받는 타입들의 키를 다 적는다

```json
"leads_to": {
  "subjects": ["<원인 타입>"],
  "object": { "kind": "entity_ref", "types": ["<현상 타입>", "<다른 현상 타입>"],
              "qualifiers": { "required": [], "optional": ["certainty", "dir"] } }
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
    "certainty": { "kind": "column", "column": "certainty" },
    "dir": { "kind": "column", "column": "dir" } } } } }
}
```

- 원장은 부호 `dir` 하나만 잇는다(샘플 `server/config/sample/ledger_config.json.sample` 의 `leads_to@1` 도 `dir`) — 두 방향 칸은 후보 표에 근거로 남는다. `dir` 이 빈 행은 그 엣지에 `dir` 없이 들어간다(d338d3fdc · 아래 줄).
- `optional` 한정자의 칸이 빈 행은 그 엣지에 그 한정자만 없이 들어간다(빈 속성과 같은 읽기). `required` 한정자의 칸이 빈 행은 전처럼 그 행이 든 원장 묶음 전체를 실패시킨다(`missing_binding_value`).
- 타입 칸의 값은 선언된 타입 이름 그대로다(옛 철자 `x@1` 도 접힌다). 행마다 그 타입의 키만 쓴다.
- 그 자리가 받지 않는 타입의 행은 그 행만 `type_not_admitted` 로 거절되고 다른 행은 들어간다 — 받는 타입은 술어 목록(`subjects` · `object.types`)이 정한다.
- 타입 칸이 비거나 그 타입의 키 칸이 빈 행은 `no_identity`.
- 적재에서 거절: 받는 타입의 키를 안 적음 · 어느 타입에도 없는 키 · 칸 타입에 속성 · 받는 타입에 소스 속성(`bind.entities`) · 코드 맵퍼.
- 선언 화면의 타입 칸은 아직 이름만 고른다 — 칸에서 읽는 모양은 선언 원본(JSON)으로 적는다.

## 8. 사전 키우기 — 낱말 주머니 · 다시 맞추기 · 제안 표

후보 표의 빈 키 → 제안 표 → 사람이 확정 → 사전 → 빈 키가 찬다. 규칙 셋(8-2 · 8-3)은 골라 쓴다.

### 8-1. 낱말 주머니 — 수식어가 붙어도 노드를 찾는다

1. 말과 사전 구절을 «두 글자 조각»의 모음으로 본다 — 띄어쓰기 · 영문 대소문자 · 따옴표 · 말줄임은 빼고(근거 견주기와 같은 접기). 한 글자 구절은 그 글자 하나.
2. 노드의 점수 = 그 노드 구절의 조각 중 말에 든 몫(구절이 여럿이면 가장 큰 것). `match_at` 이상인 노드 중 가장 높은 하나 — 맨 위가 여럿이면 다른 노드 구절 안에 든 구절이 빠지고(긴 말이 이긴다, §2 와 같다), 그래도 서로 다른 노드가 둘 이상이면 노드 없음.

| 말 | 사전(노드마다 구절) | 답 |
|---|---|---|
| 본딩 설비의 접합 온도 파라미터 | 접합 온도 | 접합 온도의 노드 |
| 웨이퍼 계면 미충진 발생 | 계면 미충진 | 계면 미충진의 노드 |
| 본딩 설비의 접합 온도 파라미터 | 본딩 설비 · 접합 온도 | 없음 — 나란히 둘 다 통째로 듦 |
| 접합 온도 | 온도 · 접합 온도 | 접합 온도의 노드 — «온도»는 «접합 온도» 안이라 빠짐 |
| 접합 온도 상향 | 접합 온도 상승 | 1.0 이면 없음 · 0.8 이면 그 노드(조각 5 중 4) |

- `match_at` 기본 1.0 = 노드 구절이 통째로 든다(`phrase_bag.MATCH_AT`). 맵퍼에서 `ask_links(글, 부르는 말 행, match_at=0.8)`.
- 한 노드의 구절 둘이 함께 들면 그 노드다 — 겨루는 것은 서로 다른 노드뿐. 같은 구절이 두 노드에 있으면 노드 없음.
- 알려진 한계 — 낱말 경계를 안 본다(영문 구절 `void` 가 `avoid` 안에서도 든다, 규칙 뽑기 `find_links` 는 본다) · 한 글자 구절은 한 글자 말에만 맞는다.

### 8-2. 다시 맞추기 — 사전을 고치면 빈 키 후보를 LLM 없이 채운다

`rematch_rows(후보 행, 부르는 말 행, match_at=None)` — `cause_key` · `phenomenon_key` 가 빈 쪽만 그 쪽 `*_phrase` 의 주머니로 채운다(타입도 비었으면 타입도). 찬 키는 안 쓴다. 타입이 찼는데 찾은 노드의 타입과 다르면 그 쪽은 그대로. 아무것도 안 채운 행은 받은 행과 같다(`==`) — 맵퍼는 바뀐 행만 낸다.

```python
import pandas as pd
from mapper_sdk import mapper, rematch_rows, sql

KEYS = ["<글 id 칸>", "sentence_no", "cause_phrase", "phenomenon_phrase"]      # 후보 표의 키 칸 (§6)
CELLS = ["cause_type", "cause_key", "phenomenon_type", "phenomenon_key"]

@mapper()
def rematch_candidates(df, db):
    names = sql(db, "SELECT <타입 칸> AS node_type, <키 칸> AS node_key, <말 칸> AS phrase "
                    "FROM <부르는 말 표>").to_dict("records")
    rows = sql(db, "SELECT " + ", ".join(KEYS + CELLS) + " FROM <후보 표> "
                   "WHERE COALESCE(TRIM(cause_key), '') = '' "
                   "OR COALESCE(TRIM(phenomenon_key), '') = ''").to_dict("records")
    filled = [after for before, after in zip(rows, rematch_rows(rows, names)) if after != before]
    return pd.DataFrame(filled, columns=KEYS + CELLS)
```

```json
{
  "name": "<규칙 이름>",
  "trigger_table": "<부르는 말 표>",
  "target_table": "<후보 표>",
  "mapper": "rematch_candidates",
  "is_batch": true,
  "allow_retraction": false,
  "allow_chain_trigger": true
}
```

- 사전 행이 들어오거나 바뀌면 깨어난다. `allow_chain_trigger: true` — 8-3 의 확정 규칙이 쓴 사전 행에도 깨어나게.
- 채우기만 한다(`allow_retraction: false`). 사전 행을 지워도 채운 키는 남는다.
- 키가 구절인 후보 표(§6)라야 그 행을 고쳐 쓴다. 키에 `cause_key` 가 든 후보 표(§1 의 규칙 뽑기 모양)에서는 키를 채우면 새 행이 된다.
- 한 번 깨어날 때 사전 전체와 키 빈 후보 행 전체를 한 번씩 읽는다.

### 8-3. 제안 표 — 아무 노드도 안 받은 말을 모델이 사전 행으로 제안한다

`ask_dictionary(말 행, 부르는 말 행, instruction=None)` — 말 행 `{phrase, count}` 전부를 모델에게 한 번에 묻는다: 그 말이 가리키는 목록의 노드 식별자, 없으면 null 과 새 노드의 짧은 이름 · 타입, 그리고 한 줄 이유. 사전에는 아무것도 안 쓴다. 모델은 사전을 §6 과 같은 한 줄씩으로 본다.

| 제안 표 칸 | 적는 쪽 |
|---|---|
| `phrase`(키) · `count` · `suggested_node_type` · `suggested_node_key` · `new_node_name` · `reason` · `extractor` | 맵퍼 |
| `<확정 칸>` — 찬 값 = 확정 | 사람 |

- 새 노드 행은 `suggested_node_key` 가 비고 `suggested_node_type` 에 모델이 고른 타입이 든다. 고르는 타입은 «맵퍼가 읽은 부르는 말 행»의 타입들(겹친 것은 하나, 이름순)이다 — 모델링 노드 타입 넷 중에서만 고르게 하려면 그 SQL 에 `WHERE <타입 칸> IN (<그 넷>)` (다른 타입의 노드도 목록에서 빠진다).
- 그 타입이 목록에 그대로(앞뒤 공백만 무시, 대소문자 그대로) 없으면 타입을 비우고 한 줄 `[LLM] phrase N of M answers new_node_type '<타입>', which the dictionary does not list - suggested without a type (llm:<모델>): '<말>'`. 목록의 노드를 답한 행의 타입은 사전의 것이다 — 모델이 다른 타입을 말해도.
- 목록에 없는 식별자는 노드를 비우고 로그에 한 줄 `[LLM] phrase N of M answers node '<식별자>', which the dictionary does not list - suggested without a node (llm:<모델>): '<말>'`.
- 모델이 건너뛴 말은 행이 없고 한 줄 `[LLM] phrase N of M has no answer - no suggestion (llm:<모델>): '<말>'` — 다음에 깨어날 때 다시 묻는다.
- 답에 `phrases` 목록이 없으면 `LlmRefused` 로 그 묶음이 실패한다(§6 과 같다). 빈 말뿐이면 부르지 않는다.

```python
import pandas as pd
from mapper_sdk import ask_dictionary, mapper, sql

@mapper()
def suggest_dictionary(df, db):
    names = sql(db, "SELECT <타입 칸> AS node_type, <키 칸> AS node_key, <말 칸> AS phrase "
                    "FROM <부르는 말 표>").to_dict("records")
    phrases = sql(db, "SELECT phrase, COUNT(*) AS count FROM ("
                      " SELECT cause_phrase AS phrase FROM <후보 표> WHERE COALESCE(TRIM(cause_key), '') = ''"
                      " UNION ALL"
                      " SELECT phenomenon_phrase FROM <후보 표> WHERE COALESCE(TRIM(phenomenon_key), '') = ''"
                      ") AS p WHERE NOT EXISTS (SELECT 1 FROM <제안 표> s WHERE s.phrase = p.phrase)"
                      " GROUP BY phrase ORDER BY count DESC LIMIT 100").to_dict("records")
    return pd.DataFrame(ask_dictionary(phrases, names))


@mapper()
def confirmed_suggestion_to_dictionary(df, db):
    return pd.DataFrame({"<타입 칸>": df["suggested_node_type"], "<키 칸>": df["suggested_node_key"],
                         "<말 칸>": df["phrase"]})
```

```json
{
  "name": "<제안 규칙 이름>",
  "trigger_table": "<후보 표>",
  "target_table": "<제안 표>",
  "mapper": "suggest_dictionary",
  "is_batch": true,
  "allow_chain_trigger": true
}
```

```json
{
  "name": "<확정 규칙 이름>",
  "trigger_table": "<제안 표>",
  "target_table": "<부르는 말 표>",
  "mapper": "confirmed_suggestion_to_dictionary",
  "is_batch": true,
  "require": ["<확정 칸>", "suggested_node_type", "suggested_node_key"]
}
```

- 제안 규칙: 후보 표는 §6 의 맵퍼(체인)가 쓰므로 `allow_chain_trigger: true`. 제안 표에 이미 있는 말은 다시 묻지 않는다 — 새 말만, 많은 것부터 100 개(`LIMIT` 이 한 번 부를 때의 크기). `count` 는 물을 때의 수.
- 확정 규칙: `require` 의 세 칸이 다 찬 행만 넘어간다 — 맵퍼는 칸을 옮겨 적기만 한다. `allow_chain_trigger` 를 안 적어 사람이 쓴 것에만 깨어난다.
- 새 노드 제안(`suggested_node_key` 빔)은 확정해도 넘어가지 않는다 — 로그 `[Chain] <확정 규칙 이름>: N row(s) not handed over - required column(s) empty: suggested_node_key=N`. 사람이 `suggested_node_key` 에 새 노드의 키를 적으면(타입이 비었거나 틀렸으면 `suggested_node_type` 도) 그 쓰기로 깨어나 사전 행이 된다(`new_node_name` 은 참고).
- 확정을 지워도 이미 쓴 사전 행은 남는다. 사전 행이 들어오면 8-2 가 깨어나 그 말을 가진 빈 키 후보를 채운다.
