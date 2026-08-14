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
import { mapSection, frameSpanOf, waferLabelOf } from './surprise_map_core.js';

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
 * A refused axis INSIDE a frame entry — one line, not a paragraph.
 *
 * 🔴 THE SAME SENTENCE 25 TIMES IS NOISE, AND READABILITY IS A FEATURE. Every entry
 * in a 25-wafer strip carries the same two unreachable axes, so the full sentence is
 * printed ONCE above the strip and each entry keeps a terse marker holding the axis's
 * place. Nothing is hidden — the axis is still named, still flagged, still counted.
 */
function renderGap(doc, panel) {
  const gap = el(doc, 'p', 'sx-frame__gap');
  const span = frameSpanOf(panel);
  gap.setAttribute('data-axis', panel.axis);
  gap.setAttribute('data-axis-ok', '0');
  gap.setAttribute('data-axis-code', panel.code || '');
  if (panel.unreachable) gap.setAttribute('data-unreachable', '1');
  // 🔴 SLOTS AND LOTS ARE PRINTED SEPARATELY AND NEVER MULTIPLIED — see
  // `frameSpanOf`. The wire says which slots occur and which lots occur, not which
  // pairs, so a product would be a count of frames nobody registered.
  const parts = [panel.label];
  if (span.slots) {
    gap.setAttribute('data-span-slots', String(span.slots));
    parts.push(`프레임 슬롯 ${span.slots}`);
  }
  if (span.lots > 1) {
    gap.setAttribute('data-span-lots', String(span.lots));
    parts.push(`랏 ${span.lots}`);
  }
  if (!span.slots) parts.push(panel.why);
  gap.textContent = parts.join(' · ');
  return gap;
}

/**
 * ONE FRAME = ONE PICTURE = ONE BONDED BASE WAFER.
 *
 * 🔴 AND IT IS NOT A LINK. The strip is content, not navigation: nothing here is an
 * anchor, nothing carries an `href`, so selecting or scrolling it can never load a
 * page. The reader is not asked to choose — every matched frame is already drawn.
 */
function renderFrame(doc, frame, compact) {
  const box = el(doc, 'article', 'sx-frame');
  box.setAttribute('data-frame-slot', String(frame.slot));
  box.setAttribute('data-frame-key', String(frame.key));

  const cap = el(doc, 'header', 'sx-frame__cap');
  const label = waferLabelOf(frame.panels, frame.slot);
  const name = el(doc, 'span', 'sx-frame__wafer', label.text);
  // 🔴 WHERE THE NAME CAME FROM, ON THE ELEMENT. The owner asked for base WF id and
  // the route serves the frame key; recording which one is on screen keeps the day
  // the field lands from looking like the day the label changed for no reason.
  name.setAttribute('data-wafer-source', label.source);
  cap.appendChild(name);
  box.appendChild(cap);

  if (frame.pending) {
    const wait = el(doc, 'p', 'sx-frame__gap', '불러오는 중…');
    wait.setAttribute('data-frame-pending', '1');
    box.appendChild(wait);
    return box;
  }

  // 🔴 COMPACTION IS FOR REPETITION, AND A STRIP OF ONE HAS NONE. When this lot
  // resolves to a single frame the refused axes render in FULL — their own headings
  // and the server's own sentence — exactly as before the strip existed. Compacting
  // there would have cost information and bought nothing, which is what it did: it
  // dropped two axes' headings and replaced the server's sentence with a count.
  const drawn = (frame.panels || []).filter((p) => p.ok);
  const gaps = (frame.panels || []).filter((p) => !p.ok);
  // 🔴 THE OLD CLASS IS KEPT ALONGSIDE THE NEW ONE ON PURPOSE. `.sx-maprow__panels`
  // already carries the flex row this container wants, and the stylesheet belongs to
  // another lane — riding the existing rule means the strip is laid out correctly the
  // moment it ships instead of stacking unstyled while it waits for a CSS round.
  const panels = el(doc, 'div', 'sx-frame__panels sx-maprow__panels');
  for (const panel of drawn) panels.appendChild(renderPanel(doc, panel));
  if (!compact) for (const panel of gaps) panels.appendChild(renderPanel(doc, panel));
  box.appendChild(panels);
  if (compact) for (const panel of gaps) box.appendChild(renderGap(doc, panel));
  return box;
}

