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

/**
 * 🔴 THE UNIT IS WHATEVER THE AXIS SAYS IT IS — never the word 「랏」.
 *
 * Standing owner principle: 「그냥 랏이란 단위를 잊으라 그래」. The lot survives as a
 * VALUE (a label, a filter, a colour-by) but never in the UNIT position of a count,
 * a population or a marking sentence. Hardcoding 「랏」 was how a table listing
 * wafers still told the reader it was counting lots.
 */
const unitOf = (model) => (model && model.rowAxis && model.rowAxis.label) || '행';

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
    // The resolved set goes in, so removing a column the URL never named still
    // removes it — see `materializeColumns`.
    const drop = link(doc, 'sx-colchip__drop', '✕',
      withoutColumn(model.question, col, model.columns));
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
    // 🔴 A SCREEN MUST NOT ASSERT COMPLETENESS IT HAS NOT GOT. This said 「선언된
    // 지표가 전부 올라와 있습니다」 while 1 of 12 addressable columns was up — the
    // aggregate reader was dropping every declaration (see `metricCatalog`), so
    // the bar was reporting its own blindness as a full house. It now states what
    // it can count, and claims completeness only when the numbers agree.
    const up = model.columns.length;
    const space = model.catalog.items.length * model.catalog.aggregates.length;
    let text;
    if (!model.catalog.aggregates.length) text = '집계 선언 미보고 — 추가할 후보를 셀 수 없습니다';
    else if (space > up) text = `추가 후보 없음 — 선언 ${space}개 중 ${up}개 올라옴 (나머지는 이 응답에 없음)`;
    else text = `선언된 ${space}개가 전부 올라와 있습니다`;
    const none = el(doc, 'span', 'sx-cols__none', text);
    attrs(none, { 'data-add-space': String(space), 'data-add-up': String(up) });
    add.appendChild(none);
  }
  for (const col of model.available) {
    const a = link(doc, 'sx-coladd', `+ ${col.label}`,
      withColumn(model.question, col, model.columns));
    a.setAttribute('data-col-add', col.key);
    add.appendChild(a);
  }
  box.appendChild(add);

  // Items the kind catalog declares but the metric declaration has no aggregate
  // for. 빈 축 정직 — an item nobody can chart is still an item that exists.
  const itemOnly = model.catalog.items.filter((it) => it.source === 'catalog_only');
  if (itemOnly.length) {
    const gap = el(doc, 'div', 'sx-cols__row sx-cols__row--gap');
    gap.setAttribute('data-panel', 'columns-undeclared');
    gap.appendChild(el(doc, 'span', 'sx-cols__term', '집계 미선언 항목'));
    for (const it of itemOnly) {
      const chip = el(doc, 'span', 'sx-itemchip');
      chip.setAttribute('data-item', it.kind);
      chip.appendChild(el(doc, 'span', 'sx-itemchip__label', it.label));
      chip.appendChild(el(doc, 'span', 'sx-itemchip__n',
        it.atoms === null ? '건수 미보고' : `${countText(it.atoms)}건`));
      gap.appendChild(chip);
    }
    box.appendChild(gap);
  }
  return box;
}

/**
 * 행 축 선택기 — what one column IS.
 *
 * 🔴 THE AXIS IS THE MOST CONSEQUENTIAL THING ON THIS SCREEN and it was invisible.
 * A column meant a LOT, so marking one column marked 25 wafers, and nothing on
 * screen said so. The default is the wafer now; this bar is what keeps the lot
 * axis reachable rather than deleted, and what makes the current unit legible.
 *
 * Every option comes from the server's `axes_available` — no axis list here.
 *
 * 🔴 SWITCHING AXES CLEARS THE MARKS. A lot id is not a wafer id: carrying marks
 * across would leave the URL naming rows that cannot exist on the new axis, and
 * the contrast would then be scoped to ghosts. The stray-mark reporter would
 * catch it, but the honest thing is not to create them.
 */
