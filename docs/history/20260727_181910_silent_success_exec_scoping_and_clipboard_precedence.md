# 성공이라고 보고하면서 아무것도 하지 않던 결함 둘 — **없던 기능이 아니라 억눌린 기능이었다**

> 커밋 `512dca7` · 2026-07-27 18:19 · 도메인 Server(auto-update) + Client(그리드 클립보드)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 가이드: [AUTO_UPDATE_GUIDE](../guide/AUTO_UPDATE_GUIDE.md) · 체크리스트: [FEATURE_CHECKLIST](../qa/FEATURE_CHECKLIST.md)
> 선행: [auto-update 활성 토글](./20260725_234500_auto_update_active_toggle.md) · [상관 실패와 인제션 work claim](./20260727_083551_correlated_failure_and_ingestion_work_claim.md) (`sys.exit` 항목의 배경)

## 배경

두 건 다 **사용자가 운영 중인 시스템을 보고 신고**했다. 그리고 두 건 다 같은 모양이었다.

> **기능이 없어서 안 된 게 아니라, 작동하는 메커니즘을 작동하지 않는 메커니즘이 가리고 있었다.**

- auto-update 수집기가 **0행을 적재하고 `SUCCESS`를 남겼다.** 실패 신호가 없었으므로 아무도 몰랐다.
- 그리드에서 **Ctrl+C가 사내망에서 아무 일도 하지 않았다.** 개발 환경에서는 멀쩡히 동작했다.

"조용한 성공"은 실패보다 비싸다. 실패는 보이고, 조용한 성공은 **다음에 그 데이터를 믿고 쓰는 사람에게 청구된다.**

## 변경 내용 — ① exec()의 네임스페이스 둘

### 스코프가 모듈이 아니라 **클래스 본문**이었다

러너는 `exec(code, global_ns, local_ns)`로 서로 다른 두 dict를 넘기고 있었다.
파이썬은 이 형태를 **클래스 본문 스코프**로 실행한다 — 모듈 레벨 `def`/`import`는 locals에 바인딩되는데,
**함수 본문 안에서 해석되는 이름은 `LOAD_GLOBAL`로 컴파일되어 globals만 본다.**
그래서 헬퍼를 다른 함수 안에서 호출하는 수집기는 `NameError`로 죽었다.

```python
# server/run_auto_update.py — 이 커밋에서 dict 하나로 바뀐 지점
# [REQUIRED] Pass ONE dict for both globals and locals. Two distinct
# dicts make exec() run the file with class-body scoping ...
# (Module-level calls compile to LOAD_NAME, which does consult locals,
# which is why only some collectors appeared broken.)
exec(code_content, script_ns)
```

**이 항목에서 가장 옮길 값이 있는 것은 괄호 안의 그 문장이다.**
트리거는 "함수가 함수를 부른다"가 아니라 **`LOAD_GLOBAL`**이다.
모듈 레벨 코드는 `LOAD_NAME`으로 컴파일되고 그건 locals를 **본다**.

> 그래서 헬퍼를 **모듈 레벨에서** 호출하는 순진한 테스트 픽스처는 **고장난 빌드에서도 통과하고 아무것도 증명하지 못한다.**

이번 스위트의 픽스처는 전부 **함수 본문 안에서** 헬퍼를 호출하며, 파일에 그 이유가 적혀 있다.
이 결함이 "일부 수집기만 고장 나 보이는" 모양이었던 것도 같은 이유다.

증상이 조용했던 경로는 이렇게 이어졌다. `NameError` → warning으로 삼킴 → stdout 캡처로 폴백 →
그런데 그 스크립트는 `print`가 아니라 `out`에 대입하므로 **stdout이 비어 있음** →
`"Skipping file generation"` → `last_status = SUCCESS`.

### 첫 수정이 닫지 못한 **두 번째 경로**를 검수가 찾았다

`ns.get("out")`은 **`out = None` 대입과 `out` 미정의를 구분하지 못한다.** 둘 다 `None`이다.
그리고 실제 운영 수집기 둘이 `except` 핸들러에서 `out = None`을 대입하고 있었다 —
**"이렇게 하면 스케줄러가 에러를 남긴다"는 주석과 함께.**

