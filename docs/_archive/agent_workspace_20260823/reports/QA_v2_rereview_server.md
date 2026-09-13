# QA 재검수 A — 서버 좌표·데이터 무결성 (v2 NO-GO 수정 검증)

> **검수:** qa-reviewer / 2026-07-26 · 대상: 미커밋 워킹트리(`9dbcc1f` 위) · 코드 무수정
> **범위:** B1 수정 검증 / M4 / phys 규격 부재 처리 / 인덱스 3종 / 스위트 재현
> **제외(B 담당):** `client2/**` 전부, 토스트, 페인트 잠금 UI, prune·업서트 가드, 오버레이 가져오기 UI
> **스위트 재실행:** `409 passed / 1 failed(test_map_presets_api — allowed)` — **주장 그대로 재현됨**
> **라이브 시드:** **없음**(전 검증이 읽기 전용 SELECT + GET REST). 정리할 행 0건.

---

## 1. 판정

# 🔴 NO-GO (병합 차단 1건)

**근거 한 줄:** B1 수정이 **부분 수정**이다 — `_frame_transformer`가 웨이퍼 엔진을 **맵의 물리 규격 그대로** 만들어서, 클라가 회전 90/270 프레임에서 **칩 피치를 스왑**하는 규약(`getTransformedPhysicalConfig`)을 재현하지 못한다. 그 결과 라이브 rot270 맵 6건 전부의 바운딩박스가 저장 규약과 다르고, **라이브 순서쌍 84건이 여전히 `status: ok`인 채 좌표가 어긋난다.** 더 나쁜 것은 이 84건이 **구 코드에서는 `align_unavailable`(명시 실패)이었다**는 점이다 — 직전 NO-GO가 차단했던 바로 그 거래(*소리 나는 실패 → 조용한 오답*)가 축소된 규모로 재발했다.

M4·phys 규격 부재 처리·인덱스·스위트는 **전부 통과**했다. 차단은 A1 하나이며, 국소 수정(엔진 생성 파라미터 4줄)으로 닫힌다.

---

## 2. 확인된 결함

### 🔴 A1 [차단·심각도 높음] B1 부분 수정 — 회전 90/270 프레임의 바운딩박스가 클라 저장 규약과 불일치
`server/map_overlay.py:209-236` (`_frame_transformer`) · 규약 정본 `client2/src/map_editor.js:1105-1123` (`getTransformedPhysicalConfig`)

**원인.** 수정은 좌표 왕복을 `WaferMapCoordinateTransformer`에 위임해 옳은 방향으로 갔다. 그런데 그 변환기에 물려주는 웨이퍼 엔진을 **메타의 phys 값 그대로** 만든다:

```python
dia, chip_x, chip_y, off_x, off_y, margin = _phys_signature(meta)
engine = PhysicalWaferEngine(
    wafer_diameter_mm=dia, chip_size_x_mm=chip_x, chip_size_y_mm=chip_y,   # ← 스왑 없음
    edge_exclusion_mm=margin, offset_x_mm=off_x, offset_y_mm=off_y)        # ← back 부호 없음
```

클라는 **프레임 좌표계 기준**으로 규격을 변환한 뒤 마스크를 계산한다(`map_editor.js:1118-1123`, `:1114-1116`):
- `rotation ∈ (90,270)` → `chipX = origChipY`, `chipY = origChipX` (**칩 피치 스왑**)
- `side == 'back'` → `origOffsetX = -origOffsetX` (**오프셋 x 부호 반전**)

`get_wafer_bounding_box()`는 이 마스크를 격자 전체에 돌려 얻는 값이고, **이번 수정의 모든 좌표가 이 bbox에 의존한다.** 규격이 어긋나면 bbox가 어긋나고 전 셀이 어긋난다 — B1과 **동일한 결함이 한 계층 아래로 이동했을 뿐**이다.

**실측 1 — 라이브 11개 프레임 서명 중 4개에서 bbox 불일치** (클라 산술을 독립 이식한 오라클 vs 서버 변환기):

