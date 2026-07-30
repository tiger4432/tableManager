# 업로드 경로 — 클라이언트가 정한 값 **둘**이 f-string에 그대로 들어가 있었다

> **일자:** 2026-07-30 13:19 | **커밋:** `0d4798a` | **담당:** Server PM | **검수 등급:** T3(자기 검증)
> **대상:** `server/main.py`(+33/−3) — 파일 하나, 테스트 0건
> **발견 경위:** 폴더 단위 인제션(`600b49d`) 설계 중 "업로드 경로에는 무슨 일이 생기나"를 훑다가 나왔다. 그 작업과 **독립된 선재 결함**이라 단독으로 착지했다.

## 배경 — 두 값 모두 요청이 정한다

`POST /tables/{table_name}/upload`는 저장 경로를 이렇게 만들고 있었다.

```python
orig_name, ext = os.path.splitext(file.filename)
unique_name = f"user({user})_{orig_name}_{uuid.uuid4().hex[:8]}{ext}"
file_path = os.path.join(target_dir, unique_name)
```

`os.path.splitext`는 **경로 구분자를 보존한다.** 그래서 `../../x.csv`는
`user(kim)_../../x_<uuid>.csv`가 되고 `..` 성분이 살아남는다. 접두 성분(`user(kim)_..`)이 `..`
하나를 흡수하므로 하나로는 못 나가지만, 그보다 많으면 `raws/` 밖을 가리킨다.

사거리에는 상한이 있었다 — `open(..., "wb")`은 **디렉터리를 만들지 않으므로** 이미 존재하는
디렉터리로만 쓸 수 있다. 그 집합에 `archives/`·`err/`·`config/`가 들어 있다.

그리고 문이 하나 더 있었다. **`user`는 쿼리 파라미터다** — `?user=../../..`가 같은 벡터다.
커밋 메시지는 이것을 *첫 분석에서 놓쳤다*고 스스로 적었다. 한쪽만 막았으면 같은 결함이
이름만 바꿔 남았다.

## 수리 — 두 겹, 그리고 **정본은 결과 검증**이다

```python
def _safe_component(raw: str) -> str:
    # 클라가 Windows이고 서버가 POSIX일 수 있으므로 두 구분자를 모두 접는다
    # (POSIX의 os.path.basename은 역슬래시를 구분자로 보지 않는다).
    s = str(raw or "").replace("\\", "/")
    s = os.path.basename(s).strip().strip(".")
    return s
```

역슬래시를 먼저 `/`로 접는 이유가 이 커밋의 핵심 관찰이다 — **클라이언트와 서버의 OS가 다를 수
있다.** POSIX에서 `os.path.basename("a\\b\\c.csv")`는 문자열 전체를 그대로 돌려준다. 입력을
서버 OS의 규칙으로만 읽으면 반대편 OS의 구분자가 통과한다.

그리고 판정은 입력이 아니라 **결과**가 한다.

```python
norm_target = os.path.normpath(os.path.abspath(target_dir))
norm_dest = os.path.normpath(os.path.abspath(file_path))
if (os.path.dirname(norm_dest) != norm_target
        or os.path.basename(norm_dest) != unique_name):
    raise HTTPException(status_code=400, detail=(...))
```

입력 필터만 두면 **다음에 구분자를 하나 놓치는 순간 뚫린다.** 결과 검증은 무엇이
빠져나왔는지와 무관하게 "목적지가 `target_dir`의 직접 자식인가"만 묻는다.

## ⚠️ 이 커밋이 근거로 든 선례가 20분 뒤에 삭제됐다

커밋 메시지는 같은 규율이 이미 `directory_watcher._resolve_flatten_dest`("must be a direct
child")에 있다고 적었다. **그 함수는 같은 날 `600b49d`에서 삭제됐다** — 승격(promote-to-root)
기계장치가 통째로 없어졌기 때문이다. 규율 자체는 살아남아 `_unique_dest`와
`relative_source_path`에 같은 문장으로 다시 적혀 있다. 이 커밋 시점의 인용 대상은
`_resolve_flatten_dest`였다는 것이 사실이고, 그 이름으로 지금 찾으면 없다.

## 검증 — 이 항목을 쓰며 다시 측정했다

커밋 메시지가 적은 표본을 `_safe_component` 로직만 떼어 다시 돌렸다.

| 입력 | 잔여 성분 | 저장 이름 | 직접 자식 |
|---|---|---|---|
| `../../../../etc/passwd.csv` | `passwd.csv` | `user(U)_passwd_<uuid>.csv` | ✅ |
| `C:\Users\x\a.csv` | `a.csv` | `user(U)_a_<uuid>.csv` | ✅ |
| `a/b/c.csv` | `c.csv` | `user(U)_c_<uuid>.csv` | ✅ |
| `.hidden.csv` | `hidden.csv` | `user(U)_hidden_<uuid>.csv` | ✅ |
| `?user=../../../..` | — | `user(Unknown)_…` | ✅ |
| `?user=a/b/c` | — | `user(c)_…` | ✅ |

전 표본이 커밋 메시지와 일치한다. `target_dir`을 벗어나는 경우는 없었다.

측정 중 하나 더 관측됐다: **파일명 전체가 구분자·점뿐이면**(`..`, `...`, `/`, `\\`) 잔여 성분이
빈 문자열이 되어 `user(U)__<uuid>`로 저장된다 — **확장자가 없다.** 결과 검증은 이것을 통과한다.
통과가 맞다(가드는 담기(containment) 가드이고 파일명 유효성 가드가 아니다). 이 커밋 시점의
사실로 적어 둔다: 인제션은 확장자로 레인을 고르므로, 그 이름은 `raws/`에 들어가되 어느 파서도
집지 않는다.

## 검증 수단에 대한 정직한 기록

**이 커밋에 자동 테스트는 한 줄도 없다.** `server/tests/` 어디에도 이 엔드포인트의 경로
정규화를 채점하는 케이스는 추가되지 않았고(`upload_file`을 부르는 테스트 자체가 없다),
커밋 메시지도 "verified against the sanitiser itself"라고만 적었다 — 즉 사람이 손으로 돌린
표본 검증이다. 이 항목의 위 표는 그 표본을 재현한 것이고, 회귀를 막는 것은 지금 코드의
결과 검증문 그 자체다.

## 그때 남아 있던 것

- 400 사유 문자열은 운영자에게 "파일명과 업로더 이름에서 경로 구분자를 제거한 뒤 다시
  시도하십시오"라고 말한다. 그런데 `_safe_component`가 이미 구분자를 접어 버리므로, 위
  표본 어느 것도 이 400에 도달하지 못했다 — 이 커밋 시점의 관측으로는 **1층이 통과시키는 것을
  2층이 거절한 사례가 없다.** 커밋 메시지는 이 관문을 "도달 불가"라고 주장하지 않았고,
  2층을 둔 근거는 1층이 언젠가 놓칠 것이라는 쪽이었다.
- 서버 스위트는 이 커밋 시점에 이 변경과 무관하다(엔드포인트 테스트 부재).
