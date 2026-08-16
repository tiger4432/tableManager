// LEDGER SETUP — the view model for the admin ledger declaration screens.
//
// WHY THIS IS A SEPARATE, DOM-FREE MODULE.
//   Same discipline as `config_resolve_view.js`, and for the same reason: the load-bearing half
//   of this seam is NEGATIVE. Every sentence an operator reads on these screens — the label of a
//   kind, the reason a declaration was refused, the account of what a dry run produced — is
//   written by the server. The client owns structure, colour and counts. Nothing here composes a
//   reason, and nothing here keeps a copy of the ledger's vocabulary: the predicates, the entity
//   types, the object kinds, the walk directions, the traversable states, the signature a new
//   predicate must fill, the columns a kind requires — all of it arrives in the payload and the
//   form is GENERATED from it. A client-side copy of any of those lists would be a second
//   vocabulary that drifts from the one the gate enforces.
//
//   The four taggers (`srv`/`val`/`chrome`/`count`) are imported rather than re-declared so the
//   provenance vocabulary has exactly one home.
//
// THE ONE THING THE CLIENT DECIDES: which widget draws a field. That is presentation, and every
// widget's OPTIONS come from the payload. An unrecognised field falls back to a text box rather
// than being dropped — a field the screen cannot draw is still a field the server requires.

import { srv, val, chrome, count } from './config_resolve_view.js';

export { srv, val, chrome, count };

/** Client-authored strings. Structural labels only — never a verdict, never a reason. */
export const LEDGER_CHROME = Object.freeze({
  RELATION: '테이블',
  RELATION_SEARCH: '테이블 이름 검색',
  RELATION_COLUMNS: '컬럼',
  RELATION_TRUNCATED: '목록이 잘렸습니다 — 검색어를 좁히세요',
  UNDECLARED: '미선언',
  MISSING_RELATION: '실재 없음',
  DECLARED_TOTAL: '선언된 표',
  KIND: 'kind',
  UNSUPPORTED: '미지원',
  NO_KIND_FIT: '어느 kind 모양에도 안 맞으면 저장하지 않는다 — 새 kind 판정 사안.',

  COLUMNS: '컬럼 매핑',
  REQUIRED: '필수',
  OPTIONAL: '선택',
  BLOCKS: '블록',
  BLOCK_JSON: 'JSON',
  OCCURRED_AT: '시각',
  OCCURRED_AT_COLUMN: 'occurred_at 컬럼',
  OCCURRED_AT_FORMAT: '포맷',
  OCCURRED_AT_TIMEZONE: '타임존',
  SUBJECT_TYPES: 'subject_types',
  REGISTER_TYPES: 'register_entity_types',
  WATERMARK: '워터마크 컬럼',
  ADD: '＋',
  REMOVE: '−',

  NAME: '이름',
  PREDICATE_NEW: '술어 등재',
  EDITABLE: '편집 가능',
  READ_ONLY: '읽기 전용',
  LOAD_INTO_FORM: '폼에 불러오기',
  RETIRE: '은퇴',
  RETIRE_SUPERSEDED_BY: 'superseded_by',
  NULL_OPTION: '없음 (null)',
  UNSET_OPTION: '미선택',

  DRY_RUN: '드라이런',
  DRY_RUN_RUNNING: '드라이런 실행 중…',
  DRY_RUN_TRUNCATED: '표본이 잘렸습니다',
  DRY_RUN_PROBES: '이 서명이 받는 원자 · 거절하는 원자',
  PROBE_ACCEPTED: '받음',
  PROBE_REFUSED: '거절',
  DRY_RUN_ATOM_LIST: '원자 봉투',
  DRY_RUN_REFUSALS: '거절',
  DRY_RUN_STALE: '폼이 바뀌었습니다 — 다시 드라이런',
  READ_ONLY_ENFORCED: 'read_only_enforced',
  SOURCE_CONTRACT: 'Source Contract',
  TRANSLATOR_PROFILE: '번역 프로필',
  MOLECULE: '분자 단위',
  OPERATOR: '변환 방식',
  POSSIBLE_CLAIMS: '생성 가능 Claim',
  CONFIGURED_BY: '설정 위치',
  VOCABULARY_SIGNATURE: 'vocabulary 서명',

  SAVE: '저장',
  SAVING: '저장 중…',
  RESOLVE: '먹었는가',
  MODE_FORM: '폼',
  MODE_RAW: '원본 JSON',
  RAW_CONTEXT: '같은 파일의 다른 선언',
  RAW_LOADING: '불러오는 중…',

  VIOLATIONS: '거절 사유',
  // 「조회 실패」 itself is NOT here — it is `CHROME.FETCH_FAILED` in `config_resolve_view.js`,
  // and it is imported rather than respelled. The four failure sentences (unreachable / old
  // server / rejected token / something-else-answered) are one table for the whole admin, and a
  // second spelling of any of them is a second answer to the same question.
  DRY_RUN_FAILED: '드라이런 요청 실패',
  SAVE_FAILED: '저장 요청 실패',
  RETIRE_FAILED: '은퇴 요청 실패',
  NO_RELATIONS: '검색과 일치하는 테이블이 없습니다.',
  NO_PREDICATES: '서버가 보고한 술어가 없습니다.',
});

