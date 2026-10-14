// COLOR BY - the root part's, every kind's (owner 10-13 «COLOR BY 저런 거는 모든 근원부품이 공유하게 해»). The root reads
// the Color by slot of each row and decides its colour once - a category's own colour from the declaration (`colors`:
// {category: hex}, Spotfire's legend colour picker) or the palette's category colour in turn; a kind only draws with
// it (a scatter point, a table line, a cross table cell, a map cell). The legend and its palette are drawn here too.
// The one seat a colour is asked: colorsOf; a hub (a marker, a cell) asks colorOfIds.

import { mix } from './palette.js';

/** The Color by slot every kind of the root holds. */
export const COLOR_SLOT = Object.freeze({ key: 'color', label: 'Color by', category: true, many: true });

/**
 * Each row's colour by the declaration's Color by: a row reading one value is in that category (categories in their
 * sorted order, each its declared colour - one not declared yet given the palette's next colour no category holds, in
 * the order the rows show them, and handed back in `assigned` for the declaration to keep (Spotfire's: a value keeps its
 * colour as more come); none, several or no slot - the one colour.
 * @param {Array<{id, reads: object}>} rows
 * @param {{palette: object, declaration?: object, marked?: (id) => boolean}} ctx
 * @returns {{any: boolean, of: Map<string, {fill, line, category}>, categories: Array<{name, fill, line, ids, dim}>, one: [string, string],
 *   assigned: Record<string, string>}}
 */
export function colorsOf(rows, ctx) {
  const palette = ctx.palette;
  const decl = ctx.declaration || {};
  const own = decl.colors || {};
  const categoryOf = (row) => (row.reads.color && row.reads.color.state === 'one' ? String(row.reads.color.value) : null);
  const seen = [...new Set(rows.map(categoryOf).filter((c) => c !== null))];
  const names = [...seen].sort();
  const marked = ctx.marked || (() => false);
  const anyMarked = rows.some((r) => marked(r.id));
  // A category not declared yet: the palette's next colour no category holds, in the order the rows show them (QA 10-14:
  // a colour by the value's hash put two of seven on one colour)
  const assigned = assignLooks(seen, own, palette.cat.map(([fill]) => fill));
  const lineOf = (fill) => (palette.cat.find(([f]) => f === fill) || [fill, fill])[1];
  const categories = names.map((name) => {
    const fill = own[name] || assigned[name];
    const line = lineOf(fill);
    const ids = rows.filter((r) => categoryOf(r) === name).map((r) => r.id);
    return { name, fill, line, ids, dim: anyMarked && !ids.some(marked) };
  });
  const byName = new Map(categories.map((c) => [c.name, c]));
  const of = new Map(rows.map((r) => {
    const c = byName.get(categoryOf(r));
    return [r.id, c ? { fill: c.fill, line: c.line, category: c.name } : { fill: palette.one[0], line: palette.one[1], category: null }];
  }));
  return { any: Boolean(decl.encode && decl.encode.color), of, categories, one: palette.one, assigned };
}

/** A category's look not declared yet - THE one rule for Color by's colours and Shape by's shapes: the pool's next one no
 *  category holds, in the order the rows show them (all held - round the pool again); handed back for the declaration to
 *  keep, so a value keeps its look as more come (Spotfire's). */
export function assignLooks(seen, own, pool) {
  const held = new Set(Object.values(own));
  const assigned = {};
  for (const name of seen.filter((n) => !own[n])) {
    const free = pool.findIndex((look) => !held.has(look));
    const look = pool[free >= 0 ? free : held.size % pool.length];
    assigned[name] = look;
    held.add(look);
  }
  return assigned;
}

/** A hub's colour - its rows' when they share one category, else the one colour. */
export function colorOfIds(colors, ids) {
  const seen = [...new Set(ids.map((id) => (colors.of.get(id) || {}).category))];
  const first = colors.of.get(ids[0]);
  return seen.length === 1 && first ? first : { fill: colors.one[0], line: colors.one[1], category: null };
}

/**
 * What a mark is painted (base set 5 and 7 - the root's, the kind draws it): its rows' colour; marked when a row of it is
 * marked - in the marking's colour (Spotfire's); the rest mixed toward the background while something is marked.
 * @param {boolean} [anyHeld]  something of the walk is marked though no row is (a press that stands for nodes, hubs.js)
 * @returns {(ids: string[], held?: string[]) => {fill, line, color, marked: boolean, dim: boolean}}  held - the nodes the
 *   mark's press stands for
 */
