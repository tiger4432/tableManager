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

import { API_BASE } from './config.js';
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
    console.warn('[map2] markup does not expose:', app.missing.join(', '));
  }

  // The worklist panel's meta line is where an aggregate fact belongs. Short nominal Korean,
  // no clause: this is a label, not a sentence.
  const status = document.getElementById('me2-worklist-meta');
  const say = (msg) => { if (status) status.textContent = msg; };

  // Thresholds come from server config and are never defaulted here. `ROUTES.config` is `null`
  // -- the route does not exist yet -- so the absence is named as an absence rather than
  // printed as the string "null", which is what this line used to put on screen.
  api.loadAlignConfig()
    .then(cfg => app.setConfig(cfg && cfg.align_scoring ? cfg.align_scoring : cfg))
    .catch(err => {
      console.warn('[map2] align config unavailable:', err.message);
      say('기준값 없음 · 순위 없음');
    });

  // 🔴 THE REQUEST SHAPE. `loadReferenceView` takes the UNIT, not a map: a rule name, the map
  //    table, and the decision key's values as `params`. The old `{eqp, product}` call was
  //    rejected by the transport before any network traffic happened, and the capture fallback
  //    swallowed the rejection -- which is why a broken request looked like a working screen.
  app.setLoader(decision => api.loadReferenceView({
    rule: RULE,
    mapTable: MAP_TABLE,
    params: { dt_eqp: decision.eqp, product: decision.product },
    includeCells: true,
  }));

  // The worklist route does not exist yet (`ROUTES.worklist` is null). The decision KEY is
  // seeded from the capture so the screen has a unit to ask about; the PAYLOAD it renders then
  // comes from the live route. Those are two different things, and the capture marker tracks
  // only the second -- seeding a key is not serving captured data.
  fetch(DEV_CAPTURE_URL, { headers: { Accept: 'application/json' } })
    .then(res => (res.ok ? res.json() : null))
    .then(seed => {
      const rows = seed && seed.eqp
        ? [{ eqp: seed.eqp, product: seed.product, map_count: seed.map_count, scorable: true }]
        : [];
      app.setWorklist(rows);
      if (rows.length === 0) say('작업 목록 없음');
    })
    .catch(err => {
      console.warn('[map2] worklist seed unavailable:', err.message);
      say('작업 목록 없음');
    });

  app.render();
  // Handy for the dev console and for the browser check; not read by any module.
  window.__map2 = app;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
