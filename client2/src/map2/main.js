// ═══════════════════════════════════════════════════════════════════════════════
// THE COMPOSITION ROOT -- the ONLY module in Map Editor 2 that knows a DOM exists.
//
// (MAP_ALIGNMENT_SPEC 0.2, side table: "입력칸을 읽어 ③에 넘기고 결과를 화면에 돌려줌 /
//  화면을 아는 층은 여기 하나".)
//
// EVERYTHING ELSE TAKES ARGUMENTS AND RETURNS VALUES. That is not a style preference and it is
// not about counting module globals: a function that reads a module global cannot be called
// twice with different state, so a test has to cut it out of the file as text and re-declare
// the globals around it. That is why nearly every existing client harness slices source, and
// why `map_editor.js` carries a comment forbidding extraction. Modules written this way are
// importable by a harness with no slicing at all -- a property of the CONSTRUCTION, not
// something a later cleanup can add.
//
// WHAT THIS FILE MAY DO: read controls, resolve palette tokens, call pure functions, write
// strings and shapes into elements the markup exposed.
// WHAT IT MAY NOT DO: compute a seat, decide a verdict, or format a number the view model did
// not already format.
//
// THE ONE MUTABLE BINDING IN THE PROGRAM lives in the `bootstrap` closure below, not at module
// level, and it holds a frozen session record produced by `createMapSession`.
//
// MARKUP CONTRACT. The markup lane owns `map_editor2.html` and `map_editor2.css`; this file
// binds to the ids and `data-me2-*` attributes that page publishes and adds no markup of its
// own beyond list items inside containers the page provided. Binding is TOLERANT: a missing
// hook is collected into `missing` and reported, never thrown, so a partially finished page
// still renders everything it can.
//
// STATE IS ONE ATTRIBUTE. `#me2-workbench[data-me2-state]` is switched to one of
// `scored | no-winner | computing | unscorable`, and the stylesheet does the rest -- including
// hiding every numeral in the computing and unscorable states. This file ALSO writes `미상`
// into the count slots in those states rather than relying on that alone: a numeral is a
// claim, and a stale claim sitting in a hidden node is one stylesheet edit away from being
// shown. Two independent guarantees for the rule that must not break.
// ═══════════════════════════════════════════════════════════════════════════════

import { createMapSession, withDecision, withPayload, withError, withSelectedCandidate,
         withFocusedSource, withArmed, withConfig, withCatalog, withQuestion,
         withWorklistQuery, withWorklist, withWorklistError, withConfirmed,
         columnKey, isAskable, isUnset, BINDING_DECLARED, PHASE } from './session.js';
import { computeSeating, compareSeatings, unionBounds } from './seating.js';
import { layoutFor } from './painter.js';
import { buildViewModel, VIEW_STATE, CROSS_SOURCE_ROW_ID, WORDS, CAUSE, ATTRIBUTION,
         UNKNOWN } from './view_model.js';
import { decideVerdict } from './verdict_bridge.js';
import { parseCandidateId } from './candidates.js';
import { createApiClient } from './api.js';
import { decodeReferenceView, verdictContext } from './decode.js';
import { isImplemented as artifactImplemented, rejectionSummary } from './artifact_gateway.js';

/** The ids the page publishes. Names on the left are this file's vocabulary. */
export const ELEMENT_IDS = Object.freeze({
  workbench: 'me2-workbench',
  worklistRows: 'me2-worklist-rows',
  worklistUnscorable: 'me2-worklist-rows-unscorable',
  worklistSearch: 'me2-worklist-search',
  worklistEmpty: 'me2-worklist-empty',
  worklistMeta: 'me2-worklist-meta',
  worklistBoundary: 'me2-worklist-boundary',
  worklistBoundaryLabel: 'me2-worklist-boundary-label',
  badgeUnscorable: 'me2-badge-unscorable',
  badgeRemaining: 'me2-badge-remaining',
  badgeSession: 'me2-badge-session',
  // ── THE SET-UP ROW: 대상 테이블 -> x · y · value -> 기준 ────────────────────
  // One selection row composing ONE request. Bound here by name BEFORE the markup lane lands
  // them, because `bindElements` tolerates absence: a missing hook is collected into `missing`
  // and reported, never thrown. Wiring them when they arrive is nothing -- the values are
  // already read, already normalised and already in the request.
  //
  // 🔴 THE STATE IS THE COLUMN SET, NOT A FRAME NAME. `me2-col-x` / `me2-col-y` / `me2-col-value`
  //    are the primitives; anything spelled `CORE FRAME` would be a preset that WRITES these
  //    three, never a thing held instead of them. No preset control is bound yet, on purpose:
  //    a preset built before the primitives becomes the foundation, and a wrong one then has no
  //    way around it.
  tableSelect: 'me2-table-select',
  colXSelect: 'me2-col-x',
  colYSelect: 'me2-col-y',
  colValueSelect: 'me2-col-value',
  referenceSelect: 'me2-reference-select',
  questionNote: 'me2-question-note',
  // 🔴 AGREEING WITH A PROPOSAL NEEDS ITS OWN CONTROL. Provenance is raised to `declared` by a
  //    select `change`, and re-picking the option ALREADY selected fires no `change` at all --
  //    so an operator who agrees with a proposed x/y pair had no way to say so, the dashed
  //    marker never cleared, and the write stayed blocked forever. An agreement is an act; it
  //    needs a control, not the absence of one.
  columnsConfirm: 'me2-columns-confirm',
  svg: 'me2-picture-svg',
  layerFloor: 'me2-layer-floor',
  layerMiss: 'me2-layer-miss',
  layerOnlyOne: 'me2-layer-onlyone',
  layerAlone: 'me2-layer-alone',
  caption: 'me2-picture-caption',
  refusal: 'me2-refusal',
  headline: 'me2-verdict-headline',
  cause: 'me2-verdict-cause',
  sourceList: 'me2-source-list',
  sourcesMeta: 'me2-sources-meta',
  metricConflict: 'me2-metric-conflict',
  confirmBtn: 'me2-confirm-btn',
  confirmSentence: 'me2-confirm-sentence',
  confirmNote: 'me2-confirm-note',
  confirmHint: 'me2-confirm-hint',
  exportBtn: 'me2-export-btn',
  pasteResult: 'me2-paste-result',
});

/** The page's four state words. This file speaks the view model's words and translates once. */
const STATE_ATTR = Object.freeze({
  [VIEW_STATE.SCORED_WINNER]: 'scored',
  [VIEW_STATE.SCORED_NO_WINNER]: 'no-winner',
  [VIEW_STATE.COMPUTING]: 'computing',
  [VIEW_STATE.NOT_SCORABLE]: 'unscorable',
  // Nothing selected yet shows the skeleton, because the alternative is a screen full of
  // numerals about nothing.
  [VIEW_STATE.IDLE]: 'computing',
});

const SVG_NS = 'http://www.w3.org/2000/svg';
// The page's stage is a 200x200 viewBox. Rectangles are drawn slightly smaller than the pitch
// so the grid reads as cells rather than as a solid block -- the same proportion the markup
// lane's placeholder cells use.
const STAGE = Object.freeze({ width: 200, height: 200, padding: 1, fillRatio: 0.87, radius: 1.2 });

// Same figure the enrichment queue uses for its reference views. One number, one meaning: a
// fast typist must not queue a served search per keystroke.
const SEARCH_DEBOUNCE_MS = 250;

