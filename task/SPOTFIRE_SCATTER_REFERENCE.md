# 스팟파이어 산점도 — 근원 시각화 부품의 참조 (총괄, 10-12 밤)

소유자가 띄운 로컬 스팟파이어 `http://localhost:8001/?view=9df3370b-0a82-4e2d-94cf-63ede59b553a` 를 총괄이 눌러 보고 뜬 것.
페이지 «근원 부품»(산점도 · 범례) · «Marking»(선 그래프 -> 산점도 상세). 소유자: 「너 쓰라고 만든 거니 막 눌러보고 바꿔도 됨」.

⚠️ **구조(요소 짜임 · 역할 · 배치)만 참조한다.** 스팟파이어의 JS · CSS 코드는 가져오지 않는다(그들의 저작물). 우리 코드로 같은 짜임을 짓는다.
⚠️ 스팟파이어 웹은 그림을 «서버가 이미지로 그려» 보낸다(`sf-element-canvas-image`). 우리는 화면에서 그린다(ECharts) — 같은 것은 «짜임과 동작»이다.

## 1. 그림 영역 — 부품을 격자에 앉히는 자리

```
visualization-area                      페이지의 그림 영역
  visual-enclosure × N                 그림 하나씩 (같은 종류 여럿 가능 — 소유자가 산점도를 넷으로 늘려 보임)
    visual.<종류>                       종류 클래스: scatter-plot · line-chart · text-area …
      visual-content                   본문
      visual-title (위, 끌 수 있음)      제목 글 + 오른쪽 단추 무리
  visual-outline                       활성 그림 테두리
  splitter-container · splitter × N    그림 사이 크기 조절 막대
  annotations-container · comments-container
```
우리: grid_shell 의 배치 데이터가 그림 영역, 부품마다 자기 div 가 visual. 크기 조절 막대는 «나중»(grid_shell 주석 — 끌기 없음)으로 남아 있다.

## 2. 산점도 부품 하나의 짜임

```
visual.scatter-plot
  visual-content
    legend (세로 · 오른쪽 · 폭 150)
      legend-item  «Marker by:»   제목 + 칸 고르기 [칸 이름 ▾](끌 수 있음) + [+ Add one more column]
      legend-item  «Color by:»    제목(+ «값 가로로» 단추) + 칸 고르기 + 값 목록
                                   값 하나 = 색 아이콘 + 이름, 상태 표시 marked / dimmed + «markable»(범례를 눌러 찍음)
      legend-item  «Shape by:»    제목 + 칸 고르기 + 값 목록(«All values»)
      legend-item  «Size by:»     제목 + 칸 고르기
      scroll-bar (오른쪽 · 아래)
    axis-tray-area (왼쪽, Y)       [Urban Population % ▾](세로 글) + [+ Add one more column]
    axis-tray-area (아래, X)       [Population ▾]
    canvas-visualization           그림 본체(+ 왼쪽 · 아래 «상호작용 영역»: 축 눈금 위를 누르는 자리 — 축 창이 뜸)
    actions-container
  visual-title
    제목 글 «Urban Population % vs. Population»
    단추(오른쪽): Close · Legend · Properties · Show/hide controls · Maximize visualization · Recommendations based on marked data
```
- 축 칸 고르기는 마우스를 올려야 ▾ 가 보인다(auto-hide). 칸은 끌어다 다른 축 · 범례로 옮길 수 있다(draggable · drop).
- 축 위(상호작용 영역)를 누르면 축 창: 격자선 · 기준선 값 · 세로 흩뿌리기 · 점 크기 · 숫자 서식(기본 · 소수 · 통화 · % · 지수).

## 3. 속성 창(선언) — 오른쪽 패널, 웹 컴포넌트

```
group «Visualization properties» + 닫기
search-bar «Type to search»
list-box   고른 그림 이름 + 옵션
tabs       Configuration | Appearance
scroll-container
  Configuration
    Data          데이터 표 + 아이콘 셋 · 펼치면 Data limiting: 좁히는 마킹들 · Use filtering from page · 식 조건([Population] is not null) · Add limitation
                  «좁히는 마킹이 비었을 때»: Message or empty background + 문구 글 · Data table matching
    X-axis        칸 · 펼치면 Scale position(아래/위) · Show labels(가로/세로/최대 수) · Reverse scale · Log scale · Edit scale range · Format as · Label rendering
    Y-axis        칸 + «+»
    Color by      칸 + «+»
    Marker by     칸
    Marking       «Marking: Marking (11)» · Change marking · Use separate color for marked items(꺼짐)
    Legend        보일 항목: Data limiting · Show/hide · Trellis by · Marker by · Color by · Shape by · Size by · Error bars · Add item
    Labels
    Tooltip       보일 값: Marker by · Shape by · Color by · Size by · Rotation by · X · Y · Add value
    + Add
  Appearance
    Color of all values · Color of empty values · Shape · Marker size % (슬라이더) · Transparency % (슬라이더)
```

