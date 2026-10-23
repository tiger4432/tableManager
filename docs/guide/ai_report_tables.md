# AI 리포트 — 요약표에 리포트 규칙 하나 (소유자 10-23)

```
운영에서는 요약표에 결과 칸 셋을 더하고, 요약표에 리포트 규칙 하나(send_to = 중계 PC 주소)를 적으면
계측 요약이 들어올 때 웨이퍼마다 리포트가 만들어져 메일 중계로 간다. 제품이 만드는 보조표는 0
```

> 소유자 10-23 「너무 복잡한데」 · 「보조표가 너무 많아」 · 「리포트는 웨이퍼당 하나지」. 요청 · 결과 · 걸음 · 웨이퍼 제품 표 넷과 요약표의 request_id · eval_id 칸, 조인 · decide · 보내기 규칙은 은퇴했다.
> 시범 동안(소유자 10-23 「막아」): 규칙을 `"enabled": false` 로 두면 요약 행이 들어와도 안 돈다. 소급 탭 «Replay chain rules over old data (R1)» 에 이 규칙 이름을 적은 리플레이만 돈다 — 모든 규칙이 같은 뜻이다.

## 1. 적는 것

- 요약표 선언에 결과 칸 셋(string) — 이름은 운영자가 정한다. 예: `report_state` · `report_file` · `report_reason`
- 어드민 Chain 탭에 리포트 규칙 하나 — `on` 과 `into` 가 요약표, `derive.report.results` 가 그 세 칸, `limits.group_by` 가 요약표의 웨이퍼 칸(리플레이가 웨이퍼 하나를 한 번에 — 안 적으면 행마다 따로 만들 수 있음)
- `ingestion_settings.json` 의 `"chain_slots"` 3 이상 — 리포트가 도는 동안(≤ 8 걸음 · ≤ 5 분) 체인 일꾼 하나를 쓴다

```json
{
  "name": "wafer_report",
  "on": {"table": "<요약표>"}, "into": {"table": "<요약표>"},
  "limits": {"group_by": ["wafer_id"]},
  "derive": {"kind": "report", "report": {
    "wafer":   {"table": "<웨이퍼 표>", "key": "wafer_id", "time": "measured_at", "lot": "lot_id",
                "evaluation": "<평가 칸>", "conditions": ["split", "recipe"]},
    "summary": {"table": "<요약표>", "wafer": "wafer_id", "item": "defect_item",
                "fail": "fail_chips", "total": "total_chips"},
    "results": {"state": "report_state", "file": "report_file", "reason": "report_reason"},
    "send_to": "http://<중계 PC>:8765/reports",
    "images":  {"table": "<이미지 표>", "wafer": "wafer_id", "item": "defect_item", "image": "image_path",
                "per_item": 3, "px": 320},
    "sets":    {"table": "<비교 묶음 표>", "name": "set_name", "member": "member", "kind": "kind",
                "kinds": {"evaluation": "eval", "lot": "lot"}, "default": ["baseline"]},
    "rows": ["particle", "scratch"], "digits": 1,
    "prompts": {"select": "…", "style": "…", "compare": "…"},
    "layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"},
               {"kind": "image", "fill": "images"}, {"kind": "text", "slot": "conclusion"}],
    "loop": {"steps": 8, "seconds": 300, "context_tokens": 16000}
  }}
}
```

- `send_to` 를 안 적으면 보내지 않는다(파일만 서버에).
- `wafer` 키는 칸 하나 또는 목록 — 모든 역할이 같은 순서 · 같은 길이.
- `summary` — `fail` · `total` 을 적으면 칸이 «x% (F/N)», `rate` 를 적으면 x 는 그 값(`rate_scale` 1 또는 100). rate 만이면 «조건별 묶은 열»과 파레토는 거절.
- `prompts.role` · `rules` · `functions.<읽기>.about` 을 비우면 제품 글이 들어간다.
- 옛 모양(요청 표 위의 규칙)은 로드에서 거절된다 — «derive.report.results names …» · «the report rule stands on its summary table …».

## 2. 도는 것

