// CHAIN RULE GROUPS - the admin's chain rule list folded by a table: the table a rule is triggered by, or the table it
// writes (owner 11-11 «트리거표.규칙명 이렇게 짓고 있는데 많아지니 안 보이더라», lead). One filter over a rule's name, its
// tables and the words its declaration holds. A group's head counts its rules, the ones not running and the ones whose
// last run failed. Which groups are open is this browser's alone (a convenience; none kept, all shut).
// Assembled part: its mount (the toolbar), its table body and its deps; no module state.

import { ABSENT } from './absent.js';
import { ruleOutcomeView, ruleStateView } from './rule_outcome.js';

/** What a group is keyed by - the row's own Data Flow ends (`trigger_table` → `target_table`), so a group never says
 *  another table than its rows do. */
export const GROUP_BY = Object.freeze({
  trigger: { label: 'Trigger table', of: (rule) => rule.trigger_table },
  writes: { label: 'Writes table', of: (rule) => rule.target_table },
});

/** Every word a filter may find a rule by: its name, its tables, and each key and text of its declaration (a column a
 *  join takes, an aggregation's name). */
export function ruleWords(rule) {
  const out = [rule && rule.name, rule && rule.trigger_table, rule && rule.target_table];
  const walk = (v) => {
    if (typeof v === 'string') out.push(v);
    else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === 'object') Object.entries(v).forEach(([k, x]) => { out.push(k); walk(x); });
  };
  if (rule) { walk(rule.derive); walk(rule.into); }
  return out.filter((w) => typeof w === 'string' && w);
}

/** The filter box's word - the list's and the editor picker's alike. */
export const FILTER_WORD = 'Filter: rule, table, column';

export function ruleMatches(rule, query) {
  const q = String(query || '').trim().toLowerCase();
  return !q || ruleWords(rule).some((w) => w.toLowerCase().includes(q));
}

/** The rules a filter keeps, by group: [{key, rules, off, failing}] in the key's order, a rule with no table last. */
export function chainRuleGroups(rules, { by = 'trigger', query = '', outcomes = {} } = {}) {
  const keyOf = (GROUP_BY[by] || GROUP_BY.trigger).of;
  const groups = new Map();
  for (const rule of Array.isArray(rules) ? rules : []) {
    if (!ruleMatches(rule, query)) continue;
    const key = keyOf(rule) || ABSENT;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(rule);
  }
  const last = (k) => (k === ABSENT ? 1 : 0);
  return [...groups].sort(([a], [b]) => last(a) - last(b) || (a < b ? -1 : a > b ? 1 : 0)).map(([key, list]) => ({
    key,
    rules: list,
    off: list.filter((r) => !ruleStateView(r).running).length,
    failing: list.filter((r) => ruleOutcomeView(outcomes && outcomes[r.name]).failed).length,
  }));
}

/** The rule editor's picker (owner 11-11 «체인 선언 룰 편집기도 그룹 해줘야지»): the names its registry lists, in the
 *  list's groups by the same key and filter - [{label, names}]. A name no rule here carries stands with the rules of no
 *  table. */
export function pickerGroups(rules, names, { by = 'trigger', query = '' } = {}) {
  const known = new Map((Array.isArray(rules) ? rules : []).map((r) => [r && r.name, r]));
  const listed = (Array.isArray(names) ? names : []).map((name) => known.get(name) || { name });
  return chainRuleGroups(listed, { by, query }).map((g) => ({ label: g.key, names: g.rules.map((r) => r.name) }));
}

/** A group's head: «5 rules · 2 off · 1 failing». */
export function groupCountsText(group) {
  return `${group.rules.length} ${group.rules.length === 1 ? 'rule' : 'rules'} · ${group.off} off · ${group.failing} failing`;
}

