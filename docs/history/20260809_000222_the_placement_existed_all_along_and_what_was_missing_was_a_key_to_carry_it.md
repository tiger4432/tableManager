# 이기지 않은 후보를 확정하면 각도만 바뀌었다 — 배치는 내내 있었고 없던 것은 그것을 나를 키였다

**날짜:** 2026-08-09 00:02 · **커밋:** `97b29da` · **레인:** 정렬기 + 확정
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 증상

한 맵을 세 번 확정했더니 회전이 **0 · 90 · 180**으로 돌아왔는데 `grid_start`는 **셋 다
`(-6,-3)`**이었다. 에디터는 **같은 맵을 각도만 돌려서** 다시 그렸고, 그 그림은 정렬기가
화면에 보여 준 것과 무관했다.

## 왜 그랬나

`confirmed_meta_for`에서 **프레임은 무조건 쓰이고 원점은 분기 안에 있다.**

```python
    base["rotation"], base["side"] = rot, side
```

```python
    if placement and placement.get("anchor_src") and placement.get("anchor_ref"):
        ...
    elif shift:
        ...
```

`_placement_of`가 **이긴 프레임에 서지 않은 기여자에 대해 `None`**을 돌려주고 있었다.
`None`은 위 `if`도 `elif`도 만족시키지 않는다. 그래서 **각도는 바뀌고 원점은 그대로**였다.

```python
    if (contributor or {}).get("applied_frame") != r.get("winner"):
        return None
```

🔴 **그 자리의 주석이 그것을 정당화하고 있었고, 그 주석이 거짓이었다.** 주석은 「그 프레임에서
채점된 배치는 존재하지 않는다 — null이지 0이 아니다」라고 적고 있었는데, **스코어러는 여덟
후보 전부에 대해 시프트와 배치를 푼다.** 없던 것은 **배치가 아니라 그것을 여기까지 나를
키**였다 — `ruling`은 줄곧 **승자의 것만** 쥐고 있었다.

이것이 이 항목의 재사용 가능한 부분이다. **「없다」고 적힌 주석이 실은 「전달되지 않는다」를
뜻하고 있었고**, 그 두 문장은 서로 다른 수리를 가리킨다.

## 수리

생산자 쪽에 키 하나가 생겼다.

```python
    ruling["by_frame"] = {
        r["frame"]: {"shift": r.get("shift"), "anchor": r.get("placement"),
                     "placement_basis": r.get("placement_basis")}
        for r in out if r.get("state") == STATE_SCORED}
```

소비자 쪽은 **확정된 프레임 자기 행을 먼저 보고**, 없을 때만 종전의 승자 경로로 떨어진다.

```python
    by_frame = r.get("by_frame")
    if isinstance(by_frame, dict) and applied in by_frame:
        row = by_frame.get(applied) or {}
```

- 경계를 넘으면서 **이름이 바뀐다**: 후보 행의 `placement`가 `anchor`로 실려 가고
  `_placement_of`는 `row.get("anchor")`로 읽는다.
- **클라이언트는 한 줄도 안 고쳤다.** 클라가 `ruling`을 키를 가리지 않고 얕은 복사하기
  때문이고, 커밋의 주석이 그 근거를 명시한다.
- 여기 실리는 값은 전부 **스코어러가 만든 사실**이지 화면이 보내온 숫자가 아니다.

## 같이 얼어 있던 두 번째 소비자

원점만 얼어 있던 것이 아니다. 확정 기록 행도 같은 함수를 읽는다.

```python
        _p = _placement_of(c, ruling)
        c_dx = None if _p is None else _p["dx"]
```

그래서 이기지 않은 프레임의 `FrameConfirmationSource.shift_dx`/`shift_dy`가 **`NULL`로
남아 있었다.** 그리고 `box_aware_origin`이 `False`인 채였는데, 그것이 하류에서
`valid_die_ref` 스탬프의 게이트다.

## 검증

- **커밋 본문은 스위트 수치를 제시하지 않는다.**
- 🔴 **이 커밋은 테스트를 추가하지 않았다.** 변경은 `server/frame_confirmation.py`
  (+24/−1)와 `server/map_alignment.py`(+15) 두 파일뿐이고 `server/tests/` 아래는 손대지
  않았다. 증상은 확정을 세 번 눌러서 관측됐고, 그것을 다시 잡아 줄 회귀는 이 시점에 없었다.

## 그때 남아 있던 것

- **모든 비승자 후보가 아니라 `STATE_SCORED`인 후보만** 자기 배치를 받는다. 채점되지 않은
  후보, 그리고 정수 `dx`/`dy`를 못 가진 행은 여전히 `None`이고 **원점을 그대로 둔다** —
  새 갈래 안에서 반환하므로 승자 경로로 떨어지지도 않는다.
- 🔴 **낡은 `ruling`은 조용히 옛 동작으로 되돌아간다.** `isinstance(by_frame, dict)`가
  거짓이면 종전의 승자 전용 경로를 타는데, 재생·캐시·수리 전 서버가 만든 `ruling`이 전부
  거기 해당한다. **키가 없다는 것과 값이 없다는 것을 구분하지 않는다.**
- 거짓임이 확인된 그 독스트링 문장은 **이 커밋에서 지워지지 않았다.** 새 인라인 주석이 그
  옆에서 거짓이라고 말하는 형태로 남았다.
