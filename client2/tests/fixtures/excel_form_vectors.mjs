// ═══════════════════════════════════════════════════════════════════════════════
// CONTRACT VECTORS for the operator Excel form (map2/excel_io.js).
//
// 🔴 THE VECTORS ARE THE DELIVERABLE THAT OUTLIVES THE CODE. Each one is an INPUT
//    ARTIFACT, the DECLARATION plus CELLS it must read to, and the ARTIFACT it must write
//    back out. Both directions are scored against the same record, so neither half can
//    drift without the other noticing.
//
// WHERE THE FORMAT COMES FROM. Not from the legacy editor's implementation. From the
// production ingestion code that already reads this form
// (`dev_env/ingestion_workspace/bonding_map/scripts/bonding_map_parser.py` ->
// `server/parsers/html_topology_parser.py :: HTMLMatrixTableParser`) and from the
// expectations frozen in `client2/tests/coord_table_paste_harness.mjs`.
//
// ⚠️ WHAT IS NOT VERIFIED HERE. `dev_env/ingestion_workspace/bonding_map/archives/` and
//    `raws/` are EMPTY on this development box and there is no `.xls`/`.xlsx`/`.html`
//    sample anywhere under `dev_env`. Every artifact below is CONSTRUCTED from the
//    parser's rules; none of them is a real operator file. That limit is stated in the
//    round's report and must not be papered over by the fact that these all pass.
//
// ── THE DEFECT AXES ARE DELIBERATELY LIVE ───────────────────────────────────────
// A fixture that cannot express a defect scores nothing, so across the vectors:
//   nx != ny            a transposed read cannot pass a width check by accident
//   minX != 0, negative x, minY != 0   a dropped origin term cannot hide behind zero
//   y ascending AND descending         a direction assumption shows up
//   integer values INSIDE the grid     a lexical "is this a header" test misfires
//   a numeric header VALUE (`07`)      the same test misfires in the other direction
//   blanks at the extremes             an edge-dropping read cannot hide in empty columns
//   merged AND unmerged cells present  the one measured shape fact is exercised both ways
// ═══════════════════════════════════════════════════════════════════════════════

const A = (...rows) => rows.join('');
const tr = (...cells) => '<tr>' + cells.join('') + '</tr>';
const td = (v) => `<td>${v}</td>`;
const tdc = (n, v) => `<td colspan="${n}">${v}</td>`;

// ── V1: the full rich form ──────────────────────────────────────────────────────
const V1_X = [-3, -2, -1, 0, 1, 2, 3];
const V1_Y = [10, 11, 12, 13, 14];
const V1_GRID = [
  ['', '1', '1', '1', '1', '', ''],
  ['1', 'F', '1', '1', '1', '1', ''],
  ['1', '1', '2', 'BIN', '1', '1', '1'],
  ['1', '1', '1', '1', 'F', '1', ''],
  ['', '1', '1', '1', '', '', ''],
];
const V1_HTML = A(
  '<table>',
  tr(tdc(8, 'bonding_map · 4B12')),
  tr(tdc(2, 'BDIE'), tdc(2, 'LOT'), tdc(4, 'AF12312')),
  tr(tdc(2, 'BDIE'), tdc(2, 'WF'), tdc(4, '07')),
  tr(tdc(2, 'DATE'), tdc(2, 'YM'), tdc(4, '202608')),
  tr(td(''), ...V1_X.map(x => td(String(x)))),
  ...V1_Y.map((y, i) => tr(td(String(y)), ...V1_GRID[i].map(v => td(v)))),
  '</table>');

// ── V2: rich, no TITLE band ─────────────────────────────────────────────────────
// The form does not have to state its identity. When it does not, the reader must say
// `absent` and show `미상` -- never an empty string, and never an invented placeholder.
const V2_X = [7, 8, 9, 10, 11];
const V2_Y = [-2, -1, 0, 1, 2, 3];
const V2_GRID = [
  ['', '', '1', '', ''],
  ['', '1', '1', '1', ''],
  ['1', '1', 'F', '1', '1'],
  ['1', '1', '1', '1', '1'],
  ['', '1', '4', '1', ''],
  ['', '', '1', '', ''],
];
const V2_HTML = A(
  '<table>',
  tr(tdc(2, 'LOT'), tdc(2, 'NO'), tdc(2, 'A9')),
  tr(td(''), ...V2_X.map(x => td(String(x)))),
  ...V2_Y.map((y, i) => tr(td(String(y)), ...V2_GRID[i].map(v => td(v)))),
  '</table>');

