# 📦 RELEASE_LOG — 릴리스 요약

> **Status:** 🟢 Living | **Last-verified:** 2026-10-02 | **Owner:** Lead / PM
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 규율: [CONTRIBUTING](./CONTRIBUTING.md)

소유자가 요청해서 생긴 기능과 «동작이 바뀐» 것을 최신순으로 적습니다(총괄 9eccd4e12, 소유자 10-02 「주요 기능 추가할때 마다 사용법 등등해서 릴리지노트 하나에」). 내부 수리 · 정리 · 시험만 바뀐 것은 적지 않습니다. 주요 기능은 착지하는 커밋에 이 파일의 항목이 같이 들어옵니다.

**항목 모양:** `## YYYY-MM-DD · 기능 이름` 아래에 무엇 · 선언 예시(실제로 로드되는 것, 어느 파일에 적나) · 화면에서(버튼은 화면 글자 그대로) · 필요한 조건 · 바뀐 동작 · 자세히. 2026-09-28 전의 옛 항목은 그때의 「날짜 | 영역 | 요약」 한 줄 모양 그대로 둡니다. 상세 이력은 [history/](../history/README.md).

---

## 2026-10-02 · 보류 포함 행 복사 — 같은 키 원천 행들이 갈리면 공식 행이 보류된다

- **무엇** — 제품 맵퍼 `copy_rows_with_hold`. 10-01 의 `copy_one_row` 와 같은 일(원천 행 하나를 대상 표의 같은 키 행에, 그 원천 행의 층 `chain_ingestion (<원천 row_id>)` 으로 복사, 없으면 만듦)에 한 가지를 더 합니다. 같은 키(`IS NOT DISTINCT FROM`)의 원천 행들이 `columns` 에 서로 다른 값 묶음을 몇 개 가졌는지 세어, 2 이상이면 보류 칸을 빈 값으로, 아니면 `agreed` 로 씁니다. 보류 칸은 값과 같은 쓰기(같은 커밋)에 그냥 `chain_ingestion` 층으로 들어갑니다. 원장 소스가 `read.exclude_when` 에 보류 칸을 적으면 빈 보류 행은 원장에 들어가지 않고, 이미 있던 원자는 거둬집니다.
  같은 함수를 대상 표에 건 규칙이 부르면(trigger 와 target 이 같은 표) 값은 안 쓰고 보류만 다시 셉니다 — 사람이 공식 행을 고칠 때, 그리고 원천 행을 지워 공식 행에 보이던 값이 바뀔 때 깹니다.
- **선언 예시** — 대상 표(`config/table_config.json`)의 `column_types` 에 보류 칸 한 줄(`"hold": "string"`), 체인 규칙 둘(`config/chain_rules.json`), 원장 소스 한 줄. 규칙 둘은 제품의 규칙 검사로 거절 0 이었습니다.

<!-- example: chain_rule -->
```json
[
  {"name": "dt_log_to_official_dt", "trigger_table": "dt_log", "target_table": "official_dt",
   "mapper": "copy_rows_with_hold", "require": ["dt_job", "dt_x", "dt_y"], "allow_chain_trigger": true,
   "params": {"key_columns": ["dt_job", "dt_x", "dt_y"], "columns": ["c_bn"], "hold_column": "hold"}},
  {"name": "official_dt_hold_recount", "trigger_table": "official_dt", "target_table": "official_dt",
   "mapper": "copy_rows_with_hold", "allow_chain_trigger": true,
   "params": {"key_columns": ["dt_job", "dt_x", "dt_y"], "columns": ["c_bn"], "hold_column": "hold",
              "source_table": "dt_log"}}
]
```
  원장 소스(`config/ontology/ledger_config.json` 의 그 소스 `read`)에: `"exclude_when": [{"column": "hold", "blank": true}]`
  - 둘째 규칙의 `allow_chain_trigger` 는 원천 행 지움을 받으려고 적습니다(지움 회수는 체인이 씁니다). 그래서 복사가 공식 행에 쓸 때마다 한 번 더 셉니다. 같은 보류를 다시 쓰면 이벤트가 생기지 않아 돌고 돌지 않습니다.
- **화면에서** — 없음(규칙 · 표 선언).
- **필요한 조건** — 체인 워커 재기동. 행마다 한 번 불리고, 한 번에 세기 질의 하나가 더 붙습니다.
- **바뀐 동작** — 없음(새 맵퍼).
- **한계** — 지운 원천 행의 값이 공식 행에 «가려져» 있었으면(다른 원천 행의 값이 보이던 중) 보이는 값이 안 바뀌어 다시 세지 않고, 보류가 그대로 남습니다 — 지움 경로가 스스로 이벤트를 내는 것이 다음 착지입니다. 사람이 공식 표에 값을 적어도 보류는 풀리지 않습니다(원천 행들이 갈린 동안은 계속 빈 값).
- **자세히** — 이 항목과 같은 커밋

## 2026-10-02 · 걷기 경로 목록 — 자기 고리는 줄 안의 칩

- **무엇** — 걷기 화면과 R&D 보드 걷기 상자의 경로 목록이 «자기 고리를 뺀» follow 세트로 한 줄씩 나옵니다. 그 길이 지나는 타입의 자기 고리(`transfer` · `bonded_from` 처럼 X → X 인 술어)는 그 줄 안의 칩이고 기본으로 꺼져 있습니다. 전에는 고리 하나를 넣고 빼는 것마다 다른 줄이 되어 줄이 곱해졌습니다.
- **화면에서** — 시작 타입과 도착지를 고르면 경로 줄 아래에 `↻` 칩이 섭니다. 줄을 누르면 follow 는 그 길의 술어만, hops 는 그 길의 홉입니다. 칩을 켜면 follow 에 그 고리가 더해지고 hops 가 하나 늡니다. R&D 보드 걷기 상자도 같은 줄 · 같은 칩입니다.
- **필요한 조건** — 화면만 새로 받으면 됩니다.
- **바뀐 동작** — 경로 줄 수가 줄어듭니다. 고리를 따라가는 걷기는 칩을 켜야 합니다(전에는 고리를 넣은 줄이 따로 있었습니다). 긴 길에 칩을 여럿 켜면 옛 목록의 홉 상한(타입 수 − 1)을 넘는 조합도 고를 수 있습니다 — 옛 목록에는 없던 것입니다.
- **자세히** — [WALK.md](../architecture/WALK.md) §2 · 커밋은 이 항목과 같은 커밋

## 2026-10-02 · 메인 그리드 — ROW_ID 칸으로 거르기

- **무엇** — 메인 그리드에서 row_id 가 있는 관계(모든 표, 그리고 row_id 를 선언한 보기)의 끝(`UPDATED_AT` 뒤)에 `ROW_ID` 칸이 서고, 그 머리 아래에 다른 칸과 같은 거르기 칸이 있습니다. 행 id 의 앞 몇 글자나 일부로 그 행을 찾습니다. 새 검색 기능이 아니라 «있는 칸 거르기»라, 행 수 · 내보내기 · 쪽 넘김이 같은 거르기를 따릅니다. 서버는 전부터 row_id 거르기를 받았습니다.
- **화면에서** — 메인 그리드 맨 오른쪽 `ROW_ID` 칸 머리 바로 아래 칸에 id 앞부분을 칩니다. 다른 칸의 거르기와 같이 쓰입니다.
- **필요한 조건** — 서버 재기동(표 칸 목록이 `ROW_ID` 를 끝에 실음)과 화면 새로 받기.
- **바뀐 동작** — row_id 가 있는 관계 끝에 `ROW_ID` 칸이 붙습니다(편집은 막힘). `GET /tables/{표}/schema` 의 `columns` 가 `created_at` · `updated_at` 뒤에 `row_id` 로 끝납니다 — display_columns 에 이미 적은 표는 그 자리 그대로이고 두 번 나오지 않습니다. row_id 를 선언하지 않은 보기에는 칸이 없고, 그런 보기에 `row_id`(또는 `id`) 거르기를 보내면 서버가 「'<표>' has no row_id, so it cannot be filtered by 'row_id'」로 거절합니다(422). 시스템 칸 가운데 `ROW_ID` 하나만 거를 수 있고, `CREATED_AT` · `UPDATED_AT` · `UPDATED_BY` 에는 전처럼 거르기 칸이 없습니다. 맵 편집기의 X · Y · Val 고르기에는 `row_id` 같은 시스템 칸이 나오지 않습니다(밀어넣기가 싣지 못하는 칸).
- **자세히** — 커밋은 이 항목과 같은 커밋

## 2026-10-02 · 원장 소스 — 시각은 사건 엣지에만, read 는 안 적어도 된다

- **무엇** — 매핑의 `bind.occurred_at` 이 «사건 시각 자리»가 됩니다. 그것을 적은 매핑이 사건 엣지이고, 안 적은 매핑의 원자는 «사건 시각 아님»(`occurred_at_basis = 'ingested'`)으로 쓰입니다 — 저장 시각은 같은 행의 사건 시각 그대로라 사건 id 는 하나입니다(entity references 원자와 같은 모양). 소스의 `read` 칸은 안 적으면 제품이 채웁니다: `unit`(group_by 유무) · `identity` · `order_by`(표 선언의 가장 짧은 키) · `group_by`(`unit: group` 이면 `identity`) · `occurred_at`(사건 엣지가 적은 칼럼과 시간대, 사건 엣지가 없으면 행의 저장 시각) · `registration_probe`(register 문장의 주어 키 칼럼) · `map.unit` · `map.input_columns`. 적은 값은 적은 대로 읽습니다.
- **선언 예시** — `config/ontology/ledger_config.json` 의 `sources` 에서. `read` 가 없는 소스 하나, 사건 엣지 하나(`die-inspected`), 사건 엣지가 아닌 매핑 하나(`die-in-wafer`):

<!-- example: ledger_sources -->
```json
{
  "die_inspection": {
    "relation": "inspection_run",
    "map": {"implementation_id": "declarative-role", "implementation_version": 1},
    "bind": {"mappings": {
      "die-inspected": {"predicate": "inspected@1", "bind": {
        "occurred_at": {"kind": "column", "column": "observed_at", "timezone": "Asia/Seoul"},
        "subject": {"kind": "entity", "entity_type": "wafer@1",
                    "keys": {"wafer": {"kind": "column", "column": "base_wafer_id"}}},
        "target": {"kind": "entity", "entity_type": "die@1",
                   "keys": {"mat_id": {"kind": "column", "column": "base_wafer_id"},
                            "mat_type": {"kind": "constant", "value": "Wafer"},
                            "x": {"kind": "column", "column": "base_x"},
                            "y": {"kind": "column", "column": "base_y"}}}}},
      "die-in-wafer": {"predicate": "in_container@1", "bind": {
        "subject": {"kind": "entity", "entity_type": "die@1",
                    "keys": {"mat_id": {"kind": "column", "column": "base_wafer_id"},
                             "mat_type": {"kind": "constant", "value": "Wafer"},
                             "x": {"kind": "column", "column": "base_x"},
                             "y": {"kind": "column", "column": "base_y"}}},
        "target": {"kind": "entity", "entity_type": "wafer@1",
                   "keys": {"wafer": {"kind": "column", "column": "base_wafer_id"}}}}}
    }}
  }
}
```
  출하 샘플의 표 선언으로 읽으면 `read` 는 `identity`·`order_by` = `["run_uid"]` · `unit` = `row` · `occurred_at` = `{"column": "observed_at", "timezone": "Asia/Seoul"}` 로 채워집니다.
