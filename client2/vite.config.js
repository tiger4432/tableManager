import { defineConfig } from 'vite';
import os from 'os';

export default defineConfig({
  define: {
    'import.meta.env.VITE_USER': JSON.stringify(
      process.env.USERNAME || 
      process.env.USER || 
      (os.userInfo && os.userInfo().username) || 
      'web_client'
    )
  }
});