// ── V3: the plain surface ───────────────────────────────────────────────────────
// Descending Y, which is the direction a wafer map arrives in as often as not.
const V3_X = [1, 2, 3, 4, 5, 6];
const V3_Y = [20, 19, 18, 17];
const V3_GRID = [
  ['', '1', '1', '1', '1', ''],
  ['1', '1', 'F', '1', '1', '1'],
  ['1', '1', '1', '5', '1', '1'],
  ['', '1', '1', '1', '', ''],
];
const V3_TEXT = [['', ...V3_X.map(String)]]
  .concat(V3_Y.map((y, i) => [String(y), ...V3_GRID[i]]))
  .map(r => r.join('\t')).join('\n');

// ── V4: an imperfect form -- both rejection codes, live ─────────────────────────
// A value sitting in a column the X axis never declared (`not_declared`), and a row that
// runs out before the axis does (`mapping_unavailable`). Neither is fatal and neither is
// silent: the whole point of the intake report is that the operator is told a count and a
// reason instead of losing cells without a trace.
const V4_HTML = A(
  '<table>',
  tr(td(''), td('1'), td('2'), td('3')),
  tr(td('5'), td('1'), td('F'), td('1'), td(''), td('Z')),
  tr(td('6'), td('1'), td('1')),
  tr(td('7'), td(''), td('1'), td('1')),
  '</table>');
const V4_CANON = A(
  '<table>',
  tr(td(''), td('1'), td('2'), td('3')),
  tr(td('5'), td('1'), td('F'), td('1')),
  tr(td('6'), td('1'), td('1'), td('')),
  tr(td('7'), td(''), td('1'), td('1')),
  '</table>');

// ── V5: a real-world-shaped rich form -- uppercase tags, attributes, entities ───
// Operators do not hand us canonical markup. This vector proves the reader tolerates what
// a spreadsheet actually emits AND that the writer normalises it to one canonical artifact.
const V5_MESSY = [
  '<TABLE class="mapTbl" border=1>',
  '  <TR>',
  "    <TD COLSPAN='5' style=\"font-weight:bold\">Lot &amp; Wafer</TD>",
  '  </TR>',
  '  <tr><th>X\\Y</th><th>4</th><th>5</th><th>6</th><th>7</th></tr>',
  '  <tr><td>1</td><td>1</td><td>&nbsp;</td><td>F</td><td>1</td></tr>',
  '  <tr><td>2</td><td><b>1</b></td><td>1</td><td>1</td><td>&#48;</td></tr>',
  '</TABLE>',
].join('\n');
const V5_CANON = A(
  '<table>',
  tr(tdc(5, 'Lot &amp; Wafer')),
  tr(td(''), td('4'), td('5'), td('6'), td('7')),
  tr(td('1'), td('1'), td(''), td('F'), td('1')),
  tr(td('2'), td('1'), td('1'), td('1'), td('0')),
  '</table>');

// ── V6: a header band row that is NOT identity ──────────────────────────────────
// 🔴 THE ROW THAT MAKES "RECOGNISE THE RULER BY SHAPE" SCORABLE. `WF | 12 | 25` sits above
//    the real ruler, its corner is 1x1 and its numbers are MERGED. A reader that accepts a
//    ruler because the cells hold numbers takes this row as the X axis, and then the origin
//    cross-check fires on a document that is perfectly well formed. Without a fixture like
//    this, "unmerged" in the tick test is decoration.
// It also carries no identity of its own: its LEFT chain is one long, not two, so the
// format attributes no meaning to it and the writer does not reproduce it.
const V6_X = [2, 3, 4, 5, 6, 7];
const V6_Y = [0, 1, 2];
const V6_GRID = [
  ['', '1', '1', '1', '1', ''],
  ['1', 'F', '1', '1', '1', '1'],
  ['', '1', '9', '1', '', ''],
];
const V6_HTML = A(
  '<table>',
  tr(tdc(7, 'wafer 07')),
  tr(tdc(2, 'LOT'), tdc(2, 'NO'), tdc(3, 'B7')),
  tr(td('WF'), tdc(3, '12'), tdc(3, '25')),
  tr(td(''), ...V6_X.map(x => td(String(x)))),
  ...V6_Y.map((y, i) => tr(td(String(y)), ...V6_GRID[i].map(v => td(v)))),
  '</table>');
