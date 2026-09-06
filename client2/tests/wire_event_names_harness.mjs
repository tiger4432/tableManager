// Score the two event-name contracts: the wire events the grid listens for, and the theme
// notification this client sends itself.
//
// WHY THIS EXISTS. Both were spelled as bare literals in every file that used them, so renaming
// one produced NO error and NO failing check -- the branch simply stopped matching and the
// screen went quiet. Measured 2026-09-06: all six wire names DO pair with a server emitter
// today, so nothing was dead; what was missing is anything that would say so if that changed.
// The wire chain closed with no terminal else, and `themechange` was spelled in three files.
//
// WHAT THIS CAN AND CANNOT HOLD. The theme name now has one owner and both subscribers import
// it, so that contract is closed inside this client and is checkable here. The wire names are
// NOT closed by this file: the server spells them independently (17 literal sites across three
// server files, one constant for one name), and no client-side constant can make the two sides
// agree. So the wire half is scored on the thing that IS in reach -- an unmatched event is now
// audible instead of silent.
//
// IT IMPORTS ITS SUBJECTS. `websocket.js` and `theme.js` both load under node, and the mutants
// are whole modules built by `lib/probe.mjs`.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe, isProbeArtifact } from './lib/probe.mjs';
import { state } from '../src/state.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.join(HERE, '..', 'src');
const WS_PATH = path.join(SRC_DIR, 'websocket.js');

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
  return !!cond;
}

// A bare `{}` is worse than nothing here: `utils.js` guards its listener on
// `typeof window !== 'undefined'`, so defining an empty object turns that guard TRUE and the
// module dies on `window.addEventListener`. The stand-in has to answer what the guard implies.
globalThis.window = globalThis.window
  || { addEventListener() {}, removeEventListener() {} };

// One run of the wire suite against one loaded copy of websocket.js.
async function wireSuite(mutate) {
  const before = { pass, fail };
  const said = [];
  const { module } = await loadWithProbe(WS_PATH, {
    mutate,
    tag: 'wireev',
    stubs: { './utils.js': { showToast: (text, tone, opts) => said.push({ text, tone, opts }) } },
  });

  // The copy sits beside the subject, so `./state.js` resolves to the module this file already
  // imported -- setting it here is setting the state the subject reads.
  state.currentTable = 'T';
  state.gridApi = { applyTransaction() {}, refreshCells() {}, getRowNode: () => null };
  state.pageCache = new Map();

  said.length = 0;
  module.handleWebSocketMessage({ event: 'batch_refresh_required', table_name: 'T' });
  const afterKnown = said.filter(s => s.opts && s.opts.dedupeKey === 'ws-unhandled');
  ok(afterKnown.length === 0,
    'W1 a name the chain handles is NOT reported as unhandled');

  said.length = 0;
  module.handleWebSocketMessage({ event: 'batch_row_i_do_not_know', table_name: 'T' });
  const afterUnknown = said.filter(s => s.opts && s.opts.dedupeKey === 'ws-unhandled');
  ok(afterUnknown.length === 1,
    'W2 a name nothing matches is SAID, not swallowed');
  ok(afterUnknown.length === 1 && /batch_row_i_do_not_know/.test(afterUnknown[0].text),
    'W3 ... and it names the event, which is the only thing that identifies the gap');

  said.length = 0;
  module.handleWebSocketMessage({ event: 'batch_row_i_do_not_know', table_name: 'OTHER' });
  ok(said.filter(s => s.opts && s.opts.dedupeKey === 'ws-unhandled').length === 0,
    'W4 an event for another table is not this screen\'s gap and stays quiet');

  return { pass: pass - before.pass, fail: fail - before.fail };
}

console.log('-- the wire chain --------------------------------------------------');
await wireSuite(undefined);

console.log('\n-- the theme notification ------------------------------------------');
const THEME = await import('../src/theme.js');
ok(typeof THEME.THEME_CHANGE_EVENT === 'string' && THEME.THEME_CHANGE_EVENT.length > 0,
  'T1 the dispatcher owns the name and exports it');

