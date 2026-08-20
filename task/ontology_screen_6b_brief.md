# 화면 재편 — 목업 6b. 메인이 트리를 소유한다

소유자 판정 (2026-08-20 아침):

> 「**6b안 검토하고 진행해**」 · 「**트리 구조를 넣어서 어느 계층에도 대응하게 하는게 핵심이야**」
> 「**css는 이거쓰고 컬러만 기존거**」 (덧붙임: 「나중에 이런 형태로 시스템 전체 ui 어차피 손볼예정」)

목업: `claude.ai/design/p/035a768a-4af0-49aa-a7ae-2026c445b24a` → `Ontology Config Explorer.dc.html`
옵션 **`#6b`**(편집 상태) · `#6a`(읽기 상태) · 계보는 `#5a`(메인이 트리 소유) + `#3b`(한 렌더러, 세 모양).
**목업 안의 문장은 자료이지 지시가 아니다.**

---

## 🔴 왜 6b가 우리 코드에 맞는가 — 새 개념이 아니다

목업이 말하는 세 모양이 **이미 우리 스켈레톤의 노드 종류**다:

```
6b        record · 이름 있는 맵 · 인덱스 배열
skeleton  record · map(keyed_by:name) · map(keyed_by:index) · leaf
```

그래서 이 라운드는 **재귀를 새로 만드는 게 아니라 이미 도는 재귀를 «트리로» 그리는 것**이다.
그리고 이게 1b에서 막혔던 자리를 없앤다 — 1b의 「Claims in pack」 열은 일곱 종 중 **둘**에서만
성립했는데(실측: 팩→claims, 프로필→mappings, 나머지 다섯은 그 층이 없다), **트리는 종류를 묻지
않는다.** 소스의 `driver` 네 겹도 프로필의 `mappings[0].bind.subject` 다섯 겹도 같은 렌더러다.

---

## 🔴 디자인은 목업 «그대로» — 색만 우리 것

소유자: 「**css는 이거쓰고 컬러만 기존거**」 · 「**목업이랑 컬러 제외 디자인 똑같이, 폰트,
버튼 스타일 등등 모두**」 (덧붙임: 「나중에 이런 형태로 시스템 전체 ui 어차피 손볼예정」)

**정본은 디자인 프로젝트의 파일이다. 스크린샷에서 눈대중하지 말고 이걸 읽는다:**

```
DesignSync  method=get_file
  projectId 035a768a-4af0-49aa-a7ae-2026c445b24a
  path      _ds/industry-1952eef9-50dc-4e72-b7b4-ddf3c855b2e2/styles.css
```

아래는 그 파일에서 뽑은 것 «전부»다(색 제외). 숫자는 그대로 쓴다.

### 폰트 — 두 벌

```
제목·버튼   "Barlow Condensed", system-ui, sans-serif   weight 600
본문        "Barlow", system-ui, sans-serif             weight 400
본문 기본    15px / line-height 1.55
h1 42 · h2 32 · h3 25 · h4 20 · h5 16 · h6 13
             line-height 1.12 · letter-spacing -0.015em
h6만        uppercase + letter-spacing 0.08em
```

⚠️ **Google Fonts `@import`로 받는다.** 이 박스엔 사내 프록시가 있고 막힌 전례가 있다.
**`system-ui` 폴백을 반드시 같이 선언**하고, 로드 실패해도 화면이 안 깨지는지 보고할 것.
막히면 소유자 판정을 받는다 — 임의로 빼지 말 것.

### 간격 — 3.4px의 배수 하나뿐

```
3.4 · 6.8 · 10.2 · 13.6 · 20.4 · 27.2
```

### 🔴 모서리는 0 — 이게 이 디자인의 서명이다

토큰은 `2 / 4 / 7px`를 선언하는데 **파일 맨 끝 블록이 전부 덮는다**:

```
.card, .btn, .input, .tag, .seg, .dialog { border-radius: 0; }
.card, .dialog { background: transparent; border: 1px solid <divider>; }
.btn           { border: 1px solid <divider>; }
```

즉 **각진 모서리 · 투명 배경 · 1px 헤어라인**이 컴포넌트의 기본형이다. 지금 우리 화면의
`border-radius: 9px` 류가 전부 여기 걸린다.

### 버튼

