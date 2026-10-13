// ═══════════════════════════════════════════════════════════════════════════════
// 걷기 결과 표 — «DOM 이 한 조각도 없는» 절반.
//
// 🔴 왜 자기 모듈인가 (C-72, 2026-09-10). 이 결정들은 `main.js` 의 `boot()` 안 클로저였고,
//    그래서 「이 화면이 그 함수를 부르나」를 «거동으로» 잴 자리가 없었습니다. C-70 이 구획과
//    컬럼을 `derive.js` 로 올렸지만, 그것을 «부르는 쪽»이 여전히 페이지 안이라 누가 사본을
//    다시 넣어도 빨개지는 것이 없었습니다. 상설: 「재려는 로직을 import 되는 모듈로 뺀다」.
//
// 🔴 여기서 «정하지» 않습니다. 구획은 `sectionsByType`, 머리는 `sectionHeading` — `derive.js` 의 것이고 걷기
//    검색창이 부르는 바로 그 함수들입니다. 열과 칸은 reach_table 의 것(행 하나가 노드, 열은 그 노드의 키·속성과
//    걸음의 변 속성), 평표에서 옮겨 온 두 열(Conflicts · 확인 술어)은 `tableColumns` · `cellSource` 그대로입니다.
//
// 🔴 텍스트도 여기서 만듭니다. 빈 칸은 «빈 칸»입니다 — 「—」나 0 으로 채우면 「없다」와
//    「0 이다」가 같은 글자가 됩니다. 그 판정이 렌더러에 있으면 node 가 채점할 수 없습니다.
// ═══════════════════════════════════════════════════════════════════════════════
import { confirmedPredicates, sectionsByType, sectionHeading, tableColumns, cellSource, pluralAttributes, staticTypes, cutBudgets } from './derive.js';
import { typeGraph, entityOfId } from '../rnd_board/api.js';
// The table is the formula (lead 5cf5c3401; one side for a + only walk, E1): rows, groups and columns in, cells out.
import { indexGraph, groupsOf, defaultColumns, tableOf, cellOf, readsOf, recordsOf, valueKind, valueWords, saysValue, columnKey, groupKey, stepWords, numberOf, pointWords, WAYS_A_CELL } from './reach_table.js';
import { isBlank } from '../absent.js';
import { walkPoints } from './trend.js';
import { localStamp } from '../server_time.js';

/** The edges one step from a type (lead 53050a4ec): each declared predicate touching it and the type at its other
 *  end, read off the type graph the route list reads - a predicate within the type (bonded_to die -> die) included,
 *  which the route list keeps as a loop chip. The walk takes any first step. Nothing is guessed from the data. */
export function nextRoutes(declaration, type) {
  const out = [];
  for (const edge of typeGraph(declaration).edges) {
    const to = edge.from === type ? edge.to : edge.to === type ? edge.from : null;
    if (to !== null && !out.some((r) => r.predicate === edge.predicate && r.to === to)) {
      // Its words the table's arrows (lead 10-11 W): out «→», in «←», the far type.
      out.push({ predicate: edge.predicate, to, words: stepWords({ predicate: edge.predicate, direction: edge.from === type ? 'outgoing' : 'incoming' }, to) });
    }
  }
  return out;
}

/** 한 번에 그리는 행 상한. 넘은 것은 «수»로 말합니다 — 조용히 자르지 않습니다. */
export const ROW_CAP = 200;

// ⚰️ valueText · isNumericText · qualifiersByNode · qualifierNamesOf retired 10-11 with the flat table's seat (E1): its
//    cells were text from `cellSource` on the edge qualifiers folded into the node they reached; the walk table reads a
//    column's way (reach_table.cellOf), every edge's value kept, the edge's own predicate in the head.

/** A group's cell for a node it did not reach; a reached cell with no value; a start's route; the Δ head. */
export const MISSING = 'missing';
export const EMPTY = '—';
/** «Does a shortest path reach the auxiliary node(s)?» (owner 10-12, the walk's judgment): its words - found with the hops
 *  (and which node, when there are several), none, unknown at the cap; a node not judged «—». */
export const REACH_WORDS = Object.freeze({ head: '→', reach: 'reach', none: 'none', unknown: 'unknown', only: 'Reaches only' });
const nodeWords = (id) => { const n = entityOfId(id) || {}; return Object.values(n.keys || {}).map(valueWords).join(' / ') || id; };
export function reachWords(judged, several) {
  if (!judged) return EMPTY;
  if (judged.state === 'found') return `${judged.hops} ${judged.hops === 1 ? 'hop' : 'hops'}${several && judged.via ? ` → ${nodeWords(judged.via)}` : ''}`;
  return judged.state === 'none' ? REACH_WORDS.none : REACH_WORDS.unknown;
}

/** A judged section's rows told by their judgment (owner 10-12 «ㄷ»): «<head>: N reach · N none · N unknown». */
export function reachTally(head, rows) {
  const n = (state) => rows.filter((row) => row.reach && row.reach.state === state).length;
  return `${head}: ${n('found')} ${REACH_WORDS.reach} · ${n('none')} ${REACH_WORDS.none} · ${n('unknown')} ${REACH_WORDS.unknown}`;
}
export const STARTED = 'start';
export const DELTA = 'Δ';
// ⚰️ ROUTE retired 10-11 with the Route column (lead W): how a side reached a row is the node cell's source line.
/** Where a route stands, for a node no side of the walk reached - a time page's other rows (lead 10-11). */
export const NOT_WALKED = 'not in this walk';

/** A path the server walked (an answer's evidence) in words: its hops' predicates in order, predicates only (owner 10-10
 *  «라우트는 술어만»). A hop reached by two predicates says both. */
export const routeWords = (path) => path.hops.slice(1).map((hop) => (hop.predicates || []).join(' / ')).join(' → ');

/** The paths the server walked to each node it ranked - an answer's evidence - by node id. The route cells and the
 *  graph's branch (lead 10-11 G-2) read them here. */
export const walkedPaths = (result) => new Map((((result && result.propagation) || {}).ranked || []).map((row) => [row.id, row.evidence || []]));

