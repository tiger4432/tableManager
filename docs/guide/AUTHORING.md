# 맵퍼·파서 «작성» — 이 저장소 밖입니다

> **Status:** 🟢 Living | **Last-verified:** 2026-09-13 | **Owner:** Lead PM |
> **Source-of-truth:** `server/mapper_sdk.py` · `server/parsers/pipeline_base.py`

```
맵퍼·파서를 «쓰려면» `assyManager-authoring/` 을 연다.
저장소는 «SDK 진입점의 이름»만 약속한다.
```

## 어디에 있나

```
C:/Users/kk980/Developments/assyManager-authoring/      이 저장소의 «형제» 디렉토리, 별도 git
```
⚠️ 서브모듈이 아닙니다. 이 저장소는 그쪽을 «참조하지 않고», 그쪽도 이쪽 코드를 «담지 않습니다».

## 무엇이 있나

| 파일 | 무엇 | 이 저장소의 정본 |
|---|---|---|
| `README.md` | 누구를 위한 것인가 · **SDK 버전 = 이 저장소의 커밋 해시** | — |
| `MAPPING_GUIDE.md` | 체인 맵퍼 — `(df, db) -> df` 하나 + `@mapper` 등록 | [`server/mapper_sdk.py`](../../server/mapper_sdk.py) |
| `PARSER_GUIDE.md` | 인제션 파서 — 함수형·클래스형 두 길 | [`server/parsers/pipeline_base.py`](../../server/parsers/pipeline_base.py) (`custom_parser_template.py` 는 `examples/` 로 «옮겨졌습니다» — 아래) |
| `examples/` | 맵퍼 샘플 셋(`dt_standard_map_mapper` · `lot_slot_wafer_mapper` · `production_mapper`) + `custom_parser_template.py` + `custom_parser.py.sample` — 판정 348·349 의 «다섯», 저장소에서 «이동»(사본 0) | — |

## 정본 관계 — 한 줄

**코드가 이깁니다.** 바깥 가이드는 이 저장소의 파일을 «인용»하고, 인용한 줄 번호에 인용한 것이
없으면 그 문장이 낡은 것입니다. 그래서 그쪽 `README.md` 가 **「SDK 버전 = 저장소 커밋 해시」**
한 줄을 들고, 모든 인용이 «그 커밋에서» 잰 것입니다.

## 이 저장소가 약속하는 것 — 진입점의 «이름» 셋

```
@mapper            server/mapper_sdk.py :339      체인 맵퍼 등록 (이름 -> MAPPER_REGISTRY :253)
parse_file         assyManager-authoring/examples/custom_parser_template.py   함수형 파서의 계약 전부
                   🔴 이 이름은 «저장소 코드에 없습니다»(추적 전건 0) — 아래 「⚠️」 참조
match · process_dataframe   server/parsers/pipeline_base.py :15 · :22   클래스형 파서의 훅 둘
```
그 이름이 바뀌면 제품이 «거절로» 말합니다. 그 밖의 것(파일 배치·헬퍼·예제 경로)은 약속이 아닙니다.

⚠️ **`parse_file` 은 위 셋 중 «코드가 부르는 자리»가 없습니다**(S-209 실측, 2026-09-13):
추적 파일 전건에서 그 낱말이 이 문서와 `SERVER_FILE_MAP.md` «둘»뿐이고, 워크스페이스 스크립트를
집는 자리(`server/parsers/directory_watcher.py` :1157)는 `BasePipelineParser` 의 «하위 클래스»만
찾습니다. 즉 함수형 길의 계약은 옮겨 간 템플릿의 «머리 주석»에만 살아 있었습니다.
`server/tests/test_the_authoring_guides_name_entry_points_that_exist.py` 가 이 상태를 잽니다 —
판정 대상이지 이 문서가 정할 것이 아닙니다.

## 왜 밖인가

작성자의 파일은 **이 저장소와 함께 배포되지 않습니다** — `server/mappers/*` 와
`server/ingestion_workspace/*/scripts/` 는 `.gitignore` 대상이고, `server/mapper_sdk.py` :12~17 이
SDK 가 «맵퍼 옆»이 아니라 «배포되는 자리»에 사는 이유로 바로 그것을 적습니다.
🔴 즉 **작성자 문서는 작성자의 상자에서 열려야 하고, 그것이 이 디렉토리가 형제인 이유**입니다.

## 옮겨 가지 «않은» 것

| 남는 것 | 왜 |
|---|---|
| [`guide/HTML_TOPOLOGY_PARSER_GUIDE.md`](./HTML_TOPOLOGY_PARSER_GUIDE.md) | 제품 모듈(`server/parsers/html_topology_parser.py`)의 사용 설명서 — 파서의 «길»이 아니라 «도구»다. ⚠️ 머리글 `Last-verified: 2026-07-24` 이고 `419cd8fa`(2026-08-04)가 넣은 «거절 경로»가 한 글자도 없다(실측: 그 문서에서 `REFUSED` 0건, 소스 `:654`) |
| `server/mappers/*.sample` 중 «일곱» | 시험이 바이트 동일로 읽는 «라이브 맵퍼의 추적 사본»이다(판정 348). 옮기면 드리프트 게이트가 비교할 대상을 잃는다 |
| [`guide/chain_ingestion_guide.md`](./chain_ingestion_guide.md) · [`guide/INGESTION_GUIDE.md`](./INGESTION_GUIDE.md) | 제품이 «어떻게 도나»를 적는 문서다. 작성자 문서는 「무엇을 적으면 받아 주나」만 적는다 |
