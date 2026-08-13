// ============================================================
// ledger_trace_view.js — the lineage answer as DOM.
//
// `document` IS AN ARGUMENT, not a global. That is what lets
// `tests/ledger_trace_harness.mjs` drive the real renderer under bare node and
// assert what actually reaches the screen, instead of asserting that a function
// exists. Everything here builds nodes and sets `textContent`; nothing touches
// `innerHTML`, so a lot id out of the ledger can never be markup.
//
// It renders and nothing else — no fetching, no state, no decisions. Which hop
// won is the server's answer (`server/ledger_trace.py`) and how it reads is
// `ledger_trace_core.js`.
// ============================================================
import {
  hopVerdict, hopBasis, basisLabel, hopQuestion, hopAnswer, hopAnswerContext,
  nodeText, instantText, summarize, terminalVerdict,
  coverageVerdict, coverageFacts, coverageSamples,
} from './ledger_trace_core.js';

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clear(mount) {
  while (mount.firstChild) mount.removeChild(mount.firstChild);
}

// The summary chips. Zero-valued ones are OMITTED rather than shown as 0: a row
// of zeroes is four things to read past on the way to the one number that is not
// zero, and 확정 is the only count that is always meaningful.
function renderSummary(doc, trace, subjectText) {
  const s = summarize(trace);
  const head = el(doc, 'header', 'lt-head');
  head.appendChild(el(doc, 'div', 'lt-head__subject', subjectText));

  const chips = el(doc, 'div', 'lt-chips');
  const chip = (tone, text) => {
    const c = el(doc, 'span', `lt-chip lt-chip--${tone}`, text);
    c.setAttribute('data-chip', tone);
    chips.appendChild(c);
  };
  chip('lots', `랏 ${s.lots}`);
  chip('ok', `확정 ${s.resolved}`);
  if (s.candidate > 0) chip('contested', `이견 ${s.candidate}`);
  if (s.unresolvable > 0) chip('gap', `미확정 ${s.unresolvable}`);
  // 🔴 The count that justifies the screen. Shown whenever it is non-zero, and
  // never folded into 확정 — a hop the ledger only believes under a declared
  // assumption is not the same fact as one a source uttered.
  if (s.convention > 0) chip('convention', `가정 ${s.convention}`);
  head.appendChild(chips);
  return head;
}

function renderHop(doc, hop, ordinal) {
  const verdict = hopVerdict(hop);
  const basis = hopBasis(hop && hop.reason);
  const isConvention = !!basis && basis.kind === 'convention';

  const item = el(doc, 'li',
    `lt-hop lt-hop--${verdict.tone}${isConvention ? ' lt-hop--convention' : ''}`);
  // Hooks for the harness and for anyone reading the DOM. They carry the
  // SERVER'S words (`state`, `predicate`) plus the one thing the screen derives.
  item.setAttribute('data-state', verdict.state);
  item.setAttribute('data-tone', verdict.tone);
  item.setAttribute('data-predicate', String((hop && hop.predicate) || ''));
  item.setAttribute('data-basis', isConvention ? 'convention' : (basis ? 'basis' : 'none'));

  item.appendChild(el(doc, 'div', 'lt-hop__rail'));

  const body = el(doc, 'div', 'lt-hop__body');

  const top = el(doc, 'div', 'lt-hop__top');
  top.appendChild(el(doc, 'span', 'lt-hop__ordinal', `${ordinal}`));
  top.appendChild(el(doc, 'span', 'lt-hop__from', nodeText(hop && hop.from)));
  top.appendChild(el(doc, 'span', 'lt-hop__q', hopQuestion(hop)));
  body.appendChild(top);

  const line = el(doc, 'div', 'lt-hop__answer');
  const badge = el(doc, 'span', `lt-badge lt-badge--${verdict.tone}`, verdict.label);
  badge.setAttribute('data-verdict', verdict.label);
  line.appendChild(badge);

  const answer = hopAnswer(hop);
  const value = el(doc, 'span',
    `lt-hop__value${answer === null ? ' lt-hop__value--none' : ''}`,
    answer === null ? '—' : answer);
  value.setAttribute('data-answer', answer === null ? '' : answer);
  line.appendChild(value);

  const context = hopAnswerContext(hop);
  if (context) line.appendChild(el(doc, 'span', 'lt-hop__context', context));

  const label = basisLabel(basis);
  if (label) {
    const chip = el(doc, 'span', `lt-basis lt-basis--${label.kind}`, label.text);
    chip.setAttribute('data-basis-kind', label.kind);
    line.appendChild(chip);
  }
  body.appendChild(line);

  // 🔴 THE SERVER'S SENTENCE, VERBATIM. It is the only place the operator learns
  // WHY, and a sentence composed here would be a second explanation that drifts
  // from the one the resolver actually applied.
  body.appendChild(el(doc, 'p', 'lt-hop__reason', String((hop && hop.reason) || '')));

  const meta = [];
  if (hop && hop.occurred_at) meta.push(instantText(hop.occurred_at));
  if (hop && hop.event_id) meta.push(String(hop.event_id));
  if (meta.length) body.appendChild(el(doc, 'div', 'lt-hop__meta', meta.join('  ·  ')));

  item.appendChild(body);
  return item;
}

