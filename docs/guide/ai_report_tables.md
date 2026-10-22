# AI 리포트 — 운영에서 지을 표 (소유자 10-22 저녁, 10-23 아침 착수)

> 지시서: `task/DESIGN_ORDERS.md` 맨 위 «AI 리포트 체인» (cd4eb98d0 외). 짓는 사람: 표 = 소유자(운영), 체인 · 함수 · HTML = 구현자 A.
> 칸 이름은 예시입니다. 실제 이름은 «리포트 설정 파일»에서 이 칸들에 이어 줍니다. 키 칸은 문자(시간 타입 금지).

## 1. 웨이퍼 표 — 웨이퍼 한 장에 한 행

| 칸 | 타입 | 뜻 |
|---|---|---|
| `wafer_id` | 키 | 웨이퍼 |
| `lot_id` | string | 랏 — «주요 랏» 고를 때 |
| `eval_id` | string | 평가 이름 — 이번 평가 / 타 평가를 이것으로 가름 |
| `measured_at` | datetime | 표 가로 시간순 · 트렌드 |
| `total_chips` | number | 모수 N |
| `good_chips` | number | 수율 = good_chips / total_chips |
| 조건 칸들 (`split` · `recipe` · `tool` …) | string | AI 가 읽고 웨이퍼를 고르는 조건. 몇 칸이든 |

## 2. 디펙 집계표 — 웨이퍼 × 디펙 아이템 한 행 (긴 표, 피벗으로도 봄)

| 칸 | 타입 | 뜻 |
|---|---|---|
| `wafer_id` + `defect_item` | 키 둘 | |
| `fail_chips` | number | F — 그 디펙으로 fail 된 칩 수 |

- 리포트 칸 «x% (F/N)» = 이 표 `fail_chips` ÷ 웨이퍼 표 `total_chips`. 파레토도 이 표에서.
- 피벗으로 보려면 표 선언에 `"pivot": {"column": "defect_item", "value": "fail_chips"}`.

## 3. 디펙 이미지 표 — 이미지 한 장에 한 행

| 칸 | 타입 | 뜻 |
|---|---|---|
| `image_id` | 키 | |
| `wafer_id` · `defect_item` | string | 이번 평가에서 «발생한» 디펙만 고를 때 |
| `chip_x` · `chip_y` | number | 칩 좌표 (갤러리 배치에도) |
| `image_path` | string | 이미지 파일 위치 — HTML 에 넣을 때 서버가 읽음 |

- 갤러리가 쓰는 이미지 표가 이미 이 칸들을 가지면 그것을 그대로 써도 됩니다.

## 4. 비교 묶음 표 — 타 평가 · 주요 랏을 사람이 적는 곳

| 칸 | 타입 | 뜻 |
|---|---|---|
| `set_name` + `member` | 키 둘 | 예: `baseline` + `EVAL_0915`, `baseline` + `LOT1234` |
| `kind` | string | `eval` 또는 `lot` |

- 리포트는 설정 · 요청에 적힌 묶음 이름을 읽어 그 웨이퍼들을 표 가로에 같이 놓습니다(머리에서 묶음이 구분됨).

## 5. 리포트 요청 표 — 요청 한 번에 한 행 (이 행이 체인을 깨움)

| 칸 | 타입 | 뜻 |
|---|---|---|
| `request_id` | 키 | |
| `eval_id` | string | 이번 평가 |
| `setting` | string | 어느 리포트 설정으로 |
| `compare_sets` | string | 비교 묶음 이름들(쉼표). 비우면 설정의 기본값 |
| `note` | string | 요청 메모 — AI 에게 같이 감 |

## 6. 리포트 결과 표 — 제품이 씀 (표 선언만)

| 칸 | 타입 | 뜻 |
|---|---|---|
| `request_id` | 키 | |
| `file_path` · `file_hash` | string | 서버에 저장된 HTML |
| `state` · `reason` | string | `done` / `stopped` + 사유(걸음 상한 · 5 분 · 문맥 초과 · 함수 거절) |
| `steps` | string | 걸음 요약 |
| `made_at` | datetime | 만든 시각 |

