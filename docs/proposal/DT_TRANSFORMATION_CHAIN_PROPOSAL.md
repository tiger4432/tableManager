# DT–Core 표준 좌표 변환 체인 제안

> **Status:** Proposal | **작성:** 2026-08-08 | **Owner:** Lead PM
> **결정 전제:** `dt_log`의 원본 좌표는 DT의 `(b_wx,b_wy)`와 core의 `(c_wx,c_wy)`다. 정렬 확정은 각각을 표준 좌표로 바꿀 근거를 만들며, 원본 행을 바꾸는 권한은 주지 않는다.

---

## 1. 목적과 비목적

목적은 확정된 정렬 메타를 **다른 시스템도 계산할 수 있는 선언형 식**으로 내보내는 것이다. 즉, 소비자는 회전·면·start·격자 크기를 다시 조합하지 않고 한 행의 selector/sign/offset만으로 좌표를 계산한다.

이 체인은 다음을 하지 않는다.

- `dt_log`의 원본 `dt_x/dt_y` 또는 `core_x/core_y`를 덮어쓰지 않는다.
- `dt_log`의 원본 좌표를 바꾸지 않는다. `dt_map`은 원본이 아니라 `dt_log`로부터 언제든 다시 만들 수 있는 파생뷰다.
- 일반 체인의 upsert를 `replace_map`으로 오인하지 않는다. 재확정 뒤 `dt_map`을 다시 만들 때는 구버전 셀을 job 단위로 지우고 다시 쓰는 전용 재투영 경로가 필요하다.

## 2. 원본 컬럼과 명시적 좌표식

`dt_log`의 좌표·출신 계약은 다음으로 고정한다.

```text
dt_job_id, b_wx, b_wy,
core_lot, core_slot, core_wafer_id, c_wx, c_wy, c_bn
```

`core_wafer_id`는 enrichment 대상이며, `c_bn`은 core die의 bin이다. `b_wx/b_wy`와 `c_wx/c_wy`는 원본 좌표이고, 아래의 prime 좌표가 변환 결과다.

```text
dt_x'   = select(dt_x_base,   b_wx, b_wy) * dt_x_sign   + dt_x_offset
dt_y'   = select(dt_y_base,   b_wx, b_wy) * dt_y_sign   + dt_y_offset
core_x' = select(core_x_base, c_wx, c_wy) * core_x_sign + core_x_offset
core_y' = select(core_y_base, c_wx, c_wy) * core_y_sign + core_y_offset
```

`select('X', x, y)=x`, `select('Y', x, y)=y`다. 이 식은 **원본 → 표준** 식이며 역으로 풀지 않는다.

### 유효다이 영역 메타에서 `x,y → x',y'`를 얻는 식

아래 식은 한 맵의 raw 좌표 `(x,y)`에 적용한다. DT에는 `(b_wx,b_wy)`와 DT 메타를, core에는 `(c_wx,c_wy)`와 해당 core map 메타를 각각 넣는다.

`C=Ncols`, `R=Nrows`라 하고, `Ncols/Nrows`는 유효다이 영역 bounding box의 폭·높이다. 즉 canonical cell 좌표는 `0≤X<C`, `0≤Y<R`이며 표준 저장좌표는 시작점 `(1,1)`을 쓴다.

먼저 원본 frame의 0-based 좌표를 구한다.

```text
Vcols,Vrows = (C,R)                 if rot in {0,180}
              (R,C)                 if rot in {90,270}

U = x - start_x
V = y - start_y                     if y_invert = false
    (Vrows - 1) - (y - start_y)     if y_invert = true
```

입력은 반드시 `0≤U<Vcols`, `0≤V<Vrows`를 만족해야 한다. 아닐 경우 그 메타 아래의 좌표가 아니므로 변환을 거절한다.

그 다음 `rot`, `side`에 따라 canonical 0-based 좌표 `(X,Y)`는 다음과 같다.

