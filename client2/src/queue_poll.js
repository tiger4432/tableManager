// A queue on screen reads itself again on one beat (lead 0eadab810 · 427451855): the admin's chain queue and the
// main grid's Queue tab both call this, so their interval and their skip rule are one.

/** How often a queue on screen is read again. */
export const QUEUE_POLL_MS = 5000;
/** How long a queue read may take: past it the read is cut and the next beat reads again (owner 10-11 Q). */
export const QUEUE_READ_TIMEOUT_MS = 15000;
/** What a cut read says on its screen. */
export const READ_TIMED_OUT = 'Read timed out · retrying';

/** A queue read cut at its time. */
export class QueueReadTimeout extends Error {
  constructor() { super(READ_TIMED_OUT); this.name = 'QueueReadTimeout'; }
}

/** A queue read that cannot hold its screen: `request(signal)` aborted at QUEUE_READ_TIMEOUT_MS and the read rejects
 *  with QueueReadTimeout - whoever started it, the beat, a Refresh, a broadcast; a request that ignores the signal too. */
export function timedRead(request, wait = (fn, ms) => setTimeout(fn, ms), stop = (t) => clearTimeout(t)) {
  const control = new AbortController();
  let timer = null;
  const cut = new Promise((_, reject) => {
    timer = wait(() => { reject(new QueueReadTimeout()); control.abort(); }, QUEUE_READ_TIMEOUT_MS);
  });
  return Promise.race([Promise.resolve().then(() => request(control.signal)), cut]).finally(() => stop(timer));
}

/** How long ago a screen last read its queue, in its line; none read yet, none. */
export function readAgeWords(lastReadAt, now) {
  return lastReadAt == null ? '' : `Read ${Math.max(0, Math.round((now - lastReadAt) / 1000))} s ago`;
}

/** One beat: read only while the queue is on screen and no read is on its way - a beat that finds one says how long
 *  since the last (`waiting`); true when it read. */
export function pollBeat({ onScreen, busy, read, waiting = () => {} }) {
  if (!onScreen()) return Promise.resolve(false);
  if (busy()) { waiting(); return Promise.resolve(false); }
  return Promise.resolve(read()).then(() => true);
}

/** Beat every QUEUE_POLL_MS for as long as the page lives - the next beat does not wait on this one's read, so a beat
 *  that finds it still on its way says its age (owner 10-11 Q); a beat that fails still leaves the next. */
export function pollQueue(beat, wait = (fn, ms) => setTimeout(fn, ms)) {
  const next = () => wait(() => { Promise.resolve().then(beat).catch(() => {}); next(); }, QUEUE_POLL_MS);
  next();
}
