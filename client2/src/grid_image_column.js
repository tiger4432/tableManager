// The main grid's typed cells. Image (lead 191912ce2): the value as written, a mark that opens the picture in a new
// window, and the cell's dwell handed to the grid's one ImagePreview (`context.imagePreview`).
// The cell itself still selects and edits as every other cell does; only the mark opens.
// Link (owner 11-04): the value as written is the link, opened in a new tab; the cell around it selects and edits.
import { isBlank } from './absent.js';
import { OPEN_IMAGE } from './image_preview.js';

/** The column type words (table_config `column_types`, server a8dea2bcf · link B 11-04). */
export const IMAGE_TYPE = 'image';
export const LINK_TYPE = 'link';
export const IMAGE_MARK = '▣';

/** What a column of `type` adds to its definition - the one place the grid asks how a type is drawn. */
export function columnTypeParts(type) {
  if (type === IMAGE_TYPE) return { cellRenderer: ImageCellRenderer };
  if (type === LINK_TYPE) return { cellRenderer: LinkCellRenderer };
  return {};
}

/** The address a link cell opens, as the browser's own parser reads it: an http(s) address, or a value starting
 *  with «/» that lands on our own origin. Anything else - javascript:, a file path written before the type, «//host»,
 *  «/\host», a tab or newline the browser drops - is null and is drawn as text (lead 11-04, a guard that keeps data). */
export function linkHref(value, origin = globalThis.location && globalThis.location.origin) {
  if (isBlank(value) || !origin) return null;
  const text = String(value);
  let url;
  try { url = new URL(text, origin); } catch { return null; }
  if (/^https?:\/\//i.test(text)) return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  return text.startsWith('/') && url.origin === origin ? url.href : null;
}

// A picture pasted or dropped on image cells (owner 11-05 ㄱ): the server keeps it, and its reference is written to
// the cells as a pasted value would be.
export const IMAGES_ONLY = 'Images paste into image columns only';
export const ONE_IMAGE = 'One image per paste';
export const NOT_SENT = 'Not sent to the server · check the network';
export const isImageFile = (type) => /^image\//i.test(String(type || ''));

/** A paste's picture, or why not: null when the paste is text as today. Only when there is no text - Excel puts a
 *  picture of the copied cells beside any cell's text (measured in Chrome 11-05), so that picture is not what is pasted. */
export function pastedImage(text, files, types) {
  if (!isBlank(text)) return null;
  const list = Array.from(files || []);
  const images = list.filter((f) => isImageFile(f && f.type));
  if (!images.length) return null;
  if (!types.length || !types.every((t) => t === IMAGE_TYPE)) return { refused: IMAGES_ONLY };
  if (images.length > 1 || list.length > 1) return { refused: ONE_IMAGE };
  return { file: images[0] };
}

/** The image cell under a point - a drop's target: the topmost grid cell among `elements` (document.elementsFromPoint),
 *  when its column is declared image. */
export function imageCellIn(elements, types) {
  const cell = Array.from(elements || []).find((el) => el && el.classList && el.classList.contains('ag-cell'));
  if (!cell || (types || {})[cell.getAttribute('col-id')] !== IMAGE_TYPE) return null;
  const row = cell.closest ? cell.closest('.ag-row') : null;
  const rowIndex = row ? Number(row.getAttribute('row-index')) : NaN;
  return Number.isInteger(rowIndex) ? { el: cell, colId: cell.getAttribute('col-id'), rowIndex } : null;
}

/** POST /tables/{table}/images?column= (server c2b6b8e9b): {ref} or {refused: the server's sentence}. */
export async function uploadImage(base, table, column, file, send = (...args) => fetch(...args)) {
  const body = new FormData();
  body.append('file', file, file.name || 'image');
  let res;
  try {
    res = await send(`${base}/tables/${encodeURIComponent(table)}/images?column=${encodeURIComponent(column)}`,
      { method: 'POST', body });
  } catch {
    return { refused: NOT_SENT };
  }
  const answer = await res.json().catch(() => ({}));
  if (res.ok && typeof answer.ref === 'string' && answer.ref) return { ref: answer.ref };
  return { refused: typeof answer.detail === 'string' && answer.detail ? answer.detail : `Image not saved (HTTP ${res.status})` };
}

export class ImageCellRenderer {
  init(params) {
    const doc = (params.eGridCell && params.eGridCell.ownerDocument) || document;
    this.preview = (params.context && params.context.imagePreview) || null;
    this.gui = doc.createElement('span');
    this.gui.className = 'cell-image';
    this.mark = doc.createElement('button');
    this.mark.className = 'cell-image-open';
    this.mark.setAttribute('type', 'button');
    this.mark.setAttribute('title', OPEN_IMAGE);
    this.mark.setAttribute('aria-label', OPEN_IMAGE);
    this.mark.textContent = IMAGE_MARK;
    this.text = doc.createElement('span');
    this.text.className = 'cell-image-ref';
    this.gui.appendChild(this.mark);
    this.gui.appendChild(this.text);
    this.gui.addEventListener('mouseenter', () => { if (this.preview) this.preview.hover(this.gui, this.value); });
    this.gui.addEventListener('mouseleave', () => { if (this.preview) this.preview.leave(this.gui); });
    // A press on the mark is not a press on the cell: the grid starts its range drag from the pointer
    // press and selects from the focus the button would take - neither reaches it.
    this.mark.addEventListener('pointerdown', (e) => e.stopPropagation());
    this.mark.addEventListener('mousedown', (e) => { e.preventDefault(); e.stopPropagation(); });
    this.mark.addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.preview) this.preview.open(this.value);
    });
    this._set(params.value);
  }

  _set(value) {
    this.value = value;
    const blank = isBlank(value);
    this.mark.style.display = blank ? 'none' : '';
    this.text.textContent = blank ? '' : String(value);
  }

  getGui() { return this.gui; }

  refresh(params) {
    if (params.value !== this.value && this.preview) this.preview.leave(this.gui);
    this._set(params.value);
    return true;
  }

  destroy() {
    if (this.preview) this.preview.leave(this.gui);
  }
}

export class LinkCellRenderer {
  init(params) {
    const doc = (params.eGridCell && params.eGridCell.ownerDocument) || document;
    this.gui = doc.createElement('span');
    this.gui.className = 'cell-link';
    this.link = doc.createElement('a');
    this.link.className = 'cell-link-open';
    this.link.setAttribute('target', '_blank');
    this.link.setAttribute('rel', 'noopener');
    this.text = doc.createElement('span');
    this.text.className = 'cell-link-text';
    this.gui.appendChild(this.link);
    this.gui.appendChild(this.text);
    // A press on the link is not a press on the cell - the image mark's rule: no range drag, no focus taken.
    this.link.addEventListener('pointerdown', (e) => e.stopPropagation());
    this.link.addEventListener('mousedown', (e) => { e.preventDefault(); e.stopPropagation(); });
    this.link.addEventListener('click', (e) => e.stopPropagation());
    this._set(params.value);
  }

  _set(value) {
    this.value = value;
    const href = linkHref(value);
    const shown = isBlank(value) ? '' : String(value);
    if (href) this.link.setAttribute('href', href); else this.link.removeAttribute('href');
    this.link.textContent = href ? shown : '';
    this.link.style.display = href ? '' : 'none';
    this.text.textContent = href ? '' : shown;
  }

  getGui() { return this.gui; }

  refresh(params) {
    this._set(params.value);
    return true;
  }
}
