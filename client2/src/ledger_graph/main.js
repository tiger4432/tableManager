import '../tokens.css';
import { API_BASE } from '../config.js';
import { initTheme } from '../theme.js';
import { edgeCurves, filterGraph, radialLayout, readGraph, readStructure, subgraphFrom } from './graph_core.js';
import { createEntityCatalog } from './entity_catalog.js';

const $ = (selector) => document.querySelector(selector);
const els = {
  form: $('[data-lg-search]'), entityType: $('[data-lg-entity-type]'), entityQuery: $('[data-lg-entity-query]'), hops: $('[data-lg-hops]'),
  status: $('[data-lg-status]'), summary: $('[data-lg-summary]'), canvas: $('[data-lg-canvas]'),
  wrap: $('[data-lg-canvas-wrap]'), overlay: $('[data-lg-overlay]'), foot: $('[data-lg-foot]'),
  detailTitle: $('[data-lg-detail-title]'), detailBody: $('[data-lg-detail-body]'),
  typeFilters: $('[data-lg-type-filters]'), predicateFilters: $('[data-lg-predicate-filters]'),
  nodeCount: $('[data-lg-node-count]'), edgeCount: $('[data-lg-edge-count]'),
  filterText: $('[data-lg-filter-text]'), fit: $('[data-lg-fit]'),
  modeButtons: [...document.querySelectorAll('[data-lg-mode]')],
  nodeSearch: $('[data-lg-node-search]'), nodeList: $('[data-lg-node-list]'),
  nodeListCount: $('[data-lg-node-list-count]'), clearFocus: $('[data-lg-clear-focus]'),
  nodeListLabel: $('[data-lg-node-list-label]'), showEmpty: $('[data-lg-show-empty]'),
  catalog: $('[data-lg-catalog]'), catalogList: $('[data-lg-catalog-list]'),
  catalogCount: $('[data-lg-catalog-count]'), catalogStatus: $('[data-lg-catalog-status]'),
  catalogMore: $('[data-lg-catalog-more]'),
};

let entityCatalog = null;

const state = {
  source: readGraph(null), visible: readGraph(null), positions: new Map(), curves: new Map(),
  selected: null, hoverId: null, typeSet: new Set(), predicateSet: new Set(),
  request: 0, aborter: null, drag: null, mode: 'ontology', manualPositions: new Map(), focusNodeId: null,
  view: { scale: 1, tx: 0, ty: 0, width: 0, height: 0, dpr: 1 },
};

const palette = ['#2563eb', '#7c3aed', '#0891b2', '#db2777', '#d97706', '#059669', '#dc2626'];
const typeColor = (type) => {
  let hash = 0;
  for (const ch of String(type)) hash = ((hash * 31) + ch.charCodeAt(0)) >>> 0;
  return palette[hash % palette.length];
};
const fmt = (n) => Number(n || 0).toLocaleString('ko-KR');
const short = (value, length = 24) => String(value).length > length ? `${String(value).slice(0, length - 1)}…` : String(value);
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (ch) => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[ch]));

function resizeCanvas() {
  const rect = els.wrap.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  state.view.width = rect.width; state.view.height = rect.height; state.view.dpr = dpr;
  els.canvas.width = Math.round(rect.width * dpr); els.canvas.height = Math.round(rect.height * dpr);
  els.canvas.style.width = `${rect.width}px`; els.canvas.style.height = `${rect.height}px`;
  draw();
}

function fit() {
  if (!state.positions.size) return;
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  for (const point of state.positions.values()) {
    minX=Math.min(minX,point.x); minY=Math.min(minY,point.y); maxX=Math.max(maxX,point.x); maxY=Math.max(maxY,point.y);
  }
  const width=Math.max(180,maxX-minX+180); const height=Math.max(180,maxY-minY+180);
  state.view.scale=Math.min(1.25,Math.max(.14,Math.min(state.view.width/width,state.view.height/height)));
  state.view.tx=state.view.width/2-((minX+maxX)/2)*state.view.scale;
  state.view.ty=state.view.height/2-((minY+maxY)/2)*state.view.scale;
  draw();
}

function layoutVisible() {
  state.positions = radialLayout(state.visible);
  for (const node of state.visible.nodes) {
    const saved = state.manualPositions.get(node.id);
    if (saved) state.positions.set(node.id, { ...saved });
  }
  state.curves = edgeCurves(state.visible.edges);
}

