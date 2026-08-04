#!/usr/bin/env node
//
// BLANK PREDICATE -- the CLIENT half, scored against contracts/blank_predicate/vectors.json.
//
//     node contracts/blank_predicate/client_harness.mjs [--json]
//
// Discovered and run by `client2/scripts/check_contracts.mjs`, which scans
// `contracts/*/client_harness.mjs`. A non-zero exit is the only verdict that runner reads.
//
// WHAT THE CLIENT OWNS ON THIS SEAM -- AND WHAT IT DOES NOT
//   The emptiness rule itself is entirely server-side: `crud.is_blank_value` and
//   `crud.blank_sql_condition`, scored by the pytest half. The client owns two smaller things,
//   and both are the kind that pass every existing test while breaking the seam.
//
//   1. NOT ASKING A QUESTION THE SERVER CANNOT ANSWER. Column filters in this grid are
//      SERVER-SIDE: `fetchData` ships `getFilterModel()` and `main.get_column_filter_condition`
//      returns no condition for a name it cannot resolve, so the page comes back UNFILTERED
//      while the client-side row model hides rows anyway -- visible rows look filtered and
//      `Matches:` does not. `grid.js` sets `filter: false` on virtual columns for exactly this
//      reason. Pinned here because a pin is what survives the next reader who thinks it was an
//      oversight.
//
//   2. NOT WRITING DOWN THE LABEL. `unresolved_label` is per-declaration server data. A client
//      literal lets the two sides disagree about what text a row even displays -- and then
//      "search for what you see" has two answers. This is the U6 hardcoded-copy class.
//
// EXIT CODES ARE THREE, NOT TWO
//   0  scored, no divergence      1  scored, DIVERGED      2  COULD NOT SCORE
//   2 is not a detail. `client2/tests/split_registry_harness.mjs` threw at its extraction step
//   for weeks after five symbols were renamed and reported nothing at all, because nothing
//   separated "passed" from "never ran".
//
// COMMENTS ARE STRIPPED BEFORE ANY LITERAL SEARCH.
//   `grid.js` discusses the unresolved label in prose three times. A raw grep would report
//   those as violations, and a duplication guard that cries wolf is a duplication guard that
//   gets deleted. The charter records this happening for real.

import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const JSON_OUT = process.argv.includes('--json');

const spec = JSON.parse(readFileSync(path.join(HERE, 'vectors.json'), 'utf8'));
const CLIENT = spec.client;

const results = [];
const check = (id, ok, expected, actual, why) =>
  results.push({ id, ok, expected, actual, why });

function die(msg) {
  console.error(`\nCOULD NOT SCORE: ${msg}\n`);
  process.exit(2);
}

// Printing and exiting are one function because a check may need to stop early WITH results
// (see C1's replacement arm). Two call sites, one format -- a second formatter is how the
// JSON output and the human output drift apart.
function report() {
  const failed = results.filter(r => !r.ok);
  if (JSON_OUT) {
    console.log(JSON.stringify({ contract: 'blank_predicate', results }, null, 2));
  } else {
    console.log('\n  contract blank_predicate -- CLIENT half');
    for (const r of results) {
      console.log(`  ${r.ok ? 'ok  ' : 'FAIL'} ${r.id}`);
      if (!r.ok) {
        console.log(`       expected: ${r.expected}`);
        console.log(`       actual  : ${r.actual}`);
        console.log(`       why     : ${r.why}`);
      }
    }
    console.log(`\n  ${results.length - failed.length}/${results.length} assertions, `
      + `${failed.length} divergence(s).`);
    console.log('  NOTE the emptiness rule itself is scored on the SERVER half:');
    console.log('       conda run -n assy_manager python -m pytest contracts/blank_predicate/ -q -rs');
    console.log('       A green run here does NOT mean the seam agrees.\n');
  }
  process.exit(failed.length ? 1 : 0);
}

