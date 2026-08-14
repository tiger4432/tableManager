# Two planted factors, each a decoy in the other's contrast

**Date:** 2026-08-14 09:55 · **Domain:** Server (원장 — 답안지·형제 API) · **Status:** 착지 — `849de00`, `9d1d44e`

---

## 가상 소스 확장 (`849de00`)

어휘 7 → 9: `processed_with`(예약 술어 첫 사용)와 `has_param`. `Recipe`는
`(recipe, rev)` 키의 발행 엔티티 — 리비전은 편집이 아니라 등록이다. 답안지가 양
방향·양 kind로 통과했다:

```
void   planted  recipe_rev@BONDING=SYN-RCP-BOND@5   0.123 vs 0.061   2.015x
       decoy    chamber@BONDING=CH-A                0.696 vs 0.697   0.998x
delam  planted  eqp@MOLDING=SYN-MLD-03              0.628 vs 0.159   3.945x
       decoy    recipe_rev@BONDING (void의 인자)     0.101 vs 0.100   1.011x
```

교차 kind 두 행이 곧 일반화 증명이다 — 각 kind의 인자가 상대 kind의 대조에서 평평하게
나온다. 그리고 `chamber=CH-A`가 채점할 가치가 있는 미끼다: void 패키지의 69.6%가
공유하고 clean도 69.7%가 공유한다 — 교집합 뷰는 발견으로 보고하고 대조가 죽인다.
측정-이긴다-설정값은 랭킹 코드가 필요 없었다 — `ledger_trace.py` 무접촉, 설정값
원자의 페이로드 플래그를 해소기가 이미 읽는다. 증거는 출하 코드의 149/149 합의가
아니라 **계급 무시 mutant의 149/149 불일치**다. `server/finding_kinds.py`가 kind
레지스트리가 됐고 `DEFAULT_KIND = "void"`가 코드의 유일한 리터럴 kind 이름이다.
`observed_by`가 곧 분모: 빈 배열은 「분모 없음」, 부재는 로드 시 거절. `delam_obs`는
grade를 갖지 않는다 — pass/fail은 `area > threshold`이고 threshold는 레시피
파라미터라 저장된 평결은 이력을 재판정 불가로 만든다.

## 형제 API (`9d1d44e`) — 표본 크기를 들어야 했던 비율

`GET /api/ledger/siblings?finding=&mode=intersection|contrast`. 둘이 아니라 **한
엔드포인트**: `mode`는 랭킹·필터만 바꾸고 행 모양은 동일 — 미끼가 교집합 정상에 rate
1.0으로 앉고 대조에서 평평해지는 «차이»는 두 답이 같은 모양일 때만 읽힌다. 세 갈래
분할 상시 동반: found / clean_scanned / never_scanned — clean은 런 행에서만 지어져
스캔 안 된 패키지가 구조적으로 못 들어간다. 라이브 픽스처에서 never-scanned는
280,000 대 clean 28,101 — 접으면 모든 enrichment가 1로 끌린다. 분모 없음은 `0`이
아니라 `null` + 사유 토큰, 대조는 「분모 없음 — 대조 불가」를 사유 딸린 200으로.

계약에서 한 가지 변경을 측정이 강제했다: **대조는 맨 비율이 아니라 95% Katz 구간의
하한으로 랭킹한다.** 점추정으로는 `finding=delam`이 랏별 1.7–1.9x 행 100개(각 ~108
패키지)를 돌려 나머지를 묻었다 — 하한이 1.5 아래로 떨어지며 올바르게 평평하게 읽힌다.
**표본 크기 없는 비율은 분모 없는 율만큼 못 읽는다 — 같은 규율, 한 층 위.**

라이브 데이터가 유닛 테스트가 못 잡을 결함 둘을 잡았다: delam 스캐너의 레시피가
`finding=void` 답에 새는 것, 런 팬아웃이 한 패키지를 여럿으로 세는 것. 지연 37 s →
2–4 s(행 생성자의 `count(DISTINCT)`가 밀집 정수 id가 되며).

## 그때 남아 있던 것

- 이음새 둘이 미해결로 보고됐다: 다른 레인이 2분 뒤 같은 경로에 `finding_kinds.py`를
  썼다 — 그쪽이 SSOT이고 이 엔진이 소비하되, `population_ctes()`에 철자 둘(SQLAlchemy
  대 psycopg2+window)이 생겼고 자기 docstring은 하나여야 한다고 말한다. `observed`는
  이 시점 `PREDICATES`에 아직 없다 — 어휘 판정이라 동결 7을 놔뒀다(당일 `530fda6`
  라운드에서 10으로 확장).
- `849de00` 잔여: `delam_obs`에 비즈니스 키 UNIQUE 없음(R2 감사의 유일 위반),
  `database_outbox` 574,693 미처리에 배수자 없음(524,258은 이 레인 이전부터).
  추가 행: 원자 13,554(새 파티션), scat 런 30,000, delam_obs 10,421, cell_sources
  395,052 — 기존 무접촉, 롤백 술어는 보고서에.
- `9d1d44e` 검증: 실PG 스크래치 스키마 14 tests, 주입 결함 6/6 빨강 — 다섯째는 첫
  시도에 초록이었고 테스트 탓이 아니었다: 픽스처가 패키지당 런 1이라 팬아웃 축이
  아예 안 굴러갔다. 재스캔 추가 후 빨강.
