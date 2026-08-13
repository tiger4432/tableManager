# 🗺️ DOE 영역 저장 지도 — 무엇을 어디에 쓰는가

> **Status:** 🗄️ **대체됨 — 아래 본문은 폐기된 3테이블 모델이다** | **Last-verified:** 2026-08-13 (`c0fb735` — 두 테이블이 **선언째 은퇴**했고 개발 DB에서는 물리 DROP까지 실행됐다. 직전 2026-07-27 M2.6 서버 리바인딩 `0f8d35f`) · 소스에서 역산(추정 아님)
> **대상:** map editor 우측 「2. Legend & DOE」 패널에서 편집하는 모든 항목
> **근거:** `client2/src/transfer_plan.js`(DOE 저장) · `client2/src/map_editor.js`(legend 저장)

> 🛑 **읽기 전에: 아래 본문은 더 이상 사실이 아닙니다.** M2.6이 착지해 **3테이블 → 1테이블**로 바뀌었습니다(클라 `cdcddee` · 서버 `0f8d35f`).
>
> **지금의 모델** — `map_split_registry` 한 테이블이 값(=DOE 조건) 전부를 담습니다:
> `split_key` · `color` · `split_desc` · `knobs` · **`bands` JSON** `[{seq, to, materials[]}]`.
> 🗄️ **[2026-08-13 `c0fb735`] `map_doe`·`map_doe_source`는 «선언째» 은퇴했습니다.** 2026-07-27에 폐기되고 「읽기용 선언만 남긴다」 상태였으나, 제품 소유자 승인으로 `.sample`·`product_tables.py`에서 삭제되고 **개발 두 DB에서는 물리 DROP까지 실행**됐습니다(`server/migrations/drop_map_doe_tables.sql`, 운영 절차는 [process/OPERATOR_RUNBOOK §5](../process/OPERATOR_RUNBOOK.md)). ⚠️ **그래서 아래 §2·§3의 컬럼 표는 이제 «읽을 수 있는 테이블»에 대한 서술이 아니고**, 운영 DB에 남아 있는 기존 행을 손으로 옮길 때만 의미가 있습니다. 🔴 **역방향 스크립트를 쓸 일이 생기면 그 파일을 보십시오 — 물리 컬럼은 이 문서의 목록과 다릅니다**(선언에 없는 일반 컬럼 일곱, `band_seq`/`qty_total`/`qty`는 `double precision`).
> 구간은 **연속**이라 `from`은 앞 구간의 `to`+1로 유도되고, 층 수 = `to_i − to_(i−1)`, **수량·자재 배분은 저장하지 않고 파생**합니다.
>
> **양쪽이 착지했습니다(2026-07-27).** `knobs`·`bands`는 라이브 `table_config.json`에 선언돼 **물리 컬럼으로 존재**하고(config watcher가 재기동 없이 ALTER 실행), `server/transfer_plan.py`는 `plan_store.registry` → `map_split_registry`로 **리바인딩됐습니다**.
> ⚠️ **남은 것은 웹서버 재기동 하나입니다.** 물리 컬럼은 재기동이 필요 없고 **코드만** 필요합니다. 2026-07-27 관측: 옛 모듈을 든 채 실행 중이던 프로세스에서 `GET /api/transfer-plan/validate`가 `plan_store.doe unresolved`로 404를 냈습니다. 재기동 여부는 이 문서가 아니라 실제 응답으로 확인하십시오 — **이 문장은 그날의 관측이지 현재 상태 표시가 아닙니다.**
>
> **아래 본문을 남겨두는 이유는 기존 데이터를 해석하기 위해서입니다.** 새 작업의 정본은 `server/product_tables.py`(`map_split_registry`의 `bands` 계약)와 [CONFIG_GUIDE §5.8](../guide/CONFIG_GUIDE.md)입니다.
> 바뀌지 않는 것: **구간의 정체는 정수 서수로 남습니다**(`band_seq` → `bands[].seq`). `(from, to)`나 라벨을 정체로 삼으면 범위를 고치는 순간 자재가 고아가 됩니다. 다만 **`seq`는 이제 DB가 유일성을 강제하지 않습니다** → [PRIMITIVES §2](../architecture/PRIMITIVES.md).

---

## 한눈에

DOE 패널 하나를 편집하면 **세 곳**에 나뉘어 저장된다. 이게 헷갈리는 지점이다.

