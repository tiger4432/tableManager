// The Spotfire standard's colours as a canvas takes them (lead b72a0ea4f ㄱ). The values live in tokens.css (--sf-*, both
// themes) - written once there. A canvas cannot read CSS, so it is handed what the page's computed style says, read again
// each time a part draws (`paletteOf`): a theme changed is the next picture's.

/** The tokens a canvas draws with: a role each, the category colours fill and line in Spotfire's order, one value alone. */
export const TOKENS = Object.freeze({
  bg: '--sf-bg', text: '--sf-text', axis: '--sf-axis', active: '--sf-active', brush: '--sf-brush',
  one: ['--sf-one', '--sf-one-line'],
  cat: [1, 2, 3, 4, 5, 6, 7].map((k) => [`--sf-cat-${k}`, `--sf-cat-${k}-line`]),
  swatches: ['--sf-swatch-red', '--sf-swatch-grey'],
});

/** A point not marked while others are: its colour this much, the background the rest - opaque (measured 0.20 on every
 *  channel, dark and light, 10-12). */
export const DIM_SHARE = 0.2;
/** Spotfire's marker at its default «Marker size 19%»: 13 px across (measured). The size slider scales from here. */
export const MARKER_PX = 13;
export const MARKER_PCT = 19;

/** The palette by a reader of token values - `read(name)` the value a token holds. */
export function readPalette(read) {
  const pair = ([fill, line]) => [read(fill), read(line)];
  return { bg: read(TOKENS.bg), text: read(TOKENS.text), axis: read(TOKENS.axis), active: read(TOKENS.active), brush: read(TOKENS.brush),
    one: pair(TOKENS.one), cat: TOKENS.cat.map(pair), swatches: TOKENS.swatches.map(read) };
}

/** The palette a document's root computes now - the page's theme as its tokens say it. */
export function paletteOf(doc) {
  const view = doc && doc.defaultView;
  const style = view && typeof view.getComputedStyle === 'function' ? view.getComputedStyle(doc.documentElement) : null;
  return readPalette((name) => (style ? style.getPropertyValue(name).trim() : ''));
}

// Any hex a stylesheet holds - the build writes #FFFFFF as #fff, and the page computes what the build wrote.
const hex = (h) => {
  const s = String(h).trim().replace(/^#/, '');
  const full = s.length === 3 ? [...s].map((c) => c + c).join('') : s;
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
};
/** `color` mixed toward `bg`, keeping `share` of the colour - opaque. */
export function mix(color, bg, share = DIM_SHARE) {
  const [a, b] = [hex(color), hex(bg)];
  return `#${a.map((v, i) => Math.round(v * share + b[i] * (1 - share)).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
}

/** The colours of category k (the palette repeats past its last). */
export const categoryColor = (palette, k) => palette.cat[((k % palette.cat.length) + palette.cat.length) % palette.cat.length];
