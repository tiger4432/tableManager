# M2-v2 — 「계획 = 그 맵 자체」 재설계 + 오버레이 프레임 규격 수정(A1) + DOE prune 권한 수정(C1)

> 커밋 `da65a87` · 2026-07-26 20:43 · 도메인 Server+Client / 맵·계획·전역 UI
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 선행: [M2 1차](./20260726_170434_universal_map_overlay_and_transfer_plan_m2.md)

## 배경

M2 1차(`8e34804`) 병합 직후 사용자가 근본 문제를 지적했다.

> "`bonding_map`을 열어 편집하면 그게 bonding plan, `dt_map`을 열면 dt plan이어야 하는데 Map Search & Load와 전사 계획이 따로 논다."

**계획은 별도 개체가 아니라 지금 열어 편집 중인 그 맵이다.** stage는 열린 테이블에서 유도한다. 별도 stage 선택 UI도, 타깃 입력창도, `plan_id`도, 계획 맵 사본(`transfer_plan_map`)도 없다. 사용자 제약은 **"절대 복잡하면 안 된다"** — 순 추가 3(자재 목록·브레드크럼·뒤로가기) vs 삭감 12종.

병합 관문에서 **병렬 적대적 QA 2건**(서버 좌표·무결성 / 클라 동작)을 처음 적용했다. **둘 다 NO-GO**를 반환했고, 두 차단 결함을 고쳐 독립 검증한 뒤에야 병합했다.

## 변경 내용

### A1 (서버) — 오버레이 프레임 규격 수정: `map_overlay._frame_phys_params`

**결함**: `_frame_transformer`가 `PhysicalWaferEngine`을 맵의 **물리(physical)** 규격으로 지었는데, `is_cell_inside_wafer(c, r, ...)`는 **프레임(frame)** 인덱스를 받는다. 엔진은 `x_mm = (c-cc)*chip_x + off_x`로 인덱스를 mm로 바꾸므로, `chip_x`는 **프레임 x축의 피치**여야 한다. 회전 90/270 프레임에서는 그 축이 물리 y축이므로 피치가 **스왑**돼야 한다. 메타 값을 그대로 넣으면 회전 맵의 bbox가 통째로 어긋나고, **저장 좌표가 bbox 상대값이라 전 셀이 어긋난다**.

수정은 신설 함수 하나에 국소화했다(`server/map_overlay.py:205`):

```python
def _frame_phys_params(meta: dict):
    dia, chip_x, chip_y, off_x, off_y, margin = _phys_signature(meta)
    oox = -off_x if _side_of(meta) == "back" else off_x   # back에서 물리 x축 반전
    ooy = off_y
    rot = _rotation_of(meta)
    if rot == 90:
        return dia, chip_y, chip_x, ooy, -oox, margin     # ← 피치 스왑
    if rot == 180:
        return dia, chip_x, chip_y, -oox, -ooy, margin
    if rot == 270:
        return dia, chip_y, chip_x, -ooy, oox, margin     # ← 피치 스왑
    return dia, chip_x, chip_y, oox, ooy, margin
```

| rotation | (chip_x, chip_y) | (off_x, off_y) |
|---|---|---|
| 0 | (cx, cy) | ( oox, ooy) |
| 90 | **(cy, cx)** | ( ooy, −oox) |
| 180 | (cx, cy) | (−oox, −ooy) |
| 270 | **(cy, cx)** | (−ooy, oox) |

**보정은 `map_overlay` 안에 가뒀다.** `WaferMapCoordinateTransformer`·`PhysicalWaferEngine`은 **무수정** — `bonding_plan.py`가 같은 클래스를 엔진 없이 공유하므로 부작용 위험이 있다(QA 권고 ②). 유일한 호출자는 `_frame_transformer`(:270).

