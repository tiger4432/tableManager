const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-CtEgmCQz.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-9BqUObJc.js";import{n as e}from"./absent-DJDVnjis.js";import{f as t,i as n,n as r,r as i,t as a,u as o}from"./disabled_reason-BP_E0n0W.js";import{n as s,t as c}from"./layered_graph-CRAuzeQO.js";import{A as l,D as u,E as d,F as f,I as p,L as m,M as h,N as g,O as _,P as v,R as y,T as b,c as ee,j as te,k as x,l as S,n as C,o as w,p as T,s as ne,v as E,w as D,z as O}from"./api-trXjkqxC.js";import{t as k}from"./preload-helper-zJ_50EbN.js";var A=`data-wk-styles`,j=`
.wk-form { display: flex; flex-direction: column; gap: 10px;
  font-family: 'Outfit', system-ui, sans-serif; font-size: 15px; color: var(--text, #111); }
.wk-field { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px;
  background: var(--bg-panel, transparent); border: 1px solid var(--border, #d4d4d8);
  border-radius: 8px; }
.wk-label { font-size: 0.72rem; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--text-dim, #71717a); }
.wk-note { font-size: 0.78rem; color: var(--text-dim, #71717a); }

.wk-select, .wk-input, .wk-go, .wk-check { min-height: 44px; box-sizing: border-box;
  font: inherit; }
.wk-select, .wk-input { width: 100%; padding: 0 8px; color: var(--text, #111);
  background: var(--bg, #fff); border: 1px solid var(--border, #d4d4d8); border-radius: 6px; }
.wk-keyrow { display: flex; align-items: center; gap: 8px; min-height: 44px; }
.wk-keyname { flex: none; width: 8.5em; font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem; color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-check { display: flex; align-items: center; gap: 8px; padding: 0 4px; border-radius: 6px;
  font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
.wk-check.is-on { background: var(--accent-soft, rgba(37, 99, 235, 0.10)); }
.wk-check input[type="checkbox"] { width: 22px; height: 22px; flex: none; }
/* 🔴 고르는 목록은 «폭»을 씁니다. 높이 44 는 손가락이라 그대로이고, 한 줄에 하나씩 세우는
   것만 그만둡니다 — 실측(480px 틀): 폼 1,623px 중 1,214px 가 체크박스 23줄이었습니다.
   🔴 칸은 «자기 이름만큼» 자랍니다(flex 0 1 auto) — 고정 폭으로 나누면 긴 이름이 잘리고,
   잘린 이름은 읽을 방법이 없습니다(이 폼에 hover 가 없습니다 — 휴대폰입니다). 최소 9.5em 은
   손가락이 옆 칸을 안 누르게 하는 바닥이고, 화면보다 긴 이름만 마지막 수단으로 잘립니다. */
.wk-checks { display: flex; flex-flow: row wrap; gap: var(--space-1) var(--space-2); }
.wk-check { flex: 0 1 auto; min-width: 9.5em; max-width: 100%; }
.wk-check > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Layout A (lead 2b5819e1d): the form is a rail, the result its own part. The page seats the two;
   each scrolls inside itself, and Walk stays in the rail's foot. */
.wk-rail { display: flex; flex-direction: column; min-height: 0; background: var(--bg-surface);
  border-right: 1px solid var(--border); }
.wk-rail > .wk-form { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: var(--space-4);
  gap: var(--space-5); }
/* In the rail a section is a heading and its controls, not a boxed card (the layout A mockup). */
.wk-rail .wk-field { gap: var(--space-2); padding: 0; background: transparent; border: 0; }
.wk-rail-foot { flex: none; padding: var(--space-3) var(--space-4); border-top: 1px solid var(--border);
  background: var(--bg-surface); }
.wk-main { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; min-height: 0;
  overflow: auto; padding: var(--space-4) var(--space-5); }
.wk-mainhead { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3) var(--space-4); }
.wk-title { font-size: 17px; font-weight: 600; overflow-wrap: anywhere; }
.wk-mainhead > .wk-views { margin-left: auto; }
/* A name above its control: key, step and pick cells. */
.wk-cell { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.wk-cell > .wk-keyname { width: auto; }
.wk-cell-row { flex-direction: row; align-items: center; gap: var(--space-3); }
.wk-cell-row > .wk-keyname { flex: none; width: 4.5em; }
.wk-keys, .wk-steps { display: grid; gap: var(--space-2); }
.wk-keys { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.wk-steps { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.wk-sub { display: flex; flex-direction: column; gap: var(--space-1); }
/* Collect: the picked types are chips (× takes one out); the rest are behind one + Type dropdown. */
.wk-chips { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.wk-chip, .wk-add { min-height: 44px; padding: 0 var(--space-4); border-radius: 999px; font: inherit;
  font-size: 14px; cursor: pointer; }
.wk-chip { color: var(--accent); background: var(--accent-weak); border: 1px solid var(--accent); }
.wk-add { color: var(--text-dim); background: var(--bg-surface); border: 1px dashed var(--border-strong); }
.wk-routes-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3); }
.wk-route { display: flex; flex-direction: column; gap: var(--space-2); margin: 0 0 var(--space-2);
  padding: var(--space-2); border: 1px solid var(--border); border-radius: 8px; }
.wk-route.is-on { border-color: var(--accent); background: var(--accent-weak); }
/* Follow: one folded line saying what is picked; opened, today's check list. */
.wk-fold { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
  width: 100%; min-height: 44px; padding: 0 var(--space-3); font: inherit; font-size: 14px; text-align: left;
  color: var(--text); background: var(--bg-header); border: 1px solid var(--border); border-radius: 6px;
  cursor: pointer; }
.wk-foldtext { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.wk-go { width: 100%; border: 0; border-radius: 8px;
  background: var(--accent, #2563eb); color: #fff; font-weight: 600; }
.wk-go[disabled] { opacity: 0.45; }

.wk-result { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px;
  background: var(--bg-panel, transparent); border: 1px solid var(--border, #d4d4d8);
  border-radius: 8px; }
.wk-counts { font-weight: 600; }
/* 경로 — 누를 수 있는 것이므로 button 이고, 그래서 키보드로도 닿습니다. */
.wk-path { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; width: 100%;
  text-align: left; min-height: 44px; padding: 8px 10px; margin: 0;
  border: 0; border-radius: 6px; cursor: pointer;
  background: transparent; color: inherit; font: inherit; }
.wk-path:hover { background: var(--accent-soft, rgba(37, 99, 235, 0.10)); }
.wk-pathto { font-weight: 700; grid-row: 1 / span 2; align-self: center; }
.wk-pathchain { font-size: 0.86rem; }
.wk-pathmeta { font-size: 0.78rem; color: var(--text-dim, #71717a); }
/* A route's self-loops, as chips under its row: off by default (lead 5d5b8d750). */
.wk-loops { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-loopchip { min-height: 44px; padding: 0 12px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--line, #e4e4e7); background: var(--surface, #fff); color: var(--text-dim, #71717a);
  font: inherit; font-size: 0.82rem; }
.wk-loopchip.is-on { border-color: var(--accent, #2563eb); color: var(--text, #111); font-weight: 600; }
/* 타입 분포 — 「무엇이 몇 개 왔나」. 물어본 타입은 표시가 다릅니다. */
.wk-dist { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0; }
.wk-distlabel { font-size: 0.78rem; color: var(--text-dim, #71717a); }
.wk-distchip { display: inline-flex; gap: 4px; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--line, #e4e4e7); font-size: 0.82rem; }
.wk-distchip.is-asked { border-color: var(--accent, #2563eb); font-weight: 600; }
/* 결과 표. 구획마다 «자기 키 컬럼»이라 표가 여럿입니다. */
.wk-sec { margin: 10px 0 14px; }
.wk-sechead { font-weight: 700; font-size: 0.86rem; margin: 0 0 4px; }
.wk-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; display: block;
  overflow-x: auto; white-space: nowrap; }
.wk-table th, .wk-table td { border-bottom: 1px solid var(--line, #e4e4e7);
  padding: 5px 8px; text-align: left; }
.wk-table th { font-weight: 600; color: var(--text-dim, #71717a); position: sticky; top: 0;
  background: var(--surface, #fff); }
/* 숫자는 «자릿수»로 섭니다 — x·y 가 세로로 안 맞으면 좌표를 못 읽습니다. */
.wk-table td.wk-num { text-align: right; font-variant-numeric: tabular-nums; }
/* id 는 길고 «마지막»입니다. 읽는 것이 아니라 «집는» 칸이라 폭을 안 뺏습니다. */
.wk-table td.wk-id { font-family: var(--font-mono, ui-monospace, monospace); font-size: 0.74rem;
  color: var(--text-dim, #71717a); max-width: 22ch; overflow: hidden; text-overflow: ellipsis; }
.wk-walk, .wk-trunc { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }
.wk-walk { color: var(--text-dim, #71717a); }
.wk-trunc { color: var(--warn, #b45309); }
.wk-fail { color: var(--danger, #dc2626); font-size: 0.86rem; }
.wk-row { display: flex; gap: 8px; align-items: baseline; padding: 3px 0;
  border-top: 1px solid var(--border, #d4d4d8); font-size: 0.82rem; }
.wk-rowtype { flex: none; width: 7.5em; font-family: 'JetBrains Mono', monospace;
  font-size: 0.74rem; color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-rowlabel { overflow-wrap: anywhere; }

/* Table | Graph — which view of the walk the page shows (lead c9bf53033). */
.wk-views { display: flex; gap: 6.8px; }
.wk-view { min-height: 44px; padding: 0 13.6px; font: inherit; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.wk-view.is-on { border-color: var(--accent); color: var(--accent); font-weight: 600; }

/* Subgraph viewer. Corners 0, hairlines, colours from the roles in tokens.css only. A type's colour is a
   palette token (--cat-1..9 in tokens.css, TYPE_COLOURS of them) by its declaration index. A declaration
   with more types than tokens repeats a colour; the legend names them. */
.sg-view { display: flex; flex-direction: column; gap: 6.8px; padding: 10.2px 13.6px;
  border: 1px solid var(--border); background: var(--bg-surface); color: var(--text); }
.sg-counts { font-weight: 600; }
.sg-note { font-size: var(--fs-meta); color: var(--text-dim); }
.sg-fail { color: var(--danger); }
.sg-trunc { font-family: 'JetBrains Mono', monospace; font-size: var(--fs-meta); color: var(--warning); }
.sg-type-0 { --sg-c: var(--cat-1); }
.sg-type-1 { --sg-c: var(--cat-2); }
.sg-type-2 { --sg-c: var(--cat-3); }
.sg-type-3 { --sg-c: var(--cat-4); }
.sg-type-4 { --sg-c: var(--cat-5); }
.sg-type-5 { --sg-c: var(--cat-6); }
.sg-type-6 { --sg-c: var(--cat-7); }
.sg-type-7 { --sg-c: var(--cat-8); }
.sg-type-8 { --sg-c: var(--cat-9); }
.sg-legend { display: flex; flex-wrap: wrap; gap: 6.8px; }
.sg-chip { display: inline-flex; align-items: center; gap: 6.8px; padding: 3.4px 6.8px;
  border: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; font-size: var(--fs-label); }
.sg-swatch { width: 10.2px; height: 10.2px; border-radius: 50%; background: var(--sg-c); }
.sg-swatch.is-static { border-radius: 0; }
.sg-box { max-height: var(--graph-max-height); overflow: auto; border: 1px solid var(--border);
  background: var(--bg-inset); }
.sg-graph { display: block; }
.sg-edge { stroke: var(--border-strong); stroke-width: 1; }
.sg-node circle, .sg-node rect { fill: var(--sg-c); stroke: var(--bg-surface); stroke-width: 1.5; cursor: pointer; }
/* The step a node came from is its border (lead f6fc6ba66): step 1 the plain halo, later steps dashed. */
.sg-step-2 > circle, .sg-step-2 > rect { stroke: var(--text); stroke-dasharray: 3.4 1.7; }
.sg-step-3 > circle, .sg-step-3 > rect { stroke: var(--text); stroke-dasharray: 1.7 1.7; }
.sg-step-4 > circle, .sg-step-4 > rect { stroke: var(--text); stroke-dasharray: 6.8 1.7 1.7 1.7; }
.sg-node.is-seed circle, .sg-node.is-seed rect { stroke: var(--accent); stroke-width: 2; stroke-dasharray: none; }
.sg-node.is-marked circle, .sg-node.is-marked rect { stroke: var(--accent); stroke-width: 3.4; stroke-dasharray: none; }
.sg-node.is-selected circle, .sg-node.is-selected rect { stroke: var(--text); stroke-width: 3; }
.sg-bundle text { fill: var(--accent); font-size: var(--fs-label); font-weight: 600; cursor: pointer; }
.sg-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6.8px; }
.sg-continue { min-height: 44px; padding: 0 13.6px; font: inherit; color: var(--accent-contrast);
  background: var(--accent); border: 1px solid var(--accent); border-radius: 0; cursor: pointer; }
.sg-continue[disabled] { opacity: 0.5; cursor: not-allowed; }
.sg-node text { fill: var(--text); font-size: var(--fs-tag); cursor: pointer; }
.sg-facts { display: flex; flex-direction: column; gap: 3.4px; }
.sg-facts-head { font-weight: 600; }
.sg-fact { font-family: 'JetBrains Mono', monospace; font-size: var(--fs-label); overflow-wrap: anywhere; }
`;function M(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${A}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(A,``),t.textContent=j,(e.head||e.documentElement).appendChild(t),!0}function N(e){return e==null?``:String(e)}function P(e){return e!==``&&Number.isFinite(Number(e))}function F(e){let t=new Map;for(let n of e||[]){let e=n&&n.qualifiers;if(!e||typeof e!=`object`)continue;for(let e of[n.target,n.source])(!e||!t.has(e))&&t.set(e,t.get(e)||{});let r=t.get(n.target)||{};Object.assign(r,e),t.set(n.target,r)}return t}function I(e,t){let n=[];for(let r of e||[])for(let e of Object.keys(t&&t.get(r.id)||{}))n.includes(e)||n.push(e);return n}function re(e,t,n=[],r=200){let i=e&&e.nodes||[],a=i.slice(0,r),o=F(e&&e.edges||[]),s=[],c=h(e),l=d(n);for(let[e,n]of f(a)){let r=m(t,e,I(n,o),void 0,l);s.push({type:e,heading:v(e,n.length),columns:r,rows:n.map(e=>({id:e.id,cells:r.map(t=>{let n=N(b(t,e,o.get(e.id)||{},c.get(e.type)));return{text:n,kind:t.kind,numeric:P(n)}})}))})}return{sections:s,shown:a.length,hidden:Math.max(0,i.length-a.length)}}var L=Object.freeze({margin:20.4,gapX:238,gapY:27.2,r:6.8,labelDx:10.2}),R=L.margin,z=L.gapX,B=L.labelDx;function V(e){let t=[],n=[];for(let[r,i]of e||[])i===O.CASE?t.push(r):i===O.CONTROL&&n.push(r);return{positive:t,negative:n}}function H(e,t){let n=p(t),r=(t||[]).map(e=>D(e&&e.type)),i=new Map(r.map((e,t)=>[e,t])),a=e=>{let t=e&&e.results||[];return t[t.length-1]||{}},o=new Map;(e||[]).forEach((e,t)=>{for(let n of a(e).bundles||[])o.has(n.node)||o.set(n.node,[]),o.get(n.node).push({...n,step:t})});let c=new Map,l=new Map,d=[],f=[],m=0;(e||[]).forEach((e,t)=>{let r=(e.seeds||[]).map(e=>l.get(e)).filter(Boolean).map(e=>e.layer),a=t===0||!r.length?0:Math.max(...r);for(let r of e.results||[])for(let e of Array.isArray(r.nodes)?r.nodes:[]){let r=D(e.type);if(i.has(r)||i.set(r,i.size),l.has(e.id))continue;if(!Number.isFinite(e.depth)){m+=1;continue}let u=a+e.depth,p=c.get(u)||0,h={id:e.id,type:r,label:e.label||e.id,depth:e.depth,layer:u,step:t+1,...s(L,u,p),static:n.has(r),colour:i.get(r)%9,keys:e.keys||{},attributes:e.attributes||{}};l.set(e.id,h),d.push(h),p+=1;for(let t of o.get(e.id)||[])f.push({step:t.step,node:t.node,predicate:t.predicate,direction:t.direction,farType:D(t.far_type),count:t.count,key:`${t.node}|${t.predicate}|${t.direction}`,x:h.x+B,y:s(L,u,p).y}),p+=1;c.set(u,p)}});let h=[],g=new Set,_=new Set,v=[];(e||[]).forEach((e,t)=>{for(let t of e.results||[])for(let e of Array.isArray(t.edges)?t.edges:[]){if(g.has(e.id))continue;let t=l.get(e.source),n=l.get(e.target);if(!t||!n){_.add(e.id);continue}g.add(e.id),_.delete(e.id),h.push({id:e.id,source:e.source,target:e.target,predicate:e.predicate_label||e.predicate||``,occurredAt:e.occurred_at||``,x1:t.x,y1:t.y,x2:n.x,y2:n.y})}let n=a(e);n.cut&&v.push({step:t+1,budgets:u(n.truncatedAxes,n.limits)})});let y=new Map;for(let e of d)y.set(e.type,(y.get(e.type)||0)+1);return{nodes:d,edges:h,chips:f,legend:[...y.entries()].sort((e,t)=>i.get(e[0])-i.get(t[0])).map(([e,t])=>({type:e,count:t,colour:i.get(e)%9,static:n.has(e)})),unplaced:m,loose:_.size,cut:v,width:R*2+Math.max(0,...d.map(e=>e.x))+z,height:R*2+Math.max(0,...d.map(e=>e.y),...f.map(e=>e.y))}}function U(e,t){let n=e.nodes.find(e=>e.id===t);if(!n)return null;let r=new Map(e.nodes.map(e=>[e.id,e.label]));return{node:n,edges:e.edges.filter(e=>e.source===t||e.target===t).map(e=>({out:e.source===t,predicate:e.predicate,other:r.get(e.source===t?e.target:e.source),occurredAt:e.occurredAt}))}}var W=class{constructor(e,t={}){if(!e)throw Error(`SubgraphView needs a mount element`);if(!t.markings||!Array.isArray(t.chain)||!t.chain.length)throw Error(`SubgraphView needs a marking store and a chain of marking names`);this.mount=e,this.doc=t.doc||e.ownerDocument,this.walk=t.walk,this.entities=t.entities||(()=>[]),this.markings=t.markings,this.chain=t.chain.slice(),this.fanoutLimit=Number.isFinite(t.fanoutLimit)?t.fanoutLimit:20,M(this.doc),this.root=this.doc.createElement(`div`),this.root.className=`sg-view`,this.mount.appendChild(this.root),this.state=`idle`,this.reason=``,this.steps=[],this.layout=null,this.selected=null,this.asked=``;for(let e of this.chain)this.markings.subscribe(e,()=>this._restyle())}writes(){return this.chain[this.steps.length]||``}async show(e={}){let t=JSON.stringify(this.markings.entries(this.chain[0]));e.reuse&&t===this.asked&&this.state===`done`||(this.asked=t,this.steps=[],this.layout=null,this.selected=null,await this._step(this.chain[0]))}async continueWalk(){let e=this.writes();!e||this.state!==`done`||await this._step(e)}async _step(e){let t=V(this.markings.entries(e));if(!t.positive.length){this.steps.length||(this.state=`empty`,this.render());return}let n={marking:e,seeds:[...t.positive,...t.negative],positive:t.positive,negative:t.negative,expand:[],results:[]};await this._ask(n,[],e=>[...this.steps,{...n,results:[e]}])}async expandBundle(e,t){let n=this.steps[e];if(!n||this.state!==`done`||n.expand.includes(t))return;let r=[...n.expand,t];await this._ask(n,r,t=>this.steps.map((n,i)=>i===e?{...n,expand:r,results:[...n.results,t]}:n))}async _ask(e,t,n){let r=this.steps;this.state=`running`,this.render();let i=await this.walk({positive:e.positive,negative:e.negative,fanout_limit:this.fanoutLimit,expand:t});this.steps===r&&(i&&i.ok?(this.steps=n(i),this.layout=H(this.steps,this.entities()),this.state=`done`):(this.state=`failed`,this.reason=i&&i.message||``),this.render())}_el(e,t,n){let r=this.doc.createElement(e);return t&&(r.className=t),n!==void 0&&(r.textContent=String(n)),r}_classOf(e){let t=this.writes(),n=this.steps.some(t=>t.seeds.includes(e.id));return`sg-node sg-type-${e.colour} sg-step-${e.step}`+(e.static?` is-static`:``)+(n?` is-seed`:``)+(t&&this.markings.signOf(t,e.id)!==O.ABSENT?` is-marked`:``)+(e.id===this.selected?` is-selected`:``)}render(){if(this.root.textContent=``,this._groups=new Map,this.continueButton=null,this.state===`empty`){this.root.appendChild(this._el(`div`,`sg-note`,`Nothing marked`));return}if(this.state===`failed`&&this.root.appendChild(this._el(`div`,`sg-fail`,`Failed · ${this.reason}`)),this.state===`running`&&this.root.appendChild(this._el(`div`,`sg-note`,`Walking`)),!this.layout)return;let e=this.layout;this.root.appendChild(this._el(`div`,`sg-counts`,`Nodes ${e.nodes.length} · Edges ${e.edges.length}`));for(let t of e.cut){let e=this.steps.length>1?`step ${t.step} · `:``;this.root.appendChild(this._el(`div`,`sg-trunc`,`Truncated · ${e}${t.budgets.join(` · `)}`))}e.unplaced&&this.root.appendChild(this._el(`div`,`sg-note`,`No depth · ${e.unplaced} nodes`)),e.loose&&this.root.appendChild(this._el(`div`,`sg-note`,`Not drawn · ${e.loose} edges`));let t=this._el(`div`,`sg-bar`),n=this._el(`div`,`sg-legend`);for(let t of e.legend){let e=this._el(`span`,`sg-chip sg-type-${t.colour}`);e.setAttribute(`data-type`,t.type),e.appendChild(this._el(`span`,`sg-swatch${t.static?` is-static`:``}`)),e.appendChild(this._el(`span`,``,`${t.type} ${t.count}`)),n.appendChild(e)}t.appendChild(n);let r=this._el(`button`,`sg-continue`,`Continue`);r.setAttribute(`type`,`button`),r.addEventListener&&r.addEventListener(`click`,()=>{this.continueWalk()}),this.continueButton=r,t.appendChild(r),this.root.appendChild(t);let{box:i,groups:a}=c(this.doc,{geometry:L,boxClass:`sg-box`,svgClass:`sg-graph`,width:e.width,height:e.height,edges:e.edges.map(e=>({x1:e.x1,y1:e.y1,x2:e.x2,y2:e.y2,attrs:{class:`sg-edge`,"data-predicate":e.predicate}})),nodes:e.nodes.map(e=>({id:e.id,x:e.x,y:e.y,label:e.label,shape:e.static?`rect`:`circle`,attrs:{class:this._classOf(e),"data-node":e.id,"data-depth":e.depth,"data-step":e.step},onPress:()=>this.press(e.id)})),texts:e.chips.map(e=>({x:e.x,y:e.y,text:`+${e.count} ${e.farType}`,attrs:{class:`sg-bundle`,"data-bundle":e.key,"data-step":e.step+1},onPress:()=>{this.expandBundle(e.step,e.key)}}))});for(let t of e.nodes)this._groups.set(t.id,{group:a.get(t.id),node:t});this.root.appendChild(i),this.factsBox=this._facts(),this.root.appendChild(this.factsBox),this._restyle()}_facts(){let e=this._el(`div`,`sg-facts`),t=this.layout&&this.selected?U(this.layout,this.selected):null;if(!t)return e;e.appendChild(this._el(`div`,`sg-facts-head`,`${t.node.label} · ${t.node.type}`));for(let[n,r]of[...Object.entries(t.node.keys),...Object.entries(t.node.attributes)])e.appendChild(this._el(`div`,`sg-fact`,`${n} ${r}`));for(let n of t.edges)e.appendChild(this._el(`div`,`sg-fact`,`${n.out?`→`:`←`} ${n.predicate} · ${n.other}${n.occurredAt?` · ${n.occurredAt}`:``}`));return e}_restyle(){for(let{group:e,node:t}of(this._groups||new Map).values())e.setAttribute(`class`,this._classOf(t));if(!this.continueButton)return;let e=this.writes();a(this.continueButton,e?this.markings.count(e)?``:`Mark a node`:`End of chain`)}press(e){this.select(e);let t=this.writes();t&&this.markings.toggle(t,e,O.CASE)}select(e){this.selected=e;let t=this._facts();this.factsBox&&this.factsBox.parentNode===this.root?(this.root.insertBefore(t,this.factsBox),this.root.removeChild(this.factsBox)):this.root.appendChild(t),this.factsBox=t,this._restyle()}},G=Object.freeze([`walk-start`,`walk-2`,`walk-3`,`walk-4`]),K=o,q=[`both`,`outgoing`,`incoming`],J=`default`,Y=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function X(o,s,c){let d=c||{},f=d.apiBase||``;M(o);let p=w({apiBase:f,fetchImpl:d.fetchImpl}),m={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,subjects:null,subjectsState:`idle`,subjectsReason:``,subjectsScanned:null,subjectsScanCut:!1,subjectsListCut:!1,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``,asked:null,view:`table`,loopsOn:new Map,followOpen:!1},h=e=>`${e.to}|${e.follow.slice().sort().join(`+`)}`,v=e=>m.loopsOn.get(h(e))||new Set,b=D,k=()=>m.decl&&m.decl.entities||[],A=e=>{let t=k().find(t=>t.type===e);return t&&t.keys||[]},j=Y(o,`div`,`wk-rail`),N=Y(o,`div`,`wk-main`),P=new y,F=Y(o,`div`,`wk-graph`),I=new W(F,{doc:o,walk:p,entities:k,markings:P,chain:G}),L=e=>{let t=Object.keys(m.keys||{}).length>0;P.replace(G[0],t?[[ne(m.type,m.keys),O.CASE]]:[]),I.show(e)},R=()=>m.decl&&m.decl.predicates||[],z=()=>R().map(e=>e.name),B=()=>_(g(R(),m.type,k()),z(),m.follow);function V(){if(!m.decl||!m.type||!m.collect.size)return[];let e=[];for(let t of m.collect)for(let n of T(m.decl,b(m.type),b(t)))e.push({...n,to:b(t)});return l(k(),e).sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function H(){let e={type:m.type,keys:m.keys};m.follow.size&&(e.follow=[...m.follow]),m.collect.size&&(e.collect=[...m.collect]),m.direction&&(e.direction=m.direction);let t=parseInt(m.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(m.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function U(){if(!m.type)return;if(m.view===`graph`){L();return}let e=H();m.run=`running`,m.result=null,m.reason=``,m.asked={...e,keys:{...e.keys}},Q();let t=await p(e);t&&t.ok?(m.run=`done`,m.result=t):(m.run=`failed`,m.reason=t&&t.message||`Unknown`),Q()}function X(e,t=`wk-field`){let n=Y(o,`div`,t);return n.append(Y(o,`div`,`wk-label`,e)),n}function Z(e,t,n=`wk-cell`){let r=Y(o,`label`,n);return r.append(Y(o,`span`,`wk-keyname`,e),t),r}function ie(e){let i=X(`Start`),a=Y(o,`select`,`wk-select`),s=Y(o,`option`,``,r);s.value=``,a.append(s);for(let e of k()){let t=Y(o,`option`,``,e.type);t.value=e.type,e.type===m.type&&(t.selected=!0),a.append(t)}if(a.addEventListener(`change`,()=>{m.type=a.value;let e=new Set(A(m.type));m.keys=Object.fromEntries(Object.entries(m.keys).filter(([t])=>e.has(t)));let t=new Set(g(R(),m.type,k()));m.follow=new Set([...m.follow].filter(e=>t.has(e))),m.result=null,m.run=`idle`,Q(),me()}),i.append(Z(`Type`,a,`wk-cell wk-cell-row`)),m.type){let e=X(`Pick a node`,`wk-sub`);if(m.subjectsState===`loading`)e.append(Y(o,`div`,`wk-note`,n));else if(m.subjectsState===`failed`)e.append(Y(o,`div`,`wk-fail`,`Node list · ${m.subjectsReason}`));else if(m.subjectsState===`ready`){let n=m.subjects||[];if(!n.length)e.append(Y(o,`div`,`wk-note`,m.subjectsScanCut?`Not every node read (up to ${m.subjectsScanned})`:`No node of this type in the ledger`));else{let r=Y(o,`select`,`wk-select`);r.append(Y(o,`option`,``,`— pick, or type the keys below —`)),n.forEach((e,t)=>{let n=Object.values(e.keys||{}).map(e=>String(e)).join(` · `),i=Y(o,`option`,``,e.count?`${n}  (${e.count})`:n);i.value=String(t),r.append(i)}),r.addEventListener(`change`,()=>{let e=n[Number(r.value)];e&&(m.keys={...e.keys},Q())}),e.append(r),m.subjectsListCut&&e.append(Y(o,`div`,`wk-note`,`${t(n.length,`node`)} listed · not all · type the keys below if missing`))}}i.append(e)}let c=A(m.type);m.type?c.length||i.append(Y(o,`div`,`wk-note`,`This type has no keys`)):i.append(Y(o,`div`,`wk-note`,`Pick a type for its keys`));let l=Y(o,`div`,`wk-keys`);for(let e of c){let t=Y(o,`input`,`wk-input`);t.type=`text`,t.value=m.keys[e]===void 0?``:m.keys[e],t.addEventListener(`input`,()=>{m.keys[e]=t.value}),l.append(Z(e,t))}c.length&&i.append(l),e.append(i)}function ae(t){let n=X(`Collect`),r=k().map(e=>e.type);if(!r.length){n.append(Y(o,`div`,`wk-note`,`No entity declared`)),t.append(n);return}let i=Y(o,`div`,`wk-chips`);for(let e of r.filter(e=>m.collect.has(e))){let t=Y(o,`button`,`wk-chip`,`${e} ×`);t.type=`button`,t.setAttribute(`data-collect`,e),t.setAttribute(`aria-label`,`Remove ${e}`),t.addEventListener(`click`,()=>{m.collect.delete(e),Q()}),i.append(t)}let a=r.filter(e=>!m.collect.has(e));if(a.length){let e=Y(o,`select`,`wk-add`);e.setAttribute(`aria-label`,`Add a type to collect`);let t=Y(o,`option`,``,`+ Type`);t.value=``,e.append(t);for(let t of a){let n=Y(o,`option`,``,t);n.value=t,e.append(n)}e.addEventListener(`change`,()=>{e.value&&(m.collect.add(e.value),Q())}),i.append(e)}n.append(i),m.collect.size||n.append(Y(o,`div`,`wk-note`,`${e} · ${J} · all`)),t.append(n)}function oe(e){if(!m.type||!m.collect.size)return;let n=V(),r=Y(o,`div`,`wk-field`),i=Y(o,`div`,`wk-routes-head`);i.append(Y(o,`span`,`wk-label`,`Route to ${[...m.collect].map(b).join(`, `)}`),Y(o,`span`,`wk-note`,t(n.length,`route`))),r.append(i),n.length||r.append(Y(o,`div`,`wk-note`,`No route from ${b(m.type)} to ${[...m.collect].map(b).join(` · `)}`));let a=(e,t)=>{let n=E(e,t);m.follow=new Set(x(z(),n.follow)),m.hops=String(n.hops),Q()},s=(e,t)=>e.size===t.size&&[...e].every(e=>t.has(e));for(let e of n){let n=E(e,v(e)),i=m.hops===String(n.hops)&&s(m.follow,new Set(x(z(),n.follow))),c=Y(o,`div`,`wk-route`+(i?` is-on`:``)),l=Y(o,`button`,`wk-path`);if(l.type=`button`,l.setAttribute(`aria-pressed`,i?`true`:`false`),l.append(Y(o,`span`,`wk-pathto`,`→ ${e.to}`)),l.append(Y(o,`span`,`wk-pathchain`,e.chain.join(` → `))),l.append(Y(o,`span`,`wk-pathmeta`,`${t(n.hops,`hop`)} · ${n.follow.join(`, `)}`)),l.addEventListener(`click`,()=>a(e,v(e))),c.append(l),e.loops.length){let t=Y(o,`div`,`wk-loops`);t.append(Y(o,`span`,`wk-note`,`self-loops`));for(let n of e.loops){let r=v(e).has(n.predicate),i=Y(o,`button`,`wk-loopchip`+(r?` is-on`:``),`↻ ${n.predicate}`);i.type=`button`,i.setAttribute(`aria-pressed`,r?`true`:`false`),i.title=`${n.at} → ${n.at}`,i.addEventListener(`click`,()=>{let t=new Set(v(e));r?t.delete(n.predicate):t.add(n.predicate),m.loopsOn.set(h(e),t),a(e,t)}),t.append(i)}c.append(t)}r.append(c)}e.append(r)}function se(e){let t=X(`Step`),n=Y(o,`div`,`wk-steps`),r=Y(o,`select`,`wk-select`);r.append(Y(o,`option`,``,J));for(let e of q){let t=Y(o,`option`,``,e);t.value=e,e===m.direction&&(t.selected=!0),r.append(t)}r.addEventListener(`change`,()=>{m.direction=r.value}),n.append(Z(`direction`,r));for(let[e,t,r,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=Y(o,`input`,`wk-input`);a.type=`number`,a.min=String(r),a.max=String(i),a.placeholder=J,a.value=m[t],a.addEventListener(`input`,()=>{m[t]=a.value}),n.append(Z(e,a))}t.append(n),e.append(t)}function ce(t){let n=B(),r=Y(o,`div`,`wk-field`);if(!n.length){r.append(Y(o,`div`,`wk-label`,`Follow`)),r.append(Y(o,`div`,`wk-note`,m.type?te(m.type):`No predicate declared`)),t.append(r);return}let i=m.follow.size?[...m.follow].map(b).join(`, `):J,a=Y(o,`button`,`wk-fold`);if(a.type=`button`,a.setAttribute(`aria-expanded`,m.followOpen?`true`:`false`),a.append(Y(o,`span`,`wk-foldtext`,`Follow · ${i}`),Y(o,`span`,`wk-foldmark`,m.followOpen?`▾`:`▸`)),a.addEventListener(`click`,()=>{m.followOpen=!m.followOpen,Q()}),r.append(a),m.followOpen){let t=Y(o,`div`,`wk-checks`);for(let e of n){let n=Y(o,`label`,`wk-check`+(m.follow.has(e)?` is-on`:``));n.setAttribute(`data-follow`,e);let r=Y(o,`input`);r.type=`checkbox`,r.checked=m.follow.has(e),r.addEventListener(`change`,()=>{m.follow.has(e)?m.follow.delete(e):m.follow.add(e),Q()}),n.append(r,Y(o,`span`,``,e)),t.append(n)}r.append(t),r.append(Y(o,`div`,`wk-note`,`${e} · ${J}`))}t.append(r)}function le(e){let t=Y(o,`button`,`wk-go`,m.run===`running`?K:`Walk`);t.type=`button`,a(t,m.run===`running`?K:m.type?``:C),t.addEventListener(`click`,U),e.append(t)}function ue(e,t){let n=re(t,k(),m.decl&&m.decl.predicates||[]);for(let t of n.sections){let n=Y(o,`div`,`wk-sec`);n.append(Y(o,`div`,`wk-sechead`,t.heading));let r=Y(o,`table`,`wk-table`),i=Y(o,`thead`),a=Y(o,`tr`);for(let e of t.columns)a.append(Y(o,`th`,``,e.name));i.append(a),r.append(i);let s=Y(o,`tbody`);for(let e of t.rows){let t=Y(o,`tr`);for(let n of e.cells){let e=Y(o,`td`,n.numeric?`wk-num`:``,n.text);n.kind===`id`&&(e.className=`wk-id`),t.append(e)}s.append(t)}r.append(s),n.append(r),e.append(n)}n.hidden&&e.append(Y(o,`div`,`wk-note`,`${n.hidden} more not drawn`))}function de(e){let t=Object.values(e.keys||{}).map(e=>String(e)).filter(e=>e).join(` · `),n=(e.collect||[]).map(b).join(`, `);return`${b(e.type)}${t?` `+t:``}${n?` → `+n:``}`}function fe(e){let t=Y(o,`div`,`wk-mainhead`),n=m.result;if(m.view===`table`&&m.run===`done`&&n&&m.asked){t.append(Y(o,`span`,`wk-title`,de(m.asked)));let e=(m.asked.collect||[]).map(b).join(`, `);t.append(Y(o,`span`,`wk-counts`,e?`Nodes ${n.nodes.length} (collect: ${e}) · Edges ${n.edges.length} (all)`:`Nodes ${n.nodes.length} · Edges ${n.edges.length}`))}let r=Y(o,`div`,`wk-views`);for(let[e,t]of[[`table`,`Table`],[`graph`,`Graph`]]){let n=Y(o,`button`,`wk-view`+(m.view===e?` is-on`:``),t);n.type=`button`,n.setAttribute(`data-view`,e),n.addEventListener(`click`,()=>{m.view=e,e===`graph`&&m.type&&L({reuse:!0}),Q()}),r.append(n)}t.append(r),e.append(t)}function pe(e){let n=Y(o,`div`,`wk-result`);if(m.run===`idle`)n.append(Y(o,`div`,`wk-note`,`No walk yet`));else if(m.run===`running`)n.append(Y(o,`div`,`wk-note`,K));else if(m.run===`failed`){let e=Y(o,`div`,`wk-fail`);e.append(Y(o,`b`,``,i),Y(o,`span`,``,` · `+m.reason)),n.append(e)}else if(m.result){let e=m.result;if(e.walk&&n.append(Y(o,`div`,`wk-walk`,`Asked ${t(e.walk.hops_requested,`hop`)} · reached ${t(e.walk.hops_reached,`hop`)} · ${e.walk.direction}`)),e.generatedAt&&n.append(Y(o,`div`,`wk-note`,`As of ${String(e.generatedAt)}`)),e.cut&&n.append(Y(o,`div`,`wk-trunc`,`Cut · ${u(e.truncatedAxes,e.limits).join(` · `)}`)),e.nodes.length){let t=new Map;for(let n of e.nodes){let e=n.type||`—`;t.set(e,(t.get(e)||0)+1)}let r=Y(o,`div`,`wk-dist`);r.append(Y(o,`span`,`wk-distlabel`,`Types`));for(let[e,n]of[...t.entries()].sort((e,t)=>t[1]-e[1])){let t=Y(o,`span`,`wk-distchip`+(m.collect.has(e)||m.collect.has(`${e}@1`)?` is-asked`:``));t.append(Y(o,`b`,``,e),Y(o,`span`,``,` ${n}`)),r.append(t)}n.append(r)}e.nodes.length||n.append(Y(o,`div`,`wk-note`,e.message||`No node reached`)),ue(n,e)}e.append(n)}function Q(){s.textContent=``,j.textContent=``,N.textContent=``;let e=Y(o,`div`,`wk-form`),t=Y(o,`div`,`wk-rail-foot`);if(m.declState===`loading`)e.append(Y(o,`div`,`wk-note`,`Declaration · ${n}`));else if(m.declState===`failed`){let n=Y(o,`div`,`wk-fail`);n.append(Y(o,`b`,``,`Declaration not read`),Y(o,`span`,``,` · `+m.declReason));let r=Y(o,`button`,`wk-go`,`Retry`);r.type=`button`,r.addEventListener(`click`,$),e.append(n),t.append(r)}else ie(e),ae(e),oe(e),se(e),ce(e),le(t),fe(N),m.view===`graph`?N.append(F):pe(N);j.append(e,t),s.append(j,N)}async function me(){if(!m.type){m.subjectsState=`idle`,m.subjects=null;return}let e=m.type;m.subjectsState=`loading`,m.subjects=null,Q();let t=await S({apiBase:f,fetchImpl:d.fetchImpl,type:e});m.type===e&&(t&&t.ok?(m.subjectsState=`ready`,m.subjects=t.nodes,m.subjectsScanned=t.scanned,m.subjectsScanCut=t.scanTruncated,m.subjectsListCut=t.valuesTruncated):(m.subjectsState=`failed`,m.subjectsReason=t&&t.message||`Unknown`),Q())}async function $(){m.declState=`loading`,Q();let e=await ee({apiBase:f,fetchImpl:d.fetchImpl});e&&e.ok?(m.decl=e,m.declState=`ready`):(m.declState=`failed`,m.declReason=e&&e.message||`Unknown`),Q()}return $(),{state:m,spec:H,fire:U,render:Q}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&k(async()=>{let{API_BASE:e}=await import(`./config-CtEgmCQz.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{X(document,e,{apiBase:t})})}