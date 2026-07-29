# F3 — 고유값 조회 API (입력 제안의 전제 프리미티브)

> 2026-07-29 · Server · 기준 `46a67c7`

`(table, column, prefix) → 그 접두로 시작하는 고유값 목록 + 잘림 여부`. UI 전영역 입력 제안(드롭다운)이 올라설 프리미티브다. 이 건의 어려움은 API 모양이 아니라 **1,000만 행에서도 typeahead 속도가 나오는가**였고, 실측 결과 함정이 **둘** 있었다(하나만 고치면 나머지가 그대로 남는다).

---

## 함정 ① 비-C 콜레이션에서 btree는 `LIKE '접두%'`를 못 쓴다

### 현상
`bonding_map`(1,756,689행)에서 값 3개를 얻는 데 **232ms**. 인덱스는 있었다.

```
-- SELECT DISTINCT base ... WHERE base LIKE 'C%' ORDER BY base LIMIT 51
Index Only Scan using idx_bonding_map_base on bonding_map
  Index Cond: (base IS NOT NULL)
  Filter: (((base)::text <> ''::text) AND ((base)::text ~~ 'C%'::text))
  Rows Removed by Filter: 1755308
Execution Time: 232.715 ms
```

### 근본 원인
이 DB의 콜레이션은 `Korean_Korea.949`다(`SELECT datcollate FROM pg_database`). 접두 LIKE를 범위(`>= 'C' AND < 'D'`)로 바꾸는 최적화는 **바이트 순서 비교**를 전제하므로, 비-C 콜레이션 btree에는 매칭되지 않는다. 플래너는 인덱스를 **커버링 스캔으로만** 쓰고 접두 판정은 Filter로 내려버린다 — 즉 인덱스가 있는데도 전량 스캔이다.

같은 결함이 이미 `/graph/nodes/search`의 `identity_key ILIKE 'q%'`에 있었고(보드 미해결 항목), 이번이 **두 번째 소비자**였다.

### 해결
인덱스 자체를 바이트 순서로 만든다.

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_suggest_bonding_map_base
  ON bonding_map (lower("base") COLLATE "C", "base" COLLATE "C");
```

같은 데이터, 같은 접두:

```
Index Only Scan using idx_suggest_bonding_map_base
  Index Cond: ((lower((base)::text) >= 'c') AND (lower((base)::text) < 'd') AND ...)
Execution Time: 0.186 ms
```

술어는 `value_suggest.prefix_conditions` **하나**이고, `/graph/nodes/search`가 그것을 그대로 쓴다(`ILIKE` → 범위 비교). 대소문자 무시 의미론은 `lower()`를 양쪽에 적용해 그대로 보존했고, **LIKE가 사라졌으므로 `_escape_like_term`도 삭제**했다 — 범위 비교에서 `%`·`_`는 그냥 문자다.

---

## 함정 ② `DISTINCT`의 비용은 답의 개수가 아니라 "51개를 채울 때까지 걷는 행 수"다

### 현상
올바른 인덱스를 깔아도 `leg`의 빈 접두 조회가 **161ms**, `base LIKE 'C%'`가 **144ms**다. 반면 `base`의 빈 접두는 0.3ms다 — 같은 테이블 같은 인덱스인데 500배 차이가 난다.

```
Unique  (actual time=143.970..151.727 rows=51)
  ->  Parallel Index Only Scan using idx_suggest_bonding_map_leg
        (actual rows=358647.33 loops=3)      -- 51개를 채우려고 100만 엔트리 넘게 걷는다
