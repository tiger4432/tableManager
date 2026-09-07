/**
 * WALK NODE SHAPE — the CLIENT half, scored against `vectors.json`.
 *
 *   node contracts/walk_node_shape/client_harness.mjs
 *
 * Exit codes: 0 = client matches everything this contract can score today
 *             1 = divergence(s)   2 = harness failure
 *
 * Read-only. It never writes to `client2/`.
 *
 * WHY THIS HALF EXISTS BEFORE THE FEATURE DOES
 *   Ruling 123 orders the walk table's attribute columns AFTER the server half lands, and
 *   until then 「`/declaration` 모양 «읽고» 하니스 픽스처만」. Measured today, code 0:
 *
 *     server/ledger_trace_router.py:~632  `/declaration` publishes {type, keys, class} per
 *                                          entity — `attributes` is NOT on the wire yet
 *     client2/src/walk/derive.js:57       `tableColumns` composes 깊이 + declared keys +
 *                                          qualifier names + 라벨 + id — no attribute column
 *
 *   So the positive half is reported PENDING BY NAME rather than silently passing, and the
 *   two things that CAN be scored today are scored:
 *
 *     ② the standing prohibition — no attribute NAME may appear as a source literal in the
 *        walk client. Column names come from the declaration; a name written down here makes
 *        the screen a second author of a fact the declaration owns (ruling 123 gate ㉠'s
 *        mutant is exactly that: 「이름을 코드에 적으면 빨강」).
 *     ③-b gate ㉡ — a declaration WITHOUT `attributes` must leave the table byte-identical.
 *        That is true today and must stay true after the attribute columns land, so it is the
 *        one assertion here that measures the same thing before and after.
 *
 *   The switch from PENDING to SCORED needs no edit: the moment `tableColumns` returns any
 *   declared attribute name, section ③ scores all four cases strictly. "Built, but produces
 *   no attribute column at all" and "not built" are the same state, which is why that is a
 *   sound detector rather than an escape hatch.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const WALK_SRC = join(ROOT, 'client2', 'src', 'walk');

let pass = 0;
const failures = [];
const pending = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

let VECTORS;
let derive;
try {
  VECTORS = JSON.parse(readFileSync(join(HERE, 'vectors.json'), 'utf8'));
  derive = await import(pathToFileURL(join(WALK_SRC, 'derive.js')).href);
} catch (err) {
  console.error(`harness failure: ${err && err.message}`);
  process.exit(2);
}

// ══ THE FIXTURES ARE DERIVED FROM THE FILE, NEVER RESTATED ══════════════════════════════
// 🔴 Every value below is read out of `vectors.json`. Nothing in this harness spells an
//    attribute name or a value, so editing the shared file changes what is scored on BOTH
//    sides — which is the only reason a shared vector file is worth having.
//
// ⚠️ The type is the harness's own, not the seam's: the contract is about the SHAPE of a
//    node, and pinning a domain type here would put a domain word where none belongs.
//    It never reaches client code.
const TYPE = 'shape@1';
const IDENTITY_KEY = 'k';

/** The `/declaration` entity this case would publish once the server carries `attributes`. */
const declarationFor = (vcase) => ([{
  type: TYPE, keys: [IDENTITY_KEY], class: null,
  attributes: [...(vcase.declared_attributes || [])],
}]);

/** The walk node this case's server half must build — the client's INPUT is that output. */
const nodeFor = (vcase) => ({
  id: `ledger-entity:v1:${TYPE}:1`, type: TYPE, depth: 0, label: '1',
  keys: { [IDENTITY_KEY]: '1' },
  attributes: { ...((vcase.expect || {}).attributes || {}) },
  attribute_conflicts: (vcase.expect || {}).attribute_conflicts,
});

const CASES = Array.isArray(VECTORS.cases) ? VECTORS.cases : [];
const ALL_NAMES = [...new Set(CASES.flatMap((c) => c.declared_attributes || []))];