- 5 · 6 을 원장 노드로 세우는 선언(리포트 → 쓴 웨이퍼 엣지)은 A 가 짓기 전 보고에 예시로 드립니다.

## 리포트 모양 (정한 것)

- 요약 표: **가로 = 웨이퍼 시간순**(이번 평가 + 비교 묶음, 묶음 이름 줄로 구분) · **세로 = 디펙 아이템**(고른 항목) · 칸 = **x% (F/N)**
- 이미지: 이번 평가 웨이퍼에서 실제 발생한 디펙만
- AI(Gemma 4 70B): SQL 안 씀 · 조건표를 읽고 웨이퍼를 골라 함수를 «JSON 한 줄»로 부름 · 숫자는 함수가 냄 · 최대 8 걸음 · 5 분 · 문맥 예산 기본 16,000 토큰(설정)
- 설정 파일: 표 · 칸 연결 · 고를 항목 · 프롬프트(선택 기준 · 작성 스타일 · 비교 관점) · 양식 자리(표 · 이미지 · 글의 순서)
- 저장: HTML 한 파일(데이터 · 이미지 임베딩) 서버 · 결과 표 행 · 노드 · 리포트 목록 화면(시간순, 눌러서 열기)
- 메일: 첫 판 밖 — SMTP 알려 주시면 붙임

## 아침에 확인할 것

1. 수율을 `good_chips / total_chips` 로 — 이미 수율 칸이 있으면 그것
2. ✅ 소유자 10-22: «모수 · 발생 칩»을 정리하는 비슷한 표를 운영에서 만드는 중 — 1 · 2 번 표 대신 그 표를 씀. 아침에 그 표의 칸(웨이퍼 · 디펙 아이템 · 모수 · 발생 칩 · 시간)만 알려 주시면 설정을 그것에 맞춤. 한 표에 모수와 발생 칩이 같이 있으면 2 번 표 없이 됨
3. Gemma 4 70B 문맥 길이 — 알면 예산 기본값을 그것에 맞춤

## 짓는 방법 — 구현자 A 의 짓기 전 보고 (10-22 밤, 지은 것 없음)

**추천 ㄱ: 체인 규칙 하나가 리포트 한 건을 처음부터 끝까지(최대 8 걸음 · 5 분) 돌림**
- 리포트 요청 행 하나 → 규칙 하나가 깨어나 8 걸음을 돌고, 결과 행 · 걸음 기록 행 · HTML 파일을 한 번에 저장합니다
- 좋은 점: 지금 있는 «걷기 에이전트»와 같은 꼴 · 규칙 하나 · 멈춘 사유(걸음 · 시간 · 문맥 초과)가 결과 행 한 칸에 남음
- 위험: 체인 일꾼(슬롯) 둘 중 하나를 리포트 한 건이 최대 5 분 붙잡습니다 — 그동안 다른 체인은 일꾼 하나로 돎. 저장 전에는 진행이 «running» 으로만 보임
- 다른 안: ㄴ 걸음마다 체인 한 번(진행이 보이지만 8 걸음이면 체인 깊이 한도 8 을 16 으로 올려야 하고 그 한도는 모든 규칙에 걸림) · ㄷ 따로 도는 일꾼(실행기가 하나 더 생김, 가장 큼)

**설정 파일 모양** (`config/report_config.json`) — 표 · 칸 연결 · 행에 올 디펙 · 자릿수 · 이미지(디펙당 장 수 · 크기) · 비교(평가 · 랏 · AI 가 더 고를지) · 프롬프트(고르는 기준 · 글 스타일 · 비교 관점) · 양식 자리 순서 · 상한(8 걸음 · 300 초 · 16,000 토큰)

**총괄이 정한 것(기술)**
- 그리드 읽기 경로를 체인이 부를 수 있는 모듈로 «옮김»(사본 아님) — 함수 여섯이 그리드와 같은 읽기를 지나게
- 문맥 예산 = 글자 수로 토큰을 어림하고, 게이트웨이가 돌려준 실제 토큰 수로 걸음마다 보정
- 웨이퍼 목록 거르기는 지금 필터 문법(같음의 OR)으로 — 새 필터 종류 안 만듦
- 요청 · 결과 · 걸음 기록 표는 제품 표(걷기 에이전트 표와 같은 자리)
- 원장 선언은 제품이 «샘플»을 싣고, 실제 선언은 운영자가 웨이퍼 엔티티에 맞춰 적음