/**
 * A served worklist response -> what the session stores. TOTALS ARE PASSED THROUGH, NEVER
 * DERIVED: a page is not a population, and `rows.length` is a fact about this page only. An
 * absent total stays absent and renders `미상`.
 */
export function normaliseWorklist(res) {
  const body = res || {};
  // `units`, as the route serves them. A row carries a state and a REASON CODE, never a
  // sentence: the sentences arrive once, aggregated, in `unscorable_reasons`.
  const units = Array.isArray(body.units) ? body.units
    : (Array.isArray(body.rows) ? body.rows : (Array.isArray(body) ? body : []));
  const totals = body.totals || {};
  const byState = totals.by_state || {};
  return {
    rows: Object.freeze(units.slice()),
    // 🔴 THE SERVER'S OWN TOTALS, AND NOTHING DERIVED FROM THE PAGE. `matched` is how many the
    //    query found; `returned` is how many fit in this response. Reporting the second as the
    //    first is the page-is-not-a-population defect that put `잔여 · 0건` on screen.
    total: numOrNullish(totals.matched),
    remaining: numOrNullish(byState.pending),
    unscorable: numOrNullish(totals.unscorable),
    // Aggregated reasons, counted once. Never a sentence per row.
    reasons: Object.freeze(Array.isArray(body.unscorable_reasons) ? body.unscorable_reasons : []),
    truncated: totals.units_truncated === true,
    // The route ships the catalog with the page, so the five controls need no separate call.
    selection: body.selection || null,
  };
}

function numOrNullish(v) {
  const n = Number(v);
  return Number.isFinite(n) && v !== null && v !== '' ? n : null;
}

function bindElements(doc) {
  const el = {};
  const missing = [];
  for (const [key, id] of Object.entries(ELEMENT_IDS)) {
    const node = doc.getElementById(id);
    el[key] = node || null;
    if (!node) missing.push(id);
  }
  return { el, missing };
}

/**
 * @param {object} deps
 * @param {Document} deps.document
 * @param {object}   deps.api        from `createApiClient`, or anything with the same shape
 * @param {function} [deps.verdictFn] defaults to the bridge; injectable so a harness can drive
 *                                    the shell with a scripted verdict.
 */
