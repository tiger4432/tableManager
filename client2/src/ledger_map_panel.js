// LEDGER MAP PANEL — the declaration map, hosted by admin.
//
// WHAT THIS FILE IS, AND WHAT IT DELIBERATELY IS NOT.
//   It is the DRIVER: fetch, session guard, paint, and the wiring that opens an editor on a
//   row. It is NOT a reader — `ontology_structure_core.js` (model) and
//   `ontology_structure_view.js` (DOM+SVG) are imported from where they sit and neither is
//   modified. The console kept its own copy of this driver inside `ledger_trace.js`; that is
//   the part that had to be re-hosted, because a controller belongs to its page while a reader
//   does not.
//
//   The files are imported IN PLACE on purpose. `vite.config.js` still builds `ledger.html` as
//   an entry and `journey_core.js` still imports `STRUCTURE_VIEW`/`edgeKey` from the core, so
//   physically moving them would break a build that has nothing to do with this change.
//
// 🔴 TWO FETCH DISCIPLINES, KEPT APART.
//   The reader's data is `/api/ledger/*` — not gated, plain `fetch`. The editors write to
//   `/admin/ledger/*` — gated, and every one of those calls goes through `adminFetch`. Routing
//   both through one helper would either attach the admin token to ungated read routes or send
//   writes unauthenticated. Neither is a thing to discover later.

// The map's stylesheet. Imported by the HOST, not by the view — the view stays importable in
// bare node so its harness can drive the real renderer. See the header of
// `ontology_structure_view.js` for the failure that established this.
import './ontology_structure.css';
import {
  STRUCTURE_VIEW, parseStructureQuery, structureModel,
} from './ontology_structure_core.js';
// The SHARED kind reader, imported rather than reimplemented. The console keeps the raw body
// beside the normalised catalog because the registry panel reads one field (`observation_table`)
// that the shared reader deliberately drops; this driver has to do the same or that column of
// the map goes blank on its new host.
import { kindCatalog } from './case_control_core.js';
import { renderStructure } from './ontology_structure_view.js';
import {
  configureLedgerSetup, loadFormMaterial, openSourceEditor, openPredicateEditor,
} from './ledger_setup.js';

export { STRUCTURE_VIEW };

const CHROME = Object.freeze({
  BUSY: '구조 집계 중…',
  EDIT: '편집',
  CLOSE: '닫기',
  KINDS_FAILED: 'kind 등록부를 읽지 못했습니다',
  STRUCTURE_FAILED: '구조 집계를 읽지 못했습니다',
});

let deps = null;
let mountEl = null;

// The reader's own session counter. The console keeps a separate one for the same reason: two
// questions answered on one page must not cancel each other's answers.
let session = 0;
let kindsPromise = null;
let kindsBody = null;

/**
 * @param {{root: HTMLElement, apiBase: string, adminFetch: Function,
 *          failureFactOf: Function, renderResolveInto: Function}} options
 */
export function initLedgerMap(options) {
  deps = options;
  mountEl = options.root;
  configureLedgerSetup({
    apiBase: options.apiBase,
    adminFetch: options.adminFetch,
    failureFactOf: options.failureFactOf,
    renderResolveInto: options.renderResolveInto,
  });
}

/** `/api/ledger/kinds` — the finding-kind registry the model folds in. Read once. */
function loadKinds() {
  if (kindsPromise) return kindsPromise;
  kindsPromise = fetch(`${deps.apiBase}/api/ledger/kinds`)
    .then((res) => (res.ok ? res.json() : null))
    .catch(() => null)
    .then((body) => { kindsBody = body; return kindCatalog(body); });
  return kindsPromise;
}

/**
 * Paint the map for `question` = `{view, layer, edge}`.
 *
 * The frame paints from the registry alone first, so the readable half of the screen is
 * readable while the aggregate is still in flight — the console's behaviour, kept.
 */
