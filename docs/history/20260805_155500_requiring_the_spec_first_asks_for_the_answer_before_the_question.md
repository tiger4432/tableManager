# 규격을 먼저 요구하는 것은 질문 앞에 답을 요구하는 것이다 — 그래서 바닥에서 웨이퍼를 빌린다

> **커밋:** `0947972` (2026-08-05 15:55) | **일자:** 2026-08-05 오후
> **선행:** [`20260805_155400`](./20260805_155400_nothing_scored_was_reported_as_a_tie_and_the_right_branch_was_unreachable.md)(`2fb8fc2`, **1분 전** — **이 커밋의 심볼을 미리 부르고 있던 커밋**)
> **담당:** 제품 소유자(순환 지적) · server 구현 — 어제부터 걸려 있던 스펙 판정 9(a)를 닫는다
> **대상:** `server/map_overlay.py`(114 / 5) · `server/frame_confirmation.py`(54 / 2) · `server/database/models.py`(+24) · `server/migrations/add_frame_confirmation.py`(+10) ― **4파일, 테스트 0**
> **스위트:** 커밋 메시지 기준 **변이 10/10(생존자 1건 뒤).** ⚠️ 그 생존자도 그 변이도 이 diff에 산출물이 없다 — 아래 참조.

## 배경 — 제품 소유자가 순환을 지적했다

**소스 맵은 선언된 물리 규격 없이는 채점될 수 없다. 그런데 정렬을 돌리는 이유가
바로 그 맵의 규격을 모르기 때문이다.** 규격을 먼저 요구하는 것은 **질문 앞에
답을 요구하는 것**이다.

한 웨이퍼의 두 맵은 웨이퍼의 치수를 공유하고, **「이 둘은 같은 웨이퍼다」는 애초에
그것들을 정렬하는 전제**다. 그러므로 그것은 **운영자가 할 자격이 있는 주장**이다.

빌리는 것은 **`PHYS_KEYS` 여섯뿐이다.**

```python
    sig = _phys_signature(basis_meta)
    if sig is None:
        return None
    out = dict(meta)
    for k, v in zip(PHYS_KEYS, sig):
        out[k] = v
    out[PHYS_ASSUMED_KEY] = dict(basis or {}) or True
    return out
```

## 실측이 내 스펙 독해를 정정했다 — 그래서 이 표시는 장식이 아니다

9(a)는 **공칭 피치를 공유하면 mm 왕복이 다이 인덱스 위에서 항등**이라고 적었다.
**`rot0_front`와 `rot270_back`에서만 성립한다.** 나머지 여섯은 공유값이 바뀌면
**수백 셀이 움직인다.**

> **가정에 실제 내용이 있다. 그래서 라벨이 장식이 아니다.**

## 격자 치수는 가정할 수 없고 유도할 수도 없다

저장 좌표가 bbox 상대이므로 그 폭은 **웨이퍼 크롭**이다 — **값이 아니라 하한**이
나온다. 그리고 **하한은 거절할 수는 있어도 만족시킬 수는 없다.**

부재는 이름 붙고, 불일치는 **그 맵 하나만 제외한다.** 이전에는 **맞지 않는 맵
하나가 그 단위 전체의 후보 여덟을 죽였다.**

## 회전·면·start·y반전은 값이 아니라 규칙으로 금지된다 — 그리고 그 이유가 중요하다

```
· `rotation`/`side`/`grid_start_*`/`grid_y_invert` — 풀고 있는 미지 그 자체다.
  바닥의 프레임을 베끼는 것은 답을 먼저 적어 놓고 그 답이 맞는지 묻는 것이다.
```

**start나 y반전을 빌리면 채점되는 셀이 전부 움직인다. 그런데 회전이나 면을 빌리면
배치에서는 보이지 않는다** — 후보 루프가 그것들을 덮어쓰기 때문이다. 오염되는 것은
`declared_frame` 배지뿐이다.

> **가장 조용하게 틀리는 방식이 바로 규칙이 필요한 쪽이다.**

## 실려 다니게 만들었다 — 그리고 질문이 둘로 갈렸다

`geometry_declaration`이 **`assumed`**라고 답한다. 절대 `declared`라고 답하지
않는다.

```python
    if m.get(PHYS_ASSUMED_KEY):
        return GEOMETRY_ASSUMED
    if m.get(AUTO_REGISTERED_KEY) is True:
        return GEOMETRY_AUTO_REGISTERED
```

**「이것이 선언인가」는 계속 아니오**이고, **「근거가 있는가」가 새 게이트**다
(신규 `geometry_computable`; `make_frame_transform`의 게이트가 그쪽으로 옮겨졌다).

확정은 **부분 인덱스**로 기록한다 — 어떤 판정이 가정 위에 섰는지가 **스캔 한 번**이다.

```python
    Index("idx_frame_conf_assumed", "rule_name", "unit_key",
          postgresql_where=text("geometry_assumed")),
```

**쓰기 경로는 근거를 요청에서 믿지 않고 스스로 유도한다.**

```python
        out[key] = map_alignment.geometry_basis_of(metas.get(key), c.get("excluded_reason"))
```

클라가 준 값은 **두 번째 철자**가 되고, **구버전 클라는 이 기록이 존재하는 이유인
바로 그 사실을 떨어뜨릴** 것이기 때문이다.

## ⚠️ diff가 커밋 메시지와 어긋난 자리

- 「변이 10/10, 생존자 하나 뒤」 — **이 커밋은 파일 넷을 건드리고 그중 테스트가
  0개다.** 「빌림이 그 여섯 키만 건드린다」를 말하는 테스트
  (`test_the_borrow_changes_the_six_wafer_keys_and_nothing_else`)는 **이전 커밋
  `2fb8fc2`**에 있고, **그 시점 이 코드는 존재하지 않았다.** 생존자를 기록한
  산출물은 어디에도 없다.

## 그때 남아 있던 것

- 이 커밋과 `2fb8fc2`는 **서로의 짝**이다. 어느 쪽도 혼자 온전하지 않다.
- **클라는 이 제안을 아직 읽지 않는다.** 서버가 「바닥의 웨이퍼를 공유한다고
  가정하면 채점 가능하다」고 답하기 시작했는데 **독자가 없다.** 46분 뒤 `0701968`이
  붙인다([`20260805_164100`](./20260805_164100_the_offer_had_no_reader_for_two_commits.md)).
- `_ASSUMED = "assumed"`가 `frame_confirmation.py`에 **지역 재철자**로 들어 있다 —
  임포트 순환을 피하려고 일부러 그렇게 뒀다.