export function bootstrap(deps) {
  const doc = deps.document;
  const api = deps.api;
  const verdictFn = deps.verdictFn || decideVerdict;
  const { el, missing } = bindElements(doc);

  // THE one mutable binding, function-scoped. (`loadUnit` beside it is swapped once at startup
  // by the page entry, which is the only place that knows the rule naming the decision unit.)
  let session = createMapSession({});
  let loadUnit = (decision, question) => api.loadReferenceView({ ...question, ...decision });
  let loadRows = null;
  // What only the page entry knows: the rule naming the decision unit, that rule's DECLARED
  // target fields (the write's destination, never the picker's input), and who is confirming.
  const context = { rule: null, targetFields: [], confirmedBy: null,
                    toDecisionKey: (d) => ({ ...(d || {}) }) };
  let searchTimer = null;
  // Last diagnosis logged, so a repaint does not repeat a line nobody asked for twice.
  let lastDiagnosis = '';
  // Action accounting for the switchover bar: 8 maps, <= 4 actions each, <= 30 s, 0 writes.
  const bar = { actions: 0, fetches: 0, repaints: 0, startedAt: null, lastLoopMs: null };

  function setSession(nextSession) {
    session = nextSession;
    render();
  }

  // ── the layers, called with values ───────────────────────────────────────────
  function currentVerdict() {
    if (session.phase !== PHASE.READY || !session.payload) return null;
    // Thresholds are PASSED IN from server config. There is no literal anywhere on this path:
    // without them the verdict layer refuses to rank rather than inventing a minimum.
    // The context is assembled by the decoder, not by hand here. Two call sites building it
    // themselves is how they start disagreeing about what "no reference" meant.
    return verdictFn(
      session.payload.per_candidate,
      session.config || null,
      session.payload.__context || { refusalDetail: session.payload.refusal_detail });
  }

  // ── writing to the screen ────────────────────────────────────────────────────
  function render() {
    const vm = buildViewModel({ session, verdict: currentVerdict() });

    if (el.workbench) el.workbench.setAttribute('data-me2-state', STATE_ATTR[vm.state] || 'computing');
    // 🔴 WRITE INTO `.me2-num`, NEVER INTO THE HEADLINE ELEMENT ITSELF. The page puts three
    //    siblings in every count slot -- `.me2-num` / `.me2-unknown` / `.me2-busy` (or
    //    `.me2-skel`) -- and shows exactly one of them per `data-me2-state`. Writing to the
    //    parent would delete the other two and take the guarantee with them. That guarantee is
    //    what makes "a numeral is a claim" structural rather than conventional: the computing
    //    and unscorable states cannot leak a number even from stale text, because the node
    //    holding the number is not displayed at all. So this file does NOT blank counts by
    //    state either -- a second conditional on top of a guarantee that already holds is the
    //    second spelling, and the two would drift.
    const headText = headlineNum(vm);
    if (headText) setAttrText(doc, '[data-me2-verdict]', headText);
    // A LABEL joined to a COUNT by a separator, never a clause. The decoder handed over a
    // token and a number precisely so that no template-plus-slot sentence can form here.
    text(el.cause, causeLine(vm.cause));
    text(el.caption, vm.caption);
    setAttrText(doc, '[data-me2-picture-meta]', vm.meta);

    // The server's own refusal sentence, verbatim. A second copy of it on this side would be
    // two spellings of one fact, which is the defect class this round exists to close.
    const detail = vm.cause && vm.cause.detail ? vm.cause.detail : '';
    if (el.refusal) text(el.refusal, vm.state === VIEW_STATE.NOT_SCORABLE ? detail : '');

    renderQuestion(vm);
    renderWorklist(vm);
    renderCounts(vm);
    renderSources(vm);
    renderCandidates(vm);
    renderConfirm(vm);
    renderSecondMetric(vm);
    paint(vm);
    logDiagnosis(vm);
    bar.repaints++;
    return vm;
  }

  /**
   * The set-up row. Five controls, one question. Options are written from the view model's
   * values; this file chooses no label and composes no clause.
   */
  function renderQuestion(vm) {
    const q = vm.question;
    fillSelect(el.tableSelect, q.tables);
    fillSelect(el.colXSelect, q.xOptions);
    fillSelect(el.colYSelect, q.yOptions);
    fillSelect(el.colValueSelect, q.valueOptions);
    fillSelect(el.referenceSelect, q.references);
    // 🔴 A PROPOSED PAIR IS MARKED WHEREVER IT APPEARS. One attribute, so the stylesheet can
    //    say it once; the confirm control separately refuses to rest on it, and the two
    //    guarantees are independent on purpose.
    for (const node of [el.colXSelect, el.colYSelect]) {
      if (node) node.setAttribute('data-me2-proposed', q.bindingIsGuess ? 'true' : 'false');
    }
    // Hidden unless there is something to agree to. A permanent confirm button beside a
    // declared pair would train the operator to click it without reading.
    if (el.columnsConfirm) el.columnsConfirm.hidden = !q.bindingIsGuess;
    if (el.workbench) {
      el.workbench.setAttribute('data-me2-evidence', vm.evidence.kind);
      el.workbench.setAttribute('data-me2-attribution', vm.attribution.state);
    }
    // A label joined to a value by a separator. Never a template with a slot.
    text(el.questionNote, questionNote(vm));
  }

  function fillSelect(node, options) {
    if (!node || !Array.isArray(options)) return;
    // Rebuilt only when the option set actually changed: replacing the children on every
    // repaint would close an open dropdown mid-choice and lose the operator's place.
    const signature = options.map(o => o.value).join(' ');
    if (node.getAttribute('data-me2-options') !== signature) {
      node.textContent = '';
      for (const opt of options) {
        const o = doc.createElement('option');
        o.value = opt.value;
        o.textContent = opt.label;
        node.appendChild(o);
      }
      node.setAttribute('data-me2-options', signature);
    }
    const selected = options.find(o => o.selected);
    node.value = selected ? selected.value : '';
    node.disabled = options.length === 0;
  }

  /** `제안 · 기준 없음`. Tokens and a separator; the words come from the view model. */
  function questionNote(vm) {
    const parts = [];
    if (vm.question.proposalWord) parts.push(vm.question.proposalWord);
    if (vm.evidence.occupancyOnly) parts.push(CAUSE.reference_no_values);
    if (vm.attribution.state === ATTRIBUTION.UNSTATED) parts.push(WORDS.columnsUnstated);
    return parts.join(' · ');
  }

  /**
   * The worklist: one SERVED page, above and below a boundary.
   *
   * 🔴 THE BADGES REPORT THE SERVER'S TOTALS, NOT THE ROWS ON SCREEN. This used to write
   *    `rows.length - below`, which turns "the first page held 41 scorable rows" into the claim
   *    "41 remain". A page is not a population, and the population is not bounded by anything
   *    this client controls. When the server sent no total the badge says `미상`.
   *
   * 🔴 ROWS BELOW THE BOUNDARY GET NO PER-ROW MARK. Roughly half the population lands there --
   *    320 of 668 metas are auto-registered and refused, and 8 `valid_die_ref` declarations
   *    resolve zero times. Decorating half a list trains the eye past the decoration, after
   *    which it also fails on the rows that are real. One badge, one boundary, nothing per row,
   *    and nothing red.
   */
  function renderWorklist(vm) {
    const wl = vm.worklist;
    const scorable = el.worklistRows;
    if (!scorable) return;
    scorable.textContent = '';
    if (el.worklistUnscorable) el.worklistUnscorable.textContent = '';
    for (const row of wl.rows) scorable.appendChild(worklistRow(row));
    if (el.worklistUnscorable) {
      for (const row of wl.unscorableRows) el.worklistUnscorable.appendChild(worklistRow(row));
    }
    if (el.worklistBoundary) el.worklistBoundary.hidden = !wl.boundaryVisible;
    if (el.worklistEmpty) el.worklistEmpty.hidden = !wl.empty;
    // Aggregate, once, in the header. A label joined to a count by a separator.
    writeBadge(el.badgeRemaining, WORDS.remaining, wl.remaining);
    writeBadge(el.badgeUnscorable, WORDS.unscorable, wl.unscorable);
    writeBadge(el.badgeSession, WORDS.thisSession, wl.confirmedThisSession);
    text(el.worklistMeta, wl.error ? WORDS.unknown : (wl.served ? '' : WORDS.unknown));
  }

  function worklistRow(row) {
    const node = doc.createElement('button');
    node.type = 'button';
    node.className = 'me2-wl-row';
    node.setAttribute('role', 'option');
    node.setAttribute('aria-selected', row.selected ? 'true' : 'false');
    node.setAttribute('data-me2-row', '');
    node.setAttribute('data-eqp', row.eqp);
    node.setAttribute('data-product', row.product);
    node.setAttribute('data-state', row.state);
    // The server's composed identity, carried so a click can find the row's own key dict.
    node.setAttribute('data-me2-row-key', row.unitKey);
    node.appendChild(span(doc, 'me2-wl-key', row.unitKey || `${row.eqp} · ${row.product}`));
    // `stateWord` is empty for every row below the boundary. That emptiness is the rule, not a
    // missing value: no per-row decoration down there, of any kind.
    const badge = span(doc, 'me2-wl-badge', row.stateWord);
    badge.setAttribute('data-me2-row-state', '');
    node.appendChild(badge);
    const maps = span(doc, 'me2-wl-maps', row.mapCount === null ? '' : `${WORDS.maps} ${row.mapCount}`);
    maps.setAttribute('data-me2-row-maps', '');
    node.appendChild(maps);
    return node;
  }

  /**
   * A header badge. Writes into the `.me2-num` slot when the markup publishes one, and into the
   * badge itself otherwise -- the header badges have no three-sibling pattern today, and asking
   * for one is in the report rather than being faked here. An unmeasured count says `미상`; it
   * is never blanked and never given a 0 stand-in.
   */
  function writeBadge(node, label, count) {
    if (!node) return;
    const value = Number.isFinite(Number(count)) && count !== null ? `${count}건` : UNKNOWN;
    const slot = node.querySelector ? node.querySelector('[data-me2-badge-num]') : null;
    if (slot) { slot.textContent = value; return; }
    node.textContent = `${label} · ${value}`;
  }

  /**
   * Counts go into `.me2-num` slots and are written ONLY when there is a measured number to
   * write. They are never blanked and never overwritten with `미상`: the page's three-sibling
   * pattern already guarantees a hidden `.me2-num` in the computing and unscorable states, and
   * re-implementing that here would put the same promise in two places.
   */
  function renderCounts(vm) {
    const payload = session.payload;
    const scoring = selectedScoring(vm);
    if (vm.numerals && scoring) {
      writeNum('[data-me2-top-agree]', scoring.agree);
      writeNum('[data-me2-top-discriminating]', scoring.discriminating);
    }
    if (vm.numerals) writeNum('[data-me2-margin-dies]', vm.summary.marginDies);
    if (payload) {
      writeNum('[data-me2-maps-total]', payload.map_count);
      writeNum('[data-me2-maps-excluded]', payload.excluded_map_count);
    }
  }

  /** Writes a number, or writes nothing. Never a `0` stand-in, never a dash, never a blank. */
  function writeNum(sel, value) {
    if (!Number.isFinite(Number(value)) || value === null) return;
    setAttrText(doc, sel, Number(value));
  }

  function renderSources(vm) {
    const payload = session.payload;
    const sources = payload && Array.isArray(payload.sources) ? payload.sources : [];
    text(el.sourcesMeta, sources.length > 0 ? `출처 ${sources.length}개` : '출처 없음');

    const rows = queryAll(doc, '[data-me2-source]');
    for (const row of rows) {
      const field = row.getAttribute('data-source-field');
      if (field === CROSS_SOURCE_ROW_ID) {
        // The (N+1)th row. Cross-source agreement is what the bonding plan actually rests on,
        // and no single source can produce it -- so it is a first-class row, not a new pane.
        //
        // 🔴 N=1 IS NOT A WEAKER VERSION OF N=2, IT IS A DIFFERENT CLAIM. One source placed on
        //    the floor tells you WHERE it sits; it cannot tell you whether that placement is
        //    right, because there is no second witness to disagree with. Showing it in the same
        //    green as a corroborated result would make the screen assert corroboration that
        //    nobody performed -- the same failure as a plausible default impersonating a
        //    declaration, on the layer the bonding plan actually rests on. So the row says what
        //    it has and states the absence, and carries its own state hook for the styling.
        const single = sources.length < 2;
        row.setAttribute('data-me2-cross-state', single ? 'single' : 'paired');
        row.setAttribute('aria-expanded', String(session.focusedSourceId === field));
        row.disabled = single;
        // Bound by `data-me2-*` only. `.me2-src-name` is a style class and this file does not
        // reach for it -- the source count needs its own hook (asked for by name in the report).
        setChildText(row, '[data-me2-source-value]', single ? '배치만 · 교차 확인 없음' : '상호 일치');
        continue;
      }
      const src = sources.find(s => s.id === field) || null;
      row.hidden = !src && sources.length > 0;
      if (!src) continue;
      const declared = src.stored_candidate_id || null;
      setChildText(row, '[data-me2-source-value]', declared ? spellFrame(declared) : '고르지 않음');
      // Same rule as the count slots above: write a number or write nothing. The page's
      // three-sibling pattern already shows `미상` in the states where no number was measured.
      const card = declared ? vm.candidates.find(c => c.id === declared) : null;
      if (vm.numerals && card && card.agree != null) {
        setChildText(row, '[data-me2-agree]', card.agree);
        setChildText(row, '[data-me2-discriminating]', card.discriminating);
      }
      row.setAttribute('aria-expanded', String(session.focusedSourceId === field));
    }
  }

  function renderCandidates(vm) {
    // One grid per COLUMN SET, laid out by the page as 2 columns (flip) x 4 rows (turn). The
    // geometry of the control is the geometry of the operator's two motions, so there is no
    // mental translation to pay and no rotate button anywhere on this screen: the same
    // transform applied to both compared sets leaves their relation invariant, so a rotate
    // control cannot inform.
    //
    // 🔴 THE GRID IS KEYED ON THE COLUMN SET, NOT ON A FRAME NAME. `[data-me2-candidates-for]`
    //    is the markup lane's attribute and keeps its spelling; what changed is what goes in
    //    it. When no grid carries the active key -- which is the case until that lane re-keys
    //    them -- every candidate control on the page is treated as the one grid, so a
    //    half-migrated page renders exactly as it did rather than going blank.
    const activeKey = columnKey(session.question && session.question.columns);
    const grids = queryAll(doc, '[data-me2-candidates-for]');
    const keyed = grids.filter(g => g.getAttribute('data-me2-candidates-for') === activeKey);
    if (activeKey && grids.length > 0) {
      for (const g of grids) {
        const mine = g.getAttribute('data-me2-candidates-for') === activeKey;
        g.hidden = !mine && keyed.length > 0;
        if (mine && queryAll(g, '[data-me2-candidate]').length === 0) fillGrid(g, vm);
      }
    }
    const scope = keyed.length > 0 ? keyed : [doc];
    for (const host of scope) {
    for (const cell of queryAll(host, '[data-me2-candidate]')) {
      const code = cell.getAttribute('data-frame-code');
      const card = vm.candidates.find(c => c.id === code);
      if (!card) continue;
      cell.setAttribute('aria-pressed', String(card.selected));
      cell.disabled = card.inert;
      const tags = cell.querySelector ? cell.querySelector('[data-me2-cand-tags]') : null;
      if (tags) {
        tags.textContent = '';
        for (const badge of card.badges) {
          const span = doc.createElement('span');
          span.className = badge === '추천' ? 'me2-tag is-recommended' : 'me2-tag is-current';
          span.textContent = badge;
          tags.appendChild(span);
        }
      }
    }
    }
  }

  /**
   * Fill a grid the page provided but left empty. This adds LIST ITEMS INSIDE A CONTAINER THE
   * PAGE PROVIDED, which is the only markup this file is allowed to make; it invents no
   * container, no class the stylesheet does not already carry, and no ordering of its own --
   * the eight and their arrangement come from the view model.
   */
  function fillGrid(host, vm) {
    for (const row of vm.grid) {
      for (const card of row.cells) {
        if (!card) continue;
        const cell = doc.createElement('button');
        cell.type = 'button';
        cell.className = 'me2-cand';
        cell.setAttribute('data-me2-candidate', '');
        cell.setAttribute('data-rotation', String(card.rotation));
        cell.setAttribute('data-side', card.side);
        cell.setAttribute('data-frame-code', card.id);
        cell.setAttribute('aria-pressed', 'false');
        cell.appendChild(span(doc, 'me2-cand-deg', card.degLabel));
        cell.appendChild(span(doc, 'me2-cand-code', card.storedLabel));
        const tags = span(doc, 'me2-cand-tags', '');
        tags.setAttribute('data-me2-cand-tags', '');
        cell.appendChild(tags);
        host.appendChild(cell);
      }
    }
  }

  function renderConfirm(vm) {
    // `#me2-confirm-sentence` is NOT written here. It is the one full sentence on this screen
    // and the markup lane owns its wording; this file fills the values it names through the
    // hooks that sentence exposes. Until those hooks exist the sentence stays as authored --
    // asked for by name rather than patched in from two places at once.
    setChildTextIn(el.confirmSentence, '[data-me2-confirm-eqp]', vm.confirm.eqp || '');
    setChildTextIn(el.confirmSentence, '[data-me2-confirm-product]', vm.confirm.product || '');
    setChildTextIn(el.confirmSentence, '[data-me2-confirm-frame]', vm.confirm.candidateId || '');
    text(el.confirmNote, vm.confirm.note || '');
    // Enter must never be silently inert: when nothing is marked, the hint says so.
    text(el.confirmHint, vm.confirm.inertHint || 'Enter 확정 준비 · Esc 취소');
    const btn = el.confirmBtn;
    if (!btn) return;
    btn.disabled = !vm.confirm.enabled;
    btn.setAttribute('data-armed', vm.confirm.armed ? 'true' : 'false');
  }

  function renderSecondMetric(vm) {
    // Computed always, shown only when it disagrees. A second metric that agrees changes
    // nothing and doubles the numerals on screen for zero decision value.
    //
    // 🔴 THE NODE GETS THE LABEL, THE CONSOLE GETS THE SENTENCE. `지표 불일치` is the fact that
    //    changes the decision; which candidate each metric chose is diagnosis, and diagnosis
    //    lives in the console where it can be read whole and never wraps a line on screen.
    if (!el.metricConflict) return;
    el.metricConflict.hidden = !vm.secondMetric;
    if (vm.secondMetric) el.metricConflict.textContent = vm.secondMetric;
  }

  /**
   * EVERYTHING THE SCREEN DOES NOT SAY. The audience are administrators; explanation belongs in
   * the docs and diagnosis in the console, so the full form of every short label goes here --
   * whole, never truncated. Logged only when it CHANGES, because a repaint is not an event and
   * a line per repaint is a log nobody reads.
   */
  function logDiagnosis(vm) {
    const view = doc.defaultView;
    if (!view || !view.console) return;
    const q = vm.question;
    const lines = [];
    // 🔴 THE SCREEN NOW TRUNCATES, SO THIS IS NOT A CONVENIENCE. The frame made the refusal,
    //    the caption and the inline meta one-line with ellipsis, and deleted the cause node
    //    outright. Anything not logged here whole is not moved to the console, it is DESTROYED.
    if (vm.cause && vm.cause.detail) lines.push(vm.cause.detail);
    if (vm.cause && vm.cause.token) {
      lines.push(vm.cause.count === null ? vm.cause.token : `${vm.cause.token} (${vm.cause.count})`);
    }
    if (vm.meta) lines.push(vm.meta);
    if (vm.caption) lines.push(vm.caption);
    if (vm.secondMetricDetail) lines.push(vm.secondMetricDetail);
    if (q.bindingIsGuess) {
      lines.push(`coordinate binding for '${q.mapTable}' is a fallback guess `
        + `(x=${q.xCol}, y=${q.yCol}, val=${q.valCol || 'none'}); `
        + 'it is served with source="fallback_guess" and must be agreed before confirming.');
    }
    // Only once there IS an answer. Before one arrives there is nothing to attribute and
    // nothing to say about the evidence, and logging it anyway is a line per row selection.
    const answered = vm.state === VIEW_STATE.SCORED_WINNER
      || vm.state === VIEW_STATE.SCORED_NO_WINNER || vm.state === VIEW_STATE.NOT_SCORABLE;
    if (answered && vm.attribution.state === ATTRIBUTION.UNSTATED) {
      lines.push(`the response does not say which coordinate pair it read, and '${q.mapTable}' `
        + `offers ${vm.attribution.pairCount}. Counts are withheld rather than shown under a `
        + 'pair nobody named; the fix is unit.x_col / unit.y_col on the wire.');
    }
    if (answered && vm.evidence.occupancyOnly) {
      lines.push('reference carries no values, so only occupancy could be scored. Occupancy '
        + 'alone is flat: candidates can occupy identical dies and tie. Name a value column.');
    }
    const joined = lines.join(' | ');
    if (joined === lastDiagnosis) return;
    lastDiagnosis = joined;
    if (joined) view.console.log('[map2]', joined);
  }

  // ── the picture ──────────────────────────────────────────────────────────────
  /**
   * Seating is computed HERE, from data, and the layer bodies are filled from the RESULT.
   * The drawing step receives seats and only draws; it decides nothing and returns nothing
   * anyone reads back. The scale is fitted to the seating's own bounds, so there is no
   * off-stage case for a bounds test to drop a cell through -- which is the legacy defect this
   * split exists to make impossible, not merely unlikely.
   */
  function paint(vm) {
    const layers = [el.layerFloor, el.layerMiss, el.layerOnlyOne, el.layerAlone];
    for (const g of layers) if (g) g.textContent = '';
    if (vm.picture === 'skeleton' || vm.picture === 'empty') return null;

    const payload = session.payload;
    const source = pickSource(payload, session.focusedSourceId);
    if (!source) return null;

    const candidateId = vm.selectedCandidateId || source.stored_candidate_id;
    const axes = parseCandidateId(candidateId) || { rotation: 0, side: 'front' };
    const dims = payload.dims || { cols: gridSpan(payload, 'x'), rows: gridSpan(payload, 'y') };
    const frame = {
      rotation: axes.rotation, side: axes.side,
      cols: dims.cols, rows: dims.rows,
      startX: numOr(payload.start_x, 0), startY: numOr(payload.start_y, 0),
    };
    // The FLOOR is held still and the SOURCE turns on top of it. Turning both together is the
    // thing that cannot inform; this version can produce a wrong-looking picture, which is
    // precisely what makes it evidence.
    const floorFrame = { ...frame, rotation: 0, side: 'front' };
    const floor = computeSeating(payload.floor_cells || [], floorFrame);
    const seated = computeSeating(source.cells || [], frame);

    if (vm.picture === 'alone') {
      const layout = layoutFor(seated.bounds, STAGE);
      drawSeats(el.layerAlone, seated.seats, layout, 'me2-cell-alone');
      return { pxPerDie: layout.cell };
    }

    const layout = layoutFor(unionBounds(floor.bounds, seated.bounds), STAGE);
    const comparison = compareSeatings(floor, seated);
    // Order is the argument: agreement is the quiet ground, the coverage gap is a ring because
    // it is not a disagreement, and the mismatch is drawn LAST at full strength because the
    // error shape is the figure. Drawing agreement loudly buries the crescent that tells the
    // operator which way to shift.
    drawSeats(el.layerFloor, floor.seats, layout, 'me2-cell-floor');
    drawSeats(el.layerOnlyOne, comparison.floorOnly, layout, 'me2-cell-onlyone');
    drawSeats(el.layerMiss, comparison.sourceOnly, layout, 'me2-cell-miss');

    const drawn = floor.seats.length + comparison.floorOnly.length + comparison.sourceOnly.length;
    const expected = floor.seatCount + comparison.floorOnly.length + comparison.sourceOnly.length;
    if (drawn !== expected) warn(`picture accounting mismatch: ${drawn} of ${expected}`);
    return { pxPerDie: layout.cell, drawn };
  }

  function drawSeats(g, seats, layout, className) {
    if (!g || layout.empty) return 0;
    const size = layout.cell * STAGE.fillRatio;
    const inset = (layout.cell - size) / 2;
    let n = 0;
    for (const seat of seats) {
      const rect = doc.createElementNS(SVG_NS, 'rect');
      rect.setAttribute('class', className);
      rect.setAttribute('x', String(round1(layout.originX + (seat.x - layout.minX) * layout.cell + inset)));
      rect.setAttribute('y', String(round1(layout.originY + (seat.y - layout.minY) * layout.cell + inset)));
      rect.setAttribute('width', String(round1(size)));
      rect.setAttribute('height', String(round1(size)));
      rect.setAttribute('rx', String(STAGE.radius));
      g.appendChild(rect);
      n++;
    }
    return n;
  }

  // ── events ───────────────────────────────────────────────────────────────────
  function selectDecision(decision) {
    bar.actions++;
    bar.startedAt = Date.now();
    setSession(withDecision(session, decision));
    ask();
  }

  /**
   * ONE request, carrying the whole primitive tuple: the unit, the table, the columns and the
   * floor. Reference cells, source cells and all eight candidate scorings come back together --
   * there is deliberately no per-candidate fetch anywhere in this program, because eight round
   * trips per row would blow the 30-second bar on their own.
   *
   * Changing any part of the question re-asks. That is one fetch, and the sequence guard is
   * what keeps the previous set-up's answer from being painted under the new labels.
   */
  function ask() {
    const decision = session.decision;
    if (!decision) return;
    // Untouched set-up asks as before; a HALF-filled one refuses. See .
    if (!isUnset(session.question) && !isAskable(session.question)) return;
    const seq = session.requestSeq;
    bar.fetches++;
    Promise.resolve(loadUnit(decision, session.question))
      .then(raw => { setSession(withPayload(session, adaptPayload(raw), seq)); markLoop(); })
      .catch(err => setSession(withError(session, err, seq)));
  }

  /** One of the five set-up controls moved. Normalise, then re-ask if there is a row selected. */
  function setQuestion(patch) {
    bar.actions++;
    const before = session;
    setSession(withQuestion(session, patch));
    if (session !== before) ask();
  }

  /**
   * 🔴 THE SEARCH IS THE SERVER'S. This sends the text and renders what comes back; it never
   *    filters a loaded list, and there is no "load them all" call for it to filter over. The
   *    population is not bounded by anything this client controls. Debounced so a fast typist
   *    does not queue a request per keystroke, and sequence-guarded so the answer to a query
   *    the operator already retyped is discarded rather than painted.
   */
  function searchWorklist(query) {
    setSession(withWorklistQuery(session, query));
    if (searchTimer !== null && doc.defaultView) doc.defaultView.clearTimeout(searchTimer);
    const run = () => { searchTimer = null; fetchWorklist(); };
    if (doc.defaultView && doc.defaultView.setTimeout) {
      searchTimer = doc.defaultView.setTimeout(run, SEARCH_DEBOUNCE_MS);
    } else {
      run();
    }
  }

  function fetchWorklist() {
    if (typeof loadRows !== 'function') return;
    const seq = session.worklistSeq;
    const q = session.question || {};
    Promise.resolve(loadRows({
      q: session.worklist.query,
      rule: context.rule,
      mapTable: q.mapTable,
      // The worklist is a list of UNITS. It is not scoped by the coordinate columns -- those
      // decide how one unit is READ, not which units exist -- so they are not sent here.
    })).then(res => setSession(withWorklist(session, normaliseWorklist(res), seq)))
      .catch(err => setSession(withWorklistError(session, err, seq)));
  }

  function markLoop() {
    if (bar.startedAt !== null) bar.lastLoopMs = Date.now() - bar.startedAt;
  }

  /**
   * 🔴 THIS USED TO CALL `confirmFrame` POSITIONALLY AND THE TRANSPORT TAKES A RECORD. Every
   *    field the POST body names -- `rule`, `decision_key`, `frames`, `sources`, `ruling`,
   *    `reference` -- read `undefined` off a `{eqp, product}` object, so the one write on this
   *    screen was posting an empty record. The record is built here now, from the same values
   *    the operator was looking at.
   *
   * 🔴 THE COLUMNS ARE THE INPUT; THE TARGET FIELD IS THE OUTPUT. `frames` is keyed by the
   *    rule's DECLARED target fields, because that is what downstream reads. Nothing declares
   *    which column pair writes which target field, so when the rule declares more than one and
   *    the operator's pair could map to either, this refuses rather than guessing -- naming
   *    that ambiguity is the finding, and a guess here would bake a rotation into stored
   *    coordinates under the wrong label with nothing downstream looking wrong.
   */
  function onConfirm() {
    bar.actions++;
    const vm = buildViewModel({ session, verdict: currentVerdict() });
    if (!vm.confirm.enabled) return;
    // Reading is frictionless; this write gets exactly one confirmation and it is not a modal.
    if (!session.armed) { setSession(withArmed(session, true)); return; }
    const payload = session.payload || {};
    const q = session.question || {};
    Promise.resolve(api.confirmFrame({
      rule: context.rule,
      decisionKey: context.toDecisionKey(session.decision),
      // The SUBJECT of the confirmation: this pair, in this table, at this frame.
      mapTable: q.mapTable,
      columns: { x: q.columns.x, y: q.columns.y, val: q.columns.val },
      frame: vm.selectedCandidateId,
      frames: {},
      sources: (payload.sources || []).map(s => ({
        role: 'source',
        source_table: q.mapTable,
        map_id: s.id,
        source_name: s.label,
        applied_frame: vm.selectedCandidateId,
        shift_dx: 0,
        shift_dy: 0,
        agreement: null,
        discriminating: null,
        excluded_reason: null,
      })),
      ruling: (payload.__decoded && payload.__decoded.ruling) || null,
      reference: referenceOf(q.reference),
      confirmedBy: context.confirmedBy,
    })).then(() => { setSession(withConfirmed(session)); })
      .catch(() => { setSession(withArmed(session, false)); });
  }

  /**
   * 🔴 NO TARGET FIELD IS NAMED, BY RULING (2026-08-05). The confirmation records WHICH
   *    COORDINATES WERE ALIGNED -- the column pair -- because `frame_confirmation` is
   *    authoritative for what was confirmed and a target field is a name from a different
   *    system's vocabulary. Nothing declares which pair writes which `target_field`, and the
   *    resolution is not to add that declaration: it is that this record does not need it.
   *    Whether the confirmation writes through to the enrichment fields, or those fields become
   *    a pointer to this record, is open. Until it is decided, we keep refusing to name one.
   */
  /** `"table:map_id"` back into the record's `{table, map_id}`. 기준 없음 stays null. */
  function referenceOf(spec) {
    if (!spec || String(spec).indexOf(':') < 0) return null;
    const parts = String(spec).split(':');
    return { table: parts[0], map_id: parts.slice(1).join(':') };
  }

  function onWorklistClick(e) {
    const row = e.target && e.target.closest ? e.target.closest('[data-me2-row]') : null;
    if (!row) return;
    for (const other of queryAll(doc, '[data-me2-row]')) other.setAttribute('aria-selected', 'false');
    row.setAttribute('aria-selected', 'true');
    // 🔴 THE REQUEST TAKES THE SERVED KEY DICT, NOT TWO ATTRIBUTES RE-READ OFF THE DOM. The
    //    rule owns which columns compose a unit, so reconstructing `{dt_eqp, product}` from
    //    `data-eqp` / `data-product` would hardcode today's rule into the click handler and
    //    silently answer about the wrong thing the day a rule declares a third key column.
    const unitKey = row.getAttribute('data-me2-row-key') || '';
    const served = (session.worklist.rows || []).find(
      r => String(r.unit_key == null ? '' : r.unit_key) === unitKey) || null;
    selectDecision({
      eqp: row.getAttribute('data-eqp'),
      product: row.getAttribute('data-product'),
      __unitKey: unitKey,
      __key: served && served.key && typeof served.key === 'object' ? served.key : null,
    });
  }

  for (const host of [el.worklistRows, el.worklistUnscorable]) {
    if (host) host.addEventListener('click', onWorklistClick);
  }
  // The five set-up controls. Each writes ONE primitive field; none of them derives behaviour
  // from a name. A preset, when one exists, will write these same fields and nothing else.
  bindSelect(el.tableSelect, v => setQuestion({ mapTable: v }));
  bindSelect(el.colXSelect, v => setQuestion({
    columns: { ...session.question.columns, x: v || null }, bindingSource: BINDING_DECLARED }));
  bindSelect(el.colYSelect, v => setQuestion({
    columns: { ...session.question.columns, y: v || null }, bindingSource: BINDING_DECLARED }));
  bindSelect(el.colValueSelect, v => setQuestion({
    columns: { ...session.question.columns, val: v || null }, bindingSource: BINDING_DECLARED }));
  bindSelect(el.referenceSelect, v => setQuestion({ reference: v || null }));
  if (el.columnsConfirm) {
    el.columnsConfirm.addEventListener('click', () => {
      // Agreeing changes nothing about the columns, only about who stands behind them, so it
      // must NOT re-ask: the answer already on screen was computed from this very pair.
      bar.actions++;
      setSession(withQuestion(session, { bindingSource: BINDING_DECLARED }));
    });
  }
  if (el.worklistSearch) {
    el.worklistSearch.addEventListener('input', (e) => {
      searchWorklist((e.target && e.target.value) || '');
    });
  }
  if (el.confirmBtn) el.confirmBtn.addEventListener('click', onConfirm);
  if (el.sourceList) {
    el.sourceList.addEventListener('click', (e) => {
      const row = e.target && e.target.closest ? e.target.closest('[data-me2-source]') : null;
      if (!row || row.disabled) return;
      bar.actions++;
      setSession(withFocusedSource(session, row.getAttribute('data-source-field')));
    });
  }
  // Candidate clicks are delegated from the document so the handler survives any re-render the
  // markup lane's page performs. Selection is a repaint of data already in hand: no fetch.
  doc.addEventListener('click', (e) => {
    const cell = e.target && e.target.closest ? e.target.closest('[data-me2-candidate]') : null;
    if (!cell || cell.disabled) return;
    bar.actions++;
    setSession(withSelectedCandidate(session, cell.getAttribute('data-frame-code')));
  });
  doc.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && session.armed) setSession(withArmed(session, false));
    // Enter arms, then commits. Arrow keys stay with the worklist -- existing muscle memory.
    //
    // 🔴 THIS HANDLER HAD NO TARGET GUARD, AND IT MADE THE ONE WRITE IN THE CHAIN REACHABLE BY
    //    A KEYSTROKE INSIDE A DROPDOWN. Enter in any of the five set-up selects bubbled to the
    //    document, armed on the first press and committed on the second -- while the operator
    //    believed they were choosing a column. A confirmation that a wrong frame bakes an
    //    unverified rotation into stored coordinates, reachable by accident, is the failure
    //    this whole arm-then-commit design exists to prevent.
    //
    //    The guard is on WHAT KIND OF THING HAS FOCUS, not on one container's id. Keying it to
    //    `#me2-question-bar` would protect exactly today's markup and silently stop protecting
    //    anything the day a control is added outside that div -- and the next control to be
    //    added is the one nobody remembers to re-check. Enter belongs to a focused control
    //    whenever there is one; only the confirm button itself may turn it into this write.
    if (e.key === 'Enter' && el.confirmBtn && !el.confirmBtn.disabled && !takesEnter(e.target)) {
      onConfirm();
    }
  });

  /**
   * Does this element own the Enter key? Every form control does -- a select opens or commits
   * its own choice, an input submits its own value -- and so does anything explicitly opted out
   * with `data-me2-no-enter`. The confirm button is the ONE exception: Enter on it is this
   * write by definition.
   */
  function takesEnter(target) {
    if (!target) return false;
    if (el.confirmBtn && target === el.confirmBtn) return false;
    if (typeof target.closest === 'function' && el.confirmBtn && target.closest('#me2-confirm-btn')) {
      return false;
    }
    // 🔴 ALLOW-LIST, NOT DENY-LIST, AND THAT IS THE WHOLE POINT. Enumerating the controls that
    //    own Enter (`SELECT`, `INPUT`, ...) protects exactly the controls somebody remembered,
    //    and the next control added is the one nobody re-checks -- the same shape of hole as
    //    keying the guard to one container's id. So Enter reaches this write ONLY from the
    //    confirm control itself or from a page with nothing focused at all. Anything else
    //    focused owns its own Enter, whatever it turns out to be.
    const tag = String(target.tagName || '').toUpperCase();
    return !(tag === 'BODY' || tag === 'HTML' || tag === '#DOCUMENT' || tag === '');
  }
  if (el.exportBtn) {
    el.exportBtn.disabled = !artifactImplemented();
    // The reason is an explanation, so it goes to the console. The disabled control is what
    // the screen says; a sentence hanging off a tooltip is neither one line nor a decision.
    if (!artifactImplemented() && doc.defaultView && doc.defaultView.console) {
      doc.defaultView.console.log('[map2] excel artifact export is not wired to a control yet.');
    }
  }

  // ── helpers that touch the DOM ───────────────────────────────────────────────
  function bindSelect(node, onPick) {
    if (!node) return;
    node.addEventListener('change', (e) => onPick((e.target && e.target.value) || ''));
  }
  function text(node, value) { if (node) node.textContent = value; }
  function queryAll(d, sel) {
    return d.querySelectorAll ? Array.from(d.querySelectorAll(sel)) : [];
  }
  function setAttrText(d, sel, value) {
    for (const node of queryAll(d, sel)) node.textContent = String(value);
  }
  function setChildText(root, sel, value) {
    const node = root && root.querySelector ? root.querySelector(sel) : null;
    if (node) node.textContent = String(value);
  }
  function setChildTextIn(root, sel, value) { setChildText(root, sel, value); }
  function warn(msg) {
    if (doc.defaultView && doc.defaultView.console) doc.defaultView.console.log(`[map2] ${msg}`);
  }

  function selectedScoring(vm) {
    const payload = session.payload;
    if (!payload || !Array.isArray(payload.per_candidate)) return null;
    const id = vm.selectedCandidateId;
    return payload.per_candidate.find(s => s && s.candidate_id === id) || null;
  }

  return Object.freeze({
    ELEMENT_IDS,
    missing: Object.freeze(missing),
    bar,
    render,
    selectDecision,
    /** The page entry supplies the request, because only it knows the rule naming the unit. */
    setLoader(fn) { if (typeof fn === 'function') loadUnit = fn; },
    /** The worklist loader, same seam. Absent until the route lands; nothing fetches without it. */
    setWorklistLoader(fn) { if (typeof fn === 'function') loadRows = fn; },
    /**
     * The rule, its DECLARED target fields, and who is confirming. Target fields are the WRITE's
     * destination and never the picker's input -- see `framesToWrite`.
     */
    setContext(next) {
      if (!next) return;
      if (next.rule) context.rule = String(next.rule);
      if (Array.isArray(next.targetFields)) context.targetFields = next.targetFields.slice();
      if (next.confirmedBy) context.confirmedBy = String(next.confirmedBy);
      if (typeof next.toDecisionKey === 'function') context.toDecisionKey = next.toDecisionKey;
    },
    setConfig(config) { setSession(withConfig(session, config)); },
    /** What the five controls may offer. Re-normalises the standing question against it. */
    setCatalog(catalog) { setSession(withCatalog(session, catalog)); },
    setQuestion,
    /** Re-runs the served search with the current text. */
    refreshWorklist() { fetchWorklist(); },
    searchWorklist,
    /**
     * Adopt an already-fetched page. The seam the stub loader hands to, and the same path a
     * served response takes -- one renderer, so the stub cannot render differently from live.
     */
    setWorklist(rows) {
      setSession(withWorklist(session, normaliseWorklist(rows), session.worklistSeq));
    },
    /** Paste outcome: an aggregate count, never per-row noise. Fed by the artifact gateway. */
    showArtifactResult(result) {
      if (!el.pasteResult) return;
      el.pasteResult.hidden = !result;
      if (!result) return;
      setChildText(el.pasteResult, '[data-me2-paste-applied]', result.accepted);
      setChildText(el.pasteResult, '[data-me2-paste-rejected]', result.rejectedTotal);
      setChildText(el.pasteResult, '[data-me2-paste-reason]', rejectionSummary(result.rejected));
    },
    // Returns the frozen record, so a caller cannot reach in and mutate the session.
    peek() { return session; },
  });
}

