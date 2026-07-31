# 유니크 인덱스가 프로브보다 잘 말한다 — 62분 만에 지운 방어

> **일자:** 2026-07-31 아침 | **관련 커밋:** `4e06eec`(07:18, 프로브를 세운다) · `b6942ec`(08:20, 그 대부분을 지운다) — **한 라운드다.** 두 커밋 사이는 **62분**이다.
> **담당:** 사용자(판정 두 문장 — 아래 인용) · 구현자는 커밋에 기록이 없다
> **대상:** `server/virtual_join_config.py`(신설 → 축소) · `server/config_resolve_report.py` · `server/main.py`(라우트 1개 신설) · `server/config/virtual_join_rules.json.sample` · `server/tests/test_virtual_join_guard.py`(신설) · `docs/guide/config/virtual_join_rules.md`
> **함께 읽을 보드 커밋:** `e16a862`(중복 전제가 강제된 적이 없다) · `316073c`(그 항목을 오독으로 열었다고 스스로 닫는다)
> **스위트(이 항목 작성 시점, HEAD = `1dc761b` 실측):** `conda run -n assy_manager python -m pytest server/tests contracts -q` → **1707 통과 / 0 실패**.
> ⚠️ `b6942ec` 본문의 「1736 → 1739」는 **그 시점 트리에 있던 미커밋 테스트 파일 1개(`server/tests/test_config_reload_integrity.py`, 32건)를 포함한 수**다. 커밋된 파일만 수집하면 1707이고, 그 파일까지 넣고 돌리면 1739/0이다. 델타 +3은 맞고 절대값이 32만큼 크다. (그 파일은 이 항목을 쓰는 사이에 다른 라운드가 `8a257f0`으로 커밋했다.)
> `test_virtual_join_guard.py` 단독: **43 통과 / 0 실패.**

## 배경 — 「불어난다」가 의견이 아니라 측정치였다

가상 조인은 두 테이블을 저장하지 않고 조회 시점에 잇는다. 위험은 오른쪽이 조인 키로
유일하지 않을 때 왼쪽 한 행이 맞는 행 수만큼 불어나는 것이고, 그 크기가 운영 DB에서 실측됐다.

| 같은 두 테이블, 조인 키만 다름 | 결과 |
|---|---|
| `core_defect_map ⋈ eds_fail_map` on `(lot, slot, x, y)` | 103,040 → **103,040** (1:1) |
| 같은 쌍 on `(lot, slot)` | 103,040 → **132,715,520** |

컬럼 두 개 차이인데 10만 행과 1억 3천만 행이다. 규칙은 그 수에서 바로 나온다 —
**맵 정체성(`lot,slot`)으로 이으면 그 맵의 셀 수만큼 곱해지고, 칩 정체성(`lot,slot,x,y`)으로
이으면 곱해지지 않는다.**

왼쪽의 다중도는 이 결함이 아니다. `dt_log ⋈ core_wafer_map` on `(core_lot, core_slot)`은
왼쪽이 키당 128행인데 결과는 768 → 768(×1.00)이다. 로그 여러 줄이 같은 웨이퍼를 가리키는 것이
곧 이 기능의 목적이라, **검사는 오른쪽에만 건다.**

## 07:18 `4e06eec` — 두 겹의 방어, 세 개의 증거 등급, 예산

첫 판은 이렇게 섰다.

1. **구조 검사(DB 0회)** — 오른쪽 테이블이 선언한 키가 오른쪽 조인 컬럼의 부분집합인가.
   선언의 **모양**에 대한 성질이라 시간이 지나도 썩지 않는다.
2. **실측 유일성 프로브** — `GROUP BY` 스캔. 1이 필요했던 이유가 아니라 **1로 부족하다는
   측정**이 근거였다: `bonding_map`은 1을 통과하면서 선언 키에 중복군 2,312개를 갖는다.

프로브 비용도 추정이 아니라 측정이었다 — 중복을 **찾는** 것은 조기 종료라 1~351ms지만,
**깨끗함을 증명하는** 것은 전수 스캔이라 859행/ms(1,000만 행이면 약 11.6초, 정렬은 337k부터
디스크로 샌다). 그래서 예산을 두고, **예산 소진은 `incomplete` = 거절**로 답하게 했다.
타임아웃이 「깨끗함」으로 읽히면 결함이 통째로 돌아온다.

