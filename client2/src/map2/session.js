// ═══════════════════════════════════════════════════════════════════════════════
// SESSION -- "current state", as a RECORD YOU MAKE AND PASS, not a module global.
//
// (MAP_ALIGNMENT_SPEC 0.2, the side table: "현재 상태 보관. 전역이 아니라 만들어 넘기는 통".)
//
// 🔴 WHY A FACTORY. `map_editor.js` holds its state in top-level `let`s, and the ceiling in
//    `check_harnesses.mjs` records that population as being at its maximum with no headroom.
//    The reason that number cannot come down by tidying is structural: a function that reads a
//    module global cannot be called with different state twice, so a test must SLICE it out of
//    the file and re-declare the globals around it -- which is why nearly every client harness
//    reads source text instead of importing it.
//
//    The dodge to avoid is `export const session = {}`. That is still one shared box; it just
//    stops being counted, because a counter that looks for `let` at top level does not look
//    inside a frozen-looking `const`. There is no such object in this file. `createMapSession`
//    returns a NEW record each call, and every transition returns a NEW record.
//
// IMMUTABLE TRANSITIONS. Each `with*` returns a frozen copy. The composition root holds the
// current record in a closure variable inside `bootstrap()`, so even the one mutable binding
// in the program is function-scoped, not module-scoped.
//
// NO DOM. NO TRANSPORT. NO COMPUTATION -- the session stores what was decided elsewhere.
// ═══════════════════════════════════════════════════════════════════════════════

/** Lifecycle of one (eqp, product) decision. `IDLE` is before anything is selected. */
export const PHASE = Object.freeze({
  IDLE: 'idle',
  COMPUTING: 'computing',
  READY: 'ready',
  FAILED: 'failed',
});

/**
 * @param {object} [init]
 * @param {object} [init.config]   thresholds and knobs, PASSED IN. Never read from a literal
 *                                 here: `min_margin_dies` / `min_discriminating_dies` are
 *                                 operator-tunable and belong to server config.
 */
export function createMapSession(init = {}) {
  return freezeSession({
    // The decision unit is (eqp, product) -- NOT one map. Wafers under one eqp+product were
    // measured disagreeing with each other, so the evidence has to be pooled before it is
    // scored. A per-map session would rebuild the reload loop this replaces.
    decision: init.decision || null,
    phase: init.phase || PHASE.IDLE,
    config: init.config || null,
    payload: init.payload || null,
    // Which of the eight the operator is LOOKING at. Selection is a repaint, never a fetch.
    selectedCandidateId: init.selectedCandidateId || null,
    // Which source row (or the cross-source row) the picture is answering for. A picture that
    // silently changes meaning is worse than no picture, so this drives the caption.
    focusedSourceId: init.focusedSourceId || null,
    // The one write gets exactly one confirmation, inline. Reading stays frictionless.
    armed: init.armed === true,
    error: init.error || null,
    requestSeq: Number.isFinite(init.requestSeq) ? init.requestSeq : 0,
  });
}

function freezeSession(s) {
  return Object.freeze(s);
}

function next(session, patch) {
  return freezeSession({ ...session, ...patch });
}

/**
 * Begin exploring one (eqp, product). Bumps `requestSeq` so a late response for a row the
 * operator already left can be dropped instead of painted over the current one -- the same
 * guard class the grid's search sessions use.
 */
export function withDecision(session, decision) {
  return next(session, {
    decision,
    phase: PHASE.COMPUTING,
    payload: null,
    selectedCandidateId: null,
    focusedSourceId: null,
    armed: false,
    error: null,
    requestSeq: session.requestSeq + 1,
  });
}

export function withPayload(session, payload, seq) {
  if (seq !== session.requestSeq) return session; // stale response, discarded
  return next(session, { phase: PHASE.READY, payload, error: null });
}

export function withError(session, error, seq) {
  if (seq !== session.requestSeq) return session;
  return next(session, { phase: PHASE.FAILED, error, payload: null });
}

/** Candidate selection is client-side only. It must never change `requestSeq`. */
export function withSelectedCandidate(session, candidateId) {
  return next(session, { selectedCandidateId: candidateId, armed: false });
}

export function withFocusedSource(session, sourceId) {
  return next(session, { focusedSourceId: sourceId, armed: false });
}

/** Arm / disarm the single confirmation. Arming is not a write. */
export function withArmed(session, armed) {
  return next(session, { armed: armed === true });
}

export function withConfig(session, config) {
  return next(session, { config });
}

/**
 * True when nothing this session has done could have written to the database.
 * Exploring is GET-only by construction: the only write path is the armed confirm.
 */
export function isExploringOnly(session) {
  return session.armed !== true;
}
