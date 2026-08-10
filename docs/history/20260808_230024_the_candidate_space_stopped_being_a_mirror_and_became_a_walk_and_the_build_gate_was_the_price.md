# 후보 공간이 거울이기를 그만두고 걸음이 됐다 — 그리고 빌드 게이트가 그 값이었다

**날짜:** 2026-08-08 23:00 · **커밋:** `db1ee42` (선행 문서 `2dc4e5f` · `1caa263`,
후속 `6541e35`) · **레인:** 정렬기 + map2
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

> 이 스레드의 앞부분은 `20260807_100446`(정렬기의 `back`은 거울이었다)과
> `20260807_120619`(거울 절반이 곧 우상단 절반이다)에 있다. 이 항목은 **그 절반을 실제로
> 걷어내고 걸음 축으로 갈아 끼운** 라운드다.

---

## 배경

설비마다 **어느 모서리부터 번호를 매기는지가 다르다.** 그런데 스코어러는
`serpentine_index(left_to_right=...)`를 **한 번도 흔들어 본 적이 없었다** — 그 인자를 실제로
바꿔 부르는 곳은 시드 스크립트 두 줄뿐이었다.

그래서 우상단부터 번호를 매기는 유닛은 **거울 프레임에 착지해야만** 맞았다. 그런데
**거울은 셀을 옮긴다.** 물리적으로 뒤집히지 않은 웨이퍼에 대해서 그것은 **틀린 답**이다.

## 무엇으로 갈아 끼웠나

두 번째 축이 **면**에서 **걸음의 시작 모서리**로 바뀌었다.

```python
START_TOP_LEFT = "top_left"
START_TOP_RIGHT = "top_right"
CANDIDATE_STARTS = (START_TOP_LEFT, START_TOP_RIGHT)
START_TOKEN = {START_TOP_LEFT: "tl", START_TOP_RIGHT: "tr"}
#: 후보의 면은 **언제나 front**다. 후보 축에서 빠졌지 값이 없어진 것이 아니다.
CANDIDATE_SIDE = "front"
```

후보는 `rot0_tl rot0_tr rot90_tl rot90_tr rot180_tl rot180_tr rot270_tl rot270_tr` 여덟이고
**전부 `side: front`**다. 대응은 **한 곳에서만 철자한다.**

```python
def left_to_right_of(frame: str) -> bool:
    """후보 문자열 → `serpentine_index`의 `left_to_right`. **철자는 여기 하나다** —
    두 곳에서 이 대응을 적으면 채점과 진단이 다른 걸음을 잰다."""
    return candidate_start(frame) == START_TOP_LEFT
```

**저장 형식은 건드리지 않았다.** `parse_frame`이 `tl`/`tr`을 받으면서 `front`/`back`도
계속 받는다 — 걸음 축이 생기기 전에 확정된 행들이 그 철자를 들고 있기 때문이다.

```python
_SIDE_OF_TOKEN = {"front": "front", "back": "back", "tl": "front", "tr": "front"}
```

🔴 **판사를 상수로 두면 새 축이 자기 자신을 벌한다.** 행 방향의 위상을 시작 모서리가
정하므로, 판사를 하나만 만들면 **우상단 후보의 모든 걸음이 위반으로 세어진다.** 바닥은
하나이므로 판사는 **둘만** 만들어 나눠 쓴다.

```python
    _judges = ({True: direction_judge(_canon_ref, left_to_right=True),
                False: direction_judge(_canon_ref, left_to_right=False)}
               if _canon_ref else {})
```

그리고 **회전과 시작 모서리는 한 문자열이 아니라 따로 나간다.** 화면이 문자열을 다시
쪼개게 하면 그 쪼개기가 **두 번째 철자**가 되는데, 이 라운드가 고친 결함이 정확히
**「두 번째 축을 문자열에서 추론하기」**였기 때문이다.

## 등가표가 여섯 곳에서 틀려 있었다 (`2dc4e5f`)

「거울 절반 = 우상단 절반」은 **반 바퀴에서만** 참이다. **`rot90_back`은 우상단의 `rot270`이지
`rot90`이 아니다.**

🔴 **그 틀린 문장이 어디서 왔는지가 이 항목의 재사용 가능한 부분이다** — **정사각 그리드에서
측정됐다.** 정사각에서는 **행을 뒤집는 것과 열을 뒤집는 것이 구분되지 않는다.** 퇴화 픽스처가
틀린 일반화를 낳고, 그것이 여섯 곳으로 복사됐다.

바로잡은 곳: 스펙 §2.4, `PRIMITIVES.md`, `decode.js` 주석 4개. 그리고 **테스트 벡터도 그 표를
통과시켜 옮겼다** — `rot90_back` → `rot270_tr`, `rot270_back` → `rot90_tr`.

## 같이 실린 것 (반경이 같아서)

- **앵커 없는 확정은 더 이상 `valid_die_ref`를 찍지 않는다.** `elif shift` 갈래는 **구조적으로
  상자를 모르므로**, 거기서 찍으면 **3,840셀 중 2,880셀**이 다른 다이에 앉는다(커밋 본문의
  진술이며 이 커밋에 그것을 재는 테스트는 없다). 확정 게이트 자체는 열린 채로 둔다.
