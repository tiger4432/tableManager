// ============================================================
// surprise_core.js — 놀라움 장치(화면 ①)를 모델로. THE SURPRISE DEVICE.
//
// PURE. No DOM, no network, no `window`. It runs under bare node, which is why
// `tests/surprise_harness.mjs` drives it directly — same contract as
// `ledger_trace_core.js`, `case_control_core.js`, `ontology_structure_core.js`.
//
// 🔴 WHAT THIS SCREEN IS FOR (SCENARIO_CONSOLE_BRIEF §0-ter, owner-confirmed
// 2026-08-14). It is called the surprise device because THERE IS NO PICKER: the
// operator must see something odd BEFORE choosing what to look at. Rows are lots
// in PRODUCTION ORDER, columns are the declared metrics side by side, and the
// conditional formatting runs down the ITEM axis — each column against its own
// baseline. Reading the table is the analysis; selecting is what comes after.
//
// 🔴 NOTHING HERE IS A METRIC LIST. The owner's first confirmed constraint:
// "열 구성 = {항목 × 집계}는 사용자 커스텀이고 URL에 실린다. 지표 자체는 config
// 선언이니 목록을 하드코딩하지 말 것." So:
//
//   WHAT CAN BE A COLUMN   comes from the server's metric DECLARATION
//                          (`metrics[].aggregates[]`), degrading to the kind
//                          catalog this page already fetches. A metric declared
//                          tomorrow appears without a line changing here.
//   WHICH COLUMNS ARE UP   comes from the URL (`cols=void:chip_rate,…`).
//                          The column set IS the question, so it is shareable.
//
// The only literals in this file are: the URL parameter names, LABEL MAPS FOR
// CLOSED WIRE ENUMS (bucket, unit), and the conditional-formatting scale — which
// is a rendering scale, not a metric list, and the server can override it. An
// enum member this file has never heard of survives under its raw wire spelling
// rather than vanishing; that is the test of the difference.
//
// 🔴 AND 미검사 IS NOT 0. Second confirmed constraint, and the one that has
// already cost a round: `Number(null) === 0`, so a cell that was never inspected
// becomes a measured zero the moment anybody reaches for `Number()`. Every
// numeric read in this file goes through `numOrNull`, every cell carries a
// `state`, and 「—」(미검사) and 「0」(측정된 0) are DIFFERENT STATES with
// different text, different `data-*`, and different formatting. `cellReading`
// is the only door a number uses to reach the table.
//
// 🔴 AND THE STATE IS THE SERVER'S WORD, NOT AN INFERENCE FROM THE NUMBER.
// Measured on the live fixture (server lane, 2026-08-14): only 725 of a lot's
// 3,525 chips are inspected — 20.6%. A client that took the LOT SIZE for the
// denominator would be wrong by a factor of five, and a client that read
// "unscanned" off a null would call 80% of a wafer clean. So the four wire
// states — `measured` | `unscanned` | `no_denominator` | `unmeasurable` — are
// consumed verbatim, and this file never derives one from a value.
//
// 🔴 AND `level` — THE CONDITIONAL-FORMATTING STEP — IS THE SERVER'S TOO. It
// arrives per cell and is NOT recomputed here. There is deliberately no
// client-side threshold function in this file: two implementations of one scale
// is how the paint and the numbers come to disagree, and this screen already
// paid that bill once today on `has_denominator`.
//
// ------------------------------------------------------------
// 🔴 THE LANDED CONTRACT — `server/ledger_lots.py` (`56d8aae`), diffed field by
// field on 2026-08-14. THE SERVER IS CANONICAL; where this client's earlier
// proposal disagreed, the client moved.
//
//   GET /api/ledger/lots?columns=<kind:agg,…>&by=&window=&kind=&limit=&offset=
//     -> { state: "absent"|"empty"|"ready", generated_at,
//
//          // 🔴 THE COLUMNS ARE THE RESOLVED SET, not a menu. `columns[].id` is
//          // "<kind>:<aggregate>" and it is the SAME STRING `rows[].cells[].column`
//          // carries, so the two collide by construction.
//          columns: [ { id, kind, kind_label, aggregate, aggregate_label,
//                       value_kind: "ratio"|"count"|"mean", doc,
//                       has_denominator,
//                       denominator: {population, label, methods} | null,
//                       baseline: {value, basis: "median_of_rows", n_rows,
//                                  excluded_rows, excluded_reason},
//                       thresholds: [{level, at, label}],
//                       state: "ready"|"unmeasurable", reason } ],
//          // 🔴 `name`, NOT `aggregate` — verified against the live route
//          // 2026-08-14. This comment said `aggregate` and that is precisely what
//          // made the mismatch look settled for a whole round.
//          aggregates_available: [ {name, label, value_kind, needs_denominator,
//                                   over, doc} ],
//          row_axis: { name, label, about, relation, column, source },
//          axes_available: [ {name, label, about, source} ],
//
//          rows: [ { row, label, order_index,
//                    occurred_at: {first, last},
//                    bucket: {id, label, counts_toward_baseline},
//                    universe: <int>,
//                    cells: [ { column, state, value, n, of,
//                               ratio_to_baseline, level } ] } ],
//
//          populations: {rows_total, rows_returned, rows_truncated},
//          window: {requested, applied, forced, forced_reason},
//          gate: {...}, notes: [{code, message}],
//          provenance: {source, ledger_backed, relations, absent_relations, note} }
//
// DIFFS THIS CLIENT ABSORBED (server won every one):
//   `of`            not `d`          — the denominator's field name
//   `ratio_to_baseline` not `lift`
//   `columns[]`     not `metrics[].aggregates[]`
//   `rows[]`        not `lots[]`;  `cells` is a LIST, not a map
//   `id` uses `:`   not `|`
//   `order_index`   not `seq`;  `label` not `lot`;  `universe` not `inspected.chips`
//   `thresholds` are PER COLUMN, not one page-level `scale`
//   `baseline` is an OBJECT with its basis and its exclusion count
//   `bucket` is an OBJECT and carries `counts_toward_baseline` — which is what
//           decides paint suppression now, instead of matching a literal
//           `special_eval`. The server declares the rule; this file obeys it.
//   no `events` — the ledger carries no chip observations yet, so the trend
//           charts have no vertical markers to draw and say nothing about them.
//
// 🔴 AND ONE STATE IS THIS CLIENT'S OWN, CONFIRMED BY THE LEAD PM. The wire has
// four (`measured`/`unscanned`/`no_denominator`/`unmeasurable`); `unreported` is
// a FIFTH that only this file can produce — the response omitted the cell
// entirely. That is a hole in the ANSWER, not a measurement about the fab, and
// collapsing it into 미검사 would put a claim behind a missing field.
// ------------------------------------------------------------

