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
         withFocusedSource, withConfig, withCatalog, withQuestion, withConfirmFailed,
         withWorklistQuery, withWorklist, withWorklistError, withConfirmed,
         columnKey, isAskable, isUnset, BINDING_DECLARED, PHASE } from './session.js';
import { computeSeating, compareSeatings, unionBounds } from './seating.js';
import { layoutFor, paintComparison, createCanvasSurface } from './painter.js';
import { buildViewModel, VIEW_STATE, CROSS_SOURCE_ROW_ID, WORDS, CAUSE, ATTRIBUTION,
         UNKNOWN } from './view_model.js';
import { decideVerdict } from './verdict_bridge.js';
import { parseCandidateId, candidateList } from './candidates.js';
import { createApiClient } from './api.js';
import { decodeReferenceView, verdictContext } from './decode.js';
// The provenance vocabulary, imported rather than re-spelled. A string literal `'assumed'` here
// is a second copy of a word the server owns, and the day the two drift nothing says so.
import { ASSUMED, CONFIRMED, DECLARED } from './declaration.js';
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
  // The rule names the decision unit, so it is the FIRST thing chosen and sits ahead of the
  // table. Bound by name before the markup lane lands it -- `bindElements` tolerates absence.
  ruleSelect: 'me2-rule-select',
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
  // 🔴 ACCEPTING THE BORROWED GEOMETRY IS AN ACT AND NEEDS A CONTROL, exactly like agreeing to a
  //    proposed column pair. It is bound here BEFORE the markup lane lands it -- `bindElements`
  //    tolerates absence and reports the id in `missing` -- so the wiring is complete the moment
  //    the node appears and nothing has to be re-derived then.
  //
  svg: 'me2-picture-svg',
  layerFloor: 'me2-layer-floor',
  layerMiss: 'me2-layer-miss',
  layerOnlyOne: 'me2-layer-onlyone',
  layerAlone: 'me2-layer-alone',
  caption: 'me2-picture-caption',
  refusal: 'me2-refusal',
  headline: 'me2-verdict-headline',
  // `cause: 'me2-verdict-cause'` IS GONE, and it is gone because the NODE is gone. The markup
  // deleted it on purpose and says so; a binding that outlives its node is how a slot nobody
  // can see ends up holding the one string that mattered. See `render`.
  sourceList: 'me2-source-list',
  sourcesMeta: 'me2-sources-meta',
  metricConflict: 'me2-metric-conflict',
  confirmBtn: 'me2-confirm-btn',
  confirmSentence: 'me2-confirm-sentence',
  confirmNote: 'me2-confirm-note',
  confirmHint: 'me2-confirm-hint',
  // The footer itself, bound only to carry the refusal state attribute. It is the smallest
  // node that contains both the sentence and the control the refusal is about.
  confirmBar: 'me2-confirmbar',
  exportBtn: 'me2-export-btn',
  pasteResult: 'me2-paste-result',
});

/** The legend the authored grid already carries, so the two spellings cannot drift apart. */
const CAND_LEGEND = '숫자 = 일치 / 판별 다이';

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