/** The ways a walk took to the collected types (owner 10-12 「실제 걸은 경로로 리턴 안 해?」): each node of those types by
 *  the way its evidence walked - «type —predicate→ type …» - a line a way, its nodes counted, the most first. */
export function walkedRoutes(result, collect) {
  const types = new Map(((result && result.nodes) || []).map((n) => [n.id, n.type]));
  const typeOf = (id) => types.get(id) || (entityOfId(id) || {}).type || id;
  const ways = new Map();
  for (const [id, evidence] of walkedPaths(result)) {
    if (!collect.has(typeOf(id))) continue;
    for (const e of evidence) {
      const hops = e.hops || [];
      if (hops.length < 2) continue;
      const words = hops.map((h, i) => (i ? `—${(h.predicates || []).join('/')}→ ${typeOf(h.id)}` : typeOf(h.id))).join(' ');
      const way = ways.get(words) || { words, follow: [...new Set(hops.slice(1).flatMap((h) => h.predicates || []))], hops: hops.length - 1, nodes: new Set() };
      way.nodes.add(id);
      ways.set(words, way);
    }
  }
  return [...ways.values()].map((w) => ({ words: w.words, follow: w.follow, hops: w.hops, count: w.nodes.size }))
    .sort((a, b) => b.count - a.count || a.hops - b.hops);
}

/**
 * How a side reached a node and who gave a value, read off one walk's answer (leads df11f9e81 B, 99ed68cb7 C):
 *   route(g, id)   the paths the server walked to `id` from side g's starts - its evidence - a start «start»
 *   source(g, id)  the node a read ends at: its keys in their declared order (its label without), and route(g, id) - a
 *                  node the answer did not send (collect) read off its id, never the id itself (lead 10-11); no side
 *                  (g null, a time page's other row): «not in this walk» where the route would be
 * The table's cells and the trend's points read both here.
 */
export function valueSources(result, entities, groups) {
  const walked = walkedPaths(result);
  const nodes = new Map(((result && result.nodes) || []).map((n) => [n.id, n]));
  const route = (g, id) => {
    if (g.starts.includes(id)) return { text: STARTED };
    const ways = [...new Set((walked.get(id) || []).filter((path) => g.starts.includes(path.seed)).map(routeWords))];
    return ways.length ? cellWords({ values: ways }, 'string') : { text: EMPTY };
  };
  const keyWords = (id) => {
    const node = nodes.get(id) || entityOfId(id) || {};
    const keys = node.keys || {};
    const declared = ((entities || []).find((e) => e && e.type === node.type) || {}).keys || Object.keys(keys);
    const said = declared.map((k) => keys[k]).filter((v) => !isBlank(v)).map(valueWords);
    return said.length ? said.join(' / ') : (node.label || EMPTY);
  };
  return { route, source: (g, id) => `${keyWords(id)} · ${g ? route(g, id).text : NOT_WALKED}`, keys: keyWords };
}

/**
 * A drawn table as sort, filter and the search box read it (lead 10-11 W addendum 7): its columns, a key and a head each,
 * and its lines - Wide a row a line, the node's own cells then each column's group cells with Δ (sheetOf's order); Long a
 * record a line, LONG_HEAD's. A cell is its words as drawn (the first of several), blank when it says nothing or a side
 * did not reach, its number when it is one.
 */
export function gridOf(section, lines = null) {
  const said = (cell) => {
    const blank = Boolean(cell.missing) || cell.text === EMPTY || cell.text === '';
    const number = 'value' in cell ? (typeof cell.value === 'number' ? cell.value : null) : (blank ? null : numberOf(cell.text));
    return { words: cell.missing ? MISSING : blank ? '' : cell.text, blank, number };
  };
  if (lines) {
    const rows = new Map(section.rows.map((row) => [row.id, row]));
    return { columns: longHead(section.groups).map((head) => ({ key: `long\u0000${head}`, head })),
      lines: lines.map((l) => ({ id: l.id, row: rows.get(l.id), line: l, cells: longRow(l).map((text) => said({ text })) })) };
  }
  const order = (list, delta) => (section.groups.length === 2 && delta !== undefined ? [list[0], delta, list[1]] : list);
  return {
    columns: [...section.centreHeads.map((head) => ({ key: `own\u0000${head}`, head })),
      ...section.columns.flatMap((column, i) => order(section.groups.map((g) => ({ key: `${columnKey(column)}\u0000${g.sign}`, head: `${section.columnHeads[i]} · ${g.sign}` })),
        section.parts[i].delta ? { key: `${columnKey(column)}\u0000${DELTA}`, head: `${section.columnHeads[i]} · ${DELTA}` } : undefined))],
    lines: section.rows.map((row) => ({ id: row.id, row,
      cells: [...row.centre, ...row.cells.flatMap((cell) => order(cell.sides, cell.delta || undefined))].map(said) })),
  };
}

/** A group head's step said as its far end and the way to it - «a → b → far»: { far, via: «a → b →» } (owner 10-12 «m..»). */
export function farEnd(step) {
  const said = /^(.*) ([→←]) (.+)$/.exec(step);
  return said ? { far: said[3], via: `${said[1]} ${said[2]}` } : { far: step, via: '' };
}

/** A column's letters (owner 10-12 「컬럼 여백 남아도는데 존나 넓게」 · 「꿀렁꿀렁」): read off the answer, not what is
 *  shown - a sort, a filter or a check moves none. One letter more than its longest words (`ch` is a «0»; the face is
 *  proportional), between these ends; past the far one a cell is cut, whole in its title. The node column - keys read
 *  whole - to `node` (lead 10-12: 19 to 21-letter quantity keys cut at 18). */
export const COLUMN_CH = Object.freeze({ min: 5, max: 18, node: 36 });
// Hangul, CJK and full-width forms are drawn two letters wide.
const WIDE_LETTER = /[ᄀ-ᅟ⺀-꓏가-힣豈-﫿︰-﹏＀-｠￠-￦]/;
export const lettersOf = (words) => [...String(words)].reduce((n, c) => n + (WIDE_LETTER.test(c) ? 2 : 1), 0);
const columnCh = (letters, min, max) => Math.min(max, Math.max(min, Math.ceil(letters) + 1));
/**
 * A <col>'s width: its cells' letters and padding (`extra` what else sits in their line - the node's copy icon); with
 * `head` the letters of a sorting head over it alone, its «▾» seat beside them when they ask more; `max` its far end.
 */
