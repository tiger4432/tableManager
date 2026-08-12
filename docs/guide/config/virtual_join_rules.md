# `virtual_join_rules.json` 세팅 — 저장하지 않는 조인(virtual join) 선언

> **Status:** 🟢 Living | **Last-verified:** 2026-08-12 (**§2-ter 신설 — 조인 비용의 실측 모양**(`16b49ef`): `attach`의 **58%가 SQL**(10,000행 페이지 하나에 왕복 20회 = 선언 둘 × 청크 10, `CHUNK_SIZE=1000`)이고 노출 컬럼 넷이 **전부 `virtual_only`**라 비용은 구성상 O(행)이다 — 깎을 수 있는 것은 셀당 상수뿐. 🔴 **「이 루프는 무조건 돈다」가 거짓**이었다: `attach`는 테이블당 단락하고 선언을 가진 왼쪽 테이블은 14개 중 `dt_log` 하나이며, **격리 `assy_qa`에서는 두 선언 모두 거부**돼(중복 키 → UNIQUE 인덱스 생성 불가) 그 박스의 `attach`는 0.0 ms다. 함께 §「정확성 제약」에 **코드 사본 경고** 추가 — `virtual_join_executor.py`·`main.py`가 아직 「UNIQUE 인덱스를 그대로 탄다」고 적고 있다(성능 주장으로는 거짓, 총괄 라우팅 대상). 직전 2026-08-04: **§2-bis 신설 — 표기 정규화가 걸린 조인 키에서는 세 번째 배제가 뒤집힌다**(`8d306a5`): 접힌 비교는 컬럼 유일성이 아니라 **식 유일성**을 요구하므로 **함수 인덱스만 후보**가 되고 평범한 컬럼 UNIQUE는 배제된다. 🔴 이유는 성능이 아니라 **정확성**이다 — 원본으로 다른 두 행이 접히면 한 값이라 컬럼 UNIQUE가 있어도 접힌 키로는 중복이다. 함께 **「이 인덱스는 정확성 제약이지 조회 계획이 아니다」** 절 신설: 실측 플랜은 `Hash Left Join` + 오른쪽 `Seq Scan`이고 **인덱스의 성능 역할은 한 번도 행사된 적이 없다**(조인이 더한 버퍼는 왼쪽 15,469행에서도 103,040행에서도 **4**). 인덱스는 팬아웃 방지로 **여전히 필수**다. 직전 라운드: **N7 — 숫자 expose 컬럼이 읽기 표면 전체에서 동작한다.** 2026-08-02 사용자 보고: `number` 타입 컬럼을 노출하면 조회가 SQL 계층에서 500이었다 — 해석식이 `COALESCE(double precision, '미상')`을 만들었고 PostgreSQL이 타입 불일치로 거절했다. 수정: 숫자 컬럼은 COALESCE **이전에** 정본 비교 텍스트로 렌더한다(`crud.numeric_text_sql` — 정수값이면 INT 철자, `3.0`이 아니라 `3`). §4-ter 참조. **§9의 검색·CSV 두 미해결은 `cd3e0f4`(2026-07-31)로 이미 해소**돼 있었고 이번에 문서를 따라잡혔다. 직전 라운드 기록은 히스토리로) — 이전: 2026-07-31 (**같은 날 네 번째 라운드 — 화면 착지 `9200f20`+`4b50135`**: `/schema`가 가상 컬럼을 **별도 키 `virtual_columns`로** 알리고 그리드가 그것을 **덧붙여** 그린다. 🔴 **`columns`에 합치지 않는 것이 설계의 전부**다 — 그 배열의 뜻은 「저장하는 컬럼」이고 소비자 넷이 그 뜻에 기댄다. 🔴 **그리는 순간 그 컬럼은 붙여넣기·비우기·일괄채우기의 대상이 되므로** 클라에 술어 하나(`isVirtualColumn`)를 두어 제안을 막는다(강제는 여전히 서버 깔때기). §9의 첫 미해결 항목이 **해소**됐고 **새 미해결 둘**(CSV 추출 누락 · `미상` 행 검색 불가)이 그 자리에 들어왔다. 직전: **신설 → 같은 날 게이트 확정 → 같은 날 실행기 착지 `d70a33d`**. 사용자 판정 「인덱스 없으면 거절해」로 **승인 근거가 UNIQUE 인덱스 하나**가 됐고, 직전 판의 3등급 모델(`unique_index`/`probe_clean`/`unverified`)과 중복 프로브·예산·`incomplete` 상태는 **삭제**됐다. **조인은 이제 실제로 실행된다** — `server/virtual_join_executor.py`가 읽기 경로에서 `expose` 컬럼을 붙이고, **이름 충돌 거부는 해제**돼 「부재일 때만 채운다」가 됐다(§4-bis)) | **Owner:** Backend / 총괄
> 상위: [폴더 인덱스](./README.md) · 절차 요약은 [CONFIG_GUIDE §1](../CONFIG_GUIDE.md) · 선언·검증 정본은 `server/virtual_join_config.py` · **실행 정본은 `server/virtual_join_executor.py`**

