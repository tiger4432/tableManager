// ============================================================
// ontology_structure_view.js — the type-level structure view as DOM + SVG.
//
// `document` IS AN ARGUMENT, not a global — same contract as
// `ledger_trace_view.js` and `case_control_view.js`, so the harness drives the
// REAL renderer under bare node and asserts what reaches the screen. Everything
// here builds nodes and sets `textContent`; nothing touches `innerHTML`, so a
// predicate name or a config term out of the server can never become markup.
//
// 🔴 NO NEW GRAPH LIBRARY, AND NO NEW CANVAS. `graph_viewer.js` owns the
// INSTANCE graph and draws it on a 2D canvas with a force layout — the right
// tool for an unknown, large, pannable node set. This graph is the vocabulary:
// a dozen nodes, fixed, and every one of them carries KOREAN TEXT that has to be
// readable and selectable. Canvas text is neither, and hit-testing it by hand
// would be a second implementation of what an `<a>` already does. So this is
// inline SVG built by hand — no dependency added, and the layout is the pure
// geometry in `ontology_structure_core.js`.
//
// 🔴 NO FORM CONTROLS. Every navigation is an anchor (`?view=structure&…`), so
// the layer filter and the selected edge are in the URL and a structure the owner
// is looking at pastes into a message. `ledger.html` still carries exactly one
// input, the lineage box it always had.
//
// 🔴 READABILITY IS A FUNCTION. Node type is 17px, the detail list is 15px, and
// nothing on this screen is below 13px. The SVG has a `min-width` and scrolls
// horizontally inside its own box rather than scaling the type down.
// ============================================================

// 🔴 THIS MODULE DOES NOT IMPORT ITS OWN STYLESHEET, AND THAT IS DELIBERATE.
//   The obvious move when the `os-*` rules left `ledger.html` was `import './ontology_structure.css'`
//   right here, so both hosts got it through the module graph. It was tried and reverted: this
//   file is imported by `tests/ontology_structure_harness.mjs` in BARE NODE, which has no CSS
//   loader, so the import turned the whole harness into ERR_UNKNOWN_FILE_EXTENSION. Being
//   importable outside a bundler is not an accident of this module — it is the property that
//   lets the harness drive the real renderer instead of a copy of it.
//   The stylesheet is therefore imported by the HOSTS (`ledger_map_panel.js` for admin,
//   `ledger_trace.js` for the console), which is one more place to remember and the right
//   trade: a forgotten import is an unstyled screen, a broken harness is a blind one.
import {
  structureQuery, classLabel, objectKindLabel, layerLabel,
  instantText, LAYOUT, curvePath, curvePointAt,
} from './ontology_structure_core.js';
import { countText } from './case_control_view.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function svg(doc, tag, className) {
  const node = doc.createElementNS(SVG_NS, tag);
  if (className) node.setAttribute('class', className);
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

function clear(mount) {
  while (mount.firstChild) mount.removeChild(mount.firstChild);
}

function link(doc, className, text, question, omit) {
  const a = el(doc, 'a', className, text);
  a.setAttribute('href', `?${structureQuery(question, omit)}`);
  return a;
}

/** A count, or the refusal — never a 0 standing in for an absent field. */
function countOrDash(n) {
  return n === null || n === undefined ? '미보고' : `${countText(n)}건`;
}

// ── the legend: the visual language, spelled out ─────────────
//
// 🔴 THE LEGEND IS NOT DECORATION. This screen exists so that an axis carrying
// data and an axis that is only declared can be told apart at a glance, and a
// difference the reader has to guess at is not a difference.
//
// 🔴 AND 「선언만」 IS NOT DRAWN AS A WEAKER VERSION OF 「데이터 있음」 (lead PM,
// 2026-08-14): "결함처럼 보이지도, 정상처럼 보이지도 않게 — 사실로". So the
// declared-only edge is DASHED, not faded — full-contrast ink, same stroke
// weight, different texture. Fading it would say "less important", and the whole
// reason the owner comes to this screen may be to find exactly these.
//: The five states `server/ledger_structure.py` assigns, in its spelling. A state
//: not in this map still renders — under its raw wire word — because a state that
//: vanishes takes its edges off the screen with it.
const EDGE_STATUS = {
  flowing: { label: '원장 집계', hint: '선언 + 원장에 원자' },
  declared_only: { label: '선언만 · 원장 0', hint: '축은 선언됐고 집계는 0을 셌다' },
  unmeasured: { label: '선언만 · 집계 미보고', hint: '아직 세어지지 않았다' },
  undeclared: { label: '미선언 · 관측됨', hint: '원장에 있고 어휘에 없음' },
  declared_unconsumed: { label: '선언만 · 소비자 없음', hint: '선언됐고 읽는 쪽이 없다' },
};

const statusLabelOf = (key) => (EDGE_STATUS[key] ? EDGE_STATUS[key].label : String(key));

