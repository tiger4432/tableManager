// BRANCH PICKER (lead 64c380aeb) - which ledger world a screen reads. One part, seated by the declaration
// screen and the R&D board alike: the page hands it the worlds and the operating one, and what to do on a
// pick; making, deleting and operating a branch are offered only where the page hands those as well. It
// holds no world itself - the page's one seat does. The empty choice sends no world, which reads the
// operating one, so it is named after it; every world, the default too, is picked by its name (lead
// 120450931 ①).
import { setDisabledReason } from './disabled_reason.js';
import { isBlank } from './absent.js';
import { localShortOrAsSent } from './server_time.js';

const NAME_FIRST = 'Name the branch first';
const OPERATES = 'Already the operating world';

export class BranchPicker {
  /**
   * @param {object|null} mount the element this part owns (may come later, via `attach`)
   * @param {{doc?: Document, onPick: function, onCreate?: function, onDelete?: function, onOperate?: function}} deps
   *   `onPick(name|null)` · `onCreate(name, beneath)` · `onDelete(name)` · `onOperate(name)` - null is the
   *   operating world; `beneath` is null (not chosen: the server's own), [] (nothing) or names, top first
   */
  constructor(mount, deps) {
    const options = deps || {};
    this.doc = options.doc || (typeof document !== 'undefined' ? document : null);
    this.onPick = options.onPick || null;
    this.onCreate = options.onCreate || null;
    this.onDelete = options.onDelete || null;
    this.onOperate = options.onOperate || null;
    this.worlds = [];
    this.current = null;
    this.operating = null;
    this.history = [];
    // A new branch's name and what it stands on, as chosen so far: the page redraws this part on its own renders.
    this.typed = '';
    this.beneath = null;
    this.mount = null;
    this.attach(mount);
  }

  /** Seat the part in `mount` (the same one again is fine) and draw it there. */
  attach(mount) {
    this.mount = mount || null;
    this.render();
  }

  /** The worlds there are, the one the page reads now (null = the operating one), the operating one and
   *  who operated which when. */
  show({ worlds, current, operating, history } = {}) {
    this.worlds = Array.isArray(worlds) ? worlds.slice() : [];
    this.current = current || null;
    this.operating = typeof operating === 'string' && operating ? operating : null;
    this.history = Array.isArray(history) ? history.slice() : [];
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.mount) return;
    this.mount.textContent = '';
    const box = doc.createElement('div');
    box.className = 'branch-picker';
    const label = doc.createElement('label');
    label.className = 'branch-picker__label';
    label.textContent = 'Branch';
    const select = doc.createElement('select');
    select.className = 'branch-picker__select';
    // The one being read is listed even before the list names it (a branch just made).
    const names = this.current && !this.worlds.includes(this.current) ? [...this.worlds, this.current] : this.worlds;
    const empty = this.operating ? `Operating · ${this.operating}` : 'Operating';
    for (const [value, text] of [['', empty], ...names.map((name) => [name, name])]) {
      const option = doc.createElement('option');
      option.value = value;
      option.textContent = text;
      if (value === (this.current || '')) option.selected = true;
      select.appendChild(option);
    }
    select.value = this.current || '';
    select.addEventListener('change', () => { if (this.onPick) this.onPick(select.value || null); });
    label.appendChild(select);
    box.appendChild(label);
    if (this.onCreate) {
      const name = doc.createElement('input');
      name.className = 'branch-picker__name';
      name.setAttribute('placeholder', 'New branch');
      name.setAttribute('aria-label', 'New branch');
      name.value = this.typed;
      const make = doc.createElement('button');
      make.className = 'branch-picker__create';
      make.setAttribute('type', 'button');
      make.textContent = 'Create';
      setDisabledReason(make, isBlank(this.typed) ? NAME_FIRST : '');
      name.addEventListener('input', () => {
        this.typed = name.value;
        setDisabledReason(make, isBlank(name.value) ? NAME_FIRST : '');
      });
      make.addEventListener('click', () => {
        if (isBlank(name.value)) return;
        const beneath = this.beneath;
        this.typed = '';
        this.beneath = null;
        this.onCreate(String(name.value).trim(), beneath);
      });
      box.append(name, this.beneathRow(), make);
    }
    if (this.onDelete && this.current) {
      const drop = doc.createElement('button');
      drop.className = 'branch-picker__delete btn-danger';
      drop.setAttribute('type', 'button');
      drop.textContent = 'Delete branch';
      drop.addEventListener('click', () => this.onDelete(this.current));
      box.appendChild(drop);
    }
    if (this.onOperate) box.append(...this.operateRow());
    this.mount.appendChild(box);
  }

  /** What a new branch stands on: Nothing, or worlds pressed in order (top first). Pressing a picked one
   *  again takes it out; none pressed sends nothing, and the server's own choice stands. */
  beneathRow() {
    const doc = this.doc;
    const row = doc.createElement('div');
    row.className = 'branch-picker__beneath';
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', 'Beneath');
    const head = doc.createElement('span');
    head.className = 'branch-picker__beneath-label';
    head.textContent = 'Beneath';
    row.appendChild(head);
    const chip = (text, pressed, next) => {
      const b = doc.createElement('button');
      b.className = 'branch-picker__chip';
      b.setAttribute('type', 'button');
      b.setAttribute('aria-pressed', String(pressed));
      if (pressed) b.classList.add('is-on');
      b.textContent = text;
      b.addEventListener('click', () => { this.beneath = next; this.render(); });
      row.appendChild(b);
    };
    const list = this.beneath || [];
    const nothing = Array.isArray(this.beneath) && this.beneath.length === 0;
    chip('Nothing', nothing, nothing ? null : []);
    for (const world of this.worlds) {
      const at = list.indexOf(world);
      const rest = list.filter((name) => name !== world);
      chip(at >= 0 ? `${at + 1} · ${world}` : world, at >= 0, at >= 0 ? (rest.length ? rest : null) : [...list, world]);
    }
    return row;
  }

  /** The operating world, the switch to the one being read, and who operated which when (newest first). */
  operateRow() {
    const doc = this.doc;
    const parts = [];
    if (this.current) {
      const now = doc.createElement('span');
      now.className = 'branch-picker__operating';
      now.textContent = this.operating ? `Operating · ${this.operating}` : 'Operating';
      parts.push(now);
    }
    const go = doc.createElement('button');
    go.className = 'branch-picker__operate';
    go.setAttribute('type', 'button');
    go.textContent = 'Operate';
    const operates = !this.current || this.current === this.operating;
    setDisabledReason(go, operates ? OPERATES : '');
    go.addEventListener('click', () => { if (!operates) this.onOperate(this.current); });
    parts.push(go);
    if (this.history.length) {
      const log = doc.createElement('details');
      log.className = 'branch-picker__history';
      const summary = doc.createElement('summary');
      summary.textContent = `History · ${this.history.length}`;
      const lines = doc.createElement('ol');
      for (const entry of this.history.slice().reverse()) {
        const line = doc.createElement('li');
        line.textContent = [entry && entry.world, entry && entry.by, localShortOrAsSent(entry && entry.at)]
          .filter((word) => !isBlank(word)).join(' · ');
        lines.appendChild(line);
      }
      log.append(summary, lines);
      parts.push(log);
    }
    return parts;
  }
}
