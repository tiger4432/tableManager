// COLOR BY - the root part's, every kind's (owner 10-13 «COLOR BY 저런 거는 모든 근원부품이 공유하게 해»). The root reads
// the Color by slot of each row and decides its colour once - a category's own colour from the declaration (`colors`:
// {category: hex}, Spotfire's legend colour picker) or the palette's category colour in turn; a kind only draws with
// it (a scatter point, a table line, a cross table cell, a map cell). The legend and its palette are drawn here too.
// The one seat a colour is asked: colorsOf; a hub (a marker, a cell) asks colorOfIds.

import { categoryColor } from './palette.js';

/** The Color by slot every kind of the root holds. */
export const COLOR_SLOT = Object.freeze({ key: 'color', label: 'Color by', category: true });

/**
 * Each row's colour by the declaration's Color by: a row reading one value is in that category (categories in their
 * sorted order, each its declared colour or the palette's k-th); none, several or no slot - the palette's one colour.
 * @param {Array<{id, reads: object}>} rows
 * @param {{palette: object, declaration?: object, marked?: (id) => boolean}} ctx
 * @returns {{any: boolean, of: Map<string, {fill, line, category}>, categories: Array<{name, fill, line, ids, dim}>, one: [string, string]}}
 */
export function colorsOf(rows, ctx) {
  const palette = ctx.palette;
  const decl = ctx.declaration || {};
  const own = decl.colors || {};
  const categoryOf = (row) => (row.reads.color && row.reads.color.state === 'one' ? String(row.reads.color.value) : null);
  const names = [...new Set(rows.map(categoryOf).filter((c) => c !== null))].sort();
  const marked = ctx.marked || (() => false);
  const anyMarked = rows.some((r) => marked(r.id));
  const categories = names.map((name, k) => {
    const [fill, line] = own[name] ? [own[name], own[name]] : categoryColor(palette, k);
    const ids = rows.filter((r) => categoryOf(r) === name).map((r) => r.id);
    return { name, fill, line, ids, dim: anyMarked && !ids.some(marked) };
  });
  const byName = new Map(categories.map((c) => [c.name, c]));
  const of = new Map(rows.map((r) => {
    const c = byName.get(categoryOf(r));
    return [r.id, c ? { fill: c.fill, line: c.line, category: c.name } : { fill: palette.one[0], line: palette.one[1], category: null }];
  }));
  return { any: Boolean(decl.encode && decl.encode.color), of, categories, one: palette.one };
}

/** A hub's colour - its rows' when they share one category, else the one colour. */
export function colorOfIds(colors, ids) {
  const seen = [...new Set(ids.map((id) => (colors.of.get(id) || {}).category))];
  const first = colors.of.get(ids[0]);
  return seen.length === 1 && first ? first : { fill: colors.one[0], line: colors.one[1], category: null };
}

/**
 * The legend's Color by block: its title, the slot's pill and «+», a line a category - its colour (pressed, the palette
 * for it) and its name (pressed, its rows marked as a hub) - or «All values».
 * @param {{doc, pill, plus, words, markHub, openPalette}} ctx  the root's
 */
export function legendBlock(colors, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const block = el('div', 'sf-legend__block');
  const row = el('div', 'sf-legend__row');
  row.append(ctx.pill('color'), ctx.plus('color'));
  block.append(el('div', 'sf-legend__ttl', 'Color by:'), row);
  if (!colors.categories.length) {
    const v = el('div', 'sf-legend__v');
    const ico = el('span', 'sf-legend__ico');
    ico.style.background = colors.one[0];
    ico.style.borderColor = colors.one[1];
    v.append(ico, el('span', 'sf-legend__name', 'All values'));
    block.append(v);
    return block;
  }
  for (const c of colors.categories) {
    const v = el('div', `sf-legend__v${c.dim ? ' is-dim' : ''}`);
    v.setAttribute('data-category', c.name);
    const ico = el('button', 'sf-legend__ico');
    ico.type = 'button';
    ico.setAttribute('aria-label', `Colour of ${c.name}`);
    ico.style.background = c.fill;
    ico.style.borderColor = c.line;
    ico.addEventListener('click', (event) => { if (event.stopPropagation) event.stopPropagation(); ctx.openPalette(c.name, ico); });
    const name = el('button', 'sf-legend__name', c.name);
    name.type = 'button';
    name.addEventListener('click', (event) => ctx.markHub([[ctx.words('color'), c.name]], c.ids, event));
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

