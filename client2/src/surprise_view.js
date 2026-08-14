// ============================================================
// surprise_view.js — 놀라움 장치를 DOM + inline SVG로.
//
// `document` IS AN ARGUMENT, not a global — same contract as
// `ledger_trace_view.js`, `case_control_view.js` and `ontology_structure_view.js`,
// so `tests/surprise_harness.mjs` drives the REAL renderer under bare node and
// asserts what reaches the screen. Everything here builds nodes and sets
// `textContent`; nothing touches `innerHTML`, so a lot id or a metric label out of
// the server can never become markup.
//
// 🔴 NO NEW CHART LIBRARY. The small multiples are inline SVG built by hand, the
// same call the structure view already made and for the same reasons: a dozen
// points per chart, Korean labels that have to be selectable, and no dependency
// worth adding for a polyline. `graph_viewer.js` still owns the instance graph.
//
// 🔴 NO FORM CONTROLS EXCEPT THE MARK BOXES. Column composition is anchors, so
// the column set is in the URL and pastes into a message. Marking is a checkbox
// because it is a SELECTION rather than a question — it must be instant and must
// not refetch — and the entry file listens once, delegated on the mount, so this
// file stays a pure renderer.
//
// 🔴 THE LEGEND DOES NOT SPEAK THE ROWS' LANGUAGE. Heat rows carry `data-heat`;
// the legend carries `data-heat-key`. That is deliberate: a legend using the same
// attribute and the same words makes every tree-wide assertion vacuous — it stays
// green with every row deleted. The harness scopes to `sx-table` as well, but the
// attribute split is what makes the mistake impossible rather than merely caught.
//
// 🔴 READABILITY IS A FUNCTION. Cell values 15px, fractions and lifts 13px,
// nothing below 13px. The table scrolls horizontally inside its own box rather
// than shrinking the type — a wide table is a layout problem, not a font-size one.
// ============================================================

import {
  surpriseQuery, withColumn, withoutColumn,
  valueText, liftText, fractionText, HEAT_LABELS,
} from './surprise_core.js';
import { countText } from './case_control_view.js';
import { renderAxisMaps } from './surprise_map_view.js';

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

function link(doc, className, text, question) {
  const a = el(doc, 'a', className, text);
  a.setAttribute('href', `?${surpriseQuery(question)}`);
  return a;
}

// ── the notice ───────────────────────────────────────────────

/**
 * What the screen does not know, said out loud at the top.
 *
 * 🔴 A 404 IS NOT AN ERROR SCREEN HERE. The aggregate route is not deployed yet;
 * the frame still paints from the kind catalog, and this line is what tells the
 * reader that the empty table is a missing route rather than a fab with no lots.
 */
function renderNotice(doc, { tone, title, detail }) {
  const box = el(doc, 'div', `sx-notice sx-notice--${tone}`);
  box.setAttribute('data-notice-tone', tone);
  box.appendChild(el(doc, 'div', 'sx-notice__title', title));
  if (detail) box.appendChild(el(doc, 'pre', 'sx-notice__detail', detail));
  return box;
}

// ── 열 구성 — the question, as chips ─────────────────────────

/**
 * The column set: what is up, and what could be.
 *
 * 🔴 THIS PANEL IS THE PROOF THE METRIC LIST IS NOT HARDCODED. Every chip here
 * comes from the server's declaration; a metric registered tomorrow shows up in
 * 「열 추가」 without a line changing in this file. And every chip is an ANCHOR
 * carrying the whole question, so the column set the owner built is the URL.
 */