function span(doc, cls, value) {
  const s = doc.createElement('span');
  s.className = cls;
  s.textContent = value;
  return s;
}

/**
 * The served payload -> what the view model reads. The customs post, and there is exactly one.
 *
 * 🔴 CELLS ARRIVE AS `[x, y]` PAIRS, NOT `{x, y}` OBJECTS. Anything that indexes `.x` on a
 *    reference cell reads `undefined`, seats every cell at NaN and paints nothing -- an empty
 *    picture that looks like "this map has no dies" rather than like a bug. The conversion
 *    happens here and nowhere else.
 *
 * The decoder owns the field renames (`refusal`, `reference.cells`, `candidates`,
 * `ruling.winner`, and the declaration block's counts); this function owns only the shape the
 * renderer needs, so a wire rename lands in one file and a render change lands in another.
 */
export function adaptPayload(raw) {
  const decoded = decodeReferenceView(raw);
  const refCells = toCells(raw && raw.reference && raw.reference.cells);
  const srcCells = toCells(raw && raw.sources && raw.sources.cells);
  // The unit's maps can disagree about what is declared, and picking a winner among
  // declarations is a JUDGEMENT the client must not make. A single frame is adopted as "what
  // is currently declared" only when the tally has exactly one entry AND nothing is
  // unattested; otherwise there is no `현재 선언` badge, which is the honest answer.
  const frames = Object.keys(decoded.declaredFrameCounts || {});
  const storedId = (frames.length === 1 && !decoded.unattestedMaps) ? frames[0] : null;

  return {
    stored_candidate_id: storedId,
    sources: decoded.sources.length > 0
      ? decoded.sources.map((s, i) => ({
          id: s.id || `source_${i}`,
          label: s.label || s.id || `출처 ${i + 1}`,
          // The provenance token gates the badge: a raw frame string is what the registrar
          // emits with nobody looking, so a badge keyed on the string alone puts `현재 선언`
          // on maps nobody ever measured.
          stored_candidate_id: s.declaredFrameSource === 'declared' ? s.declaredFrame : null,
          cells: i === 0 ? srcCells : [],
        }))
      : (srcCells.length > 0 ? [{ id: 'source', label: '출처', stored_candidate_id: null, cells: srcCells }] : []),
    floor_cells: refCells,
    per_candidate: decoded.scorings,
    occupancy_winner_id: null,
    map_count: decoded.counts.mapCount,
    excluded_map_count: decoded.counts.excludedMapCount,
    discriminating_dies: decoded.counts.discriminatingDies,
    elapsed_ms: decoded.counts.elapsedMs,
    refusal_detail: decoded.refusalDetail,
    // 🔴 WHICH COLUMN PAIR DID THE SERVER ACTUALLY READ. Null today: the route takes no column
    //    parameter and the `unit` block echoes none (`server/main.py:4160-4168`,
    //    `server/map_alignment.py:677`). Read here rather than assumed, so the day the server
    //    echoes it the screen starts attributing instead of refusing -- with no other change.
    answered_columns: answeredColumns(raw),
    // Declared on the wire (`reference.kind`), never inferred from the shape of the cells.
    // This is what tells "we had values" from "we only had occupancy", and those are two
    // different answers to "why could you not tell them apart".
    reference_kind: (raw && raw.reference && raw.reference.kind) || null,
    __decoded: decoded,
    __context: verdictContext(decoded),
  };
}

