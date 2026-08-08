// ═══════════════════════════════════════════════════════════════════════════════
// THE CANDIDATE SET -- the 8 orientations, named once.
//
// (MAP_ALIGNMENT_SPEC 0.2 layer 5; R2_ui_operator_loop.md section 3.)
//
// WHY EIGHT AND NOT SIXTEEN. 4 turns x 2 WALK START CORNERS. The mirror (`side: back`) left
// the candidate set on 2026-08-08 and the start corner took its place -- adding the walk axis
// ON TOP of the mirror halves makes every candidate tie with its twin (measured: 16 rows, 8
// answers). If anything here ever produces 16, that is the defect, not a richer search.
//
// WHY NOT A RENAME OF `back`. On quarter turns the mirror flips the ROW axis
// (`seating.js:38-40`), so `rot90_back` is `rot270` numbered from the top-right and
// `rot270_back` is `rot90` from the top-right; only the half turns keep their rotation. The
// two spaces are not the same eight under new names, and this screen must not imply they are.
//
// WHY THE LAYOUT IS PART OF THIS MODULE. The control is 2 columns (the start corner) by 4 rows
// (the turn) because those are the operator's two hands. If the layout lived in the composition
// root it would be a presentation accident; here it is the same value the scorer iterates,
// so the screen and the score cannot disagree about what candidate 3 is.
//
// NO DOM. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE. Everything exported is frozen.
// ═══════════════════════════════════════════════════════════════════════════════

// Spelled exactly as stored, so this screen never speaks a private language: `rot270_tr` is
// what the server scores, what it ships, and what a confirmation writes back.
export const ROTATIONS = Object.freeze([0, 90, 180, 270]);
export const STARTS = Object.freeze(['top_left', 'top_right']);
/** The candidate token's second half. `parse_frame` on the server accepts exactly these. */
export const START_TOKEN = Object.freeze({ top_left: 'tl', top_right: 'tr' });
/** Every candidate names the FRONT. A numbering corner is not a claim that the wafer flipped. */
export const CANDIDATE_SIDE = 'front';

export function candidateId(rotation, start) {
  return `rot${rotation}_${START_TOKEN[start]}`;
}

/**
 * Parse a spelling back into its axes -> `{rotation, side, start}`. `null` when unreadable.
 *
 * 🔴 LEGACY SPELLINGS STAY READABLE, AND THEY MEAN WHAT THEY ALWAYS MEANT. Rows confirmed
 *    before the walk axis existed hold `rot90_front` / `rot90_back`, and the database still
 *    holds `side` for maps this screen never scored. `_front` reads as the top-left walk
 *    (same geometry, same walk); `_back` reads as a PHYSICAL MIRROR with no start corner --
 *    calling it 우상단 was the equivalence this round measured wrong.
 */
export function parseCandidateId(id) {
  const m = /^rot(0|90|180|270)_(tl|tr|front|back)$/.exec(String(id || ''));
  if (!m) return null;
  const rotation = Number(m[1]);
  const token = m[2];
  if (token === 'back') return Object.freeze({ rotation, side: 'back', start: null });
  const start = token === 'tr' ? 'top_right' : 'top_left';
  return Object.freeze({ rotation, side: CANDIDATE_SIDE, start });
}

/** The eight, in a stable order: both start corners on each turn, turns ascending. */
export function candidateList() {
  const out = [];
  for (const rotation of ROTATIONS) {
    for (const start of STARTS) {
      out.push(Object.freeze({
        id: candidateId(rotation, start),
        rotation,
        side: CANDIDATE_SIDE,
        start,
        degLabel: `${rotation}°`,
      }));
    }
  }
  return Object.freeze(out);
}

/**
 * The same eight arranged as the control: one row per turn, one cell per start corner.
 * `grid[r].cells[0]` is 좌상단 시작, `[1]` is 우상단 -- the operator reads DOWN to turn and
 * ACROSS to change which corner the equipment numbered from.
 */
export function candidateGrid() {
  const byId = new Map(candidateList().map(c => [c.id, c]));
  return Object.freeze(ROTATIONS.map(rotation => Object.freeze({
    rotation,
    degLabel: `${rotation}°`,
    cells: Object.freeze(STARTS.map(start => byId.get(candidateId(rotation, start)))),
  })));
}

// UI copy. Korean, terse: the header names the corner the numbering starts from, which is the
// motion the operator is choosing between. NOT 앞면/뒷면 -- no physical side is being picked
// here, and the map editor one click away is where that genuinely lives.
export const START_HEADERS = Object.freeze({
  top_left: '좌상단 시작',
  top_right: '우상단 시작',
});

// The operator asks about flipping. Answered once, permanently, under the grid -- the mirror
// is not a candidate here, and this says so rather than leaving its absence to be noticed.
export const INVERSION_FOOTNOTE =
  '좌우/상하 뒤집기는 후보가 아닙니다 - '
  + '번호 시작 모서리로 대신 맞춥니다. '
  + '실제 뒤집힌 웨이퍼는 맵 편집기에서 선언합니다.';

export const BADGE_WINNER = '추천';
export const BADGE_STORED = '현재 선언';
