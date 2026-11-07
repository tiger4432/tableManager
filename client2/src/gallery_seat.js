// The gallery seated on the main grid's page (lead 77ffe5cb6): «Gallery» beside the View control turns the grid's place
// into the gallery and back; the gallery reads the grid's rows and draws again whenever the grid's rows change.
import { GalleryPart, WORDS } from './gallery.js';
import { ImageLoader } from './image_thumb.js';
import { IMAGE_TYPE } from './grid_image_column.js';
import { appendNextRows, gridRowsInOrder, holdsWholeTable, isSystemColumn, showGridRow } from './grid.js';
import { state, visibleRangeColIds } from './state.js';
import './gallery.css';

export function seatGallery({ doc = document, base = '', storage = null, loadAll = () => {} } = {}) {
  const grid = doc.getElementById('myGrid');
  const host = doc.getElementById('gallery-host');
  const toggle = doc.getElementById('gallery-toggle-btn');
  const counted = doc.getElementById('total-rows');
  if (!grid || !host || !toggle) return null;
  let open = false;
  const columns = () => (state.currentColumns || []).map((name) => ({ name, type: (state.currentColumnTypes || {})[name] || null }));
  const hasImage = () => columns().some((c) => c.type === IMAGE_TYPE);
  const part = new GalleryPart(host, {
    doc, base, storage, loader: new ImageLoader({ base }),
    table: () => state.currentTable || '', columns, rows: gridRowsInOrder,
    // the grid's own answers: the columns it shows, less its system ones (owner 10-20 ⑤)
    shown: () => visibleRangeColIds().filter((name) => !isSystemColumn(name) && columns().some((c) => c.name === name)),
    valueOf: (row, column) => row.cell(column),
    count: () => (counted && counted.matchCount) || null, whole: holdsWholeTable,
    // the grid's own next step: a page added while scrolling, Load All while paging
    loadMore: () => { if (state.viewMode !== 'infinite' || !appendNextRows()) loadAll(); },
    showRow: (id) => { show(false); requestAnimationFrame(() => showGridRow(id)); },
  });
  const show = (on) => {
    open = on && hasImage();
    grid.style.display = open ? 'none' : '';
    host.hidden = !open;
    toggle.textContent = open ? WORDS.grid : WORDS.gallery;
    toggle.classList.toggle('is-on', open);
    if (open) part.render();
  };
  toggle.addEventListener('click', () => show(!open));
  // the grid's rows changed (a filter, a sort, a page, another table): the button only where there is an image column
  let attached = false;
  const attach = () => {
    if (attached || !state.gridApi) return;
    attached = true;
    state.gridApi.addEventListener('modelUpdated', () => {
      toggle.hidden = !hasImage();
      if (open && !hasImage()) show(false);
      else if (open) part.render();
    });
    toggle.hidden = !hasImage();
  };
  const wait = setInterval(() => { attach(); if (attached) clearInterval(wait); }, 300);
  return { part, show };
}
