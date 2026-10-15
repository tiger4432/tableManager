// The slot picker - a pill's dropdown (lead b19236b03): the walk table's «+ Column» choice (reach_table routesFrom ·
// valuesAt, the same functions - no second list), then how the values fold, or a Custom expression (src/expression.js,
// lead 10-13). One open at a time, made by the page.

import { routesFrom, valuesAt, waysOf, WAYS_A_CELL, stepWords } from '../walk/reach_table.js';
import { routesFor } from './route.js';
import { REDUCES } from './aggregate.js';
import { readSlot, isExpression, nameValue, wayWords, columnsOf, slotWords } from './slot.js';
import { compile, ExpressionError } from '../expression.js';
import { setDisabledReason } from '../disabled_reason.js';
import { fitUnder } from '../dropdown.js';

/** The routes a part's rows take, its own values first (no step). */
export function routeChoices(index, rows) {
  return [{ steps: [], words: ['(row)'], to: [] }, ...routesFrom(index, rows)];
}

/** The routes the declaration offers from the row type that `held` (the walk in hand's) does not - each `unloaded`, its
 *  steps walked by the slot's value walk once picked (owner 10-15: rows of a type, and what hangs off it was not
 *  offered - the list read only the walk in hand, which ends at the rows). Up to `limit` steps, as `routesFrom`. */
