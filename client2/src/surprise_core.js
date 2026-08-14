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
// 🔴 PROPOSED SHAPE — NOT YET SERVED (the server lane is building the
// aggregate; the lead PM hands the contract over when it lands). Every field is
// optional to this reader: a missing one renders as 미보고 or 미검사, NEVER as 0
// and never as a blank. That is what lets this screen ship before the route.
//
//   GET /api/ledger/lots[?cols=&from=&to=&limit=]
//     -> {
//          state: "absent" | "empty" | "ready",
//          generated_at: "<iso>",
//
//          // ── 선언: 무엇이 열이 될 수 있는가 (항목 × 집계) ──
//          metrics: [
//            { metric: "void", label: "보이드",
//              basis: "inspection_run",          // 분모의 정의
//              observed_by: ["AOI"],
//              aggregates: [
//                { agg: "chip_rate", label: "발생칩비", unit: "ratio",
//                  numerator: "발생 칩", denominator: "검사 칩",
//                  baseline: <num|null> }         // 열의 기저 (없으면 행이 실어옴)
//              ] }
//          ],
//          default_columns: [ {metric, agg}, … ],  // 서버가 선언한 기본 질문
//          scale: [2, 3, 4.5, 6],                  // 조건부서식 배수 단계 (선택)
//
//          // ── 행: 생산 순서. 정렬은 서버가 한다 (클라 정렬 아님) ──
//          lots: [
//            { row: "<row id — the key /lot_map takes>",
//              lot: "CL-2601-006", seq: <int>, started_at: "<iso>",
//              bucket: "production"|"special_eval"|"unknown",
//              bucket_label: "양산",
//              inspected: { chips: <int|null>, runs: <int|null> } | null,
//              cells: {
//                // 🔴 `state` AND `level` ARE THE SERVER'S. Never derived here.
//                "void|chip_rate": { state: "measured", value: 0.416,
//                                    n: 312, d: 725,     // d = INSPECTED chips,
//                                    baseline: 0.065,    //     not lot size
//                                    lift: 6.4, level: 4 },
//                "delam|chip_rate": { state: "unscanned" },
//                "peel|area":       { state: "unmeasurable", reason: "…" }
//              } }
//          ],
//
//          // ── 원장 사건: 차트의 세로 마커 ──
//          events: [ { seq: <int>, at: "<iso>", label: "EQP-07 투입",
//                      kind: "equipment", ref: "<atom id|null>" } ]
//        }
//
// CHANGING WHAT THIS CONSUMES IS AN ESCALATION, NOT AN EDIT — and so is the
// server lane answering a different shape.
// ============================================================

export const SURPRISE_VIEW = 'surprise';

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

//: 🔴 THE CONDITIONAL-FORMATTING BANDS — FOR THE LEGEND'S WORDS ONLY.
//: Owner: "조건부서식 현행 유지 — 열마다 자기 기저 대비 배수 단계". The step a cell
//: is painted at (`level`) is COMPUTED BY THE SERVER and consumed verbatim; these
//: numbers exist so the legend can say what the steps mean, and the server's own
//: `scale` replaces them when it sends one. Nothing in this file assigns a level.
export const DEFAULT_SCALE = [2, 3, 4.5, 6];

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
export function colKey(metric, agg) {
  return `${strOrEmpty(metric)}|${strOrEmpty(agg)}`;
}

/** The URL spelling of one column — `metric:agg`. */
export function colToken(col) {
  return `${strOrEmpty(col && col.metric)}:${strOrEmpty(col && col.agg)}`;
}

