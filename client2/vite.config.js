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
        // `ledger` was here until 2026-08-24, and `ledger_graph` below it. Both pages were
        // DELETED by owner ruling 「ㅇㅇ 버려」 -- not retired from navigation like
        // `enrichment` above, deleted, so there is no file left to name here. The lineage
        // question those two asked is answered by the R&D board`s walk (`rnd_board` below).
        // The assembled R&D diagnosis board (`src/rnd_board/`). A SEPARATE entry from
        // `ledger` (deleted 2026-08-24): that page was one walk, this one is a grid of parts that
        // share a marking store. It is an entry rather than a route on an existing page
        // because the parts are seated by a layout declaration, not by that page's markup.
        rnd_board: resolve(__dirname, 'rnd-board.html'),
        // 🔴 걷기 검색 — 휴대폰에서 걷기 API 를 «사람이 모는» 자리 (소유자 요청).
        //    부품은 R&D 보드의 `WalkBoxPanel` «그대로»이고 새 부품이 아닙니다.
        //    별도 엔트리인 이유: 그 보드는 «격자에 앉은 부품 여럿»이고 이건 «한 부품이
        //    화면을 통째로 쓰는» 페이지라, 같은 페이지의 라우트로는 배치가 안 됩니다.
        walk: resolve(__dirname, 'walk.html')
      }
    }
  }
});
