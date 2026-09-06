const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-C6wMXuF6.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-nTqwt3FA.js";import{a as e,s as t,t as n,u as r}from"./preload-helper-D5ytDLcZ.js";var i=`data-wk-styles`,a=`
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

.wk-go { width: 100%; border: 0; border-radius: 8px;
  background: var(--accent, #2563eb); color: #fff; font-weight: 600; }
.wk-go[disabled] { opacity: 0.45; }

.wk-result { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px;
  background: var(--bg-panel, transparent); border: 1px solid var(--border, #d4d4d8);
  border-radius: 8px; }
.wk-counts { font-weight: 600; }
/* 경로 — 누를 수 있는 것이므로 button 이고, 그래서 키보드로도 닿습니다. */
.wk-path { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; width: 100%;
  text-align: left; min-height: 44px; padding: 8px 10px; margin: 0 0 6px;
  border: 1px solid var(--line, #e4e4e7); border-radius: 6px; cursor: pointer;
  background: var(--surface, #fff); color: inherit; font: inherit; }
.wk-path:hover { background: var(--accent-soft, rgba(37, 99, 235, 0.10)); }
.wk-pathto { font-weight: 700; grid-row: 1 / span 2; align-self: center; }
.wk-pathchain { font-size: 0.86rem; }
.wk-pathmeta { font-size: 0.78rem; color: var(--text-dim, #71717a); }
/* 타입 분포 — 「무엇이 몇 개 왔나」. 물어본 타입은 표시가 다릅니다. */
.wk-dist { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0; }
.wk-distlabel { font-size: 0.78rem; color: var(--text-dim, #71717a); }
.wk-distchip { display: inline-flex; gap: 4px; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--line, #e4e4e7); font-size: 0.82rem; }
.wk-distchip.is-asked { border-color: var(--accent, #2563eb); font-weight: 600; }
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
`;function o(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${i}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(i,``),t.textContent=a,(e.head||e.documentElement).appendChild(t),!0}function s(e){return String(e||``).split(`@`)[0]}function c(e,t){let n=new Set((t||[]).map(s));return(e||[]).filter(e=>n.has(s(e)))}function l(e,t,n){let r=n instanceof Set?n:new Set(n||[]),i=(t||[]).filter(e=>r.has(e));return[...new Set([...e||[],...i])]}var u=[`both`,`outgoing`,`incoming`],d=`서버 기본`,f=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function p(n,i,a){let p=a||{},m=p.apiBase||``;o(n);let h=e({apiBase:m,fetchImpl:p.fetchImpl}),g={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``},_=s,v=()=>g.decl&&g.decl.entities||[],y=e=>{let t=v().find(t=>t.type===e);return t&&t.keys||[]},b=()=>(g.decl&&g.decl.predicates||[]).map(e=>e.name),x=()=>{let e=g.decl&&g.decl.predicates||[];return g.type?l(e.filter(e=>(e.subjects||[]).includes(g.type)).map(e=>e.name),b(),g.follow):e.map(e=>e.name)};function S(){if(!g.decl||!g.type||!g.collect.size)return[];let e=[];for(let t of g.collect)for(let n of r(g.decl,_(g.type),_(t)))e.push({...n,to:_(t)});return e.sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function C(){let e={type:g.type,keys:g.keys};g.follow.size&&(e.follow=[...g.follow]),g.collect.size&&(e.collect=[...g.collect]),g.direction&&(e.direction=g.direction);let t=parseInt(g.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(g.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function w(){if(!g.type)return;g.run=`running`,g.result=null,g.reason=``,O();let e=await h(C());e&&e.ok?(g.run=`done`,g.result=e):(g.run=`failed`,g.reason=e&&e.message||`알 수 없음`),O()}function T(e){let t=f(n,`div`,`wk-field`);return t.append(f(n,`div`,`wk-label`,e)),t}function E(e){let t=T(`노드 타입`),r=f(n,`select`,`wk-select`);r.append(f(n,`option`,``,`— 고르십시오 —`));for(let e of v()){let t=f(n,`option`,``,e.type);t.value=e.type,e.type===g.type&&(t.selected=!0),r.append(t)}r.addEventListener(`change`,()=>{g.type=r.value;let e=new Set(y(g.type));g.keys=Object.fromEntries(Object.entries(g.keys).filter(([t])=>e.has(t)));let t=new Set(x());g.follow=new Set([...g.follow].filter(e=>t.has(e))),g.result=null,g.run=`idle`,O()}),t.append(r),e.append(t);let i=T(`키`),a=y(g.type);g.type?a.length||i.append(f(n,`div`,`wk-note`,`이 타입은 키가 없습니다`)):i.append(f(n,`div`,`wk-note`,`타입을 고르면 키가 나옵니다`));for(let e of a){let t=f(n,`label`,`wk-keyrow`);t.append(f(n,`span`,`wk-keyname`,e));let r=f(n,`input`,`wk-input`);r.type=`text`,r.value=g.keys[e]===void 0?``:g.keys[e],r.addEventListener(`input`,()=>{g.keys[e]=r.value}),t.append(r),i.append(t)}e.append(i);let o=T(`collect · 무엇을 가져오나`),s=v().map(e=>e.type);s.length||o.append(f(n,`div`,`wk-note`,`선언에 엔터티 없음`));for(let e of s){let t=f(n,`label`,`wk-check`+(g.collect.has(e)?` is-on`:``));t.setAttribute(`data-collect`,e);let r=f(n,`input`);r.type=`checkbox`,r.checked=g.collect.has(e),r.addEventListener(`change`,()=>{g.collect.has(e)?g.collect.delete(e):g.collect.add(e),O()}),t.append(r,f(n,`span`,``,e)),o.append(t)}if(s.length&&o.append(f(n,`div`,`wk-note`,`안 고르면 ${d} · 전부`)),e.append(o),g.type&&g.collect.size){let t=T(`경로 · 선언이 아는 길`),r=S();r.length||t.append(f(n,`div`,`wk-note`,`${_(g.type)} 에서 ${[...g.collect].map(_).join(` · `)} 로 가는 길 없음`));for(let e of r){let r=f(n,`button`,`wk-path`);r.type=`button`,r.append(f(n,`span`,`wk-pathto`,`→ ${e.to}`)),r.append(f(n,`span`,`wk-pathchain`,e.chain.join(` → `))),r.append(f(n,`span`,`wk-pathmeta`,`${e.hops}홉 · ${e.follow.join(`, `)}`)),r.addEventListener(`click`,()=>{g.follow=new Set(c(b(),e.follow)),g.hops=String(e.hops),O()}),t.append(r)}e.append(t)}let l=T(`follow · 어느 길로`),p=x();p.length||l.append(f(n,`div`,`wk-note`,g.type?`${g.type} 에서 나가는 술어 없음`:`선언에 술어 없음`));for(let e of p){let t=f(n,`label`,`wk-check`+(g.follow.has(e)?` is-on`:``));t.setAttribute(`data-follow`,e);let r=f(n,`input`);r.type=`checkbox`,r.checked=g.follow.has(e),r.addEventListener(`change`,()=>{g.follow.has(e)?g.follow.delete(e):g.follow.add(e),O()}),t.append(r,f(n,`span`,``,e)),l.append(t)}p.length&&l.append(f(n,`div`,`wk-note`,`안 고르면 ${d}`)),e.append(l);let m=T(`걸음`),h=f(n,`label`,`wk-keyrow`);h.append(f(n,`span`,`wk-keyname`,`direction`));let C=f(n,`select`,`wk-select`);C.append(f(n,`option`,``,d));for(let e of u){let t=f(n,`option`,``,e);t.value=e,e===g.direction&&(t.selected=!0),C.append(t)}C.addEventListener(`change`,()=>{g.direction=C.value}),h.append(C),m.append(h);for(let[e,t,r,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=f(n,`label`,`wk-keyrow`);a.append(f(n,`span`,`wk-keyname`,e));let o=f(n,`input`,`wk-input`);o.type=`number`,o.min=String(r),o.max=String(i),o.placeholder=d,o.value=g[t],o.addEventListener(`input`,()=>{g[t]=o.value}),a.append(o),m.append(a)}e.append(m);let E=f(n,`button`,`wk-go`,g.run===`running`?`걷는 중`:`날리기`);E.type=`button`,E.disabled=!g.type||g.run===`running`,E.addEventListener(`click`,w),e.append(E)}function D(e){if(g.run===`idle`)return;let t=f(n,`div`,`wk-result`);if(g.run===`running`)t.append(f(n,`div`,`wk-note`,`걷는 중`));else if(g.run===`failed`){let e=f(n,`div`,`wk-fail`);e.append(f(n,`b`,``,`실패`),f(n,`span`,``,` · `+g.reason)),t.append(e)}else if(g.result){let e=g.result;if(t.append(f(n,`div`,`wk-counts`,`노드 ${e.nodes.length} · 엣지 ${e.edges.length}`)),e.walk&&t.append(f(n,`div`,`wk-walk`,`요청 ${e.walk.hops_requested}홉 · 도달 ${e.walk.hops_reached}홉 · ${e.walk.direction}`)),e.cut&&t.append(f(n,`div`,`wk-trunc`,`절단됨 · ${e.truncated.reason}`)),e.nodes.length){let r=new Map;for(let t of e.nodes){let e=t.type||`—`;r.set(e,(r.get(e)||0)+1)}let i=f(n,`div`,`wk-dist`);i.append(f(n,`span`,`wk-distlabel`,`타입`));for(let[e,t]of[...r.entries()].sort((e,t)=>t[1]-e[1])){let r=f(n,`span`,`wk-distchip`+(g.collect.has(e)||g.collect.has(`${e}@1`)?` is-asked`:``));r.append(f(n,`b`,``,e),f(n,`span`,``,` ${t}`)),i.append(r)}t.append(i)}e.nodes.length||t.append(f(n,`div`,`wk-note`,e.message||`닿은 노드 없음`));for(let r of e.nodes.slice(0,200)){let e=f(n,`div`,`wk-row`);e.append(f(n,`span`,`wk-rowtype`,r.type||`—`)),e.append(f(n,`span`,`wk-rowlabel`,r.label||r.id||``)),t.append(e)}e.nodes.length>200&&t.append(f(n,`div`,`wk-note`,`이 아래 ${e.nodes.length-200} 개 안 그림`))}e.append(t)}function O(){i.textContent=``;let e=f(n,`div`,`wk-form`);if(g.declState===`loading`)e.append(f(n,`div`,`wk-note`,`선언 · 읽는 중`));else if(g.declState===`failed`){let t=f(n,`div`,`wk-fail`);t.append(f(n,`b`,``,`선언 못 읽음`),f(n,`span`,``,` · `+g.declReason));let r=f(n,`button`,`wk-go`,`다시`);r.type=`button`,r.addEventListener(`click`,k),e.append(t,r)}else E(e),D(e);i.append(e)}async function k(){g.declState=`loading`,O();let e=await t({apiBase:m,fetchImpl:p.fetchImpl});e&&e.ok?(g.decl=e,g.declState=`ready`):(g.declState=`failed`,g.declReason=e&&e.message||`알 수 없음`),O()}return k(),{state:g,spec:C,fire:w,render:O}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&n(async()=>{let{API_BASE:e}=await import(`./config-C6wMXuF6.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{p(document,e,{apiBase:t})})}