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

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

for (const p of [CORE_PATH, VIEW_PATH, ENTRY_PATH, PAGE_PATH, VITE_PATH, LIVE_PATH, PROBE_PATH]) {
  if (!existsSync(p)) die(`missing ${p}`);
}

const CORE_PRISTINE = readFileSync(CORE_PATH, 'utf8');
const VIEW_PRISTINE = readFileSync(VIEW_PATH, 'utf8');
const ENTRY_SRC = readFileSync(ENTRY_PATH, 'utf8');
const PAGE_SRC = readFileSync(PAGE_PATH, 'utf8');
const VITE_SRC = readFileSync(VITE_PATH, 'utf8');
const LIVE = JSON.parse(readFileSync(LIVE_PATH, 'utf8'));
const PROBE = JSON.parse(readFileSync(PROBE_PATH, 'utf8'));

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
  // check at only the first await passes every test that does not stall the body. There are
  // three suspension points on the happy-and-refusal paths (fetch, refusal body, json body).
  ok('H5 the session guard is checked after every await',
    countOccurrences(ENTRY_SRC, 'mine !== session') >= 4,
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
