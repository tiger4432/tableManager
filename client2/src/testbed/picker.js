// The slot picker - a pill's dropdown (lead b19236b03): the walk table's «+ Column» choice (reach_table routesFrom ·
// valuesAt, the same functions - no second list), then how the values fold. One open at a time, made by the page.

import { routesFrom, valuesAt, waysOf, WAYS_A_CELL } from '../walk/reach_table.js';
import { REDUCES } from './aggregate.js';
import { readSlot } from './slot.js';
import { setDisabledReason } from '../disabled_reason.js';

/** The routes a part's rows take, its own values first (no step). */
export function routeChoices(index, rows) {
  return [{ steps: [], words: ['(row)'], to: [] }, ...routesFrom(index, rows)];
}

/** The nodes a route ends at from the rows, each once with its label - a slot may end at one (the walk table's column
 *  `end`: «measures → bond_temp · value»). Past `most`, none offered: the route is read whole. */
export function endChoices(index, rows, steps, most = 40) {
  if (!steps || !steps.length) return [];
  const ids = [...new Set(waysOf(index, null, rows, steps, WAYS_A_CELL * 20).ends.map((e) => e.node))];
  if (ids.length > most) return [];
  return ids.map((id) => ({ id, label: (index.nodes.get(id) || {}).label || id })).sort((a, b) => (a.label < b.label ? -1 : a.label > b.label ? 1 : 0));
}

/** How many rows read the slot as several values with no reduce - the line under the reduce chips. */
export function severalCount(part, slot) {
  if (!part.index || !slot) return 0;
  return (part.rowIds || []).filter((id) => readSlot(part.index, part.inside, id, slot, part.oneValued(slot)).state === 'several').length;
}

const sameSteps = (a, b) => JSON.stringify(a || []) === JSON.stringify(b || []);

export class SlotPicker {
  constructor(host, deps) {
    this.host = host;
    this.doc = (deps || {}).doc;
    this.openFor = null;
  }

  close() {
    this.openFor = null;
    this.host.replaceChildren();
    this.host.style.display = 'none';
  }

  /** Open under `anchor` for `part`'s slot `key`. A pick sets the slot at once (Spotfire applies as you choose). */
  open({ part, key, anchor }) {
    if (this.openFor && this.openFor.part === part && this.openFor.key === key) { this.close(); return; }
    this.openFor = { part, key };
    const doc = this.doc;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    const slot = (part.decl.encode || {})[key] || null;
    const rows = part.rowIds || [];
    const draw = (chosen) => {
      const box = el('div', 'sf-pop');
      if (!part.index) { box.append(el('div', 'sf-pop__why', 'Walk first - nothing to pick from')); this.host.replaceChildren(box); return; }
      // Three columns side by side - the route, then where it ends and its value, then how they fold.
      const [routes, at, folds] = [el('div', 'sf-pop__col'), el('div', 'sf-pop__col'), el('div', 'sf-pop__col')];
      box.append(routes, at, folds);
      routes.append(el('div', 'sf-pop__lab', 'Route'));
      for (const route of routeChoices(part.index, rows)) {
        const it = el('button', `sf-pop__it${sameSteps(route.steps, chosen.steps) ? ' is-on' : ''}`, route.words.join(' · '));
        it.type = 'button';
        it.addEventListener('click', () => draw({ ...chosen, steps: route.steps, end: undefined, value: null }));
        routes.append(it);
      }
      const ends = endChoices(part.index, rows, chosen.steps);
      if (ends.length) {
        at.append(el('div', 'sf-pop__lab', 'Ends at'));
        for (const end of [{ id: undefined, label: '(any)' }, ...ends]) {
          const it = el('button', `sf-pop__it${chosen.end === end.id ? ' is-on' : ''}`, end.label);
          it.type = 'button';
          it.addEventListener('click', () => draw({ ...chosen, end: end.id, value: null }));
          at.append(it);
        }
      }
      if (ends.length) at.append(el('hr', 'sf-pop__hr'));
      at.append(el('div', 'sf-pop__lab', 'Value'));
      const values = valuesAt(part.index, rows, chosen.steps || []);
      if (!values.length) at.append(el('div', 'sf-pop__why', 'No value on this route'));
      for (const value of values) {
        const on = chosen.value && chosen.value.on === value.on && chosen.value.name === value.name;
        const it = el('button', `sf-pop__it${on ? ' is-on' : ''}`, value.name);
        it.type = 'button';
        it.append(el('span', 'sf-pop__n', value.on));
        it.addEventListener('click', () => {
          const far = chosen.end ? (part.index.nodes.get(chosen.end) || {}).label || chosen.end : null;
          const next = { steps: chosen.steps || [], end: chosen.end, value, reduce: chosen.reduce || undefined, words: [far ? `${far} · ${value.name}` : value.name] };
          part.setSlot(key, next);
          draw(next);
        });
        at.append(it);
      }
      folds.append(el('div', 'sf-pop__lab', 'Reduce'));
      const chips = el('div', 'sf-pop__reds');
      for (const r of [null, ...REDUCES]) {
        const chip = el('button', `sf-pop__red${(chosen.reduce || null) === r ? ' is-on' : ''}`, r || 'None');
        chip.type = 'button';
        setDisabledReason(chip, chosen.value ? null : 'Pick a value first');
        chip.addEventListener('click', () => {
          const next = { ...chosen, reduce: r || undefined };
          part.setSlot(key, next);
          draw(next);
        });
        chips.append(chip);
      }
      folds.append(chips);
      const several = chosen.value ? severalCount(part, chosen) : 0;
      if (several) folds.append(el('div', 'sf-pop__why', `${several} rows with several values`));
      folds.append(el('hr', 'sf-pop__hr'));
      const none = el('button', 'sf-pop__it', '(None)');
      none.type = 'button';
      none.addEventListener('click', () => { part.setSlot(key, null); this.close(); });
      const custom = el('button', 'sf-pop__it', 'Custom expression…');
      custom.type = 'button';
      setDisabledReason(custom, 'Waits for contracts/expression/vectors.json');
      folds.append(none, custom);
      this.host.replaceChildren(box);
    };
    draw(slot || { steps: [], value: null });
    this.host.style.display = '';
    const spot = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : null;
    if (spot) {
      const view = doc.documentElement ? doc.documentElement.clientWidth : 1440;
      this.host.style.left = `${Math.max(8, Math.min(spot.left, view - 760))}px`;
      this.host.style.top = `${spot.bottom + 4}px`;
    }
  }
}
