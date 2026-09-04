// LEDGER SOURCES — 네 상태가 넷으로 남고, 「못 읽었다」가 「안 돌았다」가 되지 않는다.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). The panel touches
// no DOM and no CSS at module scope, so it imports in node as it stands.
//
// 🔴 THE TWO THIS FILE EXISTS FOR:
//   ① `unavailable` MUST NOT RENDER AS A LIST. The server distinguishes "the cursor table
//      could not be read" from "nothing has run", and says so in `ingestion_view`'s own
//      docstring. A screen that drew four `never_ran` rows for an unreadable cursor would
//      collapse the two into one picture, and no other assertion would notice.
//   ② THE FOUR STATES STAY FOUR. Folding them into normal/warning/error loses a fact, and
//      the server never said which of them is bad — so the screen deciding that would be
//      inventing a judgement. Same ruling as `moving` / `cancel_reaches` on the queue.
//
// Run: node client2/tests/ledger_sources_panel_harness.mjs
import { sourcesView, LedgerSourcesPanel, STATES } from '../src/ledger_sources_panel.js';
import { ABSENT } from '../src/absent.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null), _text: '', title: '',
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: t => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (host, cls) => walk(host)
  .filter(n => String(n.className || '').split(/\s+/).includes(cls));
const byTag = (host, tag) => walk(host).filter(n => n.tagName === tag);
const rowsOf = (host) => byClass(host, 'table-row');

const NOTE = '이 수는 «번역기의 장부»입니다 — 지금 원장에 몇 개 있는지가 아닙니다.';
const row = (source, state, over = {}) => ({
  source, state, declared: state !== 'orphan',
  translator_ver: 'v2', molecules_done: 10, atoms_written: 40,
  atoms_deduped: 2, molecules_refused: 1, updated_at: '2026-09-04T10:00:00', ...over,
});
const FOUR = {
  ingestion: {
    note: NOTE,
    unavailable: null,
    sources: [row('a', 'ran_and_wrote'), row('b', 'ran_wrote_nothing', { atoms_written: 0 }),
              row('c', 'never_ran', { translator_ver: null, molecules_done: null,
                                      atoms_written: null, atoms_deduped: null,
                                      molecules_refused: null, updated_at: null }),
              row('d', 'orphan')],
  },
};

// ═══ ① 「못 읽었다」 ≠ 「안 돌았다」 ═══════════════════════════════════════════════
console.log('\n[1] an unreadable cursor is not an empty ledger');
{
  const gone = sourcesView({ ingestion: { note: NOTE, unavailable: 'OperationalError: no such table', sources: [] } });
  eq('an unavailable cursor draws NO rows', gone.rows.length, 0);
  eq('...and is not available', gone.available, false);
  ok('...and names the reason the server gave', /no such table/.test(gone.reason), gone.reason);
  // 🔴 THE DISCRIMINANT: compared against the readable-but-empty case, not a fixed string.
  const emptyButRead = sourcesView({ ingestion: { note: NOTE, unavailable: null, sources: [] } });
  eq('a cursor that WAS read and holds nothing is available', emptyButRead.available, true);
  ok('the two are different states', gone.available !== emptyButRead.available);
  eq('and the count of an unreadable one is a dash, not 0', gone.count, ABSENT);
  eq('while a read-and-empty one is 0', emptyButRead.count, '0');

  // the VIEW still carries it; what changes is where the SCREEN puts it (see [4]).
  eq('the view keeps the note even when there is nothing to count', gone.note, NOTE);
}

// ═══ ② the four stay four ═══════════════════════════════════════════════════════
console.log('\n[2] four states, in the server\'s own words');
{
  const v = sourcesView(FOUR);
  eq('every row keeps the state the server sent',
    v.rows.map(r => r.state), ['ran_and_wrote', 'ran_wrote_nothing', 'never_ran', 'orphan']);
  eq('the four are counted separately',
    v.byState.map(b => `${b.state}=${b.count}`),
    ['ran_and_wrote=1', 'ran_wrote_nothing=1', 'never_ran=1', 'orphan=1']);
  eq('and the module names exactly those four', [...STATES].sort(),
    ['never_ran', 'orphan', 'ran_and_wrote', 'ran_wrote_nothing']);

  // 🔴 A STATE THE SCREEN DOES NOT KNOW IS SHOWN, NOT DROPPED. Folding to the known four
  //    would make a new server state vanish silently.
  const odd = sourcesView({ ingestion: { note: NOTE, unavailable: null,
    sources: [row('x', 'something_new')] } });
  eq('an unknown state is carried through verbatim', odd.rows[0].state, 'something_new');
  eq('...and counted under its own name', odd.byState.map(b => b.state), ['something_new']);

  // one state is not a split
  const one = sourcesView({ ingestion: { note: NOTE, unavailable: null,
    sources: [row('a', 'ran_and_wrote'), row('b', 'ran_and_wrote')] } });
  eq('two states or more split', v.splitByState, true);
  eq('one state does NOT split', one.splitByState, false);
  eq('...though both rows are still there', one.rows.length, 2);
}

