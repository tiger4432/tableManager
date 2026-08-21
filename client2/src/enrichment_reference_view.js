import { API_BASE } from './config.js';
import { state, isVirtualColumn, visibleRangeColIds } from './state.js';
import { elements } from './dom.js';
// The ONE TSV implementation in this codebase. Pure: no DOM, no module state, no
// clipboard API — which is exactly why importing it does not drag the app graph in
// behind it the way importing `clipboard.js` would.
import { serializeTsv } from './tsv.js';

let rulesPromise = null;
let activeRule = null;
let requestSequence = 0;
let keyboardIsolationInstalled = false;

function valueOf(row, column) {
  const cell = row?.data?.[column];
  return cell && typeof cell === 'object' ? cell.value : (cell ?? '');
}

function selectedRow() {
  if (!state.selectedCell || !state.gridApi) return null;
  return state.gridApi.getRowNode(String(state.selectedCell.rowId))?.data || null;
}

function activateReferenceTab() {
  [elements.tabGlobalBtn, elements.tabCellBtn, elements.tabRowBtn, elements.tabReferenceBtn]
    .forEach(button => button?.classList.toggle('active', button === elements.tabReferenceBtn));
  state.activeHistoryTab = 'reference';
  elements.timelineContainer.style.display = 'none';
  elements.referenceView.style.display = '';
}

export function refreshReferenceForSelection() {
  // A row change only refreshes this sidebar when the operator is actually
  // looking at it. Normal Audit History navigation stays silent and unchanged.
  if (state.activeHistoryTab === 'reference') showReferenceView();
}

export async function syncReferenceViewRule() {
  if (!rulesPromise) {
    rulesPromise = fetch(`${API_BASE}/enrichment/rules`)
      .then(res => res.ok ? res.json() : { rules: [] })
      .then(data => Array.isArray(data.rules) ? data.rules : [])
      .catch(() => []);
  }
  const rules = await rulesPromise;

  // Which of this table's rules the panel binds to.
  //
  // `find` on "has views" was the whole test while a table had at most ONE rule. It stopped
  // being a test the day a third rule landed on `dt_inventory`: three matched, the panel took
  // the first, and the only one carrying a `candidate_for` was third and therefore
  // unreachable. Nothing errored — the panel opened on a rule that declares nothing and
  // correctly fell back, which looks identical to "this feature does not work".
  //
  // A rule that DECLARES beats one that does not, because declaring is what this screen is
  // for: the operator is here to put values into cells. A rule with no `candidate_for` is a
  // display-only view, and display-only is the right answer only when nothing better exists.
  //
  // 🔴 THIS IS A STOPGAP AND THE NEXT READER MUST NOT MISTAKE IT FOR THE RULE. The panel still
  //    shows exactly ONE rule out of N, and that limitation is untouched. This criterion picks
  //    a unique answer today only because exactly one rule declares anything. On the day a
  //    SECOND declaring rule exists, `find` returns the first of those two and the arbitrary
  //    representative is back — silently, with no error, exactly as it was silent this time.
  //    What to do that day is the lead's and the owner's call, not this function's.
  const forTable = rules.filter(rule =>
    rule?.derived_table === state.currentTable && (rule.reference_views || []).length);
  const declaresAFillTarget = rule => (rule.reference_views || []).some(
    view => view && view.candidate_for && Object.keys(view.candidate_for).length > 0);
  activeRule = forTable.find(declaresAFillTarget) || forTable[0] || null;

  requestSequence++;
  if (elements.tabReferenceBtn) elements.tabReferenceBtn.style.display = activeRule ? '' : 'none';
  // On a table that declares a reference rule this is the tab the work happens in, so
  // revealing it is not enough — it is SELECTED. Offering a tab and leaving the operator on
  // Global is the screen knowing which surface the job needs and not saying so.
  //
  // Where there is no rule the previous behaviour is unchanged: hide it and stay on Global,
  // which `loadTable` has already activated by the time this runs.
  if (activeRule) showReferenceView();
  else hideReferenceView();
}

export function hideReferenceView() {
  if (elements.referenceView) elements.referenceView.style.display = 'none';
  if (elements.timelineContainer) elements.timelineContainer.style.display = '';
}

