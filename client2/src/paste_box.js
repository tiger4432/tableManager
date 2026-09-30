// ═══════════════════════════════════════════════════════════════════════════════
// PASTE BOX — where smart paste takes Ctrl+V when the clipboard cannot be read by a click
// (plain HTTP has no navigator.clipboard; a browser may refuse it). Lead 4311a51ed, owner 09-30.
//
// It reads nothing. The paste event it receives bubbles to the one paste listener
// (clipboard.js), which hands it to the smart paste reader while the paste is armed.
// 🔴 So the zone is a focusable div, never a field: that listener skips a paste whose focus is
//    an input, a textarea or contenteditable, and the paste would go into the field instead.
//    For the same reason the caret stays in the zone: Tab does not leave it, and a press on the
//    card does not blur it.
// The dialog shell is the clipboard type modal's (`ctm-overlay` · `ctm-card`); the look is CSS.
// ═══════════════════════════════════════════════════════════════════════════════

export class PasteBox {
  /**
   * @param {HTMLElement} mount where this part seats its own div
   * @param {{doc?: Document}} [deps]
   */
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('PasteBox needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    this.root = null;
  }

  _el(tag, cls, text) {
    const el = this.doc.createElement(tag);
    el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  /**
   * @param {{onCancel: Function, keyLabel: string}} hooks a press and release on the scrim cancels
   */
  open({ onCancel, keyLabel }) {
    this.close();
    const overlay = this._el('div', 'ctm-overlay');
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Smart paste');
    const card = this._el('div', 'ctm-card pbx-card');
    const zone = this._el('div', 'pbx-zone', `Paste here (${keyLabel})`);
    zone.setAttribute('tabindex', '0');
    card.append(this._el('h3', 'ctm-title', 'Smart paste'), zone,
      this._el('p', 'ctm-sub', 'Esc to cancel'));
    overlay.append(card);
    // A drag that starts in the card and ends on the scrim lands its click on the overlay too.
    let pressedScrim = false;
    overlay.addEventListener('mousedown', (e) => {
      pressedScrim = e.target === overlay;
      if (e.target !== zone) e.preventDefault();
    });
    overlay.addEventListener('click', (e) => { if (pressedScrim && e.target === overlay) onCancel(); });
    zone.addEventListener('keydown', (e) => { if (e.key === 'Tab') e.preventDefault(); });
    this.mount.appendChild(overlay);
    this.root = overlay;
    void overlay.offsetWidth;
    overlay.classList.add('is-open');
    zone.focus();
    return zone;
  }

  close() {
    const overlay = this.root;
    this.root = null;
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }
}
