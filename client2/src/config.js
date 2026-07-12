const isDevServer = window.location.port === '5173';
export const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;
export const WS_URL = isDevServer ? 'ws://127.0.0.1:8080/ws' : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
export const CURRENT_USER = import.meta.env.VITE_USER || 'web_client';
export const pageLimit = 1000; // Chunk size
