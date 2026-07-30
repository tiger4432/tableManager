# 스마트 붙여넣기 — 평문 HTTP에서 읽을 수 없던 경로를 걸쇠로 되살림

**일자:** 2026-07-30 · **도메인:** Client (client2) · **등급:** T2 (인제션 경로 = 쓰기)

## 문제

사용자 보고: 「무슨 read 막혔다고 작동안하네」.

`main.smartPasteViaIngestion`은 전량 `navigator.clipboard.read()` / `readText()` 위에 서 있었다.
운영은 사내망 **평문 HTTP = 비보안 컨텍스트**라 `navigator.clipboard`가 **통째로 `undefined`**다.
그래서 가드 `navigator.clipboard && navigator.clipboard.read`가 거짓이 되어 else 분기로 떨어지고,
그 else가 **같은 undefined 객체의 `readText()`**를 부른다. 바깥 `try/catch`가 그 TypeError를
「❌ 스마트 붙여넣기 중 오류가 발생했습니다」 하나로 뭉갰다 — 사용자가 알 수 있는 것은 "read"까지였다.

`7694b42`가 **복사(Copy to Excel)** 쪽에서 고친 것과 **글자 그대로 같은 결함**이고, 방향만 반대다.

격리 스택 실측(비보안 조건 재현):

```
OLD SHAPE THROWS: TypeError: Cannot read properties of undefined (reading 'readText')
document.execCommand('paste') -> false      # 웹 콘텐츠에서 차단
```

## 구조 — 쓰기와 읽기는 대칭이 아니다

쓰기는 `execCommand('copy')`로 합성 이벤트를 일으켜 `e.clipboardData`를 갈아끼울 수 있다.
읽기에는 그 수가 없다. 평문 HTTP에서 클립보드를 읽는 문은 **네이티브 `paste` 이벤트 하나뿐**이고,
**버튼은 그 문을 열 수 없다.** `map_editor.js:6299`가 이미 적어둔 규칙과 같다.

그래서 두 동선을 **걸쇠(latch) 하나**로 합류시켰다.

| 진입 | 동작 |
|---|---|
| `Ctrl+Shift+V` | 걸쇠를 걸고 **`preventDefault()`하지 않는다** — 브라우저 자체 붙여넣기 명령이 `paste` 이벤트를 만들어야 읽을 수 있다. 600ms 안에 이벤트가 없으면 걸쇠를 15초로 늘리고 「이어서 Ctrl+V」를 안내 |
| 우클릭 메뉴 / 버튼 | 읽지 못한다. 보안 컨텍스트면 `navigator.clipboard.read()`를 먼저 쓰고, 아니면 걸쇠를 걸고 **누를 키를 한 줄로** 알린다 (새 패널·모드·모달 없음) |
| `paste` 이벤트 | `clipboard.js` 핸들러가 입력 필드 가드 직후·`gridApi` 가드보다 먼저 걸쇠를 확인. 걸려 있으면 `main.smartPasteFromPasteEvent`로 넘기고 1회 소비, 아니면 **평소의 범위 붙여넣기 그대로** |

- **다중 포맷은 유지했다.** `e.clipboardData.types`/`getData(type)`로 후보를 모아 기존
  `showClipboardTypeModal`을 그대로 쓴다 — text/plain으로 몰래 강등하지 않는다.
- ⚠️ **첫 `await` 이전에 모든 후보를 스냅샷**한다. `paste` 이벤트의 `DataTransfer`는 디스패치
  중에만 읽히므로, 모달을 `await`한 뒤 `getData()`를 부르면 **빈 문자열**이 올라간다(초록 토스트가
  덮는 조용한 데이터 손실).
- **무장 시점의 테이블을 기억**한다(`smartPasteArmedTable`). 15초 창 안에 테이블이 바뀌면 업로드를
  거절한다 — 이 경로는 **적재**를 하므로 엉뚱한 테이블에 들어가면 UI 불편이 아니라 데이터 사고다.
- `navigator.clipboard`가 없다고 판단한 분기에서 **다시 `navigator.clipboard`를 부르지 않는다.**
  모든 분기가 **자기가 부를 바로 그 메서드**로 가드한다.