export const SURPRISE_VIEW = 'surprise';

/**
 * 🔴 THE DEFAULT ROW AXIS IS THE WAFER — a product decision, 2026-08-14.
 *
 * Owner: 「왜 자꾸 마킹 25개씩 물려? 1매씩하라고」. The trend table listed LOTS, and
 * a lot is 25 wafers, so ticking one column marked 25 things. Nothing in the
 * marking code was wrong — it faithfully marked what the column named. The unit
 * was wrong, and that same wrong unit produced the 125-map pile earlier the same
 * evening. The owner has now said twice that the unit is the wafer.
 *
 * Measured before deciding (live, 2,600 wafers): the transposed table renders all
 * 2,600 columns in 968ms with 33,918 nodes and a 16ms scroll interaction, newest
 * still rightmost. So performance did not decide this; the unit did.
 *
 * 🔴 AND THERE IS DELIBERATELY NO DEFAULT `limit` TO GO WITH IT. `limit` alone
 * takes from the OLDEST end (verified: `limit=6` returns order_index 0–5 of
 * 2,600), so capping the wafer axis would quietly show the oldest wafers in a
 * view whose whole premise is that the newest are on the right. The honest bound
 * is a date window, not a row cap.
 *
 * The lot axis is not deleted — it is one chip away, and every axis in the picker
 * comes from the server's `axes_available`.
 */
export const DEFAULT_ROW_AXIS = 'wafer';

/**
 * 🔴 THE NEWEST-END CAP. Owner: 「웨이퍼 리스트 너무 많아서 렉 먹어서 뭐 볼 수가
 * 없는데」 — 2,600 wafer columns made the screen unusable.
 *
 * 🔴 AND `limit` ALONE WOULD HAVE MADE IT WORSE, SILENTLY. Verified: `limit=6`
 * returns `order_index` 0–5 of 2,600 — the OLDEST end — in a view whose whole
 * premise is that the newest are on the right. So the cap is a newest-N PAGE
 * (`offset = total - N`), not a `limit`.
 *
 * 🔴 AND THE DATE WINDOW CANNOT DO THIS JOB ON THIS DATA. Measured: every window
 * (7d/30d/90d/180d) returns the same 50 wafers ending at `SYN-BW-001-25`, while
 * the true newest is `SYN-BW-103-25` — the fixture's `occurred_at` run into the
 * future, so a window ending "now" catches only the earliest lots. The window is
 * still the principled bound and it ships in this round, but it is NOT the
 * default cap, because on this data it would show the oldest 50 and call them
 * recent.
 */
export const WAFER_CAP = 300;

// ── the only literals: closed wire enums, with raw fallback ──

//: Lot buckets. `special_eval` is the one that matters: the owner's second
//: constraint says special-evaluation lots are SHOWN AND MARKED, never hidden and
//: never painted — a filter that drops them would delete the very rows that
//: refute the reading. A bucket this file has never heard of keeps its raw
//: spelling and is treated as unknown-but-present.
const BUCKET_LABELS = {
  production: '양산',
  special_eval: '특수평가',
  unknown: '미상',
};

//: Units, for formatting only. An unknown unit prints the number with the raw
//: unit word appended rather than being dropped.
const UNIT_RATIO = 'ratio';

//: 🔴 FALLBACK WORDS FOR THE LEGEND, AND NOTHING ELSE. The ladder that paints is
//: `columns[].thresholds` off the wire ({level, at, label}); these names are used
//: only when a column carries none, so the legend can still say what a swatch
//: means. Nothing in this file assigns a level — see the header.
export const HEAT_LABELS = ['기저권', '주의', '높음', '심각', '극단'];

const STATES = new Set(['absent', 'empty', 'ready']);

export function surpriseState(body) {
  const s = body && body.state != null ? String(body.state) : '';
  return STATES.has(s) ? s : 'unknown';
}

export const bucketLabel = (bucket, given) => {
  if (given !== null && given !== undefined && String(given) !== '') return String(given);
  const key = bucket === null || bucket === undefined || String(bucket) === '' ? 'unknown' : String(bucket);
  return BUCKET_LABELS[key] || key;
};

/**
 * 🔴 THE ONE NUMERIC DOOR. `Number(null)` is 0 and `Number('')` is 0 — that is
 * the whole defect this screen was warned about, and it is defeated in exactly
 * one place rather than at every call site. A real 0 comes back as 0; everything
 * that is not a finite number comes back as null.
 */
