// ═══════════════════════════════════════════════════════════════════════════════
// 체인 그래프 — «누가 누구를 깨우나» 한 그림. 값만.
//
// 🔴 소유자 2026-09-11: 「chain 이 너무 거미줄 같아」. 한 흐름을 네 선언(chain · enrichment ·
//    virtual join · ledger)이 나눠 적고 있어서, 「이 표가 바뀌면 무엇이 도나」를 알려면 네
//    파일을 겹쳐 봐야 했습니다. 이 부품은 그 넷을 «한 그림»으로 놓습니다 (S-178 의 화면 절반).
//
// 🔴 여기서 «판정하지» 않습니다. 무엇이 무엇을 깨우는지도, 고리가 있는지도 서버가 선언에서
//    읽어 보낸 값입니다. 이 파일이 더하는 것은 「어디에 놓나」와 「어떤 선으로 그리나」뿐입니다.
//
// 🔴 모르는 종류를 «버리지 않습니다». 네 종류를 여기 적어 두고 그 밖을 빼면, 다섯째 선언이
//    생기는 날 그 선이 «그림에서 사라지고» 오류도 안 납니다 — 거미줄이 안 보이는 것이
//    이 부품이 없애려는 바로 그 상태입니다.
//
// ⛔ 설명 문구 «0» (상설). 원에 표 이름, 선에 종류, 그 밖에 문장이 없습니다.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 엣지 종류 넷. 순서는 «범례»의 순서이고 판정이 아닙니다.
 *
 * 🔴 S-179 (판정 293) 뒤로 «뜻이 둘» 바뀌었습니다 — 이름은 그대로입니다:
 *   mapper  체인 규칙이 표를 깨움. 인리치의 «자기 고리»와 «중복 제거 투영»도 이제 여기입니다
 *           (합성된 체인 규칙: 규칙 이름이 `enrichment_auto_confirm:` · `enrichment_dedup:` 로 시작)
 *   enrich  «폐기가 아니라 좁아졌습니다» — 이제 「참조뷰가 «읽는» 표 -> derived」 하나입니다
 *           (`reads:` 를 선언한 참조뷰가 있을 때만). 자동 확정은 더는 이 종류가 아닙니다
 */
export const EDGE_KINDS = Object.freeze(['mapper', 'enrich', 'vjoin', 'ledger']);

/** 합성된 규칙의 `origin` 은 이 접두로 시작합니다 — 뒤가 «어느 인리치에서 왔나»입니다. */
const SYNTHESIZED = 'synthesized:';

/**
 * 선 모양은 «CSS 가» 정하고 이 함수는 이름만 붙입니다.
 *
 * ⚠️ 모르는 종류도 «클래스를 받습니다». 그려지되 네 범례 중 어느 것도 아닌 모양이 되고,
 *    그것이 「새 선언이 생겼다」를 화면에서 말하는 방법입니다.
 */
export function edgeClass(kind) {
  const known = EDGE_KINDS.includes(kind);
  return `cg-edge cg-edge--${known ? kind : 'unknown'}`;
}

/**
 * 이 엣지가 «파일에 적힌 규칙»인가 «합성된 규칙»인가.
 *
 * 🔴 `origin` 은 «모든 엣지에 오지 않습니다». 실측(`server/chain_graph.py`): `mapper` 와
 *    `enrich` 만 싣고, `vjoin`·`ledger` 는 «종류가 곧 파일»이라 싣지 않습니다(소스 주석이
 *    그렇게 적습니다). 그래서 없는 것을 `file` 로 «채우지 않습니다» — 「안 왔다」와
 *    「파일에서 왔다」는 다른 사실이고, 채우면 vjoin 이 파일 규칙이라고 «주장»하게 됩니다.
 * @returns {{stated: boolean, synthesized: boolean, from: string|null}}
 */
