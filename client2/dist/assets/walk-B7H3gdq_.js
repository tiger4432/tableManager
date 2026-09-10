const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-C6wMXuF6.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-nTqwt3FA.js";import{_ as e,a as t,c as n,d as r,h as i,i as a,l as o,o as s,r as c,s as l,t as u,u as d,v as f,x as p}from"./preload-helper-DvgJlkt8.js";var m=`data-wk-styles`,h=`
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
`;function g(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${m}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(m,``),t.textContent=h,(e.head||e.documentElement).appendChild(t),!0}var _=[`both`,`outgoing`,`incoming`],v=`서버 기본`,y=e=>e==null?``:String(e),b=e=>e!==``&&Number.isFinite(Number(e)),x=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function S(u,m,h){let S=h||{},C=S.apiBase||``;g(u);let w=i({apiBase:C,fetchImpl:S.fetchImpl}),T={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,subjects:null,subjectsState:`idle`,subjectsReason:``,subjectsScanned:null,subjectsScanCut:!1,subjectsListCut:!1,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``},E=c,D=()=>T.decl&&T.decl.entities||[],O=e=>{let t=D().find(t=>t.type===e);return t&&t.keys||[]},k=()=>(T.decl&&T.decl.predicates||[]).map(e=>e.name),A=()=>{let e=T.decl&&T.decl.predicates||[];return T.type?s(e.filter(e=>(e.subjects||[]).includes(T.type)).map(e=>e.name),k(),T.follow):e.map(e=>e.name)};function j(){if(!T.decl||!T.type||!T.collect.size)return[];let e=[];for(let t of T.collect)for(let n of p(T.decl,E(T.type),E(t)))e.push({...n,to:E(t)});return n(D(),e).sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function M(){let e={type:T.type,keys:T.keys};T.follow.size&&(e.follow=[...T.follow]),T.collect.size&&(e.collect=[...T.collect]),T.direction&&(e.direction=T.direction);let t=parseInt(T.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(T.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function N(){if(!T.type)return;T.run=`running`,T.result=null,T.reason=``,R();let e=await w(M());e&&e.ok?(T.run=`done`,T.result=e):(T.run=`failed`,T.reason=e&&e.message||`알 수 없음`),R()}function P(e){let t=x(u,`div`,`wk-field`);return t.append(x(u,`div`,`wk-label`,e)),t}function F(e){let t=P(`노드 타입`),n=x(u,`select`,`wk-select`);n.append(x(u,`option`,``,`— 고르십시오 —`));for(let e of D()){let t=x(u,`option`,``,e.type);t.value=e.type,e.type===T.type&&(t.selected=!0),n.append(t)}if(n.addEventListener(`change`,()=>{T.type=n.value;let e=new Set(O(T.type));T.keys=Object.fromEntries(Object.entries(T.keys).filter(([t])=>e.has(t)));let t=new Set(A());T.follow=new Set([...T.follow].filter(e=>t.has(e))),T.result=null,T.run=`idle`,R(),z()}),t.append(n),e.append(t),T.type){let t=P(`주어 고르기`);if(T.subjectsState===`loading`)t.append(x(u,`div`,`wk-note`,`읽는 중`));else if(T.subjectsState===`failed`)t.append(x(u,`div`,`wk-fail`,`주어 목록 · ${T.subjectsReason}`));else if(T.subjectsState===`ready`){let e=T.subjects||[];if(!e.length)t.append(x(u,`div`,`wk-note`,T.subjectsScanCut?`주어를 다 못 봤습니다 (${T.subjectsScanned} 까지)`:`이 타입은 원장에 주어로 없습니다 (정적 허브)`));else{let n=x(u,`select`,`wk-select`);n.append(x(u,`option`,``,`— 고르거나 아래에 직접 —`)),e.forEach((e,t)=>{let r=Object.values(e.keys||{}).map(e=>String(e)).join(` · `),i=x(u,`option`,``,e.count?`${r}  (${e.count})`:r);i.value=String(t),n.append(i)}),n.addEventListener(`change`,()=>{let t=e[Number(n.value)];t&&(T.keys={...t.keys},R())}),t.append(n),T.subjectsListCut&&t.append(x(u,`div`,`wk-note`,`목록 ${e.length} · 이게 전부가 아닙니다 — 없으면 아래에 직접`))}}e.append(t)}let r=P(`키`),i=O(T.type);T.type?i.length||r.append(x(u,`div`,`wk-note`,`이 타입은 키가 없습니다`)):r.append(x(u,`div`,`wk-note`,`타입을 고르면 키가 나옵니다`));for(let e of i){let t=x(u,`label`,`wk-keyrow`);t.append(x(u,`span`,`wk-keyname`,e));let n=x(u,`input`,`wk-input`);n.type=`text`,n.value=T.keys[e]===void 0?``:T.keys[e],n.addEventListener(`input`,()=>{T.keys[e]=n.value}),t.append(n),r.append(t)}e.append(r);let a=P(`collect · 무엇을 가져오나`),o=D().map(e=>e.type);o.length||a.append(x(u,`div`,`wk-note`,`선언에 엔터티 없음`));for(let e of o){let t=x(u,`label`,`wk-check`+(T.collect.has(e)?` is-on`:``));t.setAttribute(`data-collect`,e);let n=x(u,`input`);n.type=`checkbox`,n.checked=T.collect.has(e),n.addEventListener(`change`,()=>{T.collect.has(e)?T.collect.delete(e):T.collect.add(e),R()}),t.append(n,x(u,`span`,``,e)),a.append(t)}if(o.length&&a.append(x(u,`div`,`wk-note`,`안 고르면 ${v} · 전부`)),e.append(a),T.type&&T.collect.size){let t=P(`경로 · 선언이 아는 길`),n=j();n.length||t.append(x(u,`div`,`wk-note`,`${E(T.type)} 에서 ${[...T.collect].map(E).join(` · `)} 로 가는 길 없음`));for(let e of n){let n=x(u,`button`,`wk-path`);n.type=`button`,n.append(x(u,`span`,`wk-pathto`,`→ ${e.to}`)),n.append(x(u,`span`,`wk-pathchain`,e.chain.join(` → `))),n.append(x(u,`span`,`wk-pathmeta`,`${e.hops}홉 · ${e.follow.join(`, `)}`)),n.addEventListener(`click`,()=>{T.follow=new Set(l(k(),e.follow)),T.hops=String(e.hops),R()}),t.append(n)}e.append(t)}let s=P(`follow · 어느 길로`),c=A();c.length||s.append(x(u,`div`,`wk-note`,T.type?`${T.type} 에서 나가는 술어 없음`:`선언에 술어 없음`));for(let e of c){let t=x(u,`label`,`wk-check`+(T.follow.has(e)?` is-on`:``));t.setAttribute(`data-follow`,e);let n=x(u,`input`);n.type=`checkbox`,n.checked=T.follow.has(e),n.addEventListener(`change`,()=>{T.follow.has(e)?T.follow.delete(e):T.follow.add(e),R()}),t.append(n,x(u,`span`,``,e)),s.append(t)}c.length&&s.append(x(u,`div`,`wk-note`,`안 고르면 ${v}`)),e.append(s);let d=P(`걸음`),f=x(u,`label`,`wk-keyrow`);f.append(x(u,`span`,`wk-keyname`,`direction`));let p=x(u,`select`,`wk-select`);p.append(x(u,`option`,``,v));for(let e of _){let t=x(u,`option`,``,e);t.value=e,e===T.direction&&(t.selected=!0),p.append(t)}p.addEventListener(`change`,()=>{T.direction=p.value}),f.append(p),d.append(f);for(let[e,t,n,r]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let i=x(u,`label`,`wk-keyrow`);i.append(x(u,`span`,`wk-keyname`,e));let a=x(u,`input`,`wk-input`);a.type=`number`,a.min=String(n),a.max=String(r),a.placeholder=v,a.value=T[t],a.addEventListener(`input`,()=>{T[t]=a.value}),i.append(a),d.append(i)}e.append(d);let m=x(u,`button`,`wk-go`,T.run===`running`?`걷는 중`:`날리기`);m.type=`button`,m.disabled=!T.type||T.run===`running`,m.addEventListener(`click`,N),e.append(m)}function I(e,t){let n=t.nodes.slice(0,200),i=new Map;for(let e of t.edges||[]){let t=e&&e.qualifiers;if(!t||typeof t!=`object`)continue;for(let t of[e.target,e.source])(!t||!i.has(t))&&i.set(t,i.get(t)||{});let n=i.get(e.target)||{};Object.assign(n,t),i.set(e.target,n)}let s=d(n);for(let[t,n]of s){let s=x(u,`div`,`wk-sec`);s.append(x(u,`div`,`wk-sechead`,o(t,n.length)));let c=[];for(let e of n)for(let t of Object.keys(i.get(e.id)||{}))c.includes(t)||c.push(t);let l=r(D(),t,c),d=x(u,`table`,`wk-table`),f=x(u,`thead`),p=x(u,`tr`);for(let e of l)p.append(x(u,`th`,``,e.name));f.append(p),d.append(f);let m=x(u,`tbody`);for(let e of n){let t=x(u,`tr`),n=i.get(e.id)||{};l.forEach(r=>{let i=y(a(r,e,n)),o=x(u,`td`,b(i)?`wk-num`:``,i);r.kind===`id`&&(o.className=`wk-id`),t.append(o)}),m.append(t)}d.append(m),s.append(d),e.append(s)}t.nodes.length>200&&e.append(x(u,`div`,`wk-note`,`이 아래 ${t.nodes.length-200} 개 안 그림`))}function L(e){if(T.run===`idle`)return;let n=x(u,`div`,`wk-result`);if(T.run===`running`)n.append(x(u,`div`,`wk-note`,`걷는 중`));else if(T.run===`failed`){let e=x(u,`div`,`wk-fail`);e.append(x(u,`b`,``,`실패`),x(u,`span`,``,` · `+T.reason)),n.append(e)}else if(T.result){let e=T.result,r=[...T.collect].map(E).join(`, `);if(n.append(x(u,`div`,`wk-counts`,r?`노드 ${e.nodes.length} (collect: ${r}) · 엣지 ${e.edges.length} (전부)`:`노드 ${e.nodes.length} · 엣지 ${e.edges.length}`)),e.walk&&n.append(x(u,`div`,`wk-walk`,`요청 ${e.walk.hops_requested}홉 · 도달 ${e.walk.hops_reached}홉 · ${e.walk.direction}`)),e.generatedAt&&n.append(x(u,`div`,`wk-note`,`기준 ${String(e.generatedAt)}`)),e.cut&&n.append(x(u,`div`,`wk-trunc`,`절단됨 · ${t(e.truncatedAxes,e.limits).join(` · `)}`)),e.nodes.length){let t=new Map;for(let n of e.nodes){let e=n.type||`—`;t.set(e,(t.get(e)||0)+1)}let r=x(u,`div`,`wk-dist`);r.append(x(u,`span`,`wk-distlabel`,`타입`));for(let[e,n]of[...t.entries()].sort((e,t)=>t[1]-e[1])){let t=x(u,`span`,`wk-distchip`+(T.collect.has(e)||T.collect.has(`${e}@1`)?` is-asked`:``));t.append(x(u,`b`,``,e),x(u,`span`,``,` ${n}`)),r.append(t)}n.append(r)}e.nodes.length||n.append(x(u,`div`,`wk-note`,e.message||`닿은 노드 없음`)),I(n,e)}e.append(n)}function R(){m.textContent=``;let e=x(u,`div`,`wk-form`);if(T.declState===`loading`)e.append(x(u,`div`,`wk-note`,`선언 · 읽는 중`));else if(T.declState===`failed`){let t=x(u,`div`,`wk-fail`);t.append(x(u,`b`,``,`선언 못 읽음`),x(u,`span`,``,` · `+T.declReason));let n=x(u,`button`,`wk-go`,`다시`);n.type=`button`,n.addEventListener(`click`,B),e.append(t,n)}else F(e),L(e);m.append(e)}async function z(){if(!T.type){T.subjectsState=`idle`,T.subjects=null;return}let e=T.type;T.subjectsState=`loading`,T.subjects=null,R();let t=await f({apiBase:C,fetchImpl:S.fetchImpl,type:e});T.type===e&&(t&&t.ok?(T.subjectsState=`ready`,T.subjects=t.subjects,T.subjectsScanned=t.scanned,T.subjectsScanCut=t.scanTruncated,T.subjectsListCut=t.valuesTruncated):(T.subjectsState=`failed`,T.subjectsReason=t&&t.message||`알 수 없음`),R())}async function B(){T.declState=`loading`,R();let t=await e({apiBase:C,fetchImpl:S.fetchImpl});t&&t.ok?(T.decl=t,T.declState=`ready`):(T.declState=`failed`,T.declReason=t&&t.message||`알 수 없음`),R()}return B(),{state:T,spec:M,fire:N,render:R}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&u(async()=>{let{API_BASE:e}=await import(`./config-C6wMXuF6.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{S(document,e,{apiBase:t})})}