// 🔴 THE EIGHT PICTURES ARE THE DELIVERABLE, NOT A DECORATION. The scoring cannot discriminate
//    on this operator's data -- eight identical counts is the ordinary answer here -- and a
//    human looking at a wafer can. Eight numbers do not let them do that; eight PICTURES do.
//
//    THEY ARE CANVASES, AND THAT IS A SCALE DECISION RATHER THAN A TASTE ONE. The main stage is
//    SVG, one `<rect>` per seat, and a production map runs to thousands of dies -- eight SVG
//    copies of it is tens of thousands of nodes on every repaint, which is a freeze. The pieces
//    are the same either way: `paintSeating` and `paintComparison` take a SURFACE, and
//    `createCanvasSurface` is the one this file was always going to need. Nothing here is a
//    second painter.
//
//    The backing store is larger than the CSS box on purpose, so the picture stays crisp when
//    the browser downscales it. 128px over a 45-column wafer is ~2.8px per die: enough for the
//    gross orientation the operator is reading, which is what they said they are looking for.
const THUMB = Object.freeze({ width: 128, height: 128, padding: 3 });

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
  // A one-line reason the SHELL can always show, independent of any payload. Bootstrap failures
  // live here: the page must draw and say why, never draw nothing.
  let notice = '';
  // The rules on offer. Held here rather than in the session because a rule is not part of the
  // QUESTION -- it declares what a unit IS, so changing it replaces the catalog and the
  // worklist wholesale rather than re-asking the same question a different way.
  let ruleModel = { options: [], proposed: false };
  let onRulePick = null;
  // Action accounting for the switchover bar: 8 maps, <= 4 actions each, <= 30 s, 0 writes.
  const bar = { actions: 0, fetches: 0, repaints: 0, startedAt: null, lastLoopMs: null };
  // 🔴 THE CONFIRM IS IN FLIGHT. Not session state: it belongs to one request, and a session
  //    field would outlive the request across a row change and wedge the button shut. See
  //    `onConfirm`; the render reads it to disable the control while the POST is running.
  let confirmInFlight = false;

  function setSession(nextSession) {
    session = nextSession;
    render();
  }

  // ── the layers, called with values ───────────────────────────────────────────
  function currentVerdict() {
    if (session.phase !== PHASE.READY || !session.payload) return null;
    // Thresholds are PASSED IN. There is no literal anywhere on this path: without them the
    // verdict layer refuses to rank rather than inventing a minimum.
    //
    // 🔴 THE RULING'S OWN PAIR WINS, AND `session.config` IS THE FALLBACK. Two reasons, and
    //    both were measured rather than reasoned:
    //
    //    (a) THE THRESHOLDS ARE PER AXIS. The server hands `_rule_on` either `index_thresholds`
    //        or `thresholds` depending on the metric (`map_alignment.py:1194`) because each
    //        axis counts a different thing. Scoring the index axis against the occupancy bar is
    //        the same class of error as reading the occupancy numbers under an index ruling --
    //        the client reaching a different conclusion from the same evidence.
    //    (b) `loadAlignConfig` REJECTS UNCONDITIONALLY (`api.js`, `ROUTES.config` is null: the
    //        route does not exist). So `session.config` is null on every live run, and every
    //        unit on this screen read `채점 불가 · 기준값 없음` no matter what the server ruled.
    //        MEASURED 2026-08-06 on all three seeded `dt_map` units.
    //
    //    This is not a default invented in code -- it is the declaration the server read from
    //    its own config and already applied, arriving on the wire beside the answer it
    //    produced. When the ruling carries no thresholds the config still speaks, and when
    //    neither does the verdict layer still refuses.
    const thresholds = session.payload.ruling_thresholds || session.config || null;
    // The context is assembled by the decoder, not by hand here. Two call sites building it
    // themselves is how they start disagreeing about what "no reference" meant.
    return verdictFn(
      session.payload.per_candidate,
      thresholds,
      session.payload.__context || { refusalDetail: session.payload.refusal_detail });
  }

  // ── writing to the screen ────────────────────────────────────────────────────
  function render() {
    const vm = buildViewModel({ session, verdict: currentVerdict() });

    if (el.workbench) el.workbench.setAttribute('data-me2-state', STATE_ATTR[vm.state] || 'computing');
    // 🔴 AN ANSWER REACHED ON BORROWED GEOMETRY MUST NOT LOOK LIKE ONE REACHED ON A DECLARATION.
    //    One hook on the workbench, next to the state, so the whole result region can be styled
    //    from a single place rather than each panel growing its own marker and drifting.
    //    ASKED FOR BY NAME (markup lane): `#me2-workbench[data-me2-assumed="true"]` should read
    //    as the existing proposal shape -- dashed and muted, the same treatment
    //    `.me2-scope-select[data-me2-proposed="true"]` already carries -- because it means the
    //    same thing: what is here was not measured. The attribute is written whether or not any
    //    rule matches it yet; a hook nobody styles is inert, a fact nobody carries is lost.
    if (el.workbench) {
      el.workbench.setAttribute('data-me2-assumed', vm.assumption.applied ? 'true' : 'false');
    }
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
    // 🔴 THE CAUSE LINE IS NOT WRITTEN TO A NODE, AND THAT IS THE PAGE'S OWN DECISION HONOURED
    //    RATHER THAN AN OMISSION. `#me2-verdict-cause` was deleted from the markup deliberately
    //    (`map_editor2.html`, and the comment there says not to revive it by accident); this
    //    file kept writing to it anyway, which was harmless only while `vm.cause.detail` was
    //    empty in the no-winner state. Now that the cause carries the SERVER'S SENTENCE there
    //    too, a page that still had that node would print the same sentence twice IN THE SAME
    //    PANEL -- here and in `#me2-refusal` directly below, both fed by `causeLine`. The whole
    //    cause -- token, count and measurements -- still goes to the console record, which is
    //    the diagnostic surface the markup lane designated when it removed the node.
    text(el.caption, vm.caption);
    setAttrText(doc, '[data-me2-picture-meta]', vm.meta);

    // The server's own refusal sentence, verbatim, WITH the measurements that sentence left
    // behind. A second copy of it on this side would be two spellings of one fact, which is the
    // defect class this round exists to close -- so both halves are the server's strings and
    // `causeLine` only joins them, in the one place that renders this.
    //
    // 🔴 ONE JOINER, NOT TWO. This slot used to read `vm.cause.detail` directly while the cause
    //    line beside it went through `causeLine`, so a fix to one of them was invisible in the
    //    other. Whatever the operator reads about why there is no answer now comes from a
    //    single function, and the console record below quotes that same string.
    if (el.refusal) {
      text(el.refusal, vm.state === VIEW_STATE.NOT_SCORABLE ? causeLine(vm.cause) : '');
    }

    renderQuestion(vm);
    renderWorklist(vm);
    renderCounts(vm);
    renderSources(vm);
    renderCandidates(vm);
    renderConfirm(vm);
    renderSecondMetric(vm);
    paint(vm);
    logDiagnosis(vm);
    // LAST, AND GUARDED. See `renderCandidateThumbs`: nothing above may be taken down by a
    // throw in the picture layer, and a failure has to name itself rather than emptying a panel.
    try {
      renderCandidateThumbs(vm);
    } catch (e) {
      warn(`candidate thumbnails failed: ${(e && e.message) || e}`);
    }
    bar.repaints++;
    return vm;
  }

  /**
   * The set-up row. Five controls, one question. Options are written from the view model's
   * values; this file chooses no label and composes no clause.
   */
  function renderQuestion(vm) {
    const q = vm.question;
    fillSelect(el.ruleSelect, ruleModel.options);
    // 🔴 A PROPOSED RULE IS MARKED, exactly like a proposed column pair. One declared candidate
    //    makes the screen usable; it is still not an agreement.
    if (el.ruleSelect) {
      el.ruleSelect.setAttribute('data-me2-proposed', ruleModel.proposed ? 'true' : 'false');
    }
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
    // Same rule for the borrowed geometry: the control exists only while there is an untaken
    // offer. Once the claim has been made it goes away -- a control still reading "accept"
    // beside an applied assumption invites the operator to assert the same thing twice.
    if (el.workbench) {
      el.workbench.setAttribute('data-me2-evidence', vm.evidence.kind);
      el.workbench.setAttribute('data-me2-attribution', vm.attribution.state);
    }
    // A label joined to a value by a separator. Never a template with a slot.
    text(el.questionNote, questionNote(vm));
    // 🔴 CAUTION IS FOR AN ANSWER STANDING ON A CLAIM, NOT FOR THE OFFER. An offer is an ordinary
    //    state -- most units on this deployment are undeclared -- and colouring it a warning
    //    would paint half the worklist yellow and teach the eye past the colour, which is the
    //    same reason the worklist decorates a boundary rather than every row below it. An
    //    APPLIED assumption is different: the numbers on screen rest on a wafer nobody measured.
    if (el.questionNote) {
      // Caution once NUMBERS REST ON SOMETHING NOBODY DECLARED -- a borrowed wafer, or a bar
      // the server substituted. The two are different facts with the same consequence for the
      // reader, so they drive one tone rather than growing a second visual language.
      if (vm.assumption.applied || vm.provisional.active) {
        el.questionNote.setAttribute('data-me2-note-tone', 'caution');
      } else el.questionNote.removeAttribute('data-me2-note-tone');
    }
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
    // The bootstrap's reason comes first: if the screen could not even find a rule or a table,
    // that outranks anything it could say about the answer it does not have.
    if (notice) parts.push(notice);
    if (vm.question.proposalWord) parts.push(vm.question.proposalWord);
    if (vm.evidence.occupancyOnly) parts.push(CAUSE.reference_no_values);
    if (vm.attribution.state === ATTRIBUTION.UNSTATED) parts.push(WORDS.columnsUnstated);
    // 🔴 THE SERVER'S SENTENCE, VERBATIM, AND IT GOES LAST. Last because the tokens ahead of it
    //    are about whether the screen can answer at all, and this one is about what the answer
    //    would rest on. Verbatim because `compose_assumption_offer` composes it for this line --
    //    the same rule as `refusal` -- and it NAMES THE FLOOR the dimensions come from. A
    //    shortened form would leave the operator asserting that two maps are one wafer without
    //    being told which two, which is not a claim anybody can make.
    //
    //    Present in BOTH states on purpose: as an offer it is what the operator acts on, and as
    //    an applied assumption it is the disclosure. `unavailable` carries no sentence at all,
    //    so nothing is added on the ordinary runs where there is nothing to say.
    if (vm.assumption.line) parts.push(vm.assumption.line);
    // 🔴 THE PROVISIONAL CAVEAT RIDES THE SAME SLOT, AND IT LEADS. Both are one sentence about
    //    what the answer on screen rests on, so they belong in one place -- but this one
    //    qualifies the RANKING itself, while the assumption qualifies the geometry the ranking
    //    was computed over. A reader who takes only the first clause should get the stronger
    //    caveat, and "this winner was chosen against a bar nobody set" outranks "the wafer
    //    dimensions were borrowed".
    //
    //    THE SENTENCE IS THE SERVER'S, VERBATIM. It exists because on a SCORED run
    //    `compose_refusal` composes nothing, so `#me2-refusal` is empty exactly when this has
    //    to be said -- which is why the caveat travels on the ruling and lands here instead.
    if (vm.provisional.line) parts.unshift(vm.provisional.line);
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

  /**
   * 🔴 THE PAGE PUBLISHES THE SOURCE ROW AND ITS EIGHT CANDIDATE CONTROLS INSIDE A `<template>`,
   *    AND NOTHING WAS CLONING IT. Measured on the live page: `[data-me2-candidate]` matched
   *    ZERO nodes and `[data-me2-candidates-for]` matched zero containers, while the template's
   *    own content held all eight. Template content is inert -- it is not in the document, CSS
   *    does not reach it and `querySelectorAll` does not see it -- so no amount of correct view
   *    model could put a candidate on screen. That is the other half of "a tie showed nothing".
   *
   *    This clones the page's OWN markup and fills in exactly the fields the wiring contract
   *    above the template names (`data-source-field`, `aria-controls`, the grid's `id`). It
   *    invents no container, no class and no ordering, which is the same rule `fillGrid`
   *    follows. `data-me2-candidates-for` is left as the page authored it: which key a grid
   *    carries is the markup lane's model to state, and guessing one here would be this file
   *    asserting a per-column-set layout nobody declared.
   *
   *    The cross-source row is the (N+1)th and stays last, so clones go in ahead of it.
   */
  function ensureSourceRows(sources) {
    const tpl = doc.getElementById('me2-source-row-template');
    const list = el.sourceList;
    if (!list || !tpl || !tpl.content || typeof tpl.content.cloneNode !== 'function') return;
    const known = new Set(queryAll(doc, '[data-me2-source]')
      .map(r => r.getAttribute('data-source-field')));
    const cross = queryAll(list, '[data-me2-source]')
      .find(r => r.getAttribute('data-source-field') === CROSS_SOURCE_ROW_ID) || null;
    for (const src of sources) {
      if (!src || !src.id || known.has(src.id)) continue;
      const frag = tpl.content.cloneNode(true);
      const row = frag.querySelector ? frag.querySelector('[data-me2-source]') : null;
      const grid = frag.querySelector ? frag.querySelector('[data-me2-candidates-for]') : null;
      if (!row || !grid) return;
      const gridId = `me2-cands-${String(src.id).replace(/[^A-Za-z0-9_-]/g, '_')}`;
      row.setAttribute('data-source-field', src.id);
      row.setAttribute('aria-controls', gridId);
      grid.setAttribute('id', gridId);
      // Which source this grid belongs to, so the accordion can show one at a time without
      // this file re-deriving the pairing from an id string on every render.
      grid.setAttribute('data-me2-cands-source', src.id);
      if (cross) list.insertBefore(frag, cross); else list.appendChild(frag);
      known.add(src.id);
    }
  }

  function renderSources(vm) {
    const payload = session.payload;
    const sources = payload && Array.isArray(payload.sources) ? payload.sources : [];
    text(el.sourcesMeta, sources.length > 0 ? `출처 ${sources.length}개` : '출처 없음');
    ensureSourceRows(sources);

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
      // 🔴 PER MAP, BECAUSE "SOME MAPS BORROWED" IS NOT AN ANSWER TO "DID THIS ONE?". A unit
      //    mixes declared and borrowed maps in one list, and a marker only on the aggregate
      //    would leave every row looking equally measured. Two attributes, because the payload
      //    carries two facts: what the map declares about itself, and what this run stood on.
      //
      //    ASKED FOR BY NAME (markup lane): `[data-me2-source][data-me2-proposed="true"]` should
      //    carry the same dashed-and-muted treatment as a proposed column pair. The attribute is
      //    the existing one on purpose -- borrowed geometry and a guessed binding are the same
      //    claim ("this was not measured") and must not grow two visual languages.
      row.setAttribute('data-me2-geometry', src.geometry || 'unknown');
      row.setAttribute('data-me2-geometry-basis', src.geometry_basis || 'unknown');
      // 🔴 `proposed` STAYS `assumed`-ONLY, AND A CONFIRMED ROW MUST NOT JOIN IT. The attribute
      //    means "this was not measured -- treat it as a guess", which is true of a borrow and
      //    false of a confirmation: a confirmation rests on a match against a per-product
      //    valid-die map and carries a `confirmation_uid` that makes it re-checkable. Putting
      //    it in the guess bucket understates it exactly as `declared` would overstate it.
      row.setAttribute('data-me2-proposed', src.geometry_basis === ASSUMED ? 'true' : 'false');
      const declared = src.stored_candidate_id || null;
      // 🔴 THE THIRD STATE, AND IT IS A LABEL RATHER THAN ANYTHING LARGER (lead PM ruling
      //    2026-08-06). `attested_maps` keeps counting `declared` only -- nobody declared a
      //    confirmed map and the count is literally true -- but the ROW may not therefore read
      //    `고르지 않음`, because a human did confirm that frame and the screen would be
      //    stating the opposite. Three visibly distinct answers in the ONE slot the row already
      //    has: the frame (declared), the frame with a confirm mark (confirmed), and `고르지
      //    않음` (neither). No new region, no new mode, no new modal, no new control.
      //
      // ⚠️ IT IS DELIBERATELY NOT `stored_candidate_id`. That field decides WHAT GETS DRAWN
      //    (`paint` reads it as the seat to use when nothing is selected, and `view_model`
      //    falls back to it the same way), so promoting a confirmation into it would
      //    silently move the picture as well as the
      //    label. A confirmation is not a selection; this round changes what the row SAYS and
      //    nothing about what the canvas shows.
      const confirmed = !declared && src.confirmed_candidate_id ? src.confirmed_candidate_id : null;
      row.setAttribute('data-me2-attest',
        declared ? 'declared' : (confirmed ? 'confirmed' : 'none'));
      setChildText(row, '[data-me2-source-value]',
        declared ? spellFrame(declared)
          : confirmed ? `✓ ${spellFrame(confirmed)}`
            : '고르지 않음');
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
    //
    // 🔴 THE EIGHT ARE NOT GATED ON A COLUMN KEY, AND THAT GATE IS WHY A TIE SHOWED NOTHING.
    //    The page ships the grid `hidden` with `data-me2-candidates-for=""`, and the only
    //    branch that ever unhid it was guarded by `if (activeKey && ...)`. Until a coordinate
    //    pair resolves -- which never happens on a server whose `/schema` and reference routes
    //    are not reachable -- `columnKey` returns `''`, the guard never runs, and eight controls
    //    the markup had already authored stayed invisible. A key decides WHICH grid is the
    //    active one; it does not decide whether the operator may see the candidate set at all.
    const activeKey = columnKey(session.question && session.question.columns);
    const grids = queryAll(doc, '[data-me2-candidates-for]');
    const keyed = grids.filter(g => g.getAttribute('data-me2-candidates-for') === activeKey);
    const drawnSource = pickSource(session.payload, session.focusedSourceId);
    const activeSourceId = drawnSource ? drawnSource.id : null;
    for (const g of grids) {
      // A grid cloned for a source belongs to that source: one open at a time, and the one
      // that is open is the one whose cells the picture is drawing. There is always exactly
      // one, because `pickSource` falls back to the first source rather than to nothing.
      const paired = g.getAttribute('data-me2-cands-source');
      // When no grid carries the active key, every candidate control on the page IS the one
      // grid -- a half-migrated page renders exactly as it did rather than going blank.
      const mine = paired
        ? paired === activeSourceId
        : (keyed.length > 0 ? g.getAttribute('data-me2-candidates-for') === activeKey : true);
      g.hidden = !mine;
      if (mine && queryAll(g, '[data-me2-candidate]').length === 0) fillGrid(g, vm);
    }
    const scope = keyed.length > 0 ? keyed : [doc];
    // The eight are in DECLARATION ORDER, never sorted by score -- sorting by score IS a
    // ranking. Said out loud in the legend the grid already carries, one line, only when no
    // winner emerged; with a winner the badge says it and this would be noise.
    const ranked = vm.state === VIEW_STATE.SCORED_WINNER;
    for (const legend of queryAll(doc, '.me2-cand-legend')) {
      legend.textContent = ranked ? CAND_LEGEND : `${CAND_LEGEND} · 순위 아님`;
    }
    for (const host of scope) {
    for (const cell of queryAll(host, '[data-me2-candidate]')) {
      const code = cell.getAttribute('data-frame-code');
      const card = vm.candidates.find(c => c.id === code);
      if (!card) continue;
      cell.setAttribute('aria-pressed', String(card.selected));
      cell.disabled = card.inert;
      // 🔴 EQUAL SCORES MUST BE VISIBLY EQUAL. Eight rows reading the same two numbers is the
      //    honest picture of a tie, and it is the only thing that lets the operator check the
      //    claim instead of believing it. Written into the `[data-me2-cand-*]` spans INSIDE
      //    `.me2-num`, never into `.me2-num` itself -- the three-sibling pattern is what keeps
      //    the computing and unscorable states from leaking a stale numeral. And written only
      //    when there IS a measured number: never blanked, never given a `0` stand-in.
      //
      // 🔴 AND THE MARK THAT SAYS THIS CELL HAS REAL NUMBERS. `[data-me2-state]` hides
      //    `.me2-num` wholesale outside the scored states, which is right for the headline
      //    and the summary -- those slots ARE the verdict -- and wrong for the eight, whose
      //    counts are measurements that survive a refusal to rank. The attribute is per CELL,
      //    not per state, so a cell with nothing measured still says `미상` rather than
      //    showing a bare separator.
      //
      // 🔴 AND WHICH KIND OF NOTHING, WHEN THERE IS NOTHING. `scored=false` alone says only
      //    "no numbers here", which is true of a frame the payload never mentioned AND of a
      //    frame the side declaration excluded before anything was measured. Those are
      //    different facts with different repairs -- the second one has a REASON on the wire --
      //    and the screen drew them identically, marked `scored=true` on a placeholder `0`.
      //    The state is the server's own token, written as a hook so the styling lane can tell
      //    them apart without this file inventing a colour or a Korean word for either.
      if (card.agree !== null && card.discriminating !== null) {
        setChildText(cell, '[data-me2-cand-agree]', card.agree);
        setChildText(cell, '[data-me2-cand-discriminating]', card.discriminating);
        cell.setAttribute('data-me2-cand-scored', 'true');
      } else {
        cell.setAttribute('data-me2-cand-scored', 'false');
      }
      cell.setAttribute('data-me2-cand-state', card.state || '');
      // The count slot's OTHER sibling. `.me2-unknown` is authored `미상` and shows whenever the
      // cell is not scored; when the server said WHY this frame has no numbers, its sentence
      // goes here instead. Written every pass, so a cell that becomes scored again on the next
      // payload gets the authored word back rather than keeping a stale reason.
      // The count slot's OTHER sibling. `[data-me2-cand-unknown]` is authored `미상`, and `미상`
      // is the right word for a frame the payload never mentioned. A frame the payload DID
      // mention and marked as never considered is a different fact, and the server sent the
      // sentence for it -- so that sentence replaces the generic word, in that cell only.
      //
      // 🔴 TOUCHED ONLY WHEN THERE IS SOMETHING TO SAY, AND PUT BACK BY THE SAME RULE. The
      //    three-sibling guarantee is that this renderer does not disturb words it is not
      //    responsible for, so a cell with no reason is left exactly as the page authored it --
      //    and a cell that HAD one gets the authored word back when the reason goes away,
      //    rather than keeping a sentence about a payload that is no longer on screen. The mark
      //    is an attribute this renderer wrote itself; nothing here parses its own output back.
      const why = (card.agree === null || card.discriminating === null) ? card.reason : null;
      if (why) {
        setChildText(cell, '[data-me2-cand-unknown]', why);
        cell.setAttribute('data-me2-cand-why', 'true');
      } else if (cell.getAttribute('data-me2-cand-why') === 'true') {
        setChildText(cell, '[data-me2-cand-unknown]', UNKNOWN);
        cell.removeAttribute('data-me2-cand-why');
      }
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
    renderCandidateReason(vm);
    logCandidateTable(vm);
  }

  /**
   * WHY NOTHING WON, BESIDE THE EIGHT, IN THE SERVER'S OWN WORDS.
   *
   * 🔴 THE SCREEN HAD THIS ANSWER AND SHOWED THE NUMBERS INSTEAD. The operator was reading the
   *    reason out of the console, lowered the ranking thresholds to 1, and still got no winner --
   *    because `no_cells_scored` / `no_candidate_scored` / `no_overlap` / `no_discrimination` /
   *    `tie` are decided AHEAD of the threshold check and none of them is a knob. Eight rows of
   *    numbers cannot tell those five apart; the sentence can, and it was already on the wire.
   *
   * VERBATIM, AND NOTHING JOINED TO IT. Every other slot on this screen joins a label to a count
   * with a separator; this one does not, because the whole point is that the sentence is the
   * SERVER'S and a word of ours beside it would be a second spelling. Empty when the server said
   * nothing -- the slot then hides rather than showing a label we invented.
   */
  function renderCandidateReason(vm) {
    for (const host of queryAll(doc, '[data-me2-candidates-for]')) {
      if (host.hidden === true) continue;
      const slot = ensureReasonSlot(host);
      if (!slot) continue;
      slot.textContent = vm.reasonLine || '';
      slot.hidden = !vm.reasonLine;
    }
  }

  /**
   * The page has not authored this slot yet, so it is created inside the container the page DID
   * provide -- the same rescue `fillGrid` performs for the eight controls, and the same rule: no
   * new container, no new panel, nothing outside markup that already exists. When the markup
   * lane authors `[data-me2-cand-reason]` this finds it and stops creating one.
   *
   * ASKED FOR BY NAME (markup lane): `<p class="me2-cand-reason" data-me2-cand-reason hidden>` as
   * the FIRST child of `.me2-cands`, above the legend -- it explains the eight, so it reads
   * before them.
   */
  function ensureReasonSlot(host) {
    if (!host || typeof host.querySelector !== 'function') return null;
    const found = host.querySelector('[data-me2-cand-reason]');
    if (found) return found;
    const slot = doc.createElement('p');
    slot.className = 'me2-cand-reason';
    slot.setAttribute('data-me2-cand-reason', '');
    slot.hidden = true;
    // Above the eight where the real DOM allows it; the stub document has no `insertBefore`, and
    // a tolerant binding is the rule on this page -- a missing capability degrades, never throws.
    if (typeof host.insertBefore === 'function' && host.firstChild) {
      host.insertBefore(slot, host.firstChild);
    } else {
      host.appendChild(slot);
    }
    return slot;
  }

  /**
   * THE EIGHT PICTURES, PAINTED. This function owns only the DOM half: find a slot per candidate,
   * make one if the page has not authored it, resolve the palette from CSS tokens, and hand a
   * SURFACE to `paintCandidateThumbs`. It computes no seat and decides no colour.
   *
   * 🔴 IT IS CALLED LAST AND IT IS GUARDED, AND BOTH HALVES ARE DELIBERATE. A throw inside a
   *    candidate renderer takes down everything rendered after it in the same pass -- one
   *    unimplemented DOM call reads as a dozen unrelated failures somewhere else entirely, which
   *    is a debugging trap this screen has already paid for. So nothing depends on this running,
   *    and a failure says so out loud in the console instead of silently emptying the panel.
   */
  function renderCandidateThumbs(vm) {
    const payload = session.payload;
    if (!payload) return null;
    // Only when there is something seated to look at. The skeleton and idle states have no
    // cells, and a blank 128px box eight times is worse than no box at all.
    if (vm.picture !== 'compare' && vm.picture !== 'alone') return null;
    const source = pickSource(payload, session.focusedSourceId);
    const byId = new Map();
    for (const cell of queryAll(doc, '[data-me2-candidate]')) {
      // A hidden grid belongs to a source that is not being drawn. Painting into it would cost a
      // full seating per candidate for a picture nobody can see.
      const host = typeof cell.closest === 'function'
        ? cell.closest('[data-me2-candidates-for]') : null;
      if (host && host.hidden === true) continue;
      const code = cell.getAttribute('data-frame-code');
      if (!code || byId.has(code)) continue;
      const slot = ensureThumbSlot(cell);
      if (slot) byId.set(code, slot);
    }
    if (byId.size === 0) return null;
    const palette = thumbPalette();
    return paintCandidateThumbs((id) => {
      const node = byId.get(id);
      const ctx = node && typeof node.getContext === 'function' ? node.getContext('2d') : null;
      return ctx ? createCanvasSurface(ctx) : null;
    }, payload, source, THUMB, palette);
  }

  /**
   * One picture slot inside a candidate control the page provided. Created when absent, exactly
   * as `fillGrid` creates the control's score slot -- and found rather than recreated once the
   * markup lane authors it.
   *
   * ASKED FOR BY NAME (markup lane): `<canvas class="me2-cand-thumb" data-me2-cand-thumb
   * width="128" height="128" aria-hidden="true">` as the first child of each `.me2-cand`.
   */
  function ensureThumbSlot(cell) {
    if (!cell || typeof cell.querySelector !== 'function') return null;
    const found = cell.querySelector('[data-me2-cand-thumb]');
    if (found) return found;
    const node = doc.createElement('canvas');
    node.className = 'me2-cand-thumb';
    node.setAttribute('data-me2-cand-thumb', '');
    // The picture carries no information a screen reader can use -- the stored spelling and the
    // counts beside it carry all of it -- so it is not announced twice.
    node.setAttribute('aria-hidden', 'true');
    node.width = THUMB.width;
    node.height = THUMB.height;
    cell.appendChild(node);
    return node;
  }

  /**
   * The semantic colours, resolved HERE from the stylesheet's own tokens.
   *
   * 🔴 THE PAINTER HAS NO `getComputedStyle` AND MUST NOT GROW ONE. Resolving tokens is a
   *    composition-root job by construction -- it is what keeps `painter.js` importable by a
   *    harness with no DOM. The fallbacks exist for exactly that case (a document stub answers
   *    every token with an empty string) and never as a second palette: on a real page every one
   *    of these resolves, because the same tokens already colour the main stage's `.me2-cell-*`
   *    classes.
   */
  function thumbPalette() {
    const view = doc.defaultView;
    const root = doc.documentElement;
    const token = (name, dflt) => {
      if (!view || typeof view.getComputedStyle !== 'function' || !root) return dflt;
      try {
        const v = view.getComputedStyle(root).getPropertyValue(name);
        return (v && String(v).trim()) || dflt;
      } catch (e) {
        return dflt;
      }
    };
    // 🔴 NOT `--canvas-inside-empty`, WHICH IS WHAT THE MAIN STAGE'S FLOOR USES. MEASURED on the
    //    live page: that token is `rgba(23, 114, 69, 0.06)` -- a 6% wash tuned for the legacy
    //    canvas, and the stylesheet already carries a note that over `--bg-inset` the footprint
    //    "all but disappeared". The stage recovers it with a per-cell STROKE; at 96px a stroke
    //    would be thicker than the die it outlines, so the recovery has to be in the fill. The
    //    same reasoning is why `agree` is a step darker rather than equal to the floor: at this
    //    size the operator is reading WHERE THE SOURCE LANDED, and a source that agrees
    //    everywhere would otherwise be indistinguishable from bare reference.
    return Object.freeze({
      floor: token('--canvas-line-strong', 'rgba(31, 39, 51, 0.16)'),
      // Agreement is the quiet ground; the mismatch is the figure and is drawn last.
      agree: token('--text-dim', '#5b6779'),
      gap: token('--orange', '#c05621'),
      mismatch: token('--accent', '#1a66d0'),
      unrelated: token('--text-dim', '#5b6779'),
      skeleton: token('--border', '#d7dce4'),
    });
  }

  // 🔴 THE WHOLE TABLE, WHOLE. The screen has one line per cell and a legend; the console is
  //    where the operator has been reading the real numbers all day, so it gets every candidate
  //    the server scored with both counts, in the same declaration order, winner or not. Logged
  //    once per distinct table -- a render loop that re-logs an unchanged table buries it.
  //
  // 🔴 AND THE ONES THAT WERE NOT SCORED ARE IN IT TOO. This used to `filter` them out, so a run
  //    where the side declaration excluded four frames logged four rows and the console record
  //    silently agreed with the screen's wrong picture -- narrowing the search narrowed the
  //    report, which is the whole defect this round is about. A frame with no numbers is logged
  //    with the server's own word for why, and the count in the line is the count of FRAMES.
  let lastCandLog = null;
  function logCandidateTable(vm) {
    // Silence while there is nothing to say. The eight cards exist before any payload does, so
    // without this the console fills with eight `미상` rows on every idle repaint -- the early
    // return this replaces got that right for a different reason and it must keep being right.
    const known = vm.candidates.some(c =>
      (c.agree !== null && c.discriminating !== null) || !!c.state || !!c.reason);
    if (!known) return;
    const rows = vm.candidates.map(c => (c.agree !== null && c.discriminating !== null)
      ? `${c.id} ${c.agree}/${c.discriminating}`
      : `${c.id} ${c.reason || c.state || UNKNOWN}`);
    const axis = vm.rulingMetric ? ` · ${vm.rulingMetric}` : '';
    const line = `[map2] 후보 ${rows.length} · 일치/판별${axis} · 순위 아님 · ${rows.join(' | ')}`;
    if (line === lastCandLog) return;
    lastCandLog = line;
    if (doc.defaultView && doc.defaultView.console) doc.defaultView.console.log(line);
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
        // The score slot, in the three-sibling shape the authored grid already uses. A rescue
        // grid built without it can never show a number no matter what the payload carries --
        // `setChildText` writes into a hook that is not there and returns silently.
        const score = span(doc, 'me2-cand-score', '');
        const num = span(doc, 'me2-num', '');
        const agree = span(doc, '', '');
        agree.setAttribute('data-me2-cand-agree', '');
        const disc = span(doc, '', '');
        disc.setAttribute('data-me2-cand-discriminating', '');
        num.appendChild(agree);
        num.appendChild(span(doc, '', ' / '));
        num.appendChild(disc);
        score.appendChild(num);
        // The `미상` sibling, WITH A HOOK. It is the slot that also carries the server's reason
        // when a frame was never considered, and a class name is not addressable from the
        // wiring's own vocabulary -- every other value slot on this page is reached through a
        // `data-me2-*` attribute, and reaching for one by class here would be the one exception
        // that a stub document (and therefore a harness) cannot see.
        const unknown = span(doc, 'me2-unknown', UNKNOWN);
        unknown.setAttribute('data-me2-cand-unknown', '');
        score.appendChild(unknown);
        cell.appendChild(score);
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
    // 🔴 THE REFUSAL TAKES THIS SLOT WHILE IT IS LIVE, AND IT IS THE SAME SLOT ON PURPOSE.
    //    `note` describes the BASIS of a write that has not happened; a refusal describes why
    //    it did not happen. Both are about the one act, only one can be the current truth, and
    //    a screen showing "현재 선언 동일" beside a write the server just rejected is the screen
    //    contradicting itself. The note returns as soon as anything changes, because every
    //    state change clears `confirmError`.
    //
    //    THIS SLOT AND NOT THE HINT: the refusals are full sentences (「결정 단위가 덜
    //    채워졌습니다 - ... 빠진 결정키: ...」), and the hint is a small span sharing a flex row
    //    with the button. `#me2-confirm-note` is the wide line in the text column and already
    //    carries a sentence-shaped value. NOT a toast either -- a transient the operator can
    //    miss puts the failure back where it was, invisible.
    const failure = vm.confirm.failure;
    text(el.confirmNote, failure || vm.confirm.note || '');
    // One attribute for the CSS lane, no new element. Asked for by name:
    // `#me2-confirmbar[data-me2-confirm-state="failed"]` should read as a refusal, not as a note.
    if (el.confirmBar) {
      if (failure) el.confirmBar.setAttribute('data-me2-confirm-state', 'failed');
      else el.confirmBar.removeAttribute('data-me2-confirm-state');
    }
    // Three states, one slot, no sentences. Inert says WHY it is inert (Enter must never be
    // silently dead); live names the key; landed says so.
    //
    // 🔴 `확정됨` IS THE ONLY THING THAT TELLS THE OPERATOR THE WRITE WORKED, AND IT EXISTS
    //    BECAUSE THE ARMING WAS REMOVED. Under the two-step, the label flipping back from
    //    `다시 Enter로 확정` to `확정` was an incidental acknowledgement -- the only pixel on
    //    the screen that changed when a confirmation landed. Deleting the arming deletes that,
    //    and a write button that answers a press with nothing at all is the same defect class
    //    this screen keeps paying for: the system knows something and the screen does not say
    //    it. It is a word in a slot that already existed, not a new control.
    // 🔴 THE ACKNOWLEDGEMENT LEADS, and the order is a decision rather than an accident.
    //    `inertHint` is computed unconditionally, so it is often non-null even while the
    //    control is live -- putting it first meant `확정됨` could never appear on exactly the
    //    screens that have a nominal hint. A write that just landed outranks a standing note
    //    about why the control is nominal; the note returns the moment anything changes,
    //    because every state change clears `confirmed`.
    text(el.confirmHint, vm.confirm.confirmed ? '확정됨'
      : (vm.confirm.inertHint || 'Enter 확정'));
    const btn = el.confirmBtn;
    if (!btn) return;
    // 🔴 DISABLED WHILE THE REQUEST IS IN FLIGHT. One of the three overlapping guards against
    //    a double confirmation (see the `preventDefault` note in the keydown handler for why
    //    they are counted as three and scored one by one). This is the only one the OPERATOR
    //    can see, and it is the one that answers "did my press register" while the POST runs.
    btn.disabled = !vm.confirm.enabled || confirmInFlight;
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
  /** The served exclusion tally, in the server's own order. Empty when nothing was excluded. */
  function excludedRows() {
    const rows = session.payload && session.payload.excluded_reasons;
    return Array.isArray(rows) ? rows : [];
  }

  function logDiagnosis(vm) {
    const view = doc.defaultView;
    if (!view || !view.console) return;
    const q = vm.question;
    const lines = [];
    // 🔴 THE SCREEN NOW TRUNCATES, SO THIS IS NOT A CONVENIENCE. The frame made the refusal,
    //    the caption and the inline meta one-line with ellipsis, and deleted the cause node
    //    outright. Anything not logged here whole is not moved to the console, it is DESTROYED.
    if (vm.cause && vm.cause.detail) lines.push(vm.cause.detail);
    // 🔴 THE WHOLE TALLY, AND IT IS WIDER THAN THE LINE ON SCREEN. The refusal slot shows the
    //    sentence and each reason's measurement; WHICH map was the example, and how many maps
    //    each reason took, do not fit beside them and are exactly what answers "what was wrong
    //    with this unit" months later. Every field here is the server's -- `reason` is its
    //    label, `detail` its measurement -- so an exclusion reason this client has never heard
    //    of still logs completely.
    for (const row of excludedRows()) {
      lines.push(['제외', row.reason || row.reasonCode || '(no reason)',
                  row.count === null ? '미상' : `${row.count}개`,
                  row.exampleMapId ? `예: ${row.exampleMapId}` : '',
                  row.detail || ''].filter(Boolean).join(' · '));
    }
    // 🔴 THE SERVER'S SENTENCE SURVIVES A SCORED STATE. On a tie `/view` sends both a
    //    `no_winner` state and a refusal sentence, so it goes here whole rather than being
    //    dropped. The guard is what keeps ONE copy: since the cause now carries that same
    //    sentence in the no-winner state too (it used to substitute `대칭 기준` for it), the
    //    unguarded spelling would print the server's words twice in a row.
    const servedRefusal = session.payload && session.payload.refusal_detail
      ? String(session.payload.refusal_detail) : '';
    if (servedRefusal && !(vm.cause && vm.cause.detail === servedRefusal)) lines.push(servedRefusal);
    // 🔴 THE BRANCH, NAMED. Five refusals are decided ahead of the two thresholds, and from the
    //    screen they are indistinguishable -- which is how an afternoon went into lowering a
    //    threshold that was never consulted. The sentence is beside the eight; this says which
    //    check produced it. And when there is no winner and no sentence at all, that silence is
    //    itself the finding: it is a gap on the wire, not a state this screen can repair.
    if (vm.reasonCode) lines.push(`ruling.reason_code=${vm.reasonCode}`);
    else if (!vm.reasonLine && (vm.state === VIEW_STATE.SCORED_NO_WINNER
                                || vm.state === VIEW_STATE.NOT_SCORABLE)) {
      lines.push('no winner and the payload carried neither `refusal` nor `ruling.reason_code`; '
        + 'the reason is not on the wire, so this screen cannot say which check refused.');
    }
    // 🔴 THE CODE ALONE DOES NOT SAY WHICH REPAIR. `no_discrimination` on the occupancy axis is
    //    a symmetric footprint; on `values_weighted` it means the values themselves are
    //    identical across all eight AND that raising a weight will not break the tie. The
    //    server's sentence already draws that line -- this puts the axis beside the code so the
    //    record says which of the two sentences the reader is looking at, without this side
    //    growing a Korean word per axis.
    //
    // 🔴 AFTER THE CHAIN ABOVE, NOT INSIDE IT. Spelled between the `if` and its `else if` this
    //    silently re-pointed the "the reason is not on the wire" finding at `rulingMetric`, so
    //    a payload carrying a metric and NO reason at all stopped reporting the gap. Caught in
    //    review of this round's own diff; `N15` below is what would have caught it.
    if (vm.rulingMetric) lines.push(`ruling.metric=${vm.rulingMetric}`);
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
    // 🔴 ONE LINE ON SCREEN, THE WHOLE RECORD HERE -- and for this one the record is the point.
    //    The screen carries the server's sentence and a per-row marker; WHICH map ids borrowed,
    //    from where, and whether this client asked for it are the facts that answer "what did
    //    this verdict stand on" months later, and none of them fit on a line. Logged in both
    //    states: an untaken offer is what the operator is being asked to decide about.
    const asm = session.payload && session.payload.assumption ? session.payload.assumption : null;
    if (asm && asm.state !== 'unavailable') {
      lines.push(`geometry assumption ${asm.state}: `
        + `${asm.mapCount === null ? '미상' : asm.mapCount} map(s) `
        + `[${asm.mapIds.join(', ') || 'none listed'}] borrow the wafer dimensions of `
        + `${asm.basis ? `${asm.basis.table}:${asm.basis.mapId}` : '(no basis)'}. `
        + 'Borrowed dimensions are never stored on the source meta; the ruling carries '
        + 'geometry_assumed and each map carries geometry vs geometry_basis.');
    }
    // 🔴 THE THIRD STATE, WHICH THE SCREEN CANNOT SHOW AND THE RECORD MUST NOT LOSE.
    //    `provisional` has three answers -- ranked on substituted thresholds / ranked on
    //    declared ones / this server does not carry the field. The first gets a sentence and a
    //    caution; the other two both render as nothing, because a caveat we cannot support is
    //    a claim and silence is not. But `unknown` and `declared` are NOT the same fact, and
    //    the difference is exactly what a stale deployment looks like -- so it is written here,
    //    where a code is a thing to grep rather than a thing to read. Without this line the
    //    distinction exists only inside the view model and nothing can observe it.
    if (!vm.provisional.known) {
      lines.push('ruling carries no thresholds_defaulted field: this server predates the '
        + 'provisional-ranking marker, so "ranked on declared thresholds" is UNVERIFIED here '
        + 'rather than true. Do not read the absent caveat as a declared one.');
    } else if (vm.provisional.active) {
      lines.push(`ruling is provisional: [${vm.provisional.axes.join(', ')}] were undeclared and `
        + 'the server substituted its development default of 1. The default does not change '
        + 'WHICH candidate wins -- only whether anyone may say so. NOT carried into '
        + 'frame_confirmation: that row stores ruling_state/reason/winner/margin/discriminating '
        + 'and nothing else, so this caveat ends at the write.');
    }
    // A token the two sides do not both know reached the wire. Named loudly: every server test
    // stays green through this, and the only symptom on screen is a row sorted into the wrong
    // bucket. This is the seam `declaration.js` grew `assumed` to keep honest.
    const rejects = (session.payload && session.payload.__decoded
      && session.payload.__decoded.rejected) || [];
    if (rejects.length > 0) lines.push(`payload fields refused: ${rejects.join('; ')}`);
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
    if (!payload) return null;
    // 🔴 NO EARLY RETURN AHEAD OF THE FLOOR. This read `if (!source) return null` before the
    //    floor was ever computed, so a resolved reference with nothing seated on it drew an
    //    empty stage -- a picture that says "there are no dies here" about a reference that
    //    served 425 of them. The floor is drawn because it RESOLVED, not because something
    //    else also arrived.
    const source = pickSource(payload, session.focusedSourceId);

    const candidateId = vm.selectedCandidateId || (source && source.stored_candidate_id);
    // ONE spelling of the frame, shared with the eight small pictures. Two constructions of the
    // same record is how the stage and the thumbnails start disagreeing about what candidate 3
    // means -- and the disagreement would look like a rendering quirk, not like a bug.
    const { frame, floorFrame } = framesFor(payload, candidateId);
    // 🔴 THE PLACEMENT THE SERVER SCORED WITH, APPLIED TO THE PICTURE. Without it the
    //    overlay is drawn at (0,0) whatever the server placed it at -- and the counts beside
    //    it are the counts for a position the operator is not looking at. Read off the CARD for
    //    the candidate actually being drawn, never off the ruling: the ruling's shift belongs
    //    to the winner, and the operator may be looking through any of the eight.
    //
    // ⚠️ THE FLOOR IS NOT SHIFTED. The offset means "move the SOURCE onto the reference";
    //    applying it to both would translate the whole stage and change nothing, and applying
    //    it to the floor alone would move the thing the source is being measured against.
    const shift = (vm.candidates.find(c => c.id === candidateId) || {}).shift || null;
    const floor = computeSeating(payload.floor_cells || [], floorFrame);
    const seated = source ? computeSeating(source.cells || [], frame, shift) : null;

    if (vm.picture === 'alone') {
      // 🔴 THE FLOOR STILL DRAWS HERE, INTO THE LAYER THIS STATE ACTUALLY SHOWS. The stylesheet
      //    displays only `#me2-layer-alone` while the workbench reads `unscorable`
      //    (`map_editor2.css`), so putting the floor in `#me2-layer-floor` would be drawing it
      //    into a hidden `<g>`. Its whole purpose is to be looked at: whether the reference
      //    resolved is a fact about the data, and no verdict may switch it off. Floor first so
      //    the source reads as the figure on top of it, which is the same order the comparison
      //    picture uses.
      const layout = layoutFor(unionBounds(floor.bounds, seated ? seated.bounds : null), STAGE);
      let drawnAlone = drawSeats(el.layerAlone, floor.seats, layout, 'me2-cell-floor');
      if (seated) drawnAlone += drawSeats(el.layerAlone, seated.seats, layout, 'me2-cell-alone');
      return { pxPerDie: layout.cell, drawn: drawnAlone };
    }

    if (!seated) {
      // A floor with nothing seated on it is still the thing the operator asked to look at.
      const layout = layoutFor(floor.bounds, STAGE);
      const drawnFloor = drawSeats(el.layerFloor, floor.seats, layout, 'me2-cell-floor');
      return { pxPerDie: layout.cell, drawn: drawnFloor };
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
    // 🔴 ONE ACTION CONFIRMS (product owner, 2026-08-06): 「그냥 엔터든 클릭이든 확정 누르면
    //    바로 되게해」. The arm-then-commit step is gone -- a click writes, Enter writes.
    //
    // 🔴 AND THE IN-FLIGHT GUARD IS NOT OPTIONAL NOW. Under the two-step, a doubled invocation
    //    landed on the arming branch and cost nothing; with one action it is a SECOND POST.
    //    The guard is a closure flag rather than session state on purpose: it is a fact about
    //    one request, not about the unit, and putting it in the session would make it survive
    //    a row change and wedge the button. It is cleared on BOTH settle paths below --
    //    a guard with one exit is a guard that eventually latches on.
    if (confirmInFlight) return;
    confirmInFlight = true;
    // 🔴 REPAINT IMMEDIATELY, OR THE GUARD IS INVISIBLE. Setting the flag disables the control
    //    on the NEXT render, and the next render is the one after the response -- so without
    //    this line the button stays live and clickable for the whole duration of the write.
    //    The flag would still refuse the second POST, but the screen would show a control that
    //    accepts presses and does nothing, which is the complaint this round started from.
    //    Caught by `G26c`, not by any end-state assertion.
    render();
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
        // 🔴 `shift_dx: 0, shift_dy: 0` STOOD HERE AND WERE DELETED (2026-08-06). They posted the
        //    PLACEMENT AS A CONSTANT: a unit the aligner placed at (4,5) was sent -- and for a
        //    while persisted and displayed -- as (0,0). The server no longer reads these fields,
        //    so the record is correct without them; they are removed because a constant in a
        //    request body that nobody reads is the next person's trap, and this one has already
        //    cost a day. If a shift ever belongs in this record it is `per_candidate[<frame>]
        //    .shift`, which is the placement the scoring actually used -- never a literal.
        //
        // ⚠️ WHY NOBODY CAUGHT IT: the old shift search broke ties toward the origin, so on a
        //    saturated partial map it returned (0,0) and the hardcoded zero agreed with the
        //    scorer BY ACCIDENT. The anchor made placements real and every stale copy of the
        //    assumption surfaced at once -- including the overlay, which applied no offset at all.
        agreement: null,
        discriminating: null,
        excluded_reason: null,
      })),
      ruling: (payload.__decoded && payload.__decoded.ruling) || null,
      // 🔴 `state` IS COPIED SEPARATELY BECAUSE `/view` PUTS IT AT THE TOP LEVEL, NOT INSIDE
      //    `ruling`. The confirm route's docstring states the rule in two lines for exactly
      //    this reason, and obeying only the first line loses it: a `no_winner` unit that the
      //    operator resolved by hand recorded `STATE_NOT_TRANSPORTED`, which erases the one
      //    fact that record exists to hold -- that a human settled what the machine would not.
      state: (payload.__decoded && payload.__decoded.state) || null,
      reference: referenceOf(q.reference),
      confirmedBy: context.confirmedBy,
    })).then(() => { confirmInFlight = false; setSession(withConfirmed(session)); })
      // 🔴 THE FAILURE PATH SAYS WHAT HAPPENED. It used to be `.catch(() => { ...; render(); })`
      //    -- ten distinct server refusals, every one discarded, and the operator saw the button
      //    become clickable again and nothing else. That is 「결과를 숨기지 않는다」 broken on the
      //    one control that writes durable provenance, and removing the arming step made it
      //    worse rather than better: a failed confirm used to leave the operator mid-gesture,
      //    which was at least a signal.
      //
      //    The sentence is the SERVER'S, lifted from the envelope by `api.serverMessage` and
      //    not re-worded here. `err.message` is the fallback ONLY when the server said nothing
      //    at all -- a transport failure has no refusal to quote, and inventing a Korean
      //    sentence for it would be exactly the classification this must not do.
      .catch((err) => {
        confirmInFlight = false;
        const said = err && err.serverMessage ? err.serverMessage : null;
        setSession(withConfirmFailed(session, said || (err && err.message) || ''));
      });
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
  bindSelect(el.ruleSelect, v => { if (onRulePick) onRulePick(v); });
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
  // 🔴 THERE IS NO ACCEPT CONTROL, AND ITS ABSENCE IS THE ENFORCEMENT. Borrowing the
  //    floor's wafer dimensions is automatic now (product owner 2026-08-06); the server applies
  //    it by default and this client never sends the parameter, so the `available` state that
  //    used to put a button here cannot occur. The handler that stood at this spot was the
  //    entire write side of the feature and it is gone with it.
  //
  // ⚠️ WHAT DID NOT GO: every disclosure. The server's offer sentence still reaches
  //    `#me2-question-note`, `data-me2-assumed` still marks the workbench, the note still turns
  //    `caution` once numbers rest on the borrowing, and the write still discloses it through
  //    `WORDS.geometryAssumed`. Removing consent is not removing notice -- if a later round
  //    finds one of those missing, this comment is the record that it was not meant to go.
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
    // Enter confirms. Arrow keys stay with the worklist -- existing muscle memory.
    //
    // 🔴 THE ESCAPE BRANCH IS GONE BECAUSE THERE IS NOTHING LEFT TO CANCEL. It disarmed the
    //    intermediate state; with one-action confirm there is no intermediate state, and a key
    //    that silently does nothing is worse than a key that is not mentioned -- the operator
    //    presses it, nothing happens, and they learn the screen ignores them. The copy that
    //    advertised it is removed with it (`map_editor2.html`, `renderConfirm`).
    //
    // 🔴 THIS HANDLER HAD NO TARGET GUARD, AND IT MADE THE ONE WRITE IN THE CHAIN REACHABLE BY
    //    A KEYSTROKE INSIDE A DROPDOWN. Enter in any of the five set-up selects bubbled to the
    //    document, armed on the first press and committed on the second -- while the operator
    //    believed they were choosing a column. A confirmation that a wrong frame bakes an
    //    unverified rotation into stored coordinates, reachable by accident, is the failure
    //    the arm-then-commit design existed to prevent -- and `takesEnter` is what carries that
    //    protection now that the arming does not. IT IS LOAD-BEARING: removing the two-step
    //    made this guard the ONLY thing between a keystroke in a dropdown and a POST.
    //
    //    The guard is on WHAT KIND OF THING HAS FOCUS, not on one container's id. Keying it to
    //    `#me2-question-bar` would protect exactly today's markup and silently stop protecting
    //    anything the day a control is added outside that div -- and the next control to be
    //    added is the one nobody remembers to re-check. Enter belongs to a focused control
    //    whenever there is one; only the confirm button itself may turn it into this write.
    if (e.key === 'Enter' && el.confirmBtn && !el.confirmBtn.disabled && !takesEnter(e.target)) {
      // 🔴 `preventDefault` IS THE WHOLE FIX FOR THE DOUBLE POST, AND IT IS EASY TO READ AS
      //    DECORATION. A focused <button> activated by Enter ALSO fires a native `click`, and
      //    `el.confirmBtn.addEventListener('click', onConfirm)` is right there -- so without
      //    this line one keystroke calls `onConfirm` twice. Under the old two-step the second
      //    call landed on the arming branch and cost nothing, which is why it was survivable
      //    and therefore invisible; with one action it is a SECOND CONFIRMATION WRITE from a
      //    single press. Cancelling the default activation is what stops the pair at source.
      //
      // ⚠️ AND THE HONEST VERSION, MEASURED RATHER THAN ASSUMED. There are THREE overlapping
      //    guards here, not two, and they are NOT independent: this `preventDefault`, the
      //    `confirmInFlight` flag, and the disable-on-repaint in `renderConfirm`. Deleting
      //    this line alone leaves the write count at 1, because either of the other two
      //    swallows the native click on its own (mutation-measured 2026-08-06). So a "one
      //    write" assertion scores the STACK and would keep passing while two thirds of it
      //    rotted. Each guard is therefore scored by its own assertion --
      //    `map_editor2_shell_harness` G26 (this cancellation), G26b (the flag), G26c (the
      //    repaint) -- and this line is kept because the other two only swallow the second
      //    call AFTER `onConfirm` has already run and already incremented `bar.actions`.
      e.preventDefault();
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
    /**
     * A one-line reason, shown in the set-up row. The WHOLE failure goes to the console; this
     * is the single line that tells an operator the screen is not merely empty.
     */
    setNotice(msg) { notice = msg == null ? '' : String(msg); render(); },
    /**
     * The alignment-capable rules on offer, and whether the current one is a PROPOSAL.
     * `options` are `{value,label,selected}` records; this file chooses no label and ranks
     * nothing -- the order it is handed is the order the server declared.
     */
    setRules(model, onPick) {
      // `options: null` means "keep the offer, change only the marking" -- picking by hand
      // clears the proposal without rebuilding the list under an open dropdown.
      ruleModel = {
        options: (model && model.options) || ruleModel.options,
        proposed: !!(model && model.proposed),
      };
      if (typeof onPick === 'function') onRulePick = onPick;
      render();
    },
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
          stored_candidate_id: s.declaredFrameSource === DECLARED ? s.declaredFrame : null,
          // 🔴 THE CONFIRMED FRAME, CARRIED SEPARATELY FROM THE DECLARED ONE. `declared_frame`
          //    arrives populated on a confirmed map -- `declared_frame_of` composes it from
          //    `orientation_declaration`, which answers `confirmed` on rotation and side once
          //    the confirm write lands `frame_confirmed_from` -- so the frame string is real
          //    and only its PROVENANCE differs. Folding it into `stored_candidate_id` would
          //    move the drawing; dropping it leaves the row saying `고르지 않음` about a frame
          //    a human confirmed. So: its own field, read only by the label.
          confirmed_candidate_id:
            s.declaredFrameSource === CONFIRMED ? s.declaredFrame : null,
          // 🔴 WHAT THIS MAP SAYS ABOUT ITS OWN GEOMETRY, AND WHAT THIS RUN ACTUALLY STOOD ON.
          //    Two fields because they can disagree, and the disagreement IS the fact: a map
          //    whose own geometry is `absent` but whose basis is `assumed` was scored on the
          //    floor's wafer. Carried per row so the operator can see WHICH maps borrowed,
          //    rather than only that some did.
          geometry: s.geometry,
          geometry_basis: s.geometryBasis,
          cells: i === 0 ? srcCells : [],
        }))
      : (srcCells.length > 0 ? [{ id: 'source', label: '출처', stored_candidate_id: null,
                                  confirmed_candidate_id: null,
                                  geometry: null, geometry_basis: null, cells: srcCells }] : []),
    floor_cells: refCells,
    per_candidate: decoded.scorings,
    occupancy_winner_id: null,
    map_count: decoded.counts.mapCount,
    excluded_map_count: decoded.counts.excludedMapCount,
    discriminating_dies: decoded.counts.discriminatingDies,
    elapsed_ms: decoded.counts.elapsedMs,
    refusal_detail: decoded.refusalDetail,
    // 🔴 WHICH BRANCH REFUSED, NOT JUST THAT ONE DID. `no_cells_scored`, `no_candidate_scored`,
    //    `no_overlap`, `no_discrimination` and `tie` are all decided AHEAD of the two threshold
    //    checks, so lowering `min_margin_dies` moves none of them -- which is exactly the dead
    //    end the operator spent an afternoon in. The SENTENCE goes on screen; this code goes to
    //    the console beside it, because a code is a thing to grep, not a thing to read.
    ruling_reason_code: (decoded.ruling && decoded.ruling.reason_code) || null,
    // 🔴 WHICH AXIS PRODUCED THE RANKING -- `occupancy` | `values` | `values_weighted`. CARRIED,
    //    NEVER TRANSLATED. The same reason code means different repairs on different axes, and
    //    the server ALREADY says so in its own sentence: `_RULING_TEXT_BY_METRIC` sends
    //    `기준 발자국 대칭 …` on occupancy and `기준 값이 8프레임에 동일 - 가중으로도 구별 불가 …`
    //    on the weighted one. So this side needs the TOKEN, for the record, and must not grow a
    //    Korean word per axis -- that would be a second spelling of a distinction the server has
    //    already drawn, on a field that gained a third value this week and can gain a fourth.
    ruling_metric: decoded.rulingMetric,
    // 🔴 THE PAIR THE SERVER ACTUALLY RANKED AGAINST, so this side scores the same evidence
    //    against the same bar. Per axis (`map_alignment.py:1194`), null when the ruling did not
    //    carry both -- see `decode.decodeThresholds`, and `currentVerdict` for why it leads.
    ruling_thresholds: decoded.rulingThresholds,
    // 🔴 THE RANKING'S OWN CAVEAT ABOUT ITSELF, AND WITHOUT THESE TWO LINES IT DOES NOT EXIST.
    //    The server now RANKS when the thresholds are undeclared instead of refusing (product
    //    owner: the feature runs before the guards go on), substituting 1/1 and saying so on
    //    the ruling. `decode` already carries the whole `ruling` through -- but this literal is
    //    hand-written, and a field not named here is a field that does not exist downstream.
    //    So the client's own verdict layer reproduced the same winner from `ruling.min_*`
    //    (which are now non-null) and drew a confident badge, while the one fact that says the
    //    bar was invented never left the payload. That is precisely the impersonation the
    //    no-default design existed to stop, relocated one layer up: the server stopped claiming
    //    more than it knows and the client started.
    //
    // ⚠️ ABSENT IS NOT EMPTY. `[]` means the server checked and the thresholds WERE declared;
    //    `null` means this server does not carry the field at all. Defaulting an absent field
    //    to `[]` would make a stale server read as "declared", which is the same collapse the
    //    server's own comment refuses when it insists on sending the list even when empty.
    ruling_thresholds_defaulted: Array.isArray(decoded.ruling && decoded.ruling.thresholds_defaulted)
      ? Object.freeze(decoded.ruling.thresholds_defaulted.map(String)) : null,
    // The SERVER'S sentence, verbatim. `null` when the ranking stood on declared thresholds --
    // it composes this because on a scored run `compose_refusal` returns nothing at all, so the
    // slot the screen would otherwise use is empty exactly when the caveat is needed.
    ruling_provisional_text: (decoded.ruling && decoded.ruling.provisional_text)
      ? String(decoded.ruling.provisional_text) : null,
    // 🔴 THE SENTENCE AND ITS MEASUREMENTS TRAVEL SEPARATELY, BECAUSE THE SERVER SENDS THEM
    //    SEPARATELY. `refusal_detail` is the composed sentence and it carries reason LABELS
    //    only; the numbers that say WHICH grid is wrong and BY HOW MUCH are in the tally's
    //    `example_detail`. Spelled `excluded_reasons` rather than `excluded` so it cannot be
    //    confused with the raw wire's own `excluded` block -- this is the adapted shape, with
    //    the decoder's names, and the raw one is still reachable through `__decoded`.
    excluded_reasons: decoded.excluded,
    // 🔴 WHICH COLUMN PAIR DID THE SERVER ACTUALLY READ. Null today: the route takes no column
    //    parameter and the `unit` block echoes none (`server/main.py:4160-4168`,
    //    `server/map_alignment.py:677`). Read here rather than assumed, so the day the server
    //    echoes it the screen starts attributing instead of refusing -- with no other change.
    answered_columns: answeredColumns(raw),
    // Declared on the wire (`reference.kind`), never inferred from the shape of the cells.
    // This is what tells "we had values" from "we only had occupancy", and those are two
    // different answers to "why could you not tell them apart".
    reference_kind: (raw && raw.reference && raw.reference.kind) || null,
    // The borrowed-geometry offer, decoded. `null` is impossible -- the decoder always returns
    // a record, whose `unavailable` state is the ordinary "there is nothing to offer here".
    assumption: decoded.assumption,
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

