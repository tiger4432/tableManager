# 이미 성립하는 자리에서는 전제가 «안 보인다» — 손으로 깐 확장, 이름만 보는 인덱스, 아무도 못 부르는 천장

> **커밋:** `743117ef` (10:26) · `1c0925ca` (10:46) · `4dd6a84d` (10:59)
> | **일자:** 2026-08-29 오전
> **레인:** 서버(원장 스키마 · 걷기 라우트)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 부류 — 셋 다 «오류가 안 나는» 결함이다

같은 오전에 착지한 셋은 서로 다른 파일이지만 **하나의 부류**다.

```
743117ef   모듈이 「6000 이 정착점」이라 «자기 주석에» 적어 뒀는데 라우트가 3000 에서 막았다
1c0925ca   코드가 적은 인덱스 정의와 «라이브가 들고 있는» 정의가 다른데 아무도 안 비교했다
4dd6a84d   확장을 «손으로» 깐 상자에서는 그것이 없다는 사실이 «영원히 안 보인다»
```
셋 다 **성립하는 자리에서 재면 초록**이고, **성립하지 않는 자리에 갔을 때 처음** 틀린다.

## ① 「더 없다」와 「그만큼 못 묻는다」가 같은 답을 냈다

`743117ef`. 라우트가 `edge_limit` 상한을 **리터럴 3000** 으로 막고 있었다. 그런데
`ledger_subgraph` 모듈은 **6000 을 「엣지가 더 이상 벽이 아닌 지점」으로 재서 자기 주석에
적어 두었다.** 즉 **모듈이 이름 댄 수를 아무도 요청할 수 없었다.**

```
씨앗 wafer SYN-BW-101-16 · hops=6 · node_limit=1000 · direction=both
   edge_limit 없음   nodes  754 · edges 1200 · hops_reached 2 · 절단 claims+edges
   edge_limit=3000   nodes 1000 · edges 3000 · hops_reached 2 · 절단 claims+edges+nodes
   edge_limit=6000   nodes 1000 · edges 3324 · hops_reached 2 · 절단 claims+nodes
```
🔴 **6000 은 「더 큰 절단」이 아니라 «정착점»이다** — 그래프가 3324 에서 스스로 멈추고
**엣지 절단 표지가 꺼진다.** 남아서 무는 것은 노드와 주장이다.

고친 방식이 요점이다: `le=3000` 을 `le=6000` 으로 «다시 적지» 않고
**`le=MAX_EDGE_LIMIT`** 로 모듈에서 «읽는다». 두 수가 다시 어긋날 자리를 없앤 것이다.
기본값 1200 은 그대로다 — **움직인 것은 천장이지 바닥이 아니다.**
`tests/test_ledger_subgraph.py` **11 passed · 1 skipped**.

## 🔴 ② `IF NOT EXISTS` 는 «이름»을 묻지 «정의»를 묻지 않는다

`1c0925ca`. 코드의 `DEDUPE_COLUMNS` 는 jsonb 컬럼 둘과 `source_raw_ref` 를 **그대로** 이름
대고 있었는데, 라이브는 `4bdbff36` 이후 셋 모두에 **`md5()`** 를 물려 왔다 — 그 변경이
이 인덱스를 **1,123.6MB → 159.7MB** 로 줄인 것이다.

```
CREATE UNIQUE INDEX IF NOT EXISTS  ->  「그 «이름»이 비었나」만 묻는다
                                       «정의가 같나»는 «절대» 묻지 않는다
=> 라이브는 조용히 건너뛰었고, 새 배포는 조용히 «뚱뚱한 쪽»을 만들었을 것이다
   상자 둘 · 인덱스 둘 · 오류는 «어느 쪽에도 없다»
```

```python
DEDUPE_COLUMNS = (
    "occurred_at", "predicate", "subject_type", "md5(subject_keys::text)",
    "md5(coalesce(object_payload, '{}'::jsonb)::text)", "source_translator_ver",
    "md5(source_raw_ref)",
)
```
**바뀐 것은 코드의 «문장»뿐이다** — 인덱스를 떨어뜨리지도 다시 만들지도 않았고, 튜플 길이가
여전히 7 이라 `envelope.py` 의 동일성 거울과 그 시험은 손대지 않았다.

⚠️ 그리고 그 사실이 «무엇을 참으로 만드는지»를 주석이 받아 적었다 —
**유일성이 값이 아니라 «다이제스트»에 걸린다.** `insert_atoms` 의 `ON CONFLICT DO NOTHING`
은 대상이 없으므로, 충돌하면 **한쪽이 말없이 버려진다.** 가드는 안 달았다. 이 규모에서는
값어치가 없고, **알아야 할 사실**이지 코드에 넣을 규칙이 아니라는 판단이다 —
그 실패는 **「도착한 적 없는 원자」처럼 보일 것**이기 때문이다.

