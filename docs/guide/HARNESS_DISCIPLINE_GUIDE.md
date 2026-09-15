# 🧪 HARNESS DISCIPLINE — 하니스가 «무엇을» 재는가

> **이 문서가 정본입니다.** CLAUDE.md 의 「잘라쓰기 하니스 절대 금지」 절은 «왜»를 적고, 여기는 «어떻게»를 적습니다.
> 신설 2026-09-10 (D-2). 아래 모든 심볼·줄 번호는 그날 소스에 대고 확인했습니다.
> 갱신 2026-09-16 — §1 「순서도, 목록도 이름으로」(C-110 · S-255) · §5-nonies 신설(PG 만 나를 수 있는 증명의 자리 — S-256 · S-257 · S-258) · §6 행 넷.

---

## 0. 한 장 요약

```
대상에 닿는 길은 셋뿐이고, 순서가 있다
  ① import          정본. 재려는 것이 «이름»으로 있으면 그냥 부른다
  ② 프로브 덧붙이기   다리. 모듈 «전문» + 뒤에 접근자. 잘라내는 양이 «0»
  ③ 텍스트가 «주어»   예외. 두 리비전의 «글자가 달라졌나»를 재는 드리프트 오라클
⛔ 없는 길: 파일을 텍스트로 읽어 함수 본문을 잘라 `vm` 에 넣기
```

**왜 ⛔ 인가 — 잘라쓰기는 «동작»이 아니라 «글자 모양»을 잽니다.**
import 를 하나 더하면 조각이 그 함수를 못 찾아 던지고, `const` 를 하나 더하면 `vm` 에서 밖으로 안 보이고, 헬퍼를 새로 부르면 「뽑을 목록」에 없어 던집니다 — **전부 «코드가 맞는데» 빨개집니다.** 그리고 반대도 참입니다: 틀렸는데 초록일 수 있습니다.

---

## 1. ① import — 정본

재려는 로직이 «import 되는 모듈»에 살면 하니스는 그것을 부르면 끝입니다.
대상이 import 가 «안 되면» 그것이 «고쳐야 할 결함»이고, 하니스를 잘라쓰기로 우회하는 것이 아닙니다.

🔵 **그 반대 방향도 참입니다** — 오늘 import 가 «되면», 잘라쓰기는 남을 사유가 없습니다.
실측 2026-09-10 (C-62): 두 하니스가 댄 사유가 둘 다 «거짓»이었습니다.

```
reference_grid_paste_harness  적힌 사유 「config.js 가 모듈 최상단에서 window 를 만져 node 가 import 못 함」
                             실측      `await import('./src/enrichment_reference_view.js')` «성공»
                                      (`config.js` 는 그 문제를 이미 고쳤고, 그 파일 머리가 그 사유를 적어 둡니다)
history_paging_harness       24 함수를 정규식으로 뽑아 `vm` 에 넣고 있었음
                             자기 주석이 대가를 «세 번» 기록: import 하나를 더하니 «맞는 코드»에 던졌고,
                             새 호출 대상이 목록에 없어 섹션 H 가 «통째로 0» 을 그림
```

**이름을 내는 것이 이관의 전부일 때가 많습니다.**
- `client2/src/enrichment_reference_view.js:126` `export function fillPlan(...)`
- `client2/src/enrichment_reference_view.js:531` `export { render as renderReferenceResults }`
- `client2/src/clipboard.js:27` `export function isReferenceSidebarCopy(e)` — 문서 수준 `copy` 핸들러의 «조건»을 이름 있는 함수로 뺀 것. 전에는 하니스가 «앵커 문자열»을 찾고 술어를 «자기가» 다시 써서, 철자만 바꿔도 맞는 코드가 빨개지고 같은 철자로 틀리게 고치면 통과했습니다

🔵 **[2026-09-16] «순서»도, «목록»도 이름으로 낼 수 있다 — 양쪽 도메인에서 같은 밤에 하나씩.**
- **C-110 `c96527d9` (클라)** — `client2/src/startup.js:32` `export async function startup({ prepare, tableChosen })`. 그리드 페이지의 부팅 «순서»(소켓 «첫 줄» → `prepare` → `checkServerHealth` → `loadTables` → `tableChosen`)를 `main.js::init()` 에서 빼서 모듈 최상단이 DOM·CSS 를 안 만지는 파일에 뒀다. `tests/startup_socket_gate_harness.mjs` 는 `startup.js`·`api.js`·`websocket.js` «전문»을 §2 의 프로브로 싣고 시나리오마다 «새 사본»을 쓴다(멈춘 REST 래치가 다음 판을 못 물들인다) · `switchTable` 은 «진짜로» 돌고 그 중복 부트스트랩의 피해는 문에서 센다(`/schema` 읽기 1 · `renderGrid` 1) · 재연결 튜닝은 `config.js` 에서 import(정규식 아님) · 변이는 모듈 «통째». 종전엔 `init()` 을 잘라 `vm` 에 넣어 `main.js` 가 모듈 이름 하나를 얻을 때마다(`redoBannerFollows` 가 마지막) 24 시나리오가 «맞는 코드»에 ReferenceError 를 던지고 스텁이 하나씩 늘었다. 같은 111 단언 · 9 변이 포착 · 3 대조군 — 그리고 `main.js` 에 `let` + `export function` 을 «덧붙여도» 초록.
- **S-255 `8c824a1e` (서버)** — `server/runtime/launcher_specs.py:23` `def child_specs(python_exe, server_dir, server_cmd, api_host, api_port)`. 런처의 자식 명부(넷 · `heartbeat=` · `ports=` · `log_file=` · API 자식의 `ASSY_CHAIN_WORKER=0`)를 «부작용 없는 모듈의 값»으로 빼서, `run_decoupled_app.py` 를 텍스트(`ChildSpec(` 뒤 420자 창 · `run_chain_worker.py` 첫 언급의 정규식)로 자르던 오라클 다섯(`test_duplicate_launcher` 둘 · `test_process_supervisor` 하나 · `test_the_chain_loop_runs_in_its_own_process` 셋)이 반환값을 단언한다. 런처 «자신»은 import 시점에 라이브 `launcher.log` 를 열고 루트 로거를 옮기니 목록이 거기 살 수 없었다. 변이(스크래치 사본): 스펙 «안» 주석 → 초록(2026-09-15 `86016d10` 에선 그것이 빨강이었다 — 런처는 맞았는데) · `log_file=`/`heartbeat=`/`ASSY_CHAIN_WORKER=0` 삭제 · 두 자식이 한 로그 파일 → 빨강(텍스트는 마지막 것을 «볼 수 없었다»).
📌 같은 부류의 셋째, 같은 밤 — S-234 `5c845e67` 의 드리프트 오라클은 `git grep` 으로 「`ASSY_CHAIN_SYNTHESIZE` 가 `server/` 어디에도 없다」를 단언한다. 텍스트가 «주어»라 §3 의 예외이고, 대리가 아니다.