function renderColumnBar(doc, model) {
  const box = el(doc, 'div', 'sx-cols');
  box.setAttribute('data-panel', 'columns');
  box.setAttribute('data-col-count', String(model.columns.length));

  const up = el(doc, 'div', 'sx-cols__row');
  up.appendChild(el(doc, 'span', 'sx-cols__term', '열 구성'));
  if (!model.columns.length) {
    up.appendChild(el(doc, 'span', 'sx-cols__none',
      model.catalog.columns.length
        ? '열 없음 — 아래에서 지표를 추가하십시오'
        : '지표 선언 미배포 — 열을 만들 수 없습니다'));
  }
  for (const col of model.columns) {
    const chip = el(doc, 'span', `sx-colchip${col.declared ? '' : ' sx-colchip--unknown'}`);
    chip.setAttribute('data-col', col.key);
    chip.setAttribute('data-col-declared', col.declared ? '1' : '0');
    chip.appendChild(el(doc, 'span', 'sx-colchip__label', col.label));
    if (!col.declared) chip.appendChild(el(doc, 'span', 'sx-colchip__warn', '미선언'));
    const drop = link(doc, 'sx-colchip__drop', '✕', withoutColumn(model.question, col));
    drop.setAttribute('title', `${col.label} 열 제거`);
    drop.setAttribute('aria-label', `${col.label} 열 제거`);
    chip.appendChild(drop);
    up.appendChild(chip);
  }
  box.appendChild(up);

  const add = el(doc, 'div', 'sx-cols__row sx-cols__row--add');
  add.setAttribute('data-panel', 'columns-available');
  add.appendChild(el(doc, 'span', 'sx-cols__term', '열 추가'));
  if (!model.available.length) {
    add.appendChild(el(doc, 'span', 'sx-cols__none',
      model.catalog.columns.length ? '선언된 지표가 전부 올라와 있습니다' : '선언된 집계 없음'));
  }
  for (const col of model.available) {
    const a = link(doc, 'sx-coladd', `+ ${col.label}`, withColumn(model.question, col));
    a.setAttribute('data-col-add', col.key);
    add.appendChild(a);
  }
  box.appendChild(add);

  // Items the kind catalog declares but the metric declaration has no aggregate
  // for. 빈 축 정직 — an item nobody can chart is still an item that exists.
  const itemOnly = model.catalog.items.filter((it) => it.source === 'declared_item_only');
  if (itemOnly.length) {
    const gap = el(doc, 'div', 'sx-cols__row sx-cols__row--gap');
    gap.setAttribute('data-panel', 'columns-undeclared');
    gap.appendChild(el(doc, 'span', 'sx-cols__term', '집계 미선언 항목'));
    for (const it of itemOnly) {
      const chip = el(doc, 'span', 'sx-itemchip');
      chip.setAttribute('data-item', it.metric);
      chip.appendChild(el(doc, 'span', 'sx-itemchip__label', it.label));
      chip.appendChild(el(doc, 'span', 'sx-itemchip__n',
        it.atoms === null ? '건수 미보고' : `${countText(it.atoms)}건`));
      gap.appendChild(chip);
    }
    box.appendChild(gap);
  }
  return box;
}

// ── 표 ───────────────────────────────────────────────────────

/** One column header: 항목 · 집계 · 기저 — the denominator's definition included. */
function renderColumnHead(doc, col) {
  const th = el(doc, 'th', 'sx-th sx-th--metric');
  attrs(th, { scope: 'col', 'data-col': col.key });
  th.appendChild(el(doc, 'span', 'sx-th__metric', col.metricLabel));
  th.appendChild(el(doc, 'span', 'sx-th__agg', col.aggLabel));
  const foot = el(doc, 'span', 'sx-th__base');
  if (col.baseline !== null && col.baseline !== undefined) {
    foot.textContent = `기저 ${valueText(col.baseline, col.unit)}`;
    foot.setAttribute('data-baseline', String(col.baseline));
  } else {
    foot.textContent = '기저 미보고';
    foot.setAttribute('data-baseline', 'none');
  }
  th.appendChild(foot);
  if (col.denominator) {
    th.appendChild(el(doc, 'span', 'sx-th__den', `분모 ${col.denominator}`));
  }
  return th;
}

/**
 * One cell.
 *
 * 🔴 미검사 AND 0 ARE NOT THE SAME CELL, and this function is where that is
 * enforced at the DOM level: they get different `data-cell-state`, different
 * text, and only one of them ever gets a `data-heat`. A reader who sees 「—」
 * knows nothing was measured; a reader who sees 「0%」 knows something was, and
 * came back clean.
 */
