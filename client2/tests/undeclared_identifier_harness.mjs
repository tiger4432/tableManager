// UNDECLARED-IDENTIFIER SMOKE CHECK over client2/src/map_editor.js.
//
// WHY. Every other harness in this directory slices functions out of the source TEXT by
// name, so a renamed declaration with a stale call site is structurally invisible to all of
// them: the sliced body still parses, the sandbox provides what the slicer asked for, and
// the stale name only explodes at runtime in the browser. That is the validDieListCache
// incident -- an undeclared global survived to HEAD and into the minified bundle. This check
// closes exactly that class WITHOUT executing anything: it parses the whole file (the same
// oxc parser the bundler uses, via `rolldown/parseAst` -- zero new dependencies) and
// requires that every identifier referenced anywhere is declared somewhere in the file,
// imported, or a known platform global.
//
// WHAT IT IS NOT. It is a file-level union check, not a scope checker: a name declared in
// one function and (wrongly) used in another passes here and is left to the runtime
// harnesses. That under-approximation is deliberate -- it keeps false positives at zero,
// which is what lets this gate BLOCK instead of warn.
//
// SELF-VACUITY CONTROLS. A scanner that visits nothing reports zero undeclared and looks
// green, so every run also (a) checks the walker saw a plausible number of declarations and
// references, and (b) scores one injected mutant (a stale reference inside a function body
// MUST be flagged) and one control (a properly declared local MUST NOT be).
//
// Usage: node undeclared_identifier_harness.mjs [path-to-source]   (default: the live src)
// Exit: 0 green | 1 a check failed | 2 harness failure (nothing was checked).

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_PATH = process.argv[2] || path.join(HERE, '..', 'src', 'map_editor.js');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was checked.)`); process.exit(2); };

let parseAst;
try { ({ parseAst } = await import('rolldown/parseAst')); }
catch (e) { die(`rolldown/parseAst did not load -- ${e && e.message}`); }

let SRC;
try { SRC = readFileSync(SRC_PATH, 'utf8'); }
catch (e) { die(`cannot read ${SRC_PATH} -- ${e && e.message}`); }

// Platform globals a browser module may reference bare. JS builtins + DOM/BOM. Anything the
// scan flags that belongs here is a one-line allowlist addition -- anything else is a bug.
const GLOBALS = new Set(('Object Function Boolean Symbol Number BigInt Math Date String RegExp Array '
  + 'Int8Array Uint8Array Uint8ClampedArray Int16Array Uint16Array Int32Array Uint32Array '
  + 'Float32Array Float64Array BigInt64Array BigUint64Array Map Set WeakMap WeakSet WeakRef '
  + 'FinalizationRegistry ArrayBuffer SharedArrayBuffer DataView JSON Promise Reflect Proxy Intl '
  + 'Error AggregateError EvalError RangeError ReferenceError SyntaxError TypeError URIError '
  + 'globalThis undefined NaN Infinity arguments eval parseInt parseFloat isNaN isFinite '
  + 'decodeURI decodeURIComponent encodeURI encodeURIComponent structuredClone queueMicrotask '
  + 'setTimeout clearTimeout setInterval clearInterval console performance crypto atob btoa '
  + 'TextEncoder TextDecoder URL URLSearchParams AbortController AbortSignal Event EventTarget '
  + 'CustomEvent WebSocket Blob File FileReader FormData Headers Request Response fetch '
  + 'navigator location history localStorage sessionStorage document window alert confirm prompt '
  + 'getComputedStyle getSelection matchMedia requestAnimationFrame cancelAnimationFrame '
  + 'requestIdleCallback cancelIdleCallback devicePixelRatio innerWidth innerHeight '
  + 'addEventListener removeEventListener dispatchEvent MutationObserver ResizeObserver '
  + 'IntersectionObserver Image ImageData Path2D OffscreenCanvas DOMParser XMLSerializer '
  + 'Node Element HTMLElement HTMLInputElement HTMLCanvasElement CanvasRenderingContext2D '
  + 'KeyboardEvent MouseEvent PointerEvent WheelEvent DragEvent ClipboardEvent ClipboardItem '
  + 'DOMRect CSS scrollTo scrollBy open close').split(/\s+/));

function patternNames(node, out) {
  if (!node) return;
  switch (node.type) {
    case 'Identifier': out.add(node.name); break;
    case 'ObjectPattern':
      for (const p of node.properties) {
        if (p.type === 'RestElement') patternNames(p.argument, out);
        else patternNames(p.value, out);
      }
      break;
    case 'ArrayPattern': for (const e of node.elements) patternNames(e, out); break;
    case 'AssignmentPattern': patternNames(node.left, out); break;
    case 'RestElement': patternNames(node.argument, out); break;
  }
}

const STRUCT_KEYS = new Set(['type', 'loc', 'range', 'start', 'end']);

// One parse, two walks: (1) every name DECLARED anywhere in the file (any scope -- the
// deliberate under-approximation), (2) every identifier REFERENCED in value position.
// Identifiers that are not variables (member property names, object keys, labels, import
// aliases, new.target/import.meta) are excluded from (2); declaration sites are naturally
// harmless there because pass (1) already knows them.
function scan(src) {
  const ast = parseAst(src, { lang: 'js' });
  const declared = new Set();
  const refs = new Map();   // name -> offset of first reference

  (function decls(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { for (const n of node) decls(n); return; }
    if (typeof node.type !== 'string') return;
    switch (node.type) {
      case 'VariableDeclarator': patternNames(node.id, declared); break;
      case 'FunctionDeclaration': case 'FunctionExpression': case 'ArrowFunctionExpression':
        if (node.id) declared.add(node.id.name);
        for (const p of node.params) patternNames(p, declared);
        break;
      case 'ClassDeclaration': case 'ClassExpression':
        if (node.id) declared.add(node.id.name); break;
      case 'CatchClause': patternNames(node.param, declared); break;
      case 'ImportDefaultSpecifier': case 'ImportSpecifier': case 'ImportNamespaceSpecifier':
        declared.add(node.local.name); break;
    }
    for (const k of Object.keys(node)) { if (!STRUCT_KEYS.has(k)) decls(node[k]); }
  })(ast);

  (function uses(node, parent, key) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { for (const n of node) uses(n, parent, key); return; }
    if (typeof node.type !== 'string') return;
    if (node.type === 'MetaProperty') return;
    if (node.type === 'Identifier') {
      if (parent) {
        if (parent.type === 'MemberExpression' && key === 'property' && !parent.computed) return;
        if (parent.type === 'Property' && key === 'key' && !parent.computed) return;
        if ((parent.type === 'MethodDefinition' || parent.type === 'PropertyDefinition')
            && key === 'key' && !parent.computed) return;
        if (parent.type === 'LabeledStatement' || parent.type === 'BreakStatement'
            || parent.type === 'ContinueStatement') return;
        if (parent.type === 'ImportSpecifier' && key === 'imported') return;
        if (parent.type === 'ExportSpecifier' && key === 'exported') return;
      }
      if (!refs.has(node.name)) refs.set(node.name, node.start);
      return;
    }
    for (const k of Object.keys(node)) { if (!STRUCT_KEYS.has(k)) uses(node[k], node, k); }
  })(ast, null, null);

  const undeclared = [...refs.keys()].filter(n => !declared.has(n) && !GLOBALS.has(n)).sort();
  return { declared, refs, undeclared };
}

const lineOf = (src, pos) => src.slice(0, pos).split('\n').length;

let pass = 0; const failures = [];
const ok = (cond, name, detail) => {
  if (cond) { pass++; console.log(`  ok   ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? `\n       ${detail}` : ''}`); }
};

// 1. the real source parses and scans
let base = null, parseErr = null;
try { base = scan(SRC); } catch (e) { parseErr = e; }
ok(!!base, 'source parses under the bundler\'s own parser',
  parseErr && String(parseErr.message || parseErr));
if (!base) base = { declared: new Set(), refs: new Map(), undeclared: [] };

// 2./3. the walker measured something (a scan that visits nothing reports a green nothing)
ok(base.declared.size >= 500, `declaration walk saw a plausible population (${base.declared.size} >= 500)`);
ok(base.refs.size >= 500, `reference walk saw a plausible population (${base.refs.size} >= 500)`);

// 4. THE CHECK: every referenced identifier is declared, imported, or a platform global
ok(base.undeclared.length === 0,
  `no function body references an identifier declared nowhere (found ${base.undeclared.length})`,
  base.undeclared.map(n => `${n} (first ref at line ${lineOf(SRC, base.refs.get(n))})`).join(', '));

// 5. mutation control: a validDieListCache-shaped stale reference inside a function body
//    MUST be flagged -- otherwise assertion 4 is inert and proves nothing.
const MUT = '\nfunction __h2MutantControl() { return __h2StaleReference.size; }\n';
let mutFlags = [];
try { mutFlags = scan(SRC + MUT).undeclared; } catch (e) { mutFlags = []; }
ok(mutFlags.includes('__h2StaleReference'),
  'injected stale reference IS flagged (the detector is live)', `flagged: ${mutFlags.join(', ')}`);

// 6. negative control: a properly declared local of the same shape must NOT be flagged --
//    a scanner that flags everything would pass 5 while making 4 unshippable noise.
const CTL = '\nfunction __h2NegControl() { const __h2LocalName = 1; return __h2LocalName; }\n';
let ctlFlags = null;
try { ctlFlags = scan(SRC + CTL).undeclared; } catch (e) { ctlFlags = null; }
ok(ctlFlags !== null && ctlFlags.length === base.undeclared.length,
  'declared local is NOT flagged (no false positive from the controls)',
  ctlFlags === null ? 'control scan threw' : `flagged: ${ctlFlags.join(', ')}`);

console.log(`\n${failures.length ? 'FAIL' : 'PASS'} -- ${pass} passed, ${failures.length} failed`
  + `  (${path.basename(SRC_PATH)}: ${base.declared.size} declared, ${base.refs.size} referenced,`
  + ` ${base.undeclared.length} undeclared)`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length ? 1 : 0);