**아침에 여쭐 것(소유자 몫)**
4. 안 ㄱ 으로 갈지
5. ㄱ 이면 «리포트가 도는 5 분 동안 체인 일꾼 하나가 줄어듦»을 받을지, 일꾼 수 설정(chain_slots)을 2 → 3 으로 올릴지

**소유자 10-22 밤 더함**
- 「저런 표 설정은 내가 넣을 수 있게」 — 리포트 설정(표 · 칸 · 행 · 프롬프트 · 양식 · 상한)은 어드민의 선언 창에서 적음: 다른 선언과 같은 «왼쪽 글 + 오른쪽 폼», 스켈레톤에서 폼이 나옴, 표 · 칸 칸은 고르기(이름 제안). 저장 관문이 모르는 표 · 칸을 이름 대고 거절
- 「키도 복수로」 — 웨이퍼를 가리키는 칸은 모든 역할(wafer · fail · total · images)에서 한 칸 또는 칸 목록(예: `["lot_id", "wafer_no"]`). 역할끼리 잇는 것은 그 목록 «순서대로» 같은 값
- 쓴 웨이퍼를 한 줄씩 적는 제품 표 `report_wafer`(요청 키 · 웨이퍼 키 칸들)를 하나 더 둠 — 리포트 → 웨이퍼 엣지를 원장 선언으로 세우려면 필요(분자 하나 → 원자 하나 규칙)
- 설정이 사는 곳(총괄 판정): 따로 된 설정 파일이 아니라 «체인 선언의 한 종류» — 체인 규칙 창에서 `derive.kind = "report"` 를 고르면 리포트 칸(표 · 칸 · 행 · 이미지 · 비교 · 프롬프트 · 양식 · 상한)이 폼에 뜸. 조인 · decide 와 같은 창 · 같은 저장 관문

## 에이전트 문맥 — 한 걸음에 모델에게 넘기는 것 (총괄 설계 10-22 밤, 소유자께 보임, 토큰 수는 어림)

```
[1] 지시문 ─ 역할 · 규칙 글 · 함수마다 설명 글(선언 prompts.role · rules · functions.<이름>.about, 비우면 샘플 기본값)
              + 제품이 쥐는 것: JSON 답 형식 · 함수 이름 · 인자 · 걸음 상한 · 지금 몇 걸음째       ~1,000
[2] 설정 프롬프트 ─ select(고르는 기준) · style(글 스타일) · compare(비교 관점), 선언 글 그대로      ~300~800
[3] 이번 요청 ─ 평가 · 비교 묶음 · note                                                          ~100
[4] 조건표 접힘 ─ «조건 값 → 웨이퍼 수», 넘치면 키워드로 좁힌 것                                  ~1,500~3,000
[5] 지난 걸음 ─ 걸음마다 한 줄 요약(호출 → 결과 한 줄)                                            걸음당 ~100
[6] 바로 앞 걸음 결과 ─ 요약 모양 그대로(상위 N 행 · 칸 x% (F/N))                                  ~800~1,500
[7] 남은 예산 ─ "used ~N of 16,000 tokens, K steps left"                                           한 줄
```
- 문맥에 안 넣음: 이미지 자체(수 · 디펙 이름만) · 표 전체(HTML 에만) · 지난 걸음의 전체 결과([5] 한 줄로)
- 예산 넘으면 [6] 행 수 → [4] 순으로 줄이고, 그래도 넘으면 «context over budget» 으로 멈춤 + 사유 행

