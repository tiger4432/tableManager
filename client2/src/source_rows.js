// C-14 tranche 3. The two source-list rows in `main.js`, which print WHERE A VALUE CAME FROM.
//
// 🔴 WHY A MODULE. `main.js` imports ag-grid's CSS, so node cannot import it and the gate for
//    these two would have to read the file as text — banned, and it would score the shape of the
//    letters rather than what reaches the DOM. The standing rule is to lift the logic being
//    measured into a module a harness can `import`, and that is what this is.
// 🔴 AND WHY *TOGETHER*. Both rows render THE SAME FACTS — a source name and the value that
//    source holds — for one cell and for a selection. They were two hand-written templates, so
//    the escaping decision would have had two authors and could diverge without erroring, which
//    is criterion ④ and is exactly the defect this whole sweep started from.
//
// ⚠️ `titleAttr` IS BUILT IN HERE FOR THE SAME REASON THE ADMIN BADGES WERE. It carries
//    `updated_by` — a name the server supplies and the client cannot vet — and it lands INSIDE
//    an attribute, which is the position where the drift found in tranche one (a copy that left
//    quotes alone) was unsafe while looking correct.
//
// ⚠️ WHAT IS DELIBERATELY *NOT* CHANGED: `String(displayVal)` keeps the existing output when a
//    source holds `undefined` — today that prints the word "undefined", and escaping it away to
//    an empty string would be a silent behaviour change smuggled into an escaping round. It is
//    reported, not fixed here.
import { escapeHtml } from './utils.js';

/** One cell's row: this source, the value it holds, and whether it is pinned. */
export function sourceRowHtml(sourceName, sourceVal, { isPinned }) {
  let displayVal = sourceVal;
  let titleAttr = '';
  if (sourceVal && typeof sourceVal === 'object') {
    displayVal = sourceVal.value !== undefined ? sourceVal.value : '';
    if (sourceVal.timestamp || sourceVal.updated_by) {
      const timeStr = sourceVal.timestamp ? new Date(sourceVal.timestamp).toLocaleString() : 'N/A';
      const userStr = sourceVal.updated_by || 'system';
      titleAttr = `title="Updated by ${escapeHtml(userStr)} at ${escapeHtml(timeStr)}"`;
    }
  }
  return `
          <td>${escapeHtml(sourceName)}</td>
          <td><code ${titleAttr}>${displayVal !== null ? escapeHtml(String(displayVal)) : 'NULL'}</code></td>
          <td>
            <button class="action-btn pin-btn ${isPinned ? 'active' : ''}" title="Pin this value">${isPinned ? '📌 Pinned' : '📍 Pin'}</button>
            <button class="action-btn del-btn" title="Delete this source">🗑️ Delete</button>
          </td>
        `;
}

/**
 * The selection's row: this source across many cells.
 * 🔴 The "how many distinct values" sentence is built HERE rather than passed in, so that the
 *    one place deciding what the operator reads is also the place that escapes it.
 */
export function sourceRowAllHtml(sourceName, values, { isPinnedAll }) {
  const uniqueVals = Array.from(new Set(values || []));
  let valText = '';
  if (uniqueVals.length === 0) {
    valText = 'N/A';
  } else if (uniqueVals.length === 1) {
    valText = String(uniqueVals[0]);
  } else {
    valText = `Multiple Values (${uniqueVals.length} types)`;
  }
  return `
          <td>${escapeHtml(sourceName)}</td>
          <td><code>${escapeHtml(valText)}</code></td>
          <td>
            <button class="action-btn pin-btn ${isPinnedAll ? 'active' : ''}" title="Pin this source for all selected cells">${isPinnedAll ? '📌 Pinned' : '📍 Pin'}</button>
            <button class="action-btn del-btn" title="Delete this source from all selected cells">🗑️ Delete</button>
          </td>
        `;
}