- **화면에서** — 선언 폼에서 안 적은 `read` 칸은 빨간 칸이 아니라 기본값이 채워진 칸으로 보입니다(`Default: …`). 매핑의 `Role occurred_at` 칸은 비워 둘 수 있습니다(비우면 사건 엣지가 아님).
- **필요한 조건** — 서버 재기동. 이미 쓴 선언은 바꿀 것이 없습니다 — 적은 값을 그대로 읽어 사건 id · 원자가 그대로입니다. 소스 시각을 사건 엣지로 옮기려면 `python -m scripts.migrate_ledger_slim_sources`(미리보기) 뒤 `--apply --source <소스>`. 사건 엣지가 소스와 «다른» 시각을 적은 소스(예: `dt_job` — 소스는 `basis: ingested`, 매핑은 `event_time`)는 옮기면 그 소스 원자 전부의 시각과 사건 id 가 바뀌어 `--change-atoms` 를 같이 줘야 하고, 그 뒤 그 소스를 통째로 다시 번역합니다(`python -m ledger.backfill --source <소스> --whole-source --apply`). 미리보기는 아무도 안 읽는 옛 바인딩 칸(`approval_status`)의 수도 보입니다 — `--drop-retired` 를 줄 때만 지우고, 그러면 묶음 해시가 한 번 바뀌어 모든 소스의 새 원자가 새 번역 버전을 갖습니다(이미 쓴 원자 · 커서 자리는 그대로). 박스에서 `dt_job` 을 옮기면 원자 866,192 개의 시각과 사건 id 가 바뀌고, 다시 번역은 원천 행 535,559 × 1,000 행당 5.85 s(박스에서 잰 율) ≈ 52 분입니다.
- **바뀐 동작** — `read.occurred_at` 을 안 적은 소스가 거절되지 않습니다(전에는 「missing field」). `unit: group` 에 `group_by` 를 안 적은 소스도 거절되지 않습니다(전에는 「missing field」 — 폼은 identity 를 미리 채우고 검사기는 거절했습니다). 사건 엣지들이 서로 다른 칼럼을 적거나 시간대 없이 적으면 `missing_time` 으로 거절합니다. 매핑이 `occurred_at` 을 안 적어도 거절되지 않습니다(전에는 `missing_required_role`).
- **자세히** — 이 항목과 같은 커밋

## 2026-10-02 · 메인 그리드 표 고르기 — 운영자가 적은 묶음 · 검색

- **무엇** — 메인 그리드의 표 드롭다운이 table_config 에 적은 `group` 이름 아래로 묶입니다(묶음은 이름 순, 안 적은 표는 맨 아래 `Other`). 드롭다운 앞의 검색 칸에 치면 표 이름으로 거릅니다. 분류는 운영자가 적습니다 — 제품이 표 이름이나 종류로 짐작해 나누지 않습니다. 원장 원자 보기(`ledger_atom_rows`)도 table_config 의 한 표라 같은 칸으로 묶입니다.
- **선언 예시** — `config/table_config.json` 에서 그 표의 항목에 `"group"` 한 줄. 출하 샘플은 group 을 비워 둡니다.

<!-- example: table -->
```json
{
  "shift_report": {
    "group": "Logs",
    "business_key": "report_id",
    "column_types": {"report_id": "string", "line": "string"},
    "display_columns": ["report_id", "line"]
  }
}
```

- **화면에서** — 메인 그리드 맨 위 `Table` 옆 검색 칸(`Search tables`)에 치면 드롭다운이 그 글자를 담은 표로 줄고, 남은 표가 있는 묶음만 머리줄이 남습니다. 지금 열린 표는 걸러져도 드롭다운에 남습니다. 어느 표도 group 을 안 적었으면 오늘처럼 묶음 없는 목록입니다.
- **필요한 조건** — 서버 재기동(`/tables` 가 묶음을 실음)과 화면 새로 받기.
- **바뀐 동작** — `GET /tables` 에 `groups`({표: 묶음}, 안 적은 표는 없음)가 붙습니다. `tables` 목록은 한 글자도 안 바뀝니다.
- **자세히** — 커밋은 이 항목과 같은 커밋

## 2026-10-02 · 시각 값 문장은 사건 시각이 아니라 «바인딩한 칸 값»을 싣는다

- **무엇** — 값이 시각인 술어(`vocabulary.<술어>.object.value_type: "timestamp"`)를 선언 맵퍼(`declarative-role`)로 번역하면, 원자의 값에 바인딩한 칸(`bind.value` 의 `column` · `timezone`) 대신 그 행의 사건 시각이 들어가고 칸 값은 버려졌습니다. 이제 바인딩한 칸 값이 들어갑니다. 원자의 사건 시각(`occurred_at`)은 그대로입니다.
- **화면에서** — 선언 폼에서 소스 시각이 `basis` 인 소스의 그 값 칸에 「This square is not read」가 붙지 않습니다(그 칸은 읽힙니다). `occurred_at` 칸에는 전처럼 붙습니다.
- **필요한 조건** — 서버 재기동. 이미 쓴 원자는 그대로이고, 그 소스를 다시 번역해야 고쳐집니다. 선언에 시각 값 술어가 없으면 할 일이 없습니다.
- **바뀐 동작** — 시각 값 술어를 선언 맵퍼로 쓰는 소스만 바뀝니다. 코드 맵퍼는 전부터 역할 이름으로 골라 이 결함이 없었습니다.
- **자세히** — 이 항목과 같은 커밋

## 2026-10-02 · 체인 대기열 — 소급 잡 하나는 한 줄

- **무엇** — 소급 실행 하나가 낸 체인 이벤트가 대기열에 «한 줄»로 뜹니다. 전에는 소급이 결과를 묶음마다 써서 묶음마다 이벤트가 생겼고, 잡 하나가 묶음 수만큼 여러 줄로 떴습니다(오류는 아니었습니다). 이제 서버가 잡이 낸 모든 이벤트(그것이 깨운 체인 쓰기까지)에 그 실행의 `run_id` 를 싣고, 대기열 답이 목록을 자르기 «전»에 그것으로 묶습니다.
- **화면에서** — 관리자 화면 `Chain` 탭과 `Overview` 의 대기열 표. 첫 칸 `Job / Transaction` 은 잡 줄이면 두 줄(위 «잡 이름(op)», 아래 «실행 id 앞 8자»), 아니면 전처럼 트랜잭션 id 입니다. `Rows` 칸은 그 줄이 싣는 «행 수»이고, 이벤트 수가 행 수와 다르면 수 앞에 «N events» 배지가 붙습니다. 목록이 상한에 걸리면 표 위에 `Showing` 한 줄(몇 줄 중 몇 줄 · 상한).
- **필요한 조건** — 서버 재기동(run_app.bat 전체)과 화면 새로 받기. 이주는 없습니다. 재기동 전에 큐에 들어간 이벤트는 실행 id 가 없어서, 그것들이 다 빠질 때까지는 같은 잡이 두 줄일 수 있습니다.
- **바뀐 동작** — `GET /admin/chain/queue` 의 `waiting_transactions[]` 한 항목이 «줄»입니다: `run_id` · `op` · `transaction_id`(잡 줄이면 null) · `events`(새 칸) · `rows`. 🔴 `rows` 의 뜻이 «이벤트 수»에서 «행 수»로 바뀌었습니다. `listed` 는 `{lines, lines_total, cap, capped}` 이고 상한은 «줄»에 걸립니다(`rows_scanned` 는 없어졌습니다). 표 첫 칸 머리줄이 `Transaction` 에서 `Job / Transaction` 으로 바뀌었습니다.
- **자세히** — [chain_ingestion_guide.md](../guide/chain_ingestion_guide.md)(5.6) · [BACKFILL_GUIDE.md](../guide/BACKFILL_GUIDE.md) · 서버 커밋 f843188e5 · 화면은 이 항목과 같은 커밋

## 2026-10-02 · 선언 폼 — 칸에 글자를 칠 때 끊기지 않음

- **무엇** — 원장 선언 폼의 글자 칸(엔티티 `Attributes` 같은 이름 칸 · 키 · 값 칸)에 칠 때, 글자마다 화면 전체를 다시 그리던 것을 멈췄습니다. 글자는 초안에만 들어가고, 화면은 칸을 떠날 때 한 번 그립니다 — 원문(JSON) 창이 이미 쓰던 규칙입니다. 한 글자를 받는 일이 한 화면 프레임 안으로 줄었고, 한글 조합도 끊기지 않습니다.
- **화면에서** — 관리자 화면 `Ontology Explorer` 탭에서 초안을 열고 칸에 칩니다. `Save` 는 첫 글자부터 누를 수 있고, 저장되는 것은 친 글자 그대로입니다.
- **필요한 조건** — 화면만 새로 받으면 됩니다.
- **바뀐 동작** — 칸에 치는 동안에는 같은 화면의 다른 자리(원문 창 · 경로 줄 등)가 따라오지 않고, 칸을 떠나면(다른 칸을 누르거나 Tab) 그때 따라옵니다.
- **자세히** — 커밋은 이 항목과 같은 커밋

## 2026-10-02 · 감사 로그 — 원장 영수증 줄을 누르면 그 트랜잭션의 행

- **무엇** — 이력 패널의 원장 배치 영수증 줄(`📒 Ledger batch`)을 누르면, 그 표로 바꾸고 «그 트랜잭션의 행들»을 띄운 뒤 멈춥니다. 전에는 행으로 옮겨 가려다 실패했습니다 — 영수증의 행 id 는 배치 id 라 표의 행이 아닙니다.
- **화면에서** — 이력 패널 `Global` 탭에서 `📒 Ledger batch` 줄을 누르면 아래 줄에 「Ledger batch · 표 · transaction …」이 뜨고 트랜잭션 거르기가 켜집니다. 몇 행인지는 그리드의 전체 수가 말합니다(그리드는 한 페이지만 들고 있어, 그 수를 줄에 적으면 1,000 행 넘게 바꾼 트랜잭션에서 틀립니다). 트랜잭션이 없는 영수증(백필 · 소급)은 띄울 것이 없어 `no transaction to show` 한 줄만 뜹니다.
- **필요한 조건** — 화면만 새로 받으면 됩니다.
- **바뀐 동작** — 다른 종류의 이력 줄을 누르는 동작은 그대로입니다. 같은 배치로 번역됐지만 그 트랜잭션에서 바뀌지 않은 행은 보이지 않습니다.
- **자세히** — 커밋은 이 항목과 같은 커밋

## 2026-10-02 · 그리드 행 지우기 — 기다리는 화면 · 답은 지운 수만

