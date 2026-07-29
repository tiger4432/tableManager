# 유효 다이도 맵이다 — `valid_die_ref` 서버 절반 (M4 phase 1)

> 2026-07-29 10:15 · 도메인 Server(맵 인프라 · 정체성 캐노니컬화 · 계기 진단)
> 상위: [MAP_EDITOR_SPEC §5.7](../spec/MAP_EDITOR_SPEC.md) · 필드 규격 [architecture_and_management §2.3-bis](../map_editor/architecture_and_management.md) · 보드 [PROJECT_STATUS 8.5](../process/PROJECT_STATUS.md)
> 선행: [7b 맵 정체성 캐노니컬화 + M3 인제션 메타 자동 등록](./20260729_014707_core_value_1_instrument_replaced.md) 대(對) `ab6ac02`
> 동반: 클라 절반(map-pm) · 계약 채점(`contracts/map_seam/`)

## 배경 — 원으로 그릴 수 없는 유효 다이는 표현할 자리가 없었다

지금까지 "어느 칸이 실물 다이인가"는 **원 기하가 판정**했다(`phys_wafer_dia`·`chip_x/y`·
`offset`·`edge_margin` → `is_cell_inside_wafer`). 그런데 실제 dt 맵은 **테이프 위**에 있고
300mm 제약이 없다. 원으로 표현할 수 없는 형상은 **저장할 자리 자체가 없었다** — 그래서
현장은 마스크 트릭으로 우회했고, 그 우회가 결함 계급 #11·#18·#20의 뿌리였다.

M4는 원을 **판정자에서 생성기로 강등**한다. phase 1은 그 첫 걸음이고 **소비만** 한다:
프리셋=템플릿 생성기(phase 2)와 `inside`에서 원 은퇴 + 기존 메타 이관(phase 3)은 별개 라운드다.

## 구현 — 새 기하식은 한 줄도 쓰지 않았다