// 🔴 ONE VOCABULARY, ALL THE WAY TO THE CLASS NAME (2026-08-14). This carried a
// `STYLE_TOKEN` map for exactly one commit, because the stylesheet was keyed on
// two spellings — `declared_zero`, `declared_unmeasured` — that never existed on
// the wire. The styling lane renamed those two rules to the server's words, so
// the translation became the identity and is gone: the state IS the modifier.
//
// Nothing may reintroduce a second spelling here. `data-state` and the class now
// carry the same five words the server assigns, which is the whole point — a
// state with two names is the drift this screen exists to report.

function renderLegend(doc, model) {
  const box = el(doc, 'div', 'os-legend');
  const layers = el(doc, 'span', 'os-legend__layers', '엣지 출처 두 층');
  box.appendChild(layers);
  for (const row of model.totals.byState) {
    const item = el(doc, 'span', `os-legend__item os-legend__item--${row.key}`);
    item.setAttribute('data-state', row.key);
    item.appendChild(el(doc, 'span', 'os-legend__swatch'));
    item.appendChild(el(doc, 'span', 'os-legend__label', statusLabelOf(row.key)));
    item.appendChild(el(doc, 'span', 'os-legend__n', countText(row.n)));
    box.appendChild(item);
  }
  const grades = el(doc, 'span', 'os-legend__grades');
  grades.appendChild(el(doc, 'span', 'os-legend__label', '해소 등급'));
  for (const key of ['pin', 'confirmed', 'observation', 'inference']) {
    const g = el(doc, 'span', `os-grade-key os-grade-key--${key}`);
    g.appendChild(el(doc, 'span', 'os-grade-key__swatch'));
    g.appendChild(el(doc, 'span', null, classLabel(key)));
    grades.appendChild(g);
  }
  box.appendChild(grades);
  return box;
}

// ── the grade bar ────────────────────────────────────────────

/**
 * The resolution mix of one edge, as a bar AND as numbers.
 *
 * 🔴 THE NUMBERS ARE NOT BEHIND A HOVER. A bar alone cannot be quoted, and this
 * screen exists so the owner can explain it to somebody else.
 */
function renderGrades(doc, grades, atoms) {
  const box = el(doc, 'div', 'os-grades');
  if (!grades || !grades.reported) {
    // 🔴 A ZERO-COUNT AXIS HAS NO GRADE MIX, AND THAT IS NOT A GAP IN REPORTING.
    // Printing 미보고 there would invite the reader to go looking for a number
    // that cannot exist; printing 「원자 0」 states the same fact the count does.
    box.appendChild(el(doc, 'span', 'os-grades__none',
      atoms === 0 ? '원자 0 — 등급 없음' : '등급 분포 미보고'));
    return box;
  }
  const bar = el(doc, 'div', 'os-grades__bar');
  bar.setAttribute('role', 'img');
  const counts = el(doc, 'div', 'os-grades__counts');
  for (const seg of grades.segments) {
    const fill = el(doc, 'span', `os-grades__seg os-grades__seg--${seg.key}`);
    fill.style.width = `${(seg.share * 100).toFixed(2)}%`;
    fill.setAttribute('data-class', seg.key);
    fill.setAttribute('data-n', String(seg.n));
    bar.appendChild(fill);

    const chip = el(doc, 'span', `os-grade os-grade--${seg.key}`);
    chip.appendChild(el(doc, 'span', 'os-grade__label', seg.label));
    chip.appendChild(el(doc, 'span', 'os-grade__n', countText(seg.n)));
    counts.appendChild(chip);
  }
  bar.setAttribute('aria-label', grades.segments.map((s) => `${s.label} ${s.n}`).join(', '));
  box.appendChild(bar);
  box.appendChild(counts);
  if (grades.mismatch) {
    box.appendChild(el(doc, 'div', 'os-grades__mismatch',
      `등급 합 ${countText(grades.counted)} ≠ 건수 ${countText(grades.total)}`));
  }
  return box;
}

// ── the graph ────────────────────────────────────────────────

// The curve spelling lives in the core now (`curvePath`), beside the function that finds a
// point ON it for badge placement. Two spellings of one curve is how a label ends up sitting
// where the line is not.

function nodeBox(doc, parent, node, className, lines) {
  const g = svg(doc, 'g', className);
  g.setAttribute('data-node', node.id);
  const rect = svg(doc, 'rect', 'os-node__box');
  attrs(rect, {
    x: node.x, y: node.y, width: node.w, height: node.h, rx: 12, ry: 12,
  });
  g.appendChild(rect);
  let dy = node.y + (node.h / 2) - ((lines.length - 1) * 11);
  for (const line of lines) {
    if (!line.text) { dy += 22; continue; }
    const t = svg(doc, 'text', line.cls);
    attrs(t, { x: node.x + 16, y: dy + 6 });
    t.textContent = line.text;
    g.appendChild(t);
    dy += line.gap || 22;
  }
  parent.appendChild(g);
  return g;
}