<!-- Loader evidence (2026-07-31, 실행기 착지 후 재확인 · d70a33d):
  shape only, no DB: virtual_join_config.load_virtual_join_rules / validate_virtual_join_rules / _validate_join
  the gate:          unique_index_covering (pg_index, excludes indisvalid=false / indpred / indexprs)
                     verify_uniqueness -> load_verified_rules  (the only accepting path)
  operator action:   required_index_name / required_index_ddl  (computed from the declaration alone)
  execution:         virtual_join_executor.rules_for / execute_rule / _resolve_one / attach
                     (load_verified_rules is its ONLY entry - a shape-only rule never executes)
  read path:         main.fetch_and_merge_metadata -> virtual_join_executor.attach
                     (the single serialization point for row payloads)
  write refusal:     crud.refuse_virtual_join_columns, first statement of crud.apply_batch_updates
                     (virtual_only columns only; collide columns stay writable)
  cache invalidation: main.reload_local_process_cache -> virtual_join_executor.reset_cache
  routes:            GET /admin/config/resolve?domain=virtual_join  (config only, zero DB queries)
                     GET /admin/config/virtual-join/verify          (catalog read, names the missing index)
  report:            config_resolve_report._resolve_virtual_join (DOMAIN_VIRTUAL_JOIN)
  tests:             server/tests/test_virtual_join_guard.py + server/tests/test_virtual_join_executor.py
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

셋 다 「UNIQUE 인덱스가 있다」로 읽히지만 (컬럼에 대한) 유일성을 보장하지 않는다.

| 배제 | 왜 |
|---|---|
| `indisvalid = false` | 취소된 `CREATE INDEX CONCURRENTLY`의 잔해. 플래너는 영원히 쓰지 않고 제약도 강제되지 않는다 |
| `indpred IS NOT NULL` | 부분 인덱스. 술어 안에서만 유일하다 |
| `indexprs IS NOT NULL` | 표현식 인덱스. 컬럼이 아니라 식에 대한 유일성이다 — ⚠️ **아래에서 조건부가 됐다** |

#### 2-bis. 🔴 조인 키에 표기 정규화가 걸리면 **세 번째 배제가 뒤집힌다** (2026-08-04 `8d306a5`)

[`notation_rules.json`](./notation_rules_config.md)이 조인 키의 어느 한쪽이라도 정규화된 것으로 선언하면, ON 절의 비교가 **접힌 식**으로 이루어진다(`notation_norm.join_pair_rules` — **한쪽만 접는 방법은 없다**). 그러면 게이트가 물어야 할 유일성도 컬럼이 아니라 **식에 대한 것**이 된다:

| 조인 키가 | 인정되는 인덱스 | 배제되는 인덱스 |
|---|---|---|
| 접히지 **않으면** | 평범한 컬럼 UNIQUE | `indexprs IS NOT NULL` |
| **접히면** | **`indexprs IS NOT NULL`(함수 인덱스)** | 평범한 컬럼 UNIQUE |

