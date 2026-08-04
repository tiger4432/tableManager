// ═══════════════════════════════════════════════════════════════════════════════
// LAYER (10) PAINTING -- receives seating, paints. MAKES NOTHING.
//
// (MAP_ALIGNMENT_SPEC 0.2 layer 10: "④ 좌석 결과만 받아 픽셀로 칠함 / 아무것도 만들지 않음".)
//
// 🔴 HOW THIS RENDERER IS MADE INCAPABLE OF LOSING A CELL. Not by being careful about the
//    order of a bounds check and a registration line -- by having no bounds check at all. The
//    scale is derived from the seating's own bounds, so the drawing window is BY CONSTRUCTION
//    the window that contains every seat. There is no "outside the canvas" case for a
//    `continue` to guard, because no seat can be outside it.
//
//    And the accounting is returned rather than assumed: `paintSeating` counts what it drew
//    and throws if that is not every seat it was handed. A renderer that quietly draws fewer
//    rectangles than it was given is the legacy failure wearing new clothes.
//
// 🔴 NOTHING DOWNSTREAM MAY READ THIS MODULE'S OUTPUT AS DATA. The return value is render
//    statistics for the harness and for a diagnostics line. Save payloads and the numbers on
//    screen come from seating and from the scoring payload, never from here.
//
// THE SURFACE IS AN INTERFACE, NOT A CANVAS. `paintSeating` takes an object with `fillRect`
// and `strokeRect`. In the browser that is a thin wrapper over a 2D context; in a harness it
// is a recorder. That is what makes the drawing layer importable without a DOM.
//
// VISUAL WEIGHT IS DELIBERATELY INVERTED FROM INSTINCT: agreement is the quiet ground, the
// MISMATCH is the figure and is drawn last. The primary channel is shape -- whether the misses
// cluster on an asymmetric feature or lie as a crescent along one edge, because the crescent
// is a direction vector. Drawing agreement loudly buries exactly that.
// ═══════════════════════════════════════════════════════════════════════════════

import { unionBounds } from './seating.js';

/** Wrap a real 2D context. The only function in this file that knows what a canvas is. */
export function createCanvasSurface(ctx) {
  return {
    clear(w, h) { ctx.clearRect(0, 0, w, h); },
    fillRect(x, y, w, h, color) { ctx.fillStyle = color; ctx.fillRect(x, y, w, h); },
    strokeRect(x, y, w, h, color, lineWidth) {
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth || 1;
      ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    },
  };
}

/** A surface that records instead of drawing, so the paint path is scorable by `import`. */
export function createRecordingSurface() {
  const ops = [];
  return {
    ops,
    clear(w, h) { ops.push({ op: 'clear', w, h }); },
    fillRect(x, y, w, h, color) { ops.push({ op: 'fill', x, y, w, h, color }); },
    strokeRect(x, y, w, h, color) { ops.push({ op: 'stroke', x, y, w, h, color }); },
  };
}

/**
 * Pure geometry: bounds + viewport => how big one die is and where the grid starts.
 * Isotropic on purpose (one scale for both axes), so a die is a square and the wafer outline
 * stays a circle rather than an ellipse.
 */
export function layoutFor(bounds, viewport) {
  if (!bounds || bounds.empty) {
    return Object.freeze({ cell: 0, originX: 0, originY: 0, cols: 0, rows: 0, empty: true });
  }
  const cols = bounds.maxX - bounds.minX + 1;
  const rows = bounds.maxY - bounds.minY + 1;
  const pad = Math.max(0, Number(viewport.padding) || 0);
  const usableW = Math.max(0, viewport.width - pad * 2);
  const usableH = Math.max(0, viewport.height - pad * 2);
  const cell = Math.max(0, Math.min(usableW / cols, usableH / rows));
  return Object.freeze({
    cell,
    cols,
    rows,
    empty: false,
    // Centre the grid in whatever room is left over on the longer axis.
    originX: pad + (usableW - cell * cols) / 2,
    originY: pad + (usableH - cell * rows) / 2,
    minX: bounds.minX,
    minY: bounds.minY,
  });
}

