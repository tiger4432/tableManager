# The console: case-control on one screen, and the kind catalog

**Date:** 2026-08-14 10:21 / 10:35 / 10:52 · **Domain:** Client + Server (조사 콘솔) · **Status:** 착지 — `b0d1606`, `1ddb937`, `3e85aff`

---

## 콘솔 (`b0d1606`) — 기한 항목, 새 페이지·모드·모달 없음

`ledger.html`이 조사 콘솔로 자랐다: 카탈로그에서 지은 kind 피커(대조 불가 kind에
「분모없음」 마크), 율과 분모가 항상 나란한 현황판(`2.40% 6/250`, `분모 250 ·
inspection_run · xray`), 세 갈래 모집단 분할(never-scanned 점선·분모 밖·산수를
찍어 독자가 제외를 검산 가능), 한 호출에서의 공통점/차이점(서버의 `flat` 평결만
버리고 `undeterminable` 유지), measured/observed/processed_with 공용 fact-chip 렌더러
(화자 배지·증거 ref·가정/근거). 추적 패널은 고정 4단이 아니라 **위치 연속성으로
이어진 가변 길이 hop 목록** — 픽스처가 DT를 두 번 걷고 두 hop 다 렌더, 불연속은
조용히 잇지 않고 「사슬 끊김」 빨강.

하네스가 콘솔 자신의 코드에서 잡은 결함이 남길 것이다: **`Number(null) === 0`** —
`Number.isFinite(Number(v))`가 명시적 null(서버의 「세지 않았다」)을 **측정된 0**으로
읽었다. 첫 드래프트에 실렸다: null 분모 슬라이스가 「검사 0회」, 분모 객체 없는
응답이 「분모 0」 — 둘 다 실측처럼 보인다. 서버 쪽에서 「없어서 0은 무해해서 0이
아니다」로 만났던 그 실패가 JS 강제변환으로 도착한 것. `numOrNull` 하나로 수리,
mutant로 유지. 레인이 안 발라 넘긴 분모 공백도 기록됐다: `factors[].found`의 `of`는
**found 카운트**라 「6건 중 5건이 B-3 경유」이지 「B-3의 void율 4.2%」가 아니다 —
축별 검사 수가 응답에 없어 장비별 결함율은 당시 계산 불가였고 패널이 한 줄로
말한다.

## 카탈로그 API (`1ddb937`) — 분모의 존재를 서버가 답한다

`GET /api/ledger/kinds`가 `finding_kinds.py`를 노출한다 — 자기 것은 아무것도 선언하지
않고. `has_denominator`는 서버가 답한다 — 목록 모양에서 능력을 추론하는 클라는
소유자 있는 규칙의 둘째 구현이다. 부재 셋이 구별 가능하게 유지된다: `atoms: null`
(아무도 안 셈) 대 `0`(세었고 빈 것), 방법 없는 kind의 `runs: null`, `/coverage`와
같은 세 상태 단어. `classes: []`는 스텁이 아니라 측정이다 — 어느 관측 표에도 class
컬럼이 없고 `delam_obs.interface`는 위치로 선언돼 있다. 스케일은 유계:

```sql
SELECT pg_relation_size(c.oid), c.reltuples FROM pg_class c
 WHERE c.oid = to_regclass(%(rel)s)   -- 256MB 초과 시 reltuples + atoms_exact: false
```

함정 둘이 유지됐다: 코드에 `void` 리터럴 0(새 테스트는 `bubble`/`crack`/`smudge`
레지스트리로 돌고 kind 이름이 코드에 나타나면 빨강), 원자 0인 kind는 숨기지 않고
목록에 남는다(행을 빼면 사용자가 kind의 존재를 알 수 없다).

## 피커 배선 (`3e85aff`) — 라이브 캡처가 손 픽스처가 못 찾을 구멍 셋을 찾았다

`has_denominator`가 `observed_by.length` 재유도에서 서버 읽기로 바뀌었다 — 둘의
합의가 위험이었지, 안전이 아니었다: 방법을 선언하고도 `has_denominator: false`인
카탈로그 행이 판별 픽스처다(유도는 true, 읽기는 false). 라이브 캡처가 번 것:
응답에 `trace`·`facts` 키가 아예 없음(부재 상태 렌더 확인 + 미래 캡처가 들고 오면
하네스가 «실패»하는 픽스처 가드); `populations.scanned_outside_universe` 2,500 —
세 수의 합이 universe와 안 닫히는 간극이 자기 줄을 얻음; `axes[].covered`는 인자
분모가 **아니다** — 본딩 축이 46,899 중 44,399에 닿는데 인자는 전부 46,899로 나눈다.
빠진 5.3%는 측정된 부재의 옷을 입은 데이터 공백 — 축 헤더가 다를 때만 「귀속 N/M」을
단다. 그리고 라이브 `default`가 `void` = `DEFAULT_FINDING_KIND`와 같아 「카탈로그를
읽는다」와 「상수에 손을 뻗는다」를 라이브가 판별 못 하므로, 다른 default의 구성
카탈로그가 그 옆에 앉았다 — **두 규칙이 합의하는 픽스처는 아무것도 판정하지 않는다.**

## 그때 남아 있던 것

- `b0d1606`: 213 단언, 43/43 mutant, 대조군 2/2 탈출, 콘솔 순 폼 컨트롤 증가 0(전
  내비게이션이 앵커). `1ddb937`의 보고 응답은 `assy_manager` 실물이고 독립 계수와
  일치(void_obs 91,756 · delam_obs 10,421 · sat 77,500 · scat 30,000). `3e85aff`:
  241 단언, 44/44 mutant, build exit 0.
- `:8080` 프로세스는 라우트보다 오래돼 `/kinds`가 404 — 피커는 재기동 전까지 강등
  상태를 보이는 중이었고 계약은 하네스에서 끝까지 채점됐다.
- 미해결로 남긴 것: 피커 정렬이 가나다라 「박리」가 「보이드」보다 앞(레지스트리
  정렬 결정), `GET /api/ledger/siblings`가 백엔드 라우트 표에 미등록.