---

## 2. ② 프로브 — `client2/tests/lib/probe.mjs`

`export` 만으로 안 되는 자리가 있습니다: 하니스가 대상의 «모듈 변수»를 심어야 할 때. ESM 네임스페이스는 봉인돼 있고 `export let` 은 밖에서 읽기 전용입니다.

```
하는 일   대상을 «바이트 그대로» 복사하고, 마지막 줄 «뒤»에 접근자 객체를 붙여 그 사본을 import
잘라낸 양  «0» — import 도 const 도 헬퍼도 파일 안에 그대로 있습니다
증명      `assertAppendOnly` 가 매 로드마다 「사본이 원본 바이트로 시작한다」를 단언합니다.
         그 단언이 없으면 덧붙이기는 조용히 잘라쓰기로 돌아갑니다
```

### 쓰는 법
```js
const { probe, module } = await loadWithProbe(srcPath, {
  expose: ['fnA', 'CONST_B'],   // 한 번 읽는 이름 — 하니스가 «부르는» 것
  state:  ['moduleLet'],        // 하니스가 «읽고 써야» 하는 모듈 수준 let/var
  stubs:  { './dep.js': { showToast: fn } },   // 가로챌 의존
  mutate: (text) => text.replace(from, to),    // 변이: 조각이 아니라 «모듈 전체»
  tag:    'label',
});
```
- `mutate` 가 «아무것도 안 바꾸면» 프로브가 **멈춥니다**(exit 2). 안 먹은 변이는 잡힌 변이가 아닙니다.
- `expose` 에 없는 이름은 평가 시 «던집니다» — 조용히 `undefined` 가 되면 개명된 함수가 초록으로 통과합니다.

### 🔴 사본은 «제품 트리 밖»에 삽니다 (C-67, 2026-09-10)
```
어디에   client2/.tmp/probe/<client2 기준 상대경로>/<파일>.__probe__.<tag>.js   (gitignore)
왜      사본이 `client2/src` 옆에 살면 그 트리를 «걷는» 하니스가 그것을 봅니다 —
        `split_registry_harness` 가 다른 프로세스가 만들었다 지우는 사이에 읽고 ENOENT 로 죽었습니다.
        게이트가 네 번 중 «세 번» 빨갰고 매번 «다른» 하니스였습니다
거울인 이유  훅이 `register()` 로 «다른 스레드»에서 돕니다 -> 아무것도 «전달할 수» 없습니다.
        원본 디렉터리는 «경로에서 유도»돼야 하고, 접두 `/.tmp/probe/` 하나를 떼면 나옵니다
```

### 훅 — `client2/tests/lib/probe_hooks.mjs:46` `export async function resolve(...)`
```
importer 가 «프로브 사본» 이고 지정자가 `./name.js` 이면
   ① 그 이름의 «스텁»이 있으면 스텁으로
   ② 없으면 «원본 디렉터리»의 그 파일로            <- C-67. 사본이 src 를 떠났으므로 필수
importer 가 «프로브 사본» 이고 지정자가 «상대 경로 아무거나» 이면 (`../a/b.js` 포함)
   원본 디렉터리에 «지정자 전체»를 resolve 해서                <- 🆕 C-72
importer 가 «생성된 스텁» 이면
   원본 디렉터리로만. 스텁에게 또 스텁을 주지 않습니다(자기 순환)
그 밖    손대지 않습니다. 같은 `./utils.js` 를 다른 데서 import 하면 «진짜»가 나옵니다
```
🆕 🔴 **[C-72] 스텁 갈래는 «같은 디렉터리»뿐이지만 «흘려보내는» 갈래는 상대 경로 «전부»입니다.** 전에는 `./name.js` 만 원본으로 돌렸고, 그래서 `../rnd_board/api.js` 를 import 하는 «첫 대상»(`walk/main.js`)이 거울 안의 «없는 디렉터리»로 풀려 단언 하나도 못 돌고 `ERR_MODULE_NOT_FOUND` 로 죽었습니다. ⚠️ **이 부류는 「하니스가 약하다」가 아니라 「하니스가 «안 돈다»」이고**, 게이트는 그것을 「측정을 안 한다」로 잡습니다(바닥값).

⚠️ **훅은 이제 «매 로드마다» 등록됩니다.** 전에는 스텁이 있을 때만 걸었는데, 사본이 src 를 떠난 뒤로는 훅이 «사본 자신의 형제 import 가 풀리는 유일한 이유»입니다.

---

## 3. ③ 텍스트가 «주어»인 하니스 — 예외

