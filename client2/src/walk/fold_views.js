// A folded lump seen another way (lead 793017c62 · edcc0568c · 5ef260acf, owner 10-07): as a table of its nodes or
// as plain points (x the time a value was said, y the value), with the walk's start branch drawn over the rest -
// to see at a glance whether what the start reached stands apart. The pure half: what the views read and draw.
import { parseServerInstant } from '../server_time.js';

/** Days around the start branch's times that a definition node's one more step reads (lead 10-08). Named here
 *  until the demo is over, then a declaration. */
export const AROUND_DAYS = 7;
/** The one more step's node budget, inside the walk's node_limit range (lead 10-08). Same: a declaration later. */
export const STEP_NODE_LIMIT = 200;

/** The ways a lump is seen, in the order its switch shows them; the first is the lump's own list (today's). */
export const FOLD_VIEWS = Object.freeze(['Nodes', 'Table', 'Trend']);

const DAY_MS = 24 * 60 * 60 * 1000;

/** What each lump is seen as, its y and what was walked for it - nothing yet. A part holds its own. */
export function openLumpSeen() {
  return { kind: new Map(), y: new Map(), data: new Map(), from: new Map(), choices: new Map() };
}

/** Where this browser keeps, per members' type, the type a lump's points were taken from and the value attribute. */
const PICKS_KEY = 'walk.lumpPointsFrom';

/** What this browser remembers for a members' type - `{from, y}` - or nothing (no storage, none kept, unreadable). */
export function rememberedPick(storage, membersType) {
  try {
    return JSON.parse(storage.getItem(PICKS_KEY) || '{}')[membersType] || null;
  } catch (e) {
    return null;
  }
}

/** Keep a pick for a members' type; a browser that keeps nothing asks for the pick again next time. */
export function rememberPick(storage, membersType, pick) {
  try {
    const all = JSON.parse(storage.getItem(PICKS_KEY) || '{}');
    all[membersType] = { ...(all[membersType] || {}), ...pick };
    storage.setItem(PICKS_KEY, JSON.stringify(all));
  } catch (e) {
    // Nothing kept: the picker shows again.
  }
}

/** A value as a number, or null: the server sends text, so '10.1' reads as 10.1 and 'S1' or '' as nothing. */
export function numberOf(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !value.trim()) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** The attributes some of these nodes hold a number in, in the order they are first met - the y choices. */
export function valueAttributes(nodes) {
  const out = [];
  for (const node of nodes || []) {
    for (const [name, value] of Object.entries((node && node.attributes) || {})) {
      if (!out.includes(name) && numberOf(value) !== null) out.push(name);
    }
  }
  return out;
}

/** When a node's attribute was said, in ms: the world entry that says the value shown, else the first. */
export function saidAt(node, attribute) {
  const saids = ((node && node.attributesByWorld) || {})[attribute] || [];
  const value = ((node && node.attributes) || {})[attribute];
  const said = saids.find((s) => s && s.value === value) || saids[0];
  const at = said ? parseServerInstant(said.occurred_at) : null;
  return at ? at.getTime() : null;
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
 * The points one attribute gives: every node holding it, at the time it was said. A value that does not read as a
 * number, one said at no time, or a node without it at all, is not a point - each is counted, so the view can say
 * how many it left out.
 */
export function pointsOf(nodes, attribute, lit) {
  const points = [];
  let notNumber = 0;
  let noTime = 0;
  let noValue = 0;
  for (const node of nodes || []) {
    const attrs = (node && node.attributes) || {};
    // A node the walk brought without it (a claims cut leaves nodes bare, lead 161757c35) is counted, not dropped.
    if (!(attribute in attrs)) { noValue += 1; continue; }
    const v = numberOf(attrs[attribute]);
    if (v === null) { notNumber += 1; continue; }
    const t = saidAt(node, attribute);
    if (t === null) { noTime += 1; continue; }
    points.push({ id: node.id, label: node.label, t, v, lit: Boolean(lit && lit.has(node.id)) });
  }
  points.sort((a, b) => a.t - b.t);
  return { points, notNumber, noTime, noValue };
}

/** The window a definition node's one more step reads: the start branch's times, AROUND_DAYS each side; none known,
 *  no window (the walk then reads all time - the view says so). */
export function windowAround(times) {
  const known = (times || []).filter((t) => Number.isFinite(t));
  if (!known.length) return null;
  return { since: Math.min(...known) - AROUND_DAYS * DAY_MS, until: Math.max(...known) + AROUND_DAYS * DAY_MS };
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