function renderGraph(doc, model) {
  const g = model.graph;
  const wrap = el(doc, 'div', 'os-graph');
  const scroll = el(doc, 'div', 'os-graph__scroll');
  const root = svg(doc, 'svg', 'os-svg');
  attrs(root, {
    viewBox: `0 0 ${g.width} ${g.height}`,
    width: g.width,
    height: g.height,
    role: 'img',
    'aria-label': '원장 유형 그래프 — 주어 유형, 술어, 목적어 종류',
  });
  root.style.minWidth = `${g.width}px`;

  // column captions
  for (const col of g.columns) {
    const t = svg(doc, 'text', 'os-col');
    attrs(t, { x: col.x, y: 28 });
    t.textContent = col.label;
    root.appendChild(t);
    const rule = svg(doc, 'line', 'os-col__rule');
    attrs(rule, { x1: col.x, y1: 38, x2: col.x + col.w, y2: 38 });
    root.appendChild(rule);
  }

  // edges first, so nodes paint over their ends
  const edgeLayer = svg(doc, 'g', 'os-edges');
  root.appendChild(edgeLayer);
  const anySelected = model.edgeList.some((e) => e.selected);

  for (const e of g.edges) {
    const a = svg(doc, 'a', `os-edge os-edge--${e.status}${e.selected ? ' os-edge--on' : ''}${anySelected && !e.selected ? ' os-edge--off' : ''}`);
    a.setAttribute('href', `?${structureQuery({ ...model.question, edge: e.selected ? '' : e.key })}`);
    a.setAttribute('data-edge', e.key);
    a.setAttribute('data-state', e.status);
    const title = svg(doc, 'title');
    title.textContent = `${e.subjectType} · ${e.predicate} · ${objectKindLabel(e.objectKind)} — ${countOrDash(e.atoms)}`;
    a.appendChild(title);

    if (e.tail) {
      const tail = svg(doc, 'path', 'os-edge__tail');
      attrs(tail, { d: curvePath(e.tail), fill: 'none' });
      a.appendChild(tail);
    }
    if (e.lead) {
      const lead = svg(doc, 'path', 'os-edge__lead');
      attrs(lead, {
        d: curvePath(e.lead), fill: 'none',
        // 🔴 A DECLARED-ONLY EDGE IS NOT THINNER. It is dashed and it is 2.4 —
        // heavier than the thinnest flowing edge, so "no data" can never be
        // mistaken for "a little data".
        'stroke-width': e.status === 'flowing' ? (2 + (e.weight * 5)).toFixed(2) : 2.4,
      });
      a.appendChild(lead);
      // The count rides the segment that carries it. Language-neutral numerals —
      // the Korean is on the nodes, where there is room for it.
      //
      // 🔴 THE POSITION IS THE MODEL'S, NOT A FRACTION OF THIS CURVE. Badges are placed by a
      // pass that keeps them off each other (`spreadBadges`); computing a midpoint here would
      // put a dozen of them back on the same pixel. When the model has no position — no lead
      // segment — there is no badge rather than a guessed one.
      // `0` is a MEASUREMENT and prints as one. `?` is the absence of one. The
      // screen would be lying if it printed either in place of the other.
      const text = e.atoms === null ? '?' : countText(e.atoms);
      if (e.badge) {
        const cx = e.badge.x;
        const cy = e.badge.y;
        const w = 18 + (text.length * 8.5);
        // A short leader when the badge had to move off its own curve to stay readable, so it
        // never becomes a number floating next to the wrong line.
        const onCurve = curvePointAt(e.lead, e.badgeT);
        if (Math.abs(onCurve.y - cy) > 2) {
          const tie = svg(doc, 'line', 'os-edge__tie');
          attrs(tie, { x1: onCurve.x, y1: onCurve.y, x2: cx, y2: cy });
          a.appendChild(tie);
        }
        const chip = svg(doc, 'rect', 'os-edge__chipbox');
        attrs(chip, { x: cx - (w / 2), y: cy - 13, width: w, height: 26, rx: 13, ry: 13 });
        a.appendChild(chip);
        const label = svg(doc, 'text', 'os-edge__chip');
        attrs(label, { x: cx, y: cy + 5, 'text-anchor': 'middle' });
        label.textContent = text;
        a.appendChild(label);
      }
    }
    edgeLayer.appendChild(a);
  }

  const nodeLayer = svg(doc, 'g', 'os-nodes');
  root.appendChild(nodeLayer);

  for (const n of g.subjects) {
    nodeBox(doc, nodeLayer, n, `os-node os-node--subject${n.declared ? '' : ' os-node--ghost'}`, [
      { text: n.label, cls: 'os-node__label' },
      { text: n.sub, cls: 'os-node__sub' },
    ]);
  }
  for (const n of g.predicates) {
    nodeBox(doc, nodeLayer, n, `os-node os-node--predicate os-node--${n.layer || 'unknown'}${n.declared ? '' : ' os-node--ghost'}${n.status === 'reserved' ? ' os-node--reserved' : ''}`, [
      { text: n.label, cls: 'os-node__label' },
      { text: n.predicate, cls: 'os-node__code' },
      { text: n.gloss, cls: 'os-node__sub' },
    ]);
  }
  for (const n of g.objects) {
    nodeBox(doc, nodeLayer, n, `os-node os-node--object${n.declared ? '' : ' os-node--ghost'}`, [
      { text: n.label, cls: 'os-node__label' },
      { text: n.sub, cls: 'os-node__sub' },
    ]);
  }

  scroll.appendChild(root);
  wrap.appendChild(scroll);
  return wrap;
}