function bezier(edge) {
  const a=state.positions.get(edge.source); const b=state.positions.get(edge.target);
  if (!a||!b) return null;
  const offset=state.curves.get(edge.id)||0; const mx=(a.x+b.x)/2; const my=(a.y+b.y)/2;
  const dx=b.x-a.x; const dy=b.y-a.y; const length=Math.hypot(dx,dy)||1;
  return {a,b,c:{x:mx+(-dy/length)*offset,y:my+(dx/length)*offset}};
}

function drawArrow(ctx, c, b, color) {
  const angle=Math.atan2(b.y-c.y,b.x-c.x); const x=b.x-Math.cos(angle)*18; const y=b.y-Math.sin(angle)*18;
  ctx.fillStyle=color; ctx.beginPath(); ctx.moveTo(x,y);
  ctx.lineTo(x-Math.cos(angle-.55)*9,y-Math.sin(angle-.55)*9);
  ctx.lineTo(x-Math.cos(angle+.55)*9,y-Math.sin(angle+.55)*9); ctx.closePath(); ctx.fill();
}

function draw() {
  const ctx=els.canvas.getContext('2d'); const {dpr,width,height,scale,tx,ty}=state.view;
  ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,width,height); ctx.translate(tx,ty); ctx.scale(scale,scale);
  for (const edge of state.visible.edges) {
    const path=bezier(edge); if(!path) continue;
    const selected=state.selected?.kind==='edge'&&state.selected.value.id===edge.id;
    const inferred=edge.rank===3 || edge.basis?.kind==='convention';
    ctx.strokeStyle=selected?'#2563eb':'#94a3b8'; ctx.lineWidth=(selected?3:1.45)/Math.max(.55,scale);
    ctx.setLineDash(inferred?[7/scale,5/scale]:[]); ctx.beginPath(); ctx.moveTo(path.a.x,path.a.y);
    ctx.quadraticCurveTo(path.c.x,path.c.y,path.b.x,path.b.y); ctx.stroke(); ctx.setLineDash([]);
    drawArrow(ctx,path.c,path.b,selected?'#2563eb':'#94a3b8');
    // Repeated membership labels hide the actual split/merge structure. Keep
    // lineage labels visible and reveal every other predicate when selected.
    if(scale>.55&&(state.mode==='ontology'||edge.predicate==='derived_from'||selected)){ctx.font=`${12/scale}px system-ui`;ctx.fillStyle='#64748b';ctx.textAlign='center';ctx.fillText(edge.predicateLabel||edge.predicate,path.c.x,path.c.y-7/scale);}
  }
  for (const node of state.visible.nodes) {
    const point=state.positions.get(node.id); if(!point) continue;
    const selected=state.selected?.kind==='node'&&state.selected.value.id===node.id;
    const hovered=state.hoverId===node.id; const center=node.id===state.source.seedId;
    if(center){ctx.strokeStyle='#f59e0b';ctx.lineWidth=4/scale;ctx.beginPath();ctx.arc(point.x,point.y,24/scale,0,Math.PI*2);ctx.stroke();}
    const radius=(selected||hovered?18:14)/scale;ctx.fillStyle=typeColor(node.type);ctx.beginPath();
    if(node.schema_kind==='claim_shape')ctx.roundRect(point.x-radius,point.y-radius,radius*2,radius*2,4/scale);else ctx.arc(point.x,point.y,radius,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='#fff';ctx.lineWidth=2/scale;ctx.stroke();
    if(scale>.34){ctx.font=`600 ${13/scale}px system-ui`;ctx.textAlign='center';ctx.fillStyle='#1e293b';ctx.fillText(short(node.label,26),point.x,point.y+34/scale);ctx.font=`${11/scale}px system-ui`;ctx.fillStyle='#64748b';ctx.fillText(node.type,point.x,point.y+49/scale);}
  }
}

function nodeAt(x,y){
  const wx=(x-state.view.tx)/state.view.scale; const wy=(y-state.view.ty)/state.view.scale; let best=null; let distance=Infinity;
  for(const node of state.visible.nodes){const p=state.positions.get(node.id);if(!p)continue;const d=Math.hypot(p.x-wx,p.y-wy);if(d<24/state.view.scale&&d<distance){best=node;distance=d;}}
  return best;
}