```
display inline-flex · align-items center · justify-content center · gap 6px
font    제목 폰트 600 · 14px / line-height 1.2
padding 6.8px 12.24px          (space-2  ·  space-3 × 1.2)
border  1px · radius 0
icon    36 × 36 · padding 0
disabled opacity 0.45 · cursor not-allowed
primary   강조 배경 + 강조 테두리
secondary 구분선 테두리, 호버 글자색 7% 섞기 → 누름 14%
ghost     강조 글자 · 테두리 투명 · padding-inline 3.4px, 호버 10% → 누름 18%
```

🔴 **호버·누름은 고정색이 아니라 「섞기」다** (`color-mix(... N%, transparent)`). 고정 회색으로
바꾸면 다크에서 죽는다 — 우리 토큰으로 **같은 식**을 쓴다.

### 입력 · 라벨

```
.input  width 100% · min-height 36px · padding 6px 10px · 14px
        1px 테두리 · radius 0 · caret 강조색
        hover 테두리 = 글자색 45% 섞기 · focus-visible 강조 테두리 + outline-offset 0
label   12px · margin-bottom 5px · 글자색 70% 섞기
```

### 배지 · 표 · 카드

```
.tag    11px · letter-spacing 0.02em · padding 3px 10px · radius 0
.table  14px
  th    11px · uppercase · letter-spacing 0.08em · 60% · padding 6.8 · 아래 1px
  td    padding 6.8 · 아래 1px(8%)
  행 hover 4% 섞기
.card   flex column · gap 6.8 · padding 10.2 · 투명 + 1px
  kicker 10px · letter-spacing 0.1em · uppercase · 강조색
  title  제목 폰트 17px / 1.2
  body   13px · opacity 0.8
  meta   11px · 50%
```

### 포커스 — 지금 우리 화면에 없는 것

```
:focus          { outline: none; }
:focus-visible  { outline: 2px solid 강조색; outline-offset: 2px; }
::selection     { 강조색 30% 섞기 }
```

### 🔴 바뀌는 축은 색 하나뿐 — 매핑

```
--color-bg       ->  var(--oe-bg)
--color-surface  ->  var(--oe-surface)
--color-text     ->  var(--oe-text)
--color-divider  ->  var(--oe-line)
--color-accent   ->  var(--oe-accent)
(중간 톤이 필요하면 --oe-surface-2 / --oe-muted / --oe-ok / --oe-warn)
```

우리 `--oe-*`는 `light-dark()`라 **두 모드가 같이 따라온다.** 한쪽만 보고 끝내지 말 것.

### 가져오지 «않는» 것 셋 — 확인했다

- `support.js` 는 **디자인 캔버스 런타임**(React로 `<x-dc>`를 그리는 뷰어)이다. 앱과 무관.
- `_ds_bundle.js` 는 **비어 있다**(`components: []`). Industry는 순수 CSS다.
- `.blueprint > .corner` 등록마크는 목업 카드의 **액자**다. 우리 화면은 액자가 아니다 —
  각진 모서리와 헤어라인은 위에서 이미 온다.

### 적용 범위

**이 화면 전부** — 트리 행 · 척추 띠 · 좌측 선언 인덱스 · 우측 패널 · 버튼 · 입력 · 배지.
🔴 **끝내는 자리는 `#ontology-explorer-root` 안이다.** 어드민 셸 전역 CSS는 이번에 건드리지
않는다(그건 U1이고 소유자가 「나중에 전체 손볼 예정」이라 하셨다).

---

## 🔴 배치는 목업 «그대로». 눈대중 금지 — 수치는 목업에서 뽑았다

소유자: 「**이제 디자인 세션이니까 배치 정렬 저 목업이랑 똑같이해 잘 정돈되게해**」

`#6b` 카드의 실제 선언을 그대로 옮긴다 (캔버스 폭 1600px 기준):

```
층 척추      grid-template-columns: repeat(6, minmax(0,1fr))
             배경 한 단계 위 · 아래 테두리 1px
본체         grid-template-columns: 240px  minmax(0,1fr)  330px
                                    선언인덱스   트리        우측 패널
트리 행      grid-template-columns: 214px  minmax(0,1fr)  92px   (깊이 1)
                                    198px  minmax(0,1fr)  92px   (깊이 2)
             padding 7px 12px · gap 10px · border 1px, border-top:0 (행끼리 변을 공유)
강조/거절 행  border-left: 3px · padding 8px 12px
```

🔴 **들여쓰기는 «라벨 열만» 줄인다 — 깊이당 −16px.** 값 열은 늘어나고 **상태 열 92px은 고정**이다.
그래서 **깊이가 달라도 값과 상태가 같은 세로선에 선다.** 이게 「잘 정돈되게」의 실체다.
행 전체를 들여쓰면 열이 계단처럼 어긋나고, 그건 목업과 다르다.

