// table_tabs.js - the «Open tables» row (owner 11-05 ㄱ, mockup v3): a tab per open table, the open one marked, its note,
// × closes, past `fit` the rest under «+N ▾», the open table always in the row; ← → over the tables opened, the address
// saying ?table=; two rows on one page do not meet. A small document stub - no jsdom.
import { TableTabs, closeTable, tableNote, tableSteps } from '../src/table_tabs.js';
import { TableStateStore } from '../src/table_state.js';

let pass = 0;
const failures = [];
const eq = (name, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass += 1; console.log(`  PASS ${name}`); } else { failures.push(name); console.log(`  FAIL ${name} - expected ${w}, got ${g}`); }
};

class El {
  constructor(tag) { this.tag = tag; this.className = ''; this.textContent = ''; this.dataset = {}; this.attrs = {}; this.children = []; this.on = {}; this.hidden = false; this.disabled = false; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  append(...kids) { this.children.push(...kids); }
  replaceChildren(...kids) { this.children = [...kids]; }
  addEventListener(type, fn) { (this.on[type] ||= []).push(fn); }
  click() { (this.on.click || []).forEach((fn) => fn({ stopPropagation() {} })); }
  all(cls) { const out = []; const walk = (n) => { if (n.className.split(' ').includes(cls)) out.push(n); n.children.forEach(walk); }; this.children.forEach(walk); return out; }
}
const doc = { createElement: (tag) => new El(tag) };
const names = (mount) => mount.all('table-tab-name').map((b) => b.textContent);

console.log('[T] the row');
{
  const picked = [], closed = [];
  const mount = new El('nav');
  const tabs = new TableTabs({ mount, doc, fit: 3, onPick: (t) => picked.push(t), onClose: (t) => closed.push(t),
    noteOf: (t) => (t === 'a' ? '2 filters' : '') });
  tabs.draw(['a', 'b'], 'a');
  eq('T1 a tab per open table, the open one marked and said current', [names(mount), mount.all('is-open').length,
    mount.all('table-tab-name')[0].getAttribute('aria-current')], [['a', 'b'], 1, 'page']);
  eq('T2 its note beside its name, none where it says nothing', mount.all('table-tab-note').map((n) => n.textContent), ['2 filters']);
  mount.all('table-tab-name')[1].click(); mount.all('table-tab-name')[0].click();
  eq('T3 pressing another tab picks it; the open one picks nothing', picked, ['b']);
  mount.all('table-tab-close')[1].click();
  eq('T4 × closes that table, named in its label', [closed, mount.all('table-tab-close')[1].getAttribute('aria-label')], [['b'], 'Close b']);

  tabs.draw(['a', 'b', 'c', 'd', 'e'], 'e');
  eq('T5 past fit the rest go under «+N ▾» - the open table always in the row', [names(mount), mount.all('table-tab-more-btn')[0].textContent],
    [['a', 'b', 'e'], '+2 ▾']);
  mount.all('table-tab-more-btn')[0].click();
  const items = mount.all('table-tab-menu-item');
  eq('T6 «+N ▾» opens the rest; one picked from it is opened', [items.map((i) => i.textContent), (items[0].click(), picked.at(-1))], [['c', 'd'], 'c']);
  tabs.draw([], null);
  eq('T7 no open table: the row hides', mount.hidden, true);
}

console.log('[I] two rows on one page');
{
  const one = new El('nav'), two = new El('nav');
  new TableTabs({ mount: one, doc, onPick() {}, onClose() {} }).draw(['x'], 'x');
  new TableTabs({ mount: two, doc, onPick() {}, onClose() {} }).draw(['y', 'z'], 'z');
  eq('I1 each draws its own', [names(one), names(two)], [['x'], ['y', 'z']]);
}

console.log('[N] the note');
eq('N1 filters counted, a pivot said, nothing when nothing', [tableNote({ filterModel: { a: {}, b: {} }, pivot: { on: 1 } }),
  tableNote({ filterModel: { a: {} } }), tableNote({ filterModel: {} }), tableNote(null)], ['2 filters · pivot', '1 filter', '', '']);

console.log('[H] back and forward');
{
  const listeners = {};
  const history = { state: null, stack: [], at: -1,
    replaceState(s, _t, url) { this.state = s; this.stack[Math.max(this.at, 0)] = { s, url: String(url) }; if (this.at < 0) this.at = 0; },
    pushState(s, _t, url) { this.stack = this.stack.slice(0, this.at + 1); this.stack.push({ s, url: String(url) }); this.at += 1; this.state = s; },
    go(d) { this.at += d; this.state = this.stack[this.at].s; (listeners.popstate || []).forEach((fn) => fn({ state: this.state })); },
    back() { this.go(-1); }, forward() { this.go(1); } };
  const win = { history, location: { href: 'http://box/?table=old&tx=T1' }, addEventListener: (t, fn) => (listeners[t] ||= []).push(fn) };
  const back = new El('button'), forward = new El('button');
  const opened = [];
  let refuse = false;
  const steps = tableSteps({ back, forward, win, open: (t) => { opened.push(t); if (refuse) return Promise.resolve(false); steps.went(t); return Promise.resolve(true); } });
  steps.went('a'); steps.went('b'); steps.went('c');
  eq('H1 each table opened is a step; the address says the table and drops tx', [history.stack.map((x) => x.s.table), history.stack[2].url, back.disabled, forward.disabled],
    [['a', 'b', 'c'], 'http://box/?table=c', false, true]);
  back.click();
  await Promise.resolve(); await Promise.resolve();
  eq('H2 Back opens the table before, adding no step; Forward now open', [opened, history.stack.length, back.disabled, forward.disabled], [['b'], 3, false, false]);
  forward.click();
  await Promise.resolve(); await Promise.resolve();
  eq('H3 Forward opens the table after; nothing ahead again', [opened, forward.disabled], [['b', 'c'], true]);
  steps.went('c');
  eq('H4 the same table again adds no step', history.stack.length, 3);
  refuse = true;
  back.click();
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
  eq('H5 Back refused (edits staged): the address goes back to the table on screen, opened once, Back still on',
    [history.state.table, history.at, opened.length, back.disabled, forward.disabled], ['c', 2, 3, false, true]);
}

console.log('[C] × on a tab');
{
  // the page's own order: opening a table parks the one left (api.js switchTable), so the open table is left first
  const store = new TableStateStore();
  const page = { current: 'b', refuse: false };
  const open = async (t) => { if (page.refuse) return false; store.park(page.current, { filterModel: { x: {} } }); store.opened(t); page.current = t; return true; };
  for (const t of ['a', 'b']) { store.opened(t); store.park(t, { filterModel: { x: {} } }); }
  page.refuse = true;
  const kept = await closeTable('b', { store, current: page.current, open });
  eq('C1 × on the open table refused (edits staged): the tab and its settings stay', [kept, store.tables(), store.take('b').settings !== null], [false, ['a', 'b'], true]);
  page.refuse = false;
  const closed = await closeTable('b', { store, current: page.current, open });
  eq('C2 × on the open table: the one before opened, then the closed one forgotten though leaving it parked it',
    [closed, page.current, store.tables(), store.take('b')], [true, 'a', ['a'], { settings: null, data: null }]);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length ? 1 : 0);
