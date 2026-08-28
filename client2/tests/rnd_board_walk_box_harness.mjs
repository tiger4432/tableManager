/**
 * rnd_board — 걷기 검색창 scoring
 *
 * WHAT THIS SCORES (the order's five gates, each woken by a mutant):
 *   A  changing NODE TYPE changes the KEY fields -- their COUNT and their NAMES
 *   B  `recipe@1` says in a SENTENCE that nothing leaves it; an empty list is not an answer
 *   C  FOLLOW unpicked means `follow` is NOT on the request -- an empty array is the opposite
 *   D  two instances, different type and collect, no interference
 *   E  the three absences are three different sentences
 *
 * 🔴 THE DECLARATION FIXTURE IS THE LEAD PM'S MEASUREMENT, not an invention: six entities, ten
 *    predicates, eight collects, and the `subjects` links they measured off the live
 *    declaration. `recipe@1` having no outgoing predicate is the shape that decides B.
 *
 * 🔴 THE ROUTE DOES NOT EXIST YET. That is why every fetch here is injected and why E scores
 *    「서버가 아직 못 준다」 as its own sentence: a contract adopted before its material blanks
 *    the screen while the harness stays green, and this file refuses to be that harness.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe) except for the sentences it quotes.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BOARD_DIR = path.join(HERE, '..', 'src', 'rnd_board');
const LF = String.fromCharCode(10);
const CRLF = String.fromCharCode(13, 10);
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;

// The shape the Lead PM measured (`GET /api/ledger/declaration`).
const DECL = {
  ok: true,
  entities: [
    { type: 'die@1', keys: ['mat_id', 'x', 'y', 'mat_type'] },
    { type: 'wafer@1', keys: ['wafer'] },
    { type: 'lot@1', keys: ['lot'] },
    { type: 'lot_slot@1', keys: ['lot', 'slot'] },
    { type: 'dtjob@1', keys: ['job_id'] },
    { type: 'recipe@1', keys: ['recipe'] },
  ],
  predicates: [
    { name: 'transfer@1', subjects: ['die@1'] },
    { name: 'observed@1', subjects: ['die@1'] },
    { name: 'bonded_from@1', subjects: ['die@1', 'wafer@1'] },
    { name: 'inspected@1', subjects: ['wafer@1'] },
    { name: 'processed_with@1', subjects: ['wafer@1'] },
    { name: 'register@1', subjects: ['wafer@1', 'dtjob@1', 'lot@1'] },
    { name: 'has_wafer@1', subjects: ['lot_slot@1'] },
    { name: 'slot_map@1', subjects: ['lot_slot@1'] },
    { name: 'has_netdie@1', subjects: ['dtjob@1'] },
    { name: 'derived_from@1', subjects: ['lot@1'] },
  ],
  collect: ['entity', 'event', 'claim', 'collection', 'point', 'value', 'quantity', 'action'],
};

let ran = 0;
let failedList = [];
const ok = (name, cond, detail) => {
  ran += 1;
  if (cond) { console.log(`  ok   ${name}`); return; }
  failedList.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

async function loadModules(mutate = {}) {
  const read = (file) => {
    const text = readFileSync(path.join(BOARD_DIR, file), 'utf8').split(CRLF).join(LF);
    const fn = mutate[file];
    const out = fn ? fn(text) : text;
    if (fn && out === text) throw new Error(`mutation anchor is GONE: ${file}`);
    return out;
  };
  const storeUrl = dataUrl(read('marking_store.js'));
  const panelUrl = dataUrl(read('panel.js').split("'./marking_store.js'").join(`'${storeUrl}'`));
  const tableUrl = dataUrl(read('table_part.js')
    .split("'./panel.js'").join(`'${panelUrl}'`)
    .split("'./marking_store.js'").join(`'${storeUrl}'`));
  // 🔴 `api.js` 를 «먼저» 만들고 상자에도 배선합니다 (round V, 2026-08-29). 걷기 상자가
  //    타입 그래프를 쓰려고 `./api.js` 를 import 하는데, 그 줄이 재배선 목록에 없으면
  //    「Failed to resolve module specifier」로 «하니스가 통째로» 죽습니다 -- 단언 하나가
  //    아니라 전부입니다. main.js 머리가 그 경고를 적어 둔 자리이고, 실제로 밟았습니다.
  const apiUrl = dataUrl(read('api.js'));
  const boxUrl = dataUrl(read('walk_box_panel.js')
    .split("'./panel.js'").join(`'${panelUrl}'`)
    .split("'./marking_store.js'").join(`'${storeUrl}'`)
    .split("'./table_part.js'").join(`'${tableUrl}'`)
    .split("'./api.js'").join(`'${apiUrl}'`));
  return { store: await import(storeUrl), box: await import(boxUrl), api: await import(apiUrl) };
}

/** A document just large enough for selects, inputs and buttons. No jsdom, no globals. */
function makeDoc() {
  const make = (tag) => ({
    tagName: tag, children: [], style: {}, attrs: {}, _text: '', className: '', listeners: {},
    appendChild(c) { this.children.push(c); return c; },
    append(...cs) { cs.forEach((c) => this.appendChild(c)); },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    fire(type, event) { (this.listeners[type] || []).forEach((fn) => fn(event || {})); },
    click(event) { this.fire('click', event); },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
  });
  return { createElement: make };
}

