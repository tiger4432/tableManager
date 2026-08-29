# v1 어휘 1,279줄이 죽었다 — 그리고 가드 하나는 «규칙의 두 번째 사본»에 대고 초록이었다

> **커밋:** `3d1b3803` (12:34) · `c0de3b89` (12:39) · `aed1876a` (12:50) · `4f85ef6b` (12:54)
> · `d77fa131` (13:17) · `5d7ed4f1` (13:26) · `c0497d45` (13:27) · `20ef9a7e` (13:28)
> · `f9846b58` (13:42) · `0f8b8e58` (13:48) · `1dfb1d97` (13:50) · `76a29111` (13:55)
> · `dfd484ce` (14:02) · `9cf25214` (15:13)
> | **일자:** 2026-08-27 낮
> **레인:** 서버(v1 은퇴 · 레인 A/B/C 분할)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 규칙의 사본이 둘이면 하나는 반드시 뒤처진다

`server/ledger/vocabulary.py`는 **1,279줄**(`git show dfd484ce~1:... | wc -l`로 확인)짜리
**닫힌 v1 어휘**였다 — `PREDICATES`(항목마다 시그니처) · `ENTITY_TYPES` · `OBJECT_KINDS` ·
`check_subject_keys` · `check_signature` · `check_predicate_declaration`,
그리고 `config/ledger_vocabulary.json` 확장 파일 로더.

```
모듈 임포트 줄   27  ->  «0»
vocabulary.<name> 속성 사용   261 -> 78
   (남은 78은 선언의 «vocabulary» 절 · 지역 변수 · docstring — 이 모듈이 아니다)
```

대신하는 것은 **선언 문서**이고, `ledger/config.load()`와
`server/ledger_api/entity_references.py`로 읽는다.

## 🔴 그리고 가드 하나가 «규칙의 두 번째 사본»에 대고 초록이었다

`76a29111`. `test_the_qualifier_names_the_walk_reads_are_the_ones_declared`는
`slot_map`이 `from`/`to`를, `has_wafer`가 `slot`을 선언한다고 단언했다. 물어본 곳은
**`vocabulary.PREDICATES`** — v1 낱말 목록이고 그 이름들을 여전히 들고 있었다.

**그런데 선언은 이미 그것들을 안 선언하고 있었다**(`slot_map` → `{event_type}`만,
`has_wafer` → `{}`). 동시에 `ledger_trace._slot_move`·`_wafer_slot`과
`ledger_trace.py:1749`의 SQL 은 **그 이름으로 읽고 있었다.**

```python
# server/tests/test_ledger_trace_contract.py
-    assert set(vocabulary.PREDICATES["slot_map"]["qualifiers"]) >= {"from", "to"}
-    assert "slot" in vocabulary.PREDICATES["has_wafer"]["qualifiers"]
+    from ledger import config as ledger_config
+    declared = {str(k).split("@", 1)[0]: v
+                for k, v in ((ledger_config.load() or {}).get("vocabulary") or {}).items()}
```

선언 쪽으로 겨누자 **빨개졌고, 일부러 빨간 채로 뒀다.** `4b499108`이 읽는 쪽과 그 시험을
지워서 닫았다.

## 저작 v1 이 함께 나갔다

`c0de3b89`이 저장 라우트 둘을 지워 **선언이 유일하게 남은 문**이 됐고, `4f85ef6b`이 그 저장이
미리보기하던 **dry-run 의 술어 반쪽**을 함께 은퇴시켰다(라우트 자체는 소스용으로 남는다).
`5d7ed4f1`이 배포되던 v1 어휘 확장 샘플을 지웠다 — **아무것도 그리로 폴백하지 않으므로.**
`3d1b3803`이 그 전에 **닫히는 문을 이름 대던 행들**을 고쳤다(그중 하나는 애초에 열릴 수 없었다).

## 🔴 세 커밋이 «자기 앞 커밋의 문장»을 철회했다

```
0f8b8e58   c0497d45 의 「ledger_explorer 가 키 순서를 선언에서 가져온다」를 철회
           -> 키 순서를 «아예 안 가져온다»
4f85ef6b   자기 정렬 블록의 「심볼 셋이 check_predicate_declaration 안에만 산다」를 철회
           -> PROJECTION_ONLY_WORDS 는 check_signature (vocabulary.py:998)도 쓰고,
              그건 라이브 ledger/gate.py:456 에서 닿는다
8dcf8ed5   d77fa131 의 폭발 반경을 철회
           -> tests/test_ledger_declared_kind.py 는 «결정적으로» 15 실패 / 5 통과였다
```

## 🔴 「레인 B 가 덮어쓰지 않고 기다린다」는 커밋이 «레인 C 의 삭제를 쓸어 담았다»

`20ef9a7e`의 제목은 「레인 C 에 커밋 안 된 작업이 공유 트리에 있으니 레인 B 는 덮어쓰지 않고
기다린다」이다. **그런데 이 커밋은 머지가 아니고**(부모 하나 `5f56db9b`) diff 는
`server/ledger_api/ledger_catalog.py`(213줄)와 `server/tests/test_ledger_catalog.py`(153줄)의
**삭제**다. 지시서 본문이 트리 상태를 「삭제 스테이지됨」으로 적고 있다 — **레인 C 의 삭제가
이미 스테이지돼 있었고 이 커밋이 그것을 쓸어 담았다.**

그 삭제는 **38분 전 `aed1876a`를 함께 버렸다** — 그 커밋이 방금 `ledger_catalog.entity_types()`를
`vocabulary.ENTITY_TYPES`에서 선언 쪽으로 옮겨 놓은 참이었다.

## 아키텍처 영향

- **`server/ledger/vocabulary.py`가 없다.** 어휘의 정본은 선언 문서 하나다.
- 저작 v1 라우트 둘과 배포용 v1 어휘 샘플이 사라졌다. **문은 선언 하나**다.
- 「선언에서 읽는다」가 **읽기 경로 전체**로 내려갔다 — 코드가 든 낱말 목록에 안 묻는다.

## 그때 남아 있던 것

- `9cf25214`가 남긴 것: **배포 샘플이 여전히 안 뜬다.** 모양이 낡았고(`packs`·`profiles`는
  2026-08-21 은퇴) 그것을 다시 쓰는 것은 총괄 소관이다.
- `d77fa131`이 명시했다 — 게이트 검사 둘을 없앴으므로 `screen_molecule`에 건네진 원자는
  **거기서 시그니처·신원 검사를 받지 않는다.**
- `ledger_catalog.py`와 그 시험은 **HEAD 에서 사라진 채**이고 이후 아무도 그 경로를 안 건드렸다.
