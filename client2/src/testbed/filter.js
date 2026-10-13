// The one filter (lead d1b3c1b7f · 5835e6714, owner 「시스템 마킹 + 필터 -> 부품이 마킹 라우트해서 받음 -> 부품 내 최종 필터」):
// a condition is a value slot of a node type plus what it keeps - a number's range, a text's checked values, a time's
// period, and whether an empty value passes. The system filter's conditions (start side and received side) and a part's
// own final ones are all kept by `keepNodes`; no part filters by any other code.
//
// condition  { row, steps, value: {on, name}, end?, endTypes?, reduce?, range?: {min?, max?}, values?: Array,
//              period?: {from?, to?}, empty?: boolean }
//            row - the node type it holds for; nodes of other types pass it untouched

import { numberOf } from '../walk/reach_table.js';
import { readSlot } from './slot.js';

const spelling = (v) => JSON.stringify(v);

/** Whether one value passes a condition's test. A list of values passes when any of its items does. */
export function valuePasses(condition, value) {
  if (value === null || value === undefined) return condition.empty !== false;
  if (condition.range) {
    const x = numberOf(value);
    if (x === null) return false;
    const { min, max } = condition.range;
    return !(Number.isFinite(min) && x < min) && !(Number.isFinite(max) && x > max);
  }
  if (condition.period) {
    const t = Date.parse(value);
    if (!Number.isFinite(t)) return false;
    const from = condition.period.from ? Date.parse(condition.period.from) : NaN;
    const to = condition.period.to ? Date.parse(condition.period.to) : NaN;
    return !(Number.isFinite(from) && t < from) && !(Number.isFinite(to) && t >= to);
  }
  if (Array.isArray(condition.values)) return condition.values.some((v) => spelling(v) === spelling(value));
  return true;
}

/** Whether node `id` passes one condition: its slot read, then each value it holds (several: any). */
export function nodePasses(index, inside, id, condition, oneValued, marked = null) {
  const node = index.nodes.get(id);
  if (!node || node.type !== condition.row) return true;
  const read = readSlot(index, inside, id, condition, oneValued && oneValued(condition), marked);
  if (read.state === 'missing' || read.state === 'empty') return condition.empty !== false;
  const values = read.state === 'one' ? [read.value] : read.values;
  return values.some((v) => valuePasses(condition, v));
}

/**
 * THE filter: the ids that pass every condition, and how many each condition list dropped.
 * @returns {{kept: string[], dropped: number}}
 */
export function keepNodes(index, inside, ids, conditions, oneValued = null, marked = null) {
  const list = (conditions || []).filter(Boolean);
  if (!list.length) return { kept: [...ids], dropped: 0 };
  // marked - an expression condition's Marked() (the page's marking layer, handed in by the root)
  const kept = ids.filter((id) => list.every((c) => nodePasses(index, inside, id, c, oneValued, marked)));
  return { kept, dropped: ids.length - kept.length };
}