/** Pixels per die under this layout. The shape channel needs roughly 8 to stay readable. */
export function pxPerDie(layout) {
  return layout && !layout.empty ? layout.cell : 0;
}

function rectOf(layout, seat) {
  return {
    x: layout.originX + (seat.x - layout.minX) * layout.cell,
    y: layout.originY + (seat.y - layout.minY) * layout.cell,
    w: layout.cell,
    h: layout.cell,
  };
}

/**
 * Paint one seating with one colour.
 * @returns {{painted:number, total:number}} and throws if they differ.
 */
export function paintSeating(surface, seating, layout, color, mode) {
  let painted = 0;
  for (const seat of seating.seats) {
    const r = rectOf(layout, seat);
    if (mode === 'ring') surface.strokeRect(r.x, r.y, r.w, r.h, color);
    else surface.fillRect(r.x, r.y, r.w, r.h, color);
    painted++;
  }
  if (painted !== seating.seatCount) {
    throw new Error(
      `painter lost a cell: painted ${painted} of ${seating.seatCount}. `
      + 'The renderer may not filter; scaling is fitted to the seating bounds precisely so '
      + 'that no seat can fall outside the drawing window.');
  }
  return Object.freeze({ painted, total: seating.seatCount });
}

/**
 * The alignment picture: floor, then agreement, then the coverage gap as a ring, then the
 * mismatch at full strength LAST so the error shape reads as the figure.
 *
 * @param {object} palette  semantic colours resolved by the composition root from CSS tokens.
 *        Passed in, never read from the document here -- this module has no `getComputedStyle`.
 * @returns {{painted:number, total:number, pxPerDie:number}}
 */
export function paintComparison(surface, parts, viewport, palette) {
  const { floor, source, comparison } = parts;
  const bounds = unionBounds(floor ? floor.bounds : null, source ? source.bounds : null);
  const layout = layoutFor(bounds, viewport);
  surface.clear(viewport.width, viewport.height);
  if (layout.empty) return Object.freeze({ painted: 0, total: 0, pxPerDie: 0 });

  let painted = 0;
  let total = 0;

  if (floor) {
    total += floor.seatCount;
    painted += paintSeating(surface, floor, layout, palette.floor).painted;
  }
  if (source && comparison) {
    // Agreement first and quiet: it is the ground, not the news.
    painted += paintGroup(surface, comparison.agree, layout, palette.agree, 'fill');
    // A coverage gap is not a disagreement and must not read as one.
    painted += paintGroup(surface, comparison.floorOnly, layout, palette.gap, 'ring');
    // Drawn last, full strength.
    painted += paintGroup(surface, comparison.sourceOnly, layout, palette.mismatch, 'fill');
    total += comparison.agree.length + comparison.floorOnly.length + comparison.sourceOnly.length;
  } else if (source) {
    // State 3: we genuinely know where this source's cells are; what we do not know is how
    // they relate to anything. Drawn alone, neutral, with no floor beneath -- that picture is
    // an honest statement of exactly that, not a decoration.
    total += source.seatCount;
    painted += paintSeating(surface, source, layout, palette.unrelated).painted;
  }

  return Object.freeze({ painted, total, pxPerDie: pxPerDie(layout) });
}

function paintGroup(surface, seats, layout, color, mode) {
  let n = 0;
  for (const seat of seats) {
    const r = rectOf(layout, seat);
    if (mode === 'ring') surface.strokeRect(r.x, r.y, r.w, r.h, color);
    else surface.fillRect(r.x, r.y, r.w, r.h, color);
    n++;
  }
  return n;
}

/** State 1: the frame skeleton and nothing else. No marks, and above all no numerals. */
export function paintSkeleton(surface, viewport, palette) {
  surface.clear(viewport.width, viewport.height);
  surface.strokeRect(8, 8, viewport.width - 16, viewport.height - 16, palette.skeleton);
  return Object.freeze({ painted: 0, total: 0, pxPerDie: 0 });
}