`indpred`·`indisvalid` 배제는 양쪽 모두 그대로다.

🔴 **이유가 성능이 아니라 정확성이라는 점에 주의하라.** 원본으로 서로 다른 두 행(`'CL-1'`과 `'CL_1'`)이 접히면 **한 값**이다. 컬럼에 UNIQUE가 있어도 **접힌 키로는 중복**이고, 그 중복이 곧 이 절이 막으려는 팬아웃이다. 즉 평범한 UNIQUE 인덱스는 「느릴 뿐」이 아니라 **게이트가 묻는 질문에 답하지 못한다.**

- 요구되는 DDL은 `required_index_ddl`이 **함수 인덱스 형태**로 내놓고, 인덱스 이름에 `_nf` 접미가 붙는다. 식이 길어 보이지만 `\uXXXX` 이스케이프라 **전부 ASCII**이고 psql에 그대로 붙여 넣을 수 있다.
- 🔴 **조회 식과 인덱스 식은 반드시 같은 함수(`notation_norm.fold_sql_text`)에서 나온다.** PostgreSQL은 두 식이 **일치할 때만** 함수 인덱스를 쓰므로, 철자를 둘 두면 이론적 불일치가 아니라 **순차 스캔**이 되고 테스트는 전부 통과한다.
- 어느 키가 접히고 **어떤 규칙으로** 접히는지는 `GET /admin/config/virtual-join/verify`의 `folded_join_key`가 답한다.

### 왼쪽의 중복은 팬아웃이 아니다

검사는 **오른쪽에만** 건다. `dt_log → core_wafer_map`는 왼쪽이 키당 128행이지만 결과는
768행 → 768행(x1.00)이다. 로그 여러 줄이 같은 웨이퍼를 가리키는 것이 곧 이 기능의
목적이므로, 가드가 그 모양을 잡으면 기능 자체를 잡는 것이다.

### 🔴 이 인덱스는 **정확성 제약**이지 조회 계획이 아니다 (2026-08-04 실측)

「승인 조건이 인덱스니까 조인이 그 인덱스를 타겠지」로 읽지 마라. **실측한 플랜은
`Hash Left Join` + 오른쪽 `Seq Scan`이고, 인덱스의 성능 역할은 지금까지 한 번도
행사된 적이 없다.**

| 실측 | 왼쪽 | 플랜 | 조인이 더한 버퍼 |
|---|---:|---|---:|
| `bonding_log ⋈ core_wafer_map` | 15,469 | `Hash Left Join` | **+4** |
| `core_defect_map ⋈ core_wafer_map` | 103,040 | `Hash Left Join` | **+4** |

오른쪽(80행·4페이지)을 **한 번 해싱**하므로 조인의 I/O 비용은 **왼쪽이 아니라 오른쪽
크기의 함수**다. 왼쪽이 6.7배로 늘어도 더해진 버퍼는 그대로 4다. 그리고 현재 규모에서는
그것이 **옳은 플랜**이므로 결함이 아니다.

- **그래도 인덱스는 반드시 필요하다** — 팬아웃을 막는 것이 그 역할이고, 그것은 플랜과
  무관하게 성립한다(위 x1288 실측). 지우면 **정확성 회귀**다.
- ⚠️ **다시 재야 할 수 하나**: 위 측정의 오른쪽은 80행이라 해시가 `Batches: 1`(12kB)이다.
  오른쪽이 `work_mem`을 넘길 만큼 큰 선언이 생기면 이 수치는 **이월되지 않는다.**
- ⚠️ **접히는 키에서는 이야기가 또 다르다** — §2-bis. 함수 인덱스가 없으면 접힌 비교는
  선택의 여지 없이 순차 스캔이고, 실측으로 `dt_log` 조인이 **3.1ms → 151.6ms**였다.

