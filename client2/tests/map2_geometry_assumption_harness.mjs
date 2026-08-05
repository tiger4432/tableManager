/**
 * MAP EDITOR 2 -- THE BORROWED WAFER GEOMETRY: THE OFFER, THE ACT, AND THE MARK IT LEAVES.
 *
 * THIS HARNESS DOES NOT SLICE SOURCE. It `import`s every module it scores.
 *
 * THE DEFECT IT EXISTS FOR: the server can score a source map that declares no physical spec by
 * borrowing the reference floor's wafer dimensions, it emits that offer on every run where the
 * offer would help, and the client never asked for it. The offer was emitted into nothing and
 * the screen stayed a dead end. Every assertion below is about one of the four halves of the
 * repair -- the offer is SEEN, accepting is an ACT, the act reaches the WIRE, and a result
 * reached that way is MARKED.
 *
 * WHAT IS SCORED
 *   A. THE VOCABULARY -- `assumed` is a token both sides know. A borrowed geometry that the
 *      client cannot name is sorted into some other bucket while every server test stays green.
 *   B. NOTHING ASSUMES BY DEFAULT -- a fresh question sends no `assume_reference_geometry` at
 *      all, and only `=== true` unlocks it. The server defaults it off because borrowing is a
 *      claim; a client that sent it for convenience would manufacture a declaration.
 *   C. ACCEPTING IS ONE ACT, ONE RE-ASK -- the flag rides the same question the five set-up
 *      controls ride, so the sequence guard and the payload drop are the ones already scored.
 *   D. THE CLAIM DOES NOT LATCH -- it dies with the row, the table and the floor it was made
 *      about. A claim that followed the operator down the worklist is a silent assumption with
 *      an extra step.
 *   E. `requested` IS NOT `applied` -- asking on a unit with no resolvable floor is not a
 *      borrowing that happened.
 *   F. THE MARK -- one line (the server's own sentence, naming the floor), a per-map basis, a
 *      workbench hook, and a disclosure on the one write.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe): no emoji, no em-dash.
 */

import { ASSUMED, DECLARED, ABSENT, DECLARATION_TOKENS,
         COMPUTABLE_TOKENS } from '../src/map2/declaration.js';
import { decodeReferenceView, verdictContext,
         ASSUMPTION_APPLIED, ASSUMPTION_AVAILABLE, ASSUMPTION_UNAVAILABLE,
         isAssumedGeometry, isDeclaredGeometry } from '../src/map2/decode.js';
import { createMapSession, withQuestion, withCatalog, withDecision, withPayload,
         resolveQuestion, EMPTY_QUESTION, BINDING_DECLARED } from '../src/map2/session.js';
import { buildViewModel, assertNoRatio, VIEW_STATE, WORDS } from '../src/map2/view_model.js';
import { createApiClient } from '../src/map2/api.js';
import { bootstrap, adaptPayload } from '../src/map2/main.js';
import { decideVerdict } from '../src/map2/verdict_bridge.js';

