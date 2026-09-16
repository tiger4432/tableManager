/**
 * C-40 ② — 「선언창이 속성 자리를 «코드 0»으로 그리는가」. 대상을 IMPORT 합니다.
 *
 * 🔴 THE SUBJECT IS THE SHIPPED SKELETON, NOT AN INVENTED ONE. The claim under test is that
 *    the form draws three attribute seats with no client edit, and that claim is about the
 *    document the server actually serves (`server/ledger/ledger_skeleton.json`, a tracked
 *    file). A hand-made skeleton would let this pass on the day the real one loses a seat.
 *
 * 🔴 WHAT 「코드 0」 MEANS HERE, MEASURED RATHER THAN ASSERTED: the reader is generic, so the
 *    seats resolve through the same `shapeAt` every other field uses, and the client holds no
 *    literal for any of them. Both halves are scored — a generic reader that happened to be
 *    fed a written-down path would satisfy neither.
 *
 * Run:  node client2/tests/declaration_attribute_seats_harness.mjs [--mutate]
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe, readSourceText } from './lib/probe.mjs';
import { setAtPath, getAtPath, splitBundlePath } from '../src/ontology_path.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC = join(HERE, '..', 'src', 'ontology_skeleton.js');
const SKELETON_FILE = join(ROOT, 'server', 'ledger', 'ledger_skeleton.json');
const SAMPLE_FILE = join(ROOT, 'server', 'config', 'sample', 'ledger_config.json.sample');
const AUTHORING_SOURCES = ['ontology_explorer.js', 'ontology_explorer_view.js',
  'ontology_skeleton.js', 'ontology_path.js', 'ontology_explorer_store.js'];

let pass = 0, quiet = false;
const failures = [];
const pending = [];
const ok = (cond, name, detail = '') => {
  if (cond) { pass += 1; if (!quiet) console.log(`  OK   ${name}`); }
  else { failures.push(name); if (!quiet) console.log(`  BAD  ${name}${detail ? ' — ' + detail : ''}`); }
};

const SKELETON = JSON.parse(readFileSync(SKELETON_FILE, 'utf8'));
// 🔴 LF-NORMALISED, because this worktree checks out CRLF and the question is about the
//    document's CONTENT. Comparing the bytes as checked out would report a difference that
//    exists on Windows only and hide the one this gate is for.
const SAMPLE = readFileSync(SAMPLE_FILE, 'utf8').replace(/\r\n/g, '\n');

// The three seats ruling 124 named, spelled as the skeleton's own path.
const SEATS = [
  ['entities.*.attributes', ['entities', '*']],
  ['sources.*.bind.entities.*.attributes', ['sources', '*', 'bind', 'entities', '*']],
  ['sources.*.bind.mappings.*.bind.*.attributes',
    ['sources', '*', 'bind', 'mappings', '*', 'bind', '*']],
];

function suite(M) {
  const before = failures.length;
  pending.length = 0;                            // one run's answer, not every run's
  const defs = SKELETON.defs;
  const at = (steps) => M.shapeAt(SKELETON.root, steps, defs);

  // ══ ① 세 자리가 «진짜 스켈레톤»에서 나옵니다 ═════════════════════════════════════════
  const seatNodes = [];
  for (const [label, steps] of SEATS) {
    const holder = at(steps);
    const field = M.fieldOf(holder, 'attributes');
    const node = field ? M.shapeAt(field.node, [], defs) : null;
    seatNodes.push(node);
    ok(!!field && node && node.kind === 'map', `S «${label}» is a map the form can draw`,
      `holder=${holder && holder.kind} field=${!!field} node=${node && node.kind}`);
  }
  // 🔴 THE TYPE DEFINITION IS A LIST OF NAMES; THE TWO BINDING SEATS ARE NAME→BINDING. That
  //    difference is the grammar's (`_nonblank_list` vs a mapping of bindings), and a form
  //    that drew them alike would offer a binding box where only a name belongs.
  ok(seatNodes[0] && seatNodes[0].keyed_by === 'index',
    'S4 the type definition holds a LIST of names');
  ok(seatNodes[1] && seatNodes[1].keyed_by === 'name'
    && seatNodes[2] && seatNodes[2].keyed_by === 'name',
  'S5 both binding seats hold NAME -> binding');
  // 🔴 THE CONTROL. Without it a `shapeAt` that answered for anything would satisfy S1-S3,
  //    and the three assertions above would be measuring the harness rather than the form.
  ok(at(['sources', '*', 'bind', 'no_such_clause']) === null,
    'S6 CONTROL: a clause the skeleton does not declare resolves to nothing');

  // ══ ② 「keys 와 같은 편집 경험」— 같은 기제라는 것을 값으로 ═══════════════════════════
  // 🔴 NOT "it looks the same": the seed a NEW member starts from is compared against the
  //    one `keys` starts from, so the two are provably the same control rather than two
  //    controls that happen to resemble each other today.
  const entityRec = at(['entities', '*']);
  const keysNode = M.fieldOf(entityRec, 'keys');
  const attrNode = M.fieldOf(entityRec, 'attributes');
  ok(JSON.stringify(M.emptyOf(keysNode.node, defs))
    === JSON.stringify(M.emptyOf(attrNode.node, defs)),
  'S7 a new attribute list starts as a new key list does — one control, not two');
  const bindingRec = at(['sources', '*', 'bind', 'mappings', '*', 'bind', '*']);
  ok(JSON.stringify(M.emptyOf(M.fieldOf(bindingRec, 'keys').node, defs))
    === JSON.stringify(M.emptyOf(M.fieldOf(bindingRec, 'attributes').node, defs)),
  'S8 ...and so does a role-level attribute map beside its key map');

  // 🔴 THE OTHER HALF OF 「코드 0」. A generic reader is only half the claim: fed a path the
  //    client had written down, it would draw the same seats and stop following the skeleton
  //    the day an operator declares a fourth one. Measured: zero occurrences, all five files.
  {
    const wrote = AUTHORING_SOURCES.filter((f) => {
      const text = readFileSync(join(HERE, '..', 'src', f), 'utf8');
      return text.includes("'attributes'") || text.includes('"attributes"');
    });
    ok(wrote.length === 0, 'S12 the authoring client writes the word down nowhere',
      wrote.join(' '));
  }

  // ══ ③ 손 안 댄 상자는 «저장에 안 실립니다» (총괄 물음, 09-08 08:5x) ═══════════════════
  // 🔴 THE ANSWER IS A VALUE, NOT A READING. A brand-new binding is seeded by `emptyOf`, and
  //    that seed is what lands in the file — so if `attributes` appeared in it, every newly
  //    added binding would be born carrying a key its own kind forbids.
  // 🔴 THE ENTITY SEAT IS THE ONE THAT DECIDES IT. `entities.*.attributes` is optional and
  //    UNGATED, so the only thing keeping it out of a new declaration is the seeding rule
  //    itself — seed everything and every new entity is born carrying an empty list nobody
  //    chose. The binding seat is guarded twice over (optional AND gated on kind), so it
  //    cannot answer this question alone.
  const entitySeed = M.emptyOf(entityRec, defs);
  ok(!Object.prototype.hasOwnProperty.call(entitySeed, 'attributes'),
    'S9 a new entity declaration is NOT born with an attributes list — an untouched box '
    + 'writes nothing', JSON.stringify(entitySeed));
  const seed = M.emptyOf(bindingRec, defs);
  ok(!Object.prototype.hasOwnProperty.call(seed, 'attributes'),
    'S10 ...and neither is a new binding', JSON.stringify(seed));
  // ⚠️ The control for both: the rule is `required && its gate applies`. If they passed
  //    because seeding had stopped happening at all, this moves too — `keys` is required and
  //    ungated on an entity, and required BEHIND A GATE on a binding whose kind is not set.
  ok(Object.prototype.hasOwnProperty.call(entitySeed, 'keys')
    && !Object.prototype.hasOwnProperty.call(seed, 'keys'),
  'S11 CONTROL: seeding still happens — an ungated required field lands, a gated one waits');

  // ══ ④ 왕복 — 안 건드린 절이 «바이트 동일» ════════════════════════════════════════════
  // 🔴 THE EDITOR REWRITES THE WHOLE DOCUMENT ON EVERY FIELD EDIT (`JSON.stringify(next, null,
  //    2)`), so 「안 건드린 절은 그대로」 is a claim about the SHIPPED file's formatting, not
  //    about the edit. If the two ever diverge, one attribute typed into one source reformats
  //    every other declaration in the file and the diff stops being readable.
  const parsed = JSON.parse(SAMPLE);
  ok(JSON.stringify(parsed, null, 2) === SAMPLE,
    'R1 a field edit does not reformat the rest of the file');
  // And an actual write through the form's own path tools touches ONE line's worth.
  const steps = splitBundlePath('sources.dt_job.bind.entities.dtjob@1.attributes.dt_lot');
  const written = setAtPath(parsed, steps, { kind: 'column', column: 'dt_lot' });
  ok(written !== null && getAtPath(written, steps) !== undefined,
    'R2 a new attribute lands where the server spells it');
  {
    const beforeLines = SAMPLE.split('\n');
    const afterLines = JSON.stringify(written, null, 2).split('\n');
    const added = afterLines.length - beforeLines.length;
    // The four lines of `"dt_lot": { "kind": ..., "column": ... }` and nothing else moving.
    let common = 0;
    while (common < beforeLines.length && beforeLines[common] === afterLines[common]) common += 1;
    let tail = 0;
    while (tail < beforeLines.length - common
      && beforeLines[beforeLines.length - 1 - tail] === afterLines[afterLines.length - 1 - tail]) {
      tail += 1;
    }
    ok(added === 4 && common + tail === beforeLines.length,
      'R3 ...and every other line of the document is untouched',
      `added=${added} unchanged=${common + tail}/${beforeLines.length}`);
  }

  // ══ ⑤ 거절이 «그 칸»에 앉으려면 두 철자가 «같아야» 합니다 ═══════════════════════════
  // 🔴 A REFUSAL REACHES A ROW BY ITS PATH — `attentionPaths` collects `row.path` and
  //    `needsAttention` prefix-matches it. So if the form spelled a member one way and the
  //    validator the other, the refusal would land on NO row: the screen would say the save
  //    failed and show nothing owed, which is worse than saying nothing at all.
  //    The validator's spelling is `<bind path>.entities.<type>.attributes.<name>`
  //    (setup_bundle.py:_validate_bind_entities), dots throughout, version suffix intact.
  {
    const one = M.memberPath('sources', 'dt_job', 'name');
    const two = M.memberPath(`${one}.bind.entities`, 'dtjob@1', 'name');
    const three = M.memberPath(`${two}.attributes`, 'dt_eqp', 'name');
    ok(three === 'sources.dt_job.bind.entities.dtjob@1.attributes.dt_eqp',
      'A1 the form spells an attribute exactly as the validator names it', three);
    // ⚠️ The discriminator: an index-keyed member is BRACKETED. Dot-joining that one would
    //    send every refusal under `mappings` to a row that does not exist, and this seat
    //    sits beside those.
    ok(M.memberPath('sources.dt_job.bind.mappings', 0, 'index')
      === 'sources.dt_job.bind.mappings[0]',
    'A2 ...and an index-keyed member is still bracketed, which is a different spelling');
  }

  // ══ ⑥ 넷째 자리 — 서버 S-52-d ════════════════════════════════════════════════════════
  // 🔴 `defs.binding.attributes` is the only one of its six fields with no `when`, so the box
  //    is drawn on `column` and `constant` bindings too — and `problems.exact` allows the key
  //    for `entity` only. Reported (d1e811f3), accepted, and sent to the server as S-52-d.
  //    NAMED here rather than asserted, because asserting the fix would land a red harness
  //    for a file this lane does not own; it scores itself the moment the lock arrives.
  const gate = M.fieldOf(bindingRec, 'attributes').when;
  if (!gate) {
    pending.push('P1 defs.binding.attributes is ungated, so the box draws on kinds the '
      + 'validator refuses (server S-52-d)');
    if (!quiet) {
      console.log('  PENDING P1 defs.binding.attributes has no `when` — the box draws on '
        + 'column and constant bindings, which problems.exact refuses');
    }
  } else {
    ok(gate.field === 'kind' && gate.is === 'entity',
      'P1 the attributes box is locked to the one kind that may carry it',
      JSON.stringify(gate));
  }


// ── a leaf with ONE legal value is seeded with it, and the class is walked, not named ──────
//
// 🔴 판정 484 + the application lane's Q-50. The server's seed learned to read `const`; the
//    CLIENT builds a new member with no server round trip (`ontology_explorer.js` seeds with
//    `emptyOf` and writes it straight into the draft), so the screen went on producing the one
//    value the bundle validator refuses. Two seeds, one fixed.
//
// ⛔ THE FIELD IS NOT NAMED HERE. Asserting on `virtual_joins.materialize` would make this file
//    the second place that knows which field it is, and the next `const` leaf would land unscored
//    while this stayed green. The skeleton is WALKED for the property instead, so a leaf declared
//    next week is covered the day it appears.
function constLeavesIn(node, path, out) {
  if (Array.isArray(node)) {
    node.forEach((item, i) => constLeavesIn(item, path.concat(String(i)), out));
  } else if (node && typeof node === 'object') {
    if (Object.prototype.hasOwnProperty.call(node, 'const')) out.push({ node, path: path.slice() });
    Object.keys(node).forEach((k) => constLeavesIn(node[k], path.concat(k), out));
  }
  return out;
}
{
  const defs = SKELETON.defs;
  const leaves = constLeavesIn(SKELETON, [], []);
  // 🔴 WITHOUT THIS THE BLOCK IS VACUOUS. A skeleton that declares no `const` would make every
  //    assertion below pass by having nothing to check -- the legend making the claim empty.
  ok(leaves.length > 0,
    `the shipped skeleton declares at least one const leaf (found ${leaves.length})`);
  leaves.forEach(({ node, path }) => {
    ok(M.emptyOf(node, defs) === node.const,
      `a const leaf seeds its one legal value, not its kind's empty (${path.join('/')})`);
  });

  // ...and END TO END, through the seat the form actually uses: a brand-new member of a map.
  // This is where the defect lived -- the leaf was right in isolation and the member was born
  // wrong, because the record branch seeded required flags by hint.
  (SKELETON.root.fields || []).forEach((field) => {
    const map = field.node;
    if (!map || map.kind !== 'map') return;
    const member = M.shapeAt(SKELETON.root, [field.key, 'A_NEW_MEMBER'], defs);
    if (!member || member.kind !== 'record') return;
    const seeded = M.emptyOf(member, defs);
    (member.fields || []).forEach((sub) => {
      if (!sub.node || !Object.prototype.hasOwnProperty.call(sub.node, 'const')) return;
      ok(seeded[sub.key] === sub.node.const,
        `a new ${field.key} member is born with ${sub.key} = `
        + JSON.stringify(sub.node.const),
        `got ${JSON.stringify(seeded[sub.key])}`);
    });
  });
}

  return { fail: failures.length - before };
}

console.log('-- the three attribute seats, read off the shipped skeleton ----------');
suite(await import('../src/ontology_skeleton.js'));
const base = { pass, fail: failures.length };
const basePending = pending.slice();
console.log(`\n${base.fail === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, ${base.fail} failed`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);

const DEFECTS = [
  // Re-aimed by C-115: descent moved into the one shared `childOf`, so the map step is one
  // line there now. Same claim, same seats.
  ['a map stops being walked through, so the two binding seats disappear',
    (s) => s.replace("  if (node.kind === 'map') return deref(node.of, defs);",
                     "  if (node.kind === 'map') return null;")],
  ['`use` stops being followed, so a seat behind a shared def is invisible',
    (s) => s.replace('    cursor = (defs || {})[cursor.use];', '    return null;')],
  ['every field is seeded, so a new binding is born carrying a refused key',
    (s) => s.replace('      if (field.required !== true) continue;', '')],
  ['the seeding gate stops being asked, so a kind-less binding gets keys it forbids',
    (s) => s.replace('      if (!fieldApplies(field, seeded)) continue;', '')],
  ['a gated field is treated as always applying',
    (s) => s.replace('  if (!field || !field.when) return true;', '  return true;')],
  // The shipped defect, put back: the seed ignores `const` and falls through to the kind's
  // empty, which for a required flag is `false` -- the value the bundle validator refuses.
  ['a const leaf is seeded by its kind, so a new member is born refused',
    (s) => s.replace(
      "  if (Object.prototype.hasOwnProperty.call(shape, 'const')) return shape.const;", '')],
];
const CONTROLS = [
  ['comments stripped', (s) => s.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

if (process.argv.includes('--mutate')) {
  quiet = true;
  let caught = 0; const wrong = [];
  console.log('\n-- defect mutants (each must be CAUGHT) ------------------------------');
  for (const [name, mutate] of DEFECTS) {
    let r;
    try { r = suite((await loadWithProbe(SRC, { mutate, tag: 'attrseat' })).module); }
    catch (e) {
      if (/did not mutate|unchanged/.test(String(e && e.message))) {
        quiet = false; console.error(`  anchor GONE: ${name} — ${e.message}`); process.exit(2);
      }
      r = { fail: 1 };
    }
    if (r.fail > 0) { caught += 1; console.log(`  caught  ${name}`); }
    else { wrong.push(name); console.log(`  ESCAPED ${name}`); }
  }
  console.log('\n-- control mutants (each must ESCAPE) --------------------------------');
  for (const [name, mutate] of CONTROLS) {
    let r;
    try { r = suite((await loadWithProbe(SRC, { mutate, tag: 'attrseatc' })).module); }
    catch { r = { fail: 1 }; }
    if (r.fail === 0) console.log(`  escaped ${name}`);
    else { wrong.push(`control caught: ${name}`); console.log(`  CAUGHT  ${name} <- control caught`); }
  }
  quiet = false;
  console.log(`\nmutations: ${caught}/${DEFECTS.length} caught`);
  if (wrong.length) { console.error(`wrong verdicts:\n  ${wrong.join('\n  ')}`); process.exit(1); }
}

if (basePending.length) {
  console.log('PENDING (named, not passed):');
  for (const p of basePending) console.log(`  - ${p}`);
}
process.exit(base.fail === 0 ? 0 : 1);
