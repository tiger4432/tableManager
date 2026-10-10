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
import { confirmedPredicates, sectionsByType, sectionHeading, tableColumns, cellSource, pluralAttributes } from './derive.js';
import { typeGraph, entityOfId } from '../rnd_board/api.js';
// The table is the formula (lead 5cf5c3401; one side for a + only walk, E1): rows, groups and columns in, cells out.
import { indexGraph, groupsOf, defaultColumns, tableOf, cellOf, valueKind, valueWords } from './reach_table.js';
import { isBlank } from '../absent.js';

/** The edges one step from a type (lead 53050a4ec): each declared predicate touching it and the type at its other
 *  end, read off the type graph the route list reads - a predicate within the type (bonded_to die -> die) included,
 *  which the route list keeps as a loop chip. The walk takes any first step. Nothing is guessed from the data. */
export function nextRoutes(declaration, type) {
  const out = [];
  for (const edge of typeGraph(declaration).edges) {
    const to = edge.from === type ? edge.to : edge.to === type ? edge.from : null;
    if (to !== null && !out.some((r) => r.predicate === edge.predicate && r.to === to)) {
      out.push({ predicate: edge.predicate, to });
    }
  }
  return out;
}

/** 한 번에 그리는 행 상한. 넘은 것은 «수»로 말합니다 — 조용히 자르지 않습니다. */
export const ROW_CAP = 200;

// ⚰️ valueText · isNumericText · qualifiersByNode · qualifierNamesOf retired 10-11 with the flat table's seat (E1): its
//    cells were text from `cellSource` on the edge qualifiers folded into the node they reached; the walk table reads a
//    column's way (reach_table.cellOf), every edge's value kept, the edge's own predicate in the head.

/** A group's cell for a node it did not reach; a reached cell with no value; a start's route; the Δ head; the Route head. */
export const MISSING = 'missing';
export const EMPTY = '—';
export const STARTED = 'start';
export const DELTA = 'Δ';
export const ROUTE = 'Route';
/** Where a route stands, for a node no side of the walk reached - a time page's other rows (lead 10-11). */
export const NOT_WALKED = 'not in this walk';

/** A path the server walked (an answer's evidence) in words: its hops' predicates in order, predicates only (owner 10-10
 *  «라우트는 술어만»). A hop reached by two predicates says both. */
export const routeWords = (path) => path.hops.slice(1).map((hop) => (hop.predicates || []).join(' / ')).join(' → ');

/**
 * How a side reached a node and who gave a value, read off one walk's answer (leads df11f9e81 B, 99ed68cb7 C):
 *   route(g, id)   the paths the server walked to `id` from side g's starts - its evidence - a start «start»
 *   source(g, id)  the node a read ends at: its keys in their declared order (its label without), and route(g, id) - a
 *                  node the answer did not send (collect) read off its id, never the id itself (lead 10-11); no side
 *                  (g null, a time page's other row): «not in this walk» where the route would be
 * The table's cells and the trend's points read both here.
 */
export function valueSources(result, entities, groups) {
  const walked = new Map((((result && result.propagation) || {}).ranked || []).map((row) => [row.id, row.evidence || []]));
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

/** The rows a filter shows (lead 5cf5c3401): all, those whose sides differ, those a side did not reach. */
export function rowsShown(section, filter = 'all') {
  return section.rows.filter((row) => filter === 'all' || (filter === 'differs' ? row.differs : row.missing));
}

/**
 * A section as one flat sheet for Excel (owner 10-10, lead a27dfbb0f): one head row - each side's columns under its
 * sign, the node's own, Δ, the id last; a row each the filter shows. Values as they are: several in one cell «; »,
 * none an empty cell, a side that did not reach the row «missing» in each of its columns, Δ its number.
 */
export function sheetOf(section, filter = 'all') {
  const pair = section.groups.length === 2;
  const side = (i) => section.heads.map((h) => `${section.groups[i].sign} ${h}`);
  const head = pair ? [...side(0), ...section.centreHeads, ...side(1), ...section.deltaHeads, 'id']
    : [...section.centreHeads, ...section.groups.flatMap((_, i) => side(i)), ...section.deltaHeads, 'id'];
  const words = (cell) => (cell.missing ? MISSING : cell.values ? cell.values.join('; ') : cell.text === EMPTY ? '' : cell.text);
  const cells = (row, i) => row.byGroup[i].flatMap((cell) => Array(cell.span || 1).fill(words(cell)));
  const rows = rowsShown(section, filter).map((row) => {
    const own = row.centre.map(words);
    const deltas = row.deltas.map((d) => (d.value === null || d.value === undefined ? '' : String(d.value)));
    return pair ? [...cells(row, 0), ...own, ...cells(row, 1), ...deltas, row.id]
      : [...own, ...section.groups.flatMap((_, i) => cells(row, i)), ...deltas, row.id];
  });
  return { head, rows };
}

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
  if (values.length === 1 && !cell.more) return { text: values[0], numeric: kind === 'number' };
  return { text: values[0], rest: `+${values.length - 1}${cell.more ? '+' : ''}`, values };
}

