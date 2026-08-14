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
import { surpriseQuery } from './surprise_core.js';

/**
 * 🔴 THE FOCUS LINK, BUILT WITH THE SHARED SERIALISER AND NOT A SECOND ONE.
 *
 * `surpriseQuery` whitelists the parameters it knows, and `wafer` is not yet among them —
 * so the one parameter it drops is appended here, and ONLY if it did not already emit it.
 * The day the serialiser learns `wafer` this keeps producing exactly one of it, which is
 * the difference between a seam and a duplicate parameter that silently wins.
 *
 * The href is query-only — no scheme, no pathname — so the generic in-page router keeps it
 * in the document. A focus is a question, and one question is one URL.
 */
function waferHref(question, wafer) {
  const base = surpriseQuery({ ...(question || {}), wafer });
  if (/(^|&)wafer=/.test(base)) return `?${base}`;
  return wafer ? `?${base}&wafer=${encodeURIComponent(wafer)}` : `?${base}`;
}

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
function renderFrame(doc, frame, compact, question) {
  const box = el(doc, 'article', 'sx-frame');
  box.setAttribute('data-frame-slot', String(frame.slot));
  box.setAttribute('data-frame-key', String(frame.key));

  const cap = el(doc, 'header', 'sx-frame__cap');
  const label = waferLabelOf(frame.panels, frame.slot);
  // 🔴 A WAFER THAT CANNOT BE NAMED CANNOT BE FOCUSED BY NAME, AND IT SAYS SO.
  // The focus address is the base WF id; 120 of the 2,695 frames on this box have no base
  // identity at all (the five `BS-2601-*` lots), so there is no value a `?wafer=` could
  // carry for them. Those entries render as text with a stated reason rather than as a
  // link that would resolve to nothing — 「눌러도 아무 일이 없다」 is the worst answer.
  const focusable = label.source === 'served';
  const name = el(doc, focusable ? 'a' : 'span', 'sx-frame__wafer', label.text);
  // 🔴 WHERE THE NAME CAME FROM, ON THE ELEMENT. The owner asked for base WF id and
  // the route serves the frame key; recording which one is on screen keeps the day
  // the field lands from looking like the day the label changed for no reason.
  name.setAttribute('data-wafer-source', label.source);
  if (focusable) {
    name.setAttribute('href', waferHref(question, label.text));
    name.setAttribute('data-wafer-focus', label.text);
  } else {
    name.setAttribute('data-focusable', '0');
  }
  cap.appendChild(name);
  if (!focusable) {
    const no = el(doc, 'span', 'sx-frame__nofocus', '식별자 없음 — 초점 불가');
    no.setAttribute('data-no-identity', '1');
    cap.appendChild(no);
  }
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
 * One focused wafer: the heading that says what is on screen, and the FAN-IN.
 *
 * 🔴 THE FAN-IN IS NAMED AND COUNTED, NEVER PAIRED INTO A GRID. See `fanInOf`: the wire
 * gives which source lots occur and which slots occur, not which pairs, so the lots are
 * listed BY NAME and the slot count stands beside them as its own number. With two source
 * lots nothing is enumerated at all and the row says why.
 */
function renderFocus(doc, lot, question) {
  const f = lot.focus;
  const box = el(doc, 'div', 'sx-focus');
  box.setAttribute('data-panel', 'focus');
  box.setAttribute('data-focus-wafer', String(f.wafer));
  box.setAttribute('data-focus-found', f.found ? '1' : '0');

  const head = el(doc, 'div', 'sx-focus__head');
  head.appendChild(el(doc, 'span', 'sx-focus__wafer', f.wafer));
  // Leaving focus is the same question minus one parameter — an in-page link, not a mode
  // toggle, so the way back is the address bar's way back.
  const back = el(doc, 'a', 'sx-focus__back', `전체 ${f.total}장 보기`);
  back.setAttribute('href', waferHref(question, ''));
  back.setAttribute('data-focus-clear', '1');
  head.appendChild(back);
  box.appendChild(head);

  if (!f.found) {
    // 🔴 「아직 못 찾았다」 AND 「이 랏에 없다」 ARE DIFFERENT ANSWERS, and the reader acts
    // differently on them, so the progress that separates them is printed rather than one
    // spinner standing for both.
    const why = el(doc, 'p', 'sx-focus__why', f.scanning
      ? `웨이퍼 찾는 중… ${f.scanned}/${f.total} 프레임 확인`
      : `이 랏의 ${f.total}장 어디에도 ${f.wafer}가 없습니다`);
    why.setAttribute('data-focus-state', f.scanning ? 'scanning' : 'absent');
    box.appendChild(why);
    return box;
  }

  const list = el(doc, 'ul', 'sx-focus__fanin');
  list.setAttribute('data-fanin-count', String(f.fanIn.length));
  for (const src of f.fanIn) {
    const li = el(doc, 'li', 'sx-focus__src');
    li.setAttribute('data-fanin-axis', src.axis);
    li.appendChild(el(doc, 'span', 'sx-focus__srcaxis', src.label));
    if (src.unreachable || !src.slots) {
      li.appendChild(el(doc, 'span', 'sx-focus__srcwhy', src.why));
      list.appendChild(li);
      continue;
    }
    // Lots BY NAME — the reader can go look them up — and the slot count beside them.
    const lots = el(doc, 'span', 'sx-focus__srclots', src.lots.join(' · '));
    lots.setAttribute('data-fanin-lots', String(src.lots.length));
    li.appendChild(lots);
    const n = el(doc, 'span', 'sx-focus__srcn', `프레임 ${src.slots}장`);
    n.setAttribute('data-fanin-slots', String(src.slots));
    li.appendChild(n);
    const chips = el(doc, 'span', 'sx-focus__srcchips', `칩 ${src.chips}`);
    chips.setAttribute('data-fanin-chips', String(src.chips));
    li.appendChild(chips);
    if (!src.pairable) {
      // 🔴 THE PRODUCT IS NOT COMPUTED AND THE REFUSAL SAYS SO IN THOSE WORDS.
      const no = el(doc, 'span', 'sx-focus__srcgap',
        `랏 ${src.lots.length}개 — 어느 랏의 어느 슬롯인지 응답에 없어 한 장씩 세지 않습니다`);
      no.setAttribute('data-fanin-unpairable', '1');
      li.appendChild(no);
    }
    list.appendChild(li);
  }
  box.appendChild(list);
  // The one thing the response cannot answer, stated once rather than implied by absence.
  const gap = el(doc, 'p', 'sx-focus__gap',
    '칩마다 어느 소스 프레임에서 왔는지는 응답에 없습니다 — 소스별로 나눠 그리지 않습니다.');
  gap.setAttribute('data-fanin-attribution', 'absent');
  box.appendChild(gap);
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

  // 🔴 SEVERAL LOTS: COUNT, DO NOT DRAW — AND SAY THE COUNT OUT LOUD. Five marked lots is
  // 125 maps and 12,283px of page, which is the strip answering a question nobody asked:
  // marking several lots asks how they DIFFER, and that is the contrast panel's answer.
  // P0 item 6 governs the form — 「접힌/잘린 내용은 「아래 N건」류 존재 표시 필수 —
  // 스크롤을 줄이는 건 배치이지 은닉이 아니다」 — so the real frame total is printed and
  // nothing is quietly drawn instead.
  if (section.suppressed) {
    const sum = el(doc, 'div', 'sx-mapsum');
    sum.setAttribute('data-map-summary', '1');
    sum.setAttribute('data-frame-total', String(section.frameTotal));
    sum.setAttribute('data-marked-lots', String(section.marked));
    sum.appendChild(el(doc, 'p', 'sx-mapsum__why', section.suppressedWhy));

    const list = el(doc, 'ul', 'sx-mapsum__list');
    for (const lot of section.lots) {
      const li = el(doc, 'li', 'sx-mapsum__row');
      li.setAttribute('data-map-lot', lot.lot);
      li.appendChild(el(doc, 'span', 'sx-mapsum__lot', lot.lot));
      if (lot.pending) {
        li.appendChild(el(doc, 'span', 'sx-mapsum__n', '세는 중…'));
      } else {
        const n = lot.counts ? lot.counts.frames : 0;
        const c = el(doc, 'span', 'sx-mapsum__n', `프레임 ${n}장`);
        c.setAttribute('data-frame-count', String(n));
        li.appendChild(c);
        // An axis nobody can reach is the one fact lost by not drawing the panels, so it
        // survives into the summary rather than disappearing with them.
        if (lot.counts && lot.counts.unreachable > 0) {
          const u = el(doc, 'span', 'sx-mapsum__gap',
            `연결 없는 축 ${lot.counts.unreachable}/${lot.counts.axes}`);
          u.setAttribute('data-unreachable-axes', String(lot.counts.unreachable));
          li.appendChild(u);
        }
      }
      list.appendChild(li);
    }
    sum.appendChild(list);

    // 🔴 THE EXISTENCE STATEMENT, IN THE FORM THE BRIEF NAMES. Not 「몇 장 더」 — the exact
    // number of frames that exist and are not on screen, plus how to open them.
    const more = el(doc, 'p', 'sx-mapsum__more',
      `아래 ${section.frameTotal}건 미표시 — 랏 하나만 마킹하면 그 랏의 웨이퍼 맵이 한 장씩 펼쳐집니다.`);
    more.setAttribute('data-hidden-frames', String(section.frameTotal));
    sum.appendChild(more);
    box.appendChild(sum);
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
    // 🔴 FOCUS HEADS THE ROW, because it changes what the rest of the row means: the strip
    // below is one wafer, not the lot's 25, and the reader must know that before reading it.
    if (lot.focus) row.appendChild(renderFocus(doc, lot, model.question));
    // 🔴 THE SERVER'S SENTENCE, ONCE, ABOVE THE STRIP. It is the refusal that
    // actually happened — this screen does not weaken it, it answers it by drawing
    // every frame it named. Paraphrasing would be asserting a fact not measured here.
    const said = frames.map((f) => (f.panels || []).find((p) => p.code === 'frame_ambiguous_across_slots'))
      .find(Boolean);
    // Under focus the strip is deliberately one frame, so the 「N장 — 한 장씩」 note would
    // be describing a strip that is not on screen.
    if (frames.length > 1 && !lot.focus) {
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
    for (const frame of frames) {
      strip.appendChild(renderFrame(doc, frame, frames.length > 1, model.question));
    }
    row.appendChild(strip);
    box.appendChild(row);
  }
  return box;
}
