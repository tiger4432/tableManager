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
import { buildViewModel, assertNoRatio, countCoordinatePairs, VIEW_STATE, ATTRIBUTION,
         EVIDENCE, WORDS, CAUSE, UNKNOWN } from '../src/map2/view_model.js';
import { createApiClient, ROUTES, RouteNotServedError } from '../src/map2/api.js';
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
  references: { dt_map: [{ value: 'dt_map:JOB1', label: 'JOB1' }], core_wafer_map: [] },
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
  ok(!vmGuess.confirm.enabled, 'B6 and the ONE write refuses to rest on it');
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
  ok(!vm.confirm.enabled, 'C10 an unattributed answer may not be confirmed');

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
  // The catalog route stayed unserved, and that is now correct rather than pending: the
  // worklist response carries `selection`, so nothing needs a second call.
  eq(ROUTES.catalog, null, 'F5c no separate catalog call exists');
  let refused = null;
  await client.loadCatalog({}).catch(e => { refused = e; });
  ok(refused instanceof RouteNotServedError, 'F5d and asking for one refuses by name');

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
  confirm.dispatchEvent('click');
  confirm.dispatchEvent('click');
  eq(api.counters.writes, writesBefore + 1, 'G22 a write that names no field is not ambiguous');
  eq(JSON.stringify(api.lastRecord.frames), '{}', 'G23 and still names none');

  // ── THE ENTER GUARD ─────────────────────────────────────────────────────────
  // 🔴 THE ONE WRITE IN THE CHAIN WAS REACHABLE BY A KEYSTROKE IN A DROPDOWN. The document
  //    keydown handler had no target guard, so Enter inside any of the five set-up selects
  //    armed on the first press and committed on the second, while the operator believed they
  //    were choosing a column.
  await settle();
  app.setContext({ targetFields: ['core_frame'] });
  app.render();
  const writesBeforeEnter = api.counters.writes;
  for (const id of ['me2-table-select', 'me2-col-x', 'me2-col-y', 'me2-col-value',
                    'me2-reference-select', 'me2-worklist-search']) {
    const control = doc.getElementById(id);
    if (!control) continue;
    control.dispatchEvent('keydown', 'Enter');
    control.dispatchEvent('keydown', 'Enter');
  }
  eq(api.counters.writes, writesBeforeEnter, 'G24 Enter inside a set-up control performs NO write');
  ok(!app.peek().armed, 'G25 and does not even arm the control');
  // ... while Enter on the confirm control itself is still the write, by definition.
  confirm.dispatchEvent('keydown', 'Enter');
  ok(app.peek().armed, 'G26 Enter on the confirm control still arms');
  confirm.dispatchEvent('keydown', 'Enter');
  eq(api.counters.writes, writesBeforeEnter + 1, 'G27 and the second press commits');

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
        const ev = { target: this, key: key === undefined ? type : key };
        let n = this;
        while (n) { for (const fn of n.__listeners[type] || []) fn(ev); n = n.parentNode; }
        for (const fn of (docListeners[type] || [])) fn(ev);
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
  for (const id of ['me2-table-select', 'me2-col-x', 'me2-col-y', 'me2-col-value',
                    'me2-reference-select']) {
    body.appendChild(node('select', id));
  }
  for (const id of ['me2-columns-confirm', 'me2-confirm-btn']) body.appendChild(node('button', id));

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
                    'me2-confirm-note', 'me2-confirm-hint', 'me2-export-btn', 'me2-paste-result']) {
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
