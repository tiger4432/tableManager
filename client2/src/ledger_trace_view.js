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
export function renderTrace(doc, mount, trace, subjectText) {
  clear(mount);
  const wrap = el(doc, 'section', 'lt-answer');
  wrap.setAttribute('data-answer-kind', 'trace');
  wrap.appendChild(renderSummary(doc, trace, subjectText));

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
