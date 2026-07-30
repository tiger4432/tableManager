# 중첩 파일을 **제자리에서** 적재한다 — 그리고 나르는 것은 상대 경로 자신이다

> **일자:** 2026-07-30 13:39 | **커밋:** `600b49d` | **담당:** Server PM | **검수 등급:** T2
> **대상:** `server/parsers/directory_watcher.py`(+414/−…) · `server/parsers/advanced_ingester.py`(+426/−…) · `server/tests/test_nested_dir_ingestion.py`(신규 650줄) · `server/tests/test_filename_rules_declaration.py`(신규 414줄) · `server/tests/test_flatten_nested_dirs.py`(삭제 495줄)
> **관련:** 같은 파일 삭제를 사고로 먼저 스테이징한 `e14b1d0`과 그 되돌림 `b5f051c` — 별도 항목
> **관련:** 이 작업 분석 중 발견된 업로드 경로 결함은 `0d4798a`로 단독 착지

## 배경 — 폴더 이름이 데이터인데 flatten이 그것을 버리고 있었다

`raws/`에 떨어지는 폴더의 **구조가 정보다** — lot, 장비, 날짜가 폴더 이름에 들어 있다.
그런데 `_resolve_flatten_dest`는 **맨 basename을 먼저 시도**했으므로 하위 경로 접두어는
**이름 충돌이 났을 때만** 붙었다. flatten이 끝나면 중첩 경로는 `logger.info` 한 줄 말고는
어디에도 남지 않았다.

## 🔴 라운드 중간에 방향이 바뀌었고, 그 근거가 코드에 남았다

처음 안은 "접두어를 무조건 붙이고 구분자를 발명해 나중에 정규식으로 다시 뽑아낸다"였다.
사용자가 더 나은 안을 제시하면서 **취소됐다.** 그 판단의 근거가 지금 소스 주석에 있다.

```python
# NOT flattened into raws/ (superseded 2026-07-30). Promoting the files meant
# encoding the folder names into the filename with a separator and decoding them
# back out with a regex — a round trip through a string for information the
# callee already holds, since the parser is handed the full path and only then
# reduces it (`advanced_ingester.process_file`). Carrying the path directly also
# removes the separator problem entirely: "/" cannot occur inside a folder name,
# so the path is inherently unambiguous where an invented separator was not.
```

두 논거가 서로 독립이라는 점이 이 기록의 요점이다.

1. **왕복이 불필요했다.** 파서는 이미 전체 경로를 받고 **그 다음에** 축약한다. 즉 폴더 이름을
   파일명에 인코딩하는 것은 피호출자가 **이미 들고 있는 정보**를 문자열을 경유해 되돌려 주는
   일이었다.
2. **경로는 *본래* 구조적이고, 발명한 구분자는 *만들어서* 구조적으로 해야 한다.** `/`는
   디렉터리 이름 안에 들어갈 수 없다. 그래서 경로는 발명한 구분자도, sanitizing도, 경계
   표식도 필요 없다. 발명한 구분자는 그 성질을 **sanitize로 확보해야** 하고, 그것이 실패하는
   날 값이 조용히 잘린다.

**설정 키는 `flatten_nested_dirs`로 남았다** — 이름을 바꾸면 운영자가 이미 걸어 둔 off 스위치가
조용히 무력화된다. 로그 문장만 "파일이 적재되지 않는다"로 바뀌었다.

## 변경 — `directory_watcher`

`request_flatten`/`_flatten_directory`가 `request_tree_ingest`/`_ingest_directory_tree`로
바뀌었다. 정지된 트리를 걸어 **각 파일을 진짜 중첩 경로 그대로** 기존 이벤트 경로에 던지고
(레인 라우팅 → 파서 → 체크포인트/dedup → archives/·err/), **비게 된 디렉터리만** 지운다.
승격 기계장치(`_build_collision_name` · `_resolve_flatten_dest` ·
`_sanitize_flatten_component` · `FLATTEN_SEP`)는 **전부 사라졌다** — 이 커밋의 파일에서
그 이름들은 0회 등장한다.

**선언이 보는 문자열**은 새 정적 메서드가 만든다.

