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

// ── THE QUESTION ────────────────────────────────────────────────────────────────
// The set-up the screen never let anyone express: WHICH TABLE, WHICH COLUMNS ARE THE
// COORDINATES, and WHICH FLOOR to compare against. One question, not three features -- one
// call answers it and changing any part re-asks it. Held together so an invalid combination
// cannot be expressed, rather than being discovered through a server refusal.
//
// 🔴 COLUMNS, NOT A FRAME FIELD. This was a `core_frame` / `dt_frame` picker for one round.
//    That picker was a name for "which x/y pair am I reading" -- `dt_log` carries `dt_x`/`dt_y`
//    and `core_x`/`core_y`, and choosing the frame field chose the pair by proxy. Naming the
//    columns makes any table with a coordinate pair alignable without a declaration having to
//    exist for it first, and it removes a hardcoded list of frame names from the client.
//
// 🔴 `value` IS OPTIONAL AND THE CHOICE DECIDES WHAT CAN BE ANSWERED. Without it only
//    occupancy can be scored, which is measured flat: 8 candidates inside 4 points, and one
//    production case has all 8 occupying the SAME dies -- an 8-way tie on a question that value
//    agreement settles by 374 dies. The payload already carries this distinction as
//    `reference.kind` (`none` | `occupancy` | `values`), so the screen reads it there rather
//    than growing a second opinion. What it must never do is let a missing value column read as
//    an ordinary run that happened to be inconclusive.
//
// 🔴 `reference: null` IS A VALUE, NOT AN ABSENCE. `기준 없음` is the ordinary case: the maps
//    that need alignment are exactly the ones with no valid-die reference, which is why the
//    floor is a parameter at all. Null means "asked with no floor" and is sent by OMITTING the
//    parameter; it is not a hole waiting to be filled.
// 🔴 THE SPELLING IS THE REPO'S, NOT THIS FILE'S. `x` / `y` / `val` is how a coordinate binding
//    is already declared -- `map_overlay_config.json` -> `table_bindings.<table>.columns`
//    ({x, y, val, key_columns[]}) -- and how it is already SERVED to clients, resolved, by
//    `GET /api/maps/paint-rules?table=` (`server/main.py:4394`, `map_overlay.resolve_binding_info`
//    at `map_overlay.py:995`). A `{x, y, value}` of this file's own invention would be a second
//    spelling of a declaration that exists, which is the defect class this screen keeps meeting.
export const EMPTY_COLUMNS = Object.freeze({ x: null, y: null, val: null });
// 🔴 THE BORROWED GEOMETRY IS PART OF THE QUESTION, NOT A DISPLAY TOGGLE. It is a query
//    parameter on the same request (`assume_reference_geometry`), so it belongs with the other
//    four: changing it re-asks, and the answer to the previous set-up is dropped rather than
//    painted under the new labels. Holding it anywhere else would let a screen show a result
//    scored WITHOUT the assumption while the control says the assumption is in force.
//
// 🔴 IT DEFAULTS FALSE AND IT IS AN ACT. "These two maps are the same wafer" is a claim, and the
//    operator is the one entitled to make it -- which is why the server defaults it off too. A
//    screen that turned it on by itself would have manufactured a declaration nobody made, on
//    the layer the bonding plan rests on.
export const EMPTY_QUESTION = Object.freeze({
  mapTable: null,
  columns: EMPTY_COLUMNS,
  // Provenance, in the SERVED vocabulary. See BINDING_* below.
  bindingSource: 'none',
  reference: null,
  assumeReferenceGeometry: false,
});

/**
 * How a column pair came to be filled in. THESE THREE ARE THE SERVER'S OWN WORDS, served by
 * `/api/maps/paint-rules` as `binding.source`; the fourth is this client's name for that
 * route's `null` (no binding resolvable), which has no server-side spelling because absence
 * is not a value there.
 *
 * 🔴 `fallback_guess` IS THE EXISTING NAME FOR "A PROPOSAL YOU MUST NOT TRUST SILENTLY", and
 *    the route's own contract says so: it is served only WITH that marker precisely so a client
 *    warns instead of rendering it like a declaration (the data path refuses it outright). So a
 *    pre-filled pair is marked here and refuses to underwrite the write -- using the existing
 *    marker rather than a new word for the same idea.
 */
export const BINDING_DECLARED = 'declared';
export const BINDING_DERIVED = 'derived';
export const BINDING_FALLBACK_GUESS = 'fallback_guess';
export const BINDING_NONE = 'none';

