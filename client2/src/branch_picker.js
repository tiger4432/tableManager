// BRANCH PICKER (lead 64c380aeb) - which ledger worlds a screen reads. One part, seated by the declaration
// screen, the walk and the R&D board: the page hands it the worlds and the operating one, and what to do on a
// pick; making, deleting, operating and pausing a world are offered only where the page hands those as well.
// It holds no world itself - the page's one seat does. The empty choice sends no world, which reads the
// operating one, so it is named after it; every world, the default too, is picked by its name (lead
// 120450931 ①). The declaration screen edits one world (`onPick`); a walk reads several, pressed in order -
// the earlier pick wins a vocabulary tie (`onPickSet`, lead 99032248f).
import { setDisabledReason } from './disabled_reason.js';
import { isBlank } from './absent.js';
import { localShortOrAsSent } from './server_time.js';

const NAME_FIRST = 'Name the branch first';
const OPERATES = 'Already the operating world';

export class BranchPicker {
  /**
   * @param {object|null} mount the element this part owns (may come later, via `attach`)
   * @param {{doc?: Document, onPick?: function, onPickSet?: function, onCreate?: function, onDelete?: function,
   *          onOperate?: function, onLive?: function}} deps
   *   `onPick(name|null)` (one world, null the operating one) or `onPickSet(names)` (several, in pressed order,
   *   [] the operating one) · `onCreate(name, copyFrom|null)` (null: an empty declaration) · `onDelete(name)` ·
   *   `onOperate(name)` · `onLive(name, live)`
   */
  constructor(mount, deps) {
    const options = deps || {};
    this.doc = options.doc || (typeof document !== 'undefined' ? document : null);
    this.onPick = options.onPick || null;
    this.onPickSet = options.onPickSet || null;
    this.onCreate = options.onCreate || null;
    this.onDelete = options.onDelete || null;
    this.onOperate = options.onOperate || null;
    this.onLive = options.onLive || null;
    this.worlds = [];
    this.current = this.onPickSet ? [] : null;
    this.operating = '';
    this.history = [];
    this.live = {};
    // A new branch's name and what it starts from, as chosen so far: the page redraws this part on its own renders.
    this.typed = '';
    this.copyFrom = '';
    this.mount = null;
    this.attach(mount);
  }

  /** Seat the part in `mount` (the same one again is fine) and draw it there. */
  attach(mount) {
    this.mount = mount || null;
    this.render();
  }

  /** The worlds there are, the one(s) the page reads now (none = the operating one), the operating one, who
   *  operated which when, and which worlds follow their tables live (`{world: false}` paused; absent = live). */
  show({ worlds, current, operating, history, live } = {}) {
    this.worlds = Array.isArray(worlds) ? worlds.slice() : [];
    this.current = this.onPickSet ? (Array.isArray(current) ? current.filter(Boolean) : []) : (current || null);
    this.operating = typeof operating === 'string' ? operating : '';
    this.history = Array.isArray(history) ? history.slice() : [];
    this.live = live && typeof live === 'object' ? { ...live } : {};
    this.render();
  }

