// READ AGAIN — an answer the server made while it still works behind it (`updating: true`) is asked again after
// READ_AGAIN_MS, as long as the screen still shows it; one judge for every such answer (the explorer's column counts,
// the Overview's Enrichment row - lead 11-10 «판단도 하나»). Pure: no DOM, the timer is the global one at call time.
// Not pollBeat (queue_poll.js): that is a clock that beats for as long as the page lives, for a queue that changes
// without saying so; this has no clock - the server's `updating` arms one read, and its last answer stops it. The
// «on screen» question is the caller's in both, the same word (`onScreen`).
import { READ_AGAIN_MS } from './config.js';

export class ReadAgain {
  constructor() { this.timer = null; }

  /** After an answer: when it says `updating`, `ask()` once READ_AGAIN_MS has passed - if `onScreen()` holds then. */
  after(answer, onScreen, ask) {
    this.stop();
    if (!answer || answer.updating !== true) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      if (onScreen()) ask();
    }, READ_AGAIN_MS);
  }

  /** The screen closed or asked anew: nothing is asked again. */
  stop() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  get armed() { return this.timer !== null; }
}
