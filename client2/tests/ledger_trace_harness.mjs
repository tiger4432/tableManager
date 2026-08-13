// Harness — the ledger lineage screen shows WHAT THE SERVER RESOLVED, and shows an assumption
// as an assumption.
// Run: node client2/tests/ledger_trace_harness.mjs
//
// WHAT IT DEFENDS. `GET /api/ledger/trace` answers with per-hop `state` + `reason`, and the
// screen exists so an operator can act on the difference between them. Three claims, and every
// one of them is invisible to an exit code and to a glance at the page:
//
//   P1  🔴 A HOP RESTING ON A DECLARED CONVENTION MUST NOT RENDER LIKE ONE RESTING ON A
//       MEASUREMENT. The server writes the distinction as `· convention:<name>` versus
//       `· basis=<name>` (`ledger_trace.py::_basis_label`), and the ontology owner ruled
//       (2026-08-13) that convention-backed atoms resolve at class 3 precisely so this
//       difference is visible. A screen that paints both the same throws the ruling away.
//
//   P2  UNRESOLVABLE IS CONTENT, NOT AN ERROR. `[no_claim]`, `[root]` and friends are the
//       product telling the truth about what nobody recorded. Rendering them as a failure, an
//       empty state, or a hidden row is the one forbidden answer (`trace()`: "빈 결과 금지").
//
//   P3  CANDIDATE MEANS SOMETHING DISAGREED, and the count is part of the statement.
//
//   P4  🔴 FOUR DIFFERENT NOTHINGS MUST READ AS FOUR DIFFERENT SENTENCES, AND THIS ONE IS A
//       MEASURED PRODUCT FAILURE, not a precaution. The product owner ran the shipped screen
//       against a database with no `ledger_events` table, got a blank, and said the boundary of
//       what can and cannot be found is too vague. Four unrelated situations painted that same
//       blank: the table was never migrated (DEPLOYMENT), the table is there and the backfill
//       never ran (OPERATIONS), the lot is not in the ledger (DATA BOUNDARY), and the lot is
//       registered with nobody claiming a parent (CONTENT).
//
//       🔴 TWO OF THEM ARE INDISTINGUISHABLE FROM THE TRACE ALONE, and `fixtures/
//       ledger_trace_nothings.json::unknown_lot` is the proof rather than the argument: with
//       zero atoms `ledger_trace.py`'s walk takes `cur_lot not in lots_with_atoms` for EVERY
//       lot, so an empty ledger answers `[unknown_subject] … 원장에 원자 0` — the same answer a
//       genuinely unknown lot gets on a full one. K5 and M3 score the SAME trace object under
//       two ledger states and demand two different screens. Only `GET /api/ledger/coverage`'s
//       `state` can separate them, which is why it is an argument and never an inference.
//
//       AND A REAL CHAIN IS NOT A NOTHING. `three_gen` walks three generations and ALSO
//       terminates `[root]`, so a rule keyed on the terminal tag alone calls a working answer
//       "혈통 주장 없음". K6/M5 pin it; mutant `no-lineage-claimed-on-a-real-root` proves they
//       can fail.
//
// 🔴 THE TRAP THAT MOTIVATES HALF THIS FILE, AND IT IS NOT HYPOTHETICAL — IT IS IN THE
//    FIXTURES. `_with_basis` APPENDS the WINNING claim's basis to the reason, but a `candidate`
//    reason also names the LOSERS' bases inline:
//
//      hop 1  `[candidate] … 하위 계급 반대 1종 (…-ZZ(convention:slot_preserving)) · 1순위 … · basis=pair_field`
//      hop 4  `[candidate] … 하위 계급 반대 1종 (…-QQ(convention:slot_preserving)) · 1순위 CL-2601-007-A2`
//
//    Both contain the substring `convention:`, and in BOTH the winner is a MEASUREMENT — the
//    assumption is the thing that was overruled. A `reason.includes('convention:')` check marks
//    both hops as assumption-backed, which is the exact inversion of what the screen is for.
//    Section C and G4 pin the anchored reading; mutant `basis-suffix-unanchored` proves they can
//    fail.
//
// THE FIXTURES ARE CAPTURES, NOT INVENTIONS. `fixtures/ledger_trace_live.json` is the answer the
// route gave for lot `CL-2601-007-A2-A6-A8` slot `02` on isolated `assy_qa` (878 real atoms).
// `fixtures/ledger_trace_probe.json` is the same query against a THROWAWAY COPY of that ledger
// (schema `ledger_probe`; `public` was never touched) with one `has_wafer` deleted and two
// convention-backed dissenting `derived_from` atoms added, so all three states and both suffix
// cases are real server output rather than a guess at the reason grammar.
//
// EVERY CHECK IS PAIRED WITH A MUTANT. The suite re-runs against deliberately defective copies
// of the two modules and FAILS if a defect still passes: a check that cannot fail proves
// nothing. Two CONTROL mutants (a private rename, and stripping comments) must ESCAPE — if a
// control is caught, some check is reading source text rather than behaviour. Every mutation
// asserts that it actually CHANGED the source, so a rename upstream turns this red instead of
// quietly scoring a pristine module eleven times.
//
// Exit codes: 0 = green | 1 = a check failed or a defect escaped | 2 = harness failure.
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const CORE_PATH = join(SRC, 'ledger_trace_core.js');
const VIEW_PATH = join(SRC, 'ledger_trace_view.js');
const ENTRY_PATH = join(SRC, 'ledger_trace.js');
const PAGE_PATH = join(HERE, '..', 'ledger.html');
const VITE_PATH = join(HERE, '..', 'vite.config.js');
const LIVE_PATH = join(HERE, 'fixtures', 'ledger_trace_live.json');
const PROBE_PATH = join(HERE, 'fixtures', 'ledger_trace_probe.json');
// P4's two fixtures. `ledger_trace_nothings.json` is REAL server output (`ledger_trace.trace()`
// called against isolated `assy_qa` over a read-only connection). `ledger_coverage.json` is the
// shape the lead PM pinned with its `ready` numbers MEASURED off that same ledger — it is not a
// capture, and says so in its own `_what`, because the route did not exist in `server/` when
// this was written. Section J scores the reading of that shape; if the shipped route differs,
// J goes red rather than the screen going quietly wrong.
const NOTHINGS_PATH = join(HERE, 'fixtures', 'ledger_trace_nothings.json');
const COVERAGE_PATH = join(HERE, 'fixtures', 'ledger_coverage.json');

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

for (const p of [CORE_PATH, VIEW_PATH, ENTRY_PATH, PAGE_PATH, VITE_PATH, LIVE_PATH, PROBE_PATH,
                 NOTHINGS_PATH, COVERAGE_PATH]) {
  if (!existsSync(p)) die(`missing ${p}`);
}

const CORE_PRISTINE = readFileSync(CORE_PATH, 'utf8');
const VIEW_PRISTINE = readFileSync(VIEW_PATH, 'utf8');
const ENTRY_SRC = readFileSync(ENTRY_PATH, 'utf8');
const PAGE_SRC = readFileSync(PAGE_PATH, 'utf8');
const VITE_SRC = readFileSync(VITE_PATH, 'utf8');
const LIVE = JSON.parse(readFileSync(LIVE_PATH, 'utf8'));
const PROBE = JSON.parse(readFileSync(PROBE_PATH, 'utf8'));
const NOTHINGS = JSON.parse(readFileSync(NOTHINGS_PATH, 'utf8'));
const COVERAGE = JSON.parse(readFileSync(COVERAGE_PATH, 'utf8'));

