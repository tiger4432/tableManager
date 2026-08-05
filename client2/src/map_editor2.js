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
import { createApiClient, ROUTES, RouteNotServedError } from './map2/api.js';

const DEV_CAPTURE_URL = '/map2_dev_reference.json';

// The decision unit is named by an enrichment rule, not assembled here. That rule declares
// `decision_key: [dt_eqp, product]`, which is why `params` carries those two fields and never
// a map id: wafers under one eqp+product were measured disagreeing with each other, so the
// evidence has to be pooled before it is scored.
const RULE = 'eqp_product_frame_attribution';
const MAP_TABLE = 'dt_map';

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
    loadTableSchema: (...a) => live.loadTableSchema(...a),
    loadBinding: (...a) => live.loadBinding(...a),

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
  app.setLoader((decision, question) => api.loadReferenceView({
    rule: RULE,
    mapTable: question.mapTable || MAP_TABLE,
    params: decision.__key || { dt_eqp: decision.eqp, product: decision.product },
    xCol: question.columns.x,
    yCol: question.columns.y,
    valCol: question.columns.val,
    reference: question.reference || undefined,
    includeCells: true,
  }));

  // ── THE SET-UP ROW'S THREE SOURCES ──────────────────────────────────────────
  // Which tables can be asked about, which columns each has, and which references resolve.
  // Two of the three come from ROUTES THAT ALREADY EXIST and are already consumed elsewhere in
  // this client; only the resolvable-reference list has no route, and that one degrades to
  // `기준 없음` -- which is the commonest correct answer anyway, not an error state.
  buildCatalog(api).then(({ catalog, degraded }) => {
    app.setCatalog(catalog);
    if (degraded.length > 0) console.log('[map2] catalog degraded:', degraded.join(', '));
    app.render();
  }).catch(err => console.log('[map2] catalog unavailable:', err.message));

  // The rule's DECLARED target fields. Read for the WRITE's destination, never for a picker.
  api.loadRules()
    .then(res => {
      const rule = ((res && res.rules) || []).find(r => r && r.name === RULE) || null;
      app.setContext({
        rule: RULE,
        targetFields: (rule && rule.target_fields) || [],
        confirmedBy: CURRENT_USER,
        // The decision key's COLUMNS come from the rule, so a rule that renames them does not
        // need an edit here. `{dt_eqp, product}` is not spelled in this file twice.
        // The served dict wins; `keyFrom` is only the fallback for a decision that
        // did not come from a worklist row.
        toDecisionKey: (d) => (d && d.__key) || keyFrom(rule, d),
      });
    })
    .catch(err => console.log('[map2] enrichment rules unavailable:', err.message));

  // 🔴 THE WORKLIST LOADER IS ONE SEAM AND ONE LINE. `ROUTES.worklist` is null, so the live
  //    call refuses with `RouteNotServedError` and ONLY that class falls through to the stub.
  //    Every other failure stays visible, for the same reason the reference view's fallback was
  //    narrowed: a catch-all made a broken request look like a working screen for hours.
  app.setWorklistLoader((query) => api.loadWorklist(query).catch(err => {
    if (!(err instanceof RouteNotServedError)) throw err;
    return stubWorklist(query);
  }));
  app.refreshWorklist();

  app.render();
  // Handy for the dev console and for the browser check; not read by any module.
  window.__map2 = app;
}

/**
 * What the set-up row may offer. Assembled from EXISTING routes:
 *   · tables   -- the map tables this screen can ask about
 *   · columns  -- `/tables/{t}/schema`, the route admin already consumes
 *   · binding  -- `/api/maps/paint-rules?table=`, which serves the RESOLVED declaration from
 *                 `map_overlay_config.json` together with its provenance
 * The reference list has no route; it degrades to `기준 없음` alone, which is the ordinary
 * state for the 320 maps that have no valid-die reference in the first place.
 */
async function buildCatalog(api) {
  const degraded = [];
  const tables = [{ table: MAP_TABLE, label: MAP_TABLE }];
  const columns = {};
  const columnTypes = {};
  const binding = {};
  const references = {};
  for (const t of tables) {
    try {
      const schema = await api.loadTableSchema(t.table);
      columns[t.table] = Array.isArray(schema && schema.columns) ? schema.columns : [];
      // The DECLARED types, carried through. The coordinate pickers offer declared numbers.
      columnTypes[t.table] = (schema && schema.column_types) || {};
    } catch (e) {
      degraded.push(`schema:${t.table}`);
      columns[t.table] = [];
      columnTypes[t.table] = {};
    }
    try {
      const rules = await api.loadBinding(t.table);
      const b = rules && rules.binding ? rules.binding : null;
      // Carried WITH its provenance, never flattened. `fallback_guess` is the server's own
      // marker for a binding a client must not render as a declaration.
      if (b && b.x && b.y) binding[t.table] = { x: b.x, y: b.y, val: b.val || null, source: b.source };
    } catch (e) {
      degraded.push(`binding:${t.table}`);
    }
    // No route serves "which references actually resolve". Offering the declared
    // `valid_die_ref` values would offer eight names that resolve zero times.
    references[t.table] = [];
    degraded.push(`references:${t.table}`);
  }
  return { catalog: { tables, columns, columnTypes, binding, references }, degraded };
}

/** The decision key's COLUMNS come from the rule, so this file spells them once. */
function keyFrom(rule, decision) {
  const cols = (rule && rule.decision_key) || [];
  const d = decision || {};
  if (cols.length === 2) return { [cols[0]]: d.eqp, [cols[1]]: d.product };
  return { dt_eqp: d.eqp, product: d.product };
}

/**
 * THE STUB, BEHIND ONE SEAM. Reached only when `ROUTES.worklist` refuses by name, and it says
 * so on screen rather than passing itself off as served data. Swapping it out is one line in
 * `ROUTES` -- nothing else in the program knows this exists.
 */
function stubWorklist(query) {
  const seed = { rows: [], total: null, remaining: null, unscorable: null };
  const status = document.getElementById('me2-worklist-meta');
  if (status) status.textContent = '작업 목록 · 미상';
  return Promise.resolve(seed);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
