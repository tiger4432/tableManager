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
  const doc = makeDoc('dark');
  const mount = doc.createElement('div');
  doc.body.append(mount);
  const asked = [];
  const calls = { more: 0, shown: [] };
  const state = { rows: o.rows || rowsOf(9), columns: o.columns || IMG, table: o.table || 'T', whole: o.whole !== false, count: o.count || null };
  const part = new M.GalleryPart(mount, {
    doc, storage: o.storage || memory(),
    loader: { url: (ref, px) => `/api/image?ref=${ref}&px=${px}`, want: (url, cb) => { asked.push(url); cb(true); } },
    table: () => state.table, columns: () => state.columns, rows: () => state.rows,
    valueOf: (row, col) => row.data[col], count: () => state.count, whole: () => state.whole,
    loadMore: () => { calls.more += 1; }, showRow: (id) => calls.shown.push(id),
  });
  part.render();
  return { doc, mount, part, state, asked, calls };
}
const heads = (root) => byClass(root, 'gallery-head').map((h) => [textOf(byClass(h, 'gallery-head__value')[0]), textOf(byClass(h, 'gallery-head__n')[0]), textOf(byClass(h, 'gallery-head__without')[0])]);
const tiles = (root) => byClass(root, 'gallery-tile');
const selects = (root) => walk(root).filter((n) => n.tagName === 'SELECT');
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
  ok('G3a one image column: no Image box', selects(one.mount).length === 1, `${selects(one.mount).length} boxes`);
  const twoCols = [...IMG, { name: 'pic2', type: 'image' }];
  const kept = memory();
  kept.setItem('gallery:T', JSON.stringify({ image: 'pic2' }));
  const two = seat(M, { columns: twoCols, storage: kept, rows: rowsOf(3).map((r) => ({ ...r, data: { ...r.data, pic2: `b/${r.id}.png` } })) });
  lay(two, 2000, 3000);
  const imageBox = selects(two.mount)[1];
  ok('G3b two image columns: an Image box of both, and the one kept for this table drawn',
    selects(two.mount).length === 2 && imageBox.value === 'pic2' && imageBox.children.length === 2 && textOf(byClass(tiles(two.mount)[0], 'gallery-tile__cap')[0]) === 'b/0.png',
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
  const groupBox = selects(k.mount)[0];
  groupBox.value = 'lot';
  groupBox.dispatch('change');
  k.state.table = 'U';
  k.part.render();
  ok('G8 a Group by picked is kept for that table only', JSON.parse(store.getItem('gallery:T') || '{}').groupBy === 'lot' && store.getItem('gallery:U') === null && selects(k.mount)[0].value === '',
    `T ${store.getItem('gallery:T')}, U ${store.getItem('gallery:U')}`);
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { name: 'the groups in the order of their values, not the rows\'', catches: ['G1a'], mutate: swap('  return [...groups.values()];', '  return [...groups.values()].sort((a, b) => (a.value < b.value ? 1 : -1));') },
  { name: 'a blank image drawn as a tile', catches: ['G2'], mutate: swap('    if (isBlank(ref)) g.without += 1; else g.tiles.push', '    if (isBlank(ref)) g.without += 1; g.tiles.push') },
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