> 🔴 **코드에는 아직 반대로 적혀 있다.** `server/virtual_join_executor.py` 모듈 docstring의
> 「오른쪽은 승인 조건이었던 UNIQUE 인덱스를 그대로 탄다」와 `server/main.py`의 같은 취지
> 주석 — **둘 다 성능 주장으로는 거짓**이고 위 표가 정본이다. 2026-08-04 감사에서 발견됐고
> 코드 사본 둘은 총괄 라우팅 대상으로 남아 있다(이 절이 신설된 이유가 바로 **그 문장을 코드
> 에서 읽은 사람이 다시 유도하지 않게** 하려는 것이다). 성능 판단이 필요하면 **여기를 읽어라.**

### 2-ter. 조인 비용의 실측 모양 — **파이썬이 아니라 SQL이고, 그 SQL은 왕복 수다** (2026-08-12 `16b49ef`)

⚠️ **격리 `assy_qa` · 개발 워크스테이션 실측이며 운영 수치가 아니다.**

읽기 경로의 `attach`를 「되찾을 수 있는 파이썬 비용」으로 보고 착수한 라운드가 있었고,
그 전제가 **둘 다 틀렸다.** 다음에 같은 판단을 하기 전에 읽을 것:

- **`attach`의 58%는 SQL이다.** `row_id IN (...)`이 `CHUNK_SIZE = 1000`으로 끊기므로
  10,000행 페이지 하나가 **왕복 20회**(선언 둘 × 청크 10 — 실측 180.5 ms)이고, 그것이
  `attach` 안에서 가장 큰 조각이다. 파이썬을 아무리 깎아도 이 몫은 안 줄어든다 — 줄이려면
  **청크 크기**를 건드려야 하는데 그 상수는 `enrichment_candidates`와 공유하는 시스템 공통값이다.
- **「필요한 만큼만 계산하게 만든다」가 여기서는 적용되지 않는다.** 오늘 노출되는 네 컬럼
  (`dt_lot_confirmed`·`dt_slot_confirmed`·`core_frame`·`dt_frame`)이 **전부 `virtual_only`**라
  왼쪽에 값이 있는 셀이 **0건**이다(매치율 100%). 즉 **모든 행이 그 컬럼을 실어야 하고**
  비용은 구성상 O(행). 깎을 수 있었던 것은 **셀당 상수**뿐이다.
- 🔴 **「이 루프는 무조건 돈다」는 술어를 라이브에 먹여 보기 전엔 주장이다.** ⓐ `attach`는
  `rules_for`가 빈 목록이면 즉시 반환하므로 **테이블당 단락**하고, 선언을 가진 왼쪽 테이블은
  운영 config 14개 중 **`dt_log` 하나**다. ⓑ 그리고 격리 `assy_qa`에서는 **두 선언 모두
  거부 상태**다 — `dt_job_attribution(dt_job)`과 `eqp_frame_attribution(dt_eqp, product)`에
  중복 키가 있어 요구되는 UNIQUE 인덱스가 **애초에 만들어지지 않는다**(§3의 거부가 그
  중복을 지목한다). 그래서 그 박스에서 `attach`는 **0.0 ms**이고, 거기서 잰 프로파일로
  운영을 논하면 안 된다.

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

> **②가 사는 곳은 SQL이 아니라 파이썬이다.** LEFT 조인은 ①만 준다 — 오른쪽 행이 있으면
> 빈 값을 그대로 돌려주기 때문이다. `virtual_join_executor._resolve_one`이 조인 값을
> **행의 유무가 아니라 비어 있는지**로 판정하는 것이 ②를 덮는 유일한 이유다. 빈 판정은
> `crud.clean_str_value(v) == ""` — 시스템의 나머지와 **같은 뜻**이라야 한다.
> 실행기는 오른쪽 행의 유무(`matched`)를 따로 들고 다니는데, 표시용이 아니라 **①과 ②가
> 같은 `미상`으로 접힌 뒤에도 두 분기를 관측할 수 있게** 하기 위한 것이다.

## 4-bis. 이름 충돌 — 거부가 아니라 「부재일 때만 채운다」 (2026-07-31 `d70a33d`)