/**
 * WHICH PAIR THE SERVER ACTUALLY READ, and WHO CHOSE IT. The route now answers both:
 * `unit.columns.{x,y,value} = {column, origin}` with origin `chosen` | `proposed` | `absent`
 * (`server/map_alignment.py:474-476`, echoed at `:813-818`).
 *
 * 🔴 `proposed` IS NOT `chosen`, AND FLATTENING THEM HERE WOULD UNDO THE WHOLE POINT OF THE
 *    SERVER SENDING TWO WORDS. A proposed column is a preset that filled itself in; a chosen
 *    one is a name the operator gave. Both identify the pair that was read -- so both make the
 *    answer ATTRIBUTABLE -- but only the second is an agreement, and the write still refuses to
 *    rest on the first.
 */
function answeredColumns(raw) {
  const cols = raw && raw.unit && raw.unit.columns ? raw.unit.columns : null;
  if (!cols) return null;
  const x = cols.x && cols.x.column ? cols.x.column : null;
  const y = cols.y && cols.y.column ? cols.y.column : null;
  if (!x || !y) return null;
  const chosen = (a) => a && a.origin === 'chosen';
  return {
    x, y,
    val: cols.value && cols.value.column ? cols.value.column : null,
    // The pair is agreed only when BOTH axes were named by a person.
    agreed: chosen(cols.x) && chosen(cols.y),
    // The server's own reason when it could not even propose a value column.
    valueReason: (cols.value && cols.value.reason) || null,
  };
}

