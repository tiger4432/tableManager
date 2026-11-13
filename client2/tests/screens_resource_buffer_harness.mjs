// The screen checker's page-start script that keeps every request's timing entry (lead 11-13 ㄱ). The subject is imported
// (lib/screens_resource_buffer.mjs - the checker adds its text to every page).
//
//   size    the buffer is set once to RESOURCE_BUFFER, above the most entries a page held in a run
//   page    the text, run where performance has no such call, throws nothing
//
// Run: node client2/tests/screens_resource_buffer_harness.mjs
import { RESOURCE_BUFFER, resourceBufferSource } from './lib/screens_resource_buffer.mjs';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}

// the most entries one page held, 11-13 tab branch run (RESOURCEMAX over six sizes): 323
const MOST_MEASURED = 323;

const calls = [];
new Function('performance', resourceBufferSource())({ setResourceTimingBufferSize: (n) => calls.push(n) });
eq('B1 the page-start text sets the buffer once, to RESOURCE_BUFFER', calls, [RESOURCE_BUFFER]);
eq('B2 RESOURCE_BUFFER is past the most a page held, ten times over', RESOURCE_BUFFER >= MOST_MEASURED * 10, true);
eq('B3 the browser default (250) is below the most a page held - the reason for B1', 250 < MOST_MEASURED, true);
let threw = false;
try { new Function('performance', resourceBufferSource())({}); } catch (e) { threw = true; }
eq('B4 where performance has no such call, the page-start text throws nothing', threw, false);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
