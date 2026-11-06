// The last freeze of the API process, on the admin header (owner 10-29 «ㄴ», A 63a69b97a; off the grid page again - owner
// 10-29 «스톨 뱃지 빼고 원래대로»): /health's `stall` - {line, at} once a freeze has ended, null before one - drawn as the
// server wrote it in a fixed-width face, with its time, so the owner can type it from a phone. No request of its own: the
// page hands in the /health body it already read (admin.js chainPauseFrom).
import { localShort } from './server_time.js';
import './stall_line.css';

export const LAST_STALL = 'Last stall';

/** /health's last freeze: {line, at} · null (none since the server started) · undefined (not read - keep what is drawn). */
export function stallOf(health) {
  if (!health || typeof health !== 'object' || !('stall' in health)) return undefined;
  const s = health.stall;
  return s && typeof s.line === 'string' && s.line ? { line: s.line, at: s.at || null } : null;
}

export class StallLine {
  /** @param deps { doc, label } - the label the line stands under (the page's own freeze is another: ui_stall.js). */
  constructor(mount, { doc, label = LAST_STALL } = {}) {
    this.mount = mount;
    this.doc = doc || mount.ownerDocument;
    this.root = this.doc.createElement('div');
    this.root.className = 'stall-line';
    this.root.hidden = true;
    this.label = this.el('span', 'stall-line__label', label);
    this.at = this.el('span', 'stall-line__at', '');
    this.text = this.el('span', 'stall-line__text', '');
    mount.appendChild(this.root);
  }

  el(tag, cls, text) {
    const e = this.doc.createElement(tag);
    e.className = cls;
    e.textContent = text;
    this.root.appendChild(e);
    return e;
  }

  /** `stall` from stallOf: undefined leaves the line as it is. */
  render(stall) {
    if (stall === undefined) return;
    this.root.hidden = !stall;
    this.at.textContent = stall && stall.at ? localShort(stall.at) : '';
    this.text.textContent = stall ? stall.line : '';
  }
}
