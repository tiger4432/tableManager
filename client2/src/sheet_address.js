// A sheet's cell addresses (owner 3b97fcfb9: an A1 grid) - letters for the column, a number for the row. One seat for the
// sheet kind's grid and the calculator's cell references.

export const ADDRESS = /^([A-Z]{1,3})([1-9][0-9]{0,6})$/;

/** A -> 1, Z -> 26, AA -> 27. */
export const column = (letters) => [...letters].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0);
/** 1 -> A, 27 -> AA. */
export const letters = (n) => (n > 0 ? letters(Math.floor((n - 1) / 26)) + String.fromCharCode(65 + ((n - 1) % 26)) : '');
/** 'B3' -> {c: 2, r: 3}; not an address - null. */
export const place = (at) => { const m = ADDRESS.exec(String(at || '')); return m ? { c: column(m[1]), r: Number(m[2]) } : null; };
export const address = (c, r) => `${letters(c)}${r}`;

/** A range's cells, a row at a time from its top left (B1:C2 -> B1 C1 B2 C2). */
export function rangeCells(from, to) {
  const a = place(from); const b = place(to);
  if (!a || !b) return [];
  const out = [];
  for (let r = Math.min(a.r, b.r); r <= Math.max(a.r, b.r); r += 1) {
    for (let c = Math.min(a.c, b.c); c <= Math.max(a.c, b.c); c += 1) out.push(address(c, r));
  }
  return out;
}