```
┌─ 값(value) 자체의 정체 ────────────→  map_split_registry   (색·설명)
│
├─ 값 × 구간(band)의 계획 ───────────→  map_doe              (구간·수량·knob)
│    └─ 그 구간에 투입할 자재 ───────→  map_doe_source       (lot/slot·배분수량)
│
└─ 캔버스에 칠한 셀 ────────────────→  그 맵 테이블 자신     (bonding_map 등)
```

**계획의 정체는 `(ref_table, map_key)`다.** `plan_id`도 계획 헤더 테이블도 없다 — `bonding_map`을 열면 그게 본딩 계획이다.

---

## 1. `map_split_registry` — 값의 색과 설명

**행 단위: 맵 하나의 값 하나** (`bonding_map` × `AAA` × `F`)

| 화면 항목 | 컬럼 | 비고 |
|---|---|---|
| — | `split_key` | **bk** = `ref_table\|map_key\|value` |
| — | `ref_table`, `map_key`, `value` | bk 구성 요소 |
| 값 설명 | `split_desc` | |
| 값 색상 | `color` | |
| — | `eventtime` | 저장 시각 |

> 구분자는 **`|`** 다. `map_key` 자체에 `_`가 흔하고 테이블명에도 `_`가 있어 `_`로는 파싱이 깨진다.

---

## 2. `map_doe` — 값 × 구간의 계획

**행 단위: 값 하나의 구간 하나** (`F`의 1구간, 2구간…)

| 화면 항목 | 컬럼 | 비고 |
|---|---|---|
| — | `doe_key` | **bk** = `ref_table\|map_key\|doe_value\|band_seq` |
| — | `ref_table`, `map_key` | 계획 정체성 |
| 값 | `doe_value` | legend의 값과 같은 문자열 |
| — | `band_seq` | **정수 서수 = 구간의 진짜 정체** |
| STACK 구간 | `stack_band` | **자유 텍스트 라벨**(`1`, `2-15`, `H1~H2`, `바닥`) — 파싱하지 않는다 |
| 필요 수량 | `qty_total` | |
| knob | `knobs` | JSON 문자열 |
| — | `note` | 현재 미사용(빈 문자열) |
| — | `updated_by`, `eventtime` | |

### ⚠️ 여기가 설계의 핵심

**`band_seq`가 키고 `stack_band`는 라벨이다.** 구간 표기를 자유 텍스트로 두면서도 정체를 지키기 위한 분리다.

라벨을 키로 삼았다면 `2-15`를 `2-14`로 고치는 순간 그 구간에 붙어 있던 **자재 묶음이 통째로 고아가 된다**. 정수 서수가 정체를 지고 있으므로 라벨은 마음대로 고쳐도 자재가 따라온다.

---

## 3. `map_doe_source` — 구간에 투입할 자재

**행 단위: 값 × 구간 × 자재 하나**

| 화면 항목 | 컬럼 | 비고 |
|---|---|---|
| — | `source_key` | **bk** = `ref_table\|map_key\|doe_value\|band_seq\|source_lot\|source_slot` |
| — | `ref_table`, `map_key`, `doe_value`, `band_seq` | 어느 구간에 붙는지 |
| 자재 lot | `source_lot` | |
| 자재 slot | `source_slot` | 없으면 빈 문자열 |
| — | `qty` | **`bandShare(b)`로 배분된 수량** |
| — | `note` | 현재 미사용 |
| — | `updated_by`, `eventtime` | |

### 자재는 값이 아니라 **구간**에 붙는다

`band_seq`를 반드시 함께 쓴다. 빠뜨리면 서버가 그 구간의 묶음을 못 찾아 `source_unresolved`가 뜬다.

### 배분식은 하나뿐이다

`qty`는 `bandShare(b)` 한 함수에서만 나온다. 예전에는 **저장이 `ceil`, 표시가 `round`**여서 DB에 34가 들어가 있는데 화면은 33을 보여줬다. 같은 숫자를 두 곳에서 계산하면 반드시 갈라진다.

---

## 4. 맵 테이블 자신 — 칠한 셀

캔버스에서 칠한 값은 **그 맵 테이블에 직접** 들어간다(`bonding_map`의 `x`, `y`, `leg` 등). 계획용 사본 테이블은 없다 — **계획 = 그 맵 자체**이기 때문이다.

