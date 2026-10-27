/** The worlds' facts (lead 10-27, B ed4b6cb84): the sources more than one world declares and the worlds' notices,
 *  as the worlds read sends them - one meta line each, overlaps first. Facts, not warnings: the base layer's meta ink.
 *  Nothing is drawn when both are empty. */

/** «process_event · same name · default, lab», or one table read under other names «proc_pass · same table ·
 *  default (a), lab (b)». */
export function overlapLine(overlap) {
  const o = overlap || {};
  if (o.same === 'table') {
    const read = Object.entries(o.sources || {}).map(([world, source]) => `${world} (${source})`).join(', ');
    return `${o.relation} · same table · ${read}`;
  }
  return `${o.source} · same name · ${(o.worlds || []).join(', ')}`;
}

/** A world's notice as the server wrote it («<world>: <sentence>»), the world named first. */
export function noticeLine(notice) {
  const text = String(notice == null ? '' : notice);
  const at = text.indexOf(': ');
  return at > 0 ? `${text.slice(0, at)} · ${text.slice(at + 2)}` : text;
}

export class WorldFacts {
  constructor(mount, { doc } = {}) {
    this.doc = doc || null;
    this.overlaps = [];
    this.notices = [];
    this.attach(mount);
  }

  /** Seat the part in `mount` (the same one again is fine) and draw it there. */
  attach(mount) {
    this.mount = mount || null;
    this.render();
  }

  show({ overlaps, notices } = {}) {
    this.overlaps = Array.isArray(overlaps) ? overlaps.slice() : [];
    this.notices = Array.isArray(notices) ? notices.slice() : [];
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.mount) return;
    this.mount.textContent = '';
    const facts = [...this.overlaps.map(overlapLine), ...this.notices.map(noticeLine)];
    if (!facts.length) return;
    const body = doc.createElement('div');
    body.className = 'box-body world-facts';
    body.setAttribute('aria-label', 'World facts');
    for (const fact of facts) {
      const line = doc.createElement('div');
      line.className = 'meta world-fact';
      line.textContent = fact;
      body.appendChild(line);
    }
    this.mount.appendChild(body);
  }
}
