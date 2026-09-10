/**
 * DECLARATION TOKENS — the client half lives in `client2/tests/frame_declaration_harness.mjs`,
 * and this file is the RUNNER that makes `check_contracts.mjs` count it.
 *
 *   node contracts/declaration_tokens/client_harness.mjs
 *
 * Exit codes: the harness's own — 0 = no divergence, 1 = divergence, 2 = it never ran (below).
 *
 * WHY IT EXISTS (C-69, 2026-09-10). `check_contracts.mjs` DISCOVERS contracts by looking for
 * this exact filename. This contract's client half is a top-level harness instead, so it was
 * gated — by a floor in `check_harnesses.mjs` — but never COUNTED: "is this contract gated"
 * and "does the contract gate count it" had different answers, and the second one is what
 * anybody sees when they ask how many contracts exist. Three contracts were in that state.
 *
 * ZERO COPIES. It imports the harness. It does not re-read the vectors, re-implement an
 * assertion or re-score anything — the harness owns all three, and a second scorer here would
 * be the same defect one level up.
 */
import '../../client2/tests/frame_declaration_harness.mjs';

// 🔴 UNREACHABLE, AND THAT IS THE CHECK. The harness calls `process.exit` itself, so control
//    never comes back. If it ever does, the harness stopped running on import (an entry guard,
//    an early return) and this file would otherwise hand the build a silent, meaningless 0.
console.error('frame_declaration_harness.mjs returned instead of exiting — it did not run itself. '
  + 'Run it directly to see why. Do NOT read this as a passing contract.');
process.exit(2);