// ── the edge ledger — the same edges, readable ───────────────

function renderEdgeList(doc, model) {
  const box = el(doc, 'div', 'os-edgelist');
  if (!model.edgeList.length) {
    // 🔴 WHICH EMPTY IS THIS. Three different worlds produce zero rows here and
    // they are not the same fact: the response was unreadable, the census ran and
    // found no axis, or the filter excluded them all.
    const shape = model.reading || { ok: true };
    let why;
    if (!shape.ok) why = '응답에서 축을 읽지 못했습니다 — 위 경고를 보십시오';
    else if (model.question.layer && model.totals.edges > 0) {
      why = `이 계층에 축이 없습니다 — 전체 ${countText(model.totals.edges)}개`;
    } else if (model.totals.aggregateRan) why = '집계가 실행됐고 축을 0개 보고했습니다 (측정된 0)';
    else why = '선언된 축이 없습니다 — 어휘가 비었거나 응답이 축을 담지 않았습니다';
    box.appendChild(el(doc, 'div', 'os-empty', why));
    return box;
  }
  for (const e of model.edgeList) {
    const row = el(doc, 'div', `os-row os-row--${e.status}${e.selected ? ' os-row--on' : ''}`);
    row.setAttribute('data-edge', e.key);
    row.setAttribute('data-state', e.status);
    row.id = `edge-${encodeURIComponent(e.key)}`;

    const head = el(doc, 'div', 'os-row__head');
    const triple = link(doc, 'os-row__triple', null,
      { ...model.question, edge: e.selected ? '' : e.key });
    triple.appendChild(el(doc, 'span', 'os-row__subj', e.subjectType));
    triple.appendChild(el(doc, 'span', 'os-row__arrow', '—'));
    triple.appendChild(el(doc, 'span', 'os-row__pred', e.predicate));
    triple.appendChild(el(doc, 'span', 'os-row__arrow', '▶'));
    triple.appendChild(el(doc, 'span', 'os-row__obj',
      e.targets.length ? e.targets.join(' · ') : objectKindLabel(e.objectKind)));
    head.appendChild(triple);

    const badge = el(doc, 'span', `os-badge os-badge--${e.status}`, statusLabelOf(e.status));
    head.appendChild(badge);
    head.appendChild(el(doc, 'span', 'os-row__n', countOrDash(e.atoms)));
    row.appendChild(head);

    const meta = el(doc, 'div', 'os-row__meta');
    const kindChip = el(doc, 'span', 'os-chip', `목적어 ${objectKindLabel(e.objectKind)}`);
    meta.appendChild(kindChip);
    if (e.layer) meta.appendChild(el(doc, 'span', 'os-chip', layerLabel(e.layer)));
    if (e.period.ok) {
      meta.appendChild(el(doc, 'span', 'os-chip os-chip--period',
        `${instantText(e.period.from) || '?'} → ${instantText(e.period.to) || '?'}`));
    } else {
      meta.appendChild(el(doc, 'span', 'os-chip os-chip--none',
        e.atoms === 0 ? '원자 0 — 기간 없음' : e.period.why));
    }
    row.appendChild(meta);

    row.appendChild(renderGrades(doc, e.grades, e.atoms));

    if (e.status === 'declared_only') {
      row.appendChild(el(doc, 'div', 'os-row__why',
        '선언된 축 · 원장 집계 0건 — 이 축을 쓰는 소스나 번역기가 아직 없습니다 (측정된 0)'));
    } else if (e.status === 'unmeasured') {
      row.appendChild(el(doc, 'div', 'os-row__why',
        '선언된 축 · 집계가 이 축을 보고하지 않았습니다 — 0인지 아닌지 아직 모릅니다'));
    } else if (e.status === 'undeclared') {
      row.appendChild(el(doc, 'div', 'os-row__why',
        '원장에 있는데 어휘 선언에 없습니다 — 게이트가 받았거나 선언이 뒤늦게 좁혀졌습니다'));
    }
    box.appendChild(row);
  }
  return box;
}

// ── panel 2: the vocabulary ──────────────────────────────────