function renderTerminal(doc, trace) {
  const reason = String((trace && trace.terminal_reason) || '');
  const verdict = terminalVerdict(reason);
  const box = el(doc, 'div', `lt-terminal lt-terminal--${verdict.tone}`);
  box.setAttribute('data-terminal-tone', verdict.tone);
  box.appendChild(el(doc, 'span', `lt-badge lt-badge--${verdict.tone}`, verdict.label));
  box.appendChild(el(doc, 'p', 'lt-terminal__reason', reason));
  return box;
}

/**
 * Render one whole answer into `mount`.
 *
 * 🔴 A trace with hops is NEVER an empty state, whatever the states of those
 * hops are. The server cannot return an empty `hops` list by construction, and a
 * screen that painted "결과 없음" over an all-`unresolvable` answer would be
 * discarding the answer — where the chain breaks, and why, is the product.
 */
export function renderTrace(doc, mount, trace, subjectText, nothing) {
  clear(mount);
  const wrap = el(doc, 'section', 'lt-answer');
  wrap.setAttribute('data-answer-kind', 'trace');
  wrap.appendChild(renderSummary(doc, trace, subjectText));

  // WHICH nothing this is, when it is one — above the chain, because it changes
  // what the chain below MEANS. On an empty ledger every hop reads "원장에 원자
  // 0" and that sentence is about the ledger, not about the lot; without this
  // line the operator reads a deployment state as a data boundary. `title: null`
  // (the unknown-lot case) renders nothing: the hops already say it.
  if (nothing && nothing.title) {
    const box = el(doc, 'div', `lt-nothing lt-nothing--${nothing.tone || 'gap'}`);
    box.setAttribute('data-nothing', String(nothing.kind || ''));
    box.appendChild(el(doc, 'span', `lt-badge lt-badge--${nothing.tone || 'gap'}`, nothing.title));
    if (nothing.detail) box.appendChild(el(doc, 'p', 'lt-nothing__detail', nothing.detail));
    wrap.appendChild(box);
  }

  const chain = el(doc, 'ol', 'lt-chain');
  const hops = trace && Array.isArray(trace.hops) ? trace.hops : [];
  hops.forEach((hop, i) => chain.appendChild(renderHop(doc, hop, i + 1)));
  wrap.appendChild(chain);

  wrap.appendChild(renderTerminal(doc, trace));

  if (trace && trace.generated_at) {
    wrap.appendChild(el(doc, 'div', 'lt-generated',
      `조회 ${instantText(trace.generated_at)}`));
  }
  mount.appendChild(wrap);
  return wrap;
}

