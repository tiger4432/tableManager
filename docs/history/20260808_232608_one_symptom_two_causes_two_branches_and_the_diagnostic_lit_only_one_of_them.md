# 증상은 하나였는데 원인이 둘이었고 갈래도 둘이었다 — 그리고 진단은 그중 한 갈래만 비췄다

**날짜:** 2026-08-08 23:26~23:40 · **커밋:** `1fbd4b1` · `014b5d3` · `cf85fbb` · `3dc79e6` ·
`8d37cd1` (문서 맥락 `6541e35` · `122f529`) · **레인:** 정렬기
**측정 상자:** 이 워크스테이션의 라이브 표를 읽었다. **운영이 아니다.**

---

## 배경

30분 전 `db1ee42`가 후보 공간을 **4회전 × {tl, tr}**로 바꿨다. 그런데 제품 소유자가 보고
있던 화면에서는 **`tl`과 `tr`이 같은 맵을 그렸다.** 보행 순서만 바뀌고 맵이 앉는 자리는
꿈쩍하지 않았다.

이 30분은 그 하나의 증상을 쫓은 기록이다. **증상은 하나였지만 원인은 둘이었고, 둘은 서로
배타적인 두 갈래에 있었다.**

갈래를 가르는 것은 `score_candidates`의 이 분기다 — 이 라운드에서 **한 줄도 바뀌지 않았다.**

```python
        if anchor_dxy is not None:
            ...
            bx, by = anchor_dxy[c["frame"]]
            ...
            dx, dy = bx, by
        else:
            dx, dy, _hit = _solve_shift(c["keys"], ref_sorted, shift_window, base=_base)
```

`dt_index`에 값이 있으면 **`if` 갈래(앵커)**, 없으면 **`else` 갈래(시프트 검색)**를 탄다.

## 1. `1fbd4b1` — 확정 원점이 상자를 모르는 식으로 풀리고 있었다

규칙은 `SRC_START = REF_START - SHIFT`이고 **`REF_START`는 상자 원점**이다. 그런데 검색
갈래의 원점은 `start_for_placement`에서 왔고 그 식은 `start - L⁻¹(shift)`다 — **상자 항이
없다.** 지금 그려지는 자리가 옳다는 전제 위에서 시프트만큼만 고친다. 호출부 주석이 그것을
직접 적고 있었다.

```python
    elif shift:
        # 🔴 [2026-08-08] **이 갈래는 상자를 모른다.** `start_for_placement`는
        #    `start - L⁻¹(shift)`이고 그 식에 상자 항이 없다 - 지금 그려지는 자리가 옳다는
        #    전제 위에서 시프트만큼만 고친다.
```

수리는 **상자 항을 손으로 더한 것이 아니다.** `ruling.anchor`를 순번 앵커에 걸어 두던
게이트를 **철회**했다.

```python
-    ruling["anchor"] = ((_win_row or {}).get("placement")
-                        if anchor_cell is not None else None)
+    ruling["anchor"] = (_win_row or {}).get("placement")
```

앵커가 null이면 `_placement_of`가 `anchor_src`/`anchor_ref` 없는 dict를 돌려주고, 그래서
`confirmed_meta_for`가 위의 상자 없는 `elif shift:`로 굴러떨어진다. 게이트를 걷으니 쌍이
그대로 통과해 상자를 아는 `start_from_placement(..., source_box=src_box)`가 발화한다.

**게이트를 세웠던 논거가 뒤집혀 있었다.** 「검색된 배치는 쓸 수 있는 쌍을 나르지 않는다 —
시프트가 평행이동 전체를 진다」였는데, `anchor_ref`가 이미 `anchor_placed + (dx, dy)`라
**시프트는 그 쌍 안에 들어 있다.** 게이트를 만들게 한 240/240 변위는 반대 방향의 실수였다 —
**앵커 배치에 시프트 전용 유도를 먹인 것.**

- 화면의 **세 열**은 `− box.minC`가 빠진 것이다. 기준 min `(-3,-3)` 대 선언된 `START`
  `(0,-3)` — x가 3 차이 나고 y는 둘 다 `-3`이라 우연히 일치해서, 변위가 **열 방향에만**
  나타났다.
- 🔴 커밋 본문이 남긴 문장: **「이 파일은 손으로 옮긴 좌표 대수의 값을 네 번 치렀다.」**

