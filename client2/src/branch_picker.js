// BRANCH PICKER (lead 64c380aeb) - which ledger world a screen reads. One part, seated by the declaration
// screen and the R&D board alike: the page hands it the branch list (GET /api/ledger/declaration's
// `worlds`) and what to do on a pick; making and deleting a branch are offered only where the page hands
// those two as well. It holds no world itself - the page's one seat does.
import { setDisabledReason } from './disabled_reason.js';
import { isBlank } from './absent.js';

export const DEFAULT_BRANCH = 'Default';
const NAME_FIRST = 'Name the branch first';

export class BranchPicker {
  /**
   * @param {object|null} mount the element this part owns (may come later, via `attach`)
   * @param {{doc?: Document, onPick: function, onCreate?: function, onDelete?: function}} deps
   *   `onPick(name|null)` · `onCreate(name)` · `onDelete(name)` - null is the default world
   */
  constructor(mount, deps) {
    const options = deps || {};
    this.doc = options.doc || (typeof document !== 'undefined' ? document : null);
    this.onPick = options.onPick || null;
    this.onCreate = options.onCreate || null;
    this.onDelete = options.onDelete || null;
    this.worlds = [];
    this.current = null;
    // A new branch's name as typed so far: the page redraws this part on its own renders.
    this.typed = '';
    this.mount = null;
    this.attach(mount);
  }

  /** Seat the part in `mount` (the same one again is fine) and draw it there. */
  attach(mount) {
    this.mount = mount || null;
    this.render();
  }

  /** The branches there are, and the one the page reads now (null = the default). */
  show({ worlds, current } = {}) {
    this.worlds = Array.isArray(worlds) ? worlds.slice() : [];
    this.current = current || null;
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
    for (const [value, text] of [['', DEFAULT_BRANCH], ...names.map((name) => [name, name])]) {
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
        if (!isBlank(name.value)) { this.typed = ''; this.onCreate(String(name.value).trim()); }
      });
      box.append(name, make);
    }
    if (this.onDelete && this.current) {
      const drop = doc.createElement('button');
      drop.className = 'branch-picker__delete btn-danger';
      drop.setAttribute('type', 'button');
      drop.textContent = 'Delete branch';
      drop.addEventListener('click', () => this.onDelete(this.current));
      box.appendChild(drop);
    }
    this.mount.appendChild(box);
  }
}
