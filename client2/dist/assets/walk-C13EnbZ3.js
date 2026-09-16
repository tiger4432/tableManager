const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-C6wMXuF6.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-C3JbmQ-D.js";import{A as e,C as t,D as n,E as r,O as i,S as a,T as o,a as s,c,d as l,j as u,k as d,s as f,t as p,w as m,x as h}from"./preload-helper-CSL-uNf_.js";var g=`data-wk-styles`,_=`
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
`;function v(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${g}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(g,``),t.textContent=_,(e.head||e.documentElement).appendChild(t),!0}function y(e){return e==null?``:String(e)}function b(e){return e!==``&&Number.isFinite(Number(e))}function x(e){let t=new Map;for(let n of e||[]){let e=n&&n.qualifiers;if(!e||typeof e!=`object`)continue;for(let e of[n.target,n.source])(!e||!t.has(e))&&t.set(e,t.get(e)||{});let r=t.get(n.target)||{};Object.assign(r,e),t.set(n.target,r)}return t}function S(e,t){let n=[];for(let r of e||[])for(let e of Object.keys(t&&t.get(r.id)||{}))n.includes(e)||n.push(e);return n}function C(n,r,o=[],s=200){let c=n&&n.nodes||[],l=c.slice(0,s),f=x(n&&n.edges||[]),p=[],m=i(n),h=t(o);for(let[t,n]of e(l)){let e=u(r,t,S(n,f),void 0,h);p.push({type:t,heading:d(t,n.length),columns:e,rows:n.map(t=>({id:t.id,cells:e.map(e=>{let n=y(a(e,t,f.get(t.id)||{},m.get(t.type)));return{text:n,kind:e.kind,numeric:b(n)}})}))})}return{sections:p,shown:l.length,hidden:Math.max(0,c.length-l.length)}}var w=[`both`,`outgoing`,`incoming`],T=`서버 기본`,E=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function D(e,t,i){let a=i||{},u=a.apiBase||``;v(e);let d=s({apiBase:u,fetchImpl:a.fetchImpl}),p={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,subjects:null,subjectsState:`idle`,subjectsReason:``,subjectsScanned:null,subjectsScanCut:!1,subjectsListCut:!1,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``},g=h,_=()=>p.decl&&p.decl.entities||[],y=e=>{let t=_().find(t=>t.type===e);return t&&t.keys||[]},b=()=>(p.decl&&p.decl.predicates||[]).map(e=>e.name),x=()=>{let e=p.decl&&p.decl.predicates||[];return p.type?o(e.filter(e=>(e.subjects||[]).includes(p.type)).map(e=>e.name),b(),p.follow):e.map(e=>e.name)};function S(){if(!p.decl||!p.type||!p.collect.size)return[];let e=[];for(let t of p.collect)for(let n of l(p.decl,g(p.type),g(t)))e.push({...n,to:g(t)});return n(_(),e).sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function D(){let e={type:p.type,keys:p.keys};p.follow.size&&(e.follow=[...p.follow]),p.collect.size&&(e.collect=[...p.collect]),p.direction&&(e.direction=p.direction);let t=parseInt(p.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(p.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function O(){if(!p.type)return;p.run=`running`,p.result=null,p.reason=``,N();let e=await d(D());e&&e.ok?(p.run=`done`,p.result=e):(p.run=`failed`,p.reason=e&&e.message||`알 수 없음`),N()}function k(t){let n=E(e,`div`,`wk-field`);return n.append(E(e,`div`,`wk-label`,t)),n}function A(t){let n=k(`노드 타입`),i=E(e,`select`,`wk-select`);i.append(E(e,`option`,``,`— 고르십시오 —`));for(let t of _()){let n=E(e,`option`,``,t.type);n.value=t.type,t.type===p.type&&(n.selected=!0),i.append(n)}if(i.addEventListener(`change`,()=>{p.type=i.value;let e=new Set(y(p.type));p.keys=Object.fromEntries(Object.entries(p.keys).filter(([t])=>e.has(t)));let t=new Set(x());p.follow=new Set([...p.follow].filter(e=>t.has(e))),p.result=null,p.run=`idle`,N(),P()}),n.append(i),t.append(n),p.type){let n=k(`주어 고르기`);if(p.subjectsState===`loading`)n.append(E(e,`div`,`wk-note`,`읽는 중`));else if(p.subjectsState===`failed`)n.append(E(e,`div`,`wk-fail`,`주어 목록 · ${p.subjectsReason}`));else if(p.subjectsState===`ready`){let t=p.subjects||[];if(!t.length)n.append(E(e,`div`,`wk-note`,p.subjectsScanCut?`주어를 다 못 봤습니다 (${p.subjectsScanned} 까지)`:`이 타입은 원장에 주어로 없습니다 (정적 허브)`));else{let r=E(e,`select`,`wk-select`);r.append(E(e,`option`,``,`— 고르거나 아래에 직접 —`)),t.forEach((t,n)=>{let i=Object.values(t.keys||{}).map(e=>String(e)).join(` · `),a=E(e,`option`,``,t.count?`${i}  (${t.count})`:i);a.value=String(n),r.append(a)}),r.addEventListener(`change`,()=>{let e=t[Number(r.value)];e&&(p.keys={...e.keys},N())}),n.append(r),p.subjectsListCut&&n.append(E(e,`div`,`wk-note`,`목록 ${t.length} · 이게 전부가 아닙니다 — 없으면 아래에 직접`))}}t.append(n)}let a=k(`키`),o=y(p.type);p.type?o.length||a.append(E(e,`div`,`wk-note`,`이 타입은 키가 없습니다`)):a.append(E(e,`div`,`wk-note`,`타입을 고르면 키가 나옵니다`));for(let t of o){let n=E(e,`label`,`wk-keyrow`);n.append(E(e,`span`,`wk-keyname`,t));let r=E(e,`input`,`wk-input`);r.type=`text`,r.value=p.keys[t]===void 0?``:p.keys[t],r.addEventListener(`input`,()=>{p.keys[t]=r.value}),n.append(r),a.append(n)}t.append(a);let s=k(`collect · 무엇을 가져오나`),c=_().map(e=>e.type);c.length||s.append(E(e,`div`,`wk-note`,`선언에 엔터티 없음`));for(let t of c){let n=E(e,`label`,`wk-check`+(p.collect.has(t)?` is-on`:``));n.setAttribute(`data-collect`,t);let r=E(e,`input`);r.type=`checkbox`,r.checked=p.collect.has(t),r.addEventListener(`change`,()=>{p.collect.has(t)?p.collect.delete(t):p.collect.add(t),N()}),n.append(r,E(e,`span`,``,t)),s.append(n)}if(c.length&&s.append(E(e,`div`,`wk-note`,`안 고르면 ${T} · 전부`)),t.append(s),p.type&&p.collect.size){let n=k(`경로 · 선언이 아는 길`),i=S();i.length||n.append(E(e,`div`,`wk-note`,`${g(p.type)} 에서 ${[...p.collect].map(g).join(` · `)} 로 가는 길 없음`));for(let t of i){let i=E(e,`button`,`wk-path`);i.type=`button`,i.append(E(e,`span`,`wk-pathto`,`→ ${t.to}`)),i.append(E(e,`span`,`wk-pathchain`,t.chain.join(` → `))),i.append(E(e,`span`,`wk-pathmeta`,`${t.hops}홉 · ${t.follow.join(`, `)}`)),i.addEventListener(`click`,()=>{p.follow=new Set(r(b(),t.follow)),p.hops=String(t.hops),N()}),n.append(i)}t.append(n)}let l=k(`follow · 어느 길로`),u=x();u.length||l.append(E(e,`div`,`wk-note`,p.type?`${p.type} 에서 나가는 술어 없음`:`선언에 술어 없음`));for(let t of u){let n=E(e,`label`,`wk-check`+(p.follow.has(t)?` is-on`:``));n.setAttribute(`data-follow`,t);let r=E(e,`input`);r.type=`checkbox`,r.checked=p.follow.has(t),r.addEventListener(`change`,()=>{p.follow.has(t)?p.follow.delete(t):p.follow.add(t),N()}),n.append(r,E(e,`span`,``,t)),l.append(n)}u.length&&l.append(E(e,`div`,`wk-note`,`안 고르면 ${T}`)),t.append(l);let d=k(`걸음`),f=E(e,`label`,`wk-keyrow`);f.append(E(e,`span`,`wk-keyname`,`direction`));let m=E(e,`select`,`wk-select`);m.append(E(e,`option`,``,T));for(let t of w){let n=E(e,`option`,``,t);n.value=t,t===p.direction&&(n.selected=!0),m.append(n)}m.addEventListener(`change`,()=>{p.direction=m.value}),f.append(m),d.append(f);for(let[t,n,r,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=E(e,`label`,`wk-keyrow`);a.append(E(e,`span`,`wk-keyname`,t));let o=E(e,`input`,`wk-input`);o.type=`number`,o.min=String(r),o.max=String(i),o.placeholder=T,o.value=p[n],o.addEventListener(`input`,()=>{p[n]=o.value}),a.append(o),d.append(a)}t.append(d);let h=E(e,`button`,`wk-go`,p.run===`running`?`걷는 중`:`날리기`);h.type=`button`,h.disabled=!p.type||p.run===`running`,h.addEventListener(`click`,O),t.append(h)}function j(t,n){let r=C(n,_(),p.decl&&p.decl.predicates||[]);for(let n of r.sections){let r=E(e,`div`,`wk-sec`);r.append(E(e,`div`,`wk-sechead`,n.heading));let i=E(e,`table`,`wk-table`),a=E(e,`thead`),o=E(e,`tr`);for(let t of n.columns)o.append(E(e,`th`,``,t.name));a.append(o),i.append(a);let s=E(e,`tbody`);for(let t of n.rows){let n=E(e,`tr`);for(let r of t.cells){let t=E(e,`td`,r.numeric?`wk-num`:``,r.text);r.kind===`id`&&(t.className=`wk-id`),n.append(t)}s.append(n)}i.append(s),r.append(i),t.append(r)}r.hidden&&t.append(E(e,`div`,`wk-note`,`이 아래 ${r.hidden} 개 안 그림`))}function M(t){if(p.run===`idle`)return;let n=E(e,`div`,`wk-result`);if(p.run===`running`)n.append(E(e,`div`,`wk-note`,`걷는 중`));else if(p.run===`failed`){let t=E(e,`div`,`wk-fail`);t.append(E(e,`b`,``,`실패`),E(e,`span`,``,` · `+p.reason)),n.append(t)}else if(p.result){let t=p.result,r=[...p.collect].map(g).join(`, `);if(n.append(E(e,`div`,`wk-counts`,r?`노드 ${t.nodes.length} (collect: ${r}) · 엣지 ${t.edges.length} (전부)`:`노드 ${t.nodes.length} · 엣지 ${t.edges.length}`)),t.walk&&n.append(E(e,`div`,`wk-walk`,`요청 ${t.walk.hops_requested}홉 · 도달 ${t.walk.hops_reached}홉 · ${t.walk.direction}`)),t.generatedAt&&n.append(E(e,`div`,`wk-note`,`기준 ${String(t.generatedAt)}`)),t.cut&&n.append(E(e,`div`,`wk-trunc`,`절단됨 · ${m(t.truncatedAxes,t.limits).join(` · `)}`)),t.nodes.length){let r=new Map;for(let e of t.nodes){let t=e.type||`—`;r.set(t,(r.get(t)||0)+1)}let i=E(e,`div`,`wk-dist`);i.append(E(e,`span`,`wk-distlabel`,`타입`));for(let[t,n]of[...r.entries()].sort((e,t)=>t[1]-e[1])){let r=E(e,`span`,`wk-distchip`+(p.collect.has(t)||p.collect.has(`${t}@1`)?` is-asked`:``));r.append(E(e,`b`,``,t),E(e,`span`,``,` ${n}`)),i.append(r)}n.append(i)}t.nodes.length||n.append(E(e,`div`,`wk-note`,t.message||`닿은 노드 없음`)),j(n,t)}t.append(n)}function N(){t.textContent=``;let n=E(e,`div`,`wk-form`);if(p.declState===`loading`)n.append(E(e,`div`,`wk-note`,`선언 · 읽는 중`));else if(p.declState===`failed`){let t=E(e,`div`,`wk-fail`);t.append(E(e,`b`,``,`선언 못 읽음`),E(e,`span`,``,` · `+p.declReason));let r=E(e,`button`,`wk-go`,`다시`);r.type=`button`,r.addEventListener(`click`,F),n.append(t,r)}else A(n),M(n);t.append(n)}async function P(){if(!p.type){p.subjectsState=`idle`,p.subjects=null;return}let e=p.type;p.subjectsState=`loading`,p.subjects=null,N();let t=await c({apiBase:u,fetchImpl:a.fetchImpl,type:e});p.type===e&&(t&&t.ok?(p.subjectsState=`ready`,p.subjects=t.subjects,p.subjectsScanned=t.scanned,p.subjectsScanCut=t.scanTruncated,p.subjectsListCut=t.valuesTruncated):(p.subjectsState=`failed`,p.subjectsReason=t&&t.message||`알 수 없음`),N())}async function F(){p.declState=`loading`,N();let e=await f({apiBase:u,fetchImpl:a.fetchImpl});e&&e.ok?(p.decl=e,p.declState=`ready`):(p.declState=`failed`,p.declReason=e&&e.message||`알 수 없음`),N()}return F(),{state:p,spec:D,fire:O,render:N}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&p(async()=>{let{API_BASE:e}=await import(`./config-C6wMXuF6.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{D(document,e,{apiBase:t})})}