// PICK A NODE by first letters (owner 10-10, lead bccbdd601): the search box part and the walk page that seats it.
//
// Scores: a type opened asks its first nodes once and names the box by the key the server searches by; a pause in typing
// asks once, with what is typed; an older answer landing late is dropped; the list says each node's keys and count; a
// press, or Enter (the active row, else the first), picks - never from letters no longer in the box; Escape closes; the
// notes for no match, more than shown, an empty type, a type not read to the end, a refused search, a failed answer;
// two parts on one screen do not touch each other; fetchKeyValues carries starts_with and limit and reads prefix_axis,
// prefix_case and prefix_refusal. On the walk page the box is the key it searches by (no second cell), what is typed is
// the subject, a pick fills every key, a type the server cannot search keeps every key cell and says why there, and the
// 50-node dropdown is gone. The server's answers are the contract's (lead 10-10), faked here.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { makeDoc, flush, walk as walkAll } from './lib/board_dom.mjs';
import { SEARCH_DELAY_MS } from '../src/walk/node_search.js';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const settle = async () => { for (let i = 0; i < 20; i += 1) await flush(); };
const ascii = (t) => String(t).replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
const hasClass = (n, cls) => String(n.className || '').split(/\s+/).includes(cls);
const byClass = (root, cls) => walkAll(root).filter((n) => hasClass(n, cls));
const noop = () => {};

// The ledger as the fake server holds it: 25 wafers, first letters any case.
const WAFERS = Array.from({ length: 25 }, (_, i) => `NAB115-W${String(i + 1).padStart(2, '0')}`);
const answerFor = (prefix, over = {}) => {
  const hits = WAFERS.filter((k) => k.toLowerCase().startsWith(prefix.toLowerCase()));
  return { ok: true, nodes: hits.slice(0, 20).map((k) => ({ keys: { wafer: k }, count: 1 })), scanned: hits.length,
    scanTruncated: false, valuesTruncated: hits.length > 20, prefixAxis: 'wafer', prefixCase: 'insensitive',
    prefixRefusal: '', ...over };
};
const REFUSED = 'die cannot be searched by first letters: x is a number - type its keys';

/** What a part shows: its rows' keys and counts, which row is active, its note, its box. */
const shown = (s) => ({
  rows: byClass(s.root, 'wk-searchitem').map((n) => byClass(n, 'wk-searchkey')[0]._text),
  counts: byClass(s.root, 'wk-searchitem').map((n) => (byClass(n, 'wk-searchcount')[0] || { _text: '' })._text),
  active: byClass(s.root, 'wk-searchitem').findIndex((n) => n.attrs['aria-selected'] === 'true'),
  note: s.note.hidden ? '' : s.note._text,
  box: !s.cell.hidden,
});
const type = (s, text) => { s.input.value = text; s.input.dispatch('input', {}); };
const key = (s, name) => s.input.dispatch('keydown', { key: name, preventDefault: noop });