**검증(과장 없이 그대로)**: 25,760 순서쌍 재대조에서 SILENT-WRONG 84 → 0, `LOUD_FAIL` 5,596 **불변**(무엇도 거래하지 않았다), `LOUD→SILENT` 전이 0. 오라클을 공유 import 0으로 재작성했고 그 오라클이 구버전을 **84**로 채점 — QA가 독립 작성한 오라클과 같은 수치라 오라클 신뢰의 교차 근거가 된다. 비등방 픽스처(40/70)를 넣어 스왑 축을 실제로 활성화했고, 결함 버전 주입 시 4개 테스트가 실제로 실패함을 확인했다. 저장 데이터 교차 확인: `sample_map/aa123_a`는 `x[1,21] y[1,25]`로, 스왑이 예측하고 구코드가 반증한 값이다.

**부수**: 프레임 합성 도입으로 M2의 QA-B3 가드(`flip != none` × rot 90/270 거절)는 **은퇴**했다 — 상수 `ALIGN_ORIGIN_UNRESOLVABLE`은 잔존하나 더 이상 발화하지 않는다.

### C1 (클라) — DOE prune 권한 일원화: `transfer_plan.adoptServerDoe`

**결함**: `loadDoeFromServer`가 **함수 내부에서** `serverKeys`/`doeServerLoaded`를 세웠는데, `saveDoeToServer`의 회복 재시도는 `retry.doe`를 **버렸다**. 결과는 "서버를 안다 + 화면은 서버본을 본 적이 없다"는 모순 상태였고, 이때 `serverKeys − keep`은 그 맵의 행 **전량**이 된다. QA가 라이브 브라우저에서 2회 재현했다(GET 1회 500 후 회복 / 절단 응답 + 낡은 초안) — `map_doe` 덮어쓰기 + `map_doe_source` 4행 전량 삭제, **토스트 0건**.

수정: prune 권한은 **`adoptServerDoe` 한 곳에서만** 생기고, 서버본 채택과 **원자적으로** 일어난다(`client2/src/transfer_plan.js:1189`).

```js
// [C1] 서버본 채택 — prune 권한(serverKeys/doeServerLoaded)이 생기는 유일한 지점이다.
// 불변식: `doeServerLoaded === true` ⇒ `S.doe`는 서버본에서 유래했다.
function adoptServerDoe(r) {
  S.serverKeys = {
    doe:    (r && r.keys && r.keys.doe)    || new Set(),
    source: (r && r.keys && r.keys.source) || new Set(),
  };
  if (r && r.doe instanceof Map && r.doe.size > 0) S.doe = r.doe;
  S.doeServerLoaded = true;
}
```

- `loadDoeFromServer`(:1098)는 이제 **조회만 한다** — `keys`를 반환할 뿐 상태를 세우지 않는다.
- 호출 지점은 둘뿐이다: 맵 컨텍스트 로드(:1262, seq 가드 통과 후)와 저장 회복(:946).
- 회복 사이클은 **쓰기 0건**으로 끝나고 로컬 초안을 보존한다. 삭제뿐 아니라 **쓰기도 보류**한다 — 로드 실패 후 편집하면 `band_seq`가 1부터 다시 매겨져 서버의 `…|F|1`을 덮어썼기 때문(실측).
- `loadSeq` 가드(:928/931, :1230/1249/1272): 맵 전환 중 늦게 도착한 재시도 응답을 채택하지 않는다.

**라이브 브라우저 증명**(쓰기를 fetch 셰임으로 가로채 실 DB 무접촉): 단일-500 회복 / 절단 응답 + 낡은 초안 / 정상 경로 회귀 / 맵 전환 레이스 4종.

### 그 외 이번 배치에 포함된 것

