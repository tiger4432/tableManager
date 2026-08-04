// ═══════════════════════════════════════════════════════════════════════════════
// THE SEAM TO LAYERS (5) AND (7), WHICH ANOTHER LANE OWNS.
//
// This file exists so that exactly ONE line changes when `client2/src/map/scoring.js` and
// `client2/src/map/verdict.js` land. Nothing else in Map Editor 2 imports the verdict
// implementation directly, so nothing else has to be touched at the handover.
//
// WHEN THE MAP LANE'S MODULES ARRIVE:
//   1. replace the import below with `export { decideVerdict, VERDICT, REASON } from '../map/verdict.js';`
//   2. delete `verdict_placeholder.js`
//   3. run the shell harness -- it scores the CONTRACT (shape of the returned record and the
//      "no threshold means no verdict" rule), so it will tell you whether the real module
//      keeps the promises the shell was built against.
//
// THE CONTRACT, stated here because it is the thing both sides must keep:
//   decideVerdict(scorings, thresholds, context) -> frozen {
//     kind: 'winner' | 'indistinguishable' | 'not_scorable',
//     reason: string|null, winnerId: string|null, rankedIds: string[],
//     marginDies: number|null, discriminating: number|null,
//     minMargin: number|null, minDiscriminating: number|null,
//     tiedCount: number|null, refusalDetail: string|null }
//   - `thresholds` is passed in, always. A module that defaults a threshold breaks the
//     contract even if every number it produces looks reasonable.
//   - no field is a ratio, a percentage or a fitness. Counts and a margin in dies only.
// ═══════════════════════════════════════════════════════════════════════════════

// SWAPPED 2026-08-05: the verdict lane's module landed and this now points at it.
// `verdict_placeholder.js` is DEAD -- it is not imported from anywhere and must not be
// resurrected. It carried a real defect that `verdict.js` fixes (its `finiteOrNull` used bare
// `Number(v)`, and `Number(null)` is 0, so an ABSENT `min_margin_dies` became a threshold of
// zero and every payload produced a winner -- I4 living inside the guard against I4).
export { decideVerdict, VERDICT, REASON } from './verdict.js';