// ══ ① THE FILE IS THE AUTHORITY, AND IT STILL SAYS WHAT IT SAID ═════════════════════════
console.log('\n[1] the shared vectors');
eq('A1 four shapes, because four are what an operator can meet', 4, CASES.length);
ok('A2 each case declares names, an expected map and an expected count',
  CASES.every((c) => Array.isArray(c.declared_attributes)
    && c.expect && typeof c.expect.attributes === 'object'
    && Number.isInteger(c.expect.attribute_conflicts)));
ok('A3 identity stays keys-only — an attribute never makes a node new',
  (VECTORS.identity || {}).keys_only === true);
// 🔴 The pair that decides the COUNT. If these two ever expected the same number the file
//    would have stopped pinning ruling 124's definition, and both halves could drift.
{
  const differing = CASES.find((c) => c.name === 'two_differing_values');
  const same = CASES.find((c) => c.name === 'same_value_at_two_times');
  ok('A4 two differing values and the same value twice expect DIFFERENT counts',
    !!differing && !!same
    && differing.expect.attribute_conflicts !== same.expect.attribute_conflicts,
    `${differing && differing.expect.attribute_conflicts} vs `
      + `${same && same.expect.attribute_conflicts}`);
  // 🔴 And the winner is the LATEST, not the first — the same fact the count leaves alone.
  ok('A5 the surviving value is the later arrival',
    !!differing && Object.values(differing.expect.attributes).length === 1
    && Object.values(differing.expect.attributes)[0]
       === differing.atoms[differing.atoms.length - 1].value);
}

// ══ ② THE STANDING PROHIBITION — measurable with no feature at all ══════════════════════
// 🔴 A name written into the walk client is the screen becoming a second author of the
//    declaration's fact. It fails silently: the column keeps drawing after the declaration
//    drops the name, and never appears when a new one is declared.
console.log('\n[2] no attribute name is a source literal in the walk client');
{
  const files = readdirSync(WALK_SRC).filter((f) => f.endsWith('.js'));
  ok('B0 the walk client has sources to read', files.length > 0);
  for (const name of ALL_NAMES) {
    const hits = [];
    for (const f of files) {
      const text = readFileSync(join(WALK_SRC, f), 'utf8');
      if (text.includes(`'${name}'`) || text.includes(`"${name}"`)) hits.push(f);
    }
    ok(`B1 «${name}» is not written down in client2/src/walk`, hits.length === 0,
      hits.join(' '));
  }
}

// ══ ③ COLUMN NAMES — scored the moment the reader produces one ══════════════════════════
console.log('\n[3] the columns are the declared names');
{
  // Gate ㉡, and it is true on BOTH sides of the landing: an entity that declares no
  // attributes must leave the table exactly as it is today.
  const bare = [{ type: TYPE, keys: [IDENTITY_KEY], class: null }];
  const nameList = (cols) => cols.map((c) => c.name).join(',');
  eq('C1 a declaration without attributes leaves the table unchanged',
    `깊이,${IDENTITY_KEY},라벨,id`, nameList(derive.tableColumns(bare, TYPE, [])));

  const drawn = CASES.map((c) => {
    const cols = derive.tableColumns(declarationFor(c), TYPE, []);
    return (c.declared_attributes || [])
      .filter((n) => cols.some((col) => col.name === n && col.kind === 'attribute'));
  });
  if (drawn.every((names) => names.length === 0)) {
    // ⚠️ PENDING BY NAME, not silence. The seam's server half is not on the wire
    //    (`/declaration` publishes {type, keys, class}) and the reader draws no attribute
    //    column, so there is nothing here to be right or wrong about yet.
    pending.push('C2 declared attribute names become columns '
      + '(walk/derive.js tableColumns draws none, and /declaration does not carry them)');
    console.log('  PENDING C2 declared attribute names become columns — '
      + 'no attribute column is produced, so the reader is not built');
  } else {
    for (let i = 0; i < CASES.length; i += 1) {
      const c = CASES[i];
      // 🔴 INCLUDING `declared_but_not_reached`. The column comes from the DECLARATION, so
      //    it is drawn whether or not a value arrived — that is what keeps 「없음」 and
      //    「안 걸어봤음」 from being the same pixel.
      ok(`C2.${i} «${c.name}» draws every declared name`,
        drawn[i].length === (c.declared_attributes || []).length,
        `drew ${JSON.stringify(drawn[i])} of ${JSON.stringify(c.declared_attributes)}`);
    }
  }
}

