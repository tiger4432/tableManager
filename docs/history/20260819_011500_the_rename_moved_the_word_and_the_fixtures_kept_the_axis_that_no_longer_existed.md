# 개명이 낱말을 옮겼고, 픽스처는 이미 없어진 축을 그대로 들고 있었다

**날짜:** 2026-08-19 00:28~01:16 · **커밋:** `561fe6d` `2e7ca04` `8e92cc2` `370035c` `6fa98ae`
**레인:** 서버(맵 정렬 · 테스트 복구) · **측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경 — 열흘 전 커밋이 낱말의 «뜻»을 바꿨다

`db1ee42`(2026-08-08)가 후보의 둘째 토큰이 무엇을 뜻하는지 바꿨다. **거울**(`_front`/`_back`,
진짜 기하학적 뒤집기)이던 것이 **걸음의 시작 모서리**(`_tl`/`_tr`, 인덱스 순서에 대한 주장)가
됐다. 후보 공간 자체는 온전했다 — 4회전 × 2시작모서리.

그런데 픽스처들은 **텍스트 개명으로 옮겨졌다.** 그리고,

> a rename cannot plant an axis that did not exist before.
>
> `_tl` and `_tr` are THE SAME MAP coordinate-wise. `_plant` only moves coordinates, so a
> fixture labelled rot0_tr IS a rot0_tl map, and the scorer ... answering rot0_tl is RIGHT.
> **67 reds, all downstream of that one sentence.**

**빨강 67개가 전부 그 한 문장의 하류였다.** 픽스처는 좌표만 옮기는데 새 축은 좌표가 아니라
**걸음의 번호**로 심어야 했다.

## 세 가지 다른 원인이 한 파일 더미에 섞여 있었다

빨강을 한 덩어리로 보면 「정렬이 망가졌다」가 된다. 셋으로 갈렸다.

**① 픽스처가 심을 수 없는 축을 라벨로 심고 있었다** (`370035c`, 67건).
좌표를 옮겨 심는 픽스처는 이제 **네 기하 프레임**을 이름하고, 시작 모서리가 필요한 픽스처는
**심는 프레임 안에서 걸음에 번호를 매긴다.** 도우미가 실제로 스코어러가 도는 것과 같은지를
단언하는 테스트가 함께 붙었다.

**② 한 파일이 두 어휘를 섞어 비교하고 있었다** (`8e92cc2`, 14개 중 9건).
두 프레임 어휘가 **설계상 공존한다** — `frame_text`는 META 축(`rot90_front`/`rot90_back`,
물리적 면)을, `candidate_text`는 후보 축(`rot90_tl`/`rot90_tr`, 걸음 시작 모서리, 전부 front)을
철자한다. 그 파일의 `FRONT_FRAMES`는 **잡 진리와 비교되고 `source_meta_for_frame`에 넘겨지는**
값이라 META 축 소속인데, 개명이 그것까지 `_tl`로 바꿔 놨다. **다른 축의 낱말로 비교하고
있었으니 그 뒤로 계속 빨간 것이 맞다.**

**③ 테스트 규칙이 게이트가 요구하는 키를 선언하지 않았다** (`2e7ca04`, 5건).
`a501d6d`가 `declared_alignment_rule`에 게이트를 붙였다 — `alignment` 키가 없는 규칙은 정렬
규칙이 아니므로 요청이 거절된다. 두 테스트 규칙은 그 전에 쓰여 그 키가 없었고, 그래서 모든
라우트 호출이 **재려던 것에 닿기도 전에 400**을 받았다. 실제 선언(`enrichment_rules.json`)은
`"alignment": true`를 들고 있다 — **게이트는 제품의 것이고 실제 선언과 맞으며, 뒤처져 있던
것은 픽스처뿐이다.**

## 🔴 「빨강을 초록으로 만들었다」가 아니라 「각 수리를 다시 빨갛게 해 봤다」

