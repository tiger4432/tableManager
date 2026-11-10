// ADMIN ROUTE — the admin page's address, one spelling both ways (owner 11-10 «플로우 ㄱ»: the main grid's Flow box opens
// the chain editor at a rule in a new tab), scored.
//
// The subject is imported whole (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored:
//   R  an address built for a rule reads back as that rule - spaces, Korean, # = & % ? / in its name
//   O  the addresses the router already took read as before (a tab, #editor=<path>, an old ?tab= link)
//   N  a rule the file has opens as it came; one it lacks opens nothing and says «Rule <name> not found»
// Run: node client2/tests/admin_route_harness.mjs
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';

const BASELINE = await import('../src/admin_route.js');
const SRC_PATH = fileURLToPath(new URL('../src/admin_route.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

const NAMES = ['dt_log_to_dt_map', 'rule with spaces', '한글 규칙', 'a#b=c&d%e?f/g'];
// what a browser hands the router: the hash of the address it was opened at
const hashOf = (href) => new URL(href, 'http://box:8080').hash;
const READ = { rules: ['dt_log_to_dt_map', '한글 규칙'], skeleton: {}, lists: {}, grammar: 'unified', name: '한글 규칙',
  declaration: { trigger_table: 'dt_log' }, raw: '{"trigger_table": "dt_log"}' };
const MISSING = { ...READ, name: 'gone rule', declaration: null, raw: 'null' };
const X = BASELINE;

console.log('\n── R. A RULE\'S ADDRESS READS BACK AS THAT RULE ──────────────────────');
{
  const back = NAMES.map((n) => X.adminRouteOf(hashOf(X.chainRuleHref(n))));
  ok('R1 every name, read back whole, on the chain key', back.every((r, i) => r.key === 'chain' && r.value === NAMES[i]), back);
  ok('R2 the admin page, the chain key', NAMES.every((n) => X.chainRuleHref(n).startsWith('/admin.html#chain=')));
  ok('R3 a name\'s # and = stay inside the value', !X.chainRuleHref('a#b=c&d%e?f/g').slice('/admin.html#'.length).includes('#')
    && X.chainRuleHref('a#b=c&d%e?f/g').split('=').length === 2, X.chainRuleHref('a#b=c&d%e?f/g'));
}

console.log('\n── O. THE ADDRESSES THE ROUTER ALREADY TOOK ────────────────────────');
{
  ok('O1 a tab', JSON.stringify(X.adminRouteOf('#file')) === JSON.stringify({ key: 'file', value: null }));
  ok('O2 the file editor at a path', X.adminRouteOf('#editor=mappers/x.py').value === 'mappers/x.py');
  ok('O3 an old ?tab= link', X.adminRouteOf('', '?tab=chain').key === 'chain');
  ok('O4 a key in capitals reads as its tab', X.adminRouteOf('#Chain').key === 'chain');
  ok('O5 a tab\'s own address has no value', X.adminHref('chain') === '/admin.html#chain' && X.adminRouteOf(hashOf(X.adminHref('chain'))).value === null);
}

console.log('\n── N. THE RULE AN ADDRESS NAMES ────────────────────────────────────');
{
  const has = X.ruleAddressed(READ, '한글 규칙');
  ok('N1 a rule the file has: the read as it came, nothing refused', has.body === READ && has.refusal === null);
  const lacks = X.ruleAddressed(MISSING, 'gone rule');
  ok('N2 a rule it lacks: nothing open - no name, no declaration, no text', !('name' in lacks.body)
    && !('declaration' in lacks.body) && !('raw' in lacks.body), lacks.body);
  ok('N3 ...the list and the grammar kept', lacks.body.rules.join('|') === READ.rules.join('|') && lacks.body.grammar === 'unified');
  ok('N4 ...and why, in one line', lacks.refusal && lacks.refusal.message === 'Rule gone rule not found'
    && lacks.refusal.code === '' && lacks.refusal.path === '', lacks.refusal);
  ok('N5 no name asked (the list read) and an unread answer pass as they are',
    X.ruleAddressed(READ, '').body === READ && X.ruleAddressed(null, 'x').body === null && X.ruleAddressed(null, 'x').refusal === null);
}

const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 a name put in the address as typed', swap('=${encodeURIComponent(value)}', '=${value}')],
  ['M2 the value not decoded', swap('try { value = decodeURIComponent(raw.slice(eq + 1)); }', 'try { value = raw.slice(eq + 1); }')],
  ['M3 a missing rule opens its empty form', swap('  const { name: _asked, declaration: _none, raw: _empty, ...list } = body;\n', '  const list = body;\n')],
  ['M4 a missing rule is not said', swap("return { body: list, refusal: { code: '', path: '', message: ruleNotFound(name) } };", 'return { body: list, refusal: null };')],
  ['M5 the old ?tab= link forgotten', swap("if (!raw) raw = new URLSearchParams(search || '').get('tab') || '';", '')],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\beq\b/g, 'at')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')
    && !l.trim().startsWith('*') && !l.trim().startsWith('/*')).join('\n')],
];

function verdict(M) {
  if (!NAMES.every((n) => { const r = M.adminRouteOf(hashOf(M.chainRuleHref(n))); return r.key === 'chain' && r.value === n; })) return true;
  if (M.adminRouteOf('', '?tab=chain').key !== 'chain') return true;
  const lacks = M.ruleAddressed(MISSING, 'gone rule');
  if ('name' in lacks.body || !lacks.refusal || lacks.refusal.message !== 'Rule gone rule not found') return true;
  if (M.ruleAddressed(READ, '한글 규칙').body !== READ) return true;
  return false;
}

if (verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module');
async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad;
    try { bad = verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'adminroute' })).module); }
    catch (e) { if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`); bad = true; }
    if (bad === mustCatch) { hit++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}
const caught = await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
const escaped = await score(CONTROLS, false, 'control mutants (each must ESCAPE)');
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