export const LEDGER_CHROME_STRINGS = Object.freeze(Object.values(LEDGER_CHROME));

// ── normalisers ──────────────────────────────────────────────
// The payload's item shapes are the server's to choose. A required column may arrive as a bare
// name or as an object carrying its own Korean label; both are read the same way here so a
// shape change on that side is not a blank screen on this one.

function list(value) {
  return Array.isArray(value) ? value : [];
}

/** `"row_identity"` or `{name, label_ko, ...}` → a name plus whatever label the server sent. */
export function named(entry) {
  if (entry === null || entry === undefined) return null;
  if (typeof entry === 'string' || typeof entry === 'number') {
    return { name: String(entry), label: null, fields: [], raw: entry };
  }
  if (typeof entry !== 'object') return null;
  const name = entry.name !== undefined ? entry.name
    : (entry.key !== undefined ? entry.key : entry.id);
  if (name === undefined || name === null) return null;
  return {
    name: String(name),
    label: entry.label_ko != null ? srv(entry.label_ko) : null,
    // A block that describes its own fields gets real inputs; one that does not gets JSON.
    fields: list(entry.fields).map(named).filter(Boolean),
    raw: entry,
  };
}

function namedList(value) {
  return list(value).map(named).filter(Boolean);
}

/** The label to show for a named thing: the server's when it sent one, else the name itself. */
export function nameText(entry) {
  return entry && entry.label ? entry.label.text : (entry ? entry.name : '');
}

// ── relations (`GET /admin/ledger/relations`) ────────────────

/** One `{name, detail_ko}` entry — the shape both `undeclared` and `missing_relations` use. */
function relationNote(entry) {
  const e = named(entry);
  if (!e) return null;
  const raw = e.raw && typeof e.raw === 'object' ? e.raw : {};
  return {
    name: srv(e.name),
    detail: raw.detail_ko != null ? srv(raw.detail_ko) : null,
  };
}

/** The picker lists only tables `table_config` declares — 19 today, not everything
 *  `information_schema` returns. A table the rest of the system does not know about has no
 *  keys, no ingestion and no chain, so an atom about its rows would be about something nothing
 *  else can address.
 *
 *  🔴 THE NOT-DECLARED CASE IS A LIST OF SENTENCES, NOT AN EMPTY RESULT. `undeclared[]` carries
 *  one `{name, detail_ko}` per undeclared match, and ALL of them render. A search matching three
 *  undeclared tables that showed only the first would be a silent cap on exactly the screen
 *  whose job is to say what is missing.
 *
 *  There is no `notice_ko` and no top-level `detail_ko` on this route — an earlier version of
 *  this function read for both and fell through to the real path, which works and is still
 *  wrong: a dead branch in a tolerant chain looks like coverage and is not. It reads one path
 *  now, and if that path moves the screen goes visibly empty instead of quietly half-right.
 *
 *  The client's own 「일치하는 테이블이 없습니다」 survives only for the genuine no-match case —
 *  nothing declared matched AND nothing undeclared matched either. */
