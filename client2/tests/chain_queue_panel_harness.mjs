// CHAIN QUEUE INSTRUMENT — the three rules the panel exists to keep, scored.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). `chain_queue_panel.js`
// touches no DOM and no CSS at module scope, so it imports in node as it stands.
//
// What is scored is the DISCRIMINATION, not the wording:
//   ① `null` and `0` must not render the same. Every assertion here compares the two states
//      against each other rather than against a fixed string, so a copy edit cannot redden it
//      and a copy edit cannot silently collapse them either.
//   ② a number the route refused to compute is drawn WITH ITS REASON, because an absent
//      number reads as zero.
//   ③ the panel invents no threshold — no sample of a single reading is coloured as late.
//
// Run: node client2/tests/chain_queue_panel_harness.mjs
import { queueView, formatAge, STATUS, ChainQueuePanel } from '../src/chain_queue_panel.js';

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

// ── the DOM stub (same shape `grid_source_label_harness.mjs` drives; consolidating the four
//    copies in `tests/` is its own round, and it is not this one) ──────────────────────────
function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null), _text: '',
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: t => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (host, cls) => walk(host)
  .filter(n => String(n.className || '').split(/\s+/).includes(cls));

const NOT_MEASURED = {
  retried_total: 'retry_count 에 인덱스가 없어 표 전체를 훑는다 (EXPLAIN 비용 272,812)',
  processed_recently: 'processed_at 에 인덱스가 없어 표 전체를 훑는다 (EXPLAIN 비용 272,817)',
};
const EMPTY = { waiting: 0, oldest_waiting_seconds: null, oldest_waiting_at: null,
                retried_among_waiting: 0, not_measured: NOT_MEASURED };
const JUST_ARRIVED = { waiting: 1, oldest_waiting_seconds: 0,
                       oldest_waiting_at: '2026-09-03 11:40:00', retried_among_waiting: 0,
                       not_measured: NOT_MEASURED };
const BACKED_UP = { waiting: 812, oldest_waiting_seconds: 3725.4,
                    oldest_waiting_at: '2026-09-03 10:38:14', retried_among_waiting: 17,
                    not_measured: NOT_MEASURED };

const card = (view, key) => view.cards.find(c => c.key === key);

// ═══ ① null IS NOT 0 ═══════════════════════════════════════════════════════════════
console.log('\n[1] an empty queue and a queue that just received something are DIFFERENT');
{
  const empty = queueView(EMPTY);
  const fresh = queueView(JUST_ARRIVED);
  const a = card(empty, 'oldest'), b = card(fresh, 'oldest');

  // 🔴 THE DISCRIMINANT. Compared against each other, not against fixed strings: this is the
  //    one property that cannot be allowed to drift, and pinning wording instead would make a
  //    copy edit look like a defect while a real collapse looked like a rename.
  ok('the two states do not share a headline', a.main !== b.main, `${a.main} / ${b.main}`);
  ok('nor an explanation', a.sub !== b.sub);
  ok('nor a status token', a.status !== b.status, `${a.status} / ${b.status}`);

  // and each says the right thing, so "different" cannot be satisfied by two wrong answers
  ok('empty says nothing is waiting', /대기 없음/.test(a.main), a.main);
  eq('empty is the only OK state on this card', a.status, STATUS.OK);
  ok('just-arrived shows a real zero, not an absence', /0/.test(b.main) && !/없/.test(b.main), b.main);
  ok('and its explanation carries the timestamp it has been waiting since',
    b.sub.includes('2026-09-03 11:40:00'), b.sub);

  // the same discrimination, drawn
  const doc = makeDoc();
  const h1 = doc.createElement('div'), h2 = doc.createElement('div');
  new ChainQueuePanel(h1, { doc }).render(EMPTY);
  new ChainQueuePanel(h2, { doc }).render(JUST_ARRIVED);
  const mainOf = (h) => byClass(h, 'health-card-main')[0].textContent;
  ok('and the two render to different pixels', mainOf(h1) !== mainOf(h2),
    `${mainOf(h1)} / ${mainOf(h2)}`);
}

