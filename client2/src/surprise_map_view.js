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
import { mapSection, storedAxisTracks } from './surprise_map_core.js';
import { surpriseQuery } from './surprise_core.js';

/**
 * 🔴 THE FOCUS LINK, BUILT WITH THE SHARED SERIALISER AND NOT A SECOND ONE.
 *
 * This used to append `wafer` itself, because `surpriseQuery` whitelists parameters and did
 * not know that one. It knows it now (`surprise_core.js` serialises `wafer`, and
 * `parseSurpriseQuery` reads it back), so the fallback is gone rather than kept "just in
 * case": a branch nothing can reach is a place mutants rot, and this lane has already had
 * one mutant survive by pointing at exactly such a branch.
 *
 * If the serialiser ever stopped emitting it, the guard is an ASSERTION, not defensive code
 * here — the focus suite pins that every link carries exactly one `wafer`.
 *
 * The href is query-only — no scheme, no pathname — so the generic in-page router keeps it
 * in the document. A focus is a question, and one question is one URL.
 */
function waferHref(question, wafer) {
  return `?${surpriseQuery({ ...(question || {}), wafer })}`;
}

const VIEW = { width: 176, height: 176, padding: 3 };

//: 🔴 THE GUTTER THE AXIS NUMBERS LIVE IN, in DEVICE pixels (the canvas is drawn at 2x).
//: It is carved OUT of the same box rather than added to it, so the strip's 25 entries keep
//: their footprint and the CSS lane's `.sx-map { width: 210px }` still governs.
//:
//: `tickFont` is not shrinkable. Readability is a feature here and small type is worse than
//: no type — so when the numbers do not fit, FEWER of them are drawn (see `labelStep`),
//: never smaller ones.
const AXIS = Object.freeze({
  left: 26, top: 22, tickFont: 17, minCellForUnitGrid: 5, emphasisEvery: 5,
});