export function declaredChoices(vocabulary, rowType, held, limit = 4) {
  if (!vocabulary || !rowType) return [];
  const predicates = new Map(((vocabulary.predicates) || []).map((p) => [p.name, p]));
  const joins = (name, a, b) => {
    const p = predicates.get(name);
    return p && (p.subjects || []).includes(a) && ((p.object && p.object.types) || []).includes(b);
  };
  const seen = new Set((held || []).map((r) => JSON.stringify(r.steps)));
  const out = [];
  for (const entity of vocabulary.entities || []) {
    for (const route of routesFor(vocabulary, rowType, entity.type)) {
      const chain = route.chain || [];
      if (!route.hops || route.hops > limit || chain.length !== route.hops + 1) continue;
      const steps = [];
      for (let i = 0; i + 1 < chain.length; i += 1) {
        const name = (route.follow || []).find((n) => joins(n, chain[i], chain[i + 1]) || joins(n, chain[i + 1], chain[i]));
        if (!name) break;
        steps.push({ predicate: name, direction: joins(name, chain[i], chain[i + 1]) ? 'outgoing' : 'incoming' });
      }
      // a step back down the predicate the one before climbed reaches siblings - the walk refuses it (`_goes_back_down`)
      const back = steps.some((s, i) => i > 0 && s.predicate === steps[i - 1].predicate && s.direction !== steps[i - 1].direction);
      const key = JSON.stringify(steps);
      if (steps.length !== route.hops || back || seen.has(key)) continue;
      seen.add(key);
      out.push({ steps, words: steps.map((s, i) => stepWords(s, chain[i + 1])), to: [chain[chain.length - 1]], unloaded: true });
    }
  }
  return out.sort((a, b) => a.steps.length - b.steps.length);
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
/** «time» with no value picked reads the name's - the way's last edge. */
const NAME_VALUE = Object.freeze({ on: 'label', name: 'name' });
const NO_TIME_HERE = 'No time on this route';

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
    if (this.unplace) this.unplace();
    this.unplace = null;
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
    // The pill it hangs under, alive: a pick draws the part and its pills again (owner 10-14: the picker flew to the top
    // left, placed under the pill drawn away) - the same part's same slot's pill nearest where the old one was.
    let at = anchor;
    let was = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : null;
    // in the same panel it was opened in (a tray's pill, the properties panel's); a slot gone from there (a table's
    // «+ Column» became a column) - its picker closes
    const panelOf = (n) => { const box = n && typeof n.closest === 'function' ? n.closest('[data-panel]') : null; return box ? box.getAttribute('data-panel') : null; };
    const home = panelOf(anchor);
    const live = () => {
      if (!at || at.isConnected !== false) return at;
      const id = (part.decl && part.decl.id) || '';
      const same = doc && doc.querySelectorAll ? [...doc.querySelectorAll('.sf-pill')].filter((p) => p.getAttribute('data-slot') === key && p.getAttribute('data-part') === id
        && (home === null || panelOf(p) === home)) : [];
      const gap = (p) => { const r = p.getBoundingClientRect ? p.getBoundingClientRect() : null; return r && was ? Math.abs(r.left - was.left) + Math.abs(r.top - was.top) : 0; };
      at = same.length ? same.sort((a, b) => gap(a) - gap(b))[0] : null;
      return at;
    };
    const place = () => {
      const pill = live();
      if (!pill) { if (anchor) this.close(); return; }
      if (!pill.getBoundingClientRect) return;
      fitUnder(this.host, pill, { align: 'left', gap: 4 });
      if (pill.isConnected !== false) was = pill.getBoundingClientRect();
    };
    // the window resized while it stands open - under its pill again
    if (this.unplace) this.unplace();
    const view = doc && doc.defaultView;
    if (view && view.addEventListener) {
      view.addEventListener('resize', place);
      this.unplace = () => view.removeEventListener('resize', place);
    }
    const show = (box) => {
      this.host.replaceChildren(box);
      place();
    };
    // A slot of several columns (`many`: a cross table's axes, Color by, Shape by - owner 10-14): the columns a row of
    // chips over the picker - one pressed is the one edited, × takes it out, dragged onto another they change places,
    // «+ Column» edits a new one; a pick writes the slot as its list of columns.
    const many = Boolean((part.slotList().find((s) => s.key === key) || {}).many);
    let index = 0;
    const columns = () => columnsOf((part.decl.encode || {})[key]);
    const put = (col) => {
      if (!many) { part.setSlot(key, col); return; }
      const list = columns();
      const next = col ? [...list.slice(0, index), col, ...list.slice(index + 1)] : list.filter((_, k) => k !== index);
      part.setSlot(key, next.length ? next : null);
    };
    const columnsRow = () => {
      const row = el('div', 'sf-pop__cols');
      const list = columns();
      let from = null;
      list.forEach((col, k) => {
        const chip = el('span', `sf-pop__red sf-pop__colchip${k === index ? ' is-on' : ''}`);
        chip.setAttribute('draggable', 'true');
        chip.setAttribute('data-column', String(k));
        const name = el('button', 'sf-pop__colname', slotWords(col));
        name.type = 'button';
        name.addEventListener('click', () => { index = k; draw(col); });
        const x = el('button', 'sf-pop__colx', '×');
        x.type = 'button';
        x.setAttribute('aria-label', `Remove ${slotWords(col)}`);
        x.addEventListener('click', () => { const rest = columns().filter((_, j) => j !== k); part.setSlot(key, rest.length ? rest : null); index = 0; draw(rest[0] || { steps: [], value: null }); });
        chip.addEventListener('dragstart', () => { from = k; });
        chip.addEventListener('dragover', (event) => { if (event.preventDefault) event.preventDefault(); });
        chip.addEventListener('drop', () => {
          if (from === null || from === k) return;
          const moved = [...columns()];
          const [it] = moved.splice(from, 1);
          moved.splice(k, 0, it);
          part.setSlot(key, moved);
          index = k;
          draw(moved[k]);
        });
        chip.append(name, x);
        row.append(chip);
      });
      const add = el('button', `sf-pop__red${index >= list.length ? ' is-on' : ''}`, '+ Column');
      add.type = 'button';
      add.addEventListener('click', () => { index = columns().length; draw({ steps: [], value: null }); });
      row.append(add);
      return row;
    };
    const draw = (current, writing) => {
      const box = el('div', 'sf-pop');
      if (many) box.append(columnsRow());
      if (!part.index) { box.append(el('div', 'sf-pop__why', 'Walk first - nothing to pick from')); show(box); return; }
      // An expression slot picks no route: the columns start empty, the expression row stands open.
      const chosen = isExpression(current) ? { steps: [], value: null } : current;
      // Three columns side by side - the route, then where it ends and its value, then how they fold.
      const [routes, at, folds] = [el('div', 'sf-pop__col'), el('div', 'sf-pop__col'), el('div', 'sf-pop__col')];
      box.append(routes, at, folds);
      routes.append(el('div', 'sf-pop__lab', 'Route'));
      const held = routeChoices(part.index, rows);
      const declared = declaredChoices(part.vocabulary && part.vocabulary(), part.rowType && part.rowType(), held);
      for (const route of [...held, ...declared]) {
        const it = el('button', `sf-pop__it${sameSteps(route.steps, chosen.steps) ? ' is-on' : ''}${route.unloaded ? ' is-unloaded' : ''}`,
          route.words.join(' · '));
        it.type = 'button';
        it.addEventListener('click', () => {
          const next = { ...chosen, steps: route.steps, end: undefined, value: null };
          draw(next);
          if (!route.unloaded || !part.walkValues) return;
          // not in the walk in hand: the slot's value walk brings it, and the list is drawn again with its values
          const open = this.host.firstChild;
          part.walkValues(key, { steps: route.steps, value: null })
            .then(() => { if (open && open.isConnected && this.host.firstChild === open) draw(next); });
        });
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
          put(next);
          draw(next);
        });
        at.append(it);
      }
      // «time» (lead 10-14 ③ ㄱ): the time of what the slot reads - the route's last edge's for its name, a node value's own
      // record's - the reading slot.js already does for `of: 'time'`; none made up. «(row)» has no edge: off.
      if (values.length) {
        const timed = chosen.of === 'time';
        const it = el('button', `sf-pop__it${timed ? ' is-on' : ''}`, 'time');
        it.type = 'button';
        it.append(el('span', 'sf-pop__n', 'when'));
        setDisabledReason(it, (chosen.steps || []).length ? null : NO_TIME_HERE);
        it.addEventListener('click', () => {
          const value = chosen.value || NAME_VALUE;
          const far = chosen.end ? (part.index.nodes.get(chosen.end) || {}).label || chosen.end : null;
          const next = { steps: chosen.steps || [], end: chosen.end, value, of: 'time', reduce: chosen.reduce || undefined,
            words: [far ? `${far} · ${value.name}` : value.name] };
          put(next);
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
          put(next);
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
      // Categorical / Continuous (lead-board-13 ①): a slot the kind draws either way - whatever its type declares; the one
      // lit is the scale the root draws it on now (slot.js scaleOf), a pick the declaration's `scale`
      if (desc.scalable) {
        folds.append(el('div', 'sf-pop__lab', 'Scale'));
        const scales = el('div', 'sf-pop__reds');
        const now = ((part.scales || {})[key] || {}).scale || null;
        for (const [scale, words] of [['categorical', 'Categorical'], ['continuous', 'Continuous']]) {
          const chip = el('button', `sf-pop__red${now === scale ? ' is-on' : ''}`, words);
          chip.type = 'button';
          chip.setAttribute('data-scale', scale);
          chip.addEventListener('click', () => { const d = part.declaration(); part.setDeclaration({ ...d, scale: { ...(d.scale || {}), [key]: scale } }); draw(chosen); });
          scales.append(chip);
        }
        folds.append(scales, el('hr', 'sf-pop__hr'));
      }
      for (const choice of desc.choices || []) {
        const it = el('button', 'sf-pop__it', choice.words);
        it.type = 'button';
        it.addEventListener('click', () => { part.setDeclaration({ ...part.declaration(), ...choice.patch }); this.close(); });
        folds.append(it);
      }
      const none = el('button', 'sf-pop__it', '(None)');
      none.type = 'button';
      none.addEventListener('click', () => { put(null); this.close(); });
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
        put(next);
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
    draw((many ? columns()[0] : slot) || { steps: [], value: null });
  }
}