## 소유자 답 (10-22 밤)
- 짓는 방법 ㄱ — 규칙 하나가 리포트 한 건을 끝까지(≤ 8 걸음 · ≤ 5 분)
- 체인 일꾼 3 — 운영 설정 `chain_slots: 3` 은 소유자가 바꿈(재기동)
- 수율 같은 집계는 소유자가 «아이템별 요약 표»로 미리 만들어 둠 — 함수는 계산하지 않고 선언이 가리키는 요약 표 · 칸을 읽음. 모든 표 · 칸 이름은 선언으로
- 문맥 길이 모름 — 기본 16,000 토큰으로 시작

## 운영에서 적는 것 — 지은 뒤 (A, 10-23)

리포트 설정 = `chain_rules.json` 의 규칙 하나(어드민 Chain 탭 «derive kind: report»). 아래는 이 모양 그대로 진짜 프로세스 게이트에서 돈 선언입니다 — 표 · 칸 이름만 운영 것으로.

```json
{
  "name": "eval_summary",
  "on": {"table": "report_request", "require": [{"setting": ["eval_summary"]}]},
  "into": {"table": "report"},
  "derive": {"kind": "report", "report": {
    "wafer":   {"table": "<웨이퍼 표>", "key": "wafer_id", "time": "measured_at", "lot": "lot_id",
                "evaluation": "eval_id", "conditions": ["split", "recipe"]},
    "summary": {"table": "<아이템별 요약 표>", "wafer": "wafer_id", "item": "defect_item",
                "fail": "fail_chips", "total": "total_chips", "rate": "fail_rate", "rate_scale": 100},
    "images":  {"table": "<이미지 표>", "wafer": "wafer_id", "item": "defect_item", "image": "image_path",
                "per_item": 3, "px": 320},
    "sets":    {"table": "<비교 묶음 표>", "name": "set_name", "member": "member", "kind": "kind",
                "kinds": {"evaluation": "eval", "lot": "lot"}, "default": ["baseline"]},
    "rows": ["particle", "scratch"], "digits": 1,
    "prompts": {"select": "…", "style": "…", "compare": "…", "role": "", "rules": "",
                "functions": {"yield_by": {"about": ""}}},
    "layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"},
               {"kind": "image", "fill": "images"}, {"kind": "text", "slot": "conclusion"}],
    "loop": {"steps": 8, "seconds": 300, "context_tokens": 16000}
  }}
}
```

- `on.require` 의 `{"setting": ["<규칙 이름>"]}` — 요청 행의 setting 이 이 규칙 이름인 것만 이 규칙이 받음(설정이 여럿이면 규칙도 여럿).
- `summary` — 웨이퍼 × 아이템 한 행. `fail` · `total` 을 적으면 칸이 «x% (F/N)», `rate` 를 적으면 x 는 그 값(`rate_scale` 1 = 0~1, 100 = 0~100, rate 를 적으면 필수). rate 만 적으면 칸은 «x%» — 이때 «조건별 묶은 열»과 파레토는 F · N 을 더해야 하므로 거절. 같은 (웨이퍼, 아이템)이 두 행이면 더하지 않고 표 밑에 이름이 남음.
- `wafer` 키는 칸 하나 또는 목록(최대 4) — 모든 역할이 같은 순서 · 같은 길이.
- `prompts.role` · `rules` · `functions.<읽기>.about` 을 비우면 제품 글이 들어감.
- 규칙은 결과 표(report) 옆에 `report_step` · `report_wafer` 도 씀 — 규칙의 `writes` 칸(제품이 채움, 규칙 목록 · 부팅 줄에 보임). 같은 요청을 다시 만들면 두 표의 그 요청 행이 «통째로» 바뀜.
- 리포트는 한 번에 하나 — 결과 · 걸음 · 웨이퍼 표를 리포트끼리 같이 쓰므로 밀린 요청은 차례로 돔.

원장 — 리포트 → 쓴 웨이퍼 엣지 (ledger_config.json, 짧은 꼴)

