/** The SVG cross a remove draws - an icon, not the letter «×» (lead f3639d4a2). One for every page's removes: the
 *  declaration form's and the Tables page's chips. */
export function crossIcon(doc = globalThis.document) {
  if (!doc || typeof doc.createElementNS !== 'function') {
    const span = doc.createElement('span');
    span.className = 'chip-remove__icon';
    return span;
  }
  const NS = 'http://www.w3.org/2000/svg';
  const svg = doc.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 10 10');
  svg.setAttribute('aria-hidden', 'true');
  const line = doc.createElementNS(NS, 'path');
  line.setAttribute('d', 'M2 2l6 6M8 2l-6 6');
  svg.append(line);
  return svg;
}