export function columnWidth(cells, head = 0, extra = '', max = COLUMN_CH.max) {
  const cell = `calc(${columnCh(cells, COLUMN_CH.min, max)}ch + 2 * var(--space-2)${extra})`;
  return head ? `max(${cell}, calc(${columnCh(head, 0, max)}ch + var(--space-2) + var(--space-6)))` : cell;
}

/** A column filter that says something: words it contains, a number at least or at most, values picked out. */
const isSet = (n) => typeof n === 'number' && Number.isFinite(n);
export const filterActive = (f) => Boolean(f && (f.contains || isSet(f.min) || isSet(f.max) || (f.out && f.out.length)));

/** Past this many values a column filters by the words it contains, not by values picked (lead 10-11 W addendum 7: a
 *  category picks values) - a list longer than this is no longer read at a glance. */
export const PICK_MOST = 12;

/**
 * How a column filters (lead 10-11 W addendum 7), judged over every line - not the shown ones, or the kind would change
 * while filtering: a number each - a range; a few values - pick them; else the words it contains. `choices` the values a
 * pick lists, blank as ''.
 */
export function filterKind(lines, k) {
  const cells = lines.map((l) => l.cells[k]);
  const said = cells.filter((c) => !c.blank);
  if (said.length && said.every((c) => c.number !== null)) return { kind: 'range', choices: [] };
  const choices = [...new Set(cells.map((c) => c.words))].sort((a, b) => (a === '' ? 1 : b === '' ? -1 : compareCells({ words: a, number: numberOf(a) }, { words: b, number: numberOf(b) })));
  return choices.filter(Boolean).length <= PICK_MOST ? { kind: 'pick', choices } : { kind: 'contains', choices: [] };
}

/** Two cells in ascending order: numbers as numbers, before words; words as a reader orders them (2 before 10). */
export function compareCells(a, b) {
  if (a.number !== null && b.number !== null) return a.number - b.number;
  if (a.number !== null || b.number !== null) return a.number !== null ? -1 : 1;
  return a.words.localeCompare(b.words, undefined, { numeric: true, sensitivity: 'base' });
}

const lower = (s) => String(s).toLowerCase();
const passes = (cell, f) => (!f.contains || (!cell.blank && lower(cell.words).includes(lower(f.contains))))
  && (!isSet(f.min) || (cell.number !== null && cell.number >= f.min))
  && (!isSet(f.max) || (cell.number !== null && cell.number <= f.max))
  && (!f.out || !f.out.includes(cell.words));

/**
 * THE ONE «what does this table show» SEAT (lead 10-11 W addendum 7, «보이는 것 = 하는 것»): a section's lines - Wide's
 * rows, or Long's records when `lines` are given - through its filter, in its order. The table, Copy, Trend, Walk on and
 * the head check all read it.
 * @param {{rows?: string, find?: string, columns?: object, sort?: {key: string, dir: string}|null}} [f]  All rows ·
 *        Differs · Missing; the search box (a line's words and its node's keys); a filter by column key; a sort - blanks
 *        last either way, a tie in its first order
 * @returns {{columns: Array, lines: Array, all: Array, filtering: boolean}}
 */
export function shownOf(section, f = {}, lines = null) {
  const grid = gridOf(section, lines);
  const filter = f.rows || 'all';
  const find = lower((f.find || '').trim());
  const at = new Map(grid.columns.map((c, k) => [c.key, k]));
  const tests = Object.entries(f.columns || {}).filter(([key, x]) => at.has(key) && filterActive(x)).map(([key, x]) => [at.get(key), x]);
  const found = (line) => !find || [...line.cells.map((c) => c.words), ...line.row.centre.map((c) => c.text)]
    .some((w) => lower(w).includes(find));
  let shown = grid.lines.filter((line) => (filter === 'all' || (filter === 'differs' ? line.row.differs : line.row.missing))
    && found(line) && tests.every(([k, x]) => passes(line.cells[k], x))
    && (!f.reaches || Boolean(line.row.reach && line.row.reach.state === 'found')));
  const by = f.sort && at.has(f.sort.key) ? at.get(f.sort.key) : -1;
  if (by >= 0) {
    const sign = f.sort.dir === 'desc' ? -1 : 1;
    shown = [...shown].sort((x, y) => {
      const [a, b] = [x.cells[by], y.cells[by]];
      return a.blank || b.blank ? Number(a.blank) - Number(b.blank) : sign * compareCells(a, b);
    });
  }
  return { columns: grid.columns, lines: shown, all: grid.lines, filtering: filter !== 'all' || Boolean(find) || tests.length > 0 || Boolean(f.reaches) };
}

/** A cell on the clipboard - Copy's, and a node's keys' (owner 10-12): several «; », none empty, a side that did not
 *  reach the row «missing». */
export const copyWords = (cell) => (cell.missing ? MISSING : cell.values ? cell.values.join('; ') : cell.text === EMPTY ? '' : cell.text);

/** The rows a Wide table shows, in its order (the one seat above). */
export const rowsShown = (section, f = {}) => shownOf(section, f).lines.map((line) => line.row);

/**
 * A section as one flat sheet for Excel (owner 10-10, lead a27dfbb0f), as Wide draws it (lead 10-11 W: Copy the shape
 * shown): the node's own, then each column its groups' cells and Δ under it, the id last; a row each the table shows, in its
 * order (shownOf). Values as they are: several in one cell «; », none an empty cell, a side that did not reach the row «missing», Δ its
 * number.
 */