> ⚠️ 그래서 맵 키를 잘못 바꾼 뒤 Push하면 **실운영 맵을 건드린다**. Push 시 "로드한 맵과 키가 달라졌으면 차단" 가드가 그래서 있다.

---

## 5. 저장 시점 — **삭제는 계산하지 않는다, 교체에서 따라 나온다** (2026-07-27)

- **자동 저장**(디바운스 1.2초). 별도 [저장]·[확정] 버튼은 폐기됐다.
- 헤더에 `서버 <시각>`으로 뜨는 값은 `map_doe`에서 읽어온 **`eventtime`**이다.
- 서버 상태를 확인하지 못하면 **쓰기도 삭제도 하지 않고** 브라우저 초안에만 남긴다. 화면이 서버본에서 유래했을 때만 쓰기 권한이 생긴다(로드 실패 후 편집이 서버 계획을 통째로 지우던 결함의 수정).

### 쓰기 방식: `replace_map`

DOE 저장도 legend 저장도 **맵 Push와 구조적으로 같은 연산**이다 — 화면의 집합이 곧 저장돼야 할 집합이다. 그래서 클라는 차집합을 계산하지 않고 `replace_map`으로 **범위를 통째로 교체**한다.

범위는 세 테이블 모두 **`map_key_columns = (ref_table, map_key)`**로 잡힌다(`server/product_tables.py`에 선언).

> **DOE 삭제가 되돌아오던 진짜 원인**: 계획 행은 실제로 지워지고 있었는데 `map_split_registry` 행이 살아남았고, 맵을 다시 열면 레지스트리에만 있는 값이 **빈 껍데기 legend 행으로 부활**했다. 근본 원인은 기능 부재가 아니라 **선언 부재**였다 — 세 테이블에 `map_key_columns`가 없어 `replace_map`이 지울 범위를 잡지 못했고, 그 자리를 메우려고 클라에 차집합 계산 기계장치가 얹혀 있었다. 선언을 넣자 그 기계장치(`pruneScoped`·`S.serverKeys`·차집합 장부)는 **비활성화가 아니라 삭제**됐다.
>
> ⚠️ **선언 누락은 기능 누락처럼 읽힌다.** 똑같은 요청이 선언이 있으면 지우고 없으면 아무것도 안 지우면서 **양쪽 다 `200 {"status":"success"}`**를 낸다. config 주도 서버 경로가 완전히 조용히 실패할 수 있다는 뜻이고, 그래서 이런 경로가 실제로 도는지 증명하는 방법은 **선언을 빼고 다시 돌려보는 것**이다.

### 알려진 구멍 2개 (덮지 않고 기록)

| 구멍 | 내용 |
|---|---|
| **빈 집합을 표현할 수 없다** | `crud`가 교체 범위를 `updates[0]`에서 잡으므로, 구간이 하나도 없는 값은 **보낼 것이 없어 아무 일도 일어나지 않는다.** 저장됐다고 주장하는 대신 헤더에 경고를 띄운다 |
| **형제 안전성이 사라졌다** | 구 prune은 자기가 본 키만 건드려서 다른 세션의 추가분이 **구조적으로** 안전했다. `replace`는 범위 전체를 지우므로 그 보호가 없다 → 동시 편집은 [PRODUCTION_READINESS](../process/PRODUCTION_READINESS.md) C2 |

> legend 읽기에는 절단 가드가 **아예 없었다.** 교체 의미론 아래서 절단된 읽기는 곧 **데이터 파괴 읽기**다 — 이제 가드가 있다.

---

## 6. 자주 헷갈리는 것

| 질문 | 답 |
|---|---|
| `map_doe`가 테이블 드롭다운에 없다 = 안 쓰는 건가? | ~~쓴다~~ → **더 이상 쓰지 않는다**(M2.6, `cdcddee`). 기존 행 읽기용으로 선언만 남아 있다 |
| 값의 색을 바꿨는데 `map_doe`가 안 변한다 | 정상. 색·설명은 `map_split_registry` 소관 |
| 구간 라벨을 고쳤는데 자재가 그대로다 | 정상. 정체는 `band_seq`고 라벨은 비키다 |
| 자재 수량을 직접 못 정한다 | 현재는 구간 수량을 자재 수로 **올림 배분**한다(`bandShare`) |
