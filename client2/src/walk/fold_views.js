// A folded lump seen another way (lead 793017c62 · edcc0568c · 5ef260acf, owner 10-07): opened as a step of the page's
// table (lead 10-11 E2b) and, in its own place, its numbers as plain points (x the time, y the value) with the walk's
// start branch drawn over the rest. The pure half: what the lump's read is and how its points are drawn.
import { walkTableView } from './table_view.js';
import { rowsPoints } from './trend.js';

/** A value as a number, or null: the server sends text, so '10.1' reads as 10.1 and 'S1' or '' as nothing. */
export function numberOf(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !value.trim()) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * THE ONE «start branch» QUESTION (lead 83ff2c3e6 · 5ef260acf): the nodes the walk reached from its first start -
 * every node any answer of the first step brought. The table, the points and the picture all ask this set.
 */
export function startBranch(steps) {
  const first = (steps || [])[0];
  return new Set(((first && first.results) || []).flatMap((r) => (Array.isArray(r.nodes) ? r.nodes : []))
    .map((n) => n.id));
}

/**
 * A lump's answer (lead 10-11 E2b): what the steps brought, narrowed to its owner, its members and the edges between
 * them along its predicate - nothing walked. The page opens it as a step; the thumbnail reads it the same way.
 */
export function lumpAnswer(results, lump) {
  const keep = new Set([lump.owner, ...lump.members]);
  const nodes = new Map();
  const edges = new Map();
  for (const r of results || []) {
    for (const n of (r && r.nodes) || []) if (keep.has(n.id) && !nodes.has(n.id)) nodes.set(n.id, n);
    for (const e of (r && r.edges) || []) {
      const far = e.source === lump.owner ? e.target : e.target === lump.owner ? e.source : null;
      if (e.predicate === lump.predicate && far !== null && lump.members.includes(far) && !edges.has(e.id)) edges.set(e.id, e);
    }
  }
  return { ok: true, state: 'ready', nodes: [...nodes.values()], edges: [...edges.values()] };
}

/**
 * A lump's points as its page step's Trend reads them (lead 10-11 E2b): its answer's table from its owner, the members'
 * section, its first value column, every member's walked reads - numbers only, the start branch's lit. No reading of
 * its own: the same table, the same reads, nothing paged.
 */
export function lumpPoints(answer, lump, entities, predicates, lit) {
  const view = walkTableView(answer, entities, predicates, undefined, { positive: [lump.owner], negative: [] });
  const section = view.sections.find((x) => x.type === lump.farType);
  const column = section && section.columns[0];
  if (!column) return [];
  return rowsPoints(view, section.rows.map((r) => r.id), column)
    .map((p) => ({ t: p.t, v: numberOf(p.value), lit: Boolean(lit && lit.has(p.row)) }))
    .filter((p) => Number.isFinite(p.t) && p.v !== null);
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

/**
 * THE ONE DRAWING of points, the big view's and the lump's picture alike: an SVG, the rest faded first and the
 * start branch over them (lead 5ef260acf - never hidden under the rest). No line, band or statistic (edcc0568c).
 * `colours` are resolved token values (an SVG used as an image reads no page variable).
 */
export function pointsSvg(points, { width, height, pad, r, colours, axes }) {
  const open = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
  if (!points.length) return `${open}</svg>`;
  const ts = points.map((p) => p.t);
  const vs = points.map((p) => p.v);
  const [t0, t1] = [Math.min(...ts), Math.max(...ts)];
  const [v0, v1] = [Math.min(...vs), Math.max(...vs)];
  // The axis words stand left of the dots, never under the first one.
  const left = axes ? pad * 6 : pad;
  const x = (t) => (t1 === t0 ? (left + width - pad) / 2 : left + ((t - t0) / (t1 - t0)) * (width - pad - left));
  const y = (v) => (v1 === v0 ? height / 2 : height - pad - ((v - v0) / (v1 - v0)) * (height - 2 * pad));
  const dot = (p) => (p.lit
    ? `<circle cx="${x(p.t).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="${r * 1.25}" fill="${esc(colours.lit)}" stroke="${esc(colours.ring)}" stroke-width="1"/>`
    : `<circle cx="${x(p.t).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="${r}" fill="${esc(colours.rest)}" opacity="0.4"/>`);
  const rest = points.filter((p) => !p.lit).map(dot);
  const lit = points.filter((p) => p.lit).map(dot);
  const text = (tx, ty, s, anchor) => `<text x="${tx}" y="${ty}" font-size="11" font-family="${esc(colours.font)}" fill="${esc(colours.text)}" text-anchor="${anchor}">${esc(s)}</text>`;
  const labels = axes ? [text(left - pad, pad + 4, v1, 'end'), text(left - pad, height - pad, v0, 'end')] : [];
  return open + [...labels, ...rest, ...lit].join('') + '</svg>';
}

/** The same drawing as an image address, for a picture that cannot hold markup (the lump's background). */
export function svgAddress(svg) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
