// THE LEDGER DECLARATION WINDOW (owner 10-14 «이대로 만들어» - task/design/LEDGER_DECLARATION_BAR.dc.html): a ledger source,
// a predicate or a node type declared as the walk page's sentence bar - chips that open a list, a sentence a row. Its
// look is the mockup's (ledger_declaration_bar.css). This file draws and edits; it holds nothing: the explorer's draft
// text is the declaration, and every control is a `data-action` the explorer's controller hears - its DOM is patched in
// place (dom_patch), so a listener on a fresh node would not survive.
//
//   decl-open  data-path      open (or close) that chip's list - the page's `open` says which one is open
//   decl-pick  data-path · data-value (JSON)   that value at that path
//   decl-type  data-path      the list's «Constant…» line pressed - it becomes the box to type in
//   decl-const data-path · data-chip           a typed value (Enter): a column chip's constant, a when's «= …», a name
//   decl-add   data-path      one more attribute, node type, sentence, qualifier, key, subject or type
//   decl-remove data-path     that sentence (or chip) out
//   decl-json                 the declaration as JSON (the owner 2026-08-15: the form is not the only door)
//
// A source in the short form (implementer B 10-14): { table, status?, attributes?: {type: {attribute: value}},
//   sentences: [{sentence, predicate, when?, <role>: value}] } - the roles subject · target · value · occurred_at and the
//   qualifiers. A value is a column's name, {const: v}, a time {column, timezone, format} or an end {node: type|{column}, keys}.
//   A when is {column: condition}, its columns «and»: "" blank, {not: ""} not blank, v equals, {not: v} differs.
// The atom time is each sentence's occurred_at; the Read line's chips write it on every sentence (path `sentences.*.…`).
// Sentences that state it must state the same one - the server refuses a source whose sentences differ (missing_time).

export const BAR_WORDS = Object.freeze({
  title: 'Ledger declaration', source: 'Source', active: 'active', draft: (age) => `draft · ${age}`,
  shortForm: (n) => `short form · ${n} sentence${n === 1 ? '' : 's'}`, testRun: 'Test run', saveDraft: 'Save draft', activate: 'Activate', json: 'JSON',
  read: 'Read', table: 'table', atomTime: '· atom time', identity: '· identity', tableKey: 'table key',
  attributes: 'Attributes', has: 'has', addAttribute: '+ Attribute', addNodeType: '+ Node type',
  sentences: 'Sentences', perRow: 'one row → one edge per sentence', with: '· with', when: '· when', addQualifier: '+ Qualifier',
  addSentence: '+ Sentence', remove: 'Remove sentence', fromSource: (s) => `— from source ${s}`,
  run: (draft) => `Test run · ${draft ? 'draft' : 'active declaration'}`, runSummary: (r) => `first ${r.rows} rows → ${r.edges} edges · ${r.refused} refused`, runNone: 'Not run yet',
  constant: 'Constant…', blank: 'is blank', notBlank: 'is not blank', unset: '?', mixed: 'mixed', timesDiffer: 'sentences differ: one row, one time',
  nodeType: 'Node type', keys: 'keys', addKey: '+ Key', predicate: 'Predicate', from: 'from', addSubject: '+ Subject', addType: '+ Type',
  more: 'More', json: 'JSON',
});
/** The fields a node type's and a predicate's bar draws itself; every other field of the declaration is on its More line. */
export const BAR_FIELDS = Object.freeze({ entity: Object.freeze(['keys', 'attributes']), predicate: Object.freeze(['subjects', 'object']) });
const RESERVED = new Set(['sentence', 'subject', 'predicate', 'target', 'value', 'when', 'occurred_at']);
const KINDS = Object.freeze(['entity_ref', 'value', 'none']);

/** A source in the short form - its sentences are a list (implementer B). */
export const isShortForm = (raw) => Boolean(raw) && typeof raw === 'object' && Array.isArray(raw.sentences);

const isConst = (v) => Boolean(v) && typeof v === 'object' && 'const' in v;
const isObj = (v) => Boolean(v) && typeof v === 'object' && !Array.isArray(v);
const words = (v) => (isConst(v) ? JSON.stringify(v.const) : isObj(v) && 'column' in v ? words(v.column)
  : (v === undefined || v === null || v === '' ? BAR_WORDS.unset : String(v)));
