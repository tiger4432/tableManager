// APPENDED MODULE — 잘라쓰기를 대신할 «다리»가 실제로 다리인지.
//
// 🔴 이 하니스가 재는 것은 «부품 하나»가 아니라 이 저장소의 «규율»입니다:
//    대상 모듈을 잘라내지 «않고» 그 내부를 잴 수 있는가. 지금 하니스 여럿이 대상 파일을
//    텍스트로 읽어 함수를 잘라내고 vm 에 넣는데, 그건 동작이 아니라 «글자 모양»을 잽니다.
//
// 🔴 그리고 여기서 제일 중요한 단언은 「닿는다」가 아니라 «퇴화하지 않는다»입니다 —
//    사본이 원본 바이트로 «시작»하지 않으면 던져야 합니다. 그 단언이 없으면 덧붙이기는
//    조용히 잘라쓰기로 돌아가고, 그때는 아무도 모릅니다.
//
// Run: node client2/tests/appended_module_harness.mjs
import { importWithAccessors, startsWithOriginal } from './lib/appended_module.mjs';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

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

const SRC = new URL('../src/map_editor.js', import.meta.url);
const SRC_DIR = dirname(fileURLToPath(SRC));

// ═══ ① 잘라내지 «않고» 내부에 닿는다 ═══════════════════════════════════════════════════
//
// 🔴 이 파일이 고르는 대상이 우연이 아닙니다: `map_editor.js` 는 이 저장소에서 가장 많이
//    «잘려» 온 파일이고, 잘린 이유로 기록된 것(`import './tokens.css'`)은 2026-09-05 실측
//    기준 «이미 사라졌습니다». 남은 이유는 하나뿐입니다 — 이 모듈은 아무것도 export 하지
//    않아서 밖에서 «잡을 이름»이 없습니다. 그것이 덧붙이기가 필요한 진짜 사유입니다.
console.log('\n[1] the module is reached without cutting it');
{
  const ns = await importWithAccessors(SRC,
    'export const __probe = {'
    + ' table: typeof VALID_DIE_TABLE !== "undefined" ? VALID_DIE_TABLE : null,'
    + ' hasGeometry: typeof applyPhysicalGeometry === "function",'
    + ' };');
  ok('the appended copy imports at all', !!ns);
  // 🔴 값을 «다시 적지» 않습니다 — 여기에 'valid_die_ref' 를 손으로 쓰면 그 순간 두 번째
  //    저자가 생기고, 선언이 바뀌는 날 이 하니스가 «옛 값»을 초록으로 지킵니다.
  ok('a module-level const is readable', typeof ns.__probe.table === 'string'
    && ns.__probe.table.length > 0, `saw ${JSON.stringify(ns.__probe.table)}`);
  ok('...and a module-level function too', ns.__probe.hasGeometry === true);
}

// ═══ ①-bis 2-a — «닿는가»: 잘라내던 46 개와 모듈이 «쓰는» 상태 15 개 ═══════════════
//
// 🔴 이것이 잘라쓰기가 하던 일 «전부»입니다. `valid_die_frame_adoption` 은 46 개 함수를
//    이름으로 잘라 vm 에 넣고, 모듈 최상위 `let` 15 개를 «자기 객체의 속성»으로 흉내 냅니다.
//    덧붙이기로 그 둘 다 닿으면 그 하니스가 «잘라낼 이유»가 없어집니다.
//
// ⚠️ setter 가 필요한 이유: ESM 밖에서는 모듈의 `let` 에 «못 씁니다». 접근자 블록은 모듈
//    «안»에 있으므로 쓸 수 있고, 그것이 이 다리가 사는 이유입니다.
// 🔵 그리고 그 접근자는 «사본»에만 있습니다 — 출하되는 모듈은 setter 를 갖지 않습니다.
const SLICED = (() => {
  const t = readFileSync(new URL('./valid_die_frame_adoption_harness.mjs', import.meta.url), 'utf8');
  const blk = /const SYMBOLS = \[([\s\S]*?)\n\];/.exec(t)[1];
  return [...new Set([...blk.matchAll(/'([A-Za-z_$][\w$]*)'/g)].map((m) => m[1]))];
})();
const MODULE_LETS = ['activeOverlayLayers', 'boundingBoxCache', 'cellsSeatedUnder',
  'currentRotation', 'currentSide', 'gridCells2D', 'gridData', 'isBoxDragging', 'legend',
  'loadedIdentity', 'overlayLayers', 'selectedTable', 'tableSchema', 'validDie',
  'validDieResolveSeq'];

console.log('\n[1-bis] the bridge reaches everything the slicing reached');
{
  const acc = [
    'export const __fn = { ' + SLICED.join(', ') + ' };',
    'export const __get = {', ...MODULE_LETS.map((n) => `  ${n}: () => ${n},`), '};',
    'export const __set = {', ...MODULE_LETS.map((n) => `  ${n}: (v) => { ${n} = v; },`), '};',
  ].join('\n');
  const ns = await importWithAccessors(SRC, acc);
  // 🔴 목록에서 «셉니다». 46 을 손으로 적으면 그 하니스가 심볼을 하나 더할 때 이 수가 거짓이 됩니다.
  const reached = Object.values(ns.__fn).filter((v) => typeof v === 'function').length;
  eq('every sliced symbol is reachable without cutting', reached, SLICED.length);
  ok('...and there is more than a handful of them', SLICED.length > 40, `saw ${SLICED.length}`);
  eq('every module-level binding it fakes has a getter',
    Object.keys(ns.__get).length, MODULE_LETS.length);
  // 🔴 THE ONE THAT MATTERS: writing a module `let` from outside, which ESM forbids and the
  //    accessor block permits. Without this the harness could read but not drive.
  const before = ns.__get.currentRotation();
  ns.__set.currentRotation(before === 90 ? 180 : 90);
  ok('a module-level `let` can be driven from the test',
    ns.__get.currentRotation() !== before);
}