| side | rot | `X` | `Y` |
| --- | ---: | --- | --- |
| front | 0 | `U` | `V` |
| front | 90 | `V` | `R - 1 - U` |
| front | 180 | `C - 1 - U` | `R - 1 - V` |
| front | 270 | `C - 1 - V` | `U` |
| back | 0 | `C - 1 - U` | `V` |
| back | 90 | `C - 1 - V` | `R - 1 - U` |
| back | 180 | `U` | `R - 1 - V` |
| back | 270 | `V` | `U` |

마지막으로 표준 `dt_map` 저장 좌표는 다음처럼 고정한다.

```text
x' = X + 1
y' = Y + 1
```

표의 각 행은 selector/sign/offset 네 개로 압축되며, `start_x/start_y`와 `y_invert` 항도 최종 offset/sign에 **반드시 접어 넣는다**. 예를 들어 **`front/90`, `start=(1,1)`, `y_invert=false`일 때만** `x'=b_wy`, `y'=-b_wx+R+1`이므로 DT 식은 `dt_x_base='Y', dt_x_sign=1, dt_x_offset=0`, `dt_y_base='X', dt_y_sign=-1, dt_y_offset=R+1`이다. 다른 start 또는 y반전에서 이 네 값은 달라진다.

### 표준 좌표계의 고정 메타

`dt_map`에 쓰는 표준 좌표계는 사용자 확정값으로 고정한다.

```text
rotation = 0
side = front
start_x = 1
start_y = 1
grid_y_invert = false
```

격자 크기와 물리 규격은 좌표축이 아니라 해당 DT map의 기하 메타이므로, 확정이 근거로 삼은 메타에서 가져온다. 이 다섯 축을 매번 원본 맵에서 복사하면 표준이라는 말이 거짓이 된다.

## 3. 왜 행의 단위가 단순히 설비·제품이 아닌가

`eqp_frame_attribution`의 결정 단위 `(dt_eqp, product)`는 **방위**를 확정한다. 그러나 offset은 각 맵의 `start_x/start_y`, 회전 뒤의 축 길이, `grid_y_invert` 등 실제 메타에서 나온다. 한 DT job이 여러 core wafer를 담을 수 있으므로 core 쪽은 특히 맵마다 달라질 수 있다.

따라서 한 변환 행은 다음 다섯 사실을 함께 고정한다.

```text
확정 버전(confirmation_uid)
× DT 맵(table, map_id)
× core 맵(table, map_id)
```

동일 확정 아래 DT 맵 하나가 여러 core 맵에 연결되면 core 맵마다 행 하나가 생긴다. DT 식이 중복되는 것은 오류가 아니라, 어느 core 맵과 비교한 식인지 이름으로 답하기 위한 비용이다.

## 4. 제안 테이블 — `dt_transformation`

동적 테이블로 신설한다. 모든 행은 체인이 만들며 사용자가 직접 편집하지 않는다.

| 컬럼 | 타입 | 의미 |
| --- | --- | --- |
| `transformation_key` | string | `confirmation_uid|dt_map_table|dt_map_id|core_map_table|core_map_id`; 행 정체성 |
| `confirmation_uid` | string | 이 식을 가능하게 한 불변 확정 버전 |
| `dt_eqp`, `product` | string | 확정의 결정 단위; 탐색·감사 편의 필드 |
| `dt_map_table`, `dt_map_id` | string | DT raw 좌표가 속한 맵 |
| `core_map_table`, `core_map_id` | string | core raw 좌표가 속한 맵 |
| `dt_x_base`, `dt_y_base`, `core_x_base`, `core_y_base` | string | `X` 또는 `Y` selector |
| `dt_x_sign`, `dt_y_sign`, `core_x_sign`, `core_y_sign` | number | `-1` 또는 `1` |
| `dt_x_offset`, `dt_y_offset`, `core_x_offset`, `core_y_offset` | number | 표준 기저에서 원본 좌표로 갈 때의 정수 이동 |
| `dt_frame`, `core_frame` | string | 사람이 확정한 원본 프레임; 식 해석의 감사용 |
| `generated_at` | datetime | 체인이 식을 생성한 시각 |

`confirmation_uid`를 상태값으로 업데이트하지 않는다. 재확정은 새 UID와 새 행을 낳는다. 이전 행은 당시 판단 아래의 계산 근거로 보존한다.

