// THE NARROWING SET — what the grid screen is currently showing, as query parameters.
//
// `transaction_id` · `q` · `cols` · `filters`. Four call sites built these by hand and the
// audit recorded two of them; the third and fourth were `main.js`, and one of THOSE is the
// EXPORT url. So a divergence here would not split "the rows on screen" from "the count in
// the footer" — it would split what the operator SAW from what is inside the file they
// downloaded, silently.
//
// 🔴 IT DELIBERATELY DOES NOT CARRY `order_by` / `order_desc`. Three of the four callers need
//    them and the count route must not have them, so folding order in would be making four
//    call sites into one SHAPE rather than removing the duplication. The order stays with the
//    caller; what is shared is the narrowing, which is the part that was actually repeated.
//
// 🔴 NO DOM AND NO MODULE STATE. The three inputs arrive as arguments, so a harness scores
//    this by importing it — `main.js` imports four stylesheets at module scope and cannot be
//    imported in node at all, which is why the test could not have come first.
//
// ⚠️ ENCODING. `URLSearchParams` writes a space as `+` where the hand-built strings used
//    `encodeURIComponent`'s `%20`. Both are valid in a query string and the server decodes
//    both — and `narrowingParams` already shipped `+` on the count route against the same
//    parser, so this is the spelling that was already in production, now used by all four.

/**
 * @param {{globalSearch?: {value: string}, searchCols?: {value: string},
 *          gridApi?: {getFilterModel: () => object}, transactionId?: string|null}} src
 * @returns {URLSearchParams} empty when nothing is narrowed
 */
export function narrowingParams(src = {}) {
  const params = new URLSearchParams();
  const q = src.globalSearch ? String(src.globalSearch.value || '').trim() : '';
  const cols = src.searchCols ? String(src.searchCols.value || '') : '';
  const filterModel = src.gridApi ? (src.gridApi.getFilterModel() || {}) : {};
  if (src.transactionId) params.set('transaction_id', src.transactionId);
  // `cols` only means something ALONGSIDE a search term — it names which columns the term
  // applies to. Sending it on its own would ask the server to narrow by nothing in
  // particular, and all four sites already agreed on that.
  if (q) {
    params.set('q', q);
    if (cols) params.set('cols', cols);
  }
  if (Object.keys(filterModel).length > 0) params.set('filters', JSON.stringify(filterModel));
  return params;
}

/** The same thing as a tail to append to a url that already has a `?` and one parameter. */
export function narrowingTail(src = {}) {
  const s = narrowingParams(src).toString();
  return s ? `&${s}` : '';
}
