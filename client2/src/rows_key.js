// The row a read of /tables/{t}/data goes on from (lead 11-13): the server reads a keyed page by its own rows however
// deep (main.py key_page, lead e570dcda5), where an OFFSET of 1.86 M rows sorted the table on disk (3.2 s alone, 20-30 s
// under load). Every reader that walks a table page by page - Next and Prev, the infinite view, Load All, a pivot
// group's rows before a delete, the Tables page - asks this one; skip goes beside it as the server's way back when
// that row is gone.

/** `rows`' last (`after`) or first (`before`) row as the server sent them -> `{after|before: row_id}`; none (a table
 *  without row_id, a pivot's key groups, no rows yet) - the read goes by skip. */
export function rowsKey(rows, side) {
  const row = side === 'after' ? rows[rows.length - 1] : rows[0];
  return row && row.row_id != null ? { [side]: row.row_id } : null;
}