const whenColumn = (w) => (isObj(w) ? Object.keys(w)[0] || null : null);
function whenWords(w) {
  const c = whenColumn(w);
  if (!c) return BAR_WORDS.unset;
  const v = w[c];
  if (v === '') return `${c} ${BAR_WORDS.blank}`;
  if (isObj(v) && 'not' in v) return v.not === '' ? `${c} ${BAR_WORDS.notBlank}` : `${c} ≠ ${JSON.stringify(v.not)}`;
  return `${c} = ${JSON.stringify(v)}`;
}
/** The sentences' one atom time - the column (or timezone) every sentence that states one states, `mixed` when they differ. */
function sharedTime(raw, part) {
  const seen = [...new Set((raw.sentences || []).filter((s) => s.occurred_at !== undefined && s.occurred_at !== null)
    .map((s) => (isObj(s.occurred_at) ? s.occurred_at[part] : s.occurred_at) || ''))];
  return seen.length > 1 ? BAR_WORDS.mixed : seen[0] || '';
}
const qualifiersOf = (s) => Object.keys(s || {}).filter((k) => !RESERVED.has(k));

// ── editing: one function, a path and a value - the declaration a new object, the old one untouched ──
const segs = (path) => String(path).split('.').map((p) => (/^\d+$/.test(p) ? Number(p) : p));
const clone = (v) => JSON.parse(JSON.stringify(v === undefined ? null : v));

/**
 * The declaration with one edit: `set` a value at a path (a node type's name - path `attributes.@<old>` - renames it),
 * `add` one more of what the path holds, `remove` what is at it. A node picked for a sentence's end takes that node
 * type's keys, each unset. @param {object} ctx  {entities: [{type, keys, attributes}], predicates: [{name, qualifiers}]}
 */
export function editDeclaration(raw, op, ctx = {}) {
  const out = clone(raw) || {};
  // `a.*.b` - the same edit on every member of `a`
  const star = String(op.path).split('.').indexOf('*');
  if (star >= 0) {
    const parts = String(op.path).split('.');
    const head = parts.slice(0, star).join('.');
    let list = out;
    for (const k of segs(head)) list = list && list[k];
    if (!Array.isArray(list)) return out;
    let next = out;
    list.forEach((_, i) => { next = editDeclaration(next, { ...op, path: [head, i, ...parts.slice(star + 1)].join('.') }, ctx); });
    return next;
  }
  const at = segs(op.path);
  const last = at.pop();
  let box = out;
  for (const k of at) { if (box[k] === undefined || box[k] === null) box[k] = typeof k === 'number' ? [] : {}; box = box[k]; }
  const entity = (type) => (ctx.entities || []).find((e) => e.type === type) || null;
  if (op.op === 'set') {
    if (typeof last === 'string' && last.startsWith('@')) {
      const old = last.slice(1);
      const kept = Object.entries(box).map(([k, v]) => (k === old ? [op.value, v] : [k, v]));
      for (const k of Object.keys(box)) delete box[k];
      for (const [k, v] of kept) box[k] = v;
    } else if (last === 'node' && box && typeof box === 'object') {
      box.node = op.value;
      const e = entity(op.value);
      if (e) box.keys = Object.fromEntries((e.keys || []).map((k) => [k, (box.keys || {})[k] || '']));
    } else box[last] = op.value;
  } else if (op.op === 'add') {
    const holder = last === undefined ? box : box[last] === undefined ? (box[last] = {}) : box[last];
    if (Array.isArray(holder)) {
      if (op.path === 'sentences') {
        const time = holder.length ? clone(holder[holder.length - 1].occurred_at) : null;
        holder.push({ sentence: `sentence-${holder.length + 1}`, subject: { node: '', keys: {} }, predicate: '', target: { node: '', keys: {} }, ...(time ? { occurred_at: time } : {}) });
      }
      else holder.push('');
    } else if (op.path === 'attributes') {
      const free = (ctx.entities || []).map((e) => e.type).find((t) => !(t in holder));
      holder[free || `type_${Object.keys(holder).length + 1}`] = {};
    } else if (/^attributes\./.test(op.path)) {
      const e = entity(segs(op.path)[1]);
      const free = ((e && e.attributes) || []).find((a) => !(a in holder));
      holder[free || `attribute_${Object.keys(holder).length + 1}`] = '';
    } else if (/^sentences\.\d+$/.test(op.path)) {
      const pred = (ctx.predicates || []).find((p) => p.name === holder.predicate);
      const free = ((pred && pred.qualifiers) || []).find((q) => !(q in holder));
      holder[free || `qualifier_${qualifiersOf(holder).length + 1}`] = '';
    }
  } else if (op.op === 'remove') {
    if (Array.isArray(box)) box.splice(last, 1); else delete box[last];
  }
  return out;
}