`expose` 컬럼 이름이 **왼쪽 테이블에 이미 있어도 된다.** 운영 `dt_log`는 lot/slot 대신
`wafer_id`가 직접 꽂힌 행이 섞여 있어서, 조인이 채우려는 바로 그 컬럼이 왼쪽에 이미 있다.
**거부는 이 커밋에서 해제됐다** — 그 자리를 대신하는 것이 아래 규칙이다.

| 왼쪽 값 | 조인 값 | 셀에 남는 것 | 출처 표시 |
|---|---|---|---|
| 있음 | (무엇이든) | **왼쪽 값 그대로** — 조인 값은 버린다 | **없음**(셀을 한 바이트도 건드리지 않는다) |
| 비었음 | 있음 | 조인 값 | `virtual_join` |
| 비었음 | 비었음/없음 | `unresolved_label`(기본 `미상`) | `virtual_join` |

- **「비었음」의 정의는 `crud.clean_str_value(v) == ""` 하나다.** 꼬리 공백이 여기서는 값이고
  저기서는 공백이면 안 되므로 두 번째 철자를 만들지 않는다.
- 🎯 **이 연산은 enrichment의 빈칸 전용(absent-only) 관문과 구조적으로 같다.** 새 개념이
  아니라 같은 연산의 두 번째 자리이며, 그래서 같은 어휘를 쓴다 →
  [PRIMITIVES §1](../../architecture/PRIMITIVES.md).
- **왼쪽 값이 이긴 셀에는 흔적을 남기지 않는다.** 조인이 참여했다가 진 것은 출처가 아니다 —
  `sources`에 표식을 달면 「이 값은 조인이 만들었다」는 거짓말이 된다.

### 왜 거부를 뺄 수 있었나 — 조건 둘을 갖춘 뒤에 뺐다

거부의 근거였던 걱정(**「어느 쪽 값을 보고 있는지 알 수 없는 표가 된다」**)은 옳았다. 다만
거부가 그 답이 아니었고, 답 두 개를 **함께** 갖춘 뒤에 뺐다.

1. **부재일 때만 채운다** — 왼쪽 값이 있으면 손대지 않으므로 기존 값이 조인 값으로 바뀌는
   일이 구조적으로 없다.
2. **셀마다 출처를 싣는다** — 조인이 만든 셀은 `sources`에 `virtual_join`이 붙고
   `priority_source`가 그것으로 선다. `cell_sources`가 쓰는 것과 **같은 어휘**라 기존 셀
   소스 표시가 그대로 읽는다(새 화면 0).

🔴 **둘 중 하나만 빼면 원래의 걱정이 그대로 돌아온다.**

> **가상 조인은 `cell_sources`에 쓰지 않는다.** 조회 시점 계산이라 영속 흔적이 없고, 그래서
> 조인이 만든 셀에는 `CellSource` 행이 **존재할 수 없다**. `crud.SOURCE_PRIORITY`에도
> 등록하지 않는다 — 등록하지 않으면 최하위라 `user`를 이길 수 없고, 애초에 이 이름으로는
> 우선순위 계산에 도달할 경로가 없다.

### 쓰기 — 거부는 `virtual_only`에만, 깔때기 하나에서

정규화된 선언은 `expose`를 둘로 갈라 싣는다.

| | 무엇 | 쓰기 |
|---|---|---|
| `collide` | 왼쪽에도 **실재하는** 저장 컬럼 | **된다(의도적)** — 그 쓰기가 곧 위 표의 「왼쪽 값 있음」이고, **사용자가 조인 값을 고치는 유일한 방법**이다 |
| `virtual_only` | 조인만이 만들어 내는 컬럼 | **거부**(400) — 왼쪽에 그 컬럼이 실재하지 않으므로 저장할 곳이 없다 |

거부는 `crud.apply_batch_updates`의 **첫 문장** 한 곳이다(호출부마다 검사하지 않는다).
편집·붙여넣기·Push·인제션·체인·enrichment·재생이 전부 그 함수로 수렴하므로 **새 호출부가
검사를 잊을 자리가 없다.** 트랜잭션을 열기 **전**이고 `replace_map` 소거보다 **앞**이라,
거부가 반쯤 적용된 트랜잭션이나 「거절당하러 가는 길에 행을 지운 페이로드」를 남기지 않는다.

