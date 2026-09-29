// ═══════════════════════════════════════════════════════════════════════════════
// FILE INGESTION — retry the failed files under one folder (lead f0e668bb8, owner 09-29
// 「폴더 아래 선택해서 한꺼번에 필요」).
//
// The server picks the files and counts them (`retry-failed?folder=…&preview=true`); this part
// judges no path and counts nothing. The number on Retry is the preview's `count`, and Retry
// sends the folder that was previewed — change the folder and it is off until previewed again.
// ═══════════════════════════════════════════════════════════════════════════════
import { setDisabledReason } from './disabled_reason.js';
import { isFailedStatus } from './retry_verdict.js';

export const FOLDER_RETRY_WORDS = Object.freeze({
  label: 'Retry failed files under a folder',
  placeholder: 'Folder',
  preview: 'Preview',
  retry: 'Retry',
  needFolder: 'Type or pick a folder',
  previewFirst: 'Preview this folder first',
  running: 'Running',
});

/** Folders to suggest: every folder above a listed file, spelled as the list spells it. Only a
 *  suggestion — which files lie under a folder is the server's judgement. */
export function folderCandidates(paths) {
  const out = new Set();
  for (const p of paths || []) {
    const s = String(p || '');
    for (let i = 0; i < s.length; i++) {
      if (s[i] !== '/' && s[i] !== '\\') continue;
      const head = s.slice(0, i);
      if (/[\\/]/.test(head)) out.add(head);
    }
  }
  return [...out].sort();
}

export class FolderRetryPanel {
  /**
   * @param mount  the part's host; it owns one div inside it
   * @param deps   { doc, rows: () => the log rows the page lists, preview(folder), retry(folder), onRetried() }
   *   The suggestions are the FAILED rows' folders (lead a30c55a13 — 「실패 목록」).
   *   preview / retry resolve to { ok: true, body } or { ok: false, text } — the page reads
   *   the route and says its own refusal; this part draws what it is handed.
   */
  constructor(mount, deps = {}) {
    this.doc = deps.doc || (mount && mount.ownerDocument);
    this.rows = deps.rows || (() => []);
    this.preview = deps.preview;
    this.retry = deps.retry;
    this.onRetried = deps.onRetried || null;
    this.seen = null;    // the last preview answer: { folder, count, byFolder, message }
    this.busy = false;
    this.build(mount);
    this.refresh();
  }

  build(mount) {
    const doc = this.doc;
    const el = (tag, cls, text) => {
      const n = doc.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined) n.textContent = text;
      return n;
    };
    this.root = el('div', 'form-row folder-retry');
    const listId = `folder-retry-${Math.random().toString(36).slice(2, 8)}`;
    this.root.appendChild(el('label', 'form-label', FOLDER_RETRY_WORDS.label));
    const controls = el('div', 'folder-retry-controls');
    this.input = el('input', 'folder-retry-folder');
    this.input.setAttribute('placeholder', FOLDER_RETRY_WORDS.placeholder);
    this.input.setAttribute('aria-label', FOLDER_RETRY_WORDS.label);
    this.input.setAttribute('list', listId);
    this.list = el('datalist');
    this.list.setAttribute('id', listId);
    this.previewBtn = el('button', 'admin-btn folder-retry-preview', FOLDER_RETRY_WORDS.preview);
    this.retryBtn = el('button', 'admin-btn btn-primary folder-retry-run', FOLDER_RETRY_WORDS.retry);
    controls.append(this.input, this.list, this.previewBtn, this.retryBtn);
    this.said = el('div', 'folder-retry-said');
    this.said.hidden = true;
    this.byFolder = el('div', 'meta folder-retry-by');
    this.root.append(controls, this.said, this.byFolder);
    mount.appendChild(this.root);

    if (this.input.addEventListener) {
      // The suggestions are the list the page holds NOW — read when the operator comes to type.
      this.input.addEventListener('focus', () => this.suggest());
      this.input.addEventListener('input', () => this.refresh());
      this.input.addEventListener('keydown', (e) => { if (e && e.key === 'Enter') this.runPreview(); });
      this.previewBtn.addEventListener('click', () => this.runPreview());
      this.retryBtn.addEventListener('click', () => this.runRetry());
    }
  }

  folder() { return String(this.input.value || '').trim(); }

  suggest() {
    this.list.textContent = '';
    const failed = (this.rows() || []).filter((r) => r && isFailedStatus(r.status)).map((r) => r.filepath);
    for (const folder of folderCandidates(failed)) {
      const o = this.doc.createElement('option');
      o.value = folder;
      this.list.appendChild(o);
    }
  }

  /** The preview answer that belongs to what the field says now, or null. */
  current() {
    return this.seen && this.seen.folder === this.folder() ? this.seen : null;
  }

  refresh() {
    const seen = this.current();
    setDisabledReason(this.previewBtn, this.busy ? FOLDER_RETRY_WORDS.running
      : (this.folder() ? '' : FOLDER_RETRY_WORDS.needFolder));
    this.retryBtn.textContent = seen ? `${FOLDER_RETRY_WORDS.retry} ${seen.count}` : FOLDER_RETRY_WORDS.retry;
    setDisabledReason(this.retryBtn, this.busy ? FOLDER_RETRY_WORDS.running
      : !seen ? FOLDER_RETRY_WORDS.previewFirst
        : seen.count > 0 ? '' : seen.message);
    this.byFolder.textContent = '';
    for (const [name, n] of seen ? seen.byFolder : []) {
      this.byFolder.appendChild(Object.assign(this.doc.createElement('div'), { textContent: `${name} · ${n}` }));
    }
    // An empty line takes no row gap — or the space above the list changes with the state.
    this.byFolder.hidden = !(seen && seen.byFolder.length);
  }

  say(text, refused) {
    this.said.textContent = text || '';
    this.said.className = refused ? 'refusal folder-retry-said' : 'folder-retry-said';
    this.said.hidden = !text;
  }

  async runPreview() {
    const folder = this.folder();
    if (!folder || this.busy || !this.preview) return;
    this.busy = true;
    this.refresh();
    const got = await this.preview(folder);
    this.busy = false;
    const body = (got && got.body) || {};
    if (got && got.ok && Number.isInteger(body.count)) {
      this.seen = { folder, count: body.count, message: String(body.message || ''),
        byFolder: Object.entries(body.by_folder || {}) };
      this.say(this.seen.message, false);
    } else {
      this.seen = null;
      this.say((got && got.text) || '', true);
    }
    this.refresh();
  }

  async runRetry() {
    const seen = this.current();
    if (!seen || seen.count < 1 || this.busy || !this.retry) return;
    this.busy = true;
    this.refresh();
    const got = await this.retry(seen.folder);
    this.busy = false;
    // The count is spent: the next Retry needs a new preview of what is failed now.
    this.seen = null;
    this.say(got && got.ok ? String(((got.body) || {}).message || '') : ((got && got.text) || ''), !(got && got.ok));
    this.refresh();
    if (got && got.ok && this.onRetried) this.onRetried();
  }
}
