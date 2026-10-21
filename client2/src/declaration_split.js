/**
 * Form D (owner 10-20 «d가 괜찮네», lead f3639d4a2): one declaration, two editors of it side by side - its text on the
 * left, the folded form on the right. The one seat both declaration windows lay out with (raw_registry_panel's table
 * and chain windows, the explorer's ledger window); a part holds its own nodes, no module state.
 *
 * Text that does not read as JSON: its line is marked in the gutter and said under the text, the form stays on the
 * last document that read and takes no edit (its fieldset is off), and the caller keeps Save off with `fault.message`.
 */

/** Where a text fails to read as JSON: `{ line, message }` (line 1-based, null when the parser names no place), or null
 *  when it reads. Empty reads as `{}` - both windows save an empty box as an empty document. */
export function jsonFault(text) {
  const raw = String(text == null ? '' : text);
  if (!raw.trim()) return null;
  try {
    JSON.parse(raw);
    return null;
  } catch (e) {
    const message = String((e && e.message) || e);
    // V8's sentence (Chrome · Edge · node): «... in JSON at position N». No position named: the line is not guessed.
    const at = /position (\d+)/.exec(message);
    const line = at ? raw.slice(0, Number(at[1])).split('\n').length : null;
    return { line, message };
  }
}

const withClass = (node, cls, on) => {
  const words = String(node.className || '').split(/\s+/).filter((w) => w && w !== cls);
  node.className = (on ? [...words, cls] : words).join(' ');
};

export class DeclarationSplit {
  /**
   * @param doc   the document to build in
   * @param area  the textarea that holds the declaration's text - the caller's; the caller's input handler calls `sync`
   */
  constructor(doc, area) {
    this.doc = doc;
    this.area = area;
    this.el = doc.createElement('div');
    this.el.className = 'decl-split';
    const text = doc.createElement('section');
    text.className = 'decl-split__text';
    text.setAttribute('aria-label', 'Text');
    // The text is as tall as its lines (`rows`) and scrolls with its gutter in this one box - no scroll to follow.
    const body = doc.createElement('div');
    body.className = 'decl-split__body';
    this.gutter = doc.createElement('div');
    this.gutter.className = 'decl-split__gutter';
    this.gutter.setAttribute('aria-hidden', 'true');
    withClass(area, 'decl-split__area', true);
    area.setAttribute('wrap', 'off');
    area.setAttribute('spellcheck', 'false');
    body.appendChild(this.gutter);
    body.appendChild(area);
    this.said = doc.createElement('div');
    this.said.className = 'decl-split__fault';
    this.said.setAttribute('role', 'status');
    text.appendChild(body);
    text.appendChild(this.said);
    this.form = doc.createElement('fieldset');
    this.form.className = 'decl-split__form';
    this.form.setAttribute('aria-label', 'Form');
    this.el.appendChild(text);
    this.el.appendChild(this.form);
    this.fault = null;
    this.sync();
  }

  /** The form's content, drawn by the caller (renderSkeletonForm, or a read-only view). */
  setForm(...nodes) {
    this.form.textContent = '';
    for (const node of nodes) if (node) this.form.appendChild(node);
    this.form.disabled = Boolean(this.fault);
    return this;
  }

  /** Read the text again: the gutter's numbers, the bad line, the sentence, the form on or off. Returns the fault. */
  sync() {
    const raw = String(this.area.value == null ? '' : this.area.value);
    this.fault = jsonFault(raw);
    const lines = raw.split('\n').length;
    // one more than its lines: a long line's scrollbar does not cover the last
    this.area.rows = lines + 1;
    if (this.gutter.children.length !== lines) {
      this.gutter.textContent = '';
      for (let n = 1; n <= lines; n += 1) {
        const cell = this.doc.createElement('span');
        cell.textContent = String(n);
        this.gutter.appendChild(cell);
      }
    }
    const bad = this.fault && this.fault.line ? this.fault.line - 1 : -1;
    [...this.gutter.children].forEach((cell, i) => withClass(cell, 'is-bad', i === bad));
    this.said.textContent = this.fault
      ? (this.fault.line ? `Line ${this.fault.line} · ${this.fault.message}` : this.fault.message)
      : '';
    this.said.hidden = !this.fault;
    withClass(this.el, 'is-faulty', Boolean(this.fault));
    this.form.disabled = Boolean(this.fault);
    return this.fault;
  }
}
