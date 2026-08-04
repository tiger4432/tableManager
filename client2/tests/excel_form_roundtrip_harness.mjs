// ═══════════════════════════════════════════════════════════════════════════════
// The operator Excel form, scored in BOTH directions against contract vectors.
// Run: node client2/tests/excel_form_roundtrip_harness.mjs [--verbose] [--mutate]
//
// 🔴 IT `import`s ITS TARGET. No `readFileSync` of the module under test, no `node:vm`, no
//    text slicing, no `node_modules`. That is not a testing preference -- it is what
//    `map2/excel_io.js` being a real module (arguments in, values out, no module state)
//    BUYS, and the only way to keep the buy is to spend it. The moment a harness slices
//    source text, the source's structure acquires a veto over refactoring.
//
// WHAT IT SCORES, and why both halves are here:
//   IN   input artifact -> declaration + cells + intake, compared field by field against
//        the vector. Not "did it parse" -- WHICH keys got WHICH values.
//   OUT  declaration + cells -> artifact, compared BYTE FOR BYTE against the vector's
//        expected artifact. For the vectors that are already canonical this makes the
//        round trip an identity; for the ones that are not, it pins the repair.
//   BACK the written artifact is read again and must produce the same declaration and
//        cells. A writer and a reader that are wrong in the SAME way would survive IN and
//        OUT separately; they cannot survive being scored against the vector's own record.
//
// ⚠️ NO REAL OPERATOR ARTIFACT EXISTS ON THIS BOX. `ingestion_workspace/.../archives/` and
//    `raws/` are empty and there is no spreadsheet file under `dev_env`. Every artifact is
//    CONSTRUCTED from the reference parser's rules. These vectors therefore prove
//    self-consistency and conformance to the parser's stated rules -- they do NOT prove a
//    round trip against a file an operator produced. Do not cite them as if they did.
// ═══════════════════════════════════════════════════════════════════════════════
import { VECTORS, REFUSALS } from './fixtures/excel_form_vectors.mjs';
import * as GATEWAY from '../src/map2/artifact_gateway.js';

const MODULE_PATH = new URL('../src/map2/excel_io.js', import.meta.url);

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

// Key ORDER is not part of any contract here -- a cell map keyed by coordinate is a set of
// facts, and `JSON.stringify` would score two identical maps as different because one was
// built in a different order. Arrays keep their order (identity IS ordered); objects do not.
function canon(v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object') {
    const out = {};
    Object.keys(v).sort().forEach(k => { out[k] = canon(v[k]); });
    return out;
  }
  return v;
}
const J = (v) => JSON.stringify(canon(v));

