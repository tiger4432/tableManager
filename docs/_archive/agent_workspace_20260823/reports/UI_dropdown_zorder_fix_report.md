# UI 드롭다운 z-order 수정 보고서

- **작성**: ui-designer
- **날짜**: 2026-07-25
- **대상 버그**: index.html Menu 드롭다운(`#nav-dropdown`) 위로 `.split-resizer` 세로줄이 관통
- **커밋**: 없음 (지시대로 미커밋 — main 워킹트리 수정만)

## 1. 근본 원인 (총괄 진단의 정정 포함)

총괄 진단은 "`.app-header`가 `position: static`이라 `z-index: 10`이 **무효** → 스태킹 컨텍스트 부재"였으나, 라이브 검증 결과 **메커니즘이 반대**였다.

- `#app`은 `display: flex` 컨테이너다 (`style.css` `#app`).
- **Flexbox 스펙상 flex item은 `position: static`이어도 `z-index`가 적용되며, non-auto z-index는 스태킹 컨텍스트를 생성한다** (CSS Flexible Box §Painting — grid item도 동일).
- 따라서 `.app-header { z-index: 10 }`은 무효가 아니라 **살아있는 z:10 스태킹 컨텍스트**였고, 헤더 내부 드롭다운 `.glass-dropdown-panel { z-index: 1000 }`은 이 z:10 컨텍스트 **안에 갇힌다**.
- 루트 컨텍스트 레벨 비교: 헤더 컨텍스트(10) < `.split-resizer`(100) → 드롭다운의 1000은 컨텍스트 내부 값일 뿐, 최종 페인트 순서는 10 < 100으로 resizer 승리.

### 라이브 실증 (localhost:8080, elementFromPoint)
| 조건 | 히트 결과 (드롭다운-resizer 겹침 지점) |
|---|---|
| 현행 (`static` + `z-index:10`) | `main-split-resizer` (버그 재현) |
| `z-index: auto`만으로 변경 (position 그대로 static) | `dropdown-item nav-link` (버그 소멸 → flex-item z-index가 원인임을 단독 증명) |
| `position: relative; z-index: 200` (채택안) | `dropdown-item nav-link` (수정 확인) |
| 롤백 | `main-split-resizer` (재현 복귀 — 실험 유효성 확인) |

조상 체인 전수 스캔(transform/filter/backdrop-filter/opacity/isolation/contain/will-change/mix-blend-mode/clip-path/mask/perspective/zoom/content-visibility/container-type)에서 다른 스태킹 컨텍스트 생성자는 **없음** — flex-item z-index가 유일 원인.

## 2. 변경 파일 (3개, 순수 CSS)

### `client2/src/style.css` (index + map_editor 공용)
- `.app-header`: `position: relative` 추가, `z-index: 10 → 200`. 메커니즘 주석 추가.
- before: 헤더 컨텍스트 z:10 → 드롭다운이 resizer(100) 아래.
- after: 헤더 레이어 z:200 → 헤더 소속 드롭다운·배지 전부 resizer 위, 팝업(1000)·모달(2000+)·토스트(9998+)는 여전히 그 위.

### `client2/enrichment.html` (인라인 CSS)
- 동일 구조(`#app` flex + `.app-header` static `z-index:10`)의 잠복 트랩. `position: relative` + `z-index: 200`으로 통일. (현재 겹치는 요소는 없으나 setup-overlay z:50 등 본문 고z 요소가 존재하고, index 헤더 패턴이 이 페이지로 계속 이식되는 중이라 예방 수정.)

### `client2/admin.html` (인라인 CSS)
- `header`는 `position: sticky; z-index: 100` — 자기 페이지 `.split-resizer`(z:100)와 **동률**이라 DOM 순서상 resizer가 나중 → 페이지 세로 스크롤 시 sticky 헤더 위로 resizer가 그려지는 동일 계열 결함. `z-index: 100 → 200`.

### 확립된 z 스케일 (전 페이지 일관)
`2 (AG-Grid 핸들) < 5~50 (패널 내 오버레이) < 100 (split-resizer) < 200 (헤더 레이어) < 1000 (드롭다운·컨텍스트메뉴) < 2000/3000 (모달) < 9998+ (토스트·풀스크린)`

## 3. 사이드이펙트 전수 점검 (회귀 없음 근거)

1. **`position: relative` 추가로 인한 containing block 변화**: `style.css` 내 `position: absolute` 전수 검색 결과, 헤더 자손 중 absolute는 `.glass-dropdown-panel`뿐이고 그 앵커는 `.relative-menu`(더 가까운 조상)라 **재앵커링 없음**. `.drop-overlay`·`.timeline::before`·`.wafer-notch` 등은 헤더 자손이 아님.
2. **index의 `#column-selector-dropdown`·`#custom-context-menu`** (z:1000, `#app` 직속 — 헤더 밖): 루트 레벨 1000 > 헤더 200 → 종전대로 헤더·resizer 위. 변화 없음.
3. **모달(2000/3000)·토스트(9998/9999)·풀스크린 오버레이(9999)**: 전부 body/#app 레벨이며 200보다 높음 → 헤더를 정상적으로 덮는다.
4. **map_editor**: 공용 `.app-header`라 자동 적용. 헤더에 드롭다운 없음, 본문 고z(grid-cell 10, wafer-notch 15)는 캔버스 컨테이너 내부 값 → 겹침·회귀 없음. (헤더는 이미 z:10 컨텍스트였으므로 "컨텍스트 신설"이 아니라 레벨 상향일 뿐 — 내부 상대 순서 불변.)
5. **admin**: 모달/오버레이 요소 없음(검색 확인). 헤더 100→200은 resizer(100)·sticky 테이블 헤더(10)와의 관계만 위로 정리. Monaco 위젯은 에디터 패널 내부 컨텍스트라 무관.
6. **성능**: 정적 z-index/position 변경만 — 리플로/페인트 특성 변화 없음.

## 4. Client PM 이관 항목
없음 — 로직(JS) 변경 불필요. `node --check` 대상 없음.

## 5. 검증 상태
- 소스 CSS 변경 자체의 라이브 확인은 dist 빌드 후 가능 (빌드는 총괄 수행). 위 표의 인젝션 실험이 채택안과 동일 값이므로 빌드 후 동일 결과 예상. 확인 포인트: index에서 Menu/Options 드롭다운 열고 resizer 교차 영역, admin에서 스크롤 후 sticky 헤더 경계.

## 6. 교훈 제안 (ui-designer.md 반영 요망)
- **함정**: flex/grid 컨테이너의 item은 `position: static`이어도 `z-index`가 적용되어 스태킹 컨텍스트를 만든다. "static이라 z-index 무효"라는 통념으로 진단하면 원인을 반대로 짚는다.
  **올바른 방법**: 겹침 버그는 elementFromPoint + 조상 체인 computed style 덤프로 실증하고, flex item의 z-index를 스태킹 컨텍스트 후보에 반드시 포함할 것.
