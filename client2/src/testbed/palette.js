// The testbed's colours, measured on the owner's Spotfire (task/SPOTFIRE_SCATTER_REFERENCE.md §11) - the one place they
// are written. The page sets them as CSS variables on its root (`themeVars`) and the canvas renderer, which cannot read
// CSS, reads them from here: one source for both.

export const THEMES = Object.freeze({
  dark: { page: '#232323', bg: '#2A2A2A', text: '#FFFFFF', text2: '#C8C8C8', title: '#FFFFFF', dim: 'rgba(200, 200, 200, 0.45)',
    line: '#404040', stripe: '#404040', axis: '#666666', pill: 'rgba(255, 255, 255, 0.45)', status: '#61646B', statusText: '#FFFFFF',
    active: '#7188F8', brush: 'rgba(113, 136, 248, 0.15)' },
  light: { page: '#F7F9FF', bg: '#FFFFFF', text: '#61646B', text2: '#61646B', title: '#313336', dim: 'rgba(49, 51, 54, 0.45)',
    line: '#F0F1F2', stripe: '#F7F9FF', axis: '#D1D4DE', pill: '#BDBFC5', status: '#EDF0F7', statusText: '#313336',
    active: '#7188F8', brush: 'rgba(113, 136, 248, 0.15)' },
});

/** The properties and filters panels - light in both themes, as Spotfire's (measured 10-12). */
export const PANEL = Object.freeze({ bg: '#FFFFFF', head: '#F2F5FC', text: '#313336', muted: '#6D7078', accent: '#3050EF', accentText: '#FFFFFF',
  line: '#D1D4DE', line2: '#EDF0F7', pill: '#D0D0D0', pick: '#BDCDF5', nameBg: '#EBEFFF', nameText: '#000000' });

/** The category colours, fill and border, in Spotfire's order; one value alone is ONE. */
export const CATEGORY = Object.freeze([['#6489FA', '#4B67BC'], ['#FA7864', '#BC5A4B'], ['#FFDE5C', '#BFA645'], ['#72ECA6', '#56B17C'],
  ['#ED72DD', '#B256A6'], ['#72BEED', '#568EB2'], ['#FAA264', '#BC7A4B']]);
export const ONE = Object.freeze(['#A0A0A0', '#787878']);
/** A marked cross table cell, a marked table row - and its text. */
export const MARKED = '#00A650';
export const MARKED_TEXT = '#FFFFFF';
/** A point not marked while others are: its colour this much, the background the rest - opaque (measured 0.20 on every
 *  channel, dark and light, 10-12). */
export const DIM_SHARE = 0.2;
/** Spotfire's marker at its default «Marker size 19%»: 13 px across (measured). The size slider scales from here. */
export const MARKER_PX = 13;
export const MARKER_PCT = 19;

const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
/** `color` mixed toward `bg`, keeping `share` of the colour - opaque. */
export function mix(color, bg, share = DIM_SHARE) {
  const [a, b] = [hex(color), hex(bg)];
  return `#${a.map((v, i) => Math.round(v * share + b[i] * (1 - share)).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
}

/** The colours of category k (the palette repeats past seven). */
export const categoryColor = (k) => CATEGORY[((k % CATEGORY.length) + CATEGORY.length) % CATEGORY.length];

/** The theme as the page's CSS variables. */
export function themeVars(name) {
  const t = THEMES[name] || THEMES.dark;
  return { '--tb-page': t.page, '--tb-bg': t.bg, '--tb-text': t.text, '--tb-text-2': t.text2, '--tb-title': t.title, '--tb-dim': t.dim,
    '--tb-line': t.line, '--tb-stripe': t.stripe, '--tb-axis': t.axis, '--tb-pill': t.pill, '--tb-status': t.status,
    '--tb-status-text': t.statusText, '--tb-active': t.active, '--tb-marked': MARKED,
    '--tb-panel-bg': PANEL.bg, '--tb-panel-head': PANEL.head, '--tb-panel-text': PANEL.text, '--tb-panel-muted': PANEL.muted,
    '--tb-panel-accent': PANEL.accent, '--tb-panel-accent-text': PANEL.accentText, '--tb-panel-line': PANEL.line, '--tb-panel-line-2': PANEL.line2, '--tb-panel-pill': PANEL.pill,
    '--tb-panel-pick': PANEL.pick, '--tb-panel-name-bg': PANEL.nameBg, '--tb-panel-name-text': PANEL.nameText,
    '--tb-marked-text': MARKED_TEXT };
}