/**
 * What the operator is allowed to choose between. Served, never derived here.
 *
 * 🔴 THE CLIENT DOES NOT DECIDE WHICH REFERENCES RESOLVE. Eight production rows declare a
 *    `valid_die_ref` and zero of them resolve -- they name maps that are not registered.
 *    Offering a name that cannot work teaches the operator to distrust the picker, so the
 *    catalog carries only what the server says resolves, and an empty list is the ordinary
 *    `기준 없음` state rather than an error.
 */
export const EMPTY_CATALOG = Object.freeze({
  tables: Object.freeze([]),
  // Per table, the REAL SCHEMA's column names -- `/tables/{table}/schema`, the route admin
  // already consumes. No column list is written down in this client.
  columns: Object.freeze({}),
  // Per table, the coordinate binding IF one is declared, with its provenance.
  binding: Object.freeze({}),
  references: Object.freeze({}),
});

/** The worklist as served. `rows` is one page; searching and ordering are the server's. */
export const EMPTY_WORKLIST = Object.freeze({
  rows: Object.freeze([]),
  total: null,
  remaining: null,
  unscorable: null,
  cursor: null,
  query: '',
  served: false,
  error: null,
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
    // The three set-up parameters, composed. See EMPTY_QUESTION.
    question: init.question || EMPTY_QUESTION,
    catalog: init.catalog || EMPTY_CATALOG,
    worklist: init.worklist || EMPTY_WORKLIST,
    // The worklist has its OWN sequence. Its search is served, so a slow answer for a query the
    // operator already retyped must be dropped rather than painted -- the same guard class as
    // `requestSeq`, kept separate because a worklist search must not cancel a reference view.
    worklistSeq: Number.isFinite(init.worklistSeq) ? init.worklistSeq : 0,
    // Which of the eight the operator is LOOKING at. Selection is a repaint, never a fetch.
    selectedCandidateId: init.selectedCandidateId || null,
    // Per-field picks, so switching field does not forget the other field's choice. The write
    // is keyed `{target_field: frame}` (server/main.py:4246), so this IS the write's shape.
    selections: init.selections || Object.freeze({}),
    // Confirms performed in this browser session. A measured count, never an estimate.
    confirmedCount: Number.isFinite(init.confirmedCount) ? init.confirmedCount : 0,
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
    // 🔴 THE CLAIM DOES NOT FOLLOW THE OPERATOR DOWN THE WORKLIST. Borrowing is asserted about
    //    ONE unit's maps; leaving it latched would apply it to every row afterwards without
    //    anybody asserting anything -- a screen that silently assumes, which is precisely the
    //    failure the server's off-by-default exists to prevent. The rest of the set-up (table,
    //    columns, floor) survives a row change on purpose, because it says how to READ a unit.
    //    This one says something about the unit itself, so it dies with it.
    question: Object.freeze({ ...session.question, assumeReferenceGeometry: false }),
    selectedCandidateId: null,
    // Per-field picks belong to ONE decision unit. Carrying them across rows would put the
    // previous unit's answer under the next unit's labels.
    selections: Object.freeze({}),
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
  const key = columnKey(session.question && session.question.columns);
  const selections = key
    ? Object.freeze({ ...session.selections, [key]: candidateId })
    : session.selections;
  return next(session, { selectedCandidateId: candidateId, selections, armed: false });
}

/**
 * The identity of one coordinate pair, used to key the per-pair candidate grid the markup
 * already publishes as `[data-me2-candidates-for]`. The VALUE column is deliberately not part
 * of it: the value decides what can be SCORED, not which pair is being placed.
 */
export function columnKey(columns) {
  const c = columns || EMPTY_COLUMNS;
  return c.x && c.y ? `${c.x}__${c.y}` : '';
}

// ── THE QUESTION'S TRANSITIONS ──────────────────────────────────────────────────

/**
 * Normalise a question against what is actually on offer, so an INVALID COMBINATION CANNOT BE
 * EXPRESSED rather than being discovered through a refusal. The dependency runs one way: the
 * table decides which frame fields exist, and the pair decides which references make sense.
 *
 * A reference that is not in the catalog collapses to `null`, which is `기준 없음` -- an
 * ordinary state and the commonest one, not a hole.
 */
export function resolveQuestion(question, catalog) {
  const cat = catalog || EMPTY_CATALOG;
  const q = question || EMPTY_QUESTION;
  const tables = Array.isArray(cat.tables) ? cat.tables : [];
  const tableNames = tables.map(t => t.table);
  const mapTable = tableNames.includes(q.mapTable) ? q.mapTable
    : (tableNames.length > 0 ? tableNames[0] : q.mapTable || null);

  // A column name that is not in THAT table's schema is not a column. Keeping it would let a
  // table switch carry the previous table's names forward, and the request would then name
  // columns that do not exist -- discovered as a refusal instead of being unexpressible.
  const cols = columnsOf(cat, mapTable);
  const known = (name) => (cols.length === 0 ? !!name : cols.includes(name));
  const asked = q.columns || EMPTY_COLUMNS;
  let x = known(asked.x) ? asked.x : null;
  let y = known(asked.y) ? asked.y : null;
  let val = known(asked.val) ? asked.val : null;
  let bindingSource = q.bindingSource === BINDING_DECLARED ? BINDING_DECLARED : BINDING_FALLBACK_GUESS;

  // Nothing chosen for this table yet: adopt whatever the catalog says about it, CARRYING ITS
  // PROVENANCE. A declared binding is a declaration; a name-matched guess stays a proposal all
  // the way to the screen, where the confirm control refuses to rest on it.
  // 🔴 A HALF-CARRIED PAIR IS NOT A PAIR. Switching table drops whichever column names the new
  //    table does not have, which routinely leaves ONE of x/y standing -- `core_x` survives a
  //    move that kills `dt_y`. Adopting the new table's declaration only when BOTH were empty
  //    left that half-pair in force, unbindable and unaskable, and the operator had to notice
  //    and repair it by hand. Either half missing means the declaration takes over.
  if (!x || !y) {
    const b = (cat.binding && cat.binding[mapTable]) || null;
    if (b && known(b.x) && known(b.y)) {
      x = b.x; y = b.y;
      // 🔴 THE TRIPLE IS ADOPTED WHOLE, NOT MERGED WITH THE PREVIOUS TABLE'S CHOICE. Dropping
      //    the declared `val` turns a valued run into an occupancy-only one, which is measured
      //    flat and reports 8-way ties -- but CARRYING one over a declaration that says the new
      //    table has no value column is the same failure in the other direction: a stale choice
      //    impersonating a declaration. The binding for the table now in force decides all three.
      val = known(b.val) ? b.val : null;
      bindingSource = b.source === BINDING_DECLARED ? BINDING_DECLARED : BINDING_FALLBACK_GUESS;
    } else {
      bindingSource = BINDING_NONE;
    }
  }
  if (!x || !y) bindingSource = BINDING_NONE;

  const refs = (mapTable && cat.references && Array.isArray(cat.references[mapTable]))
    ? cat.references[mapTable] : [];
  const reference = refs.some(r => r.value === q.reference) ? q.reference : null;

  // 🔴 NOT GATED ON `reference`, AND THAT IS MEASURED RATHER THAN ASSUMED. The floor the
  //    geometry is borrowed from is the RESOLVED one, and it resolves from the source map's own
  //    `valid_die_ref` when the picker sends nothing (`server/main.py:4245-4247`). Requiring a
  //    picked reference here would refuse the offer on exactly the units that carry a working
  //    declaration -- an invalid combination invented on this side, about a state the server
  //    never refuses. What DOES invalidate the claim is MOVING the floor, and that is a
  //    transition, not a normalisation: see `withQuestion`.
  const assume = q.assumeReferenceGeometry === true;

  return Object.freeze({
    mapTable,
    columns: Object.freeze({ x: x || null, y: y || null, val: val || null }),
    bindingSource,
    reference,
    assumeReferenceGeometry: assume,
  });
}

/** The table's real column names, as served by `/tables/{table}/schema`. */
export function columnsOf(catalog, table) {
  const cat = catalog || EMPTY_CATALOG;
  const list = cat.columns && Array.isArray(cat.columns[table]) ? cat.columns[table] : [];
  return list;
}

/** True when the tuple is complete enough to send. A guessed binding still asks. */
export function isAskable(question) {
  const q = question || EMPTY_QUESTION;
  return !!(q.mapTable && q.columns && q.columns.x && q.columns.y);
}

/**
 * Nothing has been set up at all -- no catalog adopted, no control touched.
 *
 * 🔴 THIS IS NOT THE SAME STATE AS "SET UP INCOMPLETELY", and collapsing the two is what turned
 *    every end-to-end path dead in one edit. An untouched question constrains nothing, so the
 *    request falls through to whatever the page entry supplies, exactly as it did before a
 *    set-up row existed. A HALF-filled one -- a table chosen whose coordinate columns nobody
 *    named -- is a real refusal, and it must not be papered over by asking anyway.
 *
 * ⚠️ `assumeReferenceGeometry` IS DELIBERATELY NOT ON THIS LIST. This predicate asks whether the
 *    tuple is COMPLETE ENOUGH TO SEND -- table and coordinates -- and the assumption is not an
 *    axis of that: it qualifies how the maps are scored, not which ones are read. Counting it
 *    would make an asserted-but-otherwise-untouched question "set up incompletely" and refuse
 *    to ask at all, which is the collapse the paragraph above is about.
 */
export function isUnset(question) {
  const q = question || EMPTY_QUESTION;
  const c = q.columns || EMPTY_COLUMNS;
  return !q.mapTable && !c.x && !c.y && !c.val && !q.reference;
}

/**
 * Adopt a served catalog and re-normalise the standing question against it. A catalog that
 * arrives after a question was already expressed must not leave an unreachable combination
 * selected, so normalisation runs on BOTH edges rather than only on operator input.
 */
export function withCatalog(session, catalog) {
  const cat = catalog || EMPTY_CATALOG;
  return next(session, { catalog: cat, question: resolveQuestion(session.question, cat) });
}

/**
 * Change one or more of the three. Bumps `requestSeq`: this RE-ASKS the same question with a
 * different set-up, so an answer to the previous set-up must be dropped rather than painted
 * under the new labels. That is the same defect class as a stale row response, and it is worse
 * here because the labels would still read as current.
 */
export function withQuestion(session, patch) {
  const merged = { ...session.question, ...(patch || {}) };
  // Naming a column is AGREEING to it. A proposal the operator edited is no longer a proposal
  // about the part they touched, and the pair as a whole stops being one the moment either half
  // is chosen by hand -- which is what makes the confirm control usable at all.
  if (patch && (patch.columns || patch.bindingSource)) {
    merged.bindingSource = patch.bindingSource || BINDING_DECLARED;
  }
  // 🔴 MOVING THE TABLE OR THE FLOOR TAKES THE CLAIM OFF. The assertion is "THESE maps are the
  //    same wafer as THAT floor" -- it is about the two things being changed, so carrying it
  //    across would re-assert it about a pair the operator has not looked at. That is the
  //    silent-assumption failure with an extra step, and it is the one this control exists to
  //    prevent. An assume patch is exempt, because that patch IS the operator asserting it.
  if (patch && patch.assumeReferenceGeometry === undefined
      && (patch.mapTable !== undefined || patch.reference !== undefined)) {
    merged.assumeReferenceGeometry = false;
  }
  const question = resolveQuestion(merged, session.catalog);
  const same = question.mapTable === session.question.mapTable
    && columnKey(question.columns) === columnKey(session.question.columns)
    && question.columns.val === session.question.columns.val
    && question.bindingSource === session.question.bindingSource
    && question.reference === session.question.reference
    && question.assumeReferenceGeometry === session.question.assumeReferenceGeometry;
  if (same) return session;
  const key = columnKey(question.columns);
  return next(session, {
    question,
    // Per-column-set picks survive a switch; the ACTIVE pick follows the new set.
    selectedCandidateId: (key && session.selections[key]) || null,
    payload: null,
    armed: false,
    error: null,
    phase: session.decision ? PHASE.COMPUTING : PHASE.IDLE,
    requestSeq: session.requestSeq + 1,
  });
}

/** A new search string. Bumps `worklistSeq` so a late answer to an old query is discarded. */
export function withWorklistQuery(session, query) {
  return next(session, {
    worklist: Object.freeze({ ...session.worklist, query: String(query == null ? '' : query) }),
    worklistSeq: session.worklistSeq + 1,
  });
}

export function withWorklist(session, worklist, seq) {
  if (seq !== session.worklistSeq) return session; // stale search answer, discarded
  return next(session, {
    worklist: Object.freeze({ ...session.worklist, ...worklist, served: true, error: null }),
  });
}

export function withWorklistError(session, error, seq) {
  if (seq !== session.worklistSeq) return session;
  return next(session, {
    worklist: Object.freeze({ ...session.worklist, rows: Object.freeze([]), served: false, error }),
  });
}

/** One confirm landed. The only counter on this screen that a write is allowed to move. */
export function withConfirmed(session) {
  return next(session, { armed: false, confirmedCount: session.confirmedCount + 1 });
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
