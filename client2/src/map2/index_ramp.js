// ═══════════════════════════════════════════════════════════════════════════════
// THE INDEX RAMP -- serpentine rank to colour. PURE. NO DOM, NO CANVAS, NO TRANSPORT,
// NO MODULE-LEVEL MUTABLE STATE.
//
// WHAT THIS PICTURE IS FOR, AND WHAT IT CANNOT DO.
//
// 🔴 A WRONG FRAME DOES NOT BREAK THE SWEEP. IT ROTATES OR MIRRORS IT. This was measured
//    against `seating.js` itself before a line of this file was written, and it is a property
//    of the problem rather than of any implementation: `localIndex` is a translation plus an
//    optional reflection and `seatOf` is a rotation plus an optional mirror, so each of the
//    eight candidates maps the stored-coordinate lattice onto itself ISOMETRICALLY. Isometries
//    preserve adjacency. Therefore EVERY adjacency-based statistic is blind to the frame --
//    measured: median neighbour dE00 was 4.32 for all eight candidates, one distinct value.
//
//    What separates them is ORIENTATION: (which corner holds rank 1) x (does the walk run in
//    rows or in columns) = 4 x 2 = 8, which exactly saturates the candidate space. Measured on
//    a planted map: eight distinct signatures, no two alike, with the truth frame the unique
//    one reading TOP-LEFT + ROWS. That is why the legend states the rule in words -- the
//    colours only make it legible, the sentence is the diagnostic.
//
//    ⚠️ SO DO NOT ADD A "SMOOTHNESS" SCORE HERE, and do not let a later round read a local
//       break as a frame fault. A break is frame-INVARIANT, which makes it a statement about
//       the DATA: a gap in the job's numbering, a renumbering, two maps pooled into one walk,
//       or a clipped payload. Those are real findings and they are a different question.
//
// 🔴 WHY THE HUE IS CYCLIC WITH A PERIOD FIXED IN INDEX UNITS, AND NOT A GRADIENT. A monotone
//    ramp's local contrast is inversely proportional to N, because its total perceptual path
//    is bounded (~224 dE00 for turbo, ~126 for a single hue sweep). Measured step-10 dE00 for
//    turbo: 20.24 at N=88, 6.39 at N=266, 3.29 at N=512, 1.26 at N=1313. The reference floors
//    in this database are 88, 425, 425, 854, 927 and 1313 cells, so a gradient is unreadable
//    over most of them -- a jump of ten and a jump of one look identical. A period fixed in
//    INDEX units makes local contrast independent of N: measured on the SHIPPED ramp, the
//    worst adjacent step is 4.56 dE00 and the weakest jump-of-ten is 20.10, and both hold at
//    N=88, 266 and 1313 alike.
//    `map2_index_ramp_harness.mjs` RUNS a monotone ramp and requires it to FAIL at N >= 512,
//    so this cannot be "simplified" back into a gradient without the build saying so.
//
// 🔴 THE PERIOD IS PRIME. 61, not 64. A period that shares a factor with the grid's row width
//    makes every row start on the same hue, which draws vertical stripes that mean nothing.
//    A prime cannot align with any row width. It also measurably beats 64 on the near-wrap:
//    dE00 between ranks 64 apart is 11.1 at P=61 against 0.6 at P=64, where the two were a
//    genuine colour collision.
//
// 🔴 THE LIGHTNESS BAND COMES FROM TOKENS AND DIFFERS PER THEME. Light is the default and a
//    ramp tuned on dark fails it: turbo's minimum WCAG contrast against `--bg-inset` is 1.16
//    on light, worse than the 1.18 the usability walk already recorded. The shipped bands were
//    measured against the real tokens -- light 0.46->0.58 gives 3.71 minimum, dark 0.66->0.78
//    gives 5.02, both clearing 3:1 at every rank. This module never reads a stylesheet; the
//    composition root resolves the band and passes it in, the same discipline that keeps
//    `painter.js` importable without a DOM.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Hue cycles every 61 ranks. PRIME ON PURPOSE -- see the header. Exported because the harness
 * scores the wrap distance against it and must not restate the number.
 */
export const INDEX_RAMP_PERIOD = 61;

/**
 * The most chroma this ramp will ever ask for. A CAP, not the value used: what a hue actually
 * gets is `min(cap, envelope(hue))` -- see `chromaAt`.
 *
 * 🔴 A BIGGER NUMBER HERE DOES NOT MAKE THE RAMP MORE VIVID, AND ON ITS OWN IT MAKES IT WORSE.
 *    Raising a flat chroma to 0.20 measures meanC 0.149 with a WORST adjacent step of 7.02
 *    dE00 -- past the 6 the harness allows -- because the sRGB boundary collapses around hue
 *    30 deg at these lightnesses and neighbouring ranks then get very different reductions.
 *    That is the seam. The vividness has to come from the ENVELOPE below, not from here.
 */
