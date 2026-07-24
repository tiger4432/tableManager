# 맵 에디터: 중앙 반투명 FRONT/BACK 워터마크 복원 (표시 전용)

## 현상 (Phenomenon)
- 직전 커밋 `0130283`에서 캔버스 내 FRONT/BACK 배지·워터마크를 통째로 제거하고 DOM 칩(`#side-indicator`)으로 대체함.
- 사용자는 **캔버스 중앙에 흐릿하게 뜨는 반투명 워터마크**를 선호 → 해당 시각 요소만 되살려 달라는 요청.

## 조치 (Solution)
`renderGridCanvas()` 말미, 마지막 `ctx.restore()` **직전**(step 8 hover 하이라이트 다음)에 표시 전용 오버레이(step 9)를 추가.
- 제거되었던 것 중 **워터마크만** 복원. 좌상단 pill 배지는 복원하지 않음(이미 DOM 칩 `#side-indicator`가 담당).
- 색상: FRONT = `rgba(56, 189, 248, 0.13)`(하늘색), BACK = `rgba(245, 158, 11, 0.13)`(앰버).
- 폰트: `900 <크기>px "JetBrains Mono", monospace`, 크기 = `Math.max(40, Math.floor(width * 0.16))`, textAlign/textBaseline = center/middle.
- 폰트·정렬 상태는 자체 `ctx.save()`/`ctx.restore()`로 격리 → 다음 렌더 패스로 상태 누수 없음.

```js
  // 9. FRONT / BACK translucent watermark (display-only overlay, centered)
  {
    const isBack = (currentSide === 'back');
    const sideWord = isBack ? 'BACK' : 'FRONT';
    const wmColor = isBack ? 'rgba(245, 158, 11, 0.13)' : 'rgba(56, 189, 248, 0.13)';
    const wmFont = Math.max(40, Math.floor(width * 0.16));

    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `900 ${wmFont}px "JetBrains Mono", monospace`;
    ctx.fillStyle = wmColor;
    ctx.fillText(sideWord, width / 2, height / 2);
    ctx.restore();
  }
```

## 사이드 이펙트 분석 (StableDevelopmentProtocol §1 준수)
| 항목 | 결과 |
|---|---|
| 좌표계/기하 | 안전 — 중앙 텍스트만 그림. `cell` 데이터·`gridCells2D` 미변경, hit-test/마우스→셀 매핑에 영향 없음. `width/height`는 렌더용 CSS px 지역변수(라인 1256~1257), dpr 스케일 이미 적용된 `ctx`에 그려 정합 유지. |
| 공유 가변 상태 | 안전 — `currentSide` 읽기만(불변). `gridCells2D`, legend, 기타 모듈 전역 미수정. |
| 타이밍(rAF) | 안전 — 워터마크는 매 렌더 패스 내부 draw. 추가 rAF/비동기/이벤트 리스너 없음. |
| 리사이즈→마우스 매핑 | 무관 — 워터마크는 표시 전용. `fitGridToWorkspace()`·`getGridCellFromMouseEvent()` 로직 미변경. wmFont가 `width` 기반이라 리사이즈 시 자연 추종. |
| ctx 상태 누수 | 자체 save/restore로 font/textAlign/textBaseline/fillStyle 격리, 다음 프레임 미오염. |
| DOM 칩 유지 | `#side-indicator`·`updateSideIndicator()` 미변경 → 워터마크는 칩과 병존(중복이 아니라 두 표기 동시). |

## 검증 (Validation)
- `node --check client2/src/map_editor.js` 통과.
- `cd client2 && npm run build`(vite) 성공 — 맵 에디터 번들 재생성(`dist/assets/map_editor-4orys1JJ.js`). FastAPI 서빙 추적 파일이므로 `client2/dist` 재빌드 결과 포함.
- 관찰된 이슈: 없음. (라이브 렌더 시각 확인은 별도 브라우저 필요 — 로직상 좌표/상태 무영향으로 사실 검증 완료.)

## 영향 (Impact)
- 도메인: Client PM. 캔버스 표시 전용 오버레이만 추가 — 경계 계약(REST/WS/셀 형태/스키마) 무관, 서버 무영향.
- 리빙 문서 `docs/map_editor/architecture_and_management.md` §3.2 "FRONT / BACK 관찰면 표기"에 중앙 반투명 워터마크(표시 전용) 1줄 병기.
- 수정 파일: `client2/src/map_editor.js`, `client2/dist/*`(빌드 산출물), `docs/map_editor/architecture_and_management.md`, 본 히스토리.
