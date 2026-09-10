/**
 * 🏷️ C-55 / S-117 — 원장 배치 영수증이 이력 타임라인에 «어떻게» 닿나. 대상을 IMPORT 합니다.
 *
 * 🔴 픽스처는 «계약 벡터»입니다 — `contracts/ledger_receipt/vectors.json`, 라이브
 *    `/audit_logs/recent` 에서 «뜬» 세 모양이지 설명에서 옮겨 적은 것이 아닙니다. 그 구별이
 *    이 화면에서 두 번 값을 했습니다(C-42 의 봉투, C-49 의 거절 상태).
 *
 * 🔴 봉투가 «둘»입니다: `status:'ok'` 는 수를 들고, `status:'failed'` 는 «수를 하나도» 안 듭니다
 *    (`{source, status, error}`). 실패를 수 자리로 그리면 셋이 빈 칸이 되고, 빈 칸은
 *    「안 쟀다」로 읽힙니다 — 그래서 가르는 것은 `status` 입니다.
 *
 * Run: node client2/tests/ledger_receipt_timeline_harness.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const VECTORS = JSON.parse(readFileSync(
  join(HERE, '..', '..', 'contracts', 'ledger_receipt', 'vectors.json'), 'utf8'));

let ran = 0;
let failed = 0;
const ok = (name, cond, detail = '') => {
  ran += 1;
  if (cond) console.log(`  PASS ${name}`);
  else { failed += 1; console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

// ── the DOM the row builder touches: it assigns `innerHTML`, so the markup IS the answer ──
function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: Object.create(null),
    _html: '', _classes: [], dataset: Object.create(null), style: {},
    get className() { return this._classes.join(' '); },
    set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: {
      add(...n) { for (const x of n) if (!node._classes.includes(x)) node._classes.push(x); },
      remove(...n) { node._classes = node._classes.filter((c) => !n.includes(c)); },
      contains(n) { return node._classes.includes(n); },
    },
    append(...i) { for (const x of i) if (x) this.children.push(x); },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    // ⚠️ The builder wires click/expand handlers onto nodes it looks up inside the row it just
    //    wrote. Returning `null` made it throw, which would have measured MY STUB rather than
    //    the markup. A blank element is enough: no assertion here is about the handlers.
    querySelector() { return element('div'); }, querySelectorAll() { return []; },
    addEventListener() {},
    set innerHTML(v) { this._html = String(v); },
    get innerHTML() { return this._html; },
    set textContent(v) { this._html = String(v); },
    get textContent() { return this._html; },
  };
  return node;
}
globalThis.document = { createElement: element, getElementById: () => null,
  createDocumentFragment: () => element('#fragment'), addEventListener() {} };
globalThis.window = { addEventListener() {} };

const T = await import('../src/timeline.js');
const { ledgerReceiptLine, LEDGER_BATCH_COLUMN, NO_TRANSACTION_BUCKET,
        createGlobalTimelineItemDom } = T;

console.log('\n[1] the receipt line, from the contract vectors');
{
  const line = (name) => ledgerReceiptLine(VECTORS.cases[name].logs[0].new_value);
  // 🔴 낱말은 «응답의 키 그대로»입니다(판정 177). 번역하면 서버가 키를 바꾸는 날 화면이
  //    옛 이름으로 옳아 보입니다.
  eq('a success carries the three counts and its status',
    'atoms_written 10 · atoms_deduped 0 · refused 0 · ok', line('followed_success'));
  // 🔴 THE DISCRIMINANT AGAINST A HARD-CODED LINE: the same shape with the numbers moved.
  eq('a backfill that only deduped says so, in the same order',
    'atoms_written 0 · atoms_deduped 10 · refused 0 · ok', line('unfollowed_backfill'));
  // 🔴 THE SECOND ENVELOPE. No counts exist here at all -- drawing three blanks would say
  //    「안 쟀다」 about a batch that FAILED, and the operator would go looking for numbers.
  eq('a failure says status, source and the error NAME', 'failed · dt_transfer · RuntimeError',
    line('failed'));
  // ⛔ 문장 전체는 이 줄의 자리가 아닙니다 (소유자 상설: 설명 문구 금지).
  ok('...and not the whole sentence', !line('failed').includes('blew up'), line('failed'));
}

console.log('\n[2] absence is not zero, and a stranger is not a receipt');
{
  eq('a count the server did not send takes NO segment', 'refused 3 · ok',
    ledgerReceiptLine({ refused: 3, status: 'ok' }));
  // ⚠️ `Number(null)` is 0 and finite -- the collapse this project keeps meeting.
  eq('a null count is 「말 안 함」, not a measured zero', 'atoms_deduped 2 · ok',
    ledgerReceiptLine({ atoms_written: null, atoms_deduped: 2, status: 'ok' }));
  eq('a measured zero IS drawn', 'atoms_written 0 · ok',
    ledgerReceiptLine({ atoms_written: 0, status: 'ok' }));
  eq('nothing at all draws nothing', '', ledgerReceiptLine(null));
  eq('...and a non-object too', '', ledgerReceiptLine('ledger ran'));
}

// ── the group shapes, straight out of the vectors ────────────────────────────────────
const groupOf = (name) => {
  const c = VECTORS.cases[name];
  return { transaction_id: c.transaction_id, total_count: c.total_count, logs: c.logs };
};
const CELL_CHANGE = {
  transaction_id: 'TX-CELL', total_count: 1,
  logs: [{ id: 1, table_name: 'dt_log', row_id: 'abcdef0123456789', column_name: 'dt_eqp',
           old_value: 'A', new_value: 'B', source_name: 'user', updated_by: 'kim',
           timestamp: '2026-09-10T01:00:00' }],
};

console.log('\n[3] what reaches the screen');
{
  const html = (g) => createGlobalTimelineItemDom(g).innerHTML;
  const success = html(groupOf('followed_success'));
  ok('the row is drawn at all', !!success && success.length > 0);
  // ① the kind. The filter list is built FROM this label (`fillAuditFilterOptions` maps
  //    `groupKindLabel` over the response), so a ledger row getting its own label is exactly
  //    what makes the filter able to separate it -- there is no second list to add it to.
  ok('a ledger batch is its own KIND, not SYSTEM', /audit-pill kind-ledger">LEDGER</.test(success),
    success.slice(0, 200));
  // ② the receipt beside the value, not folded into a word.
  ok('the receipt line is in the value cell',
    success.includes('atoms_written 10 · atoms_deduped 0 · refused 0 · ok'), success);
  ok('...and the raw envelope is NOT dumped there', !success.includes('translator_ver'), success);

  const failed = html(groupOf('failed'));
  ok('a FAILED receipt is still a ledger kind, not folded into BATCH',
    /kind-ledger">LEDGER</.test(failed), failed.slice(0, 200));
  ok('...and its line names the status and the error', failed.includes('failed · dt_transfer · RuntimeError'),
    failed);

  // ③ 'no_tid' is a NAME. Absent chain and 「자료 없음」 are different facts.
  const chainless = html(groupOf('unfollowed_backfill'));
  ok('a chainless batch is named, not blank', chainless.includes('체인 없이 들어온 배치'), chainless);
  // 🔴 THE CONTROL: the same shape WITH a transaction id must not carry that name.
  ok('...and a batch that HAS a chain does not carry that name',
    !success.includes('체인 없이 들어온 배치'), success);
}

console.log('\n[4] the rows that were already there do not move');
{
  const cell = createGlobalTimelineItemDom(CELL_CHANGE).innerHTML;
  ok('an ordinary cell change is not a ledger kind', !/kind-ledger/.test(cell), cell.slice(0, 200));
  ok('...and gets no receipt span', !cell.includes('val-receipt'), cell);
  ok('...and still draws its own before/after values',
    cell.includes('val-old') && cell.includes('val-arrow') && cell.includes('>B<'), cell);
  // 🔴 THE VOCABULARY IS THE RESPONSE'S. If the screen ever spells these itself, this breaks.
  eq('the receipt column name is the server key', 'ledger_batch', LEDGER_BATCH_COLUMN);
  eq('the chainless bucket is the route\'s own value', 'no_tid', NO_TRANSACTION_BUCKET);
}

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
