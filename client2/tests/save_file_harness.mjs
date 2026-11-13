// save_file - the save-to-file door the CSV export and the gallery zip both go through (lead 11-12).
// Run: node client2/tests/save_file_harness.mjs
//
//   F1 no picker: a browser without showSaveFilePicker has none, and asking none picks no file
//   F2 desktop: the wrapper has no picker even where the window offers one
//   F3 cancel: a closed dialog is said as cancelled (the caller sends nothing); a picker that throws otherwise is no
//      file, its error kept
//   F4 a write that fails: the file aborted, not closed, nothing saved by link, the error thrown to the caller
//   F5 a picked file: every chunk written in order, closed, its name answered; no link pressed
//   F6 no file: the chunks held and saved by a link under the name asked, its bytes the body's
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveObjectURL } from 'node:buffer';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FILE = path.join(HERE, '..', 'src', 'save_file.js');

let ran = 0;
let failed = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1;
  NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failed.push(name);
  console.log(`  FAIL ${name}${detail === undefined ? '' : ` -- ${detail}`}`);
};

const enc = (s) => new TextEncoder().encode(s);
/** An answer whose body reads `parts` one chunk each. */
const answer = (parts) => {
  const left = parts.map(enc);
  return { body: { getReader: () => ({ read: async () => (left.length ? { done: false, value: left.shift() } : { done: true }) }) } };
};
/** A picked file: what was written, closed, aborted; `failAt` - the write that throws. */
const fileOf = (name, failAt = -1) => {
  const seen = { writes: [], closed: false, aborted: false };
  return { seen, handle: { name, createWritable: async () => ({
    write: async (v) => { if (seen.writes.length === failAt) throw new Error('disk full'); seen.writes.push(new TextDecoder().decode(v)); },
    close: async () => { seen.closed = true; },
    abort: async () => { seen.aborted = true; },
  }) } };
};
/** A document whose link presses are kept: the name and the bytes the link pointed at. */
const docOf = () => {
  const pressed = [];
  return { pressed, doc: {
    createElement: () => { const a = { click: () => pressed.push({ download: a.download, blob: resolveObjectURL(a.href) }) }; return a; },
    body: { appendChild() {}, removeChild() {} },
  } };
};

async function suite(M) {
  ran = 0;
  failed = [];
  NAMES.length = 0;
  const offered = { showSaveFilePicker: async (o) => ({ name: o.suggestedName }) };

  ok('F1 no picker: none in a browser without it; none asked, no file',
    M.savePicker({ win: {} }) === null && typeof M.savePicker({ win: offered }) === 'function'
      && JSON.stringify(await M.pickFile(null, {})) === JSON.stringify({ handle: null }),
    `${M.savePicker({ win: {} })} · ${typeof M.savePicker({ win: offered })}`);

  ok('F2 desktop: no picker though the window offers one', M.savePicker({ isDesktop: true, win: offered }) === null);

  const abort = Object.assign(new Error('closed'), { name: 'AbortError' });
  const cancelled = await M.pickFile(async () => { throw abort; }, {});
  const blocked = new Error('not allowed');
  const failedPick = await M.pickFile(async () => { throw blocked; }, {});
  const picked = await M.pickFile(offered.showSaveFilePicker, { suggestedName: 'T.zip' });
  ok('F3 cancel: a closed dialog cancelled; any other throw no file with its error; a pick its handle',
    cancelled.cancelled === true && !('handle' in cancelled)
      && failedPick.handle === null && failedPick.failed === blocked && !failedPick.cancelled
      && picked.handle && picked.handle.name === 'T.zip',
    `${JSON.stringify(cancelled)} · ${JSON.stringify(failedPick)} · ${JSON.stringify(picked)}`);

  const broken = fileOf('T.zip', 1);
  const d4 = docOf();
  let thrown = null;
  try { await M.saveBody(answer(['ab', 'cd', 'ef']), { handle: broken.handle, filename: 'T.zip', doc: d4.doc }); } catch (err) { thrown = err; }
  ok('F4 a write that fails: aborted, not closed, no link, the error thrown',
    broken.seen.aborted && !broken.seen.closed && d4.pressed.length === 0 && thrown && thrown.message === 'disk full',
    `${JSON.stringify(broken.seen)} · pressed ${d4.pressed.length} · ${thrown && thrown.message}`);

  const good = fileOf('picked.zip');
  const d5 = docOf();
  const counts = [];
  const r5 = await M.saveBody(answer(['ab', 'cd', 'ef']), { handle: good.handle, filename: 'T.zip', doc: d5.doc, onBytes: (n) => counts.push(n) });
  ok('F5 a picked file: every chunk written in order, closed, its name answered, no link',
    good.seen.writes.join('|') === 'ab|cd|ef' && good.seen.closed && !good.seen.aborted && d5.pressed.length === 0
      && r5.name === 'picked.zip' && r5.picked === true && counts.join(',') === '2,4,6',
    `${JSON.stringify(good.seen)} · ${JSON.stringify(r5)} · ${counts}`);

  const d6 = docOf();
  const r6 = await M.saveBody(answer(['ab', 'cd', 'ef']), { filename: 'T_20261112-1130.zip', type: 'application/zip', doc: d6.doc });
  const held = d6.pressed[0];
  const bytes = held && held.blob ? await held.blob.text() : null;
  ok('F6 no file: held and saved by a link under the name asked, its bytes the body\'s',
    d6.pressed.length === 1 && held.download === 'T_20261112-1130.zip' && bytes === 'abcdef'
      && r6.name === 'T_20261112-1130.zip' && r6.picked === false,
    `${JSON.stringify(d6.pressed.map((p) => p.download))} · ${bytes} · ${JSON.stringify(r6)}`);
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { name: 'a picker where the browser has none', catches: ['F1'], mutate: swap("typeof win.showSaveFilePicker === 'function'", 'true') },
  { name: 'the desktop given the picker', catches: ['F2'], mutate: swap('return !isDesktop && win', 'return win') },
  { name: 'a closed dialog taken for a failed picker', catches: ['F3'], mutate: swap("err && err.name === 'AbortError' ? { cancelled: true } : ", '') },
  { name: 'a failed write leaves the file open', catches: ['F4'], mutate: swap('    if (writable) { try { await writable.abort(); }', '    if (false) { try { await writable.abort(); }') },
  { name: 'a picked file never closed', catches: ['F5'], mutate: swap('    await writable.close();\n', '') },
  { name: 'the held zip saved under no name', catches: ['F6'], mutate: swap('  link.download = filename;\n', '') },
];

const load = async (m) => (await loadWithProbe(FILE, m ? { mutate: m.mutate } : {})).module;
const base = await suite(await load());
const BASE_NAMES = NAMES.slice();
if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const M = await load(m);
  const real = console.log;
  console.log = () => {};
  try { const r = await suite(M); return { failures: r.failed, ran: r.ran }; } finally { console.log = real; }
}, { baselineRan: base.ran, baselineNames: BASE_NAMES, title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
process.exit(wrong ? 1 : 0);
