# 깨끗한 종료가 아무것도 증명하지 못하고 있었다 — 가장 큰 클라 하네스가 이틀째 0점이었다

**날짜:** 2026-08-11 09:07 · **커밋:** `ab36fab` · **레인:** 클라(하네스 게이트)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

2026-08-09, 후보-축 마이그레이션(`db1ee42`)이 착지할 수 있도록 하네스 게이트가
`process.exit(1)`을 잃었다(당시 지시: 「진단은 다 보이게 두되, 후보 계약 마이그레이션이
트리아지 되는 동안은 하네스 실패/config drift를 종료 코드 게이트로 만들지 마라」).
그 조치와 함께 하네스 셋의 바닥(FLOORS 항목)도 삭제됐다. 이 커밋이 그 이틀 뒤에 잇는다.

## 종료 코드를 없애는 것은 빨갛다고 표시하는 것과 같지 않다

```diff
-// Lead PM direction 2026-08-09: keep every diagnostic visible, but do not make harness
-// failures/config drift an exit-code gate while the candidate-contract migration is triaged.
-const fail = msg => { console.error(`\n✗ ${msg}\n`); };
+const fail = msg => { console.error(`\n✗ ${msg}\n`); process.exit(1); };
```

종료 코드를 지우는 것은 **grep으로 찾을 수 있는 것을 아무것도 남기지 않는다** — 밖에서
보면 정상 작동하는 게이트와 똑같이 읽힌다. `KNOWN_RED`는 정확히 이 상황을 위해 존재하는
장치였다: 등재된 하네스는 여전히 **실행되고 보고되지만 블록하지 않는다** — 마이그레이션
중인 것을 하네스별로, 사유를 달아, 한곳에서 소리 내어 말할 방법이다. 대신 종료 코드를
건드리는 것은 **하네스별 진술을 전부에 대한 침묵으로 바꾸는 거래**였다.

## 대가는 실측됐다

`map_editor2_shell_harness`·`map_editor2_question_harness`·`map2_placement_seat_harness`
셋이 `ran: 0`으로 `KNOWN_RED`에 들어가면서 **그 세 하네스의 바닥(FLOORS)도 함께
삭제됐다.** 결과: 이틀 동안 **트리에서 가장 큰 클라이언트 하네스가 어서션 0개를
실행했고**, 빌드는 그것을 어디에도 말하지 않았다.

## 복구 — 3방향 변이로 증명

이빨을 되찾았다는 것을 변이 셋으로 증명했다. 각각 종료 코드 1을 낸다: 측정치 위로
올린 바닥, `START_HEADERS.top_right`를 바꾼 변이, `ran:`을 올린 `KNOWN_RED` 항목.
아무것도 깨지지 않은 상태에서(여전히 `KNOWN_RED`에 5개가 남은 채로) 종료 0. 러너는
같은 이름이 `FLOORS`와 `KNOWN_RED` 양쪽에 있으면 아예 시작을 거부한다 — 두 상태가
동시에 참일 수 없다는 것을 구조로 강제한다.

```
map_editor2_shell_harness      dead ->    577   (floor was 560)
map_editor2_question_harness   dead ->    193   (floor was 192)
map2_placement_seat_harness    dead ->     60   (floor was  42)
gate total                   25,442 -> 26,272   assertions; 48 failed either way
```

바닥은 낮춰지지 않았고 `KNOWN_RED`로 옮겨 초록을 산 것도 없다.

## 실제로 부담을 진 수리 — 오라클이 안 그리는 경로를 채점하고 있었다

section L의 오라클이 `framesFor`를 통해 셀을 앉혔는데, 이 함수는 **회전과 면만** 읽는다.
모든 후보가 `front`가 된 지금은 여덟 후보 중 네 개 이상을 구별할 수 없었고, 애초에
그것은 더 이상 화면이 그리는 경로도 아니었다 — 그림은 서버의 `placement`를 통해
`seatingFor`에서 온다.

오라클을 와이어 자신의 `{linear, anchor_src, anchor_ref}`를 읽도록 바꿨다. 새 픽스처
둘은 서버가 시작 모서리를 두는 자리(`map_alignment.py:2113`)와 똑같이 **`anchor_ref`에**
둔다 — 행렬에도, 소스 앵커에도 두지 않는다. `B3b`는 한 회전의 양쪽 열이 **바이트
동일한 좌석**을 돌려주는지 단언한다 — 서버 결함(여덟 시프트 전부 `(-13,-11)`로
측정됐던 그 결함)의 클라이언트 쪽 쌍둥이다.

## enrichment.html 실제 삭제

파일과 vite 엔트리가 이 커밋에서 삭제됐다(두 커밋 전 `1e29078`에서는 링크만 제거,
그 다음 `5116f67`에서는 admin.js 점프만 제거 — 파일 자체는 여기서 처음 없어진다).
`/enrichment.html`을 남기는 `ROUTE_BY_PATH`는 평평한 조회라 다른 경로의 해석에는
영향이 없다. `ROUTE_IDS`는 **서빙된 허용목록을 검증**하는 것이지 실제 내비게이션
수를 세는 게 아니라서, id 자체는 지우지 않았다 — 지우면 그 id를 이름 댄 config
항목이 「알 수 없음」으로 보고되면서도 여전히 카운트된다. 측정으로 확인: 서빙 목록
기본값은 `[]`이고 `server/config/effort_metric.json`이 존재하지 않아, 오늘은 아무것도
면제돼 있지 않고 아무것도 면제를 풀 수 없다 — 어느 쪽이든.

두 번째 소비자를 잃으면서 vite가 `enrichment_queue`와 ag-grid 테마를 공유 청크 대신
각자의 임포터에 인라인했다. `queueQuery`는 `admin.js:3561`을 통해 여전히 살아 있고,
재빌드된 CSS에 `--ag-` 속성 2,836개가 전부 존재함을 확인했다.

## 검증

section L 재작성 + 신규 픽스처 둘, `B3b` 신설. 게이트 총계는 위 표 그대로: 어서션
25,442 → 26,272, 실패 48건(변화 없음), 회귀 신규 0건.

## 그때 남아 있던 것

- `KNOWN_RED`에는 이 커밋 이후에도 5개가 남는다 — 종료 코드 복구가 그 5개를 정리한
  것은 아니다.
- `enrichment.html`이 서빙됐던 흔적(허용목록의 route id 자체)은 이 커밋에서도 의도적으로
  남는다 — config가 그 id를 다시 참조할 가능성에 대비한 결정이다.
- `map_editor2_shell_harness`·`map_editor2_question_harness`·`map2_placement_seat_harness`
  세 하네스가 `ran: 0`으로 이틀을 보낸 것은 **되돌릴 수 없는 사실**로 남는다 — 이
  기간의 회귀는 측정 불가능했다는 뜻이고, 이 커밋은 그 기간을 소급해 검사하지 않는다.
