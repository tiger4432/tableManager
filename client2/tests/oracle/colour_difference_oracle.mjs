// ═══════════════════════════════════════════════════════════════════════════════
// COLOUR DIFFERENCE ORACLE -- CIEDE2000 and WCAG contrast, for scoring what was PAINTED.
//
// IN A SUBDIRECTORY ON PURPOSE. `check_harnesses.mjs` discovers every `*.mjs` directly under
// `client2/tests/`, and a library has no `ASSERTIONS` line to report -- the alignment scoring
// oracle next door is here for the same reason.
//
// 🔴 THIS IS AN INDEPENDENT ORACLE, NOT A SECOND COPY OF THE RAMP. It knows nothing about
//    periods, lightness bands or ranks: it takes two colours and answers how far apart a human
//    sees them. That is what makes it able to fail `index_ramp.js` -- an oracle that shared the
//    ramp's arithmetic would agree with a broken ramp by construction, which is the shape this
//    domain has been bitten by (a helper that answered the same for two different inputs was
//    not a lenient oracle, it was not an oracle).
//
// ASCII ONLY in anything printed by callers (cp949 console).
// ═══════════════════════════════════════════════════════════════════════════════

const srgbToLinear = c => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));

/** '#rrggbb' -> [r, g, b] in 0..1. Throws on anything else: a silent NaN scores as agreement. */
export function parseHex(hex) {
  const s = String(hex || '').trim().replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(s)) throw new Error(`not a #rrggbb colour: ${JSON.stringify(hex)}`);
  return [
    parseInt(s.slice(0, 2), 16) / 255,
    parseInt(s.slice(2, 4), 16) / 255,
    parseInt(s.slice(4, 6), 16) / 255,
  ];
}

export function relativeLuminance(rgb) {
  const [r, g, b] = rgb.map(srgbToLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.x contrast ratio. 3:1 is the non-text (SC 1.4.11) bar a filled die has to clear. */
export function contrastRatio(hexA, hexB) {
  const la = relativeLuminance(parseHex(hexA));
  const lb = relativeLuminance(parseHex(hexB));
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Composite a translucent colour over an opaque one -- the floor wash is rgba over --bg-inset. */
export function over(hexFg, alpha, hexBg) {
  const f = parseHex(hexFg), b = parseHex(hexBg);
  const mix = f.map((v, i) => alpha * v + (1 - alpha) * b[i]);
  return `#${mix.map(v => Math.round(Math.max(0, Math.min(1, v)) * 255)
    .toString(16).padStart(2, '0')).join('')}`;
}

export function rgbToLab(rgb) {
  const [r, g, b] = rgb.map(srgbToLinear);
  const X = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047;
  const Y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b);
  const Z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883;
  const f = t => (t > 216 / 24389 ? Math.cbrt(t) : (841 / 108) * t + 4 / 29);
  const fx = f(X), fy = f(Y), fz = f(Z);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

/** CIEDE2000 between two '#rrggbb' colours. ~1 is the just-noticeable step. */
export function deltaE00(hexA, hexB) {
  const [L1, a1, b1] = rgbToLab(parseHex(hexA));
  const [L2, a2, b2] = rgbToLab(parseHex(hexB));
  const rad = Math.PI / 180, deg = 180 / Math.PI;
  const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2), Cb = (C1 + C2) / 2;
  const G = 0.5 * (1 - Math.sqrt(Math.pow(Cb, 7) / (Math.pow(Cb, 7) + Math.pow(25, 7))));
  const ap1 = (1 + G) * a1, ap2 = (1 + G) * a2;
  const Cp1 = Math.hypot(ap1, b1), Cp2 = Math.hypot(ap2, b2);
  const hp = (bv, ap) => {
    if (bv === 0 && ap === 0) return 0;
    const h = Math.atan2(bv, ap) * deg;
    return h < 0 ? h + 360 : h;
  };
  const hp1 = hp(b1, ap1), hp2 = hp(b2, ap2);
  const dLp = L2 - L1, dCp = Cp2 - Cp1;
  let dhp = 0;
  if (Cp1 * Cp2 !== 0) {
    dhp = hp2 - hp1;
    if (dhp > 180) dhp -= 360; else if (dhp < -180) dhp += 360;
  }
  const dHp = 2 * Math.sqrt(Cp1 * Cp2) * Math.sin((dhp / 2) * rad);
  const Lbp = (L1 + L2) / 2, Cbp = (Cp1 + Cp2) / 2;
  let hbp = hp1 + hp2;
  if (Cp1 * Cp2 !== 0) {
    if (Math.abs(hp1 - hp2) > 180) hbp += (hbp < 360 ? 360 : -360);
    hbp /= 2;
  }
  const T = 1 - 0.17 * Math.cos((hbp - 30) * rad) + 0.24 * Math.cos(2 * hbp * rad)
            + 0.32 * Math.cos((3 * hbp + 6) * rad) - 0.20 * Math.cos((4 * hbp - 63) * rad);
  const dTh = 30 * Math.exp(-1 * Math.pow((hbp - 275) / 25, 2));
  const Rc = 2 * Math.sqrt(Math.pow(Cbp, 7) / (Math.pow(Cbp, 7) + Math.pow(25, 7)));
  const Sl = 1 + (0.015 * Math.pow(Lbp - 50, 2)) / Math.sqrt(20 + Math.pow(Lbp - 50, 2));
  const Sc = 1 + 0.045 * Cbp;
  const Sh = 1 + 0.015 * Cbp * T;
  const Rt = -Math.sin(2 * dTh * rad) * Rc;
  return Math.sqrt(Math.pow(dLp / Sl, 2) + Math.pow(dCp / Sc, 2) + Math.pow(dHp / Sh, 2)
                   + Rt * (dCp / Sc) * (dHp / Sh));
}