function edgeAt(x,y){
  const wx=(x-state.view.tx)/state.view.scale; const wy=(y-state.view.ty)/state.view.scale; let best=null; let distance=Infinity;
  for(const edge of state.visible.edges){const p=bezier(edge);if(!p)continue;for(let i=0;i<=18;i++){const t=i/18;const q=1-t;const px=q*q*p.a.x+2*q*t*p.c.x+t*t*p.b.x;const py=q*q*p.a.y+2*q*t*p.c.y+t*t*p.b.y;const d=Math.hypot(px-wx,py-wy);if(d<10/state.view.scale&&d<distance){best=edge;distance=d;}}}
  return best;
}

function keyRows(keys){return Object.entries(keys||{}).map(([k,v])=>`<div class="lg-kv"><span>${escapeHtml(k)}</span><strong>${escapeHtml(v)}</strong></div>`).join('');}
function select(kind,value){state.selected={kind,value};renderDetail();draw();}
function renderDetail(){
  if(!state.selected){els.detailTitle.textContent='선택 없음';els.detailBody.className='lg-panel__body lg-empty-copy';els.detailBody.textContent='노드나 선을 클릭하면 신원, 관계, 근거를 보여줍니다.';return;}
  els.detailBody.className='lg-panel__body';
  if(state.selected.kind==='node'){
    const n=state.selected.value;els.detailTitle.textContent=n.label;
    const connections=state.source.edges.filter((e)=>e.source===n.id||e.target===n.id);
    if(state.mode==='ontology'){
      const entity=n.schema_kind==='entity_type';
      const predicates=(n.predicates||[]).filter((p)=>els.showEmpty.checked||Number(p.count)>0);
      els.detailBody.innerHTML=`<span class="lg-type-chip" style="--chip:${typeColor(n.type)}">${escapeHtml(entity?'Entity Type':n.type)}</span>${keyRows(n.keys)}<div class="lg-section"><h3>${entity?'원장 현황':'주장 형태'}</h3>${entity?`<p>주어 원자 <b>${fmt(n.atoms_as_subject)}</b></p><p>목적어 원자 <b>${fmt(n.atoms_as_object)}</b></p><p>등록 <b>${n.registered===null?'해당 없음':fmt(n.registered)}</b></p><p>상태 <b>${escapeHtml(n.node_state||'미보고')}</b></p>`:`<p>목적어 종류 <b>${escapeHtml(n.object_kind||'없음')}</b></p><p>원자 <b>${fmt(n.claim_count)}</b></p>`}</div><div class="lg-section"><h3>연결된 술어</h3>${predicates.map((p)=>`<p>${escapeHtml(p.label||p.predicate)} <b>${fmt(p.count)}</b></p>`).join('')||`<p>연결 ${fmt(connections.length)}개</p>`}</div>`;
      return;
    }
    const recenter=n.id.startsWith('ledger-entity:v1:')?`<button class="lg-recenter" data-lg-recenter="${escapeHtml(n.id)}">이 개체 중심으로 탐색</button>`:'';
    els.detailBody.innerHTML=`<span class="lg-type-chip" style="--chip:${typeColor(n.type)}">${escapeHtml(n.type)}</span>${keyRows(n.keys)}<div class="lg-section"><h3>원장 요약</h3><p>주장 ${fmt(n.claim_count)}건 · 연결 ${fmt(connections.length)}개 · 시작점에서 ${n.depth??'—'}홉</p></div><div class="lg-section"><h3>술어</h3>${(n.predicates||[]).map((p)=>`<p>${escapeHtml(p.predicate)} <b>${fmt(p.count)}</b></p>`).join('')||'<p>없음</p>'}</div>${recenter}`;
    const btn=els.detailBody.querySelector('[data-lg-recenter]');if(btn)btn.addEventListener('click',()=>exploreEntity({id:btn.dataset.lgRecenter,type:n.type,label:n.label}));
  }else{
    const e=state.selected.value;els.detailTitle.textContent=e.predicate;
    const from=state.source.nodes.find((n)=>n.id===e.source);const to=state.source.nodes.find((n)=>n.id===e.target);
    if(state.mode==='ontology'){
      const sourceRows=(e.sourceRows||[]).map((row)=>`<p>${escapeHtml(row.source_who||'미상')} <b>${fmt(row.atoms)}</b></p>`).join('');
      const classRows=Object.entries(e.classes||{}).filter(([,count])=>Number(count)>0).map(([name,count])=>`<p>${escapeHtml(name)} <b>${fmt(count)}</b></p>`).join('');
      els.detailTitle.textContent=e.predicateLabel||e.predicate;
      els.detailBody.innerHTML=`<div class="lg-path"><strong>${escapeHtml(from?.label||e.source)}</strong><span>→ ${escapeHtml(e.predicateLabel||e.predicate)} →</span><strong>${escapeHtml(to?.label||e.target)}</strong></div><div class="lg-section"><h3>원장 현황</h3><p>원자 <b>${fmt(e.witnesses)}</b></p><p>상태 <b>${escapeHtml(e.edge_state||e.status||'미보고')}</b></p><p>계층 <b>${escapeHtml(e.layer||'미보고')}</b></p></div><div class="lg-section"><h3>계약</h3><p>목적어 <b>${escapeHtml(e.object_kind_label||e.object_kind||'없음')}</b></p><p>필수 필드 <b>${escapeHtml((e.object_fields||[]).join(', ')||'없음')}</b></p><p>한정자 <b>${escapeHtml((e.qualifiers||[]).join(', ')||'없음')}</b></p></div>${classRows?`<details class="lg-section"><summary>근거 등급</summary>${classRows}</details>`:''}${sourceRows?`<details class="lg-section"><summary>출처 ${fmt(e.sourceRows.length)}개</summary>${sourceRows}</details>`:''}<div class="lg-section"><h3>기간</h3><p>${escapeHtml(e.first_at||'—')}</p><p>${escapeHtml(e.last_at||'—')}</p></div>`;
      return;
    }
    els.detailBody.innerHTML=`<div class="lg-path"><strong>${escapeHtml(from?.label||e.source)}</strong><span>→ ${escapeHtml(e.predicate)} →</span><strong>${escapeHtml(to?.label||e.target)}</strong></div><div class="lg-section"><h3>근거</h3><p>원자 ${fmt(e.witnesses)}건 · 해소 등급 ${e.rank??'미보고'}</p><p>${escapeHtml((e.sources||[]).join(' · ')||'출처 미보고')}</p></div><div class="lg-section"><h3>기간</h3><p>${escapeHtml(e.first_at||'—')}</p><p>${escapeHtml(e.last_at||'—')}</p></div>${Object.keys(e.qualifiers||{}).length?`<div class="lg-section"><h3>한정자</h3>${keyRows(e.qualifiers)}</div>`:''}`;
  }
}

