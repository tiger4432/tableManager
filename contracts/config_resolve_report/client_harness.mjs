/**
 * CONFIG RESOLVE REPORT — the CLIENT half, scored against vectors.json.
 *
 * Read-only: it never writes to client2/.
 *
 *   node contracts/config_resolve_report/client_harness.mjs
 *   node contracts/config_resolve_report/client_harness.mjs --json
 *
 * Exit codes: 0 = client matches the contract | 1 = divergence(s) | 2 = harness failure.
 *
 * THE STANDING PROHIBITION, WHICH NEEDS NO RENDERER
 *   This half was written before the client renderer existed and still runs first, because
 *   the invariant with the sharpest teeth does not need the feature to be there:
 *
 *     INV-F9-7 — the client must contain NONE of the reason words as source literals.
 *
 *   The server names the reason and composes the sentence; the client renders `detail`.
 *   A client that writes `not_declared` down has, at that moment, acquired its own opinion
 *   about what counts as ineffective — and the two sides can then disagree while every
 *   server test stays green. That is the hardcoded-copy class U6 deleted six instances of,
 *   and grep catches it from the first line of client code onward.
 *
 *   So this harness is USEFUL BEFORE the feature exists and stays useful after: it is a
 *   standing prohibition, not a mirror of an implementation.
 *
 * THE POSITIVE HALF (INV-F9-4, client side) — LANDED 2026-07-31
 *   It used to be reported BY NAME as pending, because "the rendered text equals the server's
 *   `detail`" needs a renderer to exist. It does now, and it is scored rather than grepped:
 *   `client2/src/config_resolve_view.js` is a DOM-free view model that tags every string it
 *   emits with its provenance, so this harness can import it, feed it a report built out of
 *   `vectors.json`, and check each one:
 *
 *     src 'server' — must exist VERBATIM as a string in the payload (and every `detail` in
 *                    the payload must come back exactly once: nothing dropped, nothing doubled)
 *     src 'value'  — must be exactly JSON.stringify of the payload value it echoes
 *     src 'chrome' — must come from the module's own frozen CHROME table, which is static and
 *                    therefore cannot contain a composed sentence about any declaration
 *     src 'count'  — an integer the client counted, spelled as itself
 *
 *   That is the whole prohibition, expressed positively: if the client ever writes its own
 *   sentence about a config's status, that string is in neither the payload nor CHROME.
 *
 *   If the view module is ever deleted, this half goes back to reporting PENDING by name
 *   rather than silently passing.
 */
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join, relative, sep } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const VECTORS_PATH = join(HERE, 'vectors.json');
const CLIENT_SRC = join(ROOT, 'client2', 'src');

const asJson = process.argv.includes('--json');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

if (!existsSync(VECTORS_PATH)) die(`vectors.json is missing at ${VECTORS_PATH}`);
const vectors = JSON.parse(readFileSync(VECTORS_PATH, 'utf8'));

const forbidden = vectors.forbidden_client_literals?.literals;
if (!Array.isArray(forbidden) || forbidden.length === 0) {
  die('vectors.json declares no forbidden_client_literals ― the one check this harness '
    + 'can run today would silently pass over nothing.');
}
const allowPaths = new Set(vectors.forbidden_client_literals.allow_paths || []);

if (!existsSync(CLIENT_SRC)) die(`client source tree not found at ${CLIENT_SRC}`);

/** Every .js/.mjs/.html/.css under client2/src. */
function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else if (/\.(js|mjs|html|css)$/.test(name)) out.push(full);
  }
  return out;
}

const files = walk(CLIENT_SRC);
if (files.length === 0) die(`no client source files under ${CLIENT_SRC}`);

const divergences = [];
const pending = [];

// --- INV-F9-7: the reason words are SERVER words ------------------------------------
for (const file of files) {
  const rel = relative(ROOT, file).split(sep).join('/');
  if (allowPaths.has(rel)) continue;
  const text = readFileSync(file, 'utf8');
  const lines = text.split('\n');
  for (const word of forbidden) {
    lines.forEach((line, i) => {
      if (!line.includes(word)) return;
      divergences.push({
        invariant: 'INV-F9-7',
        file: rel,
        line: i + 1,
        detail: `client source contains the server reason word '${word}'. The server names `
          + `the reason and composes the sentence; the client renders \`detail\`. Iterate `
          + `\`vocabulary.reasons\` from the response instead of writing the word down.`,
        excerpt: line.trim().slice(0, 160),
      });
    });
  }
}

