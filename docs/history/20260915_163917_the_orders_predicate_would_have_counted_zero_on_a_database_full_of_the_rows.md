# 지시의 술어대로 지었으면 찾는 행이 가득한 DB 에서 «영원히 0» 이었다 — 빈 값은 SQL NULL 이 아니라 JSON 리터럴 `null` 로 저장된다

> **커밋:** `478fcf32` — feat(scripts): count the stored NULL layers that still hide, before anyone erases (S-243-b, 읽기 전용)
> **일자:** 2026-09-15 16:39
> **레인:** 구현자(서버) — 지시 `d4c14d63` → 착지 → 보고 `9d3d1f8b` → 총괄 닫힘 `f426c977`(「재기동 불필요 · 구현자 정지(큐 소진)」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **10** · 변이 **8 «전부» 빨강** · 레이어링·세기·거절 줄·API 모집단 **134 passed** · `--collect-only` **6,740** 에러 0 (구현자 보고). 총괄 확인 「21 passed」 + 이 박스에서 «돌려 봄».

## ① 왜 — 판정 405 는 «앞으로의 쓰기»만 고쳤다

`fac454af`(14분 전)로 파일의 빈 칸은 이제 층을 안 세운다. 그런데 어제까지 세워진 층은 `cell_sources` 에 그대로 있고, 파일 소스가 체인을 앞서므로(2 또는 99 대 4) 조인 값을 «오늘도» 가린다. 지우는 것은 데이터 변경이라 소유자 go 뒤이고, go 를 받으려면 «수»가 먼저다 — 이 저장소가 소급 걸음마다 취해 온 자세(「세기 먼저」).

## ② 지시의 술어가 틀렸고, 지어서가 아니라 «재서» 알았다

지시(`d4c14d63`): 「`cell_sources` 에서 source_name ∈ 파일 소스 ∧ **`value IS NULL`** 인 행 수를 세라」.
```
cell_sources.value   JSON 컬럼
진짜 쓰기 문(apply_batch_updates)으로 빈 값을 써 봄, 2026-09-15:
   user · chain_ingestion · 파일   «셋 다» 문자 네 개 `null` 로 저장  ->  `value IS NULL` 은 «전부 거짓»
   ""  도 `null` 로 도착(저장이 정규형 — normalize_stored_text)  ->  셋째 케이스 불필요
```
🔴 그 철자로 지었으면 찾는 행이 가득한 DB 에서 「없음」이라 답했고, **그 거짓 0 은 「치울 것이 없다」로 읽힌다** — 가장 비싼 오답이다. 그리고 게이트 픽스처가 진짜 쓰기 문을 «안 지났으면» 이 시험은 초록이었을 것이다.

```python
# server/scripts/count_absent_null_layers.py  count()
rows = db.execute(text("""
    SELECT s.table_name, s.column_name, s.source_name,
           COUNT(*) AS layers,
           SUM(CASE WHEN EXISTS (
                 SELECT 1 FROM cell_sources o
                  WHERE o.table_name = s.table_name AND o.row_id = s.row_id
                    AND o.column_name = s.column_name AND o.source_name <> s.source_name
                    AND o.value IS NOT NULL AND CAST(o.value AS TEXT) <> 'null'
               ) THEN 1 ELSE 0 END) AS hiding
      FROM cell_sources s
     WHERE s.value IS NULL OR CAST(s.value AS TEXT) = 'null'     -- JSON 리터럴을 묻고 SQL NULL 도 «같이» 받는다
     GROUP BY s.table_name, s.column_name, s.source_name
""")).fetchall()
for table_name, column_name, source_name, layers, hiding in rows:
    if crud.can_mean_emptied(source_name):      # 🔴 술어는 «import». 사람·체인의 NULL 층은 «답»이라 잔해가 아니다
        continue
```

## ③ 두 수를 «따로» — 그리고 술어에 이름을

```
NULL 층의 수      layers
그중 가리는 수     hiding — 같은 (표, 행, 컬럼)에 «값이 있는 다른 층»이 하나라도 있는 것
                  아래 층이 없는 NULL 층은 지워도 «한 픽셀도» 안 바뀐다. 합치면 운영자가 수천을 보고 아무것도 아닌 일에 착수한다
서열은 안 따진다   이 수는 「지울 후보가 몇이냐」이지 「지금 무엇이 보이냐」가 아니다 — 후자는 지우기 전 «내보낼 목록»이 답한다
```
```python
# server/database/crud.py — S-243 의 쓰기 자리에서 «추출». 읽는 쪽이 둘이 됐기 때문에 함수다
def can_mean_emptied(source_name: str) -> bool:
    return source_name in (USER_SOURCE, CHAIN_SOURCE)

if is_blank_value(clean_val) and not can_mean_emptied(update_item.source_name):   # 쓰기 자리도 «같은 함수»를 지난다
```
쓰는 쪽과 세는 쪽이 「누가 칸을 비울 수 있나」에 다르게 답하면 세는 수가 «다른 것의 수»가 되고, 보고를 읽는 사람은 그것을 알 수 없다.

⛔ `--apply` 는 «정책이 아니라 부재로» 없다 — 있는 플래그는 쳐진다. 지우기는 S-243-c(먼저 내보내기, 되돌릴 수 있게).

## ④ 구현자 시험 «둘»이 재기 전에 고쳐졌다

```
하나   count 의 «소스 텍스트»를 grep 해 술어를 찾다가 자기 «설명 주석»에 빨개졌다 — 빨강을 푸는 제일 쉬운 길이 «설명 지우기»인 시험
       -> `__code__.co_names` 를 묻는다
둘     손으로 정렬한 목록에 정렬을 단언했다 — 픽스처를 잰 것
       -> count 자신을 잰다
```
📌 부류: 「드리프트 오라클이 «금지를 설명하는 주석»을 읽는다」(2026-09-13) — 같은 날 다시.

## ⑤ RUN.md §1-bis — 명령 하나 + 「답의 뜻」 셋

| 답 | 뜻 | 조치 |
|---|---|---|
| 「NULL 층: 없음」 | 이 설치엔 쌓인 것이 없다 | 없음 |
| 가림 **0** | NULL 층은 있지만 밑에 값이 없다 | 없음 — 지워도 화면이 안 바뀐다 |
| 가림 **0 아님** | 그 수만큼 조인 값이 안 보이고 있다 | 그 수를 총괄에게. 지우기는 별 지시(S-243-c) |

🔴 「없음」은 «조인이 잘 보인다»가 «아니다» — 이 수는 «파일이 세운 빈 층» 하나만 센다.

## ⑥ 총괄이 이 박스에서 돌린 것

「이 박스에서는」 가림 **310**. 총괄이 보드에 «박스 수, 운영 주장 아님»이라 못 박았다. 소유자가 할 것: 운영에서 그 명령 → 「가림 N」을 질문지로. N>0 이면 S-243-c 를 go 로.

## ⑦ 아키텍처 영향

- 「누가 칸을 비울 수 있나」가 crud 의 «함수 하나»다. 쓰기 문과 세기 스크립트가 같은 것을 지난다.
- 소급 걸음의 자세가 또 한 번 같은 모양이다: 세기(읽기) → 수 → 소유자 go → 내보내기 → 지우기.

## ⑧ 그때 남아 있던 것

- **운영의 수는 없다.** 이 항목이 아는 수는 이 박스의 310 뿐이고, 그것은 운영에 대해 아무 말도 하지 않는다.
- S-243-c(지우기)는 «지시 없음» — 소유자 go 뒤의 일이다.
- 「지금 무엇이 보이나」(서열까지 따진 수)는 이 스크립트가 «안 센다» — 내보내기의 몫이고 그 내보내기는 아직 없다.
- 구현자의 앞선 물음(PG 실행 시험)은 그대로 열려 있었고, 큐는 «소진» — 구현자 정지.

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 소유자가 «돌려야 할 명령»뿐이다.
📎 쓰기 쪽(판정 405): `20260915_162502_absence_makes_no_layer_only_a_deliberate_blank_does.md` · 「빈 DB 는 모든 질문에 없다로 답한다」(2026-08-18) 의 SQL-술어 판이 이 항목의 ②다.
