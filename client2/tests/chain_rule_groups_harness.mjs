// CHAIN RULE GROUPS - the admin's chain rule list folded by a table (owner 11-11, lead), scored.
//   G  grouped by the trigger table, or by the table written: each group's rules, its head's counts (rules, not
//      running, last run failed) from the screen's own judges; a rule with no table under «—», last
//   F  the filter: a rule's name, its tables, a word its declaration holds (a column, an aggregation's name); while
//      typed, every kept group is open; none kept says so with what was typed
//   O  open groups: shut by default, a press opens one, kept in this browser per «group by»; a storage that throws
//      is no storage - the page's own state, nothing breaks
//   T  two on one page: each its own groups, filter and storage key
//   P  the rule editor's picker (owner 11-11): the names it lists in the list's groups, by the list's key and filter
// The subject is imported whole (no cut-out text). Run: node client2/tests/chain_rule_groups_harness.mjs
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/chain_rule_groups.js';

const SRC_PATH = fileURLToPath(new URL('../src/chain_rule_groups.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

// ── a DOM just big enough: built, typed into, clicks bubble ───────────────────────────
function makeDoc() {
  const doc = {
    createTextNode(text) { const n = doc.createElement('#text'); n._text = String(text); return n; },
    createElement(tag) {
      const el = {
        tagName: String(tag).toUpperCase(), className: '', children: [], parentNode: null, dataset: {}, attrs: {},
        listeners: {}, _text: '', value: '', type: '', placeholder: '', colSpan: 1,
        get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
        set textContent(v) { this._text = String(v); this.children = []; },
        appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
        addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
        closest(sel) {
          const m = /^\[data-([a-z-]+)\]$/.exec(sel);
          const key = m ? m[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase()) : null;
          for (let n = this; n; n = n.parentNode) if (key && n.dataset && key in n.dataset) return n;
          return null;
        },
        fire(type) {
          const event = { type, target: this };
          for (let n = this; n; n = n.parentNode) (n.listeners[type] || []).slice().forEach((fn) => fn(event));
        },
      };
      if (el.tagName === 'SELECT') {
        Object.defineProperty(el, 'value', {
          get() { return this._v !== undefined ? this._v : (this.children[0] ? this.children[0].value : ''); },
          set(v) { this._v = v; },
        });
      }
      return el;
    },
  };
  return doc;
}
const walk = (n, out = []) => { out.push(n); n.children.forEach((c) => walk(c, out)); return out; };
const byClass = (n, cls) => walk(n).filter((x) => String(x.className).split(' ').includes(cls));

function memoryStore() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), m };
}
const THROWS = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };

const RULES = [
  { name: 'lot_event.to_map', trigger_table: 'lot_event', target_table: 'dt_map', rule_state: 'running', kind: 'join',
    derive: { join: { on: [{ left: 'lot_id', right: 'lot_id' }], take: ['wafer_count'] } }, into: { table: 'dt_map' } },
  { name: 'lot_event.decide', trigger_table: 'lot_event', target_table: 'lot_master', rule_state: 'declared_only', kind: 'decide',
    derive: { decide: { aggregations: { height_max: 'Max([stack_height])' } } }, into: { table: 'lot_master' } },
  { name: 'dt_log.to_map', trigger_table: 'dt_log', target_table: 'dt_map', rule_state: 'running', kind: 'join',
    derive: { join: { take: [{ from: 'die_x', into: 'x' }] } }, into: { table: 'dt_map' } },
  { name: 'orphan', rule_state: 'running', kind: 'mapper' },
];
const OUTCOMES = { 'dt_log.to_map': { last_outcome: 'failed', last_reason: 'boom' }, 'lot_event.to_map': { last_outcome: 'ran:changed' } };