그리고 증거를 세 등급으로 나눴다 — `unique_index`(미래의 쓰기까지 견딘다) ·
`probe_clean`(스냅샷) · `unverified`(1층만).

### 이 커밋이 뒤집은 것은 내 가설이었다

「인덱스가 걸린 `business_key_val`을 쓰면 유일성 확인이 싸다」고 제안했었다. 아니었다 —
**그 컬럼을 덮는 인덱스가 54개인데 유일한 것이 하나도 없다.** dedup upsert는 데이터베이스가
한 번도 강제한 적 없는 **관행**이었고, 그래서 「선언이 틀렸을 수도 있다」가 아니라
「오늘 이미 틀려 있다」였다.

## 08:20 `b6942ec` — 프로브·예산·`incomplete`·세 등급이 통째로 사라졌다

사용자의 판정은 두 문장이다.

> 「인덱스 없으면 거절해」
> 「**유니크 INDEX 걸면 그냥 DB 영속 아닌가**」

두 번째 문장이 재구성을 만들었다. 유니크 인덱스는 config가 아니라 **데이터베이스에 살고**,
`pg_index`를 읽는 것은 정책 손잡이를 돌리는 것이 아니라 **살아 있는 사실을 조회**하는 것이다.
그러면 등급도 스냅샷도 예산도 있을 자리가 없다 — 인덱스가 조인 키를 덮거나, 선언이 거부되거나.

프로브를 지운 진짜 이유는 「아무도 안 쓰니까」가 아니다. **거부가 운영자에게 건네는 DDL이
프로브보다 더 나은 진단기**이기 때문이다.

```
ERROR:  could not create unique index "uq_vjoin_..."
DETAIL:  Key (lot, slot)=(LOT-A, 01) is duplicated.
```

- 프로브가 못 하던 것 — **중복된 키 값을 지목한다.**
- 스냅샷이 아니라 **행동하는 순간의 진실**이다.
- 그리고 **우리 판정이 DB와 어긋날 수 없다. 우리가 더 이상 판정을 들고 있지 않으므로.**

남은 판정은 카탈로그 조회 하나다. 행을 세지 않으므로 비용이 테이블 크기와 무관하고,
그래서 요청 경로에 앉을 수 있다(전수 스캔인 프로브가 그럴 수 없었던 이유이기도 하다).

```python
rows = db.execute(text("""
    SELECT i.relname AS idx, array_agg(a.attname::text) AS cols
    FROM pg_index x
    JOIN pg_class c ON c.oid = x.indrelid
    JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(x.indkey)
    WHERE c.relname = :t AND n.nspname = 'public'
      AND x.indisunique AND x.indisvalid
      AND x.indpred IS NULL AND x.indexprs IS NULL
    GROUP BY i.relname
"""), {"t": table}).fetchall()
target = set(columns)
for idx, cols in rows:
    if set(cols) <= target:      # (a)에 UNIQUE가 있으면 (a,b)로도 유일하다
        return idx
return None
```

세 배제(`indisvalid` · `indpred` · `indexprs`)가 남은 이유는 셋 다
**「유니크 인덱스가 있다」로 읽히면서 유일성을 보장하지 않기** 때문이다. 판정 전체가 이제
그 구분 위에 서 있다. PostgreSQL이 아니면 `None`을 돌려준다 — **모르면 거절**이다.

### 정적 검사도 같이 지워졌다

`composite_key_source ⊆ join_key` 검사는 인덱스가 관문이 된 순간 **한 성질에 대한 두 번째
진실 공급원**이 됐고, 과잉 거절이 가능했다 — 테이블이 `business_key = id`를 선언해 두었어도
`(lot,slot)`이 진짜로 유일하고 인덱스가 걸려 있을 수 있다. **관문 하나, 대리인 없음.**

| | `4e06eec` | `b6942ec` | 실측 |
|---|---|---|---|
| `server/virtual_join_config.py` | 540줄 | **475줄** | −65줄, 기능은 더 많음 |
| `server/tests/test_virtual_join_guard.py` | 551줄 | **596줄** | +45줄 |

커밋이 적어 둔 실측: `unique_index_covering`은 1,760,871행 `bonding_map`에 대해 **1.0ms**.

## 라우트가 둘로 갈렸다 — 계약이 그것을 강제했다

