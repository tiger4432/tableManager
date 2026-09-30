const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-CtEgmCQz.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-C9Rjx7_P.js";import{t as e}from"./disabled_reason-Cd0wapM5.js";import{A as t,D as n,E as r,M as i,N as a,O as o,P as s,T as c,j as l,k as u,l as d,m as f,r as p,s as m,t as h,u as g,w as _}from"./preload-helper-D9ZWOSCz.js";var v=`data-wk-styles`,y=`
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
   것만 그만둡니다 — 실측(480px 틀): 폼 1,623px 중 1,214px 가 체크박스 23줄이고, 줄마다
   438px 중 열 글자만 씁니다. 390px 휴대폰에서 「걸음」까지 두 화면 반을 내려야 했습니다.
   ⚠️ 고르는 상자만 고릅니다 — :has(.wk-check) 하나입니다. 키 줄과 걸음 손잡이는 체크박스가 없어서
      선택자에 «걸리지도» 않고, 그래서 렌더러는 한 글자도 안 바뀝니다.
   🔴 칸은 «자기 이름만큼» 자랍니다(flex 0 1 auto) — 고정 폭으로 나누면 긴 이름이 잘리고,
   잘린 이름은 읽을 방법이 없습니다(이 폼에 hover 가 없습니다 — 휴대폰입니다). 최소 9.5em 은
   손가락이 옆 칸을 안 누르게 하는 바닥이고, 화면보다 긴 이름만 마지막 수단으로 잘립니다. */