function run(mod) {
  let compared = 0;
  const failures = [];
  const evidence = [];

  const eq = (label, got, want) => {
    compared++;
    if (J(got) === J(want)) { evidence.push(`ok   ${label}`); return true; }
    failures.push(`${label}: got ${J(got)} want ${J(want)}`);
    evidence.push(`FAIL ${label}: got ${J(got)} want ${J(want)}`);
    return false;
  };
  const truthy = (label, got) => eq(label, !!got, true);

  // ── A. the exported surface exists and is shaped as declared ──────────────────
  ['readMapForm', 'writeMapForm', 'detectFormSurface', 'ingestionRecords']
    .forEach(n => eq(`A. exports ${n}`, typeof mod[n], 'function'));
  eq('A. SECTION_WIDE_RATIO', mod.SECTION_WIDE_RATIO, 0.7);
  eq('A. MIN_AXIS_TICKS', mod.MIN_AXIS_TICKS, 2);
  eq('A. META_CHAIN_LEN', mod.META_CHAIN_LEN, 2);
  eq('A. META_KEY_JOIN', mod.META_KEY_JOIN, '_');
  eq('A. UNKNOWN_DISPLAY is the borrowed word', mod.UNKNOWN_DISPLAY, '미상');
  eq('A. rejection vocabulary is borrowed, not invented',
    [...mod.REJECTION_CODES].sort(), ['mapping_unavailable', 'not_declared']);
  eq('A. INGESTION_RENAME matches the pipeline projection',
    { ...mod.INGESTION_RENAME }, { BDIE_LOT: 'base', VALUE: 'leg' });
  eq('A. surfaces', [...mod.FORM_SURFACES], ['rich', 'plain']);

  // ── B. per-vector: IN, OUT, BACK ──────────────────────────────────────────────
  for (const v of VECTORS) {
    const got = mod.readMapForm(v.input);
    if (!truthy(`${v.name} :: reads ok`, got.ok)) {
      failures.push(`${v.name}: refused with ${got.code} / ${got.reason}`);
      continue;
    }
    const d = got.declaration;

    eq(`${v.name} :: surface`, d.surface, v.declaration.surface);
    eq(`${v.name} :: detectFormSurface`, mod.detectFormSurface(v.input), v.declaration.surface);
    eq(`${v.name} :: title`, { ...d.title }, v.declaration.title);
    eq(`${v.name} :: identity`, d.identity.map(i => ({ ...i })), v.declaration.identity);
    eq(`${v.name} :: extent`, {
      xTicks: [...d.extent.xTicks], yTicks: [...d.extent.yTicks],
      minX: d.extent.minX, maxX: d.extent.maxX, minY: d.extent.minY, maxY: d.extent.maxY,
      nx: d.extent.nx, ny: d.extent.ny,
      xDirection: d.extent.xDirection, yDirection: d.extent.yDirection,
    }, v.declaration.extent);

    // 🔴 CELLS ARE COMPARED KEY -> VALUE, NOT BY COUNT. A count is exactly what a
    //    transposed or shifted read preserves. Every coordinate is named.
    const gotMap = {};
    got.cells.forEach(c => { gotMap[`${c.x},${c.y}`] = c.value; });
    const wantMap = {};
    v.cells.forEach(c => { wantMap[`${c.x},${c.y}`] = c.value; });
    eq(`${v.name} :: cells (key -> value)`, gotMap, wantMap);
    eq(`${v.name} :: cell count`, got.cells.length, v.cells.length);

    // ⚠️ THE FIXTURE MUST BE ABLE TO SEE A TRANSPOSITION. If reading the same artifact
    //    with x and y swapped produced the same map, this vector would score nothing.
    const swapped = {};
    got.cells.forEach(c => { swapped[`${c.y},${c.x}`] = c.value; });
    eq(`${v.name} :: a transposed read differs (fixture is not degenerate)`,
      J(swapped) !== J(gotMap), true);

    eq(`${v.name} :: intake counts`,
      { cellsRead: got.intake.cellsRead, cellsAccepted: got.intake.cellsAccepted },
      { cellsRead: v.intake.cellsRead, cellsAccepted: v.intake.cellsAccepted });
    eq(`${v.name} :: intake rejections (code + count)`,
      got.intake.rejected.map(r => ({ code: r.code, count: r.count })),
      v.intake.rejected);
    got.intake.rejected.forEach((r, i) => {
      truthy(`${v.name} :: rejection ${i} carries a reason`, r.reason && r.reason.length > 0);
    });

    // The form declares NO frame axis. Saying so in the shared vocabulary is the point.
    truthy(`${v.name} :: frame present`, !!d.frame);
    eq(`${v.name} :: form declares no rotation`, d.frame.axes.rotation.source, 'absent');
    eq(`${v.name} :: form declares no grid size`, d.frame.axes.cols.source, 'absent');
    eq(`${v.name} :: form declares no origin`, d.frame.axes.startX.source, 'absent');

    // OUT -- byte for byte.
    const out = mod.writeMapForm(d, got.cells);
    if (v.expectOut !== undefined) eq(`${v.name} :: writes the expected artifact`, out.html, v.expectOut);
    if (v.expectOutText !== undefined) eq(`${v.name} :: writes the expected text`, out.text, v.expectOutText);
    eq(`${v.name} :: no writer warnings`, [...out.warnings], []);

    // BACK -- the written artifact must read to the same record.
    const back = mod.readMapForm(v.declaration.surface === 'plain' ? out.text : out.html);
    truthy(`${v.name} :: re-reads ok`, back.ok);
    if (back.ok) {
      eq(`${v.name} :: round trip preserves title`, { ...back.declaration.title }, v.declaration.title);
      eq(`${v.name} :: round trip preserves identity`,
        back.declaration.identity.map(i => ({ ...i })), v.declaration.identity);
      eq(`${v.name} :: round trip preserves extent ticks`,
        { x: [...back.declaration.extent.xTicks], y: [...back.declaration.extent.yTicks] },
        { x: v.declaration.extent.xTicks, y: v.declaration.extent.yTicks });
      const backMap = {};
      back.cells.forEach(c => { backMap[`${c.x},${c.y}`] = c.value; });
      // 🔴 THE REPAIR IS NAMED, NOT ABSORBED. The writer cannot emit a ragged row, so a
      //    coordinate that arrived with no cell at all comes back as an explicit BLANK.
      //    That is a real change to the artifact, so the vector states exactly which
      //    coordinates it happens at -- otherwise "the round trip holds" would quietly
      //    mean "the round trip holds except where it invents cells".
      const repairedWant = { ...gotMap };
      (v.repairedBlanks || []).forEach(k => { repairedWant[k] = ''; });
      eq(`${v.name} :: round trip preserves every cell (plus named repairs)`,
        backMap, repairedWant);
      eq(`${v.name} :: round trip is clean (nothing rejected the second time)`,
        back.intake.rejected.map(r => r.code), []);
      // Writing what was just read must be a fixed point.
      const out2 = mod.writeMapForm(back.declaration, back.cells);
      eq(`${v.name} :: writer is idempotent`, out2.html, out.html);
      eq(`${v.name} :: writer is idempotent (text)`, out2.text, out.text);
    }

    // The flattened ingestion record shape, so a caller can be scored against the
    // reference parser's output rather than against a belief about the format.
    const recs = mod.ingestionRecords(d, got.cells);
    eq(`${v.name} :: ingestion record count`, recs.length, v.cells.length);
    if (recs.length) {
      const keys = Object.keys(recs[0]);
      eq(`${v.name} :: ingestion record starts with TITLE`, keys[0], 'TITLE');
      eq(`${v.name} :: ingestion record ends X, Y, VALUE`, keys.slice(-3), ['X', 'Y', 'VALUE']);
      const titleWant = v.declaration.title.source === 'declared'
        ? v.declaration.title.value : 'Default';
      eq(`${v.name} :: ingestion TITLE fallback matches the reference parser`,
        recs[0].TITLE, titleWant);
    }
  }

  // ── C. refusals ───────────────────────────────────────────────────────────────
  for (const r of REFUSALS) {
    const got = mod.readMapForm(r.input);
    eq(`${r.name} :: refuses`, got.ok, false);
    eq(`${r.name} :: code`, got.code, r.code);
    truthy(`${r.name} :: reason names the cause (${r.reasonHas})`,
      typeof got.reason === 'string' && got.reason.indexOf(r.reasonHas) >= 0);
    eq(`${r.name} :: reads no cells`, got.cells, null);
    eq(`${r.name} :: accepts nothing`, got.intake.cellsAccepted, 0);
  }

  // ── D. module discipline, asserted rather than assumed ────────────────────────
  const v1 = VECTORS[0];
  const a = mod.readMapForm(v1.input);
  const b = mod.readMapForm(v1.input);
  eq('D. two reads agree (no module state)', J(a.declaration), J(b.declaration));
  eq('D. result is frozen', Object.isFrozen(a), true);
  eq('D. declaration is frozen', Object.isFrozen(a.declaration), true);
  eq('D. cells are frozen', Object.isFrozen(a.cells), true);
  // Mutating the caller's array after the fact must not move the artifact.
  const cellsCopy = a.cells.map(c => ({ ...c }));
  const before = mod.writeMapForm(a.declaration, cellsCopy).html;
  cellsCopy[0].value = 'XXX';
  eq('D. the writer does not alias a previous result',
    mod.writeMapForm(a.declaration, a.cells).html, before);
  eq('D. empty input refuses rather than throwing', mod.readMapForm('').ok, false);
  eq('D. null input refuses rather than throwing', mod.readMapForm(null).ok, false);
  eq('D. an unknown surface refuses', mod.readMapForm(v1.input, { surface: 'xlsx' }).ok, false);

  // A corner label that reads as a coordinate would turn the ruler row into a data row.
  let threw = false;
  try { mod.writeMapForm(a.declaration, a.cells, { corner: '0' }); } catch (e) { threw = true; }
  eq('D. a numeric corner label is refused, not written', threw, true);

  // Below the minimum width the identity band cannot be encoded, and the writer SAYS SO
  // instead of dropping it. This is the writer's only partial outcome and it is named.
  const narrow = mod.writeMapForm(
    { title: { value: 'T', source: 'declared' }, identity: [{ key: 'A_B', value: 'c' }],
      extent: { xTicks: [1, 2], yTicks: [1, 2] } },
    [{ x: 1, y: 1, value: '1' }]);
  eq('D. narrow form warns instead of silently dropping identity',
    [...narrow.warnings], ['identity_not_encodable']);

  // ── E. the gateway seam's invariant, as a hard assertion ──────────────────────
  // 🔴 `accepted + rejectedTotal == rows`. NOTHING MAY BE SILENTLY DROPPED. This is the
  //    only way an operator can tell "the file had 40 and 40 arrived" from "the file had
  //    400 and 40 arrived", and it is checked on EVERY vector including the refusals --
  //    an invariant that holds except in the interesting case is not an invariant.
  //    The gateway is scored against the LIVE module, not the mutant, on purpose: it is a
  //    different lane's file and this harness does not mutate it.
  if (GATEWAY) {
    for (const v of VECTORS) {
      const g = GATEWAY.readArtifact(v.input);
      eq(`E. ${v.name} :: accepted + rejectedTotal === rows`,
        g.accepted + g.rejectedTotal, g.rows);
      eq(`E. ${v.name} :: rows equals the coordinates the artifact contained`,
        g.rows, v.intake.cellsRead);
      eq(`E. ${v.name} :: not refused`, g.refused, null);
      eq(`E. ${v.name} :: rejection reasons are the closed set`,
        g.rejected.every(r => Object.values(GATEWAY.REJECTED).indexOf(r.reason) >= 0), true);
      // Both surfaces come back out of the seam, and the rich one is the artifact.
      eq(`E. ${v.name} :: seam writes the same artifact as the module`,
        GATEWAY.writeArtifact(g.cells, g.declaration,
          { surface: v.declaration.surface === 'plain' ? 'plain' : 'rich' }),
        v.declaration.surface === 'plain'
          ? LIVE_OUT(v, g).text : LIVE_OUT(v, g).html);
    }
    for (const r of REFUSALS) {
      const g = GATEWAY.readArtifact(r.input);
      eq(`E. ${r.name} :: invariant holds on a refusal`, g.accepted + g.rejectedTotal, g.rows);
      eq(`E. ${r.name} :: refusal is not disguised as a partial read`, g.rows, 0);
      truthy(`E. ${r.name} :: refusal carries a reason`, !!(g.refused && g.refused.detail));
      eq(`E. ${r.name} :: refusal reason is in the closed set`,
        g.refused.reason, GATEWAY.REJECTED.NO_DECLARATION);
      eq(`E. ${r.name} :: no declaration is handed on`, g.declaration, null);
    }
    eq('E. every honest-degradation code has a seam word',
      GATEWAY.unmappedRejectionCodes(), []);
    eq('E. the aggregate line is one sentence, not per-row noise',
      GATEWAY.rejectionSummary([{ reason: GATEWAY.REJECTED.OUT_OF_DECLARED_GRID, count: 3 }]),
      '선언 격자 밖 3건');
    eq('E. the shell affordance stays closed until the wiring lane scores it',
      GATEWAY.isImplemented(), false);
  }

  function LIVE_OUT(v, g) { return mod.writeMapForm(g.declaration, g.cells); }

  return { compared, failures, evidence };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════
const verbose = process.argv.includes('--verbose');
const mutate = process.argv.includes('--mutate');

let LIVE;
try {
  LIVE = await import(MODULE_PATH.href);
} catch (e) {
  die(`could not import the module under test -- ${e && e.message ? e.message : e}`);
}

const base = run(LIVE);
if (verbose || !mutate) base.evidence.forEach(e => console.log('  ' + e));
console.log(`${base.failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${base.compared} assertions, `
  + `${base.failures.length} failure(s)`);
console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
base.failures.slice(0, 25).forEach(f => console.log(`   x ${f}`));
if (base.failures.length > 25) console.log(`   ... and ${base.failures.length - 25} more`);

if (mutate) {
  const { readFileSync } = await import('node:fs');
  const { fileURLToPath } = await import('node:url');
  // Line endings are normalised before anchoring. The repo stores these files with CRLF
  // under `core.autocrlf=true`, so an anchor written with `\n` MISSES on a plain checkout
  // and the run dies claiming the mutant could not be applied.
  // 🔴 A `data:` URL HAS NO BASE, so the module's own relative imports (`../tsv.js`,
  //    `./declaration.js`) cannot resolve inside a mutant. They are rewritten to absolute
  //    `file:` URLs first -- WITHOUT that, every mutant "throws" and every throw scores as
  //    a kill, which is the exact disguise the unapplied-mutant guard below exists to
  //    strip: a perfect mutation report in which nothing was ever executed.
  const SRC = readFileSync(fileURLToPath(MODULE_PATH), 'utf8')
    .replace(/\r\n/g, '\n')
    .replace(/from '(\.[^']*)'/g, (m, spec) => `from '${new URL(spec, MODULE_PATH).href}'`);
  const swap = (name, from, to) => ({
    name,
    apply: (s) => {
      const n = s.split(from).length - 1;
      if (n === 0) throw new Error(`anchor not found: ${from.slice(0, 60)}`);
      if (n !== 1) throw new Error(`anchor is not unique (${n} matches): ${from.slice(0, 60)}`);
      return s.split(from).join(to);
    },
  });

  const MUTANTS = [
    // ── the three the brief names ────────────────────────────────────────────────
    swap('M1 a header row is dropped (the band stops one row short of the ruler)',
      'n.isHeader = !!n.value && n.rEnd < xRow && !isUnmerged(n);',
      'n.isHeader = !!n.value && n.rEnd < xRow - 1 && !isUnmerged(n);'),
    swap('M2 the axes are transposed on the way out',
      'cells.push(Object.freeze({ x: coordInt(xNode.value), y: yVal, value: data.value }));',
      'cells.push(Object.freeze({ x: yVal, y: coordInt(xNode.value), value: data.value }));'),
    swap('M3 a rejected cell is swallowed silently',
      '      seenOffAxis.add(n.id);\n',
      '      seenOffAxis.add(n.id); continue;\n'),
    // ── the rest of the format's load-bearing rules ─────────────────────────────
    swap('M4 the grid origin is derived once instead of twice (rich)',
      'if (topAnchor === null || bottomAnchor === null || topAnchor !== bottomAnchor) {\n    let reason;\n    if (topAnchor === null && bottomAnchor === null) {\n      reason = \'X축 눈금 줄도 Y축 좌표도 없습니다 — 이 표는 2차원 맵 양식의 모양이 아닙니다.\';\n    } else if (topAnchor === null) {\n      reason = `X축 눈금 줄 모양(좌표가 아닌 모서리 칸',
      'if (topAnchor === null || bottomAnchor === null) {\n    let reason;\n    if (topAnchor === null && bottomAnchor === null) {\n      reason = \'X축 눈금 줄도 Y축 좌표도 없습니다 — 이 표는 2차원 맵 양식의 모양이 아닙니다.\';\n    } else if (topAnchor === null) {\n      reason = `X축 눈금 줄 모양(좌표가 아닌 모서리 칸'),
    swap('M5 the ruler is recognised by its numbers instead of by its shape',
      'if (!isUnmerged(node) || coordInt(node.value) === null) return null;',
      'if (coordInt(node.value) === null) return null;'),
    swap('M6 the meta chain length stops being exact',
      'if (anc.length !== META_CHAIN_LEN) continue;',
      'if (anc.length < 1) continue;'),
    swap('M7 the TITLE band threshold collapses, so an identity cell becomes the title',
      'const wideThreshold = Math.trunc(t.colCount * SECTION_WIDE_RATIO);',
      'const wideThreshold = 1;'),
    swap('M8 a repeated coordinate is accepted (rich)',
      'const dup = duplicateTicks(xNodes.map(n => coordInt(n.value)), yNodes.map(n => coordInt(n.value)));\n  if (dup) return refusal(\'mapping_unavailable\', dup);',
      'const dup = duplicateTicks(xNodes.map(n => coordInt(n.value)), yNodes.map(n => coordInt(n.value)));\n  if (false) return refusal(\'mapping_unavailable\', dup);'),
    swap('M9 the two rejection codes collapse into one',
      "        rej.add('mapping_unavailable',\n          '좌표는 있는데",
      "        rej.add('not_declared',\n          '좌표는 있는데"),
    swap('M10 cellsRead counts only what was accepted',
      'cellsRead: cells.length + rejected.reduce((n, r) => n + r.count, 0),',
      'cellsRead: cells.length,'),
    swap('M11 an absent title becomes an empty string instead of 미상',
      'display: titleDeclared ? String(a.title) : UNKNOWN_DISPLAY,',
      "display: titleDeclared ? String(a.title) : '',"),
    // ── the writer half ─────────────────────────────────────────────────────────
    swap('M12 the identity band is written unmerged, so it stops being identity',
      'const spans = [base, base, cols - 2 * base];',
      'const spans = [1, 1, cols - 2];'),
    swap('M13 the writer drops the ruler corner, shifting every column by one',
      'const matrix = [[corner].concat(xTicks.map(String))];',
      'const matrix = [xTicks.map(String)];'),
    swap('M14 the writer emits rows in tick order but reads cells by index',
      'for (const y of yTicks) matrix.push([String(y)].concat(xTicks.map(x => at(x, y))));',
      'for (const y of yTicks) matrix.push([String(y)].concat(xTicks.map(x => at(y, x))));'),
    swap('M15 plain: junk above the ruler is dropped without a word',
      "      rej.add('not_declared', '표 위에 표가 아닌 내용이 있습니다",
      "      void ('표 위에 표가 아닌 내용이 있습니다"),
    swap('CONTROL a comment change must NOT be caught',
      '// shared predicates', '// the shared predicates'),
  ];

  console.log('\n  MUTATION CONTROLS -- a surviving mutant means the check above it is inert.\n');
  let scored = 0;
  for (const m of MUTANTS) {
    const isControl = m.name.startsWith('CONTROL');
    let src;
    try {
      src = m.apply(SRC);
    } catch (e) {
      // 🔴 AN UNAPPLIED MUTANT IS NOT A CAUGHT MUTANT. A stale anchor whose throw gets
      //    scored as a kill reports a perfect run in which one axis was never tested.
      die(`mutant "${m.name}" could not be applied: ${e.message}`);
    }
    let killed;
    let detail = '';
    try {
      const url = 'data:text/javascript;base64,' + Buffer.from(src, 'utf8').toString('base64');
      const mod = await import(url);
      const out = run(mod);
      killed = out.failures.length > 0;
      detail = killed ? `${out.failures.length} failure(s), first: ${out.failures[0]}` : '';
      if (out.compared < base.compared) {
        detail += ` [WARNING: ran ${out.compared} of ${base.compared} assertions]`;
      }
    } catch (e) {
      killed = true;
      detail = `threw: ${String(e && e.message).slice(0, 110)}`;
    }
    if (killed !== isControl) scored++;
    console.log(`  ${killed ? 'CAUGHT  ' : 'SURVIVED'}  ${m.name}`);
    if (detail) console.log(`            ${detail}`);
  }
  console.log(`\n  ${scored}/${MUTANTS.length} scored as intended.`);
  if (scored !== MUTANTS.length) process.exit(1);
}

process.exit(base.failures.length === 0 ? 0 : 1);
