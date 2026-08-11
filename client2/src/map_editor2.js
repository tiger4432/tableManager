// ═══════════════════════════════════════════════════════════════════════════════
// MAP EDITOR 2 -- PAGE ENTRY.
//
// This file is the Vite entry for `map_editor2.html`. It does three things and nothing else:
// pull in the design tokens, build the transport, and hand both to the composition root.
// All DOM knowledge lives in `map2/main.js`; all logic lives in the pure modules beside it.
//
// 🔴 THE LEGACY EDITOR IS NOT TOUCHED BY ANY OF THIS. `map_editor.html` / `src/map_editor.js`
//    keep running for their users. Map Editor 2 stands beside them until it can actually do
//    the job -- the old one dies when the new one aligns, not before.
//
// DEV CAPTURE FALLBACK. The reference-view route belongs to the server lane and may not exist
// yet. This entry ALWAYS tries the live route first; only if that route is absent does it fall
// back to a captured payload, and when it does, it says so on screen in the status line. A
// screen that quietly shows captured data as if it were live is worse than a screen with no
// data at all.
// ═══════════════════════════════════════════════════════════════════════════════

import { API_BASE, CURRENT_USER } from './config.js';
import { bootstrap } from './map2/main.js';
import { selectAlignmentRules, decisionKeyOf, declaredKeyColumns,
         decisionKeyRefusal } from './map2/view_model.js';
import { createApiClient, RouteNotServedError, REFERENCE_CATALOG_SERVED } from './map2/api.js';

const DEV_CAPTURE_URL = '/map2_dev_reference.json';

// The decision unit is named by an enrichment rule, not assembled here. The rule declares
// `decision_key`, which is why `params` carries THOSE columns and never a map id: wafers under
// one decision unit were measured disagreeing with each other, so the evidence has to be pooled
// before it is scored.
// 🔴 THE ARITY IS THE RULE'S, NOT THIS FILE'S. A sentence naming one deployment's two key
//    columns stood here, and it was not a description -- it was the assumption the composer at
//    the foot of this file acted on. `decisionKeyOf` reads the declaration at every arity;
//    nothing in this file names a decision-key column, in code or in prose.
// 🔴 NO RULE NAME AND NO TABLE NAME ARE WRITTEN DOWN IN THIS PROGRAM. They used to be, as two
//    consts here, and that is not a default -- it is an ASSUMPTION ABOUT SOMEONE ELSE'S
//    DATABASE. On a deployment with no rule by that name, or no table by that name, the first
//    request fails and the operator gets a blank page: the one outcome that tells them nothing
//    and tells us nothing. `map2/*.js` never contained a name; this file was the hole, and it
//    survived because it is the last place a reader looks.
//
//    Both now come from the server's own declarations, in this order:
//      1. rules   <- GET /enrichment/rules
//      2. tables  <- the map tables, discovered from each table's declared `map_key_columns`
//      3. tables  <- REPLACED by `selection.map_tables` once the worklist answers, which is
//                    the authoritative list and costs no extra round trip
//
//    ⚠️ STEP 3 CANNOT BE STEP 2. `/api/maps/alignment/worklist` requires BOTH `rule` AND
//       `map_table` (`server/main.py:4332-4334`), so its `selection.map_tables` cannot bootstrap
//       the first table -- it can only correct it. Step 2 therefore reads the same declaration
//       the server reads (`map_key_columns`, cf. `map_alignment.map_table_catalog`), which is a
//       declaration rather than a guess, and is discarded the moment step 3 answers.