export function sheetOf(section, filter = {}) {
  const pair = section.groups.length === 2;
  // Two groups: + · Δ · − under a column that has Δ; otherwise each group's cell.
  const order = (list, delta) => (pair && delta !== undefined ? [list[0], delta, list[1]] : list);
  const head = [...section.centreHeads, ...section.columnHeads.flatMap((h, i) => {
    const signs = section.groups.map((g) => `${h} · ${g.sign}`);
    return order(signs, section.parts[i].delta ? `${h} · ${DELTA}` : undefined);
  }), 'id'];
  const rows = rowsShown(section, filter).map((row) => [...row.centre.map(copyWords), ...row.cells.flatMap((cell) => {
    const sides = cell.sides.map(copyWords);
    return order(sides, cell.delta ? (cell.delta.value === null || cell.delta.value === undefined ? '' : String(cell.delta.value)) : undefined);
  }), row.id]);
  return { head, rows };
}

/** Long's columns (lead 10-11 W): a value record a line. One basket: a value and its side. */
export const LONG_HEAD = Object.freeze(['node', 'value name', 'value', 'point', 'time', 'side', 'from']);
/** Two baskets: a value column a side, no Δ (owner 10-12 「좌우 값부터 제대로 띄워」) - the one seat that asks. */
const bySide = (groups) => groups.length > 1;
export const longHead = (groups) => (bySide(groups)
  ? ['node', 'value name', ...groups.map((g) => g.sign), 'point', 'time', 'from'] : [...LONG_HEAD]);
/** A Long line's words in its head's order. */
export const longRow = (l) => (l.sides ? [l.node, l.name, ...l.sides, l.point, l.time, l.from]
  : [l.node, l.name, l.words, l.point, l.time, l.side, l.from]);

/**
 * A section as Long draws it (lead 10-11 W): a line a value record - the node, the value's name, its value, the edge's
 * other attributes (point …), its time, the group it came by (none: the node's own), and who gave it with their way
 * (one meaning with Wide's source line). Wide's «+N» lists a cell's lines here: one read, two drawers.
 * @param {{index, groups, sources}} view   the walk's view
 * @param {object} section                  a section of it
 * @param {{row?: string, column?: string}} [only]  one row, one column (key) - what a table shows of the lines is shownOf's
 */
export function longLines(view, section, only = {}) {
  const rows = section.rows.filter((row) => !only.row || row.id === only.row);
  // One column asked: Long's, or a drawn one (a group's folded cell opened) - a drawer is any cell's.
  const drawn = section.columns.map((column, i) => ({ column, head: section.columnHeads[i], own: false }));
  const columns = !only.column ? section.long
    : [section.long.find((c) => columnKey(c.column) === only.column) || drawn.find((c) => columnKey(c.column) === only.column)].filter(Boolean);
  const lines = [];
  for (const row of rows) {
    for (const { column, head, own: mine } of columns) {
      const groups = mine ? [null] : view.groups.map((g, i) => ({ g, i }));
      for (const at of groups) {
        const inside = at ? at.g.inside : new Set([row.id]);
        for (const r of readsOf(view.index, inside, row.id, column, view.ways).reads.flatMap((read) => recordsOf(view.index, column, read))) {
          const point = pointWords(r.point);
          const t = r.when && Date.parse(r.when.occurred_at);
          lines.push({ id: row.id, node: row.label, name: head, value: r.value, words: valueWords(r.value), image: Boolean(r.image), point,
            time: Number.isFinite(t) ? localStamp(new Date(t).toISOString()) : '', side: at ? at.g.name : '',
            from: at && r.giver !== row.id ? view.sources.source(at.g, r.giver) : '', group: at ? at.i : null, column: columnKey(column),
            record: r.record });
        }
      }
    }
  }
  return lines;
}

/**
 * Long's lines (owner 10-12): two baskets, a record a line - its value under each side ITS way was walked inside (a side's
 * reads are longLines' per group), both when both; a node's own value under the sides that reached the node. A record is
 * its record (lead 10-12 C3: recordsOf's claim id) - not its edge, nor its value - however many ways reached it; one
 * basket: longLines as they are.
 */
export function longRecords(view, section, lines) {
  if (!bySide(section.groups)) return lines;
  const out = [];
  const seen = new Map();
  for (const l of lines) {
    const at = l.group !== null ? [l.group] : view.groups.flatMap((g, i) => (g.inside.has(l.id) ? [i] : []));
    const key = `${l.id}\u0000${l.column}`;
    const same = seen.get(key) || new Map();
    seen.set(key, same);
    const line = same.get(l.record) || { ...l, sides: view.groups.map(() => ''), froms: [] };
    if (!same.has(l.record)) { out.push(line); same.set(l.record, line); }
    for (const i of at) line.sides[i] = l.words;
    if (l.from && !line.froms.includes(l.from)) line.froms.push(l.from);
    line.from = line.froms.join('; ');
  }
  return out;
}

/** Long as a sheet: its head and a line a row, as drawn. */
export const longSheet = (section, lines) => ({ head: longHead(section.groups), rows: lines.map(longRow) });

const html = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
/** A sheet as the <table> Excel reads off the clipboard beside its TSV. */
export function sheetHtml(sheet) {
  const row = (cells, tag) => `<tr>${cells.map((c) => `<${tag}>${html(c)}</${tag}>`).join('')}</tr>`;
  return `<table><thead>${row(sheet.head, 'th')}</thead><tbody>${sheet.rows.map((r) => row(r, 'td')).join('')}</tbody></table>`;
}

/**
 * A formula cell in words (lead 5cf5c3401, a2eb4a516): missing, empty, its one value, or several - none overwritten; a
 * number column's cell stands right. Several say the first and how many more, every one kept (lead 34d91c09d 1: one
 * line of fifteen values pushed the node and the − side off the screen).
 */
export function cellWords(cell, kind = valueKind(cell.values || [])) {
  if (cell.missing) return { text: MISSING, missing: true };
  const values = cell.values.map(valueWords);
  if (!values.length) return { text: EMPTY };
  // The first value an image reference (reach_table's `images`): the value as it came, for the image cell to draw.
  const image = cell.images && cell.images[0] ? { image: cell.values[0] } : {};
  if (values.length === 1 && !cell.more) return { text: values[0], numeric: kind === 'number', ...image };
  // Cut (lead 10-13): how many ways it read of how many there are - «50 of 2,199».
  const count = (x) => Number(x).toLocaleString('en-US');
  return { text: values[0], rest: cell.more ? `${count(cell.read)} of ${count(cell.total)}` : `+${values.length - 1}`, values, ...image };
}