async function seen(M) {
  const out = {};
  const part = (deps) => {
    const doc = makeDoc('light');
    const mount = doc.createElement('div');
    doc.body.appendChild(mount);
    return new M.search.NodeSearch(mount, { doc, delay: 0, ...deps });
  };
  // ── one part ──
  {
    const asked = [];
    const typed = [];
    const picked = [];
    const s = part({ ask: async (prefix) => { asked.push(prefix); return answerFor(prefix); },
      onType: (t) => typed.push(t), onPick: (n) => picked.push(n.keys.wafer) });
    await s.open();
    out.opened = [asked.slice(), s.axis, s.name._text, s.input.placeholder, shown(s).rows.length];
    s.input.dispatch('focus', {});
    out.focused = [shown(s).rows.length, shown(s).note];
    type(s, 'n'); type(s, 'na'); type(s, 'nab115-w0');
    await settle();
    out.typed = [asked.slice(1), typed.slice(), shown(s).rows, shown(s).counts.every((c) => c === '1 atom')];
    key(s, 'ArrowDown'); key(s, 'ArrowDown');
    out.active = shown(s).active;
    key(s, 'Enter');
    out.enter = [picked.slice(), shown(s).rows.length];
    s.input.dispatch('focus', {});
    key(s, 'Enter');
    out.first = picked.slice(-1);
    // Enter before the answer for the letters in the box lands: nothing picked, the key as typed stands.
    s.input.dispatch('focus', {});
    type(s, 'nab115-w1');
    key(s, 'Enter');
    out.early = picked.length;
    await settle();
    key(s, 'Escape');
    out.escape = shown(s).rows.length;
    s.input.dispatch('click', {});
    out.reopen = shown(s).rows.length;
    key(s, 'Escape');
    s.input.dispatch('focus', {});
    const third = byClass(s.root, 'wk-searchitem')[2];
    third.dispatch('mousedown', { preventDefault: noop });
    out.press = [picked.slice(-1), shown(s).rows.length];
    s.input.dispatch('focus', {});
    type(s, 'zz');
    await settle();
    out.none = [shown(s).rows.length, shown(s).note];
    // The ledger holds no node of the letters typed (lead b5cdcbc75): only letter for letter, only from a whole answer.
    type(s, 'nab115-w07');
    await settle();
    const lower = s.holdsNone('nab115-w07');
    type(s, 'NAB115-W07');
    await settle();
    const exact = s.holdsNone('NAB115-W07');
    type(s, 'nab');
    await settle();
    out.holdsNone = [lower, exact, s.holdsNone('nab'), s.holdsNone('zz')];
  }
  // ── an older answer landing after a newer one ──
  {
    const pending = [];
    const s = part({ ask: (prefix) => new Promise((resolve) => pending.push({ prefix, resolve })) });
    const opened = s.open();
    await settle();
    pending[0].resolve(answerFor(''));
    await opened;
    s.input.dispatch('focus', {});
    type(s, 'nab115-w1');
    await settle();
    type(s, 'nab115-w2');
    await settle();
    pending[2].resolve(answerFor('nab115-w2'));
    await settle();
    pending[1].resolve(answerFor('nab115-w1'));
    await settle();
    out.order = [pending.map((p) => p.prefix), shown(s).rows];
  }
  // ── the notes ──
  {
    const refused = part({ ask: async () => answerFor('', { nodes: [], prefixAxis: null, prefixRefusal: REFUSED }) });
    await refused.open();
    out.refused = [refused.axis, shown(refused).box, shown(refused).note];
    const failed = part({ ask: async () => ({ ok: false, message: 'starts_with is refused' }) });
    await failed.open();
    out.failed = shown(failed).note;
    const empty = part({ ask: async () => answerFor('', { nodes: [], scanned: 0, valuesTruncated: false }) });
    await empty.open();
    out.empty = shown(empty).note;
    const cut = part({ ask: async () => answerFor('', { nodes: [], scanned: 1001, scanTruncated: true, valuesTruncated: false }) });
    await cut.open();
    out.cut = shown(cut).note;
  }
  // ── two parts on one screen ──
  {
    const askedA = [];
    const askedB = [];
    const a = part({ ask: async (p) => { askedA.push(p); return answerFor(p); } });
    const b = part({ ask: async (p) => { askedB.push(p); return answerFor(p, { nodes: [{ keys: { wafer: 'OTHER' }, count: 2 }] }); } });
    await a.open(); await b.open();
    a.input.dispatch('focus', {});
    type(a, 'nab115-w2');
    type(b, 'x');
    await settle();
    out.two = [askedA, askedB, a.input.value, b.input.value, shown(a).rows];
  }
  // ── the wire ──
  {
    const urls = [];
    const body = { nodes: [{ keys: { wafer: 'NAB115-W07' }, count: 1 }], scanned: 1, scan_truncated: false,
      values_truncated: true, prefix_axis: 'wafer', prefix_case: 'exact' };
    const fetchImpl = async (url) => { urls.push(String(url)); return { ok: true, status: 200, json: async () => body }; };
    const got = await M.api.fetchKeyValues({ apiBase: '', fetchImpl, type: 'wafer', startsWith: 'NAB115', limit: 20 });
    await M.api.fetchKeyValues({ apiBase: '', fetchImpl, type: 'wafer', startsWith: '', limit: 20 });
    const q = (u) => Object.fromEntries(new URLSearchParams(u.split('?')[1]));
    const refusedBody = { nodes: [], scanned: 0, prefix_axis: null, prefix_refusal: REFUSED };
    const refused = await M.api.fetchKeyValues({ apiBase: '', type: 'die',
      fetchImpl: async () => ({ ok: true, status: 200, json: async () => refusedBody }) });
    out.wire = [q(urls[0]), q(urls[1]), [got.prefixAxis, got.prefixCase, got.valuesTruncated, got.nodes.length],
      [refused.prefixAxis, refused.prefixRefusal]];
  }
  // ── the walk page ──
  {
    const DECL = { entities: [{ type: 'wafer', keys: ['wafer'] }, { type: 'lot_slot', keys: ['lot', 'slot'] },
      { type: 'die', keys: ['mat_id', 'x', 'y', 'mat_type'] }], predicates: [], worlds: [], operating: null };
    const asked = [];
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    const page = M.page.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      const q = Object.fromEntries(new URLSearchParams(u.split('?')[1] || ''));
      let body = DECL;
      if (u.includes('/key-values')) {
        asked.push(q);
        body = q.type === 'die' ? { nodes: [], scanned: 0, prefix_axis: null, prefix_refusal: REFUSED }
          : q.type === 'lot_slot' ? { nodes: [{ keys: { lot: 'LOT-7', slot: '02' }, count: 3 }], scanned: 1, prefix_axis: 'lot',
            prefix_case: 'exact' }
            : { nodes: [{ keys: { wafer: 'NAB115-W07' }, count: 1 }], scanned: 1, prefix_axis: 'wafer', prefix_case: 'exact' };
      }
      return { ok: true, status: 200, json: async () => body };
    } });
    await settle();
    const pickType = async (name) => {
      const sel = walkAll(host).find((n) => n.tagName === 'SELECT' && hasClass(n, 'wk-select'));
      sel.value = name;
      sel.dispatch('change', {});
      await settle();
    };
    const keyCells = () => walkAll(host).filter((n) => hasClass(n, 'wk-keys')).flatMap((g) => byClass(g, 'wk-keyname').map((n) => n._text));
    const box = () => walkAll(host).find((n) => hasClass(n, 'wk-search'));
    const boxInput = () => walkAll(box()).find((n) => n.tagName === 'INPUT');
    const boxName = () => (byClass(box(), 'wk-keyname')[0] || {})._text;
    const add = () => walkAll(host).find((n) => hasClass(n, 'wk-basketadd'));
    await pickType('lot_slot');
    out.composite = [keyCells(), boxName(), asked.slice()];
    boxInput().value = 'LOT-9';
    boxInput().dispatch('input', {});
    const addOn = !add().disabled;
    // The page's pause is the real one: waited out by the clock, not by twenty empty ticks (a tick is 1 ms or 15.6 ms
    // by what else runs on the box - red while Chrome held the timer at 1 ms, 10-10).
    await new Promise((ok) => setTimeout(ok, SEARCH_DELAY_MS + 50));
    await settle();
    out.typedSubject = [{ ...page.state.keys }, addOn, asked.slice(-1)[0]];
    boxInput().dispatch('focus', {});
    byClass(box(), 'wk-searchitem')[0].dispatch('mousedown', { preventDefault: noop });
    await settle();
    const slotInput = walkAll(host).filter((n) => hasClass(n, 'wk-keys'))
      .flatMap((g) => walkAll(g).filter((n) => n.tagName === 'INPUT'))[0];
    out.pickFills = [{ ...page.state.keys }, boxInput().value, slotInput && slotInput.value];
    await pickType('die');
    out.refusedPage = [keyCells(), byClass(box(), 'wk-cell')[0].hidden, byClass(box(), 'wk-note').map((n) => (n.hidden ? '' : n._text)).join()];
    await pickType('wafer');
    out.single = [keyCells(), boxName()];
    // A key typed in another case than the one node listed (the box asks with the letters typed): said beside + Add.
    const unheldNotes = () => byClass(host, 'wk-unheld').map((n) => n._text);
    const typeAndWait = async (text) => {
      boxInput().value = text;
      boxInput().dispatch('input', {});
      await new Promise((ok) => setTimeout(ok, SEARCH_DELAY_MS + 50));
      await settle();
    };
    await typeAndWait('nab115-w07');
    const lowerNotes = [unheldNotes(), !add().disabled];
    await typeAndWait('NAB115-W07');
    out.unheld = [...lowerNotes, unheldNotes()];
    out.noDropdown = walkAll(host).some((n) => n.tagName === 'OPTION' && /pick, or type/.test(n._text || ''));
  }
  return out;
}