export class ChainRuleGroups {
  /**
   * @param {HTMLElement} mount  where the toolbar goes
   * @param {{doc?: Document, body: HTMLElement, rowOf: (rule: object) => HTMLElement, columns: number, key: string,
   *          storage?: Storage|null}} deps  body: the table body the rows go in; key: this list's name in the storage
   */
  constructor(mount, deps) {
    this.doc = deps.doc || mount.ownerDocument;
    this.deps = deps;
    this.store = deps.storage !== undefined ? deps.storage
      : (typeof globalThis !== 'undefined' ? globalThis.localStorage : null);
    this.rules = [];
    this.outcomes = {};
    const el = (tag, cls) => { const n = this.doc.createElement(tag); n.className = cls; return n; };
    this.root = el('div', 'chain-groups');
    const by = el('label', 'chain-groups__by');
    by.appendChild(this.doc.createTextNode('Group by '));
    this.by = el('select', 'glass-select ctl-small');
    for (const [value, { label }] of Object.entries(GROUP_BY)) {
      const option = this.doc.createElement('option');
      option.value = value;
      option.textContent = label;
      this.by.appendChild(option);
    }
    by.appendChild(this.by);
    this.filter = el('input', 'glass-input ctl-small chain-groups__filter');
    this.filter.type = 'search';
    this.filter.placeholder = FILTER_WORD;
    this.filter.setAttribute('aria-label', 'Filter chain rules');
    this.shown = el('span', 'chain-groups__shown');
    this.root.appendChild(by);
    this.root.appendChild(this.filter);
    this.root.appendChild(this.shown);
    mount.appendChild(this.root);
    this.by.addEventListener('change', () => this.draw());
    this.filter.addEventListener('input', () => this.draw());
    this.deps.body.addEventListener('click', (e) => {
      const head = e.target && e.target.closest ? e.target.closest('[data-chain-group]') : null;
      if (head) this.toggle(head.dataset.chainGroup);
    });
  }

  /** The rules and their last outcomes (`rule_outcomes`), drawn. */
  render(rules, outcomes = {}) {
    this.rules = Array.isArray(rules) ? rules : [];
    this.outcomes = outcomes || {};
    this.draw();
  }

  draw() {
    const by = this.by.value;
    const query = this.filter.value;
    const groups = chainRuleGroups(this.rules, { by, query, outcomes: this.outcomes });
    const open = this.opened(by);
    const shown = groups.reduce((n, g) => n + g.rules.length, 0);
    this.shown.textContent = query.trim() ? `${shown} of ${this.rules.length} rules` : '';
    const body = this.deps.body;
    body.textContent = '';
    if (!groups.length && query.trim()) {
      const tr = this.doc.createElement('tr');
      const td = this.doc.createElement('td');
      td.colSpan = this.deps.columns;
      td.className = 'chain-groups__none';
      td.textContent = `No rule matches «${query.trim()}»`;
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }
    for (const group of groups) {
      // while a filter is typed, every group it kept is drawn open: a match folded away reads as none
      const isOpen = Boolean(query.trim()) || open.includes(group.key);
      const tr = this.doc.createElement('tr');
      tr.className = 'chain-group';
      const td = this.doc.createElement('td');
      td.colSpan = this.deps.columns;
      const toggle = this.doc.createElement('button');
      toggle.type = 'button';
      toggle.className = 'chain-group__toggle';
      toggle.dataset.chainGroup = group.key;
      toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      const caret = this.doc.createElement('span');
      caret.className = 'chain-group__caret';
      caret.textContent = isOpen ? '▾' : '▸';
      const name = this.doc.createElement('span');
      name.className = 'chain-group__name';
      name.textContent = group.key;
      const counts = this.doc.createElement('span');
      counts.className = 'chain-group__counts';
      counts.textContent = groupCountsText(group);
      if (group.failing) counts.dataset.failing = 'true';
      toggle.appendChild(caret);
      toggle.appendChild(name);
      toggle.appendChild(counts);
      td.appendChild(toggle);
      tr.appendChild(td);
      body.appendChild(tr);
      if (isOpen) group.rules.forEach((rule) => body.appendChild(this.deps.rowOf(rule)));
    }
  }

  toggle(key) {
    if (this.filter.value.trim()) return;
    const by = this.by.value;
    const open = this.opened(by);
    const next = open.includes(key) ? open.filter((k) => k !== key) : [...open, key];
    try { if (this.store) this.store.setItem(this.storeKey(by), JSON.stringify(next)); } catch { /* none kept: all shut */ }
    this.held = { by, open: next };
    this.draw();
  }

  /** The groups open for `by`: this browser's, else what this page opened, else none. */
  opened(by) {
    try {
      const raw = this.store ? this.store.getItem(this.storeKey(by)) : null;
      const list = raw ? JSON.parse(raw) : null;
      if (Array.isArray(list)) return list.filter((k) => typeof k === 'string');
    } catch { /* storage unreadable: the page's own */ }
    return this.held && this.held.by === by ? this.held.open : [];
  }

  storeKey(by) { return `${this.deps.key}:open:${by}`; }

  /** The key the list is grouped by now - the editor's picker groups by the same. */
  groupBy() { return this.by.value; }
}