## 2. `014b5d3` — 검색 갈래를 고쳤다

`first_die_of`가 새로 생겼고(보행이 1번을 매기는 셀), 검색이 **후보 자기 시작 모서리로 잡은
base 주위**를 훑도록 바뀌었다.

```python
def first_die_of(cells, left_to_right: bool = True):
    if not cells:
        return None
    top = min(int(y) for (x, y) in cells)
    row = [int(x) for (x, y) in cells if int(y) == top]
    return ((min(row) if left_to_right else max(row)), top)
```

```python
-def _solve_shift(placed_keys, ref_sorted, window: int):
+def _solve_shift(placed_keys, ref_sorted, window: int, base=(0, 0)):
```

**이 커밋은 무해한 변경이 아니었다 — 창의 클램프를 풀었다.** 소스 첫 다이 `(6,0)`이 기준의
`(3,6)`에 닿으려면 `(-3,+6)`이 필요한데 창은 ±3이고 솔버는 **0 주위**를 훑고 있었다. 닿을 수
있는 가장 먼 `(1,3)`에 눌러앉았고, 그래서 **여덟 후보가 전부 `at_window_edge`**를 보고했다.
창은 **잔차**를 위한 것이지 평행이동 전체를 위한 것이 아니다.

측정: `rot0_tl`과 `rot0_tr`이 같은 시프트 `(1,3)`, 같은 배치 `anchor_src [6,0] → anchor_ref
[7,3]`.

## 3. `cf85fbb` — 네 숫자를 찍었다, 그런데 검색 갈래에만

「그림 보고 진단하다 여러 번 틀린 뒤」 요청됐다. 후보당 한 줄.

```python
                logger.info(
                    "[Align] %-12s ltr=%-5s | REF top-row-left=%s  REF left-col-top=%s"
                    " | SRC#1 stored=%s placed=%s | base=%s -> shift=(%d,%d) hit=%d",
                    ...)
            except Exception as _e:                     # 진단이 채점을 막지 않는다
```

`try/except`로 감싼 이유가 명시돼 있다 — **진단이 채점을 막을 수 있는 자리를 만들지 않는다.**

## 4. `3dc79e6` — 진짜로 도는 갈래는 앵커 쪽이었다

라이브 표: **여덟 후보 전부가 시프트 `(-13,-11)`.** `(1,3)`이 아니다. **다른 표다.**

`_anchor_shift`가 `t`를 **루프 위에서 한 번** 계산해 여덟에게 그대로 나눠 주고 있었다.
표현식에 루프 변수 `c`가 아예 없었으므로 **모서리가 후보에 따라 달라질 방법이 구조적으로
없었다.**

```python
-    t = (int(reference_top_left[0]) - int(anchor_cell[0]),
-         int(reference_top_left[1]) - int(anchor_cell[1]))
+    def _t_for(frame):
+        corner = (reference_top_left if left_to_right_of(frame)
+                  else (reference_top_right or reference_top_left))
+        return (int(corner[0]) - int(anchor_cell[0]),
+                int(corner[1]) - int(anchor_cell[1]))
```

우상단 모서리는 **손으로 「윗줄의 가장 오른쪽」이라고 다시 철자하지 않고** 같은 보행을
반대 방향으로 돌려서 얻는다 — 모서리 규칙이 `serpentine_index` 안에 하나로만 남게.

```python
        reference_top_right = _back.get(
            serpentine_index(_canon_ref, top_is_min_y=True, left_to_right=False).get(1))
```

**소스 앵커는 움직이지 않는다.** 어느 다이가 1번인지는 설비의 번호 매김이고 **데이터의
사실**이다. 후보가 고르는 것은 **그 다이가 기준의 어느 모서리에 앉느냐**뿐이다.

## 🔴 「같은 결함을 두 번 고쳤다」가 아니다 — 이 항목의 본론

두 커밋의 hunk는 **한 줄도 겹치지 않는다.** `3dc79e6`이 지운 `t = ...`/`out[c["frame"]] = t`는
`014b5d3`보다 **먼저부터 있던 줄**이고, `014b5d3`의 트리에 그대로 보인다. `3dc79e6`은
`first_die_of`를 부르지 않고 `_solve_shift`를 건드리지 않으며 `else:` 블록에 손대지 않는다.