// The reference panel is a read/copy surface, not an alternate grid editor.
// Give it real focus on pointer entry and stop bubbling shortcuts before the
// document-level grid handlers see them.  We deliberately do not prevent the
// event, so browser text selection and Ctrl/Cmd+C retain their native behavior.
export function installReferenceKeyboardIsolation() {
  const panel = elements.referenceView;
  if (!panel || keyboardIsolationInstalled) return;
  keyboardIsolationInstalled = true;
  panel.tabIndex = 0;
  panel.addEventListener('pointerdown', () => panel.focus({ preventScroll: true }));
  panel.addEventListener('keydown', event => event.stopPropagation());
}

// ── [2b Phase 3.1] Which columns get pasted, and in what order ───────────────────────────
//
// THE ORDER COMES OFF `target_fields`, WHICH IS AN ARRAY, NOT OFF `candidate_for`'s KEYS.
// Both say the same thing today — measured against the live server, `target_fields` is
// ['dt_lot','dt_slot'] and the view's `candidate_for` keys arrive in that same order. But one
// of those two is order-BEARING and the other is order-INCIDENTAL: a JSON object's key order
// survives Python's dict, `json.dumps` and `JSON.parse` only for keys that are not
// integer-like, because `Object.keys` hoists integer-like keys to the front in numeric order.
// No column is named `1` today. The day one is, a paste would silently land in the wrong
// column — no error, no refusal, just values in the wrong place. Reading the array costs
// nothing and that failure mode stops existing.
//
// `candidate_for` still answers the other half, which is the half `fill_targets` could not:
// WHICH view column feeds each target. So the pair is {order: target_fields, mapping:
// candidate_for} rather than either one alone.
//
// Returns null when the rule declares nothing usable — the caller then renders exactly what
// it rendered before. A view with no `candidate_for` is a display-only view (the lead's
// evidence views are deliberately empty), and guessing a fill order for one would silently
// misalign a paste.
function fillPlan(view, rule, payloadColumns) {
  const candidateFor = view?.candidate_for;
  if (!candidateFor || typeof candidateFor !== 'object') return null;
  const targets = Array.isArray(rule?.target_fields) ? rule.target_fields : [];
  const pairs = targets
    .map(target => ({ target, column: candidateFor[target] }))
    .filter(p => typeof p.column === 'string' && p.column !== '')
    // A declared column the query did not return cannot be a fill source. Dropping it here
    // keeps the numbering contiguous instead of leaving a gap the operator has to decode.
    .filter(p => payloadColumns.includes(p.column));
  if (pairs.length === 0) return null;
  const fillColumns = pairs.map(p => p.column);
  return {
    pairs,
    // Declared columns FIRST and adjacent, everything else after in its original order. The
    // paste target is a rectangle, so the columns that feed it cannot have other columns
    // interleaved between them.
    order: [...fillColumns, ...payloadColumns.filter(c => !fillColumns.includes(c))]
  };
}

const FILL_ORDINALS = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨'];

// ── [2b Phase 3.2] Range selection ───────────────────────────────────────────────────────
//
// ONE model, held here, not on the DOM. `{viewIndex, anchor, end}` where anchor and end are
// `{row, col}` into the RENDERED grid. Drag and Shift+Arrow both move `end` and nothing else,
// which is what makes them the same gesture rather than two features that agree by accident.
//
// The view index is part of it because each reference view is its own table: a selection that
// survived a tab switch would highlight cells in a grid whose columns mean something else.
let selection = null;
let dragging = false;
let selectionKeysInstalled = false;

// ── [2b Phase 3.4] The alignment band ────────────────────────────────────────────────────
//
// 🔴 IT INFORMS. IT DOES NOT BLOCK. The migration order lists a paste-blocking gate under
// "what not to build", and for a reason that is easy to lose: pasting ONE column of a
// two-column copy is a thing people legitimately do, and a screen that refuses it is wrong
// more often than the paste is. So a mismatch is a warning the operator can read and ignore.
//
// The single hard verdict is 「불가」, and even that does not block the keystroke — it says
// the paste cannot land, because the SERVER refuses a write to a virtual join column and the
// refusal is BATCH-level: one such cell in the range loses the whole pasted block, not just
// that cell. The band exists so that 400 is predicted on screen instead of discovered after.

