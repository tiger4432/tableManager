// THE GRID'S WORLD TABS (lead 120450931 ②; owner 10-02 「원장표는 메인그리드에 하나로 하고 서브탭 같은 작게
// 추가해서 브랜치, 세상 볼 수 있게」). A small tab row over a table each ledger world has its own of: the worlds
// as the server names them, the operating one marked. It holds no world - the page's seat does - and draws
// nothing when it is shown none.

export class WorldTabs {
  /**
   * @param {object|null} mount the element this part owns
   * @param {{doc?: Document, onPick: function}} deps  `onPick(name)` - a world other than the one shown
   */
  constructor(mount, deps) {
    const options = deps || {};
    this.doc = options.doc || (typeof document !== 'undefined' ? document : null);
    this.onPick = options.onPick || null;
    this.mount = mount || null;
    this.view = null;
  }

  /** `{worlds, operating, current}` (current null: none picked - the operating world is shown), or null. */
  show(view) {
    this.view = view || null;
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.mount) return;
    this.mount.textContent = '';
    const view = this.view;
    if (!view) return;
    const shown = view.current || view.operating;
    const row = doc.createElement('div');
    row.className = 'world-tabs';
    row.setAttribute('role', 'tablist');
    row.setAttribute('aria-label', 'Ledger world');
    for (const name of Array.isArray(view.worlds) ? view.worlds : []) {
      const tab = doc.createElement('button');
      tab.className = 'world-tabs__tab';
      tab.setAttribute('type', 'button');
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', String(name === shown));
      if (name === shown) tab.classList.add('is-active');
      tab.dataset.world = name;
      tab.textContent = name;
      if (name === view.operating) {
        const mark = doc.createElement('span');
        mark.className = 'world-tabs__mark';
        mark.textContent = 'Operating';
        tab.appendChild(mark);
      }
      tab.addEventListener('click', () => { if (name !== shown && this.onPick) this.onPick(name); });
      row.appendChild(tab);
    }
    this.mount.appendChild(row);
  }
}