function renderVocabulary(doc, model) {
  const panel = el(doc, 'section', 'os-panel');
  panel.appendChild(panelHead(doc, '어휘', `술어 ${countText(model.vocabulary.length)}개 — 각각 몇 번 쓰였나`));
  if (!model.vocabulary.length) {
    panel.appendChild(el(doc, 'div', 'os-empty', '어휘 미보고'));
    return panel;
  }
  const list = el(doc, 'div', 'os-vocab');
  for (const v of model.vocabulary) {
    const row = el(doc, 'div', `os-vocab__row${v.declared ? '' : ' os-vocab__row--ghost'}`);
    row.setAttribute('data-predicate', v.predicate);
    const top = el(doc, 'div', 'os-vocab__top');
    top.appendChild(el(doc, 'span', 'os-vocab__label', v.label));
    top.appendChild(el(doc, 'span', 'os-vocab__code', v.predicate));
    if (v.layer) top.appendChild(el(doc, 'span', 'os-chip', v.layerLabel));
    if (v.status && v.status !== 'active') {
      top.appendChild(el(doc, 'span', 'os-chip os-chip--warn', v.statusLabel));
    }
    if (v.since !== null) top.appendChild(el(doc, 'span', 'os-chip', `slice ${v.since}`));
    top.appendChild(el(doc, 'span', 'os-vocab__n', countOrDash(v.atoms)));
    row.appendChild(top);
    row.appendChild(el(doc, 'div', 'os-vocab__gloss', v.gloss || '뜻 미보고'));
    if (v.semiRef) row.appendChild(el(doc, 'div', 'os-vocab__ref', `SEMI ${v.semiRef}`));
    list.appendChild(row);
  }
  panel.appendChild(list);
  return panel;
}

// ── panel 3: the finding-kind registry ───────────────────────

function renderKinds(doc, model) {
  const panel = el(doc, 'section', 'os-panel');
  panel.appendChild(panelHead(doc, 'kind 레지스트리',
    'kind별 observed_by(= 분모 정의) · 관측 테이블 · 건수'));
  const rows = model.kinds.rows || [];
  if (!rows.length) {
    panel.appendChild(el(doc, 'div', 'os-empty',
      model.kinds.state === 'unknown' ? '등록부를 읽지 못했습니다' : '선언된 kind 없음'));
    return panel;
  }
  const list = el(doc, 'div', 'os-kinds');
  for (const k of rows) {
    const row = el(doc, 'div', 'os-kind');
    row.setAttribute('data-kind', k.kind);
    const top = el(doc, 'div', 'os-kind__top');
    top.appendChild(el(doc, 'span', 'os-kind__label', k.label));
    top.appendChild(el(doc, 'span', 'os-kind__code', k.kind));
    top.appendChild(el(doc, 'span', 'os-kind__n', countOrDash(k.atoms)));
    row.appendChild(top);

    const facts = el(doc, 'div', 'os-kind__facts');
    const denom = el(doc, 'div', 'os-fact');
    denom.appendChild(el(doc, 'span', 'os-fact__term', 'observed_by'));
    if (k.hasDenominator && k.methods.length) {
      denom.appendChild(el(doc, 'span', 'os-fact__val', k.methods.join(' · ')));
    } else {
      denom.appendChild(el(doc, 'span', 'os-fact__val os-fact__val--none', '미선언 — 분모 없음'));
    }
    facts.appendChild(denom);

    const table = el(doc, 'div', 'os-fact');
    table.appendChild(el(doc, 'span', 'os-fact__term', '관측 테이블'));
    table.appendChild(el(doc, 'span', k.observationTable ? 'os-fact__val' : 'os-fact__val os-fact__val--none',
      k.observationTable || '미보고'));
    facts.appendChild(table);

    const runs = el(doc, 'div', 'os-fact');
    runs.appendChild(el(doc, 'span', 'os-fact__term', '검사 실행'));
    runs.appendChild(el(doc, 'span', k.runs === null ? 'os-fact__val os-fact__val--none' : 'os-fact__val',
      k.runs === null ? '분모 없음' : `${countText(k.runs)}회`));
    facts.appendChild(runs);

    if (k.classes && k.classes.length) {
      const cls = el(doc, 'div', 'os-fact');
      cls.appendChild(el(doc, 'span', 'os-fact__term', '분류'));
      cls.appendChild(el(doc, 'span', 'os-fact__val', k.classes.join(' · ')));
      facts.appendChild(cls);
    }
    row.appendChild(facts);
    list.appendChild(row);
  }
  panel.appendChild(list);
  return panel;
}

// ── panel 4: the declaration map ─────────────────────────────

