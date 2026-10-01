// Layered graph — the one SVG drawer every layered picture declares into (lead 65754c39a; the chain graph
// and the subgraph viewer). 근원 템플릿 상설: the template is the shape, each screen's declaration is the value.
//
// It knows slots, shapes, lines and texts; it composes no name of its own. Every class and data attribute
// it writes was handed to it, and where a slot stands is the declaration's geometry - so a screen's
// picture is its declaration and nothing here.
// ⛔ Layout (which layer, which row) stays in each screen: the chain asks 「who wakes whom」, the viewer
//    「how many steps from the start」. Only layer/row -> x/y is one author, `slotXY`.

const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * Where a slot stands: the column a layer is, the row inside it.
 * @param {{margin: number, gapX: number, gapY: number}} geometry
 */
export function slotXY(geometry, layer, row) {
  return { x: geometry.margin + layer * geometry.gapX, y: geometry.margin + row * geometry.gapY };
}

/**
 * Draw one declaration and return its box (the caller places it), the SVG, and each node's group by id.
 *
 * @param {Document} doc
 * @param {{
 *   geometry: {r: number, labelDx: number},
 *   boxClass: string, svgClass: string, width: number, height: number,
 *   edges: Array<{x1: number, y1: number, x2: number, y2: number, attrs: object}>,
 *   nodes: Array<{id: string, x: number, y: number, shape?: 'circle'|'rect', attrs: object, label: string,
 *                 marks?: Array<{dx: number, dy: number, text: string, attrs: object}>, onPress?: Function}>,
 *   texts?: Array<{x: number, y: number, text: string, attrs: object, onPress?: Function}>,
 * }} decl
 */
export function drawLayeredGraph(doc, decl) {
  const make = (tag, attrs) => {
    const node = doc.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value !== undefined && value !== null) node.setAttribute(key, String(value));
    }
    return node;
  };
  const { r, labelDx } = decl.geometry;
  const svg = make('svg', {
    class: decl.svgClass, viewBox: `0 0 ${decl.width} ${decl.height}`,
    width: decl.width, height: decl.height, preserveAspectRatio: 'xMinYMin meet',
  });
  // Lines first, so the shapes sit on top of them.
  for (const edge of decl.edges || []) {
    svg.appendChild(make('line', { ...edge.attrs, x1: edge.x1, y1: edge.y1, x2: edge.x2, y2: edge.y2 }));
  }
  const groups = new Map();
  for (const node of decl.nodes || []) {
    const group = make('g', node.attrs);
    group.appendChild(node.shape === 'rect'
      ? make('rect', { x: node.x - r, y: node.y - r, width: r * 2, height: r * 2 })
      : make('circle', { cx: node.x, cy: node.y, r }));
    const label = make('text', { x: node.x + labelDx, y: node.y + 4 });
    label.textContent = node.label;
    group.appendChild(label);
    for (const mark of node.marks || []) {
      const text = make('text', { ...mark.attrs, x: node.x + mark.dx, y: node.y + mark.dy });
      text.textContent = mark.text;
      group.appendChild(text);
    }
    if (node.onPress && group.addEventListener) group.addEventListener('click', node.onPress);
    svg.appendChild(group);
    groups.set(node.id, group);
  }
  for (const item of decl.texts || []) {
    const group = make('g', item.attrs);
    const text = make('text', { x: item.x, y: item.y + 4 });
    text.textContent = item.text;
    group.appendChild(text);
    if (item.onPress && group.addEventListener) group.addEventListener('click', item.onPress);
    svg.appendChild(group);
  }
  // The box is the screen's: its height cap and scroll come from the class it declares.
  const box = doc.createElement('div');
  box.className = decl.boxClass;
  box.appendChild(svg);
  return { box, svg, groups };
}
