# 합성의 두 반쪽이 «따로» 실패한다 — 한쪽이 다른 쪽을 조용히 끌 수 없다

> **커밋:** `9365c580` (00:37 · 판정 452 ②) — 구현자. 보고 `b33e8be2`
> **일자:** 2026-09-17
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **앵커는 HEAD blob 에서 다시 쟀다**

## 배경 — 전수 조사가 «폭발 반경»을 찾았다

판정 449 가 「능력을 선언할 수 있는 모든 길을 전수로 적으라」고 요구했고, 그 조사가
`chain/builtins.py` 의 `synthesize_chain_rules` 를 열게 만들었다.

```
그 함수가 «한 표현식»으로 두 반쪽을 지었다:
    rules = enrichment.config.load_enrichment_chain_rules(...)
    rules.extend(virtual_join.config.synthesized_join_chain_rules(...))
=> 가상 조인 쪽에서 «무엇이든 던지면» 인리치 쪽을 «같이» 데려간다
워커의 except 는 한 줄을 찍는다 — 「인리치와 가상 조인 파일에서 합성 실패」
   «어느 쪽»인지도, «무엇이 멈췄는지»도 말하지 않는다
그리고 체인은 «계속 돈다» — 합성 규칙이 «하나도» 없는 채로, dedup 과 자동 확정 포함
```

## 🔴 그 실패는 «가설이 아니다» — 4단계가 정확히 그것이다

`virtual_join` 패키지를 지우면 그 import 가 던진다. 이 수리 없이 4단계를 열었다면,
그 실패가 화면에 **「이 박스는 인리치를 하나도 선언하지 않았다」**로 보였을 것이다 —
빈 선언의 모양을 쓴 «조용한 손실». 이 밤이 계속 닫고 있던 바로 그 부류다.

## 무엇을 했나

```python
#: (half, what stops running when that half does)
_SYNTHESIS_HALVES = (
    ("enrichment", "dedup and auto-confirm rules are NOT running"),
    ("virtual join", "materialised join rules are NOT running"),
)
```

반쪽마다 «따로» 감싸고, 자기 이름과 «자기가 데려가는 것»을 말한다 —
「the virtual join half of synthesis failed, so materialised join rules are NOT running」.

🔴 **반쪽↔결과의 짝을 `except` 블록 «둘»이 아니라 «표»로 둔 것이 요점이다.**
두 반쪽이 «두 목소리»로 보고되는 것이 곧 「무엇이 안 돈다」가 「선언된 게 없다」로
변하는 길이다 — 상설 「문 가르기 금지」의 «로그도 문이다» 줄 그대로.

```
failures     rejections 가 이 저장소의 다른 곳에서 하는 방식대로 모은다. «선택»이다 —
             config_resolve_report 는 아무것도 안 넘기고, 실패한 반쪽이 거기서 던져서도 안 된다
인리치 반쪽    «바이트까지 그대로»이고 여전히 «먼저» 돈다
워커의 catch  진짜로 두 반쪽 «밖»의 것에만 남았고, 이제 그것만 말한다.
             종전 문장은 한 반쪽이 거기 닿기 «전»에 실패하는 순간 거짓이 됐을 것이다
```

## 게이트 — «양방향»이라는 것이 이 라운드의 배움이다

```
새 게이트 넷, «양쪽 방향» 다
  조인 반쪽만 시험하면 「인리치가 실패한다」가 «덮인 것처럼» 읽힌다
  그리고 쌍을 감싼 try «하나»는 바깥에서 «똑같아 보인다» —
  시험 안 한 반쪽이 던지는 그 순간까지
변이   단일 try 로 되돌리기 -> 인리치 방향이 잡는다
      「무엇이 멈췄나」를 안 말하기 -> 잡힌다
이 파일 23 passed · 영향 시험 파일 130 에서 2,054 passed / 0 failed
```

## ⚰️ 같은 조사가 찾은, 같은 파일의 «박스 수» 주석

`virtual_join/config.py` 의 `synthesized_join_chain_rules` 주석이
「this box's two production rules」로 «이 박스의 수»를 적고 있었다. `chain/graph.py` 에서
같은 밤에 고친 것(`8bf1d549`)과 **같은 부류**다 — gitignore 된 파일을 센 수가
docstring 에 박히면 다른 설치에 대해 아무 말도 하지 않는다.

## 그때 남아 있던 것

- **4단계는 열리지 않았다.** 이 커밋은 4단계가 «터뜨릴» 것을 미리 갈라 놓은 것이지,
  패키지를 지운 것이 아니다.
- 레거시 파일의 입구는 «둘»이라는 것이 같은 조사에서 나왔다 —
  `materialize: false`(읽기 시점, 은퇴 대상)와 `materialize: true`(«쓰기» 체인 규칙,
  은퇴 대상 «아님»). 후자가 이 함수를 지난다.
- ⚠️ **이 항목을 쓰는 시점에 `builtins.py` 는 «작업 트리에서 수정 중»이었다**
  (판정 454 — 「452 의 수리가 침묵을 로그에서 화면으로 옮겼다」). 위 앵커와 인용은 전부
  HEAD blob 기준이다.
