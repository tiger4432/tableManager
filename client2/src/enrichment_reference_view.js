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
  activeRule = rules.find(rule => rule?.derived_table === state.currentTable && (rule.reference_views || []).length) || null;
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
      const head = document.createElement('thead'); const header = document.createElement('tr');
      columns.forEach(column => { const th = document.createElement('th'); th.textContent = column; header.appendChild(th); });
      head.appendChild(header); table.appendChild(head);
      const body = document.createElement('tbody');
      payload.rows.forEach(row => { const tr = document.createElement('tr'); columns.forEach((column, index) => { const td = document.createElement('td'); td.textContent = Array.isArray(row) ? (row[index] ?? '') : (row?.[column] ?? ''); tr.appendChild(td); }); body.appendChild(tr); });
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
