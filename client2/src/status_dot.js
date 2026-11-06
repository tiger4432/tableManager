// The head bar's status button (lead 11-05 ③, mockup v3): API · Live · Chain · Last · Account · Last stall live in its
// panel; the button is a dot while all is well and says the one thing that is not. It reads the badges the writers
// already draw (api.js setBadge · websocket.js) - no word of its own - and /health's stall through stall_line.js.
// Opening and closing the panel is the page's (main.js headPanel), as for ⋯.
import { StallLine } from './stall_line.js';
import { parseServerInstant } from './server_time.js';

/** A stall this recent turns the button orange (lead 11-05: «within 10 min, one constant»). */
export const STALL_RECENT_MS = 10 * 60 * 1000;
/** The page's own freeze stands under this, beside the server's «Last stall». */
export const LAST_UI_STALL = 'Last UI stall';

const wordOf = (text) => String(text).trim().replace(/:\s*/, ' · ');

/** A stall ({line, at} · null) that ended within STALL_RECENT_MS of `now` - the server's and the page's alike. */
function recent(stall, now) {
  const at = stall && parseServerInstant(stall.at);
  return Boolean(at && now - at.getTime() < STALL_RECENT_MS);
}

/**
 * What the button says, from the badges ({text, cls} each), the server's last stall and the page's (ui_stall.js), each
 * {line, at} · null. Order: a badge offline · a server stall within STALL_RECENT_MS · the page's · a chain running · a
 * badge not read yet · all well.
 * @returns {{tone: 'bad'|'busy'|'unknown'|'ok', word: string}}
 */
export function statusOf(badges, stall, now, uiStall = null) {
  const bad = badges.find((b) => /\boffline\b/.test(b.cls));
  if (bad) return { tone: 'bad', word: wordOf(bad.text) };
  if (recent(stall, now)) return { tone: 'busy', word: 'STALL' };
  if (recent(uiStall, now)) return { tone: 'busy', word: 'UI STALL' };
  const running = badges.find((b) => /:\s*RUNNING$/.test(String(b.text).trim()));
  if (running) return { tone: 'busy', word: wordOf(running.text) };
  if (badges.some((b) => !/\bonline\b/.test(b.cls))) return { tone: 'unknown', word: '' };
  return { tone: 'ok', word: '' };
}

export class StatusDot {
  /**
   * @param button  the head bar's status button (its dot and word spans inside)
   * @param panel   its panel: the badges (.status-badge) and the Last line are in it; the stall line is added to it
   * @param deps    { doc, now: () => ms }
   */
  constructor(button, panel, { doc, now } = {}) {
    this.button = button;
    this.panel = panel;
    this.doc = doc || button.ownerDocument;
    this.now = now || (() => Date.now());
    this.stall = null;
    this.uiStall = null;
    this.stallLine = new StallLine(panel, { doc: this.doc });
    this.uiStallLine = new StallLine(panel, { doc: this.doc, label: LAST_UI_STALL });
    this.word = button.querySelector('.status-btn__word');
    const View = this.doc.defaultView && this.doc.defaultView.MutationObserver;
    if (View) {
      this.watch = new View(() => this.draw());
      for (const badge of panel.querySelectorAll('.status-badge')) {
        this.watch.observe(badge, { attributes: true, attributeFilter: ['class'], childList: true, characterData: true, subtree: true });
      }
    }
    this.draw();
  }

  /** `stall` from stallOf: undefined (not read) keeps what is drawn. */
  setStall(stall) {
    if (stall === undefined) return;
    this.stall = stall;
    this.stallLine.render(stall);
    this.draw();
  }

  /** The page's own last freeze (ui_stall.js), {line, at}. */
  setUiStall(stall) {
    this.uiStall = stall;
    this.uiStallLine.render(stall);
    this.draw();
  }

  draw() {
    const badges = [...this.panel.querySelectorAll('.status-badge')].map((b) => ({ text: b.textContent, cls: b.className }));
    const { tone, word } = statusOf(badges, this.stall, this.now(), this.uiStall);
    this.button.dataset.tone = tone;
    if (this.word.textContent !== word) this.word.textContent = word;
    this.button.title = badges.map((b) => b.text.trim()).join(' · ');
  }
}