function read(rel) {
  const p = path.join(ROOT, rel);
  if (!existsSync(p)) die(`${rel} does not exist. The contract points at a file that moved.`);
  return readFileSync(p, 'utf8');
}

// Strip `//` line comments and `/* */` blocks without touching string literals. Naive enough
// to be readable, careful enough not to eat a `//` inside a quoted string or a regex-looking
// slash pair -- which is the only way this could produce a FALSE PASS rather than a false fail.
function stripComments(src) {
  let out = '', i = 0, n = src.length;
  let inS = null, inBlock = false, inLine = false;
  while (i < n) {
    const c = src[i], d = src[i + 1];
    if (inLine) { if (c === '\n') { inLine = false; out += c; } i++; continue; }
    if (inBlock) { if (c === '*' && d === '/') { inBlock = false; i += 2; } else i++; continue; }
    if (inS) {
      out += c;
      if (c === '\\') { out += d ?? ''; i += 2; continue; }
      if (c === inS) inS = null;
      i++; continue;
    }
    if (c === '"' || c === "'" || c === '`') { inS = c; out += c; i++; continue; }
    if (c === '/' && d === '/') { inLine = true; i += 2; continue; }
    if (c === '/' && d === '*') { inBlock = true; i += 2; continue; }
    out += c; i++;
  }
  return out;
}

// ── Extraction: the declared symbols must still exist, BY NAME ──────────────────────────
//
// Anchored on names, never on position. The pin this replaced asked whether a literal appeared
// "within 4000 characters of the first `unresolved_label`", and that broke the moment the label
// moved to a different object -- reporting a divergence about proximity while the client was
// doing the RIGHT thing. Proximity is a property of the file layout, not of the code.
function extract(rel, fn) {
  const code = stripComments(read(rel));
  // Built by concatenation, NOT as a template literal: `\s` and `\b` are not valid template
  // escapes, so a template silently degrades `\s` to `s` and `\b` to a backspace character --
  // a regex that compiles, never matches, and reports "symbol renamed" about code that is
  // fine. Cost me a false exit 2 on this very file.
  const re = new RegExp('(?:export\\s+)?(?:function\\s+' + fn + '\\b|const\\s+' + fn + '\\s*=)');
  const m = re.exec(code);
  if (!m) {
    die(`${rel} no longer defines \`${fn}\`. Either it was renamed -- re-point vectors.json `
      + `\`client_symbols\` -- or the read path was rewritten. Both mean this harness is scoring `
      + `nothing, which must never be reported as green.`);
  }
  // Brace-match from the first `{` after the declaration, so the extracted body is the whole
  // function and not a fixed-size window.
  let i = code.indexOf('{', m.index), depth = 0;
  for (let j = i; j < code.length; j++) {
    if (code[j] === '{') depth++;
    else if (code[j] === '}' && --depth === 0) return code.slice(i, j + 1);
  }
  die(`${rel}: could not brace-match the body of \`${fn}\`.`);
}

const SYMS = CLIENT.client_symbols;
for (const [role, meta] of Object.entries(SYMS)) {
  if (role === '$comment') continue;
  extract(meta.file, meta.fn);           // dies with exit 2 if the symbol moved
}

const FB = CLIENT.filter_behaviour;
const BUILDER = extract(SYMS.column_builder.file, SYMS.column_builder.fn);
const FILTER_DEF = extract(SYMS.filter_def_builder.file, SYMS.filter_def_builder.fn);