function createResilientClient() {
  const live = createApiClient({ baseUrl: API_BASE });
  let usedCapture = false;

  async function capture() {
    const res = await fetch(DEV_CAPTURE_URL, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`dev capture ${DEV_CAPTURE_URL} -> ${res.status}`);
    usedCapture = true;
    return res.json();
  }

  return {
    counters: live.counters,
    get usedCapture() { return usedCapture; },
    loadWorklist: (...a) => live.loadWorklist(...a),
    loadAlignConfig: (...a) => live.loadAlignConfig(...a),
    // Straight through, no fallback: these three hit routes that EXIST, so a failure is a
    // failure and must stay visible rather than being papered over with a plausible answer.
    loadRules: (...a) => live.loadRules(...a),
    loadTables: (...a) => live.loadTables(...a),
    loadTableSchema: (...a) => live.loadTableSchema(...a),
    loadBinding: (...a) => live.loadBinding(...a),
    // Straight through too. A captured stand-in for "which floors resolve" would be the worst
    // possible fallback on this control: the operator would pick a floor that does not exist.
    loadReferenceCatalog: (...a) => live.loadReferenceCatalog(...a),

    /**
     * 🔴 THE `.catch(capture)` THAT USED TO BE ON THIS LINE WAS THE MORE DANGEROUS HALF OF
     *    TONIGHT'S BUG. It turned every failure into a screen full of plausible cells: a wrong
     *    request shape, a 500, a renamed route -- all of them landed in the captured file and
     *    the page looked alive. It hid this exact defect for hours; the request was still
     *    sending `{eqp, product}`, `loadReferenceView` rejected it before any network call
     *    happened, and nobody saw it because the fallback painted a wafer. A green-looking
     *    proxy standing in for a green claim.
     *
     *    Failures are now SORTED, because two different things were being treated as one:
     *      · ROUTE OR SHAPE FAILURE = a bug in this client (bad shape, 4xx, 5xx, absent
     *        route). No fallback. Re-thrown, logged whole, and named on screen.
     *      · NETWORK FAILURE = an outage. Only this class may fall back, and when it does the
     *        marker is set BY THE FALLBACK FIRING -- nothing on the live path writes it, so a
     *        live render cannot claim to be captured and a captured one cannot stay silent.
     */
    loadReferenceView: (req) => live.loadReferenceView(req).catch(err => {
      // Always logged, never discarded, whichever class it is.
      console.error('[map2] reference view failed:',
        err.status || '(no status)', err.message, err.detail || '');
      if (!isOutage(err)) throw err;
      return capture();
    }),
    confirmFrame: (...a) => live.confirmFrame(...a),
  };
}

/**
 * Which failure is this? The answer decides whether the screen may fall back at all.
 * Only a fetch-shaped error with NO status counts as an outage. Anything the server answered,
 * and anything this client refused to send, is a bug and must stay visible.
 */
function isOutage(err) {
  if (!err) return false;
  if (err instanceof RouteNotServedError) return false;  // our own contract, not the network
  if (Number.isFinite(err.status)) return false;         // the server answered; it is a bug
  if (err.name === 'AbortError') return false;
  return err instanceof TypeError
    || /fetch|network|ECONN|Failed to fetch/i.test(String(err && err.message));
}