/** One list on a page: its toolbar mount, its body, the rows drawn by name. */
function list(M, { doc = makeDoc(), storage = memoryStore(), key = 'admin.chainRules' } = {}) {
  const mount = doc.createElement('div');
  const body = doc.createElement('tbody');
  const part = new M.ChainRuleGroups(mount, { doc, body, columns: 6, key, storage,
    rowOf: (rule) => { const tr = doc.createElement('tr'); tr.className = 'table-row'; tr.dataset.name = rule.name; return tr; } });
  const heads = () => byClass(body, 'chain-group__toggle');
  const head = (k) => heads().find((h) => h.dataset.chainGroup === k);
  const rows = () => body.children.filter((r) => r.className === 'table-row').map((r) => r.dataset.name);
  const type = (q) => { part.filter.value = q; part.filter.fire('input'); };
  const groupBy = (v) => { part.by.value = v; part.by.fire('change'); };
  return { part, mount, body, heads, head, rows, type, groupBy, storage, doc };
}

/** The questions, asked of a (possibly mutated) module. Returns the failed names (quiet) or scores them (loud). */
function suite(M, loud) {
  const bad = [];
  const say = (name, cond, saw) => { if (loud) ok(name, cond, saw); else if (!cond) bad.push(name); };

  if (loud) console.log('\n── G. GROUPS ───────────────────────────────────────────────────────');
  const g = M.chainRuleGroups(RULES, { by: 'trigger', outcomes: OUTCOMES });
  say('G1 by trigger table: one group a table, in its order, a rule with none under «—» last',
    g.map((x) => x.key).join() === 'dt_log,lot_event,—' && g[1].rules.map((r) => r.name).join() === 'lot_event.to_map,lot_event.decide',
    g.map((x) => x.key));
  say('G2 a head counts its rules, the ones not running and the ones whose last run failed',
    g[1].rules.length === 2 && g[1].off === 1 && g[1].failing === 0 && g[0].off === 0 && g[0].failing === 1
    && M.groupCountsText(g[1]) === '2 rules · 1 off · 0 failing' && M.groupCountsText(g[0]) === '1 rule · 0 off · 1 failing',
    g.map((x) => M.groupCountsText(x)));
  const w = M.chainRuleGroups(RULES, { by: 'writes', outcomes: OUTCOMES });
  say('G3 by the table written: dt_map holds both rules that write it', w.map((x) => x.key).join() === 'dt_map,lot_master,—'
    && w[0].rules.length === 2, w.map((x) => x.key));
  const a = list(M);
  a.part.render(RULES, OUTCOMES);
  say('G4 drawn: a head a group, shut, its counts on it; no row under a shut head', a.heads().length === 3 && a.rows().length === 0
    && a.head('dt_log').getAttribute('aria-expanded') === 'false' && a.head('dt_log').textContent.includes('1 rule · 0 off · 1 failing'),
    a.heads().map((h) => h.textContent));
  const ko = M.chainRuleGroups([{ name: 'n' }, { name: 'k', trigger_table: '설비_로그' }]);
  say('G6 a rule with no table is last even after a table named past «—» (a Korean name)', ko.map((x) => x.key).join() === '설비_로그,—',
    ko.map((x) => x.key));
  say('G5 a head with a failing rule is marked so', byClass(a.head('dt_log'), 'chain-group__counts')[0].dataset.failing === 'true'
    && byClass(a.head('lot_event'), 'chain-group__counts')[0].dataset.failing === undefined);

  if (loud) console.log('\n── F. THE FILTER ───────────────────────────────────────────────────');
  say('F1 a rule found by its name, its table, a column its declaration names, an aggregation\'s name',
    M.ruleMatches(RULES[0], 'TO_MAP') && M.ruleMatches(RULES[2], 'dt_log') && M.ruleMatches(RULES[2], 'die_x')
    && M.ruleMatches(RULES[1], 'height_max') && !M.ruleMatches(RULES[3], 'height') && M.ruleMatches(RULES[3], '  '));
  a.type('die_x');
  say('F2 typed: only the groups it keeps, drawn open with their rows; how many of how many',
    a.heads().map((h) => h.dataset.chainGroup).join() === 'dt_log' && a.rows().join() === 'dt_log.to_map'
    && a.part.shown.textContent === '1 of 4 rules', [a.heads().map((h) => h.dataset.chainGroup), a.rows(), a.part.shown.textContent]);
  a.type('nothing_named_so');
  say('F3 nothing kept says so, with what was typed', a.heads().length === 0
    && a.body.textContent === 'No rule matches «nothing_named_so»', a.body.textContent);
  a.type('');
  say('F4 cleared: every group back, shut as before, no count line', a.heads().length === 3 && a.rows().length === 0
    && a.part.shown.textContent === '');

  if (loud) console.log('\n── O. OPEN GROUPS ──────────────────────────────────────────────────');
  a.head('lot_event').fire('click');
  say('O1 a press opens that group alone, its rows under it', a.rows().join() === 'lot_event.to_map,lot_event.decide'
    && a.head('lot_event').getAttribute('aria-expanded') === 'true' && a.head('dt_log').getAttribute('aria-expanded') === 'false');
  say('O2 kept in this browser, per «group by»', a.storage.getItem('admin.chainRules:open:trigger') === '["lot_event"]',
    [...a.storage.m]);
  const again = list(M, { storage: a.storage });
  again.part.render(RULES, OUTCOMES);
  say('O3 a page opened again opens the same group', again.rows().join() === 'lot_event.to_map,lot_event.decide');
  a.groupBy('writes');
  say('O4 another «group by» has its own open groups - none yet', a.rows().length === 0 && a.heads().length === 3);
  a.groupBy('trigger');
  a.head('lot_event').fire('click');
  say('O5 a second press shuts it', a.rows().length === 0 && a.storage.getItem('admin.chainRules:open:trigger') === '[]');
  const t = list(M, { storage: THROWS });
  t.part.render(RULES, OUTCOMES);
  t.head('dt_log').fire('click');
  say('O6 a storage that throws: the press still opens the group (this page only)', t.rows().join() === 'dt_log.to_map');
  const none = list(M, { storage: null });
  none.part.render(RULES, OUTCOMES);
  none.head('dt_log').fire('click');
  say('O7 no storage at all: the same', none.rows().join() === 'dt_log.to_map');

  if (loud) console.log('\n── T. TWO ON ONE PAGE ──────────────────────────────────────────────');
  const doc = makeDoc();
  const shared = memoryStore();
  const x = list(M, { doc, storage: shared, key: 'x' });
  const y = list(M, { doc, storage: shared, key: 'y' });
  x.part.render(RULES, OUTCOMES);
  y.part.render(RULES, OUTCOMES);
  x.head('lot_event').fire('click');
  y.type('die_x');
  say('T1 a press and a filter in one leave the other as it was', x.rows().length === 2 && y.rows().join() === 'dt_log.to_map'
    && y.head('lot_event') === undefined && x.part.shown.textContent === '' && shared.getItem('y:open:trigger') === null,
    [x.rows(), y.rows()]);

  if (loud) console.log('\n── P. THE EDITOR\'S PICKER ─────────────────────────────────────────');
  const names = RULES.map((r) => r.name);
  const flat = (gs) => gs.map((x) => `${x.label}:${x.names.join('+')}`).join(' | ');
  const asList = (gs) => gs.map((x) => `${x.key}:${x.rules.map((r) => r.name).join('+')}`).join(' | ');
  const pt = M.pickerGroups(RULES, names, { by: 'trigger' });
  say('P1 by the trigger table: the list\'s groups, in its order, each with the list\'s rules',
    flat(pt) === asList(M.chainRuleGroups(RULES, { by: 'trigger' })), flat(pt));
  const pw = M.pickerGroups(RULES, names, { by: 'writes' });
  say('P2 by the table written: the same as the list\'s', flat(pw) === asList(M.chainRuleGroups(RULES, { by: 'writes' })), flat(pw));
  const pf = M.pickerGroups(RULES, names, { by: 'trigger', query: 'die_x' });
  say('P3 under a filter: the rules the list\'s filter keeps', flat(pf) === asList(M.chainRuleGroups(RULES, { query: 'die_x' }))
    && flat(pf) === 'dt_log:dt_log.to_map', flat(pf));
  const odd = M.pickerGroups(RULES.slice(0, 1), ['lot_event.to_map', 'just_typed'], {});
  say('P4 a name no rule here carries stands with the rules of no table; a rule the registry does not list is not offered',
    flat(odd) === 'lot_event:lot_event.to_map | —:just_typed', flat(odd));
  const b = list(M);
  b.groupBy('writes');
  say('P5 the list answers the key it is grouped by, and its filter says the picker\'s word',
    b.part.groupBy() === 'writes' && b.part.filter.placeholder === M.FILTER_WORD && M.FILTER_WORD === 'Filter: rule, table, column');
  return bad;
}