const V6_CANON = A(
  '<table>',
  tr(tdc(7, 'wafer 07')),
  tr(tdc(2, 'LOT'), tdc(2, 'NO'), tdc(3, 'B7')),
  tr(td(''), ...V6_X.map(x => td(String(x)))),
  ...V6_Y.map((y, i) => tr(td(String(y)), ...V6_GRID[i].map(v => td(v)))),
  '</table>');

// ── V7: the plain surface with an operator's note above it ──────────────────────
// Not a refusal: the two origin derivations still agree, so the table is readable. The note
// is content that has no coordinate, and it is REPORTED rather than dropped in silence.
const V7_X = [1, 2, 3, 4, 5];
const V7_Y = [8, 9, 10];
const V7_GRID = [
  ['', '1', '1', '1', ''],
  ['1', '1', 'F', '1', '1'],
  ['', '1', '1', '1', ''],
];
const V7_MATRIX = [['', ...V7_X.map(String)]]
  .concat(V7_Y.map((y, i) => [String(y), ...V7_GRID[i]]))
  .map(r => r.join('\t')).join('\n');
const V7_TEXT = ['맵 출력본 2026-08', ''].concat(V7_MATRIX.split('\n')).join('\n');

// ── refusals ────────────────────────────────────────────────────────────────────
// 🔴 A REFUSAL IS A CONTRACT, NOT AN ERROR PATH. X and Y are the business key, so a
//    plausible-looking wrong origin files the whole map under coordinates that do not
//    exist. Zero cells with a named reason is strictly better.
const R1_HTML = A(
  '<table>',
  tr(td('SLOT'), td('2'), td('3'), td('6')),
  tr(td(''), td('11'), td('12'), td('13')),
  tr(td('1'), td('1'), td('1'), td('F')),
  tr(td('2'), td('1'), td('1'), td('1')),
  '</table>');
const R2_HTML = A('<table>', tr(tdc(3, 'TITLE')), tr(td('A'), td('B'), td('C')), '</table>');
const R3_HTML = A(
  '<table>',
  tr(td(''), td('1'), td('2'), td('2')),
  tr(td('5'), td('1'), td('1'), td('1')),
  tr(td('6'), td('1'), td('1'), td('1')),
  '</table>');
const R4_TEXT = ['SLOT\t2\t3\t6', '\t11\t12\t13', '1\t1\t1\tF', '2\t1\t1\t1'].join('\n');

const cellsFrom = (xs, ys, grid) => {
  const out = [];
  ys.forEach((y, r) => xs.forEach((x, c) => out.push({ x, y, value: grid[r][c] })));
  return out;
};

const decl = (o) => ({
  surface: o.surface,
  title: {
    value: o.title === undefined ? null : o.title,
    source: o.title === undefined ? 'absent' : 'declared',
    display: o.title === undefined ? '미상' : o.title,
  },
  identity: (o.identity || []).map(([key, value]) => ({ key, value, source: 'declared' })),
  extent: {
    xTicks: o.x, yTicks: o.y,
    minX: Math.min(...o.x), maxX: Math.max(...o.x),
    minY: Math.min(...o.y), maxY: Math.max(...o.y),
    nx: o.x.length, ny: o.y.length,
    xDirection: o.xDir, yDirection: o.yDir,
  },
});

