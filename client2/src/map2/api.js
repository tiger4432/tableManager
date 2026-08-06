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
//                  maps: [{ map_id, cell_count, declared_frame, declared_frame_source,
//                           geometry, geometry_basis }] },
//     assumption: { state: 'applied'|'available'|'unavailable', requested, map_count, map_ids,
//                   basis: {table, map_id}|null, text: string|null },
//     candidates:  [{ frame, rotation, side, state, shift, agreement, discriminating,
//                     placed, margin, reason, declared_by_maps }],   // ALL EIGHT, no ratios
//     declaration: { frames, unanimous, frame, attested_maps, unattested_maps, axis_sources },
//     ruling: { winner, margin, reason_code, tied?, geometry_assumed },
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
 * 🔴 ONE OF THESE IS `null` ON PURPOSE -- the THRESHOLD CONFIG, and only that one. (The
 *    worklist was the second until 2026-08-05; the route landed and this sentence did not
 *    follow it for a day. Counts in prose go stale exactly like counts in code.) No server
 *    route exists for a threshold config, and inventing a path here would produce a 404 that
 *    reads to the next reader as a server bug rather than as an absent feature. A threshold
 *    route written in a hurry is exactly how the `Number(null) === 0` class of defect gets
 *    RE-CREATED rather than avoided: a config endpoint that answers `{}` hands the verdict
 *    layer an absent threshold wearing the clothes of a declared one. Named and unreachable is
 *    the honest state, and the loader below refuses loudly rather than fetching nothing.
 */
