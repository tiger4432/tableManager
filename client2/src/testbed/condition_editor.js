// One condition's control (lead d1b3c1b7f): a number slot - a range, from and to; a text slot - its values checked, each
// with its count; «Include empty». The filters panel and a part's own Filter draw this same control.

import { numberOf } from '../walk/reach_table.js';
import { valueText } from './slot.js';

/** A text slot with more values than this draws its most counted this many and a search box (owner 10-20: 34,616 boxes at
 *  once held the page); a value not drawn keeps its check. */
export const FILTER_TOP = 20;

/** A condition's identity - its row type and its slot - so one slot holds one condition. */
export const conditionKey = (c) => JSON.stringify([c.row, c.steps || [], c.value, c.end || null, c.endTypes || null, c.reduce || null, c.expr || null]);

/** A new condition on a slot summary ({row, slot, values: [[v, n]], empty}): everything kept. */
export function conditionFor(summary) {
  const numbers = summary.values.length > 0 && summary.values.every(([v]) => numberOf(v) !== null);
  const base = { row: summary.row, steps: summary.slot.steps || [], value: summary.slot.value, end: summary.slot.end, endTypes: summary.slot.endTypes,
    reduce: summary.slot.reduce, expr: summary.slot.expr, words: summary.words, empty: true };
  if (numbers) {
    const xs = summary.values.map(([v]) => numberOf(v));
    return { ...base, range: { min: Math.min(...xs), max: Math.max(...xs) } };
  }
  return { ...base, values: summary.values.map(([v]) => v) };
}

/** A condition in words - «void_ratio 0.1 – 0.4» · «recipe: 3 of 7». */
export function conditionWords(c, total) {
  if (c.range) return `${c.words} ${c.range.min} – ${c.range.max}`;
  if (c.period) return `${c.words} ${c.period.from || ''} – ${c.period.to || ''}`;
  if (Array.isArray(c.values)) return `${c.words}: ${c.values.length}${total ? ` of ${total}` : ''}`;
  return c.words;
}

/**
 * The control. `onChange(next)` hears every edit at once (Spotfire filters apply as they move).
 * @param {{row, words, slot, values: Array<[*, number]>, empty: number}} summary
 * @param {{search?: string, onSearch?: (text) => void}} [view]  the search box's text, kept by the caller across drawings
 */
export function drawCondition(doc, summary, condition, onChange, view = {}) {
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const c = condition || conditionFor(summary);
  const box = el('div', 'sf-filter');
  const head = el('div', 'sf-filter__h', summary.words);
  head.title = summary.words;
  head.setAttribute('data-clip-ok', '');
  box.append(head);
  if (c.range) {
    const line = el('div', 'sf-filter__range');
    for (const end of ['min', 'max']) {
      const input = el('input', 'sf-filter__num');
      input.type = 'number';
      input.value = String(c.range[end]);
      input.setAttribute('aria-label', end === 'min' ? 'From' : 'To');
      input.addEventListener('change', () => {
        const x = numberOf(input.value);
        onChange({ ...c, range: { ...c.range, [end]: x === null ? undefined : x } });
      });
      line.append(input);
    }
    box.append(line);
  } else {
    const kept = new Set((c.values || []).map((v) => JSON.stringify(v)));
    const line = (v, n) => {
      const label = el('label', 'sf-filter__v');
      const check = el('input');
      check.type = 'checkbox';
      check.checked = kept.has(JSON.stringify(v));
      check.addEventListener('change', () => {
        const next = summary.values.map(([x]) => x).filter((x) => (JSON.stringify(x) === JSON.stringify(v) ? check.checked : kept.has(JSON.stringify(x))));
        onChange({ ...c, values: next });
      });
      // one line - a long value cut with its whole words in its tooltip (lead 10-14: two lines ran over the next)
      const said = valueText(v, summary.time);
      const words = el('span', 'sf-filter__t', said);
      words.title = said;
      words.setAttribute('data-clip-ok', '');
      label.append(check, words, el('span', 'sf-filter__n', String(n)));
      return label;
    };
    const many = summary.values.length > FILTER_TOP;
    const list = el('div', 'sf-filter__list');
    // the values the search matches, the most counted first when there are many; past FILTER_TOP, a count of the rest
    const fill = (text) => {
      const want = String(text || '').trim().toLowerCase();
      const matched = want ? summary.values.filter(([v]) => valueText(v, summary.time).toLowerCase().includes(want)) : summary.values;
      const shown = many ? [...matched].sort((x, y) => y[1] - x[1]).slice(0, FILTER_TOP) : matched;
      list.replaceChildren(...shown.map(([v, n]) => line(v, n)));
      if (matched.length > shown.length) list.append(el('div', 'sf-filter__more', `${matched.length - shown.length} more`));
    };
    if (many) {
      const search = el('input', 'sf-filter__search');
      search.type = 'search';
      search.placeholder = 'Search values';
      search.setAttribute('aria-label', `Search ${summary.words}`);
      search.value = view.search || '';
      search.addEventListener('input', () => { if (view.onSearch) view.onSearch(search.value); fill(search.value); });
      box.append(search);
    }
    box.append(list);
    fill(many ? view.search : '');
  }
  const empty = el('label', 'sf-filter__v');
  const check = el('input');
  check.type = 'checkbox';
  check.checked = c.empty !== false;
  check.addEventListener('change', () => onChange({ ...c, empty: check.checked }));
  empty.append(check, el('span', '', 'Include empty'), el('span', 'sf-filter__n', String(summary.empty || 0)));
  box.append(empty);
  return box;
}
