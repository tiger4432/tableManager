# `main`은 워커 안에서 안정된 이름이 아니다 — 그리고 웹 프로세스가 무사했던 것은 우연이었다

> **일자:** 2026-08-04 오후 | **관련 커밋:** `cd80d66`
> **담당:** 운영 신고(어드민 AUTO CONFIRM 소급 실행이 죽는다) · server 구현
> **대상:** 신규 `server/column_filter.py` · `server/main.py`(재수출) · `scripts/archive/profile_fetch.py` · 신규 테스트 2건
> **스위트:** `2007 passed / 2 skipped`

## 증상 — 같은 규칙인데 두 표면이 다른 답을 했다

어드민 AUTO CONFIRM을 소급 실행하면 이렇게 죽었다.

```
AttributeError: module 'main' has no attribute 'get_column_filter_condition'
```

그런데 **CLI에서 같은 스윕을 돌리면 됐다.** 순환 임포트도 아니고 낡은 프로세스도
아니다 — 새 프로세스에서 `import main`은 성공하고, 그 심볼은 **40개 커밋 동안
`main.py`의 모든 버전에 있었다.**

## 원인 — `sys.path[0]`에 남의 `main.py`가 앉는다

스케줄러는 **각 수집기 자신의 디렉터리를 `sys.path[0]`에 넣고**, 워처는 테이블별
`scripts/` 디렉터리에 대해 같은 일을 한다. **그 디렉터리들은 사용자 소유다.**

첫 수집기가 돈 뒤부터, 그 프로세스 안의 한정되지 않은 `import main`은
**경로에서 가장 먼저 나오는 `main.py`가 무엇이든 그것에 바인딩된다.**

무해한 미끼를 `sys.path[0]`에 놓고 **그대로 재현**했다 — 스윕이 `_queue_condition`에서
죽고 `main`이 미끼로 해소된다.

| 표면 | 왜 그렇게 됐나 |
|---|---|
| CLI | 그 디렉터리들을 **절대 넣지 않는다** → 무사 |
| 웹 프로세스 | uvicorn이 진짜 모듈을 `sys.modules`에 넣고, **그것이 `sys.path`를 이긴다** → **우연히** 무사 |
| 스케줄러(실행 버튼) | 수집기 디렉터리가 앞에 있다 → **죽는다** |

> **그래서 개수 라우트(웹)와 실행 버튼(스케줄러)이 같은 규칙에 대해 서로 다른 답을
> 하고 있었다.**

## 수리 — 이 저장소가 이미 쓰던 처방

번역기를 `server/column_filter.py`로 옮긴다 — **엔트리포인트가 아니고 `main`이라고
불리지 않는 모듈**이다. 애초에 FastAPI가 필요 없었다 — SQLAlchemy와 crud만 필요하다.

같은 처방이 H4에서 이미 쓰였다: `chain_ingestion_worker`가
`from main import to_local_str`를 하자 `utils/time_format.py`를 만들었다.
**그 수리는 사본 둘을 남겼고**, 그중 `scripts/archive/profile_fetch.py`를 여기서
다시 겨눴다.

`main.py`가 이름을 재수출하므로 `main.get_column_filter_condition`은 **같은 객체**이고,
`blank_predicate` 계약은 여전히 **운영 빌더를 채점한다**(계약 107 passed, 2 skipped).

## 거짓 믿음이 수리의 일부로 정정됐다

모듈 docstring은 이 분석이 **「웹 프로세스에서는 절대 돌지 않는다」**고 적어 뒀다.
그것은 **2026-07-31에 소급 어드민 표면이 웹 **과** 스케줄러 양쪽에서 그것을 부르기
시작한 순간 거짓이 됐다.**

> **그 거짓 믿음이 한정되지 않은 `import main`을 안전해 보이게 만든 것**이므로,
> docstring은 수리 뒤가 아니라 **수리의 일부로** 고쳤다.

## 스위트가 이것을 볼 수 없었던 이유

`conftest.py`가 **수집 시점에** 앱을 임포트한다. 그래서 2000개 넘는 테스트 전부가
`import main`을 `sys.modules`에서 답하고 **`sys.path`를 한 번도 건드리지 않는다.**

새 테스트 둘이 그 구멍을 덮는다.

1. `server/` 아래 어디서든 `import main`을 금지하는 **소스 규칙**(H4 규칙의 일반형 —
   그것은 파일 하나만 덮었다).
2. **미끼 `main.py`를 `sys.path` 맨 앞에 두고** 큐 술어를 번역하는 서브프로세스
   프로브. 그리고 **미끼가 실제로 가렸다는 것까지 단언**한다 — 그래야 이 축이
   불활성으로 갈 수 없다.

## 그때 남아 있던 것

- 스케줄러와 워처는 이 커밋 시점에도 **사용자 소유 디렉터리를 `sys.path[0]`에
  넣는다.** 바뀐 것은 그 프로세스 안에서 `main`이라는 이름에 의존하는 코드가
  없어진 것이다.
- `main.py`의 재수출은 남아 있다 — 기존 호출부와 계약이 같은 객체를 본다.