// ── the server's answers, as the bar's words ──
const keyWords = (keys) => (isObj(keys) ? Object.values(keys).map((v) => (v === null || v === undefined ? '' : String(v))).join(' · ') : '');

/**
 * The test run's answer (POST /test-run, as it comes) as the bar's table: rows read, atoms, refused, each refusal a
 * pill (its row and the server's sentence), and an atom a line. Null before a run.
 */
export function barRun(run) {
  if (!run || typeof run !== 'object') return null;
  const refused = isObj(run.refused) ? run.refused : {};
  const refusals = (Array.isArray(refused.samples) ? refused.samples : []).filter(isObj).map((s) => {
    const at = isObj(s.row_key) && s.row_key.position !== undefined && s.row_key.position !== null ? `row ${s.row_key.position}: ` : '';
    return `${at}${s.detail || s.reason || ''}`;
  });
  if (isObj(run.refusal) && run.refusal.message) refusals.unshift(String(run.refusal.message));
  const lines = (Array.isArray(run.atoms_sample) ? run.atoms_sample : []).filter(isObj).map((a) => {
    const payload = isObj(a.object_payload) ? a.object_payload : {};
    const quals = isObj(payload.qualifiers) ? Object.entries(payload.qualifiers) : [];
    const target = a.object_kind === 'entity_ref' ? { node: payload.type || '', key: keyWords(payload.keys) }
      : { node: a.object_kind || '', key: 'value' in payload ? String(payload.value) : '' };
    return { row: (Array.isArray(a.row_ids) ? a.row_ids : []).join(', '), sentence: a.sentence || '', subject: { node: a.subject_type || '', key: keyWords(a.subject_keys) },
      predicate: a.predicate || '', target, with: quals.length ? { name: quals[0][0], value: String(quals[0][1]) } : null, at: a.occurred_at || '' };
  });
  const count = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
  // ran the draft = the answer names the draft it ran (implementer B's door); else it ran the active declaration
  return { rows: count(run.rows_read), edges: count(run.atoms), refused: count(refused.count), refusals, lines, draft: Boolean(run.draft_id) };
}

/** «edited N min ago» off the draft's `updated_at` - the words the mockup draws. */
export function draftAge(updatedAt, now = Date.now()) {
  const t = Date.parse(updatedAt || '');
  if (!Number.isFinite(t)) return '';
  const min = Math.max(0, Math.round((now - t) / 60000));
  if (min < 60) return `edited ${min} min ago`;
  const hours = Math.round(min / 60);
  return hours < 48 ? `edited ${hours} h ago` : `edited ${Math.round(hours / 24)} d ago`;
}

// ── drawing ──
const make = (doc) => (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = String(text); return n; };

/**
 * One chip and, when it is the open one, its list under it.
 * @param {{kind: 'col'|'node'|'pred'|'table'|'tz'|'identity'|'when'|'name'|'kind'|'source', path, text, options?: Array<{value, words, type?, on?, action?, key?}>, constant?: boolean, cls?: string, parts?: Node[]}} c
 */