```
 29x25 rot270 front  chip 11/13   클라 (2,22,2,26)   서버 (0,24,4,24)   *** 불일치 ***
 29x25 rot270 back   chip 11/13   클라 (2,22,2,26)   서버 (0,24,4,24)   *** 불일치 ***
 29x25 rot270 back   chip 11/13 start(-10,-12)       동일 형태          *** 불일치 ***
 27x21 rot270 front  chip 12/16   클라 (2,18,2,24)   서버 (0,20,5,21)   *** 불일치 ***
 (나머지 7개 서명 = rot 0/180 또는 정방 칩 → MATCH)
```
서버 bbox는 **회전하지 않은 형태**(가로 25 / 세로 21)이고, 클라 bbox는 **회전한 형태**(가로 21 / 세로 25)다. 300mm 웨이퍼에서 화면 x축은 회전 후 칩의 **y피치**(13mm)를 쓰는 것이 맞다.

**실측 2 — 어느 쪽이 옳은지 라이브 저장 데이터가 결정한다(결정적 증거).**
bbox는 저장 좌표의 범위를 직접 규정한다(`xv = c - minC + start_x`). 라이브 rot270 맵의 실제 셀 좌표 범위:

| 맵 | 클라 bbox 예측 | 서버 bbox 예측 | **실제 저장값** | 판정 |
|---|---|---|---|---|
| `sample_map/aa123_a` (n=184) | x[1,21] y[1,25] | x[1,25] y[1,21] | **x[1,21] y[1,25]** | 클라 정확 일치 |
| `bonding_map/4B12` (n=177) | x[1,17] y[1,23] | x[1,21] y[1,17] | **x[1,17] y[1,23]** | 클라 정확 일치 |
| `test/QQ` (n=80) | x[1,21] y[1,25] | x[1,25] y[1,21] | **x[1,21] y[1,25]** | 클라 정확 일치 |
| `test/AAA` (n=44, 부분 도색) | ⊂ 예측 범위 | **y=23 > 서버 상한 21** | x[1,18] y[12,23] | 서버 예측 반증 |
| `bonding_map/QQ` (n=16, 부분) | ⊂ 예측 범위 | **y=9 > 서버 상한 8** | x[-9,6] y[-8,9] | 서버 예측 반증 |

즉 **저장된 실데이터가 서버 bbox를 반증한다.** 논쟁의 여지가 없다.

**실측 3 — 라이브 전수 재대조(독립 오라클, 서버 코드 미호출).**
`client2/src/map_editor.js`의 `getWaferBoundingBox`/`getVisualCoords`/`getCellFromVisualCoords`/`getPhysicalCoords`/`getCellFromPhysicalCoords`를 파이썬으로 **산술 그대로** 이식했다(`qaA_oracle.py`). 오라클 자체 검증: ①11개 라이브 서명 전부 자기 자신 쌍에서 항등 ②`align_unavailable` 총계 5,596이 구현자 보고와 **정확히 일치**(쌍 열거·가중이 같음을 교차 확인).

| OLD(`HEAD`) → NEW(워킹트리) | 서명쌍 | 라이브 가중 |
|---|---|---|
| CORRECT → CORRECT | 13 | 20,052 |
| LOUD_FAIL → LOUD_FAIL | 70 | 4,256 |
| SILENT-WRONG → LOUD_FAIL | 14 | 1,324 |
| **LOUD_FAIL → SILENT-WRONG** | **18** | **84** ← **차단 사유** |
| SILENT-WRONG → CORRECT | 4 | 28 |
| CORRECT → LOUD_FAIL | 2 | 16 (오라클 산출물 아티팩트, §3 S6) |

```
NEW 총계 (25,760 순서쌍):  CORRECT 20,080 · LOUD_FAIL 5,596 · SILENT-WRONG 84
구현자 주장:                                                    SILENT-WRONG 0
```

