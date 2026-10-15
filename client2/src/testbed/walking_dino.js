// «Walking…»'s dinosaur (owner 10-15) - its own module: the part's root names no slot (testbed_harness T19).

/** «Walking…»'s dinosaur (owner 10-15): pixels in the notice's own colour, its two legs taking turns (testbed.css). */
const DINO = {
  body: [[11, 1, 8, 5], [10, 5, 4, 3], [4, 7, 10, 6], [1, 6, 3, 2], [2, 8, 3, 2], [14, 9, 2, 1]],
  eye: [[16, 2, 1, 1]],
  a: [[6, 13, 2, 4], [6, 16, 3, 1], [10, 13, 2, 2]],
  b: [[6, 13, 2, 2], [10, 13, 2, 4], [10, 16, 3, 1]],
};
export function walkingDino(doc) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = doc.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 20 18');
  svg.setAttribute('class', 'tb-dino');
  svg.setAttribute('aria-hidden', 'true');
  for (const [part, cells] of Object.entries(DINO)) {
    const g = doc.createElementNS(NS, 'g');
    g.setAttribute('class', `tb-dino__${part}`);
    for (const [x, y, w, h] of cells) {
      const r = doc.createElementNS(NS, 'rect');
      for (const [k, v] of [['x', x], ['y', y], ['width', w], ['height', h]]) r.setAttribute(k, String(v));
      g.appendChild(r);
    }
    svg.appendChild(g);
  }
  return svg;
}
