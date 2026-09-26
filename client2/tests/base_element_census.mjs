// BASE ELEMENT CENSUS — lead a5e732537 ① 셈: for each base element, how many looks there are today.
// Runs IN a page (a look is a rendered fact): every element of a kind is reduced to a signature of
// its computed style, and the census counts the distinct signatures. Colour is left out on purpose
// — tone (ok · warn · danger) is a state, not a second style.
//
// Run in a page:  (await import('/tests/base_element_census.mjs')).baseElementCensus()

const px = (v) => Math.round((parseFloat(v) || 0) * 10) / 10;

function box(cs) {
  return `pad ${px(cs.paddingTop)} ${px(cs.paddingRight)} ${px(cs.paddingBottom)} ${px(cs.paddingLeft)}`
    + ` · border ${px(cs.borderTopWidth)}/${px(cs.borderBottomWidth)}/${px(cs.borderLeftWidth)}`
    + ` · radius ${px(cs.borderTopLeftRadius)}`;
}
function type(cs) {
  return `${cs.fontFamily.split(',')[0].replace(/["']/g, '')} ${px(cs.fontSize)} w${cs.fontWeight}`
    + `${cs.textTransform !== 'none' ? ` ${cs.textTransform}` : ''}`;
}
const filled = (cs) => (/^(transparent|rgba\(0, 0, 0, 0\))$/.test(cs.backgroundColor) ? 'bare' : 'filled');

const KINDS = {
  table: {
    pick: (doc) => doc.querySelectorAll('table'),
    sign: (el, win) => {
      const th = el.querySelector('th');
      const td = el.querySelector('td');
      return [`th ${th ? `${type(win.getComputedStyle(th))} ${box(win.getComputedStyle(th))}` : '-'}`,
        `td ${td ? `${type(win.getComputedStyle(td))} ${box(win.getComputedStyle(td))}` : '-'}`].join(' | ');
    },
  },
  input: {
    pick: (doc) => doc.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=file]):not([type=range]), textarea, select'),
    sign: (el, win) => { const cs = win.getComputedStyle(el); return `${el.tagName.toLowerCase()} ${type(cs)} ${box(cs)} · h ${px(el.getBoundingClientRect().height)} · ${filled(cs)}`; },
  },
  button: {
    pick: (doc) => doc.querySelectorAll('button, [role=button]:not(tr):not(div), input[type=button], input[type=submit]'),
    sign: (el, win) => { const cs = win.getComputedStyle(el); return `${type(cs)} ${box(cs)} · ${filled(cs)}`; },
  },
  statNumber: {
    pick: (doc) => doc.querySelectorAll('[class*="number-value"], [class*="stat-value"], [class*="metric-value"], [class*="kpi"], [class*="-count"]:not(select):not(button)'),
    sign: (el, win) => { const cs = win.getComputedStyle(el); return `${type(cs)} ${box(cs)} · num ${cs.fontVariantNumeric}`; },
  },
  emptyLine: {
    pick: (doc) => doc.querySelectorAll('[class*="empty"]:not([class*="empty-icon"]):not([class*="empty-text"])'),
    sign: (el, win) => { const cs = win.getComputedStyle(el); return `${type(cs)} ${box(cs)} · align ${cs.textAlign} · ${cs.display}`; },
  },
  formRow: {
    // A row that holds its own label and its own control.
    pick: (doc) => [...doc.querySelectorAll('label, div, p, li')].filter((el) => {
      const kids = [...el.children];
      const label = kids.some((k) => k.tagName === 'LABEL' || /label/.test(String(k.className)));
      const control = kids.some((k) => /^(INPUT|SELECT|TEXTAREA)$/.test(k.tagName));
      return label && control;
    }),
    sign: (el, win) => { const cs = win.getComputedStyle(el); const lab = [...el.children].find((k) => k.tagName === 'LABEL' || /label/.test(String(k.className)));
      return `${cs.display} ${cs.flexDirection || ''} gap ${px(cs.rowGap)}/${px(cs.columnGap)} · label ${lab ? type(win.getComputedStyle(lab)) : '-'}`; },
  },
  metaLine: {
    pick: (doc) => doc.querySelectorAll('[class*="meta"], [class*="-note"], [class*="-sub"], [class*="hint"], [class*="caption"]'),
    sign: (el, win) => { const cs = win.getComputedStyle(el); return `${type(cs)} ${box(cs)}`; },
  },
};

const nameOf = (el) => `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ''}${el.classList.length ? `.${[...el.classList].slice(0, 2).join('.')}` : ''}`;

export function baseElementCensus(doc = document, win = window, examples = 2, limit = 12) {
  const out = {};
  for (const [kind, spec] of Object.entries(KINDS)) {
    const groups = new Map();
    for (const el of spec.pick(doc)) {
      const sig = spec.sign(el, win);
      if (!groups.has(sig)) groups.set(sig, []);
      groups.get(sig).push(el);
    }
    const looks = [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
    out[kind] = {
      elements: looks.reduce((n, [, els]) => n + els.length, 0),
      looks: looks.length,
      top: looks.slice(0, limit).map(([sig, els]) => ({ n: els.length, sig, e: els.slice(0, examples).map(nameOf) })),
    };
  }
  return out;
}
