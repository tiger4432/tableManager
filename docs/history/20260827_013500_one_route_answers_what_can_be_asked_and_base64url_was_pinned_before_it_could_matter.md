# 「물을 수 있는 것」에 라우트 «하나»가 답하고, base64url 이 «문제가 되기 전에» 못 박혔다

> **커밋:** `b7877d8f` (01:07) · `2e8200d3` (01:21) · `4eb4dea1` (01:35) · `6da3a177` (02:13)
> · `02ff6abd` (02:26) · `819f4d13` (12:51) · `148248be` (17:26) · `e4ab4b0e` (19:29)
> | **일자:** 2026-08-27 새벽 / 낮
> **레인:** 서버(선언 카탈로그) + 클라(걷기 상자)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 걷기 상자에 드롭다운 넷이 필요한데 재료는 이미 선언에 있다

코드 쪽에 사본을 두면 드리프트한다. `b7877d8f`이 **선언 «만»** 읽는 라우트 하나를 세웠다:

```python
# server/ledger_trace_router.py
@router.get("/declaration")
def ledger_declaration_catalog():
    ...
    from ledger import config as _config
    declared = _config.load() or {}
    ...
    return {"state": "ready" if entities else "empty",
            "entities": entities, "predicates": predicates,
            "collect": list(ledger_subgraph.NODE_KINDS)}
```

`GET /api/ledger/declaration`. `entities[] {type, keys}` · `predicates[] {name, subjects, object}`
— 둘 다 정렬 — 과 `collect[]`. 선언을 못 읽으면 **503 `declaration_unreadable`**.
**원장 행은 한 줄도 안 읽는다.**

## 🔴 그 카탈로그가 «422 를 내는 값»을 광고하고 있었다

`b7877d8f`은 `NODE_KINDS` **여덟을 전부** 내보냈고 그중 **둘은 walk 이 422로 거절**한다.
**16시간 뒤 `148248be`가 고쳤다** — 「`/declaration`은 walk 이 «받는 것»을 광고하지,
자기가 아는 것 전부를 광고하지 않는다」.

## 상자가 앉았다 — 그리고 자초한 결함 둘

`2e8200d3`. 프리빌드가 실패했는데 **`npm`이 종료코드 0으로 끝나서 dist 가 안 바뀌었고**,
바인딩이 `options.part`를 읽는데 부품은 `decl` 밑에 있어서 **라우트가 200을 답하는 동안
아무것도 주입되지 않았다.**

## base64url 이 못 박힌 자리 — «오늘은 아무 차이가 없어서» 못 박았다

```js
// client2/src/rnd_board/api.js
export function entitySeedId(type, keys) {
  const bare = String(type || '').split('@')[0];
  const json = JSON.stringify([bare, keys || {}]);
  const b64 = btoa(unescape(encodeURIComponent(json)));
  return 'ledger-entity:v1:' + b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
```

`4eb4dea1`은 **이 줄을 안 바꿨다.** 위에 계약 주석을 달고 하니스 절을 붙였다.
닫은 것은 **반증 불가능성**이다 — 오늘 쓰이는 모든 씨앗이 `+`나 `/` 없이 인코딩되므로
표준 base64 와 base64url 이 **같은 답**을 내고, 「단순화」로 표준 base64 로 되돌려도
`SYN-BW-101-16>` 같은 키가 나타나기 전까지 **조용히 맞다**(표준 → 422, base64url → 200).
단언 S1 이 **픽스처가 실제로 `+`를 만드는지**를 고정한다.

같은 커밋이 진짜 렌더 버그도 고쳤다 — 절단 알림이 표 호스트 «밖»에 있어야 한다.
`TablePart.render()`가 자기 호스트를 지우기 때문이다.

## 문법 하나에 소유자가 하나

`6da3a177`이 `OBJECT_KINDS`를 **검증기 소유**로 하나만 남기고, 어드민 카탈로그가 **선언이 쓰는
값을 숨기던 것**을 그만두게 했다. `02ff6abd`가 뒤에 남은 읽는 쪽 둘을 **직접 호출해서 확인하며**
새 자리로 옮겼다.

`819f4d13`이 collect 드롭다운을 **라벨은 그리고 id 는 보내게** 했다 — 선언이 어느 모양이든.

## 🔴 그리고 계약 하나가 «세 시간» 살았다

`e4ab4b0e`(19:29). `follow`가 **선언된 술어 열에 대고만** 검사돼서 `in_container` —
다이가 자기 웨이퍼나 dt-job 으로 건너가는 엣지 — 가 **422** 를 냈다. 그것은 선언돼 있다
(`entities.die@1.references[].edge`). 원자가 없을 뿐이고, 그래서 `vocabulary`에 없었다.
`follow`는 여전히 **인자 하나**이고 대조 목록만 넓어졌으며, 거절문의 `declared` 배열도
**같은 집합을 렌더하므로** 함께 넓어졌다. `/declaration`이 그것을 `predicates[]`에 같은 모양으로
싣고 `origin` 필드(`vocabulary` / `reference`)를 붙였다 — **배열 하나라서 클라 갈래가 안 생긴다.**

**그리고 그날 밤 `2cb9a8b9`이 그것을 되돌렸다** — follow 검증기와 `/declaration` 양쪽의
참조 엣지 광고가 **참조 반쪽이 총괄에게 넘어가면서** 함께 나갔다. 즉 이 계약은
**약 세 시간** 존재했다.

## 아키텍처 영향

- **「무엇을 물을 수 있나」에 라우트 하나가 답하고, 그것이 읽는 것은 선언뿐**이다.
  부품은 사본을 안 든다.
- 걷기 상자가 **선언에서 생성된 드롭다운 넷**으로 서고, 씨앗 id 를 자기가 인코딩한다.
- `OBJECT_KINDS`의 소유자가 **검증기 하나**다.

## 그때 남아 있던 것

- `819f4d13`이 **`event`와 `claim`을 collect 드롭다운에 «일부러» 남겼다** — 누르면 422 다.
- 클라의 COLLECT 드롭다운 자체는 이 시점에 안 건드려졌다.
- 🔴 `4eb4dea1`이 자기 문장 하나를 철회했다 — 절단 조건의 `.reason`은 **불필요**했다.
  `if (cut)`이 이미 빈 문자열을 거절한다.
