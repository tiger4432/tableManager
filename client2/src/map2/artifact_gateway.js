// ═══════════════════════════════════════════════════════════════════════════════
// THE ARTIFACT GATEWAY -- the Excel form, in and out.
//
// 🔴 STATUS: NAMED SEAM, NOT AN IMPLEMENTATION. The functions below throw `NOT_IMPLEMENTED`
//    on purpose. This file exists tonight so that the shape is fixed and the work has a home;
//    a named seam with no implementation is recoverable, an implementation with no seam is
//    not. Do not quietly fill these in from the legacy source -- see WHY NOT below.
//
// WHAT THIS IS. The Excel form is one of the means by which maps enter and leave the system,
// so Map Editor 2 is not doing its job without it. In the legacy editor this path is dozens of
// functions and hundreds of lines and it is the ONLY route by which a map arrives from
// outside.
//
// IT IS NOT A LAYER. It is a gatekeeper standing beside the stack: on the way IN it turns an
// external artifact into (a declaration + cells) and hands those to the pure layers; on the
// way OUT it turns a confirmed map back into the artifact. It must not be folded into the
// declaration layer (which knows nothing about files) nor into the view (which knows nothing
// about coordinates).
//
// 🔴 WHY NOT TO REIMPLEMENT IT BY READING THE LEGACY SOURCE. Copying that code copies its bugs
//    along with its behaviour, and afterwards there is no way to tell which is which. The
//    format is NOT ours to design: it is an artifact operators already use, so the job is to
//    MATCH it in both directions and PROVE the round trip. That makes it a contract job --
//    capture real forms as vectors under `contracts/`, and score both directions against them.
//    The existing legacy harnesses (`company_roundtrip_harness.mjs`, `coord_table_paste_harness.mjs`,
//    `copy_header_count_harness.mjs`) encode what the format actually is and are the best
//    available description of it.
//
// ⚠️ LANDMINE, LEAVE IT ALONE. `company_roundtrip_harness.mjs` asserts on literal CALL-NAME
//    STRINGS from the legacy file. Those assertions constrain the legacy file's text and
//    nothing here. Do not "fix" them to point at this module -- that harness dies with its
//    target, and re-pointing it would make a green harness that scores neither implementation.
//
// ASYMMETRY THAT SHAPES THE SURFACE: PASTE CAN PARTIALLY FAIL, EXPORT CANNOT. So the inbound
// function returns what arrived AND what was rejected with a reason, aggregated by reason so
// the screen can state one count instead of per-row noise. The outbound function either
// produces the artifact or throws.
//
// NO DOM. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE.
// ═══════════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════════
// 2026-08-05, map lane: THE SEAM IS FILLED. The format work lives in `./excel_io.js`
// (derived from `dev_env/ingestion_workspace/bonding_map/scripts/bonding_map_parser.py`
// -> `server/parsers/html_topology_parser.py`, which is the production code that already
// reads this form) and this file stays what it was written to be: the seam. It adapts, it
// does not parse.
//
// 🔴 FOUR CORRECTIONS TO THE CONTRACT ABOVE, STATED RATHER THAN SILENTLY CONFORMED TO. The
//    seam was written without seeing the format; these are what reading it changed.
//
//    ① `rows` HAD TO BECOME AN EXPLICIT FIELD. `accepted + rejectedTotal == rows` is the
//       right invariant, but with `rows` implicit the caller cannot check it -- it would
//       have to re-derive the artifact's row count, which means parsing the artifact a
//       second time with a second reader. It is returned.
//    ② A WHOLE-ARTIFACT REFUSAL IS NOT A PARTIAL READ. When the grid origin cannot be
//       established, the coordinates in the document are not merely unusable -- they are
//       unknowable, so there is no honest row count to attribute to a rejection reason.
//       Folding that into `rejected` would mean inventing a number. It is reported as
//       `refused` with the reason, and `rows === accepted === rejectedTotal === 0`.
//       The arithmetic then holds in every case instead of holding except when it matters.
//    ③ THE ROW UNIT IS A CELL, NOT A SPREADSHEET LINE. The ingestion pipeline flattens this
//       form to one record PER COORDINATE (`parse_matrix_to_records`), so a line of the
//       artifact is many rows. `rows` counts coordinates, which is the unit the operator's
//       "the file had 400 and 40 arrived" question is actually about.
//    ④ `writeArtifact` TAKES CELLS IN ABSOLUTE COORDINATES, NOT A SEATING. A seating is
//       screen space; this form addresses cells by DB x/y, and the axis ticks in the
//       artifact ARE those coordinates. Handing it a seating would require this file to
//       know the frame, which is exactly what "not a layer" forbids. It also cannot return
//       one string for both surfaces -- see `SURFACES` below -- so the caller picks.
//
//    Not corrected, deliberately: the four `REJECTED` tokens. The form produces one
//    condition the closed set has no word for -- the axes name a coordinate and the table
//    has no cell that answers to it (a ragged row). It is reported as `UNPARSABLE_CELL`
//    with the precision carried in the reason string rather than by widening a vocabulary
//    another lane owns.
// ═══════════════════════════════════════════════════════════════════════════════
import {
  readMapForm, writeMapForm, FORM_SURFACES, REJECTION_CODES,
} from './excel_io.js';

export const NOT_IMPLEMENTED = 'artifact_gateway_not_implemented';

/** The two surfaces of the one form. `rich` is the HTML table the ingestion pipeline reads;
 *  `plain` is the delimited projection that survives a clipboard. They are not variants of
 *  taste: the plain surface physically cannot carry the merged header band, so identity
 *  travels on `rich` only. */