function start() {
  const api = createResilientClient();
  const app = bootstrap({ document, api });

  if (app.missing.length > 0) {
    // Named out loud rather than thrown: a partially finished page must still render what it
    // can, and the operator (or the markup lane) needs the list, not a blank screen.
    console.log('[map2] markup does not expose:', app.missing.join(', '));
  }

  // The worklist panel's meta line is where an aggregate fact belongs. Short nominal Korean,
  // no clause: this is a label, not a sentence.
  // Thresholds come from server config and are never defaulted here. `ROUTES.config` is `null`
  // -- the route does not exist yet -- so the absence is named as an absence rather than
  // printed as the string "null", which is what this line used to put on screen.
  // 🔴 THE SCREEN ALREADY SAYS THIS ONCE. The verdict layer refuses to rank without thresholds
  //    and the view model renders that as `기준값 없음`, so writing a second copy into the
  //    worklist's meta line was two spellings of one fact -- and the renderer overwrites that
  //    node anyway. The reason goes to the console, where diagnosis lives.
  api.loadAlignConfig()
    .then(cfg => app.setConfig(cfg && cfg.align_scoring ? cfg.align_scoring : cfg))
    .catch(err => console.log('[map2] align config unavailable:', err.message));

  // 🔴 THE REQUEST SHAPE. `loadReferenceView` takes the UNIT, not a map: a rule name, the map
  //    table, and the decision key's values as `params`. The old `{eqp, product}` call was
  //    rejected by the transport before any network traffic happened, and the capture fallback
  //    swallowed the rejection -- which is why a broken request looked like a working screen.
  // THE PRIMITIVE TUPLE, straight through. The loader takes the question as an ARGUMENT rather
  // than reading it from anywhere: no module state, so a harness can call it twice with two
  // different questions, which is the whole reason `map2/` is importable instead of sliced.
  app.setLoader((decision, question) => {
    // 🔴 THE UNIT IS STATED OR THE REQUEST IS NOT MADE. A key short of a declared column comes
    //    back from the server as 「빠진 결정키」 -- a true statement about the payload and a
    //    misleading one about the cause, because the client is the one that never had the
    //    value. So the refusal is raised HERE, with the column named, and no request is sent.
    //    It goes to the console rather than to the set-up row's notice line: that line carries
    //    facts about the whole deployment (no rule, no table) and is not cleared per row, so a
    //    per-unit refusal parked there would keep accusing the NEXT row of it.
    const unit = decisionKeyOf(chosen.declaration, decision);
    if (!unit.key) {
      console.error('[map2]', decisionKeyRefusal(unit),
        '| declared:', unit.columns.join(', ') || '(none)',
        '| missing:', unit.missing.join(', ') || '(none)',
        '| decision:', decision);
      return Promise.reject(new Error(
        `decision key not stated for rule '${chosen.rule}': declared [${unit.columns.join(', ')}], `
        + `missing [${unit.missing.join(', ')}]. Refused here rather than sent -- a blank column `
        + 'returns as "under-filled", which describes the payload and not the cause.'));
    }
    return api.loadReferenceView({
      rule: chosen.rule,
      mapTable: question.mapTable,
      params: unit.key,
      xCol: question.columns.x,
      yCol: question.columns.y,
      valCol: question.columns.val,
      reference: question.reference || undefined,
      // 🔴 READ OFF THE QUESTION, NEVER SET HERE. The borrowed-geometry claim reaches the wire
      //    only because the operator clicked the control that put it on the question -- this
      //    file passes it through and has no opinion about it. A default written on this line
      //    would be the same defect as the rule and table names that used to live here: an
      //    assumption about somebody else's data, in the last place a reader looks.
      assumeReferenceGeometry: question.assumeReferenceGeometry === true,
      includeCells: true,
    });
  });

  // 🔴 THE SHELL IS DRAWN BEFORE ANY REQUEST IS MADE, AND EVERY FAILURE BELOW IS CAUGHT. No
  //    bootstrap step may leave the page blank: whatever breaks, the workbench, the selection
  //    row and a one-line reason still appear, and the WHOLE failure goes to the console.
  app.render();

  // 🔴 THE SIGNAL IS PASSED THROUGH, AND THAT IS WHAT MAKES SUPERSESSION POSSIBLE AT ALL. The
  //    shell aborts the previous worklist request when the set-up row asks a new question; a
  //    loader that dropped the second argument would leave the shell holding a controller that
  //    cancels nothing, and two answers to two different tables would race to the same list.
  app.setWorklistLoader((query, signal) => api.loadWorklist(query, signal));

  discover(api).then(found => {
    if (found.reason) app.setNotice(found.reason);
    // The offer, in the order the server declared it. Nothing here ranks or renames.
    app.setRules({
      options: [{ value: '', label: WORDS_PICK_RULE, selected: !found.declaration }].concat(
        found.rules.map(r => ({
          value: r.name,
          label: r.name,
          selected: !!found.declaration && r.name === found.declaration.name,
        }))),
      proposed: !!found.proposed,
    }, (name) => {
      const picked = found.rules.find(r => r.name === name) || null;
      // Picking BY HAND is a choice, so the proposal marker comes off.
      app.setRules({ options: null, proposed: false });
      // 🔴 AND THE REASON GOES WITH IT. `규칙 선택 필요` described the state BEFORE this pick;
      //    left standing it would tell the operator to choose a rule they just chose, which is
      //    the same class of defect as the silence it replaced -- a line that does not track
      //    what it describes. Clearing to `found.reason` rather than to `''` keeps the 0-rule
      //    case's line, which no pick can resolve.
      app.setNotice(picked ? '' : found.reason);
      adoptRule(app, api, picked);
    });
    // A single declared candidate is adopted so the screen is usable; it stays MARKED as a
    // proposal, and the write still refuses to rest on a proposed column pair beneath it.
    if (found.declaration) adoptRule(app, api, found.declaration);
  }).catch(err => {
    // The last resort. A rejection that reaches here would otherwise be an unhandled promise
    // and a blank screen, which is exactly the production symptom being chased.
    console.log('[map2] bootstrap failed:', err && err.stack ? err.stack : err);
    app.setNotice(WORDS_SETUP_FAILED);
  });

  app.render();
  // Handy for the dev console and for the browser check; not read by any module.
  window.__map2 = app;
}