**실측 4 — 라이브 REST로 재기동된 서버에 직접 확인**(`GET /api/maps/overlay`, 127.0.0.1:8080).
반환된 셀을 오라클로 원시 소스 행에서 재계산한 결과와 대조:

```
target bonding_map/aa123_a <- sample_map:aa123_a   status=ok  align={rot270, flip:x, origin:derived}
   184 셀 전부 어긋남.  저장(8,1) → 서버 (3,6)   오라클(클라 규약) (1,8)      [Δ = (+2,-2)]
target sample_map/aa123_a  <- bonding_map:aa123_a  status=ok  184→187 셀 전부 어긋남
target bonding_map/AAA     <- test:AAA             status=ok   44 셀 전부 어긋남 [Δ = (0,-4)]
target bonding_map/EXP1    <- sample_map:aa123_a   status=ok  184 셀 전부 어긋남
                                                   → 서버가 x = -1 셀을 반환(타깃 start_x=1, 격자 밖)
--- 대조군 ---
target bonding_map/aa123_a <- bonding_map:EXP1     status=ok  232 셀 **MATCH** (rot0↔rot0)
```
대조군이 맞는다는 것은 **원래 B1(12쌍)은 실제로 닫혔음**을 뜻한다. 남은 것은 rot90/270 축이다.

**실패 시나리오 (직전 검수와 동일하게 데이터 오염까지 간다).**
1. 사용자가 `bonding_map/aa123_a`(29x25 rot0 back)를 연다.
2. 오버레이에 `sample_map:aa123_a`(rot270 front)를 얹는다 → `status: ok`, 배지 "정렬됨 270°". 화면에 이상 신호 0.
3. `[↓ 가져오기]` → **(+2, −2) 밀린 184셀**이 `gridData`에 들어간다.
4. `[⚡ Push]` `replace_map: true` → 실운영 맵이 통째로 밀린 맵으로 교체.
   `bonding_map/EXP1` 케이스는 더 나쁘다 — 서버가 `x = -1`(격자 밖)을 반환하므로 클라의 격자 밖 필터가 **셀을 조용히 버려** 셀 수까지 줄어든다.

**왜 신규 회귀 테스트가 이것을 못 잡는가 — 자기 참조가 한 계층 아래로 내려갔다.**
`server/tests/test_map_overlay.py:604-618 _oracle_bbox`는 "독립 정답지"라고 선언돼 있지만, **`PhysicalWaferEngine`을 서버 구현과 똑같이(스왑 없이, back 부호 없이) 생성한다.** 즉 오라클은 visual↔cell↔physical **합성**에 대해서만 독립이고, **bbox 계층에서는 검증 대상과 같은 코드를 공유**한다. 결함이 정확히 그 계층에 있으므로 원리적으로 통과한다.
더해서 픽스처가 결함 축을 활성화하지 않는다 — `PHYS_STD`(`:58-60`)와 `PHYS_CROP`(`:61`)이 **둘 다 `chip_x == chip_y`**라 칩 피치 스왑의 유무가 결과에 영향을 주지 않는다. 구현자가 §1-10에 직접 쓴 교훈("회귀의 무게는 조합 수가 아니라 픽스처가 결함 축을 활성화하는가")이 **자기 픽스처에는 적용되지 않았다.**

**권장 조치 (①이 정본, 4줄).** `_frame_transformer`에서 엔진을 **프레임 좌표계 규격**으로 만든다. 클라 산술과 등가인 파라미터는 다음과 같다(`oox = -phys_offset_x if side=='back' else phys_offset_x`, `ooy = phys_offset_y`):

| rotation | `chip_size_x, chip_size_y` | `offset_x, offset_y` |
|---|---|---|
| 0   | `(cx, cy)` | `( oox,  ooy)` |
| 90  | `(cy, cx)` | `( ooy, -oox)` |
| 180 | `(cx, cy)` | `(-oox, -ooy)` |
| 270 | `(cy, cx)` | `(-ooy,  oox)` |

