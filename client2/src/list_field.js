// ONE LIST FIELD (lead 11-11, admin census «목록을 입력 하나로»): a box that takes a list - one value per line, comma or tab,
// so a column pasted from a sheet comes in whole - and says how many values it read. The grid filter's Paste list, the
// retroactive form's list parameters (declared `"type": "csv"`) and the explorer form's word adder read lists through it.
// Its look is the base layer's (base.css `.list-field`); the label above it is the caller's.

/** A list typed or pasted: one value per line, comma or tab; trimmed, the empty dropped, each once. A number column's
 *  values go as numbers when they read as one - the server says which do not (422), the screen does not judge them. */
export function listValues(text, kind = 'text') {
  const seen = new Set();
  const values = [];
  let duplicates = 0;
  for (const part of String(text == null ? '' : text).split(/[\r\n\t,]+/)) {
    const word = part.trim();
    if (!word) continue;
    if (seen.has(word)) { duplicates += 1; continue; }
    seen.add(word);
    values.push(kind === 'number' && Number.isFinite(Number(word)) ? Number(word) : word);
  }
  return { values, duplicates };
}

/** «N values» and, beside it, how many repeats were dropped ('' none). */
export function listCountWords(values, duplicates) {
  return [`${values.length.toLocaleString('en-US')} value${values.length === 1 ? '' : 's'}`,
    duplicates ? `${duplicates} duplicate${duplicates === 1 ? '' : 's'} removed` : ''];
}

/**
 * @param {HTMLElement} mount  the field: its box and its count line are its children
 * @param {{doc?: Document, kind?: string, rows?: number, values?: Array, say?: (n: string) => string,
 *          onChange?: (values: Array) => void}} deps
 *   `values` the list it opens with (one a line); `say` words the count (the grid filter adds «equals any»).
 */
export class ListField {
  constructor(mount, deps = {}) {
    this.root = mount;
    this.doc = deps.doc || mount.ownerDocument;
    this.kind = deps.kind === 'number' ? 'number' : 'text';
    this.say = deps.say || ((n) => n);
    this.onChange = deps.onChange || (() => {});
    mount.classList.add('list-field');
    this.box = this.doc.createElement('textarea');
    this.box.className = 'list-field__box';
    this.box.rows = deps.rows || 5;
    this.box.spellcheck = false;
    const line = this.doc.createElement('div');
    line.className = 'list-field__line';
    this.count = this.doc.createElement('span');
    this.count.className = 'list-field__count';
    this.dup = this.doc.createElement('span');
    this.dup.className = 'meta';
    line.append(this.count, this.dup);
    mount.replaceChildren(this.box, line);
    this.box.addEventListener('input', () => { this.draw(); this.onChange(this.values()); });
    this.setValues(deps.values || []);
  }

  /** The values read from the box. */
  values() { return listValues(this.box.value, this.kind).values; }

  /** The box holds these, one a line (no onChange: the caller set them). */
  setValues(values) {
    this.box.value = (values || []).map(String).join('\n');
    this.draw();
  }

  draw() {
    const { values, duplicates } = listValues(this.box.value, this.kind);
    const [count, dup] = listCountWords(values, duplicates);
    this.count.textContent = this.say(count);
    this.dup.textContent = dup;
  }
}
