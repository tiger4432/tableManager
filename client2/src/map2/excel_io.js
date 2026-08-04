// ═══════════════════════════════════════════════════════════════════════════════
// map2/excel_io.js -- THE GATEKEEPER. Maps enter and leave the system through the
// operator's Excel form, and this module is the only place that speaks it.
//
// 🔴 THE FORM IS NOT OURS TO DESIGN. It is an artifact operators already use, so the job
//    is to MATCH it in both directions. The authoritative encoding of what it IS lives in
//    production ingestion code that already reads it:
//
//      dev_env/ingestion_workspace/bonding_map/scripts/bonding_map_parser.py
//        -> server/parsers/html_topology_parser.py :: HTMLMatrixTableParser
//
//    and, for the plain-text projection that travels through the clipboard, in the
//    expectations frozen by `client2/tests/coord_table_paste_harness.mjs`.
//
//    This module is written FROM THAT FORMAT, not transcribed from the legacy editor. A
//    transcription carries the legacy defects across with the behaviour and leaves no way
//    to tell which is which afterwards.
//
// ⚠️ NOT A LAYER -- A DOORWAY. It does not judge. It reads what arrived, says what it
//    could not place and why, and writes back out. Scoring, seating, verdicts and saving
//    all live elsewhere and none of them are called from here.
//
// ── IN IS NOT THE MIRROR OF OUT ────────────────────────────────────────────────
// Reading can partially fail; writing cannot. `readMapForm` therefore returns an INTAKE
// report -- what arrived, and what was rejected with a reason, as AGGREGATE COUNTS. It is
// not per-row noise, and there is no symmetric `writeIntake`, because the asymmetry is
// real and a symmetric API would imply a symmetry that does not hold.
//
// The degradation vocabulary is borrowed, not invented: `not_declared` and
// `mapping_unavailable` are the codes, `미상` is what the operator reads when the form
// does not state its own identity.
//
// ── MODULE DISCIPLINE ───────────────────────────────────────────────────────────
// Pure ES module. Arguments in, values out, NO MODULE-LEVEL STATE, no DOM, no fetch, and
// no import of `config.js` (it reads `window.location.port`, so it is not node-importable
// and would make this module untestable by `import`). Config values are passed in.
//
// The two things it does import are the codebase's existing single implementations, which
// is reuse rather than a second spelling of the same operation:
//   - `tsv.js`      the ONE text<->grid reader/writer, and the only one that knows Excel's
//                   quoting rules. Writing a second one here is how a DESC containing a
//                   tab silently truncates.
//   - `declaration.js`  the ONE place a frame axis becomes a fact with a provenance token.
//                   The form declares NO frame axis, and saying so in that vocabulary is
//                   more useful than returning `null`.
//
// 🔴 THE FORM DOES NOT DECLARE A FRAME, AND THIS MODULE MUST NOT INVENT ONE. The axis
//    ticks state which coordinates the form carries; they do NOT state the grid's size,
//    its rotation, its side or its origin. Grid size is derived from the orientation and
//    the physical spec -- never back-derived from the range of the data. So `extent` is
//    reported as an extent and is never laundered into `grid_cols`/`grid_rows`.
// ═══════════════════════════════════════════════════════════════════════════════

import { parseTsv, serializeTsv } from '../tsv.js';
import { frameFromDeclaration, ABSENT, DECLARED } from './declaration.js';

// ── the format's own constants, each traceable to the reference implementation ───

/** A cell spanning at least this share of the table width is the TITLE band.
 *  `html_topology_parser.py` -- `wide_threshold = int(col_count * 0.7)`. */
export const SECTION_WIDE_RATIO = 0.7;

/** An axis needs at least this many ticks to be an axis. Both references agree:
 *  `len(ticks) >= 2` and `COORD_MIN_TICKS`. */
export const MIN_AXIS_TICKS = 2;

/** Header chains join with this. `meta_key = "_".join(ancestors_vals)`. */
export const META_KEY_JOIN = '_';

/** Exactly how long a LEFT-ancestor chain must be for a header cell to be a VALUE:
 *  GROUP then KEY, and nothing else. `if len(ancestors) == 2`. */
export const META_CHAIN_LEN = 2;

/** The column projection the ingestion pipeline applies AFTER parsing
 *  (`bonding_map_parser.py :: CustomHtmlIngestionParser.process_dataframe`): rename, then
 *  lowercase everything. Exported because a caller that wants to know what the DB will
 *  hold must not re-derive it, and because the rename is a property of THIS form. */
export const INGESTION_RENAME = Object.freeze({ BDIE_LOT: 'base', VALUE: 'leg' });