const walkAll = (el, out = []) => { out.push(el); el.children.forEach((c) => walkAll(c, out)); return out; };
const byAttr = (host, name, value) => walkAll(host)
  .filter((e) => e.getAttribute && e.getAttribute(name) !== null
    && (value === undefined || e.getAttribute(name) === value));
const textOf = (host) => walkAll(host).map((e) => e._text).join(' ');
const settle = async () => { for (let i = 0; i < 8; i += 1) await Promise.resolve(); };

const NODES = [
  { id: 'ledger-entity:v1:AAA', type: 'die@1', label: 'D-1' },
  { id: 'ledger-entity:v1:BBB', type: 'die@1', label: 'D-2' },
];

async function suite(mods) {
  const { store: S, box: B, api: A } = mods;
  const { MarkingStore, SIGN } = S;
  const { WalkBoxPanel } = B;

  const doc = makeDoc();
  const markings = new MarkingStore();
  const asked = [];
  const host = doc.createElement('div');
  const panel = new WalkBoxPanel(host, {
    doc, markings, reads: 'marking:1', writes: 'marking:2',
    loadDeclaration: () => Promise.resolve(DECL),
    walk: (spec) => { asked.push(spec); return Promise.resolve({ ok: true, nodes: NODES }); },
  });
  panel.mount();
  await settle();

  console.log(`${LF}-- A. the KEY fields follow the type, in count and in name --`);
  const keyNames = () => byAttr(host, 'data-key').map((e) => e.getAttribute('data-key'));
  eq('A1 nothing is chosen, so no key field is drawn', keyNames().length, 0);
  panel.setType('die@1');
  eq('A2 die@1 draws FOUR', keyNames().join(','), 'mat_id,x,y,mat_type');
  panel.setType('wafer@1');
  eq('A3 wafer@1 draws ONE, and it is named', keyNames().join(','), 'wafer');
  panel.setType('lot_slot@1');
  eq('A4 lot_slot@1 draws TWO', keyNames().join(','), 'lot,slot');
  // 🔴 THE COUNT ALONE DOES NOT DECIDE IT. A fixed four-field form would pass 「four」 on die@1
  //    and fail here, but a form that draws the right COUNT with the wrong NAMES would pass a
  //    count-only assertion everywhere. A2/A3/A4 compare names.
  ok('A5 a value typed under one type does not survive a type that lacks that key',
    (() => {
      panel.setType('die@1');
      panel.keyValues.mat_id = 'M-9';
      panel.setType('wafer@1');
      return panel.keyValues.mat_id === undefined;
    })());

  console.log(`${LF}-- B. a type nothing leaves says so in a sentence --`);
  panel.setType('die@1');
  eq('B1 die@1 offers exactly what the declaration says leaves it',
    panel.followOptions().join(','), 'transfer@1,observed@1,bonded_from@1');
  eq('B2 wafer@1 offers its own three',
    panel.followOptions.call(Object.assign(Object.create(Object.getPrototypeOf(panel)),
      panel, { nodeType: 'wafer@1' })).join(','),
    'bonded_from@1,inspected@1,processed_with@1,register@1');
  panel.setType('recipe@1');
  eq('B3 recipe@1 offers nothing -- it is an object, never a subject', panel.followOptions().length, 0);
  const recipeText = textOf(host);
  ok('B4 and the screen SAYS so rather than drawing an empty list',
    recipeText.includes('나가는 술어가 없습니다'), recipeText.slice(0, 90));
  ok('B5 the sentence names the type it is talking about', recipeText.includes('recipe@1'));
  eq('B6 no follow checkbox is drawn', byAttr(host, 'data-follow').length, 0);

  console.log(`${LF}-- C. unpicked FOLLOW is ABSENT from the request, not an empty list --`);
  panel.setType('die@1');
  panel.collect = 'quantity';
  await panel.run();
  await settle();
  eq('C1 one walk went out', asked.length, 1);
  ok('C2 and it carries NO follow key at all', !('follow' in asked[0]), JSON.stringify(asked[0]));
  eq('C3 the type on screen is the one asked', asked[0].type, 'die@1');
  eq('C3-bis and no collect rides along', 'collect' in asked[0], false);
  panel.toggleFollow('observed@1');
  await panel.run();
  await settle();
  // 🔴 2026-08-29 (round V): 전선의 철자가 «벗겨진 이름»입니다. 선언은 `observed@1` 로
  //    부르고 라우트는 그것을 «422» 로 거절합니다 -- 실측: follow=inspected 200 ·
  //    follow=inspected@1 «422». 이 단언은 여태 «라우트가 거절하는 값»을 기대하고
  //    있었습니다. 재는 것(「고른 것이 요청에 실린다」)은 그대로이고 철자만 참으로 옮깁니다.
  eq('C4 picking one puts it on the request', JSON.stringify(asked[1].follow), '["observed"]');
  panel.toggleFollow('observed@1');
  await panel.run();
  await settle();
  ok('C5 un-picking it takes the key away again, not leaving []', !('follow' in asked[2]),
    JSON.stringify(asked[2]));
  // 🔴 C6 NEEDS A BOX THAT WAS TYPED IN AND THEN CLEARED. If nothing was ever typed the
  //    map is empty and both rules answer `{}` -- the rule would be unfalsifiable on the
  //    only input a test naturally produces. A cleared box is the real case: the operator
  //    typed a lot number, changed their mind, and an empty string is NOT a filter for
  //    「키가 빈 것」 -- it would ask the server for rows whose mat_id is the empty string.
  panel.keyValues.mat_id = '';
  panel.keyValues.x = '12';
  await panel.run();
  await settle();
  eq('C6 a cleared key box is not sent as a filter', JSON.stringify(asked[3].keys), '{"x":"12"}');
  ok('C6b and the one that still has a value is', asked[3].keys.x === '12');

  console.log(`${LF}-- result rows and the marking --`);
  const rowsOf = (h) => walkAll(h).filter((e) => (e.className || '').includes('rb-table-row'));
  eq('R1 the collected return is drawn as rows', rowsOf(host).length, 2);
  rowsOf(host)[0].click({});
  eq('R2 clicking a row marks that node', markings.count('marking:2'), 1);
  eq('R3 under the name this instance declared it writes',
    markings.signOf('marking:2', NODES[0].id), SIGN.CASE);

  console.log(`${LF}-- S. the seed id is base64URL, and the server requires it --`);
  {
    const { entitySeedId } = A;
    // 🔴 THE KEY THAT DECIDES IT. Every seed this screen uses today encodes without a `+` or a
    //    `/`, so standard base64 and base64url produce the SAME string and the rule cannot be
    //    falsified by real data. `SYN-BW-101-16>` is the first key whose JSON base64 carries a
    //    `+`. Measured live 2026-08-27: standard base64 -> HTTP 422, base64url -> 200. This is
    //    a contract the server enforces, not a taste, and it was correct-but-unverified until
    //    an input was MADE that could tell the two apart.
    const withPlus = entitySeedId('wafer@1', { wafer: 'SYN-BW-101-16>' });
    ok('S1 the discriminating key really does produce a + under standard base64',
      Buffer.from(JSON.stringify(['wafer', { wafer: 'SYN-BW-101-16>' }]), 'utf8')
        .toString('base64').includes('+'));
    ok('S2 and the seed id carries none', !withPlus.includes('+'), withPlus.slice(-24));
    ok('S3 it carries the base64url substitute instead', withPlus.includes('-'), withPlus.slice(-24));
    ok('S4 padding is stripped', !withPlus.includes('='), withPlus.slice(-24));
    // The version tag is stripped from the TYPE, not from the id.
    eq('S5 the type loses its @version', Buffer.from(withPlus.split(':').pop()
      .replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8').slice(0, 8), '["wafer"');
    eq('S6 a plain key round-trips to the id the board already uses',
      entitySeedId('wafer@1', { wafer: 'SYN-CX-BW-001' }),
      'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0');
  }

  // 🔴 SECTION L RETIRED 2026-08-28 -- it measured the COLLECT dropdown, and the
  //    dropdown is gone: every node the walk returns is a declared entity, so a switch
  //    selecting a node kind had one value. What it guarded (a new kind with no label
  //    yet must render its id rather than a blank) has no list left to render.
  console.log(`${LF}-- D. two on one screen, different declarations, no interference --`);
  const hostA = doc.createElement('div');
  const hostB = doc.createElement('div');
  const askedA = []; const askedB = [];
  const a = new WalkBoxPanel(hostA, {
    doc, markings, reads: 'marking:1', writes: 'marking:3',
    loadDeclaration: () => Promise.resolve(DECL),
    walk: (s) => { askedA.push(s); return Promise.resolve({ ok: true, nodes: NODES }); },
  });
  const b = new WalkBoxPanel(hostB, {
    doc, markings, reads: 'marking:2', writes: 'marking:4',
    loadDeclaration: () => Promise.resolve(DECL),
    walk: (s) => { askedB.push(s); return Promise.resolve({ ok: true, nodes: [NODES[1]] }); },
  });
  a.mount(); b.mount();
  await settle();
  a.setType('die@1'); a.collect = 'point';
  b.setType('lot_slot@1'); b.collect = 'event';
  a.toggleFollow('observed@1');
  await a.run(); await b.run();
  await settle();
  eq('D1 A asked with its own type', askedA[0].type, 'die@1');
  eq('D2 B asked with its own', askedB[0].type, 'lot_slot@1');
  // 같은 이음매 (round V) -- 전선은 벗겨진 이름을 받습니다. C4 위의 실측 참조.
  eq('D3 A carried its follow', JSON.stringify(askedA[0].follow), '["observed"]');
  ok('D4 B carried none', !('follow' in askedB[0]));
  ok('D5 their key fields differ',
    byAttr(hostA, 'data-key').map((e) => e.getAttribute('data-key')).join(',') === 'mat_id,x,y,mat_type'
    && byAttr(hostB, 'data-key').map((e) => e.getAttribute('data-key')).join(',') === 'lot,slot');
  rowsOf(hostA)[0].click({});
  eq('D6 A wrote its own marking', markings.count('marking:3'), 1);
  eq('D7 and B name stayed empty', markings.count('marking:4'), 0);
  ok('D8 each holds its own result', a.result !== b.result && a.result.nodes.length === 2
    && b.result.nodes.length === 1);

  console.log(`${LF}-- T. a cut walk says it was cut --`);
  {
    const hostT = doc.createElement('div');
    const pt = new WalkBoxPanel(hostT, {
      doc, markings, reads: 'marking:1', writes: 'marking:2',
      loadDeclaration: () => Promise.resolve(DECL),
      // The shape the live route really returns -- measured 2026-08-27, wafer@1 SYN-BW-101-16:
      // depth false, everything else true. A budget cut, not a question about depth.
      walk: () => Promise.resolve({ ok: true, nodes: NODES, truncated: {
        depth: false, nodes: true, edges: true, claims: true, actions: true,
        reason: 'nodes, edges, claims, actions' } }),
    });
    pt.mount();
    await settle();
    pt.setType('die@1');
    await pt.run();
    await settle();
    const cutText = textOf(hostT);
    ok('T1 a truncated walk says so', cutText.includes('예산에서 끊겼습니다'), cutText.slice(-100));
    ok('T2 and it names what the server named', cutText.includes('nodes, edges, claims, actions'));
    // 🔴 THE ROWS ARE STILL THERE. 「끊겼다」 is not 「없다」 -- a cut answer still answers.
    eq('T3 the rows it did get are still drawn', rowsOf(hostT).length, 2);
    // 🔴 T4 NEEDS `truncated` PRESENT AND EMPTY, which is what the route actually sends when
    //    nothing was cut. The panel above returns no `truncated` key at all, so a mutant that
    //    drops the `.reason` guard is inert there -- `undefined` is falsy either way. The
    //    real shape has every flag false and an empty reason, and only that tells the two apart.
    const hostQ = doc.createElement('div');
    const pq = new WalkBoxPanel(hostQ, {
      doc, markings, reads: 'marking:1', writes: 'marking:2',
      loadDeclaration: () => Promise.resolve(DECL),
      walk: () => Promise.resolve({ ok: true, nodes: NODES, truncated: {
        depth: false, nodes: false, edges: false, claims: false, actions: false, reason: '' } }),
    });
    pq.mount();
    await settle();
    pq.setType('die@1');
    await pq.run();
    await settle();
    ok('T4 a walk that was NOT cut stays silent', !textOf(hostQ).includes('예산에서 끊겼습니다'),
      textOf(hostQ).slice(-80));
    ok('T4b and a walk with no truncated key at all stays silent too',
      !textOf(host).includes('예산에서 끊겼습니다'));
  }

  console.log(`${LF}-- E. three absences, three sentences --`);
  // ② the route is not there yet -- the state this whole round is written under.
  const hostR = doc.createElement('div');
  const pr = new WalkBoxPanel(hostR, {
    doc, markings, reads: 'marking:1', writes: 'marking:2',
    loadDeclaration: () => Promise.resolve({ ok: false, message: null }),
    walk: () => Promise.resolve({ ok: true, nodes: [] }),
  });
  pr.mount();
  await settle();
  const noDecl = textOf(hostR);
  ok('E1 no declaration says the SERVER cannot answer yet',
    noDecl.includes('서버가 아직 선언을 못 줍니다'), noDecl.slice(0, 90));
  eq('E2 and it draws no controls to click', byAttr(hostR, 'data-field').length, 0);

  // ① chosen nothing yet, ③ walked and found nothing -- on the SAME panel, different sentences.
  const hostN = doc.createElement('div');
  const pn = new WalkBoxPanel(hostN, {
    doc, markings, reads: 'marking:1', writes: 'marking:2',
    loadDeclaration: () => Promise.resolve(DECL),
    walk: () => Promise.resolve({ ok: true, nodes: [] }),
  });
  pn.mount();
  await settle();
  const before = textOf(hostN);
  ok('E3 nothing chosen yet is its own sentence', before.includes('타입을 고르고 걸으십시오'),
    before.slice(-90));
  pn.setType('die@1');
  await pn.run();
  await settle();
  const after = textOf(hostN);
  ok('E4 walked-and-empty is a DIFFERENT sentence', after.includes('걸었는데 닿은 것이 없습니다'),
    after.slice(-90));
  ok('E5 and it is not the not-chosen one', !after.includes('타입을 고르고 걸으십시오'));

  const hostF = doc.createElement('div');
  const pf = new WalkBoxPanel(hostF, {
    doc, markings, reads: 'marking:1', writes: 'marking:2',
    loadDeclaration: () => Promise.resolve(DECL),
    walk: () => Promise.resolve({ ok: false, message: '서버가 거절했습니다 (HTTP 503)' }),
  });
  pf.mount();
  await settle();
  pf.setType('die@1');
  await pf.run();
  await settle();
  const refused = textOf(hostF);
  ok('E6 a refused walk carries the server sentence', refused.includes('HTTP 503'), refused.slice(-90));
  ok('E7 which is neither of the other two',
    !refused.includes('걸었는데 닿은 것이 없습니다') && !refused.includes('타입을 고르고 걸으십시오'));

  return { ran, failed: failedList.slice() };
}

// 🔴 THREE MUTANTS RETIRED 2026-08-28 with the COLLECT dropdown they mutated
//    (`a-kind-with-no-label-is-drawn-blank`, `the-label-is-sent-instead-of-the-id`,
//    `the-object-shape-is-not-understood`). Their anchors are gone from the panel, and a
//    mutant whose anchor is absent reports as a harness failure rather than as a caught
//    defect -- which is the honest behaviour, and why they leave rather than linger.
const MUTANTS = [
  // ① the gate the order names: a fixed four-field form.
  { name: 'the-key-form-is-four-fixed-fields', wakes: 'A2/A3/A4',
    from: "    return (found && found.keys) || [];",
    to: "    return ['mat_id', 'x', 'y', 'mat_type'];" },
  { name: 'keys-survive-a-type-that-lacks-them', wakes: 'A5',
    from: "    for (const k of keys) if (this.keyValues[k] !== undefined) kept[k] = this.keyValues[k];\n    this.keyValues = kept;",
    to: "    for (const k of keys) if (this.keyValues[k] !== undefined) kept[k] = this.keyValues[k];" },
  // ② the touchstone: an empty dropdown instead of a sentence.
  { name: 'an-empty-follow-list-is-drawn-as-a-list', wakes: 'B4/B6',
    from: "      box.appendChild(this._note(this.nodeType",
    to: "      return box; box.appendChild(this._note(this.nodeType" },
  { name: 'follow-is-not-narrowed-by-subjects', wakes: 'B1/B3',
    from: "    return all.filter((p) => (p.subjects || []).includes(this.nodeType)).map((p) => p.name);",
    to: "    return all.map((p) => p.name);" },
  // ③ an empty array is the OPPOSITE of the server default.
  { name: 'unpicked-follow-is-sent-as-an-empty-array', wakes: 'C2/C5',
    // 앵커 갱신 2026-08-29 (round V): 그 줄이 전선에서 버전을 «벗기게» 바뀌었습니다.
    // 재는 것은 그대로입니다 -- 「안 고른 follow 를 빈 배열로 보내지 않는다」.
    from: "    if (this.follow.size) spec.follow = [...this.follow].map(bareTypeName);",
    to: "    spec.follow = [...this.follow].map(bareTypeName);" },
  { name: 'blank-key-boxes-are-sent-as-filters', wakes: 'C6',
    from: "    for (const [k, v] of Object.entries(this.keyValues)) if (v !== '' && v !== undefined) keys[k] = v;",
    to: "    for (const [k, v] of Object.entries(this.keyValues)) keys[k] = v;" },
  // ⑤ one sentence for every absence.
  { name: 'the-cut-is-not-mentioned', wakes: 'T1/T2',
    from: "    if (cut) box.appendChild(this._note(",
    to: "    if (false) box.appendChild(this._note(" },
  // 🔴 THE MUTANT TARGETS THE *RENDER* CONDITION, NOT THE `.reason` GUARD, BECAUSE THAT GUARD
  //    IS REDUNDANT: `if (cut)` already rejects the empty string the route sends when nothing
  //    was cut, so removing `.reason` changes nothing and the mutant sat inert. The defect that
  //    IS observable is announcing a cut whenever the KEY is present -- which is every walk.
  { name: 'a-cut-is-reported-whenever-the-key-is-present', wakes: 'T4',
    from: "    if (cut) box.appendChild(this._note(",
    to: "    if (this.result && this.result.truncated) box.appendChild(this._note(" },
  { name: 'every-absence-shares-one-sentence', wakes: 'E4/E6',
    from: "    if (this.walkState === 'ready') return '걸었는데 닿은 것이 없습니다';",
    to: "    if (this.walkState === 'ready') return '타입을 고르고 걸으십시오';" },
  { name: 'a-missing-route-reads-as-an-empty-result', wakes: 'E1',
    from: "    if (this.declState !== 'ready') {",
    to: "    if (false) {" },
];

const main = async () => {
  console.log('== baseline ==');
  const base = await suite(await loadModules());
  console.log(`${LF}${base.ran - base.failed.length} passed, ${base.failed.length} failed.`);
  if (base.failed.length) {
    console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`);
    process.exit(1);
  }

  console.log(`${LF}== defect mutants (each must be CAUGHT) ==`);
  let escaped = 0;
  for (const m of MUTANTS) {
    let mods;
    try {
      mods = await loadModules({
        'walk_box_panel.js': (src) => (src.includes(m.from) ? src.split(m.from).join(m.to) : src),
      });
    } catch (err) {
      console.error(`HARNESS FAILURE: ${err.message} (${m.name})`);
      console.error('(This is not a passing result. Nothing was compared.)');
      process.exit(2);
    }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    let result;
    try { result = await suite(mods); } catch (err) { result = { failed: ['threw: ' + err.message] }; }
    console.log = real;
    if (result.failed.length) {
      real(`  caught  ${m.name}  (${m.wakes}) -- ${String(result.failed[0]).slice(0, 62)}`);
    } else { real(`  ESCAPED ${m.name}  (${m.wakes})`); escaped += 1; }
  }

  console.log(`${LF}ASSERTIONS ${base.ran} ${base.failed.length}`);
  process.exit(escaped ? 1 : 0);
};

main();
