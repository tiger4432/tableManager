const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-CtEgmCQz.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-DOzbin0I.js";import{r as e}from"./absent-o9jpRT19.js";import{C as t,d as n,f as r,h as i,l as a,m as o,p as s,u as c,x as l}from"./server_time-BtxF7Pd1.js";import{n as u,t as d}from"./layered_graph-CRAuzeQO.js";import{A as f,B as p,D as m,E as h,F as g,I as _,L as v,M as ee,N as y,O as b,P as x,R as S,T as C,c as te,j as ne,k as re,l as ie,m as ae,r as w,s as oe,t as T,u as se,y as E,z as ce}from"./branch_picker-BEQBEtqe.js";import{t as D}from"./preload-helper-zJ_50EbN.js";var O=`data-wk-styles`,k=`
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
  background: var(--bg-surface); border: 1px solid var(--border, #d4d4d8); border-radius: 6px; }
.wk-keyrow { display: flex; align-items: center; gap: 8px; min-height: 44px; }
.wk-keyname { flex: none; width: 8.5em; font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem; color: var(--text-dim, #71717a);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wk-check { display: flex; align-items: center; gap: 8px; padding: 0 4px; border-radius: 6px;
  font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
.wk-check.is-on { background: var(--accent-weak); }
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
  background: var(--accent, #2563eb); color: var(--accent-contrast); font-weight: 600; }
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
.wk-path:hover { background: var(--accent-weak); }
.wk-pathto { font-weight: 700; grid-row: 1 / span 2; align-self: center; }
.wk-pathchain { font-size: 0.86rem; }
.wk-pathmeta { font-size: 0.78rem; color: var(--text-dim, #71717a); }
/* A route's self-loops, as chips under its row: off by default (lead 5d5b8d750). */
.wk-loops { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.wk-loopchip { min-height: 44px; padding: 0 12px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-surface); color: var(--text-dim, #71717a);
  font: inherit; font-size: 0.82rem; }
.wk-loopchip.is-on { border-color: var(--accent, #2563eb); color: var(--text, #111); font-weight: 600; }
/* 타입 분포 — 「무엇이 몇 개 왔나」. 물어본 타입은 표시가 다릅니다. */
.wk-dist { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0; }
.wk-distlabel { font-size: 0.78rem; color: var(--text-dim, #71717a); }
.wk-distchip { display: inline-flex; gap: 4px; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--border); font-size: 0.82rem; }
.wk-distchip.is-asked { border-color: var(--accent, #2563eb); font-weight: 600; }
/* 결과 표. 구획마다 «자기 키 컬럼»이라 표가 여럿입니다. */
.wk-sec { margin: 10px 0 14px; }
.wk-sechead { font-weight: 700; font-size: 0.86rem; margin: 0 0 4px; }
.wk-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; display: block;
  overflow-x: auto; white-space: nowrap; }
.wk-table th, .wk-table td { border-bottom: 1px solid var(--border);
  padding: 5px 8px; text-align: left; }
.wk-table th { font-weight: 600; color: var(--text-dim, #71717a); position: sticky; top: 0;
  background: var(--bg-surface); }
/* 숫자는 «자릿수»로 섭니다 — x·y 가 세로로 안 맞으면 좌표를 못 읽습니다. */
.wk-table td.wk-num { text-align: right; font-variant-numeric: tabular-nums; }
/* id 는 길고 «마지막»입니다. 읽는 것이 아니라 «집는» 칸이라 폭을 안 뺏습니다. */
.wk-table td.wk-id { font-family: var(--font-mono, ui-monospace, monospace); font-size: 0.74rem;
  color: var(--text-dim, #71717a); max-width: 22ch; overflow: hidden; text-overflow: ellipsis; }
.wk-walk, .wk-trunc { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }
.wk-walk { color: var(--text-dim, #71717a); }
.wk-trunc { color: var(--warning); }
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
/* Node names at the body size (lead 9dc2a5695 ⑤): the rows (gapY 27.2) clear it; names longer than a column
   already ran into the next one at the tag size, and still do. */
.sg-node text { fill: var(--text); font-size: var(--fs-body); cursor: pointer; }
/* The picked node's facts stay in sight (lead 9dc2a5695 ①): pinned to the bottom of whatever scrolls the
   picture, capped with a scroll of their own, Mark and Fold first. Nothing picked draws nothing. */
.sg-facts { display: flex; flex-direction: column; gap: 3.4px; position: sticky; bottom: 0; z-index: 1;
  max-height: 45vh; overflow: auto; padding: var(--space-3); background: var(--bg-surface);
  border-top: 1px solid var(--border); }
.sg-facts:empty { display: none; }
.sg-facts-acts { display: flex; flex-wrap: wrap; gap: var(--space-2); }
/* Mark (into the marking Continue walks) and Fold branches / Unfold (lead 43a738d58 ③) - their own presses. */
.sg-mark, .sg-fold { min-height: 44px; padding: 0 var(--space-4); font: inherit; color: var(--text);
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 0; cursor: pointer; }
.sg-mark.is-on { color: var(--accent); background: var(--accent-weak); border-color: var(--accent); font-weight: 600; }
.sg-mark[disabled] { opacity: 0.5; cursor: not-allowed; }
.sg-facts-head { font-weight: 600; }
.sg-fact { font-family: 'JetBrains Mono', monospace; font-size: var(--fs-label); overflow-wrap: anywhere; }
/* Which world says an edge, when the walk reads several (leads 99032248f, ee0f66e7b): one row per world under
   the edge, its chip first, then that world's evidence. */
.sg-fact--world { padding-left: var(--space-4); color: var(--text-muted); }
.sg-world { display: inline-block; margin-right: var(--space-2); padding: 0 var(--space-1); border: 1px solid var(--border);
  font-family: var(--font-sans); font-size: var(--fs-tag); color: var(--text); }
`;function A(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${O}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(O,``),t.textContent=k,(e.head||e.documentElement).appendChild(t),!0}function j(e){return e==null?``:String(e)}function M(e){return e!==``&&Number.isFinite(Number(e))}function N(e){let t=new Map;for(let n of e||[]){let e=n&&n.qualifiers;if(!e||typeof e!=`object`)continue;for(let e of[n.target,n.source])(!e||!t.has(e))&&t.set(e,t.get(e)||{});let r=t.get(n.target)||{};Object.assign(r,e),t.set(n.target,r)}return t}function P(e,t){let n=[];for(let r of e||[])for(let e of Object.keys(t&&t.get(r.id)||{}))n.includes(e)||n.push(e);return n}function le(e,t,n=[],r=200){let i=e&&e.nodes||[],a=i.slice(0,r),o=N(e&&e.edges||[]),s=[],c=y(e),l=m(n);for(let[e,n]of _(a)){let r=S(t,e,P(n,o),void 0,l);s.push({type:e,heading:g(e,n.length),columns:r,rows:n.map(e=>({id:e.id,cells:r.map(t=>{let n=j(h(t,e,o.get(e.id)||{},c.get(e.type)));return{text:n,kind:t.kind,numeric:M(n)}})}))})}return{sections:s,shown:a.length,hidden:Math.max(0,i.length-a.length)}}var F=Object.freeze({margin:20.4,gapX:238,gapY:27.2,r:6.8,labelDx:10.2}),I=F.margin,L=F.gapX,R=F.labelDx;function z(e){let t=[],n=[];for(let[r,i]of e||[])i===p.CASE?t.push(r):i===p.CONTROL&&n.push(r);return{positive:t,negative:n}}function B(e,t){let n=v(t),r=(t||[]).map(e=>C(e&&e.type)),i=new Map(r.map((e,t)=>[e,t])),a=e=>{let t=e&&e.results||[];return t[t.length-1]||{}},o=new Map;(e||[]).forEach((e,t)=>{for(let n of a(e).bundles||[])o.has(n.node)||o.set(n.node,[]),o.get(n.node).push({...n,step:t})});let s=new Map,c=new Map,l=[],d=[],f=0;(e||[]).forEach((e,t)=>{let r=(e.seeds||[]).map(e=>c.get(e)).filter(Boolean).map(e=>e.layer),a=t===0||!r.length?0:Math.max(...r);for(let r of e.results||[])for(let e of Array.isArray(r.nodes)?r.nodes:[]){let r=C(e.type);if(i.has(r)||i.set(r,i.size),c.has(e.id))continue;if(!Number.isFinite(e.depth)){f+=1;continue}let p=a+e.depth,m=s.get(p)||0,h={id:e.id,type:r,label:e.label||e.id,depth:e.depth,layer:p,step:t+1,...u(F,p,m),static:n.has(r),colour:i.get(r)%9,keys:e.keys||{},attributes:e.attributes||{}};c.set(e.id,h),l.push(h),m+=1;for(let t of o.get(e.id)||[])d.push({step:t.step,node:t.node,predicate:t.predicate,direction:t.direction,farType:C(t.far_type),count:t.count,key:`${t.node}|${t.predicate}|${t.direction}`,x:h.x+R,y:u(F,p,m).y}),m+=1;s.set(p,m)}});let p=[],m=new Set,h=new Set,g=[];(e||[]).forEach((e,t)=>{for(let t of e.results||[])for(let e of Array.isArray(t.edges)?t.edges:[]){if(m.has(e.id))continue;let t=c.get(e.source),n=c.get(e.target);if(!t||!n){h.add(e.id);continue}m.add(e.id),h.delete(e.id),p.push({id:e.id,source:e.source,target:e.target,predicate:e.predicate_label||e.predicate||``,occurredAt:e.occurred_at||``,byWorld:Array.isArray(e.by_world)?e.by_world:[],x1:t.x,y1:t.y,x2:n.x,y2:n.y})}let n=a(e);n.cut&&g.push({step:t+1,budgets:b(n.truncatedAxes,n.limits)})});let _=new Map;for(let e of l)_.set(e.type,(_.get(e.type)||0)+1);return{nodes:l,edges:p,chips:d,legend:[..._.entries()].sort((e,t)=>i.get(e[0])-i.get(t[0])).map(([e,t])=>({type:e,count:t,colour:i.get(e)%9,static:n.has(e)})),unplaced:f,loose:h.size,cut:g,width:I*2+Math.max(0,...l.map(e=>e.x))+L,height:I*2+Math.max(0,...l.map(e=>e.y),...d.map(e=>e.y))}}function V(e,t,n){let r=new Map(e.nodes.map(e=>[e.id,e.layer])),i=[...n||[],...e.nodes.filter(e=>e.depth===0).map(e=>e.id)],a=new Map;for(let t of e.edges)for(let[e,n]of[[t.source,t.target],[t.target,t.source]])r.get(n)>=r.get(e)&&(a.has(e)||a.set(e,[]),a.get(e).push(n));let o=e=>{let t=new Set(i.filter(e=>r.has(e))),n=[...t];for(;n.length;){let r=n.shift();if(!e.has(r))for(let e of a.get(r)||[])t.has(e)||(t.add(e),n.push(e))}return t},s=o(t);return new Set([...o(new Set)].filter(e=>!s.has(e)))}function H({x:e,y:t,count:n,word:r,data:i,press:a}){return{x:e,y:t,text:`+${n} ${r}`,attrs:{class:`sg-bundle`,...i},onPress:a}}function U(e,t,n){let r=V(e,t,n),i=e=>r.has(e),a=[];for(let r of t){if(i(r))continue;let t=V(e,new Set([r]),n),o=e.nodes.filter(e=>t.has(e.id)).sort((e,t)=>e.layer-t.layer||e.y-t.y)[0];o&&a.push({node:r,count:t.size,x:o.x,y:o.y})}return{nodes:e.nodes.filter(e=>!i(e.id)),edges:e.edges.filter(e=>!i(e.source)&&!i(e.target)),chips:e.chips.filter(e=>!i(e.node)&&!t.has(e.node)),folds:a,hidden:r.size}}function W(e,t){let n=e.nodes.find(e=>e.id===t);if(!n)return null;let r=new Map(e.nodes.map(e=>[e.id,e.label]));return{node:n,edges:e.edges.filter(e=>e.source===t||e.target===t).map(e=>({out:e.source===t,predicate:e.predicate,other:r.get(e.source===t?e.target:e.source),occurredAt:e.occurredAt,byWorld:e.byWorld}))}}var ue=class{constructor(e,t={}){if(!e)throw Error(`SubgraphView needs a mount element`);if(!t.markings||!Array.isArray(t.chain)||!t.chain.length)throw Error(`SubgraphView needs a marking store and a chain of marking names`);this.mount=e,this.doc=t.doc||e.ownerDocument,this.walk=t.walk,this.entities=t.entities||(()=>[]),this.markings=t.markings,this.chain=t.chain.slice(),this.fanoutLimit=Number.isFinite(t.fanoutLimit)?t.fanoutLimit:20,this.worldChips=!!t.worldChips,A(this.doc),this.root=this.doc.createElement(`div`),this.root.className=`sg-view`,this.mount.appendChild(this.root),this.state=`idle`,this.reason=``,this.steps=[],this.layout=null,this.selected=null,this.asked=``,this.folded=new Set;for(let e of this.chain)this.markings.subscribe(e,()=>this._restyle())}writes(){return this.chain[this.steps.length]||``}async show(e={}){let t=JSON.stringify(this.markings.entries(this.chain[0]));e.reuse&&t===this.asked&&this.state===`done`||(this.asked=t,this.steps=[],this.layout=null,this.selected=null,this.folded=new Set,await this._step(this.chain[0]))}_seeds(){return this.steps.flatMap(e=>e.seeds)}toggleFold(e){this.folded.has(e)?this.folded.delete(e):this.folded.add(e),this.render()}async continueWalk(){let e=this.writes();!e||this.state!==`done`||await this._step(e)}async _step(e){let t=z(this.markings.entries(e));if(!t.positive.length){this.steps.length||(this.state=`empty`,this.render());return}let n={marking:e,seeds:[...t.positive,...t.negative],positive:t.positive,negative:t.negative,expand:[],results:[]};await this._ask(n,[],e=>[...this.steps,{...n,results:[e]}])}async expandBundle(e,t){let n=this.steps[e];if(!n||this.state!==`done`||n.expand.includes(t))return;let r=[...n.expand,t];await this._ask(n,r,t=>this.steps.map((n,i)=>i===e?{...n,expand:r,results:[...n.results,t]}:n))}async _ask(e,t,n){let r=this.steps;this.state=`running`,this.render();let i=await this.walk({positive:e.positive,negative:e.negative,fanout_limit:this.fanoutLimit,expand:t});this.steps===r&&(i&&i.ok?(this.steps=n(i),this.layout=B(this.steps,this.entities()),this.state=`done`):(this.state=`failed`,this.reason=i&&i.message||``),this.render())}_el(e,t,n){let r=this.doc.createElement(e);return t&&(r.className=t),n!==void 0&&(r.textContent=String(n)),r}_classOf(e){let t=this.writes(),n=this.steps.some(t=>t.seeds.includes(e.id));return`sg-node sg-type-${e.colour} sg-step-${e.step}`+(e.static?` is-static`:``)+(n?` is-seed`:``)+(t&&this.markings.signOf(t,e.id)!==p.ABSENT?` is-marked`:``)+(e.id===this.selected?` is-selected`:``)}render(){if(this.root.textContent=``,this._groups=new Map,this.continueButton=null,this.state===`empty`){this.root.appendChild(this._el(`div`,`sg-note`,`Nothing marked`));return}if(this.state===`failed`&&this.root.appendChild(this._el(`div`,`sg-fail`,`Failed · ${this.reason}`)),this.state===`running`&&this.root.appendChild(this._el(`div`,`sg-note`,`Walking`)),!this.layout)return;let e=this.layout;this.root.appendChild(this._el(`div`,`sg-counts`,`Nodes ${e.nodes.length} · Edges ${e.edges.length}`));for(let t of e.cut){let e=this.steps.length>1?`step ${t.step} · `:``;this.root.appendChild(this._el(`div`,`sg-trunc`,`Truncated · ${e}${t.budgets.join(` · `)}`))}e.unplaced&&this.root.appendChild(this._el(`div`,`sg-note`,`No depth · ${e.unplaced} nodes`)),e.loose&&this.root.appendChild(this._el(`div`,`sg-note`,`Not drawn · ${e.loose} edges`));let n=U(e,this.folded,this._seeds());n.hidden&&this.root.appendChild(this._el(`div`,`sg-note`,`Folded · ${t(n.hidden,`node`)}`));let r=this._el(`div`,`sg-bar`),i=this._el(`div`,`sg-legend`);for(let t of e.legend){let e=this._el(`span`,`sg-chip sg-type-${t.colour}`);e.setAttribute(`data-type`,t.type),e.appendChild(this._el(`span`,`sg-swatch${t.static?` is-static`:``}`)),e.appendChild(this._el(`span`,``,`${t.type} ${t.count}`)),i.appendChild(e)}r.appendChild(i);let a=this._el(`button`,`sg-continue`,`Continue`);a.setAttribute(`type`,`button`),a.addEventListener&&a.addEventListener(`click`,()=>{this.continueWalk()}),this.continueButton=a,r.appendChild(a),this.root.appendChild(r);let{box:o,groups:s}=d(this.doc,{geometry:F,boxClass:`sg-box`,svgClass:`sg-graph`,width:e.width,height:e.height,edges:n.edges.map(e=>({x1:e.x1,y1:e.y1,x2:e.x2,y2:e.y2,attrs:{class:`sg-edge`,"data-predicate":e.predicate}})),nodes:n.nodes.map(e=>({id:e.id,x:e.x,y:e.y,label:e.label,shape:e.static?`rect`:`circle`,attrs:{class:this._classOf(e),"data-node":e.id,"data-depth":e.depth,"data-step":e.step},onPress:()=>this.press(e.id)})),texts:[...n.chips.map(e=>H({x:e.x,y:e.y,count:e.count,word:e.farType,data:{"data-bundle":e.key,"data-step":e.step+1},press:()=>{this.expandBundle(e.step,e.key)}})),...n.folds.map(e=>H({x:e.x,y:e.y,count:e.count,word:`folded`,data:{"data-fold":e.node},press:()=>{this.toggleFold(e.node)}}))]});for(let e of n.nodes)this._groups.set(e.id,{group:s.get(e.id),node:e});this.root.appendChild(o),this.factsBox=this._facts(),this.root.appendChild(this.factsBox),this._restyle()}_facts(){let e=this._el(`div`,`sg-facts`);this.markButton=null;let t=this.layout&&this.selected?W(this.layout,this.selected):null;if(!t)return e;e.appendChild(this._el(`div`,`sg-facts-head`,`${t.node.label} · ${t.node.type}`));let n=t.node.id,r=this._el(`div`,`sg-facts-acts`),i=this._el(`button`,`sg-mark`,`Mark`);i.setAttribute(`type`,`button`),i.setAttribute(`data-mark-node`,n),i.addEventListener&&i.addEventListener(`click`,()=>{this.toggleMark(n)}),this.markButton=i,r.appendChild(i);let a=this.folded.has(n);if(a||V(this.layout,new Set([n]),this._seeds()).size){let e=this._el(`button`,`sg-fold`,a?`Unfold`:`Fold branches`);e.setAttribute(`type`,`button`),e.setAttribute(`data-fold-node`,n),e.addEventListener&&e.addEventListener(`click`,()=>{this.toggleFold(n)}),r.appendChild(e)}e.appendChild(r);for(let[n,r]of[...Object.entries(t.node.keys),...Object.entries(t.node.attributes)])e.appendChild(this._el(`div`,`sg-fact`,`${n} ${r}`));for(let n of t.edges)if(e.appendChild(this._el(`div`,`sg-fact`,`${n.out?`→`:`←`} ${n.predicate} · ${n.other}${n.occurredAt?` · ${n.occurredAt}`:``}`)),this.worldChips)for(let t of n.byWorld||[]){let n=this._el(`div`,`sg-fact sg-fact--world`);n.appendChild(this._el(`span`,`sg-world`,t.world)),n.appendChild(this._el(`span`,``,[t.source_who,t.occurred_at].filter(Boolean).join(` · `))),e.appendChild(n)}return e}_restyle(){for(let{group:e,node:t}of(this._groups||new Map).values())e.setAttribute(`class`,this._classOf(t));let e=this.writes();if(this.markButton&&this.selected){let t=!!e&&this.markings.signOf(e,this.selected)!==p.ABSENT;this.markButton.setAttribute(`aria-pressed`,String(t)),this.markButton.className=`sg-mark${t?` is-on`:``}`,a(this.markButton,e?``:`End of chain`)}this.continueButton&&a(this.continueButton,e?this.markings.count(e)?``:`Mark a node`:`End of chain`)}press(e){this.select(e)}toggleMark(e){let t=this.writes();t&&this.markings.toggle(t,e,p.CASE)}select(e){this.selected=e;let t=this._facts();this.factsBox&&this.factsBox.parentNode===this.root?(this.root.insertBefore(t,this.factsBox),this.root.removeChild(this.factsBox)):this.root.appendChild(t),this.factsBox=t,this._restyle()}},G=Object.freeze([`walk-start`,`walk-2`,`walk-3`,`walk-4`]),K=l,de=[`both`,`outgoing`,`incoming`],q=`default`,J=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function Y(c,l,u){let d=u||{},m=d.apiBase||``;A(c);let h=r(d.world),g=n(d.fetchImpl||((e,t)=>globalThis.fetch(e,t)),()=>h),_=oe({apiBase:m,fetchImpl:g}),v={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,subjects:null,subjectsState:`idle`,subjectsReason:``,subjectsScanned:null,subjectsScanCut:!1,subjectsListCut:!1,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``,asked:null,view:`table`,loopsOn:new Map,followOpen:!1},y=e=>`${e.to}|${e.follow.slice().sort().join(`+`)}`,S=e=>v.loopsOn.get(y(e))||new Set,D=C,O=()=>v.decl&&v.decl.entities||[],k=e=>{let t=O().find(t=>t.type===e);return t&&t.keys||[]},j=J(c,`div`,`wk-rail`),M=J(c,`div`,`wk-main`),N=new ce,P=J(c,`div`,`wk-graph`),F=new ue(P,{doc:c,walk:_,entities:O,markings:N,chain:G,worldChips:h.length>1}),I=e=>{let t=Object.keys(v.keys||{}).length>0;N.replace(G[0],t?[[te(v.type,v.keys),p.CASE]]:[]),F.show(e)},L=()=>v.decl&&v.decl.predicates||[],R=()=>L().map(e=>e.name),z=()=>re(x(L(),v.type,O()),R(),v.follow);function B(){if(!v.decl||!v.type||!v.collect.size)return[];let e=[];for(let t of v.collect)for(let n of ae(v.decl,D(v.type),D(t)))e.push({...n,to:D(t)});return ne(O(),e).sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function V(){let e={type:v.type,keys:v.keys};v.follow.size&&(e.follow=[...v.follow]),v.collect.size&&(e.collect=[...v.collect]),v.direction&&(e.direction=v.direction);let t=parseInt(v.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(v.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function H(){if(!v.type)return;if(v.view===`graph`){I();return}let e=V();v.run=`running`,v.result=null,v.reason=``,v.asked={...e,keys:{...e.keys}},Z();let t=await _(e);t&&t.ok?(v.run=`done`,v.result=t):(v.run=`failed`,v.reason=t&&t.message||`Unknown`),Z()}function U(e,t=`wk-field`){let n=J(c,`div`,t);return n.append(J(c,`div`,`wk-label`,e)),n}function W(e,t,n=`wk-cell`){let r=J(c,`label`,n);return r.append(J(c,`span`,`wk-keyname`,e),t),r}function Y(e){let n=U(`Start`),r=J(c,`select`,`wk-select`),a=J(c,`option`,``,s);a.value=``,r.append(a);for(let e of O()){let t=J(c,`option`,``,e.type);t.value=e.type,e.type===v.type&&(t.selected=!0),r.append(t)}if(r.addEventListener(`change`,()=>{v.type=r.value;let e=new Set(k(v.type));v.keys=Object.fromEntries(Object.entries(v.keys).filter(([t])=>e.has(t)));let t=new Set(x(L(),v.type,O()));v.follow=new Set([...v.follow].filter(e=>t.has(e))),v.result=null,v.run=`idle`,Z(),be()}),n.append(W(`Type`,r,`wk-cell wk-cell-row`)),v.type){let e=U(`Pick a node`,`wk-sub`);if(v.subjectsState===`loading`)e.append(J(c,`div`,`wk-note`,i));else if(v.subjectsState===`failed`)e.append(J(c,`div`,`wk-fail`,`Node list · ${v.subjectsReason}`));else if(v.subjectsState===`ready`){let n=v.subjects||[];if(!n.length)e.append(J(c,`div`,`wk-note`,v.subjectsScanCut?`Not every node read (up to ${v.subjectsScanned})`:`No node of this type in the ledger`));else{let r=J(c,`select`,`wk-select`);r.append(J(c,`option`,``,`— pick, or type the keys below —`)),n.forEach((e,t)=>{let n=Object.values(e.keys||{}).map(e=>String(e)).join(` · `),i=J(c,`option`,``,e.count?`${n}  (${e.count})`:n);i.value=String(t),r.append(i)}),r.addEventListener(`change`,()=>{let e=n[Number(r.value)];e&&(v.keys={...e.keys},Z())}),e.append(r),v.subjectsListCut&&e.append(J(c,`div`,`wk-note`,`${t(n.length,`node`)} listed · not all · type the keys below if missing`))}}n.append(e)}let o=k(v.type);v.type?o.length||n.append(J(c,`div`,`wk-note`,`This type has no keys`)):n.append(J(c,`div`,`wk-note`,`Pick a type for its keys`));let l=J(c,`div`,`wk-keys`);for(let e of o){let t=J(c,`input`,`wk-input`);t.type=`text`,t.value=v.keys[e]===void 0?``:v.keys[e],t.addEventListener(`input`,()=>{v.keys[e]=t.value}),l.append(W(e,t))}o.length&&n.append(l),e.append(n)}function fe(t){let n=U(`Collect`),r=O().map(e=>e.type);if(!r.length){n.append(J(c,`div`,`wk-note`,`No entity declared`)),t.append(n);return}let i=J(c,`div`,`wk-chips`);for(let e of r.filter(e=>v.collect.has(e))){let t=J(c,`button`,`wk-chip`,`${e} ×`);t.type=`button`,t.setAttribute(`data-collect`,e),t.setAttribute(`aria-label`,`Remove ${e}`),t.addEventListener(`click`,()=>{v.collect.delete(e),Z()}),i.append(t)}let a=r.filter(e=>!v.collect.has(e));if(a.length){let e=J(c,`select`,`wk-add`);e.setAttribute(`aria-label`,`Add a type to collect`);let t=J(c,`option`,``,`+ Type`);t.value=``,e.append(t);for(let t of a){let n=J(c,`option`,``,t);n.value=t,e.append(n)}e.addEventListener(`change`,()=>{e.value&&(v.collect.add(e.value),Z())}),i.append(e)}n.append(i),v.collect.size||n.append(J(c,`div`,`wk-note`,`${e} · ${q} · all`)),t.append(n)}function pe(e){if(!v.type||!v.collect.size)return;let n=B(),r=J(c,`div`,`wk-field`),i=J(c,`div`,`wk-routes-head`);i.append(J(c,`span`,`wk-label`,`Route to ${[...v.collect].map(D).join(`, `)}`),J(c,`span`,`wk-note`,t(n.length,`route`))),r.append(i),n.length||r.append(J(c,`div`,`wk-note`,`No route from ${D(v.type)} to ${[...v.collect].map(D).join(` · `)}`));let a=(e,t)=>{let n=E(e,t);v.follow=new Set(f(R(),n.follow)),v.hops=String(n.hops),Z()},o=(e,t)=>e.size===t.size&&[...e].every(e=>t.has(e));for(let e of n){let n=E(e,S(e)),i=v.hops===String(n.hops)&&o(v.follow,new Set(f(R(),n.follow))),s=J(c,`div`,`wk-route`+(i?` is-on`:``)),l=J(c,`button`,`wk-path`);if(l.type=`button`,l.setAttribute(`aria-pressed`,i?`true`:`false`),l.append(J(c,`span`,`wk-pathto`,`→ ${e.to}`)),l.append(J(c,`span`,`wk-pathchain`,e.chain.join(` → `))),l.append(J(c,`span`,`wk-pathmeta`,`${t(n.hops,`hop`)} · ${n.follow.join(`, `)}`)),l.addEventListener(`click`,()=>a(e,S(e))),s.append(l),e.loops.length){let t=J(c,`div`,`wk-loops`);t.append(J(c,`span`,`wk-note`,`self-loops`));for(let n of e.loops){let r=S(e).has(n.predicate),i=J(c,`button`,`wk-loopchip`+(r?` is-on`:``),`↻ ${n.predicate}`);i.type=`button`,i.setAttribute(`aria-pressed`,r?`true`:`false`),i.title=`${n.at} → ${n.at}`,i.addEventListener(`click`,()=>{let t=new Set(S(e));r?t.delete(n.predicate):t.add(n.predicate),v.loopsOn.set(y(e),t),a(e,t)}),t.append(i)}s.append(t)}r.append(s)}e.append(r)}function X(e){let t=U(`Step`),n=J(c,`div`,`wk-steps`),r=J(c,`select`,`wk-select`);r.append(J(c,`option`,``,q));for(let e of de){let t=J(c,`option`,``,e);t.value=e,e===v.direction&&(t.selected=!0),r.append(t)}r.addEventListener(`change`,()=>{v.direction=r.value}),n.append(W(`direction`,r));for(let[e,t,r,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=J(c,`input`,`wk-input`);a.type=`number`,a.min=String(r),a.max=String(i),a.placeholder=q,a.value=v[t],a.addEventListener(`input`,()=>{v[t]=a.value}),n.append(W(e,a))}t.append(n),e.append(t)}function me(t){let n=z(),r=J(c,`div`,`wk-field`);if(!n.length){r.append(J(c,`div`,`wk-label`,`Follow`)),r.append(J(c,`div`,`wk-note`,v.type?ee(v.type):`No predicate declared`)),t.append(r);return}let i=v.follow.size?[...v.follow].map(D).join(`, `):q,a=J(c,`button`,`wk-fold`);if(a.type=`button`,a.setAttribute(`aria-expanded`,v.followOpen?`true`:`false`),a.append(J(c,`span`,`wk-foldtext`,`Follow · ${i}`),J(c,`span`,`wk-foldmark`,v.followOpen?`▾`:`▸`)),a.addEventListener(`click`,()=>{v.followOpen=!v.followOpen,Z()}),r.append(a),v.followOpen){let t=J(c,`div`,`wk-checks`);for(let e of n){let n=J(c,`label`,`wk-check`+(v.follow.has(e)?` is-on`:``));n.setAttribute(`data-follow`,e);let r=J(c,`input`);r.type=`checkbox`,r.checked=v.follow.has(e),r.addEventListener(`change`,()=>{v.follow.has(e)?v.follow.delete(e):v.follow.add(e),Z()}),n.append(r,J(c,`span`,``,e)),t.append(n)}r.append(t),r.append(J(c,`div`,`wk-note`,`${e} · ${q}`))}t.append(r)}function he(e){let t=J(c,`button`,`wk-go`,v.run===`running`?K:`Walk`);t.type=`button`,a(t,v.run===`running`?K:v.type?``:w),t.addEventListener(`click`,H),e.append(t)}function ge(e,t){let n=le(t,O(),v.decl&&v.decl.predicates||[]);for(let t of n.sections){let n=J(c,`div`,`wk-sec`);n.append(J(c,`div`,`wk-sechead`,t.heading));let r=J(c,`table`,`wk-table`),i=J(c,`thead`),a=J(c,`tr`);for(let e of t.columns)a.append(J(c,`th`,``,e.name));i.append(a),r.append(i);let o=J(c,`tbody`);for(let e of t.rows){let t=J(c,`tr`);for(let n of e.cells){let e=J(c,`td`,n.numeric?`wk-num`:``,n.text);n.kind===`id`&&(e.className=`wk-id`),t.append(e)}o.append(t)}r.append(o),n.append(r),e.append(n)}n.hidden&&e.append(J(c,`div`,`wk-note`,`${n.hidden} more not drawn`))}function _e(e){let t=Object.values(e.keys||{}).map(e=>String(e)).filter(e=>e).join(` · `),n=(e.collect||[]).map(D).join(`, `);return`${D(e.type)}${t?` `+t:``}${n?` → `+n:``}`}function ve(e){let t=J(c,`div`,`wk-mainhead`),n=v.result;if(v.view===`table`&&v.run===`done`&&n&&v.asked){t.append(J(c,`span`,`wk-title`,_e(v.asked)));let e=(v.asked.collect||[]).map(D).join(`, `);t.append(J(c,`span`,`wk-counts`,e?`Nodes ${n.nodes.length} (collect: ${e}) · Edges ${n.edges.length} (all)`:`Nodes ${n.nodes.length} · Edges ${n.edges.length}`))}let r=J(c,`div`,`wk-views`);for(let[e,t]of[[`table`,`Table`],[`graph`,`Graph`]]){let n=J(c,`button`,`wk-view`+(v.view===e?` is-on`:``),t);n.type=`button`,n.setAttribute(`data-view`,e),n.addEventListener(`click`,()=>{v.view=e,e===`graph`&&v.type&&I({reuse:!0}),Z()}),r.append(n)}t.append(r),e.append(t)}function ye(e){let n=J(c,`div`,`wk-result`);if(v.run===`idle`)n.append(J(c,`div`,`wk-note`,`No walk yet`));else if(v.run===`running`)n.append(J(c,`div`,`wk-note`,K));else if(v.run===`failed`){let e=J(c,`div`,`wk-fail`);e.append(J(c,`b`,``,o),J(c,`span`,``,` · `+v.reason)),n.append(e)}else if(v.result){let e=v.result;if(e.walk&&n.append(J(c,`div`,`wk-walk`,`Asked ${t(e.walk.hops_requested,`hop`)} · reached ${t(e.walk.hops_reached,`hop`)} · ${e.walk.direction}`)),e.generatedAt&&n.append(J(c,`div`,`wk-note`,`As of ${String(e.generatedAt)}`)),e.cut&&n.append(J(c,`div`,`wk-trunc`,`Cut · ${b(e.truncatedAxes,e.limits).join(` · `)}`)),e.nodes.length){let t=new Map;for(let n of e.nodes){let e=n.type||`—`;t.set(e,(t.get(e)||0)+1)}let r=J(c,`div`,`wk-dist`);r.append(J(c,`span`,`wk-distlabel`,`Types`));for(let[e,n]of[...t.entries()].sort((e,t)=>t[1]-e[1])){let t=J(c,`span`,`wk-distchip`+(v.collect.has(e)||v.collect.has(`${e}@1`)?` is-asked`:``));t.append(J(c,`b`,``,e),J(c,`span`,``,` ${n}`)),r.append(t)}n.append(r)}e.nodes.length||n.append(J(c,`div`,`wk-note`,e.message||`No node reached`)),ge(n,e)}e.append(n)}function Z(){l.textContent=``,j.textContent=``,M.textContent=``;let e=J(c,`div`,`wk-form`),t=J(c,`div`,`wk-rail-foot`);if(v.declState===`loading`)e.append(J(c,`div`,`wk-note`,`Declaration · ${i}`));else if(v.declState===`failed`){let n=J(c,`div`,`wk-fail`);n.append(J(c,`b`,``,`Declaration not read`),J(c,`span`,``,` · `+v.declReason));let r=J(c,`button`,`wk-go`,`Retry`);r.type=`button`,r.addEventListener(`click`,Q),e.append(n),t.append(r)}else Y(e),fe(e),pe(e),X(e),me(e),he(t),ve(M),v.view===`graph`?M.append(P):ye(M);j.append(e,t),l.append(j,M)}async function be(){if(!v.type){v.subjectsState=`idle`,v.subjects=null;return}let e=v.type;v.subjectsState=`loading`,v.subjects=null,Z();let t=await se({apiBase:m,fetchImpl:g,type:e});v.type===e&&(t&&t.ok?(v.subjectsState=`ready`,v.subjects=t.nodes,v.subjectsScanned=t.scanned,v.subjectsScanCut=t.scanTruncated,v.subjectsListCut=t.valuesTruncated):(v.subjectsState=`failed`,v.subjectsReason=t&&t.message||`Unknown`),Z())}async function Q(){v.declState=`loading`,Z();let e=await ie({apiBase:m,fetchImpl:g});e&&e.ok?(v.decl=e,v.declState=`ready`):(v.declState=`failed`,v.declReason=e&&e.message||`Unknown`),$&&$.show({worlds:e&&e.worlds||[],current:h,operating:e&&e.operating}),Z()}let $=d.branchMount?new T(d.branchMount,{doc:c,onPickSet:d.pickWorld}):null;return $&&$.show({current:h}),Q(),{state:v,spec:V,fire:H,render:Z}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&D(async()=>{let{API_BASE:e}=await import(`./config-CtEgmCQz.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{Y(document,e,{apiBase:t,world:new URL(location.href).searchParams.getAll(`world`),branchMount:document.getElementById(`wk-branch`),pickWorld:e=>{location.assign(c(location.href,e))}})})}