function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'boolean') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function strOrEmpty(v) {
  return v === null || v === undefined ? '' : String(v);
}

function listOf(v) {
  return Array.isArray(v) ? v.filter((x) => x !== null && x !== undefined) : [];
}

// ── the column identity ──────────────────────────────────────

/**
 * One column's key — `{항목}|{집계}`, spelled once.
 *
 * The declaration, the row cell map and the URL all collide on this same string
 * by construction, so a metric renamed on the server cannot silently match the
 * wrong column.
 */
export function colKey(kind, aggregate) {
  return `${strOrEmpty(kind)}:${strOrEmpty(aggregate)}`;
}

/** The URL spelling of one column — identical to the server's `id`. */
export function colToken(col) {
  return colKey(col && col.kind, col && col.aggregate);
}

function parseColToken(token) {
  const raw = strOrEmpty(token).trim();
  if (!raw) return null;
  const at = raw.indexOf(':');
  if (at < 0) return null;
  const kind = raw.slice(0, at).trim();
  const aggregate = raw.slice(at + 1).trim();
  if (!kind || !aggregate) return null;
  return { kind, aggregate };
}

// ── the question, as a URL ───────────────────────────────────

/**
 * Read the surprise question out of a `URLSearchParams`-like.
 *
 * `cols` is the OWNER'S CUSTOM COLUMN SET and it rides in the URL because the
 * column set is the question — "질문 하나 = URL 하나". An empty `cols` is not an
 * empty table: it means "whatever the declaration says by default", resolved in
 * `resolveColumns` against data this file does not carry.
 *
 * `mark` is the Spotfire-style global marking, also in the URL, so a marked
 * comparison pastes into a message exactly as the operator left it.
 */
export function parseSurpriseQuery(params) {
  const get = (k) => {
    const v = params && typeof params.get === 'function' ? params.get(k) : null;
    return v === null || v === undefined ? '' : String(v).trim();
  };
  return {
    view: get('view'),
    // 🔴 THE PARAMETER NAMES ARE THE SERVER'S, SPELLED IDENTICALLY. `columns`,
    // `by`, `window`, `kind` go to the route verbatim, so the address bar and the
    // request are the same sentence and there is no translation layer to drift.
    cols: get('columns').split(',').map(parseColToken).filter(Boolean),
    // Absent means the product default, not "let the server choose" — the server's
    // own default is the lot axis, which is the unit the owner rejected. It is
    // materialized into the URL by `surpriseQuery`, so the axis is addressable and
    // a pasted link restores it like every other part of the question.
    by: get('by') || DEFAULT_ROW_AXIS,
    window: get('window'),
    kind: get('kind'),
    limit: get('limit'),
    // The newest-N page. Both ride in the URL so a bounded view is addressable and
    // 「이전 보기」 is an anchor like every other control.
    offset: get('offset'),
    // 🔴 THE CAP IS A DEFAULT, NEVER A WALL. `all=1` is the reader saying "show me
    // everything anyway" — explicit, addressable, and their choice rather than the
    // screen's. It is the client's own, so it never reaches the route.
    all: get('all') === '1',
    // 🔴 THE MAP LANE'S 「낱장 / 집계」 TOGGLE. Its link was correct but this reader
    // dropped the parameter, so `?sheets=agg` was ignored on load — the toggle
    // survived a click and not a reload, which means a shared link showed a
    // different screen than the sender was looking at. Same treatment as `wafer`.
    sheets: get('sheets'),
    // Marking and slot are the client's own — the server has no opinion on which
    // rows are emphasised, and `slot` belongs to /lot_map rather than /lots.
    marked: get('mark').split(',').map((x) => x.trim()).filter(Boolean),
    slot: get('slot'),
    // 🔴 THE WAFER IN THE SEAT, NOT THE SEAT. `wafer` carries the base WF id
    // exactly as the server serves it on `projections[].frame.wafer`; empty or
    // absent means no focus. It is deliberately NOT a slot number and NOT a frame
    // key — those name a seat, and a seat is occupied by different wafers over
    // time, so focusing by seat would follow the position rather than the thing.
    //
    // Client-only, like `mark` and `slot`: it changes which wafer is emphasised,
    // not what was asked of `/lots`, so it stays out of `lotsQuery` below.
    wafer: get('wafer'),
  };
}

/** Write it back. Only non-empty parts, so the default question is a bare `?view=surprise`. */
export function surpriseQuery(question) {
  const q = question || {};
  const parts = [`view=${encodeURIComponent(SURPRISE_VIEW)}`];
  const cols = listOf(q.cols).map(colToken).filter((t) => t.indexOf(':') > 0);
  if (cols.length) parts.push(`columns=${encodeURIComponent(cols.join(','))}`);
  if (q.by) parts.push(`by=${encodeURIComponent(q.by)}`);
  if (q.window) parts.push(`window=${encodeURIComponent(q.window)}`);
  if (q.kind) parts.push(`kind=${encodeURIComponent(q.kind)}`);
  if (q.limit) parts.push(`limit=${encodeURIComponent(q.limit)}`);
  if (q.offset) parts.push(`offset=${encodeURIComponent(q.offset)}`);
  if (q.all) parts.push('all=1');
  if (q.sheets) parts.push(`sheets=${encodeURIComponent(q.sheets)}`);
  const marked = listOf(q.marked).map(strOrEmpty).filter(Boolean);
  if (marked.length) parts.push(`mark=${encodeURIComponent(marked.join(','))}`);
  if (q.slot) parts.push(`slot=${encodeURIComponent(q.slot)}`);
  // 🔴 THE FOCUSED WAFER TRAVELS WITH THE QUESTION. Without this the serializer
  // dropped it silently, so a focus could be reached by clicking but never by
  // pasting — and this screen's whole contract is that the answer IS the URL.
  if (q.wafer) parts.push(`wafer=${encodeURIComponent(q.wafer)}`);
  return parts.join('&');
}