function chip(el, view, c) {
  const open = view.open === c.path;
  const b = el('button', `ldb-chip${c.cls ? ` ${c.cls}` : ''}${open ? ' is-open' : ''}`);
  b.type = 'button';
  b.dataset.action = 'decl-open';
  b.dataset.path = c.path;
  b.dataset.chip = c.kind;
  if (c.parts) b.append(...c.parts); else b.append(c.text);
  b.append(' ', el('span', 'ldb-caret', '▾'));
  // the chip sits in its wrapper open or shut, so opening adds the list and moves nothing
  const wrap = el('div', 'ldb-at');
  if (!open) { wrap.append(b); return wrap; }
  const pop = el('div', 'ldb-pop');
  pop.setAttribute('role', 'listbox');
  for (const o of c.options || []) {
    const opt = el('button', `ldb-opt${o.on ? ' is-on' : ''}`);
    opt.type = 'button';
    opt.setAttribute('role', 'option');
    if (o.action) { opt.dataset.action = o.action; opt.dataset.value = o.key; } else {
      opt.dataset.action = 'decl-pick';
      opt.dataset.path = c.path;
      opt.dataset.value = JSON.stringify(o.value);
    }
    opt.append(el('span', c.kind === 'node' || c.kind === 'pred' || c.kind === 'tz' || c.kind === 'kind' || c.kind === 'source' ? '' : 'ldb-mono', o.words));
    if (o.type) opt.append(el('span', 'ldb-type', o.type));
    pop.append(opt);
  }
  if (c.constant) {
    if ((c.options || []).length) pop.append(el('div', 'ldb-hr'));
    // «Constant…» a line of the list as the mockup draws it; pressed, the line is the box to type it in.
    if (view.typing !== c.path) {
      const line = el('button', 'ldb-opt');
      line.type = 'button';
      line.dataset.action = 'decl-type';
      line.dataset.path = c.path;
      line.append(el('span', '', c.kind === 'name' ? 'Name…' : BAR_WORDS.constant), el('span', 'ldb-type', c.hint || ''));
      pop.append(line);
      wrap.append(b, pop);
      return wrap;
    }
    const input = el('input', 'ldb-opt-input');
    input.type = 'text';
    input.placeholder = c.kind === 'name' ? 'Name' : BAR_WORDS.constant;
    input.setAttribute('aria-label', c.kind === 'name' ? 'Name' : 'Constant');
    input.dataset.action = 'decl-const';
    input.dataset.path = c.path;
    input.dataset.chip = c.kind;
    if (c.typed !== undefined) input.value = c.typed;
    pop.append(input);
  }
  wrap.append(b, pop);
  return wrap;
}

const columnOptions = (view, table, current) => (((view.catalog || {}).tables || {})[table] || [])
  .map((col) => ({ value: col.name, words: col.name, type: col.type, on: col.name === current }));
const nodeOptions = (view, current) => (view.entities || []).map((e) => ({ value: e.type, words: e.type, on: e.type === current }));

/** The window's head: its title, the source picker (the tree's Sources list), its state, Test run · Save draft · Activate. */
function head(el, view, raw) {
  const top = el('header', 'ldb-head');
  top.append(el('h1', 'ldb-title', BAR_WORDS.title));
  if (view.kind === 'source') {
    top.append(chip(el, view, { kind: 'source', path: '@source', cls: 'is-open', text: `${BAR_WORDS.source}: ${view.name || BAR_WORDS.unset}`,
      options: (view.sources || []).map((s) => ({ words: s.id, action: 'select', key: s.key, on: s.id === view.name })) }));
  } else top.append(el('span', 'ldb-mono', view.name || ''));
  if (view.active) top.append(el('span', 'ldb-pill is-active', BAR_WORDS.active));
  if (view.draftAge) top.append(el('span', 'ldb-pill is-draft', BAR_WORDS.draft(view.draftAge)));
  if (view.kind === 'source') top.append(el('span', 'ldb-word', BAR_WORDS.shortForm((raw.sentences || []).length)));
  top.append(el('div', 'ldb-grow'));
  const btn = (words, action, cls = '', value) => { const b = el('button', `ldb-btn${cls}`, words); b.type = 'button'; b.dataset.action = action; if (value !== undefined) b.dataset.value = value; return b; };
  top.append(btn(BAR_WORDS.json, 'decl-json'));
  if (view.kind === 'source') { const run = btn(BAR_WORDS.testRun, 'test-run', '', view.sourceId || ''); if (view.draftId) run.dataset.draft = view.draftId; top.append(run); }
  top.append(btn(BAR_WORDS.saveDraft, 'save-draft-only'), btn(BAR_WORDS.activate, 'save-draft', ' is-primary'));
  return top;
}

