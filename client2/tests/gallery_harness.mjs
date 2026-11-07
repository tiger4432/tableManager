// THE MAIN GRID'S GALLERY (lead 77ffe5cb6): the grid's rows as 160 px tiles of one image column, a line a value of the
// Group by column.
//   G1 groups in the order the rows first say a value, each head its value and its count; no Group by - one «All rows»
//   G2 a row with a blank image has no tile; its group's head says «N without image»
//   G3 one image column - no Image box; two - the box, and the one kept for this table drawn
//   G4 the grid holds part of the table - «N of total loaded» and Load more, which asks the grid; all held - «N rows», no button
//   G5 the grid's rows change (a filter) - drawn again from them
//   G6 only the lines in view (and OVERSCAN either side) are drawn; scrolled, the drawn lines follow
//   G7 a tile pressed - its picture at LARGE_PX through the page's loader, its row's values, «Show in grid» hands its id
//   G8 a Group by picked is kept for that table only
//   G9 the caption: the picked column's value, by default the first column the grid shows that is not the picture; kept per table
//   G10 the group order: most rows first (the first said first among equals) by default, or by value; its box only with a Group by
//   G11 the side panel's keys: → ← the neighbour tile across a group's end, Esc closes, nothing while typing in a box
//   G12 the side panel's values: the columns the grid shows (its answer handed in), no other
//   G13 two galleries on one page, two tables: a caption picked on one leaves the other's
// Imports only (the probe copies a module whole); each defect must go red at its line.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, walk, byClass } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FILE = path.join(HERE, '..', 'src', 'gallery.js');

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

const memory = () => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), m }; };
const textOf = (n) => (n ? n.textContent : '');
const IMG = [{ name: 'lot', type: null }, { name: 'defect', type: null }, { name: 'pic', type: 'image' }];
/** `n` rows: defect cycles A, B, C; every `blankEvery`th has no picture. */
const rowsOf = (n, blankEvery = 0) => Array.from({ length: n }, (_, i) => ({ id: String(i),
  data: { lot: `L${i}`, defect: ['A', 'B', 'C'][i % 3], pic: blankEvery && i % blankEvery === 0 ? '' : `img/${i}.png` } }));

function seat(M, o = {}) {
  const doc = o.doc || makeDoc('dark');
  // the page's key listeners, which the stub document only swallows
  if (!doc.keys) {
    doc.keys = [];
    doc.addEventListener = (type, fn) => { if (type === 'keydown') doc.keys.push(fn); };
    doc.removeEventListener = (type, fn) => { if (type === 'keydown') doc.keys = doc.keys.filter((f) => f !== fn); };
    doc.press = (key, target = doc.body) => { const ev = { key, target, preventDefault() {} }; for (const fn of doc.keys.slice()) fn(ev); };
  }
  const mount = doc.createElement('div');
  doc.body.append(mount);
  const asked = [];
  const calls = { more: 0, shown: [] };
  const state = { rows: o.rows || rowsOf(9), columns: o.columns || IMG, table: o.table || 'T', whole: o.whole !== false, count: o.count || null };
  const part = new M.GalleryPart(mount, {
    doc, storage: o.storage || memory(),
    loader: { url: (ref, px) => `/api/image?ref=${ref}&px=${px}`, want: (url, cb) => { asked.push(url); cb(true); } },
    table: () => state.table, columns: () => state.columns, rows: () => state.rows,
    ...(o.shown ? { shown: () => o.shown } : {}),
    valueOf: (row, col) => row.data[col], count: () => state.count, whole: () => state.whole,
    loadMore: () => { calls.more += 1; }, showRow: (id) => calls.shown.push(id),
  });
  part.render();
  return { doc, mount, part, state, asked, calls };
}
const heads = (root) => byClass(root, 'gallery-head').map((h) => [textOf(byClass(h, 'gallery-head__value')[0]), textOf(byClass(h, 'gallery-head__n')[0]), textOf(byClass(h, 'gallery-head__without')[0])]);
const tiles = (root) => byClass(root, 'gallery-tile');
const selects = (root) => walk(root).filter((n) => n.tagName === 'SELECT');
/** The box under its label word. */
const box = (root, words) => { const l = byClass(root, 'gallery-pick').find((p) => textOf(byClass(p, 'gallery-pick__word')[0]) === words); return l ? walk(l).find((n) => n.tagName === 'SELECT') : null; };
/** Lay the scroller out: a box `w` wide and `h` high scrolled to `top`, then place. */
const lay = (s, w, h, top = 0) => { s.part.scroller.clientWidth = w; s.part.scroller.clientHeight = h; s.part.scroller.scrollTop = top; s.part.place(); };

