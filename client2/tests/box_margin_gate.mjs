// BOX MARGIN GATE — the box owns its margin (lead 482e9956f, owner 09-26 「박스 기본 마진 아예 고정
// 스타일로 박아」). Runs IN the page: there is no headless browser here, and a margin is a
// rendered fact. Every admin section body and Overview box body has ONE padding (10.2 · 13.6), and
// what sits in it writes no outer space of its own — its leftmost glyph starts at wall + 13.6
// (plus a table cell's or a control's own padding, which is inside the part, not around it).
//
// Run in the admin page (the built bundle):  (await import(<this file>)).boxMarginGate()
//                                            (await import(<this file>)).boxMarginMutants()

export const BODIES = '.section-body, .ov-section-body, .ov-row-body';
const PAD = { t: 10.2, r: 13.6, b: 10.2, l: 13.6 };
// Elements whose own padding sits between their edge and their text on purpose.
const INNER = new Set(['TD', 'TH', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'SUMMARY', 'OPTION']);

const px = (v) => parseFloat(v) || 0;

function visible(el, win) {
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return false;
  const cs = win.getComputedStyle(el);
  return cs.visibility !== 'hidden' && cs.position !== 'absolute' && cs.position !== 'fixed';
}

function boxName(body) {
  const box = body.closest('.stage-section, .ov-section');
  return (box && box.id) || body.id || body.className;
}

// Any border (a row's separator starts at the row's left) or a fill.
const drawsEdge = (cs) => ['Top', 'Right', 'Bottom', 'Left'].some((s) => px(cs[`border${s}Width`]) > 0)
  || !/^(transparent|rgba\(0, 0, 0, 0\))$/.test(cs.backgroundColor);

/** Where the ink starts in `kid`: the smallest (glyph left − the paddings it sits inside on
 *  purpose) over its texts, or the left of a mark it draws (a dot, a card's edge, an icon).
 *  Centred text is not a margin and is not counted. */
function leftmostInk(kid, doc, win) {
  let best = null;
  const take = (at, what) => { if (best === null || at < best.at) best = { at, text: what }; };
  for (const el of kid.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (drawsEdge(win.getComputedStyle(el)) || /^(svg|img|canvas|input|select|textarea|button)$/i.test(el.tagName)) {
      take(r.left, `<${el.tagName.toLowerCase()}>`);
    }
  }
  const walker = doc.createTreeWalker(kid, 4 /* NodeFilter.SHOW_TEXT */);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.textContent.trim()) continue;
    if (win.getComputedStyle(node.parentElement).textAlign === 'center') continue;
    const range = doc.createRange();
    range.selectNodeContents(node);
    const rect = [...range.getClientRects()].find((r) => r.width > 0 && r.height > 0);
    if (!rect) continue;
    // Padding is «inside» only where something draws the edge it is measured from — a cell, a
    // control, an inline chip, a bordered or filled card. On an invisible wrapper it is indentation:
    // a second margin.
    let allowed = 0;
    for (let el = node.parentElement; el; el = el.parentElement) {
      const cs = win.getComputedStyle(el);
      if (INNER.has(el.tagName) || /^inline/.test(cs.display) || drawsEdge(cs)) {
        allowed += px(cs.paddingLeft) + px(cs.borderLeftWidth);
      }
      if (el === kid) break;
    }
    take(rect.left - allowed, node.textContent.trim().slice(0, 24));
  }
  return best;
}