export function buildRelationsView(payload) {
  const p = payload && typeof payload === 'object' ? payload : {};
  const undeclared = list(p.undeclared).map(relationNote).filter(Boolean);
  // Declared in `table_config` but not physically in the database — the opposite failure, and
  // the operator's next step is a different one, so it is not folded in with `undeclared`.
  const missing = list(p.missing_relations).map(relationNote).filter(Boolean);
  return {
    undeclared,
    missing,
    // How many tables the picker could ever offer. Shown so an operator who sees four results
    // knows whether that is the whole world or a filtered slice of it.
    declaredTotal: p.declared_total === undefined ? null : count(Number(p.declared_total) || 0),
    relations: list(payload && payload.relations).map((rel) => ({
      name: rel && rel.name != null ? srv(rel.name) : null,
      key: rel && rel.name != null ? String(rel.name) : '',
      columns: list(rel && rel.columns).map((col) => ({
        name: col && col.name != null ? srv(col.name) : null,
        key: col && col.name != null ? String(col.name) : '',
        type: col && col.type != null ? srv(col.type) : null,
      })),
      columnCount: count(list(rel && rel.columns).length),
    })),
    truncated: Boolean(payload && payload.truncated),
    truncatedText: chrome(LEDGER_CHROME.RELATION_TRUNCATED),
    empty: list(payload && payload.relations).length === 0,
    // The one sentence on this surface the client writes, and only for the genuine no-match:
    // nothing declared matched AND the server named nothing undeclared or missing either.
    emptyText: (undeclared.length || missing.length)
      ? null : chrome(LEDGER_CHROME.NO_RELATIONS),
    undeclaredLabel: chrome(LEDGER_CHROME.UNDECLARED),
    missingLabel: chrome(LEDGER_CHROME.MISSING_RELATION),
    declaredTotalLabel: chrome(LEDGER_CHROME.DECLARED_TOTAL),
  };
}

// ── sources (`GET /admin/ledger/sources`) ────────────────────

/** Block ids this screen draws with a dedicated widget rather than a JSON box.
 *
 * These are not a copy of anything the server owns — the ids arrive in `required_blocks` and a
 * block that is NOT in this table still renders (as JSON, or as its own declared fields). This
 * only says which four the screen already has a nicer control for. */
export const STANDARD_BLOCKS = Object.freeze(
  ['occurred_at', 'subject_types', 'register_entity_types', 'watermark']);

export function buildSourcesView(payload) {
  const kinds = namedList(payload && payload.kinds).map((kind) => {
    const raw = kind.raw && typeof kind.raw === 'object' ? kind.raw : {};
    const blocks = namedList(raw.required_blocks);
    const translator = raw.translator && typeof raw.translator === 'object'
      ? raw.translator : {};
    return {
      key: kind.name,
      label: kind.label,
      name: srv(kind.name),
      required: namedList(raw.required_columns),
      optional: namedList(raw.optional_columns),
      blocks,
      translator: {
        profile: val(translator.profile),
        molecule: translator.molecule != null ? srv(translator.molecule) : null,
        operator: translator.operator != null ? srv(translator.operator) : null,
        implementation: val(translator.implementation),
      },
      // Drawn by the standard sections below the column grid; not repeated as JSON boxes.
      extraBlocks: blocks.filter((b) => !STANDARD_BLOCKS.includes(b.name)),
      standardBlocks: blocks.filter((b) => STANDARD_BLOCKS.includes(b.name)).map((b) => b.name),
    };
  });
  return {
    kinds,
    unsupported: namedList(payload && payload.unsupported_kinds).map((kind) => ({
      key: kind.name,
      name: srv(kind.name),
      label: kind.label,
      // The server's sentence about why this kind cannot be offered. Rendered verbatim.
      detail: kind.raw && kind.raw.detail_ko != null ? srv(kind.raw.detail_ko) : null,
    })),
    sources: (payload && payload.sources) || {},
    sourceNames: Object.keys((payload && payload.sources) || {}).sort(),
    configPath: payload && payload.config_path != null ? srv(payload.config_path) : null,
  };
}