/** What the operator reads when the form does not state its own identity. UI string. */
export const UNKNOWN_DISPLAY = '미상';

/** The two honest-degradation codes this module can attach to an intake rejection.
 *  Borrowed vocabulary -- do not add a third without the same justification. */
export const REJECTION_CODES = Object.freeze(['not_declared', 'mapping_unavailable']);

/** The two surfaces of ONE form. `rich` is the HTML table ingestion reads; `plain` is the
 *  delimited projection that survives the clipboard. See `writeMapForm` for why the plain
 *  surface deliberately carries no header band. */
export const FORM_SURFACES = Object.freeze(['rich', 'plain']);

// ═══════════════════════════════════════════════════════════════════════════════
// shared predicates
// ═══════════════════════════════════════════════════════════════════════════════

// A coordinate is a WHOLE integer. Not `parseInt`: `parseInt('3A')` is 3, and then `3A`
// passes as an axis tick. This is the spelling `coord_table_paste` already uses.
//
// ⚠️ MEASURED DIVERGENCE FROM THE REFERENCE, recorded rather than smoothed over: Python's
//    `int()` also accepts digit separators (`int('1_0')`) and non-ASCII digits, so the
//    reference would read a tick this rejects. The client-side spelling is chosen because
//    the two client surfaces must agree with each other first.
function coordInt(raw) {
  const t = String(raw === null || raw === undefined ? '' : raw).trim();
  return /^[+-]?\d+$/.test(t) ? parseInt(t, 10) : null;
}

const asText = (v) => String(v === null || v === undefined ? '' : v);
const isBlank = (v) => asText(v).trim() === '';

function refusal(code, reason) {
  return Object.freeze({
    ok: false, code, reason,
    declaration: null, cells: null,
    intake: Object.freeze({ cellsRead: 0, cellsAccepted: 0, rejected: Object.freeze([]) }),
  });
}

