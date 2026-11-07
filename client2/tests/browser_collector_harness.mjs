// The browser collector's run, without a browser (lead 11-07): the subject is IMPORTED - browser_collector/lib - and the
// page, the tab and the product are fakes with the answers a page gives. What only a page can say (shown, selectors, the
// clicks) is the bench run's (browser_collector/tests/bench_run.mjs).
//
//   V  a value: text or @attribute, the regex's first group, length 0 is no value
//   O  opened: shown, changed from before the click, the pair equal; waiting ends in time with the reason
//   B  a batch: a key the table has is skipped unopened · an item that does not open is kept «not_opened», never read
//      from the previous item's content · no key is kept «no_key» with its cells · a key read after opening is asked after
//   R  a run: written · seen twice is skipped · the limit · a refused write named row by row · not allowed ends the run ·
//      a page read in batches of BATCH_MOST before its next page · a pause holds between batches · a retry reads only the
//      kept items (by the values read before opening) and ends when each is found
//   M  mutants - each on a copy of the whole lib folder with one change
//
// Run: node client2/tests/browser_collector_harness.mjs
import { cpSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { readSourceText } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const LIB = path.join(HERE, '..', '..', 'browser_collector', 'lib');
let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); } else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}

const load = async (dir) => ({
  open: await import(pathToFileURL(path.join(dir, 'open_check.js'))),
  extract: await import(pathToFileURL(path.join(dir, 'extract.js'))),
  batch: await import(pathToFileURL(path.join(dir, 'batch.js'))),
  run: await import(pathToFileURL(path.join(dir, 'run.js'))),
});

// ── fakes ────────────────────────────────────────────────────────────────────────────────
const el = (text, attrs = {}, kids = {}) => ({ innerText: text, getAttribute: (a) => attrs[a] ?? null, querySelector: (s) => kids[s] || null });

const T = {
  name: 'Inbox', keys: ['id'], max: 0, waitSeconds: 0.3,
  fields: [
    { column: 'id', base: 'item', selector: '', read: '@data-id', regex: '' },
    { column: 'unread', base: 'item', selector: '', read: '@class', regex: '\\b(unread)\\b' },
    { column: 'subject', base: 'content', selector: 'h2', read: 'text', regex: '' },
  ],
};
const mail = (id, subject, { opens = true, cls = 'row' } = {}) => ({ el: el(subject, { 'data-id': id, class: cls }), subject, opens });

/** A webmail list: the content area keeps the previous item's text until an item opens. */
function fakeMail(lib, items) {
  let shownText = 'Earlier mail body';
  let shownKids = { h2: el('Earlier mail') };
  let at = 0;
  const page = {
    opened: [],
    items(most) { const out = items.slice(at, at + most); at += out.length; return out; },
    where: () => 'bench://mail/list/1',
    base: (h) => h.el,
    async open(h) {
      page.opened.push(h.subject);
      const before = shownText;
      if (h.opens) { shownText = `${h.subject} body`; shownKids = { h2: el(h.subject) }; }
      return lib.open.waitOpened(() => ({ isShown: true, after: shownText, pair: null }), { before, limitMs: T.waitSeconds * 1000, everyMs: 20 });
    },
    content: () => el(shownText, {}, shownKids),
    async close() {},
  };
  return page;
}

const existingOf = (have, t) => async (cellsList) => new Set(cellsList.map((c) => t.keys.map((k) => c[k]).join('|')).filter((k) => have.includes(k)));

async function batchCase(lib, items, have = [], t = T) {
  const page = fakeMail(lib, items);
  const b = await lib.batch.readBatch(t, page, { room: Infinity, existing: existingOf(have, t) });
  return { b, opened: page.opened };
}