// --- the positive half ---------------------------------------------------------------
const rendererHints = files.filter((f) => {
  const t = readFileSync(f, 'utf8');
  return t.includes('/admin/config/resolve') || t.includes('configResolve');
});
if (rendererHints.length === 0) {
  pending.push({
    invariant: 'INV-F9-4 (client side)',
    detail: 'no client code consumes GET /admin/config/resolve yet, so "the rendered text '
      + 'is the server\'s `detail`, verbatim" is UNSCORED. This blocks round completion, '
      + 'not the suite. When the renderer lands, extend this harness to assert it reads '
      + '`entry.detail` and never composes its own sentence per reason.',
  });
} else {
  const missing = rendererHints.filter(f => !readFileSync(f, 'utf8').includes('.detail'));
  for (const f of missing) {
    divergences.push({
      invariant: 'INV-F9-4 (client side)',
      file: relative(ROOT, f).split(sep).join('/'),
      line: 0,
      detail: 'this file consumes the resolve report but never reads `.detail`. The '
        + 'server composed a sentence for exactly this reason; ignoring it means the '
        + 'client is composing its own.',
    });
  }
}

// --- INV-F9-4: run the view model and score every string it emits ---------------------
const VIEW_MODULE = join(CLIENT_SRC, 'config_resolve_view.js');
const VIEW_REL = relative(ROOT, VIEW_MODULE).split(sep).join('/');
let checksRun = 0;

/** Marks a string as SERVER-OWNED. Any of these that comes back changed is a rewrite. */
const mark = (kind, id) => `<<${kind}:${id}>>`;

/** Every string value anywhere in a payload, and every `detail` value specifically. */
function scanPayload(node, strings = new Set(), details = []) {
  if (node === null || node === undefined) return { strings, details };
  if (Array.isArray(node)) {
    for (const child of node) scanPayload(child, strings, details);
    return { strings, details };
  }
  if (typeof node === 'string') { strings.add(node); return { strings, details }; }
  if (typeof node !== 'object') return { strings, details };
  for (const [key, value] of Object.entries(node)) {
    // KEYS COUNT AS PAYLOAD TEXT. Some of the server's words arrive as keys, not values -
    // `refused` on the dry-run is a {reason_word: count} map, and rendering that word is
    // rendering the server's vocabulary, not inventing one.
    strings.add(key);
    if (key === 'detail' && typeof value === 'string' && value !== '') details.push(value);
    scanPayload(value, strings, details);
  }
  return { strings, details };
}

/** The domain a case belongs to.
 *  ⚠️ A CASE WITHOUT `domain` IS AN ENRICHMENT CASE (S-180 ⓐ-0). The eight that
 *  existed when this axis was added carry no such field and stay byte-identical, so the
 *  default lives here rather than in the vector file. */
const DEFAULT_DOMAIN = 'enrichment';
const domainOf = c => c.domain || DEFAULT_DOMAIN;

// --- S-202: THE SETUP ORDER TRAVELS IN THE PAYLOAD -----------------------------------
//
// 🔴 WHY THE HARNESS BUILDS IT. `envelope.domain` has required `step` and `blocked_by` since
//    S-180, and this file was emitting neither -- so the client could have invented both and
//    the contract would have said nothing. That asymmetry is what S-202 closes: the payload
//    carries the order, and the view is scored against it.
//
// ⛔ AND IT IS NOT COPIED FROM THE SERVER'S LIST. The names here are MARKERS, so a view that
//    prints 「표」 because it wrote 「표」 down fails: the marker is the only string in the
//    payload, and a server-owned text carrier must be found in the payload verbatim.
// ⚠️ The step numbers and the `after` chain are the SHAPE the server documents (six steps,
//    each naming the one it follows); the domains are this file's own, so a domain rename on
//    the server cannot make this harness green by accident.
const SETUP_STEPS = [
  { step: 1, name: mark('step-name', 'catalog'), domain: 'catalog', after: null },
  { step: 2, name: mark('step-name', 'chain'), domain: 'chain', after: 1 },
  { step: 3, name: mark('step-name', 'enrichment'), domain: DEFAULT_DOMAIN, after: 1 },
  { step: 4, name: mark('step-name', 'virtual_join'), domain: 'virtual_join', after: 1 },
  { step: 5, name: mark('step-name', 'ledger'), domain: 'ledger', after: 1 },
  { step: 6, name: mark('step-name', 'walk'), domain: 'walk', after: 5 },
];
const STEP_OF = new Map(SETUP_STEPS.map((s) => [s.domain, s]));
// One blocked step in the fixture, because 「blocked」 and 「not blocked」 must both be drawn:
// a payload where nothing is blocked cannot tell a marker that never renders from one that
// renders correctly.
const BLOCKED_DOMAIN = 'walk';
const BLOCKED_BY = 5;