export function painter({ colors, marked, markColor, palette, ids, anyHeld = false }) {
  const anyMarked = anyHeld || ids.some(marked);
  return (of, held = null) => {
    const c = colorOfIds(colors, of);
    // color - the rows' own colour, unmarked and undimmed (a table line's band, a cross table cell)
    if (of.some(marked) || (held && held.some(marked))) return { fill: markColor || c.fill, line: markColor || c.line, color: c.fill, marked: true, dim: false };
    if (anyMarked) return { fill: mix(c.fill, palette.bg), line: mix(c.line, palette.bg), color: c.fill, marked: false, dim: true };
    return { fill: c.fill, line: c.line, color: c.fill, marked: false, dim: false };
  };
}

/** The root's colours and paint for rows, together - what a kind's model is handed (`colors`, `paint`, `colored`). */
export function paintRows(rows, { palette, declaration, marked = () => false, markColor = null, anyHeld = false }) {
  const colors = colorsOf(rows, { palette, declaration, marked });
  return { colors, colored: colors.any, paint: painter({ colors, marked, markColor, palette, ids: rows.map((r) => r.id), anyHeld }) };
}

/** The Color by legend's look: a category's colour circle (pressed, the palette for it); none - the one colour. */
export const COLOR_LEGEND = Object.freeze({
  key: 'color', title: 'Color by:',
  icon(c, ctx, el) {
    const ico = el(c ? 'button' : 'span', 'sf-legend__ico');
    ico.style.background = c ? c.fill : ctx.looks.one[0];
    ico.style.borderColor = c ? c.line : ctx.looks.one[1];
    if (!c) return ico;
    ico.type = 'button';
    ico.setAttribute('aria-label', `Colour of ${c.name}`);
    ico.addEventListener('click', (event) => { if (event.stopPropagation) event.stopPropagation(); ctx.openPalette(c.name, ico); });
    return ico;
  },
});

/**
 * A legend block (Color by, Shape by - `look`): its title, the slot's pill and «+», a line a category - its look and its
 * name (pressed, its rows marked as a hub) - or «All values».
 * @param {{doc, pill, plus, words, markHub, openPalette}} ctx  the root's
 */
export function legendBlock(looks, ctx, look = COLOR_LEGEND) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const at = { ...ctx, looks };
  const block = el('div', 'sf-legend__block');
  const row = el('div', 'sf-legend__row');
  row.append(ctx.pill(look.key), ctx.plus(look.key));
  block.append(el('div', 'sf-legend__ttl', look.title), row);
  if (!looks.categories.length) {
    const v = el('div', 'sf-legend__v');
    v.append(look.icon(null, at, el), el('span', 'sf-legend__name', 'All values'));
    block.append(v);
    return block;
  }
  for (const c of looks.categories) {
    const v = el('div', `sf-legend__v${c.dim ? ' is-dim' : ''}`);
    v.setAttribute('data-category', c.name);
    const ico = look.icon(c, at, el);
    const name = el('button', 'sf-legend__name', c.name);
    name.type = 'button';
    name.addEventListener('click', (event) => ctx.markHub([[ctx.words(look.key), c.name]], c.ids, event));
    v.append(ico, name);
    block.append(v);
  }
  return block;
}

/** The palette for a category: the palette's colours in a grid, then any colour; a pick is the declaration's. */
export function paletteBox(doc, palette, current, onPick) {
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const box = el('div', 'sf-pop sf-swatches');
  const grid = el('div', 'sf-swatches__grid');
  for (const fill of [...palette.cat.map(([f]) => f), ...(palette.swatches || [])]) {
    const s = el('button', `sf-swatches__it${fill === current ? ' is-on' : ''}`);
    s.type = 'button';
    s.style.background = fill;
    s.setAttribute('aria-label', fill);
    s.addEventListener('click', () => onPick(fill));
    grid.append(s);
  }
  const more = el('label', 'sf-swatches__more');
  const input = el('input');
  input.type = 'color';
  input.value = /^#[0-9a-f]{6}$/i.test(current || '') ? current : '#000000';
  input.addEventListener('change', () => onPick(input.value));
  more.append(input, el('span', '', 'More colors'));
  box.append(grid, more);
  return box;
}