/** A tab whose batches are given; a product that answers per row. */
function fakeRun(batches, answer = () => ({ ok: true })) {
  let i = 0;
  const writes = [];
  return {
    writes,
    tab: {
      async batch(room) { const b = batches[i] || { read: 0, skipped: 0, rows: [], misses: [] }; const rows = b.rows.slice(0, room); return { ...b, read: Math.min(b.read, room), rows }; },
      async next() { i += 1; return i < batches.length ? 'more' : 'none'; },
    },
    product: {
      async write(rows) {
        writes.push(rows.map((r) => r.key));
        const bad = rows.map(answer).find((a) => !a.ok);
        return bad || { ok: true };
      },
    },
  };
}
const row = (key) => ({ key, cells: { id: key }, at: 'p', index: 0 });
const got = (n) => ({ read: n.length, skipped: 0, rows: n.map(row), misses: [] });

// ── the cases, on a lib folder ───────────────────────────────────────────────────────────
async function cases(lib) {
  const out = {};
  const { pick } = lib.extract;
  out.V = [pick(' a ', ''), pick('row unread', '\\b(unread)\\b'), pick('row', '\\b(unread)\\b'), pick('   ', ''), pick(null, ''), pick('id=42;', 'id=(\\d+)')];

  const { notOpenYet } = lib.open;
  out.O = [notOpenYet({ before: 'a', after: 'b', isShown: false }), notOpenYet({ before: 'a', after: 'a', isShown: true }),
    notOpenYet({ before: 'a', after: 'b', isShown: true, pair: { item: 'x', content: 'y' } }), notOpenYet({ before: 'a', after: 'b', isShown: true, pair: { item: 'x', content: 'x' } })];
  let looks = 0;
  out.Owait = [await lib.open.waitOpened(() => ({ isShown: true, after: ++looks > 2 ? 'new' : 'old' }), { before: 'old', limitMs: 1000, everyMs: 5 }),
    await lib.open.waitOpened(() => ({ isShown: true, after: 'old' }), { before: 'old', limitMs: 60, everyMs: 5 })];

  const known = await batchCase(lib, [mail('m1', 'One'), mail('m2', 'Two'), mail('m3', 'Three')], ['m2']);
  out.Bknown = { rows: known.b.rows.map((r) => [r.key, r.cells.subject, r.cells.unread]), skipped: known.b.skipped, opened: known.opened };

  const stale = await batchCase(lib, [mail('m1', 'One'), mail('m2', 'Two', { opens: false }), mail('m3', 'Three', { cls: 'row unread' })]);
  out.Bstale = { rows: stale.b.rows.map((r) => [r.key, r.cells.subject, r.cells.unread]), misses: stale.b.misses.map((m) => [m.reason, m.detail, m.index, m.cells.id]) };

  const nokey = await batchCase(lib, [mail(null, 'Nameless'), mail('m9', 'Nine')]);
  out.Bnokey = { rows: nokey.b.rows.map((r) => r.key), misses: nokey.b.misses.map((m) => [m.reason, m.at, m.index, m.cells.subject]) };

  const after = { ...T, keys: ['subject'] };
  const late = await batchCase(lib, [mail('m1', 'One'), mail('m2', 'Two')], ['Two'], after);
  out.Bafter = { rows: late.b.rows.map((r) => r.key), skipped: late.b.skipped, opened: late.opened };

  const plain = fakeRun([got(['a', 'b']), got(['b', 'c'])]);
  const t1 = await lib.run.runTemplate({ ...T }, plain.tab, plain.product);
  out.Rplain = { written: t1.written, skipped: t1.skipped, pages: t1.pages, ended: t1.ended, writes: plain.writes };

  const capped = fakeRun([got(['a', 'b', 'c']), got(['d', 'e', 'f']), got(['g'])]);
  const t2 = await lib.run.runTemplate({ ...T, max: 5 }, capped.tab, capped.product);
  out.Rlimit = { read: t2.read, written: t2.written, ended: t2.ended };

  const one = fakeRun([got(['a', 'bad', 'c'])], (r) => (r.key === 'bad' ? { ok: false, status: 400, detail: 'received: «yesterday» is not a time' } : { ok: true }));
  const t3 = await lib.run.runTemplate({ ...T }, one.tab, one.product);
  out.Rrefused = { written: t3.written, misses: t3.misses.map((m) => [m.reason, m.detail]), ended: t3.ended };

  const barred = fakeRun([got(['a', 'b']), got(['c'])], () => ({ ok: false, status: 403, detail: 'lee may not edit the table mail' }));
  const t4 = await lib.run.runTemplate({ ...T }, barred.tab, barred.product);
  out.Rbarred = { written: t4.written, ended: t4.ended, detail: t4.detail, misses: t4.misses.length, batchesWritten: barred.writes.length };
  const page = Array.from({ length: 25 }, (_, i) => `k${i + 1}`);
  let at = 0;
  const paged = { writes: [], nexts: 0 };
  const t6 = await lib.run.runTemplate({ ...T }, {
    async batch(room) { const keys = page.slice(at, at + room); at += keys.length; return got(keys); },
    async next() { paged.nexts += 1; return 'none'; },
  }, { async write(rows) { paged.writes.push(rows.length); return { ok: true }; } });
  out.Rpaged = { most: lib.run.BATCH_MOST, writes: paged.writes, nexts: paged.nexts, written: t6.written, pages: t6.pages };

  const held = fakeRun([got(['a']), got(['b'])]);
  let asks = 0;
  const seenPaused = [];
  const t7 = await lib.run.runTemplate({ ...T }, held.tab, held.product, {
    paused: () => { asks += 1; return asks === 2 || asks === 3; },       // paused after the first batch, for two looks
    progress: (x) => seenPaused.push(Boolean(x.paused)), wait: async () => {},
  });
  out.Rpause = { written: t7.written, ended: t7.ended, seen: seenPaused };

  const again = await batchCase(lib, [mail('m1', 'One'), mail('m2', 'Two'), mail('m3', 'Three')], [], { ...T, only: [{ id: 'm3' }, { id: 'm9' }] });
  out.Bonly = { seen: again.b.seen, read: again.b.read, rows: again.b.rows.map((r) => r.key), opened: again.opened };

  const pages2 = [['k1', 'k2', 'k3'], ['k4', 'k5'], ['k6']];
  let pg = 0;
  let nexts2 = 0;
  const t8 = await lib.run.runTemplate({ ...T, only: [{ id: 'k2' }, { id: 'k4' }], max: 2 }, {
    async batch(room) { const keys = pages2[pg].filter((k) => k === 'k2' || k === 'k4').slice(0, room); return { ...got(keys), seen: pages2[pg].length }; },
    async next() { nexts2 += 1; pg += 1; return pg < pages2.length ? 'more' : 'none'; },
  }, { async write() { return { ok: true }; } });
  out.Rretry = { written: t8.written, ended: t8.ended, nexts: nexts2 };
  return out;
}