function suite(out) {
  const names = [];
  const failures = [];
  const eq = (name, got, want) => {
    names.push(name);
    const g = ascii(JSON.stringify(got)), w = ascii(JSON.stringify(want));
    if (g === w) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`);
  };
  const w = (from, to) => WAFERS.slice(from, to);
  eq('T1 a type opened asks its first nodes once; the box is named by the key the server searches by, its case rule '
    + 'where the letters go; closed, no list', out.opened, [[''], 'wafer', 'wafer', 'First letters · any case', 0]);
  eq('T2 focused, the first nodes hang under the box, said to be not all', out.focused,
    [20, '20 nodes shown · not all · type more']);
  eq('T3 a burst of typing asks once, with what the box holds; every keystroke heard; the list is that answer, '
    + 'each row its count of atoms',
    out.typed, [['nab115-w0'], ['n', 'na', 'nab115-w0'], w(0, 9), true]);
  eq('T4 the arrows move the active row', out.active, 1);
  eq('T5 Enter picks the active row and closes the list', out.enter, [['NAB115-W02'], 0]);
  eq('T6 Enter with no row active picks the first', out.first, ['NAB115-W01']);
  eq('T7 Enter before the answer for the letters in the box lands picks nothing', out.early, 2);
  eq('T8 Escape closes the list', out.escape, 0);
  eq('T24 a press on the box opens it again', out.reopen, 10);
  eq('T9 a press picks its row and closes the list', out.press, [['NAB115-W12'], 0]);
  eq('T10 no node starts with the letters: said, and what + Add does', out.none,
    [0, 'No node starts with zz · + Add takes it as typed']);
  eq('T11 an older answer landing after a newer one is dropped', out.order,
    [['', 'nab115-w1', 'nab115-w2'], w(19, 25)]);
  eq('T12 a type the server cannot search by first letters: no box, its reason where the box was', out.refused,
    [null, false, REFUSED]);
  eq('T13 a failed answer says the server\'s sentence', out.failed, 'Node list · starts_with is refused');
  eq('T14 read to the end and empty: no node of this type', out.empty, 'No node of this type in the ledger');
  eq('T15 not read to the end: how many nodes were read', out.cut, 'Not every node read (up to 1001)');
  eq('T16 two parts on one screen: each asks its own, keeps its own text and list', out.two,
    [['', 'nab115-w2'], ['', 'x'], 'nab115-w2', 'x', w(19, 25)]);
  eq('T17 the wire: starts_with and limit asked, blank asks no starts_with; prefix_axis, prefix_case and '
    + 'prefix_refusal read', out.wire,
    [{ type: 'wafer', starts_with: 'NAB115', limit: '20' }, { type: 'wafer', limit: '20' }, ['wafer', 'exact', true, 1],
      [null, REFUSED]]);
  eq('T18 the page: a composite type - the box is the key it searches by, the other keys keep their cells; one ask, '
    + 'no starts_with, 20', out.composite, [['slot'], 'lot', [{ type: 'lot_slot', limit: '20' }]]);
  eq('T19 the page: what is typed in the box is the subject - + Add comes on, the pause asks those letters',
    out.typedSubject, [{ lot: 'LOT-9' }, true, { type: 'lot_slot', starts_with: 'LOT-9', limit: '20' }]);
  eq('T20 the page: a node picked fills every key - the box and the other cells', out.pickFills,
    [{ lot: 'LOT-7', slot: '02' }, 'LOT-7', '02']);
  eq('T21 the page: a type the server cannot search - every key a cell, the reason where the box was', out.refusedPage,
    [['mat_id', 'x', 'y', 'mat_type'], true, REFUSED]);
  eq('T22 the page: a single-key type - the box is its only key cell', out.single, [[], 'wafer']);
  eq('T23 the page: the 50-node dropdown is gone', out.noDropdown, false);
  eq('T25 the ledger holds none of the letters typed: only letter for letter (another case is another node), only from '
    + 'a whole answer - a cut one, or letters it was not asked, cannot say', out.holdsNone, [true, false, false, false]);
  eq('T26 the page: a key typed that no listed node is letter for letter - beside each + Add «0 atoms · not in the ledger», '
    + '+ Add still on; typed as the node is, nothing said (lead b5cdcbc75)', out.unheld,
    [['0 atoms · not in the ledger', '0 atoms · not in the ledger'], true, []]);
  return { ran: names.length, names, failures };
}

const REAL = {
  search: await import('../src/walk/node_search.js'),
  api: await import('../src/rnd_board/api.js'),
  page: await import('../src/walk/main.js'),
};
console.log('\n[1] node search');
const base = suite(await seen(REAL));
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const PART = { file: 'walk/node_search.js', key: 'search' };
const API = { file: 'rnd_board/api.js', key: 'api' };
const PAGE = { file: 'walk/main.js', key: 'page' };
const MUTANTS = [
  { id: 'NS1', what: 'every keystroke asks', catches: 'T3', ...PART,
    mutate: (t) => swap(t, "      clearTimeout(this.timer);\n      this.timer = setTimeout(", "      this.timer = setTimeout(") },
  { id: 'NS2', what: 'an older answer overwrites a newer one', catches: 'T11', ...PART,
    mutate: (t) => swap(t, '    if (mine !== this.seq) return null;\n', '') },
  { id: 'NS3', what: 'Enter picks from letters no longer in the box', catches: 'T7', ...PART,
    mutate: (t) => swap(t, 'if (!this.isOpen || !n || now !== this.asked) return;', 'if (!this.isOpen || !n) return;') },
  { id: 'NS4', what: 'a refused search keeps its box', catches: 'T12', ...PART,
    mutate: (t) => swap(t, "this.cell.hidden = this.state === 'loading' || Boolean(refusal);", "this.cell.hidden = this.state === 'loading';") },
  { id: 'NS5', what: 'read to the end and empty reads as not read to the end', catches: 'T14', ...PART,
    mutate: (t) => swap(t, 'say = got.scanTruncated ? SEARCH_WORDS.scanCut(got.scanned) : SEARCH_WORDS.empty;', 'say = SEARCH_WORDS.scanCut(got.scanned);') },
  { id: 'NS6', what: 'the pause is the module\'s, not the part\'s', catches: 'T16', ...PART,
    mutate: (t) => swap(t, "      clearTimeout(this.timer);\n      this.timer = setTimeout(() => { void this._ask(this.input.value); }, this.delay);",
      "      clearTimeout(globalThis.__nsPause);\n      globalThis.__nsPause = setTimeout(() => { void this._ask(this.input.value); }, this.delay);") },
  { id: 'NS7', what: 'the arrows do not move the active row', catches: 'T4', ...PART,
    mutate: (t) => swap(t, "this.active = e.key === 'ArrowDown' ? Math.min(this.active + 1, n - 1) : Math.max(this.active - 1, 0);", '') },
  { id: 'NS13', what: 'a pick keeps its active row for the next opening', catches: 'T6', ...PART,
    mutate: (t) => swap(t, '    this.isOpen = false;\n    this.active = -1;\n    this._draw();\n    this.onPick(node);',
      '    this.isOpen = false;\n    this._draw();\n    this.onPick(node);') },
  { id: 'NS14', what: 'a press on the box does not open it', catches: 'T24', ...PART,
    mutate: (t) => swap(t, "    this.input.addEventListener('click', open);\n", '') },
  { id: 'NS15', what: 'the row count drawn bare, not saying what it counts', catches: 'T3', ...PART,
    mutate: (t) => swap(t, "unitText(node.count, 'atom')", 'String(node.count)') },
  { id: 'NS8', what: 'starts_with is not asked', catches: 'T17', ...API,
    mutate: (t) => swap(t, "  if (startsWith) query.set('starts_with', String(startsWith));\n", '') },
  { id: 'NS9', what: 'prefix_axis is not read', catches: 'T17', ...API,
    mutate: (t) => swap(t, "prefixAxis: typeof body.prefix_axis === 'string' && body.prefix_axis ? body.prefix_axis : null,", 'prefixAxis: null,') },
  { id: 'NS10', what: 'the box\'s key keeps a second cell', catches: 'T18', ...PAGE,
    mutate: (t) => swap(t, '    const cells = keys.filter((k) => k !== search.axis);', '    const cells = keys;') },
  { id: 'NS11', what: 'what is typed in the box is not the subject', catches: 'T19', ...PAGE,
    mutate: (t) => swap(t, 'onType: (text) => { if (search.axis) state.keys[search.axis] = text; baskets.render(); },',
      'onType: () => { baskets.render(); },') },
  { id: 'NS12', what: 'a pick fills the box alone', catches: 'T20', ...PAGE,
    mutate: (t) => swap(t, 'onPick: (node) => { state.keys = { ...node.keys }; render(); },',
      'onPick: (node) => { state.keys = { [search.axis]: node.keys[search.axis] }; render(); },') },
  { id: 'HM2', what: 'a key matched in any case - a guess at another node', catches: 'T25', ...PART,
    mutate: (t) => swap(t, 'String((n.keys || {})[this.axis]) === key', 'String((n.keys || {})[this.axis]).toLowerCase() === key.toLowerCase()') },
  { id: 'HM3', what: 'a cut answer read as whole', catches: 'T25', ...PART,
    mutate: (t) => swap(t, ' || got.valuesTruncated || got.scanTruncated) return false;', ') return false;') },
  { id: 'HM4', what: 'an answer landing does not redraw the baskets', catches: 'T26', ...PAGE,
    mutate: (t) => swap(t, '    onAnswer: () => baskets.render() });', '    });') },
  { id: 'HM5', what: 'the picked node does not say it is not held', catches: 'T26', ...PAGE,
    mutate: (t) => swap(t, ',\n        unheld: search.holdsNone(keys[search.axis]) }', ' }') },
];
const scored = await scoreMutants(MUTANTS, async (m) => {
  const copy = (await loadWithProbe(join(SRC, m.file), { mutate: m.mutate })).module;
  return suite(await seen({ ...REAL, [m.key]: copy }));
}, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;
console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