// ── vocabulary (`GET /admin/ledger/vocabulary`) ──────────────

/** PRESENTATION ONLY — the colour a status or an origin is drawn in.
 *  An unknown word draws neutral instead of being guessed at. */
const STATUS_TONE = { active: 'ok', reserved: 'warn', retired: 'muted' };
const ORIGIN_TONE = { code: 'muted', config: 'ok' };

export function buildVocabularyView(payload) {
  const p = payload || {};
  return {
    predicates: list(p.predicates).map((pred) => {
      const e = pred || {};
      const object = e.object && typeof e.object === 'object' ? e.object : null;
      return {
        key: e.name != null ? String(e.name) : '',
        name: e.name != null ? srv(e.name) : null,
        label: e.label_ko != null ? srv(e.label_ko) : null,
        origin: e.origin != null ? srv(e.origin) : null,
        originTone: ORIGIN_TONE[String(e.origin)] || '',
        layer: e.layer != null ? srv(e.layer) : null,
        status: e.status != null ? srv(e.status) : null,
        statusTone: STATUS_TONE[String(e.status)] || '',
        since: e.since != null ? srv(e.since) : null,
        subject: list(e.subject).map(srv),
        objectKind: object && object.kind != null ? srv(object.kind) : null,
        objectRequired: object ? list(object.required).map(srv) : [],
        objectTypes: object ? list(object.types).map(srv) : [],
        objectNull: Object.prototype.hasOwnProperty.call(e, 'object') && e.object === null,
        qualifiers: list(e.qualifiers).map(srv),
        // A tri-state, rendered as the value the server sent — JSON spelling, so `null` reads
        // as `null` and not as an empty cell that could mean anything.
        traversable: val(e.traversable === undefined ? null : e.traversable),
        direction: e.direction != null ? srv(e.direction) : null,
        supersededBy: e.superseded_by != null ? srv(e.superseded_by) : null,
        // TRUE ONLY FOR origin == "config". Canonical is read-only and so is code-loaded
        // ontology, because code is code. The client does not re-derive this.
        editable: e.editable === true,
        raw: e,
      };
    }),
    entityTypes: namedList(p.entity_types),
    objectKinds: namedList(p.object_kinds),
    walkDirections: namedList(p.walk_directions),
    traversableStates: list(p.traversable_states).map((s) => {
      const entry = named(s);
      if (!entry) return null;
      const raw = entry.raw && typeof entry.raw === 'object' ? entry.raw : {};
      // The value carried by a traversable state is a tri-state, and `false`/`null` are
      // meaningful — so the state's own `value` wins whenever it was sent, and only a state
      // that sent none falls back to its name.
      const hasValue = Object.prototype.hasOwnProperty.call(raw, 'value');
      return {
        name: entry.name,
        label: entry.label,
        value: hasValue ? raw.value : parseTriState(entry.name),
      };
    }).filter(Boolean),
    statuses: namedList(p.statuses),
    // EXACTLY what a new predicate must supply. The form is generated from this list; a field
    // the screen has never heard of still gets an input.
    signatureFields: namedList(p.signature_fields),
    configPath: p.config_path != null ? srv(p.config_path) : null,
    editableLayer: p.editable_layer != null ? String(p.editable_layer) : '',
    editableLayerText: p.editable_layer != null ? srv(p.editable_layer) : null,
    empty: list(p.predicates).length === 0,
    emptyText: chrome(LEDGER_CHROME.NO_PREDICATES),
  };
}

/** `"true"`/`"false"`/`"null"` → the value. Only used for a state that sent no `value`. */
function parseTriState(word) {
  const w = String(word).toLowerCase();
  if (w === 'true') return true;
  if (w === 'false') return false;
  if (w === 'null' || w === 'none') return null;
  return word;
}

