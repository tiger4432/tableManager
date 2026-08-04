# 컬럼을 빼고, 대신 비교를 접었다

> **일자:** 2026-08-04 오후 | **선행:** `92b8d6f`(파생 컬럼 1단계 — **철회됨**) · `090c74a` · `7cea7fe`
> **담당:** 사용자(판정: 「물리 컬럼을 만들지 마라」) · server 구현
> **대상:** `server/notation_norm.py`(재작성) · `server/virtual_join_config.py` · `server/virtual_join_executor.py` · `server/database/crud.py`(훅·거부 제거) · `server/database/database.py` · `server/main.py`(신규 라우트) · `server/config_resolve_report.py` · `server/config/notation_rules.json.sample`(재작성) · **신규 `contracts/notation_fold/`** · `server/scripts/rederive_notation_norm.py`(**삭제**)
> **⚠️ [`20260804_123223`](./20260804_123223_one_lot_two_spellings_and_a_fold_that_shipped_switched_off.md) 항목이 서술한 「파생 컬럼에 저장한다」 모델은 이 라운드에서 **전부 철회**됐다. 그 항목은 `92b8d6f` 시점의 사실로만 읽을 것.

## 왜 물리 컬럼이 거절됐는가 — 취향이 아니라 실측이다

- **켜는 데 층이 셋이었다.** `table_config`가 물리 컬럼을 선언하고 → `notation_rules`가
  쌍을 선언하고 → `display_columns`가 가시성을 정한다. 층 사이의 실패가 **조용하다.**
- **파생 컬럼은 설계상 쓰기 거부였다.** 사용자에게 **보이는데 고칠 수 없는** 컬럼이고,
  CSV 추출에 따라 나가며, 누군가 `display_columns`에 넣는 순간 헤더가 맞는 입력 파일이
  `crud`에 닿아 그 거부가 **배치 전체를 실패시킨다.**
- **결정타 — 조인에서 쓰려면 `<컬럼>_norm`을 `join_key` 양쪽에 적어야 했다.**
  실측: `dt_log.core_lot`은 병합군 15개, `core_wafer_map.core_lot`은 **0개**다. 깨끗한
  쪽에 그것을 적을 이유가 있는 운영자는 없다. 그런데 **한쪽만 접힌 조인은 이미 맞고
  있던 매치를 조용히 잃는다.**

> 문법도 맞고 컬럼도 존재하는데 **결과만 틀린** 설정이 가장 나쁜 모양이다.

## 지금의 모양 — 선언은 한 줄, 접기는 조회 시점에 양쪽

```json
"columns": { "dt_log": { "core_lot": true } }
```

이 한 줄이 말하는 것은 **「이 컬럼의 표기는 정규화된 것이다」** 하나다. 파생 컬럼도,
`table_config` 수정도, 가시성 질문도, 채워 넣을 과거 행도 없다. 소비자
(`virtual_join_executor.join_onclause`)가 **비교의 양쪽을 SQL에서** 접는다.

**한쪽만 접는 인자가 존재하지 않는다.** `notation_norm.join_pair_rules`가 「어느 한쪽이라도
선언되면 양쪽」을 결정하고, 그 하나가 ON 절·인덱스 DDL·승인 게이트에 똑같이 실린다.
양쪽 규칙이 다르면 **합집합**이다 — 접기는 컬럼의 성질이 아니라 **비교의 성질**이다.

## 🔴 두 엔진, 한 답 — 이 라운드에서 제일 위험했던 자리

접기가 파이썬(참조 구현)과 SQL(실제로 도는 것) 양쪽에 존재하게 됐다. **「normalize」의
두 번째 철자**는 이 저장소가 반복해서 대가를 치른 결함이고, `notation_norm`이 자기 접기를
`canonical_key_value` **위에** 쌓은 이유가 바로 그것이었다. 한 층 아래에서 같은 함정이
열렸으므로, 같은 규율을 적용했다 — 다만 이번엔 **계약으로 채점**한다.

실측(운영 DB, PostgreSQL 18.3, 읽기 전용)이 설계를 두 번 바꿨다:

| 순진한 구현 | 실측된 불일치 |
|---|---|
| `[._\-\s]+` | 파이썬 `\s`는 29개 코드포인트, 이 서버의 `[[:space:]]`는 26개 — **U+001C~U+001F를 놓치고 U+180E를 더 잡는다.** 게다가 그 답이 DB의 ctype(`Korean_Korea.949`)에 달려 있어 **같은 제품의 다른 설치에서 또 달라진다.** |
| `upper()` | `upper('straße')`가 eszett를 남긴다 — 파이썬은 `'STRASSE'`, **길이가 바뀐다.** `ı`·`ﬁ`도 갈리고 `é`는 ctype에 따라 갈린다. |

→ 문자류는 **`\uXXXX`로 열거**(두 엔진 다 브래킷 안에서 이해한다 — 27벡터 실측), 케이스는
**ASCII 전용 `translate`**. 어느 엔진의 유니코드 테이블도 참여하지 않는다. `'g'` 플래그가
빠지면 첫 런만 접힌다는 것도 실측(`'WF.A_B 01'` → `'WF-A_B 01'`)이라 `fold_sql_text`
한 곳에만 적혀 있다.

**`contracts/notation_fold/`** — 43벡터 × 4 규칙조합 = 172 비교. 기댓값을 **기록**해 두고
두 엔진을 각각 그것에 채점한다(엔진끼리만 비교하면 **둘이 같은 방향으로 틀릴 때** 초록으로
남는데, 상수를 공유하는 구조에서 그건 가장 쉬운 실수다).