export const ROUTES = Object.freeze({
  // The decision unit is declared by an enrichment rule, never by one map. A per-map route
  // would rebuild the reload loop this screen exists to end.
  referenceView: '/api/maps/alignment/view',
  confirm: '/api/maps/alignment/confirm',
  // The rule declares its own `target_fields`. Those are what the CONFIRMATION writes -- the
  // decision's destination -- and they are read from the declaration rather than listed here.
  // Contract as documented at `client2/src/enrichment.js:6-7`, already consumed by admin.
  rules: '/enrichment/rules',
  // The table's REAL columns. An existing route, already consumed by admin; reused rather than
  // reinvented, and it is the reason no column name is written down in this client.
  // Every table the server defines. With `/tables/{t}/schema`'s `map_key_columns` this is how
  // the screen DISCOVERS which tables are map tables -- the same declaration
  // `map_alignment.map_table_catalog` reads server-side (`crud.TABLE_CONFIG[t].map_key_columns`),
  // so no table name is written down here.
  tables: '/tables',
  schema: '/tables/{table}/schema',
  // (Kept null: `selection` now rides on the worklist response, so nothing needs this.)
  // 🔴 THE PRESET ALREADY EXISTS AND IS ALREADY SERVED. A table's coordinate binding is
  //    declared in `map_overlay_config.json` -> `table_bindings.<table>.columns`
  //    ({x, y, val, key_columns[]}) and served RESOLVED -- declaration beating derivation --
  //    by this route as `binding: {x, y, val, key_columns[], source}`. So the x/y/value pickers
  //    are pre-filled from the repo's own declaration rather than from a shape invented here,
  //    and `source: "fallback_guess"` is the EXISTING marker for "a guess you must not render
  //    like a declaration". Nothing about presets is designed in this client.
  paintRules: '/api/maps/paint-rules',
  // LANDED 2026-08-05. The route serves the page, the server's own totals, AND the `selection`
  // catalog (map tables + coordinate columns + the binding ambiguity), so the client no longer
  // assembles a catalog of its own from three calls.
  worklist: '/api/maps/alignment/worklist',
  // WHICH REFERENCES ACTUALLY RESOLVE. Served standalone (lead ruling 2026-08-05) precisely
  // because riding on the worklist response made it UNREACHABLE WITHOUT A RULE -- and a
  // deployment with no alignment-capable rule is the production case, so the picker was empty
  // exactly where it was needed. It takes no parameter here: absent `table` means every map
  // table, which is what lets a rule-less client bootstrap. `map_table` deliberately does NOT
  // narrow the candidate set (`map_alignment.resolve_reference_catalog`), so sending it would
  // ask for a narrowing nobody performs.
  referenceCatalog: '/api/maps/alignment/references',
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

    /**
     * The worklist, ONE PAGE AT A TIME, SEARCHED AND ORDERED BY THE SERVER.
     *
     * 🔴 `q` GOES TO THE SERVER. It is not a browser filter over a loaded list, and this
     *    function is the reason it cannot become one: there is no "load them all" call here to
     *    filter over. The population is not bounded by anything this client controls -- 668
     *    metas today -- and a filter that works at 668 is the same code that freezes at 60,000.
     *
     * ✅ SERVED. `GET /api/maps/alignment/worklist` landed 2026-08-05 and `ROUTES.worklist`
     *    points at it. This used to say "STILL UNSERVED", which stayed on the page after the
     *    route arrived -- a comment describing a defect that no longer exists sends the next
     *    reader hunting for it, and costs more than saying nothing. The guard below is KEPT on
     *    purpose: it is not dead code, it is what makes a route being un-wired refuse by name
     *    instead of fetching `undefined`.
     *
     * @param {object} [query]
     * @param {string} [query.q]          search text, applied server-side
     * @param {string} [query.rule]       the rule naming the decision unit
     * @param {string} [query.mapTable]   the chosen map table
     * @param {string} [query.field]      the chosen target field
     * @param {string} [query.reference]  "table:map_id", omitted for 기준 없음
     * @param {number} [query.limit]
     * @param {string} [query.cursor]     opaque; paging is the server's, never an offset here
     */
    loadWorklist(query, signal) {
      if (!ROUTES.worklist) return Promise.reject(new RouteNotServedError('worklist'));
      return getJson(ROUTES.worklist, worklistParams(query), signal);
    },

    /**
     * THE FLOORS THAT ACTUALLY RESOLVE. The only honest source for "which references resolve"
     * is the side that resolves them, and it now says so on a route of its own.
     *
     * 🔴 NO PARAMETERS. The list is a per-deployment constant: it does not vary by unit, by
     *    search, by page, or by map table. Asking per table would be a narrowing the server
     *    does not perform, and asking per unit would put the reload loop back.
     *
     * Returns the NORMALISED record (see `normaliseReferenceCatalog`), never the raw body --
     * so the envelope, the field names and the path are all in this one file.
     */
    async loadReferenceCatalog(signal) {
      if (!ROUTES.referenceCatalog) return Promise.reject(new RouteNotServedError('referenceCatalog'));
      return normaliseReferenceCatalog(await getJson(ROUTES.referenceCatalog, null, signal));
    },

    /**
     * The enrichment rules, as the meta route already serves them to the queue screen and to
     * admin. Read for ONE field: `target_fields`. Nothing here derives a frame field.
     */
    loadRules(signal) {
      return getJson(ROUTES.rules, null, signal);
    },

    /** Every defined table. Which of them are MAP tables is decided by their schema. */
    loadTables(signal) {
      return getJson(ROUTES.tables, null, signal);
    },

    /**
     * One table's real schema. `columns[]` is what the x / y / value pickers offer, and it is
     * the only source they have -- there is no column list anywhere in this client to fall
     * back to, which is what keeps a stale hardcoded name from outliving a renamed column.
     */
    /**
     * The RESOLVED coordinate binding for one table, with its provenance. This is where a
     * pre-filled x/y/val comes from; the client neither declares nor guesses one.
     */
    loadBinding(table, signal) {
      const name = String(table || '');
      if (!name) return Promise.reject(new Error('loadBinding: a table name is required'));
      return getJson(ROUTES.paintRules, { table: name }, signal);
    },

    loadTableSchema(table, signal) {
      const name = String(table || '');
      if (!name) return Promise.reject(new Error('loadTableSchema: a table name is required'));
      return getJson(ROUTES.schema.replace('{table}', encodeURIComponent(name)), null, signal);
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
     * @param {string} [req.xCol]        the column read as x
     * @param {string} [req.yCol]        the column read as y
     * @param {string} [req.valCol]    the column read as the die value; OPTIONAL, and its
     *                                   absence is what makes the run occupancy-only
     * @param {boolean} [req.includeCells]  false drops the cell arrays (list screens)
     *
     * 🔴 THERE IS NO `assumeReferenceGeometry` PARAMETER, AND ITS ABSENCE IS DELIBERATE.
     *    `assume_reference_geometry` exists on the route and DEFAULTS TO TRUE
     *    (`get_map_alignment_view(..., assume_reference_geometry: bool = True, ...)`), so
     *    omitting it is how the automatic behaviour the product owner asked for
     *    (「가정 적용은 자동으로 되게」) reaches the wire. This client sends it in NEITHER
     *    direction: there is no control to turn it on, and none to decline it either.
     *    Restoring this line is what a round that wants to let an operator DECLINE would do --
     *    written down here so that possibility is not lost with the code.
     *
     * 🔴 THE COLUMNS ARE SENT AND ARE NOT YET HONOURED. The server derives the coordinate
     *    binding from its OWN overlay config -- `_binding_of` -> `map_overlay.resolve_binding`
     *    (`server/map_alignment.py:445-449`), consumed at `:468-479` and at `:600-604` -- and
     *    the route takes no column parameter at all (`server/main.py:4160-4168`). So a table
     *    with two coordinate pairs answers for whichever pair the config names, whatever the
     *    operator picked. The client sends the primitive tuple anyway, because that is the
     *    request shape, and it REFUSES TO ATTRIBUTE the answer to the chosen pair until the
     *    response echoes it (`unit.x_col` / `unit.y_col`). Rendering one measurement under
     *    whichever pair happens to be selected would be a plausible default impersonating a
     *    declaration -- and here it would be one on the layer the bonding plan rests on.
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
      // Omitted, not sent empty. An omitted `reference` means "follow the declaration"; a
      // 기준 없음 selection is the same wire shape and an ordinary state, not a hole.
      if (r.reference) q.reference = String(r.reference);
      // The primitive tuple. Omitted when unset rather than sent empty -- `?value_col=` and no
      // `value_col` at all are different requests, and only one of them means occupancy-only.
      if (r.xCol) q.x_col = String(r.xCol);
      if (r.yCol) q.y_col = String(r.yCol);
      if (r.valCol) q.value_col = String(r.valCol);
      if (r.includeCells === false) q.include_cells = 'false';
      // 🔴 THE SERVER DEFAULTS THIS **ON**, AND THE SENTENCE HERE USED TO SAY THE OPPOSITE.
      //    `get_map_alignment_view(..., assume_reference_geometry: bool = True, ...)` --
      //    measured 2026-08-06, `server/main.py`. This comment claimed "the server defaults it
      //    off for that reason", which was the design intent at one time and is not the served
      //    behaviour; product owner has since ruled that the assumption applies automatically
      //    (「가정 적용은 자동으로 되게」), and the server matches the ruling.
      //
      // ⚠️ CONSEQUENCE, STATED HERE BECAUSE IT IS NOT VISIBLE FROM THIS LINE. Sending the
      //    parameter only when TRUE means this client never sends `false` -- so the server's
      //    default stands on every request, the assumption is always applied where it helps,
      //    and the `available` state (the one that would put an accept control on screen) can
      //    never occur. The behaviour is what was asked for; what is left over is a control for
      //    an act nobody performs. Reported to the lead PM 2026-08-06, not resolved here.
      //
      //    `=== true` STRICTLY is kept regardless: a truthy coercion would let
      //    `undefined`-adjacent junk from a caller unlock the claim, which is the same class as
      //    a config typo unlocking a capability (`selectAlignmentRules`).
      return getJson(ROUTES.referenceView, q, signal);
    },

    /**
     * THE ONLY WRITE IN THIS SCREEN. Called once per confirmation -- one operator action, a
     * click on 확정 or Enter (product owner, 2026-08-06). There is no arming step to precede it.
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
     * @param {object} record.columns      {x, y, val} -- the pair that was aligned. THIS is
     *                                     what identifies the confirmation's subject.
     * @param {string} record.frame        the confirmed frame, e.g. 'rot90_front'
     * @param {string} record.mapTable     the table those coordinates live in
     * @param {object} [record.frames]     {target_field: frame}. Deliberately EMPTY: see the
     *                                     body below. Not a placeholder to be filled in later
     *                                     without a ruling.
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
          // 🔴 THE RECORD NAMES THE COLUMN PAIR, NOT A TARGET FIELD (lead ruling 2026-08-05).
          //    `frame_confirmation` is authoritative for what was confirmed, so what it must
          //    record is WHICH COORDINATES WERE ALIGNED. Nothing declares which pair writes
          //    which enrichment `target_field`, and whether the confirmation writes through to
          //    those fields or they become a pointer is still open -- so this sends `frames`
          //    EMPTY on purpose rather than guessing `core_x -> core_frame`. The server accepts
          //    an empty map (`frame_confirmation.py:193`); it only refuses names the rule did
          //    not declare. An empty map is the honest "we did not name a field".
          frames: r.frames || {},
          map_table: r.mapTable || null,
          columns: r.columns || null,
          frame: r.frame || null,
          sources: Array.isArray(r.sources) ? r.sources : [],
          ruling: r.ruling || null,
          // 🔴 `state` IS A SECOND FIELD BECAUSE `/view` PUTS IT AT THE RESPONSE TOP LEVEL,
          //    NOT INSIDE `ruling`. The confirm route's own docstring states the transcription
          //    rule as two lines for exactly this reason -- copy `ruling`, AND copy `state` --
          //    and following only the first loses the state entirely. Measured 2026-08-06:
          //    without this field a unit the server could not rank (`no_winner`) and an
          //    operator resolved by hand was recorded as `STATE_NOT_TRANSPORTED`, so the record
          //    could not say that a human broke a tie the machine refused to break. That is
          //    the whole content of those records.
          state: r.state || null,
          reference: r.reference || null,
          confirmed_by: r.confirmedBy,
        }),
        signal,
      });
      if (!res.ok) {
        const err = new Error(`POST ${ROUTES.confirm} -> ${res.status}`);
        err.status = res.status;
        err.detail = await safeText(res);
        // 🔴 THE SERVER'S OWN SENTENCE, LIFTED OUT OF THE ENVELOPE AND NOT RE-SPELLED.
        //    `frame_confirmation` raises TEN distinct `ConfirmationRefused` messages, each
        //    written in Korean for a person to read, and the route hands every one of them
        //    back as a 400 with the sentence in `detail`. Parsing the envelope belongs HERE,
        //    at the transport, because the envelope is FastAPI's shape -- a caller that had to
        //    know about `{"detail": ...}` would be a second place that knows the wire format.
        //    What callers get is the sentence, and it is the SERVER'S: composing an equivalent
        //    on this side is the second-judgement defect this screen already pays for with
        //    `refusal`, and a generic "확정 실패" would delete the one thing the operator needs
        //    -- WHICH of the ten refusals happened.
        err.serverMessage = serverMessage(err.detail);
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

/**
 * The human sentence out of an error body, or null.
 *
 * FastAPI wraps `HTTPException(detail=...)` as `{"detail": "<sentence>"}`. A body that is not
 * that shape is returned AS IT CAME rather than dropped: an unrecognised envelope still carries
 * whatever the server said, and silently discarding it is the behaviour this function exists to
 * end. Only genuinely empty bodies answer null, because null is what lets a caller say "the
 * server gave no reason" instead of showing an empty line that reads as no reason at all.
 *
 * ⚠️ NO CLASSIFICATION HAPPENS HERE. No mapping of status codes to categories, no matching
 *    against known messages, no default sentence. Ten refusals exist on the server precisely
 *    so the operator can tell them apart, and any grouping performed on this side would be a
 *    second judgement about evidence the server has already judged.
 */
function serverMessage(body) {
  const raw = typeof body === 'string' ? body.trim() : '';
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.detail === 'string' && parsed.detail.trim() !== '') {
      return parsed.detail.trim();
    }
    // Parsed, but not the shape we know. The body is still evidence; hand it over unchanged.
    return raw;
  } catch (e) {
    return raw;
  }
}

