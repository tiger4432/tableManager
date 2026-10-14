// IMAGE THUMB - an image value drawn in the place it is given (lead-board-14, owner 10-14 «썸네일은 주어진 칸에 딱 맞게
// 비율은 보존 · 한 칸에 이미지 여러 개 걸리면 슬라이드쇼»): fitted with its ratio kept; several - turned by hand (‹ › and
// «1/3» on a hover, a press, the wheel or the arrow keys, that place only, the first at the start, nothing saved); a place
// too small to show one asks for none - its mark (▣) or «1/3», the dwell preview (image_preview.js) showing it bigger.
// Every picture is asked through one loader a page, a few at once; a place out of view asks when it comes into view.
import { isBlank } from './absent.js';
import { imageRefUrl } from './image_preview.js';

/** Under this many pixels a place shows no picture and asks for none. */
export const THUMB_MIN_PX = 16;
/** A table's line with an image column (lead 10-15 ①: the table's line height one value). */
export const IMAGE_ROW_PX = 48;
/** A scatter point drawn as its image (Shape by), and a label drawn as one (Label by). */
export const IMAGE_MARKER_PX = 32;
export const LABEL_IMAGE_PX = 24;
/** The tooltip's picture. */
export const TIP_IMAGE_PX = 96;
/** Pictures asked at once - the rest wait their turn. */
export const LOADS_AT_ONCE = 4;
/** GET /api/image's `px` (implementer B 9b1de54a9): on - a thumbnail is asked at the size it is drawn; off - the original. */
export const SEND_PX = true;
/** Where an image cannot be drawn (Color by, a cross table's axes). */
export const IMAGES_REFUSED = 'Images draw in Shape by or Label by';
export const IMAGE_MARK = '▣';

/** A read's images - its one value, its several; none - []. */
export const imagesOf = (read) => (!read ? [] : read.state === 'one' ? [read.value] : read.state === 'several' ? read.values || [] : [])
  .filter((v) => !isBlank(v)).map(String);

/** Whether a place of `px` shows a picture. */
export const drawsImage = (px) => Number.isFinite(px) && px >= THUMB_MIN_PX;

/** «k/n» of a turn. */
export const turnWords = (k, n) => `${k + 1}/${n}`;

/** The page's one door to the pictures: each asked once, `atOnce` at a time, the rest in order; a picture asked again
 *  answers at once. `make` - the element that loads one (an Image). */
export class ImageLoader {
  constructor({ base = '', make = () => new Image(), atOnce = LOADS_AT_ONCE } = {}) {
    this.base = base;
    this.make = make;
    this.atOnce = atOnce;
    this.ready = new Set();
    this.waiting = [];
    this.out = new Map();
  }

  /** The address of a ref at a size (the size sent only when the server takes it). */
  url(ref, px = null) { return imageRefUrl(this.base, ref, SEND_PX ? px : null); }

  /** Whether the picture of `url` is here. */
  has(url) { return this.ready.has(url); }

  /** Ask for `url`; `done(ok)` when it came (or failed). */
  want(url, done = () => {}) {
    if (this.ready.has(url)) { done(true); return; }
    if (this.out.has(url)) { this.out.get(url).push(done); return; }
    const queued = this.waiting.find((w) => w.url === url);
    if (queued) { queued.done.push(done); return; }
    this.waiting.push({ url, done: [done] });
    this.next();
  }

  next() {
    while (this.out.size < this.atOnce && this.waiting.length) {
      const { url, done } = this.waiting.shift();
      this.out.set(url, done);
      const img = this.make();
      const end = (ok) => {
        img.onload = null;
        img.onerror = null;
        const all = this.out.get(url) || [];
        this.out.delete(url);
        if (ok) this.ready.add(url);
        for (const d of all) d(ok);
        this.next();
      };
      img.onload = () => end(true);
      img.onerror = () => end(false);
      img.src = url;
    }
  }
}

