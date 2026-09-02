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

export async function resolve(specifier, context, nextResolve) {
  const parent = context && context.parentURL ? context.parentURL : '';
  const tagged = COPY_RE.exec(parent);
  if (tagged) {
    const sib = SIBLING_RE.exec(specifier);
    if (sib) {
      const candidate = join(dirname(fileURLToPath(parent)),
        `${sib[1]}.__probe_stub__.${tagged[1]}.js`);
      // The stub exists only for specifiers this load actually declared stubs for. Everything
      // else falls through to the default resolution, unchanged.
      if (existsSync(candidate)) {
        return { url: pathToFileURL(candidate).href, shortCircuit: true };
      }
    }
  }
  return nextResolve(specifier, context);
}
