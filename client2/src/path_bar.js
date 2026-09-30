// ═══════════════════════════════════════════════════════════════════════════════
// PATH BAR (lead 619befe8c, owner 09-30 「내가 지금 어디의 하위 선언을 고치고 있는지」).
//
// THE path widget of the explorer, drawn twice there: the declaration trail at the top of the
// workspace and the form trail under the hand (lead d4a949a8c ㉯ - one widget, not two). Steps root
// first, each a button the page's own delegated click handles (`data-action` · `data-value`), so a
// pick does what that action already does; the current step asks nothing. The box around it is the
// seat's (CSS), and it knows no word of the form: the page hands it the steps.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * @param {Document} doc
 * @param {Array<{label: string, action: string, value: string, current?: boolean,
 *   dataset?: Object<string, string>}>} steps root first
 */
export function pathSteps(doc, steps) {
  const bar = doc.createElement('nav');
  bar.className = 'oe-path-bar';
  bar.setAttribute('aria-label', 'Path');
  (steps || []).forEach((step, i) => {
    if (i) {
      const sep = doc.createElement('span');
      sep.className = 'oe-path-sep';
      sep.textContent = '›';
      sep.setAttribute('aria-hidden', 'true');
      bar.appendChild(sep);
    }
    // Where you are is a word, the rest are buttons (a button on this screen is always pressable).
    const go = doc.createElement(step.current ? 'span' : 'button');
    go.className = 'oe-path-step';
    if (!step.current) go.setAttribute('type', 'button');
    go.textContent = step.label;
    // One line: an ancestor may shrink to «…», so its whole word stays one hover away.
    go.setAttribute('title', step.label);
    if (step.current) go.setAttribute('aria-current', 'true');
    else {
      go.dataset.action = step.action;
      go.dataset.value = step.value;
      for (const [key, value] of Object.entries(step.dataset || {})) go.dataset[key] = value;
    }
    bar.appendChild(go);
  });
  return bar;
}

export class PathBar {
  /**
   * @param {object|null} mount the element this bar owns (may come later, via `attach`)
   * @param {{doc?: Document, action: string}} deps `action`: what a picked step asks the page to do
   */
  constructor(mount, deps) {
    const options = deps || {};
    this.doc = options.doc || (typeof document !== 'undefined' ? document : null);
    this.action = options.action;
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
    if (!this.doc || !this.mount) return;
    this.mount.textContent = '';
    const last = this.trail.length - 1;
    this.mount.appendChild(pathSteps(this.doc, this.trail.map((step, i) => ({
      label: step.label || step.path, action: this.action, value: step.path, current: i === last,
    }))));
  }
}