.wk-field:has(.wk-check) { flex-flow: row wrap; column-gap: 6px; }
.wk-field:has(.wk-check) > .wk-label,
.wk-field:has(.wk-check) > .wk-note { flex: 1 0 100%; }
.wk-check { flex: 0 1 auto; min-width: 9.5em; max-width: 100%; }
.wk-check > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

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
`;function b(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${v}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(v,``),t.textContent=y,(e.head||e.documentElement).appendChild(t),!0}function x(e){return e==null?``:String(e)}function S(e){return e!==``&&Number.isFinite(Number(e))}function C(e){let t=new Map;for(let n of e||[]){let e=n&&n.qualifiers;if(!e||typeof e!=`object`)continue;for(let e of[n.target,n.source])(!e||!t.has(e))&&t.set(e,t.get(e)||{});let r=t.get(n.target)||{};Object.assign(r,e),t.set(n.target,r)}return t}function w(e,t){let n=[];for(let r of e||[])for(let e of Object.keys(t&&t.get(r.id)||{}))n.includes(e)||n.push(e);return n}function T(e,t,n=[],o=200){let u=e&&e.nodes||[],d=u.slice(0,o),f=C(e&&e.edges||[]),p=[],m=l(e),h=r(n);for(let[e,n]of a(d)){let r=s(t,e,w(n,f),void 0,h);p.push({type:e,heading:i(e,n.length),columns:r,rows:n.map(e=>({id:e.id,cells:r.map(t=>{let n=x(c(t,e,f.get(e.id)||{},m.get(e.type)));return{text:n,kind:t.kind,numeric:S(n)}})}))})}return{sections:p,shown:d.length,hidden:Math.max(0,u.length-d.length)}}var E=`걷는 중`,D=[`both`,`outgoing`,`incoming`],O=`서버 기본`,k=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function A(r,i,a){let s=a||{},c=s.apiBase||``;b(r);let l=m({apiBase:c,fetchImpl:s.fetchImpl}),h={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,subjects:null,subjectsState:`idle`,subjectsReason:``,subjectsScanned:null,subjectsScanCut:!1,subjectsListCut:!1,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``},v=_,y=()=>h.decl&&h.decl.entities||[],x=e=>{let t=y().find(t=>t.type===e);return t&&t.keys||[]},S=()=>(h.decl&&h.decl.predicates||[]).map(e=>e.name),C=()=>{let e=h.decl&&h.decl.predicates||[];return h.type?o(e.filter(e=>(e.subjects||[]).includes(h.type)).map(e=>e.name),S(),h.follow):e.map(e=>e.name)};function w(){if(!h.decl||!h.type||!h.collect.size)return[];let e=[];for(let t of h.collect)for(let n of f(h.decl,v(h.type),v(t)))e.push({...n,to:v(t)});return t(y(),e).sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function A(){let e={type:h.type,keys:h.keys};h.follow.size&&(e.follow=[...h.follow]),h.collect.size&&(e.collect=[...h.collect]),h.direction&&(e.direction=h.direction);let t=parseInt(h.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(h.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function j(){if(!h.type)return;h.run=`running`,h.result=null,h.reason=``,I();let e=await l(A());e&&e.ok?(h.run=`done`,h.result=e):(h.run=`failed`,h.reason=e&&e.message||`알 수 없음`),I()}function M(e){let t=k(r,`div`,`wk-field`);return t.append(k(r,`div`,`wk-label`,e)),t}function N(t){let n=M(`노드 타입`),i=k(r,`select`,`wk-select`);i.append(k(r,`option`,``,`— 고르십시오 —`));for(let e of y()){let t=k(r,`option`,``,e.type);t.value=e.type,e.type===h.type&&(t.selected=!0),i.append(t)}if(i.addEventListener(`change`,()=>{h.type=i.value;let e=new Set(x(h.type));h.keys=Object.fromEntries(Object.entries(h.keys).filter(([t])=>e.has(t)));let t=new Set(C());h.follow=new Set([...h.follow].filter(e=>t.has(e))),h.result=null,h.run=`idle`,I(),L()}),n.append(i),t.append(n),h.type){let e=M(`주어 고르기`);if(h.subjectsState===`loading`)e.append(k(r,`div`,`wk-note`,`읽는 중`));else if(h.subjectsState===`failed`)e.append(k(r,`div`,`wk-fail`,`주어 목록 · ${h.subjectsReason}`));else if(h.subjectsState===`ready`){let t=h.subjects||[];if(!t.length)e.append(k(r,`div`,`wk-note`,h.subjectsScanCut?`주어를 다 못 봤습니다 (${h.subjectsScanned} 까지)`:`이 타입은 원장에 주어로 없습니다 (정적 허브)`));else{let n=k(r,`select`,`wk-select`);n.append(k(r,`option`,``,`— 고르거나 아래에 직접 —`)),t.forEach((e,t)=>{let i=Object.values(e.keys||{}).map(e=>String(e)).join(` · `),a=k(r,`option`,``,e.count?`${i}  (${e.count})`:i);a.value=String(t),n.append(a)}),n.addEventListener(`change`,()=>{let e=t[Number(n.value)];e&&(h.keys={...e.keys},I())}),e.append(n),h.subjectsListCut&&e.append(k(r,`div`,`wk-note`,`목록 ${t.length} · 이게 전부가 아닙니다 — 없으면 아래에 직접`))}}t.append(e)}let a=M(`키`),o=x(h.type);h.type?o.length||a.append(k(r,`div`,`wk-note`,`이 타입은 키가 없습니다`)):a.append(k(r,`div`,`wk-note`,`타입을 고르면 키가 나옵니다`));for(let e of o){let t=k(r,`label`,`wk-keyrow`);t.append(k(r,`span`,`wk-keyname`,e));let n=k(r,`input`,`wk-input`);n.type=`text`,n.value=h.keys[e]===void 0?``:h.keys[e],n.addEventListener(`input`,()=>{h.keys[e]=n.value}),t.append(n),a.append(t)}t.append(a);let s=M(`collect · 무엇을 가져오나`),c=y().map(e=>e.type);c.length||s.append(k(r,`div`,`wk-note`,`선언에 엔터티 없음`));for(let e of c){let t=k(r,`label`,`wk-check`+(h.collect.has(e)?` is-on`:``));t.setAttribute(`data-collect`,e);let n=k(r,`input`);n.type=`checkbox`,n.checked=h.collect.has(e),n.addEventListener(`change`,()=>{h.collect.has(e)?h.collect.delete(e):h.collect.add(e),I()}),t.append(n,k(r,`span`,``,e)),s.append(t)}if(c.length&&s.append(k(r,`div`,`wk-note`,`안 고르면 ${O} · 전부`)),t.append(s),h.type&&h.collect.size){let e=M(`경로 · 선언이 아는 길`),n=w();n.length||e.append(k(r,`div`,`wk-note`,`${v(h.type)} 에서 ${[...h.collect].map(v).join(` · `)} 로 가는 길 없음`));for(let t of n){let n=k(r,`button`,`wk-path`);n.type=`button`,n.append(k(r,`span`,`wk-pathto`,`→ ${t.to}`)),n.append(k(r,`span`,`wk-pathchain`,t.chain.join(` → `))),n.append(k(r,`span`,`wk-pathmeta`,`${t.hops}홉 · ${t.follow.join(`, `)}`)),n.addEventListener(`click`,()=>{h.follow=new Set(u(S(),t.follow)),h.hops=String(t.hops),I()}),e.append(n)}t.append(e)}let l=M(`follow · 어느 길로`),d=C();d.length||l.append(k(r,`div`,`wk-note`,h.type?`${h.type} 에서 나가는 술어 없음`:`선언에 술어 없음`));for(let e of d){let t=k(r,`label`,`wk-check`+(h.follow.has(e)?` is-on`:``));t.setAttribute(`data-follow`,e);let n=k(r,`input`);n.type=`checkbox`,n.checked=h.follow.has(e),n.addEventListener(`change`,()=>{h.follow.has(e)?h.follow.delete(e):h.follow.add(e),I()}),t.append(n,k(r,`span`,``,e)),l.append(t)}d.length&&l.append(k(r,`div`,`wk-note`,`안 고르면 ${O}`)),t.append(l);let f=M(`걸음`),m=k(r,`label`,`wk-keyrow`);m.append(k(r,`span`,`wk-keyname`,`direction`));let g=k(r,`select`,`wk-select`);g.append(k(r,`option`,``,O));for(let e of D){let t=k(r,`option`,``,e);t.value=e,e===h.direction&&(t.selected=!0),g.append(t)}g.addEventListener(`change`,()=>{h.direction=g.value}),m.append(g),f.append(m);for(let[e,t,n,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=k(r,`label`,`wk-keyrow`);a.append(k(r,`span`,`wk-keyname`,e));let o=k(r,`input`,`wk-input`);o.type=`number`,o.min=String(n),o.max=String(i),o.placeholder=O,o.value=h[t],o.addEventListener(`input`,()=>{h[t]=o.value}),a.append(o),f.append(a)}t.append(f);let _=k(r,`button`,`wk-go`,h.run===`running`?E:`날리기`);_.type=`button`,e(_,h.run===`running`?E:h.type?``:p),_.addEventListener(`click`,j),t.append(_)}function P(e,t){let n=T(t,y(),h.decl&&h.decl.predicates||[]);for(let t of n.sections){let n=k(r,`div`,`wk-sec`);n.append(k(r,`div`,`wk-sechead`,t.heading));let i=k(r,`table`,`wk-table`),a=k(r,`thead`),o=k(r,`tr`);for(let e of t.columns)o.append(k(r,`th`,``,e.name));a.append(o),i.append(a);let s=k(r,`tbody`);for(let e of t.rows){let t=k(r,`tr`);for(let n of e.cells){let e=k(r,`td`,n.numeric?`wk-num`:``,n.text);n.kind===`id`&&(e.className=`wk-id`),t.append(e)}s.append(t)}i.append(s),n.append(i),e.append(n)}n.hidden&&e.append(k(r,`div`,`wk-note`,`이 아래 ${n.hidden} 개 안 그림`))}function F(e){if(h.run===`idle`)return;let t=k(r,`div`,`wk-result`);if(h.run===`running`)t.append(k(r,`div`,`wk-note`,`걷는 중`));else if(h.run===`failed`){let e=k(r,`div`,`wk-fail`);e.append(k(r,`b`,``,`실패`),k(r,`span`,``,` · `+h.reason)),t.append(e)}else if(h.result){let e=h.result,i=[...h.collect].map(v).join(`, `);if(t.append(k(r,`div`,`wk-counts`,i?`노드 ${e.nodes.length} (collect: ${i}) · 엣지 ${e.edges.length} (전부)`:`노드 ${e.nodes.length} · 엣지 ${e.edges.length}`)),e.walk&&t.append(k(r,`div`,`wk-walk`,`요청 ${e.walk.hops_requested}홉 · 도달 ${e.walk.hops_reached}홉 · ${e.walk.direction}`)),e.generatedAt&&t.append(k(r,`div`,`wk-note`,`기준 ${String(e.generatedAt)}`)),e.cut&&t.append(k(r,`div`,`wk-trunc`,`절단됨 · ${n(e.truncatedAxes,e.limits).join(` · `)}`)),e.nodes.length){let n=new Map;for(let t of e.nodes){let e=t.type||`—`;n.set(e,(n.get(e)||0)+1)}let i=k(r,`div`,`wk-dist`);i.append(k(r,`span`,`wk-distlabel`,`타입`));for(let[e,t]of[...n.entries()].sort((e,t)=>t[1]-e[1])){let n=k(r,`span`,`wk-distchip`+(h.collect.has(e)||h.collect.has(`${e}@1`)?` is-asked`:``));n.append(k(r,`b`,``,e),k(r,`span`,``,` ${t}`)),i.append(n)}t.append(i)}e.nodes.length||t.append(k(r,`div`,`wk-note`,e.message||`닿은 노드 없음`)),P(t,e)}e.append(t)}function I(){i.textContent=``;let e=k(r,`div`,`wk-form`);if(h.declState===`loading`)e.append(k(r,`div`,`wk-note`,`선언 · 읽는 중`));else if(h.declState===`failed`){let t=k(r,`div`,`wk-fail`);t.append(k(r,`b`,``,`선언 못 읽음`),k(r,`span`,``,` · `+h.declReason));let n=k(r,`button`,`wk-go`,`다시`);n.type=`button`,n.addEventListener(`click`,R),e.append(t,n)}else N(e),F(e);i.append(e)}async function L(){if(!h.type){h.subjectsState=`idle`,h.subjects=null;return}let e=h.type;h.subjectsState=`loading`,h.subjects=null,I();let t=await g({apiBase:c,fetchImpl:s.fetchImpl,type:e});h.type===e&&(t&&t.ok?(h.subjectsState=`ready`,h.subjects=t.subjects,h.subjectsScanned=t.scanned,h.subjectsScanCut=t.scanTruncated,h.subjectsListCut=t.valuesTruncated):(h.subjectsState=`failed`,h.subjectsReason=t&&t.message||`알 수 없음`),I())}async function R(){h.declState=`loading`,I();let e=await d({apiBase:c,fetchImpl:s.fetchImpl});e&&e.ok?(h.decl=e,h.declState=`ready`):(h.declState=`failed`,h.declReason=e&&e.message||`알 수 없음`),I()}return R(),{state:h,spec:A,fire:j,render:I}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&h(async()=>{let{API_BASE:e}=await import(`./config-CtEgmCQz.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{A(document,e,{apiBase:t})})}