# 부재는 층을 만들지 않는다 — 고의로 비운 것만 NULL 층이다. 그리고 그 대가는 «어제 값이 남는다»

> **커밋:** `fac454af` — fix(layering): absence makes no layer; only a deliberate blank does (S-243, 판정 405)
> **일자:** 2026-09-15 16:25
> **레인:** 구현자(서버) — 판정 405 `977f11b9`(16:07) → 착지 → 보고 `c4168c82` → 총괄 닫힘 `a1f83129`(「S-243 닫힘 · 재기동 PID 47204 · 판정 396~405 전부 닫힘」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **11** · 기존 **1 변경**(부수 피해가 아니라 «판정의 결과») · 변이 **7 «전부» 빨강**(가드 제거 = 7 빨강) · 쓰기 경로·cell_sources·drop_report 모집단 **1,362 passed** · `--collect-only` **6,727** 에러 0 (구현자 보고). 총괄 확인 「쓰기 경로 모집단 1,177 passed · 부팅 오류 0 · 체인 17」.

## ① 왜 — 두 사실을 «아무 데서도» 가르지 않았다

소유자 케이스(11:1x): 「log→inventory 로 dt_wafer 가 들어가고, 역으로 inventory.dt_wafer 는 log 의 조인 대상」. 총괄이 코드로 잰 구조:
```
표시값 해석   crud `min(sources, key=_rank)` — 최상위 층을 «값이 NULL 이어도» 그대로 답한다(null 건너뛰기 없음)
빈 칸        `cast_value_by_type` 이 NULL 로 접어 «층으로 저장»한다 — 사람이 손으로 지운 것과 «똑같이»
서열         pipeline_parser 2 · chain_ingestion 4  ->  파일의 NULL 층이 조인의 값 층을 «영원히» 가린다
가상 조인     COALESCE(자기 값, 조인 값) = «null 을 건너뛰어 채운다»
=> 같은 「빈 칸」에 두 경로가 «다른 뜻»을 주고 있었고, 한쪽만 그것을 소리 내어 말했다
```
⛔ 조인은 계속 돌고 계속 맞는데 화면에는 «안 보인다». 오류가 없어서 위험한 부류다.

**판정 405(소유자 16:0x):** 「빈 층 고의 입력은 진짜 빈 것, 그냥 없던 것은 아직 입력하지 않은 것」. 총괄 번역: 부재는 층을 안 만든다 · 사람의 빈 칸 = NULL 층 · 체인의 matched-null = NULL 층(판정 f3c04dee). 종전 물음 「빈 층은 «답 없음»인가 «답이 null»인가」가 이 한 줄로 갈렸다.

## ② 변경 — 움직인 경계는 «쓰기 하나», 술어는 «이미 있는 하나»

```python
# server/database/crud.py  apply_row_update_internal — 모든 쓰기가 지나는 자리
clean_val = cast_value_by_type(val, col_type, col_name, table_name)

# 🔴 [S-243, 판정 405] ABSENCE MAKES NO LAYER; ONLY A DELIBERATE BLANK DOES.
# ⛔ THE WRITER IS SELECTED POSITIVELY ... file parsers write under the INGESTED FILENAME,
#    so the set of automatic source names is open-ended and cannot be blacklisted.
# ⚠️ AND THE EXISTING LAYER IS LEFT ALONE, not deleted.
if (is_blank_value(clean_val)
        and update_item.source_name not in (USER_SOURCE, CHAIN_SOURCE)):
    if drop_stats is not None:
        _record_dropped_cell(drop_stats, row.row_id, update_item.business_key_val,
                             col_name, DROP_ABSENT_NOT_WRITTEN)
    continue
```
```python
DROP_ABSENT_NOT_WRITTEN = "absent_not_written"   # 실패가 아니라 «셈». 이름이 없으면 「컬럼이 빈 파일」과 「컬럼을 안 부른 파일」이 같아 보인다
CHAIN_SOURCE = "chain_ingestion"                 # 이 라운드가 「누가 빈 칸을 썼나」를 «물어야» 해서 이름을 줬다 — 둘째 리터럴은 둘째 답이다
SOURCE_PRIORITY = { "user": 0, ..., CHAIN_SOURCE: 4 }
```
```
술어         is_blank_value — 키 자리들이 접는 «그 하나»(S-181). ""·"   "·None 이 같은 부재
쓴 이 «긍정 선택»  USER_SOURCE 상수 위 주석이 이미 이유를 적어 두고 있었다: 파일 파서는 «적재된 파일명»으로 쓴다(라이브 DB 10,750 가지) -> 블랙리스트 불가
읽기 «무접촉»  compute_priority_value 는 최상위 층이 NULL 이어도 그대로 답한다 — 고의로 비운 것이 «이겨야» 하므로 판정을 읽는 쪽에 옮기면 그것이 깨진다
```

## ③ 판정의 대가 — 그대로 적는다

**파일이 어제 값을 주고 오늘 빈 칸을 주면 «어제 값이 남는다».** 「아직 입력하지 않은 것」이 정확히 그 뜻이고, 「전에 말한 것을 철회한다」가 아니다. 지우는 것은 사람 · 철회(R2 `withdraw_source`) · `replace_map` 의 일이다. 그 문장이 작성 가이드(`docs/guide/config/table_config.md`)의 `source_priority` 옆에 한 줄로 들어갔다.

## ④ 픽스처 둘이 가설을 못 담아 변이 둘이 «빠져나갔다» — 그리고 기존 시험 하나

```
0 케이스        문자열 "0" 을 썼는데 truthy 라, is_blank_value 를 `not value` 로 바꿔도 «그냥 통과»
               -> number 컬럼(stock_qty)의 «진짜 0» 으로. 0 과 False 는 «답»이다
「층 안 건드림」  변이가 «메모리 리스트»에서만 빼서 아무것도 안 바꿨다(무해 변이)
               -> 저장된 행을 «지우는» 변이로 날을 세웠다
```
📌 부류: 「던진 변이는 잡힐 게 아니다」의 이웃 — «아무것도 안 바꾸는 변이»도 잡힐 게 없다.

`test_mapping_gap_is_detected_and_is_not_vacuous` 는 「이 검사가 진짜다」를 증명하려고 소스 행을 빈 값으로 «다시 심었다» — `pipeline_parser` 로. 405 아래서 그 주입은 «아무것도 주입하지 않는다»(값이 올바르게 남으므로). 주장은 그대로 두고 빈 값을 «사람(`user`)으로» 쓴다 — 칸을 고의로 비우는 것이 사람의 행위다.

## ⑤ 아키텍처 영향

- 「빈 칸」의 뜻이 쓰기 문 «한 자리»에서 정해진다: 뜻할 수 있는 둘(사람 · 체인)만 층, 나머지는 «셈». 가상 조인의 COALESCE 와 «같은 방향»이 됐다.
- `drop_report` 어휘가 하나 늘었다(`absent_not_written`) — 넷 다 «따로 이름»을 가진 이유가 같다.
- 체인 소스 이름이 crud 에 상수로 섰다. 커밋 자기 주석: **같은 문자열이 다른 모듈 «여섯»에 아직 리터럴로 있다 — 이 라운드는 손대지 않았다.**

## ⑥ 그때 남아 있던 것

- **이미 저장된 파일 소스의 NULL 층은 «여전히 가린다».** 이 변경은 «지금부터 써지는 것»을 바꾸지 이미 있는 것을 바꾸지 않는다. 세기(S-243-b, 읽기 전용)는 «별 줄»로 뒀고 이 시점에 미착지.
- 구현자의 앞선 물음 하나가 열려 있었다 — **PG 실행 시험**(S-240·S-245 의 `::text` 인덱스가 진짜로 서는지). 총괄 마지막 줄은 「미답 없음」이었고, 구현자가 이 보고에서 다시 올렸다(「급하지 않음」).
- 총괄 재기동 PID 47204 가 확인한 것은 「부팅 오류 0 · 체인 17」이다. 소유자 케이스(dt_log.dt_wafer)가 화면에서 «보이게 된 것»을 본 기록은 이 시점에 없다.
- 이 채널의 미답 «둘»(① PG 실행 시험 ② S-243-b 를 지금 지을지).

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「라이브 DB 10,750 가지」는 `USER_SOURCE` 주석의 앞선 실측 인용이다.
📎 소급 세기(S-243-b)의 착지: `20260915_163917_the_orders_predicate_would_have_counted_zero_on_a_database_full_of_the_rows.md` · `is_blank_value` 가 「한 술어」가 된 자리: `20260915_151725_the_fold_was_half_the_key_and_the_other_half_had_four_authors.md` · 조인 쓰기가 체인 층을 나르는 자리(판정 f3c04dee 근방): `20260915_113722_the_joins_writes_carry_the_chains_layer_so_they_cannot_wake_the_enrich_that_feeds_them.md`.
