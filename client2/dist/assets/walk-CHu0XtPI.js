const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/config-C6wMXuF6.js","assets/config-BUp4smhE.js"])))=>i.map(i=>d[i]);
import"./tokens-nTqwt3FA.js";import{a as e,s as t,t as n}from"./preload-helper-C9Hjvsp-.js";var r=`data-wk-styles`,i=`
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
`;function a(e){if(!e||typeof e.createElement!=`function`||e.querySelector&&e.querySelector(`style[${r}]`))return!1;let t=e.createElement(`style`);return t.setAttribute(r,``),t.textContent=i,(e.head||e.documentElement).appendChild(t),!0}var o=[`both`,`outgoing`,`incoming`],s=`서버 기본`,c=(e,t,n,r)=>{let i=e.createElement(t);return n&&(i.className=n),r!==void 0&&(i.textContent=String(r)),i};function l(n,r,i){let l=i||{},u=l.apiBase||``;a(n);let d=e({apiBase:u,fetchImpl:l.fetchImpl}),f={decl:null,declState:`loading`,declReason:``,type:``,keys:{},follow:new Set,direction:``,hops:``,nodeLimit:``,run:`idle`,result:null,reason:``},p=()=>f.decl&&f.decl.entities||[],m=e=>{let t=p().find(t=>t.type===e);return t&&t.keys||[]},h=()=>{let e=f.decl&&f.decl.predicates||[];return f.type?e.filter(e=>(e.subjects||[]).includes(f.type)).map(e=>e.name):e.map(e=>e.name)};function g(){let e={type:f.type,keys:f.keys};f.follow.size&&(e.follow=[...f.follow]),f.direction&&(e.direction=f.direction);let t=parseInt(f.hops,10);Number.isFinite(t)&&(e.hops=t);let n=parseInt(f.nodeLimit,10);return Number.isFinite(n)&&(e.node_limit=n),e}async function _(){if(!f.type)return;f.run=`running`,f.result=null,f.reason=``,x();let e=await d(g());e&&e.ok?(f.run=`done`,f.result=e):(f.run=`failed`,f.reason=e&&e.message||`알 수 없음`),x()}function v(e){let t=c(n,`div`,`wk-field`);return t.append(c(n,`div`,`wk-label`,e)),t}function y(e){let t=v(`노드 타입`),r=c(n,`select`,`wk-select`);r.append(c(n,`option`,``,`— 고르십시오 —`));for(let e of p()){let t=c(n,`option`,``,e.type);t.value=e.type,e.type===f.type&&(t.selected=!0),r.append(t)}r.addEventListener(`change`,()=>{f.type=r.value;let e=new Set(m(f.type));f.keys=Object.fromEntries(Object.entries(f.keys).filter(([t])=>e.has(t)));let t=new Set(h());f.follow=new Set([...f.follow].filter(e=>t.has(e))),f.result=null,f.run=`idle`,x()}),t.append(r),e.append(t);let i=v(`키`),a=m(f.type);f.type?a.length||i.append(c(n,`div`,`wk-note`,`이 타입은 키가 없습니다`)):i.append(c(n,`div`,`wk-note`,`타입을 고르면 키가 나옵니다`));for(let e of a){let t=c(n,`label`,`wk-keyrow`);t.append(c(n,`span`,`wk-keyname`,e));let r=c(n,`input`,`wk-input`);r.type=`text`,r.value=f.keys[e]===void 0?``:f.keys[e],r.addEventListener(`input`,()=>{f.keys[e]=r.value}),t.append(r),i.append(t)}e.append(i);let l=v(`follow`),u=h();u.length||l.append(c(n,`div`,`wk-note`,f.type?`${f.type} 에서 나가는 술어 없음`:`선언에 술어 없음`));for(let e of u){let t=c(n,`label`,`wk-check`+(f.follow.has(e)?` is-on`:``));t.setAttribute(`data-follow`,e);let r=c(n,`input`);r.type=`checkbox`,r.checked=f.follow.has(e),r.addEventListener(`change`,()=>{f.follow.has(e)?f.follow.delete(e):f.follow.add(e),x()}),t.append(r,c(n,`span`,``,e)),l.append(t)}u.length&&l.append(c(n,`div`,`wk-note`,`안 고르면 ${s}`)),e.append(l);let d=v(`걸음`),g=c(n,`label`,`wk-keyrow`);g.append(c(n,`span`,`wk-keyname`,`direction`));let y=c(n,`select`,`wk-select`);y.append(c(n,`option`,``,s));for(let e of o){let t=c(n,`option`,``,e);t.value=e,e===f.direction&&(t.selected=!0),y.append(t)}y.addEventListener(`change`,()=>{f.direction=y.value}),g.append(y),d.append(g);for(let[e,t,r,i]of[[`hops`,`hops`,1,40],[`node_limit`,`nodeLimit`,10,5e3]]){let a=c(n,`label`,`wk-keyrow`);a.append(c(n,`span`,`wk-keyname`,e));let o=c(n,`input`,`wk-input`);o.type=`number`,o.min=String(r),o.max=String(i),o.placeholder=s,o.value=f[t],o.addEventListener(`input`,()=>{f[t]=o.value}),a.append(o),d.append(a)}e.append(d);let b=c(n,`button`,`wk-go`,f.run===`running`?`걷는 중`:`날리기`);b.type=`button`,b.disabled=!f.type||f.run===`running`,b.addEventListener(`click`,_),e.append(b)}function b(e){if(f.run===`idle`)return;let t=c(n,`div`,`wk-result`);if(f.run===`running`)t.append(c(n,`div`,`wk-note`,`걷는 중`));else if(f.run===`failed`){let e=c(n,`div`,`wk-fail`);e.append(c(n,`b`,``,`실패`),c(n,`span`,``,` · `+f.reason)),t.append(e)}else if(f.result){let e=f.result;t.append(c(n,`div`,`wk-counts`,`노드 ${e.nodes.length} · 엣지 ${e.edges.length}`)),e.walk&&t.append(c(n,`div`,`wk-walk`,`요청 ${e.walk.hops_requested}홉 · 도달 ${e.walk.hops_reached}홉 · ${e.walk.direction}`)),e.cut&&t.append(c(n,`div`,`wk-trunc`,`절단됨 · ${e.truncated.reason}`)),e.nodes.length||t.append(c(n,`div`,`wk-note`,e.message||`닿은 노드 없음`));for(let r of e.nodes.slice(0,200)){let e=c(n,`div`,`wk-row`);e.append(c(n,`span`,`wk-rowtype`,r.type||`—`)),e.append(c(n,`span`,`wk-rowlabel`,r.label||r.id||``)),t.append(e)}e.nodes.length>200&&t.append(c(n,`div`,`wk-note`,`이 아래 ${e.nodes.length-200} 개 안 그림`))}e.append(t)}function x(){r.textContent=``;let e=c(n,`div`,`wk-form`);if(f.declState===`loading`)e.append(c(n,`div`,`wk-note`,`선언 · 읽는 중`));else if(f.declState===`failed`){let t=c(n,`div`,`wk-fail`);t.append(c(n,`b`,``,`선언 못 읽음`),c(n,`span`,``,` · `+f.declReason));let r=c(n,`button`,`wk-go`,`다시`);r.type=`button`,r.addEventListener(`click`,S),e.append(t,r)}else y(e),b(e);r.append(e)}async function S(){f.declState=`loading`,x();let e=await t({apiBase:u,fetchImpl:l.fetchImpl});e&&e.ok?(f.decl=e,f.declState=`ready`):(f.declState=`failed`,f.declReason=e&&e.message||`알 수 없음`),x()}return S(),{state:f,spec:g,fire:_,render:x}}if(typeof document<`u`){let e=document.getElementById(`wk-host`);e&&n(async()=>{let{API_BASE:e}=await import(`./config-C6wMXuF6.js`);return{API_BASE:e}},__vite__mapDeps([0,1])).then(({API_BASE:t})=>{l(document,e,{apiBase:t})})}