## 5. 체인과 산출물

### 5.1 트리거

트리거는 `eqp_frame_attribution`이 아니라 `frame_confirmation`이다. 작업대 값은 수정될 수 있지만 `frame_confirmation`만이 확정자·시간·근거·버전·supersession을 가진다.

```text
frame_confirmation (새 확정)
  → dt_transformation (맵 쌍별 선언형 식)
  → dt_standard_map (선택적, 원본 dt_log의 표준 좌표 투영)
```

`frame_confirmation.superseded_by IS NULL`인 UID만 현재 선택 대상으로 삼는다. 과거 확정의 변환 행·투영 행은 삭제하지 않는다.

### 5.2 재투영 대상 — 기존 `dt_map`

`dt_map`은 `dt_log`의 파생뷰이므로, 확정된 변환을 적용한 표준 좌표 셀을 여기에 다시 만든다. `dt_map.dt_x/dt_y`는 이 시점부터 raw 좌표가 아니라 표준 좌표 `(b_wx, b_wy)`이고, raw 값은 아래 provenance 컬럼으로 보존한다.

| 컬럼 | 의미 |
| --- | --- |
| `cell_key` | `dt_job|b_wx|b_wy` — 표준 좌표로 만든 파생 셀의 정체성 |
| `confirmation_uid`, `transformation_key` | 어느 확정과 식이 만든 행인지 |
| `dt_job_id`, `b_wx`, `b_wy` | 원본 DT 셀 식별·추적 |
| `dt_x`, `dt_y` | DT 식으로 변환한 표준 좌표 `(dt_x',dt_y')` |
| `core_lot`, `core_slot`, `core_wafer_id`, `c_wx`, `c_wy` | 출신 core 추적 정보 |
| `core_x`, `core_y` | core 식으로 변환한 표준 좌표 `(core_x',core_y')` |
| `c_bn` | 기존 DT map이 보존하는 값 |

재확정은 같은 `(dt_eqp, product)`에 속한 각 `dt_job`의 기존 `dt_map` 파생 셀을 지우고, 그 job의 `dt_log`로부터 새 표준 셀을 넣는다. 한 job의 purge와 재삽입은 하나의 `replace_map` batch로 원자적이어야 한다. 현 `apply_batch_updates`는 내부 commit을 하므로 여러 job을 하나의 DB 트랜잭션으로 묶는다고 주장하지 않는다. job 사이 실패는 outbox 재시도로 다시 시도하며, 이미 끝난 job의 재실행도 같은 결과가 되어야 한다.

`core_x/core_y`를 함께 싣되 DT 표준 `(dt_x',dt_y')`와 core 표준 `(core_x',core_y')`가 항상 같다고 가정하지 않는다. 둘의 관계는 이후 전사·본딩 규칙이 판단할 일이다. 또한 DT에 오지 않은 core die는 이 투영에서 만들 수 없으므로, 이것을 core wafer 전체의 정본 맵으로 사용하지 않는다.

## 6. 계산 책임과 검증

변환 식은 `map_overlay.make_frame_transform` 계열이 실제로 쓰는 변환에서 **읽어내야** 한다. 회전 표를 mapper에 두 번째로 구현하거나, 문자열 `rot90_back`을 보고 selector/sign/offset을 손으로 만든다. 기존 정렬기의 규칙처럼 세 점 `(0,0)`, `(1,0)`, `(0,1)`을 변환해 선형부와 이동을 추출한다.

필수 테스트는 다음이다.

1. 8개 프레임 각각에서 DT와 core 식이 원 변환과 모든 셀에 대해 왕복 일치한다.
2. 비정방 격자, non-zero start, `grid_y_invert`, non-zero offset을 함께 넣는다.
3. 한 DT job에 여러 core wafer가 있는 입력에서 맵 쌍별 core 식이 섞이지 않는다.
4. 재확정 후 해당 job들의 `dt_map`은 새 `confirmation_uid`로 완전히 교체되고, `dt_log` 원본 행은 바이트 단위로 변하지 않는다.
5. `confirmed`가 아니거나 프레임·메타가 불완전하면 이름 붙여 거절하며 식 또는 투영을 만들지 않는다.

