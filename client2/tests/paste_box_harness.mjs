/**
 * Smart paste where a click cannot read the clipboard: the paste box (lead 4311a51ed, owner 09-30).
 *   B  the part: its own div, the caret in the zone and kept there (a press on the card, Tab),
 *      English words, a press and release on the scrim cancels and a click inside or a drag out
 *      does not, open replaces its own box, two instances do not interfere
 *   P  the REAL paste listener (clipboard.js): armed + a paste in the box reaches the smart paste
 *      reader and spends the arming; in a field it does not; unarmed it does not
 *   M  main.js (cannot be imported, it wires the page — this reads its text): the three no-read
 *      branches open the box, both ends of an arming close it
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, walk, byClass } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'paste_box.js');
const MAIN = path.join(HERE, '..', 'src', 'main.js');

// The page clipboard.js expects: one document (the stub the box draws into) whose listeners fire.
const doc = makeDoc('light');
const docListeners = new Map();
doc.addEventListener = (type, fn) => { (docListeners.get(type) || docListeners.set(type, []).get(type)).push(fn); };
doc.activeElement = doc.body;
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
};
const { state } = await import('../src/state.js');
const clipboard = await import('../src/clipboard.js');
clipboard.setupClipboardHandlers();
const heard = [];
clipboard.registerSmartPasteHandler((e) => heard.push(e));

let ran = 0;
let failedList = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failedList.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

const mountIn = () => { const host = doc.createElement('div'); doc.body.appendChild(host); return host; };
const paste = () => {
  // A real paste event fires at the focused element and bubbles to the document listener.
  let prevented = 0;
  const ev = { clipboardData: { types: [], getData: () => '' }, preventDefault() { prevented += 1; } };
  for (const fn of docListeners.get('paste') || []) fn({ ...ev, target: doc.activeElement, preventDefault: ev.preventDefault });
  return () => prevented;
};

async function suite(PasteBox, mainText) {
  console.log('\n-- B. the part --');
  const host = mountIn();
  const box = new PasteBox(host);
  let cancels = 0;
  const KEY = 'Ctrl+V';
  const zone = box.open({ onCancel: () => { cancels += 1; }, keyLabel: KEY });
  eq('B1 one own div under the mount, a dialog, no fixed id',
    `${host.children.length}|${host.children[0] && host.children[0].getAttribute('role')}|${walk(host).filter((n) => n.attrs && n.attrs.id).length}`,
    '1|dialog|0');
  eq('B2 the caret is in the zone, and the zone takes focus', `${doc.activeElement === zone}|${zone.getAttribute('tabindex')}`, 'true|0');
  const words = walk(host).map((n) => n._text || '').join(' ');
  ok('B3 English, and the zone names the key it is given', !/[ㄱ-힝]/.test(words) && zone.textContent.includes(KEY), words);
  const overlay = host.children[0];
  const card = byClass(host, 'pbx-card')[0];
  const press = (el) => { let stopped = 0; el.dispatch('mousedown', { preventDefault() { stopped += 1; } }); return stopped; };
  press(zone); zone.dispatch('click', {});
  press(card); card.dispatch('click', {});
  eq('B4a a click inside the card does not cancel', cancels, 0);
  press(zone); overlay.dispatch('click', {});
  eq('B4b a drag from the card out to the scrim does not cancel', cancels, 0);
  press(overlay); overlay.dispatch('click', {});
  eq('B4c a press and release on the scrim cancels, once', cancels, 1);
  eq('B4d a press on the card keeps the caret in the zone; a press on the zone is its own',
    `${press(byClass(host, 'ctm-title')[0])}|${press(zone)}`, '1|0');
  let tabbed = 0;
  zone.dispatch('keydown', { key: 'Tab', preventDefault() { tabbed += 1; } });
  eq('B7 Tab does not take the caret out of the box', tabbed, 1);
  box.open({ onCancel() {}, keyLabel: KEY });
  eq('B5a open again: still one box', host.children.length, 1);
  box.close(); box.close();
  eq('B5b close takes its own div, and twice is harmless', host.children.length, 0);
  const hostA = mountIn(); const hostB = mountIn();
  const a = new PasteBox(hostA); const b = new PasteBox(hostB);
  a.open({ onCancel() {}, keyLabel: 'Ctrl+V' }); b.open({ onCancel() {}, keyLabel: 'Ctrl+V' });
  a.close();
  eq('B6 two on one page: closing one leaves the other', `${hostA.children.length}|${hostB.children.length}`, '0|1');
  b.close();

  console.log('\n-- P. the real paste listener --');
  const armed = (on) => { state.smartPasteArmedUntil = on ? Date.now() + 60000 : 0; };
  heard.length = 0;
  const pbox = new PasteBox(mountIn());
  pbox.open({ onCancel() {}, keyLabel: 'Ctrl+V' });
  armed(true);
  const prevented = paste();
  eq('P1 armed, a paste in the box: the smart paste reader gets it, the arming is spent, the default is stopped',
    `${heard.length}|${state.smartPasteArmedUntil}|${prevented()}`, '1|0|1');
  heard.length = 0;
  const field = doc.createElement('input');
  doc.body.appendChild(field);
  field.focus();
  armed(true);
  paste();
  eq('P2 the same paste with the caret in a field: not the reader (why the zone is not a field)', heard.length, 0);
  pbox.open({ onCancel() {}, keyLabel: 'Ctrl+V' });
  armed(false);
  paste();
  eq('P3 the box without an arming: not the reader', heard.length, 0);
  pbox.close();
  state.smartPasteArmedUntil = 0;

  console.log('\n-- M. main.js --');
  const body = (name) => {
    const at = mainText.indexOf(`function ${name}(`);
    return at < 0 ? '' : mainText.slice(at, mainText.indexOf('\n}\n', at));
  };
  const via = body('smartPasteViaIngestion');
  eq('M1 the three branches that cannot read open the box, and nothing arms around it',
    `${(via.match(/openSmartPasteBox\(\);/g) || []).length}|${(via.match(/armSmartPaste\(/g) || []).length}`, '3|0');
  eq('M2 both ends of an arming close the box (cancel · the paste)',
    `${body('cancelSmartPasteArm').includes('closeSmartPasteBox();')}|${body('smartPasteFromPasteEvent').includes('closeSmartPasteBox();')}`,
    'true|true');
  return { ran, failed: failedList.slice() };
}

const mainText = () => readFileSync(MAIN, 'utf8').replace(/\r\n/g, '\n');
const load = async (mutate) => (await loadWithProbe(SUBJECT, mutate ? { mutate } : {})).module.PasteBox;

const MUTANTS = [
  { name: 'the-zone-is-a-field', catches: ['P1'],
    from: "const zone = this._el('div', 'pbx-zone',", to: "const zone = this._el('textarea', 'pbx-zone'," },
  { name: 'the-caret-is-not-put-in', catches: ['B2', 'P1'], from: '    zone.focus();\n', to: '\n' },
  { name: 'a-click-inside-cancels', catches: ['B4a'],
    from: '(e) => { if (pressedScrim && e.target === overlay) onCancel(); }', to: '() => onCancel()' },
  { name: 'a-drag-out-cancels', catches: ['B4b'], from: 'if (pressedScrim && e.target === overlay)', to: 'if (e.target === overlay)' },
  { name: 'a-card-press-blurs', catches: ['B4d'], from: '      if (e.target !== zone) e.preventDefault();\n', to: '\n' },
  { name: 'tab-leaves-the-box', catches: ['B7'], from: "if (e.key === 'Tab') e.preventDefault();", to: '' },
  { name: 'open-stacks-a-second-box', catches: ['B5a'], from: '  open({ onCancel, keyLabel }) {\n    this.close();\n', to: '  open({ onCancel, keyLabel }) {\n' },
  { name: 'main-cancel-leaves-the-box', catches: ['M2'], main: true,
    from: '  closeSmartPasteBox();\n  if (logText)', to: '  if (logText)' },
];

const main = async () => {
  console.log('== baseline ==');
  const result = await suite(await load(), mainText());
  const BASE_NAMES = NAMES.slice();
  console.log(`\n${result.ran - result.failed.length} passed, ${result.failed.length} failed.`);
  if (result.failed.length) { console.log(`ASSERTIONS ${result.ran} ${result.failed.length}`); process.exit(1); }
  const { wrong } = await scoreMutants(MUTANTS, async (m) => {
    const swap = (t) => { if (!t.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.name}`); return t.split(m.from).join(m.to); };
    let PasteBox, text;
    try {
      PasteBox = await load(m.main ? null : swap);
      text = m.main ? swap(mainText()) : mainText();
    } catch (err) { console.error(`HARNESS FAILURE: ${err.message}`); process.exit(2); }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { await suite(PasteBox, text); } finally { console.log = real; }
    return { failures: failedList, ran };
  }, { baselineRan: result.ran, baselineNames: BASE_NAMES,
       title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
  console.log(`\nASSERTIONS ${result.ran} ${result.failed.length}`);
  process.exit(wrong ? 1 : 0);
};

main();