/**
 * A notice — the states that are NOT an answer: nothing asked yet, in flight,
 * or the server refusing.
 *
 * `detail` is printed verbatim when it comes from the server. A refusal reworded
 * here reads exactly like a real answer and cannot be traced back to what the
 * server actually said.
 */
/**
 * The empty state — the screen BEFORE a question, answering "what can I ask".
 *
 * 🔴 IT IS CONTENT IN THE STATE THAT WAS ALREADY THERE, NOT A PANEL. This mount
 * held a one-line hint; it now holds the hint plus the coverage the hint was
 * missing. No new region, no mode, no control: the samples are ANCHORS, because
 * this screen's answer is a URL, so a sample is the answer already written down.
 *
 * On `absent` / `empty` it is the whole message — there is nothing to sample and
 * the reason there is nothing is the thing the operator needs.
 */
export function renderCoverage(doc, mount, coverage) {
  clear(mount);
  const verdict = coverageVerdict(coverage);
  const wrap = el(doc, 'section', `lt-coverage lt-coverage--${verdict.tone}`);
  wrap.setAttribute('data-answer-kind', 'coverage');
  wrap.setAttribute('data-coverage-state', verdict.state);

  wrap.appendChild(el(doc, 'div', 'lt-coverage__title', verdict.title));
  if (verdict.detail) wrap.appendChild(el(doc, 'p', 'lt-coverage__detail', verdict.detail));

  if (verdict.state === 'ready') {
    const facts = coverageFacts(coverage);
    const list = el(doc, 'dl', 'lt-facts');
    const fact = (key, term, text) => {
      const row = el(doc, 'div', 'lt-fact');
      row.setAttribute('data-fact', key);
      row.appendChild(el(doc, 'dt', 'lt-fact__term', term));
      row.appendChild(el(doc, 'dd', 'lt-fact__value', text));
      list.appendChild(row);
    };
    // Each fact appears only if the wire carried it. An omitted row says "not
    // reported"; a row reading 0 or "—" would say "measured, and it is nothing".
    if (facts.lots !== null) fact('lots', '추적 가능한 랏', `${facts.lots}`);
    if (facts.sources.length) fact('sources', '출처', facts.sources.join(' · '));
    if (facts.from && facts.to) fact('range', '기간', `${facts.from} ~ ${facts.to}`);
    else if (facts.from) fact('range', '기간', `${facts.from} ~`);
    if (list.children.length) wrap.appendChild(list);

    const samples = coverageSamples(coverage);
    if (samples.length) {
      const ul = el(doc, 'ul', 'lt-samples');
      for (const s of samples) {
        const li = el(doc, 'li', 'lt-samples__item');
        const a = el(doc, 'a', 'lt-samples__link', s.text);
        // A real href, not a click handler: middle-click, copy-link and the
        // back button all work, and the page needs no state to serve it.
        a.setAttribute('href', `?${s.query}`);
        a.setAttribute('data-sample-lot', s.lot);
        if (s.slot !== null) a.setAttribute('data-sample-slot', s.slot);
        li.appendChild(a);
        ul.appendChild(li);
      }
      wrap.appendChild(ul);
    }

    wrap.appendChild(el(doc, 'p', 'lt-coverage__hint',
      '랏만 넣으면 랏 사슬만, 「랏/슬롯」이면 그 자리의 웨이퍼까지.'));
  }

  mount.appendChild(wrap);
  return wrap;
}

export function renderNotice(doc, mount, { tone, title, detail }) {
  clear(mount);
  const box = el(doc, 'div', `lt-notice lt-notice--${tone || 'idle'}`);
  box.setAttribute('data-answer-kind', 'notice');
  box.setAttribute('data-notice-tone', tone || 'idle');
  box.appendChild(el(doc, 'div', 'lt-notice__title', title || ''));
  if (detail) box.appendChild(el(doc, 'p', 'lt-notice__detail', String(detail)));
  mount.appendChild(box);
  return box;
}