- **무엇** — 메인 그리드에서 여러 행을 지울 때, 서버 답이 «지운 수와 트랜잭션»만 담습니다. 전에는 지운 행마다의 이력을 통째로 돌려보냈습니다. 행마다 이력은 전처럼 DB 에 남고, 다른 화면은 전처럼 방송으로 지움과 그 이력을 받습니다. 10,000 행(박스 시험 DB · 좁은 표 · 넓은 표)에서 답 크기 3,227,847 · 3,207,847 → 98 · 98 바이트, 서버 처리 2.7 → 2.3 s(좁은 표) · 3.5 → 2.8 s(넓은 표).
- **화면에서** — 행을 고르고 `🗑️ Row` → 확인. 기다리는 동안 버튼이 꺼지고(사유 `Deleting…`) 아래 줄에 `Deleting N rows · S s` 가 초마다 오릅니다. 끝나면 그 행들이 빠지고 `Deleted N rows · S s`. 서버가 거절하면 서버의 사유 문장 뒤에 `— reload the table to see which rows remain`.
- **필요한 조건** — 서버 재기동.
- **바뀐 동작** — `POST /tables/{table}/rows/batch_delete` 의 답에서 `created_logs` 가 빠지고 `transaction_id` 가 생겼습니다. 이 답을 직접 읽는 스크립트가 있으면 이력은 DB 의 `audit_logs`(그 `transaction_id`)에서 읽습니다.
- **자세히** — [api_documentation.md](../spec/api_documentation.md)(1.3) · 화면 커밋 45d14144b · 서버는 이 항목과 같은 커밋

## 2026-10-02 · 원장 펼친 보기에 `occurred_at_basis` 칸

- **무엇** — 원장 펼친 보기(`ledger_atom_rows`, 메인 그리드)에 `occurred_at_basis` 칸이 맨 끝에 붙습니다. 비어 있으면 `occurred_at` 이 사건 시각이고, `ingested` 면 사건 시각이 아닙니다(references 원자 · dt_job 같은 소스).
- **선언 예시** — `config/table_config.json` 의 `ledger_atom_rows.column_types` 맨 끝에 한 줄. 출하 샘플(`config/sample/table_config.json.sample`)의 그 항목을 그대로 베껴도 됩니다:

```json
"occurred_at_basis": "string"
```
- **필요한 조건** — 이미 보기가 있는 설치는 `python server/migrations/add_ledger_atom_rows.py` 한 번(보기를 그 자리에서 다시 만듭니다. 원장 · 원천 표는 안 건드립니다). 새 설치는 서버가 처음 뜰 때 만듭니다.
- **자세히** — 이 항목과 같은 커밋

## 2026-10-02 · 바인딩에 적은 칸은 맵퍼 입력 칸에 다시 적지 않는다

- **무엇** — 바인딩 · `bind.entities` 의 속성 · 맵퍼 묶음(`map.unit.columns`) · `when` 이 부르는 칸은 읽기가 저절로 싣습니다. 검증기가 그 칸을 `map.input_columns` 에 다시 적으라고 하지 않습니다(전에는 「Profile column 'X' at … is missing」 으로 거절). `input_columns` 에는 코드 맵퍼가 선언 밖에서 직접 읽는 칸만 적습니다.
- **선언 예시** — `config/ontology/ledger_config.json` 의 `sources` 에서. 입력 칸이 비어 있어도 `dt_eqp`(엔티티 속성) · `netdie_count` · `event_time` · `dt_job` 이 읽힙니다:

<!-- example: ledger_sources -->
```json
{
  "dt_job": {
    "relation": "dt_job_rollup",
    "read": {"unit": "row", "identity": ["dt_job"], "order_by": ["dt_job"],
             "cursor": {"columns": ["dt_job"]},
             "occurred_at": {"basis": "ingested", "timezone": "Asia/Seoul"}},
    "map": {"implementation_id": "declarative-role", "implementation_version": 1,
            "unit": {"kind": "row"}, "input_columns": []},
    "bind": {
      "entities": {"dtjob@1": {"attributes": {"dt_eqp": {"kind": "column", "column": "dt_eqp"}}}},
      "mappings": {
        "counted": {"predicate": "has_netdie@1", "bind": {
          "occurred_at": {"kind": "column", "column": "event_time"},
          "subject": {"kind": "entity", "entity_type": "dtjob@1",
                      "keys": {"dt_job": {"kind": "column", "column": "dt_job"}}},
          "value": {"kind": "column", "column": "netdie_count"}}}
      }
    }
  }
}
```
- **화면에서** — 탐색기 소스 폼의 `Mapper input_columns` 에서 그 칸들이 눌린 채 잠긴 칩으로 나옵니다(전에는 키 · 묶음 · 정렬 · 커서 · 시각 칸만). 기본값은 잠기지 않은 칸 전부입니다.
- **바뀐 동작** — 이미 두 곳에 적힌 선언은 그대로 통과하고 같은 원자를 씁니다. `bind.entities` 속성 칸은 전에는 `input_columns` 에서 빠지면 검증은 통과하고 번역에서 `missing_binding_column` 으로 멈췄는데, 이제 저절로 읽힙니다. 그런 속성이 있는 소스는 재기동 때 커서 지문이 한 번 다시 찍힙니다(자리 그대로, 다시 읽는 행 없음). 맵퍼 묶음 칸이 관계에 없으면 `unknown_column`(`map.unit.columns`)으로 거절합니다.
- **자세히** — [ONTOLOGY_LEDGER_SETUP.md](../guide/ONTOLOGY_LEDGER_SETUP.md)(잠긴 칩 절 · 증상표) · 이 항목과 같은 커밋

## 2026-10-02 · 다이 → 웨이퍼 잇기 — 엔티티의 `references` 가 원자를 쓴다

- **무엇** — 엔티티 선언에 «이 엔티티는 자기 키로 정해지는 상위에 속한다»를 적으면, 그 엔티티를 부르는 소스가 어느 것이든(주어로든 목적어로든) 번역할 때 그 상위로 가는 엣지 원자를 하나 더 씁니다. 예: Wafer 다이는 mat_id 가 이름 붙인 웨이퍼 안에 있다 — 다이를 부르는 소스마다 다이 → 웨이퍼 `in_container` 가 생겨, 걷기에서 다이에서 웨이퍼로 닿습니다. 한 분자에 같은 다이가 둘이면 원자 하나이고, 그 분자가 이미 같은 사실을 말하면 다시 쓰지 않습니다. 이 원자의 시각은 사건 시각이 아닙니다(`occurred_at_basis` = `ingested`).
- **선언 예시** — `config/ontology/ledger_config.json` 의 `entities` 에서 그 엔티티에 `references` 목록(하나만 적어도 됩니다). 목록 모양은 이 착지 전 코드도 받아들여서, 서버를 재기동하기 전에 선언을 먼저 고쳐도 그 엔티티가 빠지지 않습니다:

<!-- example: ledger_entities -->
```json
{
  "die@1": {
    "keys": ["mat_id", "x", "y", "mat_type"],
    "references": [{"edge": "in_container@1",
                    "to": {"entity": "wafer@1", "keys": {"wafer": "mat_id"}},
                    "from": {"when": {"mat_type": "Wafer"}}}]
  }
}
```

  `edge` 는 어휘의 술어이고 그 술어의 `subjects` 에 이 엔티티가, `object.types` 에 `to.entity` 가 있어야 합니다. `to.keys` 는 «상위의 키: 이 엔티티의 키», `from.when` 은 «이 엔티티의 키: 값» — 맞는 원자에만 씁니다. 틀리면 로더가 이름 대어 거절하고, 그 엔티티와 그것을 부르는 소스가 같이 빠집니다.
- **화면에서** — 온톨로지 탐색기의 엔티티 폼에 `References` 칸(`Predicate` · `Points at` · `Only when`). 메인 그리드 메뉴의 `🚶 Walk` 에서 다이를 씨앗으로 `in_container@1` 을 따르면 웨이퍼에 닿습니다.
- **필요한 조건** — 서버 재기동. 선언에 `references` 를 넣으면 그 엔티티를 부르는 소스들의 선언 지문이 바뀝니다 — 체인 데몬이 다시 뜰 때 커서 지문을 새로 찍고(자리는 그대로) 그 뒤에 번역되는 행부터 references 원자가 생깁니다. 이미 번역된 행은 소스마다 다시 번역해야 생깁니다: `python -m ledger.backfill --source <소스> --whole-source --apply`. 원장 이주는 없습니다(새 칸 · 새 값 없음).
- **바뀐 동작**
  - 사건 시각이 아닌 원자 — 이 references 원자, 그리고 원래부터 `ingested` 로 적히던 원자(이 박스에서는 dt_job) — 는 걷기 시간 창(`since` · `until`)이 언제나 지나보내고, 창 밖 수(`interval_excluded`)에 안 들어가며, 응답 엣지의 `occurred_at` 이 비어 있고(null), 노드의 처음 본 시각(결측 목록의 oldest · newest)에 안 듭니다. 전에는 `ingested` 원자가 적재 시각으로 걸러지고 보였습니다.
  - 최신값 · 가져오기 순서는 저장된 시각 그대로입니다.
  - `GET /api/ledger/declaration` 의 `sources[].emits` 에 그 소스가 부르는 엔티티의 references 술어도 나옵니다.
- **자세히** — [WALK.md](../architecture/WALK.md)(구간 걷기 절) · 구현자 보고(task/scoped_redo_report.md) · 이 항목과 같은 커밋

## 2026-10-02 · 걷기 — 목적어 쪽 노드에서도 출발 · 정적 씨앗의 첫 걸음

- **무엇** — 걷기 화면에서 노드 타입을 고르면, 그 타입의 노드 목록이 «주어 쪽»만이 아니라 «목적어 쪽»에서도 나옵니다. 그래서 다른 술어의 목적어로만 나오는 타입도 노드를 고를 수 있습니다. follow 목록에도 그 타입으로 «들어오는» 술어가 나옵니다. 정적 타입(예: 레시피)의 노드를 씨앗으로 걸으면 «첫 걸음»은 정적이 아닌 노드로도 갑니다 — 레시피 하나에서 그 레시피를 쓴 웨이퍼들로. 둘째 걸음부터는 전처럼 정적 → 정적 아님을 밟지 않습니다. R&D 보드의 걷기 상자도 같은 follow 목록 · 같은 경로 목록을 냅니다.
- **선언 예시** — 새로 적을 것은 없습니다. 술어의 `subjects` · `object.types` 와 엔티티의 `class` 가 답입니다(`config/ontology/ledger_config.json`). 아래 둘이 있으면 `recipe@1` 을 고른 화면의 follow 에 `processed_with@1` 이 나오고, 그것을 따라 걸으면 웨이퍼에 닿습니다.

<!-- example: ledger_entities -->
```json
{
  "recipe@1": {"keys": ["recipe"], "class": "static"}
}
```

<!-- example: ledger_vocabulary -->
```json
{
  "processed_with@1": {
    "status": "active",
    "subjects": ["wafer@1", "dtwafer@1"],
    "object": {"kind": "entity_ref", "types": ["recipe@1"], "qualifiers": {"required": [], "optional": ["step"]}}
  }
}
```

