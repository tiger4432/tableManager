// A node resolve/load hook that answers `.css` imports with an EMPTY MODULE.
//
// 🔴 WHY THIS EXISTS (C-56). `ontology_explorer.js` opens with `import './ontology_explorer.css'`,
//    so node cannot import it and NO HARNESS COULD SEE THAT FILE. That is exactly where a
//    `loadCensus is not defined` reached production: the call site survived a removal, every
//    gated harness stayed green, and the defect was found by opening the screen.
//
// ⚠️ THE SUBJECT IS NOT MODIFIED. This is not slicing and not a stubbed copy — the module is
//    imported byte-for-byte as it ships; only the CSS specifier resolves to nothing, which is
//    what the bundler does with it anyway. The alternative (a copy with the import deleted)
//    would be a harness measuring a file that does not exist.
export async function resolve(specifier, context, next) {
  if (specifier.endsWith('.css')) {
    return { url: 'data:text/javascript,', shortCircuit: true };
  }
  return next(specifier, context);
}
