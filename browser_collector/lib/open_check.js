// When an opened item counts as open (owner 11-07): the content area is SHOWN, its visible text CHANGED from the moment
// before the click, and - when the template names a pair - the item's value equals the content's. «Shown» alone is not
// enough: a page may keep the content area in the DOM hidden, or keep the previous item's text in it.

/** The text a person sees in `el` - innerText, never textContent (that one reads hidden text too). */
export const visibleText = (el) => (el && typeof el.innerText === 'string' ? el.innerText.trim() : '');

/** Is `el` on the screen: drawn (checkVisibility), not 0 in size, inside every clipping ancestor and inside the window. */
export function shown(el, win = globalThis) {
  if (!el || !el.isConnected) return false;
  if (typeof el.checkVisibility === 'function'
    && !el.checkVisibility({ opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true })) return false;
  const r = el.getBoundingClientRect();
  if (!(r.width > 0 && r.height > 0)) return false;
  const outside = (c) => r.right <= c.left || r.left >= c.right || r.bottom <= c.top || r.top >= c.bottom;
  for (let a = el.parentElement; a; a = a.parentElement) {
    const s = win.getComputedStyle(a);
    if ((s.overflowX !== 'visible' || s.overflowY !== 'visible') && outside(a.getBoundingClientRect())) return false;
  }
  return !outside({ left: 0, top: 0, right: win.innerWidth, bottom: win.innerHeight });
}

/** One look at the content area -> null when it is open, else why not. */
export function notOpenYet({ before, after, isShown, pair }) {
  if (!isShown) return 'content not shown';
  if (after === before) return 'content did not change';
  if (pair && pair.item !== pair.content) return 'content is another item';
  return null;
}

/** Look until the item is open or `limitMs` passes -> {opened: true} | {opened: false, detail}. */
export async function waitOpened(look, { before, limitMs, everyMs = 100, now = () => Date.now(), sleep = (ms) => new Promise((r) => setTimeout(r, ms)) }) {
  const end = now() + limitMs;
  let why = 'content not shown';
  for (;;) {
    why = notOpenYet({ before, ...look() });
    if (!why) return { opened: true };
    if (now() >= end) return { opened: false, detail: `${why} in ${Math.round(limitMs / 1000)} s` };
    await sleep(everyMs);
  }
}