## 실패 문구도 수리 대상이었다

일반 catch-all 토스트가 이 결함을 자가 해결 불가능한 문의로 만들었다. 모든 거절이 원인과 다음 행동을 말한다.

- 클립보드를 읽을 수 없음 → 「이 환경(평문 HTTP)에서는 버튼이 클립보드를 읽을 수 없습니다. 지금 Ctrl+V 를 눌러 주세요. (취소: Esc)」
- 텍스트 포맷 없음 → 「클립보드에 텍스트 형식이 없습니다. (감지된 형식: Files)」
- 빈 클립보드 → 「클립보드가 비어 있습니다. 복사한 뒤 다시 시도해 주세요.」
- 서버 거부 → 「서버가 스마트 붙여넣기를 거부했습니다 (HTTP 4xx).」 / 전송 실패 → 「서버에 전송하지 못했습니다.」 (클립보드 실패와 구분)
- 테이블 변경 → 「테이블이 [A] → [B] 로 바뀌어 취소했습니다.」

토스트 컴포넌트가 자체 아이콘을 붙이므로 문구 앞의 중복 이모지를 제거했다(종전 「❌❌ …」).
지시형 토스트는 `dismissToasts('smart-paste-arm')`로 **붙여넣기가 끝나는 즉시 회수**한다 —
이미 실행된 행동을 계속 지시하는 안내는 그 자체가 결함이다.

## 검증 (격리 스택 8081, `navigator.clipboard`를 `undefined`로 스텁한 비보안 조건)

| 항목 | 결과 |
|---|---|
| 종전 형태 재연(음성 대조군) | `TypeError: ... (reading 'readText')` — 진단과 일치 |
| `execCommand('paste')` | `false` (차단 확인) |
| 우클릭 진입 | 원인+키 안내 토스트, JS 에러 0 |
| 다중 포맷 paste | 모달 2종 제시 → HTML 선택 → **114바이트 HTML 원문**이 그대로 업로드, 성공 토스트가 포맷·파일명 명시 |
| 단일 포맷 paste | 모달 없이 직행, `.txt` 확장자·내용 일치 |
| 걸쇠 1회성 | 두 번째 paste는 **평소 범위 붙여넣기**로 낙하(`Staged clipboard paste: 1 total pending edits`) |
| 무장 없는 paste | 범위 붙여넣기 정상 — **기존 Ctrl+V 회귀 없음** |
| Esc | 예약 해제 + 이후 paste는 범위 붙여넣기 |
| 무장 후 테이블 변경 | 업로드 0회, 「테이블이 [test] → [parts] 로 바뀌어 취소했습니다」 |
| 텍스트 포맷 없음 / 빈 클립보드 | 각각 감지 포맷 명시 / 비어 있음 명시 |
| prebuild 게이트 | `check:clipboard` OK · `check:contracts` 4/4 · `check:suggest-keys` OK |

⚠️ **미확인 1건**: 브라우저가 `Ctrl+Shift+V`를 실제로 붙여넣기 명령으로 번역하는지는 확인하지 못했다
(자동화 도구의 키 주입이 CDP 합성 이벤트라 Chrome의 편집 명령을 타지 않는다 — 대조로 `Ctrl+V`도
paste 이벤트를 만들지 못했다). **설계가 그 답에 의존하지 않도록** 600ms 에스컬레이션을 넣었으므로
어느 쪽이든 동작하지만, 운영 QA에서 실제 키로 확인이 필요하다.

## 변경 파일

- `client2/src/main.js` — 스마트 페이스트 전면 재작성, `Ctrl+Shift+V` 바인딩, Esc 회수
- `client2/src/clipboard.js` — `registerSmartPasteHandler` 훅 + paste 핸들러 걸쇠 분기
- `client2/src/state.js` — `smartPasteArmedUntil` / `smartPasteArmedTable`
- `client2/src/utils.js` — `dismissToasts(dedupeKey)`
- `client2/index.html` — 컨텍스트 메뉴 라벨에 단축키 표기
- `docs/architecture/frontend.md` §2.1-ter 신설 · `docs/qa/FEATURE_CHECKLIST.md` 점검 항목 재작성