// ── C2: no client literal for the unresolved label, in the read path ────────────────────
//
// UNCHANGED by the 2026-07-31 re-point, and it must stay that way: where the label is READ
// FROM moved (`vc` -> the announcement entry), but "never write it down" did not move at all.
// It is the one assertion here that survived the round untouched, and it is the U6 class --
// a client that knows the word can decide for itself what it means.
{
  const { literals, scope } = CLIENT.forbidden_client_literals;
  const offences = [];
  for (const rel of scope) {
    const code = stripComments(read(rel));
    for (const lit of literals) {
      let idx = code.indexOf(lit);
      while (idx >= 0) {
        offences.push(`${rel}:${code.slice(0, idx).split('\n').length} contains the literal `
          + `(outside comments)`);
        idx = code.indexOf(lit, idx + lit.length);
      }
    }
  }
  check('C2-no-label-literal', offences.length === 0,
    'no forbidden literal in the scoped read path',
    offences.length ? offences.join('; ') : 'none',
    'a client that writes the label down can disagree with the server about what a row '
    + 'displays -- and then "search for what you see" has two answers. U6 deleted six of these.');
}

// ── C1: filter behaviour is keyed off the ANNOUNCEMENT ──────────────────────────────────
{
  // Every place the builder decides a filter must consult `joinResolvedColumn`. Counting
  // occurrences rather than testing for one: BOTH column paths (virtual_only AND collide)
  // have to consult it, and a single call would mean one of them was forgotten.
  const calls = (BUILDER.match(new RegExp(FB.keyed_off + '\\s*\\(', 'g')) || []).length;
  const wanted = FB.paths_that_must_consult_the_announcement.length;
  check('C1-filter-keyed-off-announcement', calls >= wanted,
    `${SYMS.column_builder.fn} consults \`${FB.keyed_off}\` on all ${wanted} paths `
    + `(${FB.paths_that_must_consult_the_announcement.map(p => p.path).join(', ')})`,
    `${calls} call(s)`,
    'the announcement is the server saying "I can resolve and filter this name". Deciding it '
    + 'client-side is how the two sides come to disagree about which columns are filterable.');
}

// ── C1b: and NOT off `isVirtualColumn` ──────────────────────────────────────────────────
{
  // The forbidden key may legitimately appear in the builder for OTHER reasons; what it may
  // not do is sit in a filter decision. Scored as: no line mentioning it also mentions
  // `filter`. Line-scoped rather than file-scoped so the paste/clear guards that legitimately
  // use it are not reported -- a guard that cries wolf gets deleted.
  const bad = BUILDER.split('\n')
    .map((l, i) => ({ l, i }))
    .filter(({ l }) => l.includes(FB.forbidden_key) && /\bfilter\b/i.test(l))
    .map(({ l, i }) => `line ${i + 1} of ${SYMS.column_builder.fn}: ${l.trim().slice(0, 80)}`);
  check('C1b-not-keyed-off-isVirtualColumn', bad.length === 0,
    `no filter decision keys off \`${FB.forbidden_key}\``,
    bad.length ? bad.join('; ') : 'none',
    FB.$why_forbidden);
}

// ── C1c: the absent-announcement fallback survives ──────────────────────────────────────
{
  // SCOPED TO THE ELSE-ARM OF THE ANNOUNCEMENT TERNARY, not to the file.
  // The first version of this pin asked whether `filter: false` appeared ANYWHERE in the
  // builder -- and a `filter: false` on an unrelated column def satisfied it, so deleting the
  // actual fallback was NOT caught (measured: fault F2, exit 0). A pin that a coincidence can
  // satisfy is not a pin.
  const norm = BUILDER.replace(/\s+/g, ' ');
  const want = FB.absent_announcement_fallback.replace(/\s+/g, ' ');
  // The ternary's `:` is the first one at BRACKET DEPTH ZERO after the `?`. Neither
  // `lastIndexOf(':')` nor `indexOf(':')` finds it: the true-arm and the else-arm are both
  // object literals full of `key:` colons, so the naive scans land inside one of them and
  // compare the wrong text (the first cut of this pin reported `: baseTooltip }` and went red
  // against a perfectly correct client).
  const tern = new RegExp('resolvedEntry\\s*\\?([\\s\\S]{0,400}?);').exec(norm);
  let elseArm = '';
  if (tern) {
    const arms = tern[1];
    let depth = 0;
    for (let i = 0; i < arms.length; i++) {
      const ch = arms[i];
      if ('{(['.includes(ch)) depth++;
      else if ('})]'.includes(ch)) depth--;
      else if (ch === ':' && depth === 0) { elseArm = arms.slice(i + 1); break; }
    }
  }
  const has = elseArm.includes(want);
  check('C1c-pre-change-server-falls-back', has,
    `the else-arm of the announcement ternary is \`${want}\``,
    tern ? (has ? 'it is' : `it is \`${elseArm.trim().slice(0, 70)}\``)
         : 'the announcement ternary could not be located',
    FB.$why_fallback);
}

