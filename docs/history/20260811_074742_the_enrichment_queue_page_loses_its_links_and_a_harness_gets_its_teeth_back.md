# enrichment 큐 페이지가 내비게이션에서 은퇴했고, 실패 못 하던 하네스가 이빨을 되찾았다

**날짜:** 2026-08-11 07:47 · **커밋:** `5116f67` · **레인:** 클라(client2, enrichment 정리)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

제품 소유자 판정: `enrichment.html`은 내비게이션에서 은퇴한다. 파일과 vite 엔트리는
남기고, **그것을 가리키던 모든 것**과 두 커밋 전(`1e29078`) 뱃지가 빠지면서 남긴 잔해를
정리하는 것이 이 커밋의 범위다.

## admin.js에서 지운 점프 넷

넷 중 둘은 `?rule=`을 실었는데, `switchTab('enrichment')`로 보낼 수 없었다 — **두 버튼이
이미 그 탭 안에 있었다**(하나는 규칙 행마다, 하나는 규칙을 포커스해야만 렌더되는 진단
패널 안). 자기 위치로 보내는 것은 no-op이다. admin에서 규칙을 포커스하는 것은 행 클릭
핸들러로 여전히 되지만, **이름 붙은 규칙의 결손 입력 워크리스트를 여는 기능 자체는
대체물 없이 사라졌다.**

UI 문구 셋이 사라진 버튼을 지칭하고 있어 거짓이 됐고, 「교정은 그리드에서, 이 프로젝트의
교정 표면이며 사이드바 참조뷰가 그 옆에서 참조를 보여준다」는 판정으로 다시 썼다.

죽은 뱃지 코드(`updateEnrichmentBadge`·`notifyEnrichmentTableEvent`, 호출자 0)와
`#enrichment-badge` 규칙, `websocket.js`의 고아 주석도 함께 제거됐다.

## 하네스 수리 — 실패 개수가 말해 주지 않던 더 큰 문제

`1e29078`이 `installReferenceKeyboardIsolation`을 `init`에 더하면서
`startup_socket_gate_harness`의 샌드박스에 그 협력자를 추가하지 않았다. 그래서 그 스윕의
**모든 변이가 자기 결함이 아니라 `ReferenceError`로 죽었다**:

```
baseline  controls APPLIED 3 / ESCAPED 0 of 3, WRONGLY CAUGHT C1 C2 C3
now       mutations APPLIED 9 / CAUGHT 9, controls APPLIED 3 / ESCAPED 3 of 3
```

실패하고 있던 것은 하네스가 아니라 **제대로 실패할 수 없던 하네스**였고, 그 사실은
자기 통제군(negative control)이 스스로 말하고 있었다 — 통제군은 이스케이프해야 정상인데
셋 다 「잘못 잡힘」이었다.

이웃한 두 no-op은 `src/`에 더는 존재하지 않는 심볼을 스텁하고 있어 제거했다 —
`ran 103`이 그대로인 것이 그 심볼들이 이미 죽어 있었다는 증거다.

```js
// `init` installs the reference panel's keyboard isolation (main.js). Outside the question
// scored here, but its absence made every `init` slice die with a ReferenceError.
installReferenceKeyboardIsolation: noop,
```

## 검증

게이트 이후: **하네스 43개 보고, 어서션 25,344개, 실패 48건(종전 74건), 초록 41 / 빨강 8,
BLOCKING 0건.** 커밋 자신의 표현으로는 「베이스라인에서 정확히 한 줄만 움직였다」. 빌드는
`prebuild`를 우회하지 않고 `npm run build`로 통과.

## 그때 남아 있던 것

- `enrichment.html` 파일과 그 vite 엔트리는 이 커밋에서도 **아직 삭제되지 않았다** — 링크만
  없앤다는 이 커밋의 명시적 범위다. 실제 삭제는 두 커밋 뒤 `ab36fab`.
- 「이름 붙은 규칙의 결손 입력 워크리스트를 연다」는 기능은 **대체물 없이** 사라진 채로
  이 커밋이 끝난다 — 다음에 필요해지면 새로 설계해야 한다는 뜻이고, 이 커밋은 그것을
  「대체 없음」이라고 명시했다.
- `admin.js fetchEnrichmentStatus`는 `enrichment_queue_partition_harness.mjs`가 여전히
  **범위 밖**으로 표시한 채로 남는다 — 번들러·DOM 싱글턴 의존 때문에 bare node로 import할
  수 없다는 사유가 이 시점에도 유효하다.