- 요약 행이 들어오면 그 묶음(파일 하나)의 웨이퍼마다 리포트 한 판. 한 웨이퍼의 행 전부에 같은 결과가 써진다.
- 결과 칸: state = `done` · `stopped`(+ reason) · send_to 가 있으면 `sending` → `done`, 세 번 실패면 `send failed` + reason. file = `<데이터 루트>/reports/<웨이퍼>.html`(키가 여러 칸이면 «_» 로 이음).
- 보내기는 체인 일꾼 밖 — 체인 워커의 유지보수 자리가 5 초마다 `sending` 을 찾아 `<send_to>/<파일 이름>` 으로 POST(`tools/report_receiver/receive.py`). 한 번에 규칙마다 20 파일.
- 걸음 기록: 파일 끝 접힌 «Evidence»(걸음마다 한 줄 — 부른 것 · 돌아온 것) + `chain_worker.log` 의 `[Report]` 줄.
- 같은 웨이퍼의 요약이 여러 파일로 들어오면 들어올 때마다 그 웨이퍼 리포트를 다시 만든다(같은 파일을 덮음).
- 다시 만들기: 어드민 소급 탭 «Replay chain rules over old data (R1)» 에 규칙 이름.

## 3. 읽는 표 — 이름은 선언으로

| 역할 | 한 행 | 칸 |
|---|---|---|
| wafer | 웨이퍼 하나 | 키 · 시간 · 랏 · 평가 · 조건 칸들(모델이 읽고 고름) |
| summary | 웨이퍼 × 디펙 아이템 | F(fail) · N(total) 또는 rate — 리포트 칸 «x% (F/N)» · 파레토 |
| images | 이미지 한 장 | 웨이퍼 · 아이템 · 이미지 위치 — 이번 웨이퍼에서 «발생한» 디펙만 |
| sets | 비교 묶음 × 멤버 | 묶음 이름 · 멤버 · 종류(평가 · 랏) — 사람이 적음 |
| info | 웨이퍼 × 정보 이름 | 값 — 요약 표 머리 밑에 한 줄씩 |
| picture_rows | 웨이퍼 그림 | 열마다 그림 한 장 |

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

**글은 «쓰기 호출» 한 번에서 나온다 (소유자 10-23 ㄱ, A)** — 읽기 걸음의 끝 대답은 `{"done": {}}`(다 읽었다)이고, 그 뒤 쓰기 호출 하나가 글 자리를 받는다. 걸음 상한 · 시간 상한에 닿아도 쓰기 호출은 한 번 한다(상태 · 사유는 상한 그대로, 글은 읽은 만큼).
```
쓰기 호출 ─ 역할 · rules(적었으면) · 글 자리 형식 · style · compare · control · 이번 요청
           + 읽은 표 전부: step 0 conditions() 접힘, 그다음 읽기마다 «step k: 부른 꼴» + 그 결과 그대로
             (같은 읽기를 다른 인자로 두 번 부르면 둘 다)
```
- 예산을 넘으면 «오래된 읽기부터» 행을 반씩 줄이고, 그 걸음 기록(Evidence 의 write 줄)에 «step k <읽기>: 남긴 줄 수»가 남는다. 다 줄여도 넘으면 «context over budget».
- 쓰기 호출이 글 없이 대답하면 «the write call answered no text».
- 쓰기 호출은 Evidence 한 줄(write)이고 걸음 상한에는 안 센다. 시간 상한에 닿은 리포트는 쓰기 호출 하나만큼 상한을 넘긴다.
- 잰 크기(박스): 20 열 + 대조 2 열 · 항목 10 · 정보 줄 3 에서 읽은 표 전부 ~7,000 자 · 어림 ~1,950 토큰. 게이트(항목 3 · 정보 줄 2)의 쓰기 호출은 2,445 자 · ~692.

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
- «이번 평가»는 리포트 웨이퍼의 평가이고 후보에서 빠진다. `"same": ["<웨이퍼 표의 칸>"]`(예: 제품군 칸)을 적으면 그 칸 값이 리포트 웨이퍼와 같은 후보만 남는다. 비우면 거르지 않는다.
- 고른 것은 «control <평가>» 묶음으로 요약 표 · 트렌드 가로에 붙는다. 사람이 적은 비교 묶음(sets)도 그대로 함께.
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
- **한글 낱말** — 파일에 나오는 고정 낱말은 전부 `labels` 를 지난다. 안 적은 이름은 영어 기본값으로 나온다. 모르는 이름은 저장 줄에 알림이 뜬다. `control` 은 묶음 이름이라 모델 문맥에도 같은 글이 간다.
- 붙여 넣은 양식의 charset 줄(엑셀은 `ks_c_5601-1987` 같은 것을 적는다)은 빠지고, 파일에는 utf-8 한 줄만 남는다.