/**
 * The two frames one candidate is read under. PURE, and the ONLY place either is constructed.
 *
 * 🔴 THE FLOOR IS HELD STILL AND THE SOURCE TURNS ON TOP OF IT. Turning both together is the
 *    thing that cannot inform -- the same transform applied to both compared sets leaves their
 *    relation invariant, which is also why there is no rotate control anywhere on this screen.
 *    This version can produce a wrong-LOOKING picture, and that is precisely what makes it
 *    evidence rather than decoration.
 *
 * `candidateId` may be null or unparsable; the frame then reads `rot0_front`, which is the
 * identity and is what the floor uses anyway.
 */
export function framesFor(payload, candidateId) {
  const p = payload || {};
  const axes = parseCandidateId(candidateId) || { rotation: 0, side: 'front' };
  const dims = p.dims || { cols: gridSpan(p, 'x'), rows: gridSpan(p, 'y') };
  const frame = Object.freeze({
    rotation: axes.rotation, side: axes.side,
    cols: dims.cols, rows: dims.rows,
    startX: numOr(p.start_x, 0), startY: numOr(p.start_y, 0),
  });
  return Object.freeze({
    frame,
    floorFrame: Object.freeze({ ...frame, rotation: 0, side: 'front' }),
  });
}

/**
 * THE EIGHT PICTURES. One per candidate, all of them at once, each showing the source seated
 * under that frame against the same reference floor.
 *
 * 🔴 IT TAKES A `surfaceFor(id)` RATHER THAN A DOCUMENT, which is the whole reason this is
 *    scorable at all: the harness hands it `createRecordingSurface` and reads the ops back, with
 *    no canvas and no DOM anywhere in the path. Everything below is the pieces that already
 *    existed -- `computeSeating`, `compareSeatings`, and `paintComparison` (which calls
 *    `layoutFor` and `paintSeating` for us). There is no second painter in this file.
 *
 * 🔴 THE FLOOR IS SEATED ONCE, NOT EIGHT TIMES. It is the same seating for every candidate by
 *    construction -- `floorFrame` is `rot0_front` whatever the candidate is -- so recomputing it
 *    per thumbnail would be eight passes over the reference population for one answer. On a
 *    map with thousands of dies that is the difference between a repaint and a freeze.
 *
 * @param {(id:string)=>object|null} surfaceFor  a drawing surface per candidate id, or null to
 *        skip that one (a page that published fewer than eight slots still renders the rest).
 * @returns {Array<{id:string, stats:{painted:number,total:number,pxPerDie:number}}>}
 */
