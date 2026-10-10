/**
 * rnd_board — 걷기 검색창 scoring
 *
 * WHAT THIS SCORES (the order's five gates, each woken by a mutant):
 *   A  changing NODE TYPE changes the KEY fields -- their COUNT and their NAMES
 *   B  FOLLOW offers what touches the type from EITHER side (`recipe` gets the one entering it),
 *      the walk page offers the same list, and a type nothing touches says so in a SENTENCE
 *   C  FOLLOW unpicked means `follow` is NOT on the request -- an empty array is the opposite
 *   D  two instances, different type and collect, no interference
 *   E  the three absences are three different sentences
 *
 * 🔴 THE DECLARATION FIXTURE IS THE LEAD PM'S MEASUREMENT, not an invention: six entities, ten
 *    predicates, eight collects, and the `subjects` links they measured off the live
 *    declaration. The `object.types` and recipe's `class` are the shipped sample's (server/config/
 *    sample/ledger_config.json.sample); `defect` (an object-only type that is not static) and
 *    `note` (no predicate touches it) are HAND-HELD.
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
import { loadBoardModules } from './lib/board_modules.mjs';
// 🔴 THE SPELLING HAS ONE AUTHOR (C-99 ③). These assertions are about a STATE --
//    「아직 안 골랐다」 has its own seat -- and a copy of the sentence here would make
//    this harness a second author of it: a wording change reddens an assertion that
//    was never about the wording.
import { UNPICKED } from '../src/absent.js';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BOARD_DIR = path.join(HERE, '..', 'src', 'rnd_board');
const WALK_DIR = path.join(HERE, '..', 'src', 'walk');
const LF = String.fromCharCode(10);
const CRLF = String.fromCharCode(13, 10);

// The shape the Lead PM measured (`GET /api/ledger/declaration`).
const DECL = {
  ok: true,
  entities: [
    { type: 'die', keys: ['mat_id', 'x', 'y', 'mat_type'] },
    { type: 'wafer', keys: ['wafer'] },
    { type: 'lot', keys: ['lot'] },
    { type: 'lot_slot', keys: ['lot', 'slot'] },
    { type: 'dtjob', keys: ['job_id'] },
    { type: 'recipe', keys: ['recipe'], class: ['static'] },
    { type: 'defect', keys: ['defect'] },
    { type: 'note', keys: ['note'] },
  ],
  predicates: [
    { name: 'transfer', subjects: ['die'], object: { types: ['die'] } },
    { name: 'observed', subjects: ['die'], object: { types: ['defect'] } },
    { name: 'bonded_from', subjects: ['die', 'wafer'], object: { types: ['die'] } },
    { name: 'inspected', subjects: ['wafer'], object: { types: ['die'] } },
    { name: 'processed_with', subjects: ['wafer'], object: { types: ['recipe'] } },
    { name: 'register', subjects: ['wafer', 'dtjob', 'lot'], object: {} },
    { name: 'has_wafer', subjects: ['lot_slot'], object: { types: ['wafer'] } },
    { name: 'slot_map', subjects: ['lot_slot'], object: { types: ['lot_slot'] } },
    { name: 'has_netdie', subjects: ['dtjob'], object: {} },
    { name: 'derived_from', subjects: ['lot'], object: { types: ['lot'] } },
  ],
  collect: ['entity', 'event', 'claim', 'collection', 'point', 'value', 'quantity', 'action'],
};

let ran = 0;
const NAMES = [];   // every assertion NAME, so the scorer can spot a prefix that hits two
let failedList = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failedList.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

// 🔴 C-93 (판정 345). THE LOADER IS SHARED. This file used to carry its own `dataUrl`/`read`/
//    `outward` -- the same three lines six harnesses each held -- and the day `api.js` gained its
//    first outward import, every one of those copies was missing the rewrite it already knew
//    about. One place to forget nothing; the mutation keys and the names driven here are unchanged.
async function loadModules(mutate = {}) {
  const board = await loadBoardModules(mutate);
  return { store: board.store, box: board.parts.box, api: board.api,
    derive: board.parts.derive };
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
  { id: 'ledger-entity:v1:AAA', type: 'die', label: 'D-1' },
  { id: 'ledger-entity:v1:BBB', type: 'die', label: 'D-2' },
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
  panel.setType('die');
  eq('A2 die draws FOUR', keyNames().join(','), 'mat_id,x,y,mat_type');
  panel.setType('wafer');
  eq('A3 wafer draws ONE, and it is named', keyNames().join(','), 'wafer');
  panel.setType('lot_slot');
  eq('A4 lot_slot draws TWO', keyNames().join(','), 'lot,slot');
  // 🔴 THE COUNT ALONE DOES NOT DECIDE IT. A fixed four-field form would pass 「four」 on die
  //    and fail here, but a form that draws the right COUNT with the wrong NAMES would pass a
  //    count-only assertion everywhere. A2/A3/A4 compare names.
  ok('A5 a value typed under one type does not survive a type that lacks that key',
    (() => {
      panel.setType('die');
      panel.keyValues.mat_id = 'M-9';
      panel.setType('wafer');
      return panel.keyValues.mat_id === undefined;
    })());

  console.log(`${LF}-- B. FOLLOW offers what touches the type; a type nothing touches says so --`);
  const drawnFollow = (h) => byAttr(h, 'data-follow').map((e) => e.getAttribute('data-follow')).join(',');
  panel.setType('die');
  eq('B1 die offers the three that leave it and inspected, which enters it',
    panel.followOptions().join(','), 'transfer,observed,bonded_from,inspected');
  eq('B2 wafer offers its own four and has_wafer, which enters it',
    panel.followOptions.call(Object.assign(Object.create(Object.getPrototypeOf(panel)),
      panel, { nodeType: 'wafer' })).join(','),
    'bonded_from,inspected,processed_with,register,has_wafer');
  panel.setType('defect');
  eq('B3 defect, only ever an object, offers the predicate that enters it',
    panel.followOptions().join(','), 'observed');
  eq('B7 ... and draws its checkbox', drawnFollow(host), 'observed');
  // 🔴 THE SEED'S FIRST STEP IS OPEN (owner 10-02, lead c24ba7d82): a static type gets what enters it.
  panel.setType('recipe');
  eq('H1 static recipe offers the step in from wafer', panel.followOptions().join(','), 'processed_with');
  eq('H2 ... and draws its checkbox', drawnFollow(host), 'processed_with');
  panel.setType('note');
  const noteText = textOf(host);
  ok('B4 a type no predicate touches: the screen SAYS so rather than drawing an empty list',
    noteText.includes('No predicate touches'), noteText.slice(0, 90));
  ok('B5 the sentence names the type it is talking about', noteText.includes('note'));
  eq('B6 no follow checkbox is drawn', byAttr(host, 'data-follow').length, 0);
  // The two-screen follow compare (B8) left 10-06 (lead): the walk page draws every declared predicate
  // (owner 10-06), this frozen box what touches the type. It comes back when the board follows the page.
  const walkPage = await import('../src/walk/main.js');
  // 🔴 A TYPE CHANGE (lead 10-02): a ticked follow that does not touch the new type leaves, one that does
  //    stays. This box only - the walk page keeps every tick since 10-06 (lead).
  panel.setType('die'); panel.follow = new Set(['inspected', 'processed_with']); panel.setType('recipe');
  await settle();
  ok('H3 a type change keeps only the ticked follow that touches the new type',
    [...panel.follow].join(',') === 'processed_with', [...panel.follow].join(','));

  console.log(`${LF}-- K. the route list leaves out what the walk refuses, as the walk page does --`);
  {
    // Hand-held, in the shipped sample's shape: two ways from wafer to defect, one through the static hub.
    const DECL_R = { ok: true,
      entities: [{ type: 'wafer', keys: ['wafer'] }, { type: 'die', keys: ['mat_id'] },
        { type: 'defect', keys: ['defect'] }, { type: 'quantity', keys: ['q'], class: ['static'] },
        { type: 'defect_kind', keys: ['kind'], class: ['static'] }],
      predicates: [
        { name: 'measures', subjects: ['wafer'], object: { types: ['quantity'] } },
        { name: 'leads_to', subjects: ['quantity'], object: { types: ['quantity', 'defect_kind'] } },
        { name: 'of_kind', subjects: ['defect'], object: { types: ['defect_kind'] } },
        { name: 'inspected', subjects: ['wafer'], object: { types: ['die'] } },
        { name: 'observed', subjects: ['die'], object: { types: ['defect'] } }] };
    const rhost = doc.createElement('div');
    const rbox = new WalkBoxPanel(rhost, { doc, markings: new MarkingStore(), reads: 'marking:1', writes: 'marking:2',
      loadDeclaration: () => Promise.resolve(DECL_R), walk: () => Promise.resolve({ ok: true, nodes: [] }) });
    rbox.mount();
    await settle();
    const chains = () => rbox.routes().map((r) => r.chain.join('>')).sort().join(' ; ');
    rbox.setType('wafer'); rbox.destination = 'defect';
    eq('K1 wafer to defect: the route through die, not the one stepping out of the static hub',
      chains(), 'wafer>die>defect');
    rbox.setType('quantity'); rbox.destination = 'die';
    ok('K2 static quantity to die: the first step out to wafer is offered',
      chains().split(' ; ').includes('quantity>wafer>die'), chains());
    const rdoc = makeDoc();
    rdoc.head = rdoc.createElement('head');
    const rpageHost = rdoc.createElement('div');
    const rpage = walkPage.boot(rdoc, rpageHost, { apiBase: '',
      fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL_R }) });
    await settle();
    const pageChains = (type, to) => {
      rpage.state.type = type; rpage.state.collect = new Set([to]); rpage.render();
      return walkAll(rpageHost).filter((e) => e.className === 'wk-pathchain')
        .map((e) => e.textContent.split(' → ').join('>')).sort().join(' ; ');
    };
    const boxChains = (type, to) => { rbox.setType(type); rbox.destination = to; return chains(); };
    const pairs = [['wafer', 'defect'], ['quantity', 'die'], ['defect', 'wafer']];
    const apart = pairs.filter(([t, to]) => pageChains(t, `${to}`) !== boxChains(t, to))
      .map(([t, to]) => `${t}->${to}: page ${pageChains(t, `${to}`)} | box ${boxChains(t, to)}`);
    ok('K3 the walk page and this box offer the same routes', apart.length === 0, apart.join(' ; '));
  }

  console.log(`${LF}-- R. a self-loop is a chip in its route's row, off by default (lead 5d5b8d750) --`);
  {
    // 🔴 THE BOX DECLARATION'S SHAPE (GET /api/ledger/declaration, 10-02): fourteen predicates,
    //    five self-loops (transfer · bonded_from on die, derived_from on lot, slot_map on lot_slot,
    //    leads_to on quantity - which also steps quantity -> defect_kind).
    const P = (name, subjects, types) => ({ name: `${name}`, subjects: subjects.map((s) => `${s}`),
      object: { types: types && types.map((t) => `${t}`) } });
    const DECL_BOX = { ok: true,
      entities: ['defect', 'die', 'dtjob', 'lot', 'lot_slot', 'wafer'].map((t) => ({ type: `${t}`, keys: ['k'] }))
        .concat(['defect_kind', 'quantity', 'recipe'].map((t) => ({ type: `${t}`, keys: ['k'], class: ['static'] }))),
      predicates: [P('bonded_from', ['die'], ['die']), P('derived_from', ['lot'], ['lot']),
        P('has_netdie', ['dtjob'], null), P('has_wafer', ['lot_slot'], ['wafer']),
        P('in_container', ['die'], ['wafer']), P('inspected', ['wafer'], ['die']),
        P('leads_to', ['quantity'], ['quantity', 'defect_kind']), P('measures', ['wafer'], ['quantity']),
        P('observed', ['die'], ['defect']), P('of_kind', ['defect'], ['defect_kind']),
        P('processed_with', ['wafer'], ['recipe']), P('register', ['lot', 'wafer', 'dtjob'], null),
        P('slot_map', ['lot_slot'], ['lot_slot']), P('transfer', ['die'], ['die'])] };
    const { pathsBetween, routeWith, typeGraph } = A;
    const { types, edges } = typeGraph(DECL_BOX);
    const limit = types.length - 1;
    // THE ORACLE IS THE OLD LIST BY ITS DEFINITION: every walk from `a` that reaches `b`, a type at
    // most once, each loop at most once, at most `limit` steps, folded by follow set to the fewest
    // hops. Written here from that definition, not copied from any source.
    const oldList = (a, b) => {
      const best = new Map();
      const go = (at, seen, loops, steps) => {
        if (steps.length && at === b) {
          const key = [...new Set(steps)].sort().join('|');
          if (!best.has(key) || steps.length < best.get(key)) best.set(key, steps.length);
          return;
        }
        if (steps.length >= limit) return;
        for (const e of edges) {
          if (e.from === e.to) {
            if (e.from !== at || loops.has(e.predicate)) continue;
            loops.add(e.predicate); go(at, seen, loops, [...steps, e.predicate]); loops.delete(e.predicate);
            continue;
          }
          const next = e.from === at ? e.to : e.to === at ? e.from : null;
          if (!next || seen.has(next)) continue;
          seen.add(next); go(next, seen, loops, [...steps, e.predicate]); seen.delete(next);
        }
      };
      go(a, new Set([a]), new Set(), []);
      return best;
    };
    const subsets = (xs) => xs.reduce((acc, x) => acc.concat(acc.map((s) => [...s, x])), [[]]);
    const newList = (a, b) => {
      const best = new Map();
      for (const r of pathsBetween(DECL_BOX, a, b)) {
        for (const on of subsets(r.loops.map((l) => l.predicate))) {
          const { follow, hops } = routeWith(r, new Set(on));
          const key = [...follow].sort().join('|');
          if (!best.has(key) || hops < best.get(key)) best.set(key, hops);
        }
      }
      return best;
    };
    const lost = [], gained = [], overCap = [];
    let pairs = 0;
    for (const a of types) for (const b of types) {
      if (a === b) continue;
      pairs += 1;
      const o = oldList(a, b), n = newList(a, b);
      for (const [k, h] of o) if (n.get(k) !== h) lost.push(`${a}>${b} ${k} ${h}->${n.get(k)}`);
      for (const [k, h] of n) if (!o.has(k)) (h > limit ? overCap : gained).push(`${a}>${b} ${k} ${h}`);
    }
    ok('RC1 every {follow, hops} of the old list is a route with some chips on, same hops',
      lost.length === 0 && pairs > 0, lost.slice(0, 3).join(' ; '));
    ok('RC2 and the other way: a route with chips on is an old line, unless it runs past the old cap',
      gained.length === 0, gained.slice(0, 3).join(' ; '));
    ok('RC2b the only new ones are past the old cap (it counted loop steps; a route + its chips may not)',
      overCap.every((s) => Number(s.split(' ').pop()) > limit), overCap.join(' ; '));
    const dw = pathsBetween(DECL_BOX, 'die', 'wafer');
    eq('RC3 die -> wafer: one row per follow set without its loops',
      dw.map((r) => r.follow.slice().sort().join('+')).sort().join(' ; '),
      'in_container ; inspected ; leads_to+measures+observed+of_kind');
    ok('RC4 ... each row carries die\'s two loops as chips, and the row itself walks none of them',
      dw.every((r) => r.loops.map((l) => l.predicate).sort().join('+') === 'bonded_from+transfer'
        && !r.follow.includes('transfer') && !r.follow.includes('bonded_from')
        && r.hops === r.chain.length - 1), JSON.stringify(dw));
    const one = dw.find((r) => r.follow.join() === 'in_container');
    eq('RC5 a chip on adds its loop to follow and one hop', JSON.stringify(routeWith(one, new Set(['transfer']))),
      JSON.stringify({ follow: ['in_container', 'transfer'], hops: 2 }));
    eq('RC6 no chip on is the row as it stands', JSON.stringify(routeWith(one, new Set())),
      JSON.stringify({ follow: ['in_container'], hops: 1 }));
    const viaKind = pathsBetween(DECL_BOX, 'wafer', 'defect_kind').find((r) => r.follow.includes('leads_to'));
    ok('RC7 a loop the route already walks as a step is not a chip (leads_to on quantity -> defect_kind)',
      viaKind && !viaKind.loops.some((l) => l.predicate === 'leads_to'), JSON.stringify(viaKind));
    // A route back to the start type (lead 10-09): the start is reached again only on arriving.
    const back = pathsBetween(DECL_BOX, 'wafer', 'wafer');
    const out = back.find((r) => r.follow.join() === 'in_container');
    ok('RC12 wafer -> wafer: die by in_container and back, two hops, die\'s two loops as its chips',
      Boolean(out) && out.chain.join(' ') === 'wafer die wafer' && out.hops === 2
        && out.loops.map((l) => l.predicate).sort().join('+') === 'bonded_from+transfer'
        && JSON.stringify(routeWith(out, new Set(['bonded_from']))) === JSON.stringify({ follow: ['in_container', 'bonded_from'], hops: 3 }),
      JSON.stringify(out));
    ok('RC13 ... and every route back passes its start type only at its two ends',
      back.length > 1 && back.every((r) => r.chain[0] === 'wafer' && r.chain[r.chain.length - 1] === 'wafer'
        && !r.chain.slice(1, -1).includes('wafer')), JSON.stringify(back.map((r) => r.chain)));
    const dd = pathsBetween(DECL_BOX, 'die', 'die');
    ok('RC14 a self-loop is still a chip, not a route back by itself (owner 10-02): die -> die goes out and back',
      dd.length > 0 && dd.every((r) => r.hops > 1 && !r.follow.includes('bonded_from') && !r.follow.includes('transfer')),
      JSON.stringify(dd.map((r) => [r.chain.join('>'), r.follow.join('+')])));

    // ── both callers: the same rows, chips off by default, a chip on fills follow and one hop ──
    const bdoc = makeDoc();
    const bhost = bdoc.createElement('div');
    const bbox = new WalkBoxPanel(bhost, { doc: bdoc, markings: new MarkingStore(), reads: 'marking:1',
      writes: 'marking:2', loadDeclaration: () => Promise.resolve(DECL_BOX),
      walk: () => Promise.resolve({ ok: true, nodes: [] }) });
    bbox.mount();
    await settle();
    bbox.setType('die'); bbox.destination = 'wafer'; bbox.render();
    const boxRows = () => walkAll(bhost).filter((e) => String(e.className).startsWith('rb-walkbox-route'));
    const boxChips = () => walkAll(bhost).filter((e) => String(e.className).startsWith('rb-walkbox-loopchip'));
    const pdoc = makeDoc();
    pdoc.head = pdoc.createElement('head');
    const phost = pdoc.createElement('div');
    const ppage = walkPage.boot(pdoc, phost, { apiBase: '',
      fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL_BOX }) });
    await settle();
    ppage.state.type = 'die'; ppage.state.collect = new Set(['wafer']); ppage.render();
    const pageRows = () => walkAll(phost).filter((e) => e.className === 'wk-path');
    const pageChips = () => walkAll(phost).filter((e) => String(e.className).startsWith('wk-loopchip'));
    // the walkable rows (the 4-hop one steps out of a static type and the walk refuses it)
    const walkable = bbox.routes().length;
    ok('RC8 both callers draw the same rows for die -> wafer, each with its loop chips, all off',
      walkable > 0 && boxRows().length === walkable && pageRows().length === walkable
        && boxChips().length === 2 * walkable && pageChips().length === 2 * walkable
        && [...boxChips(), ...pageChips()].every((c) => c.getAttribute('aria-pressed') === 'false'),
      `box ${boxRows().length}/${boxChips().length} page ${pageRows().length}/${pageChips().length}`);
    const first = bbox.routes()[0];
    boxRows()[0].click();
    ok('RC9 pressing a row with no chip on walks the route as it stands',
      [...bbox.follow].sort().join('+') === first.follow.slice().sort().join('+') && bbox.hops === first.hops,
      `${[...bbox.follow]} ${bbox.hops}`);
    boxChips().find((c) => c.getAttribute('data-loop') === 'transfer').click();
    ok('RC10 the box: pressing a loop chip adds it to that route and one hop, and the chip shows on',
      bbox.follow.has('transfer') && bbox.hops === first.hops + 1
        && boxChips().find((c) => c.getAttribute('data-loop') === 'transfer').getAttribute('aria-pressed') === 'true',
      `${[...bbox.follow]} ${bbox.hops}`);
    pageChips()[0].click();
    const pfirst = pathsBetween(DECL_BOX, 'die', 'wafer')
      .sort((a, b) => a.hops - b.hops || a.follow.length - b.follow.length)[0];
    ok('RC11 the page: pressing a loop chip fills follow with the route and that loop, and one hop more',
      ppage.state.hops === String(pfirst.hops + 1)
        && [...ppage.state.follow].map((n) => n.split('@')[0]).sort().join('+')
          === [...pfirst.follow, pfirst.loops[0].predicate].sort().join('+'),
      `${[...ppage.state.follow]} ${ppage.state.hops}`);
  }

  console.log(`${LF}-- C. unpicked FOLLOW is ABSENT from the request, not an empty list --`);
  panel.setType('die');
  panel.collect = 'quantity';
  await panel.run();
  await settle();
  eq('C1 one walk went out', asked.length, 1);
  ok('C2 and it carries NO follow key at all', !('follow' in asked[0]), JSON.stringify(asked[0]));
  eq('C3 the type on screen is the one asked', asked[0].type, 'die');
  eq('C3-bis and no collect rides along', 'collect' in asked[0], false);
  panel.toggleFollow('observed');
  await panel.run();
  await settle();
  // 🔴 2026-08-29 (round V): 전선의 철자가 «벗겨진 이름»입니다. 선언은 `observed` 로
  //    부르고 라우트는 그것을 «422» 로 거절합니다 -- 실측: follow=inspected 200 ·
  //    follow=inspected «422». 이 단언은 여태 «라우트가 거절하는 값»을 기대하고
  //    있었습니다. 재는 것(「고른 것이 요청에 실린다」)은 그대로이고 철자만 참으로 옮깁니다.
  eq('C4 picking one puts it on the request', JSON.stringify(asked[1].follow), '["observed"]');
  panel.toggleFollow('observed');
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
  console.log(`${LF}-- P. C-70: sections AND columns come from the walk PAGE's function --`);
  {
    const { sectionsByType, sectionHeading, tableColumns, COLUMNS } = mods.derive;
    // 🔴 MIXED TYPES ON PURPOSE, AND THAT IS THE DISCRIMINANT. This box sends no `collect`, so
    //    the server default returns everything the walk reached. A flat table naming its own
    //    three columns passes a single-type fixture and is WRONG here -- the declared key names
    //    differ per type, so `wafer` under `die`'s columns would draw empty cells and raise
    //    nothing. The old fixture was two `die` rows, which could not tell the two apart.
    const MIXED = [
      { id: 'n:1', type: 'die', label: 'D-1',
        keys: { mat_id: 'M-1', x: 1, y: 2, mat_type: 'Wafer' } },
      { id: 'n:2', type: 'die', label: 'D-2',
        keys: { mat_id: 'M-2', x: 3, y: 4, mat_type: 'Wafer' } },
      { id: 'n:3', type: 'wafer', label: 'W-1', keys: { wafer: 'SYN-1' } },
    ];
    const doc2 = makeDoc();
    const host2 = doc2.createElement('div');
    const panel2 = new WalkBoxPanel(host2, {
      doc: doc2, markings: new MarkingStore(), reads: 'marking:1', writes: 'marking:2',
      loadDeclaration: () => Promise.resolve(DECL),
      walk: () => Promise.resolve({ ok: true, nodes: MIXED }),
    });
    panel2.mount();
    await settle();
    panel2.setType('die');
    await panel2.run();
    await settle();

    const titles = walkAll(host2).filter((e) => (e.className || '').includes('rb-part-title'))
      .map((e) => e.textContent);
    eq('P1 one section head per type, worded by the shared function, in the walk\'s order',
      titles.join(' | '),
      [...sectionsByType(MIXED)].map(([t, n]) => sectionHeading(t, n.length)).join(' | '));

    // 🔴 THE GATE. Not 「the headers look right」 but 「the headers ARE that function's answer」.
    //    A second author here would have to reproduce the order too, and this compares both.
    const headLabels = walkAll(host2)
      .filter((e) => (e.className || '').includes('rb-table-cell--head'))
      .map((e) => e.textContent);
    eq('P2 every column label is the walk page function\'s answer, in its order',
      headLabels.join(','),
      [...sectionsByType(MIXED)].map(([t]) => tableColumns(DECL.entities, t, [],
        COLUMNS.FOR_PICKING).map((c) => c.name).join(',')).join(','));

    const rows2 = walkAll(host2).filter((e) => (e.className || '').includes('rb-table-row'));
    eq('P3 sectioning neither drops a node nor invents one', rows2.length, MIXED.length);
    const cellsOf = (row) => row.children.map((c) => c.textContent);
    eq('P4 a declared key reaches its own cell', cellsOf(rows2[0]).join('|'), 'M-1|1|2|Wafer|D-1');
    // 🔴 THIS ONE FAILS IF THE COLUMNS ARE HARD-CODED ANYWHERE. Under `label · type · id` the
    //    wafer row reads 「W-1|wafer|n:3」; under its OWN declaration it reads its key then
    //    its label. Same rows, same count, different truth.
    eq('P5 a row of another type is drawn under THAT type\'s declared keys',
      cellsOf(rows2[2]).join('|'), 'SYN-1|W-1');
    eq('P6 clicking a row in a later section still marks THAT node',
      (() => { rows2[2].click({}); return panel2.markings.signOf('marking:2', 'n:3'); })(), SIGN.CASE);
  }

  console.log(`${LF}-- S. the seed id is base64URL, and the server requires it --`);
  {
    const { entitySeedId } = A;
    // 🔴 THE KEY THAT DECIDES IT. Every seed this screen uses today encodes without a `+` or a
    //    `/`, so standard base64 and base64url produce the SAME string and the rule cannot be
    //    falsified by real data. `SYN-BW-101-16>` is the first key whose JSON base64 carries a
    //    `+`. Measured live 2026-08-27: standard base64 -> HTTP 422, base64url -> 200. This is
    //    a contract the server enforces, not a taste, and it was correct-but-unverified until
    //    an input was MADE that could tell the two apart.
    const withPlus = entitySeedId('wafer', { wafer: 'SYN-BW-101-16>' });
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
      entitySeedId('wafer', { wafer: 'SYN-CX-BW-001' }),
      'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0');
    // The server's own ids (fixtures/capture_entity_ids.py), keys given in the order the form types them (lead 10-10).
    const SERVER_IDS = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'server_entity_ids.json'), 'utf8'));
    const spelled = (i) => entitySeedId(SERVER_IDS[i].type, SERVER_IDS[i].keys);
    eq('S7 a composite key typed in the form\'s order is spelled as the server spells it', spelled(0), SERVER_IDS[0].id);
    eq('S8 number keys as the ledger holds them, spelled as the server spells them', spelled(1), SERVER_IDS[1].id);
    eq('S9 keys already in order: the same id', spelled(2), SERVER_IDS[2].id);
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
  a.setType('die'); a.collect = 'point';
  b.setType('lot_slot'); b.collect = 'event';
  a.toggleFollow('observed');
  await a.run(); await b.run();
  await settle();
  eq('D1 A asked with its own type', askedA[0].type, 'die');
  eq('D2 B asked with its own', askedB[0].type, 'lot_slot');
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
      // 🔴 THE REAL DECODER, not a hand-made copy of what it returns. This fixture used to
      //    build the walk result itself -- `{ok, nodes, truncated}` -- and that made it a
      //    fixture imitating its subject: when `createWalkBoxWalk` learned to fold `truncated`
      //    into `cut`/`truncatedAxes`, the panel read the new fields and the stub still served
      //    the old shape, so this went red for a change that was correct. It now stubs the
      //    FETCH and lets the real function decode, which is the only version of this test that
      //    can still be true after the decoder changes.
      // The body is the shape the live route really returns -- measured 2026-08-27, wafer
      // SYN-BW-101-16: depth false, everything else true. A budget cut, not a depth question.
      walk: A.createWalkBoxWalk({
        apiBase: '',
        fetchImpl: async () => ({ ok: true, json: async () => ({
          nodes: NODES, edges: [], truncated: {
            depth: false, nodes: true, edges: true, claims: true, actions: true,
            reason: 'nodes, edges, claims, actions' } }) }),
      }),
    });
    pt.mount();
    await settle();
    pt.setType('die');
    await pt.run();
    await settle();
    const cutText = textOf(hostT);
    ok('T1 a truncated walk says so', cutText.includes('Truncated at'), cutText.slice(-100));
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
    pq.setType('die');
    await pq.run();
    await settle();
    ok('T4 a walk that was NOT cut stays silent', !textOf(hostQ).includes('Truncated at'),
      textOf(hostQ).slice(-80));
    ok('T4b and a walk with no truncated key at all stays silent too',
      !textOf(host).includes('Truncated at'));
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
    noDecl.includes('Server refused'), noDecl.slice(0, 90));
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
  ok('E3 nothing chosen yet has its own seat', before.includes(UNPICKED),
    before.slice(-90));
  pn.setType('die');
  await pn.run();
  await settle();
  const after = textOf(hostN);
  ok('E4 walked-and-empty is a DIFFERENT sentence', after.includes('Walked, reached nothing'),
    after.slice(-90));
  ok('E5 and it is not the not-chosen one', !after.includes(UNPICKED));

  const hostF = doc.createElement('div');
  const pf = new WalkBoxPanel(hostF, {
    doc, markings, reads: 'marking:1', writes: 'marking:2',
    loadDeclaration: () => Promise.resolve(DECL),
    walk: () => Promise.resolve({ ok: false, message: '서버가 거절했습니다 (HTTP 503)' }),
  });
  pf.mount();
  await settle();
  pf.setType('die');
  await pf.run();
  await settle();
  const refused = textOf(hostF);
  ok('E6 a refused walk carries the server sentence', refused.includes('HTTP 503'), refused.slice(-90));
  ok('E7 which is neither of the other two',
    !refused.includes('Walked, reached nothing') && !refused.includes(UNPICKED));

  // ── W: the reader hands the node ON, it does not re-author it ────────────────────────
  // 🔴 THE DEFECT THIS CLOSES HAPPENED TWICE IN THREE DAYS, in the same line. `createWalkBoxWalk`
  //    rebuilt each node from a FIELD LIST, so anything the server learned to send died here:
  //    `keys` and `depth` on 09-06 (the table could not name a row or say how far it was), and
  //    `attributes`/`attribute_conflicts` on 09-08 (the declaration named the columns, the table
  //    drew the headers, every cell was empty). NO ERROR EITHER TIME — and the second time the
  //    contract harness was green throughout, because it held the post-narrowing shape by hand.
  // 🔴 SO THE ASSERTION IS ABOUT THE CLASS, NOT THE TWO NAMES. A field nobody has invented yet
  //    has to survive too; naming only today's fields would pass this test and fail the next
  //    round exactly as before.
  {
    const sent = {
      id: 'ledger-entity:v1:WWW', type: 'dtjob', label: 'J-1', depth: 1,
      keys: { dt_job: 'SYN-DTJ-002-04' },
      attributes: { dt_eqp: 'SYN-DTE-03' }, attribute_conflicts: 0,
      a_field_invented_after_this_test_was_written: 'survives',
    };
    const walk = A.createWalkBoxWalk({ apiBase: '',
      fetchImpl: async () => ({ ok: true, status: 200,
        json: async () => ({ nodes: [sent], edges: [], truncated: null }) }) });
    const got = await walk({ type: 'dtjob', keys: { dt_job: 'SYN-DTJ-002-04' } });
    const node = got.ok && got.nodes ? got.nodes[0] : null;
    ok('W1 the walk read succeeds', !!node, JSON.stringify(got).slice(0, 90));
    ok('W2 a declared value reaches the caller',
      node && node.attributes && node.attributes.dt_eqp === 'SYN-DTE-03',
      JSON.stringify(node && node.attributes));
    ok('W3 ...and so does the disagreement count, INCLUDING when it is 0',
      node && node.attribute_conflicts === 0, String(node && node.attribute_conflicts));
    ok('W4 a field this test never heard of survives too — the narrowing is gone, not widened',
      node && node.a_field_invented_after_this_test_was_written === 'survives');
    ok('W5 and the fields that were rescued in 09-06 are still there',
      node && node.depth === 1 && node.keys && node.keys.dt_job === 'SYN-DTJ-002-04');
    // ⚠️ CONTROL. If the reader started passing the whole BODY through, or the stub were
    //    wired wrong, W2-W5 would pass on something that is not a node at all.
    ok('W6 CONTROL: what came back is the node, not the envelope',
      node && node.id === sent.id && got.nodes.length === 1);
  }

  // ══ C-97 (판정 365). 키를 «안 골랐으면» 씨앗을 서술한다 ═══════════════════════════
  //
  // 🔴 재는 것은 «나가는 요청»입니다. 실측 2026-09-13, 라이브 라우트에 직접: 오늘 이 화면이
  //    타입만 고르고 걸으면 `id=…WyJ3YWZlciIse31d`(빈 키) 가 나가 «422» 를 받습니다 --
  //    `entity id must contain [type, structured keys]`. 즉 주어를 모르면 걸을 수 없었고,
  //    「이 타입이 무엇에 닿나」는 주어를 «모를 때» 묻는 질문입니다.
  // ⛔ 서버는 `id` 와 `seed_type` 을 «같이» 주는 것을 거절합니다. 그래서 「둘 중 하나」가
  //    단언이지 「seed_type 이 있다」가 아닙니다 -- 둘 다 실리면 그 거절이 화면에서 「고장」이 됩니다.
  console.log(`${LF}-- X. 키를 안 고르면 씨앗을 «서술»한다 (C-97) --`);
  {
    const asked = [];
    const walk = A.createWalkBoxWalk({ apiBase: '',
      fetchImpl: async (url) => { asked.push(String(url)); return { ok: true, status: 200,
        json: async () => ({ nodes: [], edges: [], truncated: null }) }; } });
    const query = (i) => new URLSearchParams(String(asked[i]).split('?')[1] || '');

    await walk({ type: 'wafer', keys: {} });
    eq('XS1 타입만 고르면 씨앗을 서술한다 — 버전은 벗겨서',
      query(0).get('seed_type'), 'wafer');
    ok('XS2 ...그리고 `id` 는 «안 실린다» (서버가 둘 다를 거절한다)',
      query(0).get('id') === null, asked[0]);

    await walk({ type: 'wafer', keys: { wafer: 'SYN-CX-BW-001' } });
    eq('XS3 키를 고르면 오늘 그대로 열거된 씨앗이다',
      query(1).get('id'),
      'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0');
    ok('XS4 ...그리고 그때는 `seed_type` 이 «안 실린다»',
      query(1).get('seed_type') === null, asked[1]);

    // 🔴 빈 «문자열» 키는 「안 고름」입니다 -- `run()` 이 이미 그렇게 접고, 이 층도 같은 답을
    //    내야 합니다. 두 층이 갈리면 칸을 비운 사람이 422 를 받습니다.
    await walk({ type: 'wafer' });
    eq('XS5 키 칸이 아예 없어도 서술이다', query(2).get('seed_type'), 'wafer');

    // ⚠️ CONTROL. 서술된 씨앗도 «씨앗»이라, 관문이 「아직 안 골랐다」로 막으면 안 됩니다.
    ok('XS6 CONTROL: 서술된 걷기가 실제로 «나갔다» (관문이 먹지 않았다)', asked.length === 3,
      String(asked.length));
  }

  // ══ C-97. 잘린 축이 «수»로 와도 잘린 것이다 ══════════════════════════════════════
  //
  // 🔴 실측: `seed_type` 절단은 `truncated.seeds: 1` -- 몇을 «안 걸었는지»를 수로 말합니다.
  //    `=== true` 만 읽으면 그 절단이 화면에서 사라지고, 사라진 절단은 「그게 전부였다」로
  //    읽힙니다 -- 이 축 목록이 존재하는 이유 그대로입니다.
  console.log(`${LF}-- Y. 수로 오는 절단 (C-97) --`);
  {
    const walkWith = (truncated) => A.createWalkBoxWalk({ apiBase: '',
      fetchImpl: async () => ({ ok: true, status: 200,
        json: async () => ({ nodes: [], edges: [], truncated }) }) });

    const cutSeeds = await walkWith({ depth: false, nodes: false, seeds: 1,
                                      reason: 'seeds' })({ type: 'wafer', keys: {} });
    ok('Y1 `seeds: 1` 은 잘린 축이다', (cutSeeds.truncatedAxes || []).includes('seeds'),
      JSON.stringify(cutSeeds.truncatedAxes));
    ok('Y2 ...그리고 「잘림」이 서 있다', cutSeeds.cut === true);

    const none = await walkWith({ depth: false, nodes: false, seeds: 0, reason: null })(
      { type: 'wafer', keys: {} });
    ok('Y3 `seeds: 0` 은 «안 잘린» 것이다 — 0 은 「전부 걸었다」이지 절단이 아니다',
      !(none.truncatedAxes || []).includes('seeds'), JSON.stringify(none.truncatedAxes));

    // 🔴 그 하나의 예외. `interval_excluded` 는 예산에 걸려 못 간 것이 아니라 «구간 밖이라
    //    안 가져온» 것이고, 자기 독자가 따로 있습니다. 절단 축에 세면 「예산이 모자랐다」를
    //    구간이 한 일에 대고 말하게 됩니다.
    const interval = await walkWith({ depth: false, nodes: false, interval_excluded: 7,
                                      reason: null })({ type: 'wafer', keys: {} });
    ok('Y4 `interval_excluded` 는 수여도 절단이 «아니다»',
      !(interval.truncatedAxes || []).includes('interval_excluded'),
      JSON.stringify(interval.truncatedAxes));
    eq('Y5 ...그리고 그 수는 자기 자리에서 읽힌다', interval.intervalExcluded, 7);
  }

  // ══ C-51. 「언제부터 언제까지」 — 칸 둘, 그리고 돌아온 수 ═══════════════════════════
  //
  // 🔴 THE COMPONENT DOES NOT FILTER. These two boxes are a QUESTION; the walk answers it
  //    (standing: 「부품이 거르면 어긴 것」). So what is measured here is what the panel PUTS
  //    IN THE SPEC and what it DRAWS — never a narrowing of its own.
  console.log(`${LF}-- V. the interval: two boxes, an empty one is not an interval --`);
  {
    const names = () => byAttr(host, 'data-interval').map((e) => e.getAttribute('data-interval'));
    eq('V1 two date boxes, named as the route names them', names().join(','), 'since,until');
    asked.length = 0;
    panel.setType('wafer');
    await panel.run();
    const bare = asked[asked.length - 1] || {};
    ok('V2 empty boxes put NOTHING in the spec — 「구간 없음」 is not 「1970」',
      !('since' in bare) && !('until' in bare), JSON.stringify(bare));
    panel.since = '2026-09-01';
    panel.until = '2026-09-08';
    asked.length = 0;
    await panel.run();
    const filled = asked[asked.length - 1] || {};
    eq('V3 a filled box travels', `${filled.since}|${filled.until}`, '2026-09-01|2026-09-08');
    // 🔴 ONE END IS A LEGAL QUESTION, and a panel that only ever sent pairs would pass V3.
    panel.until = '';
    asked.length = 0;
    await panel.run();
    const oneEnd = asked[asked.length - 1] || {};
    ok('V4 one end alone still travels, and the other stays out',
      oneEnd.since === '2026-09-01' && !('until' in oneEnd), JSON.stringify(oneEnd));
    panel.since = '';
  }

  console.log(`${LF}-- W-bis. 「구간 밖 N」 — absent is not zero, on the SCREEN --`);
  {
    const drawWith = async (result) => {
      const d = makeDoc();
      const h = d.createElement('div');
      const p = new WalkBoxPanel(h, {
        doc: d, markings: new MarkingStore(), reads: 'marking:1', writes: 'marking:2',
        loadDeclaration: () => Promise.resolve(DECL),
        walk: () => Promise.resolve({ ok: true, nodes: NODES, ...result }),
      });
      p.mount();
      await settle();
      p.setType('wafer');
      await p.run();
      return h;
    };
    const textOf = (h) => h.textContent;
    ok('X1 a measured zero is SAID — 「물었고 제외된 게 없다」 is an answer',
      /Outside the interval 0/.test(textOf(await drawWith({ intervalExcluded: 0 }))));
    ok('X2 a real count is said', /Outside the interval 37/.test(textOf(await drawWith({ intervalExcluded: 37 }))));
    // 🔴 THE DISCRIMINANT: no interval asked -> the line is NOT DRAWN. Without this, X1 is
    //    satisfied by a panel that prints the line unconditionally.
    ok('X3 an unasked interval draws NO line at all',
      !/Outside the interval/.test(textOf(await drawWith({ intervalExcluded: null }))),
      textOf(await drawWith({ intervalExcluded: null })).slice(0, 80));
    ok('X4 ...and neither does a walk that never carried the field',
      !/Outside the interval/.test(textOf(await drawWith({}))));
  }

  return { ran, failed: failedList.slice() };
}

// 🔴 THREE MUTANTS RETIRED 2026-08-28 with the COLLECT dropdown they mutated
//    (`a-kind-with-no-label-is-drawn-blank`, `the-label-is-sent-instead-of-the-id`,
//    `the-object-shape-is-not-understood`). Their anchors are gone from the panel, and a
//    mutant whose anchor is absent reports as a harness failure rather than as a caught
//    defect -- which is the honest behaviour, and why they leave rather than linger.
const MUTANTS = [
  { name: 'the-keys-keep-the-form-order', catches: ['S7', 'S8'], file: 'api.js',
    from: "  const json = `[${JSON.stringify(String(type || ''))},{${Object.keys(held).sort()",
    to: "  const json = `[${JSON.stringify(String(type || ''))},{${Object.keys(held)" },
  // 🔴 THE ONE THAT COST TWO ROUNDS. Rebuilding the node from a field list is how
  //    `keys`/`depth` died on 09-06 and `attributes` on 09-08 -- the server sends it, the
  //    screen draws an empty cell, and nothing raises. The mutant restores exactly the line
  //    that was there, so if anyone reintroduces it W2-W5 go red.
  { name: 'the-node-is-rebuilt-from-a-field-list', catches: ['W2', 'W3', 'W4'], file: 'api.js',
    from: "      const nodes = Array.isArray(body.nodes) ? body.nodes : [];",
    to: "      const nodes = (body.nodes || []).map((n) => ({ id: n.id, type: n.type,"
        + " label: n.label, keys: n.keys || null, depth: n.depth }));" },
  // 🔴 C-70. The screen naming its own columns is the defect this round closed, so it is the
  //    mutant. Under a hard-coded list the ROW COUNT is unchanged and nothing throws -- P2 and
  //    P5 are what tell a screen following the declaration from one repeating it.
  { name: 'the-picking-list-names-its-own-columns', catches: ['P2', 'P5'],
    from: "      const cols = tableColumns(entities, type, [], COLUMNS.FOR_PICKING);",
    to: "      const cols = [{ name: 'label', kind: 'label' }, { name: 'type', kind: 'type' },"
        + " { name: 'id', kind: 'id' }];" },
  // 🔴 And the other half: without sections there is no per-type place to ask the declaration
  //    from, so a flat list silently draws every type under the SEED type's keys.
  { name: 'the-result-is-not-sectioned-by-type', catches: ['P1', 'P5'],
    from: "    const sections = sectionsByType(rows);",
    to: "    const sections = new Map(rows.length ? [[this.nodeType, rows]] : []);" },
  // ① the gate the order names: a fixed four-field form.
  { name: 'the-key-form-is-four-fixed-fields', catches: ['A2', 'A3', 'A4'],
    from: "    return (found && found.keys) || [];",
    to: "    return ['mat_id', 'x', 'y', 'mat_type'];" },
  { name: 'keys-survive-a-type-that-lacks-them', catches: ['A5'],
    from: "    for (const k of keys) if (this.keyValues[k] !== undefined) kept[k] = this.keyValues[k];\n    this.keyValues = kept;",
    to: "    for (const k of keys) if (this.keyValues[k] !== undefined) kept[k] = this.keyValues[k];" },
  // ② the touchstone: an empty dropdown instead of a sentence.
  { name: 'an-empty-follow-list-is-drawn-as-a-list', catches: ['B4', 'B6'],
    from: "      box.appendChild(this._note(this.nodeType",
    to: "      return box; box.appendChild(this._note(this.nodeType" },
  { name: 'follow-is-not-narrowed-by-type', catches: ['B1', 'B3'],
    from: "    return predicatesTouching(decl.predicates || [], this.nodeType, decl.entities);",
    to: "    return (decl.predicates || []).map((p) => p.name);" },
  // 🔴 10-02. The copy this round removed: the box answering on its own, subject side only.
  { name: 'the-box-keeps-its-own-subject-only-copy', catches: ['B1', 'B3'],
    from: "    return predicatesTouching(decl.predicates || [], this.nodeType, decl.entities);",
    to: "    const all = decl.predicates || []; if (!this.nodeType) return all.map((p) => p.name);"
        + " return all.filter((p) => (p.subjects || []).includes(this.nodeType)).map((p) => p.name);" },
  // 🔴 10-02. The route list that did not ask the walk's step rule — the walk page's did.
  { name: 'the-box-route-list-offers-what-the-walk-refuses', catches: ['K1', 'K3'],
    from: "    return keepWalkableRoutes(this.declaration.entities,\n"
        + "      pathsBetween(this.declaration, bareTypeName(this.nodeType), this.destination));",
    to: "    return pathsBetween(this.declaration, bareTypeName(this.nodeType), this.destination);" },
  { name: 'ticked-follow-survives-a-type-change', catches: ['H3'],
    from: "    this.follow = new Set([...this.follow].filter((f) => allowed.has(f)));\n    this.result = null;",
    to: "    this.result = null;" },
  // ③ an empty array is the OPPOSITE of the server default.
  { name: 'unpicked-follow-is-sent-as-an-empty-array', catches: ['C2', 'C5'],
    // 앵커 갱신 2026-08-29 (round V): 그 줄이 전선에서 버전을 «벗기게» 바뀌었습니다.
    // 재는 것은 그대로입니다 -- 「안 고른 follow 를 빈 배열로 보내지 않는다」.
    from: "    if (this.follow.size) spec.follow = [...this.follow].map(bareTypeName);",
    to: "    spec.follow = [...this.follow].map(bareTypeName);" },
  { name: 'blank-key-boxes-are-sent-as-filters', catches: ['C6 a cleared key box'],
    from: "    for (const [k, v] of Object.entries(this.keyValues)) if (v !== '' && v !== undefined) keys[k] = v;",
    to: "    for (const [k, v] of Object.entries(this.keyValues)) keys[k] = v;" },
  // ⑤ one sentence for every absence.
  { name: 'the-cut-is-not-mentioned', catches: ['T1', 'T2'],
    from: "    if (cut) box.appendChild(this._note(",
    to: "    if (false) box.appendChild(this._note(" },
  // 🔴 THE MUTANT TARGETS THE *RENDER* CONDITION, NOT THE `.reason` GUARD, BECAUSE THAT GUARD
  //    IS REDUNDANT: `if (cut)` already rejects the empty string the route sends when nothing
  //    was cut, so removing `.reason` changes nothing and the mutant sat inert. The defect that
  //    IS observable is announcing a cut whenever the KEY is present -- which is every walk.
  { name: 'a-cut-is-reported-whenever-the-key-is-present', catches: ['T4 a walk that was NOT cut'],
    from: "    if (cut) box.appendChild(this._note(",
    to: "    if (this.result && this.result.truncated) box.appendChild(this._note(" },
  { name: 'every-absence-shares-one-sentence', catches: ['E4', 'E6'],
    from: "    if (this.walkState === 'ready') return 'Walked, reached nothing';",
    to: "    if (this.walkState === 'ready') return UNPICKED;" },
  { name: 'a-missing-route-reads-as-an-empty-result', catches: ['E1'],
    from: "    if (this.declState !== 'ready') {",
    to: "    if (false) {" },
  // 🔴 10-02 (lead 5d5b8d750). The loop chips: off by default, one hop each, never a loop the route
  //    already walks, never one at the destination (the walk stops on arriving), and the box asks them.
  { name: 'the-loop-chips-are-on-by-default', catches: ['RC6 ', 'RC9 '], file: 'api.js',
    from: "const picked = (route.loops || []).filter((l) => on && on.has(l.predicate));",
    to: "const picked = route.loops || [];" },
  { name: 'a-loop-the-route-already-walks-is-a-chip', catches: ['RC7 '], file: 'api.js',
    from: "if (edge.from !== edge.to || edge.from !== at || follow.includes(edge.predicate)",
    to: "if (edge.from !== edge.to || edge.from !== at" },
  { name: 'a-loop-chip-adds-no-hop', catches: ['RC5 ', 'RC10 '], file: 'api.js',
    from: "hops: route.hops + picked.length };", to: "hops: route.hops };" },
  // A route back to the start type (lead 10-09).
  { name: 'a-route-never-comes-back', catches: ['RC12 '], file: 'api.js',
    from: "      if (seen.has(next) && next !== to) continue;", to: "      if (seen.has(next)) continue;" },
  { name: 'a-route-walks-on-past-its-destination', catches: ['RC13 '], file: 'api.js',
    from: "    if (chain.length && at === to) { out.push(chain.slice()); return; }",
    to: "    if (chain.length && at === to) { out.push(chain.slice()); if (chain.length > 2) return; }" },
  { name: 'a-self-loop-onto-the-destination-is-a-route', catches: ['RC14 '], file: 'api.js',
    from: "      if (edge.from === edge.to) continue;", to: "      if (edge.from === edge.to && edge.from !== to) continue;" },
  { name: 'a-loop-at-the-destination-is-offered', catches: ['RC2 '], file: 'api.js',
    from: "for (const at of chain.slice(0, -1)) {", to: "for (const at of chain) {" },
  { name: 'the-box-route-ignores-its-chips', catches: ['RC10 '],
    from: "    const asked = routeWith(route, this.loopsOf(route));\n    this.chosenPath = index;",
    to: "    const asked = routeWith(route, new Set());\n    this.chosenPath = index;" },
];

const main = async () => {
  console.log('== baseline ==');
  const base = await suite(await loadModules());
  const BASE_NAMES = NAMES.slice();   // snapshot: later runs append to the same array
  console.log(`${LF}${base.ran - base.failed.length} passed, ${base.failed.length} failed.`);
  if (base.failed.length) {
    console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`);
    process.exit(1);
  }

  // 🔴 C-66 ①. SCORED BY `lib/mutation_scorer.mjs`, AND THAT CHANGES WHAT `wakes` MEANS.
  //    This file already PRINTED the named assertion beside every verdict — and never checked
  //    it: `caught` was 「some assertion failed」, and a suite that THREW was folded in as
  //    `failed: ['threw: …']`, i.e. counted as a catch. Printing a name you do not verify is the
  //    quieter half of the same defect: the line the mutant exists to protect can rot away while
  //    its id keeps appearing in the output. `wakes` is now `catches`, the scorer matches it, and
  //    a throw is INERT.
  // ⚠️ A BUILD failure still exits 2 rather than becoming INERT. 「the mutation did not apply」
  //    is the harness losing its subject, not a mutant behaving; it must stop the run, loudly.
  const { wrong: escaped } = await scoreMutants(MUTANTS, async (m) => {
    let mods;
    try {
      mods = await loadModules({
        [m.file || 'walk_box_panel.js']:
          (src) => (src.includes(m.from) ? src.split(m.from).join(m.to) : src),
      });
    } catch (err) {
      console.error(`HARNESS FAILURE: ${err.message} (${m.name})`);
      console.error('(This is not a passing result. Nothing was compared.)');
      process.exit(2);
    }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { await suite(mods); } finally { console.log = real; }
    // `ran` lets the scorer say when a mutant REMOVES assertions instead of failing them.
    return { failures: failedList, ran };
  }, { baselineRan: base.ran, baselineNames: BASE_NAMES,
       title: `${LF}== defect mutants (each must be CAUGHT by its named line) ==` });

  console.log(`${LF}ASSERTIONS ${base.ran} ${base.failed.length}`);
  process.exit(escaped ? 1 : 0);
};

main();