// One-line reasons. Nominal register, and each names a DIFFERENT state: the rules route not
// answering at all, versus a rule found but nothing to align it against, versus the bootstrap
// itself failing. Collapsing them would tell the operator "empty" three times for three
// different repairs.
// 🔴 `정렬 규칙 없음` IS NO LONGER SPELLED HERE. It is one of the two adoption refusals and it
//    now arrives from `selectAlignmentRules`, WITH the counts that make it actionable -- how
//    many rules declared `alignment`, and that exactly one is required. A copy in this file
//    would be a second spelling of one fact, and the copy is the one that goes stale.
//    A FAILED ROUTE IS NOT AN ABSENT DECLARATION. Those two used to share `정렬 규칙 없음`,
//    which sent an administrator to `enrichment_rules.json` when the server had not answered.
const WORDS_RULES_UNREACHABLE = '규칙 조회 실패';
const WORDS_NO_TABLE = '맵 테이블 없음';
const WORDS_SETUP_FAILED = '초기 설정 실패';

/** The rule in force, filled by `discover`. Nothing else in this file names one. */
const chosen = { rule: null, declaration: null };

/** Shown when several rules are capable and none may be proposed. */
const WORDS_PICK_RULE = '규칙 선택';

/**
 * Adopt one rule: it declares what a unit IS, so everything downstream is rebuilt rather than
 * re-asked -- the catalog it can align against, and the worklist of its units.
 */
function adoptRule(app, api, declaration) {
  chosen.rule = declaration ? declaration.name : null;
  chosen.declaration = declaration;
  if (!declaration) return;
  app.setContext({
    rule: declaration.name,
    // The rule's DECLARED target fields. Read for the write's destination, never for a picker.
    targetFields: declaration.target_fields || [],
    confirmedBy: CURRENT_USER,
    // 🔴 THE DECLARED COLUMNS TRAVEL WITH THE SEAM, so the shell can NAME what a refused write
    //    was short of instead of posting a blank key and relaying the server's `빠진 결정키`.
    //    An array here means "wired"; the shell's default is `null`, which means "no page entry
    //    has said" -- a different state, and one a harness driving `bootstrap` bare is in.
    //    🔴 THE SAME CLEANED LIST THE COMPOSER READS, not `declaration.decision_key` raw. The
    //       shell computes what a refused write was short of by comparing this against the
    //       composed dict, so two spellings of "the declared columns" would disagree on exactly
    //       the malformed declarations where the disagreement matters -- and a non-array raw
    //       value would fall through `setContext`'s guard and leave the write UNGUARDED.
    decisionKeyColumns: declaredKeyColumns(declaration),
    toDecisionKey: (d) => decisionKeyOf(declaration, d).key,
  });
  buildCatalog(api, declaration).then(built => {
    app.setCatalog(built.catalog);
    if (built.catalog.tables.length === 0) app.setNotice(WORDS_NO_TABLE);
    app.render();
    // Now the worklist can be asked, and its `selection` corrects the bootstrap table list.
    app.refreshWorklist();
  }).catch(err => {
    console.log('[map2] catalog failed:', err && err.stack ? err.stack : err);
    app.setNotice(WORDS_SETUP_FAILED);
  });
}

/**
 * WHAT THIS DEPLOYMENT ACTUALLY HAS. Every answer is a server declaration; nothing here is a
 * name this program knows in advance, and every step degrades to a stated reason rather than a
 * throw.
 *
 * 🔴 A RULE DECLARES ITSELF ALIGNMENT-CAPABLE: `"alignment": true` in `enrichment_rules.json`,
 *    served through `GET /enrichment/rules`. ABSENCE MEANS NOT CAPABLE -- a fact, not a
 *    default: an unmarked rule has never been claimed to align anything. So there is no
 *    fallback to "offer everything" when nothing is marked. An empty offer is the honest
 *    answer, and it lets the operator SEE that the config is missing a declaration instead of
 *    being handed a rule that cannot work.
 *
 *    `=== true` STRICTLY, matching `map_push_ok` (`server/main.py:2019`, client `=== true`).
 *    A config typo -- the string "true", or 1 -- must not unlock a capability.
 *
 *    This replaces picking `rules[0]`, which is exactly how `dt_job_lot_slot_attribution` --
 *    the lot/slot rule, which aligns nothing -- came to be proposed on the live screen.
 */
