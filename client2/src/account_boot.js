// Company SSO on every page (lead 2095014ee): each page's HTML loads this script BEFORE its own entry, so the login
// door wraps `fetch` before the page sends anything, and the account part takes the head bar's `#account-badge` seat.
import './account_badge.css';
import { installLoginGate } from './auth_gate.js';
import { AccountBadge } from './account_badge.js';
import { writeClipboardRich } from './clipboard_write.js';

installLoginGate(window);
const host = document.getElementById('account-badge');
if (host) {
  void new AccountBadge(host, {
    doc: document,
    fetch: (url, init) => window.fetch(url, init),
    reload: () => window.location.reload(),
    go: (url) => window.location.assign(url),
    // The copy event, not the browser's clipboard object: that one is missing on the plain-HTTP LAN (lead 10-09).
    clipboard: { writeText: (text) => writeClipboardRich('', text) },
  }).mount();
}