export function originOf(edge) {
  const raw = edge && edge.origin;
  if (typeof raw !== 'string' || raw === '') return { stated: false, synthesized: false, from: null };
  if (raw.startsWith(SYNTHESIZED)) {
    return { stated: true, synthesized: true, from: raw.slice(SYNTHESIZED.length) || null };
  }
  return { stated: true, synthesized: false, from: null };
}

/**
 * 선언 순서의 «층» — 원천 표가 왼쪽, 파생이 오른쪽, 원장이 끝.
 *
 * 🔴 들어오는 엣지가 없는 노드가 층 0 입니다. 그 밖은 «자기를 깨우는 것들의 최대 층 + 1».
 * 🔴 고리가 있어도 «끝납니다». 방문 중인 노드를 다시 만나면 그 변을 층 계산에서만 무시합니다 —
 *    엣지는 그대로 그려지고, 고리라는 사실은 `cycles` 가 말합니다. 여기서 멈추면 거미줄이
 *    있는 바로 그 설치에서 그림이 «통째로» 안 나옵니다.
 */
export function layersOf(nodes, edges) {
  const incoming = new Map();
  for (const node of nodes) incoming.set(node.id, []);
  for (const edge of edges) {
    if (incoming.has(edge.to) && incoming.has(edge.from)) incoming.get(edge.to).push(edge.from);
  }
  const layer = new Map();
  const visiting = new Set();
  const depth = (id) => {
    if (layer.has(id)) return layer.get(id);
    if (visiting.has(id)) return 0;           // 고리 — 이 변만 무시합니다
    visiting.add(id);
    const parents = incoming.get(id) || [];
    const value = parents.length === 0 ? 0 : Math.max(...parents.map(depth)) + 1;
    visiting.delete(id);
    layer.set(id, value);
    return value;
  };
  for (const node of nodes) depth(node.id);
  return layer;
}

const NODE_GAP_Y = 64;
const LAYER_GAP_X = 190;
const MARGIN = 40;

/**
 * 응답 -> 그릴 것. DOM 이 없습니다.
 *
 * 🔴 「못 읽음」과 「그래프가 비었다」는 다른 상태입니다. 실패를 빈 그래프로 접으면 화면이
 *    「아무것도 안 깨운다」는 «거짓»을 말하고, 그건 이 그림이 없애려는 침묵 그대로입니다.
 */