/** `[[x, y], ...]` -> `[{x, y}, ...]`. Objects are passed through so a capture still renders. */
function toCells(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const c of list) {
    if (Array.isArray(c)) {
      const x = Number(c[0]);
      const y = Number(c[1]);
      if (Number.isFinite(x) && Number.isFinite(y)) out.push({ x, y });
    } else if (c && typeof c === 'object' && Number.isFinite(Number(c.x))) {
      out.push({ x: Number(c.x), y: Number(c.y) });
    }
  }
  return out;
}

function pickSource(payload, focusedId) {
  if (!payload || !Array.isArray(payload.sources) || payload.sources.length === 0) return null;
  if (focusedId && focusedId !== CROSS_SOURCE_ROW_ID) {
    const hit = payload.sources.find(s => s.id === focusedId);
    if (hit) return hit;
  }
  return payload.sources[0];
}

/** `rot270_back` -> `270° · 뒷면`. The stored spelling stays visible beside it in the markup. */
function spellFrame(candidateId) {
  const axes = parseCandidateId(candidateId);
  if (!axes) return candidateId;
  return `${axes.rotation}° · ${axes.side === 'back' ? '뒷면' : '앞면'}`;
}

function gridSpan(payload, axis) {
  const cells = (payload && payload.floor_cells) || [];
  let max = 0;
  for (const c of cells) { const v = Number(c[axis]); if (Number.isFinite(v) && v > max) max = v; }
  return max + 1;
}