const real = await cases(await load(LIB));
eq('V text, a regex group, no match, blank, none, a group of digits', real.V, ['a', 'unread', null, null, null, '42']);
eq('O not shown · unchanged · another item (the pair) · open', real.O, ['content not shown', 'content did not change', 'content is another item', null]);
eq('O waiting - opens on the third look; never changes -> the reason in its seconds', real.Owait, [{ opened: true }, { opened: false, detail: 'content did not change in 0 s' }]);
eq('B a key the table has is skipped unopened', real.Bknown, { rows: [['m1', 'One', null], ['m3', 'Three', null]], skipped: 1, opened: ['One', 'Three'] });
eq('B an item that does not open is kept «not_opened» - never the previous item\'s content; «unread» read before opening',
  real.Bstale, { rows: [['m1', 'One', null], ['m3', 'Three', 'unread']], misses: [['not_opened', 'content did not change in 0 s', 1, 'm2']] });
eq('B no key is kept «no_key» with where it was and its cells', real.Bnokey, { rows: ['m9'], misses: [['no_key', 'bench://mail/list/1', 0, 'Nameless']] });
eq('B a key read after opening: every item opened, the one the table has skipped after', real.Bafter, { rows: ['One'], skipped: 1, opened: ['One', 'Two'] });
eq('R written, a key seen twice skipped, one write per batch, ended at the last page', real.Rplain,
  { written: 3, skipped: 1, pages: 2, ended: 'last page', writes: [['a', 'b'], ['c']] });