/**
 * The whole map section — one entry per MATCHED FRAME, each its own map.
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
    const hint = el(doc, 'p', 'sx-empty', '표에서 랏을 ☑ 마킹하면 여기에 그 랏의 웨이퍼 맵이 한 장씩 뜹니다.');
    hint.setAttribute('data-maps-empty', '1');
    box.appendChild(hint);
    return box;
  }

  for (const lot of section.lots) {
    const row = el(doc, 'div', 'sx-maprow');
    row.setAttribute('data-map-lot', lot.lot);

    const head = el(doc, 'div', 'sx-maprow__head');
    head.appendChild(el(doc, 'span', 'sx-maprow__lot', lot.lot));
    row.appendChild(head);

    if (lot.pending) {
      row.appendChild(el(doc, 'p', 'sx-map__why', lot.why));
      box.appendChild(row);
      continue;
    }

    // 🔴 THE CASE THAT CANNOT BE OPENED SAYS SO, AND STILL SHOWS WHAT IT HAS. The
    // matched frames span several lots and the wire does not say which (lot, slot)
    // pairs are real — so nothing is enumerated and the served refusals keep their
    // places, each axis still named. Picking one lot would be the fiction.
    if (lot.plan && (lot.plan.kind === 'blocked' || lot.plan.kind === 'no_axes')) {
      const why = el(doc, 'p', 'sx-map__why', lot.plan.why);
      why.setAttribute('data-refusal', lot.plan.code || 'no_axes');
      row.appendChild(why);
      const panels = el(doc, 'div', 'sx-maprow__panels');
      for (const panel of lot.served || []) panels.appendChild(renderPanel(doc, panel));
      row.appendChild(panels);
      box.appendChild(row);
      continue;
    }

    const frames = lot.frames || [];
    const ready = frames.filter((f) => !f.pending).length;
    // 🔴 THE SERVER'S SENTENCE, ONCE, ABOVE THE STRIP. It is the refusal that
    // actually happened — this screen does not weaken it, it answers it by drawing
    // every frame it named. Paraphrasing would be asserting a fact not measured here.
    const said = frames.map((f) => (f.panels || []).find((p) => p.code === 'frame_ambiguous_across_slots'))
      .find(Boolean);
    if (frames.length > 1) {
      const note = el(doc, 'p', 'sx-maprow__note');
      note.setAttribute('data-frame-total', String(frames.length));
      note.setAttribute('data-frame-ready', String(ready));
      note.setAttribute('data-strip-axis', (lot.plan && lot.plan.axis) || '');
      note.textContent = `${(lot.plan && lot.plan.label) || ''} 프레임 ${frames.length}장 — 한 장씩`
        + (ready < frames.length ? ` · ${ready}/${frames.length} 로드됨` : '');
      row.appendChild(note);
      if (said && said.detail) {
        const server = el(doc, 'p', 'sx-maprow__served', said.detail);
        server.setAttribute('data-refusal', said.code);
        row.appendChild(server);
      }
    }

    // Same reasoning as `sx-frame__panels`: ride the existing flex rule so the strip
    // lays out on arrival, and let the CSS lane refine `.sx-strip` afterwards.
    const strip = el(doc, 'div', 'sx-strip sx-maprow__panels');
    strip.setAttribute('data-panel', 'frames');
    strip.setAttribute('data-frame-count', String(frames.length));
    for (const frame of frames) strip.appendChild(renderFrame(doc, frame, frames.length > 1));
    row.appendChild(strip);
    box.appendChild(row);
  }
  return box;
}
