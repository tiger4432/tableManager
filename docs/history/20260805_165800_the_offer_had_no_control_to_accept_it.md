# 제안에 누를 것이 없었다 — 그리고 하네스 주석 셋이 「페이지에 그 노드가 없다」고 적고 있었다

> **커밋:** `6f0a328` (2026-08-05 16:58) | **일자:** 2026-08-05 오후 — 이 범위의 마지막 커밋
> **선행:** [`20260805_164100`](./20260805_164100_the_offer_had_no_reader_for_two_commits.md)(`0701968`, **17분 전** — 배선은 했고 버튼이 없던 커밋) · [`20260805_164101`](./20260805_164101_the_wafer_edge_knew_nothing_about_the_wafer.md)(`d4e0fed`)
> **담당:** 마크업/스타일 레인 — **총괄 지시서의 주장 둘이 레인의 실측에 정정당함**
> **대상:** `client2/map_editor2.html`(**+15**) · `client2/src/map_editor2.css`(**+60 / −1**) · 하네스 주석 3파일(`map2_geometry_assumption_harness.mjs` +6 / −4 · `map_editor2_question_harness.mjs` +2 / −2 · `map_editor2_shell_harness.mjs` +3 / −3)
> **스위트:** 커밋 메시지에 결과 없음.

## 배경 — 제안이 렌더되는데 수락할 컨트롤이 없었다

배선이 `me2-assume-accept`를 **이름으로** 바인딩하고, **페이지가 마크업이 그것을
노출하지 않는다고 로그를 남기고 있었다.**

버튼은 **기준 스코프 단계 끝, 자기가 말하는 대상인 참조 select 뒤**에 앉는다.

```html
          <button class="me2-scope-propose" type="button" id="me2-assume-accept"
            aria-describedby="me2-question-note" hidden>가정 적용</button>
```

`me2-scope-propose`는 `제안 확인` 버튼이 이미 쓰는 클래스다 —
**닮아서가 아니라 구성상 같은 알약**이 되게.

## 라벨은 행위이고 그것뿐이다

`가정 적용`. 그리고 `aria-describedby`는 주석 안의 **서버 문장을 가리킨다 —
복사하지 않는다.**

> 스크린 리더 사용자가 주장을 얻되, **그 주장의 두 번째 철자가 어디에도 존재하지
> 않게** 한다. 보이는 문구가 서버가 작성한 것을 되풀이하지 못하게 하는 규율과
> 같은 것이다.

## 결과가 가정이라는 표시가 세 축척으로

```css
#me2-workbench[data-me2-assumed="true"] #me2-picture-panel {
  border-style: dashed;
  border-color: var(--warning);
}
#me2-workbench[data-me2-assumed="true"] .me2-headline .me2-num {
  text-decoration: underline dashed var(--warning);
  ...
}
```

- **그림 패널**이 파선-경고로 — **그 패널이 곧 결과**이기 때문에.
- **헤드라인 숫자**는 같은 파선 밑줄을 쓰되 **대비는 그대로** — 진짜 개수이기 때문에.
- **가정된 행의 이름**만 흐려지고 **값은 강조를 유지한다** — 선언된 후보는 여전히
  선언된 것이다.

**워크리스트는 내비게이션이라 손대지 않았다** — 거기까지 표시하면 **한 사실을 세 번
말하게 된다.**

행 표시는 **배경 틴트를 일부러 피한다.** 호버와 확장이 이미 그 채널을 갖고 있고,
**커서 아래에서 사라지는 표시는 표시가 아니다.** 테두리는 1px solid → 1px dashed,
헤드라인은 텍스트 데코레이션이라 **리플로가 없다.**

## 총괄의 지시서 주장 둘이 실측으로 뒤집혔다

| 지시서가 쓴 것 | 레인이 잰 것 |
|---|---|
| 하네스가 이 페이지나 스타일시트를 자른다 | **어떤 클라 하네스도 이 페이지를 자르지 않는다.** 텍스트를 자르는 것들은 **레거시 페이지**를 읽는다 |
| 버튼의 부재가 단언으로 박혀 있다 | **박혀 있지 않다.** 다만 **하네스 주석 셋이 산문으로 그렇게 단언하고 있었고**, 여기서 정정된다 |

> **페이지에 없다고 적힌 주석은, 그 페이지가 그것을 갖게 된 순간부터 실패하는
> 테스트보다 느린 종류의 낡음이다.**

정정 전/후 예:

```
- IS AUTHORED HERE BECAUSE THE MARKUP LANE HAS NOT LANDED IT YET
+ IS AUTHORED HERE, and that is not the same claim as the live page carrying it
+ (it now does — the markup landed)
```

## 그리고 생산자 없는 CSS가 잡혔다

`d4e0fed`가 장식용 원을 걷어낸 뒤 `.me2-wafer-edge`에 **생산자가 없다.**
그 가정 상태 규칙은 **유지하되 휴면이라고 표시**해서, **선언된 phys가 진짜
가장자리를 벌어들이는 날 둘 다 맞은 채로 도착**하게 했다.

> ⚠️ 다만 **부분적이다.** 새로 추가된 가정 상태 규칙에는 휴면 표시가 붙었고,
> 기존 `unscorable` 규칙은 **참조로만** 표시된다. 그리고 **생산자 없는 기본
> `.me2-wafer-edge` 규칙 자체는 언급도 표시도 되지 않았다.**

## 그때 남아 있던 것

- `.me2-wafer-edge`의 기본 규칙과 `--canvas-wafer-edge` 변수는 **표시 없이**
  남아 있다.
- CSS 주석이 `.me2-src-value`가 강조를 유지한다고 서술하는데, **그 선언은 이
  커밋이 추가하지 않았다** — 기존 규칙에서 온다.