function parseColToken(token) {
  const raw = strOrEmpty(token).trim();
  if (!raw) return null;
  const at = raw.indexOf(':');
  if (at < 0) return null;
  const metric = raw.slice(0, at).trim();
  const agg = raw.slice(at + 1).trim();
  if (!metric || !agg) return null;
  return { metric, agg };
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
  const cols = get('cols').split(',').map(parseColToken).filter(Boolean);
  const marked = get('mark').split(',').map((s) => s.trim()).filter(Boolean);
  return {
    view: get('view'),
    cols,
    marked,
    // Which finding kind the three-axis maps are OF. Shared spelling with the
    // console's `finding` on purpose — the same word means the same thing on
    // both of this page's questions, and a lot carried from one to the other
    // keeps its kind.
    finding: get('finding'),
    // 🔴 WHICH SLOT THE MAPS ARE OF, AND IT IS NOT OPTIONAL DETAIL. Measured by
    // the server lane: the bonding map is keyed on `(bond_lot, bond_slot)`, so
    // ONE LOT IS 25 FRAMES and their grids differ (11×11, 12×12, 12×13, 13×13…).
    // There is no such thing as "the lot's map"; overlaying 25 slots into one
    // picture would invent a wafer that does not exist. Empty means "whichever
    // slot the server declares as default", resolved against the answer.
    slot: get('slot'),
    from: get('from'),
    to: get('to'),
  };
}

/** Write it back. Only non-empty parts, so the default question is a bare `?view=surprise`. */
export function surpriseQuery(question) {
  const q = question || {};
  const parts = [`view=${encodeURIComponent(SURPRISE_VIEW)}`];
  const cols = listOf(q.cols).map(colToken).filter((t) => t !== ':' && t.indexOf(':') > 0);
  if (cols.length) parts.push(`cols=${encodeURIComponent(cols.join(','))}`);
  const marked = listOf(q.marked).map(strOrEmpty).filter(Boolean);
  if (marked.length) parts.push(`mark=${encodeURIComponent(marked.join(','))}`);
  if (q.finding) parts.push(`finding=${encodeURIComponent(q.finding)}`);
  if (q.slot) parts.push(`slot=${encodeURIComponent(q.slot)}`);
  if (q.from) parts.push(`from=${encodeURIComponent(q.from)}`);
  if (q.to) parts.push(`to=${encodeURIComponent(q.to)}`);
  return parts.join('&');
}

/** The same question with one column dropped. */
export function withoutColumn(question, col) {
  const key = colKey(col && col.metric, col && col.agg);
  return {
    ...question,
    cols: listOf(question && question.cols).filter((c) => colKey(c.metric, c.agg) !== key),
  };
}

