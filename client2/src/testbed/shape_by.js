// SHAPE BY - the root part's (base set 7-b, docs/architecture/ROOT_PART_BASE_SET.md; owner «점을 찍는 부품들은 모두 SHAPE
// BY»): a kind that draws points (`points: true`) holds the Shape by slot; the root reads each row's category and decides
// its shape once - the declaration's (`shapes`: {category: shape}) or the next shape no category holds, kept in the
// declaration as Color by keeps its colours (color_by.js assignLooks, the one rule for both). The kind draws the shape
// it is handed; the legend draws the same names.

import { assignLooks } from './color_by.js';

/** The Shape by slot a points kind holds. */
export const SHAPE_SLOT = Object.freeze({ key: 'shape', label: 'Shape by', category: true });
/** The shapes, in the order categories are given them - ECharts' symbol names; the legend's glyphs are these. */
export const SHAPES = Object.freeze(['circle', 'rect', 'triangle', 'diamond', 'roundRect', 'pin', 'arrow']);
const ONE = SHAPES[0];

/** The Shape by legend's look: a category's shape - the same name the kind draws. */
export const SHAPE_LEGEND = Object.freeze({
  key: 'shape', title: 'Shape by:',
  icon(c, ctx, el) {
    const ico = el('span', 'sf-legend__shape');
    ico.setAttribute('data-shape', c ? c.shape : ONE);
    return ico;
  },
});

/**
 * Each row's shape by the declaration's Shape by: a row reading one value is in that category; none, several or no slot -
 * the one shape.
 * @returns {{any: boolean, of: Map<string, {shape, category}>, categories: Array<{name, shape, ids}>, assigned: Record<string, string>}}
 */
export function shapesOf(rows, decl) {
  const own = (decl && decl.shapes) || {};
  const categoryOf = (row) => (row.reads.shape && row.reads.shape.state === 'one' ? String(row.reads.shape.value) : null);
  const seen = [...new Set(rows.map(categoryOf).filter((c) => c !== null))];
  const assigned = assignLooks(seen, own, SHAPES);
  const categories = [...seen].sort().map((name) => ({ name, shape: own[name] || assigned[name], ids: rows.filter((r) => categoryOf(r) === name).map((r) => r.id) }));
  const byName = new Map(categories.map((c) => [c.name, c]));
  const of = new Map(rows.map((r) => { const c = byName.get(categoryOf(r)); return [r.id, c ? { shape: c.shape, category: c.name } : { shape: ONE, category: null }]; }));
  return { any: Boolean(decl && decl.encode && decl.encode.shape), of, categories, assigned };
}

/** A mark's shape - its rows' when they share one category, else the one shape. */
export function shapeOfIds(shapes, ids) {
  const seen = [...new Set(ids.map((id) => (shapes.of.get(id) || {}).category))];
  return seen.length === 1 && shapes.of.get(ids[0]) ? shapes.of.get(ids[0]).shape : ONE;
}
