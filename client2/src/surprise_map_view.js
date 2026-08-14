// ============================================================
// surprise_map_view.js — 3축 맵의 DOM. 캔버스는 «기존 렌더러»가 칠한다.
//
// `document` IS AN ARGUMENT. Scored under bare node by
// `tests/surprise_harness.mjs`, which is possible because the painting is
// guarded: a document stub has no `getContext`, so the structure and the
// refusal sentences are asserted without a canvas existing.
//
// 🔴 NO NEW RENDERER. `map2/painter.js` (`layoutFor`, `paintSeating`,
// `createCanvasSurface`) draws every die here, and `map2/seating.js` seated them.
// Both are already scored by their own harnesses; re-deriving either would be a
// second implementation of arithmetic the repo declares single-source.
//
// 🔴 CANVAS, NOT SVG, AND THAT IS A MEASURED CHOICE. `map2/main.js` records it:
// a production map runs to thousands of dies, so N copies of it as SVG is tens of
// thousands of nodes per repaint. This screen draws THREE per marked lot and the
// marked set is unbounded — exactly the case the note is about.
//
// 🔴 AND NOTHING IS DRAWN THAT WAS NOT SOURCED. A refused panel renders its
// reason as text and NO canvas at all. The mockup's circular grid does not exist
// in this file; there is no code path that invents a wafer.
// ============================================================

import { layoutFor, paintSeating, createCanvasSurface } from './map2/painter.js';
import { mapSection } from './surprise_map_core.js';
import { surpriseQuery, withSlot } from './surprise_core.js';

const VIEW = { width: 176, height: 176, padding: 3 };

//: 🔴 THE PAINTER TAKES COLOURS, IT NEVER READS THEM (`painter.js` calls no
//: `getComputedStyle` by design). These are transcribed from `tokens.css` for the
//: two themes; a canvas cannot inherit a CSS variable, so the transcription is the
//: only way and keeping it beside the only call site is what keeps it findable.
const PALETTE = {
  light: { floor: '#d7dce4', mark: '#c22f2f', off: '#8a5a00' },
  dark: { floor: '#36425f', mark: '#f87e7e', off: '#f6bd35' },
};

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function attrs(node, map) {
  for (const k of Object.keys(map)) {
    const v = map[k];
    if (v === null || v === undefined) continue;
    node.setAttribute(k, String(v));
  }
  return node;
}

function paletteFor(doc) {
  const root = doc && doc.documentElement;
  const theme = root && typeof root.getAttribute === 'function' ? root.getAttribute('data-theme') : null;
  return theme === 'dark' ? PALETTE.dark : PALETTE.light;
}

/**
 * One axis panel.
 *
 * A refusal is CONTENT: the axis keeps its heading and its reason, so a reader
 * comparing three axes can see which one is missing rather than finding two
 * pictures and a hole.
 */
