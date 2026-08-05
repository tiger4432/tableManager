// ============================================================
// The enrichment queue, asked for BY NAME.
//
// "Which rows still need work" is ONE question, and the rule already declares
// everything needed to answer it. It used to travel to the client as a filter
// dict (`queue_filters`: one `blank` spec per target field) and every consumer
// ANDs the per-column specs -- so on a rule with TWO targets the queue silently
// meant EVERY target blank, and filling one column dropped the row out of the
// list while its sibling was still empty. Both live rules declare two targets,
// so that was reachable, not theoretical. Server ruling 2026-08-05: the
// predicate is composed SERVER-side as OR-of-blank across the rule's own
// `target_fields`, and the client asks for it instead of reconstructing it.
//
// THIS MODULE IS THE CLIENT'S SINGLE SPELLING OF THAT REQUEST. Three call sites
// consume it: the conveyor worklist (`enrichment.js`), the main-grid badge
// (`ui.js`) and the admin missing-count (`admin.js`). Each composed the filter
// dict on its own before -- one question's definition living in three places,
// which is three places for it to drift and the reason the badge could disagree
// with the list it links to.
//
// NOT here, deliberately: the progress bar's DENOMINATOR. That request is
// unfiltered by design (every derived row), and the numerator being a subset of
// exactly that population is the N36 invariant. Routing it through a queue
// composer is how a filter gets attached to it again.
//
// DOM-free and dependency-free on purpose, so a harness can `import` it rather
// than slice its text.
// ============================================================

// The four scopes the server publishes. `keyed` + `blank_key` partition `queue`
// exactly, which is what keeps the named aggregate equal to the remainder it is
// carved out of.
export const QUEUE_SCOPE_QUEUE = 'queue';          // ANY target blank
export const QUEUE_SCOPE_KEYED = 'keyed';          // queue AND every decision key present
export const QUEUE_SCOPE_BLANK_KEY = 'blank_key';  // queue AND at least one decision key blank
export const QUEUE_SCOPE_RESOLVED = 'resolved';    // every target filled AND every key present

// Does this server ship the named predicate? Its ABSENCE is the whole version
// signal, and it is a positive one -- nothing is inferred from a status code, a
// build string or a probe request.
export function hasQueuePredicate(rule) {
  const p = rule && rule.queue_predicate;
  return !!(p && p.param && p.value);
}

// Query fragment for `GET /tables/{derived}/data`, without a leading separator.
//
// `null` means THIS server cannot be asked THIS question, and the caller must
// then say nothing. It must not drop the condition and take the answer: a page
// that returns more rows than were asked for while the response implies the
// queue is the same wrong answer the server's own `?cols=` refusal exists to
// prevent.
export function queueQuery(rule, scope = QUEUE_SCOPE_QUEUE) {
  if (hasQueuePredicate(rule)) {
    const p = rule.queue_predicate;
    const listed = !Array.isArray(p.scopes) || p.scopes.indexOf(scope) >= 0;
    const scopable = !!p.scope_param && listed;
    // A scope this server does not publish is unanswerable, not defaultable.
    // Falling back to the plain queue here would answer a WIDER population under
    // the narrower question's name.
    if (!scopable && scope !== QUEUE_SCOPE_QUEUE) return null;
    const base = `${encodeURIComponent(p.param)}=${encodeURIComponent(p.value)}`;
    if (!scopable) return base;
    return `${base}&${encodeURIComponent(p.scope_param)}=${encodeURIComponent(scope)}`;
  }
  return legacyQueueQuery(rule, scope);
}

// Old server. `queue_filters` is the answer it is able to give: one `blank` spec
// per target, conjoined by whoever applies it. That is the EVERY-blank reading
// this round replaces, so on a multi-target rule it under-reports -- but it is
// still what THAT server means by the queue, and reporting its own number is
// honest where erroring is not.
//
// The other three scopes need a cross-column OR, which the public filter DSL
// cannot spell (`operator`/`conditions` combine specs for ONE column). They are
// unanswerable there and say so rather than being approximated.
function legacyQueueQuery(rule, scope) {
  if (scope !== QUEUE_SCOPE_QUEUE) return null;
  const filters = (rule && rule.queue_filters) || legacyBlankFilters(rule);
  if (!filters) return null;
  return `filters=${encodeURIComponent(JSON.stringify(filters))}`;
}

// Server older still: no `queue_filters` either. Compose the same shape from the
// declared targets. A rule with no targets yields no condition at all, and an
// unconditioned request is the whole table -- so that is `null`, not `{}`.
function legacyBlankFilters(rule) {
  const targets = (rule && rule.target_fields) || [];
  if (targets.length === 0) return null;
  const filters = {};
  targets.forEach(f => { filters[f] = { type: 'blank' }; });
  return filters;
}