/** A report shaped like the route's response, populated from the vectors' own cases.
 *  🔴 ONE DOMAIN OBJECT PER NAMED DOMAIN, NEVER ONE HARDCODED. This emitted a single
 *  `domain: 'enrichment'` envelope holding every case, so a case belonging to another domain
 *  would have been scored as enrichment's - the mirror of the positional read the python
 *  harness carried. */
function domainFromVectors(name) {
  const populations = vectors.vocabulary.populations;
  const buckets = Object.fromEntries(populations.map(p => [p, []]));
  for (const c of vectors.cases) {
    if (domainOf(c) !== name) continue;
    const expect = c.expect || c.expect_any;
    if (!expect || !buckets[expect.population]) continue;
    const views = Object.values(c.rules || {}).flatMap(r => r.reference_views || []);
    buckets[expect.population].push({
      scope: expect.scope || 'rule',
      subject: c.id,
      detail: mark('entry-detail', c.id),
      reason: expect.reason === undefined ? null : expect.reason,
      warnings: expect.warnings || [],
      fields: {
        // The knob's presence is what tells the client this rule has a dry-run route.
        auto_confirm: true,
        reference_views: views.map((v, i) => ({
          label: mark('view-label', `${c.id}#${i}`),
          detail: mark('view-detail', `${c.id}#${i}`),
          warnings: expect.warnings || [],
          required_binds: v.binds || [],
          candidate_for: v.candidate_for || {},
          scope_narrow: false,
        })),
      },
    });
  }
  // ⚠️ SETTINGS BELONG TO THE DOMAIN THAT HAS THEM. `settings_cases` carry no domain
  // field, so they are enrichment's; emitting them under every domain rendered one detail
  // twice and the contract counted that as two chances to disagree.
  const settings = [];
  for (const sc of (name === DEFAULT_DOMAIN ? vectors.settings_cases || [] : [])) {
    for (const s of sc.expect || []) {
      settings.push({
        key: s.key,
        value: s.value,
        origin: s.origin,
        path: mark('settings-path', sc.id),
        declared: s.declared === undefined ? null : s.declared,
        detail: mark('setting-detail', `${sc.id}:${s.key}`),
      });
    }
  }
  return {
    domain: name,
    title: mark('domain-title', name),
    // ⚠️ A SOURCE MARKER IS PER DOMAIN, for the same reason the settings are: the enrichment
    // file names were emitted under every domain, and the contract read one sentence
    // rendered twice - which it counts as two chances to disagree.
    sources: name === DEFAULT_DOMAIN ? [
      { key: 'rules', path: mark('src-path', 'rules'), exists: true, status: 'ok',
        detail: mark('source-detail', 'rules') },
      { key: 'settings', path: mark('src-path', 'settings'), exists: false, status: 'ok',
        detail: mark('source-detail', 'settings') },
    ] : [
      { key: name, path: mark('src-path', name), exists: true, status: 'ok',
        detail: mark('source-detail', name) },
    ],
    settings,
    ...buckets,
    counts: Object.fromEntries(populations.map(p => [p, buckets[p].length])),
    // S-202. The two keys `envelope.domain` has required since S-180.
    step: (STEP_OF.get(name) || {}).step ?? null,
    blocked_by: name === BLOCKED_DOMAIN ? BLOCKED_BY : null,
  };
}

function reportFromVectors() {
  // The domains the CASES name, plus the stepped ones they do not -- a report that held only
  // enrichment could not show an order at all, and 「the six stand in order」 is the claim.
  const named = [...new Set(vectors.cases.map(domainOf))];
  const names = [...new Set([...named, ...SETUP_STEPS.map((s) => s.domain), 'notation'])];
  return {
    domains: names.map(domainFromVectors),
    // ⚠️ SPREAD, NOT REPLACED. `vectors.vocabulary` is the server's and this file does not
    //    edit the vector document; the order is ADDED beside it, which is what an additive
    //    envelope change looks like from the client side.
    vocabulary: { ...vectors.vocabulary, setup_steps: SETUP_STEPS },
  };
}

