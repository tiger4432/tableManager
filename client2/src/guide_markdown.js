/**
 * The Help panel's Guide body (owner 11-06): a guide section's markdown read into blocks, then drawn with text nodes
 * only (no innerHTML). Read and draw are apart so the read is measured on the real guides without a browser.
 *
 *   blocks   p · h (# to ####) · pre (a fence, indented or not) · quote (blocks) · list (items of blocks, nested
 *            by indent, ordered from its number) · table (head, rows) · hr · unknown
 *   inline   text · code · b (inline) · em · a (http(s) only - a repo path stays its text)
 *   unknown  a line no block reads (an html tag, an image, a footnote, a deeper heading, a table row with no header)
 *            - drawn as its letters, and counted: the guides should hold none
 */

const FENCE = /^(\s*)```/;
const HEADING = /^(#{1,4})\s+(.*)$/;
const RULE = /^(---|\*\*\*|___)\s*$/;
const MARKER = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const TABLE_RULE = /^\|?[\s:|-]+\|?\s*$/;
const UNKNOWN = /^\s*(<[a-zA-Z/]|!\[|\[\^|#{5,}\s)/;
const COMMENT = /^\s*<!--/;

const indentOf = (line) => line.length - line.trimStart().length;
const dedent = (line, n) => line.slice(Math.min(n, indentOf(line)));

function cellsOf(row) {
  const cells = [];
  let cur = '';
  let code = false;
  const s = row.trim().replace(/^\|/, '').replace(/\|$/, '');
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === '\\' && s[i + 1] === '|') { cur += '|'; i++; continue; }
    if (ch === '`') code = !code;
    if (ch === '|' && !code) { cells.push(cur.trim()); cur = ''; continue; }
    cur += ch;
  }
  cells.push(cur.trim());
  return cells.map(inline);
}

const startsBlock = (line, next) => FENCE.test(line) || HEADING.test(line) || RULE.test(line) || /^\s*>/.test(line)
  || MARKER.test(line) || COMMENT.test(line) || UNKNOWN.test(line)
  || (line.trimStart().startsWith('|') && next !== undefined && TABLE_RULE.test(next) && next.includes('-'));

/** The blocks of `text`. */
export function readMarkdown(text) {
  return blocksOf(String(text || '').replace(/\r\n?/g, '\n').split('\n'));
}

function blocksOf(lines) {
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (COMMENT.test(line)) {
      while (i < lines.length && !lines[i].includes('-->')) i++;
      i++;
      continue;
    }
    const fence = FENCE.exec(line);
    if (fence) {
      const n = fence[1].length;
      const body = [];
      i++;
      while (i < lines.length && !FENCE.test(lines[i])) body.push(dedent(lines[i++], n));
      i++;
      out.push({ t: 'pre', text: body.join('\n') });
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) { out.push({ t: 'h', level: heading[1].length, inl: inline(heading[2].trim()) }); i++; continue; }
    if (RULE.test(line)) { out.push({ t: 'hr' }); i++; continue; }
    if (/^\s*>/.test(line)) {
      const body = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ''));
      out.push({ t: 'quote', blocks: blocksOf(body) });
      continue;
    }
    if (line.trimStart().startsWith('|')) {
      const next = lines[i + 1];
      if (next !== undefined && TABLE_RULE.test(next) && next.includes('-')) {
        const head = cellsOf(line);
        const rows = [];
        i += 2;
        while (i < lines.length && lines[i].trimStart().startsWith('|')) rows.push(cellsOf(lines[i++]));
        out.push({ t: 'table', head, rows });
        continue;
      }
      out.push({ t: 'unknown', text: line });
      i++;
      continue;
    }
    if (UNKNOWN.test(line)) { out.push({ t: 'unknown', text: line }); i++; continue; }
    const marker = MARKER.exec(line);
    if (marker) {
      const [list, end] = listAt(lines, i);
      out.push(list);
      i = end;
      continue;
    }
    const para = [line.trim()];
    i++;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines[i], lines[i + 1])) para.push(lines[i++].trim());
    out.push({ t: 'p', inl: inline(para.join(' ')) });
  }
  return out;
}

