# 화면이 «진짜 한 배치»를 돌린다 — 판정기를 하나 더 만드는 대신

> **커밋:** `fd3dda05` (2026-08-21 20:59) | **일자:** 2026-08-21 밤
> **레인:** 서버(원장 · 탐색기 서비스 / 백필) + 클라(작성 패널)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **검증:** 라이브 라우트를 통과한 실측 — `lot_event` 142행 · 40분자 · **1,323 원자**
> (문장 여섯 개에 걸쳐) · `dt_job` 144행 · 2분자 · 4원자 · 알 수 없는 id 는 **400**

## 배경 — 두 판정기가 «코드 이름을 하나도 공유하지 않았다»

런타임은 **85가지**로 거절할 수 있고 작성 화면은 **57가지**로 거절할 수 있다. 그리고 둘은
코드 이름을 하나도 공유하지 않는다.

그래서 선언이 폼을 통과하고 백필에서 죽었다. **`lot_event`는 오늘 그것을 다섯 번 했다** —
매번 화면에서는 초록이고 실행에서는 빨강이었고, 매 라운드 소유자를 다시 불러 **폼에서는
아무도 볼 수 없는 구멍**에 대해 듣게 했다.

## 변경 — 옮기지 않고, 진짜를 «한 번» 돌린다

그 거절들을 폼 검증으로 이식하면 **두 번째 판정기**를 짓는 것이고, `main.py`가 이미 그러지
말라고 적어 두었다.

시험 실행은 **첫 페이지를 읽고**, 스냅샷이 이미 이름 붙인 **신뢰된 구현들을 실행**하고,
**원자도 커서도 안 쓰고**, 읽은 행 수·분자 수·문장별 원자 수를 보고한다. **거절하는 것은
있는 그대로 돌아온다.**

```python
    @staticmethod
    def _test_run_refusal(source):
        """One refusal, with the form path it lands on WHEN THERE IS ONE.

        🔴 THE PATH IS MAPPED, NEVER INVENTED. Snapshot-born refusals already address the
        form (`bundle.sources.<id>.bind.mappings.<sentence>`), and the driver's own
        refusals address the same tree one prefix short (`sources.<id>.read.cursor`). Those
        two are turned into a form path. Everything else -- `cursor_value`,
        `known_registrations`, `role_frame.rows[0].roles.subject` -- keeps `form_path`
        empty and is shown RAW, because a guessed box is worse than an unplaced sentence."""
```

거절의 경로가 폼을 주소로 삼으면 **그 칸으로 가는 버튼**이 되고, 아니면 **raw 경로를
그래도 인쇄한다 — raw 가 침묵보다 낫기 때문이다.**

## 🔴 `known_registrations` — 셋 중 어느 값인지가 «측정»으로 정해졌다

```
라이브 집합을 넘김   1,173 원자   <- 원장에 이미 있는 등록 150건이 «억제»된다
빈 집합             1,323 원자   <- 백필과 «일치»
None                            탐침이 없는 소스는 registration_context_required 를 «듣는다»
```

라이브 집합을 넘기면 **끝난 문장이 아무것도 안 내는 문장과 정확히 같아 보인다.** 그래서
탐침이 선언됐으면 **빈 집합**, 안 됐으면 **None** 이다. None 을 유지한 이유는 탐침 없는
소스가 **조용한 통과 대신 그 거절을 듣게** 하기 위해서다.

## 상태 이름과, 손대지 않은 것

한 번도 안 돌아 본 소스는 `ACTIVE`가 아니라 **미검증**으로 읽히고, 더 오래된 선언 텍스트에
대고 돈 실행은 **선언 변경됨**으로 읽힌다.

**저장은 일부러 손대지 않았다.** 반쯤 쓴 선언은 여전히 저장 가능해야 한다. 아니면 폼이
**한자리에 앉아 다 끝내라고 요구**하게 된다.

## 아키텍처 영향

- 작성 화면이 **런타임의 거절을 자기 어휘로 번역하지 않고 그대로 통과시키는** 첫 경로다.
  두 판정기를 하나로 유지하는 대신 **두 번째 판정기를 안 만드는** 쪽을 골랐다.
- 시험 실행은 **쓰기가 없다** — 원자도, 커서도.

## 그때 남아 있던 것

- 매핑이 없는 소스는 **비어 있는 칸의 경로를 대고** 거절한다. 선언됐지만 조용한 문장은
  **생략되지 않고 0으로 나열된다.**
- 이 라운드는 저장 경로를 안 건드렸으므로, 반쯤 쓴 선언이 저장돼 있는 상태는 그대로다.