export const INDEX_RAMP_CHROMA_CAP = 0.30;

/**
 * How fast the chroma envelope may change, in chroma per DEGREE of hue.
 *
 * 🔴 THIS IS THE WHOLE GAMUT FIX, AND IT IS NOT EITHER OF THE TWO OBVIOUS ONES. Measured, all
 *    three, light band, N=266 (meanC = mean achieved chroma, the vividness number):
 *
 *      flat chroma 0.12, clip when outside   meanC 0.114   worst adjacent 3.82   <- shipped before
 *      flat chroma 0.20, clip when outside   meanC 0.149   worst adjacent 7.02   <- seam returns
 *      chroma = 0.85 x each hue's maximum    meanC 0.139   worst adjacent 10.07  <- WORSE
 *      chroma = 0.95 x each hue's maximum    meanC 0.156   worst adjacent 11.59  <- WORSE STILL
 *      gradient-limited envelope (this)      meanC 0.133   worst adjacent 4.56
 *
 *    "Fit the chroma to the hue" is the intuitive answer and it is measurably the worst one:
 *    riding the gamut boundary means inheriting every kink IN that boundary at full amplitude.
 *    The seam is a HIGH-FREQUENCY feature of the boundary, so the repair is to low-pass it --
 *    take the largest envelope that stays under the boundary everywhere AND whose slope is
 *    capped. Nothing is ever clipped, so there is no discontinuity to see, and the envelope
 *    sits as high as smoothness allows rather than as high as the gamut allows.
 */
export const INDEX_RAMP_CHROMA_SLOPE = 0.0015;

/** Kept for callers that only want "roughly how saturated is this ramp". */
export const INDEX_RAMP_CHROMA = INDEX_RAMP_CHROMA_CAP;

/**
 * The fallback band. Used ONLY when a document stub answers every token with an empty string,
 * exactly like `thumbPalette`'s fallbacks -- never as a second palette. It is the LIGHT band
 * because light is the default theme, so a failure to resolve degrades toward the case that
 * was measured hardest rather than toward the one that only works on dark.
 */
export const INDEX_RAMP_BAND_FALLBACK = Object.freeze({ l0: 0.46, l1: 0.58 });

/**
 * A rank's colour, or `null` when the die carries no number.
 *
 * 🔴 `null` IS A FACT AND NOT A MISSING RETURN VALUE, the same contract `legend.colorOf` holds.
 *    A die the job touched but did not number is IN the walk (the server's `_index_member` is
 *    explicit about this: dropping it would pull every later rank back by one). It has no
 *    colour, and the renderer must draw that absence rather than substitute one -- a plausible
 *    colour on an unnumbered die is a number the data never carried.
 *
 * @param {number|null} rank  the server's normalised rank, 1-based. USED VERBATIM.
 * @param {number} rankMax    the walk's extent -- the largest rank in THIS map.
 * @param {{l0:number,l1:number}} band  lightness band, resolved from tokens by the caller.
 */
export function indexColor(rank, rankMax, band) {
  if (!Number.isInteger(rank) || rank < 1) return null;
  const b = band && Number.isFinite(band.l0) && Number.isFinite(band.l1)
    ? band : INDEX_RAMP_BAND_FALLBACK;
  // 🔴 THE RANK IS NOT RENORMALISED HERE. The server already shifted each map's own base to 1
  //    with the same function the scorer used, and a second spelling of that arithmetic is how
  //    a `ceil`/`round` split once put 34 in the database and 33 on the screen. `rankMax` is
  //    the ramp's DOMAIN, not a re-derivation of the rank: the numbering may be sparse (the
  //    shift is min->1, not a dense re-rank), so `rankMax` and the count of numbered dies are
  //    different numbers on purpose and neither is computed from the other.
  const span = Math.max(1, rankMax - 1);
  const t = Math.min(1, Math.max(0, (rank - 1) / span));
  const L = b.l0 + (b.l1 - b.l0) * t;
  const H = ((rank - 1) % INDEX_RAMP_PERIOD) / INDEX_RAMP_PERIOD * 360;
  return oklchToHex(L, chromaAt(H, b), H);
}

/**
 * The legend bar, as data: evenly spaced stops across the same domain the cells are painted
 * from.
 *
 * 🔴 THE BAR IS BUILT FROM `indexColor`, NOT FROM A HAND-WRITTEN CSS GRADIENT. A gradient
 *    spelled in the stylesheet is a SECOND implementation of the ramp, and the day the two
 *    drift the legend explains a picture that is not on screen. Enough stops that the cyclic
 *    hue reads as a sweep rather than as banding.
 */