function renderCell(doc, cell) {
  const { column, reading } = cell;
  const td = el(doc, 'td', 'sx-cell');
  attrs(td, { 'data-col': column.key, 'data-cell-state': reading.state });

  if (reading.state !== 'measured') {
    td.className = `sx-cell sx-cell--${reading.state}`;
    const v = el(doc, 'span', 'sx-cell__v sx-cell__v--none', reading.text);
    td.appendChild(v);
    const why = el(doc, 'span', 'sx-cell__why', reading.why);
    why.setAttribute('data-cell-why', reading.why);
    td.appendChild(why);
    return td;
  }

  if (reading.level !== null) td.setAttribute('data-heat', String(reading.level));
  if (reading.suppressed) td.setAttribute('data-heat-suppressed', 'special_eval');
  if (reading.level !== null && reading.level > 0) {
    td.className = `sx-cell sx-cell--h${reading.level}`;
  }

  td.appendChild(el(doc, 'span', 'sx-cell__v', valueText(reading.value, column.unit)));
  const frac = fractionText(reading);
  if (frac) {
    const f = el(doc, 'span', 'sx-cell__f', frac);
    attrs(f, {
      'data-numerator': reading.n === null ? null : String(reading.n),
      'data-denominator': reading.d === null ? null : String(reading.d),
    });
    td.appendChild(f);
  }
  if (reading.lift !== null) {
    const lift = el(doc, 'span', 'sx-cell__lift', liftText(reading.lift));
    lift.setAttribute('data-lift', String(reading.lift));
    td.appendChild(lift);
  }
  return td;
}

function renderRow(doc, row, model) {
  const tr = el(doc, 'tr', `sx-row${row.marked ? ' sx-row--marked' : ''}`);
  attrs(tr, {
    'data-lot': row.lot,
    'data-bucket': row.bucket,
    'data-marked': row.marked ? '1' : '0',
  });

  const markTd = el(doc, 'td', 'sx-row__mark');
  const box = doc.createElement('input');
  attrs(box, {
    type: 'checkbox',
    'data-mark-lot': row.lot,
    'aria-label': `${row.lot} 마킹`,
  });
  // `.checked` is the property the browser reads; the attribute alone would only
  // set the DEFAULT and a re-render would leave stale boxes ticked.
  box.checked = row.marked;
  if (row.marked) box.setAttribute('checked', 'checked');
  markTd.appendChild(box);
  tr.appendChild(markTd);

  const lotTd = el(doc, 'td', 'sx-row__lot');
  // The lineage answer for this lot — the other question on this same page.
  const a = el(doc, 'a', 'sx-lot', row.lot);
  a.setAttribute('href', `?lot=${encodeURIComponent(row.lot)}`);
  a.setAttribute('data-lot-link', row.lot);
  lotTd.appendChild(a);
  if (row.seq !== null) {
    lotTd.appendChild(el(doc, 'span', 'sx-row__seq', `#${row.seq}`));
  }
  tr.appendChild(lotTd);

  const bucketTd = el(doc, 'td', 'sx-row__bucket');
  const badge = el(doc, 'span', `sx-bucket sx-bucket--${row.bucket}`, row.bucketLabel);
  badge.setAttribute('data-bucket-badge', row.bucket);
  bucketTd.appendChild(badge);
  tr.appendChild(bucketTd);

  const chipsTd = el(doc, 'td', 'sx-row__chips');
  if (row.chips === null) {
    const none = el(doc, 'span', 'sx-row__chips--none', '미보고');
    none.setAttribute('data-chips', 'none');
    chipsTd.appendChild(none);
  } else {
    chipsTd.appendChild(el(doc, 'span', null, countText(row.chips)));
  }
  tr.appendChild(chipsTd);

  for (const cell of row.cells) tr.appendChild(renderCell(doc, cell));
  if (!model.columns.length) {
    tr.appendChild(el(doc, 'td', 'sx-cell sx-cell--nocol', '열 없음'));
  }
  return tr;
}