> 🔴 **막지 않으면 조용히 사라진다.** 없는 컬럼을 겨냥한 쓰기는 기존 미선언 컬럼 게이트가
> **드롭하고 200을 낸다** — 화면은 조인 값으로 다시 그려지고 사용자의 편집만 이유 없이
> 증발한다. 드롭 자체는 늘 옳았고, 결함은 침묵이었다.

## 4-ter. expose 컬럼의 타입 — 라벨이 문자열이므로 **전부** 텍스트로 렌더된다 (2026-08-04, N7 + N8)

`expose`에 어떤 타입의 컬럼이든 놓을 수 있다. 다만 라벨(`미상`)이 문자열이므로 **해석식 전체는
텍스트 식**이고, 텍스트가 아닌 컬럼은 COALESCE에 앉기 전에 텍스트로 렌더된다.

🔴 **판정은 「이미 텍스트인가」이지 「우리가 아는 문제 타입인가」가 아니다.** 처음에는 숫자만
접었고(N7), 그래서 **timestamp·boolean expose 컬럼이 같은 방식으로 500을 냈다**(N8) — 목록에
없던 타입은 전부 같은 결함을 물려받는다. 지금 깔때기는 `crud.column_text_sql` **하나**이고
모델의 SQLAlchemy 타입으로 갈린다(`table_config`의 선언이 아니라 **모델**을 읽는다):

| 타입 | 렌더러 | 나오는 철자 |
|---|---|---|
| `Numeric`·`Float`·`Integer` | `crud.numeric_text_sql` | 정수값이면 **INT 철자**(`3.0` → `3`), 소수부가 있으면 그대로(`2.5`) |
| `Boolean` | `crud.boolean_text_sql` | **`true` / `false`**(파이썬의 `True`가 아니다). 🔴 **NULL 분기가 먼저**다 — 없으면 짝 없는 행이 전부 `false`라는 **값**이 되어 `미상`으로 접히지 않는다 |
| `DateTime`·`Date`·`Time` | `crud.temporal_text_sql` | **UTC · 공백 구분 · 마이크로초 항상 6자리**(`1999-01-02 03:04:05.000000`) |
| `String`(단 `Enum` 제외) | `blank_to_null` | 그대로(§4의 빈 문자열 처리만) |
| 그 밖 · 미지의 타입 | `cast(..., String)` 후 `blank_to_null` | **먼저 캐스트한다** — 빈 값 술어의 「텍스트 타입」 전제가 모든 방언에서 서도록 |

### 시각 컬럼의 철자를 방언에 맡기지 않는 이유

`TEMPORAL_TEXT_FORMAT`(파이썬 `"%Y-%m-%d %H:%M:%S.%f"` / PostgreSQL
`"YYYY-MM-DD HH24:MI:SS.US"`)은 **못박은 것이지 기본값이 아니다.** 실측(PostgreSQL 18.3,
2026-08-04): `CAST(timestamptz AS varchar)`는 **세션의 `TimeZone` GUC를 따라**
`…+09` 같은 오프셋을 붙이고, **소수부가 0이면 아예 떨어뜨린다**. 두 성질 모두 움직이는
과녁이라(오프셋은 서버 설정을, 폭은 값을 따라간다) 그 위에 세운 텍스트 비교는 **같은 행을 든
두 서버가 다른 답**을 낸다. 고정폭은 덤도 하나 준다 — **사전순 = 시간순**이라, 해석된 시각
컬럼에 `lessThan`을 걸어도 거짓말이 아니다.

### 숫자 철자의 계약

- **정수값 float은 INT 철자** — 저장값 `3.0`의 비교 텍스트는 `3`이다(사용자 판정 2026-08-02:
  slot은 3으로 와야지 3.0이면 안 된다). 소수부가 있으면 그대로(`2.5` → `2.5`).