- **화면에서** — 메인 그리드 메뉴의 `🚶 Walk` → 노드 타입을 고르면 `Pick a node` 칸에 그 타입의 노드가 나오고, 하나 고르면 아래 키 칸이 다 찹니다. follow 칸에는 그 타입이 주어든 목적어든 닿는 술어가 나옵니다(정적 타입도). 아무 술어도 안 닿으면 `No predicate touches` 뒤에 타입 이름이 보입니다. 노드 목록이 비면 `No node of this type in the ledger`, 노드를 다 못 읽었으면 `Not every node read` 와 읽은 노드 수가 보입니다. 타입을 바꾸면 새 타입에 안 닿는 follow 체크는 풀립니다. R&D 보드 걷기 상자의 `FOLLOW` 칸과 경로 목록도 같은 답입니다.
- **필요한 조건** — 서버 재기동(노드 목록 `GET /api/ledger/key-values` 의 답 모양과, 걷기 `GET /api/ledger/subgraph` 의 정적 씨앗 첫 걸음이 바뀌었습니다). 화면과 서버를 «같이» 올립니다. 새 화면이 옛 서버에 붙으면 노드 목록이 비어 「No node of this type in the ledger」로 보이고(옛 서버는 `subjects` 칸으로 답하고 새 화면은 `nodes` 칸을 읽습니다), 정적 씨앗의 첫 걸음도 가지 않습니다. 선언은 그대로입니다.
- **바뀐 동작**
  - 노드 목록이 주어 쪽만 읽다가 두 쪽을 읽습니다. 전에는 목적어로만 나오는 타입이 빈 목록과 「이 타입은 원장에 주어로 없습니다 (정적 허브)」로 보였습니다.
  - 노드 목록의 순서가 «많이 나온 순»에서 «값 순»으로 바뀌었습니다. 값 옆 괄호의 수는 그 노드를 주어 쪽이든 목적어 쪽이든 이름 부르는 원자 수입니다.
  - follow 목록에 들어오는 술어도 나옵니다. 주어 타입에 전부터 나오던 술어는 그대로 다 나옵니다.
  - 정적 씨앗에서 걸으면 첫 걸음이 정적이 아닌 노드로 갑니다. 전에는 씨앗 하나만 돌아왔습니다. 그 노드가 많으면 그림(`Graph`)에서는 «+개수 타입» 묶음 칩으로 오고, 표에서는 노드 상한과 원자 예산에서 잘렸다고(`nodes` · `claims`) 나옵니다. 걷는 도중 만난 정적 노드는 전처럼 막힙니다.
  - 경로 목록: 정적 시작 타입의 첫 걸음이 정적이 아닌 타입으로 가는 경로가 이제 나옵니다. 정적 타입을 «지나며» 정적이 아닌 쪽으로 나가는 경로는 전처럼 빠집니다. R&D 걷기 상자의 경로 목록은 전에는 그런 경로도 내놓았는데, 이제 걷기 화면과 같이 뺍니다.
  - 걷기 화면에서 타입을 바꾸면 새 타입에 안 닿는 follow 체크가 풀립니다. 전에는 체크가 남아 그대로 요청에 실렸습니다.
  - 걷기 화면 글자: 「주어 고르기」 → Pick a node · 「주어 목록 · 사유」 → Node list · 사유(서버에 못 닿으면 사유도 Subject list unreachable → Node list unreachable) · 「주어를 다 못 봤습니다 (N 까지)」 → Not every node read (up to N) · 「이 타입은 원장에 주어로 없습니다 (정적 허브)」 → No node of this type in the ledger · 「타입 에서 나가는 술어 없음」 → No predicate touches 타입. R&D 걷기 상자의 「No predicate out of … — this type is only an object」 도 No predicate touches 타입으로 바뀌었습니다.
  - 노드 목록 경로를 직접 부르는 곳이 있으면 새 칸 이름을 읽어야 합니다: `subjects` → `nodes` · `limits.scan_rows` → `limits.scan_nodes` · `scanned` 는 읽은 노드 수 · `order` 는 `value_asc`.
- **자세히** — [WALK.md](../architecture/WALK.md)(씨앗 절 · 정적 허브 규칙) · 커밋 6c44b0b3d(노드 목록) · 커밋 c46163324(정적 씨앗 첫 걸음) · 화면은 이 항목과 같은 커밋

## 2026-10-01 · 이미지 참조 — 칸에 적은 참조로 그림을 읽고, 메인 그리드에서 미리보기

- **무엇** — 표 칸에 그림의 «참조»(글자)를 적어 두면 서버가 선언된 출처(공유 폴더 · DB · URL)에서 그림을 읽어 줍니다. 메인 그리드에서 image 칸에 잠깐 머물면 미리보기 하나가 뜨고, 칸 안의 표시를 누르면 새 창으로 열립니다.
- **선언 예시** — 출처는 `config/image_sources.json` 에 적습니다(샘플: `server/config/sample/image_sources.json.sample`, DB 출처의 모양도 거기 있습니다).

<!-- example: image_sources -->
```json
{
  "photos": {"kind": "folder", "root": "D:/shared/photos"},
  "vendor": {"kind": "url", "base": "https://vendor.example.com/images/"}
}
```

  칸은 `config/table_config.json` 의 `column_types` 에 타입 낱말 `image` 로 적습니다(글자로 저장됩니다). 칸 값은 `photos:2026/10/a.png` · `vendor:a.png` · `https://…` 처럼 적습니다.

<!-- example: table -->
```json
{
  "inspection_photo": {
    "business_key": "photo_id",
    "column_types": {"photo_id": "string", "lot": "string", "photo": "image"},
    "display_columns": ["photo_id", "lot", "photo"]
  }
}
```

- **화면에서** — 메인 그리드에서 그 표를 열고 image 칸에 마우스를 잠깐 올리면 미리보기가 뜹니다. 칸 안의 `▣` 표시(툴팁 `Open image`)를 누르면 새 창으로 열립니다. 칸 자체를 누르면 오늘처럼 고르기 · 편집입니다.
- **필요한 조건** — 서버 재기동(새 경로 `GET /api/image`). `image_sources.json` 을 서버의 config 폴더에 둡니다. DB 출처의 비밀번호는 파일에 적지 않고 `password_env` 가 가리키는 환경변수에 둡니다.
- **바뀐 동작** — 처음 생긴 기능입니다. 그림은 언제나 서버를 거쳐 옵니다. 그림이 아닌 답, 너무 큰 답, 다른 곳으로 넘기는 답은 서버가 502 로 거절하고, 미리보기 자리에 그 문장이 보입니다. 같은 그림은 브라우저가 «최대 1시간»(서버의 `CACHE_SECONDS` 3600) 들고 있어, 그동안 다시 올려도 서버에 다시 가지 않습니다. 그래서 원본 그림을 바꿔도 그 시간 동안은 옛 그림이 보일 수 있습니다.
- **자세히** — [config/table_config.md](../guide/config/table_config.md)(`column_types` 의 `image`) · 커밋 a8dea2bcf · e1420082c · c23df3704 · 26c1b238d · 493275903

## 2026-10-01 · 글에서 «원인 → 현상» 후보 뽑기 (text_links)

- **무엇** — 회의록 · 8D 같은 글을 운영자가 적은 사전 두 표(부르는 말 · 연결 말)로 읽어, «무엇이 무엇의 원인이라고 적혔나»를 후보 행으로 만듭니다. 맵퍼가 부르는 도우미 `find_links` · `unknown_words` 입니다. 코드에는 어느 언어의 낱말도 없고, 낱말은 전부 사전 행에서 옵니다.
- **선언 예시** — 표 넷을 `config/table_config.json` 에 적습니다. 사전 둘은 `text_node_phrase`(노드를 부르는 말 — 한 노드에 말 여럿) · `text_link_phrase`(원인 · 나열 · 부정 · 추정 · 확인을 잇는 말)입니다.

<!-- example: table -->
```json
{
  "meeting_note": {
    "business_key": "note_id",
    "column_types": {"note_id": "string", "body": "string"},
    "display_columns": ["note_id", "body"]
  },
  "text_node_phrase": {
    "composite_key_source": ["node_type", "node_key", "phrase"],
    "column_types": {"node_type": "string", "node_key": "string", "phrase": "string"},
    "display_columns": ["node_type", "node_key", "phrase"]
  },
  "text_link_phrase": {
    "composite_key_source": ["phrase", "meaning"],
    "column_types": {"phrase": "string", "meaning": "string", "side": "string"},
    "display_columns": ["phrase", "meaning", "side"]
  },
  "text_cause_candidate": {
    "composite_key_source": ["note_id", "sentence_no", "cause_type", "cause_key", "phenomenon_type", "phenomenon_key"],
    "column_types": {"note_id": "string", "sentence_no": "number", "sentence": "string",
                     "cause_type": "string", "cause_key": "string", "cause_phrase": "string",
                     "phenomenon_type": "string", "phenomenon_key": "string", "phenomenon_phrase": "string",
                     "link": "string", "polarity": "string", "certainty": "string"},
    "display_columns": ["note_id", "sentence_no", "cause_key", "phenomenon_key", "link", "polarity", "certainty"]
  }
}
```

  `text_link_phrase.meaning` 은 `cause` · `and` · `negation` · `suspected` · `confirmed` 중 하나이고, `cause` 행만 `side`(`before` = 원인이 말 앞 · `after` = 말 뒤)를 적습니다. 같은 말을 두 뜻으로 쓰면 두 행입니다(「무관」 = `cause` 한 행 + `negation` 한 행). 맵퍼는 `server/mappers/` 의 파일에 둡니다.

<!-- example: mapper -->
```python
import pandas as pd
from mapper_sdk import find_links, mapper, sql

@mapper()
def meeting_cause_links(df, db):
    names = sql(db, "SELECT node_type, node_key, phrase FROM text_node_phrase").to_dict("records")
    links = sql(db, "SELECT phrase, meaning, side FROM text_link_phrase").to_dict("records")
    rows = [{"note_id": note_id, **row}
            for note_id, text in zip(df["note_id"], df["body"])
            for row in find_links(text, names, links)]
    return pd.DataFrame(rows)
```

  규칙은 `config/chain_rules.json` 의 `rules` 에 적습니다. 글을 고치면 그 글이 이번에 안 낸 옛 후보만 지워집니다.

<!-- example: chain_rule -->
```json
{
  "name": "meeting_note_cause_links",
  "trigger_table": "meeting_note",
  "target_table": "text_cause_candidate",
  "mapper": "meeting_cause_links",
  "is_batch": true,
  "allow_retraction": true,
  "trigger_job_column": "note_id",
  "target_job_column": "note_id"
}
```

- **화면에서** — 사전 두 표는 메인 그리드에서 행으로 적습니다(엑셀 붙여넣기도 됩니다). 글 표에 글이 들어오면 규칙이 돌아 후보 표가 채워집니다.
- **필요한 조건** — 표 넷이 선언돼 있어야 합니다. 맵퍼 파일을 둔 뒤 체인 워커 재기동. 사전 표를 고쳐도 규칙은 깨어나지 않으니, 고친 뒤에는 리플레이 명령으로 다시 돌립니다(가이드 4절).
- **바뀐 동작** — 새 도우미입니다. 맵퍼는 두 함수를 `mapper_sdk` 에서 import 합니다.
- **자세히** — [TEXT_LINKS_GUIDE](../guide/TEXT_LINKS_GUIDE.md) · 커밋 27978d555 · cb4d5157d

## 2026-10-01 · 원천 행 여럿이 받치는 칸 — 행 단위 맵퍼로 쓰면 지운 행의 값만 빠집니다

- **무엇** — 대상 표의 한 칸을 원천 행 여럿이 받칠 때(official 같은 표), 맵퍼가 항목마다 층 이름을 `chain_ingestion (<원천 row_id>)` 로, `origin_row_id` 를 그 원천 행으로 적으면 원천 행마다 층이 하나씩 남습니다. 원천 행 하나를 지우면 그 행의 층만 빠지고, 다른 행이 받치는 값은 그대로 보입니다. 제품 코드는 바뀌지 않았고 쓰는 법이 정해진 것입니다(총괄 55c1f20ee 판정).
- **선언 예시** — 맵퍼(`server/mappers/official_rows.py`). 원천 한 행을 받아 그 행의 칸을 그대로 씁니다.

