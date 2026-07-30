// CONFIG RESOLVE REPORT — the view model for `GET /admin/config/resolve`.
//
// WHY THIS IS A SEPARATE, DOM-FREE MODULE.
//   The load-bearing half of this seam is negative: the server composes the operator-facing
//   sentence and the client renders `detail` VERBATIM. The client must never decide for itself
//   that a declaration has no effect — that is the hardcoded-copy class U6 deleted six times.
//   A renderer that builds DOM inline cannot be scored for that from node, so
//   `contracts/config_resolve_report/client_harness.mjs` imports THIS file and checks every
//   string it emits:
//
//     src 'server' — must exist verbatim as a string somewhere in the payload
//     src 'value'  — must be exactly JSON.stringify(<a payload value>)
//     src 'chrome' — must come from the frozen CHROME table below
//     src 'count'  — must be an integer the client counted, spelled as itself
//
//   The moment a sentence about a config's status gets composed here, it is neither in the
//   payload nor in CHROME, and the harness says so with a file and a line.
//
// WHAT THE CLIENT IS ALLOWED TO KNOW
//   Structure, colour and counts. Not meaning. The reason words never appear in this file as
//   literals (they arrive inside the data and are rendered as data); population names appear
//   only as keys of a presentation-only colour table, and an unknown population draws neutral
//   instead of guessing.

/** Client-authored strings. Structural labels only — never a verdict, never per-reason. */
export const CHROME = Object.freeze({
  HEADLINE: '설정 반영',
  DETAIL_HINT: '자세히 보기',
  SOURCES: '설정 파일',
  SETTINGS: '현재 값',
  DECLARED: '선언값',
  VIEWS: '참조뷰',
  MEASURE: '드라이런',
  MEASURE_HINT: '쓰기 없이 큐를 검사해 사람 없이 확정 가능한 건수를 셉니다.',
  MEASURING: '측정 중…',
  MEASURE_FAILED: '드라이런 요청 실패',
  REFUSED: '보류 사유',
  FETCH_FAILED: '조회 실패',
  NO_DOMAINS: '서버가 보고한 설정 도메인이 없습니다.',
});

export const CHROME_STRINGS = Object.freeze(Object.values(CHROME));

/** The four text provenances the harness scores. */
export const TEXT_SOURCES = Object.freeze(['server', 'value', 'chrome', 'count']);

/** PRESENTATION ONLY — which colour a bucket is drawn in.
 *
 * The server decides which bucket a declaration lands in; this table decides nothing except
 * the colour, and a population the client has never heard of draws neutral rather than being
 * guessed at. No sentence is composed from it and no entry is re-classified.
 */
const POPULATION_TONE = { effective: 'ok', ineffective: 'warn', rejected: 'danger' };

/** The dry-run route is enrichment-specific and keyed by rule NAME.
 *
 * The report advertises no per-entry actions, so the pairing lives HERE, in one place, and is
 * read off the data rather than off a scope word: an entry whose `fields` carry the
 * auto-confirm knob is a rule that `GET /admin/enrichment/auto-confirm/dry-run` can measure.
 * That is a routing fact about which URL exists — not a verdict about the entry.
 */
const MEASURABLE_DOMAIN = 'enrichment';
const MEASURABLE_FIELD = 'auto_confirm';

/** A string the SERVER wrote. Rendered verbatim, never reworded. */
function srv(value) {
  return { src: 'server', text: String(value) };
}

/** A payload VALUE, spelled in JSON — the syntax of the file the operator edited.
 *  (`_as_json` on the server side does the same thing for the same reason.) */
function val(value) {
  return { src: 'value', text: JSON.stringify(value), raw: value };
}

function chrome(text) {
  return { src: 'chrome', text };
}