/** The request the route actually takes — the question minus the client-only parts. */
export function lotsQuery(question) {
  const q = question || {};
  const parts = [];
  const cols = listOf(q.cols).map(colToken).filter((t) => t.indexOf(':') > 0);
  if (cols.length) parts.push(`columns=${encodeURIComponent(cols.join(','))}`);
  if (q.by) parts.push(`by=${encodeURIComponent(q.by)}`);
  if (q.window) parts.push(`window=${encodeURIComponent(q.window)}`);
  if (q.kind) parts.push(`kind=${encodeURIComponent(q.kind)}`);
  if (q.limit) parts.push(`limit=${encodeURIComponent(q.limit)}`);
  if (q.offset) parts.push(`offset=${encodeURIComponent(q.offset)}`);
  return parts.join('&');
}

/**
 * The newest-N page this question needs, or `null` when nothing needs capping.
 *
 * An explicit `limit`/`offset` in the URL wins — the reader paged deliberately —
 * and an axis with fewer rows than the cap is shown whole.
 */
export function newestPage(question, rowAxisName, total, cap) {
  const q = question || {};
  if (q.all) return null;
  if (q.limit || q.offset) return null;
  if (strOrEmpty(rowAxisName) !== DEFAULT_ROW_AXIS) return null;
  const n = cap || WAFER_CAP;
  const t = numOrNull(total);
  if (t === null || t <= n) return null;
  return { limit: String(n), offset: String(t - n) };
}

/**
 * The question's column list, MATERIALIZED.
 *
 * 🔴 THE IMPLICIT DEFAULT MUST BECOME EXPLICIT THE MOMENT THE READER EDITS IT.
 * With a bare `?view=surprise` the question names no columns while the server
 * resolves four, so editing produced a `cols` list derived from an EMPTY one:
 * removing gave back the same URL (the ✕ buttons were dead, which is what the
 * owner hit), and adding would have written a one-column URL that silently
 * dropped the other three. Both are the same bug — an edit computed against a
 * list the reader was never shown.
 *
 * So the resolved set is written into the question first, and the edit applies to
 * that. Arriving stays convenient; editing becomes explicit. Nothing downstream
 * needed changing — once the URL names the columns, it already worked.
 */
export function materializeColumns(question, resolved) {
  const named = listOf(question && question.cols);
  const src = named.length ? named : listOf(resolved);
  return src
    .map((c) => ({ kind: strOrEmpty(c && c.kind), aggregate: strOrEmpty(c && c.aggregate) }))
    .filter((c) => c.kind && c.aggregate);
}

/** The same question with one column dropped, against the materialized set. */
export function withoutColumn(question, col, resolved) {
  const key = colKey(col && col.kind, col && col.aggregate);
  return {
    ...question,
    cols: materializeColumns(question, resolved).filter((c) => colKey(c.kind, c.aggregate) !== key),
  };
}

/** The same question with one column appended (idempotent), against the materialized set. */
export function withColumn(question, col, resolved) {
  const key = colKey(col && col.kind, col && col.aggregate);
  const cols = materializeColumns(question, resolved);
  if (cols.some((c) => colKey(c.kind, c.aggregate) === key)) return { ...question, cols };
  return { ...question, cols: cols.concat([{ kind: strOrEmpty(col.kind), aggregate: strOrEmpty(col.aggregate) }]) };
}

/** The same question aimed at a different slot — an anchor, like every other control. */
export function withSlot(question, slot) {
  return { ...question, slot: strOrEmpty(slot) };
}

/**
 * The same question with one lot's marking flipped.
 *
 * 🔴 MARKING IS A SELECTION, NOT A QUESTION — it changes what is EMPHASISED, not
 * what was asked of the server, so the caller applies this with `replaceState`
 * and re-renders locally instead of navigating. It still lives in the URL,
 * because a marked comparison that cannot be pasted is a comparison the operator
 * has to rebuild by hand for whoever they are explaining it to.
 */
export function toggleMark(question, lot) {
  const id = strOrEmpty(lot);
  if (!id) return question;
  const marked = listOf(question && question.marked).map(strOrEmpty);
  return {
    ...question,
    marked: marked.includes(id) ? marked.filter((m) => m !== id) : marked.concat([id]),
  };
}

// ── the declaration: what can be a column ────────────────────

/**
 * The column space, read from the answer.
 *
 * 🔴 STILL NO METRIC LIST IN THIS FILE, and the landed contract makes that
 * cleaner rather than harder. `body.columns` is the RESOLVED set (what is up);
 * `body.aggregates_available` × the kind catalog is the space it was resolved
 * out of (what could be). Both come off the wire. A finding kind registered
 * tomorrow, or an aggregate added to `ledger_lots.AGGREGATES`, appears here
 * without a line changing.
 */
