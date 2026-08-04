// ═══════════════════════════════════════════════════════════════════════════════
// TRANSPORT -- the only module in Map Editor 2 that talks to the server.
//
// (MAP_ALIGNMENT_SPEC 0.2, side table: "서버 호출은 여기 하나 / 층들은 서버를 모른다".)
//
// 🔴 EXPLORING IS GET-ONLY BY CONSTRUCTION. The switchover bar is 8 maps, at most 4 actions
//    each, at most 30 seconds each, and ZERO database writes while exploring. This factory
//    therefore separates the two kinds of call at the type level: `loadReferenceView` is the
//    read, `confirmFrame` is the single write, and the returned client counts each kind so the
//    bar can be MEASURED rather than asserted.
//
// 🔴 ALL EIGHT SCORINGS ARRIVE IN ONE PAYLOAD. This is the load-bearing requirement of the
//    whole design, not a nicety: if the client fetched per candidate, eight round trips per
//    row would blow the 30-second bar on their own. Candidate selection is a client-side
//    repaint of data already in hand and MUST NOT reach this module. There is deliberately no
//    `loadCandidate(id)` function here -- the absence is the enforcement.
//
// FACTORY, NOT A SINGLETON. `createApiClient` returns a record. No module-level mutable state,
// so a harness can make one with a recording `fetch` and never touch the network.
//
// ── THE READ PAYLOAD, AS THE SERVER ACTUALLY SERVES IT (2026-08-05) ────────────
// Verified against `server/main.py:4160` / `server/map_alignment.py:675`. The previous
// spelling in this comment described a payload nobody serves, which is how the screen ended
// up running off a captured file.
//   {
//     unit: { rule, decision_key, source_table, map_table, map_key_columns },
//     state: 'scored' | 'no_winner' | 'not_scorable',
//     refusal: string|null,               // the server's own Korean sentence, verbatim
//     reference: { state, kind: 'none'|'occupancy'|'values', source, table, map_id,
//                  count, reason, truncated, cells: [[x, y], ...] },
//     sources:   { map_count, usable_map_count, cell_count, cells, truncated, cell_cap,
//                  maps: [{ map_id, cell_count, declared_frame, declared_frame_source }] },
//     candidates:  [{ frame, rotation, side, state, shift, agreement, discriminating,
//                     placed, margin, reason, declared_by_maps }],   // ALL EIGHT, no ratios
//     declaration: { frames, unanimous, frame, attested_maps, unattested_maps, axis_sources },
//     ruling: { winner, margin, reason_code, tied? },
//     excluded, excluded_total, stats
//   }
// 🔴 CELLS ARE `[x, y]` PAIRS, NOT `{x, y}` OBJECTS. Anything indexing `.x` on a reference
//    cell reads `undefined` and silently draws nothing.
// 🔴 `reference.kind` IS DECLARED ON THE WIRE. The client no longer infers it (see
//    `decode.js`) -- an inferred kind was a plausible default impersonating a declaration.
// 🔴 THE VOCABULARY IS `frame` (`rot90_front`), keyed by `map_id`. Not `candidate_id`, not
//    `source_ids`.
// No field in that payload is a percentage. If one appears, the decoder throws on entry and
// the view model throws on build.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Routes. These are the seam with the server lane and are the ONE place a path is written.
 * They are not thresholds -- tuning knobs live in server config and are passed in.
 *
 * 🔴 TWO OF THESE ARE `null` ON PURPOSE. No server route exists for a worklist or for a
 *    threshold config, and inventing a path here would produce a 404 that reads to the next
 *    reader as a server bug rather than as an absent feature. A threshold route written in a
 *    hurry is exactly how the `Number(null) === 0` class of defect gets RE-CREATED rather
 *    than avoided: a config endpoint that answers `{}` hands the verdict layer an absent
 *    threshold wearing the clothes of a declared one. Named and unreachable is the honest
 *    state, and the two loaders below refuse loudly rather than fetching nothing.
 */
export const ROUTES = Object.freeze({
  // The decision unit is declared by an enrichment rule, never by one map. A per-map route
  // would rebuild the reload loop this screen exists to end.
  referenceView: '/api/maps/alignment/view',
  confirm: '/api/maps/alignment/confirm',
  worklist: null,
  config: null,
});

/** Thrown by the two loaders whose route does not exist. Names the absence as an absence. */
export class RouteNotServedError extends Error {
  constructor(name) {
    super(`no server route exists for '${name}'. It is named in ROUTES and deliberately `
      + 'unreachable; do not invent a path here.');
    this.name = 'RouteNotServedError';
    this.route = name;
  }
}

