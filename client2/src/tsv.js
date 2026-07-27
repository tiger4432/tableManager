// ── TSV: text ⇄ string grid. THE ONLY implementation in this codebase. ────────────
//
// Extracted from clipboard.js, where the parse was four lines inline inside the `paste`
// event handler, interleaved with `state.gridApi` / `state.selectedCellsMap`. That is why
// it could not be reused: the code was not tangled conceptually, it was tangled
// POSITIONALLY. Pulling it out is the whole fix - both callers now run the same reader.
//
// WHY THIS IS PURE. No DOM, no module state, no clipboard API. The DOE panel and the grid
// need the same text format and nothing else in common: the grid pastes into a 2D range,
// the panel pastes into a list of rows with named columns. Sharing the RANGE logic would
// have forced one of them into the other's shape; sharing the TEXT logic costs nothing.
//
// ⚠️ `navigator.clipboard` is undefined in production. The intranet is plain HTTP, which
//    is a non-secure context, so the async Clipboard API simply is not there. Everything
//    goes through `e.clipboardData` on the native copy/paste event. This module never
//    touches either - it takes a string and returns a string, which is exactly why it can
//    be tested without a browser.
//
// ── EXCEL'S QUOTING RULES, which the previous inline parser did not have ──────────
//
// Excel emits `"..."` around any cell containing a tab, a newline or a quote, and doubles
// interior quotes. A `split('\n')` on that text breaks ONE cell into TWO rows the moment a
// cell holds two lines - which is precisely the shape of a MID cell with two materials:
//
//     #2f7d63⇥B⇥16⇥라이너⇥ADFE1H_01⇥"MID1↵MID3"⇥TOP1
//
// Under the old reader that became two records, the second of which (`MID3"⇥TOP1`) is
// garbage that would have been pasted into the next value's row. The parser below is a
// character scanner, so the newline inside the quotes is just a character.
//
// A quote only opens a quoted field when it is the FIRST character of that field: `a"b` is
// the three characters a, ", b, exactly as Excel reads it. Anything after a closing quote
// but before the delimiter is appended literally rather than refused - clipboard text from
// other tools is not always well-formed, and refusing a paste is the one outcome this
// screen is not allowed to produce.

const QUOTE = '"';
const TAB = '\t';

// Rows are split on \n; \r\n and a lone \r are normalized first so a file that travelled
// through Windows, a mail client and Excel still reads as one record per line.
function normalizeNewlines(text) {
  return String(text === null || text === undefined ? '' : text).replace(/\r\n?/g, '\n');
}

/**
 * TSV text -> string[][]. Never throws, never returns null: unparseable input degrades to
 * literal text rather than to an error, because the caller's alternative is refusing a
 * paste the user already committed to.
 *
 * opts.trimCells       - trim each field AFTER unquoting (grid behaviour; default false).
 *                        Applied after unquoting so `"  a  "` keeps its spaces only when
 *                        the caller asked for no trimming at all.
 * opts.dropBlankLines  - drop records that are a single empty field (the grid's old
 *                        `.filter(r => r.length > 0)`; default false).
 *
 * A single trailing newline never produces a phantom empty record - that one is always
 * dropped, for every caller. Excel always ends its clipboard block with one.
 */
function parseTsv(text, opts) {
  const o = opts || {};
  const src = normalizeNewlines(text);
  const rows = [];
  let row = [];
  let field = '';
  let i = 0;
  let quoted = false;      // we are inside a quoted field
  let fieldStart = true;   // no character of the current field has been consumed yet

  const endField = () => { row.push(o.trimCells ? field.trim() : field); field = ''; fieldStart = true; quoted = false; };
  const endRow = () => { endField(); rows.push(row); row = []; };

  while (i < src.length) {
    const c = src[i];
    if (quoted) {
      if (c === QUOTE) {
        if (src[i + 1] === QUOTE) { field += QUOTE; i += 2; continue; }   // "" -> literal "
        quoted = false; i++; continue;                                    // closing quote
      }
      field += c; i++; continue;                                          // tabs/newlines are data
    }
    if (c === QUOTE && fieldStart) { quoted = true; fieldStart = false; i++; continue; }
    if (c === TAB) { endField(); i++; continue; }
    if (c === '\n') { endRow(); i++; continue; }
    field += c; fieldStart = false; i++;
  }
  // The tail. `src.length === 0` must yield no rows at all, not one empty row - an empty
  // clipboard is "nothing was pasted", and a phantom row would blank a value's fields.
  if (src.length > 0) endRow();

  // Excel's trailing newline. Drop exactly one empty record at the end, never more: two
  // blank lines in the middle of a block are the user's data and get to survive.
  if (rows.length > 0) {
    const last = rows[rows.length - 1];
    if (last.length === 1 && last[0] === '') rows.pop();
  }
  if (o.dropBlankLines) return rows.filter(r => !(r.length === 1 && r[0] === ''));
  return rows;
}

// A field needs quoting iff it carries a delimiter or a quote. Note what this REPLACES in
// clipboard.js: `String(val).replace(/\t/g,' ').replace(/\n/g,' ')`, which destroyed the
// characters instead of escaping them. That is silent data loss on copy, and it is the
// reason a copied cell could never be pasted back to produce the same cell.
function needsQuote(s) {
  return s.indexOf(TAB) >= 0 || s.indexOf('\n') >= 0 || s.indexOf('\r') >= 0 || s.indexOf(QUOTE) >= 0;
}

function quoteField(v) {
  const s = String(v === null || v === undefined ? '' : v);
  return needsQuote(s) ? QUOTE + s.split(QUOTE).join(QUOTE + QUOTE) + QUOTE : s;
}

/** string[][] -> TSV text. `parseTsv(serializeTsv(g))` must equal `g` for every grid. */
function serializeTsv(grid) {
  return (Array.isArray(grid) ? grid : [])
    .map(row => (Array.isArray(row) ? row : []).map(quoteField).join(TAB))
    .join('\n');
}

export { parseTsv, serializeTsv, quoteField };