// ── dry run (`POST /admin/ledger/dry-run`) ───────────────────

/** The five counters, labelled with the WIRE NAMES the server sent them under.
 *
 * A Korean label here would be a translation this client invented, and it would be wrong half
 * the time: for `target:"predicate"` the same five fields count EXISTING atoms the new
 * signature would accept or refuse, not rows a translator read. The meaning of the numbers is
 * in `sentence_ko`, which the server writes. The keys are the server's own words, so they are
 * safe to print as they are — and they stay correct for both targets. */
const DRY_RUN_COUNTERS = Object.freeze(
  ['rows_read', 'molecules', 'atoms', 'refused_molecules', 'writes']);

/** Source declaration + executable translator + live vocabulary, compiled by the server.
 *
 * This is intentionally a read model.  The client does not infer what a translator can emit
 * from sampled atoms: a branch may simply be absent from the first 20 rows.  `emissions` is the
 * server's complete profile contract; the atoms remain the empirical preview beneath it.
 */
export function buildSourceContractView(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const translator = payload.translator && typeof payload.translator === 'object'
    ? payload.translator : {};
  return {
    title: chrome(LEDGER_CHROME.SOURCE_CONTRACT),
    sentence: payload.sentence_ko != null ? srv(payload.sentence_ko) : null,
    state: val(payload.state),
    translator: {
      profile: val(translator.profile),
      molecule: translator.molecule != null ? srv(translator.molecule) : null,
      operator: translator.operator != null ? srv(translator.operator) : null,
      implementation: val(translator.implementation),
    },
    labels: {
      profile: chrome(LEDGER_CHROME.TRANSLATOR_PROFILE),
      molecule: chrome(LEDGER_CHROME.MOLECULE),
      operator: chrome(LEDGER_CHROME.OPERATOR),
      claims: chrome(LEDGER_CHROME.POSSIBLE_CLAIMS),
      configuredBy: chrome(LEDGER_CHROME.CONFIGURED_BY),
      signature: chrome(LEDGER_CHROME.VOCABULARY_SIGNATURE),
    },
    emissions: list(payload.emissions).map((entry) => ({
      predicate: val(entry && entry.predicate),
      state: val(entry && entry.state),
      subjects: val(entry && entry.subject_types),
      objectKind: val(entry && entry.object_kind),
      objectTypes: val(entry && entry.object_types),
      qualifiers: val(entry && entry.qualifiers),
      derivations: val(entry && entry.derivations),
      eventTypes: val(entry && entry.event_types),
      configuredBy: val(entry && entry.configured_by),
      vocabulary: val(entry && entry.vocabulary),
      issues: list(entry && entry.issues).map((issue) => ({
        code: val(issue && issue.code),
        detail: issue && issue.detail_ko != null ? srv(issue.detail_ko) : null,
      })),
    })),
  };
}

