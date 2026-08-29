# 같은 부품 «둘»을 놓을 수 있는 골격과, 부품 «밖»에 사는 마킹 저장소

> **커밋:** `d77499a1` (20:02) · `33ff44fc` (20:55) · `4319f380` (21:13) · `38e50890` (21:23)
> · `da23c4be` (21:28) · `80dbe80c` (22:19) · `a38297e2` (22:38) · `74cd65c1` (22:46)
> · `409ddaf0` (22:50) · `0f42743d` (22:57) · `fb34790a` (23:07)
> | **일자:** 2026-08-23 저녁
> **레인:** 클라(R&D 보드)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 기존 맵 패널은 «한 페이지에 둘»을 못 놓는다

`ledger_map_panel.js`가 `deps`·`mountEl`·`session`을 **모듈 수준**에 들고 있어서 둘째가 첫째를
덮었다. 소유자 상설이 「모든 UI 는 조립식」이므로 골격부터 다시 세웠다 — `d77499a1`.
**같은 종류 둘을 담을 수 있는 골격 하나와 그 위에 선 맵 하나.**

## 마킹은 부모가 내려 주지 않는다 — «밖»에 살고 부품이 구독한다

`client2/src/rnd_board/marking_store.js`가 `name -> Map(nodeId -> sign)`을 들고 있다.
**이름 붙은 마킹이 여럿**이고 부호는 셋이다:

```js
export const SIGN = Object.freeze({ ABSENT: 0, CASE: 1, CONTROL: -1 });
```

`normaliseSign`은 그 밖의 값에 **throw** 한다. 부품은 `reads`/`writes`로 **자기가 읽을 이름과
쓸 이름을 선언**하고, **어느 부품도 남의 이름을 모른다.**

`a38297e2`가 파생 이름을 **레이아웃 데이터**로 선언했다 —
`intersections: [{ sources: ['marking:1','marking:2'], target: 'marking:3' }]`.
교집합 규칙은 **id 만이 아니라 부호까지 같아야 동의**로 친다:

```js
// client2/src/rnd_board/marking_intersection.js
if (otherSign !== sign) { agreed = false; contradicted = true; break; }
```

모순은 `conflicts()`로 셀 수 있게 남는다. **부품 파일은 한 개도 안 바뀌었다** — diff 가
`main.js`, 새 파일, 하니스 둘, 보고서만 건드린다.

## 선택 모델 전체가 다섯 줄이다

```js
// client2/src/rnd_board/panel.js  (74cd65c1)
mark(nodeId, sign, mode = 'replace') {
  if (!this.writes || !this.markings) return SIGN.ABSENT;
  if (mode === 'add') return this.markings.toggle(this.writes, nodeId, sign);
  this.markings.clear(this.writes);
  return this.markings.set(this.writes, nodeId, sign);
}
```

클릭은 **교체**, ctrl 은 **더하기**. 그리고 행이 커서 밑에서 움직이지 않는다 — 스크롤 200이
200으로, 클릭한 행의 y 가 411로 유지되는 것을 재서 확인했다.

## 소유자의 스팟파이어가 기준이 됐다 — 마킹은 «나머지를 흐려서» 그린다

`409ddaf0`. 마킹된 것을 칠하는 게 아니라 **나머지 전부를 흐린다.** 그리고 맵 배지가
**자기가 그린 것을 세게** 했다.

🔴 **같은 결함이 한 층 아래에 그대로 있었다.** 배지는 고쳤는데 **감쇠(attenuation)는 여전히
마킹 «이름 전체»의 개수를 봤다** — `attenuating = this.markCount() > 0`. 그래서 손도 안 댄
웨이퍼 위의 맵 B 가 1을 읽었다. 이 자리는 **다음 날 `1aa326a1`에서야** 닫혔다.

## 🔴 채점기가 «던진 변이»를 «잡힌 것»으로 찍고 있었다

`33ff44fc`은 「6/6 잡음」을 보고했다. `da23c4be`이 나중에 보인 것: **채점 자체가 던진 변이를
`caught`로 세고 있었다.** 즉 `33ff44fc`의 6/6은 **잡힌 변이와 무해한 변이를 구분 못 하는
러너 아래에서 측정된 수**다.

같은 커밋이 자기 본문에서 「수용 조건 다섯」이라 쓰고 **여섯(A–F)을 나열**한다.

## 파생을 «증거 홉»에서 만들어야 했다

`4319f380`이 실측했다: `/api/ledger/subgraph` 행에 `kind`·`sublabel`·`detail`·`color_role`이
**없다.** 그래서 화면이 존재하는 이유인 「실측 대 이름뿐」 구분을 **증거 홉에서 도출**해야 했다.
측정: 후보 25 · 순위 1–9 · **실측 4 / 이름뿐 21** · 동률 22 · top_set 1 · 홉 3–6.
지시서는 3/22라고 적었고, **작성자가 맞추는 대신 어긋남을 신고했다.**

## 아키텍처 영향

- 부품이 `Panel` 클래스이고 **자기 mount 와 deps 를 생성자로 받는다.** 모듈 수준 상태가 없다.
- 마킹이 **부품 밖의 저장소 하나**에 살고 **이름 붙은 여럿**이다. 부품은 읽을 이름·쓸 이름을
  선언한다. 교집합은 **레이아웃 선언**이지 코드가 아니다.
- 부호가 셋(`ABSENT`·`CASE`·`CONTROL`)이고 교집합은 **부호까지 같아야** 동의한다.

## 그때 남아 있던 것

- 부품 넷이 `PARTS`에 등록됐지만 **`BOARD`에 앉지 않았다** — 앉히려면 `bindLoaders`가 필요하고
  그건 골격 소관으로 판정됐다.
- **감쇠가 아직 마킹 이름 전체를 센다.** 배지만 고쳐졌다.
- `marking:3`을 **읽는 부품이 없다**(`a38297e2` 자기 기록).
- 관련 없는 하니스 셋이 빨갛고, HEAD 에서도 같다.
