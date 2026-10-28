// Loaded with --import into a harness that has a SCANS cell (harness_floors.mjs): every folder the harness's own code
// (client2/tests, its lib) lists goes to the file SCAN_WATCH_OUT names, one per line, «\t**» after a recursive listing.
// A listing a package makes (vite reading its own tree) is not the harness naming a folder and is not recorded.
// The runner holds the record against the cell. Observation only: a failure here costs the record, never the harness.
import fs from 'node:fs';
import path from 'node:path';
import { syncBuiltinESMExports } from 'node:module';
import { fileURLToPath } from 'node:url';

const out = process.env.SCAN_WATCH_OUT;
const SELF = fileURLToPath(import.meta.url);
const TESTS = path.resolve(path.dirname(SELF), '..', 'tests') + path.sep;
const FRAME = /\(?((?:file:\/\/\/|[A-Za-z]:[\\/])[^()]+?):\d+:\d+\)?$/;
const callerFile = () => {
  for (const line of String(new Error().stack).split('\n').slice(1)) {
    const m = line.trim().match(FRAME);
    if (!m) continue;
    const f = m[1].startsWith('file:') ? fileURLToPath(m[1]) : m[1];
    if (f !== SELF) return f;
  }
  return '';
};
if (out) {
  const append = fs.appendFileSync;
  const note = (dir, options) => {
    try {
      if (!callerFile().startsWith(TESTS)) return;
      const p = dir instanceof URL ? fileURLToPath(dir) : String(dir);
      append(out, `${path.resolve(p)}${options && options.recursive ? '\t**' : ''}\n`);
    } catch (err) {
      try { process.stderr.write(`scan_watch: a listing went unrecorded (${err.message})\n`); } catch { /* nothing left to say it with */ }
    }
  };
  const wrap = (owner, key) => {
    const real = owner[key];
    if (typeof real !== 'function') return;
    owner[key] = function listed(dir, options, ...rest) { note(dir, options); return real.call(this, dir, options, ...rest); };
  };
  wrap(fs, 'readdirSync');
  wrap(fs, 'readdir');
  wrap(fs.promises, 'readdir');
  syncBuiltinESMExports();
}
