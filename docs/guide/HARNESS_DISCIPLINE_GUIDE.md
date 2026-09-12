# 🧪 HARNESS DISCIPLINE — 하니스가 «무엇을» 재는가

> **이 문서가 정본입니다.** CLAUDE.md 의 「잘라쓰기 하니스 절대 금지」 절은 «왜»를 적고, 여기는 «어떻게»를 적습니다.
> 신설 2026-09-10 (D-2). 아래 모든 심볼·줄 번호는 그날 소스에 대고 확인했습니다.

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

⚠️ **`referenceHeadBand` 는 export 가 «아닙니다»** — `enrichment_reference_view.js:342` 의 모듈 지역 함수이고, 두 갈래(primary·evidence)가 그것을 부릅니다. 띠가 «한 벌»이라는 것이 요점이지 내보내는 것이 요점이 아닙니다.
