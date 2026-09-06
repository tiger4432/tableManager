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
`;function o(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${i}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(i,``),t.textContent=a,(e.head||e.documentElement).appendChild(t),!0}var s=[`both`,`outgoing`,`incoming`],c=`서버 기본`,l=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function u(n,i,a){let u=a||{},d=u.apiBase||``;o(n);let f=e({apiBase:d,fetchImpl:u.fetchImpl}),p={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``},m=e=>String(e||``).split(`@`)[0],h=()=>p.decl&&p.decl.entities||[],g=e=>{let t=h().find(t=>t.type===e);return t&&t.keys||[]},_=()=>(p.decl&&p.decl.predicates||[]).map(e=>e.name),v=()=>{let e=p.decl&&p.decl.predicates||[];if(!p.type)return e.map(e=>e.name);let t=e.filter(e=>(e.subjects||[]).includes(p.type)).map(e=>e.name);return[...new Set([...t,..._().filter(e=>p.follow.has(e))])]};function y(){if(!p.decl||!p.type||!p.collect.size)return[];let e=[];for(let t of p.collect)for(let n of r(p.decl,m(p.type),m(t)))e.push({...n,to:m(t)});return e.sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function b(){let e={type:p.type,keys:p.keys};p.follow.size&&(e.follow=[...p.follow]),p.collect.size&&(e.collect=[...p.collect]),p.direction&&(e.direction=p.direction);let t=parseInt(p.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(p.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function x(){if(!p.type)return;p.run=`running`,p.result=null,p.reason=``,T();let e=await f(b());e&&e.ok?(p.run=`done`,p.result=e):(p.run=`failed`,p.reason=e&&e.message||`알 수 없음`),T()}function S(e){let t=l(n,`div`,`wk-field`);return t.append(l(n,`div`,`wk-label`,e)),t}function C(e){let t=S(`노드 타입`),r=l(n,`select`,`wk-select`);r.append(l(n,`option`,``,`— 고르십시오 —`));for(let e of h()){let t=l(n,`option`,``,e.type);t.value=e.type,e.type===p.type&&(t.selected=!0),r.append(t)}r.addEventListener(`change`,()=>{p.type=r.value;let e=new Set(g(p.type));p.keys=Object.fromEntries(Object.entries(p.keys).filter(([t])=>e.has(t)));let t=new Set(v());p.follow=new Set([...p.follow].filter(e=>t.has(e))),p.result=null,p.run=`idle`,T()}),t.append(r),e.append(t);let i=S(`키`),a=g(p.type);p.type?a.length||i.append(l(n,`div`,`wk-note`,`이 타입은 키가 없습니다`)):i.append(l(n,`div`,`wk-note`,`타입을 고르면 키가 나옵니다`));for(let e of a){let t=l(n,`label`,`wk-keyrow`);t.append(l(n,`span`,`wk-keyname`,e));let r=l(n,`input`,`wk-input`);r.type=`text`,r.value=p.keys[e]===void 0?``:p.keys[e],r.addEventListener(`input`,()=>{p.keys[e]=r.value}),t.append(r),i.append(t)}e.append(i);let o=S(`collect · 무엇을 가져오나`),u=h().map(e=>e.type);u.length||o.append(l(n,`div`,`wk-note`,`선언에 엔터티 없음`));for(let e of u){let t=l(n,`label`,`wk-check`+(p.collect.has(e)?` is-on`:``));t.setAttribute(`data-collect`,e);let r=l(n,`input`);r.type=`checkbox`,r.checked=p.collect.has(e),r.addEventListener(`change`,()=>{p.collect.has(e)?p.collect.delete(e):p.collect.add(e),T()}),t.append(r,l(n,`span`,``,e)),o.append(t)}if(u.length&&o.append(l(n,`div`,`wk-note`,`안 고르면 ${c} · 전부`)),e.append(o),p.type&&p.collect.size){let t=S(`경로 · 선언이 아는 길`),r=y();r.length||t.append(l(n,`div`,`wk-note`,`${m(p.type)} 에서 ${[...p.collect].map(m).join(` · `)} 로 가는 길 없음`));for(let e of r){let r=l(n,`button`,`wk-path`);r.type=`button`,r.append(l(n,`span`,`wk-pathto`,`→ ${e.to}`)),r.append(l(n,`span`,`wk-pathchain`,e.chain.join(` → `))),r.append(l(n,`span`,`wk-pathmeta`,`${e.hops}홉 · ${e.follow.join(`, `)}`)),r.addEventListener(`click`,()=>{let t=new Set(e.follow.map(m));p.follow=new Set(_().filter(e=>t.has(m(e)))),p.hops=String(e.hops),T()}),t.append(r)}e.append(t)}let d=S(`follow · 어느 길로`),f=v();f.length||d.append(l(n,`div`,`wk-note`,p.type?`${p.type} 에서 나가는 술어 없음`:`선언에 술어 없음`));for(let e of f){let t=l(n,`label`,`wk-check`+(p.follow.has(e)?` is-on`:``));t.setAttribute(`data-follow`,e);let r=l(n,`input`);r.type=`checkbox`,r.checked=p.follow.has(e),r.addEventListener(`change`,()=>{p.follow.has(e)?p.follow.delete(e):p.follow.add(e),T()}),t.append(r,l(n,`span`,``,e)),d.append(t)}f.length&&d.append(l(n,`div`,`wk-note`,`안 고르면 ${c}`)),e.append(d);let b=S(`걸음`),C=l(n,`label`,`wk-keyrow`);C.append(l(n,`span`,`wk-keyname`,`direction`));let w=l(n,`select`,`wk-select`);w.append(l(n,`option`,``,c));for(let e of s){let t=l(n,`option`,``,e);t.value=e,e===p.direction&&(t.selected=!0),w.append(t)}w.addEventListener(`change`,()=>{p.direction=w.value}),C.append(w),b.append(C);for(let[e,t,r,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=l(n,`label`,`wk-keyrow`);a.append(l(n,`span`,`wk-keyname`,e));let o=l(n,`input`,`wk-input`);o.type=`number`,o.min=String(r),o.max=String(i),o.placeholder=c,o.value=p[t],o.addEventListener(`input`,()=>{p[t]=o.value}),a.append(o),b.append(a)}e.append(b);let E=l(n,`button`,`wk-go`,p.run===`running`?`걷는 중`:`날리기`);E.type=`button`,E.disabled=!p.type||p.run===`running`,E.addEventListener(`click`,x),e.append(E)}function w(e){if(p.run===`idle`)return;let t=l(n,`div`,`wk-result`);if(p.run===`running`)t.append(l(n,`div`,`wk-note`,`걷는 중`));else if(p.run===`failed`){let e=l(n,`div`,`wk-fail`);e.append(l(n,`b`,``,`실패`),l(n,`span`,``,` · `+p.reason)),t.append(e)}else if(p.result){let e=p.result;if(t.append(l(n,`div`,`wk-counts`,`노드 ${e.nodes.length} · 엣지 ${e.edges.length}`)),e.walk&&t.append(l(n,`div`,`wk-walk`,`요청 ${e.walk.hops_requested}홉 · 도달 ${e.walk.hops_reached}홉 · ${e.walk.direction}`)),e.cut&&t.append(l(n,`div`,`wk-trunc`,`절단됨 · ${e.truncated.reason}`)),e.nodes.length){let r=new Map;for(let t of e.nodes){let e=t.type||`—`;r.set(e,(r.get(e)||0)+1)}let i=l(n,`div`,`wk-dist`);i.append(l(n,`span`,`wk-distlabel`,`타입`));for(let[e,t]of[...r.entries()].sort((e,t)=>t[1]-e[1])){let r=l(n,`span`,`wk-distchip`+(p.collect.has(e)||p.collect.has(`${e}@1`)?` is-asked`:``));r.append(l(n,`b`,``,e),l(n,`span`,``,` ${t}`)),i.append(r)}t.append(i)}e.nodes.length||t.append(l(n,`div`,`wk-note`,e.message||`닿은 노드 없음`));for(let r of e.nodes.slice(0,200)){let e=l(n,`div`,`wk-row`);e.append(l(n,`span`,`wk-rowtype`,r.type||`—`)),e.append(l(n,`span`,`wk-rowlabel`,r.label||r.id||``)),t.append(e)}e.nodes.length>200&&t.append(l(n,`div`,`wk-note`,`이 아래 ${e.nodes.length-200} 개 안 그림`))}e.append(t)}function T(){i.textContent=``;let e=l(n,`div`,`wk-form`);if(p.declState===`loading`)e.append(l(n,`div`,`wk-note`,`선언 · 읽는 중`));else if(p.declState===`failed`){let t=l(n,`div`,`wk-fail`);t.append(l(n,`b`,``,`선언 못 읽음`),l(n,`span`,``,` · `+p.declReason));let r=l(n,`button`,`wk-go`,`다시`);r.type=`button`,r.addEventListener(`click`,E),e.append(t,r)}else C(e),w(e);i.append(e)}async function E(){p.declState=`loading`,T();let e=await t({apiBase:d,fetchImpl:u.fetchImpl});e&&e.ok?(p.decl=e,p.declState=`ready`):(p.declState=`failed`,p.declReason=e&&e.message||`알 수 없음`),T()}return E(),{state:p,spec:b,fire:x,render:T}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&n(async()=>{let{API_BASE:e}=await import(`./config-C6wMXuF6.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{u(document,e,{apiBase:t})})}