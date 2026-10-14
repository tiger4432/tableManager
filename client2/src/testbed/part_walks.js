// A PART'S WALKS (owner 10-14 «행 걷기 + 값 걷기»): a row walk - from its start along its route, carrying the row type
// (and the start's), to its end - and a value walk a slot - from the rows along the slot's ways, carrying the types its
// columns read, to its end. A walk is not asked when one in hand covers it (owner «이미 로드된 그래프면 받지 말 것»).
// An answer is read as its nodes and its edges' ends (a type it did not carry stands on a way by its id) - never by its
// evidence, which has no direction (lead 10-14: core dies read a bonding wafer through a bonded_from taken backwards).

import { columnsOf, isExpression, wayOf } from './slot.js';
import { compile } from '../expression.js';
import { typeOfStart } from './route.js';
import { truncationAxes } from '../rnd_board/api.js';

/** A page cut - an axis of its truncated (the board's one reading, rnd_board/api.js; its steps are asked, so the depth
 *  reached is not a cut) - with no next page to take it on. */
const cutPage = (a) => Boolean(a) && !(a.more && a.more.resume) && (truncationAxes(a.truncated, { hopsChosen: true }) || []).length > 0;

/** How many rows a value walk starts from at once - the request's query stays under 64 KB (lead-board-10b: past it
 *  the box read seed ids broken, 422; 500 die ids are 56 KB). */
export const SEED_CHUNK = 500;
/** The pages one walk asks at most - past it, cut. */
export const MAX_PAGES = 50;

/** Answers as one readable answer: their nodes and edges once each, an edge's end the answer did not carry a node by its
 *  id - THE one place a walk's answer is read. */
export function readable(answers) {
  const nodes = new Map();
  const edges = new Map();
  for (const a of answers) {
    for (const n of (a && a.nodes) || []) if (!nodes.has(n.id)) nodes.set(n.id, n);
    for (const e of (a && a.edges) || []) { const k = e.id || JSON.stringify(e); if (!edges.has(k)) edges.set(k, e); }
  }
  for (const e of edges.values()) {
    for (const id of [e.source, e.target]) if (id && !nodes.has(id)) nodes.set(id, { id, type: typeOfStart(id), label: id, keys: {}, attributes: {}, carried: false });
  }
  const cut = answers.find(cutPage);
  const last = answers.length ? answers[answers.length - 1] : null;
  return { nodes: [...nodes.values()], edges: [...edges.values()], truncated: ((cut || last) && (cut || last).truncated) || null };
}

/** The types a column reads at its end - its steps taken over the vocabulary from the row type; unknown - null (carry all). */
function endTypes(column, rowType, vocabulary) {
  if (column.endTypes && column.endTypes.length) return [...column.endTypes];
  if (column.end) { const t = typeOfStart(column.end); return t ? [t] : null; }
  const preds = new Map(((vocabulary && vocabulary.predicates) || []).map((p) => [p.name, p]));
  let at = [rowType];
  for (const step of column.steps || []) {
    const p = preds.get(step.predicate);
    if (!p) return null;
    const objects = (p.object && p.object.types) || [];
    at = step.direction === 'incoming' ? (p.subjects || []) : objects;
    if (!at.length) return null;
  }
  return at;
}

/** A slot's value walk - its columns' ways together: follow, hops and the types to carry; a slot of the row's own values
 *  only - null (nothing to walk). */
export function valueAsk(slot, rowType, vocabulary) {
  const ways = [];
  for (const col of columnsOf(slot)) {
    if (isExpression(col)) {
      const c = compile(col.expr);
      for (const w of c.ok ? c.names.map(wayOf).filter(Boolean) : []) ways.push({ steps: w.steps });
    } else if (Array.isArray(col.steps) && col.steps.length) ways.push(col);
  }
  if (!ways.length) return null;
  const follow = [...new Set(ways.flatMap((w) => w.steps.map((s) => s.predicate)))].sort();
  const hops = Math.max(...ways.map((w) => w.steps.length));
  const types = ways.map((w) => endTypes(w, rowType, vocabulary));
  const collect = types.some((t) => !t) ? null : [...new Set(types.flat())].sort();
  return { follow, hops, collect };
}

/** Whether a walk in hand answers an ask - THE one judgment: the same start, the ask's types among those it carried (all,
 *  none named), its predicates among those it followed, its steps no more, and walked to its end. */
export function covers(held, ask) {
  if (!held || !held.complete) return false;
  const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
  if (!same(held.seeds, ask.seeds)) return false;
  if (held.collect && (!ask.collect || !ask.collect.every((t) => held.collect.includes(t)))) return false;
  if (!(ask.follow || []).every((p) => (held.follow || []).includes(p))) return false;
  return ask.hops <= held.hops;
}

/** The slot keys whose declaration differs between two encodes. */
export function changedSlots(before, after) {
  const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
  return [...keys].filter((k) => JSON.stringify((before || {})[k] || null) !== JSON.stringify((after || {})[k] || null));
}

/** Ids in runs of `n`. */
export const chunks = (ids, n) => { const out = []; for (let i = 0; i < ids.length; i += n) out.push(ids.slice(i, i + n)); return out; };

/**
 * One walk to its end - each page its answer's more.resume - each page handed to `onPage` as it comes.
 * @returns {Promise<{answers: Array, complete: boolean, why: string|null, aborted: boolean}>}
 */
export async function walkToEnd(fetchWalk, params, signal, onPage) {
  const answers = [];
  let resume = null;
  for (let n = 0; n < MAX_PAGES; n += 1) {
    let res;
    try {
      res = await fetchWalk({ ...params, resumable: true, ...(resume ? { resume } : {}), signal });
    } catch (e) {
      if (signal && signal.aborted) return { answers, complete: false, why: null, aborted: true };
      return { answers, complete: false, why: String((e && e.message) || e), aborted: false };
    }
    if (signal && signal.aborted) return { answers, complete: false, why: null, aborted: true };
    if (!res || !res.ok) {
      const d = res && res.detail && res.detail.detail;
      const said = d && typeof d === 'object' ? (d.reason || d.message) : d;
      return { answers, complete: false, why: said || `Walk refused (${res && res.status})`, aborted: false, refused: answers.length === 0, res };
    }
    answers.push(res.body);
    if (onPage) onPage(answers);
    resume = res.body && res.body.more && res.body.more.resume;
    if (!resume) return cutPage(res.body) ? { answers, complete: false, why: 'cut', aborted: false } : { answers, complete: true, why: null, aborted: false };
  }
  return { answers, complete: false, why: `stopped after ${MAX_PAGES} pages`, aborted: false };
}