function scoreTexts(texts, payload, chromeSet, label) {
  const { strings, details } = scanPayload(payload);
  const rendered = texts.filter(t => t.src === 'server').map(t => t.text);
  for (const t of texts) {
    checksRun++;
    if (t.src === 'server') {
      if (!strings.has(t.text)) {
        divergences.push({
          invariant: 'INV-F9-4 (client side)', file: VIEW_REL, line: 0,
          detail: `${label}: the view emits "${t.text}" as server-owned text, but that exact `
            + `string is not in the payload. The client rendered something the server did not `
            + `say - that is the composed sentence this contract forbids.`,
        });
      }
    } else if (t.src === 'chrome') {
      if (!chromeSet.has(t.text)) {
        divergences.push({
          invariant: 'INV-F9-4 (client side)', file: VIEW_REL, line: 0,
          detail: `${label}: client-authored text "${t.text}" is not in the module's frozen `
            + `CHROME table. Client strings must be static structural labels, declared in one `
            + `place, so that no per-declaration sentence can hide among them.`,
        });
      }
    } else if (t.src === 'value') {
      if (JSON.stringify(t.raw) !== t.text) {
        divergences.push({
          invariant: 'INV-F9-4 (client side)', file: VIEW_REL, line: 0,
          detail: `${label}: value text "${t.text}" is not JSON.stringify of the payload value `
            + `it echoes (${JSON.stringify(t.raw)}). The operator must read their value back in `
            + `the syntax of the file they edited.`,
        });
      }
    } else if (t.src === 'count') {
      if (!Number.isInteger(t.value) || String(t.value) !== t.text) {
        divergences.push({
          invariant: 'INV-F9-5 (client side)', file: VIEW_REL, line: 0,
          detail: `${label}: count "${t.text}" does not spell its own integer (${t.value}).`,
        });
      }
    }
  }
  // Nothing dropped, nothing doubled: every sentence the server composed is rendered once.
  for (const detail of details) {
    checksRun++;
    const seen = rendered.filter(text => text === detail).length;
    if (seen !== 1) {
      divergences.push({
        invariant: 'INV-F9-4 (client side)', file: VIEW_REL, line: 0,
        detail: `${label}: the payload carries a \`detail\` that the view renders ${seen} `
          + `time(s), expected exactly 1: ${JSON.stringify(detail)}. A dropped sentence sends `
          + `the operator back to the daemon log; a doubled one is two chances to disagree.`,
      });
    }
  }
}