function renderDeclarations(doc, model) {
  const panel = el(doc, 'section', 'os-panel os-panel--wide');
  const declHead = panelHead(doc, '선언 지도', '어떤 config가 무엇을 선언하는가 — 항목에서 해당 축으로');
  // 🔴 THE PANEL NAMES ITS N (lead PM, 2026-08-14). The list scrolls inside its
  // own box now, which is not concealment — every row is still there and still
  // reachable — but a reader who cannot see the end of a list has to ask how long
  // it is. Saying it removes the question. DERIVED, never typed: it is the count
  // of items across the groups, so it stays true when a config is added.
  const declN = model.declarations.reduce(
    (s, d) => s + (Array.isArray(d.items) ? d.items.length : 0), 0);
  //: Only when there ARE declarations. A 「0건」 over a response that simply did
  //: not carry the container would be an invented measurement — the same
  //: absent-is-not-zero rule the rest of this screen follows.
  if (model.declarations.length) {
    declHead.appendChild(el(doc, 'span', 'os-chip os-panel__n', `${countText(declN)}건`));
  }
  panel.appendChild(declHead);
  if (!model.declarations.length) {
    panel.appendChild(el(doc, 'div', 'os-empty',
      '선언 미보고 — 집계 응답이 `declarations`를 담지 않았습니다'));
    return panel;
  }
  for (const d of model.declarations) {
    const group = el(doc, 'div', 'os-decl');
    const head = el(doc, 'div', 'os-decl__head');
    head.appendChild(el(doc, 'span', 'os-decl__title', d.title));
    if (d.file) head.appendChild(el(doc, 'span', 'os-decl__file', d.file));
    group.appendChild(head);
    if (!d.items.length) {
      group.appendChild(el(doc, 'div', 'os-empty', '항목 없음'));
    }
    for (const item of d.items) {
      const row = el(doc, 'div', 'os-decl__item');
      row.appendChild(el(doc, 'span', 'os-decl__term', item.term));
      if (item.detail) row.appendChild(el(doc, 'span', 'os-decl__detail', item.detail));
      if (item.edges.length) {
        const refs = el(doc, 'span', 'os-decl__refs');
        for (const key of item.edges) {
          const a = link(doc, 'os-decl__ref', key.split('|').slice(0, 2).join(' · '),
            { ...model.question, edge: key });
          a.setAttribute('data-edge', key);
          refs.appendChild(a);
        }
        row.appendChild(refs);
      } else {
        row.appendChild(el(doc, 'span', 'os-decl__norefs', '연결된 축 없음'));
      }
      group.appendChild(row);
    }
    panel.appendChild(group);
  }
  return panel;
}

// ── frame ────────────────────────────────────────────────────

function panelHead(doc, title, sub) {
  const head = el(doc, 'div', 'os-panel__head');
  head.appendChild(el(doc, 'h2', 'os-panel__title', title));
  if (sub) head.appendChild(el(doc, 'span', 'os-panel__sub', sub));
  return head;
}

function renderNotice(doc, notice) {
  const box = el(doc, 'div', `os-notice os-notice--${notice.tone || 'idle'}`);
  box.appendChild(el(doc, 'div', 'os-notice__title', notice.title || ''));
  if (notice.detail) box.appendChild(el(doc, 'div', 'os-notice__detail', notice.detail));
  return box;
}

// ── the seam, when it drifts ─────────────────────────────────
//
// 🔴 A BLANK MUST SAY WHICH BLANK IT IS (lead PM, P0, 2026-08-14). This screen
// spent an evening painting an empty frame under the words 「원장 가동 — 아래
// 숫자는 실측입니다」 because three of the four containers it read had moved one
// level down the response. Nothing threw; every panel just had nothing to say and
// said it politely.
//
// So when the reader could not find the graph, that is stated ABOVE everything
// else, with the keys it expected and the keys that arrived — a pair anyone can
// check against the server without reading this file.
function renderShapeAlarm(doc, reading) {
  if (!reading || reading.ok) return null;
  const box = el(doc, 'div', 'os-notice os-notice--error');
  box.appendChild(el(doc, 'div', 'os-notice__title',
    reading.shape === 'none'
      ? '구조 응답 없음 — 화면이 빈 것은 원장이 비어서가 아닙니다'
      : '구조 응답을 읽지 못했습니다 — 화면이 빈 것은 원장이 비어서가 아닙니다'));
  if (reading.why) box.appendChild(el(doc, 'div', 'os-notice__detail', reading.why));
  return box;
}

/** A served-shape gap: the graph was found, one of its parts was not. */
function renderShapeGap(doc, reading) {
  if (!reading || !reading.ok || !reading.why) return null;
  const box = el(doc, 'div', 'os-notice os-notice--gap');
  box.appendChild(el(doc, 'div', 'os-notice__title', '응답에 빠진 부분이 있습니다'));
  box.appendChild(el(doc, 'div', 'os-notice__detail', reading.why));
  return box;
}

// ── the layers of the world ──────────────────────────────────

function renderLayers(doc, model) {
  if (!model.graphLayers || !model.graphLayers.length) return null;
  const box = el(doc, 'div', 'os-filter');
  box.appendChild(el(doc, 'span', 'os-filter__term', '층'));
  for (const l of model.graphLayers) {
    const chip = el(doc, 'span', 'os-chip');
    chip.setAttribute('data-layer', l.id);
    const parts = [l.label];
    parts.push(`노드 ${l.nodes === null ? '미보고' : countText(l.nodes)}`);
    parts.push(`엣지 ${l.edges === null ? '미보고' : countText(l.edges)}`);
    //: A layer with no atom count is not a layer with zero atoms — the mechanism
    //: layer is declared and never counted, and those are different facts.
    parts.push(l.atoms === null ? '원자 미집계' : `원자 ${countText(l.atoms)}`);
    chip.textContent = parts.join(' · ');
    box.appendChild(chip);
    if (l.message) box.appendChild(el(doc, 'span', 'os-chip os-chip--none', l.message));
  }
  return box;
}

