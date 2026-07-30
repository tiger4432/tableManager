# `virtual_join_rules.json` 세팅 — 저장하지 않는 조인(virtual join) 선언

> **Status:** 🟢 Living | **Last-verified:** 2026-07-31 (**신설 + 같은 날 게이트 확정** — 사용자 판정 「인덱스 없으면 거절해」로 **승인 근거가 UNIQUE 인덱스 하나**가 됐다. 직전 판의 3등급 모델(`unique_index`/`probe_clean`/`unverified`)과 중복 프로브·예산·`incomplete` 상태는 **삭제**됐다. ⏳ **조인 실행 코드는 아직 없다** — 이 파일은 선언과 그 검증만 다룬다) | **Owner:** Backend / 총괄
> 상위: [폴더 인덱스](./README.md) · 절차 요약은 [CONFIG_GUIDE §1](../CONFIG_GUIDE.md) · 검증기 정본은 `server/virtual_join_config.py`

<!-- Loader evidence (2026-07-31):
  shape only, no DB: virtual_join_config.load_virtual_join_rules / validate_virtual_join_rules / _validate_join
  the gate:          unique_index_covering (pg_index, excludes indisvalid=false / indpred / indexprs)
                     verify_uniqueness -> load_verified_rules  (the only accepting path)
  operator action:   required_index_name / required_index_ddl  (computed from the declaration alone)
  routes:            GET /admin/config/resolve?domain=virtual_join  (config only, zero DB queries)
                     GET /admin/config/virtual-join/verify          (catalog read, names the missing index)
  report:            config_resolve_report._resolve_virtual_join (DOMAIN_VIRTUAL_JOIN)
  tests:             server/tests/test_virtual_join_guard.py (41)
-->

## 1. 무엇인가

두 테이블을 **저장하지 않고 조회 시점에** 잇는다. `/api/maps/overlay`가 좌표로 하는 일의
행(row) 버전이고, 잇는 기준은 좌표가 아니라 선언된 조인 키다.

분석가는 REST API로 두 테이블을 Spotfire에 끌어와 거기서 잇는다. DB 뷰를 만들지 않는
이유가 그것이다 — 서빙 계층은 API다.

## 2. 승인 조건은 하나다 — 조인 키를 덮는 UNIQUE 인덱스

오른쪽 테이블에 **조인 키를 덮는 유효한 UNIQUE 인덱스**가 있어야 승인된다. 없으면 거부다.

> 사용자 판정(2026-07-31): 「인덱스 없으면 거절해」 · 「유니크 INDEX 걸면 그냥 DB 영속
> 아닌가」

그 지적이 설계를 바꿨다. UNIQUE 인덱스는 **이미 영속**이다 — config가 아니라 데이터베이스에
살고, 이후의 어떤 쓰기도 그 성질을 깰 수 없다. `pg_index`를 읽는 것은 정책 노브가 아니라
**살아 있는 사실의 조회**다. 그래서 등급도, 스냅샷도, 유효기간도 없다.

### 왜 필요한가 — 실측 (2026-07-31, 운영 DB read-only)

| 선언 | 왼쪽 행 | 조인 결과 | 배율 |
|---|---:|---:|---:|
| `core_defect_map ⋈ eds_fail_map (lot,slot,x,y)` | 103,040 | 103,040 | x1 |
| `core_defect_map ⋈ eds_fail_map (lot,slot)` | 103,040 | **132,715,520** | **x1288** |
| `bonding_log ⋈ wafer_process (lot,slot)` | 14,436 | **2,552,624** | **x177** |
| `dt_log ⋈ core_wafer_map (core_lot,core_slot)` | 768 | 768 | x1.00 |

오른쪽이 조인 키로 유일하지 않으면 왼쪽 행 하나가 맞는 행 수만큼 불어난다. 위 2행과 1행은
컬럼 두 개 차이인데 결과는 10만 행과 1억 3천만 행이다.

### 인정하지 않는 인덱스 셋

셋 다 「UNIQUE 인덱스가 있다」로 읽히지만 유일성을 보장하지 않는다.

| 배제 | 왜 |
|---|---|
| `indisvalid = false` | 취소된 `CREATE INDEX CONCURRENTLY`의 잔해. 플래너는 영원히 쓰지 않고 제약도 강제되지 않는다 |
| `indpred IS NOT NULL` | 부분 인덱스. 술어 안에서만 유일하다 |
| `indexprs IS NOT NULL` | 표현식 인덱스. 컬럼이 아니라 식에 대한 유일성이다 |

### 왼쪽의 중복은 팬아웃이 아니다

검사는 **오른쪽에만** 건다. `dt_log → core_wafer_map`는 왼쪽이 키당 128행이지만 결과는
768행 → 768행(x1.00)이다. 로그 여러 줄이 같은 웨이퍼를 가리키는 것이 곧 이 기능의
목적이므로, 가드가 그 모양을 잡으면 기능 자체를 잡는 것이다.

## 3. 거부됐을 때 무엇을 하는가

거부는 **만들어야 할 인덱스의 DDL을 그대로** 준다. 「UNIQUE 인덱스가 없다」만 말하고
어느 컬럼인지 말하지 않는 거부는 운영자가 행동할 수 없는 거부다.

```
CREATE UNIQUE INDEX CONCURRENTLY uq_vjoin_core_wafer_map_core_lot_core_slot
  ON "core_wafer_map" ("core_lot", "core_slot");
```

- `CONCURRENTLY`는 쓰기를 잠그지 않는다. 대신 **취소되면 무효 인덱스가 남으므로**,
  취소했다면 `DROP INDEX` 후 다시 만들어야 판정이 인정한다(§2의 배제 1번).
