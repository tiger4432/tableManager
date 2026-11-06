// THE TABLES PAGE (owner 11-06, lead L1): source tables a person reads as tables. L1 is the first table only - opened from
// the grid with its narrowing (its «Tables» button, handoff.js) or by its address and a search. The page places the box;
// the box is its own part (table_box.js).
import '../tokens.css';
import '../base.css';
import '../spotfire.css';
import '../testbed/testbed.css';
import './tables.css';
import { API_BASE } from '../config.js';
import { handoffRead } from './handoff.js';
import { TableBox } from './table_box.js';

const doc = document;
const from = doc.getElementById('tables-from');
const mount = doc.getElementById('tables-board');
const picker = doc.getElementById('tables-table');

const asked = handoffRead(window.localStorage, window.location.search);

function openTable(table, narrowing = '', world = null) {
  const box = new TableBox(mount, { doc, fetch: (url, init) => window.fetch(url, init), apiBase: API_BASE, table, narrowing, world });
  return box.open();
}

async function start() {
  const res = await window.fetch(`${API_BASE}/tables`);
  const tables = res.ok ? ((await res.json()).tables || []) : [];
  picker.replaceChildren(...['', ...tables].map((t) => {
    const o = doc.createElement('option');
    o.value = t;
    o.textContent = t || 'Pick a table';
    return o;
  }));
  picker.addEventListener('change', () => {
    if (!picker.value) return;
    window.history.replaceState(null, '', `?table=${encodeURIComponent(picker.value)}`);
    from.hidden = true;
    openTable(picker.value);
  });
  if (asked.table && tables.includes(asked.table)) {
    picker.value = asked.table;
    from.hidden = !asked.handed;
    await openTable(asked.table, asked.narrowing, asked.world);
  }
}

start();