function renderChecks(container,values,selected,kind){
  container.replaceChildren();for(const [value,count] of values){const label=document.createElement('label');label.innerHTML=`<input type="checkbox" checked value="${escapeHtml(value)}" data-lg-filter-kind="${kind}"><span class="lg-check-label">${escapeHtml(value)}</span><b>${fmt(count)}</b>`;container.appendChild(label);}
  selected.clear();values.forEach(([v])=>selected.add(v));
}

function displaySource(){
  if(state.mode!=='ontology'||els.showEmpty.checked)return state.source;
  const edges=state.source.edges.filter((edge)=>edge.witnesses>0);const connected=new Set();edges.forEach((edge)=>{connected.add(edge.source);connected.add(edge.target);});
  const nodes=state.source.nodes.filter((node)=>node.schema_kind==='entity_type'||connected.has(node.id));
  return {...state.source,nodes,edges};
}

function renderFilters(){
  const source=displaySource();const types=new Map();const predicates=new Map();source.nodes.forEach((n)=>types.set(n.type,(types.get(n.type)||0)+1));source.edges.forEach((e)=>predicates.set(e.predicate,(predicates.get(e.predicate)||0)+1));
  renderChecks(els.typeFilters,[...types].sort(),state.typeSet,'type');renderChecks(els.predicateFilters,[...predicates].sort(),state.predicateSet,'predicate');
  els.nodeCount.textContent=fmt(source.nodes.length);els.edgeCount.textContent=fmt(source.edges.length);
}