- 실행 중 **중복 오류**가 나면 그 값이 실제로 둘 이상 있다는 뜻이다. PostgreSQL이
  중복된 키 값을 지목해 주므로 데이터를 먼저 정리한 뒤 다시 만든다.

> 🔴 **중복 검사를 서버가 따로 하지 않는 이유가 이것이다.** 직전 판에는
> `GROUP BY … HAVING count(*)>1` 프로브와 시간 예산이 있었지만, 게이트가 UNIQUE
> 인덱스로 바뀌면서 소비자를 잃었고 **삭제**했다. `CREATE UNIQUE INDEX`가 같은 진단을
> 더 정확하게(중복된 키 값까지 지목) 행동하는 그 순간에 내놓으며, 스냅샷이 아니라 그
> 순간의 진실이다. 같은 연산이 이미 있는데 열등한 사본을 두지 않는다.

## 4. 「미상」의 정의 — 경계 계약

조인 결과에서 `unresolved_label`(기본 `미상`)은 **두 경우를 모두 덮는다**:

1. 오른쪽에 맞는 행이 **아예 없다**.
2. 맞는 행은 **있는데 그 값이 비어 있다**(NULL 또는 빈 문자열).

②를 빼면 안 되는 이유는 실측이다. `bonding_log → core_wafer_map.wafer_id`는
**14,436행 전부가 오른쪽 행을 찾는다** — 그런데 3,792행(26.27%)의 `wafer_id`가 비어 있다.
`core_defect_map → core_wafer_map.wafer_id`는 103,040행 전부가 행을 찾고 88,872행(86.25%)이
비어 있다. LEFT 조인만으로는 이 26%와 86%가 「값이 있다」로 읽힌다.

INNER 조인은 ①을 조용히 지우므로 쓰지 않는다.

## 5. 키 사전

| 키 | 필수 | 뜻 |
|---|---|---|
| `left_table` | ✅ | 왼쪽(구동) 테이블. `table_config`에 등록돼 있어야 한다 |
| `right_table` | ✅ | 오른쪽(참조) 테이블. 조인 키를 덮는 UNIQUE 인덱스 필요(§2) |
| `join_key` | ✅ | `{left, right}` 쌍의 목록. 같은 `right` 컬럼을 두 번 묶을 수 없다(키가 넓어 보이지만 고정하는 성분은 하나다) |
| `expose` | ✅ | 왼쪽에 붙여 보여줄 오른쪽 컬럼들. 왼쪽에 **같은 이름이 있으면 거부** — 어느 쪽 값인지 알 수 없는 표가 된다. 상한 32개 |
| `unresolved_label` | | 기본 `미상`. §4의 두 경우를 모두 덮는다 |
| `enabled` | | 기본 `true`. `false`는 오류가 아니라 조용한 제외 |
| `join_cardinality` | | `"one"`만 지원. 집계 형태는 **구현이 없어** 선언하면 거부된다(§7) |

## 6. 확인하는 법 — 라우트가 둘인 이유

```bash
# ① 선언의 모양이 유효한가 (설정 파일만 읽음 · DB 질의 0건)
curl -H "X-Admin-Token: <토큰>" "http://localhost:8080/admin/config/resolve?domain=virtual_join"

# ② 실제로 승인됐는가 (pg_index 카탈로그 조회)
curl -H "X-Admin-Token: <토큰>" "http://localhost:8080/admin/config/virtual-join/verify"
```

①은 「DB 질의 0건」이 계약이라 인덱스의 존재를 알지 못한다. 그래서 **어떤 선언도 ①에서
`effective`가 되지 않는다** — 대신 만들어야 할 인덱스 DDL을 문장에 실어 준다(필요한
인덱스는 선언 자체로 계산되므로 세션 없이도 말할 수 있다).

②는 카탈로그만 읽는다 — **행을 세지 않으므로 비용이 테이블 크기와 무관**하고, 그래서
요청 경로에 앉을 수 있다(전수 스캔이던 구 프로브는 그럴 수 없었다). 응답의
`accepted` / `unique_index` / `required_index_ddl`이 선언별 답이다.

- ①의 `rejected` — 사유는 닫힌 어휘 4단어. 유일성 미보장은 `scope_unresolved`,
  문법·미구현 형태는 `mapping_unavailable`.

> 사유 어휘에 단어를 추가하는 것은 **계약 변경**이며
> `contracts/config_resolve_report/vectors.json` + node 하네스를 함께 고쳐야 한다.

## 7. 왜 「집계 형태」 스위치가 열려 있지 않은가

x1288 조인이 언제나 틀린 것은 아니다 — **행 조인으로서** 틀렸다. 집계 형태(오른쪽을 먼저
접고 잇기)는 정당할 수 있다.

그래도 `join_cardinality: "many"`는 지금 **거부**된다. 유일성 요구를 끄는 스위치는 그것이
향할 안전한 경로가 생긴 뒤에 열려야 하기 때문이다. 지금 열어 두면 처음 거부를 만난
운영자가 그 스위치를 켜고 1억 3천만 행 조인을 얻는다.

## 8. 함정

- **`expose`가 왼쪽 컬럼을 가리면 거부된다.** 이름이 겹치면 표에서 어느 쪽 값을 보고 있는지
  알 수 없다.
- **밑줄로 시작하는 키는 선언이 아니라 주석이다**(`_comment` 등) — 조용히 건너뛴다.
- **파일 부재는 거부가 아니다.** 선언이 없을 뿐이며 `sources[].exists: false`로 나온다.
- **PostgreSQL이 아니면 전부 거부된다.** 카탈로그를 읽을 수 없으면 유일성을 모르고,
  모르면 통과시키지 않는다.