/** The columns the paste would land on, read from the main grid's own range. */
function targetColumnIds() {
  const cols = visibleRangeColIds();
  const start = state.dragStartCell?.colId;
  const end = state.dragEndCell?.colId;
  if (start && end) {
    const a = cols.indexOf(start);
    const b = cols.indexOf(end);
    if (a >= 0 && b >= 0) return cols.slice(Math.min(a, b), Math.max(a, b) + 1);
  }
  // No range drawn yet: a single focused cell is a 1-wide target, which is the common case
  // for filling one value.
  const single = state.selectedCell?.colId;
  return single ? [single] : [];
}

/**
 * The derived-table columns this rule fills, in paste order — the main grid's ①②.
 *
 * Reads `target_fields` for the same reason `fillPlan` does: it is the order-BEARING
 * declaration. Empty until `syncReferenceViewRule` has resolved, which is why the caller
 * re-applies the column defs once it has rather than building them and hoping.
 */
export function fillTargetOrdinals() {
  const targets = activeRule?.target_fields;
  if (!Array.isArray(targets)) return new Map();
  return new Map(targets.map((column, index) => [column, FILL_ORDINALS[index] || `${index + 1}`]));
}

/** The column names inside the panel's current selection, left to right. */
function selectedColumnNames() {
  const rect = selectionRect();
  const table = elements.referenceViewContent
    ?.querySelectorAll('.reference-view-table')[selection?.viewIndex];
  if (!rect || !table) return [];
  return [...table.querySelectorAll('thead th')]
    .filter(th => th.dataset.column !== undefined)
    .slice(rect.c0, rect.c1 + 1)
    .map(th => th.dataset.column);
}

/**
 * The band's whole decision, as a pure function of the two column lists.
 *
 * SEPARATED FROM THE DOM ON PURPOSE. This is the part that can be wrong in a way nobody
 * sees — a comparison that only counts columns still shows a green band while the paste
 * lands sideways — so it is the part a harness has to be able to score without a browser.
 * `isVirtual` arrives as an argument rather than being imported here for the same reason.
 *
 * 🔴 NO ARITY BRANCH. The lists carry their own lengths; a two-column case and a
 * three-column case take the same path.
 */
export function alignmentVerdict(sourceCols, targetCols, isVirtual) {
  const rowsLabel = count => `${count}행 × ${sourceCols.length}열`;
  const arrow = list => list.length ? list.join(' → ') : '—';
  // 🔴 `isVirtualColumn`, NOT `joinResolvedColumn`. The question is "will the server refuse a
  // WRITE here", which is what that predicate answers; a `collide` column is join-resolved
  // AND writable, so the wider one would refuse a paste that would have worked.
  const blocked = targetCols.filter(isVirtual);
  // Names AND order AND count — any one of the three differing is a mismatch. Comparing only
  // the count is the defect this is written to make visible.
  const same = sourceCols.length === targetCols.length
    && sourceCols.every((name, index) => name === targetCols[index]);
  if (blocked.length) {
    return { state: 'blocked', blocked, rowsLabel,
      body: `불가 — 조인 컬럼 ${blocked.join(', ')} 포함 · 대상에서 빼고 붙여넣기` };
  }
  if (same) return { state: 'match', blocked, rowsLabel, body: `열 순서 일치 · ${arrow(sourceCols)}` };
  return { state: 'warn', blocked, rowsLabel,
    body: `열 순서 불일치 · 복사 ${arrow(sourceCols)} / 대상 ${arrow(targetCols)}` };
}

