import { defineConfig } from 'vite';
import { resolve } from 'path';
import os from 'os';

export default defineConfig({
  define: {
    'import.meta.env.VITE_USER': JSON.stringify(
      process.env.USERNAME || 
      process.env.USER || 
      (os.userInfo && os.userInfo().username) || 
      'web_client'
    )
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        admin: resolve(__dirname, 'admin.html'),
        map_editor: resolve(__dirname, 'map_editor.html'),
        // Map Editor 2 stands BESIDE the legacy editor, it does not replace it. The entry
        // above keeps shipping unchanged until the new screen can actually confirm a frame.
        map_editor2: resolve(__dirname, 'map_editor2.html'),
        // `enrichment` was here until 2026-08-11. The queue page was retired from navigation by
        // product-owner ruling (`5116f67` took its links; this takes the page), because
        // correction happens in the grid with the sidebar 참조뷰 beside it. Building an entry
        // nobody can reach is how a retired screen keeps looking shipped.
        graph: resolve(__dirname, 'graph.html'),
        trace: resolve(__dirname, 'trace.html'),
        // Ledger lineage (slice 1, layer 3). A SEPARATE entry from `trace` above:
        // that one is the G2 knowledge-graph report over `/graph/trace`, this one
        // is the canonical ledger walk over `/api/ledger/trace`. Two questions,
        // two answers, and folding them into one page would put a screen that
        // shows WHY a claim won behind a screen that shows what is connected.
        ledger: resolve(__dirname, 'ledger.html'),
        // Isolated R&D investigation entry. It does not replace ledger.html until
        // product-owner cutover approval; keeping both inputs makes rollback trivial.
        rnd_console: resolve(__dirname, 'rnd-console.html'),
        ledger_graph: resolve(__dirname, 'ledger-graph.html')
      }
    }
  }
});