<!-- example: mapper_module official_rows -->
```python
from database import crud
from mapper_sdk import df_to_updates, payloads_to_df

COLUMNS = ["dt_job", "dt_x", "dt_y", "c_bn"]   # 대상 표에 쓸 칸

def copy_one_row(db, payload, rule=None):
    df = payloads_to_df(payload)
    if df.empty:
        return {"updates": []}
    row_id = df.at[0, "row_id"]
    layer = crud.merged_layer_name(crud.CHAIN_SOURCE, row_id)
    result = df_to_updates(df[COLUMNS], rule["target_table"], source_name=layer, updated_by="copy_one_row")
    for item in result["updates"]:
        item["origin_row_id"] = row_id
    return result
```

  대상 표와 규칙. 규칙에 `is_batch` 를 적지 않고(행마다 한 번 불립니다), `require` 에 대상의 키가 되는 칸을 적습니다. 소유자의 흐름처럼 `dt_log` 의 키 칸을 다른 체인(조인)이 채우면 `"allow_chain_trigger": true` 가 있어야 채워진 뒤에 다시 깨어납니다. 없으면 사람 · 파일 · 수집기가 바꾼 행에만 깨어나, 조인이 키를 채운 행은 넘어가지 않습니다.

<!-- example: table -->
```json
{
  "official_dt": {
    "composite_key_source": ["dt_job", "dt_x", "dt_y"],
    "column_types": {"dt_job": "string", "dt_x": "number", "dt_y": "number", "c_bn": "string"},
    "display_columns": ["dt_job", "dt_x", "dt_y", "c_bn"]
  }
}
```

<!-- example: chain_rule -->
```json
{
  "name": "dt_log_to_official_dt",
  "trigger_table": "dt_log",
  "target_table": "official_dt",
  "mapper_module": "mappers.official_rows",
  "mapper_function": "copy_one_row",
  "require": ["dt_job", "dt_x", "dt_y"],
  "allow_chain_trigger": true
}
```

- **화면에서** — 없음(맵퍼 파일과 체인 규칙).
- **필요한 조건** — 맵퍼 파일을 둔 뒤 체인 워커 재기동. 행마다 한 번 불리므로 1,000 행 묶음이면 맵퍼가 1,000 번 불립니다.
- **바뀐 동작 · 주의** — 층 이름은 반드시 `chain_ingestion (` 로 시작해야 체인이 쓴 층으로 읽힙니다. 다른 이름이면 파일 층처럼 같은 값이 한 층으로 접혀, 행 하나를 지울 때 값이 같이 빠집니다. 이 이름은 소스 순위표에 없어서 순위 99(가장 낮음)로 읽힙니다. 같은 칸에 다른 소스의 값이 있으면 그쪽이 이길 수 있습니다. 남는 것도 셋 있습니다. 키가 바뀐 행의 옛 층, `require` 칸이 다시 빈 행, 받치는 행이 0 이 된 대상 행(빈 행으로 남음)입니다.
- **자세히** — [MAPPING_GUIDE](../../authoring/MAPPING_GUIDE.md) · [CHAIN_COPY_WHEN_FILLED_GUIDE](../guide/CHAIN_COPY_WHEN_FILLED_GUIDE.md) · `task/IMPLEMENTER_ORDERS.md` 의 「official 층 넓히기(나) 짓지 않음」 덧붙임

## 2026-10-01 · 원장 펼친 보기 — 메인 그리드에서 원자를 원천 행으로 찾기 (ledger_atom_rows)

- **무엇** — 원장의 원자 하나 × 그 원자를 만든 원천 행 하나가 한 줄인 «읽기 전용 보기»입니다. 주어 · 술어 · 목적어 · 원천 표 · 원천 row_id 가 저장된 글자 그대로라, 그리드의 칸 필터로 「이 행이 만든 원자가 무엇인가」 「이 원자가 어느 행에서 왔나」를 찾습니다.
- **선언 예시** — `config/table_config.json` 에 보기로 등록합니다(샘플에 같은 항목이 있습니다).

<!-- example: table -->
```json
{
  "ledger_atom_rows": {
    "kind": "view",
    "composite_key_source": ["atom_id", "source_relation", "source_row_id"],
    "column_types": {"atom_id": "string", "occurred_at": "datetime", "subject_type": "string", "subject": "string",
                     "predicate": "string", "object": "string", "qualifiers": "string", "source_who": "string",
                     "source_relation": "string", "source_row_id": "string"}
  }
}
```

- **화면에서** — 메인 그리드 위의 표 고르기에서 `ledger_atom_rows` 를 고르고, `SOURCE_ROW_ID` 나 `SUBJECT` 칸 머리 아래 필터에 값을 적습니다. 보기라 편집은 안 됩니다.
- **필요한 조건** — PostgreSQL. 이주 명령 두 번(저장소 루트에서): `python server/migrations/add_ledger_atom_rows.py --report`(있는지 · 크기만 봄) 다음 `python server/migrations/add_ledger_atom_rows.py`(색인 둘과 보기 — 쓰기는 계속되고, 다시 돌려도 같습니다).
- **바뀐 동작** — 새 보기입니다. 원장 표에는 색인을 더하지 않고, 행 참조 표에만 둘을 더합니다.
- **자세히** — `RUN.md` · 커밋 57bc6d5e9

## 2026-10-01 · HTTPS 로 열기 — Windows 서버 앞에 nginx

- **무엇** — 사내 CA 인증서로 https 를 여는 설정 안내입니다. 제품 코드는 바뀌지 않았습니다.
- **선언 예시** — 없음(가이드의 nginx.conf).
- **화면에서** — 없음.
- **필요한 조건** — 인증서 파일(pfx · p7b, 가이드대로 fullchain 으로 만듦) · nginx · 방화벽 443 열기 · 부팅 때 자동 실행.
- **바뀐 동작** — 없음(안내만).
- **자세히** — [HTTPS_PROXY_GUIDE](../guide/HTTPS_PROXY_GUIDE.md) · [DEPLOY_SETUP](../guide/DEPLOY_SETUP.md) · 커밋 2967827ba

## 2026-10-01 · 걷기 — 메인 메뉴에서 열기 · 되내려가지 않기 · 묶음 · Graph 보기

- **무엇** — 걷기만 하는 화면을 메인 그리드 메뉴에서 엽니다. 걸음은 방금 올라온 술어로 형제에게 «되내려가지» 않습니다(다이 → 웨이퍼 → 다이 수백 개를 막음). Graph 보기는 시작점에서 걸어 닿는 서브그래프를 걸음마다 한 층으로 그립니다. 한 노드에서 같은 술어로 20 개 넘게 퍼지는 갈래는 «묶음» 하나로 보이고, 눌러야 펼쳐집니다. 그림의 점을 마킹하면 거기서 이어 걷습니다. 노드 이름표는 선언된 키를 모두 씁니다.
- **선언 예시** — 짝인 술어는 `config/ledger_config.json` 의 `vocabulary` 에서 `inverse_of` 로 알려 줄 수 있습니다(새 칸, 안 적어도 됩니다). 같은 술어를 반대로 내려가는 걸음은 적지 않아도 막힙니다.

<!-- example: ledger_vocabulary -->
```json
{
  "wafer_in_slot@1": {
    "status": "active",
    "subjects": ["wafer@1"],
    "object": {"kind": "entity_ref", "types": ["lot_slot@1"], "qualifiers": {"required": [], "optional": []}},
    "inverse_of": "has_wafer@1"
  }
}
```

- **화면에서** — 메인 그리드 메뉴의 `🚶 Walk`(→ `/walk.html`) → 노드 타입과 키를 고르고 `Graph` → `날리기`. 그림에서 점을 누르면 그 노드의 사실이 보이고 마킹됩니다. `Continue` 를 누르면 그 마킹에서 이어 걷습니다. 노드 밑의 «+개수 타입» 칩을 누르면 그 묶음이 같은 그림에 펼쳐집니다.
- **필요한 조건** — 서버 재기동(걷기 경로의 묶음 · 되내려가기 판정).
- **바뀐 동작** — 걷기 답에서 «같은 술어를 반대로» 또는 «선언한 짝 술어로» 형제에게 내려가는 걸음이 사라집니다. 노드 이름표가 키를 모두 부릅니다(전엔 앞 두 값만이라 다이 278 개가 이름표 42 개를 나눠 썼습니다). 표(`Table`) 보기의 걷기는 묶지 않습니다.
- **자세히** — [WALK.md](../architecture/WALK.md) · [ONTOLOGY_LEDGER_SETUP](../guide/ONTOLOGY_LEDGER_SETUP.md)(술어 표) · 커밋 ce041066d · 3ab88ae49 · b1245bab9 · 74974d6ed · 69f15a845 · 4bedb9c0a

## 2026-10-01 · 원장 가지(branch) · `one` 술어의 «지금 값»

- **무엇** — 원장 선언을 여러 벌 견주어 보려고 «가지»를 만듭니다. 가지에는 기본 선언과 «다른 소스만» 담기고, 걷기는 가지 + 기본을 한 보기로 읽습니다. 선언창과 R&D 보드에서 가지를 고릅니다. 그리고 `cardinality: one` 술어의 지금 값은 «가장 늦은 occurred_at» 하나로 읽힙니다.
- **선언 예시** — 손으로 적는 파일은 없습니다. 화면이 가지 선언을 `config/ontology_worlds/<이름>` 에 만듭니다.
- **화면에서** — 어드민 `Ontology Explorer` 탭 → `Branch` 에서 `New branch` 칸에 이름을 적고 `Create` → 그 가지에서 선언을 고쳐 저장 → (아래 번역 명령) → R&D 보드(`/rnd-board.html`)의 `Branch` 에서 그 가지를 고릅니다. 고치던 글이 있으면 `Keep draft` · `Discard draft` · `Stay` 를 묻습니다. 지울 때는 `Delete branch`(원자 수를 먼저 보여 줌). `Default` 는 오늘의 원장입니다.
- **필요한 조건** — PostgreSQL · 서버 재기동. 가지에서 바꾼 소스는 한 번 번역합니다(server 폴더에서): `python -m ledger.backfill --source <바꾼 소스> --world <이름> --whole-source --apply`(`--apply` 없이 돌리면 미리보기).
- **바뀐 동작** — `one` 술어: 쓸 때 막던 거절(`cardinality_one_violated`)이 없어지고, 읽을 때 최신 사실 하나만 지금 값으로 보입니다. 같은 시각의 사실 둘은 둘 다 지금 값이고 노드에 `current_conflicts` 가 붙습니다. 명령줄의 `--ontology-root` 는 `--world` 로 바뀌었습니다. 통째 다시 읽기(`--whole-source --apply`)는 표에서 사라진 행의 원자를 거둡니다.
- **자세히** — [ONTOLOGY_LEDGER_SETUP](../guide/ONTOLOGY_LEDGER_SETUP.md) · `RUN.md` · 커밋 070a4558b · ccf374d48 · 609341a55 · 77a5f264c · ec01b42de · 8d9228cf1 · 08d2f8189 · fa41a6f25 · 051c7c187