// The fixtures are load-bearing. A capture that stopped carrying the states this file scores
// would make every section below pass vacuously, so their SHAPE is asserted before anything
// else runs and a shortfall is a HARNESS FAILURE, not a red assertion.
{
  const states = (t) => t.hops.map((h) => h.state);
  if (LIVE.hops.length !== 11) die(`live fixture has ${LIVE.hops.length} hops, expected 11`);
  if (!states(PROBE).includes('candidate')) die('probe fixture carries no `candidate` hop');
  if (!states(PROBE).includes('unresolvable')) die('probe fixture carries no `unresolvable` hop');
  if (!states(PROBE).includes('resolved')) die('probe fixture carries no `resolved` hop');
  // The two suffix cases, by construction rather than by hope.
  const h1 = PROBE.hops[1].reason;
  const h4 = PROBE.hops[4].reason;
  if (!(h1.includes('convention:') && h1.endsWith('basis=pair_field'))) {
    die('probe hop 1 is no longer "winner has a basis, loser is a convention"');
  }
  if (!(h4.includes('convention:') && !/(convention:|basis=)[^\s·()]+$/.test(h4))) {
    die('probe hop 4 is no longer "winner has NO basis, loser is a convention" — '
      + 'the anchored-suffix trap is not in the fixture and section C would pass vacuously');
  }

  // ── P4's fixtures, same rule ──────────────────────────────────────────────────────
  // 🔴 THE PAIRING IS THE FIXTURE. `root_only` and `three_gen` must BOTH terminate `[root]`,
  // and only one of them may have walked anywhere. If that stops being true, K6/M5 stop
  // scoring the discrimination and start agreeing with a defect for free.
  const term = (t) => String((t && t.terminal_reason) || '');
  if (!term(NOTHINGS.root_only).startsWith('[root]')) {
    die('nothings fixture: `root_only` no longer terminates `[root]`');
  }
  if (!term(NOTHINGS.three_gen).startsWith('[root]')) {
    die('nothings fixture: `three_gen` no longer terminates `[root]` — it is here precisely '
      + 'because a REAL chain shares that tag with a lot nobody claimed a parent for');
  }
  if (NOTHINGS.root_only.hops.some((h) => h.predicate === 'derived_from' && h.state === 'resolved')) {
    die('nothings fixture: `root_only` resolved a parent — it is supposed to have none');
  }
  if (!NOTHINGS.three_gen.hops.some((h) => h.predicate === 'derived_from' && h.state === 'resolved')) {
    die('nothings fixture: `three_gen` resolved no parent — it is no longer a chain');
  }
  if (!term(NOTHINGS.unknown_lot).startsWith('[unknown_subject]')) {
    die('nothings fixture: `unknown_lot` no longer terminates `[unknown_subject]`');
  }
  // 🔴 AND THE ONE-HOP ANSWERS MUST BE THE SAME SHAPE. That identity is the defect: on an
  // empty ledger EVERY lot answers exactly like this. K5/M3 are about telling them apart
  // from OUTSIDE the trace, so the trace must genuinely be unable to.
  if (NOTHINGS.unknown_lot.hops.length !== 1) {
    die(`nothings fixture: \`unknown_lot\` has ${NOTHINGS.unknown_lot.hops.length} hops, expected 1`);
  }
  for (const state of ['ready', 'empty', 'absent']) {
    if (!COVERAGE[state] || COVERAGE[state].state !== state) {
      die(`coverage fixture has no \`${state}\` body carrying state="${state}"`);
    }
  }
  if (!(COVERAGE.ready.sample || []).length) {
    die('coverage fixture `ready` carries no sample — section L would score an empty list');
  }
}

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');

/** Import a (possibly mutated) pair of modules without writing into client2/src. */
async function load(coreSource, viewSource) {
  const coreUrl = `data:text/javascript;base64,${b64(coreSource)}`;
  const viewRewritten = viewSource.replaceAll("'./ledger_trace_core.js'", `'${coreUrl}'`);
  const [core, view] = await Promise.all([
    import(coreUrl),
    import(`data:text/javascript;base64,${b64(viewRewritten)}`),
  ]);
  return { core, view };
}

// ── the document stub ───────────────────────────────────────────────────────────────
// Just enough DOM for what the view uses, with REAL semantics for the two things that decide
// whether this harness can see anything: `textContent` concatenates descendants (so an
// assertion about "what reached the screen" is about the tree, not one node), and setting it
// CLEARS children (so a re-render that forgot to clear is visible).
//
// 🔴 A STUB THAT CANNOT SEE THE DEFECT IS THE DEFECT. That is not a worry, it is measured: the
//    mutant list below is applied to the real modules and driven through this stub, and every
//    one of them must be CAUGHT. A stub too inert to notice would show up as escapes.
function makeDoc() {
  return {
    createElement(tag) {
      return {
        tagName: String(tag).toUpperCase(),
        className: '',
        children: [],
        attrs: Object.create(null),
        _text: '',
        parentNode: null,
        appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
        removeChild(c) {
          const i = this.children.indexOf(c);
          if (i >= 0) this.children.splice(i, 1);
          c.parentNode = null;
          return c;
        },
        setAttribute(k, v) { this.attrs[String(k)] = String(v); },
        getAttribute(k) {
          return Object.prototype.hasOwnProperty.call(this.attrs, String(k))
            ? this.attrs[String(k)] : null;
        },
        get firstChild() { return this.children.length ? this.children[0] : null; },
        set textContent(v) { this._text = String(v); this.children.length = 0; },
        get textContent() {
          return this._text + this.children.map((c) => c.textContent).join('');
        },
      };
    },
  };
}

const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children) walk(c, out);
  return out;
};
// 🔴 TOLERANT ACCESSORS, ON PURPOSE. Several mutants below make an element DISAPPEAR, so the
// runs that must be scored are exactly the runs where `list[0]` is undefined — and a throw
// before the ASSERTIONS line reports to `check_harnesses.mjs` as DEAD, not as red. With these,
// a missing element fails the assertion that NAMES it instead of killing the file.
const NOTHING = { tagName: '', className: '', children: [], textContent: '', getAttribute: () => null };
const first = (list) => (list && list.length ? list[0] : NOTHING);
const at = (list, i) => (list && list[i] ? list[i] : NOTHING);
// The census reads TEXT, so it must read CODE. Every string it looks for is also written in
// the prose above it ("NEVER `new Date(iso).toLocaleString()`"), and a check that cannot tell
// the prohibition from its violation reports the file as violating itself — measured here on
// the first run, on both H8 and H9.
const stripComments = (s) => s
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n');
const classesOf = (n) => String(n.className || '').split(/\s+/).filter(Boolean);
const byClass = (root, cls) => walk(root).filter((n) => classesOf(n).includes(cls));
const byTag = (root, tag) => walk(root).filter((n) => n.tagName === String(tag).toUpperCase());
const byAttr = (root, k, v) => walk(root).filter((n) => n.getAttribute(k) === v);
const countOccurrences = (haystack, needle) => {
  if (!needle) return 0;
  let n = 0;
  let i = haystack.indexOf(needle);
  while (i !== -1) { n += 1; i = haystack.indexOf(needle, i + needle.length); }
  return n;
};

// ── the suite ───────────────────────────────────────────────────────────────────────
let quiet = false;