// T2 is a drift oracle and says so. No behavioural check can see a THIRD subscriber added in
// another file with the literal typed again -- that code is on no path this harness calls -- so
// the question is asked of the source. `addEventListener('themechange'` is the exact shape that
// stopped existing; prose mentioning the name in a comment is not a subscription.
function jsFiles(dir) {
  const out = [];
  for (const e of readdirSync(dir)) {
    const p = path.join(dir, e);
    if (statSync(p).isDirectory()) out.push(...jsFiles(p));
    else if (e.endsWith('.js') && !isProbeArtifact(e)) out.push(p);
  }
  return out;
}
const literalSubscribers = jsFiles(SRC_DIR)
  .filter(p => /addEventListener\(\s*['"]themechange['"]/.test(readFileSync(p, 'utf8')))
  .map(p => path.relative(SRC_DIR, p).replace(/\\/g, '/'));
ok(literalSubscribers.length === 0,
  `T2 no subscriber re-spells the name -- found [${literalSubscribers.join(', ')}]`);

const base = { pass, fail };
failedNames.length = 0;

// -- mutants ---------------------------------------------------------------------------
const DEFECTS = [
  ['a handled event is renamed, so it stops matching',
    s => s.replace("event === 'batch_refresh_required'", "event === 'batch_refresh_requiredX'")],
  ['the terminal else is removed again',
    s => s.replace("    console.warn('[WebSocket] unhandled event', event);\n", '')
          .replace(/    showToast\(`실시간 갱신 누락[^`]*`, 'warning',\n      \{ dedupeKey: 'ws-unhandled' \}\);\n/, '')],
  ['the unhandled report drops the event name',
    s => s.replace('실시간 갱신 누락 · 알 수 없는 이벤트 «${event}»', '실시간 갱신 누락')],
  ['the report fires for every table, not just this one',
    s => s.replace('  if (msg.table_name !== state.currentTable) return;',
                   '  if (false) return;')],
];
const CONTROLS = [
  // A control has to be SEMANTICS-PRESERVING or it is not a control. The first version of this
  // one swept `\bevent === '`, which also matches `msg.event === '` and renamed the field on the
  // two branches above the chain, and it left `console.warn(..., event)` pointing at a name that
  // no longer existed -- so it threw, and a throw scores as caught. Each use of the local is
  // named explicitly instead.
  ['a local rename', s => s
    .replace('  const event = msg.event;', '  const evt = msg.event;')
    .replace("  if (event === 'batch_row_create') {", "  if (evt === 'batch_row_create') {")
    .replace("  } else if (event === 'batch_row_upsert') {", "  } else if (evt === 'batch_row_upsert') {")
    .replace("  } else if (event === 'batch_row_delete') {", "  } else if (evt === 'batch_row_delete') {")
    .replace("  } else if (event === 'batch_refresh_required') {", "  } else if (evt === 'batch_refresh_required') {")
    .replace("    console.warn('[WebSocket] unhandled event', event);",
             "    console.warn('[WebSocket] unhandled event', evt);")
    .replace('알 수 없는 이벤트 «${event}»', '알 수 없는 이벤트 «${evt}»')],
  ['comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
];

quiet = true;
let caught = 0; const escapedNames = [];
console.log('\n-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [name, mutate] of DEFECTS) {
  let r;
  try { r = await wireSuite(mutate); }
  catch (e) {
    const m = String(e && e.message);
    if (/did not mutate|unchanged/.test(m)) {
      quiet = false; console.error(`\nan anchor no longer matches: ${name}: ${m}`); process.exit(2);
    }
    r = { pass: 0, fail: 1 };
  }
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  let r;
  try { r = await wireSuite(mutate); }
  catch (e) {
    const m = String(e && e.message);
    if (/did not mutate|unchanged/.test(m)) {
      quiet = false; console.error(`\nan anchor no longer matches: ${name}: ${m}`); process.exit(2);
    }
    r = { pass: 0, fail: 1 };
  }
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; console.log(`  CAUGHT  ${name}  <- a check is reading source text`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${failedNames.join('\n  ')}`);
if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);

const bad = base.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escapedNames.length} escaped; ${CONTROLS.length - controlsCaught}/`
  + `${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
