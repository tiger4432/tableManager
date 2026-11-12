// The save-to-file door - the CSV export's and the gallery zip's (lead 11-12): where the browser can write a picked file
// the answer streams into it; elsewhere (the desktop wrapper, a browser without showSaveFilePicker) it is held as a Blob
// and saved by its name.

/** The picker, or null where there is none: the desktop wrapper saves through its own download. */
export function savePicker({ isDesktop = false, win = globalThis.window } = {}) {
  return !isDesktop && win && typeof win.showSaveFilePicker === 'function' ? (options) => win.showSaveFilePicker(options) : null;
}

/** The file to write, asked while the press still counts - before the request: `{handle}`; `{cancelled: true}` for a
 *  closed dialog; `{handle: null}` with no picker, `failed` the error of a picker that threw. */
export async function pickFile(picker, options) {
  if (!picker) return { handle: null };
  try {
    return { handle: await picker(options) };
  } catch (err) {
    return err && err.name === 'AbortError' ? { cancelled: true } : { handle: null, failed: err };
  }
}

/** The answer's body saved: streamed into `handle` (closed at the end, aborted when a read or a write fails), or with
 *  none held and saved as `filename`. `onBytes(received)` after each chunk. Returns `{name, picked}`. */
export async function saveBody(res, { handle = null, filename, type, doc = globalThis.document, onBytes = () => {} }) {
  const reader = res.body.getReader();
  const writable = handle ? await handle.createWritable() : null;
  const chunks = [];
  let received = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (writable) await writable.write(value);
      else chunks.push(value);
      received += value.length;
      onBytes(received);
    }
  } catch (err) {
    if (writable) { try { await writable.abort(); } catch (e) { /* the read's or write's error is the one said */ } }
    throw err;
  }
  if (writable) {
    await writable.close();
    return { name: handle.name, picked: true };
  }
  const url = URL.createObjectURL(new Blob(chunks, { type }));
  const link = doc.createElement('a');
  link.href = url;
  link.download = filename;
  doc.body.appendChild(link);
  link.click();
  doc.body.removeChild(link);
  URL.revokeObjectURL(url);
  return { name: filename, picked: false };
}