export function metricCatalog(body, kinds) {
  const columns = listOf(body && body.columns).map(readColumn).filter((c) => c.key);
  // 🔴 THE FIELD IS `name`. Measured live 2026-08-14: the server ships
  // `aggregates_available: [{name, label, value_kind, needs_denominator, over,
  // doc}, …]` — six of them — and this reader looked for `aggregate` then `id`.
  // Neither exists, so all six parsed to an empty id, got filtered out, and the
  // 「열 추가」 menu was silently empty while claiming to be complete. The READER
  // moved (lead PM ruling): the response is live and other consumers may already
  // read it, so bending the server to one reader is the larger blast radius.
  // `aggregate`/`id` stay as fallbacks so an older server keeps working.
  const aggregates = listOf(body && body.aggregates_available).map((a) => ({
    aggregate: strOrEmpty(a && (a.name !== undefined ? a.name
      : (a.aggregate !== undefined ? a.aggregate : a.id))),
    label: strOrEmpty(a && a.label),
    valueKind: strOrEmpty(a && a.value_kind),
    needsDenominator: !!(a && a.needs_denominator),
    doc: strOrEmpty(a && a.doc),
  })).filter((a) => a.aggregate);

  const items = [];
  const seen = new Set();
  for (const c of columns) {
    if (seen.has(c.kind)) continue;
    seen.add(c.kind);
    items.push({ kind: c.kind, label: c.kindLabel, atoms: null, source: 'columns' });
  }
  for (const row of listOf(kinds && kinds.kinds)) {
    const kind = strOrEmpty(row && row.kind);
    if (!kind || seen.has(kind)) continue;
    seen.add(kind);
    items.push({
      kind,
      label: strOrEmpty(row.label) || kind,
      atoms: numOrNull(row.atoms),
      source: 'catalog_only',
    });
  }

  return { state: surpriseState(body), columns, aggregates, items };
}

/** One declared column, normalised. Every field optional; a missing one is null, never 0. */
export function readColumn(raw) {
  const c = raw || {};
  const kind = strOrEmpty(c.kind);
  const aggregate = strOrEmpty(c.aggregate);
  const base = c.baseline || null;
  const den = c.denominator || null;
  return {
    // 🔴 THE SERVER'S OWN `id` WHEN IT SENT ONE. Deriving it would be a second
    // spelling of a key the cells already carry, and the day the two disagree the
    // table silently loses a column.
    key: strOrEmpty(c.id) || (kind && aggregate ? colKey(kind, aggregate) : ''),
    kind,
    aggregate,
    kindLabel: strOrEmpty(c.kind_label) || kind,
    aggLabel: strOrEmpty(c.aggregate_label) || aggregate,
    label: `${strOrEmpty(c.kind_label) || kind} ${strOrEmpty(c.aggregate_label) || aggregate}`.trim(),
    valueKind: strOrEmpty(c.value_kind),
    doc: strOrEmpty(c.doc),
    hasDenominator: c.has_denominator === true,
    denominatorLabel: strOrEmpty(den && den.label),
    denominatorPopulation: strOrEmpty(den && den.population),
    baseline: numOrNull(base && base.value),
    baselineBasis: strOrEmpty(base && base.basis),
    baselineRows: numOrNull(base && base.n_rows),
    baselineExcluded: numOrNull(base && base.excluded_rows),
    baselineExcludedReason: strOrEmpty(base && base.excluded_reason),
    thresholds: listOf(c.thresholds).map((t) => ({
      level: numOrNull(t && t.level),
      at: numOrNull(t && t.at),
      label: strOrEmpty(t && t.label),
    })).filter((t) => t.level !== null),
    state: strOrEmpty(c.state) || 'ready',
    reason: strOrEmpty(c.reason),
    declared: true,
  };
}

/** The columns that are up — the server already resolved them. */
export function resolveColumns(catalog) {
  return listOf(catalog && catalog.columns);
}

/**
 * The declared columns that are NOT up — the 「열 추가」 menu, DERIVED as the
 * cross product of the registered kinds with the declared aggregates.
 *
 * 🔴 A PAIR THE SERVER WOULD REFUSE IS STILL OFFERED, because the refusal is
 * itself the answer (`state: "unmeasurable"` with a reason) and hiding the pair
 * would leave the reader unable to find out why it is not available.
 */
export function availableColumns(catalog, columns) {
  const up = new Set(listOf(columns).map((c) => c.key));
  const out = [];
  for (const item of listOf(catalog && catalog.items)) {
    for (const agg of listOf(catalog && catalog.aggregates)) {
      const key = colKey(item.kind, agg.aggregate);
      if (up.has(key)) continue;
      out.push({
        key,
        kind: item.kind,
        aggregate: agg.aggregate,
        kindLabel: item.label,
        aggLabel: agg.label || agg.aggregate,
        label: `${item.label} ${agg.label || agg.aggregate}`.trim(),
        doc: agg.doc,
      });
    }
  }
  return out;
}

// ── the cell: where 미검사 and 0 part ways ───────────────────

/**
 * 🔴 THE ONE DOOR A NUMBER USES TO REACH THE TABLE, and the whole point of it is
 * that FOUR different cells do not collapse into one:
 *
 *   measured        the value exists. `0` lands HERE, painted at the baseline
 *                   level, reading "0" — a measured zero is a result.
 *   uninspected     the cell is null/absent. Reads 「—」. NEVER painted, never
 *                   compared to a baseline, and it is not a good result.
 *   unreported      the cell exists but carries no value. The metric was asked
 *                   for and the answer did not come back — a gap in the ANSWER,
 *                   not in the lot.
 *   no_denominator  a rate whose denominator is missing or zero. The count is
 *                   real and still shows; the RATE is undefined.
 *
 * `Number(null) === 0` is the defect this guards, and it is guarded here rather
 * than at every call site because there are as many call sites as there are
 * cells.
 */