function renderTable(doc, model) {
  const wrap = el(doc, 'div', 'sx-tablewrap');
  wrap.setAttribute('data-panel', 'table');

  const table = el(doc, 'table', 'sx-table');
  const head = el(doc, 'thead');
  const hr = el(doc, 'tr');
  const th = (cls, text, extra) => {
    const n = el(doc, 'th', `sx-th ${cls}`, text);
    n.setAttribute('scope', 'col');
    if (extra) attrs(n, extra);
    hr.appendChild(n);
    return n;
  };
  th('sx-th--mark', '마킹');
  th('sx-th--lot', '랏');
  th('sx-th--bucket', '버킷');
  th('sx-th--chips', '검사 칩');
  for (const col of model.columns) hr.appendChild(renderColumnHead(doc, col));
  if (!model.columns.length) th('sx-th--nocol', '지표');
  head.appendChild(hr);
  table.appendChild(head);

  const body = el(doc, 'tbody', 'sx-tbody');
  for (const row of model.rows) body.appendChild(renderRow(doc, row, model));
  table.appendChild(body);
  wrap.appendChild(table);

  if (!model.rows.length) {
    wrap.appendChild(el(doc, 'p', 'sx-empty',
      model.state === 'unknown'
        ? '집계 응답 없음 — 행을 그릴 근거가 없습니다'
        : '이 구간에 랏이 없습니다'));
  }
  return wrap;
}

// ── 범례 ─────────────────────────────────────────────────────

/**
 * 🔴 THE LEGEND USES `data-heat-key`, NOT `data-heat`. See the file header: a
 * legend that speaks the rows' language makes every tree-wide assertion about the
 * rows vacuously true. This is the structural half of that defence; the harness
 * scoping is the other half.
 */
function renderLegend(doc, model) {
  const box = el(doc, 'div', 'sx-legend');
  box.setAttribute('data-panel', 'legend');

  const heat = el(doc, 'div', 'sx-legend__group');
  heat.appendChild(el(doc, 'span', 'sx-legend__term', '조건부서식 — 열마다 자기 기저 대비 배수'));
  for (let i = 1; i < HEAT_LABELS.length; i += 1) {
    const item = el(doc, 'span', `sx-legend__item sx-legend__item--h${i}`);
    item.setAttribute('data-heat-key', String(i));
    item.appendChild(el(doc, 'span', 'sx-legend__swatch'));
    item.appendChild(el(doc, 'span', 'sx-legend__label', HEAT_LABELS[i]));
    item.appendChild(el(doc, 'span', 'sx-legend__cut', `${model.scale[i - 1]}배 이상`));
    heat.appendChild(item);
  }
  // 🔴 WHO ASSIGNED THE STEP, SAID ON SCREEN. The level is the server's number in
  // every case — this line only says whether the BANDS beside the swatches came
  // from the server's declaration or are the documented defaults, so a reader
  // cannot mistake the cut points for something the browser decided.
  heat.appendChild(el(doc, 'span', 'sx-legend__src',
    model.scaleFromServer ? '단계 판정: 서버 · 구간 선언됨' : '단계 판정: 서버 · 구간 표시는 기본값'));
  box.appendChild(heat);

  const states = el(doc, 'div', 'sx-legend__group');
  states.appendChild(el(doc, 'span', 'sx-legend__term', '칸 상태'));
  // 🔴 SPELLED OUT BECAUSE THE DIFFERENCE IS THE POINT. 미검사 is not a good
  // result and must never be read as one.
  const cellStates = [
    ['unscanned', '— 미검사', '검사 모집단 밖입니다. 0이 아니라 «모름»입니다'],
    ['measured', '0 측정된 0', '검사했고 발생이 0이었습니다'],
    ['unmeasurable', '측정 불가', '이 항목이 이 랏에서 정의되지 않습니다'],
    ['no_denominator', '분모 없음', '건수는 있으나 율을 정의할 분모가 없습니다'],
    ['unreported', '미보고', '집계가 이 칸을 싣지 않았습니다 — 답의 구멍입니다'],
  ];
  for (const [key, label, hint] of cellStates) {
    const item = el(doc, 'span', `sx-legend__item sx-legend__item--${key}`);
    item.setAttribute('data-cell-state-key', key);
    item.appendChild(el(doc, 'span', 'sx-legend__label', label));
    item.appendChild(el(doc, 'span', 'sx-legend__hint', hint));
    states.appendChild(item);
  }
  box.appendChild(states);

  const buckets = el(doc, 'div', 'sx-legend__group');
  buckets.appendChild(el(doc, 'span', 'sx-legend__term', '특수평가 행'));
  buckets.appendChild(el(doc, 'span', 'sx-legend__hint',
    '뱃지로만 구분하고 칠하지 않습니다 — 숨기지도 않습니다. 배율 계산·대조군에서만 빠집니다.'));
  box.appendChild(buckets);

  return box;
}