/** The catalog's two states, as the server spells them. Not re-spelled on this side. */
export const REFERENCE_CATALOG_SERVED = 'served';
export const REFERENCE_CATALOG_UNAVAILABLE = 'unavailable';

/**
 * THE ONE FUNCTION THAT KNOWS THE REFERENCE CATALOG'S SHAPE.
 *
 * 🔴 THE EXPECTED SHAPE IS THE DIRECT ONE. `/api/maps/alignment/references` returns the record
 *    unwrapped (lead ruling 2026-08-05):
 *      {state, table, filter, items: [{table, map_id, kind, cell_count, grid:{cols,rows}|null}],
 *       not_offered: [{table, map_id, reason_code, reason, cell_count}],
 *       examined, rejected, rejected_example, truncated, reason}
 *    Verified against `server/main.py:4419` / `server/map_alignment.py:1348-1437`.
 *    The two nested spellings below are NOT equal alternatives -- they exist because the same
 *    record ALSO rides on `/worklist` as `selection.references`, where it is one selection fact
 *    among several. One record, one decoder, rather than a second reader growing beside the
 *    worklist's copy and drifting from it.
 *
 * 🔴 `kind` IS PASSED THROUGH VERBATIM -- `values` | `occupancy`, the same vocabulary as
 *    `reference.kind` on `/view`. A second client-side spelling of a server word is the exact
 *    defect this round has been closing. `none` is reachable on `/view` (a unit may have no
 *    reference at all) but NOT here: a catalog item resolves by construction, so there is
 *    deliberately no `none` branch to write.
 *
 * 🔴 `value` IS THE WIRE SPELLING `table:map_id`, which is what `/view` takes back as its
 *    `reference` parameter. Composed here, once, so no caller assembles an identifier.
 *
 * Absences stay absent: a missing `cell_count` is `null` and NEVER a 0 stand-in, because a
 * measured zero-cell floor would be a very loud fact and an unmeasured one is not a fact at all.
 */