function renderPanel(doc, panel) {
  const box = el(doc, 'figure',
    `sx-map${panel.ok ? '' : ' sx-map--refused'}${panel.unreachable ? ' sx-map--unreachable' : ''}`);
  attrs(box, {
    'data-axis': panel.axis,
    'data-axis-ok': panel.ok ? '1' : '0',
    'data-axis-code': panel.code || null,
    // 🔴 THE UNREACHABLE AXIS IS FLAGGED SEPARATELY FROM A FAILURE. "nobody built
    // the bridge" and "the fetch broke" are different facts and a reader deciding
    // whether to chase it needs to tell them apart.
    'data-unreachable': panel.unreachable ? '1' : null,
  });

  const cap = el(doc, 'figcaption', 'sx-map__cap');
  cap.appendChild(el(doc, 'span', 'sx-map__axis', panel.label));
  if (panel.hint) cap.appendChild(el(doc, 'span', 'sx-map__hint', panel.hint));
  box.appendChild(cap);

  if (!panel.ok) {
    const why = el(doc, 'p', 'sx-map__why', panel.why);
    why.setAttribute('data-refusal', panel.code || '');
    box.appendChild(why);
    if (panel.detail) box.appendChild(el(doc, 'p', 'sx-map__detail', panel.detail));
    // 🔴 AND NOTHING IS DRAWN. No canvas, no placeholder grid, no circle.
    return box;
  }

  const canvas = doc.createElement('canvas');
  attrs(canvas, {
    class: 'sx-map__canvas',
    width: String(VIEW.width * 2),
    height: String(VIEW.height * 2),
    role: 'img',
    'aria-label': `${panel.label} — 유효 다이 ${panel.counts.floor}칸, 불량 ${panel.counts.marked}칸`,
    'data-floor-cells': String(panel.counts.floor),
    'data-mark-cells': String(panel.counts.marked),
  });

  // Under a document stub there is no 2D context, and that is fine: the tree,
  // the counts and the sentences are what this screen is scored on.
  if (typeof canvas.getContext === 'function') {
    const ctx = canvas.getContext('2d');
    if (ctx) {
      const surface = createCanvasSurface(ctx);
      const layout = layoutFor(panel.bounds, {
        width: VIEW.width * 2, height: VIEW.height * 2, padding: VIEW.padding * 2,
      });
      const colors = paletteFor(doc);
      surface.clear(VIEW.width * 2, VIEW.height * 2);
      try {
        paintSeating(surface, panel.floor, layout, colors.floor);
        if (panel.marks) paintSeating(surface, panel.marks, layout, colors.mark);
      } catch (err) {
        // `paintSeating` throws when it could not place every seat — a loud
        // contract, and swallowing it silently would leave a partial wafer
        // looking complete.
        box.setAttribute('data-paint-error', String((err && err.message) || err));
      }
    }
  }
  box.appendChild(canvas);

  const foot = el(doc, 'div', 'sx-map__foot');
  const stat = (term, value, key) => {
    const s = el(doc, 'span', 'sx-map__stat');
    s.setAttribute('data-map-stat', key);
    s.appendChild(el(doc, 'span', 'sx-map__statn', String(value)));
    s.appendChild(el(doc, 'span', 'sx-map__statterm', term));
    foot.appendChild(s);
  };
  // 🔴 THE MASK IS ONLY COUNTED WHEN IT WAS APPLIED. Printing 「유효 다이 0」 for a
  // panel that never received a mask would read as a wafer with no good dies.
  if (panel.floor) stat('유효 다이', panel.counts.floor, 'floor');
  else if (panel.grid) stat('등록 격자', `${panel.grid.cols}×${panel.grid.rows}`, 'grid');
  stat('불량 칩', panel.counts.marked, 'marked');
  // `found`/`scanned` are the projection's own denominator — the chips this axis
  // could see at all. A defect count without it is a number with no claim.
  if (panel.counts.scanned !== null && panel.counts.scanned !== undefined) {
    stat('검사 칩', panel.counts.scanned, 'scanned');
  }
  if (panel.counts.offFloor > 0) {
    const off = el(doc, 'span', 'sx-map__off',
      `레퍼런스 밖 ${panel.counts.offFloor}칩 — 두 맵이 유효 다이를 다르게 봅니다`);
    off.setAttribute('data-off-floor', String(panel.counts.offFloor));
    foot.appendChild(off);
  }
  if (panel.counts.dropped > 0) {
    const drop = el(doc, 'span', 'sx-map__off', `좌표 불량 ${panel.counts.dropped}행 제외`);
    drop.setAttribute('data-dropped', String(panel.counts.dropped));
    foot.appendChild(drop);
  }
  box.appendChild(foot);

  if (panel.code) {
    const gap = el(doc, 'p', 'sx-map__why', panel.why);
    gap.setAttribute('data-refusal', panel.code);
    box.appendChild(gap);
  }

  const prov = el(doc, 'p', 'sx-map__prov');
  prov.setAttribute('data-provenance', panel.reference || 'none');
  prov.textContent = [
    panel.mapId ? `프레임 ${panel.mapId}` : '',
    panel.table ? `등록 ${panel.table}` : '',
    panel.reference ? `마스크 ${panel.reference}` : '마스크 미지정',
    '좌표 단위: 오리진 기준 칸수',
  ].filter(Boolean).join(' · ');
  box.appendChild(prov);
  return box;
}