export function chainGraphView(payload) {
  const nodes = payload && Array.isArray(payload.nodes) ? payload.nodes : null;
  if (!nodes) return { state: 'unread', nodes: [], edges: [], cycles: [] };
  const edges = payload && Array.isArray(payload.edges) ? payload.edges : [];
  const cycles = payload && Array.isArray(payload.cycles) ? payload.cycles : [];

  // 🔴 고리에 «든» 것만 빨강입니다. 고리가 하나라도 있으면 전부 빨갛게 칠하면, 어느 표가
  //    문제인지를 그림이 다시 감춥니다.
  // 🔴 그런데 `cycles` 의 «모양이 둘»입니다 (2026-09-11 라우트 실측, `server/chain_graph.py`):
  //    오늘 서버가 담는 것은 «검증기가 던진 «문장»»이고 표 이름의 배열이 아닙니다. 배열을
  //    전제하고 쓰면 빨강이 «한 번도 안 켜지고» 오류도 안 납니다 -- 이 부품이 없애려는
  //    침묵 그대로입니다. 그래서 «둘 다» 받습니다:
  //      배열  -> 그 표들만 빨강
  //      문장  -> 표시할 표를 «모르므로» 아무도 안 칠하고, 그 «문장을 값으로» 내놓습니다
  // ⛔ 문장에서 표 이름을 «뽑지» 않습니다. 그건 서버가 안 한 말을 화면이 지어내는 것입니다.
  const inCycle = new Set();
  const cycleNotes = [];
  for (const cycle of cycles) {
    if (Array.isArray(cycle)) for (const id of cycle) inCycle.add(id);
    else if (cycle) cycleNotes.push(String(cycle));
  }

  const layer = layersOf(nodes, edges);
  const seen = new Map();
  const placed = nodes.map((node) => {
    const column = layer.get(node.id) || 0;
    const row = seen.get(column) || 0;
    seen.set(column, row + 1);
    return {
      id: node.id,
      label: node.label || node.id,
      layer: column,
      x: MARGIN + column * LAYER_GAP_X,
      y: MARGIN + row * NODE_GAP_Y,
      // 「꺼져 있다」는 «값»입니다. 키가 없으면 끈 적이 없는 것이라 흐리게 그리지 않습니다.
      // ⚠️ 오늘 라우트의 «노드»는 `enabled` 도 `opt_in` 도 «안 실어 보냅니다»(실측:
      //    `{id, kind, declared, wakes}`). `enabled` 는 «엣지»에 있습니다. 그래서 이 두 칸은
      //    오늘 언제나 false 이고, 그 사실을 보고에 적었습니다 -- 키가 생기는 날 «코드 0 줄»로
      //    켜지도록 읽는 자리는 남겨 둡니다.
      dim: node.enabled === false,
      optIn: node.opt_in === true,
      // 🔴 카탈로그에 «없는» 표는 서버가 이름으로 말해 줍니다. 「모른다」가 아니라 「선언이
      //    없다」이고, 그 둘은 다른 사실입니다.
      undeclared: node.declared === false,
      kind: node.kind,
      inCycle: inCycle.has(node.id),
      wakes: Array.isArray(node.wakes) ? node.wakes : [],
    };
  });
  const at = new Map(placed.map((node) => [node.id, node]));

  return {
    state: 'ready',
    nodes: placed,
    edges: edges.map((edge) => {
      const origin = originOf(edge);
      return {
      from: edge.from,
      to: edge.to,
      kind: edge.kind,
      rule: edge.rule || null,
      // 🔴 합성 규칙은 «다른 선»입니다. 파일에 적힌 규칙과 같아 보이면, 운영자가 파일을 열어
      //    찾을 수 없는 규칙을 파일에서 찾게 됩니다.
      origin: origin.stated ? edge.origin : null,
      synthesized: origin.synthesized,
      // 「어느 인리치에서 왔나」 — 규칙 이름의 접두가 이미 말하지만, 값으로도 들고 있습니다.
      synthesizedFrom: origin.from,
      className: edgeClass(edge.kind)
        + (edge.enabled === false ? ' is-dim' : '')
        + (origin.synthesized ? ' is-synth' : '')
        + (inCycle.has(edge.from) && inCycle.has(edge.to) ? ' is-cycle' : ''),
      x1: (at.get(edge.from) || {}).x,
      y1: (at.get(edge.from) || {}).y,
      x2: (at.get(edge.to) || {}).x,
      y2: (at.get(edge.to) || {}).y,
      };
    }),
    cycles,
    // 「고리가 있다」는 사실은 표를 못 칠할 때도 «말해져야» 합니다.
    cycleNotes,
  };
}

const SVG_NS = 'http://www.w3.org/2000/svg';

export class ChainGraphPanel {
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('ChainGraphPanel needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('ChainGraphPanel needs a document (deps.doc or mount.ownerDocument)');
    this.root = this.doc.createElement('div');
    this.root.className = 'chain-graph-panel';
    this.mount.appendChild(this.root);
    // 🔴 클릭이 고른 표. 선택은 «부품의» 상태이고 그래프의 값이 아닙니다.
    this.selected = null;
  }

