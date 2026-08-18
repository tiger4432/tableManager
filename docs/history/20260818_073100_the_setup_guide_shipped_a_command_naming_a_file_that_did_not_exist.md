# 셋업 가이드가 「존재하지 않는 명령을 쓰지 말라」는 문장 두 줄 위에 존재하지 않는 명령을 실었다

**날짜:** 2026-08-18 07:05 / 07:11 · **커밋:** `bfb510a` → `5359fdd` · **레인:** 문서(원장 V2)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

Ledger V2가 1~7단계 승인으로 닫히고 Ontology Config Explorer까지 승인된 뒤에도
`docs/guide/ONTOLOGY_LEDGER_SETUP.md`는 **승인 이전 구조**를 현행처럼 설명하고 있었다 —
flat config, source-kind translator, `declared_lookup`, 옛 migration/reset 절차. 사용자가 운영
manifest 여섯 파일을 앞에 놓고 새 Source를 직접 세우려면 Pack/Profile/Preparer/Mapper,
cursor 전순서, verified join, binding 승인 계약이 한 흐름으로 이어져 있어야 하는데 그 흐름이
문서에 없었다.

직전 인수인계 감사가 별도로 두 불일치를 지목했고, 둘 다 **문서가 자기 근거보다 후하게
적은** 모양이었다.

1. `task/ontology_config_explorer_pending.md`의 완료 게이트가 「server 관련 단위·계약·
   **PostgreSQL** 테스트 … 통과한다」에 체크돼 있었다. 같은 라운드의 Evidence는 Explorer
   PostgreSQL E2E **미실행**을 정직하게 적고 있었다 — 체크박스와 증거가 어긋난 것이다.
2. 인수인계 문서는 Admin token을 **항상 필수**라고 단정했지만, 실제 API는 환경변수 설정
   여부에 따른 두 상태 계약이었다.

## `bfb510a`이 한 일

가이드를 Ledger V2 전용 17절로 전면 재작성했다(그 한 파일에서 +1538 / −289). 운영
`server/config/ontology/` 여섯 파일과 `server/config/sample/ontology/transfer_explorer/`를
기준 샘플로 묶고, manifest·physical catalog·virtual join·Vocabulary·Entity·Preparer·Mapper·
Pack·Profile·Source·chain·enrichment의 필드를 **실제 JSON으로** 설명했다. `declared_lookup`과
임의 실행식 대신 verified Source Preparer batch join을 쓰는 경계 —**config가 신뢰 코드를
발명할 수 없다**— 를 명시했다.

체크박스는 실행한 것과 실행하지 않은 것으로 갈라졌다.

```
- [x] 실행 가능한 server 직접 단위·계약군, Ledger V2 직접 회귀, client harness/build gate가
      통과했다. 실제 수치는 승인 Evidence에 기록했다.

  **미실행 범위:** Explorer PostgreSQL E2E와 full server suite는 사용자 지시에 따라
  재실행하지 않았다. 통과로 주장하지 않으며 …
```

## 6분 뒤 `5359fdd`이 고친 것

같은 커밋이 **자기가 인쇄한 명령을 검증하지 않았다.** 가이드 §14의 집중 테스트 블록 마지막
줄이 `server/tests/test_ledger_runtime_v2.py`를 가리켰는데, 트리의 실제 파일명은
`test_ledger_v2_runtime.py`다. 그리고 그 블록 **두 줄 아래**에 이런 문장이 있었다.

> 실제 파일명은 변경 범위와 현재 test inventory를 확인한 뒤 선택한다. 존재하지 않는 명령을
> 복사해 통과 근거로 쓰지 않는다.

`5359fdd`이 파일명과 `--basetemp` 경로를 함께 바로잡았다. 같은 커밋이 Admin 인증 서술도 한 번
더 좁혔다 — `bfb510a`은 「두 상태」까지는 정정했지만 token이 설정된 쪽을 `401` 하나로 뭉쳐
「header 누락/불일치」라고 적었고, 실제 게이트는 둘을 나눈다(`server/admin_auth.py`, 이 커밋
시점 `~221`·`~224`).

```python
    presented = request.headers.get(ADMIN_TOKEN_HEADER)
    if not presented:
        raise HTTPException(status_code=401, detail=_MISSING_DETAIL, ...)
    if not _matches(presented, expected):
        raise HTTPException(status_code=403, detail=_MISMATCH_DETAIL, ...)
```

가이드의 troubleshooting 행과 `docs/process/FORK_SESSION_BRIEF.md`의 같은 문장이 「header
누락 `401` · 값 불일치 `403` · token 미설정 strict route `503`」 셋으로 갈라졌다.

## 아키텍처 영향

없다 — 두 커밋 모두 문서 전용이고 server/client/runtime/config 코드와 DB는 건드리지 않았다.
바뀐 것은 **어느 문서가 정본인가**다: 새 담당자의 읽기 순서가 legacy `LEDGER_GUIDE`의
translator/reset 절차가 아니라 V2 전용 셋업 가이드에서 시작하도록 문서 지도·소유권·인수인계가
재배선됐고, `LEDGER_GUIDE`의 legacy 절차에는 V2 전환 배너가 붙었다.

## 검증

- `bfb510a`이 스스로 적은 검증은 링크 대상 존재 확인, 참조 JSON 12개 parse 확인,
  히스토리 인덱스 재생성과 `--check`, `git diff --check`다. **인쇄한 pytest 명령의 대상
  파일이 존재하는지는 그 목록에 없었고**, 정확히 그 자리가 6분 뒤에 빨개졌다.
- 기록자가 `5359fdd` 이후 §14 블록의 다섯 명령을 대조했다: 다섯 파일 모두
  `server/tests/`에 존재한다.
- 문서 전용 변경이라 두 커밋 모두 서버 스위트를 돌리지 않았고, 통과를 주장하지도 않았다.

## 그때 남아 있던 것

- Explorer PostgreSQL E2E와 full server suite는 **여전히 미실행**이었다. 두 커밋이 한 일은
  실행이 아니라 「미실행을 미실행이라고 적는 것」이다.
- `5359fdd` 시점에 가이드가 인쇄한 명령의 **대상 존재**는 맞춰졌지만, 그 명령들이 실제로
  초록인지는 두 커밋 중 어느 쪽도 측정하지 않았다.
- 운영 reset/replay, DB migration/write, legacy config·code 이동·삭제, DT/observation
  cutover는 이 문서 라운드 밖에 그대로 남아 있었고 별도 사용자 승인 대상이었다.