async function discover(api) {
  let rules = [];
  try {
    const res = await api.loadRules();
    rules = Array.isArray(res && res.rules) ? res.rules : [];
  } catch (e) {
    console.log('[map2] enrichment rules unavailable:', e && e.message);
    return { rules: [], declaration: null, reason: WORDS_RULES_UNREACHABLE };
  }

  // The predicate lives in a pure module so it is scored by importing, not by driving a page.
  // 🔴 AND SO DOES THE REASON. `picked.reason` is empty ONLY when exactly one rule declared
  //    `alignment` -- the case where a rule is adopted and the worklist is about to be asked.
  //    Every other case returns a line, because `adoptRule` returns before `refreshWorklist()`
  //    and no request is ever issued: an unasked worklist and a slow one look identical, and
  //    the operator has been reading the first as the second.
  const picked = selectAlignmentRules(rules);
  if (picked.capable === 0) {
    console.log('[map2] no rule declares `alignment: true`; nothing can be aligned. '
      + `Declared rules: ${rules.map(r => r && r.name).join(', ') || '(none)'}`);
    return { rules: [], declaration: null, reason: picked.reason };
  }
  if (!picked.proposed) {
    console.log(`[map2] ${picked.capable} alignment-capable rules; offering, proposing none: `
      + picked.rules.map(r => r.name).join(', ')
      + '. No worklist request is made until one is picked -- exactly one is required.');
  }
  return { rules: picked.rules, declaration: picked.declaration,
           proposed: picked.proposed, reason: picked.reason };
}

/**
 * What the set-up row may offer, assembled from EXISTING routes:
 *   · tables   -- discovered: a table is a MAP table when its schema declares `map_key_columns`
 *   · columns  -- `/tables/{t}/schema`, the route admin already consumes
 *   · binding  -- `/api/maps/paint-rules?table=`, which serves the RESOLVED declaration from
 *                 `map_overlay_config.json` together with its provenance
 *   · references -- `/api/maps/alignment/references`, WHICH FLOORS ACTUALLY RESOLVE
 *
 * 🔴 THE REFERENCE LIST IS ASKED ONCE, FOR THE WHOLE DEPLOYMENT, AND NOT PER TABLE. The server
 *    does not narrow it by map table (`map_alignment.resolve_reference_catalog`), so one call
 *    answers for every table in the loop below; asking per table would be N requests for N
 *    copies of one answer. It is also started BEFORE the loop and awaited after it, so it costs
 *    no wall clock against the switchover bar.
 *
 * 🔴 AND THE CALL CARRIES NO RULE. That is the point of the standalone route: the list used to
 *    ride on `/worklist`, which requires both `rule` and `map_table`, so it could not be asked
 *    for at all without one.
 *
 *    ⚠️ ONE GATE IS STILL IN FRONT OF IT, AND IT IS NOT THIS ROUTE'S. `buildCatalog` is reached
 *       only from `adoptRule`, so a deployment where NO rule declares `alignment: true` never
 *       gets here and the picker stays empty -- measured on the dev box today, whose two
 *       declared rules are both unmarked. That gate is deliberate and is NOT removed here:
 *       without a rule `chosen.rule` is null, `loadReferenceView` refuses by construction, and
 *       a set-up row that filled in anyway would be a control that cannot ask what it offers.
 *       The honest screen there says `정렬 규칙 없음`. Naming the gate rather than papering over
 *       it, because "the route is reachable without a rule" and "the picker fills without a
 *       rule" are two different claims and only the first one is true.
 */
