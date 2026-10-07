// IMAGE PREVIEW — an image cell's picture on a dwell, one at a time, nothing fetched ahead (lead 191912ce2,
// owner 10-01 「이미지 일단 메인그리드 해봐 서버 부하 크지 않게」).
//
// 🔴 THE PICTURE LOADS THROUGH AN <img>. One request on success, cached by the browser under the server's
//    Cache-Control - this part keeps no cache of its own. GET /api/image brokers every source itself (lead
//    f087403fe, owner 「그래야함」), so a picture always comes from our server and a refusal is always its
//    sentence: only a failed <img> costs a second request, one fetch that reads that sentence.
import { isBlank } from './absent.js';

/** How long the pointer rests on a cell before its picture is asked for. Passing over asks nothing. */
export const DWELL_MS = 450;
export const IMAGE_ROUTE = '/api/image';
export const OPEN_IMAGE = 'Open image';
export const LOADING = 'Loading';
/** The token that caps the preview box, read once per show (tokens.css). */
export const SIZE_TOKEN = '--image-preview-max';
export const EDGE_TOKEN = '--space-2';

/**
 * Where a floating box (position: fixed) stands beside `rect`: under it, above it when the window has no room below,
 * kept `edge` inside the window (`view`: width, height). One placement - the image preview and the declaration
 * screen's annotations both stand here (lead dee90e340).
 */
export function placeBeside(rect, width, height, view, edge) {
  const left = Math.max(edge, Math.min(rect.left, view.width - width - edge));
  let top = rect.bottom + edge;
  if (top + height > view.height - edge) top = rect.top - edge - height;
  top = Math.max(edge, Math.min(top, view.height - height - edge));
  return { left, top };
}

/** The one address of a ref, for the preview and the new window alike. The value goes as written. */
export function imageRefUrl(base, ref) {
  return `${base || ''}${IMAGE_ROUTE}?ref=${encodeURIComponent(String(ref))}`;
}

/** What the screen says when the picture did not come, from the one extra request. */
export function whyLines(answer) {
  if (answer.unreached) return ['Server not reached', 'Next: check the connection, then hover again'];
  if (answer.status >= 400) {
    const next = answer.status >= 500 ? 'Next: check this source in image_sources.json'
      : 'Next: correct the value in this cell';
    return [`${answer.status} · ${answer.detail || 'Refused'}`, next];
  }
  return ['Not a picture the browser can draw', 'Next: open it to see what came back'];
}

async function detailOf(res) {
  try {
    const body = await res.json();
    const d = body && body.detail;
    return typeof d === 'string' ? d : (d == null ? '' : JSON.stringify(d));
  } catch (e) {
    return '';
  }
}

/** The px value of a length token on the document's root, or NaN. */
function tokenPx(doc, name) {
  const view = doc && doc.defaultView;
  if (!view || !view.getComputedStyle) return NaN;
  return parseFloat(view.getComputedStyle(doc.documentElement).getPropertyValue(name));
}

export class ImagePreview {
  /**
   * @param {HTMLElement} mount  this part's own div; it holds the one box and nothing else
   * @param {{doc?, base?, setTimeout?, clearTimeout?, fetch?, open?, viewport?, sizePx?, edgePx?}} deps
   */
  constructor(mount, deps = {}) {
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    this.base = deps.base || '';
    this.later = deps.setTimeout || ((fn, ms) => setTimeout(fn, ms));
    this.cancel = deps.clearTimeout || ((t) => clearTimeout(t));
    this.fetch = deps.fetch || ((url, init) => fetch(url, init));
    this.openWindow = deps.open || ((url, target, features) => window.open(url, target, features));
    this.viewport = deps.viewport || (() => ({ width: window.innerWidth, height: window.innerHeight }));
    this.sizePx = deps.sizePx || (() => tokenPx(this.doc, SIZE_TOKEN));
    this.edgePx = deps.edgePx || (() => tokenPx(this.doc, EDGE_TOKEN));
    this.anchor = null;
    this.ref = null;
    this.timer = null;
    this.box = null;
    this.img = null;
    this.abort = null;
  }

  /** The pointer rests on `anchor`, a cell whose value is `ref`: ask after the dwell, unless it leaves. */
  hover(anchor, ref) {
    if (anchor === this.anchor && ref === this.ref) return;
    this.drop();
    if (isBlank(ref)) return;
    this.anchor = anchor;
    this.ref = ref;
    this.timer = this.later(() => { this.timer = null; this._show(); }, DWELL_MS);
  }

  /** The pointer left `anchor` (or, with no argument, anything): its timer, request and box go. */
  leave(anchor) {
    if (anchor === undefined || anchor === this.anchor) this.drop();
  }

  open(ref) {
    if (!isBlank(ref)) this.openWindow(imageRefUrl(this.base, ref), '_blank', 'noopener');
  }

  drop() {
    if (this.timer !== null) { this.cancel(this.timer); this.timer = null; }
    if (this.abort) { this.abort.abort(); this.abort = null; }
    if (this.img) {
      this.img.onload = null;
      this.img.onerror = null;
      this.img.removeAttribute('src');
      this.img = null;
    }
    if (this.box) { this.mount.textContent = ''; this.box = null; }
    this.anchor = null;
    this.ref = null;
  }

  _show() {
    const doc = this.doc;
    const url = imageRefUrl(this.base, this.ref);
    const box = doc.createElement('div');
    box.className = 'image-preview';
    const img = doc.createElement('img');
    img.className = 'image-preview-img';
    img.setAttribute('alt', '');
    const why = doc.createElement('div');
    why.className = 'image-preview-why';
    why.textContent = LOADING;
    box.appendChild(img);
    box.appendChild(why);
    this.mount.textContent = '';
    this.mount.appendChild(box);
    this.box = box;
    this.img = img;
    this._place(box);
    img.onload = () => { if (this.img === img) { why.textContent = ''; this._place(box); } };
    img.onerror = () => { if (this.img === img) this._explain(url, img, box, why); };
    img.setAttribute('src', url);
  }

  /** Beside the cell, inside the window, by the box's own size once it has one (the token's cap until then).
   *  Placed again when the picture or the reason arrives. */
  _place(box) {
    const view = this.viewport();
    const edge = Number.isFinite(this.edgePx()) ? this.edgePx() : 0;
    const cap = Number.isFinite(this.sizePx()) ? this.sizePx() : Math.min(view.width, view.height) / 2;
    const w = Math.min(box.offsetWidth || cap, cap);
    const h = Math.min(box.offsetHeight || cap, cap);
    const r = this.anchor && this.anchor.getBoundingClientRect
      ? this.anchor.getBoundingClientRect() : { left: edge, top: edge, bottom: edge };
    const { left, top } = placeBeside(r, w, h, view, edge);
    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
  }

  async _explain(url, img, box, why) {
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    this.abort = ctl;
    let answer;
    try {
      const res = await this.fetch(url, { signal: ctl ? ctl.signal : undefined });
      answer = { status: res.status, detail: res.ok ? '' : await detailOf(res) };
    } catch (e) {
      answer = { unreached: true };
    }
    if (this.img !== img) return;
    this.abort = null;
    box.classList.add('is-refused');
    why.textContent = '';
    for (const line of whyLines(answer)) {
      const row = this.doc.createElement('div');
      row.textContent = line;
      why.appendChild(row);
    }
    this._place(box);
  }
}
