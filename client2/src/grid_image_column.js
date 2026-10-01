// The main grid's image cell (lead 191912ce2): the value as written, a mark that opens the picture in a new
// window, and the cell's dwell handed to the grid's one ImagePreview (`context.imagePreview`).
// The cell itself still selects and edits as every other cell does; only the mark opens.
import { isBlank } from './absent.js';
import { OPEN_IMAGE } from './image_preview.js';

/** The column type word (table_config `column_types`, server a8dea2bcf). */
export const IMAGE_TYPE = 'image';
export const IMAGE_MARK = '▣';

/** What a column of `type` adds to its definition - the one place the grid asks whether it is an image. */
export function imageColumnParts(type) {
  return type === IMAGE_TYPE ? { cellRenderer: ImageCellRenderer } : {};
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
