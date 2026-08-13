# The refusal that failed to parse looked exactly like one that fired

**Date:** 2026-08-13 14:07 · **Domain:** Server (계획 테이블 은퇴 / 마이그레이션) · **Status:** 착지 — `c0fb735`

> ⚠️ **DROP은 격리 `assy_qa`에서만 실행됐다.** `assy_manager`는 직후 재확인했고 여전히 두
> 테이블을 들고 있다. **운영은 아직 떨궈지지 않았다.**

---

## 배경 — 코드는 2026-07-27부터 기다리고 있었다

`map_doe`와 `map_doe_source`는 M2.6에서 마지막 쓰는 쪽을 잃었다 — DOE가
`map_split_registry` 행 자체가 되면서(값 하나 = 행 하나). `product_tables.py`가 자기 주석에
그렇게 적고 있었다: *「DROP TABLE needs the operator's approval, no new consumers」*.
오늘 제품 소유자가 승인했다. 두 개발 데이터베이스 모두 **0행.**

## 드릴이 «성공으로 보고됐을» 결함을 잡았다

전진 마이그레이션의 거절 메시지가 처음엔 **인접한 `E'...'` 리터럴들**로 지어졌다.
plpgsql의 `RAISE`는 **문자열 리터럴 «하나»만** 받고 SQL 리터럴 접합을 거부한다. 그래서 그
파일은 **파싱되지 않았다.**

**밖에서 보면 그것은 작동하는 가드와 구별되지 않는다** — 빨간 글씨, 0 아닌 종료 코드,
아무것도 안 떨어짐. 두 팔을 다 발사해 보지 않았다면 **「가드가 거절했다」로 출하됐을 것이다.**

```sql
IF COALESCE(n_doe, 0) > 0 OR COALESCE(n_source, 0) > 0 THEN
    -- 인접 리터럴 여러 개가 아니라 dollar-quote 하나: plpgsql의 RAISE는 단일
    -- 문자열 리터럴만 받고 SQL 리터럴 접합을 거부한다 (이 파일의 첫 초안이
    -- 정확히 그것이었고 파싱되지 않았다).
    RAISE EXCEPTION $msg$REFUSING TO DROP - the retired plan tables are NOT empty in "%".
```

그래서 가드를 버리는 데이터베이스 위에서 **다섯 상태로 드릴했다**: `map_doe`에만 행 하나,
`map_doe_source`에만 행 하나(**OR의 둘째 팔은 따로 태웠다 — OR은 안 태운 팔을 감춘다**),
둘 다 비지 않음, 둘 다 빔, 그리고 드롭 후 재실행. **거절 / 거절 / 거절 / 드롭 / 멱등.**

가드와 DROP은 **의도적으로 한 `DO` 블록**에 산다 — `psql`은 최상위 문장마다 자기 트랜잭션을
쓰므로, 가드가 별도 블록에 있으면 **빨간 글씨를 찍고 아래의 DROP은 그대로 실행된다.**

## 재생성 경로는 추론이 아니라 «발사»로 닫혔다

드롭을 되돌릴 수 있는 메커니즘이 둘 있었고, **둘 다 빈 새 데이터베이스에 대고 돌렸다.**
설치기는 이제 정확히 `wafer_map_metadata` · `map_split_registry` · `valid_die_ref`만 만든다.
부팅은 29개 테이블을 만들고 그 안에 `map_doe*`는 없다 — `map_split_registry`가 대조군으로
존재한다.

## 선언은 스키마가 아니다

역방향의 컬럼 집합은 **삭제되는 선언에서 옮겨 적지 않고** 라이브 데이터베이스의
`information_schema`에서 읽었다. 물리 테이블은 어떤 선언도 언급하지 않는 **범용 컬럼 일곱**을
들고 있었고, `band_seq`/`qty_total`/`qty`는 정수가 아니라 **`double precision`**이었다.

## 이 변경보다 오래 살 세 발견

- **`assy_manager`에 고아 레이어링 행이 있다 — 오늘 이전부터 고아였다.**
  이 테이블 이름들로 범위 잡힌 `cell_sources` 110+100, `cell_overwrites` 110+100,
  `audit_logs` 288+229행이 있는데 베이스 테이블은 비어 있었다. 무언가가 **cascade 없이**
  테이블을 비웠다. 마이그레이션은 그것을 **세고 보고하며 아무것도 지우지 않는다** —
  `audit_logs`는 이력이라 서술 대상보다 오래 살아야 하고, 사용자가 핀한 셀을 지우는 것은
  별개의 결정이다.
- **`idx_map_doe_ref_map` / `idx_map_doe_source_ref_map`은 어느 데이터베이스에도 존재한 적이
  없다** — 선언돼 있었는데도. 그 존재 게이트는 **영원히 `[skip]`을 찍었을 것이고, 영구
  skip은 운영자에게 skip을 무시하도록 가르친다.**
- `crud.py:828`과 `test_stored_text_normalization.py:212`가 `map_doe.mat_*`를 말한다. 그
  컬럼들은 `map_split_registry`에 있고 `map_doe`는 가진 적이 없다. **두 주석 다 사라진
  테이블을 지목하면서 «동시에» 엉뚱한 쪽을 가리킨다.** 조용한 때로 남겼다 — `crud.py`가
  레인 넷의 쓰기로 뜨겁다.

## 의도적으로 남긴 것

`migrate_map_meta_to_wafer_id.py`는 여전히 두 테이블을 탐색한다(`_table_exists`로 게이트됨).
**운영은 아직 안 떨궈졌고**, 운영의 사본이 비어 있지 않다면 맵 id 개명 도중 그것을 말해 줄
유일한 장치가 그 탐색이다. 운영자가 드롭을 돌리면 무해한 「absent」 두 줄이 된다.

클라이언트의 `map_doe_draft::` localStorage 네임스페이스는 접두사를 공유할 뿐 이 테이블들이
아니다. **가정이 아니라 확인.**

## 그때 남아 있던 것

- 7파일 +271/-208.
- 격리 `assy_qa`: 둘 다 **사라졌고** 남은 인덱스 0. `assy_manager`는 **그대로 들고 있다.**
- 운영 데이터베이스는 손대지 않았다 — 절차는 `e662ff9`의 운영 런북으로 들어갔다.
- 검증: `test_install_product_tables.py` 39 passed; 이송계획·config 백업·미선언 컬럼·
  저장 텍스트까지 211 passed; 맵 메타·valid-die·prod-import 86 passed.
