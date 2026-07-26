# 정렬 일원화 — `wafer_map_metadata` 단일 근거화 + `bonding_plan` 변환 사본 삭제

**일자:** 2026-07-27 · **담당:** Server PM · **보드:** #20 · **관련 스펙:** [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md)

## 현상

좌표 변환 구현이 셋이었다.

| 위치 | 상태 |
|---|---|
| `client2/src/map_editor.js` | 정본(렌더). A1 수정 반영, 화면에 그려지는 것 |
| `server/map_overlay.py` (`make_frame_transform` 등) | A1 수정 반영·정확하나 **운영 소비자 0** — 엔드포인트와 자기 테스트뿐 |
| `server/bonding_plan.py` (`make_align_transform`) | **자체 사본.** A1 수정이 전파되지 않아 bbox 항 없는 구 산술 |

즉 **맞는 구현은 안 돌고, 도는 구현이 안 고쳐진 쪽**이었다. 게다가 `server/transfer_plan.py`가
같은 사본을 3번째 소비자로 쓰고 있었다(가용량 산출의 실제 라이브 경로).

## 근본 원인

정렬의 근거가 **둘**이었다 — 맵 자신의 `wafer_map_metadata`와, config의 `align` 선언
(`map_overlay_config.align_overrides`, `bonding_plan_config.sources[].align`,
`transfer_plan_config.…fail_sources[].align`). 선언 레이어가 있으니 그것을 해석하는 파서와
변환기가 따로 필요했고, 그 사본이 `bonding_plan`에 살아남았다.

### "휴면"이 아니었다

착수 전제는 "라이브 `align` 선언이 없어 사본은 휴면"이었으나 **거짓**이었다. 실측:

- `server/config/bonding_plan_config.json` → `sources.eds_fail.align = {default:{rotation:180}}`
- `server/config/transfer_plan_config.json` → `stages.bonding.source.fail_sources.eds_fail.align` 동일

두 선언 모두 `eds_fail_map`을 가리키는데, **그 맵의 메타가 이미 `rotation: 180`을 선언**하고
있었다(라이브 `wafer_map_metadata` 읽기 전용 조회로 확인). 선언은 메타의 중복이었다.
휴면이었던 것은 `map_overlay_config.align_overrides` 하나뿐이다(키가 `__example_` 접두라
어떤 테이블에도 매칭되지 않음).

## 해결

**정렬의 유일한 근거 = `wafer_map_metadata`.** 소스·타깃 메타의 델타에서 변환을 유도한다.

- `bonding_plan`: `normalize_align` · `make_align_transform` · `align_status_label` ·
  `VALID_ROTATIONS` · `VALID_FLIPS` **삭제**. `align_status_label`은 변환 소유 모듈인
  `map_overlay`로 **이관**(삭제 아님).
- `map_overlay`: `align_overrides` 해석 · `by_eqp` 분기 · `ALIGN_ORIGIN_DECLARED/DEFAULT` ·
  `_frame_grid_of`(선언 경로 전용) 삭제. 단일 진입점 `resolve_map_transform` 신설 —
  오버레이와 가용량이 같은 함수를 쓴다.
- `transfer_plan`: `_canonical_origin_grid` → `_canonical_origin_meta`(격자가 아니라 메타 전체),
  `_canonical_fail_set`이 `resolve_map_transform` 경유.
- 클라: `probeAlignDeclaration`과 `align_override_declared`/`align_unconfirmed` 거절 경로 삭제
  (리뷰 B3를 수리가 아니라 **삭제**로 해소). 오버레이 추가의 REST 왕복이 하나 줄었다.
- `.sample` config 3종에서 `align_overrides` / `sources[].align` / `fail_sources[].align` 제거
  + `__comment`에 폐기 사유 명시. **라이브 `server/config/*.json`은 미수정**(사용자 자산).

### canonical 프레임 선택 규율 (신설)

```
canonical = 좌표를 바인딩한 **첫** 역할의 메타 (bonding_plan: total_chips → defect → eds_fail)
            그 역할에 메타가 없으면 canonical은 None — **뒤 역할로 넘어가지 않는다**
```

넘어가면 회전된 계측 맵이 스스로 기준을 참칭한다(소스 == 기준 → identity). 그러면 상태는
`connected`인 채 fail 투영이 통째로 빠지는 **조용한 과소 집계**가 된다.

그리고 **비대칭 지식 거절**: 소스 메타는 있는데 canonical 메타가 없으면 `align_unavailable`.
둘 다 없으면 identity(등록 누락은 실패가 아니다)지만, 한쪽만 알 때 identity를 가정할 근거는
없다.