export function paintCandidateThumbs(surfaceFor, payload, source, viewport, palette) {
  const out = [];
  if (!payload || typeof surfaceFor !== 'function') return Object.freeze(out);
  const floor = computeSeating(payload.floor_cells || [], framesFor(payload, null).floorFrame);
  for (const c of candidateList()) {
    const surface = surfaceFor(c.id);
    if (!surface) continue;
    // Each thumbnail gets ITS OWN candidate's placement -- the eight are eight different
    // placements, and drawing them all at the winner's (or at none) is what made the small
    // pictures agree with each other and disagree with the stage.
    const cShift = shiftFor(payload, c.id);
    const seated = source
      ? computeSeating(source.cells || [], framesFor(payload, c.id).frame, cShift) : null;
    const comparison = seated ? compareSeatings(floor, seated) : null;
    out.push(Object.freeze({
      id: c.id,
      stats: paintComparison(surface, { floor, source: seated, comparison }, viewport, palette),
    }));
  }
  return Object.freeze(out);
}

/**
 * The placement `map_alignment` solved for ONE candidate, off the adapted payload.
 *
 * Kept beside `pickSource` rather than inlined at both call sites: the stage and the eight
 * thumbnails must read the same field the same way, and two spellings of "which shift belongs
 * to this frame" is how a stage and its thumbnails start disagreeing about candidate 3.
 */
