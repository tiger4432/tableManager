// PROBE MECHANISM — 잘라쓰기를 «대신하는» 기제가 실제로 그 일을 하는지.
//
// 🔴 이 하니스가 재는 것은 부품 하나가 아니라 이 저장소의 «규율»입니다: 대상 모듈을 잘라내지
//    «않고» 그 내부를 잴 수 있는가. 그리고 그 기제가 «조용히 잘라쓰기로 되돌아가지» 않는가.
//
// ═══ 🔴 이 파일의 내력 — 제가 «두 번째 경로»를 만들었습니다 (2026-09-06) ═══
// 오늘 저는 `tests/lib/appended_module.mjs` 라는 다리를 «새로» 지었습니다. 그런데 그 기제는
// «이미 있었습니다» — `tests/lib/probe.mjs`, 251줄, 소비자 «21». 덧붙이기도, 바이트 접두
// 단언도, 「변이가 안 먹으면 죽는다」도, 심지어 «의존 모듈 갈아끼우기»까지 전부 거기 있습니다.
// 제가 그것을 안 찾고 지은 것이라 기준 ④(같은 기능에 두 경로 없음) 위반이고, 제 헬퍼는
// 지웠습니다. 이 파일은 그 헬퍼가 아니라 «살아남은 정본»을 채점합니다.
//
// 🔵 그리고 이 자리가 «비어 있었습니다»: probe.mjs 를 21개가 쓰는데 그 «가드»를 재는 파일이
//    하나도 없었습니다. 그래서 이건 중복이 아니라 메우는 것입니다.
//
// ⚠️ 가드 둘은 `process.exit(2)` 로 죽습니다 — 그래서 그 둘만 «자식 프로세스»로 잽니다.
//    같은 프로세스에서는 잡을 방법이 없고, 「못 재니까 안 잰다」로 두면 그 가드가 사라지는 날
//    아무도 모릅니다.
//
// Run: node client2/tests/probe_mechanism_harness.mjs
import { loadWithProbe, MARK } from './lib/probe.mjs';
import { readdirSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}`); console.log(`        got  ${g}`); console.log(`        want ${w}`); }
}
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

const SRC_PATH = fileURLToPath(new URL('../src/map_editor.js', import.meta.url));
const SRC_DIR = dirname(SRC_PATH);
const HERE = dirname(fileURLToPath(import.meta.url));

// ═══ ① 잘라내지 «않고» 내부에 닿는다 ═══════════════════════════════════════════════════
//
// 🔴 대상이 우연이 아닙니다: `map_editor.js` 는 이 저장소에서 가장 많이 «잘려» 온 파일이고,
//    아무것도 export 하지 않아 밖에서 «잡을 이름»이 없습니다. 그것이 덧붙이기가 사는 이유입니다.
console.log('\n[1] the module is reached without cutting it');
{
  const { probe } = await loadWithProbe(SRC_PATH, {
    expose: ['VALID_DIE_TABLE', 'applyPhysicalGeometry'], tag: 'reach',
  });
  // 🔴 값을 «다시 적지» 않습니다 — 여기에 'valid_die_ref' 를 손으로 쓰면 그 순간 두 번째
  //    저자가 생기고, 선언이 바뀌는 날 이 하니스가 «옛 값»을 초록으로 지킵니다.
  ok('a module-level const is readable', typeof probe.VALID_DIE_TABLE === 'string'
    && probe.VALID_DIE_TABLE.length > 0, `saw ${JSON.stringify(probe.VALID_DIE_TABLE)}`);
  ok('...and a module-level function too', typeof probe.applyPhysicalGeometry === 'function');
}

// ═══ ② 잘라쓰기가 «닿던 것 전부»에 닿는다 ══════════════════════════════════════════════
//
// 🔴 목록을 «세어서» 씁니다. 46 을 손으로 적으면 그 하니스가 심볼을 하나 더할 때 이 수가
//    거짓이 됩니다.
const SLICED = (() => {
  const t = readFileSync(join(HERE, 'valid_die_frame_adoption_harness.mjs'), 'utf8');
  const blk = /const SYMBOLS = \[([\s\S]*?)\n\];/.exec(t)[1];
  return [...new Set([...blk.matchAll(/'([A-Za-z_$][\w$]*)'/g)].map((m) => m[1]))];
})();
const MODULE_LETS = ['activeOverlayLayers', 'boundingBoxCache', 'cellsSeatedUnder',
  'currentRotation', 'currentSide', 'gridCells2D', 'gridData', 'isBoxDragging', 'legend',
  'loadedIdentity', 'overlayLayers', 'selectedTable', 'tableSchema', 'validDie',
  'validDieResolveSeq'];

console.log('\n[2] it reaches everything the slicing reached');
{
  const { probe } = await loadWithProbe(SRC_PATH,
    { expose: SLICED, state: MODULE_LETS, tag: 'symbols' });
  const reached = SLICED.filter((n) => typeof probe[n] === 'function').length;
  eq('every sliced symbol is reachable without cutting', reached, SLICED.length);
  ok('...and there is more than a handful of them', SLICED.length > 40, `saw ${SLICED.length}`);
  // 🔴 THE ONE THAT MATTERS: writing a module `let` from outside, which ESM forbids and the
  //    appended accessor permits. Without this a harness could read but not drive.
  const before = probe.currentRotation;
  probe.currentRotation = before === 90 ? 180 : 90;
  ok('a module-level `let` can be DRIVEN from the test', probe.currentRotation !== before);
  eq('...and every binding it fakes has an accessor',
    MODULE_LETS.filter((n) => n in probe).length, MODULE_LETS.length);
}

// ═══ ③ 실제 함수가 «돈다» — DOM 없이 ═══════════════════════════════════════════════════
//
// ⚠️ 스텁 document 를 «안 놓습니다». 그래서 어떤 함수가 document 를 만지면 즉시 죽습니다 —
//    너그러운 스텁이 조용히 초록을 만들 여지가 «0» 입니다.
console.log('\n[3] the real functions run with no DOM at all');
{
  const { probe } = await loadWithProbe(SRC_PATH, {
    expose: ['el', 'applyPhysicalGeometry', 'currentFrame'],
    state: ['currentRotation', 'currentSide', 'gridData'], tag: 'run',
  });
  eq('the el bag is empty at import, which is why loading needs no DOM',
    Object.keys(probe.el).length, 0);
  eq('and the module never saw a document', typeof globalThis.document, 'undefined');
  const mk = (v) => ({ value: String(v), checked: false, querySelector: () => null,
                       appendChild() {} });
  for (const k of ['gridStartX', 'gridStartY', 'physOffsetX', 'physOffsetY']) probe.el[k] = mk(1);
  probe.el.gridYInvert = { checked: false };
  probe.el.gridCols = mk(13); probe.el.gridRows = mk(13);
  probe.el.physChipX = mk(7); probe.el.physChipY = mk(7); probe.el.physEdgeMargin = mk(3);
  probe.el.physWaferDia = { value: '300', querySelector: () => ({}), appendChild() {} };
  probe.el.gridCanvas = { getBoundingClientRect: () => ({ width: 700, height: 700 }) };
  probe.currentRotation = 0; probe.currentSide = 'front'; probe.gridData = {};
  const frame = probe.currentFrame();
  ok('a real module function returns a frame', frame && frame.cols > 0,
    JSON.stringify(frame).slice(0, 60));
  let ran = true;
  try { probe.applyPhysicalGeometry(); } catch (e) { ran = String(e.message); }
  eq('the heaviest one runs', ran, true);
}

// ═══ ④ 변이는 «먹어야» 한다 ════════════════════════════════════════════════════════════
console.log('\n[4] a mutant is a whole module, and it must actually differ');
{
  const { probe } = await loadWithProbe(SRC_PATH, {
    expose: ['VALID_DIE_TABLE'], tag: 'mutant',
    mutate: (src) => src.replace(/const VALID_DIE_TABLE = '[^']*'/,
      "const VALID_DIE_TABLE = 'MUTATED_TABLE'"),
  });
  eq('a mutated whole module loads and carries the mutation',
    probe.VALID_DIE_TABLE, 'MUTATED_TABLE');
}

// ═══ ⑤ 🔴 퇴화 방지 — 두 가드가 «죽는다». 자식 프로세스로 잽니다 ══════════════════════
//
// 이 둘이 이 파일의 «존재 이유»입니다. 「그 import 하나만 빼면 되잖아」가 덧붙이기를
// 잘라쓰기로 되돌리는 방법이고, 「앵커가 안 맞네」가 변이를 침묵시키는 방법입니다.
// 둘 다 «조용»합니다 — 가드가 없으면.
console.log('\n[5] it refuses to become slicing again, and refuses a no-op mutant');
function runsAndDies(body, label) {
  const f = join(HERE, `.probe_guard_${label}.mjs`);
  writeFileSync(f, body, 'utf8');
  try {
    execFileSync(process.execPath, [f], { stdio: 'pipe' });
    return { code: 0, err: '' };
  } catch (e) {
    return { code: e.status, err: String(e.stderr || '') };
  } finally { try { unlinkSync(f); } catch { /* gone */ } }
}
{
  // 자르는 변이 — 접두가 원본이 아니게 되는 것이 아니라, `mutate` 를 안 주고 «원본이 아닌»
  // 것을 밀어 넣을 수는 없으므로, 여기서는 「변이가 아무것도 안 바꿨다」를 잽니다.
  const noop = runsAndDies(
    "import { loadWithProbe } from './lib/probe.mjs';\n"
    + `await loadWithProbe(${JSON.stringify(SRC_PATH)}, `
    + "{ expose: ['VALID_DIE_TABLE'], mutate: (s) => s, tag: 'noop' });\n", 'noop');
  eq('a mutant that changed nothing exits 2, not 0', noop.code, 2);
  ok('...and says why', /did not mutate/.test(noop.err), noop.err.slice(0, 120));

  // 그리고 «대상이 이미» 그 이름을 들고 있으면 붙인 것이 그것을 가립니다 — 그때도 죽어야 합니다.
  //
  // ⚠️ 처음에 이걸 `mutate` 로 마크를 «덧붙여» 재려 했는데 «틀린 자리»였습니다: 그 검사는
  //    `mutate` «전»에 «원본 파일»을 봅니다. 그래서 그 판은 가드가 아니라 중복 선언이 만든
  //    SyntaxError 를 재고 있었고, 종료 코드가 2 가 아니라 «1» 이라 들켰습니다.
  //    가드를 재려면 마크를 «파일 안»에 들고 있는 대상이 있어야 합니다.
  const shadowSubject = join(SRC_DIR, '.probe_shadow_subject.js');
  writeFileSync(shadowSubject, `export const x = 1;\nconst ${MARK} = 1;\n`, 'utf8');
  const shadow = runsAndDies(
    "import { loadWithProbe } from './lib/probe.mjs';\n"
    + `await loadWithProbe(${JSON.stringify(shadowSubject)}, `
    + "{ expose: ['x'], tag: 'shadow' });\n", 'shadow');
  try { unlinkSync(shadowSubject); } catch { /* gone */ }
  eq('a subject that already carries the probe mark exits 2', shadow.code, 2);
  ok('...and names the collision', /already contains/.test(shadow.err), shadow.err.slice(0, 120));
}

// ═══ ⑥ 흔적을 남기지 않는다 ═══════════════════════════════════════════════════════════
//
// ⚠️ 사본은 상대 import 가 풀려야 해서 «원본 옆»에 놓입니다. 그래서 지우는 것이 규율입니다 —
//    남으면 추적 안 되는 파일이 `src/` 에 서고, 다음 사람의 git status 에 «남의 것»처럼 보입니다.
console.log('\n[6] it leaves nothing behind');
{
  const strays = readdirSync(SRC_DIR)
    .filter((f) => f.includes('__probe__') || f.includes('__probe_stub__'));
  eq('no probe copy survives the imports above', strays, []);
  const here = readdirSync(HERE).filter((f) => f.startsWith('.probe_guard_'));
  eq('and no guard script survives either', here, []);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
