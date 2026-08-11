# CODE_MAP이 죽은 심볼 다섯을 살아 있다고 적고 있었고, 「배선 안 됨」이라던 축은 이미 두 곳에서 불리고 있었다

**날짜:** 2026-08-11 07:43 · **커밋:** `686dfbe` · **레인:** 문서(CODE_MAP 재앵커)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

직전 커밋 `6cc7a6e`가 리빙 문서(SPEC·PRIMITIVES 등)를 `db1ee42`의 후보 공간 교체에
맞췄다. `CODE_MAP.md`는 심볼·시그니처·라인 앵커를 다루는 별도 문서라 이 커밋에서 따로
재검증된다. 기준 리비전은 `7097a67`(당일 HEAD) — 커밋된 blob만 재고, 워킹트리는 보지
않는다.

## 죽은 심볼 다섯이 살아 있는 행으로 등재돼 있었다

`db1ee42`가 지운 `load_alignment_sides`·`SIDES_KEY`·`score_candidates`의 `sides=`
매개변수·클라의 `SIDES`/`SIDE_HEADERS`가 CODE_MAP에는 여전히 시그니처 표의 행이었다.
grep 정의 검사로 재앵커했다:

```
git grep -nE "^(SIDES_KEY|def load_alignment_sides)" -- server/map_alignment.py
git grep -nE "^export const (SIDES|SIDE_HEADERS) " -- client2/src/map2/candidates.js
```

두 질의 모두 **0건**이어야 정본이다. 단, `declaration.js`의 `SIDES`는 대상이 아니다 —
그건 **저장된 메타의 어휘**(`front`/`back`)이고 여전히 실재한다. 사라진 것은 **후보
축**으로서의 `side`뿐이다.

## 시그니처 아홉이 옛 호출을 던지지 않고 틀리게 만드는 방식으로 드리프트했다

`build_alignment_view`는 `index_col`을 매개변수 목록 **중간에** 새로 얻었다(`value_col`과
`assume_reference_geometry` 사이). `_anchor_shift`·`make_frame_transform`·
`_frame_transformer`는 모두 box·corner 항을 얻었다. 위치 인자로 부르던 옛 호출은
**예외를 던지지 않고 다른 인자에 값을 넣는다** — 이 커밋이 이 부류를 「가장 위험한
낡음」으로 부르는 이유다.

## §5-F가 「호출자 없다」던 축이 실제로는 두 곳에서 불리고 있었다

```
§5-F ①의 「축은 있는데 아무도 탐색하지 않는다」가 이제 거짓이다 —
left_to_right_of를 부르는 것은 _anchor_shift와 score_candidates다
```

이 걸음 축은 거울 절반에 **더해진** 것이 아니라 그것을 **대체**했다 — CODE_MAP은 이제
「추가」가 아니라 「교체」로 적는다.

## map_overlay.py가 87a944e와 blob 동일이라고 표시돼 있었는데 237줄 자랐다

등재 당시 `87a944e` 기준으로 봉인됐던 표시가 갱신되지 않은 채 남아, 2,289 → 2,526줄로
자란 사실(`origin_box`·`die_mask_from_reference`·`_ORIGIN_BOX_CACHE` 신설, box 인자
추가)을 가리고 있었다. `dt_map_derivation.py`(849줄, `parse_frame`의 소유자)는 아예
등재된 적이 없었다 — 신설 §5-G로 처음 올랐다.

## 검증

이 패스 자신의 수치: **깨진 링크 6 → 1, 새로 깨진 것은 없다.** 남은 하나(`§5-F ①`)는
제목의 원문자(①, U+2460)를 GitHub 슬러거가 지우는지 남기는지 이 문서 안에서 확인할
방법이 없어 **판정을 보류**했다 — 「모르는 것을 고친 척하지 않는다」는 이 커밋 자신의
표현이다. 이 재앵커는 코드를 바꾸지 않으므로 pytest/하네스 스위트 대상이 아니다.

## 그때 남아 있던 것

- `1e29078`이 바꾼 `client2/src/`의 나머지 파일들(`api.js`·`grid.js`·`main.js`·
  `clipboard.js`·`dom.js`·`websocket.js`·`style.css`)은 **이 패스가 열지 않았다** —
  §7의 해당 행은 이 시점에도 미검증으로 남는다.
- 인제션/outbox 경로 세 파일(`database/crud.py`·`database/database.py`·
  `parsers/directory_watcher.py`)은 top-level 심볼 집합의 **무변동만** 확인했을 뿐,
  본문 산문 서술은 이 패스가 재검증하지 않았다.
- `server/main.py`에 `get_cell_history`가 두 번 정의된 상태는 이 패스가 아직 고치는
  대상이 아니었다 — 그 해소는 이날 뒤에 오는 `dab9152`.
