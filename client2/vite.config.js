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
        enrichment: resolve(__dirname, 'enrichment.html'),
        graph: resolve(__dirname, 'graph.html'),
        trace: resolve(__dirname, 'trace.html')
      }
    }
  }
});