- **화면·검색·필터·CSV가 같은 철자를 쓴다.** 페이로드는 원시 숫자를 싣고 화면이 `3`으로
  접으며(`clean_str_value`와 같은 규칙), 검색/필터/CSV의 SQL 철자도 `3`이다 — 두 철자의
  일치는 `contracts/blank_predicate`의 `test_the_two_resolutions_agree_on_a_numeric_column`이
  채점한다(PostgreSQL은 `cast`가 우연히 `3`을 주지만 SQLite는 `3.0`을 주므로, 방언에 기대지
  않고 식 자체가 INT 철자를 만든다).
- **숫자의 「비었음」은 NULL 하나다.** 숫자는 `''`일 수 없으므로 §4의 ②(빈 문자열)는 숫자
  컬럼에 존재하지 않는다 — NULL이면 `미상`, 0은 **값이다**(0이 `미상`이 되면 결함).
- 한계: |값| ≥ 9.2×10¹⁸(BIGINT 상한 근처)이면 INT 접기를 포기하고 방언의 기본 캐스트로
  떨어진다 — 지수 표기가 나올 수 있으나, 실측된 어떤 운영 컬럼도 그 규모에 닿지 않는다
  (`FLOAT_EXPONENT` 선언 발산과 같은 도달 범위).

> 이 수정 전에는 숫자 expose 컬럼을 조회하는 **모든 읽기가 PostgreSQL에서 500**이었다
> (`double precision = ''` + `COALESCE(double precision, text)` — 둘 다 타입 오류,
> 2026-08-02 사용자 보고). 출하 당시 「이 환경에 숫자 expose 컬럼 0개」라 어떤 그물도
> 빨개지지 않았고, 지금은 `server/tests/test_virtual_join_numeric.py`가 그 축을 상시
> 활성화한다.

## 5. 키 사전

| 키 | 필수 | 뜻 |
|---|---|---|
| `left_table` | ✅ | 왼쪽(구동) 테이블. `table_config`에 등록돼 있어야 한다 |
| `right_table` | ✅ | 오른쪽(참조) 테이블. 조인 키를 덮는 UNIQUE 인덱스 필요(§2) |
| `join_key` | ✅ | `{left, right}` 쌍의 목록. 같은 `right` 컬럼을 두 번 묶을 수 없다(키가 넓어 보이지만 고정하는 성분은 하나다) |
| `expose` | ✅ | 왼쪽에 붙여 보여줄 오른쪽 컬럼들. **왼쪽에 같은 이름이 있어도 된다** — 거부가 아니라 §4-bis의 「부재일 때만 채운다」로 합쳐지고, 셀마다 출처가 실린다. 상한 32개 |
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

- **`expose`가 왼쪽 컬럼과 겹치는 것은 정상이며 기대되는 경우다**(2026-07-31 `d70a33d`에서
  거부 해제). 겹치면 §4-bis의 「부재일 때만 채운다」가 돌고, 셀마다 출처가 실려 어느 쪽 값을
  보고 있는지 읽을 수 있다. 🔴 **그 두 가지가 이 완화의 조건이다** — 하나라도 빼면 거부를
  되살려야 한다.
- **선언을 고쳤는데 안 먹으면 캐시를 의심하기 전에 승인부터 보라.** 승인된 선언은 웹서버에서
  짧은 TTL 캐시로 들고 있고 `POST /admin/reload-configs`가 즉시 무효화한다. 워커 프로세스는
  그 훅이 없어 TTL이 지나야 바뀐다.
- **선언을 읽지 못하면 「조인 없음」으로 간다.** 붙지 않은 컬럼은 눈에 보이는 부재이고,
  잘못 붙은 컬럼은 조용한 오답이기 때문이다. 조인이 통째로 안 보이면 서버 로그의
  `[VirtualJoin]`을 먼저 본다 — 그리드는 죽지 않는다.
- **`expose`한 이름이 왼쪽의 *시스템* 컬럼과 같으면 그리드에 뜨지 않는다** — `created_at`처럼
  config가 선언하지 않았는데 스키마 응답이 무조건 붙이는 꼬리가 있고, 라우트가 최종 컬럼
  목록과 대조해 **이미 있는 이름은 알리지 않는다.** 거부가 아니라 **알림에서만 빠지는 것**이고,
  값은 그 저장 컬럼의 것이 보인다. 조인 값을 보려면 다른 이름으로 노출하라.