function readBar(el, view, raw) {
  const bar = el('section', 'ldb-bar');
  bar.setAttribute('aria-label', BAR_WORDS.read);
  const tables = Object.keys(((view.catalog || {}).tables) || {});
  const time = { column: sharedTime(raw, 'column'), timezone: sharedTime(raw, 'timezone') };
  const zones = [...new Set([time.timezone, 'UTC', ...(view.zones || [])].filter((z) => z && z !== BAR_WORDS.mixed))];
  bar.append(el('span', 'ldb-label is-row', BAR_WORDS.read), el('span', 'ldb-word', BAR_WORDS.table),
    chip(el, view, { kind: 'table', path: 'table', cls: 'is-col', text: words(raw.table), options: tables.map((t) => ({ value: t, words: t, on: t === raw.table })) }),
    el('span', 'ldb-word', BAR_WORDS.atomTime),
    chip(el, view, { kind: 'col', path: 'sentences.*.occurred_at.column', cls: 'is-col', text: words(time.column), options: columnOptions(view, raw.table, time.column) }),
    chip(el, view, { kind: 'tz', path: 'sentences.*.occurred_at.timezone', text: words(time.timezone), options: zones.map((z) => ({ value: z, words: z, on: z === time.timezone })) }),
    // the short form has no identity: the table's own key (implementer B 10-14), named when the schema says it
    el('span', 'ldb-word', BAR_WORDS.identity),
    el('span', 'ldb-chip', (((view.catalog || {}).keys || {})[raw.table] || []).length
      ? `${BAR_WORDS.tableKey} (${view.catalog.keys[raw.table].join(' · ')})` : BAR_WORDS.tableKey));
  if (time.column === BAR_WORDS.mixed || time.timezone === BAR_WORDS.mixed) bar.append(el('span', 'ldb-pill is-bad', BAR_WORDS.timesDiffer));
  return bar;
}

function attributesBar(el, view, raw) {
  const bar = el('section', 'ldb-bar');
  bar.setAttribute('aria-label', BAR_WORDS.attributes);
  bar.append(el('span', 'ldb-label is-row', BAR_WORDS.attributes));
  for (const [type, attrs] of Object.entries(raw.attributes || {})) {
    bar.append(chip(el, view, { kind: 'node', path: `attributes.@${type}`, cls: 'is-node', text: type, options: nodeOptions(view, type) }), el('span', 'ldb-word', BAR_WORDS.has));
    for (const [name, col] of Object.entries(attrs || {})) {
      bar.append(chip(el, view, { kind: 'col', path: `attributes.${type}.${name}`, constant: true, options: columnOptions(view, raw.table, col),
        parts: [name, ' ', el('span', 'ldb-arrow', '←'), ' ', el('span', 'ldb-mono', words(col))] }));
    }
    bar.append(addChip(el, `attributes.${type}`, BAR_WORDS.addAttribute), el('span', 'ldb-gap'));
  }
  bar.append(addChip(el, 'attributes', BAR_WORDS.addNodeType));
  return bar;
}

function addChip(el, path, text, cls = '') {
  const b = el('button', `ldb-chip is-add${cls}`, text);
  b.type = 'button';
  b.dataset.action = 'decl-add';
  b.dataset.path = path;
  return b;
}

/** A sentence's end: its node, then its keys «key ← column» (a constant dashed). */
function end(el, view, raw, at, side) {
  const e = (raw.sentences[at] || {})[side] || {};
  const node = isObj(e.node) ? `← ${words(e.node)}` : words(e.node);
  const out = [chip(el, view, { kind: 'node', path: `sentences.${at}.${side}.node`, cls: 'is-node', text: node, options: nodeOptions(view, e.node) }),
    el('span', 'ldb-word', '(')];
  for (const [k, v] of Object.entries(e.keys || {})) {
    out.push(chip(el, view, { kind: 'col', path: `sentences.${at}.${side}.keys.${k}`, constant: true, cls: isConst(v) ? 'is-const' : 'is-col', hint: isConst(v) ? JSON.stringify(v.const) : '',
      text: isConst(v) ? `${k} = ${JSON.stringify(v.const)}` : `${k} ← ${words(v)}`, options: columnOptions(view, raw.table, isConst(v) ? null : v),
      parts: isConst(v) ? undefined : [k, ' ', el('span', 'ldb-arrow', '←'), ' ', words(v)] }));
  }
  out.push(el('span', 'ldb-word', ')'));
  return out;
}