function renderAxisBar(doc, model) {
  const box = el(doc, 'div', 'sx-axes');
  box.setAttribute('data-panel', 'axes');
  box.appendChild(el(doc, 'span', 'sx-cols__term', '행 축'));
  if (!model.axesAvailable.length) {
    box.appendChild(el(doc, 'span', 'sx-cols__none',
      model.rowAxis.label
        ? `${model.rowAxis.label} — 선택 가능한 축 미보고`
        : '축 선언 미보고'));
    return box;
  }
  for (const axis of model.axesAvailable) {
    const on = axis.name === model.rowAxis.name;
    const a = link(doc, `sx-axis${on ? ' sx-axis--on' : ''}`, axis.label || axis.name,
      { ...model.question, by: axis.name, marked: [], slot: '' });
    attrs(a, { 'data-axis': axis.name, 'data-axis-on': on ? '1' : '0' });
    if (on) a.setAttribute('aria-current', 'true');
    box.appendChild(a);
  }
  return box;
}

// ── 표 ───────────────────────────────────────────────────────

/**
 * One METRIC's header: 항목 · 집계 · 기저 — the denominator's definition included.
 *
 * 🔴 IT IS A ROW HEADER NOW (`scope="row"`), not a column header. The wire still
 * calls these `columns[]` and this file still calls them columns, because that is
 * the server's word for "a metric × an aggregate" and renaming it here would put
 * a translation layer between the address bar and the request. What changed is
 * only where they are DRAWN — see `renderTable`.
 */