  /** A world's words: its name, and `Paused` while it does not follow its tables. */
  nameOf(world) {
    return this.live[world] === false ? `${world} · Paused` : world;
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.mount) return;
    this.mount.textContent = '';
    const box = doc.createElement('div');
    box.className = 'branch-picker';
    const empty = `Operating · ${this.operating}`;
    if (this.onPickSet) box.appendChild(this.setRow(empty));
    else {
      const label = doc.createElement('label');
      label.className = 'branch-picker__label';
      label.textContent = 'Branch';
      const select = doc.createElement('select');
      select.className = 'branch-picker__select';
      // The one being read is listed even before the list names it (a branch just made).
      const names = this.current && !this.worlds.includes(this.current) ? [...this.worlds, this.current] : this.worlds;
      for (const [value, text] of [['', empty], ...names.map((name) => [name, this.nameOf(name)])]) {
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
    }
    if (this.onCreate) {
      const name = doc.createElement('input');
      name.className = 'branch-picker__name';
      name.setAttribute('placeholder', 'New branch');
      name.setAttribute('aria-label', 'New branch');
      name.value = this.typed;
      // What it starts from: an empty declaration, or a copy of one world's - copied once, then its own.
      const from = doc.createElement('select');
      from.className = 'branch-picker__copy';
      from.setAttribute('aria-label', 'Start from');
      for (const [value, text] of [['', 'Empty'], ...this.worlds.map((world) => [world, `Copy of ${world}`])]) {
        const option = doc.createElement('option');
        option.value = value;
        option.textContent = text;
        if (value === this.copyFrom) option.selected = true;
        from.appendChild(option);
      }
      from.value = this.copyFrom;
      from.addEventListener('change', () => { this.copyFrom = from.value; });
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
        const copyFrom = this.copyFrom || null;
        this.typed = '';
        this.copyFrom = '';
        this.onCreate(String(name.value).trim(), copyFrom);
      });
      box.append(name, from, make);
    }
    if (this.onDelete && this.current) {
      const drop = doc.createElement('button');
      drop.className = 'branch-picker__delete btn-danger';
      drop.setAttribute('type', 'button');
      drop.textContent = 'Delete branch';
      drop.addEventListener('click', () => this.onDelete(this.current));
      box.appendChild(drop);
    }
    if (this.onOperate) box.append(...this.operateRow(empty));
    if (this.onLive) box.appendChild(this.liveButton());
    this.mount.appendChild(box);
  }

  /** The worlds a walk reads, pressed in order (top first); pressing a picked one takes it out, and the empty
   *  choice - first, pressed while none is - clears them. Each press hands the page the whole new list. */
  setRow(empty) {
    const doc = this.doc;
    const row = doc.createElement('div');
    row.className = 'branch-picker__set';
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', 'Worlds');
    const head = doc.createElement('span');
    head.className = 'branch-picker__set-label';
    head.textContent = 'Worlds';
    row.appendChild(head);
    const chip = (text, pressed, next) => {
      const b = doc.createElement('button');
      b.className = 'branch-picker__chip';
      b.setAttribute('type', 'button');
      b.setAttribute('aria-pressed', String(pressed));
      if (pressed) b.classList.add('is-on');
      b.textContent = text;
      b.addEventListener('click', () => { this.onPickSet(next); });
      row.appendChild(b);
    };
    const list = this.current;
    chip(empty, list.length === 0, []);
    for (const world of [...this.worlds, ...list.filter((name) => !this.worlds.includes(name))]) {
      const at = list.indexOf(world);
      chip(at >= 0 ? `${at + 1} · ${world}` : world, at >= 0,
        at >= 0 ? list.filter((name) => name !== world) : [...list, world]);
    }
    return row;
  }

  /** The operating world, the switch to the one being read, and who switched what when (newest first). */
  operateRow(empty) {
    const doc = this.doc;
    const parts = [];
    if (this.current) {
      const now = doc.createElement('span');
      now.className = 'branch-picker__operating';
      now.textContent = empty;
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
        // One list holds both switches: a live entry says which way, the rest made the world the operating one.
        const what = entry && typeof entry.live === 'boolean' ? (entry.live ? 'Live' : 'Paused') : 'Operating';
        line.textContent = [entry && entry.world, what, entry && entry.by, localShortOrAsSent(entry && entry.at)]
          .filter((word) => !isBlank(word)).join(' · ');
        lines.appendChild(line);
      }
      log.append(summary, lines);
      parts.push(log);
    }
    return parts;
  }

  /** Pause or resume the world being read (none read: the operating one) - whether it follows its tables live. */
  liveButton() {
    const doc = this.doc;
    const world = this.current || this.operating;
    const live = this.live[world] !== false;
    const toggle = doc.createElement('button');
    toggle.className = 'branch-picker__live';
    toggle.setAttribute('type', 'button');
    toggle.setAttribute('aria-pressed', String(live));
    toggle.textContent = live ? 'Pause live' : 'Resume live';
    setDisabledReason(toggle, world ? '' : 'No world read');
    toggle.addEventListener('click', () => { if (world) this.onLive(world, !live); });
    return toggle;
  }
}
