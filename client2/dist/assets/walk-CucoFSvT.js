const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-C6wMXuF6.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-HUps0QzO.js";import{A as e,C as t,D as n,E as r,O as i,S as a,T as o,a as s,c,d as l,k as u,s as d,t as f,w as p,x as m}from"./preload-helper-rH28oKiQ.js";var h=`data-wk-styles`,g=`
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
`;function _(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${h}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(h,``),t.textContent=g,(e.head||e.documentElement).appendChild(t),!0}function v(e){return e==null?``:String(e)}function y(e){return e!==``&&Number.isFinite(Number(e))}function b(e){let t=new Map;for(let n of e||[]){let e=n&&n.qualifiers;if(!e||typeof e!=`object`)continue;for(let e of[n.target,n.source])(!e||!t.has(e))&&t.set(e,t.get(e)||{});let r=t.get(n.target)||{};Object.assign(r,e),t.set(n.target,r)}return t}function x(e,t){let n=[];for(let r of e||[])for(let e of Object.keys(t&&t.get(r.id)||{}))n.includes(e)||n.push(e);return n}function S(t,r,o=200){let s=t&&t.nodes||[],c=s.slice(0,o),l=b(t&&t.edges||[]),d=[],f=n(t);for(let[t,n]of u(c)){let o=e(r,t,x(n,l));d.push({type:t,heading:i(t,n.length),columns:o,rows:n.map(e=>({id:e.id,cells:o.map(t=>{let n=v(a(t,e,l.get(e.id)||{},f.get(e.type)));return{text:n,kind:t.kind,numeric:y(n)}})}))})}return{sections:d,shown:c.length,hidden:Math.max(0,s.length-c.length)}}var C=[`both`,`outgoing`,`incoming`],w=`서버 기본`,T=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function E(e,n,i){let a=i||{},u=a.apiBase||``;_(e);let f=s({apiBase:u,fetchImpl:a.fetchImpl}),h={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,collect:new Set,subjects:null,subjectsState:`idle`,subjectsReason:``,subjectsScanned:null,subjectsScanCut:!1,subjectsListCut:!1,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``},g=m,v=()=>h.decl&&h.decl.entities||[],y=e=>{let t=v().find(t=>t.type===e);return t&&t.keys||[]},b=()=>(h.decl&&h.decl.predicates||[]).map(e=>e.name),x=()=>{let e=h.decl&&h.decl.predicates||[];return h.type?p(e.filter(e=>(e.subjects||[]).includes(h.type)).map(e=>e.name),b(),h.follow):e.map(e=>e.name)};function E(){if(!h.decl||!h.type||!h.collect.size)return[];let e=[];for(let t of h.collect)for(let n of l(h.decl,g(h.type),g(t)))e.push({...n,to:g(t)});return r(v(),e).sort((e,t)=>e.hops-t.hops||e.follow.length-t.follow.length)}function D(){let e={type:h.type,keys:h.keys};h.follow.size&&(e.follow=[...h.follow]),h.collect.size&&(e.collect=[...h.collect]),h.direction&&(e.direction=h.direction);let t=parseInt(h.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(h.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function O(){if(!h.type)return;h.run=`running`,h.result=null,h.reason=``,N();let e=await f(D());e&&e.ok?(h.run=`done`,h.result=e):(h.run=`failed`,h.reason=e&&e.message||`알 수 없음`),N()}function k(t){let n=T(e,`div`,`wk-field`);return n.append(T(e,`div`,`wk-label`,t)),n}function A(t){let n=k(`노드 타입`),r=T(e,`select`,`wk-select`);r.append(T(e,`option`,``,`— 고르십시오 —`));for(let t of v()){let n=T(e,`option`,``,t.type);n.value=t.type,t.type===h.type&&(n.selected=!0),r.append(n)}if(r.addEventListener(`change`,()=>{h.type=r.value;let e=new Set(y(h.type));h.keys=Object.fromEntries(Object.entries(h.keys).filter(([t])=>e.has(t)));let t=new Set(x());h.follow=new Set([...h.follow].filter(e=>t.has(e))),h.result=null,h.run=`idle`,N(),P()}),n.append(r),t.append(n),h.type){let n=k(`주어 고르기`);if(h.subjectsState===`loading`)n.append(T(e,`div`,`wk-note`,`읽는 중`));else if(h.subjectsState===`failed`)n.append(T(e,`div`,`wk-fail`,`주어 목록 · ${h.subjectsReason}`));else if(h.subjectsState===`ready`){let t=h.subjects||[];if(!t.length)n.append(T(e,`div`,`wk-note`,h.subjectsScanCut?`주어를 다 못 봤습니다 (${h.subjectsScanned} 까지)`:`이 타입은 원장에 주어로 없습니다 (정적 허브)`));else{let r=T(e,`select`,`wk-select`);r.append(T(e,`option`,``,`— 고르거나 아래에 직접 —`)),t.forEach((t,n)=>{let i=Object.values(t.keys||{}).map(e=>String(e)).join(` · `),a=T(e,`option`,``,t.count?`${i}  (${t.count})`:i);a.value=String(n),r.append(a)}),r.addEventListener(`change`,()=>{let e=t[Number(r.value)];e&&(h.keys={...e.keys},N())}),n.append(r),h.subjectsListCut&&n.append(T(e,`div`,`wk-note`,`목록 ${t.length} · 이게 전부가 아닙니다 — 없으면 아래에 직접`))}}t.append(n)}let i=k(`키`),a=y(h.type);h.type?a.length||i.append(T(e,`div`,`wk-note`,`이 타입은 키가 없습니다`)):i.append(T(e,`div`,`wk-note`,`타입을 고르면 키가 나옵니다`));for(let t of a){let n=T(e,`label`,`wk-keyrow`);n.append(T(e,`span`,`wk-keyname`,t));let r=T(e,`input`,`wk-input`);r.type=`text`,r.value=h.keys[t]===void 0?``:h.keys[t],r.addEventListener(`input`,()=>{h.keys[t]=r.value}),n.append(r),i.append(n)}t.append(i);let s=k(`collect · 무엇을 가져오나`),c=v().map(e=>e.type);c.length||s.append(T(e,`div`,`wk-note`,`선언에 엔터티 없음`));for(let t of c){let n=T(e,`label`,`wk-check`+(h.collect.has(t)?` is-on`:``));n.setAttribute(`data-collect`,t);let r=T(e,`input`);r.type=`checkbox`,r.checked=h.collect.has(t),r.addEventListener(`change`,()=>{h.collect.has(t)?h.collect.delete(t):h.collect.add(t),N()}),n.append(r,T(e,`span`,``,t)),s.append(n)}if(c.length&&s.append(T(e,`div`,`wk-note`,`안 고르면 ${w} · 전부`)),t.append(s),h.type&&h.collect.size){let n=k(`경로 · 선언이 아는 길`),r=E();r.length||n.append(T(e,`div`,`wk-note`,`${g(h.type)} 에서 ${[...h.collect].map(g).join(` · `)} 로 가는 길 없음`));for(let t of r){let r=T(e,`button`,`wk-path`);r.type=`button`,r.append(T(e,`span`,`wk-pathto`,`→ ${t.to}`)),r.append(T(e,`span`,`wk-pathchain`,t.chain.join(` → `))),r.append(T(e,`span`,`wk-pathmeta`,`${t.hops}홉 · ${t.follow.join(`, `)}`)),r.addEventListener(`click`,()=>{h.follow=new Set(o(b(),t.follow)),h.hops=String(t.hops),N()}),n.append(r)}t.append(n)}let l=k(`follow · 어느 길로`),u=x();u.length||l.append(T(e,`div`,`wk-note`,h.type?`${h.type} 에서 나가는 술어 없음`:`선언에 술어 없음`));for(let t of u){let n=T(e,`label`,`wk-check`+(h.follow.has(t)?` is-on`:``));n.setAttribute(`data-follow`,t);let r=T(e,`input`);r.type=`checkbox`,r.checked=h.follow.has(t),r.addEventListener(`change`,()=>{h.follow.has(t)?h.follow.delete(t):h.follow.add(t),N()}),n.append(r,T(e,`span`,``,t)),l.append(n)}u.length&&l.append(T(e,`div`,`wk-note`,`안 고르면 ${w}`)),t.append(l);let d=k(`걸음`),f=T(e,`label`,`wk-keyrow`);f.append(T(e,`span`,`wk-keyname`,`direction`));let p=T(e,`select`,`wk-select`);p.append(T(e,`option`,``,w));for(let t of C){let n=T(e,`option`,``,t);n.value=t,t===h.direction&&(n.selected=!0),p.append(n)}p.addEventListener(`change`,()=>{h.direction=p.value}),f.append(p),d.append(f);for(let[t,n,r,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=T(e,`label`,`wk-keyrow`);a.append(T(e,`span`,`wk-keyname`,t));let o=T(e,`input`,`wk-input`);o.type=`number`,o.min=String(r),o.max=String(i),o.placeholder=w,o.value=h[n],o.addEventListener(`input`,()=>{h[n]=o.value}),a.append(o),d.append(a)}t.append(d);let m=T(e,`button`,`wk-go`,h.run===`running`?`걷는 중`:`날리기`);m.type=`button`,m.disabled=!h.type||h.run===`running`,m.addEventListener(`click`,O),t.append(m)}function j(t,n){let r=S(n,v());for(let n of r.sections){let r=T(e,`div`,`wk-sec`);r.append(T(e,`div`,`wk-sechead`,n.heading));let i=T(e,`table`,`wk-table`),a=T(e,`thead`),o=T(e,`tr`);for(let t of n.columns)o.append(T(e,`th`,``,t.name));a.append(o),i.append(a);let s=T(e,`tbody`);for(let t of n.rows){let n=T(e,`tr`);for(let r of t.cells){let t=T(e,`td`,r.numeric?`wk-num`:``,r.text);r.kind===`id`&&(t.className=`wk-id`),n.append(t)}s.append(n)}i.append(s),r.append(i),t.append(r)}r.hidden&&t.append(T(e,`div`,`wk-note`,`이 아래 ${r.hidden} 개 안 그림`))}function M(n){if(h.run===`idle`)return;let r=T(e,`div`,`wk-result`);if(h.run===`running`)r.append(T(e,`div`,`wk-note`,`걷는 중`));else if(h.run===`failed`){let t=T(e,`div`,`wk-fail`);t.append(T(e,`b`,``,`실패`),T(e,`span`,``,` · `+h.reason)),r.append(t)}else if(h.result){let n=h.result,i=[...h.collect].map(g).join(`, `);if(r.append(T(e,`div`,`wk-counts`,i?`노드 ${n.nodes.length} (collect: ${i}) · 엣지 ${n.edges.length} (전부)`:`노드 ${n.nodes.length} · 엣지 ${n.edges.length}`)),n.walk&&r.append(T(e,`div`,`wk-walk`,`요청 ${n.walk.hops_requested}홉 · 도달 ${n.walk.hops_reached}홉 · ${n.walk.direction}`)),n.generatedAt&&r.append(T(e,`div`,`wk-note`,`기준 ${String(n.generatedAt)}`)),n.cut&&r.append(T(e,`div`,`wk-trunc`,`절단됨 · ${t(n.truncatedAxes,n.limits).join(` · `)}`)),n.nodes.length){let t=new Map;for(let e of n.nodes){let n=e.type||`—`;t.set(n,(t.get(n)||0)+1)}let i=T(e,`div`,`wk-dist`);i.append(T(e,`span`,`wk-distlabel`,`타입`));for(let[n,r]of[...t.entries()].sort((e,t)=>t[1]-e[1])){let t=T(e,`span`,`wk-distchip`+(h.collect.has(n)||h.collect.has(`${n}@1`)?` is-asked`:``));t.append(T(e,`b`,``,n),T(e,`span`,``,` ${r}`)),i.append(t)}r.append(i)}n.nodes.length||r.append(T(e,`div`,`wk-note`,n.message||`닿은 노드 없음`)),j(r,n)}n.append(r)}function N(){n.textContent=``;let t=T(e,`div`,`wk-form`);if(h.declState===`loading`)t.append(T(e,`div`,`wk-note`,`선언 · 읽는 중`));else if(h.declState===`failed`){let n=T(e,`div`,`wk-fail`);n.append(T(e,`b`,``,`선언 못 읽음`),T(e,`span`,``,` · `+h.declReason));let r=T(e,`button`,`wk-go`,`다시`);r.type=`button`,r.addEventListener(`click`,F),t.append(n,r)}else A(t),M(t);n.append(t)}async function P(){if(!h.type){h.subjectsState=`idle`,h.subjects=null;return}let e=h.type;h.subjectsState=`loading`,h.subjects=null,N();let t=await c({apiBase:u,fetchImpl:a.fetchImpl,type:e});h.type===e&&(t&&t.ok?(h.subjectsState=`ready`,h.subjects=t.subjects,h.subjectsScanned=t.scanned,h.subjectsScanCut=t.scanTruncated,h.subjectsListCut=t.valuesTruncated):(h.subjectsState=`failed`,h.subjectsReason=t&&t.message||`알 수 없음`),N())}async function F(){h.declState=`loading`,N();let e=await d({apiBase:u,fetchImpl:a.fetchImpl});e&&e.ok?(h.decl=e,h.declState=`ready`):(h.declState=`failed`,h.declReason=e&&e.message||`알 수 없음`),N()}return F(),{state:h,spec:D,fire:O,render:N}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&f(async()=>{let{API_BASE:e}=await import(`./config-C6wMXuF6.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{E(document,e,{apiBase:t})})}