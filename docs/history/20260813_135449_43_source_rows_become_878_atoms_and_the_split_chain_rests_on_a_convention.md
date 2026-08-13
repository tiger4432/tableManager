# 43 source rows become 878 atoms, and the split chain rests on a convention

**Date:** 2026-08-13 13:54 · **Domain:** Server (정본 원장 / ledger slice 1 L1) · **Status:** 착지 — `f896020`

> ⚠️ **전부 격리 `assy_qa` 실측이다.** 운영 `lot_event`가 실제 SPLIT/MERGE 행을 들고 있는지는
> **운영에 대고 한 번 질의해야 알 수 있고, 여기 어느 레인도 그것을 돌릴 수 없다.**

---

## 배경 — 원장의 첫 층

`ledger_events` 테이블, 봉투(envelope), 닫힌 술어 어휘, 게이트, 그리고 `lot_event` 번역기가
착지했다. 물리 컬럼 열하나 — 일곱 필드 봉투를 평탄화한 것 — 이고 `occurred_at`으로 **월별
파티션**, `PRIMARY KEY (id, occurred_at)`.

실제 백필, 모든 수를 소스에 대고 교차 확인: `register` 245 · `has_wafer` 466 ·
`slot_map` 148 · `derived_from` 19. **합 878**(재검산 통과).

## 남길 값어치가 있는 판단은 «split»에 대한 것이다

MERGE의 소스 행은 이동 **전** 스냅숏이고 목적 행은 **후**다. 그래서 옮겨진 웨이퍼가 양쪽에
다 나타나고 **링크에 관례가 필요 없다.**

SPLIT의 두 행은 **둘 다 이동 후**다. 실측: 14건 전부에서 **웨이퍼 겹침이 0.**
거기서 슬롯 체인이 성립하려면 누군가가 「split은 슬롯 번호를 보존한다」를 **믿어야** 하고,
**그 믿음은 데이터에 없다.**

## 그래서 번역기가 그것을 들지 않는다

관례는 **이벤트 타입별로 config에 선언**되고 `source_translator_ver`에 해시되며, 원자마다
버전이 `#<derivation>`으로 끝난다.

```python
# 🔴 `<source>/<cfg version>/rules:<hash>#<derivation>` — 이 원자를 만든 «규칙».
#     WHERE source_translator_ver LIKE '%#slot_preserving'
source_translator_ver=f"{self.translator_ver}#{derivation}",
```

**878 중 127**이 여기에 걸린다. 열두 번째 컬럼 없이 관례에 기댄 원자와 소스가 실제로 발화한
원자를 갈라낼 수 있다. 그것들이 관측이 아니라 **추론**으로 등급 매겨져야 하는지는 온톨로지
소유자에게 회부됐다 — **어느 쪽이든 메커니즘은 바뀌지 않고, 분리 가능하게 둔 이유가 그것이다.**

```json
"split": { "lineage": "parent_child", "slot_pairing": "slot_preserving",
  "__comment": "slot_preserving is an OPERATOR DECLARATION, not something the
   translator inferred ..." },
"merge": { "lineage": "parent_child", "slot_pairing": "shared_wafer",
  "__comment": "... shared_wafer therefore needs no convention at all here." }
```

## 게이트가 «실제» 데이터를 거절했다

누군가 이미 `parent_lot`을 들고 있는 행의 `child_lot`을 손으로 편집해 놓았다. 「부모를 읽고
없으면 자식」류의 순서 — **레인이 처음 쓴 것이 그것이다** — 는 그 행의 웨이퍼 25장을 소스가
주장한 적 없는 계보에 **조용히** 붙인다. 지금은 격리돼 이름으로 거절되고 전체 사유가 운영자
로그에 남는다.

두 번째 편집된 행은 **일부러 거절되지 않는다** — 참이지만 불완전한 주장을 하고 있어서
`incomplete`로 계수된다. 그래야 추적이 **사유 있는 끊긴 체인**이 되지 그냥 구멍이 되지 않는다.

거절 어휘는 번호가 아니라 **이름**이다(`REFUSE_UNDECLARED_DERIVATION`,
`REFUSE_ATOMICITY`, …). 거절은 원자 단위가 아니라 **분자 단위**다 — 반쪽 분자가 온전한
분자로 오인되면 안 되고, 분자를 거절하면 지연 리포트가 볼 수 있는 구멍이 남는다.

## 착지 전에 고친 것

실행 노트가 「0 lost」라고 적는 동안 **26개 원자가 아예 쓰이지 않았다** — 원자가 되기 전의
거절은 `atoms_lost`에 기여하지 않기 때문이다. `source_rows`와 `built_atoms_discarded`가
이제 별개의 수다.

## 아키텍처 영향

- `register`의 목적어는 ∅이고 고정된 enum에는 ∅이 없다. 그래서 `object_kind IS NULL`은
  `register`에만 합법이고 다른 무엇에도 아니며, CHECK가 **양방향으로** 강제한다.
- 유니크 인덱스는 해시가 아니라 **컬럼 자체**에 걸린다. 해시 키는 Python(쓰기 시점)과
  PostgreSQL(인덱스 표현식)이 **똑같이** 계산해야 하는데 둘은 JSON 철자가 다르고, 어긋나면
  **조용히** 실패한다(모든 행이 새 행으로 보인다).
- 이 레인과 추적 레인의 픽스처가 갈린 자리에서 판정했다: 파티션은 **월별**(원자당 673 B,
  1,000만 원자면 ~6.7 GB — 연별 파티션은 한 해가 통째로 한 릴레이션이라 pruning을 무력화한다),
  그리고 `source_who` / `source_translator_ver` / `source_raw_ref`는 **NOT NULL**(누가 어떤
  번역기로 어느 원시 행에서 주장했는지 말 못 하는 원자는 증거가 아니다).
- 🔴 **모든 인덱스는 이름 붙은 소비자를 가져야 한다.** 후보 셋이 지어지고, 측정되고,
  소비자가 없어서 **제거**됐다(1,000만 원자에서 각 0.3–0.6 GB). 값을 `schema.py`에 적어
  두었으므로 되돌리는 것은 **숫자가 있는 결정**이다.

## 그때 남아 있던 것

- 15파일 +4,180/-0. 그중 테스트가 1,262줄.
- 멱등성은 **독립된 두 그물로 각각** 증명됐다 — 커서(2회차가 0행을 읽는다)와
  `uq_ledger_atom`(커서 리셋: 633 시도, 0 삽입, 633 dedupe).
- 반쪽 착지: 페이지 3에서 첫 청크가 이미 INSERT된 뒤 두 번째 문장이 raise하면 **0개 원자가
  살아남는다.** 경계를 걷어내면 원자가 남는다 — 그것이 그 테스트가 빨개질 수 있음의 증명이다.
- 🔴 `occurred_at_timezone`이 **`UTC`로 출하됐다** — 명시된 강제 추측이고, fab 타임스탬프가
  로컬이면 모든 원자가 아홉 시간 틀린다. (같은 날 `bee1aeb`이 이 자리를 다시 연다.)
- 검증: 커밋되는 트리에서 69 passed / 0 skipped, PostgreSQL 절반을 격리 `assy_qa`에 대고
  **실제로** 실행. 기본 실행은 그 18개를 건너뛰고 **51 green을 보고하는데, 그것은 통과처럼
  보인다.**
