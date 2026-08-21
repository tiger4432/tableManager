import { API_BASE } from './config.js';
import { state } from './state.js';
import { elements } from './dom.js';

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

function render(results) {
  const host = elements.referenceViewContent;
  host.replaceChildren();
  const tabs = document.createElement('div');
  tabs.className = 'reference-view-tabs';
  const panels = document.createElement('div');
  panels.className = 'reference-view-panels';
  const selectView = (index) => {
    Array.from(tabs.children).forEach((button, tabIndex) => button.classList.toggle('active', tabIndex === index));
    Array.from(panels.children).forEach((panel, panelIndex) => { panel.style.display = panelIndex === index ? '' : 'none'; });
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
      shown.forEach(column => {
        const th = document.createElement('th');
        const ordinal = fillOrdinal.get(column);
        // The number is the paste order, so it belongs on the column that will be pasted.
        // Without it the reordering is unexplained and the operator has to trust it.
        th.textContent = ordinal ? `${ordinal} ${column}` : column;
        if (ordinal) th.className = 'reference-view-fill';
        header.appendChild(th);
      });
      head.appendChild(header); table.appendChild(head);
      const body = document.createElement('tbody');
      payload.rows.forEach(row => {
        const tr = document.createElement('tr');
        shown.forEach(column => {
          const td = document.createElement('td');
          const at = sourceIndex.get(column);
          td.textContent = Array.isArray(row) ? (row[at] ?? '') : (row?.[column] ?? '');
          if (fillOrdinal.has(column)) td.className = 'reference-view-fill';
          tr.appendChild(td);
        });
        body.appendChild(tr);
      });
      table.appendChild(body); section.appendChild(table);
    }
    panels.appendChild(section);
  });
  host.append(tabs, panels);
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