if (!existsSync(VIEW_MODULE)) {
  pending.push({
    invariant: 'INV-F9-4 (client side)',
    detail: `no view model at ${VIEW_REL}, so "the rendered text is the server's \`detail\`, `
      + `verbatim" cannot be executed - only grepped. If the renderer moved, point this `
      + `harness at it; scoring the DOM builder by substring is not the same check.`,
  });
} else {
  const view = await import(pathToFileURL(VIEW_MODULE).href);
  const chromeSet = new Set(view.CHROME_STRINGS);

  // The client's own words must not include the server's reason words (INV-F9-7, but for the
  // one table the grep above cannot reason about semantically).
  for (const text of chromeSet) {
    checksRun++;
    for (const word of forbidden) {
      if (text.includes(word)) {
        divergences.push({
          invariant: 'INV-F9-7', file: VIEW_REL, line: 0,
          detail: `CHROME entry "${text}" contains the server reason word '${word}'.`,
        });
      }
    }
  }

  const payload = reportFromVectors();
  scoreTexts(view.collectTexts(view.buildConfigResolveView(payload)), payload, chromeSet,
    'resolve report');

  // The dry-run route answers with the same discipline: one server-composed sentence.
  const dryRun = {
    rule: 'core_wafer_attribution', mode: 'dry-run', limit: 200,
    refused_reason: vectors.vocabulary.reasons[0],
    detail: mark('dry-run-detail', 'core_wafer_attribution'),
    queue_size: 12, keys_examined: 12, confirmed: 3, written_cells: 3,
    refused: { no_candidate: 7, ambiguous: 2 }, samples: [], truncated: false,
  };
  scoreTexts(view.collectTexts(view.buildDryRunView(dryRun)), dryRun, chromeSet, 'dry-run');

  // --- S-202 / C-87: the order on screen is the order in the payload -------------------
  const built = view.buildConfigResolveView(payload);
  const shown = built.domains.map((d) => d.name);
  const wantOrder = [
    ...SETUP_STEPS.map((s) => s.domain).filter((n) => shown.includes(n)),
    ...shown.filter((n) => !STEP_OF.has(n)),
  ];
  checksRun++;
  if (shown.join(',') !== wantOrder.join(',')) {
    divergences.push({
      invariant: 'INV-F9-8', file: VIEW_REL, line: 0,
      detail: `the report stands its domains as [${shown.join(', ')}], but the payload's `
        + `\`vocabulary.setup_steps\` says [${wantOrder.join(', ')}]. The order is the setup `
        + `order or it is nothing: a screen that lists them as they arrived teaches an order `
        + `the server did not state.`,
    });
  }
  for (const domain of built.domains) {
    const item = STEP_OF.get(domain.name);
    checksRun++;
    if (!item) {
      if (domain.step !== null || domain.stepName !== null || domain.unstepped !== true) {
        divergences.push({
          invariant: 'INV-F9-8', file: VIEW_REL, line: 0,
          detail: `domain '${domain.name}' has no step in the payload, but the view gave it `
            + `one (${JSON.stringify(domain.step)} / ${JSON.stringify(domain.stepName)}). `
            + `Absent is not step zero.`,
        });
      }
      continue;
    }
    if (!domain.step || domain.step.raw !== item.step) {
      divergences.push({
        invariant: 'INV-F9-8', file: VIEW_REL, line: 0,
        detail: `domain '${domain.name}' is drawn at step ${JSON.stringify(domain.step)}, `
          + `while the payload says ${item.step}.`,
      });
    }
    checksRun++;
    if (!domain.stepName || domain.stepName.text !== item.name) {
      divergences.push({
        invariant: 'INV-F9-8', file: VIEW_REL, line: 0,
        detail: `domain '${domain.name}' is named ${JSON.stringify(domain.stepName)} on `
          + `screen; the payload calls that step ${JSON.stringify(item.name)}. The step names `
          + `are the server's words -- a client that spells them owns a list it cannot keep.`,
      });
    }
  }
  const blocked = built.domains.find((d) => d.name === BLOCKED_DOMAIN);
  checksRun++;
  if (!blocked || !blocked.blockedBy || blocked.blockedBy.raw !== BLOCKED_BY) {
    divergences.push({
      invariant: 'INV-F9-8', file: VIEW_REL, line: 0,
      detail: `the blocked domain '${BLOCKED_DOMAIN}' should carry the number of the step it `
        + `waits on (${BLOCKED_BY}); the view carries `
        + `${JSON.stringify(blocked && blocked.blockedBy)}.`,
    });
  }
  const free = built.domains.find((d) => d.name !== BLOCKED_DOMAIN && STEP_OF.has(d.name));
  checksRun++;
  if (free && free.blockedBy !== null) {
    divergences.push({
      invariant: 'INV-F9-8', file: VIEW_REL, line: 0,
      detail: `domain '${free.name}' is not blocked in the payload, but the view drew a `
        + `blocked marker for it. A marker that is always there says nothing.`,
    });
  }
}

const result = {
  contract: 'config_resolve_report',
  scanned_files: files.length,
  forbidden_literals: forbidden,
  checks_run: checksRun,
  divergences,
  pending,
  ok: divergences.length === 0,
};

if (asJson) {
  console.log(JSON.stringify(result, null, 2));
} else {
  console.log(`config_resolve_report ― client half (${files.length} files scanned)`);
  for (const d of divergences) {
    console.log(`  DIVERGENCE ${d.invariant} ${d.file}:${d.line}`);
    console.log(`    ${d.detail}`);
    if (d.excerpt) console.log(`    > ${d.excerpt}`);
  }
  for (const p of pending) {
    console.log(`  PENDING ${p.invariant}`);
    console.log(`    ${p.detail}`);
  }
  console.log(divergences.length === 0
    ? `  OK ― no client source writes a server reason word down, and ${checksRun} rendered `
      + `string(s) trace back to the payload or to the client's frozen label table.`
    : `  ${divergences.length} divergence(s).`);
}

process.exit(divergences.length === 0 ? 0 : 1);