/** The list that starts at `lines[i]` and the index after it - an item holds the lines indented under it. */
function listAt(lines, i) {
  const first = MARKER.exec(lines[i]);
  const base = first[1].length;
  const ordered = /\d/.test(first[2]);
  const list = { t: 'list', ordered, start: ordered ? parseInt(first[2], 10) : 1, items: [] };
  while (i < lines.length) {
    const m = MARKER.exec(lines[i]);
    if (!m || m[1].length !== base || /\d/.test(m[2]) !== ordered) break;
    const content = m[0].length - m[3].length;
    const body = [m[3]];
    i++;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) {
        const next = lines.slice(i + 1).find((l) => l.trim());
        if (next === undefined || indentOf(next) <= base) break;
        body.push('');
        i++;
        continue;
      }
      if (indentOf(line) > base) { body.push(dedent(line, content)); i++; continue; }
      if (MARKER.test(line) || startsBlock(line, lines[i + 1])) break;
      body.push(line.trim());            // a lazy line: the item's paragraph goes on
      i++;
    }
    list.items.push(blocksOf(body));
  }
  return [list, i];
}

/** The inline runs of one line of text. */
export function inline(s) {
  const out = [];
  let text = '';
  const flush = () => { if (text) out.push({ t: 'text', s: text }); text = ''; };
  for (let i = 0; i < s.length;) {
    const ch = s[i];
    if (ch === '\\' && i + 1 < s.length && /[\\`*_[\]()|#>-]/.test(s[i + 1])) { text += s[i + 1]; i += 2; continue; }
    if (ch === '`') {
      const end = s.indexOf('`', i + 1);
      if (end > i) { flush(); out.push({ t: 'code', s: s.slice(i + 1, end) }); i = end + 1; continue; }
    }
    if (s.startsWith('**', i)) {
      const end = s.indexOf('**', i + 2);
      if (end > i + 2) { flush(); out.push({ t: 'b', inl: inline(s.slice(i + 2, end)) }); i = end + 2; continue; }
    }
    if (ch === '*' && s[i + 1] && s[i + 1] !== ' ' && s[i + 1] !== '*') {
      const end = s.indexOf('*', i + 1);
      if (end > i + 1 && s[end - 1] !== ' ') { flush(); out.push({ t: 'em', s: s.slice(i + 1, end) }); i = end + 1; continue; }
    }
    if (ch === '[') {
      const close = s.indexOf('](', i + 1);
      const end = close > i ? s.indexOf(')', close + 2) : -1;
      if (close > i && end > close) {
        flush();
        out.push({ t: 'a', s: s.slice(i + 1, close), href: s.slice(close + 2, end) });
        i = end + 1;
        continue;
      }
    }
    text += ch;
    i++;
  }
  flush();
  return out;
}

/** Every text run of `blocks` in drawing order - Find counts in these, and draws its marks in the same ones. */
export function runsOf(blocks, out = []) {
  const ofInline = (inl) => inl.forEach((r) => (r.t === 'b' ? ofInline(r.inl) : out.push(r.s)));
  for (const b of blocks) {
    if (b.t === 'p' || b.t === 'h') ofInline(b.inl);
    else if (b.t === 'pre' || b.t === 'unknown') out.push(b.text);
    else if (b.t === 'quote') runsOf(b.blocks, out);
    else if (b.t === 'list') b.items.forEach((item) => runsOf(item, out));
    else if (b.t === 'table') [b.head, ...b.rows].forEach((row) => row.forEach(ofInline));
  }
  return out;
}

/** The lines no block read, under `blocks`. */
export function unknownOf(blocks, out = []) {
  for (const b of blocks) {
    if (b.t === 'unknown') out.push(b.text);
    else if (b.t === 'quote') unknownOf(b.blocks, out);
    else if (b.t === 'list') b.items.forEach((item) => unknownOf(item, out));
  }
  return out;
}

/** Hits of `find` (case folded) in one run: [start, end] pairs. */
export function hitsIn(run, find) {
  const out = [];
  if (!find) return out;
  const hay = run.toLowerCase();
  const needle = find.toLowerCase();
  for (let at = hay.indexOf(needle); at >= 0; at = hay.indexOf(needle, at + needle.length)) {
    out.push([at, at + needle.length]);
  }
  return out;
}

/**
 * Draws `blocks` into a fragment. `mark(text)` returns the nodes for one text run (Find's marks); by default the
 * text itself.
 */
export function drawBlocks(doc, blocks, mark = (text) => [doc.createTextNode(text)]) {
  const frag = doc.createDocumentFragment();
  const el = (tag, cls) => { const e = doc.createElement(tag); if (cls) e.className = cls; return e; };
  const put = (parent, nodes) => nodes.forEach((n) => parent.appendChild(n));
  const drawInline = (parent, inl) => inl.forEach((r) => {
    if (r.t === 'text') put(parent, mark(r.s));
    else if (r.t === 'code') { const c = el('code', 'gmd-code'); put(c, mark(r.s)); parent.appendChild(c); }
    else if (r.t === 'b') { const b = el('strong'); drawInline(b, r.inl); parent.appendChild(b); }
    else if (r.t === 'em') { const e = el('em'); put(e, mark(r.s)); parent.appendChild(e); }
    else if (r.t === 'a') {
      if (/^https?:\/\//.test(r.href)) {
        const a = el('a');
        a.href = r.href;
        a.target = '_blank';
        a.rel = 'noopener';
        put(a, mark(r.s));
        parent.appendChild(a);
      } else {
        put(parent, mark(r.s));
      }
    }
  });
  const draw = (parent, list) => list.forEach((b) => {
    if (b.t === 'p') { const p = el('p', 'gmd-p'); drawInline(p, b.inl); parent.appendChild(p); }
    else if (b.t === 'h') { const h = el('div', `gmd-h gmd-h${b.level}`); drawInline(h, b.inl); parent.appendChild(h); }
    else if (b.t === 'pre') { const pre = el('pre', 'gmd-pre'); put(pre, mark(b.text)); parent.appendChild(pre); }
    else if (b.t === 'unknown') { const p = el('p', 'gmd-p'); put(p, mark(b.text)); parent.appendChild(p); }
    else if (b.t === 'hr') parent.appendChild(el('hr', 'gmd-hr'));
    else if (b.t === 'quote') { const q = el('blockquote', 'gmd-quote'); draw(q, b.blocks); parent.appendChild(q); }
    else if (b.t === 'list') {
      const l = el(b.ordered ? 'ol' : 'ul', 'gmd-list');
      if (b.ordered && b.start !== 1) l.start = b.start;
      b.items.forEach((item) => { const li = el('li'); draw(li, item); l.appendChild(li); });
      parent.appendChild(l);
    } else if (b.t === 'table') {
      const box = el('div', 'gmd-table');
      const table = el('table');
      const head = el('thead');
      const tr = el('tr');
      b.head.forEach((c) => { const th = el('th'); drawInline(th, c); tr.appendChild(th); });
      head.appendChild(tr);
      table.appendChild(head);
      const body = el('tbody');
      b.rows.forEach((row) => {
        const r = el('tr');
        row.forEach((c) => { const td = el('td'); drawInline(td, c); r.appendChild(td); });
        body.appendChild(r);
      });
      table.appendChild(body);
      box.appendChild(table);
      parent.appendChild(box);
    }
  });
  draw(frag, blocks);
  return frag;
}