function sentenceBar(el, view, raw, at, from = null) {
  const s = raw.sentences[at];
  const bar = el('section', `ldb-bar${!from && view.picked === at ? ' is-picked' : ''}${from ? ' is-other' : ''}`);
  bar.setAttribute('aria-label', `Sentence ${s.sentence}`);
  // another source's sentence on the same table: drawn as one, not this draft's to edit
  if (from) bar.setAttribute('inert', '');
  const name = el('span', 'ldb-sname', s.sentence);
  if (from) name.append(' ', el('span', 'ldb-sname-from', BAR_WORDS.fromSource(from)));
  bar.append(name, ...end(el, view, raw, at, 'subject'), el('span', 'ldb-arrow', '—'),
    chip(el, view, { kind: 'pred', path: `sentences.${at}.predicate`, cls: 'is-pred', text: words(s.predicate),
      options: (view.predicates || []).map((p) => ({ value: p.name, words: p.name, on: p.name === s.predicate })) }));
  // the end the sentence holds: a node (target), a value read off a column (value), or none (a predicate with no object)
  if (s.target !== undefined) bar.append(el('span', 'ldb-arrow', '→'), ...end(el, view, raw, at, 'target'));
  else if (s.value !== undefined) {
    bar.append(el('span', 'ldb-arrow', '→'), chip(el, view, { kind: 'col', path: `sentences.${at}.value`, constant: true, cls: isConst(s.value) ? 'is-const' : 'is-col',
      hint: isConst(s.value) ? JSON.stringify(s.value.const) : '', text: isConst(s.value) ? `value = ${JSON.stringify(s.value.const)}` : `value ← ${words(s.value)}`,
      options: columnOptions(view, raw.table, isConst(s.value) ? null : s.value),
      parts: isConst(s.value) ? undefined : ['value', ' ', el('span', 'ldb-arrow', '←'), ' ', words(s.value)] }));
  }
  const quals = qualifiersOf(s);
  const pred = (view.predicates || []).find((p) => p.name === s.predicate);
  const free = ((pred && pred.qualifiers) || []).some((q) => !quals.includes(q));
  if (quals.length) {
    bar.append(el('span', 'ldb-word', BAR_WORDS.with));
    for (const q of quals) {
      bar.append(chip(el, view, { kind: 'col', path: `sentences.${at}.${q}`, constant: true, cls: isConst(s[q]) ? 'is-const' : 'is-col',
        text: isConst(s[q]) ? `${q} = ${JSON.stringify(s[q].const)}` : `${q} ← ${words(s[q])}`, options: columnOptions(view, raw.table, s[q]),
        parts: isConst(s[q]) ? undefined : [q, ' ', el('span', 'ldb-arrow', '←'), ' ', words(s[q])] }));
    }
    // + Qualifier closes the with group while the predicate still takes one (lead 10-14: a door to a nameless cell is untrue)
    if (free) bar.append(addChip(el, `sentences.${at}`, BAR_WORDS.addQualifier));
  }
  if (s.when !== undefined) {
    const wc = whenColumn(s.when);
    bar.append(el('span', 'ldb-word', BAR_WORDS.when), chip(el, view, { kind: 'when', path: `sentences.${at}.when`, cls: 'is-col', constant: true, text: whenWords(s.when),
      hint: wc ? `${wc} = …` : '',
      options: columnOptions(view, raw.table, wc).flatMap((o) => [
        { ...o, value: { [o.value]: '' }, words: `${o.words} ${BAR_WORDS.blank}`, on: o.on && s.when[wc] === '' },
        { ...o, value: { [o.value]: { not: '' } }, words: `${o.words} ${BAR_WORDS.notBlank}`, on: o.on && isObj(s.when[wc]) && s.when[wc].not === '' }]) }));
  }
  if (!quals.length && free) {
    // the predicate takes a qualifier this sentence has none of yet: «· with + Qualifier» (lead 10-14), after the when so a
    // narrow bar wraps it beside a chip
    bar.append(el('span', 'ldb-word', BAR_WORDS.with), addChip(el, `sentences.${at}`, BAR_WORDS.addQualifier));
  }
  const x = el('button', 'ldb-x', '×');
  x.type = 'button';
  x.dataset.action = 'decl-remove';
  x.dataset.path = `sentences.${at}`;
  x.setAttribute('aria-label', BAR_WORDS.remove);
  bar.append(el('div', 'ldb-grow'), x);
  return bar;
}