function renderNodeList(){
  const query=String(els.nodeSearch.value||'').trim().toLowerCase();
  const source=displaySource();const nodes=source.nodes.filter((node)=>!query||`${node.label} ${node.type} ${node.id} ${JSON.stringify(node.keys)}`.toLowerCase().includes(query)).sort((a,b)=>`${a.type}|${a.label}|${a.id}`.localeCompare(`${b.type}|${b.label}|${b.id}`));
  els.nodeListCount.textContent=query?`${fmt(nodes.length)}/${fmt(source.nodes.length)}`:fmt(nodes.length);
  els.nodeList.innerHTML=nodes.map((node)=>{const context=node.schema_kind==='claim_shape'?`${node.id.split(':')[1]} · ${node.type}`:node.type;return `<button type="button" class="lg-node-item" data-lg-node-pick="${escapeHtml(node.id)}" aria-current="${String(node.id===state.focusNodeId)}" title="${escapeHtml(node.label)}에서 서브그래프 시작"><i style="--node:${typeColor(node.type)}"></i><span>${escapeHtml(node.label)}</span><small>${escapeHtml(context)}</small></button>`;}).join('')||'<p class="lg-empty-copy">일치하는 노드가 없습니다.</p>';
  els.clearFocus.hidden=!state.focusNodeId;
}

function startFromNode(id){
  const node=state.source.nodes.find((item)=>item.id===id);if(!node)return;
  if(state.mode==='lineage'&&node.id.startsWith('ledger-entity:v1:')){exploreEntity(node);return;}
  state.focusNodeId=node.id;state.manualPositions.clear();select('node',node);applyFilters();renderNodeList();
}

function applyFilters(){
  const filtered=filterGraph(displaySource(),{text:els.filterText.value,types:state.typeSet,predicates:state.predicateSet});state.visible=state.focusNodeId?subgraphFrom(filtered,state.focusNodeId,Number(els.hops.value)||20):filtered;layoutVisible();
  const focus=state.source.nodes.find((node)=>node.id===state.focusNodeId);els.summary.textContent=`표시 ${fmt(state.visible.nodes.length)} nodes · ${fmt(state.visible.edges.length)} edges${focus?` · ${focus.label}에서 시작`:''}`;fit();
}

function renderGraph(){
  state.focusNodeId=null;renderFilters();renderNodeList();const shown=displaySource();state.visible=filterGraph(shown,{types:state.typeSet,predicates:state.predicateSet});layoutVisible();
  els.overlay.hidden=state.source.nodes.length>0;els.status.textContent=state.source.state==='ready'?(state.mode==='ontology'?'구조 연결됨':'원장 연결됨'):'데이터 없음';
  els.summary.textContent=state.mode==='ontology'?`${fmt(shown.nodes.length)} nodes · ${fmt(shown.edges.length)} predicates · ${fmt(state.source.cost.atoms_counted)} atoms`:`${fmt(state.source.nodes.length)} nodes · ${fmt(state.source.edges.length)} edges · ${state.source.walk.hops_reached||0}/${state.source.walk.hops_requested||0} hops`;
  if(state.mode==='ontology'){
    const drift=(state.source.drift.undeclared_edge_ids||[]).length+(state.source.drift.undeclared_node_ids||[]).length;
    els.foot.textContent=`${state.source.cost.exact?'정확 집계':'부분 집계'} · ${fmt(state.source.cost.census_ms)} ms · 선언 밖 구조 ${fmt(drift)}건 · 노드를 끌어 위치 조절`;
    state.selected=null;renderDetail();fit();return;
  }
  const cuts=Object.entries(state.source.truncated).filter(([k,v])=>k!=='reason'&&v).map(([k])=>k);
  els.foot.textContent=cuts.length?`절단됨: ${cuts.join(' · ')} · ${state.source.truncated.reason||'표시 상한 도달'}`:`전체 응답 · ${state.source.walk.direction||'subject_to_object'} · ${state.source.generatedAt||''}`;
  state.selected=null;renderDetail();fit();
}