```

### 근본 원인
`DISTINCT ... LIMIT 51`은 51개를 채우거나 **인덱스가 끝날 때까지** 걷는다. 비용을 정하는 것은 답의 개수가 아니라 **일치가 얼마나 성긴가**다. `base`는 빈 접두에서 distinct가 촘촘해 51개가 즉시 나오지만(0.3ms), 접두 `'C%'`로 좁히면 일치가 3개뿐이라 `c` 구간 전체를 훑고(144ms), `leg`는 distinct 342개가 175만 행에 퍼져 있어 51개를 채우는 데만 100만 엔트리를 지난다(161ms). 1000만 행이면 그대로 비례해 늘어난다.

즉 **드롭다운이 실제로 던지는 질의(좁은 접두 · 낮은 카디널리티)가 정확히 최악의 경우**다.

> ⚠️ 이 절의 숫자는 2026-07-29 검수에서 **한 번 틀렸다가 고쳐졌다.** 최초 기록은 `leg` distinct를 6, `base`를 11,058로 적었는데 실제는 **342 / 397,602**다. 바로 위 실행계획의 `Unique (actual rows=51)`이 그 서술을 이미 반증하고 있었다 — 고유값이 6개인 컬럼은 51행을 낼 수 없다. 논증(성긴 일치 = 전량 주사)은 정정 후에도 그대로 서지만, **첨부한 증거가 본문을 반박하는데 아무도 안 읽은 것**이 문제였다.

### 해결 — loose index scan (skip scan)
첫 값을 찾고, 이후 **"직전 값보다 큰 첫 값"** 을 반복 탐색한다. 값 1개당 인덱스 하강 1회이므로 비용이 테이블 크기·카디널리티와 무관해진다.

```python
# server/value_suggest.py _text_values
q = sa.select(sa.func.lower(col).label("lk"), col.label("v")).where(*base)
if cursor is not None:
    q = q.where(sa.tuple_(lk_expr, cv_expr) >
                sa.tuple_(sa.literal(cursor[0]), sa.literal(cursor[1])))
row = db.execute(q.order_by(lk_expr, cv_expr).limit(1)).first()
```

`(lower(col), col)` 2키 커서인 이유: 1키면 대소문자 변종(`ABC`/`abc`)이 하나로 접혀 "고유값"이 아니게 된다. PostgreSQL은 이 행 값 비교를 인덱스 조건으로 받는다 — `Index Cond: (ROW((lower(base)), base) > ROW('c002…', 'c002…'))`.

**실측** — `bonding_map` 1,756,794행, `suggest_values` 종단 51값, 7회 중앙값:

| 컬럼 | distinct | loose scan | `SELECT DISTINCT … LIMIT 51` |
|---|---|---|---|
| `leg` | 342 | **33ms** | 161ms |
| `base` | 397,602 | **32ms** | 0.3ms (빈 접두) · 144ms (`'C%'`) |
| `pkg_id` | 1,753,841 | **37ms** | 3,364ms |

숫자의 요점은 배율이 아니라 **평탄함**이다. 순진한 질의는 같은 테이블 안에서 0.3ms~3.4s로 네 자릿수를 널뛰는데, loose scan은 카디널리티와 무관하게 ~33ms에 머문다. 드롭다운은 후자 위에만 올릴 수 있다.

SQLAlchemy 표현식 하나로 sqlite에서도 같은 모양이 나온다(sqlite의 기본 BINARY 콜레이션이 이미 바이트 순서라 `COLLATE "C"` 장식만 PostgreSQL에서 붙인다) — **코드 경로가 하나**여서 스위트가 실제 알고리즘을 검증한다.

---

## 라이브에서만 드러난 결함 — `number` 컬럼이 답은 하는데 인덱스가 없었다

첫 라이브 검증에서 `bonding_map.x`(number 선언, `double precision`)가 이렇게 나왔다:

```
### bonding_map.x prefix='' -> 1663.0 ms, 0 values,
    unavailable = 조회 시간 초과 (1500ms) — 접두 인덱스 idx_suggest_bonding_map_x 가 없습니다.
                  server/scripts/setup_db_performance.py 를 실행하세요.