## 2026-10-01 · 원장 선언 setup_version 6 — 준비기(prepare) 은퇴 · 계보는 체인 규칙이 씁니다

- **무엇** — 원장 소스의 `prepare` 칸이 없어졌습니다. 소스는 `relation` · `read` · `map` · `bind` 넷입니다. `lot_event` 원장 소스가 은퇴했고(이미 만든 원자는 남습니다), 계보(`derived_from`)는 체인 규칙이 `lot_lineage` 표에 쓴 것을 원장 소스 `lot_lineage` 가 읽습니다.
- **선언 예시** — 이주 명령이 운영 파일에 넣어 주는 규칙입니다(`config/chain_rules.json`, 샘플에 같은 규칙).

<!-- example: chain_rule -->
```json
{
  "name": "lot_event_to_lot_lineage",
  "trigger_table": "lot_event",
  "target_table": "lot_lineage",
  "mapper_module": "mappers.lot_lineage_mapper",
  "mapper_function": "build_lot_lineage_rows",
  "is_batch": true,
  "enabled": true,
  "params": {
    "lot_column": "lot_id",
    "parent_column": "parent_lot",
    "child_column": "child_lot",
    "time_column": "event_time",
    "event_type_column": "event_type",
    "target_parent_column": "parent_lot",
    "target_child_column": "child_lot",
    "target_event_type_column": "event_type",
    "target_time_column": "event_time"
  }
}
```

- **화면에서** — 없음(이주 명령).
- **필요한 조건** — 저장소 루트에서 `python server/scripts/migrate_ledger_config_to_v6.py`(미리보기 — 바꿀 것을 줄마다 보여 주고 아무것도 안 씀) 다음 `python server/scripts/migrate_ledger_config_to_v6.py --apply`(ledger_config · table_config · chain_rules 셋, 백업을 남김). 그다음 서버 · 체인 워커 재기동.
- **바뀐 동작** — `prepare` 를 적은 소스는 그 소스만 이름 대어 거절됩니다(`prepare_retired`). 이주 전의 v5 파일은 메모리에서 v6 로 읽히고 로그에 「setup_version 5 read as 6 … Next: run scripts/migrate_ledger_config_to_v6.py」 한 줄이 남습니다. 노드 타입 목록은 그 노드를 이름 대는 원자가 하나라도 있으면 뜹니다. `lot_slot_wafer` · `lot_lineage` 맵퍼는 칸 이름을 전부 규칙의 `params` 에서 읽고, 빠진 칸은 규칙과 칸 이름을 대어 거절합니다.
- **자세히** — [ONTOLOGY_LEDGER_SETUP](../guide/ONTOLOGY_LEDGER_SETUP.md) · `RUN.md` · 커밋 0b59a2f30

## 2026-10-01 · 숫자는 한 철자로 — 문자 칸의 숫자 · 원장 키 1 과 1.0

- **무엇** — 문자 칸(number · datetime 이 아닌 칸)에 숫자가 오면 한 철자로 저장됩니다(1.0 → `1`). 층과 보이는 칸이 같은 글자입니다. 원장 엔티티 키는 그 칼럼의 선언 타입으로 접혀, number 칸의 1 · 1.0 · 01 이 한 키가 됩니다.
- **선언 예시** — 없음. 문자 칸의 `1.0` 을 접고 싶으면 그 칸을 `table_config` 에서 `number` 로 선언합니다.
- **화면에서** — 이미 저장된 칸은 표마다 어드민 `Retroactive` 탭의 `Fold stored values into the declared spelling` → 표 고르기 → `Count` 로 먼저 세고 `Run`.
- **필요한 조건** — 서버 재기동. 원장의 옛 꼴 키는 소스마다 다시 번역할 때 빠집니다(server 폴더에서 `python ledger/backfill.py --source <소스> --whole-source --apply --pace slow`, `--apply` 없이 미리보기).
- **바뀐 동작** — 다이 x · y 가 1 과 1.0 으로 두 노드가 되던 것이 한 노드가 됩니다. 다시 번역하기 전에는 옛 꼴과 새 꼴이 걷기에서 둘로 보일 수 있습니다. 코드 맵퍼가 직접 만든 키는 이 접기를 지나지 않습니다.
- **자세히** — [BACKFILL_GUIDE](../guide/BACKFILL_GUIDE.md) · `RUN.md` · 커밋 7350027a6

## 2026-10-01 · 체인 규칙 이름 바꾸기 — 그 자리에서 이름만 바뀝니다

- **무엇** — 체인 규칙 이름을 고쳐 저장하면 그 규칙이 그 자리에서, 켜짐 · 꺼짐도 그대로 이름만 바뀝니다. 전엔 꺼진 사본이 새로 생기고 옛 규칙이 계속 돌았습니다.
- **선언 예시** — 없음.
- **화면에서** — 어드민 `Chain` 탭 → 규칙 고르기 → 이름 고치기 → `Save`. 저장 줄 밑에 서버의 문장이 붙습니다(그 규칙이 쓴 행이 다음에 올 때 새 이름으로 다시 쓰인다는 안내).
- **필요한 조건** — 서버 재기동.
- **바뀐 동작** — 새 이름이 다른 규칙의 것이면, 열어 둔 규칙이 파일에서 사라졌으면, 그 이름을 기록이 붙들고 있으면(맵 확정 · 처리 안 된 리플레이 · 다른 규칙의 `alignment_rule` · 끝나지 않은 소급) 저장이 이름 대어 거절되고 「Next: 이름을 그대로 두거나, 새 규칙을 더하고 이것을 끄십시오」 가 붙습니다.
- **자세히** — 커밋 4a0c69b2f · 666b3568d · 46bb3f26b

## 2026-10-01 · 표 선언 — 엑셀에서 칼럼 붙여넣기 · Copy columns

- **무엇** — 표 설정 화면에 엑셀 세 줄(1줄 칼럼 이름 · 2줄 타입 · 3줄 키 표시)을 붙여넣으면 `column_types` · `display_columns` · 키가 채워집니다. `Copy columns` 는 지금 칼럼을 같은 세 줄로 복사합니다. 타입 낱말은 `string` · `number` · `datetime` · `image` 넷입니다(대소문자 무관).
- **선언 예시** — 붙여넣는 시트(칸은 탭으로 나뉨). 3줄은 키 칼럼 밑에 `key` — 하나면 `business_key`, 여럿이면 `composite_key_source` 가 됩니다.

<!-- example: paste_sheet -->
```text
lot	slot	qty	photo
string	string	number	image
key	key
```

- **화면에서** — 어드민 `Tables` 탭 → 표를 고르거나 `+ Add table`(이름 적기) → 붙여넣기 칸에 Ctrl+V → 바뀌는 것(Dropped · Type · Key · Shown) 줄을 보고 `Save`(이미 있는 표는 저장 전에 그 줄로 묻습니다). `Copy columns` 로 지금 칼럼을 복사합니다. 표를 안 골랐으면 칸과 버튼이 꺼져 있고 「Pick a table or Add table」 이 보입니다.
- **필요한 조건** — 없음.
- **바뀐 동작** — 붙여넣은 표는 칼럼이 «통째로» 바뀝니다(없는 칼럼은 Dropped). 모르는 타입 낱말 · 빈 이름 · 겹친 이름은 이름 대어 거절됩니다.
- **자세히** — [config/table_config.md](../guide/config/table_config.md) · 커밋 4d07d3987 · 927b73a6e · 176244796 · cbbf03dd7 · b4f162ccd · 4ebb668df · e4fb38eec · 26c1b238d

## 2026-09-30 · 원장 선언창 — 저장 전 키 목록 · 경로 줄 · 물려받은 속성 · 꺼진 칸

- **무엇** — 원장 선언 폼이 네 가지를 보여 줍니다. 엔티티 바인딩을 고르면 «저장하지 않아도» 그 엔티티의 키 칸이 뜹니다. 지금 고치는 칸의 경로가 위에 한 줄로 고정되고, 깊이마다 안내선이 그어집니다. 역할이 소스에서 물려받는 속성이 그 역할의 속성 밑에 읽기 전용으로 보입니다. column ↔ constant 처럼 고르기를 바꿔 꺼진 칸은 저장이 빼고, 폼 머리에 그 칸을 적습니다. 누를 수 있는 것만 상자로 그려 설명 글자와 구분됩니다.
- **선언 예시** — 없음.
- **화면에서** — 어드민 `Ontology Explorer` 탭 → 원장 선언 고르기 → 폼에서 바인딩의 kind 를 고르면 키 칸이 뜹니다. 경로 줄의 단계를 누르면 그 칸으로 갑니다. 저장 전에는 `Dropped on save`, 저장 뒤에는 `Dropped` 가 뺀 칸의 경로를 적습니다.
- **필요한 조건** — 서버 재기동.
- **바뀐 동작** — 키 없는 엔티티 바인딩 저장이 500 대신 이름 댄 거절이 됩니다. 바인드 칸을 상수로 바꾼 뒤 저장해도 빈 칸 오류가 나지 않습니다. 행 단위(`unit: row`) 소스에는 `group_by` 칸이 없습니다.
- **자세히** — [ONTOLOGY_LEDGER_SETUP](../guide/ONTOLOGY_LEDGER_SETUP.md) · 커밋 92611320e · 052ac582c · 3cf207cd6 · f8c28ef94 · 06a7139f2 · a057073e7 · 37c714205 · b66f6eb2b · ee918c6b3 · 3f4efda82 · c83fe086a

## 2026-09-30 · 대조 저장 (Save contrast)

- **무엇** — R&D 보드에서 결함 웨이퍼와 비교군을 마킹한 «질문»을 저장하면, 체인이 그 걷기의 순위를 계산해 `contrast_factor` 에 쓰고, 저장한 행(`contrast_run`)에 계산했는지와 찾은 수를 적습니다.
- **선언 예시** — 표 둘(`contrast_run` · `contrast_factor`)과 규칙 하나가 샘플에 있습니다(샘플 규칙은 켜져 나갑니다). 규칙:

<!-- example: chain_rule -->
```json
{
  "name": "contrast_factor_from_run",
  "enabled": true,
  "is_batch": true,
  "on": {"table": "contrast_run"},
  "into": {"table": "contrast_factor"},
  "derive": {"kind": "mapper", "mapper": {"mapper_module": "mappers.contrast_walk", "mapper_function": "contrast_walk"}}
}
```

- **화면에서** — R&D 보드(`/rnd-board.html`) → 결함 웨이퍼를 마킹(마킹 1)하고 비교군을 고름 → `Save contrast` → 저장 목록에 「Not computed yet」, 계산되면 「factors N · computed HH:MM」(`Refresh` 로 다시 읽음).
- **필요한 조건** — 표 설정에 두 표, 체인 규칙에 위 규칙, 맵퍼 `server/mappers/contrast_walk.py`(저장소에 있음). 서버 · 체인 워커 재기동.
- **바뀐 동작** — 새 기능입니다.
- **자세히** — [config/chain_rules.md](../guide/config/chain_rules.md) · `RUN.md` · 커밋 cd069102e · 2005c0649 · e352d71a3 · 247c0aba6 · c35c28ba9

## 2026-09-30 · 시간 칸 — 체인이 옮긴 시간이 표에 다시 보이고, 같은 순간은 같은 값

