# 화면으로 만든 확정은 **전부** 「무엇을 확정했는지」가 빈 채로 남았다 — 그리고 200이 나갔다

> **커밋:** `e6fcc92`(2026-08-06 01:17) | **일자:** 2026-08-06 새벽
> **후속:** [`20260806_065114`](./20260806_065114_the_confirmation_reached_the_metadata_because_without_a_marker_the_winner_is_a_row_nobody_touched.md)(`3e96747` — **이 커밋이 만든 `resolve_ruling_state`·`_resolve_frames` 위에 확정 사슬이 얹힌다.** 그 커밋의 소스 주석이 이 커밋을 이름으로 인용한다)
> **담당:** 제품 소유자(2026-08-05 판정: 확정이 기록하는 것은 「어느 좌표를 정렬했나」다) · server 구현
> **대상:** `server/frame_confirmation.py`(+150 / −6) · `server/database/models.py`(+29 / −2) · `server/main.py`(+18 / −3) · `server/migrations/add_frame_confirmation.py`(+10) · 테스트 4종(**+320 / −36**) · `docs/architecture/data_model.md`
> **스위트:** 커밋 메시지 기준 **수리 전 16 빨강 → 수리 후 초록**, **변이 7건(고친 줄마다 하나)**, 그리고 수리 후 실행은 **실제 라우트로 실제 PostgreSQL에 실제 규칙 파일**을 대고 돌렸다. 마이그레이션은 **가산적·멱등**이고 새 컬럼은 **바로 이 위험 때문에 존재하는 시스템 컬럼 게이트**에 함께 등록됐다.

## 배경 — 두 컬럼이 스키마가 아니라 **한 규칙의 `target_fields`**였다

확정 기록은 확정된 값을 **`core_frame` / `dt_frame` 두 고정 컬럼**에 저장했다.
그런데 그 둘은 스키마가 아니라 **규칙 **하나**의 `target_fields`**다.

검증은 **`target_fields` *밖의* 키를 거절**했지만 **선언된 필드가 저장 가능한지는 한
번도 확인하지 않았다.** 그래서 **다른 규칙의 답은 검증을 통과하고 아무 데도 안 쓰였다.**

실측 2026-08-06: `dt_job_lot_slot_attribution`의 답이 **통째로 NULL로 들어가고 라우트는
200을 냈다.**

> 이 기록에서 **비어도 되는 마지막 필드가 「무엇을 확정했나」**다. 비면 이 기록의 존재
> 이유가 사라지는데, **그런데도 완료로 보인다.**

같은 기록의 **결정 키(decision key) 절반은 이미 일반화돼 있었다.** 확정 값 절반은
한 번도 그렇게 되지 않았다. 수리는 **없는 모양을 발명한 것이 아니라 옆에 이미 있던
모양을 맞춘 것**이다.

```python
    frames = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
```

## 🔴 그런데 내가 재현한 것은 **약한 판**이었다

**진짜 클라이언트는 그 키를 아예 보내지 않는다.** **일부러 빈 객체를 올리고**
답을 **다른 세 필드**에 담는다 — 「확정이 기록하는 것은 **어느 좌표를 정렬했나**」라는
판정을 인용하면서.

**라우트는 그 셋 중 아무것도 읽지 않았다.**

> **그래서 화면으로 만든 확정은 전부 아무것도 기록하지 않았고, 200을 반환했다.**

새 컬럼 넷이 그 셋을 받는다 — `confirmed_frame` · `map_table` · `x_col` · `y_col`,
그리고 점유 전용 실행에서 NULL이 되는 `value_col`.

## ① 알고 미뤄 둔 자리였고, 그 핀이 그렇게 적혀 있었다

두 테스트가 이 격차를 **「격차가 발견이 아니라 결정이 되도록 못 박음」**이라는 문구와
함께 고정하고 있었다.

```python
-    # but not WHAT WAS CONFIRMED. Pinned so the gap is a decision, not a discovery.
-    assert body["frames"] == {"core_frame": None, "dt_frame": None}
-    assert "columns" not in body and "frame" not in body
+    assert body["frames"] == {}
+    assert body["confirmed"] == {"frame": "rot0_front", "map_table": MAPT, ...
```

**삭제하지 않고 뒤집어서 수리를 단언하게 했다.** 테스트 이름까지 바뀌었다 —
`..._is_accepted_and_then_silently_dropped` → `..._is_stored_under_the_name_the_rule_declared`.

