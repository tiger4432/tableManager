# 반나절 동안 모든 트리 인제션이 `NameError`를 냈고, 로그는 두 가지를 다 틀리게 말했다

> **일자:** 2026-07-30 오후 | **관련 커밋:** `152d058` (4줄 추가 / 6줄 삭제) · 원인 커밋 `600b49d`(같은 날 오전) · 보드 기록 `269ac95` | **담당:** server-pm(발견·수리, 다른 라운드 중)
> **대상:** `server/parsers/directory_watcher.py`

## 무슨 일이었나

`600b49d`(폴더 구조 보존 인제션 — 중첩 파일을 제자리에서 인제스트)가 **이동 단계를 없앴는데,
그 단계가 만들던 변수 `moved`를 순회하는 마지막 디스패치 패스는 남았다.** 그래서
`_ingest_directory_tree`는 **그날 오전 이후 모든 디렉터리 트리 인제션에서 그 줄에 닿아
`NameError`를 냈다.** `600b49d`는 총괄이 검토하고 푸시한 커밋이다.

## 반나절을 살아남은 이유: 양쪽에서 다 안 보인다

**앞에서 안 보인다.** 일이 이미 끝나 있다 — `to_process`는 훨씬 위에서 **중첩 경로 그대로**
디스패치되고, 비워진 디렉터리도 이미 제거된다. 예외는 **할 일이 다 끝난 뒤에** 난다.

**뒤에서도 안 보인다.** `_tree_ingest_worker`가 그것을 잡아서 이렇게 남긴다 —
*"directory left in place; periodic sweep will retry"*.

> **이 문장은 두 가지를 다 틀리게 말한다.** 디렉터리는 남아 있지 않다(이미 지워졌다).
> 재시도할 것도 없다(작업은 완료됐다). 이 줄을 읽은 운영자는 **존재하지 않는 디렉터리를
> 찾으러 간다.**

**스위트도 같은 이유로 초록이다** — 예외가 밖으로 나오지 않는다.

## 수리: 고치지 않고 지웠다

```python
-        for _mtime, dest in moved:
-            self._handle_event(dest)
+        # NOTE: the flatten design ended here with a second dispatch pass over the
+        # files it had MOVED into the watched root. In-place ingestion has no move
+        # step — `to_process` is dispatched above at its nested path — so that pass
+        # is gone. Re-adding one over `to_process` would double-process every file.
```

**`to_process`로 고치는 것이 눈에 보이는 수리이고 틀린 수리다.** 그 파일들은 이미 제자리에서
디스패치됐으므로, 두 번째 패스는 **전부를 이중 처리한다.** 그래서 삭제했고, **그 루프가 무엇을
위한 것이었는지를 주석으로 남겼다** — 다음 사람이 친절하게 복원하지 않도록.

## 이 항목이 남기는 것

- **잡아서 로그하는 예외 처리기는 자기가 무엇을 잡았는지 모른다.** 여기서 그 처리기는
  「이동 실패」를 위해 쓰인 문장을 「이미 끝난 일 뒤의 프로그램 결함」에 붙였다. 그리고 그
  문장이 **결함을 반나절 동안 정상처럼 보이게 했다.**
- **다른 라운드를 하던 server-pm이 인접 코드를 읽다가 찾았다.** 같은 날 두 번째로, 읽던
  라운드보다 **읽고 있던 주변 코드가 더 값이 나간 경우**다.

## 그때 남아 있던 것

- 커밋 시점에 이 결함을 **잡을 수 있는 테스트는 추가되지 않았다.** 예외가 워커의 catch
  안에서 끝나는 이상 스위트는 초록이었고, 그 성질은 수리 뒤에도 그대로다.
