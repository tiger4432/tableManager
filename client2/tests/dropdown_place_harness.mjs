// PLACE UNDER — one function puts every panel a header control opens just under it, at the page's own size, on screen
// (lead 10-09: Replay chain's opened away from its button after the header went to --header-zoom; owner 10-09: the
// panels under the header's buttons came out narrower and their rows broke in two). `placeUnder` in dropdown.js.
//
//   P1 a panel opened inside the header moves to the body and lands just under its control, right edges met
//   P2 asked to, its left edge meets the control's, with the gap asked
//   P3 a control near either edge of the window keeps the whole panel on screen
//   P4 the moved panel is still its origin's: a click on it is inside for watchForDismiss, a click elsewhere closes
//   P5 a document with no layout (a node stub) leaves the panel where it is
//   P6 a panel that does not fit under its control at the foot of the window opens above it (lead 72b2d7f8f)
//   P7 neither side holds it: it goes to the roomier side, cut to that height with its own scroll - below here
//   P8 ... and above when above is roomier, from the window's margin
//   P9 opened again where it fits, the cut is gone
//   R1 fitUnder places a panel where it stands - not moved to the body (the slot picker, the start picker)
//
// Positions are screen px (`position: fixed`), so the check reads the px written. Every defect below must be caught by
// the line it names.
//
// Run: node client2/tests/dropdown_place_harness.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'dropdown.js');
const VW = 1536;
const VH = 864;

const rect = (left, top, width, height) => ({ left, top, width, height, right: left + width, bottom: top + height });
function page() {
  const listeners = {};
  const body = { appendChild(el) { el.parentNode = body; } };
  return { body, documentElement: { clientWidth: VW }, listeners,
    addEventListener: (t, f) => { listeners[t] = f; }, removeEventListener: (t) => { delete listeners[t]; } };
}
/** A panel `width` px wide opened inside `header` - where placeUnder finds it. */
const panelIn = (doc, header, width) => ({ ownerDocument: doc, parentNode: header, style: {},
  getBoundingClientRect: () => rect(0, 0, width, 200) });
const near = (a, b) => Math.abs(a - b) <= 1;
const px = (v) => parseFloat(v);

function suite(m) {
  const ran = [];
  const failures = [];
  const ok = (name, cond, detail) => { ran.push(name); if (!cond) failures.push(`${name}: ${detail}`); };

  const button = { getBoundingClientRect: () => rect(900, 20, 60, 24) };
  const doc = page();
  const header = { parentNode: null };
  const p1 = panelIn(doc, header, 300);
  m.placeUnder(p1, button);
  ok('P1 a panel opened in the header moves to the body, just under its control, right edges met',
    p1.parentNode === doc.body && p1.style.position === 'fixed' && near(px(p1.style.top), 44 + 8)
      && near(px(p1.style.left) + 300, 960), JSON.stringify({ parent: p1.parentNode === doc.body, style: p1.style }));

  const p2 = panelIn(doc, header, 300);
  m.placeUnder(p2, button, { align: 'left', gap: 6 });
  ok('P2 asked to, the left edges meet and the gap is the one asked',
    near(px(p2.style.left), 900) && near(px(p2.style.top), 44 + 6), JSON.stringify(p2.style));

  const atRight = panelIn(doc, header, 400);
  m.placeUnder(atRight, { getBoundingClientRect: () => rect(1500, 20, 30, 24) }, { align: 'left' });
  const atLeft = panelIn(doc, header, 400);
  m.placeUnder(atLeft, { getBoundingClientRect: () => rect(10, 20, 30, 24) });
  ok('P3 a control near either edge keeps the whole panel on screen',
    px(atRight.style.left) + 400 <= VW - 8 + 1 && px(atLeft.style.left) >= 8 - 1,
    JSON.stringify({ right: atRight.style, left: atLeft.style }));

  let closed = 0;
  const host = { parentNode: null };
  const fold = panelIn(doc, host, 300);
  const row = { parentNode: fold };
  m.watchForDismiss(doc, host, () => { closed += 1; });
  m.placeUnder(fold, button);
  doc.listeners.mousedown({ target: row });
  const inside = closed;
  doc.listeners.mousedown({ target: { parentNode: doc.body } });
  ok('P4 the moved panel is still its origin\'s: a click on it is inside, a click elsewhere closes',
    fold.parentNode === doc.body && fold.placedFrom === host && inside === 0 && closed === 1, JSON.stringify({ inside, closed }));

  const stub = { ownerDocument: { documentElement: { clientWidth: VW } }, parentNode: header, style: {} };
  m.placeUnder(stub, button);
  ok('P5 a document with no layout leaves the panel where it is', stub.parentNode === header && !stub.style.top,
    JSON.stringify(stub));

  // A window with a height (lead 72b2d7f8f, owner 10-13: the X axis picker opened under a pill at the foot of the page).
  const tall = { ...page(), documentElement: { clientWidth: VW, clientHeight: VH } };
  const sized = (height) => { const p = { ownerDocument: tall, parentNode: header, style: {}, height };
    p.getBoundingClientRect = () => rect(0, 0, 300, p.height); return p; };
  const at = (top) => ({ getBoundingClientRect: () => rect(100, top, 60, 24) });
  const foot = sized(300);
  m.fitUnder(foot, at(800), { align: 'left' });
  ok('P6 at the foot of the window a panel opens above its control, uncut', near(px(foot.style.top), 800 - 8 - 300) && !foot.style.maxHeight,
    JSON.stringify(foot.style));
  const huge = sized(900);
  m.fitUnder(huge, at(400), { align: 'left' });
  ok('P7 neither side holds it: under the control (the roomier side here), cut to the room left, its own scroll',
    near(px(huge.style.top), 424 + 8) && near(px(huge.style.maxHeight), VH - 8 - 432) && huge.style.overflowY === 'auto',
    JSON.stringify(huge.style));
  const high = sized(900);
  m.fitUnder(high, at(600), { align: 'left' });
  ok('P8 ... above when above is roomier, from the window\'s margin to the control',
    near(px(high.style.top), 8) && near(px(high.style.maxHeight), 600 - 8 - 8) && high.style.overflowY === 'auto',
    JSON.stringify(high.style));
  huge.height = 100;
  m.fitUnder(huge, at(400), { align: 'left' });
  ok('P9 opened again where it fits, the cut is gone', !huge.style.maxHeight && !huge.style.overflowY && near(px(huge.style.top), 432),
    JSON.stringify(huge.style));
  ok('R1 fitUnder places the panel where it stands - not moved to the body', foot.parentNode === header && foot.style.position === 'fixed',
    String(foot.parentNode === header));
  return { ran: ran.length, names: ran, failures };
}