- **가상 컬럼은 CSV 추출에 없다** — §9. 보고서를 만들 재료로 쓰지 말 것.
- **밑줄로 시작하는 키는 선언이 아니라 주석이다**(`_comment` 등) — 조용히 건너뛴다.
- **파일 부재는 거부가 아니다.** 선언이 없을 뿐이며 `sources[].exists: false`로 나온다.
- **PostgreSQL이 아니면 전부 거부된다.** 카탈로그를 읽을 수 없으면 유일성을 모르고,
  모르면 통과시키지 않는다.

## 9. 아직 열려 있는 것 (`4b50135` 시점)

**이 절이 미해결 항목의 단독 소유자다.** 다른 문서는 여기를 링크한다.

> 🔴 **항목이 해소되면 함께 걷어야 하는 곳은 셋이다** — 이 절 · [CONFIG_GUIDE §1](../CONFIG_GUIDE.md)의
> `virtual_join_rules.json` 행 ⏳ · [FEATURE_CHECKLIST](../../qa/FEATURE_CHECKLIST.md) §1.1 행과
> §2.2-bis 서두. **목록은 여기에만 둔다** — 두 곳에 적으면 반드시 갈린다(직전 라운드 실증).

✅ **해소 (2026-07-31 `9200f20`+`4b50135`): `virtual_only` 컬럼이 그리드에 뜬다.**
`/schema`가 `virtual_columns` 키로 알리고(**`columns`에 합치지 않는다**) 그리드가 저장 컬럼 뒤에
덧붙여 그린다. 헤더는 `🔗`, 색은 시스템 컬럼과 같은 회색, 툴팁이 오른쪽 테이블과 선언
이름을 말한다. 🔴 **읽기 전용을 지키는 것은 여전히 `crud.refuse_virtual_join_columns`
하나**이고, 클라의 `editable: false`와 `isVirtualColumn` 술어는 **되돌아올 400을 제안하지
않기 위한 것**이다. 계약은 [architecture/backend §2.2](../../architecture/backend.md) ·
[architecture/frontend §3.4](../../architecture/frontend.md).

✅ **해소 (2026-07-31 `cd3e0f4`): 검색·필터·CSV가 화면과 같은 값을 본다.** 해석값이 SQL
표현식(`resolved_expression`)이 되어 검색과 컬럼 필터가 DB로 내려가고(`미상` 행은
`equals 미상`으로 찾는다 — Blank/NotBlank는 해석값이 결코 빈 값이 아니므로 그 컬럼에서
제거됐다), `GET /tables/{t}/export`가 같은 표현식을 SELECT에 실어 **화면에 보이는 컬럼이
추출물에도 같은 값으로 있다**(15,504행 대조 0 불일치). `/schema`는 `join_resolved_columns`
키로 「이 컬럼의 값은 조인이 해석한다」를 collide까지 포함해 알린다.

✅ **해소 (2026-08-04, N7): 숫자 expose 컬럼.** 위 표현식이 숫자 컬럼에서 PostgreSQL 타입
오류로 죽던 것을 §4-ter의 INT 철자 렌더로 고쳤다 — 검색·필터·CSV·화면이 같은 철자(`3`,
`2.5`, `미상`)를 쓴다.

여전히 열려 있는 것:

- ⏳ **사용자가 일부러 비운 셀은 조인 값을 보여 준다.** 「비었음」의 정의가 `clean_str_value`
  하나이므로 「원래 비어 있음」과 「사람이 지워서 비어 있음」이 구별되지 않는다. 사용자는
  **비운 것은 빈 것이 맞다**고 판정했고, 그래서 이것은 결함이 아니라 **기록된 성질**이다.
  다만 뒤집으려면 셀 단위 「사람이 지웠음」 표식이 필요하므로 여기 남긴다.