(유도: 클라 `getScreenShift`의 셀 단위 시프트를 `PhysicalWaferEngine.is_cell_inside_wafer`의 정규화 항과 항별로 맞춘 결과. y축은 엔진이 `(center_r - r)` 로 부호를 뒤집으므로 위 표의 부호가 그것을 상쇄한다. 라이브 오프셋은 0 또는 0.1mm라 **부호 항은 지금 발현하지 않지만 스왑 항은 발현한다** — 둘 다 고쳐야 재발이 없다.)
**②** `WaferMapCoordinateTransformer`/`PhysicalWaferEngine` 자체는 손대지 말 것 — `bonding_plan.py:187`이 같은 클래스를 엔진 없이 쓰고 있어 부작용 위험이 있다. 수정은 `map_overlay._frame_transformer` 안에 가둔다.
**③ 회귀는 반드시 `chip_x != chip_y` + `rotation ∈ (90,270)` 픽스처로 짤 것.** 그리고 테스트 오라클의 `_oracle_bbox`도 클라 산술(스왑·부호 포함)로 다시 써야 한다 — 지금 것은 서버 코드의 복사본이라 정답지가 아니다.

> 검증 하네스: `…/scratchpad/qaA_oracle.py`(클라 산술 이식) · `qaA_bbox.py`(bbox 대조+자기항등) · `qaA_livedata3.py`(저장 데이터로 판정) · `qaA_sweep.py`(라이브 전수) · `qaA_oldnew.py`(구/신 전이행렬) · `qaA_rest2.py`(라이브 REST 대조).

---

### 🟠 A2 [심각도 중 · 후속] 선언(override) 경로는 **bbox 항이 아직 없다** — B1의 미수복 형제
`server/bonding_plan.py:199-204` (`make_align_transform.to_canonical`)

```python
c = int(x) - src_start_x        # 참값은 x - src_start_x + minC_src
...
return xp + dst_start_x + off_x  # 참값은 xp - minC_dst + dst_start_x + off_x
```
이번 수정은 **유도(derived) 경로만** 프레임 합성으로 옮겼고, 선언 경로(`map_overlay.py:574`)와 전사 계획의 fail-map 정렬(`transfer_plan.py:592`)은 여전히 원래 B1 산술을 쓴다. **현재 라이브에서는 휴면**이다 — `server/config/map_overlay_config.json`의 `align_overrides`에 `__example_eds_fail_map` 한 건(비활성 접두)뿐이고, `transfer_plan` 프리셋의 `fail_cfg.align` 선언도 없다. **차단 사유는 아니나**, 사용자가 오버라이드를 한 줄 선언하는 순간 조용한 오답이 부활한다. 후속 배치에서 선언 경로도 `make_frame_transform`로 흡수하거나 bbox 항을 넣을 것.

---

### 🟡 A3 [심각도 낮음 · 정보] 인덱스 2/3 물리 존재, 3번째는 대상 테이블 부재
`pg_indexes` 직접 조회 결과:

```
idx_map_doe_ref_map          CREATE INDEX ... ON public.map_doe        USING btree (ref_table, map_key)   ✅
idx_map_doe_source_ref_map   CREATE INDEX ... ON public.map_doe_source USING btree (ref_table, map_key)   ✅
idx_map_source_region_ref_map_src  — 없음 (map_source_region 물리 테이블 미존재, E5 휴면 설계대로)
```
컬럼 구성이 `transfer_plan.py:1161-1164`의 `(ref_table, map_key)` equality 필터와 **정확히 매칭**한다(표현식 캐스트 불일치 없음). 직전 검수의 "인덱스 미생성" 지적은 **해소**. 현재 행 수 `map_doe=2 / map_doe_source=4`.

---

## 3. 반증 시도했으나 **안전한** 항목

