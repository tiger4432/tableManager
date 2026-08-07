/**
 * MAP EDITOR 2 -- THE SET-UP QUESTION, THE SERVED WORKLIST, AND WHAT MAY NOT BE CLAIMED.
 *
 * THIS HARNESS DOES NOT SLICE SOURCE. It `import`s every module it scores: no `readFileSync` of
 * a `.js`, no `node:vm`, no `node_modules`. That is possible because these modules take
 * arguments and return values.
 *
 * WHAT IS SCORED
 *   A. THE QUESTION IS PRIMITIVE -- {table, x, y, val, reference}, never a frame name. An
 *      invalid combination is UNEXPRESSIBLE rather than discovered through a server refusal.
 *   B. PROVENANCE SURVIVES TO THE SCREEN -- a `fallback_guess` binding is marked as a guess and
 *      refuses to underwrite the one write. The vocabulary is the SERVER'S
 *      (declared/derived/fallback_guess), not a second spelling invented client-side.
 *   C. ATTRIBUTION -- with two coordinate pairs available and nothing on the wire naming which
 *      one was read, the counts exist and their owner does not. Numerals are withheld.
 *   D. EVIDENCE -- occupancy-only is not an ordinary inconclusive run, and it reuses the word
 *      the system already has rather than growing a synonym.
 *   E. THE WORKLIST -- badges report the SERVER'S totals, never the rows on screen; rows below
 *      the boundary carry no per-row decoration; a stale search answer is discarded.
 *   F. TRANSPORT -- search goes to the server; unserved routes refuse by name; the existing
 *      schema and paint-rules routes are reused rather than reinvented.
 *   G. THE SHELL -- changing any part of the set-up costs exactly ONE fetch; selecting a
 *      candidate still costs none.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe): no emoji, no em-dash.
 */

import { createMapSession, withQuestion, withCatalog, withSelectedCandidate, withDecision,
         withPayload, withWorklistQuery, withWorklist, withWorklistError, withConfirmed,
         resolveQuestion, columnKey, isAskable, isUnset, columnsOf,
         BINDING_DECLARED, BINDING_DERIVED, BINDING_FALLBACK_GUESS, BINDING_NONE,
         EMPTY_QUESTION } from '../src/map2/session.js';
import { buildViewModel, assertNoRatio, countCoordinatePairs, selectAlignmentRules,
         VIEW_STATE, ATTRIBUTION,
         EVIDENCE, WORDS, CAUSE, UNKNOWN } from '../src/map2/view_model.js';
import { createApiClient, ROUTES, RouteNotServedError, normaliseReferenceCatalog,
         REFERENCE_CATALOG_SERVED, REFERENCE_CATALOG_UNAVAILABLE } from '../src/map2/api.js';
import { referenceOptionLabel, REFERENCE_KIND_WORD } from '../src/map2/view_model.js';
import { bootstrap, normaliseWorklist } from '../src/map2/main.js';
import { decideVerdict } from '../src/map2/verdict_bridge.js';