export function buildDryRunView(payload) {
  const p = payload || {};
  return {
    // The server's one-sentence account. Verbatim.
    sentence: p.sentence_ko != null ? srv(p.sentence_ko) : null,
    facts: DRY_RUN_COUNTERS.filter((key) => p[key] !== undefined).map((key) => {
      const n = Number(p[key]) || 0;
      let tone = '';
      if (key === 'refused_molecules') tone = n > 0 ? 'warn' : '';
      // A dry run that wrote is not a dry run. Non-zero draws red without a sentence being
      // invented for it — the number says it.
      if (key === 'writes') tone = n === 0 ? 'ok' : 'danger';
      return { key, value: count(n), tone };
    }),
    readOnlyLabel: chrome(LEDGER_CHROME.READ_ONLY_ENFORCED),
    readOnly: val(p.read_only_enforced === undefined ? null : p.read_only_enforced),
    readOnlyTone: p.read_only_enforced === true ? 'ok' : 'danger',
    // THE ATOMS AS THEY ARE. Envelope order, envelope spelling, nothing folded away. The screen
    // is showing the translator's output, and a prettier shape would be a different claim.
    //
    // `atoms` is the COUNT and `atoms_rendered` is the list — a predicate dry run answers
    // `atoms: 0, atoms_rendered: []` because there is no emitter for a word nobody has used
    // yet. The `Array.isArray` fallback is for the case where the two names ever collapse back
    // into one: a screen that reads a number as a list draws nothing and says nothing.
    atoms: list(Array.isArray(p.atoms_rendered) ? p.atoms_rendered
      : (Array.isArray(p.atoms) ? p.atoms : [])).map((atom) => val(atom)),
    atomsLabel: chrome(LEDGER_CHROME.DRY_RUN_ATOM_LIST),

    // A PREDICATE dry run runs THE GATE'S OWN JUDGING FUNCTION over the candidate signature and
    // reports what it accepted and refused. It is the gate, not a description of one — so the
    // cases and the violation strings are rendered exactly as they arrived.
    probesLabel: chrome(LEDGER_CHROME.DRY_RUN_PROBES),
    probes: list(p.signature_probes).map((probe) => ({
      caseText: probe && probe.case_ko != null ? srv(probe.case_ko) : null,
      accepted: probe ? probe.accepted === true : false,
      acceptedValue: val(probe ? probe.accepted : null),
      violations: list(probe && probe.violations).map(srv),
    })),
    truncated: Boolean(p.truncated),
    truncatedText: chrome(LEDGER_CHROME.DRY_RUN_TRUNCATED),
    refusalsLabel: chrome(LEDGER_CHROME.DRY_RUN_REFUSALS),
    refusals: list(p.refusals).map((r) => ({
      reason: r && r.reason != null ? srv(r.reason) : null,
      detail: r && r.detail_ko != null ? srv(r.detail_ko) : null,
      moleculeRef: r && r.molecule_ref != null ? val(r.molecule_ref) : null,
    })),
    sourceContract: buildSourceContractView(p.source_contract),
    // Not rendered. The proof that a dry run of THIS declaration happened.
    token: p.token != null ? String(p.token) : '',
  };
}

// ── raw source declaration ───────────────────────────────────

/** The raw read for ONE source — the declaration, plus the file around it for context.
 *
 * 🔴 PER SOURCE, NOT WHOLE FILE. Whole-file writing makes two operators on two unrelated tables
 * collide by construction: both read the file, both write it, and the second erases the first
 * even though they never touched the same declaration. The file stays READABLE for context; it
 * is not the unit of writing.
 *
 * 🔴 `base` IS THE FINGERPRINT AND IT IS NOT OPTIONAL FOR THIS PATH. The strict admin token is
 * authentication — it says who you are, never what you read. Two operators holding the same
 * valid token who open the same declaration will both save, and the second silently erases the
 * first. `base` is what makes that collision a named refusal (`stale_base`) instead of a quiet
 * loss. It is checked only when sent, which is exactly why the raw editor must always send it:
 * an omitted fingerprint is not a safe default, it is the old behaviour back.
 */
export function buildRawView(payload) {
  const p = payload || {};
  return {
    // `raw` is the server's own serialisation of this ONE declaration. Taken as sent — a client
    // that re-serialised `declaration` would show the operator different characters than the
    // ones the fingerprint was taken over.
    text: typeof p.raw === 'string' ? p.raw : '',
    path: p.config_path != null ? srv(p.config_path) : null,
    readPath: p.read_path != null ? srv(p.read_path) : null,
    // The server's sentence about why the unit is one source. Rendered verbatim.
    note: p.note_ko != null ? srv(p.note_ko) : null,
    // The OTHER declarations in the file — names only. The route does not return the file's
    // text (its docstring says `document`, its payload sends `sources`), so the context this
    // screen can honestly show is "what else is in here", not the file itself. Showing an empty
    // 「파일 전체」 box would claim a context that was never sent.
    siblings: list(p.sources).map((s) => String(s)),
    // A read that failed says so, in the server's words, instead of presenting an empty editor
    // that looks like an empty declaration.
    error: p.error != null ? srv(p.error) : null,
    // Opaque. The client never derives, compares or regenerates it — it round-trips.
    base: p.base != null ? String(p.base) : '',
  };
}