// ── the mechanism layer (M4) ─────────────────────────────────
//
// 🔴 NOT DRAWN INTO THE THREE COLUMNS. Its nodes are causal variables, not
// subject/predicate/object triples; forcing them into that layout would assert a
// join that does not exist. It is also the only place the fifth edge state,
// `declared_unconsumed`, can be seen today.
function renderMechanism(doc, model) {
  const m = model.mechanism;
  if (!m) return null;
  const panel = el(doc, 'section', 'os-panel os-panel--wide');
  panel.appendChild(panelHead(doc, '기전 그래프 (M4)',
    '선언된 인과 모형 — 원장이 아직 읽지 않는 축'));

  const facts = el(doc, 'div', 'os-kind__facts');
  const fact = (term, val, none) => {
    const f = el(doc, 'div', 'os-fact');
    f.appendChild(el(doc, 'span', 'os-fact__term', term));
    f.appendChild(el(doc, 'span', none ? 'os-fact__val os-fact__val--none' : 'os-fact__val', val));
    facts.appendChild(f);
  };
  fact('상태', m.state);
  fact('선언 파일', m.config || '미보고', !m.config);
  if (m.specRef) fact('스펙', m.specRef);
  if (m.link && m.link.message) fact('원장 연결', m.link.message, true);
  if (m.message) fact('메시지', m.message, true);
  panel.appendChild(facts);

  if (!m.models.length) {
    panel.appendChild(el(doc, 'div', 'os-empty', '선언된 모형 없음'));
    return panel;
  }
  const byModel = new Map();
  for (const e of m.edges) {
    if (!byModel.has(e.model)) byModel.set(e.model, []);
    byModel.get(e.model).push(e);
  }
  for (const mm of m.models) {
    const row = el(doc, 'div', 'os-row');
    row.setAttribute('data-model', mm.model);
    const head = el(doc, 'div', 'os-row__head');
    head.appendChild(el(doc, 'span', 'os-row__pred', mm.model));
    if (mm.version) head.appendChild(el(doc, 'span', 'os-chip', mm.version));
    head.appendChild(el(doc, 'span', 'os-row__n',
      `노드 ${countText(mm.nodes.length)} · 엣지 ${countText(mm.edgeIds.length)}`));
    row.appendChild(head);
    const edges = byModel.get(mm.model) || [];
    if (!edges.length) {
      // 🔴 NOT SKIPPED. A config section with no causal edges is a DECLARATION
      // that contributes none — `bindings` (field → physical quantity) is exactly
      // that, and dropping it because its count surprised somebody would hide a
      // real declaration behind a tidier list.
      row.appendChild(el(doc, 'div', 'os-row__why', '인과 엣지 없음 — 선언은 있고 그래프에 기여하지 않습니다'));
    } else {
      const meta = el(doc, 'div', 'os-row__meta');
      for (const e of edges) {
        const chip = el(doc, 'span', 'os-chip',
          `${e.source} ${e.dirLabel || e.dir || '→'} ${e.target}`);
        chip.setAttribute('data-state', e.status);
        meta.appendChild(chip);
      }
      row.appendChild(meta);
      const states = [...new Set(edges.map((e) => e.status))].filter(Boolean);
      const badges = el(doc, 'div', 'os-row__meta');
      for (const s of states) {
        badges.appendChild(el(doc, 'span', `os-badge os-badge--${s}`, statusLabelOf(s)));
      }
      row.appendChild(badges);
    }
    panel.appendChild(row);
  }
  return panel;
}

const STATE_READING = {
  ready: { tone: 'ok', text: '원장 가동 — 아래 숫자는 실측입니다' },
  empty: { tone: 'gap', text: '테이블은 있고 원자 0 — 선언만 보입니다 (백필 미실행)' },
  absent: { tone: 'gap', text: '원장 테이블 없음 — 선언만 보입니다 (마이그레이션 미실행)' },
  unknown: { tone: 'gap', text: '원장 상태 미보고' },
};

/**
 * The whole view.
 *
 * `notice` is the transport's word (busy / 404 / refusal) and is rendered ABOVE
 * the frame, never instead of it: the panels paint from whatever the model has,
 * each one saying what it does not know. That is what lets this screen ship
 * before the aggregate route does.
 */
