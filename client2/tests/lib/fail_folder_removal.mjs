// Preloaded (node --import) by screen_layout_cleanup_harness: every removal of a 'screens-' temp folder throws EBUSY,
// as Windows does while a killed Chrome's children still hold its cache. Nothing is removed and nothing else changes.
import fs from 'node:fs';
import { syncBuiltinESMExports } from 'node:module';

const real = fs.rmSync;
fs.rmSync = (target, options) => {
  if (/[\\/]screens-/.test(String(target))) {
    const err = new Error(`EBUSY: resource busy or locked, rmdir '${target}'`);
    err.code = 'EBUSY';
    throw err;
  }
  return real(target, options);
};
syncBuiltinESMExports();
