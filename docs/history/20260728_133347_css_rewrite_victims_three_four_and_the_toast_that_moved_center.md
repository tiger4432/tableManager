# 재작성의 세 번째·네 번째 희생자 — 그리고 회피 장치째 사라진 토스트 가림

> 커밋 `a98dc72` · 2026-07-28 13:33 · 도메인 Client(시각 전용, T3)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)
> 원인 커밋: [b35bc9f의 CSS 전면 재작성](./20260728_072317_doe_zone_client_half_config_backup_and_two_traps.md) · 첫 희생자 복원: [.overlay-box](./20260728_074941_map_editor_five_fixes_lag_overlay_reopen.md)
> CSS 전용 — 하네스 82/331/71 green을 no-JS 카나리아로 사용. 격리 :8081에서 기하 실측.

## U7 — .map-breadcrumb와 .plock-chip: JS는 클래스를 계속 썼고, CSS만 없었다

`b35bc9f`의 `transfer_plan.css` 전면 재작성이 떨어뜨린 것이 `.overlay-box` 하나가
아니었다. `.map-breadcrumb`/`.bc-*`(프레임 스택 빵부스러기 바)와 `.plock-chip`
(칠 잠금 상태 칩)도 함께 사라져 있었다 — `renderBreadcrumb()`/
`updatePaintLockIndicator()`와 HTML은 클래스를 계속 쓰고 있었으므로, 바는 스타일
없는 인라인 텍스트로 찌그러져 겹쳐 그려졌다. 같은 원인의 세 번째·네 번째 희생자다.

복원은 재작성 이전(`da65a87`) 원본 그대로에, 좁은 폭 보강 셋을 얹었다:

```css
.bc-back { flex: none; }              /* 뒤로 버튼은 절대 눌리지 않는다 */
.bc-up, .bc-cur { flex: 0 1 auto; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; }  /* 경로는 말줄임 */
.map-breadcrumb { flex-wrap: wrap; }  /* 힌트(.bc-why, margin-left:auto)는
                                         좁아지면 제 줄로 내려간다 — JS·미디어쿼리 없이 */
```

`.plock-chip.stale`(경고색)도 함께 살아났다 — "확인 불가"가 화면에 보이는 것 자체가
M2의 요점이었으므로, 이 클래스의 소실은 조용한 fail-open의 시각적 재발이었다.

이번에는 클래스 하나를 되살리고 끝내지 않았다: `da65a87` 대비 **전수 클래스
인벤토리 diff**로 재작성이 떨어뜨린 것이 더 없음을 확인했다. `b35bc9f` CSS 소실
계열의 감사는 이 시점에 닫혔다 — 이후 같은 증상이 나오면 원인은 다른 커밋이다.

## U1 — 50/50은 이미 살아 있었고, 거짓말한 것은 주석뿐이었다

두 pane의 반반 분할은 이 커밋 전에 이미 규칙(`flex: 1 1 0`)으로 살아 있었다 —
파일 머리 주석만 옛 고정 250px 자재 pane 레이아웃을 서술하고 있었다. 주석을 실제
구조로 다시 썼고, 참조 0건인 죽은 `.tp-scroll` 블록을 지웠으며, `min-height: 0`을
110px 바닥으로 올렸다 — 아주 낮은 창에서 pane이 무로 붕괴하는 것을 막되, flex 기본
`min-height: auto`는 여전히 눌러 긴 내용이 pane을 늘이는 대신 스크롤되게 유지한다
(옛 시안에서 실측된 696px→211px 찌그러짐의 재발 방지 조건은 그대로다).

## U3 — 토스트를 가운데로 옮기자 회피 장치가 통째로 필요 없어졌다

`--toast-inset-right`는 토스트가 우하단에 떠서 자재 목록(이동 허브)을 덮는 문제를
페이지별 오프셋으로 **비켜 세우던** 장치였다. 토스트를 하단 중앙 배너
(`width: min(640px, calc(100vw - 48px))`)로 옮기니 가림과 오프셋 장치가 동시에
무의미해졌다 — 변수 선언·소비처를 grep 0건 확인 후 제거했다. 진입/퇴장은
opacity 전용(상승 모션 삭제), 최신 토스트가 하단에 가장 가깝게 쌓인다.

## 검증

- CSS 전용 변경 — 하네스 82/331/71 green은 JS 무접촉의 카나리아.
- 기하는 격리 :8081에서 **가정이 아니라 실측**: 두 pane 319px/319px, 토스트
  centerOffset 0.

## 그때 남아 있던 것

- <1540px 사이드바 잘림은 이 라운드의 좁은 폭 보강(빵부스러기)과 별개로 대기열에
  그대로 있었다 — 이 커밋은 건드리지 않았다.
- 110px 바닥의 대가: 아주 낮은 창에서는 두 pane이 합계 220px+를 항상 점유한다.
- 호환용 `@keyframes toastIn`(구 admin.js가 참조하던 이름)은 rise만 빠진 채 남았다.