| # | 가설 | 반증 근거 |
|---|---|---|
| S1 | M4 수정이 불완전해 identity 지름길이 아직 규격 불일치를 우회한다 | **안전 — 실증.** `frame_axes`(`map_overlay.py:187-206`)가 8튜플 `(rot, side, y반전, start_x, start_y, cols, rows, phys서명)`로 확장됐다. `40x40 vs 20x20`(축 동일, 치수만 다름) → 지름길 미적용 → `derived` → `align_unavailable: physical grid dims differ`. `29x25 chip7/7 vs chip11/13`(phys만 다름) → 지름길 미적용 → 변환 생성(bbox 재계산, 설계대로). **직전 M4는 닫혔다** |
| S2 | phys 규격 부재 명시 실패가 **과잉**이다(정상 맵이 막힌다) | 안전 — 라이브 161건 전부 phys 6필드 보유(0건 결측). 인제션 자동생성 경로도 전부 포함해 쓴다(`generate_dt_map.py:86-93`, `generate_core_defect.py:145`, `generate_eds_fail.py:153`). 또한 **양쪽 다 phys가 없고 축이 같으면 identity 지름길로 통과**하므로(실증) 무-phys 맵끼리는 막히지 않는다 |
| S3 | phys 규격 부재 명시 실패가 **과소**다(부분 결측이 새어나간다) | 안전 — `_phys_signature`(`:177-185`)가 6키 중 **하나라도** 없거나 float 변환 실패면 `None`. 실증: `phys_chip_y`만 뺀 메타 → `align_unavailable`. 한쪽만 결측인 경우(src 有/dst 無, 그 반대)도 전부 명시 실패 |
| S4 | `_pure_translation`이 틀린 offset을 클라에 표시한다 | 안전 — `map_overlay.py:349-363`이 `s[:3] != t[:3] or s[5:] != t[5:]`로 **회전·면·y반전·치수·phys가 전부 같을 때만** `(t_sx - s_sx, t_sy - s_sy)`를 낸다. 그 조건에서 bbox가 동일하므로 변환은 정확히 그 평행이동이다(대수 검증 완료). 조건 밖에서는 `None` → offset 0 유지 + `note`로 표면화 |
| S5 | `_FRAME_TF_CACHE`가 서로 다른 프레임을 같은 키로 뭉갠다 / 스레드 경합으로 깨진다 | 안전 — 키가 `frame_axes(meta)`이고 이것이 `WaferMapCoordinateTransformer` 생성자 인자 **전부**를 결정한다(치수·start·rot·side·y반전·phys). `29x25 rot270 chip7/7` vs `chip11/13` 키 상이 확인. FastAPI sync 엔드포인트라 스레드풀 경합이 가능하나 dict get/setitem/clear가 GIL 하 원자적이고 최악이 중복 생성이라 무해. 캐시된 변환기는 `get_wafer_bounding_box()` 확정 후 read-only |
| S6 | `CORRECT → LOUD_FAIL` 2쌍(가중 16)이 커버리지 회귀다 | 안전 — 해당 쌍은 `29x25 ↔ 23x23`(물리 치수 상이)이다. 구 코드가 지름길로 그냥 붙였고 오라클도 "무보정"을 냈을 뿐 **의미상 정답이 없는 조합**이다. 신 코드의 `align_unavailable`이 옳다(M4가 의도대로 작동한 결과) |
| S7 | 확장성 위반 — bbox 계산이 요청마다 격자를 전수 훑는다 | 안전 — `_FRAME_TF_CACHE`(512 상한)가 프레임 서명 단위로 재사용하고, 최대 격자가 40x40=1,600 셀이라 최초 1회도 무시할 수준. `MAX_OVERLAY_CELLS` 캡 존치. 1000만행 축과 무관(메타 테이블 161행) |
| S8 | 스위트 주장이 과장 | 안전 — `409 passed / 1 failed(test_map_presets_api)` **정확히 재현**. 알려진 무관 실패 |

---

## 4. 런타임 검증 필요

