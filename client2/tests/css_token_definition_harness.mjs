// css_token_definition — 화면이 «부르는» 토큰은 «정의돼» 있다. (C-117 ㉰)
// Run: node client2/tests/css_token_definition_harness.mjs
//
// 🔴 이 라운드가 왜 있나. `admin.html` 이 `--bg` · `--text-primary` · `--text-secondary` 를
//    부르는데 그 셋은 이 저장소에 «정의가 없습니다». git 이력으로 확인했습니다 — «한 번도»
//    없었습니다. 지어진 이름입니다. 그리고 정의 없는 커스텀 속성은 «조용히» 틀립니다:
//
//      `fill` 의 무효  -> 상속이 아니라 «초기값» = 검정. 체인 그래프 노드 원이 검게 칠해졌습니다
//      `color` 의 무효 -> «상속». 값도 라벨도 muted 도 «전부 같은 색»이 됐고, 그래서
//                        `[data-tone="muted"]` 이 «무효»였습니다 — 「측정 안 함」이
//                        「측정된 값」과 «같은 픽셀»입니다(「같아 보이는 다섯 개의 0」 부류)
//
// 🔴 이 파일의 주어는 «텍스트»입니다. CSS 토큰은 텍스트 사실이라 그것이 주어이지 대리가
//    아닙니다(CLAUDE.md 의 그 판별식). 그리고 단언은 «성질»입니다: 목록을 세지 않고
//    「정의 없이 불리는 이름이 하나도 없다」를 잽니다 — 네 번째가 지어지는 날 빨개집니다.
//
// ⛔ 고친 방법이 「그 셋을 «정의»한다」가 아닌 이유: 캐논에 `--bg-surface` · `--text` ·
//    `--text-dim` 이 그 세 역할로 «이미» 있습니다. 새 이름을 정의하면 한 역할에 두 이름이
//    되고, 그건 토큰 층의 문 가르기입니다(기준 ④). 지시는 「토큰 셋 정의」였고, 정의하면
//    지시의 «목표»(구별되는 픽셀)는 되지만 «둘째 어휘»가 남습니다 — 그래서 참조를 옮겼습니다.
//
// ⚠️ 주석은 «안 봅니다». 주석이 옛 이름을 설명하면 그것까지 세게 되고, 그러면 빨강을 푸는
//    제일 쉬운 길이 «설명을 지우는 것»이 됩니다(그 함정은 이 저장소에서 한 번 겪었습니다).

import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLIENT = path.join(HERE, '..');
const ADMIN_HTML = path.join(CLIENT, 'admin.html');
const TOKENS = path.join(CLIENT, 'src', 'tokens.css');
// 🔴 `dist` 는 빌드 산출물이라 소스와 «같은 사실»을 두 번 세게 됩니다. `.tmp` 는 프로브의
//    사본 자리이고, 둘 다 세면 한 결함이 세 번 나와 수가 뜻을 잃습니다.
const SKIP = new Set(['dist', 'node_modules', '.tmp', '.git']);

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name, saw) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else {
    fail++; failedNames.push(name);
    if (!quiet) console.log(`  BAD  ${name}${saw === undefined ? '' : `  -- ${JSON.stringify(saw)}`}`);
  }
  return !!cond;
}

// 🔴 모집단은 «브라우저가 싣는 것»입니다 — 최상위 페이지들과 `src/`. `tests/` 와 `scripts/`
//    는 브라우저에 안 갑니다. 그리고 그것들을 넣으면 이 파일이 «자기 변이 앵커»를 세어
//    스스로 빨개집니다 — 첫 판에 그랬습니다. 진단기는 자기가 진단하는 것을 죽일 수 없고,
//    자기 자신을 «모집단»으로 삼는 것도 같은 부류입니다.
const sources = [];
const collect = (dir) => {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) collect(p);
    else if (/\.(css|html|js|mjs)$/.test(name)) sources.push(p);
  }
};
collect(path.join(CLIENT, 'src'));
for (const name of readdirSync(CLIENT)) {
  if (name.endsWith('.html')) sources.push(path.join(CLIENT, name));
}