async function loadInstanceGraph(endpoint, selection, urlState){
  state.mode='lineage';paintMode();
  state.aborter?.abort();state.aborter=new AbortController();const mine=++state.request;
  els.status.textContent='조회 중';els.overlay.hidden=false;els.overlay.innerHTML='<strong>개체 탐색 중</strong><span>선택한 개체의 주장과 관계를 읽고 있습니다.</span>';
  try{const response=await fetch(endpoint,{signal:state.aborter.signal});const body=await response.json();if(mine!==state.request)return;if(!response.ok)throw new Error(body?.detail?.message||body?.detail||`HTTP ${response.status}`);state.source=readGraph(body);state.manualPositions.clear();els.nodeSearch.value='';els.filterText.value='';if(selection?.type)entityCatalog?.setType(selection.type);const url=new URL(location.href);url.searchParams.set('view','lineage');url.searchParams.delete('lot');url.searchParams.delete('entity');url.searchParams.delete('type');Object.entries(urlState||{}).forEach(([key,value])=>url.searchParams.set(key,value));url.searchParams.set('hops',els.hops.value);history.replaceState({},'',url);renderGraph();}
  catch(error){if(error.name==='AbortError'||mine!==state.request)return;els.status.textContent='조회 실패';els.overlay.hidden=false;els.overlay.innerHTML=`<strong>그래프를 불러오지 못했습니다</strong><span>${escapeHtml(error.message)}</span>`;}
}

function exploreEntity(entity){
  const id=String(entity?.id||entity||'').trim();if(!id)return;
  const params=new URLSearchParams({id,hops:els.hops.value,node_limit:'400',edge_limit:'1200'});
  const urlState={entity:id};if(entity?.type)urlState.type=entity.type;
  return loadInstanceGraph(`${API_BASE}/api/ledger/explore_entity?${params}`,entity,urlState);
}

function exploreLot(lotValue){
  const lot=String(lotValue||'').trim();if(!lot)return;
  const params=new URLSearchParams({lot,hops:els.hops.value,node_limit:'400',edge_limit:'1200'});
  return loadInstanceGraph(`${API_BASE}/api/ledger/explore?${params}`,{type:'Lot',label:lot},{lot});
}

function paintMode(){
  els.modeButtons.forEach((button)=>button.setAttribute('aria-pressed',String(button.dataset.lgMode===state.mode)));
  els.form.hidden=state.mode!=='lineage';
  els.showEmpty.parentElement.hidden=state.mode!=='ontology';
  els.nodeListLabel.textContent=state.mode==='ontology'?'ONTOLOGY NODES':'GRAPH NODES';
  els.filterText.placeholder=state.mode==='ontology'?'개체, 술어, 값 종류':'개체, 주장, 관계';
  entityCatalog?.setVisible(state.mode==='lineage');
}

async function loadOntology(){
  state.mode='ontology';paintMode();state.aborter?.abort();state.aborter=new AbortController();const mine=++state.request;
  els.status.textContent='구조 집계 중';els.overlay.hidden=false;els.overlay.innerHTML='<strong>Ontology 불러오는 중</strong><span>선언과 실제 원자 흐름을 합쳐 읽고 있습니다.</span>';
  try{const response=await fetch(`${API_BASE}/api/ledger/structure`,{signal:state.aborter.signal});const body=await response.json();if(mine!==state.request)return;if(!response.ok)throw new Error(body?.detail?.message||body?.detail||`HTTP ${response.status}`);state.source=readStructure(body);state.manualPositions.clear();els.nodeSearch.value='';els.filterText.value='';const url=new URL(location.href);url.searchParams.set('view','ontology');url.searchParams.delete('lot');url.searchParams.delete('entity');url.searchParams.delete('type');history.replaceState({},'',url);renderGraph();}
  catch(error){if(error.name==='AbortError'||mine!==state.request)return;els.status.textContent='조회 실패';els.overlay.hidden=false;els.overlay.innerHTML=`<strong>구조를 불러오지 못했습니다</strong><span>${escapeHtml(error.message)}</span>`;}
}

function enterInstances(){
  state.request+=1;state.aborter?.abort();state.aborter=null;state.mode='lineage';paintMode();state.source=readGraph(null);state.manualPositions.clear();els.nodeSearch.value='';els.filterText.value='';renderGraph();els.status.textContent='개체를 선택하세요';els.overlay.hidden=false;els.overlay.innerHTML='<strong>Instances</strong><span>오른쪽 전체 개체 목록에서 항목을 고르면 그 개체의 서브그래프를 엽니다.</span>';els.entityQuery.focus();
}