function updateAlignmentBand() {
  const band = elements.referenceAlignment;
  if (!band) return;
  const rect = selectionRect();
  if (!rect) { band.style.display = 'none'; return; }
  band.style.display = '';

  const sourceCols = selectedColumnNames();
  const targetCols = targetColumnIds();
  const verdict = alignmentVerdict(sourceCols, targetCols, isVirtualColumn);

  // 🔴 THE MISMATCH LABEL IS NOT SHOWN (owner, 2026-08-21: "그냥 없애"). Pasting two copied
  // columns into one target is something people do on purpose, so a band that turns red every
  // time the shapes differ is crying wolf on the normal case — and a warning that fires on
  // normal use is one the operator learns to read past, including on the day it is right.
  //
  // The other two states stay: the green match is the mockup's own badge, and `blocked` is not
  // an opinion about tidiness — the server refuses that write batch-wide, so the band is
  // predicting a 400 rather than grading the operator.
  if (verdict.state === 'warn') { band.style.display = 'none'; return; }

  const rows = rect.r1 - rect.r0 + 1;

  band.classList.remove('is-match', 'is-warn', 'is-blocked');
  band.classList.add(`is-${verdict.state}`);

  // Mockup 2b: the copied column order, then a pill for the verdict, then the keystroke pair
  // pushed right. The row count rides in the pill rather than leading the strip — the order
  // is what the operator has to check before pasting, and it should be the first thing read.
  band.replaceChildren();
  const order = document.createElement('span');
  order.className = 'alignment-order';
  order.textContent = sourceCols.map(c => c.toUpperCase()).join(' → ');
  const pill = document.createElement('span');
  pill.className = 'pill alignment-pill';
  pill.textContent = verdict.state === 'blocked'
    ? verdict.body
    : `${verdict.rowsLabel(rows)} · 대상 열 순서와 일치`;
  const keys = document.createElement('span');
  keys.className = 'alignment-keys';
  ['Ctrl', 'C', '→', 'Ctrl', 'V'].forEach(k => {
    const el = document.createElement('span');
    if (k !== '→') el.className = 'kbd';
    el.textContent = k;
    keys.appendChild(el);
  });
  band.append(order, pill, keys);
}

function selectionRect() {
  if (!selection) return null;
  const { anchor, end } = selection;
  return {
    r0: Math.min(anchor.row, end.row), r1: Math.max(anchor.row, end.row),
    c0: Math.min(anchor.col, end.col), c1: Math.max(anchor.col, end.col)
  };
}

// Paints the current rectangle. Reuses `.custom-range-selected` — the grid's own name for
// this state — rather than inventing a second one, so the two surfaces cannot drift apart.
function paintSelection() {
  const host = elements.referenceViewContent;
  if (!host) return;
  const rect = selectionRect();
  host.querySelectorAll('td[data-row]').forEach(td => {
    const inView = Number(td.dataset.view) === selection?.viewIndex;
    const row = Number(td.dataset.row);
    const col = Number(td.dataset.col);
    const inRect = !!rect && inView && row >= rect.r0 && row <= rect.r1 && col >= rect.c0 && col <= rect.c1;
    td.classList.toggle('custom-range-selected', inRect);
  });
  updateAlignmentBand();
}

// Shift+Arrow extends the same rectangle the mouse drags. Installed on the panel, which
// already swallows keydown so these never reach the main grid's handlers — that isolation
// exists for exactly this reason and predates this round.
function installSelectionKeys() {
  const panel = elements.referenceView;
  if (!panel || selectionKeysInstalled) return;
  selectionKeysInstalled = true;
  // On the DOCUMENT, not the table: a drag that leaves the panel and releases over the grid
  // would otherwise never end, and the next hover would keep extending a range the operator
  // let go of.
  // Also refreshes the band: a drag that ended in the MAIN grid changed the paste target
  // without touching this panel, and the band would otherwise describe the previous target.
  document.addEventListener('mouseup', () => { dragging = false; updateAlignmentBand(); });

  // ── [2b Phase 3.3] Copy ────────────────────────────────────────────────────────────────
  //
  // WHY THIS MODULE DOES NOT IMPORT `clipboard.js`. That module pulls `grid.js`, `ui.js` and
  // `effort_meter.js` behind it, none of which this panel needs — it already has the three it
  // does need (`config`, `state`, `dom`). The constraint is about which way the dependency
  // points, NOT about avoiding reuse: the serializer below IS the shared one, and the
  // header toggle IS the grid's own control.
  //
  // `serializeTsv` from `tsv.js`, never a second TSV writer. That module is the single
  // implementation the clipboard path and the company-form round trip share, and its quoting
  // is the part that is easy to get wrong — a value holding a tab or a newline has to survive
  // the round trip rather than be flattened into spaces.
  //
  // `e.clipboardData`, never `navigator.clipboard`: production is plain-HTTP, a non-secure
  // context where that object is simply undefined. `scripts/check_clipboard_convention.mjs`
  // enforces this at prebuild.
  //
  // 🔴 `clipboard.js`'s own document-level `copy` handler ALREADY steps aside for this panel
  // (`e.target.closest('#reference-view')`), added when the panel was a native-text surface.
  // It is still exactly the guard this needs, so nothing was added there — a second guard
  // saying the same thing is how two of them later disagree.
  document.addEventListener('copy', event => {
    const panel = elements.referenceView;
    if (!selection || !panel || !panel.contains(document.activeElement)) return;
    const rect = selectionRect();
    const table = elements.referenceViewContent
      ?.querySelectorAll('.reference-view-table')[selection.viewIndex];
    if (!rect || !table) return;

    const matrix = [];
    // The grid's OWN toggle, not a second one. Two switches meaning the same thing is how an
    // operator ends up with headers in one surface and not the other.
    if (elements.copyHeaderToggle?.checked) {
      const heads = [...table.querySelectorAll('thead th')];
      matrix.push(heads
        .filter(th => th.dataset.column !== undefined)
        .slice(rect.c0, rect.c1 + 1)
        .map(th => th.dataset.column));
    }
    for (let row = rect.r0; row <= rect.r1; row++) {
      const line = [];
      for (let col = rect.c0; col <= rect.c1; col++) {
        line.push(table.querySelector(`td[data-row="${row}"][data-col="${col}"]`)?.textContent ?? '');
      }
      matrix.push(line);
    }
    event.clipboardData.setData('text/plain', serializeTsv(matrix));
    event.preventDefault();
  });
  panel.addEventListener('keydown', event => {
    if (!selection || !event.shiftKey) return;
    const delta = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[event.key];
    if (!delta) return;
    const table = elements.referenceViewContent
      ?.querySelectorAll('.reference-view-table')[selection.viewIndex];
    if (!table) return;
    // Clamped to the grid it is in. Without this the rectangle keeps growing past the last
    // row and the copy silently carries blank trailing lines.
    const rows = table.querySelectorAll('tbody tr').length;
    const cols = table.querySelectorAll('thead th').length - 1; // minus the row-number gutter
    selection.end = {
      row: Math.min(Math.max(selection.end.row + delta[0], 0), rows - 1),
      col: Math.min(Math.max(selection.end.col + delta[1], 0), cols - 1)
    };
    event.preventDefault();
    paintSelection();
  });
}