  _svg(tag, attrs) {
    const el = this.doc.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value !== undefined && value !== null) el.setAttribute(key, String(value));
    }
    return el;
  }

  /** @param {object|null} payload `GET /chain/graph` 의 응답, 못 읽었으면 `null` */
  render(payload) {
    const view = chainGraphView(payload);
    this.view = view;
    this.root.textContent = '';

    if (view.state === 'unread') {
      const box = this.doc.createElement('div');
      box.className = 'chain-graph-unread';
      box.textContent = '—';
      this.root.appendChild(box);
      return view;
    }

    const width = MARGIN * 2 + Math.max(0, ...view.nodes.map((n) => n.x));
    const height = MARGIN * 2 + Math.max(0, ...view.nodes.map((n) => n.y));
    const svg = this._svg('svg', { class: 'chain-graph', viewBox: `0 0 ${width} ${height}` });

    // 선을 «먼저» 그립니다 — 원 밑으로 지나가야 원이 가려지지 않습니다.
    for (const edge of view.edges) {
      if (edge.x1 === undefined || edge.x2 === undefined) continue;   // 끝이 없는 변은 못 그립니다
      svg.appendChild(this._svg('line', {
        class: edge.className, x1: edge.x1, y1: edge.y1, x2: edge.x2, y2: edge.y2,
        'data-kind': edge.kind,
        // 값이 «없으면 칸도 없습니다» — 빈 속성은 「파일에서 왔다」로 읽힙니다.
        'data-origin': edge.origin,
        'data-rule': edge.rule,
      }));
    }

    for (const node of view.nodes) {
      const group = this._svg('g', {
        class: 'cg-node' + (node.dim ? ' is-dim' : '') + (node.inCycle ? ' is-cycle' : '')
          + (node.undeclared ? ' is-undeclared' : '')
          + (node.kind === 'ledger' ? ' is-ledger' : ''),
        'data-node': node.id,
      });
      group.appendChild(this._svg('circle', { cx: node.x, cy: node.y, r: 12 }));
      const label = this._svg('text', { x: node.x + 18, y: node.y + 4 });
      label.textContent = node.label;
      group.appendChild(label);
      // 옵트인은 «표시 하나»입니다. 문장이 아닙니다.
      if (node.optIn) {
        const mark = this._svg('text', { class: 'cg-optin', x: node.x - 4, y: node.y - 16 });
        mark.textContent = '◦';
        group.appendChild(mark);
      }
      if (group.addEventListener) {
        group.addEventListener('click', () => { this.select(node.id); });
      }
      svg.appendChild(group);
    }
    this.root.appendChild(svg);
    // 🔴 표를 못 칠하는 고리도 «말해집니다». 문장은 서버의 것이고 여기서 다시 쓰지 않습니다.
    for (const note of view.cycleNotes || []) {
      const line = this.doc.createElement('div');
      line.className = 'chain-graph-cycle';
      line.textContent = note;
      this.root.appendChild(line);
    }
    this.wakesBox = this._wakes();
    this.root.appendChild(this.wakesBox);
    return view;
  }

  /** 고른 표가 «무엇을 깨우나» — 값의 목록입니다. */
  _wakes() {
    const box = this.doc.createElement('div');
    box.className = 'chain-graph-wakes';
    const node = (this.view ? this.view.nodes : []).find((n) => n.id === this.selected);
    if (!node) return box;
    const head = this.doc.createElement('div');
    head.className = 'chain-graph-wakes-head';
    head.textContent = node.label;
    box.appendChild(head);
    for (const wake of node.wakes) {
      const line = this.doc.createElement('div');
      line.className = 'chain-graph-wake';
      line.textContent = typeof wake === 'string' ? wake : JSON.stringify(wake);
      box.appendChild(line);
    }
    return box;
  }

  select(id) {
    this.selected = id;
    // 🔴 다시 그리는 대신 «목록만» 갈아 끼웁니다. 그래프를 다시 그리면 고른 원이 깜빡이고,
    //    클릭이 먹었는지 아닌지가 화면에서 안 보입니다.
    // ⚠️ 갈아 끼울 자리는 «들고 있습니다». `root.children` 을 뒤지면 그것은 진짜 DOM 에서
    //    HTMLCollection 이라 `find` 가 없습니다 — 하니스의 가짜 노드에서만 도는 코드가 됩니다.
    const next = this._wakes();
    if (this.wakesBox && this.wakesBox.parentNode === this.root) {
      this.root.replaceChild(next, this.wakesBox);
    } else {
      this.root.appendChild(next);
    }
    this.wakesBox = next;
    return next;
  }
}