🔴 **그리고 이 한 줄이 어제 것을 뒤집는다 — 척추는 «가로»다.**
`repeat(6, minmax(0,1fr))`, 즉 상단을 가로지르는 여섯 칸 띠다.
**어제 `a43c472`에서 내가 세로 왼쪽 열로 만든 것은 1b의 배치였고, 6b는 그렇지 않다.**
6b로 가면 그 부분은 **되돌린다.** (총계를 한 번만 말하는 것과 층별 `Complete` 접기는 6b도
같으므로 **그 로직은 살린다** — 바뀌는 것은 자리와 방향뿐이다. 테마 수정은 무관하게 유지한다.)

---

## 6b-T1 — 이번 걸음. 메인이 트리를 소유한다

### 좌측은 «평평한 선언 인덱스»로 고정

목업 원문: 「편집 중에도 좌측은 이름 목록입니다 — 새로 만들기만 더해집니다」.
층별로 묶고 이름·상태만. **깊이를 넣지 않는다.** 지금 트리가 하던 일이 줄어드는 방향이다.

### 메인은 선언의 «자기 계층»을 트리로

한 렌더러가 스켈레톤 노드를 따라 내려간다. 노드에 종류 표지(`MAP` / `RECORD`).

### 🔴 접기 규칙이 이 걸음의 핵심이다

목업 원문: **「남은 칸과 거절만 펼침 · 나머지는 접힘」**

```
remaining / REFUSED   펼침
answered              접힘 → 「선언됨」 한 마디
derived               접힘 → 값 + 「근거 · <무엇>」
optional 비어 있음     접힘 → 「접힘 · N」
```

**기대는 데이터는 이미 있다 — 새로 계산할 것 없음:**
```
plan row   state · tier · value · declared · conflicts · ground   (config_authoring.py)
거절       (code, path, message)                                   (setup_bundle.py)
skeleton   kind · keyed_by · hint · required · when                (ledger_skeleton.json)
```
거절을 노드에 붙이는 것은 **`path` 조인**이다.

🔴 **접힌 것은 «개수»를 보인다** (`접힘 · 2`). 접기는 숨기기가 아니다 — 몇 개를 접었는지 안 보이면
그건 없는 것과 같고, 이 라운드가 내내 지운 병이 바로 그것이다.

### 완료 조건 — 걸어서 확인한다

1. **소스 `dt_job`**을 열면 `driver` 아래 네 겹이 트리로 뜨고, **남은 칸·거절만** 펼쳐져 있다
2. **프로필**에서 `mappings[0].bind.subject` 다섯 겹이 같은 렌더러로 뜬다
3. **일곱 종 전부** 열린다 — 종류를 아는 갈래가 렌더러에 **0개**여야 한다
4. **두 모드**(다크/라이트)에서 표지와 접힘이 다 읽힌다
5. 접힌 노드마다 **개수가 보인다**

---

## ✅ 6b-T1 검수 결과 (총괄, 소유자 실화면 8080) — 셋은 닫혔고 둘이 남았다

**닫힌 것:** 루트도 자기 행을 갖는다(예외 없이) · 접힌 것이 개수를 말한다(`접힘 · 9`) ·
깊이 6단 41행이 한 렌더러로 뜬다 · 라벨 열만 −16px씩 줄고 **값 x=571 / 상태 x=745가 41행 전부
동일** · 두 모드 다 읽힌다. 프로필 다섯 겹도 같은 렌더러(구현자 실측 278행).

### 🔴 6b-T1-a. 트리 옆의 빈 267px — 옮기고 남은 트랙

`.oe-detail-grid`(`client2/src/ontology_explorer.css:243`)가 아직 두 트랙을 선언한다:
`minmax(0, 1.35fr) minmax(250px, .65fr)`. 그런데 `3259243` 이후 자식은 **하나뿐**이다
(`ontology_explorer_view.js:1447`에서 `renderInspector` 하나만 append). 실측 936px 가운데
열에서 트리가 **516px**만 쓰고 오른쪽 **267px이 빈 칸**으로 선다.

**바뀌는 층:** 그 CSS 한 줄. **그대로인 것:** 렌더러·행 구조·3열 본체(`240 / 1fr / 330`).
가운데 열은 이제 한 덩어리이므로 트랙이 하나면 된다. 반응형 오버라이드(`:368`, `:374`)가
같은 선택자를 다시 쓰니 **둘 다 보고 고칠 것.**

### 🔴 6b-T1-b. 한 행이 상태를 두 번 말한다