export const SURFACES = FORM_SURFACES;

/** Rejection reasons are a closed set, so the aggregate line can name them in Korean. */
export const REJECTED = Object.freeze({
  OUT_OF_DECLARED_GRID: 'out_of_declared_grid',
  UNPARSABLE_CELL: 'unparsable_cell',
  DUPLICATE_COORD: 'duplicate_coord',
  NO_DECLARATION: 'no_declaration',
});

export const REJECTED_WORDS = Object.freeze({
  [REJECTED.OUT_OF_DECLARED_GRID]: '선언 격자 밖',
  [REJECTED.UNPARSABLE_CELL]: '읽을 수 없는 값',
  [REJECTED.DUPLICATE_COORD]: '좌표 중복',
  [REJECTED.NO_DECLARATION]: '선언 없음',
});

/**
 * INBOUND. Clipboard text or a parsed sheet => a declaration plus cells, plus an honest
 * account of what did not make it.
 *
 * CONTRACT (fixed now, implemented later):
 *   readArtifact(text, opts) -> {
 *     declaration: object|null,   // shaped for `client2/src/map/declaration.js`
 *     cells: [{x, y, value}],     // accepted rows only
 *     accepted: number,
 *     rejected: [{ reason, count }],   // aggregated by reason, never per-row noise
 *     rejectedTotal: number
 *   }
 * `accepted + rejectedTotal` must equal the number of data rows the artifact contained. A
 * gateway that silently drops rows is the same defect class as a renderer that silently drops
 * cells, and it must be measured the same way.
 */
export function readArtifact(text, opts) {
  const got = readMapForm(text, opts);
  if (!got.ok) {
    // ② A refusal, not a partial read. Nothing is attributed to a rejection reason because
    //    nothing about the artifact's coordinates is known.
    return Object.freeze({
      declaration: null, cells: Object.freeze([]),
      rows: 0, accepted: 0, rejected: Object.freeze([]), rejectedTotal: 0,
      refused: Object.freeze({ reason: REJECTED.NO_DECLARATION, detail: got.reason }),
    });
  }
  const rejected = got.intake.rejected.map(r => Object.freeze({
    reason: GATEWAY_REASON[r.code] || REJECTED.UNPARSABLE_CELL,
    count: r.count,
    detail: r.reason,
  }));
  const rejectedTotal = rejected.reduce((n, r) => n + r.count, 0);
  return Object.freeze({
    declaration: got.declaration,
    cells: got.cells,
    rows: got.intake.cellsRead,
    accepted: got.intake.cellsAccepted,
    rejected: Object.freeze(rejected),
    rejectedTotal,
    refused: null,
  });
}

/** `excel_io`'s honest-degradation codes -> this seam's closed set. Written out rather than
 *  guessed at the call site, so the one condition the set has no word for is visible. */
const GATEWAY_REASON = Object.freeze({
  not_declared: REJECTED.OUT_OF_DECLARED_GRID,
  mapping_unavailable: REJECTED.UNPARSABLE_CELL,
});

/** Every code `excel_io` can emit has a seam word. Exported so a harness can assert it
 *  instead of a reviewer having to notice a new code was added without one. */
export function unmappedRejectionCodes() {
  return REJECTION_CODES.filter(c => !GATEWAY_REASON[c]);
}

/**
 * OUTBOUND. A confirmed map => the artifact text, in the same form the operator already uses.
 *
 * CONTRACT: writeArtifact(seating, declaration, opts) -> string
 * Export cannot partially fail: it either produces the whole artifact or throws.
 */
export function writeArtifact(cells, declaration, opts) {
  const o = opts || {};
  const surface = o.surface || 'rich';
  if (SURFACES.indexOf(surface) < 0) throw new Error(`writeArtifact: unknown surface ${surface}`);
  const list = Array.isArray(cells) ? cells : (cells && Array.isArray(cells.cells) ? cells.cells : null);
  if (!list) throw new Error('writeArtifact: cells must be [{x, y, value}] in absolute coordinates');
  const out = writeMapForm(declaration, list, o);
  // Export cannot partially fail. The one thing it can fail to encode is the identity band
  // on a form too narrow to hold it, and that is a throw rather than a silent omission --
  // an artifact that lost its identity is indistinguishable from one that never had it.
  if (out.warnings.length && !o.allowDegraded) {
    throw new Error(`writeArtifact: ${out.warnings.join(', ')}`);
  }
  return surface === 'rich' ? out.html : out.text;
}

/** True once the gateway is more than a seam.
 *
 *  🔴 IT STAYS `false` UNTIL THE WIRING LANE FLIPS IT, AND THAT IS DELIBERATE. The two
 *     functions above are implemented and scored (`client2/tests/excel_form_roundtrip_harness.mjs`),
 *     but this flag does not report whether a module works -- it reports whether the SHELL
 *     may offer the affordance, and no control has been driven end to end yet. The map lane
 *     does not own that control, so it does not get to enable it. Flipping this is a
 *     one-line change for whoever scores the button. */
export function isImplemented() {
  return false;
}

/** One aggregate sentence for the screen, never one line per rejected row. */
export function rejectionSummary(rejected) {
  const list = Array.isArray(rejected) ? rejected.filter(r => r && r.count > 0) : [];
  if (list.length === 0) return '';
  return list
    .map(r => `${REJECTED_WORDS[r.reason] || r.reason} ${r.count}건`)
    .join(' · ');
}