- **무엇** — 조인이 datetime 칸을 가져올 때 쓰기 전체가 실패해 표에 NULL 로 보이던 것이 고쳐졌습니다. 같은 순간을 다른 철자(UTC · 지역 시각)로 다시 보내도 «바뀜»으로 치지 않습니다.
- **선언 예시** — 없음.
- **화면에서** — 없음.
- **필요한 조건** — 서버 · 체인 워커 재기동.
- **바뀐 동작** — 같은 순간을 다시 받으면 이력 줄 · 이벤트가 생기지 않습니다. 빈 값은 «없음»으로 견줍니다.
- **자세히** — `RUN.md` · 커밋 0ba95c23a · 29b14dc21

## 2026-09-30 · 스마트 붙여넣기 — 표가 정한 형식 순서 · 붙여넣기 상자 · Ctrl+Shift+V

- **무엇** — 표 설정에 `smart_paste` 순서를 적으면, 그리드 스마트 붙여넣기가 묻지 않고 그 순서에서 클립보드에 먼저 있는 형식을 보냅니다. 평문 http 처럼 클립보드를 읽을 수 없는 곳에서는 붙여넣기 상자가 떠서 그 안에 Ctrl+V 합니다. Ctrl+Shift+V 도 같은 길입니다.
- **선언 예시** — `config/table_config.json` 의 표에 `smart_paste`(클립보드 형식 이름, 적힌 그대로).

<!-- example: table -->
```json
{
  "paste_target": {
    "business_key": "lot",
    "column_types": {"lot": "string", "qty": "number"},
    "display_columns": ["lot", "qty"],
    "smart_paste": ["text/html", "text/plain"]
  }
}
```

- **화면에서** — 메인 그리드에서 오른쪽 클릭 메뉴의 `📋 Smart Paste` 나 `Ctrl+Shift+V` → 클립보드를 못 읽으면 「Paste here (Ctrl+V)」 상자가 뜨고 그 안에 Ctrl+V(취소는 Esc). 순서의 형식이 클립보드에 하나도 없으면 형식 고르기 창이 「Not in this table's smart_paste」 로 묻습니다. 순서가 고른 붙여넣기는 성공 알림에 「table order」 가 붙습니다.
- **필요한 조건** — 서버 재기동(`/schema` 가 `smart_paste` 를 실음).
- **바뀐 동작** — Ctrl+Shift+V 가 브라우저의 «서식 없이 붙여넣기»를 막고 스마트 붙여넣기로 갑니다. 예전의 「Smart paste armed · press Ctrl+V」 15 초 대기는 없어지고 상자로 바뀌었습니다.
- **자세히** — [config/table_config.md](../guide/config/table_config.md)(`smart_paste`) · 커밋 5c67b2473 · ce9318a51 · 4c46b3268 · f5de87625 · 2dcf6be37

## 2026-09-30 · nokey — 파일의 빈 키 칸을 제품이 채웁니다

- **무엇** — 표 설정의 `null_policy` 에 키 칼럼을 `"nokey"` 로 적으면, 파일에서 읽은 행의 그 칸이 비거나 칼럼이 아예 없을 때 `nokey_<처음 적재 시각>_<6자리>` 로 채웁니다. 같은 파일을 다시 넣어도(Retry) 같은 값입니다.
- **선언 예시** — `config/table_config.json`:

<!-- example: table -->
```json
{
  "void_inspection": {
    "composite_key_source": ["lot", "slot"],
    "column_types": {"lot": "string", "slot": "string", "void": "number"},
    "display_columns": ["lot", "slot", "void"],
    "null_policy": {"slot": "nokey"}
  }
}
```

- **화면에서** — 없음(파일 적재). 파일 줄에 「N row(s) keyed nokey_... (<칼럼>)」 이 남습니다.
- **필요한 조건** — 서버 · 워처 재기동. 파일에 내용 서명이 있어야 합니다(없으면 채우지 않고 그렇다고 적습니다).
- **바뀐 동작** — 그 칼럼이 없는 파일도 헤더에서 거절되지 않고 적재됩니다. 파일이 자라 내용 서명이 바뀌면 앞 행들의 키가 새로 매겨집니다.
- **자세히** — [config/table_config.md](../guide/config/table_config.md)(`null_policy`) · 커밋 a02701d3a · d28bccbdd · 95248fee8

## 2026-09-30 · HTML 토폴로지 파서 — 겹치는 헤더 경로는 이름 대어 거절합니다

- **무엇** — 값 칸 둘 이상이 같은 헤더 경로를 가지면, 전엔 앞 값이 조용히 사라졌습니다. 이제 그 표를 거절하고 경로 · 칸 수 · 좌표 하나 · 다음 할 일을 말합니다. 넓은 헤더는 자기가 덮는 칼럼의 값만 머리합니다.
- **선언 예시** — 없음(파서 코드의 `is_header_fn`).
- **화면에서** — 어드민 `File Ingestion` 로그의 상태 칸에 「Next: …」 가 먼저 보입니다.
- **필요한 조건** — 워처 재기동.
- **바뀐 동작** — 전엔 값 일부를 잃은 채 적재되던 표가 거절됩니다. 행을 가르는 칸을 `is_header_fn` 에서 헤더로 표시하면 들어갑니다.
- **자세히** — [HTML_TOPOLOGY_PARSER_GUIDE](../guide/HTML_TOPOLOGY_PARSER_GUIDE.md) · 커밋 499d89de4 · c4faced98

## 2026-09-30 · DT 뒤 공정 행은 dtwafer 에 — 스텝으로 재료 종류 나누기

- **무엇** — `step_phase` 표에 DT 스텝을 적으면, 조인이 그 스텝의 `wafer_process` 행에 `mat_type` 을 복사하고, 원장은 `mat_type` 이 DT 인 행을 dtwafer 에 대한 문장으로 읽습니다(비어 있으면 wafer).
- **선언 예시** — 표와 조인(둘 다 샘플에 있음, 원장 쪽 문장 둘도 샘플의 `wafer_process_recipe`).

<!-- example: table -->
```json
{
  "step_phase": {
    "business_key": "step",
    "composite_key_source": ["step"],
    "column_types": {"step": "string", "mat_type": "string"},
    "display_columns": ["step", "mat_type"]
  }
}
```

<!-- example: chain_rule -->
```json
{
  "name": "step_phase_to_wafer_process",
  "on": {"table": "step_phase"},
  "derive": {"kind": "join", "join": {"on": [{"left": "step", "right": "step"}], "take": ["mat_type"]}},
  "into": {"table": "wafer_process"},
  "key": {"unique": true}
}
```

- **화면에서** — 메인 그리드에서 `step_phase` 표에 행을 적습니다(step, mat_type = DT).
- **필요한 조건** — 샘플의 세 선언(표 · 조인 · 원장 문장)을 운영 설정에 넣습니다. 서버 · 체인 워커 재기동.
- **바뀐 동작** — 어떤 문장도 말하지 않은 행은 세어 로그에 이름을 댑니다. 텍스트 칸의 NULL 이 배치를 멈추지 않습니다. 스텝을 빼려면 행을 지우지 말고 `mat_type` 을 비웁니다.
- **자세히** — 커밋 c1746aa1e

## 2026-09-29 · 부류(class) — 엔티티 · 술어에 낱말을 달고, 걷기에서 부류로 따라가기

- **무엇** — 엔티티와 술어의 `class` 에 낱말 하나나 낱말 목록을 적습니다(예: 모델링 엣지 · 컨텍스트 엣지). 걷기의 `follow=class:<낱말>` 은 그 낱말을 단 술어 전부를 따라갑니다.
- **선언 예시** — `config/ledger_config.json` 의 `vocabulary`(술어)와 `entities`(엔티티).

<!-- example: ledger_vocabulary -->
```json
{
  "in_container@1": {
    "status": "active",
    "subjects": ["die@1"],
    "object": {"kind": "entity_ref", "types": ["wafer@1"], "qualifiers": {"required": [], "optional": []}},
    "class": ["modeling", "containment"]
  }
}
```

<!-- example: ledger_entities -->
```json
{
  "quantity@1": {"keys": ["quantity"], "class": ["static", "probe"]}
}
```

- **화면에서** — 어드민 `Ontology Explorer` 선언창의 술어 · 엔티티 `class` 칸(낱말 하나도 목록 한 칸으로 고칩니다). 걷기는 요청의 `follow` 에 `class:modeling`.
- **필요한 조건** — 서버 재기동.
- **바뀐 동작** — 엔티티 `class` 가 static · dynamic 한 낱말에서 «낱말 목록»으로 넓어졌습니다. 걷기가 읽는 낱말은 여전히 `static` 입니다. 선언에 없는 부류 낱말로 걸으면 422 `predicate_class_not_declared`.
- **자세히** — [WALK.md](../architecture/WALK.md) · 커밋 fdda4ebf6 · 45e363a05 · c9c27c450 · a5746efc1

## 2026-09-29 · 체인 규칙 저장 뒤의 반응 · 실패한 묶음 처리

- **무엇** — 체인 규칙을 저장하면 폼 머리가 「Saved · waiting for the chain worker」 에서, 워커가 그 파일을 읽으면 「Loaded by chain worker HH:MM:SS」 로 바뀝니다(워커가 안 보이면 「Saved · chain worker not seen」). 저장하면 체인 워커가 규칙만 다시 읽습니다. 거절된 새 규칙도 폼이 남고, 원장 선언이 저장됐지만 안 읽히면 「Saved but not applied」 와 사유가 붙습니다. 실패한 체인 묶음은 반으로 쪼개지 않고 «통째로» FAILED 가 되고, 실패 기록에 규칙 · 표 · 행 수 · 사유 원문 · 오류가 가리킨 행이 남습니다.
- **선언 예시** — 없음(시도 횟수는 전부터 있던 `max_group_attempts`, 기본 1 번).
- **화면에서** — 어드민 `Chain` 탭 → 규칙 고치고 `Save` → 폼 머리 줄. 실패한 사건은 Chain 탭의 실패 목록에서 열면 rule · table · rows · row · reason 이 기록 그대로 보입니다.
- **필요한 조건** — 서버 · 체인 워커 재기동.
- **바뀐 동작** — 실패 묶음이 한 행까지 쪼개지며 새 사건을 만들던 것이 없어졌습니다. 큐를 새로 읽을 때마다 규칙 파일을 다시 읽지 않습니다. 손으로 고친 파일은 `⚙️ Reload Configs & Code` 뒤에 읽힙니다.
- **자세히** — [config/chain_rules.md](../guide/config/chain_rules.md)(`max_group_attempts`) · `RUN.md` · 커밋 5fa5b1d83 · 4ee01686e · 29de5321c · 31ae7ce4b · 370684bd0 · 640421b64 · 790511099 · 7fc52efef · 3a8f35296 · 7f3bf293b

## 2026-09-29 · 폴더 아래 실패 파일을 한꺼번에 다시 넣기

