// THE MAIN GRID'S TABLE DROPDOWN, GROUPED BY THE OPERATOR'S `group` (lead 685f236d7, owner 10-02).
//
// 🔴 THE GROUP IS WRITTEN, NOT GUESSED. An operator writes `group` on a table in table_config and
//    `/tables` hands it over as `groups` ({table: group}; a table without one is absent). Nothing
//    here sorts a table into a group by its name or kind — a table nobody grouped goes under Other.
// ⚠️ An answer without `groups` (an older server), or one where no table is grouped, is today's
//    flat list — one section with no head.

export const OTHER_GROUP = 'Other';

/**
 * The dropdown's sections: `[{group, tables}]`, groups by name with Other last, each group's tables
 * in the server's order. `group` is null for the flat list.
 * A query keeps the tables whose name contains it (any case). The selected table always stays, so
 * the select can still show what is open. A group with no table left is not a section.
 */
export function tableMenu(tables, groups, query = '', selected = '') {
  const names = (Array.isArray(tables) ? tables : []).map(String);
  const of = groups && typeof groups === 'object' ? groups : {};
  const groupOf = (name) => (typeof of[name] === 'string' && of[name] ? of[name] : '');
  const q = String(query || '').trim().toLowerCase();
  const shown = names.filter((n) => n === selected || !q || n.toLowerCase().includes(q));
  if (!names.some(groupOf)) return shown.length ? [{ group: null, tables: shown }] : [];
  const by = new Map();
  for (const name of shown) {
    const g = groupOf(name) || OTHER_GROUP;
    if (!by.has(g)) by.set(g, []);
    by.get(g).push(name);
  }
  const order = [...by.keys()].filter((g) => g !== OTHER_GROUP).sort((a, b) => a.localeCompare(b));
  if (by.has(OTHER_GROUP)) order.push(OTHER_GROUP);
  return order.map((group) => ({ group, tables: by.get(group) }));
}

/** Draw the sections into a `<select>`: an `<optgroup>` per group, bare options for the flat list. */
export function fillTableSelect(select, sections, selected, doc = document) {
  select.innerHTML = '';
  for (const { group, tables } of sections) {
    const parent = group === null ? select : doc.createElement('optgroup');
    if (group !== null) {
      parent.label = group;
      select.appendChild(parent);
    }
    for (const name of tables) {
      const option = doc.createElement('option');
      option.value = name;
      option.textContent = name;
      parent.appendChild(option);
    }
  }
  if (selected) select.value = selected;
}