async function buildCatalog(api, declaration) {
  const degraded = [];
  const columns = {};
  const columnTypes = {};
  const binding = {};
  const references = {};

  // Started first, awaited last. Nothing in the table loop depends on it.
  const refCatalog = api.loadReferenceCatalog().then(cat => {
    // 🔴 ONE LINE ON SCREEN, THE WHOLE RECORD HERE. The picker shows one line per floor; the
    //    server's accounting for what it examined and threw away is diagnosis, and diagnosis
    //    lives in the console. A short list with `rejected > 0` is a DIFFERENT fact from a
    //    short list with nothing rejected, and only this line can tell them apart.
    console.log('[map2] reference catalog:', cat);
    return cat;
  }).catch(err => {
    console.log('[map2] reference catalog unavailable:', err && err.message);
    return null;
  });

  let names = [];
  try {
    const res = await api.loadTables();
    names = Array.isArray(res && res.tables) ? res.tables : [];
  } catch (e) {
    degraded.push('tables');
    console.log('[map2] table list unavailable:', e && e.message);
  }

  const tables = [];
  for (const name of names) {
    let schema = null;
    try {
      schema = await api.loadTableSchema(name);
    } catch (e) {
      degraded.push(`schema:${name}`);
      continue;
    }
    // THE DECLARATION THAT MAKES A TABLE A MAP TABLE. Same one the server reads.
    const keyCols = (schema && schema.map_key_columns) || [];
    if (!Array.isArray(keyCols) || keyCols.length === 0) continue;
    tables.push({ table: name, label: name });
    columns[name] = Array.isArray(schema.columns) ? schema.columns : [];
    columnTypes[name] = schema.column_types || {};
    try {
      const rules = await api.loadBinding(name);
      const b = rules && rules.binding ? rules.binding : null;
      // Carried WITH its provenance, never flattened. `fallback_guess` is the server's own
      // marker for a binding a client must not render as a declaration.
      if (b && b.x && b.y) binding[name] = { x: b.x, y: b.y, val: b.val || null, source: b.source };
    } catch (e) {
      degraded.push(`binding:${name}`);
    }
  }

  // 🔴 THE `references:<table>` MARKER IS GONE, AND ONLY THAT ONE. It was written
  //    unconditionally, so it said "degraded" about a list that is now real -- a marker that
  //    lies in the other direction is worse than none, because the next reader trusts it. What
  //    remains is a marker by FACT: the route answering is the ordinary case, and the route
  //    failing is a genuine degradation, named once rather than once per table.
  const cat = await refCatalog;
  if (cat === null) {
    degraded.push('references');
  } else if (cat.state !== REFERENCE_CATALOG_SERVED) {
    // The server looked and could not answer -- its own word for it, not a second spelling.
    degraded.push('references');
    console.log('[map2] reference catalog not served:', cat.reason || '(no reason given)');
  }
  // The SAME list for every map table: the server does not narrow it, and neither may this.
  // An empty list is the ordinary `기준 없음` state, not an error -- see `view_model`, which
  // always carries 기준 없음 as a real first option beside whatever this holds.
  const refItems = cat ? cat.items : [];
  for (const t of tables) references[t.table] = refItems;

  if (tables.length === 0) {
    console.log('[map2] no table declares map_key_columns; there is nothing to align. '
      + `Rule '${declaration && declaration.name}' has source_table `
      + `'${declaration && declaration.source_table}'.`);
  }
  if (degraded.length > 0) console.log('[map2] catalog degraded:', degraded.join(', '));
  return { catalog: { tables, columns, columnTypes, binding, references }, degraded };
}

// 🔴 THE DECISION-KEY FALLBACK THAT STOOD HERE IS GONE, NOT MOVED-AND-KEPT. It honoured the
//    rule's declared columns at arity 2 and emitted a HARDCODED TWO-COLUMN PAIR at every other
//    arity, so a rule declaring a SINGLE column could never be confirmed on any deployment --
//    not a regression, a feature that never shipped working. Its replacement is `decisionKeyOf`
//    in `map2/view_model.js`: pure, arity-agnostic, importable, and it REFUSES rather than
//    filling a declared column with a blank.
//
//    THIS FILE NOW NAMES NO DECISION-KEY COLUMN AT ALL, IN CODE OR IN PROSE -- which is the
//    property, not the deletion. `map_editor2_question_harness.mjs` section L holds it that way,
//    including the prose: the header of this file used to state one rule's key columns as if
//    they were universal, which is the same assumption written in a place nobody greps.

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