function count(n) {
  return { src: 'count', text: String(n), value: n };
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function buildView(view) {
  return {
    label: view && view.label != null ? srv(view.label) : null,
    detail: view && view.detail != null ? srv(view.detail) : null,
    warnings: list(view && view.warnings).map(srv),
    narrow: Boolean(view && view.scope_narrow),
  };
}

function buildEntry(entry, domainName) {
  const fields = (entry && entry.fields) || {};
  const measurable = domainName === MEASURABLE_DOMAIN
    && Object.prototype.hasOwnProperty.call(fields, MEASURABLE_FIELD)
    && entry.subject != null && String(entry.subject) !== '';
  const warnings = list(entry && entry.warnings);
  return {
    scope: entry && entry.scope != null ? srv(entry.scope) : null,
    subject: entry && entry.subject != null ? srv(entry.subject) : null,
    // THE sentence. Straight through, untouched.
    detail: entry && entry.detail != null ? srv(entry.detail) : null,
    reason: entry && entry.reason != null ? srv(entry.reason) : null,
    warnings: warnings.map(srv),
    views: list(fields.reference_views).map(buildView),
    // Open the view list without a click when the entry carries a warning: the trap sentence
    // is the whole point of that list, and a collapsed warning is a warning nobody reads.
    viewsOpen: warnings.length > 0,
    measure: measurable ? String(entry.subject) : null,
  };
}

function buildSource(source) {
  const missing = source && source.exists === false;
  const degraded = source && source.status && source.status !== 'ok';
  return {
    key: source && source.key != null ? srv(source.key) : null,
    path: source && source.path != null ? srv(source.path) : null,
    detail: source && source.detail != null ? srv(source.detail) : null,
    // A missing config file is NOT a rejection (INV-F9-6) — it is drawn muted, not red.
    tone: degraded ? 'danger' : (missing ? 'muted' : ''),
  };
}

function buildSetting(setting) {
  const declared = setting ? setting.declared : null;
  return {
    key: setting && setting.key != null ? srv(setting.key) : null,
    value: setting ? val(setting.value) : null,
    origin: setting && setting.origin != null ? srv(setting.origin) : null,
    path: setting && setting.path != null ? srv(setting.path) : null,
    declaredLabel: declared === null || declared === undefined ? null : chrome(CHROME.DECLARED),
    declared: declared === null || declared === undefined ? null : val(declared),
    detail: setting && setting.detail != null ? srv(setting.detail) : null,
  };
}

function buildDomain(domain, populations) {
  const name = domain && domain.domain != null ? String(domain.domain) : '';
  return {
    name,
    title: domain && domain.title != null ? srv(domain.title) : null,
    sourcesLabel: chrome(CHROME.SOURCES),
    sources: list(domain && domain.sources).map(buildSource),
    settingsLabel: chrome(CHROME.SETTINGS),
    settings: list(domain && domain.settings).map(buildSetting),
    populations: populations.map((population) => {
      // The list the client shows IS the list it counts. `counts` is the server's own tally
      // and the contract test scores the two against each other (INV-F9-5); rendering the
      // tally next to a different list is how a badge starts lying.
      const entries = list(domain && domain[population]);
      return {
        name: population,
        label: srv(population),
        count: count(entries.length),
        tone: POPULATION_TONE[population] || '',
        entries: entries.map((e) => buildEntry(e, name)),
      };
    }),
  };
}

/** The whole report, as a tree of text carriers. `report` is the parsed route response. */
export function buildConfigResolveView(report) {
  const vocabulary = (report && report.vocabulary) || {};
  const populations = list(vocabulary.populations).map(String);
  const domains = list(report && report.domains);
  const totals = populations.map((population) => ({
    name: population,
    label: srv(population),
    count: count(domains.reduce((sum, d) => sum + list(d && d[population]).length, 0)),
    tone: POPULATION_TONE[population] || '',
  }));
  // The headline tone follows the worst bucket that has anything in it. Neutral when the
  // client was given a population it has no colour for — silence beats a guess.
  let tone = '';
  for (const total of totals) {
    if (total.count.value === 0) continue;
    if (total.tone === 'danger') { tone = 'danger'; break; }
    if (total.tone === 'warn') tone = 'warn';
  }
  return {
    headlineLabel: chrome(CHROME.HEADLINE),
    detailHint: chrome(CHROME.DETAIL_HINT),
    totals,
    tone,
    titles: domains.map((d) => (d && d.title != null ? srv(d.title) : null)).filter(Boolean),
    domains: domains.map((d) => buildDomain(d, populations)),
    empty: domains.length === 0,
    emptyText: chrome(CHROME.NO_DOMAINS),
  };
}

/** `GET /admin/enrichment/auto-confirm/dry-run` — the same discipline, one sentence long.
 *
 * The server's `detail` already carries every number worth reading ("큐 N건을 검사해 M건이…"),
 * so this deliberately does NOT re-tile those numbers: a second rendering of the same facts is
 * a second chance to disagree with them. What it adds is the refusal breakdown, which the
 * sentence does not contain.
 */
export function buildDryRunView(payload) {
  const refusedMap = (payload && payload.refused) || {};
  return {
    rule: payload && payload.rule != null ? srv(payload.rule) : null,
    detail: payload && payload.detail != null ? srv(payload.detail) : null,
    reason: payload && payload.refused_reason != null ? srv(payload.refused_reason) : null,
    refusedLabel: chrome(CHROME.REFUSED),
    refused: Object.keys(refusedMap).sort().map((word) => ({
      word: srv(word),
      count: count(Number(refusedMap[word]) || 0),
    })),
  };
}

/** Every text carrier in a view tree, in document order. Used by the contract harness. */
export function collectTexts(node, out = []) {
  if (node === null || node === undefined) return out;
  if (Array.isArray(node)) {
    for (const child of node) collectTexts(child, out);
    return out;
  }
  if (typeof node !== 'object') return out;
  if (typeof node.src === 'string' && typeof node.text === 'string'
      && TEXT_SOURCES.includes(node.src)) {
    out.push(node);
    return out;
  }
  for (const key of Object.keys(node)) collectTexts(node[key], out);
  return out;
}