/** 주석을 뺀 본문. 블록 주석과 `//` 줄 주석 둘 다 — 이유는 머리글에 있습니다. */
const live = (text) => text.replace(/\/\*[\s\S]*?\*\//g, ' ')
  .split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');

/**
 * 한 트리의 토큰 그래프. `overrides` 는 «파일 하나를 갈아 끼우는» 자리이고, 변이가
 * 그것으로 들어옵니다 — 디스크를 건드리지 않고 같은 함수를 돌립니다.
 */
function tokenGraph(overrides = {}) {
  const defined = new Set();
  const referenced = new Map();
  for (const file of sources) {
    const raw = Object.prototype.hasOwnProperty.call(overrides, file)
      ? overrides[file] : readFileSync(file, 'utf8');
    const text = live(raw);
    for (const m of text.matchAll(/(--[A-Za-z0-9_-]+)\s*:/g)) defined.add(m[1]);
    // 런타임에 심는 것도 «정의»입니다. 안 세면 그 토큰이 거짓 양성으로 올라옵니다.
    for (const m of text.matchAll(/setProperty\(\s*['"`](--[A-Za-z0-9_-]+)/g)) defined.add(m[1]);
    text.split('\n').forEach((line, i) => {
      for (const m of line.matchAll(/var\(\s*(--[A-Za-z0-9_-]+)\s*([,)])/g)) {
        // ⚠️ 대체값이 있으면 그건 «선언된 의도»입니다 — 없을 수 있다는 것을 저자가 적은 것이라
        //    결함이 아닙니다. 이걸 안 가르면 게이트가 정당한 코드를 빨갛게 만듭니다.
        if (m[2] === ',') continue;
        const where = `${path.relative(CLIENT, file)}:${i + 1}`;
        if (!referenced.has(m[1])) referenced.set(m[1], []);
        referenced.get(m[1]).push(where);
      }
    });
  }
  const missing = [...referenced.entries()].filter(([n]) => !defined.has(n));
  return { defined, referenced, missing };
}

/** 한 선택자가 «마지막으로» 정하는 속성값. CSS 는 뒤가 이기므로 마지막을 읽습니다. */
const declOf = (text, selector, prop) => {
  const body = live(text).split(selector).slice(1).join(selector);
  const hits = [...body.matchAll(new RegExp(`${prop}\\s*:\\s*([^;}]+)`, 'g'))];
  return hits.length ? hits[0][1].trim() : '';
};
/** tokens.css 의 두 블록(기본 = 밝은 쪽, `[data-theme="dark"]`)에서 그 토큰의 값. */
const tokenValues = (text, name) =>
  [...live(text).matchAll(new RegExp(`${name}\\s*:\\s*([^;]+);`, 'g'))].map((m) => m[1].trim());

function suite(overrides = {}) {
  const before = { pass, fail };
  const g = tokenGraph(overrides);
  const admin = Object.prototype.hasOwnProperty.call(overrides, ADMIN_HTML)
    ? overrides[ADMIN_HTML] : readFileSync(ADMIN_HTML, 'utf8');
  const tokens = Object.prototype.hasOwnProperty.call(overrides, TOKENS)
    ? overrides[TOKENS] : readFileSync(TOKENS, 'utf8');

  // ── ① 성질. 목록이 아니라 「하나도 없다」 ──────────────────────────────────────────
  ok(g.missing.length === 0,
     `T1 정의 없이 불리는 토큰이 «하나도» 없다 (본 수 ${g.missing.length})`,
     g.missing.map(([n, w]) => `${n} <- ${w.join(' ')}`));
  // ⚠️ 그리고 그 성질이 «공허하지 않다»는 것을 같이 답니다. 모집단이 0 이면 T1 은 언제나 참입니다.
  ok(g.referenced.size > 50 && g.defined.size > 50,
     `T2 그 성질의 모집단이 실재한다 (부름 ${g.referenced.size} · 정의 ${g.defined.size})`,
     [g.referenced.size, g.defined.size]);

  // ── ② 보고된 증상 둘을 «이름 대고» ──────────────────────────────────────────────
  const circleFill = declOf(admin, '.cg-node circle', 'fill');
  const fillToken = (/var\(\s*(--[A-Za-z0-9_-]+)/.exec(circleFill) || [])[1] || '';
  ok(Boolean(fillToken) && g.defined.has(fillToken),
     'T3 체인 그래프 노드 원의 fill 이 «정의된» 토큰이다 — 무효면 초기값(검정)이다', circleFill);

  const normal = declOf(admin, '.recorrection-line .rc-value', 'color');
  const muted = declOf(admin, '.recorrection-line[data-tone="muted"] .rc-value', 'color');
  const nToken = (/var\(\s*(--[A-Za-z0-9_-]+)/.exec(normal) || [])[1] || '';
  const mToken = (/var\(\s*(--[A-Za-z0-9_-]+)/.exec(muted) || [])[1] || '';
  ok(Boolean(nToken) && g.defined.has(nToken) && Boolean(mToken) && g.defined.has(mToken),
     'T4 「값」과 「측정 안 함」이 둘 다 «정의된» 토큰을 쓴다', [normal, muted]);
  // 🔴 여기가 이 라운드의 «진짜» 주장입니다. 정의돼 있어도 «같은 값»이면 두 상태가 같은 픽셀입니다.
  ok(nToken !== mToken, 'T5 그 둘이 «다른 토큰»이다', [nToken, mToken]);
  const nVals = tokenValues(tokens, nToken);
  const mVals = tokenValues(tokens, mToken);
  ok(nVals.length >= 2 && mVals.length >= 2,
     'T6 두 토큰 모두 «밝은 쪽과 어두운 쪽»에 값이 있다 — 한 테마에만 있으면 다른 테마에서 죽는다',
     [nVals.length, mVals.length]);
  // ⚠️ 테마마다 «각각» 다릅니다. 한 테마에서만 갈리면 다른 테마의 운영자는 못 봅니다.
  ok(nVals.length >= 2 && mVals.length >= 2
     && nVals.every((v, i) => v !== mVals[i]),
     'T7 ...그리고 «모든 테마»에서 그 둘의 값이 다르다', [nVals, mVals]);

  return { pass: pass - before.pass, fail: fail - before.fail };
}

// ── 채점 ──────────────────────────────────────────────────────────────────────────────
const ADMIN_TEXT = readFileSync(ADMIN_HTML, 'utf8');
const TOKENS_TEXT = readFileSync(TOKENS, 'utf8');
const swap = (text, from, to) => {
  if (!text.includes(from)) {
    console.error(`HARNESS FAILURE: mutation anchor stopped matching: ${JSON.stringify(from)}`);
    console.log('ASSERTIONS 0 1');
    process.exit(2);
  }
  return text.replace(from, to);
};

const DEFECTS = [
  ['M1 지어진 이름이 다시 들어온다 -> T1',
   () => ({ [ADMIN_HTML]: swap(ADMIN_TEXT, 'fill: var(--bg-surface);', 'fill: var(--bg);') })],
  ['M2 캐논이 토큰 하나를 잃는다 -> T1 (부르는 자리가 전부 고아가 된다)',
   () => ({ [TOKENS]: swap(TOKENS_TEXT, '  --text-dim: #5b6779;', '  --removed-dim: #5b6779;') })],
  ['M3 「측정 안 함」이 「값」과 «같은 토큰»을 쓴다 -> T5',
   () => ({ [ADMIN_HTML]: swap(ADMIN_TEXT,
     '.recorrection-line[data-tone="muted"] .rc-value { color: var(--text-dim); }',
     '.recorrection-line[data-tone="muted"] .rc-value { color: var(--text); }') })],
  ['M4 어두운 쪽에서만 둘이 같아진다 -> T7',
   () => ({ [TOKENS]: swap(TOKENS_TEXT, '  --text-dim: #8b99ae;', '  --text-dim: #e9edf4;') })],
  ['M5 원의 fill 이 토큰을 안 쓴다 -> T3',
   () => ({ [ADMIN_HTML]: swap(ADMIN_TEXT, 'fill: var(--bg-surface);', 'fill: none;') })],
];
const CONTROLS = [
  // 🔴 대체값은 «선언된 의도»입니다. 이것이 잡히면 게이트가 정당한 코드를 빨갛게 만듭니다.
  // ⚠️ 그 참조를 «원의 fill 자리»에 넣었다가 T3 에 잡혔습니다 — 그건 대조군이 잘못 놓인
  //    것이지 게이트가 틀린 것이 아닙니다(그 자리는 «정의된 토큰»을 대야 합니다). 규칙을
  //    하나 «더해서» 잽니다: 그 줄은 T1 말고 아무도 안 봅니다.
  ['대체값이 붙은 참조 (없어도 된다고 «적은» 것)',
   () => ({ [ADMIN_HTML]: swap(ADMIN_TEXT, '    .cg-optin { fill: var(--text-dim); font-size: 11px; }',
                               '    .cg-optin { fill: var(--text-dim); font-size: 11px; }\n'
                               + '    .cg-spare { color: var(--nowhere, #fff); }') })],
  // 🔴 주석이 옛 이름을 «설명»하는 것. 잡히면 빨강을 푸는 제일 쉬운 길이 「설명 지우기」가 됩니다.
  ['주석 안의 옛 이름',
   () => ({ [ADMIN_HTML]: swap(ADMIN_TEXT, '/* 🔴 C-117 ㉰. 여기 `var(--bg)` 가 있었고',
                               '/* 🔴 C-117 ㉰. 여기 `var(--bg)` · `var(--gone)` 가 있었고') })],
];

console.log('-- css_token_definition (C-117 ㉰) ---------------------------------');
const base = suite();

const caught = [], escaped = [];
let controlsCaught = 0;
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
for (const [name, make] of DEFECTS) {
  quiet = true;
  const delta = suite(make());
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, make] of CONTROLS) {
  quiet = true;
  const delta = suite(make());
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) controlsCaught += 1;
  console.log(`  ${delta.fail > 0 ? 'CAUGHT ' : 'escaped'} ${name}`);
}

const badScore = escaped.length > 0 || controlsCaught > 0;
console.log('');
console.log(`${base.pass} passed, ${base.fail} failed; ${caught.length}/${DEFECTS.length} defects `
  + `caught, ${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} `
  + 'controls escaped.');
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
if (base.fail) console.log('FAILED: ' + failedNames.slice(0, base.fail).join(' | '));
if (base.fail || badScore) process.exitCode = 1;
