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
  // The four failure lines. See `fetchFailureText` below for why these are client-owned:
  // the server did not answer, so it cannot be the one to say why.
  //
  // 🔴 상태는 «명사», 다음 행동은 «옆에», 가르는 것은 「·」 (상설 2026-09-05). 이 다섯이
  //    화면에서 «문장»으로 남아 있던 마지막 자리였습니다 — 읽어서 찾았고, 어느 체크리스트에도
  //    없었습니다. ⚠️ «고칠 자리»는 남깁니다: 사유만 남기고 행동을 지우면 짧아진 것이 아니라
  //    운영자가 갈 곳을 잃습니다.
  FETCH_OLD_SERVER: '구버전 서버 · 재시작 필요',
  FETCH_UNREACHABLE: '서버 연결 불가 · 실행 중인지 확인',
  FETCH_UNAUTHORIZED: '토큰 거부 · 새로고침 후 재입력',
  FETCH_INTERCEPTED: '관리자 게이트 아님 · 앞단 프록시 확인',
  NO_DOMAINS: '설정 도메인 없음',
  // C-87. 막힌 걸음이 «기다리는 걸음»을 가리키는 부호. 문장이 아니라 부호 하나이고, 번호는
  // 서버의 값입니다 — 「⑤ 가 안 서서 막혔습니다」라고 쓰면 그 문장의 저자가 화면이 됩니다.
  STEP_BLOCKED: '←',
  // 걸음 번호가 «없는» 도메인이 서는 자리의 이름. 없는 것을 0 번으로 그리지 않으려고
  // 이름을 하나 둡니다 — 「안 물어봤다」가 「첫 걸음」이 되면 순서가 거짓이 됩니다.
  UNSTEPPED: '순서 밖',
});

export const CHROME_STRINGS = Object.freeze(Object.values(CHROME));

/** The four text provenances the harness scores. */
export const TEXT_SOURCES = Object.freeze(['server', 'value', 'chrome', 'count']);

/** What a failed response said about ITSELF. Built by the caller, which owns the `Response`.
 *
 * `gate` must come from the caller's existing `isGateRejection` rather than from a status
 * comparison here — see `fetchFailureText`.
 *
 * @typedef {{status: number, gate: boolean, server: string}} FetchFailure
 */

/** Why the request failed, said as the thing to DO about it.
 *
 * THE ONE EXCEPTION TO "THE SERVER COMPOSES THE SENTENCE", AND IT PROVES THE RULE.
 *   Everywhere else the client renders `detail` verbatim because the server is the only side
 *   that knows what happened. Here it is the reverse: a server that predates this route cannot
 *   compose a sentence about not having the route — a server without the route cannot answer
 *   at all. The 404 IS the answer, and only the client is positioned to read it.
 *
 *   So the words stay in the frozen CHROME table above, tagged as chrome like every other
 *   client-owned string, and nothing is composed per call: this maps a failure onto one of five
 *   constants. No interpolation, no per-status sentence building. (The one dynamic fact worth
 *   showing is separated out into `fetchFailureEvidence` precisely so that stays true.)
 *
 * WHY FIVE AND NOT ONE. 「조회 실패」 answered every one of these with the same shrug, and they
 * put different hands on different things:
 *
 *   no response    nothing answered at all      → is the server running
 *   404            the process is older than the route → RESTART the server
 *   401/403, gate  our admin gate rejected us    → the token
 *   401/403, NOT   something else answered       → what is on this port
 *   anything else  the route is there and it broke → the caller's own failure label
 *
 * THE 401 SPLIT IS THE SAME DEFECT ONE LEVEL IN, so it gets the same treatment. A 401 is not
 * self-evidently OUR gate: a proxy sitting in front of the port answers with its own
 * `WWW-Authenticate: Basic realm=...`, and a corporate proxy did exactly that to a loopback
 * call. Sending an operator to the token modal for a proxy costs them the afternoon. The test
 * for "ours" is a header, not a status, and the caller already owns it (`isGateRejection`) —
 * this function must not re-derive it, or the two copies will drift.
 *
 * @param {FetchFailure|null} failure The response's own account of itself, or null/undefined
 *   when the request never got a response at all (fetch rejected: refused, DNS, offline).
 * @param {string} fallback The caller's own label for "it really did fail" — the only branch
 *   where the surface's own noun belongs, since the others are about who answered.
 * @returns {string} A CHROME entry. Never a newly composed string.
 */
export function fetchFailureText(failure, fallback = CHROME.FETCH_FAILED) {
  if (!failure) return CHROME.FETCH_UNREACHABLE;
  if (failure.status === 404) return CHROME.FETCH_OLD_SERVER;
  if (failure.status === 401 || failure.status === 403) {
    return failure.gate ? CHROME.FETCH_UNAUTHORIZED : CHROME.FETCH_INTERCEPTED;
  }
  return fallback;
}