eq('R the limit - 5 of max 5, ended «limit»', real.Rlimit, { read: 5, written: 5, ended: 'limit' });
eq('R a refused write is tried row by row - the bad row kept with the server\'s sentence, the others written', real.Rrefused,
  { written: 2, misses: [['refused', 'received: «yesterday» is not a time']], ended: 'last page' });
eq('R a page of 25 read 10 at a time, its next page asked once, after its last item', real.Rpaged, { most: 10, writes: [10, 10, 5], nexts: 1, written: 25, pages: 1 });
eq('R a pause holds between batches - said paused, then on to the end', real.Rpause, { written: 2, ended: 'last page', seen: [false, true, false, false] });
eq('B a retry reads only the kept items - m3 of three, the one not on the page not invented', real.Bonly, { seen: 3, read: 1, rows: ['m3'], opened: ['Three'] });
eq('R a retry ends when each kept item is found - on the second page, the third not asked', real.Rretry, { written: 2, ended: 'limit', nexts: 1 });
eq('R not allowed - the run ends «refused» with the sentence, nothing written, no second batch', real.Rbarred,
  { written: 0, ended: 'refused', detail: 'lee may not edit the table mail', misses: 0, batchesWritten: 3 });

// ── mutants: a copy of the whole lib folder, one change ─────────────────────────────────────
const MUTANTS = [
  ['M1 the before/after comparison off - the item that did not open is read from the previous item', 'Bstale', 'open_check.js',
    "if (after === before) return 'content did not change';", ''],
  ['M2 the table\'s keys not asked before opening', 'Bknown', 'batch.js', 'if (keyBefore && known.has(keyOf(t, x.cells))) { out.skipped += 1; continue; }', ''],
  ['M3 the limit off', 'Rlimit', 'run.js', 'Math.min(t.max ? t.max - tally.read : Infinity, BATCH_MOST)', 'BATCH_MOST'],
  ['M4 a refused write not tried row by row', 'Rrefused', 'run.js', 'const one = rows.length === 1 ? all : await product.write([r]);', 'const one = all;'],
  ['M6 the next page asked while the page still has items', 'Rpaged', 'run.js', 'if ((b.seen ?? b.read) === room) continue;', ''],
  ['M7 the pause not held', 'Rpause', 'run.js', 'if (paused() && !stopped()) {', 'if (false) {'],
  ['M8 a retry reading every item', 'Bonly', 'batch.js', 'const listed = t.only ? taken.filter((x) => t.only.some((c) => same(c, x.cells))) : taken;', 'const listed = taken;'],
  ['M5 no key written as a row', 'Bnokey', 'batch.js', "if (key === null) { out.misses.push({ reason: MISS.NO_KEY, detail: `${t.keys.join(', ')} has no value`, at, index: x.index, cells }); continue; }", ''],
];
for (const [name, which, file, from, to] of MUTANTS) {
  const dir = mkdtempSync(path.join(tmpdir(), 'collector-mutant-'));
  try {
    cpSync(LIB, dir, { recursive: true });
    const p = path.join(dir, file);
    const { text } = readSourceText(p);      // LF whatever the checkout did
    if (!text.includes(from)) { eq(`${name}: its anchor is in ${file}`, false, true); continue; }
    writeFileSync(p, text.replace(from, to));
    let caught;
    try { caught = JSON.stringify((await cases(await load(dir)))[which]) !== JSON.stringify(real[which]); } catch (e) { caught = `threw ${e.message}`; }
    eq(`${name}: caught`, caught, true);
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