```
게이트 1   빈 DB 에서 만든 스크래치 인덱스 DDL 과 라이브 DDL 을 «문자열 그대로» 비교 -> EQUAL
게이트 2   라이브에 ensure_schema -> 인덱스 «9 전 · 9 후», 추가·삭제·변경 «0»
표 투영 상수 셋 삭제   심볼로 재세었다 (server · client2 · contracts · docs · task)
                    선언 밖의 히트는 전부 「고아다」라는 «산문». getattr·조립 호출 «없음»
수집 4,256 그대로. test_ledger_l1_unit.py 의 빨강 «1» 은 두 파일을 HEAD 로 되돌려도 «동일»
```

## 🔴 ③ 빈 DB 에서 스키마가 «안 세워졌다» — 라이브에서는 영원히 안 보인다

`4dd6a84d`. `ensure_schema` 가 **빈 데이터베이스를 만들지 못했다.** 원자 표가 쓸 수 있게
되기도 전에 `gin_trgm_ops` 에서 죽었다. 라이브 상자에서는 **누군가 언젠가 손으로 `pg_trgm` 을
깔았고 아무도 기록하지 않아서** 그 사실이 보이지 않았다.

```python
def _ensure_trigram(cursor):
    """Install `pg_trgm`, because one of `INDEXES` cannot be built without it.

    🔴 MEASURED 2026-08-29 ON AN EMPTY DATABASE: `ensure_schema` did not survive one.
    ... the live box never showed it because the extension was installed
    there by hand at some point nobody recorded. Exactly the shape of the index defect
    fixed in the same round: a premise that is invisible wherever it already holds.
    """
```
⚠️ **권한이 없으면 «이름을 대고» 거절한다.** `CREATE EXTENSION` 은 응용 롤에 없을 수 있는
권한을 쓰고, 거기서 조용히 넘어가면 **방금 고친 바로 그 결함(보이지 않는 반쪽 스키마)을
한 층 아래에서 다시 만드는 것**이다.

증명 방식이 요점이다 — **버팀목을 «빼고» 쟀다.** 프로브 DB 가 확장을 미리 깔지 않게 하고
`ensure_schema` «만»으로 빈 상태에서 세웠더니, `uq_ledger_atom` 이 **라이브와 문자 단위로
동일**했다. 라이브 대조는 **9 전 · 9 후**.

## 시험 하나를 «깨우고» 하나는 «지우지 않았다»

같은 커밋의 판단 두 갈래다.

```
timezone 단언   선언이 그 값을 «옮겼다»    -> read.occurred_at.timezone 로 «재조준»
                                          소스 «14» 가 전부 Asia/Seoul
format   단언   sample 에 `format` «0회»  -> 값이 «옮긴» 게 아니라 «선언을 떠났다»
                                          모든 소스가 config.DEFAULT_OCCURRED_AT_FORMAT 로
                                          떨어지고, 2026-08-13 판정이 이제 «거기 혼자» 산다
                                          -> 지우지 «않고» 그 상수를 못 박도록 재조준
                                          + 소스가 다시 format 을 선언하면 «터지는» 가드
```
🔴 **「선언에서 사라졌으니 시험도 지운다」가 아니다.** 값이 «옮긴» 것과 «떠난» 것은 다르고,
떠난 값의 기본값은 **그 뒤로 아무도 안 지키는 자리**가 된다. 지시서가 이 건은 «판단하지 말고
보고하라»고 했기 때문에 보고서에 판단 사항으로 표시됐다.

`-k "schema or subgraph or l1_unit"`: **209 passed · 4 skipped**.

## 아키텍처 영향

- 걷기 라우트의 엣지 천장이 **모듈 상수를 읽는다** — 두 수가 어긋날 자리가 없어졌다.
- 원장 유일 인덱스의 코드 정의가 **라이브가 들고 있는 정의와 같아졌다.** 유일성은
  **다이제스트**에 걸리고, 충돌은 **말없이 버려진다**는 사실이 주석에 남았다.
- `ensure_schema` 가 **빈 데이터베이스에서 스키마를 세운다.** 확장이 없으면 **이름을 대고**
  거절한다.

## 그때 남아 있던 것

- `test_ledger_l1_unit.py` 의 빨강 «1» 은 이 라운드의 것이 아니다 —
  두 파일을 HEAD 로 되돌려도 **똑같이** 실패했고, 두 파일이 건드리지 않는 선언 키
  (`occurred_at_timezone`)에서 났다.
- 인덱스 다이제스트 충돌에 **가드는 없다.** 규모 판단이고, 주석이 그 사실을 들고 있다.
- `format` 재조준은 **판단 사항으로 표시된 채** 넘어갔다 — 이 시점에 확정 판정은 없었다.
- 게이트 수(9 전/9 후 · 1,123.6MB → 159.7MB)는 **이 상자의 데이터베이스**에서 잰 것이다.