1. **A1 수정 후 재대조** — `qaA_bbox.py`(11개 서명 전부 MATCH) → `qaA_sweep.py`(SILENT-WRONG 0) → `qaA_rest2.py`(라이브 REST 5케이스 전부 MATCH) 순으로 재실행. 스크래치패드에 그대로 있으니 이식만 하면 된다.
2. **화면 육안 대조** — `bonding_map/aa123_a` 위에 `sample_map:aa123_a`(rot270)를 얹어 같은 칩이 같은 자리인지. 코드만으로는 캔버스 렌더까지 단정 불가.
3. **`grid_y_invert = true` 맵은 라이브 0건** — y반전 축은 실증 불가. `max_r - (yv - start_y)` 규약 자체는 `coordinate_transformer.py:151-164`가 `cell_to_visual`(`:136-149`)의 정확한 역함수임을 대수 확인했고 내 오라클도 같은 식이라 **`minR ≠ 0`에서도 정합**하나, bbox가 틀리면 y반전은 `2·minR`가 아니라 `maxR` 항까지 틀어지므로 **A1 수정 전에 `true` 맵을 만들지 말 것.**
4. **오프셋 부호 항(back + 비영 offset_x)** — 라이브 유일 케이스가 `bonding_map/4B13`(27x21 rot0 back, offset 0.1mm)인데 0.1/12 = 0.008셀이라 셀 포함 판정을 바꾸지 못해 현재는 발현하지 않는다. 오프셋이 칩 크기의 수 % 이상인 맵이 들어오는 즉시 발현한다 — A1 수정에 반드시 포함할 것.

---

## 5. 병합 차단 vs 후속 백로그

### 병합 차단 (이것만 고치면 GO)
| # | 조치 | 규모 |
|---|---|---|
| **A1** | `_frame_transformer`의 `PhysicalWaferEngine` 생성을 **프레임 규격**(rot 90/270 칩 스왑 + back 오프셋 부호)으로 교정 + `chip_x != chip_y` × `rot 90/270` 픽스처 회귀 + 테스트 `_oracle_bbox`를 클라 산술로 재작성 | 서버 ~6줄 + 테스트 2건 |

### 후속 백로그
- **A2** 선언(override)/`transfer_plan` fail-map 경로에 bbox 항 편입 (`bonding_plan.py:199-204`) — 현재 휴면
- (직전 검수 이월, 미해소 확인) M3 `doe_value` 재키잉 · M5 조용한 저장 실패 · M6 배분 반올림 · M7 config 주석 정정 · L1 죽은 배선
- `CODE_MAP.md`에 `make_frame_transform` · `frame_axes` · `_frame_transformer` · `derive_table_binding` · `resolve_binding` 등재

---

## 6. 문서 정합

| 대상 | 판정 |
|---|---|
| 서버 보고서 §1-8 "지적 전면 수용 … bbox·start·y반전이 규약과 자동 일치한다" | ❌ **거짓** — 변환기에 물려준 **엔진 규격이 프레임 좌표계가 아니라서** bbox가 규약과 어긋난다(rot 90/270). 위임 방향은 옳으나 결론이 성립하지 않는다 |
| 서버 보고서 §1-9 "조용한 오답 108 → **0**", "명시 실패 5,596 불변" | ❌ **전자 거짓 / 후자 참.** 독립 오라클 기준 SILENT-WRONG **84 잔존**. `align_unavailable` 5,596은 내 집계와 정확히 일치(교차 검증됨) |
| 서버 보고서 §1-10 "`oracle_overlay` — `map_overlay`를 일절 호출하지 않는 정답지" | ⚠️ **과장.** 모듈은 호출하지 않으나 `_oracle_bbox`가 `PhysicalWaferEngine`을 **검증 대상과 동일한 파라미터로** 생성한다 → bbox 계층에서 독립이 아니다. "독립"의 기준은 *모듈 미호출*이 아니라 *소비자(클라) 규약의 재구현* 이어야 한다 |
| 서버 보고서 §1-10 "회귀의 무게는 픽스처가 결함 축을 활성화하는가" | ⚠️ 교훈은 정확한데 **자기 픽스처에 미적용** — `PHYS_STD`/`PHYS_CROP` 둘 다 `chip_x == chip_y`라 칩 피치 축이 죽어 있다 |
| 서버 보고서 §1-8 "[M4] `frame_axes`에 격자 치수 + phys 서명 추가" | ✅ **정확** — 실증으로 확인(§3 S1) |
| 서버 보고서 §1-8 "phys 6필드 하나라도 없으면 `align_unavailable`" | ✅ **정확** — 부분 결측·한쪽 결측 모두 실증 |
| 직전 QA 보고서 §4-2 "인덱스 3종 미생성" | ✅ **해소**(2종 생성 확인, 3종째는 테이블 부재로 정상 skip) |
| `docs/architecture/CODE_MAP.md` | 미갱신 — 신규 함수 5종 부재. doc-keeper 트리거 유지 |