els.form.addEventListener('submit',(event)=>{event.preventDefault();entityCatalog?.searchNow();});
els.modeButtons.forEach((button)=>button.addEventListener('click',()=>{if(button.dataset.lgMode==='ontology')loadOntology();else enterInstances();}));
els.filterText.addEventListener('input',applyFilters);
els.nodeSearch.addEventListener('input',renderNodeList);
els.nodeList.addEventListener('click',(event)=>{const button=event.target.closest('[data-lg-node-pick]');if(button)startFromNode(button.dataset.lgNodePick);});
els.clearFocus.addEventListener('click',()=>{state.focusNodeId=null;state.manualPositions.clear();applyFilters();renderNodeList();});
els.showEmpty.addEventListener('change',()=>{if(state.mode==='ontology'){state.manualPositions.clear();renderGraph();}});
document.addEventListener('change',(event)=>{const input=event.target.closest('[data-lg-filter-kind]');if(!input)return;const set=input.dataset.lgFilterKind==='type'?state.typeSet:state.predicateSet;input.checked?set.add(input.value):set.delete(input.value);applyFilters();});
els.fit.addEventListener('click',fit);document.querySelectorAll('[data-lg-zoom]').forEach((button)=>button.addEventListener('click',()=>{state.view.scale=Math.max(.12,Math.min(3,state.view.scale*(button.dataset.lgZoom==='in'?1.2:1/1.2)));draw();}));
els.canvas.addEventListener('mousedown',(event)=>{const node=nodeAt(event.offsetX,event.offsetY);if(node){const point=state.positions.get(node.id);state.drag={kind:'node',nodeId:node.id,x:event.clientX,y:event.clientY,px:point.x,py:point.y,moved:false};els.canvas.style.cursor='move';}else state.drag={kind:'view',x:event.clientX,y:event.clientY,tx:state.view.tx,ty:state.view.ty,moved:false};});
window.addEventListener('mousemove',(event)=>{if(!state.drag)return;const dx=event.clientX-state.drag.x;const dy=event.clientY-state.drag.y;if(Math.hypot(dx,dy)>3)state.drag.moved=true;if(state.drag.kind==='node'){const point={x:state.drag.px+dx/state.view.scale,y:state.drag.py+dy/state.view.scale,depth:state.positions.get(state.drag.nodeId)?.depth??0};state.positions.set(state.drag.nodeId,point);state.manualPositions.set(state.drag.nodeId,{...point});}else{state.view.tx=state.drag.tx+dx;state.view.ty=state.drag.ty+dy;}draw();});
window.addEventListener('mouseup',(event)=>{if(!state.drag)return;const moved=state.drag.moved;state.drag=null;els.canvas.style.cursor='grab';if(!moved){const rect=els.canvas.getBoundingClientRect();const x=event.clientX-rect.left;const y=event.clientY-rect.top;const node=nodeAt(x,y);if(node)select('node',node);else{const edge=edgeAt(x,y);if(edge)select('edge',edge);}}});
els.canvas.addEventListener('mousemove',(event)=>{if(state.drag)return;const hit=nodeAt(event.offsetX,event.offsetY);const id=hit?.id||null;if(id!==state.hoverId){state.hoverId=id;els.canvas.style.cursor=hit?'move':'grab';draw();}});
els.canvas.addEventListener('dblclick',(event)=>{const node=nodeAt(event.offsetX,event.offsetY);if(node?.id.startsWith('ledger-entity:v1:'))exploreEntity(node);});
els.canvas.addEventListener('wheel',(event)=>{event.preventDefault();const next=Math.max(.12,Math.min(3,state.view.scale*(event.deltaY<0?1.14:1/1.14)));const ratio=next/state.view.scale;state.view.tx=event.offsetX-(event.offsetX-state.view.tx)*ratio;state.view.ty=event.offsetY-(event.offsetY-state.view.ty)*ratio;state.view.scale=next;draw();},{passive:false});

initTheme();new ResizeObserver(resizeCanvas).observe(els.wrap);resizeCanvas();
entityCatalog=createEntityCatalog({apiBase:API_BASE,typeSelect:els.entityType,queryInput:els.entityQuery,section:els.catalog,listElement:els.catalogList,countElement:els.catalogCount,statusElement:els.catalogStatus,moreButton:els.catalogMore,onPick:exploreEntity});
const query=new URLSearchParams(location.search);if(query.get('hops'))els.hops.value=query.get('hops');if(query.get('type'))entityCatalog.setType(query.get('type'));
if(query.get('entity'))exploreEntity({id:query.get('entity'),type:query.get('type')||undefined});else if(query.get('lot'))exploreLot(query.get('lot'));else if(query.get('view')==='lineage')enterInstances();else loadOntology();
