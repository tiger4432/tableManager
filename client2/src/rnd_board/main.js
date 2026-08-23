// ═══════════════════════════════════════════════════════════════════════════════
// THE COMPOSITION ROOT of the R&D board. The ONLY file that knows a URL, a lot number, or
// where a panel sits.
//
// 🔴 THE SCREEN IS A LIST OF INSTANCE DECLARATIONS (below). Each entry names the part, its
//    seat, the marking it READS, the marking it WRITES, and its question. Adding a chart is
//    one entry; moving one when drag lands is a change to `at`. No part is edited either way.
//
// 🔴 THE DECLARATION IS DATA -- no functions in it -- so it can be serialised the day a
//    layout is saved or dragged. `bindLoaders` is what turns a question into a fetch, and it
//    lives HERE so no part ever holds a route.
//
// 🔴 TWO MAPS, TWO DIFFERENT MARKING NAMES. That is the round's acceptance standing on the
//    real screen: the same class, twice, reading and writing different names, not interfering.
//
// ⚠️ WHY BOTH ARE THE BOND AXIS AND NOT THE MOCKUP'S 본딩/코어 PAIR. Measured 2026-08-23:
//    `/api/ledger/lot_map?row=SYN-VOID-001&slot=07` returns `core` and `dt` as
//    `state:"no_frame", reason:"frame_ambiguous_across_slots"` -- a slot narrows rows in the
//    ROW axis's family only, so the core axis stays spread over 25 frames and there is no one
//    lattice to draw it on. Seating a core panel here would put a refusal sentence where the
//    mockup shows a wafer. Two bond maps of two different wafers are the same test of the
//    contract and they both DRAW.
// ═══════════════════════════════════════════════════════════════════════════════

// 🔴 THE STYLESHEET IS LINKED BY THE PAGE, AND `config.js` IS IMPORTED ONLY IN THE BROWSER
// BRANCH (at the bottom, dynamically). This module has to stay importable under bare node so
// the harness can drive the real composition root -- and `config.js` reads `window.location`
// and `import.meta.env` at module top level, so a static import of it would kill that.
// `API_BASE` still has exactly one definition; this file just does not ask for it until there
// is a document to ask on behalf of.
import { MarkingStore } from './marking_store.js';
import { GridShell } from './grid_shell.js';
import { MapPanel } from './map_panel.js';
import { HeadSummaryPanel } from './head_summary_panel.js';
import { CompositionPanel } from './composition_panel.js';
import { fetchLotMap } from './api.js';

/** part name -> class. The shell resolves a declaration through this and nothing else. */
export const PARTS = { map: MapPanel, headSummary: HeadSummaryPanel, composition: CompositionPanel };

/**
 * THE SCREEN. Round 1 seats the two maps; the remaining seven parts land beside them as
 * entries in this list.
 */
export const BOARD = Object.freeze({
  columns: 'minmax(0,1fr) minmax(0,1fr)',
  rows: 'minmax(0,1fr)',
  gap: '10px',
  panels: [
    {
      id: 'map-bond-a',
      part: 'map',
      title: '본딩 맵 · 슬롯 07',
      at: { column: 1, row: 1 },
      reads: 'marking:1',
      writes: 'marking:1',
      options: {
        axis: 'bond',
        question: { row: 'SYN-VOID-001', slot: '07', kind: 'void' },
      },
    },
    {
      id: 'map-bond-b',
      part: 'map',
      title: '본딩 맵 · 슬롯 03',
      at: { column: 2, row: 1 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        axis: 'bond',
        question: { row: 'SYN-VOID-001', slot: '03', kind: 'void' },
      },
    },
  ],
});

/**
 * Question -> `load`. The one seam between a declared screen and the network: replacing a
 * mocked answer with a real route is a change here, never in a part.
 */
export function bindLoaders(layout, deps) {
  const { apiBase, fetchImpl, dpr } = deps || {};
  return {
    ...layout,
    panels: (layout.panels || []).map((decl) => {
      const options = decl.options || {};
      if (!options.question) return decl;
      return {
        ...decl,
        options: {
          ...options,
          dpr: dpr || 1,
          load: () => fetchLotMap({ apiBase, fetchImpl, ...options.question }),
        },
      };
    }),
  };
}

/** Boot the board into `host`. Returns the shell, so a caller can reseat or tear down. */
export function boot(doc, host, deps) {
  const options = deps || {};
  const markings = options.markings || new MarkingStore();
  const shell = new GridShell(host, {
    doc,
    markings,
    parts: options.parts || PARTS,
    observeSize: options.observeSize,
  });
  shell.render(bindLoaders(options.layout || BOARD, {
    apiBase: options.apiBase || '',
    fetchImpl: options.fetchImpl,
    dpr: options.dpr || 1,
  }));
  return shell;
}

if (typeof document !== 'undefined') {
  const host = document.getElementById('rb-board');
  if (host) {
    import('../config.js').then(({ API_BASE }) => {
      boot(document, host, {
        apiBase: API_BASE,
        dpr: (typeof window !== 'undefined' && window.devicePixelRatio) || 1,
      });
    });
  }
}