/** The responder's own `Server:` header, when naming it tells the operator something.
 *
 * Not a sentence and not composed — a value the responder sent, echoed verbatim, the same
 * provenance rule `val()`/`srv()` follow above. It is separated from the sentence so that
 * "the text is always a CHROME constant" stays literally true and testable.
 *
 * Silent when it says nothing: absent (some deployments strip it), or our own server, in which
 * case the sentence already covers it. `Server: squid/5.7` next to a failure, on the other
 * hand, is the single most useful fact on the screen.
 */
export function fetchFailureEvidence(failure) {
  const server = failure && failure.server ? String(failure.server).trim() : '';
  if (!server || /uvicorn/i.test(server)) return null;
  // A response header is input from whoever answered, which is exactly the party in question
  // when this fires. It is a hint on one line, so it is capped at one line's worth.
  return server.slice(0, 40);
}

/** The failure line as rendered: the sentence, plus the evidence when there is any. */
export function fetchFailureLine(failure, fallback = CHROME.FETCH_FAILED) {
  const text = fetchFailureText(failure, fallback);
  const evidence = fetchFailureEvidence(failure);
  return evidence ? `${text} (${evidence})` : text;
}

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

// THE FOUR TAGGERS ARE EXPORTED, NOT COPIED.
//   They were private while this was the only surface with the discipline. `retroactive_view.js`
//   is the second one, and the alternative to exporting them was four three-line functions
//   duplicated into it — which is how `DUPLICATION_LEDGER.md` entries start. The tag vocabulary
//   (`TEXT_SOURCES`) already lives here and both harnesses read it from here, so the taggers that
//   produce those tags belong in the same place. Nothing about the config-resolve view changed.

/** A string the SERVER wrote. Rendered verbatim, never reworded. */
export function srv(value) {
  return { src: 'server', text: String(value) };
}

/** A payload VALUE, spelled in JSON — the syntax of the file the operator edited.
 *  (`_as_json` on the server side does the same thing for the same reason.) */
export function val(value) {
  return { src: 'value', text: JSON.stringify(value), raw: value };
}

export function chrome(text) {
  return { src: 'chrome', text };
}

export function count(n) {
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

/**
 * C-87. 도메인 -> 그 «걸음». 번호도 이름도 «서버의 목록»(`vocabulary.setup_steps`)에서 옵니다.
 *
 * 🔴 한 자리에서만 읽습니다. 도메인 봉투도 `step` 을 싣지만, 둘 다 읽으면 화면이 「번호는
 *    이쪽, 이름은 저쪽」이 되고 두 자리가 갈라질 수 있습니다 — 서버에서는 한 표에서 나온
 *    값이라 갈리지 않지만, 갈릴 «수» 있는 구조를 만드는 것이 criterion ④ 입니다.
 * 🔴 이름은 «서버 문자열»입니다. 「표」·「파생」을 여기 적으면 걸음이 하나 늘 때 화면이 모릅니다.
 */
function stepIndex(vocabulary) {
  const out = new Map();
  for (const item of list(vocabulary && vocabulary.setup_steps)) {
    if (!item || item.domain == null) continue;
    out.set(String(item.domain), item);
  }
  return out;
}

/** 걸음이 없는 도메인은 «맨 뒤»입니다. 0 이 아니라 뒤 — 없는 것은 첫 걸음이 아닙니다. */
const LAST = Number.MAX_SAFE_INTEGER;
const stepRank = (item) => (item && item.step != null ? Number(item.step) : LAST);

function buildDomain(domain, populations, stepItem) {
  const name = domain && domain.domain != null ? String(domain.domain) : '';
  const blocked = domain && domain.blocked_by != null ? domain.blocked_by : null;
  return {
    name,
    // C-87. 걸음의 번호·이름, 그리고 「무엇을 기다리나」. 셋 다 없을 수 있고, 없으면 null 입니다.
    step: stepItem && stepItem.step != null ? val(stepItem.step) : null,
    stepName: stepItem && stepItem.name != null ? srv(stepItem.name) : null,
    unstepped: !stepItem,
    blockedLabel: blocked === null ? null : chrome(CHROME.STEP_BLOCKED),
    blockedBy: blocked === null ? null : val(blocked),
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
  const steps = stepIndex(vocabulary);
  // C-87. 걸음 «순서»로 세웁니다. 서버가 보낸 순서가 아니라 서버가 «말한 순서»입니다 — 그리고
  // 번호가 없는 도메인은 뒤에, 받은 순서 그대로(`sort` 는 안정 정렬입니다).
  const domains = list(report && report.domains).slice().sort(
    (a, b) => stepRank(steps.get(String(a && a.domain)))
            - stepRank(steps.get(String(b && b.domain))));
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
    domains: domains.map((d) => buildDomain(d, populations, steps.get(String(d && d.domain)))),
    // 걸음 밖 무리가 «있을 때만» 그 이름이 있습니다. 비어 있는 구분선은 없는 무리를 있는 것처럼
    // 그립니다.
    unsteppedLabel: domains.some((d) => !steps.get(String(d && d.domain)))
      ? chrome(CHROME.UNSTEPPED) : null,
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