export function cellReading(raw, column, { counts } = {}) {
  const col = column || {};

  // 🔴 AN ABSENT CELL IS NOT AN UNSCANNED CELL — the fifth state, and the only
  // one this file produces. `unscanned` is a MEASUREMENT (`of == 0`: the chip was
  // outside the inspected population). A cell the response never carried is a gap
  // in the ANSWER, and calling it 미검사 would put a claim about the fab behind a
  // missing field.
  if (raw === null || raw === undefined) {
    return {
      state: 'unreported', value: null, n: null, of: null,
      baseline: null, ratio: null, level: null, painted: false,
      text: '미보고', why: '집계가 이 칸을 싣지 않았습니다',
    };
  }

  const n = numOrNull(raw.n);
  const of = numOrNull(raw.of);
  const value = numOrNull(raw.value);
  const wire = strOrEmpty(raw.state);

  // ── the three non-measured wire states, consumed verbatim ──
  if (wire === 'unscanned') {
    return {
      state: 'unscanned', value: null, n, of,
      baseline: null, ratio: null, level: null, painted: false,
      text: '—', why: '미검사 · 0 아님',
    };
  }
  if (wire === 'unmeasurable') {
    return {
      state: 'unmeasurable', value: null, n, of,
      baseline: null, ratio: null, level: null, painted: false,
      text: '측정 불가', why: strOrEmpty(col.reason) || '이 상자에서 계산할 수 없는 열입니다',
    };
  }
  if (wire === 'no_denominator') {
    return {
      state: 'no_denominator', value: null, n, of,
      baseline: null, ratio: null, level: null, painted: false,
      text: n !== null ? `${n}건` : '—',
      why: '분모 없음 — 율을 정의할 수 없습니다',
    };
  }

  // ── measured ──
  //
  // 🔴 A CELL THE SERVER CALLED `measured` WITH NO VALUE IS A CONTRADICTION, and
  // it is reported as one rather than smoothed into a zero.
  if (value === null) {
    return {
      state: 'unreported', value: null, n, of,
      baseline: null, ratio: null, level: null, painted: false,
      text: '미보고', why: wire === 'measured' ? '측정됨이라 했으나 값이 없습니다' : '집계 미보고',
    };
  }
  // 🔴 분모 없는 숫자 출고 금지. Measured on the live box: only 20.6% of a lot's
  // chips are inspected, so a rate whose denominator never arrived would be wrong
  // by ~5× if anybody substituted the lot size.
  if (col.hasDenominator && of === null) {
    return {
      state: 'no_denominator', value, n, of: null,
      baseline: null, ratio: null, level: null, painted: false,
      text: n !== null ? `${n}건` : '—',
      why: `분모 없음 — ${col.denominatorLabel || '분모'} 미보고`,
    };
  }

  // 🔴 THE STEP AND THE RATIO ARE THE SERVER'S NUMBERS. No threshold ladder runs
  // in this file — the baseline is a median over rows this client never sees, so
  // recomputing the level would be a second scale that drifts from the first.
  const served = numOrNull(raw.level);
  // 🔴 SUPPRESSION IS DECLARED, NOT MATCHED. The server marks each row with
  // `bucket.counts_toward_baseline`; a row outside the baseline is shown, badged,
  // and NOT painted — because a colour means "against this baseline" and that row
  // is not in it. Matching a literal bucket name here would re-hardcode the very
  // discriminator the owner has not yet named.
  const suppressed = counts === false;
  const level = suppressed ? null : served;

  return {
    state: 'measured', value, n, of,
    baseline: numOrNull(col.baseline),
    ratio: numOrNull(raw.ratio_to_baseline),
    level, painted: level !== null && level > 0,
    levelServed: served !== null,
    suppressed,
    text: null, why: null,
  };
}

/** The multiple, as text. Never a bare number without its ×. */
export function liftText(ratio) {
  const l = numOrNull(ratio);
  if (l === null) return '';
  if (l >= 100) return `${Math.round(l)}×`;
  if (l >= 10) return `${l.toFixed(1)}×`;
  return `${l.toFixed(2)}×`;
}

/**
 * One measured value, formatted for its declared unit.
 *
 * An unknown unit keeps its raw spelling beside the number rather than being
 * dropped — the same "an enum member I have never heard of still renders" rule
 * the rest of these screens hold.
 */
export function valueText(value, valueKind) {
  const v = numOrNull(value);
  if (v === null) return '—';
  const u = strOrEmpty(valueKind);
  if (u === UNIT_RATIO) {
    const pct = v * 100;
    if (pct === 0) return '0%';
    if (Math.abs(pct) < 0.01) return '<0.01%';
    if (Math.abs(pct) < 10) return `${pct.toFixed(2)}%`;
    if (Math.abs(pct) < 100) return `${pct.toFixed(1)}%`;
    return `${Math.round(pct)}%`;
  }
  const abs = Math.abs(v);
  let body;
  if (Number.isInteger(v) && abs < 1e6) body = String(v);
  else if (abs >= 1000) body = String(Math.round(v));
  else if (abs >= 1) body = v.toFixed(2);
  else if (abs === 0) body = '0';
  else body = v.toPrecision(3);
  // `count` and `mean` are shapes, not units — the server sends no unit word,
  // so appending one would be this file inventing a dimension.
  return body;
}

/** The fraction under a cell — the denominator, always on screen when it exists. */
export function fractionText(reading) {
  if (!reading) return '';
  const n = reading.n;
  const of = reading.of;
  if (n === null || n === undefined) return '';
  if (of === null || of === undefined) return `${n}`;
  return `${n}/${of}`;
}

// ── the rows: lots in production order ───────────────────────

/**
 * 🔴 THE ORDER IS THE SERVER'S, AND THAT IS DELIBERATE. "행 = 랏 생산 순서" is
 * the axis that makes the table temporal, and production order is a fact about
 * the fab that this client cannot reconstruct from a lot id. When `seq` is
 * missing the response order is kept — the reading degrades to "the order the
 * server chose" and says so, rather than to an alphabetical sort that would look
 * like a production order and not be one.
 */