export async function renderLedgerMap(question) {
  if (!deps || !mountEl) return;
  const mine = ++session;

  const catalog = await loadKinds();
  if (mine !== session) return;

  const paint = (body, notice) => {
    renderStructure(document, mountEl,
      structureModel({ body, kinds: catalog, kindsBody, question }), notice);
    attachEditors();
  };

  paint(null, { tone: 'busy', title: CHROME.BUSY, detail: null });

  // Ungated read: NOT adminFetch. See the header.
  let body = null;
  let notice = null;
  try {
    const res = await fetch(`${deps.apiBase}/api/ledger/structure`);
    if (mine !== session) return;
    if (res.ok) body = await res.json();
    else notice = { tone: 'error', title: CHROME.STRUCTURE_FAILED, detail: `HTTP ${res.status}` };
  } catch (err) {
    notice = {
      tone: 'error',
      title: CHROME.STRUCTURE_FAILED,
      detail: String((err && err.message) || err).slice(0, 200),
    };
  }
  if (mine !== session) return;
  paint(body, notice);

  // The form material for the editors. Gated, so it goes through adminFetch inside the module.
  loadFormMaterial().then(() => { if (mine === session) attachEditors(); });
}

/**
 * Hang an 편집 control off the rows that carry an identity.
 *
 * 🔴 The reader is not modified to do this — the rows already stamp what they are
 * (`data-predicate` on a vocabulary row, `data-kind` on a registry row) and this reads those
 * stamps from the outside. That is the whole reason the editors were built host-agnostic.
 *
 * ⚠️ The 선언 지도 rows (`.os-decl__item`) still carry NO identity, so the source→ledger editor
 * has a row visually and not addressably. That key is being routed on the server side; until it
 * lands, the source editor opens from the panel rather than from its row, and this function
 * does not pretend otherwise.
 */
function attachEditors() {
  if (!mountEl) return;
  mountEl.querySelectorAll('[data-predicate]').forEach((row) => {
    if (row.querySelector('.lm-edit')) return;
    row.appendChild(editButton(() => openPredicateEditor(editorHost(row), {
      name: row.getAttribute('data-predicate'),
    })));
  });

  // The source→ledger editor, anchored on the 선언 지도 PANEL.
  //
  // ⚠️ THE PANEL, NOT THE ROW, AND THAT IS A STOPGAP I AM NAMING RATHER THAN HIDING. The right
  // anchor is the row for the source being edited, and those rows carry no key — the identity
  // is being routed server-side. Until it lands the editor opens from the panel, because the
  // alternative is an editor with no opener at all: landed and unwired, which is worse than a
  // stopgap that says what it is.
  //
  // The panel is picked by `:has(.os-decl)` — 「선언 행을 담은 패널」 — which is the same
  // predicate `ledger_console.css` already uses for this panel, and it is stable against the
  // group's internal shape. An earlier attempt matched the FILE NAME printed in the group head
  // and found nothing, because the served envelope normalises declarations through a different
  // path than the unserved one: matching on rendered prose is matching on a coincidence.
  const declPanel = mountEl.querySelector('.os-panel:has(.os-decl)');
  if (declPanel && !declPanel.querySelector('.lm-edit')) {
    const head = declPanel.querySelector('.os-panel__head') || declPanel;
    head.appendChild(editButton(() => openSourceEditor(editorHost(declPanel))));
  }
}

function editButton(open) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'lm-edit glass-btn cfg-btn';
  btn.textContent = CHROME.EDIT;
  btn.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    open();
  });
  return btn;
}

/** The drawer this row's editor renders into — created on the row, once. */
function editorHost(row) {
  let host = row.querySelector('.lm-editor-host');
  if (!host) {
    host = document.createElement('div');
    host.className = 'lm-editor-host';
    row.appendChild(host);
  }
  return host;
}

/** `?view=…&layer=…&edge=…` off a `URLSearchParams` — the reader's own parser, reused rather
 *  than re-derived, so the host and the anchors cannot disagree about what a question is. */
export function parseMapQuestion(params) {
  return parseStructureQuery(params);
}