export function createApiClient(opts) {
  const baseUrl = String((opts && opts.baseUrl) || '');
  const doFetch = (opts && opts.fetchImpl) || globalThis.fetch;
  const timeoutMs = Number(opts && opts.timeoutMs);
  const counters = { reads: 0, writes: 0 };

  async function getJson(path, params, signal) {
    counters.reads++;
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    const res = await doFetch(`${baseUrl}${path}${qs}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
    });
    if (!res.ok) {
      const text = await safeText(res);
      const err = new Error(`GET ${path} -> ${res.status}`);
      err.status = res.status;
      err.detail = text;
      throw err;
    }
    return res.json();
  }

  return Object.freeze({
    counters,

    /** NO SERVER ROUTE. Named so the seam is visible; unreachable so it cannot half-work. */
    loadWorklist() {
      return Promise.reject(new RouteNotServedError('worklist'));
    },

    /**
     * NO SERVER ROUTE, AND THAT IS THE SAFE STATE. Thresholds must be read from a declaration,
     * never defaulted in client code, and the verdict layer already refuses to rank at all
     * when they are missing rather than guessing. An endpoint invented here would replace
     * "we refuse, loudly" with "we ranked against zero".
     */
    loadAlignConfig() {
      return Promise.reject(new RouteNotServedError('config'));
    },

    /**
     * One request. Reference cells, pooled source cells, the declaration block and ALL EIGHT
     * candidate scorings together.
     *
     * 🔴 `params` IS REQUIRED, AND THIS REFUSES WITHOUT IT. A reference view with no decision
     *    key is not this screen's question. Wafers under ONE eqp+product were MEASURED
     *    disagreeing -- three declaring `rot270_back` and one `rot0_front` -- and pooling them
     *    is the entire reason the unit is not a single map. A unit-less query still returns
     *    200 with a shape that renders, which is the worst failure available: a confident
     *    screen about nothing in particular.
     *
     * 🔴 AND IT GOES IN `params`, NOT AS `?eqp=&product=`. That spelling hardcodes the
     *    decision key into the API, and `enrichment_rules.json` owns the unit precisely so it
     *    can change without an API change. The server validates these keys against the rule's
     *    own `decision_key` and 400s on a key the rule does not declare, so a wrong spelling
     *    fails loudly instead of quietly answering about nothing.
     *
     * @param {object} req
     * @param {string} req.rule          enrichment rule that declares the decision unit
     * @param {string} req.mapTable      map table the source coordinates live in
     * @param {object} req.params        {decision_key_col: value} -- REQUIRED, non-empty
     * @param {string} [req.reference]   "table:map_id"; omitted means "follow valid_die_ref"
     * @param {boolean} [req.includeCells]  false drops the cell arrays (list screens)
     */
    loadReferenceView(req, signal) {
      const r = req || {};
      if (!r.rule) {
        return Promise.reject(new Error(
          "loadReferenceView: 'rule' is required. The enrichment rule names the decision unit."));
      }
      if (!r.params || typeof r.params !== 'object' || Object.keys(r.params).length === 0) {
        return Promise.reject(new Error(
          "loadReferenceView: 'params' is required and must carry the decision key's values "
          + '(e.g. {dt_eqp, product}). Refused here rather than sent, because a unit-less view '
          + 'answers a different question and still renders.'));
      }
      const q = {
        rule: String(r.rule),
        map_table: r.mapTable == null ? '' : String(r.mapTable),
        params: JSON.stringify(r.params),
      };
      if (r.reference) q.reference = String(r.reference);
      if (r.includeCells === false) q.include_cells = 'false';
      return getJson(ROUTES.referenceView, q, signal);
    },

    /**
     * THE ONLY WRITE IN THIS SCREEN. Called once, after the operator has armed and confirmed.
     *
     * 🔴 THE REQUEST CARRIES THE RULING AND THE PER-SOURCE ROWS. The write path deliberately
     *    does NOT re-score: what has to be recorded is what the operator looked at when they
     *    decided. Sending ids and letting the server re-derive would force a second scoring
     *    implementation in by the back door, and the day the two disagree the screen still
     *    looks fine while the record is wrong.
     * 🔴 EVERY SOURCE CARRIES ITS OWN FRAME AND SHIFT, excluded ones included. A dropped
     *    nonzero shift moves every die on that map; a dropped excluded source cannot later be
     *    told apart from a source that was never there.
     *
     * @param {object} record
     * @param {string} record.rule
     * @param {object} record.decisionKey  {column: value}, every declared key filled
     * @param {object} record.frames       {target_field: frame}, e.g. {core_frame:'rot90_front'}
     * @param {Array}  record.sources      [{role, source_table, map_id, source_name,
     *                                      applied_frame, shift_dx, shift_dy,
     *                                      agreement, discriminating, excluded_reason}]
     * @param {object} record.ruling       the `/view` ruling, passed through unchanged
     * @param {object} record.reference    {table, map_id}
     * @param {string} record.confirmedBy
     * @returns the WHOLE created record: confirmation_uid, version, supersedes, per-source
     *          rows. Render that. NEVER re-fetch after a write.
     */
    async confirmFrame(record, signal) {
      counters.writes++;
      const r = record || {};
      const res = await doFetch(`${baseUrl}${ROUTES.confirm}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rule: r.rule,
          decision_key: r.decisionKey || {},
          frames: r.frames || {},
          sources: Array.isArray(r.sources) ? r.sources : [],
          ruling: r.ruling || null,
          reference: r.reference || null,
          confirmed_by: r.confirmedBy,
        }),
        signal,
      });
      if (!res.ok) {
        const err = new Error(`POST ${ROUTES.confirm} -> ${res.status}`);
        err.status = res.status;
        err.detail = await safeText(res);
        throw err;
      }
      return res.json();
    },

    /** Bound on a hung response, so a stalled request cannot strand the control forever. */
    timeoutMs: Number.isFinite(timeoutMs) ? timeoutMs : null,
  });
}

async function safeText(res) {
  try { return await res.text(); } catch (e) { return ''; }
}