## 4. 마킹 (Marking 페이지에서 눌러 봄)

```
이름 붙은 마킹 여럿        Marking · Marking (10) · Marking (11) …
그림마다                   «쓰는 마킹 하나»(Marking 절) + «좁히는 마킹 여럿»(Data limiting)
예                         선 그래프 -> Marking (10) 에 씀 · 산점도는 Marking (10) 으로 좁히고 자기는 Marking (11) 에 씀
찍기                       누르기(하나) · 끌어서 사각형(여럿) · 빈 곳 누르기(지움) · 범례 값 누르기
표시                       찍힌 것 제 색 · 안 찍힌 것 흐림(«찍힌 것만 다른 색»을 켜면 다른 색) · 범례 값도 marked / dimmed
수                         바닥줄 «N of N rows · N marked · N columns · 표 이름»
좁혀진 그림이 비면           선언한 문구 «Mark regions in the line chart to view country details»
```

## 5. 우리 뜻으로 옮길 때

| 스팟파이어 | 우리 |
|---|---|
| 좁히는 마킹 | 그 마킹에서 «걷기»(start) — 행을 거르지 않는다 |
| 쓰는 마킹 | 부품 선언 writes |
| 축 칸 | { row, route, value, reduce } — 걷기 표 «+ Column» 고르기 (b19236b03) |
| 집계식 «Sum(Population)» | 보이는 꼴은 같게, 이름은 서버 어휘(답 전) |
| 식 조건 · 페이지 필터 | 없음 — 걷기 인자로 넓힐 일(따로) |
| 바닥줄 N rows · N marked | 시험대 화면에 둔다(행 = 닿은 노드) |
| 그림 서버 이미지 | 화면에서 ECharts |

## 6. 같은 구조를 다시 뜨는 법

스팟파이어 탭의 개발자 도구 콘솔에서(우리 스크립트):

```js
function outline(root, maxDepth = 16, maxLines = 200) {
  const lines = [];
  const walk = (el, d) => {
    if (lines.length >= maxLines || d > maxDepth) return;
    if (el.tagName === 'svg') { lines.push('  '.repeat(d) + 'svg (icon)'); return; }
    const cls = [...el.classList].filter((c) => /^sf/.test(c)).map((c) => c.replace(/_\d+$/, '')).slice(0, 4).join('.');
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ').slice(0, 40);
    const attrs = ['role', 'title', 'draggable'].map((a) => (el.getAttribute(a) ? `${a}=${el.getAttribute(a).slice(0, 40)}` : '')).filter(Boolean).join(' ');
    const keep = cls || own || attrs;
    if (keep) lines.push('  '.repeat(d) + `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''} ${attrs} ${own ? '«' + own + '»' : ''}`);
    for (const c of el.children) walk(c, d + (keep ? 1 : 0));
    if (el.shadowRoot) for (const c of el.shadowRoot.children) walk(c, d + 1);
  };
  walk(root, 0);
  return lines.join('\n');
}
outline(document.querySelector('.sf-element-visual.sfc-scatter-plot'));
```

## 7. 요소 = 노드 또는 허브 (소유자 10-12 밤 「각 요소가 다 노드거나 노드 허브고 허브를 통째로 마킹할 수도 · 노드의 집합도 가상의 한 노드 · 우리 걷기 스킴과 동일」)

```
그림의 요소 하나 = 노드 하나 또는 허브(노드 묶음) 하나
   산점도 점        노드 하나
   크로스 테이블 칸  그 칸에 든 노드들의 허브 (타입 + 값 조건)
   범례 값          그 값을 가진 노드들의 허브 (타입 + 값 조건)
   걷기 허브        같은 걸음으로 닿은 노드들 (노드 + 술어 + 방향)
마킹             노드와 허브가 같이 든다 — 허브는 «통째로» 한 노드처럼
허브의 정체       «목록»이 아니라 «설명» — 노드를 따로 저장하지 않는다(걷기의 «설명된 씨앗»을 넓힌 것)
허브에서 걷기     그 구성원들에서 걷는다 — 걷기가 허브를 시작점으로 받는다
값 조건 허브      걷기에 «값 조건» 인자가 생겨야 시작점이 된다(스팟파이어 식 조건 · 필터와 같은 넓히기)
```