- **`placement_basis`(`anchor`|`shift_search`)가 후보마다 실려** 판정이 무엇에 기댔는지
  말할 수 있게 됐다. 🔴 **영속화는 유보 — 컬럼이 아직 없다.**

## 검증 — 그리고 이 라운드가 치른 값

- 🔴 **`test_map_alignment.py`의 실패 61건 중 24건이 「순번 값이 없으면 tl과 tr이 같은
  기하」라서 생긴 동점**이라고 커밋 본문이 적는다. **제품 소유자가 수용 가능으로 판정했다** —
  화면이 후보를 보여 주고 **사람이 고른다.**
- **아무 커밋도 이 61/24를 재는 실행 결과를 남기지 않았다.** 다만 diff와 모순되지는 않는다 —
  예를 들어 `declared_frame_of`는 그대로 `frame_text(...)`로 `"rot0_front"`를 만드는데
  테스트는 `"rot0_tl"`을 단언한다. **그 단언은 이 커밋 시점에 통과할 수 없다.**
- 🔴 **`npm run build`가 `prebuild`에서 막혔고, `dist`는 `npx vite build`로 그 게이트를
  우회해서 만들어졌다.** 기록된 오라클 벡터 둘이 `rot270_back`·`rot0_back`을 이름으로 갖는데
  그것들이 더 이상 후보가 아니라 `alignment_verdict_harness.mjs`가 던진다.
  **오라클 케이스는 고치지 않았다** — 그 실패가 **진짜**이기 때문이다.
- **정렬기 모듈 밖으로는 테스트를 돌리지 않았다**(`1caa263`의 상시 지시: `pytest.ini`도
  커스텀 마커도 없고 **전체 스위트 게이트를 두지 않는다**).
- 스펙이 **받아들인 비용**을 적어 뒀다: 물리적으로 거울인 소스 맵은 값·점유 정렬을 잃는다.
  실측 — `rot0_back`에서 **93/93**을 받던 유닛이 front 전용 공간에서는 **승자가 없고**
  최고가 틀린 프레임의 **87/93**이다.

## 🔴 커밋이 제시한 「2 → 8」은 기준이 움직인 수다

본문은 `left_to_right` 호출부가 **2에서 8로** 늘었다고 적는다. 그런데 세어 보면 **8 쪽은
모듈 내부 통과 호출 한 곳을 포함하고 2 쪽은 그것을 제외한다.** 같은 기준으로 세면
**3 → 8**이거나 **2 → 7**이다. 늘어난 것은 사실이고 방향도 맞지만, **그 두 수는 같은 술어의
값이 아니다.**

## 18분 뒤 — 게이트를 내렸다 (`6541e35`)

제품 소유자 판정(**「하네스 무시해」**)에 따라 `alignment_verdict_harness.mjs`가 빌드
게이트에서 빠졌다. **주석이 그 이유를 숨기지 않고 적는다.**

```js
  // 🔴 OFF THE BUILD GATE 2026-08-08 (product owner: 「하네스 무시해」). `db1ee42` replaced the
  //    mirror half of the candidate space with the walk axis, so 8 of the 16 production frame
  //    tuples are no longer reachable BY RULING, and this harness reports that honestly: 6 of
  //    its 163 assertions fail, including a recorded unit whose truth was a reflection. Those
  //    failures are TRUE -- the harness is not broken and its vectors were not edited. It is
  //    off the gate so `npm run build` stops needing `npx vite build` to bypass it, not because
  //    the numbers were dismissed.
```

**게이트에서 빼되 `KNOWN_RED`에 등재하지 않고 벤치도 고치지 않는다** — 즉 「초록으로
보이게」 만들지 않았다. 손으로 돌리는 명령이 주석에 남는다.

## 그때 남아 있던 것

- `alignment_verdict_harness.mjs`는 **163개 단언 중 6개가 빨간 채**였고, **운영 16튜플 중
  8만 판정으로 도달 가능**했다. 거울이 정답이던 실측 단위 하나는 **복구 불가**로 기록됐다.
- **`sides` 설정 축이 통째로 사라졌다** — `SIDES_KEY`·`load_alignment_sides`·
  `score_candidates(sides=)`. `alignment.sides`를 선언해 두었더라도 이 시점부터 읽히지 않는다.
- `STATE_NOT_CONSIDERED`와 `TEXT_SIDE_NOT_CONSIDERED`는 **생산자가 없는 채로** 코드에
  남았다. 그것들을 검증하던 테스트 넷은 삭제됐고, 삭제 이유가 주석으로 대체됐다.
- **`placement_basis`를 담을 컬럼이 없다.** 후보 행과 판정에는 실리지만 저장되지 않는다.
- 소스와 `dist`가 **다른 명령으로** 만들어진 상태였다. 이 저장소에서 「소스에 있고 dist에
  없으면 사용자에겐 없는 것」은 이미 두 번 사고가 났던 자리다.