/**
 * A place's picture: `refs` the images it holds, `px` the size it is drawn at (the smaller side). Its own mount; the
 * page's loader and the part's preview (image_preview.js ImagePreview) handed in.
 */
export class Thumb {
  constructor(mount, { doc, loader, preview = null, at = 0, onTurn = null }) {
    this.mount = mount;
    this.doc = doc || mount.ownerDocument;
    this.loader = loader;
    this.preview = preview;
    this.k = at;
    this.onTurn = onTurn;
    this.refs = [];
    this.px = 0;
    this.seen = false;
    this.hovered = false;
    this.key = (event) => {
      if (!this.hovered || this.refs.length < 2) return;
      if (event.key === 'ArrowRight') { event.preventDefault(); this.turn(1); }
      if (event.key === 'ArrowLeft') { event.preventDefault(); this.turn(-1); }
    };
  }

  show(refs, px) {
    const doc = this.doc;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    this.refs = refs;
    this.px = px;
    if (this.k >= refs.length) this.k = 0;
    const box = el('span', `sf-thumb${refs.length > 1 ? ' sf-thumb--many' : ''}${drawsImage(px) ? '' : ' sf-thumb--small'}`);
    this.box = box;
    this.mount.replaceChildren(box);
    if (!refs.length) return this;
    this.img = null;
    if (drawsImage(px)) {
      this.img = el('img', 'sf-thumb__img');
      this.img.setAttribute('alt', '');
    }
    this.count = el('span', 'sf-thumb__n', refs.length > 1 ? turnWords(this.k, refs.length) : (this.img ? '' : IMAGE_MARK));
    const nav = (words, d) => {
      const b = el('button', 'sf-thumb__nav', words);
      b.type = 'button';
      // a press on ‹ › turns, it marks nothing
      b.addEventListener('mousedown', (event) => { event.preventDefault(); event.stopPropagation(); });
      b.addEventListener('click', (event) => { event.preventDefault(); event.stopPropagation(); this.turn(d); });
      return b;
    };
    const turnable = refs.length > 1 && this.img;
    box.append(...(turnable ? [nav('‹', -1)] : []), ...(this.img ? [this.img] : []), this.count, ...(turnable ? [nav('›', 1)] : []));
    box.addEventListener('wheel', (event) => {
      if (this.refs.length < 2) return;
      event.preventDefault();
      this.turn(event.deltaY > 0 ? 1 : -1);
    });
    box.addEventListener('mouseenter', () => {
      this.hovered = true;
      if (this.doc.addEventListener) this.doc.addEventListener('keydown', this.key);
      if (this.preview) this.preview.hover(box, this.refs[this.k]);
    });
    box.addEventListener('mouseleave', () => {
      this.hovered = false;
      if (this.doc.removeEventListener) this.doc.removeEventListener('keydown', this.key);
      if (this.preview) this.preview.leave(box);
    });
    this.watch();
    return this;
  }

  /** Ask once it is in view (the window's IntersectionObserver), at once with none. */
  watch() {
    if (!this.img) return;
    const view = this.doc.defaultView;
    const Observer = view && view.IntersectionObserver;
    if (!Observer) { this.seen = true; this.paint(); return; }
    const watcher = new Observer((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      watcher.disconnect();
      this.seen = true;
      this.paint();
    });
    watcher.observe(this.box);
  }

  paint() {
    if (this.count && this.refs.length > 1) this.count.textContent = turnWords(this.k, this.refs.length);
    if (!this.img || !this.seen) return;
    const img = this.img;
    const url = this.loader.url(this.refs[this.k], this.px);
    this.loader.want(url, (ok) => { if (this.img === img && this.loader.url(this.refs[this.k], this.px) === url) img.setAttribute('src', ok ? url : ''); });
  }

  turn(d) {
    const n = this.refs.length;
    if (n < 2) return;
    this.k = (this.k + d + n) % n;
    this.paint();
    if (this.preview && this.hovered) this.preview.hover(this.box, this.refs[this.k]);
    if (this.onTurn) this.onTurn(this.k);
  }
}