function renderColumnHead(doc, col) {
  const th = el(doc, 'th', 'sx-th sx-th--metric');
  attrs(th, { scope: 'row', 'data-col': col.key });
  th.appendChild(el(doc, 'span', 'sx-th__metric', col.kindLabel));
  th.appendChild(el(doc, 'span', 'sx-th__agg', col.aggLabel));
  const foot = el(doc, 'span', 'sx-th__base');
  if (col.baseline !== null && col.baseline !== undefined) {
    foot.textContent = `기저 ${valueText(col.baseline, col.valueKind)}`;
    foot.setAttribute('data-baseline', String(col.baseline));
  } else {
    foot.textContent = '기저 미보고';
    foot.setAttribute('data-baseline', 'none');
  }
  th.appendChild(foot);
  if (col.denominatorLabel) {
    th.appendChild(el(doc, 'span', 'sx-th__den', `분모 ${col.denominatorLabel}`));
  }
  // 🔴 THE SERVER'S COLUMN-LEVEL DECLARATION, FIRST AND GENERIC. Any state other
  // than `ready` renders here with the server's own reason — so the 「채점 불가」
  // declaration of R-2026-08-14-G lights up the moment the server ships it, with
  // no edit to this file. It is NOT emitted today (checked in `ledger_lots.py`:
  // the only non-ready column state is `unmeasurable`, set when a relation is
  // absent), and that gap is reported rather than filled in from here.
  if (col.state !== 'ready') {
    const bad = el(doc, 'span', 'sx-th__flag sx-th__flag--declared',
      col.reason ? `채점 불가 — ${col.reason}` : '채점 불가 — 사유 미보고');
    bad.setAttribute('data-col-state', col.state);
    th.appendChild(bad);
  } else if (col.observed && col.observed.neverPainted) {
    // 🔴 A COLUMN THAT WENT ENTIRELY UNPAINTED SAYS SO. Not 「채점 불가」 — that is
    // the server's claim about the metric and this is a fact about this answer:
    // N cells measured, none reached the first step, and the largest multiple was
    // this. A reader can no longer read the absence of colour as 「정상」, and a
    // reader also cannot mistake it for a declaration, because it never claims
    // the metric CANNOT be graded — only that here, it was not.
    const flag = el(doc, 'span', 'sx-th__flag');
    flag.setAttribute('data-col-unpainted', String(col.observed.measured));
    const top = col.observed.maxRatio;
    const cut = col.observed.firstThreshold;
    flag.textContent = `이 응답에서 칠해진 칸 0 / ${col.observed.measured}`
      + (top !== null && cut !== null ? ` · 최대 ${liftText(top)}, 첫 문턱 ${cut}배` : '');
    th.appendChild(flag);
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

  td.appendChild(el(doc, 'span', 'sx-cell__v', valueText(reading.value, column.valueKind)));
  const frac = fractionText(reading);
  if (frac) {
    const f = el(doc, 'span', 'sx-cell__f', frac);
    attrs(f, {
      'data-numerator': reading.n === null ? null : String(reading.n),
      'data-denominator': reading.of === null ? null : String(reading.of),
    });
    td.appendChild(f);
  }
  if (reading.ratio !== null) {
    const ratio = el(doc, 'span', 'sx-cell__lift', liftText(reading.ratio));
    ratio.setAttribute('data-lift', String(reading.ratio));
    td.appendChild(ratio);
  }
  return td;
}

/**
 * ONE LOT, as a COLUMN HEADER.
 *
 * 🔴 THE TABLE RUNS SIDEWAYS NOW — product owner, 2026-08-14: 「상단 트렌드 표는
 * 세로 말고 가로로 리스팅해」. Everything a lot used to carry across a row (the
 * mark box, the lineage link, the production ordinal, the bucket badge, the unit
 * count) is stacked into its column header instead, in that reading order.
 *
 * Nothing about a lot was dropped in the move: the SAME `data-*` attributes ride
 * here that used to ride on `sx-row`, so marking, the bucket reading and the
 * baseline-exclusion flag are all still addressable — they just changed axis.
 */
function renderLotHead(doc, row) {
  const th = el(doc, 'th', `sx-th sx-lotcol${row.marked ? ' sx-lotcol--marked' : ''}`);
  attrs(th, {
    scope: 'col',
    'data-lot': row.lot,
    'data-row': row.row,
    'data-bucket': row.bucket,
    'data-counts-baseline': row.counts ? '1' : '0',
    'data-marked': row.marked ? '1' : '0',
  });

  const markWrap = el(doc, 'label', 'sx-lotcol__mark');
  const box = doc.createElement('input');
  attrs(box, {
    type: 'checkbox',
    'data-mark-lot': row.row,
    'aria-label': `${row.lot} 마킹`,
  });
  // `.checked` is the property the browser reads; the attribute alone would only
  // set the DEFAULT and a re-render would leave stale boxes ticked.
  box.checked = row.marked;
  if (row.marked) box.setAttribute('checked', 'checked');
  markWrap.appendChild(box);
  th.appendChild(markWrap);

  // The lineage answer for this lot — the other question on this same page.
  const a = el(doc, 'a', 'sx-lot', row.lot);
  a.setAttribute('href', `?lot=${encodeURIComponent(row.lot)}`);
  a.setAttribute('data-lot-link', row.lot);
  th.appendChild(a);

  const foot = el(doc, 'span', 'sx-lotcol__foot');
  if (row.seq !== null) foot.appendChild(el(doc, 'span', 'sx-row__seq', `#${row.seq}`));
  const badge = el(doc, 'span', `sx-bucket sx-bucket--${row.bucket}`, row.bucketLabel);
  badge.setAttribute('data-bucket-badge', row.bucket);
  foot.appendChild(badge);
  th.appendChild(foot);

  // `universe` is the lot's unit count, NOT the inspected-chip denominator —
  // those differ by ~5× and the denominator rides in each cell's fraction.
  const units = el(doc, 'span', 'sx-lotcol__units');
  if (row.universe === null) {
    units.className = 'sx-lotcol__units sx-row__chips--none';
    units.textContent = '단위 수 미보고';
    units.setAttribute('data-chips', 'none');
  } else {
    units.textContent = countText(row.universe);
    units.setAttribute('data-universe', String(row.universe));
  }
  th.appendChild(units);
  return th;
}

/**
 * The table, TRANSPOSED: rows = 지표, columns = 랏 생산 순서, newest on the right.
 *
 * 🔴 WHY SIDEWAYS. A trend is read along the time axis, and the eye reads left to
 * right — with lots down the page the owner had to scan vertically for a trend and
 * horizontally for a comparison, which is the wrong way round for both. The lots
 * arrive from `/lots` in ascending `order_index` (oldest first, verified against
 * the live route), and the columns are laid out in that same array order, so the
 * NEWEST LOT IS THE RIGHTMOST COLUMN with no sorting in this file.
 *
 * 🔴 AND THE METRIC AXIS IS A LIST, NOT A LAYOUT. `model.columns` is the resolved
 * metric set — the URL's `columns=` question intersected with the server's
 * declaration — and this function does nothing but iterate it. A metric declared
 * tomorrow becomes a row here with no line changing, the row ORDER is the list's
 * order, and a panel that edits that list is a panel that edits the URL. There is
 * no hardcoded sequence of rows anywhere in this file.
 *
 * 🔴 WHAT SURVIVED THE TRANSPOSE UNCHANGED: `renderCell` is called verbatim, so
 * the conditional formatting (`data-heat`, `sx-cell--hN`), the fraction, the lift
 * and — the one that must never be quietly dropped — the THIRD BUCKET, 미검사, are
 * exactly what they were. 미검사 · 측정된 0 · 미보고 are still three different
 * cells with three different `data-cell-state`s.
 */
function renderTable(doc, model) {
  const wrap = el(doc, 'div', 'sx-tablewrap');
  attrs(wrap, { 'data-panel': 'table', 'data-orient': 'metric-rows' });

  const table = el(doc, 'table', 'sx-table sx-table--t');
  attrs(table, {
    'data-lot-count': String(model.rows.length),
    'data-metric-count': String(model.columns.length),
  });

  // ── the head: one cell per lot, in production order ──
  const head = el(doc, 'thead');
  const hr = el(doc, 'tr', 'sx-hrow');
  const corner = el(doc, 'th', 'sx-th sx-th--corner');
  corner.setAttribute('scope', 'col');
  corner.appendChild(el(doc, 'span', 'sx-th__corner-a', '지표'));
  // 🔴 THE LOT AXIS NAMES ITSELF. `row_axis.label` is 「본딩 랏」 today and the axis
  // is switchable (`by=`), so a hardcoded 「랏」 would mislabel the axis the moment
  // somebody asks a different one. The arrow is the direction of time.
  corner.appendChild(el(doc, 'span', 'sx-th__corner-b',
    `${model.rowAxis.label || '행'} 생산 순서 →`));
  hr.appendChild(corner);
  for (const row of model.rows) hr.appendChild(renderLotHead(doc, row));
  head.appendChild(hr);
  table.appendChild(head);

  // ── the body: one row per metric ──
  const body = el(doc, 'tbody', 'sx-tbody');
  for (const col of model.columns) {
    const tr = el(doc, 'tr', 'sx-mrow');
    attrs(tr, { 'data-col': col.key, 'data-metric-row': '1' });
    tr.appendChild(renderColumnHead(doc, col));
    for (const row of model.rows) {
      const hit = row.cells.find((c) => c.column.key === col.key);
      if (!hit) continue;
      const td = renderCell(doc, hit);
      // The marked lot is a COLUMN now, and CSS cannot select a column — so the
      // membership is written on every cell of it, the same fact the header
      // carries.
      td.setAttribute('data-lot', row.lot);
      if (row.marked) {
        td.setAttribute('data-marked', '1');
        td.className = `${td.className} sx-cell--marked`;
      }
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  if (!model.columns.length) {
    // 빈 축 정직 — the metric axis is empty, and the table says so in its own
    // voice rather than disappearing.
    const tr = el(doc, 'tr', 'sx-mrow sx-mrow--nocol');
    const th = el(doc, 'th', 'sx-th sx-th--nocol', '지표');
    th.setAttribute('scope', 'row');
    tr.appendChild(th);
    const td = el(doc, 'td', 'sx-cell sx-cell--nocol', '지표 없음');
    if (model.rows.length) td.setAttribute('colspan', String(model.rows.length));
    tr.appendChild(td);
    body.appendChild(tr);
  }
  table.appendChild(body);
  wrap.appendChild(table);

  if (!model.rows.length) {
    wrap.appendChild(el(doc, 'p', 'sx-empty',
      model.state === 'unknown'
        ? '집계 응답 없음 — 열을 그릴 근거가 없습니다'
        : `이 구간에 ${unitOf(model)}이 없습니다`));
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
  heat.appendChild(el(doc, 'span', 'sx-legend__term', '조건부서식 — 지표마다 자기 기저 대비 배수'));
  // 🔴 THE LADDER IS THE WIRE'S, LABELS INCLUDED. A legend that described a scale
  // the paint does not use is worse than no legend.
  for (const step of model.ladder) {
    const item = el(doc, 'span', `sx-legend__item sx-legend__item--h${step.level}`);
    item.setAttribute('data-heat-key', String(step.level));
    item.appendChild(el(doc, 'span', 'sx-legend__swatch'));
    item.appendChild(el(doc, 'span', 'sx-legend__label',
      step.label || HEAT_LABELS[step.level] || `단계 ${step.level}`));
    item.appendChild(el(doc, 'span', 'sx-legend__cut',
      step.at === null ? '문턱 미보고' : `${step.at}배 이상`));
    heat.appendChild(item);
  }
  if (!model.ladder.length) {
    heat.appendChild(el(doc, 'span', 'sx-legend__cut', '문턱 선언 미보고 — 서버가 단계를 싣지 않았습니다'));
  }
  // 🔴 WHO ASSIGNED THE STEP, SAID ON SCREEN. The level is the server's number in
  // every case — this line only says whether the BANDS beside the swatches came
  // from the server's declaration or are the documented defaults, so a reader
  // cannot mistake the cut points for something the browser decided.
  heat.appendChild(el(doc, 'span', 'sx-legend__src',
    model.ladder.length ? '단계 판정·구간 선언: 서버' : '단계 판정: 서버'));
  box.appendChild(heat);

  const states = el(doc, 'div', 'sx-legend__group');
  states.appendChild(el(doc, 'span', 'sx-legend__term', '칸 상태'));
  // 🔴 SPELLED OUT BECAUSE THE DIFFERENCE IS THE POINT. 미검사 is not a good
  // result and must never be read as one.
  const cellStates = [
    ['unscanned', '— 미검사', '검사 모집단 밖입니다. 0이 아니라 «모름»입니다'],
    ['measured', '0 측정된 0', '검사했고 발생이 0이었습니다'],
    ['unmeasurable', '측정 불가', `이 항목이 이 ${unitOf(model)}에서 정의되지 않습니다`],
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
    '기저에서 빠지는 행은 뱃지로만 구분하고 칠하지 않습니다 — 숨기지도 않습니다. '
    + '구분자는 서버 선언(bucket.counts_toward_baseline)이며, 지금은 전 행이 「미상 · 기저 포함」입니다.'));
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
    `${series.plotted}/${series.total} ${unitOf(model)} 표시`));
  box.appendChild(cap);

  if (!series.points.length) {
    // 🔴 AN EMPTY CHART STILL CARRIES ITS COUNTS. "nothing to draw" and "40 lots
    // went unmeasured" are different facts, and dropping the second one turns a
    // measurement gap into a blank box the reader will read as "nothing happened".
    const none = el(doc, 'p', 'sx-chart__none',
      series.gaps.length ? `측정값 없음 — ${series.gaps.length}${unitOf(model)} 미측정` : '그릴 측정값 없음');
    none.setAttribute('data-chart-empty', '1');
    if (series.gaps.length) none.setAttribute('data-chart-gaps', String(series.gaps.length));
    box.appendChild(none);
    if (series.special.length) {
      const sp = el(doc, 'p', 'sx-chart__none', `특수평가 ${series.special.length}${unitOf(model)}은 선에서 제외됩니다`);
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
    'aria-label': `${series.column.label} 생산 순서 추이, ${series.plotted}개 ${unitOf(model)}`,
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
    `최대 ${valueText(series.max, series.column.valueKind)}`));
  if (series.gaps.length) {
    const g = el(doc, 'span', 'sx-chart__gaps', `미측정 ${series.gaps.length}${unitOf(model)}`);
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
    `행 = 선언된 지표 · 열 = ${unitOf(model)} 생산 순서(최신이 오른쪽) · 색 = 지표마다 자기 기저 대비 배수. `
    + '트렌드는 가로로 읽습니다.'));

  const meta = el(doc, 'div', 'sx-head__meta');
  meta.setAttribute('data-panel', 'counts');
  const stat = (term, value, key) => {
    const s = el(doc, 'span', 'sx-stat');
    s.setAttribute('data-stat', key);
    s.appendChild(el(doc, 'span', 'sx-stat__n', value));
    s.appendChild(el(doc, 'span', 'sx-stat__term', term));
    meta.appendChild(s);
  };
  stat(model.rowAxis.label || '행', countText(model.counts.rows), 'rows');
  stat('기저 제외', countText(model.counts.offBaseline), 'off_baseline');
  stat('마킹', countText(model.counts.marked), 'marked');
  head.appendChild(meta);

  // 🔴 WHAT WOULD CHANGE THE MEANING OF EVERY NUMBER ABOVE, SAID BESIDE THEM.
  const facts = el(doc, 'div', 'sx-facts');
  facts.setAttribute('data-panel', 'facts');
  const fact = (key, text, tone) => {
    const f = el(doc, 'span', `sx-fact${tone ? ` sx-fact--${tone}` : ''}`, text);
    f.setAttribute('data-fact', key);
    facts.appendChild(f);
  };
  if (model.window.forced) {
    fact('window_forced', `구간 강제됨 — ${model.window.forcedReason || '사유 미보고'}`, 'warn');
  }
  // 🔴 A CAP THE SCREEN DOES NOT MENTION IS A SILENT TRUNCATION — and here it is
  // the worst kind, because a wafer missing from the table is a wafer nobody can
  // mark. So the bound says its own size, the whole size, and offers the way back.
  if (model.truncated) {
    const shown = model.rowsReturned;
    const total = model.rowsTotal;
    const back = Number(model.question.offset || 0);
    const span = shown || 0;
    const f = el(doc, 'span', 'sx-fact sx-fact--cap');
    f.setAttribute('data-fact', 'capped');
    // 「장」 for wafers reads as Korean; any other axis takes its own label rather
    // than a counter this file invented. Closed enum, raw fallback — the same
    // pattern the bucket and heat labels use.
    const c = model.rowAxis.name === 'wafer' ? '장' : ` ${unitOf(model)}`;
    f.appendChild(el(doc, 'span', null,
      `최신 ${countText(shown)}${c} — 전체 ${countText(total)}${c}`));
    if (back > 0) {
      const prev = link(doc, 'sx-fact__more', '· 이전 보기', {
        ...model.question,
        limit: String(span),
        offset: String(Math.max(0, back - span)),
      });
      prev.setAttribute('data-cap-prev', String(Math.max(0, back - span)));
      f.appendChild(prev);
    }
    if (back + span < (total || 0)) {
      const next = link(doc, 'sx-fact__more', '· 이후 보기', {
        ...model.question,
        limit: String(span),
        offset: String(Math.min((total || 0) - span, back + span)),
      });
      next.setAttribute('data-cap-next', '1');
      f.appendChild(next);
    }
    // 전체 보기 — the cap is a default, never a wall.
    const all = link(doc, 'sx-fact__more', '· 전체 보기',
      { ...model.question, limit: '', offset: '', all: '1' });
    all.setAttribute('data-cap-all', '1');
    f.appendChild(all);
    facts.appendChild(f);
  }
  if (model.provenance.source) {
    fact('provenance',
      model.provenance.ledgerBacked
        ? `출처 ${model.provenance.source} · 원장 기반`
        : `출처 ${model.provenance.source} · 원장 미기반`,
      model.provenance.ledgerBacked ? null : 'warn');
  }
  for (const nte of model.notes) fact(nte.code || 'note', nte.message, 'warn');
  if (facts.children.length) head.appendChild(facts);
  if (model.provenance.note) {
    head.appendChild(el(doc, 'p', 'sx-provnote', model.provenance.note));
  }

  const order = el(doc, 'p', `sx-order${model.order.ok ? '' : ' sx-order--gap'}`);
  order.setAttribute('data-order-ok', model.order.ok ? '1' : '0');
  order.textContent = `행 순서: ${model.order.why}`;
  head.appendChild(order);

  if (model.strayMarks.length) {
    const stray = el(doc, 'p', 'sx-stray');
    stray.setAttribute('data-stray-marks', String(model.strayMarks.length));
    // 🔴 OFF-PAGE IS NOT UNMARKED. The newest-N cap can leave a marked wafer
    // outside the loaded page; it still counts, it still scopes the contrast, and
    // it must not read as though the reader had unmarked it. The link brings the
    // page back to where they are.
    stray.textContent = `이 페이지 밖 마킹 ${model.strayMarks.length}건: ${model.strayMarks.join(', ')}`
      + ' — 대조·개수에는 그대로 들어갑니다';
    const showAll = link(doc, 'sx-stray__all', '· 전체 보기',
      { ...model.question, limit: '', offset: '', all: '1' });
    showAll.setAttribute('data-stray-all', '1');
    stray.appendChild(showAll);
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
/**
 * 🔴 A MARK MUST NOT REBUILD THE TABLE. This is the other half of the lag fix.
 *
 * A cap alone still repaints everything it kept: ticking one checkbox tore down
 * and rebuilt every column × every metric row, plus the chart, plus the maps —
 * and at 2,600 columns that hung the renderer for over 30 seconds (measured: the
 * click never returned inside a 30s budget). Marking is a SELECTION, not a new
 * answer, so it touches only what marking changes:
 *
 *   · the marked column's header flag, class and checkbox
 *   · that column's cells' membership flag
 *   · the marked count
 *   · the chart dots (marked points are drawn larger)
 *   · the maps and the contrast rail, which are keyed on the marked set
 *
 * Everything else — the table's structure, every value, every heat class — is
 * already correct and is left alone. Returns false when the DOM is not in a state
 * it can patch, so the caller falls back to a full render rather than guessing.
 */
export function updateMarks(doc, root, model, axisData, contrastNode) {
  if (!root) return false;
  const table = root.querySelector('.sx-table');
  if (!table) return false;

  const marked = new Set(model.marked.map((r) => r.row));
  const markedLots = new Set(model.marked.map((r) => r.lot));
  for (const th of table.querySelectorAll('.sx-lotcol')) {
    const on = marked.has(th.getAttribute('data-row'));
    th.setAttribute('data-marked', on ? '1' : '0');
    th.classList.toggle('sx-lotcol--marked', on);
    const box = th.querySelector('input[data-mark-lot]');
    if (box) box.checked = on;
  }
  for (const td of table.querySelectorAll('.sx-tbody td[data-lot]')) {
    const on = markedLots.has(td.getAttribute('data-lot'));
    if (on) td.setAttribute('data-marked', '1');
    else td.removeAttribute('data-marked');
    td.classList.toggle('sx-cell--marked', on);
  }

  const stat = root.querySelector('[data-stat="marked"] .sx-stat__n');
  if (stat) stat.textContent = countText(model.counts.marked);

  // The three panels that ARE keyed on the marked set get rebuilt — they are
  // small beside the table, and they would otherwise show a stale selection.
  const charts = root.querySelector('[data-panel="charts"]');
  if (charts && charts.parentNode) charts.parentNode.replaceChild(renderCharts(doc, model), charts);

  const maps = root.querySelector('[data-panel="maps-body"]');
  if (maps && maps.parentNode) {
    maps.parentNode.replaceChild(renderAxisMaps(doc, model,
      (axisData && axisData.maps) || null, (axisData && axisData.floors) || null), maps);
  }

  const slot = root.querySelector('[data-panel="contrast-slot"]');
  if (slot) {
    while (slot.firstChild) slot.removeChild(slot.firstChild);
    if (contrastNode) slot.appendChild(contrastNode);
  } else if (contrastNode) {
    // The rail did not exist at the last full render (nothing was marked then).
    return false;
  }
  return true;
}

export function renderSurprise(doc, mount, model, notice, axisData, contrastNode) {
  clear(mount);
  const root = el(doc, 'section', 'sx');
  root.setAttribute('data-view', 'surprise');
  root.setAttribute('data-state', model.state);

  root.appendChild(renderHead(doc, model));
  if (notice) root.appendChild(renderNotice(doc, notice));
  root.appendChild(renderAxisBar(doc, model));
  root.appendChild(renderColumnBar(doc, model));
  root.appendChild(renderTable(doc, model));
  root.appendChild(renderLegend(doc, model));

  // 🔴 THE ANSWER TO MULTI-MARKING GOES HERE — directly under the table the marks
  // were made in, above the pictures. Marking several lots asks "what is different
  // about these", and a pile of wafer maps restates the question once per wafer
  // instead of answering it. The panel is built by the entry file (it is a fetch
  // of its own) and handed in as a node, so this renderer stays a pure function of
  // the model it was given.
  if (contrastNode) {
    const slot = el(doc, 'section', 'sx-section sx-section--contrast');
    slot.setAttribute('data-panel', 'contrast-slot');
    slot.appendChild(contrastNode);
    root.appendChild(slot);
  }

  const charts = el(doc, 'section', 'sx-section');
  charts.appendChild(el(doc, 'h3', 'sx-section__h', '같은 표를 선으로 — 생산 순서 축'));
  charts.appendChild(el(doc, 'p', 'sx-section__sub',
    `지표마다 작은 차트 하나. 단위가 달라 겹치면 서로를 가립니다. 표에서 마킹하면 그 ${unitOf(model)}의 점이 굵어집니다.`));
  charts.appendChild(renderCharts(doc, model));
  root.appendChild(charts);

  const maps = el(doc, 'section', 'sx-section');
  maps.setAttribute('data-panel', 'maps-section');
  maps.appendChild(el(doc, 'h3', 'sx-section__h', `마킹한 ${unitOf(model)} — 본딩축 · DT축 · 코어축`));
  maps.appendChild(el(doc, 'p', 'sx-section__sub',
    '같은 불량 칩을 transferred 걷기로 세 좌표계에 투영합니다. 어느 축에서 뭉치는지가 기전 힌트입니다.'));
  const mapsBody = renderAxisMaps(doc, model,
    (axisData && axisData.maps) || null, (axisData && axisData.floors) || null);
  // Named so `updateMarks` can replace exactly this and nothing around it.
  mapsBody.setAttribute('data-panel', 'maps-body');
  maps.appendChild(mapsBody);
  root.appendChild(maps);

  if (model.generatedAt) {
    root.appendChild(el(doc, 'p', 'sx-generated', `집계 시각 ${model.generatedAt}`));
  }
  mount.appendChild(root);
  return root;
}