```json
"entities":   {"report@1": {"keys": ["request_id"]}},
"vocabulary": {"reports_on@1": {"status": "active", "subjects": ["report@1"],
               "object": {"kind": "entity_ref", "types": ["<웨이퍼 엔티티>"],
                          "qualifiers": {"required": [], "optional": []}}}},
"sources":    {"report_wafer": {"table": "report_wafer", "sentences": [{
                 "sentence": "report-reads-wafer", "predicate": "reports_on@1",
                 "subject": {"node": "report@1", "keys": {"request_id": "request_id"}},
                 "target":  {"node": "<웨이퍼 엔티티>", "keys": {"<키 이름>": "key_1"}}}]}}
```
- `key_1` · `key_2` … 는 리포트 선언 `wafer.key` 의 순서. 웨이퍼 키가 두 칸이면 target keys 에 둘.

## 엑셀 양식 붙이는 법 (A, 10-23)

1. 엑셀에서 회사 양식 시트를 꾸미고, 리포트 내용이 들어갈 칸마다 표시 하나를 적는다 — 칸 하나에 표시 하나, 다른 글자 없이.
   - `{{title}}` 제목 · `{{meta}}` 요청 · 규칙 · 만든 시각
   - `{{summary}}` 처럼 `layout` 의 글 자리 이름 — 모델이 쓴 글
   - `{{table:yield_by}}` · `{{table:pareto}}` · `{{table:trend}}` — 그 표
   - `{{images}}` — 디펙 이미지 묶음
2. 그 범위를 복사(Ctrl+C) → 어드민 Chain 탭 리포트 규칙의 **Paste template** 에 붙여 넣고 저장. (그 칸은 클라 착지 뒤 — 그 전엔 선언 글의 `template` 칸에 HTML 그대로)
3. 리포트는 그 양식 그대로 나오고, 표시가 든 칸 안에 내용이 들어간다. 넓은 표는 그 칸 안에서 가로로 스크롤된다.

- `layout` 의 글 자리(`kind: text`)는 양식에 표시가 «있어야» 저장된다. 양식에만 있는 모르는 표시도 거절(이름을 댐).
- 엑셀이 같이 붙이는 살림 링크(File-List · Main-File · 테마)와 그림은 저장 때 빠진다 — 그림은 클립보드에 «내 PC 파일 경로»로만 오기 때문. 저장 줄에 «image(s) dropped: N».
- 거절: `<script>` · `on…` 속성 · 바깥 주소(`http` · `https` · `//`)를 부르는 `src` · `href` · CSS `url(…)` — 리포트 파일은 바깥에서 아무것도 안 불러온다.
- 우리 표의 칸에는 class 가 붙는다 — `rpt-group`(묶음 머리) · `rpt-head`(웨이퍼 머리) · `rpt-item`(항목) · `rpt-cell`(값). 양식의 `<style>` 에 이 이름으로 꾸밈을 적을 수 있다.
- `template` 을 비우면 지금의 기본 모양(`layout` 순서)으로 나온다.

## 대조군 — 모델이 최근 평가에서 고른다 (A, 10-23)

```json
"control": {"recent": {"days": 90, "evaluations": 10}, "max_wafers": 30, "max_evaluations": 3},
"prompts": {"control": "같은 레시피 · 같은 split 이 섞인 평가를 고르고, 조건이 튀는 웨이퍼는 빼라"}
```
- `recent` — 이번 평가의 «가장 늦은 웨이퍼 시각»부터 거꾸로 `days` 일 안 · 최신 `evaluations` 개(둘 다 적으면 둘 다 걸림). 그보다 늦은 평가는 안 들어감(다시 만들어도 같은 답).
- 모델은 `candidates()` 로 평가마다 한 줄(이름 · 날짜 · 웨이퍼 수 · 조건 값별 수)을 보고, `compare({"evaluations": [...], "wafers": [...]})` 로 고른다 — 평가를 적으면 그 평가 웨이퍼 전부, 웨이퍼를 적으면 그것만.
- 고른 것은 «control <평가>» 묶음으로 요약 표 · 트렌드 가로에 붙고, report_wafer 에 set_name «control <평가>» 로 남는다. 사람이 적은 비교 묶음(sets)도 그대로 함께.
- 거절: 이번 평가 · 범위 밖 평가 · 상한(`max_evaluations` 기본 3 · `max_wafers` 기본 30)을 넘는 고르기 — 사유가 모델의 다음 문맥으로 간다.
- 트렌드는 이제 이번 평가 + 모든 묶음(비교 · 대조)을 가로로 — 머리에 묶음 이름 줄.