## 7. 단계 제안

1. `dt_transformation`을 먼저 만든다. 외부 소비자가 실제 식을 계산할 수 있는지 검증한다.
2. `dt_map` 스키마에 raw provenance와 `confirmation_uid`를 추가하고, 표준 메타(`front`, `0°`, `start=(1,1)`)를 기록한다.
3. `frame_confirmation` 트리거가 job 단위 전용 재투영을 실행하도록 만든다. 일반 upsert 체인은 이 단계에 쓰지 않는다.

이 순서는 표준 좌표 변환이라는 계약을 먼저 고정하고, 그 계약 아래의 `dt_map`만 원본 `dt_log`에서 결정적으로 다시 만들게 한다.

## 8. 체인 `replace_map` 확장 검토 (2026-08-08)

### 결론

**가능하다.** `GeneralUpdateBatch`는 이미 `replace_map: bool`과 명시 `scope`를 가지며, CRUD는 선언된 `map_key_columns` 안의 scope만 받아 purge 뒤 upsert한다. `dt_map`의 map key는 `dt_job`이므로 `{ "dt_job": "<job>" }`는 안전하게 한 DT map만 교체하는 scope다.

현 체인에서 안 되는 이유는 CRUD가 아니라 워커의 전달 경계다. `chain_ingestion_worker`는 mapper의 결과에서 `updates`만 모아 target table별 **한 배치**를 만들고, `replace_map`과 `scope`는 만들지 않는다. 그러므로 규칙 JSON에 단순히 `replace_map: true`를 추가해도 효과가 없다.

### 필요한 계약: mapper가 “업데이트 목록”이 아니라 “배치 목록”을 낸다

확정 하나는 여러 `dt_job`을 다시 만들 수 있고, 한 `GeneralUpdateBatch.scope`는 하나의 AND scope만 표현한다. 그래서 다음 형태가 필요하다.

```json
{
  "batches": [
    {
      "target_table": "dt_map",
      "replace_map": true,
      "scope": {"dt_job": "DT-EQP-01_20260808_01"},
      "updates": ["해당 job의 표준 좌표 셀들"]
    }
  ]
}
```

워커는 이 envelope를 읽어 기존 mapper의 `{ "updates": [...] }` 반환도 그대로 지원하고, batch마다 `GeneralUpdateBatch`를 만든다. `replace_map`은 mapper가 임의로 켜는 범용 권한이 아니라, chain rule의 `allow_replace_map: true`와 일치할 때만 허용한다. scope가 비었거나 target의 `map_key_columns` 밖이면 기존 CRUD 거절을 그대로 통과시킨다.

### 보장 범위와 비용

- **보장:** 한 `dt_job`의 purge와 재삽입은 기존 CRUD 경로의 한 batch 안에서 완료되거나 rollback된다.
- **보장하지 않는 것:** 하나의 frame confirmation이 건드리는 여러 job의 전역 원자성. 현 CRUD가 batch 안에서 commit하므로 이를 원하면 CRUD commit 책임 자체를 재설계해야 하며, 이 제안 범위를 넘는 고위험 변경이다.
- **재시도:** job별 replacement는 `dt_log`와 confirmation으로 결정적이므로, outbox 재시도는 같은 map을 같은 결과로 다시 만든다.
- **통지:** worker는 한 job replacement마다 셀 단위 이벤트를 폭발시키지 말고, 기존 table-level `batch_refresh_required` 경로로 합쳐야 한다.

### 구현 전 필수 테스트

1. 한 confirmation이 두 job을 재투영할 때 각 `dt_job` scope 밖 셀은 절대 삭제하지 않는다.
2. 한 job의 새 투영이 빈 경우에도 명시 scope로 옛 map만 완전히 비운다.
3. 두 번째 동일 confirmation 처리 결과가 첫 처리 결과와 동일하다.
4. 두 job 중 두 번째가 실패하면 첫 job은 완전한 새 map이고, 두 번째만 retry 대상임을 검증한다.
5. `allow_replace_map` 없는 규칙·비어 있는 scope·map-key 밖 scope는 모두 이름 붙여 거절한다.
