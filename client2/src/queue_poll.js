// A queue on screen reads itself again on one beat (lead 0eadab810 · 427451855): the admin's chain queue and the
// main grid's Queue tab both call this, so their interval and their skip rule are one.

/** How often a queue on screen is read again. */
export const QUEUE_POLL_MS = 5000;

/** One beat: read only while the queue is on screen and no read is on its way; true when it read. */
export function pollBeat({ onScreen, busy, read }) {
  if (!onScreen() || busy()) return Promise.resolve(false);
  return Promise.resolve(read()).then(() => true);
}

/** Beat every QUEUE_POLL_MS for as long as the page lives; a beat that fails still schedules the next. */
export function pollQueue(beat, wait = (fn, ms) => setTimeout(fn, ms)) {
  const next = () => wait(() => { beat().then(next, next); }, QUEUE_POLL_MS);
  next();
}