export function renderStructure(doc, mount, model, notice) {
  // 🔴 THE MOUNT IS NOT CLEARED UNTIL THERE IS SOMETHING TO PUT IN IT, AND A
  // THROW IS PUT ON SCREEN (lead PM, P0, 2026-08-14). The old order was
  // `clear(mount)` and then build; anything that threw mid-build left a literally
  // empty element and the user saw a blank page with no way to tell it from an
  // empty world. Now the tree is built detached, and a failure paints the failure.
  let root;
  try {
    root = buildStructure(doc, mount, model, notice);
  } catch (err) {
    root = el(doc, 'div', 'os');
    const box = el(doc, 'div', 'os-notice os-notice--error');
    box.appendChild(el(doc, 'div', 'os-notice__title', '구조 화면을 그리지 못했습니다'));
    box.appendChild(el(doc, 'div', 'os-notice__detail',
      String((err && err.stack) || (err && err.message) || err).slice(0, 600)));
    root.appendChild(box);
  }
  clear(mount);
  mount.appendChild(root);
  return root;
}

function buildStructure(doc, mount, model, notice) {
  const root = el(doc, 'div', 'os');

  const head = el(doc, 'div', 'os-head');
  const title = el(doc, 'div', 'os-head__title');
  title.appendChild(el(doc, 'span', 'os-head__h', '원장 유형 구조'));
  title.appendChild(el(doc, 'span', 'os-head__sub',
    '어떤 객체가 어떤 관계로 이어져 있고, 어디에 데이터가 얼마나 있는가'));
  head.appendChild(title);

  // 🔴 THE LEDGER'S STATE IS ONLY CLAIMABLE IF THE ANSWER WAS READ. `ready` over
  // an unreadable body is how this screen came to announce 「아래 숫자는 실측입니다」
  // above nothing at all.
  const shape = model.reading || { ok: true, shape: 'legacy' };
  const reading = shape.ok
    ? (STATE_READING[model.state] || STATE_READING.unknown)
    : { tone: 'gap', text: '응답을 읽지 못해 원장 상태를 말할 수 없습니다' };
  const state = el(doc, 'span', `os-state os-state--${reading.tone}`, reading.text);
  state.setAttribute('data-state', shape.ok ? model.state : 'unreadable');
  head.appendChild(state);
  root.appendChild(head);

  const alarm = renderShapeAlarm(doc, shape);
  if (alarm) root.appendChild(alarm);
  const gap = renderShapeGap(doc, shape);
  if (gap) root.appendChild(gap);

  if (notice) root.appendChild(renderNotice(doc, notice));

  const layerStrip = renderLayers(doc, model);
  if (layerStrip) root.appendChild(layerStrip);

  // the layer filter — anchors, so it is in the URL
  if (model.layers.length > 1) {
    const filter = el(doc, 'div', 'os-filter');
    filter.appendChild(el(doc, 'span', 'os-filter__term', '계층'));
    const all = link(doc, `os-filter__opt${model.question.layer ? '' : ' os-filter__opt--on'}`,
      `전체 ${countText(model.totals.edges)}`, { ...model.question, layer: '' });
    filter.appendChild(all);
    for (const l of model.layers) {
      filter.appendChild(link(doc,
        `os-filter__opt${model.question.layer === l.key ? ' os-filter__opt--on' : ''}`,
        `${l.label} ${countText(l.count)}`, { ...model.question, layer: l.key }));
    }
    root.appendChild(filter);
  }

  root.appendChild(renderLegend(doc, model));
  root.appendChild(renderGraph(doc, model));

  const listPanel = el(doc, 'section', 'os-panel os-panel--wide');
  listPanel.appendChild(panelHead(doc, '축별 실측',
    '주어 유형 × 술어 × 목적어 종류 — 건수 · 기간 · 해소 등급 분포'));
  listPanel.appendChild(renderEdgeList(doc, model));
  root.appendChild(listPanel);

  const grid = el(doc, 'div', 'os-grid');
  grid.appendChild(renderVocabulary(doc, model));
  grid.appendChild(renderKinds(doc, model));
  root.appendChild(grid);

  const mech = renderMechanism(doc, model);
  if (mech) root.appendChild(mech);

  root.appendChild(renderDeclarations(doc, model));

  const stamp = [];
  if (model.generatedAt) stamp.push(`집계 시각 ${instantText(model.generatedAt)}`);
  const c = model.census;
  if (c) {
    if (c.relation) stamp.push(c.relation);
    if (c.ms !== null) stamp.push(`${countText(c.ms)}ms`);
    if (c.atoms !== null) stamp.push(`원자 ${countText(c.atoms)}`);
    //: `exact: false` means the census was windowed — the numbers above are a
    //: slice, not the ledger. Saying so is cheaper than being asked why they moved.
    if (c.exact === false) {
      stamp.push(`부분 집계${c.windowSpec ? ` · ${c.windowSpec}` : ''}`);
    }
    if (c.forced && c.forcedReason) stamp.push(c.forcedReason);
  }
  if (stamp.length) {
    root.appendChild(el(doc, 'div', 'os-generated', stamp.join(' · ')));
  }
  return root;
}

//: Re-exported so a caller sizing the scroll box does not have to import the core
//: as well. The geometry itself lives in the core, where the harness scores it.
export { LAYOUT };
