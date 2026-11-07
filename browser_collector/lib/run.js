// A run of a template: batch after batch on the tab, each batch's rows written to the product as one write, until the
// last page, the template's limit, a stop, or the product refuses the run. What was not written is kept with its reason.
import { MISS } from './batch.js';

export const ENDED = Object.freeze({ LAST: 'last page', LIMIT: 'limit', STOPPED: 'stopped', REFUSED: 'refused' });
/** Items a batch reads at most - its rows are written, and the run screen counts, every this many items. */
export const BATCH_MOST = 10;
const NOT_ALLOWED = new Set([401, 403]);

/**
 * Rows to the product, one write; a refused write is tried row by row so each refusal is named on its row.
 * product.write(rows) -> {ok: true} | {ok: false, status, detail}
 * -> {written, refused: [miss], stop: detail|null} - stop when no row of a refused write went in for a «not allowed»
 */
export async function writeRows(rows, product) {
  const all = await product.write(rows);
  if (all.ok) return { written: rows.length, refused: [], stop: null };
  const refused = [];
  let written = 0;
  let barred = null;
  for (const r of rows) {
    const one = rows.length === 1 ? all : await product.write([r]);
    if (one.ok) { written += 1; continue; }
    if (NOT_ALLOWED.has(one.status)) barred = barred || one.detail;
    refused.push({ reason: MISS.REFUSED, detail: one.detail, at: r.at, index: r.index, cells: r.cells });
  }
  const stop = written === 0 && barred && refused.every((m) => m.detail === barred) ? barred : null;
  return { written, refused: stop ? [] : refused, stop };
}

/**
 * tab      { batch(room, firstIndex) -> readBatch's answer, next() -> 'more' | 'none' }
 * product  { write(rows) }
 * -> the tally: pages, read, written, skipped, misses, ended, detail. A retry is `t.only` (the kept items' cells) with
 * `t.max` their number - it ends when each is found again.
 */
export async function runTemplate(t, tab, product, { progress = () => {}, stopped = () => false, paused = () => false, wait = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
  const tally = { pages: 1, read: 0, written: 0, skipped: 0, misses: [], ended: null, detail: null };
  const seen = new Set();
  for (;;) {
    if (paused() && !stopped()) {           // a pause holds between batches - nothing is half read
      tally.paused = true;
      progress(tally);
      while (paused() && !stopped()) await wait(300);
      tally.paused = false;
      progress(tally);
    }
    if (stopped()) { tally.ended = ENDED.STOPPED; break; }
    const room = Math.min(t.max ? t.max - tally.read : Infinity, BATCH_MOST);
    const b = await tab.batch(room, tally.read);
    tally.read += b.read;
    tally.skipped += b.skipped;
    tally.misses.push(...b.misses);
    const fresh = [];
    for (const r of b.rows) {
      if (seen.has(r.key)) tally.skipped += 1; else { seen.add(r.key); fresh.push(r); }
    }
    if (fresh.length) {
      const w = await writeRows(fresh, product);
      if (w.stop) { tally.ended = ENDED.REFUSED; tally.detail = w.stop; progress(tally); break; }
      tally.written += w.written;
      tally.misses.push(...w.refused);
    }
    progress(tally);
    if (t.max && tally.read >= t.max) { tally.ended = ENDED.LIMIT; break; }
    if (stopped()) { tally.ended = ENDED.STOPPED; break; }
    if ((b.seen ?? b.read) === room) continue;        // the page has more before its next page
    if (await tab.next() === 'none') { tally.ended = ENDED.LAST; break; }
    tally.pages += 1;
  }
  return tally;
}