---

## 7. 라이브 정리 목록

**없음.** 본 검수는 `SELECT` + `GET /api/maps/overlay`만 사용했다. `qaA_*` 접두 시드 생성 0건, 쓰기 0건.
(참고: 직전 검수의 `qa_v2_BAND1` 시드는 현재 `map_doe`/`map_doe_source`에서 **조회되지 않는다** — 이미 정리된 것으로 보인다.)

---

## 8. 교훈 제안 (`agent_workspace/memory/qa-reviewer.md` — 총괄 검수 후 반영)

- **함정**: "독립 오라클로 대조했다"는 보고를 받으면 오라클이 정말 독립인지 확인하지 않고 수치를 믿게 된다. 본 건의 오라클은 **모듈은 호출하지 않았지만 결함이 사는 계층(`PhysicalWaferEngine` 생성 파라미터)을 검증 대상과 공유**해 원리적으로 통과했다.
  **올바른 방법**: 오라클 코드를 열어 **어느 계층까지 독립인지 계층별로 표시**한다. "구현 모듈 미호출"은 독립의 기준이 아니다. 기준은 *소비자(클라) 규약을 소비자 소스에서 재이식했는가* 이며, 재이식 대상에는 마스크·bbox 같은 **전처리 계층까지 포함**해야 한다.
- **함정**: 좌표 결함을 고칠 때 "공용 변환기 클래스에 위임했으니 규약과 자동 일치한다"는 논리는 매우 설득력 있게 들리지만, **그 클래스에 무엇을 물려주는가**가 규약과 다르면 결함이 한 계층 아래로 이동할 뿐이다.
  **올바른 방법**: 위임형 수정은 **위임 대상의 생성자 인자를 소비자 규약과 항목별로 대조**한다(본 건: 클라 `getTransformedPhysicalConfig`의 칩 스왑·오프셋 부호 vs 서버 `PhysicalWaferEngine(...)` 인자).
- **함정**: 좌표 규약 논쟁에서 "어느 쪽이 옳은가"를 코드 독해로 판정하려 하면 끝나지 않는다.
  **올바른 방법**: **저장된 실데이터에 물어본다.** bbox는 저장 좌표의 min/max를 직접 규정하므로, 도색이 꽉 찬 맵의 `MIN(x)/MAX(x)/MIN(y)/MAX(y)`를 두 가설의 예측과 대조하면 한 번에 결판난다. 부분 도색 맵도 "예측 범위를 **초과**하는 값이 있는가"로 반증에 쓸 수 있다.
- **함정**: 결함을 파라미터 공간의 한 축(회전·면)에서 고치면 이웃 축(칩 이방성·오프셋)이 같은 결함을 갖고 있어도 "고쳤다"로 보고된다.
  **올바른 방법**: 라이브 메타의 **파라미터별 분포를 먼저 세어**(본 건: `chip_x != chip_y` 14건 / 비영 오프셋 2건 / rot90·270 6건 / y반전 0건) 각 축이 검증 케이스에 포함됐는지 체크리스트로 확인한다. 0건인 축은 "안전"이 아니라 "실증 불가"로 보고한다.
