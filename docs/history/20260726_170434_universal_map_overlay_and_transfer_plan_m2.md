# M2 — 범용 맵 오버레이 + DOE 계획 엔진 + 페인트 잠금 선언 (1차)

> 커밋 `8e34804` · 2026-07-26 17:04 · 도메인 Server+Client / 맵·계획
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 후속 재설계: [M2-v2](./20260726_204344_m2_v2_plan_as_map_redesign.md)

## 배경

M1(`e6eabe4`)은 본딩 실험계획을 **조회 전용 Info 패널**로 붙였다. M2의 과제는 두 가지였다.

1. **전사(transfer)를 프리미티브로 일반화** — 본딩만이 아니라 임의의 단계(DT→테이프, 테이프→본딩 …)를 `(stage, target 맵 페인팅, assignments)`로 선언만 하면 코드 불변으로 추가되게 한다. 관리 단위는 **value(DOE)** — 값 하나가 조건군 하나를 뜻한다.
2. **맵 오버레이를 계획 전용이 아닌 맵 인프라로 격상**(사용자 지시) — "모든 MAP을 universal하게 오버레이". map meta가 달라도 정렬해서 겹친다.

## 변경 내용

### 서버

**`server/map_overlay.py` 신설 — 범용 오버레이.** `GET /api/maps/overlay`가 `sources` CSV(`table` 또는 `table:key`, 최대 8종)를 받아 타깃 맵 캔버스 좌표로 정렬한 `overlays[]`를 반환한다. 정렬은 **마이그레이션 없이** `wafer_map_metadata`의 rotation/side 차이에서 자동 유도된다.

align 기본값 규율(총괄 고정 계약):

```
선언(align_overrides) 있으면 그대로 적용
→ 없으면 메타 차이에서 유도
→ 유도 근거도 없으면 identity(0°)로 그냥 붙임 (선언 부재는 실패가 아니다)
→ 변환을 계산할 근거 자체가 없을 때만 status = align_unavailable
```

QA-B3 가드로 `flip != none` × 타깃 rot 90/270 조합은 `align_unavailable`로 거절했다(16/64 조합의 조용한 거울상 오답 차단). 선언 override는 탈출구로 존치.

`GET /api/maps/paint-rules` — 페인트 잠금 선언의 정본을 서버로 옮겼다(**기존엔 클라 하드코딩 `'F'`**). 기본은 F 잠금.

**`server/transfer_plan.py` 신설 — DOE 계획 엔진.** stage config 로더 + 가용량 엔진:

```
가용 = 총 − (fail ∪ transferred)
```

fail 투영은 코어 fail을 `dt_log` 조인으로 테이프 계층에 내린다. `by_core`는 **7키 균일 형태**로 통일하고 출처를 `by_core_origin` 마커로 구분한다.

QA F1(degraded 시 `remaining` 과대 표기) 대응은 **3층 방어**다 — 한 층만으로는 클라가 초록으로 뒤집을 수 있었기 때문이다:

```
remaining: null              ← 값을 아예 주지 않는다
remaining_reliable: false    ← 신뢰 플래그
warnings: [source_degraded]  ← 사람이 읽는 사유
```

`validate`는 이 상태에서 `unverified`를 반환하고 `qty_shortage` 판정을 **금지**한다. 그 외 N1 음수 가드, F4 소스 합산 초과배정, F6 `dst_grid` 전달, F2 캡 절단 표기.

**인덱스**: `server/scripts/setup_transfer_plan_indexes.py` — `bonding_map.base` Seq Scan 214ms → 0.345ms(~600배).

### 클라

- 슬라이드 패널 폐기 → **사이드바 통합**. `client2/src/bonding_plan.js`(903줄)·`bonding_plan.css`는 **삭제**되고 `transfer_plan.js`/`.css`로 대체됐다.
- B1 잠금 재개통 수정(컬럼 드롭다운 변경 시 readOnly + 맵키 복원).
- B2 DOE 층 잔재의 서버 삭제 전파(거짓 초과배정 경고 제거).
- **`'F'` 하드코딩 제거 → `/api/maps/paint-rules` 소비.** 코어 팔레트 범례 오염 가드.

## 아키텍처 영향

- 신규 라우트 5종: `/api/maps/overlay`, `/api/maps/paint-rules`, `/api/transfer-plan/{stages,source-summary,validate}`.
- 신규 config 2종(gitignored, `.sample` tracked): `map_overlay_config.json`, `transfer_plan_config.json`.
- **오버레이는 맵 인프라다** — 계획 UI는 그 소비자 중 하나일 뿐이며, 임의의 맵 위에 임의의 맵을 겹치는 데 쓸 수 있다.
- 테스트 352 passed / 1 allowed fail.

## 다음 단계 / 열린 항목

- QA 판정은 **GO-WITH-FIXES**였고, 병합 직후 사용자 지시로 **M2-v2 「계획 = 그 맵 자체」 재설계**가 착수됐다 → [M2-v2 히스토리](./20260726_204344_m2_v2_plan_as_map_redesign.md). 본 문서의 클라 UI 서술(슬라이드 패널→사이드바, `plan_id` 기반 모델)은 v2에서 **다시 갈아엎혔다** — 현재 상태는 v2 문서를 보라.
- 이슈 #14(맵 push 경로 기존 결함 3종)가 이 QA에서 부수 발견됐다. **M2 회귀가 아니라 전 맵 공통**이다.