## 요약 표 꾸미기 — 정보 표 · 그림 줄 · 조건부 서식 · 항목 계층 · 견본 줄 · 한글 낱말 (A, 10-23)

```json
"info": {"table": "<정보 표>", "wafer": ["wafer_id", "version"], "item": "name", "value": "value", "rows": ["자재", "평가자"]},
"picture_rows": [{"label": "합성맵", "table": "<그림 표>", "wafer": ["wafer_id", "version"], "image": "path", "px": 160}],
"formats": {"결함.입자.대": [{"vs": "control", "times": 2, "fill": "#ffcccc"},
                          {"when": ">=", "value": 5, "fill": "#ffffcc", "color": "#000000"}]},
"item_sep": ".",
"labels": {"report": "리포트", "item": "항목", "control": "대조", "mixed": "섞임 (%d)",
           "left_out": "제외 - 같은 웨이퍼 · 이름 두 행", "not_read": "%s 안 읽음", "nothing_written": "%s 글 없음",
           "no_image": "이미지 없음", "pareto_item": "항목", "pareto_fail": "불량 칩", "pareto_cumulative": "누적"}
```
- **정보 표** — (웨이퍼 키, 정보 이름, 값) 한 행씩. 요약 표 머리줄 밑에 정보 이름마다 한 줄이 선다. 그 웨이퍼들에 행이 없는 이름은 안 선다. `rows` 로 보일 이름과 순서를 고른다(비우면 행이 있는 이름 전부, 이름 순). 조건 값으로 묶은 열은 값이 하나면 그 값, 여럿이면 «mixed (n)». 같은 (웨이퍼, 이름) 두 행은 빠지고 표 밑 «Left out» 줄에 이름이 남는다.
- **그림 줄** — 열마다 그 웨이퍼의 그림 한 장이 파일에 박힌다. 그림은 이미지 소스(`image_sources.json`)의 참조 그대로이고, 디펙 이미지와 같은 함수로 줄여 넣는다(기본 160px). 못 읽은 그림은 그 칸에 사유가 나오고, 조건 값으로 묶은 열에는 «—» 가 들어간다. 모델에게는 «합성맵: n of m columns» 한 줄만 간다.
- **조건부 서식** — 항목마다 규칙 목록. 위에서부터 «처음 맞는 하나»가 칸을 칠한다. 견주는 수는 칸의 퍼센트다. `{"when", "value"}` 은 고정 기준이고, `{"vs": "control", "times"}` 는 «이번 평가 칸 ≥ 다른 묶음 칸들의 F 합 / N 합 × times» 이다(이번 평가 칸에만, summary 에 fail · total 이 있어야 저장됨). 요약 표와 트렌드 표에 걸린다. 색은 `#rrggbb` 만 받는다.
- **항목 계층** — `item_sep` 를 적으면 «결함.입자.대» 가 줄 머리 세 칸이 되고, 같은 앞부분은 한 칸으로 합쳐진다(rowspan). 같은 앞부분끼리는 처음 나온 자리로 모인다. 서식 · `rows` · 모델 문맥은 이름 전체를 쓴다.
- **두 단 머리** — 웨이퍼 키가 두 칸 이상이면 머리가 «웨이퍼 / 나머지» 두 단이 되고, 한 웨이퍼의 열들 위에 웨이퍼 이름이 한 칸으로 선다.
- **견본 줄** — 엑셀 양식에서 `{{table:yield_by}}` 줄 바로 밑 줄들의 첫 칸에 `{{info}}` · `{{picture}}` · `{{item}}` 을 적고, 그 줄들의 이름 칸(첫 칸)과 값 칸(둘째 칸)을 칠해 둔다. 우리 표의 그 종류 칸이 같은 class · style 을 받고(머리줄은 `{{table:yield_by}}` 줄의 서식), 견본 줄들은 표 하나가 든 칸으로 바뀐다. 견본 줄이 없는 종류는 `{{item}}` 줄의 서식을 받는다. 조건부 서식 색은 견본 서식 위에 칠해진다.
- **한글 낱말** — 파일에 나오는 고정 낱말은 전부 `labels` 를 지난다. 안 적은 이름은 영어 기본값으로 나온다. 모르는 이름은 저장 줄에 알림이 뜬다. `control` 은 묶음 이름이라 report_wafer 의 set_name 과 모델 문맥에도 같은 글이 간다.
- 붙여 넣은 양식의 charset 줄(엑셀은 `ks_c_5601-1987` 같은 것을 적는다)은 빠지고, 파일에는 utf-8 한 줄만 남는다.