function shiftFor(payload, candidateId) {
  const list = (payload && payload.per_candidate) || [];
  const row = list.find(c => c && c.candidate_id === candidateId) || null;
  return (row && row.shift) || null;
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

/**
 * The one line the operator reads about why there is no answer.
 *
 * 🔴 A SENTENCE JOINED TO ITS MEASUREMENTS BY A SEPARATOR, NEVER A CLAUSE. Every part is a
 *    string the SERVER composed -- the refusal sentence, and each excluded reason's own
 *    `example_detail` -- and this side contributes only the ` · ` between them, exactly as the
 *    set-up note already joins served parts. Without the second half the operator is told
 *    `격자 치수가 기준과 다름` and cannot see which grid is wrong or by how much, which is the
 *    entire content of that message; with it they read `소스 45x39 · 기준 44x39` beside it.
 */
function causeLine(cause) {
  if (!cause) return '';
  const measured = (cause.measurements || []).filter(Boolean);
  // the server's sentence, verbatim, plus the numbers it did not carry
  if (cause.detail) return [cause.detail].concat(measured).join(' · ');
  if (!cause.token) return '';
  const head = cause.count === null ? cause.token : `${cause.token} · 후보 ${cause.count}`;
  return [head].concat(measured).join(' · ');
}

export { VIEW_STATE, createApiClient, spellFrame };