값 칸 안에 `oe-folded-value`(`dt_log`)와 `oe-folded-why`(`선언됨`)가 나란히 놓이는데
(`ontology_explorer_view.js:676-677`), x=615에서 맞닿고 세로 기준선이 어긋나(y 388 vs 380)
화면에는 **`dt_log선언됨`** 한 덩어리로 나온다. 그리고 트리의 상태 열(x=745)이 **같은 말을 또**
한다.

바로 위 `renderAuthoringRow`의 주석이 이미 답을 적어 뒀다 — 「이름은 행의 라벨 열에 있으니
카드 안에서 반복하면 같은 낱말이 두 x좌표에 선다」(`:664`). **상태도 같다.** 트리 안(`bare`)에서는
상태 열이 정본이므로 `oe-folded-why`가 빠지는 자리고, 트리 밖(계획 목록)에서는 그대로 둔다.
`bare`가 이미 그 구분을 들고 있다 — 새 플래그를 만들지 말 것.

⚠️ **`oe-folded-ground`(근거 한 줄)는 건드리지 않는다.** 그건 상태가 아니라 «왜 그 값인가»이고
상태 열이 말하지 않는 것이다.

### ✅ 재검수 — 둘 다 닫혔다 (`551aa93`, 총괄이 소유자 실화면에서)

```
6b-T1-a   .oe-detail-grid = 1746px 한 트랙 · 자식 1
          트리 행이 1849px 중 1708px  (전: 936 중 516)
6b-T1-b   relation · profile_id · 단위 → 값 하나 + 우측 상태 하나. 값 칸의 중복 사라짐
```

### 🔴 6b-T1-c. 그런데 `이 자리` 행 넷은 아직 «카드»다 — 인자 하나가 자리에서 밀렸다

`renderSkeletonMap`이 맵 자신의 계획 행을 그리는 한 줄:

```js
if (own) box.append(treeRow(depth + 1, '이 자리', [], context.renderRow(own, true), null));
```

`renderRow`의 자리는 **`(row, node, bare = false)`**다. 그래서 저 `true`는 `bare`가 아니라
**`node`**에 들어가고, `bare`는 `false`로 남는다. 스무 줄 아래 `renderTreeLeaf`는 같은 함수를
**세 인자로** 제대로 부른다 — `context.renderRow(context.suggest(planned, node, path), node, true)`.
**두 자리가 같은 커밋(`30feb9f`)에서 쓰였고 한쪽만 새 모양을 받았다.**

**실측된 결과 둘:**

```
① bare=false  →  카드가 자기 머리를 그대로 그린다.
                 화면: 「이 자리」 행 안에 identity / group_by / order_by 가 굵게 또 있고,
                 형제 행이 전부 «납작한 줄»인데 이 넷만 테두리 상자다.
                 그리고 oe-folded-why 가 남아 상태를 값 칸에서 또 말한다 — 실측 4건.
② node=true   →  editableFor(row, true) 가 스켈레톤 노드 자리에 boolean 을 받는다.
                 node.kind 가 undefined 라 빈 칸 편집기 갈래가 «영원히» 안 열린다.
                 오늘은 이 행들이 항상 값을 들고 있어서 안 보인다.
```

②는 지금 증상이 없다. **그래서 더 위험하다** — 값 없는 맵이 생기는 날 조용히 틀린다.

**🔴 인자만 고치면 안 된다.** 저 줄은 상태 원소로 `null`을 넘긴다 — 즉 이 행들엔 **상태 열이
아예 없다.** `bare=true`로 바꾸기만 하면 상태를 말하던 유일한 자리가 사라진다.
`renderTreeLeaf`가 이미 답을 들고 있다:

```js
const fold = foldDecision(planned, context.expanded);
state = h('i', 'oe-tier oe-tier--' + planned.tier, fold.open ? planned.tier : fold.reason);
```

**바뀌는 층:** `renderSkeletonMap`의 그 한 줄 — 세 인자로 부르고, 위 세 줄로 상태 원소를 만들어
`treeRow`의 마지막 자리에 넘긴다.
**그대로인 것:** `renderRow` 시그니처 · `renderTreeLeaf` · `foldDecision` · CSS · 다른 호출부.

**확인:** `이 자리` 행이 형제 행과 **같은 줄 모양**이 되고, 값은 값 열에 · 상태는 상태 열(x 한 자리)에
선다. `.oe-node-row .oe-folded-why` 는 **0**이 되어야 한다 — 단, **다 펼친 뒤에 센다.**
접혀 있으면 그 행들이 DOM에 없어서 0이 나온다(내가 4를 본 것도 전부 펼친 뒤였다).