// ── 소형 트렌드 차트 ─────────────────────────────────────────

const CHART = { w: 320, h: 128, left: 8, right: 8, top: 12, bottom: 22 };

/**
 * One column's small multiple.
 *
 * 🔴 A GAP IS DRAWN AS A GAP. `chartSeries` already separated 미검사 out of the
 * points; the polyline is broken at those indices rather than joined across them,
 * because a segment drawn through data nobody has is the chart telling a story the
 * ledger did not.
 *
 * 🔴 AND THE DENOMINATOR OF THE CHART IS ON THE CHART. "n/N 랏 표시" says how
 * many lots are behind the line — a trend over 3 of 40 lots is a different claim
 * from a trend over 40.
 */
function renderChart(doc, series, model) {
  const box = el(doc, 'figure', 'sx-chart');
  box.setAttribute('data-chart', series.column.key);

  const cap = el(doc, 'figcaption', 'sx-chart__cap');
  cap.appendChild(el(doc, 'span', 'sx-chart__title', series.column.label));
  cap.appendChild(el(doc, 'span', 'sx-chart__n',
    `${series.plotted}/${series.total} 랏 표시`));
  box.appendChild(cap);

  if (!series.points.length) {
    // 🔴 AN EMPTY CHART STILL CARRIES ITS COUNTS. "nothing to draw" and "40 lots
    // went unmeasured" are different facts, and dropping the second one turns a
    // measurement gap into a blank box the reader will read as "nothing happened".
    const none = el(doc, 'p', 'sx-chart__none',
      series.gaps.length ? `측정값 없음 — ${series.gaps.length}랏 미측정` : '그릴 측정값 없음');
    none.setAttribute('data-chart-empty', '1');
    if (series.gaps.length) none.setAttribute('data-chart-gaps', String(series.gaps.length));
    box.appendChild(none);
    if (series.special.length) {
      const sp = el(doc, 'p', 'sx-chart__none', `특수평가 ${series.special.length}랏은 선에서 제외됩니다`);
      sp.setAttribute('data-chart-special', String(series.special.length));
      box.appendChild(sp);
    }
    return box;
  }

  const n = model.rows.length;
  const innerW = CHART.w - CHART.left - CHART.right;
  const innerH = CHART.h - CHART.top - CHART.bottom;
  const top = Math.max(
    series.max === null ? 0 : series.max,
    series.baseline === null ? 0 : series.baseline * 1.2,
  ) * 1.12 || 1;
  const X = (i) => CHART.left + (n <= 1 ? innerW / 2 : (i * innerW) / (n - 1));
  const Y = (v) => CHART.top + innerH - (v / top) * innerH;

  const s = svg(doc, 'svg', 'sx-chart__svg');
  attrs(s, {
    viewBox: `0 0 ${CHART.w} ${CHART.h}`,
    role: 'img',
    'aria-label': `${series.column.label} 생산 순서 추이, ${series.plotted}개 랏`,
    preserveAspectRatio: 'none',
  });

  // The baseline band — where "normal" is, so a spike has something to be a spike
  // against. Absent baseline draws nothing rather than a band at zero.
  if (series.baseline !== null && series.baseline > 0) {
    const band = svg(doc, 'rect', 'sx-chart__band');
    attrs(band, {
      x: CHART.left, y: Y(series.baseline).toFixed(1),
      width: innerW, height: Math.max(0, CHART.top + innerH - Y(series.baseline)).toFixed(1),
      'data-baseline': String(series.baseline),
    });
    s.appendChild(band);
  }

  // Ledger events as vertical markers on the shared axis.
  for (const ev of model.events) {
    if (!ev.placed) continue;
    const line = svg(doc, 'line', 'sx-chart__event');
    attrs(line, {
      x1: X(ev.i).toFixed(1), y1: CHART.top,
      x2: X(ev.i).toFixed(1), y2: (CHART.top + innerH).toFixed(1),
      'data-event': ev.label,
    });
    s.appendChild(line);
  }

  // Broken polyline: one segment per run of consecutive plotted indices.
  let run = [];
  const flush = () => {
    if (run.length > 1) {
      const poly = svg(doc, 'polyline', 'sx-chart__line');
      attrs(poly, { points: run.map((p) => `${X(p.i).toFixed(1)},${Y(p.value).toFixed(1)}`).join(' ') });
      s.appendChild(poly);
    }
    run = [];
  };
  for (const p of series.points) {
    if (run.length && p.i !== run[run.length - 1].i + 1) flush();
    run.push(p);
  }
  flush();

  for (const p of series.points) {
    const row = model.rows[p.i];
    const dot = svg(doc, 'circle', `sx-chart__dot${row && row.marked ? ' sx-chart__dot--marked' : ''}`);
    attrs(dot, {
      cx: X(p.i).toFixed(1), cy: Y(p.value).toFixed(1),
      r: row && row.marked ? 4.5 : 2,
      'data-dot-lot': p.lot,
      'data-dot-marked': row && row.marked ? '1' : '0',
    });
    s.appendChild(dot);
  }
  // Special-evaluation lots ride ON the axis, distinct from the line, never in it.
  for (const p of series.special) {
    const tick = svg(doc, 'rect', 'sx-chart__special');
    attrs(tick, {
      x: (X(p.i) - 2.5).toFixed(1), y: (CHART.top + innerH - 4).toFixed(1),
      width: 5, height: 8, 'data-special-lot': p.lot,
    });
    s.appendChild(tick);
  }

  const axis = svg(doc, 'line', 'sx-chart__axis');
  attrs(axis, {
    x1: CHART.left, y1: (CHART.top + innerH).toFixed(1),
    x2: (CHART.w - CHART.right), y2: (CHART.top + innerH).toFixed(1),
  });
  s.appendChild(axis);
  box.appendChild(s);

  const foot = el(doc, 'div', 'sx-chart__foot');
  foot.appendChild(el(doc, 'span', 'sx-chart__axislabel', '생산 순서 →'));
  foot.appendChild(el(doc, 'span', 'sx-chart__top',
    `최대 ${valueText(series.max, series.column.unit)}`));
  if (series.gaps.length) {
    const g = el(doc, 'span', 'sx-chart__gaps', `미측정 ${series.gaps.length}랏`);
    g.setAttribute('data-chart-gaps', String(series.gaps.length));
    foot.appendChild(g);
  }
  box.appendChild(foot);
  return box;
}

