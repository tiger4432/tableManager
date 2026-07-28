# U6 — 클라가 들고 있던 서버 지식 네 무더기를 선언으로 회수했다 · 두 레인 QA의 첫 가동

> 커밋 `95bf072` · 2026-07-28 13:15 · 도메인 Server(map_overlay·paint-rules) + Client(맵 에디터·계획 패널)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) · config 가이드: [map_overlay_config.md](../guide/config/map_overlay_config.md)
> 스위트 838 green · 하네스 82/331/71 green.

## 배경 — 복사본은 반드시 갈라진다

클라이언트가 서버 지식의 사본을 네 무더기 들고 있었고, 이미 갈라져 있었다:

- 값 컬럼 후보 목록 **두 벌** — 서버는 `("val","value","leg",...)` 8종, 클라 한 곳은
  `['leg','status','value','val','bin']`으로 **내용까지 달랐다**. 같은 테이블의
  값 컬럼을 서버와 클라가 다르게 고를 수 있는 상태였다.
- builtin stage 목록 — `dt_map`/`bonding_map`을 클라가 직접 알았고, 초기 테이블
  선택도 `bonding_map` 하드코딩이었다.
- legend 팔레트 12색 **세 벌 복사**.
- E1/E2 자동칠 색 고정(`#8b5cf6`/`#ec4899`).

수정 원리는 하나다: **선언은 서버 config에 한 벌, 클라는 읽어서 적용한다.** 새 엔드포인트를
만들지 않고 기존 `GET /api/maps/paint-rules` 응답에 실었다 — 이미 테이블 전환마다
재조회되는 관문이다.

## 서버 절반 — 두 선언, 두 부재 의미

`map_overlay_config.json`에 선택 키 둘이 생겼고, 부재의 의미를 서로 다르게 정했다:

```python
# server/map_overlay.py — 이 커밋 시점
def resolve_value_column_candidates(cfg):   # 미선언 → DEFAULT_VAL_CANDIDATES (문서화된 기본값)
def get_default_legend(cfg):                # 미선언 → None (정직한 부재 — 지어내지 않는다)
```

- `value_column_candidates`: 선언하면 서버 기본값을 **통째로 대체**(부분 병합 없음).
  종전 `VAL_CANDIDATES` 튜플은 `DEFAULT_VAL_CANDIDATES`로 강등되고, 소비자는
  `resolve_...(cfg)`를 거치게 했다 — 튜플을 직접 읽으면 이 기본값이 없애려는
  하드코딩을 재생산하는 것이라고 주석이 직접 경고한다.
- `default_legend`: registry 행 없는 맵의 시작 legend + 자동 추가 값의 색/설명 사전.
  미선언이면 `null` — 서버가 사용자가 선언한 적 없는 행을 지어내지 않는다. 라이브/샘플
  선언은 빈 맵 규칙(2026-07-28)대로 VALUE 1 한 행이고, 4행 팔레트는 원하는 현장을
  위한 주석 예시로만 남겼다.

## 클라 절반 — 사본 삭제와, 사본 없는 실패의 모양

삭제 후 남는 질문은 "서버가 답하기 전/못할 때 어떻게 행동하나"다. builtin 사본으로
돌아가는 길은 없앴으므로, 실패는 **정직한 축소 동작**이어야 했다:

- paint-rules 응답의 두 기본값은 `overlayContract` 캐시 하나로 들어오고, 후보 목록을
  실제로 실은 응답만 캐시를 갱신한다(구버전 서버는 기존 캐시 유지). `switchTable`은
  스키마 fetch와 병렬로 돈 paint-rules 왕복을 **기다린 뒤** 컬럼 자동 감지를 한다.
- stage는 두 부재를 구분했다: 404/405·빈 선언 = "선언 없음"(확정, stages `[]`),
  그 외 실패 = "확인 불가"(마지막으로 안 선언 유지 + 다음 맵 전환 시 재시도, 배지
  툴팁이 그 사실을 말한다). 초기 테이블 선택은 `stageTargetTables()` — 선언된 stage
  TARGET 중 첫 맵 테이블, 없으면 첫 맵 테이블이다.
- 값 자동 추가는 `autoAddLegendValue` 한 경로로 모였다: 선언된 `default_legend` 행이
  색/설명을 이기고, 없으면 한 벌짜리 `LEGEND_PALETTE` 규칙이다. E1/E2 자동칠·패널
  [+ 값]·맵 로드 legend 빌드가 전부 이 경로를 탄다.

## U6-1 — 같은 테이블의 0셀 맵이 앞 맵의 legend를 상속했다 (라운드 내 발견·수정)

브라우저 레인 QA가 재현했다: 같은 테이블에서 0셀 맵을 열면 칠 기반 legend 재구축이
`uniqueVals.size > 0` 가드로 건너뛰어져, **앞 맵의 non-vocab 행이 화면에 남은 채**
registry 병합이 그것을 이 맵의 baseline으로 삼았다(AAA의 F/2/D1/D2가 QA_EMPTY_U6에
그대로 표시). 수정은 registry가 0행을 **확정 응답**했을 때만 seed 팔로 리셋:

```js
// loadExistingMap — read.ok 아래에서만. 읽기 실패는 화면 보존(unknown-server-state).
if (uniqueVals.size === 0) seedEmptyDoe();
applyRegistryRowsToLegend(read.rows);
```

## QA — 두 레인 분할의 첫 가동

병렬 QA 방침의 첫 실행이었다: **API 레인**(GO — 요청별 재독 증명, 삭제된 목록 전부의
번들 grep 청정, 하네스가 진짜 단언임을 rename 주입으로 확인)과 **브라우저 레인**
(GO-WITH-FIXES — 위 U6-1을 라운드 내 발견, 결함 주입 정확히 1회로 검증)이 동시에
돌았다. 레인 분할이 깊이를 잃지 않고 대기를 줄인다는 첫 실측이 이 라운드다.

## 그때 남아 있던 것

- 후보 매칭의 대소문자 규약이 서버(정확 일치)와 클라(소문자화 비교)에서 달랐다 —
  Low로 대기열에 남겼다.
- 미열람 프레임에서의 뒤로가기 confirm, <1540px 사이드바 잘림도 함께 대기열행.
- stage 선언 자체가 없는 서버(구버전)에서는 계획 기능 전체가 "일반 맵 (legend)"
  축소 상태였다 — builtin 폴백 삭제의 의도된 대가다.