**클라 `transfer_plan.js`(1,405줄) — v2 모델**
- 키 조립의 유일 지점: `doeRowKey(value, seq)` = `` `${table}|${mapKey}|${value}|${seq}` ``, `doeSourceRowKey(value, seq, lot, slot)` = 거기에 `|${lot}|${slot||''}` (:187/:190). 같은 문자열이 `business_key_val`·`keep` 집합·`serverKeys`를 모두 채운다.
- **STACK 라벨은 자유 텍스트, `band_seq`가 정수 정체**다(다중 구간 `1, 2-15, 16`). `nextBandSeq`는 `max+1`이며 **삭제 시 재번호를 매기지 않는다** — 재번호는 자식 `map_doe_source`를 전부 고아로 만든다.
- 자재 수량 분배는 `Math.ceil`(서버 규약 일치 — `round`면 100/3매가 33×3=99로 부족이 숨는다).
- 파일 말미 `__held_*` 6함수(:1324~)는 명시적 **보류 구역** — 호출자 없음(검증/경고 기능은 사용자 지시로 미구현).

**클라 `map_editor.js`(4,209줄) — 오버레이 레이어**
- 오버레이 로드는 메인 로드와 **코드 경로가 완전히 분리**돼 있다. `addOverlayLayer`(:3861)는 `selectedTable`·`tableSchema`·`gridData`·legend·규격·brush·메타 입력을 **읽지도 쓰지도 않으며** `switchTable`을 경유하지 않는다(불변식 주석 :3857–3860).
- `overlayCellsToPhysMap`(:3817) — 서버가 이미 타깃 프레임으로 정렬해 내려준 좌표를 현재 격자 물리키로 배치한다. **재변환 금지**(이중 변환 방지).
- `currentGeomSignature`(:3981)/`syncOverlayGeometry`(:3992) — `cols|rows|startX|startY|yInvert|rotation|side` 서명이 바뀌면 `rawCells`에서 물리키를 재계산.
- `overlayAlignChip`(:4012) — 정렬 상태 칩. 판정은 `align.origin`으로만 한다.
- `importOverlayToGrid`(:4038) — 오버레이 → `gridData` 가져오기(서버 쓰기 없음, 페인트 잠금 존중).
- 페인트 잠금은 `/api/maps/paint-rules` 소비(:92 `fetchPaintRules`). **조용한 fail-open 제거** — 404/405는 "선언 없음"(해제)이지만 네트워크·5xx는 **직전 잠금 유지** + `source:'stale'` + 툴바 칩. (콜드 스타트는 아직 열린 채 시작 — 아래 열린 항목 C4)

**클라 `utils.js`(307줄) — 전역 토스트 재작성** (전 페이지 영향)
- 만료는 **벽시계 `expireAt`** 기준(`sweepToasts`가 `now >= expireAt` 비교). 백그라운드 탭의 `setTimeout` 스로틀링으로 토스트가 무한 누적되던(복귀 시 15개+) 원인을 제거했다 — 타이머는 스윕을 깨우는 힌트일 뿐이다.
- 상한 `TOAST_MAX_VISIBLE = 4`. 초과 퇴거는 **비-에러 오래된 것 우선**, 전부 에러일 때만 오래된 것부터. 방금 삽입한 항목은 `keep` 인자로 퇴거 면제(에러 4개일 때 새 성공 토스트가 즉시 사라지던 결함 수정).
- TTL: info/success 5s, warning 9s, **error 15s**(에러는 성공 알림에 밀려나면 안 되므로 예외).
- 스윕 트리거: 타이머 + `visibilitychange`(복귀 시) + `window.focus` + 삽입 전후.
- `dedupeKey` 합치기는 **에러 제외**(에러는 건별 원인이 중요) — 같은 키+같은 타입이면 `count += 1`·만료 연장·`… · N건` 표기.

## 아키텍처 영향