## 계측 → 리포트 자동 — 요약표가 바뀌면 그 평가의 리포트가 돈다 (A, 10-23)

규칙 넷을 체인 창에 적는다. 제품 코드는 없다. 아래는 진짜 프로세스 판에서 제품 로더가 읽어 넷 다 running 으로 선 선언 그대로다 — 표 이름(gs_…)은 판의 것이니 자기 표로 바꾼다.

1. 조인 — 웨이퍼 표의 평가를 요약표에 쓴다. 요약표 선언에 `request_id` · `eval_id` 두 칸(string)을 더해 둔다.
```json
{"name": "gs_eval", "on": {"table": "gs_wafer"}, "into": {"table": "gs_summary"},
 "derive": {"kind": "join", "join": {
   "on": [{"left": "wafer_id", "right": "wafer_id"}, {"left": "version", "right": "version"}],
   "take": [{"from": "eval_id", "into": "request_id"}, "eval_id"]}}}
```
2. 결정 — 요약표에서 평가마다 요청 행 하나를 세운다(요청 키 = 평가).
```json
{"name": "gs_ask", "on": {"table": "gs_summary", "require": ["request_id"]},
 "into": {"table": "report_request"}, "allow_chain_trigger": true,
 "derive": {"kind": "decide", "decide": {"key": ["request_id"], "fields": ["note"], "list_columns": ["eval_id"]}}}
```
3. 리포트 규칙 — 요청 행에 깨어난다. `derive.report` 는 위 절들 그대로.
```json
{"name": "gs_report", "on": {"table": "report_request"}, "into": {"table": "report"}, "allow_chain_trigger": true,
 "derive": {"kind": "report", "report": {"wafer": {"…": "…"}, "summary": {"…": "…"}}}}
```
4. 소유자 맵퍼 자리 — 리포트가 done 이 되면 소유자 맵퍼(`server/mappers/<모듈>.py`)가 불린다. 맵퍼는 `payload["data"]["file_path"]["value"]` 로 파일 경로를 받는다(보내기 · 복사는 맵퍼 몫).
```json
{"name": "gs_send", "on": {"table": "report", "require": [{"state": ["done"]}]},
 "into": {"table": "gs_sent"}, "allow_chain_trigger": true,
 "derive": {"kind": "mapper", "mapper": {"mapper_module": "mappers.<모듈>", "mapper_function": "<함수>"}}}
```
```python
def send(db, payload, rule=None):
    path = payload["data"]["file_path"]["value"]      # <데이터 루트>/reports/<평가>.html
    ...                                               # 중계 PC 로 보내기 등
    return {"updates": []}
```

- 잰 것(박스, 평가 하나 20 열): 요약이 한 저장에 들어오면 요청 행 쓰기 1 · 리포트 1 판 · 마지막 요약 반영 · 4 초.
- ⚠️ 한계: 한 평가의 요약이 웨이퍼마다 따로 저장되면 리포트는 «첫 저장 뒤 한 판»만 돌고 뒤의 요약은 안 담긴다. 운영은 인제션이 대상 파일을 한 커밋으로 넣어 «한 번에» 들어온다(소유자 10-23).
- ⚠️ 이미지 표가 반쪽으로 들어온 때에 리포트가 돌면 리포트 이미지도 반쪽이다 — 조사 중.
- 다시 만들기는 지금처럼 요청 행 고치기(note 등) — 그 쓰기에 리포트 규칙이 다시 돈다.