// ═══ ③ a count that did not arrive is a dash ════════════════════════════════════
console.log('\n[3] missing numbers, beside the real zeros');
{
  const v = sourcesView(FOUR);
  const never = v.rows[2];
  eq('a never-run source shows a dash for atoms', never.atomsWritten, ABSENT);
  eq('...and for molecules', never.moleculesDone, ABSENT);
  eq('...and for the timestamp', never.updatedAt, ABSENT);
  eq('...and for translator_ver', never.translatorVer, ABSENT);
  // 🔴 the other half — a source that ran and wrote NOTHING is a real 0, not a dash
  eq('a real zero is a zero', v.rows[1].atomsWritten, '0');
  ok('the two are different pixels', never.atomsWritten !== v.rows[1].atomsWritten,
    `${never.atomsWritten} / ${v.rows[1].atomsWritten}`);
}

// ═══ ④ what reaches the screen ═════════════════════════════════════════════════
console.log('\n[4] the screen');
{
  const doc = makeDoc();
  const host = doc.createElement('div');
  const v = new LedgerSourcesPanel(host, { doc }).render(FOUR);
  eq('four rows are drawn', rowsOf(host).length, 4);
  eq('the header declares six', byTag(host, 'TH').length, 6);
  eq('and each row has six cells', rowsOf(host)[0].children.length, 6);
  // 🔴 IN THE TABLE HEAD, beside the numbers it qualifies -- not a paragraph above them
  //    (owner, 2026-09-04: 「ui에 설명 문구 주저리주저리 금지」).
  eq('the note is the table caption', byTag(host, 'CAPTION').length, 1);
  ok('...and it is the server\'s sentence', byTag(host, 'CAPTION')[0].textContent === NOTE);
  ok('each state reaches the screen under its own name',
    ['ran_and_wrote', 'ran_wrote_nothing', 'never_ran', 'orphan']
      .every(s => rowsOf(host).some(r => r.getAttribute('data-state') === s)));
  ok('the two extra cursor fields ride inside the row, not in a seventh column',
    byClass(host, 'ledger-sources-sub').length === 4
    && /translator_ver/.test(host.textContent) && /atoms_deduped/.test(host.textContent));
  eq('the view reports the row count for the section chip', v.count, '4');

  // unavailable: no table at all, and the reason on screen
  const doc2 = makeDoc();
  const host2 = doc2.createElement('div');
  new LedgerSourcesPanel(host2, { doc: doc2 })
    .render({ ingestion: { note: NOTE, unavailable: 'boom', sources: [] } });
  eq('an unreadable cursor draws no table', byTag(host2, 'TABLE').length, 0);
  eq('...and no row', rowsOf(host2).length, 0);
  ok('...but says why', /boom/.test(host2.textContent), host2.textContent);
  // 🔴 AND WITH NO NUMBERS THERE IS NO NOTE. It explains what the counts are; with no
  //    counts on screen it is a paragraph explaining nothing, which is what the rule forbids.
  eq('no table means no note', byTag(host2, 'CAPTION').length, 0);
  ok('the refusal is what shows instead', /boom/.test(host2.textContent));

  // a response this build does not understand
  const doc3 = makeDoc();
  const host3 = doc3.createElement('div');
  const v3 = new LedgerSourcesPanel(host3, { doc: doc3 }).render({});
  eq('a response with no ingestion key draws no table', byTag(host3, 'TABLE').length, 0);
  eq('...and its chip is a dash', v3.count, ABSENT);
  const doc4 = makeDoc();
  const host4 = doc4.createElement('div');
  new LedgerSourcesPanel(host4, { doc: doc4 }).render(null, { unavailable: 'HTTP 500' });
  ok('a failed fetch says so', /HTTP 500/.test(host4.textContent), host4.textContent);
  eq('...and draws nothing numeric', byTag(host4, 'TABLE').length, 0);
}

// ═══ ⑤ 조립식 — two on one page ════════════════════════════════════════════════
console.log('\n[5] two panels on one page');
{
  const doc = makeDoc();
  const h1 = doc.createElement('div'), h2 = doc.createElement('div');
  const p1 = new LedgerSourcesPanel(h1, { doc });
  const p2 = new LedgerSourcesPanel(h2, { doc });
  p1.render({ ingestion: { note: NOTE, unavailable: null, sources: [row('a', 'ran_and_wrote')] } });
  p2.render(FOUR);
  eq('the first keeps its own rows', rowsOf(h1).length, 1);
  eq('the second keeps its own', rowsOf(h2).length, 4);
  p1.render(FOUR);
  eq('a re-render replaces rather than appends', rowsOf(h1).length, 4);
  eq('and leaves exactly one table', byTag(h1, 'TABLE').length, 1);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