- **무엇** — File Ingestion 에서 폴더 하나를 고르면, 그 아래(모든 깊이)의 실패 파일 수를 먼저 보고 그것만 다시 넣습니다. 외부 폴더의 파일은 그 폴더의 처리기로 다시 들어가 폴더의 웨이퍼 · 시각 · 옵션을 지킵니다.
- **선언 예시** — 없음.
- **화면에서** — 어드민 `File Ingestion` 탭 → `Retry failed files under a folder` → `Folder` 에 적거나 고르기 → `Preview` → 서버가 센 수가 붙은 `Retry`.
- **필요한 조건** — 서버 · 워처 재기동.
- **바뀐 동작** — 다시 넣기가 워처의 그 표 처리기로 갑니다(전엔 새 처리기라 외부 파일의 문맥을 잃었습니다).
- **자세히** — 커밋 207cb0bf1 · f90754d7d · 7e0a114dd · 5b20d9d1b

## 2026-09-29 · 오토 업데이트 백필 — 마지막 실행의 다음부터

- **무엇** — 수집기 백필의 시작 칸이 그 수집기의 마지막 실행이 끝난 다음 날로 열립니다. 다시 돌려도 처음부터 다시 돌지 않습니다.
- **선언 예시** — 없음.
- **화면에서** — 어드민 `Auto Update` 탭 → 수집기 줄의 `Backfill` 시작 칸(`YYYY-MM-DD`) → `Start`.
- **필요한 조건** — 서버 · 스케줄러 · 체인 워커 재기동.
- **바뀐 동작** — 칸을 건드리지 않고 `Start` 를 누르면 보이는 날짜가 그대로 갑니다(전엔 빈 시작이 가서 처음부터 돌았습니다).
- **자세히** — 커밋 efa60fd9c · 9eb859e47

## 2026-09-28 ~ 10-01 · 체인 규칙 · 조인의 동작

- **무엇** — 여섯 가지입니다. (1) `require` — 적은 칸이 «다 찬» 트리거 행만 규칙에 넘어갑니다(조인은 양쪽). (2) 선언은 자기가 쓴 것으로 다시 깨어나지 않습니다(파생 → 조인 → 파생에서 돌던 것). (3) `trigger_columns` 가 실제로 거르고, 조인은 키와 `take` 칸이 바뀌면 깹니다. (4) 조인 키가 «모두» 빈 행은 짝이 아닙니다(일부만 빈 것은 짝). (5) 조인 `blank: "skip"` — 짝이 된 원천의 빈 `take` 값은 쓰지 않습니다. (6) `allow_retraction` 으로 거둔 행도 지움 이벤트 · 이력을 남기고 원장 후속으로 갑니다.
- **선언 예시** — `config/chain_rules.json`. 통합 문법의 조인에 `on.require` 와 `blank`(옛 모양의 규칙은 맨 위에 `require`):

<!-- example: chain_rule -->
```json
{
  "name": "attribution_to_inventory_filled",
  "on": {"table": "dt_job_attribution", "require": ["dt_lot_confirmed"]},
  "derive": {"kind": "join", "join": {"on": [{"left": "dt_job", "right": "dt_job"}],
                                       "take": ["dt_lot_confirmed", "dt_slot_confirmed"], "blank": "skip"}},
  "into": {"table": "dt_inventory"},
  "key": {"unique": true}
}
```

<!-- example: chain_rule -->
```json
{
  "name": "lot_event_to_lot_slot_wafer_filled",
  "trigger_table": "lot_event",
  "target_table": "lot_slot_wafer",
  "mapper_module": "mappers.lot_slot_wafer_mapper",
  "mapper_function": "build_lot_slot_wafer_rows",
  "is_batch": true,
  "require": ["lot_id", "slotnumbers", "waferids"],
  "params": {"list_delimiter": ":", "slot_list_column": "slotnumbers", "wafer_list_column": "waferids",
             "lot_column": "lot_id", "time_column": "event_time", "event_type_column": "event_type",
             "target_lot_column": "lot", "target_slot_column": "slot", "target_wafer_column": "wafer",
             "target_time_column": "event_time", "target_event_type_column": "event_type"}
}
```

- **화면에서** — 어드민 `Chain` 탭의 폼에서 `on` 밑의 `require`, 조인의 `blank` 칸.
- **필요한 조건** — 서버 · 체인 워커 재기동. `blank: "skip"` 전에 이미 NULL 로 쓴 층은 남습니다(걷는 절차는 `RUN.md`).
- **바뀐 동작** — 위 (2) · (3) · (4) · (6). 로드 로그에 규칙마다 「wakes only on: [..]」 한 줄이 남습니다. 조인에 `on.columns` 를 적으면 키 + `take` 와 «집합으로» 같아야 합니다. `require` 에 트리거 표에 없는 이름을 적으면 그 규칙이 로드에서 거절됩니다. `require` 칸을 «조인(체인)»이 채우는 표라면 그 규칙에 `"allow_chain_trigger": true` 가 있어야 칸이 다 찬 뒤에 다시 깨어납니다 — 없으면 사람 · 파일 · 수집기가 바꾼 행에만 깨어나고, 「왜 안 도나」의 가장 흔한 답이 이것입니다(트리거 표와 대상 표가 같은 규칙에는 켜지 않습니다).
- **자세히** — [config/chain_rules.md](../guide/config/chain_rules.md) · [CHAIN_COPY_WHEN_FILLED_GUIDE](../guide/CHAIN_COPY_WHEN_FILLED_GUIDE.md) · `RUN.md` · 커밋 3aec8eaa9 · 29c590044 · 5ad90d16d · 66b5fcbe7 · 512b0575b · f36abbb1a · 880043afb · cb4d5157d

## 2026-09-28 · 맵 에디터 — 고른 칸만 고쳐 쓰기 (Save changed cells)

- **무엇** — 맵 에디터에서 고른 값 칼럼의 «바뀐 칸만» 그리드의 쓰기 문으로 저장합니다. 맵을 통째로 갈아끼우는 `Push` 는 그대로입니다.
- **선언 예시** — 없음.
- **화면에서** — 맵 에디터 → 값 칼럼 고르기 → 칠하기 · 지우기 → `Save changed cells` → 묻는 창에서 확인 → 결과 줄.
- **필요한 조건** — 없음.
- **바뀐 동작** — 불러온 뒤 다른 곳에서 값이 바뀐 칸은 건너뛰고 셉니다. 불러온 뒤 맵 키 · 값 칼럼 · 프레임이 바뀌었으면 저장을 거절합니다.
- **자세히** — 커밋 de356e889

## 2026-09-29 ~ 10-01 · 이번 주 고친 것 — 소유자가 신고한 화면

- 참조 보기 탭이 가끔 사라지던 것이 고쳐졌습니다(a937d209d · 3da6a2a09).
- Replay chain 드롭다운에서 글씨가 넘치던 것이 고쳐졌습니다(df7a22399 · 2538fe367).
- 체인 선언 폼의 상태 배지가 입력칸과 겹치던 것이 고쳐졌습니다(42b9465c6 · 66e86ca0d).
- Replay chain 줄이 겹치던 것과, 목록이 상자 안에서 스크롤되게 고쳐졌습니다(e99b496f5).
- 체인 규칙 폼에서 다음에 누른 칸의 초점이 사라지던 것이 고쳐졌습니다(4ecbc813e).
- 낱말 하나만 든 목록 칸을 고칠 수 없던 것이 고쳐졌습니다(c9c27c450 · a5746efc1).
- 선언창에서 새 가지에 아무것도 만들 수 없던 것이 고쳐졌습니다(77a5f264c).

---

## 2026-08 — Ledger V2 & Ontology Config Explorer

- **2026-08-18 | Ledger/Ontology** | **Ledger V2 1~7단계와 Ontology Config Explorer 전체 계약 승인 완료.** manifest 단일 진입점, config-only Registry, verified batch join, RoleFrame/Pack compiler, 기존 gate/store/cursor transaction, 비파괴 `lot_event` cutover를 확정했다. Explorer는 compiled 참조 그래프·Used by·단일 context history·draft preview/review/revise/CAS activation과 반응형 3단 UI를 제공한다. 운영 reset/replay·migration·legacy 삭제는 별도 승인 전 금지. [인수인계](./FORK_SESSION_BRIEF.md) · [Ledger V2](../_archive/ledger_v2_redesign_plan_20260817/README.md) · [Explorer 근거](../_archive/ontology_config_explorer_plan_20260817/02_IMPLEMENTATION_AND_ACCEPTANCE.md)

## 2026-07 — 웨이퍼 맵 에디터 & 물리 지오메트리

- **2026-07-26 | Map/Overlay** | **범용 맵 오버레이의 좌표 변환을 클라 단일 구현으로 일원화** — 소스 원본 좌표를 소스 자신의 `wafer_map_metadata` 프레임으로 해석해 물리 키로 투영하므로 화면 규격 변경을 오버레이가 따라온다(서버 엔드포인트는 존치, 클라는 보정 선언 관문으로만 사용). 실패 status 6종 명시화 · 테이블 전환 시 오버레이 해제. **도메인 규칙 확정: `wafer_map_metadata`가 정렬의 유일한 기준**(셀 레벨 `grid_metadata`는 폐기 스킴). [상세](../history/20260726_225311_overlay_geometry_unified_into_client.md)
- **2026-07-21 | Map/Ingestion** | 물리 웨이퍼 지오메트리 엔진 도입, 체인 인제션 페이로드 문자열 내성 강화.
- **2026-07-19~20 | Map Editor** | 2세대 격자 맵 에디터 완성 — 회전/면반전 좌표계, E1/E2 외곽 자동 추출, 드래그 페인팅, 엑셀 복사, 메타데이터 전용 테이블(`wafer_map_metadata`), 프리셋.
- **2026-07-17 | Admin** | 브라우저 내 Monaco 코드 에디터 시스템(맵퍼/스크립트 인라인 편집, no-cache 응답).
- **2026-07-15 | Ingestion** | Silent Upsert + 하이브리드 Auto-Update 스케줄러(주석기반 크론).

## 2026-06 — RDB 전환 & 관리자 대시보드

- **2026-06-20 | Data Model** | 복합 비즈니스 키 생성 및 고유성 보장.
- **2026-06-16 | Admin/Perf** | 전용 관리자 대시보드(ingestions/chains/mappers), 배치 업서트·클라이언트 성능 최적화.
- **2026-06-13 | Data Model** | JSONB blob → 정규화 RDB(동적 네이티브 테이블) 마이그레이션.
- **2026-06-09 | Ingestion** | 체인 인제션 Pandas 배치 맵퍼, 공용 맵퍼 유틸 베이스, 폴트 톨러런스·리플레이.

## 2026-05 — 웹 클라이언트 전환

- **2026-05-25 | Frontend** | `client2` AG-Grid 웹 클라이언트 재구축 및 프로덕션 통합. PySide6 데스크톱 → QtWebEngine 셸 + 웹앱 체제로 전환.

## 2026-04 이전 — 기반 플랫폼 (구 Phase 1~80)

- 실시간 WebSocket 동기화, 가상 로딩 그리드, 데이터 계보(AuditLog), 비즈니스 키 업서트, 검색 세션 가드, Float-to-top, 트랜잭션 그룹화 등. 상세: [PROJECT_RECAP(archived)](../_archive/PROJECT_RECAP.md) 및 [history/](../history/README.md).

---

## 앞으로 (백로그)

루트 `task/` 디렉토리의 대기 작업:
- `cursor_based_pagination_pending.md`
- `total_count_sync_pending.md`
- `desktop_hybrid_wrapper_plan.md`

> 새 릴리스는 이 파일 상단(해당 월 섹션)에 한 줄 추가하고 history 상세를 링크하십시오.
