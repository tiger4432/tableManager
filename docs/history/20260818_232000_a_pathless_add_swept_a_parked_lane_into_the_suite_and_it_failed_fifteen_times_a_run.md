# 경로 없는 `add`가 세워 둔 레인을 스위트로 쓸어 넣었고, 그게 한 번 돌 때마다 15번 빨개졌다

**날짜:** 2026-08-18 23:19 · **커밋:** `1319113` · **레인:** 서버(감사 · 정리)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경 — 되돌린 라운드가 파일 둘을 남겼다

`server/audit_changeset.py`는 **운영 호출자가 0개**다. 저장소 안의 유일한 importer가 자기
테스트 파일이다.

그 레인은 2026-08-12에 **의도적으로 멈췄다** — `crud.py`·`main.py`·`schemas.py` 훅은
되돌렸고, 이 두 파일은 **추적되지 않은 채로** 남겨 뒀다. 판정과 되돌림 기록은
`PROJECT_STATUS.md`에 있다.

## 무엇이 그것을 스위트 안으로 데려왔나

> Commit 1aeda91, a broad checkpoint six days later, swept them in with a pathless
> `git add` - which is how a parked test file became part of the suite and started failing
> 15 times a run.

**경로를 안 붙인 `add` 한 번**이다. 세워 둔 파일은 세워 둔 상태를 스스로 방어하지 못한다 —
추적되지 않는다는 것이 그 파일의 유일한 표지였고, 그 표지를 지우는 데 명령 하나면 됐다.

## 🔴 그리고 초록 8개가 «공허했다»

23개 중 8개는 **통과하고 있었는데, 읽기 엔드포인트가 changeset을 아예 못 보기 때문에**
통과하고 있었다.

> 8 of them were passing VACUOUSLY - green only because the read endpoint cannot see
> changesets at all, which reads as coverage while measuring nothing, so they are skipped
> with the rest rather than left as false assurance.

빨간 15개는 **자기가 고장 났다고 말하고 있었다.** 초록 8개는 **아무것도 재지 않으면서 커버리지
처럼 보였다.** 둘 중 조용한 쪽이 더 나쁘고, 그래서 함께 skip으로 갔다.

## 지우지 않고 세워 둔 이유

테스트가 못 박는 결함 셋은 **라이브 기계 쓰기 경로에서 여전히 열려 있다** — 과대 값이 감사
행에서 이웃을 떨어뜨리고, NULL과 리터럴 `비어있음`이 구별되지 않고, 기계가 쓴 셀에는
셀 단위 이력이 없다. 손실은 **감사 이력에 국한**되고 라이브 셀 값은 정확하다.

그래서 파일은 **이 레인을 다시 시작하는 사람의 인수 테스트**로 남는다. 삭제했다면 그 판정
근거가 함께 사라진다.

## 모듈 자신에게 표지를 달았다

```
PARKED - NOT WIRED, ZERO PRODUCTION CALLERS
    ...
    THEREFORE: DO NOT READ THIS DOCSTRING AS THE LIVE AUDIT SHAPE. ... This module is the
    PROPOSED replacement, and everything past this banner is written in the voice of a
    change that landed. It did not.
```

**「착지한 변경의 목소리로 쓰인 docstring」**이 이 파일의 진짜 함정이었다. 읽는 사람은
그것을 현재의 감사 모양으로 읽는다. `CODE_MAP.md`도 이 모듈을 라이브로 올려 두고 있었고
같은 커밋에서 정정됐다.

`crud.py`·`main.py`·`schemas.py`는 **건드리지 않았다** — 그 파일들의 주석은 결함을 「알려져
있고 열려 있음」으로 서술하고 있어 정확하기 때문이다.

## 아키텍처 영향

없다. 실행 경로 0줄. 바뀐 것은 **스위트가 무엇을 재는가**와 **파일이 자기 상태를 말하는가**다.

## 검증

기록자가 직접 확인한 것: 배너와 skip이 `1319113`의 diff에 실재한다는 것, 이 모듈의 저장소 내
importer가 자기 테스트뿐이라는 커밋의 주장이 diff 범위와 어긋나지 않는다는 것.
⚠️ 「한 번 돌 때 15번 실패」와 「공허한 초록 8개」는 **커밋의 실측**이다. 기록자는 스위트를
돌리지 않았다.

## 그때 남아 있던 것

- 감사 결함 셋은 열려 있다. 이 커밋은 **아무것도 고치지 않았고**, 고쳤다고 말하지도 않는다.
- `1aeda91`이 함께 쓸어 넣은 다른 파일이 있는지는 이 커밋의 범위 밖이다.