```python
# server/bonding_plan.py — get_core_summary
if src_meta is not None and canonical_meta is None:
    align_ok = False          # -> "connected(align_unavailable)"
else:
    transform, align, _origin, _note = map_overlay.resolve_map_transform(src_meta, canonical_meta)
```

## 검증

**① 두 구현의 대조 (전 셀 실측)**

| 규격 | bbox(minC,maxC,minR,maxR) | 구 사본 vs 신 변환 |
|---|---|---|
| 라이브 40×40 · chip 7×7 · dia 300 · margin 3 | (0, 39, 0, 39) | **1288/1288 일치** |
| 29×25 · chip 11×13 · dia 300 · margin 3 (rot180) | (2, 26, 2, 22) | **425/425 불일치**, 편차 일정 (4,4) = `2·minC` |
| 같은 규격 rot270+back | (2, 22, 2, 26) | 일치 — 합성 선형부가 +1이라 bbox 항이 상쇄 |

라이브 규격은 웨이퍼 원이 격자를 자르지 않아 bbox가 0이고, 그래서 구 사본이 빠뜨린 항이
**우연히 0**이었다. 정확한 쪽은 `map_overlay`다 — 저장 좌표는 `xv = c - box.minC + start_x`
(웨이퍼 원으로 자른 바운딩박스 상대값)이고, 이 항을 빼면 거울 변환에서 두 항이 상쇄되지 않고
가산된다.

**② 가용량 before/after (격리 sqlite · 라이브 규격 복제)** — 8개 조회 중 7개 완전 동일,
1개 변경:

```
core-summary-region-half:CROP   eds_fail  6 -> 7   (remaining 240 -> 239)
```

독립 정답지로 재확인: 시딩한 fail 다이의 canonical 좌표는 (8,3)…(8,9) 7개이며 전부 y ≤ 12.
구 사본은 이들을 (12,7)…(12,13)으로 되돌려 **7개 전부 다른 다이**에 얹었고, 그중 하나가
y=13으로 밀려 경계 밖으로 떨어졌다 → 6. **7이 옳다.**
주의할 점: 같은 CROP 케이스의 **총 개수는 7로 before/after 동일**했다 — 균일 이동이 모든
다이를 다른 유효 다이로 옮겼기 때문이다. 개수만 보는 검증은 이 결함을 원리적으로 못 잡는다.

**③ 결함 주입 (4종) — 전부 검출**

| 주입 | 실패 테스트 수 |
|---|---|
| `bbox_less` (bbox 항 제거 = 구 사본의 산술) | 13 (bonding_plan 3 + map_overlay 10) |
| `wrong_bbox_source` (소스 bbox를 타깃 것으로) | 39 |
| `canonical_lost` (`CANONICAL_FRAME_ROLES = ()`) | 12 |
| `tp_canonical_lost` (`dst_meta = None`) | 18 |

주입은 소스 백업/복원을 **바이트 단위 sha256 대조**로 수행했다(`git checkout --`는 다른
에이전트의 미커밋 작업이 같은 파일에 있어 사용 불가).

> ⚠️ **1차 시도는 헛돌았다.** 처음 쓴 `bonding_plan` 픽스처는 좌표 대응을
> `make_frame_transform`(검증 대상)으로 만들어서, `bbox_less` 주입에도 20건이 **전건 통과**
> 했다 — 시드와 복원이 같은 함수라 상쇄됐다. 픽스처를 `test_map_overlay`의 **독립 정답지**로
> 바꾼 뒤에야 실패했다.

**④ 픽스처의 결함 축** — `test_bonding_plan.CROP_GRID` = 11×9 · chip 11×13 · dia 100 ·
margin 3 · offset (4, 2). 테스트 자신이 축 활성화를 단언한다: `bbox != 0`, `minC != minR`
(1 vs 2 — 축 혼동을 잡기 위해), `chip_x != chip_y`, front/back의 bbox가 실제로 다름
(offset 부호 반전 항이 관측 가능). rot 0/back · 90 · 180 · 270/back 4조합 parametrize.

**⑤ 스위트** — `427 passed / 0 failed` (기준선 414 + 신규 13).

## 남은 것

- `GET /api/maps/overlay`의 `eqp` 쿼리 파라미터는 **no-op으로 존치**했다. `by_eqp` 전용
  파라미터였으나 REST 시그니처 축소는 경계 계약이라 총괄 승인 사항.
- 사용자 라이브 config 3종에 폐기 키가 남아 있다(서버는 무시하나 혼동 유발) — 제거 권고는
  보고서 참조.