let compared = 0;
const failures = [];
function ok(cond, what) { compared++; if (!cond) failures.push(what); }
function eq(actual, expected, what) {
  compared++;
  if (actual !== expected) failures.push(`${what}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

// `dt_log` is the real shape that makes this screen hard: TWO coordinate pairs in one table.
const CATALOG = {
  tables: [{ table: 'dt_map', label: 'dt_map' }, { table: 'core_wafer_map', label: 'core_wafer_map' }],
  columns: {
    dt_map: ['dt_job', 'dt_x', 'dt_y', 'core_x', 'core_y', 'c_bn'],
    core_wafer_map: ['core_lot', 'core_slot', 'core_x', 'core_y', 'c_bn'],
  },
  binding: {
    // The SERVED shape, verbatim: x / y / val plus the provenance word.
    dt_map: { x: 'dt_x', y: 'dt_y', val: 'c_bn', source: BINDING_DECLARED },
    core_wafer_map: { x: 'core_x', y: 'core_y', val: null, source: BINDING_FALLBACK_GUESS },
  },
  // THE NORMALISED CATALOG ITEM, as `normaliseReferenceCatalog` emits it. No `label` field:
  // the picker's line is composed from the record, so a fixture cannot smuggle in a label the
  // production path would never produce.
  references: {
    dt_map: [{ value: 'dt_map:JOB1', table: 'dt_map', mapId: 'JOB1',
               kind: 'values', cellCount: 5024, grid: { cols: 63, rows: 63 } }],
    core_wafer_map: [],
  },
};

// ── A. the question is primitive, and invalid combinations are unexpressible ────
{
  const empty = createMapSession({});
  ok(isUnset(empty.question), 'A1 an untouched question is unset, not merely incomplete');
  ok(!isAskable(empty.question), 'A2 and it is not askable either -- the two are different states');
  eq(empty.question.columns.x, null, 'A3 no column is assumed');
  ok(!('field' in empty.question), 'A4 there is no frame field in the state, by absence');

  const s = withCatalog(empty, CATALOG);
  eq(s.question.mapTable, 'dt_map', 'A5 the first served table is adopted');
  eq(s.question.columns.x, 'dt_x', 'A6 the DECLARED binding fills x');
  eq(s.question.columns.val, 'c_bn', 'A7 and the value column it declares');
  eq(s.question.bindingSource, BINDING_DECLARED, 'A8 carrying the server word for its provenance');
  ok(isAskable(s.question), 'A9 a filled tuple is askable');

  // THE DEFECT THIS PREVENTS: switching table must not carry the previous table's column names
  // forward, or the request names columns that do not exist in the table it names.
  const switched = withQuestion(s, { mapTable: 'core_wafer_map' });
  eq(switched.question.columns.x, 'core_x', 'A10 a table switch re-binds x from the new table');
  ok(columnsOf(CATALOG, 'core_wafer_map').indexOf(switched.question.columns.x) >= 0,
     'A11 and the bound column exists in that table');
  eq(switched.question.columns.val, null, 'A12 an undeclared value column stays absent, not inherited');

  // A column the table does not have is not a column.
  const bogus = withQuestion(s, { columns: { x: 'no_such_col', y: 'dt_y', val: null } });
  ok(bogus.question.columns.x !== 'no_such_col', 'A13 a column outside the schema is never sent');
  ok(columnsOf(CATALOG, 'dt_map').indexOf(bogus.question.columns.x) >= 0,
     'A13b and the half-pair it left behind is repaired from the declaration');

  // A reference that is not on offer collapses to 기준 없음 -- a value, not a hole.
  const badRef = withQuestion(s, { reference: 'dt_map:GHOST' });
  eq(badRef.question.reference, null, 'A14 an unoffered reference collapses to 기준 없음');
  const goodRef = withQuestion(s, { reference: 'dt_map:JOB1' });
  eq(goodRef.question.reference, 'dt_map:JOB1', 'A15 an offered one is kept');
  // The reference list for core_wafer_map is empty, so the same value must not survive there.
  eq(withQuestion(goodRef, { mapTable: 'core_wafer_map' }).question.reference, null,
     'A16 changing table re-checks the reference against the new table');

  eq(resolveQuestion(EMPTY_QUESTION, null).mapTable, null, 'A17 no catalog invents no table');

  // Changing the set-up RE-ASKS: a stale answer must be droppable by sequence.
  const withRow = withDecision(s, { eqp: 'E', product: 'P' });
  const moved = withQuestion(withRow, { reference: 'dt_map:JOB1' });
  eq(moved.requestSeq, withRow.requestSeq + 1, 'A18 changing the set-up bumps the sequence');
  eq(withQuestion(moved, { reference: 'dt_map:JOB1' }), moved,
     'A19 re-selecting the same value is not a change and does not re-ask');
  const stale = withPayload(moved, { per_candidate: [] }, withRow.requestSeq);
  eq(stale, moved, 'A20 the previous set-up answer is discarded, not painted under new labels');

  // Per-pair picks survive a switch, so the operator does not lose a choice by looking around.
  const picked = withSelectedCandidate(moved, 'rot90_back');
  eq(picked.requestSeq, moved.requestSeq, 'A21 picking a candidate does NOT re-ask');
  const other = withQuestion(picked, { columns: { x: 'core_x', y: 'core_y', val: 'c_bn' } });
  eq(other.selectedCandidateId, null, 'A22 a different pair starts with no pick of its own');
  const back = withQuestion(other, { columns: { x: 'dt_x', y: 'dt_y', val: 'c_bn' } });
  eq(back.selectedCandidateId, 'rot90_back', 'A23 returning to a pair restores its pick');
  eq(columnKey({ x: 'dt_x', y: 'dt_y', val: 'c_bn' }), 'dt_x__dt_y',
     'A24 the pair key ignores the value column -- value decides scoring, not placement');
}

// ── A2. only a DECLARED alignment-capable rule may be offered ──────────────────
{
  const frame = { name: 'eqp_product_frame_attribution', alignment: true, target_fields: ['core_frame'] };
  const lot = { name: 'dt_job_lot_slot_attribution', target_fields: ['dt_lot_confirmed'] };

  const one = selectAlignmentRules([lot, frame]);
  eq(one.capable, 1, 'A25 only the rule carrying the flag is capable');
  eq(one.rules[0].name, 'eqp_product_frame_attribution', 'A26 and it is the one offered');
  ok(one.proposed, 'A27 a single candidate is proposed');
  eq(one.declaration.name, 'eqp_product_frame_attribution', 'A28 and adopted so the screen works');

  // 🔴 THE LIVE DEFECT THIS CLOSES: `rules[0]` proposed the lot/slot rule, which aligns nothing.
  ok(one.declaration.name !== 'dt_job_lot_slot_attribution',
     'A29 an unmarked rule is never proposed, whatever its position in the list');

  const many = selectAlignmentRules([frame, { name: 'other', alignment: true }]);
  eq(many.capable, 2, 'A30 two capable rules are both offered');
  eq(many.declaration, null, 'A31 and NOTHING is proposed -- there is no order to prefer');
  ok(!many.proposed, 'A32 so the screen asks rather than guessing');

  // ABSENCE IS A FACT. No fallback to offering everything.
  const none = selectAlignmentRules([lot, { name: 'x' }]);
  eq(none.capable, 0, 'A33 no flag means no capable rule');
  eq(none.rules.length, 0, 'A34 and the offer is EMPTY -- never a fallback to everything');
  eq(none.declaration, null, 'A35 with nothing proposed');
  eq(none.declared, 2, 'A36 while still reporting how many were declared, for the log');

  // A config typo must not unlock a capability.
  eq(selectAlignmentRules([{ name: 'a', alignment: 'true' }]).capable, 0,
     'A37 the STRING "true" is a typo, not a declaration');
  eq(selectAlignmentRules([{ name: 'a', alignment: 1 }]).capable, 0, 'A38 nor is 1');
  eq(selectAlignmentRules(null).capable, 0, 'A39 no rules at all is not a crash');
}

// ── B. a guess is marked, and may not underwrite the write ─────────────────────
{
  const guessed = withCatalog(createMapSession({}), CATALOG);
  const onGuess = withQuestion(guessed, { mapTable: 'core_wafer_map' });
  eq(onGuess.question.bindingSource, BINDING_FALLBACK_GUESS,
     'B1 a guessed binding keeps the SERVER word for its provenance');
  ok([BINDING_DECLARED, BINDING_DERIVED, BINDING_FALLBACK_GUESS, BINDING_NONE]
       .every(w => typeof w === 'string'),
     'B2 the provenance vocabulary is the served one, not a second spelling');
  eq(BINDING_FALLBACK_GUESS, 'fallback_guess',
     'B3 spelled exactly as /api/maps/paint-rules serves it');

  const scored = readySession(onGuess);
  const vmGuess = buildViewModel({ session: scored.session, verdict: scored.verdict });
  ok(vmGuess.question.bindingIsGuess, 'B4 the view model marks the pair as a guess');
  eq(vmGuess.question.proposalWord, WORDS.proposed, 'B5 with a word the view can show');
  // CONTRACT CHANGED 2026-08-07 (product owner: 「어차피 사람이 검수하고 누르는거라 막을
  // 이유없음」). A guessed pair no longer HOLDS the write -- it DISCLOSES it. The assertion
  // therefore moves rather than disappearing: what must stay true is that the operator is told
  // before pressing, which B7/B8 already pin. Deleting B6 outright would have left "the guess
  // is surfaced at all" resting on nothing.
  ok(vmGuess.confirm.enabled, 'B6 the write is available -- a guess is disclosed, not blocked');
  ok(vmGuess.confirm.restsOnGuess, 'B7 saying so as a value, not by being silently inert');
  ok(vmGuess.confirm.inertHint.length > 0, 'B8 and Enter is never silently inert');
  // Reading is still frictionless: a guess does not blank the screen.
  ok(vmGuess.numerals, 'B9 a guessed pair still SHOWS its measurement -- only the write is held');

  // Naming a column by hand is agreeing to it.
  const agreed = withQuestion(onGuess, { columns: { x: 'core_x', y: 'core_y', val: 'c_bn' } });
  eq(agreed.question.bindingSource, BINDING_DECLARED, 'B10 choosing a column by hand agrees to the pair');
  const vmAgreed = buildViewModel(readySession(agreed));
  ok(vmAgreed.confirm.enabled, 'B11 and the write becomes available');
  eq(vmAgreed.question.proposalWord, '', 'B12 with no proposal marker left over');
  // The tuple reaches the record as VALUES, not as a name to be re-parsed.
  eq(vmAgreed.confirm.xCol, 'core_x', 'B13 the record carries the x column');
  eq(vmAgreed.confirm.valCol, 'c_bn', 'B14 and the value column');
}

// ── C. an answer nobody can attribute is not attributed ────────────────────────
{
  // `dt_map` offers TWO pairs (dt_x/dt_y and core_x/core_y).
  eq(countCoordinatePairs(CATALOG.columns.dt_map), 2, 'C1 two coordinate pairs are counted');
  eq(countCoordinatePairs(CATALOG.columns.core_wafer_map), 1, 'C2 one pair here');
  eq(countCoordinatePairs(['dt_x', 'lot']), 0, 'C3 a lone x is not a pair');
  eq(countCoordinatePairs(null), 0, 'C4 no schema is no pairs, not a crash');

  const two = withCatalog(createMapSession({}), CATALOG);  // dt_map, two pairs
  const vm = buildViewModel(readySession(two));
  eq(vm.attribution.state, ATTRIBUTION.UNSTATED,
     'C5 two pairs and no echo on the wire means the answer has no stated owner');
  ok(!vm.numerals, 'C6 so the counts are NOT shown under a pair nobody named');
  eq(vm.summary.countText, UNKNOWN, 'C7 the count slot says the unknown word');
  eq(vm.cause.token, WORDS.columnsUnstated, 'C8 and the cause names the absence as a token');
  eq(vm.cause.count, 2, 'C9 with how many pairs it could have been');
  // CONTRACT CHANGED 2026-08-07 (same ruling as B6). An unattributed answer is confirmable;
  // the absence is carried by `cause` (C8/C9) and by `restsOnGuess`, not by an inert button.
  ok(vm.confirm.enabled, 'C10 an unattributed answer is confirmable -- the absence is named, not enforced');
  ok(vm.confirm.restsOnGuess, 'C10-bis and the record of WHY it was doubtful survives the opening');

  // The one-line server fix: echo the columns in `unit`, and the screen starts attributing.
  const echoed = buildViewModel(readySession(two, { unit: { x_col: 'dt_x', y_col: 'dt_y' } }));
  eq(echoed.attribution.state, ATTRIBUTION.DECLARED, 'C11 an echoed pair is a declaration');
  ok(echoed.numerals, 'C12 and the measurement becomes attributable');
  ok(echoed.confirm.enabled, 'C13 and confirmable');

  // One pair available is not ambiguous at all.
  const one = withQuestion(withCatalog(createMapSession({}), CATALOG), { mapTable: 'core_wafer_map' });
  eq(buildViewModel(readySession(one)).attribution.state, ATTRIBUTION.UNAMBIGUOUS,
     'C14 one pair needs no echo to be unambiguous');
}

// ── D. occupancy-only is its own statement ─────────────────────────────────────
{
  const base = withQuestion(withCatalog(createMapSession({}), CATALOG), { mapTable: 'core_wafer_map' });
  const tie = [{ candidate_id: 'rot0_front', agree: 500, discriminating: 528 },
               { candidate_id: 'rot90_front', agree: 499, discriminating: 528 }];
  const occ = buildViewModel(readySession(base, { reference: { kind: 'occupancy' } }, tie));
  eq(occ.evidence.kind, EVIDENCE.OCCUPANCY, 'D1 the evidence kind is read off the wire');
  ok(occ.evidence.occupancyOnly, 'D2 and flagged');
  eq(occ.state, VIEW_STATE.SCORED_NO_WINNER, 'D3 the tie is still a tie');
  eq(occ.cause.token, CAUSE.reference_no_values,
     'D4 but it is named with the word the system ALREADY has, not a new synonym');

  const vals = buildViewModel(readySession(base, { reference: { kind: 'values' } }, tie));
  eq(vals.evidence.kind, EVIDENCE.VALUES, 'D5 a valued run says so');
  ok(!vals.evidence.occupancyOnly, 'D6 and is not flagged as occupancy-only');
  ok(vals.cause.token !== CAUSE.reference_no_values,
     'D7 a genuine ambiguity does not borrow the thin-evidence wording');
}

// ── E. the worklist reports the server's totals, not the page ──────────────────
{
  const rows = [
    { eqp: 'E1', product: 'P1', state: 'pending', map_count: 12 },
    { eqp: 'E1', product: 'P2', state: 'confirmed', map_count: 7 },
    { eqp: 'E9', product: 'P9', state: 'unscorable', map_count: 4 },
  ];
  // THE SERVED SHAPE: `units` plus the route's own `totals` block.
  const s = withWorklist(createMapSession({}),
    normaliseWorklist({ units: rows,
      totals: { matched: 668, returned: rows.length, unscorable: 320,
                by_state: { pending: 348, confirmed: 40, unscorable: 320 } } }), 0);
  const wl = buildViewModel({ session: s, verdict: null }).worklist;
  eq(wl.rows.length, 2, 'E1 scorable rows sit above the boundary');
  eq(wl.unscorableRows.length, 1, 'E2 and the rest below it');
  ok(wl.boundaryVisible, 'E3 the boundary exists because something is below it');

  // 🔴 THE BADGE IS NOT `rows.length`. A page is not a population.
  eq(wl.remaining, 348, 'E4 the remaining badge is the SERVER total');
  eq(wl.unscorable, 320, 'E5 as is the unscorable badge');
  ok(wl.remaining !== wl.rows.length, 'E6 and it is not the count of rows on this page');

  // Below the boundary: no per-row decoration of any kind.
  eq(wl.unscorableRows[0].stateWord, '', 'E7 an unscorable row carries NO word of its own');
  eq(wl.rows[0].stateWord, WORDS.pending, 'E8 rows above it keep their state word');
  eq(wl.rows[1].stateWord, WORDS.confirmed, 'E9 in the nominal register');

  // No served total means no claim.
  const partial = withWorklist(createMapSession({}), normaliseWorklist({ units: rows }), 0);
  const wl2 = buildViewModel({ session: partial, verdict: null }).worklist;
  eq(wl2.remaining, null, 'E10 an unsent total is null, never substituted from the page');
  eq(wl2.unscorable, null, 'E11 same for the unscorable badge');
  eq(normaliseWorklist({ units: rows, totals: { by_state: { pending: '' } } }).remaining, null,
     'E12 an empty string is not a count');
  eq(normaliseWorklist(null).rows.length, 0, 'E13 a null response is an empty page, not a crash');
  eq(normaliseWorklist({ units: rows, totals: { matched: 668, returned: 3 } }).total, 668,
     'E13b `matched` is the population; `returned` is only how many fit in this page');

  // Nothing below the boundary means no boundary.
  const clean = withWorklist(createMapSession({}), normaliseWorklist({ units: rows.slice(0, 2) }), 0);
  ok(!buildViewModel({ session: clean, verdict: null }).worklist.boundaryVisible,
     'E14 no boundary is drawn when nothing is below it');

  // The search is sequence-guarded: a slow answer to a retyped query is discarded.
  const q1 = withWorklistQuery(createMapSession({}), 'EQP');
  const q2 = withWorklistQuery(q1, 'EQP-DT');
  eq(withWorklist(q2, normaliseWorklist({ units: rows }), q1.worklistSeq), q2,
     'E15 a stale search answer is discarded');
  eq(withWorklist(q2, normaliseWorklist({ units: rows }), q2.worklistSeq).worklist.rows.length, 3,
     'E16 the current one lands');
  eq(withWorklistError(q2, new Error('x'), q1.worklistSeq), q2, 'E17 a stale error too');
  eq(q2.worklist.query, 'EQP-DT', 'E18 the query is carried so the server can be re-asked');

  // Only the write moves the session counter.
  eq(withConfirmed(createMapSession({})).confirmedCount, 1, 'E19 a confirm is counted');
  eq(createMapSession({}).confirmedCount, 0, 'E20 and nothing else is');
}

// ── F. transport ───────────────────────────────────────────────────────────────
{
  const calls = [];
  const client = createApiClient({
    baseUrl: 'http://127.0.0.1:8080',
    fetchImpl: (url, init) => {
      calls.push({ url, method: init.method });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    },
  });

  // THE WORKLIST ROUTE LANDED. The search is the SERVER'S: `q` travels as a query parameter,
  // and there is no "load them all" call here for a browser filter to sit on top of.
  eq(ROUTES.worklist, '/api/maps/alignment/worklist', 'F1 the worklist route is served');
  await client.loadWorklist({ q: 'EQP', rule: 'r', mapTable: 'dt_map',
                              params: { dt_eqp: 'E' }, limit: 200, offset: 0 });
  ok(calls[0].url.includes('q=EQP'), 'F2 the search text goes to the server');
  ok(calls[0].url.includes('map_table=dt_map'), 'F3 scoped by the chosen table');
  ok(calls[0].url.includes('params='), 'F4 the unit filter travels as one encoded object');
  ok(!calls[0].url.includes('x_col='), 'F5 the coordinate columns are NOT sent -- they decide '
     + 'how a unit is read, not which units exist');
  ok(calls[0].url.includes('offset=0'), 'F5b paging is by the offset the route serves');
  // THE REFERENCE CATALOG ROUTE LANDED, standalone. It rode on `/worklist` before, which needs
  // both `rule` and `map_table` -- so on a deployment with no alignment-capable rule the picker
  // could never be filled, which is the production case.
  eq(ROUTES.referenceCatalog, '/api/maps/alignment/references',
     'F5c which floors resolve is served on a route of its own');
  ok(!('catalog' in ROUTES), 'F5d and the old placeholder route is gone, not left beside it');
  ok(!('loadCatalog' in client), 'F5e nor the loader that refused by name');

  // The routes that DO exist are reused, not reinvented.
  eq(ROUTES.schema, '/tables/{table}/schema', 'F6 the existing schema route is reused');
  eq(ROUTES.paintRules, '/api/maps/paint-rules', 'F7 and the existing binding route');
  eq(ROUTES.rules, '/enrichment/rules', 'F8 and the existing rule-meta route');
  await client.loadTableSchema('dt_map');
  ok(calls[1].url.includes('/tables/dt_map/schema'), 'F9 the schema call names the table in the path');
  await client.loadBinding('dt_map');
  ok(calls[2].url.includes('table=dt_map'), 'F10 the binding call asks for one table');

  // The reference view carries the PRIMITIVE TUPLE, and omits what was not chosen.
  await client.loadReferenceView({
    rule: 'r', mapTable: 'dt_map', params: { dt_eqp: 'E', product: 'P' },
    xCol: 'dt_x', yCol: 'dt_y', valCol: null, reference: null,
  });
  const viewUrl = calls[3].url;
  ok(viewUrl.includes('x_col=dt_x'), 'F11 the x column is sent');
  ok(viewUrl.includes('y_col=dt_y'), 'F12 and the y column');
  ok(!viewUrl.includes('value_col='), 'F13 an unchosen value column is OMITTED, not sent empty');
  ok(!viewUrl.includes('reference='), 'F14 and 기준 없음 is an omission, not an empty parameter');
  eq(calls.length, 4, 'F15 still exactly one request per view');
  ok(!('loadCandidate' in client), 'F16 there is still no per-candidate fetch, by absence');

  // Asked last here so the counts above stay the counts they were measuring.
  await client.loadReferenceCatalog();
  ok(calls[4].url.includes('/api/maps/alignment/references'),
     'F17 the catalog call names the reference route');
  ok(!calls[4].url.includes('?'), 'F18 and sends NO parameter -- `map_table` does not narrow '
     + 'the candidate set, and asking WITHOUT a rule is the whole point of the route');
}

// ── G. the shell: one fetch per set-up change, none per candidate ──────────────
{
  const doc = makeDocument();
  const fetches = [];
  const worklistCalls = [];
  const payload = {
    state: 'scored', refusal: null,
    // 🔴 THE ONE-LINE SERVER FIX, EXERCISED. `unit` echoes the pair that was read, so the shell
    //    can attribute the answer instead of refusing to. Without it, `dt_map`'s two pairs make
    //    every measurement unattributable -- which section C scores from the other side.
    // THE SERVED SHAPE: per axis, the column AND who chose it (`chosen` | `proposed` |
    // `absent`, server/map_alignment.py:474-476). Two words, kept as two.
    unit: { rule: 'eqp_product_frame_attribution', map_table: 'dt_map',
            columns: { x: { column: 'dt_x', origin: 'chosen' },
                       y: { column: 'dt_y', origin: 'chosen' },
                       value: { column: 'c_bn', origin: 'proposed', reason: null } } },
    reference: { state: 'ok', kind: 'values', cells: [[0, 0], [1, 0], [0, 1]] },
    sources: { map_count: 2, cell_count: 3, cells: [[0, 0], [1, 0], [2, 2]],
               maps: [{ map_id: 's1', cell_count: 3, declared_frame: 'rot0_front',
                        declared_frame_source: 'declared' }] },
    candidates: [{ frame: 'rot0_front', agreement: 200, discriminating: 300 },
                 { frame: 'rot180_back', agreement: 90, discriminating: 300 }],
    declaration: { frames: { rot0_front: 2 }, attested_maps: 2, unattested_maps: 0, axis_sources: {} },
    ruling: { winner: 'rot0_front' }, excluded_total: 0, stats: { scored_cells: 300, elapsed_ms: 9 },
  };
  const api = {
    counters: { reads: 0, writes: 0 },
    loadReferenceView: (r) => { fetches.push(r); return Promise.resolve(payload); },
    loadWorklist: () => Promise.resolve({ rows: [] }),
    loadAlignConfig: () => Promise.resolve({}),
    confirmFrame: (rec) => { api.counters.writes++; api.lastRecord = rec; return Promise.resolve({}); },
  };
  const app = bootstrap({ document: doc, api });
  eq(app.missing.length, 0, 'G1 the stub exposes every id this shell binds');
  app.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  app.setCatalog(CATALOG);
  app.setContext({ rule: 'eqp_product_frame_attribution', targetFields: ['core_frame'],
                   confirmedBy: 'tester', toDecisionKey: (d) => ({ dt_eqp: d.eqp, product: d.product }) });

  app.selectDecision({ eqp: 'E1', product: 'P1' });
  eq(fetches.length, 1, 'G2 selecting a row costs exactly one fetch');
  eq(fetches[0].mapTable, 'dt_map', 'G3 and it carries the chosen table');
  eq(fetches[0].columns.x, 'dt_x', 'G4 and the chosen x column');
  await settle();

  // THE BAR: changing any part of the set-up re-asks ONCE.
  const before = fetches.length;
  doc.getElementById('me2-reference-select').value = 'dt_map:JOB1';
  doc.getElementById('me2-reference-select').dispatchEvent('change');
  eq(fetches.length, before + 1, 'G5 changing the reference re-asks exactly once');
  eq(fetches[fetches.length - 1].reference, 'dt_map:JOB1', 'G6 with the new floor in the request');
  await settle();

  // The grid the page published for THIS column pair was empty; the shell fills it with list
  // items inside the container the page provided, and selecting one is still a repaint.
  const beforePick = fetches.length;
  const cells = doc.querySelectorAll('[data-me2-candidate]');
  eq(cells.length, 8, 'G7 the empty per-pair grid is populated with the eight, and only eight');
  cells.find(c => c.getAttribute('data-frame-code') === 'rot180_back').dispatchEvent('click');
  eq(fetches.length, beforePick, 'G8 switching candidates issues NO fetch');
  eq(api.counters.writes, 0, 'G9 and exploring performed zero writes');
  eq(doc.querySelectorAll('[data-me2-candidate]').length, 8,
     'G10 a repaint does not multiply the controls');

  // The write: a RECORD, not positional arguments. This was posting an empty body.
  const confirm = doc.getElementById('me2-confirm-btn');
  confirm.dispatchEvent('click');
  confirm.dispatchEvent('click');
  eq(api.counters.writes, 1, 'G16 arm-then-commit still yields exactly one write');
  ok(api.lastRecord && typeof api.lastRecord === 'object', 'G17 the write is given a record');
  eq(api.lastRecord.rule, 'eqp_product_frame_attribution', 'G18 naming the rule');
  eq(JSON.stringify(api.lastRecord.decisionKey), '{"dt_eqp":"E1","product":"P1"}',
     'G19 with the decision key filled from the rule, not from a literal');
  // 🔴 THE RECORD NAMES THE COLUMN PAIR, NOT A TARGET FIELD (ruling 2026-08-05). Nothing
  //    declares which pair writes which enrichment field, and the resolution is that this
  //    record does not need one -- so `frames` stays EMPTY rather than carrying a guess.
  eq(JSON.stringify(api.lastRecord.columns), '{"x":"dt_x","y":"dt_y","val":"c_bn"}',
     'G20 the record names the column pair that was aligned');
  eq(api.lastRecord.frame, 'rot180_back', 'G20b with the confirmed frame');
  eq(api.lastRecord.mapTable, 'dt_map', 'G20c and the table those coordinates live in');
  eq(JSON.stringify(api.lastRecord.frames), '{}',
     'G20d and it names NO target field -- an empty map, not a guessed one');
  eq(api.lastRecord.confirmedBy, 'tester', 'G21 and who confirmed it');

  // Two declared target fields no longer block anything, because the record names none: the
  // ambiguity was in the MAPPING, and the mapping is no longer part of this write.
  await settle();
  app.setContext({ targetFields: ['core_frame', 'dt_frame'] });
  const writesBefore = api.counters.writes;
  // Two clicks, ONE write -- and since 2026-08-06 that is a different fact than it was. It used
  // to mean "arm, then commit"; it now means the first click wrote and the in-flight guard
  // refused the second. Same number, opposite mechanism, so the comment has to say which.
  confirm.dispatchEvent('click');
  confirm.dispatchEvent('click');
  eq(api.counters.writes, writesBefore + 1, 'G22 a write that names no field is not ambiguous');
  eq(JSON.stringify(api.lastRecord.frames), '{}', 'G23 and still names none');

  // ── THE ENTER GUARD ─────────────────────────────────────────────────────────
  // 🔴 THE ONE WRITE IN THE CHAIN WAS REACHABLE BY A KEYSTROKE IN A DROPDOWN. The document
  //    keydown handler had no target guard, so Enter inside any of the five set-up selects
  //    armed on the first press and committed on the second, while the operator believed they
  //    were choosing a column.
  //
  // 🔴 AND THE GUARD GOT STRICTLY MORE LOAD-BEARING ON 2026-08-06, WHICH IS WHY THIS BLOCK IS
  //    RE-POINTED RATHER THAN RELAXED. One action now confirms: the arming step is gone, so
  //    `takesEnter` is no longer the FIRST of two things between a stray keystroke and a POST
  //    -- it is the ONLY one. A keystroke that used to cost an arming now costs a write.
  await settle();
  app.setContext({ targetFields: ['core_frame'] });
  app.render();
  const writesBeforeEnter = api.counters.writes;
  // Clear the acknowledgement first. A confirm landed earlier in this block, so asserting
  // `!confirmed` after the loop without this would be scoring a stale precondition -- it would
  // pass, or fail, for reasons that have nothing to do with the dropdowns. Re-picking a
  // candidate is the operator gesture that clears it.
  doc.querySelectorAll('[data-me2-candidate]')[0].dispatchEvent('click');
  ok(!app.peek().confirmed, 'G23b precondition: the acknowledgement is clear before the loop');
  for (const id of ['me2-table-select', 'me2-col-x', 'me2-col-y', 'me2-col-value',
                    'me2-reference-select', 'me2-worklist-search']) {
    const control = doc.getElementById(id);
    if (!control) continue;
    control.dispatchEvent('keydown', 'Enter');
    control.dispatchEvent('keydown', 'Enter');
  }
  eq(api.counters.writes, writesBeforeEnter, 'G24 Enter inside a set-up control performs NO write');
  ok(!app.peek().confirmed, 'G25 and nothing was confirmed by typing in a dropdown');
  // ... while Enter on the confirm control itself IS the write, by definition, in one press.
  //
  // 🔴 COUNTED, NOT INSPECTED. The stub fires the native `click` that a real focused <button>
  //    produces on Enter, and the shell binds `click` -> onConfirm as well as this keydown --
  //    so this number is 2 unless the handled keydown cancels its default. The end state is
  //    identical either way, which is why the assertion is on the COUNT.
  confirm.dispatchEvent('keydown', 'Enter');
  eq(api.counters.writes, writesBeforeEnter + 1,
     'G26 one Enter on the confirm control sends exactly ONE write');
  // And pressing it again while the first is still open does not send a second.
  confirm.dispatchEvent('keydown', 'Enter');
  eq(api.counters.writes, writesBeforeEnter + 1,
     'G27 a second Enter during the in-flight write sends nothing');

  // ── AGREEING TO A PROPOSAL ──────────────────────────────────────────────────
  // Re-picking the option ALREADY selected fires no `change`, so an operator who agrees with a
  // proposed pair had no way to say so and the write stayed blocked forever.
  app.setQuestion({ mapTable: 'core_wafer_map' });
  await settle();
  eq(app.peek().question.bindingSource, 'fallback_guess', 'G28 this table binds by guess');
  ok(!doc.getElementById('me2-columns-confirm').hidden, 'G29 so the agree control is shown');
  const beforeAgree = fetches.length;
  doc.getElementById('me2-columns-confirm').dispatchEvent('click');
  eq(app.peek().question.bindingSource, 'declared', 'G30 agreeing raises the provenance');
  eq(fetches.length, beforeAgree, 'G31 and does NOT re-ask -- the columns did not change');
  ok(doc.getElementById('me2-columns-confirm').hidden, 'G32 the control hides once agreed');

  // No percentage reached any of it.
  const vm = app.render();
  ok(assertNoRatio(vm), 'G24 no ratio reached the view model');
  ok(!JSON.stringify(vm).includes('%'), 'G25 and no percent sign anywhere in it');
  eq(vm.question.references[0].label, WORDS.alignUnavailable,
     'G26 기준 없음 leads the reference list as a real option');
  eq(vm.question.references[0].value, '', 'G27 and its value is the omission, not a name');
}

// ── H. the reference picker: which floors resolve, and what each can answer ─────
// The gap this closes: the picker was empty in production BY INSTRUCTION. The catalog route
// had landed and the client was still writing `references[t] = []` beside a `degraded` marker
// that had been correct only while no route existed.
{
  // The DIRECT shape, which is what the standalone route returns.
  const served = normaliseReferenceCatalog({
    state: 'served', table: 'dt_valid_die', examined: 9, rejected: 1,
    rejected_example: '격자 규격 불일치', truncated: false, reason: null,
    items: [
      { table: 'dt_valid_die', map_id: 'WMAP1', kind: 'values',
        cell_count: 5024, grid: { cols: 63, rows: 63 } },
      { table: 'dt_valid_die', map_id: 'WMAP2', kind: 'occupancy',
        cell_count: 4, grid: null },
      // Unnameable: no map id. Cannot be selected, so it is not offered.
      { table: 'dt_valid_die', map_id: null, kind: 'values', cell_count: 12 },
    ],
  });
  eq(served.items.length, 2, 'H1 an item that cannot be named is not offered');
  eq(served.items[0].value, 'dt_valid_die:WMAP1',
     'H2 the value is the wire spelling `table:map_id`, composed once in the transport');
  eq(served.state, REFERENCE_CATALOG_SERVED, "H3 the server's own state word survives");
  eq(served.rejectedExample, '격자 규격 불일치',
     'H4 and its accounting for what it threw away -- a short list with rejections is a '
     + 'DIFFERENT fact from a short list without');

  // 🔴 THE SAME RECORD ALSO RIDES ON `/worklist` AS `selection.references`. One decoder for
  //    both, so a second reader cannot grow beside the worklist copy and drift from it.
  const nested = normaliseReferenceCatalog({ selection: { references: {
    state: 'served', table: 'dt_valid_die',
    items: [{ table: 'dt_valid_die', map_id: 'WMAP1', kind: 'values', cell_count: 5024 }],
  } } });
  eq(nested.items[0].value, 'dt_valid_die:WMAP1', 'H5 the worklist envelope decodes identically');

  // 🔴 THE VOCABULARY IS THE SERVER'S, ONE SPELLING. `kind` on a catalog item and
  //    `reference.kind` on `/view` are one word; two spellings would let the picker promise
  //    what the run denies.
  eq(served.items[0].kind, EVIDENCE.VALUES, 'H6 `values` is passed through verbatim');
  eq(served.items[1].kind, EVIDENCE.OCCUPANCY, 'H7 and `occupancy`');
  ok(!(EVIDENCE.NONE in REFERENCE_KIND_WORD),
     'H8 there is NO `none` branch -- a catalog item resolves by construction');

  // 🔴 `kind` IS VISIBLE AT SELECTION TIME. This is the whole reason the field exists: a floor
  //    carrying occupancy alone cannot discriminate, and one production case had all eight
  //    candidates scoring identically against exactly such a floor. Learning that by running it
  //    wastes the run.
  const valuesLine = referenceOptionLabel(served.items[0]);
  const occLine = referenceOptionLabel(served.items[1]);
  ok(valuesLine.includes(WORDS.refValues), 'H9 a valued floor says so on its own line');
  ok(occLine.includes(WORDS.refOccupancy), 'H10 and an occupancy-only floor says so');
  ok(valuesLine !== occLine, 'H11 so the two are distinguishable BEFORE a run is spent');
  // 🔴 AND IT LEADS, WHICH IS WHAT MAKES IT SURVIVE. The control is 238px wide (measured live)
  //    and a <select> truncates from the right, so any ordering that puts identity first
  //    truncates the kind away exactly when the map id is long.
  eq(valuesLine.split(' · ')[0], WORDS.refValues, 'H11b kind is the FIRST token, never cut off');
  eq(occLine.split(' · ')[0], WORDS.refOccupancy, 'H11c for both kinds');
  const longId = referenceOptionLabel({ mapId: 'WAFERMAP_20260805_A1', kind: 'occupancy',
                                        cellCount: 4, grid: null });
  ok(longId.startsWith(WORDS.refOccupancy),
     'H11d a realistic long map id cannot push the kind off the right edge');
  ok(!valuesLine.includes('dt_valid_die'), 'H11e the constant table is not spending pixels on '
     + 'the line -- it lives in `value` and in the console record');
  ok(occLine.includes(`4${WORDS.cellUnit}`),
     'H12 the line carries the measured size -- a four-cell floor is not worth choosing');
  ok(valuesLine.includes('63x63'), 'H13 and the grid when the server measured one');
  ok(!occLine.includes('null') && !occLine.includes('undefined'),
     'H14 an absent grid contributes NO token rather than a printed null');
  eq(valuesLine.split('\n').length, 1, 'H15 ONE line on screen; the record goes to the console');
  ok(!/%/.test(valuesLine + occLine), 'H16 and no percentage anywhere in it');

  // An unmeasured count says the unknown word. Never a 0: a measured zero-cell floor would be
  // a very loud fact, and a stand-in makes the two indistinguishable.
  const unmeasured = normaliseReferenceCatalog({ state: 'served', items: [
    { table: 'dt_valid_die', map_id: 'WMAP3', kind: 'values', cell_count: null }] });
  eq(unmeasured.items[0].cellCount, null, 'H17 an unmeasured count stays absent in the record');
  ok(referenceOptionLabel(unmeasured.items[0]).includes(UNKNOWN),
     'H18 and reads as the unknown word on screen, never as 0');

  // The server looked and could not answer. Its own word, not a second spelling.
  const dead = normaliseReferenceCatalog({ state: 'unavailable', reason: '맵 규격 표 미등록' });
  eq(dead.state, REFERENCE_CATALOG_UNAVAILABLE, 'H19 an unavailable catalog says so');
  eq(dead.items.length, 0, 'H20 and offers nothing rather than something plausible');
  // An ABSENT state is not a served one. Defaulting it would let the caller read "the server
  // looked and found nothing" out of a body that never said so.
  eq(normaliseReferenceCatalog({ items: [] }).state, null,
     'H20b an absent state stays absent, and is therefore not `served`');

  // 🔴 `기준 없음` IS A REAL, SELECTABLE VALUE IN EVERY CASE -- with a full list, and with an
  //    empty one. It is the COMMON case (the maps that need aligning are exactly the ones with
  //    no reference), so it must never read as a picker's empty state or as an error.
  const withRefs = withCatalog(createMapSession({}), {
    ...CATALOG, references: { ...CATALOG.references, dt_map: served.items } });
  const full = buildViewModel({ session: withRefs, verdict: null }).question.references;
  eq(full[0].label, WORDS.alignUnavailable, 'H21 기준 없음 leads a POPULATED list too');
  eq(full.length, 3, 'H22 with every resolving floor beside it');
  ok(full[1].label.includes(WORDS.refValues), 'H23 each carrying what it can answer');
  const empty = buildViewModel({
    session: withCatalog(createMapSession({}), { ...CATALOG, references: { dt_map: [] } }),
    verdict: null,
  }).question.references;
  eq(empty.length, 1, 'H24 an empty catalog still offers 기준 없음, and offers it alone');
  eq(empty[0].label, WORDS.alignUnavailable, 'H25 which is a value, not an empty state');
  ok(empty[0].selected, 'H26 and it is what stands selected');

  // There is no "show all" affordance, by absence: what did not resolve is never offered, and
  // nothing on this side may reveal it into the control.
  ok(!JSON.stringify(full).includes('valid_die_ref'),
     'H27 no declared-but-unresolvable pointer reaches the picker');

  // 🔴 `not_offered` IS DIAGNOSIS, NOT AN OFFER. The server names what it refused and why
  //    (`server/map_alignment.py:1413-1419`) because a reasonless "none" sends the operator to
  //    a person instead of to a repair -- so it rides in the console record and is kept out of
  //    `items` and out of the control.
  const withRefused = normaliseReferenceCatalog({
    state: 'served', table: 'dt_valid_die',
    items: [{ table: 'dt_valid_die', map_id: 'OK1', kind: 'values', cell_count: 500 }],
    not_offered: [{ table: 'dt_valid_die', map_id: 'BAD1', reason_code: 'meta_missing',
                    reason: '맵 규격 행 없음', cell_count: 4096 }],
    examined: 2, rejected: 1, rejected_example: '맵 규격 행 없음',
  });
  eq(withRefused.items.length, 1, 'H29 only what resolves lands in `items`');
  eq(withRefused.notOffered.length, 1, 'H30 and what did not is carried separately');
  eq(withRefused.notOffered[0].reason, '맵 규격 행 없음',
     "H31 with the server's own sentence verbatim, not a second spelling");
  eq(withRefused.notOffered[0].cellCount, 4096,
     'H32 and its cell count -- HAVING cells and still not resolving is a different repair');
  const offered = buildViewModel({
    session: withCatalog(createMapSession({}), {
      ...CATALOG, references: { ...CATALOG.references, dt_map: withRefused.items } }),
    verdict: null,
  }).question.references;
  eq(offered.length, 2, 'H33 the picker offers 기준 없음 and the ONE floor that resolves');
  ok(!JSON.stringify(offered).includes('BAD1'),
     'H34 the refused candidate is nowhere in the control -- no "show all" affordance');

  // The config route is still unserved, and still refuses by name.
  const c = createApiClient({ baseUrl: '', fetchImpl: () => Promise.reject(new Error('no')) });
  let stillRefused = null;
  await c.loadAlignConfig().catch(e => { stillRefused = e; });
  ok(stillRefused instanceof RouteNotServedError, 'H28 the threshold route still refuses by name');
}

console.log(`ASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) {
  console.log('\nFAILURES');
  for (const f of failures) console.log(`  - ${f}`);
}
process.exit(failures.length === 0 ? 0 : 1);

// ────────────────────────────────────────────────────────────────────────────────
function settle() { return Promise.resolve().then(() => {}).then(() => {}).then(() => {}); }

/** A READY session plus its verdict, built from the decoded payload the shell would hold. */
function readySession(session, extra, scorings) {
  const per = scorings || [
    { candidate_id: 'rot0_front', agree: 512, discriminating: 528 },
    { candidate_id: 'rot90_front', agree: 300, discriminating: 528 },
  ];
  const thresholds = { min_margin_dies: 20, min_discriminating_dies: 40 };
  const payload = {
    stored_candidate_id: null, sources: [], floor_cells: [], per_candidate: per,
    map_count: 2, excluded_map_count: 0, discriminating_dies: 528, elapsed_ms: 10,
    reference_kind: (extra && extra.reference && extra.reference.kind) || 'values',
    answered_columns: (extra && extra.unit && extra.unit.x_col)
      ? { x: extra.unit.x_col, y: extra.unit.y_col, agreed: true } : null,
  };
  // The sequence is READ, never assumed: `withQuestion` bumps it, so a hardcoded `1` here
  // silently discards the payload as stale and leaves every state reading `computing`. That is
  // the same guard the shell relies on, so getting it wrong here fails quietly rather than loudly.
  const started = withDecision(createMapSession({ ...session, config: thresholds }),
    { eqp: 'E', product: 'P' });
  const ready = withPayload(started, payload, started.requestSeq);
  return { session: ready, verdict: decideVerdict(per, thresholds) };
}

/** The minimal document. Not jsdom: this harness runs with no `node_modules`. */
function makeDocument() {
  const registry = new Map();
  const docListeners = {};

  function makeEl(tag) {
    const el = {
      tagName: String(tag).toUpperCase(), children: [], attrs: {}, style: {}, className: '',
      hidden: false, disabled: false, type: '', title: '', value: '', parentNode: null,
      __listeners: {},
      setAttribute(k, v) { this.attrs[k] = String(v); },
      getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
      removeAttribute(k) { delete this.attrs[k]; },
      appendChild(node) { node.parentNode = this; this.children.push(node); return node; },
      addEventListener(type, fn) { (this.__listeners[type] = this.__listeners[type] || []).push(fn); },
      // `key` carries the KEY for keydown and the type otherwise, which is what the shell's
      // keydown handler reads. `target` is this node, so the Enter guard sees a real tagName.
      dispatchEvent(type, key) {
        let defaultPrevented = false;
        const ev = { target: this, key: key === undefined ? type : key,
                     preventDefault() { defaultPrevented = true; } };
        let n = this;
        while (n) { for (const fn of n.__listeners[type] || []) fn(ev); n = n.parentNode; }
        for (const fn of (docListeners[type] || [])) fn(ev);
        // 🔴 NATIVE ACTIVATION, MODELLED ON PURPOSE (2026-08-06). A focused <button> activated
        //    by Enter ALSO fires a `click` unless the keydown's default was cancelled. The stub
        //    did not model this, and that omission is exactly why a double confirmation could
        //    not be seen from here: the shell binds `click` -> onConfirm AND has a document
        //    keydown -> onConfirm, so one real Enter calls it twice. Under the old two-step the
        //    second call hit the arming branch and cost nothing; with one-action confirm it is
        //    a second POST. A stub that under-models the platform reports green on a defect
        //    that only exists in a real browser -- the failure mode this file exists to avoid.
        if (type === 'keydown' && ev.key === 'Enter' && this.tagName === 'BUTTON'
            && !this.disabled && !defaultPrevented) {
          this.dispatchEvent('click');
        }
        return !defaultPrevented;
      },
      closest(sel) {
        if (sel === '#me2-confirm-btn') return this.attrs.id === 'me2-confirm-btn' ? this : null;
        let node = this;
        while (node) { if (matches(node, sel)) return node; node = node.parentNode; }
        return null;
      },
    };
    let ownText = '';
    Object.defineProperty(el, 'textContent', {
      get() { return this.children.length > 0 ? this.children.map(c => c.textContent).join('') : ownText; },
      set(v) { ownText = String(v); this.children.length = 0; },
    });
    return el;
  }

  function matches(node, sel) {
    const m = /^\[([^\]=]+)(?:="([^"]*)")?\]$/.exec(sel);
    if (!m || !node.attrs) return false;
    if (!Object.prototype.hasOwnProperty.call(node.attrs, m[1])) return false;
    return m[2] === undefined || node.attrs[m[1]] === m[2];
  }
  function collect(node, sel, out) {
    for (const child of node.children || []) {
      if (matches(child, sel)) out.push(child);
      collect(child, sel, out);
    }
    return out;
  }
  function withQuery(el) {
    el.querySelectorAll = (sel) => collect(el, sel, []);
    el.querySelector = (sel) => collect(el, sel, [])[0] || null;
    return el;
  }

  const body = withQuery(makeEl('body'));
  const doc = {
    body, documentElement: makeEl('html'), __listeners: docListeners,
    createElement: (tag) => withQuery(makeEl(tag)),
    createElementNS: (_ns, tag) => withQuery(makeEl(tag)),
    getElementById: (id) => registry.get(id) || null,
    addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
    querySelectorAll: (sel) => collect(body, sel, []),
    querySelector: (sel) => collect(body, sel, [])[0] || null,
    // No `setTimeout` here on purpose: the debounce falls through to an immediate run, so the
    // search is scored for WHERE it goes rather than for how long it waits.
    defaultView: { console, getComputedStyle: () => ({ getPropertyValue: () => '' }) },
  };

  function node(tag, id, attrs) {
    const n = withQuery(makeEl(tag));
    if (id) { n.setAttribute('id', id); registry.set(id, n); }
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  }

  // REAL TAG NAMES for the five selects and the two buttons. The Enter guard keys on what kind
  // of control has focus, so a stub that made every node a <div> would score the guard as
  // working while the live page committed a write from inside a dropdown.
  for (const id of ['me2-rule-select', 'me2-table-select', 'me2-col-x', 'me2-col-y',
                    'me2-col-value', 'me2-reference-select']) {
    body.appendChild(node('select', id));
  }
  // `me2-assume-accept` used to be authored here because the shell bound it. Both are gone
  // (2026-08-06): the borrowing is automatic, so there is no act to accept, and a stub that
  // kept the node would hand `getElementById` something the real document does not have.
  for (const id of ['me2-columns-confirm', 'me2-confirm-btn']) {
    body.appendChild(node('button', id));
  }

  for (const id of ['me2-workbench', 'me2-worklist-rows', 'me2-worklist-rows-unscorable',
                    'me2-worklist-search', 'me2-worklist-empty', 'me2-worklist-meta',
                    'me2-worklist-boundary', 'me2-worklist-boundary-label',
                    'me2-question-note',
                    'me2-badge-session',
                    'me2-badge-unscorable', 'me2-badge-remaining', 'me2-picture-svg',
                    'me2-layer-floor', 'me2-layer-miss', 'me2-layer-onlyone', 'me2-layer-alone',
                    'me2-picture-caption', 'me2-refusal', 'me2-verdict-headline',
                    'me2-verdict-cause', 'me2-source-list', 'me2-sources-meta',
                    'me2-metric-conflict', 'me2-confirm-sentence',
                    'me2-confirm-note', 'me2-confirm-hint',
                    // The footer, bound since 2026-08-06 to carry the refusal state attribute.
                    'me2-confirmbar',
                    'me2-export-btn', 'me2-paste-result',
                    // The rank picture, bound since 2026-08-06 (third census: the stub).
                    'me2-index-control', 'me2-index-colour', 'me2-index-legend',
                    'me2-index-bar', 'me2-index-min', 'me2-index-max', 'me2-index-note']) {
    body.appendChild(node('div', id));
  }
  for (const attr of ['data-me2-picture-meta', 'data-me2-top-agree', 'data-me2-top-discriminating',
                      'data-me2-margin-dies', 'data-me2-maps-total', 'data-me2-maps-excluded']) {
    const slot = node('span', null, { [attr]: '' });
    slot.textContent = 'AUTHORED';
    body.appendChild(slot);
  }
  const head = registry.get('me2-verdict-headline');
  const num = node('span', null, { 'data-me2-verdict': '' });
  num.textContent = 'AUTHORED';
  head.appendChild(num);

  // One candidate grid, keyed by the COLUMN SET rather than by a frame name.
  const grid = node('div', 'me2-cands-dt_x__dt_y', { 'data-me2-candidates-for': 'dt_x__dt_y' });
  registry.get('me2-source-list').appendChild(grid);
  return doc;
}
