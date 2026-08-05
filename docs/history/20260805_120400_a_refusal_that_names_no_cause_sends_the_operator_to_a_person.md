# 원인을 이름 대지 않는 거절은 운영자를 사람에게 보낸다 — 그리고 거짓 문장은 존재하는 것을 찾으러 보낸다

> **커밋:** `36323f7` (2026-08-05 12:04) | **일자:** 2026-08-05 정오
> **선행:** [`20260805_090800`](./20260805_090800_the_decision_screen_was_specified_and_the_setup_was_specified_by_nobody.md)(`74ce8b1` — 참조 카탈로그를 `?rule=`에 묶은 커밋)
> **담당:** 제품 소유자(운영 신고: 셀도 있고 메타 행도 있는 `valid_die_ref` 맵을 picker가 안 준다) · map 구현
> **대상:** `server/map_alignment.py`(259) · `server/main.py`(+47) · `client2/src/map2/api.js`(127) · `view_model.js`(67) · `client2/src/map_editor2.js`(66) · 하네스(175) · **신규** `server/tests/test_map_alignment_references.py`(**+343**) · `test_map_alignment_worklist.py`(25)
> **스위트:** 커밋 메시지 기준 **서버 2,524 passed**, 클라 게이트 초록. **diff 안에 기록 산출물 없음** — 이 커밋은 `check_harnesses.mjs`를 아예 건드리지 않는다.

## 배경 — 원인 둘이 이름 붙일 수 없는 상태였고, 신고는 둘 다에 들어맞았다

제품 소유자에게 **셀이 있고 `wafer_map_metadata` 행도 있는** `valid_die_ref` 맵이
있는데 picker가 그것을 제시하지 않았고, **화면은 왜인지 말할 수 없었다.**

## ① `meta_unreadable` — 존재하는 행을 「등록되지 않았다」고 말하고 있었다

`load_map_meta`는 **메타 행이 없을 때와 행의 `grid_metadata`가 비었거나 안 읽힐 때
둘 다 `None`**을 돌려준다. 거절 문장은 후자에서도 「규격이 `wafer_map_metadata`에
등록되지 않았습니다」라고 말했다 — **소유자가 표에서 눈으로 보고 있는 행에 대해.**

> **거짓 문장이 존재하는 것을 찾으러 보냈다.**

행 존재 프로브를 **거절 경로에서만** 돌려 갈랐다:

```python
        if _meta_row_exists(db, table, map_id):
            return _refuse(REF_REFUSAL_META_UNREADABLE,
                           "기준 맵 '%s · %s'의 wafer_map_metadata 행은 있으나 "
                           "grid_metadata가 비어 있거나 읽히지 않습니다" % (table, map_id))
        return _refuse(REF_REFUSAL_META_MISSING, ...)
```

## ② `key_ambiguous` — 맵 id가 왕복하지 않는다

`compose_map_id`는 키 값들을 **언더스코어로 잇는다.**

```python
    return _MAP_KEY_SEPARATOR.join("" if v is None else str(v) for v in values)
```

그리고 `map_overlay.map_key_parts`는 **마지막 컬럼이 나머지를 흡수**한다
(이 함수 자체는 기존 코드이고 이 커밋에서 수정되지 않았다):

```python
    # 마지막 컬럼이 나머지를 흡수(랏 이름에 '_'가 있는 경우 방어)
    head = parts[:len(key_cols) - 1]
    tail = "_".join(parts[len(key_cols) - 1:])
    return list(zip(key_cols, head + [tail]))
```

그래서 `product='A_B', type='C'`로 키를 잡은 바닥은 **`A_B_C`로 등록되고
`product='A', type='B_C'`로 읽힌다.** 양쪽 다 존재하고, 셀도 거기 있고,
**매칭되는 행은 0이고, 조용히 제시되지 않는다.**

**첫 키 컬럼 값에 언더스코어가 들어가는 모든 경우**가 여기에 걸린다.
거절이 이제 **자기가 실제로 바인딩한 컬럼을 인쇄한다.**

키 컬럼이 하나뿐인 테이블은 모호성 판정에서 **명시적으로 제외**된다.

## 이름 붙은 거절 어휘

```python
REF_REFUSAL_META_MISSING · META_UNREADABLE · GEOMETRY · BINDING
NO_CELLS · COORDS_UNREADABLE · KEY_UNSPLIT · KEY_AMBIGUOUS
SPEC_MALFORMED · DECLARATION
```

**거절된 항목에 `cell_count`가 붙는다.** 그것이 「셀이 있는데도 거절됨」과
「셀이 없음」을 가른다.

## 내 최적화가 목록을 정확히 운영 상황에서 못 쓰게 만들었다

참조 카탈로그를 `?rule=`에 묶은 것은 **내 최적화**였다. 그리고 그 결합이
**운영 상황 그 자체에서** 목록을 도달 불가로 만들었다 — **규칙이 선언돼 있지
않으니 워크리스트가 아무것도 답하지 못하고, 참조 목록을 같이 끌고 내려간다.**

> **참조는 맵 테이블의 성질이지 규칙의 성질이 아니다.**

```python
@app.get("/api/maps/alignment/references")
def get_map_alignment_references(table: str = None,
                                 cap: int = map_alignment.MAX_REFERENCE_CANDIDATES,
                                 db: Session = Depends(get_db)):
```

`selection.references`는 여전히 워크리스트에 실려 가고, **그 둘이 같다는 것이
단언된다** — 다만 단언은 HTTP 라우트가 아니라 **양쪽이 부르는 공유 함수**에
대고 이뤄진다(라우트는 그 함수로 한 줄 위임이다):

```python
    assert _wl(env)["selection"]["references"] == ma.resolve_reference_catalog(env, {})
```

**해소 경로 하나에 호출자 둘**이다.

## picker에서 종류가 앞에 온다 — `select`는 오른쪽부터 잘린다

진짜 맵 id가 폭을 다 먹으므로, **값 대 점유**가 잘림에서 살아남게 앞에 놓았다.
상수인 테이블 이름이 **184픽셀 중 100을 쓰지 않게** 한다. 측정되지 않은 셀 수는
**`미상`이지 0이 아니다.**

## 그때 남아 있던 것

- 스위트 수치도 클라 게이트 결과도 **이 커밋의 diff에 기록되지 않았다.**
- `map_key_parts`의 흡수 규칙은 **그대로 남아 있다.** 이 커밋이 한 것은 그
  결과를 **이름으로 진단하는 것**이지 왕복을 고친 것이 아니다.