const real = await import('../src/dropdown.js');
const base = suite(real);
console.log('-- place under ------------------------------------------------------');
for (const name of base.names) console.log(`  ${base.failures.some((f) => f.startsWith(name + ':')) ? 'FAIL' : 'PASS'} ${name}`);
base.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  // The owner's: the panel left where it was opened - inside the zoomed header.
  { id: 'DP1', what: 'the panel stays where it was opened', catches: ['P1'],
    mutate: swap('    doc.body.appendChild(panel);\n', '') },
  { id: 'DP2', what: 'the panel is not kept on screen', catches: ['P3'],
    mutate: swap('Math.max(MARGIN, Math.min(wanted, vw - MARGIN - width))', 'wanted') },
  { id: 'DP3', what: 'the left edge is never met', catches: ['P2'],
    mutate: swap("const wanted = align === 'left' ? a.left : a.right - width;", 'const wanted = a.right - width;') },
  { id: 'DP4', what: 'the gap asked is not the gap used', catches: ['P2'],
    mutate: swap('  let top = a.bottom + gap;', '  let top = a.bottom + GAP;') },
  // ── the one placement (lead 72b2d7f8f) ──
  { id: 'DP6', what: 'a panel at the foot of the window never flips - the owner\'s X axis picker off the screen', catches: ['P6'],
    mutate: swap('if (height <= above) top = a.top - gap - height;', 'if (false) top = a.top - gap - height;') },
  { id: 'DP7', what: 'a panel taller than the room is not cut', catches: ['P7', 'P8'],
    mutate: swap("      panel.style.maxHeight = `${Math.floor(Math.max(above, below))}px`;\n", '') },
  { id: 'DP8', what: 'cut under the control though above is roomier', catches: ['P8'],
    mutate: swap('if (above > below) top = MARGIN;', 'if (false) top = MARGIN;') },
  { id: 'DP9', what: 'a cut stays when the panel fits again', catches: ['P9'],
    mutate: swap("  panel.style.maxHeight = '';\n  panel.style.overflowY = '';\n", '') },
  { id: 'DP10', what: 'fitUnder moves the panel to the body too', catches: ['R1'],
    mutate: swap("  panel.style.position = 'fixed';\n  panel.style.right = 'auto';", "  doc.body.appendChild(panel);\n  panel.style.position = 'fixed';\n  panel.style.right = 'auto';") },
  { id: 'DP5', what: 'a click on a moved panel reads as outside', catches: ['P4'],
    mutate: swap('node = node.placedFrom || node.parentNode;', 'node = node.parentNode;') },
];
console.log('');
const { wrong } = await scoreMutants(MUTANTS, async (mu) => suite((await loadWithProbe(SUBJECT, { mutate: mu.mutate })).module),
  { baselineRan: base.ran, baselineNames: base.names, title: '-- defect mutants (each must be CAUGHT by its named line) -----------' });
const failed = base.failures.length + wrong;
console.log(`\n${base.ran - base.failures.length} passed, ${base.failures.length} failed; ${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