// ── C1d: blank/notBlank absent HERE, present on ordinary stored columns ─────────────────
{
  const FO = CLIENT.filter_options;
  const code = stripComments(read(SYMS.column_builder.file));
  const listM = new RegExp(FO.join_resolved_option_list + '\\s*=\\s*\\[([^\\]]*)\\]').exec(code);
  if (!listM) die(`${SYMS.column_builder.file}: could not find \`${FO.join_resolved_option_list}\``);
  const offered = listM[1];
  const leaked = FO.must_not_offer.filter(o => new RegExp(`['"\`]${o}['"\`]`).test(offered));
  check('C1d-join-resolved-offers-no-blank', leaked.length === 0,
    `${FO.join_resolved_option_list} omits ${FO.must_not_offer.join('/')}`,
    leaked.length ? `offers ${leaked.join(', ')}` : 'it does',
    FO.$why_absent);

  // The other direction. The ordinary stored def must NOT carry the restricted option list --
  // removing blank from the wrong set is the failure that already happened once today.
  const storedDef = BUILDER.slice(0, BUILDER.indexOf('currentVirtualColumns'));
  const restricted = storedDef.includes(FO.join_resolved_option_list);
  check('C1d2-stored-columns-keep-blank', !restricted,
    'the ordinary stored columnDef keeps AG-Grid\'s full option list',
    restricted ? `it applies ${FO.join_resolved_option_list}` : 'it does',
    FO.$why_present_on_stored);
}

// ── C1e: the announcement does not decide editability ───────────────────────────────────
{
  // `editable` must not be a function of the announcement lookup anywhere in the builder.
  const bad = BUILDER.split('\n')
    .filter(l => /editable\s*:/.test(l) && l.includes(FB.keyed_off))
    .map(l => l.trim().slice(0, 80));
  check('C1e-announcement-does-not-decide-editability', bad.length === 0,
    'no `editable:` is computed from the announcement -- a collide column stays editable',
    bad.length ? bad.join('; ') : 'none',
    CLIENT.editability.$why);
}

// ── C1f: the label reaching the filter def is read off the SERVER ENTRY ─────────────────
{
  const LS = CLIENT.label_source;
  // BOTH directions. `includes` alone was satisfied by the `typeof entry.unresolved_label`
  // guard while the VALUE had been replaced by a literal (measured: fault F5 slipped past it
  // and only C2 caught the hardcode). So: the entry read must be present AND no OTHER object
  // may supply an `unresolved_label` here -- `vc.unresolved_label` is the convenient wrong
  // read, and it is wrong because `virtual_columns` omits every `collide` column.
  const reads = FILTER_DEF.includes(LS.read_from);
  const others = [...new Set(
    (FILTER_DEF.match(/([A-Za-z_$][\w$]*)\.unresolved_label/g) || [])
      .filter(m => m !== LS.read_from))];
  check('C1f-label-from-the-server-entry', reads && others.length === 0,
    `${LS.scored_in} takes the label from \`${LS.read_from}\` and from nothing else`,
    !reads ? `it does not read \`${LS.read_from}\``
           : `it also reads ${others.join(', ')}`,
    LS.$why);
}