async function suite(coreSource, viewSource) {
  let pass = 0;
  const failed = [];
  const ok = (name, cond, detail) => {
    if (cond) { pass += 1; return; }
    failed.push(detail ? `${name} — ${detail}` : name);
  };
  const eq = (name, got, want) => ok(name, got === want, `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

  let core;
  let view;
  try {
    ({ core, view } = await load(coreSource, viewSource));
  } catch (e) {
    return { pass: 0, fail: 1, failed: [`modules did not load: ${e && e.message}`] };
  }

  // ── A. the one input box ──────────────────────────────────────────────────────────
  {
    const p = core.parseQuery;
    eq('A1 lot only / lot', p('CL-A').lot, 'CL-A');
    eq('A1b lot only / slot', p('CL-A').slot, null);
    eq('A2 slash form / lot', p('CL-A/02').lot, 'CL-A');
    eq('A2b slash form / slot', p('CL-A/02').slot, '02');
    eq('A3 space form / lot', p('CL-A 02').lot, 'CL-A');
    eq('A3b space form / slot', p('CL-A 02').slot, '02');
    eq('A4 padding trimmed / lot', p('   CL-A / 02   ').lot, 'CL-A');
    eq('A4b padding trimmed / slot', p('   CL-A / 02   ').slot, '02');
    eq('A5 empty / lot', p('').lot, '');
    eq('A5b empty / slot', p('').slot, null);
    eq('A5c null input', p(null).lot, '');
    // A leading slash is not a slot separator — "/02" is a lot with an odd name, and
    // guessing otherwise would send a lot the operator can see to a route that cannot find it.
    eq('A6 leading slash is not a split', p('/02').lot, '/02');
    eq('A6b leading slash keeps slot null', p('/02').slot, null);
    // Lot ids in this fab carry dashes, not slashes, but the LAST separator wins either way.
    eq('A7 last slash wins / lot', p('A/B/3').lot, 'A/B');
    eq('A7b last slash wins / slot', p('A/B/3').slot, '3');
    eq('A8 trailing separator leaves no slot', p('CL-A/').slot, null);
    eq('A9 query omits an absent slot', core.traceQuery({ lot: 'CL-A', slot: null }), 'lot=CL-A');
    eq('A10 query carries the slot', core.traceQuery({ lot: 'CL-A', slot: '02' }), 'lot=CL-A&slot=02');
    eq('A11 query escapes', core.traceQuery({ lot: 'a b&c', slot: '0/2' }), 'lot=a%20b%26c&slot=0%2F2');
    eq('A12 queryText round-trips the pair', core.queryText(p('CL-A/02')), 'CL-A/02');
    eq('A13 queryText of a bare lot', core.queryText({ lot: 'CL-A', slot: null }), 'CL-A');
  }

  // ── B. hop verdicts ───────────────────────────────────────────────────────────────
  {
    const v = core.hopVerdict;
    const hop = (state, reason, n) => ({ state, reason, n });
    eq('B1 resolved tone', v(hop('resolved', '[single] x')).tone, 'ok');
    eq('B1b resolved label', v(hop('resolved', '[single] x')).label, '확정');
    eq('B2 candidate tone', v(hop('candidate', '[candidate] x', 2)).tone, 'contested');
    // P3: the count is part of the statement. "이견" alone does not tell the operator
    // whether two things disagreed or five did.
    eq('B2b candidate label carries the count', v(hop('candidate', '[candidate] x', 2)).label, '이견 2종');
    eq('B2c candidate label at n=5', v(hop('candidate', '[candidate] x', 5)).label, '이견 5종');
    eq('B3 no_claim tone', v(hop('unresolvable', '[no_claim] x')).tone, 'gap');
    eq('B3b no_claim label', v(hop('unresolvable', '[no_claim] x')).label, '주장 없음');
    // P2: a root is the END of a recorded chain, not a hole in one.
    eq('B4 root tone', v(hop('unresolvable', '[root] x')).tone, 'end');
    eq('B4b root label', v(hop('unresolvable', '[root] x')).label, '뿌리');
    eq('B5 unknown_subject label', v(hop('unresolvable', '[unknown_subject] x')).label, '원장에 없음');
    eq('B6 no_slot_map label', v(hop('unresolvable', '[no_slot_map] x')).label, '대응 없음');
    eq('B7 unusable_payload label', v(hop('unresolvable', '[unusable_payload] x')).label, '답 없는 원자');
    eq('B8 unknown tag degrades', v(hop('unresolvable', '[brand_new] x')).label, '미해결');
    eq('B8b untagged reason degrades', v(hop('unresolvable', 'no tag here')).label, '미해결');
    // 🔴 A wire that grows a fifth state must not be able to paint itself confident.
    eq('B9 unknown state is never ok', v(hop('provisional', '[single] x')).tone, 'gap');
    eq('B9b absent state is never ok', v({}).tone, 'gap');
    eq('B10 candidate without n', v(hop('candidate', '[candidate] x', null)).label, '이견');
    eq('B11 terminal root', core.terminalVerdict('[root] lot=X · derived_from 주장 없음').label, '뿌리 도달');
    eq('B11b terminal root tone', core.terminalVerdict('[root] x').tone, 'end');
    eq('B12 terminal dead_end', core.terminalVerdict('[dead_end] x').label, '혈통 미상');
    eq('B13 terminal cycle', core.terminalVerdict('[cycle] x').label, '순환');
    eq('B14 terminal depth_cap', core.terminalVerdict('[depth_cap] x').tone, 'truncated');
    eq('B15 terminal unknown degrades', core.terminalVerdict('[brand_new] x').label, '중단');
  }

  // ── C. the basis suffix — P1, and the trap ────────────────────────────────────────
  {
    const b = core.hopBasis;
    const conv = b(LIVE.hops[2].reason);
    ok('C1 a convention hop is read as a convention', conv && conv.kind === 'convention',
      `got ${JSON.stringify(conv)}`);
    eq('C1b and names the derivation', conv && conv.name, 'slot_preserving');
    const meas = b(LIVE.hops[1].reason);
    ok('C2 a measured hop is read as a measurement', meas && meas.kind === 'basis',
      `got ${JSON.stringify(meas)}`);
    eq('C2b and names its derivation', meas && meas.name, 'pair_field');
    eq('C3 has_wafer basis', b(LIVE.hops[0].reason).name, 'positional_row');

    // 🔴 THE TRAP, BOTH DIRECTIONS, ON REAL SERVER OUTPUT.
    const trapA = b(PROBE.hops[1].reason);
    ok('C4 winner=measurement, loser=convention -> MEASUREMENT',
      trapA && trapA.kind === 'basis' && trapA.name === 'pair_field',
      `got ${JSON.stringify(trapA)} from ${JSON.stringify(PROBE.hops[1].reason)}`);
    const trapB = b(PROBE.hops[4].reason);
    ok('C5 winner=no basis, loser=convention -> NOTHING', trapB === null,
      `got ${JSON.stringify(trapB)} from ${JSON.stringify(PROBE.hops[4].reason)}`);

    eq('C6 a reason with no basis', b('[no_claim] has_wafer 원자 없음 · lot=X slot=2'), null);
    eq('C7 empty reason', b(''), null);
    eq('C8 null reason', b(null), null);
    const label = core.basisLabel({ kind: 'convention', name: 'slot_preserving' });
    eq('C9 convention label text', label.text, '가정 · slot_preserving');
    eq('C9b convention label kind', label.kind, 'convention');
    const mlabel = core.basisLabel({ kind: 'basis', name: 'pair_field' });
    eq('C10 measurement label text', mlabel.text, '근거 · pair_field');
    // The two labels must not be the same string with a different noun in front — they are the
    // whole of P1 in the vocabulary, so they are asserted apart explicitly.
    ok('C10b the two labels differ', label.text !== mlabel.text, 'assumption and basis read alike');
    eq('C11 no basis, no label', core.basisLabel(null), null);
    eq('C12 tag is read off the prefix', core.reasonTag('[class_wins] x'), 'class_wins');
    eq('C12b untagged', core.reasonTag('no tag'), null);
  }

  // ── D. answers and nodes ──────────────────────────────────────────────────────────
  {
    eq('D1 lot node with a slot', core.nodeText({ type: 'Lot', keys: { lot: 'CL-A' }, slot: '2' }),
      'CL-A · 슬롯 2');
    eq('D2 lot node without a slot', core.nodeText({ type: 'Lot', keys: { lot: 'CL-A' } }), 'CL-A');
    eq('D3 wafer node', core.nodeText({ type: 'Wafer', keys: { wafer: 'WF.01' } }), 'WF.01');
    eq('D4 absent node', core.nodeText(null), '—');
    eq('D5 has_wafer answer is the wafer', core.hopAnswer(LIVE.hops[0]), 'WF.010702');
    eq('D6 derived_from answer is the parent lot', core.hopAnswer(LIVE.hops[1]), 'CL-2601-007-A2-A6');
    // 🔴 slot_map asks WHERE, so the answer is a SLOT. Its `to` node is the parent lot carrying
    // that slot, and rendering the node there answers a question nobody asked.
    eq('D7 slot_map answer is a slot', core.hopAnswer(LIVE.hops[2]), '슬롯 2');
    eq('D7b slot_map keeps the parent lot as context',
      core.hopAnswerContext(LIVE.hops[2]), 'CL-2601-007-A2-A6');
    eq('D7c a non-slot_map hop has no context', core.hopAnswerContext(LIVE.hops[1]), null);
    eq('D8 an unanswered hop', core.hopAnswer(LIVE.hops[9]), null);
    eq('D9 has_wafer question', core.hopQuestion({ predicate: 'has_wafer' }), '이 자리의 웨이퍼는?');
    eq('D10 derived_from question', core.hopQuestion({ predicate: 'derived_from' }), '이 랏의 부모 랏은?');
    eq('D11 slot_map question', core.hopQuestion({ predicate: 'slot_map' }), '부모 랏에서 이 자리는?');
    eq('D12 register question', core.hopQuestion({ predicate: 'register' }), '원장이 이 랏을 아는가?');
    ok('D13 an unknown predicate still says something',
      typeof core.hopQuestion({ predicate: 'brand_new' }) === 'string'
      && core.hopQuestion({ predicate: 'brand_new' }).includes('brand_new'));
  }

  // ── E. the declared zone survives the client ──────────────────────────────────────
  {
    const t = core.instantText;
    eq('E1 T becomes a space', t('2026-05-03T18:16:00+09:00'), '2026-05-03 18:16:00+09:00');
    eq('E2 sub-second noise is dropped, offset kept',
      t('2026-08-13T14:47:38.983888+09:00'), '2026-08-13 14:47:38+09:00');
    eq('E3 a negative offset survives', t('2026-05-03T04:34:00-05:00'), '2026-05-03 04:34:00-05:00');
    eq('E4 Z survives', t('2026-05-03T04:34:00Z'), '2026-05-03 04:34:00Z');
    eq('E5 absent instant', t(null), '');
    // 🔴 THE ONE THAT MATTERS. `ledger_trace.py` renders in a DECLARED zone so a fab record
    // reads the same everywhere; `new Date(iso).toLocaleString()` here would silently re-render
    // it in the viewer's machine zone AND drop the offset, so nothing on screen would admit it.
    ok('E6 the offset is still on screen', /[+\-]\d{2}:\d{2}$|Z$/.test(t(LIVE.hops[0].occurred_at)),
      `got ${JSON.stringify(t(LIVE.hops[0].occurred_at))}`);
    ok('E7 the clock is not moved', t(LIVE.hops[0].occurred_at).includes('18:16:00'),
      `got ${JSON.stringify(t(LIVE.hops[0].occurred_at))} from ${LIVE.hops[0].occurred_at}`);
  }

  // ── F. the summary ────────────────────────────────────────────────────────────────
  {
    const live = core.summarize(LIVE);
    eq('F1 live total', live.total, 11);
    eq('F2 live resolved', live.resolved, 9);
    eq('F3 live unresolvable', live.unresolvable, 2);
    eq('F4 live candidate', live.candidate, 0);
    eq('F5 live conventions', live.convention, 3);
    eq('F6 live distinct lots', live.lots, 4);

    const probe = core.summarize(PROBE);
    eq('F7 probe candidate', probe.candidate, 2);
    eq('F8 probe unresolvable', probe.unresolvable, 3);
    // 🔴 THE TRAP AT THE SUMMARY LEVEL. Five of the eleven probe hops contain the substring
    // `convention:`; only THREE of them rest on one. A count that says 5 tells the operator
    // that two measured hops are assumptions.
    eq('F9 probe conventions counted at the WINNER', probe.convention, 3);
    eq('F10 an empty trace summarises to zero', core.summarize({ hops: [] }).total, 0);
    eq('F11 a malformed trace does not throw', core.summarize(null).total, 0);
  }

  // ── G. what actually reaches the screen ───────────────────────────────────────────
  {
    const doc = makeDoc();
    const mount = doc.createElement('div');
    view.renderTrace(doc, mount, LIVE, 'CL-2601-007-A2-A6-A8 · 슬롯 2');

    const items = byTag(mount, 'LI');
    eq('G1 one row per hop', items.length, LIVE.hops.length);
    ok('G2 each row carries the server state verbatim',
      items.every((li, i) => li.getAttribute('data-state') === LIVE.hops[i].state),
      items.map((li) => li.getAttribute('data-state')).join(','));
    ok('G2b each row carries the predicate',
      items.every((li, i) => li.getAttribute('data-predicate') === LIVE.hops[i].predicate));

    // P1 on screen: the three convention hops are marked, and marked DIFFERENTLY from the rest.
    const conventionRows = items.filter((li) => li.getAttribute('data-basis') === 'convention');
    eq('G3 three rows are marked as assumptions', conventionRows.length, 3);
    ok('G3b the marked rows are the slot_map ones',
      conventionRows.every((li) => li.getAttribute('data-predicate') === 'slot_map'));
    ok('G3c the mark is also a class, so it can look different',
      conventionRows.every((li) => classesOf(li).includes('lt-hop--convention')));
    ok('G3d a measured row is NOT marked',
      !classesOf(at(items, 1)).includes('lt-hop--convention'));
    eq('G3e a measured row says so', at(items, 1).getAttribute('data-basis'), 'basis');
    eq('G3f a basis-less row says that too', at(items, 9).getAttribute('data-basis'), 'none');
    const chips = byClass(mount, 'lt-basis');
    ok('G3g 가정 and 근거 chips are different elements',
      chips.some((c) => c.getAttribute('data-basis-kind') === 'convention')
      && chips.some((c) => c.getAttribute('data-basis-kind') === 'basis'));
    ok('G3h the assumption chip says 가정',
      first(byAttr(mount, 'data-basis-kind', 'convention')).textContent.startsWith('가정'));

    // P2 on screen.
    ok('G4 an unresolvable row is not an error tone',
      at(items, 9).getAttribute('data-tone') === 'gap',
      at(items, 9).getAttribute('data-tone'));
    eq('G4b the root row is an ENDING, not a hole', at(items, 10).getAttribute('data-tone'), 'end');
    ok('G4c no row anywhere is toned as an error',
      items.every((li) => li.getAttribute('data-tone') !== 'error'));
    ok('G4d the gap row still names its kind',
      first(byClass(at(items, 9), 'lt-badge')).textContent === '주장 없음');

    // 🔴 THE SERVER'S SENTENCE, VERBATIM AND EXACTLY ONCE. It is the only place the operator
    // learns WHY, and a paraphrase here is a second explanation that drifts from the resolver.
    const screen = mount.textContent;
    ok('G5 every reason is on screen',
      LIVE.hops.every((h) => screen.includes(h.reason)),
      LIVE.hops.filter((h) => !screen.includes(h.reason)).map((h) => h.reason).join(' | '));
    ok('G5b and each one exactly once in ITS OWN row',
      items.every((li, i) => countOccurrences(li.textContent, LIVE.hops[i].reason) === 1),
      'a reason was dropped from or doubled inside its row');
    ok('G6 the terminal reason is on screen once',
      countOccurrences(first(byClass(mount, 'lt-terminal')).textContent, LIVE.terminal_reason) === 1);
    eq('G6b the terminal block carries its tone',
      first(byClass(mount, 'lt-terminal')).getAttribute('data-terminal-tone'), 'end');

    ok('G7 the answers are on screen',
      screen.includes('WF.010702') && screen.includes('CL-2601-007-A2-A6'));
    ok('G8 the instant is on screen with its offset', screen.includes('2026-05-03 18:16:00+09:00'));
    ok('G9 the subject line is on screen', screen.includes('CL-2601-007-A2-A6-A8 · 슬롯 2'));
    ok('G10 the assumption count is a chip', byAttr(mount, 'data-chip', 'convention').length === 1
      && first(byAttr(mount, 'data-chip', 'convention')).textContent === '가정 3');
    eq('G10b no 이견 chip when nothing disagreed', byAttr(mount, 'data-chip', 'contested').length, 0);

    // ── the probe answer: candidate, and the trap on screen ────────────────────────
    const doc2 = makeDoc();
    const mount2 = doc2.createElement('div');
    view.renderTrace(doc2, mount2, PROBE, 'probe');
    const items2 = byTag(mount2, 'LI');
    eq('G11 probe rows', items2.length, 11);
    eq('G11b the candidate row is toned contested', at(items2, 1).getAttribute('data-tone'), 'contested');
    ok('G11c and says how many disagreed',
      first(byClass(at(items2, 1), 'lt-badge')).textContent === '이견 2종',
      first(byClass(at(items2, 1), 'lt-badge')).textContent);
    // 🔴 G12 IS THE TRAP ON SCREEN. Both candidate rows contain the word `convention:` in their
    // reason and NEITHER rests on one. A screen that marks them is telling the operator that a
    // measurement is an assumption — the inversion, not merely a miss.
    ok('G12 a contested row whose WINNER is measured is not marked as an assumption',
      !classesOf(at(items2, 1)).includes('lt-hop--convention'),
      'the overruled assumption was attributed to the winner');
    ok('G12b same when the winner has no basis at all',
      !classesOf(at(items2, 4)).includes('lt-hop--convention'));
    eq('G12c and the summary chip agrees',
      first(byAttr(mount2, 'data-chip', 'convention')).textContent, '가정 3');
    eq('G12d the 이견 chip appears', first(byAttr(mount2, 'data-chip', 'contested')).textContent, '이견 2');

    // P2 in its strongest form: an answer that is entirely gaps is still an ANSWER.
    const allGaps = {
      hops: PROBE.hops.filter((h) => h.state === 'unresolvable'),
      terminal_reason: PROBE.terminal_reason,
      generated_at: PROBE.generated_at,
    };
    const doc3 = makeDoc();
    const mount3 = doc3.createElement('div');
    view.renderTrace(doc3, mount3, allGaps, 'all gaps');
    eq('G13 an all-unresolvable answer still renders every hop',
      byTag(mount3, 'LI').length, allGaps.hops.length);
    eq('G13b and is still an answer, not a notice',
      first(byClass(mount3, 'lt-answer')).getAttribute('data-answer-kind'), 'trace');

    // Re-rendering must REPLACE, not accumulate — the screen answers one question at a time.
    view.renderTrace(doc3, mount3, LIVE, 'second question');
    eq('G14 a second answer replaces the first', byClass(mount3, 'lt-answer').length, 1);
    eq('G14b with the second question\'s rows', byTag(mount3, 'LI').length, LIVE.hops.length);
    ok('G14c and none of the first answer left behind',
      !mount3.textContent.includes('all gaps'));

    // A lot id is DATA. Nothing here builds markup out of it.
    const nasty = JSON.parse(JSON.stringify(LIVE));
    nasty.hops[0].from.keys.lot = '<img src=x onerror=1>';
    const doc4 = makeDoc();
    const mount4 = doc4.createElement('div');
    view.renderTrace(doc4, mount4, nasty, 'x');
    ok('G15 a lot id reaches the screen as text',
      mount4.textContent.includes('<img src=x onerror=1>'));

    // The notice states — not answers, and they must not look like one.
    const doc5 = makeDoc();
    const mount5 = doc5.createElement('div');
    view.renderTrace(doc5, mount5, LIVE, 'x');
    view.renderNotice(doc5, mount5, { tone: 'error', title: '서버 거절 (503)', detail: '<<detail>>' });
    eq('G16 a notice replaces the answer', byClass(mount5, 'lt-answer').length, 0);
    ok('G16b the server sentence is verbatim', mount5.textContent.includes('<<detail>>'));
    eq('G16c and is marked as a notice',
      first(byClass(mount5, 'lt-notice')).getAttribute('data-answer-kind'), 'notice');
  }

  // ── J. reading the coverage answer — "what can I ask" ─────────────────────────────
  {
    const cs = core.coverageState;
    eq('J1 ready', cs(COVERAGE.ready), 'ready');
    eq('J2 empty', cs(COVERAGE.empty), 'empty');
    eq('J3 absent', cs(COVERAGE.absent), 'absent');
    // 🔴 Same rule as `hopVerdict`'s default branch, for the same reason: 'ready' is the one
    // value that makes the screen say "ask me anything". A wire that grows a fourth state — or
    // a server too old to carry this route — must not be able to claim it.
    eq('J4 an unknown state degrades', cs({ state: 'brand_new' }), 'unknown');
    eq('J5 no body degrades', cs(null), 'unknown');
    eq('J6 a body with no state degrades', cs({ lots: 25 }), 'unknown');

    const ready = core.coverageVerdict(COVERAGE.ready);
    const absent = core.coverageVerdict(COVERAGE.absent);
    const empty = core.coverageVerdict(COVERAGE.empty);
    eq('J7 ready asks the operator for a question', ready.title, '무엇을 물을 수 있나');
    eq('J8 absent names the deployment', absent.title, '원장이 이 DB에 설치되지 않았습니다');
    eq('J8b and points at the runbook', absent.detail, '마이그레이션 미실행 · 런북 6항');
    eq('J9 empty names the backfill', empty.title, '원장이 비어 있습니다 — 백필 미실행');
    // 🔴 THE PRODUCT COMPLAINT, AS ONE ASSERTION. On the shipped screen these three were the
    // same blank. If any two of them read alike here, this round did nothing.
    ok('J10 the three states say three different things',
      new Set([ready.title, absent.title, empty.title]).size === 3,
      `${ready.title} | ${absent.title} | ${empty.title}`);
    const unknown = core.coverageVerdict(null);
    eq('J11 an unreachable coverage falls back to the old hint', unknown.title, '랏을 입력하세요');
    // It must not diagnose a box it never reached. 'idle' is the tone that claims nothing.
    eq('J11b and claims nothing about the ledger', unknown.tone, 'idle');

    const facts = core.coverageFacts(COVERAGE.ready);
    eq('J12 the lot count', facts.lots, 25);
    eq('J13 the sources', facts.sources.join(','), 'lot_event');
    // The declared zone survives here exactly as it does in a hop (section E).
    eq('J14 the range keeps its offset', facts.from, '2026-05-03 02:17:00+09:00');
    eq('J14b both ends', facts.to, '2026-05-21 20:33:00+09:00');
    // 🔴 A COUNT NOBODY SENT IS NOT A MEASURED ZERO. "0 lots" means the backfill has not run;
    // an absent field means nothing was reported, and printing the second as the first states
    // a fact nobody established.
    eq('J15 an absent count is null', core.coverageFacts({ state: 'ready' }).lots, null);
    eq('J15b a real zero survives', core.coverageFacts({ lots: 0 }).lots, 0);
    eq('J16 no sources is an empty list', core.coverageFacts(null).sources.length, 0);
    eq('J16b junk in the source list is dropped',
      core.coverageFacts({ sources: ['a', null, ''] }).sources.join(','), 'a');
    eq('J17 no range', core.coverageFacts(null).from, null);

    const samples = core.coverageSamples(COVERAGE.ready);
    eq('J18 every sample survives', samples.length, COVERAGE.ready.sample.length);
    // A sample IS the question, spelled by the same two functions Enter uses — so a sample
    // cannot drift from what the one input box sends.
    eq('J19 a sample with a slot reads as it would be typed', samples[0].text, 'CL-2601-006-A1-A7/04');
    eq('J19b and its query carries the slot', samples[0].query, 'lot=CL-2601-006-A1-A7&slot=04');
    eq('J20 a bare lot keeps no slot', samples[1].query, 'lot=CL-2601-006-A1');
    eq('J20b nor in its text', samples[1].text, 'CL-2601-006-A1');
    eq('J21 malformed entries are dropped, not rendered as blanks',
      core.coverageSamples({ sample: [null, {}, { lot: '' }, { lot: 'X' }] }).length, 1);
    eq('J22 no sample list at all', core.coverageSamples(null).length, 0);

    // ── the refusal, read structurally ──────────────────────────────────────────────
    // `COVERAGE.refusal_absent` is the real 503 body, captured off the live route.
    const rr = core.refusalReading;
    const absentRefusal = rr(COVERAGE.refusal_absent, 503);
    eq('J23 the refusal carries its own state', absentRefusal.state, 'absent');
    // 🔴 AND THE OPERATOR GETS THE SENTENCE, NOT THE BLOB. `message` is written for a human;
    // dumping the whole JSON is how a refusal becomes unreadable at the moment it matters.
    eq('J23b and the server sentence is what is shown',
      absentRefusal.text, COVERAGE.refusal_absent.message);
    ok('J23c not the JSON blob', !absentRefusal.text.startsWith('{'), absentRefusal.text);
    // 🔴 J24 IS THE PROHIBITION THE BRIEF SPELLED OUT. The state comes from the STRUCTURED
    // field; a reading that infers it from the sentence says "absent" about a box that told it
    // "ready". `message` is prose the server lane may reword at any time.
    eq('J24 the sentence does not decide the state',
      rr({ state: 'ready', message: '원장 테이블 ledger_events 없음' }, 503).state, 'ready');
    eq('J25 an older server sends a bare string', rr('해결기 config 거절: x', 503).state, 'unknown');
    eq('J25b and it is shown verbatim', rr('해결기 config 거절: x', 503).text, '해결기 config 거절: x');
    eq('J26 an object with no state degrades', rr({ message: 'x' }, 503).state, 'unknown');
    eq('J26b an unrecognised state degrades', rr({ state: 'brand_new' }, 503).state, 'unknown');
    eq('J27 an object with no message still shows something', rr({ state: 'absent' }, 503).text,
      '{"state":"absent"}');
    eq('J28 no detail at all falls back to the status', rr(null, 503).text, 'HTTP 503');
    eq('J28b and claims no state', rr(null, 503).state, 'unknown');
  }

  // ── K. WHICH nothing — P4 ─────────────────────────────────────────────────────────
  {
    const nv = core.nothingVerdict;
    // 🔴 TOLERANT, FOR THE SAME REASON AS `first`/`at` ABOVE, AND IT IS MEASURED. Several of
    // the mutants below make `nothingVerdict` return NULL where a verdict is due, so a bare
    // `nv(...).kind` throws — and a throw aborts the whole suite, scoring the mutant "caught"
    // by an exception while the assertions that were supposed to name it never run. Both
    // `nothing-ignores-the-ledger-state` and `lineage-step-counts-any-hop` did exactly that on
    // the first run of this section. With these, each one fails the assertion that NAMES it.
    const kindOf = (v) => (v && v.kind !== undefined ? v.kind : '(no verdict)');
    const titleOf = (v) => (v && v.title !== undefined ? v.title : '(no verdict)');

    eq('K1 absent is a deployment fact', kindOf(nv(null, 'absent')), 'ledger_absent');
    eq('K1b in the words the operator needs',
      titleOf(nv(null, 'absent')), '원장이 이 DB에 설치되지 않았습니다');
    eq('K2 empty is an operations fact',
      kindOf(nv(NOTHINGS.unknown_lot, 'empty')), 'ledger_empty');
    eq('K2b in its own words',
      titleOf(nv(NOTHINGS.unknown_lot, 'empty')), '원장이 비어 있습니다 — 백필 미실행');

    const unk = nv(NOTHINGS.unknown_lot, 'ready');
    eq('K3 an unknown lot is a data boundary', kindOf(unk), 'unknown_lot');
    // 🔴 NAMED, AND DELIBERATELY SILENT. The gap hop and the terminal block already say this
    // lot is not in the ledger; a headline repeating it is a second sentence about one fact,
    // which is what "UI 단순성" costs when nobody counts it.
    eq('K3b and adds no second sentence', titleOf(unk), null);

    const root = nv(NOTHINGS.root_only, 'ready');
    eq('K4 a registered lot with no parent claim', kindOf(root), 'no_lineage_claim');
    eq('K4b says so', titleOf(root), '등재됐으나 혈통 주장 없음');

    // 🔴 K5 IS THE MEASURED DEFECT. The SAME trace object. On a ready ledger it means "that lot
    // is not here"; on an empty one it means "nothing is here, the backfill never ran". The
    // shipped screen could not tell an operator which, and that is the report this round answers.
    ok('K5 one trace, two ledgers, two answers',
      kindOf(nv(NOTHINGS.unknown_lot, 'ready')) !== kindOf(nv(NOTHINGS.unknown_lot, 'empty')),
      'an empty ledger and an unknown lot still read the same');
    // 🔴 K6 IS THE OTHER HALF. `three_gen` walked three generations and ALSO terminates
    // `[root]`. A rule keyed on the terminal tag alone tells the operator that a working answer
    // has no lineage — the inversion again, not merely a miss.
    eq('K6 a real chain is not a nothing', nv(NOTHINGS.three_gen, 'ready'), null);

    // 🔴 THE TAG DECIDES, NEVER THE SENTENCE. Same tag, completely different prose -> same
    // verdict; and prose that reads like ANOTHER tag must not win. `[root]`'s real sentence
    // already contains 없음 and `[unknown_subject]`'s contains 원자 0, so a substring reader
    // has two ways to be wrong here.
    const reworded = { hops: NOTHINGS.root_only.hops, terminal_reason: '[root] 완전히 다른 문장' };
    eq('K7 rewording the sentence does not change the verdict',
      kindOf(nv(reworded, 'ready')), 'no_lineage_claim');
    const trap = {
      hops: NOTHINGS.root_only.hops,
      terminal_reason: '[root] lot=X · 원장에 원자 0 처럼 읽히는 문장',
    };
    eq('K7b prose that reads like another tag does not win',
      kindOf(nv(trap, 'ready')), 'no_lineage_claim');

    eq('K8 an untagged terminal is not a nothing',
      nv({ hops: [], terminal_reason: 'no tag here' }, 'ready'), null);
    // With no coverage route the trace-side nothings still work — the screen degrades, it does
    // not go blind.
    eq('K9 an unknown ledger state still reads the trace',
      kindOf(nv(NOTHINGS.root_only, 'unknown')), 'no_lineage_claim');
    eq('K9b a null state does not throw', kindOf(nv(NOTHINGS.unknown_lot, null)), 'unknown_lot');
    eq('K10 a malformed trace does not throw', nv(null, 'ready'), null);
  }

  // ── L. the empty state on screen — requirement 1 ──────────────────────────────────
  {
    const doc = makeDoc();
    const mount = doc.createElement('div');
    view.renderCoverage(doc, mount, COVERAGE.ready);
    const wrap = first(byClass(mount, 'lt-coverage'));
    eq('L1 the empty state is not an answer', wrap.getAttribute('data-answer-kind'), 'coverage');
    eq('L1b and says which ledger state it is', wrap.getAttribute('data-coverage-state'), 'ready');

    const screen = mount.textContent;
    ok('L2 how many lots are traceable', screen.includes('25'), screen);
    ok('L3 from which sources', screen.includes('lot_event'));
    ok('L4 over what range, with its offset', screen.includes('2026-05-03 02:17:00+09:00'));

    const links = byTag(mount, 'A');
    eq('L5 every sample is a link', links.length, COVERAGE.ready.sample.length);
    eq('L5b and the link IS the question',
      first(links).getAttribute('href'), '?lot=CL-2601-006-A1-A7&slot=04');
    eq('L5c reading as the operator would type it', first(links).textContent, 'CL-2601-006-A1-A7/04');
    eq('L6 a bare-lot sample', at(links, 1).getAttribute('href'), '?lot=CL-2601-006-A1');
    // 🔴 THE COMPLEXITY BUDGET, ON THE RENDERED DOM RATHER THAN THE PAGE SOURCE. Coverage is
    // CONTENT in the state that was already there. An anchor is not a control: the answer to
    // this screen is a URL, so a sample is that answer already written down.
    eq('L7 no input was added', byTag(mount, 'INPUT').length, 0);
    eq('L7b no button was added', byTag(mount, 'BUTTON').length, 0);

    const doc2 = makeDoc();
    const m2 = doc2.createElement('div');
    view.renderCoverage(doc2, m2, COVERAGE.absent);
    ok('L8 absent says the deployment sentence',
      m2.textContent.includes('원장이 이 DB에 설치되지 않았습니다'), m2.textContent);
    ok('L8b and points at the runbook', m2.textContent.includes('런북 6항'));
    eq('L8c and offers nothing to click', byTag(m2, 'A').length, 0);
    eq('L8d and is marked absent',
      first(byClass(m2, 'lt-coverage')).getAttribute('data-coverage-state'), 'absent');
    // 🔴 NO FABRICATED MEASUREMENT. There is no ledger to count, so no count is printed. A
    // "추적 가능한 랏 0" here would be a measurement of a table that does not exist.
    ok('L8e and counts nothing', !m2.textContent.includes('추적 가능한 랏'), m2.textContent);

    const doc3 = makeDoc();
    const m3 = doc3.createElement('div');
    view.renderCoverage(doc3, m3, COVERAGE.empty);
    ok('L9 empty says the backfill sentence', m3.textContent.includes('백필 미실행'), m3.textContent);
    ok('L9b and the two do not read alike', m2.textContent !== m3.textContent);

    const doc4 = makeDoc();
    const m4 = doc4.createElement('div');
    view.renderCoverage(doc4, m4, null);
    ok('L10 an unreachable coverage falls back to the shipped hint',
      m4.textContent.includes('랏을 입력하세요'), m4.textContent);
    eq('L10b and diagnoses nothing',
      first(byClass(m4, 'lt-coverage')).getAttribute('data-coverage-state'), 'unknown');
    eq('L10c and offers no samples it does not have', byTag(m4, 'A').length, 0);

    view.renderCoverage(doc4, m4, COVERAGE.ready);
    eq('L11 a second render replaces the first', byClass(m4, 'lt-coverage').length, 1);
    ok('L11b with nothing of the first left', !m4.textContent.includes('랏을 입력하세요'));

    // A lot id out of the ledger is DATA here too.
    const doc5 = makeDoc();
    const m5 = doc5.createElement('div');
    view.renderCoverage(doc5, m5, { state: 'ready', lots: 1, sources: [], sample: [{ lot: '<b>x</b>' }] });
    ok('L12 a sample lot reaches the screen as text', m5.textContent.includes('<b>x</b>'));
  }

  // ── M. the nothing, on the answer — requirement 2 ─────────────────────────────────
  {
    const doc = makeDoc();
    const mount = doc.createElement('div');
    view.renderTrace(doc, mount, NOTHINGS.unknown_lot, 'x',
      core.nothingVerdict(NOTHINGS.unknown_lot, 'empty'));
    const box = first(byClass(mount, 'lt-nothing'));
    eq('M1 an empty ledger is named on the answer', box.getAttribute('data-nothing'), 'ledger_empty');
    ok('M1b in words', box.textContent.includes('원장이 비어 있습니다 — 백필 미실행'), box.textContent);
    // The headline is ADDED, never substituted. The hops are still the answer.
    eq('M1c the answer is still an answer', byTag(mount, 'LI').length, 1);
    eq('M1d and still a trace',
      first(byClass(mount, 'lt-answer')).getAttribute('data-answer-kind'), 'trace');
    ok('M1e with the server sentence still verbatim',
      mount.textContent.includes(NOTHINGS.unknown_lot.hops[0].reason));

    const doc2 = makeDoc();
    const m2 = doc2.createElement('div');
    view.renderTrace(doc2, m2, NOTHINGS.unknown_lot, 'x',
      core.nothingVerdict(NOTHINGS.unknown_lot, 'ready'));
    eq('M2 an unknown lot on a ready ledger adds no headline',
      byClass(m2, 'lt-nothing').length, 0);
    ok('M2b because the gap rendering already names it',
      m2.textContent.includes('원장에 없는 랏'), m2.textContent);
    // 🔴 M3 IS K5 ON SCREEN. Same fixture, same renderer, two ledgers — two screens.
    ok('M3 the two screens differ', m2.textContent !== mount.textContent,
      'an empty ledger and an unknown lot still render identically');

    const doc3 = makeDoc();
    const m3 = doc3.createElement('div');
    view.renderTrace(doc3, m3, NOTHINGS.root_only, 'x',
      core.nothingVerdict(NOTHINGS.root_only, 'ready'));
    ok('M4 a registered lot with no parent claim says so',
      m3.textContent.includes('등재됐으나 혈통 주장 없음'), m3.textContent);
    eq('M4b and is named for the DOM',
      first(byClass(m3, 'lt-nothing')).getAttribute('data-nothing'), 'no_lineage_claim');

    const doc4 = makeDoc();
    const m4 = doc4.createElement('div');
    view.renderTrace(doc4, m4, NOTHINGS.three_gen, 'x',
      core.nothingVerdict(NOTHINGS.three_gen, 'ready'));
    eq('M5 a working chain carries no nothing headline', byClass(m4, 'lt-nothing').length, 0);
    eq('M5b and renders its whole chain', byTag(m4, 'LI').length, NOTHINGS.three_gen.hops.length);

    // Omitting the verdict is the pre-P4 call shape (section G) and must stay silent.
    const doc5 = makeDoc();
    const m5 = doc5.createElement('div');
    view.renderTrace(doc5, m5, LIVE, 'x');
    eq('M6 no verdict, no headline', byClass(m5, 'lt-nothing').length, 0);

    view.renderTrace(doc3, m3, LIVE, 'x');
    eq('M7 a second answer drops the previous headline', byClass(m3, 'lt-nothing').length, 0);
  }

  return { pass, fail: failed.length, failed };
}

// ── the wiring census — the page entry cannot be imported under bare node ───────────
// Without this the two modules above could be perfect and unused. It reads TEXT, so it is the
// one section the control mutants must not disturb (they only touch core/view).
function census() {
  let pass = 0;
  const failed = [];
  const ok = (name, cond, detail) => {
    if (cond) { pass += 1; return; }
    failed.push(detail ? `${name} — ${detail}` : name);
  };

  ok('H1 the entry imports the core', ENTRY_SRC.includes("from './ledger_trace_core.js'"));
  ok('H2 the entry imports the view', ENTRY_SRC.includes("from './ledger_trace_view.js'"));
  ok('H3 the entry calls the pinned route', ENTRY_SRC.includes('/api/ledger/trace?'));
  ok('H4 the entry renders through the view',
    ENTRY_SRC.includes('renderTrace(') && ENTRY_SRC.includes('renderNotice('));
  // 🔴 THE SESSION GUARD, COUNTED. Two questions in flight resolve in arrival order, and a
  // check at only the first await passes every test that does not stall the body. The
  // suspension points are fetch, refusal body, json body, and — since P4 — the coverage body
  // on all three of the empty / refusal / answer paths. Raised 4 -> 8 with those: a coverage
  // response landing after the operator has moved on would repaint a stale screen just as a
  // stale trace would.
  ok('H5 the session guard is checked after every await',
    countOccurrences(ENTRY_SRC, 'mine !== session') >= 8,
    `found ${countOccurrences(ENTRY_SRC, 'mine !== session')}`);
  // 🔴 READ-ONLY. This screen issues one GET and the route writes nothing.
  ok('H6 the entry issues no write', !/method\s*:\s*['"](POST|PUT|PATCH|DELETE)/i.test(ENTRY_SRC));
  // `change` also fires on BLUR, so binding it would re-ask a question the operator did not
  // ask again — the same trap the map editor's confirm control paid for.
  ok('H7 the input commits on keydown only',
    ENTRY_SRC.includes("addEventListener('keydown'") && !ENTRY_SRC.includes("addEventListener('change'"));
  // The zone ruling, enforced across all three modules at once.
  ok('H8 nothing re-localises the server instants',
    !/toLocale(Date|Time)?String/.test(stripComments(ENTRY_SRC + CORE_PRISTINE + VIEW_PRISTINE)));
  ok('H9 the view never builds markup from data',
    !/innerHTML|outerHTML|insertAdjacentHTML/.test(stripComments(VIEW_PRISTINE)));
  ok('H10 the page declares the hooks the entry reads',
    PAGE_SRC.includes('id="lt-query"') && PAGE_SRC.includes('id="lt-result"'));
  ok('H11 the page loads the entry', PAGE_SRC.includes('/src/ledger_trace.js'));
  // "Landed is not wired": an entry nobody builds is a file, not a screen.
  ok('H12 the page is a build entry', /ledger:\s*resolve\(__dirname, 'ledger\.html'\)/.test(VITE_SRC));
  // 🔴 COMPLEXITY BUDGET, ASSERTED. The screen is one question and one answer: exactly one
  // form control on the page, no modal, no second mode. A later round that grows a filter bar
  // goes red here and has to argue for it.
  const controls = (PAGE_SRC.match(/<(input|select|textarea)\b/gi) || []).length;
  ok('H13 the page carries exactly one input', controls === 1, `found ${controls}`);
  const buttons = (PAGE_SRC.match(/<button\b/gi) || []).length;
  ok('H14 and no buttons at all', buttons === 0, `found ${buttons}`);
  // P4's wiring. The reading of coverage could be perfect and never asked for.
  ok('H15 the entry asks the coverage route', ENTRY_SRC.includes('/api/ledger/coverage'));
  ok('H16 the empty state goes through the view', ENTRY_SRC.includes('renderCoverage('));
  ok('H17 and the answer is told WHICH nothing it is', ENTRY_SRC.includes('nothingVerdict('));
  // The refusal's reading lives in the core, where the harness can score it (section J23-J28).
  // Re-deriving it in the entry would put an unmeasurable branch on the path that runs when
  // the ledger is not deployed — the exact path the product owner was on.
  ok('H17b the refusal is read by the core', ENTRY_SRC.includes('refusalReading('));
  // 🔴 STILL READ-ONLY, AND NOW OVER TWO ROUTES. `/coverage` is a GET like `/trace`, and H6
  // above already forbids a method on either — this pins that the second route did not arrive
  // with a write path of its own.
  ok('H18 the coverage call is a bare GET',
    /fetch\(`\$\{API_BASE\}\/api\/ledger\/coverage`\)/.test(ENTRY_SRC));
  // The four sentences live in the CORE, where the harness can score them, not in the entry —
  // which is text-only here and would make them unmeasurable.
  ok('H19 the four sentences are not composed in the entry',
    !ENTRY_SRC.includes('원장이 이 DB에 설치되지 않았습니다')
    && !ENTRY_SRC.includes('등재됐으나 혈통 주장 없음'));

  return { pass, fail: failed.length, failed };
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
// `[target, name, mutate]` — `mutate` returns the new source and MUST change it.
const CORE = 'core';
const VIEW = 'view';

const DEFECTS = [
  // The trap, from the front: an anywhere-match reads the overruled assumption as the winner's.
  [CORE, 'basis-suffix-unanchored',
    (s) => s.replace('/\\s·\\s(convention:|basis=)([^\\s·()]+)$/', '/(convention:|basis=)([^\\s·()]+)/')],
  [CORE, 'basis-kind-collapsed',
    (s) => s.replace("kind: m[1] === 'convention:' ? 'convention' : 'basis'", "kind: 'basis'")],
  [CORE, 'assumption-labelled-like-a-measurement',
    (s) => s.replace('? { text: `가정 · ${basis.name}`, kind: \'convention\' }',
      '? { text: `근거 · ${basis.name}`, kind: \'convention\' }')],
  [CORE, 'unknown-state-reads-confident',
    (s) => s.replace("tone: 'gap',\n    label: (tag && GAP_LABEL[tag]) || '미해결',",
      "tone: 'ok',\n    label: (tag && GAP_LABEL[tag]) || '미해결',")],
  [CORE, 'root-is-a-hole',
    (s) => s.replace("if (tag === 'root') return { state: 'unresolvable', tag, tone: 'end', label: '뿌리' };", '')],
  [CORE, 'candidate-loses-its-count',
    (s) => s.replace('label: Number.isFinite(n) && n > 1 ? `이견 ${n}종` : \'이견\',', "label: '이견',")],
  [CORE, 'slot_map-answers-with-a-lot',
    (s) => s.replace("if (predicate === 'slot_map') {", "if (false) {")],
  [CORE, 'instant-drops-its-offset',
    (s) => s.replace('return `${date} ${rest}`;', 'return `${date} ${rest.slice(0, 8)}`;')],
  [CORE, 'summary-counts-any-basis-as-an-assumption',
    (s) => s.replace("if (basis && basis.kind === 'convention') out.convention += 1;",
      'if (basis) out.convention += 1;')],
  [CORE, 'gap-labels-collapse',
    (s) => s.replace("label: (tag && GAP_LABEL[tag]) || '미해결',", "label: '미해결',")],
  [VIEW, 'assumption-mark-dropped',
    (s) => s.replace("item.setAttribute('data-basis', isConvention ? 'convention' : (basis ? 'basis' : 'none'));",
      "item.setAttribute('data-basis', basis ? 'basis' : 'none');")],
  [VIEW, 'assumption-class-dropped',
    (s) => s.replace("${isConvention ? ' lt-hop--convention' : ''}", '')],
  [VIEW, 'every-row-marked-as-an-assumption',
    (s) => s.replace("${isConvention ? ' lt-hop--convention' : ''}", ' lt-hop--convention')],
  [VIEW, 'reason-paraphrased',
    (s) => s.replace("body.appendChild(el(doc, 'p', 'lt-hop__reason', String((hop && hop.reason) || '')));",
      "body.appendChild(el(doc, 'p', 'lt-hop__reason', '판정 근거 확인 필요'));")],
  [VIEW, 'gap-rows-hidden',
    (s) => s.replace('hops.forEach((hop, i) => chain.appendChild(renderHop(doc, hop, i + 1)));',
      "hops.filter((h) => h.state !== 'unresolvable').forEach((hop, i) => chain.appendChild(renderHop(doc, hop, i + 1)));")],
  [VIEW, 'gap-rows-toned-as-errors',
    (s) => s.replace("item.setAttribute('data-tone', verdict.tone);",
      "item.setAttribute('data-tone', verdict.state === 'unresolvable' ? 'error' : verdict.tone);")],
  [VIEW, 'terminal-block-dropped',
    (s) => s.replace('wrap.appendChild(renderTerminal(doc, trace));', '')],
  [VIEW, 'assumption-chip-dropped',
    (s) => s.replace("if (s.convention > 0) chip('convention', `가정 ${s.convention}`);", '')],
  [VIEW, 're-render-accumulates',
    (s) => s.replace('  clear(mount);\n  const wrap', '  const wrap')],
  [VIEW, 'state-hook-invented',
    (s) => s.replace("item.setAttribute('data-state', verdict.state);",
      "item.setAttribute('data-state', 'resolved');")],
  [VIEW, 'answer-built-as-markup',
    (s) => s.replace("if (text !== undefined && text !== null) node.textContent = String(text);", '')],

  // ── P4: the four nothings ─────────────────────────────────────────────────────────
  // 🔴 THE ONE THAT SHIPPED. `nothingVerdict` stops consulting the ledger state, so an empty
  //    ledger reads exactly like an unknown lot — the screen the product owner used.
  [CORE, 'nothing-ignores-the-ledger-state',
    (s) => s.replace("const state = ledgerState == null ? 'unknown' : String(ledgerState);",
      "const state = 'unknown';")],
  // 🔴 THE INVERSION ON THIS AXIS. Keyed on the terminal tag alone, a chain that really walked
  //    three generations is announced as having no lineage.
  [CORE, 'no-lineage-claimed-on-a-real-root',
    (s) => s.replace("if (tag === 'root' && !hasLineageStep(trace)) {", "if (tag === 'root') {")],
  [CORE, 'lineage-step-counts-any-hop',
    (s) => s.replace("h.predicate === 'derived_from' && h.state === 'resolved'", '!!h')],
  [CORE, 'coverage-unknown-state-reads-ready',
    (s) => s.replace("return COVERAGE_STATES.has(s) ? s : 'unknown';", "return s || 'ready';")],
  [CORE, 'absent-and-empty-collapse',
    (s) => s.replaceAll("title: '원장이 비어 있습니다 — 백필 미실행',",
      "title: '원장이 이 DB에 설치되지 않았습니다',")],
  [CORE, 'unknown-lot-repeats-what-the-hops-said',
    (s) => s.replace("return { kind: 'unknown_lot', tone: 'gap', title: null, detail: null };",
      "return { kind: 'unknown_lot', tone: 'gap', title: '원장에 없는 랏', detail: null };")],
  // 🔴 THE PROSE PARSER, AS A MUTANT. It passes the real captured refusal (whose sentence does
  //    contain 없음) and lies about every other one — the shape of defect this screen has
  //    already paid for once on the convention/measurement axis.
  [CORE, 'refusal-state-read-from-the-sentence',
    (s) => s.replace('return { state: coverageState(detail), text: message };',
      "return { state: String(detail.message || '').includes('없음') ? 'absent' : 'unknown', text: message };")],
  [CORE, 'refusal-state-ignored',
    (s) => s.replace('return { state: coverageState(detail), text: message };',
      "return { state: 'unknown', text: message };")],
  [CORE, 'refusal-shows-the-blob-not-the-sentence',
    (s) => s.replace("? detail.message : JSON.stringify(detail);", '? JSON.stringify(detail) : JSON.stringify(detail);')],
  [CORE, 'coverage-count-fakes-a-zero',
    (s) => s.replace('lots: Number.isFinite(lots) ? lots : null,',
      'lots: Number.isFinite(lots) ? lots : 0,')],
  [CORE, 'samples-drop-the-slot',
    (s) => s.replace('out.push({ lot, slot, text: queryText({ lot, slot }), query: traceQuery({ lot, slot }) });',
      'out.push({ lot, slot, text: queryText({ lot, slot: null }), query: traceQuery({ lot, slot: null }) });')],
  [VIEW, 'coverage-renders-as-an-answer',
    (s) => s.replace("wrap.setAttribute('data-answer-kind', 'coverage');",
      "wrap.setAttribute('data-answer-kind', 'trace');")],
  [VIEW, 'samples-are-not-links',
    (s) => s.replace("const a = el(doc, 'a', 'lt-samples__link', s.text);",
      "const a = el(doc, 'span', 'lt-samples__link', s.text);")],
  [VIEW, 'sample-links-lose-their-question',
    (s) => s.replace('a.setAttribute(\'href\', `?${s.query}`);', "a.setAttribute('href', '?');")],
  [VIEW, 'coverage-samples-dropped', (s) => s.replace('if (samples.length) {', 'if (false) {')],
  [VIEW, 'coverage-count-dropped',
    (s) => s.replace("if (facts.lots !== null) fact('lots', '추적 가능한 랏', `${facts.lots}`);", '')],
  // An absent ledger has nothing to count, so a count printed there is a measurement of a
  // table that does not exist.
  [VIEW, 'a-broken-ledger-reports-measurements',
    (s) => s.replace("if (verdict.state === 'ready') {", 'if (true) {')],
  [VIEW, 'coverage-re-render-accumulates',
    (s) => s.replace('  clear(mount);\n  const verdict = coverageVerdict(coverage);',
      '  const verdict = coverageVerdict(coverage);')],
  [VIEW, 'nothing-headline-dropped',
    (s) => s.replace('if (nothing && nothing.title) {', 'if (false) {')],
  [VIEW, 'nothing-headline-loses-its-kind',
    (s) => s.replace("box.setAttribute('data-nothing', String(nothing.kind || ''));",
      "box.setAttribute('data-nothing', 'gap');")],
];

// Must ESCAPE. If one is caught, a check is reading source text instead of behaviour.
const CONTROLS = [
  [CORE, 'control:private-rename', (s) => s.replaceAll('TAG_RE', 'TAG_PATTERN')],
  [VIEW, 'control:comments-stripped',
    (s) => s.split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n')],
];

// ── run ─────────────────────────────────────────────────────────────────────────────
console.log('── ledger lineage screen ─────────────────────────────────────────');
const base = await suite(CORE_PRISTINE, VIEW_PRISTINE);
const wiring = census();
for (const f of base.failed) console.log(`  ✗ ${f}`);
for (const f of wiring.failed) console.log(`  ✗ ${f}`);
console.log(`  ${base.pass + wiring.pass} passed, ${base.fail + wiring.fail} failed`);

async function runMutant(target, mutate) {
  const core = target === CORE ? mutate(CORE_PRISTINE) : CORE_PRISTINE;
  const view = target === VIEW ? mutate(VIEW_PRISTINE) : VIEW_PRISTINE;
  if (target === CORE && core === CORE_PRISTINE) return { unchanged: true };
  if (target === VIEW && view === VIEW_PRISTINE) return { unchanged: true };
  try { return await suite(core, view); }
  catch (e) { return { pass: 0, fail: 1, failed: [`threw: ${e && e.message}`] }; }
}

let caught = 0;
const escapedNames = [];
console.log('\n── defect mutants (each must be CAUGHT) ──────────────────────────');
for (const [target, name, mutate] of DEFECTS) {
  const r = await runMutant(target, mutate);
  // 🔴 A mutation that did not apply scores a PRISTINE module and reports "caught: no". A
  // rename upstream must turn this file red, not quietly retire its corpus.
  if (r.unchanged) die(`mutant \`${name}\` did not change the ${target} source — its anchor moved`);
  if (r.fail > 0) { caught += 1; console.log(`  caught  ${name}  (${r.failed[0]})`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
const controlsCaughtNames = [];
console.log('\n── control mutants (each must ESCAPE) ────────────────────────────');
for (const [target, name, mutate] of CONTROLS) {
  const r = await runMutant(target, mutate);
  if (r.unchanged) die(`control \`${name}\` did not change the ${target} source — its anchor moved`);
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else {
    controlsCaught += 1;
    controlsCaughtNames.push(`${name} (${r.failed[0]})`);
    console.log(`  CAUGHT  ${name}  (${r.failed[0]})`);
  }
}

if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);
if (controlsCaughtNames.length) {
  console.error(`\ncontrols that were caught (a check is reading source text):\n  `
    + controlsCaughtNames.join('\n  '));
}

const bad = base.fail + wiring.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass + wiring.pass} passed, ${base.fail + wiring.fail} failed; `
  + `${caught}/${DEFECTS.length} defects caught, ${escapedNames.length} escaped; `
  + `${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash. The
// mutants are counted as assertions so a corpus that stops being applied SINKS `ran` and blocks.
const ran = base.pass + base.fail + wiring.pass + wiring.fail + DEFECTS.length + CONTROLS.length;
const failedTotal = base.fail + wiring.fail + escapedNames.length + controlsCaught;
console.log(`ASSERTIONS ${ran} ${failedTotal}`);
process.exit(bad ? 1 : 0);