//: 🔴 THE PAINTER TAKES COLOURS, IT NEVER READS THEM (`painter.js` calls no
//: `getComputedStyle` by design). These are transcribed from `tokens.css` for the
//: two themes; a canvas cannot inherit a CSS variable, so the transcription is the
//: only way and keeping it beside the only call site is what keeps it findable.
const PALETTE = {
  // 🔴 THE GRID TONES ARE MEASURED, NOT PICKED BY EYE — three constraints pull against each
  // other and a swatch that looks fine in isolation loses one of them. Contrast ratios,
  // computed against this palette's own values:
  //
  //                     unit vs mask   5th vs mask   unit vs 5th   mark vs mask
  //   light             2.28           3.97          1.74          4.08
  //   dark              2.26           3.59          1.59          3.94
  //
  // Darkening the unit line further raises the first column and collapses the third — at
  // `#737f96` the every-fifth emphasis falls to 1.35 and stops reading as emphasis at all,
  // so the thing you actually count by disappears. These sit at the knee.
  light: { floor: '#d7dce4', mark: '#c22f2f', off: '#8a5a00', grid: '#8792a5', grid5: '#5f6a7d', tick: '#5a6478' },
  dark: { floor: '#36425f', mark: '#f87e7e', off: '#f6bd35', grid: '#6b7897', grid5: '#8f9bb8', tick: '#9aa6c0' },
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

/**
 * How many cells apart the printed numbers are.
 *
 * 🔴 THE TYPE NEVER SHRINKS; THE LABELS THIN OUT. A 23-wide core grid gives each cell about
 * 14 device px and a two-digit number needs roughly 20, so labelling every cell would
 * either overlap or force 8px type — and small type is worse than none. The GRID stays at
 * one cell either way, which is what makes counting possible; the numbers are the anchors
 * you count from.
 */
function labelStep(cell, font) {
  const need = font * 1.35;
  let step = 1;
  while (cell * step < need) step += 1;
  // Land on 1, 2, 5, 10 ... so the printed numbers are ones a human counts by.
  const nice = [1, 2, 5, 10, 20, 25, 50];
  for (const n of nice) if (n >= step) return n;
  return step;
}

/**
 * Coordinate axes and a one-cell grid, drawn with the raw context.
 *
 * 🔴 NOT A SECOND RENDERER. Every DIE is still placed by `map2/painter.js` off
 * `map2/seating.js`; this draws only chrome — rules and numerals — in the gutter and across
 * the same layout the painter used. No cell position is computed here.
 *
 * 🔴 THE NUMBERS ARE CELL COUNTS FROM THE ORIGIN. Nothing here multiplies by a pitch and
 * nothing emits a millimetre. `storedAxisTracks` supplies them from the seats' own source
 * cells, so they are the stored coordinates however the frame rotated the picture — and
 * when it cannot determine that mapping it returns null and the numbers are omitted rather
 * than guessed.
 */
function paintAxes(ctx, panel, layout, colors, tracks) {
  if (!layout || layout.empty || !layout.cell) return;
  const { cell, originX, originY, cols, rows, minX, minY } = layout;
  const right = originX + cols * cell;
  const bottom = originY + rows * cell;

  // ── the rules, ON TOP OF THE MASK but UNDER the defect marks ───────────────────────
  // That order is the whole answer to 「겹쳐도 읽혀야 한다」: the grid has to cross the
  // valid-die footprint to be countable there, and it must never cross a marked die,
  // because the mark is the figure and the grid is the scaffold. Nothing is sacrificed —
  // the mark's own edges are grid lines, so a run stays countable straight through it.
  const unit = cell >= AXIS.minCellForUnitGrid;
  ctx.lineWidth = 1;
  for (let i = 0; i <= cols; i++) {
    const strong = (minX + i) % AXIS.emphasisEvery === 0 || i === cols;
    if (!strong && !unit) continue;
    ctx.strokeStyle = strong ? colors.grid5 : colors.grid;
    ctx.beginPath();
    const x = Math.round(originX + i * cell) + 0.5;
    ctx.moveTo(x, originY); ctx.lineTo(x, bottom); ctx.stroke();
  }
  for (let j = 0; j <= rows; j++) {
    const strong = (minY + j) % AXIS.emphasisEvery === 0 || j === rows;
    if (!strong && !unit) continue;
    ctx.strokeStyle = strong ? colors.grid5 : colors.grid;
    ctx.beginPath();
    const y = Math.round(originY + j * cell) + 0.5;
    ctx.moveTo(originX, y); ctx.lineTo(right, y); ctx.stroke();
  }

  if (!tracks) return;
  // ── the numerals ──────────────────────────────────────────────────────────────────
  ctx.fillStyle = colors.tick;
  ctx.font = `${AXIS.tickFont}px ui-monospace, monospace`;
  const step = labelStep(cell, AXIS.tickFont);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  for (let i = 0; i < cols; i++) {
    const v = tracks.top.at.get(minX + i);
    if (v === undefined) continue;
    if (v % step !== 0 && i !== cols - 1 && i !== 0) continue;
    ctx.fillText(String(v), originX + (i + 0.5) * cell, originY - 4);
  }
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let j = 0; j < rows; j++) {
    const v = tracks.left.at.get(minY + j);
    if (v === undefined) continue;
    if (v % step !== 0 && j !== rows - 1 && j !== 0) continue;
    ctx.fillText(String(v), originX - 5, originY + (j + 0.5) * cell);
  }
  // 🔴 WHICH STORED AXIS EACH EDGE IS. Under a rotated frame the top edge carries stored
  // Y, and a corner that still said 「X」 would be the wrong caption on a right picture.
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  ctx.fillText(`${tracks.left.axis.toUpperCase()}↓`, 2, originY - 4);
  ctx.textAlign = 'right';
  ctx.fillText(`${tracks.top.axis.toUpperCase()}→`, originX - 5, AXIS.tickFont);
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
      // 🔴 THE GUTTER IS CARVED OUT, NOT ADDED ON. `layoutFor` is given the SHRUNKEN
      // viewport and its origin is then translated into the remaining box, so the die
      // arithmetic is still entirely the painter's — this shifts the window, it does not
      // recompute a single cell position.
      const fitted = layoutFor(panel.bounds, {
        width: VIEW.width * 2 - AXIS.left,
        height: VIEW.height * 2 - AXIS.top,
        padding: VIEW.padding * 2,
      });
      const layout = fitted.empty ? fitted : {
        ...fitted, originX: fitted.originX + AXIS.left, originY: fitted.originY + AXIS.top,
      };
      const colors = paletteFor(doc);
      surface.clear(VIEW.width * 2, VIEW.height * 2);
      try {
        paintSeating(surface, panel.floor, layout, colors.floor);
        // Order is load-bearing: mask, then the rules ON it, then the marks ON TOP of
        // everything — so the grid is countable across the footprint and can never sit
        // over a defect die. See `paintAxes`.
        paintAxes(ctx, panel, layout, colors, storedAxisTracks(panel));
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
 * A refused axis INSIDE a frame entry — one line, not a paragraph.
 *
 * 🔴 THE SAME SENTENCE 25 TIMES IS NOISE, AND READABILITY IS A FEATURE. Every entry
 * in a 25-wafer strip carries the same two unreachable axes, so the full sentence is
 * printed ONCE above the strip and each entry keeps a terse marker holding the axis's
 * place. Nothing is hidden — the axis is still named, still flagged, still counted.
 */
/**
 * ONE AGGREGATE SHEET — every marked wafer's chips overlaid on one coordinate system.
 *
 * 🔴 THE HEAT IS THE OVERLAP COUNT, AND THE OVERLAY IS IN STORED COORDINATES. See
 * `overlayOf` in the core for why that is measured rather than chosen: seating the cells
 * first drags the stage pattern from VMR 2.17 down to 1.20, i.e. to noise. Nothing here
 * calls `computeSeating`, and that omission is the feature.
 *
 * 🔴 AND THE GRID IS THE REGISTERED ONE. The sheet is the declared cols x rows; a cell with
 * no chips is drawn empty rather than the sheet being shrunk to fit the damage.
 */
function renderSheet(doc, sheet) {
  const box = el(doc, 'figure', `sx-sheet${sheet.ok ? '' : ' sx-sheet--refused'}`);
  attrs(box, {
    'data-sheet-axis': sheet.axis,
    'data-sheet-ok': sheet.ok ? '1' : '0',
    'data-sheet-wafers': String((sheet.wafers || []).length),
    'data-sheet-chips': String(sheet.chips || 0),
    'data-sheet-max': String(sheet.max || 0),
  });
  const cap = el(doc, 'figcaption', 'sx-sheet__cap');
  cap.appendChild(el(doc, 'span', 'sx-sheet__axis', sheet.label));
  if (sheet.ok) {
    // 🔴 THE GRID IS NAMED ON THE SHEET, because more than one grid inside an axis means
    // more than one sheet and the reader has to know which is which.
    const g = el(doc, 'span', 'sx-sheet__grid', `격자 ${sheet.cols}×${sheet.rows}`);
    g.setAttribute('data-sheet-grid', `${sheet.cols}x${sheet.rows}`);
    cap.appendChild(g);
  }
  cap.appendChild(el(doc, 'span', 'sx-sheet__n',
    `웨이퍼 ${(sheet.wafers || []).length}장 · 칩 ${sheet.chips || 0}`));
  box.appendChild(cap);

  if (!sheet.ok) {
    // No declared grid for this axis at this granularity. The chips are counted and their
    // coordinates are real; what is missing is a registered lattice, and this file does not
    // invent one — the standing constraint the whole screen is built on.
    const why = el(doc, 'p', 'sx-sheet__why',
      `${sheet.label}은 집계 시트를 그릴 등록 격자가 응답에 없습니다 — 칩 ${sheet.chips || 0}개의 `
      + '좌표는 실측이지만 올릴 격자가 없습니다'
      + (sheet.spans && sheet.spans.slots ? ` (프레임 ${sheet.spans.slots}장 분산`
        + (sheet.spans.lots > 1 ? ` · 랏 ${sheet.spans.lots}` : '') + ')' : ''));
    why.setAttribute('data-refusal', sheet.code || 'no_registered_frame');
    box.appendChild(why);
    return box;
  }

  const canvas = doc.createElement('canvas');
  attrs(canvas, {
    class: 'sx-sheet__canvas',
    width: String(VIEW.width * 2), height: String(VIEW.height * 2),
    role: 'img',
    'aria-label': `${sheet.label} 집계 — 웨이퍼 ${(sheet.wafers || []).length}장, 최대 겹침 ${sheet.max}`,
  });
  if (typeof canvas.getContext === 'function') {
    const ctx = canvas.getContext('2d');
    if (ctx) {
      const colors = paletteFor(doc);
      const bounds = { minX: 0, minY: 0, maxX: sheet.cols - 1, maxY: sheet.rows - 1, empty: false };
      const fitted = layoutFor(bounds, {
        width: VIEW.width * 2 - AXIS.left, height: VIEW.height * 2 - AXIS.top,
        padding: VIEW.padding * 2,
      });
      const layout = { ...fitted, originX: fitted.originX + AXIS.left, originY: fitted.originY + AXIS.top };
      ctx.clearRect(0, 0, VIEW.width * 2, VIEW.height * 2);
      // 🔴 A SINGLE-HUE RAMP, NOT A RAINBOW. Order has to be readable at a glance (more
      // overlap = stronger), and this repo already carries a measured lesson about hue
      // sweeps collapsing local contrast.
      for (const [k, v] of sheet.heat) {
        const parts = String(k).split(',');
        const x = Number(parts[0]); const y = Number(parts[1]);
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
        const t = sheet.max > 1 ? (v - 1) / (sheet.max - 1) : 1;
        ctx.fillStyle = heatColor(colors, t);
        ctx.fillRect(layout.originX + (x - bounds.minX) * layout.cell,
          layout.originY + (y - bounds.minY) * layout.cell,
          layout.cell, layout.cell);
      }
      // The rules go ON TOP here: on an aggregate the grid is how a position is read off
      // the sheet, and there are no individual marks for it to hide.
      paintAxes(ctx, null, layout, colors, identityTracks(bounds));
    }
  }
  box.appendChild(canvas);

  const foot = el(doc, 'div', 'sx-sheet__foot');
  foot.appendChild(el(doc, 'span', 'sx-sheet__stat',
    `최대 겹침 ${sheet.max}/${(sheet.wafers || []).length}`));
  foot.appendChild(el(doc, 'span', 'sx-sheet__stat', `점유 칸 ${sheet.cellCount}`));
  // 🔴 THE ORIENTATION MIX IS STATED. These are stage coordinates, so mixing rotations is
  // correct here and is what reveals the pattern — but the reader is told it happened.
  if ((sheet.orientations || []).length > 1) {
    const o = el(doc, 'span', 'sx-sheet__stat', `방향 ${sheet.orientations.length}종 혼재`);
    o.setAttribute('data-orientations', String(sheet.orientations.length));
    foot.appendChild(o);
  }
  if (sheet.unsettled > 0) {
    const u = el(doc, 'span', 'sx-sheet__gap', `방향 미확정 ${sheet.unsettled}장 제외`);
    u.setAttribute('data-unsettled', String(sheet.unsettled));
    foot.appendChild(u);
  }
  box.appendChild(foot);
  return box;
}

/** Stored coordinates ARE the sheet's own axes, so the labels are the indices themselves. */
function identityTracks(bounds) {
  const top = new Map(); const left = new Map();
  for (let x = bounds.minX; x <= bounds.maxX; x++) top.set(x, x);
  for (let y = bounds.minY; y <= bounds.maxY; y++) left.set(y, y);
  return { top: { axis: 'x', at: top }, left: { axis: 'y', at: left } };
}

function heatColor(colors, t) {
  // 1 -> the mask tone, max -> the mark tone. A straight sRGB interpolation is enough for an
  // ordered ramp and keeps both endpoints colours already on this screen.
  const a = colors.floor.replace('#', ''); const b = colors.mark.replace('#', '');
  const mix = (i) => Math.round(parseInt(a.substr(i, 2), 16)
    + (parseInt(b.substr(i, 2), 16) - parseInt(a.substr(i, 2), 16)) * t);
  return `rgb(${mix(0)},${mix(2)},${mix(4)})`;
}

/**
 * The whole map section.
 *
 * 🔴 THE POPULATION IS WHAT WAS MARKED, AND THE UNIT IS THE WAFER. There is no lot-count
 * gate here and no lot-count sentence: 「그냥 랏이란 단위를 잊으라 그래」. Two wafers across
 * two lots draw exactly as two wafers.
 */
export function renderAxisMaps(doc, model, maps, floors) {
  const box = el(doc, 'div', 'sx-maps');
  box.setAttribute('data-panel', 'maps');

  const section = mapSection(model, maps, floors);
  box.setAttribute('data-marked-wafers', String(section.wafers));
  box.setAttribute('data-sheet-count', String(section.sheets.length));

  if (!section.marked) {
    const hint = el(doc, 'p', 'sx-empty',
      '표에서 웨이퍼를 ☑ 마킹하면 좌표계마다 한 장씩, 마킹한 웨이퍼의 불량이 포개져 뜹니다.');
    hint.setAttribute('data-maps-empty', '1');
    box.appendChild(hint);
    return box;
  }

  const head = el(doc, 'p', 'sx-maps__head');
  head.setAttribute('data-population', String(section.wafers));
  head.textContent = `마킹 ${section.wafers}장 — 좌표계마다 한 장으로 포갭니다`
    + (section.pending ? ` · ${section.wafers - section.pending}/${section.wafers} 로드됨` : '');
  box.appendChild(head);

  const sheets = el(doc, 'div', 'sx-sheets sx-maprow__panels');
  sheets.setAttribute('data-panel', 'sheets');
  for (const sheet of section.sheets) sheets.appendChild(renderSheet(doc, sheet));
  box.appendChild(sheets);

  // 🔴 INDIVIDUAL FRAMES ARE DETAIL, NOT THE DEFAULT — and the cap is counted in WAFERS.
  if (section.focus) {
    const det = el(doc, 'div', 'sx-detail');
    det.setAttribute('data-detail-wafer', section.focus.row);
    det.appendChild(el(doc, 'p', 'sx-detail__head', `${section.focus.row} — 이 웨이퍼의 프레임`));
    const panels = el(doc, 'div', 'sx-maprow__panels');
    for (const p of section.focus.panels) panels.appendChild(renderPanel(doc, p));
    det.appendChild(panels);
    box.appendChild(det);
  } else if (section.wafers <= section.detailCap) {
    const pick = el(doc, 'p', 'sx-maps__pick');
    pick.setAttribute('data-detail-offer', String(section.wafers));
    pick.appendChild(el(doc, 'span', 'sx-maps__picklabel', '낱장으로 보려면 웨이퍼를 고르십시오: '));
    for (const m of section.members) {
      const a = el(doc, 'a', 'sx-waferpick', m.row);
      a.setAttribute('href', waferHref(model.question, m.row));
      a.setAttribute('data-wafer-focus', m.row);
      pick.appendChild(a);
    }
    box.appendChild(pick);
  } else {
    const many = el(doc, 'p', 'sx-maps__pick',
      `마킹 ${section.wafers}장 — 낱장 상세는 ${section.detailCap}장 이하에서 제공합니다 (집계 시트는 제한 없음)`);
    many.setAttribute('data-detail-capped', String(section.wafers));
    box.appendChild(many);
  }
  return box;
}
