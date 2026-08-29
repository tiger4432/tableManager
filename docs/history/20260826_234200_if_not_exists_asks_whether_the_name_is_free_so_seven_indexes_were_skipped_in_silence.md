# `IF NOT EXISTS`는 「이 «이름»이 비었나」를 묻는다 — 그래서 인덱스 일곱이 조용히 건너뛰어졌고, 1,123.6 MB 가 159.7 MB 가 됐다

> **커밋:** `b27ae61d` (12:30) · `4bdbff36` (23:29) · `6e313b39` (23:42)
> | **일자:** 2026-08-26 낮~심야
> **레인:** 서버(스키마 · 인덱스)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 재건이 `ledger_events`를 개명했고, 인덱스 «이름»이 따라갔다

`CREATE ... IF NOT EXISTS <고정 이름>`은 **「이 이름이 비었나」**를 묻는다. 개명이 이름을
가져가 버렸으니 이름은 이미 «차 있었고», 그래서 **생성 일곱이 조용히 건너뛰어졌다.**
원자 **533,259**이 인덱스 여덟이 아니라 **하나**를 들고 적재됐다.

`b27ae61d`이 이름을 풀어 주고, 무엇보다 **판정 기준을 바꿨다:**

> 패리티 검사가 마지막에 돌고 인덱스 **정의**를 비교한다. 이름은 아니다 —
> **이름이야말로 개명이 가져갈 수 있는 것**이다.

즉 **존재가 아니라 유효성으로** 게이트한다.

## 🔴 그리고 유일 인덱스가 인덱스 바이트의 75%였다

`4bdbff36`. `uq_ledger_atom`이 원자당 **284.6 B**를 먹고 있었다.

```sql
-- 전 (server/scripts/shrink_uq_ledger_atom.py 헤더의 롤백 SQL)
(occurred_at, predicate, subject_type, subject_keys,
 COALESCE(object_payload, '{}'::jsonb), source_translator_ver, source_raw_ref)

-- 후
CREATE UNIQUE INDEX uq_ledger_atom ON ledger_events
  (occurred_at, predicate, subject_type,
   md5(subject_keys::text),
   md5(COALESCE(object_payload, '{}'::jsonb)::text),
   source_translator_ver,
   md5(source_raw_ref))
```

**1,123.6 MB → 159.7 MB (14%)**, 645,203행.

🔴 **유일성 의미는 «정확히 보존되지 않는다» — 충돌이 가능해졌고, 파일이 그렇게 적고 있다.**
`store.insert_atoms`가 타깃 없는 `ON CONFLICT DO NOTHING`을 쓰므로, 세 다이제스트가 모두
충돌하는 미래의 원자는 **거절이 아니라 «침묵 속에» 버려진다.** 제목의 「모든 컬럼을 유지한다」는
**모든 컬럼이 다이제스트를 통해 참여한다**는 뜻으로만 참이다.

## 뒤에 아무것도 없는 문과 비교할 것이 없는 비교기

`6e313b39`. `server/ledger/legacy_import.py`(31줄) · `shadow_parity.py`(241) ·
`test_ledger_shadow_parity.py`(153) = **425줄**이 통째로 나갔다. `vocabulary.py`는
**남았다** — 이 시점에 파일 12개 · 자리 19개가 그것을 읽는다.

## 아키텍처 영향

- 인덱스 패리티가 **이름이 아니라 «정의»**를 비교한다.
- `uq_ledger_atom`이 세 컬럼을 md5 로 다이제스트한다. 크기는 14%가 됐고 **충돌이 이론상 가능**해졌다.
- 레거시 임포트와 그림자 패리티 경로가 사라졌다.

## 그때 남아 있던 것

- 🔴 **`server/ledger/schema.py`가 여전히 옛 «뚱뚱한» 정의를 같은 이름 + `IF NOT EXISTS`로
  내보낸다.** `b27ae61d`이 그날 배운 규칙대로면 그것은 **조용히 건너뛰어질 것**이고, 따라서
  새로 만든 `ensure_schema`와 라이브 인덱스가 **서로 다른 정의**를 들게 된다. 두 커밋 어느
  쪽도 이 자리를 안 건드렸다.
- 🔴 `6e313b39`이 넣은 주석은 은퇴 날짜를 **2026-08-27**로 적었는데 커밋은 **2026-08-26 23:42**다.
- `1,123.6 MB → 159.7 MB` 수치는 스크립트 docstring 에 있고 **diff 가 생산한 것이 아니다.**