두 리비전의 «텍스트가 달라졌나»를 재는 드리프트 오라클은 이 금지 밖입니다. 거기서는 「모양이 바뀌면 빨개진다」가 **병이 아니라 기능**입니다.

🔴 **판별식은 «단언» 단위입니다. «파일» 단위가 아닙니다.** 한 파일이 「순서를 읽는 단언」과 「잘라내어 돌리는 단언」을 같이 가질 수 있고, 파일을 통째로 예외로 읽으면 잘라쓰기가 그 안에 남습니다.

---

## 4. 변이 채점기 — `client2/tests/lib/mutation_scorer.mjs`

`export async function scoreMutants(mutants, run, opts)` (`:48`) · `export const VERDICT` (`:35`)

**변이 하나의 모양**
```js
{ id, what, catches, mutate, drops }
```

### 판정 넷 — «정확한 뜻»
| 판정 | 뜻 | 언제 |
|---|---|---|
| `caught` | **그 변이가 이름 댄 단언이** 실패했다 | defect 집합에서 옳음 |
| `escaped` | 아무 단언도 안 깨웠다 | control 집합에서 «옳음», defect 에서는 틀림 |
| `INERT` | 실행이 **던졌다** | 언제나 틀림 — defect 든 control 이든 |
| `SHRUNK(-n)` | 판정과 «별개»로, 단언 «수»가 기저보다 n 개 적었다 | 보고만. 점수 아님 |
| `AMBIGUOUS(...)` | `catches` 의 «한 접두»가 기저 단언 «둘 이상»을 가리킨다 | 보고만. 점수 아님 |

🔴 **`caught` 는 「무엇이든 실패」가 «아닙니다».** 「이 단언이 실패」입니다. 엉뚱한 이유로 잡힌 변이는 아무도 재고 있지 않은 변이입니다 — 그 변이가 지키려던 줄이 밑에서 썩어도 코퍼스는 초록입니다.

🔴 **던짐은 «구멍»이지 «잡힘»이 아닙니다.** 하니스가 «멈춘» 것이지 «알아챈» 것이 아닙니다. 이것을 잡힘으로 세면, 죽은 하니스가 초록 한 줄이 됩니다.

### `catches` — 어느 단언이 잡아야 하나
```
값     단언 이름의 «접두». 문자열 하나, 또는 «배열»(한 변이가 여러 이름 줄 중 하나를 정당하게 깰 때)
왜 접두  뒷말을 손질해도 변이가 «조용히 무명»이 되지 않게
🔴 짓지 말고 «재서» 적는다  코퍼스를 한 번 돌려 각 변이의 «처음 실패한 단언»을 읽고 옮깁니다.
      직관으로 적으면 「이 변이는 이 단언이 잡을 것」이 틀려도 «초록»이고, 그 단언은 영원히 안 재집니다
⚠️ `catches` 없는 defect 는 «조용히 통과 안 합니다» — ESCAPED 로 이름 대어 찍힙니다
```

### `drops: n` — 「단언이 줄어드는 것을 «봤다»」
변이가 갈래를 도달 불가로 만들면 단언이 «실패»하는 게 아니라 «안 돕니다». `drops` 에 그 수를 적으면 접히되 **정확히 같을 때만** 접힙니다 — 3 을 적으면 실제 -4 가 다시 웁니다. 선언은 «침묵»이 아니라 «본 것»의 기록입니다.

### `baselineNames` — AMBIGUOUS 를 켜는 옵트인
`run` 이 `ran`(수)을 돌려주고 호출자가 `baselineRan` 을 주면 SHRUNK 가, `baselineNames`(이름 배열)를 주면 AMBIGUOUS 가 켜집니다. 안 주면 «안 재집니다» — 모양을 바꾸지 않습니다.

⚠️ **AMBIGUOUS 는 «접두 하나» 단위로 묻습니다.** 배열 `catches` 의 매치를 «합쳐» 세면 «설계대로 여럿을 가리키는» 변이가 전부 충돌로 찍힙니다(실측: walk_box 에서 그 오독이 2 를 9 로 부풀렸습니다).

### ⛔ 정의역 밖 — 「기대 결과가 throw」인 변이
`effort_instrument_harness.mjs` 에는 **던지는 것이 기대값**인 변이가 있고, 그것은 옳습니다. 이 채점기는 던짐을 정의상 INERT 로 보므로 그 코퍼스를 여기 태우면 «맞는 코드가 빨개집니다». 목록만 보고 넣지 마십시오.

### 오늘의 소비자 일곱
`frame_declaration` · `map_key_datalist` · `map_spec_only_save` · `redo_banner` · `rnd_board_composition` · `rnd_board_walk` · `rnd_board_walk_box`

---

## 5. 게이트 — `client2/scripts/check_harnesses.mjs` 가 «무엇을» 단언하나

