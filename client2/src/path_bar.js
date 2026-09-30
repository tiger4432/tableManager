// ═══════════════════════════════════════════════════════════════════════════════
// PATH BAR (lead 619befe8c, owner 09-30 「내가 지금 어디의 하위 선언을 고치고 있는지」).
//
// One line of steps — root first — for whatever node the page hands it, each step a button that
// asks the page to go there. It knows nothing about the form: the steps and their words come
// from the page, which reads them off the form's own rows, so every word is the skeleton's.
// It draws only inside its mount. A page that rebuilds that mount seats the bar again (`attach`).
// ═══════════════════════════════════════════════════════════════════════════════

export class PathBar {
  /**
   * @param {object|null} mount the element this bar owns (may come later, via `attach`)
   * @param {{doc?: Document, onPick?: (path: string) => void}} deps
   */
  constructor(mount, deps) {
    const options = deps || {};
    this.doc = options.doc || (typeof document !== 'undefined' ? document : null);
    this.onPick = options.onPick || (() => {});
    this.mount = null;
    this.trail = [];
    this.attach(mount);
  }

  /** Seat the bar in `mount` (the same one again is fine) and draw the last trail there. */
  attach(mount) {
    this.mount = mount || null;
    this.render();
  }

  /** Show a trail: `[{ path, label }]`, root first. The last step is where the hand is. */
  show(trail) {
    this.trail = Array.isArray(trail) ? trail.slice() : [];
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.mount) return;
    this.mount.textContent = '';
    const bar = doc.createElement('nav');
    bar.className = 'oe-path-bar';
    bar.setAttribute('aria-label', 'Path');
    this.trail.forEach((step, i) => {
      if (i) {
        const sep = doc.createElement('span');
        sep.className = 'oe-path-sep';
        sep.textContent = '›';
        sep.setAttribute('aria-hidden', 'true');
        bar.appendChild(sep);
      }
      const here = i === this.trail.length - 1;
      const go = doc.createElement('button');
      go.className = 'oe-path-step';
      go.setAttribute('type', 'button');
      go.setAttribute('data-path', step.path);
      go.textContent = step.label || step.path;
      // One line: an ancestor may shrink to «…», so its whole word stays one hover away.
      go.setAttribute('title', step.label || step.path);
      if (here) go.setAttribute('aria-current', 'true');
      else if (go.addEventListener) go.addEventListener('click', () => this.onPick(step.path));
      bar.appendChild(go);
    });
    this.mount.appendChild(bar);
  }
}