/** Which walk reached a row, a control walk B gone too (lead 99ed68cb7 D): A alone, both, or B alone. */
export const REACHED = Object.freeze({ a: 'A only', ab: 'A + B', b: 'B only' });
const reachedBy = (inA, inB) => (inA && inB ? 'ab' : inB ? 'b' : 'a');
const countReached = (kinds) => ({ a: kinds.filter((k) => k === 'a').length, ab: kinds.filter((k) => k === 'ab').length,
  b: kinds.filter((k) => k === 'b').length });

/** A walk and its control walk as one graph: each node and edge once, the walk's own first (lead 99ed68cb7 D). */
export function mergeWalks(a, b) {
  const once = (key) => [...new Map([...(b[key] || []), ...(a[key] || [])].map((x) => [x.id, x])).values()];
  return { ...a, nodes: once('nodes'), edges: once('edges') };
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
 * @returns {{sections: Array, shown: number, hidden: number, groups: Array, unsplit: boolean}}
 */
export function walkTableView(result, entities, predicates = [], cap = ROW_CAP, starts = null, added = new Map(),
  opened = new Set(), control = null) {
  // A control walk B (lead 99ed68cb7 D): the rows and values are both answers' graph; which walk reached a row, each its own.
  const walked = control ? mergeWalks(result, control) : result;
  const nodes = (walked && walked.nodes) || [];
  // C-89. 「어느 이름이 여럿인가」는 봉투가 말합니다. 노드마다 다시 묻지 않습니다 — 한 답이고,
  // 표 중간에서 답이 바뀔 수 있으면 그 자체가 결함입니다.
  const plural = pluralAttributes(walked);
  // C-98. 「무엇이 안 보이는 것이 무슨 뜻인가」의 모집단은 «선언»이라, 한 번 읽고 모든 구획이
  // 같은 열을 씁니다 — 구획마다 다시 물으면 표 중간에서 열이 바뀔 수 있습니다.
  const confirmers = confirmedPredicates(predicates);
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
  const index = indexGraph(walked);
  const own = valueSources(result, entities, groups);
  const sourcesB = control ? valueSources(control, entities, groups) : null;
  // B reached the node on this side: Route says B's path a line more; a value only B brought says B's source.
  const byB = (g, id) => Boolean(g && g.b && g.b.has(id));
  const sources = { route: own.route, keys: own.keys, source: (g, id) => (byB(g, id) && !g.a.has(id) ? `B · ${sourcesB.source(g, id)}` : own.source(g, id)) };
  const routeCell = (g, id) => (byB(g, id) ? { ...own.route(g, id), sources: [`B · ${sourcesB.route(g, id).text}`] } : own.route(g, id));
  // A node a row: one row whichever groups reached it.
  const members = nodes.filter((n) => groups.some((g) => g.inside.has(n.id)));
  const shown = members.slice(0, cap);
  const sections = [];
  for (const [type, rows] of sectionsByType(shown)) {
    const ids = rows.map((n) => n.id);
    const entity = (entities || []).find((e) => e && e.type === type) || {};
    const all = [...defaultColumns(index, ids, entity.keys || []), ...(added.get(type) || [])];
    // The node's own (no step) once in the centre; the groups' columns are the steps'.
    const ownAll = all.filter((c) => !c.steps.length);
    const ownCells = rows.map((node) => ownAll.map((c) => cellOf(index, new Set([node.id]), node.id, c)));
    const sideAll = all.filter((c) => c.steps.length);
    const tableAll = tableOf(index, groups, ids, sideAll);
    // Each column judged once by its values' JSON type (lead a2eb4a516); a mixed one says so in its head.
    const kindsAll = sideAll.map((_, c) => valueKind(tableAll.flatMap((row) => row.cells[c].flatMap((cell) => cell.values))));
    // A column no row has a value in folds unless its type is opened (lead 34d91c09d 7); the numbers stand nearest the
    // node, the rest outward, each in its order (34d91c09d 2: the value to set side by side was the fourth from the node).
    const keep = opened.has(type);
    const ownEmpty = ownAll.map((_, c) => !ownCells.some((cells) => cells[c].values.length));
    const sideEmpty = kindsAll.map((kind) => kind === 'empty');
    const ownAt = ownAll.map((_, c) => c).filter((c) => keep || !ownEmpty[c]);
    const sideAt = sideAll.map((_, c) => c).filter((c) => keep || !sideEmpty[c])
      .sort((p, q) => (kindsAll[q] === 'number') - (kindsAll[p] === 'number'));
    const empty = [...ownEmpty, ...sideEmpty].filter(Boolean).length;
    const centre = ownAt.map((c) => ownAll[c]);
    const carried = carriedOf(type);
    const columns = sideAt.map((c) => sideAll[c]);
    const kinds = sideAt.map((c) => kindsAll[c]);
    const table = tableAll.map((row) => ({ ...row, cells: sideAt.map((c) => row.cells[c]), deltas: sideAt.map((c) => row.deltas[c]) }));
    // Route at each side's outer end (the mockup the owner approved; the numbers stay nearest the node): how that side
    // reached the row (lead df11f9e81).
    const columnHeads = columns.map((c, i) => `${c.words.join(' · ')}${kinds[i] === 'mixed' ? ' (mixed)' : ''}`);
    const heads = [...columnHeads, ROUTE];
    const deltas = groups.length === 2 ? columns.map((_, c) => c).filter((c) => table.some((row) => row.deltas[c] !== null)) : [];
    const said = rows.map((node, r) => {
      const row = table[r];
      const byGroup = groups.map((g, i) => {
        // A side that did not reach the node says so once, across its columns (lead 34d91c09d 3).
        if (!g.inside.has(node.id)) return [{ text: MISSING, missing: true, span: heads.length }];
        return [...row.cells.map((byCol, c) => ({ ...cellWords(byCol[i], kinds[c]), col: c,
          sources: (byCol[i].nodes || []).map((id) => sources.source(g, id)) })), routeCell(g, node.id)];
      });
      const reached = groups[0].b ? groups.map((g) => (g.inside.has(node.id) ? reachedBy(g.a.has(node.id), g.b.has(node.id)) : null)) : null;
      return { id: node.id, label: node.label || node.id, differs: row.differs, missing: row.missing, byGroup, reached,
        // A type with no own column says the node's name there.
        centre: [...(ownAt.length ? ownAt.map((c) => cellWords(ownCells[r][c], 'string')) : [{ text: node.label || node.id }]),
          ...carried.map((c) => cellWords({ values: [cellSource(c, node, {}, plural.get(node.type))].filter((v) => v !== undefined) }, 'string'))],
        deltas: deltas.map((c) => ({ text: deltaWords(row.deltas[c]), numeric: true, value: row.deltas[c] })) };
    });
    sections.push({
      type,
      heading: sectionHeading(type, rows.length),
      groups: groups.map((g) => ({ sign: g.name, starts: g.starts.length, count: rows.filter((n) => g.inside.has(n.id)).length })),
      reached: groups[0].b ? groups.map((g, i) => countReached(said.map((row) => row.reached[i]).filter(Boolean))) : null,
      heads,
      // A value column's own head, by the index its cells carry (`col`): heads is Route and these.
      columnHeads,
      // The heads in two rows (lead 34d91c09d, its answer (나)): a column's step, said once over the columns that share it,
      // and below it the value's name - the step repeated in every head pushed Δ 608 px off at 1568.
      parts: [...columns.map((c, i) => ({ step: c.words.slice(0, -1).join(' · '), leaf: `${c.words[c.words.length - 1]}${kinds[i] === 'mixed' ? ' (mixed)' : ''}` })),
        { step: '', leaf: ROUTE }],
      centreHeads: [...(centre.length ? centre.map((c) => c.words.join(' · ')) : [type]), ...carried.map((c) => c.name)],
      deltaHeads: deltas.map((c) => (deltas.length > 1 ? `${DELTA} ${columnHeads[c]}` : DELTA)),
      rows: said,
      columns,
      empty: { count: empty, open: keep },
    });
  }
  return { sections, shown: shown.length, hidden: Math.max(0, members.length - shown.length), groups,
    unsplit: !ranked && negative.length > 0, index, sources };
}

// ⚰️ reachBySign retired 10-10 (lead 5cf5c3401): the reach is read in one seat, reach_table.groupsOf - a group a start
//    sign, k of them, not a pair named here.
