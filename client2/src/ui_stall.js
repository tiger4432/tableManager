// UI STALL — the page's own freeze, said as the server's STALL line is (lead 11-06 ㄱ, owner «자꾸 클라 ui 가 굳는데 · 클릭
// 휠 무반응»): a main-thread task of a second or more, once it has ended, as one short line «UI 3.4s ws batch_row_upsert
// dt_log 500» - seconds, what the page was doing, the table, the rows.
// What it was doing is the work marked in that slice (markWork). The heavy places carry one - an AST census on 11-06
// found 118 calls that redraw or refit the main grid in 54 functions; a mark goes on the slices those calls run in. A
// stall in no marked slice says «?», never a guess.
import { isCount } from './absent.js';

/** A task this long is a stall (lead 11-06: «1 s 넘는 멈춤»). */
export const UI_STALL_MS = 1000;
const KEEP = 200;

// The one main thread's slices, newest last. Module state on purpose: every module marks into it without being handed
// anything, as every module draws into the one toast stack.
const works = [];

/** The rest of this synchronous slice is `name` (on `table`, `rows` rows): it ends at the slice's end - the next await or
 *  return - so a mark never stays open across a wait. */
export function markWork(name, table = null, rows = null) {
  const work = { name, table, rows, start: performance.now(), end: null };
  works.push(work);
  // a slice still open is never let go - a slice of 500 marks inside a socket message lost the message's name (box 11-06)
  if (works.length > KEEP && works[0].end !== null) works.shift();
  queueMicrotask(() => { work.end = performance.now(); });
}

/** The marked slice a task of [start, start + ms] spent most of its time in, or null. `within` a slice: the one marked
 *  inside it, under another name, that covered most of the task - where the slice's time went (lead 11-06). */
export function workOf(start, ms, log = works, within = null) {
  let best = null;
  let most = 0;
  for (const work of log) {
    if (within && (work === within || work.name === within.name || work.start < within.start)) continue;
    const overlap = Math.min(start + ms, work.end ?? Infinity) - Math.max(start, work.start);
    if (overlap > most) { most = overlap; best = work; }
  }
  return best;
}

/** «UI 3.4s <what> <table> <rows> › <inner>» - the parts there are; nothing marked, «?». */
export function uiStallLine(ms, work, inner = null) {
  const parts = [`UI ${(ms / 1000).toFixed(1)}s`];
  if (!work) parts.push('?');
  else {
    parts.push(work.name);
    if (work.table) parts.push(work.table);
    if (isCount(work.rows)) parts.push(String(work.rows));
    if (inner) parts.push('›', inner.name);
  }
  return parts.join(' ');
}

export class UiStallWatch {
  /** @param deps { view: the window, onStall({line, at}), nowIso: () => string } - long tasks where the browser reports
   *  them, else the gap between two frames while the page is shown. */
  constructor({ view = globalThis, onStall, nowIso = () => new Date().toISOString() } = {}) {
    this.view = view;
    this.onStall = onStall;
    this.nowIso = nowIso;
    const Observer = view.PerformanceObserver;
    if (Observer && (Observer.supportedEntryTypes || []).includes('longtask')) {
      new Observer((list) => { for (const e of list.getEntries()) this.seen(e.startTime, e.duration); }).observe({ type: 'longtask' });
    } else if (typeof view.requestAnimationFrame === 'function') {
      let last = null;
      const frame = (at) => {
        const doc = view.document;
        if (doc && doc.hidden) last = null;
        else { if (last !== null) this.seen(last, at - last); last = at; }
        view.requestAnimationFrame(frame);
      };
      view.requestAnimationFrame(frame);
    }
  }

  /** A task of `ms` from `start`: a stall said; the instrument only ever goes quiet itself. */
  seen(start, ms) {
    if (ms < UI_STALL_MS) return;
    try {
      const work = workOf(start, ms);
      this.onStall({ line: uiStallLine(ms, work, work && workOf(start, ms, undefined, work)), at: this.nowIso() });
    }
    catch (err) { console.warn('[ui stall] a stall was not said:', err && err.message); }
  }
}