export function rampStops(rankMax, band, count = 96) {
  const n = Math.max(2, Math.floor(count));
  const max = Math.max(1, Math.floor(rankMax) || 1);
  const out = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const rank = 1 + Math.round(t * (max - 1));
    out.push(Object.freeze({ offset: t, color: indexColor(rank, max, band) }));
  }
  return Object.freeze(out);
}

/** The stops as one CSS `linear-gradient(...)` value. The bar's only styling input. */
export function rampGradientCss(rankMax, band, count) {
  const stops = rampStops(rankMax, band, count)
    .map(s => `${s.color} ${(s.offset * 100).toFixed(2)}%`)
    .join(', ');
  return `linear-gradient(90deg, ${stops})`;
}

// ── THE CHROMA ENVELOPE ─────────────────────────────────────────────────────────
// The largest chroma this band can use at each hue WITHOUT ever being clipped, smoothed so
// that neighbouring hues get neighbouring chroma. Memoised per band: it costs a few thousand
// binary searches to build and the band changes only when the theme does.

const envelopeCache = new Map();

/** Largest in-gamut chroma at this lightness and hue. */
function maxChromaAt(L, hueDeg) {
  let lo = 0, hi = 0.45;
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2;
    if (inGamut(oklchToLinear(L, mid, hueDeg))) lo = mid; else hi = mid;
  }
  return lo;
}

function envelopeFor(band) {
  const key = `${band.l0}:${band.l1}`;
  const hit = envelopeCache.get(key);
  if (hit) return hit;

  // The ceiling is the WORST lightness in the band at each hue -- the ramp tilts through the
  // whole band, so a chroma that only fits at one end would clip at the other.
  const ceiling = new Array(360);
  for (let h = 0; h < 360; h++) {
    let worst = Infinity;
    for (let i = 0; i <= 6; i++) {
      worst = Math.min(worst, maxChromaAt(band.l0 + (band.l1 - band.l0) * (i / 6), h));
    }
    ceiling[h] = worst;
  }
  // Slope-capped erosion on the hue circle: the largest function under the ceiling whose
  // derivative never exceeds INDEX_RAMP_CHROMA_SLOPE. This is what removes the seam -- the
  // ceiling's sharp dips are widened into gentle valleys instead of being ridden into.
  const env = new Array(360);
  for (let h = 0; h < 360; h++) {
    let best = INDEX_RAMP_CHROMA_CAP;
    for (let d = -180; d <= 180; d++) {
      const j = ((h + d) % 360 + 360) % 360;
      const bound = ceiling[j] + Math.abs(d) * INDEX_RAMP_CHROMA_SLOPE;
      if (bound < best) best = bound;
    }
    env[h] = best;
  }
  const frozen = Object.freeze(env);
  envelopeCache.set(key, frozen);
  return frozen;
}

/** The chroma this hue gets under this band. Never above the gamut, never a sudden step. */
export function chromaAt(hueDeg, band) {
  const b = band && Number.isFinite(band.l0) && Number.isFinite(band.l1)
    ? band : INDEX_RAMP_BAND_FALLBACK;
  const h = ((Math.round(hueDeg) % 360) + 360) % 360;
  return envelopeFor(b)[h];
}

// ── OKLCH -> sRGB ───────────────────────────────────────────────────────────────
// Transcribed from the OKLab definition rather than re-derived. Chroma is REDUCED until the
// colour is inside sRGB instead of clamping the channels: clamping bends the hue, and a hue
// that bends near the gamut edge would make two ranks that are far apart read as neighbours.

function oklchToLinear(L, C, Hdeg) {
  const h = (Hdeg * Math.PI) / 180;
  const a = C * Math.cos(h);
  const bb = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * bb;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * bb;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * bb;
  const l = l_ * l_ * l_, m = m_ * m_ * m_, s = s_ * s_ * s_;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ];
}

const inGamut = rgb => rgb.every(v => v >= -0.0005 && v <= 1.0005);

function oklchToHex(L, C, H) {
  let rgb = oklchToLinear(L, C, H);
  if (!inGamut(rgb)) {
    let lo = 0, hi = C;
    for (let i = 0; i < 20; i++) {
      const mid = (lo + hi) / 2;
      if (inGamut(oklchToLinear(L, mid, H))) lo = mid; else hi = mid;
    }
    rgb = oklchToLinear(L, lo, H);
  }
  return `#${rgb.map(toByte).join('')}`;
}

function toByte(linear) {
  const c = Math.max(0, Math.min(1, linear));
  const srgb = c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
  return Math.round(Math.max(0, Math.min(1, srgb)) * 255).toString(16).padStart(2, '0');
}
