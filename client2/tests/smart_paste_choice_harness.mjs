/**
 * Smart paste: which clipboard format is sent (lead 8771e43ac 1).
 *   C  the table's declared order picks without asking; no order or none of it on the clipboard asks
 *      as before (more than one format), one format goes as before
 *   N  the chooser names no format (the order is the table's), and both readers in main.js choose
 *      through it — main.js cannot be imported (it wires the page), so that line reads its text
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'smart_paste_choice.js');
const MAIN = path.join(HERE, '..', 'src', 'main.js');

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

// The fixture's formats — the chooser itself never names one.
const HTML = 'text/html';
const PLAIN = 'text/plain';
const RTF = 'text/rtf';
const EXCEL = [PLAIN, HTML, RTF];

async function suite(choose, source) {
  const asked = [];
  const ask = (answer) => async (types) => { asked.push(types.join(',')); return answer; };
  console.log('\n-- C. the order picks; otherwise as before --');
  const a = await choose(EXCEL, [HTML, PLAIN], ask(RTF));
  eq('C1 declared [html, plain], an Excel copy: html, without asking', `${a.type}|${a.byOrder}|${asked.length}`, `${HTML}|true|0`);
  const b = await choose([PLAIN, RTF], [HTML], ask(RTF));
  eq('C2 declared [html], none of it on the clipboard: asked, with what is there', `${b.type}|${b.byOrder}|${asked.join(' ; ')}`, `${RTF}|false|${PLAIN},${RTF}`);
  asked.length = 0;
  const c = await choose(EXCEL, null, ask(PLAIN));
  eq('C3 no order declared: asked, as before', `${c.type}|${c.byOrder}|${asked.length}`, `${PLAIN}|false|1`);
  asked.length = 0;
  const d = await choose([PLAIN], [HTML], ask(RTF));
  eq('C4 one format and not the declared one: it goes, as before, unasked', `${d.type}|${d.byOrder}|${asked.length}`, `${PLAIN}|false|0`);
  const e = await choose(EXCEL, [], ask(null));
  eq('C5 an empty order is no order; a cancelled ask sends nothing', `${e.type}|${e.byOrder}`, 'null|false');
  const f = await choose([PLAIN, HTML], [HTML, PLAIN], ask(RTF));
  eq('C6 the order\'s first that is present, not the clipboard\'s first', `${f.type}|${f.byOrder}`, `${HTML}|true`);

  console.log('\n-- N. no format named; both readers choose here --');
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  ok('N1 the chooser names no format', !/['"`][a-z]+\/[a-z.+-]+['"`]/i.test(code));
  const main = readFileSync(MAIN, 'utf8');
  eq('N2 both readers in main.js choose through it, and nothing asks around it',
    `${(main.match(/chooseClipboardType\(textTypes, state\.currentSmartPaste, showClipboardTypeModal\)/g) || []).length}|${(main.match(/showClipboardTypeModal\(textTypes\)/g) || []).length}`, '2|0');
  return { ran, failed: failedList.slice() };
}

const load = async (mutate) => {
  const text = readFileSync(SUBJECT, 'utf8').replace(/\r\n/g, '\n');
  const got = await loadWithProbe(SUBJECT, mutate ? { mutate: (t) => mutate(t.replace(/\r\n/g, '\n')) } : {});
  return { choose: got.module.chooseClipboardType, source: mutate ? mutate(text) : text };
};

const MUTANTS = [
  { name: 'the-order-is-not-read', catches: ['C1', 'C6'], from: '  if (Array.isArray(order)) {', to: '  if (false) {' },
  { name: 'the-clipboard-order-wins', catches: ['C6'],
    from: '    const hit = order.find((type) => types.includes(type));', to: '    const hit = types.find((type) => order.includes(type));' },
  { name: 'one-format-asks-too', catches: ['C4'], from: '  if (types.length > 1) return', to: '  if (types.length >= 1) return' },
  { name: 'a-default-format-is-named', catches: ['N1'],
    from: '  return { type: types[0] || null, byOrder: false };', to: "  return { type: types[0] || 'text/plain', byOrder: false };" },
];

const main = async () => {
  console.log('== baseline ==');
  const base = await load();
  const result = await suite(base.choose, base.source);
  const BASE_NAMES = NAMES.slice();
  console.log(`\n${result.ran - result.failed.length} passed, ${result.failed.length} failed.`);
  if (result.failed.length) { console.log(`ASSERTIONS ${result.ran} ${result.failed.length}`); process.exit(1); }
  const { wrong } = await scoreMutants(MUTANTS, async (m) => {
    const swap = (t) => { if (!t.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.name}`); return t.split(m.from).join(m.to); };
    let mods;
    try { mods = await load(swap); } catch (err) { console.error(`HARNESS FAILURE: ${err.message}`); process.exit(2); }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { await suite(mods.choose, mods.source); } finally { console.log = real; }
    return { failures: failedList, ran };
  }, { baselineRan: result.ran, baselineNames: BASE_NAMES,
       title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
  console.log(`\nASSERTIONS ${result.ran} ${result.failed.length}`);
  process.exit(wrong ? 1 : 0);
};

main();