`GET /admin/config/resolve`는 **DB 질의 0건**이 계약이라, 인덱스가 있는지 원리적으로 모른다.
그래서 승인 여부를 답하는 자리는 새 라우트다.

- `/admin/config/resolve?domain=virtual_join` — 선언의 **모양**이 유효한가 (설정 파일만 읽는다)
- `/admin/config/virtual-join/verify` — 실제로 **승인됐는가**, 아니면 무엇을 만들어야 하는가

⚠️ 문장은 **같은 조립기**(`config_resolve_report.virtual_join_detail`)가 만든다. 갈라 두면
같은 거부가 두 화면에서 다른 문장으로 나오고, 그 순간 「서버가 문장의 정본」 계약이 깨진다.

## 이 라운드가 자기 결함을 하나 잡았다 — 아무도 볼 수 없는 한국어 문장

주입 F에서 드러났다. `no_unique_index`의 한국어 문장이 **도달 불가**였다 — 그 코드는 세션을
쥔 경로만 만들어 내는데, DB 없는 리포트는 그것을 결코 내보내지 않는다.
**누구도 볼 수 없는 문장**이었다. 조립기를 하나로 뽑고 verify 라우트를 그리로 물려 고쳤다.
커밋 본문이 스스로 적어 뒀듯 **이 라운드에서 픽스처 결함이 방어를 가린 두 번째 사례**다.

## 내가 울린 경보 하나는 틀렸다 — 437행은 중복이 아니었다

`4e06eec`가 「`bonding_map` 키 하나에 437행」을 중복 위기의 대표 수치로 올렸다.
**중복이 아니다.** `business_key_val`에는 `x,y`가 들어가지 않으므로 **한 맵의 437개 셀이 키
하나를 공유**한다. 맵 테이블의 정상적인 모양이고, 그 437행은 **437가지 서로 다른 값 조합**을
싣고 있었다.

키 개수가 아니라 **행의 값**을 대조하고 남은 것은 `bonding_log` 117건 · `wafer_process` 43건이
바이트 동일, `inventory_master` 163건이 한 필드만 다름 — 사용자 판정으로 **전부 개발 환경
산물**이다(`316073c`).

> 살아남은 구조적 사실은 하나뿐이다: **`business_key_val`을 덮는 인덱스 54개 중 유일한 것이
> 없다.** 「키당 한 행」은 데이터베이스가 강제하지 않는 관행이다.
> 조인 경로는 「유니크 인덱스 없는 선언은 거부」라는 별개의 판정으로 닫혔고, 그것이 닫은 것은
> **한 경로이지 이 부류 전체가 아니다.**

## 그때 남아 있던 것

- **동봉된 샘플 선언은 오늘 거부된다.** `core_wafer_map`에 `(core_lot, core_slot)`을 덮는
  유니크 인덱스가 없다. 커밋 본문이 이것을 「올바른 동작」이라고 적었고, 가이드가 운영자에게
  DDL을 안내한다.
- **유효한 선언도 `effective`로 보고되지 않는다.** 아직 이 선언을 참조하는 조인 실행기가 없어
  `ineffective / not_reached`다. 실행기가 없는데 `effective`로 찍는 것이 곧 이 리포트가 막으려는
  거짓 「먹었다」이다.
- **`join_cardinality: "many"`는 이름이 붙은 거절이지 탈출구가 아니다.** 집계 형태의 코드
  경로가 아직 없다 — 탈출구를 먼저 내보내면 첫 거절을 만난 운영자가 그것을 열고 1억 3천만 행
  조인을 받는다.
- **새 사유 단어를 만들지 않았다.** 팬아웃은 기존 `scope_unresolved`에 매핑된다(런타임 뜻이
  이미 「0개 또는 2개 이상이 자기 것이라 주장한다」이다).
- `미상`은 **오른쪽 행이 없는 경우와 있는데 값이 빈 경우를 모두** 덮는다. 실측 근거는
  `bonding_log ⋈ core_wafer_map`에서 14,436행 전부가 오른쪽을 찾지만 3,792행(26.27%)의
  `wafer_id`가 비어 있다는 것. INNER는 이름을 붙여 금지했다.
- **주입 검증:** `4e06eec` 6건, `b6942ec` 9건, 각각 적색 후 되돌림.
