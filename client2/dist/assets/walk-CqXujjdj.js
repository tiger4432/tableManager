const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-C6wMXuF6.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-C3JbmQ-D.js";import{t as e}from"./disabled_reason-BCuzM_C1.js";import{A as t,C as n,D as r,E as i,M as a,O as o,S as s,T as c,c as l,f as u,j as d,k as f,l as p,o as m,r as h,t as g,w as _}from"./preload-helper-DO7G1RZR.js";var v=`data-wk-styles`,y=`
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
`;function b(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${v}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(v,``),t.textContent=y,(e.head||e.documentElement).appendChild(t),!0}function x(e){return e==null?``:String(e)}function S(e){return e!==``&&Number.isFinite(Number(e))}function C(e){let t=new Map;for(let n of e||[]){let e=n&&n.qualifiers;if(!e||typeof e!=`object`)continue;for(let e of[n.target,n.source])(!e||!t.has(e))&&t.set(e,t.get(e)||{});let r=t.get(n.target)||{};Object.assign(r,e),t.set(n.target,r)}return t}function w(e,t){let n=[];for(let r of e||[])for(let e of Object.keys(t&&t.get(r.id)||{}))n.includes(e)||n.push(e);return n}function T(e,r,i=[],o=200){let s=e&&e.nodes||[],c=s.slice(0,o),l=C(e&&e.edges||[]),u=[],p=f(e),m=_(i);for(let[e,i]of d(c)){let o=a(r,e,w(i,l),void 0,m);u.push({type:e,heading:t(e,i.length),columns:o,rows:i.map(e=>({id:e.id,cells:o.map(t=>{let r=x(n(t,e,l.get(e.id)||{},p.get(e.type)));return{text:r,kind:t.kind,numeric:S(r)}})}))})}return{sections:u,shown:c.length,hidden:Math.max(0,s.length-c.length)}}var E=`걷는 중`,D=[`both`,`outgoing`,`incoming`],O=`서버 기본`,k=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function A(t,n,a){let d=a||{},f=d.apiBase||``;b(t);let g=m({apiBase:f,fetchImpl:d.fetchImpl}),_={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,subjects:null,subjectsState:`idle`,subjectsReason:``,subjectsScanned:null,subjectsScanCut:!1,subjectsListCut:!1,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``},v=s,y=()=>_.decl&&_.decl.entities||[],x=e=>{let t=y().find(t=>t.type===e);return t&&t.keys||[]},S=()=>(_.decl&&_.decl.predicates||[]).map(e=>e.name),C=()=>{let e=_.decl&&_.decl.predicates||[];return _.type?i(e.filter(e=>(e.subjects||[]).includes(_.type)).map(e=>e.name),S(),_.follow):e.map(e=>e.name)};function w(){if(!_.decl||!_.type||!_.collect.size)return[];let e=[];for(let t of _.collect)for(let n of u(_.decl,v(_.type),v(t)))e.push({...n,to:v(t)});return o(y(),e).sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function A(){let e={type:_.type,keys:_.keys};_.follow.size&&(e.follow=[..._.follow]),_.collect.size&&(e.collect=[..._.collect]),_.direction&&(e.direction=_.direction);let t=parseInt(_.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(_.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function j(){if(!_.type)return;_.run=`running`,_.result=null,_.reason=``,I();let e=await g(A());e&&e.ok?(_.run=`done`,_.result=e):(_.run=`failed`,_.reason=e&&e.message||`알 수 없음`),I()}function M(e){let n=k(t,`div`,`wk-field`);return n.append(k(t,`div`,`wk-label`,e)),n}function N(n){let i=M(`노드 타입`),a=k(t,`select`,`wk-select`);a.append(k(t,`option`,``,`— 고르십시오 —`));for(let e of y()){let n=k(t,`option`,``,e.type);n.value=e.type,e.type===_.type&&(n.selected=!0),a.append(n)}if(a.addEventListener(`change`,()=>{_.type=a.value;let e=new Set(x(_.type));_.keys=Object.fromEntries(Object.entries(_.keys).filter(([t])=>e.has(t)));let t=new Set(C());_.follow=new Set([..._.follow].filter(e=>t.has(e))),_.result=null,_.run=`idle`,I(),L()}),i.append(a),n.append(i),_.type){let e=M(`주어 고르기`);if(_.subjectsState===`loading`)e.append(k(t,`div`,`wk-note`,`읽는 중`));else if(_.subjectsState===`failed`)e.append(k(t,`div`,`wk-fail`,`주어 목록 · ${_.subjectsReason}`));else if(_.subjectsState===`ready`){let n=_.subjects||[];if(!n.length)e.append(k(t,`div`,`wk-note`,_.subjectsScanCut?`주어를 다 못 봤습니다 (${_.subjectsScanned} 까지)`:`이 타입은 원장에 주어로 없습니다 (정적 허브)`));else{let r=k(t,`select`,`wk-select`);r.append(k(t,`option`,``,`— 고르거나 아래에 직접 —`)),n.forEach((e,n)=>{let i=Object.values(e.keys||{}).map(e=>String(e)).join(` · `),a=k(t,`option`,``,e.count?`${i}  (${e.count})`:i);a.value=String(n),r.append(a)}),r.addEventListener(`change`,()=>{let e=n[Number(r.value)];e&&(_.keys={...e.keys},I())}),e.append(r),_.subjectsListCut&&e.append(k(t,`div`,`wk-note`,`목록 ${n.length} · 이게 전부가 아닙니다 — 없으면 아래에 직접`))}}n.append(e)}let o=M(`키`),s=x(_.type);_.type?s.length||o.append(k(t,`div`,`wk-note`,`이 타입은 키가 없습니다`)):o.append(k(t,`div`,`wk-note`,`타입을 고르면 키가 나옵니다`));for(let e of s){let n=k(t,`label`,`wk-keyrow`);n.append(k(t,`span`,`wk-keyname`,e));let r=k(t,`input`,`wk-input`);r.type=`text`,r.value=_.keys[e]===void 0?``:_.keys[e],r.addEventListener(`input`,()=>{_.keys[e]=r.value}),n.append(r),o.append(n)}n.append(o);let c=M(`collect · 무엇을 가져오나`),l=y().map(e=>e.type);l.length||c.append(k(t,`div`,`wk-note`,`선언에 엔터티 없음`));for(let e of l){let n=k(t,`label`,`wk-check`+(_.collect.has(e)?` is-on`:``));n.setAttribute(`data-collect`,e);let r=k(t,`input`);r.type=`checkbox`,r.checked=_.collect.has(e),r.addEventListener(`change`,()=>{_.collect.has(e)?_.collect.delete(e):_.collect.add(e),I()}),n.append(r,k(t,`span`,``,e)),c.append(n)}if(l.length&&c.append(k(t,`div`,`wk-note`,`안 고르면 ${O} · 전부`)),n.append(c),_.type&&_.collect.size){let e=M(`경로 · 선언이 아는 길`),i=w();i.length||e.append(k(t,`div`,`wk-note`,`${v(_.type)} 에서 ${[..._.collect].map(v).join(` · `)} 로 가는 길 없음`));for(let n of i){let i=k(t,`button`,`wk-path`);i.type=`button`,i.append(k(t,`span`,`wk-pathto`,`→ ${n.to}`)),i.append(k(t,`span`,`wk-pathchain`,n.chain.join(` → `))),i.append(k(t,`span`,`wk-pathmeta`,`${n.hops}홉 · ${n.follow.join(`, `)}`)),i.addEventListener(`click`,()=>{_.follow=new Set(r(S(),n.follow)),_.hops=String(n.hops),I()}),e.append(i)}n.append(e)}let u=M(`follow · 어느 길로`),d=C();d.length||u.append(k(t,`div`,`wk-note`,_.type?`${_.type} 에서 나가는 술어 없음`:`선언에 술어 없음`));for(let e of d){let n=k(t,`label`,`wk-check`+(_.follow.has(e)?` is-on`:``));n.setAttribute(`data-follow`,e);let r=k(t,`input`);r.type=`checkbox`,r.checked=_.follow.has(e),r.addEventListener(`change`,()=>{_.follow.has(e)?_.follow.delete(e):_.follow.add(e),I()}),n.append(r,k(t,`span`,``,e)),u.append(n)}d.length&&u.append(k(t,`div`,`wk-note`,`안 고르면 ${O}`)),n.append(u);let f=M(`걸음`),p=k(t,`label`,`wk-keyrow`);p.append(k(t,`span`,`wk-keyname`,`direction`));let m=k(t,`select`,`wk-select`);m.append(k(t,`option`,``,O));for(let e of D){let n=k(t,`option`,``,e);n.value=e,e===_.direction&&(n.selected=!0),m.append(n)}m.addEventListener(`change`,()=>{_.direction=m.value}),p.append(m),f.append(p);for(let[e,n,r,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=k(t,`label`,`wk-keyrow`);a.append(k(t,`span`,`wk-keyname`,e));let o=k(t,`input`,`wk-input`);o.type=`number`,o.min=String(r),o.max=String(i),o.placeholder=O,o.value=_[n],o.addEventListener(`input`,()=>{_[n]=o.value}),a.append(o),f.append(a)}n.append(f);let g=k(t,`button`,`wk-go`,_.run===`running`?E:`날리기`);g.type=`button`,e(g,_.run===`running`?E:_.type?``:h),g.addEventListener(`click`,j),n.append(g)}function P(e,n){let r=T(n,y(),_.decl&&_.decl.predicates||[]);for(let n of r.sections){let r=k(t,`div`,`wk-sec`);r.append(k(t,`div`,`wk-sechead`,n.heading));let i=k(t,`table`,`wk-table`),a=k(t,`thead`),o=k(t,`tr`);for(let e of n.columns)o.append(k(t,`th`,``,e.name));a.append(o),i.append(a);let s=k(t,`tbody`);for(let e of n.rows){let n=k(t,`tr`);for(let r of e.cells){let e=k(t,`td`,r.numeric?`wk-num`:``,r.text);r.kind===`id`&&(e.className=`wk-id`),n.append(e)}s.append(n)}i.append(s),r.append(i),e.append(r)}r.hidden&&e.append(k(t,`div`,`wk-note`,`이 아래 ${r.hidden} 개 안 그림`))}function F(e){if(_.run===`idle`)return;let n=k(t,`div`,`wk-result`);if(_.run===`running`)n.append(k(t,`div`,`wk-note`,`걷는 중`));else if(_.run===`failed`){let e=k(t,`div`,`wk-fail`);e.append(k(t,`b`,``,`실패`),k(t,`span`,``,` · `+_.reason)),n.append(e)}else if(_.result){let e=_.result,r=[..._.collect].map(v).join(`, `);if(n.append(k(t,`div`,`wk-counts`,r?`노드 ${e.nodes.length} (collect: ${r}) · 엣지 ${e.edges.length} (전부)`:`노드 ${e.nodes.length} · 엣지 ${e.edges.length}`)),e.walk&&n.append(k(t,`div`,`wk-walk`,`요청 ${e.walk.hops_requested}홉 · 도달 ${e.walk.hops_reached}홉 · ${e.walk.direction}`)),e.generatedAt&&n.append(k(t,`div`,`wk-note`,`기준 ${String(e.generatedAt)}`)),e.cut&&n.append(k(t,`div`,`wk-trunc`,`절단됨 · ${c(e.truncatedAxes,e.limits).join(` · `)}`)),e.nodes.length){let r=new Map;for(let t of e.nodes){let e=t.type||`—`;r.set(e,(r.get(e)||0)+1)}let i=k(t,`div`,`wk-dist`);i.append(k(t,`span`,`wk-distlabel`,`타입`));for(let[e,n]of[...r.entries()].sort((e,t)=>t[1]-e[1])){let r=k(t,`span`,`wk-distchip`+(_.collect.has(e)||_.collect.has(`${e}@1`)?` is-asked`:``));r.append(k(t,`b`,``,e),k(t,`span`,``,` ${n}`)),i.append(r)}n.append(i)}e.nodes.length||n.append(k(t,`div`,`wk-note`,e.message||`닿은 노드 없음`)),P(n,e)}e.append(n)}function I(){n.textContent=``;let e=k(t,`div`,`wk-form`);if(_.declState===`loading`)e.append(k(t,`div`,`wk-note`,`선언 · 읽는 중`));else if(_.declState===`failed`){let n=k(t,`div`,`wk-fail`);n.append(k(t,`b`,``,`선언 못 읽음`),k(t,`span`,``,` · `+_.declReason));let r=k(t,`button`,`wk-go`,`다시`);r.type=`button`,r.addEventListener(`click`,R),e.append(n,r)}else N(e),F(e);n.append(e)}async function L(){if(!_.type){_.subjectsState=`idle`,_.subjects=null;return}let e=_.type;_.subjectsState=`loading`,_.subjects=null,I();let t=await p({apiBase:f,fetchImpl:d.fetchImpl,type:e});_.type===e&&(t&&t.ok?(_.subjectsState=`ready`,_.subjects=t.subjects,_.subjectsScanned=t.scanned,_.subjectsScanCut=t.scanTruncated,_.subjectsListCut=t.valuesTruncated):(_.subjectsState=`failed`,_.subjectsReason=t&&t.message||`알 수 없음`),I())}async function R(){_.declState=`loading`,I();let e=await l({apiBase:f,fetchImpl:d.fetchImpl});e&&e.ok?(_.decl=e,_.declState=`ready`):(_.declState=`failed`,_.declReason=e&&e.message||`알 수 없음`),I()}return R(),{state:_,spec:A,fire:j,render:I}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&g(async()=>{let{API_BASE:e}=await import(`./config-C6wMXuF6.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{A(document,e,{apiBase:t})})}