// ═══ ② a number that was NOT measured is named, with its reason ═══════════════════
console.log('\n[2] the two the route refuses to compute are named, not omitted');
{
  const v = queueView(BACKED_UP);
  eq('both are carried', v.notMeasured.map(x => x.name), ['retried_total', 'processed_recently']);
  ok('each carries the route\'s own reason, not a shrug',
    v.notMeasured.every(x => x.why.length > 20 && /인덱스/.test(x.why)),
    JSON.stringify(v.notMeasured));

  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(BACKED_UP);
  const named = walk(host).filter(n => n.getAttribute && n.getAttribute('data-name'));
  eq('and both reach the screen', named.map(n => n.getAttribute('data-name')),
    ['retried_total', 'processed_recently']);
  ok('with the reason beside the name', named.every(n => /인덱스/.test(n.textContent)));

  // 🔴 NEGATIVE CONTROL. A response that names nothing must draw nothing here -- otherwise
  //    "both reach the screen" would pass on a panel that printed a hardcoded pair.
  const bare = { ...BACKED_UP };
  delete bare.not_measured;
  const doc2 = makeDoc();
  const host2 = doc2.createElement('div');
  new ChainQueuePanel(host2, { doc: doc2 }).render(bare);
  eq('a response that names none draws none',
    walk(host2).filter(n => n.getAttribute && n.getAttribute('data-name')).length, 0);
}

// ═══ ③ no invented threshold, and no invented number ═══════════════════════════════
console.log('\n[3] the panel judges nothing it was not told, and prints no number it was not given');
{
  // An hour of backlog is still not coloured as a fault: one sample cannot tell "growing"
  // from "busy", and the route's own docstring says so. If a threshold is ever wanted it is a
  // declaration, not a constant hidden in a view.
  const v = queueView(BACKED_UP);
  eq('a large age is NOT coloured as danger', card(v, 'oldest').status, STATUS.NEUTRAL);
  ok('and the card says how to read it instead', /자라는지/.test(card(v, 'oldest').sub));

  // A missing count is a dash. `0` would be a claim.
  const partial = queueView({ oldest_waiting_seconds: null, not_measured: NOT_MEASURED });
  eq('an absent depth is a dash, not 0', card(partial, 'waiting').main, '—');
  eq('an absent retry count is a dash, not 0', card(partial, 'retried').main, '—');
  eq('a present zero IS a zero', card(queueView(EMPTY), 'waiting').main, '0');

  // Unavailable: no cards at all. A stale or invented figure is worse than an empty card.
  const gone = queueView(null, { unavailable: '이 서버 프로세스에 /admin/chain/queue 가 없습니다 (404).' });
  eq('unavailable draws no cards', gone.cards.length, 0);
  ok('and says why by name', /404/.test(gone.reason), gone.reason);
  const doc = makeDoc();
  const host = doc.createElement('div');
  new ChainQueuePanel(host, { doc }).render(null, { unavailable: 'HTTP 500' });
  eq('and nothing numeric reaches the screen', byClass(host, 'health-card-main').length, 0);
  ok('but the reason does', /HTTP 500/.test(host.textContent), host.textContent);
}

// ═══ ④ formatAge — total, and the boundaries ═══════════════════════════════════════
console.log('\n[4] formatAge');
{
  eq('0', formatAge(0), '0초');
  eq('59', formatAge(59), '59초');
  eq('60', formatAge(60), '1분');
  eq('90', formatAge(90), '1분 30초');
  eq('3600', formatAge(3600), '1시간');
  eq('3725.4 truncates, never rounds up past the real wait', formatAge(3725.4), '1시간 2분');
  eq('86400', formatAge(86400), '1일');
  eq('90000', formatAge(90000), '1일 1시간');
  // total: garbage in is null, not `NaN초`
  eq('null', formatAge(null), null);
  eq('undefined', formatAge(undefined), null);
  eq('a string', formatAge('soon'), null);
  eq('negative', formatAge(-5), null);
}

// ═══ ⑤ 조립식 — two instances on one page do not touch each other ═══════════════════
console.log('\n[5] two panels on one page');
{
  const doc = makeDoc();
  const h1 = doc.createElement('div'), h2 = doc.createElement('div');
  const p1 = new ChainQueuePanel(h1, { doc });
  const p2 = new ChainQueuePanel(h2, { doc });
  p1.render(EMPTY);
  p2.render(BACKED_UP);
  const main1 = byClass(h1, 'health-card-main').map(n => n.textContent);
  const main2 = byClass(h2, 'health-card-main').map(n => n.textContent);
  ok('the second does not overwrite the first', main1[0] !== main2[0], `${main1[0]} / ${main2[0]}`);
  eq('the first still reads its own payload', main1[1], '0');
  eq('the second still reads its own', main2[1], '812');
  // re-rendering replaces rather than appends -- a panel that appended would show every
  // refresh ever made, stacked, and the newest would be at the bottom.
  p1.render(BACKED_UP);
  eq('a re-render replaces, it does not append', byClass(h1, 'health-card').length, 3);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
