// The slot picker - a pill's dropdown (lead b19236b03): the walk table's «+ Column» choice (reach_table routesFrom ·
// valuesAt, the same functions - no second list), then how the values fold, or a Custom expression (src/expression.js,
// lead 10-13). One open at a time, made by the page.

import { routesFrom, valuesAt, waysOf, WAYS_A_CELL } from '../walk/reach_table.js';
import { REDUCES } from './aggregate.js';
import { readSlot, isExpression, nameValue, wayWords } from './slot.js';
import { compile, ExpressionError } from '../expression.js';
import { setDisabledReason } from '../disabled_reason.js';
import { fitUnder } from '../dropdown.js';

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

/** Why an expression cannot stand for a part's slot, or '' - the calculator's sentence, or a [name] none of the rows has
 *  as its own value. */
export function expressionRefusal(part, text) {
  const compiled = compile(text);
  if (!compiled.ok) return compiled.why;
  const rows = part.rowIds || [];
  for (const name of compiled.names) {
    try {
      if (!rows.some((id) => nameValue(part.index, part.inside, id, name).value)) return `No value named ${name} on ${part.decl.row}`;
    } catch (e) {
      if (e instanceof ExpressionError) return e.message;
      throw e;
    }
  }
  return '';
}

/** Custom expression's first text when a route is chosen (lead 10-13): the route and value in the brackets' spelling,
 *  its reduce around it - [in_container~.x], Avg([measures.value]); a route with no value yet ends at its «.»; none,
 *  nothing. «Ends at» has no spelling in the brackets: the expression reads every end. */
export function startingExpression(slot) {
  const way = wayWords(slot && slot.steps);
  if (!slot || (!way && !slot.value)) return '';
  const name = slot.value ? (slot.value.on === 'label' ? 'name' : slot.value.name) : '';
  const ref = `[${way ? `${way}.` : ''}${name}]`;
  return slot.value && slot.reduce ? `${slot.reduce}(${ref})` : slot.value ? ref : `[${way}.`;
}

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
    // Drawn again on every pick, so placed again: the one placement (dropdown.js fitUnder, lead 72b2d7f8f) - an axis
    // pill at the foot of the page opens its picker above it.
    const show = (box) => {
      this.host.replaceChildren(box);
      if (anchor && anchor.getBoundingClientRect) fitUnder(this.host, anchor, { align: 'left', gap: 4 });
    };
    const draw = (current, writing) => {
      const box = el('div', 'sf-pop');
      if (!part.index) { box.append(el('div', 'sf-pop__why', 'Walk first - nothing to pick from')); show(box); return; }
      // An expression slot picks no route: the columns start empty, the expression row stands open.
      const chosen = isExpression(current) ? { steps: [], value: null } : current;
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
      // A slot's choices that are not a value (the scatter's Marker by: «(Node)», «(Value record)»): each a declaration field.
      const desc = part.slotList().find((s) => s.key === key) || {};
      for (const choice of desc.choices || []) {
        const it = el('button', 'sf-pop__it', choice.words);
        it.type = 'button';
        it.addEventListener('click', () => { part.setDeclaration({ ...part.declaration(), ...choice.patch }); this.close(); });
        folds.append(it);
      }
      const none = el('button', 'sf-pop__it', '(None)');
      none.type = 'button';
      none.addEventListener('click', () => { part.setSlot(key, null); this.close(); });
      const custom = el('button', `sf-pop__it${isExpression(current) ? ' is-on' : ''}`, 'Custom expression…');
      custom.type = 'button';
      custom.addEventListener('click', () => draw(current, isExpression(current) ? current.expr : startingExpression(chosen)));
      folds.append(none, custom);
      if (isExpression(current) || writing !== undefined) box.append(expressionRow(writing !== undefined ? writing : current.expr));
      show(box);
    };
    const expressionRow = (text) => {
      const row = el('div', 'sf-pop__edit');
      const line = el('div', 'sf-pop__line');
      const input = el('input', 'sf-pop__expr');
      input.type = 'text';
      input.value = text;
      input.spellcheck = false;
      input.setAttribute('aria-label', 'Expression');
      const why = el('div', 'sf-pop__why');
      const apply = () => {
        const said = expressionRefusal(part, input.value);
        if (said) { why.textContent = said; return; }
        const next = { expr: input.value.trim(), words: [input.value.trim()] };
        part.setSlot(key, next);
        draw(next);
      };
      input.addEventListener('keydown', (event) => { if (event.key === 'Enter') apply(); });
      const ok = el('button', 'sf-btn', 'OK');
      ok.type = 'button';
      ok.addEventListener('click', apply);
      line.append(input, ok);
      row.append(el('div', 'sf-pop__lab', 'Expression'), line, why);
      return row;
    };
    this.host.style.display = '';
    draw(slot || { steps: [], value: null });
  }
}
