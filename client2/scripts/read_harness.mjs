// One harness run as check_harnesses reads it. Its output past the buffer is no verdict at all (lead 10-13):
// walk_table_harness's 1.6 MB against spawnSync's 1 MiB default read as «it used to assert and now measures nothing»
// while it ran 313/0.
import { spawnSync } from 'node:child_process';

export const RUN_BUFFER = 256 * 1048576;

/** The finished run, or null when the runner could not read it (spawnSync ENOBUFS). */
export function readHarness(file, args, cwd, maxBuffer = RUN_BUFFER) {
  const run = spawnSync(process.execPath, [file, ...args], { cwd, encoding: 'utf8', maxBuffer });
  if (run.error && run.error.code === 'ENOBUFS') return null;
  return run;
}