세 커밋 모두 같은 규율을 적었다: **고친 것마다 재는 대상을 깨뜨려 빨갛게 만들어 봤다.**

```
Mutation-proved, each repair reddened by breaking what it measures:
  test_route_passes_the_columns_through          x_col/y_col dropped in
  test_route_400s_on_a_column_the_table_lacks    resolve_alignment_view
  ...
```

그리고 `370035c`가 **제품 파일이 안 바뀌었음을 바이트로** 못 박았다.

> No product file changed: map_alignment.py, map_overlay.py, dt_map_derivation.py and
> seed_dt_index_walk.py are byte-identical to HEAD after the mutation work.

변이 작업은 제품 파일을 임시로 깨뜨리는 일이라, **되돌려 놨다는 것을 스스로 증명하지 않으면**
그 초록이 무엇의 초록인지 알 수 없다.

## 초록이었는데 두 가지가 틀려 있던 테스트 하나

`test_a_map_that_is_not_this_wafer`는 **두 결함을 안고 초록**이었다. `tie`를 단언했는데 그건
옛 공간에 거울이 있었고 정사각형이 전치 대칭이라 성립한 것이었고, 블록에 넘긴 걸음은
`rot0_tl` 맵이 나를 것이어서 걸음 축이 살아나자 스코어러가 **정확하게** `rot0_tl`을
400/400으로 지목했다. 거절은 이제 `no_discrimination`이다.

**이름은 여전히 픽스처를 과장한다. 그 사실을 개명으로 감추지 않고 docstring에 적었다.**

## 진단 로그가 테스트 프로세스끼리 충돌하던 문제

`561fe6d`. 회전 핸들러는 파일을 열어 둔 채 롤오버에서 이름을 바꾼다 — pytest 프로세스 둘이
같은 `server/align_test.log`에 쓰면 Windows에서 `PermissionError: [WinError 32]`가 나고,
**진 쪽이 그때 돌고 있던 아무 테스트의 실패로 보고한다.**

> which has already cost one corrupted measurement in this project.

pytest 아래에서는 `<tempdir>/assy_align_test_<pid>.log`가 된다 — **핸들을 소유하는 것이
프로세스이므로 프로세스마다**, 그리고 **드릴은 작업 트리의 산출물이 아니므로** `server/` 밖에.
운영은 손대지 않았고 회전 핸들러도 그대로 돈다. `6fa98ae`가 `CODE_MAP.md`의 옛 경로를 따라
고쳤다.

## 아키텍처 영향

제품 코드 변경은 `561fe6d`의 **진단 라인 목적지 하나**뿐이다. 나머지는 전부 테스트 쪽이고,
정렬 동작은 바뀌지 않았다.

## 검증

- 기록자가 직접 확인한 것: 인용문이 각 커밋 본문·diff에 실재한다는 것, `db1ee42`(08-08)의
  본문이 **픽스처 개명의 여파를 언급하지 않는다**는 것.
- ⚠️ 빨강 개수(67 / 9 of 14 / 5)와 변이 목록은 **커밋의 측정**이다. 기록자는 스위트를
  돌리지 않았다.

## 그때 남아 있던 것

- `db1ee42`의 본문은 「wire shape는 그대로다, `parse_frame`이 tl/tr을 받고 front/back도 legacy로
  받는다」까지 적었다. **저장된 확인은 계속 파싱됐다** — 틀린 것은 저장 형식이 아니라
  **픽스처가 그 개명을 따라간 방식**이었고, 그 사실이 드러나는 데 열흘이 걸렸다.
- `test_a_map_that_is_not_this_wafer`의 이름은 여전히 픽스처를 과장한다.
- 이 시간대에 `server/map_alignment.py`·`map_overlay.py`·`dt_map_derivation.py`·
  `seed_dt_index_walk.py`는 다른 레인의 작업 트리 변경을 안고 있었다. 이 커밋들은 그것들에
  손대지 않았다.