// ═══ ①-ter 2-b — «도는가»: 모듈의 «자기» el 자루를 채우면 실제 함수가 돕니다 ═════════
//
// 🔴 2-b 는 「document 최소 스텁이 필요한가」를 물었고, 답은 «아니오»입니다.
//    모듈은 `const el = {}` 를 최상위에 두고 «나중에» 채웁니다 — 그래서 import 가 DOM 을
//    안 건드리고, 시험은 그 자루에 «직접» 넣으면 됩니다. getElementById 를 흉내 낼 필요가
//    없습니다. 잘라쓰기 샌드박스가 하던 일 중 «가장 큰 덩어리»가 이렇게 사라집니다.
//
// ⚠️ 그리고 이것이 총괄이 요구한 「모형화 안 한 것에 시끄러울 것」을 «더 세게» 만족시킵니다:
//    스텁이 없으므로, 어떤 함수가 document 를 만지면 `ReferenceError: document is not
//    defined` 로 «즉시» 죽습니다. 너그러운 스텁이 조용히 초록을 만들 여지가 «0» 입니다.
const EL_BAG = ['gridCols', 'gridRows', 'gridStartX', 'gridStartY', 'gridYInvert',
  'physChipX', 'physChipY', 'physOffsetX', 'physOffsetY', 'physEdgeMargin',
  'physWaferDia', 'gridCanvas'];

console.log('\n[1-ter] the real functions run once the module bag is filled');
{
  const ns = await importWithAccessors(SRC, [
    'export const __el = el;',
    'export const __fn = { applyPhysicalGeometry, currentFrame, cellMetrics };',
    'export const __set = { currentRotation: (v) => { currentRotation = v; },',
    '  currentSide: (v) => { currentSide = v; }, gridData: (v) => { gridData = v; } };',
    'export const __documentSeen = () => typeof document;',
  ].join('\n'));
  eq('the bag is empty at import, which is why loading needs no DOM',
    Object.keys(ns.__el).length, 0);
  eq('and the module never saw a document', ns.__documentSeen(), 'undefined');
  const mk = (v) => ({ value: String(v), checked: false, querySelector: () => null,
                       appendChild() {} });
  Object.assign(ns.__el, Object.fromEntries(EL_BAG.map((k) => [k, mk(1)])));
  ns.__el.gridYInvert = { checked: false };
  ns.__el.gridCols = mk(13); ns.__el.gridRows = mk(13);
  ns.__el.physChipX = mk(7); ns.__el.physChipY = mk(7); ns.__el.physEdgeMargin = mk(3);
  ns.__el.physWaferDia = { value: '300', querySelector: () => ({}), appendChild() {} };
  ns.__el.gridCanvas = { getBoundingClientRect: () => ({ width: 700, height: 700 }) };
  ns.__set.currentRotation(0); ns.__set.currentSide('front'); ns.__set.gridData({});
  // 🔴 THE ANSWER TO 2-b: a real module function, not a slice of one, produces a value.
  const frame = ns.__fn.currentFrame();
  ok('a real module function returns a frame', frame && frame.cols > 0,
    JSON.stringify(frame).slice(0, 60));
  // The heaviest of the sliced set. If anything needed a DOM this is where it would.
  let ran = true;
  try { ns.__fn.applyPhysicalGeometry(); } catch (e) { ran = String(e.message); }
  eq('the heaviest one runs with no DOM at all', ran, true);
}

// ═══ ② 🔴 퇴화 방지 — 사본이 원본으로 «시작»하지 않으면 던진다 ═══════════════════════════
//
// 이 단언이 이 파일의 «존재 이유»입니다. 「그 import 하나만 빼면 되잖아」가 덧붙이기를
// 잘라쓰기로 되돌리는 방법이고, 그 되돌림은 조용합니다.
console.log('\n[2] it refuses to become slicing again');
{
  eq('appending keeps the prefix', startsWithOriginal('abc', 'abc\nexport const x = 1;'), true);
  eq('removing anything breaks it', startsWithOriginal('abc', 'bc\nexport const x = 1;'), false);
  eq('a middle edit breaks it too', startsWithOriginal('abc', 'axc\nexport const x = 1;'), false);
  eq('an empty copy is not a prefix of a real original', startsWithOriginal('abc', ''), false);
  // The helper must not accept a non-string and call it a match.
  eq('a missing copy is not a match', startsWithOriginal('abc', null), false);
}

// ═══ ③ 흔적을 남기지 않는다 ═══════════════════════════════════════════════════════════
//
// ⚠️ 사본은 상대 import 가 풀려야 해서 «원본 옆»에 놓입니다. 그래서 지우는 것이 규율입니다 —
//    남으면 추적 안 되는 파일이 `src/` 에 서고, 다음 사람의 git status 에 «남의 것»처럼 보입니다.
console.log('\n[3] it leaves nothing behind');
{
  const strays = readdirSync(SRC_DIR).filter((f) => f.startsWith('.appended-'));
  eq('no appended copy survives the import', strays, []);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