function renderCharts(doc, model) {
  const box = el(doc, 'div', 'sx-charts');
  box.setAttribute('data-panel', 'charts');
  if (!model.series.length) {
    box.appendChild(el(doc, 'p', 'sx-empty', '열이 없어 그릴 차트가 없습니다'));
    return box;
  }
  for (const s of model.series) box.appendChild(renderChart(doc, s, model));
  if (model.events.length) {
    const legend = el(doc, 'p', 'sx-charts__events');
    legend.setAttribute('data-panel', 'chart-events');
    legend.appendChild(el(doc, 'span', 'sx-charts__term', '세로 마커 = 원장 사건'));
    for (const ev of model.events) {
      const chip = el(doc, 'span', 'sx-eventchip');
      chip.setAttribute('data-event-chip', ev.label);
      chip.appendChild(el(doc, 'span', null, ev.label));
      if (!ev.placed) chip.appendChild(el(doc, 'span', 'sx-eventchip__off', '표 밖'));
      legend.appendChild(chip);
    }
    box.appendChild(legend);
  }
  return box;
}

// ── 화면 ─────────────────────────────────────────────────────

function renderHead(doc, model) {
  const head = el(doc, 'header', 'sx-head');
  head.appendChild(el(doc, 'h2', 'sx-head__h', '구성요소 항목별 종합 트렌드'));
  head.appendChild(el(doc, 'p', 'sx-head__sub',
    '행 = 랏 생산 순서 · 열 = 선언된 지표 · 색 = 열마다 자기 기저 대비 배수. 고르기 전에 눈에 들어오는 것이 이 화면의 목적입니다.'));

  const meta = el(doc, 'div', 'sx-head__meta');
  meta.setAttribute('data-panel', 'counts');
  const stat = (term, value, key) => {
    const s = el(doc, 'span', 'sx-stat');
    s.setAttribute('data-stat', key);
    s.appendChild(el(doc, 'span', 'sx-stat__n', value));
    s.appendChild(el(doc, 'span', 'sx-stat__term', term));
    meta.appendChild(s);
  };
  stat('랏', countText(model.counts.lots), 'lots');
  stat('특수평가', countText(model.counts.special), 'special');
  stat('마킹', countText(model.counts.marked), 'marked');
  head.appendChild(meta);

  const order = el(doc, 'p', `sx-order${model.order.ok ? '' : ' sx-order--gap'}`);
  order.setAttribute('data-order-ok', model.order.ok ? '1' : '0');
  order.textContent = `행 순서: ${model.order.why}`;
  head.appendChild(order);

  if (model.strayMarks.length) {
    const stray = el(doc, 'p', 'sx-stray');
    stray.setAttribute('data-stray-marks', String(model.strayMarks.length));
    stray.textContent = `표에 없는 마킹 ${model.strayMarks.length}건: ${model.strayMarks.join(', ')} — 이 구간 밖의 랏입니다`;
    head.appendChild(stray);
  }
  return head;
}

