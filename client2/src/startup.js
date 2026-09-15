// STARTUP — the grid page's boot ORDER, in a module node can import.
//
// WHY THIS IS ITS OWN FILE (C-110, 2026-09-16). The order below used to be the body of
// `init()` in main.js, and main.js cannot be imported outside a browser (it imports ag-grid's
// stylesheets and seats the whole page). The harness that scores this order —
// `tests/startup_socket_gate_harness.mjs` — therefore sliced `init()` out of main.js as text
// and ran the fragment in `vm`, which measured the SHAPE OF THE LETTERS rather than the order:
// every new module-level name main.js gained (`redoBannerFollows` on 2026-09-15 was the
// latest) made every section-C scenario (8 handle sets × 3 failure modes) throw ReferenceError
// on correct code, and each time the harness grew a stub. That is the slicing the owner
// forbade (CLAUDE.md, 2026-09-02).
// With the order living here, the harness imports it; main.js can add whatever it likes.
//
// 🔴 NOTHING HERE TOUCHES THE DOM OR CSS AT MODULE TOP LEVEL, and that is the property that
//    makes the file importable. What DOES touch the DOM is handed in by the caller as
//    `prepare` and `tableChosen`, so this file knows the order and nothing else.
import { initWebSocket } from './websocket.js';
import { checkServerHealth, loadTables } from './api.js';

/**
 * Boot the page.
 *
 * @param {object} hooks
 * @param {() => void} hooks.prepare       everything else startup installs (listeners, cached
 *                                         settings, the assembled parts). May throw on a
 *                                         missing DOM handle — see below for why that is
 *                                         allowed to happen AFTER the socket, never before.
 * @param {() => void} hooks.tableChosen   runs once the table list is loaded and the first
 *                                         table auto-selected; the caller reads
 *                                         `state.currentTable` and tells its parts.
 */
export async function startup({ prepare, tableChosen }) {
  // THE LIVE CHANNEL IS NOT GATED ON ANYTHING ELSE. This used to be the LAST statement of
  // `init()`, after `await checkServerHealth()` and `await loadTables()`. Since the whole
  // reconnect ladder lives inside `initWebSocket`, anything that stopped startup short of this
  // line left the page with no socket AND no retry, for the rest of the session — reproduced
  // three ways (see startup_socket_gate_harness.mjs): a `catch` block that itself throws on a
  // null DOM handle, and a `fetch` that never settles (a hung backend or proxy), which does not
  // even reject and so logs nothing at all.
  //
  // FIRST, not merely "earlier". Every setup call in `prepare` can throw too (an unguarded
  // `elements.x.checked` is one), so the socket goes ahead of ALL of it. Opening it has no
  // dependency on health status or the table list: `initWebSocket` reads only WS_URL, `state`,
  // and the wake signals, and its `onopen` re-derives what it needs (`checkServerHealth`, then
  // `loadTables` only if the picker is still empty). The overlap that creates with
  // `loadTables()` below is de-duplicated by an in-flight latch in api.js.
  initWebSocket();

  prepare();

  // The socket is already open (first line). These two cannot gate it any more.
  // 📌 Still open: if `checkServerHealth` rejected, `loadTables` would be skipped and the table
  //    list would stay empty. Both are written not to reject; wrapping them here as well is a
  //    separate change with its own harness anchors, not something to fold into this move.
  await checkServerHealth();
  await loadTables();

  tableChosen();
}
