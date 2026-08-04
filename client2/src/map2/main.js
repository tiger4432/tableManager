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
         withFocusedSource, withArmed, withConfig, PHASE } from './session.js';
import { computeSeating, compareSeatings, unionBounds } from './seating.js';
import { layoutFor } from './painter.js';
import { buildViewModel, VIEW_STATE, CROSS_SOURCE_ROW_ID } from './view_model.js';
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
  badgeUnscorable: 'me2-badge-unscorable',
  badgeRemaining: 'me2-badge-remaining',
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
  let loadUnit = (decision) => api.loadReferenceView(decision);
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

    renderCounts(vm);
    renderSources(vm);
    renderCandidates(vm);
    renderConfirm(vm);
    renderSecondMetric(vm);
    paint(vm);
    bar.repaints++;
    return vm;
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
    // One grid per source, already laid out by the page as 2 columns (flip) x 4 rows (turn).
    // The geometry of the control is the geometry of the operator's two motions, so there is
    // no mental translation to pay and no rotate button anywhere on this screen: the same
    // transform applied to both compared sets leaves their relation invariant, so a rotate
    // control cannot inform.
    for (const cell of queryAll(doc, '[data-me2-candidate]')) {
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
    if (!el.metricConflict) return;
    el.metricConflict.hidden = !vm.secondMetric;
    if (vm.secondMetric) el.metricConflict.textContent = vm.secondMetric;
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
    const started = withDecision(session, decision);
    setSession(started);
    const seq = started.requestSeq;
    bar.fetches++;
    // ONE request. Reference cells, source cells and all eight candidate scorings together.
    // There is deliberately no per-candidate fetch anywhere in this program: eight round trips
    // per row would blow the 30-second bar on their own.
    Promise.resolve(loadUnit(decision))
      .then(raw => { setSession(withPayload(session, adaptPayload(raw), seq)); markLoop(); })
      .catch(err => setSession(withError(session, err, seq)));
  }

  function markLoop() {
    if (bar.startedAt !== null) bar.lastLoopMs = Date.now() - bar.startedAt;
  }

  function onConfirm() {
    bar.actions++;
    const vm = buildViewModel({ session, verdict: currentVerdict() });
    if (!vm.confirm.enabled) return;
    // Reading is frictionless; this write gets exactly one confirmation and it is not a modal.
    if (!session.armed) { setSession(withArmed(session, true)); return; }
    const sourceIds = (session.payload.sources || []).map(s => s.id);
    Promise.resolve(api.confirmFrame(session.decision, vm.selectedCandidateId, sourceIds))
      .then(() => { setSession(withArmed(session, false)); })
      .catch(() => { setSession(withArmed(session, false)); });
  }

  function onWorklistClick(e) {
    const row = e.target && e.target.closest ? e.target.closest('[data-me2-row]') : null;
    if (!row) return;
    for (const other of queryAll(doc, '[data-me2-row]')) other.setAttribute('aria-selected', 'false');
    row.setAttribute('aria-selected', 'true');
    selectDecision({ eqp: row.getAttribute('data-eqp'), product: row.getAttribute('data-product') });
  }

  for (const host of [el.worklistRows, el.worklistUnscorable]) {
    if (host) host.addEventListener('click', onWorklistClick);
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
    if (e.key === 'Enter' && el.confirmBtn && !el.confirmBtn.disabled) onConfirm();
  });
  if (el.exportBtn) {
    el.exportBtn.disabled = !artifactImplemented();
    if (!artifactImplemented()) el.exportBtn.title = '엑셀 양식 내보내기는 아직 연결되지 않았습니다.';
  }

  // ── helpers that touch the DOM ───────────────────────────────────────────────
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
    if (doc.defaultView && doc.defaultView.console) doc.defaultView.console.warn(`[map2] ${msg}`);
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
    setConfig(config) { setSession(withConfig(session, config)); },
    setWorklist(rows) { renderWorklist(doc, el, rows); },
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

function renderWorklist(doc, el, rows) {
  const scorable = el.worklistRows;
  const unscorable = el.worklistUnscorable;
  if (!scorable) return;
  scorable.textContent = '';
  if (unscorable) unscorable.textContent = '';
  let below = 0;
  for (const row of rows || []) {
    // Unscorable rows sink below a visible boundary and carry NO per-row decoration: roughly
    // half the population lands there, and decorating half a population trains the eye to
    // ignore the decoration -- after which it also fails on the cases that are real.
    const isBelow = row.scorable === false;
    const host = isBelow && unscorable ? unscorable : scorable;
    if (isBelow) below++;
    const node = doc.createElement('button');
    node.type = 'button';
    node.className = 'me2-wl-row';
    node.setAttribute('role', 'option');
    node.setAttribute('aria-selected', 'false');
    node.setAttribute('data-me2-row', '');
    node.setAttribute('data-eqp', row.eqp);
    node.setAttribute('data-product', row.product);
    node.setAttribute('data-state', isBelow ? 'unscorable' : (row.state || 'pending'));
    node.appendChild(span(doc, 'me2-wl-key', `${row.eqp} · ${row.product}`));
    const badge = span(doc, 'me2-wl-badge', isBelow ? '' : (row.state === 'confirmed' ? '확정' : '미확정'));
    badge.setAttribute('data-me2-row-state', '');
    node.appendChild(badge);
    const maps = span(doc, 'me2-wl-maps', row.map_count != null ? `맵 ${row.map_count}` : '');
    maps.setAttribute('data-me2-row-maps', '');
    node.appendChild(maps);
    host.appendChild(node);
  }
  // One badge, one count, never one mark per row.
  if (el.badgeUnscorable) el.badgeUnscorable.textContent = `기준 없음 ${below}건`;
  if (el.badgeRemaining) el.badgeRemaining.textContent = `남은 판정 ${Math.max(0, (rows || []).length - below)}건`;
  if (el.worklistEmpty) el.worklistEmpty.hidden = (rows || []).length > 0;
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
    __decoded: decoded,
    __context: verdictContext(decoded),
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