```
발견        `client2/tests/*.mjs` 를 «훑어» 찾습니다. 고정 목록이 아닙니다
            -> 새 하니스가 목록에 안 실려 「태어나자마자 죽는」 일이 없습니다
판정        종료 코드 + `ASSERTIONS <ran> <failed>` 한 줄. 그 줄은 «하니스 자신의 계수기»에서 옵니다
            (러너는 체크 표시를 세지 않습니다 — 산문을 다시 채점하지 않습니다)
막는 것     ① 초록인데 그 줄이 «없음» / `ran=0` / `failed>0`
            ② KNOWN_RED 항목이 «기록보다 적게» 단언 -> 빚이 아니라 «죽음»
            ③ FLOORS 아래로 내려간 하니스 (:185)
            ④ 🔴 `client2/src` 에 «프로브 산출물»이 하나라도 있음 (:1642, C-67)
KNOWN_RED   (:102) 빚 목록이지 «건너뛰기»가 아닙니다. 여전히 «돌고» 여전히 «보고»되며 다만 안 막습니다
CEILINGS    (:1450) 바닥의 거울 — 「쌓인 것을 더 쌓지 마라」
```

### ④ 가 왜 «면역의 증명»인가
사본을 옮긴 것은 «습관»이고, 이 단언이 그것을 «보증»으로 만듭니다. 무언가 다시 src 에 쓰면 그날 빌드가 말합니다 — 몇 주 뒤 엉뚱한 하니스가 무작위로 죽는 대신에.
⚠️ 이 검사는 **하니스를 돌리기 «전»**에 섭니다. 뒤에 뒀더니 심어 둔 잔해 하나가 하니스 «19 개»를 빨갛게 만들고 정작 원인을 말할 기회가 없었습니다.

---

## 🆕 5-bis. 동적 모델을 «물리는» 것은 함수 «하나»다 (2026-09-12 S-191 `1f730cc9`)

```
✅ `server/tests/conftest.py::retire_dynamic_model(name)`           — 이것을 쓴다
   (📐 줄 번호를 안 적는다 — 09-12 에 :75 → :147 로 밀렸다. 이름으로 grep 한다)
⛔ `models.DYNAMIC_TABLES.pop(name)` «만» 하는 것                   — 절반이고, 나머지 절반이 «세 파일 건너»에서 터진다
```

### 🔴 왜 pop 이 «절반»인가 — 실패가 «다른 파일»에서 난다
```
pop 하면        `DYNAMIC_TABLES` 에서 클래스가 빠진다
남는 것         `Base.metadata` 는 «같은 싱글턴»이라 `Table` 과 그 `Index` 객체가 «살아남는다»
다음 빌드       클래스가 없으니 `init_dynamic_models` 가 «새로 짓는» 팔을 타고 **같은 이름의 `Index` 를 하나 더** 붙인다
터지는 곳       그 «뒤에» `Base.metadata.create_all` 을 부르는 «첫 파일»이 「index … already exists」로 죽는다
                — 샌 파일도, 그렇게 만든 픽스처도 «이름 대지 않고»
```
📐 **이 세션 실측: 그런 픽스처 «하나»에서 오류 1,008 건**(`ea1e8ec2`). 좌석 «넷»이 양쪽 절반을 손으로 했고
«넷»은 안 했다 — 그래서 「Table 은 어디서 또 빼지」가 시험마다 «외울 일»이 아니게 함수 하나로 접었다.

### ⛔ 그리고 「저장했다 되돌리기」는 이 헬퍼의 «예외»다 — 이름까지 적혀 있다
```
tests/test_map_alignment_references.py   test_an_unservable_catalog_is_a_different_state
tests/test_map_alignment_worklist.py     test_an_unservable_catalog_is_a_different_state
tests/test_ledger_v2_pg.py               `previous_model` 을 되돌리는 `finally`
```
🔴 **거기서는 pop 이 restore 의 «역»이다.** `Table` 까지 떨어뜨리는 헬퍼를 쓰면 그 짝이 깨진다 —
restore 는 «클래스»를 돌려놓지 `Table` 을 돌려놓지 않기 때문이다. 소스가 이 셋을 «이름 대어» 적어 둔 이유가
그것이다: **다음 독자가 「일을 마저 끝내지」 않게.**
🔵 반환은 «물린 클래스», 없던 이름이면 `None` — 그래서 호출자가 「있었다」와 「애초에 없었다」를 «구별»할 수 있다.

📌 부류: 「한 축은 한 칸·한 함수」의 «시험 픽스처» 판이다. 그리고 이 항목이 이 문서에 있는 이유는
**증상이 원인에서 세 파일 떨어져 나타나기 때문**이다 — 하니스가 「무엇을 재는가」만큼이나
「무엇을 «남기는가»」가 이 저장소가 값을 치른 자리다.


## 🆕 5-quinquies. `data:` 사본은 «다리»이고, 로더는 «문 하나»여야 한다 (2026-09-13 C-93 `d30e0a1d`, 판정 345)

```
✅ `client2/tests/lib/board_modules.mjs` 의 `moduleUrl(src)` :24 — 모든 모듈 URL 이 «여기»를 지나고
   `outward(src)` :39 가 «그 안»에 산다 -> 호출 자리가 «잊을 수 없다»
⛔ 자리마다 «자기 사본» — 같은 세 줄을 여섯 곳이 각자 들고 있었고, 여섯 다 «같은 누락»을 들고 있었다
```
🔴 **그 누락이 언제 값을 치르는지가 요점이다** — 사본들이 «바깥 지정자»(`../src/...` 같은 것)를 다시 쓰지
않으므로, 대상 파일이 **«첫 바깥 import 를 얻는 날»** 보드 하니스 «여덟»이 조용히 «아무것도 안 재게» 된다.
그때까지는 전부 초록이다. ⚠️ **즉 이것은 「하니스가 틀렸다」가 아니라 「하니스가 «없어졌다»」이고,
초록이 그것을 숨긴다** — 이 문서 §5 의 「초록 대리지표」와 같은 병이다.
🔵 **그리고 그 일반 규칙은 «이미 있었다»** — `board_modules.mjs` 자기 주석이 이유를 적는다:
손으로 적은 목록이 하니스를 «두 번» 넘어뜨렸다(C-70 · C-77). 그래서 C-93 이 만든 것은 규칙이 아니라
«그 규칙을 지나지 않을 수 없게 하는 문»이다.
📌 부류: **「같은 일을 하는 자리가 여럿이면 갈리고, 갈린 쪽이 조용하다」** — 상설 「같은 기능에 두 경로가
있어서도 안 됨」의 하니스 판이다.

⚰️ **그리고 `data:` URL 사본은 «걷히지 않았다 — 접혔다»** (2026-09-13 C-94 실측 `df8cac15`, 판정 367).

```
적었던 것   「다리다 — C-91 · 그다음 C-94 에서 은퇴 예정」 (판정 345·346)
오늘      그 은퇴를 **짓기 전에 재 봤고**, 재보니 바꾸는 것이 손해였다
이득      «바이트 충실도» 하나 — C-93(`d30e0a1d`)이 다리를 로더 «하나»로
          모은 뒤에는 그것만 남았다
비용      «잊을 자리 69» · 로드 «3.7배»
결론      기존 보드 하니스는 그대로 · **새 보드 하니스만 처음부터 probe(import)**
```
🔴 **이 줄이 남는 이유는 «결론»이 아니라 «절차»이다** — 다리를 놓을 때 «언제 걷을지»를 같이 적었고, 그 날짜가 오자 «걷는 대신 재고» 그 자리에서 판정이 나왔다. ⚠️ 표기가 없었으면 이 전환은 「언젠가 할 일」로 남아 «재보지도 않은 채» 영우롬았을 것이다.
🔵 그리고 이것이 «다리» 표기가 할 수 있는 두 가지 끝 중 둘째다 — D-19 의 `AGGREGATE` export 는 «예고대로 걷혔고»(C-90 ② `deebe3da`, 하루 만에), 이쪽은 «예고된 날에 재서 접혔다». 둘 다 «영구 건물이 되지 않았다»는 점에서 같은 결과다.
⚠️ 그래서 §5-quinquies 의 문 하나(`moduleUrl` :24)는 «임시가 아니라 오늘의 정본»이다 — 그 절을 「곷 없어질 것」으로 읽지 말 것.

## 🆕 5-sexies. stub 목록은 «주체의 import 줄»에서 «읽고», stage 는 «번들의» state 에 한다 (2026-09-13 C-91 ⓐ `d9e9d704`, 판정 346)

```
✅ 주체가 `./state.js` 에서 가져가는 이름은 «그 파일의 import 줄»을 파싱해서 얻는다
   (`virtual_column_render_harness.mjs` 의 `STATE_IMPORTS`)
   -> 주체가 이름을 «하나 더» 가져가기 시작해도 대조군에서 «조용히 빠질 수» 없다
⛔ 하니스가 그 목록을 «기억»해서 손으로 적는 것 — 이름이 늘면 목록이 낡고, 낡은 목록은 «초록»이다
✅ 러너는 자기가 «채점하는 번들»의 state 를 stage 한다 (`useState(bundle)`)
⛔ 진짜 싱글턴을 stage 하는 것 — 변이된 사본은 «다른 객체»라, 변이가 «아무도 안 연 페이지»에 서 있게 된다
```
🔴 **이 절이 생긴 사유는 «벽 하나가 벽이 아니었다»는 것이다.** C-88 이 `state.js` 를 「사본이 자기 객체를 들어서 다른 모듈이 안 읽는다」로 적었고, 그래서 대조군 둘이 «여섯 중 다섯»만 덮었다. 실측하니 `probe.mjs` 의 `spec.stubs` 가 그것을 «이미» 할 수 있었다 — 사본을 «먼저» 싣고 그 `state` 를 나머지 주체에게 넘기면 치환이 «닿는다»(명시적 export 가 stub 의 `export *` 를 이긴다). 📌 부류: **「기제가 없다」가 아니라 「아무도 그 조합을 안 써 봤다」** — 같은 밤에 «두 번» 나왔고(C-93 `d30e0a1d` 의 로더가 첫째), 둘 다 새로 «지을» 물건이 아니었다.
🔵 **그리고 stub 목록을 «읽는» 것이 의례가 아닌 이유는 프로브가 «거절»하기 때문이다** — `probe.mjs` :220~ 이 「주체가 import 하지 않은 이름의 stub」을 이름 대어 거절한다(`importedNames` :221). 즉 목록이 틀리면 «조용히 안 재는» 대신 «빨개진다». 실측으로 그 거절을 받아 봤다: `grid.js` 는 `isVirtualColumn` 을 import 하지 않는다.
🔴 **치환이 «닿았는지»는 대조군으로 못 잰다** — 달아난 대조군은 「사본이 배선됐어도」 「조용히 건너뛰었어도」 «같은 값»을 낸다. 그래서 C-91 ⓐ 는 `state.js` 에 «잡힐 변이»를 하나 놓았고, 그것을 잡는 자리는 «다른 파일»의 쓰기 깔때기다 — 29/29 CAUGHT(종전 28). ⚠️ 이것이 이 문서 §5 「초록 대리지표는 초록 주장이 아니다」의 «대조군 판»이다.
📐 게이트는 그대로다 — `virtual_column_render` 66/0 · 결함 29/29 CAUGHT · 대조군 2/2 ESCAPED가 이제 «여섯 파일» 위에서. 보드 하니스 일곱 무변(173 · 40 · 59 · 24 · 63 · 68 · 32).

## 🆕 5-septies. 추적 파일을 흔는 게이트는 «커밋 전후»에 다른 답을 낸다 (2026-09-13 S-214 실측 `4fc7ff2c`)

```
상황   「실행기 정의가 저장소에 «하나»」를 `git grep` 으로 세는 새 게이트
답     «0» — 새 모듈이 아직 «미추적»이어서 `git grep` 이 그것을 «못 본다»
그래서  같은 게이트가 커밋 «전»엔 0, «후»엔 1 — 모집단이 바뀜 것이지 코드가 바뀐 것이 아니다
```
🔴 **이것은 «게이트가 틀렸다»가 아니라 «게이트가 다른 집합을 재고 있다»이다** — 이 문서 §1 의 「잔라쓰기는 동작이 아니라 글자 모양을 재다」와 같은 부류다. 재는 대상이 «코드»가 아니라 «색인»이면, 내가 `add` 를 누를 때마다 답이 움직인다.
✅ **그래서 두 가지 중 하나다** — 게이트를 «파일시스템»(`os.walk`) 으로 돌리거나, `git grep` 을 쓰되 «추적된 것만 본다»를 게이트 자신이 적어 둔다.
⚠️ 그리고 이 부류는 «초록으로» 나타난다 — 개수가 0 이면 「중복 없음」으로 읽히고, 새 파일을 넣은 바로 그 라운드가 가장 위험하다.
🔵 같은 자리의 이웃 부류 하나도 같은 날 나왔다 — 한 파일만 흔는 가드(`test_finish_still_has_exactly_one_caller`)가 «그 파일 밖으로 나간 호출»을 못 봤다. 모집단을 «파일 하나»로 잡은 게이트는 이사가 일어나는 날 조용해진다.

## 🆕 5-octies. 「소스 오라클」은 «줄의 모양»을 잰다 — 좌석은 «돌려서» 잰다 (2026-09-13 S-225 `ca579f9d`, 판정 380)

```
⛔ assert "attempts_cap = min(_caps)" in body      <- 소스 오라클. «글자»를 잰다
   지역 변수 이름만 바꿔도  ->  «옳은» 좌석이 빨개진다
   `max` 를 다른 철자로 써도 ->  «틀린» 좌석이 초록으로 남는다
✅ 좌석을 «돌린다» — 규칙 «둘»이 한 그룹을 깨우고 상한이 2 와 5, 그룹은 «일부러» 실패
      시도 1 -> RETRYING   (상한이 «내장값 1 이 아님»)
      시도 2 -> FAILED     (상한이 «2 이고 5 가 아님»)
```
🔴 **반쪽씩은 «틀린 답도 만족시킨다»** — 그래서 둘을 «순서대로» 단언한다. 상한이 1 이면 첫 줄이 깨지고, 5 면 둘째 줄이 깨진다. 한 줄만 보면 어느 쪽도 못 가른다.
🔵 그리고 `processed_chain` 도 같이 단언한다 — **격리는 «이름표를 바꾼 것»이 아니라 «워커의 질의에서 빠진 것»**이고, 그 둘은 화면에서 같아 보인다.
📌 부류: 이 문서 §1 의 「잘라쓰기는 동작이 아니라 «글자 모양»을 잰다」와 «같은 병**이다 — 재는 대상이 «텍스트»이면, 코드가 맞아도 빨개지고 틀려도 초록일 수 있다. ⚠️ §3 의 예외(「텍스트가 «주어»인 하니스」)와 헷갈리지 말 것: 거기서는 텍스트가 «주어»이고, 여기서는 «대리»다.

## 🆕 5-quater. 게이트 실행은 «자기 호출»로 — 파이프가 종료 코드를 가린다 (2026-09-12, 구현자 `174346f2`)

```
❌ pytest … | tail -2 && git commit …     파이프라인의 종료 코드는 «tail 의 0» 이다
                                          -> 빨강 위에 커밋이 그대로 나간다
✅ pytest …                               게이트 실행은 «자기 호출». 출력이 길면 그건 별개 문제다
```
🔴 **실물이 그렇게 났다**: 모집단 실행과 커밋을 `&&` 로 이었는데 실행이 `| tail -2` 로 끝나서
**실패한 시험 위에 커밋이 나갔다**. 구현자가 자기 커밋 메시지에 적었다 —
**「파이프에 종료 코드가 가려진 게이트는 게이트가 아니다」**.
📌 부류는 이 문서 §5 의 「초록 대리지표는 초록 주장이 아니다」다 — 여기서 대리지표는 «파이프의 마지막 명령»이다.
⚠️ 그리고 이 저장소는 «반대 방향»으로도 값을 치렀다: `| head` 에 잘린 것을 「없다」로 읽은 것,
그리고 자식의 stdout 파이프가 차서 100k 주입이 «교착»한 것. **파이프는 답을 바꾼다** —
게이트든 측정이든, 파이프를 물리기 전에 「무엇이 종료 코드를 정하나」를 본다.

## 🆕 5-ter. 빨강·스킵이 «이름»을 갖는 두 자리 (2026-09-12 S-199-b·S-199-e, 판정 309·311)

📎 정본은 `server/tests/conftest.py` 의 docstring 이다. 아래는 «옮겨 적기»다.

### ① 판정의 «주어»가 «라이브 파일»이면 — `requires_live(shape)`

```
@requires_live("<그 파일이 어떤 모양이어야 하는가>")
def test_…            -> `ASSY_TEST_LIVE=1` 없으면 «이름 대어» skip
```
🔴 **그 시험이 틀린 것도, 라이브 파일이 틀린 것도 아니다.** 주어가 `server/mappers/*.py` ·
`server/config/*.json` 이고 그것들은 `.gitignore` 밖이다 — 즉 답이 «한 기계에 대한 사실»이고,
여기의 빨강은 «운영에 대해 아무 말도 하지 않는다». 기본으로 돌리면 **「스위트가 초록이다」가
«누구의 체크아웃인가»에 달리게 된다.**
⛔ **사유가 «요구되는 모양»을 든다** — 「스킵됐다」만 말하는 스킵은 독자에게 «그것을 무시하라»고
가르친다. 「그 라이브 파일이 «어떤 모양»이어야 했나」를 말하는 스킵이 운영자가 «행동할 수 있는» 한 줄이다.
⚠️ **양쪽 다 «고쳐서 맞추지» 않는다** — 시험을 오늘의 라이브 파일에 맞추면 «요구 자체»가 지워지고,
여기서 소유자 파일을 고치는 것은 «이 박스를 고치는» 일이다.

### ② 「의도한 빨강」이면 — **strict** xfail

```
❌ 그냥 빨강으로 둔다        스위트의 빨강 수가 «세어지지 않는 수»가 된다
❌ 느슨한 xfail             고쳐진 날에도 «조용히» 넘어간다 — 그래서 아무도 그것이 닫힌 것을 모른다
✅ strict xfail             ① 오늘 빨간 이유가 «이름»으로 남고 ② «초록이 되면 빨개진다»
```
🔵 **그 둘째 성질이 요점이다** — strict 가 아니면 xfail 은 「영원히 무해한 것」이 되고,
그것은 이 문서가 §5 에서 금지하는 「초록 대리지표」의 빨강 판이다.
📌 실물: `bonding_log` 다리가 S-127-b·S-79 의 «셋째 구성원»이라 계약 시험을 «표별»로 가르고
그 하나만 strict xfail 로 뒀다(S-199-e, 판정 311). **부류를 묶되 구성원은 «센다»** — 셋째가
나타나면 계약이 표 단위로 갈리는 것이 맞는 처방이고, 그 하나를 «부류째» 느슨하게 만들지 않는다.
🔵 **그리고 이것이 「전부 초록」보다 «읽을 수 있는» 상태다** — 수가 아니라 «목록»이고, 목록은
줄어드는 것이 보인다. 📐 **수를 인용할 때는 모집단을 적는다**: 보드가 09-12 밤에 적은
「이름 붙은 xfail 둘 + 이름 붙은 skip 다섯」은 «총괄이 돌린 그 선택»의 수다. 제가 `server/tests` 전체를
`git grep "xfail(strict=True"` 로 세면 자리가 **셋**이다(`test_replace_map_cross_scope` ·
`test_trace_fixture`(S-199-e 의 표별 parametrize) · `test_virtual_join_types`) — «다른 모집단»이라
겹쳐 쓰면 둘 다 거짓이 된다.

## 🆕 5-nonies. PostgreSQL «만» 나를 수 있는 증명 — `@pytest.mark.pg` 는 «불렀을 때만» 돈다 (2026-09-16 S-256 `baf17cfa` · S-257 `ae28b356` · S-258 `27f5d7d9` · `69f7a130`)

📎 정본은 `server/scripts/run_pg_tests.py` 의 docstring 과 `server/tests/conftest.py` 의 표지 등록 주석이다. 아래는 «옮겨 적기»다. 운영자용 한 줄은 `RUN.md` §6.

```
왜        SQLite 는 PostgreSQL 이 거절하는 것을 받는다 — jsonb · 파티션 · ON CONFLICT · CHECK · NULL 위 UNIQUE
          그래서 «PG 만» 증명할 수 있는 시험은 sqlite:///:memory: 스위트에서 픽스처가 skip 했고 «부재로 초록»이었다
          (S-104 · S-115 가 몇 달 조용했던 이유). 이 절이 준 것은 «자리»다
표지      @pytest.mark.pg — tests/conftest.py::pytest_configure 가 등록한다
          (이 저장소엔 pytest.ini 도 [tool.pytest] 도 없다: «그 훅이 설정»이다. 등록 안 된 표지는 경고뿐이라 `pgs` 오타가 증명을 «두 실행 모두»에서 조용히 떨어뜨린다)
          붙이는 곳: PG 픽스처(pg_engine · pg_session · clean_pg_v2 · ledger · pg_url · isolated_pg 스위트)로 «이미 sqlite 에서 skip 하던» 시험만
맨 pytest  tests/conftest.py::pytest_collection_modifyitems — `-m pg` 가 없으면 pg 표지를 «이름 대어» skip 한다 (`69f7a130`)
          🔴 왜: S-257 이 pg_engine 에 dev_env QA 문을 열자 QA DB 를 선언한 박스에선 «모든 레인이 돌리는 기본 게이트»가 PG 증명까지 돌기 시작했고,
             첫 만난 S-259(은퇴한 배관을 재는 trace 시험)가 «그 게이트»를 빨갛게 했다. 기본 실행은 어제의 뜻을 지키고, PG 자리는 아래 «한 명령»이다
한 명령    conda run -n assy_manager python server/scripts/run_pg_tests.py   (인자는 전부 pytest 로 그대로)
          ① 어느 서버: 제품이 푸는 «같은 길» paths.resolve_database_url (env DATABASE_URL > config/database.json > 기본). PG 가 아니면 REFUSED 한 줄, 종료 64
          ② 어느 DB: tests/support/isolated_pg.resolve_url — «한 철자» (ASSY_PG_TEST_DATABASE_URL > ASSY_TEST_DATABASE_URL > dev_env QA), db_safety 를 지나
             운영은 «이름으로» 거절. 선언이 없으면 REFUSED, 종료 64 — skip 이 «아니다»(skip 이 몇 달의 침묵이었다)
          ③ pytest tests -m pg -rs --continue-on-collection-errors — 그 DB 를 ASSY_PG_TEST_DATABASE_URL 로 «내보내서» conftest 의 pg_engine 과
             isolated_pg 스위트가 같은 박스에 대해 «다르게 결정할 수 없다». 종료 코드는 pytest 의 것
답 읽기    passed = 이 박스의 PG 에서 참 · skipped = «통과가 아니다»(-rs 줄이 이유: 서버 도달 불가 · 확장 없음) · failed/error = 재기동 «전»에 고침
          (맵퍼 시험 모듈의 error 는 이 박스의 gitignore 맵퍼·설정 부재이지 PG 의 사실이 아니다) · REFUSED + 64 = 아무것도 안 돌았다 (pytest 의 2 「interrupted」와 갈리도록 64)
```

🔴 **`--continue-on-collection-errors` 가 하중을 받는다.** pytest 는 «선택 안 된» 모듈의 수집 오류 하나로 «전체 실행»을 중단한다 — 이 박스의 gitignore 맵퍼를 import 하는 시험이 새 체크아웃에서 그렇고, 그래서 `-m pg` 가 «아무것도 안 돌고» 2 로 끝났다(실측 2026-09-16). 플래그가 있으면 증명은 돌고, 수집 오류는 여전히 찍히며 종료 코드도 0 이 아니다 — 박스가 «그것 때문에» 깨끗해 보일 수는 없다.

### 스크래치 검색 경로는 «한 철자»다 (S-257)

```
isolated_pg.scratch_connect_args(schema)   -> {"options": "-csearch_path=<scratch>,public"}
                                            스크래치가 «먼저»(증명이 만드는 것은 전부 거기 떨어져 DROP 과 같이 간다) · public 은 «뒤에서 읽기만»
                                            같은 dict 를 psycopg2.connect 도 받는다 — 경쟁 커넥션도 자기 SET search_path 없이 같은 자리에 선다
isolated_pg.install_trigram(connection, schema)  pg_trgm 을 스크래치 «안»에. 역할이 확장을 못 만들면 그 시험을 skip
```
🔴 **`public` 을 빼면 «이미 설치된» 확장이 안 보인다** — `CREATE EXTENSION IF NOT EXISTS pg_trgm` 이 «조용히 no-op» 이 되고 첫 실행에서 48 중 47 이 `UndefinedObject: gin_trgm_ops` 로 죽었다. 형제 스위트 셋은 이미 쉼표를 배웠고 conftest 와 카탈로그 시험 둘이 «없는 철자»였다 — 「전제가 성립하는 자리에서 전제가 안 보인다」 부류(`_ensure_trigram` 이 생긴 이유와 같다). `git grep -n "-csearch_path" -- server/tests` 가 `isolated_pg.py` 하나만 대야 한다.
⚰️ `conftest._resolve_pg_test_url` · `_declared_as_test_database` 는 `isolated_pg.resolve_url` / `declared_as_test_database` 의 «둘째 사본»(dev_env 문이 빠진)이었고 삭제됐다 — 그 이름은 import 로만 남아 세 시험 파일이 그대로 돈다.

### 거절 줄의 단언은 «저자를 import»한다 (S-258)

`test_a_persistent_business_key_conflict_is_refused_not_replayed` 가 은퇴한 영어 표지 「BK Conflict Unresolved」를 단언하고 있었다 — 제품은 S-247 부터 `[BKConflict:<표>] … → 다음: <widen_the_key>` 를 낸다. 수리는 한국어 문장을 베끼지 않는다: 접두는 `operator_line.line("BKConflict", TABLE, …)` 이 «앞에 붙이는 것», 다음-행동 절은 `operator_line.widen_the_key` 를 «함수에서 읽어»(`_invariant_tail` — 표지 값으로 렌더해 마지막 표지 «뒤»만 남긴다) «행동의 부류»를 판다(선언을 넓혀라 — `fold_the_data` 의 «반대» 수리). 실측: `fold_the_data` 로 지은 같은 접두의 줄은 «빨강», widen 줄은 초록. 문장을 베끼면 하니스가 «둘째 저자»가 된다(2026-09-13 의 여덟 빈-상태 문장이 같은 병이었다).

⚠️ **표지 없이 «일부러» 둔 sqlite-skip 둘** — `test_set_based_write_path` · `test_a_walk_can_be_read_as_rows` 는 `db_session`/앱 엔진을 타고, 러너는 그 엔진을 «다시 겨누지» 않는다. 📌 첫 실행이 «자리가 숨기던 것»을 드러냈다: `ledger.trace.trace` 없음 · `/api/ledger/trace` 404 · `hops`/`neighbourhood` 없음(29 건, S-259). 자리의 결함이 아니라 내용의 결함이고, 이 절이 고친 것이 아니다.

## 6. 이 문서가 부르는 이름 (2026-09-10 실측)

| 심볼 | 자리 |
|---|---|
| `scoreMutants` · `VERDICT` | `client2/tests/lib/mutation_scorer.mjs:48` · `:35` |
| `loadWithProbe` · `readSourceText` · `isProbeArtifact` · `isOwnProbeArtifact` · `MARK` | `client2/tests/lib/probe.mjs:276` · `:73` · `:124` · `:139` · `:53` |
| `resolve` (훅) | `client2/tests/lib/probe_hooks.mjs:46` |
| `fillPlan` · `renderReferenceResults` | `client2/src/enrichment_reference_view.js:126` · `:531` |
| `isReferenceSidebarCopy` | `client2/src/clipboard.js:27` |
| `MINUTE_SECONDS` | `client2/src/chain_queue_panel.js:58` |
| 프로브 잔해 단언 | `client2/scripts/check_harnesses.mjs:1642` |
| 🆕 `startup` (부팅 순서, C-110) | `client2/src/startup.js:32` |
| 🆕 `child_specs` (자식 명부의 값, S-255) | `server/runtime/launcher_specs.py:23` |
| 🆕 `PG_TEST_URL_ENV` · `scratch_connect_args` · `install_trigram` · `resolve_url` | `server/tests/support/isolated_pg.py:21` · `:44` · `:67` · `:109` |
| 🆕 `pytest_configure` · `pytest_collection_modifyitems` (pg 표지) · `run_pg_tests.main` · `REFUSED` | `server/tests/conftest.py:581` · `:588` · `server/scripts/run_pg_tests.py` |

⚠️ **`referenceHeadBand` 는 export 가 «아닙니다»** — `enrichment_reference_view.js:342` 의 모듈 지역 함수이고, 두 갈래(primary·evidence)가 그것을 부릅니다. 띠가 «한 벌»이라는 것이 요점이지 내보내는 것이 요점이 아닙니다.