// ══ ④ VALUES — scored; THE CONFLICT COUNT — still PENDING BY NAME ═══════════════════════
// 🔴 Scoreable since 판정 130-C ㉡ put the column→source mapping in `derive.js:cellSource`.
//    Before that the mapping lived in `walk/main.js:renderTable` as ARITHMETIC over the name
//    list (`cols.slice(1, cols.length - 2 - qualNames.length)`), which nothing could import
//    and therefore nothing could redden.
console.log('\n[4] values, and the conflict count');
for (const c of CASES) {
  const node = nodeFor(c);
  for (const name of c.declared_attributes || []) {
    const want = Object.prototype.hasOwnProperty.call(node.attributes, name)
      ? node.attributes[name] : undefined;
    const got = derive.cellSource({ kind: 'attribute', key: name }, node, {});
    // ⚠️ `declared_but_not_reached` is the case that matters here: the expectation is
    //    `undefined`, NOT an empty string and NOT 0. The client turns it into an empty cell
    //    one layer up; deciding it here would make 「never reached」 unrecoverable.
    eq(`D1 «${c.name}» reads ${name}`, want, got);
  }
  // 🔴 AND IT READS THE ATTRIBUTE MAP, NOT THE IDENTITY ONE. A node's keys never answer for
  //    an attribute — that swap is what the removed arithmetic effectively did, and it is
  //    invisible because its result (an empty cell) is also a legitimate answer.
  for (const name of c.declared_attributes || []) {
    eq(`D2 «${c.name}» does not find ${name} among the keys`, undefined,
      derive.cellSource({ kind: 'key', key: name }, node, {}));
  }
}
// 🔴 THE COUNT, AND THE PAIR THAT DECIDES IT. `two_differing_values` must draw its number and
//    `same_value_at_two_times` must draw nothing — the two cases the shared file exists to keep
//    apart. A client that counted ARRIVALS instead of differing values would draw a number on
//    both, and every server test would stay green.
for (const c of CASES) {
  const want = c.expect.attribute_conflicts > 0 ? c.expect.attribute_conflicts : undefined;
  eq(`E «${c.name}» draws ${want === undefined ? 'nothing' : want}`, want,
    derive.cellSource({ kind: 'conflicts' }, nodeFor(c), {}));
}
// ⚠️ Zero and never-reached are BOTH silent here, which is the ruling (0 이면 안 그림). What
//    keeps them apart is the attribute cells one column to the left, and D1 above is that.
{
  const reached = CASES.find((c) => c.name === 'attributes_present');
  const never = CASES.find((c) => c.name === 'declared_but_not_reached');
  const name = (reached.declared_attributes || [])[0];
  ok('E2 agreed-on and never-reached differ in the row, though not in this cell',
    derive.cellSource({ kind: 'attribute', key: name }, nodeFor(reached), {}) !== undefined
    && derive.cellSource({ kind: 'attribute', key: name }, nodeFor(never), {}) === undefined);
}

console.log(`\n${failures.length === 0 ? 'OK' : 'DIVERGED'}: ${pass} passed, `
  + `${failures.length} failed, ${pending.length} pending`);
if (pending.length) {
  console.log('PENDING (named, not passed):');
  for (const p of pending) console.log(`  - ${p}`);
}
process.exit(failures.length === 0 ? 0 : 1);
