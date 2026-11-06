/**
 * GuideReader - the Help panel's Guide (owner 11-06 «헬퍼는 시안대로»): the declaration guides read without asking.
 * The guides and the tabs each is shown on are the server's (GET /admin/help/guides, `help_guides.GUIDE_TABS`).
 *
 *   picks     the guides for this tab as chips · every guide in «All N» · the guide's sections
 *   find      every hit in the guide, «2 of 5», marked in the section shown; Enter the next, Shift+Enter the one before
 *   body      the section as written (guide_markdown.js) · ‹ Previous section · Next section ›
 *
 * deps
 *   doc    the document
 *   load   () -> {ok, body: {guides}} | {ok: false, error} - asked once; a refusal is drawn and asked again on show
 */
import { readMarkdown, runsOf, hitsIn, drawBlocks } from './guide_markdown.js';
import { setDisabledReason } from './disabled_reason.js';

export const GUIDES_ROUTE = '/admin/help/guides';
export const LOADING = 'Loading guides';
export const NONE_FOR_TAB = 'None for this tab';
export const NO_MATCH = 'No match';
export const FIRST_SECTION = 'The first section';
export const LAST_SECTION = 'The last section';

export class GuideReader {
  constructor(host, deps = {}) {
    this.host = host;
    this.doc = deps.doc;
    this.load = deps.load;
    this.guides = null;          // [{path, file, updated, tabs, sections}] once loaded
    this.refused = '';
    this.tab = null;
    this.file = null;
    this.section = 0;
    this.find = '';
    this.hit = 0;                // the current hit, counted over the whole guide
    this.parsed = new Map();     // file -> [{blocks, runs}] per section
    this.root = null;
  }

  el(tag, cls, text) {
    const e = this.doc.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  button(cls, text, onClick) {
    const b = this.el('button', `btn ${cls}`.trim(), text);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  /** Shows the guides for `tab` - `file` when given, else the one shown before when it is this tab's, else its first. */
  async show(tab, file = null) {
    if (!this.root) this.build();
    this.tab = tab;
    if (file) this.pick(file);
    if (!this.guides) {
      this.render();
      const got = await this.load();
      if (!got || !got.ok) {
        this.refused = (got && got.error) || 'Guides refused';
        this.render();
        return;
      }
      this.refused = '';
      this.guides = got.body.guides || [];
    }
    const mine = this.forTab();
    const known = this.guides.some((g) => g.file === this.file);
    if (!known || (!file && mine.length && !mine.some((g) => g.file === this.file))) {
      this.pick((mine[0] || this.guides[0] || {}).file || null);
    }
    this.render();
  }

  forTab() { return (this.guides || []).filter((g) => g.tabs.includes(this.tab)); }

  get guide() { return (this.guides || []).find((g) => g.file === this.file) || null; }

  pick(file) {
    if (file === this.file) return;
    this.file = file;
    const g = this.guide;
    const first = g ? g.sections.findIndex((s) => s.text.trim()) : -1;
    this.section = Math.max(first, 0);
    this.hit = 0;
  }

  sectionsOf(g) {
    if (!this.parsed.has(g.file)) {
      this.parsed.set(g.file, g.sections.map((s) => {
        const blocks = readMarkdown(s.text);
        return { blocks, runs: runsOf(blocks) };
      }));
    }
    return this.parsed.get(g.file);
  }

  /** Hits per section of the guide shown. */
  hits() {
    const g = this.guide;
    if (!g || !this.find) return [];
    return this.sectionsOf(g).map((s) => s.runs.reduce((n, run) => n + hitsIn(run, this.find).length, 0));
  }

  /** Moves the current hit by `step` and shows its section. */
  go(step) {
    const per = this.hits();
    const total = per.reduce((a, b) => a + b, 0);
    if (!total) return;
    this.hit = (this.hit + step + total) % total;
    let n = this.hit;
    this.section = per.findIndex((count) => { if (n < count) return true; n -= count; return false; });
    this.render();
  }

  build() {
    const root = this.el('div', 'guide-reader');
    const picks = this.el('div', 'guide-reader__line');
    this.tabLabel = this.el('span', 'guide-reader__label', 'For this tab');
    this.chips = this.el('span', 'guide-reader__chips');
    this.all = this.el('select', 'guide-reader__all');
    this.all.setAttribute('aria-label', 'All guides');
    this.all.addEventListener('change', () => { if (this.all.value) { this.pick(this.all.value); this.render(); } });
    picks.append(this.tabLabel, this.chips, this.all);

    const sections = this.el('label', 'guide-reader__line');
    this.sections = this.el('select', 'guide-reader__sections');
    this.sections.addEventListener('change', () => { this.section = Number(this.sections.value); this.render(); });
    sections.append(this.el('span', 'guide-reader__label', 'Sections'), this.sections);

    const find = this.el('label', 'guide-reader__line');
    this.input = this.el('input', 'guide-reader__find');
    this.input.type = 'search';
    this.input.addEventListener('input', () => { this.find = this.input.value.trim(); this.hit = 0; this.go(0); this.render(); });
    this.input.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      if (e.preventDefault) e.preventDefault();
      this.go(e.shiftKey ? -1 : 1);
    });
    this.count = this.el('span', 'guide-reader__count');
    find.append(this.el('span', 'guide-reader__label', 'Find'), this.input, this.count);

    const controls = this.el('div', 'guide-reader__controls');
    controls.append(picks, sections, find);
    this.controls = controls;
    this.body = this.el('article', 'guide-reader__body');
    root.append(controls, this.body);
    this.root = root;
    this.host.appendChild(root);
  }

