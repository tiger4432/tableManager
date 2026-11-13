// The screen checker's «is this the pressed button's panel» (lead 11-13 ㄱ3). The subject is imported
// (lib/screens_panel.mjs - the checker hands the same function into the page).
//
//   overlay  an AG Grid overlay floating new after a press is the grid redrawing, not a panel
//   panel    a real popover is a panel wherever it sits - its place is the panel rule's own finding
//   page     the function's text, as the checker sends it, answers the same
//
// Run: node client2/tests/screens_panel_harness.mjs
import { opensAsPanel } from './lib/screens_panel.mjs';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}

// as the 11-13 probe found them: the overlay's root and its no-rows / loading wrappers, the grid's width
const NO_ROWS = { classes: ['ag-overlay-wrapper', 'ag-overlay-no-rows-wrapper'], width: 1500, height: 600 };
const LOADING = { classes: ['ag-overlay-wrapper', 'ag-overlay-loading-wrapper'], width: 1500, height: 600 };
const ROOT = { classes: ['ag-overlay'], width: 1500, height: 600 };
const POPOVER = { classes: ['more-panel'], width: 220, height: 160 };
const FAR = { classes: ['more-panel'], width: 220, height: 160, below: 76 };

eq('P1 a no-rows overlay is not a panel', opensAsPanel(NO_ROWS), false);
eq('P2 a loading overlay is not a panel', opensAsPanel(LOADING), false);
eq('P3 the overlay root is not a panel', opensAsPanel(ROOT), false);
eq('P4 a popover under its button is a panel', opensAsPanel(POPOVER), true);
eq('P5 a popover 76 px below is still a panel (the panel rule finds its place)', opensAsPanel(FAR), true);
const inPage = new Function(`return (${opensAsPanel});`)();
eq('P6 its text, as the checker sends it into the page, answers the same',
  [NO_ROWS, LOADING, ROOT, POPOVER, FAR].map(inPage), [false, false, false, true, true]);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