/** The same question with one column appended (idempotent). */
export function withColumn(question, col) {
  const key = colKey(col && col.metric, col && col.agg);
  const cols = listOf(question && question.cols);
  if (cols.some((c) => colKey(c.metric, c.agg) === key)) return { ...question, cols };
  return { ...question, cols: cols.concat([{ metric: col.metric, agg: col.agg }]) };
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
 * The declared metric × aggregate space.
 *
 * 🔴 THIS IS THE WHOLE ANSWER TO "지표를 하드코딩하지 말 것". Two sources, in
 * order of authority:
 *
 *   the metrics declaration   `body.metrics[].aggregates[]` — the real one. Each
 *                             aggregate declares its own label, unit, numerator,
 *                             denominator and baseline.
 *   the kind catalog          `GET /api/ledger/kinds`, which this page already
 *                             fetches and which IS deployed. It carries the ITEM
 *                             axis only, so before the metrics route ships the
 *                             screen can still say WHICH items exist and that
 *                             their aggregates are not declared yet.
 *
 * An item present in the catalog and absent from the metrics declaration is
 * reported as `declared_item_only` rather than dropped — a hidden axis is one the
 * owner cannot know exists (the structure view's rule, and the same reason).
 */
export function metricCatalog(body, kinds) {
  const columns = [];
  const seen = new Set();
  const items = [];
  const itemSeen = new Set();

  const pushItem = (item) => {
    if (itemSeen.has(item.metric)) return;
    itemSeen.add(item.metric);
    items.push(item);
  };

  for (const m of listOf(body && body.metrics)) {
    const metric = strOrEmpty(m && m.metric);
    if (!metric) continue;
    const aggregates = listOf(m.aggregates);
    pushItem({
      metric,
      label: strOrEmpty(m.label) || metric,
      basis: strOrEmpty(m.basis),
      observedBy: listOf(m.observed_by).map(strOrEmpty).filter(Boolean),
      atoms: numOrNull(m.atoms),
      aggregateCount: aggregates.length,
      source: 'metrics',
    });
    for (const a of aggregates) {
      const agg = strOrEmpty(a && a.agg);
      if (!agg) continue;
      const key = colKey(metric, agg);
      if (seen.has(key)) continue;
      seen.add(key);
      columns.push({
        key,
        metric,
        agg,
        metricLabel: strOrEmpty(m.label) || metric,
        aggLabel: strOrEmpty(a.label) || agg,
        label: `${strOrEmpty(m.label) || metric} ${strOrEmpty(a.label) || agg}`,
        unit: strOrEmpty(a.unit),
        numerator: strOrEmpty(a.numerator),
        denominator: strOrEmpty(a.denominator),
        basis: strOrEmpty(a.basis) || strOrEmpty(m.basis),
        baseline: numOrNull(a.baseline),
      });
    }
  }

  // The item axis from the catalog that IS deployed, for everything the metrics
  // declaration did not cover.
  for (const row of listOf(kinds && kinds.kinds)) {
    const metric = strOrEmpty(row && row.kind);
    if (!metric || itemSeen.has(metric)) continue;
    pushItem({
      metric,
      label: strOrEmpty(row.label) || metric,
      basis: listOf(row.observed_by).length ? 'inspection_run' : '',
      observedBy: listOf(row.observed_by).map(strOrEmpty).filter(Boolean),
      atoms: numOrNull(row.atoms),
      aggregateCount: 0,
      source: 'declared_item_only',
    });
  }

  return {
    state: surpriseState(body),
    columns,
    items,
    // The server's own default question. Absent -> the whole declared space, in
    // declaration order. Never a list written here.
    defaults: listOf(body && body.default_columns)
      .map((c) => ({ metric: strOrEmpty(c && c.metric), agg: strOrEmpty(c && c.agg) }))
      .filter((c) => c.metric && c.agg && seen.has(colKey(c.metric, c.agg))),
  };
}

/**
 * Which columns are up, resolved against the declaration.
 *
 * A column asked for by the URL and NOT declared does not silently vanish: it
 * comes back with `declared: false` so the screen can say the question named
 * something the server does not know, which is a fact about the question rather
 * than a rendering accident.
 */
export function resolveColumns(catalog, question) {
  const declared = new Map(listOf(catalog && catalog.columns).map((c) => [c.key, c]));
  const asked = listOf(question && question.cols);

  if (asked.length) {
    return asked.map((c) => {
      const key = colKey(c.metric, c.agg);
      const hit = declared.get(key);
      if (hit) return { ...hit, declared: true };
      return {
        key,
        metric: strOrEmpty(c.metric),
        agg: strOrEmpty(c.agg),
        metricLabel: strOrEmpty(c.metric),
        aggLabel: strOrEmpty(c.agg),
        label: `${strOrEmpty(c.metric)} · ${strOrEmpty(c.agg)}`,
        unit: '',
        numerator: '',
        denominator: '',
        basis: '',
        baseline: null,
        declared: false,
      };
    });
  }

  const defaults = listOf(catalog && catalog.defaults);
  if (defaults.length) {
    return defaults
      .map((c) => declared.get(colKey(c.metric, c.agg)))
      .filter(Boolean)
      .map((c) => ({ ...c, declared: true }));
  }
  return listOf(catalog && catalog.columns).map((c) => ({ ...c, declared: true }));
}

/** The declared columns that are NOT currently up — the "열 추가" menu, derived. */
export function availableColumns(catalog, columns) {
  const up = new Set(listOf(columns).map((c) => c.key));
  return listOf(catalog && catalog.columns).filter((c) => !up.has(c.key));
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
export function cellReading(raw, column, { bucket } = {}) {
  const col = column || {};

  // 🔴 AN ABSENT CELL IS NOT AN UNSCANNED CELL. `unscanned` is a MEASUREMENT —
  // the server looked and the chip was outside the inspected population. A cell
  // the response simply did not carry is a gap in the ANSWER, and calling it
  // 미검사 would put a claim about the fab behind a hole in a payload.
  if (raw === null || raw === undefined) {
    return {
      state: 'unreported', value: null, n: null, d: null,
      baseline: null, lift: null, level: null, painted: false,
      text: '미보고', why: '집계가 이 칸을 싣지 않았습니다',
    };
  }

  const n = numOrNull(raw.n);
  const d = numOrNull(raw.d);
  const value = numOrNull(raw.value);
  const wire = strOrEmpty(raw.state);

  // ── the three non-measured wire states, consumed verbatim ──
  if (wire === 'unscanned') {
    return {
      state: 'unscanned', value: null, n, d,
      baseline: null, lift: null, level: null, painted: false,
      text: '—', why: '미검사 · 0 아님',
    };
  }
  if (wire === 'unmeasurable') {
    return {
      state: 'unmeasurable', value: null, n, d,
      baseline: null, lift: null, level: null, painted: false,
      text: '측정 불가', why: strOrEmpty(raw.reason) || '이 항목은 이 랏에서 정의되지 않습니다',
    };
  }
  if (wire === 'no_denominator') {
    return {
      state: 'no_denominator', value: null, n, d,
      baseline: null, lift: null, level: null, painted: false,
      text: n !== null ? `${n}건` : '—',
      why: strOrEmpty(raw.reason) || '분모 없음 — 율을 정의할 수 없습니다',
    };
  }

  // ── measured ──
  //
  // 🔴 A CELL THE SERVER CALLED `measured` WITH NO VALUE IS A CONTRADICTION, and
  // it is reported as one rather than smoothed into a zero.
  if (value === null) {
    return {
      state: 'unreported', value: null, n, d,
      baseline: null, lift: null, level: null, painted: false,
      text: '미보고', why: wire === 'measured' ? '측정됨이라 했으나 값이 없습니다' : '집계 미보고',
    };
  }
  // 🔴 분모 없는 숫자 출고 금지. A rate whose denominator never arrived is a
  // number with no claim attached — and on this fixture the denominator is the
  // INSPECTED chip count (725 of 3,525), so guessing one would be wrong by 5×.
  if (col.unit === UNIT_RATIO && d === null) {
    return {
      state: 'no_denominator', value, n, d: null,
      baseline: null, lift: null, level: null, painted: false,
      text: n !== null ? `${n}건` : '—', why: '분모 없음 — 검사 칩 수 미보고',
    };
  }

  const baseline = numOrNull(raw.baseline) !== null ? numOrNull(raw.baseline) : numOrNull(col.baseline);
  const lift = numOrNull(raw.lift);

  // 🔴 THE STEP IS THE SERVER'S NUMBER. No threshold function runs here — see
  // the file header. An absent `level` leaves the cell UNPAINTED rather than
  // falling back to a client scale that would disagree with every other cell.
  const served = numOrNull(raw.level);
  // 🔴 특수평가 행은 칠하지 않는다 (owner constraint 2). The value is printed and
  // the badge distinguishes it; suppressing the PAINT rather than the ROW is the
  // whole point — a filter would delete the rows that refute the reading.
  const suppressed = strOrEmpty(bucket) === 'special_eval';
  const level = suppressed ? null : served;

  return {
    state: 'measured', value, n, d, baseline, lift,
    level, painted: level !== null && level > 0,
    levelServed: served !== null,
    suppressed,
    text: null, why: null,
  };
}

/** The multiple, as text. Never a bare number without its ×. */
export function liftText(lift) {
  const l = numOrNull(lift);
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
export function valueText(value, unit) {
  const v = numOrNull(value);
  if (v === null) return '—';
  const u = strOrEmpty(unit);
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
  if (!u || u === 'count') return body;
  return `${body} ${u}`;
}

/** The fraction under a cell — the denominator, always on screen when it exists. */
export function fractionText(reading) {
  if (!reading) return '';
  const n = reading.n;
  const d = reading.d;
  if (n === null || n === undefined) return '';
  if (d === null || d === undefined) return `${n}`;
  return `${n}/${d}`;
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
  return listOf(body && body.lots).map((row, i) => {
    const lot = strOrEmpty(row && row.lot);
    const bucket = strOrEmpty(row && row.bucket) || 'unknown';
    const cells = (row && row.cells) || {};
    return {
      lot,
      // 🔴 THE KEY `/api/ledger/lot_map` TAKES. It is `row`, not the lot name:
      // the map is keyed on a bonding row, and passing a display label where an
      // id belongs is how a map comes back for the wrong wafer.
      row: strOrEmpty(row && row.row) || lot,
      index: i,
      seq: numOrNull(row && row.seq),
      startedAt: strOrEmpty(row && row.started_at),
      bucket,
      bucketLabel: bucketLabel(bucket, row && row.bucket_label),
      special: bucket === 'special_eval',
      chips: numOrNull(row && row.inspected && row.inspected.chips),
      runs: numOrNull(row && row.inspected && row.inspected.runs),
      cells: cols.map((col) => ({
        column: col,
        reading: cellReading(
          Object.prototype.hasOwnProperty.call(cells, col.key) ? cells[col.key] : null,
          col, { bucket },
        ),
      })),
    };
  });
}

/** Whether the response gave a real production order, stated rather than assumed. */
export function orderReading(rows) {
  const list = listOf(rows);
  if (!list.length) return { ok: false, why: '행 없음' };
  const withSeq = list.filter((r) => r.seq !== null);
  if (withSeq.length === list.length) return { ok: true, why: '생산 순서 (서버 seq)' };
  if (withSeq.length === 0) return { ok: false, why: '생산 순서 미보고 — 응답 순서 그대로' };
  return { ok: false, why: `생산 순서 일부 미보고 (${withSeq.length}/${list.length})` };
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
  const columns = resolveColumns(catalog, asked);
  const scale = listOf(body && body.scale).map(numOrNull).filter((s) => s !== null);
  const rows = lotRows(body, columns);
  const markedSet = new Set(listOf(asked.marked).map(strOrEmpty));
  for (const row of rows) row.marked = markedSet.has(row.lot);

  const marked = rows.filter((r) => r.marked);
  // 🔴 A MARK FOR A LOT NOT IN THE TABLE IS REPORTED, NOT SWALLOWED. A pasted URL
  // whose window no longer contains the lot would otherwise show an empty map
  // section with no explanation.
  const inTable = new Set(rows.map((r) => r.lot));
  const strayMarks = Array.from(markedSet).filter((m) => !inTable.has(m));

  return {
    state: surpriseState(body),
    generatedAt: strOrEmpty(body && body.generated_at),
    question: asked,
    catalog,
    columns,
    available: availableColumns(catalog, columns),
    scale: scale.length ? scale : DEFAULT_SCALE,
    scaleFromServer: scale.length > 0,
    rows,
    order: orderReading(rows),
    marked,
    strayMarks,
    series: columns.map((c) => chartSeries(rows, c)),
    events: eventMarkers(body, rows),
    counts: {
      lots: rows.length,
      special: rows.filter((r) => r.special).length,
      marked: marked.length,
    },
  };
}