/** Which walk reached a row, a control walk B gone too (lead 99ed68cb7 D): A alone, both, or B alone. */
export const REACHED = Object.freeze({ a: 'A only', ab: 'A + B', b: 'B only' });
const reachedBy = (inA, inB) => (inA && inB ? 'ab' : inB ? 'b' : 'a');
const countReached = (kinds) => ({ a: kinds.filter((k) => k === 'a').length, ab: kinds.filter((k) => k === 'ab').length,
  b: kinds.filter((k) => k === 'b').length });

/** A walk and its control walk as one graph: each node and edge once, the walk's own first (lead 99ed68cb7 D); a walk's
 *  pages too (owner 10-12 «이어 걷기») - each ranked row once, so the signed table reads every page's rows. */
export function mergeWalks(a, b) {
  const once = (list) => [...new Map(list.map((x) => [x.id, x])).values()];
  const ranked = (w) => ((w && w.propagation) || {}).ranked || [];
  // A continued page's top set is a difference (implementer A d5df12352): top = (top - top_set_left) | top_set.
  const { top_set_left: left, ...own } = a.propagation || {};
  const top = (w) => ((w && w.propagation) || {}).top_set || [];
  const topSet = Array.isArray(left) ? { top_set: [...new Set([...top(b).filter((id) => !left.includes(id)), ...top(a)])] } : {};
  return { ...a, nodes: once([...(b.nodes || []), ...(a.nodes || [])]), edges: once([...(b.edges || []), ...(a.edges || [])]),
    ...(a.propagation || b.propagation
      ? { propagation: { ...(b.propagation || {}), ...own, ranked: once([...ranked(b), ...ranked(a)]), ...topSet } } : {}) };
}

/** The server's most for node_limit (ledger_subgraph.MAX_NODE_LIMIT, the route's `le`). */
export const SERVER_NODE_LIMIT = 1000;
/** The limits a walk's ask can raise, each its wire knob, where it stands in the answer and the server's most: nodes,
 *  depth (hops, up to the answer's max_hops) and fan-out (no most). Edges and claims are none: the screen sends no
 *  edge_limit and the route's default is its most, the claim scan read off it. */
const RAISES = [
  { axis: 'nodes', knob: 'node_limit', now: (r) => (r.limits || {}).nodes, most: () => SERVER_NODE_LIMIT },
  { axis: 'depth', knob: 'hops', now: (r) => (r.walk || {}).hops_requested, most: (r) => (r.limits || {}).max_hops },
  { axis: 'fan-out', knob: 'fanout_limit', now: (r, asked) => asked.fanout_limit, most: () => Infinity },
];
/** A cut answer's More (lead 10-12, the 18766 run: seeding from the deepest nodes hit the same cap): the same walk with
 *  each limit that cut it doubled up to the server's most - fan-out when a bundle drew fewer than it holds. Null when
 *  nothing cut it; no `asked` when every limit that cut it is at the server's most. `budgets` the Cut line's words. */
export function moreAsk(answer, asked = {}) {
  const cutBy = [...((answer && answer.truncatedAxes) || []),
    ...(((answer && answer.bundles) || []).some((b) => b.drawn < b.count) ? ['fan-out'] : [])];
  if (!cutBy.length) return null;
  const raised = {};
  for (const r of RAISES) {
    const now = Number(r.now(answer, asked));
    const most = Number(r.most(answer));
    if (cutBy.includes(r.axis) && Number.isFinite(now) && now < most) raised[r.knob] = Math.min(now * 2, most);
  }
  const budgets = cutBudgets(cutBy, { ...(answer.limits || {}), 'fan-out': asked.fanout_limit });
  return Object.keys(raised).length ? { asked: { ...asked, ...raised }, budgets } : { asked: null, budgets };
}

