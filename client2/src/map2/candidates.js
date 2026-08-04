// ═══════════════════════════════════════════════════════════════════════════════
// THE CANDIDATE SET -- the 8 orientations, named once.
//
// (MAP_ALIGNMENT_SPEC 0.2 layer 5; R2_ui_operator_loop.md section 3.)
//
// WHY EIGHT AND NOT SIXTEEN. Round 1 measured that every answer appears twice in the
// 16-spelling set, so half of a 16-row control is a second copy of the other half. Vertical
// flip is not a third axis: it is `180 deg more turn, then the same left/right flip`, which
// is why it appears here as ONE permanent footnote rather than as a doubling of the list.
//
// WHY THE LAYOUT IS PART OF THIS MODULE. The control is 2 columns (the flip) by 4 rows (the
// turn) because those are the operator's two hands. If the layout lived in the composition
// root it would be a presentation accident; here it is the same value the scorer iterates,
// so the screen and the score cannot disagree about what candidate 3 is.
//
// NO DOM. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE. Everything exported is frozen.
// ═══════════════════════════════════════════════════════════════════════════════

// Spelled exactly as stored, so this screen never speaks a private language: `rot270_back`
// is what the database holds and what every other screen shows.
export const ROTATIONS = Object.freeze([0, 90, 180, 270]);
export const SIDES = Object.freeze(['front', 'back']);

export function candidateId(rotation, side) {
  return `rot${rotation}_${side}`;
}

/** Parse a stored spelling back into its axes. Returns null when it is not one of the eight. */
export function parseCandidateId(id) {
  const m = /^rot(0|90|180|270)_(front|back)$/.exec(String(id || ''));
  if (!m) return null;
  return Object.freeze({ rotation: Number(m[1]), side: m[2] });
}

/** The eight, in a stable order: all four turns on the front, then all four on the back. */
export function candidateList() {
  const out = [];
  for (const side of SIDES) {
    for (const rotation of ROTATIONS) {
      out.push(Object.freeze({
        id: candidateId(rotation, side),
        rotation,
        side,
        degLabel: `${rotation}°`,
      }));
    }
  }
  return Object.freeze(out);
}

/**
 * The same eight arranged as the control: one row per turn, one cell per flip.
 * `grid[r].cells[0]` is front, `[1]` is back -- the operator reads DOWN to turn and
 * ACROSS to flip.
 */
export function candidateGrid() {
  const byId = new Map(candidateList().map(c => [c.id, c]));
  return Object.freeze(ROTATIONS.map(rotation => Object.freeze({
    rotation,
    degLabel: `${rotation}°`,
    cells: Object.freeze(SIDES.map(side => byId.get(candidateId(rotation, side)))),
  })));
}

// UI copy. Korean, and the parenthetical is what makes the column header a description of a
// motion rather than a word the operator has to already know.
export const SIDE_HEADERS = Object.freeze({
  front: '앞면 (좌우 그대로)',
  back: '뒷면 (좌우 뒤집음)',
});

// The operator asks about inversion. Answered once, permanently, under the grid -- not as a
// third axis, and not re-explained on every row.
export const INVERSION_FOOTNOTE =
  '상하 뒤집기는 별도 후보가 아닙니다 - '
  + '180° 더 돌린 뒤 좌우 뒤집기와 같은 '
  + '격자 변환입니다.';

export const BADGE_WINNER = '추천';
export const BADGE_STORED = '현재 선언';