그 주석은 틀렸다. 실제로 벌어진 일은:

1. stdout 수집기로 오인 → **스크립트 전체를 서브프로세스로 재실행**
   (방금 실패한 업스트림에 대한 **두 번째 호출**)
2. 그것도 빈손 → `"Skipping file generation"` → **`SUCCESS`**

> **수집기 작성자들이 이미 믿고 있던 관용구가 실제 판정과 반대였다.**
> 그래서 판정을 그 기대에 맞추는 쪽으로 고쳤다 — 존재 판정을 `"out" in ns`로 바꾸고, 선언된 `None`은 실패다.

```python
if exec_error is None and out_declared and out_data is None:
    # ... it declared it has nothing to give. That is a failure, and it must
    # NOT fall through to the stdout re-run: collectors that do this are
    # error handlers around a network fetch, so re-running the file would
    # repeat the external call and still produce nothing.
    raise RuntimeError(msg)
```

`out = []` / `out = ""`가 **"이번 주기엔 수집할 게 없다"의 공인된 표현**으로 남았고,
가이드의 판정 표가 그것을 **수집기 작성자가 실제로 보는 자리**에 적었다.

### 같은 열다섯 줄 안에 있던 것 — `sys.exit(0)`이 스케줄러 데몬을 죽였다

`SystemExit`은 `Exception`이 아니라 **`BaseException`**이다.
그래서 `execute_collector`와 `check_and_run_schedules`의 `except Exception`을 **전부 관통해** `run()` 밖으로 나갔다.
`process_supervisor`는 모든 종료를 실패로 취급하므로, **반복되는 수집기 하나가 auto-update를 영구 정지시킬 수 있었다.**

이제 종료코드 0/None은 정상 완료로 처리해 `out`을 그대로 채택하고, 0이 아니면 실패다.

### 의도적으로 받아들인 회귀 하나 — **그리고 그 근거가 한 번 뒤집혔다**

`print`도 하고 `out = df`도 하는 하이브리드 수집기는, `to_csv`가 깨지면 이제 **stdout 사본이 있어도 실패로 끝난다**
(수정 전에는 폴백이 CSV를 만들어 `SUCCESS`였다). 두 출력이 조용히 어긋나는 것보다 시끄러운 실패가 낫다는 판단이다.

기록할 값이 있는 것은 **판단이 아니라 그 근거의 이력**이다.
구현자가 처음 붙인 정당화는 *"어차피 아무것도 못 만들었을 것"*이었고,
그것은 **A/B 프로브로 반증됐다.** 조용히 지우지 않고 정정해서 남겼다.

### 스코프를 고치자 **새로 생긴 위험**이 있다

`print` 수집기는 주기마다 부작용을 **두 번** 실행한다. 폴백이 스크립트를 서브프로세스로 한 번 더 돌리기 때문이다.
**원래도 두 번 실행됐지만**, 네임스페이스가 갈려 있던 동안에는 in-process 패스가 첫 `LOAD_GLOBAL`에서 즉사해
부작용을 남기지 못했다. 이제는 끝까지 실행된다 — ack를 POST하거나 소스 커서를 전진시키는 수집기라면
**실제로 두 번 한다**(측정: 1회 → 2회). 커서를 전진시키는 수집기는 매 주기 배치를 하나씩 건너뛴다.

> **버그를 고치면 그 버그가 우연히 막고 있던 것이 풀린다.** 이 커밋이 만든 게 아니라 **드러낸** 위험이고,
> 그래서 코드가 아니라 가이드의 경고로 처리됐다.

## 변경 내용 — ② 그리드 Ctrl+C

### 될 수 없는 구현이 되는 구현을 **억누르고 있었다**

복사 구현이 둘이었다.

- `clipboard.js` — `copy` 이벤트를 `e.clipboardData`로 처리한다. **보안 컨텍스트를 요구하지 않는다.**
- `main.js` — keydown을 가로채 `preventDefault()`를 **먼저** 부르고(= copy 이벤트를 통째로 취소),
  그다음 `navigator.clipboard.writeText`를 부른다. 이 API는 **보안 컨텍스트 밖에서 undefined다.**