function render(results) {
  const host = elements.referenceViewContent;
  host.replaceChildren();
  const band = document.createElement('div');
  band.id = 'reference-alignment';
  // Phase 0: the SAME banner, not a lookalike. `.tx-filter-banner` carries the structure and
  // geometry; `.reference-alignment` is a colour variant on top of it.
  band.className = 'tx-filter-banner reference-alignment';
  band.style.display = 'none';
  const tabs = document.createElement('div');
  tabs.className = 'reference-view-tabs';
  const panels = document.createElement('div');
  panels.className = 'reference-view-panels';
  const selectView = (index) => {
    Array.from(tabs.children).forEach((button, tabIndex) => button.classList.toggle('active', tabIndex === index));
    Array.from(panels.children).forEach((panel, panelIndex) => { panel.style.display = panelIndex === index ? '' : 'none'; });
    // A selection belongs to the grid it was made in. Carrying it across a tab switch would
    // leave a rectangle highlighted over columns that mean something else.
    selection = null;
    dragging = false;
    paintSelection();
  };
  results.forEach(({ view, payload, error }, index) => {
    const tab = document.createElement('button');
    tab.type = 'button'; tab.className = 'reference-view-tab'; tab.textContent = view.label || `Reference ${index + 1}`;
    tab.addEventListener('click', () => selectView(index));
    tabs.appendChild(tab);
    const section = document.createElement('section'); section.className = 'reference-view-section';
    if (error || !payload.rows?.length) {
      const empty = document.createElement('div'); empty.className = 'reference-view-empty'; empty.textContent = error || '참조 행이 없습니다.'; section.appendChild(empty);
    } else {
      const table = document.createElement('table'); table.className = 'reference-view-table';
      const columns = payload.columns || [];
      const plan = fillPlan(view, activeRule, columns);
      const shown = plan ? plan.order : columns;
      // 🔴 THE ORIGINAL INDEX, KEPT. `payload.rows` may be positional arrays, so a reordered
      // header must still read each cell from the column's position in `payload.columns` —
      // reordering the header alone would shift every value one column sideways and the
      // table would still look plausible.
      const sourceIndex = new Map(columns.map((column, index) => [column, index]));
      const fillOrdinal = new Map((plan?.pairs || []).map((p, i) => [p.column, FILL_ORDINALS[i] || `${i + 1}`]));

      const head = document.createElement('thead'); const header = document.createElement('tr');
      // The row-number gutter, same idea as the main grid's `#` column: it gives the operator
      // a way to say "rows 3 to 7" out loud, and it gives the drag somewhere to start that is
      // not a value.
      const gutterHead = document.createElement('th');
      gutterHead.className = 'reference-view-gutter';
      gutterHead.textContent = '#';
      header.appendChild(gutterHead);
      shown.forEach(column => {
        const th = document.createElement('th');
        const ordinal = fillOrdinal.get(column);
        // The number is the paste order, so it belongs on the column that will be pasted.
        // Without it the reordering is unexplained and the operator has to trust it.
        th.textContent = ordinal ? `${ordinal} ${column}` : column;
        // The BARE name, kept beside the decorated label. A copy with headers must carry
        // `dt_lot`, not `① dt_lot` — the ordinal is this screen's explanation of paste order
        // and means nothing in the cell you paste into.
        th.dataset.column = column;
        if (ordinal) th.className = 'reference-view-fill';
        header.appendChild(th);
      });
      head.appendChild(header); table.appendChild(head);
      const body = document.createElement('tbody');
      payload.rows.forEach((row, rowIndex) => {
        const tr = document.createElement('tr');
        const gutter = document.createElement('td');
        gutter.className = 'reference-view-gutter';
        gutter.textContent = String(rowIndex + 1);
        tr.appendChild(gutter);
        shown.forEach((column, colIndex) => {
          const td = document.createElement('td');
          const at = sourceIndex.get(column);
          td.textContent = Array.isArray(row) ? (row[at] ?? '') : (row?.[column] ?? '');
          if (fillOrdinal.has(column)) td.className = 'reference-view-fill';
          // The coordinates the selection model works in. Held on the cell rather than
          // recomputed from `cellIndex`, because the gutter offsets that by one and every
          // reader would have to remember the offset.
          td.dataset.view = String(index);
          td.dataset.row = String(rowIndex);
          td.dataset.col = String(colIndex);
          tr.appendChild(td);
        });
        body.appendChild(tr);
      });
      table.appendChild(body);

      // Drag. `mousedown` seeds anchor and end together so a single click is a 1x1 range,
      // and `mouseover` only moves `end` while the button is down.
      table.addEventListener('mousedown', event => {
        const td = event.target.closest('td[data-row]');
        if (!td) return;
        const at = { row: Number(td.dataset.row), col: Number(td.dataset.col) };
        selection = { viewIndex: index, anchor: at, end: at };
        dragging = true;
        // Stops the browser turning the drag into a text selection, which would paint its own
        // highlight over this one and put different text on the clipboard.
        event.preventDefault();
        paintSelection();
      });
      table.addEventListener('mouseover', event => {
        if (!dragging || selection?.viewIndex !== index) return;
        const td = event.target.closest('td[data-row]');
        if (!td) return;
        selection.end = { row: Number(td.dataset.row), col: Number(td.dataset.col) };
        paintSelection();
      });

      section.appendChild(table);
    }
    panels.appendChild(section);
  });
  host.append(band, tabs, panels);
  installSelectionKeys();
  if (results.length) selectView(0);
}

export async function showReferenceView() {
  if (!activeRule) return;
  activateReferenceTab();
  const row = selectedRow();
  if (!row) { elements.referenceViewContent.textContent = '그리드에서 참조할 행을 먼저 선택하세요.'; return; }
  const params = Object.fromEntries((activeRule.decision_key || []).map(column => [column, valueOf(row, column)]));
  if (Object.values(params).some(value => String(value).trim() === '')) { elements.referenceViewContent.textContent = '선택 행의 결정 키가 비어 있어 참조뷰를 조회할 수 없습니다.'; return; }
  const sequence = ++requestSequence;
  elements.referenceViewContent.textContent = '참조뷰 조회 중…';
  const results = await Promise.all((activeRule.reference_views || []).map(async (view, index) => {
    try {
      const res = await fetch(`${API_BASE}/enrichment/rules/${encodeURIComponent(activeRule.name)}/references/${index}?params=${encodeURIComponent(JSON.stringify(params))}`);
      const payload = await res.json();
      return res.ok ? { view, payload } : { view, error: payload.detail || `HTTP ${res.status}` };
    } catch { return { view, error: '참조뷰 요청에 실패했습니다.' }; }
  }));
  if (sequence === requestSequence) render(results);
}