선언은 `wafer_map_metadata.grid_metadata`에 얹는 **가산 필드 하나**다. 컬럼 추가가 아니라
JSON 페이로드의 키라서 마이그레이션 순서 의존이 없다(server-pm 교훈 #66의 회피).

```jsonc
"valid_die_ref": {"table": "dt_map", "map_id": "TPL_1"}   // 또는 "TPL_1" (테이블 승계)
```

해석은 **이미 있는 프리미티브만 순서대로** 쓴다 — 오버레이가 하는 일과 구조적으로 같은
연산이고, 다른 점은 결과를 그리지 않고 마스크로 쓴다는 것뿐이다.

```
resolve_binding(§5.6-bis)  →  canonical_map_key(7b)  →  load_map_meta(§5.0)
                           →  resolve_map_transform(§5.2의 단일 변환기)  →  셀 집합
```

판정 근거가 갈리는 지점은 **한 함수**다(계약 심볼):

```python
map_overlay.resolve_valid_die_basis(meta, resolver) -> {basis, source, reason}
#   source == "circle"   선언 없음 → 2a9f6c4 그대로
#   source == "ref"      참조가 답의 전부 (원과 교집합하지 않는다)
#   source == "refused"  풀지 못했다 → basis None + 사유 (원으로 되돌아가지 않는다)
```

## 이 라운드가 막은 조용한 오답 다섯

**① 교집합의 유혹.** 참조 집합을 원과 `&` 하면 보수적으로 보인다 — 그러나 템플릿이 유효라고
선언한 다이를 **소리 없이 떨어뜨린다**. 계약 벡터가 이것을 직접 겨냥하고(`ref_present_supersedes_circle`),
테스트는 매번 `resolved != circle_mask`를 단언해 결함 축이 살아 있음을 증명한다.

**② 오타 하나가 원으로 되돌아가는 길.** `null`/부재만 "선언 없음"이고 **그 밖은 전부 선언**이다.
읽을 수 없는 선언을 "선언 없음"으로 접으면 오타가 조용히 원 기하로 강등된다 — 틀린 답과
맞은 답이 구별되지 않는 바로 그 상태다.

**③ 셀 0건을 "유효 다이 0개"로 읽기.** 거의 언제나 "아직 적재되지 않았다"이고, 0건을 답으로
삼으면 **그 맵 전체가 무효**가 된다. 거절로 처리한다.

**④ 비대칭 프레임의 identity 가정.** 선언은 메타 안에 사니 **선언한 맵의 프레임은 언제나 안다.**
참조 맵 규격만 미등록인 비대칭에서 identity를 가정하면 180° 돌아간 템플릿을 무보정으로
받아들인다(`bonding_plan`의 canonical 프레임 규율과 같은 판단).

**⑤ 절단된 마스크.** 상한 초과 시 **자르지 않고 거절**한다. 잘린 유효 다이 집합은
"맞아 보이는 틀린 집합"이고, 그 차이는 화면에 나타나지 않는다.

## 7b가 남긴 마지막 구멍 — 조립된 키 문자열

`compose_map_id`는 **조각으로부터** 키를 만들 때 캐노니컬화한다. 그런데 `valid_die_ref`는
**이미 조립된 문자열**로 온다. 셀 필터는 `build_key_filters`가 컬럼 타입으로 캐스팅해
살아남지만, `load_map_meta`는 `map_id` **문자열 정확 일치**라 조용히 빗나갔다 —
`LOT_01` 선언이 셀은 찾고 규격은 못 찾아 `align_unavailable`로 거절되는 증상으로 드러났다.

```python
map_overlay.canonical_map_key(table, binding, map_key)   # 신설
```

**두 번째 정규화가 아니다.** 분해는 `map_key_parts`(신설 — `build_key_filters`에서 추출해
**공유**), 값 정규화는 기존 `canonical_bind_value` → `canonical_key_value`다. 분해 규칙이
갈라지면 같은 선언이 셀은 찾고 메타는 못 찾는 상태가 조용히 생기므로 한 함수로 모았다.

회귀는 **뮤테이션 쌍둥이**로 증명한다(`test_key_canonicalization.py`의 그 패턴): 캐노니컬화를
raw `str()`로 퇴화시키면 같은 선언이 **해석되지 않아야** 한다. 이것이 없으면 두 번째
정규화를 몰래 들여도 테스트가 통과한다.

## 함께 고친 것 — 재교정률 진단의 쌍둥이

`main._get_recorrection_stat`이 **모든 실패 모드에** 대해 고정 문구
`"집계 시간 초과 또는 실패 (idx_audit_user_recorrection 인덱스 확인)"`를 돌려줬다. 컬럼 누락
같은 사고가 **인덱스 문제로 읽히고 당직자가 애초에 원인이 아닌 인덱스를 손보러 간다.**
같은 날 아침 `_get_effort_stat`에서 고친 결함(A-F6)의 쌍둥이이며, 그때 범위 밖으로 남았던
것을 이번에 닫았다. 이제 타임아웃일 때만 시간 초과 + 인덱스를 말하고, 그 외에는
`집계 실패 — [예외타입] 첫 줄`을 싣는다.

## 검증

- `server/tests/test_valid_die_ref.py` **43건 신설** — 착수 시 26건 실패(구현 전), 구현 후 전건 통과.
  INV-M4-1(가산적 공존·`frame_axes` 불변·오버레이 출력 동일) / INV-M4-2(원과 불일치 단언 포함) /
  INV-M4-3(거절 9종 + `cells` 키 부재) / INV-M4-4(뮤테이션 쌍둥이).
- `contracts/map_seam/` **`valid_die_basis_cases` 4건 전건 통과** — INV-M4-1의 기대값은 서술이
  아니라 `2a9f6c4`에서 **실측된** 마스크(`mask_baseline_cases.r7_sym_rot0`)와의 대조다.
- 픽스처 결함 축 확인: 6×6 격자 + chip 60mm로 원이 **실제로 자른다**(36칸 중 12칸, bbox
  `minC/minR = 1`). 40×40(`minC=0`)이면 결함이 원리적으로 발현할 수 없다(§5.3 회귀 규율).
- 전체 스위트: 기준선 **1005 passed**(`2a9f6c4`) → **1050 passed**(신설 43 + 재교정률 진단 2).

## 남긴 것

- **새 REST 경로는 추가하지 않았다.** 클라 half가 이미 있는 셋(`/tables/{t}/data` + paint-rules
  `binding` + `/schema`)으로 참조를 풀고 있어 소비자가 없고, REST 시그니처는 총괄 승인이 필요한
  경계 계약이다. 서버측 해석기는 모듈 함수 `resolve_valid_die_set`으로 존재하며 phase 2/3가 쓴다.
- 참조 셀 조회는 맵 키 컬럼 필터다 — 오버레이와 **같은 쿼리 형태**라 인덱싱 사정도 같다.
  참조 1건당 조회 1회(작업 단위 캐시)이고 셀 단위로 떨어지는 경로는 없다.