export const VECTORS = [
  {
    name: 'V1 rich form, full header band',
    surface: 'rich',
    input: V1_HTML,
    expectOut: V1_HTML,               // already canonical: write(read(x)) must be x
    declaration: decl({
      surface: 'rich', title: 'bonding_map · 4B12',
      identity: [['BDIE_LOT', 'AF12312'], ['BDIE_WF', '07'], ['DATE_YM', '202608']],
      x: V1_X, y: V1_Y, xDir: 'ascending', yDir: 'ascending',
    }),
    cells: cellsFrom(V1_X, V1_Y, V1_GRID),
    intake: { cellsRead: 35, cellsAccepted: 35, rejected: [] },
  },
  {
    name: 'V2 rich form, identity but no TITLE',
    surface: 'rich',
    input: V2_HTML,
    expectOut: V2_HTML,
    declaration: decl({
      surface: 'rich', identity: [['LOT_NO', 'A9']],
      x: V2_X, y: V2_Y, xDir: 'ascending', yDir: 'ascending',
    }),
    cells: cellsFrom(V2_X, V2_Y, V2_GRID),
    intake: { cellsRead: 30, cellsAccepted: 30, rejected: [] },
  },
  {
    name: 'V3 plain surface, descending Y',
    surface: 'plain',
    input: V3_TEXT,
    expectOutText: V3_TEXT,
    declaration: decl({
      surface: 'plain', x: V3_X, y: V3_Y, xDir: 'ascending', yDir: 'descending',
    }),
    cells: cellsFrom(V3_X, V3_Y, V3_GRID),
    intake: { cellsRead: 24, cellsAccepted: 24, rejected: [] },
  },
  {
    name: 'V4 rich form with an undeclared column and a short row',
    surface: 'rich',
    input: V4_HTML,
    expectOut: V4_CANON,
    declaration: decl({
      surface: 'rich', x: [1, 2, 3], y: [5, 6, 7], xDir: 'ascending', yDir: 'ascending',
    }),
    cells: [
      { x: 1, y: 5, value: '1' }, { x: 2, y: 5, value: 'F' }, { x: 3, y: 5, value: '1' },
      { x: 1, y: 6, value: '1' }, { x: 2, y: 6, value: '1' },
      { x: 1, y: 7, value: '' }, { x: 2, y: 7, value: '1' }, { x: 3, y: 7, value: '1' },
    ],
    intake: {
      cellsRead: 10, cellsAccepted: 8,
      rejected: [
        { code: 'mapping_unavailable', count: 1 },
        { code: 'not_declared', count: 1 },
      ],
    },
    // The written form cannot be ragged, so the coordinate that had no cell comes back as
    // an explicit blank. Named here so the round-trip assertion stays exact.
    repairedBlanks: ['3,6'],
  },
  {
    name: 'V5 rich form as a spreadsheet actually emits it',
    surface: 'rich',
    input: V5_MESSY,
    expectOut: V5_CANON,
    declaration: decl({
      surface: 'rich', title: 'Lot & Wafer',
      x: [4, 5, 6, 7], y: [1, 2], xDir: 'ascending', yDir: 'ascending',
    }),
    cells: cellsFrom([4, 5, 6, 7], [1, 2], [
      ['1', '', 'F', '1'],
      ['1', '1', '1', '0'],
    ]),
    intake: { cellsRead: 8, cellsAccepted: 8, rejected: [] },
  },
  {
    name: 'V6 rich form with a merged numeric row above the ruler',
    surface: 'rich',
    input: V6_HTML,
    expectOut: V6_CANON,
    declaration: decl({
      surface: 'rich', title: 'wafer 07', identity: [['LOT_NO', 'B7']],
      x: V6_X, y: V6_Y, xDir: 'ascending', yDir: 'ascending',
    }),
    cells: cellsFrom(V6_X, V6_Y, V6_GRID),
    intake: { cellsRead: 18, cellsAccepted: 18, rejected: [] },
  },
  {
    name: 'V7 plain surface with a note above the table',
    surface: 'plain',
    input: V7_TEXT,
    expectOutText: V7_MATRIX,
    declaration: decl({
      surface: 'plain', x: V7_X, y: V7_Y, xDir: 'ascending', yDir: 'ascending',
    }),
    cells: cellsFrom(V7_X, V7_Y, V7_GRID),
    intake: {
      cellsRead: 16, cellsAccepted: 15,
      rejected: [{ code: 'not_declared', count: 1 }],
    },
  },
];

export const REFUSALS = [
  { name: 'R1 rich: a ruler-shaped SLOT row above the real ruler', input: R1_HTML,
    code: 'mapping_unavailable', reasonHas: '엇갈립니다' },
  { name: 'R2 rich: no ruler row and no Y axis', input: R2_HTML,
    code: 'mapping_unavailable', reasonHas: '2차원 맵 양식의 모양이 아닙니다' },
  { name: 'R3 rich: the same X coordinate twice', input: R3_HTML,
    code: 'mapping_unavailable', reasonHas: '두 번 나옵니다' },
  { name: 'R4 plain: a ruler-shaped SLOT row above the real ruler', input: R4_TEXT,
    code: 'mapping_unavailable', reasonHas: '엇갈립니다' },
];

// The canonical artifacts, exported so an oracle outside this harness (the reference
// Python parser) can be run over exactly the bytes the harness scores.
export const ARTIFACTS = Object.freeze({
  V1: V1_HTML, V2: V2_HTML, V3: V3_TEXT, V4: V4_HTML, V5: V5_MESSY, V6: V6_HTML,
  V7: V7_TEXT, R1: R1_HTML, R2: R2_HTML, R3: R3_HTML, R4: R4_TEXT,
});