/** Δ in words: signed, ten significant digits (a float's tail is not a difference anyone measured). */
export function deltaWords(delta) {
  if (delta === null || delta === undefined) return '';
  const n = Number(delta.toPrecision(10));
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n)}`;
}

/**
 * 걷기 결과 하나 -> 표 «전부». 구획마다 머리·컬럼·행, 그리고 못 그린 수.
 *
 * @param {{nodes?: Array, edges?: Array}} result  walk 응답
 * @param {Array} entities                          선언의 엔티티 목록
 * @param {Array} [predicates]                      선언의 술어 목록 (확인 술어를 읽는 자리, C-98)
 * @param {number} [cap]                            행 상한
 * @param {{positive?: string[], negative?: string[]}} [starts]  the walk's signed starts: a side a sign it started from
 *        (lead 3375edd9b) - a node a row, a + group and, with a − start, a − group of columns; + only, one side (E1)
 * @param {Map} [added]                             the columns «+ Column» added, by type
 * @param {{off?: Map<string, Set<string>>, open?: Map<string, Set<string>>}} [fold]  by type, the columns and groups
 *        Columns turned off (a node's own column by columnKey, a group by groupKey) and the groups opened past their
 *        number cells (lead 10-11 W addendum 8)
 * @param {Array<{words: string, seeds: string[], answer: object}>} [adds]  walks merged into this step (lead 10-11 W
 *        addenda 5, 6: «Add here», «More»), in order: each start's side read off the groups, a node it brought on its
 *        starts' sides
 * @returns {{sections: Array, shown: number, hidden: number, groups: Array, unsplit: boolean}}
 */
export function walkTableView(result, entities, predicates = [], cap = ROW_CAP, starts = null, added = new Map(),
  fold = {}, control = null, adds = [], ways = WAYS_A_CELL) {
  // A control walk B (lead 99ed68cb7 D): the rows and values are both answers' graph; which walk reached a row, each its own.
  const walked = control ? mergeWalks(result, control) : result;
  // The walk's judgment for each node it walked (owner 10-12): the answer's «aux» names the auxiliary node(s) (seeds), each
  // node its own «aux» - found · hops · via / none / unknown.
  const reaches = (result && result.aux) || null;
  const reachTo = reaches ? (reaches.seeds || []) : [];
  const reachHead = `${REACH_WORDS.head} ${reachTo.map(nodeWords).join(' · ')}`;
  // Drawn an auxiliary node a line (lead 10-12: two read «→ pressure_MPa · SY…», cut).
  const reachLines = reachTo.length > 1 ? reachTo.map((id) => `${REACH_WORDS.head} ${nodeWords(id)}`) : [reachHead];
  const judgedById = new Map(((result && result.nodes) || []).map((n) => [n.id, n.aux || null]));
  const judgedOf = (id) => judgedById.get(id) || null;
  // Each addition merged by the same merge; the step's rows keep their order, what an addition brought after them.
  const merged = adds.reduce((graph, add) => mergeWalks(graph, add.answer), walked);
  const before = new Map(((walked && walked.nodes) || []).map((n, i) => [n.id, i]));
  const brought = new Map();
  adds.forEach((add, k) => ((add.answer && add.answer.nodes) || []).forEach((n) => {
    if (!before.has(n.id) && !brought.has(n.id)) brought.set(n.id, k);
  }));
  const nodes = [...((merged && merged.nodes) || [])].sort((a, b) => (before.has(a.id) ? before.get(a.id) : Infinity)
    - (before.has(b.id) ? before.get(b.id) : Infinity) || 0);
  // C-89. 「어느 이름이 여럿인가」는 봉투가 말합니다. 노드마다 다시 묻지 않습니다 — 한 답이고,
  // 표 중간에서 답이 바뀔 수 있으면 그 자체가 결함입니다.
  const plural = pluralAttributes(merged);
  // C-98. 「무엇이 안 보이는 것이 무슨 뜻인가」의 모집단은 «선언»이라, 한 번 읽고 모든 구획이
  // 같은 열을 씁니다 — 구획마다 다시 물으면 표 중간에서 열이 바뀔 수 있습니다.
  const confirmers = confirmedPredicates(predicates);
  // A value-bearing edge's far node of a type the declaration calls static - a name - stands its own group (lead 10-11 W
  // addendum 8 (다)): the one seat that asks.
  const statics = staticTypes(entities);
  // The flat table's two node-own columns, carried into the centre (lead 10-11): «Conflicts» and a confirmation
  // predicate's - the declaration says they stand, its own functions read them.
  const carriedOf = (type) => tableColumns(entities, type, [], undefined, confirmers)
    .filter((c) => c.kind === 'conflicts' || c.kind === 'absence');
  const positive = (starts && starts.positive) || [];
  const negative = (starts && starts.negative) || [];
  // A group a sign the walk started from (lead 5cf5c3401): its starts and the nodes it reached. One sign reached all the
  // walk brought; two are told apart by the answer's reach - one that ranks nothing is one side holding every node,
  // said to be both signs.
  const signs = [{ name: '+', starts: positive }, ...(negative.length ? [{ name: '−', starts: negative }] : [])];
  const one = (answer) => [{ name: '+', starts: [...positive, ...negative],
    inside: new Set([...positive, ...negative, ...((answer && answer.nodes) || []).map((n) => n.id)]) }];
  const ranked = signs.length > 1 ? groupsOf(result, signs) : null;
  const groupsA = ranked || one(result);
  // A control walk B (lead 99ed68cb7 D), its sides read as A's are: a side reached a row by A, by B or both - its inside
  // is either, a and b say which.
  const groupsB = control ? (ranked ? groupsOf(control, signs) || ranked.map((g) => ({ ...g, inside: new Set(g.starts) })) : one(control)) : null;
  const groups = groupsB ? groupsA.map((g, i) => ({ ...g, inside: new Set([...g.inside, ...groupsB[i].inside]),
    a: g.inside, b: groupsB[i].inside })) : groupsA;
  // An addition's node joins the sides its starts stand on (lead 10-11 W addendum 6): a start + only its + cell, − only
  // its − cell, both both - the starts read off the paths the addition walked to it, none said: all its starts.
  const addSources = adds.map((add) => valueSources(add.answer, entities, groups));
  const addPaths = adds.map((add) => walkedPaths(add.answer));
  const seedsTo = (k, id) => {
    const from = adds[k].seeds.includes(id) ? [id] : [...new Set((addPaths[k].get(id) || []).map((p) => p.seed))];
    return from.length ? from : adds[k].seeds;
  };
  adds.forEach((add, k) => ((add.answer && add.answer.nodes) || []).forEach((n) => {
    for (const g of groups) if (seedsTo(k, n.id).some((s) => g.inside.has(s))) g.inside.add(n.id);
  }));
  // A far end the answer did not send (collect) is still a node of its type and keys - read off its id, as its source
  // words are (lead 10-11): a column group needs its type and name. It is no row: rows are the answer's nodes.
  const sent = new Set(nodes.map((n) => n.id));
  const unsent = [...new Set(((merged && merged.edges) || []).flatMap((e) => [e.source, e.target]))].filter((id) => !sent.has(id))
    .map((id) => ({ id, ...(entityOfId(id) || {}) })).filter((n) => n.type)
    .map((n) => ({ ...n, label: Object.values(n.keys || {}).map(valueWords).join(' / ') || n.id }));
  const index = indexGraph({ ...merged, nodes: [...nodes, ...unsent] });
  const own = valueSources(result, entities, groups);
  const sourcesB = control ? valueSources(control, entities, groups) : null;
  // A node an addition brought: its way from that addition's starts on the side, a start both sides hold said by name.
  const addRoute = (g, id) => {
    const k = brought.get(id);
    const starts = adds[k].seeds.filter((s) => g.inside.has(s));
    const way = addSources[k].route({ starts }, id);
    const shared = groups.length > 1 ? starts.filter((s) => seedsTo(k, id).includes(s) && groups.every((h) => h.inside.has(s))) : [];
    return shared.length ? { ...way, text: `${way.text} · via shared ${shared.map(addSources[k].keys).join(', ')}` } : way;
  };
  // B reached the node on this side: Route says B's path a line more; a value only B brought says B's source.
  const byB = (g, id) => Boolean(g && g.b && g.b.has(id));
  const sources = { route: own.route, keys: own.keys, source: (g, id) => (g && brought.has(id) ? `${addSources[brought.get(id)].keys(id)} · ${addRoute(g, id).text}`
    : byB(g, id) && !g.a.has(id) ? `B · ${sourcesB.source(g, id)}` : own.source(g, id)) };
  // The node's way, one line: with a control walk each walk that reached it says its own, named - A's, then B's; the same
  // way by both once (lead 10-11 W 1 regression: a B-only row said «—»).
  const routeCell = (g, id) => {
    if (brought.has(id)) return addRoute(g, id);
    if (!g.b) return own.route(g, id);
    const one = (w) => `${w.text}${w.rest ? ` ${w.rest}` : ''}`;
    const ways = [[g.a, 'A', own], [g.b, 'B', sourcesB]].filter(([by]) => by.has(id)).map(([, word, from]) => ({ word, ...from.route(g, id) }));
    const same = ways.length === 2 && one(ways[0]) === one(ways[1]);
    return { text: same ? `A + B ${one(ways[0])}` : ways.map((w) => `${w.word} ${one(w)}`).join(' · '),
      values: ways.flatMap((w) => (w.values || [w.text]).map((v) => `${w.word} ${v}`)) };
  };
  // A node a row: one row whichever groups reached it.
  const members = nodes.filter((n) => groups.some((g) => g.inside.has(n.id)));
  // The cap is a section's own (lead 10-12, 18766: one cap over the answer's order drew no defect section of 188 and 20
  // of 32 quantities): each type draws up to `cap` of its rows, in its order, and says what it did not.
  const sections = [];
  let shown = 0;
  let waysCut = false;
  for (const [type, typed] of sectionsByType(members)) {
    const rows = typed.slice(0, cap);
    shown += rows.length;
    const ids = rows.map((n) => n.id);
    const entity = (entities || []).find((e) => e && e.type === type) || {};
    const off = (fold.off && fold.off.get(type)) || new Set();
    const open = (fold.open && fold.open.get(type)) || new Set();
    const all = [...defaultColumns(index, ids, entity.keys || [], (t) => statics.has(t)), ...(added.get(type) || [])];
    // The node's own (no step) in the node's columns; the groups' columns are the steps'.
    const ownAll = all.filter((c) => !c.steps.length);
    const ownCells = rows.map((node) => ownAll.map((c) => cellOf(index, new Set([node.id]), node.id, c)));
    const sideAll = all.filter((c) => c.steps.length);
    const tableAll = tableOf(index, groups, ids, sideAll, ways);
    if (tableAll.some((row) => row.cells.some((byGroup) => byGroup.some((c) => c.more)))) waysCut = true;
    // Each column judged once by its values' JSON type (lead a2eb4a516); a mixed one says so in its head.
    const kindsAll = sideAll.map((_, c) => valueKind(tableAll.flatMap((row) => row.cells[c].flatMap((cell) => cell.values))));
    const headOf = (c) => `${sideAll[c].words.join(' · ')}${kindsAll[c] === 'mixed' ? ' (mixed)' : ''}`;
    // A column no row has a value in is in no list (lead 10-11 W). A key says who the row is and is never off.
    const ownValued = ownAll.map((_, c) => ownCells.some((cells) => cells[c].values.length));
    const ownAt = ownAll.map((_, c) => c).filter((c) => ownValued[c] && (ownAll[c].value.on === 'key' || !off.has(columnKey(ownAll[c]))));
    // A value-bearing edge's columns a group per far node (lead 10-11 W addendum 8, owner ㄷ): its number cells open - none,
    // its first - the rest folded under its head until opened; Columns turns a group on and off.
    const bundles = new Map();
    sideAll.forEach((c, i) => {
      if (kindsAll[i] === 'empty') return;
      const key = groupKey(c);
      if (!bundles.has(key)) bundles.set(key, { key, step: c.words.slice(0, -1).join(' · '), at: [] });
      bundles.get(key).at.push(i);
    });
    const folds = [...bundles.values()].map((b) => {
      const numbers = b.at.filter((i) => kindsAll[i] === 'number');
      const first = numbers.length ? numbers : b.at.slice(0, 1);
      const opened = open.has(b.key);
      return { ...b, first, shown: opened ? [...first, ...b.at.filter((i) => !first.includes(i))] : first,
        folded: b.at.length - first.length, open: opened, on: !off.has(b.key) };
    });
    // The groups that set the sides against each other - a Δ under a cell they show - nearest the node, the rest after,
    // each in its order (34d91c09d 2's numbers nearest the node, carried to W's groups: the first Δ in the first screen).
    const hasDelta = (c) => groups.length === 2 && tableAll.some((row) => row.deltas[c] !== null);
    const compared = (b) => b.shown.some(hasDelta);
    const sideAt = [...folds.filter((b) => b.on && compared(b)), ...folds.filter((b) => b.on && !compared(b))].flatMap((b) => b.shown);
    const centre = ownAt.map((c) => ownAll[c]);
    const carried = carriedOf(type);
    const columns = sideAt.map((c) => sideAll[c]);
    const kinds = sideAt.map((c) => kindsAll[c]);
    const table = tableAll.map((row) => ({ ...row, cells: sideAt.map((c) => row.cells[c]), deltas: sideAt.map((c) => row.deltas[c]) }));
    const columnHeads = sideAt.map(headOf);
    // The columns a trend reads (lead 10-11 E2c, G-2): a value something says - an edge's or a node's own, never a key or
    // a name - read with a time in this section, as the trend reads it (a button that draws nothing is wrong); the
    // steps' (folded ones too: they stand in place) then the node's own, numbers first - a numeral in text one too - so
    // the first is the one it opens on.
    const valued = [...folds.filter((b) => b.on).flatMap((b) => b.at).map((c) => ({ column: sideAll[c], head: headOf(c) })),
      ...centre.map((column) => ({ column, head: column.words.join(' · ') }))].filter(({ column }) => saysValue(column))
      .map((x) => {
        const timed = ids.flatMap((id) => walkPoints(index, groups, id, x.column, ways)).filter((p) => p.t !== null);
        return { ...x, timed: timed.length > 0, number: timed.length > 0 && timed.every((p) => numberOf(p.value) !== null) };
      }).filter((x) => x.timed);
    const trendable = [...valued.filter((x) => x.number), ...valued.filter((x) => !x.number)].map(({ column, head }) => ({ column, head }));
    // Δ under a column of two groups (lead 10-11 W: «+ · Δ · −», the mockup B-ㄱ) - a number where both cells are one
    // number each, «—» where not; the copy leaves it empty. A column no row has a Δ for draws none (lead 10-12: 48 Δ
    // columns of «—» alone); one row's Δ and it is drawn.
    const deltaAt = new Set(sideAt.flatMap((c, k) => (hasDelta(c) ? [k] : [])));
    const said = rows.map((node, r) => {
      const row = table[r];
      // A value the row gave itself says no source line - its node's cell says how the row was reached; one from another
      // node says that node and its way from the side's starts (lead 10-11 W 11: one meaning).
      const cells = columns.map((_, c) => ({
        sides: groups.map((g, i) => (g.inside.has(node.id)
          ? { ...cellWords(row.cells[c][i], kinds[c]), col: c,
            sources: (row.cells[c][i].nodes || []).map((id) => (id === node.id ? '' : sources.source(g, id))) }
          : { text: MISSING, missing: true, col: c })),
        delta: deltaAt.has(c) ? { text: deltaWords(row.deltas[c]) || EMPTY, numeric: true, value: row.deltas[c] } : null,
      }));
      const reached = groups[0].b ? groups.map((g) => (g.inside.has(node.id) ? reachedBy(g.a.has(node.id), g.b.has(node.id)) : null)) : null;
      return { id: node.id, label: node.label || node.id, differs: row.differs, missing: row.missing, reached, cells,
        reach: reaches ? judgedOf(node.id) : null,
        // How each side reached the row (lead 10-11 W: the Route column retired - the way is the node's source line).
        routes: groups.filter((g) => g.inside.has(node.id)).map((g) => ({ sign: g.name, ...routeCell(g, node.id) })),
        // A type with no own column says the node's name there.
        centre: [...(ownAt.length ? ownAt.map((c) => cellWords(ownCells[r][c], 'string')) : [{ text: node.label || node.id }]),
          ...carried.map((c) => cellWords({ values: [cellSource(c, node, {}, plural.get(node.type))].filter((v) => v !== undefined) }, 'string')),
          ...(reaches ? [{ text: reachWords(judgedOf(node.id), reachTo.length > 1) }] : [])] };
    });
    const groupOf = new Map(folds.map((b) => [b.key, b]));
    const ownHeads = [...(centre.length ? centre.map((c) => c.words.join(' · ')) : [type]), ...carried.map((c) => c.name)];
    sections.push({
      type,
      heading: sectionHeading(type, rows.length),
      groups: groups.map((g) => ({ sign: g.name, starts: g.starts.length, count: rows.filter((n) => g.inside.has(n.id)).length })),
      reached: groups[0].b ? groups.map((g, i) => countReached(said.map((row) => row.reached[i]).filter(Boolean))) : null,
      // The additions that reached this type, each the rows it brought (lead 10-11 W addendum 5: «+N from walk on»).
      adds: adds.map((add, at) => ({ at, words: add.words, n: rows.filter((node) => brought.get(node.id) === at).length }))
        .filter(({ at }) => ((adds[at].answer && adds[at].answer.nodes) || []).some((n) => n.type === type && !adds[at].seeds.includes(n.id))),
      // A value column's own head, by the index its cells carry (`col`).
      columnHeads,
      // The heads in rows (lead 34d91c09d (나), W): a column's group - its step and far end - once over its columns with
      // what it folds, the value's name under, each group's sign and Δ under that.
      parts: columns.map((c, i) => {
        const b = groupOf.get(groupKey(c));
        return { step: b.step, leaf: `${c.words[c.words.length - 1]}${kinds[i] === 'mixed' ? ' (mixed)' : ''}`, delta: deltaAt.has(i),
          group: b.key, folded: b.folded, open: b.open };
      }),
      centreHeads: [...ownHeads, ...(reaches ? [reachHead] : [])],
      // Each head's drawn lines: its words, the judgment's an auxiliary node a line.
      centreLines: [...ownHeads.map((h) => [h]), ...(reaches ? [reachLines] : [])],
      // A judged walk (owner 10-12): its section offers «Reaches only» and tallies every row's judgment, not the shown ones.
      judged: Boolean(reaches),
      tally: reaches ? reachTally(reachHead, said) : '',
      centre,
      rows: said,
      columns,
      // What Columns lists (lead 10-11 W, addendum 8): the node's own a column each, the steps' a group each - and which
      // are drawn.
      listed: [...ownAll.filter((c, i) => ownValued[i] && c.value.on !== 'key').map((column) => ({ key: columnKey(column), head: column.words.join(' · '),
        on: !off.has(columnKey(column)) })), ...folds.map((b) => ({ key: b.key, head: b.step, on: b.on }))],
      // What Long reads (lead 10-11 W, addendum 8: «Long 은 그대로 다»): a line a record - the node's own a value each; a
      // group's its open cell, the edge's other attributes its point (the mockup B-ㄱ's Long).
      long: [...ownAll.filter((c, i) => ownValued[i] && saysValue(c)).map((column) => ({ column, head: column.words.join(' · '), own: true })),
        ...folds.flatMap((b) => b.first.map((c) => ({ column: sideAll[c], head: b.first.length === 1 ? b.step : headOf(c), own: false })))],
      trendable,
      hidden: typed.length - rows.length,
    });
  }
  return { sections, shown, hidden: members.length - shown, groups,
    unsplit: !ranked && negative.length > 0, index, sources, ways, waysCut };
}

// ⚰️ reachBySign retired 10-10 (lead 5cf5c3401): the reach is read in one seat, reach_table.groupsOf - a group a start
//    sign, k of them, not a pair named here.