export function normaliseReferenceCatalog(body) {
  const root = body && typeof body === 'object' ? body : {};
  // Direct first. The nested reads are the worklist's `selection` envelope, not a guess.
  const rec = Array.isArray(root.items) ? root
    : (root.references && typeof root.references === 'object' ? root.references
      : (root.selection && root.selection.references && typeof root.selection.references === 'object'
        ? root.selection.references : root));
  const raw = Array.isArray(rec.items) ? rec.items : [];
  const items = [];
  for (const it of raw) {
    if (!it || typeof it !== 'object') continue;
    const table = it.table == null ? '' : String(it.table);
    const mapId = it.map_id == null ? '' : String(it.map_id);
    // An item that cannot be named cannot be selected, and offering it would be the "name that
    // resolves zero times" defect wearing new clothes.
    if (!table || !mapId) continue;
    const g = it.grid && typeof it.grid === 'object' ? it.grid : null;
    items.push(Object.freeze({
      value: `${table}:${mapId}`,
      table,
      mapId,
      kind: it.kind == null ? null : String(it.kind),
      cellCount: Number.isFinite(Number(it.cell_count)) && it.cell_count !== null
        ? Number(it.cell_count) : null,
      grid: (g && Number.isFinite(Number(g.cols)) && Number.isFinite(Number(g.rows)))
        ? Object.freeze({ cols: Number(g.cols), rows: Number(g.rows) }) : null,
    }));
  }
  return Object.freeze({
    // 🔴 PASSED THROUGH, NOT DEFAULTED. Defaulting an ABSENT state to `served` would be a
    //    plausible default impersonating a declaration -- the caller would read "the server
    //    looked and found nothing" out of a body that never said so. Absent stays `null`, which
    //    is not `served`, so the caller marks it degraded instead of trusting it.
    state: rec.state == null ? null : String(rec.state),
    table: rec.table == null ? null : String(rec.table),
    items: Object.freeze(items),
    // The filter that was in force, echoed. We send none, so this is `null` today.
    filter: rec.filter == null ? null : String(rec.filter),
    // 🔴 WHAT WAS NOT OFFERED, WITH ITS REASON -- AND IT NEVER REACHES THE PICKER. It is kept
    //    STRICTLY SEPARATE from `items`: a control that offers a floor which cannot resolve
    //    teaches the operator that the control lies, and there is deliberately no "show all"
    //    affordance for it anywhere on this side. But dropping it entirely would recreate the
    //    defect the server added it for -- a reasonless "none" sends the operator to a person
    //    instead of to a repair. So it rides in the record, which goes to the console whole.
    //    `cell_count` is carried for the same reason the server sends it: a candidate that HAS
    //    cells and still did not resolve is a different repair from one with no cells at all.
    notOffered: Object.freeze((Array.isArray(rec.not_offered) ? rec.not_offered : [])
      .filter(n => n && typeof n === 'object')
      .map(n => Object.freeze({
        table: n.table == null ? null : String(n.table),
        mapId: n.map_id == null ? null : String(n.map_id),
        reasonCode: n.reason_code == null ? null : String(n.reason_code),
        // The server's own sentence, verbatim. A second spelling here would drift from it.
        reason: n.reason == null ? null : String(n.reason),
        cellCount: Number.isFinite(Number(n.cell_count)) && n.cell_count !== null
          ? Number(n.cell_count) : null,
      }))),
    // The server's own accounting for what it looked at and threw away. Carried so the console
    // can say WHY a served list is short, which an empty list alone cannot.
    examined: Number.isFinite(Number(rec.examined)) ? Number(rec.examined) : null,
    rejected: Number.isFinite(Number(rec.rejected)) ? Number(rec.rejected) : null,
    rejectedExample: rec.rejected_example == null ? null : String(rec.rejected_example),
    truncated: rec.truncated === true,
    reason: rec.reason == null ? null : String(rec.reason),
  });
}

/**
 * The list/catalog query, as query STRING parameters the server reads. Empty values are
 * dropped rather than sent blank: `?reference=` is a different request from no `reference` at
 * all, and only one of them means 기준 없음.
 */
function worklistParams(query) {
  const q = query || {};
  const out = {};
  if (q.q) out.q = String(q.q);
  if (q.rule) out.rule = String(q.rule);
  if (q.mapTable) out.map_table = String(q.mapTable);
  // The unit filter travels as ONE encoded JSON object, exactly as `/view` takes it -- the
  // decision key's columns belong to the rule, so they are never spelled as query fields here.
  if (q.params && Object.keys(q.params).length > 0) out.params = JSON.stringify(q.params);
  if (q.sort) out.sort = String(q.sort);
  if (q.order) out.order = String(q.order);
  if (Number.isFinite(Number(q.limit))) out.limit = String(Number(q.limit));
  // OFFSET, not an opaque cursor: the route paginates by offset and inventing a cursor here
  // would be a parameter nobody serves.
  if (Number.isFinite(Number(q.offset))) out.offset = String(Number(q.offset));
  return out;
}
