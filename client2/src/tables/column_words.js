// A TABLE COLUMN'S ONTOLOGY WORD (owner 11-12 «온톨로지로 맵핑 · 같은 원자를 내면 표를 하나처럼 잇기», lead, D -
// contracts/column_words): the place a column fills, read off the declaration's sources[].columns. Two tables' columns
// with one word are ONE column when tables are stacked; the column's own name rides beside it. No DOM, no network.

const KIND_ORDER = { entity: 0, predicate: 1, table: 2 };
const bare = (name) => String(name ?? '').split('@')[0];
const byOfName = (a, b) => (a.of < b.of ? -1 : a.of > b.of ? 1 : a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
const wordKey = (w) => `${w.kind}\u0000${w.of}\u0000${w.name}`;

/** The word one bound row says, or null when it names no entity or predicate - an entity-type column and a key whose
 *  entity's type a column says carry neither, so they are the table's own. */
function wordOfRow(row) {
  if ((row.role === 'key' || row.role === 'attribute') && row.entity) return { kind: 'entity', of: bare(row.entity), name: row.name };
  if ((row.role === 'qualifier' || row.role === 'time') && row.predicate) return { kind: 'predicate', of: bare(row.predicate), name: row.name };
  return null;
}

/**
 * {column: [word]} for each of `columns` (the table's, in its order): entity words, then predicate words, each by
 * (of, name), one word once; a column binding no entity or predicate place - the table's own {kind: table, of: table,
 * name: column}.
 * @param {Array<{relation: string, columns?: object[]}>} sources  the declaration's sources[]
 */
export function columnWords(sources, table, columns) {
  const rows = (sources || []).filter((s) => s.relation === table).flatMap((s) => s.columns || []);
  return Object.fromEntries((columns || []).map((column) => {
    const seen = new Map();
    for (const row of rows) {
      if (row.column !== column) continue;
      const word = wordOfRow(row);
      if (word) seen.set(wordKey(word), word);
    }
    const words = [...seen.values()].sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || byOfName(a, b));
    return [column, words.length ? words : [{ kind: 'table', of: table, name: column }]];
  }));
}

/**
 * Tables stacked by their columns' words: a word one column - [{word, from: {table: [its columns with the word]}}] -
 * words by kind (entity, predicate, table) then (of, name); `from` by table name, each list in the table's column order.
 * A column of two words is in both.
 * @param {{[table: string]: {[column: string]: object[]}}} tables  each table's columnWords
 * @param {{[table: string]: string[]}} order  each table's columns, in its order
 */
export function stackColumns(tables, order) {
  const stacked = new Map();
  for (const table of Object.keys(tables).sort()) {
    const words = tables[table];
    for (const column of order[table] || Object.keys(words)) {
      for (const word of words[column] || []) {
        const key = wordKey(word);
        if (!stacked.has(key)) stacked.set(key, { word: { kind: word.kind, of: word.of, name: word.name }, from: {} });
        const from = stacked.get(key).from;
        (from[table] ||= []).push(column);
      }
    }
  }
  return [...stacked.values()].sort((a, b) => KIND_ORDER[a.word.kind] - KIND_ORDER[b.word.kind] || byOfName(a.word, b.word));
}
