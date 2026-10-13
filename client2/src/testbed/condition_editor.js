// One condition's control (lead d1b3c1b7f): a number slot - a range, from and to; a text slot - its values checked, each
// with its count; «Include empty». The filters panel and a part's own Filter draw this same control.

import { numberOf } from '../walk/reach_table.js';

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
 */
export function drawCondition(doc, summary, condition, onChange) {
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const c = condition || conditionFor(summary);
  const box = el('div', 'sf-filter');
  box.append(el('div', 'sf-filter__h', summary.words));
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
    for (const [v, n] of summary.values) {
      const label = el('label', 'sf-filter__v');
      const check = el('input');
      check.type = 'checkbox';
      check.checked = kept.has(JSON.stringify(v));
      check.addEventListener('change', () => {
        const next = summary.values.map(([x]) => x).filter((x) => (JSON.stringify(x) === JSON.stringify(v) ? check.checked : kept.has(JSON.stringify(x))));
        onChange({ ...c, values: next });
      });
      label.append(check, el('span', '', String(v)), el('span', 'sf-filter__n', String(n)));
      box.append(label);
    }
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