// ── save (`POST /admin/ledger/save`) ─────────────────────────

/** Wire names again, and only the ones the response actually carried — `POST .../retire` shares
 *  this renderer and it is not obliged to answer with the same three facts a save does. A `null`
 *  printed for a key nobody sent is a fact the screen made up. */
const SAVE_FACTS = Object.freeze(['saved', 'backup', 'reloaded']);

export function buildSaveView(payload) {
  const p = payload || {};
  return {
    sentence: p.sentence_ko != null ? srv(p.sentence_ko) : null,
    facts: SAVE_FACTS.filter((key) => p[key] !== undefined)
      .map((key) => ({ key, value: val(p[key]) })),
    resolveLabel: chrome(LEDGER_CHROME.RESOLVE),
    // Handed straight to `buildConfigResolveView` — the ONE 「먹었는가」 judge, not a second one.
    resolve: p.resolve || null,
  };
}

// ── refusals — identical shape on all three writes ───────────

/** `{ok:false, target, name, violations:[{code, field, detail_ko}]}`.
 *
 * NESTED UNDER `detail`. FastAPI's `HTTPException` wraps whatever it is given, so the wire body
 * is `{"detail": {"ok": false, "violations": [...]}}`. Reading the un-nested path renders every
 * refusal as NOTHING — the screen would go quiet exactly when the server had something to say,
 * which is the failure this whole design exists to prevent. The unwrap is done here, once, and
 * it tolerates both shapes so the screen does not depend on which layer wrapped it.
 *
 * `detail_ko` IS the reason. It is rendered verbatim and the client never maps `code` to
 * wording of its own: a screen that can invent a reason invents a wrong one exactly when the
 * server's reason was the interesting one. `code` is shown as the server's own word, as data,
 * and `field` is used only to decide WHICH INPUT the message hangs off.
 */
/** The refusal object out of a 400 body, whichever layer wrapped it. */
export function unwrapRefusal(body) {
  const b = body && typeof body === 'object' ? body : {};
  if (b.detail && typeof b.detail === 'object' && Array.isArray(b.detail.violations)) {
    return b.detail;
  }
  return b;
}

/** True when a 400 body carries a refusal this screen can render. */
export function hasViolations(body) {
  return Array.isArray(unwrapRefusal(body).violations);
}

export function buildViolationsView(body) {
  const b = unwrapRefusal(body);
  return {
    label: chrome(LEDGER_CHROME.VIOLATIONS),
    target: b.target != null ? srv(b.target) : null,
    name: b.name != null ? srv(b.name) : null,
    // NOTE FOR WHOEVER COMES NEXT: the closed code set is SERVED — `refusal_codes` on
    // `GET /admin/ledger/vocabulary`. Nothing in this file branches on `code`, which is why no
    // copy of that set exists here. If a screen ever needs to branch, read it from the payload.
    violations: list(b.violations).map((v) => ({
      code: v && v.code != null ? srv(v.code) : null,
      field: v && v.field != null ? String(v.field) : '',
      detail: v && v.detail_ko != null ? srv(v.detail_ko) : null,
    })),
    count: count(list(b.violations).length),
  };
}

// ── declaration identity — what makes a dry-run token stale ──

/** A stable string for a declaration, so "the form changed" is a comparison and not a guess.
 *
 * Key order in an object literal is not part of what an operator declared, so it is sorted out
 * of the comparison; array order IS (a column list is positional), so it is kept.
 */
export function declarationKey(value) {
  return stable(value);
}

function stable(value) {
  if (value === null || value === undefined) return 'null';
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  if (typeof value === 'object') {
    return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${stable(value[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/** Every text carrier in a view tree, in document order. Same helper the config report uses. */
export { collectTexts } from './config_resolve_view.js';