수정은 **중복의 삭제**였다. 다시 복원하지 못하도록 자리에 주석을 남겼다.

```javascript
// client2/src/main.js
// NOTE: Ctrl+C is intentionally NOT intercepted here. The native copy
// event is handled by the `copy` listener in clipboard.js, which uses
// e.clipboardData and therefore works in non-secure (plain HTTP)
// contexts where navigator.clipboard is undefined.
```

### 이 부류의 결함이 개발에서 **구조적으로 안 보이는** 이유

`localhost`·`127.0.0.1`·`file://`은 **전부 보안 컨텍스트다.**
그래서 개발자는 이 결함을 만들 수는 있어도 **볼 수는 없다.** LAN 주소에서만 나타난다.

붙어 있던 `.catch()`도 한 번도 발화하지 않았다 — **throw가 동기적이라 promise가 생기기 전에 던진다.**
에러 핸들러가 있다는 사실이 에러가 보고된다는 뜻이 아니다.

`FEATURE_CHECKLIST`의 복사 항목이 이제 **평문 HTTP 사내망 주소에서의 시험**을 요구한다.

### 고치지 않기로 한 것과 확인한 것

- **행 선택 복사는 깨진 채로 남았다 — 의도적이다.** `clipboard.js`에 같은 우선순위 게이트가 있고,
  행 체크박스가 첫 데이터 셀 안에 있어 행을 고르면 **1셀 범위**로 기록된다. 사용자가 행 복사는 불필요하다고 판단했다.
- **엑셀 → 그리드 붙여넣기는 영향 없음을 확인했다.** Ctrl+V를 가로채는 코드가 없어 네이티브 paste 이벤트가
  `clipboardData` 핸들러에 그대로 도달한다.
- **Smart Paste(우클릭 전용)는 평문 HTTP에서 깨져 있다.** 다만 **시끄럽게 실패하고 아무것도 억누르지 않는다.**

## 검증

- 스위트 **630 passed** (기준선 608, **+22**).
- 신규 테스트 **22개 중 17개가 배포 소스에 대해 실패**함을 확인했다 — 바뀐 파일 하나만 stash해서 측정했다.
  **테스트가 결함을 실제로 잡는다는 증거는 통과가 아니라 이 실패다.**

## 아키텍처 영향

- 수집기 러너에 **명시적 실패 계약**이 생겼다. 핵심 원칙은 코드 주석에 한 줄로 박혀 있다 —
  *"could not check" must never be reported as "nothing is wrong".*
  `AUTO_UPDATE_GUIDE`의 판정 표가 9가지 경우를 열거하고, 그 표가 SSOT다.
- **수집기 스크립트가 평범한 파이썬 모듈과 같은 이름 해석 규칙으로 실행된다.** 종전에는 아니었다.
  가이드가 이 보증을 명시하므로, 수집기 작성자는 헬퍼 분리와 모듈 레벨 import를 제약 없이 쓸 수 있다.
- 그리드 복사 경로가 **하나로 줄었다.** `clipboard.js`의 `copy` 리스너가 유일한 구현이며,
  보안 컨텍스트에 의존하지 않는다.

## 그때 남아 있던 것

- **두 수정 모두 재기동해야 적용되고, 서로 다른 프로세스다** — 클라이언트 번들은 웹서버,
  수집기 러너는 auto-update 스케줄러. **`SYSTEM_RELOAD`는 워크스페이스 재스캔만 하므로 둘 다 반영하지 못한다.**
  이 커밋 시점에는 재기동 전이었다.
- **행 선택 복사는 깨진 채로 남아 있다.** 위에 적은 대로 판단에 의한 보존이지 해소가 아니다.
- **Smart Paste는 평문 HTTP에서 여전히 동작하지 않는다.** `navigator.clipboard.readText`를 쓰기 때문이고,
  이번 변경 범위 밖이다.
- **`print` 수집기의 2회 실행은 코드로 막지 않았다.** 가이드 경고로만 처리했으므로,
  부작용을 가진 print 수집기가 존재한다면 그 부작용은 계속 두 번 일어난다.
- **불투명한 수집기 구간은 여전히 계측되지 않는다.** 수집기가 오래 걸리는 것과 멈춘 것을 러너가 구분하지 못한다.