| | `014b5d3` | `3dc79e6` |
|---|---|---|
| 고친 갈래 | `else:` (시프트 검색) | `if:` (앵커) |
| 측정된 시프트 | `tl`/`tr` 둘 다 `(1,3)` | **여덟 전부** `(-13,-11)` |
| 라이브 유닛이 타는 갈래인가 | **아니다** (`dt_index`에 값이 있었다) | **그렇다** |

`anchor_dxy is not None`이면 `dx, dy = bx, by`가 딕셔너리에서 바로 오고 **`else:` 블록은
실행되지 않는다.** 그러니 `014b5d3`이 고친 코드는 신고자의 유닛에서 **처음부터 돌지 않았다.**

**그래서 이것은 「아무것도 안 한 수리」가 아니라 「안 도는 갈래를 고친 수리」다.** 그 커밋은
실제로 검색 갈래의 창을 언클램프했다 — 순번이 없는 유닛에게는 진짜 변경이다. 다만 **보고자가
보고 있던 유닛에게는 보이지 않았다.**

진짜 공정 결함은 중복 수리가 아니라 **그 사이 30분 동안 라이브 유닛이 어느 갈래에 있는지
말해 주는 것이 아무것도 없었다는 것**이다. `cf85fbb`가 검색 갈래에만 불을 켰고, `8d37cd1`의
본문이 그것을 그대로 적는다 — 진단이 **「지금 라이브 유닛이 타지 않는 갈래」**에만 발화해서
**정작 문제의 표에는 설명하는 줄이 한 줄도 없었다.**

## 5. `8d37cd1` — 앵커 갈래에도 불을 켰다

요청당 한 줄(기준의 모서리들), 후보당 한 줄(어느 소스 다이가 어느 기준 모서리에 앉았고 `t`가
무엇이 나왔는지).

```python
            logger.info("[Align] REF n=%d box=(%d,%d) | stored top-row-left=%s"
                        " top-row-right=%s | walk#1 tl=%s tr=%s | canon_linear=%s", ...)
```

`box=`(생 min-x/min-y 모서리)를 `stored top-row-left=` **바로 옆에** 찍는 것이 의도다 —
**빈 모서리 함정이 눈에 보이도록.** CORE_DT 실측: **261셀**, 상자 모서리 `(-3,-3)`에는
**다이가 없고**, 저장된 윗줄 왼쪽은 `(5,-3)`(제품 소유자가 준 값), 오른쪽은 `(7,-3)`.
윗줄은 x 5..7의 **세 칸**이다. **상자 모서리를 앵커로 쓴 구현은 여덟 열 어긋난다.**

`6541e35`가 그 이유를 적어 뒀다: `boundingBoxOf`가 웨이퍼 원을 훑으므로 `minC`는 **가장 넓은
가운데 줄**에서, `minR`은 **가장 좁은 윗줄**에서 온다 — **그 둘의 모서리에는 다이가 없다.**

## 검증

- **다섯 커밋 어느 것도 본문에 스위트 수치를 제시하지 않는다.** 이 라운드의 근거는 전부
  **라이브 표 실측**이다(위의 `(1,3)`·`(-13,-11)`·261셀).
- 이 라운드는 **테스트를 추가하지 않았다.** 다섯 커밋 합계가 `server/map_alignment.py`
  +130/-22, `server/frame_confirmation.py` 무변경이며 `server/tests/` 아래는 손대지 않았다.

## 그때 남아 있던 것

- **회귀 테스트가 없다.** 「여덟 후보가 같은 시프트를 낸다」는 이 라운드에서 **사람이 로그를
  읽어서** 잡았고, 그것을 다시 잡아 줄 테스트는 이 시점에 없었다.
- **`8d37cd1`의 후보별 로그 줄만 `try/except`로 감싸여 있지 않다.** 이 아크의 다른 진단은
  전부 감싸여 있다.
- 같은 줄이 `_t_for`가 이미 소유한 **모서리 선택 식을 다시 철자한다**(`left_to_right_of`를
  두 번 더 부른다). 두 철자가 갈라지는 날 로그는 **코드가 쓰지 않은 모서리를 확신에 차서
  보고한다** — 이 파일 자기 주석이 경고하는 바로 그 형태다.
- `122f529`는 **코드 변경이 아니라 지침**으로 남았다: 유효 다이 맵 자체에 회전이 선언되면
  앵커 모서리가 움직인다.
