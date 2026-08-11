# 참조뷰가 이미 열려 있던 사이드바 안으로 enrichment 페이지 하나를 접었다

**날짜:** 2026-08-11 07:18 · **커밋:** `1e29078` · **레인:** 클라(client2)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

`enrichment.html`은 별도 페이지였다. 그리드에서 결손 값을 보다가 참조 자료를 확인하려면
그 페이지로 나가야 했고, 돌아오면 선택했던 셀·스크롤 위치가 사라졌다. 신고는 「참조 한 번
보려고 화면을 통째로 잃는다」였다.

## 무엇이 바뀌었나

메인 그리드의 이력 사이드바(Cell History·Row History 옆)에 **참조뷰 탭**이 새로 생겼다.
새 모듈 `client2/src/enrichment_reference_view.js`(118줄)가 셀 클릭 시
`refreshReferenceForSelection`, 테이블 전환 시 `syncReferenceViewRule`로 현재 선택을
반영해 채운다.

```js
export function refreshReferenceForSelection() {
  // A row change only refreshes this sidebar when the operator is actually
  // looking at it. Normal Audit History navigation stays silent and unchanged.
  if (state.activeHistoryTab === 'reference') showReferenceView();
}
```

뱃지·뱃지 클릭 핸들러·nav 드롭다운의 enrichment.html 링크는 제거됐다. `enrichment.html`
파일 자체는 이 커밋에서 손대지 않았고, 더는 어디서도 링크되지 않을 뿐이다(파일 삭제는
다음 커밋 `ab36fab`).

## 사이드바가 필요했지만 없었던 동작 둘

**복사.** `#reference-view` 안의 복사는 브라우저 기본 동작에 맡긴다. 그리드의 전역 `copy`
핸들러가 그리드 선택이 남아 있으면(거의 항상 남아 있다) 사이드바에서 하이라이트한 텍스트를
자기 range/row TSV로 덮어써서, 참조뷰 안의 텍스트는 선택은 되는데 복사는 안 되는 상태였다.

```js
if (e.target instanceof Element && e.target.closest('#reference-view')) {
  return;
}
```

**적재 완료 브로드캐스트.** 종전엔 `state.pageCache.clear()` 뒤 `fetchData(true)`를 호출해
페이지 전체를 다시 읽었다 — 조작자가 보던 문맥을 그대로 갈아치웠다. 행 단위 브로드캐스트는
이미 자기 델타를 병합하므로, 이 커밋은 캐시 무효화만 남기고 `fetchData(true)` 호출을 뺐다.

```js
// Keep the currently inspected grid stable.  Row-level broadcast events
// already merge their deltas below; an ingestion-complete notification
// must not replace the whole page and steal the operator's context.
state.pageCache.clear();
triggerHistoryReloadDebounced();
```

`batch_refresh_required` 이벤트도 같은 방식으로 바뀌었다 — 캐시만 비우고 화면은 다음
명시적 새로고침을 기다린다.

## 검증

이 커밋의 본문에는 하네스·pytest 수치가 없다. 언급되는 것은 `dist rebuilt:
main-BW4a1zS3.js, map_editor-CeSfyMRg.js, style-8s5Ut0Az.css`뿐이다 — 빌드가 됐다는
사실 이상은 이 커밋 자체가 주장하지 않는다.

## 그때 남아 있던 것

- `enrichment.html` 파일과 그 vite 엔트리는 이 시점에 아직 살아 있다 — 링크만 제거됐다.
  삭제는 두 커밋 뒤 `ab36fab`.
- 뱃지 배후 로직(`updateEnrichmentBadge`·`notifyEnrichmentTableEvent`)과 관리자 화면의
  관련 링크 넷은 이 커밋에서 손대지 않았다 — 다음 커밋 `5116f67`이 정리한다.
- `websocket.js`에서 `notifyEnrichmentTableEvent` import가 제거됐지만, 그 함수 정의와
  admin.js 쪽 호출부는 이 시점에 아직 파일에 남아 있다.
