# 스코어러가 여덟 맵의 순위를 매겨 놓고 화면에는 그중 어느 것도 그릴 방법을 주지 않았다

**날짜:** 2026-08-08 22:08 · **커밋:** `1ebcc88` · **레인:** 정렬기 + map2
**측정 상자:** 이 워크스테이션의 라이브 페이로드. **운영이 아니다.**

---

## 관측

라이브 유닛(`dt_frame_confrimation` · `DT-EQP-02_20260512T0000_T09` · 기준
`valid_die_ref/QA_MAP2`)의 페이로드를 그대로 읽었다.

| 관측 | 값 |
|---|---|
| 소스 셀 | **72건** |
| `dt_index` 컬럼 해석 | **성공**, 그러나 값이 전부 NULL |
| `index_axis` | `absent` |
| `placement` (판정) | `shift_search` |
| 후보 8개의 `value_agreement` | **51~72** |
| 후보 8개의 `placement` | **여덟 전부 `null`** |

**채점은 멀쩡히 돌았다.** 여덟 후보 전부가 시프트를 가졌고 값 일치도까지 가졌다. 그런데
조작자 화면에는 **기준 바닥만 뜨고 그 위에 아무것도 없었다.**

## 왜

클라이언트는 소스 맵을 `placement` **하나만** 보고 그린다. **대체 갈래는 설계상 없다.**

```js
export function seatingFor(payload, candidateId, cells) {
  const placement = placementFor(payload, candidateId);
  if (!placement) return { seating: null, reason: '배치 없음' };
  return { seating: placeCells(cells || [], placement), reason: null };
}
```

서버 쪽에서 `placement`가 **앵커 셀에 걸려** 있었다. 순번이 어디에도 없으면 앵커 셀이
없고, 그러면 배치도 `null`이다.

```python
            "placement": (None if c.get("_linear") is None or anchor_cell is None
                          or c.get("_anchor_placed") is None else {
```

🔴 **게이트가 틀린 질문을 하고 있었다.** 그리는 데 필요한 것은 **선형부 하나와 기준점
하나**이지 앵커가 아니다. 앵커는 **평행이동을 결정하는** 물건이고, 그리기는 그 결정을
필요로 하지 않는다.

## 수리가 기대는 항등식

검색 갈래에서도 `placed = tf(cell)`이고 `tf`는 **아핀**이다. 그러므로

```
tf(cell) = tf(pivot) + L·(cell − pivot)
```

가 **어떤 pivot에 대해서도** 성립한다 — 기존 오라클 `test_the_linear_part_matches_the_transform`이
여덟 프레임 전부에서 이미 단언하고 있는 항등식이다. **그래서 pivot은 맵을 움직일 수 없고,
결정론적이기만 하면 된다.**

두 pivot 규칙은 **하는 일이 다르다.** `anchor_cell_of`(최소 순번)는 **평행이동을 결정**하고,
새로 생긴 `search_pivot_of`(저장된 최소 `(y, x)`)는 **아무것도 주장하지 않는다.**

```python
    contributing = [mi for mi, sm in enumerate(usable or ()) if sm.get("_use")]
    if len(contributing) != 1:
        return None
```

기여하는 맵이 둘이면 **거절한다.**

그리는 형태는 **한 곳에서만 철자한다.**

```python
def _placement_payload(linear, anchor_src, anchor_placed, dx, dy):
    """The drawable form, spelled ONCE: `placed = anchor_ref + linear*(cell - anchor_src)`.
    ...
    """
    if linear is None or anchor_src is None or anchor_placed is None:
        return None
    return {"linear": [list(linear[0]), list(linear[1])],
            "anchor_src": list(anchor_src),
            "anchor_ref": [anchor_placed[0] + (dx or 0), anchor_placed[1] + (dy or 0)]}
```

`anchor_placed`는 **시프트 적용 전** 채점 루프가 pivot을 놓은 자리이고, **시프트는 여기서
정확히 한 번** 더해진다.

🔴 **검색 값은 앵커 경로의 슬롯을 공유하지 않고 자기 이름을 갖는다**(`_search_linear`,
`_search_placed`). 커밋 본문의 문장이 그 이유다 — **「공유는 『안 바뀌었다』가 조용히
거짓이 되는 방식이다.」** 순번 경로는 여덟 프레임 전부에 대해 **바이트 동일**로 고정됐다.

## 픽스처가 함정이었다

**오프셋 `(0,0)`에서는 검색이 포화해 여덟 후보가 전부 시프트 `{0,0}`에 앉는다.** 그러면
**시프트 항을 통째로 빠뜨린 구현도 모든 수를 그대로 재현한다.** 그래서 테스트는 두 번째
픽스처를 `(5,-4)`만큼 옮겨서 들고 있고, 거기서 시프트를 빠뜨리면 **16조합 중 8이** 빨개진다.
pivot을 한 칸 옮기면 **16조합 중 14**가 빨개진다.

이 항목에서 다시 쓸 수 있는 부분이 이것이다 — **가장 자연스러워 보이는 픽스처가 정확히
아무것도 구분하지 못하는 자리에 앉아 있었다.**

## 검증

- 새 테스트 3개(`server/tests/test_map_alignment.py` +140):
  `test_the_screen_can_draw_when_no_die_carries_an_index`(8프레임 × 오프셋 2 = **16조합**),
  `test_the_index_path_still_pivots_on_the_minimum_index_die`(3), `test_the_search_pivot_refuses_two_maps`.
- 테스트는 클라의 식을 **import하지 않고 옮겨 적는다**(`_seats_from_placement`) — 화면이
  실제로 하는 역산을 서버 쪽에서 재현하기 위해서다.
- **커밋 본문은 스위트 수치를 제시하지 않는다.** 순번 경로 무변경은 스위트가 아니라
  **여덟 프레임 바이트 비교**로 확인됐다(`elapsed_ms`만 다름).
- `docs/spec/MAP_ALIGNMENT_SPEC.md`에 §9.9가 추가됐다(+39, 삭제 0).

## 그때 남아 있던 것

- 🔴 **`ruling["anchor"]`는 검색 갈래에서 여전히 `null`이고, 이 커밋은 그것을 의도적으로
  지켰다.** 근거는 `frame_confirmation._placement_of`가 그 쌍을 들어 `start_from_placement`에
  넘기는데 그 유도가 **평행이동의 나머지가 앵커 쌍 안에 있다**고 전제하기 때문 — 검색된
  배치를 거기 실으면 실측된 **240/240 변위**를 다시 산다는 것이었다.

  **78분 뒤 `1fbd4b1`이 그 게이트를 철회했다.** 반대 논거는 `anchor_ref`가 이미
  `anchor_placed + (dx, dy)`라 **시프트가 그 쌍 안에 들어 있다**는 것이었고, 240/240은
  **반대 방향의 실수**(앵커 배치에 시프트 전용 유도)였다는 것이었다. 즉 **이 커밋이 명시적
  근거를 대고 지켜 낸 결정이 같은 밤에 뒤집혔다.**
- 「값 축」은 이 커밋이 만든 것이 아니다 — `ruling["value_axis"]`(`ranking`/`reported`/
  `absent`)는 이미 있었다. 이 커밋이 추가한 심볼은 `search_pivot_of`와 `_placement_payload`
  둘이다.
- `client2/src/map2/main.js`의 `anchor_ref = reference_top_left + (dx, dy)` 주석은 **철 지난
  문장인 채로 남았다**(동작은 옳다). 스펙 §9.9가 그것을 적어 두고 넘어갔다.