let compared = 0;
const failures = [];
function ok(cond, what) { compared++; if (!cond) failures.push(what); }
function eq(actual, expected, what) {
  compared++;
  if (actual !== expected) {
    failures.push(`${what}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// ── the wire, as the server actually serves it ──────────────────────────────────
// `server/map_alignment.py:1366-1373` for the block, `:797-812` for the sentence, `:815-834`
// for the per-map basis. The sentence is copied verbatim rather than paraphrased: this harness
// scores that the client RENDERS the server's words, so inventing my own here would score the
// client against a sentence nobody serves.
const FLOOR = { table: 'core_wafer_map', map_id: 'LOT-A_05' };
const OFFER_TEXT = '맵 3개는 기준(core_wafer_map / LOT-A_05)과 같은 웨이퍼로 가정하면 채점 가능'
  + ' - 가정은 기록에 남고 규격으로 저장되지 않음';
const APPLIED_TEXT = '맵 3개를 기준(core_wafer_map / LOT-A_05)의 웨이퍼 치수를 빌려 채점'
  + ' - 동일 웨이퍼 가정이며 이 맵의 규격 선언이 아님';

function wire(over) {
  const o = over || {};
  return {
    unit: { rule: 'r', decision_key: { dt_eqp: 'E', product: 'P' },
            source_table: 'dt_log', map_table: 'dt_map', map_key_columns: ['dt_job'] },
    state: o.state || 'scored',
    refusal: o.refusal === undefined ? null : o.refusal,
    reference: { state: 'resolved', kind: 'values', source: 'declared',
                 table: FLOOR.table, map_id: FLOOR.map_id, count: 500, cells: [] },
    sources: {
      map_count: 2, usable_map_count: 2, cell_count: 4, cells: [], truncated: false,
      maps: o.maps || [
        { map_id: 'M1', cell_count: 2, declared_frame: 'rot0_front',
          declared_frame_source: 'declared', geometry: DECLARED, geometry_basis: DECLARED },
        { map_id: 'M2', cell_count: 2, declared_frame: null,
          declared_frame_source: null, geometry: ABSENT, geometry_basis: ASSUMED },
      ],
    },
    candidates: [
      { frame: 'rot0_front', agreement: 512, discriminating: 528 },
      { frame: 'rot90_front', agreement: 300, discriminating: 528 },
    ],
    declaration: { frames: { rot0_front: 1 }, unanimous: false, frame: null,
                   attested_maps: 1, unattested_maps: 1, axis_sources: {} },
    ruling: { winner: 'rot0_front', margin: 212, reason_code: null,
              geometry_assumed: o.geometry_assumed === true },
    assumption: o.assumption === undefined
      ? { state: ASSUMPTION_AVAILABLE, requested: false, basis: { ...FLOOR },
          map_count: 3, map_ids: ['M2', 'M3', 'M4'], text: OFFER_TEXT }
      : o.assumption,
    excluded: [], excluded_total: 1,
    stats: { scored_cells: 528, elapsed_ms: 12 },
  };
}

const THRESHOLDS = { min_margin_dies: 20, min_discriminating_dies: 40 };

// ════════════════════════════════════════════════════════════════════════════════
// A. THE VOCABULARY -- CONFIRMED, NOT ASSUMED
// ════════════════════════════════════════════════════════════════════════════════
// This is the check the brief asked to CONFIRM rather than perform blind. `assumed` was already
// in `declaration.js` when this lane arrived (the frame-declaration lane landed it, with the
// reasoning at `declaration.js:113-140`). Scored here anyway: a token that is present today and
// silently dropped tomorrow is the same divergence, and only an assertion notices.
ok(DECLARATION_TOKENS.includes(ASSUMED),
   'A1 `assumed` is in the shared provenance vocabulary');
eq(ASSUMED, 'assumed', 'A2 spelled byte-identically to server/map_overlay.GEOMETRY_ASSUMED');
ok(COMPUTABLE_TOKENS.includes(ASSUMED) && COMPUTABLE_TOKENS.includes(DECLARED),
   'A3 `assumed` is COMPUTABLE -- a map scored on borrowed geometry was scored');
ok(!COMPUTABLE_TOKENS.includes(ABSENT),
   'A4 and computability did not become "anything that is not absent"');

// ════════════════════════════════════════════════════════════════════════════════
// B. NOTHING ASSUMES BY DEFAULT
// ════════════════════════════════════════════════════════════════════════════════
eq(EMPTY_QUESTION.assumeReferenceGeometry, false,
   'B1 the empty question does not assume');

const sent = [];
function recordingClient() {
  return createApiClient({
    baseUrl: '',
    fetchImpl: (url) => {
      sent.push(String(url));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(wire()) });
    },
  });
}
const REQ = { rule: 'r', mapTable: 'dt_map', params: { dt_eqp: 'E', product: 'P' } };

await recordingClient().loadReferenceView({ ...REQ });
ok(!sent[0].includes('assume_reference_geometry'),
   'B2 an ordinary view request carries no assume parameter at all -- omitted, not sent false');

sent.length = 0;
await recordingClient().loadReferenceView({ ...REQ, assumeReferenceGeometry: true });
ok(sent[0].includes('assume_reference_geometry=true'),
   'B3 the claim, once made, is on the wire');

// A config typo, a stray string, a truthy object: none of them may unlock a claim.
for (const junk of ['true', 1, {}, 'yes']) {
  sent.length = 0;
  await recordingClient().loadReferenceView({ ...REQ, assumeReferenceGeometry: junk });
  ok(!sent[0].includes('assume_reference_geometry'),
     `B4 truthy junk (${JSON.stringify(junk)}) does not unlock the claim -- === true strictly`);
}

// ════════════════════════════════════════════════════════════════════════════════
// C + D. THE ACT, AND THAT IT DOES NOT LATCH
// ════════════════════════════════════════════════════════════════════════════════
const CATALOG = {
  tables: [{ table: 'dt_map', label: 'dt_map' }, { table: 'core_wafer_map', label: 'core_wafer_map' }],
  columns: { dt_map: ['dt_x', 'dt_y', 'c_bn'], core_wafer_map: ['core_x', 'core_y', 'c_bn'] },
  columnTypes: { dt_map: { dt_x: 'number', dt_y: 'number' },
                 core_wafer_map: { core_x: 'number', core_y: 'number' } },
  binding: { dt_map: { x: 'dt_x', y: 'dt_y', val: 'c_bn', source: BINDING_DECLARED },
             core_wafer_map: { x: 'core_x', y: 'core_y', val: null, source: BINDING_DECLARED } },
  references: { dt_map: [{ value: `${FLOOR.table}:${FLOOR.map_id}`, mapId: FLOOR.map_id,
                           kind: 'values', cellCount: 500 },
                         { value: 'core_wafer_map:OTHER', mapId: 'OTHER',
                           kind: 'values', cellCount: 400 }],
                core_wafer_map: [] },
};

const base = withCatalog(createMapSession({ config: THRESHOLDS }), CATALOG);
const accepted = withQuestion(base, { assumeReferenceGeometry: true });
eq(accepted.question.assumeReferenceGeometry, true, 'C1 accepting sets the claim');
ok(accepted.requestSeq > base.requestSeq,
   'C2 accepting RE-ASKS -- the answer already on screen was scored without the assumption');
eq(accepted.payload, null, 'C3 and the previous answer is dropped rather than re-labelled');

// 🔴 THE FLOOR MAY RESOLVE FROM THE MAP'S OWN DECLARATION, so an accepted claim must NOT be
//    normalised away just because the picker sent nothing. This was a real defect in the first
//    cut of `resolveQuestion` and it would have refused the offer on exactly the units that
//    carry a working `valid_die_ref`.
const noPicker = resolveQuestion({ ...EMPTY_QUESTION, mapTable: 'dt_map',
                                   columns: { x: 'dt_x', y: 'dt_y', val: null },
                                   assumeReferenceGeometry: true }, CATALOG);
eq(noPicker.reference, null, 'C4 no floor is picked (the ordinary state)');
eq(noPicker.assumeReferenceGeometry, true,
   'C5 and the claim survives it -- the floor resolves server-side from valid_die_ref');

const nextRow = withDecision(accepted, { eqp: 'E2', product: 'P2' });
eq(nextRow.question.assumeReferenceGeometry, false,
   'D1 the claim dies with the row -- it is asserted about ONE unit, not latched');
eq(nextRow.question.mapTable, accepted.question.mapTable,
   'D2 and the rest of the set-up survives the row change, as before');

const movedFloor = withQuestion(accepted, { reference: 'core_wafer_map:OTHER' });
eq(movedFloor.question.assumeReferenceGeometry, false,
   'D3 moving the floor takes the claim off -- it was about THAT floor');
const movedTable = withQuestion(accepted, { mapTable: 'core_wafer_map' });
eq(movedTable.question.assumeReferenceGeometry, false,
   'D4 moving the table takes the claim off -- it was about THOSE maps');
const pickedColumn = withQuestion(accepted, {
  columns: { ...accepted.question.columns, val: 'c_bn' } });
eq(pickedColumn.question.assumeReferenceGeometry, true,
   'D5 but naming a VALUE column does not -- it changes how the same maps are read, '
   + 'not which wafer they are claimed to be');

// ════════════════════════════════════════════════════════════════════════════════
// E + F. THE DECODE AND THE MARK
// ════════════════════════════════════════════════════════════════════════════════
const offered = decodeReferenceView(wire());
eq(offered.assumption.state, ASSUMPTION_AVAILABLE, 'E1 an untaken offer reads as available');
ok(offered.assumption.offered, 'E2 and is actionable');
ok(!offered.assumption.applied, 'E3 and has not been taken');
eq(offered.assumption.basisTable, undefined, 'E4 the basis is a record, not flat fields');
eq(offered.assumption.basis.table, FLOOR.table, 'E5 the offer names the floor it borrows from');
eq(offered.assumption.basis.mapId, FLOOR.map_id, 'E6 including which map on it');
eq(offered.assumption.mapCount, 3, 'E7 and how many maps it covers');
eq(offered.assumption.text, OFFER_TEXT, 'E8 the sentence is the server, verbatim');
eq(offered.geometryAssumed, false, 'E9 nothing was assumed, so the ruling says so');

const appliedWire = wire({
  geometry_assumed: true,
  assumption: { state: ASSUMPTION_APPLIED, requested: true, basis: { ...FLOOR },
                map_count: 3, map_ids: ['M2', 'M3', 'M4'], text: APPLIED_TEXT },
});
const applied = decodeReferenceView(appliedWire);
ok(applied.assumption.applied, 'E10 an applied assumption reads as applied');
ok(!applied.assumption.offered, 'E11 and is no longer an offer -- the act was performed');
eq(applied.geometryAssumed, true, 'E12 the ruling carries the fact about itself');

// 🔴 REQUESTED IS NOT APPLIED. A request on a unit whose floor does not resolve comes back
//    `unavailable`, and reading the request back as the state would report a borrowing that
//    never happened -- a screen confident about a wafer nobody borrowed from.
const refusedWire = wire({
  assumption: { state: ASSUMPTION_UNAVAILABLE, requested: true, basis: null,
                map_count: 0, map_ids: [], text: null },
});
const refused = decodeReferenceView(refusedWire);
ok(!refused.assumption.applied && !refused.assumption.offered,
   'E13 asking on a unit with nothing to borrow from is not a borrowing');
eq(refused.assumption.requested, true, 'E14 but the request is still recorded, not erased');
eq(refused.assumption.text, null, 'E15 and there is no sentence to show');

// Per map: what it says about itself vs what this run stood on.
const m1 = offered.sources.find(s => s.id === 'M1');
const m2 = offered.sources.find(s => s.id === 'M2');
eq(m1.geometry, DECLARED, 'F1 a declared map says so');
ok(isDeclaredGeometry(m1), 'F2 and stood on its own declaration');
eq(m2.geometry, ABSENT, 'F3 a borrowing map declares nothing of its own');
eq(m2.geometryBasis, ASSUMED, 'F4 and the run stood on borrowed dimensions');
ok(isAssumedGeometry(m2) && !isDeclaredGeometry(m2),
   'F5 the two questions stay split -- borrowed is not declared, and not a refusal either');

// A token neither side agreed on must be NAMED, not bucketed. This is the failure mode the
// brief pointed at: the server grows a word, the client sorts it into whatever catches it, and
// every server test stays green.
const alien = decodeReferenceView(wire({
  maps: [{ map_id: 'M9', cell_count: 1, declared_frame: null, declared_frame_source: null,
           geometry: 'borrowed_ish', geometry_basis: 'borrowed_ish' }],
}));
eq(alien.sources[0].geometryBasis, null, 'F6 an unknown provenance token is dropped, not kept');
ok(alien.rejected.some(r => r.includes('borrowed_ish')),
   'F7 and named out loud, so the fix goes to the side that can make it');

const badState = decodeReferenceView(wire({
  assumption: { state: 'maybe', requested: false, basis: { ...FLOOR },
                map_count: 1, map_ids: ['M2'], text: 'x' },
}));
eq(badState.assumption.state, ASSUMPTION_UNAVAILABLE,
   'F8 an unrecognised assumption state falls back to "nothing on offer", never to an offer');
ok(badState.rejected.some(r => r.includes('maybe')), 'F9 and is named');

const nameless = decodeReferenceView(wire({
  assumption: { state: ASSUMPTION_AVAILABLE, requested: false, basis: null,
                map_count: 2, map_ids: ['M2', 'M3'], text: 'x' },
}));
ok(!nameless.assumption.offered,
   'F10 an offer with no floor named is not an offer -- "borrow from somewhere" is not a claim');
ok(nameless.rejected.some(r => r.includes('no basis')), 'F11 and is named');

// ── the view model ──────────────────────────────────────────────────────────────
function ready(rawPayload, question) {
  let s = withCatalog(createMapSession({ config: THRESHOLDS }), CATALOG);
  if (question) s = withQuestion(s, question);
  s = withDecision(s, { eqp: 'E', product: 'P' });
  const adapted = adaptPayload(rawPayload);
  s = withPayload(s, adapted, s.requestSeq);
  return buildViewModel({ session: s, verdict: decideVerdict(adapted.per_candidate, THRESHOLDS,
                                                             adapted.__context) });
}

const vmOffer = ready(wire());
eq(vmOffer.assumption.line, OFFER_TEXT, 'F12 the offer is ONE line and it is the server\'s');
ok(vmOffer.assumption.line.includes(FLOOR.map_id),
   'F13 which names the floor -- not summarised away');
ok(vmOffer.assumption.offered, 'F14 so a control may be shown');
eq(vmOffer.assumption.word, '', 'F15 an untaken offer is not a mark on the answer');
eq(vmOffer.confirm.geometryAssumed, false, 'F16 and the write discloses nothing');

const vmApplied = ready(appliedWire);
eq(vmApplied.assumption.line, APPLIED_TEXT,
   'F17 an applied assumption keeps saying so, in the server\'s words');
eq(vmApplied.assumption.word, WORDS.geometryAssumed, 'F18 plus a one-word mark for tight slots');
eq(vmApplied.assumption.basisLabel, `${FLOOR.table}:${FLOOR.map_id}`,
   'F19 the basis is spelled the way /view takes it back');
ok(!vmApplied.assumption.offered, 'F20 and there is nothing left to accept');
ok(vmApplied.confirm.geometryAssumed && vmApplied.confirm.note.includes(WORDS.geometryAssumed),
   'F21 the ONE write discloses that its geometry was borrowed');
ok(vmApplied.confirm.enabled,
   'F22 and is NOT blocked -- the claim is the operator\'s to make; blocking would rebuild the '
   + 'dead end this capability exists to open');
eq(vmApplied.state, VIEW_STATE.SCORED_WINNER, 'F23 a borrowed geometry still produces a verdict');
assertNoRatio(vmApplied);
compared++;

// The disclosure outranks "unchanged", and neither is lost.
const stored = ready({ ...appliedWire,
  declaration: { ...appliedWire.declaration, unanimous: true, unattested_maps: 0 } });
ok(stored.confirm.note.startsWith(WORDS.geometryAssumed),
   'F24 which geometry the answer rests on leads the confirm note');

// ════════════════════════════════════════════════════════════════════════════════
// G. END TO END THROUGH THE SHELL -- one click, one fetch, the flag on the wire
// ════════════════════════════════════════════════════════════════════════════════
{
  const doc = makeDocument();
  const asked = [];
  const app = bootstrap({
    document: doc,
    api: { confirmFrame: () => Promise.resolve({}) },
  });
  app.setLoader((decision, question) => {
    asked.push(question.assumeReferenceGeometry === true);
    return Promise.resolve(asked.length === 1 ? wire() : appliedWire);
  });
  app.setConfig(THRESHOLDS);
  app.setCatalog(CATALOG);
  app.selectDecision({ eqp: 'E', product: 'P' });
  await settle();

  const note = doc.getElementById('me2-question-note');
  const accept = doc.getElementById('me2-assume-accept');
  eq(asked[0], false, 'G1 the first request assumed nothing');
  ok(note.textContent.includes(FLOOR.map_id),
     'G2 the offer is on screen, naming the floor, without anyone asking for it');
  eq(accept.hidden, false, 'G3 and there is a control to accept it');
  eq(note.getAttribute('data-me2-note-tone'), null,
     'G4 an offer is an ordinary state and is not painted as a warning');

  const before = app.bar.fetches;
  accept.dispatchEvent('click');
  await settle();
  eq(app.bar.fetches - before, 1, 'G5 accepting costs exactly ONE fetch');
  eq(asked[1], true, 'G6 and that request carries the claim');
  eq(doc.getElementById('me2-workbench').getAttribute('data-me2-assumed'), 'true',
     'G7 the result region is marked as standing on a borrowed wafer');
  eq(note.getAttribute('data-me2-note-tone'), 'caution',
     'G8 and NOW the line is a warning, because numbers rest on it');
  eq(accept.hidden, true, 'G9 the control is gone -- the act was performed once');
  eq(doc.getElementById('me2-confirm-note').textContent.includes(WORDS.geometryAssumed), true,
     'G10 the write discloses it');

  const rows = doc.querySelectorAll('[data-me2-source]');
  const borrowed = rows.find(r => r.getAttribute('data-source-field') === 'M2');
  const own = rows.find(r => r.getAttribute('data-source-field') === 'M1');
  ok(borrowed && borrowed.getAttribute('data-me2-geometry-basis') === ASSUMED,
     'G11 the map that borrowed says so, per row');
  ok(borrowed && borrowed.getAttribute('data-me2-proposed') === 'true',
     'G12 wearing the SAME proposal shape as a guessed column pair -- not a second language');
  ok(own && own.getAttribute('data-me2-proposed') === 'false',
     'G13 and the map that measured its own geometry does not');
}

console.log(`ASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) {
  console.log('\nFAILURES');
  for (const f of failures) console.log(`  - ${f}`);
}
process.exit(failures.length === 0 ? 0 : 1);

// ────────────────────────────────────────────────────────────────────────────────
function settle() {
  return Promise.resolve().then(() => {}).then(() => {}).then(() => {}).then(() => {});
}

/** The minimal document. Not jsdom: this harness runs with no `node_modules`. */
function makeDocument() {
  const registry = new Map();
  const docListeners = {};

  function makeEl(tag) {
    const el = {
      tagName: String(tag).toUpperCase(), children: [], attrs: {}, style: {}, className: '',
      hidden: false, disabled: false, type: '', value: '', parentNode: null, __listeners: {},
      setAttribute(k, v) { this.attrs[k] = String(v); },
      getAttribute(k) {
        return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
      },
      removeAttribute(k) { delete this.attrs[k]; },
      appendChild(n) { n.parentNode = this; this.children.push(n); return n; },
      insertBefore(n, ref) {
        const at = this.children.indexOf(ref);
        n.parentNode = this;
        if (at < 0) this.children.push(n); else this.children.splice(at, 0, n);
        return n;
      },
      addEventListener(type, fn) { (this.__listeners[type] = this.__listeners[type] || []).push(fn); },
      dispatchEvent(type, key) {
        const ev = { target: this, key: key === undefined ? type : key };
        let n = this;
        while (n) { for (const fn of n.__listeners[type] || []) fn(ev); n = n.parentNode; }
        for (const fn of (docListeners[type] || [])) fn(ev);
      },
      closest(sel) {
        let n = this;
        while (n) { if (matches(n, sel)) return n; n = n.parentNode; }
        return null;
      },
    };
    let ownText = '';
    Object.defineProperty(el, 'textContent', {
      get() {
        return this.children.length > 0 ? this.children.map(c => c.textContent).join('') : ownText;
      },
      set(v) { ownText = String(v); this.children.length = 0; },
    });
    return el;
  }

  function matches(node, sel) {
    if (!node || !node.attrs) return false;
    const byId = /^#([A-Za-z0-9_-]+)$/.exec(sel);
    if (byId) return node.attrs.id === byId[1];
    const m = /^\[([^\]=]+)(?:="([^"]*)")?\]$/.exec(sel);
    if (!m) return false;
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
    defaultView: { console: { log() {} }, getComputedStyle: () => ({ getPropertyValue: () => '' }) },
  };

  function node(tag, id, attrs) {
    const n = withQuery(makeEl(tag));
    if (id) { n.setAttribute('id', id); registry.set(id, n); }
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  }

  for (const id of ['me2-rule-select', 'me2-table-select', 'me2-col-x', 'me2-col-y',
                    'me2-col-value', 'me2-reference-select']) {
    body.appendChild(node('select', id));
  }
  // 🔴 `me2-assume-accept` IS AUTHORED HERE, and that is not the same claim as the live page
  //    carrying it (it now does — the markup landed). This harness scores the WIRING: that the
  //    control sends the claim exactly once and is hidden the rest of the time. It does not and
  //    cannot score the page's markup; `bootstrap` reports any absence in `app.missing`, which
  //    the page entry logs. Keep the two apart — a stub that authors its own node will pass
  //    forever after someone deletes the button.
  for (const id of ['me2-columns-confirm', 'me2-assume-accept', 'me2-confirm-btn']) {
    body.appendChild(node('button', id));
  }
  for (const id of ['me2-workbench', 'me2-worklist-rows', 'me2-worklist-rows-unscorable',
                    'me2-worklist-search', 'me2-worklist-empty', 'me2-worklist-meta',
                    'me2-worklist-boundary', 'me2-worklist-boundary-label', 'me2-question-note',
                    'me2-badge-session', 'me2-badge-unscorable', 'me2-badge-remaining',
                    'me2-picture-svg', 'me2-layer-floor', 'me2-layer-miss', 'me2-layer-onlyone',
                    'me2-layer-alone', 'me2-picture-caption', 'me2-refusal',
                    'me2-verdict-headline', 'me2-source-list', 'me2-sources-meta',
                    'me2-metric-conflict', 'me2-confirm-sentence', 'me2-confirm-note',
                    'me2-confirm-hint', 'me2-export-btn', 'me2-paste-result']) {
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

  // The page publishes the source row inside a <template>; the shell clones it per map. Without
  // it no source row exists at all, and the per-map marker could not be scored.
  const tpl = node('template', 'me2-source-row-template');
  const tplRoot = withQuery(makeEl('div'));
  const row = node('button', null, { 'data-me2-source': '', 'data-source-field': '' });
  row.appendChild(node('span', null, { 'data-me2-source-value': '' }));
  row.appendChild(node('span', null, { 'data-me2-agree': '' }));
  row.appendChild(node('span', null, { 'data-me2-discriminating': '' }));
  tplRoot.appendChild(row);
  tplRoot.appendChild(node('div', null, { 'data-me2-candidates-for': '' }));
  tpl.content = { cloneNode: () => cloneOf(tplRoot) };
  body.appendChild(tpl);

  function cloneOf(src) {
    const copy = withQuery(makeEl(src.tagName));
    copy.attrs = { ...src.attrs };
    delete copy.attrs.id;
    for (const child of src.children) copy.appendChild(cloneOf(child));
    return copy;
  }

  return doc;
}