// Rejections are AGGREGATE. The UI states a count and a reason, never a row list, so the
// accumulator is shaped for that from the start.
function makeRejections() {
  const byCode = new Map();
  return {
    add(code, reason) {
      const k = code + '\u0000' + reason;
      const hit = byCode.get(k);
      if (hit) { hit.count++; return; }
      byCode.set(k, { code, reason, count: 1 });
    },
    list() {
      return Object.freeze([...byCode.values()]
        .sort((a, b) => (b.count - a.count) || (a.code < b.code ? -1 : 1))
        .map(r => Object.freeze({ ...r })));
    },
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// the rich surface -- an HTML table
//
// 🔴 THE GRID ORIGIN IS DERIVED TWICE AND MUST AGREE. This is the single most important
//    rule in the format and it is NOT a style choice: X and Y are part of the business
//    key, so a plausible-looking wrong origin files every cell of the map under
//    coordinates that do not exist. The two derivations have blind spots at OPPOSITE ends
//    of the document -- top-anchored reads a row's SHAPE and is fooled by operator junk
//    above the grid; bottom-anchored reads where the Y labels begin and is dragged upward
//    by any unmerged integer in column 0. They fail on disjoint inputs, so agreement is
//    evidence. On disagreement this module REFUSES with a named reason and reads nothing.
// ═══════════════════════════════════════════════════════════════════════════════

const TAG_RE = /<[^>]*>/g;
const ENTITIES = Object.freeze({
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0',
});

function decodeEntities(s) {
  return s.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (m, body) => {
    if (body.charAt(0) === '#') {
      const hex = body.charAt(1) === 'x' || body.charAt(1) === 'X';
      const n = parseInt(hex ? body.slice(2) : body.slice(1), hex ? 16 : 10);
      return Number.isFinite(n) ? String.fromCodePoint(n) : m;
    }
    const hit = ENTITIES[body.toLowerCase()];
    return hit === undefined ? m : hit;
  });
}

// `BeautifulSoup`'s `cell.text` is the concatenation of every descendant string, and
// `TableNode` stores it `.strip()`ed. Stripping tags then trimming reproduces that for
// the flat cells this form uses. Nested tables are not supported and are not part of the
// form -- a caller handed one gets a refusal from the shape checks below, not a guess.
function cellText(html) {
  return decodeEntities(String(html).replace(TAG_RE, ' ')).replace(/\s+/g, ' ').trim();
}

function attrInt(tagHtml, name) {
  const m = new RegExp(name + '\\s*=\\s*"?\'?(\\d+)', 'i').exec(tagHtml);
  const n = m ? parseInt(m[1], 10) : 1;
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

/** The <table> reconstructed into a virtual 2D grid with merges expanded -- the same shape
 *  `_reconstruct_2d_grid` builds, because every rule downstream is expressed in it. */
function reconstructGrid(html) {
  const table = /<table\b[\s\S]*?<\/table\s*>/i.exec(String(html));
  if (!table) return null;
  const body = table[0];

  const grid = new Map();          // "r,c" -> node
  const nodes = [];
  const key = (r, c) => r + ',' + c;
  let rowIdx = 0;
  let maxColIdx = 0;
  let counter = 0;

  const trRe = /<tr\b[^>]*>([\s\S]*?)<\/tr\s*>/gi;
  let tr;
  while ((tr = trRe.exec(body)) !== null) {
    const inner = tr[1];
    let colIdx = 0;
    const tdRe = /<(td|th)\b([^>]*)>([\s\S]*?)<\/\1\s*>/gi;
    let td;
    while ((td = tdRe.exec(inner)) !== null) {
      while (grid.has(key(rowIdx, colIdx))) colIdx++;
      const rowSpan = attrInt(td[2], 'rowspan');
      const colSpan = attrInt(td[2], 'colspan');
      const node = {
        id: 'cell_' + rowIdx + '_' + colIdx + '_' + (counter++),
        value: cellText(td[3]),
        rStart: rowIdx, rEnd: rowIdx + rowSpan - 1,
        cStart: colIdx, cEnd: colIdx + colSpan - 1,
        isHeader: false,
      };
      nodes.push(node);
      for (let r = node.rStart; r <= node.rEnd; r++) {
        for (let c = node.cStart; c <= node.cEnd; c++) {
          grid.set(key(r, c), node);
          if (c > maxColIdx) maxColIdx = c;
        }
      }
      colIdx += colSpan;
    }
    rowIdx++;
  }
  if (nodes.length === 0) return null;
  return { grid, nodes, rowCount: rowIdx, colCount: maxColIdx + 1, at: (r, c) => grid.get(key(r, c)) };
}

const isUnmerged = (n) => (n.rEnd - n.rStart === 0) && (n.cEnd - n.cStart === 0);
const spanCols = (n) => n.cEnd - n.cStart + 1;

// 🔴 ONE MEASURED FACT, STATED ONCE, AND BOTH HALVES MATTER: across the archived corpus
//    every corner and every axis tick is 1x1 and every header-band cell is merged. Ruler
//    cells are unmerged; header cells are not. Recognising the ruler by SHAPE rather than
//    by "it holds numbers" is what keeps a lot id or a slot number out of the axis.
function rulerTicksAt(t, r) {
  const corner = t.at(r, 0);
  if (!corner || !isUnmerged(corner) || coordInt(corner.value) !== null) return null;
  const ticks = [];
  const seen = new Set([corner.id]);
  for (let c = 1; c < t.colCount; c++) {
    const node = t.at(r, c);
    if (!node || seen.has(node.id)) continue;
    seen.add(node.id);
    if (!isUnmerged(node) || coordInt(node.value) === null) return null;
    ticks.push(node);
  }
  return ticks.length >= MIN_AXIS_TICKS ? ticks : null;
}

// The LEFT-ancestor chain, transitively, through blanks. Non-header cells do not lengthen
// the chain but are walked through; already-claimed VALUE cells act as barriers. This is
// `_find_ancestors(..., "LEFT", ...)` expressed directly on the grid: for a node, the LEFT
// neighbours are exactly the distinct nodes occupying the column immediately to its left
// over its own row range.
function leftAncestors(t, start, barriers) {
  const out = [];
  const seenOut = new Set();
  const visited = new Set([start.id]);
  const walk = (curr) => {
    if (curr.cStart === 0) return;
    const cands = [];
    const local = new Set();
    for (let r = curr.rStart; r <= curr.rEnd; r++) {
      const p = t.at(r, curr.cStart - 1);
      if (p && !local.has(p.id)) { local.add(p.id); cands.push(p); }
    }
    for (const p of cands) {
      if (visited.has(p.id)) continue;
      if (!(p.cEnd < curr.cStart)) continue;
      if (!(Math.max(p.rStart, curr.rStart) <= Math.min(p.rEnd, curr.rEnd))) continue;
      visited.add(p.id);
      if (p.isHeader && !seenOut.has(p.id)) { seenOut.add(p.id); out.push(p); }
      if (!barriers.has(p.id)) walk(p);
    }
  };
  walk(start);
  return out;
}

function readRich(source, opts) {
  const t = reconstructGrid(source);
  if (!t) return refusal('mapping_unavailable', '표를 찾지 못했습니다 — 맵 양식의 표 전체를 넣어 주십시오.');

  // ⓐ top-anchored: the first ruler-SHAPED row.
  let topAnchor = null;
  let topTicks = null;
  for (let r = 0; r < t.rowCount; r++) {
    const ticks = rulerTicksAt(t, r);
    if (ticks) { topAnchor = r; topTicks = ticks; break; }
  }
  // ⓑ bottom-anchored: one row above the topmost unmerged integer in column 0.
  const yLabelRows = t.nodes
    .filter(n => n.cStart === 0 && isUnmerged(n) && coordInt(n.value) !== null)
    .map(n => n.rStart);
  const bottomAnchor = yLabelRows.length ? Math.min(...yLabelRows) - 1 : null;

  if (topAnchor === null || bottomAnchor === null || topAnchor !== bottomAnchor) {
    let reason;
    if (topAnchor === null && bottomAnchor === null) {
      reason = 'X축 눈금 줄도 Y축 좌표도 없습니다 — 이 표는 2차원 맵 양식의 모양이 아닙니다.';
    } else if (topAnchor === null) {
      reason = `X축 눈금 줄 모양(좌표가 아닌 모서리 칸 + 정수 눈금 ${MIN_AXIS_TICKS}개 이상)인 줄이 `
        + `없는데, 첫 열의 Y 좌표는 ${bottomAnchor + 1}번째 줄이 눈금 줄이라고 말합니다.`;
    } else if (bottomAnchor === null) {
      reason = `${topAnchor + 1}번째 줄이 눈금 줄 모양이지만 첫 열에 Y 좌표가 없어 확인할 수 없습니다.`;
    } else {
      reason = `격자 원점을 두 판정이 엇갈립니다 — 줄 모양은 ${topAnchor + 1}번째 줄`
        + `(눈금 ${topTicks.map(n => n.value).join(', ')}), 첫 열의 Y 좌표는 ${bottomAnchor + 1}번째 `
        + '줄을 가리킵니다. 격자 위에 눈금처럼 생긴 다른 줄이 섞여 있습니다 — 표만 넣어 주십시오.';
    }
    return refusal('mapping_unavailable', reason);
  }

  const xRow = topAnchor;
  const xNodes = topTicks.slice().sort((a, b) => a.cStart - b.cStart);
  const yNodes = t.nodes
    .filter(n => n.cStart === 0 && isUnmerged(n) && coordInt(n.value) !== null && n.rStart > xRow)
    .sort((a, b) => a.rStart - b.rStart);

  const dup = duplicateTicks(xNodes.map(n => coordInt(n.value)), yNodes.map(n => coordInt(n.value)));
  if (dup) return refusal('mapping_unavailable', dup);

  // The header role is POSITIONAL, never lexical. "Is this a header?" answered by "does it
  // parse as a number" is wrong in both directions on this form: a numeric lot id drops out
  // of the header set and shifts the chain, and a non-numeric BIN letter inside the grid
  // gets promoted out of the data.
  for (const n of t.nodes) {
    n.isHeader = !!n.value && n.rEnd < xRow && !isUnmerged(n);
  }

  const wideThreshold = Math.trunc(t.colCount * SECTION_WIDE_RATIO);
  const sectionHeaders = t.nodes
    .filter(n => n.isHeader && spanCols(n) > 1 && spanCols(n) >= wideThreshold)
    .sort((a, b) => a.rStart - b.rStart);
  const titleNode = sectionHeaders.length ? sectionHeaders[0] : null;

  const axisIds = new Set([...xNodes, ...yNodes].map(n => n.id));
  const metaNodes = t.nodes
    .filter(n => n.isHeader && n.value)
    .filter(n => (!titleNode || n.id !== titleNode.id) && !axisIds.has(n.id))
    .sort((a, b) => a.cStart - b.cStart);

  const identity = [];
  const claimed = new Set();
  for (const node of metaNodes) {
    const anc = leftAncestors(t, node, claimed).filter(a => !claimed.has(a.id));
    if (anc.length !== META_CHAIN_LEN) continue;
    anc.sort((a, b) => a.cStart - b.cStart);
    const parts = anc.map(a => a.value).filter(Boolean);
    if (!parts.length) continue;
    identity.push(Object.freeze({
      key: parts.join(META_KEY_JOIN), value: node.value, source: DECLARED,
    }));
    claimed.add(node.id);
  }

  // ── the cells ─────────────────────────────────────────────────────────────────
  const rej = makeRejections();
  const cells = [];
  const tickCols = new Set(xNodes.map(n => n.cStart));
  for (const yNode of yNodes) {
    const rY = yNode.rStart;
    const yVal = coordInt(yNode.value);
    for (const xNode of xNodes) {
      const data = t.at(rY, xNode.cStart);
      if (!data || data.id === yNode.id || data.id === xNode.id) {
        // The axes name this coordinate but the table has no cell that answers to it.
        rej.add('mapping_unavailable',
          '좌표는 있는데 그 자리에 칸이 없습니다 — 표의 줄 길이가 고르지 않습니다.');
        continue;
      }
      cells.push(Object.freeze({ x: coordInt(xNode.value), y: yVal, value: data.value }));
    }
    // 🔴 A VALUE WITH NO COORDINATE IS NOT DROPPED SILENTLY. The reference HTML parser
    //    iterates the ticks and never looks at the other columns, so these vanish without
    //    a trace. This module counts them instead -- that is the whole point of the intake
    //    report, and a dropped value is exactly the screen-looks-fine defect class.
    const seenOffAxis = new Set();
    for (let c = 1; c < t.colCount; c++) {
      if (tickCols.has(c)) continue;
      const n = t.at(rY, c);
      if (!n || seenOffAxis.has(n.id) || isBlank(n.value)) continue;
      seenOffAxis.add(n.id);
      rej.add('not_declared', 'X축 눈금이 없는 열에 값이 있습니다 — 그 값을 놓을 좌표가 선언되지 않았습니다.');
    }
  }

  return assemble({
    surface: 'rich',
    title: titleNode ? titleNode.value : null,
    identity,
    xVals: xNodes.map(n => coordInt(n.value)),
    yVals: yNodes.map(n => coordInt(n.value)),
    cells, rej, opts,
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// the plain surface -- the delimited projection that survives the clipboard
//
// Same two derivations, same refusal on disagreement. What it CANNOT carry is the header
// band: in plain text a merged cell is indistinguishable from a value followed by blanks,
// so identity is `미상` here by construction rather than by accident.
// ═══════════════════════════════════════════════════════════════════════════════

function plainRulerTicks(line) {
  const width = (line || []).length;
  if (width < 1 + MIN_AXIS_TICKS) return null;
  if (coordInt(line[0]) !== null) return null;         // an integer corner means a data row
  const ticks = [];
  for (let c = 1; c < width; c++) {
    const f = asText(line[c]);
    if (isBlank(f)) {
      // Blanks before the first tick are not allowed (the ruler starts at column 1);
      // blanks after are tail padding only -- a hole in the middle leaves a column with
      // no coordinate.
      if (ticks.length === 0) return null;
      for (let d = c; d < width; d++) if (!isBlank(line[d])) return null;
      break;
    }
    const v = coordInt(f);
    if (v === null) return null;
    ticks.push({ c, v });
  }
  return ticks.length >= MIN_AXIS_TICKS ? ticks : null;
}

function readPlain(source, opts) {
  const lines = parseTsv(source, { trimCells: true });
  let lastContent = -1;
  for (let r = 0; r < lines.length; r++) {
    if ((lines[r] || []).some(f => !isBlank(f))) lastContent = r;
  }
  if (lastContent < 0) return refusal('mapping_unavailable', '내용이 비어 있습니다.');

  let topAnchor = null;
  let topTicks = null;
  for (let r = 0; r <= lastContent; r++) {
    const t = plainRulerTicks(lines[r]);
    if (t) { topAnchor = r; topTicks = t; break; }
  }
  const yRows = [];
  for (let r = 0; r <= lastContent; r++) {
    if (coordInt((lines[r] || [])[0]) !== null) yRows.push(r);
  }
  const bottomAnchor = (yRows.length >= MIN_AXIS_TICKS && yRows[0] >= 1) ? yRows[0] - 1 : null;

  if (topAnchor === null || bottomAnchor === null || topAnchor !== bottomAnchor) {
    let reason;
    if (topAnchor === null && bottomAnchor === null) {
      reason = 'X축 눈금 줄도 Y축 좌표도 없습니다 — 이 표는 2차원 맵 양식의 모양이 아닙니다.';
    } else if (topAnchor === null) {
      reason = `X축 눈금 줄 모양인 줄이 없는데, 첫 열의 Y 좌표는 ${bottomAnchor + 1}번째 줄이 `
        + '눈금 줄이라고 말합니다.';
    } else if (bottomAnchor === null) {
      reason = `${topAnchor + 1}번째 줄이 X축 눈금 모양인데, 그 아래 첫 열에 Y 좌표가 `
        + `${MIN_AXIS_TICKS}개 이상 없습니다 — X축만으로는 셀의 자리를 정할 수 없습니다.`;
    } else {
      reason = `격자 원점을 두 판정이 엇갈립니다 — 줄 모양은 ${topAnchor + 1}번째 줄`
        + `(눈금 ${topTicks.map(t => t.v).join(', ')}), 첫 열의 Y 좌표는 ${bottomAnchor + 1}번째 `
        + '줄을 가리킵니다. 표 위에 다른 내용이 섞여 있습니다 — 표만 넣어 주십시오.';
    }
    return refusal('mapping_unavailable', reason);
  }
  for (let i = 1; i < yRows.length; i++) {
    if (yRows[i] !== yRows[i - 1] + 1) {
      return refusal('mapping_unavailable',
        `${yRows[i - 1] + 2}번째 줄의 첫 칸이 Y 좌표가 아닙니다 — 표의 모든 줄은 첫 칸에 `
        + 'Y 좌표를 가져야 합니다.');
    }
  }

  const yVals = yRows.map(r => coordInt(lines[r][0]));
  const dup = duplicateTicks(topTicks.map(t => t.v), yVals);
  if (dup) return refusal('mapping_unavailable', dup);

  const rej = makeRejections();
  const cells = [];
  const tickCols = new Set(topTicks.map(t => t.c));
  for (let i = 0; i < yRows.length; i++) {
    const line = lines[yRows[i]] || [];
    for (const t of topTicks) {
      cells.push(Object.freeze({ x: t.v, y: yVals[i], value: asText(line[t.c]).trim() }));
    }
    for (let c = 1; c < line.length; c++) {
      if (tickCols.has(c) || isBlank(line[c])) continue;
      rej.add('not_declared', 'X축 눈금이 없는 열에 값이 있습니다 — 그 값을 놓을 좌표가 선언되지 않았습니다.');
    }
  }
  // Anything above the ruler or below the last coordinate row is not part of the table.
  for (let r = 0; r < topAnchor; r++) {
    if ((lines[r] || []).some(f => !isBlank(f))) {
      rej.add('not_declared', '표 위에 표가 아닌 내용이 있습니다 — 좌표가 없어 읽지 않았습니다.');
    }
  }
  for (let r = yRows[yRows.length - 1] + 1; r <= lastContent; r++) {
    if ((lines[r] || []).some(f => !isBlank(f))) {
      rej.add('not_declared', '표 아래에 표가 아닌 내용이 있습니다 — 좌표가 없어 읽지 않았습니다.');
    }
  }

  return assemble({
    surface: 'plain', title: null, identity: [],
    xVals: topTicks.map(t => t.v), yVals, cells, rej, opts,
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// assembly -- the same declaration shape from either surface
// ═══════════════════════════════════════════════════════════════════════════════

function duplicateTicks(xVals, yVals) {
  const dupOf = (vals) => {
    const seen = new Set();
    for (const v of vals) { if (seen.has(v)) return v; seen.add(v); }
    return null;
  };
  const dx = dupOf(xVals);
  if (dx !== null) return `X 좌표 ${dx}이(가) 두 번 나옵니다 — 어느 열이 그 좌표인지 정할 수 없습니다.`;
  const dy = dupOf(yVals);
  if (dy !== null) return `Y 좌표 ${dy}이(가) 두 번 나옵니다 — 어느 줄이 그 좌표인지 정할 수 없습니다.`;
  return null;
}

const direction = (vals) => {
  if (vals.length < 2) return 'indeterminate';
  const up = vals[vals.length - 1] > vals[0];
  for (let i = 1; i < vals.length; i++) {
    if (up ? !(vals[i] > vals[i - 1]) : !(vals[i] < vals[i - 1])) return 'mixed';
  }
  return up ? 'ascending' : 'descending';
};

function assemble(a) {
  const { xVals, yVals, cells, rej, opts } = a;
  const o = opts || {};
  const titleDeclared = a.title !== null && a.title !== undefined && String(a.title).trim() !== '';

  // 🔴 THE FRAME COMES BACK ALL-ABSENT ON PURPOSE. The form states coordinates, not a
  //    frame, and this is the codebase's one vocabulary for saying so. Passing
  //    `o.frameMeta` lets a caller that ALREADY holds the map's registered metadata get the
  //    axes filled from that source -- the form never fills them.
  const frame = frameFromDeclaration(o.frameMeta || null, o.frameOpts);

  const declaration = Object.freeze({
    surface: a.surface,
    title: Object.freeze({
      value: titleDeclared ? String(a.title) : null,
      source: titleDeclared ? DECLARED : ABSENT,
      display: titleDeclared ? String(a.title) : UNKNOWN_DISPLAY,
    }),
    identity: Object.freeze(a.identity.slice()),
    extent: Object.freeze({
      xTicks: Object.freeze(xVals.slice()), yTicks: Object.freeze(yVals.slice()),
      minX: Math.min(...xVals), maxX: Math.max(...xVals),
      minY: Math.min(...yVals), maxY: Math.max(...yVals),
      nx: xVals.length, ny: yVals.length,
      xDirection: direction(xVals), yDirection: direction(yVals),
    }),
    frame,
  });

  const rejected = rej.list();
  return Object.freeze({
    ok: true, code: null, reason: '',
    declaration,
    cells: Object.freeze(cells.slice()),
    intake: Object.freeze({
      cellsRead: cells.length + rejected.reduce((n, r) => n + r.count, 0),
      cellsAccepted: cells.length,
      rejected,
    }),
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// PUBLIC SURFACE
// ═══════════════════════════════════════════════════════════════════════════════

/** Which surface is this text? The rich surface announces itself with a `<table>`; there is
 *  nothing subtler to detect, and guessing harder would be the "best-effort placement" this
 *  format's rules exist to forbid. */
export function detectFormSurface(source) {
  return /<table\b/i.test(String(source === null || source === undefined ? '' : source))
    ? 'rich' : 'plain';
}

/**
 * Read the operator form. THE DOORWAY IN.
 *
 * @param {string} source     the form, as HTML (rich) or delimited text (plain).
 * @param {object} [opts]
 * @param {string} [opts.surface]    force a surface instead of detecting it.
 * @param {object} [opts.frameMeta]  a `grid_metadata` blob the CALLER already holds. The
 *                                   form never supplies one; this is how a caller attaches
 *                                   the registered frame without this module inventing it.
 * @param {object} [opts.frameOpts]  passed straight to `frameFromDeclaration` (this is how
 *                                   config defaults reach a module that cannot import config).
 *
 * @returns {{ok: boolean, code: string|null, reason: string,
 *            declaration: object|null, cells: ReadonlyArray<{x:number,y:number,value:string}>|null,
 *            intake: {cellsRead:number, cellsAccepted:number,
 *                     rejected: ReadonlyArray<{code:string, reason:string, count:number}>}}}
 *
 * 🔴 `intake.rejected` IS THE HALF THAT HAS NO MIRROR ON THE WAY OUT. Aggregate counts with
 *    a reason, deduplicated by reason, heaviest first -- shaped for a UI that states one
 *    line, not a row list.
 */
export function readMapForm(source, opts) {
  const o = opts || {};
  const text = source === null || source === undefined ? '' : String(source);
  const surface = o.surface || detectFormSurface(text);
  if (FORM_SURFACES.indexOf(surface) < 0) {
    return refusal('mapping_unavailable', `알 수 없는 양식 종류입니다 — ${surface}`);
  }
  return surface === 'rich' ? readRich(text, o) : readPlain(text, o);
}

/**
 * Write the operator form. THE DOORWAY OUT.
 *
 * Writing cannot partially fail: every cell handed in is placed. What it CAN do is fail to
 * encode the identity band, and it says so in `warnings` rather than dropping it silently.
 *
 * @param {object} declaration  a declaration from `readMapForm`, or any object with the
 *                              same `title`/`identity`/`extent` shape.
 * @param {Array<{x:number,y:number,value:*}>} cells  absolute coordinates, not screen ones.
 * @param {object} [opts]
 * @param {string} [opts.corner]  the ruler corner label. Must NOT parse as an integer.
 *
 * @returns {{html: string, text: string, warnings: ReadonlyArray<string>, cols: number}}
 *
 * ⚠️ `text` IS THE MATRIX ALONE, and that is a format fact rather than a shortcut. In plain
 *    text a merged header cell is indistinguishable from a value followed by blanks, and
 *    the reader on the other side refuses a table with anything above its ruler. So the
 *    rich surface carries identity and the plain surface carries coordinates; a plain
 *    surface with a title band would be rejected by the very reader it is written for.
 */
export function writeMapForm(declaration, cells, opts) {
  const o = opts || {};
  const d = declaration || {};
  const ext = d.extent || {};
  const list = Array.isArray(cells) ? cells : [];

  const xTicks = normaliseTicks(ext.xTicks, list.map(c => c.x));
  const yTicks = normaliseTicks(ext.yTicks, list.map(c => c.y));
  const cols = 1 + xTicks.length;
  const warnings = [];

  const byKey = new Map();
  for (const c of list) byKey.set(c.x + ',' + c.y, asText(c.value));
  const at = (x, y) => {
    const v = byKey.get(x + ',' + y);
    return v === undefined ? '' : v;
  };

  const corner = o.corner === undefined ? '' : String(o.corner);
  if (coordInt(corner) !== null) {
    throw new Error('writeMapForm: corner label must not read as a coordinate');
  }

  // ── plain: the matrix alone ────────────────────────────────────────────────────
  const matrix = [[corner].concat(xTicks.map(String))];
  for (const y of yTicks) matrix.push([String(y)].concat(xTicks.map(x => at(x, y))));
  const text = serializeTsv(matrix);

  // ── rich: title band, identity band, then the same matrix ─────────────────────
  const parts = ['<table>'];
  const titleValue = d.title && d.title.source === DECLARED ? asText(d.title.value) : '';
  if (titleValue !== '') {
    // colspan = the full width, which is trivially at least the wide threshold.
    parts.push(`<tr><td colspan="${cols}">${esc(titleValue)}</td></tr>`);
  }

  const identity = Array.isArray(d.identity) ? d.identity : [];
  // 🔴 ONE TRIPLE PER ROW. Two triples on one row would chain: the first VALUE is itself a
  //    merged non-empty header, so it lengthens the second VALUE's LEFT chain past the
  //    length that makes it a value, and the whole pair silently stops being identity.
  const band = bandSpans(cols);
  if (identity.length && !band) {
    warnings.push('identity_not_encodable');
  } else {
    for (const item of identity) {
      const idx = String(item.key).indexOf(META_KEY_JOIN);
      if (idx <= 0 || idx >= String(item.key).length - 1) {
        warnings.push('identity_key_not_a_group_key_pair:' + item.key);
        continue;
      }
      const group = String(item.key).slice(0, idx);
      const keyWord = String(item.key).slice(idx + META_KEY_JOIN.length);
      parts.push('<tr>'
        + `<td colspan="${band[0]}">${esc(group)}</td>`
        + `<td colspan="${band[1]}">${esc(keyWord)}</td>`
        + `<td colspan="${band[2]}">${esc(asText(item.value))}</td>`
        + '</tr>');
    }
  }

  parts.push('<tr>' + matrix[0].map(v => `<td>${esc(v)}</td>`).join('') + '</tr>');
  for (let i = 1; i < matrix.length; i++) {
    parts.push('<tr>' + matrix[i].map(v => `<td>${esc(v)}</td>`).join('') + '</tr>');
  }
  parts.push('</table>');

  return Object.freeze({
    html: parts.join(''), text, cols,
    warnings: Object.freeze(warnings),
  });
}

/**
 * The flattened record list the ingestion pipeline produces from this form, BEFORE its
 * rename/lowercase projection. Exported so a caller -- or a contract vector -- can score
 * this module against the reference parser's output key by key instead of against a belief
 * about what the format means.
 */
export function ingestionRecords(declaration, cells) {
  const d = declaration || {};
  const title = d.title && d.title.source === DECLARED ? asText(d.title.value) : 'Default';
  const meta = {};
  for (const item of (Array.isArray(d.identity) ? d.identity : [])) meta[item.key] = asText(item.value);
  return (Array.isArray(cells) ? cells : []).map(c => Object.assign(
    { TITLE: title }, meta, { X: c.x, Y: c.y, VALUE: asText(c.value) }));
}

// ── writer helpers ──────────────────────────────────────────────────────────────

function normaliseTicks(declaredTicks, observed) {
  if (Array.isArray(declaredTicks) && declaredTicks.length) return declaredTicks.map(Number);
  const seen = new Set();
  const out = [];
  for (const v of observed) {
    const n = Number(v);
    if (!Number.isFinite(n) || seen.has(n)) continue;
    seen.add(n); out.push(n);
  }
  return out.sort((a, b) => a - b);
}

// Three merged cells that fill the row exactly, each wide enough to count as merged and
// none wide enough to be mistaken for the TITLE band. Below the minimum width there is no
// such split and the caller is told rather than given a broken band.
function bandSpans(cols) {
  const base = Math.floor(cols / 3);
  if (base < 2) return null;
  const spans = [base, base, cols - 2 * base];
  const wide = Math.trunc(cols * SECTION_WIDE_RATIO);
  if (spans.some(s => s > 1 && s >= wide)) return null;
  return spans;
}

function esc(s) {
  return asText(s)
    .split('&').join('&amp;')
    .split('<').join('&lt;')
    .split('>').join('&gt;');
}
