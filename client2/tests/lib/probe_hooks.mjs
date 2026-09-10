// PROBE RESOLVE HOOK — redirect a dependency, and ONLY for a probe copy.
//
// A probe reaches what its own file declares. It cannot reach a name the subject got through
// `import`, because an ESM import binding is read-only to everyone but the module that
// declared it. Measured on map_editor.js: 15 of the 30 harnesses that slice it stub such a
// name -- `showToast` alone in 15 -- so without this they could call the function under test
// and never intercept what it reports.
//
// So the copy's dependency is redirected to a generated stub module. The subject is NOT
// touched: the byte-prefix assertion in probe.mjs still passes, and that passing assertion is
// the evidence this stayed honest.
//
// 🔴 THE SCOPE LIMIT IS THE WHOLE SAFETY ARGUMENT. The redirect fires only when the IMPORTER
// is a probe copy carrying the tag, so the same `./utils.js` imported anywhere else in the
// process -- including by the harness itself -- resolves to the real file. A hook without
// that check silently restubs the entire process.
//
// There is no message passing: the stub's path is DERIVED from the importer's tag, and the
// hook only asks whether that file exists. A hooks thread that had to be told about each load
// would need a port, a protocol, and an ordering guarantee; a filename needs none of them.
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// `map_editor.__probe__.ovprov3.js` -> tag `ovprov3`
const COPY_RE = /\.__probe__\.([A-Za-z0-9_]+)\.js$/;
// Only bare sibling specifiers. A package name or a deep path is never redirected.
const SIBLING_RE = /^\.\/([A-Za-z0-9_.-]+)\.js$/;

// `<client2>/.tmp/probe/<rel>` -> `<client2>/<rel>`. One marker, stripped. Both separators are
// accepted because a URL path arrives with `/` on every platform while `path.join` gives `\` on
// Windows, and a marker that only matched one of them would silently never fire.
const MIRROR_RE = /^(.*)[\\/]\.tmp[\\/]probe[\\/](.*)$/;
function originalDirOf(copyDir) {
  const m = MIRROR_RE.exec(copyDir);
  return m ? join(m[1], m[2]) : null;
}

// 🔴 A GENERATED STUB IS ALSO AN IMPORTER, and C-67 is what made that matter. Every stub begins
//    `export * from './x.js'` -- it delegates the names it does not intercept -- and while stubs
//    were written into `client2/src` that specifier happened to land on the real neighbour. In
//    the mirror it lands on nothing. So a stub's siblings resolve against the ORIGINAL directory
//    too; what a stub must never get is another stub, which would be a cycle through itself.
const STUB_RE = /\.__probe_stub__\.([A-Za-z0-9_]+)\.js$/;

export async function resolve(specifier, context, nextResolve) {
  const parent = context && context.parentURL ? context.parentURL : '';
  const tagged = COPY_RE.exec(parent);
  const fromStub = !tagged && STUB_RE.test(parent);
  if (fromStub) {
    const sib = SIBLING_RE.exec(specifier);
    if (sib) {
      const original = originalDirOf(dirname(fileURLToPath(parent)));
      if (original) {
        const real = join(original, `${sib[1]}.js`);
        if (existsSync(real)) return { url: pathToFileURL(real).href, shortCircuit: true };
      }
    }
    return nextResolve(specifier, context);
  }
  if (tagged) {
    const sib = SIBLING_RE.exec(specifier);
    if (sib) {
      const copyDir = dirname(fileURLToPath(parent));
      const candidate = join(copyDir, `${sib[1]}.__probe_stub__.${tagged[1]}.js`);
      // The stub exists only for specifiers this load actually declared stubs for. Everything
      // else falls through — but see below: the fall-through is no longer the default one.
      if (existsSync(candidate)) {
        return { url: pathToFileURL(candidate).href, shortCircuit: true };
      }
      // 🔴 C-67. THE COPY NO LONGER SITS BESIDE ITS SUBJECT, so a sibling specifier can no
      //    longer be left to the default resolution: `./x.js` next to the copy is now a place
      //    in `client2/.tmp/probe/…` where nothing lives. The subject's own directory is
      //    recovered from the mirror path -- one marker stripped -- which is why the mirror
      //    exists at all: these hooks run on another thread and cannot be TOLD anything, so the
      //    path has to carry the answer.
      // ⚠️ Still scoped to a probe copy as the importer, and still only for `./name.js`. The
      //    same specifier imported anywhere else in the process resolves normally.
      const original = originalDirOf(copyDir);
      if (original) {
        const real = join(original, `${sib[1]}.js`);
        if (existsSync(real)) {
          return { url: pathToFileURL(real).href, shortCircuit: true };
        }
      }
    }
  }
  return nextResolve(specifier, context);
}
