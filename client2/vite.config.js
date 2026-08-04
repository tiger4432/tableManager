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
        enrichment: resolve(__dirname, 'enrichment.html'),
        graph: resolve(__dirname, 'graph.html'),
        trace: resolve(__dirname, 'trace.html')
      }
    }
  }
});