/**
 * The whole screen.
 *
 * `notice` is nullable and is the ONLY thing that changes between "the aggregate
 * is in flight", "the route is not deployed" and "here is the answer" — every
 * panel below renders in all three, saying what it does not know.
 */
export function renderSurprise(doc, mount, model, notice, axisData) {
  clear(mount);
  const root = el(doc, 'section', 'sx');
  root.setAttribute('data-view', 'surprise');
  root.setAttribute('data-state', model.state);

  root.appendChild(renderHead(doc, model));
  if (notice) root.appendChild(renderNotice(doc, notice));
  root.appendChild(renderColumnBar(doc, model));
  root.appendChild(renderTable(doc, model));
  root.appendChild(renderLegend(doc, model));

  const charts = el(doc, 'section', 'sx-section');
  charts.appendChild(el(doc, 'h3', 'sx-section__h', '같은 표를 선으로 — 생산 순서 축'));
  charts.appendChild(el(doc, 'p', 'sx-section__sub',
    '지표마다 작은 차트 하나. 단위가 달라 겹치면 서로를 가립니다. 표에서 마킹하면 그 랏의 점이 굵어집니다.'));
  charts.appendChild(renderCharts(doc, model));
  root.appendChild(charts);

  const maps = el(doc, 'section', 'sx-section');
  maps.setAttribute('data-panel', 'maps-section');
  maps.appendChild(el(doc, 'h3', 'sx-section__h', '마킹한 랏 — 본딩축 · DT축 · 코어축'));
  maps.appendChild(el(doc, 'p', 'sx-section__sub',
    '같은 불량 칩을 transferred 걷기로 세 좌표계에 투영합니다. 어느 축에서 뭉치는지가 기전 힌트입니다.'));
  maps.appendChild(renderAxisMaps(doc, model,
    (axisData && axisData.maps) || null, (axisData && axisData.floors) || null));
  root.appendChild(maps);

  if (model.generatedAt) {
    root.appendChild(el(doc, 'p', 'sx-generated', `집계 시각 ${model.generatedAt}`));
  }
  mount.appendChild(root);
  return root;
}