export function boxMarginGate(doc = document, win = window, tol = 1) {
  const out = { bodies: 0, hidden: 0, children: 0, bad: [] };
  for (const body of doc.querySelectorAll(BODIES)) {
    out.bodies++;
    const r = body.getBoundingClientRect();
    if (!r.width || !r.height) { out.hidden++; continue; }
    const cs = win.getComputedStyle(body);
    const box = boxName(body);
    const pad = { t: px(cs.paddingTop), r: px(cs.paddingRight), b: px(cs.paddingBottom), l: px(cs.paddingLeft) };
    if (Object.keys(PAD).some((k) => Math.abs(pad[k] - PAD[k]) > 0.05)) {
      out.bad.push({ box, what: 'body padding is not the one rule', saw: pad });
    }
    const wall = { l: r.left + px(cs.borderLeftWidth), r: r.right - px(cs.borderRightWidth),
      t: r.top + px(cs.borderTopWidth), b: r.bottom - px(cs.borderBottomWidth) };
    const scrolls = body.scrollWidth > body.clientWidth + 1;
    const kids = [...body.children].filter((el) => visible(el, win));
    kids.forEach((kid, i) => {
      out.children++;
      const k = kid.getBoundingClientRect();
      const who = `${kid.tagName.toLowerCase()}${kid.id ? `#${kid.id}` : ''}${kid.classList[0] ? `.${kid.classList[0]}` : ''}`;
      const flag = (what, saw) => out.bad.push({ box, child: who, what, saw: Math.round(saw * 10) / 10 });
      if (k.left < wall.l + PAD.l - tol) flag('starts inside the left padding', k.left - wall.l);
      if (!scrolls && k.right > wall.r - PAD.r + tol) flag('ends inside the right padding', wall.r - k.right);
      if (i === 0 && k.top < wall.t + PAD.t - tol) flag('starts inside the top padding', k.top - wall.t);
      if (i === kids.length - 1 && k.bottom > wall.b - PAD.b + tol) flag('ends inside the bottom padding', wall.b - k.bottom);
      const g = leftmostInk(kid, doc, win);
      if (g && g.at - (wall.l + PAD.l) > tol) flag(`a second margin before "${g.text}"`, g.at - wall.l);
    });
  }
  return out;
}

/** The census the lead asked for: every first-level child of every box body (hidden ones too)
 *  and the outer space it — or the part root in it — writes. A child or root that draws its own
 *  edge (a banner, a card) keeps its padding: that space is inside its edge. */
export function boxMarginCensus(doc = document, win = window) {
  const sides = (el, p) => ['Top', 'Right', 'Bottom', 'Left'].map((s) => px(win.getComputedStyle(el)[`${p}${s}`]));
  const rows = [];
  let children = 0;
  for (const body of doc.querySelectorAll(BODIES)) {
    for (const kid of body.children) {
      children++;
      for (const el of [kid, kid.firstElementChild].filter(Boolean)) {
        const pad = sides(el, 'padding');
        const margin = sides(el, 'margin');
        // The box's own gap between its children is not the child's margin.
        if (el === kid && kid.previousElementSibling && Math.abs(margin[0] - PAD.t) < 0.05) margin[0] = 0;
        const edge = drawsEdge(win.getComputedStyle(el));
        if ((!edge && pad.some(Boolean)) || margin.some(Boolean)) {
          rows.push({ box: boxName(body), el: `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ''}.${String(el.className).split(' ').join('.')}`,
            padding: edge ? 'inside its edge' : pad.join(' '), margin: margin.join(' ') });
        }
      }
    }
  }
  return { bodies: doc.querySelectorAll(BODIES).length, children, writesOuterSpace: rows.length, rows };
}

/** The gate must go red when the rule goes and when one part writes its own outer padding again. */
export function boxMarginMutants(doc = document, win = window) {
  const cases = [
    ['body padding removed', `${BODIES} { padding: 0 !important; }`],
    ['one part writes its outer padding again', '.chain-queue-panel { padding: 10.2px 13.6px !important; }'],
  ];
  return cases.map(([name, css]) => {
    const style = doc.createElement('style');
    style.textContent = css;
    doc.head.appendChild(style);
    const res = boxMarginGate(doc, win);
    style.remove();
    return { name, caught: res.bad.length > 0, bad: res.bad.length };
  });
}