**빨개지는 것을 보였다.** 실제 구현의 패턴을 `[._[:space:]-]`로 되돌려 계약을 돌리자
`file_separator`·`unit_separator`·`mongolian_vowel_separator`가 **양방향으로** 빨개졌다
(파이썬이 접는데 PG가 안 접고, PG가 접는데 파이썬이 안 접는다). 되돌리자 다시 초록.
계약 안에도 세 가지 인위적 오철자(`DROPPED_G` 8건 / `UPPER` 4건 / `POSIX_SPACE` 6건)를
넣어 **코퍼스가 그것들을 실제로 잡는지**를 매 실행 확인한다 — 진짜 구현은 같은 루프에서 0건이다.

## 게이트도 함께 움직였다 — 그리고 이유는 성능이 아니다

접히는 조인 키에 평범한 UNIQUE 인덱스는 **게이트가 묻는 질문에 답하지 않는다.** 원본으로
서로 다른 두 행(`'CL-1'`, `'CL_1'`)이 접히면 한 값이므로, 컬럼에 UNIQUE가 있어도 **접힌
키로는 중복**이고 그 중복이 정확히 조인 팬아웃이다. 그래서 접히는 키에서는 **함수 인덱스**만
후보가 되고, `required_index_ddl`이 그 DDL을 그대로 찍는다(397자, 전부 ASCII, psql에 붙여
넣을 수 있다 — 제어문자를 날것으로 싣지 않으려고 `\uXXXX`를 쓴 이유가 여기서도 값을 한다).

운영 DB 실측: `dt_job_attribution`에는 `(dt_job)`을 덮는 평범한 UNIQUE 인덱스가 있고
식 인덱스는 하나도 없다.

    접지 않는 키 → 'uq_vjoin_dt_job_attribution_dt_job'   (통과 — 축이 살아 있다)
    접히는 키    → None, code=no_unique_index             (거부)

## ⚠️ 비싸다 — 감추지 않는다

| 측정 | 결과 |
|---|---|
| 접기 자체의 행당 비용 | **3.06 us/행** → 1,000만 행이면 스캔 위에 **약 31초** |
| 조인 (dt_log 8,700 × dt_job_attribution 120) | 3.1 ms → **151.6 ms (48.7배)** |
| 미리보기 GROUP BY (core_wafer_map 24,200행) | 6.1 ms → **73.4 ms (12.0배)** |

**함수 인덱스는 이 비용을 구해 주지 않는다.** 그것은 정확성(유일성) 요구지 성능 장치가
아니다 — 전수 조인에서 왼쪽은 어차피 행마다 접힌다. 다만 비싼 경로는 **두 번 opt-in**이다:
선언이 있고 **그 위에** 조인 컬럼을 대상으로 필터/검색/추출을 걸어야 `resolved_expression`이
만들어진다. 페이로드 경로(`execute_rule`)는 페이지당 1,000행으로 좁혀져 있어 약 3 ms다.

## 사라진 파생 컬럼의 대가를 갚는다 — 병합군 미리보기

운영자는 접힌 값을 그리드에서 **눈으로** 보던 수단을 잃었다. 그 손실은 흡수하는 것이 아니라
갚아야 한다. `GET /admin/config/notation/preview`가 갚는데, 형태가 원본→접힌값 **나열이
아니다**. 답해야 하는 질문은 「무엇이 무엇이 되는가」가 아니라
**「내 규칙이 서로 다른 두 로트를 합쳐 버리지 않았는가」**이므로, **병합군**(한 접힌 값에
원본 표기가 둘 이상 모인 그룹 + 원본 목록)이 먼저 온다.

접기는 **SQL에서, 조인이 쓰는 바로 그 식으로** 계산된다. 파이썬에서 접어 보여 주면
운영자가 신뢰하는 화면이 조인이 쓰지 않는 답을 보여 주게 되고, 그게 이 기능이 없애려는
「두 철자」 문제 그 자체다.

## 사라진 것들 — 은퇴이지 완화가 아니다

`apply_derivations`(쓰기 훅) · `crud.refuse_notation_derived_columns`(쓰기 거부) ·
`rederive` + `server/scripts/rederive_notation_norm.py` · `normalized_value` ·
`derivations_*`/`derived_columns_for` · 거절 코드 `would_rewrite_raw`·`key_column`.

뒤의 둘은 **쓰기를 지키던 문구**였고, 쓰기가 없어졌으므로 **주어가 사라진 것**이지
느슨해진 것이 아니다. 근거는 `notation_norm` 모듈 상단과 `crud`의 원래 자리에 문장으로
남겨 두었다 — 언젠가 접힌 값을 어디든 저장하게 되면 **둘 다 돌아와야 한다.**

## 맵 키는 건드리지 않았다

`canonical_map_key`를 접힌 값으로 돌리는 것은 별개의, 승인되지 않은 결정이고 **설정
스위치가 아니라 데이터 마이그레이션**이다. `wafer_map_metadata` 행이 **원본 신원**으로
등록돼 있어서, 그 순간 기존 `map_id`가 자기 메타 행과 어긋난다.

## 남은 것

- **운영자 문서 4종이 낡았다** — `guide/config/notation_rules_config.md`(§0·§1·§2 전체·
  §4.1·§4.2·§4.4·§5.2·§6 일부·§7 전체·§8 사망), `guide/CONFIG_GUIDE.md`(§1 표 행 + §5.6-quater),
  `guide/config/table_config.md`(§1 항목 + §5 `column_types`·`display_columns` 행),
  `guide/config/README.md`(표 행). **부분 패치가 아니라 재작성 대기.**
- **필터는 아직 접지 않는다.** 「보이는 것으로 검색한다」 계약과 전수 스캔 비용 둘 다
  걸려 있어 총괄 판정이 필요하다.