async function suite(M) {
  ran = 0;
  failed = [];
  NAMES.length = 0;

  // G1 - grouped by defect: A, B, C in the order the rows say them, 3 each; no Group by - one group
  const g = seat(M, { storage: (() => { const s = memory(); s.setItem('gallery:T', JSON.stringify({ groupBy: 'defect' })); return s; })() });
  lay(g, 2000, 3000);
  ok('G1a grouped by a column: a head a value in the rows\' order, with its count', JSON.stringify(heads(g.mount).map((h) => h.slice(0, 2))) === JSON.stringify([['A', '3'], ['B', '3'], ['C', '3']]),
    JSON.stringify(heads(g.mount)));
  const one = seat(M);
  lay(one, 2000, 3000);
  ok('G1b no Group by: one «All rows» group of every row', JSON.stringify(heads(one.mount).map((h) => h.slice(0, 2))) === JSON.stringify([[M.WORDS.all, '9']]), JSON.stringify(heads(one.mount)));

  // G2 - every 3rd row blank: rows 0, 3, 6 (all A) have no tile, A's head says so
  const b = seat(M, { rows: rowsOf(9, 3), storage: (() => { const s = memory(); s.setItem('gallery:T', JSON.stringify({ groupBy: 'defect' })); return s; })() });
  lay(b, 2000, 3000);
  const bh = heads(b.mount);
  ok('G2 a blank image draws no tile and its head says «N without image»',
    tiles(b.mount).length === 6 && (bh[0] || [])[2] === M.WORDS.without(3) && (bh[1] || [])[2] === '' && !tiles(b.mount).some((t) => ['0', '3', '6'].includes(t.dataset.row)),
    `${tiles(b.mount).length} tiles, heads ${JSON.stringify(bh)}`);

  // G3 - one image column: Group by alone; two: the Image box too, the kept one drawn
  ok('G3a one image column: no Image box', !box(one.mount, M.WORDS.image) && !!box(one.mount, M.WORDS.groupBy), `${selects(one.mount).length} boxes`);
  const twoCols = [...IMG, { name: 'pic2', type: 'image' }];
  const kept = memory();
  kept.setItem('gallery:T', JSON.stringify({ image: 'pic2' }));
  const two = seat(M, { columns: twoCols, storage: kept, rows: rowsOf(3).map((r) => ({ ...r, data: { ...r.data, pic2: `b/${r.id}.png` } })) });
  lay(two, 2000, 3000);
  const imageBox = box(two.mount, M.WORDS.image);
  ok('G3b two image columns: an Image box of both, and the one kept for this table drawn',
    imageBox && imageBox.value === 'pic2' && imageBox.children.length === 2 && String(tiles(two.mount)[0].title).endsWith('b/0.png'),
    `${selects(two.mount).length} boxes, ${imageBox && imageBox.value}`);

  // G4 - part held: «9 of 1,200 loaded» and Load more asks the grid; all held: «9 rows», no button
  const part = seat(M, { whole: false, count: { total: 1200 } });
  const say = textOf(byClass(part.mount, 'gallery-count')[0]);
  const more = byClass(part.mount, 'gallery-more')[0];
  if (more) more.dispatch('click');
  ok('G4a the grid holds part: «9 of 1,200 loaded» and Load more asks the grid', say === '9 of 1,200 loaded' && part.calls.more === 1, `«${say}», asked ${part.calls.more}`);
  ok('G4b all held: «9 rows» and no Load more', textOf(byClass(one.mount, 'gallery-count')[0]) === '9 rows' && byClass(one.mount, 'gallery-more').length === 0,
    textOf(byClass(one.mount, 'gallery-count')[0]));

  // G5 - a filter: the grid now holds rows 0..1; drawn again, two tiles
  one.state.rows = rowsOf(2);
  one.part.render();
  lay(one, 2000, 3000);
  ok('G5 the grid\'s rows change: drawn again from them', tiles(one.mount).length === 2 && heads(one.mount)[0][1] === '2', `${tiles(one.mount).length} tiles`);

  // G6 - 1,000 rows, a box 1,000 wide (6 a line) and 600 high: the lines in view and OVERSCAN below, not 167
  const big = seat(M, { rows: rowsOf(1000) });
  lay(big, 1000, 600);
  const per = big.part.layout.per;
  const lineH = M.TILE_PX + M.CAPTION_PX + M.GAP_PX;
  const inView = Math.ceil((600 + M.OVERSCAN * lineH - M.HEAD_PX) / lineH) + 1;
  const drawnTop = byClass(big.mount, 'gallery-line').length;
  ok('G6a only the lines in view and OVERSCAN either side are drawn', per === 6 && drawnTop > 0 && drawnTop <= inView && tiles(big.mount).length <= inView * per,
    `${drawnTop} lines (at most ${inView}), ${per} a line, ${tiles(big.mount).length} tiles`);
  lay(big, 1000, 600, 100 * lineH);
  const rowsDrawn = tiles(big.mount).map((t) => Number(t.dataset.row));
  ok('G6b scrolled to line 100: the drawn tiles follow, the first lines are gone',
    Math.min(...rowsDrawn) >= (100 - M.OVERSCAN - 1) * per && rowsDrawn.includes(100 * per) && byClass(big.mount, 'gallery-line').length <= inView + M.OVERSCAN + 1,
    `rows ${Math.min(...rowsDrawn)}..${Math.max(...rowsDrawn)}`);

  // G7 - a tile pressed: the large picture, the row's values, «Show in grid» hands its id
  const t = tiles(g.mount).find((n) => n.dataset.row === '4');
  t.dispatch('click');
  const side = byClass(g.mount, 'gallery-side')[0];
  const big7 = walk(side).find((n) => n.tagName === 'IMG');
  const dd = walk(side).filter((n) => n.tagName === 'DD').map(textOf);
  const go = byClass(side, 'gallery-side__go')[0];
  go.dispatch('click');
  ok('G7 a tile pressed: its picture at LARGE_PX, its row\'s values, «Show in grid» hands its id',
    !side.hidden && big7.src === `/api/image?ref=img/4.png&px=${M.LARGE_PX}` && JSON.stringify(dd) === JSON.stringify(['L4', 'B', 'img/4.png']) && JSON.stringify(g.calls.shown) === '["4"]'
      && t.classList.contains('is-picked'),
    `src ${big7 && big7.src}, values ${JSON.stringify(dd)}, shown ${JSON.stringify(g.calls.shown)}`);

  // G8 - Group by picked on table T: kept for T, not for U
  const store = memory();
  const k = seat(M, { storage: store });
  const groupBox = box(k.mount, M.WORDS.groupBy);
  groupBox.value = 'lot';
  groupBox.dispatch('change');
  k.state.table = 'U';
  k.part.render();
  ok('G8 a Group by picked is kept for that table only', JSON.parse(store.getItem('gallery:T') || '{}').groupBy === 'lot' && store.getItem('gallery:U') === null && box(k.mount, M.WORDS.groupBy).value === '',
    `T ${store.getItem('gallery:T')}, U ${store.getItem('gallery:U')}`);
  // G9 - the caption: by default the first shown column not the picture; a picked one kept for its table
  const cap = seat(M, { shown: ['pic', 'defect', 'lot'] });
  lay(cap, 2000, 3000);
  const firstCap = textOf(byClass(tiles(cap.mount)[0], 'gallery-tile__cap')[0]);
  const capBox = box(cap.mount, M.WORDS.caption);
  if (capBox) { capBox.value = 'lot'; capBox.dispatch('change'); }
  lay(cap, 2000, 3000);
  ok('G9 the caption: the first shown column not the picture, a picked one kept for the table',
    firstCap === 'A' && textOf(byClass(tiles(cap.mount)[0], 'gallery-tile__cap')[0]) === 'L0' && (box(cap.mount, M.WORDS.caption) || {}).value === 'lot',
    `${firstCap} -> ${textOf(byClass(tiles(cap.mount)[0], 'gallery-tile__cap')[0])}`);

  // G10 - the order: defect C×1, A×3, B×2 in that first-said order
  const ordered = ['C', 'A', 'B', 'A', 'B', 'A'].map((d, i) => ({ id: String(i), data: { lot: `L${i}`, defect: d, pic: `img/${i}.png` } }));
  const ostore = memory();
  ostore.setItem('gallery:T', JSON.stringify({ groupBy: 'defect' }));
  const ord = seat(M, { rows: ordered, storage: ostore });
  lay(ord, 2000, 3000);
  const byCount = heads(ord.mount).map((h) => h[0]).join('');
  const orderBox = box(ord.mount, M.WORDS.order);
  if (orderBox) { orderBox.value = 'value'; orderBox.dispatch('change'); }
  lay(ord, 2000, 3000);
  const byValue = heads(ord.mount).map((h) => h[0]).join('');
  ok('G10a most rows first by default, by value when picked; no Order box without a Group by', byCount === 'ABC' && byValue === 'ABC'.split('').sort().join('')
    && !box(one.mount, M.WORDS.order), `${byCount} / ${byValue}`);
  const ties = M.galleryModel(['C', 'A', 'B'].map((d, i) => ({ id: String(i), data: { defect: d, pic: 'p' } })), { groupBy: 'defect', image: 'pic', valueOf: (r, c) => r.data[c] });
  ok('G10b among equal counts the first said first; by value numbers in their order', ties.map((g) => g.value).join('') === 'CAB'
    && M.galleryModel(['10', '9', '2'].map((d, i) => ({ id: String(i), data: { defect: d, pic: 'p' } })), { groupBy: 'defect', image: 'pic', order: 'value', valueOf: (r, c) => r.data[c] }).map((g) => g.value).join(',') === '2,9,10');

  // G11 - the keys: A's last tile → B's first (across the group's end), ← back, typing ignored, Esc closes and lets the keys go
  const kstore = memory();
  kstore.setItem('gallery:T', JSON.stringify({ groupBy: 'defect' }));
  const ks = seat(M, { storage: kstore });
  lay(ks, 2000, 3000);
  const lastOfA = tiles(ks.mount).filter((n) => ['0', '3', '6'].includes(n.dataset.row)).pop();
  lastOfA.dispatch('click');
  ks.doc.press('ArrowRight');
  const afterRight = ks.part.picked && ks.part.picked.id;
  ks.doc.press('ArrowLeft');
  const afterLeft = ks.part.picked && ks.part.picked.id;
  const input = ks.doc.createElement('input');
  ks.doc.press('ArrowRight', input);
  const afterTyping = ks.part.picked && ks.part.picked.id;
  ks.doc.press('Escape');
  const kside = byClass(ks.mount, 'gallery-side')[0];
  ok('G11 → ← the neighbour tile across a group\'s end, not while typing, Esc closes and lets go',
    afterRight === '1' && afterLeft === '6' && afterTyping === '6' && ks.part.picked === null && kside.hidden === true && ks.doc.keys.length === 0,
    `→ ${afterRight} ← ${afterLeft} typing ${afterTyping} keys ${ks.doc.keys.length}`);

  // G12 - the values: only the columns handed as shown
  const sv = seat(M, { shown: ['defect', 'lot'] });
  lay(sv, 2000, 3000);
  tiles(sv.mount)[0].dispatch('click');
  const dts = walk(byClass(sv.mount, 'gallery-side')[0]).filter((n) => n.tagName === 'DT').map(textOf);
  ok('G12 the side panel\'s values: the columns the grid shows, no other', JSON.stringify(dts) === '["defect","lot"]', JSON.stringify(dts));

  // G13 - two galleries, one page, two tables
  const shared = memory();
  const g1 = seat(M, { storage: shared, table: 'T' });
  const g2 = seat(M, { storage: shared, table: 'U', doc: g1.doc });
  const c1 = box(g1.mount, M.WORDS.caption);
  if (c1) { c1.value = 'pic'; c1.dispatch('change'); }
  g2.part.render();
  ok('G13 two galleries, two tables: a caption picked on one leaves the other\'s', (box(g1.mount, M.WORDS.caption) || {}).value === 'pic' && (box(g2.mount, M.WORDS.caption) || {}).value === 'lot',
    `${(box(g1.mount, M.WORDS.caption) || {}).value} / ${(box(g2.mount, M.WORDS.caption) || {}).value}`);
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { name: 'the groups in the order of their values, not the rows\'', catches: ['G1a'], mutate: swap('b[0].count - a[0].count || a[1] - b[1]', 'b[0].count - a[0].count || b[1] - a[1]') },
  { name: 'a blank image drawn as a tile', catches: ['G2'], mutate: swap('    if (isBlank(ref)) g.without += 1;\n    else g.tiles.push', '    if (isBlank(ref)) g.without += 1;\n    g.tiles.push') },
  { name: 'the head never says the rows without image', catches: ['G2'], mutate: swap('    if (group.without) h.append', '    if (false) h.append') },
  { name: 'the Image box for one image column too', catches: ['G3a'], mutate: swap('    if (images.length > 1) bar.append', '    if (images.length > 0) bar.append') },
  { name: 'the kept image column not read', catches: ['G3b'], mutate: swap('    const image = images.includes(kept.image) ? kept.image : images[0];', '    const image = images[0];') },
  { name: 'part held said as the rows alone', catches: ['G4a'], mutate: swap('whole || !total ? WORDS.rows(rows.length) : WORDS.loaded(rows.length, total)', 'WORDS.rows(rows.length)') },
  { name: 'Load more when all are held', catches: ['G4b'], mutate: swap('    if (!whole) {\n      const more', '    if (true) {\n      const more') },
  { name: 'the groups kept from the first draw', catches: ['G5'], mutate: swap('    this.groups = galleryModel(rows,', '    this.groups = this.groups || galleryModel(rows,') },
  { name: 'every line drawn', catches: ['G6a'], mutate: swap('  return layout.items.filter((it) => it.top + it.height >= top - margin && it.top <= top + height + margin);', '  return layout.items;') },
  { name: 'the drawn lines do not follow the scroll', catches: ['G6b'], mutate: swap("    const want = itemsInView(this.layout, this.scroller.scrollTop || 0,", '    const want = itemsInView(this.layout, 0,') },
  { name: 'the large picture asked at the tile\'s px', catches: ['G7'], mutate: swap('    const url = this.deps.loader.url(t.ref, LARGE_PX);', '    const url = this.deps.loader.url(t.ref, TILE_PX);') },
  { name: 'Show in grid hands nothing', catches: ['G7'], mutate: swap('() => this.deps.showRow(t.id)', '() => this.deps.showRow(null)') },
  { name: 'the choices kept for every table', catches: ['G8'], mutate: (s) => swap('getItem(`gallery:${table}`)', "getItem('gallery:')")(swap('setItem(`gallery:${table}`', "setItem('gallery:'")(s)) },
  { name: 'the caption defaults to the picture', catches: ['G9'], mutate: swap("(shown.find((n) => n !== image) || null)", '(image || null)') },
  { name: 'the groups kept in the order first said', catches: ['G10a'], mutate: swap("  return out.map((g, i) => [g, i]).sort((a, b) => b[0].count - a[0].count || a[1] - b[1]).map(([g]) => g);", '  return out;') },
  { name: 'by value as text, not as numbers', catches: ['G10b'], mutate: swap("a.value.localeCompare(b.value, 'en', { numeric: true })", "(a.value < b.value ? -1 : 1)") },
  { name: 'the arrows stop at a group\'s end', catches: ['G11'], mutate: swap('const tiles = (this.groups || []).flatMap((g) => g.tiles);', 'const tiles = ((this.groups || []).find((g) => g.tiles.some((x) => x.id === this.picked.id)) || { tiles: [] }).tiles;') },
  { name: 'typing in a box moves the panel', catches: ['G11'], mutate: swap("if (tag === 'input' || tag === 'select' || tag === 'textarea' || (t && t.isContentEditable)) return;", '') },
  { name: 'Esc keeps the keys', catches: ['G11'], mutate: swap("    if (this.doc.removeEventListener) this.doc.removeEventListener('keydown', this.onKey);\n    this.render();", '    this.render();') },
  { name: 'the side panel shows every column', catches: ['G12'], mutate: swap('(this.deps.shown ? this.deps.shown() : (this.deps.columns() || []).map((c) => c.name))', '(this.deps.columns() || []).map((c) => c.name)') },
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