```python
@staticmethod
def relative_source_path(abs_path: str, root: str) -> str | None:
    ...
    rejoined = os.path.normpath(os.path.join(os.path.abspath(root), rel))
    if os.path.normcase(rejoined) != os.path.normcase(os.path.normpath(os.path.abspath(abs_path))):
        return None
    return rel.replace(os.sep, "/")
```

두 결정이 박혀 있다. **절대 경로가 아니라 상대**여야 한다 — 절대 경로는 기계의 디렉터리 배치를
선언에 끌고 들어와 같은 규칙이 dev↔운영에서 매칭을 멈춘다. 그리고 **어느 플랫폼에서도 `/`**여야
한다 — Windows의 `os.sep`는 역슬래시이고 JSON 정규식에서 운영자가 네 글자로 써야 한다.

담기 판정은 **결과 기반**이다(문자 블랙리스트는 `C:foo`를 놓치고 `..foo`를 과잉 거절한다).
답이 `root` 아래 같은 파일로 다시 조립돼야 하므로 `..` 성분도 다른 드라이브도 살아남지 못한다.
트리 워크는 이 검사를 통과하지 못하는 엔트리를 거절한다 — **junction이 그 경로로 도달하는
방법**이다.

## 변경 — 보관(archive)이 **조건부**가 됐다

```python
def is_managed_source(self, file_path: str) -> bool:
    """True when this handler OWNS the file and may move it. ...
    The guard lives here, at the two move primitives, and not at their call
    sites: the same defect otherwise recurs once per caller ..."""
    return self.relative_source_path(file_path, os.path.abspath(self.raws_path)) is not None
```

이 술어가 **두 이동 프리미티브**를 막으므로 모든 호출자가 한 번에 덮인다 — 성공 보관,
dedup-skip 보관, err 이동, 재시도 경로. 호출부마다 막으면 같은 결함이 **호출자 수만큼 재발한다.**

외부 읽기전용 트리의 파일은 옮기지도, err로 보내지도, 지우지도 않는다. 적재 기록은 원래 경로를
가리키고 내용 서명은 여전히 dedup에 답한다. 외부 파일의 반복 dedup-skip은 **조용하다** —
스윕이 구성상 그것을 영원히 다시 찾을 것이므로, 스윕마다 로그 한 줄이면 실제 이벤트가 전부
묻힌다.

## 변경 — 보관 충돌이 실제로 위험해졌다

```python
candidates = [filename, f"{base}_{ts}{ext}"]
candidates.extend(f"{base}_{ts}_{n}{ext}" for n in range(2, limit))
```

제자리 적재는 **다른 폴더의 같은 이름 파일들을 일상적으로 보관한다.** 종전의 `_<epoch>` 단발
시도는 같은 초에 끝나는 두 파일에서 충돌했고, POSIX에서는 `shutil.move`가 앞 보관을
**덮어썼고** Windows에서는 예외가 나 파일이 `raws/`에 영구히 걸려 매 스윕이 같은 실패를
반복했다.

파서에는 `self.rel_path` **속성**으로 전달된다 — `parse(path)` 시그니처를 넓히지 않는다.
그 시그니처는 사용자 스크립트가 상속한다.

## 변경 — `filename_rules`가 침묵을 그만뒀다

`extract_path_metadata(subject)`가 **상대 경로 전체**에 매칭한다. 형제 `path_rules`를 만들지
않은 이유가 명시돼 있다 — **경로가 파일명을 포함하고**, 같은 문자열에 대한 두 번째 채널은
부재·모호·필수 기계장치를 똑같이 다시 필요로 한다. `process_file(path, rel_path=None)`은
basename으로 폴백하므로 **기존 호출자는 그대로다.**

그리고 상태마다 이름이 붙었다(미상 ≠ 빈칸).

| 상태 | 종전 | 지금 |
|---|---|---|
| 선언했는데 아무것도 매칭 안 됨 | 조용히 빈칸 | `no_match` — 파일마다 계수·로그 |
| 패턴이 **서로 다른 값 둘**에 매칭 | `re.search` 첫 히트 | `ambiguous_reference` — **거절** |
| 매칭됐지만 캐스팅 실패 | None 저장(= 빈칸) | `cast_failed` |
| `required`인데 없음 | (개념 부재) | 파일 전체 거절 (기본 false) |