function preview(el, view) {
  const run = view.run || null;
  const box = el('section', 'ldb-preview');
  box.setAttribute('aria-label', BAR_WORDS.run(Boolean(run && run.draft)));
  const top = el('div', 'ldb-preview-head');
  top.append(el('span', 'ldb-label', BAR_WORDS.run(Boolean(run && run.draft))), el('span', 'ldb-word', run ? BAR_WORDS.runSummary(run) : BAR_WORDS.runNone));
  for (const r of (run && run.refusals) || []) top.append(el('span', 'ldb-pill is-bad', r));
  top.append(el('div', 'ldb-grow'));
  // What this save would run again (the explorer's redo cost) - its answer in bold, as the mockup.
  if (view.cost) { const c = el('span', 'ldb-word'); c.append(view.cost.before || '', el('b', '', view.cost.strong || ''), view.cost.after || ''); top.append(c); }
  box.append(top);
  if (run && (run.lines || []).length) {
    const scroll = el('div', 'ldb-scroll');
    const t = el('table', 'ldb-table');
    const hr = el('tr');
    for (const w of ['row', 'sentence', 'subject', 'predicate', 'target', 'with', 'at']) hr.append(el('th', '', w));
    const thead = el('thead'); thead.append(hr);
    const tbody = el('tbody');
    for (const l of run.lines) {
      const tr = el('tr');
      const nodeCell = (n) => { const td = el('td'); td.append(`${n.node} `, el('span', 'ldb-mono', n.key)); return td; };
      tr.append(el('td', 'ldb-mono', l.row), el('td', 'ldb-mono', l.sentence), nodeCell(l.subject), el('td', '', l.predicate), nodeCell(l.target));
      if (l.with) { const td = el('td'); td.append(`${l.with.name} `, el('span', 'ldb-mono', l.with.value)); tr.append(td); } else tr.append(el('td', 'is-none', '—'));
      tr.append(el('td', 'ldb-mono', l.at));
      tbody.append(tr);
    }
    t.append(thead, tbody);
    scroll.append(t);
    box.append(scroll);
  }
  return box;
}

/**
 * The declaration's other fields (the lead 10-14 ㄱ), as the form's skeleton lists them: one value picked from its
 * closed list (`options`), a typed one (`free`), or a list or object opened as that field's JSON (`json`).
 * @param {Array<{name, kind: 'options'|'free'|'json', options?: Array<{value, words}>}>} view.more
 */