suite(BASELINE, true);

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 «off» counted by the declaration\'s enabled, not the server\'s state',
    swap('off: list.filter((r) => !ruleStateView(r).running).length,', 'off: list.filter((r) => r.enabled === false).length,')],
  ['M2 «failing» counts nothing', swap('failing: list.filter((r) => ruleOutcomeView(outcomes && outcomes[r.name]).failed).length,', 'failing: 0,')],
  ['M3 the filter reads only the name', swap("  if (rule) { walk(rule.derive); walk(rule.into); }\n", '')],
  ['M4 a declaration\'s keys are not words (an aggregation\'s name)', swap('Object.entries(v).forEach(([k, x]) => { out.push(k); walk(x); });', 'Object.values(v).forEach(walk);')],
  ['M5 a kept group stays shut while filtering', swap('const isOpen = Boolean(query.trim()) || open.includes(group.key);', 'const isOpen = open.includes(group.key);')],
  ['M6 one storage key for every «group by»', swap('storeKey(by) { return `${this.deps.key}:open:${by}`; }', 'storeKey() { return `${this.deps.key}:open`; }')],
  ['M7 a storage that throws breaks the press', swap("    try { if (this.store) this.store.setItem(this.storeKey(by), JSON.stringify(next)); } catch { /* none kept: all shut */ }",
    '    if (this.store) this.store.setItem(this.storeKey(by), JSON.stringify(next));')],
  ['M8 the «—» group sorts by its glyph', swap('const last = (k) => (k === ABSENT ? 1 : 0);', 'const last = () => 0;')],
  ['M9 groups keyed by the table written whatever is picked', swap('const keyOf = (GROUP_BY[by] || GROUP_BY.trigger).of;', 'const keyOf = GROUP_BY.writes.of;')],
  ['M10 the picker groups by the trigger table whatever the list is grouped by', swap('return chainRuleGroups(listed, { by, query })', 'return chainRuleGroups(listed, { query })')],
  ['M11 the picker ignores the filter', swap('return chainRuleGroups(listed, { by, query })', 'return chainRuleGroups(listed, { by })')],
  ['M12 a name no rule carries is dropped', swap('.map((name) => known.get(name) || { name });', '.map((name) => known.get(name)).filter(Boolean);')],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bkeyOf\b/g, 'keyFor')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')
    && !l.trim().startsWith('*') && !l.trim().startsWith('/*')).join('\n')],
];
async function score(listOf, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of listOf) {
    let bad;
    try { bad = suite((await loadWithProbe(SRC_PATH, { mutate, tag: 'chaingroups' })).module, false).length > 0; }
    catch (e) { if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`); bad = true; }
    if (bad === mustCatch) { hit++; passed++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}
await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
await score(CONTROLS, false, 'control mutants (each must ESCAPE)');
console.log(`\n${passed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