```

강등은 정확히 설계대로 동작했지만 **사유가 막다른 길**이었다 — 대상 선정에서 number를 뺐으므로 그 스크립트는 그 인덱스를 영원히 만들지 않는다. API는 답하는데 빌더는 모르는 비대칭이었다. `index_targets`가 number를 포함하도록 고치고(정의는 콜레이션이 개입하지 않는 일반 btree `(col)`), 회귀 테스트를 붙였다. 수정 후 **6.2ms**.

두 번째 결함은 **스크립트의 고아 인덱스 보고가 잡았다**: `CREATE INDEX ... idx_suggest_inventory_master_MAX`는 PostgreSQL이 식별자를 소문자로 접어 `..._max`로 만든다. 우리가 요청한 이름과 카탈로그에 있는 이름이 달라, 존재 확인과 고아 판정이 **자기가 지은 이름에 대해 거짓말**을 했다. `suggest_index_name`이 소문자로 접고, 접힘이 일어난 경우에만 해시 접미를 붙여 `MAX`/`max` 충돌을 막는다.

---

## 검수 라운드 — 스위트가 결함을 고정하고 있었다

QA가 NO-GO를 냈다. 다섯 건이 나왔고, 하나는 **운영 DB에서 값이 사라지는** 결함이었다.

### HIGH — 음수 접두가 가장 둥근 값들을 조용히 떨궜다

`numeric_prefix_ranges`가 양수 범위를 음수축에 미러링할 때 이렇게 했다:

```python
return sorted(((-hi, -lo) for lo, hi in ranges), key=lambda r: r[0])
```

half-open `[lo, hi)`를 음수축에 뒤집으면 `(-hi, -lo]`, 즉 **오른쪽이 닫힌** 구간이다. 그런데 소비자 `_numeric_values`는 모든 범위를 `col >= lo AND col < hi`로 적용한다. 그래서 `-lo`가 제외되는데, 그 `-lo`가 하필 `-d·10^k` — **가장 둥글고 가장 있을 법한 값**이다.

라이브 재현:

| 실제 데이터 | 요청 | 응답 |
|---|---|---|
| `bonding_map.y`에 `-9.0` 존재 | `prefix=-9` | `values: []`, `truncated: false`, `unavailable_reason: null` |
| `bonding_map.x`에 `-2.0` 존재 | `prefix=-2` | `values: []` |
| 같은 행 | `prefix=-` | `values: ["-9"]` ← 값이 도달 가능함을 증명 |

원래 주석은 이걸 *"끝점에서 작은 겹침 … 무해"*라고 적어놨는데, **겹침이 아니라 구멍**이었다. 그리고 이 모듈의 방어선인 "파이썬 재검사가 권위"는 여기서 작동할 수 없다 — **행이 애초에 SELECT되지 않기 때문이다.** 범위 산술이 상위집합이라는 전제가 깨지면 그 아래 모든 논증이 같이 무너진다.

수정은 미러링한 상한을 **1 ULP 넓히는 것**(`math.nextafter(-lo, math.inf)`). 범위는 상위집합이기만 하면 되므로 한 float 넓은 것은 프로브 1회를 쓸 뿐이고, 한 float 좁은 것은 값을 잃는다.

🔴 **그리고 스위트가 이 결함을 고정하고 있었다** — `test_value_suggest.py`에 `assert (-2.0, -1.0) in neg`가 있었다. 결함의 *모양 그대로*를 단언한 것이다. 엔드포인트에 음수 접두를 보내보는 테스트는 **하나도 없었다.** 그래서 1215건이 통과하는 동안 라이브에서는 값이 사라지고 있었다. 이번에 그 단언을 지우고, 음수를 심고 접두로 물어보는 종단 테스트를 넣었다.

같은 계열로 `_MAX_MAGNITUDE`(=15)의 닫힌 최상단 범위도 열었다 — 10^16 이상 저장값이 1자리 접두의 모든 범위 밖으로 빠지는, 형태가 똑같은 구멍이었다.

### MEDIUM — 나머지 넷

| 건 | 내용 | 수정 |
|---|---|---|
| 공유 술어가 지킬 수 없는 필터를 준다 | `prefix_upper_bound`가 마지막 문자에서 포기해 `None`을 반환 → `prefix_conditions`가 **하한만** 냄. 소비자 1은 파이썬 재검사가 받아주지만 **소비자 2(`/graph/nodes/search`)는 그게 곧 답**이다. 라이브에서 `q="L\U0010FFFF"`가 term 이상 전부를 반환했다(옛 ILIKE는 0행) | 상한 계산에 **자리올림** 도입. `None`은 이제 접두가 전부 U+10FFFF일 때만 나오고, 그 경우엔 하한만으로 정확하다 — docstring이 사실이 됐다 |
| PG `lower()`와 파이썬 `.lower()`가 다르다 | 인덱스 키는 PG의 `lower(col)`인데 범위는 파이썬으로 접었다. 이 DB에서 `lower(U+00C4·BC)`는 PG가 `U+00C4·bc`, 파이썬이 `U+00E4·bc` — 저장값이 `truncated: false`인 채 답에서 빠진다. **스위트는 sqlite에서 도는데 sqlite의 `lower()`도 ASCII 전용이라 이 축을 잡을 수 없었다** | `db_fold`로 **DB 자신의 `lower()`** 에 물어서 접는다(ASCII 접두는 왕복 없음 — A-Z→a-z는 모든 구현이 같다). 시크 루프의 재검사도 질의가 이미 돌려준 `lower(col)`로 바꿔 두 함수를 하나로 만들었다. 계약도 정직하게 서술: **"같다"의 범위는 DB가 접어주는 딱 그만큼** |
| 열화 안내가 막다른 길 | *"인덱스가 없으니 스크립트를 실행하세요"* — `index_exclude`·`index_columns`·`index_min_rows` 때문에 **빌더가 애초에 만들 생각이 없는** 컬럼이면 몇 번을 돌려도 안 만들어진다(라이브에 임계 미만 테이블 15개). number 컬럼 건에서 이미 고쳤다고 적은 것과 같은 계급 — 그 수정은 한 **사례**만 덮고 **규칙**은 안 덮었다 | `_diagnose`가 정책 소유자 `index_targets`에 **직접 물어서** 사유를 만든다. 대상이면 재실행을 지시하고, 아니면 어느 노브가 막는지와 무엇을 고칠지를 말한다 |
| 무효 인덱스를 건강하다고 보고 | `to_regclass`는 INVALID 인덱스도 해석한다. 취소된 `CONCURRENTLY` 빌드가 그 이름으로 잔존하면 플래너는 절대 안 쓰는데 진단은 *"존재합니다"*라고 하고, 빌더의 `IF NOT EXISTS`는 **이름이 있어 영원히 건너뛴다**. 가이드가 경고하는 워커 `idle in transaction` 상황이 정확히 그 도달 경로다 | 판정을 `indisvalid AND indisready`로. 사유가 `REINDEX`/`DROP` 복구 명령을 직접 제시하고, 빌더는 Step 3.8 **시작에** 무효 목록을 먼저 출력한다. 가이드의 확인 SQL도 유효성 열을 갖도록 교체 |

### 남긴 것 (의도적)

- **`truncated`가 예산 경계에서 과보고될 수 있다.** 프로브가 정확히 예산에서 끊기면 "더 있을지 모른다"고 말하는데 실제로는 완전할 수 있다. 더 있는지 확인하려면 프로브가 한 번 더 필요한데 그게 바로 예산이 금지한 것이다 — **구조적으로 불가피하고, 틀리는 방향이 안전한 쪽**(과소 보고는 INV-F3-1 위반, 과보고는 아니다).
- **선행 공백 값은 도달 불가.** 인덱스가 원본 컬럼의 `lower()`이므로 `"  ABC"`는 `"  abc"`로 색인되어 접두 `a` 범위 밖이다. 인덱스 정의를 바꿔야 하는 문제라 이번 범위 밖.
- **인덱스 이름 충돌**(`a_b`+`c` vs `a`+`b_c` → 같은 이름). 명명 규칙을 바꾸면 **라이브 34개 인덱스가 전부 고아가 되므로** 총괄 판단 사항으로 남긴다.

## INV 요약

| INV | 규율 |
|---|---|
| F3-1 잘림 고지 | `limit + 1`번째 값을 실제로 한 번 더 찾아 확인. 프로브 예산으로 멈춘 것도 잘림 |
| F3-2 빈 접두 | loose scan이라 O(limit)이므로 안전 — 하드 캡 + `truncated`. `min_prefix_length`는 성능이 아니라 **정책** 노브 |
| F3-3 선언 대조 | `crud.TABLE_CONFIG.column_types`가 권위. 물리적으로 존재해도 미선언이면 400(`business_key_val` 등). 호출자 문자열이 SQL 텍스트에 닿는 경로 없음 |
| F3-4 7b 정합 | `map_overlay.canonical_key_value` 재사용 — 반환값도 접두도 같은 함수로 정규화(`01` → `1`). 두 번째 정규화 없음. datetime은 400으로 거절(날짜 정규화를 새로 만들지 않기 위해) |
| F3-5 빈 값 제외 | canonical이 비었는지로 판정(SQL `col <> ''`는 공백 문자열을 못 본다 — 그쪽은 좁히기용) |
| F3-6 열화 | 예외·시간 초과는 `values: []` + 사유. **시간 초과는 잘림이 아니다** — 인덱스가 없으면 몇 개만 건지고 끝나는데 그게 "짧지만 완전한 픽 리스트"로 읽힌다 |

---

## 검증

- **스위트 1228 passed / 0 failed / 0 skipped** (기준선 1180 + 최초 35 + 검수 13).
- **검수 라운드 역주입 8종 전부 재증명** — 음수 미러 원복 / 최상단 범위 닫기 / 상한 자리올림 제거(순수함수·그래프 라우트 각각) / `db_fold` 파이썬 접기 / 재검사 파이썬 접기 / 사유 상수화 / `to_regclass` 원복 / 강제 컬럼 경고 제거. 그중 하나는 **처음에 헛돌았다** — 진단 분기 테스트가 sqlite에서 `pg_class` 조회 실패 → 폴백 문자열로 빠지는데 그 폴백이 세 노브 이름을 전부 담고 있어 통과했다. 행 수 조회를 분리하고 폴백 판별 단언을 넣어 축을 켰다.
- **최초 라운드 역주입 16종.** 1차 시도에서 **2종이 "주입했는데 통과"** 했다 — ⓐ SQL `col <> ''` 제거는 파이썬 canonical 가드가 받아내 차이가 0이었고(권위 있는 가드를 겨누도록 재조준), ⓑ LIKE 주입은 살아남은 상한 조건이 결과를 대신 걸러 축이 꺼져 있었다(전체 술어를 교체하고, 파이썬 재검사가 없는 `/graph/nodes/search`를 겨누도록 이동). 부분 주입은 축을 켜지 못한다.
- **라이브 PostgreSQL 18(13GB) EXPLAIN ANALYZE로 인덱스 실사용 확인** — 선언이 아니라 실행 계획으로. 텍스트·숫자·그래프 세 경로 모두 `Index Cond`에 접두 범위가 들어간다. 검수 후 재확인: 넓힌 음수 상한도 인덱스 조건으로 들어간다 — `Index Cond: (y >= '-10' AND y < '-8.999999999999998')`, 0.011ms.
- **라이브 결함 3건 사후 재현으로 해소 확인**(읽기 전용): `prefix=-9` → `['-9']`, `prefix=-2` → `['-2']`, `q="L\U0010FFFF"` → 0행(`LOT`·`lot`은 그대로 동작).
- `setup_db_performance.py` 실 적용: 34개 인덱스, 합계 **418MB**(13GB DB의 ~3%). `bonding_map.pkg_id` 189MB가 최대.

## 수정 파일

| 파일 | 내용 |
|---|---|
| `server/value_suggest.py` | **신규** — 조회 코어(loose index scan), 공용 접두 술어, config 로드·검증, 인덱스 이름·정의·대상 선정. 검수 후: `_mirror_negative`(HIGH), `prefix_upper_bound` 자리올림, `db_fold`, `_why_not_a_target`/`_approx_row_count`, `_index_state` |
| `server/main.py` | `GET /tables/{t}/columns/{c}/values` 신설(라우트 순서상 `/tables/{t}/{row_id}` **위**), `/graph/nodes/search` 술어 교체(+`db_fold` 경유), `_escape_like_term` 삭제 |
| `server/scripts/setup_db_performance.py` | Step 3.8 — 제안 인덱스 생성 + 고아 보고 + **무효 인덱스 선행 보고** |
| `server/config/suggest_config.json.sample` | **신규** |
| `server/tests/test_value_suggest.py` | **신규** 46건(최초 34 + 검수 12, 결함을 고정하던 단언 `(-2.0, -1.0) in neg` 제거) |
| `server/tests/test_graph_viewer_api.py` | 대소문자 무시 회귀 1건 + 상한 자리올림 회귀 1건 |
| `docs/architecture/backend.md` §2.1 · `docs/guide/POSTGRES_OPERATIONS_GUIDE.md` §3.1 · `docs/guide/config/suggest_config.md` | 실측 수치 정정(342 / 397,602 / 418MB / ~33ms 단일화), 대소문자 계약 정직화, 무효 인덱스 확인 SQL, 사유 문자열 표 |