function numOr(v, dflt) {
  const n = Number(v);
  return Number.isFinite(n) ? n : dflt;
}

function round1(n) { return Math.round(n * 10) / 10; }

/**
 * `{token:'대칭 기준', count:3}` -> `대칭 기준 · 후보 3`.
 * A label, a separator and a count. Not a template with a slot -- that shape is how
 * translationese gets in, and a decoder that only ever hands over a token and a number cannot
 * produce one.
 */
/**
 * The headline's `.me2-num` slot.
 *   scored    -> `일치 512 / 판별 528`   the counts, denominator kept
 *   no-winner -> `구별 안 됨 · 후보 3개`  a label, a separator and a count
 * The computing and unscorable states are not handled here at all: their siblings
 * (`.me2-busy`, `.me2-unknown`) carry those words and CSS chooses between them, so writing
 * anything for them would be a second copy of a decision the page already makes.
 */
function headlineNum(vm) {
  if (vm.state === VIEW_STATE.SCORED_NO_WINNER) {
    const n = vm.cause && vm.cause.count !== null ? vm.cause.count : null;
    return n === null ? '구별 안 됨' : `구별 안 됨 · 후보 ${n}개`;
  }
  return vm.summary.hasNumerals ? vm.summary.countText : '';
}

function causeLine(cause) {
  if (!cause) return '';
  if (cause.detail) return cause.detail;      // the server's sentence, verbatim
  if (!cause.token) return '';
  return cause.count === null ? cause.token : `${cause.token} · 후보 ${cause.count}`;
}

export { VIEW_STATE, createApiClient, spellFrame };