function moreBar(el, view, raw) {
  const bar = el('section', 'ldb-bar');
  bar.setAttribute('aria-label', BAR_WORDS.more);
  bar.append(el('span', 'ldb-label is-row', BAR_WORDS.more));
  for (const f of view.more || []) {
    const v = raw[f.name];
    if (f.kind === 'json') {
      bar.append(chip(el, view, { kind: 'json', path: f.name, cls: 'is-col', constant: true, hint: v === undefined ? '' : JSON.stringify(v),
        typed: v === undefined ? '' : JSON.stringify(v), text: `${f.name} · ${BAR_WORDS.json}` }));
    } else {
      bar.append(chip(el, view, { kind: f.kind === 'free' ? 'name' : 'kind', path: f.name, cls: 'is-col', constant: f.kind === 'free',
        text: `${f.name} = ${v === undefined ? BAR_WORDS.unset : typeof v === 'string' ? v : JSON.stringify(v)}`,
        options: (f.options || []).map((o) => ({ ...o, on: same(o.value, v) })) }));
    }
  }
  return bar;
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** A node type: its keys and its attributes, each a chip; a name typed in the chip's list. */
function entityBar(el, view, raw) {
  const bar = el('section', 'ldb-bar');
  bar.setAttribute('aria-label', BAR_WORDS.nodeType);
  bar.append(el('span', 'ldb-label is-row', BAR_WORDS.nodeType), el('span', 'ldb-chip is-node', view.name || ''), el('span', 'ldb-word', BAR_WORDS.keys));
  (raw.keys || []).forEach((k, i) => bar.append(chip(el, view, { kind: 'name', path: `keys.${i}`, cls: 'is-col', constant: true, text: words(k) })));
  bar.append(addChip(el, 'keys', BAR_WORDS.addKey));
  if (Array.isArray(raw.attributes)) {
    bar.append(el('span', 'ldb-word', `· ${BAR_WORDS.attributes.toLowerCase()}`));
    raw.attributes.forEach((a, i) => bar.append(chip(el, view, { kind: 'name', path: `attributes.${i}`, cls: 'is-col', constant: true, text: words(a) })));
    bar.append(addChip(el, 'attributes', BAR_WORDS.addAttribute));
  }
  return bar;
}

/** A predicate: from its subject types, its object's kind and types, its qualifiers. */
function predicateBar(el, view, raw) {
  const bar = el('section', 'ldb-bar');
  bar.setAttribute('aria-label', BAR_WORDS.predicate);
  const object = raw.object || {};
  bar.append(el('span', 'ldb-label is-row', BAR_WORDS.predicate), el('span', 'ldb-chip is-pred', view.name || ''), el('span', 'ldb-word', BAR_WORDS.from));
  (raw.subjects || []).forEach((s, i) => bar.append(chip(el, view, { kind: 'node', path: `subjects.${i}`, cls: 'is-node', text: words(s), options: nodeOptions(view, s) })));
  bar.append(addChip(el, 'subjects', BAR_WORDS.addSubject), el('span', 'ldb-arrow', '→'),
    chip(el, view, { kind: 'kind', path: 'object.kind', text: words(object.kind), options: KINDS.map((k) => ({ value: k, words: k, on: k === object.kind })) }));
  if (object.kind === 'entity_ref') {
    (object.types || []).forEach((t, i) => bar.append(chip(el, view, { kind: 'node', path: `object.types.${i}`, cls: 'is-node', text: words(t), options: nodeOptions(view, t) })));
    bar.append(addChip(el, 'object.types', BAR_WORDS.addType));
  }
  const optional = ((object.qualifiers || {}).optional) || [];
  bar.append(el('span', 'ldb-word', BAR_WORDS.with));
  optional.forEach((q, i) => bar.append(chip(el, view, { kind: 'name', path: `object.qualifiers.optional.${i}`, cls: 'is-col', constant: true, text: words(q) })));
  bar.append(addChip(el, 'object.qualifiers.optional', BAR_WORDS.addQualifier));
  return bar;
}

/**
 * The window for one declaration.
 * @param {Document} doc
 * @param {object} raw  the draft's declaration (parsed)
 * @param {{kind: 'source'|'entity'|'predicate', name, sourceId?, open?: string, picked?: number, catalog?: {tables: {[t]: Array<{name, type}>}},
 *          entities?: Array<{type, keys, attributes}>, predicates?: Array<{name, qualifiers}>, sources?: Array<{key, id}>, zones?: string[],
 *          active?: boolean, draftAge?: string, run?: object, cost?: {before, strong, after}, json?: Node,
 *          others?: Array<{source, sentence}>, draftId?: string, more?: Array<{name, kind, options?}>}} view   others: other sources' sentences on this table, drawn inert
 */
export function renderDeclarationBar(doc, raw, view) {
  const el = make(doc);
  const root = el('div', 'ldb');
  root.setAttribute('data-decl-kind', view.kind);
  root.append(head(el, view, raw || {}));
  if (view.json) { const j = el('div', 'ldb-json'); j.append(view.json); root.append(j); }
  if (view.kind === 'entity') root.append(entityBar(el, view, raw || {}), moreBar(el, view, raw || {}));
  else if (view.kind === 'predicate') root.append(predicateBar(el, view, raw || {}), moreBar(el, view, raw || {}));
  else {
    root.append(readBar(el, view, raw), attributesBar(el, view, raw));
    const list = el('div', 'ldb-sentences');
    const top = el('div', 'ldb-sentences-head');
    top.append(el('span', 'ldb-label', BAR_WORDS.sentences), el('span', 'ldb-word', BAR_WORDS.perRow));
    list.append(top);
    (raw.sentences || []).forEach((_, i) => list.append(sentenceBar(el, view, raw, i)));
    for (const o of view.others || []) list.append(sentenceBar(el, view, { table: raw.table, sentences: [o.sentence] }, 0, o.source));
    const add = el('div');
    add.append(addChip(el, 'sentences', BAR_WORDS.addSentence, ' is-big'));
    list.append(add);
    root.append(list, preview(el, view));
  }
  return root;
}