export function lotRows(body, columns) {
  const cols = listOf(columns);
  return listOf(body && body.rows).map((row, i) => {
    const r = row || {};
    const bucket = r.bucket || {};
    // 🔴 `counts_toward_baseline` IS THE PAINT RULE, and it is the SERVER'S
    // declaration. Today every row is `unknown` + counts:true, deliberately —
    // the owner has not yet named the real special-evaluation discriminator, and
    // excluding rows on a guess would quietly reshape every colour on the screen.
    const counts = bucket.counts_toward_baseline !== false;
    // The cells arrive as a LIST keyed by the column id, so they are indexed once
    // per row rather than searched once per column per row.
    const byColumn = new Map();
    for (const c of listOf(r.cells)) {
      const key = strOrEmpty(c && c.column);
      if (key) byColumn.set(key, c);
    }
    return {
      // 🔴 `row` IS THE KEY `/lot_map` TAKES; `label` is what a human reads. They
      // are the same string today and passing one where the other belongs is how
      // a map comes back for the wrong wafer the day they diverge.
      row: strOrEmpty(r.row),
      lot: strOrEmpty(r.label) || strOrEmpty(r.row),
      index: i,
      seq: numOrNull(r.order_index),
      startedAt: strOrEmpty(r.occurred_at && r.occurred_at.first),
      lastAt: strOrEmpty(r.occurred_at && r.occurred_at.last),
      bucket: strOrEmpty(bucket.id) || 'unknown',
      bucketLabel: bucketLabel(bucket.id, bucket.label),
      counts,
      special: !counts,
      universe: numOrNull(r.universe),
      cells: cols.map((col) => ({
        column: col,
        reading: cellReading(byColumn.has(col.key) ? byColumn.get(col.key) : null,
          col, { counts }),
      })),
    };
  });
}

/** Whether the response gave a real production order, stated rather than assumed. */
export function orderReading(rows, body) {
  const list = listOf(rows);
  const axis = (body && body.row_axis) || null;
  const term = strOrEmpty(axis && axis.label) || '행';
  if (!list.length) return { ok: false, why: '행 없음', term };
  const withSeq = list.filter((r) => r.seq !== null);
  if (withSeq.length === list.length) {
    return { ok: true, why: `${term} 발생 순서 (서버 order_index)`, term };
  }
  if (withSeq.length === 0) return { ok: false, why: '순서 미보고 — 응답 순서 그대로', term };
  return { ok: false, why: `순서 일부 미보고 (${withSeq.length}/${list.length})`, term };
}

// ── the small multiples ──────────────────────────────────────

/**
 * One column's trend, as points on the shared production-order axis.
 *
 * 🔴 SPECIAL-EVALUATION LOTS ARE NOT PLOTTED IN THE LINE but they are NOT
 * dropped either — they come back separately so the view can mark them on the
 * axis. A special lot inside the line would drag the trend with a number that was
 * produced under different conditions; a special lot deleted from the chart is a
 * row the operator saw in the table and cannot find in the graph.
 *
 * 🔴 AND 미검사 BREAKS THE LINE. A gap is a gap: joining across it would draw a
 * segment through data nobody has.
 */
export function chartSeries(rows, column) {
  const key = column && column.key;
  const points = [];
  const gaps = [];
  const special = [];
  let min = null;
  let max = null;

  listOf(rows).forEach((row, i) => {
    const cell = listOf(row.cells).find((c) => c.column && c.column.key === key);
    const reading = cell && cell.reading;
    if (!reading || reading.state !== 'measured') {
      gaps.push({ i, lot: row.lot, why: (reading && reading.why) || '미검사' });
      return;
    }
    const pt = { i, lot: row.lot, value: reading.value, level: reading.level, special: row.special };
    if (row.special) { special.push(pt); return; }
    points.push(pt);
    if (min === null || reading.value < min) min = reading.value;
    if (max === null || reading.value > max) max = reading.value;
  });

  const baseline = points.length
    ? numOrNull(column && column.baseline)
    : numOrNull(column && column.baseline);

  return {
    column, points, gaps, special,
    min, max, baseline,
    plotted: points.length,
    total: listOf(rows).length,
  };
}

/** Ledger events placed on the shared axis by lot index. */
export function eventMarkers(body, rows) {
  const bySeq = new Map();
  const byLot = new Map();
  listOf(rows).forEach((r, i) => {
    if (r.seq !== null) bySeq.set(r.seq, i);
    if (r.lot) byLot.set(r.lot, i);
  });
  return listOf(body && body.events).map((e) => {
    const seq = numOrNull(e && e.seq);
    const lot = strOrEmpty(e && e.lot);
    let i = null;
    if (seq !== null && bySeq.has(seq)) i = bySeq.get(seq);
    else if (lot && byLot.has(lot)) i = byLot.get(lot);
    return {
      i,
      label: strOrEmpty(e && e.label),
      kind: strOrEmpty(e && e.kind),
      at: strOrEmpty(e && e.at),
      placed: i !== null,
    };
  }).filter((m) => m.label);
}

// ── the model ────────────────────────────────────────────────

/**
 * Everything the view needs, and nothing it has to compute.
 *
 * A null `body` is a first-class case, not an error path: the frame paints from
 * the kind catalog alone while the aggregate is in flight, and it paints the same
 * way forever if the route never ships — every panel saying what it does not
 * know. That is what makes this screen shippable ahead of the server lane.
 */