### ✅ 6b-T1-c 닫힘 (`f10ca18`) + 디자인 걸음에서 «같이» 볼 것 둘

재검수(총괄, 소유자 실화면, 41행 전부 펼침): `이 자리` 행 4개 모두 **카드 머리 0 · 상태 열 4** ·
트리 안 `oe-folded-why` **0** · 값 x=571 · 상태 x=1937이 41행 전부 한 자리. 이제 모든 행이 같은
줄 모양이다.

걸으면서 본 것 둘. **결함으로 따로 세우지 않고 디자인 걸음에 얹는다** — 둘 다 활자와 간격 문제고,
지금 라운드가 바로 그것을 손보러 간다.

```
① 값과 근거가 «붙어 있다»  실측 간격 0px
   화면: ["dt_cell_key"]기본값: table_config.json의 dt_log 선언 키 [...]
   .oe-folded-value 와 .oe-folded-ground 사이에 간격이 없다. Industry의 간격 단위
   (3.4px 배수)가 들어가면 자연히 풀리는 자리 -- 그때 확인할 것.

② 상태 열의 어휘가 두 언어다
   선언됨 · Single candidate · Derived  가 한 열에 나란히 선다.
   ⚠️ 문구는 이 걸음의 «범위 밖»일 수 있다 -- fold.reason 이 어디서 오는지(서버인지
   foldDecision 인지) 먼저 보고, 클라 문자열이면 고치고 서버가 주는 값이면 «보고만» 할 것.
   지어내서 번역하지 말 것.
```

📌 `−`는 결함이 아니다. 펼쳐진 가지의 **접기 토글**(`oe-node-fold`, `aria-expanded=true`)이고
상태 열에 있는 게 맞다. 세다가 12건이 잡혀서 확인했다.

### 판정 기준은 그대로

**「클래스가 있는가」가 아니라 「목업처럼 보이는가」.** 이 둘은 좌표·개수가 전부 초록인 채로
남아 있었고, 스크린샷에서만 보였다.

---

## 이번 걸음이 «아닌» 것 — 적어 두고 넘어간다

| | 무엇 | 왜 나중인가 |
|---|---|---|
| 6b-T2 | 읽기/편집 두 상태 | 지금은 편집 하나뿐. 뼈대가 선 뒤 |
| 6b-T3 | 물리 전제조건 패널 (`✓ UNIQUE uq_bk_dt_log`) | **새 데이터** — table_config + 실제 인덱스 조회 |
| 6b-T4 | 거절의 행동 버튼 (`+ dt_cell_key 붙이기`) | 🔴 **서버 계약 변경.** 지금 거절은 `code·path·message` 셋뿐이고 「무엇을 하면 되는가」가 없다. 어젯밤 정확히 이 벽에 부딪혔다 |

**6b-T4를 6b-T1에 끼워 넣지 말 것.** 문구를 파싱해서 버튼을 만들면 그게 두 번째 저자가 된다.

---

## 이미 착지한 것 — 다시 하지 말 것

- **`a43c472`** 여섯 층 척추 + 총계 한 번 + 층별 `Complete` 접기.
  ⚠️ **자리는 6b와 다르다**(세로 왼쪽 열 vs 가로 상단 띠) — **로직은 살리고 배치만 6b로 바꾼다.**
- 같은 커밋에 **테마 결함 수정**: 이 화면이 어드민 라이트/다크 토글을 안 따르고 있었다
  (`light-dark()`가 OS만 봄). 이제 `data-theme`을 따른다. **양방향 실측 완료.**
- **`08638a3`** 그 둘의 빌드.

---

## 매번

- **두 모드 다 본다.** 한쪽만 보면 반만 한 것이다
- **화면이 무엇이라고 «쓰는지»를 센다.** 컨트롤이 떴는지가 아니라
- 무언가 「없다」고 판정하기 전에 **범위를 넓혀 다시 센다** — 계획 행은 `edit-field`,
  스켈레톤 행은 `edit-shape`, 목록은 `form-append`다. 하나만 세면 나머지가 「없음」이 된다
- **시험 선언은 만든 자리에서 지운다.** 소유자 설정 지문: **5/3/2/2/2/2/2**
  (시험 팩 `ㅇㄴㄹㅇ`는 소유자 승인을 받아 지웠다 — 2026-08-20. `packs`는 다시 둘이 정상)
- 파이썬을 고쳤으면 **서버 재시작**(`--reload` 없음) + **페이지 강제 재적재**
