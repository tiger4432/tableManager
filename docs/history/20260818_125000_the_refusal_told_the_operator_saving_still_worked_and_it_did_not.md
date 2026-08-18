# 거절문이 「저장은 그대로 동작합니다」라고 말했고, 그건 거짓이었다

**날짜:** 2026-08-18 12:48 · **커밋:** `adb1cd7` · **레인:** 서버 + 문서(원장 드라이런)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경 — 히스토리에 적어 둔 자리가 그날 안에 닫혔다

같은 날 11:19의 항목(`ab8657f`)이 **판정 대상**으로 이렇게 남겼다.

> 🔴 거절문의 「저장(3단)은 그대로 동작합니다」는 `source` 타깃에 대해 **거짓으로 보인다.**
> 저장 토큰이 드라이런 응답으로만 화면에 건네지는데, `source`의 드라이런은 이제 항상
> 거절하므로 토큰이 발급되는 지점이 없다.

`adb1cd7`이 그것을 확인하고 고쳤다. **히스토리가 문서로 고칠 수 없는 자리라고 표시했고,
코드 레인이 같은 날 코드로 닫았다.**

## 왜 이게 「문구 수정」보다 큰가

커밋 본문의 문장이 그 이유를 말한다.

> A refusal that misstates what still works is worse than the failure it reports: the
> operator follows it, hits a second failure that looks unrelated, and now has two problems
> to explain instead of one.

운영자는 거절문을 **믿고 행동한다.** 「저장은 된다」를 읽고 저장을 시도하면 `dry_run_stale`
이라는 **전혀 달라 보이는 두 번째 실패**를 만난다. 첫 실패의 원인을 아는 사람도 두 번째
실패는 새 사고로 읽는다.

## 고친 내용

```python
raise DryRunUnavailable(
    f"'{source}' 드라이런을 실행할 번역기가 없습니다 - v1 번역기 4종이 "
    f"2026-08-18에 은퇴했고 v2 미리보기는 아직 이 화면에 연결되지 않았습니다. "
    f"저장(3단)도 함께 막힙니다 - 저장 토큰이 드라이런에서만 나옵니다. "
    f"선언 검증(1단)과 술어 드라이런은 그대로 동작합니다.",
    ...)
```

**안심 문구를 통째로 지우지 않고 «진짜로 영향 없는 것»의 이름을 댄 것**이 이 수정의 형태다.
술어 드라이런은 실제로 무사하다 — `main._ledger_predicate_dry_run`이 `preview()`에 닿기
전에 반환한다. 그 사실이 코드 옆 주석에 근거로 적혔다.

## 낡은 docstring을 지우지 않고 «사양»으로 표시했다

`ledger/dry_run.py`의 모듈 헤더는 「**실제** 번역기를 읽기 전용 트랜잭션에서 태운다」로
시작하고, `main.post_ledger_dry_run`도 같은 주장을 한국어로 하고 있었다. 둘 다 그 시점에
거짓이었다. 이 커밋은 **지우는 대신 표지를 붙였다.**

```
⚠️ AS OF 2026-08-18 THIS MODULE NO LONGER DOES THAT FOR SOURCES. ... Everything below
describes the design the restored preview must satisfy - it is a specification now, not a
description. Read it that way.
```

지웠다면 **그 설계가 왜 그랬는지가 함께 사라진다.** 미리보기를 되살릴 사람이 만족시켜야 할
조건이 그 문단들이다.

## 아키텍처 영향

없다 — 실행 경로는 그대로다. 바뀐 것은 **막힌 상태를 운영자에게 어떻게 말하는가**이고,
그것이 이 커밋의 전부다.

## 검증

기록자가 직접 확인한 것: 위 문자열과 두 docstring 표지가 `adb1cd7`의 diff에 실재한다는 것.
토큰 발급 지점이 드라이런 성공 경로뿐이라는 주장은 커밋 본문과 코드 주석의 근거를 그대로
옮긴 것이며, 기록자가 라우트를 태워 재현하지는 않았다.

## 그때 남아 있던 것

- **v2 미리보기(`ledger.setup.preview_selected_cursor_batch`)를 HTTP 라우트에 잇는 일은
  여전히 안 됐다.** 쓰기 0 미리보기 자체는 이미 되고 원자 기준선 하네스가 그것을 몰지만,
  그것을 부르는 라우트가 없다.
- 같은 커밋이 그날 원장 라운드의 **문서 따라잡기**를 함께 실었다 — 히스토리 항목 4개,
  `dry_run.py`(596→179)와 `setup.py`의 CODE_MAP 앵커, 리빙 문서 훑기.
  이 시점 이후 `docs/history/README.md`는 **오늘 밤까지 재생성되지 않는다.**