`ambiguous_reference`는 `enrichment_analysis.CLS_AMBIGUOUS`와 **같은 단어**다 — 한 상태에 한
어휘, 동의어를 두 번째로 만들지 않는다.

**잘못된 선언은 LOAD 시점에 이름 있는 사유로 실패한다**(`RuleDeclarationError`,
`ontology_config`의 미지 키 거절을 따른다). 캡처 그룹 없는 정규식은 파스 시점의 `IndexError`가
아니라 선언 오류다. 검사는 `rules`·`header_rules`에도 걸렸다 — **같은 구멍이 거기에도 있었다.**

## 변경 — 우선순위가 창발이 아니라 **선언**이 됐고, 채우기 절반이 고쳐졌다

사용자 판정(**"파일이 정본"**)에 따라 `header < filename < row`다. 그런데 순서만으로는
절반밖에 안 됐다.

```python
merged = {**header_metadata, **filename_data, **row_data}
for col in self._fill_merge_cols:
    if merged.get(col) is not None:
        continue
    ...
```

`parse_line`이 **모든 선언 컬럼을 모든 행에 대해** 내보내고 매칭 안 된 규칙에는 `default`
(보통 None)를 쓴다. 그래서 평범한 dict 병합은 **그 컬럼에 대해 침묵하는 행**이 경로에서 온 값
위에 None을 쓰게 만들었고, 판정의 "채우기" 절반이 아예 일어나지 않았다. **None은 `parse_line`의
부재 표식이고 값이 아니다** — 선언된 non-None `default`는 값이므로 여전히 이긴다.

비용도 제한돼 있다: 채우기 패스는 `_fill_merge_cols`(둘 이상의 출처가 만들 수 있는 컬럼)만
돌고, 같은 컬럼이 두 계열에 선언되지 않으면 비어 있다 — **평상 경로는 정확히 오늘의 dict
병합이다.**

행이 경로와 다르면 **계수한다**(`file_overrides_path`), 막지 않는다. 경로가 파일 자신의
헤더를 이기는 경우는 **따로** 보고된다(`path_overrides_header`) — "파일이 정본" 판정은
파일의 *행* 대 경로에 대해 내려졌고, 그것이 헤더 메타데이터까지 확장되는지는 이 커밋 시점에
선언 소유자에게 열린 질문이다.

## 검증

- **1432 passed.** 이 항목을 쓰며 HEAD에서 재실행 —
  `conda run -n assy_manager python -m pytest server/tests/ -q` → **1432 passed / 4분 33초**,
  커밋이 주장한 수와 일치.
- 각 케이스가 주입으로 red임이 증명됐다(**14회 주입, 전부 red**).
- 신규 테스트 20건이 제자리 디스패치 위치, 상대 경로 형태와 탈출 거절, 파서의 `rel_path`,
  외부 소스 4경로 전부, 보관 충돌 안전을 덮는다. 선언 계약은
  `test_filename_rules_declaration.py`가 따로 덮는다.

## 그때 남아 있던 것

- **`path_overrides_header`는 보고만 되고 해소되지 않았다** — 판정이 아직 내려지지 않은 상태다.
- **외부 소스의 반복 dedup-skip은 의도적으로 조용하다.** 스윕은 그 파일을 영원히 다시 찾고,
  이 커밋 시점에 그것을 멈추는 기제는 없다.
- `_unique_dest`의 상한은 1000이고, 그 이상 충돌하면 `None`을 돌려준다 — 이 커밋 시점에 그
  경로의 호출자 처리는 이동을 포기하는 것이다.
- 삭제된 `test_flatten_nested_dirs.py`는 **이 커밋에서 두 번째로** 지워졌다. 첫 번째는
  `e14b1d0`이 사고로 스테이징한 것이고 `b5f051c`가 되돌렸다.
- `0d4798a`가 근거로 인용한 `_resolve_flatten_dest`("must be a direct child")는 이 커밋에서
  사라졌다. 같은 규율은 `_unique_dest`와 `relative_source_path`에 같은 문장으로 남아 있다.