export function surpriseModel({ body, kinds, question } = {}) {
  const asked = question || { cols: [], marked: [] };
  const catalog = metricCatalog(body, kinds);
  const columns = resolveColumns(catalog);
  const rows = lotRows(body, columns);
  const markedSet = new Set(listOf(asked.marked).map(strOrEmpty));
  for (const row of rows) row.marked = markedSet.has(row.row) || markedSet.has(row.lot);

  const marked = rows.filter((r) => r.marked);
  // 🔴 A MARK FOR A ROW NOT IN THE TABLE IS REPORTED, NOT SWALLOWED. A pasted URL
  // whose window no longer contains the row would otherwise show an empty map
  // section with no explanation.
  const present = new Set();
  for (const r of rows) { present.add(r.row); present.add(r.lot); }
  const strayMarks = Array.from(markedSet).filter((m) => !present.has(m));

  // The threshold ladder, for the LEGEND'S WORDS. It is read off a column rather
  // than declared here, so the legend cannot describe a scale the paint does not
  // use. Columns all carry the same ladder today; the first one that has it wins.
  const ladder = (columns.find((c) => c.thresholds.length) || { thresholds: [] }).thresholds;

  // 🔴 FAKE ATTENUATION — R-2026-08-14-G. A column that is never painted READS AS
  // 「정상」, and silence is the one thing this screen must not say by accident.
  //
  // 🔴 AND THIS IS NOT THE SERVER'S DECLARATION. The ruling asks for 「이 지표는
  // 현행 규칙으로 채점 불가」, which is a claim about the metric's MATHEMATICS —
  // that `found/scanned` saturates at 1.0, so with a baseline of 0.6124 its
  // ceiling is 1.633 and the first threshold at 2.0 is unreachable BY ANY DATA.
  // Only the server can say that; deriving it here would be the client inventing
  // the answer, which is the shape already repaired twice today.
  //
  // What IS computable from the payload, and is stated as such, is a fact about
  // THIS RESPONSE: how many cells were painted, and how far the largest multiple
  // got toward the first step. It cannot be mistaken for the declaration because
  // it never says 「불가」 — it says what happened here. When the server ships the
  // real declaration it arrives on `columns[].state`/`reason` and renders through
  // the generic path above, ahead of this.
  for (const col of columns) {
    let painted = 0;
    let measured = 0;
    let maxRatio = null;
    for (const row of rows) {
      const hit = row.cells.find((c) => c.column.key === col.key);
      const r = hit && hit.reading;
      if (!r || r.state !== 'measured') continue;
      measured += 1;
      if (r.painted) painted += 1;
      if (r.ratio !== null && (maxRatio === null || r.ratio > maxRatio)) maxRatio = r.ratio;
    }
    const steps = col.thresholds.map((t) => t.at).filter((t) => t !== null);
    col.observed = {
      painted,
      measured,
      maxRatio,
      firstThreshold: steps.length ? Math.min.apply(null, steps) : null,
      // `true` only when there was something to paint and none of it was painted.
      // Zero measured cells is a different nothing and is left to the cells.
      neverPainted: measured > 0 && painted === 0,
    };
  }

  const populations = (body && body.populations) || {};
  const win = (body && body.window) || {};
  const prov = (body && body.provenance) || {};

  return {
    state: surpriseState(body),
    generatedAt: strOrEmpty(body && body.generated_at),
    question: asked,
    catalog,
    columns,
    available: availableColumns(catalog, columns),
    rowAxis: {
      name: strOrEmpty(body && body.row_axis && body.row_axis.name),
      label: strOrEmpty(body && body.row_axis && body.row_axis.label),
      source: strOrEmpty(body && body.row_axis && body.row_axis.source),
    },
    axesAvailable: listOf(body && body.axes_available).map((a) => ({
      name: strOrEmpty(a && a.name),
      label: strOrEmpty(a && a.label),
      about: strOrEmpty(a && a.about),
    })).filter((a) => a.name),
    ladder,
    rows,
    order: orderReading(rows, body),
    marked,
    strayMarks,
    series: columns.map((c) => chartSeries(rows, c)),
    events: eventMarkers(body, rows),
    // 🔴 THE HONESTY BLOCK. A forced window, a truncated row set and a
    // not-ledger-backed provenance are all things that change what the numbers
    // mean, and a screen that shows the numbers without them is overstating them.
    truncated: populations.rows_truncated === true,
    rowsTotal: numOrNull(populations.rows_total),
    rowsReturned: numOrNull(populations.rows_returned),
    window: {
      requested: win.requested || null,
      applied: win.applied || null,
      forced: win.forced === true,
      forcedReason: strOrEmpty(win.forced_reason),
    },
    provenance: {
      source: strOrEmpty(prov.source),
      ledgerBacked: prov.ledger_backed === true,
      note: strOrEmpty(prov.note),
      relations: listOf(prov.relations).map(strOrEmpty).filter(Boolean),
      absent: listOf(prov.absent_relations).map(strOrEmpty).filter(Boolean),
    },
    notes: listOf(body && body.notes).map((nte) => ({
      code: strOrEmpty(nte && nte.code),
      message: strOrEmpty(nte && nte.message),
    })).filter((nte) => nte.message),
    counts: {
      rows: rows.length,
      offBaseline: rows.filter((r) => !r.counts).length,
      // 🔴 THE MARKED COUNT IS THE READER'S SET, NOT THE VISIBLE SUBSET. With a
      // newest-N cap a marked wafer can sit off the loaded page; counting only the
      // rows on screen would report the reader's own selection as smaller than it
      // is, and paging is the machine's convenience, not a change of mind.
      marked: markedSet.size,
      markedOnPage: marked.length,
      markedOffPage: strayMarks.length,
    },
  };
}
