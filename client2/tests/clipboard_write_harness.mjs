// CLIPBOARD WRITE - the one writer that works on plain HTTP, scored as it ships (lead 72aa14785).
//
// 🔴 WHY THIS FILE EXISTS. `writeClipboardRich` moved out of map_editor.js so the table registry's
//    Copy columns could call it. The map harnesses REPLACE that name and the table harness injects its
//    own writer, so nothing ran the function itself: a mutation of it was green everywhere.
//    Here it is imported and run against a document whose `execCommand('copy')` fires the copy
//    listeners, as the browser does - what lands on the clipboard is read off that event.
//
// Run: node client2/tests/clipboard_write_harness.mjs
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'clipboard_write.js');

/** A document and window just big enough for the writer, recording what the copy event was given. */
function world({ execReturns = true, clipboard = true } = {}) {
  const listeners = [];
  const set = {};
  const restored = [];
  const body = { children: [], appendChild(n) { this.children.push(n); return n; } };
  const doc = {
    body,
    activeElement: body,
    createElement: (tag) => {
      const node = { tag, attrs: {}, style: {}, textContent: '',
        setAttribute(k, v) { this.attrs[k] = v; },
        focus() { doc.activeElement = node; },
        remove() { body.children = body.children.filter((c) => c !== node); } };
      return node;
    },
    createRange: () => ({ selectNodeContents() {} }),
    addEventListener: (type, fn) => { if (type === 'copy') listeners.push(fn); },
    removeEventListener: (type, fn) => { const at = listeners.indexOf(fn); if (at >= 0) listeners.splice(at, 1); },
    execCommand: (cmd) => {
      if (cmd !== 'copy') return false;
      const event = { clipboardData: clipboard ? { setData: (kind, value) => { set[kind] = value; } } : null,
        preventDefault() { event.prevented = true; } };
      for (const fn of [...listeners]) fn(event);
      return execReturns;
    },
    contains: (n) => n === body || body.children.includes(n),
  };
  const selection = { rangeCount: 1, getRangeAt: () => ({ cloneRange: () => 'the user\'s range' }),
    removeAllRanges() { restored.length = 0; }, addRange(r) { restored.push(r); } };
  globalThis.document = doc;
  globalThis.window = { getSelection: () => selection };
  return { set, listeners, body, restored };
}

function suite(write) {
  const names = [];
  const failures = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  const text = world();
  const wroteText = write('', 'lot\tqty\nstring\tnumber');
  say('W1 text alone: the plain text is set and no HTML part', wroteText === true
    && text.set['text/plain'] === 'lot\tqty\nstring\tnumber' && !('text/html' in text.set), JSON.stringify(text.set));
  const rich = world();
  write('<table></table>', 'a');
  say('W2 with HTML: both parts', rich.set['text/html'] === '<table></table>' && rich.set['text/plain'] === 'a',
    JSON.stringify(rich.set));
  world({ clipboard: false });
  const unserved = write('', 'a');
  world({ execReturns: false });
  const unfired = write('', 'a');
  say('W3 a copy event with nothing to write into, or a copy that did not fire, is a failure',
    unserved === false && unfired === false, `${unserved} ${unfired}`);
  const tidy = world();
  write('', 'a');
  say('W4 afterwards: no holder left in the page, no listener left, the user\'s selection back',
    tidy.body.children.length === 0 && tidy.listeners.length === 0
      && JSON.stringify(tidy.restored) === '["the user\'s range"]', JSON.stringify(tidy));
  return { ran: names.length, names, failures };
}

const { writeClipboardRich } = await import('../src/clipboard_write.js');
console.log('\n[1] the shared clipboard writer');
const base = suite(writeClipboardRich);
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'K1', what: 'an HTML part is set even when there is none', catches: 'W1',
    mutate: (t) => swap(t, "    if (html) e.clipboardData.setData('text/html', html);\n", "    e.clipboardData.setData('text/html', html);\n") },
  { id: 'K2', what: 'the plain text is not set', catches: 'W1',
    mutate: (t) => swap(t, "    e.clipboardData.setData('text/plain', text);\n", '') },
  { id: 'K3', what: 'a copy that did not land says it did', catches: 'W3',
    mutate: (t) => swap(t, '  return fired && served;\n', '  return true;\n') },
  { id: 'K4', what: 'the copy listener is left on the page', catches: 'W4',
    mutate: (t) => swap(t, "    document.removeEventListener('copy', onCopy, true);\n", '') },
];
const scored = await scoreMutants(MUTANTS, async (m) => {
  const loaded = (await loadWithProbe(SUBJECT, { mutate: m.mutate })).module;
  const quiet = console.log;
  console.log = () => {};
  try { return suite(loaded.writeClipboardRich); } finally { console.log = quiet; }
}, { baselineRan: base.ran, baselineNames: base.names,
     title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