/**
 * The whole map section — one row per marked lot, three axes across.
 *
 * 🔴 NOTHING MARKED IS NOT AN ERROR, it is the screen's resting state, and it
 * says what to do rather than showing an empty box.
 */
export function renderAxisMaps(doc, model, maps, floors) {
  const box = el(doc, 'div', 'sx-maps');
  box.setAttribute('data-panel', 'maps');

  const section = mapSection(model, maps, floors);
  box.setAttribute('data-marked-lots', String(section.marked));

  if (!section.marked) {
    const hint = el(doc, 'p', 'sx-empty', '표에서 랏을 ☑ 마킹하면 여기에 세 좌표계의 맵이 뜹니다.');
    hint.setAttribute('data-maps-empty', '1');
    box.appendChild(hint);
    return box;
  }

  for (const lot of section.lots) {
    const row = el(doc, 'div', 'sx-maprow');
    row.setAttribute('data-map-lot', lot.lot);

    const head = el(doc, 'div', 'sx-maprow__head');
    head.appendChild(el(doc, 'span', 'sx-maprow__lot', lot.lot));
    if (lot.slot) {
      const s = el(doc, 'span', 'sx-maprow__slot', `슬롯 ${lot.slot}`);
      s.setAttribute('data-served-slot', String(lot.slot));
      head.appendChild(s);
    }
    head.appendChild(el(doc, 'span', 'sx-maprow__hint', '마킹 해제는 표에서'));
    row.appendChild(head);

    // 🔴 THE SLOT STRIP. One lot is 25 bonding frames with DIFFERENT grids, so
    // "the lot's map" does not exist and a picture that averaged them would be a
    // wafer nobody made. This is anchors, not a mode and not a modal: the slot is
    // in the URL like every other part of the question, and the strip lists the
    // slots this lot ACTUALLY has rather than a range invented here.
    if (lot.slots && lot.slots.length) {
      const strip = el(doc, 'div', 'sx-slots');
      strip.setAttribute('data-panel', 'slots');
      strip.setAttribute('data-slot-count', String(lot.slots.length));
      strip.appendChild(el(doc, 'span', 'sx-slots__term', '슬롯'));
      for (const s of lot.slots) {
        const on = String(s.slot) === String(lot.slot);
        const a = el(doc, 'a', `sx-slot${on ? ' sx-slot--on' : ''}`, String(s.slot));
        a.setAttribute('href', `?${surpriseQuery(withSlot(model.question, s.slot))}`);
        a.setAttribute('data-slot', String(s.slot));
        if (s.cols !== null && s.rows !== null) {
          a.setAttribute('title', `${s.cols}×${s.rows}`);
        }
        if (on) a.setAttribute('aria-current', 'true');
        strip.appendChild(a);
      }
      // 🔴 WHY THE SLOT MATTERS IS THE SERVER'S SENTENCE, NOT A GUESS HERE. It
      // says the row spans several frames and that the grids differ per slot;
      // paraphrasing it would be this client asserting a fact it did not measure.
      const said = lot.panels.find((pn) => pn.code === 'frame_ambiguous_across_slots');
      const note = el(doc, 'span', 'sx-slots__note',
        (said && said.detail) || (said && said.why) || '슬롯마다 격자가 다릅니다');
      note.setAttribute('data-slot-note', said ? said.code : 'none');
      strip.appendChild(note);
      row.appendChild(strip);
    }

    if (lot.pending) {
      row.appendChild(el(doc, 'p', 'sx-map__why', lot.why));
      box.appendChild(row);
      continue;
    }
    if (!lot.panels.length) {
      const why = el(doc, 'p', 'sx-map__why', lot.why);
      why.setAttribute('data-refusal', 'no_axes');
      row.appendChild(why);
      box.appendChild(row);
      continue;
    }

    const panels = el(doc, 'div', 'sx-maprow__panels');
    for (const panel of lot.panels) panels.appendChild(renderPanel(doc, panel));
    row.appendChild(panels);
    box.appendChild(row);
  }
  return box;
}