  render() {
    if (!this.root) return;
    this.body.textContent = '';
    // nothing to pick from until the guides came: the refusal (or Loading) stands alone
    this.controls.hidden = !this.guides;
    if (!this.guides) {
      this.body.appendChild(this.el('div', 'guide-reader__state', this.refused || LOADING));
      return;
    }
    this.drawPicks();
    const g = this.guide;
    if (!g) return;
    this.sections.textContent = '';
    g.sections.forEach((s, n) => {
      const o = this.el('option', '', `${' '.repeat(s.level - 1)}${s.path[s.path.length - 1]}`);
      o.value = String(n);
      this.sections.appendChild(o);
    });
    this.sections.value = String(this.section);

    const per = this.hits();
    const total = per.reduce((a, b) => a + b, 0);
    this.count.textContent = !this.find ? '' : total ? `${this.hit + 1} of ${total}` : NO_MATCH;
    const before = per.slice(0, this.section).reduce((a, b) => a + b, 0);

    const s = g.sections[this.section];
    this.body.appendChild(this.el('div', 'guide-reader__meta', `${g.file} · updated ${String(g.updated).slice(0, 10)}`));
    this.body.appendChild(this.el('h3', 'guide-reader__heading', s.path[s.path.length - 1]));
    const text = this.el('div', 'guide-reader__text');
    let seen = before;
    const mark = (run) => {
      const spots = hitsIn(run, this.find);
      if (!spots.length) return [this.doc.createTextNode(run)];
      const out = [];
      let at = 0;
      spots.forEach(([a, b]) => {
        if (a > at) out.push(this.doc.createTextNode(run.slice(at, a)));
        const m = this.el('mark', seen === this.hit ? 'guide-hit is-current' : 'guide-hit', run.slice(a, b));
        seen += 1;
        out.push(m);
        at = b;
      });
      if (at < run.length) out.push(this.doc.createTextNode(run.slice(at)));
      return out;
    };
    text.appendChild(drawBlocks(this.doc, this.sectionsOf(g)[this.section].blocks, mark));
    this.body.appendChild(text);

    const steps = this.el('div', 'guide-reader__steps');
    const prev = this.button('guide-reader__prev', '‹ Previous section', () => { this.section -= 1; this.render(); });
    const next = this.button('guide-reader__next', 'Next section ›', () => { this.section += 1; this.render(); });
    setDisabledReason(prev, this.section <= 0 ? FIRST_SECTION : '');
    setDisabledReason(next, this.section >= g.sections.length - 1 ? LAST_SECTION : '');
    steps.append(prev, next);
    this.body.appendChild(steps);
    const current = this.body.querySelector('.guide-hit.is-current');
    if (current && current.scrollIntoView) current.scrollIntoView({ block: 'center' });
    else if (this.body.scrollTo) this.body.scrollTo(0, 0);
  }

  drawPicks() {
    const mine = this.forTab();
    this.chips.textContent = '';
    if (!mine.length) this.chips.appendChild(this.el('span', 'guide-reader__none', NONE_FOR_TAB));
    mine.forEach((g) => {
      const chip = this.button(`guide-chip${g.file === this.file ? ' is-on' : ''}`, g.file, () => { this.pick(g.file); this.render(); });
      chip.setAttribute('aria-pressed', g.file === this.file ? 'true' : 'false');
      this.chips.appendChild(chip);
    });
    this.all.textContent = '';
    const head = this.el('option', '', `All ${this.guides.length}`);
    head.value = '';
    this.all.appendChild(head);
    this.guides.forEach((g) => { const o = this.el('option', '', g.file); o.value = g.file; this.all.appendChild(o); });
    this.all.value = mine.some((g) => g.file === this.file) ? '' : this.file;
  }
}
