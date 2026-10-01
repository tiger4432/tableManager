// THE CLIPBOARD WRITER - moved here from map_editor.js so a second screen (the table registry's
// Copy columns, lead 72aa14785) calls it instead of writing a second one. map_editor still calls it.
//
// ── 클립보드 쓰기 — **비보안 컨텍스트에서 동작하는 유일한 경로** ────────────────────
//
// 🔴 `navigator.clipboard`는 이 앱에 없다. 운영은 LAN 평문 HTTP = 비보안 컨텍스트라
//    `navigator.clipboard`가 통째로 `undefined`다. 종전 코드는 그 undefined에 `.writeText`를
//    부르고, catch가 **같은 식을 한 번 더** 불러 결국 한글 alert로 끝났다 — 사용자가 본
//    그 팝업이다. 규약은 `clipboard.js`(그리드 복사)가 이미 지키고 있던 것과 같다:
//    **copy 이벤트의 `e.clipboardData`**.
//
//    버튼 클릭에는 사용자의 copy 키 입력이 없으므로 이벤트를 합성한다 — 화면 밖 편집 가능
//    노드를 선택하고 `document.execCommand('copy')`로 copy 이벤트를 일으킨 뒤, 그 이벤트에서
//    내용을 갈아끼운다. Windows가 `text/html`을 CF_HTML로 매핑하므로 엑셀이 서식을 읽는다.
//
//    사용자의 기존 선택 영역은 복원한다. 복사 한 번이 사용자가 잡아 둔 선택을 날리면 안 된다.
export function writeClipboardRich(html, text) {
  const sel = window.getSelection ? window.getSelection() : null;
  const saved = (sel && sel.rangeCount > 0) ? sel.getRangeAt(0).cloneRange() : null;
  // The hidden holder has to TAKE focus to receive the copy, and removing it drops focus on
  // <body>. Harmless from the toolbar button (nothing had focus), but a keyboard caller
  // would come back to a page that lost its focused control, so put it back.
  const prevActive = document.activeElement;

  const holder = document.createElement('div');
  holder.setAttribute('contenteditable', 'true');
  holder.setAttribute('aria-hidden', 'true');
  holder.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;overflow:hidden;';
  holder.textContent = ' ';
  document.body.appendChild(holder);

  let served = false;
  const onCopy = (e) => {
    if (!e.clipboardData) return;      // 갈아끼우지 못하면 served=false로 남아 정직하게 실패한다
    // Text alone when there is no HTML: an empty HTML part is what Excel would read first.
    if (html) e.clipboardData.setData('text/html', html);
    e.clipboardData.setData('text/plain', text);
    e.preventDefault();
    served = true;
  };

  let fired = false;
  document.addEventListener('copy', onCopy, true);
  try {
    if (sel) {
      const range = document.createRange();
      range.selectNodeContents(holder);
      sel.removeAllRanges();
      sel.addRange(range);
    }
    holder.focus();
    fired = document.execCommand('copy');
  } catch (err) {
    console.debug('[clipboard] execCommand copy threw', err);
  } finally {
    document.removeEventListener('copy', onCopy, true);
    holder.remove();
    // 포커스를 먼저 되돌리고 선택을 되돌린다 — 순서가 반대면 포커스 이동이 방금 복원한 선택을 지운다.
    if (prevActive && prevActive !== document.body && prevActive.focus && document.contains(prevActive)) {
      try { prevActive.focus({ preventScroll: true }); } catch (_) { /* not focusable anymore */ }
    }
    if (sel) {
      sel.removeAllRanges();
      if (saved) sel.addRange(saved);
    }
  }
  return fired && served;
}