// ── C3: the numeric display guard still refuses to coerce ───────────────────────────────
{
  // `numericDisplayValue` must leave a non-numeric value ALONE. A `number` virtual column
  // genuinely carries the label on unresolved rows, and `Number('...')` is NaN -- coercing
  // would put NaN or 0 on screen where the server said "unresolved". Same class as the
  // charter's `v || dflt` warning: `''` and `null` both coerce to 0.
  const code = stripComments(read('client2/src/grid.js'));
  const m = code.match(/function\s+numericDisplayValue[\s\S]{0,600}?\n}/);
  if (!m) die('client2/src/grid.js: could not extract numericDisplayValue to score it');
  const body = m[0];
  const guardsEmpty = /!==\s*''/.test(body) && /!==\s*null/.test(body);
  const returnsOriginal = /return\s+val\s*;?\s*\n?}/.test(body) || /return\s+val\b/.test(body);
  check('C3-no-coercion', guardsEmpty && returnsOriginal,
    "empty/null are excluded up front and a non-numeric value is returned UNCHANGED",
    `guards_empty=${guardsEmpty} returns_original=${returnsOriginal}`,
    "Number('') and Number(null) are both 0, so without the guard an empty cell displays a "
    + 'zero -- the contract corpus keeps 0 and "" apart precisely because this is where they '
    + 'get confused');
}

// ── C4: the `browser` column of browser_render.ladder, measured by a real JS engine ─────
//
// [Board item N9, 2026-08-04] The server half of this contract used to score the numeric
// virtual-join seam as SQL vs `crud.clean_str_value`, and the two agree -- while the GRID
// and the SEARCH disagreed for every |v| in a band nobody had written down. The payload
// carries a raw JSON number and nothing on the way to the screen calls `clean_str_value`;
// what the operator reads is whatever THIS engine prints. So the third column of the
// ladder is measured here, and the server half compares its own dialect against it.
//
// 🔴 This is a MEASUREMENT, not a re-typing. Recording a JS spelling in a JSON file and
// never running JS over it is how a contract acquires folklore: the number stops being a
// fact and becomes a comment that outranks the code.
{
  const BR = spec.browser_render;
  if (!BR || !Array.isArray(BR.ladder)) {
    die('vectors.json has no `browser_render.ladder` -- the N9 axis was removed, not scored.');
  }
  // The path a value actually takes: JSON number -> valueGetter (`numericDisplayValue`,
  // scored by C3 above, returns `Number(val)` for a `number` column) -> AG-Grid's default
  // renderer, which stringifies. `String(Number(v))` is that pipeline, spelled out.
  const wrong = BR.ladder
    .map(r => ({ r, got: String(Number(r.value)) }))
    .filter(({ r, got }) => got !== r.browser);
  check('C4-browser-spelling-is-measured-not-transcribed', wrong.length === 0,
    `all ${BR.ladder.length} ladder values print as recorded`,
    wrong.length
      ? wrong.map(({ r, got }) => `${r.value}: recorded ${r.browser}, this engine ${got}`).join('; ')
      : 'they do',
    'the recorded browser spelling is the expectation the SERVER half is scored against; if '
    + 'it drifts, the server half silently starts scoring the wrong endpoint again -- which '
    + 'is the whole of N9');

  // The band itself, computed HERE from the two recorded columns, so a `divergence` edited
  // without re-measuring is caught on this side too (the pytest half checks the same thing;
  // a boundary that only one half verifies is a boundary one commit can move).
  const measured = BR.ladder.filter(r => r.postgres !== r.browser).map(r => r.value);
  const recorded = BR.divergence.postgres_divergent;
  const same = measured.length === recorded.length
    && measured.every((v, i) => v === recorded[i]);
  check('C4b-divergence-band-matches-the-ladder', same,
    `postgres_divergent == the values where the ladder's two columns differ`,
    same ? 'it does' : `ladder says [${measured}], divergence says [${recorded}]`,
    'a recorded band that no longer follows from the recorded measurements is the shape a '
    + 'declared divergence takes just before it stops asserting anything');
}

report();