**출하된 클라이언트가 변경 없이 통과한다**는 것이 새 어휘가 옳다는 신호다.
그리고 **아무것도 이름 대지 않는 것은 이제 400**이고, **선언된 필드에 빈 값도 400**이다.

## 🔴 ② 두 번째 결함은 한 필드 옆의 **같은 모양**이었다

쓰기 경로가 판정 상태를 **`ruling` dict 안에서** 읽었다. 그런데 `/view`는 그것을
**응답 최상위 `state`**에 싣고 `ruling` 안에는 **넣지 않는다.**

> **그래서 「`ruling`을 그대로 넘겨라」는 라우트 자신의 지시를 그대로 따르면 기본값이
> 보장됐다.** 그리고 **그 기본값은 선언된 상태 어휘의 구성원이 아닌 낱말**이었다.

실측: `/view`가 `winner: rot0_front`, `margin: 87`로 답한 단위의 확정 기록이
`ruling_state: unscored`로 남았다. **한 행이 서로를 부정하는 두 문장을 실었다.**

상태는 이제 **뷰가 놓는 자리로 이동한다**. 그래서 화면의 전사(轉寫) 규칙이 **두 줄**이
된다 — 판정을 복사하고, 상태를 복사한다.

```python
    if winner:
        return map_alignment.STATE_SCORED
    return STATE_NOT_TRANSPORTED
```

- **없는데 승자가 지명됐다 → `scored`.** **유도가 아니라 전사다** — 뷰가 화면 상태를
  정하는 **첫 분기가 정확히 `if ruling.get("winner")`**이고 여기서 같은 입력에 같은
  식을 쓴다. **두 답이 갈릴 수 없다.**
- **없고 승자도 없다 → 모른다고 말한다.** 판정만으로는 `no_winner`와 `not_scorable`이
  **진짜로 안 갈린다**(`no_candidate_scored` 하나가 양쪽 갈래에서 다 나온다).
  **여기서 표를 만들어 찍으면 그것이 두 번째 판정 구현이고, 둘이 갈리는 날 화면은
  멀쩡한 채 기록만 틀린다.**
- **자기 판정과 어긋나는 상태는 거절한다.** 「채점 안 됨 + 승자는 rot0_front」는
  **명시로 도착한다고 참이 되지 않는다.**

**새 낱말 `state_not_transported`는 `map_alignment.STATE_*`의 구성원이 아니다 —
일부러.** 저쪽 어휘는 「채점이 무엇을 말했나」이고 이것은 **「그 말이 여기까지 왔나」**다.
**다른 질문이라 같은 집합에 넣으면 소비자가 판정 하나로 읽는다.**

## ③ 필수로 만들지 않은 것도 결정이다

**클라는 승자 없는 판정에 대해서도 확정을 활성화한다.** 그래서 상태를 필수로 만들면
**살아 있는 조작자 경로 하나가 깨진다.** 클라가 보내기 시작할 때까지 그 확정들은
**거짓 대신 「전달되지 않았다」를 기록한다.**

## 어휘의 정본을 복사하지 않았다

```python
def accepted_ruling_states() -> set:
    import map_alignment
    return {map_alignment.STATE_SCORED,
            map_alignment.STATE_NO_WINNER,
            map_alignment.STATE_NOT_SCORABLE}
```

**여기 철자를 적으면 그것이 두 번째 집합이 되고, 화면이 본 낱말과 기록된 낱말이
갈리는 날 양쪽 다 멀쩡해 보인다.** 상수를 복사하는 대신 PEP 562 `__getattr__`로
**쓸 때 푼다** — 이 모듈의 나머지 임포트가 전부 지연이라 여기만 최상단으로 올리면
**임포트 무게가 조용히 바뀌기** 때문이다.

## 그때 남아 있던 것

- 이 커밋 시점 확정은 **자기 기록 테이블까지만** 간다. `wafer_map_metadata`까지 가는
  것은 다섯 시간 뒤 `3e96747`이고, 그 커밋은 **낮은 서열로 쓰면 「아무것도 안 바뀐 채
  200이 나간다」**는 판단의 근거로 **이 커밋을 이름으로 인용한다.**
- `STATE_NOT_TRANSPORTED`는 **클라가 상태를 보내기 시작하면 줄어드는 값**이다. 이
  시점 그것을 보내는 클라는 없다.
