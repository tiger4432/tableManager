// PLACE UNDER — one function puts every panel a header control opens just under it and on screen (lead 10-09: the
// Replay chain dropdown opened away from its button after the header went to --header-zoom; the filter fold panel,
// the redo banner's panel and the column selector all go through `placeUnder` in dropdown.js).
//
//   P1 inside a parent drawn at 0.67 the panel lands just under its control, its right edge on the control's, on screen
//   P2 inside a parent at no zoom too; asked to, its left edge meets the control's
//   P3 a control near either edge of the window keeps the whole panel on screen
//   P4 a panel with no offset parent is placed against the page's body
//
// Every check reads where the panel lands ON SCREEN (the parent's left/top plus its px times its scale) - the question
// the operator asks - not the px written. Every defect below must be caught by the line it names.
//
// Run: node client2/tests/dropdown_place_harness.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'dropdown.js');
const VW = 1536;

const rect = (left, top, width, height) => ({ left, top, width, height, right: left + width, bottom: top + height });
/** A parent at `scale`: `width` css px drawn as width * scale on screen. */
const parentAt = (scale, left = 0, top = 0, width = 2290) =>
  ({ offsetWidth: width, getBoundingClientRect: () => rect(left, top, width * scale, 60 * scale) });
/** A panel `cssWidth` px wide inside `parent` (drawn at its scale), and where it lands on screen once placed. */
function panelIn(parent, cssWidth, scale) {
  const doc = { documentElement: { clientWidth: VW }, body: parentAt(1) };
  const panel = { ownerDocument: doc, offsetParent: parent, style: {},
    getBoundingClientRect: () => rect(0, 0, cssWidth * scale, 200 * scale) };
  const o = parent ? parent.getBoundingClientRect() : doc.body.getBoundingClientRect();
  const k = scale;
  panel.screen = () => ({ left: o.left + parseFloat(panel.style.left) * k, top: o.top + parseFloat(panel.style.top) * k,
    right: o.left + parseFloat(panel.style.left) * k + cssWidth * k });
  return panel;
}
const near = (a, b) => Math.abs(a - b) <= 1;

function suite(m) {
  const ran = [];
  const failures = [];
  const ok = (name, cond, detail) => { ran.push(name); if (!cond) failures.push(`${name}: ${detail}`); };

  const z = 0.67;
  const button = { getBoundingClientRect: () => rect(900, 20, 60, 24) };
  const inHeader = panelIn(parentAt(z, 0, 0), 300, z);
  m.placeUnder(inHeader, button);
  const s1 = inHeader.screen();
  ok('P1 inside a parent at 0.67: just under the control, right edges met, on screen',
    near(s1.top, 44 + 8) && near(s1.right, 960) && s1.left >= 8 && s1.right <= VW - 8,
    JSON.stringify({ s1, style: inHeader.style }));

  const plain = panelIn(parentAt(1, 0, 0, VW), 300, 1);
  m.placeUnder(plain, button);
  const leftMet = panelIn(parentAt(1, 0, 0, VW), 300, 1);
  m.placeUnder(leftMet, button, { align: 'left', gap: 6 });
  ok('P2 at no zoom the same; asked to, the left edges meet and the gap is the one asked',
    near(plain.screen().top, 52) && near(plain.screen().right, 960)
      && near(leftMet.screen().left, 900) && near(leftMet.screen().top, 44 + 6),
    JSON.stringify({ plain: plain.screen(), leftMet: leftMet.screen() }));

  const atRight = panelIn(parentAt(z, 0, 0), 400, z);
  m.placeUnder(atRight, { getBoundingClientRect: () => rect(1500, 20, 30, 24) }, { align: 'left' });
  const atLeft = panelIn(parentAt(z, 0, 0), 400, z);
  m.placeUnder(atLeft, { getBoundingClientRect: () => rect(10, 20, 30, 24) });
  ok('P3 a control near either edge keeps the whole panel on screen',
    atRight.screen().right <= VW - 8 + 1 && atLeft.screen().left >= 8 - 1,
    JSON.stringify({ right: atRight.screen(), left: atLeft.screen() }));

  const orphan = panelIn(null, 300, 1);
  m.placeUnder(orphan, button);
  ok('P4 with no offset parent the panel is placed against the body',
    near(orphan.screen().top, 52) && near(orphan.screen().right, 960), JSON.stringify(orphan.style));
  return { ran: ran.length, names: ran, failures };
}

const real = await import('../src/dropdown.js');
const base = suite(real);
console.log('-- place under ------------------------------------------------------');
for (const name of base.names) console.log(`  ${base.failures.some((f) => f.startsWith(name + ':')) ? 'FAIL' : 'PASS'} ${name}`);
base.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  // The lead's: the parent's scale left out.
  { id: 'DP1', what: 'screen distances are not divided by the parent\'s scale', catches: ['P1'],
    mutate: (t) => swap('  panel.style.left = `${Math.round(Math.max(least, Math.min(wanted, most)) / scale)}px`;',
      '  panel.style.left = `${Math.round(Math.max(least, Math.min(wanted, most)))}px`;')(
      swap('  panel.style.top = `${Math.round((a.bottom - o.top + gap) / scale)}px`;',
        '  panel.style.top = `${Math.round(a.bottom - o.top + gap)}px`;')(t)) },
  { id: 'DP2', what: 'the panel is not kept on screen', catches: ['P3'],
    mutate: swap('Math.max(least, Math.min(wanted, most))', 'wanted') },
  { id: 'DP3', what: 'the left edge is never met', catches: ['P2'],
    mutate: swap("const wanted = align === 'left' ? a.left - o.left : a.right - o.left - width;",
      'const wanted = a.right - o.left - width;') },
  { id: 'DP4', what: 'the gap asked is not the gap used', catches: ['P2'],
    mutate: swap("export function placeUnder(panel, anchor, { align = 'right', gap = GAP } = {}) {",
      "export function placeUnder(panel, anchor, { align = 'right' } = {}) {\n  const gap = GAP;") },
];
console.log('');
const { wrong } = await scoreMutants(MUTANTS, async (mu) => suite((await loadWithProbe(SUBJECT, { mutate: mu.mutate })).module),
  { baselineRan: base.ran, baselineNames: base.names, title: '-- defect mutants (each must be CAUGHT by its named line) -----------' });
const failed = base.failures.length + wrong;
console.log(`\n${base.ran - base.failures.length} passed, ${base.failures.length} failed; ${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