- **계획 정체성 = 맵 정체성 `(ref_table, map_key)`.** `plan_id` 폐기. `GET /api/transfer-plan/validate`는 `ref_table`/`map_key`를 받고, stage는 `stages.*.target_map.table` **역인덱스**(`transfer_plan.stage_of_table`)로 유도한다. 미선언 맵은 404가 아니라 `stage_unknown` 경고 + `status: unverified` — 임의의 맵도 열 수 있어야 하기 때문.
- `validate`의 `status`는 `ok` / `warnings` / `unverified` 3값이며, **"검사 안 함"과 "이상 없음"을 절대 같은 값으로 내지 않는다.**
- 스위트 413 passed / 1 allowed fail(`test_map_presets_api` — 상시 허용).

## 다음 단계 / 열린 항목

- **A3 — A1의 REST 재검증 미완.** 라이브 서버가 A1 수정 이전 코드로 가동 중이라 재기동 대기다. 현재 A1의 **라이브 동작은 미검증**이며 근거는 오프라인 대조·테스트뿐이다.
- **A2 — `server/bonding_plan.py:199-204`의 선언(override) 경로가 여전히 bbox 항 없는 구 산술.** 라이브 오버라이드가 없어 **휴면**이나, 한 줄 선언하면 부활한다.
- **오버레이 변환 일원화 작업이 병행 진행 중**(사용자 지시). `소스 원본(x,y) --[소스 메타 프레임]--> 물리 --[타깃의 현재 화면 컨트롤]--> 셀`로 **클라 단일 구현** 전환하며, 서버는 계측 보정(`align_overrides`)을 정렬된 좌표가 아니라 `(dx, dy, rot)` 보정값으로만 내려준다. 따라서 위 `map_editor.js` 오버레이 함수 시그니처는 **현재 상태 기술일 뿐 확정 계약이 아니다 — 곧 바뀐다.**
- **이슈 #15** — `Wafer` label에 이질적 정체가 혼입돼 있다(`wafer_slot_history.wafer_id` vs `core_wafer_map.core_lot|core_slot`). 후자는 실은 DT/테이프 계층이라 "테이프를 Wafer라 부르는" 상태다. 온톨로지 매핑은 이 때문에 보류 중.
- **QA v2 재검수의 비차단 결함은 미해소로 이월됐다**(병합은 차단 2건 A1/C1만 고치고 진행). 상세는 [MAP_EDITOR_SPEC §5.4 열린 항목](../spec/MAP_EDITOR_SPEC.md):
  - **C3** 클라 조회 `limit=500`이 `map_doe`·`map_doe_source` 양쪽에 걸려, **자재 행 500 초과 계획은 영구히 저장 불가**(절단 → 로드 실패 강등의 부작용).
  - **C4** 페인트 잠금 **콜드 스타트 fail-open** — "직전 값"이 로드 직후엔 `{enabled:false}`라 첫 조회 실패 시 잠기지 않는다.
  - **C5** legend 저장이 *실패*와 *보낼 것 없음*을 같은 `false`로 반환 → 근거 없는 경고 토스트.
  - **C6** 헤더가 서버본 로드 후에도 낡은 초안 시각을 표시.
  - **C7** 오버레이 기하 서명에 물리 파라미터 누락 — 신규 `importOverlayToGrid`가 **표시 오류를 데이터 오염 경로로 승격**시켰다.
  - **C8** `sticky` 토스트가 상한 퇴거에서 보호되지 않음(현재 호출부 0건).
- **회귀 시험 규율** — 오버레이 좌표 회귀는 반드시 **bbox ≠ 0인 실데이터**(29×25, 27×21 등)로 재확인할 것. 40×40(`minC=0`)은 결함이 원리적으로 발현할 수 없는 구간이며, **같은 사각지대에서 2회 연속 "해소" 오판정이 났다.**
- **M3(클라 백로그)** — `doe_value` 재키잉: 값 개명 시 자식 `map_doe_source`가 고아가 되는 구조(`stack_band`와 동형).
- **config 샘플 드리프트(신규 발견)** — `server/config/transfer_plan_config.json.sample`의 `plan_store` 섹션이 v1 잔재다. 상세는 아래 "문서-코드 정합" 항목 및 doc-keeper 사이클 보고서 참조.
