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
export function sourceRowHtml(sourceName, sourceVal, { isPinned, writable }) {
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
  // C-84. 쓸 수 없는 표(뷰)에서는 두 버튼을 «안 그린다». 그려 두고 누르면 400 이고, 회색으로
  // 그리는 것은 「눌러도 되는 것처럼 보이는 것」을 하나 더 만드는 일이다.
  // 🔴 `writable` 을 «안 주면» 안 그린다. 이 칸은 쓰기 컨트롤이라, 빠뜨린 호출자가 «권하는»
  //    쪽으로 기울면 안 된다 — 없는 버튼은 조용하고, 있는 버튼은 쓴다.
  const actions = writable
    ? `<button class="action-btn pin-btn ${isPinned ? 'active' : ''}" title="Pin this value">${isPinned ? '📌 Pinned' : '📍 Pin'}</button>
            <button class="action-btn del-btn" title="Delete this source">🗑️ Delete</button>`
    : '';
  return `
          <td>${escapeHtml(sourceName)}</td>
          <td><code ${titleAttr}>${displayVal !== null ? escapeHtml(String(displayVal)) : 'NULL'}</code></td>
          <td>${actions}</td>
        `;
}

/**
 * The selection's row: this source across many cells.
 * 🔴 The "how many distinct values" sentence is built HERE rather than passed in, so that the
 *    one place deciding what the operator reads is also the place that escapes it.
 *
 * 🔴 S-21. `cellCount` is HOW MANY CELLS WERE SELECTED, and it is the missing half of a
 *    fact this row could not state: a source present in 2 of 5 selected cells drew exactly
 *    like one present in all 5. 「그 소스는 여기 없다」 and 「그 소스는 없다」 were the same
 *    shape. `values` already carries one entry per cell THAT HAS THE SOURCE, so the
 *    comparison needs nothing new on the wire -- only the denominator, which the caller
 *    has been holding all along.
 * ⚠️ Optional on purpose: a caller that does not pass it renders EXACTLY as before. The
 *    single-cell row is a different function and is untouched.
 */
export function sourceRowAllHtml(sourceName, values, { isPinnedAll, cellCount, writable }) {
  const uniqueVals = Array.from(new Set(values || []));
  let valText = '';
  if (uniqueVals.length === 0) {
    valText = 'N/A';
  } else if (uniqueVals.length === 1) {
    valText = String(uniqueVals[0]);
  } else {
    valText = `Multiple Values (${uniqueVals.length} types)`;
  }
  // 🔴 S-21. Said ONLY when this source is missing from some of the selection. Covering
  //    every selected cell is the ordinary case and gets no note -- a mark on every row is
  //    noise, and noise is how the one row that matters stops being seen.
  // ⚠️ `values.length`, not `uniqueVals.length`: the question is HOW MANY CELLS, and two
  //    cells holding the same value are still two cells. Deduplicating here would report
  //    a source as missing from cells it actually covers.
  const covered = Array.isArray(values) ? values.length : 0;
  const selected = Number.isInteger(cellCount) ? cellCount : null;
  // 🔴 THE RATIO ALONE, NO ABSENCE WORD. 「없음」 beside a PRESENCE count reads as its
  //    numerator and inverts the sentence; the ratio cannot be read backwards because both
  //    numbers carry their unit. Reported to the lead as a wording call, not buried.
  if (selected !== null && covered > 0 && covered < selected) {
    valText = `${valText} · ${selected}칸 중 ${covered}칸`;
  }
  // C-84. 같은 규칙, 같은 이유 — 선택 여럿짜리 행도 뷰에서는 컨트롤을 안 그린다.
  const actions = writable
    ? `<button class="action-btn pin-btn ${isPinnedAll ? 'active' : ''}" title="Pin this source for all selected cells">${isPinnedAll ? '📌 Pinned' : '📍 Pin'}</button>
            <button class="action-btn del-btn" title="Delete this source from all selected cells">🗑️ Delete</button>`
    : '';
  return `
          <td>${escapeHtml(sourceName)}</td>
          <td><code>${escapeHtml(valText)}</code></td>
          <td>${actions}</td>
        `;
}
